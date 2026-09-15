"""A Gaussian hidden Markov model, written out rather than imported.

The model is standard: a latent state that evolves as a first-order Markov chain,
and an observation drawn from a state-specific multivariate normal. Fitting is by
the Baum-Welch algorithm, decoding by Viterbi, and everything runs in log space
so that a seventy-year monthly sample does not underflow.

Why this is written here rather than pulled from a package
----------------------------------------------------------
One requirement decides it. A backtest may only use **filtered** state
probabilities, meaning the distribution over the state at month t given
observations up to and including t. The available libraries expose *smoothed*
probabilities, which condition on the whole sample including months after t.
Using smoothed probabilities in a backtest is look-ahead of the purest kind, and
it does not announce itself: the numbers are plausible, merely impossible.

Making a library hand back filtered probabilities means reaching past its public
surface into its emission likelihood and running the forward pass anyway. At that
point the forward pass is written either way, and writing all of it buys exact
control over restarts, seeding and determinism, with no dependency to pin.

Conventions used throughout
---------------------------
``observations`` is shaped (months, dimensions). ``initial_distribution`` is over
states at the first month. ``transition_matrix[i, j]`` is the probability of
moving from state i to state j, so rows sum to one and a distribution advances by
right-multiplication.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Self

import numpy as np
import pandas as pd
from scipy.linalg import solve_triangular
from scipy.special import logsumexp

logger = logging.getLogger(__name__)

_LOG_TWO_PI = float(np.log(2.0 * np.pi))

COVARIANCE_RIDGE = 1e-6
"""Fraction of the pooled variance added to each covariance diagonal.

A state that captures few months can produce a singular covariance, whose inverse
is infinite and whose likelihood is meaningless. The ridge keeps every covariance
invertible at a cost far below the measurement error in the data itself."""

MINIMUM_STATE_RESPONSIBILITY = 1e-8
"""Floor on a state's total responsibility, so a collapsed state divides safely.

