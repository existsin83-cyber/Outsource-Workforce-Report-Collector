"""Outlook COM PoC: open .msg files directly from disk and dump key fields.

Verifies (per docs/README.md and docs/rules.md):
- Outlook COM automation works on this machine / under this security software.
- No mail state is mutated (no Save() call, no Display(), read/unread untouched).
- What the real report-mail body actually looks like (HTML table vs. pasted image,
  section markers) so section_parser / outsource_extractor regexes can be designed
  against real data instead of guesses.

Usage:
    python tools/outlook_poc.py [path-to-msg-or-folder ...]

Defaults to every *.msg under samples/ next to the project root.
"""

from __future__ import annotations

import sys
from pathlib import Path

import win32com.client

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SAMPLES_DIR = PROJECT_ROOT / "samples"
OUTPUT_DIR = PROJECT_ROOT / "tools" / "poc_output"


def resolve_smtp(mail_item) -> str:
    """Exchange senders report an EX address; resolve to SMTP per TRD note."""
    try:
        if mail_item.SenderEmailType == "EX":
            return mail_item.Sender.GetExchangeUser().PrimarySmtpAddress
        return mail_item.SenderEmailAddress
    except Exception as exc:  # COM can raise for malformed/missing sender info
        return f"<unresolved: {exc}>"


def dump_msg(outlook_ns, msg_path: Path, out_dir: Path) -> None:
    print(f"\n=== {msg_path.name} ===")
    mail = outlook_ns.OpenSharedItem(str(msg_path))
    try:
        print(f"Subject         : {mail.Subject!r}")
        print(f"SenderName      : {mail.SenderName!r}")
        print(f"SenderEmail     : {resolve_smtp(mail)!r}")
        print(f"ReceivedTime    : {mail.ReceivedTime}")
        print(f"EntryID         : {mail.EntryID}")
        print(f"BodyFormat      : {mail.BodyFormat}  (1=plain 2=HTML 3=RTF)")
        print(f"Body length     : {len(mail.Body or '')} chars")
        print(f"HTMLBody length : {len(mail.HTMLBody or '')} chars")
        print(f"Has attachments : {mail.Attachments.Count}")

        out_dir.mkdir(parents=True, exist_ok=True)
        stem = msg_path.stem
        (out_dir / f"{stem}.body.txt").write_text(mail.Body or "", encoding="utf-8")
        (out_dir / f"{stem}.body.html").write_text(mail.HTMLBody or "", encoding="utf-8")
        print(f"-> full body written to {out_dir / f'{stem}.body.txt'} / .body.html")
    finally:
        # No Save()/Display() call anywhere: item is left untouched and discarded.
        pass


def main(argv: list[str]) -> int:
    targets = [Path(p) for p in argv] if argv else [DEFAULT_SAMPLES_DIR]
    msg_files: list[Path] = []
    for target in targets:
        if target.is_dir():
            msg_files.extend(sorted(target.glob("*.msg")))
        elif target.suffix.lower() == ".msg":
            msg_files.append(target)

    if not msg_files:
        print(f"No .msg files found under: {targets}")
        return 1

    outlook = win32com.client.Dispatch("Outlook.Application")
    outlook_ns = outlook.GetNamespace("MAPI")

    print(f"Outlook COM connected. Found {len(msg_files)} .msg file(s).")
    for msg_path in msg_files:
        try:
            dump_msg(outlook_ns, msg_path, OUTPUT_DIR)
        except Exception as exc:
            print(f"FAILED on {msg_path.name}: {exc}")

    print(f"\nDone. Extracted bodies saved under: {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
