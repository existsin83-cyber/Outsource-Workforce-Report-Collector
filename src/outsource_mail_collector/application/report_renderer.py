"""Pure HTML and plain-text rendering for immutable final snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from html import escape
from itertools import groupby

from outsource_mail_collector.application.models import (
    FinalReportRow,
    FinalReportSnapshot,
)


_HEADERS = (
    "일자",
    "거래처명",
    "Tracking No.",
    "장비명",
    "사업팀",
    "실제 작업인원",
    "야근 인원",
    "인당 공수",
    "투입 공수",
    "누적 공수",
)
_WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")
_TABLE_STYLE = (
    "border-collapse:collapse;font-family:맑은 고딕,Arial,sans-serif;"
    "font-size:10pt;margin:8px 0 14px 0;"
)
_CELL_STYLE = (
    "border:1px solid #555;padding:5px 7px;text-align:center;"
    "white-space:nowrap;"
)
_HEADER_STYLE = _CELL_STYLE + "background:#d9d9d9;font-weight:bold;"


@dataclass(frozen=True)
class RenderedReport:
    html: str
    plain_text: str


class HtmlReportRenderer:
    """Render only confirmed snapshot values, with no repository access."""

    def render(self, snapshot: FinalReportSnapshot) -> RenderedReport:
        title = _title(snapshot.date_from, snapshot.date_to)
        html_parts = [
            '<div style="font-family:맑은 고딕,Arial,sans-serif;">',
            f'<div style="margin-bottom:10px;">{escape(title)}</div>',
        ]
        plain_parts = [title]

        for work_date, grouped in groupby(
            snapshot.rows, key=lambda row: row.work_date
        ):
            rows = tuple(grouped)
            html_parts.append(f'<table style="{_TABLE_STYLE}">')
            html_parts.append(
                "<tr>"
                + "".join(
                    f'<th style="{_HEADER_STYLE}">{escape(header)}</th>'
                    for header in _HEADERS
                )
                + "</tr>"
            )
            plain_parts.append("\t".join(_HEADERS))
            for row in rows:
                values = _row_values(row)
                html_parts.append(
                    "<tr>"
                    + "".join(
                        f'<td style="{_CELL_STYLE}">{escape(value)}</td>'
                        for value in values
                    )
                    + "</tr>"
                )
                plain_parts.append("\t".join(values))
            html_parts.append("</table>")
        html_parts.append("</div>")
        return RenderedReport(
            html="".join(html_parts),
            plain_text="\n".join(plain_parts),
        )


def _row_values(row: FinalReportRow) -> tuple[str, ...]:
    return (
        f"{row.work_date:%Y-%m-%d} ({_WEEKDAYS[row.work_date.weekday()]})",
        row.vendor_name,
        row.tracking_no or "",
        row.equipment_name or "",
        row.business_team or "",
        str(int(row.actual_headcount)),
        (
            str(row.night_headcount)
            if row.night_headcount is not None
            else ""
        ),
        row.man_day_basis,
        f"{row.confirmed_daily_man_day:.1f}",
        f"{row.confirmed_cumulative_man_day:.1f}",
    )


def _title(date_from: date, date_to: date) -> str:
    start = _display_date(date_from)
    if date_from == date_to:
        return f"{start} 전장 외주 공수표"
    return f"{start} ~ {_display_date(date_to)} 전장 외주 공수표"


def _display_date(value: date) -> str:
    return f"{value:%Y. %m. %d} ({_WEEKDAYS[value.weekday()]})"
