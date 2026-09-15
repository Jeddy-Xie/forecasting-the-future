# Look-ahead review: arm A4, two-timescale-chains (experiment 0002)

I did not write this arm and have no stake in whether it passes. Reviewed 2026-09-15.

- **Change reviewed:** `git diff 2e025b7...research/two-timescale-chains`. The branch head is 7e10cf9.
  - The code is in commits 3c7f8d8, 2d6fbc5 and f5cbe91.
  - c1fc04e and 7e10cf9 add only the 8 output and report files under `research/arms/two-timescale-chains/`. `git diff --stat f5cbe91 research/two-timescale-chains` shows 8 files, 5,616 insertions and no source or test file.
- **Files:** in `src/…` and `tests/…` paths below, line numbers are on the branch, from `git show research/two-timescale-chains:<path>`. Output files are cited by their name in the worktree.
- **Scope of my own work:** I modified nothing in the arm's branch, worktree or caches. Every script I ran lived in the session scratchpad, and each ran against a `git archive` export of the branch.

## two-timescale-chains
VERDICT: CLEAN

I found no way for information from after a forecast date to reach that forecast, in the backtest or in today's forecast.

The change adds three things:
- a new emission density, the sum of two block Gaussians;
- a new maximisation step, which marginalises the expected counts to each chain;
- a new way of choosing the state count, the same rule run once on each block.

Each of these reads only the panel that main already assembles `as_of` the refit or forecast date. The arm touches none of the following:
- outcome resolution;
- the climatology benchmark;
- conditional-rate estimation;
- the data layer and the standardisation.

It writes no second copy of any publication boundary. The forecasts use only the inherited forward pass, which is filtered, and I showed by mutation that the arm's test would catch a switch to smoothed probabilities. The result is large, but I could not trace any part of it to a leak. The honest caveat is attribution, not leakage: see check 7 below.

### 1. Deterministic audit: passed

- `exit_codes.json` records `look_ahead_audit_exit: 0` at commit f5cbe91, the last code commit.
- `look_ahead_audit.txt` records:
  - `PASS: no forecast issued on or before 2000-03-01 changed when every observation unavailable at 2000-03-01 was perturbed`;
  - 2,190 rows, 7 refits and 627,617 values perturbed;
  - "16 regimes chosen on the burn-in window" in both the original and the perturbed run.
- The cap is 4 per chain, so a joint count of 16 can only be 4x4. The audit's equality on `state_count` therefore also pins the factorisation.
- The audit stops at 2000-03, but it still covers everything after that date. The diff adds no logic that depends on the date. The only date term is the fit seed, `settings.random_seed + as_of.year * 100 + as_of.month`, at `backtest/walk_forward.py:256`. That is main's expression, moved up a few lines and unchanged. Every refit from 2001 to 2026 runs the code path the audit exercised.

### 2. Every value the change introduces, traced to its inputs

| New quantity | Estimated at | Latest observation it can touch | What enforces it |
|---|---|---|---|
| Growth-chain and levels-chain state counts (4, 4) | once, first forecast date 1994-03-01 | label 1994-01-01, the last row of the burn-in panel (518 months, 1950-12-01 to 1994-01-01, per the cached choice `burn_in_state_count_choice_1994-03-01_seed20260908_fec79a040f9ca6f9.json`) | `backtest/state_count_on_burn_in.py:185` assembles the panel `as_of` the first forecast date; `:189` raises unless `panel_end < first_forecast_date` (strict `<`). The two-chain branch (`:198-228`) runs after that assertion, on the same `matrix.values`. |
| Growth and levels chain parameters (means, covariances, transition matrices, initial distribution) | every refit date t (33 refits, 1994-03 to 2026-03) | the last row of `assemble_point_in_time_panel(registry, t, cache)`, main's `as_of` panel with main's vintage and publication-lag rules, unchanged | `backtest/walk_forward.py:234-236` builds the matrix; `:257-266` fits two chains on exactly that matrix. `models/two_timescale_hidden_markov_model.py:319-422` (`fit`) reads only its `observations` argument: k-means++ starting points and pooled covariances come from that array (`:356-361`). |
| Joint filtered distribution at forecast date s | every forecast date s | the last row of the `as_of`-s panel | `walk_forward.py:349-352` computes `filtered_state_probabilities(matrix.values)[-1]`, main's code, unchanged. The subclass does not override `filtered_state_probabilities` or `_forward` (checked programmatically, see check 2). |
| Conditional rates per joint state | every refit date t | outcomes and conditions admitted by main's `condition_available_at(history, t)` | `walk_forward.py:281-299`, unchanged. The rates are fed filtered probabilities (`:281`), never smoothed ones. |
| Transition matrix used for projection | every refit date t | same as the chain parameters | `np.kron(A_g, A_l)` at `two_timescale_hidden_markov_model.py:205-207`. |

