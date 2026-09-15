"""Research arm A3: growth and inflation surprises, and the quadrants they cut.

Experiment 0002 registers arm A3 (quadrant-structure-surprises) with a leakage
note: an expectation model fitted once on the whole panel would recreate the
look-ahead ADR 0008 closed, so the surprise at month s must use coefficients
estimated strictly before s. The first group of tests pins exactly that, and one
of them shows the same check failing on the leak it guards against, so a pass
means something.

The rest pin the other two parts of the change: the state count is fixed at four
while the sweep still runs and is reported, and every restart starts at the four
quadrant centroids. The hyperparameters are read back from the registration
itself, so the code and the pre-registration cannot drift apart unnoticed.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from datetime import date

import numpy as np
import pandas as pd
import pytest

from economic_regime_forecasting.backtest.state_count_on_burn_in import (
    BurnInStateCountChoice,
    choose_state_count_on_burn_in_window,
)
from economic_regime_forecasting.backtest.walk_forward import BacktestError, fit_regime_model
from economic_regime_forecasting.configuration.registry import EconomicSeriesRegistry
from economic_regime_forecasting.configuration.run_settings import (
    DEFAULT_RUN_SETTINGS,
    PROJECT_ROOT,
    CacheLayout,
    RunSettings,
)
from economic_regime_forecasting.data.cache import SeriesCache, SeriesSnapshot
from economic_regime_forecasting.data.panel import assemble_point_in_time_panel
from economic_regime_forecasting.features.observation_matrix import (
    COLUMN_NAMES,
    ObservationMatrixError,
    build_observation_matrix,
    observations_as_configured,
    replace_growth_and_inflation_with_surprises,
)
from economic_regime_forecasting.features.transforms import (
    MINIMUM_MONTHS_BEFORE_FIRST_SURPRISE,
    TransformError,
    recursive_autoregressive_surprise,
)
from economic_regime_forecasting.models import gaussian_hidden_markov_model as hidden_markov
from economic_regime_forecasting.models.gaussian_hidden_markov_model import (
    HiddenMarkovModelError,
)
from economic_regime_forecasting.models.surprise_quadrants import (
    QUADRANT_COUNT,
    QuadrantInitialisationError,
    state_count_fixed_by_the_quadrant_structure,
    surprise_quadrant_centroids,
)

EXPERIMENT = PROJECT_ROOT / "proving/experiments/0002-research-slate-2026-09/experiment.json"
ARM = "A3-quadrant-structure-surprises"
MAIN_REFERENCE_CONFIGURATION_HASH = "ad7fcc1affd0746a"

ARM_SETTINGS_FOR_SMALL_FITS: dict[str, object] = {
    "random_seed": 20260908,
    "hidden_state_counts_to_search": (1, 2),
    "expectation_maximisation_restarts": 2,
    "expectation_maximisation_max_iterations": 25,
    "expectation_maximisation_tolerance": 1e-4,
    "growth_and_inflation_surprise_quadrants": True,
}


def _autoregressive_series(months: int = 240, seed: int = 20260915) -> pd.Series:
    """A persistent series with an intercept, the shape a year-over-year rate has."""
    generator = np.random.default_rng(seed)
    values = np.empty(months)
    values[0] = 1.0
    for month in range(1, months):
        values[month] = 0.2 + 0.9 * values[month - 1] + generator.normal(0.0, 0.3)
    index = pd.date_range("1960-01-01", periods=months, freq="MS")
    return pd.Series(values, index=index, name="test_series")


def _full_sample_surprise(series: pd.Series, minimum: int) -> pd.Series:
    """The leak the registration warns about: ONE regression over every month.

    Defined here only so a test can show the invariance check failing on it.
    """
    values = series.to_numpy(dtype="float64")
    design = np.column_stack([np.ones(values.size - 1), values[:-1]])
    (intercept, slope), *_ = np.linalg.lstsq(design, values[1:], rcond=None)
    surprises = np.full(values.size, np.nan)
    surprises[minimum:] = values[minimum:] - (intercept + slope * values[minimum - 1 : -1])
    return pd.Series(surprises, index=series.index)


# ------------------------------------------------------ the registration


def test_the_hyperparameters_in_force_are_the_pre_registered_ones() -> None:
    """K = 4 and sixty months, read from the registration rather than restated."""
    registered = json.loads(EXPERIMENT.read_text())["arms"][ARM]["hyperparameters"]
    assert registered["state_count"] == QUADRANT_COUNT == 4
    assert (
        registered["minimum_months_before_first_surprise"]
        == MINIMUM_MONTHS_BEFORE_FIRST_SURPRISE
        == 60
    )
    assert "AR(1) with intercept" in registered["expectation_model"]
    assert "recursive" in registered["expectation_model"]


def test_every_command_on_this_branch_runs_the_arm_by_default() -> None:
    assert DEFAULT_RUN_SETTINGS.growth_and_inflation_surprise_quadrants is True
    assert state_count_fixed_by_the_quadrant_structure(DEFAULT_RUN_SETTINGS) == 4


def test_mains_configuration_is_untouched_and_keeps_mains_digest() -> None:
    """`RunSettings()` is still main's run, so it must still hash to the reference
    run's digest recorded in the registration, and the arm must not."""
    registered = json.loads(EXPERIMENT.read_text())["reference_run"]["configuration_hash"]
    assert registered == MAIN_REFERENCE_CONFIGURATION_HASH
    main = RunSettings()
    assert main.growth_and_inflation_surprise_quadrants is False
    assert state_count_fixed_by_the_quadrant_structure(main) is None
    assert main.configuration_hash() == MAIN_REFERENCE_CONFIGURATION_HASH
    assert DEFAULT_RUN_SETTINGS.configuration_hash() != MAIN_REFERENCE_CONFIGURATION_HASH


