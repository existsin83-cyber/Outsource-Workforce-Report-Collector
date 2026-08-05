"""Shared single-row man-day review/confirm flow.

Used by both the main review grid and the tracking dashboard's detail table
so editing a row behaves identically regardless of where it was opened from.
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import QMessageBox, QWidget

from outsource_mail_collector.application.models import WorkReportRow
from outsource_mail_collector.application.work_report_service import (
    WorkReportService,
)
from outsource_mail_collector.domain.work_report import WorkReportIssueCode
from outsource_mail_collector.ui.problem_review_dialog import (
    ProblemReviewDialog,
)

_NIGHT_ISSUE_CODES = {
    WorkReportIssueCode.NIGHT_HEADCOUNT_UNRESOLVED,
    WorkReportIssueCode.NIGHT_HEADCOUNT_INVALID,
}


def review_single_row(
    row: WorkReportRow,
    work_report_service: WorkReportService,
    parent: QWidget,
) -> bool:
    """Open the edit/confirm dialog for one non-duplicate row.

    Returns True if the row was updated and callers should refresh.
    """

    dialog_arguments: dict[str, object] = {
        "reported_daily": row.reported_daily_man_day,
        "calculated_daily": row.calculated_daily_man_day,
        "reported_cumulative": row.reported_cumulative_man_day,
        "calculated_cumulative": row.calculated_cumulative_man_day,
        "confirmed_daily": _confirmed_candidate(
            row.confirmed_daily_man_day,
            row.reported_daily_man_day,
            row.calculated_daily_man_day,
        ),
        "issue_codes": row.issue_codes,
        "parent": parent,
    }
    if set(row.issue_codes) & _NIGHT_ISSUE_CODES:
        dialog_arguments["actual_headcount"] = row.actual_headcount
        dialog_arguments["night_headcount"] = row.night_headcount
        dialog_arguments["headcount_correction"] = True
    if WorkReportIssueCode.DATE_UNRESOLVED in row.issue_codes:
        dialog_arguments["work_date"] = row.work_date
        dialog_arguments["date_correction"] = True
    if WorkReportIssueCode.SERIES_KEY_MISSING in row.issue_codes:
        dialog_arguments["tracking_no"] = row.tracking_no
        dialog_arguments["series_key_correction"] = True
    dialog = ProblemReviewDialog(**dialog_arguments)
    if dialog.exec() != dialog.DialogCode.Accepted:
        return False
    values = dialog.values()
    resolution_note = str(values["resolution_note"])
    field_changes = {
        field_name: values[field_name]
        for field_name in (
            "actual_headcount",
            "night_headcount",
            "work_date",
            "tracking_no",
        )
        if field_name in values
    }
    try:
        if field_changes:
            work_report_service.update_row(
                row.row_id,
                field_changes,
                resolution_note=resolution_note,
            )
        work_report_service.confirm_row(
            row.row_id,
            confirmed_daily_man_day=values["confirmed_daily_man_day"],
            resolution_note=resolution_note,
        )
    except ValueError as exc:
        QMessageBox.warning(parent, "행 확정 실패", str(exc))
        return False
    return True


def _confirmed_candidate(
    confirmed: Decimal | None,
    reported: Decimal | None,
    calculated: Decimal | None,
) -> Decimal | None:
    if confirmed is not None:
        return confirmed
    if (
        reported is not None
        and calculated is not None
        and reported == calculated
    ):
        return reported
    return None
