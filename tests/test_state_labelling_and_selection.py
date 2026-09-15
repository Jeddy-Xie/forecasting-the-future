"""State labels are arbitrary until they are canonicalised.

The invariance test is the important one: permuting a model's states must leave
the canonicalised model identical. Without that, a walk-forward backtest averages
unrelated regimes together across refits and produces conditional base rates that
look reasonable and mean nothing.
"""

from __future__ import annotations

import numpy as np
import pytest

from economic_regime_forecasting.models import gaussian_hidden_markov_model as hidden_markov
from economic_regime_forecasting.models.gaussian_hidden_markov_model import (
    GaussianHiddenMarkovModel,
)
from economic_regime_forecasting.models.regime_forecast import (
    measure_mixing,
    total_variation_distance,
    transition_matrix_table,
)
from economic_regime_forecasting.models.state_labelling import (
    canonical_order,
    canonicalise,
    describe_regimes,
    label_for,
    permute_state_probabilities,
    regime_table,
)
from economic_regime_forecasting.models.state_selection import (
    StateSelectionError,
    sweep_state_counts,
)


def _three_state_model(order: tuple[int, int, int] = (0, 1, 2)) -> GaussianHiddenMarkovModel:
    """Three states with distinct growth means, presented in a chosen order."""
    initial = np.array([0.2, 0.3, 0.5])
    transitions = np.array([[0.80, 0.10, 0.10], [0.20, 0.70, 0.10], [0.05, 0.05, 0.90]])
    means = np.array([[1.5, 0.2, 0.1], [-1.2, 1.4, 0.9], [0.0, -0.7, -0.6]])
    covariances = np.repeat(np.eye(3)[None, :, :], 3, axis=0)
    index = np.array(order)
    return GaussianHiddenMarkovModel(
        initial_distribution=initial[index],
        transition_matrix=transitions[np.ix_(index, index)],
        means=means[index],
        covariances=covariances[index],
    )


def test_canonicalising_a_permuted_model_gives_an_identical_model() -> None:
    """The invariance the walk-forward backtest depends on."""
    reference = canonicalise(_three_state_model())
    for order in [(2, 0, 1), (1, 2, 0), (2, 1, 0), (0, 2, 1)]:
        permuted = canonicalise(_three_state_model(order))  # type: ignore[arg-type]
        np.testing.assert_allclose(permuted.means, reference.means)
        np.testing.assert_allclose(permuted.transition_matrix, reference.transition_matrix)
        np.testing.assert_allclose(permuted.initial_distribution, reference.initial_distribution)
        np.testing.assert_allclose(permuted.covariances, reference.covariances)


def test_canonical_order_sorts_by_growth_ascending() -> None:
    canonicalised = canonicalise(_three_state_model())
    growth_means = canonicalised.means[:, 0]
    assert list(growth_means) == sorted(growth_means)


def test_canonicalising_preserves_the_likelihood_of_any_sample() -> None:
    """Relabelling states cannot change what the model says about the data."""
    original = _three_state_model()
    sample = np.random.default_rng(1).normal(size=(50, 3))
    assert canonicalise(original).log_likelihood(sample) == pytest.approx(
        original.log_likelihood(sample)
    )


def test_the_transition_matrix_is_permuted_on_both_axes() -> None:
    """Reordering rows and forgetting columns is the half-right version of this."""
    canonicalised = canonicalise(_three_state_model((2, 0, 1)))
    np.testing.assert_allclose(canonicalised.transition_matrix.sum(axis=1), 1.0)
    reference = canonicalise(_three_state_model())
    np.testing.assert_allclose(canonicalised.transition_matrix, reference.transition_matrix)


def test_state_probability_vectors_permute_with_the_same_order() -> None:
    order = canonical_order(_three_state_model())
    single = np.array([0.1, 0.6, 0.3])
    np.testing.assert_allclose(permute_state_probabilities(single, order), single[order])
    series = np.array([[0.1, 0.6, 0.3], [0.5, 0.25, 0.25]])
    np.testing.assert_allclose(permute_state_probabilities(series, order), series[:, order])


def test_labels_read_as_english_a_non_specialist_can_follow() -> None:
    assert label_for(np.array([-1.2, 1.4, 0.9])) == (
        "contracting growth, high inflation, high rates"
    )
    assert label_for(np.array([0.0, 0.0, 0.0])) == (
        "steady growth, moderate inflation, neutral rates"
    )


