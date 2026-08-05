from datetime import date
from decimal import Decimal

from PySide6.QtWidgets import QApplication, QMessageBox

from outsource_mail_collector.application.models import (
    FinalizationBlocker,
    FinalReportPreview,
    FinalReportRow,
    FinalReportSnapshot,
    TrackingDashboardSummary,
)
from outsource_mail_collector.application.report_renderer import RenderedReport
from outsource_mail_collector.ui.final_report_dialog import FinalReportDialog


def test_preview_blocker_notice_is_compact_and_row_tooltip_keeps_details():
    _app()
    preview = FinalReportPreview(
        date_from=date(2026, 7, 29),
        date_to=date(2026, 7, 29),
        rows=(_summary(blockers=(FinalizationBlocker(7, "ONE", "원인과 조치"),)),),
        blockers=(FinalizationBlocker(7, "ONE", "원인과 조치"),),
    )
    dialog = FinalReportDialog(preview)

    assert dialog.blocker_label.text() == "확정 전 확인 필요: 1건"
    assert "원인과 조치" in dialog.preview_table.item(0, 0).toolTip()


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_excel_button_shows_preparation_notice(monkeypatch):
    _app()
    dialog = FinalReportDialog(
        FinalReportPreview(
            date_from=date(2026, 7, 29), date_to=date(2026, 7, 29), rows=(), blockers=()
        )
    )
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, title, text: shown.append((title, text)),
    )

    dialog.excel_button.click()

    assert shown
    assert "실제 Excel 연동은 아직 준비되지 않았습니다." in shown[0][1]
    assert "실 워크북 확보 후 사용할 수 있습니다." in shown[0][1]


def test_show_copy_error_sets_inline_status_without_modal(monkeypatch):
    _app()
    dialog = FinalReportDialog(
        FinalReportPreview(
            date_from=date(2026, 7, 29), date_to=date(2026, 7, 29), rows=(), blockers=()
        )
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("copy failure must not show a blocking modal")
        ),
    )

    dialog.show_copy_error("클립보드를 사용할 수 없습니다.")

    assert "클립보드를 사용할 수 없습니다." in dialog.copy_status_label.text()


def test_blocker_details_are_visible_below_preview_table():
    _app()
    preview = FinalReportPreview(
        date_from=date(2026, 7, 29),
        date_to=date(2026, 7, 29),
        rows=(
            _summary(
                blockers=(FinalizationBlocker(7, "ONE", "원인 설명 / 조치 설명"),)
            ),
        ),
        blockers=(FinalizationBlocker(7, "ONE", "원인 설명 / 조치 설명"),),
    )

    dialog = FinalReportDialog(preview)

    details = dialog.blocker_details_label.text()
    assert "작업일" in details
    assert "업체" in details
    assert "Tracking No." in details
    assert "원인 설명" in details
    assert "조치" in details


def test_blockers_disable_confirmation_and_identify_affected_row():
    _app()
    preview = FinalReportPreview(
        date_from=date(2026, 7, 29),
        date_to=date(2026, 7, 29),
        rows=(
            _summary(
                blockers=(
                    FinalizationBlocker(7, "WARNING_UNCONFIRMED", "확인 필요"),
                )
            ),
        ),
        blockers=(FinalizationBlocker(7, "WARNING_UNCONFIRMED", "확인 필요"),),
    )

    dialog = FinalReportDialog(preview)

    assert dialog.confirm_button.isEnabled() is False
    assert dialog.blocker_label.text() == "확정 전 확인 필요: 1건"
    assert dialog.copy_button.isEnabled() is True


def test_clean_multi_tracking_preview_uses_nine_column_table_and_enables_confirmation():
    _app()
    preview = FinalReportPreview(
        date_from=date(2026, 7, 29),
        date_to=date(2026, 7, 30),
        rows=(
            _summary(tracking_no="AB260101", latest_work_date=date(2026, 7, 29)),
            _summary(tracking_no="AB260102", latest_work_date=date(2026, 7, 30)),
        ),
        blockers=(),
    )

    dialog = FinalReportDialog(preview)

    assert dialog.confirm_button.isEnabled() is True
    assert dialog.preview_table.rowCount() == 2
    assert dialog.preview_table.columnCount() == 9
    headers = [
        dialog.preview_table.horizontalHeaderItem(column).text()
        for column in range(dialog.preview_table.columnCount())
    ]
    assert headers.count("일자") == 1
    assert headers == [
        "일자",
        "거래처명",
        "Tracking No.",
        "장비명",
        "사업팀",
        "실제 작업인원",
        "인당 공수",
        "투입 공수",
        "누적 공수",
    ]
    assert dialog.copy_button.isEnabled() is True


