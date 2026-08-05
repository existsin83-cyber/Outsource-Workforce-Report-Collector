from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QMenu,
)

import outsource_mail_collector.ui.row_review_flow as row_review_flow_module
import outsource_mail_collector.ui.tracking_dashboard_dialog as dialog_module
from outsource_mail_collector.application.models import (
    FinalizationBlocker,
    FinalReportPreview,
    TrackingDashboardSummary,
    WorkReportRow,
)
from outsource_mail_collector.domain.models import ReviewStatus
from outsource_mail_collector.domain.work_report import (
    RowSource,
    WorkReportIssueCode,
)
from outsource_mail_collector.ui.tracking_dashboard_dialog import (
    BaselineDialog,
    CompletedTrackingDialog,
    TrackingDashboardDialog,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_dashboard_renders_summary_drill_down_and_blocking_guidance():
    _app()
    dashboard_service = _DashboardService(
        summaries=(
            _summary(
                blockers=(
                    FinalizationBlocker(
                        7,
                        "CUMULATIVE_MISMATCH",
                        "메일 누적과 계산 누적을 확인해 주세요.",
                    ),
                )
            ),
        ),
        details=(_row(7), _row(8, work_date=date(2026, 7, 30))),
    )
    dialog = TrackingDashboardDialog(
        dashboard_service,
        _WorkReportService(),
        lambda: None,
    )

    assert dialog.summary_table.rowCount() == 1
    summary_headers = [
        dialog.summary_table.horizontalHeaderItem(column).text()
        for column in range(dialog.summary_table.columnCount())
    ]
    assert summary_headers == [
        "행 번호",
        "Tracking No.",
        "최근 작업일",
        "거래처명",
        "장비명",
        "사업팀",
        "최근 실제 인원",
        "최근 야근 인원",
        "인당 공수",
        "최근 확정 투입",
        "초기 누적",
        "메일 누적",
        "계산 누적",
        "확정 누적",
        "검증 상태",
    ]
    assert dialog.summary_table.item(0, 0).text() == "1"
    assert (
        dialog.summary_table.item(0, dialog_module._TRACKING_COLUMN).text()
        == "AB260101"
    )
    assert (
        dialog.summary_table.item(0, dialog_module._STATUS_COLUMN).text()
        == "확인 필요"
    )
    # 클릭 전에는 아무 강조도 없이 차단(blocker) 배경색만 보인다. 하단 상세표는
    # 그래도 첫 Tracking No. 기준으로 미리 채워져 있어야 한다.
    assert not dialog.summary_table.selectionModel().hasSelection()
    assert (
        dialog.summary_table.item(0, dialog_module._TRACKING_COLUMN)
        .background()
        .color()
        == QColor("#ffebee")
    )
    assert dashboard_service.drill_down_calls == ["AB260101"]
    assert dialog.detail_table.rowCount() == 2
    detail_headers = [
        dialog.detail_table.horizontalHeaderItem(column).text()
        for column in range(dialog.detail_table.columnCount())
    ]
    assert "야근 인원" in detail_headers
    assert "메일 누적" in detail_headers
    assert "계산 누적" not in detail_headers
    assert "확정 누적" not in detail_headers
    assert "포함" in detail_headers
    assert "문제 및 조치" in detail_headers
    assert "메일 누적과 계산 누적" in dialog.guidance_label.text()

    dialog.summary_table.selectRow(0)

    # 실제로 클릭(선택)한 뒤에는 파란 강조가 차단(빨간) 배경을 덮어써야 한다.
    # 클릭 전 표시용 기본 조회와 클릭에 의한 조회가 합쳐져 같은 Tracking No.가
    # 두 번 조회된다.
    assert dialog.summary_table.selectionModel().hasSelection()
    assert (
        dialog.summary_table.item(0, dialog_module._TRACKING_COLUMN)
        .background()
        .color()
        == QColor("#1565c0")
    )
    assert dashboard_service.drill_down_calls == ["AB260101", "AB260101"]


def test_unregistered_summary_register_button_passes_summary_and_refreshes_views():
    """Dropping the success refresh path must leave dashboard and preview stale."""
    _app()
    summary = _summary(
        blockers=(
            FinalizationBlocker(7, "WORK_ORDER_UNREGISTERED", "수주 마스터 등록 필요"),
        )
    )
    dashboard_service = _DashboardService(summaries=(summary,), details=(_row(7),))
    requested: list[TrackingDashboardSummary] = []
    refreshed: list[bool] = []
    preview_calls: list[bool] = []
    preview = FinalReportPreview(None, None, tuple(), tuple())
    dialog = TrackingDashboardDialog(
        dashboard_service,
        _WorkReportService(),
        lambda: refreshed.append(True),
        final_preview=preview,
        preview_supplier=lambda: (preview_calls.append(True) or preview),
        work_order_registration_callback=lambda value: requested.append(value) or True,
    )

    button = dialog.summary_table.cellWidget(0, dialog_module._STATUS_COLUMN)
    assert button is not None
    assert "background:#b71c1c" in button.styleSheet()
    assert "color:white" in button.styleSheet()
    assert button.text() == "수주 등록 이동"
    button.click()

    assert requested == [summary]
    assert dashboard_service.summary_calls == 2
    assert preview_calls == [True]
    assert refreshed == [True]


def test_successful_registration_refresh_removes_stale_status_button():
    """Keeping the old cell widget would offer registration after its blocker is resolved."""
    _app()
    unregistered = _summary(
        blockers=(
            FinalizationBlocker(7, "WORK_ORDER_UNREGISTERED", "수주 마스터 등록 필요"),
        )
    )
    resolved = _summary()
    dashboard_service = _DashboardService(
        summaries=(unregistered,), details=(_row(7),)
    )
    dialog = TrackingDashboardDialog(
        dashboard_service,
        _WorkReportService(),
        lambda: None,
        work_order_registration_callback=lambda _: True,
    )

    dashboard_service._summaries = (resolved,)
    dialog.summary_table.cellWidget(0, dialog_module._STATUS_COLUMN).click()

    assert dialog.summary_table.item(0, dialog_module._STATUS_COLUMN).text() == "확정 가능"
    assert dialog.summary_table.cellWidget(0, dialog_module._STATUS_COLUMN) is None


def test_successful_registration_refreshes_selected_detail_and_guidance():
    """Relying on an unchanged selection signal leaves the resolved detail view stale."""
    _app()
    unregistered = _summary(
        blockers=(
            FinalizationBlocker(7, "WORK_ORDER_UNREGISTERED", "수주 마스터 등록 필요"),
        )
    )
    initial_detail = _row(7)
    resolved_detail = replace(
        initial_detail,
        actual_headcount=4,
        issue_codes=(),
        review_status=ReviewStatus.REVIEWED,
        warning_confirmed=True,
    )
    dashboard_service = _DashboardService(
        summaries=(unregistered,), details=(initial_detail,)
    )
    dialog = TrackingDashboardDialog(
        dashboard_service,
        _WorkReportService(),
        lambda: None,
        work_order_registration_callback=lambda _: True,
    )

    assert dialog.detail_table.item(0, 2).text() == "3"
    assert "수주 마스터 등록 필요" in dialog.guidance_label.text()
    dashboard_service._summaries = (_summary(),)
    dashboard_service._details = (resolved_detail,)
    dialog.summary_table.cellWidget(0, dialog_module._STATUS_COLUMN).click()

    assert dialog.detail_table.item(0, 2).text() == "4"
    assert dialog.detail_table.item(0, 10).text() == "검토 완료"
    assert dialog.detail_table.item(0, 11).text() == ""
    assert dialog.guidance_label.text() == "현재 최종 표를 차단하는 문제가 없습니다."


def test_dashboard_registration_button_ignores_nonmatching_blockers_and_cancelled_callback():
    """Refreshing after cancellation or exposing unrelated blockers would change data without registration."""
    _app()
    unmatched = _summary(
        blockers=(FinalizationBlocker(7, "CUMULATIVE_MISMATCH", "누적 확인 필요"),)
    )
    dialog = TrackingDashboardDialog(
        _DashboardService(summaries=(unmatched,), details=(_row(7),)),
        _WorkReportService(),
        lambda: None,
        work_order_registration_callback=lambda _: True,
    )
    assert dialog.summary_table.cellWidget(0, dialog_module._STATUS_COLUMN) is None

    cancelled_summary = _summary(
        blockers=(
            FinalizationBlocker(7, "WORK_ORDER_UNREGISTERED", "수주 마스터 등록 필요"),
        )
    )
    dashboard_service = _DashboardService(
        summaries=(cancelled_summary,), details=(_row(7),)
    )
    refreshed: list[bool] = []
    dialog = TrackingDashboardDialog(
        dashboard_service,
        _WorkReportService(),
        lambda: refreshed.append(True),
        work_order_registration_callback=lambda _: False,
    )
    dialog.summary_table.cellWidget(0, dialog_module._STATUS_COLUMN).click()

    assert dashboard_service.summary_calls == 1
    assert refreshed == []


def test_dashboard_tables_copy_selected_cells_as_tsv_and_ignore_empty_selection():
    """Removing the table copy handler must leave the clipboard unchanged."""
    _app()
    dialog = TrackingDashboardDialog(
        _DashboardService(summaries=(_summary(),), details=(_row(7),)),
        _WorkReportService(),
        lambda: None,
    )
    table = dialog.summary_table
    tracking_col = dialog_module._TRACKING_COLUMN
    date_col = tracking_col + 1
    table.clearSelection()
    table.selectionModel().select(
        table.model().index(0, tracking_col),
        table.selectionModel().SelectionFlag.Select,
    )
    table.selectionModel().select(
        table.model().index(0, date_col),
        table.selectionModel().SelectionFlag.Select,
    )
    table.setFocus()
    QApplication.clipboard().setText("")

    QTest.keyClick(table, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)

    assert QApplication.clipboard().text() == "AB260101\t2026-07-30"
    table.clearSelection()
    QApplication.clipboard().setText("unchanged")
    QTest.keyClick(table, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QApplication.clipboard().text() == "unchanged"
    dialog.close()


def test_dashboard_table_context_menu_copies_selected_cells_as_tsv():
    """Removing the viewport context-menu route must make the Copy action unavailable."""
    _app()
    dialog = TrackingDashboardDialog(
        _DashboardService(summaries=(_summary(),), details=(_row(7),)),
        _WorkReportService(),
        lambda: None,
    )
    dialog.show()
    table = dialog.summary_table
    tracking_col = dialog_module._TRACKING_COLUMN
    date_col = tracking_col + 1
    _select_cells(table, ((0, tracking_col), (0, date_col)))
    QApplication.clipboard().setText("")

    QTest.mouseClick(
        table.viewport(),
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
        table.visualItemRect(table.item(0, tracking_col)).center(),
    )
    QApplication.processEvents()

    menu = QApplication.activePopupWidget()
    assert isinstance(menu, QMenu)
    copy_action = next(action for action in menu.actions() if action.text() == "복사")
    QTest.mouseClick(
        menu,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        menu.actionGeometry(copy_action).center(),
    )
    assert QApplication.clipboard().text() == "AB260101\t2026-07-30"
    dialog.close()
    QApplication.processEvents()


def test_dashboard_detail_table_copies_multirow_cells_with_blank_tsv_positions():
    """Copying only selected cells must retain blank positions inside their bounding TSV area."""
    _app()
    dialog = TrackingDashboardDialog(
        _DashboardService(
            summaries=(_summary(),),
            details=(_row(701), _row(902, work_date=date(2026, 7, 30))),
        ),
        _WorkReportService(),
        lambda: None,
    )
    dialog.summary_table.selectRow(0)
    table = dialog.detail_table
    _select_cells(table, ((0, 0), (0, 2), (1, 0), (1, 2)))
    table.setFocus()
    QApplication.clipboard().setText("")

    QTest.keyClick(table, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)

    assert QApplication.clipboard().text() == "1\t\t3\n2\t\t3"
    dialog.close()


def test_dashboard_tables_use_extended_selection_with_row_summary_and_cell_detail():
    """Changing either table's selection behavior must fail this contract."""
    _app()
    dialog = TrackingDashboardDialog(
        _DashboardService(summaries=(_summary(),), details=(_row(7),)),
        _WorkReportService(),
        lambda: None,
    )

    assert (
        dialog.summary_table.selectionBehavior()
        == QAbstractItemView.SelectionBehavior.SelectRows
    )
    assert (
        dialog.detail_table.selectionBehavior()
        == QAbstractItemView.SelectionBehavior.SelectItems
    )
    for table in (dialog.summary_table, dialog.detail_table):
        assert table.selectionMode() == QAbstractItemView.SelectionMode.ExtendedSelection
    dialog.close()


def test_dashboard_details_use_display_row_numbers_without_exposing_row_ids():
    """Replacing display positions with persistent row IDs must fail this audit-safe view."""
    _app()
    dialog = TrackingDashboardDialog(
        _DashboardService(
            summaries=(_summary(),),
            details=(_row(701), _row(902, work_date=date(2026, 7, 30))),
        ),
        _WorkReportService(),
        lambda: None,
    )

    dialog.summary_table.selectRow(0)

    assert dialog.detail_table.horizontalHeaderItem(0).text() == "행 번호"
    assert [dialog.detail_table.item(row, 0).text() for row in range(2)] == [
        "1",
        "2",
    ]
    dialog.close()


def test_detail_row_double_click_opens_edit_flow_and_refreshes(monkeypatch):
    _app()
    dashboard_service = _DashboardService(
        summaries=(_summary(),),
        details=(_row(7),),
    )
    work_report_service = _WorkReportService()
    refresh_calls = []
    dialog = TrackingDashboardDialog(
        dashboard_service,
        work_report_service,
        lambda: refresh_calls.append(True),
    )
    dialog.summary_table.selectRow(0)
    opened_rows = []

    class FakeProblemDialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, **kwargs):
            opened_rows.append(kwargs)

        def exec(self):
            return QDialog.DialogCode.Accepted

        def values(self):
            return {
                "confirmed_daily_man_day": Decimal("3.5"),
                "resolution_note": "대시보드에서 확인",
            }

    monkeypatch.setattr(
        row_review_flow_module, "ProblemReviewDialog", FakeProblemDialog
    )

    dialog.detail_table.cellDoubleClicked.emit(0, 0)

    assert opened_rows
    assert work_report_service.confirm_calls == [
        (7, Decimal("3.5"), "대시보드에서 확인")
    ]
    assert dashboard_service.summary_calls >= 2
    assert refresh_calls


def test_detail_row_edit_button_uses_current_row_selection(monkeypatch):
    _app()
    dashboard_service = _DashboardService(
        summaries=(_summary(),),
        details=(_row(7), _row(8, work_date=date(2026, 7, 30))),
    )
    work_report_service = _WorkReportService()
    dialog = TrackingDashboardDialog(
        dashboard_service, work_report_service, lambda: None
    )
    dialog.summary_table.selectRow(0)
    dialog.detail_table.setCurrentCell(1, 0)

    class FakeProblemDialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, **kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def values(self):
            return {
                "confirmed_daily_man_day": Decimal("3.5"),
                "resolution_note": "확인",
            }

    monkeypatch.setattr(
        row_review_flow_module, "ProblemReviewDialog", FakeProblemDialog
    )

    dialog.edit_button.click()

    assert work_report_service.confirm_calls[0][0] == 8


def test_unified_edit_button_targets_whichever_table_was_selected_last():
    """상단/하단 표 선택에 따라 통합 버튼의 동작 대상이 바뀌지 않으면 이 계약이 깨진다."""
    _app()
    dashboard_service = _DashboardService(
        summaries=(_summary("AB260101"), _summary("CD260202")),
        details=(_row(7), _row(8, work_date=date(2026, 7, 30))),
    )
    dialog = TrackingDashboardDialog(
        dashboard_service,
        _WorkReportService(),
        lambda: None,
    )
    opened: list[str] = []

    class FakeBaselineDialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, tracking_no, **_kwargs):
            opened.append(tracking_no)

        def exec(self):
            return QDialog.DialogCode.Rejected

    dialog_module.BaselineDialog, original = (
        FakeBaselineDialog,
        dialog_module.BaselineDialog,
    )
    try:
        # 상단 표를 선택하면 통합 버튼이 초기 누적 수정으로 동작한다.
        dialog.summary_table.selectRow(1)
        assert "CD260202" in dialog.edit_button.text()
        dialog.edit_button.click()
        assert opened == ["CD260202"]

        # 하단 표를 선택하면 같은 버튼이 행 수정으로 동작 대상이 바뀐다.
        dialog.detail_table.setCurrentCell(1, 0)
        assert "2행" in dialog.edit_button.text()
        assert "2026-07-30" in dialog.edit_button.text()
    finally:
        dialog_module.BaselineDialog = original
    dialog.close()


