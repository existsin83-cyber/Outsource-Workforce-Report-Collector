# TRD — 업무보고 메일 자동 추출·Excel 취합 프로그램

## 1. 기술 목표

Outlook 2019 Desktop 64비트에서 선택 날짜의 업무보고 메일을 직접 조회하고, 규칙 기반으로 장비별 외주업체·인원·공수 데이터를 추출한 뒤, 사용자의 검토를 거쳐 기존 Excel 파일에 안전하게 반영하는 Windows 데스크톱 애플리케이션을 구현한다.

---

## 2. 대상 환경

- OS: Windows 10/11 64비트
- Office: Microsoft Office Professional Plus 2019
- Outlook: Outlook 2019 MSO 64비트
- Excel: Office 2019 Excel
- 메일 위치: 기본 받은편지함
- 예상 메일 수: 하루 약 20통
- 예상 담당자 수: 약 20명
- 네트워크: 외부 인터넷 연결 없이도 핵심 기능 동작
- 권장 언어: Python 3.12
- 권장 배포: PyInstaller 기반 단일 실행 파일 또는 사내 설치형 패키지

---

## 3. 권장 기술 스택

### 3.1 애플리케이션

- Python 3.12
- PySide6: Windows GUI
- pywin32: Outlook/Excel COM 연동
- BeautifulSoup4 또는 lxml: HTML 본문 정리
- regex: 패턴 추출
- pydantic: 데이터 검증
- pandas: 검토용 테이블 및 데이터 변환
- openpyxl: Excel 구조 점검 및 보조 처리
- sqlite3: 처리 이력·설정·중복 키 저장
- loguru 또는 표준 logging: 로그
- pytest: 테스트
- PyInstaller: 실행 파일 패키징

### 3.2 COM 사용 원칙

- Outlook: 읽기 전용 접근
- Excel: COM 기반으로 실제 Excel 파일 열기·쓰기
- Excel 구조 분석은 openpyxl로 보조 가능하나, 수식·외부 연결·병합·서식 보존이 중요하면 최종 반영은 Excel COM을 우선 사용

---

## 4. 시스템 구성요소

1. UI Layer
2. Application Service Layer
3. Outlook Adapter
4. Mail Normalizer
5. Mail Classifier
6. Equipment Section Parser
7. Outsource Data Extractor
8. Validation & Confidence Engine
9. Review State Manager
10. Excel Adapter
11. Duplicate Detection Service
12. SQLite Repository
13. Configuration Manager
14. Logging & Error Handler

---

## 5. 주요 모듈 설계

### 5.1 outlook_adapter.py

책임:

- Outlook Application 연결
- MAPI Namespace 획득
- 지정 폴더 조회
- 날짜 범위 필터
- 발신자 정보 획득
- MailItem 필드 읽기
- 원본 메일 열기

주요 인터페이스:

```python
class OutlookAdapter:
    def connect(self) -> None: ...
    def list_messages(
        self,
        folder_path: str,
        start_at: datetime,
        end_at: datetime,
    ) -> list[MailEnvelope]: ...
    def open_message(self, entry_id: str) -> None: ...
```

주의사항:

- Outlook COM 객체는 생성 스레드에서 사용
- UI 스레드와 COM 작업 스레드 분리 시 `pythoncom.CoInitialize()` 호출
- Restrict 필터의 날짜 형식은 Outlook 로캘 영향을 고려
- 발신자 Exchange 주소는 SMTP 주소로 변환 필요

### 5.2 mail_normalizer.py

책임:

- HTML 본문에서 텍스트 추출
- `<br>`, `<p>`, 표 셀을 의미 있는 줄바꿈으로 변환
- non-breaking space 제거
- 중복 공백 정리
- 원본 줄 구조 최대한 보존

출력:

```python
NormalizedMailBody(
    plain_text: str,
    lines: list[str],
    source_html: str | None,
)
```

### 5.3 mail_classifier.py

책임:

- 대상 담당자 여부 판정
- 보고일 판정
- 업무보고 가능성 점수 계산
- 제목은 보조 신호로만 사용

예시 점수:

- 등록 담당자 발신: +50
- 선택 날짜 수신: +20
- 제목에 업무/보고 포함: +10
- 본문에 외주인원/작업내용/수주번호 포함: +20
- 광고/자동발송 주소: -100

임계값 이상만 대상 후보로 표시하되, 경계값 메일은 사용자가 포함할 수 있게 한다.

