> Written to disk by the orchestrator, verbatim from the text the arm agent returned: the harness
> refused the agent's own write ("Subagents should return findings as text"). Extracted by code from
> the agent's transcript, not retyped. Check every number against `paired.json` and `compare.json`.

# A2-quadrant-structure-levels — report

Branch `research/quadrant-structure-levels`, scored at commit `f4d9734553f65e5fa1ef171b931a24fb550a2614`.

## What changed

All Weather's growth-by-inflation 2x2 is imposed as a structural prior on the state space, and the state count used for forecasting is fixed at 4.

- `src/economic_regime_forecasting/models/gaussian_hidden_markov_model.py` — new `_seed_means_by_quadrant_centroids(observations, state_count)`. Each month is assigned to one of four quadrants by the sign of its growth and inflation relative to their own **expanding** medians (`pandas.Series.expanding(min_periods=1).median()`), computed point in time over the panel being fitted — never a single median of the whole panel. Rates enter each centroid as that quadrant's mean; they play no part in the assignment. Wired into `fit()` via a new `seed_means_by_quadrant_structure: bool = False` parameter: when set, every restart begins from the same four centroids (deterministic, not restart-dependent), and only the transition matrix's persistence draw still varies restart to restart — "the fitter's existing per-restart perturbation" the brief asks to keep. Requires `state_count == 4`; refuses (raises `HiddenMarkovModelError`) rather than silently falling back if a quadrant has no month in the panel.
- `src/economic_regime_forecasting/configuration/run_settings.py` — new `RunSettings` field `fix_state_count_at_four_with_quadrant_structured_seeding: bool = True` (this branch's default). Added to `SETTINGS_OMITTED_FROM_THE_HASH_WHEN_THEY_HOLD_THE_SHIPPED_VALUE` at its main-equivalent value (`False`), so main's `configuration_hash` is unchanged and this arm's own configuration gets its own hash (`9632ee1193541d34` this run, vs main's `ad7fcc1affd0746a`).
- `src/economic_regime_forecasting/backtest/walk_forward.py` — `fit_regime_model` seeds by quadrant exactly when the flag is set **and** `state_count == 4`. This single call site covers every walk-forward refit and, via `forecast_now`, today's fit.
- `src/economic_regime_forecasting/command_line_interface.py`:
  - `_state_count_for_the_backtest`: the burn-in sweep still runs and its choice is still written out (the regimes-exist gate still needs that evidence), but the state count actually used to fit is fixed at `QUADRANT_STRUCTURE_STATE_COUNT = 4` regardless of what the sweep recommends.
  - `fit_regimes` (gate 2): the full-sample sweep still runs, unchanged, and its table/checks are exactly as before — but the model gate 2 selects, describes and writes to `selected_model.json` is a **separate**, quadrant-seeded four-state fit, not the sweep's own recommendation. This is what makes `forecast_now`/today's fit use K = 4 (the brief's explicit requirement); it is a deliberate design choice, not a hyperparameter change, and is recorded under Deviations below.
  - `_write_burn_in_choice` (new): writes both the sweep's own recommendation and what was actually used for forecasting into the one artifact. See the regression_baseline.py fix under Deviations.
- `src/economic_regime_forecasting/regression_baseline.py` — bug found and fixed while running this arm; see Deviations.

Tests: `tests/test_gaussian_hidden_markov_model.py` (centroid arithmetic against an independently computed reference, the whole-panel-vs-expanding-median distinction, empty-quadrant and wrong-K refusals, restart-invariant means, canonicalisation stability for a quadrant-initialised four-state fit), new `tests/test_quadrant_structure_levels.py` (RunSettings/hash wiring, `walk_forward.fit_regime_model` wiring, CLI wiring for `_state_count_for_the_backtest` and `fit_regimes`, the burn-in-choice artifact), and additions to `tests/test_regression_baseline.py` (below).

## Look-ahead audit

`docs/TECHNICAL_DEBT.md`'s look-ahead audit table, filled in for this arm.

| path | status for A2 |
|---|---|
| Training panel assembly | **clean, unaffected.** A2 only changes what happens *inside* `hidden_markov.fit()`, given an already point-in-time, already-assembled observation matrix. |
| Standardisation window | **clean, unaffected.** `observation_matrix.py` untouched. |
| State probabilities used in forecasts | **clean, unaffected.** Filtered/smoothed method calls untouched. |
| Model parameters at each refit | **clean.** Every refit still fits from scratch on the point-in-time panel at that refit's `as_of` date. The new computation this arm adds — the expanding median inside `_seed_means_by_quadrant_centroids` — operates only on that same, already point-in-time `observations` array, and is itself causal (row *t* uses only rows 0..*t* of that panel; pinned by `test_quadrant_centroids_differ_from_seeding_off_a_whole_panel_median`, which constructs a panel where the expanding-median and whole-panel-median answers provably differ for the first two months, and asserts the function gives the expanding one). No new source of future information. |
| **Number of regimes** | **clean, and simpler than before.** For A2 the K actually used for forecasting is not "chosen" from data at all; it is a pre-registered constant (4), a priori, the same status as a seed or a restart count. The burn-in sweep (for backtest, gate feeding) and the full-sample sweep (for gate 2) both still run, still touch only point-in-time-safe windows exactly as on main, and their recommendations are reported (6 and 5 respectively, this run — see below) but never feed any forecast-generating computation for this arm. |
| Conditional rates | **clean, unaffected.** `indicator_forecast.py` untouched. |
| Benchmark (climatology) | **clean, unaffected.** `walk_forward.py`'s climatology logic untouched (only `fit_regime_model`'s seeding call changed). |
| Outcome resolution | **clean by design, unaffected.** |
| Condition values feeding rate estimation | **unaffected** (D5, unchanged approximation). |
| Every run setting | **clean.** A2 adds one new a priori constant (`fix_state_count_at_four_with_quadrant_structured_seeding=True`, `QUADRANT_STRUCTURE_STATE_COUNT=4`) — not derived from data, pre-registered in `experiment.json`. |
| Acceptance thresholds | **clean, unaffected** (0001 unchanged). |
| Canonicalisation rule | **clean, unaffected** — a fixed sort, not fitted. Verified stable/non-degenerate for a quadrant-initialised four-state fit by `test_a_quadrant_seeded_fit_converges_and_canonicalises_to_four_distinct_states` (four states, strictly increasing growth means, no state below the 5% population floor). |
| Indicator thresholds | **unaffected** (D12, unchanged, still weak). |
| **Future-perturbation invariance** (`forecast audit-look-ahead`) | **Exit 0** on this run: `PASS: no forecast issued on or before 2000-03-01 changed when every observation unavailable at 2000-03-01 was perturbed` (347s, 627,617 values perturbed across 1,348 copied cache entries, 2,190 rows compared). **Important limitation, found while writing this report:** `look_ahead_audit.py`'s `_run_from_scratch` calls `choose_state_count_on_burn_in_window` directly and fits with `choice.state_count` (the sweep's own, unconstrained recommendation) — it does **not** call `_state_count_for_the_backtest` and has no knowledge of `fix_state_count_at_four_with_quadrant_structured_seeding`. Both the "original" and "perturbed" runs inside this audit report `6 regimes chosen on the burn-in window, 7 fits computed from scratch` (see `look_ahead_audit.txt`) — i.e. this audit exercised K = 6 with furthest-point seeding, the *main-shaped* configuration, not this arm's actual K = 4 quadrant-seeded path. `_seed_means_by_quadrant_centroids` and the K = 4 override in `_state_count_for_the_backtest`/`fit_regimes` were never called during this audit. The PASS is still evidence — it re-confirms the shared point-in-time panel/vintage machinery every arm's fits read from is leak-free — but it is **not** a direct mechanized test of this arm's own seeding code. That code's causality is instead established by unit test (`test_quadrant_centroids_differ_from_seeding_off_a_whole_panel_median`, above) and by inspection: `_seed_means_by_quadrant_centroids` receives only the already-point-in-time `observations` array `fit_regime_model` builds for each refit's `as_of` date, and computes the median with `pandas`' `expanding()`, which by construction only ever looks backward. This gap is pre-existing in `look_ahead_audit.py` (unmodified by this arm) and would affect any arm that changes *which* state count gets used for forecasting; it is reported here rather than worked around, per the "no silent fallbacks" rule and because fixing the shared audit tool is out of scope for a research arm. A judged look-ahead review by an agent that did not write this arm should specifically check `_seed_means_by_quadrant_centroids`'s causality by reading the code, since the deterministic check did not exercise it directly. |

