"""Experiment 0006: the two-chain sweep restricted to six joint states.

The registration (``research/experiments-drafts/0006-structure-at-matched-granularity.md``)
restricts the two-chain sweep to the pairs of chain counts whose product is six, so
the joint state space matches main's single six-state chain, and lets the sweep's own
rule choose between the admissible pairs. Nothing else moves.

What is pinned here, in that order:

- the switch: its default on this branch, its place in the hash, and that at False
  every digest main has written is unchanged;
- the candidates: with per-chain candidates 1 to 4 the sweep offers exactly 2 x 3 and
  3 x 2, plus the single-regime pair 1 x 1 as the null;
- the rule: it is the existing rule and nothing new. Over every pair it picks what
  the per-chain sweeps pick, so the restriction changes the candidates and only the
  candidates; an inadmissible pair is never chosen, whatever its likelihood; nothing
  admissible raises rather than falling back;
- the regimes-exist gate reads only the pairs the sweep offered;
- the wiring: the burn-in choice, `forecast fit-regimes` and the look-ahead audit all
  run the restricted sweep, and gate 2 rebuilt from a run's tables is the run's gate.
"""

from __future__ import annotations

import dataclasses
import itertools
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from economic_regime_forecasting import command_line_interface as interface
from economic_regime_forecasting import look_ahead_audit, pipeline_gates
from economic_regime_forecasting.backtest import schedule as schedule_module
from economic_regime_forecasting.backtest.state_count_on_burn_in import (
    BurnInStateCountChoice,
    choose_state_count_on_burn_in_window,
)
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
    ARTIFACTS,
    DEFAULT_RUN_SETTINGS,
    SETTINGS_OMITTED_FROM_THE_HASH_WHEN_THEY_HOLD_THE_SHIPPED_VALUE,
    CacheLayout,
    RunSettings,
)
from economic_regime_forecasting.data.cache import ArtifactStore, SeriesRequest, SeriesSnapshot
from economic_regime_forecasting.models import state_selection
from economic_regime_forecasting.models.model_loading import regime_model_from_dictionary
from economic_regime_forecasting.models.state_selection import (
    StateCountEvaluation,
    StateCountSweep,
    StateSelectionError,
    regimes_exist_from_sweep_table,
)
from economic_regime_forecasting.models.two_timescale_hidden_markov_model import (
    TwoChainStateCount,
    TwoTimescaleHiddenMarkovModel,
)
from economic_regime_forecasting.models.two_timescale_state_selection import (
    JOINT_STATE_COUNT_MATCHING_THE_SINGLE_CHAIN,
    TwoChainStateCountSweep,
    joint_state_count_required_by_a_joint_table,
    joint_state_count_the_sweep_requires,
    sweep_state_counts_for_two_chains,
)

RESTRICTION = "restrict_the_two_chain_sweep_to_six_joint_states"
TWO_CHAINS = "separate_chains_for_growth_and_for_inflation_with_rates"
MAIN_TWO_CHAIN_DEFAULT_HASH = "fec79a040f9ca6f9"
"""Main's default at the commit this branch was cut from (ADR 0010; rule 0007's pinned
configuration): two chains, unrestricted."""
MAIN_SINGLE_CHAIN_HASH = "ad7fcc1affd0746a"
"""The single six-state chain: experiment 0006's anchor, baselines/main-single-chain-d14."""

MATCHED_PAIRS = {(2, 3), (3, 2)}


# ------------------------------------------------------------------ the switch


def test_the_restriction_is_on_by_default_on_this_branch_and_asks_for_six_joint_states() -> None:
    assert getattr(DEFAULT_RUN_SETTINGS, RESTRICTION) is True
    assert getattr(DEFAULT_RUN_SETTINGS, TWO_CHAINS) is True
    assert JOINT_STATE_COUNT_MATCHING_THE_SINGLE_CHAIN == 6
    assert joint_state_count_the_sweep_requires(True) == 6
    assert joint_state_count_the_sweep_requires(False) is None


