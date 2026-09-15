# Research arm A4: two-timescale chains

> Written to disk by the orchestrator, verbatim from the text the arm agent returned. The harness
> refused the agent's own write of a report file ("Subagents should return findings as text"), and
> the agent did not route around it. Every number below should be checked against `paired.json` and
> `compare.json` in this directory, as the look-ahead reviewer's brief requires.

**Verdict under the pre-registered rule: CONFIRMED_IN_SAMPLE** (it also meets PROMISING), conditional
on the independent look-ahead review. One-year paired difference **+0.0590136743390319**; 90% interval
[0.027472602063961918, 0.08768502815065951]; 98.33% interval [0.01473722563546723, 0.10192460575098956].
Not HARMFUL: every interval at every horizon is above zero.

Branch `research/two-timescale-chains`. The run was made at `f5cbe91`, after the model (`3c7f8d8`),
wiring (`2d6fbc5`) and tests (`f5cbe91`) commits; `c1fc04e` adds the run's outputs. Exit codes:
check-gates 0 (all five gates), plain compare 1 (the verdict and the run's identity moved), paired
compare 0, `audit-look-ahead` 0. A0's files show exact zeros at every horizon and every exit code 0,
so this result counts.

The machine hibernated from 16:00:46 to 20:44:16. The process had used 9 min 18 s of CPU in 4 h 52 min
of wall clock, so it was paused, not stuck. It resumed where it stopped and was not interrupted.

## What changed

Two independent hidden Markov chains replace main's one. A growth chain drives the growth column; a
levels chain drives inflation and rates.

- The joint state is the pair of states, with transition matrix `kron(A_growth, A_levels)` and an
  emission log density equal to the sum of the two blocks'.
- Filtering is main's own forward pass over the 16 joint states, filtered only.
- Fitting is expectation maximisation over the joint states, with the expected counts summed down to
  each chain. That update is exact because the model's complete-data likelihood separates by chain.
- Each chain is sorted on its own before the joint states are formed.
- The burn-in rule chose **4 growth states × 4 inflation-and-rates states = 16** at 1994-03-01, on
  518 months (1950-12-01 to 1994-01-01).

| file | change |
|---|---|
| `models/two_timescale_hidden_markov_model.py` (new) | the model, a `GaussianHiddenMarkovModel` subclass; `TwoChainStateCount`, an int equal to the joint count that carries both chain counts; the fit; a loader for either kind of model |
| `models/two_timescale_state_selection.py` (new) | each chain's sweep and the joint table |
| `configuration/run_settings.py` | the switch `separate_chains_for_growth_and_for_inflation_with_rates`, True on this branch |
| `backtest/state_count_on_burn_in.py` | with the switch on, each chain is swept on its own block |
| `backtest/walk_forward.py` | fits two chains when handed a `TwoChainStateCount`; both counts in the cache key |
| `command_line_interface.py` | a two-chain branch in `fit-regimes`; the loader reads either kind of model |
| `pipeline_gates.py` | a gate-2 function for two chains |
| `tests/test_two_timescale_chains.py` (new) | 27 tests |

Not modified: the single-chain model file, the forecast composition, `look_ahead_audit.py`,
`regression_baseline.py`, `evaluation/`.

The tests check the joint model against independent computations: every joint path enumerated,
scipy's joint Gaussian, the joint likelihood equal to the sum of the two chains', the joint filter
equal to the product of the two chains' filters, and the joint second eigenvalue equal to the slower
chain's. **With one growth state the fit reduces to a single-chain fit on inflation and rates, and with
one levels state to a single-chain fit on growth, to 1e-8.** Full suite: 500 passed, 2 skipped; ruff
and mypy clean.

## Monotonicity

The monitored quantity stays the joint log likelihood, because the chain-marginalised update is the
exact maximiser and there is no prior. The shared allowance was not changed. Replaying the real 4×4
fits at 1994-03-01, 2010-03-01 and 2026-09-15 (20 restarts each, 2,138 update steps, each replay
reproducing the cached fit exactly): the joint log likelihood fell on **0 steps**, and the guard never
fired.

## Look-ahead audit

| path | status for this change |
|---|---|
| Training panel assembly | clean. The same `as_of` panel at each refit date, with the same boundary assertion and pre-flight. |
| Standardisation window | clean, untouched. The chains read the same expanding-standardised matrix. |
| State probabilities in forecasts | clean. The joint filtered distribution comes from the inherited forward pass; the backward pass runs only inside fitting on the refit-date panel, as in main. A test shows earlier filtered rows are unchanged when later months are appended. |
| Model parameters at each refit | clean. Both chains are refitted from scratch at every refit date from 1994-03-01 onward, with seeds derived from the date. |
| Number of regimes | clean. Both counts are chosen once, on the panel ending 1994-01-01, strictly before 1994-03-01. The cap of 4 comes from the pre-registration. |
| Conditional rates | clean, code unchanged. Rates are now per joint state, and the evidence behind each forecast is thinner: mean effective sample size fell from about 118 to about 46 months. |
| Benchmark, outcome resolution | untouched. |
| Condition values feeding rate estimation | the D5 approximation, unchanged. |
| Run settings | clean. One boolean switch, plus constants (the cap of 4, the seed offset of 1) not derived from data. |
| Acceptance thresholds | untouched. |
| Canonicalisation | clean. A fixed sort within each chain. |
| Indicator thresholds | weak (D12), unchanged. |
| Future-perturbation invariance | **pass**, exit 0 at cutoff 2000-03-01: all 2,190 rows identical, 16 regimes and 7 fits computed from scratch in both runs, 627,617 values perturbed, 378 s. |

## Results

Paired differences, arm minus main, from `paired.json`:

| horizon | main skill | arm skill | difference | 90% interval | 98.33% interval |
|---|---|---|---|---|---|
| 12 months | +0.2154 | +0.2744 | +0.0590 | [+0.0275, +0.0877] | [+0.0147, +0.1019] |
| 60 months | +0.0728 | +0.1192 | +0.0465 | [+0.0249, +0.0953] | [+0.0132, +0.1295] |
| 120 months | −0.3528 | −0.1673 | +0.1855 | [+0.0843, +0.2228] | [+0.0700, +0.3834] |

- **Verdicts under 0001 (secondary endpoint only):**
  - 1 year flips from SHIP BASE RATE to **SHIP MODEL**, with calibration error 0.0870 against main's
    0.1250.
  - 5 years stays SHIP BASE RATE, failing skill, calibration and robustness; calibration error 0.1539
    against 0.1942.
  - 10 years stays SHIP BASE RATE, failing skill, calibration and honesty (total variation 0.0499
    against a floor of 0.05). It now passes robustness; calibration error 0.0937 against 0.1156.
- **Per-indicator scores (`compare.txt`):** log loss fell on 26 of 30 indicator-horizon rows and
  calibration error on 25 of 30.
- **λ2:** at every refit the joint λ2 equals the levels chain's. Medians over 34 refits: joint 0.9821
  (half-life 38 months), growth 0.9464 (13 months), main's six-state model 0.9777 (31 months). Today's
  fit: 0.9802 against main's 0.9831. The information horizon is 60 months for both.

## Verdict arithmetic

The 98.33% level is 1 − 0.10/6 (Bonferroni across the six arms). The one-year 98.33% interval's lower
bound, 0.0147, is above zero, so the arm is CONFIRMED_IN_SAMPLE, conditional on the independent
look-ahead review.

## Prediction versus outcome

- Predicted: one-year skill on any-time-within-horizon questions rises. Partly right. Four of the five
  any-time indicators rose, but their mean gain is about +0.030 against about +0.088 for the
  at-horizon indicators (the arm's arithmetic from `paired.json`). The largest one-year gain is the
  funds rate above 4% at the horizon, +0.1828, and unemployment above 7% within the horizon fell by
  0.0423.
- Predicted: joint λ2 equals the slower chain's. Confirmed exactly at every refit.
- Predicted: information horizon roughly unchanged. Confirmed, at 60 months.

## Deviations, with reasons

1. **Two existing test files edited, assertion counts unchanged.** The brief's "default on the branch"
   rule collides with tests that pin main's configuration as the default.
   - `test_configuration_hash_compatibility.py`: the shipped settings now name the new switch at
     False, as they already do the other two switches. The omission-map membership set gains the new
     key, which is the path that test's own docstring prescribes.
   - `test_honest_start_date_against_the_live_cache.py`: the 1994-03 and 1971-12 burn-in tests now
     name main's configuration explicitly, with the switch off.
   - No test was deleted. This needs the owner's review because the brief says tests are additive only.
2. **The switch was added to the hash-omission map at False.** At False the code is main's, and a new
   test proves the hash then equals main's reference `ad7fcc1affd0746a`.
3. **`test_cached_fits_reproduce_byte_for_byte.py` now skips on this branch.** The default hash
   differs, so no cached six-state file matches its name.
4. **Decided before the run, not in the pre-registration:**
   - The regimes-exist check reads the joint table of every pair of chain counts. Its null is the 1×1
     two-chain model, a Gaussian with growth independent of inflation and rates, not main's single
     full-covariance Gaussian.
   - Gate 2 asks the same five requirements: persistence and population of each chain, flicker of the
     joint regime path.
   - The runner-up state count is recorded as None.
   - The levels chain draws starting points from seed + 1.

## Surprises and caveats

- The effect is far larger than the slate expected for any single arm.
- The arm changes the structure and the number of joint states (16 against 6) at once, with fewer
  parameters than main (58 against 89, the arm's count), so the gain cannot be attributed to the
  timescale split alone.
- Because the joint likelihood factorises, this model is equivalent to fitting the two chains
  separately and forecasting on their product.
- At ten years, "recession within ten years" improved by +0.7300, the D4 compounding case.
- Today's joint regime path switches 1.52 times a year, under the ceiling of 2.0 but closer to it than
  main.
- Not done: the independent look-ahead review, and the REPORT.md write refused above.

Scratch diagnostics are in the session scratchpad (`a4_monotonicity.py` and `.log`,
`a4_burn_in_replay.log`).
