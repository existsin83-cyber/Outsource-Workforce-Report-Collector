from __future__ import annotations

from datetime import date, datetime

import pytest

from fixtures import (
    DATE_BODY_CONFLICTING,
    DATE_SUBJECT_DOTTED,
    FORMAT_B_NUMBERED_VENDOR_PER_UNIT,
)
from outsource_mail_collector.application.extraction_orchestrator import (
    ExtractionOrchestrator,
)
from outsource_mail_collector.domain.models import MailRecord
from outsource_mail_collector.infrastructure.db.repository import SQLiteRepository


@pytest.fixture
def repository(tmp_path):
    return SQLiteRepository(tmp_path / "collector.db")


def test_process_parses_persists_and_returns_review_records(repository):
    mail = _mail_record("ENTRY-1", FORMAT_B_NUMBERED_VENDOR_PER_UNIT)

    result = ExtractionOrchestrator(repository).process([mail])

    assert result.errors == ()
    assert len(result.records) == 4
    assert repository.is_mail_processed(mail.mail_id)
    assert result.records[0].mail_entry_id == mail.mail_id
    assert result.records[0].sender_name == "홍길동"


def test_process_existing_entry_id_returns_saved_rows_without_duplicate(repository):
    mail = _mail_record("ENTRY-1", FORMAT_B_NUMBERED_VENDOR_PER_UNIT)
    first = ExtractionOrchestrator(repository).process([mail])

    second = ExtractionOrchestrator(repository).process([mail])

    assert second.skipped_mail_ids == ("ENTRY-1",)
    assert [row.record_id for row in second.records] == [
        row.record_id for row in first.records
    ]
    assert len(repository.list_review_records(date(2026, 7, 24))) == 4


def test_process_converts_vendor_alias_to_canonical_name(repository):
    repository.save_vendor(None, "정식협력사", ["협력사A"], True)
    mail = _mail_record("ENTRY-1", FORMAT_B_NUMBERED_VENDOR_PER_UNIT)

    result = ExtractionOrchestrator(repository).process([mail])

    assert {row.vendor_name for row in result.records} == {"정식협력사", "협력사B"}


def test_process_mail_without_outsource_marks_mail_processed_without_rows(repository):
    mail = _mail_record(
        "ENTRY-NONE",
        """\
1. 고객사A
.수주번호 : AB260101
.장비명 : 장비A
.작업내용 : 자체 인원 작업
""",
    )

    result = ExtractionOrchestrator(repository).process([mail])

    assert result.records == ()
    assert result.errors == ()
    assert repository.is_mail_processed(mail.mail_id)


def test_process_resolves_subject_date_before_persistence(repository):
    mail = _mail_record("ENTRY-DATE", FORMAT_B_NUMBERED_VENDOR_PER_UNIT).model_copy(
        update={
            "subject": DATE_SUBJECT_DOTTED,
            "report_date": None,
            "received_at": datetime(2026, 7, 30, 8, 0),
        }
    )

    result = ExtractionOrchestrator(repository).process([mail])

    assert result.errors == ()
    assert {row.report_date for row in result.records} == {date(2026, 7, 29)}


def test_process_preserves_date_mismatch_evidence_for_repository():
    repository = _CapturingRepository()
    body = f"{DATE_BODY_CONFLICTING}\n{FORMAT_B_NUMBERED_VENDOR_PER_UNIT}"
    mail = _mail_record("ENTRY-MISMATCH", body).model_copy(
        update={
            "subject": DATE_SUBJECT_DOTTED,
            "report_date": None,
            "received_at": datetime(2026, 7, 30, 8, 0),
        }
    )

    ExtractionOrchestrator(repository).process([mail])

    assert repository.mail is not None
    assert repository.mail.report_date == date(2026, 7, 29)
    assert repository.mail.body_report_date == date(2026, 7, 28)
    assert repository.mail.work_date_confirmed is False
    assert "DATE_MISMATCH" in repository.mail.date_issue_codes


def test_process_unresolved_date_keeps_review_rows_without_received_date_guess(
    repository,
):
    body = FORMAT_B_NUMBERED_VENDOR_PER_UNIT.replace(
        "7월 24일 금요일 일일 업무보고 드립니다.", "일일 업무보고 드립니다."
    )
    mail = _mail_record("ENTRY-UNRESOLVED", body).model_copy(
        update={
            "subject": "일일 업무보고",
            "report_date": None,
            "received_at": datetime(2026, 7, 30, 8, 0),
        }
    )

    result = ExtractionOrchestrator(repository).process([mail])

    assert result.errors == ()
    assert len(result.records) == 4
    assert {row.report_date for row in result.records} == {None}


class _CapturingRepository:
    def __init__(self) -> None:
        self.mail: MailRecord | None = None

    def is_mail_processed(self, mail_entry_id: str) -> bool:
        return False

    def list_vendors(self, active_only: bool = False) -> list:
        return []

    def store_extraction(self, mail: MailRecord, rows: list) -> list:
        self.mail = mail
        return []


def _mail_record(mail_id: str, body: str) -> MailRecord:
    return MailRecord(
        mail_id=mail_id,
        subject="업무보고",
        sender_name="홍길동",
        sender_email="hong@example.com",
        received_at=datetime(2026, 7, 24, 18, 0),
        report_date=date(2026, 7, 24),
        body_text=body,
        body_html="",
        source_folder="Inbox",
    )
