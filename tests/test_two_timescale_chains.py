"""Research arm A4: one regime chain for growth, a second for inflation with rates.

The product construction is checked against answers computed another way: the
forward algorithm against enumerating every joint path, the joint filtered
distribution against the two chains filtered on their own, the joint likelihood
against the sum of the chains', the product's second eigenvalue against the slower
chain's. The fit is checked against its defining properties: a one-state growth
chain reduces it to a single chain on the levels block and vice versa, one
marginalised maximisation step equals the single-chain step on each block, and the
joint likelihood never falls by more than the shared allowance. Then the wiring:
the burn-in choice, the walk-forward and its cache, the hash, gate 2, and the
look-ahead audit run with the switch explicitly on.
"""

from __future__ import annotations

import copy
import dataclasses
import itertools
import json
import pickle
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import multivariate_normal

from economic_regime_forecasting import look_ahead_audit, pipeline_gates
from economic_regime_forecasting.backtest import schedule as schedule_module
from economic_regime_forecasting.backtest.state_count_on_burn_in import (
    BurnInStateCountChoice,
    choose_state_count_on_burn_in_window,
)
from economic_regime_forecasting.backtest.walk_forward import run_walk_forward
from economic_regime_forecasting.configuration.registry import (
    BinaryIndicator,
    Composition,
    EconomicSeries,
    EconomicSeriesRegistry,
    IndicatorResolution,
    ModelDimension,
    ResolutionRule,
    Transform,
)
from economic_regime_forecasting.configuration.run_settings import (
    DEFAULT_RUN_SETTINGS,
    CacheLayout,
    RunSettings,
)
from economic_regime_forecasting.data.cache import ArtifactStore, SeriesRequest, SeriesSnapshot
from economic_regime_forecasting.models import gaussian_hidden_markov_model as hidden_markov
from economic_regime_forecasting.models import two_timescale_hidden_markov_model as two_timescale
from economic_regime_forecasting.models.gaussian_hidden_markov_model import (
    GaussianHiddenMarkovModel,
    HiddenMarkovModelError,
)
from economic_regime_forecasting.models.state_labelling import canonical_order, canonicalise
from economic_regime_forecasting.models.state_selection import regimes_exist_from_sweep_table
from economic_regime_forecasting.models.two_timescale_hidden_markov_model import (
    LEVELS_CHAIN_SEED_OFFSET,
    TwoChainStateCount,
    TwoTimescaleHiddenMarkovModel,
    regime_model_from_dictionary,
)
from economic_regime_forecasting.models.two_timescale_state_selection import (
    candidate_state_counts_per_chain,
    sweep_state_counts_for_two_chains,
)

SWITCH = "separate_chains_for_growth_and_for_inflation_with_rates"
MAIN_REFERENCE_HASH = "ad7fcc1affd0746a"
"""experiment 0002's reference_run.configuration_hash: main's honest default."""

GROWTH = [0]
LEVELS = [1, 2]

GROWTH_CHAIN = GaussianHiddenMarkovModel(
    initial_distribution=np.array([0.7, 0.3]),
    transition_matrix=np.array([[0.9, 0.1], [0.3, 0.7]]),
    means=np.array([[-1.0], [1.0]]),
    covariances=np.array([[[0.5]], [[0.8]]]),
)
LEVELS_CHAIN = GaussianHiddenMarkovModel(
    initial_distribution=np.array([0.4, 0.6]),
    transition_matrix=np.array([[0.95, 0.05], [0.1, 0.9]]),
    means=np.array([[-0.5, 0.2], [1.5, -0.3]]),
    covariances=np.array([[[1.0, 0.3], [0.3, 0.7]], [[0.6, -0.1], [-0.1, 0.9]]]),
)
OBSERVATIONS = np.array(
    [[0.1, -0.2, 0.3], [0.9, 1.2, -0.1], [-1.1, 0.4, 0.2], [1.2, 1.6, -0.5], [0.3, -0.4, 0.1]]
)


def _model() -> TwoTimescaleHiddenMarkovModel:
    return TwoTimescaleHiddenMarkovModel(GROWTH_CHAIN, LEVELS_CHAIN)


