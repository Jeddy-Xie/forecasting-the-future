# Look-ahead review: direct-horizon-rates (A5, experiment 0002)

Independent judged review, the second half of 0002's VOID rule. The reviewer did not write this
arm. Written 2026-09-15.

- **Change reviewed:** `git diff 2e025b7...research/direct-horizon-rates`, at branch head `02581dc`.
  Implementation commit `0136e6f`; run outputs `3919f08`.
- **Method:** reading the diff, then re-deriving the arm's outputs. Every script ran against a
  scratch copy of the arm's `.cache/raw` and `.cache/vintage`, with the branch's `src/` on
  `PYTHONPATH`. The arm's branch and worktree were not modified.

## direct-horizon-rates
VERDICT: CLEAN

The change adds no path by which information from after a forecast date reaches that forecast.
The strongest evidence is a full recomputation. For every probability the arm issued, I rebuilt
it from the pre-registered formula. The admitted outcome set was decided by my own date
arithmetic (`dateutil.relativedelta` plus `timedelta`), not by the arm's function.
- **Backtest:** all 11,730 predicted probabilities reproduce **exactly** (max abs difference 0.0),
  and so do all 391 `regime_distribution` strings.
- **Live forecast:** all 30 cells of today's grid reproduce exactly.

One real look-ahead turned up. It is **pre-existing, in the shared registry, and identical on
main**, so it does not bear on this arm's verdict. It is recorded at the end, under "Outside this
arm", because the deterministic audit cannot see it by design.

### 1. Deterministic audit: passed

- **Exit code:** `exit_codes.json` records `"look_ahead_audit_exit": 0` at commit `0136e6f`.
- **Result:** `look_ahead_audit.txt` gives PASS at cutoff 2000-03-01. 2190 rows were compared and
  0 moved. 7 refits ran from scratch in each run, and 627617 values were perturbed across 1348
  cache entries.
- **The audit ran on the direct path.** The audit record `.cache/models/look_ahead_audit.json` in
  the worktree carries `"configuration_hash": "224dc4027b23b1c7"`. That is the arm's setting-on
  digest, not main's `ad7fcc1affd0746a`.
- **The audit can see this boundary.** `tests/test_direct_horizon_rates_look_ahead.py:84-108`
  injects two off-by-ones: the lag forgotten, and the horizon one month short. The audit exits 1
  on each and 0 on the honest code (`:111-122`).

### 2. Every value the change introduces, traced to its inputs

The admission rule at refit date t: an outcome is admitted when P ≤ t, where P is the day it was
published, (s + h months) + the indicator's lag.

| quantity | computed at | inputs | latest observation it can touch | enforced by |
|---|---|---|---|---|
| admitted outcomes y_{s,h} | refit date t | final-vintage resolution series | label s + h, published P = (s + h months) + lag days | P ≤ t: `published.searchsorted(as_of, side="right")`, `backtest/walk_forward.py:220-223` |
| which label decides an outcome | (definition) | `data/indicator_outcomes.py:62-77, 101-111` | at-horizon: label s + h (`shift(-h)`). Within-horizon: labels s+1 … s+h (reversed rolling window, then `shift(-1)`). The last label is always s + h | the boundary uses exactly s + h (`walk_forward.py:220`) |
| lag per indicator | (definition) | registry | the resolution series' lag; for the derived yield-curve spread, the max over its components | `walk_forward.py:156-164` |
| gamma_s (regime weights) | refit date t | model fitted on the panel assembled `as_of` t (`walk_forward.py:295-297`) | panel rows labelled ≤ s | **filtered**: `model.filtered_state_probabilities`, `walk_forward.py:324-325`. Every admitted s satisfies s + h + lag ≤ t, so row s is in the t panel |
| pooled rate, shrinkage | refit date t | admitted outcomes only | as above | `indicator_forecast.py:322-326` (`_shrink`, strength `settings.conditional_rate_shrinkage_strength`) |
| today's distribution | forecast date f | refit model applied to the panel `as_of` f | panel as of f | filtered, `[-1]`, `walk_forward.py:418-421`. Refit ≤ f by construction (`:410-413`) and true on all 11,730 rows |
| the forecast | forecast date f | today's distribution · rate | as above | `compose_direct_horizon`, `indicator_forecast.py:401-414`, used at `:436-446` |

**The boundary, stated explicitly.**
- `searchsorted(..., side="right")` counts publication dates **≤** the as-of date. The comparison
  is `<=`: an outcome published on t itself counts; one published on t + 1 day does not.
- Forecast dates ascend (guarded at `walk_forward.py:214-219`), so the admitted outcomes are
  always a prefix, and `outcomes.iloc[:published_count].dropna()` (`:271`) takes exactly that
  prefix.
- Unresolved windows are dropped, never read as zero.

