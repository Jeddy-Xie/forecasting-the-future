# Look-ahead review: arm B2, observe-what-is-forecast (experiment 0008)

I did not write this arm and have no stake in whether it passes. Reviewed 2026-09-29 under
`research/process/lookahead-review-brief-0008.md`.

- **Change reviewed:** `git diff 99f232d...research/observe-what-is-forecast`. The branch head is 2433c5f.
  - The code and tests are in 98b103f.
  - 4bf1abd, 85e301d and 2433c5f add only files under `research/arms/observe-what-is-forecast/`. `git show --name-only` lists no other path for any of the three.
  - The arm touches nothing under `proving/`, `baselines/` or `docs/`.
- **Files:** in `src/…` and `tests/…` paths below, line numbers are on the branch.
- **Scope of my own work:**
  - I modified nothing in the arm's branch, worktree or cache.
  - Scripts live in the session scratchpad. Each ran against a `git archive` export of the branch, with `PYTHONPATH` at the export's `src/`; the import resolved inside the export.
  - Each ran on a scratch copy of the arm's cache.

## observe-what-is-forecast
VERDICT: CLEAN

I found no way for information from after a forecast date to reach that forecast, and no class-B path that this change opens.

**The two new inputs are exactly point-in-time:**
- **The unemployment rate** is read from the archival vintage dated each forecast date, at all 391 dates. No vintage holds a label on or after its date.
- **The term spread** is a difference of two market series that are never revised, each censored at 32 days. On a first-of-month forecast date that lag never reads a month early.

**Nothing else is new.** The change adds no read of a final-data file into any forecast, and no publication-dating logic. The deterministic audit perturbs exactly these new inputs (UNRATE's vintages and current file, GS10's current file) and passed at both cutoffs.

**For completeness, main's standing approximations** — the per-regime rates' final-data conditions (D5), the recession boundary (D14-class) and today's condition reads — reach this arm's forecasts as they reach the reference's.
- Correcting them in real time in **both** runs moves the one-year difference from −0.008794 to −0.009498, a shift of −0.000703.
- No verdict moves: not PROMISING, and HARMFUL at ten years (90% upper bound −0.0503).

The arm's own verdict, HARMFUL, therefore stands on inputs free of look-ahead.

### 1. Deterministic audits: passed. What they cover, and what they do not

`exit_codes.json` records, at commit 4bf1abd (whose code is 98b103f): both audits exit 0, and `tree_clean_at_start_and_end: true`.

| cutoff | forecast dates | refits | rows compared | perturbed | run time |
|---|---|---|---|---|---|
| 2000-03-01 | 73 | 7 | 2,190, all identical | 1,038 vintages dated after the cutoff, UNRATE's among them; 9 current files; 951,951 values | 329 s |
| 2022-03-01 | 337 | 29 | 10,110, all identical | 187 vintages; 12 current files; 198,500 values | 1,241 s |

- **What they cover:**
  - In both runs the burn-in choice (9 = 3x3) and every fit are recomputed from scratch.
  - The perturbation reaches UNRATE's vintages and current file (36 days) and GS10's current file (32 days). `copy_series_cache` perturbs every cache entry, not only model inputs.
  - The 206 WARNING lines are CPI vintage fallbacks from the honest-start scan, all dated 1994-02-01 or earlier.
- **What they do not cover:**
  - Revised values: none are new here. UNRATE comes from vintages, and the spread's legs are unrevised.
  - A wrong registry lag: the UNRATE input uses none, and the 32-day lag is conservative on these dates.
  - Information published between a forecast date and the cutoff. I closed that for the new input directly (section 2).
  - The 54 dates after 2022-03-01, and today's grid.

### 2. Every value the change introduces, traced to its inputs

| input | read as of | publication timing | outcome? | filtered? |
|---|---|---|---|---|
| UNRATE column | s | `vintage.observe` requests the vintage dated s (`data/panel.py:73-75`, unchanged `vintage.py`). The boundary assertion requires label < s. | no | n/a |
| Term-spread column | s | GS10 and TB3MS current files censored at 32 days. The difference is taken on the months both legs cover (`features/observation_matrix.py:151-163`). | no | n/a |
| Growth chain (IP growth, UNRATE) and levels chain (inflation, rates, spread) | each refit t | Columns are assigned by dimension, a fixed rule (`two_timescale_hidden_markov_model.chain_columns`). The fit reads the as-of-t matrix (`walk_forward.py:404`, `:429`). | no | n/a |
| Regime distribution at s | s | as-of-s panel through the configured registry (`walk_forward.py:522`) | no | **filtered**, `:559`. The diff contains no `smoothed` call. |
| State count (3x3) | once, as of 1994-03-01 | Panel 1956-03-01..1994-01-01. Strict `panel_end < first_forecast_date` (`state_count_on_burn_in.py:253-255`), registry configured at `:244`. | no | n/a |

My direct check of the UNRATE input (scratchpad `b2_unrate_vintages.py`) covered all 391 forecast-date vintages:
- **Every one is cached.** The shortest has 553 months (1948-01..).
- **The vintages are genuine.** 383 of them differ from the final file somewhere.
- **The last label is never on or after the date.** It is s−2 on 362 dates and s−3 on 2 (the 2025 shutdown). It is s−1 on 27, and every one of those 27 is a Friday the 1st, when the Employment Situation was released that morning. That is inclusive publication, the same convention as `censor_by_publication_lag`. The matrix drops that month anyway, because it aligns on its shortest column, which ends at s−2.

