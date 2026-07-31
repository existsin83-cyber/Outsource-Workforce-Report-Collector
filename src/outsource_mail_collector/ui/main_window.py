"""Main window for collecting, reviewing, and copying work-report tables."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

try:
    import pywintypes
except ImportError:  # pragma: no cover - Outlook support is Windows-only.
    _OUTLOOK_ERRORS = (OSError, RuntimeError, ValueError)
else:
    _OUTLOOK_ERRORS = (OSError, RuntimeError, ValueError, pywintypes.com_error)

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from outsource_mail_collector.application.container import ApplicationServices
from outsource_mail_collector.application.models import (
    CollectionWorkflowResult,
    WorkReportRow,
)
from outsource_mail_collector.domain.work_report import WorkReportIssueCode
from outsource_mail_collector.ui.clipboard import ClipboardWriter
from outsource_mail_collector.ui.deleted_rows_dialog import DeletedRowsDialog
from outsource_mail_collector.ui.final_report_dialog import FinalReportDialog
from outsource_mail_collector.ui.manual_row_dialog import ManualRowDialog
from outsource_mail_collector.ui.problem_review_dialog import (
    ProblemReviewDialog,
)
from outsource_mail_collector.ui.review_grid import ReviewGridWidget
from outsource_mail_collector.ui.settings_dialog import SettingsDialog
from outsource_mail_collector.ui.tracking_dashboard_dialog import (
    TrackingDashboardDialog,
)
from outsource_mail_collector.ui.workers import CollectionWorker


class MainWindow(QMainWindow):
    def __init__(self, services: ApplicationServices) -> None:
        super().__init__()
        self._services = services
        self._clipboard_writer = ClipboardWriter()
        self._collection_worker: CollectionWorker | None = None
        self._rows: tuple[WorkReportRow, ...] = ()
        self._last_missing_names: tuple[str, ...] = ()
        self._last_target_count = 0
        self._last_received_count = 0

        self.setWindowTitle("Outsource Mail Collector")
        self.resize(1500, 820)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self._build_toolbar())
        layout.addWidget(self._build_summary())
        self.missing_banner = QLabel()
        self.missing_banner.setStyleSheet(
            "background-color:#fff3e0;color:#e65100;padding:8px;"
        )
        self.missing_banner.hide()
        layout.addWidget(self.missing_banner)
        self.review_grid = ReviewGridWidget()
        self.review_grid.original_requested.connect(self._open_original)
        self.review_grid.inclusion_requested.connect(self._set_row_included)
        self.review_grid.review_requested.connect(self._review_problem_row)
        layout.addWidget(self.review_grid)
        layout.addWidget(self._build_action_bar())
        self.setCentralWidget(central)
        self._reload_rows()

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        today = QDate.currentDate()
        yesterday = today.addDays(-1)
        self.received_date_edit = QDateEdit(today)
        self.received_date_edit.setCalendarPopup(True)
        self.work_date_from_edit = QDateEdit(yesterday)
        self.work_date_from_edit.setCalendarPopup(True)
        self.work_date_to_edit = QDateEdit(yesterday)
        self.work_date_to_edit.setCalendarPopup(True)
        self.folder_combo = QComboBox()
        self.folder_combo.setEditable(True)
        folder = self._services.settings_service.get_setting(
            "outlook_folder", "Inbox"
        )
        self.folder_combo.addItem(folder or "Inbox")
        self.fetch_button = QPushButton("메일 가져오기")
        self.fetch_button.clicked.connect(self.start_collection)
        self.settings_button = QPushButton("⚙ 설정")
        self.settings_button.clicked.connect(self._open_settings)
        self.progress_label = QLabel()
        for label, widget in (
            ("메일 수신일", self.received_date_edit),
            ("작업일 시작", self.work_date_from_edit),
            ("작업일 종료", self.work_date_to_edit),
            ("폴더", self.folder_combo),
        ):
            layout.addWidget(QLabel(label))
            layout.addWidget(widget)
        layout.addWidget(self.fetch_button)
        layout.addWidget(self.progress_label)
        layout.addStretch()
        layout.addWidget(self.settings_button)
        return bar

    def _build_summary(self) -> QWidget:
        self._summary_labels: dict[str, QLabel] = {}
        summary = QWidget()
        layout = QHBoxLayout(summary)
        for title in (
            "대상 인원",
            "수신 메일",
            "취합 행",
            "검토 필요",
            "차단 오류",
            "미보고",
        ):
            tile, value = self._stat_tile(title)
            self._summary_labels[title] = value
            layout.addWidget(tile)
        return summary

    @staticmethod
    def _stat_tile(title: str) -> tuple[QFrame, QLabel]:
        tile = QFrame()
        tile.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(tile)
        value = QLabel("0")
        value.setStyleSheet("font-size:20px;font-weight:700;")
        layout.addWidget(value)
        layout.addWidget(QLabel(title))
        return tile, value

    def _build_action_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        self.manual_button = QPushButton("수동 행 추가")
        self.manual_button.clicked.connect(self._add_manual_row)
        self.delete_button = QPushButton("선택 삭제")
        self.delete_button.clicked.connect(self._delete_selected_rows)
        self.recovery_button = QPushButton("삭제 항목 복구")
        self.recovery_button.clicked.connect(self._open_deleted_rows)
        self.dashboard_button = QPushButton("수주 공수 대시보드")
        self.dashboard_button.clicked.connect(self._open_tracking_dashboard)
        self.preview_button = QPushButton("최종 표 미리보기")
        self.preview_button.clicked.connect(self._open_final_preview)
        self.excel_button = QPushButton("Excel 반영")
        self.excel_button.clicked.connect(self._show_excel_notice)
        layout.addWidget(self.manual_button)
        layout.addWidget(self.delete_button)
        layout.addWidget(self.recovery_button)
        layout.addWidget(self.dashboard_button)
        layout.addStretch()
        layout.addWidget(self.preview_button)
        layout.addWidget(self.excel_button)
        return bar

    def start_collection(self) -> None:
        if self._collection_worker and self._collection_worker.isRunning():
            return
        date_from, date_to = self._selected_work_range()
        if date_from > date_to:
            QMessageBox.warning(
                self, "날짜 확인", "작업일 시작은 종료보다 늦을 수 없습니다."
            )
            return
        self.fetch_button.setEnabled(False)
        self.progress_label.setText("메일 분석 중…")
        worker = CollectionWorker(
            self._qdate_to_date(self.received_date_edit.date()),
            date_from,
            date_to,
            self.folder_combo.currentText().strip() or "Inbox",
            self._services.mail_collection_service,
            self._services.extraction_orchestrator,
            self._services.work_report_service,
        )
        worker.completed.connect(self.apply_collection_result)
        worker.failed.connect(self._collection_failed)
        worker.finished.connect(self._collection_finished)
        self._collection_worker = worker
        worker.start()

    def apply_collection_result(self, result: CollectionWorkflowResult) -> None:
        self._last_target_count = result.collection.target_employee_count
        self._last_received_count = result.collection.received_mail_count
        self._last_missing_names = tuple(
            employee.name for employee in result.collection.missing_employees
        )
        self._apply_rows(result.work_report_rows)
        errors = result.collection.errors + result.extraction.errors
        if errors:
            QMessageBox.warning(
                self,
                "일부 메일 처리 실패",
                "\n".join(error.message for error in errors),
            )

    def _collection_failed(self, message: str) -> None:
        QMessageBox.critical(
            self,
            "메일 가져오기 실패",
            message or "Outlook 메일을 가져올 수 없습니다.",
        )

    def _collection_finished(self) -> None:
        self.fetch_button.setEnabled(True)
        self.progress_label.clear()
        if self._collection_worker is not None:
            self._collection_worker.deleteLater()
            self._collection_worker = None

    def _reload_rows(self) -> None:
        date_from, date_to = self._selected_work_range()
        result = self._services.work_report_service.list_rows(
            date_from, date_to
        )
        self._last_target_count = len(
            self._services.settings_service.list_employees(active_only=True)
        )
        self._last_received_count = 0
        self._last_missing_names = ()
        self._apply_rows(result.rows)

    def _apply_rows(self, rows: tuple[WorkReportRow, ...]) -> None:
        self._rows = tuple(rows)
        self.review_grid.set_rows(list(rows))
        warning_count = sum(
            bool(row.issue_codes) and row.included for row in rows
        )
        blocking_codes = {
            WorkReportIssueCode.DATE_UNRESOLVED,
            WorkReportIssueCode.CUMULATIVE_BASELINE_REQUIRED,
            WorkReportIssueCode.DUPLICATE_UNRESOLVED,
            WorkReportIssueCode.SERIES_KEY_MISSING,
            WorkReportIssueCode.INVALID_VALUE,
        }
        blocking_count = sum(
            bool(set(row.issue_codes) & blocking_codes) and row.included
            for row in rows
        )
        values = {
            "대상 인원": self._last_target_count,
            "수신 메일": self._last_received_count,
            "취합 행": len(rows),
            "검토 필요": warning_count,
            "차단 오류": blocking_count,
            "미보고": len(self._last_missing_names),
        }
        for title, value in values.items():
            self._summary_labels[title].setText(str(value))
        if self._last_missing_names:
            self.missing_banner.setText(
                f"⚠ 미보고자 {len(self._last_missing_names)}명: "
                + ", ".join(self._last_missing_names)
            )
            self.missing_banner.show()
        else:
            self.missing_banner.hide()

    def _add_manual_row(self) -> None:
        dialog = ManualRowDialog(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            self._services.work_report_service.add_manual_row(
                **dialog.values()
            )
        except ValueError as exc:
            QMessageBox.warning(self, "수동 행 추가 실패", str(exc))
            return
        self._reload_rows()

    def _review_problem_row(self, row_id: int) -> None:
        row = next((item for item in self._rows if item.row_id == row_id), None)
        if row is None:
            return
        if WorkReportIssueCode.DUPLICATE_UNRESOLVED in row.issue_codes:
            selected = self.review_grid.checked_row_ids()
            if row_id not in selected:
                selected.append(row_id)
            if len(selected) < 2:
                QMessageBox.information(
                    self, "중복 행 선택", "중복 후보 행을 함께 선택해 주세요."
                )
                return
            dialog = ProblemReviewDialog(duplicate_mode=True, parent=self)
            if dialog.exec() == dialog.DialogCode.Accepted:
                values = dialog.values()
                self._services.work_report_service.resolve_duplicate(
                    selected,
                    str(values["duplicate_decision"]),
                    resolution_note=str(values["resolution_note"]),
                )
                self._reload_rows()
            return
        dialog_arguments: dict[str, object] = {
            "reported_daily": row.reported_daily_man_day,
            "calculated_daily": row.calculated_daily_man_day,
            "reported_cumulative": row.reported_cumulative_man_day,
            "calculated_cumulative": row.calculated_cumulative_man_day,
            "confirmed_daily": _confirmed_candidate(
                row.confirmed_daily_man_day,
                row.reported_daily_man_day,
                row.calculated_daily_man_day,
            ),
            "confirmed_cumulative": _confirmed_candidate(
                row.confirmed_cumulative_man_day,
                row.reported_cumulative_man_day,
                row.calculated_cumulative_man_day,
            ),
            "issue_codes": row.issue_codes,
            "parent": self,
        }
        night_issue_codes = {
            WorkReportIssueCode.NIGHT_HEADCOUNT_UNRESOLVED,
            WorkReportIssueCode.NIGHT_HEADCOUNT_INVALID,
        }
        if set(row.issue_codes) & night_issue_codes:
            dialog_arguments["actual_headcount"] = row.actual_headcount
            dialog_arguments["night_headcount"] = row.night_headcount
            dialog_arguments["headcount_correction"] = True
        dialog = ProblemReviewDialog(**dialog_arguments)
        if dialog.exec() == dialog.DialogCode.Accepted:
            try:
                values = dialog.values()
                resolution_note = str(values["resolution_note"])
                headcount_changes = {
                    field_name: values[field_name]
                    for field_name in (
                        "actual_headcount",
                        "night_headcount",
                    )
                    if field_name in values
                }
                if headcount_changes:
                    self._services.work_report_service.update_row(
                        row_id,
                        headcount_changes,
                        resolution_note=resolution_note,
                    )
                self._services.work_report_service.confirm_row(
                    row_id,
                    confirmed_daily_man_day=values[
                        "confirmed_daily_man_day"
                    ],
                    confirmed_cumulative_man_day=values[
                        "confirmed_cumulative_man_day"
                    ],
                    resolution_note=resolution_note,
                )
            except ValueError as exc:
                QMessageBox.warning(self, "행 확정 실패", str(exc))
            self._reload_rows()

    def _set_row_included(self, row_id: int, included: bool) -> None:
        try:
            self._services.work_report_service.set_included(
                row_id,
                included,
                resolution_note=(
                    "사용자 반영 제외 취소"
                    if included
                    else "사용자 반영 제외"
                ),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "포함 상태 변경 실패", str(exc))
            return
        self._reload_rows()

    def _delete_selected_rows(self) -> None:
        row_ids = self.review_grid.checked_row_ids()
        if not row_ids:
            QMessageBox.information(
                self, "삭제 행 선택", "삭제할 행을 선택해 주세요."
            )
            return
        answer = QMessageBox.question(
            self,
            "선택 행 삭제",
            "선택한 행을 애플리케이션에서 삭제하시겠습니까?\n"
            "Outlook 메일은 삭제하거나 변경하지 않습니다.\n"
            "삭제한 행은 대시보드와 최종 표에서 빠지며 나중에 복구할 수 있습니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._services.work_report_service.soft_delete_rows(
                row_ids, resolution_note="사용자 선택 삭제"
            )
        except ValueError as exc:
            QMessageBox.warning(self, "선택 삭제 실패", str(exc))
            return
        self._reload_rows()

    def _open_deleted_rows(self) -> None:
        result = self._services.work_report_service.list_rows(
            date.min, date.max, include_deleted=True
        )
        deleted_rows = tuple(
            row for row in result.rows if row.deleted_at is not None
        )
        if not deleted_rows:
            QMessageBox.information(
                self, "삭제 항목 복구", "복구할 삭제 항목이 없습니다."
            )
            return
        dialog = DeletedRowsDialog(deleted_rows, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        row_ids = dialog.selected_row_ids()
        if not row_ids:
            QMessageBox.information(
                self, "복구 항목 선택", "복구할 행을 선택해 주세요."
            )
            return
        resolution_note = dialog.resolution_note().strip()
        if not resolution_note:
            QMessageBox.warning(
                self, "복구 사유 필요", "복구 사유를 입력해 주세요."
            )
            return
        answer = QMessageBox.question(
            self,
            "선택 행 복구",
            "선택한 행을 복구하시겠습니까?\n"
            "복구 후 누적 공수는 다시 계산됩니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._services.work_report_service.restore_rows(
                row_ids, resolution_note=resolution_note
            )
        except ValueError as exc:
            QMessageBox.warning(self, "삭제 항목 복구 실패", str(exc))
            return
        self._reload_rows()

    def _open_tracking_dashboard(self) -> None:
        dialog = TrackingDashboardDialog(
            self._services.tracking_dashboard_service,
            self._services.work_report_service,
            self._reload_rows,
            self,
        )
        dialog.exec()

    def _open_final_preview(self) -> None:
        date_from, date_to = self._selected_work_range()
        preview = self._services.final_report_service.preview(
            date_from, date_to
        )
        dialog = FinalReportDialog(preview, self)
        dialog.confirm_requested.connect(
            lambda: self._confirm_final(dialog, date_from, date_to)
        )
        dialog.copy_requested.connect(lambda: self._copy_final(dialog))
        dialog.exec()

    def _confirm_final(
        self, dialog: FinalReportDialog, date_from: date, date_to: date
    ) -> None:
        try:
            snapshot = self._services.final_report_service.confirm(
                date_from, date_to
            )
        except ValueError as exc:
            QMessageBox.warning(self, "최종 확정 실패", str(exc))
            dialog.invalidate_confirmation()
            return
        dialog.set_confirmed_report(
            snapshot, self._services.report_renderer.render(snapshot)
        )

    def _copy_final(self, dialog: FinalReportDialog) -> None:
        if dialog.snapshot is None or dialog.rendered_report is None:
            return
        try:
            self._clipboard_writer.write(dialog.rendered_report)
        except RuntimeError as exc:
            QMessageBox.warning(self, "표 복사 실패", str(exc))
            return
        updated = self._services.final_report_service.mark_copied(
            dialog.snapshot.report_id
        )
        dialog.set_confirmed_report(updated, dialog.rendered_report)

    def _open_original(self, mail_entry_id: str) -> None:
        if not mail_entry_id:
            return
        try:
            self._services.review_service.open_original(mail_entry_id)
        except _OUTLOOK_ERRORS as exc:
            QMessageBox.warning(self, "원본 메일 열기 실패", str(exc))

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self._services.settings_service, self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            folder = self._services.settings_service.get_setting(
                "outlook_folder", "Inbox"
            )
            self.folder_combo.setCurrentText(folder or "Inbox")
            self._services.work_report_service.refresh_work_order_mappings()
            self._reload_rows()

    def _show_excel_notice(self) -> None:
        QMessageBox.information(
            self,
            "Excel 연동 준비 중",
            "실제 Excel 연동은 아직 준비되지 않았습니다.\n"
            "실 워크북 확보 후 사용할 수 있습니다.",
        )

    def summary_value(self, title: str) -> str:
        return self._summary_labels[title].text()

    def _selected_work_range(self) -> tuple[date, date]:
        return (
            self._qdate_to_date(self.work_date_from_edit.date()),
            self._qdate_to_date(self.work_date_to_edit.date()),
        )

    @staticmethod
    def _qdate_to_date(value: QDate) -> date:
        return date(value.year(), value.month(), value.day())


def _confirmed_candidate(
    confirmed: Decimal | None,
    reported: Decimal | None,
    calculated: Decimal | None,
) -> Decimal | None:
    if confirmed is not None:
        return confirmed
    if (
        reported is not None
        and calculated is not None
        and reported == calculated
    ):
        return reported
    return None
