# Look-ahead review: sticky-dirichlet-prior (A1, experiment 0002)

Reviewer: an independent agent that did not write this arm. Reviewed on 2026-09-15.
Change reviewed: `git diff 2e025b7...research/sticky-dirichlet-prior` (branch head `5e42828`, code commit `7ca7b93`).
Line numbers below are for the branch (`git show research/sticky-dirichlet-prior:<path>`).
Nothing in the arm's branch or worktree was modified. Every re-computation below ran on a
`git archive` copy of the branch in a scratch directory, with a copy of the arm's `.cache/`.

## sticky-dirichlet-prior
VERDICT: CLEAN

**Summary.** The change introduces no new data channel. Every quantity it adds is a function of two
pre-registered constants, the state count, and expected transition counts from the same
point-in-time panel main already fits on. The deterministic audit passed on this arm's own
configuration. The prior reaches every fit: the burn-in sweep, the full-sample gate sweep, every
walk-forward refit, and today's fit. I re-verified the required bit-for-bit check on real data
against main's own cached model, which is stronger than the arm's tests. Both failing tests pin
main's behaviour, which this arm is registered to change. Every headline number matches
`paired.json` and `compare.json` when extracted by code. Three things are not leaks but are
recorded below:
- an inaccurate comment on the monotonicity guard (§7);
- a test-suite count in the report that the tree does not support (§9);
- the D12-class provenance of D itself (§10).

### 1. Deterministic audit (VOID check a): passed, on this arm's configuration
- `research/arms/sticky-dirichlet-prior/exit_codes.json`: `"look_ahead_audit_exit": 0`, commit `7ca7b93fbef…`.
- `look_ahead_audit.txt:293`: `PASS: no forecast issued on or before 2000-03-01 changed when every observation unavailable at 2000-03-01 was perturbed`.
- The audit record `.cache/models/look_ahead_audit.json` shows:
  - `configuration_hash: 7239dd930035d4f8`, `rows_compared 2190`, `rows_moved 0`, `moved_rows []`;
  - 7 fits computed from scratch in both the original and the perturbed runs, and both runs
    choose 6 states with runner-up 4.
- I computed `DEFAULT_RUN_SETTINGS.configuration_hash()` on the branch and got `7239dd930035d4f8`.
  So the audit ran with the prior on (D = 30, M = 60), not with main's settings.

### 2. Every value the change introduces, traced to its inputs
The source diff touches six files and nothing else:
- `models/gaussian_hidden_markov_model.py` and `models/state_selection.py`;
- `backtest/walk_forward.py`, where the only change is 11 lines inside `fit_regime_model`;
- `backtest/state_count_on_burn_in.py`, where the only change is 2 lines of argument plumbing;
- `command_line_interface.py`, where the only change is 2 lines of argument plumbing;
- `configuration/run_settings.py`.

Nothing under `data/`, `features/`, outcome resolution, condition timing, or
`_expanding_climatology` changed. So the ADR 0009 outcome-publication boundary is untouched, and
there is no second implementation of it. No new read of revised current-vintage values was added,
so there is no new D5 channel.

