from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from threading import Event, Thread

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


def test_repository_connections_enable_wal_and_bounded_busy_timeout(repository):
    with repository._open_connection() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 10_000


def test_repository_write_waits_for_immediate_transaction_lock(tmp_path, monkeypatch):
    db_path = tmp_path / "collector.db"
    repository = SQLiteRepository(db_path)
    lock_acquired = Event()
    release_lock = Event()
    write_started = Event()
    write_attempted = Event()
    write_finished = Event()
    holder_errors: list[BaseException] = []
    writer_errors: list[BaseException] = []

    real_open_connection = repository_module._open_sqlite_connection

    def observe_writer_connection(path):
        conn = real_open_connection(path)

        def trace(statement: str) -> None:
            if statement.lstrip().upper().startswith("INSERT INTO SETTINGS"):
                write_attempted.set()

        conn.set_trace_callback(trace)
        return conn

    monkeypatch.setattr(
        repository_module, "_open_sqlite_connection", observe_writer_connection
    )

    def hold_write_lock() -> None:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            lock_acquired.set()
            if not release_lock.wait(timeout=1):
                holder_errors.append(TimeoutError("test did not release write lock"))
        except BaseException as error:
            holder_errors.append(error)
        finally:
            conn.rollback()
            conn.close()

    def write_setting() -> None:
        try:
            write_started.set()
            repository.set_setting("outlook_folder", "Inbox")
        except BaseException as error:
            writer_errors.append(error)
        finally:
            write_finished.set()

    lock_holder = Thread(target=hold_write_lock)
    writer = Thread(target=write_setting)
    lock_holder.start()
    try:
        assert lock_acquired.wait(timeout=1)
        writer.start()
        assert write_started.wait(timeout=1)
        assert write_attempted.wait(timeout=1)
        assert not write_finished.is_set()
        release_lock.set()
        assert write_finished.wait(timeout=1)
    finally:
        release_lock.set()
        writer.join(timeout=1)
        lock_holder.join(timeout=1)

    assert not writer.is_alive()
    assert not lock_holder.is_alive()
    assert holder_errors == []
    assert writer_errors == []
    assert repository.get_setting("outlook_folder") == "Inbox"


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


def test_work_order_mapping_round_trip_normalizes_tracking(repository):
    vendor = repository.save_vendor(None, "협력사A", [], True)

    mapping = repository.save_work_order_mapping(
        None,
        tracking_no=" ab 260101 ",
        equipment_name="장비 Alpha #1",
        vendor_id=vendor.vendor_id,
        business_team="PKG",
        active=True,
    )

    assert mapping.normalized_tracking_no == "AB260101"
    assert mapping.vendor_name == "협력사A"
    assert repository.list_work_order_mappings() == [mapping]


