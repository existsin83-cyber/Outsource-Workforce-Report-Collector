"""docs/PRD.md 상태 어휘에 따라 OutsourceWorkRecord 를 검증한다.

우선순위대로 첫 번째로 걸리는 문제를 대표 상태로 삼는다 (docs/rules.md 검증 규칙).
"""

from __future__ import annotations

from outsource_mail_collector.domain.models import (
    EquipmentSection,
    OutsourceWorkRecord,
    ReviewStatus,
    ValidationResult,
)
from outsource_mail_collector.parsing.outsource_extractor import AMBIGUOUS_NOTE_PREFIX


def validate(section: EquipmentSection, record: OutsourceWorkRecord) -> ValidationResult:
    issues: list[str] = []
    status = ReviewStatus.NORMAL

    def flag(issue: str, review_status: ReviewStatus) -> None:
        nonlocal status
        issues.append(issue)
        if status is ReviewStatus.NORMAL:
            status = review_status

    if section.equipment_name is None:
        flag("장비명 없음", ReviewStatus.EQUIPMENT_UNCONFIRMED)
    if section.tracking_no is None:
        flag("Tracking No./수주번호 없음", ReviewStatus.TRACKING_NO_UNCONFIRMED)
    if record.vendor_name is None:
        flag("업체명 없음", ReviewStatus.VENDOR_UNCONFIRMED)
    if (
        record.actual_headcount is None
        and record.day_headcount is None
        and record.night_headcount is None
    ):
        flag("실제 투입 인원 미기재", ReviewStatus.HEADCOUNT_MISSING)
    if record.note and record.note.startswith(AMBIGUOUS_NOTE_PREFIX):
        flag("당일/누적 여부가 불명확한 공수 값 존재", ReviewStatus.NUMBER_UNPARSABLE)
    if record.daily_man_day is None and record.cumulative_man_day is not None:
        flag("누적 공수만 존재, 당일 공수 없음", ReviewStatus.CUMULATIVE_ONLY)
    elif record.daily_man_day is None and record.cumulative_man_day is None:
        flag("당일/누적 공수 모두 없음", ReviewStatus.DAILY_MAN_DAY_MISSING)

    if not issues:
        record.review_status = ReviewStatus.NORMAL
    else:
        record.review_status = status

    return ValidationResult(
        work_record_id=record.work_record_id,
        is_valid=status is ReviewStatus.NORMAL,
        issues=issues,
        status=status,
    )
