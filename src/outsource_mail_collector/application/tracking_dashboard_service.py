"""Build Tracking-No lifetime and date-level aggregate projections."""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from outsource_mail_collector.application.models import (
    FinalizationBlocker,
    TrackingDailyAggregate,
    TrackingDashboardSummary,
    WorkReportRow,
    work_report_row_from_stored,
)
from outsource_mail_collector.domain.work_report import (
    WorkReportIssueCode,
    man_day_basis,
)
from outsource_mail_collector.infrastructure.db.repository import (
    CumulativeBaseline,
    SQLiteRepository,
    StoredWorkReportRow,
    WorkOrderMapping,
    normalize_tracking_no,
)


_BLOCKING_ISSUES = {
    WorkReportIssueCode.DATE_UNRESOLVED,
    WorkReportIssueCode.CUMULATIVE_MISMATCH,
    WorkReportIssueCode.CUMULATIVE_BASELINE_REQUIRED,
    WorkReportIssueCode.DUPLICATE_UNRESOLVED,
    WorkReportIssueCode.SERIES_KEY_MISSING,
    WorkReportIssueCode.INVALID_VALUE,
    WorkReportIssueCode.ACTUAL_HEADCOUNT_INVALID,
    WorkReportIssueCode.REPORTED_DAILY_INVALID,
    WorkReportIssueCode.REPORTED_CUMULATIVE_INVALID,
    WorkReportIssueCode.WORK_ORDER_UNREGISTERED,
    WorkReportIssueCode.NIGHT_HEADCOUNT_UNRESOLVED,
    WorkReportIssueCode.NIGHT_HEADCOUNT_INVALID,
}

_BLOCKING_MESSAGES = {
    WorkReportIssueCode.DATE_UNRESOLVED: "작업일을 결정할 수 없습니다. 작업일을 확정해 주세요.",
    WorkReportIssueCode.CUMULATIVE_MISMATCH: "메일 누적과 계산 누적이 일치하지 않습니다.",
    WorkReportIssueCode.CUMULATIVE_BASELINE_REQUIRED: "이전 확정 누적 기준을 입력해 주세요.",
    WorkReportIssueCode.DUPLICATE_UNRESOLVED: "중복 보고가 해결되지 않았습니다.",
    WorkReportIssueCode.SERIES_KEY_MISSING: "Tracking No.를 확인해 주세요.",
    WorkReportIssueCode.INVALID_VALUE: "유효하지 않은 값을 수정해 주세요.",
    WorkReportIssueCode.ACTUAL_HEADCOUNT_INVALID: "실제 작업인원을 수정해 주세요.",
    WorkReportIssueCode.REPORTED_DAILY_INVALID: "메일 당일 공수를 확인해 주세요.",
    WorkReportIssueCode.REPORTED_CUMULATIVE_INVALID: "메일 누적 공수를 확인해 주세요.",
    WorkReportIssueCode.WORK_ORDER_UNREGISTERED: "설정에서 해당 Tracking No.의 수주를 등록해 주세요.",
    WorkReportIssueCode.NIGHT_HEADCOUNT_UNRESOLVED: "야근 인원을 입력해 주세요.",
    WorkReportIssueCode.NIGHT_HEADCOUNT_INVALID: "야근 인원을 실제 작업인원 이하로 수정해 주세요.",
}


