"""Main review window connected to application services."""

from __future__ import annotations

from datetime import date

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
from outsource_mail_collector.application.errors import InvalidReviewValueError
from outsource_mail_collector.application.models import (
    CollectionWorkflowResult,
    ReviewRecord,
)
from outsource_mail_collector.domain.models import ReviewStatus
from outsource_mail_collector.ui.review_grid import ReviewGridWidget, ReviewRow
from outsource_mail_collector.ui.settings_dialog import SettingsDialog
from outsource_mail_collector.ui.workers import CollectionWorker


class MainWindow(QMainWindow):
    def __init__(self, services: ApplicationServices) -> None:
        super().__init__()
        self._services = services
        self._collection_worker: CollectionWorker | None = None
        self._last_missing_names: tuple[str, ...] = ()
        self._last_target_count = 0
        self._last_received_count = 0

        self.setWindowTitle("Outsource Mail Collector")
        self.resize(1280, 720)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self._build_toolbar())
        layout.addWidget(self._build_summary())
        self.missing_banner = QLabel()
        self.missing_banner.setStyleSheet(
            "background-color: #fff3e0; color: #e65100; "
            "padding: 8px; border-radius: 4px;"
        )
        self.missing_banner.hide()
        layout.addWidget(self.missing_banner)

        self.review_grid = ReviewGridWidget()
        self.review_grid.edit_requested.connect(self._update_review_field)
        self.review_grid.original_requested.connect(self._open_original)
        self.review_grid.exclude_requested.connect(
            lambda record_id: self._set_status(
                [record_id], ReviewStatus.EXCLUDED
            )
        )
        layout.addWidget(self.review_grid)
        layout.addWidget(self._build_action_bar())
        self.setCentralWidget(central)
        self._reload_records()

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
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
        self.progress_label = QLabel("")
        layout.addWidget(QLabel("조회 날짜"))
        layout.addWidget(self.date_edit)
        layout.addWidget(QLabel("폴더"))
        layout.addWidget(self.folder_combo)
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
            "정상",
            "검토 필요",
            "미보고",
            "중복 의심",
        ):
            tile, value_label = self._stat_tile(title)
            self._summary_labels[title] = value_label
            layout.addWidget(tile)
        return summary

    @staticmethod
    def _stat_tile(title: str) -> tuple[QFrame, QLabel]:
        tile = QFrame()
        tile.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(tile)
        value_label = QLabel("0")
        value_label.setStyleSheet("font-size: 20px; font-weight: 700;")
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #666;")
        layout.addWidget(value_label)
        layout.addWidget(title_label)
        return tile, value_label

    def _build_action_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.addStretch()
        self.exclude_button = QPushButton("선택 항목 반영 제외")
        self.review_button = QPushButton("검토 완료 처리")
        self.excel_button = QPushButton("Excel 반영")
        self.log_button = QPushButton("처리 로그 보기")
        self.exclude_button.clicked.connect(
            lambda: self._set_status(
                self.review_grid.checked_record_ids(), ReviewStatus.EXCLUDED
            )
        )
        self.review_button.clicked.connect(
            lambda: self._set_status(
                self.review_grid.checked_record_ids(), ReviewStatus.REVIEWED
            )
        )
        self.excel_button.clicked.connect(self._show_excel_notice)
        self.log_button.clicked.connect(
            lambda: QMessageBox.information(
                self, "처리 로그", "처리 로그 화면은 후속 작업에서 제공됩니다."
            )
        )
        for button in (
            self.exclude_button,
            self.review_button,
            self.excel_button,
            self.log_button,
        ):
            layout.addWidget(button)
        return bar

    def start_collection(self) -> None:
        if self._collection_worker is not None and self._collection_worker.isRunning():
            return
        self.fetch_button.setEnabled(False)
        self.progress_label.setText("메일 분석 중…")
        worker = CollectionWorker(
            self._selected_date(),
            self.folder_combo.currentText().strip() or "Inbox",
            self._services.mail_collection_service,
            self._services.extraction_orchestrator,
            self._services.review_service,
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
        self._apply_records(result.records)
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

    def _reload_records(self) -> None:
        records = tuple(
            self._services.review_service.list_records(self._selected_date())
        )
        self._last_target_count = len(
            self._services.settings_service.list_employees(active_only=True)
        )
        self._apply_records(records)

    def _apply_records(self, records: tuple[ReviewRecord, ...] | list[ReviewRecord]) -> None:
        self.review_grid.set_rows([_to_review_row(record) for record in records])
        normal = sum(
            record.review_status is ReviewStatus.NORMAL for record in records
        )
        review_needed = sum(
            record.review_status
            not in {
                ReviewStatus.NORMAL,
                ReviewStatus.REVIEWED,
                ReviewStatus.EXCLUDED,
            }
            for record in records
        )
        duplicate = sum(
            record.review_status is ReviewStatus.DUPLICATE_SUSPECTED
            for record in records
        )
        values = {
            "대상 인원": self._last_target_count,
            "수신 메일": self._last_received_count,
            "정상": normal,
            "검토 필요": review_needed,
            "미보고": len(self._last_missing_names),
            "중복 의심": duplicate,
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
            self.missing_banner.clear()
            self.missing_banner.hide()

    def _update_review_field(
        self, record_id: int, field_name: str, value: str
    ) -> None:
        try:
            self._services.review_service.update_field(
                record_id, field_name, value
            )
        except InvalidReviewValueError as exc:
            QMessageBox.warning(self, "입력값 확인", str(exc))
        self._reload_records()

    def _set_status(
        self, record_ids: list[int], status: ReviewStatus
    ) -> None:
        if not record_ids:
            QMessageBox.information(self, "선택 필요", "처리할 행을 선택해 주세요.")
            return
        self._services.review_service.set_status(record_ids, status)
        self._reload_records()

    def _open_original(self, mail_entry_id: str) -> None:
        try:
            self._services.review_service.open_original(mail_entry_id)
        except (OSError, RuntimeError, ValueError) as exc:
            QMessageBox.warning(self, "원본 메일 열기 실패", str(exc))

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self._services.settings_service, self)
        if dialog.exec() == SettingsDialog.DialogCode.Accepted:
            folder = self._services.settings_service.get_setting(
                "outlook_folder", "Inbox"
            )
            self.folder_combo.setCurrentText(folder or "Inbox")
            self._reload_records()

    def _show_excel_notice(self) -> None:
        QMessageBox.information(
            self,
            "Excel 연동 준비 중",
            "실제 Excel 연동은 아직 준비되지 않았습니다.\n"
            "실 워크북 확보 후 사용할 수 있습니다.",
        )

    def summary_value(self, title: str) -> str:
        return self._summary_labels[title].text()

    def _selected_date(self) -> date:
        selected = self.date_edit.date()
        return date(selected.year(), selected.month(), selected.day())


def _to_review_row(record: ReviewRecord) -> ReviewRow:
    return ReviewRow(
        report_date=record.report_date.isoformat(),
        author=record.sender_name,
        equipment_name=record.equipment_name or "",
        tracking_no=record.tracking_no or "",
        vendor_name=record.vendor_name or "",
        actual_headcount=_display_number(record.actual_headcount),
        daily_man_day=_display_number(record.daily_man_day),
        cumulative_man_day=_display_number(record.cumulative_man_day),
        confidence=record.confidence,
        status=record.review_status,
        record_id=record.record_id,
        mail_entry_id=record.mail_entry_id,
    )


def _display_number(value: float | None) -> str:
    if value is None:
        return ""
    return str(value)
