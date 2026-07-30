# HANDOFF

이 문서는 작업 세션 사이에서 프로젝트 상태와 판단 근거를 안전하게 인계하기 위한 기록이다.
다음 세션은 가장 최근 기록부터 읽고, 작업을 마칠 때 같은 형식으로 새 기록을 문서 상단에 추가한다.

## 고정 기록 규칙

### 작성 원칙

- 세션 기록은 `YYYY-MM-DD HH:mm:ss KST` 기준으로 작성한다.
- 최신 세션을 `세션 기록` 바로 아래에 추가한다.
- 과거 기록은 원칙적으로 수정하거나 삭제하지 않는다. 오류는 새 기록의 `이전 기록 정정`에서 바로잡는다.
- 결과와 판단을 중심으로 간결하게 쓰되, 요구사항, 결정, 변경, 검증, 실패, 위험, 미완료 사항은 생략하지 않는다.
- 확인한 사실과 추정·미확인 사항을 명확하게 구분한다.
- 해당 사항이 없으면 항목을 삭제하지 않고 `없음`이라고 쓴다.
- 비밀번호, 토큰, 개인정보, 실제 메일 본문과 같은 민감정보는 기록하지 않는다.
- 기존 사용자 변경과 현재 세션 변경을 구분하며, 기존 변경을 임의로 되돌리지 않는다.
- 실행하지 않은 검증을 통과했다고 쓰지 않는다. 코드 검사와 실제 Outlook·Excel·GUI 검증을 구분한다.
- 커밋이나 푸시는 사용자가 명시적으로 요청한 경우에만 수행한다.

### 필수 식별 정보

- 세션명
- 기록 시각
- 작성 주체
- 세션 ID: 확인할 수 있을 때만 기록하고 임의 생성하지 않는다.
- 작업 디렉터리
- Git 브랜치와 기준 커밋

### 필수 목차

모든 세션 기록은 다음 순서를 유지한다.

1. 세션 목표
2. 시작 시점 상태
3. 핵심 결정
4. 수행 내용
5. 변경 파일
6. 검증 결과
7. 실패 및 미확인 사항
8. 현재 상태
9. 다음 세션 실행 순서
10. 위험 및 주의사항
11. Git 및 변경 경계
12. 이전 기록 정정

### 상태 표현

- `완료`: 요구사항과 필요한 검증을 모두 충족함
- `부분 완료`: 일부 구현 또는 검증이 남아 있음
- `미완료`: 아직 수행하지 않았거나 결과를 확인하지 못함
- `차단됨`: 외부 조건이나 사용자 결정 없이는 진행할 수 없음
- `실환경 검증 필요`: 코드 수준 확인만 끝났고 실제 Outlook·Excel·GUI 환경 검증이 남음

---

## 세션 기록

## 2026-07-30 11:18:00 KST — 커밋 및 애플리케이션 실행

### 세션 정보

- 작업 주체: Codex
- 작업 디렉터리: `D:\My_Work\Outsource Workforce Report Collector`
- Git 브랜치: `master`
- 기준 커밋: `70a710a` (`fix: complete settings UI bug changes`)

### 수행 내용

- 전체 테스트와 정적 검증을 다시 실행했다.
- 변경 산출물을 `70a710a`로 커밋했다.
- `.venv\Scripts\python.exe -m outsource_mail_collector.app`를 실행했다.

### 검증 결과

- `pytest`: `167 passed in 81.92s`
- `compileall`: 성공
- `git diff --check`: 성공
- 애플리케이션 프로세스: PID `44672`, 실행 중이며 응답 상태 확인

### 경계 및 미실행 항목

- `AGENTS.md`, `CLAUDE.md`, `.superpowers/`는 사용자 지침/도구 메타데이터로 커밋에서 제외했다.
- 애플리케이션 시작만 확인했으며 Outlook 수집, Excel 쓰기, 실제 사용자 GUI 시나리오는 실행하지 않았다.
- 원격 푸시는 수행하지 않았다.

---

## 2026-07-30 11:04:52 KST — UI 버그 및 설정 흐름 수정

### 세션 정보

- 작성 주체: Codex 세션
- 세션 ID: 확인 불가
- 작업 디렉터리: `D:\My_Work\Outsource Workforce Report Collector`
- Git 브랜치: `master`
- 기준 커밋: `99f0756`

### 1. 세션 목표

- `docs/2026-07-30-ui-bugs-and-change-list.md`의 업체·수주 동시 등록,
  활성 체크박스, 사업팀 드롭다운, 검토표 오류 대비 문제를 수정한다.
- 실제 Outlook, Excel 및 live collector DB에는 접근하지 않는다.

### 2. 시작 시점 상태

- 기준 커밋은 `99f0756`, 브랜치는 `master`였다.
- `.superpowers/`, `AGENTS.md`, `CLAUDE.md`,
  `docs/2026-07-30-ui-bugs-and-change-list.md`가 기존 미추적 파일이었다.
- 위 기존 파일을 되돌리거나 이번 기능 코드의 기존 상태로 간주하지 않았다.

### 3. 핵심 결정

- 새 업체는 저장 전에도 수주 업체 드롭다운에서 이름 기반 임시 참조로 선택할 수
  있게 하고, 단일 SQLite 트랜잭션에서 업체를 먼저 저장한 뒤 확보한 ID로 수주를
  저장한다.
- 새 미완성 수주 행은 다른 설정 저장을 막지 않고 저장 대상에서 제외하며,
  설정창을 닫지 않은 채 행별 누락 원인을 안내한다.
- 수주 삭제와 미완성 수주 행이 동시에 있으면 기존 수주 손실을 막기 위해 전체
  저장을 차단한다.
- 활성 표시는 테마에서 명확히 보이는 `QCheckBox` 셀 위젯으로 통일한다.
- 신규 수주의 사업팀은 승인된 10개 목록만 선택하며, 과거 목록 외 저장값은
  재오픈 시 손실 없이 표시한다.
- 오류 행은 밝은 배경과 명시적인 어두운 전경색을 함께 설정한다.

### 4. 수행 내용

- 신규 업체와 신규 수주를 같은 설정창에서 한 번에 저장하는 흐름을 구현했다.
- 업체명·활성 변경 시 모든 수주 업체 드롭다운을 즉시 갱신한다.
- 미완성 수주 행을 분리하고 수주번호, 장비명, 업체, 사업팀별 누락 이유를
  메시지에 표시한다.
- 담당자·업체·수주 활성 상태를 체크박스 셀 위젯으로 변경했다.
- 사업팀 선택과 기존 저장값 복원을 콤보박스로 구현했다.
- 검토표 문제 행의 글자 대비를 보강했다.
- 익명·격리 테스트 DB와 가짜 Outlook adapter로 다크 테마 GUI 렌더를 생성해
  업체·사업팀 드롭다운, 활성 체크박스, 오류 행 대비를 육안 확인했다.

### 5. 변경 파일

기능 코드:

- `src/outsource_mail_collector/ui/settings_dialog.py`
- `src/outsource_mail_collector/ui/review_grid.py`

테스트:

- `tests/test_settings_dialog.py`
- `tests/test_review_grid.py`

문서:

- `docs/2026-07-30-ui-bugs-and-change-list.md`
- `HANDOFF.md`

### 6. 검증 결과

- TDD RED:
  - 최초 집중 실행: `5 failed, 15 passed`
  - 누락 업체 원인 메시지: `1 failed`
  - 비활성 업체 표시 중복 회귀: `1 failed`
- 집중 테스트:
  - `tests/test_settings_dialog.py`, `tests/test_review_grid.py`
  - `QT_QPA_PLATFORM=offscreen`, 저장소 내부 `--basetemp`,
    `-p no:cacheprovider`
  - 결과: `21 passed in 16.73s`
- 전체 테스트:
  - `QT_QPA_PLATFORM=offscreen`, 저장소 내부 `--basetemp`,
    `-p no:cacheprovider`
  - 결과: `167 passed in 76.65s`
- `git diff --check`: exit code 0, LF-to-CRLF 안내 경고만 출력
- 격리 GUI 렌더:
  - `D:\tmp\collector-ui-settings-work-order-20260730.png`
  - `D:\tmp\collector-ui-review-error-20260730.png`
  - 수주 업체·사업팀 드롭다운, 활성 체크박스, 오류 행의 밝은 배경과 어두운
    글자 대비를 확인했다.

### 7. 실패 및 미확인 사항

- 실제 사용자 데스크톱에서 대화형 GUI 확인: 미실행.
- 격리 렌더 환경은 Qt 글꼴 디렉터리가 없어 일부 한글이 `?`로 표시됐으며,
  위젯 배치·선택 UI·색 대비 확인에는 영향을 주지 않았다.
- 실제 Outlook 수집/Inspector: 실행하지 않음.
- 실제 Excel 접근·내보내기: 실행하지 않음.
- live collector DB 접근·변경: 실행하지 않음.

### 8. 현재 상태

- 코드 구현 및 자동 회귀: 완료.
- 격리 GUI 렌더 검토: 완료.
- 실제 사용자 데스크톱 GUI 확인: 미완료.
- 전체 상태: 부분 완료.

### 9. 다음 세션 실행 순서

1. 실제 사용자 데스크톱에서 설정창을 열어 업체와 수주를 한 번의 Save로
   저장하고, 미완성 수주 안내가 행별 원인으로 표시되는지 확인한다.
2. 업체·수주 활성 체크박스와 사업팀 전체 목록·재오픈 복원을 확인한다.
3. 다크 테마 메인 검토표의 오류 행 대비를 확인한다.
4. 확인 후 `docs/2026-07-30-ui-bugs-and-change-list.md`의 기능 항목과 실제 GUI
   검증 체크박스를 완료 처리한다.

### 10. 위험 및 주의사항

- 실제 Outlook·Excel·live DB 검증으로 자동 확대하지 않는다.
- 미완성 신규 수주 행은 DB에 저장되지 않고 설정창에 남는다.
- 수주 삭제가 대기 중이면 미완성 행을 허용하지 않아 기존 매핑의 의도치 않은
  삭제를 방지한다.
- 기존 목록 외 사업팀 값은 자동 변경하거나 삭제하지 않는다.

### 11. Git 및 변경 경계

- 커밋: 하지 않음.
- 푸시: 하지 않음.
- 브랜치 변경/PR: 하지 않음.
- 기존 사용자 및 이전 세션 변경은 보존함.

### 12. 이전 기록 정정

- 없음.

## 2026-07-29 21:55:31 KST — 최종 코드 리뷰 중요 발견사항 수정

### 세션 정보

- 작성 주체: Codex 세션
- 세션 ID: 확인 불가
- 작업 디렉터리: `D:\My_Work\Outsource Workforce Report Collector`
- Git 브랜치: `master`
- 기준 커밋: `efa7305` (`feat: add work report compilation workflow`)

### 1. 세션 목표

- 최종 코드 리뷰의 Important 발견사항 네 건을 단일 수정 파동으로 해결한다.
- 회귀 테스트를 먼저 실패시키고 최소 구현 후 집중·전체·정적 검증을 수행한다.
- 실제 Outlook, Excel 및 live collector DB에는 접근하지 않는다.

### 2. 시작 시점 상태

