# Work Order Master and Mixed Man-Day Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 수주번호로 업체·사업팀을 자동 매핑하고, 실제 인원과 야근 인원을 분리해 일부 야근도 장비당 한 행으로 정확히 계산·검토·출력한다.

**Architecture:** 파서는 수주번호·장비명·실제 인원·야근 인원·메일 투입 공수만 순수 추출한다. application의 `WorkOrderMappingService`가 SQLite 수주 마스터를 조회해 업체·사업팀과 매핑 경고를 반환하고, `WorkReportService`가 매핑 결과와 `ManDayCalculationService`의 실제·야근 인원 계산 결과를 영속 취합 행으로 조립한다. UI는 설정·검토·수동 입력을 제공하고 최종 스냅샷 렌더러는 야근 인원과 `혼합` 표시를 출력한다.

**Tech Stack:** Python 3.12, PySide6, Pydantic, SQLite, pytest, Decimal

## Global Constraints

- Outlook 접근은 읽기 전용이며 삭제·이동·읽음 상태 변경·회신·전달을 하지 않는다.
- 실제 Excel 쓰기와 실제 Outlook 데이터에 영향을 주는 검증은 별도 사용자 승인 없이는 실행하지 않는다.
- 파싱 흐름은 `normalize → split_sections → extract_work_records → validate`를 유지한다.
- 실제 메일 본문·개인정보·회사 기밀을 fixture, 로그, 문서에 넣지 않는다.
- parser fixture는 `.txt`가 아니라 `tests/fixtures.py`의 익명화 Python 문자열 상수로 유지한다.
- 실제 작업인원, 야근 인원, 인당 공수, 보고·계산·확정 당일 공수, 보고·계산·확정 누적 공수를 서로 덮어쓰지 않는다.
- 모든 공수 계산은 `Decimal`, 소수점 한 자리, `ROUND_HALF_UP`을 사용한다.
- DB 변경은 기존 데이터를 파괴하지 않는 additive migration이어야 한다.
- 기존 사용자 변경과 미추적 파일을 보존한다.
- 사용자의 명시적 요청 전에는 커밋·푸시를 수행하지 않는다. 아래 각 작업은 검증 명령으로 끝내며 자동 커밋 단계는 실행하지 않는다.
- Windows pytest 임시 경로 문제를 피하기 위해 작업 전용 `--basetemp`를 저장소 내부에 사용한다.

---

## File Map

신규 파일:

- `src/outsource_mail_collector/application/work_order_mapping_service.py`
  - 수주번호 정규화, 매핑 조회, 장비명 교차 검증 결과를 제공한다.
- `tests/test_work_order_mapping_service.py`
  - 정상·미등록·장비명 불일치·비활성 매핑을 직접 검증한다.

주요 수정 파일:

- `tests/fixtures.py`, `tests/test_extraction_pipeline.py`
  - 익명화한 `투입 공수` 변형과 일부 야근 회귀를 추가한다.
- `src/outsource_mail_collector/parsing/outsource_extractor.py`
  - `투입 공수`를 `daily_man_day`로 추출한다.
- `src/outsource_mail_collector/domain/work_report.py`
  - 수주·장비·야근 관련 안정적인 이슈 코드를 추가한다.
- `src/outsource_mail_collector/infrastructure/db/schema.sql`
  - `work_order_mappings`와 야근 인원 스냅샷 열을 정의한다.
- `src/outsource_mail_collector/infrastructure/db/repository.py`
  - 수주 마스터 CRUD, migration, 야근 인원 round-trip을 제공한다.
- `src/outsource_mail_collector/application/models.py`
  - `night_headcount`를 추출 DTO부터 최종 DTO까지 전달한다.
- `src/outsource_mail_collector/application/man_day_calculation_service.py`
  - 실제·야근 인원 기반 당일 공수를 계산한다.
- `src/outsource_mail_collector/application/work_report_service.py`
  - 매핑 결과와 혼합 공수 표시 규칙을 취합 행에 적용한다.
- `src/outsource_mail_collector/application/final_report_service.py`
  - 혼합 행의 확정 조건과 스냅샷 필드를 검증한다.
- `src/outsource_mail_collector/application/settings_service.py`
  - 수주 마스터 CRUD application 경계를 제공한다.
- `src/outsource_mail_collector/application/container.py`, `src/outsource_mail_collector/app.py`
  - 매핑 서비스를 생성자 주입한다.
- `src/outsource_mail_collector/ui/settings_dialog.py`
  - 수주 마스터 탭을 제공한다.
- `src/outsource_mail_collector/ui/manual_row_dialog.py`
  - 수동 행의 야근 인원 입력을 제공한다.
- `src/outsource_mail_collector/ui/review_grid.py`
  - 야근 인원과 `혼합`을 표시한다.
- `src/outsource_mail_collector/application/report_renderer.py`
  - 최종 표의 야근 인원 열과 혼합 표시를 렌더링한다.

---

### Task 1: Parse Reported Daily Man-Day and Preserve Night Headcount

**Files:**
- Modify: `tests/fixtures.py`
- Modify: `tests/test_extraction_pipeline.py`
- Modify: `src/outsource_mail_collector/parsing/outsource_extractor.py`
- Modify: `src/outsource_mail_collector/application/models.py`
- Modify: `src/outsource_mail_collector/application/extraction_orchestrator.py`
- Test: `tests/test_extraction_pipeline.py`
- Test: `tests/test_extraction_orchestrator.py`

