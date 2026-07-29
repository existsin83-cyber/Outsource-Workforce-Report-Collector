"""Pure domain types for compiling external-work man-day reports."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class RowSource(str, Enum):
    """Origin of a compiled work-report row."""

    MAIL = "MAIL"
    MANUAL = "MANUAL"


class WorkDateSource(str, Enum):
    """Evidence source selected for the candidate work date."""

    SUBJECT = "SUBJECT"
    BODY = "BODY"
    UNRESOLVED = "UNRESOLVED"


class IssueSeverity(str, Enum):
    """Whether an issue needs review or blocks final confirmation."""

    WARNING = "WARNING"
    BLOCKING = "BLOCKING"


class WorkReportIssueCode(str, Enum):
    """Stable machine-readable issue codes used across services and UI."""

    DATE_MISMATCH = "DATE_MISMATCH"
    DATE_SUBJECT_MISSING = "DATE_SUBJECT_MISSING"
    DATE_UNRESOLVED = "DATE_UNRESOLVED"
    DAILY_MISSING = "DAILY_MISSING"
    DAILY_MISMATCH = "DAILY_MISMATCH"
    CUMULATIVE_MISSING = "CUMULATIVE_MISSING"
    CUMULATIVE_MISMATCH = "CUMULATIVE_MISMATCH"
    CUMULATIVE_BASELINE_CONFIRMATION = "CUMULATIVE_BASELINE_CONFIRMATION"
    CUMULATIVE_BASELINE_REQUIRED = "CUMULATIVE_BASELINE_REQUIRED"
    DUPLICATE_UNRESOLVED = "DUPLICATE_UNRESOLVED"
    SERIES_KEY_MISSING = "SERIES_KEY_MISSING"
    INVALID_VALUE = "INVALID_VALUE"
    ACTUAL_HEADCOUNT_INVALID = "ACTUAL_HEADCOUNT_INVALID"
    REPORTED_DAILY_INVALID = "REPORTED_DAILY_INVALID"
    REPORTED_CUMULATIVE_INVALID = "REPORTED_CUMULATIVE_INVALID"
    WORK_ORDER_UNREGISTERED = "WORK_ORDER_UNREGISTERED"
    EQUIPMENT_MAPPING_MISMATCH = "EQUIPMENT_MAPPING_MISMATCH"
    NIGHT_HEADCOUNT_UNRESOLVED = "NIGHT_HEADCOUNT_UNRESOLVED"
    NIGHT_HEADCOUNT_INVALID = "NIGHT_HEADCOUNT_INVALID"


def man_day_basis(
    actual_headcount: int | None,
    night_headcount: int | None,
) -> str:
    """Return the per-person basis label derived from headcount evidence."""

    if actual_headcount is None or night_headcount is None:
        return "확인 필요"
    if (
        actual_headcount < 0
        or night_headcount < 0
        or night_headcount > actual_headcount
    ):
        return "확인 필요"
    if night_headcount == 0:
        return "1.0"
    if night_headcount == actual_headcount:
        return "1.5"
    return "혼합"


@dataclass(frozen=True)
class ManDayValues:
    """Reported, calculated, and currently usable candidate man-day values."""

    reported: Decimal | None
    calculated: Decimal | None
    confirmed_candidate: Decimal | None
    issues: tuple[WorkReportIssueCode, ...] = ()
