"""The advisory "no look-ahead" rule, made into an executable check.

`start_walk_forward_when_every_input_is_point_in_time` promises that every
forecast date in a walk-forward schedule is fitted on a panel where nothing fell
back to a revised value published later than the forecast date. Before this unit
that promise was prose. These tests pin the pre-flight assertion that enforces
it, the finder that computes the earliest date from which the promise can be
kept, and the two sad paths a scan over history must not fall into: reaching the
network, and returning a date past the end of an unsatisfiable range.

Everything here is offline: a small registry, a cache filled with generated
series, and hand-placed truncated vintages standing in for the real archive's
publication-lag fallback -- following the same idiom `filled_cache` uses in
`tests/test_walk_forward_backtest.py`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import numpy as np
import pandas as pd
import pytest

from economic_regime_forecasting.backtest import schedule as schedule_module
from economic_regime_forecasting.backtest.walk_forward import (
    BacktestError,
    find_first_fully_point_in_time_date,
    forecast_dates_using_the_publication_lag_fallback,
    run_walk_forward,
)
from economic_regime_forecasting.configuration.registry import (
    BinaryIndicator,
    Composition,
    EconomicSeries,
    EconomicSeriesRegistry,
    IndicatorResolution,
    ModelDimension,
    ResolutionRule,
    Transform,
)
from economic_regime_forecasting.configuration.run_settings import CacheLayout, RunSettings
from economic_regime_forecasting.data.cache import ArtifactStore, SeriesCache, SeriesSnapshot
from economic_regime_forecasting.data.vintage import LookAheadError

MONTHS = 500
START = "1960-01-01"


def _series_entry(
    name: str, series_id: str, dimension: ModelDimension, transform: Transform, is_revised: bool
) -> EconomicSeries:
    return EconomicSeries(
        name=name,
        series_id=series_id,
        description=f"synthetic {name}",
        role=dimension.value,
        model_dimension=dimension,
        frequency="monthly",
        units="units",
        transform=transform,
        publication_lag_days=45,
        observation_start=date(1960, 1, 1),
        is_revised=is_revised,
    )


@pytest.fixture
def registry() -> EconomicSeriesRegistry:
    return EconomicSeriesRegistry(
        series=(
            _series_entry(
                "synthetic_output",
                "SYNOUT",
                ModelDimension.GROWTH,
                Transform.YEAR_OVER_YEAR_LOG_CHANGE,
                True,
            ),
            _series_entry(
                "synthetic_prices",
                "SYNCPI",
                ModelDimension.INFLATION,
                Transform.YEAR_OVER_YEAR_LOG_CHANGE,
                True,
            ),
            _series_entry(
                "synthetic_rate", "SYNRATE", ModelDimension.RATES, Transform.LEVEL, False
            ),
        ),
        derived=(),
    )


@pytest.fixture
def indicators() -> tuple[BinaryIndicator, ...]:
    return (
        BinaryIndicator(
            name="rate_above_three_at_horizon",
            question="is the rate above three at the horizon",
            resolution=IndicatorResolution(
                series="synthetic_rate",
                rule=ResolutionRule.LEVEL_ABOVE_THRESHOLD_AT_HORIZON,
                transform=Transform.LEVEL,
                threshold=3.0,
            ),
            composition=Composition.POINT_IN_TIME,
            horizons_in_years=(1,),
        ),
    )


def _base_values() -> dict[str, pd.Series]:
    """Forty-plus years of two-regime data, generated once per test."""
    index = pd.date_range(START, periods=MONTHS, freq="MS", name="observation_date")
    generator = np.random.default_rng(20260910)
    transitions = np.array([[0.97, 0.03], [0.05, 0.95]])
    state = 0
    output, prices, rate = [100.0], [100.0], []
    for _ in range(MONTHS):
        state = int(generator.choice(2, p=transitions[state]))
        output.append(output[-1] * (1.0 + (0.004 if state == 0 else -0.002)))
        prices.append(prices[-1] * (1.0 + (0.002 if state == 0 else 0.006)))
        rate.append((4.5 if state == 0 else 0.6) + float(generator.normal(0, 0.2)))
    return {
        "SYNOUT": pd.Series(output[1:], index=index),
        "SYNCPI": pd.Series(prices[1:], index=index),
        "SYNRATE": pd.Series(np.clip(rate, 0.0, None), index=index),
    }


def _write_cache_with_fallback_dates(
    cache: SeriesCache,
    snapshot_factory: Callable[..., SeriesSnapshot],
    values: dict[str, pd.Series],
    candidate_dates: pd.DatetimeIndex,
    fallback_dates: set,
) -> None:
    """Every revised series gets an archival vintage at each candidate date;
    dates named in ``fallback_dates`` get a vintage truncated far below the
    usability bar, so ``vintage.observe`` falls back to the publication-lag
    policy exactly there and nowhere else."""
    for series_id, series in values.items():
        cache.write(snapshot_factory(series, series_id=series_id))
    for series_id in ("SYNOUT", "SYNCPI"):  # the two revised series
        series = values[series_id]
        for stamp in candidate_dates:
            as_of = stamp.date()
            full = series[series.index < pd.Timestamp(as_of) - pd.DateOffset(months=1)]
            view = full.iloc[-10:] if as_of in fallback_dates else full
            cache.write(snapshot_factory(view, series_id=series_id, vintage_date=as_of))


def _settings(tmp_path, start_switch: bool) -> RunSettings:  # type: ignore[no-untyped-def]
    return RunSettings(
        random_seed=99,
        expectation_maximisation_restarts=2,
        expectation_maximisation_max_iterations=30,
        minimum_observations_before_first_fit=180,
        refit_every_n_months=24,
        forecast_horizons_in_months=(12,),
        cache=CacheLayout(tmp_path / "cache"),
        start_walk_forward_when_every_input_is_point_in_time=start_switch,
    )


CANDIDATE_MONTHS = pd.date_range("1998-01-01", periods=6, freq="MS")
FALLBACK_MONTHS = {date(1998, 3, 1), date(1998, 4, 1)}


# --------------------------------------------------------------- the pre-flight


def test_the_pre_flight_raises_look_ahead_error_when_a_forecast_date_falls_back(
    cache: SeriesCache,
    snapshot_factory: Callable[..., SeriesSnapshot],
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    values = _base_values()
    schedule = schedule_module.build_schedule(date(1998, 1, 1), date(1998, 6, 1), 24)
    _write_cache_with_fallback_dates(
        cache, snapshot_factory, values, schedule.forecast_dates, FALLBACK_MONTHS
    )
    settings = _settings(tmp_path, start_switch=True)

    with pytest.raises(LookAheadError) as error:
        run_walk_forward(
            registry,
            indicators,
            cache,
            settings,
            2,
            schedule.forecast_dates,
            schedule.refit_dates,
            artifacts=None,
            progress_every=0,
        )
    message = str(error.value)
    assert "2 of 6" in message
    assert "1998-03" in message
    assert "fetch-data" in message


def test_the_pre_flight_raises_before_any_model_is_fitted(
    cache: SeriesCache,
    snapshot_factory: Callable[..., SeriesSnapshot],
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    """AC3: the message is not the only promise -- nothing may have been fitted
    by the time it fires. An `ArtifactStore` rooted in its own directory ends the
    test holding zero `model_*.json` files."""
    values = _base_values()
    schedule = schedule_module.build_schedule(date(1998, 1, 1), date(1998, 6, 1), 24)
    _write_cache_with_fallback_dates(
        cache, snapshot_factory, values, schedule.forecast_dates, FALLBACK_MONTHS
    )
    settings = _settings(tmp_path, start_switch=True)
    artifacts_directory = tmp_path / "artifacts_under_test"
    artifacts = ArtifactStore(artifacts_directory)

    with pytest.raises(LookAheadError):
        run_walk_forward(
            registry,
            indicators,
            cache,
            settings,
            2,
            schedule.forecast_dates,
            schedule.refit_dates,
            artifacts=artifacts,
            progress_every=0,
        )
    written_models = (
        list(artifacts_directory.glob("model_*.json")) if artifacts_directory.exists() else []
    )
    assert written_models == []


def test_the_pre_flight_does_not_fire_when_the_switch_is_off(
    cache: SeriesCache,
    snapshot_factory: Callable[..., SeriesSnapshot],
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    """AC4: the same fallback pattern, but the switch is off, so the walk-forward
    runs from the panel-length start and raises nothing."""
    values = _base_values()
    schedule = schedule_module.build_schedule(date(1998, 1, 1), date(1998, 6, 1), 24)
    _write_cache_with_fallback_dates(
        cache, snapshot_factory, values, schedule.forecast_dates, FALLBACK_MONTHS
    )
    settings = _settings(tmp_path, start_switch=False)

    results = run_walk_forward(
        registry,
        indicators,
        cache,
        settings,
        2,
        schedule.forecast_dates,
        schedule.refit_dates,
        artifacts=None,
        progress_every=0,
    )
    assert len(results) == 6 * len(indicators)


# --------------------------------------------------------------------- the finder


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_the_finder_survives_non_monotone_fallback_placement(
    cache: SeriesCache,
    snapshot_factory: Callable[..., SeriesSnapshot],
    registry: EconomicSeriesRegistry,
    tmp_path,
    seed: int,
) -> None:  # type: ignore[no-untyped-def]
    """Property: for randomly-placed truncated vintages (never on the final
    candidate, which is the boundary case below), the returned date `D` is
    followed by no fallback month, and `D` is either the earliest candidate or
    directly follows a month that did fall back. A naive "first clean month"
    implementation gets this wrong whenever the fallback pattern is not monotone
    -- exactly the real INDPRO/CPIAUCSL census this fix exists for."""
    values = _base_values()
    candidates = pd.date_range("1998-01-01", periods=12, freq="MS")
    generator = np.random.default_rng(seed)
    how_many = int(generator.integers(0, 6))
    chosen_positions = generator.choice(len(candidates) - 1, size=how_many, replace=False)
    fallback_dates = {candidates[position].date() for position in chosen_positions}
    _write_cache_with_fallback_dates(cache, snapshot_factory, values, candidates, fallback_dates)
    settings = _settings(tmp_path, start_switch=True)

    result = find_first_fully_point_in_time_date(
        registry, cache, settings, candidates[0].date(), candidates[-1].date()
    )

    remaining = pd.date_range(result, candidates[-1].date(), freq="MS")
    assert forecast_dates_using_the_publication_lag_fallback(registry, cache, remaining) == []
    if result != candidates[0].date():
        month_before = (pd.Timestamp(result) - pd.DateOffset(months=1)).date()
        assert month_before in fallback_dates


def test_the_finder_raises_rather_than_return_a_date_past_the_end(
    cache: SeriesCache,
    snapshot_factory: Callable[..., SeriesSnapshot],
    registry: EconomicSeriesRegistry,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    """The boundary case: when the very last candidate itself falls back there is
    no honest start inside the range, and returning a date past the end would
    silently produce an empty schedule instead."""
    values = _base_values()
    candidates = pd.date_range("1998-01-01", periods=6, freq="MS")
    fallback_dates = {candidates[-1].date()}
    _write_cache_with_fallback_dates(cache, snapshot_factory, values, candidates, fallback_dates)
    settings = _settings(tmp_path, start_switch=True)

    with pytest.raises(BacktestError, match="no fully point-in-time start"):
        find_first_fully_point_in_time_date(
            registry, cache, settings, candidates[0].date(), candidates[-1].date()
        )


def test_the_scanner_refuses_the_network_and_says_what_to_run_instead(
    cache: SeriesCache,
    snapshot_factory: Callable[..., SeriesSnapshot],
    registry: EconomicSeriesRegistry,
) -> None:  # type: ignore[no-untyped-def]
    """A scan over hundreds of dates against a half-populated cache must not turn
    into a network fetch. No archival vintage is cached at all here; the scanner
    must refuse before touching a single one of them, not after failing to fetch
    the first."""
    values = _base_values()
    candidates = pd.date_range("1998-01-01", periods=3, freq="MS")
    for series_id, series in values.items():
        cache.write(snapshot_factory(series, series_id=series_id))  # only the current vintage

    with pytest.raises(BacktestError, match="fetch-data"):
        forecast_dates_using_the_publication_lag_fallback(registry, cache, candidates)