- 기준 커밋은 `efa7305`, 브랜치는 `master`였다.
- Tasks 1~8의 기존 수정 및 미추적 산출물이 있는 dirty worktree였으며 이를
  이번 작업 결과로 간주하거나 되돌리지 않았다.
- 이전 전체 자동 검증 기준은 148개 테스트 통과였다.

### 3. 핵심 결정

- `WORK_ORDER_UNREGISTERED`와 필드별 잘못된 숫자 provenance를 최종 확정
  차단 문제로 처리한다.
- 매핑 새로고침 대상은 메일 기원, 경고 미확정 행 중 매핑 문제 또는 빈
  업체/팀 값이 있는 행으로 한정한다.
- 빈 값과 이전 매핑에서 온 것으로 확인되는 값만 채우거나 교체하고, 사용자가
  별도로 입력한 비어 있지 않은 값은 보존한다.
- 설정 저장은 UI가 연결 객체를 직접 다루지 않도록 repository/application
  트랜잭션 경계를 사용하며, 하나의 SQLite 연결에서 전부 commit 또는 rollback한다.
- 일반 `INVALID_VALUE`를 유지하면서 원본 필드를 식별하는 별도 issue code를
  추가해 관련 없는 재계산으로 근거가 사라지지 않게 한다.

### 4. 수행 내용

- 최종 보고서의 미등록 작업번호 차단 집합을 보강했다.
- 기존 미확정 메일 행의 작업번호 매핑 새로고침과 설정 저장 후 호출을 구현했다.
- 작업번호 또는 장비명 수정 시 매핑 문제를 재평가하도록 했다.
- 기존 매핑 값, 사용자 값, 빈 값을 구분해 업체/팀 값을 안전하게 갱신했다.
- repository의 thread-local 단일 연결 트랜잭션과 application 경계를 추가했다.
- 설정 전체 사전 검증, 동일 트랜잭션 저장, commit 후 UI 상태 반영을 구현했다.
- 실제/보고 일일/보고 누적 잘못된 숫자 provenance를 필드별로 보존하고 원본
  필드의 명시적 수정 때만 제거하도록 했다.
- 자기검토에서 invalid provenance와 missing 문제가 동시에 생성되는 중복 경고를
  발견해 실패 테스트 후 억제 규칙을 추가했다.

### 5. 변경 파일

기능 코드:

- `src/outsource_mail_collector/domain/work_report.py`
- `src/outsource_mail_collector/application/final_report_service.py`
- `src/outsource_mail_collector/application/settings_service.py`
- `src/outsource_mail_collector/application/work_report_service.py`
- `src/outsource_mail_collector/infrastructure/db/repository.py`
- `src/outsource_mail_collector/ui/main_window.py`
- `src/outsource_mail_collector/ui/settings_dialog.py`

테스트:

- `tests/test_final_report_service.py`
- `tests/test_work_order_mapping_service.py`
- `tests/test_work_report_service.py`
- `tests/test_settings_dialog.py`
- `tests/test_main_window.py`

기록:

- `.superpowers/sdd/2026-07-29-work-order-master-mixed-man-day/final-fix-report.md`
- `HANDOFF.md`

### 6. 검증 결과

- TDD RED:
  - 미등록 작업번호 최종 차단: `1 failed, 3 passed`
  - 매핑 새로고침·provenance 선택 테스트: `7 failed, 2 passed, 19 deselected`
  - 설정 원자성: `2 failed, 1 passed, 10 deselected`
  - 설정 수락 후 새로고침: `1 failed`
  - 자기검토 중복 missing 경고: `1 failed, 1 passed`
- TDD GREEN:
  - 선택 회귀: `17 passed, 29 deselected`
  - 영향 파일 전체: `67 passed`
  - 자기검토 보강: `2 passed, 22 deselected`
- 최종 집중 테스트:
  - 지정한 13개 테스트 파일
  - `QT_QPA_PLATFORM=offscreen`
  - 저장소 내부 `--basetemp`
  - `-p no:cacheprovider`
  - 결과: `127 passed in 60.15s`
- 최종 전체 테스트:
  - `QT_QPA_PLATFORM=offscreen`
  - 저장소 내부 `--basetemp`
  - `-p no:cacheprovider`
  - 결과: `162 passed in 75.05s`
- `python -m compileall -q src tests`: exit code 0
- `git diff --check`: exit code 0, LF-to-CRLF 안내 경고만 출력
- `HANDOFF.md` 및 `docs/**/*.md` strict UTF-8 읽기:
  `STRICT_UTF8=ok`

### 7. 실패 및 미확인 사항

- 최종 자동 검증 실패: 없음.
- 실제 Outlook 수집/Inspector: 실행하지 않음.
- 실제 Excel 내보내기 및 서식 보존: 실행하지 않음.
- 대화형 GUI 육안 검증: 실행하지 않음.
- live collector DB 변경 검증: 실행하지 않음.

### 8. 현재 상태

- 상태: 완료.
- 요청된 네 건의 Important 발견사항과 저비용 보강 회귀가 구현·검증됐다.
- 실환경 경계는 코드 실패가 아니라 이번 작업에서 의도적으로 실행하지 않은 검증이다.

### 9. 다음 세션 실행 순서

1. `.superpowers/sdd/2026-07-29-work-order-master-mixed-man-day/final-fix-report.md`
   의 결정과 검증 결과를 확인한다.
2. 필요 시 복사 DB와 테스트 Outlook/Excel 파일에서만 수동 GUI 흐름을 검증한다.
3. 커밋이 필요하면 기존 dirty worktree와 이번 수정 범위를 다시 구분한 뒤 사용자의
   명시적 지시에 따라 진행한다.

### 10. 위험 및 주의사항

- repository 트랜잭션은 현재 동기식 설정 저장 경로와 같은 스레드에서 사용해야 하며
  SQLite 연결을 다른 스레드로 전달하지 않는다.
- 실제 Outlook·Excel·GUI 동작은 자동 테스트 결과로 확대 해석하지 않는다.
- 기존 worktree의 다른 변경과 산출물을 임의로 정리하거나 되돌리지 않는다.

### 11. Git 및 변경 경계

- 커밋: 하지 않음.
- 푸시: 하지 않음.
- 브랜치 변경/PR: 하지 않음.
- 기존 사용자 및 이전 Task 변경은 보존함.

### 12. 이전 기록 정정

- 없음.

## 2026-07-29 20:28:40 KST — Task 8 전체 회귀·문서·실환경 재확인

### 세션 정보

- 작성 주체: Codex 세션
- 세션 ID: 확인 불가
- 작업 디렉터리: `D:\My_Work\Outsource Workforce Report Collector`
- Git 브랜치: `master`
- 기준 커밋: `efa7305` (`feat: add work report compilation workflow`)

### 1. 세션 목표

- Tasks 1~7의 전체 회귀와 정적 검사를 수행하고 governing 문서를 동기화한다.
- live DB를 변경하지 않는 새 테스트 DB에서 승인된 2026-07-27 Outlook 읽기
  전용 재확인을 수행한다.

제외 범위:

- 실제 Excel 접근·쓰기
- Outlook Display/Inspector, 이동, 삭제, 회신, 전달, 발송 또는 읽음 상태 변경
- 기능 코드 변경

### 2. 시작 시점 상태

- `master`, 기준 커밋 `efa7305` 위에 Tasks 1~7 기능·테스트와 기존 사용자 문서가
  미커밋 상태로 존재했다.
- governing 문서에는 상세 공수표 설계가 있었으나 exact 수주 매핑과 혼합 야근
  공수의 최종 결정을 명시적으로 동기화해야 했다.

### 3. 핵심 결정

- 정규화 수주번호 exact mapping만 업체·사업팀을 공급하며 장비명 불일치는
  매핑을 바꾸지 않고 경고로 남긴다.
- `투입 공수`는 당일 보고 공수이고, 계산 당일 공수는
  `실제 작업인원 + 야근 인원 × 0.5`다.
- 인당 공수 표시는 `1.0`, `1.5`, `혼합`이며 최종 표에 `야근 인원`을 포함한다.
- 수주 미등록과 유효하지 않은 야근 인원은 최종화를 차단한다.
- 최초 Outlook 권한 상승 거절 후 안전 경계를 우회하지 않고 controller에 동일
  runner의 명시 권한 실행을 인계한다.

### 4. 수행 내용

- PRD, TRD, 시스템 아키텍처, ADR에 승인 결정을 반영했다.
- focused/full/offscreen 회귀, compileall, diff, strict UTF-8 검사를 실행했다.
- live DB를 SQLite URI `mode=ro`로 열어 새 ignored 테스트 DB에 backup API로
  복제했다.
- fresh DB에만 additive migration과 승인된 테스트 전용 업체 1건, 활성 수주
  매핑 2건을 등록했다. 실제 업무 값은 이 문서에 기록하지 않는다.
- 2026-07-27 count-only Outlook runner를 실행했으나 unread baseline 단계에서
  COM 오류가 발생했다. 사용자 세션 실행을 위한 권한 상승도 거절돼 재시도하지
  않았다.
- 동일한 안전 runner를 Task 8 SDD 작업공간에 보존했다.
- controller가 사용자 승인 맥락으로 동일 runner를 1회 명시 권한 실행해 두 행의
  필드·매핑·공수와 unread 비변경을 count-only로 확인했다.

### 5. 변경 파일

- `docs/PRD.md`
- `docs/TRD.md`
- `docs/SYSTEM_ARCHITECTURE.md`
- `docs/ADR.md`
- `.superpowers/sdd/2026-07-29-work-order-master-mixed-man-day/task-8-outlook-readonly-check.py`
- `.superpowers/sdd/2026-07-29-work-order-master-mixed-man-day/task-8-report.md`
- `HANDOFF.md`
- `local-test/collector-work-order-realcheck-20260729.db`
  - Git ignored fresh 테스트 DB

기능 코드 변경: 없음

### 6. 검증 결과

- focused:

  ```powershell
  $env:QT_QPA_PLATFORM='offscreen'
  .\.venv\Scripts\python.exe -m pytest tests/test_extraction_pipeline.py tests/test_repository.py tests/test_work_order_mapping_service.py tests/test_man_day_calculation_service.py tests/test_work_report_service.py tests/test_settings_dialog.py tests/test_review_grid.py tests/test_manual_row_dialog.py tests/test_problem_review_dialog.py tests/test_final_report_service.py tests/test_report_renderer.py tests/test_final_report_dialog.py tests/test_main_window.py -q --basetemp .pytest-basetemp-task8-focused-20260729 -p no:cacheprovider
  ```

  결과: `113 passed in 47.88s`

- full:

  ```powershell
  $env:QT_QPA_PLATFORM='offscreen'
  .\.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-basetemp-task8-full-20260729 -p no:cacheprovider
  ```

  결과: `148 passed in 65.32s`

- static 및 문서:

  ```powershell
  .\.venv\Scripts\python.exe -m compileall -q src tests
  git diff --check
  .\.venv\Scripts\python.exe -c "from pathlib import Path; [p.read_text(encoding='utf-8', errors='strict') for p in [Path('HANDOFF.md'), *Path('docs').rglob('*.md')]]; print('STRICT_UTF8=ok')"
  ```

  결과: compileall exit 0, `git diff --check` exit 0(LF→CRLF 정보 경고만),
  `STRICT_UTF8=ok`

