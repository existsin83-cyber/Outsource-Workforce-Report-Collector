# Work Report Compilation Implementation Plan

> **For implementation:** Execute this plan task-by-task with
> `superpowers:executing-plans`. Apply TDD for every production change and stop at
> the verification checkpoints. Do not commit or push unless the user explicitly
> requests it.

**Goal:** Convert extracted Outlook work-report rows and manually entered exception
rows into a validated multi-day external-work man-day table, preserve reported,
calculated, and confirmed values, and copy a user-confirmed snapshot as HTML and
plain text.

**Architecture:** Keep Outlook collection read-only and preserve the existing
parser boundary. Add pure date-resolution and Decimal calculation components,
persist report rows and immutable final snapshots through the SQLite repository,
orchestrate review and finalization in application services, and let PySide6 only
display DTOs and place rendered output on the clipboard.

**Tech Stack:** Python 3.12, Pydantic 2, Decimal, sqlite3, PySide6, pytest

**Approved design:**
`docs/superpowers/specs/2026-07-29-work-report-compilation-design.md`

## Global Constraints

- Only the detailed external-work man-day table is in scope. Do not implement the
  upper site/headcount summary table, KakaoTalk collection, or site classification.
- Outlook remains read-only. Do not create drafts, send, reply, forward, move,
  delete, or change read state.
- Keep `actual_headcount`, `per_person_man_day`, `daily_man_day`,
  `cumulative_man_day`, `day_man_day`, and `night_man_day` separate.
- Do not overwrite reported values with calculated or confirmed values.
- Use `Decimal` in new calculation code and SQLite `TEXT` for new persisted man-day
  values. Convert legacy float values through `Decimal(str(value))`.
- Reuse `ReviewStatus` for row review state. Use a separate enum only for
  machine-readable issue codes.
- Keep mail fixtures as anonymized Python string constants. Never add sample
  `.msg` files, real mail bodies, personal data, or company-confidential data.
- Preserve existing untracked files and the `.superpowers/` visual mockup.
- No implementation task includes a commit or push step.
- Run actual Outlook or clipboard integration checks only after separate user
  approval. Automated tests must use fakes or Qt's isolated test process.

---

### Task 1: Domain Types and Decimal Man-Day Calculation

**Files:**

- Create: `src/outsource_mail_collector/domain/work_report.py`
- Create:
  `src/outsource_mail_collector/application/man_day_calculation_service.py`
- Modify: `src/outsource_mail_collector/domain/__init__.py`
- Create: `tests/test_man_day_calculation_service.py`

**Interfaces:**

- `RowSource`: `MAIL`, `MANUAL`
- `WorkReportIssueCode`: date, daily, cumulative, duplicate, and invalid-value
  issue codes
- `IssueSeverity`: `WARNING`, `BLOCKING`
- `ManDayValues`: reported, calculated, and confirmed daily/cumulative values
- `ManDayCalculationService.calculate_daily(...)`
- `ManDayCalculationService.calculate_cumulative(...)`
- `quantize_man_day(value) -> Decimal`

- [ ] **Step 1: Write failing daily calculation tests**

Cover:

```python
def test_missing_reported_daily_uses_calculation_and_warns():
    result = service.calculate_daily(
        actual_headcount=2,
        per_person_man_day=Decimal("1.5"),
        reported_daily=None,
    )
    assert result.calculated == Decimal("3.0")
    assert result.confirmed_candidate == Decimal("3.0")
    assert WorkReportIssueCode.DAILY_MISSING in result.issues


def test_reported_daily_mismatch_requires_confirmation():
    result = service.calculate_daily(
        actual_headcount=2,
        per_person_man_day=Decimal("1.5"),
        reported_daily=Decimal("4.0"),
    )
    assert result.calculated == Decimal("3.0")
    assert result.confirmed_candidate is None
    assert WorkReportIssueCode.DAILY_MISMATCH in result.issues
```

Also cover integer-only non-negative headcount, negative values, missing required
inputs, exact match, and `ROUND_HALF_UP` at one decimal place.

