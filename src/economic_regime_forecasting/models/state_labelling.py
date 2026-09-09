"""Give the model's states a fixed order and a plain-English name.

Hidden Markov state labels are arbitrary. Nothing in the algorithm distinguishes
"state 0" from "state 1"; the labels fall out of wherever the fit happened to
start. Two consequences follow, and the second is the dangerous one.

The harmless consequence is that a printed transition matrix is meaningless until
someone reads the emission means. The dangerous one is that a walk-forward
backtest refits the model many times, and state 0 in 1985 need not be the same
regime as state 0 in 1986. Conditional base rates accumulated across refits would
then average unrelated regimes together and produce numbers that look fine and
mean nothing.

Canonicalisation fixes the order by a rule that depends only on the fitted
parameters: states are sorted by their growth emission mean, ascending, with ties
broken by inflation and then by interest rates. State zero is always the weakest
growth environment the model found.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from economic_regime_forecasting.features.observation_matrix import COLUMN_NAMES
from economic_regime_forecasting.models.gaussian_hidden_markov_model import (
    GaussianHiddenMarkovModel,
)

STANDARD_DEVIATION_CUT = 0.5
"""Where a standardised emission mean stops being ordinary and becomes notable.

Observations are expanding-window z-scores, so half a standard deviation from the
running mean is the point at which a regime is describably different from the
typical conditions of its own era rather than of ours."""


SHORT_WORDS: dict[str, tuple[str, str, str]] = {
    "growth": ("contracting", "steady", "strong"),
    "inflation": ("low inflation", "moderate inflation", "high inflation"),
    "rates": ("low rates", "neutral rates", "high rates"),
}
"""Three words per dimension, below the cut, between the cuts, and above it.

The long form reads well in a sentence and badly on a chart, where a five-item
legend of thirty-character strings forces the reader to look away from the data
for every band. The compact form is what charts label directly."""


@dataclass(frozen=True)
class RegimeDescription:
    """One state, named and quantified, for the report and the diagnostics."""

    state: int
    label: str
    standardised_means: tuple[float, ...]
    natural_means: tuple[float, ...]
    population_share: float
    expected_duration_in_months: float

    @property
    def compact_label(self) -> str:
        """A short name a chart can print beside the data instead of in a legend."""
        parts = []
        for name, mean in zip(COLUMN_NAMES, self.standardised_means, strict=True):
            low, middle, high = SHORT_WORDS[name]
            parts.append(
                low
                if mean < -STANDARD_DEVIATION_CUT
                else high
                if mean > STANDARD_DEVIATION_CUT
                else middle
            )
        return ", ".join(parts)

    def as_row(self) -> dict[str, object]:
        row: dict[str, object] = {
            "state": self.state,
            "regime": self.label,
            "short_regime": self.compact_label,
        }
        for name, standardised, natural in zip(
            COLUMN_NAMES, self.standardised_means, self.natural_means, strict=True
        ):
            row[f"{name}_standardised"] = standardised
            row[f"{name}_natural"] = natural
        row["population_share"] = self.population_share
        row["expected_duration_months"] = self.expected_duration_in_months
        return row


def canonical_order(model: GaussianHiddenMarkovModel) -> np.ndarray:
    """The permutation that puts states in canonical order.

    Sorting on growth first, then inflation, then rates, using a lexicographic
    sort whose last key is the primary one.
    """
    means = model.means
    keys = [means[:, dimension] for dimension in reversed(range(means.shape[1]))]
    return np.lexsort(tuple(keys))


def canonicalise(model: GaussianHiddenMarkovModel) -> GaussianHiddenMarkovModel:
    """Return the same model with its states in canonical order.

    Every parameter is permuted together. The transition matrix needs both its
    rows and its columns reordered, which is the step easiest to get half right.
    """
    order = canonical_order(model)
    return GaussianHiddenMarkovModel(
        initial_distribution=model.initial_distribution[order],
        transition_matrix=model.transition_matrix[np.ix_(order, order)],
        means=model.means[order],
        covariances=model.covariances[order],
        covariance_type=model.covariance_type,
        fit_report=model.fit_report,
    )


def permute_state_probabilities(state_probabilities: np.ndarray, order: np.ndarray) -> np.ndarray:
    """Reorder a state distribution, or a series of them, to match a permutation."""
    array = np.asarray(state_probabilities, dtype="float64")
    if array.ndim == 1:
        reordered_vector: np.ndarray = array[order]
        return reordered_vector
    reordered_series: np.ndarray = array[:, order]
    return reordered_series


def _describe_dimension(name: str, standardised_mean: float) -> str:
    if name == "growth":
        if standardised_mean < -STANDARD_DEVIATION_CUT:
            return "contracting growth"
        if standardised_mean > STANDARD_DEVIATION_CUT:
            return "strong growth"
        return "steady growth"
    if name == "inflation":
        if standardised_mean < -STANDARD_DEVIATION_CUT:
            return "low inflation"
        if standardised_mean > STANDARD_DEVIATION_CUT:
            return "high inflation"
        return "moderate inflation"
    if standardised_mean < -STANDARD_DEVIATION_CUT:
        return "low rates"
    if standardised_mean > STANDARD_DEVIATION_CUT:
        return "high rates"
    return "neutral rates"


def label_for(standardised_means: np.ndarray) -> str:
    """A readable name for a state, from the sign and size of its emission means."""
    parts = [
        _describe_dimension(name, float(mean))
        for name, mean in zip(COLUMN_NAMES, standardised_means, strict=True)
    ]
    return ", ".join(parts)


def describe_regimes(
    model: GaussianHiddenMarkovModel,
    standardised_observations: np.ndarray,
    natural_observations: np.ndarray,
) -> list[RegimeDescription]:
    """Name every state and attach the numbers a reader needs to judge it.

    Population share and the natural-unit means both come from the smoothed state
    responsibilities, which is correct here: this is a description of the sample
    the model was fitted to, not a forecast, so conditioning on the whole sample
    is what the question asks for.
    """
    responsibilities = model.smoothed_state_probabilities(standardised_observations)
    totals = responsibilities.sum(axis=0)
    population = totals / totals.sum()
    natural = np.asarray(natural_observations, dtype="float64")
    durations = model.expected_state_durations()

    descriptions: list[RegimeDescription] = []
    for state in range(model.state_count):
        weights = responsibilities[:, state]
        weight_total = max(float(weights.sum()), 1e-12)
        natural_mean = (weights[:, None] * natural).sum(axis=0) / weight_total
        descriptions.append(
            RegimeDescription(
                state=state,
                label=label_for(model.means[state]),
                standardised_means=tuple(float(value) for value in model.means[state]),
                natural_means=tuple(float(value) for value in natural_mean),
                population_share=float(population[state]),
                expected_duration_in_months=float(durations[state]),
            )
        )
    return descriptions


def regime_table(descriptions: list[RegimeDescription]) -> pd.DataFrame:
    return pd.DataFrame([item.as_row() for item in descriptions])