- 상세 명령과 결과: `.superpowers/sdd/2026-07-29-work-order-master-mixed-man-day/task-8-report.md`
- fresh DB:
  - 생성 전 목적지 미존재
  - SQLite backup source `mode=ro`
  - `git check-ignore`: `.gitignore:15:*.db`
  - 초기 및 Outlook 실패 후 `PRAGMA integrity_check = ok`
  - 활성 업체 1건, 전체/활성 수주 매핑 각 2건
  - controller 실행 후 2026-07-27 추출 행 2건, `integrity_check = ok`
- controller Outlook read-only:
  - 조회 범위 MailItem 31건, 등록 담당자 1명
  - 수집 메일 1건, 수집 오류 0건
  - 추출 2행, 추출 오류 0건
  - 동기화 2행
  - tracking, equipment, vendor, team, actual, night, reported daily,
    calculated daily이 채워진 행 각각 2건
  - reported/calculated daily 일치 2건
  - 행 issue code: `CUMULATIVE_BASELINE_REQUIRED`
  - unread 비교 31건, mutation 0건
  - `INVALID_VALUE`, `SERIES_KEY_MISSING`, `WORK_ORDER_UNREGISTERED` 없음
  - Display/Inspector·이동·삭제·회신·전달·발송·Excel 접근 없음
- 실제 Excel: 미실행
- visual GUI: 미실행; offscreen UI 자동 테스트만 통과

### 7. 실패 및 미확인 사항

- Outlook sandbox 실행:
  - `BLOCKER_PHASE=UNREAD_BEFORE`
  - `BLOCKER_TYPE=com_error`
  - `BLOCKER_HRESULT=-2147352567`
- 오류는 collection·extraction·synchronization 전에 발생했고 unread baseline도
  완성되지 않았다.
- unsandboxed retry 요청은 권한 검토에서 실메일/DB 위험을 이유로 거절됐다.
- controller의 후속 명시 권한 실행은 동일 안전 runner로 성공했으므로 위 최초
  실패는 더 이상 Task 8 blocker가 아니다.
- `CUMULATIVE_BASELINE_REQUIRED`는 최초 누적 기준에 대한 정상 사용자 검토
  이슈로 남는다.

### 8. 현재 상태

- governing 문서 동기화: 완료
- focused/full/static/UTF-8: 완료
- fresh ignored DB와 테스트 전용 매핑: 완료
- Outlook 읽기 전용 실환경 재확인: 완료
- Task 8 전체: `DONE_WITH_CONCERNS`

### 9. 다음 세션 실행 순서

1. 사용자는 두 행의 최초 누적 기준을 검토·확정한다.
2. 필요하면 별도 사용자 승인 아래 visual GUI와 Outlook 붙여넣기 모양을
   확인한다.
3. 실제 Excel 기능은 현재 범위 밖이므로 별도 설계·승인 전까지 접근하지 않는다.

완료 판단 기준:

- Task 8 completion gate는 자동 검증, fresh DB, 두 행 필드·매핑·공수 일치와
  unread mutation 0을 모두 확인해 충족했다.

### 10. 위험 및 주의사항

- live DB는 절대 쓰지 말고 fresh DB만 사용한다.
- Outlook runner는 명시 날짜 read-only 속성 조회만 허용한다. Display/Inspector,
  이동, 삭제, 회신, 전달, 발송 또는 읽음 상태 변경으로 범위를 넓히지 않는다.
- 실제 tracking/equipment/vendor/business-team 값과 메일 본문을 로그·문서에
  출력하지 않는다.
- 실제 Excel과 visual GUI 검증은 여전히 미실행이다.

### 11. Git 및 변경 경계

- Tasks 1~7과 기존 사용자 변경을 보존했다.
- 커밋: 수행하지 않음
- 푸시: 수행하지 않음
- 브랜치 변경: 수행하지 않음
- PR: 수행하지 않음

### 12. 이전 기록 정정

- 없음

## 2026-07-29 15:34:00 KST — 수주 마스터·혼합 공수 구현 계획

### 세션 정보

- 작성 주체: Codex 세션
- 세션 ID: 확인 불가
- 작업 디렉터리: `D:\My_Work\Outsource Workforce Report Collector`
- Git 브랜치: `master`
- 기준 커밋: `efa7305` (`feat: add work report compilation workflow`)

### 1. 세션 목표

- 사용자 승인 설계를 실행 가능한 TDD 구현 계획으로 구체화한다.

### 2. 시작 시점 상태

- 수주 마스터와 혼합 야근 공수 설계 문서가 작성·사용자 승인된 상태였다.
- 코드 구현과 신규 자동 테스트는 시작하지 않은 상태였다.

### 3. 핵심 결정

- 파서, 수주 마스터 영속성, 매핑 서비스, 공수 계산, 설정 UI, 검토 UI, 최종 출력, 전체 검증의 8개 작업으로 나눈다.
- 각 작업은 실패 테스트 확인 후 최소 구현과 관련 테스트 통과로 끝낸다.
- 기존 `final_report_rows.per_person_man_day TEXT NOT NULL` 호환성을 위해 최종 스냅샷에는 `1.0`, `1.5`, `혼합` 표시 문자열을 저장하고 야근 인원을 별도 열로 보존한다.
- 저장소 규칙에 따라 계획의 자동 커밋 단계는 수행하지 않는다.

### 4. 수행 내용

- 관련 domain, application, infrastructure, UI, 테스트 파일과 기존 인터페이스를 매핑했다.
- 파일별 변경, 정확한 서비스·저장소 signature, 실패 테스트, 구현 핵심 코드, 실행 명령과 기대 결과를 포함한 계획을 작성했다.
- 설계 명세 coverage, 작업 수, 체크박스 수, placeholder, 타입 이름과 diff 형식을 자체 검토했다.

### 5. 변경 파일

- `docs/superpowers/plans/2026-07-29-work-order-master-mixed-man-day.md`
  - 8개 작업, 60개 실행 체크포인트의 TDD 구현 계획을 추가했다.
- `HANDOFF.md`
  - 설계 승인과 구현 계획 완료 상태를 기록했다.

### 6. 검증 결과

- 계획 strict UTF-8 읽기: 성공
- 명세 coverage 검사: 성공
- Task 수 8개, 체크박스 60개 확인
- `TBD`, `TODO`, 구현 생략 placeholder 검사: 발견 없음
- `git diff --check -- <계획 문서>`: 성공
- 애플리케이션 테스트: 미실행
- 실제 Outlook·Excel·GUI 검증: 미실행

### 7. 실패 및 미확인 사항

- 최초 coverage 검사 명령은 PowerShell 인용 오류로 실패했으나 인용에 민감한 문자열을 제거해 재실행했고 성공했다.
- 구현 실행 방식 선택과 코드 구현이 남아 있다.

### 8. 현재 상태

- 설계 승인: 완료
- 구현 계획: 완료
- 코드 구현·자동 검증: 미완료
- 실환경 재검증: 미완료

### 9. 다음 세션 실행 순서

1. 사용자가 subagent-driven 또는 inline 실행 방식을 선택한다.
2. 선택한 실행 skill로 계획 Task 1부터 TDD 순서대로 구현한다.
3. focused/full/static 검증 후 새 테스트 DB로 2026-07-27 Outlook 읽기 전용 재검증을 수행한다.

완료 판단 기준:

- 계획의 completion gate와 승인된 실환경 검증 조건을 모두 충족해야 한다.

### 10. 위험 및 주의사항

- 실제 메일·회사 데이터를 fixture나 로그에 넣지 않는다.
- 기존 최종 스냅샷의 NOT NULL 호환성을 깨지 않는다.
- Outlook은 읽기 전용이며 실제 Excel 쓰기는 별도 사용자 승인 전까지 수행하지 않는다.

### 11. Git 및 변경 경계

- 이번 세션 변경: 신규 구현 계획, `HANDOFF.md`
- 기존 이번 기능 변경: 신규 설계 문서
- 기존 사용자 변경: `.claude/`, `.superpowers/`, `AGENTS.md`, `CLAUDE.md`
- 커밋: 수행하지 않음
- 푸시: 수행하지 않음
- 자동 커밋·푸시 금지: 유지

### 12. 이전 기록 정정

- 없음

## 2026-07-29 15:15:57 KST — 수주 마스터·혼합 야근 공수 설계

### 세션 정보

- 작성 주체: Codex 세션
- 세션 ID: 확인 불가
- 작업 디렉터리: `D:\My_Work\Outsource Workforce Report Collector`
- Git 브랜치: `master`
- 기준 커밋: `efa7305` (`feat: add work report compilation workflow`)

### 1. 세션 목표

- 실환경 메일에서 확인한 업체·사업팀 미기재와 일부 야근 공수 형식을 반영하는 후속 설계를 확정한다.

### 2. 시작 시점 상태

- 2026-07-27 메일에서 수주번호·장비명·인원·야근 인원은 추출되었으나 `투입 공수`는 추출되지 않았다.
- 업체·사업팀 매핑이 없어 생성된 두 공수표 행이 구조적 오류로 차단된 상태였다.

### 3. 핵심 결정

- 별도 수주 마스터에 수주번호·장비명·업체·사업팀·활성 상태를 저장한다.
- 수주번호 정확 일치를 업체·사업팀 자동 입력의 기준으로 사용하고 장비명은 교차 검증한다.
- 장비당 한 행을 유지하며 실제 작업인원과 야근 인원을 분리한다.
- 계산 당일 공수는 `실제 작업인원 + 야근 인원 × 0.5`를 사용한다.
- 전원 주간은 인당 공수 `1.0`, 전원 야근은 `1.5`, 일부 야근은 `혼합`으로 표시한다.

### 4. 수행 내용

- 실제 테스트 DB에서 수주번호 2건과 해당 장비명이 정확히 추출된 사실을 확인했다.
- 추출 레코드에는 실제 인원과 야근 인원이 저장되지만 application DTO와 취합 행에서 야근 인원이 누락되는 경계를 확인했다.
- 현재 파서가 `총 공수`만 처리하고 `투입 공수` 라벨을 처리하지 않는 직접 원인을 확인했다.
- 승인된 설계를 신규 설계 문서로 작성하고 미정 표현·필수 목차·UTF-8·diff 형식을 검사했다.

### 5. 변경 파일

- `docs/superpowers/specs/2026-07-29-work-order-master-mixed-man-day-design.md`
  - 수주 마스터, 혼합 야근 계산, 데이터 모델, UI, 오류 코드, migration 및 테스트 설계를 기록했다.
- `HANDOFF.md`
  - 이번 설계 결정과 다음 단계의 사용자 검토 게이트를 기록했다.

### 6. 검증 결과

- 설계 문서 엄격한 UTF-8 읽기 및 필수 구조 검사: 성공
- `TBD`, `TODO`, `미정`, placeholder 검사: 발견 없음
- `git diff --check -- <설계 문서>`: 성공
- 애플리케이션 테스트: 미실행
- 실제 Outlook·Excel·GUI 검증: 미실행

### 7. 실패 및 미확인 사항

- 설계 문서에 대한 사용자 최종 검토가 남아 있다.
- 구현 계획과 코드 변경은 아직 시작하지 않았다.

### 8. 현재 상태

