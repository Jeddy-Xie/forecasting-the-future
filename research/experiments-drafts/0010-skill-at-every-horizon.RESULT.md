# Measurement 0010 — RESULT

Run 2026-09-29 at commit `e7755ef`, in a detached worktree with a private copy of the cache, by
`forecast skill-by-horizon` (8 minutes 10 seconds, exit 0). The configuration is the default,
`fec79a040f9ca6f9`, 391 forecast dates from 1994-03 to 2026-09.

- **Reproduction check, passed before anything was scored.** The every-horizon walk equalled the gate
  run row for row at 12, 60 and 120 months.
- **References used.** R1 and R2 were used only after they reproduced delegated decision P1-1's
  acceptance numbers from committed code (ADR 0012).
- **Tables.** `research/reports/skill-at-every-horizon/`: `skill.csv` (480 rows: two forecasters × two
  benchmarks × 120 horizons), `model_minus_chain.csv` (240 rows), `summary.json` and the printed curve.

## The answer, read by the rule registered before the run

| forecaster | benchmark | carries skill at every horizon from 1 month to | ship-the-average horizon H\* | informative there? |
|---|---|---:|---:|---|
| regime model | series-start (0001's) | 39 months | **39 months** | yes |
| regime model | model-sample (0007's R1) | 29 months | **29 months** | yes |
| condition chain | series-start | 71 months | 120 | no: beyond 60 months |
| condition chain | model-sample | 120 months | 120 | no: beyond 60 months |

**The regime model stops carrying skill after 29 months against a fair benchmark, and after 39
against 0001's.** Beyond that, as far as this sample can say, the historical average does as well.

**The historical average is not the best thing to ship there.** The regime-free chain carries skill at
every horizon measured. Beyond 60 months that rests on fewer than 5.5 independent observations, so it
is labelled uninformative, but the sign never changes.

## How skill decays, against the model-sample benchmark

| months | regime model | condition chain | model minus chain, 90% |
|---:|---:|---:|---|
| 1 | +0.290 | +0.532 | −0.243 [−0.358, −0.181] |
| 6 | +0.236 | +0.367 | −0.130 [−0.192, −0.084] |
| 12 | +0.179 | +0.248 | −0.069 [−0.115, −0.029] |
| 24 | +0.135 | +0.144 | −0.009 [−0.062, +0.043] |
| 30 | +0.121 | +0.119 | +0.002 [−0.063, +0.063] |
| 36 | +0.109 | +0.105 | +0.004 [−0.075, +0.075] |
| 48 | +0.078 | +0.083 | −0.004 [−0.122, +0.082] |
| 60 | +0.069 | +0.088 | −0.020 [−0.173, +0.079] |
| 120 | −0.211 | +0.032 | −0.243 [−0.327, −0.072] |

- **Model minus chain lies entirely below zero at 34 horizons, 1–16 and 103–120 months, and entirely
  above zero at none.** From 17 to 102 months the two cannot be told apart.
- **At no horizon does the regime model beat the regime-free chain.**
- **Where the chain wins is persistence.** Most of its early lead is whether the condition holds now,
  which `compose_point_in_time` ignores. That is what experiment 0008's arm B1 tests.

## Prediction versus outcome

| stated in advance | p | outcome |
|---|---:|---|
| at one month the chain beats the model by a wide margin | 0.85 | **held**: +0.613 against +0.396 on the series-start benchmark, difference −0.217 [−0.265, −0.175] |
| the model carries skill against the series-start benchmark unbroken from 1 to at least 24 months | 0.70 | **held**: 39 |
| H\* is shorter against the model-sample benchmark than the series-start one | 0.75 | **held**: 29 against 39 |
| H\* against the model-sample benchmark falls between 12 and 48 months | 0.60 | **held**: 29 |
| model minus chain is negative at every horizon to 24 months | 0.60 | **held in sign**: every point estimate is negative to 24 months, and the interval excludes zero to 16 |
| the honesty measure crosses 0.05 between 100 and 130 months | 0.80 | **held**: 120 months (0.0508 at 119, 0.0499 at 120) |

## Secondary readings

- **Pooled and mean-of-ratios skill agree in sign at every horizon up to 91 months.** From 92 months on
  the mean of ratios is negative and pooled skill positive: the forking path ADR 0012 names. It sits
  entirely in the uninformative range.
- **The series-start H\* of 39 is marginal.** Its lower bound is +0.0002 at 39 months and −0.003 at 40.
  At the rule's precision the reading is 39. A reader should take it as "about three years", not as a
  month.
- **Effective independent observations are 32.4 at one month, 31.5 at twelve and 5.5 at sixty.**

## What this does not change

- 0001's verdicts are unchanged: one year SHIP MODEL, five and ten years SHIP BASE RATE.
- The shipped horizons remain one, five and ten years.
- Read against the project's own deliverable, the curve agrees with 0001: one year sits well inside the
  model's skill horizon, five years well outside it.
- What it adds is the shape between and beyond them, and that a regime-free forecaster is at least as
  good everywhere on it.