def test_cumulative_value_is_under_cumulative_header():
    _app()
    row = _summary(
        latest_confirmed_daily_man_day=Decimal("1.5"),
        latest_confirmed_cumulative_man_day=Decimal("3.0"),
    )
    preview = FinalReportPreview(
        date_from=date(2026, 7, 29),
        date_to=date(2026, 7, 29),
        rows=(row,),
        blockers=(),
    )

    dialog = FinalReportDialog(preview)
    cumulative_column = next(
        column
        for column in range(dialog.preview_table.columnCount())
        if dialog.preview_table.horizontalHeaderItem(column).text()
        == "누적 공수"
    )

    assert dialog.preview_table.item(0, cumulative_column).text() == "3.0"


def test_final_preview_shows_mixed_basis_without_night_column():
    _app()
    row = _summary()
    preview = FinalReportPreview(
        date_from=date(2026, 7, 29),
        date_to=date(2026, 7, 29),
        rows=(row,),
        blockers=(),
    )

    dialog = FinalReportDialog(preview)
    headers = [
        dialog.preview_table.horizontalHeaderItem(column).text()
        for column in range(dialog.preview_table.columnCount())
    ]

    assert "야근 인원" not in headers
    assert dialog.preview_table.item(0, headers.index("인당 공수")).text() == "혼합"
    assert dialog.preview_table.item(0, headers.index("투입 공수")).text() == "3.0"


def test_blockers_are_grouped_once_per_row_with_row_context():
    _app()
    preview = FinalReportPreview(
        date_from=date(2026, 7, 29),
        date_to=date(2026, 7, 29),
        rows=(
            _summary(
                blockers=(
                    FinalizationBlocker(7, "ONE", "첫 번째 문제"),
                    FinalizationBlocker(7, "TWO", "두 번째 문제"),
                )
            ),
        ),
        blockers=(
            FinalizationBlocker(7, "ONE", "첫 번째 문제"),
            FinalizationBlocker(7, "TWO", "두 번째 문제"),
        ),
    )

    dialog = FinalReportDialog(preview)
    text = dialog.blocker_label.text()

    assert text == "확정 전 확인 필요: 2건"


def test_copy_uses_preview_before_confirmation_and_snapshot_after():
    _app()
    preview = FinalReportPreview(
        date_from=date(2026, 7, 29),
        date_to=date(2026, 7, 29),
        rows=(_summary(),),
        blockers=(),
    )
    dialog = FinalReportDialog(preview)
    snapshot = FinalReportSnapshot(
        report_id=1,
        date_from=date(2026, 7, 29),
        date_to=date(2026, 7, 29),
        snapshot_hash="hash",
        confirmed_at="now",
        copied_at=None,
        invalidated_at=None,
        rows=(
            FinalReportRow(
                source_row_id=1,
                work_date=date(2026, 7, 29),
                vendor_name="업체A",
                vendor_sort_order=1,
                tracking_no="AB260101",
                equipment_name="장비 1",
                business_team="WA",
                actual_headcount=2,
                night_headcount=2,
                man_day_basis="1.5",
                confirmed_daily_man_day=Decimal("3.0"),
                confirmed_cumulative_man_day=Decimal("12.0"),
            ),
        ),
    )

    assert dialog.copy_button.isEnabled() is True
    unconfirmed = dialog.current_rendered_report()
    assert "AB260101" in unconfirmed.plain_text
    assert "미확정 미리보기" in unconfirmed.plain_text

    dialog.set_confirmed_report(
        snapshot, RenderedReport("<table></table>", "표")
    )
    assert dialog.current_rendered_report().plain_text == "표"

    dialog.invalidate_confirmation()
    assert dialog.copy_button.isEnabled() is True
    assert "미확정 미리보기" in dialog.current_rendered_report().plain_text


def _summary(
    *,
    tracking_no: str = "AB260101",
    latest_work_date: date = date(2026, 7, 29),
    latest_confirmed_daily_man_day: Decimal = Decimal("3.0"),
    latest_confirmed_cumulative_man_day: Decimal = Decimal("12.0"),
    blockers: tuple[FinalizationBlocker, ...] = (),
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
        latest_actual_headcount=2,
        latest_night_headcount=1,
        latest_man_day_basis="혼합",
        latest_confirmed_daily_man_day=latest_confirmed_daily_man_day,
        latest_reported_cumulative_man_day=latest_confirmed_cumulative_man_day,
        latest_calculated_cumulative_man_day=latest_confirmed_cumulative_man_day,
        latest_confirmed_cumulative_man_day=latest_confirmed_cumulative_man_day,
        initial_cumulative_man_day=None,
        source_row_ids=(7,),
        blockers=blockers,
    )
