# Collection, Review, and Settings Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect read-only Outlook collection, parsing, persistent review records, and employee/vendor/folder settings to the existing PySide6 review grid.

**Architecture:** Application services receive repository and adapter dependencies through constructors. SQLite operations use short-lived connections, Outlook COM stays inside the infrastructure adapter, and PySide6 runs COM collection in a worker thread before applying DTO results on the UI thread.

**Tech Stack:** Python 3.12, PySide6, pywin32, pydantic 2, sqlite3, pytest

## Global Constraints

- Outlook access is read-only: no delete, move, read-state change, reply, or forward operations.
- UI code calls Application services only and never receives COM objects.
- The database path is `%LOCALAPPDATA%\OutsourceMailCollector\collector.db`.
- Mail fixtures remain Python constants; no plain-text fixture files are added.
- Ambiguous numeric values remain unset and are never inferred.
- Excel COM writing is outside this implementation; the enabled button shows a preparation notice.
- Existing untracked `.claude/` and `CLAUDE.md` files are not staged or modified.
- Every production behavior is introduced by a failing test first.

---

### Task 1: Persistent SQLite Repository

**Files:**
- Modify: `src/outsource_mail_collector/infrastructure/db/repository.py`
- Modify: `src/outsource_mail_collector/infrastructure/db/schema.sql`
- Create: `tests/test_repository.py`

**Interfaces:**
- Produces: `Employee`, `Vendor`, `StoredReviewRecord`, and `SQLiteRepository`
- Produces: `default_db_path() -> Path`
- Produces repository methods for settings, employees, vendors, processed mail, extracted records, review edits, status changes, and logs

- [ ] **Step 1: Write failing repository tests**

```python
def test_default_db_path_uses_local_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert default_db_path() == tmp_path / "OutsourceMailCollector" / "collector.db"


def test_employee_and_vendor_round_trip(repository):
    employee = repository.save_employee(None, "홍길동", "USER@EXAMPLE.COM", ["길동"], True)
    vendor = repository.save_vendor(None, "협력사A", ["A사"], True)
    assert employee.email == "user@example.com"
    assert repository.list_employees() == [employee]
    assert repository.list_vendors() == [vendor]
```

Add focused tests for duplicate email/name rejection, setting round trips, processed EntryID
deduplication, atomic extracted-record storage, editable field updates, status updates, and
`action_logs` before/after JSON.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_repository.py -q
```

Expected: collection/import failure because the repository types and methods do not exist.

- [ ] **Step 3: Extend the schema**

Add missing persisted review fields needed by the approved UI while retaining existing table and
column names. Use idempotent schema creation for a new DB and a repository migration that checks
`PRAGMA table_info(extracted_records)` before adding:

```sql
equipment_record_id TEXT;
order_no TEXT;
project_name TEXT;
unit_no TEXT;
business_team TEXT;
day_headcount REAL;
night_headcount REAL;
per_person_man_day REAL;
day_man_day REAL;
night_man_day REAL;
note TEXT;
```

- [ ] **Step 4: Implement focused repository models and operations**

Use frozen dataclasses for `Employee`, `Vendor`, and `StoredReviewRecord`. Normalize emails with
`strip().lower()`, serialize aliases as UTF-8 JSON, use `sqlite3.Row`, and open a fresh connection
inside each public operation. Multi-table writes use one connection and one transaction.

- [ ] **Step 5: Run repository and smoke tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_repository.py tests/test_smoke.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add src/outsource_mail_collector/infrastructure/db/repository.py src/outsource_mail_collector/infrastructure/db/schema.sql tests/test_repository.py
git commit -m "feat: add persistent collector repository"
```

### Task 2: Collection Service and Application DTOs

**Files:**
- Create: `src/outsource_mail_collector/application/models.py`
- Create: `src/outsource_mail_collector/application/errors.py`
- Create: `src/outsource_mail_collector/application/mail_collection_service.py`
- Create: `tests/test_mail_collection_service.py`

**Interfaces:**
- Consumes: `SQLiteRepository.list_employees()`
- Consumes: `OutlookAdapter.list_messages()` and `OutlookAdapter.open_message()`
- Produces: `CollectionResult(mails, missing_employees, errors)`
- Produces: `MailCollectionService.collect(report_date, folder_path) -> CollectionResult`