class TrackingDashboardService:
    """Project active source rows into daily and lifetime Tracking-No views."""

    def __init__(self, repository: SQLiteRepository) -> None:
        self._repository = repository

    def daily_aggregates(
        self, date_from: date, date_to: date
    ) -> tuple[TrackingDailyAggregate, ...]:
        if date_from > date_to:
            raise ValueError("시작일은 종료일보다 늦을 수 없습니다.")
        return tuple(
            aggregate
            for aggregate in self._all_daily_aggregates()
            if (
                aggregate.work_date is None
                or date_from <= aggregate.work_date <= date_to
            )
        )

    def summaries(self) -> tuple[TrackingDashboardSummary, ...]:
        grouped: dict[str, list[TrackingDailyAggregate]] = defaultdict(list)
        for aggregate in self._all_daily_aggregates():
            if aggregate.normalized_tracking_no:
                grouped[aggregate.normalized_tracking_no].append(aggregate)
        summaries = [
            self._summary_for_tracking(tracking_no, rows)
            for tracking_no, rows in grouped.items()
        ]
        return tuple(
            sorted(
                summaries,
                key=lambda item: item.normalized_tracking_no,
            )
        )

    def drill_down(self, tracking_no: str) -> tuple[WorkReportRow, ...]:
        normalized = normalize_tracking_no(tracking_no)
        rows = [
            row
            for row in self._active_rows()
            if normalize_tracking_no(row.tracking_no or "") == normalized
        ]
        rows.sort(key=lambda row: (row.work_date or date.max, row.row_id))
        return tuple(work_report_row_from_stored(row) for row in rows)

    def _all_daily_aggregates(self) -> list[TrackingDailyAggregate]:
        rows = self._active_rows()
        groups: dict[
            tuple[date | None, str], list[StoredWorkReportRow]
        ] = defaultdict(list)
        lifetime_rows: dict[str, list[StoredWorkReportRow]] = defaultdict(list)
        for row in rows:
            normalized = normalize_tracking_no(row.tracking_no or "")
            identity = normalized or f"__MISSING__{row.row_id}"
            groups[(row.work_date, identity)].append(row)
            lifetime_rows[identity].append(row)
        mappings = {
            mapping.normalized_tracking_no: mapping
            for mapping in self._repository.list_work_order_mappings(
                active_only=True
            )
        }
        baselines = {
            baseline.normalized_tracking_no: baseline
            for baseline in self._repository.list_cumulative_baselines()
        }
        vendor_orders = {
            vendor.canonical_name.strip().casefold(): vendor.sort_order
            for vendor in self._repository.list_vendors()
        }
        running: dict[str, Decimal | None] = {}
        result: list[TrackingDailyAggregate] = []
        for (work_date, identity), contributors in sorted(
            groups.items(),
            key=lambda item: (item[0][0] or date.max, item[0][1]),
        ):
            contributors.sort(key=lambda row: row.row_id)
            normalized = "" if identity.startswith("__MISSING__") else identity
            daily = _sum_decimals(
                row.confirmed_daily_man_day for row in contributors
            )
            calculated = self._calculated_cumulative(
                normalized,
                work_date,
                daily,
                contributors[-1],
                baselines.get(normalized),
                running,
            )
            result.append(
                _aggregate_group(
                    contributors,
                    normalized,
                    mappings.get(normalized),
                    vendor_orders,
                    daily,
                    calculated,
                    lifetime_rows[identity],
                )
            )
        return result

    def _active_rows(self) -> list[StoredWorkReportRow]:
        return [
            row
            for row in self._repository.list_all_work_report_rows()
            if row.included and row.deleted_at is None
        ]

    @staticmethod
    def _calculated_cumulative(
        normalized: str,
        work_date: date | None,
        daily: Decimal | None,
        final_row: StoredWorkReportRow,
        baseline: CumulativeBaseline | None,
        running: dict[str, Decimal | None],
    ) -> Decimal | None:
        if not normalized:
            return final_row.calculated_cumulative_man_day
        if work_date is None:
            return final_row.calculated_cumulative_man_day
        if (
            baseline is not None
            and work_date <= baseline.effective_through_date
        ):
            return final_row.calculated_cumulative_man_day
        if normalized not in running:
            running[normalized] = (
                baseline.cumulative_man_day
                if baseline is not None
                else final_row.calculated_cumulative_man_day
            )
            if baseline is None:
                return running[normalized]
        previous = running[normalized]
        if previous is None or daily is None:
            running[normalized] = None
            return None
        calculated = (previous + daily).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )
        running[normalized] = calculated
        return calculated

    def _summary_for_tracking(
        self,
        normalized: str,
        aggregates: list[TrackingDailyAggregate],
    ) -> TrackingDashboardSummary:
        latest = next(
            (
                aggregate
                for aggregate in reversed(aggregates)
                if aggregate.work_date is not None
            ),
            aggregates[-1],
        )
        baseline = self._repository.get_cumulative_baseline(normalized)
        blockers = _deduplicate_blockers(
            blocker
            for aggregate in aggregates
            for blocker in aggregate.blockers
        )
        return TrackingDashboardSummary(
            normalized_tracking_no=normalized,
            tracking_no=latest.tracking_no or normalized,
            vendor_name=latest.vendor_name,
            equipment_name=latest.equipment_name,
            business_team=latest.business_team,
            latest_work_date=latest.work_date,
            latest_actual_headcount=latest.actual_headcount,
            latest_night_headcount=latest.night_headcount,
            latest_man_day_basis=latest.man_day_basis,
            latest_confirmed_daily_man_day=latest.confirmed_daily_man_day,
            latest_reported_cumulative_man_day=(
                latest.reported_cumulative_man_day
            ),
            latest_calculated_cumulative_man_day=(
                latest.calculated_cumulative_man_day
            ),
            latest_confirmed_cumulative_man_day=(
                latest.confirmed_cumulative_man_day
            ),
            initial_cumulative_man_day=(
                baseline.cumulative_man_day if baseline is not None else None
            ),
            source_row_ids=tuple(
                source_id
                for aggregate in aggregates
                for source_id in aggregate.source_row_ids
            ),
            blockers=blockers,
        )


