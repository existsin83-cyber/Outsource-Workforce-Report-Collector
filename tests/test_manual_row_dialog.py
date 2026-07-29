from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication

from outsource_mail_collector.ui.manual_row_dialog import ManualRowDialog


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_manual_dialog_returns_validated_decimal_input():
    _app()
    dialog = ManualRowDialog()
    dialog.work_date_edit.setDate(QDate(2026, 8, 1))
    dialog.vendor_edit.setText("업체A")
    dialog.tracking_edit.setText("AB260101")
    dialog.equipment_edit.setText("장비 1")
    dialog.business_team_edit.setText("WA")
    dialog.headcount_edit.setText("2")
    dialog.per_person_edit.setText("1.5")
    dialog.reported_daily_edit.setText("")
    dialog.reported_cumulative_edit.setText("12.0")
    dialog.note_edit.setText("주말 작업 확인")

    values = dialog.values()

    assert values["work_date"] == date(2026, 8, 1)
    assert values["actual_headcount"] == 2
    assert values["per_person_man_day"] == Decimal("1.5")
    assert values["reported_daily_man_day"] is None
    assert values["reported_cumulative_man_day"] == Decimal("12.0")


@pytest.mark.parametrize(
    ("headcount", "per_person"),
    [("1.5", "1.0"), ("2", "not-a-number")],
)
def test_manual_dialog_rejects_invalid_numeric_text(
    headcount: str, per_person: str
):
    _app()
    dialog = ManualRowDialog()
    dialog.vendor_edit.setText("업체A")
    dialog.tracking_edit.setText("AB260101")
    dialog.business_team_edit.setText("WA")
    dialog.headcount_edit.setText(headcount)
    dialog.per_person_edit.setText(per_person)
    dialog.note_edit.setText("확인")

    with pytest.raises(ValueError):
        dialog.values()
