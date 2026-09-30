"""Experiment 0008, arm B3: the issued forecast is half the model and half the chain.

The registration (proving/experiments/0008-condition-aware-regime-forecasts/
experiment.json, arm ``B3-equal-blend-with-the-chain``) says, in full:
``p = 0.5 * p_model + 0.5 * p_R2`` at every indicator and horizon, where ``p_R2`` is
the ``condition_chain_probability`` column at every-forecast-date cadence; the model
is unchanged; a missing R2 value raises; the weight is 0.5, fixed, never fitted. Its
one required check is that R2 reads only conditions published by the forecast date
and no outcome at all.

Each of those sentences is pinned below, on synthetic data and offline. The
forecast-now test ties today's grid to the backtest row the walk-forward would
issue on the same date, so today's number comes out of the same method that was
scored.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from economic_regime_forecasting import command_line_interface as interface
from economic_regime_forecasting.backtest import schedule as schedule_module
from economic_regime_forecasting.backtest import walk_forward
from economic_regime_forecasting.backtest.walk_forward import (
    RESULT_COLUMNS,
    ConditionChainCadence,
    IndicatorHistory,
    ResolvedOutcomeTotals,
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
from economic_regime_forecasting.configuration.run_settings import (
    ARTIFACTS,
    DEFAULT_RUN_SETTINGS,
    CacheLayout,
    RunSettings,
)
from economic_regime_forecasting.data.cache import ArtifactStore, SeriesCache, SeriesSnapshot
from economic_regime_forecasting.models import indicator_forecast
from economic_regime_forecasting.models.indicator_forecast import (
    CONDITION_CHAIN_BLEND_WEIGHT,
    ForecastCompositionError,
    blend_equally_with_the_condition_chain,
)

REFERENCE_0008_CONFIGURATION_HASH = "fec79a040f9ca6f9"
"""reference_run.configuration_hash in experiment 0008's registration."""

MONTHS = 480
START = "1970-01-01"
FIRST_FORECAST = date(2000, 1, 1)
LAST_FORECAST = date(2000, 12, 1)


# ------------------------------------------------------------------ fixtures


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
        observation_start=date(1970, 1, 1),
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
    """One indicator on each composition path, so both are blended."""
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
            horizons_in_years=(1, 5),
        ),
        BinaryIndicator(
            name="rate_below_one_within_horizon",
            question="does the rate fall below one within the horizon",
            resolution=IndicatorResolution(
                series="synthetic_rate",
                rule=ResolutionRule.LEVEL_BELOW_THRESHOLD_WITHIN_HORIZON,
                transform=Transform.LEVEL,
                threshold=1.0,
            ),
            composition=Composition.ANY_TIME_WITHIN_HORIZON,
            horizons_in_years=(1, 5),
        ),
    )


@pytest.fixture
def filled_cache(
    cache: SeriesCache, snapshot_factory: Callable[..., SeriesSnapshot]
) -> SeriesCache:
    """Forty years of two-regime data, with vintages that stop where real ones do."""
    index = pd.date_range(START, periods=MONTHS, freq="MS", name="observation_date")
    generator = np.random.default_rng(20260929)
    transitions = np.array([[0.97, 0.03], [0.05, 0.95]])
    state = 0
    output, prices, rate = [100.0], [100.0], []
    for _ in range(MONTHS):
        state = int(generator.choice(2, p=transitions[state]))
        output.append(output[-1] * (1.0 + (0.004 if state == 0 else -0.002)))
        prices.append(prices[-1] * (1.0 + (0.002 if state == 0 else 0.006)))
        rate.append((4.5 if state == 0 else 0.6) + float(generator.normal(0, 0.2)))
    values = {
        "SYNOUT": pd.Series(output[1:], index=index),
        "SYNCPI": pd.Series(prices[1:], index=index),
        "SYNRATE": pd.Series(np.clip(rate, 0.0, None), index=index),
    }
    for series_id, series in values.items():
        cache.write(snapshot_factory(series, series_id=series_id))
        for stamp in index:
            as_published = series[series.index < stamp - pd.DateOffset(months=1)]
            if as_published.empty:
                continue
            cache.write(
                snapshot_factory(as_published, series_id=series_id, vintage_date=stamp.date())
            )
    return cache


