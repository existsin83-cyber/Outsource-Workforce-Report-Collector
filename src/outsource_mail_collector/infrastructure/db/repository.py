"""SQLite persistence for settings, collection results, and review history."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any

from outsource_mail_collector.domain.models import (
    EquipmentSection,
    MailRecord,
    OutsourceWorkRecord,
    ReviewStatus,
    ValidationResult,
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


@dataclass(frozen=True)
class StoredReviewRecord:
    record_id: int
    mail_entry_id: str
    work_record_id: str
    equipment_record_id: str | None
    report_date: date
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


_MIGRATION_COLUMNS: dict[str, dict[str, str]] = {
    "processed_mails": {
        "sender_name": "TEXT",
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


class SQLiteRepository:
    """Short-lived-connection repository safe to call from UI and worker threads."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        init_db(self.db_path).close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

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
        sql += " ORDER BY vendor_id"
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
                    cursor = conn.execute(
                        """
                        INSERT INTO vendors(canonical_name, aliases_json, active)
                        VALUES (?, ?, ?)
                        """,
                        (normalized_name, aliases_json, int(active)),
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
        )

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
                        received_at, report_date, content_hash, status, processed_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mail.mail_id,
                        mail.subject,
                        mail.sender_name,
                        mail.sender_email.strip().lower(),
                        mail.received_at.isoformat(),
                        mail.report_date.isoformat(),
                        content_hash,
                        "처리 완료",
                        now,
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
                mail.report_date.isoformat(),
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
        self, report_date: date | None = None
    ) -> list[StoredReviewRecord]:
        sql = _REVIEW_SELECT
        parameters: tuple[Any, ...] = ()
        if report_date is not None:
            sql += " WHERE er.report_date = ?"
            parameters = (report_date.isoformat(),)
        sql += " ORDER BY er.record_id"
        with self._connect() as conn:
            rows = conn.execute(sql, parameters).fetchall()
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
    pm.sender_name AS sender_name
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
    )


def _review_from_row(row: sqlite3.Row) -> StoredReviewRecord:
    return StoredReviewRecord(
        record_id=int(row["record_id"]),
        mail_entry_id=str(row["mail_entry_id"]),
        work_record_id=str(row["work_record_id"]),
        equipment_record_id=row["equipment_record_id"],
        report_date=date.fromisoformat(str(row["report_date"])),
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
