"""Turning history into the zeros and ones a conditional base rate is built from.

Every rule is checked against a series whose answers can be read off by eye. The
two conventions that would otherwise be invisible get their own tests: the
horizon window excludes the forecast month itself, and an outcome that runs past
the end of the data is unknown rather than zero.
"""

from __future__ import annotations

import pandas as pd
import pytest

from economic_regime_forecasting.configuration.registry import (
    BinaryIndicator,
    Composition,
    IndicatorResolution,
    ResolutionRule,
    Transform,
)
from economic_regime_forecasting.data.indicator_outcomes import (
    ResolutionError,
    required_series_names,
    resolve,
    resolve_all,
)


def _indicator(
    rule: ResolutionRule,
    threshold: float | None = None,
    transform: Transform = Transform.LEVEL,
) -> BinaryIndicator:
    return BinaryIndicator(
        name="test_indicator",
        question="a test question",
        resolution=IndicatorResolution(
            series="test_series", rule=rule, transform=transform, threshold=threshold
        ),
        composition=(
            Composition.ANY_TIME_WITHIN_HORIZON
            if rule.reads_whole_path
            else Composition.POINT_IN_TIME
        ),
        horizons_in_years=(1,),
    )


def _series(values: list[float]) -> pd.Series:
    index = pd.date_range("2000-01-01", periods=len(values), freq="MS")
    return pd.Series(values, index=index, name="test_series", dtype="float64")


def test_level_above_threshold_at_horizon_reads_one_month_only() -> None:
    """Values of 0, 9, 0, 0: at a two month horizon only the first date sees the
    nine, and only because the nine sits exactly two months ahead of it."""
    outcomes = resolve(
        _indicator(ResolutionRule.LEVEL_ABOVE_THRESHOLD_AT_HORIZON, threshold=5.0),
        _series([0.0, 9.0, 0.0, 0.0]),
        horizon_in_months=2,
    ).outcomes
    assert list(outcomes.dropna()) == [0.0, 0.0]
    outcomes_at_one = resolve(
        _indicator(ResolutionRule.LEVEL_ABOVE_THRESHOLD_AT_HORIZON, threshold=5.0),
        _series([0.0, 9.0, 0.0, 0.0]),
        horizon_in_months=1,
    ).outcomes
    assert list(outcomes_at_one.dropna()) == [1.0, 0.0, 0.0]


def test_a_within_horizon_rule_sees_a_spike_the_at_horizon_rule_misses() -> None:
    """This difference is the whole reason both composition paths exist."""
    series = _series([0.0, 9.0, 0.0, 0.0])
    within = resolve(
        _indicator(ResolutionRule.LEVEL_ABOVE_THRESHOLD_WITHIN_HORIZON, threshold=5.0),
        series,
        horizon_in_months=2,
    ).outcomes
    at_horizon = resolve(
        _indicator(ResolutionRule.LEVEL_ABOVE_THRESHOLD_AT_HORIZON, threshold=5.0),
        series,
        horizon_in_months=2,
    ).outcomes
    assert within.iloc[0] == 1.0
    assert at_horizon.iloc[0] == 0.0


def test_the_horizon_window_excludes_the_forecast_month_itself() -> None:
    """ "Will a recession happen in the next five years" does not count a recession
    already under way this month."""
    already_happening = _series([1.0, 0.0, 0.0, 0.0])
    outcomes = resolve(
        _indicator(ResolutionRule.FLAG_POSITIVE_WITHIN_HORIZON),
        already_happening,
        horizon_in_months=2,
    ).outcomes
    assert outcomes.iloc[0] == 0.0


def test_level_below_threshold_within_horizon_finds_a_dip() -> None:
    outcomes = resolve(
        _indicator(ResolutionRule.LEVEL_BELOW_THRESHOLD_WITHIN_HORIZON, threshold=1.0),
        _series([5.0, 5.0, 0.5, 5.0]),
        horizon_in_months=2,
    ).outcomes
    assert list(outcomes.dropna()) == [1.0, 1.0]


