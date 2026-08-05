from __future__ import annotations

from datetime import date
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QToolButton
import pywintypes

import outsource_mail_collector.ui.main_window as main_window_module
import outsource_mail_collector.ui.row_review_flow as row_review_flow_module
from outsource_mail_collector.application.models import (
    CollectionResult,
    CollectionWorkflowResult,
    ExtractionResult,
    FinalReportPreview,
    FinalizationBlocker,
    TrackingDashboardSummary,
    WorkReportRangeResult,
    WorkReportRow,
)
from outsource_mail_collector.domain.models import ReviewStatus
from outsource_mail_collector.domain.work_report import (
    RowSource,
    WorkReportIssueCode,
)
from outsource_mail_collector.ui.main_window import MainWindow
from outsource_mail_collector.ui.review_grid import _COLUMNS


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_window_has_received_date_and_work_date_range_controls():
    _app()
    window = MainWindow(_services())

    assert window.received_date_edit is not None
    assert window.work_date_from_edit is not None
    assert window.work_date_to_edit is not None
    assert window.review_grid.rowCount() == 1


def test_apply_collection_result_populates_extended_work_rows():
    _app()
    services = _services()
    window = MainWindow(services)
    workflow = CollectionWorkflowResult(
        collection=CollectionResult(
            mails=(),
            missing_employees=(
                SimpleNamespace(name="김철수", email="kim@example.com"),
            ),
            errors=(),
            target_employee_count=2,
            received_mail_count=2,
        ),
        extraction=ExtractionResult(records=(), skipped_mail_ids=(), errors=()),
        records=(),
        work_report_rows=(_row(2),),
    )

    window.apply_collection_result(workflow)

    assert window.review_grid.rowCount() == 1
    assert window.summary_value("대상 인원") == "2"
    assert window.summary_value("수신 메일") == "2"
    assert "김철수" in window.missing_banner.text()


def test_reload_rows_clears_collection_only_received_and_missing_state():
    _app()
    services = _services()
    window = MainWindow(services)
    workflow = CollectionWorkflowResult(
        collection=CollectionResult(
            mails=(),
            missing_employees=(
                SimpleNamespace(name="김철수", email="kim@example.com"),
            ),
            errors=(),
            target_employee_count=2,
            received_mail_count=2,
        ),
        extraction=ExtractionResult(records=(), skipped_mail_ids=(), errors=()),
        records=(),
        work_report_rows=(_row(2),),
    )
    window.apply_collection_result(workflow)

    window._reload_rows()

    assert window.summary_value("수신 메일") == "0"
    assert window.summary_value("미보고") == "0"
    assert window.missing_banner.isHidden()


def test_open_original_shows_warning_for_com_error(monkeypatch):
    _app()
    services = _services()
    services.review_service = SimpleNamespace(
        open_original=lambda _mail_id: (_ for _ in ()).throw(
            pywintypes.com_error(-1, "Outlook item is unavailable", None, None)
        )
    )
    window = MainWindow(services)
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, text: warnings.append(text),
    )

    window._open_original("ENTRY-1")

    assert warnings == ["(-1, 'Outlook item is unavailable', None, None)"]


def test_manual_row_button_calls_work_report_service(monkeypatch):
    _app()
    services = _services()
    window = MainWindow(services)

    class FakeManualDialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, parent=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def values(self):
            return {
                "work_date": date(2026, 8, 1),
                "vendor_name": "업체A",
                "tracking_no": "AB260101",
                "equipment_name": "장비 1",
                "business_team": "WA",
                "actual_headcount": 2,
                "night_headcount": 2,
                "reported_daily_man_day": None,
                "reported_cumulative_man_day": Decimal("12.0"),
                "resolution_note": "주말 작업",
            }

    monkeypatch.setattr(
        main_window_module, "ManualRowDialog", FakeManualDialog
    )

    window.manual_button.click()

    assert len(services.work_report_service.manual_calls) == 1
    assert services.work_report_service.manual_calls[0]["night_headcount"] == 2
    assert (
        "per_person_man_day"
        not in services.work_report_service.manual_calls[0]
    )


