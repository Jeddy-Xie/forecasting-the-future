"""Shared fixtures.

Every fixture here is offline and deterministic. Tests that reach the Federal
Reserve are marked ``network`` and are the only ones that do.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from economic_regime_forecasting.configuration.registry import (
    EconomicSeries,
    EconomicSeriesRegistry,
    ModelDimension,
    Transform,
)
from economic_regime_forecasting.data.cache import SeriesCache, SeriesRequest, SeriesSnapshot


@pytest.fixture
def cache(tmp_path: Path) -> SeriesCache:
    """A cache rooted in a temporary directory, never the project's own."""
    return SeriesCache(tmp_path / "raw", tmp_path / "vintage")


@pytest.fixture
def monthly_index() -> pd.DatetimeIndex:
    """Fifty years of month starts, long enough for twelve-month transforms."""
    return pd.date_range("1960-01-01", periods=600, freq="MS", name="observation_date")


@pytest.fixture
def rising_series(monthly_index: pd.DatetimeIndex) -> pd.Series:
    """A series that grows at a constant five percent a year, exactly."""
    years = np.arange(len(monthly_index)) / 12.0
    return pd.Series(100.0 * 1.05**years, index=monthly_index, name="TESTSERIES")


@pytest.fixture
def snapshot_factory() -> Callable[..., SeriesSnapshot]:
    """Build a snapshot without touching the network."""

    def build(
        observations: pd.Series,
        series_id: str = "TESTSERIES",
        vintage_date: date | None = None,
    ) -> SeriesSnapshot:
        request = SeriesRequest(
            source="federal_reserve_economic_data",
            series_id=series_id,
            transform="as_published",
            vintage_date=vintage_date,
        )
        return SeriesSnapshot(
            request=request,
            observations=observations.rename(series_id),
            source_url=f"https://example.invalid/{series_id}",
            units="index",
            retrieved_at=datetime(2026, 9, 8, tzinfo=UTC),
            payload_digest="0" * 64,
        )

    return build


@pytest.fixture
def three_dimension_registry() -> EconomicSeriesRegistry:
    """A registry with one series per model dimension and nothing else."""

    def entry(
        name: str,
        series_id: str,
        dimension: ModelDimension,
        transform: Transform,
        is_revised: bool,
    ) -> EconomicSeries:
        return EconomicSeries(
            name=name,
            series_id=series_id,
            description=f"test series {name}",
            role=dimension.value,
            model_dimension=dimension,
            frequency="monthly",
            units="test units",
            transform=transform,
            publication_lag_days=45,
            observation_start=date(1960, 1, 1),
            is_revised=is_revised,
        )

    return EconomicSeriesRegistry(
        series=(
            entry(
                "test_output",
                "TESTOUT",
                ModelDimension.GROWTH,
                Transform.YEAR_OVER_YEAR_LOG_CHANGE,
                True,
            ),
            entry(
                "test_prices",
                "TESTCPI",
                ModelDimension.INFLATION,
                Transform.YEAR_OVER_YEAR_LOG_CHANGE,
                True,
            ),
            entry("test_rate", "TESTRATE", ModelDimension.RATES, Transform.LEVEL, False),
        ),
        derived=(),
    )
