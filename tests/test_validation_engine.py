"""Focused status-priority tests for parser validation."""

import pytest

from outsource_mail_collector.domain.models import (
    EquipmentSection,
    OutsourceWorkRecord,
    ReviewStatus,
)
from outsource_mail_collector.parsing.outsource_extractor import AMBIGUOUS_NOTE_PREFIX
from outsource_mail_collector.parsing.validation_engine import validate


def _section() -> EquipmentSection:
    return EquipmentSection(
        section_index=0,
        mail_id="mail-id",
        tracking_no="AA260101",
        equipment_name="Equipment A",
        section_text="source",
    )


def _record(**changes: object) -> OutsourceWorkRecord:
    values: dict[str, object] = {
        "work_record_id": "record-id",
        "equipment_record_id": "equipment-id",
        "vendor_name": None,
        "actual_headcount": 1.0,
        "daily_man_day": 1.0,
    }
    values.update(changes)
    return OutsourceWorkRecord(**values)


@pytest.mark.parametrize(
    ("record", "expected_status", "expected_issue_count"),
    [
        (
            _record(note=f"{AMBIGUOUS_NOTE_PREFIX} total input man-day 10"),
            ReviewStatus.NUMBER_UNPARSABLE,
            2,
        ),
        (
            _record(actual_headcount=None, daily_man_day=None),
            ReviewStatus.HEADCOUNT_MISSING,
            3,
        ),
        (
            _record(daily_man_day=None, cumulative_man_day=2.0),
            ReviewStatus.CUMULATIVE_ONLY,
            2,
        ),
        (
            _record(daily_man_day=None),
            ReviewStatus.DAILY_MAN_DAY_MISSING,
            2,
        ),
    ],
    ids=["ambiguous", "headcount", "cumulative_only", "daily_missing"],
)
def test_vendor_missing_is_lower_priority_than_data_quality_issues(
    record: OutsourceWorkRecord,
    expected_status: ReviewStatus,
    expected_issue_count: int,
) -> None:
    result = validate(_section(), record)

    assert result.status is expected_status
    assert record.review_status is expected_status
    assert len(result.issues) == expected_issue_count


def test_vendor_headcount_and_ambiguous_issues_are_all_retained() -> None:
    result = validate(
        _section(),
        _record(
            actual_headcount=None,
            note=f"{AMBIGUOUS_NOTE_PREFIX} total input man-day 10",
        ),
    )

    assert result.status is ReviewStatus.HEADCOUNT_MISSING
    assert result.issues == [
        "업체명 없음",
        "실제 투입 인원 미기재",
        "당일/누적 여부가 불명확한 공수 값 존재",
    ]


@pytest.mark.parametrize(
    ("section", "expected_status", "expected_issues"),
    [
        (
            EquipmentSection(
                section_index=0,
                mail_id="mail-id",
                section_text="source",
            ),
            ReviewStatus.EQUIPMENT_UNCONFIRMED,
            [
                "장비명 없음",
                "Tracking No./수주번호 없음",
                "업체명 없음",
                "실제 투입 인원 미기재",
                "당일/누적 공수 모두 없음",
            ],
        ),
        (
            EquipmentSection(
                section_index=0,
                mail_id="mail-id",
                equipment_name="Equipment A",
                section_text="source",
            ),
            ReviewStatus.TRACKING_NO_UNCONFIRMED,
            [
                "Tracking No./수주번호 없음",
                "업체명 없음",
                "실제 투입 인원 미기재",
                "당일/누적 공수 모두 없음",
            ],
        ),
    ],
    ids=["equipment_before_all_lower_statuses", "tracking_before_all_lower_statuses"],
)
def test_equipment_and_tracking_statuses_keep_their_full_priority_order(
    section: EquipmentSection,
    expected_status: ReviewStatus,
    expected_issues: list[str],
) -> None:
    result = validate(section, _record(actual_headcount=None, daily_man_day=None))

    assert result.status is expected_status
    assert result.issues == expected_issues


@pytest.mark.parametrize(
    ("section", "record", "expected_status", "expected_issues"),
    [
        (
            EquipmentSection(
                section_index=0,
                mail_id="mail-id",
                tracking_no="AA260101",
                section_text="source",
            ),
            _record(note=f"{AMBIGUOUS_NOTE_PREFIX} total input man-day 10"),
            ReviewStatus.EQUIPMENT_UNCONFIRMED,
            [
                "장비명 없음",
                "업체명 없음",
                "당일/누적 여부가 불명확한 공수 값 존재",
            ],
        ),
        (
            EquipmentSection(
                section_index=0,
                mail_id="mail-id",
                equipment_name="Equipment A",
                section_text="source",
            ),
            _record(daily_man_day=None, cumulative_man_day=2.0),
            ReviewStatus.TRACKING_NO_UNCONFIRMED,
            [
                "Tracking No./수주번호 없음",
                "업체명 없음",
                "누적 공수만 존재, 당일 공수 없음",
            ],
        ),
    ],
    ids=["equipment_before_ambiguous_number", "tracking_before_cumulative_only"],
)
def test_equipment_and_tracking_precede_number_and_cumulative_statuses(
    section: EquipmentSection,
    record: OutsourceWorkRecord,
    expected_status: ReviewStatus,
    expected_issues: list[str],
) -> None:
    result = validate(section, record)

    assert result.status is expected_status
    assert result.issues == expected_issues
