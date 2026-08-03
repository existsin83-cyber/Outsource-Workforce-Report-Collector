from decimal import Decimal

import pytest
from PySide6.QtWidgets import QApplication

from outsource_mail_collector.domain.work_report import WorkReportIssueCode
from outsource_mail_collector.ui.problem_review_dialog import (
    ProblemReviewDialog,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_mismatch_choice_buttons_copy_mail_or_calculated_values():
    _app()
    dialog = ProblemReviewDialog(
        reported_daily=Decimal("2.0"),
        calculated_daily=Decimal("3.0"),
        reported_cumulative=Decimal("10.0"),
        calculated_cumulative=Decimal("11.0"),
    )

    dialog.mail_value_button.click()
    assert dialog.confirmed_daily_edit.text() == "2.0"
    assert dialog.confirmed_cumulative_edit.text() == "10.0"
    dialog.calculated_value_button.click()
    assert dialog.confirmed_daily_edit.text() == "3.0"
    assert dialog.confirmed_cumulative_edit.text() == "11.0"
    dialog.close()


def test_direct_input_button_preserves_values_for_manual_editing():
    _app()
    dialog = ProblemReviewDialog(
        reported_daily=Decimal("2.0"),
        calculated_daily=Decimal("3.0"),
        reported_cumulative=Decimal("10.0"),
        calculated_cumulative=Decimal("11.0"),
        confirmed_daily=Decimal("4.0"),
        confirmed_cumulative=Decimal("12.0"),
    )

    dialog.direct_input_button.click()

    assert dialog.confirmed_daily_edit.text() == "4.0"
    assert dialog.confirmed_cumulative_edit.text() == "12.0"
    assert "직접 입력" in dialog.choice_label.text()
    dialog.close()


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


def test_review_dialog_explains_values_and_prefills_confirmed_candidates():
    _app()
    dialog = ProblemReviewDialog(
        reported_daily=Decimal("3.0"),
        calculated_daily=Decimal("3.0"),
        reported_cumulative=Decimal("12.0"),
        calculated_cumulative=Decimal("12.0"),
        confirmed_daily=Decimal("3.0"),
        confirmed_cumulative=Decimal("12.0"),
        issue_codes=(WorkReportIssueCode.DAILY_MISMATCH,),
    )

    instruction = dialog.instruction_label.text()
    assert "메일값" in instruction
    assert "자동 계산값" in instruction
    assert "Excel" in instruction
    assert "당일 투입 공수 불일치" in dialog.issue_label.text()
    assert dialog.confirmed_daily_edit.text() == "3.0"
    assert dialog.confirmed_cumulative_edit.text() == "12.0"


def test_invalid_accept_displays_specific_error_in_dialog():
    _app()
    dialog = ProblemReviewDialog()

    dialog._accept_if_valid()

    assert "확인 사유" in dialog.error_label.text()
    dialog.note_edit.setText("원문 확인")
    dialog._accept_if_valid()
    assert "확정 투입" in dialog.error_label.text()