def test_night_issue_review_updates_headcounts_before_confirmation(
    monkeypatch,
):
    _app()
    services = _services()
    services.work_report_service.rows = [
        _row(
            1,
            night_headcount=None,
            issue_codes=(WorkReportIssueCode.NIGHT_HEADCOUNT_UNRESOLVED,),
        )
    ]
    window = MainWindow(services)
    dialog_arguments: list[dict] = []

    class FakeProblemDialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, **kwargs):
            dialog_arguments.append(kwargs)
            self.confirmed_daily_edit = SimpleNamespace(
                setText=lambda text: None
            )
            self.confirmed_cumulative_edit = SimpleNamespace(
                setText=lambda text: None
            )

        def exec(self):
            return QDialog.DialogCode.Accepted

        def values(self):
            return {
                "actual_headcount": 3,
                "night_headcount": 1,
                "confirmed_daily_man_day": Decimal("3.5"),
                "confirmed_cumulative_man_day": Decimal("10.0"),
                "resolution_note": "혼합 야근 인원 확인",
            }

    monkeypatch.setattr(
        row_review_flow_module, "ProblemReviewDialog", FakeProblemDialog
    )

    window._review_problem_row(1)

    assert dialog_arguments[0]["actual_headcount"] == 2
    assert dialog_arguments[0]["night_headcount"] is None
    assert dialog_arguments[0]["headcount_correction"] is True
    assert services.work_report_service.update_calls == [
        (
            1,
            {"actual_headcount": 3, "night_headcount": 1},
            "혼합 야근 인원 확인",
        )
    ]
    assert services.work_report_service.confirm_calls == [
        (
            1,
            Decimal("3.5"),
            Decimal("10.0"),
            "혼합 야근 인원 확인",
        )
    ]


def test_blue_dashboard_button_opens_dashboard_with_final_preview(monkeypatch):
    _app()
    services = _services()
    window = MainWindow(services)
    window.work_date_from_edit.setDate(QDate(2026, 8, 2))
    window.work_date_to_edit.setDate(QDate(2026, 8, 2))

    captured: dict[str, object] = {}

    class FakeDashboardDialog:
        def __init__(
            self,
            *args,
            final_preview=None,
            work_order_registration_callback=None,
            **kwargs,
        ):
            captured["final_preview"] = final_preview
            captured["registration_callback"] = work_order_registration_callback
            self.final_preview_view = None

        def exec(self):
            captured["executed"] = True

    monkeypatch.setattr(
        main_window_module, "TrackingDashboardDialog", FakeDashboardDialog
    )

    window.dashboard_button.click()

    assert services.final_report_service.preview_calls == [()]
    assert captured["final_preview"] is not None
    assert callable(captured["registration_callback"])
    assert captured["executed"] is True
    assert "#1565c0" in window.dashboard_button.styleSheet()
    assert not hasattr(window, "preview_button")


def test_accepting_settings_refreshes_work_order_mappings(monkeypatch):
    _app()
    services = _services()
    window = MainWindow(services)

    class FakeSettingsDialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, settings_service, parent=None):
            self.settings_service = settings_service

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        main_window_module, "SettingsDialog", FakeSettingsDialog
    )

    window._open_settings()

    assert services.work_report_service.mapping_refresh_calls == 1


def test_work_order_registration_acceptance_prefills_settings_and_refreshes_rows(monkeypatch):
    """Removing accepted-save refreshes would leave newly mapped rows unresolved."""
    _app()
    services = _services()
    window = MainWindow(services)
    captured: dict[str, object] = {}
    reloaded: list[bool] = []
    summary = _dashboard_summary()

    class FakeSettingsDialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, settings_service, parent=None, *, work_order_prefill=None):
            captured["settings_service"] = settings_service
            captured["prefill"] = work_order_prefill

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(main_window_module, "SettingsDialog", FakeSettingsDialog)
    monkeypatch.setattr(window, "_reload_rows", lambda: reloaded.append(True))

    assert window._open_work_order_registration(summary) is True
    assert captured["settings_service"] is services.settings_service
    assert captured["prefill"].tracking_no == "AB260101"
    assert captured["prefill"].equipment_name == "장비 1"
    assert captured["prefill"].vendor_name == "업체A"
    assert captured["prefill"].business_team == "WA"
    assert services.work_report_service.mapping_refresh_calls == 1
    assert reloaded == [True]


