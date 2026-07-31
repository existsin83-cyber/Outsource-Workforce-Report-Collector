"""Plain application DTOs shared between services and the presentation layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from outsource_mail_collector.domain.models import MailRecord, ReviewStatus
from outsource_mail_collector.domain.work_report import (
    RowSource,
    WorkReportIssueCode,
    man_day_basis,
)
from outsource_mail_collector.infrastructure.db.repository import (
    Employee,
    StoredFinalReport,
    StoredFinalReportRow,
    StoredWorkReportRow,
    StoredReviewRecord,
)


@dataclass(frozen=True)
class CollectionError:
    mail_id: str | None
    code: str
    message: str


@dataclass(frozen=True)
class CollectionResult:
    mails: tuple[MailRecord, ...]
    missing_employees: tuple[Employee, ...]
    errors: tuple[CollectionError, ...]
    target_employee_count: int = 0
    received_mail_count: int = 0


@dataclass(frozen=True)
class ReviewRecord:
    record_id: int
    mail_entry_id: str
    report_date: date | None
    sender_name: str
    sender_email: str
    equipment_name: str | None
    tracking_no: str | None
    vendor_name: str | None
    actual_headcount: float | None
    night_headcount: float | None
    daily_man_day: float | None
    cumulative_man_day: float | None
    confidence: float
    review_status: ReviewStatus
    note: str | None
    per_person_man_day: float | None = None
    business_team: str | None = None
    date_issue_codes: tuple[str, ...] = ()
    work_date_confirmed: bool = False


@dataclass(frozen=True)
class WorkReportRow:
    row_id: int
    source_type: RowSource
    extracted_record_id: int | None
    mail_entry_id: str | None
    work_date: date | None
    work_date_confirmed: bool
    vendor_name: str | None
    tracking_no: str | None
    equipment_name: str | None
    business_team: str | None
    actual_headcount: int | None
    per_person_man_day: Decimal | None
    reported_daily_man_day: Decimal | None
    calculated_daily_man_day: Decimal | None
    confirmed_daily_man_day: Decimal | None
    reported_cumulative_man_day: Decimal | None
    calculated_cumulative_man_day: Decimal | None
    confirmed_cumulative_man_day: Decimal | None
    cumulative_series_key: str | None
    issue_codes: tuple[WorkReportIssueCode, ...]
    review_status: ReviewStatus
    included: bool
    warning_confirmed: bool
    resolution_note: str | None
    night_headcount: int | None = None
    deleted_at: str | None = None
    man_day_confirmed: bool = True

    @property
    def per_person_display(self) -> str:
        """Return the display-only basis derived from headcount fields."""

        return man_day_basis(self.actual_headcount, self.night_headcount)


@dataclass(frozen=True)
class WorkReportRangeResult:
    rows: tuple[WorkReportRow, ...]
    warning_count: int
    blocking_count: int


@dataclass(frozen=True)
class FinalizationBlocker:
    row_id: int
    code: str
    message: str


@dataclass(frozen=True)
class TrackingDailyAggregate:
    """Confirmed source rows collapsed by work date and Tracking No."""

    row_id: int
    source_row_ids: tuple[int, ...]
    work_date: date | None
    normalized_tracking_no: str
    tracking_no: str | None
    vendor_name: str | None
    vendor_sort_order: int
    equipment_name: str | None
    business_team: str | None
    actual_headcount: int | None
    night_headcount: int | None
    per_person_man_day: Decimal | None
    man_day_basis: str
    confirmed_daily_man_day: Decimal | None
    reported_cumulative_man_day: Decimal | None
    calculated_cumulative_man_day: Decimal | None
    confirmed_cumulative_man_day: Decimal | None
    blockers: tuple[FinalizationBlocker, ...]

    @property
    def can_confirm(self) -> bool:
        return not self.blockers


@dataclass(frozen=True)
class TrackingDashboardSummary:
    """Lifetime projection for one normalized Tracking No."""

    normalized_tracking_no: str
    tracking_no: str
    vendor_name: str | None
    equipment_name: str | None
    business_team: str | None
    latest_work_date: date | None
    latest_actual_headcount: int | None
    latest_night_headcount: int | None
    latest_man_day_basis: str
    latest_confirmed_daily_man_day: Decimal | None
    latest_reported_cumulative_man_day: Decimal | None
    latest_calculated_cumulative_man_day: Decimal | None
    latest_confirmed_cumulative_man_day: Decimal | None
    initial_cumulative_man_day: Decimal | None
    source_row_ids: tuple[int, ...]
    blockers: tuple[FinalizationBlocker, ...]
    work_start_date: date | None = None
    completed: bool = False

    @property
    def can_confirm(self) -> bool:
        return not self.blockers


@dataclass(frozen=True)
class FinalReportRow:
    source_row_id: int
    work_date: date
    vendor_name: str
    vendor_sort_order: int
    tracking_no: str | None
    equipment_name: str | None
    business_team: str | None
    actual_headcount: int
    night_headcount: int | None
    man_day_basis: str
    confirmed_daily_man_day: Decimal
    confirmed_cumulative_man_day: Decimal
    source_row_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class FinalReportPreview:
    date_from: date
    date_to: date
    rows: tuple[TrackingDailyAggregate, ...]
    blockers: tuple[FinalizationBlocker, ...]

    @property
    def can_confirm(self) -> bool:
        return not self.blockers


@dataclass(frozen=True)
class FinalReportSnapshot:
    report_id: int
    date_from: date
    date_to: date
    snapshot_hash: str
    confirmed_at: str
    copied_at: str | None
    invalidated_at: str | None
    rows: tuple[FinalReportRow, ...]


@dataclass(frozen=True)
class ExtractionResult:
    records: tuple[ReviewRecord, ...]
    skipped_mail_ids: tuple[str, ...]
    errors: tuple[CollectionError, ...]


@dataclass(frozen=True)
class CollectionWorkflowResult:
    collection: CollectionResult
    extraction: ExtractionResult
    records: tuple[ReviewRecord, ...]
    work_report_rows: tuple[WorkReportRow, ...] = ()


def review_record_from_stored(stored: StoredReviewRecord) -> ReviewRecord:
    return ReviewRecord(
        record_id=stored.record_id,
        mail_entry_id=stored.mail_entry_id,
        report_date=stored.report_date,
        sender_name=stored.sender_name,
        sender_email=stored.sender_email,
        equipment_name=stored.equipment_name,
        tracking_no=stored.tracking_no,
        vendor_name=stored.vendor_name,
        actual_headcount=stored.actual_headcount,
        night_headcount=stored.night_headcount,
        per_person_man_day=stored.per_person_man_day,
        daily_man_day=stored.daily_man_day,
        cumulative_man_day=stored.cumulative_man_day,
        business_team=stored.business_team,
        confidence=stored.confidence,
        review_status=stored.review_status,
        note=stored.note,
        date_issue_codes=stored.date_issue_codes,
        work_date_confirmed=stored.work_date_confirmed,
    )


def work_report_row_from_stored(stored: StoredWorkReportRow) -> WorkReportRow:
    return WorkReportRow(
        row_id=stored.row_id,
        source_type=stored.source_type,
        extracted_record_id=stored.extracted_record_id,
        mail_entry_id=stored.mail_entry_id,
        work_date=stored.work_date,
        work_date_confirmed=stored.work_date_confirmed,
        vendor_name=stored.vendor_name,
        tracking_no=stored.tracking_no,
        equipment_name=stored.equipment_name,
        business_team=stored.business_team,
        actual_headcount=stored.actual_headcount,
        night_headcount=stored.night_headcount,
        per_person_man_day=stored.per_person_man_day,
        reported_daily_man_day=stored.reported_daily_man_day,
        calculated_daily_man_day=stored.calculated_daily_man_day,
        confirmed_daily_man_day=stored.confirmed_daily_man_day,
        man_day_confirmed=stored.man_day_confirmed,
        reported_cumulative_man_day=stored.reported_cumulative_man_day,
        calculated_cumulative_man_day=stored.calculated_cumulative_man_day,
        confirmed_cumulative_man_day=stored.confirmed_cumulative_man_day,
        cumulative_series_key=stored.cumulative_series_key,
        issue_codes=stored.issue_codes,
        review_status=stored.review_status,
        included=stored.included,
        warning_confirmed=stored.warning_confirmed,
        resolution_note=stored.resolution_note,
        deleted_at=stored.deleted_at,
    )


def final_report_row_from_stored(stored: StoredFinalReportRow) -> FinalReportRow:
    return FinalReportRow(
        source_row_id=stored.source_row_id,
        work_date=stored.work_date,
        vendor_name=stored.vendor_name,
        vendor_sort_order=stored.vendor_sort_order,
        tracking_no=stored.tracking_no,
        equipment_name=stored.equipment_name,
        business_team=stored.business_team,
        actual_headcount=stored.actual_headcount,
        night_headcount=stored.night_headcount,
        man_day_basis=stored.man_day_basis,
        confirmed_daily_man_day=stored.confirmed_daily_man_day,
        confirmed_cumulative_man_day=stored.confirmed_cumulative_man_day,
        source_row_ids=stored.source_row_ids,
    )


def final_report_snapshot_from_stored(
    stored: StoredFinalReport,
) -> FinalReportSnapshot:
    return FinalReportSnapshot(
        report_id=stored.report_id,
        date_from=stored.date_from,
        date_to=stored.date_to,
        snapshot_hash=stored.snapshot_hash,
        confirmed_at=stored.confirmed_at,
        copied_at=stored.copied_at,
        invalidated_at=stored.invalidated_at,
        rows=tuple(final_report_row_from_stored(row) for row in stored.rows),
    )
