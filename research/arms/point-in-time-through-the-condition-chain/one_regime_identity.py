"""Experiment 0008, arm B1: the one-regime diagnostics, run BEFORE the scored run.

The registration (proving/experiments/0008-condition-aware-regime-forecasts/
experiment.json) requires `end_to_end_identity`:

    B1 run with the state count fixed at one, through `forecast backtest` (never
    check-gates, and never `baseline compare`), writes forecasts that equal, bit for
    bit by array equality, the reference chain at REFIT cadence
    (run_walk_forward(..., condition_chain_cadence=ConditionChainCadence.REFIT)) over
    the same POINT-IN-TIME rows. ... On any-time rows the one-regime run must instead
    equal the model's own unchanged any-time composition, which is what main computes
    at one regime.

and two secondaries from the one-regime run, measurements rather than endpoints:

    cadence_effect      R2 at refit cadence minus R2 at every forecast date, paired, one year
    pure_regime_effect  B1's scored run minus B1 at one regime, paired, one year, on
                        point-in-time rows and on all rows

Nothing here changes what the package does. The state count is forced to one by
replacing `state_count_on_burn_in.state_count_for_the_backtest` -- the one place every
walk-forward caller asks for it (debt D15) -- inside this process only, and then
`forecast backtest` runs unchanged. Every other number comes from package functions.

Subcommands, in order:

  backtest-at-one-regime OUT LABEL   `forecast backtest` at one regime with whatever code
                                     PYTHONPATH names, into the cache
                                     ECONOMIC_REGIME_FORECASTING_CACHE names; LABEL b1 also
                                     runs the refit-cadence walk-forward on the same fits
  identity OUT                       the two identities, array equality, and cadence_effect
  pure-regime-effect OUT RESULTS     after the scored run: RESULTS is its backtest_results

OUT is this directory. Every table is written through data/cache.py's ArtifactStore.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

AS_OF = date(2026, 9, 29)
"""The day the scored run is made, so the one-regime run visits the same 391 dates."""

SEED = 20260908
RESAMPLES = 10_000
LEVELS = (0.90, 0.9667)
BENCHMARK = "model-sample"
KEY = ["indicator", "forecast_date", "horizon_months"]


def _store(out: Path):  # type: ignore[no-untyped-def]
    from economic_regime_forecasting.data.cache import ArtifactStore

    return ArtifactStore(out)


def _imported_from() -> str:
    import economic_regime_forecasting as package

    return str(Path(package.__file__).resolve())


# --------------------------------------------------------------- the runs


def backtest_at_one_regime(out: Path, label: str) -> int:
    from economic_regime_forecasting import command_line_interface
    from economic_regime_forecasting.backtest import state_count_on_burn_in, walk_forward

    print(f"code under test: {_imported_from()}")

    def one_regime(*_arguments: Any, **_keywords: Any) -> Any:
        return state_count_on_burn_in.BacktestStateCount(
            state_count=1,
            runner_up_state_count=None,
            description=(
                "1 regime, fixed for experiment 0008 arm B1's end_to_end_identity diagnostic; "
                "no sweep was run"
            ),
        )

    state_count_on_burn_in.state_count_for_the_backtest = one_regime  # type: ignore[assignment]

    code = command_line_interface.main(["--as-of", AS_OF.isoformat(), "backtest"])
    if code != 0:
        print(f"`forecast backtest` at one regime exited {code}; the diagnostic cannot be made")
        return code

    workspace = command_line_interface.Workspace.open()
    backtest = workspace.artifacts.read_table("backtest_results.parquet")
    _store(out).write_table(f"one_regime_{label}_backtest.parquet", backtest)
    print(f"wrote one_regime_{label}_backtest.parquet: {len(backtest)} rows")

    if label == "b1":
        schedule = workspace.backtest_schedule(AS_OF)
        refit_cadence = walk_forward.run_walk_forward(
            workspace.registry,
            workspace.indicators,
            workspace.cache,
            workspace.settings,
            1,
            schedule.forecast_dates,
            schedule.refit_dates,
            workspace.artifacts,
            condition_chain_cadence=walk_forward.ConditionChainCadence.REFIT,
        )
        _store(out).write_table("one_regime_b1_refit_cadence.parquet", refit_cadence)
        print(f"wrote one_regime_b1_refit_cadence.parquet: {len(refit_cadence)} rows")
    return 0


# --------------------------------------------------------------- the checks


def _keyed(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.sort_values(KEY).reset_index(drop=True)


def _same_keys(first: pd.DataFrame, second: pd.DataFrame) -> bool:
    return bool(first[KEY].reset_index(drop=True).equals(second[KEY].reset_index(drop=True)))


def _array_equality(name: str, left: np.ndarray, right: np.ndarray, rows: int) -> dict[str, Any]:
    equal = bool(np.array_equal(left, right))
    differing = int(np.sum(left != right))
    return {
        "check": name,
        "method": "numpy.array_equal, no tolerance",
        "rows": rows,
        "outcome": "PASS" if equal else "FAIL",
        "rows_differing": differing,
        "largest_absolute_difference": float(np.max(np.abs(left - right))) if rows else None,
    }


def _document(frame: pd.DataFrame) -> dict[str, Any]:
    from economic_regime_forecasting import regression_baseline

    hashes = sorted({str(value) for value in frame["configuration_hash"]})
    if len(hashes) != 1:
        raise SystemExit(f"a frame carries {len(hashes)} configuration hashes {hashes}")
    return {
        "format_version": regression_baseline.FORMAT_VERSION,
        "run": {"configuration_hash": hashes[0]},
        "horizons": [],
    }


def _paired(baseline: pd.DataFrame, current: pd.DataFrame) -> dict[str, Any]:
    """The harness's own paired machinery: regression_baseline.compare_paired, which
    lines the frames up and calls paired_skill_comparison.paired_mean_skill_difference
    with blocks as long as the horizon."""
    from economic_regime_forecasting import regression_baseline

    comparison = regression_baseline.compare_paired(
        _document(baseline),
        baseline,
        _document(current),
        current,
        random_seed=SEED,
        resamples=RESAMPLES,
        confidence_levels=LEVELS,
        name="baseline",
        benchmark=BENCHMARK,
    )
    document: dict[str, Any] = comparison.as_dictionary()
    return document


def _one_year(document: dict[str, Any]) -> dict[str, Any]:
    for row in document["horizons"]:
        if row["horizon_months"] == 12:
            return dict(row)
    raise SystemExit("no one-year horizon in the paired comparison")


def identity(out: Path) -> int:
    from economic_regime_forecasting.configuration.registry import Composition

    store = _store(out)
    b1 = _keyed(store.read_table("one_regime_b1_backtest.parquet"))
    refit = _keyed(store.read_table("one_regime_b1_refit_cadence.parquet"))
    main = _keyed(store.read_table("one_regime_main_backtest.parquet"))

    for name, frame in (("b1", b1), ("refit", refit), ("main", main)):
        counts = sorted({int(value) for value in frame["state_count"]})
        distributions = sorted({str(value) for value in frame["regime_distribution"]})
        if counts != [1] or distributions != ["1.000000"]:
            raise SystemExit(f"{name} is not a one-regime run: {counts}, {distributions[:3]}")
    if not (_same_keys(b1, refit) and _same_keys(b1, main)):
        raise SystemExit("the three one-regime frames do not cover the same forecasts")

    point_in_time = (b1["composition"] == Composition.POINT_IN_TIME.value).to_numpy()
    any_time = (b1["composition"] == Composition.ANY_TIME_WITHIN_HORIZON.value).to_numpy()

    checks = [
        _array_equality(
            "end_to_end_identity, point-in-time rows: B1 at one regime's predicted_probability "
            "equals the reference chain at REFIT cadence (condition_chain_probability of "
            "run_walk_forward(..., condition_chain_cadence=REFIT) on the same one-regime fits)",
            b1.loc[point_in_time, "predicted_probability"].to_numpy(),
            refit.loc[point_in_time, "condition_chain_probability"].to_numpy(),
            int(point_in_time.sum()),
        ),
        _array_equality(
            "end_to_end_identity, any-time rows: B1 at one regime's predicted_probability "
            "equals main's own any-time composition at one regime (main's code, 99f232d)",
            b1.loc[any_time, "predicted_probability"].to_numpy(),
            main.loc[any_time, "predicted_probability"].to_numpy(),
            int(any_time.sum()),
        ),
        _array_equality(
            "determinism: the refit-cadence walk-forward, reading the same cached one-regime "
            "fits, reproduces B1's one-regime predicted_probability on every row",
            b1["predicted_probability"].to_numpy(),
            refit["predicted_probability"].to_numpy(),
            len(b1),
        ),
    ]
    # Recorded, not required: main's point-in-time rows are NOT the chain by construction.
    contrast = _array_equality(
        "contrast (expected to differ): main at one regime's point-in-time rows against the "
        "same refit-cadence chain",
        main.loc[point_in_time, "predicted_probability"].to_numpy(),
        refit.loc[point_in_time, "condition_chain_probability"].to_numpy(),
        int(point_in_time.sum()),
    )

    cadence = _paired(
        b1.assign(predicted_probability=b1["condition_chain_probability"]),
        refit.assign(predicted_probability=refit["condition_chain_probability"]),
    )

    passed = all(item["outcome"] == "PASS" for item in checks)
    record = {
        "experiment": "0008-condition-aware-regime-forecasts",
        "arm": "B1-point-in-time-through-the-condition-chain",
        "as_of": AS_OF.isoformat(),
        "configuration_hash_b1_one_regime": _document(b1)["run"]["configuration_hash"],
        "configuration_hash_main_one_regime": _document(main)["run"]["configuration_hash"],
        "forecast_dates": int(b1["forecast_date"].nunique()),
        "first_forecast_date": str(pd.Timestamp(b1["forecast_date"].min()).date()),
        "last_forecast_date": str(pd.Timestamp(b1["forecast_date"].max()).date()),
        "end_to_end_identity": "PASS" if passed else "FAIL",
        "checks": checks,
        "contrast": contrast,
        "cadence_effect": {
            "definition": "R2 at refit cadence minus R2 at every forecast date, paired, one year",
            "baseline": "condition_chain_probability, every forecast date (rule 0007's R2)",
            "current": "condition_chain_probability, refit cadence",
            "registered_expectation": "about -0.004",
            "one_year": _one_year(cadence),
            "every_horizon": cadence,
        },
    }
    store.write_json("one_regime_identity.json", record)
    print(f"end_to_end_identity: {record['end_to_end_identity']}")
    for item in [*checks, contrast]:
        print(f"  {item['outcome']}  {item['rows']} rows, {item['rows_differing']} differ: "
              f"{item['check']}")
    one_year = record["cadence_effect"]["one_year"]
    print(f"cadence_effect, one year: {one_year}")
    return 0 if passed else 1


def pure_regime_effect(out: Path, results: Path) -> int:
    from economic_regime_forecasting.configuration.registry import Composition

    store = _store(out)
    one_regime = _keyed(store.read_table("one_regime_b1_backtest.parquet"))
    scored = _keyed(_store(results.parent).read_table(results.name))
    if not _same_keys(one_regime, scored):
        raise SystemExit("the scored run and the one-regime run do not cover the same forecasts")
    point_in_time = Composition.POINT_IN_TIME.value

    def only(frame: pd.DataFrame) -> pd.DataFrame:
        return frame[frame["composition"] == point_in_time]

    every_row = _paired(one_regime, scored)
    point_in_time_rows = _paired(only(one_regime), only(scored))
    record = {
        "definition": "B1's scored run minus B1 at one regime, paired, one year",
        "baseline": "one_regime_b1_backtest.parquet",
        "current": str(results),
        "current_configuration_hash": _document(scored)["run"]["configuration_hash"],
        "current_state_counts": sorted({int(value) for value in scored["state_count"]}),
        "point_in_time_rows": {
            "one_year": _one_year(point_in_time_rows),
            "every_horizon": point_in_time_rows,
        },
        "all_rows": {"one_year": _one_year(every_row), "every_horizon": every_row},
    }
    store.write_json("pure_regime_effect.json", record)
    print(f"pure_regime_effect, point-in-time rows, one year: {record['point_in_time_rows']['one_year']}")
    print(f"pure_regime_effect, all rows, one year: {record['all_rows']['one_year']}")
    return 0


def main(arguments: list[str]) -> int:
    if len(arguments) == 3 and arguments[0] == "backtest-at-one-regime":
        return backtest_at_one_regime(Path(arguments[1]), arguments[2])
    if len(arguments) == 2 and arguments[0] == "identity":
        return identity(Path(arguments[1]))
    if len(arguments) == 3 and arguments[0] == "pure-regime-effect":
        return pure_regime_effect(Path(arguments[1]), Path(arguments[2]))
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