**Re-derived on the real data** (10 indicators × 3 horizons, at all 33 refits 1994-03-01 …
2026-03-01 plus today, 2026-09-15):
- My hand rule and `outcomes_available_at` produce the same admitted set in all 1020 cases: 0
  mismatches.
- For each case, take the last admitted outcome and its publication date P. It is included at P
  and excluded at P − 1 day in **1020 of 1020** cases.
- The latest-published outcome admitted at any refit was published 12 or 13 days before it. It is
  always industrial production, labelled January and published February 17 at a 47-day lag. The
  smallest slack at any as-of date is 9 days, at 2026-09-15.
- The rows of REPORT.md's boundary table that I reproduced all match, for recession dating,
  unemployment, consumer prices, the funds rate and industrial production, as of 1994-03-01 and
  2000-03-01. Example: recession, 12 months, as of 1994-03-01: last s = 1992-01-01, published
  1994-02-05.

### 3. Reported deviation 1, the boundary refactor: confirmed

- **There is exactly one implementation of the outcome-publication boundary:**
  `count_of_outcomes_published_by`, `walk_forward.py:194-224`.
  - Both consumers call it: `_expanding_climatology` (`:242-244`) and `outcomes_available_at`
    (`:263-271`).
  - Grepping `src/` and `scripts/` for `searchsorted`, `DateOffset(months=` and
    `publication_dates(` finds no other *outcome* boundary.
  - The other publication cuts in the repository cut different objects, and the diff leaves them
    unchanged:
    - monthly conditions: `condition_available_at`, `walk_forward.py:274-278`, also `<=`;
    - model inputs: `data/vintage.py:111-122`;
    - the audit's own perturbation rule: `look_ahead_audit.py:227`, which should stay separate
      from the thing it checks.
- **The new function body is main's expression verbatim** (2e025b7 `walk_forward.py:194-201`),
  plus a guard that raises on unsorted dates.
- **Byte identity, re-derived rather than read from the report:**
  - *Function level.* I pasted 2e025b7's `_expanding_climatology` verbatim and ran it against the
    branch's on all 30 real (indicator, horizon) outcome series: **30 of 30** have an equal index
    and equal float64 bytes.
  - *Output level.* I compared `climatology_probability` in the arm's
    `.cache/models/backtest_results.parquet` with main's `baselines/main.forecasts.parquet`. All
    11,730 rows join, and the bytes are equal including NaN positions (11,691 non-NaN).
    `realised_outcome` is also byte-equal (9,702 non-NaN).
  - `compare.json` agrees: `climatology_brier_score`, `base_rate`, `resolved_forecasts` and
    `mean_distance_to_stationary` are IDENTICAL in 30 of 30 rows each.

### 4. Reported deviation 2, the test edit: confirmed

- **What changed.** `tests/test_configuration_hash_compatibility.py` has 8 insertions and 0
  deletions in the diff. Two lines are code; the rest are comments:
  - `estimate_each_horizon_rate_directly=False` added to the constructor in
    `test_the_shipped_configuration_hashes_to_the_recorded_digest` (`:39`);
  - `"estimate_each_horizon_rate_directly"` added to the pinned set in
    `test_the_omission_map_holds_only_the_two_documented_switches` (`:123`).
- **Nothing was loosened.** Both assertions are still exact equalities, and no assertion was
  removed or weakened.
- **What the first test now pins.** It pins the digest of an explicitly-off configuration rather
  than of the defaults, which is unavoidable with a default-on field. The off-reproduces-main
  guarantee is pinned separately at `tests/test_direct_horizon_rates.py:511-517`.
- **Nit, not a leak.** The second test's name still says "two documented switches" but now pins
  three. This project names tests for the requirement they pin, so rename it before any merge.

### 5. Reported deviation 3, `forecast_now`: as leak-free as the backtest

- **Same code path as a refit.** `command_line_interface.py:318-341` builds today's rates with
  `walk_forward.fit_regime_model(today, …)`, the same function every walk-forward refit calls.
  Its outcomes are therefore cut by `outcomes_available_at(history, horizon, today)`: published
  on or before today, `<=`.
- **Today's distribution** is `filtered[-1]` over `observation_matrix_as_of(today)` (`:303`,
  `:327`). That matrix ends at 2026-07-01.
- **Re-derived.** The arm's `current_forecasts.parquet` was written at 15:47:11, after the
  implementation commit at 15:44:53. All **30 of 30** cells reproduce exactly from the cached
  today-fit and my hand-cut outcomes. No admitted outcome was published after 2026-09-15; the
  latest recession one is s = 2024-08-01 at 12 months, published 2026-09-05.
