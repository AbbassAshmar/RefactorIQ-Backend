from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


MetricValue = int | float | str | bool | None


@dataclass(slots=True)
class MetricsVector:
    layer: str
    file_path: str | None
    scan_id: UUID | None = None

    metrics: dict[str, MetricValue] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_errors(self) -> bool:
        return len(self.errors) > 0
