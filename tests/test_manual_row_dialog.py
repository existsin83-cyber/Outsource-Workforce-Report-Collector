from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication

from outsource_mail_collector.ui.manual_row_dialog import ManualRowDialog


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_manual_row_collects_actual_and_night_headcount():
    _app()
    dialog = ManualRowDialog()
    dialog.work_date_edit.setDate(QDate(2026, 8, 1))
    dialog.vendor_edit.setText("업체A")
    dialog.tracking_edit.setText("AB260101")
    dialog.equipment_edit.setText("장비 1")
    dialog.business_team_edit.setText("PKG")
    dialog.headcount_edit.setText("3")
    dialog.night_headcount_edit.setText("1")
    dialog.reported_daily_edit.setText("3.5")
    dialog.reported_cumulative_edit.setText("12.0")
    dialog.note_edit.setText("주말 작업 확인")

    values = dialog.values()

    assert values["work_date"] == date(2026, 8, 1)
    assert values["actual_headcount"] == 3
    assert values["night_headcount"] == 1
    assert "per_person_man_day" not in values
    assert values["reported_daily_man_day"] == Decimal("3.5")
    assert values["reported_cumulative_man_day"] == Decimal("12.0")


@pytest.mark.parametrize(
    ("headcount", "night_headcount"),
    [
        ("1.5", "1"),
        ("2", "not-a-number"),
        ("3", "4"),
    ],
)
def test_manual_dialog_rejects_invalid_numeric_text(
    headcount: str, night_headcount: str
):
    _app()
    dialog = ManualRowDialog()
    dialog.vendor_edit.setText("업체A")
    dialog.tracking_edit.setText("AB260101")
    dialog.business_team_edit.setText("WA")
    dialog.headcount_edit.setText(headcount)
    dialog.night_headcount_edit.setText(night_headcount)
    dialog.note_edit.setText("확인")

    with pytest.raises(ValueError):
        dialog.values()