def test_edit_button_shows_guidance_when_nothing_is_selected(monkeypatch):
    """아무 것도 선택하지 않았을 때 클릭하면 조용히 실패하지 않고 안내가 떠야 한다."""
    _app()
    dialog = TrackingDashboardDialog(
        _DashboardService(summaries=(_summary(),), details=(_row(7),)),
        _WorkReportService(),
        lambda: None,
    )
    assert "선택해 주세요" in dialog.edit_button.text()
    shown = []
    monkeypatch.setattr(
        dialog_module.QMessageBox,
        "information",
        lambda *args, **kwargs: shown.append(args),
    )

    dialog.edit_button.click()

    assert shown
    dialog.close()


def test_selected_detail_row_is_highlighted_and_named_on_the_edit_button():
    """선택 행 표시가 사라지면 어떤 행을 수정하는지 알 수 없다."""
    _app()
    dialog = TrackingDashboardDialog(
        _DashboardService(
            summaries=(_summary(),),
            details=(_row(7), _row(8, work_date=date(2026, 7, 30))),
        ),
        _WorkReportService(),
        lambda: None,
    )
    dialog.summary_table.selectRow(0)

    dialog.detail_table.setCurrentCell(1, 0)

    assert (
        dialog.detail_table.item(1, 0).background().color() == QColor("#1565c0")
    )
    assert dialog.detail_table.item(1, 0).font().bold()
    assert (
        dialog.detail_table.item(0, 0).background().color()
        != QColor("#1565c0")
    )
    assert not dialog.detail_table.item(0, 0).font().bold()
    assert "2행" in dialog.edit_button.text()
    assert "2026-07-30" in dialog.edit_button.text()
    dialog.close()