- [ ] **Step 1: Write failing collection-service tests**

```python
def test_collect_filters_registered_senders_and_reports_missing():
    repository = FakeRepository(
        employees=[
            Employee(1, "홍길동", "hong@example.com", (), True),
            Employee(2, "김철수", "kim@example.com", (), True),
        ]
    )
    outlook = FakeOutlookAdapter(envelopes=[mail_envelope("HONG@EXAMPLE.COM")])
    result = MailCollectionService(repository, outlook).collect(date(2026, 7, 24), "Inbox")
    assert [mail.sender_email for mail in result.mails] == ["hong@example.com"]
    assert [employee.name for employee in result.missing_employees] == ["김철수"]
```

Add separate tests for no active employees, unregistered senders, one-message failure with later
messages continuing, and the end-exclusive next-day date range.

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_mail_collection_service.py -q
```

Expected: import failure for the missing service.

- [ ] **Step 3: Implement DTOs, errors, and collection**

Create immutable dataclasses:

```python
@dataclass(frozen=True)
class CollectionError:
    mail_id: str | None
    code: str
    message: str


@dataclass(frozen=True)
class CollectionResult:
    mails: tuple[MailRecord, ...]
    missing_employees: tuple[Employee, ...]
    errors: tuple[CollectionError, ...]
```

`collect()` calculates local midnight boundaries, filters against active normalized employee
emails, reads each matching message, and appends individual failures without aborting the batch.
With no active employees it returns an empty result with a `NO_ACTIVE_EMPLOYEES` error.

- [ ] **Step 4: Run service tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_mail_collection_service.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/outsource_mail_collector/application tests/test_mail_collection_service.py
git commit -m "feat: add mail collection service"
```

### Task 3: Extraction Orchestrator and Review DTO Mapping

**Files:**
- Create: `src/outsource_mail_collector/application/extraction_orchestrator.py`
- Modify: `src/outsource_mail_collector/application/models.py`
- Create: `tests/test_extraction_orchestrator.py`

**Interfaces:**
- Consumes: existing parsing functions and repository persistence operations
- Produces: `ReviewRecord`
- Produces: `ExtractionResult(records, skipped_mail_ids, errors)`
- Produces: `ExtractionOrchestrator.process(mails) -> ExtractionResult`

- [ ] **Step 1: Write failing orchestrator tests**

```python
def test_process_parses_persists_and_returns_review_records(repository):
    mail = sample_mail_record(FORMAT_A_NUMBERED)
    result = ExtractionOrchestrator(repository).process([mail])
    assert result.errors == ()
    assert result.records
    assert repository.is_mail_processed(mail.mail_id)


def test_process_skips_an_existing_entry_id(repository):
    mail = sample_mail_record(FORMAT_A_NUMBERED)
    repository.mark_processed_for_test(mail.mail_id)
    result = ExtractionOrchestrator(repository).process([mail])
    assert result.skipped_mail_ids == (mail.mail_id,)
```

Add tests for vendor alias canonicalization, a valid no-outsourcing mail, and one malformed mail
not preventing the next mail from being stored.

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_extraction_orchestrator.py -q
```

Expected: import failure for the missing orchestrator.

- [ ] **Step 3: Implement the orchestrator**

Call the existing pipeline in this exact order:

```python
normalized = normalize(mail.body_text, mail.body_html)
sections = split_sections(mail.mail_id, normalized.lines)
section_records = tuple(
    (section, record)
    for section in sections
    for record in extract_work_records(section)
)
validations = tuple(
    validate(section, record)
    for section, record in section_records
)
```

Map aliases through active vendors, persist a mail and all extracted records atomically, and map
stored records to immutable `ReviewRecord` DTOs. Existing EntryIDs are returned from repository
state instead of inserted again.

- [ ] **Step 4: Run orchestrator and parser tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_extraction_orchestrator.py tests/test_extraction_pipeline.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/outsource_mail_collector/application tests/test_extraction_orchestrator.py
git commit -m "feat: orchestrate extraction persistence"
```

### Task 4: Review and Excel Application Services

**Files:**
- Create: `src/outsource_mail_collector/application/review_service.py`
- Create: `src/outsource_mail_collector/application/excel_export_service.py`
- Modify: `src/outsource_mail_collector/application/errors.py`
- Create: `tests/test_review_service.py`
- Create: `tests/test_excel_export_service.py`

