# Work Report UI Guidance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make work-report values, blocking errors, final preview columns, and row-review actions understandable without requiring prior knowledge of the calculation model.

**Architecture:** Keep calculation and finalization rules in the application/domain layers, and add a small presentation helper that translates stable issue codes into Korean titles, explanations, and corrective actions. Replace the tab-aligned final preview text with a real Qt table so headers and values have an unambiguous column relationship. Preserve existing Outlook/Excel boundaries and finalization safety checks.

**Tech Stack:** Python 3.12, PySide6, pytest, SQLite-backed application services

## Global Constraints

- Do not change reported, calculated, or confirmed man-day calculation semantics.
- Do not access real Outlook or write to real Excel during validation.
- Add a failing regression test before each production behavior change.
- Preserve the current worktree and do not commit or push without explicit approval.
- Finish with related tests, the full test suite, `compileall`, `git diff --check`, and a `HANDOFF.md` entry.

---

### Task 1: Shared work-report guidance

**Files:**
- Create: `src/outsource_mail_collector/ui/work_report_guidance.py`
- Test: `tests/test_work_report_guidance.py`

**Interfaces:**
- Consumes: `WorkReportIssueCode`
- Produces: `COLUMN_HELP: dict[str, str]`, `issue_title(code) -> str`, `issue_detail(code) -> str`, and `issue_action(code) -> str`

- [ ] **Step 1: Write failing tests for human-readable column and issue guidance**

```python
def test_man_day_column_help_distinguishes_reported_calculated_and_confirmed():
    assert "메일 본문" in COLUMN_HELP["메일 투입"]
    assert "자동 계산" in COLUMN_HELP["계산 투입"]
    assert "Excel" in COLUMN_HELP["확정 투입"]
    assert "이전 확정 누적" in COLUMN_HELP["계산 누적"]


def test_issue_guidance_explains_registration_fix():
    code = WorkReportIssueCode.WORK_ORDER_UNREGISTERED
    assert "수주 미등록" in issue_title(code)
    assert "설정" in issue_action(code)
```

- [ ] **Step 2: Run the tests and verify they fail because the helper module does not exist**

Run: `pytest tests/test_work_report_guidance.py -v --basetemp .pytest-tmp/ui-guidance-red`

Expected: FAIL during import because `work_report_guidance` does not exist.

- [ ] **Step 3: Implement literal Korean guidance for every issue code and every review-grid column**

Create immutable dictionaries keyed by visible column text and `WorkReportIssueCode`. Return a safe fallback containing the enum value for any future unmapped issue code.

- [ ] **Step 4: Run the helper tests and verify they pass**

Run: `pytest tests/test_work_report_guidance.py -v --basetemp .pytest-tmp/ui-guidance-green`

Expected: PASS.

### Task 2: Review-grid tooltips and readable status

**Files:**
- Modify: `src/outsource_mail_collector/ui/review_grid.py`
- Modify: `tests/test_review_grid.py`

**Interfaces:**
- Consumes: `COLUMN_HELP`, `issue_title`, `issue_detail`, and `issue_action`
- Produces: header/cell/action tooltips and Korean validation-status summaries

- [ ] **Step 1: Add failing tests for header, value-cell, action-button, and issue tooltips**

```python
def test_review_grid_explains_man_day_columns_and_actions():
    grid = ReviewGridWidget([_row(1)])
    assert "자동 계산" in grid.horizontalHeaderItem(10).toolTip()
    assert "이전 확정 누적" in grid.item(0, 13).toolTip()
    actions = grid.cellWidget(0, 17).findChildren(QToolButton)
    assert all(button.toolTip() for button in actions)


def test_review_grid_uses_korean_issue_summary_with_detailed_tooltip():
    grid = ReviewGridWidget([_row(1, issue_codes=(WorkReportIssueCode.WORK_ORDER_UNREGISTERED,))])
    assert "수주 미등록" in grid.item(0, 15).text()
    assert "설정" in grid.item(0, 15).toolTip()
```

