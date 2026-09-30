"""Rule 0007's verdict, computed beside 0001's and never instead of it.

0001 is frozen: its five gates keep reading the series-start climatology exactly as
coded, and its verdicts keep being printed. Rule 0007
(`proving/experiments/0007-successor-evaluation-rule/experiment.json`) governs every
new claim and every re-ship after 2026-09-29's. It asks, per horizon:

- **skill** against R1, the climatology on the model's own sample: mean skill above
  +0.02 with the 90% interval above zero, and pooled skill of the same sign, since a
  claim on which the two aggregates disagree is not established;
- **calibration** by the logistic recalibration test sized for this sample, not by
  0001's ten-bin error, which a perfectly calibrated forecaster fails most of the time;
- **robustness**: positive skill against R1 in at least three of four chronological
  blocks;
- **honesty**: the projection still at least 0.05 from the stationary distribution;
- **not beaten by the chain**: the model minus R2, the regime-free chain, not
  entirely below zero at 90%.

The thresholds are 0001's. Plain frames in, plain values out.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from economic_regime_forecasting.evaluation import paired_skill_comparison as paired
from economic_regime_forecasting.evaluation.calibration import (
    RecalibrationTest,
    assess_recalibration,
)
from economic_regime_forecasting.evaluation.scoring import ScoringError
from economic_regime_forecasting.evaluation.skill_by_horizon import matrices_at
from economic_regime_forecasting.evaluation.verdict import (
    SHIP_BASE_RATE,
    SHIP_MODEL,
    GateOutcome,
    _mean_skill_over,
    _scoreable_columns,
)

MODEL_SAMPLE_CLIMATOLOGY = "model_sample_climatology_probability"
CONDITION_CHAIN = "condition_chain_probability"
MINIMUM_MEAN_SKILL = 0.02
SKILL_CONFIDENCE_LEVEL = 0.90
SUB_PERIODS = 4
MINIMUM_POSITIVE_SUB_PERIODS = 3
MINIMUM_TOTAL_VARIATION_DISTANCE = 0.05

CALIBRATION_TEST_USES_INTERCEPT = False
"""Whether the calibration test asks the intercept to contain zero as well as the
slope to contain one. Rule 0007 fixed, before the test was used, that the joint test
applies only if a perfectly calibrated forecaster passes it at least 80% of the time
at this sample size, and the slope alone otherwise.

Measured 2026-09-29 by research/briefings/derivations/sim_recalibration_test_size.py
(200 simulated panels of 378 dates by 10 indicators, persistent and overlapping
outcomes, 12-month blocks): the joint test passed a perfectly calibrated forecaster
60.5% of the time, so the fallback applies, and this is False. The fallback is not
clean either: the slope test alone passed 77.5%. The 95% intervals under-cover on
outcomes this persistent, so the test fails a calibrated forecaster about one time in
four, not one in twenty. That errs against shipping the model, and it is recorded
rather than adjusted: moving the level after seeing the size would be the forbidden
act in miniature."""


class SuccessorVerdictError(ValueError):
    """Rule 0007 could not be evaluated on the forecasts given."""


@dataclass(frozen=True)
class SuccessorVerdict:
    """Rule 0007's verdict at one horizon."""

    horizon_in_months: int
    mean_skill: float
    pooled_skill: float
    skill_lower_bound: float
    skill_upper_bound: float
    model_minus_chain: float
    model_minus_chain_lower_bound: float
    model_minus_chain_upper_bound: float
    calibration: RecalibrationTest | None
    gates: tuple[GateOutcome, ...]

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
        years = self.horizon_in_months // 12
        if self.ships_model:
            return f"{years} year: {SHIP_MODEL} under 0007. Every gate passed."
        return (
            f"{years} year: {SHIP_BASE_RATE} under 0007 (ships R1). Failed "
            f"{', '.join(self.failing_gates)}."
        )

    def as_row(self) -> dict[str, object]:
        return {
            "horizon_months": self.horizon_in_months,
            "verdict": self.verdict,
            "failing_gates": ", ".join(self.failing_gates) or "none",
            "mean_brier_skill_score_against_model_sample": self.mean_skill,
            "pooled_brier_skill_score_against_model_sample": self.pooled_skill,
            "skill_lower_bound": self.skill_lower_bound,
            "skill_upper_bound": self.skill_upper_bound,
            "model_minus_chain": self.model_minus_chain,
            "model_minus_chain_lower_bound": self.model_minus_chain_lower_bound,
            "model_minus_chain_upper_bound": self.model_minus_chain_upper_bound,
            "calibration_slope": None if self.calibration is None else self.calibration.slope,
            "calibration_intercept": (
                None if self.calibration is None else self.calibration.intercept
            ),
            "calibrated": None if self.calibration is None else self.calibration.calibrated,
        }


def _pooled_skill(matrices: paired.ForecastMatrices) -> float:
    usable = np.isfinite(matrices.realised) & np.isfinite(matrices.climatology)
    forecast = np.sum((matrices.predicted[usable] - matrices.realised[usable]) ** 2)
    benchmark = np.sum((matrices.climatology[usable] - matrices.realised[usable]) ** 2)
    return float(1.0 - forecast / benchmark) if benchmark > 0 else float("nan")


