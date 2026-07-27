"""Background workers that keep COM operations off the PySide6 UI thread."""

from __future__ import annotations

import pywintypes
from PySide6.QtCore import QThread, Signal

from outsource_mail_collector.infrastructure.outlook_adapter import OutlookAdapter


class FolderLoadWorker(QThread):
    loaded = Signal(list)
    failed = Signal(str)

    def __init__(self, outlook_adapter: OutlookAdapter) -> None:
        super().__init__()
        self._outlook = outlook_adapter

    def run(self) -> None:
        import pythoncom

        pythoncom.CoInitialize()
        try:
            self._outlook.connect()
            self.loaded.emit(self._outlook.list_folders())
        except (OSError, RuntimeError, ValueError, pywintypes.com_error) as exc:
            self.failed.emit(str(exc))
        finally:
            pythoncom.CoUninitialize()
