"""Validate, order, and snapshot a final external-work report."""

from __future__ import annotations

import hashlib
import json
from datetime import date

from outsource_mail_collector.application.models import (
    FinalizationBlocker,
    FinalReportPreview,
    FinalReportSnapshot,
    TrackingDailyAggregate,
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
        rows = self._dashboard.active_daily_aggregates()
        blockers = tuple(
            blocker
            for row in rows
            for blocker in row.blockers
        )
        return FinalReportPreview(
            date_from=min(
                (row.work_date for row in rows if row.work_date is not None),
                default=None,
            ),
            date_to=max(
                (row.work_date for row in rows if row.work_date is not None),
                default=None,
            ),
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

def _snapshot_input(row: TrackingDailyAggregate) -> FinalReportRowInput:
    required = (
        row.vendor_name,
        row.actual_headcount,
        row.night_headcount,
        row.confirmed_daily_man_day,
        row.confirmed_cumulative_man_day,
    )
    if any(value is None for value in required):
        raise ValueError("최종 보고서 행의 필수 확정값이 누락되었습니다.")
    return FinalReportRowInput(
        source_row_id=row.row_id,
        source_row_ids=row.source_row_ids,
        work_date=row.work_date,
        vendor_name=row.vendor_name,  # type: ignore[arg-type]
        tracking_no=row.tracking_no,
        equipment_name=row.equipment_name,
        business_team=row.business_team,
        actual_headcount=row.actual_headcount,  # type: ignore[arg-type]
        night_headcount=row.night_headcount,  # type: ignore[arg-type]
        man_day_basis=row.man_day_basis,
        confirmed_daily_man_day=row.confirmed_daily_man_day,  # type: ignore[arg-type]
        confirmed_cumulative_man_day=row.confirmed_cumulative_man_day,  # type: ignore[arg-type]
    )


def _snapshot_hash(rows: tuple[TrackingDailyAggregate, ...]) -> str:
    payload = [
        {
            "source_row_ids": sorted(row.source_row_ids),
            "work_date": row.work_date.isoformat(),
            "vendor_name": row.vendor_name,
            "tracking_no": row.tracking_no,
            "equipment_name": row.equipment_name,
            "business_team": row.business_team,
            "actual_headcount": row.actual_headcount,
            "night_headcount": row.night_headcount,
            "man_day_basis": row.man_day_basis,
            "confirmed_daily_man_day": str(row.confirmed_daily_man_day),
            "reported_cumulative_man_day": str(
                row.reported_cumulative_man_day
            ),
            "calculated_cumulative_man_day": str(
                row.calculated_cumulative_man_day
            ),
            "confirmed_cumulative_man_day": str(
                row.confirmed_cumulative_man_day
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