def test_work_order_registration_cancellation_skips_global_refresh(monkeypatch):
    """Refreshing on cancel would report a master-data change that was never saved."""
    _app()
    services = _services()
    window = MainWindow(services)
    reloaded: list[bool] = []

    class FakeSettingsDialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, settings_service, parent=None, *, work_order_prefill=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(main_window_module, "SettingsDialog", FakeSettingsDialog)
    monkeypatch.setattr(window, "_reload_rows", lambda: reloaded.append(True))

    assert window._open_work_order_registration(_dashboard_summary()) is False
    assert services.work_report_service.mapping_refresh_calls == 0
    assert reloaded == []


def test_row_inclusion_toggle_calls_service_and_reloads():
    _app()
    services = _services()
    window = MainWindow(services)
    buttons = {
        button.text(): button
        for button in window.review_grid.cellWidget(0, _COLUMNS.index("작업")).findChildren(
            QToolButton
        )
    }

    buttons["제외"].click()

    assert services.work_report_service.inclusion_calls == [
        (1, False, "사용자 반영 제외")
    ]
    assert window.review_grid.item(0, _COLUMNS.index("포함")).text() == "제외"
    buttons = {
        button.text(): button
        for button in window.review_grid.cellWidget(0, _COLUMNS.index("작업")).findChildren(
            QToolButton
        )
    }
    buttons["제외 취소"].click()
    assert services.work_report_service.inclusion_calls[-1] == (
        1,
        True,
        "사용자 반영 제외 취소",
    )


def test_bulk_soft_delete_confirms_outlook_is_untouched_and_reloads(monkeypatch):
    _app()
    services = _services()
    services.work_report_service.rows.append(_row(2))
    window = MainWindow(services)
    for row_index in range(2):
        window.review_grid.item(row_index, 0).setCheckState(
            Qt.CheckState.Checked
        )
    initial_reload_count = services.work_report_service.list_calls
    questions: list[str] = []

    def question(_parent, _title, text, *_args):
        questions.append(text)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", question)

    window.delete_button.click()

    assert "Outlook 메일은 삭제하거나 변경하지 않습니다" in questions[0]
    assert "대시보드와 최종 표" in questions[0]
    assert services.work_report_service.bulk_delete_calls == [
        ([1, 2], "사용자 선택 삭제")
    ]
    assert window.review_grid.rowCount() == 0
    assert services.work_report_service.list_calls == initial_reload_count + 1


def test_confirm_selected_rows_calls_bulk_confirm_and_reloads():
    _app()
    services = _services()
    services.work_report_service.rows.append(_row(2))
    window = MainWindow(services)
    for row_index in range(2):
        window.review_grid.item(row_index, 0).setCheckState(
            Qt.CheckState.Checked
        )
    initial_reload_count = services.work_report_service.list_calls

    window.confirm_selected_button.click()

    assert services.work_report_service.bulk_confirm_calls == [
        ([1, 2], "사용자 선택 일괄 확정")
    ]
    assert services.work_report_service.list_calls == initial_reload_count + 1


def test_confirm_selected_rows_empty_selection_shows_message(monkeypatch):
    _app()
    services = _services()
    window = MainWindow(services)
    messages: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, _title, text: messages.append(text),
    )

    window.confirm_selected_button.click()

    assert "확정할 행을 선택해 주세요" in messages[0]
    assert services.work_report_service.bulk_confirm_calls == []


def test_confirm_selected_rows_service_error_shows_warning_without_reload(
    monkeypatch,
):
    _app()
    services = _services()
    services.work_report_service.bulk_confirm_error = ValueError(
        "메일 값과 계산 값이 달라 개별 확인이 필요한 행입니다: 1"
    )
    window = MainWindow(services)
    window.review_grid.item(0, 0).setCheckState(Qt.CheckState.Checked)
    initial_reload_count = services.work_report_service.list_calls
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, text: warnings.append(text),
    )

    window.confirm_selected_button.click()

    assert "개별 확인이 필요한 행입니다" in warnings[0]
    assert services.work_report_service.list_calls == initial_reload_count


