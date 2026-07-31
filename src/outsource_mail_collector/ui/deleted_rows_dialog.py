"""Recovery dialog for application-soft-deleted work-report rows."""

from __future__ import annotations

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
        layout = QVBoxLayout(self)
        self.table = QTableWidget(len(rows), 6)
        self.table.setHorizontalHeaderLabels(
            ("", "작업일", "Tracking No.", "거래처명", "장비명", "삭제 시각")
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        for row_index, row in enumerate(rows):
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
