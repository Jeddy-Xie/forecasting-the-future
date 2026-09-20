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
"""

from __future__ import annotations

from collections.abc import Sequence
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

    @property
    def recommended_state_count(self) -> TwoChainStateCount:
        return TwoChainStateCount(
            self.growth_chain_sweep.recommended_state_count,
            self.levels_chain_sweep.recommended_state_count,
        )

    @property
    def recommended_model(self) -> TwoTimescaleHiddenMarkovModel:
        """The product of the two chosen chains, each fitted on its own block."""
        return TwoTimescaleHiddenMarkovModel(
            growth_chain=self.growth_chain_sweep.recommended_model,
            levels_chain=self.levels_chain_sweep.recommended_model,
        )

    @property
    def growth_chain_evaluation(self) -> StateCountEvaluation:
        return self.growth_chain_sweep.evaluation_for(
            self.growth_chain_sweep.recommended_state_count
        )

    @property
    def levels_chain_evaluation(self) -> StateCountEvaluation:
        return self.levels_chain_sweep.evaluation_for(
            self.levels_chain_sweep.recommended_state_count
        )

    @property
    def reason(self) -> str:
        return (
            f"Growth chain: {self.growth_chain_sweep.reason} Inflation-and-rates chain: "
            f"{self.levels_chain_sweep.reason} Together: {self.recommended_state_count.describe()}."
        )

    def joint_rows(self) -> tuple[dict[str, object], ...]:
        """One row per pair of candidates, with the joint quantities that add exactly."""
        chosen = self.recommended_state_count
        rows: list[dict[str, object]] = []
        for growth in self.growth_chain_sweep.evaluations:
            for levels in self.levels_chain_sweep.evaluations:
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
) -> TwoChainStateCountSweep:
    """Run the existing selection rule on each chain's own block."""
    observations = np.atleast_2d(np.asarray(observations, dtype="float64"))
    candidates = candidate_state_counts_per_chain(state_counts)
    return TwoChainStateCountSweep(
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
