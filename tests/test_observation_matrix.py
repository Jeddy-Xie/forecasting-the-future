"""Assembling the three-column matrix the model reads.

Column order is fixed at growth, inflation, rates. State labelling later reads
emission means by position, so a permuted column order would silently rename
every regime in the report. That gets its own test.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import numpy as np
import pandas as pd
import pytest

from economic_regime_forecasting.configuration.registry import EconomicSeriesRegistry
from economic_regime_forecasting.data.cache import SeriesCache, SeriesSnapshot
from economic_regime_forecasting.data.panel import (
    PointInTimePanel,
    assemble_point_in_time_panel,
    latest_common_observation_date,
)
from economic_regime_forecasting.features.observation_matrix import (
    COLUMN_NAMES,
    ObservationMatrixError,
    build_observation_matrix,
)


def _fill_cache(
    cache: SeriesCache,
    registry: EconomicSeriesRegistry,
    snapshot_factory: Callable[..., SeriesSnapshot],
    index: pd.DatetimeIndex,
    as_of: date,
) -> None:
    generator = np.random.default_rng(20260908)
    for entry in registry.series:
        values = 100.0 * np.exp(np.cumsum(generator.normal(0.002, 0.01, size=len(index))))
        series = pd.Series(values, index=index, name=entry.series_id)
        cache.write(snapshot_factory(series, series_id=entry.series_id))
        # A real archival vintage stops before the date it is dated, so the test
        # double must too. Writing the full series here would trip the look-ahead
        # guard, which is the guard working rather than the fixture being clever.
        as_published = series[series.index < pd.Timestamp(as_of) - pd.DateOffset(months=1)]
        cache.write(snapshot_factory(as_published, series_id=entry.series_id, vintage_date=as_of))


def test_columns_are_growth_then_inflation_then_rates(
    cache: SeriesCache,
    three_dimension_registry: EconomicSeriesRegistry,
    monthly_index: pd.DatetimeIndex,
    snapshot_factory: Callable[..., SeriesSnapshot],
) -> None:
    as_of = date(2005, 1, 1)
    _fill_cache(cache, three_dimension_registry, snapshot_factory, monthly_index, as_of)
    panel = assemble_point_in_time_panel(three_dimension_registry, as_of, cache)
    matrix = build_observation_matrix(panel, three_dimension_registry)

    assert tuple(matrix.standardised.columns) == COLUMN_NAMES
    assert COLUMN_NAMES == ("growth", "inflation", "rates")
    assert matrix.values.shape[1] == 3


def test_the_matrix_never_extends_past_its_as_of_date(
    cache: SeriesCache,
    three_dimension_registry: EconomicSeriesRegistry,
    monthly_index: pd.DatetimeIndex,
    snapshot_factory: Callable[..., SeriesSnapshot],
) -> None:
    as_of = date(2005, 1, 1)
    _fill_cache(cache, three_dimension_registry, snapshot_factory, monthly_index, as_of)
    matrix = build_observation_matrix(
        assemble_point_in_time_panel(three_dimension_registry, as_of, cache),
        three_dimension_registry,
    )
    assert matrix.dates[-1].date() < as_of


def test_every_standardised_value_is_finite(
    cache: SeriesCache,
    three_dimension_registry: EconomicSeriesRegistry,
    monthly_index: pd.DatetimeIndex,
    snapshot_factory: Callable[..., SeriesSnapshot],
) -> None:
    as_of = date(2005, 1, 1)
    _fill_cache(cache, three_dimension_registry, snapshot_factory, monthly_index, as_of)
    matrix = build_observation_matrix(
        assemble_point_in_time_panel(three_dimension_registry, as_of, cache),
        three_dimension_registry,
    )
    assert np.isfinite(matrix.values).all()
    assert len(matrix) > 0


def test_a_panel_too_short_to_standardise_is_reported_with_the_numbers(
    cache: SeriesCache,
    three_dimension_registry: EconomicSeriesRegistry,
    snapshot_factory: Callable[..., SeriesSnapshot],
) -> None:
    short_index = pd.date_range("1960-01-01", periods=20, freq="MS", name="observation_date")
    as_of = date(1962, 6, 1)
    _fill_cache(cache, three_dimension_registry, snapshot_factory, short_index, as_of)
    with pytest.raises(ObservationMatrixError, match="fewer than the"):
        build_observation_matrix(
            assemble_point_in_time_panel(three_dimension_registry, as_of, cache),
            three_dimension_registry,
        )


def test_asking_a_panel_for_a_series_it_does_not_hold_lists_what_it_does() -> None:
    panel = PointInTimePanel(as_of=date(2000, 1, 1), series={})
    with pytest.raises(Exception, match="not in this panel"):
        _ = panel["absent_series"]


def test_the_common_end_date_is_the_earliest_series_end() -> None:
    """Taking the latest would silently extend a panel with missing values."""
    short = pd.Series(
        [1.0, 2.0], index=pd.date_range("2000-01-01", periods=2, freq="MS"), name="short"
    )
    long = pd.Series(
        [1.0] * 10, index=pd.date_range("2000-01-01", periods=10, freq="MS"), name="long"
    )
    assert latest_common_observation_date({"short": short, "long": long}) == date(2000, 2, 1)
