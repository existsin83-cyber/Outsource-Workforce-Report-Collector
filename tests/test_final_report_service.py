import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from outsource_mail_collector.application.final_report_service import (
    FinalReportService,
    FinalizationError,
)
from outsource_mail_collector.application.models import (
    final_report_snapshot_from_stored,
)
from outsource_mail_collector.domain.models import ReviewStatus
from outsource_mail_collector.domain.work_report import (
    WorkReportIssueCode,
    man_day_basis,
)
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
        WorkReportIssueCode.WORK_ORDER_UNREGISTERED,
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


def test_preview_explains_how_to_fix_unregistered_work_order(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    _create_ready_row(
        repository,
        vendor_name="업체A",
        issue_codes=(WorkReportIssueCode.WORK_ORDER_UNREGISTERED,),
    )

    preview = FinalReportService(repository).preview(
        date(2026, 7, 29), date(2026, 7, 29)
    )

    blocker = next(
        item
        for item in preview.blockers
        if item.code == WorkReportIssueCode.WORK_ORDER_UNREGISTERED.value
    )
    assert "수주" in blocker.message
    assert "설정" in blocker.message


def test_preview_names_the_missing_confirmed_man_day_field(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    _create_ready_row(
        repository,
        vendor_name="업체A",
        confirmed_daily_man_day=None,
        confirmed_cumulative_man_day=Decimal("12.0"),
    )

    preview = FinalReportService(repository).preview(
        date(2026, 7, 29), date(2026, 7, 29)
    )

    blocker = next(
        item
        for item in preview.blockers
        if item.code == "CONFIRMED_MAN_DAY_MISSING"
    )
    assert "확정 투입" in blocker.message
    assert "확정 누적" not in blocker.message


def test_preview_names_each_missing_required_field(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    _create_ready_row(
        repository,
        vendor_name="업체A",
        tracking_no="",
        equipment_name=None,
        business_team=None,
    )

    preview = FinalReportService(repository).preview(
        date(2026, 7, 29), date(2026, 7, 29)
    )

    blocker = next(
        item
        for item in preview.blockers
        if item.code == "REQUIRED_FIELD_MISSING"
    )
    assert "사업팀" in blocker.message
    assert "Tracking No. 또는 장비명" in blocker.message


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


def test_preview_allows_mixed_headcount_without_uniform_per_person_value(
    tmp_path,
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    _create_ready_row(
        repository,
        vendor_name="업체A",
        actual_headcount=3,
        night_headcount=1,
        per_person_man_day=None,
        confirmed_daily_man_day=Decimal("3.5"),
        confirmed_cumulative_man_day=Decimal("20.0"),
    )

    preview = FinalReportService(repository).preview(
        date(2026, 7, 29), date(2026, 7, 29)
    )

    assert preview.can_confirm is True


def test_preview_blocks_unresolved_night_headcount(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    _create_ready_row(
        repository,
        vendor_name="업체A",
        night_headcount=None,
        issue_codes=(WorkReportIssueCode.NIGHT_HEADCOUNT_UNRESOLVED,),
        warning_confirmed=True,
    )

    preview = FinalReportService(repository).preview(
        date(2026, 7, 29), date(2026, 7, 29)
    )

    assert preview.can_confirm is False


@pytest.mark.parametrize(
    ("actual_headcount", "night_headcount"),
    [
        (-1, 0),
        (2, -1),
        (2, 3),
    ],
)
def test_preview_blocks_invalid_headcount_relationship_without_issue_code(
    tmp_path,
    actual_headcount,
    night_headcount,
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    _create_ready_row(
        repository,
        vendor_name="업체A",
        actual_headcount=actual_headcount,
        night_headcount=night_headcount,
        per_person_man_day=Decimal("1.5"),
        issue_codes=(),
    )

    preview = FinalReportService(repository).preview(
        date(2026, 7, 29), date(2026, 7, 29)
    )

    assert preview.can_confirm is False
    assert any(
        blocker.code == WorkReportIssueCode.NIGHT_HEADCOUNT_INVALID.value
        for blocker in preview.blockers
    )


@pytest.mark.parametrize(
    ("actual_headcount", "night_headcount"),
    [
        (-1, 0),
        (2, -1),
        (2, 3),
    ],
)
def test_man_day_basis_does_not_label_invalid_counts_as_mixed(
    actual_headcount,
    night_headcount,
):
    assert man_day_basis(actual_headcount, night_headcount) == "확인 필요"


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


def test_confirmation_snapshots_mixed_basis_and_night_headcount(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    _create_ready_row(
        repository,
        vendor_name="업체A",
        actual_headcount=3,
        night_headcount=1,
        per_person_man_day=None,
        confirmed_daily_man_day=Decimal("3.5"),
        confirmed_cumulative_man_day=Decimal("20.0"),
    )

    snapshot = FinalReportService(repository).confirm(
        date(2026, 7, 29), date(2026, 7, 29)
    )

    assert snapshot.rows[0].night_headcount == 1
    assert snapshot.rows[0].man_day_basis == "혼합"


def test_snapshot_hash_distinguishes_mixed_night_headcounts(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    row = _create_ready_row(
        repository,
        vendor_name="업체A",
        actual_headcount=4,
        night_headcount=1,
        per_person_man_day=None,
        confirmed_daily_man_day=Decimal("4.5"),
    )
    service = FinalReportService(repository)

    first = service.confirm(date(2026, 7, 29), date(2026, 7, 29))
    repository.update_work_report_row(
        row.row_id,
        {"night_headcount": 2},
        resolution_note="야근 인원 정정",
    )
    second = service.confirm(date(2026, 7, 29), date(2026, 7, 29))

    assert first.rows[0].man_day_basis == "혼합"
    assert second.rows[0].man_day_basis == "혼합"
    assert first.snapshot_hash != second.snapshot_hash


def test_legacy_snapshot_without_night_keeps_stored_basis(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    with sqlite3.connect(repository.db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO final_reports(
                date_from, date_to, snapshot_hash, confirmed_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                "2026-07-29",
                "2026-07-29",
                "legacy-hash",
                "2026-07-29T09:00:00+00:00",
            ),
        )
        report_id = int(cursor.lastrowid)
        conn.execute(
            """
            INSERT INTO final_report_rows(
                report_id, source_row_id, work_date, vendor_name,
                vendor_sort_order, tracking_no, equipment_name, business_team,
                actual_headcount, night_headcount, per_person_man_day,
                confirmed_daily_man_day, confirmed_cumulative_man_day
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                1,
                "2026-07-29",
                "업체A",
                1,
                "AB260101",
                "장비 1",
                "WA",
                2,
                None,
                "1.5",
                "3.0",
                "12.0",
            ),
        )

    snapshot = final_report_snapshot_from_stored(
        repository.get_final_report(report_id)
    )

    assert snapshot.rows[0].night_headcount is None
    assert snapshot.rows[0].man_day_basis == "1.5"


def _create_ready_row(
    repository: SQLiteRepository,
    *,
    vendor_name: str,
    tracking_no: str = "AB260101",
    equipment_name: str | None = "장비 1",
    business_team: str | None = "WA",
    actual_headcount: int = 2,
    night_headcount: int | None = 2,
    per_person_man_day: Decimal | None = Decimal("1.5"),
    issue_codes: tuple[WorkReportIssueCode, ...] = (),
    warning_confirmed: bool = True,
    confirmed_daily_man_day: Decimal | None = Decimal("3.0"),
    confirmed_cumulative_man_day: Decimal | None = Decimal("12.0"),
    included: bool = True,
    review_status: ReviewStatus = ReviewStatus.REVIEWED,
):
    return repository.create_manual_report_row(
        work_date=date(2026, 7, 29),
        work_date_confirmed=True,
        vendor_name=vendor_name,
        tracking_no=tracking_no,
        equipment_name=equipment_name,
        business_team=business_team,
        actual_headcount=actual_headcount,
        night_headcount=night_headcount,
        per_person_man_day=per_person_man_day,
        reported_daily_man_day=confirmed_daily_man_day,
        calculated_daily_man_day=confirmed_daily_man_day,
        confirmed_daily_man_day=confirmed_daily_man_day,
        reported_cumulative_man_day=confirmed_cumulative_man_day,
        calculated_cumulative_man_day=confirmed_cumulative_man_day,
        confirmed_cumulative_man_day=confirmed_cumulative_man_day,
        cumulative_series_key=f"{vendor_name.casefold()}|T:{tracking_no}",
        issue_codes=issue_codes,
        review_status=review_status,
        included=included,
        warning_confirmed=warning_confirmed,
        resolution_note="테스트 준비",
    )
