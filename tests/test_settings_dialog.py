from __future__ import annotations

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
)

from outsource_mail_collector.application.settings_service import SettingsService
from outsource_mail_collector.infrastructure.db.repository import (
    DuplicateEntityError,
    SQLiteRepository,
)
from outsource_mail_collector.ui.settings_dialog import (
    IncompleteWorkOrderError,
    SettingsDialog,
    _is_checked,
)
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


def test_settings_dialog_saves_work_order_mapping(tmp_path):
    _app()
    repository = SQLiteRepository(tmp_path / "collector.db")
    vendor = repository.save_vendor(None, "협력사", [], True)
    dialog = SettingsDialog(SettingsService(repository, FakeOutlookAdapter()))

    row = dialog.add_work_order_row()
    dialog.work_order_table.setItem(row, 0, QTableWidgetItem("AB260101"))
    dialog.work_order_table.setItem(row, 1, QTableWidgetItem("장비 1"))
    dialog.work_order_table.cellWidget(row, 2).setCurrentIndex(0)
    dialog.work_order_table.cellWidget(row, 3).setCurrentText("PKG")

    dialog.save()

    mapping = repository.list_work_order_mappings()[0]
    assert mapping.normalized_tracking_no == "AB260101"
    assert mapping.vendor_id == vendor.vendor_id
    assert mapping.business_team == "PKG"


def test_settings_dialog_saves_new_vendor_and_mapping_in_one_save(tmp_path):
    _app()
    repository = SQLiteRepository(tmp_path / "collector.db")
    dialog = SettingsDialog(SettingsService(repository, FakeOutlookAdapter()))

    vendor_row = dialog.add_vendor_row()
    dialog.vendor_table.setItem(vendor_row, 0, QTableWidgetItem("신규 업체"))
    mapping_row = dialog.add_work_order_row()
    dialog.work_order_table.setItem(
        mapping_row, 0, QTableWidgetItem("AB260201")
    )
    dialog.work_order_table.setItem(mapping_row, 1, QTableWidgetItem("장비 2"))
    vendor_combo = dialog.work_order_table.cellWidget(mapping_row, 2)
    team_combo = dialog.work_order_table.cellWidget(mapping_row, 3)

    assert isinstance(vendor_combo, QComboBox)
    assert vendor_combo.findText("신규 업체") >= 0
    vendor_combo.setCurrentText("신규 업체")
    assert isinstance(team_combo, QComboBox)
    team_combo.setCurrentText("WA")

    dialog.save()

    vendor = repository.list_vendors()[0]
    mapping = repository.list_work_order_mappings()[0]
    assert vendor.canonical_name == "신규 업체"
    assert mapping.vendor_id == vendor.vendor_id
    assert mapping.business_team == "WA"


def test_incomplete_work_order_blocks_all_settings_mutation(tmp_path):
    _app()
    repository = SQLiteRepository(tmp_path / "collector.db")
    repository.set_setting("outlook_folder", "Inbox")
    dialog = SettingsDialog(SettingsService(repository, FakeOutlookAdapter()))

    dialog.set_general_values("Inbox/Updated", "", "")
    vendor_row = dialog.add_vendor_row()
    dialog.vendor_table.setItem(vendor_row, 0, QTableWidgetItem("신규 업체"))
    mapping_row = dialog.add_work_order_row()
    dialog.work_order_table.setItem(
        mapping_row, 0, QTableWidgetItem("AB260202")
    )

    with pytest.raises(IncompleteWorkOrderError) as exc_info:
        dialog.save()

    assert exc_info.value.rows == [mapping_row]
    assert repository.get_setting("outlook_folder") == "Inbox"
    assert repository.list_vendors() == []
    assert repository.list_work_order_mappings() == []


def test_is_checked_returns_false_until_checkbox_is_installed(tmp_path):
    _app()
    dialog = SettingsDialog(
        SettingsService(
            SQLiteRepository(tmp_path / "collector.db"), FakeOutlookAdapter()
        )
    )
    dialog.vendor_table.insertRow(0)

    assert _is_checked(dialog.vendor_table, 0, 2) is False


