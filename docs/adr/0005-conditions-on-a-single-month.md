# 0005. Every indicator is a condition on a single month

Date: 2026-09-08 · Status: accepted

## Context and problem
The brief asked for both composition paths: a point-in-time question about the
horizon date, and an any-time-within-horizon question about the whole window. The
first draft of the indicator registry had six resolution rules, two of which were
phrased relative to today's level: "does unemployment rise two points from where
it is now", and "is industrial production higher then than it is now".

Those two do not compose. The probability of a point-in-time question given the
regime at the horizon is a per-regime rate that serves every horizon. The
probability that a level rises two points from *today's* level depends on today's
level as well as on the regime, so it is not a function of the regime at all. It
needs a conditional distribution of the level given the regime, which is a
different and much larger model, and it would have required a third composition
path used by two indicators.

## Decision
Every indicator is a condition on the state of the economy in a single month: a
series above a threshold, or below one. Three resolution rules cover all ten.
Point-in-time asks whether the condition holds in the horizon month;
any-time-within-horizon asks whether it holds in any month of the window.

The two origin-relative indicators were replaced with fixed-threshold equivalents
of the same economic spirit: unemployment above seven percent within the horizon,
and industrial production growing above two percent at the horizon.

## Consequences
- Good: one per-regime rate serves all three horizons, which is what makes the
  long horizon estimable at all. Estimating a separate rate per horizon starves at
  ten years, where an outcome needs ten years of history after the forecast before
  it can be counted.
- Good: two composition paths, three rules, no special cases, and the registry can
  check that a rule and a composition are paired coherently.
- Good: the exclusion is written into the registry file itself, so a future
  contributor adding an origin-relative indicator meets the reason rather than the
  rule.
- Bad / accepted cost: "will X be higher than today" is a natural question that
  real forecasting competitions ask, and this project cannot answer it. Stated in
  the limitations section of the report rather than left for a reader to notice.

## Options considered
- Keep both and add a third composition path estimating a rate per horizon —
  rejected: an extra path with two users, a much thinner evidence base at long
  horizons, and it would not use the transition matrix, which is the thesis under
  test.
- Keep both and model the conditional distribution of each level given the regime
  — rejected: a substantially larger model for two of ten indicators.