def _simulated_two_chain_sample(months: int = 300, seed: int = 11) -> np.ndarray:
    """A fast growth chain and a slow levels chain, each emitting its own block."""
    generator = np.random.default_rng(seed)
    growth_transitions = np.array([[0.9, 0.1], [0.15, 0.85]])
    levels_transitions = np.array([[0.97, 0.03], [0.04, 0.96]])
    levels_means = np.array([[-1.0, -0.8], [1.2, 1.0]])
    levels_covariance = np.array([[0.3, 0.1], [0.1, 0.3]])
    growth_state, levels_state = 0, 0
    rows = []
    for _ in range(months):
        growth_state = int(generator.choice(2, p=growth_transitions[growth_state]))
        levels_state = int(generator.choice(2, p=levels_transitions[levels_state]))
        growth = generator.normal((-1.0, 1.0)[growth_state], 0.4)
        levels = generator.multivariate_normal(levels_means[levels_state], levels_covariance)
        rows.append([growth, *levels])
    return np.array(rows)


# ------------------------------------------------------------ the product


def test_the_joint_chain_is_the_kronecker_product_of_the_two() -> None:
    model = _model()
    np.testing.assert_array_equal(
        model.transition_matrix,
        np.kron(GROWTH_CHAIN.transition_matrix, LEVELS_CHAIN.transition_matrix),
    )
    np.testing.assert_array_equal(
        model.initial_distribution,
        np.kron(GROWTH_CHAIN.initial_distribution, LEVELS_CHAIN.initial_distribution),
    )
    np.testing.assert_allclose(model.transition_matrix.sum(axis=1), 1.0, rtol=1e-15)


def test_joint_state_g_times_levels_plus_l_carries_both_chains_parameters() -> None:
    model = _model()
    for growth_state, levels_state in itertools.product(range(2), range(2)):
        joint = growth_state * 2 + levels_state
        np.testing.assert_array_equal(
            model.means[joint],
            [GROWTH_CHAIN.means[growth_state, 0], *LEVELS_CHAIN.means[levels_state]],
        )
        covariance = model.covariances[joint]
        assert covariance[0, 0] == GROWTH_CHAIN.covariances[growth_state, 0, 0]
        np.testing.assert_array_equal(covariance[1:, 1:], LEVELS_CHAIN.covariances[levels_state])
        np.testing.assert_array_equal(covariance[0, 1:], [0.0, 0.0])
        np.testing.assert_array_equal(covariance[1:, 0], [0.0, 0.0])


def test_the_product_numbering_is_already_the_canonical_order() -> None:
    """Each chain sorted on its own gives a product the canonical sort leaves alone."""
    np.testing.assert_array_equal(canonical_order(_model()), np.arange(4))


def test_the_state_count_is_the_joint_count_and_carries_the_factorisation() -> None:
    count = _model().state_count
    assert isinstance(count, TwoChainStateCount)
    assert count == 4
    assert (count.growth_chain_state_count, count.levels_chain_state_count) == (2, 2)
    assert _model().free_parameter_count == (
        GROWTH_CHAIN.free_parameter_count + LEVELS_CHAIN.free_parameter_count
    )


# ------------------------------------------------ densities and inference


def test_the_emission_log_density_is_the_sum_of_the_two_blocks() -> None:
    model = _model()
    joint = model.log_emission_probabilities(OBSERVATIONS)
    growth = GROWTH_CHAIN.log_emission_probabilities(OBSERVATIONS[:, GROWTH])
    levels = LEVELS_CHAIN.log_emission_probabilities(OBSERVATIONS[:, LEVELS])
    for growth_state, levels_state in itertools.product(range(2), range(2)):
        np.testing.assert_allclose(
            joint[:, growth_state * 2 + levels_state],
            growth[:, growth_state] + levels[:, levels_state],
            rtol=1e-15,
        )
    # And that sum is the block-diagonal joint Gaussian, computed another way.
    for state in range(4):
        np.testing.assert_allclose(
            joint[:, state],
            multivariate_normal(model.means[state], model.covariances[state]).logpdf(OBSERVATIONS),
            rtol=1e-12,
        )


