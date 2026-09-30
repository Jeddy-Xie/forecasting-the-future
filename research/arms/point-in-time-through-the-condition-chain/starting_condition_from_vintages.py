"""Experiment 0008, arm B1: the class-B correction for the chain's starting condition.

`starting_condition_revisions.py` found that the condition B1 starts from, read from
the final file with publication timing enforced (debt D5), is not the value the
archival vintage dated the forecast date holds on 58 of 389 forecast dates for
industrial production and 6 of 391 for consumer prices. Rule 0007 classes this as
class B (revised values of observations already published) and asks for the
corrected one-year paired difference: RECORDED-NOT-VOID if the correction moves it by
less than 0.001 and moves no verdict.

This replays B1's walk-forward AFTER the scored run, reading its cached fits, with one
thing changed: for the point-in-time indicators on the two series that have an
archival vintage at every forecast date -- consumer prices and industrial production,
both model inputs -- the condition the forecast starts from, and the month it is
dated, are read from the vintage dated the forecast date instead of the final file.
The per-regime rates are left exactly as they are (their own D5 exposure is main's,
not this arm's). Unemployment (0 flips at the 35 dates its vintage is cached; D5
measured 15 flips in 24,584 months) and recession dating (dated by announcement, ADR
0011) are left on the final file.

It is a supplementary measurement by the arm's author, not the independent judged
review the registration requires; that reviewer measures this independently.

Run with PYTHONPATH at the arm's src/ and ECONOMIC_REGIME_FORECASTING_CACHE at a COPY
of the arm's cache after the scored run:
  .venv/bin/python research/arms/point-in-time-through-the-condition-chain/starting_condition_from_vintages.py OUT
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

AS_OF = date(2026, 9, 29)
SEED = 20260908
RESAMPLES = 10_000
LEVELS = (0.90, 0.9667)
SERIES_READ_FROM_VINTAGES = ("consumer_price_index", "industrial_production")
KEY = ["indicator", "forecast_date", "horizon_months"]


def main(out: Path) -> int:
    from economic_regime_forecasting import command_line_interface, regression_baseline
    from economic_regime_forecasting.backtest import state_count_on_burn_in, walk_forward
    from economic_regime_forecasting.configuration.registry import Composition
    from economic_regime_forecasting.data import federal_reserve_client, indicator_outcomes
    from economic_regime_forecasting.data.cache import ArtifactStore

    workspace = command_line_interface.Workspace.open()
    settings = workspace.settings
    registry = workspace.registry
    schedule = workspace.backtest_schedule(AS_OF)
    scored = workspace.artifacts.read_table("backtest_results.parquet")
    if sorted(set(scored["configuration_hash"])) != [settings.configuration_hash()]:
        raise SystemExit("the cache's backtest is not this configuration's scored run")

    decided = state_count_on_burn_in.state_count_for_the_backtest(
        registry,
        workspace.cache,
        settings,
        first_forecast_date=schedule.forecast_dates[0].date(),
        artifacts=workspace.artifacts,
    )
    corrected_indicators = {
        item.name
        for item in workspace.indicators
        if item.composition is Composition.POINT_IN_TIME
        and item.resolution.series in SERIES_READ_FROM_VINTAGES
    }

    original = walk_forward.condition_available_at
    replaced: dict[str, int] = dict.fromkeys(sorted(corrected_indicators), 0)

    def condition_available_at(history: Any, as_of: date) -> pd.Series:
        # Only the forecast-date read inside run_walk_forward, never the refit-time read in
        # fit_regime_model that the per-regime rates are learned from.
        caller = sys._getframe(1).f_code.co_name
        if caller != "run_walk_forward" or history.indicator.name not in corrected_indicators:
            return original(history, as_of)
        entry = registry[history.indicator.resolution.series]
        request = federal_reserve_client.build_request(entry.series_id, as_of)
        if not workspace.cache.contains(request):
            raise SystemExit(f"no archival vintage of {entry.series_id} as of {as_of}")
        vintage = workspace.cache.read(request).observations.dropna()
        as_published = indicator_outcomes.monthly_condition(history.indicator, vintage).dropna()
        final = original(history, as_of)
        if (
            as_published.index[-1] != final.index[-1]
            or (as_published.iloc[-1] > 0.5) != (final.iloc[-1] > 0.5)
        ):
            replaced[history.indicator.name] += 1
        return as_published

    walk_forward.condition_available_at = condition_available_at  # type: ignore[assignment]
    corrected = walk_forward.run_walk_forward(
        registry,
        workspace.indicators,
        workspace.cache,
        settings,
        decided.state_count,
        schedule.forecast_dates,
        schedule.refit_dates,
        workspace.artifacts,
    )
    walk_forward.condition_available_at = original

    # Only the corrected indicators' point-in-time predictions, and the reference chain
    # beside them, may have moved.
    left = scored.sort_values(KEY).reset_index(drop=True)
    right = corrected.sort_values(KEY).reset_index(drop=True)
    untouched = ~left["indicator"].isin(corrected_indicators)
    for column in left.columns:
        if column in ("predicted_probability", "condition_chain_probability"):
            same = left.loc[untouched, column].equals(right.loc[untouched, column])
        else:
            same = left[column].equals(right[column])
        if not same:
            raise SystemExit(f"the replay moved {column!r} outside the corrected indicators")
    moved_rows = int(
        (left["predicted_probability"] != right["predicted_probability"]).sum()
    )

    reference = regression_baseline.read_baseline("reference-0008")
    reference_forecasts = regression_baseline.read_baseline_forecasts("reference-0008")

    def document(frame: pd.DataFrame) -> dict[str, Any]:
        return {
            "format_version": regression_baseline.FORMAT_VERSION,
            "run": {"configuration_hash": str(frame["configuration_hash"].iloc[0])},
            "horizons": [],
        }

    def paired(frame: pd.DataFrame) -> dict[str, Any]:
        result: dict[str, Any] = regression_baseline.compare_paired(
            reference,
            reference_forecasts,
            document(frame),
            frame,
            random_seed=SEED,
            resamples=RESAMPLES,
            confidence_levels=LEVELS,
            name="reference-0008",
            benchmark="model-sample",
        ).as_dictionary()
        return result

    as_scored = paired(scored)
    as_corrected = paired(corrected)

    def horizons(document: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                key: row[key]
                for key in ("horizon_months", "difference", "intervals", "rows_in_both")
            }
            for row in document["horizons"]
        ]

    one_year_scored = next(r for r in as_scored["horizons"] if r["horizon_months"] == 12)
    one_year_corrected = next(r for r in as_corrected["horizons"] if r["horizon_months"] == 12)
    record = {
        "question": (
            "rule 0007 class B: B1 minus reference-0008, paired, model-sample, with the "
            "starting condition of the consumer-price and industrial-production point-in-time "
            "indicators read from the archival vintage dated each forecast date"
        ),
        "corrected_indicators": sorted(corrected_indicators),
        "forecast_dates_whose_starting_condition_or_month_changed": replaced,
        "rows_whose_predicted_probability_moved": moved_rows,
        "as_scored": horizons(as_scored),
        "as_corrected": horizons(as_corrected),
        "one_year_shift": one_year_corrected["difference"] - one_year_scored["difference"],
        "per_indicator_one_year_corrected": [
            row for row in as_corrected["indicators"] if row["horizon_months"] == 12
        ],
    }
    ArtifactStore(out).write_json("starting_condition_from_vintages.json", record)
    for key in ("forecast_dates_whose_starting_condition_or_month_changed",
                "rows_whose_predicted_probability_moved", "as_scored", "as_corrected",
                "one_year_shift"):
        print(f"{key}: {record[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
