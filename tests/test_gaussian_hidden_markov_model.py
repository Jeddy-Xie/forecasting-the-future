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