def test_duplicate_unresolved_detail_row_shows_guidance_instead_of_dialog(
    monkeypatch,
):
    _app()
    dashboard_service = _DashboardService(
        summaries=(_summary(),),
        details=(
            _row(7, issue_codes=(WorkReportIssueCode.DUPLICATE_UNRESOLVED,)),
        ),
    )
    work_report_service = _WorkReportService()
    dialog = TrackingDashboardDialog(
        dashboard_service, work_report_service, lambda: None
    )
    dialog.summary_table.selectRow(0)
    shown = []
    monkeypatch.setattr(
        dialog_module.QMessageBox,
        "information",
        lambda *args, **kwargs: shown.append(args),
    )

    def _fail(**_kwargs):
        raise AssertionError("duplicate rows must not open the edit dialog")

    monkeypatch.setattr(row_review_flow_module, "ProblemReviewDialog", _fail)

    dialog.detail_table.cellDoubleClicked.emit(0, 0)

    assert shown
    assert work_report_service.confirm_calls == []


def test_dashboard_sorts_work_dates_by_default_and_from_date_buttons():
    """Dropping date keys or the button handlers must break the visible ordering."""
    _app()
    dialog = TrackingDashboardDialog(
        _DashboardService(
            summaries=(
                _summary("ZZ260730", date(2026, 7, 30)),
                _summary("NO_DATE", None),
                _summary("AA260730", date(2026, 7, 30)),
                _summary("MID260801", date(2026, 8, 1)),
            ),
            details=(_row(7),),
        ),
        _WorkReportService(),
        lambda: None,
    )

    assert _visible_tracking_nos(dialog) == [
        "MID260801",
        "AA260730",
        "ZZ260730",
        "NO_DATE",
    ]
    dialog.sort_ascending_button.click()
    assert _visible_tracking_nos(dialog) == [
        "AA260730",
        "ZZ260730",
        "MID260801",
        "NO_DATE",
    ]
    dialog.sort_descending_button.click()
    assert _visible_tracking_nos(dialog) == [
        "MID260801",
        "AA260730",
        "ZZ260730",
        "NO_DATE",
    ]
    dialog.close()


