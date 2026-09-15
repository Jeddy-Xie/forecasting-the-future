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
from dataclasses import dataclass
from datetime import date

import pandas as pd

from economic_regime_forecasting.configuration.registry import EconomicSeriesRegistry
from economic_regime_forecasting.configuration.run_settings import RunSettings
from economic_regime_forecasting.data.cache import ArtifactStore, SeriesCache
from economic_regime_forecasting.data.panel import assemble_point_in_time_panel
from economic_regime_forecasting.features.observation_matrix import (
    build_observation_matrix,
    observations_as_configured,
)
from economic_regime_forecasting.models.state_selection import sweep_state_counts
from economic_regime_forecasting.models.surprise_quadrants import (
    state_count_fixed_by_the_quadrant_structure,
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
    state_count_recommended_by_the_sweep: int | None = None
    """What the sweep recommended. Equal to ``state_count`` unless the
    configuration fixes the count (research arm A3), in which case the sweep is
    reported here and no longer chooses."""

    def as_manifest(self) -> dict[str, object]:
        """Everything a reader needs to see that the choice looked at no future."""
        return {
            "state_count": self.state_count,
            "runner_up_state_count": self.runner_up_state_count,
            "chosen_as_of": self.chosen_as_of.isoformat(),
            "panel_start": self.panel_start.isoformat(),
            "panel_end": self.panel_end.isoformat(),
            "months_in_burn_in_panel": self.months_in_burn_in_panel,
            "reason": self.reason,
            "sweep": [dict(row) for row in self.sweep_rows],
            "state_count_recommended_by_the_sweep": self.state_count_recommended_by_the_sweep,
        }

    @classmethod
    def from_manifest(cls, payload: dict[str, object]) -> BurnInStateCountChoice:
        """Rebuild a choice read back from its cached artifact."""
        runner_up = payload["runner_up_state_count"]
        recommended = payload.get("state_count_recommended_by_the_sweep")
        rows = payload["sweep"]
        if not isinstance(rows, list):
            raise BurnInSelectionError(
                "the cached burn-in choice has no sweep rows, so the regimes-exist gate "
                "would have nothing honest to read. Delete the artifact and let "
                "`forecast backtest` recompute it."
            )
        return cls(
            state_count=int(str(payload["state_count"])),
            runner_up_state_count=None if runner_up is None else int(str(runner_up)),
            chosen_as_of=date.fromisoformat(str(payload["chosen_as_of"])),
            panel_start=date.fromisoformat(str(payload["panel_start"])),
            panel_end=date.fromisoformat(str(payload["panel_end"])),
            months_in_burn_in_panel=int(str(payload["months_in_burn_in_panel"])),
            reason=str(payload["reason"]),
            sweep_rows=tuple(dict(row) for row in rows),
            state_count_recommended_by_the_sweep=(
                None if recommended is None else int(str(recommended))
            ),
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
    # Research arm A3 replaces growth and inflation with their surprises. That
    # step only drops months from the start, so the boundary checked above holds
    # for the matrix the sweep reads; the start and the length are re-read.
    matrix = observations_as_configured(matrix, settings)
    panel_start = matrix.dates[0].date()

    sweep = sweep_state_counts(
        matrix.values,
        settings.hidden_state_counts_to_search,
        seed=settings.random_seed,
        restarts=settings.expectation_maximisation_restarts,
        max_iterations=settings.expectation_maximisation_max_iterations,
        tolerance=settings.expectation_maximisation_tolerance,
    )

    fixed_state_count = state_count_fixed_by_the_quadrant_structure(settings)
    if fixed_state_count is None:
        state_count, reason = sweep.recommended_state_count, sweep.reason
    else:
        state_count = fixed_state_count
        reason = (
            f"{fixed_state_count} states, fixed by the surprise quadrant structure (research "
            f"arm A3); the sweep no longer chooses, and recommended "
            f"{sweep.recommended_state_count}: {sweep.reason}"
        )
    choice = BurnInStateCountChoice(
        state_count=state_count,
        runner_up_state_count=sweep.runner_up_state_count,
        chosen_as_of=first_forecast_date,
        panel_start=panel_start,
        panel_end=panel_end,
        months_in_burn_in_panel=len(matrix),
        reason=reason,
        sweep_rows=tuple(item.as_row() for item in sweep.evaluations),
        state_count_recommended_by_the_sweep=sweep.recommended_state_count,
    )
    logger.info("burn_in_state_count %s", choice.describe())

    if artifacts is not None:
        artifacts.write_json(cache_name, choice.as_manifest())
    return choice