**Outcome-resolution timing, the channel the brief says to check hardest.**
- The diff does not touch `_expanding_climatology`, `condition_available_at`, `prepare_indicator_history` or `indicator_forecast.py`. The diff stat names no file under `evaluation/`, `data/` or `features/`, and none of the model modules other than the two new files.
- The arm reuses the one boundary main already has. It does not write a second one.

**D5 (revised values of observations published before the cutoff).**
- The arm reads exactly the three columns of main's observation matrix, split by name at `two_timescale_hidden_markov_model.py:90-96`. It reads no series, vintage or current-vintage file that main did not already read.
- It therefore opens no new route into the D5 approximation.

### 3. Hyperparameters, and how many times the arm ran

- **Registered values.** At 2e025b7 (committed 15:22), `experiment.json` registers `state_count_per_chain` as "candidates 1 to 4 … on the point-in-time panel at the first forecast date" and `maximum_product_states` as 16. The arm's first commit came at 15:46.
- **In the code:**
  - The cap is the constant `MAXIMUM_STATES_PER_CHAIN = 4` at `two_timescale_hidden_markov_model.py:99`.
  - It is applied to main's unchanged `hidden_state_counts_to_search = (1, 2, 3, 4, 5, 6)` at `models/two_timescale_state_selection.py:47-62`, giving candidates 1 to 4.
  - The branch changes nothing under `proving/`.
- **Constants the pre-registration does not fix.** Two exist, and neither is derived from data:
  - the levels-chain seed offset of 1 (`:103`);
  - the choice to canonicalise each chain on its own.
- **One run.**
  - `git log` shows a single outputs commit, c1fc04e.
  - The arm's cache holds exactly one burn-in choice under the arm's configuration hash, fec79a040f9ca6f9.
  - It holds 34 `states4x4` fit files: the 33 refits plus today's fit, dated 2026-09-15. There are no fit files for any other chain pair under that hash.
  - The report mentions scratch replays of three fits for the monotonicity check. It says those replays reproduced the cached fits exactly, so they are not a second run with different settings.
- **The cap binds.** Both chains chose the ceiling of 4, and held-out likelihood was still improving at 4:
  - growth: -0.4221 per month at 3 states, -0.0416 at 4;
  - inflation and rates: -2.0013 at 3 states, -1.7326 at 4.

  The registered cap, not the data, therefore set the size of the model. That is not a leak, because the cap was fixed before any arm ran. It is still the design-time channel of D12's kind. The hypothesis itself was motivated by λ2 values measured on the point-in-time panels up to 2026 (0.943 for growth alone, 0.973 to 0.984 for inflation and rates). Experiment 0002 already discloses this under `the_forking_path_this_does_not_remove`, and it is why CONFIRMED_IN_SAMPLE is the strongest claim available. The arm did not add to that channel.

### 4. Today's forecast

`forecast_now` (`command_line_interface.py:344-406`) is as free of look-ahead as the backtest, and it runs the same structure through the same code path:

- It reads the selected model (`:348`) through `regime_model_from_dictionary`, so a two-chain payload keeps its `TwoChainStateCount`.
- It passes `selected.state_count` (`:366`) to `walk_forward.fit_regime_model(today, …)` (`:360`). That is the backtest's fitting function, so today's model is `two_timescale.fit` on the `as_of`-today panel, with the date-derived seed.
- It uses only `fitted.model.filtered_state_probabilities(matrix.values)` (`:369`), and `filtered[-1]` issues the forecast (`:379`).
- The state count for today comes from `_fit_two_timescale_regimes` (`:305-341`). That function sweeps each block on today's panel, which contains only data published by today. Main's live path does the same thing with its single chain, so this is no new leak.
- In `check_gates.log`, today's sweep also chose 4x4 (line 57), so the live model has the same structure as the backtested one. The cache holds `model_2026-09-15_states4x4_seed20260908_fec79a040f9ca6f9.json`.
- Today's gate 2 uses `describe_regimes` (smoothed, `models/state_labelling.py:173`) and Viterbi only as narrative and diagnostics, as main does. Neither feeds a forecast.

