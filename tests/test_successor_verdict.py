"""Rule 0007's verdict and the calibration test it uses, on synthetic forecasts."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from economic_regime_forecasting.evaluation import successor_verdict
from economic_regime_forecasting.evaluation.calibration import (
    RecalibrationTest,
    assess_recalibration,
    fit_logistic_recalibration,
)
from economic_regime_forecasting.evaluation.scoring import ScoringError


def _calibrated(count: int, seed: int = 1) -> tuple[np.ndarray, np.ndarray]:
    generator = np.random.default_rng(seed)
    probability = generator.uniform(0.05, 0.95, size=count)
    return probability, (generator.uniform(size=count) < probability).astype(float)


def test_a_calibrated_forecaster_needs_no_shift_and_no_stretch() -> None:
    predicted, realised = _calibrated(20000)
    intercept, slope = fit_logistic_recalibration(predicted, realised)
    assert intercept == pytest.approx(0.0, abs=0.05)
    assert slope == pytest.approx(1.0, abs=0.05)


def test_an_overconfident_forecaster_is_stretched_back() -> None:
    predicted, realised = _calibrated(20000)
    log_odds = np.log(predicted / (1 - predicted))
    overconfident = 1.0 / (1.0 + np.exp(-2.0 * log_odds))
    _, slope = fit_logistic_recalibration(overconfident, realised)
    assert slope == pytest.approx(0.5, abs=0.05)


def test_outcomes_that_never_vary_cannot_be_recalibrated() -> None:
    with pytest.raises(ScoringError, match="do not vary"):
        fit_logistic_recalibration(np.full(10, 0.3), np.zeros(10))


def _test(intercept_interval: tuple[float, float], uses_intercept: bool) -> RecalibrationTest:
    return RecalibrationTest(
        intercept=0.0,
        slope=1.0,
        intercept_interval=intercept_interval,
        slope_interval=(0.8, 1.2),
        confidence_level=0.95,
        block_length=12,
        resamples_used=100,
        uses_intercept=uses_intercept,
    )


def test_the_fallback_reads_the_slope_alone() -> None:
    assert not _test((0.1, 0.3), uses_intercept=True).calibrated
    assert _test((0.1, 0.3), uses_intercept=False).calibrated
    assert _test((-0.1, 0.3), uses_intercept=True).calibrated


def test_the_bootstrap_resamples_whole_dates() -> None:
    predicted, realised = _calibrated(3000, seed=4)
    test = assess_recalibration(
        predicted.reshape(300, 10),
        realised.reshape(300, 10),
        block_length=12,
        resamples=100,
        seed=1,
    )
    assert test.slope_interval[0] < test.slope < test.slope_interval[1]
    assert test.block_length == 12
    assert "slope" in test.describe()


def _results(model_skill: float, chain_skill: float) -> pd.DataFrame:
    generator = np.random.default_rng(9)
    dates = pd.date_range("1990-01-01", periods=240, freq="MS")
    rows = []
    for indicator in ("first", "second", "third"):
        truth = np.clip(0.45 + 0.35 * np.sin(np.arange(len(dates)) / 9.0), 0.05, 0.95)
        outcome = (generator.uniform(size=len(dates)) < truth).astype(float)
        base = float(outcome.mean())
        for position, stamp in enumerate(dates):
            rows.append(
                {
                    "indicator": indicator,
                    "forecast_date": stamp,
                    "horizon_months": 12,
                    "predicted_probability": model_skill * truth[position]
                    + (1 - model_skill) * base,
                    "condition_chain_probability": chain_skill * truth[position]
                    + (1 - chain_skill) * base,
                    "climatology_probability": base,
                    "model_sample_climatology_probability": base,
                    "realised_outcome": outcome[position],
                    "distance_to_stationary": 0.3,
                }
            )
    return pd.DataFrame(rows)


def test_a_model_that_beats_the_benchmark_and_the_chain_passes_skill_and_the_chain_gate() -> None:
    verdict = successor_verdict.evaluate_horizon(_results(0.9, 0.2), 12, resamples=200, seed=1)
    gates = {gate.name: gate.passed for gate in verdict.gates}
    assert gates["skill"] and gates["not beaten by the chain"] and gates["honesty"]
    assert verdict.model_minus_chain > 0
    assert set(gates) == {
        "skill",
        "calibration",
        "robustness",
        "honesty",
        "not beaten by the chain",
    }


def test_a_model_the_chain_beats_ships_the_base_rate_under_0007() -> None:
    verdict = successor_verdict.evaluate_horizon(_results(0.3, 0.95), 12, resamples=200, seed=1)
    assert "not beaten by the chain" in verdict.failing_gates
    assert verdict.verdict == "SHIP BASE RATE"
    assert "ships R1" in verdict.describe()


def test_results_without_the_reference_columns_are_refused() -> None:
    frame = _results(0.9, 0.2).drop(columns=["condition_chain_probability"])
    with pytest.raises(successor_verdict.SuccessorVerdictError, match="reference columns"):
        successor_verdict.evaluate_horizon(frame, 12, resamples=50, seed=1)
