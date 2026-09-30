"""Choosing each chain's number of states, and asking whether regimes exist, for two chains.

Research arm A4 of experiment 0002 fixes the rule: the growth chain's count is
chosen on the growth column alone, and the levels chain's on the inflation and
rates columns alone, each by the existing selection rule
(``state_selection.sweep_state_counts``: persistence and population floors, then
held-out log likelihood) over candidates 1 to 4. Nothing about the rule is new; it
is run twice, on two blocks.

The joint table
---------------
The product of two independent chains, each emitting its own block, has a joint
likelihood that is exactly the product of the two chains' likelihoods. So for
every pair of candidates the joint model's training log likelihood, held-out log
likelihood per month and Bayesian information criterion are the SUMS of the two
chains' (the criterion because both chains are scored on the same months, so
``-2 (L_g + L_l) + (p_g + p_l) log n`` is the sum of the two). The joint table
lists every pair, and ``regimes_exist_from_sweep_table`` reads it unchanged: the
single-regime row is the pair (1, 1), and every other pair is a multi-regime
candidate. No new arithmetic decides whether regimes exist.

Matched granularity (experiment 0006)
-------------------------------------
Two chains of up to four states each can reach sixteen joint regimes where main's
single chain has six, so a two-chain result mixes the structure with the number of
cells. Experiment 0006 holds the cells fixed: the sweep offers only the pairs whose
product is six (``JOINT_STATE_COUNT_MATCHING_THE_SINGLE_CHAIN``), which with
candidates 1 to 4 are 2 x 3 and 3 x 2. The pair is chosen by the existing rule read
on the joint rows: each chain's count above one and admissible (the persistence and
population floors), then the highest joint held-out log likelihood, the Bayesian
information criterion reported beside it. Because admissibility is per chain and
the joint held-out likelihood is the sum of the chains', that rule over EVERY pair
picks exactly what the two per-chain sweeps pick, so the restriction changes the
candidates and nothing else. The pair (1, 1) stays in the joint table as the
single-regime null the regimes-exist gate compares against, for the same reason 1
is in ``hidden_state_counts_to_search``.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from economic_regime_forecasting.models.state_selection import (
    StateCountEvaluation,
    StateCountSweep,
    StateSelectionError,
    sweep_state_counts,
)
from economic_regime_forecasting.models.two_timescale_hidden_markov_model import (
    GROWTH_COLUMNS,
    LEVELS_CHAIN_SEED_OFFSET,
    LEVELS_COLUMNS,
    MAXIMUM_STATES_PER_CHAIN,
    TwoChainStateCount,
    TwoTimescaleHiddenMarkovModel,
)

JOINT_STATE_COUNT_MATCHING_THE_SINGLE_CHAIN = 6
"""Experiment 0006: the joint state count the restricted sweep holds fixed.