def test_add_vendor_row_does_not_refresh_before_checkbox_is_installed(tmp_path):
    _app()
    dialog = SettingsDialog(
        SettingsService(
            SQLiteRepository(tmp_path / "collector.db"), FakeOutlookAdapter()
        )
    )
    refresh_checkbox_states: list[bool] = []

    def record_refresh() -> None:
        refresh_checkbox_states.append(
            isinstance(dialog.vendor_table.cellWidget(0, 2), QCheckBox)
        )

    dialog._refresh_work_order_vendor_combos = record_refresh
    dialog.add_vendor_row()

    assert refresh_checkbox_states == [True]


def test_incomplete_work_order_message_names_missing_vendor(tmp_path, monkeypatch):
    _app()
    repository = SQLiteRepository(tmp_path / "collector.db")
    dialog = SettingsDialog(SettingsService(repository, FakeOutlookAdapter()))
    mapping_row = dialog.add_work_order_row()
    dialog.work_order_table.setItem(
        mapping_row, 0, QTableWidgetItem("AB260203")
    )
    dialog.work_order_table.setItem(mapping_row, 1, QTableWidgetItem("장비 3"))
    dialog.work_order_table.cellWidget(mapping_row, 3).setCurrentText("PKG")
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(message),
    )

    dialog._save_and_accept()

    assert len(warnings) == 1
    assert "1행: 업체가 선택되지 않았습니다." in warnings[0]
    assert dialog.result() != dialog.DialogCode.Accepted


def test_settings_tables_use_visible_active_checkboxes(tmp_path):
    _app()
    dialog = SettingsDialog(
        SettingsService(
            SQLiteRepository(tmp_path / "collector.db"), FakeOutlookAdapter()
        )
    )

    employee_row = dialog.add_employee_row()
    vendor_row = dialog.add_vendor_row()
    mapping_row = dialog.add_work_order_row()

    for table, row, column in (
        (dialog.employee_table, employee_row, 3),
        (dialog.vendor_table, vendor_row, 2),
        (dialog.work_order_table, mapping_row, 4),
    ):
        checkbox = table.cellWidget(row, column)
        assert isinstance(checkbox, QCheckBox)
        assert checkbox.text() == "활성"
        assert checkbox.minimumWidth() >= 56
        assert checkbox.isChecked()
        checkbox.setChecked(False)
        assert not checkbox.isChecked()


def test_add_buttons_create_rows_with_embedded_controls(tmp_path):
    _app()
    dialog = SettingsDialog(
        SettingsService(
            SQLiteRepository(tmp_path / "collector.db"), FakeOutlookAdapter()
        )
    )
    buttons = {button.text(): button for button in dialog.findChildren(QPushButton)}

    buttons["담당자 추가"].click()
    buttons["업체 추가"].click()
    buttons["수주 추가"].click()

    assert isinstance(dialog.employee_table.cellWidget(0, 3), QCheckBox)
    assert isinstance(dialog.vendor_table.cellWidget(0, 2), QCheckBox)
    assert isinstance(dialog.work_order_table.cellWidget(0, 2), QComboBox)
    assert isinstance(dialog.work_order_table.cellWidget(0, 3), QComboBox)
    assert isinstance(dialog.work_order_table.cellWidget(0, 4), QCheckBox)


def test_business_team_combo_has_allowed_values_and_restores_saved_value(tmp_path):
    _app()
    repository = SQLiteRepository(tmp_path / "collector.db")
    vendor = repository.save_vendor(None, "협력사", [], True)
    repository.save_work_order_mapping(
        None, "AB260101", "장비 1", vendor.vendor_id, "광학영업", True
    )

    dialog = SettingsDialog(SettingsService(repository, FakeOutlookAdapter()))
    combo = dialog.work_order_table.cellWidget(0, 3)

    assert isinstance(combo, QComboBox)
    vendor_combo = dialog.work_order_table.cellWidget(0, 2)
    assert isinstance(vendor_combo, QComboBox)
    assert vendor_combo.minimumWidth() >= 140
    assert combo.minimumWidth() >= 120
    assert dialog.work_order_table.rowHeight(0) >= 28
    assert [combo.itemText(index) for index in range(combo.count())] == [
        "MARKER",
        "CSM",
        "GROOVING",
        "WA",
        "PKG",
        "PCB",
        "DISPLAY",
        "MACRO",
        "광학영업",
        "LDM",
    ]
    assert combo.currentText() == "광학영업"


