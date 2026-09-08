"""From a regime forecast to an indicator probability.

Two steps. First, learn from history how often each indicator's condition holds
in each regime. Second, combine those rates with the projected regime
distribution to get a probability at a horizon.

The second step is where the two composition paths differ, and the difference is
not cosmetic.

A **point-in-time** question asks about the single month at the horizon. Its
answer is the projected regime distribution dotted with the per-regime rate.

An **any-time-within-horizon** question asks whether the condition ever holds
between now and then. Its answer must integrate over the whole regime path.
Composing it point-in-time would answer a different and much easier question, and
would understate the probability by a wide margin at long horizons: the chance of
a recession *in the single month* sixty months from now is around thirty percent,
while the chance of one *at some point* in those sixty months is closer to ninety.

Modelling the path
------------------
The path integral is done by tracking the probability that the condition has
still not occurred. Write ``e_k`` for the chance the condition starts holding in a
month whose regime is k, given it did not hold the month before, and ``p_k`` for
the chance it continues holding given it did. Then the probability of surviving a
month without an occurrence, having already survived, is one minus ``e``, and the
survival transfer matrix is the transition matrix with each column scaled by that.
Chaining it over the horizon gives the exact answer under one assumption: that
whether the condition holds depends on last month's condition and this month's
regime, and on nothing else.

That assumption is worth stating plainly because the obvious simpler version is
worse. Treating each month as an independent draw at the per-regime occupancy rate
ignores that these conditions are sticky -- unemployment above seven percent this
month makes it very likely next month -- and so it counts one long episode as many
independent chances. It overstates every any-time probability, systematically.
Carrying the one extra parameter per regime removes most of that.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from economic_regime_forecasting.configuration.registry import BinaryIndicator, Composition
from economic_regime_forecasting.models.gaussian_hidden_markov_model import (
    GaussianHiddenMarkovModel,
)


class ForecastCompositionError(ValueError):
    """A forecast could not be composed from the inputs given."""


@dataclass(frozen=True)
class ConditionalRates:
    """How often an indicator's condition holds, per regime, with its evidence.

    Three rates per regime, all shrunk toward their pooled value by a Beta prior,
    because a regime holding forty months of history cannot support an unshrunk
    frequency. The effective sample size behind each is carried alongside so that
    a reader can see which numbers rest on evidence and which rest on the prior.
    """

    indicator_name: str
    occupancy_rate: np.ndarray
    """P(condition holds this month | regime). Used by point-in-time questions."""

    entry_hazard: np.ndarray
    """P(condition starts holding | it did not hold last month, regime)."""

    persistence: np.ndarray
    """P(condition keeps holding | it held last month, regime)."""

    occupancy_sample_size: np.ndarray
    entry_sample_size: np.ndarray
    persistence_sample_size: np.ndarray

    pooled_occupancy_rate: float
    pooled_entry_hazard: float
    pooled_persistence: float

    shrinkage_strength: float
    months_used: int

    @property
    def state_count(self) -> int:
        return int(self.occupancy_rate.size)

    def to_dictionary(self) -> dict[str, Any]:
        return {
            "indicator_name": self.indicator_name,
            "occupancy_rate": self.occupancy_rate.tolist(),
            "entry_hazard": self.entry_hazard.tolist(),
            "persistence": self.persistence.tolist(),
            "occupancy_sample_size": self.occupancy_sample_size.tolist(),
            "entry_sample_size": self.entry_sample_size.tolist(),
            "persistence_sample_size": self.persistence_sample_size.tolist(),
            "pooled_occupancy_rate": self.pooled_occupancy_rate,
            "pooled_entry_hazard": self.pooled_entry_hazard,
            "pooled_persistence": self.pooled_persistence,
            "shrinkage_strength": self.shrinkage_strength,
            "months_used": self.months_used,
        }


def _shrink(
    weighted_successes: np.ndarray,
    weighted_totals: np.ndarray,
    pooled_rate: float,
    shrinkage_strength: float,
) -> np.ndarray:
    """Pull each per-regime rate toward the pooled rate by a Beta prior.

    A regime with a thousand months behind it barely moves; a regime with five
    months lands almost on the pooled rate, which is the honest answer when there
    is nothing else to go on.
    """
    denominator = weighted_totals + shrinkage_strength
    # A zero denominator needs both no prior weight and a regime with no months
    # behind it. The pooled rate is then the only information there is, and
    # answering with it is a decision rather than a not-a-number that travels.
    shrunk: np.ndarray = np.where(
        denominator > 0.0,
        (weighted_successes + shrinkage_strength * pooled_rate)
        / np.where(denominator > 0.0, denominator, 1.0),
        pooled_rate,
    )
    return shrunk


def estimate_conditional_rates(
    indicator: BinaryIndicator,
    monthly_condition: np.ndarray,
    state_probabilities: np.ndarray,
    shrinkage_strength: float,
) -> ConditionalRates:
    """Learn the three per-regime rates from aligned history.

    ``monthly_condition`` and ``state_probabilities`` must cover the same months,
    in the same order, and must both be free of missing values. The state
    probabilities are the filtered ones, so nothing here reads the future.

    Weighting by the filtered probabilities rather than by a hard state assignment
    uses every month's partial evidence. A month the model is sixty-forty unsure
    about contributes to both regimes in proportion, which is both more accurate
    and better behaved when a regime is rare.
    """
    condition = np.asarray(monthly_condition, dtype="float64")
    weights = np.atleast_2d(np.asarray(state_probabilities, dtype="float64"))
    if condition.shape[0] != weights.shape[0]:
        raise ForecastCompositionError(
            f"indicator {indicator.name!r} has {condition.shape[0]} months of condition data "
            f"against {weights.shape[0]} months of state probabilities. Align them before "
            "estimating rates."
        )
    if condition.size == 0:
        raise ForecastCompositionError(
            f"indicator {indicator.name!r} has no months to estimate rates from"
        )
    if not np.isfinite(condition).all():
        raise ForecastCompositionError(
            f"indicator {indicator.name!r} has unresolved months in its condition series; drop "
            "them before estimating rates rather than treating them as zeroes"
        )

    occupancy_totals = weights.sum(axis=0)
    occupancy_successes = weights.T @ condition
    pooled_occupancy = float(condition.mean())

    # Transitions need a previous month, so the first month is dropped from both.
    previous = condition[:-1]
    current = condition[1:]
    transition_weights = weights[1:]

    did_not_hold = previous < 0.5
    held = ~did_not_hold

    entry_totals = transition_weights[did_not_hold].sum(axis=0)
    entry_successes = transition_weights[did_not_hold].T @ current[did_not_hold]
    pooled_entry = float(current[did_not_hold].mean()) if did_not_hold.any() else 0.0

    persistence_totals = transition_weights[held].sum(axis=0)
    persistence_successes = transition_weights[held].T @ current[held]
    pooled_persistence = float(current[held].mean()) if held.any() else pooled_occupancy

    return ConditionalRates(
        indicator_name=indicator.name,
        occupancy_rate=_shrink(
            occupancy_successes, occupancy_totals, pooled_occupancy, shrinkage_strength
        ),
        entry_hazard=_shrink(entry_successes, entry_totals, pooled_entry, shrinkage_strength),
        persistence=_shrink(
            persistence_successes, persistence_totals, pooled_persistence, shrinkage_strength
        ),
        occupancy_sample_size=occupancy_totals,
        entry_sample_size=entry_totals,
        persistence_sample_size=persistence_totals,
        pooled_occupancy_rate=pooled_occupancy,
        pooled_entry_hazard=pooled_entry,
        pooled_persistence=pooled_persistence,
        shrinkage_strength=shrinkage_strength,
        months_used=int(condition.size),
    )


@dataclass(frozen=True)
class IndicatorForecast:
    """One probability, with everything a reader needs to judge how much it rests on."""

    indicator_name: str
    horizon_in_months: int
    probability: float
    composition: Composition
    effective_sample_size: float
    """Months of history behind this particular forecast, weighted by how much
    each regime contributes to it."""

    distance_to_stationary: float
    """How far the projected regime distribution is from the model's long-run
    distribution. Near zero means this forecast is the unconditional base rate
    wearing a model's clothes."""

    projected_state_distribution: tuple[float, ...]

    def as_row(self) -> dict[str, object]:
        return {
            "indicator": self.indicator_name,
            "horizon_months": self.horizon_in_months,
            "probability": self.probability,
            "composition": self.composition.value,
            "effective_sample_size": self.effective_sample_size,
            "distance_to_stationary": self.distance_to_stationary,
        }


