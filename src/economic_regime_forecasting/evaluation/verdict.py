"""Apply the pre-registered decision rule and say, per horizon, what to ship.

The thresholds are not in this file. They are in
``proving/experiments/0001-regime-conditional-forecast-skill/experiment.json``,
which was committed before the walk-forward engine had ever been run. This module
reads them and evaluates them in code, so that the verdict is a computation rather
than a judgement made after seeing the numbers.

Five gates, all of which must hold for a horizon to ship the model:

* **regimes exist** -- more than one latent state beats a single state, on both
  the held-out likelihood and the information criterion. Asked once for the whole
  run, not per horizon.
* **skill** -- the mean Brier skill score against an expanding climatology clears
  the bar, with a bootstrap interval that excludes zero.
* **calibration** -- forecasts of seventy percent happen about seventy percent of
  the time, and the reliability curve does not double back.
* **robustness** -- the sign of the skill holds up in three of four disjoint
  sub-periods, so it is not one lucky decade.
* **honesty** -- the projected regime distribution is still distinguishable from
  the model's long-run distribution at this horizon. When it is not, the model's
  forecast *is* the base rate, and presenting it as a prediction would misdescribe
  it even if it happened to score well.

A horizon that fails any gate ships the climatological base rate, and the failing
gate is named.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from economic_regime_forecasting.configuration.run_settings import PROJECT_ROOT
from economic_regime_forecasting.evaluation import bootstrap as bootstrap_module
from economic_regime_forecasting.evaluation import scoring
from economic_regime_forecasting.evaluation.calibration import assess_calibration

PRE_REGISTRATION_FILE: Path = (
    PROJECT_ROOT
    / "proving"
    / "experiments"
    / "0001-regime-conditional-forecast-skill"
    / "experiment.json"
)

SHIP_MODEL = "SHIP MODEL"
SHIP_BASE_RATE = "SHIP BASE RATE"


class VerdictError(ValueError):
    """The decision rule could not be evaluated on the results given."""


def load_decision_rule(path: Path = PRE_REGISTRATION_FILE) -> dict[str, Any]:
    """Read the pre-registered thresholds. The arbiter, not a copy of it."""
    if not path.is_file():
        raise VerdictError(
            f"the pre-registration is missing at {path}. The decision rule must exist and be "
            "committed before results are evaluated against it."
        )
    document = json.loads(path.read_text(encoding="utf-8"))
    rule: dict[str, Any] = document["decision_rule"]
    return rule


@dataclass(frozen=True)
class IndicatorHorizonMetrics:
    """Every metric for one indicator at one horizon."""

    indicator: str
    horizon_in_months: int
    resolved_forecasts: int
    base_rate: float
    brier_score: float
    climatology_brier_score: float
    brier_skill_score: float
    logarithmic_loss: float
    area_under_the_curve: float
    expected_calibration_error: float
    reliability: float
    resolution: float
    mean_distance_to_stationary: float
    mean_effective_sample_size: float

    def as_row(self) -> dict[str, object]:
        return {
            "indicator": self.indicator,
            "horizon_months": self.horizon_in_months,
            "resolved_forecasts": self.resolved_forecasts,
            "base_rate": self.base_rate,
            "brier_score": self.brier_score,
            "climatology_brier_score": self.climatology_brier_score,
            "brier_skill_score": self.brier_skill_score,
            "logarithmic_loss": self.logarithmic_loss,
            "area_under_the_curve": self.area_under_the_curve,
            "expected_calibration_error": self.expected_calibration_error,
            "reliability": self.reliability,
            "resolution": self.resolution,
            "mean_distance_to_stationary": self.mean_distance_to_stationary,
            "mean_effective_sample_size": self.mean_effective_sample_size,
        }


@dataclass(frozen=True)
class GateOutcome:
    """One gate, its requirement in words, and the evidence for or against."""

    name: str
    requirement: str
    passed: bool
    evidence: str

    def as_row(self) -> dict[str, object]:
        return {
            "gate": self.name,
            "passed": self.passed,
            "evidence": self.evidence,
            "requirement": self.requirement,
        }


@dataclass(frozen=True)
class HorizonVerdict:
    """What to ship at one horizon, and why."""

    horizon_in_months: int
    gates: tuple[GateOutcome, ...]
    mean_brier_skill_score: float
    skill_interval: bootstrap_module.BootstrapInterval | None

    @property
    def ships_model(self) -> bool:
        return all(gate.passed for gate in self.gates)

    @property
    def verdict(self) -> str:
        return SHIP_MODEL if self.ships_model else SHIP_BASE_RATE

    @property
    def failing_gates(self) -> tuple[str, ...]:
        return tuple(gate.name for gate in self.gates if not gate.passed)

    def describe(self) -> str:
        if self.ships_model:
            return (
                f"{self.horizon_in_months // 12} year: {SHIP_MODEL}. Mean skill score "
                f"{self.mean_brier_skill_score:+.4f}, every gate passed."
            )
        return (
            f"{self.horizon_in_months // 12} year: {SHIP_BASE_RATE}. Failed "
            f"{', '.join(self.failing_gates)}. Mean skill score "
            f"{self.mean_brier_skill_score:+.4f}."
        )

    def table(self) -> pd.DataFrame:
        return pd.DataFrame([gate.as_row() for gate in self.gates])


def compute_metrics(results: pd.DataFrame) -> list[IndicatorHorizonMetrics]:
    """Every metric for every indicator at every horizon."""
    metrics: list[IndicatorHorizonMetrics] = []
    for group_key, group in results.groupby(["indicator", "horizon_months"], sort=True):
        indicator = str(group_key[0])
        horizon = int(str(group_key[1]))
        scored = group.dropna(subset=["realised_outcome", "climatology_probability"])
        if scored.empty:
            continue
        predicted = scored["predicted_probability"].to_numpy(dtype="float64")
        realised = scored["realised_outcome"].to_numpy(dtype="float64")
        climatology = scored["climatology_probability"].to_numpy(dtype="float64")

        try:
            skill = scoring.brier_skill_score(predicted, realised, climatology)
        except scoring.ScoringError:
            # A benchmark with no error means the outcome never varies; the skill
            # score is undefined rather than zero, and is reported as missing.
            skill = float("nan")
        decomposition = scoring.murphy_decomposition(predicted, realised)
        calibration = assess_calibration(predicted, realised)

        metrics.append(
            IndicatorHorizonMetrics(
                indicator=indicator,
                horizon_in_months=horizon,
                resolved_forecasts=int(scored.shape[0]),
                base_rate=float(realised.mean()),
                brier_score=scoring.brier_score(predicted, realised),
                climatology_brier_score=scoring.brier_score(climatology, realised),
                brier_skill_score=skill,
                logarithmic_loss=scoring.logarithmic_loss(predicted, realised),
                area_under_the_curve=scoring.area_under_the_curve(predicted, realised),
                expected_calibration_error=calibration.expected_calibration_error,
                reliability=decomposition.reliability,
                resolution=decomposition.resolution,
                mean_distance_to_stationary=float(scored["distance_to_stationary"].mean()),
                mean_effective_sample_size=float(scored["effective_sample_size"].mean()),
            )
        )
    return metrics


def metrics_table(metrics: Sequence[IndicatorHorizonMetrics]) -> pd.DataFrame:
    return pd.DataFrame([item.as_row() for item in metrics])


def _skill_matrix(
    results: pd.DataFrame, horizon_in_months: int
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Predicted, realised and climatology as date-by-indicator matrices.

    Working in this shape is what lets the bootstrap resample *dates* while
    keeping all ten indicators aligned, which is the dependence that matters:
    forecasts made in adjacent months share almost all of their horizon window.
    """
    at_horizon = results[results["horizon_months"] == horizon_in_months]
    scored = at_horizon.dropna(subset=["realised_outcome", "climatology_probability"])
    if scored.empty:
        raise VerdictError(
            f"no forecast at the {horizon_in_months} month horizon has both a resolved outcome "
            "and a benchmark. The sample does not reach far enough to score this horizon."
        )
    predicted = scored.pivot(
        index="forecast_date", columns="indicator", values="predicted_probability"
    )
    realised = scored.pivot(index="forecast_date", columns="indicator", values="realised_outcome")
    climatology = scored.pivot(
        index="forecast_date", columns="indicator", values="climatology_probability"
    )
    return predicted, realised, climatology


