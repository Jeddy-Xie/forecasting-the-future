"""Choose how many regimes there are without looking past the first forecast date.

`forecast fit-regimes` sweeps the state count on the panel as it stands *today*
and writes the winner to `selected_model.json`. Reading that integer back into a
walk-forward means a forecast issued in 1972 was produced by a model whose shape
was chosen with data through 2026. It is one integer, but it is the whole sample
compressed into one integer, and it is look-ahead.

This module answers the same question honestly: sweep once, on the panel as it
stood at the first forecast date, and use that answer for the whole run.

**Why once, and not at every refit.** Selecting at every refit costs fifty-five
sweeps rather than one, and the measured behaviour is that the winner flips
between adjacent counts for reasons that are not economic. A model whose number
of regimes changes every year is not tracking the economy, it is tracking the
sampling noise in a holdout comparison. Once, at the start, on a window that ends
before the first forecast, is the shape the debt entry argued for.

**Why this lives in `backtest/` and not in `models/`.** Selecting on a burn-in
window needs a point-in-time panel, which is `data`, and the declared layering
forbids `models` importing `data`. `backtest` may import both. The arithmetic
that decides whether regimes exist at all stays in `models.state_selection`,
where the full-sample path already reads it, so both paths ask that question with
one implementation.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import pandas as pd

from economic_regime_forecasting.configuration.registry import EconomicSeriesRegistry
from economic_regime_forecasting.configuration.run_settings import ARTIFACTS, RunSettings
from economic_regime_forecasting.data.cache import ArtifactStore, SeriesCache
from economic_regime_forecasting.data.panel import assemble_point_in_time_panel
from economic_regime_forecasting.features.observation_matrix import build_observation_matrix
from economic_regime_forecasting.models.state_selection import (
    StateSelectionError,
    sweep_state_counts,
)
from economic_regime_forecasting.models.two_timescale_hidden_markov_model import TwoChainStateCount
from economic_regime_forecasting.models.two_timescale_state_selection import (
    sweep_state_counts_for_two_chains,
)

logger = logging.getLogger(__name__)


class BurnInSelectionError(RuntimeError):
    """The burn-in state-count choice could not be made, or would not be honest."""


@dataclass(frozen=True)
class BurnInStateCountChoice:
    """The number of regimes, chosen on the panel that ended before the run began."""

    state_count: int
    runner_up_state_count: int | None
    chosen_as_of: date
    panel_start: date
    panel_end: date
    months_in_burn_in_panel: int
    reason: str
    sweep_rows: tuple[dict[str, object], ...]
    growth_chain_sweep_rows: tuple[dict[str, object], ...] = ()
    """Research arm A4 only: the growth chain's own sweep. With two chains
    ``state_count`` is a ``TwoChainStateCount`` and ``sweep_rows`` is the joint
    table, one row per pair of chain counts, which is what the regimes-exist gate
    reads. Empty for one chain, and then absent from the manifest."""

    levels_chain_sweep_rows: tuple[dict[str, object], ...] = ()
    """Research arm A4 only: the inflation-and-rates chain's own sweep."""

    def as_manifest(self) -> dict[str, object]:
        """Everything a reader needs to see that the choice looked at no future."""
        manifest: dict[str, object] = {
            "state_count": int(self.state_count),
            "runner_up_state_count": self.runner_up_state_count,
            "chosen_as_of": self.chosen_as_of.isoformat(),
            "panel_start": self.panel_start.isoformat(),
            "panel_end": self.panel_end.isoformat(),
            "months_in_burn_in_panel": self.months_in_burn_in_panel,
            "reason": self.reason,
            "sweep": [dict(row) for row in self.sweep_rows],
        }
        if isinstance(self.state_count, TwoChainStateCount):
            manifest["growth_chain_state_count"] = self.state_count.growth_chain_state_count
            manifest["levels_chain_state_count"] = self.state_count.levels_chain_state_count
            manifest["growth_chain_sweep"] = [dict(row) for row in self.growth_chain_sweep_rows]
            manifest["levels_chain_sweep"] = [dict(row) for row in self.levels_chain_sweep_rows]
        return manifest

    @classmethod
    def from_manifest(cls, payload: dict[str, object]) -> BurnInStateCountChoice:
        """Rebuild a choice read back from its cached artifact."""
        runner_up = payload["runner_up_state_count"]
        rows = payload["sweep"]
        growth_rows = payload.get("growth_chain_sweep", [])
        levels_rows = payload.get("levels_chain_sweep", [])
        if (
            not isinstance(rows, list)
            or not isinstance(growth_rows, list)
            or not isinstance(levels_rows, list)
        ):
            raise BurnInSelectionError(
                "the cached burn-in choice has no sweep rows, so the regimes-exist gate "
                "would have nothing honest to read. Delete the artifact and let "
                "`forecast backtest` recompute it."
            )
        state_count = int(str(payload["state_count"]))
        if "growth_chain_state_count" in payload:
            two_chains = TwoChainStateCount(
                int(str(payload["growth_chain_state_count"])),
                int(str(payload["levels_chain_state_count"])),
            )
            if int(two_chains) != state_count:
                raise BurnInSelectionError(
                    f"the cached burn-in choice says {state_count} regimes but its chains "
                    f"multiply to {two_chains.describe()}. Delete the artifact and let "
                    "`forecast backtest` recompute it."
                )
            state_count = two_chains
        return cls(
            state_count=state_count,
            runner_up_state_count=None if runner_up is None else int(str(runner_up)),
            chosen_as_of=date.fromisoformat(str(payload["chosen_as_of"])),
            panel_start=date.fromisoformat(str(payload["panel_start"])),
            panel_end=date.fromisoformat(str(payload["panel_end"])),
            months_in_burn_in_panel=int(str(payload["months_in_burn_in_panel"])),
            reason=str(payload["reason"]),
            sweep_rows=tuple(dict(row) for row in rows),
            growth_chain_sweep_rows=tuple(dict(row) for row in growth_rows),
            levels_chain_sweep_rows=tuple(dict(row) for row in levels_rows),
        )

    def sweep_table(self) -> pd.DataFrame:
        """The sweep as the verdict's regimes-exist gate wants to read it."""
        return pd.DataFrame(list(self.sweep_rows))

    def describe(self) -> str:
        return (
            f"{self.state_count} regimes chosen as of {self.chosen_as_of.isoformat()} on "
            f"{self.months_in_burn_in_panel} months of burn-in "
            f"({self.panel_start.isoformat()} .. {self.panel_end.isoformat()}), "
            f"runner-up {self.runner_up_state_count}. {self.reason}"
        )


