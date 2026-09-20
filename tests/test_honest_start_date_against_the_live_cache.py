"""1994-03-01 is a measured answer, not a literal in the source.

The goal names 1994-03-01 as the honest start date, but `measured-facts.md` is
explicit that it must never be hardcoded: it is the expected value of a
computation against the real archive, asserted here so that if ALFRED ever
backfills earlier CPI vintages, this test is the one that notices and fails
loudly rather than the shipped default silently going stale.

This file is the one place the new code touches the project's own `.cache/` --
deliberately, per the Test plan, so the burn-in choice for both cells is computed
once (by whoever runs this test first) and read from disk by every run after,
the same file `forecast backtest` itself writes. It skips itself on a checkout
that has never run `forecast fetch-data`, so a fresh clone's suite still passes.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from economic_regime_forecasting import command_line_interface as interface
from economic_regime_forecasting.backtest.state_count_on_burn_in import (
    choose_state_count_on_burn_in_window,
)
from economic_regime_forecasting.backtest.walk_forward import find_first_fully_point_in_time_date
from economic_regime_forecasting.configuration.registry import load_registries
from economic_regime_forecasting.configuration.run_settings import ARTIFACTS, DEFAULT_RUN_SETTINGS
from economic_regime_forecasting.data.cache import ArtifactStore

pytestmark = [
    pytest.mark.skipif(
        not DEFAULT_RUN_SETTINGS.cache.vintage.exists(),
        reason="no .cache/vintage on this checkout; run `forecast fetch-data` first",
    ),
    pytest.mark.slow,
]

HONEST_START = date(1994, 3, 1)
SHIPPED_START = date(1971, 12, 1)
AS_OF = date(2026, 9, 1)


@pytest.fixture(scope="module")
def live_workspace() -> interface.Workspace:
    return interface.Workspace.open(DEFAULT_RUN_SETTINGS)


def test_the_finder_returns_the_measured_boundary_on_the_live_cache(
    live_workspace: interface.Workspace,
) -> None:
    """AC5. The one place 1994-03-01 is asserted against real data."""
    result = find_first_fully_point_in_time_date(
        live_workspace.registry,
        live_workspace.cache,
        DEFAULT_RUN_SETTINGS,
        earliest_candidate=SHIPPED_START,
        last_forecast_date=date(2026, 9, 1),
    )
    assert result == HONEST_START


def test_the_honest_start_is_pinned_through_backtest_schedule_itself(
    live_workspace: interface.Workspace,
) -> None:
    """AC16. Not only the finder in isolation: the real call path a run takes."""
    schedule = live_workspace.backtest_schedule(AS_OF)
    assert schedule.forecast_dates[0] == pd.Timestamp(HONEST_START)


def test_the_shipped_start_survives_with_the_switch_off(
    live_workspace: interface.Workspace,
) -> None:
    """AC16. `start_walk_forward_when_every_input_is_point_in_time=False` must
    still give the shipped answer through the exact same call path."""
    import dataclasses

    shipped_settings = dataclasses.replace(
        DEFAULT_RUN_SETTINGS, start_walk_forward_when_every_input_is_point_in_time=False
    )
    workspace = interface.Workspace.open(shipped_settings)
    schedule = workspace.backtest_schedule(AS_OF)
    assert schedule.forecast_dates[0] == pd.Timestamp(SHIPPED_START)


def test_the_widest_schedule_ignores_the_start_policy_under_both_settings(
    live_workspace: interface.Workspace,
) -> None:
    """AC16. `fetch-data` must never be starved by the honest start it is itself
    computing: `widest_backtest_schedule` always gives the shipped answer, with
    every one of the 658 forecast dates the shipped run holds."""
    import dataclasses

    honest_widest = live_workspace.widest_backtest_schedule(AS_OF)
    assert honest_widest.forecast_dates[0] == pd.Timestamp(SHIPPED_START)
    assert len(honest_widest.forecast_dates) == 658

    shipped_settings = dataclasses.replace(
        DEFAULT_RUN_SETTINGS, start_walk_forward_when_every_input_is_point_in_time=False
    )
    shipped_widest = interface.Workspace.open(shipped_settings).widest_backtest_schedule(AS_OF)
    assert shipped_widest.forecast_dates[0] == pd.Timestamp(SHIPPED_START)
    assert len(shipped_widest.forecast_dates) == 658


def test_the_burn_in_choice_reproduces_the_measured_sweep_at_1994_03(
    live_workspace: interface.Workspace,
) -> None:
    """AC6. Main's default is the `both` cell: 6 states, runner-up 2. On research arm
    A4's branch the default fits two chains, so main's configuration is named here:
    the separate-chains switch off, everything else the default."""
    import dataclasses

    main_settings = dataclasses.replace(
        DEFAULT_RUN_SETTINGS, separate_chains_for_growth_and_for_inflation_with_rates=False
    )
    choice = choose_state_count_on_burn_in_window(
        live_workspace.registry,
        live_workspace.cache,
        main_settings,
        first_forecast_date=HONEST_START,
        artifacts=ArtifactStore(main_settings.cache.models),
    )
    assert choice.state_count == 6
    assert choice.runner_up_state_count == 2
    assert choice.months_in_burn_in_panel == 518
    assert choice.panel_start == date(1950, 12, 1)
    assert choice.panel_end == date(1994, 1, 1)


def test_the_burn_in_choice_reproduces_the_measured_sweep_at_1971_12(
    live_workspace: interface.Workspace,
) -> None:
    """AC6. The shipped start with the state-count switch on: 2 states, runner-up
    3 -- the sweep that fails `regimes_exist` and is finding F2's mechanism."""
    import dataclasses

    settings = dataclasses.replace(
        DEFAULT_RUN_SETTINGS,
        start_walk_forward_when_every_input_is_point_in_time=False,
        separate_chains_for_growth_and_for_inflation_with_rates=False,
    )
    choice = choose_state_count_on_burn_in_window(
        live_workspace.registry,
        live_workspace.cache,
        settings,
        first_forecast_date=SHIPPED_START,
        artifacts=ArtifactStore(settings.cache.models),
    )
    assert choice.state_count == 2
    assert choice.runner_up_state_count == 3


def test_selected_model_json_is_still_available_for_the_shipped_cell() -> None:
    """The `compare-variants` shipped and honest_start cells read
    `selected_model.json` for their state count; a live checkout that has run
    `forecast fit-regimes` at least once must still have it."""
    registry, indicators = load_registries()
    artifacts = ArtifactStore(DEFAULT_RUN_SETTINGS.cache.models)
    if not artifacts.has(ARTIFACTS.selected_model):
        pytest.skip("selected_model.json not on this checkout; run `forecast fit-regimes` first")
    assert artifacts.read_json(ARTIFACTS.selected_model)
