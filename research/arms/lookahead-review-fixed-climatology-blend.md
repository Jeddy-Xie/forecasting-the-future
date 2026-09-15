# Look-ahead review, experiment 0002

Independent judged review, the second half of 0002's VOID rule. I did not write this arm and have no
stake in it passing. Reviewed 2026-09-15.

- **Code reviewed:** `git diff 2e025b7...e3f70e5` (the code commit that ran, 21:39:06 +0900). The branch
  head `c74c96d` (22:05:35) touches only the 8 files under `research/arms/fixed-climatology-blend/`. The
  code diff touches `backtest/walk_forward.py`, `command_line_interface.py`,
  `configuration/run_settings.py` and three test files. It touches nothing under `proving/`,
  `scripts/` or `docs/`.
- **Method:** every computation ran on `git archive` copies of `e3f70e5` and `2e025b7` in the session
  scratchpad, with a copy of the arm's series cache. I did not modify the arm's branch or worktree.
  Line numbers are for `e3f70e5` (`git show e3f70e5:<path>`).
- **REPORT.md:** present. It was committed in `c74c96d`, and I verified it below.

## fixed-climatology-blend
VERDICT: LEAK FOUND

**Summary.** The implementation is faithful and its own new machinery is clean:
- It uses one outcome-publication boundary, not two.
- The live-edge carry-forward never reads past the forecast date and never reaches a scored row.
- Every refit equals main's, parameter for parameter.
- The deterministic audit exited 0, and it did exercise the blend.

The leaks are in the **registered design itself**. The blend routes main's climatology benchmark into the
forecast. That benchmark is built from outcomes resolved on the current-vintage file, under each series'
registered publication lag. `docs/TECHNICAL_DEBT.md`'s audit table calls outcome resolution "clean by
design", because "the forecaster never sees it". In this arm the forecaster does see it. So two known
main-level approximations each gain a channel into the forecast that main's forecast does not have:
- **D14**, the recession lag after a trough (L1 below);
- **D5**, revised values (L2 below).

I measured both. Each moves a forecast by less than 0.005 and the one-year paired difference by less than
0.00024. That is one to four orders of magnitude inside every decision boundary, so **no 0002 verdict for
this arm can move**.

0002's rule (b) requires that the review find "no path by which information from after a forecast date
reaches that forecast". A path exists, so the verdict above is LEAK FOUND. Whether a leak this small, in
a design the pre-registration fixed, should void the arm is the owner's decision. It is not mine.

### L1 · D14 reaches the forecast through a new channel: the climatology half of the blend

- **The channel.** The blend takes `history.climatology_by_horizon[horizon]` (`walk_forward.py:366-375`).
  That series is built at `:172` by `_expanding_climatology`, with the registered 400-day lag for
  recession dating. In main, the same series reaches only `climatology_probability`, the benchmark. Here
  it also reaches `predicted_probability` (`:380`).
- **New, not amplified.** The climatology path reads post-trough labels 2002-02 to 2002-06 before the
  trough was announced. Main's forecast never reads those early. At the 2003-03-01 refit, main's
  conditional rates admit labels only through 2002-01, because 2003-03-01 minus 400 days is 2002-01-25.
  Main's own D14 exposure through the rates is carried here at weight 0.5, which halves it. I did not
  re-measure that part.
- **Method.**
  - I re-implemented the registered rule. It reproduces the pipeline's climatology exactly on all 2,340
    recession-indicator rows (maximum absolute difference 0.0).
  - I then withheld the early-read labels until D14's announcement dates. Those labels are 1991-04 to
    1991-11, 2001-12 to 2002-06, 2009-07 to 2009-08 and 2020-05 to 2020-06. The announcement dates are
    1992-12-22, 2003-07-17, 2010-09-20 and 2021-07-19.
  - An outcome counted as available only once every label in its window was. This is conservative, so it
    gives an upper bound.
- **What moves.** 48 rows move, 46 of them scored. The scored ones fall on exactly D14's 8 scored
  forecast dates: 2003-02 to 2003-07, 2010-09 and 2021-07.

