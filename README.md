# Outsource Mail Collector

Outlook에 도착하는 외주 업무보고 메일을 수집·파싱해 검토 후 Excel 취합표에 반영하는
Windows 데스크톱 도구. 상세 요구사항은 `docs/PRD.md`, `docs/TRD.md`,
`docs/SYSTEM_ARCHITECTURE.md`, `docs/rules.md` 참고.

## 현재 상태

스켈레톤 단계. 도메인 모델, 어댑터 인터페이스, SQLite 스키마, 빈 실행 창만 있고
실제 Outlook 조회/Excel 쓰기 로직은 아직 없음.

## 개발 환경 준비

```powershell
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## 실행

```powershell
python -m outsource_mail_collector.app
```

## 테스트

```powershell
pytest
```

## Outlook COM PoC

`samples/*.msg` (git에는 포함되지 않음, 로컬에만 존재)를 Outlook COM으로 직접 열어
필드를 덤프하는 스크립트:

```powershell
python tools/outlook_poc.py
```
