from datetime import date
from decimal import Decimal
from importlib import import_module

import pytest

from outsource_mail_collector.domain.models import ReviewStatus
from outsource_mail_collector.domain.work_report import WorkReportIssueCode
from outsource_mail_collector.infrastructure.db.repository import SQLiteRepository


def test_dashboard_has_one_lifetime_summary_and_separate_daily_rows(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    repository.save_cumulative_baseline(
        tracking_no="AB260101",
        effective_through_date=date(2026, 7, 27),
        cumulative_man_day=Decimal("20.0"),
        resolution_note="테스트 기준",
    )
    first = _create_row(
        repository,
        work_date=date(2026, 7, 28),
        confirmed_daily=Decimal("2.0"),
        reported_cumulative=Decimal("22.0"),
        calculated_cumulative=Decimal("22.0"),
        confirmed_cumulative=Decimal("22.0"),
    )
    second = _create_row(
        repository,
        work_date=date(2026, 7, 29),
        confirmed_daily=Decimal("3.0"),
        reported_cumulative=Decimal("25.0"),
        calculated_cumulative=Decimal("25.0"),
        confirmed_cumulative=Decimal("25.0"),
    )
    service = _dashboard_service(repository)

    daily = service.daily_aggregates(
        date(2026, 7, 28), date(2026, 7, 29)
    )
    summaries = service.summaries()

    assert [(row.work_date, row.tracking_no) for row in daily] == [
        (date(2026, 7, 28), "AB260101"),
        (date(2026, 7, 29), "AB260101"),
    ]
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.normalized_tracking_no == "AB260101"
    assert summary.latest_work_date == date(2026, 7, 29)
    assert summary.latest_actual_headcount == 2
    assert summary.latest_night_headcount == 0
    assert summary.latest_man_day_basis == "1.0"
    assert summary.latest_confirmed_daily_man_day == Decimal("3.0")
    assert summary.latest_reported_cumulative_man_day == Decimal("25.0")
    assert summary.latest_calculated_cumulative_man_day == Decimal("25.0")
    assert summary.initial_cumulative_man_day == Decimal("20.0")
    assert summary.latest_confirmed_cumulative_man_day == Decimal("25.0")
    assert summary.source_row_ids == (first.row_id, second.row_id)


def test_dashboard_separates_completed_tracking_numbers_and_preserves_start_date(
    tmp_path,
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    _create_row(
        repository,
        work_date=date(2026, 7, 29),
        confirmed_daily=Decimal("3.0"),
        reported_cumulative=Decimal("3.0"),
        calculated_cumulative=Decimal("3.0"),
        confirmed_cumulative=Decimal("3.0"),
    )
    service = _dashboard_service(repository)
    service.set_start_date("AB260101", date(2026, 7, 28))
    service.complete("AB260101")

    assert service.summaries() == ()
    completed = service.completed_summaries()
    assert len(completed) == 1
    assert completed[0].start_date == date(2026, 7, 28)
    service.resume("AB260101")
    assert len(service.summaries()) == 1


def test_active_daily_aggregates_exclude_completed_tracking_and_keep_drill_down(
    tmp_path,
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    completed_row = _create_row(repository, tracking_no="A-01")
    _create_row(repository, tracking_no="B-01")
    service = _dashboard_service(repository)
    service.complete("A-01")

    active = service.active_daily_aggregates()

    assert [row.tracking_no for row in active] == ["B-01"]
    assert [row.row_id for row in service.drill_down("A-01")] == [
        completed_row.row_id
    ]


def test_completion_rejects_unknown_tracking_without_creating_status(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _dashboard_service(repository)

    with pytest.raises(ValueError, match="존재하지"):
        service.complete("UNKNOWN")
    with pytest.raises(ValueError, match="존재하지"):
        service.resume("UNKNOWN")
    assert repository.list_tracking_work_status() == []


def test_completion_uses_first_work_date_and_records_one_completion_action(
    tmp_path,
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    _create_row(repository, work_date=date(2026, 7, 30))
    _create_row(repository, work_date=date(2026, 7, 29))
    service = _dashboard_service(repository)

    service.complete("AB260101")

    status = repository.get_tracking_work_status("AB260101")
    assert status is not None
    assert status.start_date == date(2026, 7, 29)
    assert status.completed_at is not None
    assert [log.action for log in repository.list_action_logs()[-1:]] == [
        "TRACKING_COMPLETED"
    ]


def test_dashboard_calculates_baseline_plus_confirmed_daily(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    repository.save_cumulative_baseline(
        tracking_no="AB260101",
        effective_through_date=date(2026, 7, 28),
        cumulative_man_day=Decimal("20.0"),
        resolution_note="테스트 기준",
    )
    _create_row(
        repository,
        work_date=date(2026, 7, 29),
        confirmed_daily=Decimal("3.0"),
        reported_cumulative=Decimal("23.0"),
        calculated_cumulative=Decimal("999.0"),
        confirmed_cumulative=Decimal("23.0"),
    )

    daily = _dashboard_service(repository).daily_aggregates(
        date(2026, 7, 29), date(2026, 7, 29)
    )

    assert daily[0].calculated_cumulative_man_day == Decimal("23.0")
    assert daily[0].confirmed_cumulative_man_day == Decimal("23.0")
    assert daily[0].blockers == ()


def test_reported_cumulative_mismatch_blocks_against_calculated_value(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    repository.save_cumulative_baseline(
        tracking_no="AB260101",
        effective_through_date=date(2026, 7, 28),
        cumulative_man_day=Decimal("30.0"),
        resolution_note="테스트 기준",
    )
    _create_row(
        repository,
        work_date=date(2026, 7, 29),
        confirmed_daily=Decimal("3.0"),
        reported_cumulative=Decimal("30.0"),
        calculated_cumulative=Decimal("30.0"),
        confirmed_cumulative=Decimal("30.0"),
    )

    aggregate = _dashboard_service(repository).daily_aggregates(
        date(2026, 7, 29), date(2026, 7, 29)
    )[0]

    assert aggregate.calculated_cumulative_man_day == Decimal("33.0")
    assert any(
        blocker.code == WorkReportIssueCode.CUMULATIVE_MISMATCH.value
        for blocker in aggregate.blockers
    )


def test_excluded_and_deleted_rows_do_not_contribute_but_drilldown_is_lifetime(
    tmp_path,
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    prior = _create_row(
        repository,
        work_date=date(2026, 7, 28),
        confirmed_daily=Decimal("1.0"),
        reported_cumulative=Decimal("11.0"),
        calculated_cumulative=Decimal("11.0"),
        confirmed_cumulative=Decimal("11.0"),
    )
    active = _create_row(repository)
    excluded = _create_row(repository, included=False)
    deleted = _create_row(repository)
    repository.soft_delete_work_report_row(
        deleted.row_id, resolution_note="테스트 삭제"
    )
    service = _dashboard_service(repository)

    aggregate = service.daily_aggregates(
        date(2026, 7, 29), date(2026, 7, 29)
    )[0]
    drilldown = service.drill_down(" ab 260101 ")

    assert aggregate.source_row_ids == (active.row_id,)
    assert [row.row_id for row in drilldown] == [prior.row_id, active.row_id]
    assert excluded.row_id not in aggregate.source_row_ids
    assert deleted.row_id not in aggregate.source_row_ids


def test_missing_values_and_unmapped_identity_conflicts_block_without_guessing(
    tmp_path,
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    first = _create_row(
        repository,
        vendor_name="업체A",
        equipment_name="장비A",
        business_team="팀A",
        actual_headcount=None,
        confirmed_daily=None,
    )
    second = _create_row(
        repository,
        vendor_name="업체B",
        equipment_name="장비B",
        business_team="팀B",
    )

    aggregate = _dashboard_service(repository).daily_aggregates(
        date(2026, 7, 29), date(2026, 7, 29)
    )[0]

    assert aggregate.source_row_ids == (first.row_id, second.row_id)
    assert aggregate.vendor_name is None
    assert aggregate.equipment_name is None
    assert aggregate.business_team is None
    assert aggregate.actual_headcount is None
    assert aggregate.confirmed_daily_man_day is None
    assert {blocker.code for blocker in aggregate.blockers} >= {
        "IDENTITY_CONFLICT",
        "REQUIRED_FIELD_MISSING",
        "CONFIRMED_MAN_DAY_MISSING",
    }


def test_active_mapping_is_canonical_for_conflicting_source_identity(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    vendor = repository.save_vendor(None, "기준 업체", [], True)
    repository.save_work_order_mapping(
        None,
        "AB260101",
        "기준 장비",
        vendor.vendor_id,
        "기준 팀",
        True,
    )
    _create_row(
        repository,
        vendor_name="메일 업체 A",
        equipment_name="메일 장비 A",
        business_team="메일 팀 A",
    )
    _create_row(
        repository,
        vendor_name="메일 업체 B",
        equipment_name="메일 장비 B",
        business_team="메일 팀 B",
    )

    aggregate = _dashboard_service(repository).daily_aggregates(
        date(2026, 7, 29), date(2026, 7, 29)
    )[0]

    assert aggregate.tracking_no == "AB260101"
    assert aggregate.vendor_name == "기준 업체"
    assert aggregate.equipment_name == "기준 장비"
    assert aggregate.business_team == "기준 팀"
    assert all(
        blocker.code != "IDENTITY_CONFLICT"
        for blocker in aggregate.blockers
    )


def test_cross_date_identity_conflict_blocks_lifetime_and_final_preview(
    tmp_path,
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    first = _create_row(
        repository,
        work_date=date(2026, 7, 28),
        vendor_name="업체A",
        equipment_name="장비A",
        business_team="팀A",
        reported_cumulative=Decimal("12.0"),
        calculated_cumulative=Decimal("12.0"),
        confirmed_cumulative=Decimal("12.0"),
    )
    second = _create_row(
        repository,
        work_date=date(2026, 7, 29),
        vendor_name="업체B",
        equipment_name="장비B",
        business_team="팀B",
        reported_cumulative=Decimal("14.0"),
        calculated_cumulative=Decimal("14.0"),
        confirmed_cumulative=Decimal("14.0"),
    )
    dashboard = _dashboard_service(repository)

    summary = dashboard.summaries()[0]
    preview = _final_report_service(repository).preview()

    assert summary.source_row_ids == (first.row_id, second.row_id)
    assert summary.vendor_name is None
    assert summary.equipment_name is None
    assert summary.business_team is None
    assert any(
        blocker.code == "IDENTITY_CONFLICT"
        for blocker in summary.blockers
    )
    assert preview.can_confirm is False
    assert any(
        blocker.code == "IDENTITY_CONFLICT"
        for blocker in preview.blockers
    )


def test_active_mapping_is_canonical_across_dates(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    vendor = repository.save_vendor(None, "기준 업체", [], True)
    repository.save_work_order_mapping(
        None,
        "AB260101",
        "기준 장비",
        vendor.vendor_id,
        "기준 팀",
        True,
    )
    _create_row(
        repository,
        work_date=date(2026, 7, 28),
        vendor_name="메일 업체 A",
        equipment_name="메일 장비 A",
        business_team="메일 팀 A",
        reported_cumulative=Decimal("12.0"),
        calculated_cumulative=Decimal("12.0"),
        confirmed_cumulative=Decimal("12.0"),
    )
    _create_row(
        repository,
        work_date=date(2026, 7, 29),
        vendor_name="메일 업체 B",
        equipment_name="메일 장비 B",
        business_team="메일 팀 B",
        reported_cumulative=Decimal("14.0"),
        calculated_cumulative=Decimal("14.0"),
        confirmed_cumulative=Decimal("14.0"),
    )
    service = _dashboard_service(repository)

    summary = service.summaries()[0]
    daily = service.daily_aggregates(
        date(2026, 7, 28), date(2026, 7, 29)
    )

    assert (
        summary.vendor_name,
        summary.equipment_name,
        summary.business_team,
    ) == ("기준 업체", "기준 장비", "기준 팀")
    assert [
        (row.vendor_name, row.equipment_name, row.business_team)
        for row in daily
    ] == [
        ("기준 업체", "기준 장비", "기준 팀"),
        ("기준 업체", "기준 장비", "기준 팀"),
    ]
    assert all(
        blocker.code != "IDENTITY_CONFLICT"
        for row in daily
        for blocker in row.blockers
    )


def test_unresolved_date_row_remains_visible_and_blocks_finalization(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    unresolved = _create_row(
        repository,
        work_date=None,
        work_date_confirmed=False,
    )
    dashboard = _dashboard_service(repository)
    final_report = _final_report_service(repository)

    summaries = dashboard.summaries()
    preview = final_report.preview()

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.latest_work_date is None
    assert summary.source_row_ids == (unresolved.row_id,)
    assert any(
        blocker.code == "WORK_DATE_UNCONFIRMED"
        for blocker in summary.blockers
    )
    assert len(preview.rows) == 1
    assert preview.rows[0].work_date is None
    assert preview.rows[0].source_row_ids == (unresolved.row_id,)
    assert preview.can_confirm is False
    assert any(
        blocker.code == "WORK_DATE_UNCONFIRMED"
        for blocker in preview.blockers
    )

    from outsource_mail_collector.application.final_report_service import (
        FinalizationError,
    )
    import pytest

    with pytest.raises(FinalizationError):
        final_report.confirm()


def test_missing_tracking_blocks_even_when_equipment_is_present(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    _create_row(
        repository,
        tracking_no="",
        equipment_name="장비1",
    )

    aggregate = _dashboard_service(repository).daily_aggregates(
        date(2026, 7, 29), date(2026, 7, 29)
    )[0]

    assert aggregate.normalized_tracking_no == ""
    assert any(
        blocker.code == "TRACKING_NO_MISSING"
        for blocker in aggregate.blockers
    )


def _dashboard_service(repository: SQLiteRepository):
    module = import_module(
        "outsource_mail_collector.application.tracking_dashboard_service"
    )
    service_type = getattr(module, "TrackingDashboardService", None)
    assert service_type is not None
    return service_type(repository)


def _final_report_service(repository: SQLiteRepository):
    module = import_module(
        "outsource_mail_collector.application.final_report_service"
    )
    return module.FinalReportService(repository)


def _create_row(
    repository: SQLiteRepository,
    *,
    work_date: date | None = date(2026, 7, 29),
    work_date_confirmed: bool = True,
    tracking_no: str = "AB260101",
    vendor_name: str | None = "업체A",
    equipment_name: str | None = "장비1",
    business_team: str | None = "팀1",
    actual_headcount: int | None = 2,
    night_headcount: int | None = 0,
    confirmed_daily: Decimal | None = Decimal("2.0"),
    reported_cumulative: Decimal | None = Decimal("12.0"),
    calculated_cumulative: Decimal | None = Decimal("12.0"),
    confirmed_cumulative: Decimal | None = Decimal("12.0"),
    issue_codes: tuple[WorkReportIssueCode, ...] = (),
    included: bool = True,
):
    return repository.create_manual_report_row(
        work_date=work_date,
        work_date_confirmed=work_date_confirmed,
        vendor_name=vendor_name,
        tracking_no=tracking_no,
        equipment_name=equipment_name,
        business_team=business_team,
        actual_headcount=actual_headcount,
        night_headcount=night_headcount,
        per_person_man_day=Decimal("1.0"),
        reported_daily_man_day=confirmed_daily,
        calculated_daily_man_day=confirmed_daily,
        confirmed_daily_man_day=confirmed_daily,
        reported_cumulative_man_day=reported_cumulative,
        calculated_cumulative_man_day=calculated_cumulative,
        confirmed_cumulative_man_day=confirmed_cumulative,
        cumulative_series_key="".join(tracking_no.split()).upper(),
        issue_codes=issue_codes,
        review_status=ReviewStatus.REVIEWED,
        included=included,
        warning_confirmed=True,
        resolution_note="테스트 준비",
    )
