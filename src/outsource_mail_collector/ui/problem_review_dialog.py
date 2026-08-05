"""Dialog for confirming mismatched values or duplicate decisions."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from outsource_mail_collector.domain.work_report import WorkReportIssueCode
from outsource_mail_collector.ui.work_report_guidance import (
    COLUMN_HELP,
    issue_action,
    issue_title,
)


class ProblemReviewDialog(QDialog):
    def __init__(
        self,
        *,
        reported_daily: Decimal | None = None,
        calculated_daily: Decimal | None = None,
        reported_cumulative: Decimal | None = None,
        calculated_cumulative: Decimal | None = None,
        confirmed_daily: Decimal | None = None,
        issue_codes: tuple[WorkReportIssueCode, ...] = (),
        actual_headcount: int | None = None,
        night_headcount: int | None = None,
        headcount_correction: bool = False,
        work_date: date | None = None,
        date_correction: bool = False,
        tracking_no: str | None = None,
        series_key_correction: bool = False,
        duplicate_mode: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("문제 행 확인")
        self._duplicate_mode = duplicate_mode
        self._headcount_correction = (
            headcount_correction
            or actual_headcount is not None
            or night_headcount is not None
        )
        self._date_correction = date_correction
        self._series_key_correction = series_key_correction
        layout = QFormLayout(self)
        self.instruction_label = QLabel(
            "메일값은 메일 본문에서 읽은 값, 자동 계산값은 인원·공수 "
            "규칙으로 계산한 값입니다. 두 값을 비교해 Excel에 반영할 "
            "확정 투입을 입력하세요. 확정 누적은 수주 공수 대시보드 "
            "상단표에서 Tracking No. 단위로 확정합니다."
        )
        self.instruction_label.setWordWrap(True)
        layout.addRow(self.instruction_label)
        self.issue_label = QLabel(
            "\n".join(
                f"{issue_title(issue)} — {issue_action(issue)}"
                for issue in issue_codes
            )
        )
        self.issue_label.setWordWrap(True)
        self.issue_label.setStyleSheet("color:#e65100;")
        self.issue_label.setVisible(bool(issue_codes))
        layout.addRow(self.issue_label)
        self.reported_daily_label = QLabel(_display(reported_daily))
        self.calculated_daily_label = QLabel(_display(calculated_daily))
        self.reported_cumulative_label = QLabel(
            _display(reported_cumulative)
        )
        self.calculated_cumulative_label = QLabel(
            _display(calculated_cumulative)
        )
        self.confirmed_daily_edit = QLineEdit(_display(confirmed_daily))
        self.mail_value_button = QPushButton("메일값 채택")
        self.calculated_value_button = QPushButton("계산값 채택")
        self.direct_input_button = QPushButton("직접 입력")
        self.choice_label = QLabel()
        self.choice_label.setStyleSheet("color:#555;")
        self.mail_value_button.clicked.connect(
            lambda: self._choose_values(reported_daily, reported_cumulative)
        )
        self.calculated_value_button.clicked.connect(
            lambda: self._choose_values(calculated_daily, calculated_cumulative)
        )
        self.direct_input_button.clicked.connect(self._choose_direct_input)
        self.actual_headcount_edit = QLineEdit(_display_int(actual_headcount))
        self.night_headcount_edit = QLineEdit(_display_int(night_headcount))
        self.work_date_edit = QDateEdit()
        self.work_date_edit.setCalendarPopup(True)
        initial_work_date = work_date or date.today()
        self.work_date_edit.setDate(
            QDate(
                initial_work_date.year,
                initial_work_date.month,
                initial_work_date.day,
            )
        )
        self.tracking_no_edit = QLineEdit(tracking_no or "")
        self.tracking_no_edit.setPlaceholderText("예: SE260101")
        self.duplicate_decision = QComboBox()
        self.duplicate_decision.addItem("선택", None)
        self.duplicate_decision.addItem("기존 보고 유지", "KEEP_OLD")
        self.duplicate_decision.addItem("새 보고로 교체", "REPLACE_NEW")
        self.duplicate_decision.addItem("둘 다 제외", "EXCLUDE_BOTH")
        self.note_edit = QLineEdit()
        self.confirmed_daily_edit.setPlaceholderText(
            "메일값과 계산값을 비교해 확정 투입 입력"
        )
        self.note_edit.setPlaceholderText("확정 근거 또는 확인 내용을 입력")
        for key, widget in (
            ("메일 투입", self.reported_daily_label),
            ("계산 투입", self.calculated_daily_label),
            ("확정 투입", self.confirmed_daily_edit),
            ("메일 누적", self.reported_cumulative_label),
            ("계산 누적", self.calculated_cumulative_label),
        ):
            widget.setToolTip(COLUMN_HELP[key])
        if duplicate_mode:
            layout.addRow("중복 처리", self.duplicate_decision)
        else:
            if self._date_correction:
                layout.addRow("작업일자", self.work_date_edit)
            if self._series_key_correction:
                layout.addRow("Tracking No.", self.tracking_no_edit)
            if self._headcount_correction:
                layout.addRow("실제 작업인원", self.actual_headcount_edit)
                layout.addRow("야근 인원", self.night_headcount_edit)
            for label, widget in (
                ("메일 투입", self.reported_daily_label),
                ("계산 투입", self.calculated_daily_label),
                ("확정 투입", self.confirmed_daily_edit),
                ("메일 누적", self.reported_cumulative_label),
                ("계산 누적", self.calculated_cumulative_label),
            ):
                layout.addRow(label, widget)
            choice_layout = QHBoxLayout()
            choice_layout.addWidget(self.mail_value_button)
            choice_layout.addWidget(self.calculated_value_button)
            choice_layout.addWidget(self.direct_input_button)
            layout.addRow("불일치 빠른 선택", choice_layout)
            layout.addRow(self.choice_label)
        self.note_edit.setToolTip(
            "어떤 원문과 계산 근거로 확정했는지 기록합니다."
        )
        layout.addRow("확인 사유", self.note_edit)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color:#c62828;")
        layout.addRow(self.error_label)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "확정값 저장"
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
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
        values: dict[str, object] = {
            "confirmed_daily_man_day": _required_decimal(
                self.confirmed_daily_edit.text(),
                field_name="확정 투입",
            ),
            "resolution_note": note,
        }
        if self._headcount_correction:
            actual = _required_headcount(
                self.actual_headcount_edit.text(),
                field_name="실제 작업인원",
            )
            night = _required_headcount(
                self.night_headcount_edit.text(),
                field_name="야근 인원",
            )
            if night > actual:
                raise ValueError(
                    "야근 인원은 실제 작업인원보다 클 수 없습니다."
                )
            values["actual_headcount"] = actual
            values["night_headcount"] = night
        if self._date_correction:
            selected = self.work_date_edit.date()
            values["work_date"] = date(
                selected.year(), selected.month(), selected.day()
            )
        if self._series_key_correction:
            tracking_no = self.tracking_no_edit.text().strip()
            if not tracking_no:
                raise ValueError("Tracking No.를 입력해 주세요.")
            values["tracking_no"] = tracking_no
        return values

    def _accept_if_valid(self) -> None:
        try:
            self.values()
        except ValueError as exc:
            self.error_label.setText(str(exc))
            return
        self.error_label.clear()
        self.accept()

    def _choose_values(
        self,
        daily: Decimal | None,
        cumulative: Decimal | None,
    ) -> None:
        del cumulative  # 확정 누적은 이 창에서 다루지 않는다 (Tracking No. 단위로 대시보드에서 확정)
        if daily is not None:
            self.confirmed_daily_edit.setText(_display(daily))
        self.choice_label.setText("메일값 또는 계산값을 선택했습니다.")

    def _choose_direct_input(self) -> None:
        self.choice_label.setText(
            "직접 입력을 선택했습니다. 확정 투입을 직접 수정하세요."
        )
        self.confirmed_daily_edit.setFocus()


def _display(value: Decimal | None) -> str:
    return "" if value is None else f"{value:.1f}"


def _display_int(value: int | None) -> str:
    return "" if value is None else str(value)


def _required_headcount(raw_value: str, *, field_name: str) -> int:
    try:
        value = Decimal(raw_value.strip())
    except InvalidOperation as exc:
        raise ValueError(f"{field_name}을 숫자로 입력해 주세요.") from exc
    if (
        not value.is_finite()
        or value < 0
        or value != value.to_integral_value()
    ):
        raise ValueError(f"{field_name}은 0 이상의 정수여야 합니다.")
    return int(value)


def _required_decimal(raw_value: str, *, field_name: str) -> Decimal:
    try:
        value = Decimal(raw_value.strip())
    except InvalidOperation as exc:
        raise ValueError(f"{field_name}을 숫자로 입력해 주세요.") from exc
    if not value.is_finite() or value < 0:
        raise ValueError(
            f"{field_name}은 0 이상의 유한한 숫자여야 합니다."
        )
    return value
