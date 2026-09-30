# Experiment 0006 — RESULT: STRUCTURE HELPS

Run 2026-09-29 on branch `research/structure-at-matched-granularity`.
- **Code:** implementation and tests `6221813`, which is the commit the harness ran at, with a clean
  tree throughout.
- **Outputs:** `79601f0`.
- **Report:** `1bb6129`. The arm agent's write of REPORT.md was refused by the session harness, so the
  coordinator committed its text verbatim after checking it.
- **Anchor:** `baselines/main-single-chain-d14`, per the amendment of 2026-09-29. **Benchmark:**
  series-start, as registered.

## The reading

- **d6, one year:** +0.0587, 90% [+0.0216, +0.0934].
- **Both conditions for a reading held:** check-gates exited 0, and `audit-look-ahead` exited 0 at
  2000-03-01 and at 2022-03-01.
- **The interval lies entirely above zero: STRUCTURE HELPS.**

Giving growth its own chain buys a one-year gain at exactly the single chain's six cells. The sweep's
own rule chose 3 growth states by 2 inflation-and-rates states. The gain does not need sixteen cells.

| horizon | d6 | 90% |
|---|---:|---|
| 1 year | +0.0587 | [+0.0216, +0.0934] |
| 5 years | +0.0389 | [−0.0126, +0.1293] |
| 10 years | +0.2788 | [+0.1396, +0.2999] (about 2.2 independent observations) |

Registered secondaries:
- against the model-sample benchmark, one year: +0.0640 [+0.0277, +0.0976];
- against the pre-D14 `baselines/main.json`: +0.0518 [+0.0137, +0.0870].

All ten indicators improve at one year.

## Beside the adopted default

| | single chain, 6 | two chains, 3x2 | two chains, 4x4 (default) |
|---|---:|---:|---:|
| one-year skill, series-start | +0.2085 | +0.2672 | +0.2673 |
| free parameters | 89 | 27 | 58 |
| effective sample per forecast, one year | 118 months | 142 months | 46 months |
| 0001 verdict at one year | SHIP BASE RATE (calibration) | SHIP MODEL | SHIP MODEL |

- **The six-cell factorial model matches the sixteen-cell default to 0.0001 at one year.** It does so
  with half the parameters and three times the evidence behind each forecast.
- **This comparison was not registered.** It is a point estimate from committed numbers, and
  whether to prefer the smaller model is a decision, not a reading.

## Prediction versus outcome, and a correction

- **Predicted:** GRANULARITY, NOT STRUCTURE, by briefing 05's matched-cell arithmetic.
- **Outcome:** STRUCTURE HELPS.
- **The arithmetic mixed two panels.** Briefing 05 set the factorial 2x3's full-sample held-out
  likelihood (−3.1026 per month, from A4's `fit_regimes` sweep) against the single chain's burn-in
  value (−3.0801).
- **On the same burn-in panel** (518 months, 1950-12 to 1994-01), checked by the coordinator in
  `.cache/models/burn_in_state_count_choice_1994-03-01_seed20260908_{ad7fcc1affd0746a,fec79a040f9ca6f9}.json`:
  2x3 scores −2.6867 and 3x2 −2.6708, against −3.0801. The factorial structure is **better by 0.39
  to 0.41 nats per month**, not worse by 0.0225.
- **Where the correction is recorded.** Briefing 05 and ADR 0010 both carried the wrong comparison.
  Each gets a dated correction appended; the original text is left standing.

## Deviations the owner should see

- **Test fixtures edited on the arm's branch.** Six settings constructions in four existing test files
  were changed to name the arm's switch at False, with no assertion changed. A4 and A5 did the same.
  The branch is not merged. If the change is ever adopted, these edits come with it and need review.
- **No judged look-ahead review.** 0006's rule names only the deterministic audit, and none was run.