def _mean_skill_over(
    positions: np.ndarray,
    predicted: np.ndarray,
    realised: np.ndarray,
    climatology: np.ndarray,
) -> float:
    """Mean Brier skill score across indicators, on the selected dates."""
    scores: list[float] = []
    for column in range(predicted.shape[1]):
        selected_realised = realised[positions, column]
        usable = np.isfinite(selected_realised)
        if usable.sum() < 2 or len(np.unique(selected_realised[usable])) < 2:
            continue
        try:
            scores.append(
                scoring.brier_skill_score(
                    predicted[positions, column][usable],
                    selected_realised[usable],
                    climatology[positions, column][usable],
                )
            )
        except scoring.ScoringError:
            continue
    if not scores:
        raise ValueError("no indicator could be scored on this resample")
    return float(np.mean(scores))


def evaluate_horizon(
    results: pd.DataFrame,
    horizon_in_months: int,
    regimes_exist: bool,
    regimes_exist_evidence: str,
    decision_rule: dict[str, Any],
    seed: int,
) -> HorizonVerdict:
    """Apply all five gates at one horizon."""
    gates_specification = decision_rule["gates"]
    predicted_frame, realised_frame, climatology_frame = _skill_matrix(results, horizon_in_months)
    predicted = predicted_frame.to_numpy(dtype="float64")
    realised = realised_frame.to_numpy(dtype="float64")
    climatology = climatology_frame.to_numpy(dtype="float64")
    date_count = predicted.shape[0]

    def statistic(positions: np.ndarray) -> float:
        return _mean_skill_over(positions, predicted, realised, climatology)

    all_positions = np.arange(date_count)
    mean_skill = statistic(all_positions)

    skill_specification = gates_specification["skill"]
    interval: bootstrap_module.BootstrapInterval | None = None
    try:
        interval = bootstrap_module.moving_block_bootstrap(
            statistic,
            all_positions,
            block_length=horizon_in_months,
            resamples=int(skill_specification["bootstrap"]["resamples"]),
            seed=seed,
            confidence_level=float(skill_specification["confidence_level"]),
        )
    except bootstrap_module.BootstrapError as error:
        interval = None
        interval_note = f"interval unavailable: {error}"
    else:
        interval_note = interval.describe()

    minimum_skill = float(skill_specification["minimum_mean_skill_score"])
    skill_passed = (
        mean_skill > minimum_skill and interval is not None and interval.lower_bound > 0.0
    )

    # Calibration, pooled across indicators at this horizon.
    flat_usable = np.isfinite(realised)
    # Blocks as long as the horizon, matching the bootstrap. Monthly forecasts at
    # this horizon overlap by all but one month, so treating a bin's raw count as
    # independent evidence would make every wobble look significant.
    calibration = assess_calibration(
        predicted[flat_usable],
        realised[flat_usable],
        dependence_block_length=horizon_in_months,
    )
    calibration_specification = gates_specification["calibration"]
    maximum_error = float(calibration_specification["maximum_expected_calibration_error"])
    calibration_passed = (
        calibration.expected_calibration_error < maximum_error and calibration.is_monotone
    )

    # Robustness across four disjoint, chronologically contiguous sub-periods.
    robustness_specification = gates_specification["robustness"]
    sub_period_count = int(robustness_specification["sub_periods"])
    minimum_positive = int(robustness_specification["minimum_positive_sub_periods"])
    sub_period_scores: list[float] = []
    for chunk in np.array_split(all_positions, sub_period_count):
        if chunk.size == 0:
            continue
        try:
            sub_period_scores.append(statistic(chunk))
        except ValueError:
            sub_period_scores.append(float("nan"))
    positive_periods = int(sum(1 for value in sub_period_scores if value > 0.0))
    robustness_passed = positive_periods >= minimum_positive

    # Honesty: is the projection still distinguishable from the stationary distribution?
    honesty_specification = gates_specification["honesty"]
    minimum_distance = float(honesty_specification["minimum_total_variation_distance"])
    at_horizon = results[results["horizon_months"] == horizon_in_months]
    mean_distance = float(at_horizon["distance_to_stationary"].mean())
    honesty_passed = mean_distance > minimum_distance

    gates = (
        GateOutcome(
            name="regimes exist",
            requirement=gates_specification["regimes_exist"]["requirement"],
            passed=regimes_exist,
            evidence=regimes_exist_evidence,
        ),
        GateOutcome(
            name="skill",
            requirement=skill_specification["requirement"],
            passed=skill_passed,
            evidence=(
                f"mean skill score {mean_skill:+.4f} against a bar of {minimum_skill:+.2f}; "
                f"{interval_note}"
            ),
        ),
        GateOutcome(
            name="calibration",
            requirement=calibration_specification["requirement"],
            passed=calibration_passed,
            evidence=calibration.describe(),
        ),
        GateOutcome(
            name="robustness",
            requirement=robustness_specification["requirement"],
            passed=robustness_passed,
            evidence=(
                f"{positive_periods} of {sub_period_count} sub-periods positive; scores "
                + ", ".join(f"{value:+.3f}" for value in sub_period_scores)
            ),
        ),
        GateOutcome(
            name="honesty",
            requirement=honesty_specification["requirement"],
            passed=honesty_passed,
            evidence=(
                f"mean total variation distance to the stationary distribution "
                f"{mean_distance:.4f} against a floor of {minimum_distance:.2f}"
            ),
        ),
    )

    return HorizonVerdict(
        horizon_in_months=horizon_in_months,
        gates=gates,
        mean_brier_skill_score=mean_skill,
        skill_interval=interval,
    )


