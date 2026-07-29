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
from outsource_mail_collector.application.work_order_mapping_service import (
    WorkOrderMappingService,
)
from outsource_mail_collector.application.models import (
    ReviewRecord,
    WorkReportRow,
    WorkReportRangeResult,
    work_report_row_from_stored,
)
from outsource_mail_collector.domain.models import ReviewStatus
from outsource_mail_collector.domain.work_report import (
    RowSource,
    WorkReportIssueCode,
    man_day_basis,
)
from outsource_mail_collector.infrastructure.db.repository import (
    SQLiteRepository,
    StoredWorkReportRow,
)


_STRUCTURAL_BLOCKERS = {
    WorkReportIssueCode.DATE_UNRESOLVED,
    WorkReportIssueCode.DUPLICATE_UNRESOLVED,
    WorkReportIssueCode.SERIES_KEY_MISSING,
    WorkReportIssueCode.INVALID_VALUE,
    WorkReportIssueCode.ACTUAL_HEADCOUNT_INVALID,
    WorkReportIssueCode.REPORTED_DAILY_INVALID,
    WorkReportIssueCode.REPORTED_CUMULATIVE_INVALID,
    WorkReportIssueCode.WORK_ORDER_UNREGISTERED,
    WorkReportIssueCode.NIGHT_HEADCOUNT_INVALID,
}
_BLOCKING_CODES = _STRUCTURAL_BLOCKERS | {
    WorkReportIssueCode.CUMULATIVE_BASELINE_REQUIRED,
}
_RECALCULATION_TRIGGER_FIELDS = {
    "work_date",
    "vendor_name",
    "tracking_no",
    "equipment_name",
    "actual_headcount",
    "night_headcount",
    "reported_daily_man_day",
    "reported_cumulative_man_day",
}
_RECALCULATED_ISSUE_CODES = {
    WorkReportIssueCode.DATE_UNRESOLVED,
    WorkReportIssueCode.DAILY_MISSING,
    WorkReportIssueCode.DAILY_MISMATCH,
    WorkReportIssueCode.CUMULATIVE_MISSING,
    WorkReportIssueCode.CUMULATIVE_MISMATCH,
    WorkReportIssueCode.CUMULATIVE_BASELINE_CONFIRMATION,
    WorkReportIssueCode.CUMULATIVE_BASELINE_REQUIRED,
    WorkReportIssueCode.SERIES_KEY_MISSING,
    WorkReportIssueCode.INVALID_VALUE,
    WorkReportIssueCode.ACTUAL_HEADCOUNT_INVALID,
    WorkReportIssueCode.REPORTED_DAILY_INVALID,
    WorkReportIssueCode.REPORTED_CUMULATIVE_INVALID,
    WorkReportIssueCode.NIGHT_HEADCOUNT_UNRESOLVED,
    WorkReportIssueCode.NIGHT_HEADCOUNT_INVALID,
}
_MAPPING_ISSUE_CODES = {
    WorkReportIssueCode.WORK_ORDER_UNREGISTERED,
    WorkReportIssueCode.EQUIPMENT_MAPPING_MISMATCH,
}
_INVALID_PROVENANCE_FIELDS = {
    WorkReportIssueCode.ACTUAL_HEADCOUNT_INVALID: "actual_headcount",
    WorkReportIssueCode.REPORTED_DAILY_INVALID: "reported_daily_man_day",
    WorkReportIssueCode.REPORTED_CUMULATIVE_INVALID: (
        "reported_cumulative_man_day"
    ),
}
_NIGHT_HEADCOUNT_ISSUE_CODES = {
    WorkReportIssueCode.NIGHT_HEADCOUNT_UNRESOLVED,
    WorkReportIssueCode.NIGHT_HEADCOUNT_INVALID,
}
_RECALCULATED_FIELDS = {
    "per_person_man_day",
    "calculated_daily_man_day",
    "confirmed_daily_man_day",
    "calculated_cumulative_man_day",
    "confirmed_cumulative_man_day",
    "cumulative_series_key",
    "issue_codes",
    "warning_confirmed",
}