### 5.4 section_parser.py

책임:

- 메일 본문을 장비 단위 구간으로 분리
- 다음 패턴을 조합
  - `1.`, `2)`, `■`, `◆`
  - Tracking No.
  - 수주번호
  - 장비명
  - 고객사명
  - 호기 표기 `#7`, `7호기`

출력:

```python
EquipmentSection(
    section_index: int,
    heading: str | None,
    tracking_no: str | None,
    equipment_name: str | None,
    raw_text: str,
    split_confidence: float,
)
```

### 5.5 outsource_extractor.py

책임:

- 외주인원 영역 탐색
- 업체명 매칭
- 인원·공수·누적값 추출
- 주간/야간 구분
- 장비 구간과 연결

추출 우선순위:

1. 명시적 레이블 기반
2. 업체 마스터 기반
3. 근접 문맥 기반
4. 미확정 후보 반환

정규식 예시:

```python
VENDOR_LABEL = r"(?:외주업체|업체명)\s*[:：]?\s*(?P<vendor>[^\n,;/]+)"
HEADCOUNT = r"(?P<count>\d+(?:\.\d+)?)\s*(?:명|인)"
MAN_DAY = r"(?P<value>\d+(?:\.\d+)?)\s*공수"
CUMULATIVE = r"(?:누적\s*공수|누적공수|누계)\s*[:：]?\s*(?P<value>\d+(?:\.\d+)?)"
DAY = r"(?:주간|당일)\s*[:：]?\s*(?P<value>\d+(?:\.\d+)?)\s*공수"
NIGHT = r"야간\s*[:：]?\s*(?P<value>\d+(?:\.\d+)?)\s*공수"
```

주의:

- 정규식 하나로 모든 형식을 처리하지 않는다.
- 토큰 주변의 레이블과 줄 위치를 함께 평가한다.
- 누적값이 당일값보다 크다는 이유만으로 의미를 추정하지 않는다.

### 5.6 validation_engine.py

책임:

- 필수값 검증
- 논리 충돌 판정
- 신뢰도 계산
- 검토 상태 지정

검토 조건 예시:

- 누적 공수만 존재
- 업체명은 있으나 당일값 없음
- 장비명 또는 Tracking No. 둘 다 없음
- 같은 구간에 누적값 후보가 2개 이상
- 실제 인원이 소수
- 누적 공수 < 당일 공수
- 업체 마스터 미등록
- 동일 장비·업체에 상충하는 값 존재

### 5.7 duplicate_service.py

키 구성:

```text
mail_entry_id
+ report_date
+ sender_email
+ tracking_no
+ equipment_name
+ vendor_name
```

해시:

- SHA-256 사용
- 원문 공백·대소문자 정규화 후 생성

수정본 판정:

- 동일 보고일·발신자이지만 다른 EntryID
- 제목에 수정/재송부/재발송 포함
- 핵심 레코드 키는 같지만 값이 다름

### 5.8 excel_adapter.py

책임:

- Excel 실행 또는 기존 인스턴스 연결
- 파일 잠금 확인
- 반영 전 백업
- 시트 존재 여부 확인
- 테이블 헤더 매핑
- 행 추가
- 저장
- 오류 시 롤백 또는 백업 안내

권장 저장 순서:

1. 대상 파일 경로 확인
2. 읽기 전용 여부 확인
3. 백업 파일 생성
4. Excel COM으로 파일 열기
5. 원본 시트 확인 또는 생성
6. 검토 완료 행만 추가
7. 저장
8. 처리 이력 커밋

중간 오류 시 DB 처리 완료 상태를 기록하지 않는다.

---

## 6. 데이터베이스 설계

SQLite 파일: `app_data.db`

### tables

#### settings

- key TEXT PRIMARY KEY
- value TEXT
- updated_at TEXT

#### employees

- employee_id INTEGER PRIMARY KEY
- name TEXT
- email TEXT UNIQUE
- active INTEGER
- aliases_json TEXT

#### vendors

- vendor_id INTEGER PRIMARY KEY
- canonical_name TEXT UNIQUE
- aliases_json TEXT
- active INTEGER

#### processed_mails

- mail_entry_id TEXT PRIMARY KEY
- subject TEXT
- sender_email TEXT
- received_at TEXT
- report_date TEXT
- content_hash TEXT
- status TEXT
- processed_at TEXT

#### extracted_records