def _cache_name(settings: RunSettings, first_forecast_date: date) -> str:
    """The same key discipline `fit_regime_model` already uses for fitted models.

    Everything that could change the answer is in the key: the date the panel was
    assembled as of, the seed, and the configuration digest that covers the swept
    range, the restarts, the iteration cap and the tolerance.
    """
    return (
        f"burn_in_state_count_choice_{first_forecast_date.isoformat()}"
        f"_seed{settings.random_seed}_{settings.configuration_hash()}.json"
    )


@dataclass(frozen=True)
class BacktestStateCount:
    """The count the backtest will fit, how it was decided, and the runner-up if there was one."""

    state_count: int
    runner_up_state_count: int | None
    description: str


def state_count_for_the_backtest(
    registry: EconomicSeriesRegistry,
    cache: SeriesCache,
    settings: RunSettings,
    first_forecast_date: date,
    artifacts: ArtifactStore,
    selected_model_state_count: Callable[[], int] | None = None,
) -> BacktestStateCount:
    """The number of regimes the backtest will fit, decided in ONE place.

    Every caller that runs the walk-forward asks this, so a configuration that chooses
    its count somewhere other than the sweep is honoured identically wherever it runs.
    Debt D15 is what happens otherwise: the look-ahead audit called the sweep directly,
    so an arm that fixed its count elsewhere was audited with main's count and never ran
    its own code. An audit that quietly tests a different model than the one under test
    is worse than no audit.

    With ``select_state_count_on_a_burn_in_window`` off the count comes from the
    full-sample sweep already written to ``selected_model.json``; the caller supplies
    that reader, because reading a fitted artifact belongs to whoever owns the artifact
    store. A caller that cannot read one -- the audit refits everything from scratch by
    design -- may omit it, and this refuses rather than guessing.
    """
    if not settings.select_state_count_on_a_burn_in_window:
        if selected_model_state_count is None:
            raise StateSelectionError(
                "this configuration takes its state count from the full-sample sweep in "
                "selected_model.json, and this caller cannot read one. Pass "
                "selected_model_state_count, or set select_state_count_on_a_burn_in_window."
            )
        count = selected_model_state_count()
        return BacktestStateCount(
            state_count=count,
            runner_up_state_count=None,
            description=f"{count} regimes, read from the full-sample sweep in selected_model.json",
        )

    choice = choose_state_count_on_burn_in_window(
        registry, cache, settings, first_forecast_date=first_forecast_date, artifacts=artifacts
    )
    artifacts.write_json(ARTIFACTS.burn_in_state_count_choice, choice.as_manifest())
    return BacktestStateCount(
        state_count=choice.state_count,
        runner_up_state_count=choice.runner_up_state_count,
        description=choice.describe(),
    )


