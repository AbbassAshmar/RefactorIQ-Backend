"""Cross-module KPI composition for the administrative dashboard."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.analytics.analytics_dtos import (
    AdminKpisResponse,
    KpiMetric,
    KpiPeriod,
    KpiPeriodWindow,
)
from app.core.enums import ScanStatus
from app.core.exceptions.domain_exceptions import PersistenceError
from app.core.exceptions.repository_exceptions import DatabaseOperationException
from app.projects.projects_repository import ProjectRepository
from app.scans.scans_repository import ScanRepository
from app.users.repositories.user_repository import UserRepository


KPI_PERIOD_DAYS = 30


class AnalyticsService:
    def __init__(
        self,
        user_repository: UserRepository,
        scan_repository: ScanRepository,
        project_repository: ProjectRepository,
    ) -> None:
        self._users = user_repository
        self._scans = scan_repository
        self._projects = project_repository

    @staticmethod
    def _metric(total: int, current: int, previous: int) -> KpiMetric:
        delta = current - previous
        delta_percent = (
            round((delta / previous) * 100, 2) if previous != 0 else None
        )
        return KpiMetric(
            total=total,
            current_period_count=current,
            previous_period_count=previous,
            delta=delta,
            delta_percent=delta_percent,
        )

    def get_kpis(self, *, now: datetime | None = None) -> AdminKpisResponse:
        period_end = now or datetime.now(timezone.utc)
        if period_end.tzinfo is None:
            period_end = period_end.replace(tzinfo=timezone.utc)
        else:
            period_end = period_end.astimezone(timezone.utc)

        current_start = period_end - timedelta(days=KPI_PERIOD_DAYS)
        previous_start = current_start - timedelta(days=KPI_PERIOD_DAYS)

        try:
            users = self._metric(
                self._users.count_users(),
                self._users.count_users(
                    created_from=current_start,
                    created_before=period_end,
                ),
                self._users.count_users(
                    created_from=previous_start,
                    created_before=current_start,
                ),
            )
            scans = self._metric(
                self._scans.count_scans(),
                self._scans.count_scans(
                    created_from=current_start,
                    created_before=period_end,
                ),
                self._scans.count_scans(
                    created_from=previous_start,
                    created_before=current_start,
                ),
            )
            projects = self._metric(
                self._projects.count_projects(),
                self._projects.count_projects(
                    created_from=current_start,
                    created_before=period_end,
                ),
                self._projects.count_projects(
                    created_from=previous_start,
                    created_before=current_start,
                ),
            )
            running_scans = self._metric(
                self._scans.count_scans(status=ScanStatus.RUNNING),
                self._scans.count_scans(
                    status=ScanStatus.RUNNING,
                    created_from=current_start,
                    created_before=period_end,
                ),
                self._scans.count_scans(
                    status=ScanStatus.RUNNING,
                    created_from=previous_start,
                    created_before=current_start,
                ),
            )
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to load administrative KPIs") from exc

        return AdminKpisResponse(
            period=KpiPeriod(
                days=KPI_PERIOD_DAYS,
                current=KpiPeriodWindow(start=current_start, end=period_end),
                previous=KpiPeriodWindow(start=previous_start, end=current_start),
            ),
            kpis={
                "users": users,
                "scans": scans,
                "projects": projects,
                "running_scans": running_scans,
            },
        )
