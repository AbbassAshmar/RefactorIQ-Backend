from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


MetricValue = int | float | str | bool | None


@dataclass(slots=True)
class MetricsVector:
    scan_id: UUID
    layer: str
    file_path: str | None

    metrics: dict[str, MetricValue] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_errors(self) -> bool:
        return len(self.errors) > 0