- [ ] **Step 2: Run the focused tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_man_day_calculation_service.py -q
```

Expected: import failure because the domain types and service do not exist.

- [ ] **Step 3: Implement the minimum daily calculation**

Parse inputs with `Decimal(str(value))`, reject non-finite/negative values, require
an integral headcount, and quantize with:

```python
MAN_DAY_QUANTUM = Decimal("0.1")


def quantize_man_day(value: Decimal) -> Decimal:
    return value.quantize(MAN_DAY_QUANTUM, rounding=ROUND_HALF_UP)
```

Do not use `float` inside the service.

- [ ] **Step 4: Add failing cumulative calculation tests**

Cover:

- prior confirmed cumulative plus current confirmed daily
- missing reported cumulative with a prior value
- reported/calculated cumulative mismatch
- first row with a reported baseline candidate
- first row with neither a prior value nor a reported value becoming blocking

- [ ] **Step 5: Implement cumulative calculation and run tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_man_day_calculation_service.py -q
```

Expected: all Task 1 tests pass.

---

### Task 2: Subject-First Work-Date Resolution

**Files:**

- Create: `src/outsource_mail_collector/parsing/work_date_parser.py`
- Modify: `src/outsource_mail_collector/domain/models.py`
- Modify:
  `src/outsource_mail_collector/application/extraction_orchestrator.py`
- Create: `tests/test_work_date_parser.py`
- Modify: `tests/test_extraction_orchestrator.py`
- Modify: `tests/fixtures.py`

**Interfaces:**

- `WorkDateSource`: `SUBJECT`, `BODY`, `UNRESOLVED`
- `WorkDateResolution`
  - `candidate_date`
  - `subject_date`
  - `body_date`
  - `source`
  - `requires_review`
  - `issue_codes`
- `resolve_work_date(subject, body_text, received_at) -> WorkDateResolution`

- [ ] **Step 1: Add anonymized date-format fixtures and failing parser tests**

Cover at least:

- `26_07_29`, `2026. 07. 29`, and `7월 29일` subject forms
- same subject/body date
- conflicting subject/body dates: subject remains the candidate and warning is set
- subject date with next-day received timestamp: subject remains authoritative
- missing subject date with body date: body is only a review-required candidate
- both missing: no candidate; received date is not silently substituted

Use fixed current/received years in the tests so two-digit-year behavior is
deterministic.

- [ ] **Step 2: Run parser tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_work_date_parser.py -q
```

- [ ] **Step 3: Implement the pure parser**

Keep regular expressions and year normalization in `parsing/`. Return evidence
dates only; do not store body text or perform DB access.

- [ ] **Step 4: Extend `MailRecord` with backward-compatible date evidence**

Add optional/defaulted fields so existing constructors remain valid:

```python
subject_report_date: date | None = None
body_report_date: date | None = None
report_date_source: WorkDateSource = WorkDateSource.UNRESOLVED
date_issue_codes: tuple[str, ...] = ()
work_date_confirmed: bool = False
```

Keep `received_at` timezone-aware when Outlook supplies timezone information.

- [ ] **Step 5: Add orchestration tests**

Assert that `ExtractionOrchestrator` resolves the date before persistence:

- subject date becomes `MailRecord.report_date`
- mismatch evidence reaches the repository
- unresolved dates do not get marked confirmed
- the existing extraction pipeline order is unchanged

- [ ] **Step 6: Integrate resolution and run focused regression**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_work_date_parser.py tests/test_extraction_orchestrator.py tests/test_extraction_pipeline.py -q
```

Expected: all focused tests pass without changing Outlook COM behavior.

---

### Task 3: Additive SQLite Persistence for Report Rows and Snapshots

**Files:**

- Modify:
  `src/outsource_mail_collector/infrastructure/db/schema.sql`
- Modify:
  `src/outsource_mail_collector/infrastructure/db/repository.py`
- Modify: `src/outsource_mail_collector/application/models.py`
- Modify: `tests/test_repository.py`
- Modify: `tests/test_smoke.py`

**Schema additions:**

