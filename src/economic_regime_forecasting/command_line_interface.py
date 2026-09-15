"""The operator's surface: one command per stage, and one that runs them all.

    forecast fetch-data      populate the cache from the Federal Reserve
    forecast audit-data      gate 1: what was fetched, against what was declared
    forecast fit-regimes     gate 2: sweep the number of regimes and fit
    forecast forecast-now    gate 3: the current ten by three probability grid
    forecast backtest        gate 4: walk the method through history
    forecast evaluate        gate 5: apply the pre-registered decision rule
    forecast submit          write the submission and its manifest
    forecast check-gates     all five gates in order, stopping at the first failure
    forecast compare-variants  the 2x2 of the two look-ahead fixes (one-off, ~40 min)
    forecast register        record the shipped forecasts as dated, resolvable claims
    forecast resolve         score every registered forecast whose date has passed
    forecast baseline ...    capture, compare and list the committed regression baselines
    forecast audit-look-ahead  perturb what was unpublished at a cutoff; no forecast may move

Each stage reads what the previous one wrote and writes what the next one needs,
under ``.cache/``. Nothing here contains analysis; every command is a few lines of
orchestration over the package.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from economic_regime_forecasting import (
    __version__,
    forecast_register,
    look_ahead_audit,
    pipeline_gates,
    regression_baseline,
)
from economic_regime_forecasting.backtest import schedule as schedule_module
from economic_regime_forecasting.backtest import state_count_on_burn_in, walk_forward
from economic_regime_forecasting.configuration import shipping_approval
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
from economic_regime_forecasting.data import federal_reserve_client, indicator_outcomes
from economic_regime_forecasting.data.cache import ArtifactStore, SeriesCache
from economic_regime_forecasting.data.panel import (
    assemble_point_in_time_panel,
    load_final_series,
)
from economic_regime_forecasting.evaluation import verdict as verdict_module
from economic_regime_forecasting.features.observation_matrix import build_observation_matrix
from economic_regime_forecasting.models import indicator_forecast, regime_forecast
from economic_regime_forecasting.models.gaussian_hidden_markov_model import (
    GaussianHiddenMarkovModel,
)
from economic_regime_forecasting.models.state_labelling import describe_regimes, regime_table
from economic_regime_forecasting.models.state_selection import (
    regimes_exist_from_sweep_table,
    sweep_state_counts,
)

logger = logging.getLogger("economic_regime_forecasting")

SUBMISSION_DIRECTORY = PROJECT_ROOT / "submission"


def _display_path(path: Path) -> str:
    """A path relative to the project when it is inside it, absolute otherwise.

    Only ever used for printing. A path that happens to live elsewhere -- a test
    running against a temporary directory, say -- must not be able to end a
    command that has already done its work.
    """
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


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

    def _panel_length_first_forecast_date(self, today: date) -> date:
        """Unchanged: the first month whose point-in-time panel is long enough."""
        latest = self.observation_matrix_as_of(today)
        earliest_candidate = (
            latest.dates[self.settings.minimum_observations_before_first_fit - 1]
            + pd.DateOffset(months=1)
        ).date()
        return walk_forward.find_first_forecast_date(
            self.registry,
            self.cache,
            self.settings,
            earliest_candidate,
            (pd.Timestamp(today) - pd.DateOffset(years=15)).date(),
        )

    def _first_forecast_date(self, today: date) -> date:
        """The panel-length answer, then the start policy on top of it.

        The point-in-time search takes the panel-length answer as its earliest
        candidate and scans forward, so the honest start is the later of the two
        by construction. There is no ``max()`` to get the wrong way round, and no
        way to produce a date the panel-length rule would have rejected.
        """
        start = self._panel_length_first_forecast_date(today)
        if not self.settings.start_walk_forward_when_every_input_is_point_in_time:
            return start
        return walk_forward.find_first_fully_point_in_time_date(
            self.registry,
            self.cache,
            self.settings,
            earliest_candidate=start,
            last_forecast_date=today,
        )

    def backtest_schedule(self, today: date) -> schedule_module.ForecastSchedule:
        """The forecast dates this run will visit, computed the same way everywhere."""
        return schedule_module.build_schedule(
            self._first_forecast_date(today), today, self.settings.refit_every_n_months
        )

    def widest_backtest_schedule(self, today: date) -> schedule_module.ForecastSchedule:
        """Every date any variant could visit: the start policy is ignored on purpose.

        `fetch-data` populates this one, so a single fetch serves the shipped run
        and all four cells of the comparison. Narrowing the fetch to the honest
        start would starve the very scan that computes it, which has to look back
        to 1971 to find the last month that falls back.
        """
        return schedule_module.build_schedule(
            self._panel_length_first_forecast_date(today),
            today,
            self.settings.refit_every_n_months,
        )


# --------------------------------------------------------------------- stages


def fetch_data(workspace: Workspace, today: date, workers: int) -> int:
    """Populate the cache: every series as it stands, and the vintages history needs."""
    for entry in workspace.registry.series:
        workspace.cache.get_or_fetch(
            federal_reserve_client.build_request(entry.series_id),
            federal_reserve_client.fetcher_for(entry.units),
        )
    print(f"fetched {len(workspace.registry.series)} series at their current vintage")

    # The widest schedule, not the run's own: one fetch then serves the shipped
    # configuration and every cell of the look-ahead comparison, and the scan that
    # computes the honest start still has the pre-1994 vintages it must look at.
    schedule = workspace.widest_backtest_schedule(today)
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

    today_stamp = pd.Timestamp(today)
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
            # Research arm A6 (fixed-climatology-blend): the issued probability is
            # the blend, not the model alone; the model's own number is kept
            # under its own key. See RunSettings.climatology_blend_model_weight
            # and walk_forward.climatology_probability_for_blend for why the
            # climatology value here can be carried forward from an earlier date.
            climatology_for_blend, carried_forward = walk_forward.climatology_probability_for_blend(
                histories[indicator.name].climatology_by_horizon[horizon], today_stamp
            )
            blended_probability = walk_forward.blend_model_and_climatology_probability(
                composed.probability, climatology_for_blend, settings.climatology_blend_model_weight
            )
            row = {**composed.as_row(), "question": indicator.question}
            row["model_probability"] = composed.probability
            row["probability"] = blended_probability
            row["climatology_probability_used_in_blend"] = climatology_for_blend
            row["climatology_carried_forward"] = carried_forward
            rows.append(row)

    forecasts = pd.DataFrame(rows)
    mixing = regime_forecast.measure_mixing(
        fitted.model,
        filtered,
        settings.forecast_horizons_in_months,
        settings.information_horizon_total_variation_threshold,
    )
    workspace.artifacts.write_table(ARTIFACTS.current_forecasts, forecasts)
    workspace.artifacts.write_table(ARTIFACTS.mixing_diagnostics, mixing.table())

    carry_forward_record = walk_forward.climatology_carry_forward_record(
        settings.configuration_hash(),
        forecasts["indicator"],
        forecasts["horizon_months"],
        pd.Series([today_stamp] * len(forecasts)),
        forecasts["climatology_carried_forward"],
    )
    workspace.artifacts.write_json(
        ARTIFACTS.climatology_carry_forward_forecast_record, carry_forward_record
    )
    print(
        f"climatology carried forward on {carry_forward_record['carried_forward_row_count']} "
        f"of {carry_forward_record['row_count']} of today's forecasts "
        f"(see {ARTIFACTS.climatology_carry_forward_forecast_record})"
    )

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


def _state_count_for_the_backtest(
    workspace: Workspace, schedule: schedule_module.ForecastSchedule
) -> int:
    """One integer, from whichever of the two sources this configuration declares.

    With ``select_state_count_on_a_burn_in_window`` off this reads the winner of
    the full-sample sweep off `selected_model.json`, exactly as the shipped run
    did — a forecast issued in 1972 then uses a shape chosen with data through
    today. With it on the count is swept once on the panel as it stood at the
    first forecast date, and the choice is written out so the evaluation can read
    the same evidence rather than the full-sample sweep.
    """
    if not workspace.settings.select_state_count_on_a_burn_in_window:
        model = GaussianHiddenMarkovModel.from_dictionary(
            workspace.artifacts.read_json(ARTIFACTS.selected_model)
        )
        return int(model.state_count)

    choice = state_count_on_burn_in.choose_state_count_on_burn_in_window(
        workspace.registry,
        workspace.cache,
        workspace.settings,
        first_forecast_date=schedule.forecast_dates[0].date(),
        artifacts=workspace.artifacts,
    )
    workspace.artifacts.write_json(ARTIFACTS.burn_in_state_count_choice, choice.as_manifest())
    print(choice.describe())
    return choice.state_count


def run_backtest(workspace: Workspace, today: date) -> tuple[int, pipeline_gates.GateReport]:
    """Gate 4. Walk the whole method through history."""
    settings = workspace.settings
    schedule = workspace.backtest_schedule(today)
    state_count = _state_count_for_the_backtest(workspace, schedule)
    print(f"{schedule.describe()}, {state_count} regimes")

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

    # Measured over this run's own schedule by the scan the pre-flight uses, and
    # recorded beside the results, so the run summary never borrows the count from
    # another command's artifact. Under the honest start the pre-flight refuses
    # anything but zero; the record holds what was measured, not that assumption.
    fallback_dates = walk_forward.forecast_dates_using_the_publication_lag_fallback(
        workspace.registry, workspace.cache, schedule.forecast_dates
    )
    print(
        f"{len(fallback_dates)} of {len(schedule.forecast_dates)} forecast dates use the "
        "publication-lag fallback"
    )

    results = walk_forward.run_walk_forward(
        workspace.registry,
        workspace.indicators,
        workspace.cache,
        settings,
        state_count,
        schedule.forecast_dates,
        schedule.refit_dates,
        workspace.artifacts,
    )
    workspace.artifacts.write_table(ARTIFACTS.backtest_results, results)
    workspace.artifacts.write_json(
        ARTIFACTS.backtest_fallback_record,
        regression_baseline.fallback_record(
            settings.configuration_hash(), schedule.forecast_dates, fallback_dates
        ),
    )
    # Research arm A6 (fixed-climatology-blend): a deliberate fallback recorded,
    # not silent. See RunSettings.climatology_blend_model_weight and
    # walk_forward.climatology_probability_for_blend.
    carry_forward_record = walk_forward.climatology_carry_forward_record(
        settings.configuration_hash(),
        results["indicator"],
        results["horizon_months"],
        results["forecast_date"],
        results["climatology_carried_forward"],
    )
    workspace.artifacts.write_json(
        ARTIFACTS.climatology_carry_forward_backtest_record, carry_forward_record
    )
    print(
        f"climatology carried forward on {carry_forward_record['carried_forward_row_count']} "
        f"of {carry_forward_record['row_count']} backtest rows "
        f"(see {ARTIFACTS.climatology_carry_forward_backtest_record})"
    )
    report = pipeline_gates.gate_four_backtest(results)
    print(report.describe())
    return (0 if report.passed else 1), report


def _sweep_the_verdict_should_read(workspace: Workspace) -> pd.DataFrame:
    """The sweep that answers "do regimes exist" for *this* configuration.

    Feeding a full-sample sweep into the verdict of an honest run would put the
    leak back into the one gate meant to certify its absence, so the burn-in run
    reads the burn-in sweep and the shipped run reads the full-sample one. Same
    requirement, same arithmetic, honest evidence.
    """
    if not workspace.settings.select_state_count_on_a_burn_in_window:
        return workspace.artifacts.read_table(ARTIFACTS.state_count_sweep)
    if not workspace.artifacts.has(ARTIFACTS.burn_in_state_count_choice):
        raise SystemExit(
            f"{ARTIFACTS.burn_in_state_count_choice} is not in the cache, so there is no "
            "burn-in sweep for the regimes-exist gate to read. Run `forecast backtest` "
            "first; it writes the choice it made. Reading the full-sample sweep instead "
            "would answer this gate with the very look-ahead the run removed."
        )
    choice = state_count_on_burn_in.BurnInStateCountChoice.from_manifest(
        workspace.artifacts.read_json(ARTIFACTS.burn_in_state_count_choice)
    )
    return choice.sweep_table()


def evaluate(workspace: Workspace, today: date) -> tuple[int, pipeline_gates.GateReport]:
    """Gate 5. Apply the pre-registered decision rule, per horizon."""
    settings = workspace.settings
    results = workspace.artifacts.read_table(ARTIFACTS.backtest_results)
    sweep_table = _sweep_the_verdict_should_read(workspace)

    regimes_exist, evidence = regimes_exist_from_sweep_table(sweep_table)

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


def _hash_that_produced_the_artifacts(results: pd.DataFrame) -> str:
    """The one configuration behind `backtest_results.parquet`, or a refusal.

    A submission assembled from two runs has no single provenance to check, so
    there is nothing honest to compare the approved hash against.
    """
    found = sorted({str(value) for value in results["configuration_hash"]})
    if len(found) != 1:
        raise shipping_approval.SubmissionNotApprovedError(
            f"backtest_results.parquet carries {len(found)} configuration hashes {found}, "
            "so the submission would have no single provenance to check against the "
            "approved one. Re-run `forecast backtest` under one configuration."
        )
    return found[0]


def _read_backtest_results_or_say_what_to_run(workspace: Workspace) -> pd.DataFrame:
    """`backtest_results.parquet`, or the sentence that says how to make it."""
    if not workspace.artifacts.has(ARTIFACTS.backtest_results):
        raise SystemExit(
            f"{ARTIFACTS.backtest_results} is not in the cache, so there is nothing to "
            "submit or to verify. Run `forecast backtest` first."
        )
    return workspace.artifacts.read_table(ARTIFACTS.backtest_results)


def verify_submission(workspace: Workspace, today: date) -> int:
    """Print the three hashes and write nothing, under any configuration.

    This is what the documented one-command pipeline runs. It reports the
    divergence between the honest default and the shipped record every time,
    which is the single most confusing fact this change creates, exactly where a
    reader would look for it.
    """
    results = _read_backtest_results_or_say_what_to_run(workspace)
    live = workspace.settings.configuration_hash()
    producing = _hash_that_produced_the_artifacts(results)
    approved = shipping_approval.CONFIGURATION_HASH_APPROVED_FOR_SHIPPING

    forecasts_file = SUBMISSION_DIRECTORY / "forecasts.csv"
    manifest_file = SUBMISSION_DIRECTORY / "manifest.json"
    committed: str | None = None
    if forecasts_file.exists() and manifest_file.exists():
        try:
            recorded = json.loads(manifest_file.read_text(encoding="utf-8"))
            committed = str(recorded["configuration_hash"])
        except (OSError, ValueError, KeyError):
            committed = None

    print("submit --verify-only: nothing is written by this command.")
    print(f"  approved for shipping   : {approved}")
    print(f"  this run's settings     : {live}")
    print(f"  produced the artifacts  : {producing}   ({ARTIFACTS.backtest_results})")
    print(f"  committed submission    : {committed if committed else 'absent or unreadable'}")

    if committed is None:
        print(
            "\nThe committed submission is missing or its manifest cannot be read. That is "
            "a defect in the shipped record, not a routine divergence: restore it from git "
            "before anything else."
        )
        return 1
    if committed != approved:
        print(
            f"\nThe committed submission records {committed}, but the code says {approved} is "
            "what was approved. The shipped record and the constant that guards it have "
            "drifted apart. Fix one to match the other, in a commit that says which and why."
        )
        return 1
    if live != approved or producing != approved:
        print(
            "\nThis run differs from the shipped record, which is expected: the pipeline "
            "default is the honest configuration and the submission was produced by "
            f"{approved}. `forecast submit` will refuse to overwrite it without a named, "
            "single-use authorisation. See docs/adr/0008."
        )
    else:
        print("\nThis run is the approved configuration; `forecast submit` would ship it.")
    return 0


def submit(workspace: Workspace, today: date) -> int:
    """Write the final grid, shipping the base rate where a gate failed."""
    settings = workspace.settings
    forecasts = workspace.artifacts.read_table(ARTIFACTS.current_forecasts)
    verdicts = workspace.artifacts.read_table(ARTIFACTS.verdicts)
    results = _read_backtest_results_or_say_what_to_run(workspace)
    model = GaussianHiddenMarkovModel.from_dictionary(
        workspace.artifacts.read_json(ARTIFACTS.selected_model)
    )

    # Before anything is written. `authorise_shipping` returns None when there is
    # nothing to authorise -- a destination that is not the repository's own
    # submission, or a run that already is the approved configuration -- and the
    # consumed authorisation when a token let an unapproved run through.
    authorisation = shipping_approval.authorise_shipping(
        destination=SUBMISSION_DIRECTORY,
        repo_root=PROJECT_ROOT,
        live_configuration_hash=settings.configuration_hash(),
        producing_configuration_hash=_hash_that_produced_the_artifacts(results),
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
    if authorisation is not None:
        # Present only when a token let an unapproved run through, so a manifest
        # produced by the approved configuration keeps exactly today's schema.
        manifest["shipped_under_authorisation"] = authorisation.as_manifest_entry()
    (SUBMISSION_DIRECTORY / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(
        submission[["indicator", "horizon_years", "probability", "source"]].to_string(index=False)
    )
    if authorisation is not None:
        print(
            f"\nshipped under authorisation by {authorisation.by} "
            f"({authorisation.minted_at}): {authorisation.reason}"
        )
    print(f"\nwritten to {_display_path(SUBMISSION_DIRECTORY)}/")
    return 0


VARIANTS: tuple[tuple[str, bool, bool], ...] = (
    ("shipped", False, False),
    ("honest_state_count", True, False),
    ("honest_start", False, True),
    ("both", True, True),
)
"""The 2x2: (label, select the state count on a burn-in window, start point in time).

