"""DTOs for cross-module administrative analytics."""

from datetime import datetime

from pydantic import BaseModel


class KpiPeriodWindow(BaseModel):
    start: datetime
    end: datetime


class KpiPeriod(BaseModel):
    days: int
    current: KpiPeriodWindow
    previous: KpiPeriodWindow


class KpiMetric(BaseModel):
    total: int
    current_period_count: int
    previous_period_count: int
    delta: int
    delta_percent: float | None


class AdminKpisResponse(BaseModel):
    period: KpiPeriod
    kpis: dict[str, KpiMetric]