def test_baseline_dialog_defaults_and_prefills_saved_values():
    _app()
    first = BaselineDialog(
        "AB260101",
        earliest_work_date=date(2026, 7, 29),
        baseline=None,
    )
    assert first.effective_date_edit.date() == QDate(2026, 7, 28)
    assert first.cumulative_edit.text() == "0.0"

    saved = SimpleNamespace(
        effective_through_date=date(2026, 7, 27),
        cumulative_man_day=Decimal("20.5"),
    )
    existing = BaselineDialog(
        "AB260101",
        earliest_work_date=date(2026, 7, 29),
        baseline=saved,
    )

    assert existing.effective_date_edit.date() == QDate(2026, 7, 27)
    assert existing.cumulative_edit.text() == "20.5"


def test_baseline_save_calls_service_and_refreshes_dashboard_and_main(
    monkeypatch,
):
    _app()
    work_service = _WorkReportService()
    refreshes: list[str] = []
    dialog = TrackingDashboardDialog(
        _DashboardService(
            summaries=(_summary(),),
            details=(_row(7),),
        ),
        work_service,
        lambda: refreshes.append("main"),
    )

    class FakeBaselineDialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, tracking_no, earliest_work_date, baseline, parent=None):
            assert tracking_no == "AB260101"
            assert earliest_work_date == date(2026, 7, 29)
            assert baseline is None

        def exec(self):
            return QDialog.DialogCode.Accepted

        def values(self):
            return {
                "effective_through_date": date(2026, 7, 28),
                "cumulative_man_day": Decimal("20.0"),
                "resolution_note": "초기 자료 확인",
            }

    monkeypatch.setattr(dialog_module, "BaselineDialog", FakeBaselineDialog)

    dialog.summary_table.selectRow(0)
    dialog._edit_baseline()

    assert work_service.saved == [
        {
            "tracking_no": "AB260101",
            "effective_through_date": date(2026, 7, 28),
            "cumulative_man_day": Decimal("20.0"),
            "resolution_note": "초기 자료 확인",
        }
    ]
    assert refreshes == ["main"]
    assert dialog.summary_table.rowCount() == 1


