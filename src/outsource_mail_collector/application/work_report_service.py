"""Assemble extracted and manual records into reviewable work-report rows."""

from __future__ import annotations

import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from outsource_mail_collector.application.man_day_calculation_service import (
    ManDayCalculationService,
    quantize_man_day,
)
from outsource_mail_collector.application.models import (
    ReviewRecord,
    WorkReportRow,
    WorkReportRangeResult,
    work_report_row_from_stored,
)
from outsource_mail_collector.domain.models import ReviewStatus
from outsource_mail_collector.domain.work_report import WorkReportIssueCode
from outsource_mail_collector.infrastructure.db.repository import (
    SQLiteRepository,
    StoredWorkReportRow,
)


_STRUCTURAL_BLOCKERS = {
    WorkReportIssueCode.DATE_UNRESOLVED,
    WorkReportIssueCode.DUPLICATE_UNRESOLVED,
    WorkReportIssueCode.SERIES_KEY_MISSING,
    WorkReportIssueCode.INVALID_VALUE,
}
_BLOCKING_CODES = _STRUCTURAL_BLOCKERS | {
    WorkReportIssueCode.CUMULATIVE_BASELINE_REQUIRED,
}


class WorkReportService:
    """Coordinate calculation, series lookup, duplicates, and audit persistence."""

    def __init__(
        self,
        repository: SQLiteRepository,
        calculation_service: ManDayCalculationService,
    ) -> None:
        self._repository = repository
        self._calculation = calculation_service

    def synchronize_extracted_records(
        self, records: Iterable[ReviewRecord]
    ) -> list[WorkReportRow]:
        stored_rows: list[StoredWorkReportRow] = []
        ordered = sorted(
            records,
            key=lambda row: (
                row.report_date is None,
                row.report_date or date.max,
                row.record_id,
            ),
        )
        for record in ordered:
            values = self._calculate_values(
                work_date=record.report_date,
                work_date_confirmed=record.work_date_confirmed,
                vendor_name=record.vendor_name,
                tracking_no=record.tracking_no,
                equipment_name=record.equipment_name,
                business_team=record.business_team,
                actual_headcount=record.actual_headcount,
                per_person_man_day=record.per_person_man_day,
                reported_daily_man_day=record.daily_man_day,
                reported_cumulative_man_day=record.cumulative_man_day,
                date_issue_codes=record.date_issue_codes,
                review_status=record.review_status,
            )
            stored_rows.append(
                self._repository.get_or_create_mail_report_row(
                    extracted_record_id=record.record_id,
                    mail_entry_id=record.mail_entry_id,
                    **values,
                )
            )
        self._mark_unresolved_duplicates()
        return [
            work_report_row_from_stored(
                self._repository.get_work_report_row(row.row_id)
            )
            for row in stored_rows
        ]

    def list_rows(
        self, date_from: date, date_to: date
    ) -> WorkReportRangeResult:
        rows = tuple(
            work_report_row_from_stored(row)
            for row in self._repository.list_work_report_rows(
                date_from, date_to
            )
        )
        blocking_count = sum(
            bool(set(row.issue_codes) & _BLOCKING_CODES)
            for row in rows
            if row.included
        )
        warning_count = sum(
            bool(row.issue_codes)
            and not bool(set(row.issue_codes) & _BLOCKING_CODES)
            for row in rows
            if row.included
        )
        return WorkReportRangeResult(
            rows=rows,
            warning_count=warning_count,
            blocking_count=blocking_count,
        )

    def add_manual_row(
        self,
        *,
        work_date: date,
        vendor_name: str,
        tracking_no: str | None,
        equipment_name: str | None,
        business_team: str,
        actual_headcount: object,
        per_person_man_day: object,
        reported_daily_man_day: object | None,
        reported_cumulative_man_day: object | None,
        resolution_note: str,
    ) -> WorkReportRow:
        if not resolution_note.strip():
            raise ValueError("수동 행 추가 사유를 입력해 주세요.")
        values = self._calculate_values(
            work_date=work_date,
            work_date_confirmed=True,
            vendor_name=vendor_name,
            tracking_no=tracking_no,
            equipment_name=equipment_name,
            business_team=business_team,
            actual_headcount=actual_headcount,
            per_person_man_day=per_person_man_day,
            reported_daily_man_day=reported_daily_man_day,
            reported_cumulative_man_day=reported_cumulative_man_day,
            date_issue_codes=(),
            review_status=ReviewStatus.NORMAL,
        )
        values["resolution_note"] = resolution_note.strip()
        row = self._repository.create_manual_report_row(**values)
        self._mark_unresolved_duplicates()
        return work_report_row_from_stored(
            self._repository.get_work_report_row(row.row_id)
        )

    def update_row(
        self,
        row_id: int,
        changes: dict[str, Any],
        *,
        resolution_note: str,
    ) -> WorkReportRow:
        if not resolution_note.strip():
            raise ValueError("변경 사유를 입력해 주세요.")
        row = self._repository.update_work_report_row(
            row_id, changes, resolution_note=resolution_note
        )
        self._mark_unresolved_duplicates()
        return work_report_row_from_stored(row)

    def confirm_row(
        self,
        row_id: int,
        *,
        confirmed_daily_man_day: Decimal,
        confirmed_cumulative_man_day: Decimal,
        resolution_note: str,
    ) -> WorkReportRow:
        row = self._repository.get_work_report_row(row_id)
        blockers = set(row.issue_codes) & _STRUCTURAL_BLOCKERS
        if blockers:
            raise ValueError("구조적 오류를 먼저 해결해야 행을 확정할 수 있습니다.")
        confirmed = self._repository.confirm_work_report_row(
            row_id,
            confirmed_daily_man_day=quantize_man_day(
                Decimal(str(confirmed_daily_man_day))
            ),
            confirmed_cumulative_man_day=quantize_man_day(
                Decimal(str(confirmed_cumulative_man_day))
            ),
            resolution_note=resolution_note,
        )
        self._recalculate_following_rows(confirmed)
        return work_report_row_from_stored(confirmed)

    def set_included(
        self, row_id: int, included: bool, *, resolution_note: str
    ) -> WorkReportRow:
        status = ReviewStatus.NORMAL if included else ReviewStatus.EXCLUDED
        stored = self._repository.update_work_report_row(
            row_id,
            {"included": included, "review_status": status},
            resolution_note=resolution_note,
        )
        return work_report_row_from_stored(stored)

    def resolve_duplicate(
        self,
        row_ids: list[int],
        decision: str,
        *,
        resolution_note: str,
    ) -> list[WorkReportRow]:
        return [
            work_report_row_from_stored(row)
            for row in self._repository.resolve_duplicate_rows(
                row_ids, decision, resolution_note=resolution_note
            )
        ]

    def _calculate_values(
        self,
        *,
        work_date: date | None,
        work_date_confirmed: bool,
        vendor_name: str | None,
        tracking_no: str | None,
        equipment_name: str | None,
        business_team: str | None,
        actual_headcount: object,
        per_person_man_day: object,
        reported_daily_man_day: object | None,
        reported_cumulative_man_day: object | None,
        date_issue_codes: tuple[str, ...],
        review_status: ReviewStatus,
    ) -> dict[str, Any]:
        issues = _known_issue_codes(date_issue_codes)
        series_key = build_cumulative_series_key(
            vendor_name, tracking_no, equipment_name
        )
        if work_date is None:
            _append_issue(issues, WorkReportIssueCode.DATE_UNRESOLVED)
        if series_key is None:
            _append_issue(issues, WorkReportIssueCode.SERIES_KEY_MISSING)

        reported_daily = _optional_man_day(reported_daily_man_day)
        reported_cumulative = _optional_man_day(
            reported_cumulative_man_day
        )
        daily_calculated: Decimal | None = None
        confirmed_daily: Decimal | None = None
        parsed_headcount: int | None = None
        parsed_per_person: Decimal | None = None
        try:
            daily = self._calculation.calculate_daily(
                actual_headcount=actual_headcount,
                per_person_man_day=per_person_man_day,
                reported_daily=reported_daily,
            )
            parsed_headcount = int(Decimal(str(actual_headcount)))
            parsed_per_person = quantize_man_day(
                Decimal(str(per_person_man_day))
            )
            reported_daily = daily.reported
            daily_calculated = daily.calculated
            confirmed_daily = daily.confirmed_candidate
            for issue in daily.issues:
                _append_issue(issues, issue)
        except (ValueError, InvalidOperation):
            _append_issue(issues, WorkReportIssueCode.INVALID_VALUE)

        cumulative_calculated: Decimal | None = None
        confirmed_cumulative: Decimal | None = None
        if confirmed_daily is not None and series_key is not None:
            prior = self._prior_cumulative(series_key, work_date)
            cumulative = self._calculation.calculate_cumulative(
                prior_confirmed_cumulative=prior,
                confirmed_daily=confirmed_daily,
                reported_cumulative=reported_cumulative,
            )
            reported_cumulative = cumulative.reported
            cumulative_calculated = cumulative.calculated
            confirmed_cumulative = cumulative.confirmed_candidate
            for issue in cumulative.issues:
                _append_issue(issues, issue)

        warning_confirmed = not issues
        return {
            "work_date": work_date,
            "work_date_confirmed": work_date_confirmed,
            "vendor_name": _clean_text(vendor_name),
            "tracking_no": _clean_text(tracking_no),
            "equipment_name": _clean_text(equipment_name),
            "business_team": _clean_text(business_team),
            "actual_headcount": parsed_headcount,
            "per_person_man_day": parsed_per_person,
            "reported_daily_man_day": reported_daily,
            "calculated_daily_man_day": daily_calculated,
            "confirmed_daily_man_day": confirmed_daily,
            "reported_cumulative_man_day": reported_cumulative,
            "calculated_cumulative_man_day": cumulative_calculated,
            "confirmed_cumulative_man_day": confirmed_cumulative,
            "cumulative_series_key": series_key,
            "issue_codes": tuple(issues),
            "review_status": review_status,
            "included": review_status is not ReviewStatus.EXCLUDED,
            "warning_confirmed": warning_confirmed,
            "resolution_note": None,
        }

    def _prior_cumulative(
        self, series_key: str, work_date: date | None
    ) -> Decimal | None:
        if work_date is None:
            return None
        candidates = [
            row
            for row in self._repository.list_work_report_rows(
                date.min, work_date
            )
            if row.cumulative_series_key == series_key
            and row.work_date is not None
            and row.work_date < work_date
            and row.confirmed_cumulative_man_day is not None
            and row.included
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda row: (row.work_date or date.min, row.row_id))
        return candidates[-1].confirmed_cumulative_man_day

    def _mark_unresolved_duplicates(self) -> None:
        rows = self._repository.list_work_report_rows(date.min, date.max)
        groups: dict[tuple[date, str], list[StoredWorkReportRow]] = {}
        for row in rows:
            if row.work_date is None or row.cumulative_series_key is None:
                continue
            groups.setdefault(
                (row.work_date, row.cumulative_series_key), []
            ).append(row)
        for candidates in groups.values():
            if len(candidates) < 2:
                continue
            already_resolved = (
                sum(row.included for row in candidates) <= 1
                and all(
                    WorkReportIssueCode.DUPLICATE_UNRESOLVED
                    not in row.issue_codes
                    for row in candidates
                )
            )
            if already_resolved:
                continue
            for row in candidates:
                if WorkReportIssueCode.DUPLICATE_UNRESOLVED in row.issue_codes:
                    continue
                self._repository.update_work_report_row(
                    row.row_id,
                    {
                        "issue_codes": (
                            *row.issue_codes,
                            WorkReportIssueCode.DUPLICATE_UNRESOLVED,
                        ),
                        "warning_confirmed": False,
                    },
                    resolution_note="중복 또는 수정 보고 후보 자동 감지",
                )

    def _recalculate_following_rows(
        self, confirmed_row: StoredWorkReportRow
    ) -> None:
        if (
            confirmed_row.work_date is None
            or confirmed_row.cumulative_series_key is None
            or confirmed_row.confirmed_cumulative_man_day is None
        ):
            return
        rows = [
            row
            for row in self._repository.list_work_report_rows(
                confirmed_row.work_date, date.max
            )
            if row.cumulative_series_key
            == confirmed_row.cumulative_series_key
            and row.work_date is not None
            and row.work_date > confirmed_row.work_date
            and row.included
        ]
        rows.sort(key=lambda row: (row.work_date or date.max, row.row_id))
        prior = confirmed_row.confirmed_cumulative_man_day
        cumulative_codes = {
            WorkReportIssueCode.CUMULATIVE_MISSING,
            WorkReportIssueCode.CUMULATIVE_MISMATCH,
            WorkReportIssueCode.CUMULATIVE_BASELINE_CONFIRMATION,
            WorkReportIssueCode.CUMULATIVE_BASELINE_REQUIRED,
        }
        for row in rows:
            if row.confirmed_daily_man_day is None:
                break
            result = self._calculation.calculate_cumulative(
                prior_confirmed_cumulative=prior,
                confirmed_daily=row.confirmed_daily_man_day,
                reported_cumulative=row.reported_cumulative_man_day,
            )
            issues = [
                issue
                for issue in row.issue_codes
                if issue not in cumulative_codes
            ]
            for issue in result.issues:
                _append_issue(issues, issue)
            updated = self._repository.update_work_report_row(
                row.row_id,
                {
                    "calculated_cumulative_man_day": result.calculated,
                    "confirmed_cumulative_man_day": (
                        result.confirmed_candidate
                    ),
                    "issue_codes": tuple(issues),
                    "warning_confirmed": not issues,
                },
                resolution_note="이전 확정 누적 변경에 따른 자동 재계산",
            )
            if updated.confirmed_cumulative_man_day is None:
                break
            prior = updated.confirmed_cumulative_man_day


def build_cumulative_series_key(
    vendor_name: str | None,
    tracking_no: str | None,
    equipment_name: str | None,
) -> str | None:
    vendor = _normalize_text(vendor_name)
    if not vendor:
        return None
    tracking = "".join(_normalize_text(tracking_no).split()).upper()
    if tracking:
        return f"{vendor}|T:{tracking}"
    equipment = _normalize_text(equipment_name)
    if equipment:
        return f"{vendor}|E:{equipment}"
    return None


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split()).casefold()


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _optional_man_day(value: object | None) -> Decimal | None:
    if value is None:
        return None
    parsed = Decimal(str(value))
    if not parsed.is_finite() or parsed < 0:
        raise ValueError("공수는 0 이상의 유한한 숫자여야 합니다.")
    return quantize_man_day(parsed)


def _known_issue_codes(values: tuple[str, ...]) -> list[WorkReportIssueCode]:
    result: list[WorkReportIssueCode] = []
    for value in values:
        try:
            _append_issue(result, WorkReportIssueCode(value))
        except ValueError:
            continue
    return result


def _append_issue(
    issues: list[WorkReportIssueCode], issue: WorkReportIssueCode
) -> None:
    if issue not in issues:
        issues.append(issue)
