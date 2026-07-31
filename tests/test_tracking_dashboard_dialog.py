from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from PySide6.QtCore import QDate
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QDialog

import outsource_mail_collector.ui.tracking_dashboard_dialog as dialog_module
from outsource_mail_collector.application.models import (
    FinalizationBlocker,
    TrackingDashboardSummary,
    WorkReportRow,
)
from outsource_mail_collector.domain.models import ReviewStatus
from outsource_mail_collector.domain.work_report import (
    RowSource,
    WorkReportIssueCode,
)
from outsource_mail_collector.ui.tracking_dashboard_dialog import (
    BaselineDialog,
    TrackingDashboardDialog,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_dashboard_renders_summary_drill_down_and_blocking_guidance():
    _app()
    dashboard_service = _DashboardService(
        summaries=(
            _summary(
                blockers=(
                    FinalizationBlocker(
                        7,
                        "CUMULATIVE_MISMATCH",
                        "메일 누적과 계산 누적을 확인해 주세요.",
                    ),
                )
            ),
        ),
        details=(_row(7), _row(8, work_date=date(2026, 7, 30))),
    )
    dialog = TrackingDashboardDialog(
        dashboard_service,
        _WorkReportService(),
        lambda: None,
    )

    assert dialog.summary_table.rowCount() == 1
    summary_headers = [
        dialog.summary_table.horizontalHeaderItem(column).text()
        for column in range(dialog.summary_table.columnCount())
    ]
    assert summary_headers == [
        "Tracking No.",
        "최근 작업일",
        "거래처명",
        "장비명",
        "사업팀",
        "최근 실제 인원",
        "최근 야근 인원",
        "인당 공수",
        "최근 확정 투입",
        "초기 누적",
        "메일 누적",
        "계산 누적",
        "확정 누적",
        "검증 상태",
    ]
    assert dialog.summary_table.item(0, 0).text() == "AB260101"
    assert dialog.summary_table.item(0, 13).text() == "확인 필요"
    assert (
        dialog.summary_table.item(0, 0).background().color()
        == QColor("#ffebee")
    )

    dialog.summary_table.selectRow(0)

    assert dashboard_service.drill_down_calls == ["AB260101"]
    assert dialog.detail_table.rowCount() == 2
    detail_headers = [
        dialog.detail_table.horizontalHeaderItem(column).text()
        for column in range(dialog.detail_table.columnCount())
    ]
    assert "야근 인원" in detail_headers
    assert "메일 누적" in detail_headers
    assert "확정 누적" in detail_headers
    assert "포함" in detail_headers
    assert "문제 및 조치" in detail_headers
    assert "메일 누적과 계산 누적" in dialog.guidance_label.text()


def test_baseline_dialog_defaults_and_prefills_saved_values():
    _app()
    first = BaselineDialog(
        "AB260101",
        earliest_work_date=date(2026, 7, 29),
        baseline=None,
    )
    assert first.effective_date_edit.date() == QDate(2026, 7, 28)

    saved = SimpleNamespace(
        effective_through_date=date(2026, 7, 27),
        cumulative_man_day=Decimal("20.5"),
    )
    existing = BaselineDialog(
        "AB260101",
        earliest_work_date=date(2026, 7, 29),
        baseline=saved,
    )

    assert existing.effective_date_edit.date() == QDate(2026, 7, 27)
    assert existing.cumulative_edit.text() == "20.5"


def test_baseline_save_calls_service_and_refreshes_dashboard_and_main(
    monkeypatch,
):
    _app()
    work_service = _WorkReportService()
    refreshes: list[str] = []
    dialog = TrackingDashboardDialog(
        _DashboardService(
            summaries=(_summary(),),
            details=(_row(7),),
        ),
        work_service,
        lambda: refreshes.append("main"),
    )

    class FakeBaselineDialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, tracking_no, earliest_work_date, baseline, parent=None):
            assert tracking_no == "AB260101"
            assert earliest_work_date == date(2026, 7, 29)
            assert baseline is None

        def exec(self):
            return QDialog.DialogCode.Accepted

        def values(self):
            return {
                "effective_through_date": date(2026, 7, 28),
                "cumulative_man_day": Decimal("20.0"),
                "resolution_note": "초기 자료 확인",
            }

    monkeypatch.setattr(dialog_module, "BaselineDialog", FakeBaselineDialog)

    dialog.summary_table.selectRow(0)
    dialog._edit_baseline()

    assert work_service.saved == [
        {
            "tracking_no": "AB260101",
            "effective_through_date": date(2026, 7, 28),
            "cumulative_man_day": Decimal("20.0"),
            "resolution_note": "초기 자료 확인",
        }
    ]
    assert refreshes == ["main"]
    assert dialog.summary_table.rowCount() == 1