- 설계 대화 및 문서화: 완료
- 사용자 문서 검토: 대기
- 구현 계획·구현·자동 검증: 미완료
- 실환경 재검증: 미완료

### 9. 다음 세션 실행 순서

1. 사용자가 신규 설계 문서를 검토·승인한다.
2. `writing-plans` 절차로 세부 구현 계획을 작성한다.
3. 실패 테스트부터 수주 마스터, 파서, 공수 계산, UI·출력 순으로 구현한다.
4. 자동 검증 후 새 테스트 DB 복제본으로 2026-07-27 Outlook 읽기 전용 재검증을 수행한다.

완료 판단 기준:

- 설계 승인 후 구현·자동 검증과 승인된 실환경 재검증을 모두 완료해야 한다.

### 10. 위험 및 주의사항

- 혼합 야근을 단일 숫자 인당 공수로 평균내지 않는다.
- 수주번호 미등록·야근 인원 오류·보고 공수 불일치를 임의 보정하지 않는다.
- 실제 메일 본문·개인정보·회사 기밀을 fixture, 로그, 문서에 기록하지 않는다.
- Outlook은 읽기 전용이며 실제 Excel 쓰기는 별도 사용자 승인 전까지 수행하지 않는다.

### 11. Git 및 변경 경계

- 이번 세션 변경: 신규 설계 문서, `HANDOFF.md`
- 기존 사용자 변경: `.claude/`, `.superpowers/`, `AGENTS.md`, `CLAUDE.md`
- 커밋: 수행하지 않음
- 푸시: 수행하지 않음
- 자동 커밋·푸시 금지: 유지

### 12. 이전 기록 정정

- 없음

## 2026-07-29 13:41:29 KST — 7월 27일 Outlook 수집·파싱 실환경 확인

### 세션 정보

- 작성 주체: Codex 세션
- 세션 ID: 확인 불가
- 작업 디렉터리: `D:\My_Work\Outsource Workforce Report Collector`
- Git 브랜치: `master`
- 기준 커밋: `efa7305` (`feat: add work report compilation workflow`)

### 1. 세션 목표

- 사용자가 지정한 2026-07-27 받은 편지함에서 등록 담당자 메일의 수집·파싱·공수표 동기화 경로를 확인한다.

### 2. 시작 시점 상태

- 테스트 DB와 등록 담당자 1명, Outlook `받은 편지함` 설정이 준비되어 있었다.
- 2026-07-28에는 등록 담당자의 발신 메일이 없음을 확인한 상태였다.

### 3. 핵심 결정

- 테스트 DB에만 결과를 기록하고 실제 메일 내용·주소·EntryID는 출력하거나 문서화하지 않는다.
- 조회 전후 읽음 상태를 비교해 Outlook 비변경 경계를 검증한다.

### 4. 수행 내용

- 2026-07-27 00:00 이상, 2026-07-28 00:00 미만 범위를 읽기 전용으로 조회했다.
- 등록 담당자 메일 1건을 수집·본문 조회하고 추출 레코드 및 공수표 행 각 2건을 생성했다.
- 두 행의 날짜는 모두 2026-07-27로 해석되었고 날짜 관련 경고는 없었다.
- 두 행 모두 업체·사업팀·인원·인당 공수가 비어 구조적 차단 상태임을 확인했다.

### 5. 변경 파일

- `HANDOFF.md`
  - 7월 27일 실환경 수집·파싱 결과를 기록했다.
- `local-test\collector-test-20260729.db`
  - 수집·추출·공수표 결과가 기록된 Git 제외 테스트 DB다.

### 6. 검증 결과

- 등록 담당자 메일: 1건 수집, 본문 조회 1건
- 추출 레코드 및 공수표 행: 각 2건
- 수집·추출 오류 및 날짜 경고: 0건
- 행 이슈: `SERIES_KEY_MISSING` 2건, `INVALID_VALUE` 2건
- 최종 확정 차단: `REQUIRED_FIELD_MISSING`, `CONFIRMED_MAN_DAY_MISSING` 포함 각 2건
- 조회 범위 메일 31건의 읽음 상태 비교: 변경 0건
- 실제 Excel·메일 작성·GUI 검토: 미실행

### 7. 실패 및 미확인 사항

- 실제 메일 형식에서 업체·사업팀·인원·인당 공수가 추출되지 않은 원인은 아직 조사하지 않았다.
- Computer Use 플러그인 도구 부재로 GUI 자동 검토는 수행하지 못했다.

### 8. 현재 상태

- Outlook 읽기 전용 수집: 완료
- 실제 메일 날짜 해석: 완료
- 상세 공수표 파싱: 부분 완료
- 최종 표 확정: 차단됨

### 9. 다음 세션 실행 순서

1. 실제 메일에서 보존된 최소 근거 구간과 익명화 가능한 구조를 확인한다.
2. 재현 가능한 익명화 fixture와 실패 테스트를 먼저 작성한다.
3. 파서 수정 후 관련 회귀 테스트와 테스트 DB 재수집을 수행한다.
4. GUI에서 문제 행 검토와 최종 표 미리보기를 확인한다.

완료 판단 기준:

- 업체·사업팀·인원·인당 공수가 올바르게 추출되고 두 행의 구조적 차단이 해결되어야 한다.

### 10. 위험 및 주의사항

- 실제 메일 본문·회사명·개인정보를 소스, fixture, 로그, HANDOFF에 기록하지 않는다.
- Outlook 메일 삭제·이동·읽음 상태 변경·회신·전달을 하지 않는다.
- 실제 Excel 쓰기는 별도 사용자 승인 전까지 수행하지 않는다.

### 11. Git 및 변경 경계

- 이번 세션 변경: `HANDOFF.md`, Git 제외 테스트 DB
- 기존 사용자 변경: `.claude/`, `.superpowers/`, `AGENTS.md`, `CLAUDE.md`
- 커밋: 수행하지 않음
- 푸시: 수행하지 않음
- 자동 커밋·푸시 금지: 유지

### 12. 이전 기록 정정

- 없음

## 2026-07-29 13:32:07 KST — 7월 28일 Outlook 읽기 전용 실환경 확인

### 세션 정보

- 작성 주체: Codex 세션
- 세션 ID: 확인 불가
- 작업 디렉터리: `D:\My_Work\Outsource Workforce Report Collector`
- Git 브랜치: `master`
- 기준 커밋: `efa7305` (`feat: add work report compilation workflow`)

### 1. 세션 목표

- 테스트 DB를 사용해 2026-07-28 받은 편지함 수집 경로를 읽기 전용으로 확인한다.

### 2. 시작 시점 상태

- 테스트 DB `local-test\collector-test-20260729.db`가 준비되어 있었다.
- Outlook 조회 날짜는 사용자가 2026-07-28로 지정했다.

### 3. 핵심 결정

- 메일 제목·본문·주소 등 실제 데이터는 출력하지 않고 건수와 오류·경고 코드만 확인한다.
- Outlook 읽음 상태를 조회 전후 비교해 비변경 여부를 검증한다.

### 4. 수행 내용

- 테스트 DB 설정의 `받은 편지함`에서 2026-07-28 00:00 이상,
  2026-07-29 00:00 미만 범위를 조회했다.
- 해당 날짜의 메일 항목 26건을 확인했고 등록 담당자 1명의 SMTP 주소와 일치하는 메일은 0건이었다.
- 저장 주소의 꺾쇠 제거 및 표준 주소 파싱 방식으로도 일치 건수는 0건임을 확인했다.
- 일치 메일이 없어 본문 열기·추출·공수표 행 생성은 발생하지 않았다.

### 5. 변경 파일

- `HANDOFF.md`
  - Outlook 읽기 전용 실환경 확인 결과와 차단 조건을 기록했다.
- `local-test\collector-test-20260729.db`
  - 테스트 실행 경로로만 사용했으며 Git에서 제외된다.

### 6. 검증 결과

- 조회 범위 내 Outlook 메일 항목: 26건
- 등록 담당자 일치 메일/본문 조회/추출 레코드/공수표 행: 모두 0건
- 수집 오류 및 추출 오류: 0건
- 조회 전후 읽음 상태 비교: 26건 확인, 변경 0건
- 실제 Excel·메일 작성·GUI 조작 검증: 미실행

### 7. 실패 및 미확인 사항

- 등록 담당자 주소가 해당 날짜의 실제 SMTP 발신자와 일치하지 않아 파싱 이후 흐름을 검증하지 못했다.
- 사용자가 지정한 7월 28일이 메일 수신일인지 작업일인지 추가 확인이 필요하다.
- Computer Use 플러그인에 필요한 `node_repl` 도구가 노출되지 않아 GUI 자동화는 수행하지 못했다.

### 8. 현재 상태

- Outlook 날짜 필터 및 읽기 전용 접근: 완료
- 등록 담당자 기반 수집: 정상적인 0건 결과
- 파싱·상세 공수표·GUI 검증: 차단됨

### 9. 다음 세션 실행 순서

1. 7월 28일의 의미가 메일 수신일인지 작업일인지 확인한다.
2. 테스트 DB의 등록 담당자 주소가 실제 보고 발신자와 맞는지 사용자가 설정 화면에서 확인한다.
3. 올바른 수신일·등록 주소로 다시 수집하고 파싱·상세 공수표 흐름을 검증한다.

완료 판단 기준:

- 등록 담당자와 일치하는 메일을 테스트 DB로 수집해 파싱 및 공수표 행까지 확인해야 한다.

### 10. 위험 및 주의사항

- 실제 주소·제목·본문·EntryID는 로그나 문서에 기록하지 않는다.
- Outlook 메일 삭제·이동·읽음 상태 변경·회신·전달을 하지 않는다.
- 실제 Excel 쓰기는 별도 사용자 승인 전까지 수행하지 않는다.

### 11. Git 및 변경 경계

- 이번 세션 변경: `HANDOFF.md`, Git 제외 테스트 DB
- 기존 사용자 변경: `.claude/`, `.superpowers/`, `AGENTS.md`, `CLAUDE.md`
- 커밋: 수행하지 않음
- 푸시: 수행하지 않음
- 자동 커밋·푸시 금지: 유지

### 12. 이전 기록 정정

- 없음

## 2026-07-29 13:18:59 KST — 테스트용 SQLite DB 복제

### 세션 정보

- 작성 주체: Codex 세션
- 세션 ID: 확인 불가
- 작업 디렉터리: `D:\My_Work\Outsource Workforce Report Collector`
- Git 브랜치: `master`
- 기준 커밋: `efa7305` (`feat: add work report compilation workflow`)

### 1. 세션 목표

- 앱의 기본 SQLite DB 존재 여부를 확인하고 실환경 검증에 사용할 안전한 테스트 복제본을 준비한다.

### 2. 시작 시점 상태

- 기본 DB 경로와 복제본 유무가 사용자에게 확인되지 않은 상태였다.
- 추적 파일 변경은 없었고 `.claude/`, `.superpowers/`, `AGENTS.md`, `CLAUDE.md`는 기존 미추적 상태였다.

### 3. 핵심 결정

- 원본 DB를 직접 시험에 사용하지 않고 SQLite backup API로 일관된 테스트 복제본을 만든다.
- 실제 데이터 내용은 열람하거나 출력하지 않고 파일 메타데이터와 무결성만 확인한다.

### 4. 수행 내용