def test_regime_descriptions_carry_population_and_duration() -> None:
    model = canonicalise(_three_state_model())
    sample = np.random.default_rng(2).normal(size=(200, 3))
    descriptions = describe_regimes(model, sample, sample)
    assert len(descriptions) == 3
    assert sum(item.population_share for item in descriptions) == pytest.approx(1.0)
    assert all(item.expected_duration_in_months > 0 for item in descriptions)
    assert set(regime_table(descriptions).columns) >= {"state", "regime", "population_share"}


def test_the_transition_table_is_labelled_on_both_axes() -> None:
    model = canonicalise(_three_state_model())
    table = transition_matrix_table(model, ["a", "b", "c"])
    assert list(table.index) == ["a", "b", "c"]
    assert list(table.columns) == ["a", "b", "c"]


# ------------------------------------------------------------------- mixing


def test_total_variation_distance_is_zero_for_identical_distributions() -> None:
    assert total_variation_distance(np.array([0.3, 0.7]), np.array([0.3, 0.7])) == 0.0


def test_total_variation_distance_is_one_for_disjoint_distributions() -> None:
    assert total_variation_distance(np.array([1.0, 0.0]), np.array([0.0, 1.0])) == 1.0


def test_a_fast_mixing_chain_loses_its_information_horizon() -> None:
    """A chain that switches half the time forgets its starting point in months."""
    fast = GaussianHiddenMarkovModel(
        np.array([0.5, 0.5]),
        np.array([[0.5, 0.5], [0.5, 0.5]]),
        np.array([[0.0], [1.0]]),
        np.array([[[1.0]], [[1.0]]]),
    )
    diagnostics = measure_mixing(fast, np.array([[1.0, 0.0]]), (12, 60, 120), threshold=0.05)
    assert diagnostics.information_horizon_in_months == 0
    assert "converged at every horizon" in diagnostics.describe()


def test_a_slow_mixing_chain_keeps_information_for_years() -> None:
    slow = GaussianHiddenMarkovModel(
        np.array([0.5, 0.5]),
        np.array([[0.995, 0.005], [0.005, 0.995]]),
        np.array([[0.0], [1.0]]),
        np.array([[[1.0]], [[1.0]]]),
    )
    diagnostics = measure_mixing(slow, np.array([[1.0, 0.0]]), (12, 60, 120), threshold=0.05)
    assert diagnostics.information_horizon_in_months == 120
    assert diagnostics.half_life_in_months > 60


def test_the_distance_to_stationarity_never_grows_with_the_horizon() -> None:
    model = canonicalise(_three_state_model())
    start = model.filtered_state_probabilities(np.random.default_rng(3).normal(size=(40, 3)))
    diagnostics = measure_mixing(model, start, (1, 6, 12, 60, 120), threshold=0.05)
    distances = [item.mean_distance_to_stationary for item in diagnostics.by_horizon]
    assert distances == sorted(distances, reverse=True)


def test_asking_about_an_unmeasured_horizon_raises() -> None:
    model = canonicalise(_three_state_model())
    diagnostics = measure_mixing(model, np.array([[0.2, 0.3, 0.5]]), (12,), threshold=0.05)
    with pytest.raises(KeyError):
        diagnostics.carries_information_at(60)


# ---------------------------------------------------------------- selection


def _simulated_sample(months: int = 480, seed: int = 20260908) -> np.ndarray:
    generator = np.random.default_rng(seed)
    transitions = np.array([[0.97, 0.03], [0.04, 0.96]])
    means = np.array([[1.2, -0.8, 0.3], [-1.0, 1.1, -0.4]])
    state, sample = 0, []
    for _ in range(months):
        state = int(generator.choice(2, p=transitions[state]))
        sample.append(generator.normal(means[state], 0.6))
    return np.array(sample)


def test_the_sweep_prefers_more_than_one_state_when_regimes_are_real() -> None:
    sweep = sweep_state_counts(_simulated_sample(), (1, 2, 3), seed=7, restarts=4)
    assert sweep.more_than_one_state_is_preferred_on_the_holdout
    assert sweep.more_than_one_state_is_preferred_on_the_criterion
    assert sweep.recommended_state_count > 1


