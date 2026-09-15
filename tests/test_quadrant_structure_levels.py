"""Research arm A2-quadrant-structure-levels: the state count fixed at four,
seeded from All Weather's growth-by-inflation quadrant centroids.

The seeding arithmetic itself is pinned in `test_gaussian_hidden_markov_model.py`,
next to the furthest-point rule it replaces. This file pins the wiring: the new
`RunSettings` field changes the configuration hash, `walk_forward.fit_regime_model`
only turns quadrant seeding on when the flag is set and the state count is really
four, and the two command-line stages the pre-registration names --
`_state_count_for_the_backtest` and `fit_regimes` -- fix K at four while still
running and reporting whichever sweep they would otherwise have read.

Offline throughout, following the idiom `tests/test_burn_in_state_count_choice.py`
and `tests/test_walk_forward_backtest.py` already use: a small registry
(`conftest.three_dimension_registry`) and a cache filled with generated data.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from datetime import date

import numpy as np
import pandas as pd
import pytest

from economic_regime_forecasting.backtest import schedule as schedule_module
from economic_regime_forecasting.backtest import walk_forward
from economic_regime_forecasting.command_line_interface import (
    QUADRANT_STRUCTURE_STATE_COUNT,
    Workspace,
    _state_count_for_the_backtest,
    fit_regimes,
)
from economic_regime_forecasting.configuration.registry import EconomicSeriesRegistry
from economic_regime_forecasting.configuration.run_settings import (
    ARTIFACTS,
    CacheLayout,
    RunSettings,
)
from economic_regime_forecasting.data.cache import ArtifactStore, SeriesCache, SeriesSnapshot
from economic_regime_forecasting.models import gaussian_hidden_markov_model as hidden_markov
from economic_regime_forecasting.models.gaussian_hidden_markov_model import (
    GaussianHiddenMarkovModel,
)

MONTHS = 400
START = "1950-01-01"
FIELD = "fix_state_count_at_four_with_quadrant_structured_seeding"


# ------------------------------------------------------------ RunSettings


def test_the_field_defaults_to_this_arms_behaviour() -> None:
    assert RunSettings().fix_state_count_at_four_with_quadrant_structured_seeding is True


def test_toggling_the_field_changes_the_configuration_hash_when_other_settings_hold_it_fixed() -> (
    None
):
    """Holding every other field at a value that is already in the digest either
    way (not this field's own omitted value), flipping this one must still move
    the hash -- the omission only fires when the field is at `False`."""
    on = dataclasses.replace(
        RunSettings(), fix_state_count_at_four_with_quadrant_structured_seeding=True
    )
    off = dataclasses.replace(
        RunSettings(), fix_state_count_at_four_with_quadrant_structured_seeding=False
    )
    assert on.configuration_hash() != off.configuration_hash()


def test_the_field_is_in_the_hash_omission_map_at_false() -> None:
    """`False` is what this field's *absence* would have meant before it existed
    (every forecasting fit's state count came from a sweep, not a fixed four), so
    it belongs in the omission map at `False` for the same reason the two older
    switches are there: a configuration built before this field existed --
    `submission/manifest.json`, the cached models under `.cache/models/`, the
    registered forecasts -- must keep the digest it already has, and the field's
    dataclass default on this branch is `True`, not `False`, so without the
    omission entry its mere existence would move every one of those digests."""
    from economic_regime_forecasting.configuration.run_settings import (
        SETTINGS_OMITTED_FROM_THE_HASH_WHEN_THEY_HOLD_THE_SHIPPED_VALUE,
    )

    assert SETTINGS_OMITTED_FROM_THE_HASH_WHEN_THEY_HOLD_THE_SHIPPED_VALUE[FIELD] is False


def test_the_field_at_false_hashes_identically_to_a_configuration_missing_it_entirely() -> None:
    """The omission rule itself, pinned for this field the same way
    `test_configuration_hash_compatibility.py` pins it for the other two."""
    import hashlib
    import json

    held_at_false = dataclasses.replace(
        RunSettings(), fix_state_count_at_four_with_quadrant_structured_seeding=False
    )
    payload_missing_the_field = {
        name: list(value) if isinstance(value, tuple) else value
        for name, value in held_at_false.__dict__.items()
        if name not in ("cache", FIELD)
    }
    encoded = json.dumps(payload_missing_the_field, sort_keys=True, separators=(",", ":"))
    expected = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
    assert held_at_false.configuration_hash() == expected


# ------------------------------------------------ walk_forward.fit_regime_model wiring


@pytest.fixture
def filled_cache(
    cache: SeriesCache,
    three_dimension_registry: EconomicSeriesRegistry,
    snapshot_factory: Callable[..., SeriesSnapshot],
) -> SeriesCache:
    """Thirty-plus years of data, with honest vintages at every month.

    Growth and inflation are driven by two *independent* two-state chains
    (rather than the single shared chain `tests/test_burn_in_state_count_choice.py`
    uses), so all four growth/inflation quadrants actually get months -- a single
    shared chain makes the standardised growth and inflation columns nearly exact
    mirror images of each other, which empties two of the four quadrants and is
    not what these wiring tests are about.
    """
    index = pd.date_range(START, periods=MONTHS, freq="MS", name="observation_date")
    generator = np.random.default_rng(20260911)
    transitions = np.array([[0.97, 0.03], [0.05, 0.95]])
    growth_state, inflation_state = 0, 1
    output, prices, rate = [100.0], [100.0], []
    for _ in range(MONTHS):
        growth_state = int(generator.choice(2, p=transitions[growth_state]))
        inflation_state = int(generator.choice(2, p=transitions[inflation_state]))
        output.append(
            output[-1]
            * (1.0 + (0.004 if growth_state == 0 else -0.002) + float(generator.normal(0, 0.001)))
        )
        prices.append(
            prices[-1]
            * (1.0 + (0.002 if inflation_state == 0 else 0.006) + float(generator.normal(0, 0.001)))
        )
        rate.append((4.5 if inflation_state == 0 else 0.6) + float(generator.normal(0, 0.2)))

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
        fix_state_count_at_four_with_quadrant_structured_seeding=True,
        cache=CacheLayout(tmp_path / "cache"),
    )


def test_fit_regime_model_seeds_by_quadrant_when_the_flag_is_on_and_k_is_four(
    monkeypatch: pytest.MonkeyPatch,
    three_dimension_registry: EconomicSeriesRegistry,
    filled_cache: SeriesCache,
    settings: RunSettings,
) -> None:
    captured: dict[str, object] = {}
    real_fit = hidden_markov.fit

    def _spy_fit(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured["seed_means_by_quadrant_structure"] = kwargs.get(
            "seed_means_by_quadrant_structure"
        )
        return real_fit(*args, **kwargs)

    monkeypatch.setattr(walk_forward.hidden_markov, "fit", _spy_fit)
    histories = walk_forward.prepare_indicator_history(
        (), three_dimension_registry, filled_cache, settings.forecast_horizons_in_months
    )
    walk_forward.fit_regime_model(
        date(1980, 1, 1), three_dimension_registry, filled_cache, histories, settings, 4
    )
    assert captured["seed_means_by_quadrant_structure"] is True


def test_fit_regime_model_does_not_seed_by_quadrant_when_the_state_count_is_not_four(
    monkeypatch: pytest.MonkeyPatch,
    three_dimension_registry: EconomicSeriesRegistry,
    filled_cache: SeriesCache,
    settings: RunSettings,
) -> None:
    """Defensive: the pre-registration fixes K at four everywhere the flag is on,
    but `fit_regime_model` takes `state_count` as its own argument, so a future
    caller that passed something else must not get quadrant-seeded means for a
    count the seeding function does not support."""
    captured: dict[str, object] = {}
    real_fit = hidden_markov.fit

    def _spy_fit(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured["seed_means_by_quadrant_structure"] = kwargs.get(
            "seed_means_by_quadrant_structure"
        )
        return real_fit(*args, **kwargs)

    monkeypatch.setattr(walk_forward.hidden_markov, "fit", _spy_fit)
    histories = walk_forward.prepare_indicator_history(
        (), three_dimension_registry, filled_cache, settings.forecast_horizons_in_months
    )
    walk_forward.fit_regime_model(
        date(1980, 1, 1), three_dimension_registry, filled_cache, histories, settings, 2
    )
    assert captured["seed_means_by_quadrant_structure"] is False


def test_fit_regime_model_does_not_seed_by_quadrant_when_the_flag_is_off(
    monkeypatch: pytest.MonkeyPatch,
    three_dimension_registry: EconomicSeriesRegistry,
    filled_cache: SeriesCache,
    settings: RunSettings,
) -> None:
    off = dataclasses.replace(
        settings, fix_state_count_at_four_with_quadrant_structured_seeding=False
    )
    captured: dict[str, object] = {}
    real_fit = hidden_markov.fit

    def _spy_fit(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured["seed_means_by_quadrant_structure"] = kwargs.get(
            "seed_means_by_quadrant_structure"
        )
        return real_fit(*args, **kwargs)

    monkeypatch.setattr(walk_forward.hidden_markov, "fit", _spy_fit)
    histories = walk_forward.prepare_indicator_history(
        (), three_dimension_registry, filled_cache, off.forecast_horizons_in_months
    )
    walk_forward.fit_regime_model(
        date(1980, 1, 1), three_dimension_registry, filled_cache, histories, off, 4
    )
    assert captured["seed_means_by_quadrant_structure"] is False


# --------------------------------------------- command-line wiring: backtest


def test_the_backtest_state_count_is_fixed_at_four_regardless_of_the_burn_in_sweep(
    three_dimension_registry: EconomicSeriesRegistry,
    filled_cache: SeriesCache,
    settings: RunSettings,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    """`hidden_state_counts_to_search=(1, 2)` means the burn-in sweep can only
    ever recommend 1 or 2 -- never 4 -- so a returned state count of exactly
    `QUADRANT_STRUCTURE_STATE_COUNT` proves the sweep's own choice was
    overridden, not coincidentally matched."""
    workspace = Workspace(
        registry=three_dimension_registry,
        indicators=(),
        cache=filled_cache,
        artifacts=ArtifactStore(tmp_path / "artifacts"),
        settings=settings,
    )
    schedule = schedule_module.build_schedule(
        date(1975, 1, 1), date(1980, 1, 1), settings.refit_every_n_months
    )
    state_count = _state_count_for_the_backtest(workspace, schedule)
    assert state_count == QUADRANT_STRUCTURE_STATE_COUNT == 4

    # The burn-in sweep still ran and its own (overridden) choice is still on
    # record, because the regimes-exist gate still reads it.
    choice_payload = workspace.artifacts.read_json(ARTIFACTS.burn_in_state_count_choice)
    assert int(str(choice_payload["state_count"])) in (1, 2)


def test_turning_the_flag_off_reproduces_the_burn_in_sweeps_own_choice(
    three_dimension_registry: EconomicSeriesRegistry,
    filled_cache: SeriesCache,
    settings: RunSettings,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    off = dataclasses.replace(
        settings, fix_state_count_at_four_with_quadrant_structured_seeding=False
    )
    workspace = Workspace(
        registry=three_dimension_registry,
        indicators=(),
        cache=filled_cache,
        artifacts=ArtifactStore(tmp_path / "artifacts"),
        settings=off,
    )
    schedule = schedule_module.build_schedule(
        date(1975, 1, 1), date(1980, 1, 1), off.refit_every_n_months
    )
    state_count = _state_count_for_the_backtest(workspace, schedule)
    assert state_count in (1, 2)


# ------------------------------------------------- command-line wiring: gate 2


def test_fit_regimes_selects_a_quadrant_seeded_four_state_model(
    three_dimension_registry: EconomicSeriesRegistry,
    filled_cache: SeriesCache,
    settings: RunSettings,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    """`selected_model.json` is what `forecast_now` reads its state count from,
    so this is what makes today's fit use K = 4. The full-sample sweep table is
    still written underneath it, unchanged, for gate 2's own checks."""
    workspace = Workspace(
        registry=three_dimension_registry,
        indicators=(),
        cache=filled_cache,
        artifacts=ArtifactStore(tmp_path / "artifacts"),
        settings=settings,
    )
    exit_code, report = fit_regimes(workspace, date(1980, 1, 1))

    selected = GaussianHiddenMarkovModel.from_dictionary(
        workspace.artifacts.read_json(ARTIFACTS.selected_model)
    )
    assert selected.state_count == QUADRANT_STRUCTURE_STATE_COUNT == 4

    sweep_table = workspace.artifacts.read_table(ARTIFACTS.state_count_sweep)
    assert set(sweep_table["states"]) == {1, 2}
    assert exit_code in (0, 1)  # a pipeline sanity gate on synthetic data; not the point here


def test_turning_the_flag_off_reproduces_fit_regimes_previous_behaviour(
    three_dimension_registry: EconomicSeriesRegistry,
    filled_cache: SeriesCache,
    settings: RunSettings,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    from economic_regime_forecasting.models.state_selection import sweep_state_counts

    off = dataclasses.replace(
        settings, fix_state_count_at_four_with_quadrant_structured_seeding=False
    )
    workspace = Workspace(
        registry=three_dimension_registry,
        indicators=(),
        cache=filled_cache,
        artifacts=ArtifactStore(tmp_path / "artifacts"),
        settings=off,
    )
    fit_regimes(workspace, date(1980, 1, 1))

    selected = GaussianHiddenMarkovModel.from_dictionary(
        workspace.artifacts.read_json(ARTIFACTS.selected_model)
    )
    # Ground truth from the same sweep, computed independently of `fit_regimes`.
    matrix = workspace.observation_matrix_as_of(date(1980, 1, 1))
    sweep = sweep_state_counts(
        matrix.values,
        off.hidden_state_counts_to_search,
        seed=off.random_seed,
        restarts=off.expectation_maximisation_restarts,
        max_iterations=off.expectation_maximisation_max_iterations,
        tolerance=off.expectation_maximisation_tolerance,
    )
    assert selected.state_count == sweep.recommended_state_count