It is the count main's single chain chose on its burn-in window, the panel from
1950-12 to 1994-01 assembled as of the first forecast date 1994-03-01 (the anchor
``baselines/main-single-chain-d14.json``: ``state_count`` 6, chosen as of
1994-03-01). Fixed by the registration before the run, not derived from data at run
time, and it carries nothing published after the first forecast date."""


def joint_state_count_the_sweep_requires(
    restrict_the_two_chain_sweep_to_six_joint_states: bool,
) -> int | None:
    """The joint count every multi-regime pair must multiply to, or None for no restriction.

    One place turns the ``RunSettings`` switch into the sweep's argument, so the
    burn-in sweep and the full-sample sweep cannot read it differently.
    """
    if restrict_the_two_chain_sweep_to_six_joint_states:
        return JOINT_STATE_COUNT_MATCHING_THE_SINGLE_CHAIN
    return None


def candidate_state_counts_per_chain(state_counts: Sequence[int]) -> tuple[int, ...]:
    """The configured candidates, capped at four per chain.

    Main's candidates are 1 to 6, so this is 1 to 4, the registered set. The cap is
    what keeps the product within the registered maximum of 16 joint states.
    """
    candidates = tuple(
        sorted({int(count) for count in state_counts if count <= MAXIMUM_STATES_PER_CHAIN})
    )
    if not candidates:
        raise StateSelectionError(
            f"none of the candidate state counts {tuple(state_counts)} is at most "
            f"{MAXIMUM_STATES_PER_CHAIN}, the most either chain may have. Include 1 and at least "
            "one count between 2 and 4 in `hidden_state_counts_to_search`."
        )
    return candidates


@dataclass(frozen=True)
class TwoChainStateCountSweep:
    """The two chains' sweeps, the counts they chose, and the joint table."""

    growth_chain_sweep: StateCountSweep
    levels_chain_sweep: StateCountSweep
    joint_state_count_required: int | None = None
    """Experiment 0006. None is main's sweep: every pair of chain counts is listed and
    each chain's own sweep chooses its count. An integer keeps only the pairs whose
    product is that count, plus the single-regime pair (1, 1) as the null, and the
    pair is chosen among them by the existing rule read on the joint rows."""

    def __post_init__(self) -> None:
        # Asked once, at construction, so a restriction nothing can satisfy raises
        # where the sweep is made rather than later inside a gate or a property.
        if self.joint_state_count_required is not None:
            self._restricted_choice()

    def _pairs_in_the_sweep(self) -> list[tuple[StateCountEvaluation, StateCountEvaluation]]:
        """The pairs of chain counts this sweep offers, in the per-chain tables' order."""
        required = self.joint_state_count_required
        return [
            (growth, levels)
            for growth in self.growth_chain_sweep.evaluations
            for levels in self.levels_chain_sweep.evaluations
            if required is None or growth.state_count * levels.state_count in (1, required)
        ]

    def _restricted_choice(self) -> tuple[TwoChainStateCount, str]:
        """The existing rule on the joint rows whose product is the required count.

        Each chain's count above one and admissible, as ``state_selection._choose``
        asks of each chain; then the highest joint held-out log likelihood per
        month, the sum of the two chains'. The criterion is reported beside it and a
        disagreement is stated, never resolved silently.
        """
        required = self.joint_state_count_required
        offered = [
            (growth, levels)
            for growth, levels in self._pairs_in_the_sweep()
            if growth.state_count * levels.state_count == required
        ]
        admissible = [
            (growth, levels)
            for growth, levels in offered
            if growth.state_count > 1
            and levels.state_count > 1
            and growth.is_admissible
            and levels.is_admissible
        ]
        if not admissible:
            described = (
                ", ".join(
                    f"{growth.state_count}x{levels.state_count} (growth shortest visit "
                    f"{growth.shortest_expected_duration_in_months:.1f} months, smallest "
                    f"population {growth.smallest_population_share:.1%}; inflation-and-rates "
                    f"{levels.shortest_expected_duration_in_months:.1f} months, "
                    f"{levels.smallest_population_share:.1%})"
                    for growth, levels in offered
                )
                or "none: no pair of the per-chain candidates multiplies to it"
            )
            raise StateSelectionError(
                f"no pair of chain counts whose product is {required} has each chain above one "
                f"state and both persistent and populated enough. Pairs offered: {described}. "
                "The two chains cannot be fitted at this granularity on this panel; report that "
                "rather than lowering the floors or widening the candidates."
            )

        def joint_held_out(pair: tuple[StateCountEvaluation, StateCountEvaluation]) -> float:
            return (
                pair[0].held_out_log_likelihood_per_month
                + pair[1].held_out_log_likelihood_per_month
            )

        def joint_criterion(pair: tuple[StateCountEvaluation, StateCountEvaluation]) -> float:
            return pair[0].bayesian_information_criterion + pair[1].bayesian_information_criterion

        growth, levels = max(admissible, key=joint_held_out)
        chosen = TwoChainStateCount(growth.state_count, levels.state_count)
        by_criterion = min(admissible, key=joint_criterion)
        agreement = (
            "and the Bayesian information criterion agrees."
            if by_criterion == (growth, levels)
            else (
                "while the Bayesian information criterion prefers "
                f"{by_criterion[0].state_count}x{by_criterion[1].state_count}. The holdout "
                "decides because it asks the out-of-sample question directly; the "
                "disagreement is reported rather than resolved silently."
            )
        )
        reason = (
            f"Restricted to pairs of chain counts whose product is {required}, matching the "
            f"single chain's {required} states (experiment 0006); admissible pairs "
            + ", ".join(f"{pair[0].state_count}x{pair[1].state_count}" for pair in admissible)
            + f". {chosen.label} wins on joint held-out log likelihood "
            f"({joint_held_out((growth, levels)):.4f} per month), {agreement} Unrestricted, "
            f"each chain's own sweep would have chosen "
            f"{self.growth_chain_sweep.recommended_state_count}x"
            f"{self.levels_chain_sweep.recommended_state_count}."
        )
        return chosen, reason

    @property
    def recommended_state_count(self) -> TwoChainStateCount:
        if self.joint_state_count_required is not None:
            return self._restricted_choice()[0]
        return TwoChainStateCount(
            self.growth_chain_sweep.recommended_state_count,
            self.levels_chain_sweep.recommended_state_count,
        )

    @property
    def recommended_model(self) -> TwoTimescaleHiddenMarkovModel:
        """The product of the two chosen chains, each fitted on its own block."""
        chosen = self.recommended_state_count
        return TwoTimescaleHiddenMarkovModel(
            growth_chain=self.growth_chain_sweep.models[chosen.growth_chain_state_count],
            levels_chain=self.levels_chain_sweep.models[chosen.levels_chain_state_count],
        )

    @property
    def growth_chain_evaluation(self) -> StateCountEvaluation:
        return self.growth_chain_sweep.evaluation_for(
            self.recommended_state_count.growth_chain_state_count
        )

    @property
    def levels_chain_evaluation(self) -> StateCountEvaluation:
        return self.levels_chain_sweep.evaluation_for(
            self.recommended_state_count.levels_chain_state_count
        )

    @property
    def reason(self) -> str:
        if self.joint_state_count_required is not None:
            return self._restricted_choice()[1]
        return (
            f"Growth chain: {self.growth_chain_sweep.reason} Inflation-and-rates chain: "
            f"{self.levels_chain_sweep.reason} Together: {self.recommended_state_count.describe()}."
        )

    def joint_rows(self) -> tuple[dict[str, object], ...]:
        """One row per pair of candidates, with the joint quantities that add exactly."""
        chosen = self.recommended_state_count
        rows: list[dict[str, object]] = []
        for growth, levels in self._pairs_in_the_sweep():
            rows.append(
                {
                    "states": growth.state_count * levels.state_count,
                    "growth_chain_states": growth.state_count,
                    "levels_chain_states": levels.state_count,
                    "free_parameters": growth.free_parameters + levels.free_parameters,
                    "training_log_likelihood": growth.training_log_likelihood
                    + levels.training_log_likelihood,
                    "bayesian_information_criterion": growth.bayesian_information_criterion
                    + levels.bayesian_information_criterion,
                    "held_out_log_likelihood_per_month": (
                        growth.held_out_log_likelihood_per_month
                        + levels.held_out_log_likelihood_per_month
                    ),
                    # A Kronecker product's eigenvalues are the products of its
                    # factors', so the joint chain forgets at the slower chain's rate.
                    "second_eigenvalue_modulus": max(
                        growth.second_largest_eigenvalue_modulus,
                        levels.second_largest_eigenvalue_modulus,
                    ),
                    "admissible": bool(growth.is_admissible and levels.is_admissible),
                    "chosen": bool(
                        growth.state_count == chosen.growth_chain_state_count
                        and levels.state_count == chosen.levels_chain_state_count
                    ),
                }
            )
        return tuple(rows)

    def joint_table(self) -> pd.DataFrame:
        return pd.DataFrame(list(self.joint_rows()))

    def table(self) -> pd.DataFrame:
        """Both chains' own sweeps, one above the other, labelled by chain."""
        growth = self.growth_chain_sweep.table()
        levels = self.levels_chain_sweep.table()
        growth.insert(0, "chain", "growth")
        levels.insert(0, "chain", "inflation and rates")
        return pd.concat([growth, levels], ignore_index=True)


