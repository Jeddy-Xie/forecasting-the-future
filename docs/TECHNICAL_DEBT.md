# Technical debt

Proposed fixes that have **not** been implemented. Nothing here is a bug in the
sense of a wrong answer to the question the code was asked; these are places where
the question itself was narrower than it should have been, or where a choice was
made without registering that a choice existed.

Each item says what it would change, because a debt list whose entries do not say
what they buy is a wish list. Where a number is quoted it was measured, not
guessed, and the measurement is shown.

**Reviewing this list is Jeddy's call.** Items are not scheduled and nothing here
is being worked on. To close one, implement it and delete the entry with the
commit that does.

Status legend: **material** would move a headline number · **evidential** would
strengthen or weaken confidence without moving the point estimate · **scope**
extends what the method can answer · **ergonomic** affects use, not results.

---

## Look-ahead audit

Asked and answered on 2026-09-09, after D2 was found. Every path by which
information from the whole sample could reach a walk-forward decision, and its
status. Re-run this audit whenever the pipeline gains a step.

| path | status |
|---|---|
| Training panel assembly | **clean under the default** — assembled `as_of` a date, three named vintage policies, a boundary assertion, and an assertion that no forecast date uses the publication-lag fallback. The shipped configuration ran from 1971-12, where 267 of 658 dates did use it. ADR 0008 |
| Standardisation window | **clean** — expanding, never full-sample |
| State probabilities used in forecasts | **clean** — filtered, never smoothed; separate method names and a test |
| Model parameters at each refit | **clean** — refitted from scratch on the point-in-time panel; verified that only the state count is read from the full-sample fit |
| **Number of regimes** | **clean** — chosen once on a burn-in window ending strictly before the first forecast date; the full-sample sweep no longer reaches the backtest. ADR 0008 |
| Conditional rates | **clean except D14** — only conditions whose publication lag had passed; the recession series' registered lag is itself too short after a trough |
| Benchmark (climatology) | **clean since 2026-09-15, except D14** — expanding, and an outcome enters the average at t only once the value it rests on (label s + h, plus the indicator's publication lag) was published by t, the same rule the conditions obey. Before that the average at t counted the outcome of the forecast made at t − h, which rests on the value labelled t: unpublished at t, by five weeks for most series and 400 days for recession dating. Found by the invariance audit (last row), not by reading. ADR 0009 |
| Outcome resolution | **clean by design** — final data is correct for scoring; the forecaster never sees it |
| Condition values feeding rate estimation | **approximation** — final values with timing enforced. Exact for market rates and recession dating. See D5 |
| Every run setting (seed, restarts, burn-in, refit cadence, shrinkage, thresholds, bootstrap) | **clean** — all a priori constants, none derived from the data |
| Acceptance thresholds | **clean** — pre-registered and committed before the first backtest |
| Canonicalisation rule | **clean** — a fixed sort, not fitted |
| **Indicator thresholds** | **weak** — canonical round numbers, but chosen by someone who knew the sample. See D12 |
| **Future-perturbation invariance** (`forecast audit-look-ahead`, run on demand) | **passes on main** since the benchmark fix (ADR 0009): exit 0 at the default cutoff 2000-03-01, all 2190 rows identical. It **failed** at the commit that added it (fb926ff): 12 of 2190 rows moved, every one `climatology_probability` on the cutoff date. The earliest is `consumer_price_inflation_above_five_percent_within_horizon` at 12 months, 0.375 → 0.37662337662337664. *Covers* every path by which an observation unpublished at a cutoff (label on or after it, or label plus its series' registered publication lag past it), or a vintage published after it, reaches a forecast issued on or before it, the benchmark included. Publication-aware since 2026-09-15 rather than label-only, and still exit 0 on main. *Does not cover* revised values of observations already published at the cutoff, in the current-vintage files (D5, by design); a registry publication lag that is itself wrong (D14 is one); or information published between a forecast date and the cutoff. See `docs/REGRESSION_TESTING.md` |

Two entries are still not clean, and they are the two weakest rows rather than the two
worst: the condition values feeding rate estimation (D5, narrowed — see below) and the
indicator thresholds (D12). **D2, the material one, is closed** — see ADR 0008 for what
the fix cost in the numbers.

**A third was found on 2026-09-15, and by execution rather than by reading: the
benchmark.** Every row above was judged by someone reading the code, and that row
said "clean". The invariance audit perturbed everything unpublished at a cutoff and
watched twelve climatology values move. It was closed the same day (ADR 0009). That
is why the audit is now a row of its own, and why the slate's decision rule
requires it to pass on main before any arm runs.

**A fourth was found the same day, by reading, in the one place execution cannot
look.** The audit trusts each series' registered publication lag. An independent
reviewer checked the recession series' lag against NBER's announcement dates and
found it too short after every trough since 1990. See D14.

---

## D1 · No prior on the transition matrix
**material** · raised 2026-09-09 by Jeddy

The transition matrix is plain maximum likelihood from Baum-Welch. The M-step is
a ratio of expected counts with no smoothing:

    A[i,j] = sum_t xi_t(i,j) / sum_t gamma_t(i)

Nine of the twenty off-diagonal entries come out **exactly zero to six decimal
places**. The model is asserting from 908 observations that certain regime
switches are permanently impossible: stagflation can never directly follow the
cheap-money slump. That is a strong claim from finite data and it is the standard
motivation for a Dirichlet prior on each row.

The omission is also internally inconsistent. Conditional rates already carry a
Beta prior at strength 10, on the reasoning that a regime holding forty months
cannot support an unshrunk frequency, and covariances already carry a ridge. The
transition matrix has the same problem and got neither.

Sensitivity, approximated by adding pseudo-counts to the implied transition counts
(roughly 180 expected transitions per row):

| prior on each row | second eigenvalue | half-life | zero entries | horizon |
|---|---:|---:|---:|---:|
| none (shipped) | 0.983 | 41 months | 9 | 126 months |
| Dirichlet a=0.5 | 0.970 | 22 months | 0 | 72 months |
| Dirichlet a=1 (Laplace) | 0.957 | 16 months | 0 | 51 months |
| Dirichlet a=2 | 0.931 | 10 months | 0 | 33 months |

Two caveats on that table. It is not MAP-EM: a real prior would also change the
E-step responsibilities and the model would partly refit around the smoother
transitions, so the true effect is smaller. And these horizons use pure-state
starting points rather than the observed ones, so compare the rows to each other,
not to the 60 months in the report.

**What it would change.** The reported information horizon is probably
optimistic. Regularising would shorten it, leaving the one-year result roughly
intact and making the five and ten-year results worse. It strengthens the paper's
conclusion rather than weakening it, which is its own argument for doing it.

**Shape of the fix.** A Dirichlet concentration as a field on `RunSettings`,
exactly as `conditional_rate_shrinkage_strength` already is, applied in the
maximisation step; the sensitivity of the second eigenvalue to that concentration
reported as a diagnostic rather than buried.

---

## D2 · The number of regimes is chosen with knowledge of the whole sample
**closed** 2026-09-09 by ADR 0008. Kept as a stub because five other lines in
this file and the commit history refer to it by number.

---

## D3 · The conditional-rate shrinkage strength was never tuned
**evidential**

`conditional_rate_shrinkage_strength` is 10. The original brief said to start
there and tune by cross-validation. It was set and left. Nothing establishes that
10 is better than 3 or 30, and the value directly controls how much a
thinly-populated regime's rate is pulled toward the pooled rate, which matters
most at exactly the long horizons where the evidence is thinnest.

**Shape of the fix.** A sweep over the strength inside the walk-forward, scored on
held-out skill, reported as a curve. Cheap, because the fitted models are already
cached and only the rate estimation would rerun.

---

## D4 · The any-time composition compounds a small bias over 120 months
**material at the ten-year horizon only**

The path composition computes survival by multiplying a monthly factor across the
window. Over 120 months a monthly hazard that is slightly too low compounds into a
large error. The clearest case is in the results: for "a recession at any point in
the next ten years" the realised frequency was 98.1% and the model said 69%,
scoring −2.86 against a climatology that is nearly perfect on a near-certainty.

The mechanism is understood and reported. What is not done is the comparison.

**Shape of the fix.** Implement the per-horizon conditional rate as a second
composition path, estimating P(outcome | regime today) directly for each horizon
rather than factoring through the transition matrix. It is less data-efficient at
long horizons by construction, which is why it was not chosen, but running both
and reporting the difference would replace an argument with a measurement.

---

## D5 · Outcomes and conditions are read from final data
**evidential** · **narrowed** 2026-09-09 by ADR 0008

**The model-input half of this entry is closed.** Under the default the
walk-forward starts at 1994-03, the first month on which every model input is on
a genuine point-in-time policy, and `run_walk_forward` refuses to start otherwise.
The panel the hidden Markov model is fitted on no longer contains a revised value
anywhere. That half cost 267 forecast dates and, at the ten-year horizon, most of
the evidence; ADR 0008 reports what it bought and what it cost.

**The outcome-and-condition half stays open, and is what remains of D5.** Outcome
resolution uses final revised data, which is correct: what happened is what
happened. The conditions used to estimate per-regime rates also use final data,
with publication timing enforced but not vintage. For market rates and recession
dating that is exact, because they are not revised. For industrial production it
is an approximation, and its size is measured in the data audit rather than
assumed away.

**Shape of the fix.** Fetch archival vintages for the outcome series too, as is
already done for the two revisable model inputs. Roughly 3,300 further requests at
the current polite rate, so about twenty minutes once. The expected effect is
small, which is exactly why it has not been done, and also why doing it would
close the question rather than leaving it argued.

---

## D6 · The path composition's Markov assumption is only tested indirectly
**evidential**

Equation (2) assumes whether a condition holds depends on last month's condition
and this month's regime, and nothing else. If that fails it shows up as
miscalibration, which the calibration gate tests. But the assumption is testable
directly, and is not tested directly.

**Shape of the fix.** Fit a second-order version of the condition process on the
historical conditions and compare its likelihood to the first-order one. A clear
preference for second order would mean the composition understates persistence.

---

## D7 · Questions phrased relative to today are out of scope
**scope**

"Will unemployment rise two points from where it is now" depends on today's level
as well as the regime, so it is not a function of the regime alone and does not
compose through the transition matrix. Two such indicators were dropped during
design and the exclusion is recorded in the registry and in decision record 0005.

They are, however, the kind of question forecasting competitions actually ask.

**Shape of the fix.** Model the conditional distribution of each level given the
regime, not just the probability of an event. That is a substantially larger
model and would need its own justification.

---

## D8 · One country, one sample
**scope**

Everything is United States post-war. Whether the second eigenvalue is similar in
other economies, and therefore whether the information horizon is a property of
this economy or of regime models generally, is untested. The paper claims the
bound is general for methods of this shape, which follows from the arithmetic, but
the *value* of the horizon is measured once.

**Shape of the fix.** Repeat on two or three other economies with long monthly
histories. The data layer is registry-driven, so this is mostly configuration.

---

## D9 · The diagonal-covariance fallback exists but has never run
**evidential**

`GaussianHiddenMarkovModel` supports a diagonal covariance type as a fallback for
unstable fits at small state counts, and nothing has ever selected it. Untested
code paths in a fitting routine are where surprises live.

**Shape of the fix.** Either exercise it in the sweep and report whether it
changes the choice, or delete it as speculative generality. Deleting is
defensible: the full covariance has been stable across 55 refits and six state
counts.

---

## D10 · No single place to see everything the pipeline generated
**ergonomic** · raised 2026-09-09 by Jeddy

Generated output lands in three places: `.cache/models/` for the eleven named
pipeline artifacts and the cached fits, `artifacts/<date>/` for rendered pages,
and `submission/` for the deliverable. The first two are git-ignored; the third is
tracked deliberately. There is no index, so opening anything requires knowing the
filename.

**Shape of the fix.** A `forecast artifacts` command listing every generated file
in one table with its size, age and the command that wrote it. Deferred because
another session is currently editing the command line interface.

---

## D11 · The mixing chart in notebook 2 samples five horizons
**ergonomic**

The notebook computes the distance at 12, 24, 60, 120 and 240 months and connects
them, so three quarters of the width is flat tail and the interesting decay is
compressed into the left edge. The version in the report computes all 240 months
and reads as the smooth decay it is.

**Shape of the fix.** Compute the dense curve in the notebook too, or cut the axis
at fifteen years.


---

## D12 · The indicator thresholds were chosen by someone who knew the sample
**evidential** · found 2026-09-09 during the look-ahead audit

The ten indicators ask about levels crossing fixed thresholds: unemployment above
five and seven percent, inflation above three and five, the policy rate above four
and below one, the yield curve below zero, output growth above two. Those numbers
were chosen before any backtest, but by someone who already knew what United
States history looks like, and no pre-registration exists for the indicator set
itself the way it does for the decision rule.

The defence, and it is a real one, is that they are canonical round numbers a
newspaper would use rather than tuned quantiles. If they had been tuned for
balance they would cluster near the median of each series. They do not:

| indicator | threshold | percentile of its series | monthly rate |
|---|---:|---:|---:|
| yield curve inverted | 0.0 | 11 | 11% |
| policy rate below one percent | 1.0 | 16 | 16% |
| unemployment above five percent | 5.0 | 37 | 60% |
| output growth above two percent | 2.0 | 41 | 59% |
| policy rate above four percent | 4.0 | 47 | 53% |
| inflation above three percent | 3.0 | 53 | 47% |
| in recession | 0.5 | 72 | 28% |
| unemployment above seven percent | 7.0 | 78 | 20% |
| inflation above five percent | 5.0 | 79 | 21% |

They spread from the 11th to the 79th percentile, which is not what tuning for a
balanced base rate produces.

**What it would change.** Probably nothing in the point estimates. What it costs
is the ability to say the indicator set was fixed independently of the data, which
is a claim the decision rule can make and this cannot.

**Shape of the fix.** Nothing to fix retrospectively; the choice is made. For any
future indicator set, register it the way the decision rule is registered, before
looking at how often each condition holds.

---

## D13 · There is no canonical output to diff a change against
**closed** 2026-09-15 by `forecast baseline`; see `docs/REGRESSION_TESTING.md`.
Kept as a stub because `regression_baseline.py` refers to it by number.

---

## D14 · The recession series' publication lag is too short after a trough
**evidential** · found 2026-09-15 by the independent look-ahead review of arm A5;
every announcement date below was checked at nber.org the same day

The registry gives recession dating a single publication lag,
`publication_lag_days: 400` (`configuration/economic_series.yaml`), so a month's
recession code counts as known 400 days after the month begins. NBER does not
publish months, though. It announces turning points, and a month is known to be
recession or expansion only once the turning point that ends its phase has been
announced:

| turning point | announced | days after the month began |
|---|---|---:|
| peak 1990-07 | 1991-04-25 | 298 |
| trough 1991-03 | 1992-12-22 | 662 |
| peak 2001-03 | 2001-11-26 | 270 |
| trough 2001-11 | 2003-07-17 | 623 |
| peak 2007-12 | 2008-12-01 | 366 |
| trough 2009-06 | 2010-09-20 | 476 |
| peak 2020-02 | 2020-06-08 | 128 |
| trough 2020-04 | 2021-07-19 | 474 |

Every peak came inside 400 days and every trough after them. So the months just
after each trough, coded 0, entered the benchmark and the conditional rates before
anyone knew the recession had ended. Derived with forecast dates on the first of
each month:

| trough | labels read early | forecast dates that read them | of them scored |
|---|---|---|---:|
| 1991-03 | 1991-04 to 1991-11 | 1992-06 to 1992-12 | 0 |
| 2001-11 | 2001-12 to 2002-06 | 2003-02 to 2003-07 | 6 |
| 2009-06 | 2009-07 to 2009-08 | 2010-09 | 1 |
| 2020-04 | 2020-05 to 2020-06 | 2021-07 | 1 |

That is 8 of the 391 scored forecast dates, and only the two recession indicators.
The invariance audit cannot see it, because it perturbs by the registered lag, and
its record says so.

**What it would change.** Unmeasured on main. In arm A5, its reviewer measured
that withholding the affected 2001-trough outcomes moves those forecasts by at most
0.0025. Main and every research arm read the same registry, so the leak cannot
favour one side of a paired comparison, but it can move both.

**Shape of the fix.** Either option is Jeddy's call:
- **A longer fixed lag, at least 662 days.** Simple, but it also withholds every
  month near a peak for 262 days after it was really known.
- **Availability by turning point.** A month's code counts as known once the
  turning point ending its phase has been announced, read from a dated table of
  NBER announcements, the way archival vintages are dated. Exact, at the cost of a
  small registry of eight rows since 1990.

Whichever it is, it should be its own change, measured against main with
`forecast baseline compare`. It should come after experiment 0002 closes, because
changing main now would move the reference run under every arm mid-slate.