def test_bulk_soft_delete_empty_selection_and_cancel_do_not_mutate(monkeypatch):
    _app()
    services = _services()
    window = MainWindow(services)
    messages: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, _title, text: messages.append(text),
    )

    window.delete_button.click()

    assert "삭제할 행을 선택해 주세요" in messages[0]
    assert services.work_report_service.bulk_delete_calls == []

    window.review_grid.item(0, 0).setCheckState(
        Qt.CheckState.Checked
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: QMessageBox.StandardButton.No,
    )
    window.delete_button.click()
    assert services.work_report_service.bulk_delete_calls == []


def test_deleted_row_recovery_restores_selected_rows_and_reloads(monkeypatch):
    _app()
    services = _services()
    deleted = replace(_row(8), deleted_at="2026-07-31T00:00:00+00:00")
    services.work_report_service.deleted_rows = [deleted]
    window = MainWindow(services)

    class FakeRecoveryDialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, rows, parent=None):
            assert tuple(rows) == (deleted,)

        def exec(self):
            return QDialog.DialogCode.Accepted

        def selected_row_ids(self):
            return [8]

        def resolution_note(self):
            return "잘못 삭제한 행 복구"

    monkeypatch.setattr(
        main_window_module, "DeletedRowsDialog", FakeRecoveryDialog
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: QMessageBox.StandardButton.Yes,
    )

    window.recovery_button.click()

    assert services.work_report_service.bulk_restore_calls == [
        ([8], "잘못 삭제한 행 복구")
    ]
    assert window.review_grid.rowCount() == 2


def test_empty_recovery_list_shows_message_without_opening_dialog(
    monkeypatch,
):
    _app()
    services = _services()
    window = MainWindow(services)
    messages: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, _title, text: messages.append(text),
    )

    window.recovery_button.click()

    assert messages == ["복구할 삭제 항목이 없습니다."]
    assert services.work_report_service.bulk_restore_calls == []


def test_bulk_delete_service_error_keeps_data_and_does_not_reload(
    monkeypatch,
):
    _app()
    services = _services()
    services.work_report_service.rows.append(_row(2))
    services.work_report_service.bulk_error = ValueError(
        "두 번째 행 삭제 실패"
    )
    window = MainWindow(services)
    for row_index in range(2):
        window.review_grid.item(row_index, 0).setCheckState(
            Qt.CheckState.Checked
        )
    initial_reload_count = services.work_report_service.list_calls
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, text: warnings.append(text),
    )

    window.delete_button.click()

    assert warnings == ["두 번째 행 삭제 실패"]
    assert [row.row_id for row in services.work_report_service.rows] == [1, 2]
    assert window.review_grid.rowCount() == 2
    assert services.work_report_service.list_calls == initial_reload_count


def test_bulk_restore_service_error_keeps_data_and_does_not_reload(
    monkeypatch,
):
    _app()
    services = _services()
    deleted = replace(_row(8), deleted_at="2026-07-31T00:00:00+00:00")
    services.work_report_service.deleted_rows = [deleted]
    services.work_report_service.bulk_error = ValueError(
        "두 번째 행 복구 실패"
    )
    window = MainWindow(services)
    initial_reload_count = services.work_report_service.list_calls
    warnings: list[str] = []

    class FakeRecoveryDialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, rows, parent=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def selected_row_ids(self):
            return [8]

        def resolution_note(self):
            return "복구 사유"

    monkeypatch.setattr(
        main_window_module, "DeletedRowsDialog", FakeRecoveryDialog
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, text: warnings.append(text),
    )

    window.recovery_button.click()

    assert warnings == ["두 번째 행 복구 실패"]
    assert services.work_report_service.deleted_rows == [deleted]
    assert window.review_grid.rowCount() == 1
    assert services.work_report_service.list_calls == initial_reload_count + 1


