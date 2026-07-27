"""Plain application DTOs shared between services and the presentation layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from outsource_mail_collector.domain.models import MailRecord, ReviewStatus
from outsource_mail_collector.infrastructure.db.repository import (
    Employee,
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
    report_date: date
    sender_name: str
    sender_email: str
    equipment_name: str | None
    tracking_no: str | None
    vendor_name: str | None
    actual_headcount: float | None
    daily_man_day: float | None
    cumulative_man_day: float | None
    confidence: float
    review_status: ReviewStatus
    note: str | None


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
        daily_man_day=stored.daily_man_day,
        cumulative_man_day=stored.cumulative_man_day,
        confidence=stored.confidence,
        review_status=stored.review_status,
        note=stored.note,
    )
