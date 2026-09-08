"""Transforms are pure, so their answers can be written down by hand.

Two properties get their own tests because the rest of the project depends on
them: year-over-year forms are invariant to index rebasing, which is what lets
vintages published on different index bases be compared at all; and expanding
window standardisation never uses a later observation to scale an earlier one.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from economic_regime_forecasting.features import transforms
from economic_regime_forecasting.features.transforms import (
    TransformError,
    assert_strictly_monthly,
    difference,
    expanding_window_standardisation,
    year_over_year_log_change,
    year_over_year_percent_change,
)


def test_year_over_year_log_change_of_a_doubling_is_the_log_of_two() -> None:
    index = pd.date_range("2000-01-01", periods=13, freq="MS")
    doubling = pd.Series([100.0] * 12 + [200.0], index=index)
    assert year_over_year_log_change(doubling).iloc[-1] == pytest.approx(math.log(2.0))


def test_year_over_year_percent_change_reads_in_percentage_points() -> None:
    index = pd.date_range("2000-01-01", periods=13, freq="MS")
    series = pd.Series([100.0] * 12 + [103.0], index=index)
    assert year_over_year_percent_change(series).iloc[-1] == pytest.approx(3.0)


def test_the_first_twelve_months_have_no_year_over_year_value(
    rising_series: pd.Series,
) -> None:
    changes = year_over_year_log_change(rising_series)
    assert bool(changes.iloc[:12].isna().all())
    assert bool(changes.iloc[12:].notna().all())


def test_year_over_year_forms_are_invariant_to_index_rebasing(
    rising_series: pd.Series,
) -> None:
    """A 1970 vintage puts January 1919 industrial production at 24.6 and a 2026
    vintage puts it at 4.87. In levels those vintages are incomparable. In
    year-over-year growth they agree exactly, which is why the model reads growth
    rates and not levels."""
    rebased = rising_series * 5.113
    pd.testing.assert_series_equal(
        year_over_year_log_change(rising_series).dropna(),
        year_over_year_log_change(rebased).dropna(),
    )
    pd.testing.assert_series_equal(
        year_over_year_percent_change(rising_series).dropna(),
        year_over_year_percent_change(rebased).dropna(),
    )


def test_non_positive_values_become_missing_rather_than_raising() -> None:
    index = pd.date_range("2000-01-01", periods=14, freq="MS")
    with_a_zero = pd.Series([100.0] * 13 + [0.0], index=index)
    assert bool(
        year_over_year_log_change(with_a_zero).iloc[-1]
        != year_over_year_log_change(with_a_zero).iloc[-1]
    )


def test_expanding_standardisation_uses_only_the_past() -> None:
    """Appending future observations must not change any earlier standardised
    value. A full sample z-score fails this test, which is the point of it."""
    index = pd.date_range("2000-01-01", periods=120, freq="MS")
    generator = np.random.default_rng(20260908)
    series = pd.Series(generator.normal(size=120), index=index).to_frame("x")

    on_the_short_sample = expanding_window_standardisation(series.iloc[:80], minimum_periods=12)
    on_the_full_sample = expanding_window_standardisation(series, minimum_periods=12)
    pd.testing.assert_frame_equal(on_the_short_sample, on_the_full_sample.iloc[:80])


def test_standardisation_matches_a_hand_computed_value() -> None:
    index = pd.date_range("2000-01-01", periods=4, freq="MS")
    series = pd.DataFrame({"x": [1.0, 2.0, 3.0, 10.0]}, index=index)
    standardised = expanding_window_standardisation(series, minimum_periods=3)
    expected_third = (3.0 - 2.0) / float(np.std([1.0, 2.0, 3.0], ddof=1))
    assert standardised["x"].iloc[2] == pytest.approx(expected_third)
    assert bool(standardised["x"].iloc[:2].isna().all())


def test_a_constant_column_comes_back_missing_rather_than_infinite() -> None:
    """Dividing by a zero standard deviation would put infinities into an emission
    likelihood, where they poison every state probability at once."""
    index = pd.date_range("2000-01-01", periods=10, freq="MS")
    flat = pd.DataFrame({"x": [4.0] * 10}, index=index)
    assert bool(expanding_window_standardisation(flat, minimum_periods=3)["x"].isna().all())


def test_difference_aligns_on_shared_dates() -> None:
    long_index = pd.date_range("2000-01-01", periods=10, freq="MS")
    short_index = pd.date_range("2000-04-01", periods=4, freq="MS")
    result = difference(
        pd.Series(range(10), index=long_index, dtype="float64", name="a"),
        pd.Series([1.0] * 4, index=short_index, name="b"),
    )
    assert result.size == 4
    assert result.iloc[0] == pytest.approx(2.0)


def test_differencing_series_that_never_overlap_is_reported() -> None:
    with pytest.raises(TransformError, match="share no observation dates"):
        difference(
            pd.Series([1.0], index=pd.date_range("2000-01-01", periods=1, freq="MS"), name="a"),
            pd.Series([1.0], index=pd.date_range("2020-01-01", periods=1, freq="MS"), name="b"),
        )


def test_a_gap_in_the_monthly_sequence_is_refused() -> None:
    """A hidden Markov model reads its rows as consecutive months. A missing month
    is read as no time having passed, corrupting every transition probability."""
    gappy = pd.DataFrame(
        {"x": [1.0, 2.0, 3.0]},
        index=pd.DatetimeIndex(["2000-01-01", "2000-02-01", "2000-05-01"]),
    )
    with pytest.raises(TransformError, match="missing"):
        assert_strictly_monthly(gappy)


def test_a_complete_monthly_sequence_passes(rising_series: pd.Series) -> None:
    assert_strictly_monthly(rising_series.to_frame("x"))


def test_an_unknown_transform_is_reported_by_name() -> None:
    with pytest.raises(TransformError, match="no implementation"):
        transforms.apply_transform(pd.Series([1.0]), "not_a_transform")  # type: ignore[arg-type]