- **Pre-existing, not from this arm, and not a leak.**
  - Today's fit uses the state count in `selected_model.json`, which is **5**
    (`model_2026-09-15_states5_…`), while the backtest uses 6, chosen on the burn-in window.
    Main does the same at 2e025b7 (`command_line_interface.py:324`, with a `states5` today-fit
    under main's hash too).
  - The live forecast therefore does not come from the configuration that was backtested. It is
    still point-in-time, because the sweep uses only data available today.

### 6. Hyperparameters, and the number of runs

**Hyperparameters match the registration.**
- The only registered value is `shrinkage_strength: 10`. The code reads
  `settings.conditional_rate_shrinkage_strength` (`walk_forward.py:366`), whose default is 10.0
  (`run_settings.py:94`) and is unchanged by the diff.
- The run digest `224dc4027b23b1c7` equals the branch default's (checked: strength 10.0, direct
  on, horizons (12, 60, 120)).
- The only new setting is the registered switch (`run_settings.py:97`). The pooled rate is the
  plain mean of the admitted outcomes, as registered. No threshold, window or weight was chosen.

**One run.**
- `git log 2e025b7..research/direct-horizon-rates` shows three commits: implementation, outputs,
  report. The worktree reflog has nothing else, and there is no other branch, stash or worktree
  for this arm.
- In the worktree's `.cache/models`, each of the 34 fits under `224dc4027b23b1c7` was written
  **once**, in refit-date order, in two sessions:
  - 2026-09-15 and 1994-03 … 2016-03, at 15:47:11-16:00:30;
  - 2017-03 … 2026-03, at 20:44:47-20:51:27.
- `backtest_results.parquet`, `evaluation_metrics.parquet` and `verdicts.parquet` are all dated
  20:51. That fits one walk-forward interrupted after the 2016 refit and resumed from the model
  cache. No scored output predates 20:51, so no numbers came from an earlier attempt.
- **One oddity, not a finding.** The burn-in state-count file under the arm's hash is dated
  15:41:52, three minutes before the implementation commit, so it came from uncommitted code. The
  burn-in sweep never reads rates, and it chose 6 states, as main does.

### 7. The revised-values channel (D5): no new exposure

The direct rates read the final-vintage resolution series only at labels s+1 … s+h ≤ t − lag
(plus s+h−12 inside the year-over-year transforms). Main's monthly conditional rates already read
the *same* final-vintage series:
- the same `source` object, `walk_forward.py:152, 175`;
- at *every* label ≤ t − lag, via `condition_available_at` (`:274-278`).

So the arm reads a subset of values main already reads, on the same dates. It opens no new D5
channel.

### 8. Smoothed probabilities: not used on any forecast path

- The new path calls only `filtered_state_probabilities` (`walk_forward.py:324, 421`;
  `command_line_interface.py:327`).
- The branch has two calls to `smoothed_state_probabilities`, neither on a forecast path and
  neither touched by the diff:
  - `models/state_labelling.py:173`, `describe_regimes`, which only describes regimes;
  - `models/state_selection.py:222`, the burn-in sweep (ADR 0008).

### 9. The report's numbers, machine-checked

- **`paired.json` against REPORT.md's results table.**
  - All 24 numbers are equal to full precision: for each horizon, main's skill, the arm's skill,
    the difference, both bounds at 90% and at 98.33%, and the independent observations.
  - The usable-resample counts 9953, 7495 and 5443 match.
  - All 30 per-indicator cells match to four decimals, and so do the sign counts: 7 of 10 lose at
    one year, 9 of 10 at five, and 5 of 10 gain at ten.
- **`compare.json`.**
  - The IDENTICAL and MOVED claims hold. `mean_effective_sample_size` is MOVED in 30 of 30 rows.
    `failing_gates` at 12 months moved from `calibration` to `calibration, robustness`.
  - Log loss is higher in the arm in 8, 9 and 5 of 10 indicators at the three horizons.
  - Recession within ten years: Brier skill −2.648516961690255 → 0.016042583153327628; log loss
    0.4604 → 0.1634; calibration error 0.3021 → 0.0320. Funds rate below one percent at ten
    years: log loss 0.6266 → 1.6023. All match the report.
- **`check_gates.log`.**
  - Calibration error 0.1401, 0.2718 and 0.2196; the report's full-precision values round to
    these.
  - Robustness 2 of 4 sub-periods positive at one year.
  - λ2 0.9831 with a 41-month half-life; SHIP BASE RATE at every horizon.
- **Not checked.** The report's figures for main's per-horizon calibration error (0.1249…,
  0.1942…, 0.1156…) appear in none of `paired.json`, `compare.json` or `baselines/main.json`.
  The report says it recomputed them from main's parquet.
- **The verdict is supported.** HARMFUL at one year: the 90% upper bound −0.0586262624083289 is
  below −0.02.

### 10. Why the ten-year point estimate lies outside its own 90% interval

