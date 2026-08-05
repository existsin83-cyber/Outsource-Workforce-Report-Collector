"""Tracking-No dashboard widgets backed only by application services."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Callable, Protocol

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QBrush, QColor, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QMenu,
    QPushButton,
    QSplitter,
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
from outsource_mail_collector.domain.work_report import WorkReportIssueCode
from outsource_mail_collector.application.work_report_service import (
    WorkReportService,
)
from outsource_mail_collector.ui.final_report_dialog import FinalReportDialog
from outsource_mail_collector.ui.row_review_flow import review_single_row
from outsource_mail_collector.ui.work_report_guidance import (
    issue_action,
    issue_title,
)


_SUMMARY_HEADERS = (
    "행 번호",
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
    "행 번호",
    "작업일",
    "실제 작업인원",
    "야근 인원",
    "인당 공수",
    "메일 투입",
    "계산 투입",
    "확정 투입",
    "메일 누적",
    "포함",
    "검토 상태",
    "문제 및 조치",
)
_TRACKING_COLUMN = _SUMMARY_HEADERS.index("Tracking No.")
_STATUS_COLUMN = _SUMMARY_HEADERS.index("검증 상태")
_INITIAL_CUMULATIVE_COLUMN = _SUMMARY_HEADERS.index("초기 누적")
_CONFIRMED_CUMULATIVE_COLUMN = _SUMMARY_HEADERS.index("확정 누적")
_BLOCKING_BACKGROUND = QColor("#ffebee")
_BLOCKING_FOREGROUND = QColor("#7f0000")
_CURRENT_ROW_BACKGROUND = QColor("#1565c0")
_CURRENT_ROW_FOREGROUND = QColor("#ffffff")


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
            f"{baseline.cumulative_man_day:.1f}"
            if baseline is not None
            else "0.0"
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


class CumulativeConfirmDialog(QDialog):
    """Confirm one Tracking No.'s cumulative man-day (메일 누적 vs 계산 누적)."""

    def __init__(
        self,
        tracking_no: str,
        *,
        reported_cumulative: Decimal | None,
        calculated_cumulative: Decimal | None,
        confirmed_cumulative: Decimal | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("확정 누적 확인")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("Tracking No.", QLabel(tracking_no))
        self.reported_label = QLabel(_decimal_text(reported_cumulative) or "없음")
        self.calculated_label = QLabel(_decimal_text(calculated_cumulative) or "없음")
        form.addRow("메일 누적", self.reported_label)
        form.addRow("계산 누적", self.calculated_label)
        self.confirmed_edit = QLineEdit(
            _decimal_text(confirmed_cumulative)
            or _decimal_text(calculated_cumulative)
        )
        form.addRow("확정 누적", self.confirmed_edit)
        choice_layout = QHBoxLayout()
        mail_button = QPushButton("메일값 채택")
        calculated_button = QPushButton("계산값 채택")
        mail_button.clicked.connect(
            lambda: self._adopt(reported_cumulative)
        )
        calculated_button.clicked.connect(
            lambda: self._adopt(calculated_cumulative)
        )
        choice_layout.addWidget(mail_button)
        choice_layout.addWidget(calculated_button)
        form.addRow("불일치 빠른 선택", choice_layout)
        self.reason_edit = QLineEdit()
        self.reason_edit.setPlaceholderText("확정 근거 또는 확인 내용을 입력해 주세요.")
        form.addRow("확인 사유", self.reason_edit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("확정값 저장")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _adopt(self, value: Decimal | None) -> None:
        if value is not None:
            self.confirmed_edit.setText(_decimal_text(value))

    def values(self) -> dict[str, object]:
        text = self.confirmed_edit.text().strip()
        try:
            confirmed = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError("확정 누적을 숫자로 입력해 주세요.") from exc
        if not confirmed.is_finite() or confirmed < 0:
            raise ValueError("확정 누적은 0 이상의 숫자여야 합니다.")
        reason = self.reason_edit.text().strip()
        if not reason:
            raise ValueError("확인 사유를 입력해 주세요.")
        return {
            "confirmed_cumulative_man_day": confirmed.quantize(Decimal("0.1")),
            "resolution_note": reason,
        }

    def _accept(self) -> None:
        try:
            self.values()
        except ValueError as exc:
            QMessageBox.warning(self, "확정 누적 확인", str(exc))
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
        work_order_registration_callback: (
            Callable[[TrackingDashboardSummary], bool] | None
        ) = None,
    ) -> None:
        super().__init__(parent)
        self._dashboard_service = dashboard_service
        self._work_report_service = work_report_service
        self._refresh_callback = refresh_callback
        self._preview_supplier = preview_supplier
        self._work_order_registration_callback = work_order_registration_callback
        self._completed_only = completed_only
        self._sort_ascending = False
        self._summaries: tuple[TrackingDashboardSummary, ...] = ()
        self._detail_rows: tuple[WorkReportRow, ...] = ()
        self._summary_blocked: list[bool] = []
        self._detail_blocked: list[bool] = []
        self._active_target: str | None = None
        self._summary_edit_column: int = _INITIAL_CUMULATIVE_COLUMN
        self.setWindowTitle(
            "완료 장비 목록" if completed_only else "수주 공수 대시보드"
        )
        self.resize(1450, 900)
        self.setMinimumSize(900, 560)
        self.setSizeGripEnabled(True)
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
        self.summary_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.summary_table.itemSelectionChanged.connect(
            self._on_summary_selection_changed
        )
        self.summary_table.cellDoubleClicked.connect(
            self._handle_summary_double_click
        )
        self.summary_table.cellClicked.connect(self._handle_summary_click)
        self.summary_table.horizontalHeaderItem(
            _INITIAL_CUMULATIVE_COLUMN
        ).setToolTip(
            "초기 누적: 이 프로그램 사용 전에 이미 쌓여 있던 누적 공수입니다. "
            "기본값은 0이며, 셀을 더블클릭하거나 행을 선택 후 '선택 행 수정' "
            "버튼으로 수정할 수 있습니다."
        )
        self.summary_table.horizontalHeaderItem(
            _CONFIRMED_CUMULATIVE_COLUMN
        ).setToolTip(
            "확정 누적: 메일 누적과 계산 누적을 비교해 Excel에 반영할 누적 "
            "공수를 이 Tracking No.의 최신 행에 확정합니다. 셀을 더블클릭하거나 "
            "행을 선택 후 '선택 행 수정' 버튼으로 수정할 수 있습니다."
        )
        # 등록 건수가 늘어도 두 표가 서로를 짓누르지 않도록 사용자가 비율을 잡게 한다.
        self.split = QSplitter(Qt.Orientation.Vertical)
        self.split.addWidget(self.summary_table)
        detail_pane = QWidget()
        detail_layout = QVBoxLayout(detail_pane)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        self.split.addWidget(detail_pane)
        self.split.setStretchFactor(0, 3)
        self.split.setStretchFactor(1, 2)
        outer_layout = layout
        layout = detail_layout
        outer_layout.addWidget(self.split, 1)
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
        self.sort_ascending_button = QPushButton("작업일 오름차순")
        self.sort_ascending_button.clicked.connect(
            lambda _checked=False: self._set_date_sort(ascending=True)
        )
        self.sort_descending_button = QPushButton("작업일 내림차순")
        self.sort_descending_button.clicked.connect(
            lambda _checked=False: self._set_date_sort(ascending=False)
        )
        date_controls.addWidget(self.sort_ascending_button)
        date_controls.addWidget(self.sort_descending_button)
        date_controls.addStretch()
        layout.addLayout(date_controls)
        self.detail_table = _table(_DETAIL_HEADERS)
        self.detail_table.cellDoubleClicked.connect(
            self._handle_detail_double_click
        )
        self.detail_table.currentCellChanged.connect(
            lambda *_args: self._on_detail_current_changed()
        )
        layout.addWidget(self.detail_table)
        layout = outer_layout
        self.edit_button = QPushButton("선택 행 수정")
        self.edit_button.setToolTip(
            "상단 표에서 Tracking No.를 선택하면 초기 누적을, 하단 표에서 "
            "행을 선택하면 해당 행을 수정합니다."
        )
        self.edit_button.clicked.connect(self._edit_selected)
        layout.addWidget(self.edit_button)
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
        summaries = tuple(
            self._dashboard_service.completed_summaries()
            if self._completed_only
            else self._dashboard_service.summaries()
        )
        self._summaries = self._sort_summaries(summaries)
        signals_blocked = self.summary_table.blockSignals(True)
        try:
            self.summary_table.clearSelection()
            for row_index in range(self.summary_table.rowCount()):
                status_widget = self.summary_table.cellWidget(
                    row_index, _STATUS_COLUMN
                )
                if status_widget is not None:
                    self.summary_table.removeCellWidget(
                        row_index, _STATUS_COLUMN
                    )
                    status_widget.deleteLater()
            self.summary_table.setRowCount(len(self._summaries))
            for row_index, summary in enumerate(self._summaries):
                values = (
                    str(row_index + 1),
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
                            "\n".join(
                                blocker.message for blocker in summary.blockers
                            )
                        )
                    self.summary_table.setItem(row_index, column, item)
                if (
                    self._work_order_registration_callback is not None
                    and any(
                        blocker.code == "WORK_ORDER_UNREGISTERED"
                        for blocker in summary.blockers
                    )
                ):
                    button = QPushButton("수주 등록 이동")
                    button.setStyleSheet(
                        "QPushButton {background:#b71c1c;color:white;font-weight:700;"
                        "padding:4px 8px;border:1px solid #7f0000;border-radius:3px;}"
                        "QPushButton:hover {background:#7f0000;}"
                        "QPushButton:pressed {background:#4a0000;}"
                    )
                    button.clicked.connect(
                        lambda _checked=False, current=summary: self._request_work_order_registration(current)
                    )
                    self.summary_table.setCellWidget(
                        row_index, _STATUS_COLUMN, button
                    )
                self.summary_table.item(row_index, _TRACKING_COLUMN).setData(
                    Qt.ItemDataRole.UserRole, summary.normalized_tracking_no
                )
                if selected == summary.normalized_tracking_no:
                    self.summary_table.selectRow(row_index)
        finally:
            self.summary_table.blockSignals(signals_blocked)
        self._summary_blocked = [
            bool(summary.blockers) for summary in self._summaries
        ]
        self.summary_table.resizeColumnsToContents()
        _paint_current_row(self.summary_table, self._summary_blocked)
        if not self._summaries:
            self._detail_rows = ()
            self._detail_blocked = []
            self.detail_table.setRowCount(0)
            self.guidance_label.setText("표시할 Tracking No. 집계가 없습니다.")
        else:
            self._load_selected_details()
        self._load_start_date()
        self._update_edit_button_labels()

    def _on_summary_selection_changed(self) -> None:
        if self.summary_table.selectionModel().hasSelection():
            self._active_target = "summary"
        _paint_current_row(self.summary_table, self._summary_blocked)
        self._load_selected_details()
        self._load_start_date()
        self._update_edit_button_labels()

    def _on_detail_current_changed(self) -> None:
        if self.detail_table.currentRow() >= 0:
            self._active_target = "detail"
        self._repaint_detail_rows()

    def _handle_summary_click(self, _row: int, column: int) -> None:
        if column in (_INITIAL_CUMULATIVE_COLUMN, _CONFIRMED_CUMULATIVE_COLUMN):
            self._summary_edit_column = column

    def _handle_summary_double_click(self, _row: int, column: int) -> None:
        if column == _INITIAL_CUMULATIVE_COLUMN:
            self._active_target = "summary"
            self._summary_edit_column = column
            self._edit_baseline()
        elif column == _CONFIRMED_CUMULATIVE_COLUMN:
            self._active_target = "summary"
            self._summary_edit_column = column
            self._edit_confirmed_cumulative()

    def _handle_detail_double_click(self, row: int, _column: int) -> None:
        self._active_target = "detail"
        self._edit_detail_row(row)

    def _repaint_detail_rows(self) -> None:
        _paint_current_row(self.detail_table, self._detail_blocked)
        self._update_edit_button_labels()

    def _update_edit_button_labels(self) -> None:
        if self._active_target == "summary":
            summary = self._selected_summary()
            label = (
                "확정 누적"
                if self._summary_edit_column == _CONFIRMED_CUMULATIVE_COLUMN
                else "초기 누적"
            )
            self.edit_button.setText(
                f"선택 행 수정 ({label})"
                if summary is None
                else f"선택 행 수정 ({label}) — {summary.tracking_no}"
            )
            return
        if self._active_target == "detail":
            row_index = self.detail_table.currentRow()
            if 0 <= row_index < len(self._detail_rows):
                row = self._detail_rows[row_index]
                self.edit_button.setText(
                    f"선택 행 수정 — {row_index + 1}행 "
                    f"{_date_text(row.work_date)}"
                )
                return
        self.edit_button.setText("선택 행 수정 (행을 선택해 주세요)")

    def _edit_selected(self) -> None:
        if self._active_target == "summary":
            if self._summary_edit_column == _CONFIRMED_CUMULATIVE_COLUMN:
                self._edit_confirmed_cumulative()
            else:
                self._edit_baseline()
            return
        if self._active_target == "detail":
            self._edit_detail_row(self.detail_table.currentRow())
            return
        QMessageBox.information(self, "행 선택", "수정할 행을 선택해 주세요.")

    def _selected_tracking_no(self) -> str | None:
        if not self.summary_table.selectionModel().hasSelection():
            return None
        row = self.summary_table.currentRow()
        if row < 0:
            return None
        item = self.summary_table.item(row, _TRACKING_COLUMN)
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

    def _display_summary(self) -> TrackingDashboardSummary | None:
        summary = self._selected_summary()
        if summary is not None:
            return summary
        return self._summaries[0] if self._summaries else None

    def _load_selected_details(self) -> None:
        summary = self._display_summary()
        if summary is None:
            self._detail_rows = ()
            self._detail_blocked = []
            self.detail_table.setRowCount(0)
            self._update_edit_button_labels()
            return
        rows = self._dashboard_service.drill_down(
            summary.normalized_tracking_no
        )
        self._detail_rows = rows
        self._detail_blocked = [
            bool(row.issue_codes) and not row.warning_confirmed for row in rows
        ]
        detail_signals_blocked = self.detail_table.blockSignals(True)
        try:
            self.detail_table.setRowCount(len(rows))
            for row_index, row in enumerate(rows):
                values = _detail_values(row, row_index + 1)
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    self.detail_table.setItem(row_index, column, item)
        finally:
            self.detail_table.blockSignals(detail_signals_blocked)
        self.detail_table.resizeColumnsToContents()
        self._repaint_detail_rows()
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

    def _edit_detail_row(self, row_index: int) -> None:
        if row_index < 0 or row_index >= len(self._detail_rows):
            return
        row = self._detail_rows[row_index]
        if WorkReportIssueCode.DUPLICATE_UNRESOLVED in row.issue_codes:
            QMessageBox.information(
                self,
                "중복 행 확인 필요",
                "중복 후보 행은 초기화면(메일 검토) 표에서 함께 선택해 처리해 주세요.",
            )
            return
        if review_single_row(row, self._work_report_service, self):
            self.refresh()
            self._refresh_final_preview()
            self._refresh_callback()

    def _set_date_sort(self, *, ascending: bool) -> None:
        self._sort_ascending = ascending
        self.refresh()

    def _request_work_order_registration(
        self, summary: TrackingDashboardSummary
    ) -> None:
        callback = self._work_order_registration_callback
        if callback is None or not callback(summary):
            return
        self.refresh()
        self._refresh_final_preview()
        self._refresh_callback()

    def _sort_summaries(
        self,
        summaries: tuple[TrackingDashboardSummary, ...],
    ) -> tuple[TrackingDashboardSummary, ...]:
        def key(summary: TrackingDashboardSummary) -> tuple[bool, int, str]:
            work_date = summary.latest_work_date
            return (
                work_date is None,
                (
                    work_date.toordinal()
                    if self._sort_ascending
                    else -work_date.toordinal()
                )
                if work_date is not None
                else 0,
                summary.tracking_no,
            )

        return tuple(sorted(summaries, key=key))

    def _load_start_date(self) -> None:
        summary = self._display_summary()
        if summary is None or summary.start_date is None:
            self.start_date_edit.setDate(QDate.currentDate())
            self.save_start_date_button.setEnabled(False)
            return
        self.start_date_edit.setDate(
            QDate(summary.start_date.year, summary.start_date.month, summary.start_date.day)
        )
        # 저장은 실제로 Tracking No.를 선택했을 때만 허용한다(표시는 기본값을
        # 보여주되, 클릭 없이 저장되는 일이 없도록).
        self.save_start_date_button.setEnabled(
            not self._completed_only and self._selected_summary() is not None
        )

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

    def _edit_confirmed_cumulative(self) -> None:
        summary = self._selected_summary()
        if summary is None:
            QMessageBox.information(
                self, "Tracking No. 선택", "확정 누적을 설정할 항목을 선택해 주세요."
            )
            return
        dialog = CumulativeConfirmDialog(
            summary.tracking_no,
            reported_cumulative=summary.latest_reported_cumulative_man_day,
            calculated_cumulative=summary.latest_calculated_cumulative_man_day,
            confirmed_cumulative=summary.latest_confirmed_cumulative_man_day,
            parent=self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            self._work_report_service.confirm_series_cumulative(
                summary.tracking_no, **dialog.values()
            )
        except ValueError as exc:
            QMessageBox.warning(self, "확정 누적 저장 실패", str(exc))
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


class _CopyableTableWidget(QTableWidget):
    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.StandardKey.Copy):
            _copy_selected_cells(self)
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.RightButton:
            _show_copy_menu(self, event.position().toPoint())


def _table(headers: tuple[str, ...]) -> QTableWidget:
    table = _CopyableTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
    table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    table.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.Interactive
    )
    table.horizontalHeader().setStretchLastSection(True)
    # 행이 많아져도 컬럼이 내용만큼 무한히 넓어지지 않도록 상한을 둔다.
    table.horizontalHeader().setMaximumSectionSize(260)
    table.setHorizontalScrollMode(
        QAbstractItemView.ScrollMode.ScrollPerPixel
    )
    # ponytail: _paint_current_row resets non-current rows to QBrush() (palette
    # default), which is near-black in dark mode - give the Qt selection state
    # its own readable colors instead of relying on the palette.
    table.setStyleSheet(
        "QTableWidget::item:selected {background:#1565c0;color:#ffffff;}"
        "QTableWidget::item:selected:!active {background:#90caf9;color:#1a1a1a;}"
    )
    return table


