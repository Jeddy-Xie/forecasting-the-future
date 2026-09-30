# Results

Every number in the first part of this page comes from committed code, and is regenerated rather than
typed:
- `forecast check-gates` for the verdicts;
- `forecast skill-by-horizon` for the curve;
- `forecast baseline compare` for the paired differences.

The run is the default configuration, `fec79a040f9ca6f9`: two regime chains (ADR 0010), recession status
dated by its announcement (ADR 0011). It has 391 monthly forecast dates from 1994-03 to 2026-09, and 9,702
of its 11,730 forecasts have resolved. The second part, **History**, keeps the tables that were
published for earlier configurations, unchanged, with the corrections that retired them.

**What ships.** Since 2026-09-29 `submission/forecasts.csv` comes from this run: one year ships the
model, five and ten years the base rate, as 0001 computes it. The re-ship was a delegated decision
(P1-9), not the owner's own. It ships with this disclosure, also in `submission/README.md`:

- On 2026-09-25 a regime-free two-rate condition chain was measured beating this model at one year:
  −0.0582, 98.33% [−0.1119, −0.0089], reproduced from committed code.
- Against a climatology restricted to the model's own sample, its recession indicators score below
  zero.
- Both it and the single chain are registered forward.
- The next re-ship is governed by rule 0007.

## The verdict, under both rules

Two rules are printed side by side, and neither replaces the other:
- **0001**, frozen before the first backtest ran, is the rule the pipeline's gate answers to. It scores
  skill against a climatology over every outcome since each source series began: 1854 for recession
  dating.
- **Rule 0007** (ADR 0012) governs every new claim and every re-ship from 2026-09-29 on. It scores skill
  against R1, the same average restricted to the model's own sample. It tests calibration with a test
  sized for this sample, and requires the model not to be beaten by R2, a regime-free chain on each
  indicator's own condition.

| horizon | 0001 | skill, series-start | 90% | 0007 | skill, R1 | 90% | 0007 fails |
|---|---|---:|---|---|---:|---|---|
| 1 year | **ship model** | +0.2673 | [+0.1652, +0.3649] | ship base rate | +0.1786 | [+0.1020, +0.2578] | calibration, the chain |
| 5 years | ship base rate | +0.1194 | [−0.1086, +0.2507] | ship base rate | +0.0690 | [−0.1209, +0.1905] | skill, calibration, robustness |
| 10 years | ship base rate | −0.1624 | [−0.2577, +0.0305] | ship base rate | −0.2109 | [−0.3006, −0.0398] | skill, robustness, honesty, the chain |

**0001's gates at one year.**
- Calibration error: 0.0893 at one year, 0.1549 at five, 0.0943 at ten.
- Robustness: skill is positive in 4 of 4 sub-periods at one year (+0.055, +0.079, +0.401, +0.182).
- Honesty: the distance to the stationary distribution is 0.4575 at one year.

**0007's calibration test at one year** fits a slope of 0.613 [0.429, 0.825], where 1 is calibrated. The
model is overconfident, and the regime-free chain beats it by 0.069 [0.029, 0.115] against R1.

## Skill at every horizon, and where to ship the average

Measurement 0010, registered before it ran, scores every month from 1 to 120. The full tables are in
`research/reports/skill-at-every-horizon/`, and the reading is in
`research/experiments-drafts/0010-skill-at-every-horizon.RESULT.md`.

| months | model, R1 | chain, R1 | model minus chain, 90% |
|---:|---:|---:|---|
| 1 | +0.290 | +0.532 | −0.243 [−0.358, −0.181] |
| 6 | +0.236 | +0.367 | −0.130 [−0.192, −0.084] |
| 12 | +0.179 | +0.248 | −0.069 [−0.115, −0.029] |
| 24 | +0.135 | +0.144 | −0.009 [−0.062, +0.043] |
| 36 | +0.109 | +0.105 | +0.004 [−0.075, +0.075] |
| 60 | +0.069 | +0.088 | −0.020 [−0.173, +0.079] |
| 120 | −0.211 | +0.032 | −0.243 [−0.327, −0.072] |

- **The regime model carries skill for 29 months against R1**, and 39 against the series-start benchmark.
  Beyond that, as far as this sample can say, the historical average does as well.
- **The regime-free chain carries skill at every horizon measured.** Beyond 60 months that rests on
  fewer than 5.5 independent observations.
