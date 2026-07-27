"""Application service container injected into the presentation layer."""

from __future__ import annotations

from dataclasses import dataclass

from outsource_mail_collector.application.excel_export_service import (
    ExcelExportService,
)
from outsource_mail_collector.application.extraction_orchestrator import (
    ExtractionOrchestrator,
)
from outsource_mail_collector.application.mail_collection_service import (
    MailCollectionService,
)
from outsource_mail_collector.application.review_service import ReviewService
from outsource_mail_collector.application.settings_service import SettingsService


@dataclass(frozen=True)
class ApplicationServices:
    mail_collection_service: MailCollectionService
    extraction_orchestrator: ExtractionOrchestrator
    review_service: ReviewService
    excel_export_service: ExcelExportService
    settings_service: SettingsService
