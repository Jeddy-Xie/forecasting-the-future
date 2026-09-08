# 0006. The calibration check's standard error was corrected after the first run

Date: 2026-09-08 · Status: accepted

**This record exists because the correction changed a verdict.** It is written at
length so a reader can decide for themselves whether it was legitimate.

## What happened
The pre-registered calibration gate requires "expected calibration error below
0.10 and a reliability curve with no reversal larger than sampling noise", with a
tolerance of two standard errors. The first evaluation run reported, at the
one-year horizon:

- expected calibration error **0.0612**, comfortably inside the 0.10 bar;
- a reliability curve rising monotonically across eight of nine steps, with one
  dip of 0.082 in the 0.8 to 0.9 bin;
- that dip counted as a reversal, so the gate failed and the horizon shipped the
  base rate despite a skill score of +0.232 whose interval excluded zero and
  which was positive in all four sub-periods.

The implementation computed each bin's standard error as binomial on the bin's
raw count. The 0.8 to 0.9 bin held 393 forecasts, so the standard error came out
at 0.0245 and the combined two-sigma allowance at 0.062, just under the dip.

## Why that computation is wrong
Those 393 forecasts are monthly forecasts at a twelve-month horizon. Consecutive
ones share eleven of their twelve months. The bin is worth roughly 33 independent
observations, not 393, so the correct standard error is about three and a half
times larger and the allowance about 0.21 — comfortably wider than the dip.

This is the same dependence the pre-registration mandates a moving-block bootstrap
for on the skill side, with blocks "at least the horizon in months". It applies to
the reliability curve for exactly the same reason. Applying it to one and not the
other was an oversight, not a design.

## Decision
`assess_calibration` takes a `dependence_block_length` and divides each bin's
count by it before taking the standard error. The verdict passes the horizon in
months, matching the bootstrap's block length. A block length of one recovers the
old computation, and both the corrected and the uncorrected violation counts are
carried on every report, so the difference is printed rather than buried:

> the reliability curve is monotone (counting overlapping forecasts as
> independent would have found 1)

**No threshold moved.** The bar is still two standard errors and 0.10; only the
estimate of a standard error changed, and it changed to the value the same
document already requires elsewhere.

## What it changed
| horizon | before | after |
|---|---|---|
| 1 year | SHIP BASE RATE, failed calibration | **SHIP MODEL**, all five gates pass |
| 5 years | SHIP BASE RATE, failed skill and calibration | SHIP BASE RATE, failed skill and calibration |
| 10 years | SHIP BASE RATE, failed skill, calibration, robustness | SHIP BASE RATE, failed skill and robustness |

The five-year and ten-year verdicts are unchanged: both fail the skill gate on
their own, and no calibration argument reaches them.

## Consequences
- Good: the calibration gate now tests what it claims to, and the whole project
  treats dependence consistently.
- Good: the correction is visible in the printed output of every run, not only in
  this record.
- **Bad / accepted cost, and the honest one:** the change was made after seeing a
  result, and it turned a failure into a pass. That is the shape of a moved
  goalpost even when it is not one. Three things distinguish it, and a sceptical
  reader is entitled to weigh them: the fix follows from a rule already written in
  the pre-registration; a test pins that a genuinely reversed forecaster still
  fails at any block length, so the check was not disarmed; and the same fix was
  applied at ten years, where it also removed a calibration failure and changed
  nothing, because that horizon fails on skill regardless.
- Bad / accepted cost: the wider band has less power at long horizons. At ten
  years a bin is worth about four independent observations and the monotonicity
  check can detect almost nothing. That is an honest statement of what the data
  support, not a weakness introduced by the fix.

## Options considered
- Leave the bug in and report one-year as a base-rate ship — rejected: shipping a
  worse forecast on the strength of a standard error known to be wrong is not
  rigour, it is a different kind of error, and it would have been undisclosed.
- Loosen the two-standard-error tolerance instead — rejected: that *is* moving a
  threshold, and it would have been arbitrary rather than derived.
- Drop the monotonicity requirement — rejected: it tests something the calibration
  error does not, namely whether the model orders situations correctly at all.
