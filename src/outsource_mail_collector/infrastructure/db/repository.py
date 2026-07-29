"""SQLite persistence for settings, collection results, and review history."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from importlib import resources
from pathlib import Path
from enum import Enum
from typing import Any, Iterator

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


class DuplicateEntityError(ValueError):
    """Raised when a unique employee, vendor, or mail identity already exists."""


@dataclass(frozen=True)
class Employee:
    employee_id: int
    name: str
    email: str
    aliases: tuple[str, ...]
    active: bool


@dataclass(frozen=True)
class Vendor:
    vendor_id: int
    canonical_name: str
    aliases: tuple[str, ...]
    active: bool
    sort_order: int


@dataclass(frozen=True)
class StoredReviewRecord:
    record_id: int
    mail_entry_id: str
    work_record_id: str
    equipment_record_id: str | None
    report_date: date | None
    sender_name: str
    sender_email: str
    tracking_no: str | None
    order_no: str | None
    project_name: str | None
    equipment_name: str | None
    unit_no: str | None
    business_team: str | None
    vendor_name: str | None
    actual_headcount: float | None
    day_headcount: float | None
    night_headcount: float | None
    per_person_man_day: float | None
    day_man_day: float | None
    night_man_day: float | None
    daily_man_day: float | None
    cumulative_man_day: float | None
    note: str | None
    confidence: float
    review_status: ReviewStatus
    raw_section: str
    date_issue_codes: tuple[str, ...]
    work_date_confirmed: bool


@dataclass(frozen=True)
class ActionLog:
    log_id: int
    action: str
    entity_id: str | None
    before_json: str | None
    after_json: str | None
    result: str | None
    error_message: str | None
    created_at: str


@dataclass(frozen=True)
class StoredWorkReportRow:
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
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class StoredFinalReportRow:
    snapshot_row_id: int
    report_id: int
    source_row_id: int
    work_date: date
    vendor_name: str
    vendor_sort_order: int
    tracking_no: str | None
    equipment_name: str | None
    business_team: str | None
    actual_headcount: int
    per_person_man_day: Decimal
    confirmed_daily_man_day: Decimal
    confirmed_cumulative_man_day: Decimal


@dataclass(frozen=True)
class StoredFinalReport:
    report_id: int
    date_from: date
    date_to: date
    snapshot_hash: str
    confirmed_at: str
    copied_at: str | None
    invalidated_at: str | None
    rows: tuple[StoredFinalReportRow, ...]


_MIGRATION_COLUMNS: dict[str, dict[str, str]] = {
    "processed_mails": {
        "sender_name": "TEXT",
        "subject_report_date": "TEXT",
        "body_report_date": "TEXT",
        "report_date_source": "TEXT",
        "date_issue_codes_json": "TEXT",
        "work_date_confirmed": "INTEGER NOT NULL DEFAULT 0",
    },
    "vendors": {
        "sort_order": "INTEGER NOT NULL DEFAULT 0",
    },
    "extracted_records": {
        "work_record_id": "TEXT",
        "equipment_record_id": "TEXT",
        "order_no": "TEXT",
        "project_name": "TEXT",
        "unit_no": "TEXT",
        "business_team": "TEXT",
        "day_headcount": "REAL",
        "night_headcount": "REAL",
        "per_person_man_day": "REAL",
        "day_man_day": "REAL",
        "night_man_day": "REAL",
        "note": "TEXT",
    },
}

_REVIEW_FIELDS = {
    "tracking_no",
    "equipment_name",
    "vendor_name",
    "actual_headcount",
    "daily_man_day",
    "cumulative_man_day",
}

_WORK_REPORT_UPDATE_FIELDS = {
    "work_date",
    "work_date_confirmed",
    "vendor_name",
    "tracking_no",
    "equipment_name",
    "business_team",
    "actual_headcount",
    "per_person_man_day",
    "reported_daily_man_day",
    "calculated_daily_man_day",
    "confirmed_daily_man_day",
    "reported_cumulative_man_day",
    "calculated_cumulative_man_day",
    "confirmed_cumulative_man_day",
    "cumulative_series_key",
    "issue_codes",
    "review_status",
    "included",
    "warning_confirmed",
}


def default_db_path() -> Path:
    """Return the persistent per-user database path."""

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        root = Path(local_app_data)
    else:
        root = Path.home() / "AppData" / "Local"
    return root / "OutsourceMailCollector" / "collector.db"


def init_db(db_path: Path) -> sqlite3.Connection:
    """Create or migrate the SQLite database and return an open connection."""

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    schema_sql = resources.files("outsource_mail_collector.infrastructure.db").joinpath(
        "schema.sql"
    ).read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    _apply_additive_migrations(conn)
    conn.commit()
    return conn


def _apply_additive_migrations(conn: sqlite3.Connection) -> None:
    for table, columns in _MIGRATION_COLUMNS.items():
        existing = {
            row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for column, definition in columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    conn.execute(
        """
        UPDATE vendors
        SET sort_order = vendor_id
        WHERE sort_order = 0
        """
    )


class SQLiteRepository:
    """Short-lived-connection repository safe to call from UI and worker threads."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        init_db(self.db_path).close()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def get_setting(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return None if row is None else str(row["value"])

    def set_setting(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO settings(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, _utc_now()),
            )

    def list_employees(self, active_only: bool = False) -> list[Employee]:
        sql = "SELECT * FROM employees"
        parameters: tuple[Any, ...] = ()
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY employee_id"
        with self._connect() as conn:
            rows = conn.execute(sql, parameters).fetchall()
        return [_employee_from_row(row) for row in rows]

    def save_employee(
        self,
        employee_id: int | None,
        name: str,
        email: str,
        aliases: list[str] | tuple[str, ...],
        active: bool,
    ) -> Employee:
        normalized_name = name.strip()
        normalized_email = email.strip().lower()
        if not normalized_name or not normalized_email:
            raise ValueError("직원 이름과 이메일은 필수입니다.")
        aliases_json = _aliases_json(aliases)
        try:
            with self._connect() as conn:
                if employee_id is None:
                    cursor = conn.execute(
                        """
                        INSERT INTO employees(name, email, active, aliases_json)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            normalized_name,
                            normalized_email,
                            int(active),
                            aliases_json,
                        ),
                    )
                    employee_id = int(cursor.lastrowid)
                else:
                    cursor = conn.execute(
                        """
                        UPDATE employees
                        SET name = ?, email = ?, active = ?, aliases_json = ?
                        WHERE employee_id = ?
                        """,
                        (
                            normalized_name,
                            normalized_email,
                            int(active),
                            aliases_json,
                            employee_id,
                        ),
                    )
                    if cursor.rowcount == 0:
                        raise KeyError(employee_id)
        except sqlite3.IntegrityError as exc:
            raise DuplicateEntityError("이미 등록된 직원 이메일입니다.") from exc
        return Employee(
            employee_id,
            normalized_name,
            normalized_email,
            _aliases_from_json(aliases_json),
            active,
        )

    def delete_employee(self, employee_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM employees WHERE employee_id = ?", (employee_id,))

    def list_vendors(self, active_only: bool = False) -> list[Vendor]:
        sql = "SELECT * FROM vendors"
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY sort_order, vendor_id"
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [_vendor_from_row(row) for row in rows]

    def save_vendor(
        self,
        vendor_id: int | None,
        canonical_name: str,
        aliases: list[str] | tuple[str, ...],
        active: bool,
    ) -> Vendor:
        normalized_name = canonical_name.strip()
        if not normalized_name:
            raise ValueError("업체 표준명은 필수입니다.")
        aliases_json = _aliases_json(aliases)
        try:
            with self._connect() as conn:
                if vendor_id is None:
                    next_sort_order = int(
                        conn.execute(
                            "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM vendors"
                        ).fetchone()[0]
                    )
                    cursor = conn.execute(
                        """
                        INSERT INTO vendors(
                            canonical_name, aliases_json, active, sort_order
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            normalized_name,
                            aliases_json,
                            int(active),
                            next_sort_order,
                        ),
                    )
                    vendor_id = int(cursor.lastrowid)
                else:
                    cursor = conn.execute(
                        """
                        UPDATE vendors
                        SET canonical_name = ?, aliases_json = ?, active = ?
                        WHERE vendor_id = ?
                        """,
                        (normalized_name, aliases_json, int(active), vendor_id),
                    )
                    if cursor.rowcount == 0:
                        raise KeyError(vendor_id)
        except sqlite3.IntegrityError as exc:
            raise DuplicateEntityError("이미 등록된 업체명입니다.") from exc
        return Vendor(
            vendor_id,
            normalized_name,
            _aliases_from_json(aliases_json),
            active,
            self._vendor_sort_order(vendor_id),
        )

    def _vendor_sort_order(self, vendor_id: int) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT sort_order FROM vendors WHERE vendor_id = ?",
                (vendor_id,),
            ).fetchone()
        if row is None:
            raise KeyError(vendor_id)
        return int(row["sort_order"])

    def delete_vendor(self, vendor_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM vendors WHERE vendor_id = ?", (vendor_id,))

    def is_mail_processed(self, mail_entry_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM processed_mails WHERE mail_entry_id = ?",
                (mail_entry_id,),
            ).fetchone()
        return row is not None

    def store_extraction(
        self,
        mail: MailRecord,
        rows: list[
            tuple[EquipmentSection, OutsourceWorkRecord, ValidationResult]
        ],
    ) -> list[StoredReviewRecord]:
        if any(not record.work_record_id for _, record, _ in rows):
            raise ValueError("work_record_id는 필수입니다.")

        now = _utc_now()
        content_hash = hashlib.sha256(mail.body_text.encode("utf-8")).hexdigest()
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO processed_mails(
                        mail_entry_id, subject, sender_name, sender_email,
                        received_at, report_date, content_hash, status, processed_at,
                        subject_report_date, body_report_date, report_date_source,
                        date_issue_codes_json, work_date_confirmed
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mail.mail_id,
                        mail.subject,
                        mail.sender_name,
                        mail.sender_email.strip().lower(),
                        mail.received_at.isoformat(),
                        _date_to_db(mail.report_date),
                        content_hash,
                        "처리 완료",
                        now,
                        _date_to_db(mail.subject_report_date),
                        _date_to_db(mail.body_report_date),
                        mail.report_date_source.value,
                        json.dumps(mail.date_issue_codes, ensure_ascii=False),
                        int(mail.work_date_confirmed),
                    ),
                )
                record_ids = [
                    self._insert_extracted_record(
                        conn, mail, section, record, validation, now
                    )
                    for section, record, validation in rows
                ]
        except sqlite3.IntegrityError as exc:
            if self.is_mail_processed(mail.mail_id):
                raise DuplicateEntityError("이미 처리된 메일입니다.") from exc
            raise
        return [self.get_review_record(record_id) for record_id in record_ids]

    def _insert_extracted_record(
        self,
        conn: sqlite3.Connection,
        mail: MailRecord,
        section: EquipmentSection,
        record: OutsourceWorkRecord,
        validation: ValidationResult,
        now: str,
    ) -> int:
        cursor = conn.execute(
            """
            INSERT INTO extracted_records(
                mail_entry_id, work_record_id, equipment_record_id,
                report_date, sender_email, tracking_no, order_no, project_name,
                equipment_name, unit_no, business_team, vendor_name,
                actual_headcount, day_headcount, night_headcount,
                per_person_man_day, day_man_day, night_man_day,
                daily_man_day, cumulative_man_day, note, confidence,
                review_status, raw_section, created_at, updated_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?
            )
            """,
            (
                mail.mail_id,
                record.work_record_id,
                record.equipment_record_id,
                _date_to_db(mail.report_date),
                mail.sender_email.strip().lower(),
                section.tracking_no,
                section.order_no,
                section.project_name,
                section.equipment_name,
                section.unit_no,
                section.business_team,
                record.vendor_name,
                record.actual_headcount,
                record.day_headcount,
                record.night_headcount,
                record.per_person_man_day,
                record.day_man_day,
                record.night_man_day,
                record.daily_man_day,
                record.cumulative_man_day,
                record.note,
                record.confidence,
                validation.status.value,
                section.section_text,
                now,
                now,
            ),
        )
        return int(cursor.lastrowid)

    def list_review_records(
        self,
        report_date: date | None = None,
        mail_entry_id: str | None = None,
    ) -> list[StoredReviewRecord]:
        sql = _REVIEW_SELECT
        conditions: list[str] = []
        parameters: list[Any] = []
        if report_date is not None:
            conditions.append("er.report_date = ?")
            parameters.append(report_date.isoformat())
        if mail_entry_id is not None:
            conditions.append("er.mail_entry_id = ?")
            parameters.append(mail_entry_id)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY er.record_id"
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(parameters)).fetchall()
        return [_review_from_row(row) for row in rows]

    def get_review_record(self, record_id: int) -> StoredReviewRecord:
        with self._connect() as conn:
            row = conn.execute(
                _REVIEW_SELECT + " WHERE er.record_id = ?", (record_id,)
            ).fetchone()
        if row is None:
            raise KeyError(record_id)
        return _review_from_row(row)

    def update_review_field(
        self,
        record_id: int,
        field_name: str,
        value: str | float | None,
        *,
        action: str,
    ) -> StoredReviewRecord:
        if field_name not in _REVIEW_FIELDS:
            raise ValueError(f"수정할 수 없는 필드입니다: {field_name}")
        before = self.get_review_record(record_id)
        before_json = json.dumps(
            {field_name: getattr(before, field_name)}, ensure_ascii=False
        )
        after_json = json.dumps({field_name: value}, ensure_ascii=False)
        with self._connect() as conn:
            cursor = conn.execute(
                f"UPDATE extracted_records SET {field_name} = ?, updated_at = ? "
                "WHERE record_id = ?",
                (value, _utc_now(), record_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(record_id)
            _insert_action_log(
                conn, action, str(record_id), before_json, after_json
            )
        return self.get_review_record(record_id)

    def set_review_status(
        self,
        record_ids: list[int],
        status: ReviewStatus,
        *,
        action: str,
    ) -> list[StoredReviewRecord]:
        updated: list[StoredReviewRecord] = []
        with self._connect() as conn:
            for record_id in record_ids:
                row = conn.execute(
                    "SELECT review_status FROM extracted_records WHERE record_id = ?",
                    (record_id,),
                ).fetchone()
                if row is None:
                    raise KeyError(record_id)
                conn.execute(
                    """
                    UPDATE extracted_records
                    SET review_status = ?, updated_at = ?
                    WHERE record_id = ?
                    """,
                    (status.value, _utc_now(), record_id),
                )
                _insert_action_log(
                    conn,
                    action,
                    str(record_id),
                    json.dumps(
                        {"review_status": row["review_status"]}, ensure_ascii=False
                    ),
                    json.dumps({"review_status": status.value}, ensure_ascii=False),
                )
        for record_id in record_ids:
            updated.append(self.get_review_record(record_id))
        return updated

    def get_or_create_mail_report_row(
        self,
        *,
        extracted_record_id: int,
        mail_entry_id: str,
        **values: Any,
    ) -> StoredWorkReportRow:
        """Create one mail-derived row, idempotently by extracted record."""

        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT * FROM work_report_rows
                WHERE extracted_record_id = ? AND source_type = ?
                """,
                (extracted_record_id, RowSource.MAIL.value),
            ).fetchone()
            if existing is not None:
                return _work_report_from_row(existing)
            row_id = self._insert_work_report_row(
                conn,
                source_type=RowSource.MAIL,
                extracted_record_id=extracted_record_id,
                mail_entry_id=mail_entry_id,
                values=values,
            )
        return self.get_work_report_row(row_id)

    def create_manual_report_row(self, **values: Any) -> StoredWorkReportRow:
        """Persist a user-entered exception row without Outlook identity."""

        with self._connect() as conn:
            row_id = self._insert_work_report_row(
                conn,
                source_type=RowSource.MANUAL,
                extracted_record_id=None,
                mail_entry_id=None,
                values=values,
            )
            _insert_action_log(
                conn,
                "MANUAL_WORK_REPORT_ROW_CREATED",
                str(row_id),
                None,
                json.dumps(_json_safe(values), ensure_ascii=False),
            )
        return self.get_work_report_row(row_id)

    def _insert_work_report_row(
        self,
        conn: sqlite3.Connection,
        *,
        source_type: RowSource,
        extracted_record_id: int | None,
        mail_entry_id: str | None,
        values: dict[str, Any],
    ) -> int:
        now = _utc_now()
        cursor = conn.execute(
            """
            INSERT INTO work_report_rows(
                source_type, extracted_record_id, mail_entry_id,
                work_date, work_date_confirmed, vendor_name, tracking_no,
                equipment_name, business_team, actual_headcount,
                per_person_man_day, reported_daily_man_day,
                calculated_daily_man_day, confirmed_daily_man_day,
                reported_cumulative_man_day, calculated_cumulative_man_day,
                confirmed_cumulative_man_day, cumulative_series_key,
                issue_codes_json, review_status, included, warning_confirmed,
                resolution_note, created_at, updated_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?
            )
            """,
            (
                source_type.value,
                extracted_record_id,
                mail_entry_id,
                _date_to_db(values.get("work_date")),
                int(bool(values.get("work_date_confirmed", False))),
                values.get("vendor_name"),
                values.get("tracking_no"),
                values.get("equipment_name"),
                values.get("business_team"),
                values.get("actual_headcount"),
                _decimal_to_db(values.get("per_person_man_day")),
                _decimal_to_db(values.get("reported_daily_man_day")),
                _decimal_to_db(values.get("calculated_daily_man_day")),
                _decimal_to_db(values.get("confirmed_daily_man_day")),
                _decimal_to_db(values.get("reported_cumulative_man_day")),
                _decimal_to_db(values.get("calculated_cumulative_man_day")),
                _decimal_to_db(values.get("confirmed_cumulative_man_day")),
                values.get("cumulative_series_key"),
                _issue_codes_to_db(values.get("issue_codes", ())),
                _enum_value(
                    values.get("review_status", ReviewStatus.FORMAT_UNSUPPORTED)
                ),
                int(bool(values.get("included", True))),
                int(bool(values.get("warning_confirmed", False))),
                values.get("resolution_note"),
                now,
                now,
            ),
        )
        return int(cursor.lastrowid)

    def get_work_report_row(self, row_id: int) -> StoredWorkReportRow:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM work_report_rows WHERE row_id = ?", (row_id,)
            ).fetchone()
        if row is None:
            raise KeyError(row_id)
        return _work_report_from_row(row)

    def list_work_report_rows(
        self, date_from: date, date_to: date
    ) -> list[StoredWorkReportRow]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM work_report_rows
                WHERE work_date BETWEEN ? AND ?
                ORDER BY work_date, row_id
                """,
                (date_from.isoformat(), date_to.isoformat()),
            ).fetchall()
        return [_work_report_from_row(row) for row in rows]

    def update_work_report_row(
        self,
        row_id: int,
        changes: dict[str, Any],
        *,
        resolution_note: str | None,
    ) -> StoredWorkReportRow:
        invalid = set(changes) - _WORK_REPORT_UPDATE_FIELDS
        if invalid:
            raise ValueError(f"수정할 수 없는 취합 필드입니다: {sorted(invalid)}")
        if not changes:
            return self.get_work_report_row(row_id)
        before = self.get_work_report_row(row_id)
        assignments: list[str] = []
        parameters: list[Any] = []
        for field_name, value in changes.items():
            column = (
                "issue_codes_json" if field_name == "issue_codes" else field_name
            )
            assignments.append(f"{column} = ?")
            parameters.append(_work_report_value_to_db(field_name, value))
        assignments.extend(["resolution_note = ?", "updated_at = ?"])
        parameters.extend([resolution_note, _utc_now(), row_id])
        with self._connect() as conn:
            cursor = conn.execute(
                f"UPDATE work_report_rows SET {', '.join(assignments)} "
                "WHERE row_id = ?",
                tuple(parameters),
            )
            if cursor.rowcount == 0:
                raise KeyError(row_id)
            _invalidate_reports(conn)
            _insert_action_log(
                conn,
                "WORK_REPORT_ROW_UPDATED",
                str(row_id),
                json.dumps(_json_safe(before), ensure_ascii=False),
                json.dumps(_json_safe(changes), ensure_ascii=False),
            )
        return self.get_work_report_row(row_id)

    def confirm_work_report_row(
        self,
        row_id: int,
        *,
        confirmed_daily_man_day: Decimal,
        confirmed_cumulative_man_day: Decimal,
        resolution_note: str,
    ) -> StoredWorkReportRow:
        if not resolution_note.strip():
            raise ValueError("확정 사유를 입력해 주세요.")
        before = self.get_work_report_row(row_id)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE work_report_rows
                SET confirmed_daily_man_day = ?,
                    confirmed_cumulative_man_day = ?,
                    warning_confirmed = 1,
                    work_date_confirmed = 1,
                    review_status = ?,
                    resolution_note = ?,
                    updated_at = ?
                WHERE row_id = ?
                """,
                (
                    _decimal_to_db(confirmed_daily_man_day),
                    _decimal_to_db(confirmed_cumulative_man_day),
                    ReviewStatus.REVIEWED.value,
                    resolution_note.strip(),
                    _utc_now(),
                    row_id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(row_id)
            _invalidate_reports(conn)
            _insert_action_log(
                conn,
                "WORK_REPORT_ROW_CONFIRMED",
                str(row_id),
                json.dumps(_json_safe(before), ensure_ascii=False),
                json.dumps(
                    {
                        "confirmed_daily_man_day": str(
                            confirmed_daily_man_day
                        ),
                        "confirmed_cumulative_man_day": str(
                            confirmed_cumulative_man_day
                        ),
                    },
                    ensure_ascii=False,
                ),
            )
        return self.get_work_report_row(row_id)

    def resolve_duplicate_rows(
        self,
        row_ids: list[int],
        decision: str,
        *,
        resolution_note: str,
    ) -> list[StoredWorkReportRow]:
        if len(row_ids) < 2:
            raise ValueError("중복 후보 행이 두 개 이상 필요합니다.")
        if decision not in {"KEEP_OLD", "REPLACE_NEW", "EXCLUDE_BOTH"}:
            raise ValueError("지원하지 않는 중복 해결 방식입니다.")
        if not resolution_note.strip():
            raise ValueError("중복 해결 사유를 입력해 주세요.")
        sorted_ids = sorted(row_ids)
        included_ids: set[int]
        if decision == "KEEP_OLD":
            included_ids = {sorted_ids[0]}
        elif decision == "REPLACE_NEW":
            included_ids = {sorted_ids[-1]}
        else:
            included_ids = set()
        with self._connect() as conn:
            for row_id in sorted_ids:
                current = conn.execute(
                    "SELECT issue_codes_json FROM work_report_rows WHERE row_id = ?",
                    (row_id,),
                ).fetchone()
                if current is None:
                    raise KeyError(row_id)
                issues = [
                    code
                    for code in json.loads(current["issue_codes_json"] or "[]")
                    if code != WorkReportIssueCode.DUPLICATE_UNRESOLVED.value
                ]
                conn.execute(
                    """
                    UPDATE work_report_rows
                    SET included = ?, issue_codes_json = ?, resolution_note = ?,
                        updated_at = ?
                    WHERE row_id = ?
                    """,
                    (
                        int(row_id in included_ids),
                        json.dumps(issues, ensure_ascii=False),
                        resolution_note.strip(),
                        _utc_now(),
                        row_id,
                    ),
                )
            _invalidate_reports(conn)
            _insert_action_log(
                conn,
                "WORK_REPORT_DUPLICATE_RESOLVED",
                ",".join(str(value) for value in sorted_ids),
                None,
                json.dumps(
                    {"decision": decision, "note": resolution_note},
                    ensure_ascii=False,
                ),
            )
        return [self.get_work_report_row(row_id) for row_id in sorted_ids]

    def create_final_report_snapshot(
        self,
        *,
        date_from: date,
        date_to: date,
        rows: list[StoredWorkReportRow],
        snapshot_hash: str,
    ) -> StoredFinalReport:
        now = _utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO final_reports(
                    date_from, date_to, snapshot_hash, confirmed_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    date_from.isoformat(),
                    date_to.isoformat(),
                    snapshot_hash,
                    now,
                ),
            )
            report_id = int(cursor.lastrowid)
            vendor_orders = {
                str(row["canonical_name"]).casefold(): int(row["sort_order"])
                for row in conn.execute(
                    "SELECT canonical_name, sort_order FROM vendors"
                ).fetchall()
            }
            for row in rows:
                _insert_final_report_row(
                    conn, report_id, row, vendor_orders
                )
        return self.get_final_report(report_id)

    def get_final_report(self, report_id: int) -> StoredFinalReport:
        with self._connect() as conn:
            report = conn.execute(
                "SELECT * FROM final_reports WHERE report_id = ?", (report_id,)
            ).fetchone()
            rows = conn.execute(
                """
                SELECT * FROM final_report_rows
                WHERE report_id = ?
                ORDER BY snapshot_row_id
                """,
                (report_id,),
            ).fetchall()
        if report is None:
            raise KeyError(report_id)
        return StoredFinalReport(
            report_id=int(report["report_id"]),
            date_from=date.fromisoformat(str(report["date_from"])),
            date_to=date.fromisoformat(str(report["date_to"])),
            snapshot_hash=str(report["snapshot_hash"]),
            confirmed_at=str(report["confirmed_at"]),
            copied_at=report["copied_at"],
            invalidated_at=report["invalidated_at"],
            rows=tuple(_final_report_row_from_db(row) for row in rows),
        )

    def mark_final_report_copied(self, report_id: int) -> StoredFinalReport:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE final_reports SET copied_at = ? WHERE report_id = ?",
                (_utc_now(), report_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(report_id)
            _insert_action_log(
                conn,
                "FINAL_REPORT_COPIED",
                str(report_id),
                None,
                None,
            )
        return self.get_final_report(report_id)

    def invalidate_current_final_report(self) -> None:
        with self._connect() as conn:
            _invalidate_reports(conn)

    def list_action_logs(self) -> list[ActionLog]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM action_logs ORDER BY log_id"
            ).fetchall()
        return [
            ActionLog(
                log_id=int(row["log_id"]),
                action=str(row["action"]),
                entity_id=row["entity_id"],
                before_json=row["before_json"],
                after_json=row["after_json"],
                result=row["result"],
                error_message=row["error_message"],
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]


_REVIEW_SELECT = """
SELECT
    er.*,
    pm.sender_name AS sender_name,
    pm.date_issue_codes_json AS mail_date_issue_codes_json,
    pm.work_date_confirmed AS mail_work_date_confirmed
FROM extracted_records AS er
JOIN processed_mails AS pm ON pm.mail_entry_id = er.mail_entry_id
"""


def _employee_from_row(row: sqlite3.Row) -> Employee:
    return Employee(
        employee_id=int(row["employee_id"]),
        name=str(row["name"]),
        email=str(row["email"]),
        aliases=_aliases_from_json(row["aliases_json"]),
        active=bool(row["active"]),
    )


def _vendor_from_row(row: sqlite3.Row) -> Vendor:
    return Vendor(
        vendor_id=int(row["vendor_id"]),
        canonical_name=str(row["canonical_name"]),
        aliases=_aliases_from_json(row["aliases_json"]),
        active=bool(row["active"]),
        sort_order=int(row["sort_order"]),
    )


def _review_from_row(row: sqlite3.Row) -> StoredReviewRecord:
    return StoredReviewRecord(
        record_id=int(row["record_id"]),
        mail_entry_id=str(row["mail_entry_id"]),
        work_record_id=str(row["work_record_id"]),
        equipment_record_id=row["equipment_record_id"],
        report_date=_date_from_db(row["report_date"]),
        sender_name=str(row["sender_name"] or ""),
        sender_email=str(row["sender_email"] or ""),
        tracking_no=row["tracking_no"],
        order_no=row["order_no"],
        project_name=row["project_name"],
        equipment_name=row["equipment_name"],
        unit_no=row["unit_no"],
        business_team=row["business_team"],
        vendor_name=row["vendor_name"],
        actual_headcount=row["actual_headcount"],
        day_headcount=row["day_headcount"],
        night_headcount=row["night_headcount"],
        per_person_man_day=row["per_person_man_day"],
        day_man_day=row["day_man_day"],
        night_man_day=row["night_man_day"],
        daily_man_day=row["daily_man_day"],
        cumulative_man_day=row["cumulative_man_day"],
        note=row["note"],
        confidence=float(row["confidence"] or 0.0),
        review_status=ReviewStatus(row["review_status"]),
        raw_section=str(row["raw_section"] or ""),
        date_issue_codes=tuple(
            str(code)
            for code in json.loads(
                row["mail_date_issue_codes_json"] or "[]"
            )
        ),
        work_date_confirmed=bool(row["mail_work_date_confirmed"]),
    )


def _work_report_from_row(row: sqlite3.Row) -> StoredWorkReportRow:
    return StoredWorkReportRow(
        row_id=int(row["row_id"]),
        source_type=RowSource(row["source_type"]),
        extracted_record_id=row["extracted_record_id"],
        mail_entry_id=row["mail_entry_id"],
        work_date=_date_from_db(row["work_date"]),
        work_date_confirmed=bool(row["work_date_confirmed"]),
        vendor_name=row["vendor_name"],
        tracking_no=row["tracking_no"],
        equipment_name=row["equipment_name"],
        business_team=row["business_team"],
        actual_headcount=row["actual_headcount"],
        per_person_man_day=_decimal_from_db(row["per_person_man_day"]),
        reported_daily_man_day=_decimal_from_db(
            row["reported_daily_man_day"]
        ),
        calculated_daily_man_day=_decimal_from_db(
            row["calculated_daily_man_day"]
        ),
        confirmed_daily_man_day=_decimal_from_db(
            row["confirmed_daily_man_day"]
        ),
        reported_cumulative_man_day=_decimal_from_db(
            row["reported_cumulative_man_day"]
        ),
        calculated_cumulative_man_day=_decimal_from_db(
            row["calculated_cumulative_man_day"]
        ),
        confirmed_cumulative_man_day=_decimal_from_db(
            row["confirmed_cumulative_man_day"]
        ),
        cumulative_series_key=row["cumulative_series_key"],
        issue_codes=tuple(
            WorkReportIssueCode(code)
            for code in json.loads(row["issue_codes_json"] or "[]")
        ),
        review_status=ReviewStatus(row["review_status"]),
        included=bool(row["included"]),
        warning_confirmed=bool(row["warning_confirmed"]),
        resolution_note=row["resolution_note"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _insert_final_report_row(
    conn: sqlite3.Connection,
    report_id: int,
    row: StoredWorkReportRow,
    vendor_orders: dict[str, int],
) -> None:
    required = (
        row.work_date,
        row.vendor_name,
        row.actual_headcount,
        row.per_person_man_day,
        row.confirmed_daily_man_day,
        row.confirmed_cumulative_man_day,
    )
    if any(value is None for value in required):
        raise ValueError("최종 보고서 행의 필수 확정값이 누락되었습니다.")
    conn.execute(
        """
        INSERT INTO final_report_rows(
            report_id, source_row_id, work_date, vendor_name,
            vendor_sort_order, tracking_no, equipment_name, business_team,
            actual_headcount, per_person_man_day, confirmed_daily_man_day,
            confirmed_cumulative_man_day
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            report_id,
            row.row_id,
            row.work_date.isoformat(),  # type: ignore[union-attr]
            row.vendor_name,
            vendor_orders.get(str(row.vendor_name).casefold(), 2_147_483_647),
            row.tracking_no,
            row.equipment_name,
            row.business_team,
            row.actual_headcount,
            _decimal_to_db(row.per_person_man_day),
            _decimal_to_db(row.confirmed_daily_man_day),
            _decimal_to_db(row.confirmed_cumulative_man_day),
        ),
    )


