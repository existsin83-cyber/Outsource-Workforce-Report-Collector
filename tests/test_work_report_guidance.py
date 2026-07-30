from enum import Enum

from outsource_mail_collector.domain.work_report import WorkReportIssueCode
from outsource_mail_collector.ui.review_grid import _COLUMNS
from outsource_mail_collector.ui.work_report_guidance import (
    COLUMN_HELP,
    issue_action,
    issue_detail,
    issue_title,
)


def test_guidance_covers_every_review_grid_column():
    visible_columns = [column for column in _COLUMNS if column]

    assert set(visible_columns) <= COLUMN_HELP.keys()
    assert all(COLUMN_HELP[column] for column in visible_columns)


def test_man_day_column_help_distinguishes_reported_calculated_and_confirmed():
    assert "메일 본문" in COLUMN_HELP["메일 투입"]
    assert "자동 계산" in COLUMN_HELP["계산 투입"]
    assert "Excel" in COLUMN_HELP["확정 투입"]
    assert "이전 확정 누적" in COLUMN_HELP["계산 누적"]
    assert all("전송됩니다" not in text for text in COLUMN_HELP.values())


def test_issue_guidance_covers_every_current_code():
    for code in WorkReportIssueCode:
        assert issue_title(code) != code.value
        assert issue_detail(code) != code.value
        assert issue_action(code) != code.value


def test_issue_guidance_explains_registration_fix():
    code = WorkReportIssueCode.WORK_ORDER_UNREGISTERED

    assert "수주 미등록" in issue_title(code)
    assert "설정" in issue_action(code)


def test_future_unmapped_issue_code_falls_back_to_enum_value():
    class FutureIssueCode(str, Enum):
        NEW_CODE = "NEW_CODE"

    code = FutureIssueCode.NEW_CODE

    assert issue_title(code) == code.value
    assert issue_detail(code) == code.value
    assert issue_action(code) == code.value
