# Outlook 수집·검토·설정 연결 설계

## 1. 목표와 범위

이번 작업은 현재 더미 데이터 기반 리뷰 그리드를 실제 Outlook 메일 수집, 규칙 기반
추출, SQLite 영구 저장, 사용자 검토 기능과 연결한다. 직원·업체·Outlook 폴더 및
Excel 대상 정보를 관리하는 설정 화면도 제공한다.

포함 범위:

- `MailCollectionService`, `ExtractionOrchestrator`, `ReviewService`,
  `ExcelExportService` 구현
- 읽기 전용 `OutlookComAdapter` 구현
- Outlook COM에서 실제 메일 폴더 목록 조회
- 실제 수집·추출 결과를 리뷰 그리드와 요약 영역에 표시
- 직원, 업체, Outlook 폴더, Excel 경로와 시트명 설정
- `%LOCALAPPDATA%\OutsourceMailCollector\collector.db` 영구 저장
- 리뷰 셀 수정, 선택 행 제외, 검토 완료, 변경 이력 기록
- Excel 반영 버튼 클릭 시 미연동 안내

제외 범위:

- 실제 Excel COM 쓰기
- Outlook 메일 삭제, 이동, 읽음 상태 변경, 회신 또는 전달
- 외부 AI 및 외부 네트워크 연동
- 실 직원·업체 데이터 하드코딩
- PyInstaller 패키징

## 2. 선택한 접근법

Application 서비스와 UI를 분리하고, Outlook 수집은 PySide6 백그라운드 작업자에서
실행한다. 서비스는 PySide6나 COM 객체를 직접 알지 못하며 생성자 주입으로 어댑터와
저장소를 받는다. UI 스레드에는 완료 결과와 오류 정보만 전달한다.

이 구조는 Outlook COM 지연 중에도 UI 응답성을 유지하고, 테스트에서는 가짜
어댑터로 동일한 서비스 흐름을 검증할 수 있다. 이벤트 버스나 범용 작업 큐는 현재
20~50통 규모에 필요하지 않으므로 도입하지 않는다.

## 3. 계층과 구성 요소

### 3.1 Domain

기존 `MailEnvelope`, `MailRecord`, `EquipmentSection`,
`OutsourceWorkRecord`, `ValidationResult`, `ProcessingHistory`,
`ReviewStatus`를 유지한다.

Application과 UI 사이에 전달할 결합 결과는 Application DTO로 둔다. DTO는 다음
정보를 포함한다.

- 저장된 추출 레코드 식별자
- Outlook EntryID
- 보고일과 작성자
- 장비명과 Tracking No.
- 업체명
- 실제 인원, 당일 공수, 누적 공수
- 신뢰도와 검토 상태

직원과 업체 설정은 각각 이름·정규화 이메일·활성 여부·별칭 목록, 표준 업체명·활성
여부·별칭 목록으로 표현한다.

### 3.2 Infrastructure

`SQLiteRepository`는 단일 SQLite 연결을 장기간 공유하지 않는다. 공개 작업마다
연결을 열고 트랜잭션 종료 후 닫아 UI 스레드와 작업자 스레드 사이에서 연결 객체가
전달되지 않게 한다.

담당 기능:

- 설정 키 조회·저장
- 직원과 업체 목록·추가·수정·삭제
- 처리 메일 존재 여부 및 저장
- 추출 레코드 저장·조회·수정
- 검토 상태 변경
- 변경 전후 action log 기록

DB 기본 위치는 다음과 같다.

```text
%LOCALAPPDATA%\OutsourceMailCollector\collector.db
```

앱 시작 시 디렉터리와 스키마를 생성한다. 테스트는 `tmp_path`의 독립 DB를 사용한다.

`OutlookComAdapter`는 다음 읽기 작업만 제공한다.

- Outlook 세션 연결
- 기본 Inbox부터 하위 폴더를 재귀 탐색하여 경로 목록 반환
- 선택한 폴더 경로 해석
- DASL 날짜 필터로 `MailEnvelope` 목록 반환
- EntryID로 `MailRecord` 본문 반환
- 원본 메일을 Outlook Inspector로 표시