def test_dashboard_button_receives_application_services_and_refresh(monkeypatch):
    _app()
    services = _services()
    window = MainWindow(services)
    captured: dict[str, object] = {}

    class FakeDashboardDialog:
        def __init__(
            self,
            dashboard_service,
            work_report_service,
            refresh_callback,
            parent=None,
            *,
            final_preview=None,
            preview_supplier=None,
            work_order_registration_callback=None,
        ):
            captured.update(
                dashboard_service=dashboard_service,
                work_report_service=work_report_service,
                refresh_callback=refresh_callback,
                final_preview=final_preview,
                preview_supplier=preview_supplier,
                work_order_registration_callback=work_order_registration_callback,
            )

        def exec(self):
            captured["executed"] = True

    monkeypatch.setattr(
        main_window_module, "TrackingDashboardDialog", FakeDashboardDialog
    )

    window.dashboard_button.click()

    assert captured["dashboard_service"] is services.tracking_dashboard_service
    assert captured["work_report_service"] is services.work_report_service
    assert captured["preview_supplier"] is not None
    assert callable(captured["work_order_registration_callback"])
    captured["preview_supplier"]()
    assert services.final_report_service.preview_calls == [(), ()]
    assert captured["executed"] is True


class _WorkReportService:
    def __init__(self) -> None:
        self.rows = [_row(1)]
        self.manual_calls: list[dict] = []
        self.update_calls: list[tuple[int, dict, str]] = []
        self.confirm_calls: list[tuple[int, Decimal, Decimal, str]] = []
        self.mapping_refresh_calls = 0
        self.inclusion_calls: list[tuple[int, bool, str]] = []
        self.delete_calls: list[tuple[int, str]] = []
        self.restore_calls: list[tuple[int, str]] = []
        self.bulk_delete_calls: list[tuple[list[int], str]] = []
        self.bulk_restore_calls: list[tuple[list[int], str]] = []
        self.bulk_confirm_calls: list[tuple[list[int], str]] = []
        self.bulk_confirm_error: ValueError | None = None
        self.bulk_error: ValueError | None = None
        self.deleted_rows: list[WorkReportRow] = []
        self.list_calls = 0

    def list_rows(self, date_from, date_to, *, include_deleted=False):
        self.list_calls += 1
        rows = self.rows + (self.deleted_rows if include_deleted else [])
        return WorkReportRangeResult(tuple(rows), 0, 0)

    def add_manual_row(self, **values):
        self.manual_calls.append(values)
        return self.rows[0]

    def set_included(self, row_id, included, *, resolution_note):
        self.inclusion_calls.append((row_id, included, resolution_note))
        index = next(i for i, row in enumerate(self.rows) if row.row_id == row_id)
        self.rows[index] = replace(
            self.rows[index],
            included=included,
            review_status=(
                ReviewStatus.NORMAL if included else ReviewStatus.EXCLUDED
            ),
        )
        return self.rows[index]

    def soft_delete_row(self, row_id, *, resolution_note):
        self.delete_calls.append((row_id, resolution_note))
        row = next(row for row in self.rows if row.row_id == row_id)
        self.rows.remove(row)
        self.deleted_rows.append(
            replace(row, deleted_at="2026-07-31T00:00:00+00:00")
        )
        return self.deleted_rows[-1]

    def restore_row(self, row_id, *, resolution_note):
        self.restore_calls.append((row_id, resolution_note))
        row = next(row for row in self.deleted_rows if row.row_id == row_id)
        self.deleted_rows.remove(row)
        self.rows.append(replace(row, deleted_at=None))
        return self.rows[-1]

    def soft_delete_rows(self, row_ids, *, resolution_note):
        self.bulk_delete_calls.append((list(row_ids), resolution_note))
        if self.bulk_error is not None:
            raise self.bulk_error
        deleted = []
        for row_id in row_ids:
            deleted.append(
                self.soft_delete_row(
                    row_id, resolution_note=resolution_note
                )
            )
        return deleted

    def restore_rows(self, row_ids, *, resolution_note):
        self.bulk_restore_calls.append((list(row_ids), resolution_note))
        if self.bulk_error is not None:
            raise self.bulk_error
        restored = []
        for row_id in row_ids:
            restored.append(
                self.restore_row(row_id, resolution_note=resolution_note)
            )
        return restored

    def confirm_rows(self, row_ids, *, resolution_note):
        self.bulk_confirm_calls.append((list(row_ids), resolution_note))
        if self.bulk_confirm_error is not None:
            raise self.bulk_confirm_error
        return list(self.rows)

    def refresh_work_order_mappings(self):
        self.mapping_refresh_calls += 1
        return self.rows

    def update_row(self, row_id, changes, *, resolution_note):
        self.update_calls.append((row_id, changes, resolution_note))
        return self.rows[0]

    def confirm_row(
        self,
        row_id,
        *,
        confirmed_daily_man_day,
        confirmed_cumulative_man_day,
        resolution_note,
    ):
        self.confirm_calls.append(
            (
                row_id,
                confirmed_daily_man_day,
                confirmed_cumulative_man_day,
                resolution_note,
            )
        )
        return self.rows[0]