**Interfaces:**
- Consumes: 기존 `OutsourceWorkRecord.actual_headcount`, `night_headcount`, `daily_man_day`.
- Produces: `ReviewRecord.night_headcount: float | None`과 `투입 공수`가 채워진 `ReviewRecord.daily_man_day`.

- [ ] **Step 1: Add an anonymized real-format fixture**

`tests/fixtures.py`에 다음 구조의 상수를 추가한다. 실제 회사명과 실제 수주번호는 사용하지 않는다.

```python
FORMAT_D_INLINE_REPORTED_DAILY = """\
2026년 7월 27일 업무보고입니다.

1. 고객사H 장비Alpha #1
.수주번호 : AA260101
.외주 인원 : 1 명 (야근: 1 명 투입 공수 : 1.5)

2. 고객사I 장비Beta #2
.수주번호 : BB260202
.외주 인원 : 3 명 (야근: 1 명 투입 공수 : 3.5)
"""
```

- [ ] **Step 2: Write failing parser assertions**

`tests/test_extraction_pipeline.py`에 다음 테스트를 추가한다.

```python
def test_format_d_extracts_tracking_equipment_night_and_reported_daily():
    sections = _sections_for(FORMAT_D_INLINE_REPORTED_DAILY)
    assert len(sections) == 2

    first = extract_work_records(sections[0])[0]
    second = extract_work_records(sections[1])[0]

    assert sections[0].tracking_no == "AA260101"
    assert sections[0].equipment_name == "고객사H 장비Alpha #1"
    assert first.actual_headcount == 1.0
    assert first.night_headcount == 1.0
    assert first.daily_man_day == 1.5

    assert sections[1].tracking_no == "BB260202"
    assert sections[1].equipment_name == "고객사I 장비Beta #2"
    assert second.actual_headcount == 3.0
    assert second.night_headcount == 1.0
    assert second.daily_man_day == 3.5
```

- [ ] **Step 3: Run the parser test and confirm the intended failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_extraction_pipeline.py::test_format_d_extracts_tracking_equipment_night_and_reported_daily -v --basetemp .pytest-basetemp-work-order-task1-red
```

Expected: `daily_man_day` assertions fail because `_TOTAL_MAN_DAY` does not recognize `투입 공수`.

- [ ] **Step 4: Implement the minimal parser rule**

`src/outsource_mail_collector/parsing/outsource_extractor.py`에 명시적인 당일 라벨 정규식을 추가한다.

```python
_DAILY_MAN_DAY = re.compile(
    r"투입\s*공수\s*[:：]?\s*(?P<value>\d+(?:\.\d+)?)\s*(?:MD|공수)?"
)
```

`_extract_inline_style()`에서 `_DAILY_MAN_DAY`를 검색하고 레코드에 값을 보존한다.

```python
daily_match = _DAILY_MAN_DAY.search(section.section_text)

return [
    OutsourceWorkRecord(
        work_record_id=_new_record_id(),
        equipment_record_id=(
            f"{section.mail_id}:{section.section_index}"
        ),
        vendor_name=None,
        actual_headcount=float(headcount_match.group("count")),
        night_headcount=(
            float(headcount_match.group("night"))
            if headcount_match.group("night") is not None
            else None
        ),
        daily_man_day=(
            float(daily_match.group("value")) if daily_match else None
        ),
        note=note,
        confidence=confidence,
    )
]
```

`_TOTAL_MAN_DAY`의 모호성 처리와 `AMBIGUOUS_NUMBER` 근거는 변경하지 않는다.

- [ ] **Step 5: Add failing DTO propagation coverage**

`tests/test_extraction_orchestrator.py`의 저장 결과 assertion에 다음을 추가한다.

```python
assert result.records[0].night_headcount == 1.0
assert result.records[0].daily_man_day == 1.5
```

필요한 fixture 레코드에는 `night_headcount=1.0`, `daily_man_day=1.5`를 설정한다.

- [ ] **Step 6: Propagate night headcount through application DTOs**

`ReviewRecord`에 필드를 추가한다.

```python
night_headcount: float | None
```

`review_record_from_stored()`에서 다음을 전달한다.

```python
night_headcount=stored.night_headcount,
```

모든 `ReviewRecord` 테스트 생성자에 명시적인 `night_headcount`를 추가한다.

- [ ] **Step 7: Verify Task 1**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_extraction_pipeline.py tests/test_extraction_orchestrator.py -q --basetemp .pytest-basetemp-work-order-task1-green
```

Expected: selected parser and orchestrator tests pass.

---

### Task 2: Persist the Work Order Master Safely

**Files:**
- Modify: `src/outsource_mail_collector/infrastructure/db/schema.sql`
- Modify: `src/outsource_mail_collector/infrastructure/db/repository.py`
- Modify: `src/outsource_mail_collector/application/settings_service.py`
- Modify: `tests/test_repository.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- Produces: immutable `WorkOrderMapping` dataclass.
- Produces: `SQLiteRepository.list_work_order_mappings(active_only=False)`.
- Produces: `SQLiteRepository.save_work_order_mapping(mapping_id, tracking_no, equipment_name, vendor_id, business_team, active)`.
- Produces: `SQLiteRepository.delete_work_order_mapping(mapping_id)`.
- Produces: matching `SettingsService` pass-through methods.

- [ ] **Step 1: Write failing repository round-trip and normalization tests**

`tests/test_repository.py`에 다음 테스트를 추가한다.

```python
def test_work_order_mapping_round_trip_normalizes_tracking(repository):
    vendor = repository.save_vendor(None, "협력사A", [], True)

    mapping = repository.save_work_order_mapping(
        None,
        tracking_no=" ab 260101 ",
        equipment_name="장비 Alpha #1",
        vendor_id=vendor.vendor_id,
        business_team="PKG",
        active=True,
    )

    assert mapping.normalized_tracking_no == "AB260101"
    assert mapping.vendor_name == "협력사A"
    assert repository.list_work_order_mappings() == [mapping]
