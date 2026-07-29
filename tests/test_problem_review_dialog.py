from decimal import Decimal

import pytest
from PySide6.QtWidgets import QApplication

from outsource_mail_collector.ui.problem_review_dialog import (
    ProblemReviewDialog,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_mismatch_review_shows_values_and_requires_choice_and_note():
    _app()
    dialog = ProblemReviewDialog(
        reported_daily=Decimal("4.0"),
        calculated_daily=Decimal("3.0"),
        reported_cumulative=Decimal("13.0"),
        calculated_cumulative=Decimal("12.0"),
    )

    assert "4.0" in dialog.reported_daily_label.text()
    assert "3.0" in dialog.calculated_daily_label.text()
    with pytest.raises(ValueError):
        dialog.values()

    dialog.confirmed_daily_edit.setText("3.0")
    dialog.confirmed_cumulative_edit.setText("12.0")
    dialog.note_edit.setText("계산값 확인")
    values = dialog.values()

    assert values["confirmed_daily_man_day"] == Decimal("3.0")
    assert values["confirmed_cumulative_man_day"] == Decimal("12.0")
    assert values["resolution_note"] == "계산값 확인"


def test_duplicate_review_requires_explicit_decision():
    _app()
    dialog = ProblemReviewDialog(duplicate_mode=True)
    dialog.note_edit.setText("수정 보고 확인")

    with pytest.raises(ValueError):
        dialog.values()

    dialog.duplicate_decision.setCurrentIndex(
        dialog.duplicate_decision.findData("REPLACE_NEW")
    )
    assert dialog.values()["duplicate_decision"] == "REPLACE_NEW"
