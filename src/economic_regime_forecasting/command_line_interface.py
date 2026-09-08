"""The operator's surface: one command per stage, and one that runs them all.

    forecast fetch-data      populate the cache from the Federal Reserve
    forecast audit-data      gate 1: what was fetched, against what was declared
    forecast fit-regimes     gate 2: sweep the number of regimes and fit
    forecast forecast-now    gate 3: the current ten by three probability grid
    forecast backtest        gate 4: walk the method through history
    forecast evaluate        gate 5: apply the pre-registered decision rule
    forecast submit          write the submission and its manifest
    forecast check-gates     all five gates in order, stopping at the first failure

Each stage reads what the previous one wrote and writes what the next one needs,
under ``.cache/``. Nothing here contains analysis; every command is a few lines of
orchestration over the package.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from economic_regime_forecasting import __version__, pipeline_gates
from economic_regime_forecasting.backtest import schedule as schedule_module
from economic_regime_forecasting.backtest import walk_forward
from economic_regime_forecasting.configuration.registry import (
    BinaryIndicator,
    EconomicSeriesRegistry,
    load_registries,
)
from economic_regime_forecasting.configuration.run_settings import (
    ARTIFACTS,
    DEFAULT_RUN_SETTINGS,
    PROJECT_ROOT,
    RunSettings,
)
from economic_regime_forecasting.data import audit as audit_module
from economic_regime_forecasting.data import federal_reserve_client
from economic_regime_forecasting.data.cache import ArtifactStore, SeriesCache
from economic_regime_forecasting.data.panel import assemble_point_in_time_panel
from economic_regime_forecasting.evaluation import verdict as verdict_module
from economic_regime_forecasting.features.observation_matrix import build_observation_matrix
from economic_regime_forecasting.models import indicator_forecast, regime_forecast
from economic_regime_forecasting.models.gaussian_hidden_markov_model import (
    GaussianHiddenMarkovModel,
)
from economic_regime_forecasting.models.state_labelling import describe_regimes, regime_table
from economic_regime_forecasting.models.state_selection import sweep_state_counts

logger = logging.getLogger("economic_regime_forecasting")

SUBMISSION_DIRECTORY = PROJECT_ROOT / "submission"


@dataclass(frozen=True)
class Workspace:
    """Everything a command needs, assembled once."""

    registry: EconomicSeriesRegistry
    indicators: tuple[BinaryIndicator, ...]
    cache: SeriesCache
    artifacts: ArtifactStore
    settings: RunSettings

    @classmethod
    def open(cls, settings: RunSettings = DEFAULT_RUN_SETTINGS) -> Workspace:
        settings.cache.create_directories()
        registry, indicators = load_registries()
        return cls(
            registry=registry,
            indicators=indicators,
            cache=SeriesCache(settings.cache.raw, settings.cache.vintage),
            artifacts=ArtifactStore(settings.cache.models),
            settings=settings,
        )

    def observation_matrix_as_of(self, as_of: date):  # type: ignore[no-untyped-def]
        return build_observation_matrix(
            assemble_point_in_time_panel(self.registry, as_of, self.cache), self.registry
        )

    def backtest_schedule(self, today: date) -> schedule_module.ForecastSchedule:
        """The forecast dates this run will visit, computed the same way everywhere."""
        latest = self.observation_matrix_as_of(today)
        earliest_candidate = (
            latest.dates[self.settings.minimum_observations_before_first_fit - 1]
            + pd.DateOffset(months=1)
        ).date()
        first = walk_forward.find_first_forecast_date(
            self.registry,
            self.cache,
            self.settings,
            earliest_candidate,
            (pd.Timestamp(today) - pd.DateOffset(years=15)).date(),
        )
        return schedule_module.build_schedule(first, today, self.settings.refit_every_n_months)


# --------------------------------------------------------------------- stages


def fetch_data(workspace: Workspace, today: date, workers: int) -> int:
    """Populate the cache: every series as it stands, and the vintages history needs."""
    for entry in workspace.registry.series:
        workspace.cache.get_or_fetch(
            federal_reserve_client.build_request(entry.series_id),
            federal_reserve_client.fetcher_for(entry.units),
        )
    print(f"fetched {len(workspace.registry.series)} series at their current vintage")

    schedule = workspace.backtest_schedule(today)
    revised_inputs = [item for item in workspace.registry.model_inputs if item.is_revised]
    wanted = [
        (entry, stamp.date())
        for entry in revised_inputs
        for stamp in schedule.forecast_dates
        if not workspace.cache.contains(
            federal_reserve_client.build_request(entry.series_id, stamp.date())
        )
    ]
    print(
        f"{schedule.describe()}; {len(wanted)} archival vintages still to fetch "
        f"for {len(revised_inputs)} revisable series"
    )

    if wanted:

        def fetch_one(job: tuple[object, date]) -> str | None:
            entry, as_of = job
            request = federal_reserve_client.build_request(entry.series_id, as_of)  # type: ignore[attr-defined]
            try:
                snapshot = federal_reserve_client.fetch(request, units=entry.units)  # type: ignore[attr-defined]
            except federal_reserve_client.FederalReserveError as error:
                return f"{entry.series_id} {as_of}: {error}"  # type: ignore[attr-defined]
            workspace.cache.write(snapshot)
            return None

        failures: list[str] = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for done, failure in enumerate(pool.map(fetch_one, wanted), start=1):
                if failure:
                    failures.append(failure)
                if done % 200 == 0:
                    print(f"  {done}/{len(wanted)} vintages, {len(failures)} could not be fetched")
        if failures:
            # A vintage that will not download is not fatal: that date falls back
            # to the publication-lag view, which is recorded per series in the run
            # manifest. It is reported here so the count is never a surprise.
            print(f"{len(failures)} vintages could not be fetched; first few:")
            for line in failures[:5]:
                print(f"  {line}")
            print("Re-run fetch-data to retry them; anything already cached is skipped.")
    still_missing = _missing_vintages(workspace, schedule)
    print(f"cache holds {len(workspace.cache.entries())} entries")
    if still_missing:
        print(
            f"{len(still_missing)} vintages the backtest needs are still absent. Re-run this "
            "command; the service blocks an address that asks too fast, and the block clears."
        )
        return 1
    print("every vintage the backtest needs is cached")
    return 0


def audit_data(workspace: Workspace, today: date) -> tuple[int, pipeline_gates.GateReport]:
    """Gate 1. Measure what was fetched against what the registry declared."""
    audits = audit_module.audit_series(workspace.registry, workspace.cache)
    table = audit_module.audit_table(audits)
    workspace.artifacts.write_table(ARTIFACTS.data_audit, table)

    probe_dates = [date(year, 1, 1) for year in (1975, 1990, 2005, 2020)]
    revisions = audit_module.audit_revisions(workspace.registry, workspace.cache, probe_dates)
    workspace.artifacts.write_table(
        ARTIFACTS.revision_audit, audit_module.revision_table(revisions)
    )

    reload_cache = SeriesCache(workspace.settings.cache.raw, workspace.settings.cache.vintage)
    audit_module.audit_series(workspace.registry, reload_cache)
    report = pipeline_gates.gate_one_data(workspace.registry, audits, reload_cache.statistics)

    print(table.to_string(index=False))
    print()
    print(report.describe())
    return (0 if report.passed else 1), report


def fit_regimes(workspace: Workspace, today: date) -> tuple[int, pipeline_gates.GateReport]:
    """Gate 2. Sweep the number of regimes, fit the winner, describe it."""
    matrix = workspace.observation_matrix_as_of(today)
    settings = workspace.settings
    sweep = sweep_state_counts(
        matrix.values,
        settings.hidden_state_counts_to_search,
        seed=settings.random_seed,
        restarts=settings.expectation_maximisation_restarts,
        max_iterations=settings.expectation_maximisation_max_iterations,
        tolerance=settings.expectation_maximisation_tolerance,
    )
    model = sweep.recommended_model
    descriptions = describe_regimes(model, matrix.values, matrix.transformed.to_numpy())

    workspace.artifacts.write_table(ARTIFACTS.state_count_sweep, sweep.table())
    workspace.artifacts.write_json(ARTIFACTS.selected_model, model.to_dictionary())
    workspace.artifacts.write_table(ARTIFACTS.regime_descriptions, regime_table(descriptions))

    report = pipeline_gates.gate_two_regime_model(
        sweep, model.most_likely_state_path(matrix.values), len(matrix)
    )
    print(sweep.table().to_string(index=False))
    print(f"\n{sweep.reason}\n")
    print(regime_table(descriptions).to_string(index=False))
    print()
    print(report.describe())
    return (0 if report.passed else 1), report


def forecast_now(workspace: Workspace, today: date) -> tuple[int, pipeline_gates.GateReport]:
    """Gate 3. The current probability grid, with its evidence attached."""
    settings = workspace.settings
    matrix = workspace.observation_matrix_as_of(today)
    selected = GaussianHiddenMarkovModel.from_dictionary(
        workspace.artifacts.read_json(ARTIFACTS.selected_model)
    )
    histories = walk_forward.prepare_indicator_history(
        workspace.indicators,
        workspace.registry,
        workspace.cache,
        settings.forecast_horizons_in_months,
    )
    # The sweep chose how many regimes; the model that issues today's forecast is
    # the one the walk-forward would fit at today's date, so the submission comes
    # out of the same code path that was backtested. Every quantity below reads
    # from that single model: mixing a state distribution from one fit with a
    # transition matrix from another would be quietly incoherent.
    fitted = walk_forward.fit_regime_model(
        today,
        workspace.registry,
        workspace.cache,
        histories,
        settings,
        selected.state_count,
        workspace.artifacts,
    )
    filtered = fitted.model.filtered_state_probabilities(matrix.values)

    rows = []
    for indicator in workspace.indicators:
        condition = walk_forward.condition_available_at(histories[indicator.name], today)
        holds_now = bool(condition.iloc[-1] > 0.5) if not condition.empty else False
        for horizon in settings.forecast_horizons_in_months:
            composed = indicator_forecast.forecast_indicator(
                indicator,
                fitted.model,
                filtered[-1],
                fitted.rates_by_indicator[indicator.name],
                horizon,
                holds_now,
            )
            rows.append({**composed.as_row(), "question": indicator.question})

    forecasts = pd.DataFrame(rows)
    mixing = regime_forecast.measure_mixing(
        fitted.model,
        filtered,
        settings.forecast_horizons_in_months,
        settings.information_horizon_total_variation_threshold,
    )
    workspace.artifacts.write_table(ARTIFACTS.current_forecasts, forecasts)
    workspace.artifacts.write_table(ARTIFACTS.mixing_diagnostics, mixing.table())

    report = pipeline_gates.gate_three_forecasts(
        forecasts, list(workspace.indicators), settings.forecast_horizons_in_months, mixing
    )
    print(
        forecasts.pivot(index="indicator", columns="horizon_months", values="probability")
        .round(3)
        .to_string()
    )
    print(f"\n{mixing.describe()}\n")
    print(report.describe())
    return (0 if report.passed else 1), report


def _missing_vintages(
    workspace: Workspace, schedule: schedule_module.ForecastSchedule
) -> list[tuple[str, date]]:
    """Which archival vintages the walk-forward will ask for and the cache lacks."""
    return [
        (entry.series_id, stamp.date())
        for entry in workspace.registry.model_inputs
        if entry.is_revised
        for stamp in schedule.forecast_dates
        if not workspace.cache.contains(
            federal_reserve_client.build_request(entry.series_id, stamp.date())
        )
    ]


def run_backtest(workspace: Workspace, today: date) -> tuple[int, pipeline_gates.GateReport]:
    """Gate 4. Walk the whole method through history."""
    settings = workspace.settings
    model = GaussianHiddenMarkovModel.from_dictionary(
        workspace.artifacts.read_json(ARTIFACTS.selected_model)
    )
    schedule = workspace.backtest_schedule(today)
    print(f"{schedule.describe()}, {model.state_count} regimes")

    # Check up front rather than discovering a gap forty minutes into a run. A
    # missing vintage is not fatal to the method -- the publication-lag fallback
    # covers it -- but it is fatal to an unattended run, because filling it needs
    # the network.
    missing = _missing_vintages(workspace, schedule)
    if missing:
        raise SystemExit(
            f"{len(missing)} archival vintages the run needs are not cached, first few "
            f"{missing[:3]}. Run `forecast fetch-data` first; it skips anything already there."
        )

    results = walk_forward.run_walk_forward(
        workspace.registry,
        workspace.indicators,
        workspace.cache,
        settings,
        model.state_count,
        schedule.forecast_dates,
        schedule.refit_dates,
        workspace.artifacts,
    )
    workspace.artifacts.write_table(ARTIFACTS.backtest_results, results)
    report = pipeline_gates.gate_four_backtest(results)
    print(report.describe())
    return (0 if report.passed else 1), report


def evaluate(workspace: Workspace, today: date) -> tuple[int, pipeline_gates.GateReport]:
    """Gate 5. Apply the pre-registered decision rule, per horizon."""
    settings = workspace.settings
    results = workspace.artifacts.read_table(ARTIFACTS.backtest_results)
    sweep_table = workspace.artifacts.read_table(ARTIFACTS.state_count_sweep)

    single = sweep_table[sweep_table["states"] == 1]
    multiple = sweep_table[sweep_table["states"] > 1]
    regimes_exist = bool(
        not single.empty
        and multiple["held_out_log_likelihood_per_month"].max()
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

    metrics = verdict_module.compute_metrics(results)
    metrics_table = verdict_module.metrics_table(metrics)
    verdicts = verdict_module.evaluate_all_horizons(
        results,
        settings.forecast_horizons_in_months,
        regimes_exist,
        evidence,
        seed=settings.random_seed,
    )
    table = verdict_module.verdict_table(verdicts)

    workspace.artifacts.write_table(ARTIFACTS.evaluation_metrics, metrics_table)
    workspace.artifacts.write_table(ARTIFACTS.verdicts, table)

    print(metrics_table.round(4).to_string(index=False))
    print()
    for item in verdicts:
        print(item.describe())
        for gate in item.gates:
            print(f"    {'ok  ' if gate.passed else 'FAIL'}  {gate.name}: {gate.evidence}")
        print()

    report = pipeline_gates.gate_five_evaluation(table, settings.forecast_horizons_in_months)
    print(report.describe())
    return (0 if report.passed else 1), report


def submit(workspace: Workspace, today: date) -> int:
    """Write the final grid, shipping the base rate where a gate failed."""
    settings = workspace.settings
    forecasts = workspace.artifacts.read_table(ARTIFACTS.current_forecasts)
    verdicts = workspace.artifacts.read_table(ARTIFACTS.verdicts)
    results = workspace.artifacts.read_table(ARTIFACTS.backtest_results)
    model = GaussianHiddenMarkovModel.from_dictionary(
        workspace.artifacts.read_json(ARTIFACTS.selected_model)
    )

    ships_model = dict(zip(verdicts["horizon_months"], verdicts["verdict"], strict=True))
    latest_climatology = (
        results.sort_values("forecast_date")
        .groupby(["indicator", "horizon_months"])["climatology_probability"]
        .apply(lambda column: column.dropna().iloc[-1] if column.notna().any() else np.nan)
    )

    rows = []
    for record in forecasts.to_dict("records"):
        horizon = int(record["horizon_months"])
        verdict = str(ships_model.get(horizon, verdict_module.SHIP_BASE_RATE))
        base_rate = float(latest_climatology.get((record["indicator"], horizon), np.nan))
        model_probability = float(record["probability"])
        shipped = model_probability if verdict == verdict_module.SHIP_MODEL else base_rate
        rows.append(
            {
                "indicator": record["indicator"],
                "question": record["question"],
                "horizon_years": horizon // 12,
                "probability": round(shipped, 4),
                "source": "regime model" if verdict == verdict_module.SHIP_MODEL else "base rate",
                "model_probability": round(model_probability, 4),
                "climatological_base_rate": round(base_rate, 4),
                "composition": record["composition"],
                "effective_sample_size": round(float(record["effective_sample_size"]), 1),
                "distance_to_stationary": round(float(record["distance_to_stationary"]), 4),
            }
        )

    submission = pd.DataFrame(rows).sort_values(["indicator", "horizon_years"])
    SUBMISSION_DIRECTORY.mkdir(parents=True, exist_ok=True)
    submission.to_csv(SUBMISSION_DIRECTORY / "forecasts.csv", index=False)

    manifest = {
        "generated_on": today.isoformat(),
        "package_version": __version__,
        "configuration_hash": settings.configuration_hash(),
        "random_seed": settings.random_seed,
        "regimes": model.state_count,
        "second_largest_eigenvalue_modulus": model.second_largest_eigenvalue_modulus(),
        "data_as_of": str(workspace.observation_matrix_as_of(today).dates[-1].date()),
        "verdict_by_horizon": {
            f"{int(record['horizon_months']) // 12}_year": record["verdict"]
            for record in verdicts.to_dict("records")
        },
        "vintage_policy_counts": assemble_point_in_time_panel(
            workspace.registry, today, workspace.cache
        ).policy_counts(),
        "indicator_count": len(workspace.indicators),
        "pre_registration": str(verdict_module.PRE_REGISTRATION_FILE.relative_to(PROJECT_ROOT)),
    }
    (SUBMISSION_DIRECTORY / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(
        submission[["indicator", "horizon_years", "probability", "source"]].to_string(index=False)
    )
    print(f"\nwritten to {SUBMISSION_DIRECTORY.relative_to(PROJECT_ROOT)}/")
    return 0


def check_gates(workspace: Workspace, today: date) -> int:
    """Run every stage gate in order, stopping at the first failure."""
    reports: list[pipeline_gates.GateReport] = []
    for stage in (audit_data, fit_regimes, forecast_now, run_backtest, evaluate):
        print(f"\n{'=' * 78}\n{stage.__name__}\n{'=' * 78}")
        code, report = stage(workspace, today)
        reports.append(report)
        if code != 0:
            print(f"\nStopped at gate {report.number}. Fix it rather than working around it.")
            _write_gate_reports(workspace, reports)
            return code
    _write_gate_reports(workspace, reports)
    print(f"\n{'=' * 78}\nAll five gates passed.")
    return 0


def _write_gate_reports(workspace: Workspace, reports: list[pipeline_gates.GateReport]) -> None:
    if reports:
        workspace.artifacts.write_table(
            ARTIFACTS.gate_reports, pd.concat([item.table() for item in reports])
        )


# ------------------------------------------------------------------ entry point


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forecast",
        description="Forecast binary macroeconomic indicators from latent economic regimes.",
    )
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        help="pretend today is this date (default: today)",
    )
    parser.add_argument("--verbose", action="store_true", help="log what each step is doing")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch = subparsers.add_parser("fetch-data", help="populate the cache")
    fetch.add_argument(
        "--workers",
        type=int,
        default=2,
        help=(
            "parallel downloads for archival vintages (default: 2). The client also spaces "
            "its own requests out, so raising this will not make the fetch faster and may "
            "earn a temporary block from the service."
        ),
    )
    for name, help_text in (
        ("audit-data", "gate 1: measure the data against the registry"),
        ("fit-regimes", "gate 2: sweep the number of regimes and fit"),
        ("forecast-now", "gate 3: the current probability grid"),
        ("backtest", "gate 4: walk the method through history"),
        ("evaluate", "gate 5: apply the pre-registered decision rule"),
        ("submit", "write the submission and its manifest"),
        ("check-gates", "run all five gates in order"),
    ):
        subparsers.add_parser(name, help=help_text)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if arguments.verbose else logging.WARNING,
        format="%(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    today = arguments.as_of or date.today()
    workspace = Workspace.open()

    if arguments.command == "fetch-data":
        return fetch_data(workspace, today, arguments.workers)
    if arguments.command == "submit":
        return submit(workspace, today)
    if arguments.command == "check-gates":
        return check_gates(workspace, today)

    stages = {
        "audit-data": audit_data,
        "fit-regimes": fit_regimes,
        "forecast-now": forecast_now,
        "backtest": run_backtest,
        "evaluate": evaluate,
    }
    code, _ = stages[arguments.command](workspace, today)
    return code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