**Interfaces:**
- Produces: `ReviewService.update_field(record_id, field_name, raw_value)`
- Produces: `ReviewService.set_status(record_ids, status)`
- Produces: `ReviewService.open_original(mail_entry_id)`
- Produces: `ExcelExportService.export(workbook_path, sheet_name, record_ids)`

- [ ] **Step 1: Write failing review-service tests**

```python
def test_update_numeric_field_logs_before_and_after(repository):
    record = stored_review_record(repository, actual_headcount=2.0)
    ReviewService(repository, FakeOutlookAdapter()).update_field(
        record.record_id, "actual_headcount", "3.5"
    )
    assert repository.get_review_record(record.record_id).actual_headcount == 3.5
    assert repository.list_action_logs()[-1].action == "REVIEW_FIELD_UPDATED"


def test_invalid_numeric_edit_preserves_existing_value(repository):
    record = stored_review_record(repository, daily_man_day=4.0)
    with pytest.raises(InvalidReviewValueError):
        ReviewService(repository, FakeOutlookAdapter()).update_field(
            record.record_id, "daily_man_day", "네 명"
        )
    assert repository.get_review_record(record.record_id).daily_man_day == 4.0
```

Add tests for the editable-field allowlist, empty text to `None`, reviewed/excluded status changes,
and `open_original()` delegation.

- [ ] **Step 2: Write failing Excel-service tests**

```python
def test_export_without_real_adapter_is_explicitly_unavailable(repository):
    service = ExcelExportService(repository, excel_adapter=None)
    with pytest.raises(ExcelIntegrationUnavailableError):
        service.export(Path("target.xlsx"), "외주인원_원본", [1])
```

- [ ] **Step 3: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_review_service.py tests/test_excel_export_service.py -q
```

Expected: import failure for the missing services.

- [ ] **Step 4: Implement minimal services**

Allow edits only for `equipment_name`, `tracking_no`, `vendor_name`, `actual_headcount`,
`daily_man_day`, and `cumulative_man_day`. Parse numeric fields with `float`, translate blank
strings to `None`, and call a repository operation that updates the value and writes the action
log in one transaction. Accept only `ReviewStatus.REVIEWED` and `ReviewStatus.EXCLUDED` in bulk UI
status changes.

The Excel service rejects a missing adapter before any repository mutation. If an adapter is
provided later, it filters to reviewed records, calls `backup`, `ensure_sheet`, `append_rows`, and
`save` in order, then marks success.

- [ ] **Step 5: Run service tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_review_service.py tests/test_excel_export_service.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add src/outsource_mail_collector/application tests/test_review_service.py tests/test_excel_export_service.py
git commit -m "feat: add review and export services"
```

### Task 5: Read-Only Outlook COM Adapter

**Files:**
- Modify: `src/outsource_mail_collector/infrastructure/outlook_adapter.py`
- Create: `tests/test_outlook_adapter.py`

**Interfaces:**
- Extends protocol with `list_folders() -> list[str]` and `display_message(entry_id) -> None`
- Produces: `OutlookComAdapter`

- [ ] **Step 1: Write failing adapter tests with fake COM objects**

```python
def test_list_folders_returns_inbox_and_nested_paths(fake_outlook):
    adapter = OutlookComAdapter(dispatch=lambda _: fake_outlook)
    adapter.connect()
    assert adapter.list_folders() == ["Inbox", "Inbox/전장기술팀"]


def test_list_messages_uses_dasl_restrict_without_mutating_mail(fake_outlook):
    adapter = connected_adapter(fake_outlook)
    rows = adapter.list_messages("Inbox", START, END)
    assert fake_outlook.inbox.Items.restrict_calls == [EXPECTED_DASL]
    assert rows[0].mail_id == "ENTRY-1"
    assert fake_outlook.inbox.items[0].mutation_calls == []
```

