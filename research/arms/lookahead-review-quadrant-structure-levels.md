# Independent look-ahead review, experiment 0002

Independent reviewer. I did not write this arm and have no stake in it. Reviewed 2026-09-15, 21:59-22:15 JST.
Code reviewed: `git diff main...research/quadrant-structure-levels` at `f4d9734` (the scored commit).
Outputs reviewed: the worktree's `research/arms/quadrant-structure-levels/`, which `4c840de` commits byte-identically (I compared all seven files with `cmp`).
Paths below are relative to `src/economic_regime_forecasting/` at `f4d9734` unless stated.
I did not modify the branch or the worktree. Every execution used `git archive` copies and cache copies in the session scratchpad (`.../scratchpad/a2review/`). I spawned no subagents.

## quadrant-structure-levels
VERDICT: CLEAN

I found no path by which information from after a forecast date reaches that forecast, in the walk-forward or in `forecast_now`. There is one material caveat about the evidence, which the orchestrator must weigh. **The registered deterministic audit (check a) never exercised this arm's code.** Its exit 0 certifies a 6-state, furthest-point-seeded model, not A2's. I therefore ran the same audit forced onto A2's actual 4-state, quadrant-seeded path, plus a perturbation check of my own at five later cutoffs up to and including today's fit. Every one came out byte-identical. Section 1 gives the details.