def test_with_the_restriction_off_every_digest_main_has_written_is_unchanged() -> None:
    """At False the field leaves no trace, so main's two-chain default and the single-chain
    anchor keep their identities, and the arm claims a new one."""
    unrestricted = dataclasses.replace(DEFAULT_RUN_SETTINGS, **{RESTRICTION: False})
    single_chain = dataclasses.replace(unrestricted, **{TWO_CHAINS: False})
    assert unrestricted.configuration_hash() == MAIN_TWO_CHAIN_DEFAULT_HASH
    assert single_chain.configuration_hash() == MAIN_SINGLE_CHAIN_HASH
    assert DEFAULT_RUN_SETTINGS.configuration_hash() not in {
        MAIN_TWO_CHAIN_DEFAULT_HASH,
        MAIN_SINGLE_CHAIN_HASH,
    }
    assert SETTINGS_OMITTED_FROM_THE_HASH_WHEN_THEY_HOLD_THE_SHIPPED_VALUE[RESTRICTION] is False


# ------------------------------------------------- evaluations without fitting


def _evaluation(
    states: int, held_out: float, criterion: float = 0.0, admissible: bool = True
) -> StateCountEvaluation:
    return StateCountEvaluation(
        state_count=states,
        free_parameters=7 * states,
        training_log_likelihood=-100.0 * states,
        bayesian_information_criterion=criterion,
        held_out_log_likelihood_per_month=held_out,
        smallest_population_share=0.2 if admissible else 0.01,
        shortest_expected_duration_in_months=12.0,
        second_largest_eigenvalue_modulus=0.9,
        converged=True,
    )


def _chain(evaluations: list[StateCountEvaluation]) -> StateCountSweep:
    """A per-chain sweep chosen by the existing rule itself, not by a copy of it."""
    return state_selection._choose(tuple(evaluations), {})


def _four_candidates(
    held_out: tuple[float, float, float, float],
    criterion: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
    admissible: tuple[bool, bool, bool, bool] = (True, True, True, True),
) -> StateCountSweep:
    return _chain(
        [
            _evaluation(states, held_out[states - 1], criterion[states - 1], admissible[states - 1])
            for states in (1, 2, 3, 4)
        ]
    )


def _pairs(table: pd.DataFrame) -> set[tuple[int, int]]:
    return set(
        zip(
            table["growth_chain_states"].astype(int),
            table["levels_chain_states"].astype(int),
            strict=True,
        )
    )


# ------------------------------------------------------------- the candidates


def test_candidates_one_to_four_offer_two_by_three_and_three_by_two_and_the_null() -> None:
    growth = _four_candidates((-2.0, -1.5, -1.4, -1.0))
    levels = _four_candidates((-3.0, -2.5, -2.2, -2.0))
    sweep = TwoChainStateCountSweep(growth, levels, joint_state_count_required=6)
    table = sweep.joint_table()
    assert _pairs(table) == {(1, 1)} | MATCHED_PAIRS
    assert set(table.loc[table["states"] > 1, "states"]) == {6}
    assert int(sweep.recommended_state_count) == 6
    assert int(table["chosen"].sum()) == 1
    chosen = table[table["chosen"]].iloc[0]
    assert (int(chosen["growth_chain_states"]), int(chosen["levels_chain_states"])) in (
        MATCHED_PAIRS
    )


def test_unrestricted_every_pair_is_listed_and_each_chain_chooses_for_itself_as_before() -> None:
    growth = _four_candidates((-2.0, -1.5, -1.4, -1.0))
    levels = _four_candidates((-3.0, -2.5, -2.2, -2.0))
    sweep = TwoChainStateCountSweep(growth, levels)
    assert len(sweep.joint_table()) == 16
    assert sweep.recommended_state_count.label == "4x4"
    assert sweep.reason.startswith("Growth chain: ")


# ------------------------------------------------------------------- the rule


def test_the_pair_with_the_higher_joint_held_out_likelihood_wins() -> None:
    """3 x 2 scores -1.4 + -2.5 = -3.9 against 2 x 3's -1.5 + -2.2 = -3.7, so 2 x 3
    wins, although each chain alone would have gone to four."""
    growth = _four_candidates((-2.0, -1.5, -1.4, -1.0))
    levels = _four_candidates((-3.0, -2.5, -2.2, -2.0))
    sweep = TwoChainStateCountSweep(growth, levels, joint_state_count_required=6)
    assert sweep.recommended_state_count.label == "2x3"
    assert sweep.growth_chain_evaluation.state_count == 2
    assert sweep.levels_chain_evaluation.state_count == 3
    assert "2x3 wins on joint held-out log likelihood (-3.7000 per month)" in sweep.reason
    assert "would have chosen 4x4" in sweep.reason


