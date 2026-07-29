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


def test_night_issue_review_returns_validated_headcount_corrections():
    _app()
    dialog = ProblemReviewDialog(
        reported_daily=Decimal("3.5"),
        calculated_daily=None,
        reported_cumulative=Decimal("10.0"),
        calculated_cumulative=None,
        actual_headcount=3,
        night_headcount=None,
    )

    assert dialog.actual_headcount_edit.text() == "3"
    assert dialog.night_headcount_edit.text() == ""

    dialog.night_headcount_edit.setText("1")
    dialog.confirmed_daily_edit.setText("3.5")
    dialog.confirmed_cumulative_edit.setText("10.0")
    dialog.note_edit.setText("혼합 야근 인원 확인")

    assert dialog.values() == {
        "actual_headcount": 3,
        "night_headcount": 1,
        "confirmed_daily_man_day": Decimal("3.5"),
        "confirmed_cumulative_man_day": Decimal("10.0"),
        "resolution_note": "혼합 야근 인원 확인",
    }


def test_night_issue_review_rejects_night_above_actual_headcount():
    _app()
    dialog = ProblemReviewDialog(
        actual_headcount=3,
        night_headcount=None,
    )
    dialog.night_headcount_edit.setText("4")
    dialog.confirmed_daily_edit.setText("3.5")
    dialog.confirmed_cumulative_edit.setText("10.0")
    dialog.note_edit.setText("야근 인원 확인")

    with pytest.raises(ValueError):
        dialog.values()


def test_night_issue_review_can_correct_two_missing_headcounts():
    _app()
    dialog = ProblemReviewDialog(
        actual_headcount=None,
        night_headcount=None,
        headcount_correction=True,
    )
    dialog.actual_headcount_edit.setText("2")
    dialog.night_headcount_edit.setText("0")
    dialog.confirmed_daily_edit.setText("2.0")
    dialog.confirmed_cumulative_edit.setText("8.0")
    dialog.note_edit.setText("인원 원문 확인")

    values = dialog.values()

    assert values["actual_headcount"] == 2
    assert values["night_headcount"] == 0


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
