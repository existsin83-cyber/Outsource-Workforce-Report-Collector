"""Final whole-table confirmation and copy dialog."""

from __future__ import annotations

from itertools import groupby

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from outsource_mail_collector.application.models import (
    FinalReportPreview,
    FinalReportSnapshot,
    WorkReportRow,
)
from outsource_mail_collector.application.report_renderer import RenderedReport


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
        self.blocker_label = QLabel(_blocker_text(preview))
        if preview.blockers:
            self.blocker_label.setStyleSheet(
                "background:#ffebee;color:#c62828;padding:8px;"
            )
        layout.addWidget(self.blocker_label)
        self.preview_text = QPlainTextEdit(_preview_text(preview.rows))
        self.preview_text.setReadOnly(True)
        layout.addWidget(self.preview_text)
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
    details = ", ".join(
        f"행 {blocker.row_id}: {blocker.message}"
        for blocker in preview.blockers
    )
    return f"최종 확정 불가 — {details}"


def _preview_text(rows: tuple[WorkReportRow, ...]) -> str:
    lines: list[str] = []
    for _work_date, grouped in groupby(rows, key=lambda row: row.work_date):
        lines.append("\t".join(_HEADERS))
        for row in grouped:
            lines.append(
                "\t".join(
                    (
                        row.work_date.isoformat() if row.work_date else "",
                        row.vendor_name or "",
                        row.tracking_no or "",
                        row.equipment_name or "",
                        row.business_team or "",
                        (
                            ""
                            if row.actual_headcount is None
                            else str(row.actual_headcount)
                        ),
                        _decimal_text(row.per_person_man_day),
                        _decimal_text(row.confirmed_daily_man_day),
                        _decimal_text(row.confirmed_cumulative_man_day),
                    )
                )
            )
    return "\n".join(lines)


def _decimal_text(value: object | None) -> str:
    return "" if value is None else f"{value:.1f}"