- 기본 DB `C:\Users\sjyang\AppData\Local\OutsourceMailCollector\collector.db`의 존재를 확인했다.
- `local-test\collector-test-20260729.db`에 SQLite 백업 복제본을 생성했다.
- 원본 DB에는 쓰기 작업을 수행하지 않았다.

### 5. 변경 파일

- `HANDOFF.md`
  - DB 확인·복제 및 검증 경계를 기록했다.
- `local-test\collector-test-20260729.db`
  - 테스트용 런타임 복제본이며 `*.db` 규칙으로 Git에서 제외된다.

### 6. 검증 결과

- `PRAGMA integrity_check`: `ok`
- `git check-ignore -v local-test/collector-test-20260729.db`: `.gitignore`의 `*.db` 규칙 적용 확인
- 실제 Outlook·Excel·GUI 검증: 미실행

### 7. 실패 및 미확인 사항

- 테스트 복제본을 사용하는 GUI 실행 및 Outlook 읽기 전용 수집은 아직 실행하지 않았다.
- 테스트에 사용할 Outlook 조회 날짜 범위는 아직 확정되지 않았다.

### 8. 현재 상태

- 테스트 DB 준비: 완료
- 실제 Outlook·GUI 검증: 실환경 검증 필요

### 9. 다음 세션 실행 순서

1. 테스트 복제본을 주입하여 앱을 실행한다.
2. 사용자가 승인한 날짜 범위에서 Outlook을 읽기 전용으로 조회한다.
3. 수집·검토·상세 공수표 미리보기를 확인하며 원본 DB와 실제 Excel에는 쓰지 않는다.

완료 판단 기준:

- 테스트 DB를 사용한 GUI·Outlook 읽기 전용 검증 결과가 명확히 기록되어야 한다.

### 10. 위험 및 주의사항

- 복제본에도 로컬 처리 이력과 설정이 포함될 수 있으므로 커밋·외부 전송하지 않는다.
- Outlook 메일 삭제·이동·읽음 상태 변경·회신·전달을 하지 않는다.
- 실제 Excel 파일 쓰기는 별도 사용자 승인 전까지 수행하지 않는다.

### 11. Git 및 변경 경계

- 이번 세션 변경: `HANDOFF.md`, Git 제외 테스트 DB
- 기존 사용자 변경: `.claude/`, `.superpowers/`, `AGENTS.md`, `CLAUDE.md`
- 커밋: 수행하지 않음
- 푸시: 수행하지 않음
- 자동 커밋·푸시 금지: 유지

### 12. 이전 기록 정정

- 없음

## 2026-07-29 12:43:07 KST — 상세 외주 공수표 구현 세션 최종 인계

### 세션 정보

- 작성 주체: Codex 세션
- 세션 ID: 확인 불가
- 작업 디렉터리: `D:\My_Work\Outsource Workforce Report Collector`
- Git 브랜치: `master`
- 기준 커밋: `da9ee1e` (`feat: assemble persistent collector application`)

### 1. 세션 목표

- 현재 세션에서 구현한 상세 외주 공수표 취합 기능의 최종 상태를 다음 세션이
  즉시 이어받을 수 있도록 정리한다.

### 2. 시작 시점 상태

- 바로 아래 `2026-07-29 12:36:26 KST` 기록에 전체 구현 범위, 변경 파일과
  검증 결과가 정리되어 있었다.
- 작업 트리는 `master`, 기준 커밋 `da9ee1e`이며 구현 변경은 커밋되지 않은
  상태였다.

### 3. 핵심 결정

- 이전 구현 결정을 변경하지 않았다.
- 중복·수정 보고 해결 결과는 같은 추출 레코드를 다시 동기화해도 미해결 상태로
  되돌아가면 안 된다.
- 현재 단계의 완료 상태는 `자동 검증 완료, 실환경 검증 필요`로 유지한다.

### 4. 수행 내용

- `HANDOFF.md` 최신 구현 기록과 현재 Git 변경 경계를 재확인했다.
- 중복 해결 후 재동기화 회귀를 최종 구현에 반영한 상태임을 명시했다.
- 현 세션 인계를 새 최신 기록으로 추가하고 과거 기록은 보존했다.

### 5. 변경 파일

- 이번 인계 정리에서 추가 변경:
  - `HANDOFF.md`
- 현 작업 트리의 전체 구현 변경 파일은 바로 아래
  `2026-07-29 12:36:26 KST` 기록의 `5. 변경 파일`을 기준으로 한다.

### 6. 검증 결과

- 구현 완료 후 가장 최근 전체 검증:
  - `.\.venv\Scripts\python.exe -m pytest -q --basetemp
    .pytest-basetemp-work-report-final-2`
  - 결과: `105 passed in 33.05s`
- `.\.venv\Scripts\python.exe -m compileall -q src tests` → 성공
- `git diff --check` → 오류 없음
- `HANDOFF.md` 등 7개 주요 문서 strict UTF-8 검사 → 통과
- 미추적 소스·테스트·문서 후행 공백 검사 → 이상 없음
- 이번 인계 작성 턴에서는 코드 변경이나 애플리케이션 테스트를 새로 실행하지
  않았고, 직전 구현 완료 검증 결과와 현재 Git 상태를 확인했다.

### 7. 실패 및 미확인 사항

- 첫 Git·HANDOFF 동시 조회 명령은 10초 제한을 넘어 시간 초과됐다.
- 파일 변경 없이 Git 상태와 HANDOFF 조회를 분리해 재실행했고 정상 확인했다.
- 실제 Outlook 수집, 실제 Windows 클립보드, Outlook 붙여넣기 모양과 실제 GUI
  사용자 조작은 아직 검증하지 않았다.

### 8. 현재 상태

- 상태: 구현 및 자동 검증 완료, 실환경 검증 필요
- 상세 외주 공수표 취합, 검토, 수동 행, 누적·중복 검증, 최종 스냅샷,
  HTML·일반 텍스트 복사 경로가 구현되어 있다.
- Outlook은 읽기 전용이고 Excel 쓰기는 계속 비활성 안내 상태다.

### 9. 다음 세션 실행 순서

1. 최신 기록과 바로 아래 전체 구현 기록을 함께 읽는다.
2. `git status --short --branch`와 `da9ee1e` 기준 변경을 확인한다.
3. 사용자 승인 아래 테스트/복사 DB로 애플리케이션을 실행한다.
4. 승인된 Outlook 날짜를 읽기 전용 조회해 제목·본문·수신일 경고를 확인한다.
5. 수동 예외 행, 누적 기준, 중복 해결 유지와 여러 작업일 미리보기를 확인한다.
6. 미발송 테스트 메일에 표를 붙여 넣어 값과 반복 머리글을 비교한다.

### 10. 위험 및 주의사항

- 실제 메일·회사·개인 데이터와 `samples/*.msg`를 소스·테스트·문서·로그·커밋에
  포함하지 않는다.
- Outlook 삭제·이동·읽음 변경·회신·전달·발송을 수행하지 않는다.
- 실제 Outlook/클립보드/GUI 검증은 코드 단위 테스트 통과와 구분해 기록한다.
- 기존 미추적 사용자 파일을 삭제·수정·스테이징하지 않는다.

### 11. Git 및 변경 경계

- 브랜치: `master`
- 기준 커밋: `da9ee1e`
- 커밋: 수행하지 않음
- 푸시: 수행하지 않음
- 브랜치 변경·생성: 수행하지 않음
- 현재 추적·미추적 구현 변경은 작업 트리에 그대로 보존되어 있다.

### 12. 이전 기록 정정

- 바로 아래 기록의 최종 전체 검증 `105 passed in 32.71s` 이후 중복 해결 유지
  회귀를 보강하고 다시 전체 검증했다. 최신 근거는
  `.pytest-basetemp-work-report-final-2`의 `105 passed in 33.05s`다.

## 2026-07-29 12:36:26 KST — 상세 외주 공수표 취합 기능 구현

### 세션 정보

- 작성 주체: Codex 세션
- 세션 ID: 확인 불가
- 작업 디렉터리: `D:\My_Work\Outsource Workforce Report Collector`
- Git 브랜치: `master`
- 기준 커밋: `da9ee1e` (`feat: assemble persistent collector application`)

### 1. 세션 목표

- 승인된 상세 외주 공수표 취합 설계와 10개 Task 구현 계획을 TDD로 구현한다.
- 제목 우선 작업일, 공수 계산·누적 검증, 수동 행, 중복 처리, 최종 스냅샷,
  HTML·일반 텍스트 복사와 확장 검토 UI를 기존 애플리케이션에 연결한다.
- Outlook 읽기 전용과 Excel 준비 중 경계를 유지한다.

### 2. 시작 시점 상태

- 기준 커밋은 `da9ee1e`, 브랜치는 `master`였다.
- 기존 자동화 테스트는 `.venv`에서 45개 통과했다.
- 기존 미추적 `AGENTS.md`, `CLAUDE.md`, `HANDOFF.md`, `.superpowers/`와 승인된
  설계·계획 문서를 사용자 변경으로 보존했다.
- 애플리케이션에는 Outlook 수집·추출·기존 검토 그리드·설정·SQLite가 있었으나
  상세 공수 취합 행, 누적 계열, 최종 스냅샷과 복사 기능은 없었다.

### 3. 핵심 결정

- 상단 인원 요약표는 제외하고 장비별 상세 외주 공수표만 구현했다.
- Outlook 수신 조회일과 작업일 범위를 분리했다. 기본 화면은 오늘 수신일과 어제
  작업일로 열린다.
- 작업일은 제목 날짜를 우선하고 본문·수신일은 교차 검증한다. 날짜 근거가 없으면
  수신일로 추정하지 않는다.
- 공수는 `Decimal`, 소수점 한 자리, `ROUND_HALF_UP`으로 계산하며 메일 보고값,
  계산값, 사용자 확정값을 분리한다.
- 누적 계열은 업체명+Tracking No.를 우선하고 Tracking No.가 없을 때만 장비명을
  사용한다.
- 최초 누적 기준, 공수 불일치, 중복·수정 후보는 사용자 확인을 요구한다.
- 정상 행 자동 포함, 문제 행 개별 확인, 전체 최종 확인 뒤에만 복사를 허용한다.
- 최종 표는 불변 DB 스냅샷이며 HTML과 탭 구분 일반 텍스트를 함께 복사한다.

### 4. 수행 내용

- 공수·문제 코드·행 출처 도메인과 Decimal 계산 서비스를 추가했다.
- `26_07_29`, 점 구분 날짜, `7월 29일` 형식을 지원하는 제목 우선 작업일 파서를
  추가하고 추출 오케스트레이터 앞단에 연결했다.
- 기존 DB를 삭제하지 않는 additive migration으로 날짜 근거, 업체 정렬 순서,
  취합 행, 최종 보고서와 스냅샷 테이블·인덱스를 추가했다.
- 메일 추출 행과 수동 행을 동일 규칙으로 취합하고 중복 후보를 합산하지 않는
  `WorkReportService`를 구현했다.
- 최초 누적 기준 확정 후 같은 계열의 후속 미확정 행을 다시 계산하도록 구현했다.
- 차단 조건 재검증, 업체 설정 순서 정렬, 해시·불변 스냅샷을 구현했다.
- Outlook 붙여넣기에 맞는 인라인 HTML 표와 일반 텍스트 렌더러를 구현했다.
- 확장 검토 그리드, 수동 행, 문제 검토, 최종 미리보기, Qt 클립보드 경계를
  구현하고 메인 화면·백그라운드 작업·서비스 조립에 연결했다.