- Add date-evidence columns to `processed_mails`
- Add `sort_order` to `vendors`, defaulting existing rows to `vendor_id` order
- Create `work_report_rows`
- Create `final_reports`
- Create `final_report_rows`
- Create indexes for date range, cumulative series, source record, and duplicate
  lookup

Persist new Decimal values as canonical strings such as `"3.0"`.

- [ ] **Step 1: Write failing migration tests**

Create a minimal old-version DB containing the current tables, initialize the
repository, and assert:

- existing rows survive
- new tables and columns exist
- vendor ordering is deterministic
- migration can run twice

Inspect unfamiliar tables with `PRAGMA table_info` before querying columns.

- [ ] **Step 2: Write failing repository round-trip tests**

Cover:

- mail-derived report row round trip
- manual report row creation with no EntryID
- reported/calculated/confirmed Decimal values remain exact
- issue-code JSON and `ReviewStatus` round trip
- row field update and issue confirmation create action logs
- duplicate candidates can coexist until explicitly resolved
- final report and final row snapshots are immutable
- copy timestamp update does not alter the snapshot

- [ ] **Step 3: Run repository tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_repository.py tests/test_smoke.py -q
```

- [ ] **Step 4: Implement schema and additive migration**

Use `PRAGMA table_info` in `_apply_additive_migrations`. Do not rebuild or drop
existing tables. Suggested logical columns for `work_report_rows`:

```text
row_id, source_type, extracted_record_id, mail_entry_id,
work_date, work_date_confirmed, vendor_name, tracking_no,
equipment_name, business_team, actual_headcount,
per_person_man_day, reported_daily_man_day,
calculated_daily_man_day, confirmed_daily_man_day,
reported_cumulative_man_day, calculated_cumulative_man_day,
confirmed_cumulative_man_day, cumulative_series_key,
issue_codes_json, review_status, included,
resolution_note, created_at, updated_at
```

Do not add a uniqueness constraint that prevents storing duplicate/revision
candidates. Use a non-unique lookup index instead.

- [ ] **Step 5: Add focused repository DTOs and methods**

Provide narrow methods rather than exposing connections:

- `get_or_create_mail_report_row(...)`
- `create_manual_report_row(...)`
- `list_work_report_rows(date_from, date_to)`
- `update_work_report_row(...)`
- `confirm_work_report_row(...)`
- `resolve_duplicate_rows(...)`
- `create_final_report_snapshot(...)`
- `get_final_report(...)`
- `mark_final_report_copied(...)`
- `invalidate_current_final_report(...)`

All multi-table writes and action logs use one transaction.

- [ ] **Step 6: Run persistence tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_repository.py tests/test_smoke.py -q
```

Expected: all persistence and migration tests pass.

---

### Task 4: Work Report Assembly, Manual Rows, and Duplicate Resolution

**Files:**

- Create:
  `src/outsource_mail_collector/application/work_report_service.py`
- Modify: `src/outsource_mail_collector/application/models.py`
- Modify:
  `src/outsource_mail_collector/application/review_service.py`
- Create: `tests/test_work_report_service.py`
- Modify: `tests/test_review_service.py`

**Interfaces:**

- `WorkReportRow` presentation DTO
- `WorkReportRangeResult`
- `WorkReportService.synchronize_extracted_records(...)`
- `WorkReportService.list_rows(date_from, date_to)`
- `WorkReportService.add_manual_row(...)`
- `WorkReportService.update_row(...)`
- `WorkReportService.confirm_row(...)`
- `WorkReportService.set_included(...)`
- `WorkReportService.resolve_duplicate(...)`

- [ ] **Step 1: Write failing synchronization tests**

Assert that an extracted record:

- keeps mail-reported daily and cumulative values
- converts legacy float inputs through `Decimal(str(value))`
- carries `per_person_man_day`, business team, work-date evidence, and EntryID
- gets the correct cumulative series key
- is not duplicated when synchronization is repeated

Expand `ReviewRecord` and `review_record_from_stored` only with fields required for
this mapping.

- [ ] **Step 2: Write failing series and duplicate tests**

Cover:

- series key is normalized vendor plus Tracking No.
- normalized equipment name is used only when Tracking No. is absent
- both identifiers missing creates a blocking issue
- same work date/vendor/Tracking No. is marked duplicate
- rows from different vendors or dates are not duplicates
- no automatic sum occurs
- keep-old, replace-with-new, and exclude-both resolutions are audited

- [ ] **Step 3: Write failing manual-row tests**

Assert manual rows:

- use `RowSource.MANUAL`
- may cover dates with no source mail
- have no Outlook original action
- pass through the same daily, cumulative, duplicate, and review rules
- require all final-table fields needed for output

- [ ] **Step 4: Run service tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_work_report_service.py tests/test_review_service.py -q
```

- [ ] **Step 5: Implement synchronization and validation**

Normal rows default to included. Warning rows remain included but not confirmed.
Blocking rows cannot be confirmed. Excluded rows keep their stored values.

When a confirmed value changes, recompute only later unfinalized rows in the same
series and invalidate the current draft/confirmation through the repository.

- [ ] **Step 6: Implement manual rows and duplicate decisions**

Require a resolution note for a value override or duplicate decision. Preserve
both source candidates and record the chosen action; never delete the losing row.

- [ ] **Step 7: Run service and existing review tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_work_report_service.py tests/test_review_service.py tests/test_extraction_orchestrator.py -q
```

Expected: all focused service tests pass.

---

### Task 5: Finalization, Ordering, and Immutable Snapshot

**Files:**

- Create:
  `src/outsource_mail_collector/application/final_report_service.py`
- Modify: `src/outsource_mail_collector/application/models.py`
- Create: `tests/test_final_report_service.py`

**Interfaces:**

- `FinalizationBlocker`
- `FinalReportPreview`
- `FinalReportSnapshot`
- `FinalReportService.preview(date_from, date_to)`
- `FinalReportService.confirm(date_from, date_to)`
- `FinalReportService.mark_copied(report_id)`

- [ ] **Step 1: Write failing blocker tests**

Finalization must fail when:

- a blocking issue remains
- a warning row has not been individually confirmed
- a duplicate/revision remains unresolved
- a first cumulative baseline is unavailable
- an included row lacks a confirmed daily or cumulative value

Excluded rows must not block finalization.

- [ ] **Step 2: Write failing order tests**

Assert exact order:

1. work date ascending
2. vendor repository/configuration order
3. Tracking No. ascending
4. equipment name ascending when Tracking No. is absent

Do not sort vendors alphabetically when configured order differs.

- [ ] **Step 3: Write failing snapshot tests**

Confirming creates a snapshot containing only included rows and only confirmed
daily/cumulative values. Later source edits:

- invalidate the current confirmation
- do not mutate the prior snapshot
- require a new confirmation/version

- [ ] **Step 4: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_final_report_service.py -q
```

- [ ] **Step 5: Implement preview and confirmation**

Keep preview side-effect free. Perform blocker revalidation and snapshot creation
in one confirmation transaction to prevent a stale preview from being confirmed.
Use a deterministic snapshot hash over normalized row values.

- [ ] **Step 6: Run finalization tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_final_report_service.py tests/test_work_report_service.py -q
```

Expected: all Task 4–5 service tests pass.

---

### Task 6: Pure HTML and Plain-Text Report Rendering

**Files:**

- Create:
  `src/outsource_mail_collector/application/report_renderer.py`
- Create: `tests/test_report_renderer.py`

**Interface:**

- `RenderedReport(html: str, plain_text: str)`
- `HtmlReportRenderer.render(snapshot) -> RenderedReport`

- [ ] **Step 1: Write failing rendering tests**

Assert:

- the approved nine columns and order
- HTML escaping of vendor/equipment text
- one-decimal man-day formatting and integer headcount
- a repeated column header at each date boundary
- single-date and multi-date titles
- identical row values in HTML and plain text
- no issue codes, internal calculations, EntryID, or audit data in final output

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_report_renderer.py -q
```

- [ ] **Step 3: Implement deterministic rendering**

Use the immutable snapshot as the only input. Do not query the repository or call
Outlook/Excel/PySide6 from the renderer. Generate inline table styles suitable for
Outlook paste while retaining a tab-delimited plain-text fallback.

- [ ] **Step 4: Run rendering tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_report_renderer.py -q
```