def test_an_inadmissible_pair_is_never_chosen_whatever_its_likelihood() -> None:
    """The levels chain's three states fail the population floor, so 2 x 3 is out even
    though it has the higher joint likelihood, and 3 x 2 is chosen."""
    growth = _four_candidates((-2.0, -1.5, -1.4, -1.0))
    levels = _four_candidates((-3.0, -2.5, -2.2, -2.0), admissible=(True, True, False, True))
    sweep = TwoChainStateCountSweep(growth, levels, joint_state_count_required=6)
    assert sweep.recommended_state_count.label == "3x2"
    table = sweep.joint_table()
    assert not bool(table.loc[table["growth_chain_states"] == 2, "admissible"].iloc[0])


def test_a_criterion_that_disagrees_with_the_holdout_is_reported_not_resolved() -> None:
    growth = _four_candidates((-2.0, -1.5, -1.4, -1.0), criterion=(0.0, 50.0, 10.0, 0.0))
    levels = _four_candidates((-3.0, -2.5, -2.2, -2.0), criterion=(0.0, 10.0, 50.0, 0.0))
    sweep = TwoChainStateCountSweep(growth, levels, joint_state_count_required=6)
    assert sweep.recommended_state_count.label == "2x3"
    assert "information criterion prefers 3x2" in sweep.reason
    assert "reported rather than resolved silently" in sweep.reason


def test_no_admissible_pair_raises_where_the_sweep_is_made_rather_than_falling_back() -> None:
    growth = _four_candidates((-2.0, -1.5, -1.4, -1.0), admissible=(True, True, False, True))
    levels = _four_candidates((-3.0, -2.5, -2.2, -2.0), admissible=(True, True, False, True))
    with pytest.raises(StateSelectionError, match="product is 6"):
        TwoChainStateCountSweep(growth, levels, joint_state_count_required=6)


def test_candidates_that_cannot_multiply_to_six_raise_naming_that() -> None:
    growth = _chain([_evaluation(1, -2.0), _evaluation(2, -1.5)])
    levels = _chain([_evaluation(1, -3.0), _evaluation(2, -2.5)])
    with pytest.raises(StateSelectionError, match="no pair of the per-chain candidates"):
        TwoChainStateCountSweep(growth, levels, joint_state_count_required=6)


def _best_admissible_pair(
    growth: StateCountSweep, levels: StateCountSweep, allowed: set[tuple[int, int]]
) -> tuple[int, int] | None:
    """Brute force, written independently of the module: every allowed pair with each
    chain above one state and admissible, ranked by the summed held-out likelihood."""
    candidates = [
        (
            growth_item.held_out_log_likelihood_per_month
            + levels_item.held_out_log_likelihood_per_month,
            pair,
        )
        for growth_item, levels_item in itertools.product(growth.evaluations, levels.evaluations)
        if (pair := (growth_item.state_count, levels_item.state_count)) in allowed
        and growth_item.state_count > 1
        and levels_item.state_count > 1
        and growth_item.is_admissible
        and levels_item.is_admissible
    ]
    return max(candidates)[1] if candidates else None


def test_the_joint_rule_over_every_pair_is_exactly_the_per_chain_rule() -> None:
    """The restriction changes the candidates and nothing else.

    Admissibility is per chain and the joint held-out likelihood is the sum of the
    chains', so choosing the best admissible pair (each chain above one state) over
    EVERY pair must reproduce the two per-chain choices. Checked on 300 random tables,
    beside the restricted choice, which must be the same argmax over the six-cell pairs.
    """
    generator = np.random.default_rng(20260929)
    checked = 0
    for _ in range(300):
        per_chain = []
        for _chain_index in range(2):
            held_out = tuple(float(value) for value in generator.normal(-2.0, 0.5, 4))
            admissible = (True, *(bool(value) for value in generator.random(3) < 0.8))
            if not any(admissible[1:]):
                continue
            per_chain.append(_four_candidates(held_out, admissible=admissible))  # type: ignore[arg-type]
        if len(per_chain) < 2:
            continue
        growth, levels = per_chain
        every_pair = set(itertools.product((1, 2, 3, 4), repeat=2))
        unrestricted = TwoChainStateCountSweep(growth, levels).recommended_state_count
        assert _best_admissible_pair(growth, levels, every_pair) == (
            unrestricted.growth_chain_state_count,
            unrestricted.levels_chain_state_count,
        )
        matched = _best_admissible_pair(growth, levels, MATCHED_PAIRS)
        if matched is None:
            with pytest.raises(StateSelectionError):
                TwoChainStateCountSweep(growth, levels, joint_state_count_required=6)
            continue
        restricted = TwoChainStateCountSweep(
            growth, levels, joint_state_count_required=6
        ).recommended_state_count
        assert (restricted.growth_chain_state_count, restricted.levels_chain_state_count) == (
            matched
        )
        checked += 1
    assert checked > 100


