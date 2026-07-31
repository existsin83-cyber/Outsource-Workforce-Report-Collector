from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from outsource_mail_collector.application.man_day_calculation_service import (
    ManDayCalculationService,
)
from outsource_mail_collector.application.work_order_mapping_service import (
    WorkOrderMappingService,
)
from outsource_mail_collector.application.models import ReviewRecord
from outsource_mail_collector.application.work_report_service import (
    WorkReportService,
    build_cumulative_series_key,
)
from outsource_mail_collector.domain.models import ReviewStatus
from outsource_mail_collector.domain.work_report import (
    RowSource,
    WorkReportIssueCode,
)
from outsource_mail_collector.infrastructure.db.repository import SQLiteRepository


def test_synchronize_preserves_reported_values_and_is_idempotent(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    record = _review_record()

    first = service.synchronize_extracted_records([record])
    second = service.synchronize_extracted_records([record])

    assert len(first) == 1
    assert second[0].row_id == first[0].row_id
    row = first[0]
    assert row.source_type is RowSource.MAIL
    assert row.mail_entry_id == "ENTRY-1"
    assert row.night_headcount == 2
    assert row.per_person_man_day == Decimal("1.5")
    assert row.reported_daily_man_day == Decimal("3.0")
    assert row.reported_cumulative_man_day == Decimal("12.0")
    assert row.cumulative_series_key == "AB260101"
    assert row.man_day_confirmed is False


def test_bulk_confirmation_is_atomic_when_any_selected_row_is_not_confirmable(
    tmp_path,
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    service.save_cumulative_baseline(
        tracking_no="AB260101",
        effective_through_date=date(2026, 7, 29),
        cumulative_man_day=Decimal("10.0"),
        resolution_note="initial baseline",
    )
    confirmable = _add_manual_daily(
        service, date(2026, 7, 30), Decimal("3.0")
    )
    blocked = service.synchronize_extracted_records(
        [replace(_review_record(), actual_headcount=None)]
    )[0]

    with pytest.raises(ValueError, match="일괄 확정"):
        service.confirm_rows([confirmable.row_id, blocked.row_id])

    assert repository.get_work_report_row(confirmable.row_id).man_day_confirmed is False


def test_synchronize_enriches_vendor_and_team_from_work_order(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    vendor = repository.save_vendor(None, "Vendor A", [], True)
    repository.save_work_order_mapping(
        None, "AB260101", "Equipment 1", vendor.vendor_id, "PKG", True
    )
    service = WorkReportService(
        repository,
        ManDayCalculationService(),
        WorkOrderMappingService(repository),
    )
    record = replace(
        _review_record(equipment_name="Equipment 1"),
        vendor_name=None,
        business_team=None,
    )

    row = service.synchronize_extracted_records([record])[0]

    assert row.vendor_name == "Vendor A"
    assert row.business_team == "PKG"
    assert WorkReportIssueCode.WORK_ORDER_UNREGISTERED not in row.issue_codes


def test_synchronize_preserves_prepopulated_vendor_and_team(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    mapped_vendor = repository.save_vendor(None, "Mapped Vendor", [], True)
    repository.save_work_order_mapping(
        None,
        "AB260101",
        "Equipment 1",
        mapped_vendor.vendor_id,
        "MAPPED",
        True,
    )
    service = _work_report_service(repository)

    row = service.synchronize_extracted_records(
        [
            replace(
                _review_record(equipment_name="Equipment 1"),
                vendor_name="User Vendor",
                business_team="USER",
            )
        ]
    )[0]

    assert row.vendor_name == "User Vendor"
    assert row.business_team == "USER"


def test_refresh_mapping_fills_existing_unconfirmed_mail_row(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    record = replace(
        _review_record(equipment_name="Equipment 1"),
        vendor_name=None,
        business_team=None,
    )
    original = service.synchronize_extracted_records([record])[0]
    assert WorkReportIssueCode.WORK_ORDER_UNREGISTERED in original.issue_codes

    vendor = repository.save_vendor(None, "Mapped Vendor", [], True)
    repository.save_work_order_mapping(
        None, "AB260101", "Equipment 1", vendor.vendor_id, "PKG", True
    )

    refreshed = service.refresh_work_order_mappings()

    assert refreshed[0].vendor_name == "Mapped Vendor"
    assert refreshed[0].business_team == "PKG"
    assert WorkReportIssueCode.WORK_ORDER_UNREGISTERED not in (
        refreshed[0].issue_codes
    )


def test_tracking_correction_recomputes_mapping_and_clears_unregistered(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    vendor = repository.save_vendor(None, "Mapped Vendor", [], True)
    repository.save_work_order_mapping(
        None, "AB260101", "Equipment 1", vendor.vendor_id, "PKG", True
    )
    service = _work_report_service(repository)
    original = service.synchronize_extracted_records(
        [
            replace(
                _review_record(
                    tracking_no="UNKNOWN",
                    equipment_name="Equipment 1",
                ),
                vendor_name=None,
                business_team=None,
            )
        ]
    )[0]

    updated = service.update_row(
        original.row_id,
        {"tracking_no": "AB260101"},
        resolution_note="수주번호 원문 확인",
    )

    assert updated.vendor_name == "Mapped Vendor"
    assert updated.business_team == "PKG"
    assert WorkReportIssueCode.WORK_ORDER_UNREGISTERED not in updated.issue_codes


def test_equipment_correction_clears_mapping_mismatch(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    vendor = repository.save_vendor(None, "Mapped Vendor", [], True)
    repository.save_work_order_mapping(
        None, "AB260101", "Equipment 1", vendor.vendor_id, "PKG", True
    )
    service = _work_report_service(repository)
    original = service.synchronize_extracted_records(
        [
            replace(
                _review_record(equipment_name="Wrong Equipment"),
                vendor_name=None,
                business_team=None,
            )
        ]
    )[0]
    assert WorkReportIssueCode.EQUIPMENT_MAPPING_MISMATCH in original.issue_codes

    updated = service.update_row(
        original.row_id,
        {"equipment_name": "Equipment 1"},
        resolution_note="장비명 원문 확인",
    )

    assert WorkReportIssueCode.EQUIPMENT_MAPPING_MISMATCH not in (
        updated.issue_codes
    )


def test_mapping_refresh_preserves_user_vendor_and_team_values(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    original = service.synchronize_extracted_records(
        [
            replace(
                _review_record(equipment_name="Equipment 1"),
                vendor_name="User Vendor",
                business_team="USER",
            )
        ]
    )[0]
    assert WorkReportIssueCode.WORK_ORDER_UNREGISTERED in original.issue_codes

    vendor = repository.save_vendor(None, "Mapped Vendor", [], True)
    repository.save_work_order_mapping(
        None, "AB260101", "Equipment 1", vendor.vendor_id, "PKG", True
    )

    refreshed = service.refresh_work_order_mappings()[0]

    assert refreshed.vendor_name == "User Vendor"
    assert refreshed.business_team == "USER"
    assert WorkReportIssueCode.WORK_ORDER_UNREGISTERED not in (
        refreshed.issue_codes
    )


def test_tracking_change_replaces_values_from_previous_mapping(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    old_vendor = repository.save_vendor(None, "Old Vendor", [], True)
    new_vendor = repository.save_vendor(None, "New Vendor", [], True)
    repository.save_work_order_mapping(
        None, "OLD260101", "Equipment Old", old_vendor.vendor_id, "OLD", True
    )
    repository.save_work_order_mapping(
        None, "NEW260101", "Equipment New", new_vendor.vendor_id, "NEW", True
    )
    service = _work_report_service(repository)
    original = service.synchronize_extracted_records(
        [
            replace(
                _review_record(
                    tracking_no="OLD260101",
                    equipment_name="Equipment Old",
                ),
                vendor_name=None,
                business_team=None,
            )
        ]
    )[0]

    updated = service.update_row(
        original.row_id,
        {
            "tracking_no": "NEW260101",
            "equipment_name": "Equipment New",
        },
        resolution_note="수주번호 정정",
    )

    assert updated.vendor_name == "New Vendor"
    assert updated.business_team == "NEW"


def test_series_key_uses_normalized_tracking_only_and_requires_tracking() -> None:
    assert (
        build_cumulative_series_key(" 업체 A ", " ab 260101 ", "장비 1")
        == "AB260101"
    )
    assert (
        build_cumulative_series_key(" 다른 업체 ", "AB260101", "다른 장비")
        == "AB260101"
    )
    assert build_cumulative_series_key("업체 A", None, " 장비   1 ") is None
    assert build_cumulative_series_key("업체 A", None, None) is None


def test_same_date_tracking_rows_are_valid_aggregate_contributors(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)

    rows = service.synchronize_extracted_records(
        [
            _review_record(record_id=1, mail_entry_id="ENTRY-A"),
            replace(
                _review_record(record_id=2, mail_entry_id="ENTRY-B"),
                vendor_name="Vendor B",
                equipment_name="Equipment 2",
            ),
        ]
    )

    assert len(rows) == 2
    assert all(
        WorkReportIssueCode.DUPLICATE_UNRESOLVED not in row.issue_codes
        for row in rows
    )


def test_preexisting_duplicate_evidence_is_kept_for_user_resolution(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    old = replace(
        _review_record(record_id=1, mail_entry_id="ENTRY-OLD"),
        review_status=ReviewStatus.DUPLICATE_SUSPECTED,
    )
    new = replace(
        _review_record(record_id=2, mail_entry_id="ENTRY-NEW"),
        review_status=ReviewStatus.DUPLICATE_SUSPECTED,
    )

    rows = service.synchronize_extracted_records([old, new])

    assert len(rows) == 2
    assert all(
        WorkReportIssueCode.DUPLICATE_UNRESOLVED in row.issue_codes
        for row in rows
    )
    assert [row.reported_daily_man_day for row in rows] == [
        Decimal("3.0"),
        Decimal("3.0"),
    ]

    resolved = service.resolve_duplicate(
        [rows[0].row_id, rows[1].row_id],
        "REPLACE_NEW",
        resolution_note="수정 보고 사용",
    )
    assert [row.included for row in resolved] == [False, True]
    assert WorkReportIssueCode.DUPLICATE_UNRESOLVED not in resolved[1].issue_codes

    synchronized_again = service.synchronize_extracted_records([old, new])
    assert all(
        WorkReportIssueCode.DUPLICATE_UNRESOLVED not in row.issue_codes
        for row in synchronized_again
    )


def test_manual_row_uses_same_calculation_and_can_cover_mail_free_date(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)

    row = service.add_manual_row(
        work_date=date(2026, 8, 1),
        vendor_name="업체A",
        tracking_no="AB260101",
        equipment_name="장비 1",
        business_team="WA",
        actual_headcount=2,
        night_headcount=2,
        reported_daily_man_day=None,
        reported_cumulative_man_day=Decimal("12.0"),
        resolution_note="주말 작업 확인",
    )

    assert row.source_type is RowSource.MANUAL
    assert row.mail_entry_id is None
    assert row.calculated_daily_man_day == Decimal("3.0")
    assert row.confirmed_daily_man_day == Decimal("3.0")
    assert WorkReportIssueCode.DAILY_MISSING in row.issue_codes
    assert WorkReportIssueCode.CUMULATIVE_BASELINE_REQUIRED in row.issue_codes


def test_manual_row_keeps_legacy_uniform_per_person_input_compatible(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)

    row = service.add_manual_row(
        work_date=date(2026, 8, 1),
        vendor_name="업체A",
        tracking_no="AB260101",
        equipment_name="장비 1",
        business_team="WA",
        actual_headcount=2,
        per_person_man_day=Decimal("1.5"),
        reported_daily_man_day=Decimal("3.0"),
        reported_cumulative_man_day=None,
        resolution_note="기존 수동 입력 호환 확인",
    )

    assert row.night_headcount == 2
    assert row.per_person_man_day == Decimal("1.5")
    assert row.calculated_daily_man_day == Decimal("3.0")


def test_missing_tracking_is_blocking_even_with_equipment(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    record = _review_record(tracking_no=None, equipment_name="장비 1")

    row = service.synchronize_extracted_records([record])[0]

    assert row.cumulative_series_key is None
    assert WorkReportIssueCode.SERIES_KEY_MISSING in row.issue_codes


def test_explicit_baseline_recalculates_tracking_series_in_date_and_row_order(
    tmp_path,
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    first = service.add_manual_row(
        work_date=date(2026, 7, 30),
        vendor_name="업체A",
        tracking_no=" ab 260101 ",
        equipment_name="장비 1",
        business_team="WA",
        actual_headcount=2,
        night_headcount=2,
        reported_daily_man_day=Decimal("3.0"),
        reported_cumulative_man_day=Decimal("13.0"),
        resolution_note="첫날 확인",
    )
    second = service.add_manual_row(
        work_date=date(2026, 7, 30),
        vendor_name="업체B",
        tracking_no="AB260101",
        equipment_name="장비 2",
        business_team="PKG",
        actual_headcount=2,
        night_headcount=0,
        reported_daily_man_day=Decimal("2.0"),
        reported_cumulative_man_day=Decimal("99.0"),
        resolution_note="같은 날 추가 작업",
    )
    third = service.add_manual_row(
        work_date=date(2026, 7, 31),
        vendor_name="업체C",
        tracking_no="AB260101",
        equipment_name="장비 3",
        business_team="TEST",
        actual_headcount=1,
        night_headcount=0,
        reported_daily_man_day=Decimal("1.0"),
        reported_cumulative_man_day=None,
        resolution_note="다음 날 작업",
    )

    baseline = service.save_cumulative_baseline(
        tracking_no="AB260101",
        effective_through_date=date(2026, 7, 29),
        cumulative_man_day=Decimal("10.04"),
        resolution_note="기존 누적 확인",
    )

    recalculated_first = repository.get_work_report_row(first.row_id)
    recalculated_second = repository.get_work_report_row(second.row_id)
    recalculated_third = repository.get_work_report_row(third.row_id)
    assert baseline.cumulative_man_day == Decimal("10.0")
    assert recalculated_first.cumulative_series_key == "AB260101"
    assert recalculated_first.calculated_cumulative_man_day == Decimal("13.0")
    assert recalculated_first.confirmed_cumulative_man_day == Decimal("13.0")
    assert recalculated_second.calculated_cumulative_man_day == Decimal("15.0")
    assert recalculated_second.confirmed_cumulative_man_day is None
    assert recalculated_second.reported_cumulative_man_day == Decimal("99.0")
    assert WorkReportIssueCode.CUMULATIVE_MISMATCH in (
        recalculated_second.issue_codes
    )
    assert recalculated_third.calculated_cumulative_man_day == Decimal("16.0")
    assert recalculated_third.confirmed_cumulative_man_day == Decimal("16.0")


def test_missing_explicit_baseline_stays_blocking_and_cannot_be_confirmed(
    tmp_path,
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    row = service.add_manual_row(
        work_date=date(2026, 7, 30),
        vendor_name="업체A",
        tracking_no="AB260101",
        equipment_name="장비 1",
        business_team="WA",
        actual_headcount=2,
        night_headcount=2,
        reported_daily_man_day=Decimal("3.0"),
        reported_cumulative_man_day=Decimal("13.0"),
        resolution_note="메일 없는 작업",
    )

    assert row.calculated_cumulative_man_day is None
    assert row.confirmed_cumulative_man_day is None
    assert WorkReportIssueCode.CUMULATIVE_BASELINE_REQUIRED in row.issue_codes
    with pytest.raises(ValueError, match="누적 기준"):
        service.confirm_row(
            row.row_id,
            confirmed_daily_man_day=Decimal("3.0"),
            confirmed_cumulative_man_day=Decimal("13.0"),
            resolution_note="누적 직접 입력",
        )


def test_include_delete_and_restore_recalculate_later_active_rows(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    service.save_cumulative_baseline(
        tracking_no="AB260101",
        effective_through_date=date(2026, 7, 29),
        cumulative_man_day=Decimal("10.0"),
        resolution_note="기존 누적 확인",
    )
    first = _add_manual_daily(service, date(2026, 7, 30), Decimal("3.0"))
    second = _add_manual_daily(service, date(2026, 7, 31), Decimal("2.0"))
    assert repository.get_work_report_row(second.row_id).calculated_cumulative_man_day == Decimal("15.0")

    service.set_included(
        first.row_id, False, resolution_note="중복 행 제외"
    )
    assert repository.get_work_report_row(second.row_id).calculated_cumulative_man_day == Decimal("12.0")

    service.set_included(
        first.row_id, True, resolution_note="제외 취소"
    )
    assert repository.get_work_report_row(second.row_id).calculated_cumulative_man_day == Decimal("15.0")

    service.soft_delete_row(first.row_id, resolution_note="행 삭제")
    assert repository.get_work_report_row(second.row_id).calculated_cumulative_man_day == Decimal("12.0")
    assert [
        row.row_id
        for row in service.list_rows(
            date(2026, 7, 30), date(2026, 7, 31)
        ).rows
    ] == [second.row_id]

    service.restore_row(first.row_id, resolution_note="행 복원")
    assert repository.get_work_report_row(second.row_id).calculated_cumulative_man_day == Decimal("15.0")


def test_deleted_unresolved_date_row_is_available_for_recovery(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    unresolved = service.synchronize_extracted_records(
        [
            replace(
                _review_record(),
                report_date=None,
                work_date_confirmed=False,
            )
        ]
    )[0]

    service.soft_delete_row(unresolved.row_id, resolution_note="remove bad import")

    recovery_rows = service.list_rows(
        date(2026, 7, 1),
        date(2026, 7, 31),
        include_deleted=True,
    ).rows
    assert [row.row_id for row in recovery_rows] == [unresolved.row_id]
    assert recovery_rows[0].deleted_at is not None
    assert WorkReportIssueCode.DATE_UNRESOLVED in recovery_rows[0].issue_codes


def test_bulk_soft_delete_validates_every_id_before_mutation(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    first = _add_manual_daily(service, date(2026, 7, 30), Decimal("3.0"))

    with pytest.raises(ValueError, match="찾을 수 없습니다"):
        service.soft_delete_rows(
            [first.row_id, 999_999],
            resolution_note="선택 행 정리",
        )

    assert repository.get_work_report_row(first.row_id).deleted_at is None


def test_bulk_soft_delete_rolls_back_first_row_when_second_mutation_fails(
    tmp_path, monkeypatch
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    first = _add_manual_daily(service, date(2026, 7, 30), Decimal("3.0"))
    second = _add_manual_daily(service, date(2026, 7, 31), Decimal("2.0"))
    original = repository.soft_delete_work_report_row
    calls = 0

    def fail_second(row_id, *, resolution_note):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("두 번째 행 삭제 실패")
        return original(row_id, resolution_note=resolution_note)

    monkeypatch.setattr(
        repository, "soft_delete_work_report_row", fail_second
    )

    with pytest.raises(ValueError, match="두 번째 행 삭제 실패"):
        service.soft_delete_rows(
            [first.row_id, second.row_id],
            resolution_note="선택 행 정리",
        )

    assert repository.get_work_report_row(first.row_id).deleted_at is None
    assert repository.get_work_report_row(second.row_id).deleted_at is None


def test_bulk_restore_rolls_back_first_row_when_second_mutation_fails(
    tmp_path, monkeypatch
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    first = _add_manual_daily(service, date(2026, 7, 30), Decimal("3.0"))
    second = _add_manual_daily(service, date(2026, 7, 31), Decimal("2.0"))
    service.soft_delete_row(first.row_id, resolution_note="복구 준비")
    service.soft_delete_row(second.row_id, resolution_note="복구 준비")
    original = repository.restore_work_report_row
    calls = 0

    def fail_second(row_id, *, resolution_note):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("두 번째 행 복구 실패")
        return original(row_id, resolution_note=resolution_note)

    monkeypatch.setattr(repository, "restore_work_report_row", fail_second)

    with pytest.raises(ValueError, match="두 번째 행 복구 실패"):
        service.restore_rows(
            [first.row_id, second.row_id],
            resolution_note="선택 행 복구",
        )

    assert repository.get_work_report_row(first.row_id).deleted_at is not None
    assert repository.get_work_report_row(second.row_id).deleted_at is not None


def test_bulk_soft_delete_recalculates_each_tracking_series_once(
    tmp_path, monkeypatch
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    first = _add_manual_daily(service, date(2026, 7, 30), Decimal("3.0"))
    second = _add_manual_daily(service, date(2026, 7, 31), Decimal("2.0"))
    original = service._recalculate_tracking_series
    recalculated: list[str] = []

    def track_recalculation(tracking_no, **kwargs):
        recalculated.append(tracking_no)
        return original(tracking_no, **kwargs)

    monkeypatch.setattr(
        service, "_recalculate_tracking_series", track_recalculation
    )

    rows = service.soft_delete_rows(
        [first.row_id, second.row_id],
        resolution_note="선택 행 정리",
    )

    assert [row.row_id for row in rows] == [first.row_id, second.row_id]
    assert recalculated == ["AB260101"]
    assert all(row.deleted_at is not None for row in rows)


def test_moving_baseline_effective_date_clears_consumed_row_and_reseeds_later(
    tmp_path,
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    service.save_cumulative_baseline(
        tracking_no="AB260101",
        effective_through_date=date(2026, 7, 29),
        cumulative_man_day=Decimal("10.0"),
        resolution_note="initial baseline",
    )
    first = _add_manual_daily(service, date(2026, 7, 30), Decimal("3.0"))
    second = _add_manual_daily(service, date(2026, 7, 31), Decimal("2.0"))
    assert repository.get_work_report_row(first.row_id).calculated_cumulative_man_day == Decimal("13.0")

    service.save_cumulative_baseline(
        tracking_no="AB260101",
        effective_through_date=date(2026, 7, 30),
        cumulative_man_day=Decimal("20.0"),
        resolution_note="baseline now includes July 30",
    )

    moved_first = repository.get_work_report_row(first.row_id)
    moved_second = repository.get_work_report_row(second.row_id)
    assert moved_first.calculated_cumulative_man_day is None
    assert moved_first.confirmed_cumulative_man_day is None
    assert moved_second.calculated_cumulative_man_day == Decimal("22.0")


def test_update_confirmed_daily_persists_requested_value_and_recalculates_later(
    tmp_path,
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    service.save_cumulative_baseline(
        tracking_no="AB260101",
        effective_through_date=date(2026, 7, 29),
        cumulative_man_day=Decimal("10.0"),
        resolution_note="initial baseline",
    )
    first = _add_manual_daily(service, date(2026, 7, 30), Decimal("3.0"))
    second = _add_manual_daily(service, date(2026, 7, 31), Decimal("2.0"))

    updated = service.update_row(
        first.row_id,
        {"confirmed_daily_man_day": Decimal("4.0")},
        resolution_note="daily value confirmed from source",
    )

    assert updated.confirmed_daily_man_day == Decimal("4.0")
    assert updated.calculated_cumulative_man_day == Decimal("14.0")
    assert (
        repository.get_work_report_row(second.row_id).calculated_cumulative_man_day
        == Decimal("16.0")
    )


def test_automatic_cumulative_recalculation_preserves_user_resolution_note(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    service.save_cumulative_baseline(
        tracking_no="AB260101",
        effective_through_date=date(2026, 7, 29),
        cumulative_man_day=Decimal("10.0"),
        resolution_note="기준 누적 확인",
    )

    created = _add_manual_daily(service, date(2026, 7, 30), Decimal("3.0"))
    service.save_cumulative_baseline(
        tracking_no="AB260101",
        effective_through_date=date(2026, 7, 29),
        cumulative_man_day=Decimal("11.0"),
        resolution_note="기준 누적 정정",
    )

    assert repository.get_work_report_row(created.row_id).resolution_note == "수동 작업 확인"


def test_work_date_and_tracking_changes_recalculate_old_and_new_series(
    tmp_path,
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    for tracking_no, value in (
        ("TRACK-A", Decimal("10.0")),
        ("TRACK-B", Decimal("20.0")),
    ):
        service.save_cumulative_baseline(
            tracking_no=tracking_no,
            effective_through_date=date(2026, 7, 28),
            cumulative_man_day=value,
            resolution_note="기존 누적 확인",
        )
    first = _add_manual_daily(
        service, date(2026, 7, 30), Decimal("3.0"), tracking_no="TRACK-A"
    )
    second = _add_manual_daily(
        service, date(2026, 7, 31), Decimal("2.0"), tracking_no="TRACK-A"
    )

    moved_date = service.update_row(
        second.row_id,
        {"work_date": date(2026, 7, 29)},
        resolution_note="작업일 정정",
    )

    assert moved_date.calculated_cumulative_man_day == Decimal("12.0")
    assert repository.get_work_report_row(first.row_id).calculated_cumulative_man_day == Decimal("15.0")

    moved_tracking = service.update_row(
        moved_date.row_id,
        {"tracking_no": " track-b "},
        resolution_note="수주번호 정정",
    )

    assert moved_tracking.cumulative_series_key == "TRACK-B"
    assert moved_tracking.calculated_cumulative_man_day == Decimal("22.0")
    assert repository.get_work_report_row(first.row_id).calculated_cumulative_man_day == Decimal("13.0")


def test_mixed_night_row_preserves_headcounts_and_calculates_daily(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)

    row = service.synchronize_extracted_records(
        [
            _review_record(
                actual_headcount=3,
                night_headcount=1,
                daily_man_day=3.5,
            )
        ]
    )[0]

    assert row.actual_headcount == 3
    assert row.night_headcount == 1
    assert row.per_person_man_day is None
    assert row.per_person_display == "혼합"
    assert row.calculated_daily_man_day == Decimal("3.5")
    assert row.confirmed_daily_man_day == Decimal("3.5")
    assert WorkReportIssueCode.INVALID_VALUE not in row.issue_codes
    assert WorkReportIssueCode.NIGHT_HEADCOUNT_INVALID not in row.issue_codes


def test_missing_night_count_keeps_valid_actual_headcount(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)

    row = service.synchronize_extracted_records(
        [_review_record(actual_headcount=3, night_headcount=None)]
    )[0]

    assert row.actual_headcount == 3
    assert row.night_headcount is None
    assert row.per_person_man_day is None
    assert row.per_person_display == "확인 필요"
    assert WorkReportIssueCode.NIGHT_HEADCOUNT_UNRESOLVED in row.issue_codes


def test_invalid_night_count_keeps_valid_actual_headcount(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)

    row = service.synchronize_extracted_records(
        [_review_record(actual_headcount=2, night_headcount=3)]
    )[0]

    assert row.actual_headcount == 2
    assert row.night_headcount is None
    assert WorkReportIssueCode.NIGHT_HEADCOUNT_INVALID in row.issue_codes
    assert WorkReportIssueCode.INVALID_VALUE not in row.issue_codes


def test_update_row_recalculates_uniform_to_mixed_without_overwriting_reported(
    tmp_path,
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    original = service.synchronize_extracted_records([_review_record()])[0]

    updated = service.update_row(
        original.row_id,
        {"night_headcount": 1, "business_team": "PKG"},
        resolution_note="일부 야근 인원 확인",
    )

    assert updated.actual_headcount == 2
    assert updated.night_headcount == 1
    assert updated.per_person_man_day is None
    assert updated.reported_daily_man_day == Decimal("3.0")
    assert updated.calculated_daily_man_day == Decimal("2.5")
    assert updated.confirmed_daily_man_day is None
    assert WorkReportIssueCode.DAILY_MISMATCH in updated.issue_codes
    assert WorkReportIssueCode.WORK_ORDER_UNREGISTERED in updated.issue_codes
    assert updated.vendor_name == "업체A"
    assert updated.business_team == "PKG"


@pytest.mark.parametrize(
    ("night_headcount", "expected_issue"),
    [
        (None, WorkReportIssueCode.NIGHT_HEADCOUNT_UNRESOLVED),
        (3, WorkReportIssueCode.NIGHT_HEADCOUNT_INVALID),
    ],
)
def test_update_row_missing_or_invalid_night_keeps_valid_actual(
    tmp_path,
    night_headcount,
    expected_issue,
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    original = service.synchronize_extracted_records([_review_record()])[0]

    updated = service.update_row(
        original.row_id,
        {"night_headcount": night_headcount},
        resolution_note="야근 인원 재확인",
    )

    assert updated.actual_headcount == 2
    assert updated.night_headcount is None
    assert updated.per_person_man_day is None
    assert updated.reported_daily_man_day == Decimal("3.0")
    assert updated.calculated_daily_man_day is None
    assert updated.confirmed_daily_man_day is None
    assert expected_issue in updated.issue_codes
    assert WorkReportIssueCode.INVALID_VALUE not in updated.issue_codes


def test_update_row_preserves_invalid_night_issue_on_other_trigger_change(
    tmp_path,
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    original = service.synchronize_extracted_records([_review_record()])[0]
    invalid = service.update_row(
        original.row_id,
        {"night_headcount": 3},
        resolution_note="유효하지 않은 야근 인원 입력",
    )

    updated = service.update_row(
        invalid.row_id,
        {"reported_daily_man_day": Decimal("4.0")},
        resolution_note="메일 보고 공수 정정",
    )

    assert updated.actual_headcount == 2
    assert updated.night_headcount is None
    assert WorkReportIssueCode.NIGHT_HEADCOUNT_INVALID in updated.issue_codes
    assert (
        WorkReportIssueCode.NIGHT_HEADCOUNT_UNRESOLVED
        not in updated.issue_codes
    )


def test_update_row_explicit_valid_night_correction_clears_invalid(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    original = service.synchronize_extracted_records([_review_record()])[0]
    invalid = service.update_row(
        original.row_id,
        {"night_headcount": 3},
        resolution_note="유효하지 않은 야근 인원 입력",
    )

    corrected = service.update_row(
        invalid.row_id,
        {
            "night_headcount": 1,
            "reported_daily_man_day": Decimal("2.5"),
        },
        resolution_note="야근 인원 원문 확인",
    )

    assert corrected.actual_headcount == 2
    assert corrected.night_headcount == 1
    assert corrected.per_person_man_day is None
    assert corrected.calculated_daily_man_day == Decimal("2.5")
    assert corrected.confirmed_daily_man_day == Decimal("2.5")
    assert WorkReportIssueCode.NIGHT_HEADCOUNT_INVALID not in corrected.issue_codes
    assert (
        WorkReportIssueCode.NIGHT_HEADCOUNT_UNRESOLVED
        not in corrected.issue_codes
    )


def test_invalid_reported_daily_survives_unrelated_recalculation_until_corrected(
    tmp_path,
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    invalid = service.synchronize_extracted_records(
        [replace(_review_record(), daily_man_day=-1.0)]
    )[0]
    assert WorkReportIssueCode.INVALID_VALUE in invalid.issue_codes

    unrelated = service.update_row(
        invalid.row_id,
        {"actual_headcount": 2},
        resolution_note="실제 인원 재확인",
    )
    assert WorkReportIssueCode.INVALID_VALUE in unrelated.issue_codes
    assert WorkReportIssueCode.REPORTED_DAILY_INVALID in unrelated.issue_codes
    assert WorkReportIssueCode.DAILY_MISSING not in unrelated.issue_codes

    corrected = service.update_row(
        unrelated.row_id,
        {"reported_daily_man_day": Decimal("3.0")},
        resolution_note="메일 투입 공수 정정",
    )
    assert WorkReportIssueCode.INVALID_VALUE not in corrected.issue_codes


def test_invalid_reported_cumulative_survives_unrelated_recalculation_until_corrected(
    tmp_path,
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    invalid = service.synchronize_extracted_records(
        [replace(_review_record(), cumulative_man_day=-1.0)]
    )[0]
    assert WorkReportIssueCode.INVALID_VALUE in invalid.issue_codes

    unrelated = service.update_row(
        invalid.row_id,
        {"actual_headcount": 2},
        resolution_note="실제 인원 재확인",
    )
    assert WorkReportIssueCode.INVALID_VALUE in unrelated.issue_codes
    assert (
        WorkReportIssueCode.REPORTED_CUMULATIVE_INVALID
        in unrelated.issue_codes
    )
    assert WorkReportIssueCode.CUMULATIVE_MISSING not in unrelated.issue_codes

    corrected = service.update_row(
        unrelated.row_id,
        {"reported_cumulative_man_day": Decimal("12.0")},
        resolution_note="메일 누적 공수 정정",
    )
    assert WorkReportIssueCode.INVALID_VALUE not in corrected.issue_codes


def _work_report_service(repository: SQLiteRepository) -> WorkReportService:
    return WorkReportService(
        repository,
        ManDayCalculationService(),
        WorkOrderMappingService(repository),
    )


def _add_manual_daily(
    service: WorkReportService,
    work_date: date,
    daily_man_day: Decimal,
    *,
    tracking_no: str = "AB260101",
):
    return service.add_manual_row(
        work_date=work_date,
        vendor_name="업체A",
        tracking_no=tracking_no,
        equipment_name="장비 1",
        business_team="WA",
        actual_headcount=int(daily_man_day),
        night_headcount=0,
        reported_daily_man_day=daily_man_day,
        reported_cumulative_man_day=None,
        resolution_note="수동 작업 확인",
    )


def _review_record(
    *,
    record_id: int = 1,
    mail_entry_id: str = "ENTRY-1",
    tracking_no: str | None = "AB260101",
    equipment_name: str | None = "장비 1",
    actual_headcount: float | None = 2.0,
    night_headcount: float | None = 2.0,
    daily_man_day: float | None = 3.0,
) -> ReviewRecord:
    return ReviewRecord(
        record_id=record_id,
        mail_entry_id=mail_entry_id,
        report_date=date(2026, 7, 29),
        sender_name="작성자",
        sender_email="writer@example.com",
        equipment_name=equipment_name,
        tracking_no=tracking_no,
        vendor_name="업체A",
        actual_headcount=actual_headcount,
        night_headcount=night_headcount,
        per_person_man_day=1.5,
        daily_man_day=daily_man_day,
        cumulative_man_day=12.0,
        business_team="WA",
        confidence=0.95,
        review_status=ReviewStatus.NORMAL,
        note=None,
        date_issue_codes=(),
        work_date_confirmed=True,
    )
