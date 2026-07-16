import logging
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.analysis.services.scan_engine.pipeline.metrics_vector import (
    LayerResult,
    MetricsVector,
    validate_relative_path,
)

try:
    from radon.complexity import cc_visit
except ImportError:
    cc_visit = None

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class HistoryAnalysisContext:
    absolute_path: Path
    repo_root: Path
    relative_path: str
    commit_hashes: list[str] | None = None
    recent_commit_hashes: list[str] | None = None
    commit_subjects: list[str] | None = None
    co_changed_files: set[str] = field(default_factory=set)
    co_change_commits_analyzed: int = 0
    co_change_bulk_commits_skipped: int = 0


MetricHandler = Callable[[HistoryAnalysisContext], int | float | str | bool | None]


class HistoryAnalysisLayer:
    """Layer 2 - local git history analysis, per file."""

    LAYER_NAME = "history_analysis"
    GIT_TIMEOUT_SECONDS = 10
    MAX_COMMITS_FOR_CO_CHANGE = 100
    MAX_FILES_PER_CO_CHANGE_COMMIT = 25
    BUG_KEYWORDS = ("fix", "bug", "issue", "patch", "hotfix", "repair", "correct", "defect")

    def __init__(self) -> None:
        self.metric_handlers: dict[str, MetricHandler] = {
            "contributors_count": self.contributors_count,
            "update_count": self.update_count,
            "recent_update_count": self.recent_update_count,
            "historical_update_count": self.historical_update_count,
            "recent_to_lifetime_update_ratio": self.recent_to_lifetime_update_ratio,
            "churn_rate": self.churn_rate,
            "churn_to_size_ratio": self.churn_to_size_ratio,
            "bug_fix_commit_count": self.bug_fix_commit_count,
            "bug_fix_ratio": self.bug_fix_ratio,
            "cyclomatic_complexity_growth_rate": self.cyclomatic_complexity_growth_rate,
            "co_change_file_count": self.co_change_file_count,
        }

    def run(self, vector: MetricsVector) -> LayerResult:
        if vector.absolute_path is None or vector.relative_path is None:
            raise ValueError("History analysis requires both absolute_path and relative_path")

        try:
            repo_root = self._discover_repo_root(vector.absolute_path)
            context = HistoryAnalysisContext(
                absolute_path=vector.absolute_path,
                repo_root=repo_root,
                relative_path=vector.relative_path,
            )
        except Exception as exc:
            vector.errors.append(f"Failed to prepare git history context: {exc}")
            vector.metrics = self._safe_default_metrics()
            return LayerResult.from_vector(vector)

        for metric_name, handler in self.metric_handlers.items():
            try:
                vector.metrics[metric_name] = handler(context)
            except Exception as exc:
                vector.errors.append(f"{metric_name} failed: {exc}")
                vector.metrics[metric_name] = None

        vector.metadata.update(
            {
                "co_change_commits_analyzed": context.co_change_commits_analyzed,
                "co_change_bulk_commits_skipped": context.co_change_bulk_commits_skipped,
                "co_changed_files": sorted(context.co_changed_files),
                "co_changed_files_sample": sorted(context.co_changed_files)[:10],
            }
        )
        logger.info("[HISTORY] Completed history analysis for %s with metrics: %s", vector.relative_path, vector.metrics)
        return LayerResult.from_vector(vector)

    # -- Git metrics -------------------------------------------------------

    def contributors_count(self, context: HistoryAnalysisContext) -> int:
        logger.debug("[HISTORY] computing contributor count")
        emails = self._git_lines(context, ["log", "--follow", "--format=%ae", "--", context.relative_path])
        return len({email.strip() for email in emails if email.strip()})

    def update_count(self, context: HistoryAnalysisContext) -> int:
        logger.debug("[HISTORY] computing lifetime update count")
        return len(self._commit_hashes(context))

    def recent_update_count(self, context: HistoryAnalysisContext) -> int:
        logger.debug("[HISTORY] computing recent update count")
        return len(self._recent_commit_hashes(context))

    def historical_update_count(self, context: HistoryAnalysisContext) -> int:
        logger.debug("[HISTORY] computing historical update count")
        return max(0, self.update_count(context) - self.recent_update_count(context))

    def recent_to_lifetime_update_ratio(self, context: HistoryAnalysisContext) -> float:
        logger.debug("[HISTORY] computing recent/lifetime update ratio")
        lifetime_updates = self.update_count(context)
        if lifetime_updates == 0:
            return 0.0
        return round(self.recent_update_count(context) / lifetime_updates, 3)

    def churn_rate(self, context: HistoryAnalysisContext) -> int:
        logger.debug("[HISTORY] computing churn rate")
        total_churn = 0
        lines = self._git_lines(
            context,
            ["log", "--follow", "--numstat", "--format=", "--", context.relative_path],
        )
        for line in lines:
            parts = line.split()
            if len(parts) < 3:
                continue
            total_churn += self._numstat_value(parts[0]) + self._numstat_value(parts[1])
        return total_churn

    def churn_to_size_ratio(self, context: HistoryAnalysisContext) -> float:
        logger.debug("[HISTORY] computing churn/size ratio")
        return round(self.churn_rate(context) / max(1, self._current_loc(context.absolute_path)), 3)

    def bug_fix_commit_count(self, context: HistoryAnalysisContext) -> int:
        logger.debug("[HISTORY] computing bug-fix commit count")
        return sum(
            1
            for subject in self._modification_commit_subjects(context)
            if self._is_bug_fix_subject(subject)
        )

    def bug_fix_ratio(self, context: HistoryAnalysisContext) -> float:
        logger.debug("[HISTORY] computing bug-fix ratio")
        modification_count = max(0, self.update_count(context) - 1)
        if modification_count == 0:
            return 0.0
        return round(self.bug_fix_commit_count(context) / modification_count, 3)

    def cyclomatic_complexity_growth_rate(self, context: HistoryAnalysisContext) -> float:
        logger.debug("[HISTORY] computing cyclomatic complexity growth rate")
        if cc_visit is None:
            raise RuntimeError("radon is not installed")

        current_source = context.absolute_path.read_text(encoding="utf-8")
        current_complexity = self._average_cyclomatic_complexity(current_source)
        oldest_source = self._oldest_file_source(context)
        oldest_complexity = self._average_cyclomatic_complexity(oldest_source)
        return round(current_complexity - oldest_complexity, 3)

    def co_change_file_count(self, context: HistoryAnalysisContext) -> int:
        logger.debug("[HISTORY] computing co-change file count")
        if not context.co_changed_files and context.co_change_commits_analyzed == 0:
            self._compute_co_changed_files(context)
        return len(context.co_changed_files)

    # -- Helpers -----------------------------------------------------------

    def _discover_repo_root(self, file_path: Path) -> Path:
        start_dir = file_path.parent if file_path.is_file() else file_path
        output = self._run_git(start_dir, ["rev-parse", "--show-toplevel"])
        return Path(output.strip()).resolve()

    def _commit_hashes(self, context: HistoryAnalysisContext) -> list[str]:
        if context.commit_hashes is None:
            context.commit_hashes = self._git_lines(
                context,
                ["log", "--follow", "--format=%H", "--", context.relative_path],
            )
        return context.commit_hashes

    def _recent_commit_hashes(self, context: HistoryAnalysisContext) -> list[str]:
        if context.recent_commit_hashes is None:
            context.recent_commit_hashes = self._git_lines(
                context,
                [
                    "log",
                    "--follow",
                    "--since=3 months ago",
                    "--format=%H",
                    "--",
                    context.relative_path,
                ],
            )
        return context.recent_commit_hashes

    def _commit_subjects(self, context: HistoryAnalysisContext) -> list[str]:
        if context.commit_subjects is None:
            context.commit_subjects = self._git_lines(
                context,
                ["log", "--follow", "--format=%s", "--", context.relative_path],
            )
        return context.commit_subjects

    def _modification_commit_subjects(self, context: HistoryAnalysisContext) -> list[str]:
        subjects = self._commit_subjects(context)
        return subjects[:-1] if subjects else []

    def _oldest_file_source(self, context: HistoryAnalysisContext) -> str:
        commits = self._git_lines(
            context,
            ["log", "--follow", "--reverse", "--format=%H", "--", context.relative_path], # --follow tracks renames
        )
        if not commits:
            return context.absolute_path.read_text(encoding="utf-8")

        return self._git_output(context, ["show", f"{commits[0]}:{context.relative_path}"])

    def _compute_co_changed_files(self, context: HistoryAnalysisContext) -> None:
        commit_hashes = self._commit_hashes(context)
        modification_commits = commit_hashes[:-1] if commit_hashes else []
        commits = modification_commits[: self.MAX_COMMITS_FOR_CO_CHANGE]
        context.co_change_commits_analyzed = len(commits)

        for commit_hash in commits:
            changed_files = self._git_lines(
                context,
                ["diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash],
            )
            if len(changed_files) > self.MAX_FILES_PER_CO_CHANGE_COMMIT:
                context.co_change_bulk_commits_skipped += 1
                continue

            for changed_file in changed_files:
                normalized = changed_file.strip()
                if not normalized or normalized == context.relative_path:
                    continue
                try:
                    context.co_changed_files.add(validate_relative_path(normalized))
                except (TypeError, ValueError):
                    logger.warning("[HISTORY] ignoring invalid co-changed path: %s", normalized)

    def _git_lines(self, context: HistoryAnalysisContext, args: list[str]) -> list[str]:
        output = self._git_output(context, args)
        return [line for line in output.splitlines() if line.strip()]

    def _git_output(self, context: HistoryAnalysisContext, args: list[str]) -> str:
        return self._run_git(context.repo_root, args)

    def _run_git(self, cwd: Path, args: list[str]) -> str:
        command = ["git", *args]
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                shell=False,
                capture_output=True,
                text=True,
                timeout=self.GIT_TIMEOUT_SECONDS,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("Git executable is not available") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Git command timed out: {' '.join(command)}") from exc

        if result.returncode != 0:
            output = (result.stderr or result.stdout or "").strip()
            if len(output) > 500:
                output = output[-500:]
            raise RuntimeError(f"Git command failed ({result.returncode}): {' '.join(command)}: {output}")

        return result.stdout

    def _average_cyclomatic_complexity(self, source: str) -> float:
        blocks = cc_visit(source)
        values = [
            int(block.complexity)
            for block in blocks
            if hasattr(block, "complexity") and not hasattr(block, "methods")
        ]
        if not values:
            return 0.0
        return float(sum(values) / len(values))

    def _current_loc(self, file_path: Path) -> int:
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                return sum(1 for _ in file)
        except OSError:
            return 1

    def _numstat_value(self, value: str) -> int:
        return int(value) if value.isdigit() else 0

    def _is_bug_fix_subject(self, subject: str) -> bool:
        normalized = subject.lower()
        return any(keyword in normalized for keyword in self.BUG_KEYWORDS)

    def _safe_default_metrics(self) -> dict[str, int | float | None]:
        return {
            "contributors_count": None,
            "update_count": None,
            "recent_update_count": None,
            "historical_update_count": None,
            "recent_to_lifetime_update_ratio": None,
            "churn_rate": None,
            "churn_to_size_ratio": None,
            "bug_fix_commit_count": None,
            "bug_fix_ratio": None,
            "cyclomatic_complexity_growth_rate": None,
            "co_change_file_count": None,
        }