def _final_report_row_from_db(row: sqlite3.Row) -> StoredFinalReportRow:
    return StoredFinalReportRow(
        snapshot_row_id=int(row["snapshot_row_id"]),
        report_id=int(row["report_id"]),
        source_row_id=int(row["source_row_id"]),
        work_date=date.fromisoformat(str(row["work_date"])),
        vendor_name=str(row["vendor_name"]),
        vendor_sort_order=int(row["vendor_sort_order"]),
        tracking_no=row["tracking_no"],
        equipment_name=row["equipment_name"],
        business_team=row["business_team"],
        actual_headcount=int(row["actual_headcount"]),
        per_person_man_day=Decimal(str(row["per_person_man_day"])),
        confirmed_daily_man_day=Decimal(
            str(row["confirmed_daily_man_day"])
        ),
        confirmed_cumulative_man_day=Decimal(
            str(row["confirmed_cumulative_man_day"])
        ),
    )


def _aliases_json(aliases: list[str] | tuple[str, ...]) -> str:
    normalized = [alias.strip() for alias in aliases if alias.strip()]
    return json.dumps(normalized, ensure_ascii=False)


def _aliases_from_json(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(str(alias) for alias in json.loads(value))


def _insert_action_log(
    conn: sqlite3.Connection,
    action: str,
    entity_id: str,
    before_json: str | None,
    after_json: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO action_logs(
            action, entity_id, before_json, after_json,
            result, error_message, created_at
        )
        VALUES (?, ?, ?, ?, ?, NULL, ?)
        """,
        (action, entity_id, before_json, after_json, "성공", _utc_now()),
    )


def _date_to_db(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _date_from_db(value: object) -> date | None:
    return None if value is None else date.fromisoformat(str(value))


def _decimal_to_db(value: object) -> str | None:
    if value is None:
        return None
    parsed = Decimal(str(value))
    if not parsed.is_finite():
        raise ValueError("공수는 유한한 숫자여야 합니다.")
    return format(parsed, "f")


def _decimal_from_db(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _issue_codes_to_db(value: object) -> str:
    codes = [_enum_value(code) for code in value]  # type: ignore[union-attr]
    return json.dumps(codes, ensure_ascii=False)


def _enum_value(value: object) -> str:
    return str(value.value) if isinstance(value, Enum) else str(value)


def _work_report_value_to_db(field_name: str, value: object) -> object:
    if field_name == "work_date":
        return _date_to_db(value)  # type: ignore[arg-type]
    if field_name in {
        "per_person_man_day",
        "reported_daily_man_day",
        "calculated_daily_man_day",
        "confirmed_daily_man_day",
        "reported_cumulative_man_day",
        "calculated_cumulative_man_day",
        "confirmed_cumulative_man_day",
    }:
        return _decimal_to_db(value)
    if field_name == "issue_codes":
        return _issue_codes_to_db(value)
    if field_name in {
        "work_date_confirmed",
        "included",
        "warning_confirmed",
    }:
        return int(bool(value))
    if field_name == "review_status":
        return _enum_value(value)
    return value


def _json_safe(value: object) -> object:
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (Decimal, date, datetime)):
        return value.isoformat() if hasattr(value, "isoformat") else str(value)
    if isinstance(value, Enum):
        return value.value
    return value


def _invalidate_reports(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE final_reports
        SET invalidated_at = ?
        WHERE invalidated_at IS NULL
        """,
        (_utc_now(),),
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
