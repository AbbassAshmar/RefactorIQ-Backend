import ast
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.analysis.services.scan_engine.pipeline.metrics_vector import MetricsVector

try:
    import networkx as nx
except ImportError:
    nx = None

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ArchitectureGraphContext:
    repo_root: Path
    file_paths: list[Path]
    node_by_path: dict[Path, str]
    module_to_node: dict[str, str]
    graph: Any
    betweenness: dict[str, float]
    sccs: list[dict[str, list[str] | list[list[str]]]]
    scc_size_by_node: dict[str, int]


MetricHandler = Callable[[ArchitectureGraphContext, str], int | float | None]


class ArchitectureAnalysisLayer:
    """Layer 4 - architectural influence analysis, cross-file."""

    LAYER_NAME = "architecture_analysis"

    def __init__(self) -> None:
        self.metric_handlers: dict[str, MetricHandler] = {
            "fan_in": self.fan_in,
            "fan_out": self.fan_out,
            "transitive_dependents_count": self.transitive_dependents_count,
            "betweenness_centrality": self.betweenness_centrality,
            "circular_dependency_size": self.circular_dependency_size,
            "instability_index": self.instability_index,
        }

    def run(self, file_paths: list[str | os.PathLike[str]]) -> list[MetricsVector]:
        logger.info("[ARCHITECTURE] running architecture analysis on %d files", len(file_paths))

        normalized_paths = [Path(file_path).resolve() for file_path in file_paths]
        vectors = [
            MetricsVector(layer=self.LAYER_NAME, file_path=file_path)
            for file_path in file_paths
        ]

        if not normalized_paths:
            logger.warning("[ARCHITECTURE] no files to analyze")
            return vectors

        try:
            context = self._build_context(normalized_paths)
        except Exception as exc:
            logger.warning("[ARCHITECTURE] failed to build dependency graph: %s", exc)
            for vector in vectors:
                vector.metrics = self._safe_default_metrics()
                vector.errors.append(f"architecture graph failed: {exc}")
            return vectors

        vector_by_path = dict(zip(normalized_paths, vectors))
        for path in normalized_paths:
            vector = vector_by_path[path]
            try:
                node = context.node_by_path[path]
                for metric_name, handler in self.metric_handlers.items():
                    try:
                        vector.metrics[metric_name] = handler(context, node)
                    except Exception as exc:
                        vector.errors.append(f"{metric_name} failed: {exc}")
                        vector.metrics[metric_name] = None

                vector.metadata = {
                    "repo_root": str(context.repo_root),
                    "node": node,
                    "sccs": context.sccs,
                }
            except Exception as exc:
                logger.warning("[ARCHITECTURE] failed for %s: %s", path, exc)
                vector.metrics = self._safe_default_metrics()
                vector.errors.append(f"architecture metrics failed: {exc}")

        logger.info("[ARCHITECTURE] completed architecture analysis on %d files", len(file_paths))
        logger.info("[ARCHITECTURE] graph has %d nodes and %d edges", context.graph.number_of_nodes(), context.graph.number_of_edges())
        logger.info("[ARCHITECTURE] graph has %d strongly connected components", len(context.sccs))
        logger.info("[ARCHITECTURE] graph betweenness centrality computed for %d nodes", len(context.betweenness))
        logger.info("[ARCHITECTURE] graph circular dependency sizes computed for %d nodes", len(context.scc_size_by_node))
        return vectors

    # -- Graph construction ------------------------------------------------

    def _build_context(self, file_paths: list[Path]) -> ArchitectureGraphContext:
        if nx is None:
            raise RuntimeError("networkx is not installed")

        repo_root = self._discover_repo_root(file_paths)
        node_by_path = {path: self._node_path(repo_root, path) for path in file_paths}
        module_to_node = self._module_to_node(repo_root, node_by_path)
        graph = nx.DiGraph()
        graph.add_nodes_from(node_by_path.values())

        for path, node in node_by_path.items():
            dependencies = self._dependencies_for_file(path, node, module_to_node)
            for dependency in dependencies:
                if dependency != node:
                    graph.add_edge(node, dependency)

        betweenness = nx.betweenness_centrality(graph, normalized=True)
        sccs, scc_size_by_node = self._scc_metadata(graph)
        return ArchitectureGraphContext(
            repo_root=repo_root,
            file_paths=file_paths,
            node_by_path=node_by_path,
            module_to_node=module_to_node,
            graph=graph,
            betweenness=betweenness,
            sccs=sccs,
            scc_size_by_node=scc_size_by_node,
        )

    def _dependencies_for_file(
        self,
        path: Path,
        current_node: str,
        module_to_node: dict[str, str],
    ) -> set[str]:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("[ARCHITECTURE] failed to parse %s: %s", path, exc)
            return set()

        current_module = self._module_for_node(current_node)
        dependencies: set[str] = set()
        for statement in ast.walk(tree):
            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    dependency = self._resolve_absolute_import(alias.name, module_to_node)
                    if dependency is not None:
                        dependencies.add(dependency)
            elif isinstance(statement, ast.ImportFrom):
                for module_name in self._candidate_import_from_modules(statement, current_module):
                    dependency = self._resolve_absolute_import(module_name, module_to_node)
                    if dependency is not None:
                        dependencies.add(dependency)
                        break

        return dependencies

    def _candidate_import_from_modules(self, statement: ast.ImportFrom, current_module: str) -> list[str]:
        base_module = self._resolve_import_from_base(statement, current_module)
        candidates: list[str] = []

        for alias in statement.names:
            if alias.name == "*":
                candidates.append(base_module)
            elif base_module:
                candidates.append(f"{base_module}.{alias.name}")
                candidates.append(base_module)
            else:
                candidates.append(alias.name)

        return candidates

    def _resolve_import_from_base(self, statement: ast.ImportFrom, current_module: str) -> str:
        if statement.level == 0:
            return statement.module or ""

        package_parts = current_module.split(".")
        if not current_module.endswith(".__init__") and package_parts:
            package_parts = package_parts[:-1]

        keep_count = max(0, len(package_parts) - statement.level + 1)
        relative_base = ".".join(package_parts[:keep_count])
        if statement.module:
            return f"{relative_base}.{statement.module}" if relative_base else statement.module
        return relative_base

    # converts import (e.g., "from app.module.src") to node path (e.g., "/app/module/src.py")
    def _resolve_absolute_import(self, module_name: str, module_to_node: dict[str, str]) -> str | None:
        parts = [part for part in module_name.split(".") if part]
        while parts:
            candidate = ".".join(parts)
            if candidate in module_to_node:
                return module_to_node[candidate]
            parts.pop()
        return None

    # -- Metrics -----------------------------------------------------------

    def fan_in(self, context: ArchitectureGraphContext, node: str) -> int:
        logger.debug("[ARCHITECTURE] computing fan-in")
        return int(context.graph.in_degree(node))

    def fan_out(self, context: ArchitectureGraphContext, node: str) -> int:
        logger.debug("[ARCHITECTURE] computing fan-out")
        return int(context.graph.out_degree(node))

    def transitive_dependents_count(self, context: ArchitectureGraphContext, node: str) -> int:
        logger.debug("[ARCHITECTURE] computing transitive dependents")
        reverse_graph = context.graph.reverse(copy=False)
        return len(nx.descendants(reverse_graph, node))

    def betweenness_centrality(self, context: ArchitectureGraphContext, node: str) -> float:
        logger.debug("[ARCHITECTURE] computing betweenness centrality")
        return round(float(context.betweenness.get(node, 0.0)), 6)

    def circular_dependency_size(self, context: ArchitectureGraphContext, node: str) -> int:
        logger.debug("[ARCHITECTURE] computing circular dependency size")
        return context.scc_size_by_node.get(node, 0)

    def instability_index(self, context: ArchitectureGraphContext, node: str) -> float:
        logger.debug("[ARCHITECTURE] computing instability index")
        fan_in = context.graph.in_degree(node)
        fan_out = context.graph.out_degree(node)
        dependency_total = fan_in + fan_out
        return round(fan_out / dependency_total, 3) if dependency_total else 0.0

    def _scc_metadata(self, graph: Any) -> tuple[list[dict[str, list[str] | list[list[str]]]], dict[str, int]]:
        sccs: list[dict[str, list[str] | list[list[str]]]] = []
        scc_size_by_node: dict[str, int] = {}

        for component in nx.strongly_connected_components(graph):
            if len(component) <= 1:
                continue

            nodes = sorted(component)
            node_set = set(nodes)
            edges = sorted(
                [source, target]
                for source, target in graph.edges()
                if source in node_set and target in node_set
            )
            sccs.append({"nodes": nodes, "edges": edges})
            for node in nodes:
                scc_size_by_node[node] = len(nodes)

        return sccs, scc_size_by_node

    # -- Path and module helpers ------------------------------------------

    def _discover_repo_root(self, file_paths: list[Path]) -> Path:
        for path in file_paths:
            for directory in (path.parent, *path.parents):
                if (directory / ".git").exists():
                    return directory.resolve()

        common_path = Path(os.path.commonpath([str(path.parent) for path in file_paths]))
        return common_path.resolve()

    def _node_path(self, repo_root: Path, file_path: Path) -> str:
        try:
            relative_path = file_path.relative_to(repo_root)
        except ValueError:
            relative_path = file_path
        return f"/{relative_path.as_posix().lstrip('/')}"

    def _module_to_node(self, repo_root: Path, node_by_path: dict[Path, str]) -> dict[str, str]:
        module_to_node: dict[str, str] = {}
        for path, node in node_by_path.items():
            module_name = self._module_name(repo_root, path)
            if module_name:
                module_to_node[module_name] = node
        return module_to_node

    def _module_name(self, repo_root: Path, file_path: Path) -> str:
        try:
            relative_path = file_path.relative_to(repo_root)
        except ValueError:
            relative_path = file_path

        parts = list(relative_path.with_suffix("").parts)
        if "src" in parts:
            parts = parts[parts.index("src") + 1 :]
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]

        return ".".join(part for part in parts if part)

    def _module_for_node(self, node: str) -> str:
        parts = Path(node.lstrip("/")).with_suffix("").parts
        if "src" in parts:
            parts = parts[parts.index("src") + 1 :]
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)

    def _safe_default_metrics(self) -> dict[str, int | float]:
        return {
            "fan_in": 0,
            "fan_out": 0,
            "transitive_dependents_count": 0,
            "betweenness_centrality": 0.0,
            "circular_dependency_size": 0,
            "instability_index": 0.0,
        }
