"""Choosing how many regimes the data support.

Four criteria, applied in a fixed order so the choice is a rule rather than a
judgement made after seeing the answer:

1. **Persistence.** A state whose expected visit lasts under three months is not
   an economic regime, it is a label the fit put on noise. Failing this is
   disqualifying.
2. **Population.** A state holding under five percent of months is not estimated
   from enough data to carry a conditional base rate. Also disqualifying.
3. **Held-out log likelihood**, on a chronological holdout. Among the candidates
   that survive the first two, this decides. It is the only criterion that asks
   the out-of-sample question directly.
4. **Bayesian information criterion** on the training window. Reported alongside,
   and when it disagrees with the holdout the disagreement is reported too rather
   than resolved silently.

The holdout is the last fifth of the sample and is never shuffled. Random
cross-validation on a time series lets the model interpolate between months it
has already seen, which flatters every candidate and flatters the complicated
ones most.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from economic_regime_forecasting.models import gaussian_hidden_markov_model as hidden_markov
from economic_regime_forecasting.models.gaussian_hidden_markov_model import (
    GaussianHiddenMarkovModel,
)
from economic_regime_forecasting.models.state_labelling import canonicalise

logger = logging.getLogger(__name__)

MINIMUM_EXPECTED_DURATION_IN_MONTHS = 3.0
MINIMUM_POPULATION_SHARE = 0.05
HOLDOUT_FRACTION = 0.2


class StateSelectionError(ValueError):
    """The sweep could not be run, or nothing survived the sanity floors."""


@dataclass(frozen=True)
class StateCountEvaluation:
    """One candidate number of states, measured every way that matters."""

    state_count: int
    free_parameters: int
    training_log_likelihood: float
    bayesian_information_criterion: float
    held_out_log_likelihood_per_month: float
    smallest_population_share: float
    shortest_expected_duration_in_months: float
    second_largest_eigenvalue_modulus: float
    converged: bool

    @property
    def is_persistent_enough(self) -> bool:
        return self.shortest_expected_duration_in_months >= MINIMUM_EXPECTED_DURATION_IN_MONTHS

    @property
    def is_populated_enough(self) -> bool:
        return self.smallest_population_share >= MINIMUM_POPULATION_SHARE

    @property
    def is_admissible(self) -> bool:
        """A single-state model has no persistence or population to check."""
        if self.state_count == 1:
            return True
        return self.is_persistent_enough and self.is_populated_enough

    def as_row(self) -> dict[str, object]:
        return {
            "states": self.state_count,
            "free_parameters": self.free_parameters,
            "training_log_likelihood": self.training_log_likelihood,
            "bayesian_information_criterion": self.bayesian_information_criterion,
            "held_out_log_likelihood_per_month": self.held_out_log_likelihood_per_month,
            "smallest_population_share": self.smallest_population_share,
            "shortest_expected_duration_months": self.shortest_expected_duration_in_months,
            "second_eigenvalue_modulus": self.second_largest_eigenvalue_modulus,
            "persistent_enough": self.is_persistent_enough,
            "populated_enough": self.is_populated_enough,
            "admissible": self.is_admissible,
        }


@dataclass(frozen=True)
class StateCountSweep:
    """Every candidate, the choice made, and why."""

    evaluations: tuple[StateCountEvaluation, ...]
    models: dict[int, GaussianHiddenMarkovModel]
    recommended_state_count: int
    reason: str
    runner_up_state_count: int | None

    def table(self) -> pd.DataFrame:
        return pd.DataFrame([item.as_row() for item in self.evaluations])

    def evaluation_for(self, state_count: int) -> StateCountEvaluation:
        for item in self.evaluations:
            if item.state_count == state_count:
                return item
        raise StateSelectionError(f"{state_count} states was not part of this sweep")

    @property
    def recommended_model(self) -> GaussianHiddenMarkovModel:
        return self.models[self.recommended_state_count]

    @property
    def more_than_one_state_is_preferred_on_the_holdout(self) -> bool:
        """Do regimes exist at all? The first acceptance gate asks exactly this."""
        single = next((item for item in self.evaluations if item.state_count == 1), None)
        multiple = [item for item in self.evaluations if item.state_count > 1]
        if single is None or not multiple:
            return False
        best = max(multiple, key=lambda item: item.held_out_log_likelihood_per_month)
        return best.held_out_log_likelihood_per_month > single.held_out_log_likelihood_per_month

    @property
    def more_than_one_state_is_preferred_on_the_criterion(self) -> bool:
        single = next((item for item in self.evaluations if item.state_count == 1), None)
        multiple = [item for item in self.evaluations if item.state_count > 1]
        if single is None or not multiple:
            return False
        best = min(multiple, key=lambda item: item.bayesian_information_criterion)
        return best.bayesian_information_criterion < single.bayesian_information_criterion


def regimes_exist_from_sweep_table(sweep_table: pd.DataFrame) -> tuple[bool, str]:
    """Whether more than one state beats one, and the evidence sentence for it.

    The first acceptance gate asks exactly this question, and two callers now ask
    it: the full-sample sweep written by ``forecast fit-regimes``, and the burn-in
    sweep chosen at the first forecast date. They must ask it with one
    implementation, or an honest run and a shipped run could differ in the
    arithmetic rather than only in the evidence.

    Both criteria must agree before regimes are said to exist: the held-out log
    likelihood per month, which asks the out-of-sample question, and the Bayesian
    information criterion, which penalises the extra parameters.

    A table missing either side of that comparison — no single-regime row, or no
    multi-regime row — cannot answer the question at all. Nothing enforces that
    ``hidden_state_counts_to_search`` contains both, so that table is reachable,
    and it returns ``False`` with an evidence sentence naming the setting to
    change, the way this module's two siblings on ``StateCountSweep`` already do.
    A gate that errors is not a gate that passed.
    """
    single = sweep_table[sweep_table["states"] == 1]
    multiple = sweep_table[sweep_table["states"] > 1]
    if single.empty or multiple.empty:
        absent = "no single-regime row" if single.empty else "no multi-regime row"
        return False, (
            f"the sweep table has {absent}, so there is nothing to compare and this gate "
            "cannot be answered: regimes are not said to exist. Set "
            "`hidden_state_counts_to_search` on RunSettings to include 1 and at least one "
            "larger count, then re-run the sweep that wrote this table."
        )
    regimes_exist = bool(
        multiple["held_out_log_likelihood_per_month"].max()
        > single["held_out_log_likelihood_per_month"].iloc[0]
        and multiple["bayesian_information_criterion"].min()
        < single["bayesian_information_criterion"].iloc[0]
    )
    evidence = (
        "best multi-regime held-out log likelihood per month "
        f"{multiple['held_out_log_likelihood_per_month'].max():+.4f} against "
        f"{single['held_out_log_likelihood_per_month'].iloc[0]:+.4f} for a single regime; "
        f"information criterion {multiple['bayesian_information_criterion'].min():,.0f} "
        f"against {single['bayesian_information_criterion'].iloc[0]:,.0f}"
    )
    return regimes_exist, evidence


def sweep_state_counts(
    observations: np.ndarray,
    state_counts: Sequence[int],
    seed: int,
    restarts: int = 20,
    max_iterations: int = 500,
    tolerance: float = 1e-6,
    holdout_fraction: float = HOLDOUT_FRACTION,
    sticky_dirichlet_prior_mean_visit_months: float = 0.0,
    sticky_dirichlet_prior_row_strength: float = 0.0,
) -> StateCountSweep:
    """Fit every candidate and pick one by the rule stated in this module.

    The two ``sticky_dirichlet_prior_*`` arguments default to zero row strength,
    which is no prior: every candidate fits exactly as it always did. Research
    arm A1 passes ``RunSettings.sticky_dirichlet_prior_mean_visit_months`` and
    ``RunSettings.sticky_dirichlet_prior_row_strength`` through the burn-in sweep
    as well as every walk-forward refit, so the sweep this function runs is not
    left testing a mixture of regularised and unregularised fits.
    """
    observations = np.atleast_2d(np.asarray(observations, dtype="float64"))
    months = observations.shape[0]
    holdout_months = int(round(months * holdout_fraction))
    if holdout_months < 12:
        raise StateSelectionError(
            f"a {holdout_fraction:.0%} holdout of {months} months is only {holdout_months} "
            "months, too few to compare candidates on. Fit on a longer sample."
        )
    training = observations[: months - holdout_months]

    evaluations: list[StateCountEvaluation] = []
    models: dict[int, GaussianHiddenMarkovModel] = {}

    for state_count in sorted(state_counts):
        # Each candidate gets its own derived seed so that adding a candidate to
        # the sweep does not change the fits of the others.
        prior_beta, prior_kappa = hidden_markov.derive_sticky_dirichlet_prior(
            state_count,
            sticky_dirichlet_prior_mean_visit_months,
            sticky_dirichlet_prior_row_strength,
        )
        model = canonicalise(
            hidden_markov.fit(
                training,
                state_count=state_count,
                seed=seed + 1000 * state_count,
                restarts=restarts,
                max_iterations=max_iterations,
                tolerance=tolerance,
                transition_prior_beta=prior_beta,
                transition_prior_kappa=prior_kappa,
            )
        )
        models[state_count] = model

        responsibilities = model.smoothed_state_probabilities(training)
        population = responsibilities.sum(axis=0) / responsibilities.sum()
        durations = model.expected_state_durations()

        # The holdout likelihood is evaluated on the full sequence and the
        # training part subtracted, so the holdout is scored as the continuation
        # it actually is rather than as a fresh sequence starting from the
        # model's initial distribution.
        whole_sample_log_likelihood = model.log_likelihood(observations)
        training_log_likelihood = model.log_likelihood(training)
        held_out = (whole_sample_log_likelihood - training_log_likelihood) / holdout_months

        evaluations.append(
            StateCountEvaluation(
                state_count=state_count,
                free_parameters=model.free_parameter_count,
                training_log_likelihood=training_log_likelihood,
                bayesian_information_criterion=model.bayesian_information_criterion(training),
                held_out_log_likelihood_per_month=float(held_out),
                smallest_population_share=float(population.min()),
                shortest_expected_duration_in_months=float(durations.min()),
                second_largest_eigenvalue_modulus=model.second_largest_eigenvalue_modulus(),
                converged=bool(model.fit_report.converged) if model.fit_report else False,
            )
        )
        logger.info(
            "swept states=%d bic=%.1f holdout=%.4f min_population=%.3f min_duration=%.1f",
            state_count,
            evaluations[-1].bayesian_information_criterion,
            evaluations[-1].held_out_log_likelihood_per_month,
            evaluations[-1].smallest_population_share,
            evaluations[-1].shortest_expected_duration_in_months,
        )

    return _choose(tuple(evaluations), models)


def _choose(
    evaluations: tuple[StateCountEvaluation, ...],
    models: dict[int, GaussianHiddenMarkovModel],
) -> StateCountSweep:
    """Apply the selection rule and say in words what it did."""
    admissible = [item for item in evaluations if item.is_admissible and item.state_count > 1]
    if not admissible:
        rejected = ", ".join(
            f"{item.state_count} states (shortest visit "
            f"{item.shortest_expected_duration_in_months:.1f} months, smallest population "
            f"{item.smallest_population_share:.1%})"
            for item in evaluations
            if item.state_count > 1
        )
        raise StateSelectionError(
            "no candidate with more than one state is both persistent and populated enough: "
            f"{rejected}. The data do not support regimes at this frequency; report that rather "
            "than lowering the floors."
        )

    ranked = sorted(
        admissible, key=lambda item: item.held_out_log_likelihood_per_month, reverse=True
    )
    chosen = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None

    by_criterion = min(admissible, key=lambda item: item.bayesian_information_criterion)
    if by_criterion.state_count == chosen.state_count:
        reason = (
            f"{chosen.state_count} states wins on held-out log likelihood "
            f"({chosen.held_out_log_likelihood_per_month:.4f} per month) and the Bayesian "
            "information criterion agrees."
        )
    else:
        reason = (
            f"{chosen.state_count} states wins on held-out log likelihood "
            f"({chosen.held_out_log_likelihood_per_month:.4f} per month), while the Bayesian "
            f"information criterion prefers {by_criterion.state_count}. The holdout decides "
            "because it asks the out-of-sample question directly; the disagreement is reported "
            "rather than resolved silently."
        )

    return StateCountSweep(
        evaluations=evaluations,
        models=models,
        recommended_state_count=chosen.state_count,
        reason=reason,
        runner_up_state_count=None if runner_up is None else runner_up.state_count,
    )