`shipped` is the configuration that produced `submission/forecasts.csv`; `both` is
the pipeline default from 2026-09-09. The middle two isolate one fix each, which
is the only way to say what each one cost.
"""


def compare_variants(workspace: Workspace, today: date) -> int:
    """Run all four cells of the look-ahead 2x2 against one unchanged decision rule.

    Every cell is judged by the same `evaluate_all_horizons` reading the same
    `load_decision_rule()`. The only input that differs per cell is the
    regimes-exist evidence, and it differs *towards* honesty: a cell that chose
    its state count on a burn-in window has that sweep read back to answer the
    gate, rather than the full-sample one it did not use.

    Around forty minutes, no network, deliberately not part of
    `run_full_pipeline.sh`: it is a one-off analysis, not a stage gate.
    """
    if not workspace.artifacts.has(ARTIFACTS.selected_model):
        raise SystemExit(
            f"{ARTIFACTS.selected_model} is not in the cache, and the two cells that keep "
            "the shipped state-count policy read it. Run `forecast fit-regimes` first."
        )
    full_sample_sweep = workspace.artifacts.read_table(ARTIFACTS.state_count_sweep)
    decision_rule = verdict_module.load_decision_rule()

    comparison_rows: list[dict[str, object]] = []
    manifest_entries: list[dict[str, object]] = []

    for label, on_burn_in, point_in_time in VARIANTS:
        started = time.perf_counter()
        settings = dataclasses.replace(
            DEFAULT_RUN_SETTINGS,
            select_state_count_on_a_burn_in_window=on_burn_in,
            start_walk_forward_when_every_input_is_point_in_time=point_in_time,
        )
        cell = dataclasses.replace(workspace, settings=settings)
        schedule = cell.backtest_schedule(today)

        if on_burn_in:
            choice = state_count_on_burn_in.choose_state_count_on_burn_in_window(
                cell.registry,
                cell.cache,
                settings,
                first_forecast_date=schedule.forecast_dates[0].date(),
                artifacts=cell.artifacts,
            )
            state_count = choice.state_count
            chosen_as_of = choice.chosen_as_of
            sweep_table = choice.sweep_table()
        else:
            selected = GaussianHiddenMarkovModel.from_dictionary(
                cell.artifacts.read_json(ARTIFACTS.selected_model)
            )
            state_count = int(selected.state_count)
            # The full-sample sweep is a statement about today's panel, so the
            # date it was chosen as of is today. That is the leak, named.
            chosen_as_of = today
            sweep_table = full_sample_sweep

        regimes_exist, evidence = regimes_exist_from_sweep_table(sweep_table)
        fallback_dates = walk_forward.forecast_dates_using_the_publication_lag_fallback(
            cell.registry, cell.cache, schedule.forecast_dates
        )

        print(
            f"\n{'=' * 78}\n{label}: {schedule.describe()}, {state_count} regimes chosen as of "
            f"{chosen_as_of.isoformat()}, hash {settings.configuration_hash()}, "
            f"{len(fallback_dates)} forecast dates on the publication-lag fallback\n{'=' * 78}"
        )

        results = walk_forward.run_walk_forward(
            cell.registry,
            cell.indicators,
            cell.cache,
            settings,
            state_count,
            schedule.forecast_dates,
            schedule.refit_dates,
            cell.artifacts,
        )
        cell.artifacts.write_table(ARTIFACTS.backtest_results_for_variant(label), results)

        verdicts = verdict_module.evaluate_all_horizons(
            results,
            settings.forecast_horizons_in_months,
            regimes_exist,
            evidence,
            seed=settings.random_seed,
            decision_rule=decision_rule,
        )
        table = verdict_module.verdict_table(verdicts)
        cell.artifacts.write_table(ARTIFACTS.verdicts_for_variant(label), table)

        elapsed = time.perf_counter() - started
        shared = {
            "variant": label,
            "select_state_count_on_burn_in": on_burn_in,
            "start_fully_point_in_time": point_in_time,
            "configuration_hash": settings.configuration_hash(),
            "state_count": state_count,
            "state_count_chosen_as_of": chosen_as_of.isoformat(),
            "first_forecast_date": schedule.forecast_dates[0].date().isoformat(),
            "last_forecast_date": schedule.forecast_dates[-1].date().isoformat(),
            "forecast_date_count": len(schedule.forecast_dates),
            "refit_count": len(schedule.refit_dates),
            "forecast_dates_using_fallback": len(fallback_dates),
        }
        for record in table.to_dict("records"):
            comparison_rows.append(
                {
                    **shared,
                    "horizon_months": int(record["horizon_months"]),
                    "verdict": record["verdict"],
                    "mean_brier_skill_score": float(record["mean_brier_skill_score"]),
                    "skill_lower_bound": float(record["skill_lower_bound"]),
                    "skill_upper_bound": float(record["skill_upper_bound"]),
                    "effective_independent_observations": float(
                        record["effective_independent_observations"]
                    ),
                    "failing_gates": record["failing_gates"],
                }
            )
        manifest_entries.append(
            {
                **shared,
                "seed": settings.random_seed,
                "regimes_exist": regimes_exist,
                "regimes_exist_evidence": evidence,
                "wall_clock_seconds": round(elapsed, 1),
            }
        )
        for item in verdicts:
            print(f"  {item.describe()}")

    comparison = pd.DataFrame(comparison_rows)
    workspace.artifacts.write_table(ARTIFACTS.variant_comparison, comparison)
    workspace.artifacts.write_json(
        ARTIFACTS.variant_comparison_manifest,
        {
            "generated_on": today.isoformat(),
            "package_version": __version__,
            "pre_registration": str(verdict_module.PRE_REGISTRATION_FILE.relative_to(PROJECT_ROOT)),
            "variants": manifest_entries,
        },
    )

    print(f"\n{_comparison_as_markdown(comparison)}")
    print(
        f"\nwritten to {_display_path(workspace.artifacts.path(ARTIFACTS.variant_comparison))} "
        f"and {_display_path(workspace.artifacts.path(ARTIFACTS.variant_comparison_manifest))}"
    )
    return 0


def _comparison_as_markdown(comparison: pd.DataFrame) -> str:
    """The table as it is transcribed into docs/RESULTS.md, printed once here."""
    header = (
        "| variant | start | states | dates | fallback | horizon | verdict | "
        "skill | 90% interval | independent |"
    )
    divider = "|---|---|---:|---:|---:|---:|---|---:|---|---:|"
    lines = [header, divider]
    for row in comparison.to_dict("records"):
        lines.append(
            f"| {row['variant']} | {row['first_forecast_date'][:7]} | {row['state_count']} | "
            f"{row['forecast_date_count']} | {row['forecast_dates_using_fallback']} | "
            f"{int(row['horizon_months']) // 12}y | {row['verdict']} | "
            f"{float(row['mean_brier_skill_score']):+.4f} | "
            f"[{float(row['skill_lower_bound']):+.4f}, "
            f"{float(row['skill_upper_bound']):+.4f}] | "
            f"{float(row['effective_independent_observations']):.1f} |"
        )
    return "\n".join(lines)


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
    _write_run_summary(workspace)
    print(f"\n{'=' * 78}\nAll five gates passed.")
    return 0


def _write_gate_reports(workspace: Workspace, reports: list[pipeline_gates.GateReport]) -> None:
    if reports:
        workspace.artifacts.write_table(
            ARTIFACTS.gate_reports, pd.concat([item.table() for item in reports])
        )


def _write_run_summary(workspace: Workspace) -> None:
    """Every run ends in the same shape, so two runs are comparable.

    The same `assemble_run_summary` that `forecast baseline capture` uses, so a
    committed baseline and a fresh run can never disagree about their own format.
    Written only after all five gates pass: a run that stopped at gate 4 has no
    evaluation to summarise, and a summary assembled from a half-finished cache
    would describe a run that never happened.
    """
    destination = workspace.artifacts.write_json(
        ARTIFACTS.run_summary, regression_baseline.assemble_run_summary(workspace.artifacts)
    )
    print(f"\nrun summary written to {_display_path(destination)}")


# ------------------------------------------------------- the regression baseline


def baseline_capture(
    workspace: Workspace,
    name: str,
    deterministic: bool,
    force: bool,
    directory: Path = regression_baseline.BASELINE_DIRECTORY,
) -> int:
    """Freeze what the cache currently holds as `baselines/<name>.json`, with every
    forecast beside it in `baselines/<name>.forecasts.parquet`.

    `directory` is a parameter for the same reason the register's file is: a test
    must be able to exercise the whole command without writing into the record the
    repository actually commits.
    """
    try:
        capture = regression_baseline.capture_baseline(
            workspace.artifacts, name, directory, deterministic=deterministic, force=force
        )
    except regression_baseline.BaselineError as error:
        print(f"baseline capture: {error}", file=sys.stderr)
        return 2

    document = capture.document
    destination = capture.summary_path
    run = document["run"]
    print(
        f"captured {name!r} from {_display_path(workspace.artifacts.directory)}: "
        f"configuration {run['configuration_hash']}, {run['state_count']} regimes, "
        f"{run['forecast_date_count']} forecast dates "
        f"{run['first_forecast_date']} to {run['last_forecast_date']}"
    )
    print(
        f"{len(document['horizons'])} horizon rows and {len(document['indicators'])} "
        f"indicator rows written to {_display_path(destination)}, format version "
        f"{document['format_version']}"
    )
    print(
        f"{capture.forecast_count} forecasts written to "
        f"{_display_path(capture.forecasts_path)} for the paired comparison"
    )
    if deterministic:
        print(
            "--deterministic: no capture time or commit recorded, so two captures match byte "
            "for byte"
        )
    return 0


def baseline_compare(
    workspace: Workspace,
    against: str,
    output_format: str,
    bands: list[str],
    directory: Path = regression_baseline.BASELINE_DIRECTORY,
    *,
    paired: bool = False,
    confidence_levels: list[float] | None = None,
) -> int:
    """Compare the artifacts in the cache against a committed baseline.

    Exit 0 when nothing moved, 1 when something did, 2 when the comparison could
    not be made at all. The third code is the important one: a comparison that
    could not line its two sides up has produced no evidence, and reporting that
    as a pass is the failure this whole module is built to avoid.

    `paired` asks the other question -- is this run better, or only different --
    by scoring both runs' forecasts on the same resampled dates. It measures and
    does not judge, so it exits 0 whenever the measurement could be made. Its seed
    and resample count come from the run settings. `confidence_levels` defaults to
    the run settings' one level; several give one interval each, all read off the
    same resamples. The output records every one of them.
    """
    try:
        baseline = regression_baseline.read_baseline(against, directory)
        current = regression_baseline.assemble_run_summary(workspace.artifacts)
        if paired:
            regression_baseline.check_format_version(baseline, current, against)
            settings = workspace.settings
            paired_comparison = regression_baseline.compare_paired(
                baseline,
                regression_baseline.read_baseline_forecasts(against, directory),
                current,
                regression_baseline.forecast_frame(workspace.artifacts),
                random_seed=settings.random_seed,
                resamples=settings.bootstrap_resamples,
                confidence_levels=confidence_levels or [settings.bootstrap_confidence_level],
                name=against,
            )
        else:
            comparison = regression_baseline.compare(baseline, current, against)
    except regression_baseline.BaselineError as error:
        print(f"baseline compare: {error}", file=sys.stderr)
        return 2

    if paired:
        if output_format == "json":
            print(json.dumps(paired_comparison.as_dictionary(), indent=2, sort_keys=True))
        else:
            print(paired_comparison.describe())
        return paired_comparison.exit_code
    if output_format == "json":
        print(json.dumps(comparison.as_dictionary(), indent=2, sort_keys=True))
    else:
        print(comparison.describe(bands))
    return comparison.exit_code


def _bands_to_show(chosen: list[str] | None) -> list[str]:
    """`--tolerance-band` as the band names the comparison uses.

    Nothing here changes a classification. `all` is the three field bands, and the
    default is the only one a reader usually wants: what moved, not the four
    hundred lines that did not.
    """
    if not chosen:
        return [regression_baseline.MOVED]
    if "all" in chosen:
        return [
            regression_baseline.IDENTICAL,
            regression_baseline.NUMERICAL,
            regression_baseline.MOVED,
        ]
    return [name.upper() for name in chosen]


def _confidence_level(text: str) -> float:
    """`--confidence-level` as a number strictly between zero and one, or argparse's
    refusal, which exits 2, saying what a confidence level is."""
    try:
        value = float(text)
    except ValueError:
        value = float("nan")
    if not 0.0 < value < 1.0:
        raise argparse.ArgumentTypeError(
            f"{text!r} is not a confidence level: it must lie strictly between 0 and 1, such "
            "as 0.90, or 0.9833 for a Bonferroni family-wise level over six arms"
        )
    return value


def baseline_list(directory: Path = regression_baseline.BASELINE_DIRECTORY) -> int:
    """Every committed baseline, one row each."""
    try:
        listing = regression_baseline.list_baselines(directory)
    except regression_baseline.BaselineError as error:
        print(f"baseline list: {error}", file=sys.stderr)
        return 2
    print(regression_baseline.describe_listing(listing, directory))
    return 0


# ------------------------------------------------------- the look-ahead audit


def audit_look_ahead(workspace: Workspace, today: date, cutoff: date | None) -> int:
    """Perturb everything unavailable at a cutoff and require no forecast to move.

    Exit 0 when every forecast issued on or before the cutoff is byte-identical,
    1 when one moved, which is a look-ahead, and 2 when the check could not be
    made. Both runs work on copies of the cache in a temporary directory, each with
    an empty fitted-model store; the project's own cache is only read, and the one
    thing written to it is the audit record, `look_ahead_audit.json`.
    """
    started = time.perf_counter()
    destination = workspace.artifacts.path(ARTIFACTS.look_ahead_audit)

    def configured_schedule(cache: SeriesCache) -> schedule_module.ForecastSchedule:
        return dataclasses.replace(workspace, cache=cache).backtest_schedule(today)

    with tempfile.TemporaryDirectory(prefix="look_ahead_audit_") as scratch:
        try:
            audit = look_ahead_audit.audit_look_ahead(
                workspace.registry,
                workspace.indicators,
                workspace.cache,
                workspace.settings,
                configured_schedule,
                Path(scratch),
                cutoff=cutoff,
            )
        except look_ahead_audit.LookAheadAuditError as error:
            workspace.artifacts.write_json(
                ARTIFACTS.look_ahead_audit, look_ahead_audit.failure_record(error, cutoff)
            )
            print(f"audit-look-ahead: {error}", file=sys.stderr)
            print(
                f"the check could not be made, which is not a pass; recorded in "
                f"{_display_path(destination)}",
                file=sys.stderr,
            )
            return 2

    workspace.artifacts.write_json(ARTIFACTS.look_ahead_audit, audit.as_dictionary())
    print(audit.describe())
    print(
        f"\nexit {audit.exit_code}; run time {time.perf_counter() - started:.0f} s; "
        f"written to {_display_path(destination)}"
    )
    return audit.exit_code


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
    # `submit` is pulled out of the loop below so it can carry a flag. The names
    # the loop registers are otherwise unchanged, and the set of subcommands is
    # the same, which is what `test_every_stage_has_a_subcommand` pins.
    submit_parser = subparsers.add_parser("submit", help="write the submission and its manifest")
    submit_parser.add_argument(
        "--verify-only",
        action="store_true",
        help=(
            "write nothing; print the approved, live and producing configuration hashes "
            "and whether the committed submission still records the approved one"
        ),
    )
    # `baseline` is the first subcommand with subcommands of its own. Three verbs
    # that all act on the same committed files belong under one name; three
    # top-level commands sharing a prefix would be the same thing spelled worse.
    baseline_parser = subparsers.add_parser(
        "baseline", help="capture, compare and list the committed regression baselines"
    )
    baseline_actions = baseline_parser.add_subparsers(dest="baseline_command", required=True)

    capture_parser = baseline_actions.add_parser(
        "capture", help="freeze what the cache holds as baselines/<name>.json"
    )
    capture_parser.add_argument(
        "--name", required=True, help="the baseline's name, and its filename"
    )
    capture_parser.add_argument(
        "--deterministic",
        action="store_true",
        help=(
            "omit the capture time and commit entirely, so two captures of one run are "
            "byte-identical. The comparison ignores that block either way"
        ),
    )
    capture_parser.add_argument(
        "--force", action="store_true", help="replace a baseline of this name that already exists"
    )

    compare_parser = baseline_actions.add_parser(
        "compare", help="the artifacts in the cache against a committed baseline"
    )
    compare_parser.add_argument(
        "--against", default="main", help="which baseline to compare against (default: main)"
    )
    compare_parser.add_argument(
        "--format", dest="output_format", choices=("table", "json"), default="table"
    )
    compare_parser.add_argument(
        "--tolerance-band",
        dest="tolerance_bands",
        action="append",
        choices=("moved", "numerical", "identical", "all"),
        help=(
            "which bands the table prints, repeatable (default: moved). This selects what "
            "is shown and never how a difference is classified: the boundary between "
            "NUMERICAL and MOVED is a constant in regression_baseline, not an argument, "
            "because a tolerance a caller can widen after seeing a result is not a tolerance"
        ),
    )
    compare_parser.add_argument(
        "--paired",
        action="store_true",
        help=(
            "instead of the field diff, the difference in the verdict's mean skill score per "
            "horizon, this run minus the baseline, on the forecasts both runs resolved, with a "
            "moving-block bootstrap interval that scores both runs on the same resampled dates. "
            "The comparison to trust when asking whether a change is an improvement"
        ),
    )
    compare_parser.add_argument(
        "--confidence-level",
        dest="confidence_levels",
        action="append",
        type=_confidence_level,
        help=(
            "with --paired, the interval's confidence level, strictly between 0 and 1 "
            "(default: the run settings' bootstrap_confidence_level). Repeatable: "
            "`--confidence-level 0.90 --confidence-level 0.9833` gives one interval per "
            "level, every one read off the same resamples"
        ),
    )

    baseline_actions.add_parser("list", help="every committed baseline, one row each")

    audit_parser = subparsers.add_parser(
        "audit-look-ahead",
        help=(
            "perturb every observation unavailable at a cutoff date and require every forecast "
            "issued on or before it to come out byte-identical"
        ),
    )
    audit_parser.add_argument(
        "--cutoff",
        type=date.fromisoformat,
        default=None,
        help=(
            "the date whose unavailable information is perturbed, YYYY-MM-DD (default: the first "
            f"refit at least {look_ahead_audit.DEFAULT_CUTOFF_MONTHS_AFTER_FIRST_FORECAST} months "
            "after the first forecast date)"
        ),
    )

    for name, help_text in (
        ("audit-data", "gate 1: measure the data against the registry"),
        ("fit-regimes", "gate 2: sweep the number of regimes and fit"),
        ("forecast-now", "gate 3: the current probability grid"),
        ("backtest", "gate 4: walk the method through history"),
        ("evaluate", "gate 5: apply the pre-registered decision rule"),
        ("check-gates", "run all five gates in order"),
        ("register", "record the shipped forecasts as dated, resolvable claims"),
        ("resolve", "score every registered forecast whose date has passed"),
        ("compare-variants", "the 2x2 of the two look-ahead fixes, against one decision rule"),
    ):
        subparsers.add_parser(name, help=help_text)
    return parser


def register_forecasts(workspace: Workspace, today: date) -> int:
    """Record what `forecast submit` shipped as dated claims about the future."""
    try:
        written, skipped = forecast_register.register(
            SUBMISSION_DIRECTORY / "forecasts.csv",
            SUBMISSION_DIRECTORY / "manifest.json",
            today,
        )
    except forecast_register.RegisterError as error:
        print(f"register: {error}", file=sys.stderr)
        return 2

    entries = forecast_register.read_register()
    print(f"registered {written} forecast(s); {skipped} already on record")
    if entries:
        upcoming = sorted({entry.resolves_on for entry in entries})
        print(f"{len(entries)} total in {_display_path(forecast_register.REGISTER_FILE)}")
        print(f"next resolves {upcoming[0]}, last {upcoming[-1]}")
    return 0


def resolve_forecasts(workspace: Workspace, today: date) -> int:
    """Score every registered forecast whose resolution date has passed."""
    entries = forecast_register.read_register()
    if not entries:
        print("nothing registered yet — run `forecast register` after `forecast submit`")
        return 0

    source_names = indicator_outcomes.required_series_names(list(workspace.indicators))
    series = load_final_series(workspace.registry, workspace.cache, source_names)

    try:
        outcome = forecast_register.resolve(series, today)
    except forecast_register.RegisterError as error:
        print(f"resolve: {error}", file=sys.stderr)
        return 2

    print(
        f"{outcome['registered']} registered · {outcome['due']} due by {today} · "
        f"{outcome['resolved_now']} newly resolved · {outcome['pending_data']} awaiting data"
    )
    if outcome["unknown_indicators"]:
        print(
            "indicators no longer in the registry: " + ", ".join(outcome["unknown_indicators"]),
            file=sys.stderr,
        )

    card = forecast_register.scorecard()
    if not card["n"]:
        print("no forecast has resolved yet. The register is the point; the wait is the price.")
        return 0

    print()
    print(
        f"resolved {card['n']} · Brier {card['brier']:.4f} vs "
        f"climatology {card['brier_climatology']:.4f} · skill {card['skill']:+.4f}"
    )
    for horizon, row in sorted(card["by_horizon"].items(), key=lambda kv: int(kv[0])):
        print(
            f"  {horizon:>2}y  n={row['n']:<4} brier {row['brier']:.4f}  "
            f"climatology {row['brier_climatology']:.4f}  skill {row['skill']:+.4f}"
        )
    if card["inert"]:
        print()
        print(
            f"INERT: {card['n']} resolved forecasts is below the ten this repository "
            "requires before a live skill score means anything. The numbers are "
            "printed; the inference is refused."
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if getattr(arguments, "paired", False) and getattr(arguments, "tolerance_bands", None):
        parser.error(
            "--tolerance-band selects rows of the field diff, which --paired does not print"
        )
    if getattr(arguments, "confidence_levels", None) and not getattr(arguments, "paired", False):
        parser.error("--confidence-level sets the paired comparison's interval; add --paired")
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
        if arguments.verify_only:
            return verify_submission(workspace, today)
        try:
            return submit(workspace, today)
        except shipping_approval.SubmissionNotApprovedError as error:
            # A traceback is not a message. An exit code of 2 with that text is,
            # matching how `register_forecasts` prints a `RegisterError`.
            print(f"submit: {error}", file=sys.stderr)
            return 2
    if arguments.command == "check-gates":
        return check_gates(workspace, today)
    if arguments.command == "compare-variants":
        return compare_variants(workspace, today)
    if arguments.command == "register":
        return register_forecasts(workspace, today)
    if arguments.command == "resolve":
        return resolve_forecasts(workspace, today)
    if arguments.command == "audit-look-ahead":
        return audit_look_ahead(workspace, today, arguments.cutoff)
    if arguments.command == "baseline":
        if arguments.baseline_command == "capture":
            return baseline_capture(
                workspace, arguments.name, arguments.deterministic, arguments.force
            )
        if arguments.baseline_command == "compare":
            return baseline_compare(
                workspace,
                arguments.against,
                arguments.output_format,
                _bands_to_show(arguments.tolerance_bands),
                paired=arguments.paired,
                confidence_levels=arguments.confidence_levels,
            )
        return baseline_list()

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
