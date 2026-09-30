# Research arm B1: point-in-time questions through the condition chain

> The arm agent's own write of this file was refused by the session harness ("Subagents should return
> findings as text"); it returned this text and did not route around the refusal. The coordinator
> committed it verbatim after checking the paired differences, the exit codes and the identity file
> against `paired.json`, `exit_codes.json` and `one_regime_identity.json`. One note from the
> coordinator: "0007's calibration test is not implemented in the package" was true of this branch,
> cut at 99f232d; main gained it later the same day (39dd1c8).

Experiment 0008 (`proving/experiments/0008-condition-aware-regime-forecasts/experiment.json`), arm `B1-point-in-time-through-the-condition-chain`. Branch `research/point-in-time-through-the-condition-chain`, cut from main at `99f232d`. Implementation and tests `937b331`. The pre-registered one-regime diagnostic was run and committed in `d775bca` before the scored run. The scored run was made on `d775bca`, and its outputs are in `dde0dca`. There was one scored run with the registered values: shrinkage 10, seed 20260908, and the state count chosen as main chooses it (16 = 4 x 4, on the burn-in panel as of 1994-03-01). Nothing was tuned, swept or re-run.

**Verdict under the registered rule: CONFIRMED_IN_SAMPLE, with no HARMFUL horizon.**
- One year, model-sample benchmark, paired against reference-0008: +0.05348611278922169.
- 90% interval [+0.025912735878650638, +0.08567640250674091]; 96.67% interval [+0.017355053792609352, +0.09404928610160221].
- The deterministic half of the VOID rule passed: `forecast audit-look-ahead` exited 0 at both standing cutoffs.
- The verdict is provisional until the independent judged look-ahead review and the CONTROL arm come back.
- It is in-sample: the arm was designed after the per-indicator results were seen.

## What changed

One setting, `RunSettings.compose_point_in_time_questions_through_the_condition_chain`, is `True` on this branch.

**The composition.** A point-in-time question asks whether the condition holds in month h after the forecast date. B1 answers it with `compose_through_the_condition_chain`, the existing function in `src/economic_regime_forecasting/models/indicator_forecast.py`, fed with the model's own inputs:
- the fitted model's `transition_matrix` (16 x 16 in the two-chain default);
- the filtered regime distribution at the forecast date, `filtered_state_probabilities(...)[-1]`, the same vector main already projects;
- the model's own `entry_hazard` and `persistence`, which the any-time path already estimates at every refit (nothing new is estimated);
- the last published value of the condition (`walk_forward.condition_available_at`);
- the number of months from that value's label to the forecast date (`walk_forward.months_between`). The chain steps these months first, then the horizon.

**Where.** `forecast_indicator` gains two keyword arguments: `point_in_time_through_the_condition_chain` and `months_since_condition_last_published`. Asking for the chain without the gap raises an error. The setting and the gap are passed in both places a point-in-time forecast is composed:
- `backtest/walk_forward.py`, `run_walk_forward`. The gap it already computed for the reference chain is now a named variable, `publication_gap`, and is passed to both. The look-ahead audit and `skill-by-horizon` run through this same path.
- `command_line_interface.py`, `forecast_now`. Today's grid uses the same gap, `months_between(last published label, today)`, and stops with a message if an indicator has no published condition.

**Unchanged:**
- any-time questions;
- the effective sample size, the distance to the stationary distribution and the projected distribution stored beside each forecast;
- both benchmark columns and the reference-chain column.

**Off switch.** `False` reproduces main. The setting is left out of the configuration hash when it is `False`, so the off configuration hashes to reference-0008's `fec79a040f9ca6f9`, and a test pins that. The arm itself hashes to `4fba792cff42d89e`.