Add tests for folder lookup failure, non-mail item skipping, Exchange SMTP conversion fallback,
body reading, Inspector display, and one connection retry.

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_outlook_adapter.py -q
```

Expected: import failure for `OutlookComAdapter`.

- [ ] **Step 3: Implement the adapter**

Use constants `OL_FOLDER_INBOX = 6`, `OL_MAIL_ITEM_CLASS = 43`, and the verified
`urn:schemas:httpmail:datereceived` DASL property. Accept an injectable dispatch callable for
tests. Recursively enumerate `Folders` from the default Inbox and resolve slash-separated paths.
Map COM values into pydantic models immediately so no COM object leaves the adapter.

`open_message()` reads properties only. `display_message()` is the sole method permitted to call
`Display()`. No implementation calls `Save`, `Delete`, `Move`, sets `UnRead`, replies, or forwards.

- [ ] **Step 4: Run adapter tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_outlook_adapter.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/outsource_mail_collector/infrastructure/outlook_adapter.py tests/test_outlook_adapter.py
git commit -m "feat: implement read-only Outlook adapter"
```

### Task 6: Settings Dialog

**Files:**
- Create: `src/outsource_mail_collector/ui/settings_dialog.py`
- Create: `src/outsource_mail_collector/ui/workers.py`
- Create: `tests/test_settings_dialog.py`

**Interfaces:**
- Consumes repository settings/employee/vendor methods
- Consumes `OutlookAdapter.list_folders()` through `FolderLoadWorker`
- Produces `SettingsDialog`

- [ ] **Step 1: Write failing dialog tests**

```python
def test_settings_dialog_round_trips_general_settings(qapp, repository):
    dialog = SettingsDialog(repository, FakeOutlookAdapter(["Inbox", "Inbox/전장기술팀"]))
    dialog.set_general_values("Inbox/전장기술팀", "C:/reports/source.xlsx", "외주인원_원본")
    dialog.save()
    assert repository.get_setting("outlook_folder") == "Inbox/전장기술팀"
    assert repository.get_setting("excel_sheet_name") == "외주인원_원본"


def test_refresh_folders_populates_real_adapter_results(qapp, repository):
    dialog = SettingsDialog(repository, FakeOutlookAdapter(["Inbox", "Inbox/전장기술팀"]))
    dialog.refresh_folders_for_test()
    assert dialog.folder_values() == ["Inbox", "Inbox/전장기술팀"]
```

Add tests for employee and vendor add/edit/remove, normalized email, duplicate validation messages,
and preservation of the selected folder when refresh fails.

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_settings_dialog.py -q
```

Expected: import failure for the missing dialog.

- [ ] **Step 3: Implement the dialog and folder worker**

Use a `QTabWidget` with General, Employees, and Vendors tabs. General contains an editable folder
combo, refresh button, Excel path edit with file chooser, and sheet-name edit. Employees and
vendors use `QTableWidget` plus add/edit/deactivate buttons. Modal row editors validate required
fields before calling repository methods.

`FolderLoadWorker` initializes COM inside its `run()` method, calls `list_folders()`, emits plain
Python strings, and uninitializes COM in `finally`.

- [ ] **Step 4: Run dialog tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_settings_dialog.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/outsource_mail_collector/ui/settings_dialog.py src/outsource_mail_collector/ui/workers.py tests/test_settings_dialog.py
git commit -m "feat: add collector settings dialog"
```

### Task 7: Main Window and Review Grid Integration

**Files:**
- Modify: `src/outsource_mail_collector/ui/review_grid.py`
- Modify: `src/outsource_mail_collector/ui/main_window.py`
- Modify: `src/outsource_mail_collector/ui/workers.py`
- Modify: `tests/test_review_grid.py`
- Create: `tests/test_main_window.py`

**Interfaces:**
- Consumes all Application services and `SettingsDialog`
- Produces `CollectionWorker`
- Produces actual review actions, summary values, and missing-employee display

- [ ] **Step 1: Write failing main-window tests**

```python
def test_window_starts_without_dummy_rows(qapp, services):
    window = MainWindow(services)
    assert window.review_grid.rowCount() == 0


def test_apply_collection_result_updates_grid_summary_and_missing_banner(qapp, services):
    window = MainWindow(services)
    window.apply_collection_result(sample_ui_result())
    assert window.review_grid.rowCount() == 2
    assert window.summary_value("수신 메일") == "2"
    assert "김철수" in window.missing_banner.text()


def test_excel_button_shows_preparation_notice(qapp, services, monkeypatch):
    window = MainWindow(services)
    shown = capture_information_message(monkeypatch)
    window.excel_button.click()
    assert "실제 Excel 연동은 아직 준비되지 않았습니다." in shown.text
```