## Run history

Four attempts. Only the fourth is scored.

**Run 1 — commit `d2df015`, VOIDED by a bug in the measuring instrument, not scored.**
`check_gates_exit=1, compare_exit=2, paired_exit=2, look_ahead_audit_exit=0`. `regression_baseline._state_count_chosen_as_of` assumed the burn-in sweep's own recommendation (6 states) was always the state count actually used to fit. This arm breaks that assumption on purpose (the sweep still runs and still recommends 6, as regimes-exist evidence, while forecasting is fixed at K = 4). `_write_run_summary` crashed with `BaselineError: burn_in_state_count_choice.json says 6 regimes were chosen but backtest_results.parquet was run with 4. The two artifacts come from different runs; re-run forecast backtest so the cache describes one.` — raised *after* Gate 5 had already printed PASS; the backtest and evaluation both completed, only run-summary assembly failed.

**Run 2 — commit `d2df015` + a first, wrong fix, CONTAMINATED, not scored.** The first fix attempt made the consistency check skip itself (`return None`) whenever a `state_count_is_a_fixed_hyperparameter` flag was set, instead of reconciling the two facts. This unblocked the pipeline (`check_gates_exit=0, compare_exit=1, paired_exit=0, look_ahead_audit_exit=0`) but the run was started while a full `pytest -m "not network"` re-run was **also** running against the same worktree's live `.cache/` (`tests/test_honest_start_date_against_the_live_cache.py` reads and writes it). Flagged by the coordinator; not scored regardless of exit codes, and the fix itself was reverted as substantively wrong (it hides a genuine future mismatch rather than reconciling it, which would have silently defeated the consistency check for every subsequent run of this configuration). For the record: this run's one-year paired difference, read before discarding it, was numerically identical to run 4's (+0.0381, 90% [+0.0144, +0.0583]) — expected under this project's determinism guarantee, since both ran the same configuration hash on the same data; it is reported here only as a cross-check, not as evidence in its own right.

