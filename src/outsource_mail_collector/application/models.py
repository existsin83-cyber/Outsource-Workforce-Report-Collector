"""Plain application DTOs shared between services and the presentation layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from outsource_mail_collector.domain.models import MailRecord, ReviewStatus
from outsource_mail_collector.infrastructure.db.repository import Employee


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
