"""SQLite 초기화. 스키마는 schema.sql 에서 관리 (docs/TRD.md 기준)."""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    schema_sql = resources.files("outsource_mail_collector.infrastructure.db").joinpath(
        "schema.sql"
    ).read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.commit()
    return conn