def evaluate_all_horizons(
    results: pd.DataFrame,
    horizons_in_months: Sequence[int],
    regimes_exist: bool,
    regimes_exist_evidence: str,
    seed: int,
    decision_rule: dict[str, Any] | None = None,
) -> list[HorizonVerdict]:
    """Apply the decision rule at every horizon the project forecasts."""
    rule = decision_rule if decision_rule is not None else load_decision_rule()
    return [
        evaluate_horizon(results, horizon, regimes_exist, regimes_exist_evidence, rule, seed)
        for horizon in horizons_in_months
    ]


def verdict_table(verdicts: Sequence[HorizonVerdict]) -> pd.DataFrame:
    """One row per horizon: the verdict, the skill, and any failing gates."""
    rows = []
    for item in verdicts:
        rows.append(
            {
                "horizon_months": item.horizon_in_months,
                "horizon_years": item.horizon_in_months // 12,
                "verdict": item.verdict,
                "mean_brier_skill_score": item.mean_brier_skill_score,
                "skill_lower_bound": (
                    item.skill_interval.lower_bound if item.skill_interval else float("nan")
                ),
                "skill_upper_bound": (
                    item.skill_interval.upper_bound if item.skill_interval else float("nan")
                ),
                "effective_independent_observations": (
                    item.skill_interval.effective_independent_sample_size
                    if item.skill_interval
                    else float("nan")
                ),
                "failing_gates": ", ".join(item.failing_gates) or "none",
            }
        )
    return pd.DataFrame(rows)