def test_the_sweep_returns_a_canonicalised_model_for_every_candidate() -> None:
    sweep = sweep_state_counts(_simulated_sample(240), (1, 2, 3), seed=7, restarts=3)
    for state_count, model in sweep.models.items():
        assert model.state_count == state_count
        growth = model.means[:, 0]
        assert list(growth) == sorted(growth)


def test_the_sweep_reports_every_candidate_it_tried() -> None:
    sweep = sweep_state_counts(_simulated_sample(240), (1, 2, 3, 4), seed=7, restarts=3)
    assert list(sweep.table()["states"]) == [1, 2, 3, 4]
    assert {"admissible", "persistent_enough", "populated_enough"} <= set(sweep.table().columns)


def test_a_holdout_too_short_to_compare_on_is_refused() -> None:
    with pytest.raises(StateSelectionError, match="too few"):
        sweep_state_counts(_simulated_sample(40), (1, 2), seed=7, restarts=2)


def test_adding_a_candidate_does_not_disturb_the_others() -> None:
    """Each candidate gets its own derived seed, so a sweep is reproducible piece
    by piece rather than only as a whole."""
    sample = _simulated_sample(240)
    narrow = sweep_state_counts(sample, (2, 3), seed=7, restarts=3)
    wide = sweep_state_counts(sample, (2, 3, 4), seed=7, restarts=3)
    np.testing.assert_allclose(narrow.models[2].transition_matrix, wide.models[2].transition_matrix)


def test_the_recommendation_explains_itself_in_words() -> None:
    sweep = sweep_state_counts(_simulated_sample(240), (1, 2, 3), seed=7, restarts=3)
    assert "held-out log likelihood" in sweep.reason
    assert str(sweep.recommended_state_count) in sweep.reason


def test_fitting_is_stable_enough_to_reproduce_a_sweep_exactly() -> None:
    sample = _simulated_sample(240)
    first = sweep_state_counts(sample, (2, 3), seed=7, restarts=3)
    second = sweep_state_counts(sample, (2, 3), seed=7, restarts=3)
    assert first.recommended_state_count == second.recommended_state_count
    np.testing.assert_array_equal(
        first.recommended_model.transition_matrix, second.recommended_model.transition_matrix
    )


def test_a_model_of_pure_noise_offers_no_persistent_regimes() -> None:
    """When there are no regimes, the floors should refuse to invent some."""
    noise = np.random.default_rng(4).normal(size=(360, 3))
    with pytest.raises(StateSelectionError, match="do not support regimes"):
        sweep_state_counts(noise, (1, 2, 3), seed=7, restarts=3)


def test_fitting_the_real_shape_of_data_finishes_in_reasonable_time() -> None:
    sample = _simulated_sample(300)
    fitted = hidden_markov.fit(sample, state_count=3, seed=1, restarts=3, max_iterations=200)
    assert fitted.fit_report is not None
    assert fitted.fit_report.iterations <= 200


# --------------------------------------------------- D1: the prior reaches the sweep


def test_the_sweep_defaults_to_no_prior() -> None:
    """Every candidate the sweep already tested must keep fitting exactly as it
    did before the sticky prior existed, when the two new arguments are left at
    their defaults."""
    sample = _simulated_sample(240)
    without_the_arguments = sweep_state_counts(sample, (1, 2, 3), seed=7, restarts=3)
    with_zero_row_strength = sweep_state_counts(
        sample,
        (1, 2, 3),
        seed=7,
        restarts=3,
        sticky_dirichlet_prior_mean_visit_months=30.0,
        sticky_dirichlet_prior_row_strength=0.0,
    )
    for state_count in (1, 2, 3):
        np.testing.assert_array_equal(
            without_the_arguments.models[state_count].transition_matrix,
            with_zero_row_strength.models[state_count].transition_matrix,
        )


def test_the_sweep_passes_a_positive_prior_to_every_candidate() -> None:
    """A2's non-negotiable, checked directly: if only some candidates in the
    sweep received the prior, this arm would be testing a mixture rather than
    its own hypothesis. Every candidate with more than one state must come back
    with no exact zero in its transition matrix."""
    sample = _simulated_sample(240)
    sweep = sweep_state_counts(
        sample,
        (1, 2, 3),
        seed=7,
        restarts=3,
        sticky_dirichlet_prior_mean_visit_months=30.0,
        sticky_dirichlet_prior_row_strength=60.0,
    )
    for state_count, model in sweep.models.items():
        if state_count > 1:
            assert (model.transition_matrix > 0.0).all(), state_count