| indicator | horizon | rows moved (scored) | max \|change in climatology\| | max \|change in blended forecast\| |
|---|---:|---:|---:|---:|
| economy_in_recession_at_horizon_date | 12 | 8 (8) | 0.001087 | 0.000544 |
| economy_in_recession_at_horizon_date | 60 | 8 (8) | 0.001112 | 0.000556 |
| economy_in_recession_at_horizon_date | 120 | 8 (7) | 0.001177 | 0.000588 |
| economy_in_recession_within_horizon | 12 | 8 (8) | 0.001664 | **0.000832** |
| economy_in_recession_within_horizon | 60 | 8 (8) | 0.000334 | 0.000167 |
| economy_in_recession_within_horizon | 120 | 8 (7) | 0.000003 | 0.000001 |

The largest single move is `economy_in_recession_within_horizon`, 12 months, forecast date 2003-07-01.
The blended forecast there is 0.281184 as run, and the climatology goes from 0.514221 to 0.512557.

- **Effect on the verdict statistic.** I re-ran the pre-registered paired statistic with the project's
  own functions (`regression_baseline._resolved_forecasts`, `_matrices`,
  `paired_skill_comparison.paired_mean_skill_difference`, seed 20260908, 10,000 resamples). They first
  reproduced `paired.json` to the last digit at every horizon.
  - Correcting only the blend input moves the one-year difference from −0.0208642 to −0.0208640.
  - Correcting the blend input and the benchmark in both runs moves it to −0.0208632.
  - No 90% or 98.33% bound moves by more than 0.000005 at any horizon.

### L2 · D5 (revised values) reaches the forecast through the same new channel

- **What main's forecast reads.** It reads final revised values only as conditions:
  - for the conditional rates, over observation-matrix months, joined on the matrix
    (`walk_forward.py:282`). The matrix's first month is 1950-12-01 at both 1994-03-01 and 2015-03-01, so
    the rates see nothing earlier;
  - and as the single current condition.
- **What this arm's forecast adds.** The climatology averages outcomes resolved from the current-vintage
  file back to each series' start (industrial production from 1919, the consumer price index from 1947,
  unemployment from 1948). It also runs up to each forecast date, rather than to the last refit.
