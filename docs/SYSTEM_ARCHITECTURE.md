# System Architecture — 업무보고 메일 자동 추출·Excel 취합 프로그램

## 1. 아키텍처 원칙

1. Outlook, 분석, 검토, Excel 반영을 분리한다.
2. 메일 읽기와 Excel 쓰기를 직접 결합하지 않는다.
3. 추출 결과는 항상 중간 데이터 모델을 거친다.
4. 사용자의 승인 전에는 Excel에 쓰지 않는다.
5. 모든 처리 단계는 재실행 가능하고 추적 가능해야 한다.
6. 외부 AI 없이도 핵심 기능이 동작해야 한다.
7. 보안상 Outlook은 읽기 전용으로 사용한다.

---

## 2. 논리 아키텍처

```text
┌──────────────────────────────────────────────────────────┐
│                    Windows Desktop App                   │
├──────────────────────────────────────────────────────────┤
│ UI Layer                                                 │
│ - 날짜 선택                                              │
│ - 메일 불러오기                                          │
│ - 검토 그리드                                            │
│ - 설정/담당자/업체 관리                                  │
│ - Excel 반영                                             │
├──────────────────────────────────────────────────────────┤
│ Application Services                                     │
│ - Mail Collection Service                                │
│ - Extraction Orchestrator                                │
│ - Review Service                                         │
│ - Duplicate Service                                      │
│ - Excel Export Service                                   │
├──────────────────────────────────────────────────────────┤
│ Domain Layer                                             │
│ - MailRecord                                             │
│ - EquipmentSection                                       │
│ - OutsourceWorkRecord                                    │
│ - ValidationResult                                       │
│ - ProcessingHistory                                      │
├──────────────────────────────────────────────────────────┤
│ Infrastructure                                           │
│ - Outlook COM Adapter                                    │
│ - Excel COM Adapter                                      │
│ - SQLite Repository                                      │
│ - File Backup Service                                    │
│ - Logger                                                 │
└──────────────────────────────────────────────────────────┘
           │                          │
           ▼                          ▼
┌──────────────────┐        ┌────────────────────┐
│ Outlook 2019     │        │ Existing Excel    │
│ Inbox / Folder   │        │ Workbook          │
└──────────────────┘        └────────────────────┘
```

---

## 3. 처리 흐름

```text
[사용자 날짜 선택]
        │
        ▼
[Outlook 연결]
        │
        ▼
[받은편지함 날짜 필터]
        │
        ▼
[등록 담당자 기준 후보 메일 선별]
        │
        ▼
[HTML/텍스트 정규화]
        │
        ▼
[장비 구간 분리]
        │
        ▼
[업체·인원·당일·누적 추출]
        │
        ▼
[검증 및 신뢰도 계산]
        │
        ▼
[중복/수정본 판정]
        │
        ▼
[검토 그리드]
        │
        ├── 검토 필요 → 사용자 수정
        │
        └── 정상 → 승인
        │
        ▼
[Excel 반영 전 백업]
        │
        ▼
[원본 데이터 시트 행 추가]
        │
        ▼
[처리 이력 저장]
```

---

## 4. 컴포넌트 상세

### 4.1 Presentation Layer

#### MainWindow

- 날짜 선택
- Outlook 폴더 선택
- 메일 불러오기
- 처리 요약 표시
- 검토 표 표시
- Excel 반영 요청

#### SettingsWindow

- 담당자 목록
- 업체 목록
- Excel 경로
- 백업 경로
- 키워드
- 규칙 설정

UI는 분석 로직을 직접 호출하지 않고 Application Service만 호출한다.

---

### 4.2 Application Layer

#### MailCollectionService

- Outlook Adapter 호출
- 날짜 범위 계산
- 등록 담당자 기준 필터
- 미보고 담당자 계산

#### ExtractionOrchestrator

각 메일에 대해 다음 파이프라인을 실행한다.

```text
normalize
→ classify
→ split_sections
→ extract_fields
→ validate
→ detect_duplicates
```

#### ReviewService

- 사용자 수정 반영
- 상태 변경
- 반영 제외
- 검토 완료 처리
- 변경 전후 이력 생성

#### ExcelExportService

- 검토 완료 레코드만 선택
- 백업 생성
- Excel Adapter 호출
- 성공 시 DB 상태 갱신
- 실패 시 DB 롤백

---

### 4.3 Domain Layer

도메인 객체는 Outlook COM 또는 Excel 셀 객체를 직접 참조하지 않는다.

#### MailRecord

메일 메타데이터와 원문을 보유한다.

#### EquipmentSection

한 메일의 장비별 구간을 나타낸다.

#### OutsourceWorkRecord

Excel에 반영 가능한 최소 단위다.

#### ValidationResult

- errors
- warnings
- confidence
- review_status

---

### 4.4 Infrastructure Layer

#### OutlookComAdapter

- Outlook COM 객체 캡슐화
- COM 예외를 애플리케이션 예외로 변환
- Exchange SMTP 주소 변환
- 원본 메일 열기 기능 제공

#### ExcelComAdapter

- Excel COM 객체 캡슐화
- 파일 열기·잠금 확인
- 시트 및 헤더 확인
- 행 추가
- 저장·닫기

