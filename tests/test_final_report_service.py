from datetime import date
from decimal import Decimal

import pytest

from outsource_mail_collector.application.final_report_service import (
    FinalReportService,
    FinalizationError,
)
from outsource_mail_collector.domain.models import ReviewStatus
from outsource_mail_collector.domain.work_report import WorkReportIssueCode
from outsource_mail_collector.infrastructure.db.repository import SQLiteRepository


def test_preview_blocks_included_warning_until_individually_confirmed(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    row = _create_ready_row(
        repository,
        vendor_name="업체A",
        issue_codes=(WorkReportIssueCode.DAILY_MISSING,),
        warning_confirmed=False,
    )
    service = FinalReportService(repository)

    preview = service.preview(date(2026, 7, 29), date(2026, 7, 29))

    assert preview.can_confirm is False
    assert preview.blockers[0].row_id == row.row_id
    assert preview.blockers[0].code == "WARNING_UNCONFIRMED"
    with pytest.raises(FinalizationError):
        service.confirm(date(2026, 7, 29), date(2026, 7, 29))


@pytest.mark.parametrize(
    "issue",
    [
        WorkReportIssueCode.DUPLICATE_UNRESOLVED,
        WorkReportIssueCode.CUMULATIVE_BASELINE_REQUIRED,
        WorkReportIssueCode.INVALID_VALUE,
    ],
)
def test_preview_blocks_structural_issues(tmp_path, issue):
    repository = SQLiteRepository(tmp_path / "collector.db")
    _create_ready_row(
        repository,
        vendor_name="업체A",
        issue_codes=(issue,),
        warning_confirmed=True,
    )

    preview = FinalReportService(repository).preview(
        date(2026, 7, 29), date(2026, 7, 29)
    )

    assert preview.can_confirm is False
    assert preview.blockers[0].code == issue.value


def test_excluded_rows_do_not_block_finalization(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    _create_ready_row(
        repository,
        vendor_name="업체A",
        confirmed_daily_man_day=None,
        included=False,
        review_status=ReviewStatus.EXCLUDED,
    )

    preview = FinalReportService(repository).preview(
        date(2026, 7, 29), date(2026, 7, 29)
    )

    assert preview.can_confirm is True
    assert preview.rows == ()


def test_preview_uses_vendor_configuration_order_then_tracking(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    repository.save_vendor(None, "업체B", [], True)
    repository.save_vendor(None, "업체A", [], True)
    _create_ready_row(
        repository, vendor_name="업체A", tracking_no="A-01"
    )
    _create_ready_row(
        repository, vendor_name="업체B", tracking_no="B-02"
    )
    _create_ready_row(
        repository, vendor_name="업체B", tracking_no="B-01"
    )

    preview = FinalReportService(repository).preview(
        date(2026, 7, 29), date(2026, 7, 29)
    )

    assert [
        (row.vendor_name, row.tracking_no) for row in preview.rows
    ] == [
        ("업체B", "B-01"),
        ("업체B", "B-02"),
        ("업체A", "A-01"),
    ]


def test_confirmation_snapshots_confirmed_values_and_source_edit_invalidates(
    tmp_path,
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    row = _create_ready_row(repository, vendor_name="업체A")
    service = FinalReportService(repository)

    first = service.confirm(date(2026, 7, 29), date(2026, 7, 29))
    repository.update_work_report_row(
        row.row_id,
        {"confirmed_daily_man_day": Decimal("4.0")},
        resolution_note="정정",
    )
    stored_first = repository.get_final_report(first.report_id)

    assert stored_first.invalidated_at is not None
    assert stored_first.rows[0].confirmed_daily_man_day == Decimal("3.0")
    second = service.confirm(date(2026, 7, 29), date(2026, 7, 29))
    assert second.report_id != first.report_id
    assert second.rows[0].confirmed_daily_man_day == Decimal("4.0")


def _create_ready_row(
    repository: SQLiteRepository,
    *,
    vendor_name: str,
    tracking_no: str = "AB260101",
    issue_codes: tuple[WorkReportIssueCode, ...] = (),
    warning_confirmed: bool = True,
    confirmed_daily_man_day: Decimal | None = Decimal("3.0"),
    included: bool = True,
    review_status: ReviewStatus = ReviewStatus.REVIEWED,
):
    return repository.create_manual_report_row(
        work_date=date(2026, 7, 29),
        work_date_confirmed=True,
        vendor_name=vendor_name,
        tracking_no=tracking_no,
        equipment_name="장비 1",
        business_team="WA",
        actual_headcount=2,
        per_person_man_day=Decimal("1.5"),
        reported_daily_man_day=confirmed_daily_man_day,
        calculated_daily_man_day=confirmed_daily_man_day,
        confirmed_daily_man_day=confirmed_daily_man_day,
        reported_cumulative_man_day=Decimal("12.0"),
        calculated_cumulative_man_day=Decimal("12.0"),
        confirmed_cumulative_man_day=Decimal("12.0"),
        cumulative_series_key=f"{vendor_name.casefold()}|T:{tracking_no}",
        issue_codes=issue_codes,
        review_status=review_status,
        included=included,
        warning_confirmed=warning_confirmed,
        resolution_note="테스트 준비",
    )
