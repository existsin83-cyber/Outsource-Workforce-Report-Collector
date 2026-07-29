"""Settings dialog for employees, vendors, Outlook folder, and Excel target."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from outsource_mail_collector.application.settings_service import SettingsService
from outsource_mail_collector.infrastructure.db.repository import (
    DuplicateEntityError,
    Employee,
    normalize_tracking_no,
    Vendor,
    WorkOrderMapping,
)
from outsource_mail_collector.ui.workers import FolderLoadWorker


class SettingsDialog(QDialog):
    def __init__(
        self,
        settings_service: SettingsService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings_service
        self._deleted_employee_ids: set[int] = set()
        self._deleted_vendor_ids: set[int] = set()
        self._deleted_work_order_ids: set[int] = set()
        self._folder_worker: FolderLoadWorker | None = None

        self.setWindowTitle("설정")
        self.resize(760, 520)
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(), "일반")
        tabs.addTab(self._build_employee_tab(), "담당자")
        tabs.addTab(self._build_vendor_tab(), "업체")
        tabs.addTab(self._build_work_order_tab(), "수주 마스터")
        root.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._load()

    def _build_general_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)

        folder_row = QWidget()
        folder_layout = QHBoxLayout(folder_row)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        self.folder_combo = QComboBox()
        self.folder_combo.setEditable(True)
        refresh_button = QPushButton("폴더 새로고침")
        refresh_button.clicked.connect(self.refresh_folders)
        folder_layout.addWidget(self.folder_combo)
        folder_layout.addWidget(refresh_button)

        excel_row = QWidget()
        excel_layout = QHBoxLayout(excel_row)
        excel_layout.setContentsMargins(0, 0, 0, 0)
        self.excel_path_edit = QLineEdit()
        browse_button = QPushButton("찾아보기")
        browse_button.clicked.connect(self._browse_excel)
        excel_layout.addWidget(self.excel_path_edit)
        excel_layout.addWidget(browse_button)

        self.sheet_name_edit = QLineEdit()
        form.addRow("Outlook 폴더", folder_row)
        form.addRow("Excel 파일", excel_row)
        form.addRow("원본 시트명", self.sheet_name_edit)
        form.addRow(
            "",
            QLabel("Excel 경로와 시트명은 저장되지만 실제 반영 기능은 아직 연결되지 않습니다."),
        )
        return tab

    def _build_employee_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.employee_table = QTableWidget(0, 4)
        self.employee_table.setHorizontalHeaderLabels(
            ["이름", "이메일", "별칭(쉼표 구분)", "활성"]
        )
        self.employee_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        layout.addWidget(self.employee_table)
        controls = QHBoxLayout()
        add_button = QPushButton("담당자 추가")
        remove_button = QPushButton("선택 삭제")
        add_button.clicked.connect(self.add_employee_row)
        remove_button.clicked.connect(self._remove_selected_employee)
        controls.addWidget(add_button)
        controls.addWidget(remove_button)
        controls.addStretch()
        layout.addLayout(controls)
        return tab

    def _build_vendor_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.vendor_table = QTableWidget(0, 3)
        self.vendor_table.setHorizontalHeaderLabels(
            ["표준 업체명", "별칭(쉼표 구분)", "활성"]
        )
        self.vendor_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        layout.addWidget(self.vendor_table)
        controls = QHBoxLayout()
        add_button = QPushButton("업체 추가")
        remove_button = QPushButton("선택 삭제")
        add_button.clicked.connect(self.add_vendor_row)
        remove_button.clicked.connect(self._remove_selected_vendor)
        controls.addWidget(add_button)
        controls.addWidget(remove_button)
        controls.addStretch()
        layout.addLayout(controls)
        return tab

    def _build_work_order_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.work_order_table = QTableWidget(0, 5)
        self.work_order_table.setHorizontalHeaderLabels(
            ["수주번호", "장비명", "업체", "사업팀", "활성"]
        )
        self.work_order_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        layout.addWidget(self.work_order_table)
        controls = QHBoxLayout()
        add_button = QPushButton("수주 추가")
        remove_button = QPushButton("선택 삭제")
        add_button.clicked.connect(self.add_work_order_row)
        remove_button.clicked.connect(self._remove_selected_work_order)
        controls.addWidget(add_button)
        controls.addWidget(remove_button)
        controls.addStretch()
        layout.addLayout(controls)
        return tab

    def _load(self) -> None:
        self.set_general_values(
            self._settings.get_setting("outlook_folder", "Inbox") or "Inbox",
            self._settings.get_setting("excel_workbook_path", "") or "",
            self._settings.get_setting("excel_sheet_name", "외주인원_원본")
            or "외주인원_원본",
        )
        for employee in self._settings.list_employees():
            self.add_employee_row(employee)
        for vendor in self._settings.list_vendors():
            self.add_vendor_row(vendor)
        for mapping in self._settings.list_work_order_mappings():
            self.add_work_order_row(mapping)

    def set_general_values(
        self, folder_path: str, excel_path: str, sheet_name: str
    ) -> None:
        self.folder_combo.setCurrentText(folder_path)
        self.excel_path_edit.setText(excel_path)
        self.sheet_name_edit.setText(sheet_name)

    def folder_values(self) -> list[str]:
        return [self.folder_combo.itemText(index) for index in range(self.folder_combo.count())]

    def apply_folder_values(self, folders: list[str]) -> None:
        selected = self.folder_combo.currentText()
        self.folder_combo.clear()
        self.folder_combo.addItems(folders)
        if selected:
            self.folder_combo.setCurrentText(selected)

    def refresh_folders(self) -> None:
        if self._folder_worker is not None and self._folder_worker.isRunning():
            return
        worker = FolderLoadWorker(self._settings)
        worker.loaded.connect(self.apply_folder_values)
        worker.failed.connect(self._show_folder_error)
        worker.finished.connect(self._folder_worker_finished)
        self._folder_worker = worker
        worker.start()

    def _folder_worker_finished(self) -> None:
        if self._folder_worker is not None:
            self._folder_worker.deleteLater()
            self._folder_worker = None

    def _show_folder_error(self, message: str) -> None:
        QMessageBox.warning(
            self,
            "Outlook 폴더 조회 실패",
            message or "Outlook 폴더 목록을 읽을 수 없습니다.",
        )

    def add_employee_row(self, employee: Employee | None = None) -> int:
        row = self.employee_table.rowCount()
        self.employee_table.insertRow(row)
        values = (
            employee.name if employee else "",
            employee.email if employee else "",
            ", ".join(employee.aliases) if employee else "",
        )
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column == 0 and employee is not None:
                item.setData(Qt.ItemDataRole.UserRole, employee.employee_id)
            self.employee_table.setItem(row, column, item)
        self.employee_table.setItem(
            row, 3, _check_item(employee.active if employee else True)
        )
        return row

    def add_vendor_row(self, vendor: Vendor | None = None) -> int:
        row = self.vendor_table.rowCount()
        self.vendor_table.insertRow(row)
        values = (
            vendor.canonical_name if vendor else "",
            ", ".join(vendor.aliases) if vendor else "",
        )
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column == 0 and vendor is not None:
                item.setData(Qt.ItemDataRole.UserRole, vendor.vendor_id)
            self.vendor_table.setItem(row, column, item)
        self.vendor_table.setItem(row, 2, _check_item(vendor.active if vendor else True))
        return row

    def add_work_order_row(
        self, mapping: WorkOrderMapping | None = None
    ) -> int:
        row = self.work_order_table.rowCount()
        self.work_order_table.insertRow(row)
        values = (
            mapping.tracking_no if mapping else "",
            mapping.equipment_name if mapping else "",
            mapping.business_team if mapping else "",
        )
        for column, value in ((0, values[0]), (1, values[1]), (3, values[2])):
            item = QTableWidgetItem(value)
            if column == 0 and mapping is not None:
                item.setData(Qt.ItemDataRole.UserRole, mapping.mapping_id)
            self.work_order_table.setItem(row, column, item)

        vendor_combo = QComboBox()
        for vendor in self._settings.list_vendors(active_only=True):
            vendor_combo.addItem(vendor.canonical_name, vendor.vendor_id)
        if mapping is not None:
            vendor_index = vendor_combo.findData(mapping.vendor_id)
            if vendor_index < 0:
                vendor_combo.addItem(
                    f"{mapping.vendor_name} (비활성)", mapping.vendor_id
                )
                vendor_index = vendor_combo.count() - 1
            vendor_combo.setCurrentIndex(vendor_index)
        self.work_order_table.setCellWidget(row, 2, vendor_combo)
        self.work_order_table.setItem(
            row, 4, _check_item(mapping.active if mapping else True)
        )
        return row

    def _remove_selected_employee(self) -> None:
        self._remove_selected(
            self.employee_table, self._deleted_employee_ids, id_column=0
        )

    def _remove_selected_vendor(self) -> None:
        self._remove_selected(
            self.vendor_table, self._deleted_vendor_ids, id_column=0
        )

    def _remove_selected_work_order(self) -> None:
        self._remove_selected(
            self.work_order_table, self._deleted_work_order_ids, id_column=0
        )

    @staticmethod
    def _remove_selected(
        table: QTableWidget, deleted_ids: set[int], id_column: int
    ) -> None:
        rows = sorted({index.row() for index in table.selectedIndexes()}, reverse=True)
        for row in rows:
            item = table.item(row, id_column)
            entity_id = item.data(Qt.ItemDataRole.UserRole) if item else None
            if entity_id is not None:
                deleted_ids.add(int(entity_id))
            table.removeRow(row)

    def save(self) -> None:
        self._validate_all_rows()
        folder_path = self.folder_combo.currentText().strip() or "Inbox"
        sheet_name = self.sheet_name_edit.text().strip() or "외주인원_원본"
        saved_ids: list[tuple[QTableWidgetItem, int]] = []
        with self._settings.transaction():
            self._settings.set_setting("outlook_folder", folder_path)
            self._settings.set_setting(
                "excel_workbook_path", self.excel_path_edit.text().strip()
            )
            self._settings.set_setting("excel_sheet_name", sheet_name)

            for mapping_id in self._deleted_work_order_ids:
                self._settings.delete_work_order_mapping(mapping_id)
            for employee_id in self._deleted_employee_ids:
                self._settings.delete_employee(employee_id)
            for vendor_id in self._deleted_vendor_ids:
                self._settings.delete_vendor(vendor_id)
            self._save_employee_rows(saved_ids)
            self._save_vendor_rows(saved_ids)
            self._save_work_order_rows(saved_ids)
        for item, entity_id in saved_ids:
            item.setData(Qt.ItemDataRole.UserRole, entity_id)
        self._deleted_employee_ids.clear()
        self._deleted_vendor_ids.clear()
        self._deleted_work_order_ids.clear()

    def _validate_all_rows(self) -> None:
        self._validate_vendor_deletions()
        seen_emails: set[str] = set()
        for row in range(self.employee_table.rowCount()):
            name_item = self.employee_table.item(row, 0)
            email_item = self.employee_table.item(row, 1)
            name = name_item.text().strip() if name_item else ""
            email = email_item.text().strip().lower() if email_item else ""
            if not name and not email:
                continue
            if not name or not email:
                raise ValueError("직원 이름과 이메일은 필수입니다.")
            if email in seen_emails:
                raise DuplicateEntityError("이미 등록된 직원 이메일입니다.")
            seen_emails.add(email)

        seen_vendors: set[str] = set()
        for row in range(self.vendor_table.rowCount()):
            name_item = self.vendor_table.item(row, 0)
            name = name_item.text().strip() if name_item else ""
            if not name:
                continue
            if name in seen_vendors:
                raise DuplicateEntityError("이미 등록된 업체명입니다.")
            seen_vendors.add(name)

        active_tracking_numbers: set[str] = set()
        for row in range(self.work_order_table.rowCount()):
            tracking_item = self.work_order_table.item(row, 0)
            equipment_item = self.work_order_table.item(row, 1)
            vendor_combo = self.work_order_table.cellWidget(row, 2)
            team_item = self.work_order_table.item(row, 3)
            active_item = self.work_order_table.item(row, 4)
            tracking_no = tracking_item.text().strip() if tracking_item else ""
            equipment_name = equipment_item.text().strip() if equipment_item else ""
            business_team = team_item.text().strip() if team_item else ""
            vendor_id = (
                vendor_combo.currentData()
                if isinstance(vendor_combo, QComboBox)
                else None
            )
            if not tracking_no:
                raise ValueError("수주번호는 필수입니다.")
            if not equipment_name:
                raise ValueError("장비명은 필수입니다.")
            if vendor_id is None:
                raise ValueError("업체를 선택하세요.")
            if not business_team:
                raise ValueError("사업팀은 필수입니다.")
            if active_item is None:
                raise ValueError("수주 활성 상태가 필요합니다.")
            if active_item.checkState() is Qt.CheckState.Checked:
                normalized = normalize_tracking_no(tracking_no)
                if normalized in active_tracking_numbers:
                    raise DuplicateEntityError(
                        "이미 등록된 활성 수주번호입니다."
                    )
                active_tracking_numbers.add(normalized)

    def _validate_vendor_deletions(self) -> None:
        for row in range(self.work_order_table.rowCount()):
            vendor_combo = self.work_order_table.cellWidget(row, 2)
            vendor_id = (
                vendor_combo.currentData()
                if isinstance(vendor_combo, QComboBox)
                else None
            )
            if vendor_id in self._deleted_vendor_ids:
                raise ValueError(
                    "수주 마스터에서 사용 중인 업체는 삭제할 수 없습니다."
                )

    def _save_employee_rows(
        self, saved_ids: list[tuple[QTableWidgetItem, int]]
    ) -> None:
        for row in range(self.employee_table.rowCount()):
            name_item = self.employee_table.item(row, 0)
            email_item = self.employee_table.item(row, 1)
            alias_item = self.employee_table.item(row, 2)
            active_item = self.employee_table.item(row, 3)
            name = name_item.text().strip() if name_item else ""
            email = email_item.text().strip() if email_item else ""
            if not name and not email:
                continue
            employee_id = (
                name_item.data(Qt.ItemDataRole.UserRole) if name_item else None
            )
            saved = self._settings.save_employee(
                int(employee_id) if employee_id is not None else None,
                name,
                email,
                _split_aliases(alias_item.text() if alias_item else ""),
                active_item.checkState() is Qt.CheckState.Checked,
            )
            if name_item is not None:
                saved_ids.append((name_item, saved.employee_id))

    def _save_vendor_rows(
        self, saved_ids: list[tuple[QTableWidgetItem, int]]
    ) -> None:
        for row in range(self.vendor_table.rowCount()):
            name_item = self.vendor_table.item(row, 0)
            alias_item = self.vendor_table.item(row, 1)
            active_item = self.vendor_table.item(row, 2)
            name = name_item.text().strip() if name_item else ""
            if not name:
                continue
            vendor_id = (
                name_item.data(Qt.ItemDataRole.UserRole) if name_item else None
            )
            saved = self._settings.save_vendor(
                int(vendor_id) if vendor_id is not None else None,
                name,
                _split_aliases(alias_item.text() if alias_item else ""),
                active_item.checkState() is Qt.CheckState.Checked,
            )
            if name_item is not None:
                saved_ids.append((name_item, saved.vendor_id))

    def _save_work_order_rows(
        self, saved_ids: list[tuple[QTableWidgetItem, int]]
    ) -> None:
        for row in range(self.work_order_table.rowCount()):
            tracking_item = self.work_order_table.item(row, 0)
            equipment_item = self.work_order_table.item(row, 1)
            vendor_combo = self.work_order_table.cellWidget(row, 2)
            team_item = self.work_order_table.item(row, 3)
            active_item = self.work_order_table.item(row, 4)
            tracking_no = tracking_item.text().strip() if tracking_item else ""
            equipment_name = equipment_item.text().strip() if equipment_item else ""
            business_team = team_item.text().strip() if team_item else ""
            vendor_id = (
                vendor_combo.currentData()
                if isinstance(vendor_combo, QComboBox)
                else None
            )
            if not tracking_no:
                raise ValueError("수주번호는 필수입니다.")
            if not equipment_name:
                raise ValueError("장비명은 필수입니다.")
            if vendor_id is None:
                raise ValueError("업체를 선택하세요.")
            if not business_team:
                raise ValueError("사업팀은 필수입니다.")
            mapping_id = (
                tracking_item.data(Qt.ItemDataRole.UserRole)
                if tracking_item
                else None
            )
            saved = self._settings.save_work_order_mapping(
                int(mapping_id) if mapping_id is not None else None,
                tracking_no,
                equipment_name,
                int(vendor_id),
                business_team,
                active_item.checkState() is Qt.CheckState.Checked,
            )
            if tracking_item is not None:
                saved_ids.append((tracking_item, saved.mapping_id))

    def _save_and_accept(self) -> None:
        try:
            self.save()
        except (DuplicateEntityError, ValueError) as exc:
            QMessageBox.warning(self, "설정 저장 실패", str(exc))
            return
        self.accept()

    def _browse_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Excel 파일 선택",
            self.excel_path_edit.text(),
            "Excel 통합 문서 (*.xlsx *.xlsm *.xls)",
        )
        if path:
            self.excel_path_edit.setText(path)


def _check_item(checked: bool) -> QTableWidgetItem:
    item = QTableWidgetItem()
    item.setFlags(
        Qt.ItemFlag.ItemIsEnabled
        | Qt.ItemFlag.ItemIsSelectable
        | Qt.ItemFlag.ItemIsUserCheckable
    )
    item.setCheckState(
        Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
    )
    return item


def _split_aliases(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]
