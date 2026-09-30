"""Experiment 0008's secondary measurements for one backtest frame, from committed code only.

Not an endpoint and not a harness output. For the arm's and the reference's backtest
frames it prints, per horizon:

- mean Brier skill against R1 (model-sample climatology) with its 90% moving-block
  interval, and rule 0007's skill, robustness and honesty gates, by running 0001's
  own `evaluate_horizon` with R1 in the benchmark column (0007 keeps 0001's
  thresholds). 0007's calibration test is not implemented in the package and is
  not computed here;
- pooled Brier skill against R1 (one minus the ratio of summed Brier scores over
  every resolved row), beside the mean of ratios, per 0007;
- the frame's forecast minus R2 (the `condition_chain_probability` column scored as
  a forecaster), paired on the same resamples, against both benchmarks: 0007's
  `regimes_help` statistic and its `not_beaten_by_the_chain` gate.

Every statistic is the package's own: `regression_baseline` lays the matrices out
and `evaluation.paired_skill_comparison` computes the paired difference, exactly as
`forecast baseline compare --paired` does.

Run with PYTHONPATH pointing at the src/ whose code should be used:
    python secondaries.py <backtest_results.parquet> [<label>]
"""

from __future__ import annotations

import json
import sys
from typing import Any

import numpy as np
import pandas as pd

from economic_regime_forecasting import regression_baseline as rb
from economic_regime_forecasting.evaluation import paired_skill_comparison as psc
from economic_regime_forecasting.evaluation import verdict as verdict_module

SEED = 20260908
RESAMPLES = 10_000
LEVELS = (0.90, 0.9667)
HORIZONS = (12, 60, 120)


def _minus_the_chain(frame: pd.DataFrame, benchmark: str) -> list[dict[str, Any]]:
    column = rb.BENCHMARK_COLUMNS[benchmark]
    document = {"run": {"configuration_hash": str(frame["configuration_hash"].iloc[0])}}
    chain = frame.assign(predicted_probability=frame["condition_chain_probability"])
    method_resolved = rb._resolved_forecasts(frame, document, "method", column)
    chain_resolved = rb._resolved_forecasts(chain, document, "chain", column)
    rows = []
    for horizon in HORIZONS:
        method_at = rb._at_horizon(method_resolved, horizon)
        chain_at = rb._at_horizon(chain_resolved, horizon)
        both = method_at.index.intersection(chain_at.index)
        assert len(both) == len(method_at) == len(chain_at)
        dates = sorted(set(both.get_level_values("forecast_date")))
        names = sorted({str(value) for value in both.get_level_values("indicator")})
        result = psc.paired_mean_skill_difference(
            rb._matrices(chain_at.loc[both], dates, names, column),
            rb._matrices(method_at.loc[both], dates, names, column),
            block_length=horizon,
            resamples=RESAMPLES,
            seed=SEED,
            confidence_levels=LEVELS,
        )
        rows.append(
            {
                "benchmark": benchmark,
                "horizon_months": horizon,
                "method_mean_skill": result.current_mean_skill,
                "chain_mean_skill": result.baseline_mean_skill,
                "method_minus_chain": result.difference,
                "intervals": {
                    f"{item.confidence_level:.4f}": [item.lower_bound, item.upper_bound]
                    for item in result.intervals
                },
            }
        )
    return rows


def _against_r1(frame: pd.DataFrame) -> list[dict[str, Any]]:
    on_r1 = frame.assign(climatology_probability=frame["model_sample_climatology_probability"])
    rule = verdict_module.load_decision_rule()
    rows = []
    for horizon in HORIZONS:
        verdict = verdict_module.evaluate_horizon(
            on_r1, horizon, True, "not evaluated here", rule, SEED
        )
        gates = {gate.name: gate.passed for gate in verdict.gates}
        resolved = on_r1[on_r1["horizon_months"] == horizon].dropna(
            subset=["realised_outcome", "climatology_probability"]
        )
        outcome = resolved["realised_outcome"].to_numpy()
        method_brier = float(np.sum((resolved["predicted_probability"].to_numpy() - outcome) ** 2))
        r1_brier = float(np.sum((resolved["climatology_probability"].to_numpy() - outcome) ** 2))
        pooled = 1.0 - method_brier / r1_brier
        interval = verdict.skill_interval
        rows.append(
            {
                "horizon_months": horizon,
                "mean_skill_against_r1": verdict.mean_brier_skill_score,
                "skill_interval_90": None
                if interval is None
                else [interval.lower_bound, interval.upper_bound],
                "pooled_skill_against_r1": pooled,
                "pooled_and_mean_agree_in_sign": bool(
                    np.sign(pooled) == np.sign(verdict.mean_brier_skill_score)
                ),
                "resolved_rows": len(resolved),
                "gate_skill": gates.get("skill"),
                "gate_robustness": gates.get("robustness"),
                "gate_honesty": gates.get("honesty"),
            }
        )
    return rows


def main() -> None:
    path = sys.argv[1]
    label = sys.argv[2] if len(sys.argv) > 2 else path
    frame = pd.read_parquet(path)
    hashes = sorted(frame["configuration_hash"].unique())
    output = {
        "label": label,
        "configuration_hash": hashes,
        "rows": len(frame),
        "seed": SEED,
        "resamples": RESAMPLES,
        "against_r1": _against_r1(frame),
        "minus_the_chain": [
            *_minus_the_chain(frame, "model-sample"),
            *_minus_the_chain(frame, "series-start"),
        ],
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
