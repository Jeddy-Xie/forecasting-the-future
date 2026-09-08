"""Scoring probability forecasts of binary events.

Every function here takes two aligned arrays of numbers and returns a number.
There is no input, no output, no configuration and no state, which is why the
tests can check each one against a value computed by hand.

The headline metric is the Brier skill score against an expanding climatology.
A raw Brier score cannot be read on its own: a forecaster who says "no recession"
every month scores brilliantly, because recessions are rare. The skill score asks
the only question that matters, which is whether the model beat the base rate.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


class ScoringError(ValueError):
    """Forecasts and outcomes could not be scored as given."""


def _aligned(predicted: np.ndarray, realised: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Drop pairs where either side is missing, and check what is left is usable."""
    predictions = np.asarray(predicted, dtype="float64")
    outcomes = np.asarray(realised, dtype="float64")
    if predictions.shape != outcomes.shape:
        raise ScoringError(
            f"{predictions.size} forecasts against {outcomes.size} outcomes; they must be aligned"
        )
    usable = np.isfinite(predictions) & np.isfinite(outcomes)
    predictions, outcomes = predictions[usable], outcomes[usable]
    if predictions.size == 0:
        raise ScoringError("no forecast has a resolved outcome, so nothing can be scored")
    if predictions.min() < 0.0 or predictions.max() > 1.0:
        raise ScoringError(
            f"forecasts range from {predictions.min()} to {predictions.max()}, outside the unit "
            "interval"
        )
    if not np.isin(outcomes, (0.0, 1.0)).all():
        raise ScoringError("outcomes must all be zero or one")
    return predictions, outcomes


def brier_score(predicted: np.ndarray, realised: np.ndarray) -> float:
    """Mean squared error of a probability forecast. Lower is better, zero is perfect."""
    predictions, outcomes = _aligned(predicted, realised)
    return float(np.mean((predictions - outcomes) ** 2))


def brier_skill_score(predicted: np.ndarray, realised: np.ndarray, reference: np.ndarray) -> float:
    """How much of the reference forecast's error the model removes.

    One is perfect, zero is no better than the reference, and negative means the
    model is worse than quoting the base rate. This is the headline number, and
    the reference is deliberately the expanding climatology rather than a
    full-sample one, so the benchmark never knows something the model could not.
    """
    predictions = np.asarray(predicted, dtype="float64")
    outcomes = np.asarray(realised, dtype="float64")
    benchmark = np.asarray(reference, dtype="float64")
    usable = np.isfinite(predictions) & np.isfinite(outcomes) & np.isfinite(benchmark)
    if not usable.any():
        raise ScoringError(
            "no forecast has both a resolved outcome and a benchmark to compare against"
        )
    model_error = brier_score(predictions[usable], outcomes[usable])
    benchmark_error = brier_score(benchmark[usable], outcomes[usable])
    if benchmark_error == 0.0:
        raise ScoringError(
            "the benchmark is perfect, so there is no error for the model to remove and a skill "
            "score is undefined. This happens when an outcome never varies."
        )
    return float(1.0 - model_error / benchmark_error)


def logarithmic_loss(
    predicted: np.ndarray,
    realised: np.ndarray,
    clip: tuple[float, float] = (0.01, 0.99),
) -> float:
    """Negative mean log probability of what happened.

    Unbounded when a forecast of zero meets an outcome of one, so probabilities
    are clipped. The clip is an argument rather than a constant because it changes
    the number, and a metric whose definition is hidden is not a metric.
    """
    predictions, outcomes = _aligned(predicted, realised)
    clipped = np.clip(predictions, clip[0], clip[1])
    return float(-np.mean(outcomes * np.log(clipped) + (1.0 - outcomes) * np.log(1.0 - clipped)))


def area_under_the_curve(predicted: np.ndarray, realised: np.ndarray) -> float:
    """Probability a random positive case is ranked above a random negative one.

    Computed from ranks, so ties are handled correctly. Returns not-a-number when
    every outcome is the same, because ranking is undefined with nothing to rank
    against.
    """
    predictions, outcomes = _aligned(predicted, realised)
    positives = outcomes == 1.0
    positive_count = int(positives.sum())
    negative_count = int((~positives).sum())
    if positive_count == 0 or negative_count == 0:
        return float("nan")

    order = np.argsort(predictions, kind="mergesort")
    ranks = np.empty(predictions.size, dtype="float64")
    ranks[order] = np.arange(1, predictions.size + 1, dtype="float64")

    # Average the ranks within each group of tied forecasts.
    sorted_predictions = predictions[order]
    start = 0
    for end in range(1, sorted_predictions.size + 1):
        if end == sorted_predictions.size or sorted_predictions[end] != sorted_predictions[start]:
            if end - start > 1:
                ranks[order[start:end]] = ranks[order[start:end]].mean()
            start = end

    rank_sum = float(ranks[positives].sum())
    return float(
        (rank_sum - positive_count * (positive_count + 1) / 2.0) / (positive_count * negative_count)
    )


@dataclass(frozen=True)
class MurphyDecomposition:
    """The Brier score split into the three things that drive it.

    ``reliability`` is miscalibration and should be near zero. ``resolution`` is
    the ability to tell high-probability situations from low-probability ones, and
    bigger is better. ``uncertainty`` is a property of the events themselves that
    no forecaster can change. The identity is reliability minus resolution plus
    uncertainty, and it is checked rather than asserted.
    """

    reliability: float
    resolution: float
    uncertainty: float
    bin_count: int

    @property
    def implied_brier_score(self) -> float:
        return self.reliability - self.resolution + self.uncertainty


def murphy_decomposition(
    predicted: np.ndarray, realised: np.ndarray, bin_count: int = 10
) -> MurphyDecomposition:
    """Split the Brier score into calibration, discrimination and base difficulty."""
    predictions, outcomes = _aligned(predicted, realised)
    overall_rate = float(outcomes.mean())
    edges = np.linspace(0.0, 1.0, bin_count + 1)
    assignments = np.clip(np.digitize(predictions, edges[1:-1], right=False), 0, bin_count - 1)

    reliability = 0.0
    resolution = 0.0
    for index in range(bin_count):
        in_bin = assignments == index
        count = int(in_bin.sum())
        if count == 0:
            continue
        mean_forecast = float(predictions[in_bin].mean())
        observed_rate = float(outcomes[in_bin].mean())
        reliability += count * (mean_forecast - observed_rate) ** 2
        resolution += count * (observed_rate - overall_rate) ** 2

    total = float(predictions.size)
    return MurphyDecomposition(
        reliability=reliability / total,
        resolution=resolution / total,
        uncertainty=overall_rate * (1.0 - overall_rate),
        bin_count=bin_count,
    )
