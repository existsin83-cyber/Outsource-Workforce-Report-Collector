"""Extended work-report review grid backed by application DTOs."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QWidget,
)

from outsource_mail_collector.application.models import WorkReportRow
from outsource_mail_collector.domain.models import ReviewStatus
from outsource_mail_collector.domain.work_report import man_day_basis


_COLUMNS = (
    "",
    "작업일",
    "거래처명",
    "Tracking No.",
    "장비명",
    "사업팀",
    "실제 작업인원",
    "야근 인원",
    "인당 공수",
    "메일 투입",
    "계산 투입",
    "확정 투입",
    "메일 누적",
    "계산 누적",
    "확정 누적",
    "검증 상태",
    "포함",
    "작업",
)
_INCLUDED_COLUMN = _COLUMNS.index("포함")
_ACTIONS_COLUMN = _COLUMNS.index("작업")
_PROBLEM_BACKGROUND = QColor("#fff3e0")


class ReviewGridWidget(QTableWidget):
    """Display compilation rows while delegating decisions to application services."""

    original_requested = Signal(str)
    exclude_requested = Signal(int)
    review_requested = Signal(int)

    def __init__(
        self,
        rows: list[WorkReportRow] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(0, len(_COLUMNS), parent)
        self.setHorizontalHeaderLabels(_COLUMNS)
        self.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        if rows:
            self.set_rows(rows)

    def set_rows(self, rows: list[WorkReportRow]) -> None:
        self.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self._populate_row(row_index, row)

    def checked_row_ids(self) -> list[int]:
        result: list[int] = []
        for row_index in range(self.rowCount()):
            item = self.item(row_index, 0)
            if item is not None and item.checkState() is Qt.CheckState.Checked:
                result.append(int(item.data(Qt.ItemDataRole.UserRole)))
        return result

    def _populate_row(self, row_index: int, row: WorkReportRow) -> None:
        selector = QTableWidgetItem()
        selector.setFlags(
            Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
        )
        selector.setCheckState(Qt.CheckState.Unchecked)
        selector.setData(Qt.ItemDataRole.UserRole, row.row_id)
        self.setItem(row_index, 0, selector)

        issue_text = (
            ", ".join(issue.value for issue in row.issue_codes)
            if row.issue_codes
            else row.review_status.value
        )
        values = (
            row.work_date.isoformat() if row.work_date else "확인 필요",
            row.vendor_name or "",
            row.tracking_no or "",
            row.equipment_name or "",
            row.business_team or "",
            "" if row.actual_headcount is None else str(row.actual_headcount),
            "" if row.night_headcount is None else str(row.night_headcount),
            man_day_basis(row.actual_headcount, row.night_headcount),
            _display_decimal(row.reported_daily_man_day),
            _display_decimal(row.calculated_daily_man_day),
            _display_decimal(row.confirmed_daily_man_day),
            _display_decimal(row.reported_cumulative_man_day),
            _display_decimal(row.calculated_cumulative_man_day),
            _display_decimal(row.confirmed_cumulative_man_day),
            issue_text,
        )
        problem = bool(row.issue_codes) and not row.warning_confirmed
        for column, value in enumerate(values, start=1):
            item = QTableWidgetItem(value)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if problem:
                item.setBackground(_PROBLEM_BACKGROUND)
            if not row.included or row.review_status is ReviewStatus.EXCLUDED:
                font = QFont(item.font())
                font.setStrikeOut(True)
                item.setFont(font)
            self.setItem(row_index, column, item)

        included = QTableWidgetItem("포함" if row.included else "제외")
        included.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        included.setFlags(included.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if not row.included:
            font = QFont(included.font())
            font.setStrikeOut(True)
            included.setFont(font)
        self.setItem(row_index, _INCLUDED_COLUMN, included)
        self.setCellWidget(
            row_index, _ACTIONS_COLUMN, self._row_actions(row)
        )

    def _row_actions(self, row: WorkReportRow) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        if row.mail_entry_id:
            original = QToolButton()
            original.setText("원본")
            original.clicked.connect(
                lambda _checked=False, entry_id=row.mail_entry_id: (
                    self.original_requested.emit(entry_id)
                )
            )
            layout.addWidget(original)
        review = QToolButton()
        review.setText("확인")
        review.clicked.connect(
            lambda _checked=False, row_id=row.row_id: (
                self.review_requested.emit(row_id)
            )
        )
        exclude = QToolButton()
        exclude.setText("제외")
        exclude.clicked.connect(
            lambda _checked=False, row_id=row.row_id: (
                self.exclude_requested.emit(row_id)
            )
        )
        layout.addWidget(review)
        layout.addWidget(exclude)
        return container


def _display_decimal(value: Decimal | None) -> str:
    return "" if value is None else f"{value:.1f}"
