import ast
import keyword
import logging
import math
import tokenize
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from io import StringIO
from pathlib import Path
from textwrap import dedent

from app.analysis.services.scan_engine.pipeline.code_embedding_service import (
    CodeEmbeddingProvider,
    CodeEmbeddingService,
)
from app.analysis.services.scan_engine.pipeline.metrics_vector import LayerResult, MetricsVector

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class CodeBlock:
    id: str
    file_path: Path
    kind: str
    start_line: int
    end_line: int
    source: str
    embedding_text: str
    syntax_tokens: tuple[str, ...]
    line_numbers: tuple[int, ...]

    @property
    def loc(self) -> int:
        return len(self.line_numbers)


@dataclass(slots=True, frozen=True)
class BlockMatch:
    block_id: str
    file_path: Path
    start_line: int
    end_line: int
    similarity: float


@dataclass(slots=True)
class DuplicationAnalysisContext:
    vectors: list[MetricsVector]
    relative_path_by_absolute_path: dict[Path, str]
    blocks: list[CodeBlock] = field(default_factory=list)
    blocks_by_path: dict[Path, list[CodeBlock]] = field(default_factory=dict)
    read_errors: dict[Path, str] = field(default_factory=dict)
    syntax_matches_by_block: dict[str, list[BlockMatch]] = field(default_factory=dict)
    semantic_matches_by_block: dict[str, list[BlockMatch]] = field(default_factory=dict)
    semantic_error: str | None = None


MetricHandler = Callable[[DuplicationAnalysisContext, Path], int | float | None]