#### SQLiteRepository

- 설정
- 담당자
- 업체
- 처리 메일
- 추출 레코드
- 변경 이력

#### BackupService

- 파일명 예시:
  `전장의주_집계표_20260723_081530_backup.xlsx`
- 반영 전 원본 파일 복사
- 동일 경로 실패 시 중단

---

## 5. 데이터 흐름 경계

### Outlook → 애플리케이션

허용 데이터:

- EntryID
- 제목
- 발신자
- 수신일
- Body
- HTMLBody

금지 동작:

- 메일 삭제
- 메일 이동
- 읽음/안읽음 변경
- 자동 회신
- 첨부파일 외부 전송

### 애플리케이션 → Excel

허용 데이터:

- 검토 완료된 구조화 레코드
- 처리 시각
- 원본 메일 식별값

원칙:

- 메일 본문 전체를 Excel에 저장하지 않는다.
- 원본 추적이 필요한 경우 EntryID와 제목만 저장한다.

---

## 6. 배포 아키텍처

```text
사용자 PC
├─ Outlook 2019
├─ Excel 2019
└─ 업무보고 취합 프로그램
   ├─ app.exe
   ├─ config/
   ├─ app_data.db
   ├─ logs/
   └─ backups/
```

권장 사용자 데이터 경로:

```text
%LOCALAPPDATA%\OutsourceMailCollector\
├─ app_data.db
├─ logs\
├─ backups\
└─ settings.json
```

애플리케이션 설치 폴더와 사용자 데이터를 분리한다.

---

## 7. 스레딩 모델

- UI 스레드: 화면 갱신
- Outlook Worker: Outlook COM 조회
- Parser Worker: 본문 분석
- Excel Worker: Excel 반영

주의:

- 각 COM Worker는 자체 스레드에서 `CoInitialize`/`CoUninitialize` 수행
- COM 객체를 스레드 간 전달하지 않음
- Worker는 순수 데이터 객체만 UI에 반환

---

## 8. 오류 복구 전략

### Outlook 조회 실패

- 재시도 1회
- 실패 시 사용자에게 Outlook 실행·프로필 상태 안내
- DB나 Excel은 변경하지 않음

### 일부 메일 분석 실패

- 다른 메일 처리는 계속
- 실패 메일을 `형식 미지원`으로 표시
- 원본 메일 열기 제공

### Excel 반영 실패

- 백업 유지
- 처리 이력은 성공으로 마킹하지 않음
- 부분 반영 여부 확인
- 가능한 경우 추가한 행 삭제 후 롤백

---

## 9. 확장 포인트

### 규칙 플러그인

작성자별 형식이 크게 다를 경우:

```text
parsers/
├─ default_parser.py
├─ author_a_parser.py
└─ author_b_parser.py
```

### AI 보조 분석

향후 사내 허용 환경에서만 추가:

```text
Rule-based Parser
        │
        ├─ confidence >= threshold → 정상
        └─ confidence < threshold  → AI Adapter
```

AI Adapter는 인터페이스로 분리해 외부 API, 사내 모델, 로컬 모델을 교체할 수 있게 한다.

---

## 10. 핵심 설계 결정

1. 받은편지함 전체를 조회하되 등록 담당자 기준으로 우선 필터링한다.
2. 제목은 보조 조건이며 단독 필터로 사용하지 않는다.
3. Excel 직접 입력 전에 검토 그리드를 둔다.
4. 원본 데이터 시트에 행 단위로 저장한다.
5. Outlook EntryID와 레코드 해시를 함께 사용해 중복을 방지한다.

## 11. 상세 공수표 취합 확장

```text
Outlook read-only
  → ExtractionOrchestrator
  → WorkDateResolver
  → WorkReportService
      ├─ ManDayCalculationService
      └─ SQLite work_report_rows
  → FinalReportService
  → immutable final_report_rows
  → HtmlReportRenderer
  → Qt Clipboard (HTML + plain text)
  → 사용자가 Outlook 본문에 붙여 넣기
```

- `domain/`은 날짜 출처, 행 출처, 문제 코드와 공수 값 형식만 정의하며 PySide6,
  Outlook, Excel, SQLite에 의존하지 않는다.
- `parsing/`의 작업일 판정은 제목을 우선하고 본문·수신일 불일치 근거만 반환한다.
- `application/`은 보고값, 계산값, 확정값을 분리하고 최초 누적 기준을 추정하지
  않는다.
- `infrastructure/db/`는 취합 후보와 최종 스냅샷을 별도 테이블에 저장한다.
- `ui/`는 계산하지 않고 서비스 결과를 표시하며 수동 입력과 검토 결정을 전달한다.
- 클립보드 복사 성공 후에만 복사 시각을 기록한다.
- 원본 행 변경은 현재 최종 확인을 무효화하지만 이전 스냅샷을 수정하지 않는다.

이번 확장은 Outlook 쓰기, 메일 자동 발송, Excel 쓰기를 추가하지 않는다.
6. 메일 분석 실패는 전체 작업 중단이 아니라 개별 검토 대상으로 처리한다.
7. 외부 AI는 MVP 범위에서 제외한다.
