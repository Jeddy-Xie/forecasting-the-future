"""Two hidden Markov chains on two timescales, presented as one model over their product.

Research arm A4 of experiment 0002 (``proving/experiments/0002-research-slate-2026-09``).
Measured on the point-in-time panels, growth alone runs on a chain whose second
eigenvalue is about 0.943 (a twelve-month half-life), while inflation and rates
together run at 0.973 to 0.984 (25 to 43 months). One chain serving all three
columns is pulled onto the slow timescale. This model gives growth its own chain.

The model
---------
Two independent Markov chains. The **growth chain** ``S_g`` drives the growth
column; the **levels chain** ``S_l`` drives the inflation and rates columns.
Conditional on both states the two blocks are independent Gaussians::

    growth              ~ N(mu_g[S_g], var_g[S_g])
    (inflation, rates)  ~ N(mu_l[S_l], Sigma_l[S_l])

The joint state is the pair ``(S_g, S_l)``, numbered ``g * K_l + l``, so the joint
transition matrix is ``numpy.kron(A_g, A_l)`` and the joint initial distribution is
``numpy.kron(pi_g, pi_l)``. The joint emission log density is the SUM of the two
blocks' log densities.

Why it is a subclass
--------------------
Over the product space this is exactly a Gaussian hidden Markov model with
``K_g * K_l`` states, block-diagonal covariances, tied means and a Kronecker
transition matrix. So it inherits the forward pass, the filtered probabilities,
Viterbi, the stationary distribution, the second eigenvalue and the projection
unchanged, and the walk-forward and the forecast composition use it without
knowing it is two chains. Only the emission density (a sum of two blocks), the
parameter count, the serialisation and the fit differ.

Fitting
-------
Expectation maximisation over the product space. The E-step computes the joint
posteriors over all ``K_g * K_l`` states with the inherited forward and backward
passes. The M-step marginalises the expected transition counts and the state
occupancies to each chain and re-estimates each chain from its own marginals.

That M-step is exact, not an approximation. The complete-data log likelihood of
the product model separates: ``log kron(A_g, A_l)[(g,l),(g',l')]`` is
``log A_g[g,g'] + log A_l[l,l']``, and the emission is a sum of the two blocks. Its
expectation under the joint posterior therefore splits into a growth part that
depends only on the growth marginals and a levels part that depends only on the
levels marginals, and each is maximised by the usual single-chain formulas applied
to those marginals. Expectation maximisation's monotonicity theorem applies to the
joint likelihood unchanged, so **the monitored quantity is the joint log
likelihood**, guarded by the allowance ADR 0007 set for every fit in the project
(``_monotonicity_allowance``, imported, never widened). No prior is involved, so
there is no log posterior to monitor instead.

A consequence worth stating: because the chains are independent and each block
depends on only one of them, the joint likelihood FACTORISES into the growth
chain's likelihood times the levels chain's, and the joint filtered distribution is
the Kronecker product of the two chains' filtered distributions. The tests pin
both. The product-space fit is what the pre-registration specifies; it differs
from two separate fits only in that restarts are paired and convergence is judged
on the joint likelihood.

Labelling
---------
Each chain is canonicalised on its own before the product is formed: growth states
by growth mean, levels states by inflation mean then rates mean. The product
numbering ``g * K_l + l`` is then also the order ``state_labelling.canonical_order``
gives the product, so joint regime 0 is the weakest growth with the lowest
inflation, at every refit.
"""

from __future__ import annotations

import logging
from typing import Any, Self

import numpy as np
from scipy.special import logsumexp

from economic_regime_forecasting.configuration.registry import ModelDimension
from economic_regime_forecasting.features.observation_matrix import DIMENSION_ORDER
from economic_regime_forecasting.models import gaussian_hidden_markov_model as hidden_markov
from economic_regime_forecasting.models.gaussian_hidden_markov_model import (
    MINIMUM_STATE_RESPONSIBILITY,
    FitReport,
    GaussianHiddenMarkovModel,
    HiddenMarkovModelError,
)
from economic_regime_forecasting.models.state_labelling import canonicalise

