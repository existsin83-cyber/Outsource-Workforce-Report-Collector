from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

import outsource_mail_collector.ui.main_window as main_window_module
from outsource_mail_collector.application.models import (
    CollectionResult,
    CollectionWorkflowResult,
    ExtractionResult,
    FinalReportPreview,
    WorkReportRangeResult,
    WorkReportRow,
)
from outsource_mail_collector.domain.models import ReviewStatus
from outsource_mail_collector.domain.work_report import (
    RowSource,
    WorkReportIssueCode,
)
from outsource_mail_collector.ui.main_window import MainWindow


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
        main_window_module, "ProblemReviewDialog", FakeProblemDialog
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


def test_preview_button_invokes_final_report_service(monkeypatch):
    _app()
    services = _services()
    window = MainWindow(services)

    class _Signal:
        def connect(self, callback):
            self.callback = callback

    class FakeFinalDialog:
        def __init__(self, preview, parent=None):
            self.preview = preview
            self.confirm_requested = _Signal()
            self.copy_requested = _Signal()

        def exec(self):
            return 0

    monkeypatch.setattr(
        main_window_module, "FinalReportDialog", FakeFinalDialog
    )

    window.preview_button.click()

    assert len(services.final_report_service.preview_calls) == 1


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


def test_excel_button_shows_preparation_notice(monkeypatch):
    _app()
    window = MainWindow(_services())
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, title, text: shown.append((title, text)),
    )

    window.excel_button.click()

    assert shown
    assert "실제 Excel 연동은 아직 준비되지 않았습니다." in shown[0][1]
    assert "실 워크북 확보 후 사용할 수 있습니다." in shown[0][1]


class _WorkReportService:
    def __init__(self) -> None:
        self.rows = [_row(1)]
        self.manual_calls: list[dict] = []
        self.update_calls: list[tuple[int, dict, str]] = []
        self.confirm_calls: list[tuple[int, Decimal, Decimal, str]] = []
        self.mapping_refresh_calls = 0

    def list_rows(self, date_from, date_to):
        return WorkReportRangeResult(tuple(self.rows), 0, 0)

    def add_manual_row(self, **values):
        self.manual_calls.append(values)
        return self.rows[0]

    def set_included(self, *args, **kwargs):
        return self.rows[0]

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
        self.preview_calls: list[tuple[date, date]] = []

    def preview(self, date_from, date_to):
        self.preview_calls.append((date_from, date_to))
        return FinalReportPreview(date_from, date_to, tuple(), tuple())


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
        final_report_service=_FinalReportService(),
        report_renderer=SimpleNamespace(),
        clipboard_writer=SimpleNamespace(),
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