**Bridging.** A single-month hole (October 2025) is interpolated only between two observed values, both published by s. It never extrapolates.

**Standardisation.** The expanding window is unchanged. Because GS10 begins in 1953-04, alignment starts there and the first standardised row is 1956-03, not 1950-12. This is disclosed by the arm and pinned by a test.

**Rates, outcomes and benchmarks.** None of that code changed.
- Outcomes and the series-start benchmark are identical to reference-0008 on every row.
- R1 and R2 differ from the reference's, because both start at the arm's own first matrix row, 1956-03, as rule 0007 defines them. That is a comparability matter, which the arm reports and re-scores, not a leak.

**My replay reproduces the scored run exactly.** On the arm's cached fits, the replay equals `backtest_results.parquet` on every column. My paired statistic reproduces `paired.json`: −0.00879438891023196.

### 3. Class-B paths

None is opened by this change. Main's standing approximations reach these forecasts through the unchanged rate estimator and today's condition reads, as they reach the reference's.

I measured them anyway, because arms B1 and B3 required it and the same comparison should be available for all three (scratchpad `measure.py`, variant `rec+vincons+refits`). Every condition was read as an observer had it, in both runs:
- revised series from the vintage dated each date, at forecast dates and refits;
- recession months awaiting an announcement coded provisionally, not withheld.

| horizon | as scored | corrected (both runs) | 90% corrected |
|---|---:|---:|---|
| 12 | −0.008794 | −0.009498 | [−0.042391, +0.024478] |
| 60 | −0.011614 | −0.012229 | [−0.031122, +0.020233] |
| 120 | −0.117629 | −0.118975 | [−0.162929, −0.050343] |

The shift is under 0.001 at one year. The 0001 verdicts are unchanged: SHIP BASE RATE at every horizon, the one-year failing only calibration. The registered reading is unchanged: not PROMISING, and HARMFUL at 120.

### 4. The look-ahead audit table, row by row

| row | touched? | for B2 |
|---|---|---|
| Training panel assembly | yes | Clean. Two more series; UNRATE archival at all 391 dates; 0 fallback dates. |
| Standardisation window | yes | Clean. The same expanding function, with alignment from 1953-04. |
| State probabilities used in forecasts | no | Filtered only. |
| Model parameters at each refit | shape | Clean. Refitted from scratch on the as-of-t panel. |
| Number of regimes | input | Clean. 3x3, once, panel ending 1994-01-01. |
| Conditional rates | no | Clean except D14, as on main. |
| Benchmark | indirectly | R1 and R2 follow the arm's sample start. Series-start is identical. |
| Outcome resolution | no | Unchanged. |
| Condition values feeding rate estimation | no | D5 as on main. The new inputs are not conditions. |
| Every run setting | yes | One a-priori boolean. |
| Acceptance thresholds | no | Nothing under `proving/` changed. |
| Canonicalisation | yes | A fixed sort. Growth and inflation stay columns 0 and 1. |
| Indicator thresholds | no | D12. |
| Future-perturbation invariance | run | Passes at both cutoffs, with the new inputs inside the perturbation. |

### 5. Did the arm do what it registered, no more and no less? Yes

**The registered change.**
- UNRATE as a level from vintages, standardised like every column, in the growth chain.
- GS10 minus TB3MS, unrevised, at 32 days, in the levels chain.
- Counts chosen per chain from candidates 1..4 on the burn-in window.
- Seed, shrinkage and the 240-month floor unchanged.

**One scored run.** The cache holds one burn-in choice and 33 refit fits (`states3x3`) under 0f6dc425a85b4a22, plus today's fit.

**honest_start.** 1994-03-01 is retained, and 0 of 391 dates fall back. My vintage check above agrees.

**off_reproduces_main.** The arm's off run reports 387 IDENTICAL. That run read main's fits and burn-in choice from the cache, where they sit under the same hash, copied at setup and never rewritten. So it did not exercise fitting with the setting off. I closed that gap:
- Refitting 1994-03-01 and 2026-03-01 from scratch with the setting off, into an empty store, writes JSON byte-identical to main's cached fits (scratchpad `b2_off_fit.py`).
- My replay with the setting off reproduces `reference-0008.forecasts.parquet` on all 9 columns.

**Beyond the registration, all disclosed:**
- The sample start moves to 1956-03. This is unavoidable under the unchanged alignment rule once GS10 is a column.
- Label wording generalises to the new columns (narrative only).
- The registry refuses the setting with one chain.

Only the sample start reaches a forecast.

**Tests.** Edits to three existing files only name the switch off, or add a set member:
- `test_configuration_hash_compatibility.py`
- `test_two_timescale_chains.py`
- `test_honest_start_date_against_the_live_cache.py`

No assertion was removed or loosened.

### Separate observation, outside the verdict

Today's sweep on today's panel chose 4x4 (`model_2026-09-29_states4x4_…_0f6dc425a85b4a22`), while the backtest's burn-in choice is 3x3. So the grid B2 would submit is not the structure it backtested. Main also re-sweeps on today's panel, but there both give 4x4. This is not look-ahead, and it matters only if B2 were adopted, which HARMFUL rules out.