logger = logging.getLogger(__name__)

GROWTH_COLUMNS: tuple[int, ...] = (DIMENSION_ORDER.index(ModelDimension.GROWTH),)
"""The observation column the growth chain drives, found by name, never by position."""

LEVELS_COLUMNS: tuple[int, ...] = (
    DIMENSION_ORDER.index(ModelDimension.INFLATION),
    DIMENSION_ORDER.index(ModelDimension.RATES),
)
"""The observation columns the levels chain drives: inflation, then rates."""

MAXIMUM_STATES_PER_CHAIN = 4
"""Experiment 0002, arm A4: each chain's count is chosen from candidates 1 to 4, so
the product never exceeds the registered maximum of 16 joint states."""

LEVELS_CHAIN_SEED_OFFSET = 1
"""The levels chain draws its starting points from ``seed + 1``, the growth chain
from ``seed``. Two streams, so that a chain's starting points do not depend on the
other chain's state count, and a one-state growth chain leaves the levels chain's
fit exactly what a single-chain fit on the levels block would be."""

MODEL_CLASS = "two_timescale_chains"
"""Written into every serialised two-chain model, so a loader never mistakes one
for a single chain."""


class TwoChainStateCount(int):
    """The number of joint regimes, carrying how it factors into the two chains.

    It IS the joint count wherever an integer is read: printed, compared, written
    to a results frame or a manifest, it is ``K_g * K_l``. The walk-forward reads the
    factorisation off it to know it must fit two chains, which is how a burn-in
    choice reaches the fit without any caller in between having to know.
    """

    growth_chain_state_count: int
    levels_chain_state_count: int

    def __new__(cls, growth_chain_state_count: int, levels_chain_state_count: int) -> Self:
        growth = int(growth_chain_state_count)
        levels = int(levels_chain_state_count)
        if growth < 1 or levels < 1:
            raise HiddenMarkovModelError(
                f"each chain needs at least one state; got {growth} for growth and {levels} "
                "for inflation and rates"
            )
        instance = super().__new__(cls, growth * levels)
        instance.growth_chain_state_count = growth
        instance.levels_chain_state_count = levels
        return instance

    def __reduce__(self) -> tuple[type[TwoChainStateCount], tuple[int, int]]:
        # An int subclass would otherwise be rebuilt from its value alone, which
        # cannot say how it factors.
        return (TwoChainStateCount, (self.growth_chain_state_count, self.levels_chain_state_count))

    @property
    def label(self) -> str:
        """``growth x levels``, for file names and messages."""
        return f"{self.growth_chain_state_count}x{self.levels_chain_state_count}"

    def describe(self) -> str:
        return (
            f"{int(self)} joint regimes: {self.growth_chain_state_count} growth states times "
            f"{self.levels_chain_state_count} inflation-and-rates states"
        )


