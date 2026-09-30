"""Measurement 0010: skill at every horizon, read by the rule registered before it ran."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from economic_regime_forecasting.evaluation import skill_by_horizon as curve
from economic_regime_forecasting.evaluation import verdict as verdict_module
from economic_regime_forecasting.evaluation.skill_by_horizon import HorizonSkill


def _skill(horizon: int, mean: float, lower: float, dates: int = 378) -> HorizonSkill:
    return HorizonSkill(
        horizon_in_months=horizon,
        forecaster="regime model",
        mean_skill=mean,
        lower_bound=lower,
        upper_bound=mean + 0.1,
        pooled_skill=mean,
        block_length=curve.block_length_for(horizon),
        dates=dates,
        scoreable_indicators=10,
    )


def test_the_block_is_the_horizon_but_never_shorter_than_a_year() -> None:
    assert curve.block_length_for(1) == 12
    assert curve.block_length_for(12) == 12
    assert curve.block_length_for(60) == 60


def test_carrying_skill_is_the_skill_gate_applied_at_one_horizon() -> None:
    assert _skill(12, 0.03, 0.001).carries_skill
    assert not _skill(12, 0.019, 0.001).carries_skill
    assert not _skill(12, 0.5, 0.0).carries_skill


def test_the_ship_the_average_horizon_is_the_last_horizon_carrying_skill() -> None:
    """As registered: the first horizon after which skill fails at every longer one.
    A gap in the middle does not end it; a later return does extend it."""
    skills = [
        _skill(1, 0.3, 0.1),
        _skill(2, 0.3, 0.1),
        _skill(3, 0.01, -0.1),
        _skill(4, 0.3, 0.1),
        _skill(5, 0.01, -0.1),
    ]
    assert curve.ship_the_average_horizon(skills) == 4
    assert curve.skill_unbroken_from_one_month(skills) == 2
    assert curve.ship_the_average_horizon([_skill(1, 0.0, -0.1)]) == 0


def test_a_horizon_below_five_and_a_half_independent_observations_is_uninformative() -> None:
    assert _skill(60, 0.1, 0.01, dates=330).informative
    assert not _skill(61, 0.1, 0.01, dates=330).informative


def _results(horizons: tuple[int, ...]) -> pd.DataFrame:
    generator = np.random.default_rng(3)
    dates = pd.date_range("1990-01-01", periods=150, freq="MS")
    rows = []
    for indicator in ("first", "second", "third"):
        for horizon in horizons:
            truth = np.clip(0.4 + 0.3 * np.sin(np.arange(len(dates)) / (5.0 + horizon)), 0.05, 0.95)
            outcome = (generator.uniform(size=len(dates)) < truth).astype(float)
            for position, stamp in enumerate(dates):
                resolved = position < len(dates) - horizon
                rows.append(
                    {
                        "indicator": indicator,
                        "forecast_date": stamp,
                        "horizon_months": horizon,
                        "predicted_probability": float(truth[position]),
                        "condition_chain_probability": float(np.clip(truth[position] + 0.1, 0, 1)),
                        "climatology_probability": 0.45,
                        "model_sample_climatology_probability": 0.4,
                        "realised_outcome": float(outcome[position]) if resolved else np.nan,
                        "distance_to_stationary": 0.5 / horizon,
                    }
                )
    return pd.DataFrame(rows)


def test_at_a_verdict_horizon_the_curve_is_the_verdicts_own_statistic() -> None:
    results = _results((12,))
    matrices = curve.matrices_at(results, 12, "predicted_probability", "climatology_probability")
    scored = curve.score_forecaster(matrices, 12, "regime model", resamples=200, seed=20260908)
    rule = verdict_module.load_decision_rule()
    rule["gates"]["skill"]["bootstrap"]["resamples"] = 200
    verdict = verdict_module.evaluate_horizon(results, 12, True, "stubbed", rule, seed=20260908)
    assert scored.mean_skill == verdict.mean_brier_skill_score
    skill_gate = next(gate for gate in verdict.gates if gate.name == "skill")
    assert f"{scored.lower_bound:+.4f}" in skill_gate.evidence


def test_how_many_horizons_run_at_once_changes_no_number() -> None:
    results = _results((1, 2, 12))
    serial = curve.measure(results, (1, 2, 12), resamples=100, seed=20260908, workers=1)
    parallel = curve.measure(results, (1, 2, 12), resamples=100, seed=20260908, workers=2)
    pd.testing.assert_frame_equal(serial.skill_table(), parallel.skill_table())
    pd.testing.assert_frame_equal(serial.difference_table(), parallel.difference_table())
    assert {row["benchmark"] for row in serial.readings()} == {"series-start", "model-sample"}
    assert serial.honesty_crossing(threshold=0.05) == 12
    assert "ship the average after" in serial.describe()


def test_a_curve_with_no_resolved_forecast_at_a_horizon_says_so() -> None:
    results = _results((12,))
    results["realised_outcome"] = np.nan
    with pytest.raises(curve.SkillByHorizonError, match="does not reach"):
        curve.matrices_at(results, 12, "predicted_probability", "climatology_probability")