```

```python
def test_duplicate_active_work_order_tracking_is_rejected(repository):
    vendor = repository.save_vendor(None, "협력사A", [], True)
    repository.save_work_order_mapping(
        None, "AB260101", "장비 1", vendor.vendor_id, "PKG", True
    )

    with pytest.raises(DuplicateEntityError):
        repository.save_work_order_mapping(
            None, " ab 260101 ", "장비 2", vendor.vendor_id, "WA", True
        )
```

- [ ] **Step 2: Write a failing additive migration assertion**

기존 `test_additive_migration_preserves_old_rows_and_is_idempotent`에 다음을 추가한다.

```python
assert "work_order_mappings" in tables
```

그리고 `work_report_rows`, `final_report_rows`의 `night_headcount` 열을 `PRAGMA table_info`로 확인한다.

- [ ] **Step 3: Run repository tests and verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_repository.py -q --basetemp .pytest-basetemp-work-order-task2-red
```

Expected: missing dataclass, methods, table, and migration columns cause failures.

- [ ] **Step 4: Add the schema**

`schema.sql`에 다음 테이블과 인덱스를 추가한다.

```sql
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

CREATE UNIQUE INDEX IF NOT EXISTS uq_active_work_order_tracking
ON work_order_mappings(normalized_tracking_no)
WHERE active = 1;
```

`work_report_rows`와 `final_report_rows`에 각각 `night_headcount INTEGER`를 추가한다.

- [ ] **Step 5: Add repository models and normalization**

`repository.py`에 다음 dataclass를 추가한다.

```python
@dataclass(frozen=True)
class WorkOrderMapping:
    mapping_id: int
    tracking_no: str
    normalized_tracking_no: str
    equipment_name: str
    vendor_id: int
    vendor_name: str
    business_team: str
    active: bool
    created_at: str
    updated_at: str
```

정규화 함수는 다음 계약을 갖는다.

```python
def normalize_tracking_no(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(normalized.split()).upper()
```

빈 수주번호, 장비명, 사업팀은 `ValueError`로 거부한다.

- [ ] **Step 6: Implement CRUD with vendor join**

`list_work_order_mappings()`는 `vendors`를 join해 `vendor_name`을 반환한다.
`save_work_order_mapping()`은 insert/update 모두 같은 정규화와 검증을 사용하고
partial unique index 위반을 `DuplicateEntityError("이미 등록된 활성 수주번호입니다.")`로 변환한다.

정확한 public signatures는 다음과 같다.

- `list_work_order_mappings(self, active_only: bool = False) -> list[WorkOrderMapping]`
- `save_work_order_mapping(self, mapping_id: int | None, tracking_no: str, equipment_name: str, vendor_id: int, business_team: str, active: bool) -> WorkOrderMapping`
- `delete_work_order_mapping(self, mapping_id: int) -> None`

- [ ] **Step 7: Extend additive migration**

`_MIGRATION_COLUMNS`에 다음 열을 추가한다.

```python
"work_report_rows": {"night_headcount": "INTEGER"},
"final_report_rows": {"night_headcount": "INTEGER"},
```

`schema.sql` 실행이 기존 DB에 `work_order_mappings`를 생성하도록 유지하고,
동일 DB에 `SQLiteRepository`를 두 번 생성해도 데이터가 유지되는 테스트를 통과시킨다.

- [ ] **Step 8: Add SettingsService pass-through**

다음 메서드를 추가한다.

```python
def list_work_order_mappings(
    self, active_only: bool = False
) -> list[WorkOrderMapping]:
    return self._repository.list_work_order_mappings(active_only)

def save_work_order_mapping(
    self,
    mapping_id: int | None,
    tracking_no: str,
    equipment_name: str,
    vendor_id: int,
    business_team: str,
    active: bool,
) -> WorkOrderMapping:
    return self._repository.save_work_order_mapping(
        mapping_id,
        tracking_no,
        equipment_name,
        vendor_id,
        business_team,
        active,
    )

def delete_work_order_mapping(self, mapping_id: int) -> None:
    self._repository.delete_work_order_mapping(mapping_id)
```

- [ ] **Step 9: Verify Task 2**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_repository.py tests/test_settings_dialog.py -q --basetemp .pytest-basetemp-work-order-task2-green
```

Expected: repository and existing settings tests pass.

---

### Task 3: Resolve Vendor and Business Team from Tracking Number

**Files:**
- Create: `src/outsource_mail_collector/application/work_order_mapping_service.py`
- Create: `tests/test_work_order_mapping_service.py`
- Modify: `src/outsource_mail_collector/domain/work_report.py`
- Modify: `src/outsource_mail_collector/app.py`
- Modify: `src/outsource_mail_collector/application/work_report_service.py`
- Modify: `tests/test_work_report_service.py`
- Test: `tests/test_work_order_mapping_service.py`
- Test: `tests/test_work_report_service.py`

**Interfaces:**
- Consumes: `SQLiteRepository.list_work_order_mappings(active_only=True)`.
- Produces: `WorkOrderMappingResolution`.
- Produces: `WorkOrderMappingService.resolve(tracking_no, equipment_name)`.
- `WorkReportService` gains a constructor dependency on `WorkOrderMappingService`.

- [ ] **Step 1: Define failing resolver tests**

`tests/test_work_order_mapping_service.py`에 다음 cases를 작성한다.

```python
def test_exact_tracking_maps_vendor_and_team(repository):
    mapping = _mapping(repository, "AB260101", "장비 1")
    result = WorkOrderMappingService(repository).resolve(
        " ab 260101 ", "장비 1"
    )
    assert result.vendor_name == mapping.vendor_name
    assert result.business_team == "PKG"
    assert result.issue_codes == ()