**Run 3 — commit `19bd25d` (the corrected fix design), INVALIDATED by my own mid-run edit, not scored.** Second fix: `burn_in_state_count_choice.json` now records both the sweep's own recommendation (`state_count`, unchanged) and what was actually used for forecasting (new field `state_count_used_for_forecasting`); `_state_count_chosen_as_of` compares the latter against the backtest's own state count. Started alone at 21:33:05, 7s after committing `19bd25d`, verified via `ps -ef` and `lsof +D <worktree>` that nothing else was touching the worktree at the start. Finished clean-looking (`check_gates_exit=0, compare_exit=1, paired_exit=0, look_ahead_audit_exit=0`) — but partway through, I added two more tests to `tests/test_regression_baseline.py` via an edit, which left the tree dirty against HEAD while the run was still in progress. Caught by re-checking `git status` after the run finished. The edit was test-only and not on the check-gates/backtest code path, so it could not have changed the computation, but the tree was not clean throughout the run, which is the rule broken regardless. Committed the two tests as `f4d9734` immediately after, confirmed the tree clean, reran the full offline suite alone (same two pre-existing, expected failures, nothing new), then started run 4.

**Run 4 — commit `f4d9734`, clean, solitary, untouched throughout. This is the scored run.** Started 21:46:45 JST with nothing else touching the worktree; verified clean before starting. `exit_codes.json`: `{"commit": "f4d9734553f65e5fa1ef171b931a24fb550a2614", "tree_clean_at_start_and_end": true, "check_gates_exit": 0, "compare_exit": 1, "paired_exit": 0, "look_ahead_audit_exit": 0}`.

## Results (run 4, quoted from `paired.json`, `compare.json` and `check_gates.log`; not retyped or rounded into new values)

**Five gates (`check_gates.log`):** Gate 1 — data: PASS. Gate 2 — regime model: PASS (full-sample sweep recommends 5 states on `held-out log likelihood per month` and BIC; the quadrant-seeded four-state model this arm actually uses is described separately: `contracting growth, moderate inflation, neutral rates` / `steady growth, high inflation, high rates` / `steady growth, moderate inflation, low rates` / `steady growth, moderate inflation, high rates`; populations 23.7%/22.3%/32.2%/21.8%, no regime below the 5% floor, "32 switches over 908 months, 0.42 a year against a ceiling of 2.0"). Gate 3 — forecasts: PASS. Gate 4 — backtest: PASS (11,730 rows, 0 duplicates, 9,702 resolved). Gate 5 — evaluation: PASS.

