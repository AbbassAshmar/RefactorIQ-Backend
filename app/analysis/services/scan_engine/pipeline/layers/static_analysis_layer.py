import ast
import logging
import tokenize
from collections.abc import Callable
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

from app.analysis.services.scan_engine.pipeline.metrics_vector import MetricsVector

try:
    from radon.complexity import cc_visit
    from radon.raw import analyze as analyze_raw_metrics
except ImportError:
    cc_visit = None
    analyze_raw_metrics = None

try:
    from complexipy import code_complexity
except ImportError:
    code_complexity = None

try:
    from coverage import Coverage
    from coverage.exceptions import CoverageException
except ImportError:
    Coverage = None
    CoverageException = Exception

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class StaticAnalysisContext:
    file_path: str
    source: str
    tree: ast.AST
    raw_metrics: Any = None
    cyclomatic_blocks: list[Any] | None = None
    cognitive_result: Any = None


MetricHandler = Callable[[StaticAnalysisContext], int | float | str | bool | None]


class StaticAnalysisLayer:
    """Layer 1 - local static analysis, per file."""

    LAYER_NAME = "static_analysis"
    LONG_CONDITION_OPERAND_THRESHOLD = 3
    FIXME_TAGS = ("FIXME", "TODO", "XXX", "HACK", "BUG")

    def __init__(self) -> None:
        self.metric_handlers: dict[str, MetricHandler] = {
            "average_cyclomatic_complexity": self.average_cyclomatic_complexity,
            "max_cyclomatic_complexity": self.max_cyclomatic_complexity,
            "average_cognitive_complexity": self.average_cognitive_complexity,
            "max_cognitive_complexity": self.max_cognitive_complexity,
            "testing_coverage": self.testing_coverage,
            "lines_of_code": self.lines_of_code,
            "logical_lines_of_code": self.logical_lines_of_code,
            "count_of_comments": self.count_of_comments,
            "long_conditions_count": self.long_conditions_count,
            "max_if_else_chain_length": self.max_if_else_chain_length,
            "average_parameters_count": self.average_parameters_count,
            "count_of_fixme_comments": self.count_of_fixme_comments,
            "count_of_empty_except_blocks": self.count_of_empty_except_blocks,
        }

    def run(self, file_path: str) -> MetricsVector:
        vector = MetricsVector(layer=self.LAYER_NAME, file_path=file_path)

        try:
            source = self._read_file(file_path)
            tree = ast.parse(source)
        except Exception as exc:
            vector.errors.append(f"Failed to parse file: {exc}")
            return vector

        context = StaticAnalysisContext(file_path=file_path, source=source, tree=tree)

        for metric_name, handler in self.metric_handlers.items():
            try:
                vector.metrics[metric_name] = handler(context)
            except Exception as exc:
                # One metric failing must never kill the whole layer.
                vector.errors.append(f"{metric_name} failed: {exc}")
                vector.metrics[metric_name] = None

        logger.info(f"[STATIC] Completed static analysis for {file_path} with metrics: {vector.metrics}")   
        return vector

    # -- Radon metrics -----------------------------------------------------

    def lines_of_code(self, context: StaticAnalysisContext) -> int:
        logger.debug("[STATIC] computing LOC")
        return int(self._raw_metrics(context).loc)

    def logical_lines_of_code(self, context: StaticAnalysisContext) -> int:
        logger.debug("[STATIC] computing LLOC")
        return int(self._raw_metrics(context).lloc)

    def count_of_comments(self, context: StaticAnalysisContext) -> int:
        logger.debug("[STATIC] computing comment count")
        return int(self._raw_metrics(context).comments)

    def average_cyclomatic_complexity(self, context: StaticAnalysisContext) -> float:
        logger.debug("[STATIC] computing average cyclomatic complexity")
        values = self._cyclomatic_values(context)
        return self._average(values)

    def max_cyclomatic_complexity(self, context: StaticAnalysisContext) -> float:
        logger.debug("[STATIC] computing max cyclomatic complexity")
        values = self._cyclomatic_values(context)
        return float(max(values, default=0))

    # -- Complexipy metrics -----------------------------------------------

    def average_cognitive_complexity(self, context: StaticAnalysisContext) -> float:
        logger.debug("[STATIC] computing average cognitive complexity")
        values = self._cognitive_values(context)
        return self._average(values)

    def max_cognitive_complexity(self, context: StaticAnalysisContext) -> float:
        logger.debug("[STATIC] computing max cognitive complexity")
        values = self._cognitive_values(context)
        return float(max(values, default=0))

    # -- Custom AST / token metrics ---------------------------------------

    def testing_coverage(self, context: StaticAnalysisContext) -> float:
        logger.debug("[STATIC] computing testing coverage")
        if Coverage is None:
            raise RuntimeError("coverage.py is not installed")

        data_file = self._find_coverage_data_file(context.file_path)
        if data_file is None:
            return 0.0

        try:
            coverage = Coverage(data_file=str(data_file))
            coverage.load()
            _, statements, _, missing, _ = coverage.analysis2(str(Path(context.file_path).resolve()))
        except CoverageException:
            return 0.0

        if not statements:
            return 100.0

        covered_lines = len(statements) - len(missing)
        return round((covered_lines / len(statements)) * 100, 3)

    def long_conditions_count(self, context: StaticAnalysisContext) -> int:
        logger.debug("[STATIC] computing long condition count")
        count = 0
        for node in ast.walk(context.tree):
            test = getattr(node, "test", None) # Conditional expressions (if, while, etc.) have a 'test' attribute
            if test is not None and self._condition_operand_count(test) >= self.LONG_CONDITION_OPERAND_THRESHOLD:
                count += 1
        return count

    def max_if_else_chain_length(self, context: StaticAnalysisContext) -> int:
        logger.debug("[STATIC] computing max if/else chain length")
        return max(
            (self._if_else_chain_length(node) for node in ast.walk(context.tree) if isinstance(node, ast.If)),
            default=0,
        )

    def average_parameters_count(self, context: StaticAnalysisContext) -> float:
        logger.debug("[STATIC] computing average parameter count")
        counts = [
            self._parameter_count(node)
            for node in ast.walk(context.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        return self._average(counts)

    def count_of_fixme_comments(self, context: StaticAnalysisContext) -> int:
        logger.debug("[STATIC] computing FIXME/TODO comment count")
        count = 0
        reader = StringIO(context.source).readline
        for token in tokenize.generate_tokens(reader):
            if token.type == tokenize.COMMENT and self._is_fixme_comment(token.string):
                count += 1
        return count

    def count_of_empty_except_blocks(self, context: StaticAnalysisContext) -> int:
        logger.debug("[STATIC] computing empty except block count")
        return sum(
            1
            for node in ast.walk(context.tree)
            if isinstance(node, ast.ExceptHandler) and self._is_empty_block(node.body)
        )

    # -- Helpers -----------------------------------------------------------

    def _raw_metrics(self, context: StaticAnalysisContext) -> Any:
        if analyze_raw_metrics is None:
            raise RuntimeError("radon is not installed")
        if context.raw_metrics is None:
            context.raw_metrics = analyze_raw_metrics(context.source)
        return context.raw_metrics

    def _cyclomatic_values(self, context: StaticAnalysisContext) -> list[int]:
        if cc_visit is None:
            raise RuntimeError("radon is not installed")
        if context.cyclomatic_blocks is None:
            context.cyclomatic_blocks = cc_visit(context.source)

        return [
            int(block.complexity)
            for block in context.cyclomatic_blocks
            if hasattr(block, "complexity") and not hasattr(block, "methods")
        ]

    def _cognitive_values(self, context: StaticAnalysisContext) -> list[int]:
        if code_complexity is None:
            raise RuntimeError("complexipy is not installed")
        if context.cognitive_result is None:
            context.cognitive_result = code_complexity(context.source, check_script=True)

        functions = getattr(context.cognitive_result, "functions", []) or []
        values = [int(function.complexity) for function in functions]
        if values:
            return values

        file_complexity = getattr(context.cognitive_result, "complexity", 0)
        return [int(file_complexity)] if file_complexity else []

    def _condition_operand_count(self, node: ast.AST) -> int:
        if not isinstance(node, ast.BoolOp):
            return 1

        count = 0
        for value in node.values:
            count += self._condition_operand_count(value)
        return count

    def _if_else_chain_length(self, node: ast.If) -> int:
        length = 1
        current = node

        while len(current.orelse) == 1 and isinstance(current.orelse[0], ast.If):
            length += 1
            current = current.orelse[0]

        if current.orelse:
            length += 1

        return length

    def _parameter_count(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
        args = node.args
        count = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
        if args.vararg is not None:
            count += 1
        if args.kwarg is not None:
            count += 1
        return count

    def _is_fixme_comment(self, comment: str) -> bool:
        normalized = comment.upper()
        return any(tag in normalized for tag in self.FIXME_TAGS)

    def _is_empty_block(self, body: list[ast.stmt]) -> bool:
        return all(self._is_noop_statement(statement) for statement in body)

    def _is_noop_statement(self, statement: ast.stmt) -> bool:
        if isinstance(statement, ast.Pass):
            return True
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant):
            return statement.value.value is Ellipsis or isinstance(statement.value.value, str)
        return False

    def _average(self, values: list[int]) -> float:
        if not values:
            return 0.0
        return float(sum(values) / len(values))

    def _find_coverage_data_file(self, file_path: str) -> Path | None:
        path = Path(file_path).resolve()
        search_start = path.parent if path.is_file() else path

        for directory in (search_start, *search_start.parents):
            data_file = directory / ".coverage"
            if data_file.is_file():
                return data_file

        return None

    def _read_file(self, path: str) -> str:
        with open(path, "r", encoding="utf-8") as file:
            return file.read()