Expected: all rendering tests pass.

---

### Task 7: Extend the Review Grid and Add Manual/Problem Review Dialogs

**Files:**

- Modify: `src/outsource_mail_collector/ui/review_grid.py`
- Create: `src/outsource_mail_collector/ui/manual_row_dialog.py`
- Create: `src/outsource_mail_collector/ui/problem_review_dialog.py`
- Modify: `tests/test_review_grid.py`
- Create: `tests/test_manual_row_dialog.py`
- Create: `tests/test_problem_review_dialog.py`

- [ ] **Step 1: Write failing grid tests**

Replace dummy-row-based assertions with DTO fixtures. Assert columns for:

- work date, vendor, Tracking No., equipment, business team
- actual headcount and per-person man-day
- reported/calculated/confirmed daily
- reported/calculated/confirmed cumulative
- validation state and included state

Assert that normal rows are included, problem styling is visible, excluded rows
remain visible, and mail rows retain an EntryID while manual rows do not expose an
original-mail action.

- [ ] **Step 2: Write failing manual-dialog tests**

Test validation and emitted input for work date, vendor, Tracking No./equipment,
business team, headcount, per-person man-day, reported daily, and reported
cumulative. Reject non-integer headcount and invalid Decimal text before calling a
service.

- [ ] **Step 3: Write failing problem-review tests**

Show reported, calculated, and proposed confirmed values side by side. Require an
explicit choice and resolution note for mismatches and duplicate decisions.

- [ ] **Step 4: Run UI tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_review_grid.py tests/test_manual_row_dialog.py tests/test_problem_review_dialog.py -q
```

- [ ] **Step 5: Implement the approved UI behavior**

Keep all calculation and persistence calls in application services. Dialogs return
validated user input only. Remove the stale `dummy_rows()` helper and its
temporary integration comments once no test imports it.

- [ ] **Step 6: Run focused UI tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_review_grid.py tests/test_manual_row_dialog.py tests/test_problem_review_dialog.py -q
```

Expected: all Task 7 UI tests pass headlessly.

---

### Task 8: Final Preview Dialog and Clipboard Boundary

**Files:**

- Create: `src/outsource_mail_collector/ui/final_report_dialog.py`
- Create: `src/outsource_mail_collector/ui/clipboard.py`
- Create: `tests/test_final_report_dialog.py`
- Create: `tests/test_clipboard.py`

**Interfaces:**

- `ClipboardWriter.write(rendered_report)`
- Qt implementation using `QMimeData`
- final preview dialog receiving `FinalReportPreview`

- [ ] **Step 1: Write failing preview-dialog tests**

Assert:

- multiple dates and repeated headers are visible
- blockers disable final confirmation and identify affected rows
- a clean preview enables `전체 최종 확인`
- copy remains disabled until the service returns a confirmed snapshot
- changing a row outside the dialog requires reopening/reconfirming

- [ ] **Step 2: Write failing clipboard payload tests**

Use a fake clipboard or isolated `QApplication.clipboard()` and assert both:

```text
text/html
text/plain
```

No Outlook COM call is allowed.

- [ ] **Step 3: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_final_report_dialog.py tests/test_clipboard.py -q
```

- [ ] **Step 4: Implement preview and clipboard adapter**

Use `QMimeData.setHtml()` and `setText()`. Call
`FinalReportService.mark_copied(report_id)` only after the clipboard write
succeeds.

- [ ] **Step 5: Run focused tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_final_report_dialog.py tests/test_clipboard.py tests/test_report_renderer.py -q
```

Expected: all preview, clipboard, and renderer tests pass.

---

### Task 9: Main Window, Worker, and Dependency Wiring

**Files:**