class TwoTimescaleHiddenMarkovModel(GaussianHiddenMarkovModel):
    """A growth chain and a levels chain, exposed as one chain over their product."""

    def __init__(
        self,
        growth_chain: GaussianHiddenMarkovModel,
        levels_chain: GaussianHiddenMarkovModel,
        fit_report: FitReport | None = None,
    ) -> None:
        if growth_chain.dimension_count != len(GROWTH_COLUMNS):
            raise HiddenMarkovModelError(
                f"the growth chain must model {len(GROWTH_COLUMNS)} column, not "
                f"{growth_chain.dimension_count}"
            )
        if levels_chain.dimension_count != len(LEVELS_COLUMNS):
            raise HiddenMarkovModelError(
                f"the levels chain must model {len(LEVELS_COLUMNS)} columns, not "
                f"{levels_chain.dimension_count}"
            )
        self.growth_chain = growth_chain
        self.levels_chain = levels_chain

        growth_states = growth_chain.state_count
        levels_states = levels_chain.state_count
        dimensions = len(GROWTH_COLUMNS) + len(LEVELS_COLUMNS)
        growth_index = list(GROWTH_COLUMNS)
        levels_index = list(LEVELS_COLUMNS)

        # Joint state g * K_l + l: the growth parameters repeat K_l times in a row,
        # the levels parameters cycle K_g times. The same order numpy.kron uses.
        means = np.empty((growth_states * levels_states, dimensions), dtype="float64")
        means[:, growth_index] = np.repeat(growth_chain.means, levels_states, axis=0)
        means[:, levels_index] = np.tile(levels_chain.means, (growth_states, 1))

        # Block-diagonal: each block's covariance on its own columns, zero between them.
        covariances = np.zeros((growth_states * levels_states, dimensions, dimensions))
        growth_rows, growth_columns = np.ix_(growth_index, growth_index)
        levels_rows, levels_columns = np.ix_(levels_index, levels_index)
        covariances[:, growth_rows, growth_columns] = np.repeat(
            growth_chain.covariances, levels_states, axis=0
        )
        covariances[:, levels_rows, levels_columns] = np.tile(
            levels_chain.covariances, (growth_states, 1, 1)
        )

        super().__init__(
            initial_distribution=np.kron(
                growth_chain.initial_distribution, levels_chain.initial_distribution
            ),
            transition_matrix=np.kron(
                growth_chain.transition_matrix, levels_chain.transition_matrix
            ),
            means=means,
            covariances=covariances,
            covariance_type="full",
            fit_report=fit_report,
        )

    # ---------------------------------------------------------------- shape

    @property
    def state_count(self) -> TwoChainStateCount:
        return TwoChainStateCount(self.growth_chain.state_count, self.levels_chain.state_count)

    @property
    def free_parameter_count(self) -> int:
        """The two chains' parameters, which is all the product has."""
        return self.growth_chain.free_parameter_count + self.levels_chain.free_parameter_count

    # ------------------------------------------------------------ densities

    def log_emission_probabilities(self, observations: np.ndarray) -> np.ndarray:
        """Log density of each observation under each joint state, (months, K_g * K_l).

        The sum of the growth block's log density under the growth state and the
        levels block's under the levels state, as the pre-registration specifies.
        """
        observations = np.atleast_2d(np.asarray(observations, dtype="float64"))
        months, dimensions = observations.shape
        if dimensions != self.dimension_count:
            raise HiddenMarkovModelError(
                f"observations have {dimensions} dimensions, the model has {self.dimension_count}"
            )
        growth = self.growth_chain.log_emission_probabilities(observations[:, list(GROWTH_COLUMNS)])
        levels = self.levels_chain.log_emission_probabilities(observations[:, list(LEVELS_COLUMNS)])
        joint: np.ndarray = (growth[:, :, None] + levels[:, None, :]).reshape(months, -1)
        return joint

    # ------------------------------------------------------ serialisation

    def to_dictionary(self) -> dict[str, Any]:
        """The two chains, each serialised as the single-chain model it is.

        Deliberately without the product-space arrays, so the single-chain loader
        fails on this payload instead of silently reading it as one chain.
        """
        return {
            "model_class": MODEL_CLASS,
            "growth_chain": self.growth_chain.to_dictionary(),
            "levels_chain": self.levels_chain.to_dictionary(),
            "fit_report": _fit_report_to_dictionary(self.fit_report),
        }

    @classmethod
    def from_dictionary(cls, payload: dict[str, Any]) -> Self:
        if payload.get("model_class") != MODEL_CLASS:
            raise HiddenMarkovModelError(
                f"this payload is not a two-chain model (model_class "
                f"{payload.get('model_class')!r}); read it with regime_model_from_dictionary"
            )
        return cls(
            growth_chain=GaussianHiddenMarkovModel.from_dictionary(payload["growth_chain"]),
            levels_chain=GaussianHiddenMarkovModel.from_dictionary(payload["levels_chain"]),
            fit_report=_fit_report_from_dictionary(payload.get("fit_report")),
        )