### 1. The deterministic audit: what it did and did not exercise
- **The claim in the author's REPORT.md is true.** `look_ahead_audit.py:404` calls `choose_state_count_on_burn_in_window` directly, and `:416` passes `choice.state_count` (the burn-in sweep's recommendation, 6) to `run_walk_forward`. It never goes through `command_line_interface.py:460-475` (`_state_count_for_the_backtest`), where A2 fixes K = 4. In `backtest/walk_forward.py:247-249`, quadrant seeding is on only when `state_count == 4`. So in both audit runs, `_seed_means_by_quadrant_centroids` was never called.
- **The recorded evidence agrees.** Worktree `.cache/models/look_ahead_audit.json` shows `runs.original.state_count_chosen_on_the_burn_in_window: 6`, and `look_ahead_audit.txt` reads "original 6 regimes chosen on the burn-in window, 7 fits computed from scratch".
- **What the recorded exit 0 does prove:** the shared point-in-time panel, vintage, conditional-rate and climatology machinery is leak-free up to 2000-03-01, under this branch's settings and hash `9632ee1193541d34`. It does not prove anything about the seeding code or K = 4.
- **The gap belongs to the audit tool, not to this arm.** The arm's diff does not touch `look_ahead_audit.py`. Any arm that changes which K is used for forecasting would have the same blind spot.
- **Reviewer re-run 1: the same audit, forced onto A2's path** (`scratchpad/a2review/audit4.py`, log `audit4.log`).
  - I ran the unmodified `forecast --as-of 2026-09-15 audit-look-ahead` on a `git archive` of `f4d9734`.
  - The only change was that `look_ahead_audit.choose_state_count_on_burn_in_window` was wrapped to return the sweep's own choice with `state_count` replaced by 4. That is exactly what `_state_count_for_the_backtest` does.
  - I also counted every call to `hidden_markov.fit`.
  - Result: both runs report "4 regimes ..., 7 fits computed from scratch, 2190 rows". There were 14 quadrant-seeded fits (7 refits in each of 2 runs) and 12 furthest-point fits (the burn-in sweep's K = 1..6 in each run).
  - "PASS: no forecast issued on or before 2000-03-01 changed ...", exit 0, 247 s, 627,617 values perturbed across 1,348 entries.
- **Reviewer re-run 2: a perturbation check past the audit's window, and of today's fit** (`perturb_k4.py`, log `perturb_k4.log`).
  - For each cutoff C in {2005-03-01, 2010-03-01, 2015-03-01, 2020-03-01, 2026-03-01, 2026-09-15}, I built a cache copy with the audit's own `copy_series_cache(..., cutoff=C, publication_lag_days_by_series=registry lags)`.
  - At every refit date on or before C, I required the observation matrix and the quadrant centroids to be byte-identical between the original and perturbed caches.
  - At C itself, I ran the full `walk_forward.fit_regime_model(C, ..., state_count=4)`, which is the function both the backtest and `forecast_now` call. I required the fitted model, the filtered probabilities and the conditional rates to be byte-identical.
  - Results: every cutoff byte-identical. The first figure is the values perturbed; "refits <= C" counts the refit dates whose matrix and centroids matched.

| cutoff C | values perturbed | refits <= C | full K = 4 fit at C: model, filtered, rates |
|---|---|---|---|
| 2005-03-01 | 526,208 | 12 | identical, identical, identical |
| 2010-03-01 | 419,072 | 17 | identical, identical, identical |
| 2015-03-01 | 303,872 | 22 | identical, identical, identical |
| 2020-03-01 | 178,883 | 27 | identical, identical, identical |
| 2026-03-01 | 22,503 | 33 | identical, identical, identical |
| 2026-09-15 (today's fit) | 12 | 34 | identical, identical, identical |

  The today cutoff is weak by construction. Only 12 cached values were still unpublished on 2026-09-15, so it proves little beyond the lag censoring of the newest rows. The 2026-03-01 cutoff exercises nearly the same code on a 22,503-value perturbation.
- **Consequence for the decision rule.** Check (a) as recorded is vacuous for A2. Whether my forced re-run counts in its place is for the orchestrator or Jeddy to rule, not me. My verdict is check (b), and it rests on sections 2-9 as well as on these two executions.

### 2. The growth-by-inflation boundaries (brief item 1)
- **Function:** `models/gaussian_hidden_markov_model.py:561`, `_seed_means_by_quadrant_centroids`.
- **Window:** an expanding median with `min_periods=1` over the rows of the panel being fitted, including the current row (`:592-593`).
- **Boundary:** `>=`, so a month equal to its running median is "high" (`:594-595`).
- **Centroids:** each is the mean of all three columns over the quadrant's months (`:611`). Rates play no part in the assignment.
- **Wiring:** it is called once per fit (`:433`), and the same array seeds every restart (`:505`). Its input is `matrix.values` of `build_observation_matrix(assemble_point_in_time_panel(registry, as_of, cache))` (`backtest/walk_forward.py:228-230`). The columns are growth, inflation and rates (`features/observation_matrix.py:34-38`), which are INDPRO (lag 47 days), CPIAUCSL (44) and TB3MS (32).
- **No full-sample or panel-wide median exists anywhere in the change.** Every `median` in `git diff main...research/quadrant-structure-levels -- src/` is either docstring text or the two expanding calls at `:592-593`. No numeric threshold is written down. The only constants are K = 4 (registered, `command_line_interface.py:84`) and `min_periods=1`.
- **Independent recomputation** (`centroids.py`). I used a plain Python loop of `np.median(x[:i+1])`, without pandas, on the as-of panel:

| as of | panel | months per quadrant (G+I+, G+I-, G-I+, G-I-) | arm's centroids vs mine | a panel-wide median would give |
|---|---|---|---|---|
| 1994-03-01 | 518 months, 1950-12 .. 1994-01 | 131, 99, 185, 103 | bit-identical (max abs diff 0.0) | different centroids (max diff 0.466); 123 of 518 months relabelled |
| 2026-09-15 (today's fit) | 908 months, 1950-12 .. 2026-07 | 151, 226, 245, 286 | bit-identical (0.0) | different (max diff 0.264); 207 of 908 relabelled |

  1994-03-01 centroids (growth, inflation, rates, standardised): [0.479, 0.497, 1.595], [0.544, -0.368, 0.866], [-0.647, 1.090, 1.870], [-0.551, -0.221, 0.515].
  The label of each month is unchanged when the panel is truncated at that month (checked on 25 sampled prefixes at both dates). So no month's label reads a later month.
- **A note, not a finding.** A centroid averages over every month of the as-of panel in its quadrant, later months included. All of those months were published by the refit date: the last row is 1994-01 at 1994-03-01, and 2026-07 at 2026-09-15. So this is not a look-ahead. Only the assignment boundary is registered as expanding, and it is.

### 3. K = 4 against the sweep (brief item 2)
- **Burn-in sweep.** `backtest/state_count_on_burn_in.py:169` records `sweep.recommended_state_count` (6, chosen as of 1994-03-01 on 1950-12 .. 1994-01; `check_gates.log:375`). Under the flag, `command_line_interface.py:460-475` writes that choice with `state_count_used_for_forecasting: 4` and returns 4, whatever the sweep said (`check_gates.log:376-377`: "fixes the forecasting state count at 4 ... 33 refits, 4 regimes").
  The only other reader of the burn-in choice is `_sweep_the_verdict_should_read` (`command_line_interface.py:547-567`). It reads the sweep table for the regimes-exist gate and nothing else.
- **Full-sample sweep, today.** It recommends 5 (`check_gates.log:33`). Under the flag, `fit_regimes` fits a separate quadrant-seeded 4-state model (`command_line_interface.py:299-311`). `sweep.recommended_model` is read only in the `else` branch (`:318`). `selected_model.json` is written from that separate fit (`:322`): its `means` are 4×3. `pipeline_gates.py:147` reads `recommended_state_count` only for the gate-2 sweep checks.
- **Nothing that fits or forecasts reads either recommendation.** `forecast_now` reads only `selected.state_count` (= 4) from `selected_model.json` (`:360`). `paired.json` `current_run.state_count` is 4.

### 4. The edit to the measuring instrument (brief item 3)
- **Scope of the diff.** `git diff main...research/quadrant-structure-levels --stat` touches exactly one harness file, `regression_baseline.py`, and within it only `_state_count_chosen_as_of` (`:361-399`: docstring, plus `:391` reads `state_count_used_for_forecasting` and falls back to `state_count`, plus the message). `evaluation/bootstrap.py`, `evaluation/paired_skill_comparison.py`, `evaluation/scoring.py`, `evaluation/verdict.py` and the compare/paired functions in `regression_baseline.py` are untouched.
- **It is bookkeeping.** It decides only whether the run summary's `state_count_chosen_as_of` is accepted. It feeds no forecast and no statistic.
- **Main's artifact still passes and a mismatch still raises.** On the branch, the new `test_an_artifact_without_the_new_field_still_passes_when_it_matches`, the new `..._still_raises_on_a_real_mismatch` and the pre-existing, unedited `test_a_burn_in_choice_from_a_different_run_is_refused` all pass.
- **Independent confirmation that the statistic is unchanged.** Calling the paired functions directly (`_resolved_forecasts`, `_matrices`, `paired_mean_skill_difference`, seed 20260908, 10,000 resamples), I reproduce `paired.json` exactly: +0.0380502689801345, [0.01439254036836438, 0.0582969503291242].

### 5. Run history and the cached fits (brief item 4, as corrected by the orchestrator)
- **Timeline** (reflog and file mtimes):
  - `d2df015` was committed at 20:46:23.
  - All 34 A2 fits (`model_*_states4_seed20260908_9632ee1193541d34.json`) were written between 21:03:49 (today's) and 21:13:11, by the first run.
  - `19bd25d` at 21:32:58; `f4d9734` at 21:43:46.
  - The scored run started at 21:46:45 (`revision_audit.parquet` mtime) and wrote no `model_` file, so it read all 34 from cache.
  - `git diff d2df015 f4d9734 --stat` touches only the CLI's burn-in artifact writing, `regression_baseline.py` and tests. The fitting code at the scored commit is therefore the code at `d2df015`. Whether run 1's tree was clean is not recorded, which is why the refit matters.
- **Refit from scratch.** I replayed `check-gates`, `compare` and `compare --paired` (the research_arm.sh commands, `--as-of 2026-09-15`) on a `git archive` of `f4d9734`, with a cache copy minus `.cache/models`: all five gates PASS (exit 0), compare exit 1 (the expected MOVED fields), paired exit 0, 22:01:25-22:14:24.
  - **34 of 34** `model_*_states4_seed20260908_9632ee1193541d34.json` files are **bit-identical** (`cmp`) to the cached files the scored run read (snapshotted from the worktree at 22:02). That covers the 33 walk-forward refits, including 1994-03-01, and today's 2026-09-15 fit.
  - Also bit-identical: `backtest_results.parquet`, `current_forecasts.parquet`, `verdicts.parquet`, `mixing_diagnostics.parquet`, `selected_model.json`, `state_count_sweep.parquet`, `burn_in_state_count_choice.json`, and the cached burn-in choice written at 15:38 by pre-commit code.
  - `run_summary.json` has no differing key.
  - The replayed `paired.json` and `compare.json` are equal to the scored files as parsed JSON.
  - So the scored numbers do not depend on anything the earlier runs left in the cache.
- **No hyperparameter differed between runs.** Every cached fit, the burn-in choice and the scored run carry configuration hash `9632ee1193541d34`. That hash digests every `RunSettings` field except the cache layout (`configuration/run_settings.py:146-168`): seed 20260908, 20 restarts, 500 iterations, tolerance 1e-6, 12-month refits, and both look-ahead switches on. K = 4 is in each file name (`states4`).
- **Voided runs.** Their output files were overwritten by later runs, so I could not inspect them. The scored `paired.json` gives +0.0380502689801345, 90% [+0.01439254, +0.05829695], which is +0.0381 [+0.0144, +0.0583] to four decimals. That is identical to the voided 21:19 run's reported figures, consistent with both having read the same cached fits. The from-scratch replay above is what establishes the scored numbers independently of those caches.

### 6. Tests (brief item 5)
- **Suites.** The branch at `f4d9734`, offline suite in a scratch copy: 487 passed, 10 skipped, 2 failed (499). Main at `9ece691`: 465 passed, 10 skipped, 0 failed (475).
- **No assertion removed or loosened.** `git diff main...research/quadrant-structure-levels -- tests/` contains no removed line at all. `tests/test_regression_baseline.py` gains three tests, `+52/-0`.
- **Both failures are (a): they pin main's behaviour, which this arm is registered to change. Neither is a defect.**
  - `tests/test_configuration_hash_compatibility.py:31-37` builds `RunSettings(select=False, start=False)`. On this branch, the flag's default of True enters the hash, giving `19d1cbe2da54f8c1`. With the flag named `False`, the same call gives the recorded `9f95b12dba40d138`. The branch's default settings with the flag at False give main's `ad7fcc1affd0746a`.
  - `:107-116` pins the omission map at exactly two entries. The arm adds a third at its main-equivalent value (`run_settings.py:174`).

### 7. Every value the change introduces, traced to its inputs
- The four starting centroids come from the as-of standardised matrix, whose inputs are INDPRO, CPIAUCSL and TB3MS, censored by their registry lags in panel assembly (main's code, unchanged). The newest row is always before the refit date (section 2).
- K = 4 is a registered constant.
- The change reads no new series, and does not touch outcome resolution, conditions, conditional rates or climatology. `walk_forward.py`'s diff is confined to `:243-260`. `indicator_forecast.py` and `_expanding_climatology` are untouched, so there is no second implementation of the outcome-resolution boundary.
- Filtered probabilities are used, never smoothed (`walk_forward.py:266`, `command_line_interface.py:363`). The diff adds no smoothed call.

### 8. D5 and D14
- **D5.** No new channel. The arm consumes exactly the observation matrix main consumes, and reads no revised values main did not read.
- **D14.** No new channel: the arm never reads USREC. Nor does it amplify D14 in any way that matters to its result. Recomputing the paired statistic without the 8 D14 forecast dates (2003-02..2003-07, 2010-09, 2021-07), using the harness's own functions:

| horizon | all 391 dates | without the 8 D14 dates |
|---|---|---|
| 12 months | +0.0381, 90% [+0.0144, +0.0583] | +0.0383, 90% [+0.0141, +0.0591] |
| 60 months | +0.0251, 90% [+0.0013, +0.0831] | +0.0254, 90% [+0.0010, +0.0826] |
| 120 months | +0.2202, 90% [+0.1021, +0.2506] | +0.2208, 90% [+0.1043, +0.2440] |

  At 98.33%, one year: with the dates [+0.0054, +0.0690]; without them [+0.0044, +0.0706].

### 9. `forecast_now` and today's fit
- **Same code path as the walk-forward.** `forecast_now` (`command_line_interface.py:336-363`) calls the same `walk_forward.fit_regime_model(today, ..., selected.state_count = 4)` as every walk-forward refit, which seeds by quadrant. Today's centroids are the bit-identical ones in section 2.
- **Checked under perturbation.** Today's fit is byte-identical under the 2026-09-15 perturbation in section 1.
- **Checked against the cache.** The cached today-fit is reproduced from scratch in section 5.

### 10. Headline numbers, extracted by code from `paired.json` and `compare.json`
REPORT.md is present, committed at `4c840de`, and I verified it. Its headline agrees with the files:

| horizon | main | arm | difference | 90% | 98.33% | resolved rows | dates |
|---|---|---|---|---|---|---|---|
| 12 | 0.2154 | 0.2534 | +0.0381 | [+0.0144, +0.0583] | [+0.0054, +0.0690] | 3754 | 378 |
| 60 | 0.0728 | 0.0979 | +0.0251 | [+0.0013, +0.0831] | [-0.0095, +0.1220] | 3274 | 330 |
| 120 | -0.3528 | -0.1325 | +0.2202 | [+0.1021, +0.2506] | [+0.0545, +0.8055] | 2674 | 270 |

- `outcome_disagreements`, `rows_only_in_baseline` and `rows_only_in_this_run` are 0 at every horizon.
- `compare.json` has the verdict `SHIP BASE RATE` IDENTICAL at all three horizons and `state_count` 6 → 4. Its exit 1 is the expected MOVED fields.
- REPORT.md's ECE and log-loss table matches the per-indicator means in `compare.json` to six decimals. For example, at 12 months ECE is 0.159923 → 0.144859 and log loss 0.594038 → 0.561682.
- REPORT.md's gate quotes match `check_gates.log` (lines 60, 360, 381, 387).
- Its arithmetic for the pre-registered rule is correct: the 90% and 98.33% one-year lower bounds are both above 0. Which verdict label follows is for the scorer, not for this review.

### What I could not check
- The voided and contaminated runs' raw outputs, which were overwritten in place. I have only the figures the orchestrator and REPORT.md quote for them.
- Whether run 1's tree was clean when it wrote the cached fits. It is moot: the replay from `f4d9734` reproduces every one of them bit-for-bit.
- D5 and D12 are unchanged main-level approximations, and the arm does not touch them.