def compose_point_in_time(projected_distribution: np.ndarray, rates: ConditionalRates) -> float:
    """The projected regime distribution dotted with the per-regime rate."""
    return float(np.dot(projected_distribution, rates.occupancy_rate))


def compose_any_time_within_horizon(
    model: GaussianHiddenMarkovModel,
    current_distribution: np.ndarray,
    rates: ConditionalRates,
    horizon_in_months: int,
    condition_holds_now: bool,
) -> float:
    """Probability the condition holds in at least one month of the horizon window.

    Computed as one minus the probability of surviving the whole window without
    it. The first month is special because whether the condition holds now decides
    which rate applies to it; every later month is reached only along paths where
    the condition did not hold, so the entry hazard applies throughout.
    """
    if horizon_in_months < 1:
        raise ForecastCompositionError(
            f"an any-time question needs a horizon of at least one month, got {horizon_in_months}"
        )
    transitions = model.transition_matrix
    first_month_hazard = rates.persistence if condition_holds_now else rates.entry_hazard

    surviving = np.asarray(current_distribution, dtype="float64") @ (
        transitions * (1.0 - first_month_hazard)[None, :]
    )
    if horizon_in_months > 1:
        later_transfer = transitions * (1.0 - rates.entry_hazard)[None, :]
        surviving = surviving @ np.linalg.matrix_power(later_transfer, horizon_in_months - 1)

    probability_of_never = float(surviving.sum())
    return float(np.clip(1.0 - probability_of_never, 0.0, 1.0))


