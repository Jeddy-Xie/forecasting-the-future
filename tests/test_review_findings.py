"""Regression tests for defects an adversarial review found after the first run.

Each one names the defect it pins, because a test whose reason is forgotten gets
deleted the next time it is inconvenient.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from economic_regime_forecasting.evaluation.calibration import (
    assess_calibration,
    cross_sectional_design_effect,
)
from economic_regime_forecasting.evaluation.verdict import (
    _mean_skill_over,
    _scoreable_columns,
    _skill_is_defined,
    evaluate_all_horizons,
)
from economic_regime_forecasting.models import gaussian_hidden_markov_model as hidden_markov
from economic_regime_forecasting.models.gaussian_hidden_markov_model import (
    GaussianHiddenMarkovModel,
)

# ------------------------------------------------------------------- bootstrap


def _panel_with_a_near_certain_indicator() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Two indicators, one of which is true on all but a handful of dates.

    This is the shape that broke the bootstrap: resamples that miss the handful of
    minority dates cannot score the near-certain indicator.
    """
    dates = 300
    generator = np.random.default_rng(20260908)
    ordinary_truth = np.clip(0.5 + 0.3 * np.sin(np.arange(dates) / 20.0), 0.05, 0.95)
    ordinary_outcome = (generator.uniform(size=dates) < ordinary_truth).astype("float64")

    near_certain = np.ones(dates)
    near_certain[:6] = 0.0

    predicted = np.column_stack([ordinary_truth, np.full(dates, 0.69)])
    realised = np.column_stack([ordinary_outcome, near_certain])
    climatology = np.column_stack(
        [np.full(dates, ordinary_outcome.mean()), np.full(dates, near_certain.mean())]
    )
    return predicted, realised, climatology


def test_a_skill_score_needs_the_outcome_to_vary() -> None:
    """A window where an event never happened has nothing to discriminate, so the
    ratio measures only how close the running base rate sat to a constant. On this
    project's own data the same model scored +0.867 and -8.981 on two such windows;
    neither number measures anything."""
    varying = np.array([1.0, 0.0, 1.0, 1.0])
    constant = np.ones(4)
    climatology = np.full(4, 0.4)
    assert _skill_is_defined(varying, climatology)
    assert not _skill_is_defined(constant, climatology)
    assert not _skill_is_defined(varying, np.array([1.0, 0.0, 1.0, 1.0]))


def test_the_bootstrap_refuses_a_resample_it_cannot_score_the_whole_set_on() -> None:
    """The defect: an indicator that loses its minority class on a resample used to
    drop out of that resample while staying in the point estimate, making the
    bootstrap distribution a mixture of two different quantities. A resample is now
    refused outright, and the bootstrap reports how many contributed."""
    predicted, realised, climatology = _panel_with_a_near_certain_indicator()
    columns = _scoreable_columns(predicted, realised, climatology)
    assert columns == [0, 1]

    without_the_minority_dates = np.arange(6, 300)
    with pytest.raises(ValueError, match="fixed indicator set cannot be scored"):
        _mean_skill_over(
            without_the_minority_dates,
            predicted,
            realised,
            climatology,
            columns,
            require_every_indicator=True,
        )


def test_a_sub_period_reports_how_many_indicators_it_could_score() -> None:
    """A sub-period is not a resample of one estimand. It is a description of a
    window, and the honest description of a window where an indicator never fired
    is the mean over the ones that did, with the count beside it."""
    predicted, realised, climatology = _panel_with_a_near_certain_indicator()
    value, contributing = _mean_skill_over(
        np.arange(6, 300),
        predicted,
        realised,
        climatology,
        [0, 1],
        require_every_indicator=False,
    )
    assert np.isfinite(value)
    assert contributing == 1


def test_a_window_with_nothing_scoreable_raises_rather_than_returning_a_number() -> None:
    predicted, realised, climatology = _panel_with_a_near_certain_indicator()
    all_constant = np.ones_like(realised)
    with pytest.raises(ValueError, match="no indicator has a defined skill score"):
        _mean_skill_over(
            np.arange(300),
            predicted,
            all_constant,
            climatology,
            [0, 1],
            require_every_indicator=False,
        )


def test_a_bad_indicator_cannot_vanish_from_the_interval() -> None:
    """End to end: the interval must reflect variation in skill, not the presence
    or absence of one indicator."""
    predicted, realised, climatology = _panel_with_a_near_certain_indicator()
    frame = pd.DataFrame(
        [
            {
                "indicator": name,
                "forecast_date": pd.Timestamp("1980-01-01") + pd.DateOffset(months=offset),
                "horizon_months": 12,
                "predicted_probability": float(predicted[offset, column]),
                "climatology_probability": float(climatology[offset, column]),
                "realised_outcome": float(realised[offset, column]),
                "composition": "point_in_time",
                "effective_sample_size": 100.0,
                "distance_to_stationary": 0.4,
                "regime_distribution": "0.5,0.5",
                "state_count": 2,
                "refit_date": pd.Timestamp("1980-01-01"),
                "configuration_hash": "abc",
                "seed": 1,
            }
            for column, name in enumerate(("ordinary", "near_certain"))
            for offset in range(300)
        ]
    )
    verdict = evaluate_all_horizons(frame, (12,), True, "regimes exist", seed=1)[0]
    assert verdict.skill_interval is not None
    # The near-certain indicator scores badly, so the whole interval must sit low.
    # Before the fix its absence from a fifth of resamples pushed the upper bound
    # above +0.5, which was the indicator vanishing rather than skill varying.
    assert verdict.skill_interval.upper_bound < 0.5