- PRD, TRD, 시스템 아키텍처, ADR에 현재 구현 범위와 제약을 추가했다.

### 5. 변경 파일

- 도메인·파싱
  - `src/outsource_mail_collector/domain/__init__.py`
  - `src/outsource_mail_collector/domain/models.py`
  - `src/outsource_mail_collector/domain/work_report.py`
  - `src/outsource_mail_collector/parsing/work_date_parser.py`
- 애플리케이션
  - `src/outsource_mail_collector/app.py`
  - `src/outsource_mail_collector/application/container.py`
  - `src/outsource_mail_collector/application/extraction_orchestrator.py`
  - `src/outsource_mail_collector/application/models.py`
  - `src/outsource_mail_collector/application/man_day_calculation_service.py`
  - `src/outsource_mail_collector/application/work_report_service.py`
  - `src/outsource_mail_collector/application/final_report_service.py`
  - `src/outsource_mail_collector/application/report_renderer.py`
- 인프라
  - `src/outsource_mail_collector/infrastructure/db/schema.sql`
  - `src/outsource_mail_collector/infrastructure/db/repository.py`
  - `src/outsource_mail_collector/infrastructure/outlook_adapter.py`
- UI
  - `src/outsource_mail_collector/ui/main_window.py`
  - `src/outsource_mail_collector/ui/review_grid.py`
  - `src/outsource_mail_collector/ui/workers.py`
  - `src/outsource_mail_collector/ui/manual_row_dialog.py`
  - `src/outsource_mail_collector/ui/problem_review_dialog.py`
  - `src/outsource_mail_collector/ui/final_report_dialog.py`
  - `src/outsource_mail_collector/ui/clipboard.py`
- 테스트
  - `tests/fixtures.py`
  - `tests/test_extraction_orchestrator.py`
  - `tests/test_main_window.py`
  - `tests/test_repository.py`
  - `tests/test_review_grid.py`
  - `tests/test_settings_dialog.py`
  - `tests/test_smoke.py`
  - `tests/test_man_day_calculation_service.py`
  - `tests/test_work_date_parser.py`
  - `tests/test_work_report_service.py`
  - `tests/test_final_report_service.py`
  - `tests/test_report_renderer.py`
  - `tests/test_manual_row_dialog.py`
  - `tests/test_problem_review_dialog.py`
  - `tests/test_final_report_dialog.py`
  - `tests/test_clipboard.py`
  - `tests/test_collection_worker.py`
- 문서
  - `docs/PRD.md`
  - `docs/TRD.md`
  - `docs/SYSTEM_ARCHITECTURE.md`
  - `docs/ADR.md`
  - `HANDOFF.md`

### 6. 검증 결과

- 시작 기준: `.\.venv\Scripts\python.exe -m pytest --basetemp
  .pytest-basetemp-codex-baseline-venv -q` → `45 passed`
- Task별 테스트에서 신규 모듈 부재 또는 기대 동작 미구현 RED를 먼저 확인한 뒤
  최소 구현과 GREEN을 반복했다.
- 최종 전체: `.\.venv\Scripts\python.exe -m pytest -q --basetemp
  .pytest-basetemp-work-report-final` → `105 passed in 32.71s`
- `.\.venv\Scripts\python.exe -m compileall -q src tests` → 성공
- `git diff --check` → 오류 없음
- `git status --short --branch` → `master`, 의도한 추적 변경과 기존·신규 미추적
  파일 확인
- 첫 전체 검증의 중첩 `--basetemp .pytest-tmp\work-report-full`은 상위 폴더가
  없어 fixture 생성 전 `FileNotFoundError`가 발생했다. 저장소 루트의 단일
  basetemp로 재실행해 전체 통과했다.

### 7. 실패 및 미확정 사항

- 실제 Outlook 수집, 실제 Windows 클립보드, Outlook 본문 붙여넣기 모양과 실제
  PySide6 사용자 조작은 실행하지 않았다.
- 실제 메일 제목·본문 날짜 변형은 승인된 실환경 확인이 추가로 필요하다.
- Excel 쓰기는 이번 범위가 아니며 계속 준비 중 안내만 표시한다.
- 자동 테스트의 클립보드는 fake와 Qt 데이터 객체 경계만 검증했다.

### 8. 현재 상태

- 상태: 코드 구현 및 자동 검증 완료, 실환경 검증 필요
- 전체 자동화 테스트 105개가 통과한다.
- 기존 Outlook 읽기 전용 정책과 Excel 비활성 경계는 유지된다.
- 현재 변경은 커밋되지 않은 작업 트리에 있다.

### 9. 다음 세션 실행 순서

1. `HANDOFF.md`, `git status --short --branch`, 기준 커밋을 확인한다.
2. 사용자 승인 아래 테스트/복사 DB로 애플리케이션을 실행한다.
3. 승인된 Outlook 수신일을 읽기 전용으로 조회하고 제목·본문·수신일 경고를
   확인한다.
4. 수동 예외 행과 여러 작업일 미리보기를 확인한다.
5. 확정 표를 복사해 발송하지 않을 테스트 메일 본문에 붙여 넣고 값·반복 머리글을
   비교한다.
6. 사용자가 별도로 승인하지 않으면 메일을 보내지 않고 임시 초안을 닫는다.

### 10. 위험 및 주의사항

- 실제 회사·개인 데이터와 `samples/*.msg`를 테스트·문서·로그·커밋에 넣지 않는다.
- Outlook 원본 열기 외의 삭제·이동·읽음 변경·회신·전달·발송은 금지한다.
- 최초 누적 기준이 없거나 중복이 미해결이면 최종 확정을 우회하지 않는다.
- 취합 원본 변경은 현재 최종 확인을 무효화하지만 과거 스냅샷은 수정하지 않는다.
- 실제 Outlook 붙여넣기 서식은 Office 버전과 보안 정책 영향을 받을 수 있다.

### 11. Git 및 변경 경계

- 커밋: 수행하지 않음
- 푸시: 수행하지 않음
- 브랜치 변경·생성: 수행하지 않음
- 기준 커밋은 `da9ee1e`, 현재 브랜치는 `master`다.
- 기존 미추적 `AGENTS.md`, `CLAUDE.md`, `.superpowers/`와 승인된 설계·계획
  문서를 삭제·수정·스테이징하지 않았다.

### 12. 이전 기록 정정

- 없음

## 2026-07-29 11:51:05 KST — 외주 공수표 취합 기능 설계 및 구현 계획

### 세션 정보

- 작성 주체: Codex 세션
- 세션 ID: 확인 불가
- 작업 디렉터리: `D:\My_Work\Outsource Workforce Report Collector`
- Git 브랜치: `master`
- 기준 커밋: `da9ee1e` (`feat: assemble persistent collector application`)

### 1. 세션 목표

- 최종 보고 메일의 상세 외주 공수표 취합 요구사항을 확인한다.
- 사용자 딥인터뷰로 날짜, 공수 계산, 누적, 중복, 수동 입력, 검토 및 출력 규칙을 확정한다.
- 승인된 UI와 업무 규칙을 설계 문서 및 TDD 구현 계획으로 남긴다.

### 2. 시작 시점 상태

- 기존 애플리케이션은 Outlook 읽기 전용 수집, 파싱, 리뷰 그리드, 설정, SQLite 저장까지 구현되어 있었다.
- 실제 Excel 쓰기는 준비되지 않았으며 안내만 제공하는 상태였다.
- 시작 기준 커밋은 `da9ee1e`였다.
- 기존 미추적 `AGENTS.md`, `CLAUDE.md`, `HANDOFF.md`를 사용자 변경으로 보존했다.

### 3. 핵심 결정

- 상단 지역·업체별 인원 요약표는 제외하고 상세 외주 공수표만 취합한다.
- Outlook에서 읽은 행과 주말·예외 작업용 수동 행을 같은 검증 규칙으로 처리한다.
- 작업일은 제목 날짜를 우선하고 본문 날짜와 수신일은 교차 검증 근거로 사용한다.
- 투입 공수와 누적 공수는 메일 보고값, 프로그램 계산값, 사용자 확정값을 분리한다.
- 공수는 `Decimal`, 소수점 한 자리, `ROUND_HALF_UP`을 사용한다.
- 누적 계열은 `업체 + Tracking No.`를 기본 키로 하고 Tracking No.가 없을 때만 장비명을 사용한다.
- 정상 행 자동 포함, 문제 행 개별 검토, 전체 표 최종 확인 후 HTML·일반 텍스트로 복사한다.
- Outlook 초안 생성·발송과 Excel 쓰기는 이번 범위에서 제외한다.

### 4. 수행 내용

- 샘플 최종 보고 메일의 상세 표 구조와 기존 코드·DB·UI 경계를 확인했다.
- 대안 세 가지를 비교하고 기존 리뷰 화면 확장과 최종 미리보기 방식을 채택했다.
- 로컬 정적 UI 시안으로 확장 리뷰 화면과 최종 미리보기를 확인받았다.
- 아키텍처, 데이터 모델, 계산, 날짜, 중복, 오류, 감사 이력, 테스트 설계를 단계별 승인받았다.
- 승인 설계를 문서화하고 10개 작업·58개 체크 단계의 TDD 구현 계획을 작성했다.

### 5. 변경 파일

- `docs/superpowers/specs/2026-07-29-work-report-compilation-design.md`
  - 승인된 외주 공수표 취합 기능 설계
- `docs/superpowers/plans/2026-07-29-work-report-compilation.md`
  - 파일·테스트·검증 명령 단위의 상세 구현 계획
- `.superpowers/brainstorm/353-1785290375/content/work-report-layout.html`
  - 사용자 확인용 로컬 정적 UI 시안이며 실제 애플리케이션 코드는 아님
- `HANDOFF.md`
  - 현재 세션 기록 추가

### 6. 검증 결과

- 두 신규 문서를 엄격한 UTF-8로 디코딩했다.
- 설계 문서의 필수 섹션, 미결정 placeholder, 민감 표본 포함 여부를 검사했다.
- 구현 계획에서 Task 1~10, TDD 단계, 전체 pytest, `git diff --check`, 무커밋 조건을 확인했다.
- 계획 체크박스는 58개다.
- 문서 공백 검사에서 내용 오류는 없었고 Git의 LF→CRLF 안내만 확인했다.
- 애플리케이션 코드는 변경하지 않아 pytest는 실행하지 않았다.

### 7. 실패 및 미확인 사항

- 현재 플러그인 카탈로그가 가리킨 Superpowers 스킬 파일 경로는 세션 후반에 존재하지 않아 재열람하지 못했다. 앞서 확인한 절차와 승인 흐름을 기준으로 진행했다.
- 실제 Outlook 수집, Windows 클립보드, Outlook 본문 붙여넣기, PySide6 구현 UI는 아직 검증하지 않았다.
- 구현과 DB migration은 아직 시작하지 않았다.

### 8. 현재 상태

- 상태: 설계 및 구현 계획 완료, 구현 미착수
- 설계 문서와 구현 계획은 사용자 승인을 받은 요구사항을 반영했다.
- 애플리케이션 실행 동작은 기준 커밋과 동일하다.