# --------------------------------------------------------- whether regimes exist


def test_the_regimes_exist_gate_reads_only_the_pairs_the_sweep_offered() -> None:
    """4 x 4 beats the single regime and 2 x 3 and 3 x 2 do not, so the unrestricted
    table says regimes exist and the restricted one must not borrow 4 x 4 to say so."""
    growth = _four_candidates((-2.0, -2.2, -2.3, -1.0), criterion=(10.0, 10.0, 10.0, 0.0))
    levels = _four_candidates((-3.0, -3.2, -3.3, -2.0), criterion=(10.0, 10.0, 10.0, 0.0))
    unrestricted = TwoChainStateCountSweep(growth, levels).joint_table()
    restricted = TwoChainStateCountSweep(growth, levels, joint_state_count_required=6).joint_table()
    assert regimes_exist_from_sweep_table(unrestricted)[0] is True
    assert regimes_exist_from_sweep_table(restricted)[0] is False


def test_which_sweep_a_joint_table_came_from_is_read_back_and_a_mixture_is_refused() -> None:
    counts = (1, 2, 3, 4)
    every_pair = set(itertools.product(counts, repeat=2))
    assert joint_state_count_required_by_a_joint_table(every_pair, counts, counts) is None
    assert (
        joint_state_count_required_by_a_joint_table({(1, 1)} | MATCHED_PAIRS, counts, counts) == 6
    )
    with pytest.raises(ValueError, match="different runs"):
        joint_state_count_required_by_a_joint_table({(1, 1), (2, 3)}, counts, counts)
    with pytest.raises(ValueError, match="different runs"):
        joint_state_count_required_by_a_joint_table(
            {(1, 1), (2, 3), (3, 2), (2, 2)}, counts, counts
        )


# ------------------------------------------------ a synthetic economy, fitted


def _simulated_growth_two_levels_three(months: int = 360, seed: int = 5) -> np.ndarray:
    """A fast two-state growth chain and a slow three-state levels chain."""
    generator = np.random.default_rng(seed)
    growth_transitions = np.array([[0.9, 0.1], [0.15, 0.85]])
    levels_transitions = np.array([[0.96, 0.03, 0.01], [0.02, 0.96, 0.02], [0.01, 0.03, 0.96]])
    levels_means = np.array([[-1.5, -1.2], [0.0, 0.2], [1.5, 1.3]])
    growth_state, levels_state = 0, 0
    rows = []
    for _ in range(months):
        growth_state = int(generator.choice(2, p=growth_transitions[growth_state]))
        levels_state = int(generator.choice(3, p=levels_transitions[levels_state]))
        growth = generator.normal((-1.0, 1.0)[growth_state], 0.4)
        levels = generator.multivariate_normal(levels_means[levels_state], 0.1 * np.eye(2))
        rows.append([growth, *levels])
    return np.array(rows)


