"""Final whole-table confirmation and copy dialog."""

from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from outsource_mail_collector.application.models import (
    FinalReportPreview,
    FinalReportSnapshot,
    WorkReportRow,
)
from outsource_mail_collector.application.report_renderer import RenderedReport
from outsource_mail_collector.ui.work_report_guidance import COLUMN_HELP


_HEADERS = (
    "일자",
    "거래처명",
    "Tracking No.",
    "장비명",
    "사업팀",
    "실제 작업인원",
    "야근 인원",
    "인당 공수",
    "투입 공수",
    "누적 공수",
)


class FinalReportDialog(QDialog):
    confirm_requested = Signal()
    copy_requested = Signal()

    def __init__(
        self, preview: FinalReportPreview, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("최종 표 미리보기")
        self.resize(1100, 650)
        self.snapshot: FinalReportSnapshot | None = None
        self.rendered_report: RenderedReport | None = None
        layout = QVBoxLayout(self)
        self.blocker_label = QLabel(_blocker_text(preview))
        self.blocker_label.setWordWrap(True)
        self.blocker_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        if preview.blockers:
            self.blocker_label.setStyleSheet(
                "background:#ffebee;color:#c62828;padding:8px;"
            )
        layout.addWidget(self.blocker_label)
        self.preview_table = _preview_table(preview.rows)
        layout.addWidget(self.preview_table)
        actions = QHBoxLayout()
        actions.addStretch()
        self.confirm_button = QPushButton("전체 최종 확인")
        self.confirm_button.setEnabled(preview.can_confirm)
        self.confirm_button.clicked.connect(self.confirm_requested.emit)
        self.copy_button = QPushButton("표 복사")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self.copy_requested.emit)
        close_button = QPushButton("닫기")
        close_button.clicked.connect(self.reject)
        actions.addWidget(self.confirm_button)
        actions.addWidget(self.copy_button)
        actions.addWidget(close_button)
        layout.addLayout(actions)

    def set_confirmed_report(
        self,
        snapshot: FinalReportSnapshot,
        rendered_report: RenderedReport,
    ) -> None:
        self.snapshot = snapshot
        self.rendered_report = rendered_report
        self.copy_button.setEnabled(snapshot.invalidated_at is None)

    def invalidate_confirmation(self) -> None:
        self.snapshot = None
        self.rendered_report = None
        self.copy_button.setEnabled(False)


def _blocker_text(preview: FinalReportPreview) -> str:
    if not preview.blockers:
        return "전체 행을 확인한 뒤 최종 확정해 주세요."
    rows_by_id = {row.row_id: row for row in preview.rows}
    blockers_by_row: dict[int, list[str]] = defaultdict(list)
    for blocker in preview.blockers:
        if blocker.message not in blockers_by_row[blocker.row_id]:
            blockers_by_row[blocker.row_id].append(blocker.message)
    lines = ["최종 확정할 수 없습니다."]
    for row_id, messages in blockers_by_row.items():
        row = rows_by_id.get(row_id)
        context = [f"행 {row_id}"]
        if row is not None:
            context.extend(
                value
                for value in (
                    row.work_date.isoformat() if row.work_date else None,
                    row.vendor_name,
                    row.tracking_no,
                )
                if value
            )
        lines.append(" / ".join(context))
        lines.extend(f"• {message}" for message in messages)
    return "\n".join(lines)


def _preview_table(rows: tuple[WorkReportRow, ...]) -> QTableWidget:
    table = QTableWidget(len(rows), len(_HEADERS))
    table.setHorizontalHeaderLabels(_HEADERS)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.ResizeToContents
    )
    table.horizontalHeader().setStretchLastSection(True)
    for column, header in enumerate(_HEADERS):
        help_key = {
            "투입 공수": "확정 투입",
            "누적 공수": "확정 누적",
        }.get(header, header)
        table.horizontalHeaderItem(column).setToolTip(
            COLUMN_HELP.get(help_key, header)
        )
    for row_index, row in enumerate(rows):
        values = (
            row.work_date.isoformat() if row.work_date else "",
            row.vendor_name or "",
            row.tracking_no or "",
            row.equipment_name or "",
            row.business_team or "",
            "" if row.actual_headcount is None else str(row.actual_headcount),
            "" if row.night_headcount is None else str(row.night_headcount),
            _decimal_text(row.per_person_man_day),
            _decimal_text(row.confirmed_daily_man_day),
            _decimal_text(row.confirmed_cumulative_man_day),
        )
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            header_item = table.horizontalHeaderItem(column)
            item.setToolTip(
                f"{header_item.toolTip()}\n현재 표시값: {value or '없음'}"
            )
            table.setItem(row_index, column, item)
    return table


def _decimal_text(value: object | None) -> str:
    return "" if value is None else f"{value:.1f}"
