"""Experiment 0008, arm B1: how often is the chain's starting condition a revised value?

B1 makes every point-in-time forecast start from the last published value of the
indicator's own condition. That value is read, like every condition in the
walk-forward, from the FINAL file with publication timing enforced (debt D5): the
look-ahead audit does not perturb it, by design, and rule 0007 classes it as class B.
Main's point-in-time forecasts never read it; its any-time forecasts and rule 0007's
reference chain already do.

This counts, at every forecast date of the run, whether the starting condition read
from the final file differs from the one the archival vintage dated that forecast date
would have given, wherever that vintage is cached. It measures exposure, not the
corrected skill difference, which is the judged reviewer's to measure.

Run with PYTHONPATH at the arm's src/ and the arm's own cache:
  .venv/bin/python research/arms/point-in-time-through-the-condition-chain/starting_condition_revisions.py OUT
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

AS_OF = date(2026, 9, 29)


def main(out: Path) -> int:
    from economic_regime_forecasting import command_line_interface
    from economic_regime_forecasting.backtest import walk_forward
    from economic_regime_forecasting.configuration.registry import Composition
    from economic_regime_forecasting.data import federal_reserve_client, indicator_outcomes
    from economic_regime_forecasting.data.cache import ArtifactStore

    workspace = command_line_interface.Workspace.open()
    schedule = workspace.backtest_schedule(AS_OF)
    point_in_time = [
        item for item in workspace.indicators if item.composition is Composition.POINT_IN_TIME
    ]
    histories = walk_forward.prepare_indicator_history(
        point_in_time, workspace.registry, workspace.cache, (12,)
    )

    rows = []
    for indicator in point_in_time:
        name = indicator.resolution.series
        derived = workspace.registry.derived_by_name(name)
        entry = None if derived is not None else workspace.registry[name]
        revised = bool(entry is not None and entry.is_revised)
        compared = flips = vintage_lacks_the_label = not_cached = 0
        flip_dates: list[str] = []
        for stamp in schedule.forecast_dates:
            condition = walk_forward.condition_available_at(histories[indicator.name], stamp.date())
            label = pd.Timestamp(condition.index[-1])
            if not revised or entry is None:
                continue
            request = federal_reserve_client.build_request(entry.series_id, stamp.date())
            if not workspace.cache.contains(request):
                not_cached += 1
                continue
            vintage = workspace.cache.read(request).observations
            as_published = indicator_outcomes.monthly_condition(indicator, vintage).dropna()
            if label not in as_published.index:
                vintage_lacks_the_label += 1
                continue
            compared += 1
            if (float(as_published[label]) > 0.5) != (float(condition.iloc[-1]) > 0.5):
                flips += 1
                flip_dates.append(stamp.date().isoformat())
        rows.append(
            {
                "indicator": indicator.name,
                "series": name,
                "revised": revised,
                "forecast_dates": len(schedule.forecast_dates),
                "vintage_not_cached": not_cached,
                "vintage_lacks_the_starting_month": vintage_lacks_the_label,
                "compared": compared,
                "starting_condition_flips": flips,
                "flip_forecast_dates": flip_dates,
            }
        )
        print(rows[-1])

    ArtifactStore(out).write_json(
        "starting_condition_revisions.json",
        {
            "question": (
                "At each forecast date, does the last published condition B1 starts from, read "
                "from the final file, differ from the same month's condition in the archival "
                "vintage dated that forecast date?"
            ),
            "as_of": AS_OF.isoformat(),
            "indicators": rows,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