def test_a_fitted_restricted_sweep_chooses_a_six_state_product_and_its_criteria_add_up() -> None:
    sample = _simulated_growth_two_levels_three()
    sweep = sweep_state_counts_for_two_chains(
        sample, (1, 2, 3), seed=7, restarts=2, joint_state_count_required=6
    )
    table = sweep.joint_table()
    assert _pairs(table) == {(1, 1)} | MATCHED_PAIRS
    model = sweep.recommended_model
    assert isinstance(model, TwoTimescaleHiddenMarkovModel)
    assert int(model.state_count) == 6
    assert model.state_count.label == sweep.recommended_state_count.label
    # The simulated truth is 2 x 3, and it is the admissible pair with the best holdout.
    assert sweep.recommended_state_count.label == "2x3"
    chosen = table[table["chosen"]].iloc[0]
    assert int(chosen["free_parameters"]) == model.free_parameter_count
    holdout_months = round(len(sample) * 0.2)
    training = sample[: len(sample) - holdout_months]
    assert chosen["held_out_log_likelihood_per_month"] == pytest.approx(
        (model.log_likelihood(sample) - model.log_likelihood(training)) / holdout_months,
        rel=1e-8,
    )
    # Each chain's own sweep is still complete: its table and its fits are main's.
    assert set(sweep.table()["states"]) == {1, 2, 3}


def test_gate_two_rebuilt_from_a_restricted_run_s_tables_is_the_run_s_own_gate() -> None:
    sample = _simulated_growth_two_levels_three()
    sweep = sweep_state_counts_for_two_chains(
        sample, (1, 2, 3), seed=7, restarts=2, joint_state_count_required=6
    )
    model = sweep.recommended_model
    path = model.most_likely_state_path(sample)
    in_run = pipeline_gates.gate_two_regime_model_of_two_chains(sweep, path, len(sample))
    from_tables = pipeline_gates.gate_two_from_tables(
        sweep.joint_table(), model, path, len(sample), per_chain_table=sweep.table()
    )
    assert from_tables.describe() == in_run.describe()
    assert "4x4" not in in_run.checks[0].evidence
    assert "2x3" in in_run.checks[0].evidence and "3x2" in in_run.checks[0].evidence


def test_gate_two_from_tables_refuses_a_model_the_restricted_tables_did_not_choose() -> None:
    sample = _simulated_growth_two_levels_three()
    restricted = sweep_state_counts_for_two_chains(
        sample, (1, 2, 3), seed=7, restarts=2, joint_state_count_required=6
    )
    other = TwoTimescaleHiddenMarkovModel(
        restricted.growth_chain_sweep.models[3], restricted.levels_chain_sweep.models[2]
    )
    assert other.state_count.label != restricted.recommended_state_count.label
    with pytest.raises(ValueError, match="different runs"):
        pipeline_gates.gate_two_from_tables(
            restricted.joint_table(),
            other,
            other.most_likely_state_path(sample),
            len(sample),
            per_chain_table=restricted.table(),
        )


# ----------------------------------------------- synthetic cache and wiring


FIRST_FORECAST = date(2000, 1, 1)
CUTOFF = date(2001, 1, 1)
TODAY = date(2004, 1, 1)


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
        retrieved_at=datetime(2026, 9, 29, tzinfo=UTC),
        payload_digest="0" * 64,
    )


