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


def test_clean_multi_date_preview_repeats_headers_and_enables_confirmation():
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
    assert dialog.preview_text.toPlainText().count("일자\t거래처명") == 2
    assert dialog.copy_button.isEnabled() is False


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
