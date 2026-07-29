"""Dialog for confirming mismatched values or duplicate decisions."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QWidget,
)


class ProblemReviewDialog(QDialog):
    def __init__(
        self,
        *,
        reported_daily: Decimal | None = None,
        calculated_daily: Decimal | None = None,
        reported_cumulative: Decimal | None = None,
        calculated_cumulative: Decimal | None = None,
        duplicate_mode: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("문제 행 확인")
        self._duplicate_mode = duplicate_mode
        layout = QFormLayout(self)
        self.reported_daily_label = QLabel(_display(reported_daily))
        self.calculated_daily_label = QLabel(_display(calculated_daily))
        self.reported_cumulative_label = QLabel(
            _display(reported_cumulative)
        )
        self.calculated_cumulative_label = QLabel(
            _display(calculated_cumulative)
        )
        self.confirmed_daily_edit = QLineEdit()
        self.confirmed_cumulative_edit = QLineEdit()
        self.duplicate_decision = QComboBox()
        self.duplicate_decision.addItem("선택", None)
        self.duplicate_decision.addItem("기존 보고 유지", "KEEP_OLD")
        self.duplicate_decision.addItem("새 보고로 교체", "REPLACE_NEW")
        self.duplicate_decision.addItem("둘 다 제외", "EXCLUDE_BOTH")
        self.note_edit = QLineEdit()
        if duplicate_mode:
            layout.addRow("중복 처리", self.duplicate_decision)
        else:
            for label, widget in (
                ("메일 투입", self.reported_daily_label),
                ("계산 투입", self.calculated_daily_label),
                ("확정 투입", self.confirmed_daily_edit),
                ("메일 누적", self.reported_cumulative_label),
                ("계산 누적", self.calculated_cumulative_label),
                ("확정 누적", self.confirmed_cumulative_edit),
            ):
                layout.addRow(label, widget)
        layout.addRow("확인 사유", self.note_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> dict[str, object]:
        note = self.note_edit.text().strip()
        if not note:
            raise ValueError("확인 사유를 입력해 주세요.")
        if self._duplicate_mode:
            decision = self.duplicate_decision.currentData()
            if decision is None:
                raise ValueError("중복 처리 방식을 선택해 주세요.")
            return {
                "duplicate_decision": str(decision),
                "resolution_note": note,
            }
        return {
            "confirmed_daily_man_day": _required_decimal(
                self.confirmed_daily_edit.text()
            ),
            "confirmed_cumulative_man_day": _required_decimal(
                self.confirmed_cumulative_edit.text()
            ),
            "resolution_note": note,
        }

    def _accept_if_valid(self) -> None:
        try:
            self.values()
        except ValueError:
            return
        self.accept()


def _display(value: Decimal | None) -> str:
    return "" if value is None else f"{value:.1f}"


def _required_decimal(raw_value: str) -> Decimal:
    try:
        value = Decimal(raw_value.strip())
    except InvalidOperation as exc:
        raise ValueError("확정 공수를 숫자로 입력해 주세요.") from exc
    if not value.is_finite() or value < 0:
        raise ValueError("확정 공수는 0 이상의 유한한 숫자여야 합니다.")
    return value