- **The model is never better than the chain.** It is worse at 1–16 and 103–120 months, and the two
  cannot be told apart in between.

## Where the regimes help, and where they do not

One year, skill against R1 (ADR 0012):

| question | the model sees it? | model | chain |
|---|---|---:|---:|
| inflation above 5%, any time | input | **+0.501** | +0.406 |
| inflation above 3%, at the horizon | input | **+0.142** | +0.046 |
| funds rate below 1%, any time | through the bill rate | **+0.675** | +0.610 |
| funds rate above 4%, at the horizon | through the bill rate | +0.324 | **+0.447** |
| yield curve inverted, any time | one leg | +0.179 | **+0.195** |
| output growth above 2%, at the horizon | input | −0.046 | **+0.032** |
| unemployment above 7%, any time | no | +0.437 | **+0.500** |
| unemployment above 5%, at the horizon | no | −0.110 | **+0.242** |
| recession, any time | no | −0.283 | **+0.007** |
| recession, in the horizon month | no | −0.033 | **−0.008** |

The regimes earn their keep where the model's inputs are the question. They lose where the question is
about something the model never observes, and where the answer is mostly whether the condition holds
now, which the point-in-time composition ignores.

By composition path, one year, mean skill:

| path | series-start | R1 |
|---|---:|---:|
| any time within the horizon | +0.402 | +0.302 |
| point in time | +0.133 | +0.055 |

## The regimes and the information horizon

These are today's fit, on the full panel.

| chain | states | second eigenvalue | expected visits |
|---|---:|---:|---|
| growth | 4 | 0.946 | 6.0 to 13.4 months |
| inflation and rates | 4 | 0.983 | 23.1 to 42.9 months |
| joint | 16 | 0.983 | a half-life of 39 months |

The distance from a projected regime distribution to the stationary one is:
- **one year:** 0.486;
- **five years:** 0.121;
- **ten years:** 0.033.

On the backtest's own dates it first falls to 0.05 at 120 months, which is why 0001's ten-year honesty
gate fails by a hair (0.0499). The two-chain gain over the single chain holds on current code:
+0.0588, 98.33% [+0.0146, +0.1017] (ADR 0010, measured again).

## Research in progress

- **Experiment 0008**, registered before any arm ran, tests three ways of keeping what regimes add
  while taking what the chain has. Its control reproduces the reference exactly.
  - B1: point-in-time questions through the joint regime-by-condition chain.
  - B2: observe unemployment and the term spread.
  - B3: an equal blend with the chain.
  - Its results are in `research/experiments-drafts/0008-condition-aware-regime-forecasts.RESULT.md`
    once they report.
- **Experiment 0006**: is the two-chain gain structure or granularity? It runs against a same-code
  single-chain anchor.

---

# History, as it was recorded

Everything below was published for earlier configurations. It is kept as it was, and the corrections
that retired it are inside it. The headline tables describe `9f95b12dba40d138`, which shipped from
2026-09-08 to 2026-09-29. Their one-year verdict did not survive the two look-ahead fixes (ADR 0008).

Everything here is produced by `forecast check-gates` and is regenerated, not
typed. The numbers come from a walk-forward run of 19,740 forecasts issued
monthly from December 1971 to September 2026, of which 17,712 have resolved.

**Which run.** Three configurations matter here, and the tables below are the
oldest of them. They were produced by the **shipped** configuration, hash
`9f95b12dba40d138`, which stopped being the default on 2026-09-09. It was replaced
by the honest configuration `ad7fcc1affd0746a`, which closes two look-ahead paths
and reaches a materially different verdict (ADR 0008). Since 2026-09-20 the default
is `fec79a040f9ca6f9`: the same honest configuration fitted with two chains on two
timescales instead of one (ADR 0010).

The tables are labelled rather than replaced, because replacing them without
regenerating `submission/forecasts.csv` would leave the submission and the report
describing different runs. Re-shipping needs the owner's token, so the submission
still carries `9f95b12dba40d138` and says so.

**Correction, 2026-09-15: the benchmark counted one outcome early.** The claim
below, that the climatology "never knows anything the model could not have known",
was false. At each date the benchmark counted the outcome resting on that month's
own value, weeks before the value was published, and 400 days before for recession
dating. `forecast audit-look-ahead` found it, and it was fixed the same day. See
ADR 0009.

