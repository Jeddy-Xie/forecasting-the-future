# Look-ahead review: arm B1, point-in-time-through-the-condition-chain (experiment 0008)

I did not write this arm and have no stake in whether it passes. Reviewed 2026-09-29 under
`research/process/lookahead-review-brief-0008.md`.

- **Change reviewed:** `git diff 99f232d...research/point-in-time-through-the-condition-chain`. The branch head is 65afa32.
  - The code and tests are in 937b331.
  - d775bca, dde0dca and 65afa32 add only files under `research/arms/point-in-time-through-the-condition-chain/`. `git show --name-only` lists no other path for any of the three.
  - The arm touches nothing under `proving/`, `baselines/` or `docs/`.
- **Files:** in `src/…` and `tests/…` paths below, line numbers are on the branch. Output files are cited by their name in the worktree's arm directory.
- **Scope of my own work:**
  - I modified nothing in the arm's branch, worktree or cache.
  - Every script I ran lives in the session scratchpad. Each ran against a `git archive` export of the branch, with `PYTHONPATH` at the export's `src/`; `import economic_regime_forecasting` resolved inside the export.
  - Each ran on a scratch copy of the arm's cache, to which I added the UNRATE archival vintages from a copy of arm B2's cache (598 vintages, one per forecast date).

## point-in-time-through-the-condition-chain
VERDICT: CLASS-B RECORDED-NOT-VOID

**No class-A path.** No observation labelled or published after a forecast date reaches that forecast as a value.

**Two class-B paths, both opened by this change.** I measured the correction of both.
1. **The starting condition is read from final revised data (D5-class).** The model's point-in-time forecasts never read it before this change.
2. **Recession dating's starting month depends on a later announcement (D14-class).** On 11 forecast dates, where the chain starts for recession dating is set by an NBER trough announcement that came after the forecast date. This is ADR 0011's withholding rule. The reference run shares the dependence: its own forecasts move on 51 rows under the same correction.

**The corrected number.** With both paths corrected, B1 minus reference-0008 at one year, on the model-sample benchmark, is **+0.052991110867497**:
- 90% interval [+0.0256003663275935, +0.08472069912457798]; 96.67% interval [+0.017195576529825226, +0.09335483898106295].
- The shift is **−0.000495**, under 0007's floor of 0.001.
- No verdict moves at any level or horizon. It is still PROMISING and CONFIRMED_IN_SAMPLE, with no HARMFUL horizon, and the 0001 verdicts are unchanged.
- Under 0007, +0.0530 is the number to report.

**This ruling rests on a scope judgement the owner should adjudicate.** The chain also reads the per-regime entry hazard and persistence. Those come from final revised conditions: main's standing D5 exposure, which the reference's point-in-time forecasts read from the same months through the occupancy rate. Correcting that too moves the one-year difference by more than 0.001:
- −0.001103 if only B1's side is corrected;
- +0.001090 if both runs are corrected.

In neither case does any verdict move. I treat that path as main's debt and not this change's, for three reasons:
- A4's review established that re-using main's rates on the same data opens no new route.
- D5, reopened at 86d2c7b before any arm ran, schedules the fix for after 0008 and says no verdict may be claimed from it.
- The reference carries the same exposure: correcting it lowers the reference's own point-in-time skill by about 0.0022.

If the owner reads 0007's floor as covering every approximation a new value reads, this arm is VOID, by 0.0001. See section 3.

### 1. Deterministic audits: passed. What they cover, and what they do not

`exit_codes.json` records, at commit d775bca (whose code is 937b331): `look_ahead_audit_exit: 0`, `look_ahead_audit_2022_exit: 0`, and `tree_clean_at_start_and_end: true`.

| cutoff | forecast dates | refits | rows compared | perturbed | run time |
|---|---|---|---|---|---|
| 2000-03-01 (default) | 73, 1994-03..2000-03 | 7 | 2,190, all identical | 747 vintages dated after the cutoff, whole; unpublished observations in 9 current files; 723,523 values | 435 s |
| 2022-03-01 | 337, 1994-03..2022-03 | 29 | 10,110, all identical | 136 vintages whole; 12 current files; 151,739 values | 1,891 s |

- **What they cover.** Both runs recompute the burn-in choice (16 regimes) and every fit from scratch. They compare `predicted_probability` and `condition_chain_probability` for exact equality. So B1's composition is tested against every value unpublished at each cutoff, by the recession series' announcement dating as well.
- **The 282 WARNING lines** in each file are CPI and industrial-production vintage fallbacks from the honest-start scan. All are dated 1994-02-01 or earlier, before the first forecast date, as on main.
- **What they do not cover:**
  - Revised values of already-published months (D5). This is class-B path 1.
  - A publication boundary that is itself wrong. The announcement table is code, not data, so the perturbation changes values and never moves a boundary: both runs withhold exactly the same months. Class-B path 2 is therefore invisible to the audit by construction.
  - The 11 dates where path 2 acts (2003-01..07, 2010-08..09, 2021-06..07). They lie beyond the 2000 cutoff. At the 2022 cutoff they are earlier forecasts, for which only information unpublished at the cutoff is perturbed, and every announcement predates the cutoff.
  - The 54 forecast dates after 2022-03-01.
  - Today's grid.

