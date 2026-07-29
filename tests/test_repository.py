from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal

import pytest

import outsource_mail_collector.infrastructure.db.repository as repository_module
from outsource_mail_collector.domain.models import (
    EquipmentSection,
    MailRecord,
    OutsourceWorkRecord,
    ReviewStatus,
    ValidationResult,
)
from outsource_mail_collector.domain.work_report import (
    RowSource,
    WorkReportIssueCode,
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


def test_repository_closes_connection_after_each_public_operation(
    monkeypatch, tmp_path
):
    opened = []
    real_connect = sqlite3.connect

    class TrackingConnection(sqlite3.Connection):
        closed = False

        def close(self):
            self.closed = True
            super().close()

    def tracking_connect(*args, **kwargs):
        kwargs["factory"] = TrackingConnection
        connection = real_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(repository_module.sqlite3, "connect", tracking_connect)
    repository = SQLiteRepository(tmp_path / "collector.db")

    repository.get_setting("outlook_folder")

    assert opened
    assert all(connection.closed for connection in opened)


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


def test_additive_migration_preserves_old_rows_and_is_idempotent(tmp_path):
    db_path = tmp_path / "old.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE vendors (
                vendor_id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_name TEXT NOT NULL UNIQUE,
                aliases_json TEXT,
                active INTEGER NOT NULL DEFAULT 1
            );
            INSERT INTO vendors(canonical_name, aliases_json, active)
            VALUES ('업체B', '[]', 1), ('업체A', '[]', 1);
            """
        )

    first = SQLiteRepository(db_path)
    second = SQLiteRepository(db_path)

    assert [vendor.canonical_name for vendor in second.list_vendors()] == [
        "업체B",
        "업체A",
    ]
    with sqlite3.connect(db_path) as conn:
        vendor_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(vendors)")
        }
        mail_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(processed_mails)")
        }
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert first.db_path == second.db_path
    assert "sort_order" in vendor_columns
    assert {
        "subject_report_date",
        "body_report_date",
        "report_date_source",
        "date_issue_codes_json",
        "work_date_confirmed",
    } <= mail_columns
    assert {"work_report_rows", "final_reports", "final_report_rows"} <= tables


def test_work_report_rows_round_trip_decimal_values_and_allow_duplicates(
    repository,
):
    common = dict(
        work_date=date(2026, 7, 29),
        work_date_confirmed=True,
        vendor_name="업체A",
        tracking_no="AB260101",
        equipment_name="장비 1",
        business_team="WA",
        actual_headcount=2,
        per_person_man_day=Decimal("1.5"),
        reported_daily_man_day=Decimal("4.0"),
        calculated_daily_man_day=Decimal("3.0"),
        confirmed_daily_man_day=None,
        reported_cumulative_man_day=Decimal("20.0"),
        calculated_cumulative_man_day=Decimal("19.0"),
        confirmed_cumulative_man_day=None,
        cumulative_series_key="업체a|T:AB260101",
        issue_codes=(WorkReportIssueCode.DAILY_MISMATCH,),
        review_status=ReviewStatus.NORMAL,
        included=True,
        resolution_note=None,
    )
    first = repository.get_or_create_mail_report_row(
        extracted_record_id=1,
        mail_entry_id="ENTRY-A",
        **common,
    )
    same = repository.get_or_create_mail_report_row(
        extracted_record_id=1,
        mail_entry_id="ENTRY-A",
        **common,
    )
    duplicate = repository.get_or_create_mail_report_row(
        extracted_record_id=2,
        mail_entry_id="ENTRY-B",
        **common,
    )
    manual = repository.create_manual_report_row(**common)

    assert same.row_id == first.row_id
    assert duplicate.row_id != first.row_id
    assert manual.source_type is RowSource.MANUAL
    assert manual.mail_entry_id is None
    assert first.reported_daily_man_day == Decimal("4.0")
    assert first.calculated_daily_man_day == Decimal("3.0")
    assert first.issue_codes == (WorkReportIssueCode.DAILY_MISMATCH,)


def test_confirmation_and_snapshot_are_audited_and_immutable(repository):
    row = repository.create_manual_report_row(
        work_date=date(2026, 7, 29),
        work_date_confirmed=True,
        vendor_name="업체A",
        tracking_no="AB260101",
        equipment_name="장비 1",
        business_team="WA",
        actual_headcount=2,
        per_person_man_day=Decimal("1.5"),
        reported_daily_man_day=None,
        calculated_daily_man_day=Decimal("3.0"),
        confirmed_daily_man_day=None,
        reported_cumulative_man_day=None,
        calculated_cumulative_man_day=Decimal("12.0"),
        confirmed_cumulative_man_day=None,
        cumulative_series_key="업체a|T:AB260101",
        issue_codes=(WorkReportIssueCode.DAILY_MISSING,),
        review_status=ReviewStatus.NORMAL,
        included=True,
        resolution_note=None,
    )
    confirmed = repository.confirm_work_report_row(
        row.row_id,
        confirmed_daily_man_day=Decimal("3.0"),
        confirmed_cumulative_man_day=Decimal("12.0"),
        resolution_note="계산값 확인",
    )
    report = repository.create_final_report_snapshot(
        date_from=date(2026, 7, 29),
        date_to=date(2026, 7, 29),
        rows=[confirmed],
        snapshot_hash="hash-1",
    )
    repository.update_work_report_row(
        row.row_id,
        {"confirmed_daily_man_day": Decimal("4.0")},
        resolution_note="정정",
    )
    repository.mark_final_report_copied(report.report_id)
    stored_report = repository.get_final_report(report.report_id)

    assert stored_report.rows[0].confirmed_daily_man_day == Decimal("3.0")
    assert stored_report.copied_at is not None
    assert [log.action for log in repository.list_action_logs()][-3:] == [
        "WORK_REPORT_ROW_CONFIRMED",
        "WORK_REPORT_ROW_UPDATED",
        "FINAL_REPORT_COPIED",
    ]


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
