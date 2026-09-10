"""Selecting the number of regimes on a window that ends before the forecast.

`choose_state_count_on_burn_in_window` answers the question `forecast fit-regimes`
answers dishonestly for a backtest: instead of sweeping on the panel as it stands
today, it sweeps once on the panel as it stood at the first forecast date. These
tests pin the boundary assertion that makes that true, the determinism the
verdict depends on, the artifact-cache key discipline, and the arithmetic
`regimes_exist_from_sweep_table` shares with the full-sample path.

Offline throughout: a small registry (reusing `conftest.three_dimension_registry`)
and a cache filled with generated two-regime data, following the same idiom
`filled_cache` uses in `tests/test_walk_forward_backtest.py`.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from datetime import date

import numpy as np
import pandas as pd
import pytest

from economic_regime_forecasting.backtest import state_count_on_burn_in
from economic_regime_forecasting.backtest.state_count_on_burn_in import (
    BurnInSelectionError,
    choose_state_count_on_burn_in_window,
)
from economic_regime_forecasting.configuration.registry import EconomicSeriesRegistry
from economic_regime_forecasting.configuration.run_settings import CacheLayout, RunSettings
from economic_regime_forecasting.data.cache import ArtifactStore, SeriesCache, SeriesSnapshot
from economic_regime_forecasting.models.state_selection import regimes_exist_from_sweep_table

MONTHS = 400
START = "1950-01-01"

FIRST_FORECAST_DATES = (date(1970, 1, 1), date(1975, 6, 1), date(1980, 1, 1))


@pytest.fixture
def filled_cache(
    cache: SeriesCache,
    three_dimension_registry: EconomicSeriesRegistry,
    snapshot_factory: Callable[..., SeriesSnapshot],
) -> SeriesCache:
    """Thirty-plus years of two-regime data, with honest vintages at every month."""
    index = pd.date_range(START, periods=MONTHS, freq="MS", name="observation_date")
    generator = np.random.default_rng(20260911)
    transitions = np.array([[0.97, 0.03], [0.05, 0.95]])
    state = 0
    output, prices, rate = [100.0], [100.0], []
    for _ in range(MONTHS):
        state = int(generator.choice(2, p=transitions[state]))
        output.append(output[-1] * (1.0 + (0.004 if state == 0 else -0.002)))
        prices.append(prices[-1] * (1.0 + (0.002 if state == 0 else 0.006)))
        rate.append((4.5 if state == 0 else 0.6) + float(generator.normal(0, 0.2)))

    values = {
        "TESTOUT": pd.Series(output[1:], index=index),
        "TESTCPI": pd.Series(prices[1:], index=index),
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


@pytest.fixture
def settings(tmp_path) -> RunSettings:  # type: ignore[no-untyped-def]
    return RunSettings(
        random_seed=20260908,
        hidden_state_counts_to_search=(1, 2),
        expectation_maximisation_restarts=2,
        expectation_maximisation_max_iterations=25,
        expectation_maximisation_tolerance=1e-4,
        cache=CacheLayout(tmp_path / "cache"),
    )


# ------------------------------------------------------------- the boundary


def test_the_burn_in_window_always_ends_strictly_before_the_first_forecast_date(
    three_dimension_registry: EconomicSeriesRegistry,
    filled_cache: SeriesCache,
    settings: RunSettings,
) -> None:
    """AC7, as a property: true for every first forecast date tried, not one."""
    for first_forecast_date in FIRST_FORECAST_DATES:
        choice = choose_state_count_on_burn_in_window(
            three_dimension_registry, filled_cache, settings, first_forecast_date
        )
        assert choice.panel_end < choice.chosen_as_of
        assert choice.chosen_as_of == first_forecast_date


def test_the_choice_refuses_a_panel_that_reaches_the_first_forecast_date(
    monkeypatch: pytest.MonkeyPatch,
    three_dimension_registry: EconomicSeriesRegistry,
    filled_cache: SeriesCache,
    settings: RunSettings,
) -> None:
    """The assertion, forced to fire: a panel manufactured to reach past the
    first forecast date must be refused, naming both dates."""
    first_forecast_date = date(1975, 1, 1)
    dishonest_dates = pd.date_range("1973-01-01", periods=30, freq="MS")  # runs to 1975-06

    class _DishonestMatrix:
        dates = pd.DatetimeIndex(dishonest_dates)
        values = np.zeros((len(dishonest_dates), 3))

        def __len__(self) -> int:
            return len(dishonest_dates)

    monkeypatch.setattr(
        state_count_on_burn_in,
        "build_observation_matrix",
        lambda panel, registry: _DishonestMatrix(),
    )

    with pytest.raises(BurnInSelectionError) as error:
        choose_state_count_on_burn_in_window(
            three_dimension_registry, filled_cache, settings, first_forecast_date
        )
    message = str(error.value)
    assert "1975-01-01" in message
    assert str(dishonest_dates[-1].date()) in message


def test_the_choice_refuses_a_panel_whose_last_observation_exactly_equals_the_forecast_date(
    monkeypatch: pytest.MonkeyPatch,
    three_dimension_registry: EconomicSeriesRegistry,
    filled_cache: SeriesCache,
    settings: RunSettings,
) -> None:
    """The off-by-one this boundary exists to rule out: the docstring claims
    `panel_end < chosen_as_of` is "strictly before", but the pre-existing forced-
    failure test only ever manufactures a panel that runs *past* the forecast
    date, never one that lands exactly *on* it. A `<=` in place of `<` would let
    a panel labelled the same month as the forecast through -- the boundary case
    itself, not a case safely on either side of it -- and every other test in
    this file would still pass. This one would not."""
    first_forecast_date = date(1975, 1, 1)
    exact_boundary_dates = pd.date_range("1973-01-01", periods=25, freq="MS")  # last: 1975-01-01
    assert exact_boundary_dates[-1].date() == first_forecast_date

    class _ExactBoundaryMatrix:
        dates = pd.DatetimeIndex(exact_boundary_dates)
        values = np.zeros((len(exact_boundary_dates), 3))

        def __len__(self) -> int:
            return len(exact_boundary_dates)

    monkeypatch.setattr(
        state_count_on_burn_in,
        "build_observation_matrix",
        lambda panel, registry: _ExactBoundaryMatrix(),
    )

    with pytest.raises(BurnInSelectionError) as error:
        choose_state_count_on_burn_in_window(
            three_dimension_registry, filled_cache, settings, first_forecast_date
        )
    message = str(error.value)
    assert "1975-01-01" in message


# ------------------------------------------------------------- determinism


def test_two_fresh_computations_give_equal_sweep_rows(
    three_dimension_registry: EconomicSeriesRegistry,
    filled_cache: SeriesCache,
    settings: RunSettings,
) -> None:
    """AC8: computed twice from scratch (no artifact cache), the two `sweep`
    payloads must compare equal."""
    first = choose_state_count_on_burn_in_window(
        three_dimension_registry, filled_cache, settings, date(1975, 1, 1)
    )
    second = choose_state_count_on_burn_in_window(
        three_dimension_registry, filled_cache, settings, date(1975, 1, 1)
    )
    assert first.sweep_rows == second.sweep_rows
    assert first.state_count == second.state_count
    assert first.runner_up_state_count == second.runner_up_state_count


def test_the_artifact_cached_choice_round_trips_exactly(
    three_dimension_registry: EconomicSeriesRegistry,
    filled_cache: SeriesCache,
    settings: RunSettings,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    artifacts = ArtifactStore(tmp_path / "artifacts")
    first = choose_state_count_on_burn_in_window(
        three_dimension_registry, filled_cache, settings, date(1975, 1, 1), artifacts=artifacts
    )
    second = choose_state_count_on_burn_in_window(
        three_dimension_registry, filled_cache, settings, date(1975, 1, 1), artifacts=artifacts
    )
    assert second == first


def test_the_cache_key_changes_with_the_seed(
    three_dimension_registry: EconomicSeriesRegistry,
    filled_cache: SeriesCache,
    settings: RunSettings,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    directory = tmp_path / "artifacts"
    artifacts = ArtifactStore(directory)
    settings_a = dataclasses.replace(settings, random_seed=101)
    settings_b = dataclasses.replace(settings, random_seed=202)
    choose_state_count_on_burn_in_window(
        three_dimension_registry, filled_cache, settings_a, date(1975, 1, 1), artifacts=artifacts
    )
    choose_state_count_on_burn_in_window(
        three_dimension_registry, filled_cache, settings_b, date(1975, 1, 1), artifacts=artifacts
    )
    written = list(directory.glob("burn_in_state_count_choice_*.json"))
    assert len(written) == 2


def test_the_cache_key_changes_with_the_configuration_hash(
    three_dimension_registry: EconomicSeriesRegistry,
    filled_cache: SeriesCache,
    settings: RunSettings,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    directory = tmp_path / "artifacts"
    artifacts = ArtifactStore(directory)
    settings_a = dataclasses.replace(settings, select_state_count_on_a_burn_in_window=True)
    settings_b = dataclasses.replace(settings, select_state_count_on_a_burn_in_window=False)
    assert settings_a.configuration_hash() != settings_b.configuration_hash()
    choose_state_count_on_burn_in_window(
        three_dimension_registry, filled_cache, settings_a, date(1975, 1, 1), artifacts=artifacts
    )
    choose_state_count_on_burn_in_window(
        three_dimension_registry, filled_cache, settings_b, date(1975, 1, 1), artifacts=artifacts
    )
    written = list(directory.glob("burn_in_state_count_choice_*.json"))
    assert len(written) == 2


# ---------------------------------------------------------- regimes_exist


def test_regimes_exist_from_sweep_table_says_no_when_one_state_wins() -> None:
    """The shared arithmetic, exercised on a table where a single Gaussian beats
    every multi-regime candidate on both criteria -- the honest 1971-12 result."""
    table = pd.DataFrame(
        [
            {
                "states": 1,
                "held_out_log_likelihood_per_month": -1.0,
                "bayesian_information_criterion": 100.0,
            },
            {
                "states": 2,
                "held_out_log_likelihood_per_month": -1.5,
                "bayesian_information_criterion": 150.0,
            },
        ]
    )
    regimes_exist, evidence = regimes_exist_from_sweep_table(table)
    assert regimes_exist is False
    assert "held-out log likelihood" in evidence
    assert "information criterion" in evidence


def test_regimes_exist_from_sweep_table_does_not_crash_when_no_single_state_row_exists() -> None:
    """`hidden_state_counts_to_search` has no code-enforced guarantee that ``1`` is
    included -- it is "in the list deliberately" only by the shipped default, and
    a caller (a notebook, a future test, an exploratory `RunSettings` override
    that drops it to speed up a sweep) can pass a table with no single-state row.

    The two pre-existing, hand-written siblings this function is supposed to
    unify -- `StateCountSweep.more_than_one_state_is_preferred_on_the_holdout`
    and `..._on_the_criterion` -- both guard this with `if single is None: return
    False`. `regimes_exist_from_sweep_table` guards the boolean the same way, but
    the ``evidence`` sentence below it unconditionally indexes into the (possibly
    empty) single-state row, so this crashes with a raw pandas ``IndexError``
    instead of the informative message CLAUDE.md requires of every failure path
    ("a failed gate raises with a message saying what to do next").
    """
    table = pd.DataFrame(
        [
            {
                "states": 2,
                "held_out_log_likelihood_per_month": -1.0,
                "bayesian_information_criterion": 100.0,
            },
            {
                "states": 3,
                "held_out_log_likelihood_per_month": -1.5,
                "bayesian_information_criterion": 150.0,
            },
        ]
    )
    try:
        regimes_exist_from_sweep_table(table)
    except IndexError as error:
        pytest.fail(
            "regimes_exist_from_sweep_table crashed with an uncontrolled IndexError instead "
            f"of a message saying what to do next: {error}"
        )
