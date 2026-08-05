from datetime import date
from decimal import Decimal

from outsource_mail_collector.application.models import (
    FinalReportRow,
    FinalReportSnapshot,
)
from outsource_mail_collector.application.report_renderer import (
    HtmlReportRenderer,
)


def test_renderer_uses_nine_approved_columns_and_escapes_html() -> None:
    snapshot = _snapshot(
        rows=(
            _row(
                vendor_name="업체 <A>",
                equipment_name="장비 & 1",
            ),
        )
    )

    rendered = HtmlReportRenderer().render(snapshot)

    headers = [
        "일자",
        "거래처명",
        "Tracking No.",
        "장비명",
        "사업팀",
        "실제 작업인원",
        "인당 공수",
        "투입 공수",
        "누적 공수",
    ]
    assert all(header in rendered.html for header in headers)
    assert rendered.html.index("일자") < rendered.html.index("거래처명")
    assert "업체 &lt;A&gt;" in rendered.html
    assert "장비 &amp; 1" in rendered.html
    assert "실제 작업인원\t인당 공수" in rendered.plain_text
    assert "야근 인원" not in rendered.html
    assert "3\t혼합\t3.5\t20.0" in rendered.plain_text
    assert "ENTRY" not in rendered.html
    assert "issue" not in rendered.html
    assert "calculated" not in rendered.html


def test_renderer_produces_a_single_table_across_multiple_tracking_dates() -> None:
    snapshot = _snapshot(
        date_to=date(2026, 7, 30),
        rows=(
            _row(work_date=date(2026, 7, 29)),
            _row(work_date=date(2026, 7, 30), tracking_no="AB260102"),
        ),
    )

    rendered = HtmlReportRenderer().render(snapshot)

    assert rendered.html.count("<table") == 1
    assert rendered.html.count("<th") == 9
    assert rendered.plain_text.count("일자\t거래처명") == 1
    assert "2026. 07. 29 (수) ~ 2026. 07. 30 (목) 전장 외주 공수표" in (
        rendered.html
    )


def test_single_date_title_is_not_rendered_as_range() -> None:
    rendered = HtmlReportRenderer().render(_snapshot())

    assert "2026. 07. 29 (수) 전장 외주 공수표" in rendered.html
    assert " ~ " not in rendered.plain_text.splitlines()[0]


def _snapshot(
    *,
    date_to: date = date(2026, 7, 29),
    rows: tuple[FinalReportRow, ...] | None = None,
) -> FinalReportSnapshot:
    return FinalReportSnapshot(
        report_id=1,
        date_from=date(2026, 7, 29),
        date_to=date_to,
        snapshot_hash="hash",
        confirmed_at="2026-07-29T09:00:00+00:00",
        copied_at=None,
        invalidated_at=None,
        rows=rows or (_row(),),
    )


def _row(
    *,
    work_date: date = date(2026, 7, 29),
    vendor_name: str = "업체A",
    tracking_no: str = "AB260101",
    equipment_name: str = "장비 1",
    actual_headcount: int = 3,
    night_headcount: int | None = 1,
    man_day_basis: str = "혼합",
) -> FinalReportRow:
    return FinalReportRow(
        source_row_id=1,
        work_date=work_date,
        vendor_name=vendor_name,
        vendor_sort_order=1,
        tracking_no=tracking_no,
        equipment_name=equipment_name,
        business_team="WA",
        actual_headcount=actual_headcount,
        night_headcount=night_headcount,
        man_day_basis=man_day_basis,
        confirmed_daily_man_day=Decimal("3.5"),
        confirmed_cumulative_man_day=Decimal("20.0"),
    )