A collapsed state is not hidden by this: it shows up with a near-zero population,
which model selection reads as a reason to prefer fewer states."""


class HiddenMarkovModelError(RuntimeError):
    """A fit failed, or a model was asked for something it cannot provide."""


@dataclass(frozen=True)
class FitReport:
    """What happened during one fit, for the manifest and for model selection."""

    log_likelihood: float
    iterations: int
    converged: bool
    restarts: int
    seed: int
    best_restart: int
    log_likelihood_by_restart: tuple[float, ...]

    def describe(self) -> str:
        status = "converged" if self.converged else "hit the iteration cap"
        return (
            f"log likelihood {self.log_likelihood:,.2f} after {self.iterations} iterations "
            f"({status}); best of {self.restarts} restarts"
        )


class GaussianHiddenMarkovModel:
    """A fitted, or fittable, Gaussian hidden Markov model."""

    def __init__(
        self,
        initial_distribution: np.ndarray,
        transition_matrix: np.ndarray,
        means: np.ndarray,
        covariances: np.ndarray,
        covariance_type: str = "full",
        fit_report: FitReport | None = None,
    ) -> None:
        self.initial_distribution = np.asarray(initial_distribution, dtype="float64")
        self.transition_matrix = np.asarray(transition_matrix, dtype="float64")
        self.means = np.asarray(means, dtype="float64")
        self.covariances = np.asarray(covariances, dtype="float64")
        self.covariance_type = covariance_type
        self.fit_report = fit_report
        self._validate()

    # ---------------------------------------------------------------- shape

    @property
    def state_count(self) -> int:
        return int(self.means.shape[0])

    @property
    def dimension_count(self) -> int:
        return int(self.means.shape[1])

    def _validate(self) -> None:
        states, dimensions = self.means.shape
        if self.transition_matrix.shape != (states, states):
            raise HiddenMarkovModelError(
                f"transition matrix is {self.transition_matrix.shape}, expected "
                f"{(states, states)} to match {states} states"
            )
        if self.covariances.shape != (states, dimensions, dimensions):
            raise HiddenMarkovModelError(
                f"covariances are {self.covariances.shape}, expected "
                f"{(states, dimensions, dimensions)}"
            )
        if not np.allclose(self.transition_matrix.sum(axis=1), 1.0):
            raise HiddenMarkovModelError(
                "transition matrix rows must each sum to one; they sum to "
                f"{self.transition_matrix.sum(axis=1)}"
            )
        if not np.isclose(self.initial_distribution.sum(), 1.0):
            raise HiddenMarkovModelError(
                f"initial distribution sums to {self.initial_distribution.sum()}, not one"
            )

    # ------------------------------------------------------------ densities

    def log_emission_probabilities(self, observations: np.ndarray) -> np.ndarray:
        """Log density of each observation under each state. Shaped (months, states)."""
        observations = np.atleast_2d(np.asarray(observations, dtype="float64"))
        months, dimensions = observations.shape
        if dimensions != self.dimension_count:
            raise HiddenMarkovModelError(
                f"observations have {dimensions} dimensions, the model has {self.dimension_count}"
            )

        log_densities = np.empty((months, self.state_count), dtype="float64")
        for state in range(self.state_count):
            covariance = self.covariances[state]
            try:
                cholesky = np.linalg.cholesky(covariance)
            except np.linalg.LinAlgError as error:
                raise HiddenMarkovModelError(
                    f"the covariance of state {state} is not positive definite, so its density "
                    "is undefined. This normally means the state captured almost no months; "
                    "refit with fewer states."
                ) from error
            deviations = observations - self.means[state]
            solved = solve_triangular(cholesky, deviations.T, lower=True)
            squared_distance = np.sum(solved**2, axis=0)
            log_determinant = 2.0 * float(np.sum(np.log(np.diag(cholesky))))
            log_densities[:, state] = -0.5 * (
                squared_distance + log_determinant + dimensions * _LOG_TWO_PI
            )
        return log_densities

    # -------------------------------------------------------- forward pass

    def _forward(self, log_emissions: np.ndarray) -> np.ndarray:
        """Log forward variables. Row t conditions on months up to and including t."""
        months = log_emissions.shape[0]
        log_transition = _safe_log(self.transition_matrix)
        log_alpha = np.empty_like(log_emissions)
        log_alpha[0] = _safe_log(self.initial_distribution) + log_emissions[0]
        for month in range(1, months):
            log_alpha[month] = log_emissions[month] + logsumexp(
                log_alpha[month - 1][:, None] + log_transition, axis=0
            )
        return log_alpha

    def _backward(self, log_emissions: np.ndarray) -> np.ndarray:
        months = log_emissions.shape[0]
        log_transition = _safe_log(self.transition_matrix)
        log_beta = np.zeros_like(log_emissions)
        for month in range(months - 2, -1, -1):
            log_beta[month] = logsumexp(
                log_transition + (log_emissions[month + 1] + log_beta[month + 1])[None, :],
                axis=1,
            )
        return log_beta

    def log_likelihood(self, observations: np.ndarray) -> float:
        """Log probability of the whole sequence under this model."""
        log_alpha = self._forward(self.log_emission_probabilities(observations))
        return float(logsumexp(log_alpha[-1]))

    def filtered_state_probabilities(self, observations: np.ndarray) -> np.ndarray:
        """P(state at month t | observations up to and including t).

        **This is the only state distribution a backtest may use.** It conditions
        on the past and the present, never on the future, which is what makes a
        forecast issued at month t a forecast rather than a recollection.
        """
        log_alpha = self._forward(self.log_emission_probabilities(observations))
        filtered: np.ndarray = np.exp(log_alpha - logsumexp(log_alpha, axis=1, keepdims=True))
        return filtered

    def smoothed_state_probabilities(self, observations: np.ndarray) -> np.ndarray:
        """P(state at month t | the entire sample).

        For narrative and diagnostics only. Every month's answer here uses months
        that came after it, so a backtest built on this would be reading its own
        future. Named at length so nobody reaches for it by accident.
        """
        log_emissions = self.log_emission_probabilities(observations)
        log_alpha = self._forward(log_emissions)
        log_beta = self._backward(log_emissions)
        log_gamma = log_alpha + log_beta
        smoothed: np.ndarray = np.exp(log_gamma - logsumexp(log_gamma, axis=1, keepdims=True))
        return smoothed

    def most_likely_state_path(self, observations: np.ndarray) -> np.ndarray:
        """The Viterbi path: the single most probable sequence of states."""
        log_emissions = self.log_emission_probabilities(observations)
        months, states = log_emissions.shape
        log_transition = _safe_log(self.transition_matrix)

        best_score = np.empty((months, states), dtype="float64")
        best_previous = np.zeros((months, states), dtype="int64")
        best_score[0] = _safe_log(self.initial_distribution) + log_emissions[0]
        for month in range(1, months):
            candidates = best_score[month - 1][:, None] + log_transition
            best_previous[month] = np.argmax(candidates, axis=0)
            best_score[month] = log_emissions[month] + np.max(candidates, axis=0)

        path = np.empty(months, dtype="int64")
        path[-1] = int(np.argmax(best_score[-1]))
        for month in range(months - 2, -1, -1):
            path[month] = best_previous[month + 1, path[month + 1]]
        return path

    # ------------------------------------------------------- chain summary

    def stationary_distribution(self) -> np.ndarray:
        """The chain's long-run distribution: the left eigenvector at eigenvalue one.

        This is what every forecast converges to. Once a projected distribution is
        indistinguishable from it, the model is reporting the unconditional base
        rate and nothing else, which is the finding this project is built to
        measure rather than hide.
        """
        eigenvalues, eigenvectors = np.linalg.eig(self.transition_matrix.T)
        index = int(np.argmin(np.abs(eigenvalues - 1.0)))
        vector = np.real(eigenvectors[:, index])
        vector = np.abs(vector)
        total = vector.sum()
        if total <= 0:
            raise HiddenMarkovModelError(
                "the transition matrix has no stationary distribution, which means it is not a "
                "valid stochastic matrix"
            )
        normalised: np.ndarray = vector / total
        return normalised

    def second_largest_eigenvalue_modulus(self) -> float:
        """How fast the chain forgets where it started.

        The distance from a projected distribution to the stationary one decays
        like this number raised to the horizon. A value of 0.97 forgets slowly; a
        value of 0.7 has forgotten everything within a couple of years.
        """
        eigenvalues = np.linalg.eigvals(self.transition_matrix)
        moduli = np.sort(np.abs(eigenvalues))[::-1]
        if moduli.size < 2:
            return 0.0
        return float(moduli[1])

    def expected_state_durations(self) -> np.ndarray:
        """Expected months spent in each state per visit, one over one minus the
        self-transition probability."""
        self_transitions = np.clip(np.diag(self.transition_matrix), 0.0, 1.0 - 1e-12)
        return 1.0 / (1.0 - self_transitions)

    def project_state_distribution(
        self, state_distribution: np.ndarray, horizon_in_months: int
    ) -> np.ndarray:
        """Advance a state distribution ``horizon_in_months`` steps.

        Computed by repeated squaring of the transition matrix rather than by a
        loop, so a hundred and twenty step projection costs seven matrix products.
        """
        if horizon_in_months < 0:
            raise HiddenMarkovModelError(f"horizon must not be negative, got {horizon_in_months}")
        projected = np.asarray(state_distribution, dtype="float64")
        matrix_power = np.linalg.matrix_power(self.transition_matrix, horizon_in_months)
        result: np.ndarray = projected @ matrix_power
        normalised: np.ndarray = result / result.sum()
        return normalised

    @property
    def free_parameter_count(self) -> int:
        """Parameters estimated, for the Bayesian information criterion.

        An initial distribution over K states costs K minus one; each transition
        row costs K minus one; each state's mean costs D; each full covariance
        costs D times D plus one over two.
        """
        states, dimensions = self.means.shape
        initial = states - 1
        transitions = states * (states - 1)
        means = states * dimensions
        covariances = (
            states * dimensions * (dimensions + 1) // 2
            if self.covariance_type == "full"
            else states * dimensions
        )
        return int(initial + transitions + means + covariances)

    def bayesian_information_criterion(self, observations: np.ndarray) -> float:
        """Lower is better. Penalises parameters by the log of the sample size."""
        months = np.atleast_2d(observations).shape[0]
        return float(
            -2.0 * self.log_likelihood(observations) + self.free_parameter_count * np.log(months)
        )

    # ------------------------------------------------------ serialisation

    def to_dictionary(self) -> dict[str, Any]:
        return {
            "initial_distribution": self.initial_distribution.tolist(),
            "transition_matrix": self.transition_matrix.tolist(),
            "means": self.means.tolist(),
            "covariances": self.covariances.tolist(),
            "covariance_type": self.covariance_type,
            "fit_report": None
            if self.fit_report is None
            else {
                "log_likelihood": self.fit_report.log_likelihood,
                "iterations": self.fit_report.iterations,
                "converged": self.fit_report.converged,
                "restarts": self.fit_report.restarts,
                "seed": self.fit_report.seed,
                "best_restart": self.fit_report.best_restart,
                "log_likelihood_by_restart": list(self.fit_report.log_likelihood_by_restart),
            },
        }

    @classmethod
    def from_dictionary(cls, payload: dict[str, Any]) -> Self:
        report = payload.get("fit_report")
        return cls(
            initial_distribution=np.array(payload["initial_distribution"]),
            transition_matrix=np.array(payload["transition_matrix"]),
            means=np.array(payload["means"]),
            covariances=np.array(payload["covariances"]),
            covariance_type=payload.get("covariance_type", "full"),
            fit_report=None
            if report is None
            else FitReport(
                log_likelihood=report["log_likelihood"],
                iterations=report["iterations"],
                converged=report["converged"],
                restarts=report["restarts"],
                seed=report["seed"],
                best_restart=report["best_restart"],
                log_likelihood_by_restart=tuple(report["log_likelihood_by_restart"]),
            ),
        )


def _safe_log(values: np.ndarray) -> np.ndarray:
    """Log with zeros mapped to negative infinity instead of a warning."""
    with np.errstate(divide="ignore"):
        logged: np.ndarray = np.log(values)
    return logged


# ---------------------------------------------------------------------------
# Fitting
# ---------------------------------------------------------------------------


def fit(
    observations: np.ndarray,
    state_count: int,
    seed: int,
    restarts: int = 20,
    max_iterations: int = 500,
    tolerance: float = 1e-6,
    covariance_type: str = "full",
    seed_means_by_quadrant_structure: bool = False,
) -> GaussianHiddenMarkovModel:
    """Fit by Baum-Welch from several random starts, keeping the best likelihood.

    Expectation maximisation finds a local optimum, and for a hidden Markov model
    the surface has many. Restarts are not a nicety: a single start regularly
    lands on a solution twenty log-likelihood points worse than the best of
    twenty, which changes which number of states the selection criteria prefer.

    Starting points are deliberately spread across persistence levels. Each
    restart draws a self-transition probability uniformly between 0.50 and 0.98,
    so the search covers chains that barely persist as well as chains that hold a
    state for years. By default the means are seeded by the k-means++ rule, which
    spreads them over the observed cloud rather than clustering them by luck.

    ``seed_means_by_quadrant_structure`` replaces that spread with a structural
    prior: All Weather's growth-by-inflation 2x2, imposed as the four starting
    means (research arm A2-quadrant-structure-levels). It requires exactly four
    states and is computed once, deterministically, from the observations, so
    every restart begins from the same four centroids; only the transition
    matrix's persistence draw still differs restart to restart. Either way the
    likelihood, not the starting point, decides what comes out.
    """
    observations = np.atleast_2d(np.asarray(observations, dtype="float64"))
    months, dimensions = observations.shape
    if months <= state_count:
        raise HiddenMarkovModelError(
            f"cannot fit {state_count} states to {months} months of data; there must be more "
            "observations than states, and in practice many more"
        )
    if not np.isfinite(observations).all():
        raise HiddenMarkovModelError(
            "observations contain non-finite values, which make every emission density "
            "undefined. Drop or impute them before fitting, deliberately."
        )

    generator = np.random.default_rng(seed)
    pooled_covariance = _regularised_covariance(
        np.cov(observations, rowvar=False).reshape(dimensions, dimensions)
    )

    quadrant_means: np.ndarray | None = None
    if seed_means_by_quadrant_structure:
        quadrant_means = _seed_means_by_quadrant_centroids(observations, state_count)

    best_model: GaussianHiddenMarkovModel | None = None
    best_log_likelihood = -np.inf
    best_restart = -1
    best_iterations = 0
    best_converged = False
    log_likelihood_by_restart: list[float] = []

    for restart in range(restarts):
        candidate = _initial_model(
            observations,
            state_count,
            generator,
            pooled_covariance,
            covariance_type,
            means_override=quadrant_means,
        )
        candidate, log_likelihood, iterations, converged = _run_expectation_maximisation(
            candidate, observations, max_iterations, tolerance, pooled_covariance
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
        "fitted states=%d log_likelihood=%.3f restarts=%d converged=%s",
        state_count,
        best_log_likelihood,
        restarts,
        best_converged,
    )
    return GaussianHiddenMarkovModel(
        initial_distribution=best_model.initial_distribution,
        transition_matrix=best_model.transition_matrix,
        means=best_model.means,
        covariances=best_model.covariances,
        covariance_type=covariance_type,
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


def _initial_model(
    observations: np.ndarray,
    state_count: int,
    generator: np.random.Generator,
    pooled_covariance: np.ndarray,
    covariance_type: str,
    means_override: np.ndarray | None = None,
) -> GaussianHiddenMarkovModel:
    """One starting point: spread means, a random persistence level, pooled spread.

    ``means_override``, when given, replaces the furthest-point spread outright
    (the quadrant-structured prior). It is the same array on every restart, so
    the restart diversity below comes entirely from the transition matrix.
    """
    means = (
        means_override.copy()
        if means_override is not None
        else _seed_means_by_furthest_point(observations, state_count, generator)
    )

    persistence = float(generator.uniform(0.50, 0.98))
    transition_matrix = np.full(
        (state_count, state_count),
        (1.0 - persistence) / max(state_count - 1, 1),
        dtype="float64",
    )
    np.fill_diagonal(transition_matrix, persistence)
    if state_count == 1:
        transition_matrix = np.ones((1, 1))
    transition_matrix = transition_matrix * generator.uniform(
        0.9, 1.1, size=transition_matrix.shape
    )
    transition_matrix /= transition_matrix.sum(axis=1, keepdims=True)

    covariances = np.repeat(pooled_covariance[None, :, :], state_count, axis=0)
    if covariance_type == "diagonal":
        covariances = np.stack([np.diag(np.diag(matrix)) for matrix in covariances])

    return GaussianHiddenMarkovModel(
        initial_distribution=np.full(state_count, 1.0 / state_count),
        transition_matrix=transition_matrix,
        means=means,
        covariances=covariances,
        covariance_type=covariance_type,
    )


def _seed_means_by_furthest_point(
    observations: np.ndarray, state_count: int, generator: np.random.Generator
) -> np.ndarray:
    """k-means++ seeding: pick a first centre at random, then favour distant points.

    Picking K observations uniformly at random regularly draws two from the same
    dense cluster, which starts two states on top of each other and wastes the
    restart.
    """
    months = observations.shape[0]
    chosen = [int(generator.integers(months))]
    for _ in range(1, state_count):
        squared_distances = np.min(
            ((observations[:, None, :] - observations[chosen][None, :, :]) ** 2).sum(axis=2),
            axis=1,
        )
        total = squared_distances.sum()
        if total <= 0:
            chosen.append(int(generator.integers(months)))
            continue
        chosen.append(int(generator.choice(months, p=squared_distances / total)))
    return observations[chosen].copy()


def _seed_means_by_quadrant_centroids(observations: np.ndarray, state_count: int) -> np.ndarray:
    """All Weather's growth-by-inflation 2x2, imposed as a structural prior on
    the four starting means (research arm A2-quadrant-structure-levels).

    Column 0 is growth and column 1 is inflation (``observation_matrix``'s fixed
    ``DIMENSION_ORDER``). Each month is assigned to one of four quadrants by the
    sign of its growth and inflation relative to their own **expanding**
    medians -- computed point in time, month by month, using only that month and
    the ones before it in this panel, never a single median of the whole panel.
    A month sits in the "high" half of a dimension when it is at or above the
    median seen so far; otherwise it is "low". A centroid is the mean, over every
    month assigned to its quadrant, of all three columns -- rates enter each
    centroid as that quadrant's mean and play no part in the assignment itself.

    No threshold is written down anywhere: the boundary is each dimension's own
    expanding median, not a chosen number (docs/TECHNICAL_DEBT.md D12).
    """
    if state_count != 4:
        raise HiddenMarkovModelError(
            f"quadrant-structured seeding defines exactly four centroids, one per quadrant of "
            f"growth by inflation, not {state_count}. Fit with state_count=4, or seed by the "
            "furthest-point rule instead."
        )
    if observations.shape[1] < 2:
        raise HiddenMarkovModelError(
            "quadrant-structured seeding needs at least a growth and an inflation column; the "
            f"observation matrix has {observations.shape[1]}"
        )

    growth = observations[:, 0]
    inflation = observations[:, 1]
    expanding_median_growth = pd.Series(growth).expanding(min_periods=1).median().to_numpy()
    expanding_median_inflation = pd.Series(inflation).expanding(min_periods=1).median().to_numpy()
    growth_high = growth >= expanding_median_growth
    inflation_high = inflation >= expanding_median_inflation

    quadrant_masks = (
        growth_high & inflation_high,  # rising growth, rising inflation
        growth_high & ~inflation_high,  # rising growth, falling inflation
        ~growth_high & inflation_high,  # falling growth, rising inflation
        ~growth_high & ~inflation_high,  # falling growth, falling inflation
    )
    empty = [index for index, mask in enumerate(quadrant_masks) if not mask.any()]
    if empty:
        raise HiddenMarkovModelError(
            f"{len(empty)} of 4 growth/inflation quadrants have no month in this "
            f"{observations.shape[0]}-month panel, so there is no centroid to seed a mean from. "
            "That is a property of this panel, reported rather than patched with a fallback "
            "centroid."
        )
    return np.stack([observations[mask].mean(axis=0) for mask in quadrant_masks])


def _run_expectation_maximisation(
    model: GaussianHiddenMarkovModel,
    observations: np.ndarray,
    max_iterations: int,
    tolerance: float,
    pooled_covariance: np.ndarray,
) -> tuple[GaussianHiddenMarkovModel, float, int, bool]:
    """Iterate expectation and maximisation until the likelihood stops moving."""
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

        # The allowance ADR 0007 decided on: the covariance ridge makes the update
        # not quite the maximiser, so a fall it can explain is not a bug. Until
        # 2026-09-15 this line kept a hard millionth and never called it.
        if log_likelihood < previous_log_likelihood - _monotonicity_allowance(
            previous_log_likelihood
        ):
            raise HiddenMarkovModelError(
                "the log likelihood fell from "
                f"{previous_log_likelihood:.6f} to {log_likelihood:.6f}. Expectation "
                "maximisation cannot do that, so this is a bug in the update equations, not a "
                "property of the data."
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
            pooled_covariance,
        )

    # On the iteration-cap path the loop runs one more maximisation step after the
    # last likelihood evaluation, so the model returned is one step ahead of the
    # number. Re-evaluating costs one forward pass and keeps the report honest --
    # this is the number the manifest publishes and the one restarts are ranked on.
    if not converged:
        log_likelihood = model.log_likelihood(observations)
    return model, log_likelihood, iteration, converged


def _monotonicity_allowance(previous_log_likelihood: float) -> float:
    """How far the likelihood may fall before the fall is a real problem.

    The covariance ridge perturbs each covariance by a fraction ``COVARIANCE_RIDGE``
    of the pooled variance, so the log likelihood can move by roughly that fraction
    per observation. The allowance is scaled to the likelihood's own magnitude with
    generous headroom, because the cost of being slightly too tolerant is a
    marginally worse fit and the cost of being too strict is throwing away a good
    restart.
    """
    return max(1.0, abs(previous_log_likelihood)) * COVARIANCE_RIDGE * 1000.0


def _maximisation_step(
    model: GaussianHiddenMarkovModel,
    observations: np.ndarray,
    log_emissions: np.ndarray,
    log_alpha: np.ndarray,
    log_beta: np.ndarray,
    log_likelihood: float,
    pooled_covariance: np.ndarray,
) -> GaussianHiddenMarkovModel:
    """Re-estimate every parameter from the posterior state responsibilities."""
    months, states = log_emissions.shape

    log_gamma = log_alpha + log_beta - log_likelihood
    responsibilities = np.exp(log_gamma)

    log_transition = _safe_log(model.transition_matrix)
    log_transition_counts = (
        log_alpha[:-1, :, None]
        + log_transition[None, :, :]
        + (log_emissions[1:] + log_beta[1:])[:, None, :]
        - log_likelihood
    )
    transition_counts = np.exp(logsumexp(log_transition_counts, axis=0))

    state_totals = np.maximum(responsibilities.sum(axis=0), MINIMUM_STATE_RESPONSIBILITY)

    initial_distribution = responsibilities[0] / responsibilities[0].sum()

    # A state the data have abandoned leaves a row of zeros, which is not a
    # probability distribution and would fail the constructor's check, ending the
    # whole fit. The documented behaviour is that a collapsed state survives with a
    # near-zero population so that model selection can see it and prefer fewer
    # states, so an abandoned row falls back to uniform.
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
            "state_abandoned states=%s; their transition rows fall back to uniform",
            np.flatnonzero(abandoned).tolist(),
        )

    means = (responsibilities.T @ observations) / state_totals[:, None]

    covariances = np.empty((states, observations.shape[1], observations.shape[1]))
    for state in range(states):
        deviations = observations - means[state]
        weighted = deviations * responsibilities[:, state][:, None]
        covariance = (weighted.T @ deviations) / state_totals[state]
        if model.covariance_type == "diagonal":
            covariance = np.diag(np.diag(covariance))
        covariances[state] = _regularised_covariance(covariance, pooled_covariance)

    return GaussianHiddenMarkovModel(
        initial_distribution=initial_distribution,
        transition_matrix=transition_matrix,
        means=means,
        covariances=covariances,
        covariance_type=model.covariance_type,
    )


def _regularised_covariance(
    covariance: np.ndarray, pooled_covariance: np.ndarray | None = None
) -> np.ndarray:
    """Add a ridge so every covariance stays invertible.

    The ridge is scaled to the pooled variance rather than being an absolute
    number, so it means the same thing whatever units the observations are in.
    """
    dimensions = covariance.shape[0]
    reference = pooled_covariance if pooled_covariance is not None else covariance
    scale = max(float(np.trace(reference)) / dimensions, 1e-12)
    ridged: np.ndarray = covariance + COVARIANCE_RIDGE * scale * np.eye(dimensions)
    return ridged
