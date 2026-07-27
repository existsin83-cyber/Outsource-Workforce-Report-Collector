from __future__ import annotations

from datetime import datetime

import pytest

from outsource_mail_collector.infrastructure.outlook_adapter import (
    DASL_RECEIVED,
    OutlookComAdapter,
)


START = datetime(2026, 7, 24, 0, 0)
END = datetime(2026, 7, 25, 0, 0)
EXPECTED_DASL = (
    f'@SQL="{DASL_RECEIVED}" >= \'2026-07-24 00:00\' '
    f'AND "{DASL_RECEIVED}" < \'2026-07-25 00:00\''
)


def test_list_folders_returns_inbox_and_nested_paths():
    child = FakeFolder("전장기술팀")
    nested = FakeFolder("일일보고")
    child.Folders.append(nested)
    inbox = FakeFolder("Inbox", children=[child])
    adapter, _ = _connected_adapter(inbox)

    assert adapter.list_folders() == [
        "Inbox",
        "Inbox/전장기술팀",
        "Inbox/전장기술팀/일일보고",
    ]


def test_list_messages_uses_dasl_filter_and_skips_non_mail_items():
    mail = FakeMailItem(entry_id="ENTRY-1", sender_email="user@example.com")
    meeting = FakeMailItem(
        entry_id="MEETING-1", sender_email="user@example.com", item_class=26
    )
    inbox = FakeFolder("Inbox", items=[mail, meeting])
    adapter, _ = _connected_adapter(inbox)

    rows = adapter.list_messages("Inbox", START, END)

    assert inbox.Items.restrict_calls == [EXPECTED_DASL]
    assert [row.mail_id for row in rows] == ["ENTRY-1"]
    assert rows[0].sender_email == "user@example.com"


def test_exchange_sender_is_resolved_to_primary_smtp_address():
    mail = FakeMailItem(
        entry_id="ENTRY-EX",
        sender_email="/O=EXCHANGE/OU=GROUP/CN=USER",
        sender_type="EX",
        primary_smtp="USER@EXAMPLE.COM",
    )
    inbox = FakeFolder("Inbox", items=[mail])
    adapter, _ = _connected_adapter(inbox)

    rows = adapter.list_messages("Inbox", START, END)

    assert rows[0].sender_email == "user@example.com"


def test_open_and_display_message_use_entry_id_without_state_mutation():
    mail = FakeMailItem(entry_id="ENTRY-1", sender_email="user@example.com")
    inbox = FakeFolder("Inbox", items=[mail])
    adapter, namespace = _connected_adapter(inbox)

    record = adapter.open_message("ENTRY-1")
    adapter.display_message("ENTRY-1")

    assert record.mail_id == "ENTRY-1"
    assert record.body_text == "본문"
    assert record.body_html == "<p>본문</p>"
    assert namespace.requested_ids == ["ENTRY-1", "ENTRY-1"]
    assert mail.display_count == 1
    assert mail.prohibited_calls == []


def test_unknown_folder_is_rejected():
    adapter, _ = _connected_adapter(FakeFolder("Inbox"))

    with pytest.raises(ValueError, match="Outlook 폴더"):
        adapter.list_messages("Inbox/없는폴더", START, END)


def test_connect_retries_once_when_outlook_is_starting():
    namespace = FakeNamespace(FakeFolder("Inbox"))
    outlook = FakeOutlook(namespace)
    attempts = 0

    def flaky_dispatch(_):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("Outlook startup race")
        return outlook

    adapter = OutlookComAdapter(dispatch=flaky_dispatch)

    adapter.connect()

    assert attempts == 2
    assert adapter.list_folders() == ["Inbox"]


class FakeExchangeUser:
    def __init__(self, smtp: str) -> None:
        self.PrimarySmtpAddress = smtp


class FakeSender:
    def __init__(self, smtp: str) -> None:
        self._smtp = smtp

    def GetExchangeUser(self) -> FakeExchangeUser:
        return FakeExchangeUser(self._smtp)


class FakeMailItem:
    def __init__(
        self,
        entry_id: str,
        sender_email: str,
        *,
        item_class: int = 43,
        sender_type: str = "SMTP",
        primary_smtp: str = "",
    ) -> None:
        self.EntryID = entry_id
        self.Subject = "업무보고"
        self.SenderName = "홍길동"
        self.SenderEmailAddress = sender_email
        self.SenderEmailType = sender_type
        self.Sender = FakeSender(primary_smtp)
        self.ReceivedTime = datetime(2026, 7, 24, 18, 0)
        self.Class = item_class
        self.Body = "본문"
        self.HTMLBody = "<p>본문</p>"
        self.Parent = None
        self.display_count = 0
        self.prohibited_calls: list[str] = []

    def Display(self) -> None:
        self.display_count += 1

    def Save(self) -> None:
        self.prohibited_calls.append("Save")

    def Delete(self) -> None:
        self.prohibited_calls.append("Delete")

    def Move(self, destination) -> None:
        self.prohibited_calls.append("Move")


class FakeItems:
    def __init__(self, rows: list[FakeMailItem]) -> None:
        self._rows = rows
        self.restrict_calls: list[str] = []

    def Restrict(self, filter_text: str):
        self.restrict_calls.append(filter_text)
        return list(self._rows)


class FakeFolder:
    def __init__(
        self,
        name: str,
        *,
        children: list["FakeFolder"] | None = None,
        items: list[FakeMailItem] | None = None,
    ) -> None:
        self.Name = name
        self.Folders = children or []
        self.Items = FakeItems(items or [])
        self.FolderPath = name
        for item in items or []:
            item.Parent = self


class FakeNamespace:
    def __init__(self, inbox: FakeFolder) -> None:
        self.inbox = inbox
        self.requested_ids: list[str] = []

    def GetDefaultFolder(self, folder_id: int) -> FakeFolder:
        assert folder_id == 6
        return self.inbox

    def GetItemFromID(self, entry_id: str) -> FakeMailItem:
        self.requested_ids.append(entry_id)
        for folder in _walk_folders(self.inbox):
            for item in folder.Items._rows:
                if item.EntryID == entry_id:
                    return item
        raise KeyError(entry_id)


class FakeOutlook:
    def __init__(self, namespace: FakeNamespace) -> None:
        self.namespace = namespace

    def GetNamespace(self, name: str) -> FakeNamespace:
        assert name == "MAPI"
        return self.namespace


def _connected_adapter(inbox: FakeFolder):
    namespace = FakeNamespace(inbox)
    outlook = FakeOutlook(namespace)
    adapter = OutlookComAdapter(dispatch=lambda _: outlook)
    adapter.connect()
    return adapter, namespace


def _walk_folders(root: FakeFolder):
    yield root
    for child in root.Folders:
        yield from _walk_folders(child)