class _FinalReportService:
    def __init__(self) -> None:
        self.preview_calls: list[tuple[()]] = []
        self.confirm_calls: list[tuple[()]] = []

    def preview(self):
        self.preview_calls.append(())
        return FinalReportPreview(None, None, tuple(), tuple())

    def confirm(self):
        self.confirm_calls.append(())
        raise ValueError("활성 행 없음")


def _services():
    settings = SimpleNamespace(
        get_setting=lambda key, default=None: (
            "Inbox" if key == "outlook_folder" else default
        ),
        list_employees=lambda active_only=False: [],
    )
    review = SimpleNamespace(open_original=lambda *args: None)
    return SimpleNamespace(
        settings_service=settings,
        review_service=review,
        mail_collection_service=SimpleNamespace(),
        extraction_orchestrator=SimpleNamespace(),
        excel_export_service=SimpleNamespace(),
        work_report_service=_WorkReportService(),
        tracking_dashboard_service=SimpleNamespace(),
        final_report_service=_FinalReportService(),
        report_renderer=SimpleNamespace(),
        clipboard_writer=SimpleNamespace(),
    )


def _dashboard_summary() -> TrackingDashboardSummary:
    return TrackingDashboardSummary(
        normalized_tracking_no="AB260101",
        tracking_no="AB260101",
        vendor_name="업체A",
        vendor_sort_order=1,
        equipment_name="장비 1",
        business_team="WA",
        latest_work_date=date(2026, 8, 2),
        latest_row_id=7,
        latest_actual_headcount=3,
        latest_night_headcount=1,
        latest_man_day_basis="혼합",
        latest_confirmed_daily_man_day=Decimal("3.5"),
        latest_reported_cumulative_man_day=Decimal("23.5"),
        latest_calculated_cumulative_man_day=Decimal("23.5"),
        latest_confirmed_cumulative_man_day=Decimal("23.5"),
        initial_cumulative_man_day=Decimal("20.0"),
        source_row_ids=(7,),
        blockers=(
            FinalizationBlocker(7, "WORK_ORDER_UNREGISTERED", "수주 마스터 등록 필요"),
        ),
        start_date=None,
        completed_at=None,
    )


def _row(
    row_id: int,
    *,
    night_headcount: int | None = 2,
    issue_codes: tuple[WorkReportIssueCode, ...] = (),
) -> WorkReportRow:
    return WorkReportRow(
        row_id=row_id,
        source_type=RowSource.MAIL,
        extracted_record_id=row_id,
        mail_entry_id=f"ENTRY-{row_id}",
        work_date=date.today(),
        work_date_confirmed=True,
        vendor_name="업체A",
        tracking_no="AB260101",
        equipment_name="장비 1",
        business_team="WA",
        actual_headcount=2,
        night_headcount=night_headcount,
        per_person_man_day=Decimal("1.5"),
        reported_daily_man_day=Decimal("3.0"),
        calculated_daily_man_day=Decimal("3.0"),
        confirmed_daily_man_day=Decimal("3.0"),
        reported_cumulative_man_day=Decimal("12.0"),
        calculated_cumulative_man_day=Decimal("12.0"),
        confirmed_cumulative_man_day=Decimal("12.0"),
        cumulative_series_key="업체a|T:AB260101",
        issue_codes=issue_codes,
        review_status=ReviewStatus.NORMAL,
        included=True,
        warning_confirmed=True,
        resolution_note=None,
    )
