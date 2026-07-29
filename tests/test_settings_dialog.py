from __future__ import annotations

from PySide6.QtWidgets import QApplication, QTableWidgetItem

from outsource_mail_collector.application.settings_service import SettingsService
from outsource_mail_collector.infrastructure.db.repository import SQLiteRepository
from outsource_mail_collector.ui.settings_dialog import SettingsDialog
from outsource_mail_collector.ui.workers import FolderLoadWorker


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_settings_dialog_round_trips_general_settings(tmp_path):
    _app()
    repository = SQLiteRepository(tmp_path / "collector.db")
    dialog = SettingsDialog(SettingsService(repository, FakeOutlookAdapter()))

    dialog.set_general_values(
        "Inbox/전장기술팀",
        "C:/reports/source.xlsx",
        "외주인원_원본",
    )
    dialog.save()

    assert repository.get_setting("outlook_folder") == "Inbox/전장기술팀"
    assert repository.get_setting("excel_workbook_path") == "C:/reports/source.xlsx"
    assert repository.get_setting("excel_sheet_name") == "외주인원_원본"


def test_settings_dialog_saves_employee_and_vendor_rows(tmp_path):
    _app()
    repository = SQLiteRepository(tmp_path / "collector.db")
    dialog = SettingsDialog(SettingsService(repository, FakeOutlookAdapter()))

    employee_row = dialog.add_employee_row()
    dialog.employee_table.setItem(employee_row, 0, QTableWidgetItem("홍길동"))
    dialog.employee_table.setItem(employee_row, 1, QTableWidgetItem("USER@EXAMPLE.COM"))
    dialog.employee_table.setItem(employee_row, 2, QTableWidgetItem("길동, 홍 대리"))

    vendor_row = dialog.add_vendor_row()
    dialog.vendor_table.setItem(vendor_row, 0, QTableWidgetItem("협력사A"))
    dialog.vendor_table.setItem(vendor_row, 1, QTableWidgetItem("A사, 협력 A"))

    dialog.save()

    employee = repository.list_employees()[0]
    vendor = repository.list_vendors()[0]
    assert employee.email == "user@example.com"
    assert employee.aliases == ("길동", "홍 대리")
    assert vendor.canonical_name == "협력사A"
    assert vendor.aliases == ("A사", "협력 A")


def test_vendor_rows_keep_insertion_order_for_report_sorting(tmp_path):
    _app()
    repository = SQLiteRepository(tmp_path / "collector.db")
    dialog = SettingsDialog(SettingsService(repository, FakeOutlookAdapter()))
    for name in ("업체B", "업체A"):
        row = dialog.add_vendor_row()
        dialog.vendor_table.setItem(row, 0, QTableWidgetItem(name))

    dialog.save()
    first_order = [
        (vendor.canonical_name, vendor.sort_order)
        for vendor in repository.list_vendors()
    ]
    dialog.save()

    assert [name for name, _order in first_order] == ["업체B", "업체A"]
    assert [order for _name, order in first_order] == sorted(
        order for _name, order in first_order
    )
    assert [
        vendor.canonical_name for vendor in repository.list_vendors()
    ] == ["업체B", "업체A"]


def test_folder_worker_emits_real_adapter_folder_results(tmp_path):
    _app()
    worker = FolderLoadWorker(
        SettingsService(
            SQLiteRepository(tmp_path / "collector.db"),
            FakeOutlookAdapter(["Inbox", "Inbox/전장기술팀"]),
        )
    )
    emitted: list[list[str]] = []
    worker.loaded.connect(emitted.append)

    worker.run()

    assert emitted == [["Inbox", "Inbox/전장기술팀"]]


def test_apply_folder_values_preserves_current_selection(tmp_path):
    _app()
    repository = SQLiteRepository(tmp_path / "collector.db")
    dialog = SettingsDialog(SettingsService(repository, FakeOutlookAdapter()))
    dialog.set_general_values("Inbox/전장기술팀", "", "외주인원_원본")

    dialog.apply_folder_values(["Inbox", "Inbox/전장기술팀", "Inbox/기타"])

    assert dialog.folder_values() == [
        "Inbox",
        "Inbox/전장기술팀",
        "Inbox/기타",
    ]
    assert dialog.folder_combo.currentText() == "Inbox/전장기술팀"


class FakeOutlookAdapter:
    def __init__(self, folders: list[str] | None = None) -> None:
        self.folders = folders or ["Inbox"]

    def connect(self) -> None:
        return None

    def list_folders(self) -> list[str]:
        return list(self.folders)
