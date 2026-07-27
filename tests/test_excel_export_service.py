from __future__ import annotations

from pathlib import Path

import pytest

from outsource_mail_collector.application.errors import (
    ExcelIntegrationUnavailableError,
)
from outsource_mail_collector.application.excel_export_service import ExcelExportService
from outsource_mail_collector.infrastructure.db.repository import SQLiteRepository


def test_export_without_real_adapter_is_explicitly_unavailable(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = ExcelExportService(repository, excel_adapter=None)

    with pytest.raises(ExcelIntegrationUnavailableError):
        service.export(Path("target.xlsx"), "외주인원_원본", [1])
