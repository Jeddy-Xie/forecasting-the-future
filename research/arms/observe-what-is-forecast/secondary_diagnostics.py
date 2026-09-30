"""Secondary measurements for experiment 0008 arm B2, read off the scored run's own artifacts.

None of these is the registered endpoint, which is `paired.json`. They are:

1. Benchmark decomposition. Rule 0007's R1 averages outcomes from the first month of the
   observation matrix built at each forecast date. The arm's matrix starts in 1956-03 (the
   spread's ten-year leg begins in 1953-04), the reference's in 1950-12, so the two runs'
   primary skill scores are measured against different R1 columns. Here the arm's forecasts
   are re-scored against the REFERENCE's R1, so the paired difference isolates the change in
   the forecasts from the change in the benchmark.
2. Arm minus R2 at one year (0007's regimes_help), both scored against the arm's own R1, and
   the reference minus its own R2 for comparison.
3. Pooled Brier skill against R1 beside the mean of ratios, per horizon (0007's
   NOT ESTABLISHED clause), for both runs.

Every paired number uses the same machinery, seed, resample count and levels as the harness.
Run from the arm's worktree with PYTHONPATH=<worktree>/src.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

import economic_regime_forecasting
from economic_regime_forecasting import command_line_interface as cli
from economic_regime_forecasting import regression_baseline as rb

LEVELS = [0.90, 0.9667]
REFERENCE = "reference-0008"
KEY = ["indicator", "forecast_date", "horizon_months"]


def paired(baseline_doc, baseline_frame, current_doc, current_frame, benchmark, settings):
    return rb.compare_paired(
        baseline_doc,
        baseline_frame,
        current_doc,
        current_frame,
        random_seed=settings.random_seed,
        resamples=settings.bootstrap_resamples,
        confidence_levels=LEVELS,
        name="diagnostic",
        benchmark=benchmark,
    )


def horizon_rows(comparison) -> list[dict]:
    rows = []
    for item in comparison.as_dictionary()["horizons"]:
        rows.append(item)
    return rows


def pooled_skill(frame: pd.DataFrame, horizon: int, benchmark_column: str) -> float:
    at = frame[(frame["horizon_months"] == horizon)].dropna(
        subset=["realised_outcome", benchmark_column]
    )
    method = ((at["predicted_probability"] - at["realised_outcome"]) ** 2).sum()
    reference = ((at[benchmark_column] - at["realised_outcome"]) ** 2).sum()
    return float(1.0 - method / reference)


def main() -> int:
    print(f"code imported from {economic_regime_forecasting.__file__}")
    workspace = cli.Workspace.open()
    settings = workspace.settings
    arm_doc = rb.assemble_run_summary(workspace.artifacts)
    arm_frame = rb.forecast_frame(workspace.artifacts)
    reference_doc = rb.read_baseline(REFERENCE)
    reference_frame = rb.read_baseline_forecasts(REFERENCE)
    assert arm_doc["run"]["configuration_hash"] == settings.configuration_hash()
    print(f"arm configuration {settings.configuration_hash()}, reference {REFERENCE}")
    out: dict = {}

    # 1. The arm's forecasts against the reference's R1.
    column = "model_sample_climatology_probability"
    merged = arm_frame.merge(
        reference_frame[KEY + [column]].rename(columns={column: "reference_r1"}),
        on=KEY,
        how="left",
    )
    differs = merged[column].ne(merged["reference_r1"]) & merged["reference_r1"].notna()
    print(
        f"\n1. R1 differs between the runs on {int(differs.sum())} of {len(merged)} rows; "
        f"mean absolute difference {float((merged[column] - merged['reference_r1']).abs().mean()):.4f}"
    )
    rescored = merged.drop(columns=[column]).rename(columns={"reference_r1": column})[
        arm_frame.columns
    ]
    comparison = paired(reference_doc, reference_frame, arm_doc, rescored, "model-sample", settings)
    print("   arm (against the reference's R1) minus reference (against its own R1):")
    out["arm_against_reference_r1_minus_reference"] = comparison.as_dictionary()
    print(comparison.describe())

    # 2. Arm minus R2, and reference minus R2, at every horizon.
    for label, doc, frame in (
        ("arm", arm_doc, arm_frame),
        ("reference", reference_doc, reference_frame),
    ):
        chain = frame.copy()
        chain["predicted_probability"] = chain["condition_chain_probability"]
        comparison = paired(doc, chain, doc, frame, "model-sample", settings)
        out[f"{label}_minus_r2"] = comparison.as_dictionary()
        print(f"\n2. {label} minus its own R2 (condition_chain_probability), model-sample benchmark:")
        print(comparison.describe())

    # 3. Pooled skill beside the mean of ratios.
    print("\n3. pooled Brier skill against R1 (model-sample), per horizon")
    pooled = {}
    for label, frame in (("arm", arm_frame), ("reference", reference_frame)):
        pooled[label] = {
            int(h): pooled_skill(frame, int(h), column)
            for h in sorted(frame["horizon_months"].unique())
        }
        print(f"   {label}: " + ", ".join(f"{h} months {v:+.4f}" for h, v in pooled[label].items()))
    out["pooled_skill_model_sample"] = pooled
    json.dump(out, open(sys.argv[1], "w"), indent=2, sort_keys=True, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