class WorkReportService:
    """Coordinate calculation, series lookup, duplicates, and audit persistence."""

    def __init__(
        self,
        repository: SQLiteRepository,
        calculation_service: ManDayCalculationService,
        mapping_service: WorkOrderMappingService,
    ) -> None:
        self._repository = repository
        self._calculation = calculation_service
        self._mapping = mapping_service

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
            mapping = self._mapping.resolve(
                record.tracking_no, record.equipment_name
            )
            values = self._calculate_values(
                work_date=record.report_date,
                work_date_confirmed=record.work_date_confirmed,
                vendor_name=_clean_text(record.vendor_name) or mapping.vendor_name,
                tracking_no=record.tracking_no,
                equipment_name=record.equipment_name,
                business_team=(
                    _clean_text(record.business_team) or mapping.business_team
                ),
                actual_headcount=record.actual_headcount,
                night_headcount=record.night_headcount,
                reported_daily_man_day=record.daily_man_day,
                reported_cumulative_man_day=record.cumulative_man_day,
                date_issue_codes=record.date_issue_codes,
                mapping_issue_codes=mapping.issue_codes,
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
        reported_daily_man_day: object | None,
        reported_cumulative_man_day: object | None,
        resolution_note: str,
        night_headcount: object | None = None,
        per_person_man_day: object | None = None,
    ) -> WorkReportRow:
        if not resolution_note.strip():
            raise ValueError("수동 행 추가 사유를 입력해 주세요.")
        resolved_night_headcount = _manual_night_headcount(
            actual_headcount=actual_headcount,
            night_headcount=night_headcount,
            per_person_man_day=per_person_man_day,
        )
        values = self._calculate_values(
            work_date=work_date,
            work_date_confirmed=True,
            vendor_name=vendor_name,
            tracking_no=tracking_no,
            equipment_name=equipment_name,
            business_team=business_team,
            actual_headcount=actual_headcount,
            night_headcount=resolved_night_headcount,
            reported_daily_man_day=reported_daily_man_day,
            reported_cumulative_man_day=reported_cumulative_man_day,
            date_issue_codes=(),
            mapping_issue_codes=(),
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
        if set(changes) & _RECALCULATION_TRIGGER_FIELDS:
            current = self._repository.get_work_report_row(row_id)
            changes = self._recalculate_updated_values(current, changes)
        row = self._repository.update_work_report_row(
            row_id, changes, resolution_note=resolution_note
        )
        self._mark_unresolved_duplicates()
        return work_report_row_from_stored(row)

    def refresh_work_order_mappings(self) -> list[WorkReportRow]:
        """Reapply master data to eligible unconfirmed mail-derived rows."""

        refreshed_ids: list[int] = []
        for current in self._repository.list_all_work_report_rows():
            if current.source_type is not RowSource.MAIL:
                continue
            if current.warning_confirmed:
                continue
            if (
                not set(current.issue_codes) & _MAPPING_ISSUE_CODES
                and current.vendor_name
                and current.business_team
            ):
                continue
            values = self._recalculate_updated_values(
                current,
                {},
                refresh_mapping=True,
            )
            updated = self._repository.update_work_report_row(
                current.row_id,
                values,
                resolution_note="수주 마스터 변경 재적용",
            )
            refreshed_ids.append(updated.row_id)
        if refreshed_ids:
            self._mark_unresolved_duplicates()
        return [
            work_report_row_from_stored(
                self._repository.get_work_report_row(row_id)
            )
            for row_id in refreshed_ids
        ]

    def _recalculate_updated_values(
        self,
        current: StoredWorkReportRow,
        changes: dict[str, Any],
        *,
        refresh_mapping: bool = False,
    ) -> dict[str, Any]:
        recalculated_issues = set(_RECALCULATED_ISSUE_CODES)
        mapping_recalculation = refresh_mapping or bool(
            {"tracking_no", "equipment_name"} & set(changes)
        )
        if mapping_recalculation:
            recalculated_issues.update(_MAPPING_ISSUE_CODES)
        if "night_headcount" not in changes:
            recalculated_issues -= _NIGHT_HEADCOUNT_ISSUE_CODES
        for issue, field_name in _INVALID_PROVENANCE_FIELDS.items():
            if field_name not in changes:
                recalculated_issues.discard(issue)
        recalculated_issues.discard(WorkReportIssueCode.INVALID_VALUE)
        current_invalid_sources = {
            issue
            for issue in current.issue_codes
            if issue in _INVALID_PROVENANCE_FIELDS
        }
        if WorkReportIssueCode.INVALID_VALUE in current.issue_codes:
            if current_invalid_sources:
                clear_generic_invalid = all(
                    _INVALID_PROVENANCE_FIELDS[issue] in changes
                    for issue in current_invalid_sources
                )
            else:
                clear_generic_invalid = all(
                    field_name in changes
                    for field_name in _INVALID_PROVENANCE_FIELDS.values()
                )
            if clear_generic_invalid:
                recalculated_issues.add(WorkReportIssueCode.INVALID_VALUE)
        retained_issues = tuple(
            issue.value
            for issue in current.issue_codes
            if issue not in recalculated_issues
        )
        vendor_name = changes.get("vendor_name", current.vendor_name)
        business_team = changes.get(
            "business_team", current.business_team
        )
        mapping_issue_codes: tuple[WorkReportIssueCode, ...] = ()
        if mapping_recalculation:
            old_mapping = self._mapping.resolve(
                current.tracking_no, current.equipment_name
            )
            new_mapping = self._mapping.resolve(
                changes.get("tracking_no", current.tracking_no),
                changes.get("equipment_name", current.equipment_name),
            )
            if "vendor_name" not in changes and (
                not _clean_text(current.vendor_name)
                or (
                    old_mapping.vendor_name is not None
                    and _clean_text(current.vendor_name)
                    == _clean_text(old_mapping.vendor_name)
                )
            ):
                vendor_name = new_mapping.vendor_name
            if "business_team" not in changes and (
                not _clean_text(current.business_team)
                or (
                    old_mapping.business_team is not None
                    and _clean_text(current.business_team)
                    == _clean_text(old_mapping.business_team)
                )
            ):
                business_team = new_mapping.business_team
            mapping_issue_codes = new_mapping.issue_codes
        values = self._calculate_values(
            work_date=changes.get("work_date", current.work_date),
            work_date_confirmed=changes.get(
                "work_date_confirmed", current.work_date_confirmed
            ),
            vendor_name=vendor_name,
            tracking_no=changes.get("tracking_no", current.tracking_no),
            equipment_name=changes.get(
                "equipment_name", current.equipment_name
            ),
            business_team=business_team,
            actual_headcount=changes.get(
                "actual_headcount", current.actual_headcount
            ),
            night_headcount=changes.get(
                "night_headcount", current.night_headcount
            ),
            reported_daily_man_day=changes.get(
                "reported_daily_man_day", current.reported_daily_man_day
            ),
            reported_cumulative_man_day=changes.get(
                "reported_cumulative_man_day",
                current.reported_cumulative_man_day,
            ),
            date_issue_codes=retained_issues,
            mapping_issue_codes=mapping_issue_codes,
            review_status=current.review_status,
        )
        values.pop("resolution_note")
        for field_name, value in changes.items():
            if (
                field_name not in _RECALCULATION_TRIGGER_FIELDS
                and field_name not in _RECALCULATED_FIELDS
            ):
                values[field_name] = value
        return values

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
        night_headcount: object | None,
        reported_daily_man_day: object | None,
        reported_cumulative_man_day: object | None,
        date_issue_codes: tuple[str, ...],
        mapping_issue_codes: tuple[WorkReportIssueCode, ...],
        review_status: ReviewStatus,
    ) -> dict[str, Any]:
        issues = _known_issue_codes(date_issue_codes)
        for issue in mapping_issue_codes:
            _append_issue(issues, issue)
        series_key = build_cumulative_series_key(
            vendor_name, tracking_no, equipment_name
        )
        if work_date is None:
            _append_issue(issues, WorkReportIssueCode.DATE_UNRESOLVED)
        if series_key is None:
            _append_issue(issues, WorkReportIssueCode.SERIES_KEY_MISSING)

        reported_daily: Decimal | None = None
        reported_daily_valid = True
        try:
            reported_daily = _optional_man_day(reported_daily_man_day)
        except (ValueError, InvalidOperation):
            reported_daily_valid = False
            _append_issue(issues, WorkReportIssueCode.INVALID_VALUE)
            _append_issue(
                issues, WorkReportIssueCode.REPORTED_DAILY_INVALID
            )
        reported_cumulative: Decimal | None = None
        reported_cumulative_valid = True
        try:
            reported_cumulative = _optional_man_day(
                reported_cumulative_man_day
            )
        except (ValueError, InvalidOperation):
            reported_cumulative_valid = False
            _append_issue(issues, WorkReportIssueCode.INVALID_VALUE)
            _append_issue(
                issues, WorkReportIssueCode.REPORTED_CUMULATIVE_INVALID
            )
        daily_calculated: Decimal | None = None
        confirmed_daily: Decimal | None = None
        parsed_headcount: int | None = None
        parsed_night_headcount: int | None = None
        parsed_per_person: Decimal | None = None
        try:
            parsed_headcount = _headcount(
                actual_headcount, field_name="실제 작업인원"
            )
        except (ValueError, InvalidOperation):
            _append_issue(issues, WorkReportIssueCode.INVALID_VALUE)
            _append_issue(
                issues, WorkReportIssueCode.ACTUAL_HEADCOUNT_INVALID
            )

        if night_headcount is None:
            if WorkReportIssueCode.NIGHT_HEADCOUNT_INVALID not in issues:
                _append_issue(
                    issues, WorkReportIssueCode.NIGHT_HEADCOUNT_UNRESOLVED
                )
        else:
            try:
                parsed_night_headcount = _headcount(
                    night_headcount, field_name="야근 인원"
                )
                if (
                    parsed_headcount is not None
                    and parsed_night_headcount > parsed_headcount
                ):
                    raise ValueError(
                        "야근 인원은 실제 작업인원보다 클 수 없습니다."
                    )
            except (ValueError, InvalidOperation):
                parsed_night_headcount = None
                _append_issue(
                    issues, WorkReportIssueCode.NIGHT_HEADCOUNT_INVALID
                )

        if parsed_headcount is not None and parsed_night_headcount is not None:
            daily = self._calculation.calculate_daily(
                actual_headcount=parsed_headcount,
                night_headcount=parsed_night_headcount,
                reported_daily=reported_daily,
            )
            parsed_per_person = _uniform_per_person_man_day(
                parsed_headcount, parsed_night_headcount
            )
            reported_daily = daily.reported
            daily_calculated = daily.calculated
            confirmed_daily = daily.confirmed_candidate
            for issue in daily.issues:
                if (
                    issue is WorkReportIssueCode.DAILY_MISSING
                    and (
                        not reported_daily_valid
                        or WorkReportIssueCode.REPORTED_DAILY_INVALID in issues
                    )
                ):
                    continue
                _append_issue(issues, issue)

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
                if (
                    issue is WorkReportIssueCode.CUMULATIVE_MISSING
                    and (
                        not reported_cumulative_valid
                        or WorkReportIssueCode.REPORTED_CUMULATIVE_INVALID
                        in issues
                    )
                ):
                    continue
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
            "night_headcount": parsed_night_headcount,
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