def test_the_forward_algorithm_agrees_with_enumerating_every_joint_path() -> None:
    """All 4^5 joint paths, summed directly. Independent of the forward pass."""
    model = _model()
    densities = np.exp(
        [
            multivariate_normal(model.means[state], model.covariances[state]).logpdf(OBSERVATIONS)
            for state in range(4)
        ]
    ).T
    total = 0.0
    for path in itertools.product(range(4), repeat=OBSERVATIONS.shape[0]):
        probability = model.initial_distribution[path[0]] * densities[0, path[0]]
        for month in range(1, OBSERVATIONS.shape[0]):
            probability *= model.transition_matrix[path[month - 1], path[month]]
            probability *= densities[month, path[month]]
        total += probability
    assert model.log_likelihood(OBSERVATIONS) == pytest.approx(np.log(total), rel=1e-10)


def test_the_joint_likelihood_is_the_sum_of_the_two_chains_likelihoods() -> None:
    """Independent chains each emitting their own block factorise exactly."""
    model = _model()
    assert model.log_likelihood(OBSERVATIONS) == pytest.approx(
        GROWTH_CHAIN.log_likelihood(OBSERVATIONS[:, GROWTH])
        + LEVELS_CHAIN.log_likelihood(OBSERVATIONS[:, LEVELS]),
        rel=1e-12,
    )


def test_the_joint_filtered_distribution_is_the_product_of_the_two_chains_filters() -> None:
    joint = _model().filtered_state_probabilities(OBSERVATIONS)
    growth = GROWTH_CHAIN.filtered_state_probabilities(OBSERVATIONS[:, GROWTH])
    levels = LEVELS_CHAIN.filtered_state_probabilities(OBSERVATIONS[:, LEVELS])
    for month in range(OBSERVATIONS.shape[0]):
        np.testing.assert_allclose(
            joint[month], np.kron(growth[month], levels[month]), rtol=1e-12, atol=1e-15
        )


def test_joint_filtered_probabilities_at_a_month_ignore_everything_after_it() -> None:
    """The property the whole backtest rests on, for the product model."""
    model = _model()
    short = model.filtered_state_probabilities(OBSERVATIONS[:3])
    long = model.filtered_state_probabilities(OBSERVATIONS)
    np.testing.assert_array_equal(short, long[:3])


def test_the_joint_chain_forgets_at_the_slower_chains_rate() -> None:
    """The pre-registration's prediction: lambda2 of the product is the slower chain's."""
    model = _model()
    assert model.second_largest_eigenvalue_modulus() == pytest.approx(
        max(
            GROWTH_CHAIN.second_largest_eigenvalue_modulus(),
            LEVELS_CHAIN.second_largest_eigenvalue_modulus(),
        ),
        rel=1e-12,
    )
    np.testing.assert_allclose(
        model.stationary_distribution(),
        np.kron(GROWTH_CHAIN.stationary_distribution(), LEVELS_CHAIN.stationary_distribution()),
        rtol=1e-10,
    )


# ---------------------------------------------------------- serialisation


def test_a_two_chain_model_round_trips_through_json_exactly() -> None:
    model = two_timescale.fit(_simulated_two_chain_sample(120), 2, 2, seed=3, restarts=2)
    payload = json.loads(json.dumps(model.to_dictionary()))
    restored = regime_model_from_dictionary(payload)
    assert isinstance(restored, TwoTimescaleHiddenMarkovModel)
    assert restored.to_dictionary() == model.to_dictionary()
    np.testing.assert_array_equal(restored.transition_matrix, model.transition_matrix)
    assert restored.fit_report == model.fit_report


def test_the_single_chain_loader_refuses_a_two_chain_payload_rather_than_misreading_it() -> None:
    payload = _model().to_dictionary()
    with pytest.raises(KeyError):
        GaussianHiddenMarkovModel.from_dictionary(payload)
    with pytest.raises(HiddenMarkovModelError, match="unknown model_class"):
        regime_model_from_dictionary({**payload, "model_class": "something_else"})
    plain = regime_model_from_dictionary(GROWTH_CHAIN.to_dictionary())
    assert type(plain) is GaussianHiddenMarkovModel