def source_row_blockers(
    row: StoredWorkReportRow,
) -> tuple[FinalizationBlocker, ...]:
    blockers: list[FinalizationBlocker] = []
    for issue in row.issue_codes:
        if issue in _BLOCKING_ISSUES:
            blockers.append(
                FinalizationBlocker(
                    row.row_id,
                    issue.value,
                    _BLOCKING_MESSAGES[issue],
                )
            )
    if row.issue_codes and not row.warning_confirmed and not blockers:
        blockers.append(
            FinalizationBlocker(
                row.row_id,
                "WARNING_UNCONFIRMED",
                "경고 내용을 개별 확인해 주세요.",
            )
        )
    if row.work_date is None or not row.work_date_confirmed:
        blockers.append(
            FinalizationBlocker(
                row.row_id,
                "WORK_DATE_UNCONFIRMED",
                "작업일을 확인해 주세요.",
            )
        )
    invalid_headcounts = (
        row.actual_headcount is not None
        and row.night_headcount is not None
        and (
            row.actual_headcount < 0
            or row.night_headcount < 0
            or row.night_headcount > row.actual_headcount
        )
    )
    if invalid_headcounts and not any(
        blocker.code == WorkReportIssueCode.NIGHT_HEADCOUNT_INVALID.value
        for blocker in blockers
    ):
        blockers.append(
            FinalizationBlocker(
                row.row_id,
                WorkReportIssueCode.NIGHT_HEADCOUNT_INVALID.value,
                "야근 인원은 실제 작업인원 이하의 0 이상 값이어야 합니다.",
            )
        )
    missing_fields = _missing_required_fields(row)
    if missing_fields:
        blockers.append(
            FinalizationBlocker(
                row.row_id,
                "REQUIRED_FIELD_MISSING",
                "최종 표의 필수 항목을 입력해 주세요: "
                + ", ".join(missing_fields),
            )
        )
    missing_confirmed: list[str] = []
    if row.confirmed_daily_man_day is None:
        missing_confirmed.append("확정 투입")
    if row.confirmed_cumulative_man_day is None:
        missing_confirmed.append("확정 누적")
    if missing_confirmed:
        blockers.append(
            FinalizationBlocker(
                row.row_id,
                "CONFIRMED_MAN_DAY_MISSING",
                "확인 창에서 다음 공수를 입력해 주세요: "
                + ", ".join(missing_confirmed),
            )
        )
    return tuple(blockers)


def _aggregate_group(
    rows: list[StoredWorkReportRow],
    normalized: str,
    mapping: WorkOrderMapping | None,
    vendor_orders: dict[str, int],
    confirmed_daily: Decimal | None,
    calculated_cumulative: Decimal | None,
    identity_rows: list[StoredWorkReportRow],
) -> TrackingDailyAggregate:
    final_row = rows[-1]
    vendor, equipment, team, identity_blocker = _resolve_identity(
        identity_rows, mapping
    )
    actual = _sum_integers(row.actual_headcount for row in rows)
    night = _sum_integers(row.night_headcount for row in rows)
    basis = man_day_basis(actual, night)
    blockers = [
        blocker for row in rows for blocker in source_row_blockers(row)
    ]
    if not normalized:
        blockers.append(
            FinalizationBlocker(
                final_row.row_id,
                "TRACKING_NO_MISSING",
                "Tracking No.를 입력해 주세요.",
            )
        )
    if identity_blocker is not None:
        blockers.append(identity_blocker)
    if (
        final_row.reported_cumulative_man_day is not None
        and calculated_cumulative is not None
        and final_row.reported_cumulative_man_day != calculated_cumulative
    ):
        blockers.append(
            FinalizationBlocker(
                final_row.row_id,
                WorkReportIssueCode.CUMULATIVE_MISMATCH.value,
                _BLOCKING_MESSAGES[WorkReportIssueCode.CUMULATIVE_MISMATCH],
            )
        )
    if actual is None or night is None:
        blockers.append(
            FinalizationBlocker(
                final_row.row_id,
                "REQUIRED_FIELD_MISSING",
                "집계에 필요한 작업인원 또는 야근 인원이 누락되었습니다.",
            )
        )
    if confirmed_daily is None:
        blockers.append(
            FinalizationBlocker(
                final_row.row_id,
                "CONFIRMED_MAN_DAY_MISSING",
                "집계에 필요한 확정 투입 공수가 누락되었습니다.",
            )
        )
    tracking_display = (
        mapping.tracking_no
        if mapping is not None
        else _first_text(row.tracking_no for row in rows)
    )
    return TrackingDailyAggregate(
        row_id=final_row.row_id,
        source_row_ids=tuple(row.row_id for row in rows),
        work_date=final_row.work_date,
        normalized_tracking_no=normalized,
        tracking_no=tracking_display,
        vendor_name=vendor,
        vendor_sort_order=vendor_orders.get(
            (vendor or "").strip().casefold(), 2_147_483_647
        ),
        equipment_name=equipment,
        business_team=team,
        actual_headcount=actual,
        night_headcount=night,
        per_person_man_day=(
            Decimal(basis) if basis in {"1.0", "1.5"} else None
        ),
        man_day_basis=basis,
        confirmed_daily_man_day=confirmed_daily,
        reported_cumulative_man_day=final_row.reported_cumulative_man_day,
        calculated_cumulative_man_day=calculated_cumulative,
        confirmed_cumulative_man_day=final_row.confirmed_cumulative_man_day,
        blockers=_deduplicate_blockers(blockers),
    )


