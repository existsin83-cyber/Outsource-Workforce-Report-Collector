"""Excel 어댑터 인터페이스.

TODO: 실 취합 워크북을 아직 확보하지 못했다 (딥인터뷰 확인 사항). PRD/TRD가 적어둔
컬럼명·시트명(`외주인원_원본`)을 임시 스펙으로 가정해 인터페이스를 설계했으며,
실 파일 확보 시 시트 구조/병합 셀/수식 배치를 재검증해야 한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from outsource_mail_collector.domain.models import OutsourceWorkRecord


class ExcelAdapter(Protocol):
    def backup(self, workbook_path: Path) -> Path:
        """쓰기 전 반드시 타임스탬프 백업본을 만든다. 백업 경로를 반환."""
        ...

    def ensure_sheet(self, workbook_path: Path, sheet_name: str, headers: list[str]) -> None:
        """시트가 없으면 생성, 있으면 헤더를 이름 기준으로 검증한다 (셀 주소 하드코딩 금지)."""
        ...

    def append_rows(
        self, workbook_path: Path, sheet_name: str, rows: list[OutsourceWorkRecord]
    ) -> int:
        """승인된 레코드만 행 단위로 추가한다. 기존 수식/서식/병합 셀을 보존한다."""
        ...

    def save(self, workbook_path: Path) -> None:
        """저장을 확정한다. 실패 시 호출부에서 DB를 '완료' 처리하면 안 된다."""
        ...