def _settings(tmp_path: Path, *, blend: bool) -> RunSettings:
    return RunSettings(
        random_seed=99,
        expectation_maximisation_restarts=3,
        expectation_maximisation_max_iterations=80,
        minimum_observations_before_first_fit=180,
        refit_every_n_months=24,
        forecast_horizons_in_months=(12, 60),
        blend_the_model_equally_with_the_condition_chain=blend,
        cache=CacheLayout(tmp_path / "artifacts"),
    )


def _walk(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    cache: SeriesCache,
    settings: RunSettings,
    *,
    first: date = FIRST_FORECAST,
    last: date = LAST_FORECAST,
    cadence: ConditionChainCadence = ConditionChainCadence.EVERY_FORECAST_DATE,
) -> pd.DataFrame:
    schedule = schedule_module.build_schedule(first, last, settings.refit_every_n_months)
    return run_walk_forward(
        registry,
        indicators,
        cache,
        settings,
        2,
        schedule.forecast_dates,
        schedule.refit_dates,
        artifacts=None,
        progress_every=0,
        condition_chain_cadence=cadence,
    )


def _with_histories_changed(
    monkeypatch: pytest.MonkeyPatch, change: Callable[[IndicatorHistory], IndicatorHistory]
) -> None:
    """Hand the walk-forward histories edited by ``change``, and nothing else."""
    honest = walk_forward.prepare_indicator_history

    def prepare(*arguments: Any, **keywords: Any) -> dict[str, IndicatorHistory]:
        return {name: change(history) for name, history in honest(*arguments, **keywords).items()}

    monkeypatch.setattr(walk_forward, "prepare_indicator_history", prepare)


def _published_on(history: IndicatorHistory) -> pd.DatetimeIndex:
    """When each month of the condition was published, by the walk-forward's own rule."""
    return walk_forward.publication_dates(
        pd.DatetimeIndex(history.monthly_condition.index),
        history.publication_lag_days,
        dated_by_announcement=history.dated_by_announcement,
    )


# ------------------------------------------------------------- the blend itself


@pytest.mark.parametrize(
    ("model", "chain"),
    [(0.0, 1.0), (1.0, 0.0), (0.2, 0.7), (0.123456789, 0.987654321), (0.5, 0.5), (1e-12, 0.3)],
)
def test_the_blend_is_half_the_model_and_half_the_chain_exactly(model: float, chain: float) -> None:
    """The registered formula, to the bit: no clipping, no reweighting."""
    assert blend_equally_with_the_condition_chain(model, chain) == 0.5 * model + 0.5 * chain


def test_the_weight_is_the_registered_one_half_and_is_not_a_setting() -> None:
    """Fixed by the registration, never fitted: a constant, so no configuration can
    carry a different weight under this arm's name."""
    assert CONDITION_CHAIN_BLEND_WEIGHT == 0.5
    assert not any("weight" in field.name for field in dataclasses.fields(RunSettings))


@pytest.mark.parametrize("chain", [float("nan"), float("inf"), -0.01, 1.01])
def test_a_missing_or_impossible_chain_value_raises_rather_than_falling_back(
    chain: float,
) -> None:
    with pytest.raises(ForecastCompositionError, match="reference chain"):
        blend_equally_with_the_condition_chain(0.4, chain)


def test_a_missing_model_value_raises_too() -> None:
    with pytest.raises(ForecastCompositionError, match="model"):
        blend_equally_with_the_condition_chain(float("nan"), 0.4)


# ------------------------------------------------------------------ the setting


def test_the_arm_blends_by_default_on_this_branch() -> None:
    assert DEFAULT_RUN_SETTINGS.blend_the_model_equally_with_the_condition_chain is True


def test_with_the_blend_off_the_configuration_is_reference_0008s() -> None:
    """Off is main exactly, so it must carry the reference run's identity and read
    main's cached fits; on is a different run and must say so."""
    off = dataclasses.replace(
        DEFAULT_RUN_SETTINGS, blend_the_model_equally_with_the_condition_chain=False
    )
    assert off.configuration_hash() == REFERENCE_0008_CONFIGURATION_HASH
    assert DEFAULT_RUN_SETTINGS.configuration_hash() != REFERENCE_0008_CONFIGURATION_HASH