def test_initial_cumulative_cell_double_click_opens_baseline_editor(monkeypatch):
    """Only the 초기 누적 cell may open the baseline editor from the summary table."""
    _app()
    dialog = TrackingDashboardDialog(
        _DashboardService(summaries=(_summary(),), details=(_row(7),)),
        _WorkReportService(),
        lambda: None,
    )
    opened: list[str] = []

    class FakeBaselineDialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, tracking_no, **_kwargs):
            opened.append(tracking_no)

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(dialog_module, "BaselineDialog", FakeBaselineDialog)
    dialog.summary_table.selectRow(0)

    dialog.summary_table.cellDoubleClicked.emit(0, 0)
    assert opened == []

    dialog.summary_table.cellDoubleClicked.emit(
        0, dialog_module._INITIAL_CUMULATIVE_COLUMN
    )
    assert opened == ["AB260101"]
    dialog.close()


def test_confirmed_cumulative_cell_double_click_opens_confirm_dialog_and_saves(
    monkeypatch,
):
    """확정 누적 셀만 확정 누적 확인 창을 열고, 값을 서비스로 넘겨야 한다."""
    _app()
    work_report_service = _WorkReportService()
    dialog = TrackingDashboardDialog(
        _DashboardService(summaries=(_summary(),), details=(_row(7),)),
        work_report_service,
        lambda: None,
    )
    dialog.summary_table.selectRow(0)

    class FakeCumulativeConfirmDialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, tracking_no, **_kwargs):
            self.tracking_no = tracking_no

        def exec(self):
            return QDialog.DialogCode.Accepted

        def values(self):
            return {
                "confirmed_cumulative_man_day": Decimal("13.0"),
                "resolution_note": "메일값 채택",
            }

    monkeypatch.setattr(
        dialog_module, "CumulativeConfirmDialog", FakeCumulativeConfirmDialog
    )

    dialog.summary_table.cellDoubleClicked.emit(
        0, dialog_module._CONFIRMED_CUMULATIVE_COLUMN
    )

    assert work_report_service.confirm_series_cumulative_calls == [
        ("AB260101", Decimal("13.0"), "메일값 채택")
    ]
    dialog.close()