def test_settings_dialog_preserves_inactive_mapping_vendor_on_save(tmp_path):
    _app()
    repository = SQLiteRepository(tmp_path / "collector.db")
    inactive_vendor = repository.save_vendor(None, "기존 업체", [], True)
    mapping = repository.save_work_order_mapping(
        None, "AB260101", "장비 1", inactive_vendor.vendor_id, "PKG", True
    )
    repository.save_vendor(inactive_vendor.vendor_id, "기존 업체", [], False)
    repository.save_vendor(None, "활성 업체", [], True)

    dialog = SettingsDialog(SettingsService(repository, FakeOutlookAdapter()))

    vendor_combo = dialog.work_order_table.cellWidget(0, 2)
    assert vendor_combo.currentData() == inactive_vendor.vendor_id
    assert "비활성" in vendor_combo.currentText()

    dialog.save()

    assert repository.list_work_order_mappings()[0].vendor_id == mapping.vendor_id
    assert (
        dialog.work_order_table.cellWidget(0, 2).currentText()
        == "기존 업체 (비활성)"
    )


def test_settings_dialog_handles_deleting_referenced_vendor_without_mutation(
    tmp_path, monkeypatch
):
    _app()
    repository = SQLiteRepository(tmp_path / "collector.db")
    vendor = repository.save_vendor(None, "협력사", [], True)
    mapping = repository.save_work_order_mapping(
        None, "AB260101", "장비 1", vendor.vendor_id, "PKG", True
    )
    dialog = SettingsDialog(SettingsService(repository, FakeOutlookAdapter()))
    dialog.vendor_table.selectRow(0)
    dialog._remove_selected_vendor()
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda _parent, _title, message: warnings.append(message)
    )

    dialog._save_and_accept()

    assert warnings
    assert repository.list_work_order_mappings() == [mapping]
    assert dialog._deleted_vendor_ids == {vendor.vendor_id}
    assert dialog._deleted_work_order_ids == set()


def test_settings_dialog_rejects_new_mapping_to_vendor_deleted_in_same_save(
    tmp_path, monkeypatch
):
    _app()
    repository = SQLiteRepository(tmp_path / "collector.db")
    vendor = repository.save_vendor(None, "협력사", [], True)
    mapping = repository.save_work_order_mapping(
        None, "AB260101", "장비 1", vendor.vendor_id, "PKG", True
    )
    dialog = SettingsDialog(SettingsService(repository, FakeOutlookAdapter()))
    dialog.work_order_table.selectRow(0)
    dialog._remove_selected_work_order()
    dialog.vendor_table.selectRow(0)
    dialog._remove_selected_vendor()
    row = dialog.add_work_order_row()
    dialog.work_order_table.setItem(row, 0, QTableWidgetItem("AB260102"))
    dialog.work_order_table.setItem(row, 1, QTableWidgetItem("장비 2"))
    dialog.work_order_table.cellWidget(row, 3).setCurrentText("PKG")
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda _parent, _title, message: warnings.append(message)
    )

    dialog._save_and_accept()

    assert warnings
    assert repository.list_vendors() == [vendor]
    assert repository.list_work_order_mappings() == [mapping]
    assert dialog._deleted_vendor_ids == {vendor.vendor_id}
    assert dialog._deleted_work_order_ids == {mapping.mapping_id}


def test_settings_dialog_rejects_retarget_to_vendor_deleted_in_same_save(
    tmp_path, monkeypatch
):
    _app()
    repository = SQLiteRepository(tmp_path / "collector.db")
    deleted_vendor = repository.save_vendor(None, "삭제 업체", [], True)
    retained_vendor = repository.save_vendor(None, "유지 업체", [], True)
    deleted_mapping = repository.save_work_order_mapping(
        None, "AB260101", "장비 1", deleted_vendor.vendor_id, "PKG", True
    )
    retained_mapping = repository.save_work_order_mapping(
        None, "AB260102", "장비 2", retained_vendor.vendor_id, "PKG", True
    )
    dialog = SettingsDialog(SettingsService(repository, FakeOutlookAdapter()))
    dialog.work_order_table.selectRow(0)
    dialog._remove_selected_work_order()
    dialog.vendor_table.selectRow(0)
    dialog._remove_selected_vendor()
    vendor_combo = dialog.work_order_table.cellWidget(0, 2)
    vendor_combo.setCurrentIndex(vendor_combo.findData(deleted_vendor.vendor_id))
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda _parent, _title, message: warnings.append(message)
    )

    dialog._save_and_accept()

    assert warnings
    assert repository.list_vendors() == [deleted_vendor, retained_vendor]
    assert repository.list_work_order_mappings() == [
        deleted_mapping,
        retained_mapping,
    ]
    assert dialog._deleted_vendor_ids == {deleted_vendor.vendor_id}
    assert dialog._deleted_work_order_ids == {deleted_mapping.mapping_id}