# ------------------------------------------------ the surprise, point in time


def test_no_surprise_is_issued_before_sixty_months_of_history() -> None:
    surprises = recursive_autoregressive_surprise(_autoregressive_series(), 60)
    assert surprises.iloc[:60].isna().all()
    assert np.isfinite(surprises.iloc[60:]).all()


def test_each_surprise_is_its_own_least_squares_fit_on_strictly_earlier_months() -> None:
    """The running sums against one explicit regression per month."""
    series = _autoregressive_series()
    values = series.to_numpy()
    surprises = recursive_autoregressive_surprise(series, 60).to_numpy()
    for position in (60, 61, 97, 150, len(values) - 1):
        earlier = values[:position]  # months 0 .. s - 1, and nothing after
        design = np.column_stack([np.ones(earlier.size - 1), earlier[:-1]])
        (intercept, slope), *_ = np.linalg.lstsq(design, earlier[1:], rcond=None)
        expected = values[position] - (intercept + slope * values[position - 1])
        assert surprises[position] == pytest.approx(expected, abs=1e-10), position


def test_changing_any_later_month_leaves_every_earlier_surprise_byte_identical() -> None:
    """The registration's leakage requirement, as an invariance: the surprise at s
    may not move when anything after s moves. Exact, not approximate."""
    series = _autoregressive_series()
    original = recursive_autoregressive_surprise(series, 60).to_numpy()
    generator = np.random.default_rng(7)
    for cut in (60, 75, 120, 200):
        perturbed = series.copy()
        perturbed.iloc[cut + 1 :] += generator.normal(0.0, 5.0, size=len(series) - cut - 1)
        moved = recursive_autoregressive_surprise(perturbed, 60).to_numpy()
        assert np.array_equal(original[: cut + 1], moved[: cut + 1], equal_nan=True), cut
        truncated = recursive_autoregressive_surprise(series.iloc[: cut + 1], 60).to_numpy()
        assert np.array_equal(original[: cut + 1], truncated, equal_nan=True), cut


def test_the_same_check_catches_a_single_full_sample_regression() -> None:
    """Without this, the invariance above could be passing vacuously."""
    series = _autoregressive_series()
    perturbed = series.copy()
    perturbed.iloc[150:] += 3.0
    leaky_before = _full_sample_surprise(series, 60).to_numpy()
    leaky_after = _full_sample_surprise(perturbed, 60).to_numpy()
    assert not np.array_equal(leaky_before[60:150], leaky_after[60:150])
    honest_before = recursive_autoregressive_surprise(series, 60).to_numpy()
    honest_after = recursive_autoregressive_surprise(perturbed, 60).to_numpy()
    assert np.array_equal(honest_before[:150], honest_after[:150], equal_nan=True)


def test_a_surprise_moves_one_for_one_with_its_own_month() -> None:
    """The month being described is read only as the value, never by the fit."""
    series = _autoregressive_series()
    original = recursive_autoregressive_surprise(series, 60)
    shifted = series.copy()
    shifted.iloc[100] += 1.5
    moved = recursive_autoregressive_surprise(shifted, 60)
    assert moved.iloc[100] - original.iloc[100] == pytest.approx(1.5, abs=1e-12)
    assert np.array_equal(
        original.iloc[:100].to_numpy(), moved.iloc[:100].to_numpy(), equal_nan=True
    )


def test_too_little_history_a_gap_or_a_constant_input_is_refused() -> None:
    series = _autoregressive_series()
    with pytest.raises(TransformError, match="at least 3 months"):
        recursive_autoregressive_surprise(series, 2)
    holed = series.copy()
    holed.iloc[30] = np.nan
    with pytest.raises(TransformError, match="unbroken run of months"):
        recursive_autoregressive_surprise(holed, 60)
    constant = pd.Series(np.ones(100), index=series.index[:100], name="flat")
    with pytest.raises(TransformError, match="does not vary"):
        recursive_autoregressive_surprise(constant, 60)