def forecast_indicator(
    indicator: BinaryIndicator,
    model: GaussianHiddenMarkovModel,
    filtered_distribution: np.ndarray,
    rates: ConditionalRates,
    horizon_in_months: int,
    condition_holds_now: bool,
) -> IndicatorForecast:
    """Produce one probability by the composition path the registry declares."""
    projected = model.project_state_distribution(filtered_distribution, horizon_in_months)
    stationary = model.stationary_distribution()

    if indicator.composition is Composition.POINT_IN_TIME:
        probability = compose_point_in_time(projected, rates)
        weights = projected
    else:
        probability = compose_any_time_within_horizon(
            model, filtered_distribution, rates, horizon_in_months, condition_holds_now
        )
        # An any-time question draws on the regimes the path passes through, which
        # for a persistent chain is dominated by where it starts and where it ends.
        weights = 0.5 * (np.asarray(filtered_distribution, dtype="float64") + projected)

    effective_sample_size = float(np.dot(weights, rates.occupancy_sample_size))
    distance = float(0.5 * np.abs(projected - stationary).sum())

    if not 0.0 <= probability <= 1.0:  # pragma: no cover - both paths clip already
        raise ForecastCompositionError(
            f"{indicator.name} at {horizon_in_months} months produced {probability}, which is "
            "not a probability"
        )

    return IndicatorForecast(
        indicator_name=indicator.name,
        horizon_in_months=horizon_in_months,
        probability=probability,
        composition=indicator.composition,
        effective_sample_size=effective_sample_size,
        distance_to_stationary=distance,
        projected_state_distribution=tuple(float(value) for value in projected),
    )
