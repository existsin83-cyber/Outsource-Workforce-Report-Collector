import pytest

from outsource_mail_collector.domain.models import ReviewStatus
from outsource_mail_collector.parsing.mail_normalizer import normalize
from outsource_mail_collector.parsing.outsource_extractor import extract_work_records
from outsource_mail_collector.parsing.section_parser import split_sections
from outsource_mail_collector.parsing.validation_engine import validate
from fixtures import (
    CUMULATIVE_MAN_DAY_VARIANTS,
    FORMAT_A_CATEGORY_DOT,
    FORMAT_B_NUMBERED_VENDOR_PER_UNIT,
    FORMAT_C_INLINE_ALL_IN_ONE_LINE,
    FORMAT_D_INLINE_REPORTED_DAILY,
    TOTAL_AND_DAILY_MAN_DAY,
    TOTAL_INPUT_MAN_DAY,
)
from outsource_mail_collector.domain.models import EquipmentSection
from outsource_mail_collector.domain.work_report import man_day_basis
from outsource_mail_collector.parsing.outsource_extractor import AMBIGUOUS_NOTE_PREFIX


def _sections_for(body: str):
    normalized = normalize(body)
    return split_sections("test-mail-id", normalized.lines)


def test_date_line_is_not_treated_as_numbered_section_header():
    sections = split_sections(
        "test-mail-id",
        ["7.24 금요일 일일 업무보고 드립니다.", "1. 장비A", "외주 인원 : 1명"],
    )

    assert len(sections) == 1
    assert sections[0].equipment_name == "장비A"
    assert "7.24 금요일" not in sections[0].section_text


@pytest.mark.parametrize(
    "date_line",
    ["7.24(금) 업무보고", "7.24 금 업무보고", "7.24 (금) 일일 업무보고"],
)
def test_common_parenthesized_weekday_date_lines_are_not_headers(date_line: str):
    sections = split_sections(
        "test-mail-id", [date_line, "1. 장비A", "외주 인원 : 1명"]
    )

    assert len(sections) == 1
    assert sections[0].equipment_name == "장비A"


def test_extract_work_records_preserves_existing_tracking_no_when_text_has_none():
    section = EquipmentSection(
        section_index=0,
        mail_id="test-mail-id",
        tracking_no="KEEP-ME",
        section_text="외주 인원 : 1명",
    )

    extract_work_records(section)
    first_tracking_no = section.tracking_no
    extract_work_records(section)

    assert first_tracking_no == "KEEP-ME"
    assert section.tracking_no == "KEEP-ME"


def test_format_a_category_dot_no_vendor_ambiguous_total():
    sections = _sections_for(FORMAT_A_CATEGORY_DOT)
    assert len(sections) == 3

    records_by_section = [extract_work_records(s) for s in sections]

    # 첫 섹션(고객사A)은 외주 인원 언급이 없음 -> 레코드 없음 (정상적인 "외주 없음")
    assert records_by_section[0] == []

    # 두 번째 섹션(고객사B): 외주 인원 1명, 야근 1명, 총공수는 라벨이 모호해 값을 채우지 않음
    record = records_by_section[1][0]
    assert record.vendor_name is None
    assert record.actual_headcount == 1.0
    assert record.night_headcount == 1.0
    assert record.daily_man_day is None
    assert record.cumulative_man_day is None
    assert record.note is not None and "총 공수 43.5" in record.note

    result = validate(sections[1], record)
    assert result.status == ReviewStatus.NUMBER_UNPARSABLE
    assert "당일/누적 여부가 불명확한 공수 값 존재" in result.issues


def test_format_b_vendor_header_per_unit_records():
    sections = _sections_for(FORMAT_B_NUMBERED_VENDOR_PER_UNIT)
    assert len(sections) == 2

    section = sections[0]
    assert section.tracking_no is None  # split_sections 단계에서는 아직 미추출
    records = extract_work_records(section)
    extracted_tracking_no = section.tracking_no  # extract_work_records 가 채워줌
    assert extracted_tracking_no is not None and "MK260307" in extracted_tracking_no

    assert len(records) == 2  # #7호기, #8호기
    unit7, unit8 = records
    assert unit7.vendor_name == "협력사A"
    assert unit7.cumulative_man_day == 18.5
    assert unit7.day_headcount is None  # #7호기 줄엔 주간/야간이 없음

    assert unit8.vendor_name == "협력사A"
    assert unit8.day_headcount == 4.0
    assert unit8.night_headcount == 0.0
    # FORMAT_B reports shift counts separately; do not infer a total actual
    # headcount or a per-person basis from them.
    assert unit8.actual_headcount is None
    assert unit8.cumulative_man_day == 9.0
    assert man_day_basis(unit8.actual_headcount, unit8.night_headcount) == "확인 필요"

    result = validate(section, unit8)
    # 벤더/장비/수주번호는 모두 확인됐고, 당일 공수만 없이 누적만 존재
    assert result.status == ReviewStatus.CUMULATIVE_ONLY


