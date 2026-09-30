# 0012 · The benchmark was weak by accident, and a regime-free chain wins at one year

**Status** accepted, 2026-09-29, by **delegated decision**: Jeddy Xie delegated this session's decisions
to claude-fable-5-1 ("for decisions use fable and make the decisions for me"). Every decision below is
that model's, recorded verbatim with its reasons in
`research/ledger/delegated-decisions/2026-09-29-pass-1.json`. None is the owner's own adjudication, none
promotes anything to E3, and the owner can reverse any of them.

## Context

A review of main on 2026-09-25 ("Regimes Versus Baselines", an artifact page) found no look-ahead. It did
find that two of the reference points every skill number here rests on are weaker than they look. Its
scripts lived in a temporary scratchpad and are gone; nothing it computed was committed. So before any
of it could be built on, the two forecasters it used as references were reimplemented in `src/` and
required to reproduce its numbers.

## What was found, reproduced from committed code

**The benchmark reaches back to 1854.**
- The climatology is an expanding mean over every resolved outcome since the *source series* begins:
  USREC from December 1854, INDPRO from 1919.
- The model learns its rates only from its observation matrix's first month, 1950-12.
- Restricted to outcomes inside the model's own sample (R1 below), the default's mean skill falls:

| horizon | against the series-start climatology | against R1 |
|---|---:|---:|
| 1 year | +0.2673 | **+0.1786** |
| 5 years | +0.1194 | +0.0690 |
| 10 years | −0.1624 | −0.2109 |

This is not a look-ahead. It makes the benchmark weaker, not the model better, and nobody chose it: each
start date is where the archive begins. Its effect on a skill score is still that of a strawman.

**A forecaster without regimes wins at one year.**
- R2 is a two-state Markov chain on each indicator's own monthly condition. It has two rates and
  nothing else.
- Default minus R2 at one year: **−0.0582, 90% [−0.0961, −0.0261], 98.33% [−0.1119, −0.0089]**.
- That is the same family-wise confidence the two-chain model needed to be adopted.

**Where the regimes earn their keep, and where they cannot.** One year, skill against R1:

| question | the model sees it? | model | chain | area under the curve, model | chain |
|---|---|---:|---:|---:|---:|
| inflation above 5%, any time | input | **+0.501** | +0.406 | 0.87 | 0.48 |
| inflation above 3%, at the horizon | input | **+0.142** | +0.046 | 0.47 | 0.50 |
| funds rate below 1%, any time | through the bill rate | **+0.675** | +0.610 | 0.88 | 0.84 |
| funds rate above 4%, at the horizon | through the bill rate | +0.324 | **+0.447** | 0.73 | 0.77 |
| yield curve inverted, any time | one leg | +0.179 | **+0.195** | 0.66 | 0.49 |
| output growth above 2%, at the horizon | input | −0.046 | **+0.032** | 0.52 | 0.62 |
| unemployment above 7%, any time | no | +0.437 | **+0.500** | 0.81 | 0.67 |
| unemployment above 5%, at the horizon | no | −0.110 | **+0.242** | 0.48 | 0.65 |
| recession, any time | no | −0.283 | **+0.007** | 0.57 | 0.34 |
| recession, in the horizon month | no | −0.033 | **−0.008** | 0.29 | 0.33 |

The model wins where its inputs are the question. It loses where the question is about something it
never observes, and where the answer is mostly whether the condition holds now:
`compose_point_in_time` reads only the regime distribution. The delegated reading, accepted: **"the model
forecasts recessions" does not hold** against a fair benchmark.

The two recession rows turn from +0.375 and +0.199 against the old benchmark to below zero. The chain's
per-indicator figures differ from the review's page by up to 0.009 on two rows, while its mean agrees
within 0.001. The numbers here are the committed code's.

## Decision

1. **Two reference forecasters ride beside every forecast**, as columns of the backtest frame and of
   every baseline captured from now on. They are never settings, so no configuration hash moves and no
   cached fit is invalidated. Adding them moved nothing: `baseline compare` against
   `head-2026-09-29` reads 387 of 387 fields identical, and the paired difference is exactly zero on
   [0, 0] at every horizon.
   - **R1**, `model_sample_climatology_probability`: the same expanding, publication-aware average,
     counting only outcomes whose forecast month is inside that date's observation matrix.
   - **R2**, `condition_chain_probability`: the chain above, its rates re-learned at every forecast
     date from conditions published by then, started from the last published condition, stepping the
     publication gap and then the horizon.
