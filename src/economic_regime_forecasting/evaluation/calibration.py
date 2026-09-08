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

**The comparison is across every ordered pair of bins, not only adjacent ones.**
Comparing neighbours alone misses the failure that matters most: a curve sliding
downward by a little in every step is a complete reversal, and no single step of
it is large enough to flag. Checking all pairs catches that in the comparison
between the first bin and the last, where the drop is the sum of every step.

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

**Dependence runs along a second axis too.** When several indicators are pooled
into one diagram, ten forecasts made on the same date are not ten independent
observations either: at a ten-year horizon "a recession at some point" and
"unemployment above seven percent at some point" are close to the same question.
Correcting only the time axis would leave an error of the same kind on the other.

The tempting shortcut is to count each date once, treating indicators sharing a
date as perfectly correlated. That is too conservative to be useful: applied to
ten genuinely independent indicators it widens the band far enough that a
completely reversed forecaster passes, and a check that cannot fail is not a
check. So the correlation is measured instead. :func:`cross_sectional_design_effect`
computes it from the forecast errors themselves and returns the factor by which
the variance of a pooled average is inflated; independent indicators give one, and
identical ones give the indicator count.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    cross_sectional_design_effect: float = 1.0

    @property
    def effective_count(self) -> float:
        """How many independent observations this bin is actually worth.

        The raw count divided by the two sources of dependence: overlap between
        consecutive months, and correlation between indicators forecast on the
        same date. Never less than one -- a bin holding fewer forecasts than the
        block length still contains a piece of evidence, not a fraction of one.
        """
        inflation = float(self.dependence_block_length) * max(
            self.cross_sectional_design_effect, 1.0
        )
        return max(self.count / inflation, 1.0)

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
    cross_sectional_design_effect: float

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
        independent = sum(item.effective_count for item in self.populated_bins)
        return (
            f"expected calibration error {self.expected_calibration_error:.4f} over "
            f"{self.forecast_count} forecasts in {len(self.populated_bins)} populated bins, "
            f"worth about {independent:.0f} independent observations; the reliability curve is "
            f"{shape}{correction}"
        )


def assess_calibration(
    predicted: np.ndarray,
    realised: np.ndarray,
    bin_count: int = DEFAULT_BIN_COUNT,
    noise_tolerance: float = NOISE_TOLERANCE_IN_STANDARD_ERRORS,
    dependence_block_length: int = 1,
    cross_sectional_design_effect: float = 1.0,
) -> CalibrationReport:
    """Bin the forecasts, compare each bin's mean forecast with what happened.

    ``dependence_block_length`` is how many consecutive forecasts share most of
    their window; pass the horizon in months for overlapping forecasts, or one to
    treat them as independent. ``cross_sectional_design_effect`` is how much the
    variance of a pooled average is inflated by correlation between the series
    pooled together; one means independent. Get it from
    :func:`cross_sectional_design_effect`.
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
                cross_sectional_design_effect=cross_sectional_design_effect,
            )
        )

    populated = [item for item in bins if item.count > 0]

    def count_reversals(use_naive_error: bool) -> int:
        found = 0
        for position, earlier in enumerate(populated):
            for later in populated[position + 1 :]:
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
        cross_sectional_design_effect=cross_sectional_design_effect,
    )


def cross_sectional_design_effect(forecast_errors: np.ndarray) -> float:
    """How much correlation between pooled series inflates the variance of their average.

    ``forecast_errors`` is shaped dates by series and holds realised minus
    predicted. The design effect for the mean of K series with average pairwise
    correlation r is one plus (K minus one) times r: one when the series are
    independent, K when they are identical.

    Floored at one. A negative average correlation would genuinely shrink the
    variance, but claiming a smaller standard error on the strength of an
    estimated correlation is the wrong direction to be adventurous in.
    """
    errors = np.asarray(forecast_errors, dtype="float64")
    if errors.ndim != 2 or errors.shape[1] < 2:
        return 1.0
    complete = errors[np.isfinite(errors).all(axis=1)]
    if complete.shape[0] < 3:
        return 1.0
    varying = complete[:, complete.std(axis=0) > 0.0]
    if varying.shape[1] < 2:
        return 1.0

    correlations = np.corrcoef(varying, rowvar=False)
    series_count = correlations.shape[0]
    off_diagonal = correlations[~np.eye(series_count, dtype=bool)]
    average_correlation = float(np.nanmean(off_diagonal))
    if not np.isfinite(average_correlation):
        return 1.0
    return float(max(1.0, 1.0 + (series_count - 1) * average_correlation))