def regime_model_from_dictionary(payload: dict[str, Any]) -> GaussianHiddenMarkovModel:
    """Read back either kind of fitted model, by what the payload says it is."""
    model_class = payload.get("model_class")
    if model_class == MODEL_CLASS:
        return TwoTimescaleHiddenMarkovModel.from_dictionary(payload)
    if model_class is not None:
        raise HiddenMarkovModelError(
            f"unknown model_class {model_class!r} in a fitted-model payload. Delete the cached "
            "file and refit rather than guessing what it holds."
        )
    return GaussianHiddenMarkovModel.from_dictionary(payload)


def _fit_report_to_dictionary(report: FitReport | None) -> dict[str, Any] | None:
    if report is None:
        return None
    return {
        "log_likelihood": report.log_likelihood,
        "iterations": report.iterations,
        "converged": report.converged,
        "restarts": report.restarts,
        "seed": report.seed,
        "best_restart": report.best_restart,
        "log_likelihood_by_restart": list(report.log_likelihood_by_restart),
    }


def _fit_report_from_dictionary(report: dict[str, Any] | None) -> FitReport | None:
    if report is None:
        return None
    return FitReport(
        log_likelihood=report["log_likelihood"],
        iterations=report["iterations"],
        converged=report["converged"],
        restarts=report["restarts"],
        seed=report["seed"],
        best_restart=report["best_restart"],
        log_likelihood_by_restart=tuple(report["log_likelihood_by_restart"]),
    )


# ---------------------------------------------------------------------------
# Fitting
# ---------------------------------------------------------------------------


def fit(
    observations: np.ndarray,
    growth_chain_state_count: int,
    levels_chain_state_count: int,
    seed: int,
    restarts: int = 20,
    max_iterations: int = 500,
    tolerance: float = 1e-6,
) -> TwoTimescaleHiddenMarkovModel:
    """Fit both chains jointly by expectation maximisation over the product space.

    Each restart pairs a growth starting point with a levels starting point, drawn
    by the single-chain fitter's own rule (k-means++ means, a random persistence
    between 0.50 and 0.98, pooled spread), and the restart with the best JOINT log
    likelihood wins. Convergence is judged on the joint likelihood with the same
    relative tolerance as every other fit. The chains are canonicalised before the
    product is formed.
    """
    observations = np.atleast_2d(np.asarray(observations, dtype="float64"))
    months, dimensions = observations.shape
    if dimensions != len(GROWTH_COLUMNS) + len(LEVELS_COLUMNS):
        raise HiddenMarkovModelError(
            f"a two-chain fit needs the {len(GROWTH_COLUMNS) + len(LEVELS_COLUMNS)} observation "
            f"columns growth, inflation and rates; got {dimensions}"
        )
    joint_state_count = growth_chain_state_count * levels_chain_state_count
    if months <= joint_state_count:
        raise HiddenMarkovModelError(
            f"cannot fit {joint_state_count} joint states to {months} months of data; there must "
            "be more observations than states, and in practice many more"
        )
    if not np.isfinite(observations).all():
        raise HiddenMarkovModelError(
            "observations contain non-finite values, which make every emission density "
            "undefined. Drop or impute them before fitting, deliberately."
        )

    growth_observations = observations[:, list(GROWTH_COLUMNS)]
    levels_observations = observations[:, list(LEVELS_COLUMNS)]
    growth_generator = np.random.default_rng(seed)
    levels_generator = np.random.default_rng(seed + LEVELS_CHAIN_SEED_OFFSET)
    pooled_growth = _pooled_covariance(growth_observations)
    pooled_levels = _pooled_covariance(levels_observations)

    best_model: TwoTimescaleHiddenMarkovModel | None = None
    best_log_likelihood = -np.inf
    best_restart = -1
    best_iterations = 0
    best_converged = False
    log_likelihood_by_restart: list[float] = []

    for restart in range(restarts):
        candidate = TwoTimescaleHiddenMarkovModel(
            growth_chain=hidden_markov._initial_model(
                growth_observations,
                growth_chain_state_count,
                growth_generator,
                pooled_growth,
                "full",
            ),
            levels_chain=hidden_markov._initial_model(
                levels_observations,
                levels_chain_state_count,
                levels_generator,
                pooled_levels,
                "full",
            ),
        )
        candidate, log_likelihood, iterations, converged = run_expectation_maximisation(
            candidate, observations, max_iterations, tolerance, pooled_growth, pooled_levels
        )
        log_likelihood_by_restart.append(log_likelihood)
        if log_likelihood > best_log_likelihood:
            best_model = candidate
            best_log_likelihood = log_likelihood
            best_restart = restart
            best_iterations = iterations
            best_converged = converged

    if best_model is None:  # pragma: no cover - restarts is at least one
        raise HiddenMarkovModelError("no restart produced a model")

    logger.info(
        "fitted two chains growth_states=%d levels_states=%d log_likelihood=%.3f restarts=%d "
        "converged=%s",
        growth_chain_state_count,
        levels_chain_state_count,
        best_log_likelihood,
        restarts,
        best_converged,
    )
    return TwoTimescaleHiddenMarkovModel(
        growth_chain=canonicalise(best_model.growth_chain),
        levels_chain=canonicalise(best_model.levels_chain),
        fit_report=FitReport(
            log_likelihood=best_log_likelihood,
            iterations=best_iterations,
            converged=best_converged,
            restarts=restarts,
            seed=seed,
            best_restart=best_restart,
            log_likelihood_by_restart=tuple(log_likelihood_by_restart),
        ),
    )