class DuplicationAnalysisLayer:
    """Layer 3 - cross-file syntax and semantic duplication analysis."""

    LAYER_NAME = "duplication_analysis"
    DEFAULT_SYNTAX_SIMILARITY_THRESHOLD = 0.96
    DEFAULT_SEMANTIC_SIMILARITY_THRESHOLD = 0.86
    DEFAULT_MIN_BLOCK_LINES = 3
    DEFAULT_MIN_BLOCK_TOKENS = 18
    MATCH_SAMPLE_LIMIT = 5

    def __init__(
        self,
        embedding_service: CodeEmbeddingProvider | None = None,
        syntax_similarity_threshold: float = DEFAULT_SYNTAX_SIMILARITY_THRESHOLD,
        semantic_similarity_threshold: float = DEFAULT_SEMANTIC_SIMILARITY_THRESHOLD,
        min_block_lines: int = DEFAULT_MIN_BLOCK_LINES,
        min_block_tokens: int = DEFAULT_MIN_BLOCK_TOKENS,
    ) -> None:
        self.embedding_service = embedding_service or CodeEmbeddingService()
        self.syntax_similarity_threshold = syntax_similarity_threshold
        self.semantic_similarity_threshold = semantic_similarity_threshold
        self.min_block_lines = min_block_lines
        self.min_block_tokens = min_block_tokens
        self.metric_handlers: dict[str, MetricHandler] = {
            "duplicate_blocks_count": self.duplicate_blocks_count,
            "duplicate_loc_count": self.duplicate_loc_count,
            "duplication_group_size": self.duplication_group_size,
            "semantic_duplicate_blocks_count": self.semantic_duplicate_blocks_count,
            "max_similarity_score": self.max_similarity_score,
            "duplicate_file_candidates_count": self.duplicate_file_candidates_count,
        }

    def run(self, vectors: list[MetricsVector]) -> LayerResult:
        logger.info("[DUPLICATION] running duplication analysis on %d files", len(vectors))
        self._validate_vectors(vectors)

        if not vectors:
            logger.warning("[DUPLICATION] no files to analyze")
            return LayerResult(vectors=vectors)

        context = self._build_context(vectors)
        self._find_syntax_duplicates(context)
        self._find_semantic_duplicates(context)

        for vector in vectors:
            assert vector.absolute_path is not None
            path = vector.absolute_path
            try:
                for metric_name, handler in self.metric_handlers.items():
                    try:
                        vector.metrics[metric_name] = handler(context, path)
                    except Exception as exc:
                        vector.errors.append(f"{metric_name} failed: {exc}")
                        vector.metrics[metric_name] = None

                vector.metadata = self._metadata_for_path(context, path)
                if path in context.read_errors:
                    vector.errors.append(f"duplication source failed: {context.read_errors[path]}")
                if context.semantic_error and context.blocks_by_path.get(path):
                    vector.errors.append(f"semantic duplication failed: {context.semantic_error}")
            except Exception as exc:
                logger.warning("[DUPLICATION] failed to build vector for %s: %s", path, exc)
                vector.metrics = self._safe_default_metrics()
                vector.errors.append(f"duplication metrics failed: {exc}")

        logger.info(
            "[DUPLICATION] completed duplication analysis on %d files with %d blocks",
            len(vectors),
            len(context.blocks),
        )
        return LayerResult(vectors=vectors)

    # -- Context construction ---------------------------------------------

    def _build_context(self, vectors: list[MetricsVector]) -> DuplicationAnalysisContext:
        relative_path_by_absolute_path = {
            vector.absolute_path: vector.relative_path
            for vector in vectors
            if vector.absolute_path is not None and vector.relative_path is not None
        }
        context = DuplicationAnalysisContext(
            vectors=vectors,
            relative_path_by_absolute_path=relative_path_by_absolute_path,
        )

        for path in relative_path_by_absolute_path:
            try:
                source = path.read_text(encoding="utf-8")
                blocks = self._extract_blocks(path, source)
                context.blocks_by_path[path] = blocks
                context.blocks.extend(blocks)
            except Exception as exc:
                logger.warning("[DUPLICATION] failed to extract blocks from %s: %s", path, exc)
                context.blocks_by_path[path] = []
                context.read_errors[path] = str(exc)

        return context

    def _extract_blocks(self, path: Path, source: str) -> list[CodeBlock]:
        tree = ast.parse(source)
        lines = source.splitlines()
        candidates: list[tuple[str, int, int]] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._add_node_candidate(candidates, "function", node)
            elif isinstance(node, ast.ClassDef) and self._is_class_block_candidate(node):
                self._add_node_candidate(candidates, "class", node)

        candidates.extend(self._top_level_statement_groups(tree))

        blocks: list[CodeBlock] = []
        for index, (kind, start_line, end_line) in enumerate(sorted(set(candidates), key=lambda item: (item[1], item[2], item[0]))):
            block = self._build_block(path, kind, index, start_line, end_line, lines)
            if block is not None:
                blocks.append(block)

        if not blocks:
            block = self._build_block(path, "module", 0, 1, len(lines), lines)
            if block is not None:
                blocks.append(block)

        return blocks

    def _add_node_candidate(self, candidates: list[tuple[str, int, int]], kind: str, node: ast.AST) -> None:
        start_line = getattr(node, "lineno", None)
        end_line = getattr(node, "end_lineno", None)
        if start_line is not None and end_line is not None:
            candidates.append((kind, int(start_line), int(end_line)))

    def _is_class_block_candidate(self, node: ast.ClassDef) -> bool:
        return not any(isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for child in node.body)

    def _top_level_statement_groups(self, tree: ast.Module) -> list[tuple[str, int, int]]:
        groups: list[tuple[str, int, int]] = []
        current_start: int | None = None
        current_end: int | None = None
        excluded = (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

        for statement in tree.body:
            if isinstance(statement, excluded):
                if current_start is not None and current_end is not None:
                    groups.append(("module_block", current_start, current_end))
                current_start = None
                current_end = None
                continue

            start_line = getattr(statement, "lineno", None)
            end_line = getattr(statement, "end_lineno", None)
            if start_line is None or end_line is None:
                continue

            if current_start is None:
                current_start = int(start_line)
            current_end = int(end_line)

        if current_start is not None and current_end is not None:
            groups.append(("module_block", current_start, current_end))

        return groups

    def _build_block(
        self,
        path: Path,
        kind: str,
        index: int,
        start_line: int,
        end_line: int,
        lines: list[str],
    ) -> CodeBlock | None:
        if start_line < 1 or end_line < start_line or not lines:
            return None

        source = "\n".join(lines[start_line - 1 : end_line])
        embedding_text = self._normalize_for_embedding(source)
        syntax_tokens = self._syntax_tokens(source)
        line_numbers = self._code_line_numbers(lines, start_line, end_line)

        if len(line_numbers) < self.min_block_lines or len(syntax_tokens) < self.min_block_tokens:
            return None

        return CodeBlock(
            id=f"{path.as_posix()}:{start_line}:{end_line}:{index}",
            file_path=path,
            kind=kind,
            start_line=start_line,
            end_line=end_line,
            source=source,
            embedding_text=embedding_text,
            syntax_tokens=syntax_tokens,
            line_numbers=line_numbers,
        )

    # -- Duplicate detection ----------------------------------------------

    def _find_syntax_duplicates(self, context: DuplicationAnalysisContext) -> None:
        matches_by_block: dict[str, list[BlockMatch]] = defaultdict(list)

        for index, left in enumerate(context.blocks):
            for right in context.blocks[index + 1 :]:
                if left.file_path == right.file_path:
                    continue

                similarity = self._syntax_similarity(left, right)
                if similarity < self.syntax_similarity_threshold:
                    continue

                self._add_match(matches_by_block, left, right, similarity)
                self._add_match(matches_by_block, right, left, similarity)

        context.syntax_matches_by_block = dict(matches_by_block)

    def _find_semantic_duplicates(self, context: DuplicationAnalysisContext) -> None:
        if len(context.blocks) < 2:
            return

        try:
            embeddings = self.embedding_service.encode([block.embedding_text for block in context.blocks])
            if len(embeddings) != len(context.blocks):
                raise RuntimeError(
                    f"embedding service returned {len(embeddings)} vectors for {len(context.blocks)} blocks"
                )
        except Exception as exc:
            logger.warning("[DUPLICATION] semantic duplication analysis failed: %s", exc)
            context.semantic_error = str(exc)
            context.semantic_matches_by_block = {}
            return

        matches_by_block: dict[str, list[BlockMatch]] = defaultdict(list)
        for index, left in enumerate(context.blocks):
            for right_index in range(index + 1, len(context.blocks)):
                right = context.blocks[right_index]
                if left.file_path == right.file_path:
                    continue

                similarity = self._cosine_similarity(embeddings[index], embeddings[right_index])
                if not math.isfinite(similarity):
                    continue
                if similarity < self.semantic_similarity_threshold:
                    continue

                self._add_match(matches_by_block, left, right, similarity)
                self._add_match(matches_by_block, right, left, similarity)

        context.semantic_matches_by_block = dict(matches_by_block)

    def _add_match(
        self,
        matches_by_block: dict[str, list[BlockMatch]],
        source: CodeBlock,
        target: CodeBlock,
        similarity: float,
    ) -> None:
        if not math.isfinite(similarity):
            return

        matches_by_block[source.id].append(
            BlockMatch(
                block_id=target.id,
                file_path=target.file_path,
                start_line=target.start_line,
                end_line=target.end_line,
                similarity=round(float(similarity), 6),
            )
        )

    # -- Metrics -----------------------------------------------------------

    def duplicate_blocks_count(self, context: DuplicationAnalysisContext, path: Path) -> int:
        logger.debug("[DUPLICATION] computing syntax duplicate block count")
        return len(self._syntax_duplicate_blocks(context, path))

    def duplicate_loc_count(self, context: DuplicationAnalysisContext, path: Path) -> int:
        logger.debug("[DUPLICATION] computing syntax duplicate LOC count")
        return len({
            line_number
            for block in self._syntax_duplicate_blocks(context, path)
            for line_number in block.line_numbers
        })

    def duplication_group_size(self, context: DuplicationAnalysisContext, path: Path) -> int:
        logger.debug("[DUPLICATION] computing syntax duplication group size")
        return self._max_group_size(
            self._syntax_duplicate_blocks(context, path),
            context.syntax_matches_by_block,
        )

    def semantic_duplicate_blocks_count(
        self,
        context: DuplicationAnalysisContext,
        path: Path,
    ) -> int | None:
        logger.debug("[DUPLICATION] computing semantic duplicate block count")
        if context.semantic_error is not None:
            return None
        return len(self._semantic_duplicate_blocks(context, path))

    def max_similarity_score(
        self,
        context: DuplicationAnalysisContext,
        path: Path,
    ) -> float | None:
        logger.debug("[DUPLICATION] computing max semantic similarity score")
        if context.semantic_error is not None:
            return None
        return self._max_similarity(
            self._semantic_duplicate_blocks(context, path),
            context.semantic_matches_by_block,
        )

    def duplicate_file_candidates_count(self, context: DuplicationAnalysisContext, path: Path) -> int:
        logger.debug("[DUPLICATION] computing duplicate candidate file count")
        syntax_duplicate_blocks = self._syntax_duplicate_blocks(context, path)
        semantic_duplicate_blocks = self._semantic_duplicate_blocks(context, path)
        peer_files = self._peer_files_for_blocks(
            [*syntax_duplicate_blocks, *semantic_duplicate_blocks],
            context.syntax_matches_by_block,
            context.semantic_matches_by_block,
        )
        return len(peer_files)

    def _metadata_for_path(self, context: DuplicationAnalysisContext, path: Path) -> dict[str, object]:
        blocks = context.blocks_by_path.get(path, [])
        metadata: dict[str, object] = {
            "blocks_analyzed_count": len(blocks),
            "embedding_model": getattr(self.embedding_service, "model_id", self.embedding_service.__class__.__name__),
            "syntax_similarity_threshold": self.syntax_similarity_threshold,
            "semantic_similarity_threshold": self.semantic_similarity_threshold,
            "min_block_lines": self.min_block_lines,
            "min_block_tokens": self.min_block_tokens,
            "syntax_duplicate_blocks_sample": self._match_sample(
                context,
                blocks,
                context.syntax_matches_by_block,
            ),
            "semantic_duplicate_blocks_sample": self._match_sample(
                context,
                blocks,
                context.semantic_matches_by_block,
            ),
        }
        if context.semantic_error:
            metadata["semantic_error"] = context.semantic_error
        return metadata

    def _syntax_duplicate_blocks(self, context: DuplicationAnalysisContext, path: Path) -> list[CodeBlock]:
        return [
            block
            for block in context.blocks_by_path.get(path, [])
            if context.syntax_matches_by_block.get(block.id)
        ]

    def _semantic_duplicate_blocks(self, context: DuplicationAnalysisContext, path: Path) -> list[CodeBlock]:
        return [
            block
            for block in context.blocks_by_path.get(path, [])
            if context.semantic_matches_by_block.get(block.id)
        ]

    def _peer_files_for_blocks(
        self,
        blocks: list[CodeBlock],
        *match_maps: dict[str, list[BlockMatch]],
    ) -> set[Path]:
        peer_files: set[Path] = set()
        for block in blocks:
            for match_map in match_maps:
                peer_files.update(match.file_path for match in match_map.get(block.id, []))
        return peer_files

    def _max_group_size(
        self,
        blocks: list[CodeBlock],
        matches_by_block: dict[str, list[BlockMatch]],
    ) -> int:
        group_sizes = [
            1 + len({match.file_path for match in matches_by_block.get(block.id, [])})
            for block in blocks
        ]
        return max(group_sizes, default=0)

    def _max_similarity(
        self,
        blocks: list[CodeBlock],
        matches_by_block: dict[str, list[BlockMatch]],
    ) -> float:
        similarities = [
            match.similarity
            for block in blocks
            for match in matches_by_block.get(block.id, [])
            if math.isfinite(match.similarity)
        ]
        return round(max(similarities, default=0.0), 6)

    def _match_sample(
        self,
        context: DuplicationAnalysisContext,
        blocks: list[CodeBlock],
        matches_by_block: dict[str, list[BlockMatch]],
    ) -> list[dict[str, object]]:
        sample: list[dict[str, object]] = []
        for block in blocks:
            matches = [
                match
                for match in matches_by_block.get(block.id, [])
                if math.isfinite(match.similarity)
            ]
            if not matches:
                continue

            sample.append(
                {
                    "kind": block.kind,
                    "start_line": block.start_line,
                    "end_line": block.end_line,
                    "matched_files": sorted(
                        {
                            context.relative_path_by_absolute_path[match.file_path]
                            for match in matches
                        }
                    )[: self.MATCH_SAMPLE_LIMIT],
                    "max_similarity": round(max(match.similarity for match in matches), 6),
                }
            )
            if len(sample) >= self.MATCH_SAMPLE_LIMIT:
                break

        return sample

    # -- Normalization and similarity helpers -----------------------------

    def _normalize_for_embedding(self, source: str) -> str:
        return "\n".join(line.rstrip() for line in dedent(source).strip().splitlines())

    def _syntax_tokens(self, source: str) -> tuple[str, ...]:
        tokens: list[str] = []
        reader = StringIO(dedent(source)).readline

        try:
            for token in tokenize.generate_tokens(reader):
                if token.type in {
                    tokenize.COMMENT,
                    tokenize.INDENT,
                    tokenize.DEDENT,
                    tokenize.NEWLINE,
                    tokenize.NL,
                    tokenize.ENDMARKER,
                }:
                    continue

                if token.type == tokenize.NAME:
                    tokens.append(token.string if keyword.iskeyword(token.string) else "NAME")
                elif token.type == tokenize.STRING:
                    tokens.append("STRING")
                elif token.type == tokenize.NUMBER:
                    tokens.append("NUMBER")
                elif token.type == tokenize.OP:
                    tokens.append(token.string)
                else:
                    tokens.append(tokenize.tok_name.get(token.type, token.string))
        except tokenize.TokenError:
            return tuple(dedent(source).split())

        return tuple(tokens)

    def _code_line_numbers(self, lines: list[str], start_line: int, end_line: int) -> tuple[int, ...]:
        line_numbers: list[int] = []
        for line_number in range(start_line, end_line + 1):
            line = lines[line_number - 1]
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                line_numbers.append(line_number)
        return tuple(line_numbers)

    def _syntax_similarity(self, left: CodeBlock, right: CodeBlock) -> float:
        if left.syntax_tokens == right.syntax_tokens:
            return 1.0

        if not left.syntax_tokens or not right.syntax_tokens:
            return 0.0

        length_ratio = min(len(left.syntax_tokens), len(right.syntax_tokens)) / max(
            len(left.syntax_tokens),
            len(right.syntax_tokens),
        )
        if length_ratio < self.syntax_similarity_threshold - 0.15:
            return 0.0

        return SequenceMatcher(
            None,
            left.syntax_tokens,
            right.syntax_tokens,
            autojunk=False,
        ).ratio()

    def _cosine_similarity(self, left: list[float], right: list[float]) -> float:
        if len(left) != len(right):
            raise ValueError(f"Embedding dimensions differ: {len(left)} != {len(right)}")

        dot = 0.0
        left_norm = 0.0
        right_norm = 0.0
        for left_value, right_value in zip(left, right, strict=True):
            dot += left_value * right_value
            left_norm += left_value * left_value
            right_norm += right_value * right_value

        denominator = math.sqrt(left_norm) * math.sqrt(right_norm)
        if denominator == 0.0:
            return 0.0
        return dot / denominator

    # -- Path helpers ------------------------------------------------------

    def _validate_vectors(self, vectors: list[MetricsVector]) -> None:
        if any(vector.absolute_path is None or vector.relative_path is None for vector in vectors):
            raise ValueError("Duplication analysis requires both absolute_path and relative_path")

    def _safe_default_metrics(self) -> dict[str, int | float | None]:
        return {
            "duplicate_blocks_count": None,
            "duplicate_loc_count": None,
            "duplication_group_size": None,
            "semantic_duplicate_blocks_count": None,
            "max_similarity_score": None,
            "duplicate_file_candidates_count": None,
        }