def _paint_current_row(table: QTableWidget, blocked: list[bool]) -> None:
    """Make the row the action buttons target unmistakable.

    Cell selection stays per-cell (range copy depends on it), so the current
    row gets its own accent instead: it wins over the blocking colours while
    selected and is restored to them as soon as another row is selected.
    """

    current_row = table.currentRow()
    for row in range(table.rowCount()):
        highlighted = row == current_row
        row_blocked = blocked[row] if row < len(blocked) else False
        for column in range(table.columnCount()):
            item = table.item(row, column)
            if item is None:
                continue
            if highlighted:
                item.setBackground(_CURRENT_ROW_BACKGROUND)
                item.setForeground(_CURRENT_ROW_FOREGROUND)
            elif row_blocked:
                item.setBackground(_BLOCKING_BACKGROUND)
                item.setForeground(_BLOCKING_FOREGROUND)
            else:
                item.setBackground(QBrush())
                item.setForeground(QBrush())
            font = item.font()
            font.setBold(highlighted)
            item.setFont(font)


def _show_copy_menu(table: QTableWidget, position) -> None:
    menu = QMenu(table)
    copy_action = menu.addAction("복사")
    copy_action.setEnabled(bool(table.selectedIndexes()))
    copy_action.triggered.connect(lambda: _copy_selected_cells(table))
    menu.popup(table.viewport().mapToGlobal(position))