def _pooled_covariance(block: np.ndarray) -> np.ndarray:
    """The block's own pooled covariance, ridged as the single-chain fitter ridges it."""
    columns = block.shape[1]
    return hidden_markov._regularised_covariance(
        np.cov(block, rowvar=False).reshape(columns, columns)
    )


def run_expectation_maximisation(
    model: TwoTimescaleHiddenMarkovModel,
    observations: np.ndarray,
    max_iterations: int,
    tolerance: float,
    pooled_growth: np.ndarray,
    pooled_levels: np.ndarray,
    log_likelihood_trace: list[float] | None = None,
) -> tuple[TwoTimescaleHiddenMarkovModel, float, int, bool]:
    """Iterate until the joint log likelihood stops moving.

    The loop is the single-chain loop's, line for line: the same monotonicity
    guard on the same allowance, the same relative convergence rule, the same
    re-evaluation on the iteration-cap path. ``log_likelihood_trace``, when given,
    receives the joint log likelihood at every iteration, so a test can check each
    maximisation step on its own.
    """
    previous_log_likelihood = -np.inf
    log_likelihood = -np.inf
    converged = False
    iteration = 0

    # The counter is read after the loop to report how many iterations it took.
    for iteration in range(1, max_iterations + 1):  # noqa: B007
        log_emissions = model.log_emission_probabilities(observations)
        log_alpha = model._forward(log_emissions)
        log_beta = model._backward(log_emissions)
        log_likelihood = float(logsumexp(log_alpha[-1]))
        if log_likelihood_trace is not None:
            log_likelihood_trace.append(log_likelihood)

        if log_likelihood < previous_log_likelihood - hidden_markov._monotonicity_allowance(
            previous_log_likelihood
        ):
            raise HiddenMarkovModelError(
                "the joint log likelihood of the two chains fell from "
                f"{previous_log_likelihood:.6f} to {log_likelihood:.6f}. The marginalised "
                "maximisation step is the exact maximiser for the product model, so this is a "
                "bug in the update equations, not a property of the data."
            )
        if abs(log_likelihood - previous_log_likelihood) < tolerance * max(
            1.0, abs(previous_log_likelihood)
        ):
            converged = True
            break
        previous_log_likelihood = log_likelihood

        model = _maximisation_step(
            model,
            observations,
            log_emissions,
            log_alpha,
            log_beta,
            log_likelihood,
            pooled_growth,
            pooled_levels,
        )

    if not converged:
        log_likelihood = model.log_likelihood(observations)
        if log_likelihood_trace is not None:
            log_likelihood_trace.append(log_likelihood)
    return model, log_likelihood, iteration, converged