# ------------------------------------------------------------------- the model


def test_a_state_the_data_abandon_leaves_a_valid_transition_matrix() -> None:
    """The defect: a state whose responsibilities underflowed left a row of zeros,
    which is not a distribution, and the constructor's check then ended the whole
    fit instead of letting model selection see a collapsed state."""
    generator = np.random.default_rng(7)
    sample = np.concatenate(
        [generator.normal(-3.0, 0.4, size=(120, 1)), generator.normal(3.0, 0.4, size=(120, 1))]
    )
    stranded = GaussianHiddenMarkovModel(
        initial_distribution=np.array([0.5, 0.5, 0.0]),
        transition_matrix=np.array([[0.9, 0.05, 0.05], [0.05, 0.9, 0.05], [0.3, 0.3, 0.4]]),
        means=np.array([[-3.0], [3.0], [400.0]]),
        covariances=np.array([[[0.2]], [[0.2]], [[1e-4]]]),
    )
    log_emissions = stranded.log_emission_probabilities(sample)
    log_alpha = stranded._forward(log_emissions)
    log_beta = stranded._backward(log_emissions)
    from scipy.special import logsumexp

    updated = hidden_markov._maximisation_step(
        stranded,
        sample,
        log_emissions,
        log_alpha,
        log_beta,
        float(logsumexp(log_alpha[-1])),
        np.array([[1.0]]),
    )
    np.testing.assert_allclose(updated.transition_matrix.sum(axis=1), 1.0)
    assert (updated.transition_matrix >= 0.0).all()


def test_a_fit_survives_a_state_that_collapses() -> None:
    """Model selection must get to see an over-specified model and reject it, which
    it cannot do if the fit raises."""
    generator = np.random.default_rng(11)
    sample = np.concatenate(
        [generator.normal(-2.0, 0.3, size=(150, 1)), generator.normal(2.0, 0.3, size=(150, 1))]
    )
    fitted = hidden_markov.fit(sample, state_count=5, seed=3, restarts=3, max_iterations=120)
    np.testing.assert_allclose(fitted.transition_matrix.sum(axis=1), 1.0)
    assert fitted.state_count == 5


def test_the_reported_likelihood_belongs_to_the_model_that_is_returned() -> None:
    """The defect: on the iteration-cap path the loop ran one more maximisation
    step after the last likelihood evaluation, so the number in the manifest
    described a model that had been thrown away, and restarts were ranked on it."""
    generator = np.random.default_rng(13)
    sample = np.concatenate(
        [generator.normal(-1.5, 0.5, size=(200, 2)), generator.normal(1.5, 0.5, size=(200, 2))]
    )
    fitted = hidden_markov.fit(sample, state_count=3, seed=5, restarts=2, max_iterations=4)
    assert fitted.fit_report is not None
    assert not fitted.fit_report.converged
    assert fitted.fit_report.log_likelihood == pytest.approx(
        fitted.log_likelihood(sample), abs=1e-9
    )


def test_a_converged_fit_also_reports_its_own_likelihood() -> None:
    generator = np.random.default_rng(17)
    sample = np.concatenate(
        [generator.normal(-2.0, 0.4, size=(200, 1)), generator.normal(2.0, 0.4, size=(200, 1))]
    )
    fitted = hidden_markov.fit(sample, state_count=2, seed=5, restarts=3, max_iterations=400)
    assert fitted.fit_report is not None
    assert fitted.fit_report.converged
    assert fitted.fit_report.log_likelihood == pytest.approx(
        fitted.log_likelihood(sample), abs=1e-6
    )


def test_the_monotonicity_allowance_scales_with_the_ridge() -> None:
    """The defect: the guard asserted that expectation maximisation cannot lower
    the likelihood, but the covariance ridge means the update is not exactly the
    maximiser, so a small fall is a property of the regularisation. The guard now
    tolerates a fall the ridge could explain, and abandons one restart rather than
    the whole fit for anything larger."""
    allowance = hidden_markov._monotonicity_allowance(-1140.0)
    assert allowance > 1140.0 * hidden_markov.COVARIANCE_RIDGE
    assert allowance < 10.0


