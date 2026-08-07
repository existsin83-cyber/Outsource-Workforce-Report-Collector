"""Final whole-table confirmation and copy dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from outsource_mail_collector.application.models import (
    FinalReportPreview,
    FinalReportSnapshot,
    TrackingDashboardSummary,
)
from outsource_mail_collector.application.report_renderer import (
    RenderedReport,
    render_table,
)
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
        self.preview = preview
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
        self.copy_button.setToolTip(
            "표 복사: 현재 화면의 표를 그대로 복사합니다. "
            "최종 확정 전에도 사용할 수 있습니다."
        )
        self.copy_button.clicked.connect(self.copy_requested.emit)
        self.excel_button = QPushButton("Excel 반영")
        self.excel_button.clicked.connect(self._show_excel_notice)
        close_button = QPushButton("닫기")
        close_button.clicked.connect(self.reject)
        actions.addWidget(self.confirm_button)
        actions.addWidget(self.copy_button)
        actions.addWidget(self.excel_button)
        actions.addWidget(close_button)
        layout.addLayout(actions)
        self.copy_status_label = QLabel()
        self.copy_status_label.setWordWrap(True)
        layout.addWidget(self.copy_status_label)

    def current_rendered_report(self) -> RenderedReport:
        """Render the confirmed snapshot, or the on-screen preview if unconfirmed."""
        if self.rendered_report is not None:
            return self.rendered_report
        return render_table(
            _preview_title(self.preview),
            [_row_values(row) for row in self.preview.rows],
        )

    def refresh_preview(self, preview: FinalReportPreview) -> None:
        """Replace the displayed preview after dashboard state changes."""
        self.preview = preview
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
        self.copy_status_label.clear()

    def invalidate_confirmation(self) -> None:
        self.snapshot = None
        self.rendered_report = None
        self.copy_status_label.clear()

    def show_copy_error(self, message: str) -> None:
        """Show a clipboard-copy failure inline instead of a blocking modal."""
        self.copy_status_label.setText(f"⚠ 표 복사 실패: {message}")
        self.copy_status_label.setStyleSheet(
            "background:#ffebee;color:#c62828;padding:6px;"
        )

    def _show_excel_notice(self) -> None:
        QMessageBox.information(
            self,
            "Excel 연동 준비 중",
            "실제 Excel 연동은 아직 준비되지 않았습니다.\n"
            "실 워크북 확보 후 사용할 수 있습니다.",
        )


def _blocker_text(preview: FinalReportPreview) -> str:
    if not preview.blockers:
        return "전체 행을 확인한 뒤 최종 확정해 주세요."
    return f"확정 전 확인 필요: {len(preview.blockers)}건"


def _blocker_details_text(preview: FinalReportPreview) -> str:
    if not preview.blockers:
        return "차단 상세: 없음"
    lines = ["차단 상세"]
    for row in preview.rows:
        if not row.blockers:
            continue
        context = (
            f"작업일: {row.latest_work_date.isoformat() if row.latest_work_date else '미확정'} / "
            f"업체: {row.vendor_name or '없음'} / "
            f"Tracking No.: {row.tracking_no or '없음'}"
        )
        for blocker in row.blockers:
            lines.append(
                f"{context}\n원인: {blocker.message}\n"
                "조치: 확인 후 확정값을 수정하거나 사유를 기록하세요."
            )
    return "\n\n".join(lines)


def _preview_table(
    rows: tuple[TrackingDashboardSummary, ...], blockers=()
) -> QTableWidget:
    table = QTableWidget(len(rows), len(_HEADERS))
    table.setHorizontalHeaderLabels(_HEADERS)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.Interactive
    )
    table.horizontalHeader().setStretchLastSection(True)
    # ponytail: 이 표의 행 순서는 실제 최종 확정/복사되는 순서와 같아야 하므로
    # 제목 클릭 정렬은 지원하지 않는다(정렬하면 화면과 실제 반영 순서가
    # 어긋난다). 열 너비 조절만 지원.
    for column, header in enumerate(_HEADERS):
        help_key = {
            "투입 공수": "확정 투입",
            "누적 공수": "확정 누적",
        }.get(header, header)
        table.horizontalHeaderItem(column).setToolTip(
            COLUMN_HELP.get(help_key, header)
        )
    for row_index, row in enumerate(rows):
        values = _row_values(row)
        details = [blocker.message for blocker in row.blockers]
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            header_item = table.horizontalHeaderItem(column)
            item.setToolTip(
                f"{header_item.toolTip()}\n현재 표시값: {value or '없음'}"
            )
            if details:
                item.setToolTip(
                    item.toolTip() + "\n확인 필요: " + "; ".join(details)
                )
            table.setItem(row_index, column, item)
    table.resizeColumnsToContents()
    return table


def _row_values(row: TrackingDashboardSummary) -> tuple[str, ...]:
    return (
        row.latest_work_date.isoformat() if row.latest_work_date else "",
        row.vendor_name or "",
        row.tracking_no or "",
        row.equipment_name or "",
        row.business_team or "",
        (
            ""
            if row.latest_actual_headcount is None
            else str(row.latest_actual_headcount)
        ),
        row.latest_man_day_basis or "",
        _decimal_text(row.latest_confirmed_daily_man_day),
        _decimal_text(row.latest_confirmed_cumulative_man_day),
    )


def _preview_title(preview: FinalReportPreview) -> str:
    dates = sorted(
        row.latest_work_date for row in preview.rows if row.latest_work_date
    )
    if not dates:
        return "전장 외주 공수표 (미확정 미리보기)"
    return (
        f"{dates[0].isoformat()} ~ {dates[-1].isoformat()} "
        "전장 외주 공수표 (미확정 미리보기)"
    )


def _decimal_text(value: object | None) -> str:
    return "" if value is None else f"{value:.1f}"
