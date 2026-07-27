# Outsource Mail Collector

Outlook에 도착하는 외주 업무보고 메일을 수집·파싱해 검토 후 Excel 취합표에 반영하는
Windows 데스크톱 도구. 상세 요구사항은 `docs/PRD.md`, `docs/TRD.md`,
`docs/SYSTEM_ARCHITECTURE.md`, `docs/rules.md` 참고.

## 현재 상태

Outlook 받은편지함과 하위 폴더를 읽기 전용으로 조회하고, 등록 담당자의 업무보고를
규칙 기반으로 추출해 리뷰 그리드에서 검토할 수 있다. 직원·업체·Outlook 폴더와
Excel 대상 정보는 설정 화면에서 관리한다.

실제 Excel 쓰기는 아직 연결되지 않았다. `Excel 반영` 버튼은 활성 상태이지만
클릭하면 준비 중 안내를 표시하며 파일을 변경하지 않는다.

## 개발 환경 준비

```powershell
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## 실행

```powershell
.\.venv\Scripts\python.exe -m outsource_mail_collector.app
```

첫 실행 시 `%LOCALAPPDATA%\OutsourceMailCollector\collector.db`가 생성된다.

1. `⚙ 설정`에서 담당자 이름·이메일을 등록한다.
2. 업체 표준명과 메일에 등장하는 별칭을 등록한다.
3. `폴더 새로고침`으로 Outlook의 실제 받은편지함 하위 폴더를 불러와 선택한다.
4. 메인 화면에서 날짜와 폴더를 선택하고 `메일 가져오기`를 누른다.
5. 추출 결과를 수정하거나 `검토 완료`, `반영 제외`로 처리한다.

Outlook 접근은 읽기 전용이다. 앱은 메일 삭제·이동, 읽음 상태 변경, 회신 또는
전달을 수행하지 않는다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Outlook COM PoC

`samples/*.msg` (git에는 포함되지 않음, 로컬에만 존재)를 Outlook COM으로 직접 열어
필드를 덤프하는 스크립트:

```powershell
python tools/outlook_poc.py
```
