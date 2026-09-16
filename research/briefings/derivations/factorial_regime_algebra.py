"""Derived numbers for briefing 04 (factorial regime models). Deterministic; seed 20260916.

Every E2 number in research/briefings/04-factorial-regime-models.md is produced here.

1. The Kronecker persistence identity: lambda2(kron(A,B)) == max(lambda2(A), lambda2(B)),
   checked against the A4 arm's own burn-in sweep AND against random stochastic matrices.
2. Half-lives implied by the measured second eigenvalues.
3. Free-parameter counts, against the repo's own convention, validated on the sweep table.
4. Per-indicator paired differences, split any-time vs at-horizon, from the arm's compare.json.
5. The ten-year paired difference for the A6 climatology blend.
6. The spread of the one-year paired difference across the three seed variants of arm A4 --
   the check that says whether A4's headline effect is larger than its own seed noise.

Inputs are the arm output directories written by scripts/research_arm.sh; nothing is fetched.
"""

from __future__ import annotations

import json
import math
import statistics as st
from pathlib import Path

import numpy as np

ARMS = Path("/Users/jpmorgan/Projects/forecasting-the-future-arms")
A4 = ARMS / "two-timescale-chains/research/arms/two-timescale-chains"
A6 = ARMS / "fixed-climatology-blend/research/arms/fixed-climatology-blend"

# The A4 burn-in sweep, transcribed from check_gates.log's own fit_regimes tables.
GROWTH_LAMBDA2 = {1: 0.0, 2: 0.913282, 3: 0.939538, 4: 0.946242}
LEVELS_LAMBDA2 = {1: 0.0, 2: 0.974101, 3: 0.982003, 4: 0.983885}
JOINT_LAMBDA2 = {
    (1, 1): 0.0, (1, 2): 0.974101, (1, 3): 0.982003, (1, 4): 0.983885,
    (2, 1): 0.913282, (2, 2): 0.974101, (2, 3): 0.982003, (2, 4): 0.983885,
    (3, 1): 0.939538, (3, 2): 0.974101, (3, 3): 0.982003, (3, 4): 0.983885,
    (4, 1): 0.946242, (4, 2): 0.974101, (4, 3): 0.982003, (4, 4): 0.983885,
}
# The sweep's own free_parameters column, used to validate the counting convention.
REPORTED_FREE_PARAMETERS = {("growth", 4): 23, ("levels", 4): 35, ("joint", 16): 58, ("main", 6): 89}


def free_parameters(states: int, dimensions: int) -> int:
    """The repo's convention: transitions + means + covariances + initial distribution."""
    return (
        states * (states - 1)
        + states * dimensions
        + states * dimensions * (dimensions + 1) // 2
        + (states - 1)
    )


def second_eigenvalue_modulus(matrix: np.ndarray) -> float:
    return float(np.sort(np.abs(np.linalg.eigvals(matrix)))[::-1][1])


def half_life(lambda2: float) -> float:
    return math.log(0.5) / math.log(lambda2)