```

```python
def test_equipment_mismatch_keeps_mapping_and_warns(repository):
    _mapping(repository, "AB260101", "장비 1")
    result = WorkOrderMappingService(repository).resolve(
        "AB260101", "장비 2"
    )
    assert result.vendor_name == "협력사A"
    assert result.business_team == "PKG"
    assert result.issue_codes == (
        WorkReportIssueCode.EQUIPMENT_MAPPING_MISMATCH,
    )
```

```python
def test_unregistered_tracking_is_blocked(repository):
    result = WorkOrderMappingService(repository).resolve(
        "UNKNOWN", "장비 1"
    )
    assert result.vendor_name is None
    assert result.issue_codes == (
        WorkReportIssueCode.WORK_ORDER_UNREGISTERED,
    )
```

- [ ] **Step 2: Run resolver tests and verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_work_order_mapping_service.py -q --basetemp .pytest-basetemp-work-order-task3-red
```

Expected: missing service and issue enum values fail collection or assertions.

- [ ] **Step 3: Add stable issue codes**

`WorkReportIssueCode`에 다음을 추가한다.

```python
WORK_ORDER_UNREGISTERED = "WORK_ORDER_UNREGISTERED"
EQUIPMENT_MAPPING_MISMATCH = "EQUIPMENT_MAPPING_MISMATCH"
NIGHT_HEADCOUNT_UNRESOLVED = "NIGHT_HEADCOUNT_UNRESOLVED"
NIGHT_HEADCOUNT_INVALID = "NIGHT_HEADCOUNT_INVALID"
```

`WORK_ORDER_UNREGISTERED`와 `NIGHT_HEADCOUNT_INVALID`는 구조적 차단 집합에,
나머지는 개별 확인 경고 집합에 포함한다.

- [ ] **Step 4: Implement the resolver**

`work_order_mapping_service.py`에 다음 DTO와 서비스를 만든다.

```python
def _normalize_equipment(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split()).casefold()


@dataclass(frozen=True)
class WorkOrderMappingResolution:
    vendor_name: str | None
    business_team: str | None
    issue_codes: tuple[WorkReportIssueCode, ...]


class WorkOrderMappingService:
    def __init__(self, repository: SQLiteRepository) -> None:
        self._repository = repository

    def resolve(
        self, tracking_no: str | None, equipment_name: str | None
    ) -> WorkOrderMappingResolution:
        if not tracking_no:
            return WorkOrderMappingResolution(
                None,
                None,
                (WorkReportIssueCode.WORK_ORDER_UNREGISTERED,),
            )
        normalized = normalize_tracking_no(tracking_no)
        mapping = next(
            (
                candidate
                for candidate in self._repository.list_work_order_mappings(
                    active_only=True
                )
                if candidate.normalized_tracking_no == normalized
            ),
            None,
        )
        if mapping is None:
            return WorkOrderMappingResolution(
                None,
                None,
                (WorkReportIssueCode.WORK_ORDER_UNREGISTERED,),
            )
        issues: tuple[WorkReportIssueCode, ...] = ()
        if _normalize_equipment(mapping.equipment_name) != (
            _normalize_equipment(equipment_name)
        ):
            issues = (
                WorkReportIssueCode.EQUIPMENT_MAPPING_MISMATCH,
            )
        return WorkOrderMappingResolution(
            mapping.vendor_name,
            mapping.business_team,
            issues,
        )
```

수주번호가 없거나 exact normalized mapping이 없으면
`WORK_ORDER_UNREGISTERED`를 반환한다. 장비명 비교는 NFKC, 연속 공백 축약,
`casefold()`를 사용한다.

- [ ] **Step 5: Write failing WorkReportService enrichment test**

`tests/test_work_report_service.py`에 업체와 사업팀이 없는 메일 레코드를 사용한다.

```python
def test_synchronize_enriches_vendor_and_team_from_work_order(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    vendor = repository.save_vendor(None, "협력사A", [], True)
    repository.save_work_order_mapping(
        None, "AB260101", "장비 1", vendor.vendor_id, "PKG", True
    )
    service = _work_report_service(repository)
    record = _review_record(vendor_name=None, business_team=None)

    row = service.synchronize_extracted_records([record])[0]

    assert row.vendor_name == "협력사A"
    assert row.business_team == "PKG"
    assert WorkReportIssueCode.WORK_ORDER_UNREGISTERED not in row.issue_codes
```

- [ ] **Step 6: Inject mapping service**

`WorkReportService.__init__` signature:

```python
def __init__(
    self,
    repository: SQLiteRepository,
    calculation_service: ManDayCalculationService,
    mapping_service: WorkOrderMappingService,
) -> None:
```

`build_services()`에서 하나의 repository로 `WorkOrderMappingService`를 만들고
`WorkReportService`에 전달한다. 테스트 helper도 동일한 생성자 계약을 사용한다.

동기화 시 메일 추출값에 업체·사업팀이 이미 있으면 사용자/메일 값을 덮어쓰지
않는다. 비어 있는 값만 매핑 결과로 채우고 매핑 issue를 행 issue에 합친다.

