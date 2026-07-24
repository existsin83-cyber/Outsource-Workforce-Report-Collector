-- docs/TRD.md 의 SQLite 스키마 정의 그대로.

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS employees (
    employee_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1,
    aliases_json TEXT
);

CREATE TABLE IF NOT EXISTS vendors (
    vendor_id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL UNIQUE,
    aliases_json TEXT,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS processed_mails (
    mail_entry_id TEXT PRIMARY KEY,
    subject TEXT,
    sender_email TEXT,
    received_at TEXT,
    report_date TEXT,
    content_hash TEXT,
    status TEXT,
    processed_at TEXT
);

CREATE TABLE IF NOT EXISTS extracted_records (
    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
    mail_entry_id TEXT NOT NULL REFERENCES processed_mails (mail_entry_id),
    report_date TEXT,
    sender_email TEXT,
    tracking_no TEXT,
    equipment_name TEXT,
    vendor_name TEXT,
    actual_headcount REAL,
    daily_man_day REAL,
    cumulative_man_day REAL,
    confidence REAL,
    review_status TEXT,
    raw_section TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS action_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    entity_id TEXT,
    before_json TEXT,
    after_json TEXT,
    result TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL
);
