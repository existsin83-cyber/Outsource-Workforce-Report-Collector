"""Validated input dialog for weekend and exceptional manual work rows."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QWidget,
)


class ManualRowDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("수동 행 추가")
        layout = QFormLayout(self)
        self.work_date_edit = QDateEdit(QDate.currentDate())
        self.work_date_edit.setCalendarPopup(True)
        self.vendor_edit = QLineEdit()
        self.tracking_edit = QLineEdit()
        self.equipment_edit = QLineEdit()
        self.business_team_edit = QLineEdit()
        self.headcount_edit = QLineEdit()
        self.per_person_edit = QLineEdit()
        self.reported_daily_edit = QLineEdit()
        self.reported_cumulative_edit = QLineEdit()
        self.note_edit = QLineEdit()
        for label, widget in (
            ("작업일", self.work_date_edit),
            ("거래처명", self.vendor_edit),
            ("Tracking No.", self.tracking_edit),
            ("장비명", self.equipment_edit),
            ("사업팀", self.business_team_edit),
            ("실제 작업인원", self.headcount_edit),
            ("인당 공수", self.per_person_edit),
            ("메일 투입 공수", self.reported_daily_edit),
            ("메일 누적 공수", self.reported_cumulative_edit),
            ("추가 사유", self.note_edit),
        ):
            layout.addRow(label, widget)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> dict[str, object]:
        selected = self.work_date_edit.date()
        vendor = self.vendor_edit.text().strip()
        tracking = self.tracking_edit.text().strip() or None
        equipment = self.equipment_edit.text().strip() or None
        business_team = self.business_team_edit.text().strip()
        note = self.note_edit.text().strip()
        if not vendor or not business_team or not note:
            raise ValueError("거래처명, 사업팀, 추가 사유는 필수입니다.")
        if tracking is None and equipment is None:
            raise ValueError("Tracking No. 또는 장비명을 입력해 주세요.")
        headcount = _headcount(self.headcount_edit.text())
        return {
            "work_date": date(
                selected.year(), selected.month(), selected.day()
            ),
            "vendor_name": vendor,
            "tracking_no": tracking,
            "equipment_name": equipment,
            "business_team": business_team,
            "actual_headcount": headcount,
            "per_person_man_day": _decimal(
                self.per_person_edit.text(), required=True
            ),
            "reported_daily_man_day": _decimal(
                self.reported_daily_edit.text(), required=False
            ),
            "reported_cumulative_man_day": _decimal(
                self.reported_cumulative_edit.text(), required=False
            ),
            "resolution_note": note,
        }

    def _accept_if_valid(self) -> None:
        try:
            self.values()
        except ValueError:
            return
        self.accept()


def _headcount(raw_value: str) -> int:
    value = _decimal(raw_value, required=True)
    assert value is not None
    if value != value.to_integral_value() or value < 0:
        raise ValueError("실제 작업인원은 0 이상의 정수여야 합니다.")
    return int(value)


def _decimal(raw_value: str, *, required: bool) -> Decimal | None:
    stripped = raw_value.strip()
    if not stripped:
        if required:
            raise ValueError("필수 숫자 값을 입력해 주세요.")
        return None
    try:
        value = Decimal(stripped)
    except InvalidOperation as exc:
        raise ValueError("숫자 형식을 확인해 주세요.") from exc
    if not value.is_finite() or value < 0:
        raise ValueError("0 이상의 유한한 숫자를 입력해 주세요.")
    return value