Recomputed on the shipped run behind these tables, it changes no verdict:
- one-year mean skill +0.232 → +0.235;
- five years +0.102 → +0.104;
- ten years −0.221 → −0.219;
- the base rates in `submission/forecasts.csv` move by at most 0.006.

The tables are left as published and the submission is not regenerated. Whether
to re-ship is Jeddy's call.

### The verdict

The decision rule was committed before the first backtest ran
(`proving/experiments/0001-regime-conditional-forecast-skill/experiment.json`).
It asks five questions per horizon and ships the model only if all five hold.

| horizon | verdict | mean skill | 90% interval | independent observations | failed |
|---|---|---:|---|---:|---|
| 1 year | **ship model** | +0.232 | [+0.158, +0.301] | 53.8 | none |
| 5 years | ship base rate | +0.102 | [−0.013, +0.197] | 9.9 | skill, calibration |
| 10 years | ship base rate | −0.221 | [−2.744, −0.014] | 4.5 | skill, robustness |

Skill is the Brier skill score against an expanding climatology that never knows
anything the model could not have known. Intervals are moving-block bootstraps
with blocks as long as the horizon.

This is what the pre-registration said to expect, written down in advance: *"One
year passes. Five years is marginal. Ten years fails."*

### The regimes

Five, found rather than imposed. The model was fitted on continuous standardised
growth, inflation and interest rates; the labels are read off the fitted emission
means afterwards.

| regime | growth | inflation | rate | months | typical visit |
|---|---:|---:|---:|---:|---:|
| contracting growth, low inflation, low rates | −0.6% | 2.1% | 0.58% | 23% | 31 months |
| contracting growth, high inflation, high rates | −1.5% | 9.2% | 9.39% | 10% | 29 months |
| steady growth, moderate inflation, high rates | 3.4% | 2.5% | 4.57% | 32% | 33 months |
| steady growth, moderate inflation, neutral rates | 4.0% | 2.7% | 4.17% | 23% | 42 months |
| steady growth, high inflation, high rates | 5.9% | 5.4% | 5.01% | 14% | 19 months |

Growth and inflation are year-over-year, the rate is the three-month Treasury
bill. The second regime is stagflation and the first is the zero-rate world after
2008; neither was put there by hand. Across 908 months the most likely regime
changes 30 times, about once every two and a half years.

Five states beat one on both criteria: held-out log likelihood per month −2.48
against −4.30, information criterion 3,394 against 5,635.

### The information horizon

The transition matrix's second largest eigenvalue modulus is **0.983**, a half
life of 41 months. The distance between a projected regime distribution and the
model's long-run distribution decays at that rate:

| horizon | distance to the long-run distribution | still informative |
|---|---:|---|
| 1 year | 0.497 | yes |
| 2 years | 0.346 | yes |
| 5 years | 0.149 | yes |
| 10 years | 0.047 | no |
| 20 years | 0.006 | no |

The information horizon is **five years**. At ten years the projection is the
unconditional base rate to within five percentage points of total variation, which
is the threshold below which the two are not usefully distinguishable.

Note that the ten-year honesty gate passed on the backtest's own distances (mean
0.0506 against a floor of 0.05) while failing on this full-sample measure. That
margin is a fifth of a percentage point. Nothing rests on which side of it the
number falls: the ten-year horizon ships the base rate anyway, on skill and
robustness.

### Where the skill actually is

Mean skill by composition path, which is the most useful cut in the whole run:

| horizon | any-time-within-horizon | point-in-time |
|---|---:|---:|
| 1 year | **+0.390** | +0.074 |
| 5 years | +0.104 | +0.100 |
| 10 years | −0.579 | +0.138 |

At one year almost all the skill is in questions of the form "does this happen at
any point between now and then". Their mean area under the curve is 0.758 against
0.534 for point-in-time questions, which is close to a coin flip. Knowing the
regime tells you a lot about whether an episode is coming and comparatively little
about where a slow-moving level will sit in one particular month.

The best and worst one-year indicators say the same thing:

| indicator | skill | area under the curve |
|---|---:|---:|
| federal funds rate below one percent within horizon | +0.602 | 0.855 |
| consumer price inflation above five percent within horizon | +0.542 | 0.824 |
| unemployment rate above seven percent within horizon | +0.534 | 0.825 |
| … | | |
| unemployment rate above five percent at horizon | −0.056 | 0.383 |
| industrial production growth above two percent at horizon | −0.125 | 0.423 |