def test_a_two_chain_state_count_survives_copying_pickling_and_json() -> None:
    count = TwoChainStateCount(2, 4)
    assert int(count) == 8
    assert count.label == "2x4"
    assert f"{count} regimes" == "8 regimes"
    assert json.dumps({"state_count": count}) == '{"state_count": 8}'
    for rebuilt in (copy.deepcopy(count), pickle.loads(pickle.dumps(count))):  # noqa: S301
        assert isinstance(rebuilt, TwoChainStateCount)
        assert (rebuilt.growth_chain_state_count, rebuilt.levels_chain_state_count) == (2, 4)
    with pytest.raises(HiddenMarkovModelError):
        TwoChainStateCount(0, 3)


# --------------------------------------------------------------- fitting


def _fitting_arguments() -> dict[str, float | int]:
    return {"restarts": 3, "max_iterations": 40, "tolerance": 0.0}


def test_a_one_state_growth_chain_reduces_to_a_single_chain_on_the_levels_block() -> None:
    """The cheapest proof the product construction is right.

    With K_g = 1 the growth density is the same in every joint state and cancels
    from every posterior, so the fit must be the single-chain fit on inflation and
    rates, started from the same stream. Tolerance zero runs both to the same
    iteration count; the match is to floating point, since the joint pass carries
    the growth term through every sum.
    """
    sample = _simulated_two_chain_sample()
    joint = two_timescale.fit(sample, 1, 2, seed=5, **_fitting_arguments())  # type: ignore[arg-type]
    single = canonicalise(
        hidden_markov.fit(
            sample[:, LEVELS],
            2,
            seed=5 + LEVELS_CHAIN_SEED_OFFSET,
            **_fitting_arguments(),  # type: ignore[arg-type]
        )
    )
    assert joint.fit_report is not None and single.fit_report is not None
    # Restarts pair up: every joint restart's likelihood is the single-chain
    # restart's plus the one-state chain's, a constant. (Restarts that reach the same
    # optimum tie to 1e-12, so which index wins is rounding; the fits below match.)
    differences = np.subtract(
        joint.fit_report.log_likelihood_by_restart, single.fit_report.log_likelihood_by_restart
    )
    np.testing.assert_allclose(differences, differences[0], rtol=0.0, atol=1e-8)
    for name in ("initial_distribution", "transition_matrix", "means", "covariances"):
        np.testing.assert_allclose(
            getattr(joint.levels_chain, name), getattr(single, name), rtol=1e-8, atol=1e-10
        )
    np.testing.assert_allclose(
        joint.filtered_state_probabilities(sample),
        single.filtered_state_probabilities(sample[:, LEVELS]),
        rtol=1e-8,
        atol=1e-10,
    )
    # The one growth state's occupancy is a marginal that sums to one only to rounding.
    np.testing.assert_allclose(joint.growth_chain.means[0, 0], sample[:, 0].mean(), rtol=1e-10)


def test_a_one_state_levels_chain_reduces_to_a_single_chain_on_the_growth_column() -> None:
    sample = _simulated_two_chain_sample()
    joint = two_timescale.fit(sample, 2, 1, seed=5, **_fitting_arguments())  # type: ignore[arg-type]
    single = canonicalise(
        hidden_markov.fit(sample[:, GROWTH], 2, seed=5, **_fitting_arguments())  # type: ignore[arg-type]
    )
    assert joint.fit_report is not None and single.fit_report is not None
    # Restarts pair up: every joint restart's likelihood is the single-chain
    # restart's plus the one-state chain's, a constant. (Restarts that reach the same
    # optimum tie to 1e-12, so which index wins is rounding; the fits below match.)
    differences = np.subtract(
        joint.fit_report.log_likelihood_by_restart, single.fit_report.log_likelihood_by_restart
    )
    np.testing.assert_allclose(differences, differences[0], rtol=0.0, atol=1e-8)
    for name in ("initial_distribution", "transition_matrix", "means", "covariances"):
        np.testing.assert_allclose(
            getattr(joint.growth_chain, name), getattr(single, name), rtol=1e-8, atol=1e-10
        )
    np.testing.assert_allclose(
        joint.filtered_state_probabilities(sample),
        single.filtered_state_probabilities(sample[:, GROWTH]),
        rtol=1e-8,
        atol=1e-10,
    )


