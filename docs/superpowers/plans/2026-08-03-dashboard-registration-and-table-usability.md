# Dashboard Registration and Table Usability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 수주 미등록 행의 마스터 등록 진입과 자동 입력, 대시보드 표 복사·행 번호·작업일 정렬을 제공한다.

**Architecture:** `TrackingDashboardDialog`는 표시와 사용자 액션만 담당하고, 수주 등록 화면 생성과 저장 후 전역 갱신은 `MainWindow`가 콜백으로 조정한다. `SettingsDialog`는 수주 마스터 탭 선택 및 편집 가능한 신규 행 자동 입력 API를 제공하며 기존 원자적 저장을 재사용한다.

**Tech Stack:** Python 3.12, PySide6, pytest, SQLite application services

## Global Constraints

- 실제 Outlook·Excel COM 또는 라이브 데이터에 접근하지 않는다.
- 미등록·충돌 값을 추정하지 않고 사용자가 보완하게 한다.
- DB 원본 행 ID와 최종 스냅샷 연결은 변경하지 않는다.
- 기존 사용자 미추적 파일을 보존하고, 이번 요청에서는 커밋·푸시하지 않는다.

---

### Task 1: 표 선택·복사, 행 번호, 작업일 정렬

**Files:**
- Modify: `src/outsource_mail_collector/ui/tracking_dashboard_dialog.py`
- Test: `tests/test_tracking_dashboard_dialog.py`

**Interfaces:**
- Produces: 요약/상세 표의 셀 단위 다중 선택, `Ctrl+C`/우클릭 TSV 복사, 기본 날짜 내림차 정렬과 두 정렬 버튼, 화면상 상세 행 번호.

- [ ] 선택된 실제 셀 범위를 TSV로 복사하고 빈 선택은 무시하는 실패 테스트를 작성한다.
- [ ] 테스트를 실행해 현재 복사 동작 부재로 실패하는지 확인한다.
- [ ] 공통 대시보드 표 위젯에 `SelectItems`, `ExtendedSelection`, `QKeySequence.Copy`, 컨텍스트 메뉴 복사를 구현한다.
- [ ] 상세 첫 열이 `1, 2, ...`이고 내부 `row_id`와 무관한 실패 테스트를 추가한 뒤 `_detail_values(row, display_row_number)`로 최소 구현한다.
- [ ] 최근 작업일 기본 내림차, 날짜 없음 마지막, 동률 Tracking No. 오름차와 두 버튼 전환 실패 테스트를 작성한 뒤 다이얼로그 정렬 상태와 재렌더링을 구현한다.
- [ ] `tests/test_tracking_dashboard_dialog.py`를 실행해 모두 통과시킨다.

### Task 2: 수주 등록 이동과 자동 입력

**Files:**
- Modify: `src/outsource_mail_collector/ui/settings_dialog.py`
- Modify: `src/outsource_mail_collector/ui/tracking_dashboard_dialog.py`
- Modify: `src/outsource_mail_collector/ui/main_window.py`
- Test: `tests/test_settings_dialog.py`
- Test: `tests/test_tracking_dashboard_dialog.py`
- Test: `tests/test_main_window.py`

**Interfaces:**
- `SettingsDialog(..., work_order_prefill: WorkOrderPrefill | None = None)`은 수주 마스터 탭을 선택하고 신규 행에 자동 입력한다.
- `TrackingDashboardDialog(..., work_order_registration_callback: Callable[[TrackingDashboardSummary], bool] | None = None)`은 미등록 상태 버튼을 통해 등록을 요청하고 `True`일 때 화면과 최종 미리보기를 갱신한다.
- `MainWindow._open_work_order_registration(summary) -> bool`은 설정 저장 성공 여부를 반환하고 기존 매핑 재적용/목록 갱신 경로를 재사용한다.

- [ ] SettingsDialog 자동 입력·수주 마스터 탭 선택·미등록 업체 미선택에 대한 실패 테스트를 작성한다.
- [ ] 작고 불변인 `WorkOrderPrefill` 타입과 SettingsDialog 초기화/행 선택 구현으로 테스트를 통과시킨다.
- [ ] `WORK_ORDER_UNREGISTERED` 요약에서만 검증 상태 셀에 `수주 등록 이동` 버튼이 나타나고 올바른 summary를 콜백에 전달하는 실패 테스트를 작성한다.
- [ ] 버튼 셀과 등록 성공 후 `refresh()`, 최종 미리보기 갱신, 상위 콜백 호출을 구현한다.
- [ ] MainWindow가 설정 창 저장 성공 시 매핑 재적용과 목록 갱신을 수행하고 취소 시 수행하지 않는 실패 테스트를 작성한다.
- [ ] 대시보드 생성 시 등록 콜백을 주입하고 SettingsDialog prefill 경로를 구현한다.
- [ ] 세 테스트 파일을 실행해 모두 통과시킨다.

### Task 3: 통합 검증 및 인계

**Files:**
- Modify: `HANDOFF.md`

- [ ] 관련 Qt/UI/application 테스트를 전용 `--basetemp`와 `PYTHONPATH=src`, `QT_QPA_PLATFORM=offscreen`으로 실행한다.
- [ ] 전체 pytest, `compileall`, `git diff --check`를 실행한다.
- [ ] 독립 검토에서 범위·오류·회귀를 확인하고 필요한 수정은 관련 테스트로 재검증한다.
- [ ] `HANDOFF.md` 상단에 변경, 결정, 검증, 미실행 Outlook·Excel·실GUI 검증, Git 상태를 기록한다.

