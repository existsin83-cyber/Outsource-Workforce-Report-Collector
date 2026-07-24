import pytest

from outsource_mail_collector.domain.models import ReviewStatus
from outsource_mail_collector.parsing.mail_normalizer import normalize
from outsource_mail_collector.parsing.outsource_extractor import extract_work_records
from outsource_mail_collector.parsing.section_parser import split_sections
from outsource_mail_collector.parsing.validation_engine import validate
from fixtures import (
    FORMAT_A_CATEGORY_DOT,
    FORMAT_B_NUMBERED_VENDOR_PER_UNIT,
    FORMAT_C_INLINE_ALL_IN_ONE_LINE,
)


def _sections_for(body: str):
    normalized = normalize(body)
    return split_sections("test-mail-id", normalized.lines)


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
    assert result.status == ReviewStatus.VENDOR_UNCONFIRMED  # 벤더 없음이 먼저 걸림
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
    assert unit8.cumulative_man_day == 9.0

    result = validate(section, unit8)
    # 벤더/장비/수주번호는 모두 확인됐고, 당일 공수만 없이 누적만 존재
    assert result.status == ReviewStatus.CUMULATIVE_ONLY


def test_format_c_inline_headcount_no_manday_at_all():
    sections = _sections_for(FORMAT_C_INLINE_ALL_IN_ONE_LINE)
    assert len(sections) == 2

    records0 = extract_work_records(sections[0])
    assert len(records0) == 1
    record = records0[0]
    assert record.actual_headcount == 6.0
    assert record.night_headcount == 6.0
    assert record.daily_man_day is None
    assert record.cumulative_man_day is None

    result = validate(sections[0], record)
    assert result.status == ReviewStatus.VENDOR_UNCONFIRMED

    # 두 번째 섹션은 외주 언급 자체가 없음 -> 레코드 없음
    assert extract_work_records(sections[1]) == []


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