def sweep_state_counts_for_two_chains(
    observations: np.ndarray,
    state_counts: Sequence[int],
    seed: int,
    restarts: int = 20,
    max_iterations: int = 500,
    tolerance: float = 1e-6,
    joint_state_count_required: int | None = None,
) -> TwoChainStateCountSweep:
    """Run the existing selection rule on each chain's own block.

    Each chain is still swept over every candidate, so its own table is complete and
    its fits are the ones main makes (each candidate has its own derived seed). With
    ``joint_state_count_required`` set, only the pairs whose product is that count are
    offered, and the pair is chosen on the joint rows; see the module docstring.
    """
    observations = np.atleast_2d(np.asarray(observations, dtype="float64"))
    candidates = candidate_state_counts_per_chain(state_counts)
    return TwoChainStateCountSweep(
        joint_state_count_required=joint_state_count_required,
        growth_chain_sweep=sweep_state_counts(
            observations[:, list(GROWTH_COLUMNS)],
            candidates,
            seed=seed,
            restarts=restarts,
            max_iterations=max_iterations,
            tolerance=tolerance,
        ),
        levels_chain_sweep=sweep_state_counts(
            observations[:, list(LEVELS_COLUMNS)],
            candidates,
            seed=seed + LEVELS_CHAIN_SEED_OFFSET,
            restarts=restarts,
            max_iterations=max_iterations,
            tolerance=tolerance,
        ),
    )


def joint_state_count_required_by_a_joint_table(
    pairs_in_the_table: Iterable[tuple[int, int]],
    growth_chain_state_counts: Collection[int],
    levels_chain_state_counts: Collection[int],
) -> int | None:
    """Read back, from the joint table a run wrote, which sweep that run made.

    Every pair of the per-chain candidates means the unrestricted sweep, None. The
    single-regime pair plus exactly the pairs of one joint count means the sweep was
    restricted to that count. Anything else did not come from one sweep over these
    per-chain tables, and is refused rather than guessed at.
    """
    in_the_table = {(int(growth), int(levels)) for growth, levels in pairs_in_the_table}
    every_pair = {
        (int(growth), int(levels))
        for growth in growth_chain_state_counts
        for levels in levels_chain_state_counts
    }
    if in_the_table == every_pair:
        return None
    joint_counts = {growth * levels for growth, levels in in_the_table if growth * levels > 1}
    if len(joint_counts) == 1:
        (required,) = joint_counts
        restricted = {pair for pair in every_pair if pair[0] * pair[1] in (1, required)}
        if in_the_table == restricted:
            return required
    raise ValueError(
        f"the joint sweep table lists the chain-count pairs {sorted(in_the_table)}, which are "
        "neither every pair of the per-chain tables' counts nor the single-regime pair with every "
        "pair of one joint count; the joint and per-chain tables come from different runs."
    )
