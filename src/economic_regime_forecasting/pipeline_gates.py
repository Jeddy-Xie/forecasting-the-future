"""The five stage gates, written as checks a machine runs rather than notes a
person reads.

The brief this project was built from ends each phase with a gate and says to
stop rather than work around a failure. A gate that lives only in prose is
advisory, and advisory rules get followed about half the time. These are
executable: ``forecast check-gates`` runs them in order and exits non-zero at the
first failure, so the pipeline cannot advance past a stage that did not produce
what the next stage needs.

They are separate from the five *acceptance* gates in ``evaluation.verdict``,
which decide whether the finished model is worth shipping. These decide whether
each stage did its job at all.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from economic_regime_forecasting.backtest.walk_forward import RESULT_COLUMNS
from economic_regime_forecasting.configuration.registry import (
    BinaryIndicator,
    EconomicSeriesRegistry,
)
from economic_regime_forecasting.data.audit import SeriesAudit
from economic_regime_forecasting.data.cache import CacheStatistics
from economic_regime_forecasting.models.gaussian_hidden_markov_model import (
    GaussianHiddenMarkovModel,
)
from economic_regime_forecasting.models.regime_forecast import MixingDiagnostics
from economic_regime_forecasting.models.state_selection import (
    StateCountEvaluation,
    StateCountSweep,
)
from economic_regime_forecasting.models.two_timescale_state_selection import (
    TwoChainStateCountSweep,
)

MAXIMUM_REGIME_SWITCHES_PER_YEAR = 2.0
"""How often the most likely regime may change before the fit is calling noise a
regime. Two switches a year is already fast for an economic regime; the fitted
model runs at a small fraction of it."""


@dataclass(frozen=True)
class Check:
    """One thing that must be true, and the evidence either way."""

    requirement: str
    passed: bool
    evidence: str


@dataclass(frozen=True)
class GateReport:
    """One stage gate: its checks and whether the stage may be left."""

    number: int
    name: str
    checks: tuple[Check, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def describe(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines = [f"Gate {self.number} — {self.name}: {status}"]
        for check in self.checks:
            marker = "  ok  " if check.passed else "  FAIL"
            lines.append(f"{marker}  {check.requirement}")
            lines.append(f"        {check.evidence}")
        return "\n".join(lines)

    def table(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "gate": self.number,
                    "requirement": item.requirement,
                    "passed": item.passed,
                    "evidence": item.evidence,
                }
                for item in self.checks
            ]
        )


def gate_one_data(
    registry: EconomicSeriesRegistry,
    audits: list[SeriesAudit],
    reload_statistics: CacheStatistics,
) -> GateReport:
    """Every registry entry fetches, caches, and reloads identically from cache."""
    audited_names = {item.name for item in audits}
    expected_names = {item.name for item in registry.series}
    mismatched = [item.name for item in audits if not item.start_matches_registry]

    return GateReport(
        number=1,
        name="data",
        checks=(
            Check(
                requirement="every series in the registry was fetched and audited",
                passed=audited_names == expected_names,
                evidence=(
                    f"{len(audited_names)} of {len(expected_names)} audited"
                    + (
                        f"; missing {sorted(expected_names - audited_names)}"
                        if expected_names - audited_names
                        else ""
                    )
                ),
            ),
            Check(
                requirement="each series starts where the registry says it does",
                passed=not mismatched,
                evidence=(
                    "every declared start date matches the service"
                    if not mismatched
                    else f"disagreements: {mismatched}"
                ),
            ),
            Check(
                requirement="a second pass over the same series is served entirely from cache",
                passed=reload_statistics.lookups > 0 and reload_statistics.hit_rate == 1.0,
                evidence=reload_statistics.summary(),
            ),
            Check(
                requirement="every series has at least twenty years of monthly history",
                passed=all(item.observation_count >= 240 for item in audits),
                evidence=(
                    "shortest is "
                    + min(
                        (
                            f"{item.name} with {item.observation_count} observations"
                            for item in audits
                        ),
                        key=lambda text: int(text.split()[-2]),
                    )
                    if audits
                    else "no series audited"
                ),
            ),
        ),
    )


def gate_two_regime_model(
    sweep: StateCountSweep, most_likely_state_path: np.ndarray, months: int
) -> GateReport:
    """The fitted regimes are persistent, populated, and recognisably economic."""
    chosen = sweep.evaluation_for(sweep.recommended_state_count)
    switches = int(np.sum(np.diff(most_likely_state_path) != 0))
    switches_per_year = switches / max(months / 12.0, 1.0)

    return GateReport(
        number=2,
        name="regime model",
        checks=(
            Check(
                requirement="more than one regime beats a single regime out of sample",
                passed=sweep.more_than_one_state_is_preferred_on_the_holdout,
                evidence=(
                    "held-out log likelihood per month: "
                    + ", ".join(
                        f"{item.state_count} states {item.held_out_log_likelihood_per_month:+.4f}"
                        for item in sweep.evaluations
                    )
                ),
            ),
            Check(
                requirement="the information criterion agrees that regimes exist",
                passed=sweep.more_than_one_state_is_preferred_on_the_criterion,
                evidence=(
                    "criterion: "
                    + ", ".join(
                        f"{item.state_count} states {item.bayesian_information_criterion:,.0f}"
                        for item in sweep.evaluations
                    )
                ),
            ),
            Check(
                requirement="no regime lasts less than three months on average",
                passed=chosen.is_persistent_enough,
                evidence=(
                    f"shortest expected visit is "
                    f"{chosen.shortest_expected_duration_in_months:.1f} months"
                ),
            ),
            Check(
                requirement="no regime holds less than five percent of months",
                passed=chosen.is_populated_enough,
                evidence=f"smallest regime holds {chosen.smallest_population_share:.1%} of months",
            ),
            Check(
                requirement="the regime path does not flicker month to month",
                passed=switches_per_year <= MAXIMUM_REGIME_SWITCHES_PER_YEAR,
                evidence=(
                    f"{switches} switches over {months} months, "
                    f"{switches_per_year:.2f} a year against a ceiling of "
                    f"{MAXIMUM_REGIME_SWITCHES_PER_YEAR:.1f}"
                ),
            ),
        ),
    )


def gate_two_regime_model_of_two_chains(
    sweep: TwoChainStateCountSweep, most_likely_state_path: np.ndarray, months: int
) -> GateReport:
    """Gate 2 for research arm A4's two chains: the same five requirements.

    Each is asked of the object it is about, and this was decided before any run:
    whether regimes exist, of the joint table (the pair 1 x 1 against every other
    pair, the sums being exact); persistence and population, of each chain's
    chosen count, since those are what the selection rule admitted; flicker, of the
    joint regime path, which is the path the forecasts condition on and which
    switches whenever either chain does, so it is the stricter reading.
    """
    joint = sweep.joint_table()
    single = joint[joint["states"] == 1]
    multiple = joint[joint["states"] > 1]
    both_sides = not single.empty and not multiple.empty
    holdout = "held_out_log_likelihood_per_month"
    criterion = "bayesian_information_criterion"
    beats_on_holdout = both_sides and bool(multiple[holdout].max() > single[holdout].iloc[0])
    beats_on_criterion = both_sides and bool(multiple[criterion].min() < single[criterion].iloc[0])

    def by_pair(column: str, shown: str) -> str:
        return ", ".join(
            f"{int(row['growth_chain_states'])}x{int(row['levels_chain_states'])} "
            f"{format(float(row[column]), shown)}"
            for row in joint.to_dict("records")
        )

    growth = sweep.growth_chain_evaluation
    levels = sweep.levels_chain_evaluation
    shortest_joint_visit = float(sweep.recommended_model.expected_state_durations().min())
    switches = int(np.sum(np.diff(most_likely_state_path) != 0))
    switches_per_year = switches / max(months / 12.0, 1.0)

    return GateReport(
        number=2,
        name="regime model",
        checks=(
            Check(
                requirement="more than one regime beats a single regime out of sample",
                passed=beats_on_holdout,
                evidence="held-out log likelihood per month, growth x levels states: "
                + by_pair(holdout, "+.4f"),
            ),
            Check(
                requirement="the information criterion agrees that regimes exist",
                passed=beats_on_criterion,
                evidence="criterion, growth x levels states: " + by_pair(criterion, ",.0f"),
            ),
            Check(
                requirement="no regime lasts less than three months on average",
                passed=growth.is_persistent_enough and levels.is_persistent_enough,
                evidence=(
                    f"shortest expected visit {growth.shortest_expected_duration_in_months:.1f} "
                    f"months in the growth chain, {levels.shortest_expected_duration_in_months:.1f}"
                    f" in the inflation-and-rates chain; the shortest joint regime, where both "
                    f"chains stay put, {shortest_joint_visit:.1f} months"
                ),
            ),
            Check(
                requirement="no regime holds less than five percent of months",
                passed=growth.is_populated_enough and levels.is_populated_enough,
                evidence=(
                    f"smallest regime holds {growth.smallest_population_share:.1%} of months in "
                    f"the growth chain, {levels.smallest_population_share:.1%} in the "
                    "inflation-and-rates chain"
                ),
            ),
            Check(
                requirement="the regime path does not flicker month to month",
                passed=switches_per_year <= MAXIMUM_REGIME_SWITCHES_PER_YEAR,
                evidence=(
                    f"{switches} switches of the joint regime over {months} months, "
                    f"{switches_per_year:.2f} a year against a ceiling of "
                    f"{MAXIMUM_REGIME_SWITCHES_PER_YEAR:.1f}"
                ),
            ),
        ),
    )


def gate_two_from_tables(
    sweep_table: pd.DataFrame,
    model: GaussianHiddenMarkovModel,
    most_likely_state_path: np.ndarray,
    months: int,
    per_chain_table: pd.DataFrame | None = None,
) -> GateReport:
    """Re-assert gate 2 from the artifacts a run wrote, whichever model wrote them.

    A reader who has the artifacts but not the run should be able to ask the gate
    again, and get the gate the run itself was judged by. Rebuilding the sweep
    objects by hand at the call site is how that goes wrong: it hard-codes one
    model's table shape, which is why this lives here and not in a notebook.
    """
    if "growth_chain_states" in sweep_table.columns:
        if per_chain_table is None:
            raise ValueError(
                "this run's sweep table is a two-chain joint table, and gate 2 asks persistence "
                "and population of each chain, which the joint table does not carry. Read "
                "state_count_sweep_by_chain.parquet from the same run and pass it as "
                "per_chain_table."
            )
        chains = {}
        for name in ("growth", "inflation and rates"):
            chain_model = getattr(
                model, "growth_chain" if name == "growth" else "levels_chain", None
            )
            if chain_model is None:
                raise ValueError(
                    f"the sweep table is a two-chain table but the fitted model has no {name} "
                    "chain; the two artifacts come from different runs."
                )
            rows = per_chain_table[per_chain_table["chain"] == name]
            if rows.empty:
                raise ValueError(f"the per-chain sweep table has no rows for the {name} chain")
            chains[name] = StateCountSweep(
                evaluations=_evaluations_from_rows(rows),
                models={chain_model.state_count: chain_model},
                recommended_state_count=chain_model.state_count,
                reason="loaded from the fitted artifact",
                runner_up_state_count=None,
            )
        return gate_two_regime_model_of_two_chains(
            TwoChainStateCountSweep(
                growth_chain_sweep=chains["growth"],
                levels_chain_sweep=chains["inflation and rates"],
            ),
            most_likely_state_path,
            months,
        )

    return gate_two_regime_model(
        StateCountSweep(
            evaluations=_evaluations_from_rows(sweep_table),
            models={int(model.state_count): model},
            recommended_state_count=int(model.state_count),
            reason="loaded from the fitted artifact",
            runner_up_state_count=None,
        ),
        most_likely_state_path,
        months,
    )


def _evaluations_from_rows(table: pd.DataFrame) -> tuple[StateCountEvaluation, ...]:
    """One evaluation per row of a sweep table, in the table's own order."""
    return tuple(
        StateCountEvaluation(
            state_count=int(row["states"]),
            free_parameters=int(row["free_parameters"]),
            training_log_likelihood=float(row["training_log_likelihood"]),
            bayesian_information_criterion=float(row["bayesian_information_criterion"]),
            held_out_log_likelihood_per_month=float(row["held_out_log_likelihood_per_month"]),
            smallest_population_share=float(row["smallest_population_share"]),
            shortest_expected_duration_in_months=float(row["shortest_expected_duration_months"]),
            second_largest_eigenvalue_modulus=float(row["second_eigenvalue_modulus"]),
            converged=True,
        )
        for row in table.to_dict("records")
    )


