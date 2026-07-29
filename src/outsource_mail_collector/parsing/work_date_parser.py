"""Resolve work-date evidence without depending on Outlook or persistence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from outsource_mail_collector.domain.work_report import (
    WorkDateSource,
    WorkReportIssueCode,
)


_FULL_DATE_PATTERNS = (
    re.compile(
        r"(?<!\d)(?P<year>\d{4})\s*[._/\-년]\s*"
        r"(?P<month>\d{1,2})\s*[._/\-월]\s*"
        r"(?P<day>\d{1,2})\s*일?"
    ),
    re.compile(
        r"(?<!\d)(?P<year>\d{2})\s*[._/\-]\s*"
        r"(?P<month>\d{1,2})\s*[._/\-]\s*(?P<day>\d{1,2})(?!\d)"
    ),
)
_MONTH_DAY_PATTERN = re.compile(
    r"(?<!\d)(?P<month>\d{1,2})\s*월\s*(?P<day>\d{1,2})\s*일"
)


@dataclass(frozen=True)
class WorkDateResolution:
    """Candidate work date and the evidence used to select it."""

    candidate_date: date | None
    subject_date: date | None
    body_date: date | None
    source: WorkDateSource
    requires_review: bool
    issue_codes: tuple[str, ...] = ()


def resolve_work_date(
    subject: str, body_text: str, received_at: datetime
) -> WorkDateResolution:
    """Prefer subject evidence and never infer a work date from receipt alone."""

    subject_date = _extract_date(subject, received_at.year)
    body_date = _extract_date(body_text, received_at.year)

    if subject_date is not None:
        issues: list[str] = []
        if body_date is not None and body_date != subject_date:
            issues.append(WorkReportIssueCode.DATE_MISMATCH.value)
        receipt_gap = (received_at.date() - subject_date).days
        if receipt_gap < 0 or receipt_gap > 1:
            if WorkReportIssueCode.DATE_MISMATCH.value not in issues:
                issues.append(WorkReportIssueCode.DATE_MISMATCH.value)
        return WorkDateResolution(
            candidate_date=subject_date,
            subject_date=subject_date,
            body_date=body_date,
            source=WorkDateSource.SUBJECT,
            requires_review=bool(issues),
            issue_codes=tuple(issues),
        )

    if body_date is not None:
        return WorkDateResolution(
            candidate_date=body_date,
            subject_date=None,
            body_date=body_date,
            source=WorkDateSource.BODY,
            requires_review=True,
            issue_codes=(WorkReportIssueCode.DATE_SUBJECT_MISSING.value,),
        )

    return WorkDateResolution(
        candidate_date=None,
        subject_date=None,
        body_date=None,
        source=WorkDateSource.UNRESOLVED,
        requires_review=True,
        issue_codes=(WorkReportIssueCode.DATE_UNRESOLVED.value,),
    )


def _extract_date(text: str, default_year: int) -> date | None:
    for pattern in _FULL_DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            year = int(match.group("year"))
            if year < 100:
                year += 2000
            return _safe_date(
                year, int(match.group("month")), int(match.group("day"))
            )
    match = _MONTH_DAY_PATTERN.search(text)
    if match:
        return _safe_date(
            default_year, int(match.group("month")), int(match.group("day"))
        )
    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None