def _resolve_identity(
    rows: list[StoredWorkReportRow],
    mapping: WorkOrderMapping | None,
) -> tuple[str | None, str | None, str | None, FinalizationBlocker | None]:
    if mapping is not None:
        return (
            mapping.vendor_name,
            mapping.equipment_name,
            mapping.business_team,
            None,
        )
    vendor, vendor_conflict = _single_identity(row.vendor_name for row in rows)
    equipment, equipment_conflict = _single_identity(
        row.equipment_name for row in rows
    )
    team, team_conflict = _single_identity(
        row.business_team for row in rows
    )
    if vendor_conflict or equipment_conflict or team_conflict:
        return (
            None if vendor_conflict else vendor,
            None if equipment_conflict else equipment,
            None if team_conflict else team,
            FinalizationBlocker(
                rows[-1].row_id,
                "IDENTITY_CONFLICT",
                "동일 Tracking No.의 업체, 장비 또는 사업팀 정보가 충돌합니다.",
            ),
        )
    return vendor, equipment, team, None


def _single_identity(values) -> tuple[str | None, bool]:
    originals: dict[str, str] = {}
    for value in values:
        if not value or not value.strip():
            continue
        normalized = unicodedata.normalize("NFKC", value)
        key = " ".join(normalized.split()).casefold()
        originals.setdefault(key, value.strip())
    if len(originals) > 1:
        return None, True
    return (next(iter(originals.values())) if originals else None), False


def _first_text(values) -> str | None:
    return next(
        (value.strip() for value in values if value and value.strip()),
        None,
    )


def _sum_integers(values) -> int | None:
    collected = list(values)
    if not collected or any(value is None for value in collected):
        return None
    return sum(int(value) for value in collected)


def _sum_decimals(values) -> Decimal | None:
    collected = list(values)
    if not collected or any(value is None for value in collected):
        return None
    return sum((value for value in collected if value is not None), Decimal())


def _missing_required_fields(row: StoredWorkReportRow) -> list[str]:
    missing: list[str] = []
    for label, value in (
        ("거래처명", row.vendor_name),
        ("사업팀", row.business_team),
        ("실제 작업인원", row.actual_headcount),
        ("야근 인원", row.night_headcount),
    ):
        if value is None or value == "":
            missing.append(label)
    mixed = (
        row.actual_headcount is not None
        and row.night_headcount is not None
        and 0 < row.night_headcount < row.actual_headcount
    )
    if row.per_person_man_day is None and not mixed:
        missing.append("인당 공수")
    if not normalize_tracking_no(row.tracking_no or ""):
        missing.append("Tracking No. 또는 장비명")
    return missing


def _deduplicate_blockers(blockers) -> tuple[FinalizationBlocker, ...]:
    result: list[FinalizationBlocker] = []
    seen: set[tuple[int, str]] = set()
    for blocker in blockers:
        key = (blocker.row_id, blocker.code)
        if key not in seen:
            seen.add(key)
            result.append(blocker)
    return tuple(result)