**0001's per-horizon gate verdicts, compared against main (`compare.json`'s categorical fields — `verdict` and `failing_gates` are `IDENTICAL` at all three horizons):**
- 1 year: `SHIP BASE RATE`. Failed: calibration only. `mean skill score +0.2534 against a bar of +0.02; +0.2534 [+0.1386, +0.3581] at 90%`; `expected calibration error 0.1271 over 3754 forecasts in 10 populated bins`; robustness `4 of 4 sub-periods positive`; honesty `0.3541` against a floor of `0.05`.
- 5 year: `SHIP BASE RATE`. Failed: skill, calibration, robustness. `mean skill score +0.0979 ... +0.0979 [-0.1298, +0.2272] at 90%`; `expected calibration error 0.2101`; robustness `2 of 4 sub-periods positive`; honesty `0.0804`.
- 10 year: `SHIP BASE RATE`. Failed: skill, calibration, robustness, honesty. `mean skill score -0.1325 ... [-0.2181, -0.0141] at 90%`; `expected calibration error 0.1279`; robustness `2 of 4 sub-periods positive`; honesty `0.0187` against `0.05`.

Main gets the **identical** verdict and the identical set of failing gates at every horizon (`compare.json`: `{"field": "verdict", "row": "12", "baseline": "SHIP BASE RATE", "current": "SHIP BASE RATE"}`, and likewise for 60 and 120, and for `failing_gates`). No verdict flip anywhere — consistent with the pre-registration's `why_not_the_0001_verdict` clause, which this experiment does not use as a route to success.

**lambda2 / information horizon (`check_gates.log`, gate 3):** "The second eigenvalue modulus is 0.9796, a half life of 34 months. Regime information survives to 60 months (5 years); beyond that the projection is the unconditional base rate." This arm's change affects lambda2 (fewer, differently-seeded states), so it is reported per the brief.

**Calibration error and log loss against main**, unweighted mean across the 10 scored indicators per horizon, computed from `compare.json`'s per-indicator `expected_calibration_error` and `logarithmic_loss` MOVED rows (tool-computed differences, not retyped):

| horizon | mean ECE, main | mean ECE, this run | diff | mean log loss, main | mean log loss, this run | diff |
|---|---:|---:|---:|---:|---:|---:|
| 12 | 0.159923 | 0.144859 | −0.015064 | 0.594038 | 0.561682 | −0.032356 |
| 60 | 0.250160 | 0.254861 | +0.004701 | 0.758704 | 0.736810 | −0.021894 |
| 120 | 0.281918 | 0.262517 | −0.019401 | 0.692559 | 0.643802 | −0.048757 |