**Tests.** The new file is `tests/test_point_in_time_through_the_condition_chain.py`, with 21 tests. They pin:
- the function-level identity at one regime, by array equality and against the closed form;
- that with regimes, B1 equals the joint chain run on the model's own parameters;
- that any-time forecasts and every diagnostic are unchanged;
- that whether the condition holds now changes a point-in-time answer only through the chain;
- the error when the gap is missing;
- both halves of the end-to-end identity at small scale on synthetic data;
- that with regimes, the setting moves only point-in-time `predicted_probability`;
- that the small-scale look-ahead audit passes with the setting on;
- that `forecast-now` is wired correctly with the setting on and off;
- the configuration hash.

Three existing tests were extended, none loosened:
- the shipped-hash test in `tests/test_configuration_hash_compatibility.py` now sets the new field to its shipped value;
- so does `test_with_the_switch_off_the_hash_is_main_reference_runs` in `tests/test_two_timescale_chains.py`;
- the test pinning which settings the hash omits gains one entry.

**Checks on `937b331`,** run with `PYTHONPATH` at this worktree's `src/` (verified):
- `pytest -m "not network"`: all passed;
- `ruff check .`: clean;
- `ruff format --check .`: clean;
- `mypy`: no issues in 44 files;
- `scripts/layer_check.py`: OK.

**Scripts in this directory,** none imported by `src/`:
- `one_regime_identity.py`: the registered diagnostic and both registered secondaries;
- `starting_condition_revisions.py` and `starting_condition_from_vintages.py`: the class-B path described below;
- `rule_0007_secondaries.py`.

## Look-ahead audit

This is the table from `docs/TECHNICAL_DEBT.md`, filled in for this change. The schedule is 391 forecast dates, 1994-03-01 to 2026-09-01.

| path | touched? | status for B1 |
|---|---|---|
| Training panel assembly | no | Unchanged. The filtered distribution comes from the panel assembled `as_of` the forecast date. Its last month is 2000-01 at 2000-03-01 and 2022-01 at 2022-03-01. 0 of 391 dates use the fallback. |
| Standardisation window | no | Unchanged; expanding. |
| State probabilities used in forecasts | yes, read | The chain starts from `filtered_state_probabilities(...)[-1]`, which main already projects. Filtered, never smoothed. |
| Model parameters at each refit | yes, read | Uses `model.transition_matrix`, already used by the projection and the any-time path, from the latest refit on or before the forecast date. |
| Number of regimes | no | 16 (4 x 4), chosen once on the burn-in panel (1950-12-01 to 1994-01-01) as of 1994-03-01, exactly as main chooses it. |
| Conditional rates | yes, read | Uses `entry_hazard` and `persistence`, already estimated at each refit from conditions published by the refit date (lag rule, or announcement dating for recessions per ADR 0011). No new estimation. Debt D14 unchanged from main. |
| Benchmark (climatology) | no | Neither benchmark reads a prediction. Keys are identical and there are 0 outcome disagreements with reference-0008. |
| Outcome resolution | no | Unchanged. |
| Condition values feeding rate estimation | **yes, extended** | The last published condition now enters every point-in-time forecast directly. On main it entered only any-time forecasts and rule 0007's reference chain (R2). It is read like every other condition: final values, publication timing enforced. The starting month is the forecast month minus 2 (at most 3) for unemployment, consumer prices, the funds rate and industrial production. For recession dating it is 14 to 21 months back (1999-01 at 2000-03-01; 2021-01 at 2022-03-01). This is a class-B (D5) approximation under rule 0007; it is measured below. |
| Every run setting | yes | One new boolean, fixed in advance by the registration. |
| Acceptance thresholds | no | Nothing under `proving/` was edited. |
| Canonicalisation rule | no | Unchanged. |
| Indicator thresholds | no | D12, as on main. |
| Future-perturbation invariance | run | Passes with B1 on. At 2000-03-01: exit 0, all 2,190 rows identical (73 dates, 7 refits), 435 s. At 2022-03-01: exit 0, all 10,110 rows identical (337 dates, 29 refits), 1,891 s. The starting condition and the gap both come from `condition_available_at`, which the audit perturbs past the cutoff. By design it does not cover revised values (D5) or a wrong registry lag (D14-class). |

**The class-B path, measured.** `starting_condition_revisions.json` compares, at every forecast date, the starting condition B1 reads from the final file with the same month in the archival vintage dated that forecast date, where one is cached:

| point-in-time indicator | dates compared | condition differs |
|---|---:|---:|
| industrial production growth above 2% | 389 of 391 | **58** |
| consumer price inflation above 3% | 391 of 391 | 6 |
| unemployment above 5% | 35 (vintages cached only at refit dates) | 0 |
| recession at the horizon date | 14 (18 of the cached vintages are empty) | 0 |
| funds rate above 4% | not revised | exact |

On two industrial-production dates, 2025-11-01 and 2025-12-01, the 47-day registry lag says 2025-09 and 2025-10 had been published, but the vintage ends at 2025-08. That is a registry-lag error of the D14 kind. Neither forecast has resolved at any horizon, so neither is in any score.

`starting_condition_from_vintages.py` replays B1's walk-forward on the scored run's cached fits. It changes one thing: the starting condition and its month for the consumer-price and industrial-production point-in-time indicators are read from the vintage dated the forecast date. That changes 66 dates and moves 198 forecast rows; the per-regime rates are left as they are. Against reference-0008, model-sample benchmark:

| horizon | as scored | corrected | 90% (corrected) |
|---|---:|---:|---|
| 12 | +0.05348611278922169 | +0.0530895973183253 | [+0.025760573809889727, +0.08512904087245642] |
| 60 | +0.0016206848289905956 | +0.0016206005657551925 | [-0.006465799798465903, +0.006805515883472888] |
| 120 | -0.003966001328490815 | -0.003966000659176433 | [-0.008191515656044479, +0.0019573254789735563] |

At one year the corrected 96.67% interval is [+0.01732655993541358, +0.09367540467089575]. The shift is -0.0003965154708963914, which is under rule 0007's 0.001 threshold, and no verdict moves. Under that rule this would be recorded, not voided, with +0.0531 as the reported number. This is the arm author's measurement; the independent reviewer has to make their own.

## Results

Quoted from `paired.json`, `paired_series_start.json` and `compare.json`. Paired comparisons used 10,000 resamples, seed 20260908, blocks as long as the horizon, and one set of resamples for both levels. 9,702 resolved forecasts are in both runs, 0 are on one side only, and 0 outcomes disagree.

**Primary: model-sample benchmark** (`paired.json`):

| horizon | reference-0008 | B1 | difference | 90% | 96.67% |
|---|---:|---:|---:|---|---|
| 12 | 0.17859594038965293 | 0.23208205317887462 | **+0.05348611278922169** | [+0.025912735878650638, +0.08567640250674091] | [+0.017355053792609352, +0.09404928610160221] |
| 60 | 0.0689640064251977 | 0.0705846912541883 | +0.0016206848289905956 | [-0.0064666156768923505, +0.006805420616026989] | [-0.00888253299183739, +0.007982859016629668] |
| 120 | -0.21091324039179402 | -0.21487924172028483 | -0.003966001328490815 | [-0.008191516196661105, +0.001957326199970431] | [-0.010778499662786732, +0.0027405513519647667] |

**Secondary: series-start benchmark** (`paired_series_start.json`):

| horizon | difference | 90% | 96.67% |
|---|---:|---|---|
| 12 | +0.05168298553524808 | [+0.025017905459806058, +0.07879677910618393] | [+0.016613580836830736, +0.08595497226101205] |
| 60 | +0.0015538499250699334 | [-0.006581143528725525, +0.0067982916978082475] | [-0.009044467576228057, +0.007913150789405686] |
| 120 | -0.0023248412571270083 | [-0.0030994005023469314, +0.0037767783979945273] | [-0.003970111955852597, +0.0046486028699746435] |

**Per indicator, one year, B1 minus reference-0008** (model-sample, point estimates):

| indicator | difference |
|---|---:|
| unemployment_rate_above_five_percent_at_horizon | +0.31771885599207994 |
| federal_funds_rate_above_four_percent_at_horizon | +0.16254756846142526 |
| economy_in_recession_at_horizon_date | +0.05904243855815183 |
| industrial_production_growth_above_two_percent_at_horizon | +0.008693034342367012 |
| consumer_price_inflation_above_three_percent_at_horizon | -0.013140769461807311 |
| each of the five any-time indicators | 0.0 |