### 9. 다음 세션 실행 순서

1. 설계 문서와 구현 계획을 다시 읽는다.
2. `git status --short --branch`와 기준 커밋을 확인한다.
3. `superpowers:executing-plans`와 TDD 절차로 계획 Task 1부터 순서대로 실행한다.
4. 각 Task에서 실패 테스트를 먼저 확인한 뒤 최소 구현과 관련 회귀 테스트를 수행한다.
5. 전체 자동 검증 후 사용자 승인 아래에서만 Outlook·클립보드·GUI 실환경 검증을 수행한다.

### 10. 위험 및 주의사항

- 기존 `report_date`는 Outlook 수신일로 생성되므로 제목 우선 날짜 판정을 명시적으로 연결해야 한다.
- 기존 추출 공수는 `float/REAL`이므로 신규 확정값으로 옮길 때 `Decimal(str(value))`로 변환해야 한다.
- 최초 누적 기준이 없고 메일 누적값도 없으면 추정하지 말고 확정을 차단해야 한다.
- 중복 후보를 DB 제약으로 삭제하지 말고 사용자 해결 전까지 모두 보존해야 한다.
- 최종 보고 스냅샷은 이후 원본 행 수정으로 바뀌면 안 된다.
- 실제 회사·개인 데이터와 `samples/*.msg`를 fixture, 문서, 로그 또는 커밋에 포함하지 않는다.

### 11. Git 및 변경 경계

- 커밋: 수행하지 않음
- 푸시: 수행하지 않음
- 브랜치 변경: 수행하지 않음
- 기존 미추적 파일을 삭제·수정·스테이징하지 않았다.
- 이번 세션의 프로젝트 문서 변경은 신규 설계·계획 문서와 이 HANDOFF 기록이다.

### 12. 이전 기록 정정

- 없음

## 2026-07-27 17:08:07 KST — 실데이터 연결 구현 및 Outlook 수집 실패 진단

### 세션 정보

- 작성 주체: Codex 세션
- 세션 ID: 확인 불가
- 작업 디렉터리: `D:\My_Work\Outsource Workforce Report Collector`
- Git 브랜치: `master`
- 기준 커밋: `da9ee1e` (`feat: assemble persistent collector application`)

### 1. 세션 목표

- Application 서비스 계층, Outlook COM 어댑터, 실데이터 리뷰 그리드 연결, 설정 화면을 구현한다.
- Excel 버튼은 활성 상태로 유지하되 클릭하면 연동 준비 중 안내를 표시한다.
- 설정은 `%LOCALAPPDATA%\OutsourceMailCollector\collector.db`에 영속 저장한다.
- Outlook COM에서 실제 폴더 목록을 읽어 선택할 수 있게 한다.
- 구현 후 앱을 실행하고 사용자의 실환경 테스트 결과를 진단한다.

제외 범위:

- 실제 Excel 파일 쓰기 구현
- Outlook 메일 삭제·이동·읽음 상태 변경·자동 회신·자동 전달
- PyInstaller 패키징
- 실환경 진단에서 발견한 담당자 이메일 정규화 결함의 수정

### 2. 시작 시점 상태

- 시작 브랜치: `master`
- 시작 기준 커밋: `a491375` (`리뷰 그리드 UI`)
- 리뷰 그리드는 더미 데이터만 사용했고 `application/` 패키지는 비어 있었다.
- Outlook/Excel 어댑터는 Protocol 또는 TODO 상태였다.
- 직원·업체 설정 화면과 영속 DB 연결이 없었다.
- 사용자는 별도 브랜치 없이 `master`에서 직접 구현하는 것을 승인했다.
- 기존 미추적 `.claude/`, `CLAUDE.md`는 작업 범위에서 제외했다.

### 3. 핵심 결정

- 서비스 계층을 UI와 COM/SQLite 사이의 경계로 유지했다.
- Outlook COM 작업은 `QThread`에서 실행하고 작업 스레드 안에서 `CoInitialize`/`CoUninitialize`한다.
- Outlook 접근은 읽기 전용으로 제한하고, 원본 메일 열기는 사용자 명시 동작에서만 `Display()`를 호출한다.
- DB는 사용자별 LocalAppData 경로를 기본값으로 사용하고 공개 저장소 작업마다 짧은 SQLite 연결을 열고 닫는다.
- 메일 수집은 조회일의 `[00:00, 다음 날 00:00)` 범위와 선택 폴더를 사용한다.
- 직원 이메일과 Outlook 발신자 SMTP 주소는 소문자·양끝 공백 제거 후 완전 일치시킨다.
- Excel 반영은 구현하지 않고 활성 버튼의 안내 메시지만 제공한다.

검토 후 채택하지 않은 방식:

- UI에서 COM 객체 직접 호출: 계층 분리와 스레드 안전성 때문에 채택하지 않았다.
- 더미 데이터와 실데이터 병행 표시: 실제 처리 상태를 오해할 수 있어 채택하지 않았다.
- 이번 세션에서 Excel 쓰기까지 확장: 실 워크북 구조가 확보되지 않아 제외했다.

### 4. 수행 내용

- 상세 설계와 구현 계획을 작성하고 커밋했다.
- SQLite repository에 설정·직원·업체 CRUD, 처리 메일·추출 결과·검토 상태·작업 로그 기능과 additive migration을 추가했다.
- `MailCollectionService`, `ExtractionOrchestrator`, `ReviewService`, `ExcelExportService`, `SettingsService` 및 서비스 컨테이너를 구현했다.
- 실제 Outlook 받은편지함과 하위 폴더를 재귀 조회하고 DASL 날짜 필터, Exchange 발신자 SMTP 변환, 메일 메타데이터·본문 읽기, 원본 표시를 지원하는 읽기 전용 어댑터를 구현했다.
- 일반/담당자/업체 탭을 가진 설정 대화상자와 실제 Outlook 폴더 새로고침 작업자를 구현했다.
- 메인 화면의 메일 가져오기, 요약 통계, 미보고 배너, 리뷰 그리드, 원본 열기, 상태 변경 및 Excel 안내를 실 서비스에 연결했다.
- 앱을 가상환경 Python으로 실행했으며, 사용자가 메인 화면·설정 화면·Outlook 원본 메일 화면이 표시되는 것을 스크린샷으로 확인했다.
- 사용자의 실환경 테스트에서 대상 1명, 수신 메일 0건, 미보고 1명으로 표시되는 문제를 조사했다.
- LocalAppData DB를 읽기 전용으로 조사한 결과 다음을 확인했다.
  - Outlook 폴더 설정은 실제 받은편지함 이름으로 저장되어 있었다.
  - 활성 담당자는 1명이었다.
  - 담당자 이메일이 `<주소>` 형식으로 저장되어 있었다.
  - 처리 메일과 추출 결과는 모두 0건이었다.
- 코드 데이터 흐름을 역추적한 결과 Outlook 어댑터는 `주소`만 반환하지만 담당자 입력값은 `<주소>` 그대로 저장되고, 수집 서비스는 두 값을 완전 일치 비교하여 메일을 제외하는 것을 확인했다.

### 5. 변경 파일

- `docs/superpowers/specs/2026-07-27-collection-review-settings-design.md`
  - 승인된 서비스·UI·영속화·Outlook 연결 설계
- `docs/superpowers/plans/2026-07-27-collection-review-settings.md`
  - TDD 기반 구현 계획
- `src/outsource_mail_collector/application/`
  - 수집, 추출 오케스트레이션, 리뷰, 설정, Excel 안내 서비스와 DTO·오류·컨테이너
- `src/outsource_mail_collector/infrastructure/db/repository.py`
  - 영속 DB 경로와 repository 기능, 연결 수명 보장
- `src/outsource_mail_collector/infrastructure/db/schema.sql`
  - 처리 메일·추출 결과 필드 확장
- `src/outsource_mail_collector/infrastructure/outlook_adapter.py`
  - 읽기 전용 Outlook COM 구현
- `src/outsource_mail_collector/ui/main_window.py`
  - 실 서비스 기반 수집·검토 화면 연결
- `src/outsource_mail_collector/ui/review_grid.py`
  - DB 레코드 ID와 편집·원본·제외 액션 연결
- `src/outsource_mail_collector/ui/settings_dialog.py`
  - 일반·담당자·업체 설정 화면
- `src/outsource_mail_collector/ui/workers.py`
  - Outlook 폴더 조회 및 메일 수집 백그라운드 작업자
- `src/outsource_mail_collector/app.py`
  - 영속 서비스 조립 및 메인 창 주입
- `tests/`
  - repository, 서비스, Outlook 어댑터, 설정 화면, 메인 화면 회귀 테스트 추가
- `README.md`
  - DB 경로, 설정 우선 실행 흐름, 실행·검증 방법, Outlook 읽기 전용 및 Excel 미구현 상태 기록
- `HANDOFF.md`
  - 이 세션 인계 기록 추가

### 6. 검증 결과

- `.\.venv\Scripts\python.exe -m pytest -q`: `45 passed in 4.21s`
- `.\.venv\Scripts\python.exe -m compileall -q src tests`: 성공, 출력 없음
- 최종 구현 커밋 후 `git status --short --branch`: 추적 파일 변경 없음, 기존·별도 문서 미추적 항목만 존재
- GUI 실행: 성공
  - 메인 창과 설정 대화상자 렌더링을 사용자 스크린샷으로 확인
  - 실제 Outlook 화면에서 선택한 조회일의 업무보고 메일 존재를 사용자 스크린샷으로 확인
- 실환경 메일 수집: 실패 증상 재현
  - 대상 1명, 수신 0건, 미보고 1명
- DB 진단: 완료
  - 담당자 이메일의 꺾쇠 포함 저장과 처리 결과 0건 확인
- 코드 경로 진단: 완료
  - 입력 저장은 `strip().lower()`만 수행하고 수집 서비스는 SMTP 주소와 완전 일치 비교함을 확인
- 실제 Excel 반영: 미실행
  - 기능이 아직 구현되지 않았으며 안내 메시지만 제공

### 7. 실패 및 미확인 사항

- 실제 Outlook의 2026-07-24 제한 결과 건수와 발신자 SMTP 주소를 별도 진단 명령으로 읽으려 했으나 COM 호출이 두 차례 각각 20초와 30초 제한 시간을 초과했다.
- 위 제한 시간 초과가 기존 실행 앱과의 COM 경합, Outlook 응답 지연 또는 쿼리 성능 문제인지는 확인하지 못했다.
- Outlook 날짜 필터 구현은 Phase 0 PoC와 동일한 DASL 형식이지만 이번 세션의 별도 count-only 실환경 진단은 완료하지 못했다.
- 이메일 정규화 결함은 원인만 확인했으며 코드와 현재 DB 데이터는 수정하지 않았다.
- 현재 설정의 별칭 열은 메일 발신자 매칭에 사용되지 않는다. 이메일 별칭 지원이 필요한지는 사용자 결정이 필요하다.
- 처리 로그 보기 화면은 아직 안내 메시지만 제공한다.

### 8. 현재 상태

