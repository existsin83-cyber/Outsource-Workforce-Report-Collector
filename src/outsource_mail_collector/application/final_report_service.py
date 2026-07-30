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
from outsource_mail_collector.domain.work_report import (
    WorkReportIssueCode,
    man_day_basis,
)
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
    WorkReportIssueCode.ACTUAL_HEADCOUNT_INVALID,
    WorkReportIssueCode.REPORTED_DAILY_INVALID,
    WorkReportIssueCode.REPORTED_CUMULATIVE_INVALID,
    WorkReportIssueCode.WORK_ORDER_UNREGISTERED,
    WorkReportIssueCode.NIGHT_HEADCOUNT_UNRESOLVED,
    WorkReportIssueCode.NIGHT_HEADCOUNT_INVALID,
}

_BLOCKING_MESSAGES = {
    WorkReportIssueCode.DATE_UNRESOLVED: "작업일을 결정할 수 없습니다. 원본 메일을 확인해 작업일을 확정해 주세요.",
    WorkReportIssueCode.CUMULATIVE_BASELINE_REQUIRED: "이전 확정 누적 기준이 없습니다. 이전 누적값을 확인하고 확정해 주세요.",
    WorkReportIssueCode.DUPLICATE_UNRESOLVED: "중복 보고가 해결되지 않았습니다. 후보 행을 함께 선택해 처리 방식을 정해 주세요.",
    WorkReportIssueCode.SERIES_KEY_MISSING: "누적 공수를 연결할 식별 정보가 없습니다. Tracking No. 또는 장비 정보를 확인해 주세요.",
    WorkReportIssueCode.INVALID_VALUE: "유효하지 않은 값이 있습니다. 표시된 값을 0 이상의 숫자로 수정해 주세요.",
    WorkReportIssueCode.ACTUAL_HEADCOUNT_INVALID: "실제 작업인원이 유효하지 않습니다. 0 이상의 정수로 수정해 주세요.",
    WorkReportIssueCode.REPORTED_DAILY_INVALID: "메일의 당일 투입 공수를 숫자로 확인할 수 없습니다. 원문을 확인해 확정 투입을 입력해 주세요.",
    WorkReportIssueCode.REPORTED_CUMULATIVE_INVALID: "메일의 누적 공수를 숫자로 확인할 수 없습니다. 원문을 확인해 확정 누적을 입력해 주세요.",
    WorkReportIssueCode.WORK_ORDER_UNREGISTERED: "등록되지 않은 수주입니다. 설정에서 해당 Tracking No.의 수주를 등록한 뒤 다시 취합해 주세요.",
    WorkReportIssueCode.NIGHT_HEADCOUNT_UNRESOLVED: "야근 인원을 확인할 수 없습니다. 원본 메일을 확인해 야근 인원을 입력해 주세요.",
    WorkReportIssueCode.NIGHT_HEADCOUNT_INVALID: "야근 인원이 유효하지 않습니다. 0 이상이며 실제 작업인원 이하가 되도록 수정해 주세요.",
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
                    message=_BLOCKING_MESSAGES[issue],
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
    invalid_headcounts = (
        row.actual_headcount is not None
        and row.night_headcount is not None
        and (
            row.actual_headcount < 0
            or row.night_headcount < 0
            or row.night_headcount > row.actual_headcount
        )
    )
    if (
        invalid_headcounts
        and WorkReportIssueCode.NIGHT_HEADCOUNT_INVALID
        not in row.issue_codes
    ):
        blockers.append(
            FinalizationBlocker(
                row_id=row.row_id,
                code=WorkReportIssueCode.NIGHT_HEADCOUNT_INVALID.value,
                message="야근 인원은 0 이상이며 실제 작업인원 이하여야 합니다.",
            )
        )
    mixed = (
        row.actual_headcount is not None
        and row.night_headcount is not None
        and 0 < row.night_headcount < row.actual_headcount
    )
    missing_fields: list[str] = []
    for field_name, value in (
        ("거래처명", row.vendor_name),
        ("사업팀", row.business_team),
        ("실제 작업인원", row.actual_headcount),
        ("야근 인원", row.night_headcount),
    ):
        if value is None or value == "":
            missing_fields.append(field_name)
    if row.per_person_man_day is None and not mixed:
        missing_fields.append("인당 공수")
    if not row.tracking_no and not row.equipment_name:
        missing_fields.append("Tracking No. 또는 장비명")
    if missing_fields:
        blockers.append(
            FinalizationBlocker(
                row_id=row.row_id,
                code="REQUIRED_FIELD_MISSING",
                message="최종 표의 필수 항목을 입력해 주세요: "
                + ", ".join(missing_fields),
            )
        )
    missing_confirmed: list[str] = []
    if row.confirmed_daily_man_day is None:
        missing_confirmed.append("확정 투입")
    if row.confirmed_cumulative_man_day is None:
        missing_confirmed.append("확정 누적")
    if missing_confirmed:
        blockers.append(
            FinalizationBlocker(
                row_id=row.row_id,
                code="CONFIRMED_MAN_DAY_MISSING",
                message="확인 창에서 다음 공수를 입력해 주세요: "
                + ", ".join(missing_confirmed),
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
            "night_headcount": row.night_headcount,
            "man_day_basis": man_day_basis(
                row.actual_headcount, row.night_headcount
            ),
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
