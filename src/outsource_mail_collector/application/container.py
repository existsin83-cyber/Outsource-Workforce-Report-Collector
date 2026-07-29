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
from outsource_mail_collector.application.final_report_service import (
    FinalReportService,
)
from outsource_mail_collector.application.man_day_calculation_service import (
    ManDayCalculationService,
)
from outsource_mail_collector.application.report_renderer import (
    HtmlReportRenderer,
)
from outsource_mail_collector.application.review_service import ReviewService
from outsource_mail_collector.application.settings_service import SettingsService
from outsource_mail_collector.application.work_report_service import (
    WorkReportService,
)


@dataclass(frozen=True)
class ApplicationServices:
    mail_collection_service: MailCollectionService
    extraction_orchestrator: ExtractionOrchestrator
    review_service: ReviewService
    excel_export_service: ExcelExportService
    settings_service: SettingsService
    man_day_calculation_service: ManDayCalculationService
    work_report_service: WorkReportService
    final_report_service: FinalReportService
    report_renderer: HtmlReportRenderer
