"""D5: archival vintages for the series that are read but never modelled.

`forecast fetch-data` fetches archival vintages only for revised MODEL INPUTS,
of which there are three. The conditions and outcomes are read from four further
revised series -- unemployment, payrolls, core prices and recession dating --
which get today's revised file with publication timing enforced but no vintage.
That is the open half of debt D5.

This fetches those vintages so the question can be measured rather than argued.
Idempotent: anything already cached is skipped, so it is safe to re-run after a
rate-limit block.

Run: .venv/bin/python research/derivations/fetch_outcome_vintages.py
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date

from economic_regime_forecasting import command_line_interface as interface
from economic_regime_forecasting.data import federal_reserve_client

WORKERS = 2  # gentler: the service blocks an address that asks too fast


def main() -> None:
    workspace = interface.Workspace.open()
    schedule = workspace.widest_backtest_schedule(date(2026, 9, 20))
    model_inputs = {s.name for s in workspace.registry.model_inputs}
    wanted_series = [
        s for s in workspace.registry.series if s.is_revised and s.name not in model_inputs
    ]

    jobs = [
        (entry, stamp.date())
        for entry in wanted_series
        for stamp in schedule.forecast_dates
        if not workspace.cache.contains(
            federal_reserve_client.build_request(entry.series_id, stamp.date())
        )
    ]
    print(
        f"  {len(wanted_series)} series read but not modelled: "
        f"{', '.join(s.series_id for s in wanted_series)}"
    )
    print(
        f"  {len(jobs)} archival vintages to fetch over {len(schedule.forecast_dates)} dates\n",
        flush=True,
    )
    if not jobs:
        print("  nothing to fetch")
        return

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
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for done, failure in enumerate(pool.map(fetch_one, jobs), start=1):
            if failure:
                failures.append(failure)
            if done % 200 == 0:
                print(f"  {done}/{len(jobs)}, {len(failures)} failed", flush=True)

    print(f"\n  fetched {len(jobs) - len(failures)} of {len(jobs)}; {len(failures)} failed")
    for line in failures[:5]:
        print(f"    {line}")
    if failures:
        print("  re-run to retry: anything already cached is skipped")


if __name__ == "__main__":
    main()
