"""Experiment 0008, arm B1: two of the registration's secondaries read under rule 0007.

  regimes_help   method minus R2 (condition_chain_probability, every forecast date), paired,
                 moving-block bootstrap with blocks as long as the horizon, 10,000 resamples,
                 seed 20260908; REGIMES HELP if the 90% interval is entirely above zero, REGIMES
                 DO NOT HELP if entirely below, NOT SHOWN otherwise. On the model-sample
                 benchmark (rule 0007's R1) and on the series-start one, for comparability with
                 the -0.0582 rule 0007 pins for the reference.
  pooled skill   one minus the sum of the method's Brier scores over the sum of R1's, over every
                 resolved row at the horizon, beside the mean of ratios. A claim is NOT
                 ESTABLISHED at a horizon where the two disagree in sign.

Both for B1's scored run and for reference-0008, computed by the same package functions
(evaluation/skill_by_horizon.matrices_at and _pooled_skill,
evaluation/paired_skill_comparison.paired_mean_skill_difference).

Run with PYTHONPATH at the arm's src/:
  .venv/bin/python research/arms/point-in-time-through-the-condition-chain/rule_0007_secondaries.py OUT RESULTS
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

SEED = 20260908
RESAMPLES = 10_000
LEVEL = 0.90
BENCHMARKS = {
    "model-sample": "model_sample_climatology_probability",
    "series-start": "climatology_probability",
}


def main(out: Path, results: Path) -> int:
    from economic_regime_forecasting import regression_baseline
    from economic_regime_forecasting.data.cache import ArtifactStore
    from economic_regime_forecasting.evaluation import skill_by_horizon
    from economic_regime_forecasting.evaluation.paired_skill_comparison import (
        paired_mean_skill_difference,
    )
    from economic_regime_forecasting.evaluation.verdict import _mean_skill_over, _scoreable_columns

    runs = {
        "B1": ArtifactStore(results.parent).read_table(results.name),
        "reference-0008": regression_baseline.read_baseline_forecasts("reference-0008"),
    }
    record: dict[str, Any] = {"regimes_help": [], "pooled_against_model_sample": []}
    for run, frame in runs.items():
        for horizon in (12, 60, 120):
            for benchmark, column in BENCHMARKS.items():
                method = skill_by_horizon.matrices_at(frame, horizon, "predicted_probability", column)
                chain = skill_by_horizon.matrices_at(
                    frame, horizon, "condition_chain_probability", column
                )
                result = paired_mean_skill_difference(
                    chain,
                    method,
                    block_length=horizon,
                    resamples=RESAMPLES,
                    seed=SEED,
                    confidence_levels=(LEVEL,),
                )
                interval = result.interval
                reading = "NOT SHOWN"
                if interval is not None and interval.lower_bound > 0.0:
                    reading = "REGIMES HELP"
                elif interval is not None and interval.upper_bound < 0.0:
                    reading = "REGIMES DO NOT HELP"
                record["regimes_help"].append(
                    {
                        "run": run,
                        "horizon_months": horizon,
                        "benchmark": benchmark,
                        "method_mean_skill": result.current_mean_skill,
                        "chain_mean_skill": result.baseline_mean_skill,
                        "difference": result.difference,
                        "interval_90": None
                        if interval is None
                        else [interval.lower_bound, interval.upper_bound],
                        "reading": reading,
                    }
                )
            matrices = skill_by_horizon.matrices_at(
                frame, horizon, "predicted_probability", BENCHMARKS["model-sample"]
            )
            columns = _scoreable_columns(
                matrices.predicted, matrices.realised, matrices.climatology
            )
            import numpy as np

            mean_of_ratios = _mean_skill_over(
                np.arange(matrices.predicted.shape[0]),
                matrices.predicted,
                matrices.realised,
                matrices.climatology,
                columns,
                require_every_indicator=True,
            )[0]
            pooled = skill_by_horizon._pooled_skill(matrices)
            record["pooled_against_model_sample"].append(
                {
                    "run": run,
                    "horizon_months": horizon,
                    "mean_of_ratios": mean_of_ratios,
                    "pooled": pooled,
                    "signs_agree": bool(np.sign(mean_of_ratios) == np.sign(pooled)),
                }
            )
    ArtifactStore(out).write_json("rule_0007_secondaries.json", record)
    for key, rows in record.items():
        print(key)
        for row in rows:
            print(f"  {row}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
