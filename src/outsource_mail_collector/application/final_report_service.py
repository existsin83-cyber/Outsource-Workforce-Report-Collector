"""Validate, order, and snapshot a final external-work report."""

from __future__ import annotations

import hashlib
import json
from datetime import date

from outsource_mail_collector.application.models import (
    FinalizationBlocker,
    FinalReportPreview,
    FinalReportSnapshot,
    final_report_snapshot_from_stored,
    work_report_row_from_stored,
)
from outsource_mail_collector.domain.work_report import WorkReportIssueCode
from outsource_mail_collector.infrastructure.db.repository import (
    SQLiteRepository,
    StoredWorkReportRow,
)


_BLOCKING_ISSUES = {
    WorkReportIssueCode.DATE_UNRESOLVED,
    WorkReportIssueCode.CUMULATIVE_BASELINE_REQUIRED,
    WorkReportIssueCode.DUPLICATE_UNRESOLVED,
    WorkReportIssueCode.SERIES_KEY_MISSING,
    WorkReportIssueCode.INVALID_VALUE,
}


class FinalizationError(ValueError):
    """Raised when a report range still has confirmation blockers."""

    def __init__(self, blockers: tuple[FinalizationBlocker, ...]) -> None:
        super().__init__("최종 확정 전에 문제 행을 확인해 주세요.")
        self.blockers = blockers


class FinalReportService:
    """Create immutable final-report snapshots after fresh validation."""

    def __init__(self, repository: SQLiteRepository) -> None:
        self._repository = repository

    def preview(self, date_from: date, date_to: date) -> FinalReportPreview:
        if date_from > date_to:
            raise ValueError("시작일은 종료일보다 늦을 수 없습니다.")
        stored_rows = [
            row
            for row in self._repository.list_work_report_rows(
                date_from, date_to
            )
            if row.included
        ]
        ordered = self._sort_rows(stored_rows)
        blockers = tuple(
            blocker
            for row in ordered
            for blocker in _row_blockers(row)
        )
        return FinalReportPreview(
            date_from=date_from,
            date_to=date_to,
            rows=tuple(work_report_row_from_stored(row) for row in ordered),
            blockers=blockers,
        )

    def confirm(
        self, date_from: date, date_to: date
    ) -> FinalReportSnapshot:
        preview = self.preview(date_from, date_to)
        if preview.blockers:
            raise FinalizationError(preview.blockers)
        stored_rows = [
            self._repository.get_work_report_row(row.row_id)
            for row in preview.rows
        ]
        snapshot_hash = _snapshot_hash(stored_rows)
        stored = self._repository.create_final_report_snapshot(
            date_from=date_from,
            date_to=date_to,
            rows=stored_rows,
            snapshot_hash=snapshot_hash,
        )
        return final_report_snapshot_from_stored(stored)

    def mark_copied(self, report_id: int) -> FinalReportSnapshot:
        return final_report_snapshot_from_stored(
            self._repository.mark_final_report_copied(report_id)
        )

    def _sort_rows(
        self, rows: list[StoredWorkReportRow]
    ) -> list[StoredWorkReportRow]:
        vendor_order = {
            vendor.canonical_name.strip().casefold(): vendor.sort_order
            for vendor in self._repository.list_vendors()
        }
        fallback = 2_147_483_647
        return sorted(
            rows,
            key=lambda row: (
                row.work_date or date.max,
                vendor_order.get(
                    (row.vendor_name or "").strip().casefold(), fallback
                ),
                row.tracking_no is None,
                (row.tracking_no or row.equipment_name or "").casefold(),
                row.row_id,
            ),
        )


def _row_blockers(
    row: StoredWorkReportRow,
) -> tuple[FinalizationBlocker, ...]:
    blockers: list[FinalizationBlocker] = []
    for issue in row.issue_codes:
        if issue in _BLOCKING_ISSUES:
            blockers.append(
                FinalizationBlocker(
                    row_id=row.row_id,
                    code=issue.value,
                    message="차단 오류를 먼저 해결해 주세요.",
                )
            )
    if row.issue_codes and not row.warning_confirmed and not blockers:
        blockers.append(
            FinalizationBlocker(
                row_id=row.row_id,
                code="WARNING_UNCONFIRMED",
                message="경고 내용을 개별 확인해 주세요.",
            )
        )
    if row.work_date is None or not row.work_date_confirmed:
        blockers.append(
            FinalizationBlocker(
                row_id=row.row_id,
                code="WORK_DATE_UNCONFIRMED",
                message="작업일을 확인해 주세요.",
            )
        )
    required = (
        row.vendor_name,
        row.business_team,
        row.actual_headcount,
        row.per_person_man_day,
    )
    if any(value is None or value == "" for value in required) or (
        not row.tracking_no and not row.equipment_name
    ):
        blockers.append(
            FinalizationBlocker(
                row_id=row.row_id,
                code="REQUIRED_FIELD_MISSING",
                message="최종 표의 필수 항목을 입력해 주세요.",
            )
        )
    if (
        row.confirmed_daily_man_day is None
        or row.confirmed_cumulative_man_day is None
    ):
        blockers.append(
            FinalizationBlocker(
                row_id=row.row_id,
                code="CONFIRMED_MAN_DAY_MISSING",
                message="확정 투입·누적 공수를 입력해 주세요.",
            )
        )
    return tuple(blockers)


def _snapshot_hash(rows: list[StoredWorkReportRow]) -> str:
    payload = [
        {
            "row_id": row.row_id,
            "work_date": row.work_date.isoformat() if row.work_date else None,
            "vendor_name": row.vendor_name,
            "tracking_no": row.tracking_no,
            "equipment_name": row.equipment_name,
            "business_team": row.business_team,
            "actual_headcount": row.actual_headcount,
            "per_person_man_day": str(row.per_person_man_day),
            "confirmed_daily_man_day": str(row.confirmed_daily_man_day),
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