- record_id TEXT PRIMARY KEY
- mail_entry_id TEXT
- report_date TEXT
- sender_email TEXT
- tracking_no TEXT
- equipment_name TEXT
- vendor_name TEXT
- actual_headcount REAL
- daily_man_day REAL
- cumulative_man_day REAL
- confidence REAL
- review_status TEXT
- raw_section TEXT
- created_at TEXT
- updated_at TEXT

#### action_logs

- log_id INTEGER PRIMARY KEY AUTOINCREMENT
- action TEXT
- entity_id TEXT
- before_json TEXT
- after_json TEXT
- result TEXT
- error_message TEXT
- created_at TEXT

---

## 7. UI 요구사항

### 메인 화면

상단:

- 조회 날짜
- Outlook 폴더
- 업무보고 불러오기
- 설정

요약 영역:

- 대상 담당자 수
- 수신 메일 수
- 정상
- 검토 필요
- 미보고
- 중복 의심

검토 그리드:

- 체크박스
- 보고일
- 작성자
- 장비명
- Tracking No.
- 업체
- 실제 인원
- 당일 공수
- 누적 공수
- 신뢰도
- 상태
- 원본 열기

하단:

- 선택 행 제외
- 검토 완료
- Excel 반영
- 로그 보기

### 설정 화면

- 담당자 관리
- 업체 관리
- Outlook 폴더 선택
- Excel 파일 선택
- 시트명
- 백업 폴더
- 제목 보조 키워드
- 추출 규칙 파일 경로

---

## 8. 예외 처리

### Outlook

- Outlook 미설치
- Outlook 프로필 없음
- MAPI 연결 실패
- 폴더 없음
- 보안 경고
- COM 객체 해제 실패
- Exchange 주소 SMTP 변환 실패

### 메일

- MailItem이 아닌 항목
- 암호화 메일
- 본문 없음
- RTF 전용
- 첨부파일에만 본문 존재
- 너무 큰 HTML
- 잘못된 문자 인코딩

### Excel

- 파일 없음
- 파일 잠김
- 읽기 전용
- 시트 없음
- 헤더 불일치
- 병합 셀 충돌
- 저장 권한 없음
- 네트워크 단절

### 데이터

- 업체 미등록
- 숫자 여러 개 충돌
- 장비 구간 분리 실패
- 같은 레코드 중복
- 수정본 충돌

---

## 9. 보안 요구사항

- 외부 통신 없이 동작 가능
- 메일 원문과 추출 데이터는 로컬 저장
- 민감 데이터 로그에는 최소화
- 로그에 메일 본문 전체 기록 금지
- 설정 파일에 계정 비밀번호 저장 금지
- Outlook 읽기 작업만 허용
- 삭제·이동·발송 기능은 구현하지 않음
- 향후 AI 연동 시 명시적 관리자 설정 필요

---

## 10. 테스트 전략

### 단위 테스트

- 제목 분류
- HTML 정규화
- 장비 구간 분리
- 업체 별칭 매칭
- 인원 추출
- 당일/누적 구분
- 중복 키 생성
- 신뢰도 계산

### 회귀 테스트

실제 익명화 샘플 메일을 fixture로 저장하고, 추출 결과 JSON을 golden file로 관리한다.

### 통합 테스트

- Outlook 테스트 폴더 조회
- 20통 일괄 분석
- Excel 테스트 사본 반영
- 재실행 시 중복 차단
- 수정 메일 처리
- Excel 잠금 상태

### 사용자 인수 테스트

- 정상 메일 10건
- 외주 없음 3건
- 형식 예외 5건
- 수정본 2건
- 실제 Excel 반영 및 합계 검증

---

## 11. 성능 목표

- Outlook 50통 조회: 10초 이내 목표
- 메일 20통 분석: 20초 이내 목표
- Excel 100행 반영: 10초 이내 목표
- 메인 화면 초기 표시: 3초 이내 목표

---

## 12. 배포

### 개발 환경

- Python 가상환경
- requirements.lock 고정
- Git 저장소
- pytest 자동 실행

### 사용자 배포

권장:

- PyInstaller `onedir`
- 설치 폴더 내 설정 DB와 로그 분리
- 사용자 데이터는 `%LOCALAPPDATA%\OutsourceMailCollector`
- 실행 파일 디지털 서명은 사내 정책에 따라 적용

### 업데이트