def test_a_series_no_longer_than_the_minimum_has_no_surprise_at_all() -> None:
    surprises = recursive_autoregressive_surprise(_autoregressive_series(60), 60)
    assert surprises.isna().all()


# ------------------------------------------------------ the observation matrix


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
        as_published = series[series.index < pd.Timestamp(as_of) - pd.DateOffset(months=1)]
        cache.write(snapshot_factory(as_published, series_id=entry.series_id, vintage_date=as_of))


@pytest.fixture
def level_matrix(
    cache: SeriesCache,
    three_dimension_registry: EconomicSeriesRegistry,
    monthly_index: pd.DatetimeIndex,
    snapshot_factory: Callable[..., SeriesSnapshot],
):  # type: ignore[no-untyped-def]
    as_of = date(2005, 1, 1)
    _fill_cache(cache, three_dimension_registry, snapshot_factory, monthly_index, as_of)
    return build_observation_matrix(
        assemble_point_in_time_panel(three_dimension_registry, as_of, cache),
        three_dimension_registry,
    )


def test_the_arm_replaces_growth_and_inflation_and_leaves_rates_alone(level_matrix) -> None:  # type: ignore[no-untyped-def]
    arm = observations_as_configured(level_matrix, DEFAULT_RUN_SETTINGS)
    assert tuple(arm.standardised.columns) == COLUMN_NAMES
    assert len(arm) == len(level_matrix) - 60
    assert arm.dates[-1] == level_matrix.dates[-1]
    assert arm.as_of == level_matrix.as_of

    kept = arm.dates
    assert np.array_equal(
        arm.standardised["rates"].to_numpy(),
        level_matrix.standardised.loc[kept, "rates"].to_numpy(),
    )
    for column in ("growth", "inflation"):
        expected = recursive_autoregressive_surprise(level_matrix.standardised[column], 60)
        assert np.array_equal(arm.standardised[column].to_numpy(), expected.loc[kept].to_numpy())
    assert arm.transformed.index.equals(arm.standardised.index)
    assert np.isfinite(arm.values).all()


def test_mains_configuration_reads_the_matrix_untouched(level_matrix) -> None:  # type: ignore[no-untyped-def]
    assert observations_as_configured(level_matrix, RunSettings()) is level_matrix


def test_a_matrix_too_short_for_any_surprise_says_so(level_matrix) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ObservationMatrixError, match="before its first surprise"):
        replace_growth_and_inflation_with_surprises(level_matrix, len(level_matrix))


# ---------------------------------------------------------- quadrant centroids


def test_each_centroid_is_the_mean_of_its_quadrant_in_every_column() -> None:
    observations = np.array(
        [
            [-1.0, -2.0, 10.0],
            [-3.0, -4.0, 20.0],  # growth down, inflation down
            [-1.0, 2.0, 30.0],  # growth down, inflation up
            [1.0, -1.0, 40.0],
            [3.0, -3.0, 60.0],  # growth up, inflation down
            [2.0, 2.0, 70.0],  # growth up, inflation up
            [0.0, 0.0, 80.0],  # exactly zero counts as at or below
        ]
    )
    centroids = surprise_quadrant_centroids(observations)
    assert centroids.shape == (QUADRANT_COUNT, 3)
    np.testing.assert_array_equal(centroids[0], [-4.0 / 3.0, -2.0, 110.0 / 3.0])
    np.testing.assert_array_equal(centroids[1], [-1.0, 2.0, 30.0])
    np.testing.assert_array_equal(centroids[2], [2.0, -2.0, 50.0])
    np.testing.assert_array_equal(centroids[3], [2.0, 2.0, 70.0])


def test_an_empty_quadrant_is_refused_rather_than_filled_at_random() -> None:
    no_high_inflation = np.array([[1.0, -1.0, 0.0], [-1.0, -1.0, 0.0], [2.0, -0.5, 1.0]])
    with pytest.raises(QuadrantInitialisationError, match="no month has a growth surprise"):
        surprise_quadrant_centroids(no_high_inflation)
    with pytest.raises(QuadrantInitialisationError, match="columns"):
        surprise_quadrant_centroids(np.zeros((5, 2)))


def test_every_restart_starts_at_the_given_means_and_keeps_its_own_persistence() -> None:
    generator = np.random.default_rng(3)
    observations = generator.normal(size=(120, 3))
    means = surprise_quadrant_centroids(observations)
    pooled = np.cov(observations, rowvar=False)
    first = hidden_markov._initial_model(observations, 4, generator, pooled, "full", means)
    second = hidden_markov._initial_model(observations, 4, generator, pooled, "full", means)
    np.testing.assert_array_equal(first.means, means)
    np.testing.assert_array_equal(second.means, means)
    assert not np.array_equal(first.transition_matrix, second.transition_matrix)