def choose_state_count_on_burn_in_window(
    registry: EconomicSeriesRegistry,
    cache: SeriesCache,
    settings: RunSettings,
    first_forecast_date: date,
    artifacts: ArtifactStore | None = None,
) -> BurnInStateCountChoice:
    """Sweep the state count on the panel as it stood at the first forecast date.

    The panel is assembled ``as_of`` that date, so the boundary assertion in
    ``data.vintage`` already guarantees its last observation is labelled strictly
    earlier. Selecting once, here, rather than at every refit is the shape D2
    argued for: refit-time selection costs 55 sweeps and flips between adjacent
    counts for reasons that are not economic.

    The choice, not the models, is cached: six fits cost around ninety seconds,
    and the key covers everything that could change the answer.
    """
    cache_name = _cache_name(settings, first_forecast_date)
    if artifacts is not None and artifacts.has(cache_name):
        return BurnInStateCountChoice.from_manifest(artifacts.read_json(cache_name))

    matrix = build_observation_matrix(
        assemble_point_in_time_panel(registry, first_forecast_date, cache), registry
    )
    panel_start = matrix.dates[0].date()
    panel_end = matrix.dates[-1].date()
    if not panel_end < first_forecast_date:
        raise BurnInSelectionError(
            f"the burn-in panel's last observation is labelled {panel_end.isoformat()}, which "
            f"is not strictly before the first forecast date {first_forecast_date.isoformat()}. "
            "A state count chosen on that window would have been chosen with knowledge of the "
            "month it is about to forecast. Check the vintage policy for this date rather than "
            "relaxing the comparison."
        )

    if settings.separate_chains_for_growth_and_for_inflation_with_rates:
        # Research arm A4: the same rule on each chain's own block, on the same
        # burn-in panel, so the boundary assertion above covers both.
        two_chains = sweep_state_counts_for_two_chains(
            matrix.values,
            settings.hidden_state_counts_to_search,
            seed=settings.random_seed,
            restarts=settings.expectation_maximisation_restarts,
            max_iterations=settings.expectation_maximisation_max_iterations,
            tolerance=settings.expectation_maximisation_tolerance,
        )
        choice = BurnInStateCountChoice(
            state_count=two_chains.recommended_state_count,
            runner_up_state_count=None,
            chosen_as_of=first_forecast_date,
            panel_start=panel_start,
            panel_end=panel_end,
            months_in_burn_in_panel=len(matrix),
            reason=two_chains.reason,
            sweep_rows=two_chains.joint_rows(),
            growth_chain_sweep_rows=tuple(
                item.as_row() for item in two_chains.growth_chain_sweep.evaluations
            ),
            levels_chain_sweep_rows=tuple(
                item.as_row() for item in two_chains.levels_chain_sweep.evaluations
            ),
        )
        logger.info("burn_in_state_count %s", choice.describe())
        if artifacts is not None:
            artifacts.write_json(cache_name, choice.as_manifest())
        return choice

    sweep = sweep_state_counts(
        matrix.values,
        settings.hidden_state_counts_to_search,
        seed=settings.random_seed,
        restarts=settings.expectation_maximisation_restarts,
        max_iterations=settings.expectation_maximisation_max_iterations,
        tolerance=settings.expectation_maximisation_tolerance,
    )

    choice = BurnInStateCountChoice(
        state_count=sweep.recommended_state_count,
        runner_up_state_count=sweep.runner_up_state_count,
        chosen_as_of=first_forecast_date,
        panel_start=panel_start,
        panel_end=panel_end,
        months_in_burn_in_panel=len(matrix),
        reason=sweep.reason,
        sweep_rows=tuple(item.as_row() for item in sweep.evaluations),
    )
    logger.info("burn_in_state_count %s", choice.describe())

    if artifacts is not None:
        artifacts.write_json(cache_name, choice.as_manifest())
    return choice