def _starting_chains(sample: np.ndarray) -> tuple[GaussianHiddenMarkovModel, ...]:
    pooled_growth = two_timescale._pooled_covariance(sample[:, GROWTH])
    pooled_levels = two_timescale._pooled_covariance(sample[:, LEVELS])
    growth = hidden_markov._initial_model(
        sample[:, GROWTH], 2, np.random.default_rng(3), pooled_growth, "full"
    )
    levels = hidden_markov._initial_model(
        sample[:, LEVELS], 3, np.random.default_rng(4), pooled_levels, "full"
    )
    return growth, levels


def test_one_marginalised_maximisation_step_is_each_chains_own_step() -> None:
    """Marginalising the joint posteriors gives each chain exactly the statistics a
    single-chain fit on its own block would compute, because the joint posterior
    of independent chains is the product of theirs."""
    sample = _simulated_two_chain_sample()
    growth, levels = _starting_chains(sample)
    pooled_growth = two_timescale._pooled_covariance(sample[:, GROWTH])
    pooled_levels = two_timescale._pooled_covariance(sample[:, LEVELS])

    stepped, *_ = two_timescale.run_expectation_maximisation(
        TwoTimescaleHiddenMarkovModel(growth, levels), sample, 1, 0.0, pooled_growth, pooled_levels
    )
    growth_stepped, *_ = hidden_markov._run_expectation_maximisation(
        growth, sample[:, GROWTH], 1, 0.0, pooled_growth
    )
    levels_stepped, *_ = hidden_markov._run_expectation_maximisation(
        levels, sample[:, LEVELS], 1, 0.0, pooled_levels
    )
    for name in ("initial_distribution", "transition_matrix", "means", "covariances"):
        np.testing.assert_allclose(
            getattr(stepped.growth_chain, name),
            getattr(growth_stepped, name),
            rtol=1e-9,
            atol=1e-12,
        )
        np.testing.assert_allclose(
            getattr(stepped.levels_chain, name),
            getattr(levels_stepped, name),
            rtol=1e-9,
            atol=1e-12,
        )


def test_every_maximisation_step_raises_the_joint_likelihood() -> None:
    """The monitored quantity is the joint log likelihood, and it never falls by
    more than the shared allowance (ADR 0007). On this sample it does not fall at
    all beyond rounding: the tied step is the exact maximiser."""
    sample = _simulated_two_chain_sample()
    growth, levels = _starting_chains(sample)
    trace: list[float] = []
    two_timescale.run_expectation_maximisation(
        TwoTimescaleHiddenMarkovModel(growth, levels),
        sample,
        60,
        0.0,
        two_timescale._pooled_covariance(sample[:, GROWTH]),
        two_timescale._pooled_covariance(sample[:, LEVELS]),
        log_likelihood_trace=trace,
    )
    assert len(trace) == 61
    for previous, current in itertools.pairwise(trace):
        assert current >= previous - hidden_markov._monotonicity_allowance(previous)
        assert current >= previous - 1e-9 * abs(previous)
    assert trace[-1] > trace[0] + 1.0


