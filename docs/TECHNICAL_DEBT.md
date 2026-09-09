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
**material** · found 2026-09-09 while answering a question about the backtest

`forecast fit-regimes` sweeps one to six states on the panel as of **today** and
writes the winner. `forecast backtest` then reads `state_count` off that artifact
and uses it for all 55 refits, including the one that issues forecasts for 1972.

Every other quantity in the walk-forward is honest: the panel is point-in-time,
the parameters are refitted on data available then, the conditional rates use only
published conditions, the benchmark expands. The *hyperparameter* is not. Five
regimes was chosen using data through 2026 and applied to a forecast made in 1971.

This is the one look-ahead the pipeline does not currently prevent, and the
project's own standing rule says every panel is assembled as of a date.

**What it would change.** Unknown, and that is the point. If an earlier sample
prefers three or four states, the early backtest was run with a state count it
could not have known. The direction of the bias is not obvious, but its existence
is not in doubt.

**Shape of the fix.** Either select the state count inside the walk-forward at
each refit, which is expensive and introduces its own instability as the choice
flips between adjacent counts, or select once on a burn-in window that ends before
the first forecast date, which is cheap and clearly honest. The second is
preferable. Report both alongside the shipped result the first time.

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
**evidential**

Outcome resolution uses final revised data, which is correct: what happened is
what happened. The conditions used to estimate per-regime rates also use final
data, with publication timing enforced but not vintage. For market rates and
recession dating that is exact, because they are not revised. For industrial
production it is an approximation, and its size is measured in the data audit
rather than assumed away.

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
