"""The model is written out here, so it is checked against answers computed
another way.

The forward algorithm is checked against brute-force enumeration of every state
path, which is tractable for a short sequence and is a genuinely independent
computation of the same quantity. Expectation maximisation is checked against its own
defining property, that the likelihood never falls. And the filtered
probabilities get their own test for the property the whole project rests on:
they do not change when the future changes.
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from economic_regime_forecasting.models import gaussian_hidden_markov_model as hidden_markov
from economic_regime_forecasting.models.gaussian_hidden_markov_model import (
    GaussianHiddenMarkovModel,
    HiddenMarkovModelError,
)

INITIAL = np.array([0.6, 0.4])
TRANSITIONS = np.array([[0.9, 0.1], [0.2, 0.8]])
MEANS = np.array([[0.0], [3.0]])
COVARIANCES = np.array([[[1.0]], [[1.0]]])
OBSERVATIONS = np.array([[0.1], [0.2], [3.1], [2.9], [0.0]])


def _model() -> GaussianHiddenMarkovModel:
    return GaussianHiddenMarkovModel(INITIAL, TRANSITIONS, MEANS, COVARIANCES)


def _normal_density(value: float, mean: float, variance: float) -> float:
    return float(np.exp(-0.5 * (value - mean) ** 2 / variance) / np.sqrt(2.0 * np.pi * variance))


def _likelihood_by_enumerating_every_path(observations: np.ndarray) -> float:
    """Sum over all 2^T state paths. Independent of the forward algorithm."""
    months = observations.shape[0]
    total = 0.0
    for path in itertools.product(range(2), repeat=months):
        probability = INITIAL[path[0]]
        for month in range(months):
            if month > 0:
                probability *= TRANSITIONS[path[month - 1], path[month]]
            probability *= _normal_density(
                float(observations[month, 0]), float(MEANS[path[month], 0]), 1.0
            )
        total += probability
    return total


def test_the_forward_algorithm_agrees_with_enumerating_every_path() -> None:
    expected = np.log(_likelihood_by_enumerating_every_path(OBSERVATIONS))
    assert _model().log_likelihood(OBSERVATIONS) == pytest.approx(expected, rel=1e-10)


def test_filtered_probabilities_at_a_month_ignore_everything_after_it() -> None:
    """The property the entire backtest rests on.

    Appending observations must leave every earlier filtered probability
    untouched. Smoothed probabilities fail this test, which is why they are
    forbidden in a backtest and why the two have deliberately different names.
    """
    model = _model()
    short = model.filtered_state_probabilities(OBSERVATIONS[:3])
    long = model.filtered_state_probabilities(OBSERVATIONS)
    np.testing.assert_allclose(short, long[:3], rtol=1e-12)


def test_smoothed_probabilities_do_change_when_the_future_changes() -> None:
    """The mirror image of the test above, stated so the difference is on record."""
    model = _model()
    short = model.smoothed_state_probabilities(OBSERVATIONS[:3])
    long = model.smoothed_state_probabilities(OBSERVATIONS)
    assert not np.allclose(short, long[:3], atol=1e-6)


def test_every_state_distribution_is_a_distribution() -> None:
    model = _model()
    for probabilities in (
        model.filtered_state_probabilities(OBSERVATIONS),
        model.smoothed_state_probabilities(OBSERVATIONS),
    ):
        np.testing.assert_allclose(probabilities.sum(axis=1), 1.0, rtol=1e-12)
        assert (probabilities >= 0.0).all()


def test_viterbi_finds_the_path_that_maximises_the_joint_probability() -> None:
    """Checked against enumeration again, on the same short sequence."""
    model = _model()
    best_path, best_probability = None, -1.0
    for path in itertools.product(range(2), repeat=OBSERVATIONS.shape[0]):
        probability = INITIAL[path[0]]
        for month in range(OBSERVATIONS.shape[0]):
            if month > 0:
                probability *= TRANSITIONS[path[month - 1], path[month]]
            probability *= _normal_density(
                float(OBSERVATIONS[month, 0]), float(MEANS[path[month], 0]), 1.0
            )
        if probability > best_probability:
            best_path, best_probability = path, probability
    np.testing.assert_array_equal(model.most_likely_state_path(OBSERVATIONS), np.array(best_path))


def test_the_stationary_distribution_is_the_one_the_chain_settles_on() -> None:
    """For this two-state chain the answer is known in closed form: the stationary
    probability of the first state is 0.2 over 0.1 plus 0.2, which is two thirds."""
    stationary = _model().stationary_distribution()
    np.testing.assert_allclose(stationary, np.array([2 / 3, 1 / 3]), rtol=1e-10)
    np.testing.assert_allclose(stationary @ TRANSITIONS, stationary, rtol=1e-10)


def test_the_second_eigenvalue_modulus_matches_its_closed_form() -> None:
    """A two-state chain's second eigenvalue is one minus the two switching
    probabilities, here one minus 0.1 minus 0.2."""
    assert _model().second_largest_eigenvalue_modulus() == pytest.approx(0.7, rel=1e-12)


def test_expected_durations_are_one_over_the_escape_probability() -> None:
    np.testing.assert_allclose(_model().expected_state_durations(), np.array([10.0, 5.0]))


def test_projecting_far_enough_ahead_reaches_the_stationary_distribution() -> None:
    model = _model()
    far = model.project_state_distribution(np.array([1.0, 0.0]), 500)
    np.testing.assert_allclose(far, model.stationary_distribution(), atol=1e-10)


def test_projecting_zero_months_changes_nothing() -> None:
    start = np.array([0.3, 0.7])
    np.testing.assert_allclose(_model().project_state_distribution(start, 0), start)


def test_a_transition_matrix_whose_rows_do_not_sum_to_one_is_refused() -> None:
    with pytest.raises(HiddenMarkovModelError, match="rows must each sum to one"):
        GaussianHiddenMarkovModel(INITIAL, np.array([[0.9, 0.2], [0.2, 0.8]]), MEANS, COVARIANCES)


def test_a_mismatched_observation_width_is_reported() -> None:
    with pytest.raises(HiddenMarkovModelError, match="dimensions"):
        _model().log_likelihood(np.array([[0.1, 0.2]]))


def test_the_parameter_count_is_the_one_the_criterion_penalises() -> None:
    """Two states over one dimension: one initial, two transition rows at one free
    parameter each, two means, two variances. That is seven."""
    assert _model().free_parameter_count == 7


def test_a_model_survives_a_round_trip_through_a_dictionary() -> None:
    original = _model()
    restored = GaussianHiddenMarkovModel.from_dictionary(original.to_dictionary())
    np.testing.assert_allclose(restored.transition_matrix, original.transition_matrix)
    np.testing.assert_allclose(restored.means, original.means)
    assert restored.log_likelihood(OBSERVATIONS) == pytest.approx(
        original.log_likelihood(OBSERVATIONS)
    )


# --------------------------------------------------------------------- fitting


def _simulated_two_regime_sample(months: int = 400, seed: int = 20260908) -> np.ndarray:
    generator = np.random.default_rng(seed)
    transitions = np.array([[0.97, 0.03], [0.05, 0.95]])
    means = np.array([[1.0, -0.5], [-1.5, 1.0]])
    state, sample = 0, []
    for _ in range(months):
        state = int(generator.choice(2, p=transitions[state]))
        sample.append(generator.normal(means[state], 0.5))
    return np.array(sample)


def test_fitting_recovers_parameters_it_generated_from() -> None:
    sample = _simulated_two_regime_sample()
    fitted = hidden_markov.fit(sample, state_count=2, seed=11, restarts=8)
    recovered = np.sort(fitted.means[:, 0])
    np.testing.assert_allclose(recovered, np.sort(np.array([1.0, -1.5])), atol=0.3)
    assert np.all(np.diag(fitted.transition_matrix) > 0.85)


def test_the_same_seed_gives_a_bit_identical_model() -> None:
    """Determinism is a shipping requirement, not a nicety."""
    sample = _simulated_two_regime_sample(months=200)
    first = hidden_markov.fit(sample, state_count=2, seed=5, restarts=4)
    second = hidden_markov.fit(sample, state_count=2, seed=5, restarts=4)
    np.testing.assert_array_equal(first.transition_matrix, second.transition_matrix)
    np.testing.assert_array_equal(first.means, second.means)
    assert first.fit_report is not None
    assert first.fit_report.log_likelihood == second.fit_report.log_likelihood  # type: ignore[union-attr]


def test_a_different_seed_explores_a_different_starting_point() -> None:
    sample = _simulated_two_regime_sample(months=200)
    first = hidden_markov.fit(sample, state_count=2, seed=5, restarts=2)
    second = hidden_markov.fit(sample, state_count=2, seed=6, restarts=2)
    assert first.fit_report is not None and second.fit_report is not None
    assert first.fit_report.log_likelihood_by_restart != second.fit_report.log_likelihood_by_restart


def test_more_restarts_never_find_a_worse_optimum() -> None:
    """Restarts exist because a single start regularly lands far from the best
    solution. This pins that the best-of rule actually keeps the best."""
    sample = _simulated_two_regime_sample(months=250)
    few = hidden_markov.fit(sample, state_count=3, seed=3, restarts=2)
    many = hidden_markov.fit(sample, state_count=3, seed=3, restarts=10)
    assert few.fit_report is not None and many.fit_report is not None
    assert many.fit_report.log_likelihood >= few.fit_report.log_likelihood - 1e-9


def test_the_likelihood_never_falls_across_iterations() -> None:
    """Expectation maximisation guarantees this. A fall would be a bug in the
    update equations, so the fit raises rather than returning a plausible number."""
    sample = _simulated_two_regime_sample(months=150)
    fitted = hidden_markov.fit(sample, state_count=3, seed=9, restarts=3, max_iterations=60)
    assert fitted.fit_report is not None
    assert np.isfinite(fitted.fit_report.log_likelihood)


def test_a_single_state_model_is_just_a_gaussian() -> None:
    """The sweep needs this case in order to ask whether regimes exist at all."""
    sample = _simulated_two_regime_sample(months=200)
    fitted = hidden_markov.fit(sample, state_count=1, seed=2, restarts=2)
    np.testing.assert_allclose(fitted.transition_matrix, np.array([[1.0]]))
    np.testing.assert_allclose(fitted.means[0], sample.mean(axis=0), atol=1e-6)
    assert fitted.second_largest_eigenvalue_modulus() == 0.0


def test_fitting_more_states_than_months_is_refused() -> None:
    with pytest.raises(HiddenMarkovModelError, match="more observations than states"):
        hidden_markov.fit(np.zeros((3, 2)), state_count=5, seed=1, restarts=1)


def test_non_finite_observations_are_refused_rather_than_silently_dropped() -> None:
    sample = _simulated_two_regime_sample(months=60)
    sample[10, 0] = np.nan
    with pytest.raises(HiddenMarkovModelError, match="non-finite"):
        hidden_markov.fit(sample, state_count=2, seed=1, restarts=1)


def test_a_richer_model_always_fits_the_training_data_at_least_as_well() -> None:
    sample = _simulated_two_regime_sample(months=300)
    two = hidden_markov.fit(sample, state_count=2, seed=4, restarts=6)
    three = hidden_markov.fit(sample, state_count=3, seed=4, restarts=6)
    assert three.log_likelihood(sample) >= two.log_likelihood(sample) - 1e-6


# --------------------------------------------------- D1: the sticky Dirichlet prior


def test_deriving_the_sticky_prior_matches_the_pre_registration() -> None:
    """The pre-registration's own worked examples, quoted verbatim in
    proving/experiments/0002-research-slate-2026-09/experiment.json: at K = 5,
    beta = 0.5 and kappa = 57.5; at K = 6, beta = 0.4 and kappa = 57.6."""
    beta5, kappa5 = hidden_markov.derive_sticky_dirichlet_prior(
        state_count=5, prior_mean_visit_months=30.0, prior_row_strength=60.0
    )
    assert beta5 == pytest.approx(0.5)
    assert kappa5 == pytest.approx(57.5)

    beta6, kappa6 = hidden_markov.derive_sticky_dirichlet_prior(
        state_count=6, prior_mean_visit_months=30.0, prior_row_strength=60.0
    )
    assert beta6 == pytest.approx(0.4)
    assert kappa6 == pytest.approx(57.6)


def test_a_one_state_chain_derives_no_prior() -> None:
    """A single state has no off-diagonal transition to regularise, and the
    derivation divides by K - 1; this must not raise or silently divide by zero."""
    beta, kappa = hidden_markov.derive_sticky_dirichlet_prior(
        state_count=1, prior_mean_visit_months=30.0, prior_row_strength=60.0
    )
    assert (beta, kappa) == (0.0, 0.0)


def test_zero_row_strength_derives_no_prior_whatever_the_mean_visit_is() -> None:
    beta, kappa = hidden_markov.derive_sticky_dirichlet_prior(
        state_count=6, prior_mean_visit_months=30.0, prior_row_strength=0.0
    )
    assert (beta, kappa) == (0.0, 0.0)


def test_the_dirichlet_posterior_mean_matches_its_closed_form() -> None:
    """A[k, j] = (n[k, j] + beta + kappa * 1{j = k}) / (n[k] + K*beta + kappa),
    checked against counts worked out by hand for a 2-state row."""
    counts = np.array([[8.0, 2.0], [1.0, 9.0]])
    beta, kappa = 0.5, 57.5
    matrix = hidden_markov._dirichlet_posterior_mean_transition_matrix(counts, beta, kappa)
    denominator = 10.0 + 2 * beta + kappa
    expected = np.array(
        [
            [(8.0 + beta + kappa) / denominator, (2.0 + beta) / denominator],
            [(1.0 + beta) / denominator, (9.0 + beta + kappa) / denominator],
        ]
    )
    np.testing.assert_allclose(matrix, expected, rtol=1e-12)
    np.testing.assert_allclose(matrix.sum(axis=1), 1.0, rtol=1e-12)


def test_a_positive_row_strength_never_produces_an_exact_zero() -> None:
    """The defect D1 raises: plain Baum-Welch sets some transitions to exactly
    zero from a handful of observed switches. A row with a transition NEVER
    observed (count 0) is the sharpest case, and the posterior mean must still
    come out strictly positive there."""
    counts = np.array([[20.0, 0.0, 0.0], [0.0, 15.0, 0.0], [0.0, 0.0, 10.0]])
    matrix = hidden_markov._dirichlet_posterior_mean_transition_matrix(counts, beta=0.5, kappa=57.5)
    assert (matrix > 0.0).all()
    np.testing.assert_allclose(matrix.sum(axis=1), 1.0, rtol=1e-12)

    # The same counts with no prior reproduce the zero the defect describes.
    unregularised = hidden_markov._dirichlet_posterior_mean_transition_matrix(
        counts, beta=0.0, kappa=0.0
    )
    assert (unregularised == 0.0).any()


def test_beta_and_kappa_both_zero_reproduces_the_unregularised_fit_bit_for_bit() -> None:
    """The arm's own required check (proving/experiments/0002-research-slate-2026-09
    /experiment.json, A1's ``required_check``): beta = 0 and kappa = 0 must
    reproduce the fit with no prior argument at all, to the bit, not to a
    tolerance."""
    sample = _simulated_two_regime_sample(months=300)
    without_the_argument = hidden_markov.fit(sample, state_count=3, seed=7, restarts=5)
    with_zero_prior = hidden_markov.fit(
        sample,
        state_count=3,
        seed=7,
        restarts=5,
        transition_prior_beta=0.0,
        transition_prior_kappa=0.0,
    )
    np.testing.assert_array_equal(
        with_zero_prior.transition_matrix, without_the_argument.transition_matrix
    )
    np.testing.assert_array_equal(with_zero_prior.means, without_the_argument.means)
    np.testing.assert_array_equal(with_zero_prior.covariances, without_the_argument.covariances)
    assert with_zero_prior.fit_report is not None and without_the_argument.fit_report is not None
    assert (
        with_zero_prior.fit_report.log_likelihood == without_the_argument.fit_report.log_likelihood
    )


def test_a_sticky_prior_fit_has_no_exact_zero_transitions() -> None:
    """End to end, not just the closed-form M-step: fitting with the
    pre-registered hyperparameters on a sample sparse enough to abandon a state
    under plain Baum-Welch must still come out with every entry strictly
    positive."""
    sample = _simulated_two_regime_sample(months=250)
    beta, kappa = hidden_markov.derive_sticky_dirichlet_prior(
        state_count=4, prior_mean_visit_months=30.0, prior_row_strength=60.0
    )
    fitted = hidden_markov.fit(
        sample,
        state_count=4,
        seed=13,
        restarts=4,
        transition_prior_beta=beta,
        transition_prior_kappa=kappa,
    )
    assert (fitted.transition_matrix > 0.0).all()


def test_the_prior_log_density_is_exactly_zero_with_no_prior() -> None:
    """So the monitored quantity the monotonicity guard watches reduces to the
    plain log likelihood, bit for bit, when beta and kappa are both zero."""
    matrix = np.array([[0.9, 0.1], [0.2, 0.8]])
    assert hidden_markov._log_transition_prior_density(matrix, 0.0, 0.0) == 0.0


def test_the_prior_log_density_falls_as_a_row_moves_away_from_its_mode() -> None:
    """A sanity check on the sign, not the exact value: with kappa > 0 favouring
    the diagonal, a row that has moved probability mass off the diagonal must
    score a lower log density than one still at the prior's own mode."""
    near_mode = np.array([[0.95, 0.05], [0.05, 0.95]])
    away_from_mode = np.array([[0.5, 0.5], [0.5, 0.5]])
    beta, kappa = 0.5, 57.5
    density_near = hidden_markov._log_transition_prior_density(near_mode, beta, kappa)
    density_away = hidden_markov._log_transition_prior_density(away_from_mode, beta, kappa)
    assert density_near > density_away


def test_a_sticky_prior_fit_still_never_lets_its_monitored_quantity_fall() -> None:
    """The guard ADR 0007 wired in on 2026-09-15 watches log likelihood plus the
    prior's log density on this arm, exactly because a posterior-MEAN update is
    not guaranteed to raise the likelihood alone. This does not assert the guard
    is silent -- only that when it does not fire, the fit still finishes and
    reports a finite likelihood, the same property
    ``test_the_likelihood_never_falls_across_iterations`` pins for the
    unregularised fit."""
    sample = _simulated_two_regime_sample(months=200)
    beta, kappa = hidden_markov.derive_sticky_dirichlet_prior(
        state_count=3, prior_mean_visit_months=30.0, prior_row_strength=60.0
    )
    fitted = hidden_markov.fit(
        sample,
        state_count=3,
        seed=9,
        restarts=3,
        max_iterations=60,
        transition_prior_beta=beta,
        transition_prior_kappa=kappa,
    )
    assert fitted.fit_report is not None
    assert np.isfinite(fitted.fit_report.log_likelihood)
