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
    assert row.cumulative_series_key == "업체a|T:AB260101"


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


def test_series_key_uses_equipment_only_when_tracking_is_missing() -> None:
    assert build_cumulative_series_key(" 업체 A ", " ab 260101 ", "장비 1") == (
        "업체 a|T:AB260101"
    )
    assert build_cumulative_series_key("업체 A", None, " 장비   1 ") == (
        "업체 a|E:장비 1"
    )
    assert build_cumulative_series_key("업체 A", None, None) is None


def test_duplicate_candidates_are_kept_and_marked_without_summing(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    old = _review_record(record_id=1, mail_entry_id="ENTRY-OLD")
    new = _review_record(record_id=2, mail_entry_id="ENTRY-NEW")

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
    assert WorkReportIssueCode.CUMULATIVE_BASELINE_CONFIRMATION in row.issue_codes


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


def test_missing_tracking_and_equipment_creates_blocking_series_issue(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    record = _review_record(tracking_no=None, equipment_name=None)

    row = service.synchronize_extracted_records([record])[0]

    assert row.cumulative_series_key is None
    assert WorkReportIssueCode.SERIES_KEY_MISSING in row.issue_codes


def test_confirming_baseline_recalculates_later_unconfirmed_series_rows(
    tmp_path,
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = _work_report_service(repository)
    first = service.add_manual_row(
        work_date=date(2026, 7, 29),
        vendor_name="업체A",
        tracking_no="AB260101",
        equipment_name="장비 1",
        business_team="WA",
        actual_headcount=2,
        night_headcount=2,
        reported_daily_man_day=Decimal("3.0"),
        reported_cumulative_man_day=Decimal("10.0"),
        resolution_note="첫날 확인",
    )
    second = service.add_manual_row(
        work_date=date(2026, 7, 30),
        vendor_name="업체A",
        tracking_no="AB260101",
        equipment_name="장비 1",
        business_team="WA",
        actual_headcount=2,
        night_headcount=2,
        reported_daily_man_day=Decimal("3.0"),
        reported_cumulative_man_day=None,
        resolution_note="둘째 날 확인",
    )
    assert WorkReportIssueCode.CUMULATIVE_BASELINE_REQUIRED in (
        second.issue_codes
    )

    service.confirm_row(
        first.row_id,
        confirmed_daily_man_day=Decimal("3.0"),
        confirmed_cumulative_man_day=Decimal("10.0"),
        resolution_note="최초 누적 기준 확인",
    )
    recalculated = repository.get_work_report_row(second.row_id)

    assert recalculated.calculated_cumulative_man_day == Decimal("13.0")
    assert recalculated.confirmed_cumulative_man_day == Decimal("13.0")
    assert WorkReportIssueCode.CUMULATIVE_MISSING in recalculated.issue_codes
    assert WorkReportIssueCode.CUMULATIVE_BASELINE_REQUIRED not in (
        recalculated.issue_codes
    )


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
