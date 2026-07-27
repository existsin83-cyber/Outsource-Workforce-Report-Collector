from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QMessageBox

from outsource_mail_collector.application.models import (
    CollectionResult,
    CollectionWorkflowResult,
    ExtractionResult,
    ReviewRecord,
)
from outsource_mail_collector.domain.models import ReviewStatus
from outsource_mail_collector.ui.main_window import MainWindow


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_window_starts_without_dummy_rows():
    _app()
    window = MainWindow(_services())

    assert window.review_grid.rowCount() == 0
    assert window.summary_value("수신 메일") == "0"


def test_apply_collection_result_updates_grid_summary_and_missing_banner():
    _app()
    window = MainWindow(_services())
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
        records=(
            _record(1, ReviewStatus.NORMAL),
            _record(2, ReviewStatus.VENDOR_UNCONFIRMED),
        ),
    )

    window.apply_collection_result(workflow)

    assert window.review_grid.rowCount() == 2
    assert window.summary_value("대상 인원") == "2"
    assert window.summary_value("수신 메일") == "2"
    assert window.summary_value("검토 필요") == "1"
    assert "김철수" in window.missing_banner.text()


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


def _record(record_id: int, status: ReviewStatus) -> ReviewRecord:
    return ReviewRecord(
        record_id=record_id,
        mail_entry_id=f"ENTRY-{record_id}",
        report_date=date(2026, 7, 24),
        sender_name="홍길동",
        sender_email="hong@example.com",
        equipment_name="장비A",
        tracking_no="AB260101",
        vendor_name="협력사A",
        actual_headcount=2.0,
        daily_man_day=4.0,
        cumulative_man_day=18.5,
        confidence=0.9,
        review_status=status,
        note=None,
    )


def _services():
    settings = SimpleNamespace(
        get_setting=lambda key, default=None: (
            "Inbox" if key == "outlook_folder" else default
        ),
        list_employees=lambda active_only=False: [],
    )
    review = SimpleNamespace(
        update_field=lambda *args: None,
        set_status=lambda *args: [],
        open_original=lambda *args: None,
        list_records=lambda report_date: [],
    )
    return SimpleNamespace(
        settings_service=settings,
        review_service=review,
        mail_collection_service=SimpleNamespace(),
        extraction_orchestrator=SimpleNamespace(),
        excel_export_service=SimpleNamespace(),
    )
