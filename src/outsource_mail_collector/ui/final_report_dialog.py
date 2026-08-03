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
        self._layout = layout
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
        self.preview_table = _preview_table(preview.rows, preview.blockers)
        layout.addWidget(self.preview_table)
        self.blocker_details_label = QLabel(_blocker_details_text(preview))
        self.blocker_details_label.setWordWrap(True)
        self.blocker_details_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.blocker_details_label.setStyleSheet(
            "background:#fff8e1;color:#5d4037;padding:8px;"
            if preview.blockers
            else ""
        )
        layout.addWidget(self.blocker_details_label)
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

    def refresh_preview(self, preview: FinalReportPreview) -> None:
        """Replace the displayed preview after dashboard state changes."""
        self.blocker_label.setText(_blocker_text(preview))
        self.blocker_label.setStyleSheet(
            "background:#ffebee;color:#c62828;padding:8px;"
            if preview.blockers
            else ""
        )
        previous_table = self.preview_table
        self.preview_table = _preview_table(preview.rows, preview.blockers)
        self._layout.replaceWidget(previous_table, self.preview_table)
        previous_table.deleteLater()
        self.blocker_details_label.setText(_blocker_details_text(preview))
        self.blocker_details_label.setStyleSheet(
            "background:#fff8e1;color:#5d4037;padding:8px;"
            if preview.blockers
            else ""
        )
        self.confirm_button.setEnabled(preview.can_confirm)
        self.invalidate_confirmation()

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
    return f"확정 전 확인 필요: {len(preview.blockers)}건"


def _blocker_details_text(preview: FinalReportPreview) -> str:
    if not preview.blockers:
        return "차단 상세: 없음"
    rows_by_id = {row.row_id: row for row in preview.rows}
    lines = ["차단 상세"]
    for blocker in preview.blockers:
        row = rows_by_id.get(blocker.row_id)
        if row is None:
            context = "행 정보 없음"
        else:
            context = (
                f"작업일: {row.work_date.isoformat() if row.work_date else '미확정'} / "
                f"업체: {row.vendor_name or '없음'} / "
                f"Tracking No.: {row.tracking_no or '없음'}"
            )
        lines.append(
            f"{context}\n원인: {blocker.message}\n"
            "조치: 확인 후 확정값을 수정하거나 사유를 기록하세요."
        )
    return "\n\n".join(lines)


def _preview_table(
    rows: tuple[WorkReportRow, ...], blockers=()
) -> QTableWidget:
    table = QTableWidget(len(rows), len(_HEADERS))
    table.setHorizontalHeaderLabels(_HEADERS)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.ResizeToContents
    )
    table.horizontalHeader().setStretchLastSection(True)
    blockers_by_row: dict[int, list[str]] = defaultdict(list)
    # The preview table itself receives blocker details so the banner remains compact.
    for blocker in blockers:
        if blocker.message not in blockers_by_row[blocker.row_id]:
            blockers_by_row[blocker.row_id].append(blocker.message)
    for row in rows:
        for blocker in getattr(row, "blockers", ()):
            if blocker.message not in blockers_by_row[row.row_id]:
                blockers_by_row[row.row_id].append(blocker.message)
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
            _basis_text(row),
            _decimal_text(row.confirmed_daily_man_day),
            _decimal_text(row.confirmed_cumulative_man_day),
        )
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            header_item = table.horizontalHeaderItem(column)
            item.setToolTip(
                f"{header_item.toolTip()}\n현재 표시값: {value or '없음'}"
            )
            details = blockers_by_row.get(row.row_id)
            if details:
                item.setToolTip(
                    item.toolTip() + "\n확인 필요: " + "; ".join(details)
                )
            table.setItem(row_index, column, item)
    return table


def _decimal_text(value: object | None) -> str:
    return "" if value is None else f"{value:.1f}"


def _basis_text(row: object) -> str:
    basis = getattr(row, "man_day_basis", None)
    if basis:
        return str(basis)
    return str(getattr(row, "per_person_display", ""))
