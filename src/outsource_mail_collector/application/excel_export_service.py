"""Excel export orchestration contract.

The UI intentionally does not call this service until a real workbook is available.
"""

from __future__ import annotations

from pathlib import Path

from outsource_mail_collector.application.errors import (
    ExcelIntegrationUnavailableError,
    InvalidReviewValueError,
)
from outsource_mail_collector.domain.models import OutsourceWorkRecord, ReviewStatus
from outsource_mail_collector.infrastructure.db.repository import (
    SQLiteRepository,
    StoredReviewRecord,
)
from outsource_mail_collector.infrastructure.excel_adapter import ExcelAdapter


_EXPORT_HEADERS = [
    "보고일",
    "작성자",
    "장비명",
    "Tracking No.",
    "외주업체명",
    "실제 인원",
    "당일 공수",
    "누적 공수",
]


class ExcelExportService:
    def __init__(
        self,
        repository: SQLiteRepository,
        excel_adapter: ExcelAdapter | None,
    ) -> None:
        self._repository = repository
        self._excel = excel_adapter

    def export(
        self,
        workbook_path: Path,
        sheet_name: str,
        record_ids: list[int],
    ) -> int:
        """Export reviewed records only, backing up before the first write."""

        if self._excel is None:
            raise ExcelIntegrationUnavailableError(
                "실제 Excel 연동은 아직 준비되지 않았습니다."
            )
        records = [self._repository.get_review_record(row_id) for row_id in record_ids]
        if any(record.review_status is not ReviewStatus.REVIEWED for record in records):
            raise InvalidReviewValueError("검토 완료된 항목만 Excel에 반영할 수 있습니다.")
        rows = [_to_domain_record(record) for record in records]
        self._excel.backup(workbook_path)
        self._excel.ensure_sheet(workbook_path, sheet_name, _EXPORT_HEADERS)
        appended = self._excel.append_rows(workbook_path, sheet_name, rows)
        self._excel.save(workbook_path)
        return appended


def _to_domain_record(stored: StoredReviewRecord) -> OutsourceWorkRecord:
    return OutsourceWorkRecord(
        work_record_id=stored.work_record_id,
        equipment_record_id=stored.equipment_record_id or "",
        vendor_name=stored.vendor_name,
        actual_headcount=stored.actual_headcount,
        day_headcount=stored.day_headcount,
        night_headcount=stored.night_headcount,
        per_person_man_day=stored.per_person_man_day,
        day_man_day=stored.day_man_day,
        night_man_day=stored.night_man_day,
        daily_man_day=stored.daily_man_day,
        cumulative_man_day=stored.cumulative_man_day,
        note=stored.note,
        confidence=stored.confidence,
        review_status=stored.review_status,
    )