- [ ] **Step 2: Run the tests and verify missing tooltips/readable status cause failure**

Run: `pytest tests/test_review_grid.py -v --basetemp .pytest-tmp/review-grid-red`

Expected: FAIL because tooltips are empty and issue text is the raw enum value.

- [ ] **Step 3: Set header tooltips, value-aware cell tooltips, and action tooltips**

For ordinary cells, combine the column explanation and the displayed value. For validation status, show comma-separated Korean issue titles and a multiline tooltip containing each issue’s explanation and corrective action.

- [ ] **Step 4: Run the review-grid tests and verify they pass**

Run: `pytest tests/test_review_grid.py -v --basetemp .pytest-tmp/review-grid-green`

Expected: PASS.

### Task 3: Precise finalization blocker messages

**Files:**
- Modify: `src/outsource_mail_collector/application/final_report_service.py`
- Modify: `tests/test_final_report_service.py`

**Interfaces:**
- Consumes: stable `WorkReportIssueCode` values
- Produces: `FinalizationBlocker.message` values that identify the cause and required correction

- [ ] **Step 1: Add failing tests for structural issue and missing-field instructions**

```python
def test_preview_explains_how_to_resolve_unregistered_work_order(tmp_path):
    ...
    blocker = next(item for item in preview.blockers if item.code == "WORK_ORDER_UNREGISTERED")
    assert "수주" in blocker.message
    assert "설정" in blocker.message


def test_preview_names_each_missing_required_field(tmp_path):
    ...
    blocker = next(item for item in preview.blockers if item.code == "REQUIRED_FIELD_MISSING")
    assert "Tracking No." in blocker.message
    assert "사업팀" in blocker.message
```

- [ ] **Step 2: Run the targeted tests and verify the current generic message fails**

Run: `pytest tests/test_final_report_service.py -v --basetemp .pytest-tmp/final-service-red`

Expected: FAIL because blockers currently say only “차단 오류를 먼저 해결해 주세요.”

- [ ] **Step 3: Map every blocking issue to a specific cause/action and enumerate missing fields**

Keep blocker codes unchanged. Change only user-facing messages, using application-local constants so the service does not depend on PySide6 or UI modules.

- [ ] **Step 4: Run final-report service tests and verify they pass**

Run: `pytest tests/test_final_report_service.py -v --basetemp .pytest-tmp/final-service-green`

Expected: PASS.

### Task 4: Table-based final preview and grouped blocker notice

**Files:**
- Modify: `src/outsource_mail_collector/ui/final_report_dialog.py`
- Modify: `tests/test_final_report_dialog.py`

**Interfaces:**
- Consumes: `FinalReportPreview.rows` and `FinalReportPreview.blockers`
- Produces: `preview_table: QTableWidget` with fixed headers and grouped blocker text

- [ ] **Step 1: Add a failing regression test proving 3.0 is under “누적 공수”**

```python
def test_preview_places_cumulative_value_under_cumulative_header():
    dialog = FinalReportDialog(preview_with_daily_1_5_and_cumulative_3_0)
    cumulative_column = next(
        index
        for index in range(dialog.preview_table.columnCount())
        if dialog.preview_table.horizontalHeaderItem(index).text() == "누적 공수"
    )
    assert dialog.preview_table.item(0, cumulative_column).text() == "3.0"
```

- [ ] **Step 2: Add a failing test for the visible “야근 인원” column and grouped row context**

Assert the table has a “야근 인원” header and the blocker label contains one row heading with date, vendor, and Tracking No. followed by multiple corrective bullets.

- [ ] **Step 3: Run dialog tests and verify failure against the plain-text preview**

Run: `pytest tests/test_final_report_dialog.py -v --basetemp .pytest-tmp/final-dialog-red`

Expected: FAIL because `preview_table` does not exist and blockers are comma-joined.

- [ ] **Step 4: Replace `QPlainTextEdit` with a read-only `QTableWidget`**

Create columns for date, vendor, Tracking No., equipment, team, actual headcount, night headcount, per-person man-day, confirmed daily man-day, and confirmed cumulative man-day. Use header tooltips and resize-to-contents behavior.

