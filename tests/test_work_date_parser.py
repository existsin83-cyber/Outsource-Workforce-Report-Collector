from datetime import date, datetime

import pytest

from fixtures import (
    DATE_BODY_CONFLICTING,
    DATE_BODY_MATCHING,
    DATE_SUBJECT_DOTTED,
    DATE_SUBJECT_KOREAN,
    DATE_SUBJECT_UNDERSCORE,
)
from outsource_mail_collector.domain.work_report import (
    WorkDateSource,
    WorkReportIssueCode,
)
from outsource_mail_collector.parsing.work_date_parser import resolve_work_date


@pytest.mark.parametrize(
    "subject",
    [DATE_SUBJECT_UNDERSCORE, DATE_SUBJECT_DOTTED, DATE_SUBJECT_KOREAN],
)
def test_subject_date_formats_are_authoritative(subject: str) -> None:
    result = resolve_work_date(
        subject,
        DATE_BODY_MATCHING,
        datetime(2026, 7, 30, 8, 0),
    )

    assert result.candidate_date == date(2026, 7, 29)
    assert result.subject_date == date(2026, 7, 29)
    assert result.source is WorkDateSource.SUBJECT
    assert result.requires_review is False


def test_conflicting_body_date_keeps_subject_and_warns() -> None:
    result = resolve_work_date(
        DATE_SUBJECT_DOTTED,
        DATE_BODY_CONFLICTING,
        datetime(2026, 7, 30, 8, 0),
    )

    assert result.candidate_date == date(2026, 7, 29)
    assert result.body_date == date(2026, 7, 28)
    assert result.requires_review is True
    assert WorkReportIssueCode.DATE_MISMATCH.value in result.issue_codes


def test_next_day_received_timestamp_does_not_override_subject() -> None:
    result = resolve_work_date(
        DATE_SUBJECT_DOTTED,
        DATE_BODY_MATCHING,
        datetime(2026, 7, 30, 8, 0),
    )

    assert result.candidate_date == date(2026, 7, 29)
    assert WorkReportIssueCode.DATE_MISMATCH.value not in result.issue_codes


def test_body_date_without_subject_is_review_required_candidate() -> None:
    result = resolve_work_date(
        "일일 업무보고",
        DATE_BODY_MATCHING,
        datetime(2026, 7, 30, 8, 0),
    )

    assert result.candidate_date == date(2026, 7, 29)
    assert result.source is WorkDateSource.BODY
    assert result.requires_review is True
    assert WorkReportIssueCode.DATE_SUBJECT_MISSING.value in result.issue_codes


def test_compact_yymmdd_subject_without_separators_is_authoritative() -> None:
    result = resolve_work_date(
        "전장기술팀 일일 업무 보고의 건_260804",
        "금일 작업 내용을 보고합니다.",
        datetime(2026, 8, 4, 17, 9),
    )

    assert result.candidate_date == date(2026, 8, 4)
    assert result.source is WorkDateSource.SUBJECT


def test_compact_yymmdd_does_not_match_inside_tracking_no() -> None:
    result = resolve_work_date(
        "일일 업무보고",
        "SK260303~9 외주 인원 : 6명",
        datetime(2026, 7, 30, 8, 0),
    )

    assert result.candidate_date is None
    assert result.source is WorkDateSource.UNRESOLVED


def test_missing_subject_and_body_date_is_not_inferred_from_received_at() -> None:
    result = resolve_work_date(
        "일일 업무보고",
        "금일 작업 내용을 보고합니다.",
        datetime(2026, 7, 30, 8, 0),
    )

    assert result.candidate_date is None
    assert result.source is WorkDateSource.UNRESOLVED
    assert result.requires_review is True
    assert result.issue_codes == (WorkReportIssueCode.DATE_UNRESOLVED.value,)
