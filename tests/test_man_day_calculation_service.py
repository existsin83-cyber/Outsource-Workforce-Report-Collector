from decimal import Decimal

import pytest

from outsource_mail_collector.application.man_day_calculation_service import (
    ManDayCalculationService,
    quantize_man_day,
)
from outsource_mail_collector.domain.work_report import WorkReportIssueCode


@pytest.fixture
def service() -> ManDayCalculationService:
    return ManDayCalculationService()


def test_missing_reported_daily_uses_calculation_and_warns(
    service: ManDayCalculationService,
) -> None:
    result = service.calculate_daily(
        actual_headcount=2,
        per_person_man_day=Decimal("1.5"),
        reported_daily=None,
    )

    assert result.calculated == Decimal("3.0")
    assert result.confirmed_candidate == Decimal("3.0")
    assert WorkReportIssueCode.DAILY_MISSING in result.issues


def test_reported_daily_mismatch_requires_confirmation(
    service: ManDayCalculationService,
) -> None:
    result = service.calculate_daily(
        actual_headcount=2,
        per_person_man_day=Decimal("1.5"),
        reported_daily=Decimal("4.0"),
    )

    assert result.reported == Decimal("4.0")
    assert result.calculated == Decimal("3.0")
    assert result.confirmed_candidate is None
    assert WorkReportIssueCode.DAILY_MISMATCH in result.issues


def test_matching_reported_daily_is_confirmed_candidate(
    service: ManDayCalculationService,
) -> None:
    result = service.calculate_daily(
        actual_headcount=3,
        per_person_man_day=Decimal("0.5"),
        reported_daily=Decimal("1.5"),
    )

    assert result.confirmed_candidate == Decimal("1.5")
    assert result.issues == ()


@pytest.mark.parametrize("headcount", [-1, 1.5, Decimal("2.2")])
def test_invalid_headcount_is_rejected(
    service: ManDayCalculationService, headcount: object
) -> None:
    with pytest.raises(ValueError):
        service.calculate_daily(
            actual_headcount=headcount,
            per_person_man_day=Decimal("1.0"),
            reported_daily=None,
        )


@pytest.mark.parametrize(
    ("headcount", "per_person"),
    [(None, Decimal("1.0")), (2, None)],
)
def test_missing_daily_inputs_are_rejected(
    service: ManDayCalculationService,
    headcount: object,
    per_person: object,
) -> None:
    with pytest.raises(ValueError):
        service.calculate_daily(
            actual_headcount=headcount,
            per_person_man_day=per_person,
            reported_daily=None,
        )


@pytest.mark.parametrize(
    "value",
    [Decimal("-0.1"), Decimal("NaN"), Decimal("Infinity")],
)
def test_invalid_man_day_values_are_rejected(
    service: ManDayCalculationService, value: Decimal
) -> None:
    with pytest.raises(ValueError):
        service.calculate_daily(
            actual_headcount=1,
            per_person_man_day=value,
            reported_daily=None,
        )


def test_man_day_quantization_uses_round_half_up() -> None:
    assert quantize_man_day(Decimal("1.25")) == Decimal("1.3")
    assert quantize_man_day(Decimal("1.24")) == Decimal("1.2")


def test_cumulative_uses_prior_confirmed_plus_current_daily(
    service: ManDayCalculationService,
) -> None:
    result = service.calculate_cumulative(
        prior_confirmed_cumulative=Decimal("10.5"),
        confirmed_daily=Decimal("1.5"),
        reported_cumulative=Decimal("12.0"),
    )

    assert result.calculated == Decimal("12.0")
    assert result.confirmed_candidate == Decimal("12.0")
    assert result.issues == ()


def test_missing_reported_cumulative_uses_calculation_and_warns(
    service: ManDayCalculationService,
) -> None:
    result = service.calculate_cumulative(
        prior_confirmed_cumulative=Decimal("10.5"),
        confirmed_daily=Decimal("1.5"),
        reported_cumulative=None,
    )

    assert result.calculated == Decimal("12.0")
    assert result.confirmed_candidate == Decimal("12.0")
    assert WorkReportIssueCode.CUMULATIVE_MISSING in result.issues


def test_cumulative_mismatch_requires_confirmation(
    service: ManDayCalculationService,
) -> None:
    result = service.calculate_cumulative(
        prior_confirmed_cumulative=Decimal("10.5"),
        confirmed_daily=Decimal("1.5"),
        reported_cumulative=Decimal("13.0"),
    )

    assert result.calculated == Decimal("12.0")
    assert result.confirmed_candidate is None
    assert WorkReportIssueCode.CUMULATIVE_MISMATCH in result.issues


def test_first_cumulative_report_becomes_unconfirmed_baseline_candidate(
    service: ManDayCalculationService,
) -> None:
    result = service.calculate_cumulative(
        prior_confirmed_cumulative=None,
        confirmed_daily=Decimal("1.5"),
        reported_cumulative=Decimal("8.0"),
    )

    assert result.calculated is None
    assert result.confirmed_candidate is None
    assert WorkReportIssueCode.CUMULATIVE_BASELINE_CONFIRMATION in result.issues


def test_first_cumulative_without_prior_or_report_is_blocked(
    service: ManDayCalculationService,
) -> None:
    result = service.calculate_cumulative(
        prior_confirmed_cumulative=None,
        confirmed_daily=Decimal("1.5"),
        reported_cumulative=None,
    )

    assert result.calculated is None
    assert result.confirmed_candidate is None
    assert WorkReportIssueCode.CUMULATIVE_BASELINE_REQUIRED in result.issues
