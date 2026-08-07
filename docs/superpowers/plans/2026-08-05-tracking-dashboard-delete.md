# Tracking No. 개별 삭제 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 선택한 Tracking No.의 운영 데이터를 확인 후 삭제한다.

**Architecture:** Repository가 원자적 삭제를 담당하고, 대시보드 서비스는 존재 검증을, UI는 명시적 확인과 새로고침을 담당한다.

**Tech Stack:** Python 3.12, SQLite, PySide6, pytest.

## Global Constraints

- `settings`, `employees`, `vendors`, `work_order_mappings`는 보존한다.
- 공유 원본 메일은 다른 Tracking No.가 참조하면 보존한다.
- DB 삭제 실패 시 전체 롤백한다.
- 커밋·푸시·브랜치 변경은 수행하지 않는다.

---

### Task 1: Repository 삭제 경계

**Files:**

- Modify: `src/outsource_mail_collector/infrastructure/db/repository.py`
- Test: `tests/test_repository.py`

**Interfaces:** Produces `delete_tracking_operational_data(tracking_no: str) -> None`.

- [ ] **Step 1: Write a failing repository test**

```python
def test_delete_tracking_operational_data_preserves_settings_and_shared_mail(repository):
    repository.delete_tracking_operational_data("AB260101")
    assert repository.is_mail_processed("SHARED-MAIL")
    assert not repository.is_mail_processed("TARGET-ONLY-MAIL")
    assert repository.list_employees()
```

Seed target and other Tracking No. rows, target baseline/status/action/final-report source rows, one shared mail, one target-only mail, and a project setting.

- [ ] **Step 2: Run the test and observe RED**

Run `.venv\Scripts\python.exe -m pytest tests\test_repository.py::test_delete_tracking_operational_data_preserves_settings_and_shared_mail -q --basetemp .pytest-dashboard-delete-20260805 -p no:cacheprovider`.

Expected: method missing.

- [ ] **Step 3: Implement one transaction**

```python
def delete_tracking_operational_data(self, tracking_no: str) -> None:
    normalized = normalize_tracking_no(tracking_no)
    with self.transaction():
        # Delete target snapshot dependencies, target work rows and extracts.
        # Delete target baseline/status/logs and only orphan processed mail.
        ...
```

Do not delete master tables. Remove empty final reports after their target snapshot rows are removed.

- [ ] **Step 4: Run the test and observe GREEN**

Run the Step 2 command. Expected: PASS.

### Task 2: Service guard

**Files:**

- Modify: `src/outsource_mail_collector/application/tracking_dashboard_service.py`
- Test: `tests/test_tracking_dashboard_service.py`

**Interfaces:** Consumes repository method; produces `delete(tracking_no: str) -> None`.

- [ ] **Step 1: Write failing tests for an unknown and an existing Tracking No.**

```python
with pytest.raises(ValueError, match="존재하지 않는 Tracking No."):
    service.delete("MISSING")
service.delete(" ab 260101 ")
assert service.drill_down("AB260101") == ()
```

- [ ] **Step 2: Run RED, then implement and run GREEN**

```python
def delete(self, tracking_no: str) -> None:
    if not self.drill_down(tracking_no):
        raise ValueError("존재하지 않는 Tracking No.입니다.")
    self._repository.delete_tracking_operational_data(tracking_no)
```

Run `.venv\Scripts\python.exe -m pytest tests\test_tracking_dashboard_service.py -q --basetemp .pytest-dashboard-delete-20260805 -p no:cacheprovider` before and after implementation.

### Task 3: Confirmed red delete button

**Files:**

- Modify: `src/outsource_mail_collector/ui/tracking_dashboard_dialog.py`
- Test: `tests/test_tracking_dashboard_dialog.py`

**Interfaces:** Consumes service `delete`; produces `delete_button` and `_delete_selected()`.

- [ ] **Step 1: Write failing UI tests**

Verify `#b71c1c` styling, no-selection information message, cancellation does not call deletion, and Yes confirmation calls `delete("AB260101")` and the refresh callback.

- [ ] **Step 2: Run RED, then implement and run GREEN**

```python
self.delete_button = QPushButton("삭제")
self.delete_button.setStyleSheet("QPushButton {background:#b71c1c;color:white;}")
self.delete_button.clicked.connect(self._delete_selected)
```

`_delete_selected` must use `_selected_summary()`, `QMessageBox.question` with Yes/No, then call service delete, `refresh()`, `_refresh_final_preview()`, and `_refresh_callback()` only after Yes. Run `.venv\Scripts\python.exe -m pytest tests\test_tracking_dashboard_dialog.py -q --basetemp .pytest-dashboard-delete-20260805 -p no:cacheprovider` before and after implementation.

### Task 4: Verification and handoff

**Files:** Modify `HANDOFF.md`.

- [ ] Run `.venv\Scripts\python.exe -m pytest tests\test_repository.py tests\test_tracking_dashboard_service.py tests\test_tracking_dashboard_dialog.py -q --basetemp .pytest-dashboard-delete-20260805 -p no:cacheprovider`.
- [ ] Run `.venv\Scripts\python.exe -m compileall -q src tests`.
- [ ] Run `git diff --check`.
- [ ] Record scope, test evidence, unrun live checks, and no-commit status in `HANDOFF.md`.
