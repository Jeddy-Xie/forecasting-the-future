"""D5: how large is the approximation in reading conditions from final data?

The walk-forward reads conditions and outcomes from final revised values, with
publication timing enforced but not vintage. For market rates and recession
dating that is exact; for the revised series it is an approximation, and D5's
open half is that its size was argued rather than measured.

This measures it. For every refit date, the archival vintage of each revised
series that is NOT a model input is compared against the final file on the months
both cover and that had been published by that date. What matters is not the
revision itself but whether it would have changed a condition, so the spread is
reported in the series' own units alongside the share of months that moved at all.

Dates whose vintage is not cached are skipped and counted, so this runs on a
partial cache and says how partial it was.

Run: .venv/bin/python research/derivations/vintage_vs_final_conditions.py
"""

from __future__ import annotations

from datetime import date

import numpy as np

from economic_regime_forecasting import command_line_interface as interface
from economic_regime_forecasting.data import federal_reserve_client, indicator_outcomes
from economic_regime_forecasting.data.panel import load_final_series


def main() -> None:
    workspace = interface.Workspace.open()
    schedule = workspace.backtest_schedule(date(2026, 9, 20))
    # Only the series the conditions and outcomes actually read, and of those only
    # the revised ones that are not model inputs. A model input already gets its
    # archival vintage; an unrevised series has nothing to revise. Measuring any
    # other series would report an exposure the walk-forward does not have: payroll
    # employment, for instance, moves in 72% of months and is never read here.
    required = indicator_outcomes.required_series_names(workspace.indicators)
    model_inputs = {s.name for s in workspace.registry.model_inputs}
    series_wanted = [
        workspace.registry[name]
        for name in sorted(required)
        if workspace.registry.derived_by_name(name) is None
        and workspace.registry[name].is_revised
        and name not in model_inputs
    ]
    final = load_final_series(workspace.registry, workspace.cache, [s.name for s in series_wanted])

    print(f"  refit dates: {len(schedule.refit_dates)}")
    print(f"  conditions and outcomes read: {', '.join(sorted(required))}")
    print(
        f"  of those, revised and not a model input: "
        f"{', '.join(s.series_id for s in series_wanted)}\n"
    )
    header = (
        f"  {'series':<10} {'dates':>7} {'months':>8} {'differ':>8} "
        f"{'share':>9} {'mean |d|':>10} {'max |d|':>9}  condition flips"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))

    for entry in series_wanted:
        truth = final[entry.name]
        compared = moved = used_dates = skipped = 0
        total_absolute = 0.0
        largest = 0.0
        thresholds = {
            indicator.resolution.threshold
            for indicator in workspace.indicators
            if indicator.resolution.series == entry.name
            and indicator.resolution.threshold is not None
        }
        flips = dict.fromkeys(thresholds, 0)
        for stamp in schedule.refit_dates:
            as_of = stamp.date()
            request = federal_reserve_client.build_request(entry.series_id, as_of)
            if not workspace.cache.contains(request):
                skipped += 1
                continue
            used_dates += 1
            vintage = workspace.cache.read(request).observations
            vintage = vintage[vintage.index <= stamp]
            common = truth.index.intersection(vintage.index)
            if common.empty:
                continue
            a = truth.loc[common].to_numpy(dtype="float64")
            b = vintage.loc[common].to_numpy(dtype="float64")
            both = np.isfinite(a) & np.isfinite(b)
            if not both.any():
                continue
            difference = np.abs(a[both] - b[both])
            compared += int(both.sum())
            moved += int((difference > 1e-9).sum())
            for threshold in flips:
                flips[threshold] += int(((a[both] > threshold) != (b[both] > threshold)).sum())
            total_absolute += float(difference.sum())
            largest = max(largest, float(difference.max()))

        share = f"{100.0 * moved / compared:.3f}%" if compared else "-"
        mean = f"{total_absolute / compared:.5f}" if compared else "-"
        flip_text = (
            ", ".join(f"> {threshold:g}: {count}" for threshold, count in sorted(flips.items()))
            or "-"
        )
        print(
            f"  {entry.series_id:<10} {used_dates:>7} {compared:>8} {moved:>8} "
            f"{share:>9} {mean:>10} {largest:>9.4f}  {flip_text}"
        )
        if skipped:
            print(f"  {'':<10} {skipped} refit date(s) skipped: vintage not cached")

    print(
        "\n  'differ' counts published months whose archival value is not the final one."
        "\n  'condition flips' is the number that matters: a revision only reaches a forecast"
        "\n  by crossing an indicator's threshold. A series that never flips is exact in"
        "\n  effect, however often it is revised."
    )


if __name__ == "__main__":
    main()