# ------------------------------------------------------------ the walk-forward


def test_the_issued_probability_is_half_the_model_and_half_the_reference_column(
    registry, indicators, filled_cache, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """Every row, both compositions, both horizons: the blended run's issued number
    is exactly half the unblended run's plus half its own R2 column."""
    blended = _walk(registry, indicators, filled_cache, _settings(tmp_path, blend=True))
    model_alone = _walk(registry, indicators, filled_cache, _settings(tmp_path, blend=False))

    expected = (
        0.5 * model_alone["predicted_probability"].to_numpy()
        + 0.5 * blended["condition_chain_probability"].to_numpy()
    )
    np.testing.assert_array_equal(blended["predicted_probability"].to_numpy(), expected)
    assert set(blended["composition"]) == {
        Composition.POINT_IN_TIME.value,
        Composition.ANY_TIME_WITHIN_HORIZON.value,
    }
    assert set(blended["horizon_months"]) == {12, 60}
    # A blend that changed nothing would pass the identity above only if the model
    # already equalled the chain; it does not.
    assert not np.array_equal(
        blended["predicted_probability"].to_numpy(), model_alone["predicted_probability"].to_numpy()
    )


def test_the_blend_moves_only_the_issued_probability_and_the_run_identity(
    registry, indicators, filled_cache, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """The model is unchanged, and so are the reference column and the columns that
    describe the model (effective sample size, distance to stationary)."""
    blended = _walk(registry, indicators, filled_cache, _settings(tmp_path, blend=True))
    model_alone = _walk(registry, indicators, filled_cache, _settings(tmp_path, blend=False))
    untouched = [
        column
        for column in RESULT_COLUMNS
        if column not in ("predicted_probability", "configuration_hash")
    ]
    pd.testing.assert_frame_equal(blended[untouched], model_alone[untouched])
    assert blended["configuration_hash"].nunique() == 1
    assert (blended["configuration_hash"] != model_alone["configuration_hash"]).all()


def test_the_blend_reads_the_every_forecast_date_chain_whatever_the_cadence(
    registry, indicators, filled_cache, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """The registration names R2 at every-forecast-date cadence. The cadence argument
    exists for arm B1's checks and changes only what the reference column holds."""
    settings = _settings(tmp_path, blend=True)
    monthly = _walk(registry, indicators, filled_cache, settings)
    at_refits = _walk(
        registry, indicators, filled_cache, settings, cadence=ConditionChainCadence.REFIT
    )
    np.testing.assert_array_equal(
        monthly["predicted_probability"].to_numpy(), at_refits["predicted_probability"].to_numpy()
    )
    assert not monthly["condition_chain_probability"].equals(
        at_refits["condition_chain_probability"]
    )


def _a_chain_that_is_missing(
    indicator: BinaryIndicator,
    published_condition: pd.Series,
    forecast_date: pd.Timestamp,
    rates: Any,
    longest_horizon_in_months: int,
) -> np.ndarray:
    return np.full(longest_horizon_in_months, np.nan)


def test_a_missing_reference_chain_value_raises_in_the_walk_forward(
    registry, indicators, filled_cache, tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(walk_forward, "condition_chain_at_every_horizon", _a_chain_that_is_missing)
    with pytest.raises(ForecastCompositionError, match="reference chain"):
        _walk(registry, indicators, filled_cache, _settings(tmp_path, blend=True))


def test_a_chain_with_no_published_condition_to_start_from_raises(indicators) -> None:  # type: ignore[no-untyped-def]
    indicator = indicators[0]
    condition = pd.Series(
        [0.0, 1.0, 1.0, 0.0], index=pd.date_range("1999-01-01", periods=4, freq="MS")
    )
    rates = walk_forward.condition_chain_rates(
        indicator, condition, pd.Timestamp("1999-01-01"), shrinkage_strength=10.0
    )
    with pytest.raises(walk_forward.BacktestError, match="no published condition"):
        walk_forward.condition_chain_at_every_horizon(
            indicator, condition.iloc[0:0], pd.Timestamp("2000-01-01"), rates, 12
        )


# ----------------------------------------------- the required look-ahead check


def test_no_condition_unpublished_at_a_forecast_date_reaches_its_blended_forecast(
    registry, indicators, filled_cache, tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """Required check, first half: R2 reads only conditions published by the date.

    Every month of every condition not yet published at the LAST forecast date is
    flipped. No forecast in the schedule may move, the blended number and the
    reference column alike, because no forecast date could have read those months.
    """
    settings = _settings(tmp_path, blend=True)
    honest = _walk(registry, indicators, filled_cache, settings)

    last = pd.Timestamp(LAST_FORECAST)

    def flip_the_unpublished(history: IndicatorHistory) -> IndicatorHistory:
        condition = history.monthly_condition.copy()
        unpublished = np.asarray(_published_on(history) > last)
        assert unpublished.any()
        condition[unpublished] = 1.0 - condition[unpublished]
        return dataclasses.replace(history, monthly_condition=condition)

    _with_histories_changed(monkeypatch, flip_the_unpublished)
    tampered = _walk(registry, indicators, filled_cache, settings)

    for column in ("predicted_probability", "condition_chain_probability"):
        np.testing.assert_array_equal(tampered[column].to_numpy(), honest[column].to_numpy())


def test_a_condition_published_by_the_forecast_date_does_reach_it(
    registry, indicators, filled_cache, tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """The control that gives the test above its teeth: flip the last month published
    by the first forecast date, and that date's blended forecast moves."""
    settings = _settings(tmp_path, blend=True)
    first = pd.Timestamp(FIRST_FORECAST)
    honest = _walk(registry, indicators, filled_cache, settings, last=FIRST_FORECAST)

    def flip_the_last_published(history: IndicatorHistory) -> IndicatorHistory:
        condition = history.monthly_condition.copy()
        published = np.flatnonzero(np.asarray(_published_on(history) <= first))
        condition.iloc[published[-1]] = 1.0 - condition.iloc[published[-1]]
        return dataclasses.replace(history, monthly_condition=condition)

    _with_histories_changed(monkeypatch, flip_the_last_published)
    tampered = _walk(registry, indicators, filled_cache, settings, last=FIRST_FORECAST)

    assert (
        tampered["predicted_probability"].to_numpy() != honest["predicted_probability"].to_numpy()
    ).all()


def test_no_outcome_reaches_the_blended_forecast(
    registry, indicators, filled_cache, tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """Required check, second half: R2 reads no outcome at all.

    Every outcome is flipped and both benchmarks are rebuilt from the flipped
    outcomes. The benchmarks and the realised outcomes move; the blended forecast
    and the reference column do not. This is what separates B3 from experiment
    0002's arm A6, which blended in a climatology averaging revised outcomes.
    """
    settings = _settings(tmp_path, blend=True)
    honest = _walk(registry, indicators, filled_cache, settings)

    def flip_every_outcome(history: IndicatorHistory) -> IndicatorHistory:
        flipped = {h: 1.0 - outcomes for h, outcomes in history.outcomes_by_horizon.items()}
        return dataclasses.replace(
            history,
            outcomes_by_horizon=flipped,
            climatology_by_horizon={
                h: walk_forward._expanding_climatology(
                    outcomes, h, history.publication_lag_days, history.dated_by_announcement
                )
                for h, outcomes in flipped.items()
            },
            outcome_totals_by_horizon={
                h: ResolvedOutcomeTotals.from_outcomes(
                    outcomes,
                    walk_forward.outcome_publication_dates(
                        outcomes, h, history.publication_lag_days, history.dated_by_announcement
                    ),
                )
                for h, outcomes in flipped.items()
            },
        )

    _with_histories_changed(monkeypatch, flip_every_outcome)
    tampered = _walk(registry, indicators, filled_cache, settings)

    for column in ("predicted_probability", "condition_chain_probability"):
        np.testing.assert_array_equal(tampered[column].to_numpy(), honest[column].to_numpy())
    for column in ("realised_outcome", "model_sample_climatology_probability"):
        assert not tampered[column].equals(honest[column]), column


# ------------------------------------------------------------------ forecast-now


def _workspace(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    cache: SeriesCache,
    settings: RunSettings,
    models: Path,
    today: date,
) -> interface.Workspace:
    """A workspace whose selected model has two regimes, as the walk-forward uses."""
    artifacts = ArtifactStore(models)
    histories = walk_forward.prepare_indicator_history(
        indicators, registry, cache, settings.forecast_horizons_in_months
    )
    fitted = walk_forward.fit_regime_model(today, registry, cache, histories, settings, 2)
    artifacts.write_json(ARTIFACTS.selected_model, fitted.model.to_dictionary())
    return interface.Workspace(
        registry=registry,
        indicators=indicators,
        cache=cache,
        artifacts=artifacts,
        settings=settings,
    )


def _todays_grid(workspace: interface.Workspace, today: date) -> pd.DataFrame:
    interface.forecast_now(workspace, today)
    return (
        workspace.artifacts.read_table(ARTIFACTS.current_forecasts)
        .sort_values(["indicator", "horizon_months"])
        .reset_index(drop=True)
    )


def test_todays_grid_is_the_blend_the_backtest_would_issue_on_the_same_date(
    registry, indicators, filled_cache, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """forecast-now uses the arm's method, not a copy of it.

    On a date that is also a refit date the walk-forward fits exactly the model
    forecast-now fits, so today's grid must equal that date's backtest rows: the
    chain to the bit, the issued number to the bit, and the model's own number to
    the unblended grid's.
    """
    today = FIRST_FORECAST
    blended_settings = _settings(tmp_path, blend=True)
    unblended_settings = _settings(tmp_path, blend=False)

    grid = _todays_grid(
        _workspace(registry, indicators, filled_cache, blended_settings, tmp_path / "on", today),
        today,
    )
    unblended_grid = _todays_grid(
        _workspace(registry, indicators, filled_cache, unblended_settings, tmp_path / "off", today),
        today,
    )
    backtest = (
        _walk(registry, indicators, filled_cache, blended_settings, first=today, last=today)
        .sort_values(["indicator", "horizon_months"])
        .reset_index(drop=True)
    )

    assert list(grid["indicator"]) == list(backtest["indicator"])
    assert list(grid["horizon_months"]) == list(backtest["horizon_months"])
    np.testing.assert_array_equal(
        grid["condition_chain_probability"].to_numpy(),
        backtest["condition_chain_probability"].to_numpy(),
    )
    np.testing.assert_array_equal(
        grid["probability"].to_numpy(), backtest["predicted_probability"].to_numpy()
    )
    np.testing.assert_array_equal(
        grid["model_probability"].to_numpy(), unblended_grid["probability"].to_numpy()
    )
    np.testing.assert_array_equal(
        grid["probability"].to_numpy(),
        0.5 * grid["model_probability"].to_numpy()
        + 0.5 * grid["condition_chain_probability"].to_numpy(),
    )
    # The evidence columns describe the model, blended or not.
    for column in ("effective_sample_size", "distance_to_stationary"):
        np.testing.assert_array_equal(grid[column].to_numpy(), unblended_grid[column].to_numpy())


def test_with_the_blend_off_todays_grid_keeps_mains_schema(
    registry, indicators, filled_cache, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    today = FIRST_FORECAST
    grid = _todays_grid(
        _workspace(
            registry,
            indicators,
            filled_cache,
            _settings(tmp_path, blend=False),
            tmp_path / "off",
            today,
        ),
        today,
    )
    assert "model_probability" not in grid.columns
    assert "condition_chain_probability" not in grid.columns


def test_a_missing_chain_value_raises_in_todays_grid_too(
    registry, indicators, filled_cache, tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """Never a model-only row issued under the arm's name."""
    today = FIRST_FORECAST
    workspace = _workspace(
        registry, indicators, filled_cache, _settings(tmp_path, blend=True), tmp_path / "on", today
    )
    monkeypatch.setattr(walk_forward, "condition_chain_at_every_horizon", _a_chain_that_is_missing)
    with pytest.raises(ForecastCompositionError, match="reference chain"):
        interface.forecast_now(workspace, today)
    assert not workspace.artifacts.has(ARTIFACTS.current_forecasts)


def test_the_blend_lives_below_the_backtest_layer() -> None:
    """One function issues the blended number for both the walk-forward and today's
    grid, and it lives in ``models``, where both may import it."""
    assert (
        indicator_forecast.blend_equally_with_the_condition_chain.__module__
        == "economic_regime_forecasting.models.indicator_forecast"
    )