- [ ] **Step 7: Verify Task 3**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_work_order_mapping_service.py tests/test_work_report_service.py tests/test_smoke.py -q --basetemp .pytest-basetemp-work-order-task3-green
```

Expected: mapping and service wiring tests pass.

---

### Task 4: Calculate Mixed Night Work Without Dropping Valid Headcount

**Files:**
- Modify: `src/outsource_mail_collector/application/man_day_calculation_service.py`
- Modify: `src/outsource_mail_collector/application/models.py`
- Modify: `src/outsource_mail_collector/application/work_report_service.py`
- Modify: `src/outsource_mail_collector/infrastructure/db/repository.py`
- Modify: `tests/test_man_day_calculation_service.py`
- Modify: `tests/test_work_report_service.py`
- Modify: `tests/test_repository.py`
- Test: `tests/test_man_day_calculation_service.py`
- Test: `tests/test_work_report_service.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- `ManDayCalculationService.calculate_daily()` consumes `actual_headcount`, `night_headcount`, and `reported_daily`.
- `WorkReportRow.night_headcount: int | None`.
- `WorkReportRow.per_person_display: str` is a derived property, not a persisted free-form value.

- [ ] **Step 1: Replace daily calculation tests with the approved business rule**

Add these parameterized cases:

```python
@pytest.mark.parametrize(
    ("actual", "night", "reported", "calculated"),
    [
        (2, 0, Decimal("2.0"), Decimal("2.0")),
        (2, 2, Decimal("3.0"), Decimal("3.0")),
        (3, 1, Decimal("3.5"), Decimal("3.5")),
    ],
)
def test_daily_uses_actual_and_night_headcount(
    service, actual, night, reported, calculated
):
    result = service.calculate_daily(
        actual_headcount=actual,
        night_headcount=night,
        reported_daily=reported,
    )
    assert result.calculated == calculated
    assert result.confirmed_candidate == calculated
```

Add validation:

```python
@pytest.mark.parametrize(("actual", "night"), [(2, -1), (2, 3), (2, 0.5)])
def test_invalid_night_headcount_is_rejected(service, actual, night):
    with pytest.raises(ValueError):
        service.calculate_daily(
            actual_headcount=actual,
            night_headcount=night,
            reported_daily=None,
        )
```

- [ ] **Step 2: Run calculation tests and verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_man_day_calculation_service.py -q --basetemp .pytest-basetemp-work-order-task4-red
```

Expected: current signature requires `per_person_man_day` and has no mixed calculation.

- [ ] **Step 3: Implement actual/night calculation**

New signature:

```python
def calculate_daily(
    self,
    *,
    actual_headcount: DecimalInput | None,
    night_headcount: DecimalInput | None,
    reported_daily: DecimalInput | None,
) -> ManDayValues:
```

Parse both counts as non-negative integers and enforce `night <= actual`.

```python
calculated = quantize_man_day(
    Decimal(actual) + Decimal(night) * Decimal("0.5")
)
```

`night_headcount is None`은 계산을 수행하지 않고 caller가
`NIGHT_HEADCOUNT_UNRESOLVED`를 추가할 수 있도록 명시적 `ValueError`를 발생시킨다.
보고값 일치·누락·불일치 처리는 기존 `DAILY_MISSING`,
`DAILY_MISMATCH` 계약을 유지한다.

- [ ] **Step 4: Add derived per-person display**

`WorkReportRow`와 최종 스냅샷 생성이 공통으로 사용할 다음 helper를
`domain/work_report.py`에 구현한다.

```python
def man_day_basis(
    actual_headcount: int | None,
    night_headcount: int | None,
) -> str:
    if actual_headcount is None or night_headcount is None:
        return "확인 필요"
    if night_headcount == 0:
        return "1.0"
    if night_headcount == actual_headcount:
        return "1.5"
    return "혼합"
