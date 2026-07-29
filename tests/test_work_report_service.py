from datetime import date
from decimal import Decimal

from outsource_mail_collector.application.man_day_calculation_service import (
    ManDayCalculationService,
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
    service = WorkReportService(repository, ManDayCalculationService())
    record = _review_record()

    first = service.synchronize_extracted_records([record])
    second = service.synchronize_extracted_records([record])

    assert len(first) == 1
    assert second[0].row_id == first[0].row_id
    row = first[0]
    assert row.source_type is RowSource.MAIL
    assert row.mail_entry_id == "ENTRY-1"
    assert row.per_person_man_day == Decimal("1.5")
    assert row.reported_daily_man_day == Decimal("3.0")
    assert row.reported_cumulative_man_day == Decimal("12.0")
    assert row.cumulative_series_key == "업체a|T:AB260101"


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
    service = WorkReportService(repository, ManDayCalculationService())
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
    service = WorkReportService(repository, ManDayCalculationService())

    row = service.add_manual_row(
        work_date=date(2026, 8, 1),
        vendor_name="업체A",
        tracking_no="AB260101",
        equipment_name="장비 1",
        business_team="WA",
        actual_headcount=2,
        per_person_man_day=Decimal("1.5"),
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


def test_missing_tracking_and_equipment_creates_blocking_series_issue(tmp_path):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = WorkReportService(repository, ManDayCalculationService())
    record = _review_record(tracking_no=None, equipment_name=None)

    row = service.synchronize_extracted_records([record])[0]

    assert row.cumulative_series_key is None
    assert WorkReportIssueCode.SERIES_KEY_MISSING in row.issue_codes


def test_confirming_baseline_recalculates_later_unconfirmed_series_rows(
    tmp_path,
):
    repository = SQLiteRepository(tmp_path / "collector.db")
    service = WorkReportService(repository, ManDayCalculationService())
    first = service.add_manual_row(
        work_date=date(2026, 7, 29),
        vendor_name="업체A",
        tracking_no="AB260101",
        equipment_name="장비 1",
        business_team="WA",
        actual_headcount=2,
        per_person_man_day=Decimal("1.5"),
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
        per_person_man_day=Decimal("1.5"),
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


def _review_record(
    *,
    record_id: int = 1,
    mail_entry_id: str = "ENTRY-1",
    tracking_no: str | None = "AB260101",
    equipment_name: str | None = "장비 1",
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
        actual_headcount=2.0,
        per_person_man_day=1.5,
        daily_man_day=3.0,
        cumulative_man_day=12.0,
        business_team="WA",
        confidence=0.95,
        review_status=ReviewStatus.NORMAL,
        note=None,
        date_issue_codes=(),
        work_date_confirmed=True,
    )
