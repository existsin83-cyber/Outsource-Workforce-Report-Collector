"""Qt clipboard boundary for HTML plus plain-text report payloads."""

from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import QMimeData
from PySide6.QtGui import QGuiApplication

from outsource_mail_collector.application.report_renderer import RenderedReport


class _Clipboard(Protocol):
    def setMimeData(self, mime_data: QMimeData) -> None: ...


class ClipboardWriter:
    def __init__(self, clipboard: _Clipboard | None = None) -> None:
        self._clipboard = clipboard

    def write(self, rendered_report: RenderedReport) -> None:
        clipboard = self._clipboard or QGuiApplication.clipboard()
        mime_data = QMimeData()
        mime_data.setHtml(rendered_report.html)
        mime_data.setText(rendered_report.plain_text)
        clipboard.setMimeData(mime_data)