def test_settings_save_rolls_back_pending_deletions_and_settings_on_late_invalid(
    tmp_path,
):
    _app()
    repository = SQLiteRepository(tmp_path / "collector.db")
    repository.set_setting("outlook_folder", "Inbox")
    vendor = repository.save_vendor(None, "협력사", [], True)
    mapping = repository.save_work_order_mapping(
        None, "AB260101", "장비 1", vendor.vendor_id, "PKG", True
    )
    dialog = SettingsDialog(SettingsService(repository, FakeOutlookAdapter()))
    dialog.set_general_values("Inbox/변경", "", "외주인원_원본")
    dialog.work_order_table.selectRow(0)
    dialog._remove_selected_work_order()
    invalid_row = dialog.add_work_order_row()
    dialog.work_order_table.setItem(
        invalid_row, 0, QTableWidgetItem("AB260102")
    )
    dialog.work_order_table.setItem(invalid_row, 1, QTableWidgetItem("장비 2"))

    with pytest.raises(ValueError):
        dialog.save()

    assert repository.get_setting("outlook_folder") == "Inbox"
    assert repository.list_vendors() == [vendor]
    assert repository.list_work_order_mappings() == [mapping]


def test_settings_save_rolls_back_late_duplicate_and_pending_vendor_delete(
    tmp_path,
):
    _app()
    repository = SQLiteRepository(tmp_path / "collector.db")
    repository.set_setting("outlook_folder", "Inbox")
    deleted_vendor = repository.save_vendor(None, "삭제 업체", [], True)
    retained_vendor = repository.save_vendor(None, "유지 업체", [], True)
    deleted_mapping = repository.save_work_order_mapping(
        None, "AB260101", "장비 1", deleted_vendor.vendor_id, "OLD", True
    )
    retained_mapping = repository.save_work_order_mapping(
        None, "AB260102", "장비 2", retained_vendor.vendor_id, "KEEP", True
    )
    dialog = SettingsDialog(SettingsService(repository, FakeOutlookAdapter()))
    dialog.set_general_values("Inbox/변경", "", "외주인원_원본")
    dialog.work_order_table.selectRow(0)
    dialog._remove_selected_work_order()
    dialog.vendor_table.selectRow(0)
    dialog._remove_selected_vendor()
    duplicate_row = dialog.add_work_order_row()
    dialog.work_order_table.setItem(
        duplicate_row, 0, QTableWidgetItem(" ab 260102 ")
    )
    dialog.work_order_table.setItem(
        duplicate_row, 1, QTableWidgetItem("장비 중복")
    )
    dialog.work_order_table.cellWidget(duplicate_row, 3).setCurrentText("PKG")
    vendor_combo = dialog.work_order_table.cellWidget(duplicate_row, 2)
    vendor_combo.setCurrentIndex(vendor_combo.findData(retained_vendor.vendor_id))

    with pytest.raises(DuplicateEntityError):
        dialog.save()

    assert repository.get_setting("outlook_folder") == "Inbox"
    assert repository.list_vendors() == [deleted_vendor, retained_vendor]
    assert repository.list_work_order_mappings() == [
        deleted_mapping,
        retained_mapping,
    ]


def test_settings_save_can_delete_last_mapping_and_vendor_together(tmp_path):
    _app()
    repository = SQLiteRepository(tmp_path / "collector.db")
    vendor = repository.save_vendor(None, "협력사", [], True)
    repository.save_work_order_mapping(
        None, "AB260101", "장비 1", vendor.vendor_id, "PKG", True
    )
    dialog = SettingsDialog(SettingsService(repository, FakeOutlookAdapter()))
    dialog.work_order_table.selectRow(0)
    dialog._remove_selected_work_order()
    dialog.vendor_table.selectRow(0)
    dialog._remove_selected_vendor()

    dialog.save()

    assert repository.list_work_order_mappings() == []
    assert repository.list_vendors() == []


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
