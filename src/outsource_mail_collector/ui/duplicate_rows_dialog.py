"""Read-only listing of rows that may report the same work more than once.

Purely informational: shows groups of rows sharing (작업일, 거래처명,
Tracking No., 장비명) so the user can decide what to do next (제외, 선택
삭제, or the existing 중복 처리 flow) - this dialog does not mutate anything.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from outsource_mail_collector.application.models import WorkReportRow

_HEADERS = ("No.", "작업일", "Tracking No.", "거래처명", "장비명")


class DuplicateRowsDialog(QDialog):
    """List each duplicate-candidate group with a blank row between groups."""

    def __init__(
        self,
        groups: tuple[tuple[WorkReportRow, ...], ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("중복 확인")
        self.resize(700, 420)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                f"작업일·거래처명·Tracking No.·장비명이 같은 행 그룹 {len(groups)}건입니다. "
                "값만 확인하는 창이며, 처리는 초기화면의 '제외' 또는 '선택 삭제'로 해 주세요."
                if groups
                else "동일 조합으로 중복 의심되는 행이 없습니다."
            )
        )
        rows_with_gaps = sum(len(group) + 1 for group in groups) - bool(groups)
        table = QTableWidget(max(rows_with_gaps, 0), len(_HEADERS))
        table.setHorizontalHeaderLabels(_HEADERS)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        # ponytail: 그룹 사이 빈 행으로 중복 후보를 묶어 보여주므로 제목 클릭
        # 정렬은 이 구조를 깨뜨린다. 열 너비 조절만 지원한다.
        row_index = 0
        for group_index, group in enumerate(groups):
            for row in group:
                values = (
                    str(row.row_id),
                    row.work_date.isoformat() if row.work_date else "확인 필요",
                    row.tracking_no or "",
                    row.vendor_name or "",
                    row.equipment_name or "",
                )
                for column, value in enumerate(values):
                    table.setItem(row_index, column, QTableWidgetItem(value))
                row_index += 1
            if group_index < len(groups) - 1:
                row_index += 1
        table.resizeColumnsToContents()
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
