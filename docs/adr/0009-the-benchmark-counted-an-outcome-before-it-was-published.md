# 0009. The benchmark counted an outcome before it was published

Date: 2026-09-15 · Status: accepted

## Context and problem

Every skill score in this project is measured against an expanding climatology.
The climatology is meant to be the base rate a forecaster could have quoted on the
day. Its docstring said so ("what a forecaster in month t could actually have
quoted"), and the look-ahead audit table in `docs/TECHNICAL_DEBT.md` marked it
**clean**. It was not.

### Found by execution, not by reading

`forecast audit-look-ahead` (fb926ff) perturbs everything unavailable at a cutoff
date and requires every forecast issued on or before it to come out byte-identical.
Its first run on main, at the default cutoff 2000-03-01 (73 forecast dates, 7
refits, 348 s), exited 1:

    LOOK-AHEAD: 12 of 2190 forecasts issued on or before 2000-03-01 changed when only
    information unavailable at 2000-03-01 was perturbed, on 1 forecast date(s) from
    2000-03-01 to 2000-03-01. The earliest is where the leak enters.

    forecast date  indicator                                                   horizon  field                    original             perturbed
    2000-03-01     consumer_price_inflation_above_five_percent_within_horizon  12       climatology_probability  0.375                0.37662337662337664
    ... eleven more, every one climatology_probability on 2000-03-01

No probability, regime distribution, state count or refit date moved. Only the
benchmark did.

### The mechanism

The outcome of a forecast made in month s at horizon h rests on the observation
labelled s + h. For the at-horizon rule, `data/indicator_outcomes.py::_value_at_horizon`
is `series.shift(-h)`. For the within-horizon rules, `_forward_extreme` reads months
s + 1 through s + h. `backtest/walk_forward.py::_expanding_climatology` shifted the
running mean by exactly h months. So the benchmark at t averaged outcomes up to
s = t − h, and the last of those rests on the value labelled t.

That value had not been published at t. It appears `publication_lag_days` after
its label: 32 to 47 days for the market and statistical series, and 400 days for
recession dating. So at every forecast date the benchmark knew at least one outcome
nobody could yet have resolved. For the two recession indicators it knew about
thirteen.

The conditions the per-regime rates are learned from already waited for
publication (`condition_available_at`). The benchmark was held to a weaker rule
than the model it judges.

### Why reading did not find it

The code looked like it enforced the rule: an expanding mean, shifted by the
horizon. The unit test
`tests/test_walk_forward_backtest.py::test_the_climatology_at_a_date_uses_only_outcomes_resolved_by_then`
pinned the shift as the specification. A reviewer checking code against its test
sees two things that agree. The audit does not read either one.

## Decision

An outcome enters the climatology at forecast date t only once the last
observation it rests on was published: label s + h months, plus the indicator's
`publication_lag_days`, on or before t.

- **The lag** is the one `prepare_indicator_history` already computes. For the
  derived term spread that is the larger of its two legs' lags.
- **The rule** is `walk_forward.publication_dates`, now shared with
  `condition_available_at`. One publication rule, used for both things the
  forecaster reads off final data, rather than two rules that can drift.
- **The implementation** is one binary search of the forecast dates against the
  outcomes' publication dates. Publication dates ascend with s, so the outcomes
  counted at any t are always a prefix, and the expanding mean at the end of that
  prefix is the answer.

## The test that changed

This is the change for the owner to review.

`tests/test_walk_forward_backtest.py::test_the_climatology_at_a_date_uses_only_outcomes_resolved_by_then`,
with a horizon of three months.

**Before**, with no lag:
- month one's outcome is in the benchmark in month four (`climatology.iloc[3] == 1.0`);
- months one to three are in it by month six (`iloc[5] == 2/3`).

Month four is the month whose value decides month one's outcome. The assertion
said that value is known on the first day of the month it describes, weeks before
it is published. It encoded the look-ahead as the specification.

**After**, with a 36-day lag:
- nothing has resolved through month five (month one's deciding value appears on
  2000-05-07);
- month six is 1.0;
- month eight is 2/3.

This strengthens the requirement rather than weakening it. The test's own name
says "resolved by then". `CLAUDE.md` says rates at t "use only outcomes that had
already resolved by t". The old assertion satisfied neither.

It was changed with the Edit tool, not rewritten, and it keeps its name. Beside it
are new boundary tests:
- an outcome published exactly on the forecast date is counted (a 31-day lag from
  2000-03-01 lands on 2000-04-01);
- one published a day later is not (32 days);
- a 400-day recession outcome is excluded through 2001-04-01 and counted from
  2001-05-01, where the old shift counted it from 2000-03-01;
- the last outcome the benchmark counts at a date rests on exactly the last
  condition the forecaster may read then.

## What it moved

The regression harness measured the fix against the pre-fix baseline, which is
its first real job.
- The configuration hash is unchanged (`ad7fcc1affd0746a`): the fix is code, not
  a setting.
- `forecast check-gates` passed all five gates in 113 s.
- All 181 cached fit and burn-in choice files were byte-identical afterwards, so
  every fit was a cache hit and only the benchmark column could move.

**Plain comparison** (`forecast baseline compare --against main`, exit 1):
`318 IDENTICAL 0 NUMERICAL 69 MOVED 0 REMOVED 0 ADDED`. None of the moves is
categorical: no verdict and no failing gate changed. The largest single field move
is `economy_in_recession_within_horizon @ 12` `brier_skill_score`, +0.0057.

**Paired comparison** (`--paired --confidence-level 0.90 --confidence-level
0.9833`, exit 0). Both runs resolved the same 9702 forecasts:

    horizon     in both  baseline skill  this run skill  difference  90% interval        98.33% interval     independent obs
    12 months   3754     +0.2128         +0.2154         +0.0026     [+0.0021, +0.0028]  [+0.0019, +0.0030]  31.5
    60 months   3274     +0.0722         +0.0728         +0.0006     [-0.0011, +0.0009]  [-0.0033, +0.0011]  5.5
    120 months  2674     -0.3524         -0.3528         -0.0004     [-0.0014, -0.0001]  [-0.0028, +0.0000]  2.2

**Direction.** The leaky benchmark knew one more outcome than it should, so it was
a slightly better forecaster. The model's one-year skill against it was
*understated*, by 0.0026 with an interval entirely above zero. The leak flattered
the benchmark, not the model. At five years the difference is indistinguishable
from zero. At ten it is −0.0004, and its 98.33% interval touches zero.

**Verdicts, unchanged.**
- One year: SHIP BASE RATE, failing calibration only.
- Five years: SHIP BASE RATE, failing skill, calibration and robustness.
- Ten years: SHIP BASE RATE, failing skill, calibration, robustness and honesty.

`baselines/main.json` and `baselines/main.forecasts.parquet` are re-captured in
this commit, as `docs/REGRESSION_TESTING.md` requires of a change meant to move
main's numbers.

The audit on main now exits 0, in 333 s: "no forecast issued on or before
2000-03-01 changed when every observation unavailable at 2000-03-01 was
perturbed".

## The shipped configuration was computed against the leaky benchmark

The headline tables in `docs/RESULTS.md` and the submission come from the shipped
configuration `9f95b12dba40d138`. Its skill scores, and the `climatological_base_rate`
column of `submission/forecasts.csv`, were computed against the leaky benchmark. I
recomputed both read-only from `backtest_results_shipped.parquet`, the shipped
cell of `forecast compare-variants`:

- **The submission's base-rate column** is reproduced from that run exactly, 30 of
  30 values. Under the honest benchmark the values change by at most 0.0061
  (`economy_in_recession_within_horizon` at five years, 0.8691 → 0.8752). Most
  change by 0.001 to 0.002, and six do not change. The five- and ten-year rows ship
  the base rate, so those shipped probabilities are affected by at most that much.
  The one-year rows ship the model's probability, which the benchmark does not
  touch.
- **The shipped verdicts do not change.** One year stays SHIP MODEL, mean skill
  +0.2320 → +0.2353, every gate passing. Five years stays SHIP BASE RATE, +0.1021 →
  +0.1043, failing skill and calibration. Ten years stays SHIP BASE RATE, −0.2205 →
  −0.2193, failing skill and robustness.
- Of the 19,701 shipped rows with a benchmark, 19,292 change. The largest change
  is 0.0179, at 1972-02, early in the sample, when the benchmark averaged few
  outcomes.

**The submission is not regenerated.** `forecast submit` refuses to overwrite it
without a named, single-use authorisation (ADR 0008's shipping guard), and whether
to re-ship is the owner's decision, not this change's. `docs/RESULTS.md` carries a
dated correction note pointing here, and its tables are left as published.

## Consequences

- One publication rule now governs everything read off final data: the
  conditions, and the outcomes the benchmark averages. The one approximation that
  remains is D5, the revised *values* of those series, which is unchanged.
- The look-ahead audit table's benchmark row is now clean, with this record as its
  evidence. The table also gains a row for the invariance audit itself, the check
  that found this.
- The audit caught this leak because the leak touched a value labelled exactly on
  the cutoff date. The audit's perturbation keys on labels, so a similar leak
  reading a value one month earlier, still inside its publication lag, would have
  passed. Tightening the perturbation to publication dates is the next change.

## Options considered

- **Shift by h + 1 months.** Rejected. Publication lags run from 32 to 400 days, so
  any fixed shift is right for some indicators and wrong for recession dating by a
  year.
- **Shift by h plus the lag rounded up to whole months.** Rejected. It gives the
  same months as the chosen rule but writes the publication rule a second time, in
  another unit. The point of the fix is that there is one.
- **Leave the benchmark and disclose.** Rejected. The pre-registered slate voids
  every arm until main passes the audit. A known look-ahead in the reference run
  also cannot be disclosed into correctness.
