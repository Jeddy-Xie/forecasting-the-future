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
| Benchmark (climatology) | **clean since 2026-09-15, except D14** — expanding, and an outcome enters the average at t only once the value it rests on (label s + h, plus the indicator's publication lag) was published by t, the same rule the conditions obey. Before that the average at t counted the outcome of the forecast made at t − h, which rests on the value labelled t: unpublished at t, by five weeks for most series and 400 days for recession dating. Found by the invariance audit (last row), not by reading. ADR 0009. Clean *as a benchmark* only: it averages final, revised outcome values (D5) back to 1919. That is harmless while no forecast reads it, and it becomes a leak the moment one does. Research arm A6 blended it into its forecasts and was voided for exactly this |
| Outcome resolution | **clean by design** — final data is correct for scoring; the forecaster never sees it |
| Condition values feeding rate estimation | **approximation** — final values with timing enforced. Exact for market rates and recession dating. See D5 |
| Every run setting (seed, restarts, burn-in, refit cadence, shrinkage, thresholds, bootstrap) | **clean** — all a priori constants, none derived from the data |
| Acceptance thresholds | **clean** — pre-registered and committed before the first backtest |
| Canonicalisation rule | **clean** — a fixed sort, not fitted |
| **Indicator thresholds** | **weak** — canonical round numbers, but chosen by someone who knew the sample. See D12 |
| **Future-perturbation invariance** (`forecast audit-look-ahead`, run on demand) | **passes on main** since the benchmark fix (ADR 0009): exit 0 at the default cutoff 2000-03-01, all 2190 rows identical. It **failed** at the commit that added it (fb926ff): 12 of 2190 rows moved, every one `climatology_probability` on the cutoff date. The earliest is `consumer_price_inflation_above_five_percent_within_horizon` at 12 months, 0.375 → 0.37662337662337664. *Covers* every path by which an observation unpublished at a cutoff (label on or after it, or label plus its series' registered publication lag past it), or a vintage published after it, reaches a forecast issued on or before it, the benchmark included. Publication-aware since 2026-09-15 rather than label-only, and still exit 0 on main. *Does not cover* revised values of observations already published at the cutoff, in the current-vintage files (D5, by design); a registry publication lag that is itself wrong (D14 is one); a state count decided anywhere but the burn-in sweep function, which the audit calls directly (D15); or information published between a forecast date and the cutoff. See `docs/REGRESSION_TESTING.md` |

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
**closed** 2026-09-21 by measurement, not by implementation. Research arm A1
(`sticky-dirichlet-prior`, experiment 0002, look-ahead review CLEAN) is exactly the
fix this entry proposes: in the maximisation step each transition row becomes the
Dirichlet posterior mean, `A[k,j] = (n[k,j] + beta + kappa*1{j=k}) / (n[k] + K*beta
+ kappa)`, applied in the burn-in sweep, every refit and today's fit.

**The mechanism is confirmed.** Lambda2, read off the fitted transition matrices:
0.9777 to 0.9700 at the 1994-03 refit, 0.9845 to 0.9761 at 2026-03. The prior does
regularise the matrix and shorten the horizon, as argued below.

**The consequence is contradicted.** This entry predicted the one-year result would
survive and the five and ten-year results would get worse, "strengthening the paper's
conclusion rather than weakening it". Measured, paired against main:

| horizon | main | with the prior | difference | 90% interval |
|---|---:|---:|---:|---|
| 12 months | +0.2154 | +0.2200 | +0.0046 | [−0.0126, +0.0232] spans zero |
| 60 months | +0.0728 | +0.0698 | −0.0030 | [−0.0430, +0.0574] spans zero |
| 120 months | −0.3528 | −0.1623 | **+0.1905** | [+0.0899, +0.2320] excludes zero |

One and five years survive as predicted. Ten years **improves**, not worsens, and the
ten-year honesty distance improves too (0.0373 to 0.0199) where this entry expected it
to fail by a wider margin. On 2.25 effective independent observations that is weak
evidence, but it points the opposite way to the argument made here, and the argument
should not be repeated as though it had been borne out.

**Not adopted.** No verdict moved at any horizon, and 0002's pre-registered rule
returned none of the above: not PROMISING, not CONFIRMED, not HARMFUL. The question
this entry raised is answered by measurement; adoption was declined by the rule.

One caveat for whoever implements it on main: A1's monotonicity guard comments that the
log posterior "IS guaranteed to rise". That holds for the MAP update `(n + alpha - 1)/(...)`,
not for the posterior-MEAN update `(n + alpha)/(...)` A1 actually uses, so the monitored
quantity is not guaranteed monotone and the guard could fire on a correct fit. It never
fired on that run and no number depends on it.
**was: material** · raised 2026-09-09 by Jeddy

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
**closed** 2026-09-21 by the sweep this entry asks for:
`research/derivations/shrinkage_strength_sweep.py` runs the walk-forward at five strengths
and scores each with the pre-registered verdict's own statistic, so the curve is in the
same units as every other number here. All 33 refits, 391 forecast dates, 16 regimes:

| strength | 1 year | 5 years | 10 years |
|---:|---:|---:|---:|
| 1 | +0.2563 | +0.0902 | −0.4088 |
| 3 | +0.2607 | +0.1012 | −0.3153 |
| **10 (shipped)** | **+0.2673** | **+0.1194** | **−0.1624** |
| 30 | +0.2686 | +0.1319 | −0.0380 |
| 100 | +0.2590 | +0.1327 | +0.0307 |

**Something now establishes that 10 is not worse than 3 or 30.** At the pre-registered
one-year endpoint the curve is flat across its top: 30 beats 10 by +0.0013, which is more
than an order of magnitude inside the paired interval's half-width of roughly 0.016, so
the two are not distinguishable on this sample. Below that, 3 loses 0.0066 and 1 loses
0.0110; above it, 100 loses 0.0083. The shipped value sits where the curve stops rewarding
more shrinkage and before it starts punishing it.

**The long horizons rise monotonically and do not license a change.** Ten years goes from
−0.4088 to +0.0307 as the strength climbs, which is what heavy shrinkage toward the pooled
rate should do when regime-level evidence is thin. But five and ten years carry about 5.5
and 2.2 effective independent observations, and this project's own limits say no ten-year
number here is informative. Moving a hyperparameter to chase them would be tuning on the
sample the result is measured against, which is the failure the pre-registration exists to
prevent.

**Not changed, and that is the finding.** The value stays at 10. What the entry was
missing was evidence, not a different number.

One structural note, because this entry's cost estimate is wrong as the code stands. It
predicts the sweep is "cheap, because the fitted models are already cached and only the
rate estimation would rerun". `conditional_rate_shrinkage_strength` is a `RunSettings`
field and is not in the omission map, so it enters `configuration_hash()`, which is part
of the fitted-model cache key. Every strength therefore misses the cache and refits all 33
models, even though the shrinkage cannot affect a fit: five full refit sets, about
seventy minutes, where the entry budgeted for one rate-estimation pass. Exempting a field
that provably cannot change a fit would make this genuinely cheap, and would be its own
small change with its own review.
**was: evidential**

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
**closed** 2026-09-21 by measurement. Research arm A5 (`direct-horizon-rates`,
experiment 0002, look-ahead review CLEAN) is the comparison this entry asks for: the
per-horizon conditional rate estimated directly, `rate[k] = sum_s gamma_s[k] * y_s,h /
sum_s gamma_s[k]`, replacing both compositions for every indicator and horizon.

| horizon | main | direct path | difference | 90% interval |
|---|---:|---:|---:|---|
| 12 months | +0.2154 | +0.1137 | −0.1017 | [−0.1448, −0.0586] excludes zero |
| 60 months | +0.0728 | −0.0856 | −0.1583 | [−0.2285, +0.0019] spans zero |
| 120 months | −0.3528 | −0.0881 | **+0.2647** | [+0.0459, +0.2526] excludes zero |

The compounding described below is real and the direct path does correct it: ten-year
skill improves by +0.2647. The price is the short horizon, where the direct path is far
worse (−0.1017, HARMFUL by 0002's rule, and disqualified from combination). The
data-efficiency cost this entry predicted "by construction" is visible too: mean
effective sample size for recession-within-ten-years falls from 98.1 to 39.9.

So the argument this entry wanted replaced by a measurement has been: the path
composition is the right default, and its ten-year bias is a real and quantified cost of
that choice rather than an oversight. Not adopted, for the one-year result.
**was: material at the ten-year horizon only**

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
**closed** 2026-09-21 by measurement, not by implementation, which is what this entry
asks for: "the expected effect is small, which is exactly why it has not been done, and
also why doing it would close the question rather than leaving it argued."

**The open half is narrower than it reads.** Conditions and outcomes require six series.
Two, `consumer_price_index` and `industrial_production`, are model inputs and already get
archival vintages. Two, `federal_funds_rate` and the term spread's legs, are never
revised, which is the "exact for market rates" this entry claims. That leaves exactly
two: `UNRATE` and `USREC`.

**Measured** by `research/derivations/vintage_vs_final_conditions.py`, comparing each
refit date's archival vintage against the final file on every month published by then,
over all 33 refit dates (the 132 vintages are now cached, so it re-runs offline):

| series | values differing | condition | would flip |
|---|---:|---|---:|
| USREC | 10 of 29,541 (0.034%) | recession, `> 0.5` | 10 of 29,541 (0.034%) |
| UNRATE | 467 of 24,584 (1.900%) | unemployment `> 5.0` | 15 of 24,584 (0.061%) |
| UNRATE | " | unemployment `> 7.0` | 9 of 24,584 (0.037%) |

**34 condition-months in about 54,000, across the whole backtest.** Unemployment is
revised often -- 1.9% of months -- but almost never by enough to cross a threshold, which
is the only way a revision reaches a forecast. The recession series moves on ten months,
each a full flip, and that is the same phenomenon as D14: dating revised as the committee
announces. D14 is separately fixed (ADR 0011), so those ten are now dated by announcement
rather than read early.

**Why it is not implemented.** `data.panel.load_final_series` takes no `as_of` and calls
`build_request(series_id)` with no vintage date, and `prepare_indicator_history` calls it
**once** for the whole backtest rather than per refit. Making conditions vintage-aware is
therefore an interface change threading a date down that path and loading thirty-three
times instead of once -- to correct 34 condition-months. The measurement answers the
question; the rebuild is not worth its own risk, and that is now a recorded decision
rather than an assumption.

One trap worth recording, because it nearly went in this entry as a finding: payroll
employment and core prices are revised, are in the registry, and are **not read** by any
indicator. Measured against final data payrolls move in 72% of months, and that number
describes nothing the walk-forward does. The scope that matters is
`indicator_outcomes.required_series_names`, not "every revised series".
**was: evidential** · **narrowed** 2026-09-09 by ADR 0008

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
**closed** 2026-09-21 by the direct test this entry asks for:
`research/derivations/condition_process_order.py` fits the condition process at both
orders on the same months, with the same filtered regime weights and the same
shrinkage, and compares them by log likelihood with a BIC penalty for the extra
parameters. Against the sixteen-regime default, 909 months:

| indicator | first order | second order | dBIC | prefers |
|---|---:|---:|---:|---|
| consumer_price_inflation_above_five_percent_within_horizon | −64.8 | −65.3 | +218.8 | first |
| consumer_price_inflation_above_three_percent_at_horizon | −177.0 | −170.5 | +205.0 | first |
| economy_in_recession_at_horizon_date | −83.0 | −82.1 | +216.2 | first |
| economy_in_recession_within_horizon | −83.0 | −82.1 | +216.2 | first |
| federal_funds_rate_above_four_percent_at_horizon | −58.1 | −57.9 | +215.8 | first |
| federal_funds_rate_below_one_percent_within_horizon | −32.1 | −30.2 | +212.5 | first |
| industrial_production_growth_above_two_percent_at_horizon | −178.7 | −172.7 | +206.0 | first |
| treasury_yield_curve_inverted_within_horizon | −86.3 | −86.5 | +217.4 | first |
| unemployment_rate_above_five_percent_at_horizon | −109.6 | −99.4 | +197.5 | first |
| unemployment_rate_above_seven_percent_within_horizon | −78.4 | −72.0 | +205.0 | first |

Pooled, second order buys 32.1 log-likelihood points for 320 extra parameters, dBIC
+2847.5. **There is no preference for second order at any indicator**, so the
composition does not understate persistence, which is the failure this entry was
watching for. The two recession rows are identical because both indicators resolve off
`recession_indicator` and therefore share one monthly condition series.

Two limits, stated rather than buried. This is an in-sample diagnostic on the final
model's filtered probabilities, which is what the entry asked for -- a direct test of the
assumption -- and not a walk-forward one. And with sixteen regimes the penalty term is
large (32 parameters times log 907, about 218), so the BIC does most of the work; the
raw likelihood gains are small in every case, which is the same conclusion read off the
unpenalised numbers.
**was: evidential**

Equation (2) assumes whether a condition holds depends on last month's condition
and this month's regime, and nothing else. If that fails it shows up as
miscalibration, which the calibration gate tests. But the assumption is testable
directly, and is not tested directly.

**Shape of the fix.** Fit a second-order version of the condition process on the
historical conditions and compare its likelihood to the first-order one. A clear
preference for second order would mean the composition understates persistence.

---

## D7 · Questions phrased relative to today are out of scope
**closed** 2026-09-21 as an accepted limit, by decision rather than by work. This is not
a defect: the exclusion was deliberate at design time, is recorded in the registry and in
decision record 0005, and the reason is structural. A question like "will unemployment
rise two points from where it is now" is a function of today's level as well as the
regime, so it does not compose through the transition matrix at all.

The fix this entry describes -- modelling the conditional distribution of each level given
the regime, rather than the probability of an event -- is a substantially larger model
that would need its own justification and its own experiment. Recording that as a closed
scope decision is honest; leaving it open implies work is pending that nobody intends to
do under this design. Reopening it is the owner's call and would start as a new
pre-registered experiment, not as a debt.
**was: scope**

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
**closed** 2026-09-21 as an accepted limit, by decision rather than by work, with the
claim it constrains restated so no later reader has to reconstruct it.

The bound on the information horizon follows from the arithmetic of a transition matrix's
second eigenvalue and is general for methods of this shape. The *value* -- roughly five
years on this sample -- is measured once, on United States post-war data, and nothing here
establishes it for another economy. Every published number is therefore a statement about
this economy under this method, and is written that way.

The fix, repeating on two or three economies with long monthly histories, stays available
and is mostly configuration because the data layer is registry-driven. It is a new
experiment rather than a repair, and it belongs to whoever wants that generalisation.
Left open, this entry implies a repair nobody is planning; closed, it is what it actually
is: the sample the conclusions are about.
**was: scope**

Everything is United States post-war. Whether the second eigenvalue is similar in
other economies, and therefore whether the information horizon is a property of
this economy or of regime models generally, is untested. The paper claims the
bound is general for methods of this shape, which follows from the arithmetic, but
the *value* of the horizon is measured once.

**Shape of the fix.** Repeat on two or three other economies with long monthly
histories. The data layer is registry-driven, so this is mostly configuration.

---

## D9 · The diagonal-covariance fallback exists but has never run
**closed** 2026-09-20 by deletion. `covariance_type="diagonal"` was reachable only by
passing the argument explicitly, and no caller anywhere -- source, suite, scripts or
research -- ever did. Both branches and the parameter that carried them are gone. The
model keeps its `covariance_type` field and `from_dictionary` still defaults it, so every
cached fit written before this still loads. Removing untaken generality is the resolution
this entry itself proposed; the alternative was to exercise a path nothing asks for.
**was: evidential**

`GaussianHiddenMarkovModel` supports a diagonal covariance type as a fallback for
unstable fits at small state counts, and nothing has ever selected it. Untested
code paths in a fitting routine are where surprises live.

**Shape of the fix.** Either exercise it in the sweep and report whether it
changes the choice, or delete it as speculative generality. Deleting is
defensible: the full covariance has been stable across 55 refits and six state
counts.

---

## D10 · No single place to see everything the pipeline generated
**closed** 2026-09-21 by `forecast artifacts`, the command this entry proposes: every
generated file in one table with its size, its age and the command that wrote it,
across all four places output lands -- the artifact store, `submission/`, `baselines/`
and `artifacts/`.

Three things came out of building it rather than describing it:

- **The artifact-to-command map is read off the call sites, not guessed**, and a check
  holds it against `ArtifactNames` in both directions. A name declared but unattributed
  would print a blank writer; a name attributed but undeclared would print as missing
  forever. Both are silent failures, so both are asserted.
- **`run_manifest` was deleted.** It was declared in `ArtifactNames` and written nowhere
  and read nowhere, in `src`, `scripts` or the notebooks. This command would have listed
  a file the pipeline cannot produce. The removal is recorded in `run_settings.py` beside
  where it was, with the condition for re-adding it: bring its writer in the same change.
- **This entry's own description was out of date.** It says `artifacts/<date>/` holds
  rendered pages. It holds one graph view written by `scripts/graph_view.py`; no pipeline
  command writes there. The command says what is actually there.

Building it also removed a duplication it would otherwise have tripled: the text-table
formatter existed byte-identically in `regression_baseline.py` and `look_ahead_audit.py`.
Both now use one `reporting.tables.text_table`, so the output is unchanged by
construction.
**was: ergonomic** · raised 2026-09-09 by Jeddy

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
**closed** 2026-09-20. The notebook now asks `measure_mixing` for every month to twenty
years instead of five sampled points, and `plot_mixing` drops its per-point markers once
the curve is dense, because a marker reads as "measured here". The reported information
horizon moves from 120 to 121 months: the sampled version could only ever name one of
12, 24, 60, 120 or 240, so its answer was the grid, not the crossing.
**was: ergonomic**

The notebook computes the distance at 12, 24, 60, 120 and 240 months and connects
them, so three quarters of the width is flat tail and the interesting decay is
compressed into the left edge. The version in the report computes all 240 months
and reads as the smooth decay it is.

**Shape of the fix.** Compute the dense curve in the notebook too, or cut the axis
at fifteen years.


---

## D12 · The indicator thresholds were chosen by someone who knew the sample
**closed** 2026-09-21 by recorded decision, which is what this entry itself proposes:
"nothing to fix retrospectively; the choice is made". Moving a threshold now would be
strictly worse than leaving it, because it would be moved by someone who has since seen
every backtest, and the percentile table below is the evidence that the original choice
was not tuned: the thresholds spread from the 11th to the 79th percentile, which is not
what tuning for a balanced base rate produces.

What stays true, and is the cost being accepted: the decision rule can say it was fixed
independently of the data and the indicator set cannot. That limitation is recorded here
and in the results pages rather than repaired.

The forward half of the fix is the part that binds: any future indicator set is
registered before anyone looks at how often each condition holds, the way
`proving/experiments/0001` registers the decision rule. Nothing enforces that yet -- it
is a rule, not a check -- and making it one is the natural next step if another set is
ever added.
**was: evidential** · found 2026-09-09 during the look-ahead audit

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
**closed** 2026-09-21 by ADR 0011, taking the second of the two options below:
availability by turning point, from a dated table of the eight announcements since
1990. A recession value is now published at the later of its constant-lag date and
the announcement that settled its phase, in the pipeline and, by its own separate
implementation, in the audit. Measured against `baselines/a4-pre-d14`, so A4's
adoption is not folded in: 57 MOVED fields, all on the two recession indicators,
and paired skill of −0.0071 at one year (90% [−0.0165, −0.0009]), +0.0002 at five,
+0.0049 at ten. One-year skill falls and the interval excludes zero, which is the
right sign — some of it was earned on post-trough codings nobody could have read.
No verdict changed. Eighteen forecast dates moved rather than the 8 predicted
below; ADR 0011 accounts for all of them (8 same-date, 3 benchmark-only, 7 carried
by the 2003-03 refit). The first attempt at this fix introduced a worse leak by
letting the announcement replace the lag rather than delay it, and
`forecast audit-look-ahead` caught it at 400 moved rows; that is recorded in the
ADR and pinned by three tests.
**was: evidential** · found 2026-09-15 by the independent look-ahead review of arm A5;
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
The invariance audit could not see it while it perturbed by the registered lag, and
its record said so. It now applies the same announcement rule as the pipeline, by a
separate implementation, and the two are held side by side by a test.

The measurement in ADR 0011 found 18 forecast dates rather than these 8. The table
above is not wrong: it enumerates outcome resolution, and the other ten dates come
from the expanding benchmark (3) and from a refit inside the divergence window
carrying its rates forward (7).

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

---

## D15 · The look-ahead audit chooses the state count its own way
**closed** 2026-09-20. `backtest.state_count_on_burn_in.state_count_for_the_backtest` is
now the only place the question is answered, and both the command-line interface and
`look_ahead_audit` call it. A configuration that decides its count anywhere but the sweep
is therefore audited with the count it will actually run. A caller that cannot read
`selected_model.json` -- the audit, which refits everything from scratch by design -- gets
a refusal rather than a guess.
**was: evidential** · found 2026-09-15 by the author of research arm A2

`look_ahead_audit.py`'s `_run_from_scratch` picks the number of regimes by calling
`choose_state_count_on_burn_in_window` directly, then fits with that choice. The
backtest decides the count one layer up, in
`command_line_interface._state_count_for_the_backtest`. For main the two always
agree. But a change that decides the count in the second place and not the first
gets its audit run with main's count, not its own.

Research arm A2 is the case. It fixes four states in that upper function, and turns
on quadrant seeding only when there are four. Its audit reported "6 regimes chosen on
the burn-in window" and never ran the seeding code. It was the only arm affected:
- A3 and A4 changed the sweep itself, and their audits report 4 and 16 regimes.
- A1, A5 and A6 leave the count alone.

A2's leak defence therefore rests on its independent review.

**What it would change.** Nothing on main. What it costs is the meaning of "the audit
passed" for any change to how the count is chosen, and it costs it silently, which
is the failure the audit exists to prevent.

**Shape of the fix.** One function in the backtest layer decides the backtest's state
count, and both the command-line interface and the audit call it. A test builds a
configuration whose count differs from the sweep's, and asserts that the audit fits
with the backtest's count.

---

## D16 · Seven modules import across the layer table, and nothing fails
**structural** · found 2026-09-21 while giving `forecast artifacts` a home

The package docstring declares a layer order and says dependencies point one way
only. `scripts/layer_check.py` reads that table as the specification and reports
where the imports disagree with it. Seven do:

| module | imports | the table allows |
|---|---|---|
| `data/audit.py:30` | features | configuration |
| `data/indicator_outcomes.py:31` | features | configuration |
| `data/panel.py:32` | features | configuration |
| `evaluation/verdict.py:40` | configuration | nothing |
| `features/observation_matrix.py:31` | data | configuration |
| `reporting/tables.py:20` | configuration | evaluation, models |
| `reporting/tables.py:24` | features | evaluation, models |

All seven pre-date this session; none was introduced by the `text_table` move, which
only added a function with no imports of its own. The root-level orchestration modules
(`command_line_interface`, `look_ahead_audit`, `regression_baseline`, `pipeline_gates`,
`forecast_register`) are exempt by the checker's own design and are not at issue.

**What it costs.** Not correctness: nothing here is a cycle, and the suite, the gates
and the audit all pass. What it costs is the docstring's standing as a specification. A
reader who takes the table literally will be wrong about this package seven times, and
the layer rule is one of the few architectural claims the project makes about itself.

**Why it is not fixed here.** `layer_check.py` exits 0, so this has never blocked
anything, and the fix is a judgement the owner should make rather than a repair: either
the imports move, which is real surgery in `data` and `features`, or the table is
rewritten to describe the package as it is. The checker states the choice exactly --
"the table is the specification, so decide which one is the defect" -- and it is the
kind of decision that should be made once, deliberately, not absorbed into an unrelated
change.

**Shape of the fix.** Decide which side is wrong. Then, whichever way it goes, make the
check enforceable: `scripts/layer_check.py` exits 0 today whatever it finds, so nothing
stops the count going from seven to eight.