def gate_three_forecasts(
    forecasts: pd.DataFrame,
    indicators: list[BinaryIndicator],
    horizons_in_months: tuple[int, ...],
    mixing: MixingDiagnostics,
) -> GateReport:
    """Every indicator produces a usable probability at every horizon, with its
    evidence and its distance to the base rate attached."""
    expected_rows = len(indicators) * len(horizons_in_months)
    probabilities = forecasts["probability"].to_numpy(dtype="float64")

    return GateReport(
        number=3,
        name="forecasts",
        checks=(
            Check(
                requirement="every indicator has a forecast at every horizon",
                passed=len(forecasts) == expected_rows,
                evidence=f"{len(forecasts)} forecasts against {expected_rows} expected",
            ),
            Check(
                requirement="every probability lies in the unit interval and is finite",
                passed=bool(
                    np.isfinite(probabilities).all()
                    and probabilities.min() >= 0.0
                    and probabilities.max() <= 1.0
                ),
                evidence=f"range {probabilities.min():.4f} to {probabilities.max():.4f}",
            ),
            Check(
                requirement="every forecast carries an effective sample size",
                passed=bool((forecasts["effective_sample_size"] > 0).all()),
                evidence=(
                    f"smallest effective sample size "
                    f"{forecasts['effective_sample_size'].min():.1f} months"
                ),
            ),
            Check(
                requirement="every forecast carries its distance to the stationary distribution",
                passed=bool(forecasts["distance_to_stationary"].notna().all()),
                evidence=mixing.describe(),
            ),
        ),
    )


