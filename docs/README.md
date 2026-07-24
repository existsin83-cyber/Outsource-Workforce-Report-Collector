# 업무보고 메일 자동 추출·Excel 취합 프로젝트 문서

포함 문서:

1. `PRD.md` — 제품 요구사항
2. `TRD.md` — 기술 요구사항과 구현 설계
3. `SYSTEM_ARCHITECTURE.md` — 시스템 구조와 데이터 흐름
4. `prompt.md` — 바이브 코딩용 마스터 프롬프트
5. `rules.md` — 개발·보안·추출·테스트 규칙

## 현재 확정된 환경

- Microsoft Office Professional Plus 2019
- Outlook 2019 MSO 64비트
- Windows PC
- 메일 위치: 받은편지함
- 담당자: 약 20명
- 메일: 하루 약 20통
- 제목 형식: 통일되지 않음

## 권장 1차 개발

Outlook 연결 PoC를 먼저 수행한다.

1. Outlook COM 연결
2. 선택 날짜의 메일 목록 조회
3. 제목·발신자·수신일·EntryID·본문 읽기
4. 메일 상태를 변경하지 않는지 검증
5. 실제 회사 PC 보안 환경에서 접근 가능 여부 확인

PoC 성공 후 실제 메일 샘플을 기반으로 추출기를 개발한다.
