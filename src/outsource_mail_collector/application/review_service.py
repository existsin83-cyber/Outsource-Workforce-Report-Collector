"""Application service for validated review edits and status transitions."""

from __future__ import annotations

from outsource_mail_collector.application.errors import InvalidReviewValueError
from outsource_mail_collector.application.models import (
    ReviewRecord,
    review_record_from_stored,
)
from datetime import date
from outsource_mail_collector.domain.models import ReviewStatus
from outsource_mail_collector.infrastructure.db.repository import (
    SQLiteRepository,
    StoredReviewRecord,
)
from outsource_mail_collector.infrastructure.outlook_adapter import OutlookAdapter


_TEXT_FIELDS = {"equipment_name", "tracking_no", "vendor_name"}
_NUMERIC_FIELDS = {"actual_headcount", "daily_man_day", "cumulative_man_day"}
_ALLOWED_STATUSES = {ReviewStatus.REVIEWED, ReviewStatus.EXCLUDED}


class ReviewService:
    def __init__(
        self, repository: SQLiteRepository, outlook_adapter: OutlookAdapter
    ) -> None:
        self._repository = repository
        self._outlook = outlook_adapter

    def update_field(
        self, record_id: int, field_name: str, raw_value: str
    ) -> StoredReviewRecord:
        """Validate a grid edit and persist it with an audit log."""

        if field_name not in _TEXT_FIELDS | _NUMERIC_FIELDS:
            raise InvalidReviewValueError(f"수정할 수 없는 필드입니다: {field_name}")
        value = self._convert_value(field_name, raw_value)
        return self._repository.update_review_field(
            record_id,
            field_name,
            value,
            action="REVIEW_FIELD_UPDATED",
        )

    def set_status(
        self, record_ids: list[int], status: ReviewStatus
    ) -> list[StoredReviewRecord]:
        """Apply an allowed user review status to selected records."""

        if status not in _ALLOWED_STATUSES:
            raise InvalidReviewValueError("검토 완료 또는 반영 제외 상태만 선택할 수 있습니다.")
        return self._repository.set_review_status(
            record_ids,
            status,
            action="REVIEW_STATUS_CHANGED",
        )

    def open_original(self, mail_entry_id: str) -> None:
        """Open the original message through Outlook without changing its state."""

        self._outlook.display_message(mail_entry_id)

    def list_records(self, report_date: date) -> list[ReviewRecord]:
        return [
            review_record_from_stored(row)
            for row in self._repository.list_review_records(report_date)
        ]

    @staticmethod
    def _convert_value(field_name: str, raw_value: str) -> str | float | None:
        stripped = raw_value.strip()
        if not stripped:
            return None
        if field_name in _TEXT_FIELDS:
            return stripped
        try:
            return float(stripped)
        except ValueError as exc:
            raise InvalidReviewValueError("숫자 형식으로 입력해 주세요.") from exc
