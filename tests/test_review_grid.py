from datetime import date
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QToolButton

from outsource_mail_collector.application.models import WorkReportRow
from outsource_mail_collector.domain.models import ReviewStatus
from outsource_mail_collector.domain.work_report import (
    RowSource,
    WorkReportIssueCode,
)
from outsource_mail_collector.ui.review_grid import ReviewGridWidget


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_review_grid_shows_compilation_columns_and_problem_styling():
    _app()
    rows = [
        _row(1),
        _row(
            2,
            issue_codes=(WorkReportIssueCode.DAILY_MISMATCH,),
            warning_confirmed=False,
        ),
        _row(3, included=False, review_status=ReviewStatus.EXCLUDED),
    ]
    grid = ReviewGridWidget(rows)

    assert grid.rowCount() == 3
    assert [
        grid.horizontalHeaderItem(index).text()
        for index in range(grid.columnCount())
    ][1:16] == [
        "작업일",
        "거래처명",
        "Tracking No.",
        "장비명",
        "사업팀",
        "실제 작업인원",
        "인당 공수",
        "메일 투입",
        "계산 투입",
        "확정 투입",
        "메일 누적",
        "계산 누적",
        "확정 누적",
        "검증 상태",
        "포함",
    ]
    assert grid.item(1, 1).background().color().name() == "#fff3e0"
    assert grid.item(2, 1).font().strikeOut()


def test_manual_row_has_no_original_mail_action():
    _app()
    grid = ReviewGridWidget(
        [
            _row(1, source_type=RowSource.MAIL, mail_entry_id="ENTRY-1"),
            _row(2, source_type=RowSource.MANUAL, mail_entry_id=None),
        ]
    )

    mail_actions = grid.cellWidget(0, 16).findChildren(QToolButton)
    manual_actions = grid.cellWidget(1, 16).findChildren(QToolButton)

    assert any(button.text() == "원본" for button in mail_actions)
    assert all(button.text() != "원본" for button in manual_actions)


def test_review_grid_retains_row_ids_for_selected_rows():
    _app()
    grid = ReviewGridWidget([_row(101)])
    grid.item(0, 0).setCheckState(Qt.CheckState.Checked)

    assert grid.checked_row_ids() == [101]


def _row(
    row_id: int,
    *,
    source_type: RowSource = RowSource.MAIL,
    mail_entry_id: str | None = "ENTRY-1",
    issue_codes: tuple[WorkReportIssueCode, ...] = (),
    warning_confirmed: bool = True,
    included: bool = True,
    review_status: ReviewStatus = ReviewStatus.NORMAL,
) -> WorkReportRow:
    return WorkReportRow(
        row_id=row_id,
        source_type=source_type,
        extracted_record_id=row_id if source_type is RowSource.MAIL else None,
        mail_entry_id=mail_entry_id,
        work_date=date(2026, 7, 29),
        work_date_confirmed=True,
        vendor_name="업체A",
        tracking_no="AB260101",
        equipment_name="장비 1",
        business_team="WA",
        actual_headcount=2,
        per_person_man_day=Decimal("1.5"),
        reported_daily_man_day=Decimal("3.0"),
        calculated_daily_man_day=Decimal("3.0"),
        confirmed_daily_man_day=Decimal("3.0"),
        reported_cumulative_man_day=Decimal("12.0"),
        calculated_cumulative_man_day=Decimal("12.0"),
        confirmed_cumulative_man_day=Decimal("12.0"),
        cumulative_series_key="업체a|T:AB260101",
        issue_codes=issue_codes,
        review_status=review_status,
        included=included,
        warning_confirmed=warning_confirmed,
        resolution_note=None,
    )
