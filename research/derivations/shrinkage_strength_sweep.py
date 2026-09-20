"""D3: what does the conditional-rate shrinkage strength buy?

`conditional_rate_shrinkage_strength` is 10.0. The brief said to start there and
tune by cross-validation; it was set and left. This sweeps it inside the
walk-forward and scores each value with the pre-registered verdict's own
statistic, so the curve is in the same units as every other number here.

Only rate estimation re-runs: the fitted models are read from the artifact store,
and the shrinkage does not enter a fit.

Run: .venv/bin/python research/derivations/shrinkage_strength_sweep.py
"""

from __future__ import annotations

import dataclasses
from datetime import date

from economic_regime_forecasting import command_line_interface as interface
from economic_regime_forecasting.backtest import walk_forward
from economic_regime_forecasting.evaluation import verdict as verdict_module
from economic_regime_forecasting.models.state_selection import regimes_exist_from_sweep_table

STRENGTHS = (1.0, 3.0, 10.0, 30.0, 100.0)


def main() -> None:
    workspace = interface.Workspace.open()
    today = date(2026, 9, 20)
    schedule = workspace.backtest_schedule(today)
    state_count = interface._state_count_for_the_backtest(workspace, schedule)
    sweep_table = interface._sweep_the_verdict_should_read(workspace)
    regimes_exist, evidence = regimes_exist_from_sweep_table(sweep_table)
    horizons = workspace.settings.forecast_horizons_in_months

    print(f"  {schedule.describe()}, {state_count} regimes")
    print(f"  shipped strength is {workspace.settings.conditional_rate_shrinkage_strength}\n")
    header = f"  {'strength':>9} " + " ".join(f"{h:>10}m" for h in horizons)
    print(header)
    print("  " + "-" * (len(header) - 2))

    for strength in STRENGTHS:
        settings = dataclasses.replace(
            workspace.settings, conditional_rate_shrinkage_strength=strength
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
        verdicts = verdict_module.evaluate_all_horizons(
            results, horizons, regimes_exist, evidence, seed=settings.random_seed
        )
        skills = {v.horizon_in_months: v.mean_brier_skill_score for v in verdicts}
        row = " ".join(f"{skills.get(h, float('nan')):>+11.4f}" for h in horizons)
        marker = "  <- shipped" if strength == 10.0 else ""
        print(f"  {strength:>9.0f} {row}{marker}", flush=True)


if __name__ == "__main__":
    main()
