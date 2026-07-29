from datetime import date
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from outsource_mail_collector.application.models import (
    CollectionResult,
    ExtractionResult,
    WorkReportRangeResult,
)
from outsource_mail_collector.ui.workers import CollectionWorker


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_worker_collects_received_date_then_returns_work_date_range():
    _app()
    calls: list[tuple] = []
    collection = CollectionResult(
        mails=("mail",), missing_employees=(), errors=()
    )
    extraction = ExtractionResult(
        records=("record",), skipped_mail_ids=(), errors=()
    )
    work_rows = (SimpleNamespace(row_id=1),)
    mail_service = SimpleNamespace(
        collect=lambda received_date, folder: (
            calls.append(("collect", received_date, folder)) or collection
        )
    )
    orchestrator = SimpleNamespace(
        process=lambda mails: (
            calls.append(("extract", mails)) or extraction
        )
    )

    class WorkService:
        def synchronize_extracted_records(self, records):
            calls.append(("synchronize", records))

        def list_rows(self, date_from, date_to):
            calls.append(("list", date_from, date_to))
            return WorkReportRangeResult(work_rows, 0, 0)

    emitted = []
    worker = CollectionWorker(
        date(2026, 7, 30),
        date(2026, 7, 29),
        date(2026, 7, 29),
        "Inbox",
        mail_service,
        orchestrator,
        WorkService(),
    )
    worker.completed.connect(emitted.append)

    worker.run()

    assert calls == [
        ("collect", date(2026, 7, 30), "Inbox"),
        ("extract", ("mail",)),
        ("synchronize", ("record",)),
        ("list", date(2026, 7, 29), date(2026, 7, 29)),
    ]
    assert emitted[0].work_report_rows == work_rows