### 2. Every value the change introduces, traced to its inputs

The change is one branch in `forecast_indicator` (`models/indicator_forecast.py:438-456`). A point-in-time question is answered by `compose_through_the_condition_chain` (`:280-398`), the function R2 already uses, on the model's own inputs.

| input | read as of | publication timing | outcome? | filtered? | where |
|---|---|---|---|---|---|
| Joint transition matrix | latest refit ≤ s, fitted on the as-of-refit panel | main's panel rules | no | n/a | `walk_forward.py:404-449`, `:541-544`. All 34 cached fits under the arm hash 4fba792cff42d89e are byte-identical (`cmp`) to main's under fec79a040f9ca6f9. |
| Regime distribution the chain starts from | s | as-of-s panel | no | **filtered**, `filtered_state_probabilities(...)[-1]` | `walk_forward.py:549-552`. The diff contains no `smoothed` call. |
| Entry hazard, persistence | refit t ≤ s | `condition_available_at(history, t)`: label plus lag, or ADR 0011 announcement dating | no; the condition months only | fitted on filtered weights, `:451-470` | Unchanged estimator. Its values are final data: main's D5. |
| Last published condition (**new**) | s | `condition_available_at(history, s)`, `:560-563` | no | n/a | **Class-B path 1** |
| Months since it was published (**new**) | s | `months_between(condition_now.index[-1], s)`, `:585` | no | n/a | **Class-B path 2**, recession only |

**Outcomes.** `realised_outcome` and both benchmark columns are only written to the row (`:617-624`), never read by the composition.
- On the scored run, every non-prediction column is identical to reference-0008, as is `condition_chain_probability`.
- All 5,865 any-time predictions are identical too.
- All 5,865 point-in-time predictions differ.

**Today's grid.** `forecast_now` (`command_line_interface.py:377-404`) passes the same setting and the same gap, `months_between(last published label, today)`. Live, the announcement table holds only announcements that have already happened, so path 2 cannot occur in the live grid. It is a backtest artifact.

**My replay reproduces the scored run exactly.** On the arm's cached fits, the replay equals `backtest_results.parquet` on all 16 columns (`pandas.equals`). My paired statistic reproduces `paired.json` to every digit: +0.05348611278922169, 90% [+0.025912735878650638, +0.08567640250674091]. The same code with the switch off reproduces `reference-0008.forecasts.parquet` on all 9 columns.

### 3. The class-B paths, measured

Script: scratchpad `measure.py`. It patches `walk_forward.condition_available_at` at the forecast-date read, for the point-in-time indicators only, and replays from the cached fits.

**Path 2: the recession boundary (D14-class).**
- **The mechanism.** ADR 0011 publishes a recession month at the later of label + 400 days and the announcement settling its phase. The months withheld are always a suffix. So when a trough has happened but not yet been announced, the series ends earlier than 400 days would put it, and the gap grows.
- **What a real-time observer had.** The same 400-day lag, with the withheld months coded provisionally by the last announced turning point. That code (1) equals the value the pipeline reads on all 11 dates, so only the gap differs.
- Scratchpad `recession_gap_table.py`:

  | forecast dates | pipeline starts at | gap | real-time gap |
  |---|---|---|---|
  | 2003-01 .. 2003-07 | 2001-10 (1) | 15 .. 21 | 14 |
  | 2010-08, 2010-09 | 2009-05 (1) | 15, 16 | 14 |
  | 2021-06, 2021-07 | 2020-03 (1) | 15, 16 | 14 |

- **Direction.** The longer gap lets the chain decay further from "in recession", toward what did happen, so the path flatters the forecast.
- **Why class B and not class A.**
  - It is information from a later announcement, but it is D14's own publication-dating rule, and the reference shares it.
  - Under the same correction applied to both runs, reference-0008's own predictions move on 51 rows, 2003-03..2004-02, by up to 0.0127, through the 2003-03-01 refit's rates. Its R2 column steps the identical gap.
- **Size.** Correcting it alone moves 33 rows on those 11 dates, and the one-year difference by **−0.000236**.

**Path 1: the revised starting condition (D5-class).**
- **The correction.** Read the condition from the archival vintage dated the forecast date, never past the label the pipeline itself read. That removes revised values and too-early labels without adding months the registry lag withholds.
- Scratchpad `starting_condition_diffs.py`:

  | indicator | dates differing | of which |
  |---|---:|---|
  | industrial production above 2% | 60 | 58 value flips; 2 registry-lag early reads (2025-11, 2025-12), unscored |
  | consumer prices above 3% | 6 | 6 value flips |
  | unemployment above 5% | 6 | 5 value flips; 1 early read (2025-11), unscored |
  | funds rate above 4% | 0 | never revised |