COM 객체는 어댑터 내부에서만 사용하고 다른 스레드로 반환하지 않는다. 작업자
스레드에서 `pythoncom.CoInitialize()`와 `CoUninitialize()`의 생명주기를 관리한다.
Exchange 발신자는 `PrimarySmtpAddress`로 변환하며 실패 시 원래 주소를 사용한다.
메일의 `UnRead`, 폴더 위치 또는 내용에 값을 대입하지 않는다.

### 3.3 Application

`MailCollectionService`:

1. 선택 날짜의 시작·종료 시각을 계산한다.
2. 저장된 활성 직원 이메일을 읽는다.
3. Outlook 목록을 조회하고 발신자 이메일을 소문자로 정규화한다.
4. 활성 직원이 등록된 경우 해당 직원의 메일만 대상으로 삼는다.
5. 각 EntryID의 본문을 읽는다.
6. 수신 직원 집합과 활성 직원 집합의 차이로 미보고자를 계산한다.
7. 개별 메일 읽기 실패는 결과의 오류 목록에 추가하고 나머지 메일 처리를 계속한다.

활성 직원이 한 명도 없으면 안전하게 수집 결과를 비우고 설정 안내를 반환한다.
등록되지 않은 모든 발신자 메일을 수집 대상으로 간주하지 않는다.

`ExtractionOrchestrator`:

1. 이미 저장된 EntryID는 재추출하지 않고 기존 레코드를 반환한다.
2. 새 메일에 `normalize → split_sections → extract_work_records → validate`
   파이프라인을 적용한다.
3. 업체 별칭은 추출 후 표준명으로 변환한다.
4. 처리 메일과 추출 레코드를 한 트랜잭션으로 저장한다.
5. 메일 단위 파싱 실패는 해당 메일 오류로 기록하고 다음 메일을 처리한다.
6. 저장 결과를 리뷰 DTO 목록으로 반환한다.

외주 레코드가 없는 메일은 정상적인 무외주 메일로 처리 완료하되 리뷰 행은 만들지
않는다. 불확실한 숫자를 추정하지 않는 기존 규칙을 유지한다.

`ReviewService`:

- 편집 가능한 필드만 변경한다.
- 빈 문자열을 `None`으로, 숫자 필드는 유효한 실수로 변환한다.
- 수정 전후 값을 같은 트랜잭션의 action log에 기록한다.
- 선택 행을 `반영 제외` 또는 `검토 완료`로 변경한다.
- 원본 열기 요청은 EntryID를 Outlook 어댑터에 전달한다.

`ExcelExportService`:

- `검토 완료` 레코드만 내보낼 수 있다는 계약을 구현한다.
- 실제 호출 시 Excel 어댑터가 준비되지 않았으면 명시적
  `ExcelIntegrationUnavailableError`를 발생시킨다.
- 이번 UI의 Excel 버튼은 이 서비스를 실행하지 않고 안내창만 표시한다.

### 3.4 UI

`MainWindow`는 애플리케이션 서비스를 생성하지 않고 외부에서 주입받는다. 앱 조립은
`app.py`가 DB 경로, 저장소, Outlook 어댑터와 서비스를 생성해 담당한다.

메일 가져오기:

- 조회 날짜와 선택 폴더를 입력으로 사용한다.
- 실행 중 버튼을 비활성화하고 진행 상태를 표시한다.
- 작업자 완료 시 실제 리뷰 행, 통계, 미보고 배너를 갱신한다.
- 실패 시 한국어 메시지 상자를 표시하고 기존 그리드 데이터는 유지한다.

리뷰 그리드:

- 더미 데이터 자동 로드를 제거한다.
- 저장된 레코드 식별자와 EntryID를 행 데이터로 유지한다.
- 셀 편집 완료 시 `ReviewService`를 호출한다.
- 선택 행 제외와 검토 완료 버튼을 실제 상태 변경과 연결한다.
- 원본 버튼은 Outlook Inspector를 연다.

설정 대화상자:

- 직원 탭: 이름, 이메일, 별칭, 활성 여부 CRUD
- 업체 탭: 표준명, 별칭, 활성 여부 CRUD
- 일반 탭: Outlook 폴더, Excel 파일 경로, 원본 시트명
- Outlook 폴더 새로고침은 백그라운드에서 COM 목록을 읽는다.
- 저장 시 이메일을 소문자로 정규화하고 빈 이름·중복 이메일·중복 업체명을 거부한다.
- Excel 기본 시트명은 `외주인원_원본`이다.

Excel 반영 버튼은 활성 상태를 유지한다. 클릭 시 다음 메시지를 표시한다.