### Where the method breaks, precisely

The ten-year any-time figure of −0.579 is not noise, and it is worth naming its
cause. The path composition computes the probability that a condition never holds
by multiplying a survival factor across every month of the window. Over 120 months
any bias in the monthly hazard compounds geometrically.

The clearest case is "is the economy in a recession at any point in the next ten
years". Over this sample the answer was yes 98.1% of the time; the model said 69%.
Climatology scores a Brier of 0.019 on a near-certainty and the model scores 0.072,
which is a skill score of −2.86. A shrunk hazard that is slightly too low is
almost right for one year and badly wrong compounded over 120.

That is a real limitation of the hazard formulation at long horizons, and it is
the reason the ten-year horizon ships the base rate rather than a number that
looks like a forecast.

### What ships

`submission/forecasts.csv` carries the shipped probability, the source, and both
candidates so the choice is auditable. One-year rows come from the regime model;
five and ten-year rows are the climatological base rate.

### Stability across sub-periods

The robustness gate asks whether skill survives being cut into four disjoint
chronological blocks. Where an indicator's outcome never varies inside a block its
skill score does not exist there, so the block is scored over the indicators that
do vary, with the count reported.

| block | 1 year | 5 years | 10 years |
|---|---:|---:|---:|
| first quarter | +0.221 (8) | +0.106 (7) | −0.352 (6) |
| second | +0.152 (8) | +0.017 (9) | −0.533 (10) |
| third | +0.098 (10) | −0.262 (10) | +0.109 (7) |
| fourth | +0.312 (10) | +0.122 (9) | −0.177 (8) |
| positive | 4 of 4 | 3 of 4 | 1 of 4 |

### The cost of the two look-ahead paths

Two paths by which whole-sample information reached a walk-forward decision were
closed on 2026-09-09 (ADR 0008): the number of regimes was chosen on the panel as
it stands *today*, and 267 of 658 forecast dates fitted the model on revised
consumer price index values because the archive holds no usable vintage before
1994-03. `forecast compare-variants` runs all four cells against the **same**
unchanged pre-registered decision rule.

| variant | start | states | dates | fallback | horizon | verdict | skill | 90% interval | independent |
|---|---|---:|---:|---:|---:|---|---:|---|---:|
| shipped | 1971-12 | 5 | 658 | 267 | 1y | **ship model** | +0.2320 | [+0.1578, +0.3011] | 53.8 |
| shipped | 1971-12 | 5 | 658 | 267 | 5y | ship base rate | +0.1021 | [−0.0130, +0.1969] | 9.9 |
| shipped | 1971-12 | 5 | 658 | 267 | 10y | ship base rate | −0.2205 | [−2.7437, −0.0137] | 4.5 |
| state count fixed | 1971-12 | 2 | 658 | 267 | 1y | ship base rate | +0.2414 | [+0.1723, +0.3050] | 53.8 |
| state count fixed | 1971-12 | 2 | 658 | 267 | 5y | ship base rate | +0.1147 | [+0.0248, +0.1865] | 9.9 |
| state count fixed | 1971-12 | 2 | 658 | 267 | 10y | ship base rate | −0.0197 | [−1.1474, +0.0632] | 4.5 |
| start fixed | 1994-03 | 5 | 391 | 0 | 1y | ship base rate | +0.2462 | [+0.1325, +0.3566] | 31.5 |
| start fixed | 1994-03 | 5 | 391 | 0 | 5y | ship base rate | +0.0619 | [−0.2163, +0.2030] | 5.5 |
| start fixed | 1994-03 | 5 | 391 | 0 | 10y | ship base rate | −0.4940 | [−0.5273, −0.1265] | 2.2 |
| **both (the default)** | 1994-03 | 6 | 391 | 0 | 1y | ship base rate | +0.2128 | [+0.0973, +0.3250] | 31.5 |
| **both (the default)** | 1994-03 | 6 | 391 | 0 | 5y | ship base rate | +0.0722 | [−0.1986, +0.2176] | 5.5 |
| **both (the default)** | 1994-03 | 6 | 391 | 0 | 10y | ship base rate | −0.3524 | [−0.4208, −0.1212] | 2.2 |