def _copy_selected_cells(table: QTableWidget) -> None:
    selected = table.selectedIndexes()
    if not selected:
        return
    selected_positions = {(index.row(), index.column()) for index in selected}
    row_numbers = [index.row() for index in selected]
    column_numbers = [index.column() for index in selected]
    rows = []
    for row in range(min(row_numbers), max(row_numbers) + 1):
        values = []
        for column in range(min(column_numbers), max(column_numbers) + 1):
            item = table.item(row, column)
            values.append(
                item.text() if (row, column) in selected_positions and item else ""
            )
        rows.append("\t".join(values))
    QApplication.clipboard().setText("\n".join(rows))


def _detail_values(
    row: WorkReportRow,
    display_row_number: int,
) -> tuple[str, ...]:
    issues = "; ".join(
        f"{issue_title(issue)} — {issue_action(issue)}"
        for issue in row.issue_codes
    )
    return (
        str(display_row_number),
        _date_text(row.work_date),
        _value_text(row.actual_headcount),
        _value_text(row.night_headcount),
        row.per_person_display,
        _decimal_text(row.reported_daily_man_day),
        _decimal_text(row.calculated_daily_man_day),
        _decimal_text(row.confirmed_daily_man_day),
        _decimal_text(row.reported_cumulative_man_day),
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