def _headcount(value: object, *, field_name: str) -> int:
    if value is None:
        raise ValueError(f"{field_name}이(가) 필요합니다.")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name}은(는) 숫자여야 합니다.") from exc
    if (
        not parsed.is_finite()
        or parsed < 0
        or parsed != parsed.to_integral_value()
    ):
        raise ValueError(f"{field_name}은(는) 0 이상의 정수여야 합니다.")
    return int(parsed)


def _uniform_per_person_man_day(
    actual_headcount: int,
    night_headcount: int,
) -> Decimal | None:
    basis = man_day_basis(actual_headcount, night_headcount)
    if basis in {"1.0", "1.5"}:
        return Decimal(basis)
    return None


def _manual_night_headcount(
    *,
    actual_headcount: object,
    night_headcount: object | None,
    per_person_man_day: object | None,
) -> object | None:
    if night_headcount is not None:
        return night_headcount
    if per_person_man_day is None:
        return None
    try:
        legacy_basis = Decimal(str(per_person_man_day))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("인당 공수는 숫자여야 합니다.") from exc
    if not legacy_basis.is_finite():
        raise ValueError("인당 공수는 유한한 숫자여야 합니다.")
    if legacy_basis == Decimal("1.0"):
        return 0
    if legacy_basis == Decimal("1.5"):
        return actual_headcount
    raise ValueError("기존 인당 공수 입력은 1.0 또는 1.5만 지원합니다.")


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