def test_baseline_values_require_reason_and_one_decimal():
    _app()
    dialog = BaselineDialog(
        "AB260101",
        earliest_work_date=date(2026, 7, 29),
        baseline=None,
    )
    dialog.cumulative_edit.setText("20.25")
    dialog.reason_edit.setText("")

    try:
        dialog.values()
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("invalid baseline should be rejected")

    assert "소수점 첫째 자리" in message
    dialog.cumulative_edit.setText("20.0")
    try:
        dialog.values()
    except ValueError as exc:
        assert "사유" in str(exc)
    else:
        raise AssertionError("missing reason should be rejected")


def test_dashboard_start_date_save_and_completion_flow(monkeypatch):
    _app()
    dashboard_service = _DashboardService(
        summaries=(_summary(),), details=(_row(7),)
    )
    dialog = TrackingDashboardDialog(
        dashboard_service, _WorkReportService(), lambda: None
    )
    assert dialog.start_date_edit.date() == QDate(2026, 7, 29)
    dialog.summary_table.selectRow(0)
    dialog.start_date_edit.setDate(QDate(2026, 7, 28))
    dialog.save_start_date_button.click()
    assert dashboard_service.start_dates == [
        ("AB260101", date(2026, 7, 28))
    ]

    monkeypatch.setattr(
        dialog_module.QMessageBox,
        "information",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        dialog_module.QMessageBox,
        "question",
        lambda *_args: dialog_module.QMessageBox.StandardButton.Yes,
    )
    dialog.complete_button.click()
    assert dashboard_service.completed == ["AB260101"]
    dialog.close()