- [ ] **Step 5: Group blockers by row and include row-identifying context**

Render a heading “최종 확정할 수 없습니다.”, then one row section per row ID, then deduplicated bullet messages. Preserve disabled confirmation and copy-button state rules.

- [ ] **Step 6: Run dialog tests and verify they pass**

Run: `pytest tests/test_final_report_dialog.py -v --basetemp .pytest-tmp/final-dialog-green`

Expected: PASS.

### Task 5: Self-explanatory problem-row review

**Files:**
- Modify: `src/outsource_mail_collector/ui/problem_review_dialog.py`
- Modify: `src/outsource_mail_collector/ui/main_window.py`
- Modify: `tests/test_problem_review_dialog.py`

**Interfaces:**
- Consumes: `issue_codes`, reported/calculated values, and any existing confirmed values
- Produces: an instruction panel, issue-specific actions, field tooltips, prefilled safe confirmed values, and visible validation errors

- [ ] **Step 1: Add failing tests for instructions, prefill, and visible validation errors**

```python
def test_review_dialog_explains_reported_calculated_and_confirmed_values():
    dialog = ProblemReviewDialog(issue_codes=(WorkReportIssueCode.DAILY_MISMATCH,))
    assert "메일값" in dialog.instruction_label.text()
    assert "자동 계산값" in dialog.instruction_label.text()
    assert "Excel" in dialog.instruction_label.text()


def test_invalid_accept_displays_reason_in_dialog():
    dialog = ProblemReviewDialog()
    dialog._accept_if_valid()
    assert "확정 투입" in dialog.error_label.text()
```

- [ ] **Step 2: Run the dialog tests and verify the current silent failure**

Run: `pytest tests/test_problem_review_dialog.py -v --basetemp .pytest-tmp/problem-dialog-red`

Expected: FAIL because no instruction/error labels exist.

- [ ] **Step 3: Add issue-aware guidance and visible validation feedback**

Accept `issue_codes`, `confirmed_daily`, and `confirmed_cumulative` as optional constructor parameters. Show each issue’s title/action, set field tooltips and placeholders, and put caught `ValueError` text into a red word-wrapped label.

- [ ] **Step 4: Pass row issues and confirmed candidates from `MainWindow`**

Use existing confirmed values first. When no confirmed value exists and reported equals calculated, prefill that unambiguous value; leave mismatches blank so the user must choose.

- [ ] **Step 5: Run dialog and main-window related tests**

Run: `pytest tests/test_problem_review_dialog.py tests/test_main_window.py -v --basetemp .pytest-tmp/problem-dialog-green`

Expected: PASS.

### Task 6: Integrated verification and handoff

**Files:**
- Modify: `HANDOFF.md`

**Interfaces:**
- Consumes: completed implementation and test evidence
- Produces: reproducible validation record and remaining runtime boundary

- [ ] **Step 1: Run all UI and finalization tests together**

Run: `pytest tests/test_work_report_guidance.py tests/test_review_grid.py tests/test_problem_review_dialog.py tests/test_final_report_dialog.py tests/test_final_report_service.py tests/test_main_window.py -v --basetemp .pytest-tmp/work-report-ui-related`

Expected: PASS.

- [ ] **Step 2: Run the full automated suite**

Run: `pytest --basetemp .pytest-tmp/work-report-ui-full`

Expected: PASS.

- [ ] **Step 3: Run static checks**

Run: `python -m compileall src tests`

Expected: exit code 0.

Run: `git diff --check`

Expected: no output and exit code 0.

- [ ] **Step 4: Append a session record to `HANDOFF.md`**

Record decisions, changed files, exact test counts, any failures encountered, and explicitly state that real Outlook/Excel and interactive GUI verification were not run.

- [ ] **Step 5: Inspect final status and diff scope**

Run: `git status --short --branch`

Expected: only this task’s tracked changes plus the pre-existing untracked `.claude/`, `.superpowers/`, `AGENTS.md`, and `CLAUDE.md`.