- Application 서비스 계층: 완료
- 읽기 전용 Outlook COM 어댑터: 코드 구현 완료, 추가 실환경 안정성 검증 필요
- 리뷰 그리드 실데이터 연결: 완료
- 설정 화면 및 실제 Outlook 폴더 선택: 완료
- LocalAppData DB 영속화: 완료
- Excel 안내 버튼: 완료
- 실제 Excel 쓰기: 미완료
- 담당자 이메일 정규화: 미완료
- 현재 실데이터 수집 성공: 담당자 이메일 형식 불일치로 차단됨
- Git 커밋 및 푸시: 구현 커밋 완료, 원격 푸시는 수행하지 않음

### 9. 다음 세션 실행 순서

1. `git status --short --branch`와 `da9ee1e` 이후 변경 여부를 확인한다.
2. 담당자 저장 및 수집 경계에서 이메일 정규화가 필요한 형식을 회귀 테스트로 먼저 추가한다.
  - `address@example.com`
  - `<address@example.com>`
  - `표시 이름 <address@example.com>`
  - 대소문자와 앞뒤 공백
3. 표준 라이브러리 `email.utils.parseaddr` 등을 사용해 한 개의 유효한 SMTP 주소로 정규화하고, 유효하지 않은 입력은 설정 저장 시 사용자에게 알린다.
4. 기존 DB의 `<주소>` 값도 재저장 또는 읽기 시 안전하게 정규화되도록 호환 경계를 정한다.
5. 전체 테스트와 compileall을 실행한다.
6. 앱을 다시 실행하여 동일 조회일·받은편지함에서 수신 메일 수, 미보고 상태와 추출 그리드를 확인한다.
7. 실제 COM 조회가 다시 지연되면 `Restrict(...).Count`, 메일 열거, Exchange SMTP 변환 단계를 분리 계측한다.
8. 사용자 확인 후 업체 마스터와 추가 담당자 정보를 등록하고 실제 메일 포맷의 추출 결과를 검토한다.

완료 판단 기준:

- `<주소>` 또는 `표시 이름 <주소>` 입력이 canonical SMTP 주소로 저장·비교된다.
- 회귀 테스트와 전체 테스트가 통과한다.
- 동일 실메일이 등록 담당자의 수신 메일로 집계되고 미보고 목록에서 제외된다.
- 추출 대상 메일의 레코드가 리뷰 그리드에 표시되거나, 외주 정보가 없다는 명확한 처리 결과가 남는다.

### 10. 위험 및 주의사항

- Outlook은 계속 읽기 전용으로 유지하며 삭제·이동·읽음 변경·자동 회신·자동 전달을 추가하지 않는다.
- 실환경 진단에서도 메일 본문과 전체 수신자 목록을 로그나 핸드오프에 남기지 않는다.
- DRM 에이전트 문제 때문에 새 메일 fixture를 `.txt`로 만들지 말고 `tests/fixtures.py`의 문자열 상수 패턴을 사용한다.
- 실제 Excel 쓰기는 실 워크북 구조 확인, 사용자 승인, 타임스탬프 백업 전에는 구현·실행하지 않는다.
- LocalAppData DB에는 실제 사용자 설정이 있으므로 테스트에서 기본 DB를 사용하지 말고 임시 DB 경로를 주입한다.
- COM 지연 문제와 이메일 매칭 문제를 한 번에 수정하지 말고 각각 독립적으로 재현·검증한다.

### 11. Git 및 변경 경계

- 구현 커밋:
  - `01f3a6e` — `docs: add collection review settings design`
  - `16739fc` — `docs: add collection review settings plan`
  - `b93e0d0` — `feat: add persistent collector repository`
  - `b8912fc` — `feat: add mail collection service`
  - `1ccef0d` — `feat: orchestrate extraction persistence`
  - `4b1ccf0` — `feat: add review and export services`
  - `420e988` — `feat: implement read-only Outlook adapter`
  - `1f38bde` — `feat: add collector settings dialog`
  - `bb56160` — `feat: connect review grid to collector services`
  - `da9ee1e` — `feat: assemble persistent collector application`
- 이번 기록 작업 변경:
  - `HANDOFF.md`
- 현재 미추적 항목:
  - `.claude/`
  - `AGENTS.md`
  - `CLAUDE.md`
  - `HANDOFF.md`
- 기존 사용자 파일의 수정 또는 삭제: 없음
- 진단 중 LocalAppData DB 수정: 없음
- 커밋: 이 핸드오프 기록은 커밋하지 않음
- 푸시: 수행하지 않음
- 자동 커밋·푸시 금지: 유지

### 12. 이전 기록 정정

- 이전 기록에는 저장소 시작 상태가 애플리케이션 스켈레톤으로 남아 있으나, 현재 기준 구현은 `da9ee1e`까지 완료되었다.
- `CLAUDE.md`의 “application 서비스와 Outlook 어댑터 미구현” 설명은 현재 코드 상태보다 오래된 내용이다. 다음 문서 정비 시 갱신이 필요하다.

---

## 새 세션 기록 템플릿

아래 블록을 복사하여 `세션 기록`의 가장 위에 추가한다. 대괄호 항목을 실제 값으로 바꾸고,
해당 사항이 없으면 `없음`으로 기록한다.

```markdown
## [YYYY-MM-DD HH:mm:ss KST] — [세션명]

### 세션 정보

- 작성 주체: [Codex 세션/기타]
- 세션 ID: [확인 가능한 ID/확인 불가]
- 작업 디렉터리: `[절대 경로]`
- Git 브랜치: `[브랜치]`
- 기준 커밋: `[짧은 해시와 제목]`

### 1. 세션 목표

- [사용자 요청과 최종 목표]

제외 범위:

- [이번 세션에서 하지 않는 작업/없음]

### 2. 시작 시점 상태

- [브랜치, 커밋, 기존 변경, 이전 세션 인계 상태]

### 3. 핵심 결정

- [결정, 이유, 사용자 확인 여부]

검토 후 채택하지 않은 방식:

- [대안과 미채택 이유/없음]

### 4. 수행 내용

- [실제로 조사·작성·수정한 핵심 내용]

### 5. 변경 파일

- `[경로]`
  - [변경 내용과 역할]

### 6. 검증 결과

- `[명령 또는 검사]`: [성공/실패/미실행과 근거]
- 실환경 검증: [결과/실환경 검증 필요/해당 없음]

### 7. 실패 및 미확인 사항

- [실패, 오류 원인, 미확인 사항, 사용자 결정 필요 사항/없음]

### 8. 현재 상태

- [항목]: [완료/부분 완료/미완료/차단됨/실환경 검증 필요]

### 9. 다음 세션 실행 순서

1. [첫 번째 작업]
2. [후속 작업]

완료 판단 기준:

- [검증 가능한 완료 조건]

### 10. 위험 및 주의사항

- [데이터, 보안, 호환성, 외부 환경, 회귀 위험/없음]

### 11. Git 및 변경 경계

- 이번 세션 변경: [파일 목록/없음]
- 기존 사용자 변경: [파일 목록/없음]
- 커밋: [해시/수행하지 않음]
- 푸시: [대상/수행하지 않음]
- 자동 커밋·푸시 금지: [유지/사용자 승인으로 해제]

### 12. 이전 기록 정정

[정정 내용/없음]
```

## 2026-07-30 12:05:00 KST — 설정 UI 컨트롤 표시 보강

### 작업 목적

- 업체/사업팀 드롭다운과 활성 체크박스가 화면에서 보이지 않는 문제를 재현하고 수정.

### 변경 파일

- `src/outsource_mail_collector/ui/settings_dialog.py`
- `tests/test_settings_dialog.py`

### 변경 내용

- 활성 셀 위젯에 `활성` 텍스트와 최소 폭을 지정.
- 업체/사업팀 콤보에 최소 폭을 지정.
- 설정 테이블의 열 폭과 행 높이를 명시해 임베디드 컨트롤이 잘리지 않도록 보강.

### 검증

- 회귀 테스트: `167 passed`
- `compileall`: 통과
- `git diff --check`: 통과
- Outlook/Excel 실제 연동 및 사용자의 실제 GUI 조작: 실행하지 않음.

### 현재 상태

- 수정 사항은 아직 커밋하지 않음.
- 기존 미추적 사용자 파일 `.superpowers/`, `AGENTS.md`, `CLAUDE.md`는 유지.

## 2026-07-30 12:27:32 KST — 설정 추가 버튼 실제 클릭 경로 수정

### 세션 목표

- 사용자 제공 화면에서 새 업체 행의 활성 체크박스와 새 수주 행의 업체·사업팀 드롭다운 및 활성 체크박스가 생성되지 않는 문제를 실제 GUI 기준으로 수정.

### 원인과 결정

- `QPushButton.clicked(bool)`를 `add_employee_row(employee=None)`, `add_vendor_row(vendor=None)`, `add_work_order_row(mapping=None)`에 직접 연결해 클릭 시 `False`가 엔티티 객체 인수로 전달됨.
- 새 행 삽입 직후 각각 `False.employee_id`, `False.vendor_id`, `False.mapping_id` 접근에서 예외가 발생해 내장 위젯 설치 전에 함수가 중단됨.
- 크기나 스타일 문제가 아니므로, 세 추가 버튼의 신호 연결에서 `bool` 인수를 버리고 인수 없이 행 추가 메서드를 호출하도록 수정.

### 변경 파일

- `src/outsource_mail_collector/ui/settings_dialog.py`
  - 담당자·업체·수주 추가 버튼의 `clicked(bool)` 인수를 차단.
- `tests/test_settings_dialog.py`
  - 메서드 직접 호출이 아니라 실제 추가 버튼을 클릭해 각 행의 내장 위젯 생성을 확인하는 회귀 테스트 추가.
- `docs/2026-07-30-ui-bugs-and-change-list.md`
  - 실제 GUI에서 확인한 업체 드롭다운, 활성 체크박스, 사업팀 드롭다운 항목과 작업 기록 갱신.

### 검증

- RED: 새 회귀 테스트에서 세 버튼 모두 `AttributeError`를 재현하고 내장 위젯 부재로 실패.
- GREEN: 대상 테스트 `1 passed`.
- 설정 화면 테스트: `19 passed`.
- 전체 테스트: `168 passed in 86.67s`.
- `python -m compileall -q src tests`: 통과.
- `git diff --check`: 통과(LF→CRLF 안내만 출력).
- 실제 사용자 데스크톱 GUI:
  - 새 업체 행의 기본 체크된 `활성` 체크박스 확인.
  - 새 수주 행의 업체·사업팀 드롭다운 화살표와 기본 체크된 `활성` 체크박스 확인.
  - 업체 드롭다운에서 저장된 활성 업체 `SH 오토메이션` 확인.
  - 사업팀 드롭다운에서 허용값 10개 전체 확인.
  - 검증용 미완성 행은 Cancel로 폐기하여 DB에 저장하지 않음.

### 현재 상태와 경계

- 애플리케이션 재실행 완료: 가상환경 런처 PID `65060`, 실제 GUI PID `29836`, 응답 정상.
- 실제 Outlook·Excel 연동은 실행하지 않음.
- 이번 수정은 이 기록과 함께 커밋하며, 최종 해시는 Git 로그와 완료 보고에서 확인.
- 푸시는 수행하지 않음.
- 기존 미추적 사용자 파일 `.superpowers/`, `AGENTS.md`, `CLAUDE.md`는 유지.