def test_a_fit_from_initial_means_is_deterministic_and_refuses_the_wrong_shape() -> None:
    generator = np.random.default_rng(5)
    observations = generator.normal(size=(150, 3))
    means = surprise_quadrant_centroids(observations)
    one = hidden_markov.fit(
        observations, 4, seed=11, restarts=2, max_iterations=30, initial_means=means
    )
    two = hidden_markov.fit(
        observations, 4, seed=11, restarts=2, max_iterations=30, initial_means=means
    )
    assert one.to_dictionary() == two.to_dictionary()
    with pytest.raises(HiddenMarkovModelError, match="initial means are shaped"):
        hidden_markov.fit(observations, 3, seed=11, restarts=1, initial_means=means)


# ---------------------------------------------------- the fixed state count


@pytest.fixture
def filled_cache(
    cache: SeriesCache,
    three_dimension_registry: EconomicSeriesRegistry,
    snapshot_factory: Callable[..., SeriesSnapshot],
) -> SeriesCache:
    """Thirty-plus years of two-regime data, with honest vintages at every month."""
    months = 400
    index = pd.date_range("1950-01-01", periods=months, freq="MS", name="observation_date")
    generator = np.random.default_rng(20260911)
    transitions = np.array([[0.97, 0.03], [0.05, 0.95]])
    state = 0
    output, prices, rate = [100.0], [100.0], []
    for _ in range(months):
        state = int(generator.choice(2, p=transitions[state]))
        output.append(output[-1] * (1.0 + (0.004 if state == 0 else -0.002)))
        prices.append(prices[-1] * (1.0 + (0.002 if state == 0 else 0.006)))
        rate.append((4.5 if state == 0 else 0.6) + float(generator.normal(0, 0.2)))
    values = {
        "TESTOUT": pd.Series(output[1:], index=index)
        * np.exp(generator.normal(0, 0.004, size=months)),
        "TESTCPI": pd.Series(prices[1:], index=index)
        * np.exp(generator.normal(0, 0.002, size=months)),
        "TESTRATE": pd.Series(np.clip(rate, 0.0, None), index=index),
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


def test_the_burn_in_choice_is_four_while_the_sweep_still_runs_and_is_reported(
    three_dimension_registry: EconomicSeriesRegistry,
    filled_cache: SeriesCache,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    arm = RunSettings(**ARM_SETTINGS_FOR_SMALL_FITS, cache=CacheLayout(tmp_path / "cache"))
    main = dataclasses.replace(arm, growth_and_inflation_surprise_quadrants=False)
    first_forecast_date = date(1980, 1, 1)

    arm_choice = choose_state_count_on_burn_in_window(
        three_dimension_registry, filled_cache, arm, first_forecast_date
    )
    main_choice = choose_state_count_on_burn_in_window(
        three_dimension_registry, filled_cache, main, first_forecast_date
    )

    assert arm_choice.state_count == 4
    assert arm_choice.state_count_recommended_by_the_sweep in (1, 2)
    assert [row["states"] for row in arm_choice.sweep_rows] == [1, 2]
    assert "fixed by the surprise quadrant structure" in arm_choice.reason
    assert main_choice.state_count == main_choice.state_count_recommended_by_the_sweep
    # Sixty months of surprise burn-in drop from the start; the end never moves.
    assert arm_choice.months_in_burn_in_panel == main_choice.months_in_burn_in_panel - 60
    assert arm_choice.panel_end == main_choice.panel_end < first_forecast_date
    assert BurnInStateCountChoice.from_manifest(arm_choice.as_manifest()) == arm_choice


def test_a_refit_under_the_arm_uses_four_states_and_refuses_any_other_count(
    three_dimension_registry: EconomicSeriesRegistry,
    filled_cache: SeriesCache,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    arm = RunSettings(**ARM_SETTINGS_FOR_SMALL_FITS, cache=CacheLayout(tmp_path / "cache"))
    as_of = date(1980, 1, 1)
    with pytest.raises(BacktestError, match="fixes the state count at 4"):
        fit_regime_model(as_of, three_dimension_registry, filled_cache, {}, arm, 2)

    fitted = fit_regime_model(as_of, three_dimension_registry, filled_cache, {}, arm, 4)
    levels = build_observation_matrix(
        assemble_point_in_time_panel(three_dimension_registry, as_of, filled_cache),
        three_dimension_registry,
    )
    assert fitted.model.state_count == 4
    assert fitted.months_fitted_on == len(levels) - 60