- Modify: `src/outsource_mail_collector/application/container.py`
- Modify: `src/outsource_mail_collector/ui/workers.py`
- Modify: `src/outsource_mail_collector/ui/main_window.py`
- Modify: `src/outsource_mail_collector/app.py`
- Modify: `src/outsource_mail_collector/ui/settings_dialog.py`
- Modify: `src/outsource_mail_collector/application/settings_service.py`
- Modify: `tests/test_main_window.py`
- Modify: `tests/test_settings_dialog.py`
- Modify: `tests/test_smoke.py`

- [ ] **Step 1: Write failing composition tests**

Assert `build_services()` provides:

- `man_day_calculation_service`
- `work_report_service`
- `final_report_service`
- `report_renderer`

The services share the same repository instance but no COM object crosses into
domain/parsing code.

- [ ] **Step 2: Write failing workflow tests**

After collection and extraction, the worker must synchronize report rows and
return the requested range. Preserve COM initialization inside the worker thread.
Collection still queries received-mail dates, while work rows use resolved work
dates.

- [ ] **Step 3: Write failing main-window tests**

Assert:

- a date-range control supports one or more work dates
- collected/saved report rows populate the extended grid
- `수동 행 추가` invokes `WorkReportService`
- problem-row review refreshes calculations and warnings
- `최종 표 미리보기` invokes `FinalReportService.preview`
- the existing Excel preparation notice remains unchanged
- original mail opens only for mail-sourced rows

- [ ] **Step 4: Add vendor-order settings tests**

Verify that current vendor insertion order is exposed as report sort order and
that add/edit/delete operations preserve deterministic ordering. Do not reintroduce
site visibility or headcount-summary settings.

- [ ] **Step 5: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_main_window.py tests/test_settings_dialog.py tests/test_smoke.py -q
```

- [ ] **Step 6: Wire services and UI**

The main window calls application services only. Keep Outlook original display in
`ReviewService` and keep clipboard operations in the Qt adapter. Do not enable or
alter Excel writing.

- [ ] **Step 7: Run integration-level unit tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_main_window.py tests/test_settings_dialog.py tests/test_smoke.py tests/test_mail_collection_service.py tests/test_outlook_adapter.py -q
```

Expected: all composition, UI workflow, collection, and read-only adapter tests
pass.

---

### Task 10: Full Regression, Documentation, and Handoff

**Files:**

- Modify: `docs/PRD.md`
- Modify: `docs/TRD.md`
- Modify: `docs/SYSTEM_ARCHITECTURE.md`
- Modify: `docs/ADR.md`
- Modify: `HANDOFF.md`
- Modify implementation files only if verification exposes a defect

- [ ] **Step 1: Run the complete automated suite**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

If Windows temp permissions fail, rerun with a new workspace-local path:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-tmp\work-report
```

Expected: all existing and new tests pass.

- [ ] **Step 2: Run static safety checks**

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests
git diff --check
git status --short --branch
```

Expected: compilation succeeds, no whitespace errors, and only intended files plus
pre-existing untracked files are present.

- [ ] **Step 3: Update architecture and requirement documents**

Document:

- detailed-table-only scope
- subject-first work-date policy
- reported/calculated/confirmed value separation
- cumulative key and first-baseline behavior
- manual exception rows
- final snapshot and HTML/plain-text copy
- no Outlook write and no Excel change

Do not include real mail text or sample company/person data.

- [ ] **Step 4: Append the session handoff**

Add the newest KST entry at the top of the session log while preserving older
entries. Record:

- approved design and implementation scope
- exact changed files
- automated commands and results
- unexecuted Outlook/clipboard/GUI checks
- remaining risks
- commit/push status

- [ ] **Step 5: Request approval for real-environment verification**

Do not perform it automatically. The separate checklist is:

1. start the app against a test/copy DB
2. read an approved Outlook date range without changing mail state
3. verify title/body/received-date warnings
4. enter a manual exception row
5. confirm a multi-day final preview
6. paste the copied HTML into an unsent test mail
7. compare visible values and repeated headers
8. close the draft without sending unless the user separately authorizes sending

- [ ] **Step 6: Report completion without committing**

Report changed files, tests, skipped real-environment checks, risks, and explicitly
state that no commit or push was made.
