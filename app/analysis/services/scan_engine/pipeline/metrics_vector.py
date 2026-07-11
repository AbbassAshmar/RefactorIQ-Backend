from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterator
from uuid import UUID


MetricValue = int | float | str | bool | None


def validate_relative_path(value: str) -> str:
    """Return a canonical repository-relative POSIX path.

    This deliberately validates only an already-relative identity.  Callers
    that know a repository root are responsible for converting an absolute
    filesystem path at that boundary.
    """
    if not isinstance(value, str):
        raise TypeError("relative_path must be a string")

    normalized = value.replace("\\", "/")
    if normalized.startswith("/"):
        raise ValueError("relative_path must not start with '/'")
    if PureWindowsPath(normalized).drive:
        raise ValueError("relative_path must be repository-relative")

    raw_parts = normalized.split("/")
    if any(part in {".", ".."} for part in raw_parts):
        raise ValueError("relative_path cannot contain traversal segments")

    path = PurePosixPath(normalized)
    if path.is_absolute():
        raise ValueError("relative_path must be repository-relative")

    canonical = path.as_posix()
    if not canonical or canonical == ".":
        raise ValueError("relative_path cannot be empty")

    return canonical


@dataclass(slots=True)
class MetricsVector:
    layer: str
    # The live source location used by analysis code.  It is not persisted.
    absolute_path: Path | None = None
    # The stable, repository-relative identity used between all layers.
    relative_path: str | None = None
    scan_id: UUID | None = None

    metrics: dict[str, MetricValue] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def __post_init__(self) -> None:
        paths_are_missing = self.absolute_path is None and self.relative_path is None
        paths_are_present = self.absolute_path is not None and self.relative_path is not None
        if not paths_are_missing and not paths_are_present:
            raise ValueError(
                "absolute_path and relative_path must either both be set or both be None"
            )

        if self.absolute_path is not None:
            self.absolute_path = Path(self.absolute_path).resolve()
        if self.relative_path is not None:
            self.relative_path = validate_relative_path(self.relative_path)

    def for_layer(self, layer: str) -> "MetricsVector":
        """Create an empty result vector for another layer for the same file."""
        return MetricsVector(
            layer=layer,
            absolute_path=self.absolute_path,
            relative_path=self.relative_path,
            scan_id=self.scan_id,
        )


@dataclass(slots=True)
class LayerResult:
    vectors: list[MetricsVector] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_vector(
        cls,
        vector: MetricsVector,
        metadata: dict[str, Any] | None = None,
    ) -> "LayerResult":
        return cls(vectors=[vector], metadata=metadata if metadata is not None else vector.metadata)

    def __iter__(self) -> Iterator[MetricsVector]:
        return iter(self.vectors)

    def __len__(self) -> int:
        return len(self.vectors)

    def __getitem__(self, index: int) -> MetricsVector:
        return self.vectors[index]

    def __getattr__(self, name: str) -> Any:
        if len(self.vectors) == 1:
            return getattr(self.vectors[0], name)
        raise AttributeError(name)