def test_the_monotonicity_guard_is_wired_into_the_two_chain_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A maximisation step that makes things worse must be caught, not absorbed."""
    sample = _simulated_two_chain_sample()
    growth, levels = _starting_chains(sample)
    ruined = TwoTimescaleHiddenMarkovModel(
        GaussianHiddenMarkovModel(
            growth.initial_distribution,
            growth.transition_matrix,
            growth.means + 25.0,
            growth.covariances,
        ),
        levels,
    )
    monkeypatch.setattr(two_timescale, "_maximisation_step", lambda *arguments: ruined)
    with pytest.raises(HiddenMarkovModelError, match="joint log likelihood of the two chains fell"):
        two_timescale.run_expectation_maximisation(
            TwoTimescaleHiddenMarkovModel(growth, levels),
            sample,
            5,
            0.0,
            two_timescale._pooled_covariance(sample[:, GROWTH]),
            two_timescale._pooled_covariance(sample[:, LEVELS]),
        )


def test_a_fit_is_canonical_deterministic_and_recovers_both_timescales() -> None:
    sample = _simulated_two_chain_sample(400)
    first = two_timescale.fit(sample, 2, 2, seed=9, restarts=4)
    second = two_timescale.fit(sample, 2, 2, seed=9, restarts=4)
    assert first.to_dictionary() == second.to_dictionary()
    assert first.growth_chain.means[0, 0] < first.growth_chain.means[1, 0]
    assert first.levels_chain.means[0, 0] < first.levels_chain.means[1, 0]
    np.testing.assert_array_equal(canonical_order(first), np.arange(4))
    # Simulated at 0.9/0.85 for growth and 0.97/0.96 for the levels: the fit must
    # put growth on the faster chain, which is the whole point of the arm.
    assert np.diag(first.growth_chain.transition_matrix).max() < 0.95
    assert (
        first.levels_chain.second_largest_eigenvalue_modulus()
        > first.growth_chain.second_largest_eigenvalue_modulus()
    )


# -------------------------------------------------------------- selection


def test_each_chain_is_offered_candidates_up_to_four_so_at_most_sixteen_joint_states() -> None:
    assert candidate_state_counts_per_chain(DEFAULT_RUN_SETTINGS.hidden_state_counts_to_search) == (
        1,
        2,
        3,
        4,
    )
    assert candidate_state_counts_per_chain((1, 2)) == (1, 2)


def test_the_joint_sweep_table_sums_exactly_to_the_joint_models_own_criteria() -> None:
    sample = _simulated_two_chain_sample(300)
    sweep = sweep_state_counts_for_two_chains(sample, (1, 2), seed=7, restarts=2)
    table = sweep.joint_table()
    assert len(table) == 4
    chosen = table[table["chosen"]].iloc[0]
    model = sweep.recommended_model
    holdout_months = round(len(sample) * 0.2)
    training = sample[: len(sample) - holdout_months]
    assert chosen["bayesian_information_criterion"] == pytest.approx(
        model.bayesian_information_criterion(training), rel=1e-10
    )
    assert chosen["held_out_log_likelihood_per_month"] == pytest.approx(
        (model.log_likelihood(sample) - model.log_likelihood(training)) / holdout_months,
        rel=1e-8,
    )
    assert chosen["second_eigenvalue_modulus"] == pytest.approx(
        model.second_largest_eigenvalue_modulus(), rel=1e-10
    )
    regimes_exist, evidence = regimes_exist_from_sweep_table(table)
    assert regimes_exist is True
    assert "held-out log likelihood" in evidence


def test_gate_two_for_two_chains_asks_the_same_five_questions() -> None:
    sample = _simulated_two_chain_sample(300)
    sweep = sweep_state_counts_for_two_chains(sample, (1, 2), seed=7, restarts=2)
    model = sweep.recommended_model
    report = pipeline_gates.gate_two_regime_model_of_two_chains(
        sweep, model.most_likely_state_path(sample), len(sample)
    )
    assert report.number == 2
    assert len(report.checks) == 5
    assert report.checks[0].passed and report.checks[1].passed
    assert "2x2" in report.checks[0].evidence
    assert "joint regime" in report.checks[4].evidence


# ------------------------------------------------------------ settings


def test_with_the_switch_off_the_hash_is_main_reference_runs() -> None:
    """At False the switch leaves no trace in the digest, so a run with it off
    claims main's identity only because it is main's configuration."""
    main = dataclasses.replace(DEFAULT_RUN_SETTINGS, **{SWITCH: False})
    arm = dataclasses.replace(DEFAULT_RUN_SETTINGS, **{SWITCH: True})
    assert main.configuration_hash() == MAIN_REFERENCE_HASH
    assert arm.configuration_hash() != MAIN_REFERENCE_HASH
    assert getattr(DEFAULT_RUN_SETTINGS, SWITCH) is True


# ----------------------------------------------- synthetic cache and wiring


FIRST_FORECAST = date(2000, 1, 1)
CUTOFF = date(2001, 1, 1)


def _series_entry(
    name: str, series_id: str, dimension: ModelDimension, transform: Transform, revised: bool
) -> EconomicSeries:
    return EconomicSeries(
        name=name,
        series_id=series_id,
        description=f"synthetic {name}",
        role=dimension.value,
        model_dimension=dimension,
        frequency="monthly",
        units="units",
        transform=transform,
        publication_lag_days=45,
        observation_start=date(1960, 1, 1),
        is_revised=revised,
    )


@pytest.fixture(scope="module")
def registry() -> EconomicSeriesRegistry:
    change = Transform.YEAR_OVER_YEAR_LOG_CHANGE
    return EconomicSeriesRegistry(
        series=(
            _series_entry("synthetic_output", "SYNOUT", ModelDimension.GROWTH, change, True),
            _series_entry("synthetic_prices", "SYNCPI", ModelDimension.INFLATION, change, True),
            _series_entry(
                "synthetic_rate", "SYNRATE", ModelDimension.RATES, Transform.LEVEL, False
            ),
        ),
        derived=(),
    )


@pytest.fixture(scope="module")
def indicators() -> tuple[BinaryIndicator, ...]:
    def indicator(name: str, rule: ResolutionRule, threshold: float, composition: Composition):
        return BinaryIndicator(
            name=name,
            question=name.replace("_", " "),
            resolution=IndicatorResolution(
                series="synthetic_rate", rule=rule, transform=Transform.LEVEL, threshold=threshold
            ),
            composition=composition,
            horizons_in_years=(1,),
        )

    return (
        indicator(
            "rate_above_three_at_horizon",
            ResolutionRule.LEVEL_ABOVE_THRESHOLD_AT_HORIZON,
            3.0,
            Composition.POINT_IN_TIME,
        ),
        indicator(
            "rate_below_one_within_horizon",
            ResolutionRule.LEVEL_BELOW_THRESHOLD_WITHIN_HORIZON,
            1.0,
            Composition.ANY_TIME_WITHIN_HORIZON,
        ),
    )


def _snapshot(
    values: pd.Series, series_id: str, vintage_date: date | None = None
) -> SeriesSnapshot:
    return SeriesSnapshot(
        request=SeriesRequest(
            source="federal_reserve_economic_data",
            series_id=series_id,
            transform="as_published",
            vintage_date=vintage_date,
        ),
        observations=values.rename(series_id),
        source_url=f"https://example.invalid/{series_id}",
        units="units",
        retrieved_at=datetime(2026, 9, 15, tzinfo=UTC),
        payload_digest="0" * 64,
    )


@pytest.fixture(scope="module")
def source_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Forty years in which output growth switches quickly and prices and the rate
    switch slowly, on separate chains, with honest vintages around 2000."""
    root = tmp_path_factory.mktemp("two_chain_cache")
    cache = look_ahead_audit.series_cache_at(root)
    index = pd.date_range("1960-01-01", "2004-12-01", freq="MS", name="observation_date")
    generator = np.random.default_rng(20260915)
    fast = np.array([[0.92, 0.08], [0.12, 0.88]])
    slow = np.array([[0.98, 0.02], [0.03, 0.97]])
    growth_state = levels_state = 0
    output, prices, rate = [100.0], [100.0], []
    for _ in range(len(index)):
        growth_state = int(generator.choice(2, p=fast[growth_state]))
        levels_state = int(generator.choice(2, p=slow[levels_state]))
        output.append(output[-1] * (1.0 + (0.004 if growth_state == 0 else -0.002)))
        prices.append(prices[-1] * (1.0 + (0.002 if levels_state == 0 else 0.006)))
        rate.append((4.5 if levels_state == 0 else 0.6) + float(generator.normal(0, 0.2)))
    values = {
        "SYNOUT": pd.Series(output[1:], index=index),
        "SYNCPI": pd.Series(prices[1:], index=index),
        "SYNRATE": pd.Series(np.clip(rate, 0.0, None), index=index),
    }
    for series_id, series in values.items():
        cache.write(_snapshot(series, series_id))
    for series_id in ("SYNOUT", "SYNCPI"):
        series = values[series_id]
        for stamp in pd.date_range("1999-01-01", "2003-12-01", freq="MS"):
            as_published = series[series.index < stamp - pd.DateOffset(months=1)]
            cache.write(_snapshot(as_published, series_id, stamp.date()))
    return root


