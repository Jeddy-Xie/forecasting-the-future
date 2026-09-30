# Measurement 0010 — skill at every horizon from one month to ten years

Registered 2026-09-29, BEFORE the curve is computed. This file's git timestamp is the evidence.
Approved as a registered measurement by delegated decision P1-10(4)
(`research/ledger/delegated-decisions/2026-09-29-pass-1.json`). The number 0009 is reserved for the
unadjusted-CPI sample extension that P1-3 schedules after experiment 0008 reports.

## Why

The owner asked for the accuracy one month at a time, and for the point at which the project should
just ship the historical average. The frozen rule 0001 scores three horizons, 12, 60 and 120 months, and
says the model is worth shipping at one year and not at five. It does not say where between them the
model stops, or how fast skill decays. This measures every month.

It is descriptive. **It changes no 0001 verdict and no shipped probability.** The deliverable's
horizons stay one, five and ten years, each governed by its own rule.

## What is computed

- **Forecasts.** The default configuration, `fec79a040f9ca6f9` on the code of the commit that runs it,
  re-walked from the cached fits with `run_walk_forward(..., horizons_in_months=1..120)`. Every question
  is asked at every horizon h: "within h months" for the any-time indicators, "in month h" for the
  point-in-time ones. At 12, 60 and 120 months the rows must equal the gate run's rows exactly. That is
  checked before anything is read.
- **Forecasters, each scored at every h:**
  - the regime model (`predicted_probability`);
  - the regime-free condition chain R2 (`condition_chain_probability`, rule 0007).
- **Benchmarks, each forecaster against each:**
  - the series-start climatology, 0001's (`climatology_probability`);
  - the model-sample climatology R1, rule 0007's (`model_sample_climatology_probability`).
  - R1 and R2 are used only once they reproduce delegated decision P1-1's two acceptance numbers from
    committed code. Until then the curve reports the series-start benchmark and the model alone.
- **Statistic.** The verdict's own mean Brier skill score over the indicators whose skill is defined on
  the full sample at that horizon. Pooled Brier skill is reported beside it.
- **Interval.** Moving-block bootstrap over forecast dates, 10,000 resamples, seed 20260908, 90%.
- **Block length.** max(h, 12) months. The pre-registration asks for at least the horizon. The floor
  of twelve is added because forecasts a month apart are not independent at short horizons either:
  regimes and conditions are persistent, and the review measured the loss differential decorrelating
  only within about a year.
- **Paired difference.** Model minus chain at every h, on identical resamples, same blocks.
- **Honesty measure.** The mean total variation distance from the projected regime distribution to the
  stationary one, at every h.

## How it will be read, fixed now

- The model **carries skill at h** when its mean skill exceeds +0.02 and the 90% lower bound exceeds
  zero. That is 0001's skill-gate test, applied at h.
- The **ship-the-average horizon H\*** is the first horizon after which the model fails that test at
  every longer horizon: the last horizon at which it carries skill, or 0 if none.
- Beside it, and secondary: the longest horizon up to which skill holds unbroken from one month.
- **Effective independent observations** at h are the resolved forecast dates divided by the block
  length.
  - A horizon where that falls below 5.5 (five years' worth) is labelled **uninformative**.
  - No crossing is read there. If H\* falls in that region, the reading is "no measurable end inside
    the informative range", not a number.
- H\* is reported separately for each benchmark. The model-sample one is the reading rule 0007 would
  use; the series-start one is 0001's lens.
- The honesty measure's crossing of 0.05 is reported as a second, model-internal horizon, and is not
  read as skill.

## Stated in advance

- **At one month the chain beats the model by a wide margin (p = 0.85).** Every point-in-time question
  is dominated by whether the condition holds now. The model's point-in-time composition ignores that
  (`compose_point_in_time` reads only the regime distribution), and the chain reads it directly.
- **The model carries skill against the series-start benchmark unbroken from one month to at least 24
  months (p = 0.7).**
- **Against the model-sample benchmark, H\* is shorter than against the series-start one (p = 0.75).**
  Recession skill turns negative there.
- **H\* against the model-sample benchmark falls between 12 and 48 months (p = 0.6).**
- **Model minus chain is negative at every horizon up to 24 months (p = 0.6).** Its sign at longer
  horizons is not predicted.
- **The honesty measure crosses 0.05 between 100 and 130 months (p = 0.8).** The half-life is about 41
  months and 0.0499 was measured at 120.

## What it cannot say

- Every horizon beyond about 60 months rests on fewer than 5.5 independent observations. The curve is
  there for completeness, and nothing is read from it.
- Neighbouring horizons share almost all their forecasts. A wiggle in the curve is not a finding.
- One sample, 1994-03 to 2026-09, already used for every choice this project has made. The curve inherits
  the in-sample ceiling ADR 0010 states.