def test_completion_refreshes_embedded_final_preview(monkeypatch):
    _app()
    dashboard_service = _DashboardService(
        summaries=(_summary(),), details=(_row(7),)
    )
    initial_preview = FinalReportPreview(
        date_from=date(2026, 7, 29),
        date_to=date(2026, 7, 29),
        rows=(_summary(),),
        blockers=(),
    )
    refreshed_preview = FinalReportPreview(
        date_from=None,
        date_to=None,
        rows=(),
        blockers=(FinalizationBlocker(7, "COMPLETED", "완료 항목 제외"),),
    )
    preview_calls: list[str] = []

    def preview_supplier() -> FinalReportPreview:
        preview_calls.append("refreshed")
        return refreshed_preview

    dialog = TrackingDashboardDialog(
        dashboard_service,
        _WorkReportService(),
        lambda: None,
        final_preview=initial_preview,
        preview_supplier=preview_supplier,
    )
    assert dialog.final_preview_view.preview_table.rowCount() == 1
    assert dialog.final_preview_view.confirm_button.isEnabled() is True
    monkeypatch.setattr(dialog_module.QMessageBox, "information", lambda *_: None)
    monkeypatch.setattr(
        dialog_module.QMessageBox,
        "question",
        lambda *_: dialog_module.QMessageBox.StandardButton.Yes,
    )

    dialog.summary_table.selectRow(0)
    dialog.complete_button.click()

    assert dashboard_service.completed == ["AB260101"]
    assert preview_calls == ["refreshed"]
    assert dialog.final_preview_view.preview_table.rowCount() == 0
    assert dialog.final_preview_view.confirm_button.isEnabled() is False
    dialog.close()


def test_completed_dialog_uses_same_summary_table_and_resumes_selected_row(
    monkeypatch,
):
    _app()
    service = _DashboardService(
        summaries=(_summary(completed_at="2026-08-01T00:00:00+00:00"),),
        details=(_row(7),),
    )
    dialog = CompletedTrackingDialog(
        service, _WorkReportService(), lambda: None
    )

    assert dialog.windowTitle() == "완료 장비 목록"
    assert dialog.summary_table.columnCount() == len(dialog_module._SUMMARY_HEADERS)
    monkeypatch.setattr(
        dialog_module.QMessageBox,
        "question",
        lambda *_args: dialog_module.QMessageBox.StandardButton.Yes,
    )
    dialog.summary_table.selectRow(0)
    dialog.resume_button.click()
    assert service.resumed == ["AB260101"]
    dialog.close()


def test_resuming_from_completed_child_refreshes_parent_preview(monkeypatch):
    _app()

    class StatefulDashboardService:
        def __init__(self) -> None:
            self.resumed = False

        def summaries(self):
            return (_summary(),) if self.resumed else ()

        def completed_summaries(self):
            return () if self.resumed else (_summary(),)

        def drill_down(self, _tracking_no):
            return (_row(7),)

        def resume(self, _tracking_no):
            self.resumed = True

    service = StatefulDashboardService()
    initial_preview = FinalReportPreview(
        date_from=None,
        date_to=None,
        rows=(),
        blockers=(FinalizationBlocker(7, "COMPLETED", "완료 항목 제외"),),
    )
    resumed_preview = FinalReportPreview(
        date_from=date(2026, 7, 29),
        date_to=date(2026, 7, 29),
        rows=(_summary(),),
        blockers=(),
    )
    preview_calls: list[str] = []

    def preview_supplier() -> FinalReportPreview:
        preview_calls.append("resumed")
        return resumed_preview

    parent = TrackingDashboardDialog(
        service,
        _WorkReportService(),
        lambda: None,
        final_preview=initial_preview,
        preview_supplier=preview_supplier,
    )

    class AutoResumeCompletedDialog(CompletedTrackingDialog):
        def exec(self):
            self.summary_table.selectRow(0)
            self.resume_button.click()
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        dialog_module, "CompletedTrackingDialog", AutoResumeCompletedDialog
    )
    monkeypatch.setattr(
        dialog_module.QMessageBox,
        "question",
        lambda *_: dialog_module.QMessageBox.StandardButton.Yes,
    )

    parent._open_completed_list()

    assert service.resumed is True
    assert parent.summary_table.rowCount() == 1
    assert preview_calls == ["resumed"]
    assert parent.final_preview_view.preview_table.rowCount() == 1
    assert parent.final_preview_view.confirm_button.isEnabled() is True
    parent.close()


class _DashboardService:
    def __init__(self, *, summaries, details):
        self._summaries = summaries
        self._details = details
        self.summary_calls = 0
        self.drill_down_calls: list[str] = []
        self.start_dates: list[tuple[str, date]] = []
        self.completed: list[str] = []
        self.resumed: list[str] = []

    def summaries(self):
        self.summary_calls += 1
        return self._summaries

    def drill_down(self, tracking_no):
        self.drill_down_calls.append(tracking_no)
        return self._details

    def set_start_date(self, tracking_no, start_date):
        self.start_dates.append((tracking_no, start_date))

    def complete(self, tracking_no):
        self.completed.append(tracking_no)

    def resume(self, tracking_no):
        self.resumed.append(tracking_no)

    def completed_summaries(self):
        return self._summaries