**The one-year ship-model verdict does not survive either fix.** Every honest cell
ships the base rate at every horizon. No threshold was moved to get there; the
decision rule is the one committed before the first backtest ran.

The two fixes kill it for different reasons, and the difference matters more than
the shared outcome.

**Fixing the state count kills it because regimes do not exist on the 1971 burn-in
window.** The gate asks whether more than one state beats one on both the held-out
log likelihood and the information criterion. On the 251 months an observer
actually had at 1971-12:

| states | held-out log likelihood/month | information criterion |
|---:|---:|---:|
| 1 | **−5.7037** | 1,271 |
| 2 | −5.8281 | 1,040 |
| 5 | −6.2978 | **806** |
| 6 | −6.4209 | 812 |

A single Gaussian wins the holdout outright. The criterion prefers five states,
the holdout prefers one, the gate requires both, so regimes-exist fails and every
horizon ships the base rate — even though that cell has the *best* ten-year skill
of any, at −0.0197. On the evidence available in 1971 there was no basis for a
regime model at all. By 1994-03, on 518 months, two states beat one (−3.098
against −3.586) and six wins outright, so the default cell passes this gate.

**Fixing the start kills it because the sample is no longer large enough.** The
independent observations behind the one-year verdict fall from 53.8 to 31.5, at
five years from 9.9 to 5.5, and at ten years from **4.5 to 2.2**. The robustness
gate cuts the sample into four chronological blocks and is being asked to find a
stable sign in roughly half an independent observation per block. **Any ten-year
verdict from an honest run is close to uninformative by construction.** That is a
real cost of removing the leak, not a malfunction, and it is not grounds to move a
threshold. "The honest sample cannot answer the ten-year question" is this
project's own thesis about information horizons, applied to its own evidence base.

The 1994-03 start also removes the entire stagflation episode from the
walk-forward. The fitted panel still sees 1950–1994, so the model still learns
that regime; but no forecast is ever issued during it, so none is ever scored on
it.

**Caveat.** The default cell chooses six states, the top of the swept range
(1..6). The choice sits at the boundary, so the range may be binding and the true
preference may be higher. Widening it is a third configuration change and would
confound the comparison, so it was not done.

**`submission/forecasts.csv` was not regenerated.** It still carries the shipped
configuration's numbers, on hash `9f95b12dba40d138`, and nothing outward-facing
moved. That is deliberate: the honest result changes what this project ships, and
that is Jeddy's call to make on the evidence above, not a side effect of a code
change. `forecast submit` now **refuses** to regenerate it unless the run is the
approved configuration or a single-use, named authorisation is present, and the
routine pipeline step is `forecast submit --verify-only`, which writes nothing.

### Three corrections, all disclosed

**The calibration standard error** initially treated overlapping monthly forecasts
as independent, which made it about three and a half times too small at one year.
Correcting it, using the block length the pre-registration already mandates for
the skill interval, changed the one-year verdict from ship-base-rate to
ship-model. No threshold moved. ADR 0006 records it, including the argument
against it. It was later extended to a second axis of dependence, the correlation
between the ten indicators, measured at 1.25, 1.69 and 1.16 across the horizons.

**Five defects in the statistical core** were found by an adversarial review after
the first complete run, and are recorded in ADR 0007. The one that moved a number
is worth repeating here: the bootstrap statistic scored whichever indicators
happened to be scoreable on each resample, so a near-certain indicator dropped out
of about a fifth of them while remaining in the point estimate. Fixing it made the
ten-year result **more** adverse to the model, moving its skill interval from
[−2.644, +0.043], which spanned zero, to [−2.744, −0.014], which does not.

**The first usable consumer price index vintage** was documented as 1997 in ADR
0002 and in the `MINIMUM_USABLE_VINTAGE_MONTHS` docstring. That was an estimate.
The measured boundary is **1994-03-01**, the first vintage date on which the
archive returns a usable series (565 observations, 1947-01 .. 1994-01); every
earlier date returns a rolling window of about nineteen. Both places are
corrected, each keeping a note of what it previously said. The pre-registration
carries the same 1997 estimate in its known-limitations prose and was
**deliberately not edited** — it is frozen, the sentence is descriptive rather
than a threshold, and correcting a frozen pre-registration after the fact is the
wrong instinct even when the correction is true. The discrepancy is recorded in
ADR 0008 instead.