- **Why the audit cannot see it.** It is excluded by design (`look_ahead_audit.py`, `OUT_OF_SCOPE`: "revised
  values of observations already published at the cutoff"). The brief's own rule applies: a change that
  starts reading those values where main did not is a new leak.
- **Method.** For each forecast date, I rebuilt the climatology from the outcomes as they stood on that
  date. The outcome set is the pipeline's own, but each value comes from the archival vintage dated that
  day. My final-data rebuild equals the pipeline column on all 3,513 rows.
  - The cache holds such a vintage at every forecast date for INDPRO and CPIAUCSL (391 of 391 dates).
  - For UNRATE it holds one at only 2 dates.
  - Where a vintage lacked an old label (at most 24 outcomes, INDPRO vintages starting in 1921), I kept
    the final value. The measurement is therefore a slight underestimate.
- **What moves.**
  - `industrial_production_growth_above_two_percent_at_horizon`: 10.6 outcomes flip on average (21 at
    most). The blended forecast moves by up to **0.0047** (120 months, 2009-04-01), 0.0017 on average.
  - `consumer_price_inflation_above_three_percent_at_horizon`: up to 0.0020.
  - `consumer_price_inflation_above_five_percent_within_horizon`: 0.
  - `unemployment_rate_above_five_percent_at_horizon`: up to 0.00067, at the 2 dates that have vintages.
- **Effect on the verdict statistic.** With the as-published climatology in the blend, for the two
  consumer-price indicators and industrial production:
  - the one-year difference goes from −0.020864 to −0.021097;
  - the one-year 90% interval goes from [−0.06966, +0.02963] to [−0.06992, +0.02954];
  - the 98.33% interval goes from [−0.08950, +0.05433] to [−0.08976, +0.05410];
  - the ten-year 90% interval stays entirely above zero, at [+0.1206, +0.3312].

### Why neither leak can move a 0002 verdict

- **PROMISING** needs the one-year 90% lower bound above zero. It is −0.070, and neither leak moves it by
  more than 0.0003.
- **CONFIRMED_IN_SAMPLE** needs the one-year 98.33% lower bound above zero. It is −0.090.
- **HARMFUL** needs a 90% interval entirely below −0.02 at some horizon. The upper bounds are +0.030,
  +0.174 and +0.331.

The verdict stays "none", as the report says.

The leak's origin is the registration's own sentence "p_climatology is the expanding climatology already in
main's results, so the blend knows nothing a forecaster at that date could not"
(`experiment.json`, `arms.A6-fixed-climatology-blend.change`). It is false at the 1e-3 level, for the two
reasons above.

REPORT.md's look-ahead table marks "Benchmark (climatology)" and "Outcome resolution" as clean. It also
calls the audit "a direct end-to-end check that the blend itself introduces no look-ahead". Both claims go
too far: the audit sees neither channel.

### Checked and clean

1. **One boundary, not two.**
   - The blend and the benchmark read the same series (`walk_forward.py:366-368`), and the diff does not
     touch `_expanding_climatology` (`:195-223`).
   - On all 11,691 rows that were not carried forward, `climatology_probability_used_in_blend` equals
     `climatology_probability` exactly.
   - The arm's `climatology_probability` equals main's baseline column on all 11,730 rows, `NaN`
     positions included.
   - The boundary, stated: the outcome for forecast date s at horizon h counts at t if and only if
     (s + h months) + lag days is on or before t. That is `searchsorted(..., side="right")` at `:218`, an
     inclusive comparison. It is the same inclusive comparison the conditions use (`published <= as_of`,
     `:230`).
   - I found no second implementation.
2. **Carry-forward.**
   - It is `climatology.asof(stamp)` at `:444`, reached only when the exact lookup is `NaN` (`:441-443`).
     `asof` returns the last non-`NaN` value at an index on or before `stamp`, never after it.
   - A carried row therefore has an exact benchmark of `NaN`. Scoring drops such rows
     (`evaluation/verdict.py:175`, `:226`; `regression_baseline.py:1480`), so by code no scored row can
     take this path.
   - In the data, 39 rows were carried forward, all on 2026-08-01 or 2026-09-01. None has an outcome.
     There are 9,702 scored rows, and none of them was carried forward.
   - `forecast_now` carried forward on 30 of 30 rows. The values came from labels 2026-07-01 (the
     consumer-price and industrial-production indicators) and 2026-08-01 (the rest), both on or before
     2026-09-15. They are identical to the walk-forward's carried values at 2026-09-01. No climatology
     index entry exists after today.
3. **Nothing else moves.**
   - I compared parameters field by field against main's cache. Means, covariances, transition matrix,
     initial distribution and fit report, including log likelihood, are identical at 1994-03-01,
     2010-03-01 and 2026-03-01 (6 states), and for today's fit at 2026-09-15 (5 states).
   - `model_probability` equals main's `predicted_probability` exactly on all 11,730 rows. The realised
     outcomes are identical.
   - The burn-in state-count choice file is identical to main's.
   - The weight 0.5 is registered, nothing is fitted, and the clip at `:470` binds on 0 rows.
4. **Edited existing tests.** One assertion was **loosened**:
   `tests/test_configuration_hash_compatibility.py:95` is now `isinstance(shipped_value, bool | float)`. It
   was `bool` at `2e025b7:72`.
   - This contradicts REPORT.md's "no assertion was removed or loosened", although the same report later
     says the check was "widened".
   - The loosening is needed to admit the new float entry. The check the test exists for is kept and runs
     for all three keys: the hash must move when a mapped field leaves its shipped value (`:100`).
   - It has no look-ahead consequence.
   - Every other edit extends a fixture's columns (`test_verdict_and_gates.py`,
     `test_walk_forward_backtest.py`) or the pinned membership set.
   - **No existing test fails on the branch.** The full suite with `-m "not network"` exited 0 on a copy
     of `e3f70e5` and on a copy of `2e025b7`. So no failing test is left to classify as either pinning
     main's behaviour or being a real defect.