def evaluate_horizon(
    results: pd.DataFrame,
    horizon_in_months: int,
    *,
    resamples: int,
    seed: int,
) -> SuccessorVerdict:
    """All five of rule 0007's gates at one horizon."""
    missing = [
        column for column in (MODEL_SAMPLE_CLIMATOLOGY, CONDITION_CHAIN) if column not in results
    ]
    if missing:
        raise SuccessorVerdictError(
            f"the results carry no {missing}; rule 0007 is read against the reference columns "
            "the backtest has written since 2026-09-29. Re-run `forecast backtest`."
        )
    model = matrices_at(
        results, horizon_in_months, "predicted_probability", MODEL_SAMPLE_CLIMATOLOGY
    )
    chain = matrices_at(results, horizon_in_months, CONDITION_CHAIN, MODEL_SAMPLE_CLIMATOLOGY)
    columns = _scoreable_columns(model.predicted, model.realised, model.climatology)
    if not columns:
        raise SuccessorVerdictError(
            f"no indicator's skill against R1 is defined at {horizon_in_months} months"
        )
    positions = np.arange(model.shape[0])

    def statistic(chosen: np.ndarray) -> float:
        return _mean_skill_over(
            chosen,
            model.predicted,
            model.realised,
            model.climatology,
            columns,
            require_every_indicator=True,
        )[0]

    mean_skill = statistic(positions)
    pooled_skill = _pooled_skill(model)
    (skill_interval,) = paired.intervals_from_one_set_of_resamples(
        statistic,
        positions,
        block_length=horizon_in_months,
        resamples=resamples,
        seed=seed,
        confidence_levels=(SKILL_CONFIDENCE_LEVEL,),
    )
    same_sign = np.sign(mean_skill) == np.sign(pooled_skill)
    skill_passed = (
        mean_skill > MINIMUM_MEAN_SKILL and skill_interval.lower_bound > 0.0 and bool(same_sign)
    )

    calibration: RecalibrationTest | None
    try:
        calibration = assess_recalibration(
            model.predicted,
            model.realised,
            block_length=horizon_in_months,
            resamples=resamples,
            seed=seed,
            uses_intercept=CALIBRATION_TEST_USES_INTERCEPT,
        )
        calibration_passed = calibration.calibrated
        calibration_evidence = calibration.describe()
    except (ScoringError, ValueError) as error:
        calibration, calibration_passed = None, False
        calibration_evidence = f"the recalibration could not be fitted: {error}"

    sub_period_scores: list[float] = []
    for chunk in np.array_split(positions, SUB_PERIODS):
        try:
            score, _ = _mean_skill_over(
                chunk,
                model.predicted,
                model.realised,
                model.climatology,
                columns,
                require_every_indicator=False,
            )
        except ValueError:
            score = float("nan")
        sub_period_scores.append(score)
    positive = sum(1 for score in sub_period_scores if score > 0.0)

    at_horizon = results[results["horizon_months"] == horizon_in_months]
    distance = float(at_horizon["distance_to_stationary"].mean())

    difference = paired.paired_mean_skill_difference(
        chain,
        model,
        block_length=horizon_in_months,
        resamples=resamples,
        seed=seed,
        confidence_levels=(SKILL_CONFIDENCE_LEVEL,),
    )
    if difference.interval is None:
        raise SuccessorVerdictError(
            f"model minus chain could not be bootstrapped at {horizon_in_months} months: "
            f"{difference.interval_note}"
        )
    chain_interval = difference.interval

    gates = (
        GateOutcome(
            name="skill",
            requirement=(
                "mean skill against R1 above +0.02, its 90% interval above zero, and pooled "
                "skill of the same sign"
            ),
            passed=skill_passed,
            evidence=(
                f"mean {mean_skill:+.4f} [{skill_interval.lower_bound:+.4f}, "
                f"{skill_interval.upper_bound:+.4f}], pooled {pooled_skill:+.4f}"
            ),
        ),
        GateOutcome(
            name="calibration",
            requirement="the logistic recalibration's slope interval contains 1"
            + (" and its intercept interval contains 0" if CALIBRATION_TEST_USES_INTERCEPT else ""),
            passed=calibration_passed,
            evidence=calibration_evidence,
        ),
        GateOutcome(
            name="robustness",
            requirement="skill against R1 positive in at least three of four chronological blocks",
            passed=positive >= MINIMUM_POSITIVE_SUB_PERIODS,
            evidence=f"{positive} of {SUB_PERIODS} positive: "
            + ", ".join(f"{score:+.3f}" for score in sub_period_scores),
        ),
        GateOutcome(
            name="honesty",
            requirement="mean distance to the stationary distribution above 0.05",
            passed=distance > MINIMUM_TOTAL_VARIATION_DISTANCE,
            evidence=f"mean total variation distance {distance:.4f}",
        ),
        GateOutcome(
            name="not beaten by the chain",
            requirement="model minus R2's 90% interval not entirely below zero",
            passed=not chain_interval.upper_bound < 0.0,
            evidence=(
                f"model minus chain {difference.difference:+.4f} "
                f"[{chain_interval.lower_bound:+.4f}, {chain_interval.upper_bound:+.4f}]"
            ),
        ),
    )
    return SuccessorVerdict(
        horizon_in_months=horizon_in_months,
        mean_skill=mean_skill,
        pooled_skill=pooled_skill,
        skill_lower_bound=skill_interval.lower_bound,
        skill_upper_bound=skill_interval.upper_bound,
        model_minus_chain=difference.difference,
        model_minus_chain_lower_bound=chain_interval.lower_bound,
        model_minus_chain_upper_bound=chain_interval.upper_bound,
        calibration=calibration,
        gates=gates,
    )


def evaluate_all_horizons(
    results: pd.DataFrame, horizons: Sequence[int], *, resamples: int, seed: int
) -> list[SuccessorVerdict]:
    return [
        evaluate_horizon(results, horizon, resamples=resamples, seed=seed) for horizon in horizons
    ]


def verdict_table(verdicts: Sequence[SuccessorVerdict]) -> pd.DataFrame:
    return pd.DataFrame([verdict.as_row() for verdict in verdicts])
