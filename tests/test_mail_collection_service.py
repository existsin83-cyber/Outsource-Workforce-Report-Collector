from __future__ import annotations

from datetime import date, datetime

import pytest
import pywintypes

from outsource_mail_collector.application.mail_collection_service import (
    MailCollectionService,
)
from outsource_mail_collector.domain.models import MailEnvelope, MailRecord
from outsource_mail_collector.infrastructure.db.repository import SQLiteRepository


@pytest.fixture
def repository(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    repository.save_employee(None, "홍길동", "hong@example.com", [], True)
    repository.save_employee(None, "김철수", "kim@example.com", [], True)
    return repository


def test_collect_filters_registered_senders_and_reports_missing(repository):
    outlook = FakeOutlookAdapter(
        envelopes=[
            _envelope("ENTRY-HONG", "HONG@EXAMPLE.COM"),
            _envelope("ENTRY-OTHER", "other@example.com"),
        ]
    )

    result = MailCollectionService(repository, outlook).collect(
        date(2026, 7, 24), "Inbox"
    )

    assert [mail.mail_id for mail in result.mails] == ["ENTRY-HONG"]
    assert [employee.name for employee in result.missing_employees] == ["김철수"]
    assert result.errors == ()
    assert outlook.last_range == (
        datetime(2026, 7, 24, 0, 0),
        datetime(2026, 7, 25, 0, 0),
    )


def test_collect_with_no_active_employees_does_not_read_outlook(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    outlook = FakeOutlookAdapter(envelopes=[_envelope("ENTRY-1", "user@example.com")])

    result = MailCollectionService(repository, outlook).collect(
        date(2026, 7, 24), "Inbox"
    )

    assert result.mails == ()
    assert result.missing_employees == ()
    assert result.errors[0].code == "NO_ACTIVE_EMPLOYEES"
    assert outlook.list_call_count == 0


def test_collect_continues_after_one_message_fails(repository):
    outlook = FakeOutlookAdapter(
        envelopes=[
            _envelope("ENTRY-HONG", "hong@example.com"),
            _envelope("ENTRY-KIM", "kim@example.com"),
        ],
        failing_ids={"ENTRY-HONG"},
    )

    result = MailCollectionService(repository, outlook).collect(
        date(2026, 7, 24), "Inbox"
    )

    assert [mail.mail_id for mail in result.mails] == ["ENTRY-KIM"]
    assert result.missing_employees == ()
    assert len(result.errors) == 1
    assert result.errors[0].mail_id == "ENTRY-HONG"
    assert result.errors[0].code == "MAIL_OPEN_FAILED"


def test_collect_continues_after_one_message_raises_com_error(repository):
    outlook = FakeOutlookAdapter(
        envelopes=[
            _envelope("ENTRY-HONG", "hong@example.com"),
            _envelope("ENTRY-KIM", "kim@example.com"),
        ],
        failing_exceptions={
            "ENTRY-HONG": pywintypes.com_error(
                -1, "Outlook item is unavailable", None, None
            )
        },
    )

    result = MailCollectionService(repository, outlook).collect(
        date(2026, 7, 24), "Inbox"
    )

    assert [mail.mail_id for mail in result.mails] == ["ENTRY-KIM"]
    assert result.errors[0].mail_id == "ENTRY-HONG"
    assert result.errors[0].code == "MAIL_OPEN_FAILED"


class FakeOutlookAdapter:
    def __init__(
        self,
        envelopes: list[MailEnvelope],
        failing_ids: set[str] | None = None,
        failing_exceptions: dict[str, Exception] | None = None,
    ) -> None:
        self.envelopes = envelopes
        self.failing_ids = failing_ids or set()
        self.failing_exceptions = failing_exceptions or {}
        self.list_call_count = 0
        self.last_range: tuple[datetime, datetime] | None = None

    def connect(self) -> None:
        return None

    def list_messages(
        self, folder_path: str, start_at: datetime, end_at: datetime
    ) -> list[MailEnvelope]:
        self.list_call_count += 1
        self.last_range = (start_at, end_at)
        return self.envelopes

    def open_message(self, entry_id: str) -> MailRecord:
        if exception := self.failing_exceptions.get(entry_id):
            raise exception
        if entry_id in self.failing_ids:
            raise RuntimeError("본문을 읽을 수 없습니다.")
        envelope = next(row for row in self.envelopes if row.mail_id == entry_id)
        return MailRecord(
            mail_id=envelope.mail_id,
            subject=envelope.subject,
            sender_name=envelope.sender_name,
            sender_email=envelope.sender_email.lower(),
            received_at=envelope.received_at,
            report_date=envelope.received_at.date(),
            body_text="본문",
            body_html="",
            source_folder="Inbox",
        )


def _envelope(mail_id: str, sender_email: str) -> MailEnvelope:
    return MailEnvelope(
        mail_id=mail_id,
        subject="업무보고",
        sender_name=sender_email.split("@")[0],
        sender_email=sender_email,
        received_at=datetime(2026, 7, 24, 18, 0),
    )
