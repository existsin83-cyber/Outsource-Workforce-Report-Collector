"""Validate, order, and snapshot a final external-work report."""

from __future__ import annotations

import hashlib
import json
from datetime import date

from outsource_mail_collector.application.models import (
    FinalizationBlocker,
    FinalReportPreview,
    FinalReportSnapshot,
    TrackingDashboardSummary,
    final_report_snapshot_from_stored,
)
from outsource_mail_collector.application.tracking_dashboard_service import (
    TrackingDashboardService,
)
from outsource_mail_collector.infrastructure.db.repository import (
    FinalReportRowInput,
    SQLiteRepository,
)


class FinalizationError(ValueError):
    """Raised when a report range still has confirmation blockers."""

    def __init__(self, blockers: tuple[FinalizationBlocker, ...]) -> None:
        super().__init__("최종 확정 전에 문제 행을 확인해 주세요.")
        self.blockers = blockers


class FinalReportService:
    """Create immutable final-report snapshots after fresh validation."""

    def __init__(self, repository: SQLiteRepository) -> None:
        self._repository = repository
        self._dashboard = TrackingDashboardService(repository)

    def preview(self) -> FinalReportPreview:
        rows = tuple(
            sorted(
                self._dashboard.summaries(include_completed=False),
                key=_final_report_sort_key,
            )
        )
        blockers = tuple(
            blocker
            for row in rows
            for blocker in row.blockers
        )
        dates = [row.latest_work_date for row in rows if row.latest_work_date]
        return FinalReportPreview(
            date_from=min(dates, default=None),
            date_to=max(dates, default=None),
            rows=rows,
            blockers=blockers,
        )

    def confirm(self) -> FinalReportSnapshot:
        preview = self.preview()
        if not preview.rows:
            raise ValueError("활성 대시보드 행이 없어 최종 표를 확정할 수 없습니다.")
        if preview.blockers:
            raise FinalizationError(preview.blockers)
        if preview.date_from is None or preview.date_to is None:
            raise ValueError("작업일이 없는 행은 최종 표를 확정할 수 없습니다.")
        snapshot_hash = _snapshot_hash(preview.rows)
        snapshot_rows = [_snapshot_input(row) for row in preview.rows]
        stored = self._repository.create_final_report_snapshot(
            date_from=preview.date_from,
            date_to=preview.date_to,
            rows=snapshot_rows,
            snapshot_hash=snapshot_hash,
        )
        return final_report_snapshot_from_stored(stored)

    def mark_copied(self, report_id: int) -> FinalReportSnapshot:
        return final_report_snapshot_from_stored(
            self._repository.mark_final_report_copied(report_id)
        )

def _final_report_sort_key(
    row: TrackingDashboardSummary,
) -> tuple[tuple[int, int], int, str]:
    work_date = row.latest_work_date
    date_rank = (1, 0) if work_date is None else (0, -work_date.toordinal())
    return (date_rank, row.vendor_sort_order, row.normalized_tracking_no)


def _snapshot_input(row: TrackingDashboardSummary) -> FinalReportRowInput:
    required = (
        row.vendor_name,
        row.latest_actual_headcount,
        row.latest_night_headcount,
        row.latest_confirmed_daily_man_day,
        row.latest_confirmed_cumulative_man_day,
    )
    if any(value is None for value in required):
        raise ValueError("최종 보고서 행의 필수 확정값이 누락되었습니다.")
    return FinalReportRowInput(
        source_row_id=row.latest_row_id,
        source_row_ids=row.source_row_ids,
        work_date=row.latest_work_date,
        vendor_name=row.vendor_name,  # type: ignore[arg-type]
        tracking_no=row.tracking_no,
        equipment_name=row.equipment_name,
        business_team=row.business_team,
        actual_headcount=row.latest_actual_headcount,  # type: ignore[arg-type]
        night_headcount=row.latest_night_headcount,  # type: ignore[arg-type]
        man_day_basis=row.latest_man_day_basis,
        confirmed_daily_man_day=row.latest_confirmed_daily_man_day,  # type: ignore[arg-type]
        confirmed_cumulative_man_day=row.latest_confirmed_cumulative_man_day,  # type: ignore[arg-type]
    )


def _snapshot_hash(rows: tuple[TrackingDashboardSummary, ...]) -> str:
    payload = [
        {
            "source_row_ids": sorted(row.source_row_ids),
            "work_date": (
                row.latest_work_date.isoformat()
                if row.latest_work_date
                else None
            ),
            "vendor_name": row.vendor_name,
            "tracking_no": row.tracking_no,
            "equipment_name": row.equipment_name,
            "business_team": row.business_team,
            "actual_headcount": row.latest_actual_headcount,
            "night_headcount": row.latest_night_headcount,
            "man_day_basis": row.latest_man_day_basis,
            "confirmed_daily_man_day": str(row.latest_confirmed_daily_man_day),
            "reported_cumulative_man_day": str(
                row.latest_reported_cumulative_man_day
            ),
            "calculated_cumulative_man_day": str(
                row.latest_calculated_cumulative_man_day
            ),
            "confirmed_cumulative_man_day": str(
                row.latest_confirmed_cumulative_man_day
            ),
        }
        for row in rows
    ]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
