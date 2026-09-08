"""Is a forecast of seventy percent right about seventy percent of the time?

Discrimination and calibration are different virtues and a forecaster can have
either without the other. A model that says eighty percent whenever the answer is
sixty percent discriminates perfectly and is badly calibrated; under Brier scoring
it loses to a well-calibrated model with no discrimination at all.

Monotonicity gets its own check because it fails in a specific and revealing way.
When a reliability curve doubles back -- higher forecasts followed by lower
observed rates -- the model is not merely miscalibrated, it is ordering situations
wrongly, and no recalibration can fix that. A dip is only counted as a violation
when it is larger than the sampling noise in the two bins involved, since with ten
bins over a few hundred overlapping forecasts a small wobble means nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

import numpy as np
import pandas as pd

from economic_regime_forecasting.evaluation.scoring import ScoringError, _aligned

DEFAULT_BIN_COUNT = 10
NOISE_TOLERANCE_IN_STANDARD_ERRORS = 2.0


@dataclass(frozen=True)
class ReliabilityBin:
    """One bin of the reliability diagram."""

    lower_edge: float
    upper_edge: float
    count: int
    mean_forecast: float
    observed_rate: float

    @property
    def standard_error(self) -> float:
        """Binomial standard error of the observed rate in this bin."""
        if self.count == 0:
            return float("nan")
        variance = self.observed_rate * (1.0 - self.observed_rate)
        return float(np.sqrt(variance / self.count))

    def as_row(self) -> dict[str, object]:
        return {
            "lower_edge": self.lower_edge,
            "upper_edge": self.upper_edge,
            "count": self.count,
            "mean_forecast": self.mean_forecast,
            "observed_rate": self.observed_rate,
            "standard_error": self.standard_error,
        }


@dataclass(frozen=True)
class CalibrationReport:
    """The reliability curve and the two numbers read off it."""

    bins: tuple[ReliabilityBin, ...]
    expected_calibration_error: float
    monotonicity_violations: int
    forecast_count: int

    @property
    def populated_bins(self) -> tuple[ReliabilityBin, ...]:
        return tuple(item for item in self.bins if item.count > 0)

    @property
    def is_monotone(self) -> bool:
        return self.monotonicity_violations == 0

    def table(self) -> pd.DataFrame:
        return pd.DataFrame([item.as_row() for item in self.populated_bins])

    def describe(self) -> str:
        shape = (
            "monotone"
            if self.is_monotone
            else (f"not monotone ({self.monotonicity_violations} reversal(s) beyond noise)")
        )
        return (
            f"expected calibration error {self.expected_calibration_error:.4f} over "
            f"{self.forecast_count} forecasts in {len(self.populated_bins)} populated bins; "
            f"the reliability curve is {shape}"
        )


def assess_calibration(
    predicted: np.ndarray,
    realised: np.ndarray,
    bin_count: int = DEFAULT_BIN_COUNT,
    noise_tolerance: float = NOISE_TOLERANCE_IN_STANDARD_ERRORS,
) -> CalibrationReport:
    """Bin the forecasts, compare each bin's mean forecast with what happened."""
    if bin_count < 2:
        raise ScoringError(f"a reliability diagram needs at least two bins, got {bin_count}")
    predictions, outcomes = _aligned(predicted, realised)

    edges = np.linspace(0.0, 1.0, bin_count + 1)
    assignments = np.clip(np.digitize(predictions, edges[1:-1], right=False), 0, bin_count - 1)

    bins: list[ReliabilityBin] = []
    weighted_gap = 0.0
    for index in range(bin_count):
        in_bin = assignments == index
        count = int(in_bin.sum())
        mean_forecast = float(predictions[in_bin].mean()) if count else float("nan")
        observed_rate = float(outcomes[in_bin].mean()) if count else float("nan")
        if count:
            weighted_gap += count * abs(mean_forecast - observed_rate)
        bins.append(
            ReliabilityBin(
                lower_edge=float(edges[index]),
                upper_edge=float(edges[index + 1]),
                count=count,
                mean_forecast=mean_forecast,
                observed_rate=observed_rate,
            )
        )

    populated = [item for item in bins if item.count > 0]
    violations = 0
    for earlier, later in pairwise(populated):
        allowance = noise_tolerance * float(
            np.sqrt(
                np.nan_to_num(earlier.standard_error) ** 2
                + np.nan_to_num(later.standard_error) ** 2
            )
        )
        if later.observed_rate < earlier.observed_rate - allowance:
            violations += 1

    return CalibrationReport(
        bins=tuple(bins),
        expected_calibration_error=weighted_gap / float(predictions.size),
        monotonicity_violations=violations,
        forecast_count=int(predictions.size),
    )
