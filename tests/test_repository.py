from __future__ import annotations

import sqlite3
from datetime import date, datetime

import pytest

from outsource_mail_collector.domain.models import (
    EquipmentSection,
    MailRecord,
    OutsourceWorkRecord,
    ReviewStatus,
    ValidationResult,
)
from outsource_mail_collector.infrastructure.db.repository import (
    DuplicateEntityError,
    SQLiteRepository,
    default_db_path,
)


@pytest.fixture
def repository(tmp_path):
    return SQLiteRepository(tmp_path / "collector.db")


def test_default_db_path_uses_local_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert default_db_path() == tmp_path / "OutsourceMailCollector" / "collector.db"


def test_setting_round_trip(repository):
    repository.set_setting("outlook_folder", "Inbox/전장기술팀")

    assert repository.get_setting("outlook_folder") == "Inbox/전장기술팀"
    assert repository.get_setting("missing") is None


def test_employee_and_vendor_round_trip_normalizes_email(repository):
    employee = repository.save_employee(None, "홍길동", " USER@EXAMPLE.COM ", ["길동"], True)
    vendor = repository.save_vendor(None, "협력사A", ["A사"], True)

    assert employee.email == "user@example.com"
    assert repository.list_employees() == [employee]
    assert repository.list_vendors() == [vendor]


def test_duplicate_employee_email_and_vendor_name_are_rejected(repository):
    repository.save_employee(None, "홍길동", "user@example.com", [], True)
    repository.save_vendor(None, "협력사A", [], True)

    with pytest.raises(DuplicateEntityError):
        repository.save_employee(None, "다른 사람", "USER@example.com", [], True)
    with pytest.raises(DuplicateEntityError):
        repository.save_vendor(None, "협력사A", ["다른 별칭"], True)


def test_store_extraction_is_atomic_and_deduplicates_entry_id(repository):
    mail = _mail_record()
    section = _section(mail.mail_id)
    record = _work_record()
    validation = ValidationResult(
        work_record_id=record.work_record_id,
        is_valid=True,
        issues=[],
        status=ReviewStatus.NORMAL,
    )

    stored = repository.store_extraction(mail, [(section, record, validation)])

    assert repository.is_mail_processed(mail.mail_id)
    assert len(stored) == 1
    assert stored[0].mail_entry_id == mail.mail_id
    assert stored[0].equipment_name == "ABC-200 #2"
    assert stored[0].review_status is ReviewStatus.NORMAL

    with pytest.raises(DuplicateEntityError):
        repository.store_extraction(mail, [(section, record, validation)])

    assert len(repository.list_review_records(date(2026, 7, 24))) == 1


def test_failed_extraction_rolls_back_processed_mail(repository):
    mail = _mail_record()
    section = _section(mail.mail_id)
    broken_record = _work_record()
    broken_record.work_record_id = None  # type: ignore[assignment]
    validation = ValidationResult(
        work_record_id="broken",
        is_valid=False,
        issues=["broken"],
        status=ReviewStatus.FORMAT_UNSUPPORTED,
    )

    with pytest.raises((sqlite3.IntegrityError, ValueError)):
        repository.store_extraction(mail, [(section, broken_record, validation)])

    assert not repository.is_mail_processed(mail.mail_id)


def test_review_update_and_status_change_write_action_logs(repository):
    mail = _mail_record()
    section = _section(mail.mail_id)
    record = _work_record()
    validation = ValidationResult(
        work_record_id=record.work_record_id,
        is_valid=True,
        issues=[],
        status=ReviewStatus.NORMAL,
    )
    stored = repository.store_extraction(mail, [(section, record, validation)])[0]

    updated = repository.update_review_field(
        stored.record_id, "actual_headcount", 3.5, action="REVIEW_FIELD_UPDATED"
    )
    reviewed = repository.set_review_status(
        [stored.record_id], ReviewStatus.REVIEWED, action="REVIEW_STATUS_CHANGED"
    )

    assert updated.actual_headcount == 3.5
    assert reviewed[0].review_status is ReviewStatus.REVIEWED
    logs = repository.list_action_logs()
    assert [log.action for log in logs] == [
        "REVIEW_FIELD_UPDATED",
        "REVIEW_STATUS_CHANGED",
    ]
    assert '"actual_headcount": 2.0' in (logs[0].before_json or "")
    assert '"actual_headcount": 3.5' in (logs[0].after_json or "")


def _mail_record() -> MailRecord:
    return MailRecord(
        mail_id="ENTRY-1",
        subject="업무보고",
        sender_name="홍길동",
        sender_email="USER@EXAMPLE.COM",
        received_at=datetime(2026, 7, 24, 18, 0),
        report_date=date(2026, 7, 24),
        body_text="본문",
        body_html="",
        source_folder="Inbox",
    )


def _section(mail_id: str) -> EquipmentSection:
    return EquipmentSection(
        section_index=0,
        mail_id=mail_id,
        tracking_no="XX260301",
        equipment_name="ABC-200 #2",
        section_text="장비 구간",
        split_confidence=0.9,
    )


def _work_record() -> OutsourceWorkRecord:
    return OutsourceWorkRecord(
        work_record_id="WORK-1",
        equipment_record_id="EQUIPMENT-1",
        vendor_name="협력사A",
        actual_headcount=2,
        daily_man_day=4.0,
        cumulative_man_day=18.5,
        confidence=0.95,
        review_status=ReviewStatus.NORMAL,
    )
