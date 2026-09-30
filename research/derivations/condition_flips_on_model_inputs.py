"""D5, reopened: the conditions read from final data on series that ARE model inputs.

`vintage_vs_final_conditions.py` measured D5 on the revised series that are not model
inputs (UNRATE, USREC), on the grounds that model inputs already get archival
vintages. They do -- as model INPUTS. The CONDITIONS an indicator's per-regime rates
learn from, and the reference chain starts from, are read from final data by
`load_final_series` whatever the series is. So output growth and consumer price
inflation conditions carry the same approximation, and it was never measured. The
2026-09-25 review measured it; this reproduces it from committed code.

For every forecast date, each indicator whose source series is a revised model input
has its monthly condition computed twice with the indicator's own rule: once from the
archival vintage current at that date, once from the final file. Months are counted
only where both have a value and the month had been published by that date. What is
reported is the share of those condition-months that differ.

Run: .venv/bin/python research/derivations/condition_flips_on_model_inputs.py
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from economic_regime_forecasting import command_line_interface as interface
from economic_regime_forecasting.backtest.walk_forward import publication_dates
from economic_regime_forecasting.data import federal_reserve_client, indicator_outcomes
from economic_regime_forecasting.data.panel import load_final_series


def main() -> None:
    workspace = interface.Workspace.open()
    schedule = workspace.backtest_schedule(date(2026, 9, 29))
    model_inputs = {entry.name for entry in workspace.registry.model_inputs}
    indicators = [
        indicator
        for indicator in workspace.indicators
        if indicator.resolution.series in model_inputs
        and workspace.registry[indicator.resolution.series].is_revised
    ]
    final = load_final_series(
        workspace.registry,
        workspace.cache,
        sorted({indicator.resolution.series for indicator in indicators}),
    )
    print(f"  forecast dates: {len(schedule.forecast_dates)}")
    header = f"  {'indicator':<60} {'dates':>6} {'months':>9} {'differ':>7} {'share':>8}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for indicator in indicators:
        entry = workspace.registry[indicator.resolution.series]
        final_condition = indicator_outcomes.monthly_condition(indicator, final[entry.name])
        compared = differ = used = skipped = 0
        for stamp in schedule.forecast_dates:
            request = federal_reserve_client.build_request(entry.series_id, stamp.date())
            if not workspace.cache.contains(request):
                skipped += 1
                continue
            used += 1
            vintage = workspace.cache.read(request).observations
            vintage_condition = indicator_outcomes.monthly_condition(indicator, vintage)
            published = publication_dates(
                pd.DatetimeIndex(vintage_condition.index), entry.publication_lag_days
            )
            vintage_condition = vintage_condition[published <= stamp].dropna()
            common = vintage_condition.index.intersection(final_condition.dropna().index)
            if common.empty:
                continue
            compared += len(common)
            differ += int(
                (vintage_condition.loc[common] != final_condition.loc[common]).sum()
            )
        share = f"{100.0 * differ / compared:.3f}%" if compared else "-"
        print(f"  {indicator.name:<60} {used:>6} {compared:>9} {differ:>7} {share:>8}")
        if skipped:
            print(f"  {'':<60} {skipped} date(s) skipped: vintage not cached")


if __name__ == "__main__":
    main()