def _settings(root: Path, switch: bool = True) -> RunSettings:
    return RunSettings(
        random_seed=7,
        hidden_state_counts_to_search=(1, 2),
        expectation_maximisation_restarts=2,
        expectation_maximisation_max_iterations=60,
        minimum_observations_before_first_fit=120,
        refit_every_n_months=12,
        forecast_horizons_in_months=(12,),
        cache=CacheLayout(root),
        **{SWITCH: switch},
    )


def _schedule(_cache: object = None) -> schedule_module.ForecastSchedule:
    return schedule_module.build_schedule(FIRST_FORECAST, date(2001, 6, 1), 12)


def test_the_burn_in_choice_with_the_switch_on_chooses_each_chain_and_round_trips(
    registry: EconomicSeriesRegistry, source_root: Path, tmp_path: Path
) -> None:
    cache = look_ahead_audit.series_cache_at(source_root)
    artifacts = ArtifactStore(tmp_path / "models")
    settings = _settings(tmp_path)
    first = choose_state_count_on_burn_in_window(
        registry, cache, settings, FIRST_FORECAST, artifacts=artifacts
    )
    assert isinstance(first.state_count, TwoChainStateCount)
    assert first.panel_end < FIRST_FORECAST
    assert 1 <= first.state_count.growth_chain_state_count <= 2
    assert 1 <= first.state_count.levels_chain_state_count <= 2
    assert len(first.sweep_rows) == 4
    assert {row["growth_chain_states"] for row in first.sweep_rows} == {1, 2}
    manifest = first.as_manifest()
    assert manifest["state_count"] == int(first.state_count)
    assert manifest["growth_chain_state_count"] == first.state_count.growth_chain_state_count

    second = choose_state_count_on_burn_in_window(
        registry, cache, settings, FIRST_FORECAST, artifacts=artifacts
    )
    assert second == first
    assert isinstance(second.state_count, TwoChainStateCount)
    assert second.state_count.label == first.state_count.label