```

`per_person_man_day`는 uniform 행에서만 `Decimal("1.0")` 또는
`Decimal("1.5")`, mixed/unresolved 행에서는 `None`으로 둔다.

- [ ] **Step 5: Write failing WorkReportService preservation tests**

```python
def test_mixed_night_row_preserves_headcounts_and_calculates_daily(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service_with_mapping(repository)
    row = service.synchronize_extracted_records(
        [_review_record(actual_headcount=3, night_headcount=1, daily_man_day=3.5)]
    )[0]

    assert row.actual_headcount == 3
    assert row.night_headcount == 1
    assert row.per_person_man_day is None
    assert row.calculated_daily_man_day == Decimal("3.5")
    assert row.confirmed_daily_man_day == Decimal("3.5")
    assert WorkReportIssueCode.INVALID_VALUE not in row.issue_codes
```

```python
def test_missing_night_count_keeps_valid_actual_headcount(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service_with_mapping(repository)
    row = service.synchronize_extracted_records(
        [_review_record(actual_headcount=3, night_headcount=None)]
    )[0]

    assert row.actual_headcount == 3
    assert row.night_headcount is None
    assert WorkReportIssueCode.NIGHT_HEADCOUNT_UNRESOLVED in row.issue_codes
```

- [ ] **Step 6: Refactor `_calculate_values` to parse fields independently**

현재 하나의 `try`가 실제 인원과 인당 공수 전체를 `None`으로 만드는 구조를
분리한다.

- 실제 인원은 자체 parse 결과를 항상 보존한다.
- 야근 인원은 자체 parse하고 유효하지 않으면 `NIGHT_HEADCOUNT_INVALID`.
- 야근 미기재는 `NIGHT_HEADCOUNT_UNRESOLVED`.
- 둘 다 유효할 때만 `calculate_daily()`를 호출한다.
- mapping issue, 날짜 issue, 공수 issue를 중복 없이 합친다.

- [ ] **Step 7: Persist night headcount**

`StoredWorkReportRow`, insert/update/select conversion에 `night_headcount`를
추가한다. `StoredFinalReportRow`와 snapshot 처리는 Task 7에서 최종 표시값
호환성과 함께 변경한다.

repository round-trip test에 다음을 추가한다.

```python
assert stored.night_headcount == 1
```

- [ ] **Step 8: Keep manual row compatibility**

`WorkReportService.add_manual_row()`과 `update_row()`에서
`night_headcount`를 전달한다. 기존 `per_person_man_day` 호출자는 Task 6에서
UI를 변경할 때 제거하므로 이 Task에서는 test helper를 새 signature로 일괄
갱신한다.

- [ ] **Step 9: Verify Task 4**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_man_day_calculation_service.py tests/test_work_report_service.py tests/test_repository.py -q --basetemp .pytest-basetemp-work-order-task4-green
```

Expected: calculation, persistence, and service tests pass.

---

### Task 5: Add the Work Order Master Settings Tab

**Files:**
- Modify: `src/outsource_mail_collector/ui/settings_dialog.py`
- Modify: `tests/test_settings_dialog.py`
- Test: `tests/test_settings_dialog.py`

**Interfaces:**
- Consumes: Task 2 `SettingsService` work-order CRUD.
- Produces: `SettingsDialog.work_order_table` with mapping ID stored in column 0 `UserRole`.

- [ ] **Step 1: Write failing UI round-trip test**

```python
def test_settings_dialog_saves_work_order_mapping(tmp_path):
    _app()
    repository = SQLiteRepository(tmp_path / "collector.db")
    vendor = repository.save_vendor(None, "협력사A", [], True)
    dialog = SettingsDialog(SettingsService(repository, FakeOutlookAdapter()))

    row = dialog.add_work_order_row()
    dialog.work_order_table.setItem(row, 0, QTableWidgetItem("AB260101"))
    dialog.work_order_table.setItem(row, 1, QTableWidgetItem("장비 1"))
    dialog.work_order_table.cellWidget(row, 2).setCurrentIndex(0)
    dialog.work_order_table.setItem(row, 3, QTableWidgetItem("PKG"))

    dialog.save()

    mapping = repository.list_work_order_mappings()[0]
    assert mapping.normalized_tracking_no == "AB260101"
    assert mapping.vendor_id == vendor.vendor_id
    assert mapping.business_team == "PKG"
```

- [ ] **Step 2: Run UI test and verify failure**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.venv\Scripts\python.exe -m pytest tests/test_settings_dialog.py::test_settings_dialog_saves_work_order_mapping -v --basetemp .pytest-basetemp-work-order-task5-red
```

Expected: `work_order_table` and `add_work_order_row` do not exist.

- [ ] **Step 3: Build the tab**

Add a `수주 마스터` tab with columns:

```python
["수주번호", "장비명", "업체", "사업팀", "활성"]
```

업체 열은 `QComboBox`이며 `SettingsService.list_vendors(active_only=True)`의
표준 업체명과 `vendor_id`를 item data로 가진다.

- [ ] **Step 4: Load, add, delete, and save mappings**

Dialog state:

```python
self._deleted_work_order_ids: set[int] = set()
```

Public test helper signature:

`add_work_order_row(self, mapping: WorkOrderMapping | None = None) -> int`

저장 시 수주번호, 장비명, 업체 선택, 사업팀이 모두 있어야 한다.
중복/빈 값 오류는 기존 dialog save 예외 흐름을 유지하며 부분 삭제를 완료 상태로
기록하지 않는다.

- [ ] **Step 5: Verify Task 5**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.venv\Scripts\python.exe -m pytest tests/test_settings_dialog.py -q --basetemp .pytest-basetemp-work-order-task5-green
```

Expected: settings dialog tests pass.

---

### Task 6: Update Review and Manual Input UI for Night Headcount

**Files:**
- Modify: `src/outsource_mail_collector/ui/manual_row_dialog.py`
- Modify: `src/outsource_mail_collector/ui/review_grid.py`
- Modify: `src/outsource_mail_collector/ui/problem_review_dialog.py`
- Modify: `src/outsource_mail_collector/ui/main_window.py`
- Modify: `tests/test_manual_row_dialog.py`
- Modify: `tests/test_review_grid.py`
- Modify: `tests/test_problem_review_dialog.py`
- Modify: `tests/test_main_window.py`
- Test: corresponding four test files

**Interfaces:**
- Consumes: `WorkReportRow.night_headcount` and derived `man_day_basis`.
- Produces: manual row values with `night_headcount`, without user-entered numeric `per_person_man_day`.

- [ ] **Step 1: Write failing ManualRowDialog tests**

```python
def test_manual_row_collects_actual_and_night_headcount():
    dialog = ManualRowDialog()
    dialog.vendor_edit.setText("협력사A")
    dialog.tracking_edit.setText("AB260101")
    dialog.equipment_edit.setText("장비 1")
    dialog.business_team_edit.setText("PKG")
    dialog.headcount_edit.setText("3")
    dialog.night_headcount_edit.setText("1")
    dialog.reported_daily_edit.setText("3.5")
    dialog.note_edit.setText("주말 작업 확인")
    values = dialog.values()
    assert values["actual_headcount"] == 3
    assert values["night_headcount"] == 1
    assert "per_person_man_day" not in values
```

야근 인원 4, 실제 인원 3은 `ValueError`여야 한다.

- [ ] **Step 2: Write failing ReviewGrid mixed display test**

`tests/test_review_grid.py`의 row factory에 `night_headcount=1`을 추가하고:

```python
assert grid.horizontalHeaderItem(7).text() == "야근 인원"
assert grid.item(0, 9).text() == "혼합"
```

열 인덱스는 selector와 신규 야근 열을 포함해 실제 `_COLUMNS` 순서에 맞춰
테스트에서 명시적으로 검증한다.

- [ ] **Step 3: Run UI tests and verify failure**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.venv\Scripts\python.exe -m pytest tests/test_manual_row_dialog.py tests/test_review_grid.py tests/test_problem_review_dialog.py tests/test_main_window.py -q --basetemp .pytest-basetemp-work-order-task6-red
```

Expected: missing night controls/columns and outdated service call signatures fail.

- [ ] **Step 4: Update ManualRowDialog**

- `야근 인원` input을 실제 인원 다음에 추가한다.
- 사용자가 입력하던 `인당 공수` 필드는 제거한다.
- `_headcount()`를 actual과 night에 재사용하고 `night <= actual`을 검증한다.
- `values()`는 `night_headcount`를 반환한다.

- [ ] **Step 5: Update review grid**

열 순서:

```python
"실제 작업인원",
"야근 인원",
"인당 공수",
```

인당 공수 셀은 `man_day_basis(row.actual_headcount, row.night_headcount)`를
사용한다. 이후 포함·작업 열 인덱스를 신규 열 수에 맞게 갱신한다.

- [ ] **Step 6: Update problem review and main window**

`ProblemReviewDialog`는 unresolved/invalid night issue를 검토할 수 있도록 실제
인원과 야근 인원 입력을 선택적으로 제공한다. 반환 changes:

```python
{
    "actual_headcount": 3,
    "night_headcount": 1,
    "confirmed_daily_man_day": Decimal("3.5"),
    "confirmed_cumulative_man_day": Decimal("10.0"),
    "resolution_note": "혼합 야근 인원 확인",
}
```

`MainWindow`는 이 값들을 `WorkReportService.update_row()`와 `confirm_row()`에
명시적으로 전달한다. 기존 duplicate 처리 흐름은 변경하지 않는다.

- [ ] **Step 7: Verify Task 6**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.venv\Scripts\python.exe -m pytest tests/test_manual_row_dialog.py tests/test_review_grid.py tests/test_problem_review_dialog.py tests/test_main_window.py -q --basetemp .pytest-basetemp-work-order-task6-green
```

Expected: updated UI tests pass.

---

### Task 7: Finalize and Render Mixed Rows

**Files:**
- Modify: `src/outsource_mail_collector/application/final_report_service.py`
- Modify: `src/outsource_mail_collector/application/report_renderer.py`
- Modify: `src/outsource_mail_collector/application/models.py`
- Modify: `src/outsource_mail_collector/infrastructure/db/repository.py`
- Modify: `tests/test_final_report_service.py`
- Modify: `tests/test_report_renderer.py`
- Modify: `tests/test_final_report_dialog.py`
- Test: corresponding test files

**Interfaces:**
- Consumes: persisted `night_headcount`.
- Produces: `FinalReportRow.night_headcount`.
- Produces: `FinalReportRow.man_day_basis: str`.
- Produces: ten-column HTML/plain-text report with `혼합` basis.

- [ ] **Step 1: Write failing finalization tests**

Add a mixed included row:

```python
row = _stored_row(
    actual_headcount=3,
    night_headcount=1,
    per_person_man_day=None,
    confirmed_daily_man_day=Decimal("3.5"),
    confirmed_cumulative_man_day=Decimal("20.0"),
)
preview = service.preview(date(2026, 7, 29), date(2026, 7, 29))
assert preview.can_confirm
```

`night_headcount=None` with unresolved issue must remain unconfirmable.

- [ ] **Step 2: Write failing renderer test**

Update approved headers to ten columns and assert:

```python
assert "실제 작업인원\t야근 인원\t인당 공수" in rendered.plain_text
assert "3\t1\t혼합\t3.5\t20.0" in rendered.plain_text
```

Repeated two-date headers must count 20 `<th` elements.

- [ ] **Step 3: Run final report tests and verify failure**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.venv\Scripts\python.exe -m pytest tests/test_final_report_service.py tests/test_report_renderer.py tests/test_final_report_dialog.py -q --basetemp .pytest-basetemp-work-order-task7-red
```

Expected: current per-person required blocker and nine-column renderer fail.

- [ ] **Step 4: Adjust finalization blockers**

Required numeric identity:

```python
mixed = (
    row.actual_headcount is not None
    and row.night_headcount is not None
    and 0 < row.night_headcount < row.actual_headcount
)
```

`per_person_man_day is None` is allowed only when `mixed` is true. Vendor,
사업팀, actual, night, item identity, confirmed daily, confirmed cumulative
requirements remain.

- [ ] **Step 5: Persist night count and display basis in immutable snapshots**

기존 `final_report_rows.per_person_man_day`는 SQLite `TEXT NOT NULL`이므로
구버전 DB 호환성을 위해 열을 nullable로 재작성하지 않는다. 신규 snapshot에는
이 열에 최종 표시값 `"1.0"`, `"1.5"`, `"혼합"`을 저장한다.

`StoredFinalReportRow`와 `FinalReportRow`는 숫자 대신 다음 필드를 노출한다.

```python
night_headcount: int | None
man_day_basis: str
```

snapshot insert 시:

```python
basis = man_day_basis(row.actual_headcount, row.night_headcount)
```

`per_person_man_day` DB 열에는 `basis` 문자열을 쓰고 select에서는
`str(row["per_person_man_day"])`를 `man_day_basis`로 반환한다. 기존 snapshot의
`"1.0"`, `"1.5"` 값은 그대로 호환된다.

`_snapshot_hash()` payload에는 `night_headcount`와 `man_day_basis`를 포함한다.
과거 snapshot의 NULL night는 야근 인원 빈칸으로 표시하되 기존
`per_person_man_day` 문자열은 인당 공수 표시에 유지한다. 기존 snapshot row를
수정하지 않는다.

- [ ] **Step 6: Render ten columns**

`_HEADERS`에 `야근 인원`을 추가한다. `_row_values()`:

```python
str(row.night_headcount) if row.night_headcount is not None else "",
row.man_day_basis,
```

HTML과 plain text 모두 동일한 tuple을 사용한다.

- [ ] **Step 7: Verify Task 7**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.venv\Scripts\python.exe -m pytest tests/test_final_report_service.py tests/test_report_renderer.py tests/test_final_report_dialog.py -q --basetemp .pytest-basetemp-work-order-task7-green
```

Expected: finalization and renderer tests pass.

---

### Task 8: Full Regression, Documentation, and Safe Real-Environment Recheck

**Files:**
- Modify: `docs/PRD.md`
- Modify: `docs/TRD.md`
- Modify: `docs/SYSTEM_ARCHITECTURE.md`
- Modify: `docs/ADR.md`
- Modify: `HANDOFF.md`
- Test: full `tests/`

**Interfaces:**
- Consumes: all previous task outputs.
- Produces: synchronized requirements/design docs and evidence-backed handoff.

- [ ] **Step 1: Update governing docs**

Record these exact decisions:

- 수주번호 exact mapping supplies 업체 and 사업팀.
- 장비명 mismatch warns but does not replace the exact tracking mapping.
- `투입 공수` is reported daily man-day.
- calculated daily is `actual + night × 0.5`.
- per-person display is `1.0`, `1.5`, or `혼합`.
- final table contains `야근 인원`.
- unregistered work order and invalid night count block finalization.

- [ ] **Step 2: Run focused regression**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.venv\Scripts\python.exe -m pytest tests/test_extraction_pipeline.py tests/test_repository.py tests/test_work_order_mapping_service.py tests/test_man_day_calculation_service.py tests/test_work_report_service.py tests/test_settings_dialog.py tests/test_review_grid.py tests/test_manual_row_dialog.py tests/test_problem_review_dialog.py tests/test_final_report_service.py tests/test_report_renderer.py tests/test_final_report_dialog.py tests/test_main_window.py -q --basetemp .pytest-basetemp-work-order-focused
```

Expected: all focused tests pass.

- [ ] **Step 3: Run full automated verification**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-basetemp-work-order-full
```

Expected: zero failures.

- [ ] **Step 4: Run static and document checks**

Run:

```powershell
.venv\Scripts\python.exe -m compileall -q src tests
git diff --check
.venv\Scripts\python.exe -c "from pathlib import Path; [p.read_text(encoding='utf-8', errors='strict') for p in [Path('HANDOFF.md'), *Path('docs').rglob('*.md')]]; print('STRICT_UTF8=ok')"
```

Expected: exit code 0 and `STRICT_UTF8=ok`.

- [ ] **Step 5: Prepare a fresh test DB**

Use SQLite backup API to copy the current live DB to a new ignored path such as:

```text
local-test/collector-work-order-realcheck-20260729.db
```

Verify `PRAGMA integrity_check = ok` and `git check-ignore` before use. Do not
overwrite the existing live DB or previous test DB.

- [ ] **Step 6: Add test-only master mappings**

In the fresh test DB only, register the approved mappings needed for the
2026-07-27 mail. Do not print actual sensitive values in logs or HANDOFF.
Verify the mapping count and active status only.

- [ ] **Step 7: Run approved Outlook read-only recheck**

With explicit user approval for 2026-07-27:

- initialize COM in the worker/current thread;
- use the fresh test DB;
- collect one registered sender message;
- synchronize extracted records;
- print counts and issue codes only;
- compare every in-range mail item's unread state before/after;
- do not display, move, delete, reply, forward, or send.

Expected:

- two rows retain tracking number and equipment name;
- actual/night/reported daily values are populated;
- calculated daily matches reported daily;
- work-order mappings populate vendor and business team;
- no `INVALID_VALUE`, `SERIES_KEY_MISSING`, or `WORK_ORDER_UNREGISTERED`;
- unread state mutations equal zero.

- [ ] **Step 8: Update HANDOFF**

Record:

- decisions and changed files;
- focused/full/static verification commands and exact results;
- any failed checks and root causes;
- real Outlook verification boundary and read-state result;
- unrun Excel/GUI checks;
- remaining risks;
- no commit/push unless separately requested.

---

## Completion Gate

Implementation is complete only when:

- Tasks 1–7 focused tests pass;
- the full suite has zero failures;
- compileall, `git diff --check`, and strict UTF-8 checks pass;
- a fresh ignored test DB passes integrity check;
- the approved 2026-07-27 Outlook read-only recheck produces populated mapping,
  headcount, night count, and daily man-day fields with zero read-state mutations;
- no real Excel write or Outlook mutation occurred;
- `HANDOFF.md` distinguishes automated verification from GUI/Outlook/Excel
  verification;
- no commit or push was performed without explicit user instruction.
