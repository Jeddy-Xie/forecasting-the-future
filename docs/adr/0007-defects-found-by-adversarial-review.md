# 0007. Five defects found by adversarial review after the first complete run

Date: 2026-09-08 · Status: accepted

## Context and problem
After the first end-to-end run produced verdicts, the statistical core was handed
to an independent adversarial review with instructions to verify the mathematics
numerically rather than by eye. It confirmed the parts that matter most —
Baum-Welch to 1e-15 against brute-force enumeration over all state paths, the
filtered probabilities against a direct computation, the survival composition
against a 400,000-path Monte Carlo, the rate estimation against a known generative
model, and every scoring function — and found five real defects.

All five are fixed. The first is the serious one.

## 1. The bootstrap statistic silently changed its estimand
The mean-skill statistic scored whichever indicators happened to be scoreable on
each resample. An indicator whose outcome is nearly always one loses its minority
class in any resample that misses the handful of dates carrying it, so it dropped
out of about a fifth of resamples while staying in the point estimate. The
bootstrap distribution was a mixture of two different quantities, bimodal, and its
bounds reflected the indicator's absence rather than any variation in skill.

The same statistic drove the robustness gate, so the sub-period scores had the
same defect.

**Fixed** by deciding the indicator set once on the full sample and holding it
fixed. A bootstrap resample that cannot score every member of that set is refused
outright rather than quietly averaging fewer columns; the bootstrap already
reports how many resamples contributed. Sub-periods are treated differently and
deliberately: a sub-period is not a resample of one estimand but a description of
one window, so it is scored over the indicators defined in that window with the
count printed beside it.

This fix made the ten-year result **more** adverse to the model, not less: the
skill interval moved from [−2.644, +0.043], spanning zero, to [−2.744, −0.014],
entirely below it.

## 2. A skill score computed where skill is undefined
Chasing the first defect exposed the reason it existed. Four sub-period cells had
an outcome that never varied — the federal funds rate never fell below one percent
between 1985 and 1998, and never was above four percent's opposite in the first
window. The Brier skill score there is a ratio of two numbers that both measure
how close a running base rate happened to sit to a constant, and it contains no
information about discrimination at all. The same model over two such windows
scored **+0.867** on one indicator and **−8.981** on another, and at ten years a
cell produced **−623,002**.

**Fixed** by defining explicitly when a skill score exists: the outcome must vary
in the window, and the benchmark must have some error to remove. Windows failing
that are not scored rather than scored absurdly, everywhere and consistently.
Excluding them turns the ten-year sub-period scores from `nan, −0.533, −62300,
−0.051` into `−0.352, −0.533, +0.109, −0.177`, which still fails the gate at 1 of
4, and the one-year scores into `+0.221, +0.152, +0.098, +0.312`.

## 3. A collapsed state produced a row that was not a distribution
`MINIMUM_STATE_RESPONSIBILITY` guarded the division but not the result. A state
the data abandon leaves a transition row of zeros, which fails the constructor's
stochastic-matrix check and raises out of the maximisation step, through the fit,
aborting every remaining restart and the whole sweep. That contradicted the
documented promise that a collapsed state survives with a near-zero population so
model selection can see it and prefer fewer states. **Fixed:** an abandoned row
falls back to uniform, and the event is logged.

## 4. The likelihood guard asserted something untrue, fatally
The fit raised on any fall in log likelihood, with a message blaming the update
equations. But the covariance ridge is added after the exact maximisation step, so
the update is not quite the maximiser and a small fall is a property of the
regularisation. The review demonstrated a fall of 0.140 at the shipped ridge,
120 times the guard's allowance, on data where a smaller ridge produced none.
**Fixed:** the allowance scales with the ridge, and a genuine fall abandons that
one restart rather than the entire fit.

## 5. The reported likelihood described a discarded model
On the iteration-cap path the loop runs one more maximisation step after the last
likelihood evaluation, so the number returned belonged to the model from one step
earlier — by 0.69 in the review's example. That number is published in the run
manifest and is what restarts are ranked on. **Fixed:** the likelihood is
re-evaluated from the returned model when the cap is hit.

## And one methodological gap
ADR 0006 corrected the calibration standard error for overlap between consecutive
months but not for correlation between the ten indicators pooled into one diagram.
The obvious conservative patch, counting each date once, was tried and rejected:
it widens the band far enough that a completely reversed forecaster passes, and a
check that cannot fail is not a check. The correlation is measured instead, from
the forecast errors, and comes out at 1.25, 1.69 and 1.16 at the three horizons —
modest, and much smaller than the worst case.

Chasing that also exposed a weakness in the monotonicity test itself: it compared
only adjacent bins, so a curve sliding down a little in every step — a complete
reversal — passed, because no single step was large. It now compares every ordered
pair, where the first bin against the last catches exactly that.

## Consequences
- Good: the numbers that decide the verdicts are now computed on quantities that
  exist. Three of the five defects would have produced a plausible number rather
  than an error, which is the failure mode this project is most exposed to.
- Good: fix 1 made the headline long-horizon result stronger against the model.
- Bad / accepted cost: fixes 3 and 4 make the fit more forgiving. A pathological
  fit now degrades into a low-population state or a discarded restart rather than
  a loud failure. Both are logged at warning level, and model selection's
  population floor is the check that catches the first.
- Bad / accepted cost: these were found by review after a complete run, not by the
  test suite. Every one now has a regression test naming the defect it pins.

## Options considered
- Aggregate skill as a ratio of summed errors rather than a mean of ratios, which
  is numerically stable and would have dissolved defect 2 — rejected: the
  pre-registration says "mean Brier skill score across the ten indicators", and
  changing the statistic after seeing results is the one forbidden act. Defining
  when the existing statistic exists is not the same thing.
- Set a floor on the climatological error instead of requiring the outcome to vary
  — rejected: a floor is an arbitrary parameter, and "the outcome varies" is the
  parameter-free statement of the same idea.