def gate_four_backtest(results: pd.DataFrame) -> GateReport:
    """The walk-forward run produced a tidy, complete, reproducible results frame."""
    duplicated = int(
        results.duplicated(subset=["indicator", "forecast_date", "horizon_months"]).sum()
    )
    resolved = int(results["realised_outcome"].notna().sum())
    hashes = results["configuration_hash"].unique()

    return GateReport(
        number=4,
        name="backtest",
        checks=(
            Check(
                requirement="the results frame carries every column the evaluation needs",
                passed=all(column in results.columns for column in RESULT_COLUMNS),
                evidence=f"{len(results.columns)} columns, {len(results):,} rows",
            ),
            Check(
                requirement="each indicator, date and horizon appears exactly once",
                passed=duplicated == 0,
                evidence=f"{duplicated} duplicate rows",
            ),
            Check(
                requirement="a single configuration produced the whole run",
                passed=len(hashes) == 1,
                evidence=f"configuration hash {hashes[0]}"
                if len(hashes) == 1
                else f"{len(hashes)} different configurations appear",
            ),
            Check(
                requirement="enough forecasts have resolved outcomes to score",
                passed=resolved > 0,
                evidence=f"{resolved:,} of {len(results):,} forecasts have resolved",
            ),
        ),
    )


def gate_five_evaluation(
    verdict_table: pd.DataFrame, horizons_in_months: tuple[int, ...]
) -> GateReport:
    """Every horizon reached a verdict, and every verdict names its reasoning."""
    covered = set(verdict_table["horizon_months"])
    return GateReport(
        number=5,
        name="evaluation",
        checks=(
            Check(
                requirement="every horizon reached a verdict",
                passed=covered == set(horizons_in_months),
                evidence=(
                    "verdicts: "
                    + ", ".join(
                        f"{int(record['horizon_months']) // 12} year {record['verdict']}"
                        for record in verdict_table.to_dict("records")
                    )
                ),
            ),
            Check(
                requirement="every verdict is one of the two the rule allows",
                passed=set(verdict_table["verdict"]) <= {"SHIP MODEL", "SHIP BASE RATE"},
                evidence=f"values seen: {sorted(set(verdict_table['verdict']))}",
            ),
            Check(
                requirement="a horizon that ships the base rate names the gate that failed",
                passed=bool(
                    (
                        (verdict_table["verdict"] == "SHIP MODEL")
                        | (verdict_table["failing_gates"] != "none")
                    ).all()
                ),
                evidence="; ".join(
                    f"{int(record['horizon_months']) // 12} year: {record['failing_gates']}"
                    for record in verdict_table.to_dict("records")
                ),
            ),
        ),
    )