(Lower is better for both. This is an unweighted per-indicator mean and is a different statistic from gate 5's pooled, threshold-tested ECE quoted above; it is reported because it is the number `baseline compare` actually computes and can be quoted verbatim.)

**The primary endpoint — one-year paired mean Brier skill score, this run minus main (`paired.json`, `horizons[0]`, `horizon_months: 12`):**

```
difference: +0.0380502689801345
90% interval:   [+0.01439254036836438, +0.0582969503291242]
98.33% interval: [+0.005414499173647061, +0.06898370606558105]
effective independent observations: 31.5
resamples used: 9953 of 10000
```

**Five-year (`horizons[1]`, `horizon_months: 60`):**
```
difference: +0.02512516033167124
90% interval:    [+0.0013298767787438242, +0.08307698875971993]
98.33% interval: [-0.009498595208357137, +0.1220302304072582]
effective independent observations: 5.5
```

**Ten-year (`horizons[2]`, `horizon_months: 120`):**
```
difference: +0.22022540187657258
90% interval:    [+0.10213565668642881, +0.25059741884296083]
98.33% interval: [+0.05453788825731689, +0.805531892462812]
effective independent observations: 2.25
```

All three horizons: `outcome_disagreements: 0`, `rows_only_in_baseline: 0`, `rows_only_in_this_run: 0` — the two runs score the identical set of resolved forecasts, nothing dropped uncounted.

## Verdict under the pre-registered rule (`proving/experiments/0002-research-slate-2026-09/experiment.json`, `decision_rule`)

**PROMISING** requires the one-year paired 90% interval to lie entirely above zero: `[+0.0144, +0.0583]` — lower bound `+0.0144 > 0`. **True.**

**CONFIRMED_IN_SAMPLE** requires the one-year paired interval at the family-wise level, `1 - 0.10/6 = 98.33%` (Bonferroni across experiment 0002's six arms), to lie entirely above zero: `[+0.0054, +0.0690]` — lower bound `+0.0054 > 0`. **True.** The paired output does carry a 98.33% interval (quoted above, computed from the same 10,000 resamples as the 90% interval, per `docs/REGRESSION_TESTING.md`), so this claim is made on the interval the pre-registration asks for, not a substitute.

**HARMFUL** requires the paired 90% interval to lie entirely below −0.02 at *any* horizon. One-year `[+0.0144, +0.0583]`, five-year `[+0.0013, +0.0831]`, ten-year `[+0.1021, +0.2506]` — every horizon's 90% interval lies entirely *above* zero, none anywhere near −0.02. **False.**

**Verdict: CONFIRMED_IN_SAMPLE.** This is the strongest claim the pre-registration allows a single arm to make on this run. It is not out-of-sample confirmation (the pre-registration is explicit that only forward-registered forecasts, scored as they resolve from 2027-07-01, can provide that), and every arm here was designed after seeing main's own weaknesses (over-persistence, miscalibration), which the pre-registration also states plainly.

## Prediction versus outcome

The pre-registration's `stated_in_advance` predicted: *"One-year skill lower than main, with fewer states; calibration error lower, with more data per state"* (arm-level), and separately, in the experiment-wide summary: *"A2 and A3 are expected to underperform main, and a negative result for the All Weather structure is a finding."*

The outcome is the opposite of the skill prediction: one-year paired skill is **higher** than main by +0.0381 (90% CI entirely above zero, 98.33% CI entirely above zero — CONFIRMED_IN_SAMPLE), not lower. The calibration half of the prediction is mixed rather than confirmed: this run's *pooled*, gate-tested one-year calibration error (0.1271) is numerically similar in kind to main's own failure (both `FAIL` calibration at 1 year, `IDENTICAL` verdict field); the *unweighted per-indicator mean* ECE is lower than main's at one and ten years but very slightly higher at five years (+0.0047). Five- and ten-year paired skill are also both positive (not predicted either way at the arm level, but the experiment-wide summary predicted A2 underperforming main generally). This is a genuinely surprising result relative to the pre-registration's own stated expectation, and it is reported as such rather than smoothed over — per the pre-registration's own words, "most arms are expected NOT to clear even the 90% bar," making a CONFIRMED_IN_SAMPLE result on the very indicator predicted to underperform worth flagging prominently for whoever adjudicates the slate.

One candidate explanation, offered as a hypothesis and not a finding: gate 2's quadrant-seeded four-state model is not obviously an "All Weather" partition when described (states 2 and 3 both read as `steady growth, moderate inflation`, differing mainly in rates) — the seeding is a starting point for expectation maximisation, not a constraint on the converged model, and EM was free to move away from strict quadrants. Whether the *initialization* alone (fewer states, four rather than the sweep's five or six) or the *specific* growth/inflation structure drove the improvement is not established by this run and would need a separate ablation (out of scope here, and would be a new, separately registered experiment under the pre-registration's own forbidden-act clause).

## Deviations from the specification, with reasons

1. **`fit_regimes` (gate 2) design interpretation.** The brief says the full-sample sweep "still runs... and its result is reported... but it no longer chooses K," mirroring language used for the burn-in sweep. I applied this symmetrically: the full-sample sweep's own table and gate-2 checks are unchanged, but the model written to `selected_model.json` (which `forecast_now` reads `state_count` from) is a separate quadrant-seeded K=4 fit. This is what makes "`forecast_now` and today's fit also use K = 4" true, per the brief's explicit instruction under "Notes for this arm." No hyperparameter was changed; this is a code-structure choice about which of two already-specified fits feeds which downstream artifact.

2. **`regression_baseline.py` fix** (commits `19bd25d`, `f4d9734`). Not a hyperparameter change — a narrow, mechanical fix to the measuring instrument, made necessary by this arm's registered design (the burn-in sweep recommends one K; forecasting uses a different, fixed K; the pre-existing consistency check assumed those were always equal). `_state_count_chosen_as_of` now reads a new field, `state_count_used_for_forecasting`, falling back to the pre-existing `state_count` field when the new one is absent. Main's behaviour is provably unchanged by this fix: an artifact with no `state_count_used_for_forecasting` key (main's own shape, and every prior baseline) still passes when it matches (`test_an_artifact_without_the_new_field_still_passes_when_it_matches`, new) and still raises on a genuine mismatch (`test_an_artifact_without_the_new_field_still_raises_on_a_real_mismatch`, new), and the pre-existing, unmodified `test_a_burn_in_choice_from_a_different_run_is_refused` continues to pass unchanged. Nothing in the compare, paired-comparison or bootstrap code paths was touched. A look-ahead/independent reviewer should check this change specifically, as requested.

3. **Process, not code:** two run attempts (2 and 3) were started and discarded, for contamination/tree-dirty reasons of my own making, both reported in full above rather than omitted, per "a negative result is a finding" and "report anything surprising."

## Expected, unedited test failures

Two, both in `tests/test_configuration_hash_compatibility.py`, deliberately **left unedited** (not touched by any commit on this branch), per this repository's test-protection covenant: a research branch is never merged to main, and both tests pin exactly what main's own configuration and hash-omission map are, which this arm's registered source change legitimately extends.

1. `test_the_shipped_configuration_hashes_to_the_recorded_digest` (AC1) — pins `RunSettings(select_state_count_on_a_burn_in_window=False, start_walk_forward_when_every_input_is_point_in_time=False)` hashing to the literal `9f95b12dba40d138`. On this branch, that same constructor call additionally carries `fix_state_count_at_four_with_quadrant_structured_seeding` at its dataclass default (`True`, this arm's own behaviour) because the call doesn't name it, so the digest computed is `19d1cbe2da54f8c1`, not the historical one. Confirmed **not** a regression in main's own reproducibility: the identical settings with `fix_state_count_at_four_with_quadrant_structured_seeding=False` named explicitly reproduce `9f95b12dba40d138` exactly (`tests/test_quadrant_structure_levels.py::test_the_field_at_false_hashes_identically_to_a_configuration_missing_it_entirely`, `::test_toggling_the_field_changes_the_configuration_hash_when_other_settings_hold_it_fixed`).
2. `test_the_omission_map_holds_only_the_two_documented_switches` — pins the hash-omission map at exactly two entries. This arm's source change legitimately adds a third (its `False` value reproduces pre-field behaviour, the same shape the other two entries have), and the map's own docstring anticipates exactly this: "must be revisited... the day a legitimate third entry is added." Pinned instead by `tests/test_quadrant_structure_levels.py::test_the_field_is_in_the_hash_omission_map_at_false`.

Both failures pin main's exact configuration; neither hides a defect in the arm. Full offline suite (`pytest -m "not network"`), run alone against commit `f4d9734`, immediately before run 4: these two failures only, everything else green. `ruff check .`, `ruff format --check .` and `mypy` all clean.

## Anything surprising, and anything I could not do

- **Surprising:** the CONFIRMED_IN_SAMPLE verdict itself, against the pre-registration's stated expectation that A2 would underperform — see "Prediction versus outcome" above.
- **Surprising:** `look_ahead_audit.py`'s pre-existing blind spot to per-arm state-count overrides (see the look-ahead audit table's last row) — found only while writing this report, after the deterministic check had already exited 0. It does not change this arm's own audit result, but it does mean that result carries less direct weight than a first read of "exit 0" would suggest, and is worth fixing generically (for every future arm that changes which K gets used) rather than per-arm.
- **Could not do:** produce a mechanized look-ahead test of `_seed_means_by_quadrant_centroids` specifically (as opposed to unit tests and code inspection), because the shared audit tool doesn't reach that code path under any arm's override. Flagged for the independent look-ahead reviewer rather than worked around.
- Two run attempts were lost to my own process discipline failures (contaminated cache sharing, then an edit during a run) rather than to anything about the arm's design; both are reported in full above rather than quietly redone and forgotten.