def _maximisation_step(
    model: TwoTimescaleHiddenMarkovModel,
    observations: np.ndarray,
    log_emissions: np.ndarray,
    log_alpha: np.ndarray,
    log_beta: np.ndarray,
    log_likelihood: float,
    pooled_growth: np.ndarray,
    pooled_levels: np.ndarray,
) -> TwoTimescaleHiddenMarkovModel:
    """Joint posteriors over the product space, marginalised to each chain."""
    months = log_emissions.shape[0]
    growth_states = model.growth_chain.state_count
    levels_states = model.levels_chain.state_count

    joint_responsibilities = np.exp(log_alpha + log_beta - log_likelihood)

    log_transition = hidden_markov._safe_log(model.transition_matrix)
    log_transition_counts = (
        log_alpha[:-1, :, None]
        + log_transition[None, :, :]
        + (log_emissions[1:] + log_beta[1:])[:, None, :]
        - log_likelihood
    )
    joint_transition_counts = np.exp(logsumexp(log_transition_counts, axis=0))

    # Joint index g * K_l + l, so axis order after the reshape is (g, l) then (g', l').
    counts = joint_transition_counts.reshape(
        growth_states, levels_states, growth_states, levels_states
    )
    responsibilities = joint_responsibilities.reshape(months, growth_states, levels_states)

    return TwoTimescaleHiddenMarkovModel(
        growth_chain=_chain_from_marginals(
            observations[:, list(GROWTH_COLUMNS)],
            responsibilities.sum(axis=2),
            counts.sum(axis=(1, 3)),
            pooled_growth,
            "growth",
        ),
        levels_chain=_chain_from_marginals(
            observations[:, list(LEVELS_COLUMNS)],
            responsibilities.sum(axis=1),
            counts.sum(axis=(0, 2)),
            pooled_levels,
            "inflation and rates",
        ),
    )


def _chain_from_marginals(
    block: np.ndarray,
    responsibilities: np.ndarray,
    transition_counts: np.ndarray,
    pooled_covariance: np.ndarray,
    chain_name: str,
) -> GaussianHiddenMarkovModel:
    """One chain's parameters from its own marginal statistics.

    The single-chain maximisation step's formulas, in its order: the initial
    distribution from the first month's occupancy, each transition row from the
    expected counts (an abandoned row falls back to uniform, as ADR 0007 decided),
    means and ridged full covariances from the occupancy-weighted block.
    """
    states = responsibilities.shape[1]
    state_totals = np.maximum(responsibilities.sum(axis=0), MINIMUM_STATE_RESPONSIBILITY)
    initial_distribution = responsibilities[0] / responsibilities[0].sum()

    row_totals = transition_counts.sum(axis=1)
    abandoned = row_totals <= MINIMUM_STATE_RESPONSIBILITY
    transition_matrix = np.where(
        abandoned[:, None],
        1.0 / states,
        transition_counts / np.maximum(row_totals, MINIMUM_STATE_RESPONSIBILITY)[:, None],
    )
    transition_matrix = transition_matrix / transition_matrix.sum(axis=1, keepdims=True)
    if bool(abandoned.any()):
        logger.warning(
            "state_abandoned chain=%s states=%s; their transition rows fall back to uniform",
            chain_name,
            np.flatnonzero(abandoned).tolist(),
        )

    means = (responsibilities.T @ block) / state_totals[:, None]
    covariances = np.empty((states, block.shape[1], block.shape[1]))
    for state in range(states):
        deviations = block - means[state]
        weighted = deviations * responsibilities[:, state][:, None]
        covariance = (weighted.T @ deviations) / state_totals[state]
        covariances[state] = hidden_markov._regularised_covariance(covariance, pooled_covariance)

    return GaussianHiddenMarkovModel(
        initial_distribution=initial_distribution,
        transition_matrix=transition_matrix,
        means=means,
        covariances=covariances,
        covariance_type="full",
    )
