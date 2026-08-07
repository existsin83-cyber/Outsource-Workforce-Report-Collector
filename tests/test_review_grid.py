from dataclasses import replace
from datetime import date
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from outsource_mail_collector.application.models import WorkReportRow
from outsource_mail_collector.domain.models import ReviewStatus
from outsource_mail_collector.domain.work_report import (
    RowSource,
    WorkReportIssueCode,
)
from outsource_mail_collector.ui.review_grid import (
    _COLUMNS,
    ReviewGridWidget,
    _review_status_text,
)
from outsource_mail_collector.ui.work_report_guidance import (
    COLUMN_HELP,
    issue_action,
    issue_detail,
    issue_title,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _col(name: str) -> int:
    return _COLUMNS.index(name)


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
    ][1:] == [
        "No.",
        "확정",
        "작업일",
        "담당자",
        "거래처명",
        "Tracking No.",
        "장비명",
        "사업팀",
        "실제 작업인원",
        "야근 인원",
        "인당 공수",
        "메일 투입",
        "계산 투입",
        "확정 투입",
        "메일 누적",
        "검증 상태",
    ]
    assert grid.item(0, _col("인당 공수")).text() == "혼합"
    assert grid.item(1, 1).background().color().name() == "#fff3e0"
    assert grid.item(1, 1).foreground().color().name() == "#4a1f00"
    assert (
        grid.item(1, _col("검증 상태")).foreground().color().name() == "#4a1f00"
    )
    assert grid.item(1, 0).background().color().name() == "#fff3e0"
    assert grid.item(1, _col("확정")).background().color().name() == "#e65100"
    assert grid.item(0, 0).background().color().name() != "#fff3e0"
    assert grid.item(2, 1).font().strikeOut()


def test_confirmed_warning_row_uses_readable_default_cell_colours():
    _app()
    grid = ReviewGridWidget(
        [
            _row(
                1,
                issue_codes=(WorkReportIssueCode.DAILY_MISMATCH,),
                warning_confirmed=True,
            )
        ]
    )

    for column in (0, _col("작업일")):
        item = grid.item(0, column)
        assert item.background().color().name() == "#f5f5f5"
        assert item.foreground().color().name() == "#1a1a1a"


def test_confirmed_row_is_light_green_and_cannot_be_selected_again():
    _app()
    grid = ReviewGridWidget(
        [_row(1, confirmed_daily=Decimal("3.0")), _row(2)]
    )

    for column in (0, _col("작업일")):
        assert grid.item(0, column).background().color().name() == "#e8f5e9"
        assert grid.item(0, column).foreground().color().name() == "#1b5e20"
        assert grid.item(1, column).background().color().name() == "#f5f5f5"

    assert not (
        grid.item(0, 0).flags() & Qt.ItemFlag.ItemIsUserCheckable
    )
    grid.set_all_checked(True)
    assert grid.checked_row_ids() == [2]
    assert grid.horizontalHeaderItem(0).text() == "☑"


def test_confirm_column_shows_a_distinct_badge_for_confirmed_and_button_for_unconfirmed():
    _app()
    grid = ReviewGridWidget(
        [_row(1, confirmed_daily=Decimal("3.0")), _row(2)]
    )

    confirmed_item = grid.item(0, _col("확정"))
    unconfirmed_item = grid.item(1, _col("확정"))
    assert confirmed_item.text() == "확정"
    assert confirmed_item.font().bold()
    assert confirmed_item.background().color().name() == "#2e7d32"
    assert confirmed_item.foreground().color().name() == "#ffffff"
    assert unconfirmed_item.text() == "미확정"
    assert unconfirmed_item.font().bold()
    assert unconfirmed_item.background().color().name() == "#e65100"
    assert unconfirmed_item.foreground().color().name() == "#ffffff"


def test_clicking_unconfirmed_cell_emits_confirm_requested_with_row_id():
    _app()
    grid = ReviewGridWidget([_row(101), _row(102)])
    requested: list[int] = []
    grid.confirm_requested.connect(requested.append)

    grid.cellClicked.emit(1, _col("확정"))

    assert requested == [102]


def test_clicking_already_confirmed_cell_does_not_emit_confirm_requested():
    _app()
    grid = ReviewGridWidget([_row(101, confirmed_daily=Decimal("3.0"))])
    requested: list[int] = []
    grid.confirm_requested.connect(requested.append)

    grid.cellClicked.emit(0, _col("확정"))

    assert requested == []


def test_confirmed_row_keeps_green_even_when_it_still_carries_an_issue():
    _app()
    grid = ReviewGridWidget(
        [
            _row(
                1,
                confirmed_daily=Decimal("3.0"),
                issue_codes=(WorkReportIssueCode.DAILY_MISMATCH,),
                warning_confirmed=False,
            )
        ]
    )

    assert grid.item(0, 1).background().color().name() == "#e8f5e9"


def test_review_grid_retains_row_ids_for_selected_rows():
    _app()
    grid = ReviewGridWidget([_row(101)])
    grid.item(0, 0).setCheckState(Qt.CheckState.Checked)

    assert grid.checked_row_ids() == [101]


