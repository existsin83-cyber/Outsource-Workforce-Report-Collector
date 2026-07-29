from outsource_mail_collector.application.report_renderer import RenderedReport
from outsource_mail_collector.ui.clipboard import ClipboardWriter


class _FakeClipboard:
    def __init__(self) -> None:
        self.mime_data = None

    def setMimeData(self, mime_data) -> None:
        self.mime_data = mime_data


def test_clipboard_writer_sets_html_and_plain_text_payloads():
    clipboard = _FakeClipboard()
    writer = ClipboardWriter(clipboard)

    writer.write(
        RenderedReport(
            html="<table><tr><td>업체A</td></tr></table>",
            plain_text="업체A",
        )
    )

    assert clipboard.mime_data.hasHtml()
    assert clipboard.mime_data.hasText()
    assert clipboard.mime_data.html().startswith("<table>")
    assert clipboard.mime_data.text() == "업체A"
