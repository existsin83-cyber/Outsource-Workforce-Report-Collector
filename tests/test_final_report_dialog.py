from datetime import date
from decimal import Decimal

from PySide6.QtWidgets import QApplication

from outsource_mail_collector.application.models import (
    FinalizationBlocker,
    FinalReportPreview,
    FinalReportRow,
    FinalReportSnapshot,
    WorkReportRow,
)
from outsource_mail_collector.application.report_renderer import RenderedReport
from outsource_mail_collector.domain.models import ReviewStatus
from outsource_mail_collector.domain.work_report import RowSource
from outsource_mail_collector.ui.final_report_dialog import FinalReportDialog


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_blockers_disable_confirmation_and_identify_affected_row():
    _app()
    preview = FinalReportPreview(
        date_from=date(2026, 7, 29),
        date_to=date(2026, 7, 29),
        rows=(_work_row(7),),
        blockers=(
            FinalizationBlocker(7, "WARNING_UNCONFIRMED", "확인 필요"),
        ),
    )

    dialog = FinalReportDialog(preview)

    assert dialog.confirm_button.isEnabled() is False
    assert "7" in dialog.blocker_label.text()
    assert dialog.copy_button.isEnabled() is False


def test_clean_multi_date_preview_uses_nine_column_table_and_enables_confirmation():
    _app()
    preview = FinalReportPreview(
        date_from=date(2026, 7, 29),
        date_to=date(2026, 7, 30),
        rows=(
            _work_row(1, date(2026, 7, 29)),
            _work_row(2, date(2026, 7, 30)),
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
    assert dialog.copy_button.isEnabled() is False


def test_cumulative_value_is_under_cumulative_header():
    _app()
    row = _work_row(1)
    row = WorkReportRow(
        **{
            **row.__dict__,
            "confirmed_daily_man_day": Decimal("1.5"),
            "confirmed_cumulative_man_day": Decimal("3.0"),
        }
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
    row = _work_row(1)
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
        rows=(_work_row(7),),
        blockers=(
            FinalizationBlocker(7, "ONE", "첫 번째 문제"),
            FinalizationBlocker(7, "TWO", "두 번째 문제"),
        ),
    )

    dialog = FinalReportDialog(preview)
    text = dialog.blocker_label.text()

    assert text.startswith("최종 확정할 수 없습니다.")
    assert text.count("행 7") == 1
    assert "2026-07-29" in text
    assert "업체A" in text
    assert "AB260101" in text
    assert "• 첫 번째 문제" in text
    assert "• 두 번째 문제" in text


def test_copy_enables_only_after_confirmed_snapshot_and_can_be_invalidated():
    _app()
    preview = FinalReportPreview(
        date_from=date(2026, 7, 29),
        date_to=date(2026, 7, 29),
        rows=(_work_row(1),),
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

    dialog.set_confirmed_report(
        snapshot, RenderedReport("<table></table>", "표")
    )
    assert dialog.copy_button.isEnabled() is True

    dialog.invalidate_confirmation()
    assert dialog.copy_button.isEnabled() is False


def _work_row(
    row_id: int, work_date: date = date(2026, 7, 29)
) -> WorkReportRow:
    return WorkReportRow(
        row_id=row_id,
        source_type=RowSource.MANUAL,
        extracted_record_id=None,
        mail_entry_id=None,
        work_date=work_date,
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
        confirmed_daily_man_day=Decimal("3.0"),
        reported_cumulative_man_day=Decimal("12.0"),
        calculated_cumulative_man_day=Decimal("12.0"),
        confirmed_cumulative_man_day=Decimal("12.0"),
        cumulative_series_key="업체a|T:AB260101",
        issue_codes=(),
        review_status=ReviewStatus.REVIEWED,
        included=True,
        warning_confirmed=True,
        resolution_note=None,
    )