def test_header_checkbox_selects_and_clears_every_row():
    _app()
    grid = ReviewGridWidget([_row(101), _row(102)])

    assert grid.horizontalHeaderItem(0).text() == "☐"

    grid._header_clicked(0)
    assert grid.checked_row_ids() == [101, 102]
    assert grid.horizontalHeaderItem(0).text() == "☑"

    grid._header_clicked(0)
    assert grid.checked_row_ids() == []
    assert grid.horizontalHeaderItem(0).text() == "☐"

    grid.item(0, 0).setCheckState(Qt.CheckState.Checked)
    assert grid.horizontalHeaderItem(0).text() == "☐"
    grid.item(1, 0).setCheckState(Qt.CheckState.Checked)
    assert grid.horizontalHeaderItem(0).text() == "☑"


def test_clicking_a_column_header_toggles_ascending_and_descending_sort():
    _app()
    row_b = replace(_row(101), vendor_name="업체B")
    row_a = replace(_row(102), vendor_name="업체A")
    grid = ReviewGridWidget([row_b, row_a])
    vendor_column = _col("거래처명")

    grid._header_clicked(vendor_column)
    assert [
        grid.item(row, vendor_column).text() for row in range(grid.rowCount())
    ] == ["업체A", "업체B"]

    grid._header_clicked(vendor_column)
    assert [
        grid.item(row, vendor_column).text() for row in range(grid.rowCount())
    ] == ["업체B", "업체A"]


def test_sorting_preserves_checked_row_selection():
    _app()
    row_b = replace(_row(101), vendor_name="업체B")
    row_a = replace(_row(102), vendor_name="업체A")
    grid = ReviewGridWidget([row_b, row_a])
    grid.item(0, 0).setCheckState(Qt.CheckState.Checked)

    grid._header_clicked(_col("거래처명"))

    assert grid.checked_row_ids() == [101]


def test_cumulative_columns_are_not_shown_on_the_main_grid():
    _app()
    grid = ReviewGridWidget([_row(101)])

    headers = {
        grid.horizontalHeaderItem(index).text()
        for index in range(grid.columnCount())
    }
    assert "계산 누적" not in headers
    assert "확정 누적" not in headers


def test_review_grid_adds_column_and_value_tooltips():
    _app()
    grid = ReviewGridWidget([_row(101)])

    assert all(
        grid.horizontalHeaderItem(index).toolTip()
        for index in range(grid.columnCount())
    )
    assert "자동 계산" in grid.horizontalHeaderItem(_col("계산 투입")).toolTip()
    assert "메일" in grid.horizontalHeaderItem(_col("메일 누적")).toolTip()
    assert "업체A" in grid.item(0, _col("거래처명")).toolTip()
    assert "3.0" in grid.item(0, _col("계산 투입")).toolTip()
    assert COLUMN_HELP["거래처명"] in grid.item(0, _col("거래처명")).toolTip()
    assert all(
        grid.item(0, column).toolTip()
        for column in range(1, grid.columnCount())
    )


def test_validation_status_without_issues_uses_readable_korean_status():
    _app()
    grid = ReviewGridWidget([_row(101, review_status=ReviewStatus.REVIEWED)])

    status = grid.item(0, _col("검증 상태"))
    assert status.text() == "검토 완료"
    assert "ReviewStatus.REVIEWED" not in status.text()
    assert _review_status_text(ReviewStatus.REVIEWED) == "검토 완료"


def test_validation_status_uses_korean_issue_guidance():
    _app()
    issue = WorkReportIssueCode.WORK_ORDER_UNREGISTERED
    grid = ReviewGridWidget([_row(101, issue_codes=(issue,), warning_confirmed=False)])

    status = grid.item(0, _col("검증 상태"))
    assert status.text() == issue_title(issue)
    assert issue_title(issue) in status.toolTip()
    assert issue_detail(issue) in status.toolTip()
    assert issue_action(issue) in status.toolTip()
    assert "수주 미등록" in status.toolTip()
    assert "설정" in status.toolTip()


def test_initial_screen_hides_cumulative_baseline_issues():
    _app()
    grid = ReviewGridWidget(
        [
            _row(
                101,
                issue_codes=(WorkReportIssueCode.CUMULATIVE_BASELINE_REQUIRED,),
                warning_confirmed=False,
                review_status=ReviewStatus.REVIEWED,
            )
        ]
    )

    status = grid.item(0, _col("검증 상태"))
    assert status.text() == "검토 완료"
    assert "이전 누적" not in status.toolTip()


def test_review_grid_double_click_emits_review_requested_with_row_id():
    _app()
    grid = ReviewGridWidget([_row(101), _row(102)])
    requested: list[int] = []
    grid.review_requested.connect(requested.append)

    grid.cellDoubleClicked.emit(1, 2)

    assert requested == [102]


def test_review_grid_current_row_id_returns_cursor_row_id():
    _app()
    grid = ReviewGridWidget([_row(101), _row(102)])

    assert grid.current_row_id() is None

    grid.setCurrentCell(1, 3)
    assert grid.current_row_id() == 102


def _row(
    row_id: int,
    *,
    source_type: RowSource = RowSource.MAIL,
    mail_entry_id: str | None = "ENTRY-1",
    issue_codes: tuple[WorkReportIssueCode, ...] = (),
    warning_confirmed: bool = True,
    included: bool = True,
    review_status: ReviewStatus = ReviewStatus.NORMAL,
    confirmed_daily: Decimal | None = None,
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
        night_headcount=1,
        per_person_man_day=Decimal("1.5"),
        reported_daily_man_day=Decimal("3.0"),
        calculated_daily_man_day=Decimal("3.0"),
        confirmed_daily_man_day=confirmed_daily,
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
