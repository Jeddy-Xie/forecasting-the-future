"""The forecast schedule, and the one place this project imputes a number.

Interpolation gets its own file's worth of attention because it is a modelling
choice wearing plumbing's clothes. October 2025 has no consumer price index and no
unemployment rate: the government shut down and the surveys were never run. One
month in the middle of an otherwise complete series is bridged; anything longer
raises, because a quarter-long hole deserves a decision rather than a straight
line.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from economic_regime_forecasting.backtest.schedule import (
    ScheduleError,
    build_schedule,
    first_forecast_date_after_burn_in,
)
from economic_regime_forecasting.features.transforms import (
    MAXIMUM_BRIDGEABLE_GAP_IN_MONTHS,
    TransformError,
    bridge_isolated_missing_months,
)


def _monthly(values: list[float], start: str = "2000-01-01") -> pd.Series:
    index = pd.date_range(start, periods=len(values), freq="MS")
    return pd.Series(values, index=index, name="test_series", dtype="float64")


# ------------------------------------------------------------------ bridging


def test_a_complete_series_is_returned_untouched() -> None:
    series = _monthly([1.0, 2.0, 3.0])
    repaired, bridged = bridge_isolated_missing_months(series)
    pd.testing.assert_series_equal(repaired, series, check_freq=False)
    assert bridged == ()


def test_a_single_missing_month_is_bridged_and_reported() -> None:
    """The real case: one month absent from the middle of the series."""
    series = _monthly([10.0, np.nan, 12.0, 13.0])
    repaired, bridged = bridge_isolated_missing_months(series)
    assert repaired.iloc[1] == pytest.approx(11.0)
    assert [f"{month:%Y-%m}" for month in bridged] == ["2000-02"]


def test_a_month_absent_from_the_index_entirely_is_bridged_too() -> None:
    """The service can omit a row rather than write a missing value."""
    series = pd.Series(
        [10.0, 12.0],
        index=pd.DatetimeIndex(["2000-01-01", "2000-03-01"]),
        name="test_series",
    )
    repaired, bridged = bridge_isolated_missing_months(series)
    assert len(repaired) == 3
    assert repaired.iloc[1] == pytest.approx(11.0)
    assert len(bridged) == 1


def test_two_consecutive_missing_months_are_refused() -> None:
    """The limit is deliberate: a longer hole is a different problem."""
    series = _monthly([10.0, np.nan, np.nan, 13.0])
    with pytest.raises(TransformError, match="2 consecutive months"):
        bridge_isolated_missing_months(series)


def test_the_error_names_the_month_and_says_what_to_do() -> None:
    series = _monthly([10.0, np.nan, np.nan, 13.0])
    with pytest.raises(TransformError, match="rather than drawing a straight line"):
        bridge_isolated_missing_months(series)


def test_the_gap_limit_is_one_month() -> None:
    assert MAXIMUM_BRIDGEABLE_GAP_IN_MONTHS == 1


def test_missing_months_at_the_ends_are_left_missing_not_extrapolated() -> None:
    """Drawing a line past the last real observation would be extrapolation in
    disguise, which is a much bigger claim than filling a hole."""
    series = _monthly([np.nan, 10.0, 11.0, np.nan])
    repaired, bridged = bridge_isolated_missing_months(series)
    assert bool(pd.isna(repaired.iloc[0]))
    assert bool(pd.isna(repaired.iloc[-1]))
    assert bridged == ()


def test_an_empty_series_bridges_to_nothing() -> None:
    empty = pd.Series([], index=pd.DatetimeIndex([]), dtype="float64", name="x")
    repaired, bridged = bridge_isolated_missing_months(empty)
    assert repaired.empty
    assert bridged == ()


def test_bridging_leaves_the_surrounding_values_alone() -> None:
    series = _monthly([10.0, np.nan, 12.0, 13.0, 14.0])
    repaired, _ = bridge_isolated_missing_months(series)
    assert list(repaired.iloc[[0, 2, 3, 4]]) == [10.0, 12.0, 13.0, 14.0]


# ------------------------------------------------------------------ schedule


def test_a_schedule_visits_every_month_and_refits_on_the_cadence() -> None:
    schedule = build_schedule(date(2000, 1, 1), date(2002, 12, 1), refit_every_n_months=12)
    assert len(schedule) == 36
    assert len(schedule.refit_dates) == 3
    assert schedule.refit_dates[0] == pd.Timestamp("2000-01-01")
    assert schedule.refit_dates[1] == pd.Timestamp("2001-01-01")


def test_the_first_forecast_date_is_always_a_refit_date() -> None:
    """There is no earlier model to reuse."""
    schedule = build_schedule(date(2000, 1, 1), date(2001, 6, 1), refit_every_n_months=12)
    assert schedule.refit_dates[0] == schedule.forecast_dates[0]


def test_a_forecast_uses_the_most_recent_refit_before_it() -> None:
    schedule = build_schedule(date(2000, 1, 1), date(2002, 12, 1), refit_every_n_months=12)
    assert schedule.most_recent_refit_on_or_before(pd.Timestamp("2000-07-01")) == pd.Timestamp(
        "2000-01-01"
    )
    assert schedule.most_recent_refit_on_or_before(pd.Timestamp("2001-01-01")) == pd.Timestamp(
        "2001-01-01"
    )


def test_asking_for_a_refit_before_the_schedule_starts_is_reported() -> None:
    schedule = build_schedule(date(2000, 1, 1), date(2001, 1, 1), refit_every_n_months=12)
    with pytest.raises(ScheduleError, match="no refit on or before"):
        schedule.most_recent_refit_on_or_before(pd.Timestamp("1995-01-01"))


def test_refitting_every_month_is_allowed_and_refits_every_month() -> None:
    schedule = build_schedule(date(2000, 1, 1), date(2000, 12, 1), refit_every_n_months=1)
    assert len(schedule.refit_dates) == len(schedule.forecast_dates) == 12


def test_a_refit_cadence_of_zero_is_refused() -> None:
    with pytest.raises(ScheduleError, match="at least 1"):
        build_schedule(date(2000, 1, 1), date(2001, 1, 1), refit_every_n_months=0)


def test_a_schedule_that_spans_no_months_is_reported() -> None:
    with pytest.raises(ScheduleError, match="not enough history"):
        build_schedule(date(2001, 1, 1), date(2000, 1, 1), refit_every_n_months=12)


def test_the_first_forecast_comes_the_month_after_the_burn_in_ends() -> None:
    """A forecast in month t uses observations through t minus one, because month
    t itself has not been published."""
    dates = pd.date_range("1950-01-01", periods=300, freq="MS")
    assert first_forecast_date_after_burn_in(dates, 240) == date(1970, 1, 1)


def test_too_little_history_for_the_burn_in_is_reported_with_the_numbers() -> None:
    dates = pd.date_range("1950-01-01", periods=100, freq="MS")
    with pytest.raises(ScheduleError, match="only 100 observations"):
        first_forecast_date_after_burn_in(dates, 240)


def test_a_schedule_describes_itself_for_the_run_log() -> None:
    schedule = build_schedule(date(2000, 1, 1), date(2002, 12, 1), refit_every_n_months=12)
    assert "36 forecast dates" in schedule.describe()
    assert "3 refits" in schedule.describe()