def test_baseline_values_require_reason_and_one_decimal():
    _app()
    dialog = BaselineDialog(
        "AB260101",
        earliest_work_date=date(2026, 7, 29),
        baseline=None,
    )
    dialog.cumulative_edit.setText("20.25")
    dialog.reason_edit.setText("")

    try:
        dialog.values()
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("invalid baseline should be rejected")

    assert "소수점 첫째 자리" in message
    dialog.cumulative_edit.setText("20.0")
    try:
        dialog.values()
    except ValueError as exc:
        assert "사유" in str(exc)
    else:
        raise AssertionError("missing reason should be rejected")


class _DashboardService:
    def __init__(self, *, summaries, details):
        self._summaries = summaries
        self._details = details
        self.drill_down_calls: list[str] = []

    def summaries(self):
        return self._summaries

    def drill_down(self, tracking_no):
        self.drill_down_calls.append(tracking_no)
        return self._details


class _WorkReportService:
    def __init__(self):
        self.saved: list[dict] = []

    def get_cumulative_baseline(self, tracking_no):
        return None

    def save_cumulative_baseline(self, **values):
        self.saved.append(values)
        return SimpleNamespace(**values)


def _summary(
    *,
    blockers: tuple[FinalizationBlocker, ...] = (),
) -> TrackingDashboardSummary:
    return TrackingDashboardSummary(
        normalized_tracking_no="AB260101",
        tracking_no="AB260101",
        vendor_name="업체A",
        equipment_name="장비 1",
        business_team="WA",
        latest_work_date=date(2026, 7, 30),
        latest_actual_headcount=3,
        latest_night_headcount=1,
        latest_man_day_basis="혼합",
        latest_confirmed_daily_man_day=Decimal("3.5"),
        latest_reported_cumulative_man_day=Decimal("23.5"),
        latest_calculated_cumulative_man_day=Decimal("23.5"),
        latest_confirmed_cumulative_man_day=Decimal("23.5"),
        initial_cumulative_man_day=Decimal("20.0"),
        source_row_ids=(7, 8),
        blockers=blockers,
    )


def _row(
    row_id: int,
    *,
    work_date: date = date(2026, 7, 29),
) -> WorkReportRow:
    return WorkReportRow(
        row_id=row_id,
        source_type=RowSource.MAIL,
        extracted_record_id=row_id,
        mail_entry_id=f"ENTRY-{row_id}",
        work_date=work_date,
        work_date_confirmed=True,
        vendor_name="업체A",
        tracking_no="AB260101",
        equipment_name="장비 1",
        business_team="WA",
        actual_headcount=3,
        night_headcount=1,
        per_person_man_day=None,
        reported_daily_man_day=Decimal("3.5"),
        calculated_daily_man_day=Decimal("3.5"),
        confirmed_daily_man_day=Decimal("3.5"),
        reported_cumulative_man_day=Decimal("23.5"),
        calculated_cumulative_man_day=Decimal("23.5"),
        confirmed_cumulative_man_day=Decimal("23.5"),
        cumulative_series_key="AB260101",
        issue_codes=(WorkReportIssueCode.CUMULATIVE_MISMATCH,),
        review_status=ReviewStatus.NORMAL,
        included=True,
        warning_confirmed=False,
        resolution_note=None,
    )