def test_confidence_and_split_confidence_are_bounded():
    with pytest.raises(ValueError):
        EquipmentSection(
            section_index=0,
            mail_id="mail",
            section_text="text",
            split_confidence=1.1,
        )
    with pytest.raises(ValueError):
        from outsource_mail_collector.domain.models import OutsourceWorkRecord

        OutsourceWorkRecord(
            work_record_id="record",
            equipment_record_id="equipment",
            confidence=-0.1,
        )


def test_format_c_inline_headcount_no_manday_at_all():
    sections = _sections_for(FORMAT_C_INLINE_ALL_IN_ONE_LINE)
    assert len(sections) == 2

    records0 = extract_work_records(sections[0])
    assert len(records0) == 1
    record = records0[0]
    assert sections[0].tracking_no == "ZZ260203~260207, ZZ260403"
    assert record.actual_headcount == 6.0
    assert record.night_headcount == 6.0
    assert record.daily_man_day is None
    assert record.cumulative_man_day is None

    result = validate(sections[0], record)
    assert result.status == ReviewStatus.DAILY_MAN_DAY_MISSING

    # 두 번째 섹션은 외주 언급 자체가 없음 -> 레코드 없음
    assert extract_work_records(sections[1]) == []


def test_format_d_extracts_tracking_equipment_night_and_reported_daily():
    sections = _sections_for(FORMAT_D_INLINE_REPORTED_DAILY)
    assert len(sections) == 2

    first = extract_work_records(sections[0])[0]
    second = extract_work_records(sections[1])[0]

    assert sections[0].tracking_no == "AA260101"
    assert sections[0].equipment_name == "고객사H 장비Alpha #1"
    assert first.actual_headcount == 1.0
    assert first.night_headcount == 1.0
    assert first.daily_man_day == 1.5

    assert sections[1].tracking_no == "BB260202"
    assert sections[1].equipment_name == "고객사I 장비Beta #2"
    assert second.actual_headcount == 3.0
    assert second.night_headcount == 1.0
    assert second.daily_man_day == 3.5


@pytest.mark.parametrize("cumulative_text, expected", CUMULATIVE_MAN_DAY_VARIANTS)
def test_vendor_style_accepts_cumulative_man_day_with_optional_unit(
    cumulative_text: str, expected: float
):
    section = EquipmentSection(
        section_index=0,
        mail_id="test-mail-id",
        section_text=f"외주 인원 - 협력사\n{cumulative_text}",
    )

    record = extract_work_records(section)[0]

    assert record.cumulative_man_day == expected


def test_total_input_man_day_is_ambiguous_not_daily():
    section = EquipmentSection(
        section_index=0,
        mail_id="test-mail-id",
        section_text=TOTAL_INPUT_MAN_DAY,
    )

    record = extract_work_records(section)[0]

    assert record.daily_man_day is None
    assert record.note == f"{AMBIGUOUS_NOTE_PREFIX} 총 투입 공수 100"


def test_total_input_man_day_does_not_hide_later_daily_man_day():
    section = EquipmentSection(
        section_index=0,
        mail_id="test-mail-id",
        section_text=TOTAL_AND_DAILY_MAN_DAY,
    )

    record = extract_work_records(section)[0]

    assert record.daily_man_day == 2.0
    assert record.note == f"{AMBIGUOUS_NOTE_PREFIX} 총  투입 공수 100"


@pytest.mark.parametrize(
    "body",
    [
        FORMAT_A_CATEGORY_DOT,
        FORMAT_B_NUMBERED_VENDOR_PER_UNIT,
        FORMAT_C_INLINE_ALL_IN_ONE_LINE,
    ],
    ids=["format_a", "format_b", "format_c"],
)
def test_every_fixture_parses_without_error(body: str):
    sections = _sections_for(body)
    assert sections
    for section in sections:
        records = extract_work_records(section)
        for record in records:
            validate(section, record)  # 예외 없이 검증까지 끝나야 함