**0001 verdicts for B1** (`compare.json`). No verdict moved:
- 12 months: SHIP MODEL, no failing gates.
- 60 months: SHIP BASE RATE; fails skill, calibration and robustness, as reference-0008 does.
- 120 months: SHIP BASE RATE; fails skill and honesty. Reference-0008 also failed calibration here.

The only categorical changes are that 120-month failing-gate list and the configuration hash. 0001's mean skill (series-start) at 12 months went from 0.2672554495944556 to 0.31893843512970366, and its interval's lower bound from 0.1651830457833402 to 0.20177026347784113. All five gates passed.

**Rule 0007 secondaries** (`rule_0007_secondaries.json`). The script's reference-0008 row reproduces 0007's pinned -0.0582, 90% [-0.0961, -0.0261], which checks the script.

| run | horizon | minus R2 (model-sample) | 90% | reading |
|---|---:|---:|---|---|
| reference-0008 | 12 | -0.06914653422928149 | [-0.11479810765376595, -0.02921245236972729] | REGIMES DO NOT HELP |
| B1 | 12 | -0.015660421440059802 | [-0.05504131410482599, +0.027295102873689293] | NOT SHOWN |
| B1 | 60 | -0.01789895173699048 | [-0.17323793631096854, +0.08083771116825418] | NOT SHOWN |
| B1 | 120 | -0.2473249811271019 | [-0.32973403781837773, -0.07660252684686614] | REGIMES DO NOT HELP |

- At one year, B1 is no longer beaten by R2, but it does not beat it either.
- Pooled Brier skill against R1, beside the mean of ratios, for B1:

  | horizon | pooled | mean of ratios |
  |---|---:|---:|
  | 12 | 0.27606892952205275 | 0.23208205317887462 |
  | 60 | 0.13350051331234292 | 0.0705846912541883 |
  | 120 | 0.22002367527648214 | -0.21487924172028483 |

- The two disagree in sign at ten years, for B1 and for the reference alike, so 0007 marks any ten-year claim NOT ESTABLISHED.
- 0007's full verdict could not be computed: its calibration test is not implemented in the package.

## Verdict under the registered rule

The family has three arms, so the family-wise level is 1 - 0.10/3 = 96.67%.
- **PROMISING:** the one-year 90% lower bound, +0.025912735878650638, is above 0. Yes.
- **CONFIRMED_IN_SAMPLE:** the one-year 96.67% lower bound, +0.017355053792609352, is above 0. Yes.
- **HARMFUL:** the 90% upper bounds are +0.0857, +0.0068 and +0.0020, all above -0.02. No.
- **VOID:** (a) the audits exited 0 at both cutoffs; (b) the judged review is still outstanding.

Result: **CONFIRMED_IN_SAMPLE**, conditional on (b) and on CONTROL.

## Required checks and diagnostics

- **function_level_identity: PASS.** `test_at_one_regime_b1_is_the_reference_chain_bit_for_bit` covers 8 cases (gaps 0, 1, 2 and 13; condition holding and not). Each checks `numpy.array_equal` between B1 through `forecast_indicator` at one regime and `compose_through_the_condition_chain` on `SINGLE_REGIME_TRANSITION_MATRIX`, plus agreement with the closed form to 1e-13. The existing `tests/test_reference_forecasters.py` passes unchanged.
- **end_to_end_identity: PASS.** It was run before the scored run and committed in `d775bca` (`one_regime_identity.json`).
  - B1 was run at one regime through `forecast backtest`. The state count was forced to 1 by replacing `state_count_on_burn_in.state_count_for_the_backtest` inside the diagnostic's own process only.
  - The run covered 391 dates, 1994-03-01 to 2026-09-01; every row has state count 1 and regime distribution `1.000000`. Gate four passed.
  - All comparisons used `numpy.array_equal` with no tolerance:

    | comparison | rows | differing |
    |---|---:|---:|
    | Point-in-time rows: B1 vs `condition_chain_probability` from `run_walk_forward(..., condition_chain_cadence=ConditionChainCadence.REFIT)` on the same fits | 5,865 | 0 |
    | Any-time rows: B1 vs main's code at `99f232d`, run the same way at one regime with its own cache copy | 5,865 | 0 |
    | Determinism: the refit-cadence run's predictions vs B1's | 11,730 | 0 |
    | Contrast (recorded, not required): main's point-in-time rows vs the same chain | 5,865 | 5,865 (largest 0.3885865902959806) |

    The contrast shows the identity is not trivially true.