def test_duplicate_active_work_order_tracking_is_rejected(repository):
    vendor = repository.save_vendor(None, "협력사A", [], True)
    repository.save_work_order_mapping(
        None, "AB260101", "장비 1", vendor.vendor_id, "PKG", True
    )

    with pytest.raises(DuplicateEntityError):
        repository.save_work_order_mapping(
            None, " ab 260101 ", "장비 2", vendor.vendor_id, "WA", True
        )


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
        work_report_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(work_report_rows)")
        }
        final_report_columns = {
            row[1]: (row[2], row[3])
            for row in conn.execute("PRAGMA table_info(final_report_rows)")
        }
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        indexes = {
            row[1]
            for row in conn.execute(
                "SELECT type, name FROM sqlite_master WHERE type = 'index'"
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
    assert {
        "work_order_mappings",
        "cumulative_baselines",
        "work_report_rows",
        "final_reports",
        "final_report_rows",
    } <= tables
    assert "night_headcount" in work_report_columns
    assert "deleted_at" in work_report_columns
    assert "night_headcount" in final_report_columns
    assert final_report_columns["per_person_man_day"] == ("TEXT", 1)
    assert {
        "idx_extracted_records_mail_entry",
        "idx_extracted_records_report_date",
        "idx_work_report_deleted_date",
        "idx_work_report_tracking_date",
        "idx_final_reports_invalidated",
    } <= indexes


def test_cumulative_baseline_round_trip_normalizes_quantizes_and_audits(
    repository,
):
    created = repository.save_cumulative_baseline(
        tracking_no=" ab 260101 ",
        effective_through_date=date(2026, 7, 28),
        cumulative_man_day=Decimal("10.04"),
        resolution_note="legacy total checked",
    )
    updated = repository.save_cumulative_baseline(
        tracking_no="AB260101",
        effective_through_date=date(2026, 7, 29),
        cumulative_man_day=Decimal("12.25"),
        resolution_note="effective date corrected",
    )

    assert created.tracking_no == "ab 260101"
    assert created.normalized_tracking_no == "AB260101"
    assert created.cumulative_man_day == Decimal("10.0")
    assert updated.normalized_tracking_no == "AB260101"
    assert updated.effective_through_date == date(2026, 7, 29)
    assert updated.cumulative_man_day == Decimal("12.3")
    assert updated.created_at == created.created_at
    assert repository.get_cumulative_baseline(" a b 2 6 0 1 0 1 ") == updated
    assert repository.list_cumulative_baselines() == [updated]
    assert [log.action for log in repository.list_action_logs()] == [
        "CUMULATIVE_BASELINE_SAVED",
        "CUMULATIVE_BASELINE_SAVED",
    ]
    assert [
        json.loads(log.after_json or "{}")["resolution_note"]
        for log in repository.list_action_logs()
    ] == ["legacy total checked", "effective date corrected"]


def test_legacy_work_rows_are_backfilled_by_tracking_without_data_loss(
    tmp_path,
):
    db_path = tmp_path / "legacy.db"
    _create_legacy_work_report_db(db_path)

    first_open = SQLiteRepository(db_path)
    second_open = SQLiteRepository(db_path)

    rows = sorted(
        second_open.list_all_work_report_rows(include_deleted=True),
        key=lambda row: row.row_id,
    )
    assert first_open.db_path == second_open.db_path
    assert [row.row_id for row in rows] == [1, 2, 3]
    assert [row.cumulative_series_key for row in rows] == [
        "AB260101",
        None,
        None,
    ]
    assert rows[0].issue_codes == (WorkReportIssueCode.DAILY_MISSING,)
    assert rows[1].issue_codes == (WorkReportIssueCode.SERIES_KEY_MISSING,)
    assert rows[2].issue_codes == (
        WorkReportIssueCode.DATE_UNRESOLVED,
        WorkReportIssueCode.SERIES_KEY_MISSING,
    )
    migrated_report = second_open.get_final_report(1)
    assert migrated_report.invalidated_at is not None
    assert [row.source_row_id for row in migrated_report.rows] == [1]
    migration_logs = [
        log
        for log in second_open.list_action_logs()
        if log.action == "WORK_REPORT_SERIES_BACKFILLED"
    ]
    assert len(migration_logs) == 1
    assert json.loads(migration_logs[0].after_json or "{}")["row_ids"] == [
        1,
        2,
        3,
    ]


def test_final_report_row_sources_table_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "collector.db"

    SQLiteRepository(db_path)
    SQLiteRepository(db_path)

    with sqlite3.connect(db_path) as conn:
        table_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE type = 'table' AND name = 'final_report_row_sources'
            """
        ).fetchone()[0]
        columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(final_report_row_sources)"
            ).fetchall()
        }
    assert table_count == 1
    assert columns == {"snapshot_row_id", "source_row_id"}


def test_work_order_mapping_mutations_invalidate_snapshots_and_are_audited(
    repository,
):
    first_vendor = repository.save_vendor(None, "업체A", [], True)
    second_vendor = repository.save_vendor(None, "업체B", [], True)
    source = _complete_report_row(repository, date(2026, 7, 29))

    created_snapshot = repository.create_final_report_snapshot(
        date_from=date(2026, 7, 29),
        date_to=date(2026, 7, 29),
        rows=[source],
        snapshot_hash="before-mapping-create",
    )
    mapping = repository.save_work_order_mapping(
        None,
        "AB260101",
        "장비 1",
        first_vendor.vendor_id,
        "WA",
        True,
    )
    assert (
        repository.get_final_report(created_snapshot.report_id).invalidated_at
        is not None
    )

    updated_snapshot = repository.create_final_report_snapshot(
        date_from=date(2026, 7, 29),
        date_to=date(2026, 7, 29),
        rows=[source],
        snapshot_hash="before-mapping-update",
    )
    mapping = repository.save_work_order_mapping(
        mapping.mapping_id,
        "AB260101",
        "장비 2",
        second_vendor.vendor_id,
        "WB",
        True,
    )
    assert (
        repository.get_final_report(updated_snapshot.report_id).invalidated_at
        is not None
    )

    deactivated_snapshot = repository.create_final_report_snapshot(
        date_from=date(2026, 7, 29),
        date_to=date(2026, 7, 29),
        rows=[source],
        snapshot_hash="before-mapping-deactivate",
    )
    mapping = repository.save_work_order_mapping(
        mapping.mapping_id,
        mapping.tracking_no,
        mapping.equipment_name,
        mapping.vendor_id,
        mapping.business_team,
        False,
    )
    assert (
        repository.get_final_report(
            deactivated_snapshot.report_id
        ).invalidated_at
        is not None
    )

    deleted_snapshot = repository.create_final_report_snapshot(
        date_from=date(2026, 7, 29),
        date_to=date(2026, 7, 29),
        rows=[source],
        snapshot_hash="before-mapping-delete",
    )
    repository.delete_work_order_mapping(mapping.mapping_id)
    assert (
        repository.get_final_report(deleted_snapshot.report_id).invalidated_at
        is not None
    )

    mapping_logs = [
        log
        for log in repository.list_action_logs()
        if log.action.startswith("WORK_ORDER_MAPPING_")
    ]
    assert [log.action for log in mapping_logs] == [
        "WORK_ORDER_MAPPING_SAVED",
        "WORK_ORDER_MAPPING_SAVED",
        "WORK_ORDER_MAPPING_SAVED",
        "WORK_ORDER_MAPPING_DELETED",
    ]
    assert mapping_logs[0].before_json is None
    assert json.loads(mapping_logs[0].after_json or "{}")["active"] is True
    assert json.loads(mapping_logs[1].before_json or "{}")[
        "equipment_name"
    ] == "장비 1"
    assert json.loads(mapping_logs[1].after_json or "{}")[
        "equipment_name"
    ] == "장비 2"
    assert json.loads(mapping_logs[2].after_json or "{}")["active"] is False
    assert json.loads(mapping_logs[3].before_json or "{}")[
        "mapping_id"
    ] == mapping.mapping_id
    assert mapping_logs[3].after_json is None


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
        night_headcount=1,
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
    assert first.night_headcount == 1
    assert first.reported_daily_man_day == Decimal("4.0")
    assert first.calculated_daily_man_day == Decimal("3.0")
    assert first.issue_codes == (WorkReportIssueCode.DAILY_MISMATCH,)

    updated = repository.update_work_report_row(
        first.row_id,
        {"night_headcount": 0},
        resolution_note="야근 인원 확인",
    )
    assert updated.night_headcount == 0


def test_confirmation_and_snapshot_are_audited_and_immutable(repository):
    row = repository.create_manual_report_row(
        work_date=date(2026, 7, 29),
        work_date_confirmed=True,
        vendor_name="업체A",
        tracking_no="AB260101",
        equipment_name="장비 1",
        business_team="WA",
        actual_headcount=2,
        night_headcount=2,
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


def test_soft_delete_restore_filters_active_rows_and_invalidates_snapshot(
    repository,
):
    row = _complete_report_row(repository, date(2026, 7, 29))
    report = repository.create_final_report_snapshot(
        date_from=date(2026, 7, 29),
        date_to=date(2026, 7, 29),
        rows=[row],
        snapshot_hash="before-delete",
    )

    deleted = repository.soft_delete_work_report_row(
        row.row_id, resolution_note="잘못 추가한 행"
    )

    assert deleted.deleted_at is not None
    assert repository.list_work_report_rows(
        date(2026, 7, 29), date(2026, 7, 29)
    ) == []
    assert repository.list_work_report_rows(
        date(2026, 7, 29),
        date(2026, 7, 29),
        include_deleted=True,
    ) == [deleted]
    assert repository.get_final_report(report.report_id).invalidated_at is not None

    restored = repository.restore_work_report_row(
        row.row_id, resolution_note="삭제 취소"
    )

    assert restored.deleted_at is None
    assert repository.list_work_report_rows(
        date(2026, 7, 29), date(2026, 7, 29)
    ) == [restored]
    assert [log.action for log in repository.list_action_logs()][-2:] == [
        "WORK_REPORT_ROW_SOFT_DELETED",
        "WORK_REPORT_ROW_RESTORED",
    ]


def test_new_manual_work_report_row_invalidates_existing_snapshot(repository):
    row = _complete_report_row(repository, date(2026, 7, 29))
    report = repository.create_final_report_snapshot(
        date_from=date(2026, 7, 29),
        date_to=date(2026, 7, 29),
        rows=[row],
        snapshot_hash="before-new-row",
    )

    _complete_report_row(repository, date(2026, 7, 30))

    assert repository.get_final_report(report.report_id).invalidated_at is not None


def test_new_mail_work_report_row_invalidates_existing_snapshot(repository):
    row = _complete_report_row(repository, date(2026, 7, 29))
    report = repository.create_final_report_snapshot(
        date_from=date(2026, 7, 29),
        date_to=date(2026, 7, 29),
        rows=[row],
        snapshot_hash="before-mail-row",
    )

    repository.get_or_create_mail_report_row(
        extracted_record_id=99,
        mail_entry_id="ENTRY-99",
        **_complete_report_values(date(2026, 7, 30)),
    )

    assert repository.get_final_report(report.report_id).invalidated_at is not None


def _complete_report_row(repository, work_date: date):
    return repository.create_manual_report_row(**_complete_report_values(work_date))


def _complete_report_values(work_date: date) -> dict[str, object]:
    return dict(
        work_date=work_date,
        work_date_confirmed=True,
        vendor_name="업체A",
        tracking_no="AB260101",
        equipment_name="장비 1",
        business_team="WA",
        actual_headcount=2,
        night_headcount=2,
        per_person_man_day=Decimal("1.5"),
        reported_daily_man_day=Decimal("3.0"),
        calculated_daily_man_day=Decimal("3.0"),
        confirmed_daily_man_day=Decimal("3.0"),
        reported_cumulative_man_day=Decimal("13.0"),
        calculated_cumulative_man_day=Decimal("13.0"),
        confirmed_cumulative_man_day=Decimal("13.0"),
        cumulative_series_key="AB260101",
        issue_codes=(),
        review_status=ReviewStatus.REVIEWED,
        included=True,
        resolution_note="확정",
    )


def _create_legacy_work_report_db(db_path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE work_report_rows (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                extracted_record_id INTEGER,
                mail_entry_id TEXT,
                work_date TEXT,
                work_date_confirmed INTEGER NOT NULL DEFAULT 0,
                vendor_name TEXT,
                tracking_no TEXT,
                equipment_name TEXT,
                business_team TEXT,
                actual_headcount INTEGER,
                night_headcount INTEGER,
                per_person_man_day TEXT,
                reported_daily_man_day TEXT,
                calculated_daily_man_day TEXT,
                confirmed_daily_man_day TEXT,
                reported_cumulative_man_day TEXT,
                calculated_cumulative_man_day TEXT,
                confirmed_cumulative_man_day TEXT,
                cumulative_series_key TEXT,
                issue_codes_json TEXT NOT NULL DEFAULT '[]',
                review_status TEXT NOT NULL,
                included INTEGER NOT NULL DEFAULT 1,
                warning_confirmed INTEGER NOT NULL DEFAULT 0,
                resolution_note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        common = {
            "source_type": "MANUAL",
            "extracted_record_id": None,
            "mail_entry_id": None,
            "work_date": "2026-07-30",
            "work_date_confirmed": 1,
            "vendor_name": "Legacy Vendor",
            "tracking_no": " ab 260101 ",
            "equipment_name": "Legacy Equipment",
            "business_team": "WA",
            "actual_headcount": 2,
            "night_headcount": 2,
            "per_person_man_day": "1.5",
            "reported_daily_man_day": "3.0",
            "calculated_daily_man_day": "3.0",
            "confirmed_daily_man_day": "3.0",
            "reported_cumulative_man_day": None,
            "calculated_cumulative_man_day": None,
            "confirmed_cumulative_man_day": None,
            "cumulative_series_key": "legacy vendor|T:AB260101",
            "issue_codes_json": json.dumps(
                [WorkReportIssueCode.DAILY_MISSING.value]
            ),
            "review_status": ReviewStatus.NORMAL.value,
            "included": 1,
            "warning_confirmed": 0,
            "resolution_note": "legacy row",
            "created_at": "2026-07-30T00:00:00+00:00",
            "updated_at": "2026-07-30T00:00:00+00:00",
        }
        missing_tracking = {
            **common,
            "tracking_no": None,
            "cumulative_series_key": "legacy vendor|E:legacy equipment",
            "issue_codes_json": "[]",
        }
        unresolved_missing_tracking = {
            **missing_tracking,
            "work_date": None,
            "tracking_no": "",
            "cumulative_series_key": None,
            "issue_codes_json": json.dumps(
                [WorkReportIssueCode.DATE_UNRESOLVED.value]
            ),
        }
        conn.executemany(
            """
            INSERT INTO work_report_rows(
                source_type, extracted_record_id, mail_entry_id,
                work_date, work_date_confirmed, vendor_name, tracking_no,
                equipment_name, business_team, actual_headcount,
                night_headcount, per_person_man_day, reported_daily_man_day,
                calculated_daily_man_day, confirmed_daily_man_day,
                reported_cumulative_man_day, calculated_cumulative_man_day,
                confirmed_cumulative_man_day, cumulative_series_key,
                issue_codes_json, review_status, included, warning_confirmed,
                resolution_note, created_at, updated_at
            )
            VALUES (
                :source_type, :extracted_record_id, :mail_entry_id,
                :work_date, :work_date_confirmed, :vendor_name, :tracking_no,
                :equipment_name, :business_team, :actual_headcount,
                :night_headcount, :per_person_man_day,
                :reported_daily_man_day, :calculated_daily_man_day,
                :confirmed_daily_man_day, :reported_cumulative_man_day,
                :calculated_cumulative_man_day,
                :confirmed_cumulative_man_day, :cumulative_series_key,
                :issue_codes_json, :review_status, :included,
                :warning_confirmed, :resolution_note, :created_at, :updated_at
            )
            """,
            [common, missing_tracking, unresolved_missing_tracking],
        )
        conn.executescript(
            """
            CREATE TABLE final_reports (
                report_id INTEGER PRIMARY KEY AUTOINCREMENT,
                date_from TEXT NOT NULL,
                date_to TEXT NOT NULL,
                snapshot_hash TEXT NOT NULL,
                confirmed_at TEXT NOT NULL,
                copied_at TEXT,
                invalidated_at TEXT
            );

            CREATE TABLE final_report_rows (
                snapshot_row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL REFERENCES final_reports(report_id),
                source_row_id INTEGER NOT NULL,
                work_date TEXT NOT NULL,
                vendor_name TEXT NOT NULL,
                vendor_sort_order INTEGER NOT NULL DEFAULT 0,
                tracking_no TEXT,
                equipment_name TEXT,
                business_team TEXT,
                actual_headcount INTEGER NOT NULL,
                night_headcount INTEGER,
                per_person_man_day TEXT NOT NULL,
                confirmed_daily_man_day TEXT NOT NULL,
                confirmed_cumulative_man_day TEXT NOT NULL
            );

            INSERT INTO final_reports(
                report_id, date_from, date_to, snapshot_hash, confirmed_at
            )
            VALUES (
                1, '2026-07-30', '2026-07-30', 'legacy-snapshot',
                '2026-07-30T01:00:00+00:00'
            );

            INSERT INTO final_report_rows(
                report_id, source_row_id, work_date, vendor_name,
                vendor_sort_order, tracking_no, equipment_name, business_team,
                actual_headcount, night_headcount, per_person_man_day,
                confirmed_daily_man_day, confirmed_cumulative_man_day
            )
            VALUES (
                1, 1, '2026-07-30', 'Legacy Vendor', 0, ' ab 260101 ',
                'Legacy Equipment', 'WA', 2, 2, '1.5', '3.0', '3.0'
            );
            """
        )


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
