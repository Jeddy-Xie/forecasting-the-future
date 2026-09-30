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


# ------------------------------------------------ the recalibration test (rule 0007)

RECALIBRATION_PROBABILITY_CLIP: tuple[float, float] = (0.005, 0.995)
"""Forecasts are clipped here before the logit, so a forecast of exactly zero or
one is a very confident forecast rather than an infinite one."""

RECALIBRATION_CONFIDENCE_LEVEL = 0.95


def fit_logistic_recalibration(
    predicted: np.ndarray, realised: np.ndarray, iterations: int = 100
) -> tuple[float, float]:
    """Maximum-likelihood intercept a and slope b in logit P(y = 1) = a + b logit(p).

    A calibrated forecaster has a = 0 and b = 1: its log-odds need no shifting and
    no stretching. Fitted by Newton's method, which converges in a handful of steps
    on this concave likelihood. When the outcomes do not vary, or the forecasts
    separate them perfectly, there is no finite answer, and that raises.
    """
    predictions, outcomes = _aligned(predicted, realised)
    if np.unique(outcomes).size < 2:
        raise ScoringError("the outcomes do not vary, so a recalibration cannot be fitted")
    low, high = RECALIBRATION_PROBABILITY_CLIP
    log_odds = np.log(np.clip(predictions, low, high) / (1.0 - np.clip(predictions, low, high)))
    design = np.column_stack([np.ones_like(log_odds), log_odds])
    weights = np.array([0.0, 1.0])
    for _ in range(iterations):
        # A Newton step can overshoot on the way to the optimum; clipping the linear
        # predictor keeps exp finite without moving a converged fit, whose log-odds
        # sit far inside these bounds.
        fitted = 1.0 / (1.0 + np.exp(-np.clip(design @ weights, -500.0, 500.0)))
        gradient = design.T @ (outcomes - fitted)
        curvature = design.T @ (design * (fitted * (1.0 - fitted))[:, None])
        step = np.linalg.solve(curvature, gradient)
        weights = weights + step
        if not np.all(np.isfinite(weights)) or np.abs(weights).max() > 1e6:
            raise ScoringError("the recalibration diverged: the forecasts separate the outcomes")
        if np.abs(step).max() < 1e-10:
            return float(weights[0]), float(weights[1])
    raise ScoringError(f"the recalibration did not converge in {iterations} Newton steps")


@dataclass(frozen=True)
class RecalibrationTest:
    """Rule 0007's calibration test at one horizon: the fitted intercept and slope,
    each with a moving-block bootstrap interval over forecast dates."""

    intercept: float
    slope: float
    intercept_interval: tuple[float, float]
    slope_interval: tuple[float, float]
    confidence_level: float
    block_length: int
    resamples_used: int
    uses_intercept: bool
    """False when the size check found the joint test too strict at this sample size
    and the registration's fallback, the slope alone, applies."""

    @property
    def calibrated(self) -> bool:
        slope_ok = self.slope_interval[0] <= 1.0 <= self.slope_interval[1]
        intercept_ok = self.intercept_interval[0] <= 0.0 <= self.intercept_interval[1]
        return slope_ok and (intercept_ok or not self.uses_intercept)

    def describe(self) -> str:
        level = f"{self.confidence_level:.0%}"
        low, high = self.slope_interval
        parts = [f"slope {self.slope:+.3f} [{low:+.3f}, {high:+.3f}] (1 is calibrated)"]
        if self.uses_intercept:
            parts.append(
                f"intercept {self.intercept:+.3f} [{self.intercept_interval[0]:+.3f}, "
                f"{self.intercept_interval[1]:+.3f}] (0 is calibrated)"
            )
        return (
            f"{'; '.join(parts)}, {level} moving-block intervals, blocks of {self.block_length} "
            f"months, {self.resamples_used} resamples"
        )


def assess_recalibration(
    predicted: np.ndarray,
    realised: np.ndarray,
    *,
    block_length: int,
    resamples: int,
    seed: int,
    confidence_level: float = RECALIBRATION_CONFIDENCE_LEVEL,
    uses_intercept: bool = True,
) -> RecalibrationTest:
    """Fit the recalibration on date-by-indicator matrices and bootstrap it by date.

    Resampling whole dates keeps every indicator on a date together, the same
    dependence the skill bootstrap preserves. The fit is memoised on the drawn
    dates, so the intercept's interval and the slope's are read off one set of
    resamples.
    """
    from economic_regime_forecasting.evaluation import bootstrap as bootstrap_module

    predicted = np.atleast_2d(np.asarray(predicted, dtype="float64"))
    realised = np.atleast_2d(np.asarray(realised, dtype="float64"))
    fits: dict[bytes, tuple[float, float]] = {}

    def fit_on(positions: np.ndarray) -> tuple[float, float]:
        key = np.ascontiguousarray(positions).tobytes()
        if key not in fits:
            rows_predicted = predicted[positions].ravel()
            rows_realised = realised[positions].ravel()
            usable = np.isfinite(rows_predicted) & np.isfinite(rows_realised)
            try:
                fits[key] = fit_logistic_recalibration(
                    rows_predicted[usable], rows_realised[usable]
                )
            except ScoringError as error:
                raise ValueError(str(error)) from error
        return fits[key]

    everything = np.arange(predicted.shape[0])
    intercept, slope = fit_on(everything)

    def intercept_on(positions: np.ndarray) -> float:
        return fit_on(positions)[0]

    def slope_on(positions: np.ndarray) -> float:
        return fit_on(positions)[1]

    intervals = [
        bootstrap_module.moving_block_bootstrap(
            statistic,
            everything,
            block_length=block_length,
            resamples=resamples,
            seed=seed,
            confidence_level=confidence_level,
        )
        for statistic in (intercept_on, slope_on)
    ]
    return RecalibrationTest(
        intercept=intercept,
        slope=slope,
        intercept_interval=(intervals[0].lower_bound, intervals[0].upper_bound),
        slope_interval=(intervals[1].lower_bound, intervals[1].upper_bound),
        confidence_level=confidence_level,
        block_length=intervals[1].block_length,
        resamples_used=intervals[1].resamples,
        uses_intercept=uses_intercept,
    )