- **Secondary, cadence effect** (R2 at refit cadence minus R2 at every forecast date, one year, model-sample): -0.0034823863334529637.
  - 90% [-0.006186591231166705, -0.0008008015756790115]; 96.67% [-0.007067165833371678, -6.877940721873916e-05].
  - The registered expectation was about -0.004.
- **Secondary, pure regime effect** (B1 scored minus B1 at one regime, one year, model-sample):
  - point-in-time rows: +0.01182482267255966, 90% [-0.02424431716721096, +0.05276737988934605];
  - all rows: +0.006620526030106294, 90% [-0.022199195484698134, +0.041490563185489666].
- **Harness exit codes** (`exit_codes.json`, commit `d775bca`):

  | step | exit |
  |---|---:|
  | check-gates | 0 |
  | compare | 1 (numbers moved, expected) |
  | paired, model-sample | 0 |
  | paired, series-start | 0 |
  | audit at 2000-03-01 | 0 |
  | audit at 2022-03-01 | 0 |

  Tree clean at start and end: true.

## Prediction versus outcome

The registration predicted: "Gains concentrate on unemployment above five percent at the horizon and the funds rate above four percent at the horizon; a one-year effect of order +0.03. PROMISING with probability 0.45."
- **Where the gains are:** confirmed. Unemployment above 5% gained +0.3177 and the funds rate above 4% gained +0.1625. Recession at the horizon date also gained (+0.0590), which was not predicted. Consumer prices above 3% lost (-0.0131).
- **Size:** +0.0535, larger than the predicted +0.03.
- **Verdict:** PROMISING, and beyond it CONFIRMED_IN_SAMPLE.

## Surprising, and caveats

- **Regimes add little on top of the chain.** The pure regime effect on point-in-time rows is +0.0118, and its interval spans zero. Most of the gain is the condition's own persistence. Against R2 directly, B1 is -0.0157 (NOT SHOWN).
- **Debt D5 undercounts revised starting values.** D5's measurement covered only unemployment and recession dating, reasoning that consumer prices and industrial production are model inputs with archival vintages. But the *conditions* for those two indicators are read from the final file.
  - Industrial production's starting condition differs from its vintage on 58 of 389 dates.
  - On main this already reaches the per-regime rates and R2; B1 extends it to point-in-time forecasts.
  - The effect on the primary endpoint is -0.0004.
  - This is main's debt and was not changed here; D5's table should probably gain those two series.
- **Where the chain starts in time for recession dating.** As registered, the chain starts from the filtered regime distribution, which is dated at the observation matrix's last month (the forecast month minus 2), and steps the condition's publication gap. For four indicators those two dates coincide. For recession dating the starting condition is 14 or more months old, so the regime distribution is stepped about 12 months further than the model's own projection. This is not a look-ahead. It is a property of the specification, left as registered.

## Deviations

None from the specification. The any-time half of the end-to-end identity was compared against main's code at `99f232d` rather than against this branch with the setting off. Both are "main's own any-time composition"; main's code is the stricter comparison.

## Could not do

- `REPORT.md`: the Write tool refused the file ("Subagents should return findings as text"). Per the brief I stopped rather than write it another way.
- Rule 0007's full per-horizon verdict: its calibration test is not implemented in the package.
- The class-B correction for unemployment and recession dating: vintages exist at only 35 and 14 usable dates, with 0 differences on those.
