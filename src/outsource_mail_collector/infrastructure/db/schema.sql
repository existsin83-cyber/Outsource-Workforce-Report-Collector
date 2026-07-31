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
    active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS work_order_mappings (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tracking_no TEXT NOT NULL,
    normalized_tracking_no TEXT NOT NULL,
    equipment_name TEXT NOT NULL,
    vendor_id INTEGER NOT NULL REFERENCES vendors(vendor_id),
    business_team TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cumulative_baselines (
    normalized_tracking_no TEXT PRIMARY KEY,
    tracking_no TEXT NOT NULL,
    effective_through_date TEXT NOT NULL,
    cumulative_man_day TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS processed_mails (
    mail_entry_id TEXT PRIMARY KEY,
    subject TEXT,
    sender_name TEXT,
    sender_email TEXT,
    received_at TEXT,
    report_date TEXT,
    content_hash TEXT,
    status TEXT,
    processed_at TEXT,
    subject_report_date TEXT,
    body_report_date TEXT,
    report_date_source TEXT,
    date_issue_codes_json TEXT,
    work_date_confirmed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS extracted_records (
    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
    mail_entry_id TEXT NOT NULL REFERENCES processed_mails (mail_entry_id),
    work_record_id TEXT NOT NULL UNIQUE,
    equipment_record_id TEXT,
    report_date TEXT,
    sender_email TEXT,
    tracking_no TEXT,
    order_no TEXT,
    project_name TEXT,
    equipment_name TEXT,
    unit_no TEXT,
    business_team TEXT,
    vendor_name TEXT,
    actual_headcount REAL,
    day_headcount REAL,
    night_headcount REAL,
    per_person_man_day REAL,
    day_man_day REAL,
    night_man_day REAL,
    daily_man_day REAL,
    cumulative_man_day REAL,
    note TEXT,
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

CREATE TABLE IF NOT EXISTS work_report_rows (
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
    deleted_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS final_reports (
    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
    date_from TEXT NOT NULL,
    date_to TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    confirmed_at TEXT NOT NULL,
    copied_at TEXT,
    invalidated_at TEXT
);

CREATE TABLE IF NOT EXISTS final_report_rows (
    snapshot_row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL REFERENCES final_reports (report_id),
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

CREATE TABLE IF NOT EXISTS final_report_row_sources (
    snapshot_row_id INTEGER NOT NULL
        REFERENCES final_report_rows (snapshot_row_id) ON DELETE CASCADE,
    source_row_id INTEGER NOT NULL,
    PRIMARY KEY (snapshot_row_id, source_row_id)
);

CREATE INDEX IF NOT EXISTS idx_work_report_date
ON work_report_rows(work_date);

CREATE INDEX IF NOT EXISTS idx_work_report_series
ON work_report_rows(cumulative_series_key, work_date);

CREATE INDEX IF NOT EXISTS idx_work_report_source
ON work_report_rows(extracted_record_id);

CREATE INDEX IF NOT EXISTS idx_work_report_duplicate
ON work_report_rows(work_date, vendor_name, tracking_no, equipment_name);

CREATE INDEX IF NOT EXISTS idx_final_report_rows_report
ON final_report_rows(report_id, snapshot_row_id);

CREATE INDEX IF NOT EXISTS idx_final_report_row_sources_source
ON final_report_row_sources(source_row_id, snapshot_row_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_active_work_order_tracking
ON work_order_mappings(normalized_tracking_no)
WHERE active = 1;