| introduced quantity | defined at | inputs | latest observation it can touch |
|---|---|---|---|
| D, M | `run_settings.py:97`, `:112` (30.0, 60.0) | pre-registered constants, `experiment.json:30-31` | none. No date or data is read |
| beta, kappa | `gaussian_hidden_markov_model.py:77-81`: `beta = M / (D*(K-1))`, `kappa = M - K*beta`; `(0, 0)` for K <= 1 or M == 0 | D, M, and the K being fitted | none beyond K. K is chosen once on the burn-in panel, guarded by `state_count_on_burn_in.py:150` `if not panel_end < first_forecast_date` (strict `<`: the panel's last label is strictly before 1994-03-01), and that path is unchanged |
| M-step transition row `A[k,j] = (n[k,j] + beta + kappa*1{j=k}) / (n[k] + K*beta + kappa)` | `:84-105`, applied at `:779` | expected counts n from the E-step on the matrix passed to `fit` | the last row of the `as_of` panel `fit_regime_model` already assembles at the refit date, which is identical to main |
| guard's monitored quantity, log likelihood plus prior log density | `:600-621`, `:661-666` | the current transition matrix, beta, kappa | same as above. It only decides whether a fit raises |

**Filtered versus smoothed.** Smoothed responsibilities appear only inside the M-step, on the
training panel, as in main. Forecasts still use `filtered_state_probabilities` (`:246`, unchanged),
and `forecast_now` calls it at `command_line_interface.py:329`.

### 3. Hyperparameters: registered, derived per K, not tuned, one run
- **Registered values.** D = 30 and M = 60 are the defaults at `run_settings.py:97,112`, matching
  `experiment.json:30-31`. The registration commit `9bf13d6` and its amendment `2e025b7` are
  ancestors of the branch point. `git diff --stat 2e025b7 research/sticky-dirichlet-prior -- proving/` is empty.
- **Derived per K, exactly as registered.** On the branch, `derive_sticky_dirichlet_prior`
  returns `(0.4, 57.6)` at K = 6 and `(0.5, 57.5)` at K = 5, the registration's own worked
  examples. The derivation is called with the K of each fit: per candidate in the sweep
  (`state_selection.py:220-234`) and per refit (`walk_forward.py:247-263`).
- **Nothing fitted or searched.** The only readers of the two settings are the three call sites
  above plus `command_line_interface.py:281-282` and `state_count_on_burn_in.py:166-167`, found
  with `git grep sticky_dirichlet` over `src/`, `scripts/` and `notebooks/`. No code reads lambda2
  or an unregularised fit when setting kappa, so kappa is `M - K*beta` and nothing else. The
  registration's `forbidden` clause (`experiment.json:34`) is respected.
- **One run.**
  - The branch reflog is: created at `2e025b7`, then `7ca7b93` (code), then `5e42828`
    (outputs and report only).
  - The arm's model store holds exactly two arm-era configuration hashes:
    - `7239dd930035d4f8`, the default;
    - `58c302e0b3080680`. I recomputed this as
      `DEFAULT_RUN_SETTINGS` with `start_walk_forward_when_every_input_is_point_in_time=False`,
      the 1971-12 cell of the live-cache test, with the same D and M.
  - Every other hash in the store (`ad7fcc…`, `9f95b12…`, `14a5a2…`, `e141ea…`) is timestamped
    15:22:52, the setup copy from main.
  - A run with a different D or M would carry a different hash, and none is present. This
    evidences no second run through this store. It cannot rule out a run in some other cache.
- **Run provenance, checked because the timestamps looked odd:**
  - The arm's fitted models are timestamped 15:56–16:00 (today's fit, and refits 1994-03
    through 2001-03) and 20:44–20:57 (2002-03 through 2026-03).
  - `ArtifactStore.write_table` and `write_json` always rewrite (`data/cache.py:270-290`), yet the
    gates 1–3 artifacts stayed at 15:51–15:56 while `check_gates.log` closed at 20:57. So gates 1–3
    were not re-run: this was one run that stalled for about 4h44m between two refits, not two runs.
  - The cached burn-in choice (`burn_in_state_count_choice_1994-03-01_…_7239dd….json`, 15:33:08)
    predates commit `7ca7b93` (15:51:03). The run read a choice computed by the uncommitted
    working tree.
  - I checked that it makes no difference. The audit's from-scratch runs under committed code
    choose 6 with runner-up 4. And my own from-scratch refits under committed code, with an
    empty store, of the 1994-03-01 model and today's 2026-09-15 model are **bit-identical** to the
    cached files the run used: `transition_matrix`, `means`, `covariances` and
    `initial_distribution` are all `array_equal`, and the log likelihoods match exactly
    (−989.8634510454899 and −1615.9332398489682).

### 4. The prior reaches every fit, so this is not a mixture
- `hidden_markov.fit` has exactly two callers in `src/` and `scripts/`: `walk_forward.py:253` and
  `state_selection.py:226`. Notebooks have none. Both callers pass the derived beta and kappa.
- **Burn-in sweep.** `state_count_on_burn_in.py:159-168` hands the settings to
  `sweep_state_counts`, which derives a prior per candidate. At K = 1 it derives `(0, 0)`, but a
  one-state transition matrix is `[[1.0]]` either way, so this is not a mixture.
- **Full-sample gate sweep** (`fit_regimes`, `command_line_interface.py:274-283`): the prior is passed.
- **Walk-forward refits and today's fit.** Both go through `fit_regime_model`, today's at
  `command_line_interface.py:320` with `workspace.settings`, which is `DEFAULT_RUN_SETTINGS`.
  The audit and `compare-variants` also derive their settings from `DEFAULT_RUN_SETTINGS`.
