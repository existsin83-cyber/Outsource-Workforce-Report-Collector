from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from outsource_mail_collector.application.container import ApplicationServices
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
from outsource_mail_collector.infrastructure.db.repository import (
    SQLiteRepository,
    default_db_path,
)
from outsource_mail_collector.infrastructure.outlook_adapter import OutlookComAdapter
from outsource_mail_collector.ui.main_window import MainWindow


def build_services(db_path: Path | None = None) -> ApplicationServices:
    """Build the application dependency graph without connecting to Outlook."""

    repository = SQLiteRepository(db_path or default_db_path())
    outlook = OutlookComAdapter()
    return ApplicationServices(
        mail_collection_service=MailCollectionService(repository, outlook),
        extraction_orchestrator=ExtractionOrchestrator(repository),
        review_service=ReviewService(repository, outlook),
        excel_export_service=ExcelExportService(repository, excel_adapter=None),
        settings_service=SettingsService(repository, outlook),
    )


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow(build_services())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
