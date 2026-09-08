"""Projecting a regime forward, and measuring when the projection stops meaning
anything.

Given the filtered distribution over states today and a transition matrix, the
distribution h months from now is the one multiplied by the other raised to the
h. That is the easy part. The part that decides whether this project has anything
to say at a ten-year horizon is what happens as h grows.

Every irreducible aperiodic Markov chain forgets where it started. The distance
between a projected distribution and the chain's long-run stationary distribution
decays geometrically, at a rate set by the second largest eigenvalue modulus of
the transition matrix. Once that distance is small, the projection has converged:
whatever the economy is doing today, the model's answer is the same, and that
answer is the unconditional base rate.

This is a property of the method, not a defect in it, and the only dishonest thing
to do is present a converged projection as a prediction. So the convergence is
measured, reported at every horizon, and compiled into a threshold: the
**information horizon** is the longest horizon at which a projection is still
distinguishable from the base rate. Beyond it, the project ships the base rate and
says so.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from economic_regime_forecasting.models.gaussian_hidden_markov_model import (
    GaussianHiddenMarkovModel,
)


def total_variation_distance(first: np.ndarray, second: np.ndarray) -> float:
    """Half the sum of absolute differences between two distributions.

    Zero when identical, one when disjoint. It has a direct reading: it is the
    largest difference in probability the two distributions can assign to any
    single event, which is exactly the question "how much can knowing today's
    regime change any forecast".
    """
    return float(0.5 * np.abs(np.asarray(first) - np.asarray(second)).sum())


@dataclass(frozen=True)
class HorizonMixing:
    """How much information survives to one horizon."""

    horizon_in_months: int
    mean_distance_to_stationary: float
    largest_distance_to_stationary: float
    smallest_distance_to_stationary: float
    threshold: float

    @property
    def carries_information(self) -> bool:
        return self.mean_distance_to_stationary > self.threshold

    def as_row(self) -> dict[str, object]:
        return {
            "horizon_months": self.horizon_in_months,
            "horizon_years": self.horizon_in_months / 12,
            "mean_distance_to_stationary": self.mean_distance_to_stationary,
            "largest_distance_to_stationary": self.largest_distance_to_stationary,
            "smallest_distance_to_stationary": self.smallest_distance_to_stationary,
            "carries_information": self.carries_information,
        }


@dataclass(frozen=True)
class MixingDiagnostics:
    """The convergence story for one fitted model, at the horizons that matter."""

    second_largest_eigenvalue_modulus: float
    stationary_distribution: tuple[float, ...]
    by_horizon: tuple[HorizonMixing, ...]
    threshold: float

    @property
    def half_life_in_months(self) -> float:
        """Months for the distance to the stationary distribution to halve.

        Infinite when the chain does not mix at all, which happens only for a
        transition matrix with an absorbing structure.
        """
        modulus = self.second_largest_eigenvalue_modulus
        if modulus <= 0.0:
            return 0.0
        if modulus >= 1.0:
            return float("inf")
        return float(np.log(0.5) / np.log(modulus))

    @property
    def information_horizon_in_months(self) -> int:
        """The longest measured horizon still distinguishable from the base rate.

        Zero when even the shortest horizon has converged, which would mean the
        model has nothing to say at any horizon this project forecasts.
        """
        informative = [
            item.horizon_in_months for item in self.by_horizon if item.carries_information
        ]
        return max(informative) if informative else 0

    def carries_information_at(self, horizon_in_months: int) -> bool:
        for item in self.by_horizon:
            if item.horizon_in_months == horizon_in_months:
                return item.carries_information
        raise KeyError(f"horizon {horizon_in_months} was not measured")

    def table(self) -> pd.DataFrame:
        return pd.DataFrame([item.as_row() for item in self.by_horizon])

    def describe(self) -> str:
        horizon = self.information_horizon_in_months
        if horizon == 0:
            return (
                "The chain has converged at every horizon measured. Regime information does not "
                "survive even one year, so every forecast here is the base rate."
            )
        return (
            f"The second eigenvalue modulus is {self.second_largest_eigenvalue_modulus:.4f}, a "
            f"half life of {self.half_life_in_months:.0f} months. Regime information survives to "
            f"{horizon} months ({horizon / 12:.0f} years); beyond that the projection is the "
            "unconditional base rate."
        )


def measure_mixing(
    model: GaussianHiddenMarkovModel,
    filtered_state_distributions: np.ndarray,
    horizons_in_months: Sequence[int],
    threshold: float,
) -> MixingDiagnostics:
    """Measure, across many starting points, how far each horizon has converged.

    Averaging over the filtered distributions actually observed in the sample is
    the right summary. A single starting point could be unusually informative or
    unusually close to the stationary distribution; the question a forecaster
    cares about is what happens on a typical day.
    """
    distributions = np.atleast_2d(np.asarray(filtered_state_distributions, dtype="float64"))
    stationary = model.stationary_distribution()

    measurements: list[HorizonMixing] = []
    for horizon in horizons_in_months:
        matrix_power = np.linalg.matrix_power(model.transition_matrix, horizon)
        projected = distributions @ matrix_power
        projected = projected / projected.sum(axis=1, keepdims=True)
        distances = 0.5 * np.abs(projected - stationary[None, :]).sum(axis=1)
        measurements.append(
            HorizonMixing(
                horizon_in_months=horizon,
                mean_distance_to_stationary=float(distances.mean()),
                largest_distance_to_stationary=float(distances.max()),
                smallest_distance_to_stationary=float(distances.min()),
                threshold=threshold,
            )
        )

    return MixingDiagnostics(
        second_largest_eigenvalue_modulus=model.second_largest_eigenvalue_modulus(),
        stationary_distribution=tuple(float(value) for value in stationary),
        by_horizon=tuple(measurements),
        threshold=threshold,
    )


def project_all_horizons(
    model: GaussianHiddenMarkovModel,
    state_distribution: np.ndarray,
    horizons_in_months: Sequence[int],
) -> dict[int, np.ndarray]:
    """The projected state distribution at each horizon, from one starting point."""
    return {
        horizon: model.project_state_distribution(state_distribution, horizon)
        for horizon in horizons_in_months
    }


def transition_matrix_table(
    model: GaussianHiddenMarkovModel, labels: Sequence[str]
) -> pd.DataFrame:
    """The transition matrix with readable row and column names, for the report."""
    return pd.DataFrame(
        model.transition_matrix,
        index=pd.Index(list(labels), name="from"),
        columns=pd.Index(list(labels), name="to"),
    )