- **The real fits show it.** Minimum transition entry, arm against main, computed from the model files:

  | fit | arm | main |
  |---|---|---|
  | 1994-03 | 0.00230 | 6.6e-299 |
  | 2026-03 | 0.00139 | 4.3e-252 |
  | today, 2026-09-15 | 0.00151 | 2.4e-184 (main's today fit is K = 5) |

  Main has effective zeros everywhere; the arm has none. `forecast_now` is consistent with the
  walk-forward.

### 5. The required bit-for-bit check
- `tests/test_gaussian_hidden_markov_model.py:322-345` uses `np.testing.assert_array_equal` on
  the transition matrix, means and covariances, and `==` on the log likelihood. That is exact
  equality, not a tolerance.
- `tests/test_walk_forward_backtest.py:480-522` (`fit_regime_model` with M = 0 against a direct
  `hidden_markov.fit`) and `tests/test_state_labelling_and_selection.py:253-272` (the sweep) are
  exact as well.
- **Limitation.** All three compare the branch with itself: explicit zeros against the new
  defaults. They would still pass if the zero-prior path had drifted from main's code.
- **Closed on real data.** With the branch code at M = 0, `fit_regime_model` at 1994-03-01, K = 6
  and an empty store, I compared against main's cached reference model
  `model_1994-03-01_states6_seed20260908_ad7fcc1affd0746a.json`. The result is **bit-identical**:
  all four arrays are `array_equal`, and the log likelihood is −984.7176221903965 on both sides.
  The registration's required check holds against main's behaviour, not only the branch's.
  (Suggestion, not a finding: pin that comparison as a test.)

### 6. The two existing tests that fail
Both fail because they pin main's behaviour, which this arm is registered to change. Neither is a defect.

- **`test_configuration_hash_compatibility.py:31`** builds
  `RunSettings(select_state_count_on_a_burn_in_window=False, start_walk_forward_when_every_input_is_point_in_time=False)`
  and expects `9f95b12dba40d138` (`:27`).
  - On the branch that object also carries D = 30 and M = 60. Both enter the hash
    (`run_settings.py:159-167`; neither is in the omission map at `:172`).
  - So the object now describes "the shipped configuration plus the prior", a model that produces
    different numbers. On the branch it hashes to `194f98a9f85f0df6`.
  - The test pins the digest of a prior-free run. It failing is correct. Passing would be the
    defect, because two different models would share one identity.
  - The arm could not make it pass without editing the pinned omission-map membership
    (`:107`) or its `bool` check (`:72`), and it rightly did not.
- **`test_honest_start_date_against_the_live_cache.py:107`** expects `DEFAULT_RUN_SETTINGS`' burn-in
  sweep to choose 6 with runner-up 2 (`:119`). That is main's measured sweep.
  - With the prior on, every candidate is fitted differently, and the runner-up moves to 4.
  - The test pins main's behaviour. Expected.
  - The test reads the choice from the model store if it is cached (`:116` together with
    `state_count_on_burn_in.py:142`). On the arm's worktree it would therefore read the 15:33 file.
  - I confirmed runner-up 4 from committed code in two independent ways: the audit's from-scratch
    runs (`runs.original.runner_up_state_count: 4`), and a scratch suite run with that cached
    file deleted first (§9).

### 7. The lambda2 claims and the monotonicity guard
**Lambda2**, computed as the second-largest eigenvalue modulus of `transition_matrix` in the model files:

| refit | arm | main | report |
|---|---|---|---|
| 1994-03 | 0.9700192614690768 | 0.977733694919707 | 0.9777 → 0.9700 |
| 2026-03 | 0.9760916058361273 | 0.984492978837345 | 0.9845 → 0.9761 |

Both claims are supported. Today's fit gives 0.9756630772904578, matching `check_gates.log`'s
"0.9757".

**The guard never fired:**
- `grep -c "fell from" check_gates.log` returns 0.
- Structurally, the guard raises `HiddenMarkovModelError` (`gaussian_hidden_markov_model.py:666-680`).
  Neither `fit` nor any caller in `src/` catches it. The only broad `except` is
  `look_ahead_audit.py:422`, which re-raises as an audit error, and the audit passed.
- A fitted model reaches the store only after `fit` returns. So each of the arm's 34 model files
  is a fit in which the guard did not fire.
- `check_gates` exited 0, with 33 refits.

**Not a leak, but inaccurate.** The comment at `:653` says the log posterior "IS guaranteed to
rise". That guarantee belongs to the MAP (mode) update, `(n + alpha - 1)/(...)`. The
posterior-MEAN update `(n + alpha)/(...)` used here does not maximise expected complete-data log
likelihood plus log prior. So the monitored quantity is not guaranteed to be monotone either, and
the guard could in principle fire on a correct fit. It did not on this run, so no number is
affected. This matters for anyone reusing the guard.

### 8. Headline numbers, extracted by code
- **`paired.json`.** All 9 full-precision numbers quoted in `REPORT.md` appear verbatim in
  `paired.json` (0 missing).

  | horizon | difference | 90% interval | 98.33% interval |
  |---|---|---|---|
  | 12 months | +0.0046432543498702294 | [−0.01263514317587533, 0.023163751739519112] | [−0.020565486326839136, 0.032099737982122185] |
  | 60 months | −0.002981474636052514 | [−0.04295952347611769, 0.057413481922742024] | not quoted here |
  | 120 months | +0.1904532017533582 | [0.08989604285940545, 0.2319794983328589] | not quoted here |

  - Also matching at 12 months: 31.5 independent observations, 3754 rows and 378 dates.
  - Decision rule, computed from the intervals: PROMISING is False, CONFIRMED_IN_SAMPLE is False,
    and HARMFUL is False at every horizon. The report's "none of the above" is correct.
- **`compare.json`.**
  - Counts are 110 IDENTICAL, 0 NUMERICAL, 277 MOVED.
  - Exactly one categorical MOVED field: `run.configuration_hash`, `ad7fcc1affd0746a` → `7239dd930035d4f8`.
  - `verdict` and `failing_gates` are IDENTICAL at 12, 60 and 120 months.
- **Secondary figures.** The report derived main's side itself; I recomputed both sides with
  `evaluation.verdict.evaluate_horizon`. For main I used main's cached `backtest_results.parquet`,
  whose hash is `ad7fcc…` and whose skill of 0.2154 / 0.0728 / −0.3528 matches `baselines/main.json`.

  | figure | main | arm |
  |---|---|---|
  | calibration error, 1 / 5 / 10 years | 0.1250 / 0.1942 / 0.1156 | 0.1229 / 0.2054 / 0.1364 |
  | honesty distance, 1 / 5 / 10 years | 0.4167 / 0.1197 / 0.0373 | 0.4792 / 0.1052 / 0.0199 |

  Every figure matches the report.

### 9. Test suite
I ran the full offline suite (`pytest -m "not network" -p no:cacheprovider`) on a scratch copy
of the branch at `5e42828`. The cached burn-in choices were deleted first, so the sweep
recomputed under committed code.

**Result: 487 passed, 2 failed, 0 skipped.** The failures are exactly the two tests in §6:
- `test_configuration_hash_compatibility.py:37`: `assert '194f98a9f85f0df6' == '9f95b12dba40d138'`.
- `test_honest_start_date_against_the_live_cache.py:119`: `assert 4 == 2`, from a freshly
  computed `BurnInStateCountChoice(state_count=6, runner_up_state_count=4, …)`.

**Minor discrepancy, not a leak.** `REPORT.md` states "500 passed, 2 skipped, 2 failed", which is
504 tests. The committed tree collects **489** tests under `-m "not network"`, and 490 with no
filter. The worktree's `tests/` has the same 29 `test_*.py` files the branch tracks, with no
untracked or ignored extras. So the report's count is not supported by the tree, and I could not
reconcile it. The claim that matters, that exactly these two tests fail, is confirmed.

### 10. Residual outside this arm's control (D12-class, not counted as a leak)
- D = 30 is the upper end of the 24–30 month range that
  `research/briefings/02-state-space-and-regimes.md:186-189` calls defensible from published
  persistence estimates. Those estimates are themselves fitted on post-war samples that overlap
  the 1994–2026 backtest.
- The slate was also designed after main's results were known, a forking path the registration
  names itself (`stated_in_advance.the_forking_path_this_does_not_remove`).
- That is the same weak, design-time class as D12. It was fixed at registration, before any arm
  existed, and was not chosen by this arm.
- There is no evidence of tuning. The briefing explicitly warns against setting kappa to preserve
  lambda2 (`:183-184`), and the code does not do so.