def test_rise_from_forecast_date_is_measured_against_today_not_a_fixed_level() -> None:
    """The same absolute peak counts for one starting point and not another."""
    outcomes = resolve(
        _indicator(ResolutionRule.RISE_FROM_FORECAST_DATE_WITHIN_HORIZON, threshold=2.0),
        _series([3.0, 4.0, 5.5, 5.0]),
        horizon_in_months=2,
    ).outcomes
    assert outcomes.iloc[0] == 1.0
    assert outcomes.iloc[1] == 0.0


def test_higher_than_forecast_date_at_horizon_compares_two_months() -> None:
    outcomes = resolve(
        _indicator(ResolutionRule.HIGHER_THAN_FORECAST_DATE_AT_HORIZON),
        _series([10.0, 10.0, 11.0, 9.0]),
        horizon_in_months=2,
    ).outcomes
    assert list(outcomes.dropna()) == [1.0, 0.0]


def test_an_outcome_running_past_the_data_is_unknown_and_not_zero() -> None:
    """Filling unknowns with zero is how a base rate quietly becomes wrong and a
    model gets credit for calling non-events that were merely unobserved."""
    resolved = resolve(
        _indicator(ResolutionRule.LEVEL_ABOVE_THRESHOLD_AT_HORIZON, threshold=5.0),
        _series([0.0, 0.0, 0.0, 0.0]),
        horizon_in_months=2,
    )
    assert bool(resolved.outcomes.iloc[-2:].isna().all())
    assert resolved.resolved_count == 2


def test_a_gap_inside_the_window_makes_the_outcome_unknown() -> None:
    with_a_gap = pd.Series(
        [0.0, 0.0, 0.0],
        index=pd.DatetimeIndex(["2000-01-01", "2000-02-01", "2000-04-01"]),
        name="test_series",
    )
    outcomes = resolve(
        _indicator(ResolutionRule.LEVEL_ABOVE_THRESHOLD_WITHIN_HORIZON, threshold=5.0),
        with_a_gap,
        horizon_in_months=2,
    ).outcomes
    assert bool(pd.isna(outcomes.iloc[0]))


def test_a_transform_can_be_applied_before_the_rule() -> None:
    """Inflation thresholds are quoted on the year-over-year change, not the index."""
    index_values = [100.0] * 12 + [104.0]
    outcomes = resolve(
        _indicator(
            ResolutionRule.LEVEL_ABOVE_THRESHOLD_AT_HORIZON,
            threshold=3.0,
            transform=Transform.YEAR_OVER_YEAR_PERCENT_CHANGE,
        ),
        _series(index_values),
        horizon_in_months=12,
    ).outcomes
    assert outcomes.iloc[0] == 1.0


def test_base_rate_and_counts_are_reported_together() -> None:
    resolved = resolve(
        _indicator(ResolutionRule.LEVEL_ABOVE_THRESHOLD_AT_HORIZON, threshold=0.5),
        _series([1.0, 0.0, 1.0, 1.0]),
        horizon_in_months=1,
    )
    assert resolved.resolved_count == 3
    assert resolved.positive_count == 2
    assert resolved.base_rate == pytest.approx(2.0 / 3.0)


def test_an_indicator_whose_series_was_not_loaded_is_reported_by_name() -> None:
    with pytest.raises(ResolutionError, match="test_series"):
        resolve_all([_indicator(ResolutionRule.FLAG_POSITIVE_WITHIN_HORIZON)], {}, (12,))


def test_required_series_names_are_unique_and_ordered() -> None:
    indicators = [
        _indicator(ResolutionRule.FLAG_POSITIVE_WITHIN_HORIZON),
        _indicator(ResolutionRule.LEVEL_ABOVE_THRESHOLD_AT_HORIZON, threshold=1.0),
    ]
    assert required_series_names(indicators) == ["test_series"]


def test_an_empty_series_is_reported_rather_than_silently_resolving_nothing() -> None:
    with pytest.raises(ResolutionError, match="empty series"):
        resolve(
            _indicator(ResolutionRule.FLAG_POSITIVE_WITHIN_HORIZON),
            pd.Series([], index=pd.DatetimeIndex([]), dtype="float64", name="test_series"),
            horizon_in_months=12,
        )
