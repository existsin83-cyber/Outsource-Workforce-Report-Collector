from datetime import date
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from outsource_mail_collector.application.models import WorkReportRow
from outsource_mail_collector.domain.models import ReviewStatus
from outsource_mail_collector.domain.work_report import RowSource
from outsource_mail_collector.ui.deleted_rows_dialog import DeletedRowsDialog


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_deleted_rows_dialog_returns_checkbox_selected_ids():
    _app()
    dialog = DeletedRowsDialog([_row(7), _row(8)])
    dialog.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    dialog.table.item(1, 0).setCheckState(Qt.CheckState.Checked)

    assert dialog.selected_row_ids() == [7, 8]


def test_deleted_rows_dialog_requires_selection_and_reason(monkeypatch):
    _app()
    dialog = DeletedRowsDialog([_row(7)])
    messages: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, _title, text: messages.append(text),
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, text: messages.append(text),
    )

    dialog._accept()
    dialog.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    dialog._accept()

    assert messages == [
        "복구할 행을 선택해 주세요.",
        "복구 사유를 입력해 주세요.",
    ]
    assert dialog.result() == dialog.DialogCode.Rejected

    dialog.reason_edit.setText("실수로 삭제")
    dialog._accept()
    assert dialog.result() == dialog.DialogCode.Accepted


def test_deleted_rows_dialog_cancellation_returns_rejected():
    _app()
    dialog = DeletedRowsDialog([_row(7)])
    dialog.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    dialog.reason_edit.setText("복구하지 않음")

    dialog.reject()

    assert dialog.result() == dialog.DialogCode.Rejected


def _row(row_id: int) -> WorkReportRow:
    return WorkReportRow(
        row_id=row_id,
        source_type=RowSource.MAIL,
        extracted_record_id=row_id,
        mail_entry_id=f"ENTRY-{row_id}",
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
        confirmed_daily_man_day=Decimal("3.0"),
        reported_cumulative_man_day=Decimal("12.0"),
        calculated_cumulative_man_day=Decimal("12.0"),
        confirmed_cumulative_man_day=Decimal("12.0"),
        cumulative_series_key="AB260101",
        issue_codes=(),
        review_status=ReviewStatus.NORMAL,
        included=True,
        warning_confirmed=True,
        resolution_note="사용자 선택 삭제",
        deleted_at="2026-07-31T00:00:00+00:00",
    )
