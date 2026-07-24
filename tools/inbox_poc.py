"""Outlook COM PoC: query the real default Inbox by date range, read-only.

Confirms (per docs/README.md Phase 0 step 2 and docs/rules.md Outlook rules):
- COM automation works against the live Inbox on this machine/security software.
- Restrict() date filtering works without locale-format guessing (uses a DASL/SQL
  filter on urn:schemas:httpmail:datereceived, which takes ISO-formatted values
  regardless of Windows locale - see docs/TRD.md's locale-sensitivity warning).
- No mail state is mutated: UnRead flag is read before and after, Save()/Display()
  are never called, nothing is deleted/moved.

Usage:
    python tools/inbox_poc.py [YYYY-MM-DD]

Defaults to today's date if omitted.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta

import win32com.client

OL_FOLDER_INBOX = 6
OL_MAIL_ITEM_CLASS = 43

DASL_RECEIVED = "urn:schemas:httpmail:datereceived"


def resolve_smtp(mail_item) -> str:
    try:
        if mail_item.SenderEmailType == "EX":
            return mail_item.Sender.GetExchangeUser().PrimarySmtpAddress
        return mail_item.SenderEmailAddress
    except Exception as exc:
        return f"<unresolved: {exc}>"


def build_date_filter(target_date: date) -> str:
    start = datetime(target_date.year, target_date.month, target_date.day)
    end = start + timedelta(days=1)
    fmt = "%Y-%m-%d %H:%M"
    return (
        f"@SQL=\"{DASL_RECEIVED}\" >= '{start.strftime(fmt)}' "
        f"AND \"{DASL_RECEIVED}\" < '{end.strftime(fmt)}'"
    )


def main(argv: list[str]) -> int:
    target_date = (
        datetime.strptime(argv[0], "%Y-%m-%d").date() if argv else date.today()
    )

    outlook = win32com.client.Dispatch("Outlook.Application")
    ns = outlook.GetNamespace("MAPI")
    inbox = ns.GetDefaultFolder(OL_FOLDER_INBOX)
    print(f"Connected. Inbox: {inbox.FolderPath}  (total items: {inbox.Items.Count})")

    filter_str = build_date_filter(target_date)
    print(f"Date filter ({target_date}): {filter_str}")

    items = inbox.Items.Restrict(filter_str)
    print(f"Matched {items.Count} item(s).\n")

    before_unread: dict[str, bool] = {}
    for item in items:
        if item.Class != OL_MAIL_ITEM_CLASS:
            continue  # skip meeting requests/receipts/etc. (rules.md: only MailItem)
        before_unread[item.EntryID] = item.UnRead
        print(f"- Subject     : {item.Subject!r}")
        print(f"  Sender      : {item.SenderName!r} <{resolve_smtp(item)}>")
        print(f"  ReceivedTime: {item.ReceivedTime}")
        print(f"  EntryID     : {item.EntryID}")
        print(f"  UnRead      : {item.UnRead}")

    # Re-fetch and confirm nothing flipped UnRead as a side effect of reading properties.
    mutated = []
    for entry_id, was_unread in before_unread.items():
        refetched = ns.GetItemFromID(entry_id)
        if refetched.UnRead != was_unread:
            mutated.append(entry_id)
    if mutated:
        print(f"\nWARNING: UnRead flag changed for {len(mutated)} item(s): {mutated}")
    else:
        print(f"\nNo read-state mutation detected across {len(before_unread)} mail item(s).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