5. **What the deterministic audit exercised** (the orchestrator's question). It exercised the blend.
   - `look_ahead_audit.py:95` imports the arm's `run_walk_forward`, and `_run_from_scratch` calls it at
     `:411`. The settings come from `command_line_interface.py:1147` (`workspace.settings`, weight 0.5).
   - Each row's `predicted_probability` is the blend (`walk_forward.py:380`), and it is a compared field
     (`look_ahead_audit.py:126`).
   - The audit's JSON records `configuration_hash` `43ab429af4c39560`, the arm's own. It exited 0, with
     2,190 rows identical at cutoff 2000-03-01.
   - It did **not** exercise: forecast dates after 2000-03-01; the carry-forward, which occurs only at
     2026-08 and 2026-09; `forecast_now`; revised values (L2); or a registry lag that is itself wrong (L1).
   - `climatology_probability_used_in_blend` is not compared directly, but any change in it would show in
     `predicted_probability`.
6. **The blend's inputs, checked by hand** at 1998-06-01 (before the audit cutoff) and 2015-06-01 (after
   it), for four indicators at 12 and 60 months.
   - A brute-force climatology equals the value used, as an exact float, in 16 of 16 cases.
   - The last outcome counted was published on or before the forecast date, and the first excluded one
     after it. For example, for unemployment above five percent at 12 months on 1998-06-01: the last
     outcome counted is s = 1997-04, resting on label 1998-04-01, published 1998-05-07. The first
     excluded outcome would have been published 1998-06-06.
   - The blend equals 0.5 × model + 0.5 × climatology exactly.
   - The model inputs were available by each date: INDPRO and CPIAUCSL come from archival vintages dated
     on the forecast date, and TB3MS's last labels (1998-04-01, 2015-04-01) were published by then.
   - `refit_date` is on or before `forecast_date` on every row.
7. **Filtered, never smoothed.** `walk_forward.py:347` and `command_line_interface.py:327` use
   `filtered_state_probabilities`, and the diff contains no "smooth".
8. **The arm ran once.**
   - The reflog shows `e3f70e5` at 21:39:06, then `c74c96d` at 22:05:35, with no reset or amend in
     between.
   - The first artifact of the run, `data_audit.parquet`, is stamped 21:39:13.
   - The 33 refits under hash `43ab429af4c39560` were written in one monotone sequence, 21:41:50 to
     21:54:08. The outputs are stamped 21:54 to 22:00:43.
   - `exit_codes.json` records commit `e3f70e5`, `tree_clean_at_start_and_end: true`, gates 0, compare 1,
     paired 0 and audit 0.
   - The stop commit `c97a7e6` changes only `REPORT.md`.
   - One trace of earlier activity exists. At 15:47, after the stop commit, burn-in state-count choice
     files under hashes `43ab429af4c39560` and `b32134ca7b165f80` were written. Their content is
     identical to main's, and no fit or result came of them.
9. **Headline numbers.**
   - All 25 long numbers in REPORT.md occur verbatim in `paired.json` or `compare.json`.
   - My independent re-run of the paired statistic reproduced `paired.json` exactly. The one-year
     difference is −0.020864164503446414, with a 90% interval of [−0.06965666649548773,
     +0.029634503731571022].
   - The report's derived calibration and log-loss table reproduces from `baselines/main.json` and the
     arm's `evaluation_metrics.parquet`.
10. **Main-level, not this arm's.** `forecast_now` fits with the full-sample sweep's state count (5,
    `command_line_interface.py:324`), while the walk-forward uses 6. That is not a look-ahead for today's
    forecast, and this arm did not change it.

### Could not check

- UNRATE revisions over the whole sample: the cache holds only 2 vintages after 1994.
- D14 through the conditional rates: that channel is main's, shared by both runs, and here carried at
  weight 0.5. I did not re-measure it.
- The trough announcement dates: I took them from D14 (checked at nber.org per that entry) and did not
  re-fetch them.
- REPORT.md's "two pre-existing skips": my copies give 10 skips without a cache and 3 with the series
  cache but no fitted models.
- Which command wrote the 15:47 burn-in files.