### 5. The seven checks the orchestrator asked for

**Check 1: state counts chosen strictly before the first forecast date. Confirmed.**
- The two-chain sweep sits inside `choose_state_count_on_burn_in_window`, after the strict boundary assertion (`state_count_on_burn_in.py:189`), and uses the same burn-in `matrix` (`:201-208`).
- The choice is cached under `_cache_name` (`:149-159`), keyed by the first forecast date and the configuration hash. That hash includes the new switch when it is True (`configuration/run_settings.py:157`, `:169`), so main's six-state choice (ad7fcc…) cannot be read in its place.
- `run_walk_forward` takes the count as a fixed argument (`walk_forward.py:314`) and never re-selects it.
- The cap of 4 is a constant. It is not read from any panel.
- The cached choice records `panel_end` 1994-01-01, `chosen_as_of` 1994-03-01 and 518 months. These are identical to main's choice on the same panel.

**Check 2: filtered, never smoothed, in every forecast. Confirmed, and the arm's test discriminates.**
- `TwoTimescaleHiddenMarkovModel` overrides only these members (`two_timescale_hidden_markov_model.py:216-270`):
  - `state_count`
  - `free_parameter_count`
  - `log_emission_probabilities`
  - `to_dictionary` and `from_dictionary`

  The emission density is computed month by month, with nothing carried across months (`:239-242`).
