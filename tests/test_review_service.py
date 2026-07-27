from __future__ import annotations

from datetime import date, datetime

import pytest

from outsource_mail_collector.application.errors import InvalidReviewValueError
from outsource_mail_collector.application.review_service import ReviewService
from outsource_mail_collector.domain.models import (
    EquipmentSection,
    MailRecord,
    OutsourceWorkRecord,
    ReviewStatus,
    ValidationResult,
)
from outsource_mail_collector.infrastructure.db.repository import SQLiteRepository


@pytest.fixture
def repository(tmp_path):
    return SQLiteRepository(tmp_path / "collector.db")


def test_update_numeric_field_logs_before_and_after(repository):
    record_id = _stored_record(repository)
    service = ReviewService(repository, FakeOutlookAdapter())

    updated = service.update_field(record_id, "actual_headcount", "3.5")

    assert updated.actual_headcount == 3.5
    log = repository.list_action_logs()[-1]
    assert log.action == "REVIEW_FIELD_UPDATED"
    assert '"actual_headcount": 2.0' in (log.before_json or "")
    assert '"actual_headcount": 3.5' in (log.after_json or "")


def test_invalid_numeric_edit_preserves_existing_value(repository):
    record_id = _stored_record(repository)
    service = ReviewService(repository, FakeOutlookAdapter())

    with pytest.raises(InvalidReviewValueError):
        service.update_field(record_id, "daily_man_day", "네 명")

    assert repository.get_review_record(record_id).daily_man_day == 4.0


def test_blank_text_becomes_none_and_uneditable_field_is_rejected(repository):
    record_id = _stored_record(repository)
    service = ReviewService(repository, FakeOutlookAdapter())

    updated = service.update_field(record_id, "vendor_name", "  ")

    assert updated.vendor_name is None
    with pytest.raises(InvalidReviewValueError):
        service.update_field(record_id, "confidence", "1")


def test_review_status_changes_are_limited_to_reviewed_and_excluded(repository):
    record_id = _stored_record(repository)
    service = ReviewService(repository, FakeOutlookAdapter())

    reviewed = service.set_status([record_id], ReviewStatus.REVIEWED)

    assert reviewed[0].review_status is ReviewStatus.REVIEWED
    with pytest.raises(InvalidReviewValueError):
        service.set_status([record_id], ReviewStatus.NORMAL)


def test_open_original_delegates_entry_id(repository):
    outlook = FakeOutlookAdapter()
    ReviewService(repository, outlook).open_original("ENTRY-1")

    assert outlook.displayed_ids == ["ENTRY-1"]


class FakeOutlookAdapter:
    def __init__(self) -> None:
        self.displayed_ids: list[str] = []

    def display_message(self, entry_id: str) -> None:
        self.displayed_ids.append(entry_id)


def _stored_record(repository: SQLiteRepository) -> int:
    mail = MailRecord(
        mail_id="ENTRY-1",
        subject="업무보고",
        sender_name="홍길동",
        sender_email="hong@example.com",
        received_at=datetime(2026, 7, 24, 18, 0),
        report_date=date(2026, 7, 24),
        body_text="본문",
        body_html="",
        source_folder="Inbox",
    )
    section = EquipmentSection(
        section_index=0,
        mail_id=mail.mail_id,
        tracking_no="XX260301",
        equipment_name="ABC-200 #2",
        section_text="장비 구간",
        split_confidence=0.9,
    )
    record = OutsourceWorkRecord(
        work_record_id="WORK-1",
        equipment_record_id="EQUIPMENT-1",
        vendor_name="협력사A",
        actual_headcount=2.0,
        daily_man_day=4.0,
        cumulative_man_day=18.5,
        confidence=0.95,
        review_status=ReviewStatus.NORMAL,
    )
    validation = ValidationResult(
        work_record_id=record.work_record_id,
        is_valid=True,
        issues=[],
        status=ReviewStatus.NORMAL,
    )
    return repository.store_extraction(mail, [(section, record, validation)])[0].record_id