초기에는 수동 버전 교체 방식
- 앱 시작 시 버전 표시
- DB 스키마 버전 관리
- 설정 자동 마이그레이션

---

## 13. 구현 순서

1. Outlook 연결 PoC
2. 받은편지함 날짜 필터
3. 발신자 SMTP 주소 획득
4. HTML 본문 정규화
5. 실제 샘플 10~20개 수집
6. 장비 구간 파서
7. 외주 정보 추출기
8. 검토 UI
9. SQLite 처리 이력
10. Excel 테스트 파일 반영
11. 중복·수정본 처리
12. 패키징 및 현장 테스트

---

## 14. 기술적 미확정 사항

- 회사 보안 프로그램에서 COM 접근 허용 여부
- Outlook 받은편지함 외 공유 사서함 사용 가능성
- 실제 Excel 파일의 병합 셀·수식·외부 링크 구조

## 15. 상세 공수표 취합 구현

### 15.1 추가 애플리케이션 서비스

- `ManDayCalculationService`: `Decimal` 기반 투입·누적 공수 계산과
  보고값/계산값 비교
- `WorkReportService`: 추출 행과 수동 행 동기화, 누적 계열 연결, 중복 후보 관리
- `FinalReportService`: 차단 조건 재검증, 업체 설정 순서 정렬, 불변 스냅샷 생성
- `HtmlReportRenderer`: 저장소나 COM에 의존하지 않는 HTML/일반 텍스트 렌더링

작업일 판정은 `parsing/work_date_parser.py`의 순수 함수로 수행한다. 추출 파이프라인
순서 `normalize → split_sections → extract_work_records → validate`는 변경하지
않는다.

### 15.2 SQLite 추가 구조

- `processed_mails`: 제목·본문 날짜 근거, 날짜 출처, 날짜 경고, 확인 여부
- `vendors.sort_order`: 최종 보고서 업체 정렬 순서
- `work_report_rows`: 메일/수동 취합 행과 보고·계산·확정 공수
- `final_reports`: 확정 범위, 해시, 확정·복사·무효화 시각
- `final_report_rows`: 확정 시점의 출력 행 스냅샷

공수는 SQLite `TEXT`에 정규화된 10진 문자열로 저장한다. 기존 테이블은 삭제하거나
재작성하지 않고 `PRAGMA table_info` 기반 additive migration으로 확장한다.
중복·수정 보고 후보는 모두 보존해야 하므로 취합 업무 키에 unique 제약을 두지
않는다.

### 15.3 UI 및 클립보드 경계

메일 수신 조회일과 작업일 시작·종료 범위를 별도 컨트롤로 제공한다. 검토 표는
메일·계산·확정 투입/누적값을 동시에 보여주고 문제 행을 개별 확인하게 한다.
최종 미리보기에서 전체 확인이 끝난 뒤에만 복사를 활성화한다.

클립보드는 Qt `QMimeData`에 `text/html`과 `text/plain`을 함께 기록한다. Outlook
및 Excel COM은 이 출력 경로에 사용하지 않는다.

### 15.4 수주 마스터와 혼합 야근 공수

- `WorkOrderMappingService`는 정규화 수주번호의 활성 exact mapping만 조회해
  업체와 사업팀을 공급한다. 장비명은 교차 검증 근거이며, 불일치하면
  `EQUIPMENT_MAPPING_MISMATCH`를 남기되 exact mapping 결과를 대체하지 않는다.
- 파서는 `투입 공수`를 당일 보고 공수인 `daily_man_day`로 추출한다.
  `WorkReportService`는 이를 `reported_daily_man_day`로 보존하고 계산값으로
  덮어쓰지 않는다.
- 계산 당일 공수는 `실제 작업인원 + 야근 인원 × 0.5`다. 실제 작업인원과
  야근 인원은 0 이상의 정수여야 하고 야근 인원은 실제 작업인원을 초과할 수
  없다.
- 인당 공수 표시는 야근 인원에 따라 `1.0`, `1.5`, `혼합`으로 파생한다.
  최종 스냅샷과 HTML·일반 텍스트 표는 `야근 인원` 열을 보존한다.
- `WORK_ORDER_UNREGISTERED`와 `NIGHT_HEADCOUNT_INVALID`는 최종화를 차단한다.
  장비명 불일치 경고는 명시적 검토 후 확정할 수 있다.
- 메일 표가 HTML table인지 붙여넣기 이미지인지
- 프로그램 배포 시 관리자 권한 필요 여부