2. **Rule 0007** (`proving/experiments/0007-successor-evaluation-rule/`) governs every new claim.
   - Skill is measured against R1.
   - "Regimes help" means beating R2.
   - Pooled Brier skill is reported beside the mean of ratios.
   - The calibration test is sized for about 31 independent observations.
   - 0001 is frozen and untouched. Its verdicts keep being computed exactly as coded, and printed
     beside 0007's.
3. **The acceptance check is part of the record.** Both of the review's headline numbers reproduced
   from `src/` within 0.001 before either reference was used for anything.

## The calibration test's size, measured before use

Rule 0007 replaced 0001's ten-bin calibration gate for new claims with a logistic
recalibration test. It fixed in advance that the joint test (slope interval contains 1,
intercept interval contains 0) applies only if a perfectly calibrated forecaster passes it
at least 80% of the time at this sample size, and the slope alone otherwise.

`research/briefings/derivations/sim_recalibration_test_size.py` measured it on 200 simulated
panels shaped like the one-year sample:

| test | a perfectly calibrated forecaster passes |
|---|---:|
| joint: slope and intercept | 60.5% |
| slope alone | 77.5% |

So the slope test alone applies (`CALIBRATION_TEST_USES_INTERCEPT = False`). It is not clean
either. Its 95% intervals under-cover on outcomes this persistent, and it fails a calibrated
forecaster about one time in four. That errs against shipping the model. It is recorded, not
adjusted.

On the default, one year, the fitted slope is 0.613 [0.429, 0.825]. The model is
overconfident: its log-odds need shrinking by about 40%. A calibrated forecaster would
rarely produce an interval that far below 1, even allowing for the test's under-coverage.

## Rule 0007's verdict on the default, 2026-09-29

| horizon | 0001 | 0007 | 0007's failing gates |
|---|---|---|---|
| 1 year | SHIP MODEL | SHIP BASE RATE (R1) | calibration; not beaten by the chain (−0.0691 [−0.1148, −0.0292] against R1) |
| 5 years | SHIP BASE RATE | SHIP BASE RATE (R1) | skill, calibration, robustness |
| 10 years | SHIP BASE RATE | SHIP BASE RATE (R1) | skill, robustness, honesty, not beaten by the chain |

That is what 0007 stated in advance it expected.

## The cadence finding

The first implementation of R2 re-learned its rates at the model's annual refits. It gave −0.0544
against the review's −0.0582, outside tolerance. The investigation found why: the review's chain
re-learned its rates every month, and the miss sat exactly where new episodes start mid-year (the
funds rate at the zero bound, CPI above 3%).

Delegated decision P1-11 chose the monthly chain as the reference, because a null weaker than the
cheapest honest forecaster flatters the model. The annual version survives only as a function argument
(`ConditionChainCadence.REFIT`), for two pre-registered checks in experiment 0008. Every comparison
against R2 therefore includes a cadence difference of about −0.004 at one year, and it is charged to
the model.

## Two re-ships, expected

The committed submission was produced by `9f95b12dba40d138`, a configuration with two known look-ahead
paths (ADR 0008). Delegated decision P1-9 re-ships now, under 0001 exactly as coded, with the default
`fec79a040f9ca6f9`: one-year rows from the model, five- and ten-year rows the series-start climatology.
A disclosure ships with it.

A **second** re-ship is expected once experiment 0008 reports, governed by 0007. It is not churn and
not a threshold moving: it is the successor rule doing what it was registered to do.

## What this does not claim

- The adoption of two chains over one (ADR 0010) stands. Its gain survives the corrected benchmark
  (+0.0650). What falls is the claim that the model adds information over a regime-free forecaster.
- Every number here comes from the one 1994–2026 sample already used for every choice this project
  has made. A regime-free reference built after the results were seen can only make the model's test
  harder, but which references to build was still chosen after seeing them.
- The review's scripts are lost. Its page is cited as the source of the finding, not as evidence; the
  evidence is the code in this commit.
