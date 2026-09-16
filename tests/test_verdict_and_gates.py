"""The decision rule and the stage gates.

The decision rule is read from the committed pre-registration rather than
restated here, so a test that passed while someone quietly loosened a threshold
would be impossible: loosening it changes the file these tests load.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from economic_regime_forecasting import pipeline_gates
from economic_regime_forecasting.data.audit import SeriesAudit
from economic_regime_forecasting.data.cache import CacheStatistics
from economic_regime_forecasting.evaluation.verdict import (
    SHIP_BASE_RATE,
    SHIP_MODEL,
    VerdictError,
    compute_metrics,
    evaluate_all_horizons,
    load_decision_rule,
    metrics_table,
    verdict_table,
)

HORIZONS = (12, 60)


def _results(
    skill: float, months: int = 400, seed: int = 20260908, distance: float = 0.4
) -> pd.DataFrame:
    """Synthetic backtest results with a controllable amount of real skill.

    ``skill`` of zero makes the model quote the base rate exactly; one makes it
    quote the truth. Everything between interpolates, which lets a test ask for a
    model that should pass a gate and one that should not.
    """
    generator = np.random.default_rng(seed)
    dates = pd.date_range("1980-01-01", periods=months, freq="MS")
    rows = []
    for indicator in ("first_indicator", "second_indicator", "third_indicator"):
        truth = np.clip(0.5 + 0.35 * np.sin(np.arange(months) / 30.0), 0.05, 0.95)
        outcomes = (generator.uniform(size=months) < truth).astype("float64")
        base_rate = float(outcomes.mean())
        predicted = np.clip(skill * truth + (1.0 - skill) * base_rate, 0.01, 0.99)
        for horizon in HORIZONS:
            for position, stamp in enumerate(dates):
                rows.append(
                    {
                        "indicator": indicator,
                        "forecast_date": stamp,
                        "horizon_months": horizon,
                        "predicted_probability": float(predicted[position]),
                        "climatology_probability": base_rate,
                        "realised_outcome": float(outcomes[position]),
                        "composition": "point_in_time",
                        "effective_sample_size": 300.0,
                        "distance_to_stationary": distance,
                        "regime_distribution": "0.5,0.5",
                        "state_count": 2,
                        "refit_date": stamp,
                        "configuration_hash": "abc123",
                        "seed": 1,
                    }
                )
    return pd.DataFrame(rows)


def test_the_pre_registration_loads_and_names_all_five_gates() -> None:
    rule = load_decision_rule()
    assert set(rule["gates"]) == {"regimes_exist", "skill", "calibration", "robustness", "honesty"}
    assert rule["verdict_values"] == [SHIP_MODEL, SHIP_BASE_RATE]


def test_the_thresholds_are_the_ones_that_were_registered() -> None:
    """Pinned so that loosening a bar after seeing results fails a test rather
    than passing quietly."""
    gates = load_decision_rule()["gates"]
    assert gates["skill"]["minimum_mean_skill_score"] == 0.02
    assert gates["calibration"]["maximum_expected_calibration_error"] == 0.10
    assert gates["robustness"]["minimum_positive_sub_periods"] == 3
    assert gates["honesty"]["minimum_total_variation_distance"] == 0.05


def test_a_missing_pre_registration_is_refused_rather_than_defaulted(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(VerdictError, match="must exist and be committed"):
        load_decision_rule(tmp_path / "absent.json")


def test_metrics_are_computed_for_every_indicator_and_horizon() -> None:
    metrics = compute_metrics(_results(skill=0.8))
    assert len(metrics) == 3 * len(HORIZONS)
    table = metrics_table(metrics)
    assert {"brier_skill_score", "expected_calibration_error", "area_under_the_curve"} <= set(
        table.columns
    )
    assert (table["resolved_forecasts"] > 0).all()


def test_a_skilful_well_calibrated_model_ships() -> None:
    verdicts = evaluate_all_horizons(
        _results(skill=1.0), HORIZONS, True, "regimes beat one state", seed=1
    )
    for item in verdicts:
        assert item.ships_model, (item.horizon_in_months, item.failing_gates)
        assert item.verdict == SHIP_MODEL


def test_a_model_with_no_skill_ships_the_base_rate() -> None:
    verdicts = evaluate_all_horizons(
        _results(skill=0.0), HORIZONS, True, "regimes beat one state", seed=1
    )
    for item in verdicts:
        assert not item.ships_model
        assert "skill" in item.failing_gates


def test_a_model_whose_projection_has_converged_fails_the_honesty_gate() -> None:
    """Even a model that scores well must not be presented as a prediction once
    its projection is indistinguishable from the base rate."""
    converged = _results(skill=1.0, distance=0.01)
    verdicts = evaluate_all_horizons(converged, HORIZONS, True, "regimes exist", seed=1)
    for item in verdicts:
        assert "honesty" in item.failing_gates
        assert item.verdict == SHIP_BASE_RATE


def test_failing_the_regimes_gate_fails_every_horizon() -> None:
    verdicts = evaluate_all_horizons(_results(skill=1.0), HORIZONS, False, "one state wins", seed=1)
    assert all("regimes exist" in item.failing_gates for item in verdicts)


def test_every_verdict_names_the_gate_that_decided_it() -> None:
    verdicts = evaluate_all_horizons(_results(skill=0.0), HORIZONS, True, "regimes exist", seed=1)
    for item in verdicts:
        assert item.failing_gates
        for gate in item.gates:
            assert gate.evidence
            assert gate.requirement


def test_the_skill_interval_reports_its_effective_independent_sample_size() -> None:
    """Four hundred monthly forecasts at a five-year horizon are worth about seven
    independent observations, and the reader must be told."""
    verdicts = evaluate_all_horizons(_results(skill=0.9), HORIZONS, True, "regimes exist", seed=1)
    five_year = next(item for item in verdicts if item.horizon_in_months == 60)
    assert five_year.skill_interval is not None
    assert five_year.skill_interval.effective_independent_sample_size == pytest.approx(
        400 / 60, rel=0.01
    )
    assert five_year.skill_interval.block_length == 60


def test_the_verdict_table_has_a_row_per_horizon() -> None:
    verdicts = evaluate_all_horizons(_results(skill=0.5), HORIZONS, True, "regimes exist", seed=1)
    table = verdict_table(verdicts)
    assert list(table["horizon_months"]) == list(HORIZONS)
    assert set(table["verdict"]) <= {SHIP_MODEL, SHIP_BASE_RATE}


def test_a_horizon_the_sample_cannot_reach_is_reported() -> None:
    unresolvable = _results(skill=0.5)
    unresolvable["realised_outcome"] = np.nan
    with pytest.raises(VerdictError, match="does not reach far enough"):
        evaluate_all_horizons(unresolvable, (12,), True, "regimes exist", seed=1)


# ------------------------------------------------------------- stage gates


def _audit(name: str, start_matches: bool = True, observations: int = 900) -> SeriesAudit:
    from datetime import date

    return SeriesAudit(
        name=name,
        series_id=name.upper(),
        role="growth",
        frequency="monthly",
        units="index",
        transform="level",
        declared_start=date(1950, 1, 1),
        observed_start=date(1950, 1, 1) if start_matches else date(1960, 1, 1),
        observed_end=date(2026, 8, 1),
        observation_count=observations,
        missing_value_count=0,
        publication_lag_days=45,
        is_revised=True,
    )


def test_gate_one_passes_when_the_data_matches_the_registry(
    three_dimension_registry,
) -> None:  # type: ignore[no-untyped-def]
    audits = [_audit(item.name) for item in three_dimension_registry.series]
    statistics = CacheStatistics(hits=3, misses=0, writes=0)
    report = pipeline_gates.gate_one_data(three_dimension_registry, audits, statistics)
    assert report.passed
    assert "PASS" in report.describe()


def test_gate_one_fails_when_a_declared_start_date_is_wrong(
    three_dimension_registry,
) -> None:  # type: ignore[no-untyped-def]
    audits = [_audit(item.name) for item in three_dimension_registry.series]
    audits[1] = _audit(audits[1].name, start_matches=False)
    report = pipeline_gates.gate_one_data(three_dimension_registry, audits, CacheStatistics(hits=3))
    assert not report.passed


def test_gate_one_fails_when_a_second_pass_is_not_served_from_cache(
    three_dimension_registry,
) -> None:  # type: ignore[no-untyped-def]
    """A cache that re-fetches is not a cache, and the audit would be measuring
    the network rather than the stored data."""
    audits = [_audit(item.name) for item in three_dimension_registry.series]
    report = pipeline_gates.gate_one_data(
        three_dimension_registry, audits, CacheStatistics(hits=2, misses=1)
    )
    assert not report.passed


def test_gate_four_catches_a_run_stitched_from_two_configurations() -> None:
    results = _results(skill=0.5)
    results.loc[0, "configuration_hash"] = "different"
    report = pipeline_gates.gate_four_backtest(results)
    assert not report.passed


def test_gate_four_passes_a_clean_run() -> None:
    assert pipeline_gates.gate_four_backtest(_results(skill=0.5)).passed


def test_gate_five_passes_when_every_horizon_reached_a_verdict() -> None:
    verdicts = evaluate_all_horizons(_results(skill=1.0), HORIZONS, True, "regimes exist", seed=1)
    report = pipeline_gates.gate_five_evaluation(verdict_table(verdicts), HORIZONS)
    assert report.passed


def test_gate_five_fails_when_a_horizon_is_missing() -> None:
    verdicts = evaluate_all_horizons(_results(skill=1.0), (12,), True, "regimes exist", seed=1)
    report = pipeline_gates.gate_five_evaluation(verdict_table(verdicts), HORIZONS)
    assert not report.passed


def test_gate_two_can_be_re_asserted_from_a_single_chain_run_s_own_table() -> None:
    """The artifacts a run wrote are enough to ask gate 2 again, without the run."""
    from economic_regime_forecasting.models.gaussian_hidden_markov_model import (
        GaussianHiddenMarkovModel,
    )

    model = GaussianHiddenMarkovModel(
        initial_distribution=np.array([0.6, 0.4]),
        transition_matrix=np.array([[0.9, 0.1], [0.2, 0.8]]),
        means=np.array([[-1.0], [1.0]]),
        covariances=np.array([[[0.4]], [[0.6]]]),
    )
    sweep = pd.DataFrame(
        {
            "states": [1, 2],
            "free_parameters": [2, 7],
            "training_log_likelihood": [-900.0, -700.0],
            "bayesian_information_criterion": [1810.0, 1450.0],
            "held_out_log_likelihood_per_month": [-4.3, -3.1],
            "smallest_population_share": [1.0, 0.42],
            "shortest_expected_duration_months": [1e12, 9.0],
            "second_eigenvalue_modulus": [0.0, 0.7],
            "admissible": [True, True],
        }
    )
    path = np.array([0] * 60 + [1] * 60)

    report = pipeline_gates.gate_two_from_tables(sweep, model, path, len(path))
    assert report.number == 2
    assert len(report.checks) == 5
    assert report.checks[0].passed
    assert "2 states -3.1000" in report.checks[0].evidence


def test_a_gate_report_renders_every_check_with_its_evidence() -> None:
    report = pipeline_gates.gate_four_backtest(_results(skill=0.5))
    rendered = report.describe()
    for check in report.checks:
        assert check.requirement in rendered
        assert check.evidence in rendered
    assert len(report.table()) == len(report.checks)