```text
실제 Excel 연동은 아직 준비되지 않았습니다.
실 워크북 확보 후 사용할 수 있습니다.
```

## 4. 데이터 흐름

```text
[설정 DB]
   │ 활성 직원·업체 별칭·선택 폴더
   ▼
[MailCollectionService] ── OutlookComAdapter
   │ MailRecord 목록 + 미보고자 + 개별 오류
   ▼
[ExtractionOrchestrator] ── 기존 parsing 순수 함수
   │ 처리 메일·추출 레코드 트랜잭션 저장
   ▼
[SQLiteRepository]
   │ ReviewRow DTO 조회
   ▼
[MainWindow / ReviewGrid]
   │ 셀 수정·상태 변경
   ▼
[ReviewService] ── action_logs
```

재실행 시 저장된 EntryID는 다시 추가하지 않는다. 화면은 선택 날짜의 저장 레코드와
새 수집 결과를 합친 현재 DB 상태를 조회해 표시한다.

## 5. 오류 처리

- Outlook 연결 실패: 한 번 재시도한 뒤 Outlook 실행 및 프로필 확인 안내
- 폴더 조회 실패: 기존 선택값을 보존하고 오류 메시지 표시
- 개별 메일 읽기·파싱 실패: 나머지 메일은 계속 처리하고 요약 경고 표시
- DB 저장 실패: 해당 트랜잭션을 롤백하고 처리 완료 상태를 남기지 않음
- 잘못된 셀 숫자: DB에 저장하지 않고 기존 값을 복구하며 한국어 안내
- 설정 중복: 저장하지 않고 충돌 항목을 표시
- Excel 버튼: 오류가 아닌 기능 준비 안내로 처리

로그에는 전체 메일 본문이나 전체 수신자 목록을 기록하지 않는다. EntryID는 해시
또는 부분 식별값으로 남기고 처리 단계·결과·오류 코드를 기록한다.

## 6. 테스트 전략

모든 기능은 TDD로 추가한다.

- Repository 단위 테스트
  - 설정, 직원, 업체 CRUD와 정규화
  - 처리 메일·추출 레코드 트랜잭션
  - 편집·상태 변경·action log
- Application 단위 테스트
  - 등록 직원 필터와 미보고자 계산
  - 중복 EntryID 재수집 방지
  - 개별 메일 실패 후 계속 처리
  - 파싱 결과의 리뷰 DTO 변환
  - 검토 상태 전이와 잘못된 숫자 거부
  - Excel 미연동 오류 계약
- Outlook 어댑터 단위 테스트
  - 가짜 COM 객체를 사용한 폴더 재귀 탐색
  - DASL 필터 호출
  - Exchange SMTP 변환
  - 메일 상태 변경 메서드가 호출되지 않음
- UI 테스트
  - 더미 행 없이 시작
  - 서비스 결과로 그리드·통계·미보고 배너 갱신
  - 설정 저장과 실제 폴더 선택
  - Excel 안내창 문구
  - 수집 중 UI 상태와 성공·실패 복구
- 전체 회귀 테스트
  - 기존 익명화 파싱 fixture 유지
  - 전체 pytest 통과

실 Outlook 조회는 자동 테스트에서 수행하지 않는다. COM 통합 검증은 기존 PoC와
별도 수동 실행 절차로 유지하며, 사용자 승인 없이 Outlook 또는 Excel 데이터를
변경하는 테스트는 만들지 않는다.

## 7. 완료 조건

- 등록 직원과 업체 정보를 설정 화면에서 저장·재조회할 수 있다.
- Outlook COM에서 실제 폴더 목록을 읽고 폴더를 선택할 수 있다.
- 선택 날짜와 폴더의 등록 직원 메일을 UI 멈춤 없이 가져온다.
- 파싱 결과와 저장된 검토 상태가 리뷰 그리드에 표시된다.
- 미보고자와 요약 통계가 실제 결과로 갱신된다.
- 셀 수정, 반영 제외, 검토 완료와 변경 이력이 DB에 저장된다.
- 재조회 시 같은 EntryID가 중복 저장되지 않는다.
- Excel 버튼은 활성화되어 있고 클릭 시 미연동 안내가 표시된다.
- 전체 자동 테스트가 통과하며 Outlook 읽기 전용 규칙이 유지된다.
