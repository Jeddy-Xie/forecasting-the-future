"""Is a forecast of seventy percent right about seventy percent of the time?

Discrimination and calibration are different virtues and a forecaster can have
either without the other. A model that says eighty percent whenever the answer is
sixty percent discriminates perfectly and is badly calibrated; under Brier scoring
it loses to a well-calibrated model with no discrimination at all.

Monotonicity gets its own check because it fails in a specific and revealing way.
When a reliability curve doubles back -- higher forecasts followed by lower
observed rates -- the model is not merely miscalibrated, it is ordering situations
wrongly, and no recalibration can fix that. A dip is only counted as a violation
when it is larger than the sampling noise in the two bins involved.

**How that noise is measured matters, and the obvious way is wrong here.** A bin
holding four hundred monthly forecasts at a one-year horizon does not hold four
hundred independent observations: consecutive forecasts share eleven of their
twelve months, so the bin is worth about thirty-three. A binomial standard error
computed on the raw count is roughly three and a half times too small, and at a
ten-year horizon eleven times too small. Every wobble then looks significant.

This is the same dependence the moving-block bootstrap exists to handle on the
skill side, and it applies here for the same reason. So the caller passes the
block length -- the horizon in months -- and each bin's count is divided by it
before the standard error is taken. Passing one recovers the naive computation,
which is what the reliability table reports alongside so both are visible.
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
    dependence_block_length: int = 1

    @property
    def effective_count(self) -> float:
        """How many independent observations this bin is actually worth.

        Never less than one: a bin with fewer forecasts than the block length
        still contains one piece of evidence, not a fraction of one.
        """
        return max(self.count / float(self.dependence_block_length), 1.0)

    @property
    def naive_standard_error(self) -> float:
        """Binomial standard error treating every forecast as independent.

        Reported so the correction below is visible rather than buried.
        """
        if self.count == 0:
            return float("nan")
        variance = self.observed_rate * (1.0 - self.observed_rate)
        return float(np.sqrt(variance / self.count))

    @property
    def standard_error(self) -> float:
        """Binomial standard error on the effective, not the raw, count."""
        if self.count == 0:
            return float("nan")
        variance = self.observed_rate * (1.0 - self.observed_rate)
        return float(np.sqrt(variance / self.effective_count))

    def as_row(self) -> dict[str, object]:
        return {
            "lower_edge": self.lower_edge,
            "upper_edge": self.upper_edge,
            "count": self.count,
            "effective_count": self.effective_count,
            "mean_forecast": self.mean_forecast,
            "observed_rate": self.observed_rate,
            "standard_error": self.standard_error,
            "naive_standard_error": self.naive_standard_error,
        }


@dataclass(frozen=True)
class CalibrationReport:
    """The reliability curve and the two numbers read off it."""

    bins: tuple[ReliabilityBin, ...]
    expected_calibration_error: float
    monotonicity_violations: int
    naive_monotonicity_violations: int
    """What the check would have said treating overlapping forecasts as
    independent. Carried so the correction is on the record."""

    forecast_count: int
    dependence_block_length: int

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
        correction = ""
        if self.naive_monotonicity_violations != self.monotonicity_violations:
            correction = (
                f" (counting overlapping forecasts as independent would have found "
                f"{self.naive_monotonicity_violations})"
            )
        return (
            f"expected calibration error {self.expected_calibration_error:.4f} over "
            f"{self.forecast_count} forecasts in {len(self.populated_bins)} populated bins, "
            f"worth about {self.forecast_count / self.dependence_block_length:.0f} independent "
            f"observations; the reliability curve is {shape}{correction}"
        )


def assess_calibration(
    predicted: np.ndarray,
    realised: np.ndarray,
    bin_count: int = DEFAULT_BIN_COUNT,
    noise_tolerance: float = NOISE_TOLERANCE_IN_STANDARD_ERRORS,
    dependence_block_length: int = 1,
) -> CalibrationReport:
    """Bin the forecasts, compare each bin's mean forecast with what happened.

    ``dependence_block_length`` is how many consecutive forecasts share most of
    their window; pass the horizon in months for overlapping forecasts, or one to
    treat them as independent.
    """
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
                dependence_block_length=max(dependence_block_length, 1),
            )
        )

    populated = [item for item in bins if item.count > 0]

    def count_reversals(use_naive_error: bool) -> int:
        found = 0
        for earlier, later in pairwise(populated):
            first = earlier.naive_standard_error if use_naive_error else earlier.standard_error
            second = later.naive_standard_error if use_naive_error else later.standard_error
            allowance = noise_tolerance * float(
                np.sqrt(np.nan_to_num(first) ** 2 + np.nan_to_num(second) ** 2)
            )
            if later.observed_rate < earlier.observed_rate - allowance:
                found += 1
        return found

    return CalibrationReport(
        bins=tuple(bins),
        expected_calibration_error=weighted_gap / float(predictions.size),
        monotonicity_violations=count_reversals(use_naive_error=False),
        naive_monotonicity_violations=count_reversals(use_naive_error=True),
        forecast_count=int(predictions.size),
        dependence_block_length=max(dependence_block_length, 1),
    )