def test_the_burn_in_choice_with_the_switch_off_is_mains_shape_exactly(
    registry: EconomicSeriesRegistry, source_root: Path, tmp_path: Path
) -> None:
    choice = choose_state_count_on_burn_in_window(
        registry,
        look_ahead_audit.series_cache_at(source_root),
        _settings(tmp_path, switch=False),
        FIRST_FORECAST,
    )
    assert type(choice.state_count) is int
    assert set(choice.as_manifest()) == {
        "state_count",
        "runner_up_state_count",
        "chosen_as_of",
        "panel_start",
        "panel_end",
        "months_in_burn_in_panel",
        "reason",
        "sweep",
    }
    assert BurnInStateCountChoice.from_manifest(choice.as_manifest()) == choice


def test_the_walk_forward_fits_two_chains_and_reads_them_back_from_cache_identically(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    source_root: Path,
    tmp_path: Path,
) -> None:
    cache = look_ahead_audit.series_cache_at(source_root)
    settings = _settings(tmp_path)
    schedule = _schedule()
    models = tmp_path / "models"

    def run() -> pd.DataFrame:
        return run_walk_forward(
            registry,
            indicators,
            cache,
            settings,
            TwoChainStateCount(2, 2),
            schedule.forecast_dates,
            schedule.refit_dates,
            artifacts=ArtifactStore(models),
            progress_every=0,
        )

    fresh = run()
    written = sorted(path.name for path in models.glob("model_*.json"))
    assert len(written) == 2
    assert all("_states2x2_" in name for name in written)
    from_cache = run()
    pd.testing.assert_frame_equal(fresh, from_cache)

    assert fresh["state_count"].unique().tolist() == [4]
    assert all(len(text.split(",")) == 4 for text in fresh["regime_distribution"])
    assert fresh["predicted_probability"].between(0.0, 1.0).all()
    loaded = regime_model_from_dictionary(ArtifactStore(models).read_json(written[0]))
    assert isinstance(loaded, TwoTimescaleHiddenMarkovModel)


def test_the_look_ahead_audit_passes_with_the_switch_explicitly_on(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    source_root: Path,
    tmp_path: Path,
) -> None:
    """The deterministic half of experiment 0002's void rule, at unit scale, on the
    arm's own configuration rather than on whatever the default happens to be."""
    audit = look_ahead_audit.audit_look_ahead(
        registry,
        indicators,
        look_ahead_audit.series_cache_at(source_root),
        _settings(tmp_path / "unused"),
        _schedule,
        tmp_path / "audit",
        cutoff=CUTOFF,
    )
    assert audit.exit_code == 0
    assert audit.moved == ()
    assert isinstance(audit.original.state_count, TwoChainStateCount)
    assert audit.original.fits_computed == 2