- On the branch, `smoothed_state_probabilities` and `_backward` are called in only three places:
  - inside expectation maximisation on the refit panel (`two_timescale_hidden_markov_model.py:459`, and main's `gaussian_hidden_markov_model.py:550`);
  - in `describe_regimes` (`state_labelling.py:173`, narrative);
  - in the sweep's population-share floor, on the training part of the burn-in panel (`state_selection.py:222`).

  None of them produces a forecast.
- The test `test_joint_filtered_probabilities_at_a_month_ignore_everything_after_it` exists (`tests/test_two_timescale_chains.py:226-231`). It compares, for exact equality, the rows filtered from 3 months against the first 3 rows filtered from 5.
- **Mutation check (scratchpad script `mutation_filtered.py`, run on the export):**
  - The subclass defines neither `filtered_state_probabilities` nor `_forward` itself.
  - Real filtering passes the test.
  - With `GaussianHiddenMarkovModel.filtered_state_probabilities` monkeypatched to the smoothed method, the test fails, with a largest difference of 0.396.
  - The joint filter equals the Kronecker product of the per-chain filters on every prefix.
- **Test run:** from the export, with `ECONOMIC_REGIME_FORECASTING_CACHE` pointed at an empty scratch directory, `pytest` on `test_two_timescale_chains.py` plus `test_configuration_hash_compatibility.py` gave 34 passed, exit 0.

**Check 3: the fitted-model cache key carries both chain counts. Confirmed, with no collision.**
- The key is `model_{as_of}_states{label}_seed{seed}_{configuration_hash}.json` (`walk_forward.py:240-246`).
- The label is `"{K_g}x{K_l}"` for a `TwoChainStateCount` (`two_timescale_hidden_markov_model.py:144-147`), so 2x4 and 4x2 get different keys. Main's files read `states6_…_ad7fcc1affd0746a`, while the arm's read `states4x4_…_fec79a040f9ca6f9`, which differ in both the label and the hash.
- On a cache read, `regime_model_from_dictionary` (`:273-283`) dispatches on `model_class`, and refuses an unknown one.
- The single-chain loader cannot misread a two-chain payload, because that payload has no product-space arrays (`:246-257`). A test pins this (`tests/test_two_timescale_chains.py:264`).
- The one weak point is the guard `if model.state_count != state_count` at `walk_forward.py:251`. It compares joint integers, so on its own it would accept 2x8 for 4x4. That does not matter here: the key already separates them, and the cap makes 16 = 4x4 the only possibility.

**Check 4: today's forecast. Confirmed. See section 4.**

**Check 5, the null in "regimes exist": a separate finding, outside the VERDICT. See below.**

**Check 6: the two existing test files that were edited. No assertion was removed or loosened, and the covenant passed the edits by measurement.**
- I counted assertions with the covenant's own regex, via the scratchpad script `count_assertions.py`:
  - `test_configuration_hash_compatibility.py`: 8 before, 8 after. The assertion lines are identical as a multiset, and the 7 test functions are unchanged.
  - `test_honest_start_date_against_the_live_cache.py`: 17 before, 17 after. Again the lines are identical as a multiset, with 7 test functions unchanged.
- **The edits:**
  - The shipped-hash test names the new switch at False (hunk `@@ -33,6 +33,9 @@`), exactly as it already names the other two switches. It still asserts the same `SHIPPED_HASH`.
  - The omission-map test (`@@ -113,4 +116,6 @@`) adds the new key to an exact set equality. That changes what is pinned, but the equality stays exact, so it is not looser. The test's name still says "the two documented switches" while it now pins three. That is naming drift, not weakening.
  - The two burn-in tests (`@@ -107,13 +107,20 @@` and `@@ -130,7 +137,9 @@`) now pass main's settings explicitly with the switch off. They still assert `state_count == 6` and runner-up 2, unchanged.
- **How the covenant treated it:**
  - The arm agent's transcript (`subagents/agent-afd7f328da75d187c.jsonl`) shows all four edits were made with the Edit tool, and every one returned "updated successfully". So they went through the covenant hook (`crucible/…/scripts/protect_tests.py`), not around it through the shell.
  - They passed rule 2 because no replaced span lost an assertion. Each span kept its `assert`, or had none on either side.
  - Rule 1, which bans all test edits during a build phase, could not fire. The worktree has no `.plan/ACTIVE`.
  - By contrast, A6's blocked edit (`subagents/agent-a1e83c447789f0003.jsonl`) rewrote a test function in `test_configuration_hash_compatibility.py`. The hook measured it as dropping that span from 2 assertions to 1, which counts as weakening. A4's edits only added keyword arguments and a set member, so the difference is real, not luck.
- **Coverage lost without an edit.** `test_cached_fits_reproduce_byte_for_byte.py` now skips on this branch, as the report's deviation 3 says, because the default hash changed. This test was not edited. Still, it means a check disappears on the branch, and the owner should know.

**Check 7, the attribution caveat: the parameter counts are right, and the caveat is stated honestly.**
- Main's six-state, three-dimensional, full-covariance model has 5 + 30 + 18 + 36 = **89** parameters (initial distribution, transitions, means, covariances). That matches `free_parameters` 89 in main's burn-in sweep row.
- The arm's growth chain (4 states, 1 dimension) has 3 + 12 + 4 + 4 = 23. Its levels chain (4 states, 2 dimensions) has 3 + 12 + 8 + 12 = 35. Together that is **58**, matching the joint row `free_parameters` 58 and the formula at `gaussian_hidden_markov_model.py:299-315`.
- REPORT.md, under "Surprises and caveats", says the gain "cannot be attributed to the timescale split alone": the arm changes the structure and the number of joint states (16 against 6) at once, with fewer parameters. That is accurate. I would add one point to it. The arm's regimes carry thinner evidence per forecast: mean effective sample size is about 48 against about 122, computed over every forecast row, and 45.3 against 112.4 in `compare.json`'s indicator rows. Even so, calibration improved on 25 of 30 indicator-horizon rows. The effect is consistent across horizons, which argues against a one-cell artefact. It is not an attribution.

### 6. The report's numbers against `paired.json` and `compare.json`, extracted by code

| Claim in REPORT.md | File value | Result |
|---|---|---|
| 12 months: difference +0.0590136743390319; 90% [0.027472602063961918, 0.08768502815065951]; 98.33% [0.01473722563546723, 0.10192460575098956] | identical to every digit shown (`paired.json` `horizons[0]`) | matches |
| 12 months: main +0.2154, arm +0.2744 | 0.21537738742364834, 0.27439106176268024 | matches |
| 60 months: +0.0465, 90% [+0.0249, +0.0953], 98.33% [+0.0132, +0.1295] | 0.0464788, [0.024861, 0.095348], [0.013224, 0.129477] | matches |
| 120 months: +0.1855, 90% [+0.0843, +0.2228], 98.33% [+0.0700, +0.3834] | 0.1854765, [0.084319, 0.222772], [0.069981, 0.383395] | matches |
| Not HARMFUL: every interval above zero | all six lower bounds > 0 | matches |
| CONFIRMED_IN_SAMPLE: the 98.33% lower bound 0.0147 > 0 | 0.01473722563546723 | matches. 1 − 0.10/6 = 0.98333, so the 0.9833 level is the registered Bonferroni level |
| 1 year flips to SHIP MODEL | `compare.json`: verdict `SHIP BASE RATE -> SHIP MODEL`; failing gates `calibration -> none` | matches |
| Calibration error at 1 / 5 / 10 years: arm 0.0870 / 0.1539 / 0.0937; main 0.1250 / 0.1942 / 0.1156 | arm: `check_gates.log` lines 171, 178, 185. Main: the A0 control's `check_gates.log` | matches |
| 10 years now passes robustness | failing gates go from `skill, calibration, robustness, honesty` to `skill, calibration, honesty` | matches |
| 10-year honesty, total variation 0.0499 | `check_gates.log` line 187 | matches |
| Log loss fell on 26 of 30 rows; calibration error on 25 of 30 | 26 of 30 (`logarithmic_loss`), 25 of 30 (`expected_calibration_error`) | matches |
| Largest 1-year gain: funds rate above 4% at the horizon, +0.1828. Unemployment above 7% within the horizon, −0.0423 | +0.1828, −0.0423 (`paired.json` `indicators`) | matches |
| Within-horizon: 4 of 5 rose, mean about +0.030. At-horizon mean about +0.088 | 4 of 5, +0.02967 and +0.08836 | matches |
| Recession within ten years +0.7300 | +0.7300 | matches |
| λ2 medians over 34 refits: joint 0.9821, growth 0.9464. Main 0.9777. Today 0.9802 | recomputed from the cached fit files: over all 34 files, 0.9821 and 0.9464. Over the 33 refits alone, 0.9823 and 0.9465. Main's 33 files, 0.9777. Today's file, 0.9802. The joint λ2 equals the levels chain's in every file | matches. The "34" counts today's fit as a refit (33 refits + 1). I did not verify main's 0.9831 for today |
| Effective sample size about 118 falling to about 46 | 112.4 → 45.3 (`compare.json` indicator-row means); 121.8 → 48.1 (mean over forecast rows, A0 control against the arm) | matches within its "about" |
| Exit codes: check-gates 0, plain compare 1, paired 0, audit 0 | `exit_codes.json` | matches |

None of the report's numbers is unsupported by the files.

### Separate finding, outside the VERDICT: would the 0001 SHIP MODEL claim survive main's full-covariance null?

Yes, by a wide margin.

**What the 0001 verdict reads.** Its regimes-exist gate uses the burn-in joint table. The evidence line in `check_gates.log` (line 169), "-1.7742 against -3.6661 … 1,891 against 3,310", matches the arm's cached burn-in choice exactly.

**Both nulls were computed on the identical panel.** The arm's cached burn-in choice and main's (`burn_in_state_count_choice_1994-03-01_seed20260908_ad7fcc1affd0746a.json`) cover the same 518 months, 1950-12-01 to 1994-01-01. Both hold out the same last fifth of 104 months (`state_selection.py:43`, `:196`). The joint held-out likelihood is exactly the sum of the two chains' held-out likelihoods, because the joint likelihood factorises. So the two sets of numbers can be compared directly.

| | held-out log likelihood per month | Bayesian information criterion |
|---|---|---|
| Arm's 4x4 (best multi-regime) | −1.7742 | 1,890.9 |
| Arm's null, 1x1, block-diagonal | −3.6661 | 3,310.1 |
| **Main's null, one full-covariance Gaussian** | **−3.5864** | **3,217.6** |

- **The restricted null did make the gate easier, but only slightly.** Main's full-covariance null beats the arm's block-diagonal null by 0.080 nats per month and 92.5 criterion points.
- **Against main's null the gate still passes easily:** by 1.81 nats per month on held-out likelihood, and by 1,327 criterion points.
- **The other one-year gates do not depend on the null:**
  - skill +0.2744, interval [+0.1731, +0.3712];
  - calibration 0.0870;
  - robustness 4 of 4;
  - honesty 0.4575.

The one-year SHIP MODEL therefore stands under main's null as well.

**Two caveats:**
- Today's gate 2 in `fit-regimes` also uses the 1x1 null (−4.1834 against −1.9887). I did not compute a full-covariance null for today's panel. That check is not the input to the 0001 verdict.
- Experiment 0002 deliberately declines to count a 0001 verdict flip as evidence (`why_not_the_0001_verdict`). The one-year calibration gate here passes at 0.0870, below the 0.10 bar, and briefing 01 estimates that a perfectly calibrated forecaster fails that bar about 91% of the time at this sample size. So this finding supports the secondary endpoint and nothing more.