class _WorkReportService:
    def __init__(self):
        self.saved: list[dict] = []
        self.update_calls: list[tuple[int, dict, str]] = []
        self.confirm_calls: list[tuple[int, Decimal, str]] = []
        self.confirm_series_cumulative_calls: list[tuple[str, Decimal, str]] = []

    def get_cumulative_baseline(self, tracking_no):
        return None

    def save_cumulative_baseline(self, **values):
        self.saved.append(values)
        return SimpleNamespace(**values)

    def update_row(self, row_id, changes, *, resolution_note):
        self.update_calls.append((row_id, changes, resolution_note))
        return SimpleNamespace()

    def confirm_row(
        self,
        row_id,
        *,
        confirmed_daily_man_day,
        resolution_note,
    ):
        self.confirm_calls.append(
            (row_id, confirmed_daily_man_day, resolution_note)
        )
        return SimpleNamespace()

    def confirm_series_cumulative(
        self,
        tracking_no,
        *,
        confirmed_cumulative_man_day,
        resolution_note,
    ):
        self.confirm_series_cumulative_calls.append(
            (tracking_no, confirmed_cumulative_man_day, resolution_note)
        )
        return SimpleNamespace()


def _visible_tracking_nos(dialog: TrackingDashboardDialog) -> list[str]:
    return [
        dialog.summary_table.item(row, dialog_module._TRACKING_COLUMN).text()
        for row in range(dialog.summary_table.rowCount())
    ]


def _select_cells(table, positions: tuple[tuple[int, int], ...]) -> None:
    table.clearSelection()
    for row, column in positions:
        table.selectionModel().select(
            table.model().index(row, column),
            table.selectionModel().SelectionFlag.Select,
        )


def _summary(
    tracking_no: str = "AB260101",
    latest_work_date: date | None = date(2026, 7, 30),
    *,
    blockers: tuple[FinalizationBlocker, ...] = (),
    completed_at: str | None = None,
) -> TrackingDashboardSummary:
    return TrackingDashboardSummary(
        normalized_tracking_no=tracking_no,
        tracking_no=tracking_no,
        vendor_name="업체A",
        vendor_sort_order=1,
        equipment_name="장비 1",
        business_team="WA",
        latest_work_date=latest_work_date,
        latest_row_id=7,
        latest_actual_headcount=3,
        latest_night_headcount=1,
        latest_man_day_basis="혼합",
        latest_confirmed_daily_man_day=Decimal("3.5"),
        latest_reported_cumulative_man_day=Decimal("23.5"),
        latest_calculated_cumulative_man_day=Decimal("23.5"),
        latest_confirmed_cumulative_man_day=Decimal("23.5"),
        initial_cumulative_man_day=Decimal("20.0"),
        source_row_ids=(7, 8),
        blockers=blockers,
        start_date=date(2026, 7, 29),
        completed_at=completed_at,
    )


def _row(
    row_id: int,
    *,
    work_date: date = date(2026, 7, 29),
    issue_codes: tuple[WorkReportIssueCode, ...] = (
        WorkReportIssueCode.CUMULATIVE_MISMATCH,
    ),
) -> WorkReportRow:
    return WorkReportRow(
        row_id=row_id,
        source_type=RowSource.MAIL,
        extracted_record_id=row_id,
        mail_entry_id=f"ENTRY-{row_id}",
        work_date=work_date,
        work_date_confirmed=True,
        vendor_name="업체A",
        tracking_no="AB260101",
        equipment_name="장비 1",
        business_team="WA",
        actual_headcount=3,
        night_headcount=1,
        per_person_man_day=None,
        reported_daily_man_day=Decimal("3.5"),
        calculated_daily_man_day=Decimal("3.5"),
        confirmed_daily_man_day=Decimal("3.5"),
        reported_cumulative_man_day=Decimal("23.5"),
        calculated_cumulative_man_day=Decimal("23.5"),
        confirmed_cumulative_man_day=Decimal("23.5"),
        cumulative_series_key="AB260101",
        issue_codes=issue_codes,
        review_status=ReviewStatus.NORMAL,
        included=True,
        warning_confirmed=False,
        resolution_note=None,
    )
