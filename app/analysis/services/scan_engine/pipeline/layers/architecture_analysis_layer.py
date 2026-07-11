import ast
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.analysis.services.scan_engine.pipeline.metrics_vector import LayerResult, MetricsVector

try:
    import networkx as nx
except ImportError:
    nx = None

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ArchitectureGraphContext:
    vectors: list[MetricsVector]
    module_to_relative_path: dict[str, str]
    graph: Any
    betweenness: dict[str, float]
    sccs: list[dict[str, list[str] | list[list[str]]]]
    scc_size_by_path: dict[str, int]


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

    def run(self, vectors: list[MetricsVector]) -> LayerResult:
        logger.info("[ARCHITECTURE] running architecture analysis on %d files", len(vectors))
        self._validate_vectors(vectors)

        if not vectors:
            logger.warning("[ARCHITECTURE] no files to analyze")
            return LayerResult(vectors=vectors)

        try:
            context = self._build_context(vectors)
        except Exception as exc:
            logger.warning("[ARCHITECTURE] failed to build dependency graph: %s", exc)
            for vector in vectors:
                vector.metrics = self._safe_default_metrics()
                vector.errors.append(f"architecture graph failed: {exc}")
            return LayerResult(vectors=vectors)

        for vector in vectors:
            try:
                relative_path = vector.relative_path
                assert relative_path is not None
                for metric_name, handler in self.metric_handlers.items():
                    try:
                        vector.metrics[metric_name] = handler(context, relative_path)
                    except Exception as exc:
                        vector.errors.append(f"{metric_name} failed: {exc}")
                        vector.metrics[metric_name] = None

                vector.metadata = {
                    "sccs": context.sccs,
                }
            except Exception as exc:
                logger.warning("[ARCHITECTURE] failed for %s: %s", vector.relative_path, exc)
                vector.metrics = self._safe_default_metrics()
                vector.errors.append(f"architecture metrics failed: {exc}")

        logger.info("[ARCHITECTURE] completed architecture analysis on %d files", len(vectors))
        logger.info("[ARCHITECTURE] graph has %d nodes and %d edges", context.graph.number_of_nodes(), context.graph.number_of_edges())
        logger.info("[ARCHITECTURE] graph has %d strongly connected components", len(context.sccs))
        logger.info("[ARCHITECTURE] graph betweenness centrality computed for %d nodes", len(context.betweenness))
        logger.info("[ARCHITECTURE] graph circular dependency sizes computed for %d nodes", len(context.scc_size_by_path))
        return LayerResult(
            vectors=vectors,
            metadata=self._global_metadata_for_context(context),
        )

    # -- Graph construction ------------------------------------------------

    def _build_context(self, vectors: list[MetricsVector]) -> ArchitectureGraphContext:
        if nx is None:
            raise RuntimeError("networkx is not installed")

        module_to_relative_path = self._module_to_relative_path(vectors)
        graph = nx.DiGraph()
        graph.add_nodes_from(
            vector.relative_path for vector in vectors if vector.relative_path is not None
        )

        for vector in vectors:
            assert vector.absolute_path is not None and vector.relative_path is not None
            dependencies = self._dependencies_for_file(
                vector.absolute_path,
                vector.relative_path,
                module_to_relative_path,
            )
            for dependency in dependencies:
                if dependency != vector.relative_path:
                    graph.add_edge(vector.relative_path, dependency)

        betweenness = nx.betweenness_centrality(graph, normalized=True)
        sccs, scc_size_by_path = self._scc_metadata(graph)
        return ArchitectureGraphContext(
            vectors=vectors,
            module_to_relative_path=module_to_relative_path,
            graph=graph,
            betweenness=betweenness,
            sccs=sccs,
            scc_size_by_path=scc_size_by_path,
        )

    def _dependencies_for_file(
        self,
        absolute_path: Path,
        current_relative_path: str,
        module_to_relative_path: dict[str, str],
    ) -> set[str]:
        try:
            tree = ast.parse(absolute_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("[ARCHITECTURE] failed to parse %s: %s", absolute_path, exc)
            return set()

        current_module = self._module_for_relative_path(current_relative_path)
        dependencies: set[str] = set()
        for statement in ast.walk(tree):
            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    dependency = self._resolve_absolute_import(alias.name, module_to_relative_path)
                    if dependency is not None:
                        dependencies.add(dependency)
            elif isinstance(statement, ast.ImportFrom):
                for module_name in self._candidate_import_from_modules(statement, current_module):
                    dependency = self._resolve_absolute_import(module_name, module_to_relative_path)
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

    def _resolve_absolute_import(
        self,
        module_name: str,
        module_to_relative_path: dict[str, str],
    ) -> str | None:
        parts = [part for part in module_name.split(".") if part]
        while parts:
            candidate = ".".join(parts)
            if candidate in module_to_relative_path:
                return module_to_relative_path[candidate]
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
        return context.scc_size_by_path.get(node, 0)

    def instability_index(self, context: ArchitectureGraphContext, node: str) -> float:
        logger.debug("[ARCHITECTURE] computing instability index")
        fan_in = context.graph.in_degree(node)
        fan_out = context.graph.out_degree(node)
        dependency_total = fan_in + fan_out
        return round(fan_out / dependency_total, 3) if dependency_total else 0.0

    def _scc_metadata(self, graph: Any) -> tuple[list[dict[str, list[str] | list[list[str]]]], dict[str, int]]:
        sccs: list[dict[str, list[str] | list[list[str]]]] = []
        scc_size_by_path: dict[str, int] = {}

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
                scc_size_by_path[node] = len(nodes)

        return sccs, scc_size_by_path

    def _global_metadata_for_context(self, context: ArchitectureGraphContext) -> dict[str, object]:
        dependency_edges = sorted(
            [source, target]
            for source, target in context.graph.edges()
        )
        return {
            "dependency_edges": dependency_edges,
            "circular_dependency_groups": [
                {
                    "nodes": group["nodes"],
                    "size": len(group["nodes"]),
                }
                for group in context.sccs
            ],
            "sccs": context.sccs,
        }

    # -- Path and module helpers ------------------------------------------

    def _validate_vectors(self, vectors: list[MetricsVector]) -> None:
        if any(vector.absolute_path is None or vector.relative_path is None for vector in vectors):
            raise ValueError("Architecture analysis requires both absolute_path and relative_path")

    def _module_to_relative_path(self, vectors: list[MetricsVector]) -> dict[str, str]:
        module_to_relative_path: dict[str, str] = {}
        for vector in vectors:
            assert vector.relative_path is not None
            module_name = self._module_name(vector.relative_path)
            if module_name:
                module_to_relative_path[module_name] = vector.relative_path
        return module_to_relative_path

    def _module_name(self, relative_path: str) -> str:
        parts = list(Path(relative_path).with_suffix("").parts)
        if "src" in parts:
            parts = parts[parts.index("src") + 1 :]
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]

        return ".".join(part for part in parts if part)

    def _module_for_relative_path(self, relative_path: str) -> str:
        parts = Path(relative_path).with_suffix("").parts
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