The two causes are properties of the shared instrument, not of this arm. It is a limitation every
arm shares.
- **Reproduced exactly.** Running the shared code on the two forecast files gives the reported
  figures: +0.2647, 90% interval [+0.0459, +0.2526], 5443 usable resamples.
- **The code is shared.** The causes live in `evaluation/bootstrap.py` and
  `evaluation/paired_skill_comparison.py`, which this diff does not touch. Every arm's ten-year
  interval has them.

**Cause 1: the draw under-weights the ends of the sample.** The moving-block bootstrap is
non-circular. With 270 resolved dates and 120-month blocks, block starts are uniform on 0 … 150
(`bootstrap.py:112-122`). Replaying the exact draws, the first and last 30 dates come out about
0.2-0.3 times per resample, and dates 120-150 about 1.8 times. The resamples are centred on a
re-weighted sample, not on the one the point estimate uses.

**Cause 2: many resamples are refused.** A resample is refused whenever any of the 9 fixed-set
indicators has only one outcome class in it (`verdict.py:301-308`, with `_skill_is_defined` at
`:258-262`).
- 4557 of 10000 are refused.
- The biggest reason is unemployment above seven percent: all 57 of its minority outcomes sit in
  the first 57 dates, which the draw rarely reaches. It is refused alone 1757 times, and with the
  funds-rate question 604 times.
- Recession within ten years is next: its 9 zeros sit in 2009-06 … 2010-02. It is refused alone
  1187 times.

**The effect.**
- The kept resamples have median +0.1749, and only 3.9% of them exceed +0.2647.
- Most of the shift comes from two indicators whose sign flips in the kept resamples:
  - inflation above five percent within ten years: +0.0654 on the full sample, kept mean −0.4365;
  - the inverted yield curve: +0.0351 on the full sample, kept mean −0.1934.
- Summed over indicators, (full − kept mean)/9 = +0.0725.

**What it means.** The statistic is a ratio, with about 2.25 independent observations behind it.
A percentile interval that excludes its own point estimate here says the instrument cannot
resolve anything at ten years. It says nothing about the arm. A5's HARMFUL verdict rests on the
one-year interval and is unaffected.

### Minor, not look-ahead

The `composition` column in the arm's results still names the registry's composition, although
the direct path produced every probability (`tests/test_direct_horizon_rates.py:202` pins this).
Anyone slicing the results by composition should know it is a label, not the path taken.

### Outside this arm: a pre-existing look-ahead in the recession publication lag

Recorded because it is real and verified, and because the audit states it cannot see "a registry
publication lag that is itself wrong". This change did not introduce it, does not widen it, and
it does not bear on the verdict above.

- **The lag is short by construction.** USREC's registered lag is 400 days (`economic_series.yaml:155`).
  The registry describes it as "a fair middle" of the six-to-eighteen-month announcement delay.
  A middle value is shorter than the real delay for some turning points.
- **The dates.** NBER announced the November 2001 trough on **17 July 2003** (fetched 2026-09-15
  from nber.org/research/business-cycle-dating/business-cycle-dating-committee-announcements).
  The final USREC file codes 2001-12 and 2002-01 as 0.
- **The gap.** At the 2003-03-01 refit, 2003-03-01 − 400 days = 2002-01-25, so labels through
  2002-01 count as published. Two zero months were therefore used four and a half months before
  anyone knew them: 593 days after the label 2001-12, against the 400 assumed.
- **Exposure in this arm.**
  - At the 2003-03 refit, six recession-at-horizon outcomes rest on those two labels, all 0:
    s = 2000-12 and 2001-01 at 12 months, 1996-12 and 1997-01 at 60, 1991-12 and 1992-01 at 120.
  - They feed the forecasts dated 2003-03-01 … 2003-07-01.
  - Withholding them moves those forecasts by at most 0.0001, 0.0025 and 0.0002 at the three
    horizons.
  - Within-horizon outcomes are unaffected: every window ending on those labels already contains
    2001 recession months.
- **Identical on main.**
  - The same two labels enter main's monthly conditional rates at the same refit, through
    `condition_available_at` with the same 400-day arithmetic.
  - The shared benchmark, byte-identical between the two runs, admits the outcomes resting on
    them from 2003-01-05 and 2003-02-05.
- **No other exposure on this refit schedule.**
  - The March 1991 trough was announced 1992-12-22, before the first refit in 1994.
  - For the June 2009 and April 2020 troughs, the 2010-03 and 2021-03 refits admit labels only up
    to 2009-01 and 2020-01. Those fall inside an announced recession or before an announced peak.
  - Every peak since 1990 was announced within 400 days.
- **Trough announcement delays**, measured from the first expansion month:
  - 1991: 631 days;
  - 2001: 593 days;
  - 2009: 446 days;
  - 2020: 444 days.

  Fixing this needs a longer USREC lag or a lag aware of turning points. That is the owner's
  decision; it is not taken here.
