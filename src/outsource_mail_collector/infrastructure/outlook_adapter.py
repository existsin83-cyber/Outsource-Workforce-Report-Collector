"""Read-only Outlook COM adapter.

Only property reads and the explicitly user-triggered Inspector ``Display`` call are
implemented. No mail mutation method is used.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol

import pywintypes

from outsource_mail_collector.domain.models import MailEnvelope, MailRecord


OL_FOLDER_INBOX = 6
OL_MAIL_ITEM_CLASS = 43
DASL_RECEIVED = "urn:schemas:httpmail:datereceived"


class OutlookAdapter(Protocol):
    def connect(self) -> None:
        """Connect to the current Outlook MAPI session."""
        ...

    def list_folders(self) -> list[str]:
        """Return the default Inbox and all nested mail-folder paths."""
        ...

    def list_messages(
        self, folder_path: str, start_at: datetime, end_at: datetime
    ) -> list[MailEnvelope]:
        """Return message metadata for an end-exclusive received-time range."""
        ...

    def open_message(self, entry_id: str) -> MailRecord:
        """Read one message body without changing read state."""
        ...

    def display_message(self, entry_id: str) -> None:
        """Display the original message after an explicit user action."""
        ...


class OutlookComAdapter:
    """Outlook 2019 Desktop COM implementation of :class:`OutlookAdapter`."""

    def __init__(
        self, dispatch: Callable[[str], Any] | None = None
    ) -> None:
        self._dispatch = dispatch or _default_dispatch
        self._namespace: Any | None = None

    def connect(self) -> None:
        """Connect with one retry because Outlook startup can race COM registration."""

        last_error: BaseException | None = None
        for _ in range(2):
            try:
                outlook = self._dispatch("Outlook.Application")
                self._namespace = outlook.GetNamespace("MAPI")
                return
            except (OSError, pywintypes.com_error) as exc:
                last_error = exc
        raise RuntimeError(
            "Outlook에 연결할 수 없습니다. Outlook 실행 및 프로필 상태를 확인해 주세요."
        ) from last_error

    def list_folders(self) -> list[str]:
        namespace = self._require_namespace()
        inbox = namespace.GetDefaultFolder(OL_FOLDER_INBOX)
        paths: list[str] = []
        self._append_folder_paths(inbox, str(inbox.Name), paths)
        return paths

    def _append_folder_paths(
        self, folder: Any, path: str, paths: list[str]
    ) -> None:
        paths.append(path)
        for child in folder.Folders:
            self._append_folder_paths(child, f"{path}/{child.Name}", paths)

    def list_messages(
        self, folder_path: str, start_at: datetime, end_at: datetime
    ) -> list[MailEnvelope]:
        namespace = self._require_namespace()
        folder = self._resolve_folder(folder_path)
        items = folder.Items.Restrict(_build_date_filter(start_at, end_at))
        envelopes = []
        for item in items:
            if int(item.Class) != OL_MAIL_ITEM_CLASS:
                continue
            envelopes.append(
                MailEnvelope(
                    mail_id=str(item.EntryID),
                    subject=str(item.Subject or ""),
                    sender_name=str(item.SenderName or ""),
                    sender_email=_resolve_smtp(item).strip().lower(),
                    received_at=item.ReceivedTime,
                )
            )
        return envelopes

    def open_message(self, entry_id: str) -> MailRecord:
        namespace = self._require_namespace()
        item = namespace.GetItemFromID(entry_id)
        if int(item.Class) != OL_MAIL_ITEM_CLASS:
            raise ValueError("선택한 Outlook 항목은 메일이 아닙니다.")
        received_at = item.ReceivedTime
        source_folder = str(getattr(item.Parent, "FolderPath", ""))
        return MailRecord(
            mail_id=str(item.EntryID),
            subject=str(item.Subject or ""),
            sender_name=str(item.SenderName or ""),
            sender_email=_resolve_smtp(item).strip().lower(),
            received_at=received_at,
            report_date=None,
            body_text=str(item.Body or ""),
            body_html=str(item.HTMLBody or ""),
            source_folder=source_folder,
        )

    def display_message(self, entry_id: str) -> None:
        namespace = self._require_namespace()
        item = namespace.GetItemFromID(entry_id)
        if int(item.Class) != OL_MAIL_ITEM_CLASS:
            raise ValueError("선택한 Outlook 항목은 메일이 아닙니다.")
        item.Display()

    def _resolve_folder(self, folder_path: str) -> Any:
        namespace = self._require_namespace()
        inbox = namespace.GetDefaultFolder(OL_FOLDER_INBOX)
        parts = [part for part in folder_path.replace("\\", "/").split("/") if part]
        if parts and parts[0].casefold() in {
            str(inbox.Name).casefold(),
            "inbox",
        }:
            parts = parts[1:]
        current = inbox
        for name in parts:
            current = _find_child_folder(current, name)
        return current

    def _require_namespace(self) -> Any:
        if self._namespace is None:
            raise RuntimeError("Outlook 연결이 초기화되지 않았습니다.")
        return self._namespace


def _build_date_filter(start_at: datetime, end_at: datetime) -> str:
    date_format = "%Y-%m-%d %H:%M"
    return (
        f'@SQL="{DASL_RECEIVED}" >= \'{start_at.strftime(date_format)}\' '
        f'AND "{DASL_RECEIVED}" < \'{end_at.strftime(date_format)}\''
    )


def _find_child_folder(parent: Any, name: str) -> Any:
    for child in parent.Folders:
        if str(child.Name).casefold() == name.casefold():
            return child
    raise ValueError(f"Outlook 폴더를 찾을 수 없습니다: {name}")


def _resolve_smtp(mail_item: Any) -> str:
    fallback = str(getattr(mail_item, "SenderEmailAddress", "") or "")
    if str(getattr(mail_item, "SenderEmailType", "")) != "EX":
        return fallback
    try:
        exchange_user = mail_item.Sender.GetExchangeUser()
        smtp = exchange_user.PrimarySmtpAddress
        return str(smtp or fallback)
    except (AttributeError, pywintypes.com_error):
        return fallback


def _default_dispatch(prog_id: str) -> Any:
    import win32com.client

    return win32com.client.Dispatch(prog_id)
