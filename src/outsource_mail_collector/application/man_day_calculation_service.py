"""Decimal-only calculation rules for daily and cumulative man-days."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import TypeAlias

from outsource_mail_collector.domain.work_report import (
    ManDayValues,
    WorkReportIssueCode,
)


MAN_DAY_QUANTUM = Decimal("0.1")
DecimalInput: TypeAlias = Decimal | int | float | str


def quantize_man_day(value: Decimal) -> Decimal:
    """Round a finite man-day value to one decimal using ``ROUND_HALF_UP``."""

    if not value.is_finite():
        raise ValueError("공수는 유한한 숫자여야 합니다.")
    return value.quantize(MAN_DAY_QUANTUM, rounding=ROUND_HALF_UP)


class ManDayCalculationService:
    """Calculate review candidates without guessing user-confirmed values."""

    def calculate_daily(
        self,
        *,
        actual_headcount: DecimalInput | None,
        night_headcount: DecimalInput | None,
        reported_daily: DecimalInput | None,
    ) -> ManDayValues:
        headcount = _parse_headcount(
            actual_headcount, field_name="실제 작업인원"
        )
        night = _parse_headcount(
            night_headcount, field_name="야근 인원"
        )
        if night > headcount:
            raise ValueError("야근 인원은 실제 작업인원보다 클 수 없습니다.")
        reported = _parse_man_day(
            reported_daily, field_name="메일 투입 공수", required=False
        )
        calculated = quantize_man_day(
            Decimal(headcount) + Decimal(night) * Decimal("0.5")
        )

        if reported is None:
            return ManDayValues(
                reported=None,
                calculated=calculated,
                confirmed_candidate=calculated,
                issues=(WorkReportIssueCode.DAILY_MISSING,),
            )
        if reported != calculated:
            return ManDayValues(
                reported=reported,
                calculated=calculated,
                confirmed_candidate=None,
                issues=(WorkReportIssueCode.DAILY_MISMATCH,),
            )
        return ManDayValues(
            reported=reported,
            calculated=calculated,
            confirmed_candidate=reported,
        )

    def calculate_cumulative(
        self,
        *,
        prior_confirmed_cumulative: DecimalInput | None,
        confirmed_daily: DecimalInput | None,
        reported_cumulative: DecimalInput | None,
    ) -> ManDayValues:
        prior = _parse_man_day(
            prior_confirmed_cumulative,
            field_name="직전 확정 누적 공수",
            required=False,
        )
        daily = _parse_man_day(
            confirmed_daily, field_name="확정 투입 공수", required=True
        )
        reported = _parse_man_day(
            reported_cumulative, field_name="메일 누적 공수", required=False
        )

        if prior is None:
            issue = (
                WorkReportIssueCode.CUMULATIVE_BASELINE_CONFIRMATION
                if reported is not None
                else WorkReportIssueCode.CUMULATIVE_BASELINE_REQUIRED
            )
            return ManDayValues(
                reported=reported,
                calculated=None,
                confirmed_candidate=None,
                issues=(issue,),
            )

        calculated = quantize_man_day(prior + daily)
        if reported is None:
            return ManDayValues(
                reported=None,
                calculated=calculated,
                confirmed_candidate=calculated,
                issues=(WorkReportIssueCode.CUMULATIVE_MISSING,),
            )
        if reported != calculated:
            return ManDayValues(
                reported=reported,
                calculated=calculated,
                confirmed_candidate=None,
                issues=(WorkReportIssueCode.CUMULATIVE_MISMATCH,),
            )
        return ManDayValues(
            reported=reported,
            calculated=calculated,
            confirmed_candidate=reported,
        )


def _parse_headcount(
    value: DecimalInput | None, *, field_name: str
) -> int:
    parsed = _parse_decimal(value, field_name=field_name, required=True)
    assert parsed is not None
    if parsed < 0 or parsed != parsed.to_integral_value():
        raise ValueError(f"{field_name}은(는) 0 이상의 정수여야 합니다.")
    return int(parsed)


def _parse_man_day(
    value: DecimalInput | None, *, field_name: str, required: bool
) -> Decimal | None:
    parsed = _parse_decimal(value, field_name=field_name, required=required)
    if parsed is None:
        return None
    if parsed < 0:
        raise ValueError(f"{field_name}는 0 이상이어야 합니다.")
    return quantize_man_day(parsed)


def _parse_decimal(
    value: DecimalInput | None, *, field_name: str, required: bool
) -> Decimal | None:
    if value is None:
        if required:
            raise ValueError(f"{field_name}이(가) 필요합니다.")
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name}은(는) 숫자여야 합니다.") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field_name}은(는) 유한한 숫자여야 합니다.")
    return parsed
