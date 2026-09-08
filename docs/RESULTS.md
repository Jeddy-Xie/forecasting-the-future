# Results

Everything here is produced by `forecast check-gates` and is regenerated, not
typed. The numbers come from a walk-forward run of 19,740 forecasts issued
monthly from December 1971 to September 2026, of which 17,712 have resolved.

## The verdict

The decision rule was committed before the first backtest ran
(`proving/experiments/0001-regime-conditional-forecast-skill/experiment.json`).
It asks five questions per horizon and ships the model only if all five hold.

| horizon | verdict | mean skill | 90% interval | independent observations | failed |
|---|---|---:|---|---:|---|
| 1 year | **ship model** | +0.232 | [+0.158, +0.301] | 53.8 | none |
| 5 years | ship base rate | +0.102 | [−0.013, +0.197] | 9.9 | skill, calibration |
| 10 years | ship base rate | −0.221 | [−2.644, +0.043] | 4.5 | skill, robustness |

Skill is the Brier skill score against an expanding climatology that never knows
anything the model could not have known. Intervals are moving-block bootstraps
with blocks as long as the horizon.

This is what the pre-registration said to expect, written down in advance: *"One
year passes. Five years is marginal. Ten years fails."*

## The regimes

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

## The information horizon

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

## Where the skill actually is

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

## Where the method breaks, precisely

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

## What ships

`submission/forecasts.csv` carries the shipped probability, the source, and both
candidates so the choice is auditable. One-year rows come from the regime model;
five and ten-year rows are the climatological base rate.

## One correction, disclosed

The calibration gate's standard error initially treated overlapping monthly
forecasts as independent, which made it about three and a half times too small at
one year. Correcting it, using the same block length the pre-registration already
mandates for the skill interval, changed the one-year verdict from ship-base-rate
to ship-model. No threshold was moved. ADR 0006 records the whole thing, including
the argument against it.