class _ScriptedLikelihood:
    """Stands in for a model whose log likelihood follows a script, one value per
    expectation step, so the loop's guard can be driven to an exact fall."""

    def __init__(self, script: list[float]) -> None:
        self.script = script
        self.steps = 0

    def log_emission_probabilities(self, observations: np.ndarray) -> np.ndarray:
        return np.zeros((len(observations), 1))

    def _forward(self, log_emissions: np.ndarray) -> np.ndarray:
        value = self.script[min(self.steps, len(self.script) - 1)]
        self.steps += 1
        return np.array([[value]])

    def _backward(self, log_emissions: np.ndarray) -> np.ndarray:
        return np.zeros((1, 1))

    def log_likelihood(self, observations: np.ndarray) -> float:
        return self.script[-1]


def _run_loop_on(script: list[float], monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(hidden_markov, "_maximisation_step", lambda model, *rest: model)
    return hidden_markov._run_expectation_maximisation(
        _ScriptedLikelihood(script),  # type: ignore[arg-type]
        np.zeros((5, 1)),
        max_iterations=50,
        tolerance=1e-6,
        pooled_covariance=np.eye(1),
    )


def test_the_loop_continues_through_a_fall_the_ridge_can_explain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The defect: ADR 0007 decided the allowance and a test pinned the function,
    but the loop kept a hard millionth and never called it. At a likelihood of
    -1000 the allowance is 1.0, so a fall of 0.999 is the ridge, not a bug: the
    loop carries on and converges, where before it raised. Found 2026-09-15 when
    the publication-aware look-ahead audit's injected-leak test crashed on a fall
    of 0.00133 at a likelihood of 583.9."""
    allowance = hidden_markov._monotonicity_allowance(-1000.0)
    assert allowance == pytest.approx(1.0)
    _, log_likelihood, iterations, converged = _run_loop_on(
        [-1000.0, -1000.999, -1000.999], monkeypatch
    )
    assert converged
    assert iterations == 3
    assert log_likelihood == -1000.999


def test_the_loop_still_raises_on_a_fall_beyond_the_allowance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The allowance is not widened: a fall of 1.001 from -1000 is past it."""
    with pytest.raises(hidden_markov.HiddenMarkovModelError, match="fell from"):
        _run_loop_on([-1000.0, -1001.001], monkeypatch)


# -------------------------------------------------------------- calibration


def test_correlated_indicators_widen_the_band_and_independent_ones_do_not() -> None:
    """The defect: correcting only the time axis left ten indicators forecast on
    the same date counting as ten independent observations, when at long horizons
    several of them are close to the same question.

    The correction measures the correlation rather than assuming it. Assuming the
    worst was tried first and rejected: it widens the band far enough that a
    completely reversed forecaster passes, and a check that cannot fail is useless.
    """
    generator = np.random.default_rng(19)
    dates = 400
    independent = generator.normal(size=(dates, 10))
    common = generator.normal(size=(dates, 1))
    correlated = 0.95 * common + 0.05 * generator.normal(size=(dates, 10))

    assert cross_sectional_design_effect(independent) == pytest.approx(1.0, abs=0.6)
    assert cross_sectional_design_effect(correlated) > 8.0


def test_a_single_series_has_no_cross_sectional_dependence() -> None:
    generator = np.random.default_rng(21)
    assert cross_sectional_design_effect(generator.normal(size=(100, 1))) == 1.0


def test_the_design_effect_never_claims_more_evidence_than_there_is() -> None:
    """Negatively correlated series would genuinely shrink the variance, but
    claiming a smaller standard error on an estimated correlation is the wrong
    direction to be adventurous in."""
    generator = np.random.default_rng(23)
    first = generator.normal(size=(300, 1))
    opposed = np.hstack([first, -first + 0.01 * generator.normal(size=(300, 1))])
    assert cross_sectional_design_effect(opposed) == 1.0


def test_a_wider_band_still_catches_a_reversed_forecaster() -> None:
    """Neither correction may disarm the check."""
    generator = np.random.default_rng(29)
    truth = generator.uniform(0.05, 0.95, size=20000)
    realised = (generator.uniform(size=20000) < truth).astype("float64")
    report = assess_calibration(
        1.0 - truth, realised, dependence_block_length=12, cross_sectional_design_effect=2.0
    )
    assert not report.is_monotone


def test_a_larger_design_effect_widens_every_bin() -> None:
    generator = np.random.default_rng(31)
    predicted = np.clip(np.repeat(np.linspace(0.05, 0.95, 200), 10), 0.01, 0.99)
    realised = (generator.uniform(size=2000) < predicted).astype("float64")
    narrow = assess_calibration(predicted, realised, dependence_block_length=12)
    wide = assess_calibration(
        predicted, realised, dependence_block_length=12, cross_sectional_design_effect=5.0
    )
    for widened, original in zip(wide.populated_bins, narrow.populated_bins, strict=True):
        assert widened.effective_count <= original.effective_count
        assert widened.standard_error >= original.standard_error
