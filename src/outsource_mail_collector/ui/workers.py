"""Background workers that keep COM operations off the PySide6 UI thread."""

from __future__ import annotations

import pywintypes
from PySide6.QtCore import QThread, Signal

from outsource_mail_collector.application.extraction_orchestrator import (
    ExtractionOrchestrator,
)
from outsource_mail_collector.application.mail_collection_service import (
    MailCollectionService,
)
from outsource_mail_collector.application.models import CollectionWorkflowResult
from outsource_mail_collector.application.review_service import ReviewService
from outsource_mail_collector.application.settings_service import SettingsService


class FolderLoadWorker(QThread):
    loaded = Signal(list)
    failed = Signal(str)

    def __init__(self, settings_service: SettingsService) -> None:
        super().__init__()
        self._settings = settings_service

    def run(self) -> None:
        import pythoncom

        pythoncom.CoInitialize()
        try:
            self.loaded.emit(self._settings.list_outlook_folders())
        except (OSError, RuntimeError, ValueError, pywintypes.com_error) as exc:
            self.failed.emit(str(exc))
        finally:
            pythoncom.CoUninitialize()


class CollectionWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        report_date,
        folder_path: str,
        mail_service: MailCollectionService,
        orchestrator: ExtractionOrchestrator,
        review_service: ReviewService,
    ) -> None:
        super().__init__()
        self._report_date = report_date
        self._folder_path = folder_path
        self._mail_service = mail_service
        self._orchestrator = orchestrator
        self._review_service = review_service

    def run(self) -> None:
        import pythoncom

        pythoncom.CoInitialize()
        try:
            collection = self._mail_service.collect(
                self._report_date, self._folder_path
            )
            extraction = self._orchestrator.process(collection.mails)
            records = tuple(self._review_service.list_records(self._report_date))
            self.completed.emit(
                CollectionWorkflowResult(collection, extraction, records)
            )
        except (OSError, RuntimeError, ValueError, pywintypes.com_error) as exc:
            self.failed.emit(str(exc))
        finally:
            pythoncom.CoUninitialize()