Add tests for settings-button launch, collection button busy state, error recovery, selected-row
exclude/review actions, editable-cell persistence, and original-message action.

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_main_window.py tests/test_review_grid.py -q
```

Expected: constructor/signature failures because services are not connected.

- [ ] **Step 3: Refactor the review grid around record IDs**

Extend `ReviewRow` with `record_id` and `mail_entry_id`. Emit signals containing identifiers and
field names for edits and row actions. Remove `dummy_rows()` usage from production startup while
retaining no test-only fallback in production code.

- [ ] **Step 4: Implement main-window service wiring**

Create persistent widget attributes for toolbar controls, summary labels, missing banner, and
action buttons. `CollectionWorker` calls collection and extraction services off the UI thread and
emits a combined plain-data result. MainWindow applies results, reloads selected-date records,
updates statistics, restores button state, and shows aggregated individual errors.

Connect:

- settings button → `SettingsDialog`
- mail button → worker start
- cell edit → `ReviewService.update_field`
- exclude/review buttons → `ReviewService.set_status`
- original button → `ReviewService.open_original`
- Excel button → exact preparation notice

- [ ] **Step 5: Run UI tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_main_window.py tests/test_review_grid.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add src/outsource_mail_collector/ui tests/test_main_window.py tests/test_review_grid.py
git commit -m "feat: connect review grid to collector services"
```

### Task 8: Application Composition, Documentation, and Full Verification

**Files:**
- Modify: `src/outsource_mail_collector/app.py`
- Modify: `src/outsource_mail_collector/application/__init__.py`
- Modify: `src/outsource_mail_collector/infrastructure/__init__.py`
- Modify: `README.md`
- Modify: `CLAUDE.md` only if the user separately authorizes tracking that untracked file
- Modify: `tests/test_smoke.py`

**Interfaces:**
- Produces: `build_services(db_path: Path | None = None) -> ApplicationServices`
- Produces a runnable desktop application with persistent DB initialization

- [ ] **Step 1: Write a failing composition smoke test**

```python
def test_build_services_uses_requested_database(tmp_path):
    services = build_services(tmp_path / "collector.db")
    assert services.repository.db_path == tmp_path / "collector.db"
    assert (tmp_path / "collector.db").exists()
```

- [ ] **Step 2: Run the smoke test and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_smoke.py::test_build_services_uses_requested_database -q
```

Expected: import failure for `build_services`.

- [ ] **Step 3: Implement app composition**

Build the repository at the default LocalAppData path, initialize the schema, construct one
`OutlookComAdapter`, create the four services, and inject an `ApplicationServices` container into
`MainWindow`. Keep an optional DB path for isolated tests.

- [ ] **Step 4: Update tracked documentation**

Document:

- persistent DB location
- settings-first setup sequence
- read-only Outlook behavior
- real folder refresh
- mail collection workflow
- current Excel notice behavior
- pytest and app launch commands using `.venv`

Do not add the untracked `CLAUDE.md` unless separately authorized.

- [ ] **Step 5: Run the complete test suite outside the restricted sandbox if `tmp_path` is blocked**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: all tests pass with zero failures.

- [ ] **Step 6: Run static import and compile verification**

```powershell
Get-ChildItem src,tests -Recurse -Filter *.py | ForEach-Object {
    .\.venv\Scripts\python.exe -m py_compile $_.FullName
}
```

Expected: exit code 0 and no output.

- [ ] **Step 7: Verify scope**

```powershell
git status --short
git diff --check
git diff --stat HEAD~1
```

Expected: `.claude/` and `CLAUDE.md` remain untracked; no unrelated files are staged.

- [ ] **Step 8: Commit**

```powershell
git add src/outsource_mail_collector/app.py src/outsource_mail_collector/application/__init__.py src/outsource_mail_collector/infrastructure/__init__.py README.md tests/test_smoke.py
git commit -m "feat: assemble persistent collector application"
```

- [ ] **Step 9: Manual runtime checks**

Run:

```powershell
.\.venv\Scripts\python.exe -m outsource_mail_collector.app
```

Verify the window opens, settings persist after reopening, Outlook folder refresh lists real
folders, collection does not freeze the UI, and the Excel button displays the preparation notice.
Do not run any Outlook-mutating or Excel-writing operation.
