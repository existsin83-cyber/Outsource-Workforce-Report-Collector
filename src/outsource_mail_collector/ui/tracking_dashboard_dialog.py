"""Tracking-No dashboard widgets backed only by application services."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Callable, Protocol

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from outsource_mail_collector.application.models import (
    FinalReportPreview,
    TrackingDashboardSummary,
    WorkReportRow,
)
from outsource_mail_collector.application.tracking_dashboard_service import (
    TrackingDashboardService,
)
from outsource_mail_collector.application.work_report_service import (
    WorkReportService,
)
from outsource_mail_collector.ui.final_report_dialog import FinalReportDialog
from outsource_mail_collector.ui.work_report_guidance import (
    issue_action,
    issue_title,
)


_SUMMARY_HEADERS = (
    "Tracking No.",
    "최근 작업일",
    "거래처명",
    "장비명",
    "사업팀",
    "최근 실제 인원",
    "최근 야근 인원",
    "인당 공수",
    "최근 확정 투입",
    "초기 누적",
    "메일 누적",
    "계산 누적",
    "확정 누적",
    "검증 상태",
)
_DETAIL_HEADERS = (
    "원본 행",
    "작업일",
    "실제 작업인원",
    "야근 인원",
    "인당 공수",
    "메일 투입",
    "계산 투입",
    "확정 투입",
    "메일 누적",
    "계산 누적",
    "확정 누적",
    "포함",
    "검토 상태",
    "문제 및 조치",
)
_BLOCKING_BACKGROUND = QColor("#ffebee")
_BLOCKING_FOREGROUND = QColor("#7f0000")


class _BaselineData(Protocol):
    effective_through_date: date
    cumulative_man_day: Decimal


class BaselineDialog(QDialog):
    """Edit one explicit cumulative baseline with an audit reason."""

    def __init__(
        self,
        tracking_no: str,
        *,
        earliest_work_date: date | None,
        baseline: _BaselineData | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("초기 누적 설정")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("Tracking No.", QLabel(tracking_no))
        default_date = (
            baseline.effective_through_date
            if baseline is not None
            else (earliest_work_date or date.today()) - timedelta(days=1)
        )
        self.effective_date_edit = QDateEdit(
            QDate(default_date.year, default_date.month, default_date.day)
        )
        self.effective_date_edit.setCalendarPopup(True)
        self.cumulative_edit = QLineEdit(
            (
                f"{baseline.cumulative_man_day:.1f}"
                if baseline is not None
                else ""
            )
        )
        self.cumulative_edit.setPlaceholderText("예: 20.0")
        self.reason_edit = QLineEdit()
        self.reason_edit.setPlaceholderText("설정 또는 변경 사유를 입력해 주세요.")
        form.addRow("기준 종료일", self.effective_date_edit)
        form.addRow("초기 누적 공수", self.cumulative_edit)
        form.addRow("변경 사유", self.reason_edit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("저장")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict[str, object]:
        text = self.cumulative_edit.text().strip()
        try:
            cumulative = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError("초기 누적 공수를 숫자로 입력해 주세요.") from exc
        if not cumulative.is_finite() or cumulative < 0:
            raise ValueError("초기 누적 공수는 0 이상의 숫자여야 합니다.")
        if cumulative.as_tuple().exponent < -1:
            raise ValueError("초기 누적 공수는 소수점 첫째 자리까지 입력해 주세요.")
        reason = self.reason_edit.text().strip()
        if not reason:
            raise ValueError("누적 기준 변경 사유를 입력해 주세요.")
        selected = self.effective_date_edit.date()
        return {
            "effective_through_date": date(
                selected.year(), selected.month(), selected.day()
            ),
            "cumulative_man_day": cumulative.quantize(Decimal("0.1")),
            "resolution_note": reason,
        }

    def _accept(self) -> None:
        try:
            self.values()
        except ValueError as exc:
            QMessageBox.warning(self, "초기 누적 확인", str(exc))
            return
        self.accept()


class TrackingDashboardDialog(QDialog):
    """Read projections and route baseline mutations through application services."""

    def __init__(
        self,
        dashboard_service: TrackingDashboardService,
        work_report_service: WorkReportService,
        refresh_callback: Callable[[], None],
        parent: QWidget | None = None,
        *,
        completed_only: bool = False,
        final_preview: FinalReportPreview | None = None,
        preview_supplier: Callable[[], FinalReportPreview] | None = None,
    ) -> None:
        super().__init__(parent)
        self._dashboard_service = dashboard_service
        self._work_report_service = work_report_service
        self._refresh_callback = refresh_callback
        self._preview_supplier = preview_supplier
        self._completed_only = completed_only
        self._summaries: tuple[TrackingDashboardSummary, ...] = ()
        self.setWindowTitle(
            "완료 장비 목록" if completed_only else "수주 공수 대시보드"
        )
        self.resize(1450, 760)
        root_layout = QVBoxLayout(self)
        self.final_preview_view: FinalReportDialog | None = None
        if final_preview is not None and not completed_only:
            self.tabs = QTabWidget()
            dashboard_page = QWidget()
            layout = QVBoxLayout(dashboard_page)
            self.tabs.addTab(dashboard_page, "수주 공수 대시보드")
            self.final_preview_view = FinalReportDialog(final_preview, self)
            self.final_preview_view.setWindowFlags(Qt.WindowType.Widget)
            self.tabs.addTab(self.final_preview_view, "최종 표 미리보기")
            root_layout.addWidget(self.tabs)
        else:
            self.tabs = None
            layout = root_layout
        self.summary_table = _table(_SUMMARY_HEADERS)
        self.summary_table.itemSelectionChanged.connect(
            self._load_selected_details
        )
        self.summary_table.itemSelectionChanged.connect(self._load_start_date)
        layout.addWidget(self.summary_table)
        self.guidance_label = QLabel("Tracking No.를 선택해 상세 내역을 확인하세요.")
        self.guidance_label.setWordWrap(True)
        layout.addWidget(self.guidance_label)
        date_controls = QHBoxLayout()
        date_controls.addWidget(QLabel("작업 시작일"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.save_start_date_button = QPushButton("시작일 저장")
        self.save_start_date_button.clicked.connect(self._save_start_date)
        date_controls.addWidget(self.start_date_edit)
        date_controls.addWidget(self.save_start_date_button)
        date_controls.addStretch()
        layout.addLayout(date_controls)
        self.detail_table = _table(_DETAIL_HEADERS)
        layout.addWidget(self.detail_table)
        self.baseline_button = QPushButton("초기 누적 설정")
        self.baseline_button.clicked.connect(self._edit_baseline)
        layout.addWidget(self.baseline_button)
        self.complete_button = QPushButton("작업 완료")
        self.complete_button.clicked.connect(self._complete_selected)
        self.resume_button = QPushButton("작업 재개")
        self.resume_button.clicked.connect(self._resume_selected)
        self.resume_button.setVisible(completed_only)
        self.complete_button.setVisible(not completed_only)
        actions = QHBoxLayout()
        actions.addWidget(self.complete_button)
        actions.addWidget(self.resume_button)
        if not completed_only:
            self.completed_list_button = QPushButton("완료 장비 목록")
            self.completed_list_button.clicked.connect(self._open_completed_list)
            actions.addWidget(self.completed_list_button)
        actions.addStretch()
        layout.addLayout(actions)
        close_buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close
        )
        close_buttons.rejected.connect(self.reject)
        layout.addWidget(close_buttons)
        self.refresh()

    def refresh(self) -> None:
        selected = self._selected_tracking_no()
        self._summaries = tuple(
            self._dashboard_service.completed_summaries()
            if self._completed_only
            else self._dashboard_service.summaries()
        )
        self.summary_table.setRowCount(len(self._summaries))
        for row_index, summary in enumerate(self._summaries):
            values = (
                summary.tracking_no,
                _date_text(summary.latest_work_date),
                summary.vendor_name or "",
                summary.equipment_name or "",
                summary.business_team or "",
                _value_text(summary.latest_actual_headcount),
                _value_text(summary.latest_night_headcount),
                summary.latest_man_day_basis,
                _decimal_text(summary.latest_confirmed_daily_man_day),
                _decimal_text(summary.initial_cumulative_man_day),
                _decimal_text(summary.latest_reported_cumulative_man_day),
                _decimal_text(summary.latest_calculated_cumulative_man_day),
                _decimal_text(summary.latest_confirmed_cumulative_man_day),
                "확정 가능" if summary.can_confirm else "확인 필요",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if summary.blockers:
                    item.setBackground(_BLOCKING_BACKGROUND)
                    item.setForeground(_BLOCKING_FOREGROUND)
                    item.setToolTip(
                        "\n".join(blocker.message for blocker in summary.blockers)
                    )
                self.summary_table.setItem(row_index, column, item)
            self.summary_table.item(row_index, 0).setData(
                Qt.ItemDataRole.UserRole, summary.normalized_tracking_no
            )
            if selected == summary.normalized_tracking_no:
                self.summary_table.selectRow(row_index)
        if self._summaries and self.summary_table.currentRow() < 0:
            self.summary_table.selectRow(0)
        if not self._summaries:
            self.detail_table.setRowCount(0)
            self.guidance_label.setText("표시할 Tracking No. 집계가 없습니다.")
        self._load_start_date()

    def _selected_tracking_no(self) -> str | None:
        row = self.summary_table.currentRow()
        if row < 0:
            return None
        item = self.summary_table.item(row, 0)
        if item is None:
            return None
        return str(item.data(Qt.ItemDataRole.UserRole) or item.text())

    def _selected_summary(self) -> TrackingDashboardSummary | None:
        tracking_no = self._selected_tracking_no()
        return next(
            (
                summary
                for summary in self._summaries
                if summary.normalized_tracking_no == tracking_no
            ),
            None,
        )

    def _load_selected_details(self) -> None:
        summary = self._selected_summary()
        if summary is None:
            self.detail_table.setRowCount(0)
            return
        rows = self._dashboard_service.drill_down(
            summary.normalized_tracking_no
        )
        self.detail_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = _detail_values(row)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if row.issue_codes and not row.warning_confirmed:
                    item.setBackground(_BLOCKING_BACKGROUND)
                    item.setForeground(_BLOCKING_FOREGROUND)
                self.detail_table.setItem(row_index, column, item)
        if summary.blockers:
            self.guidance_label.setText(
                "수정 안내\n"
                + "\n".join(
                    f"• {blocker.message}" for blocker in summary.blockers
                )
            )
            self.guidance_label.setStyleSheet(
                "background:#ffebee;color:#7f0000;padding:8px;"
            )
        else:
            self.guidance_label.setText("현재 최종 표를 차단하는 문제가 없습니다.")
            self.guidance_label.setStyleSheet("")

    def _load_start_date(self) -> None:
        summary = self._selected_summary()
        if summary is None or summary.start_date is None:
            self.start_date_edit.setDate(QDate.currentDate())
            self.save_start_date_button.setEnabled(False)
            return
        self.start_date_edit.setDate(
            QDate(summary.start_date.year, summary.start_date.month, summary.start_date.day)
        )
        self.save_start_date_button.setEnabled(not self._completed_only)

    def _save_start_date(self) -> None:
        summary = self._selected_summary()
        if summary is None:
            return
        selected = self.start_date_edit.date()
        self._dashboard_service.set_start_date(
            summary.tracking_no, date(selected.year(), selected.month(), selected.day())
        )
        self.refresh()
        self._refresh_final_preview()
        self._refresh_callback()

    def _complete_selected(self) -> None:
        summary = self._selected_summary()
        if summary is None:
            return
        QMessageBox.information(
            self, "작업 완료 안내", "완료된 Tracking No.는 기본 대시보드에서 숨겨집니다."
        )
        if summary.blockers:
            QMessageBox.warning(
                self,
                "확인 전 경고",
                f"확정 전 확인 필요 항목이 {len(summary.blockers)}건 있습니다. 그래도 완료할 수 있습니다.",
            )
        answer = QMessageBox.question(
            self,
            "작업 완료 재확인",
            f"{summary.tracking_no} 작업을 완료 처리하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._dashboard_service.complete(summary.tracking_no)
        self.refresh()
        self._refresh_final_preview()
        self._refresh_callback()

    def _resume_selected(self) -> None:
        summary = self._selected_summary()
        if summary is None:
            return
        answer = QMessageBox.question(
            self,
            "작업 재개",
            f"{summary.tracking_no} 작업을 다시 대시보드에 표시하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._dashboard_service.resume(summary.tracking_no)
        self.refresh()
        self._refresh_final_preview()
        self._refresh_callback()

    def _open_completed_list(self) -> None:
        dialog = CompletedTrackingDialog(
            self._dashboard_service,
            self._work_report_service,
            self._refresh_callback,
            self,
        )
        dialog.exec()
        self.refresh()
        self._refresh_final_preview()

    def _edit_baseline(self) -> None:
        summary = self._selected_summary()
        if summary is None:
            QMessageBox.information(
                self, "Tracking No. 선택", "초기 누적을 설정할 항목을 선택해 주세요."
            )
            return
        details = self._dashboard_service.drill_down(
            summary.normalized_tracking_no
        )
        known_dates = [row.work_date for row in details if row.work_date]
        baseline = self._work_report_service.get_cumulative_baseline(
            summary.normalized_tracking_no
        )
        dialog = BaselineDialog(
            summary.tracking_no,
            earliest_work_date=min(known_dates) if known_dates else None,
            baseline=baseline,
            parent=self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            self._work_report_service.save_cumulative_baseline(
                tracking_no=summary.tracking_no,
                **dialog.values(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "초기 누적 저장 실패", str(exc))
            return
        self.refresh()
        self._refresh_final_preview()
        self._refresh_callback()

    def _refresh_final_preview(self) -> None:
        if (
            self.final_preview_view is not None
            and self._preview_supplier is not None
        ):
            self.final_preview_view.refresh_preview(self._preview_supplier())


def _table(headers: tuple[str, ...]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.ResizeToContents
    )
    table.horizontalHeader().setStretchLastSection(True)
    return table


def _detail_values(row: WorkReportRow) -> tuple[str, ...]:
    issues = "; ".join(
        f"{issue_title(issue)} — {issue_action(issue)}"
        for issue in row.issue_codes
    )
    return (
        str(row.row_id),
        _date_text(row.work_date),
        _value_text(row.actual_headcount),
        _value_text(row.night_headcount),
        row.per_person_display,
        _decimal_text(row.reported_daily_man_day),
        _decimal_text(row.calculated_daily_man_day),
        _decimal_text(row.confirmed_daily_man_day),
        _decimal_text(row.reported_cumulative_man_day),
        _decimal_text(row.calculated_cumulative_man_day),
        _decimal_text(row.confirmed_cumulative_man_day),
        "포함" if row.included else "제외",
        row.review_status.value,
        issues,
    )


def _date_text(value: date | None) -> str:
    return value.isoformat() if value is not None else "확인 필요"


def _value_text(value: object | None) -> str:
    return "" if value is None else str(value)


def _decimal_text(value: Decimal | None) -> str:
    return "" if value is None else f"{value:.1f}"


class CompletedTrackingDialog(TrackingDashboardDialog):
    """Completed Tracking-No list with the same drill-down and resume UI."""

    def __init__(
        self,
        dashboard_service: TrackingDashboardService,
        work_report_service: WorkReportService,
        refresh_callback: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            dashboard_service,
            work_report_service,
            refresh_callback,
            parent,
            completed_only=True,
        )