@pytest.fixture(scope="module")
def source_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Forty-five years in which output growth switches quickly between two states and
    prices and the rate slowly among three, with honest vintages around 2000."""
    root = tmp_path_factory.mktemp("matched_granularity_cache")
    cache = look_ahead_audit.series_cache_at(root)
    index = pd.date_range("1960-01-01", "2004-12-01", freq="MS", name="observation_date")
    generator = np.random.default_rng(20260929)
    fast = np.array([[0.92, 0.08], [0.12, 0.88]])
    slow = np.array([[0.98, 0.015, 0.005], [0.01, 0.98, 0.01], [0.005, 0.015, 0.98]])
    growth_state = levels_state = 0
    output, prices, rate = [100.0], [100.0], []
    for _ in range(len(index)):
        growth_state = int(generator.choice(2, p=fast[growth_state]))
        levels_state = int(generator.choice(3, p=slow[levels_state]))
        output.append(output[-1] * (1.0 + (0.004 if growth_state == 0 else -0.002)))
        prices.append(prices[-1] * (1.0 + (0.001, 0.004, 0.008)[levels_state]))
        rate.append((1.0, 3.5, 6.5)[levels_state] + float(generator.normal(0, 0.2)))
    values = {
        "SYNOUT": pd.Series(output[1:], index=index),
        "SYNCPI": pd.Series(prices[1:], index=index),
        "SYNRATE": pd.Series(np.clip(rate, 0.0, None), index=index),
    }
    for series_id, series in values.items():
        cache.write(_snapshot(series, series_id))
    for series_id in ("SYNOUT", "SYNCPI"):
        series = values[series_id]
        for stamp in pd.date_range("1999-01-01", "2004-01-01", freq="MS"):
            as_published = series[series.index < stamp - pd.DateOffset(months=1)]
            cache.write(_snapshot(as_published, series_id, stamp.date()))
    return root


def _settings(root: Path, restricted: bool = True) -> RunSettings:
    return RunSettings(
        random_seed=7,
        hidden_state_counts_to_search=(1, 2, 3),
        expectation_maximisation_restarts=2,
        expectation_maximisation_max_iterations=60,
        minimum_observations_before_first_fit=120,
        refit_every_n_months=12,
        forecast_horizons_in_months=(12,),
        cache=CacheLayout(root),
        **{TWO_CHAINS: True, RESTRICTION: restricted},
    )


def _schedule(_cache: object = None) -> schedule_module.ForecastSchedule:
    return schedule_module.build_schedule(FIRST_FORECAST, date(2001, 6, 1), 12)


def test_the_burn_in_choice_runs_the_restricted_sweep_before_the_first_forecast(
    registry: EconomicSeriesRegistry, source_root: Path, tmp_path: Path
) -> None:
    cache = look_ahead_audit.series_cache_at(source_root)
    artifacts = ArtifactStore(tmp_path / "models")
    choice = choose_state_count_on_burn_in_window(
        registry, cache, _settings(tmp_path), FIRST_FORECAST, artifacts=artifacts
    )
    assert isinstance(choice.state_count, TwoChainStateCount)
    assert int(choice.state_count) == 6
    assert choice.panel_end < FIRST_FORECAST
    assert _pairs(choice.sweep_table()) == {(1, 1)} | MATCHED_PAIRS
    assert "Restricted to pairs of chain counts whose product is 6" in choice.reason
    # Each chain's own sweep is recorded in full beside the joint table.
    assert {row["states"] for row in choice.growth_chain_sweep_rows} == {1, 2, 3}
    assert BurnInStateCountChoice.from_manifest(choice.as_manifest()) == choice

    unrestricted = choose_state_count_on_burn_in_window(
        registry, cache, _settings(tmp_path, restricted=False), FIRST_FORECAST, artifacts=artifacts
    )
    assert len(unrestricted.sweep_rows) == 9
    # Different settings, different hash, different cache entry: neither reads the other's.
    assert unrestricted.sweep_rows != choice.sweep_rows


def test_fit_regimes_runs_the_restricted_sweep_and_its_artifacts_rebuild_its_gate(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    source_root: Path,
    tmp_path: Path,
) -> None:
    """Gate 2 and today's forecast read the full-sample sweep, so it must be restricted too."""
    artifacts = ArtifactStore(tmp_path / "models")
    workspace = interface.Workspace(
        registry=registry,
        indicators=indicators,
        cache=look_ahead_audit.series_cache_at(source_root),
        artifacts=artifacts,
        settings=_settings(tmp_path),
    )
    _code, report = interface.fit_regimes(workspace, TODAY)
    joint = artifacts.read_table(ARTIFACTS.state_count_sweep)
    assert _pairs(joint) == {(1, 1)} | MATCHED_PAIRS
    model = regime_model_from_dictionary(artifacts.read_json(ARTIFACTS.selected_model))
    assert isinstance(model, TwoTimescaleHiddenMarkovModel)
    assert int(model.state_count) == 6

    matrix = workspace.observation_matrix_as_of(TODAY)
    rebuilt = pipeline_gates.gate_two_from_tables(
        joint,
        model,
        model.most_likely_state_path(matrix.values),
        len(matrix),
        per_chain_table=artifacts.read_table(ARTIFACTS.state_count_sweep_by_chain),
    )
    assert rebuilt.describe() == report.describe()


def test_the_look_ahead_audit_passes_and_audits_the_restricted_count(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    source_root: Path,
    tmp_path: Path,
) -> None:
    """The deterministic half of the look-ahead defence, at unit scale, on this arm's
    own configuration: the audit decides the count through the same function the
    backtest does (D15), so it must be auditing a six-state product."""
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
    assert int(audit.original.state_count) == 6
    assert int(audit.perturbed.state_count) == 6
    assert audit.original.fits_computed == 2