- **Size.** One-year shift **−0.000259**.
- **The author's number, reproduced.** Restricted to the author's scope (industrial production and consumer prices, all vintage months), my independent implementation gives −0.0003965154708963914. That is the author's figure exactly.
- **With all vintage months included.** This also adds the unemployment month released on the 27 forecast dates that fall on a Friday the 1st. The shift is −0.000217.

**Both paths together: the correction I rule on.**

| horizon | as scored | corrected | 90% corrected | 96.67% corrected |
|---|---:|---:|---|---|
| 12 | +0.053486 | **+0.052991** | [+0.025600, +0.084721] | [+0.017196, +0.093355] |
| 60 | +0.001621 | +0.001589 | [−0.006476, +0.006771] | [−0.008901, +0.007938] |
| 120 | −0.003966 | −0.003958 | [−0.008158, +0.001968] | [−0.010747, +0.002749] |

- 249 rows move, on 78 dates.
- **One-year shift −0.000495**, under 0.001.
- PROMISING and CONFIRMED_IN_SAMPLE hold, and no horizon's 90% upper bound is below −0.02.
- The 0001 verdicts are unchanged: 12 SHIP MODEL; 60 SHIP BASE RATE (skill, calibration, robustness); 120 SHIP BASE RATE (skill, honesty).
- Series-start secondary: +0.051683 → +0.051282.

**Sensitivity outside the ruling: the rates the chain reads.** Entry hazard and persistence are estimated at each refit from final conditions.

| correction | one-year difference | shift | verdicts |
|---|---:|---:|---|
| Paths 1 and 2, plus B1's point-in-time rates from vintages (B1 side only) | +0.052383 | **−0.001103** | unchanged |
| Every condition read in real time, rates included, in **both** runs (any-time rows cancel) | +0.054576 | **+0.001090** | unchanged; 96.67% lower bound +0.0199 |
| The same, with all vintage months | +0.054623 | +0.001137 | unchanged |

The same symmetric correction lowers reference-0008's own one-year skill by 0.00033, and its point-in-time skill alone by about 0.0022. Both wider figures exceed the floor by about 0.0001, in opposite directions. The ruling above takes the floor to cover the paths the change opens. If the owner reads it more widely, the arm is VOID.

### 4. The look-ahead audit table, row by row

| row | touched? | for B1 |
|---|---|---|
| Training panel assembly | no | The filtered distribution comes from the as-of-s panel. |
| Standardisation window | no | Unchanged. |
| State probabilities used in forecasts | read | Filtered only. No smoothed call in the diff. |
| Model parameters at each refit | read | Transition matrix of the latest refit; fits byte-identical to main's. |
| Number of regimes | no | 16 (4x4), from the burn-in choice as of 1994-03-01 (panel ends 1994-01-01). |
| Conditional rates | read | Entry hazard and persistence, no new estimation. Clean except D14, as on main, plus path 2. |
| Benchmark | no | Both benchmark columns are identical to the reference's. |
| Outcome resolution | no | Unchanged. |
| Condition values feeding rate estimation | **extended** | Path 1, measured. |
| Every run setting | yes | One a-priori boolean. |
| Acceptance thresholds | no | Nothing under `proving/` changed. |
| Canonicalisation | no | Unchanged. |
| Indicator thresholds | no | D12, unchanged. |
| Future-perturbation invariance | run | Passes at both cutoffs. Blind to paths 1 and 2 (section 1). |

### 5. Did the arm do what it registered, no more and no less? Yes

**The composition.** Point-in-time only, through `compose_through_the_condition_chain`, with the model's own rates (no new estimation). It starts from the filtered distribution and the last published condition, and steps the gap and then the horizon. The any-time path is untouched: all 5,865 any-time rows are identical to the reference.

**Also wired into `forecast_now`.** That is the same method applied to today's grid, which the setting's scope implies.

**Hyperparameters and run count.**
- Shrinkage 10 and seed 20260908.
- The state count is main's (4x4).
- One scored run: one set of 34 fits under the arm hash.

**Required checks.**
- The one-regime identity was committed in d775bca, before the scored outputs in dde0dca.

**Tests.** Edits to existing tests only add the new switch at False, or a set member.
- `test_configuration_hash_compatibility.py`: +5 lines.
- `test_two_timescale_chains.py`: the same pattern.
- No assertion was removed or loosened.

**The report's own caveats are accurate:**
- The recession starting month is 14 to 21 months back.
- The filtered distribution is dated about 12 months later than the starting condition. That is a registered property, not a look-ahead: everything it uses is published by s.

### Separate finding, outside the verdict

ADR 0011 says "being late is never a leak". That is false once lateness is itself an input: the withheld suffix marks a trough nobody had announced.
- On main it reaches the 2003-03-01 refit's rates: 51 reference rows move.
- It reaches R2's gap, so B3 blends it, and rule 0007's `regimes_help` secondary scores it.

**Proposed fix.** Code the months after the last announced turning point provisionally, by that turning point's phase, instead of withholding them. That is what an observer had, and it removes the dependence. It should be measured with `forecast baseline compare` like the D5 fix, after 0008 reports.
