"""Recovery dialog for application-soft-deleted work-report rows."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from outsource_mail_collector.application.models import WorkReportRow

_HEADERS = ("", "작업일", "Tracking No.", "거래처명", "장비명", "삭제 시각")
_SORTABLE_COLUMNS: dict[str, Callable[[WorkReportRow], Any]] = {
    "작업일": lambda row: row.work_date,
    "Tracking No.": lambda row: row.tracking_no or "",
    "거래처명": lambda row: row.vendor_name or "",
    "장비명": lambda row: row.equipment_name or "",
    "삭제 시각": lambda row: row.deleted_at or "",
}


class DeletedRowsDialog(QDialog):
    """Select application-deleted rows and capture an audit reason."""

    def __init__(
        self,
        rows: tuple[WorkReportRow, ...] | list[WorkReportRow],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("삭제 항목 복구")
        self.resize(850, 420)
        self._rows = list(rows)
        self._sort_column: int | None = None
        self._sort_ascending = True
        layout = QVBoxLayout(self)
        self.table = QTableWidget(len(rows), len(_HEADERS))
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().sectionClicked.connect(
            self._header_clicked
        )
        self._render_rows()
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table)
        form = QFormLayout()
        self.reason_edit = QLineEdit()
        self.reason_edit.setPlaceholderText("복구 사유를 입력해 주세요.")
        form.addRow("복구 사유", self.reason_edit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("선택 복구")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _render_rows(self) -> None:
        self.table.setRowCount(len(self._rows))
        for row_index, row in enumerate(self._rows):
            selector = QTableWidgetItem()
            selector.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
            )
            selector.setCheckState(Qt.CheckState.Unchecked)
            selector.setData(Qt.ItemDataRole.UserRole, row.row_id)
            self.table.setItem(row_index, 0, selector)
            values = (
                row.work_date.isoformat() if row.work_date else "확인 필요",
                row.tracking_no or "",
                row.vendor_name or "",
                row.equipment_name or "",
                row.deleted_at or "",
            )
            for column, value in enumerate(values, start=1):
                self.table.setItem(row_index, column, QTableWidgetItem(value))

    def _header_clicked(self, column: int) -> None:
        if column == 0:
            return
        key_func = _SORTABLE_COLUMNS.get(_HEADERS[column])
        if key_func is None or not self._rows:
            return
        if self._sort_column == column:
            self._sort_ascending = not self._sort_ascending
        else:
            self._sort_column = column
            self._sort_ascending = True
        checked_ids = set(self.selected_row_ids())
        self._rows.sort(
            key=lambda row: (key_func(row) is None, key_func(row)),
            reverse=not self._sort_ascending,
        )
        self._render_rows()
        for row_index in range(self.table.rowCount()):
            item = self.table.item(row_index, 0)
            if item is not None and int(item.data(Qt.ItemDataRole.UserRole)) in checked_ids:
                item.setCheckState(Qt.CheckState.Checked)

    def selected_row_ids(self) -> list[int]:
        result: list[int] = []
        for row_index in range(self.table.rowCount()):
            item = self.table.item(row_index, 0)
            if item is not None and item.checkState() is Qt.CheckState.Checked:
                result.append(int(item.data(Qt.ItemDataRole.UserRole)))
        return result

    def resolution_note(self) -> str:
        return self.reason_edit.text().strip()

    def _accept(self) -> None:
        if not self.selected_row_ids():
            QMessageBox.information(
                self, "복구 항목 선택", "복구할 행을 선택해 주세요."
            )
            return
        if not self.resolution_note():
            QMessageBox.warning(
                self, "복구 사유 필요", "복구 사유를 입력해 주세요."
            )
            return
        self.accept()