def section(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def one_year_difference(paired_json: Path) -> float:
    horizons = json.loads(paired_json.read_text())["horizons"]
    twelve = next(h for h in horizons if h["horizon_months"] == 12)
    return float(twelve["difference"])


def horizon_difference(paired_json: Path, months: int) -> tuple[float, list[float]]:
    horizons = json.loads(paired_json.read_text())["horizons"]
    chosen = next(h for h in horizons if h["horizon_months"] == months)
    ninety = next(i for i in chosen["intervals"] if i["confidence_level"] == 0.9)
    return float(chosen["difference"]), [ninety["lower_bound"], ninety["upper_bound"]]


def main() -> None:
    section("1. Kronecker persistence identity, on the arm's own burn-in sweep")
    mismatches = [
        (g, l)
        for (g, l), joint in JOINT_LAMBDA2.items()
        if abs(max(GROWTH_LAMBDA2[g], LEVELS_LAMBDA2[l]) - joint) > 1e-9
    ]
    print(f"  cells checked: {len(JOINT_LAMBDA2)}   mismatches: {mismatches}")
    dominated_by_levels = sum(
        1 for (g, l) in JOINT_LAMBDA2 if LEVELS_LAMBDA2[l] >= GROWTH_LAMBDA2[g]
    )
    print(f"  the levels (slow) chain sets the joint rate in {dominated_by_levels} of 16 cells")

    print("\n  and on random row-stochastic matrices (the identity is algebraic, not empirical):")
    generator = np.random.default_rng(20260916)

    def stochastic(size: int, persistence: float) -> np.ndarray:
        matrix = generator.random((size, size)) + 0.05
        matrix[np.arange(size), np.arange(size)] += persistence
        return matrix / matrix.sum(axis=1, keepdims=True)

    worst = 0.0
    for rows, columns, fast, slow in [(4, 4, 6, 40), (4, 4, 40, 6), (3, 5, 10, 10), (2, 6, 3, 30)]:
        a, b = stochastic(rows, fast), stochastic(columns, slow)
        joint = second_eigenvalue_modulus(np.kron(a, b))
        expected = max(second_eigenvalue_modulus(a), second_eigenvalue_modulus(b))
        worst = max(worst, abs(joint - expected))
        print(
            f"    {rows}x{columns}: lambda2(kron)={joint:.6f}  max(lambda2)={expected:.6f}"
        )
    print(f"    worst absolute discrepancy: {worst:.2e}")
    a, b = stochastic(4, 6), stochastic(4, 40)
    spectrum = np.sort(np.abs(np.linalg.eigvals(np.kron(a, b))))
    products = np.sort(np.abs(np.outer(np.linalg.eigvals(a), np.linalg.eigvals(b))).ravel())
    print(f"    spectrum of kron == outer product of spectra: {np.allclose(spectrum, products)}")

    section("2. Half-lives implied by the measured second eigenvalues")
    for name, value in [
        ("growth chain, median of 34 refits", 0.9464),
        ("levels chain / joint, median", 0.9821),
        ("main six-state chain, median", 0.9777),
        ("arm, today's fit", 0.9802),
        ("main, today's fit", 0.9831),
    ]:
        print(f"  {name:38s} lambda2={value:.4f}  half-life={half_life(value):5.1f} months")

    section("3. Free parameters: the factorial restriction against an unrestricted chain")
    derived = {
        ("growth", 4): free_parameters(4, 1),
        ("levels", 4): free_parameters(4, 2),
        ("joint", 16): free_parameters(4, 1) + free_parameters(4, 2),
        ("main", 6): free_parameters(6, 3),
    }
    for key, value in derived.items():
        reported = REPORTED_FREE_PARAMETERS[key]
        print(f"  {key[0]:7s} K={key[1]:2d}  derived={value:3d}  reported={reported:3d}  "
              f"match={value == reported}")
    unrestricted = free_parameters(16, 3)
    print(f"\n  unrestricted single chain, K=16, d=3: {unrestricted}")
    print(f"  factorial restriction: {unrestricted} -> {derived[('joint', 16)]} "
          f"({unrestricted / derived[('joint', 16)]:.1f}x fewer)")
    print(f"  arm carries 16 states on {derived[('main', 6)] - derived[('joint', 16)]} FEWER "
          f"parameters than main carries 6")
    print("\n  transition block only -- Sims, Waggoner & Zha's own formula:")
    counts = [4, 4]
    joint_states = counts[0] * counts[1]
    print(f"    unrestricted  prod(h)*(prod(h)-1) = {joint_states}*{joint_states - 1} "
          f"= {joint_states * (joint_states - 1)}")
    print(f"    tensor-product sum(h_k*(h_k-1))   = {sum(h * (h - 1) for h in counts)}")
    print(f"    reduction: {joint_states * (joint_states - 1) / sum(h * (h - 1) for h in counts):.0f}x")

    section("4. Per-indicator paired differences, any-time vs at-horizon (A4 compare.json)")
    fields = [r for r in json.loads((A4 / "compare.json").read_text())["fields"]
              if r["section"] == "indicators"]
    for field, improves in (("brier_skill_score", "up"), ("logarithmic_loss", "down"),
                            ("expected_calibration_error", "down"),
                            ("mean_effective_sample_size", "info")):
        rows = [r for r in fields if r["field"] == field]
        print(f"\n  {field} ({len(rows)} indicator-horizon rows)")
        for months in (12, 60, 120):
            selected = [r for r in rows if str(r["row"]).strip().endswith(f"@ {months}")]
            anytime = [r for r in selected if "within_horizon" in r["row"]]
            at_horizon = [r for r in selected if "at_horizon" in r["row"]]
            line = f"    h={months:3d}"
            for label, group in (("any-time", anytime), ("at-horizon", at_horizon)):
                if group:
                    mean = st.mean(r["difference"] for r in group)
                    line += f" | {label} n={len(group)} mean={mean:+.4f}"
            print(line)
        values = [r["difference"] for r in rows]
        if improves == "up":
            print(f"    improved on {sum(1 for v in values if v > 0)}/{len(values)}")
        elif improves == "down":
            print(f"    improved on {sum(1 for v in values if v < 0)}/{len(values)}")
        else:
            print(f"    mean {st.mean(r['baseline'] for r in rows):.1f} -> "
                  f"{st.mean(r['current'] for r in rows):.1f}")

    section("5. A6 fixed-climatology-blend, for the 'what it converges to' argument")
    for months in (12, 120):
        difference, interval = horizon_difference(A6 / "paired.json", months)
        print(f"  h={months:3d}  difference={difference:+.4f}  "
              f"90% [{interval[0]:+.4f}, {interval[1]:+.4f}]")

    section("6. Seed spread of arm A4's one-year effect -- is the headline bigger than seed noise?")
    runs = {
        "two-timescale-chains (reported)": A4 / "paired.json",
        "a4-seed-20260909": ARMS / "a4-seed-20260909/research/arms/a4-seed-20260909/paired.json",
        "a4-seed-20260910": ARMS / "a4-seed-20260910/research/arms/a4-seed-20260910/paired.json",
    }
    observed = {}
    for name, path in runs.items():
        if not path.exists():
            print(f"  {name:34s} MISSING: {path}")
            continue
        observed[name] = one_year_difference(path)
        print(f"  {name:34s} one-year paired difference = {observed[name]:+.6f}")
    if len(observed) > 1:
        values = list(observed.values())
        spread = max(values) - min(values)
        print(f"\n  spread across {len(values)} seeds: {spread:.6f}")
        if len(values) > 2:
            print(f"  standard deviation across seeds: {st.stdev(values):.6f}")
        reported = observed.get("two-timescale-chains (reported)")
        if reported:
            print(f"  seed spread as a fraction of the reported effect: {spread / reported:.2f}")
            print("  (the reported 90% interval half-width is 0.0301; compare the spread to it)")


if __name__ == "__main__":
    main()
