# B3 — equal-blend-with-the-chain (experiment 0008)

> The arm agent's own write of this file was refused by the session harness ("Subagents should return
> findings as text"); it returned this text and did not route around the refusal. The coordinator
> committed it verbatim after checking the paired differences and exit codes against `paired.json` and
> `exit_codes.json`. One note from the coordinator: "0007's calibration test is not implemented in the
> package" was true of this branch, cut at 99f232d; main gained it later the same day (39dd1c8).

Branch `research/equal-blend-with-the-chain`. Code and tests committed at `9b25221` before the scored run. There was one scored run, with the registered values. `exit_codes.json` records `"tree_clean_at_start_and_end": true` at that commit.

## What changed

The issued probability is `0.5 * p_model + 0.5 * p_R2` at every indicator and horizon. `p_R2` is rule 0007's reference chain:
- It is a two-state chain on the indicator's own monthly condition.
- Its rates are re-estimated at every forecast date, from condition-months published by that date and on or after the model sample's first month.
- It starts from the last published condition and steps through the publication gap, then the horizon.

The model is unchanged. The weight is a constant 0.5. A missing chain value raises.

Files:
- **`configuration/run_settings.py`:** `blend_the_model_equally_with_the_condition_chain`, True on this branch. It is omitted from the hash at False. Off, the configuration hashes to reference-0008's `fec79a040f9ca6f9`; the arm's hash is `7647c129be85291e`.
- **`models/indicator_forecast.py`:** `CONDITION_CHAIN_BLEND_WEIGHT = 0.5` and `blend_equally_with_the_condition_chain`. It raises `ForecastCompositionError` on a missing, infinite or out-of-range model or chain value, and clips nothing.
- **`backtest/walk_forward.py`:** `condition_chain_at_every_horizon` is the chain's composition at one regime. The backtest column and today's grid both use it.
  - The blend always uses the every-forecast-date chain.
  - The `condition_chain_cadence` argument moves only the `condition_chain_probability` column.
- **`command_line_interface.py`:** `forecast_now` blends today's grid with the same functions.
  - It keeps `model_probability` and `condition_chain_probability` beside the blended number.
  - Those two columns appear only when blending, so main's grid keeps its schema.

**Checked end to end on the scored run.** Over all 11,730 rows, the arm's `predicted_probability` equals `0.5 * reference predicted + 0.5 * reference condition_chain_probability` exactly (`np.array_equal`). Every other scored and model column is identical to reference-0008's. So the fits, recomputed under the new hash, reproduce the reference to the bit.

**Test edits (additive only):**
- `test_configuration_hash_compatibility.py`: the shipped-hash test names the new switch at False, and the omission-map set gains the key.
- `test_two_timescale_chains.py::test_with_the_switch_off_the_hash_is_main_reference_runs`: both sides hold B3's switch at False. The assertions are unchanged; the test failed without this.
- `test_look_ahead_audit.py`: one new test pins that the synthetic audits run with the blend on.

**New test file:** `tests/test_equal_blend_with_the_condition_chain.py`, 26 tests. They cover:
- the formula to the bit, the fixed weight, and the raises;
- the hash when the setting is off;
- the walk-forward identity, that only the issued number and hash move, and that the cadence argument does not affect the blend;
- the required look-ahead check;
- today's grid equalling the walk-forward row on the same date.

**Checks at `9b25221`:**
- pytest (not network): exit 0, 2 skips for uncached fits.
- ruff check, ruff format --check, mypy (44 files), `scripts/layer_check.py` (38 modules): all clean.

## Look-ahead audit

| path | touched? | why still clean |
|---|---|---|
| Training panel assembly | No | The chain reads only the model sample's first month from the point-in-time panel as of the forecast date, which R2 already did. Honest start is still 1994-03-01, with 0 fallback dates. |
| Standardisation window | No | Nothing is standardised by the blend or the chain. |
| State probabilities | No | The model half is filtered as before. The chain uses no state probabilities; it is one regime, matrix `[[1.0]]`. |
| Model parameters | No | Refits under the new hash reproduce the reference. All `regime_distribution` values are identical. |
| Number of regimes | No | The burn-in window before 1994-03-01 gives 16 regimes (4 x 4), as in the reference. |
| Conditional rates | **Yes** | The chain's rates now reach the forecast. They come from `condition_available_at(history, t)`: publication date on or before t. That is label plus lag, and for recession dating the later of that and the NBER announcement (ADR 0011). Only months in the model sample count, estimated by plain counts. It is the model's censoring, applied monthly. Test: flipping every condition unpublished at 2000-12-01 moves no forecast dated 2000-01 to 2000-12. Control: flipping the last month published by 2000-01-01 does move that date. |
| Benchmark (climatology) | No, never read | This is the difference from A6. Test: flipping every outcome and rebuilding both benchmarks moves the outcomes and benchmarks, but not the blend or the chain. |
| Outcome resolution | No | The forecast reads no outcome. |
| Condition values feeding rates | **Yes, class B (D5)** | The chain reads final revised values of already-published months, in its rates and its starting condition. That includes the starting condition for point-in-time indicators, which the model half never reads. D5 measured 34 of about 54,000 condition-months that would flip. The reference shares this path. **The corrected paired difference was not measured**; the reviewer must rule on it. |
| Run settings | Yes | One boolean. The 0.5 weight is a constant fixed by the registration. |
| Thresholds, canonicalisation, indicator thresholds | No | Indicator thresholds are still "weak" (D12), shared with the reference. |
| Future-perturbation invariance | Covered | Compares `predicted_probability` (the blend) and the chain exactly. **2000-03-01: PASS, exit 0**, 73 dates, 7 refits, 2,190 rows, 402 s. **2022-03-01: PASS, exit 0**, 337 dates, 29 refits, 10,110 rows, 1,822 s. Not covered: D5, a wrong registry lag, and today's grid. Today's grid is pinned by the test that it equals the walk-forward row on the same date. |

## Results

Reference-0008 (`fec79a040f9ca6f9`) against this run (`7647c129be85291e`): 9,702 resolved keys in both, none on only one side. Paired bootstrap: 10,000 resamples, seed 20260908.

**Primary** (`paired.json`, benchmark model-sample):

| horizon | reference | this run | difference | 90% interval | 96.67% interval |
|---|---|---|---|---|---|
| 12 | 0.17859594038965293 | 0.24005794923967647 | **0.061462008850023536** | [0.04033868657418529, 0.08752753408578186] | [0.03409672891696466, 0.09606632054023913] |
| 60 | 0.0689640064251977 | 0.09698286555806143 | 0.028018859132863727 | [-0.022607670379715544, 0.1118347536809971] | [-0.037973567196391965, 0.1321759963679158] |
| 120 | -0.21091324039179402 | -0.0548082067975033 | 0.15610503359429073 | [0.053583411512001536, 0.20797168677958933] | [0.0473425025545461, 0.522462644651379] |

**Secondary** (`paired_series_start.json`, benchmark series-start):

| horizon | reference | this run | difference | 90% interval | 96.67% interval |
|---|---|---|---|---|---|
| 12 | 0.2672554495944556 | 0.32005570735254063 | 0.052800257758085056 | [0.03596642037509745, 0.07306817582570661] | [0.0309097276836491, 0.07858394510006202] |
| 60 | 0.11941618408374788 | 0.1446533446296399 | 0.025237160545892035 | [-0.022355903638678266, 0.11407964024771376] | [-0.03641673466187502, 0.14354937789889663] |
| 120 | -0.16243443909991856 | -0.0062457745798671915 | 0.15618866452005137 | [0.05688031667935849, 0.20896900009592465] | [0.05215400850662351, 0.5226022692555871] |

**0001 verdicts** (`compare.json`):

| horizon | verdict (reference -> this run) | failing gates (reference -> this run) |
|---|---|---|
| 12 | SHIP MODEL -> SHIP MODEL | none -> none |
| 60 | SHIP BASE RATE -> SHIP BASE RATE | skill, calibration, robustness -> **calibration** (MOVED) |
| 120 | SHIP BASE RATE -> SHIP BASE RATE | skill, calibration, honesty -> unchanged |

At ten years, honesty fails at 0.0499 against 0.05. That column describes the model and is unchanged by design.

**Per-indicator one-year differences** (`paired.json`, model-sample):

| indicator | difference |
|---|---|
| economy_in_recession_within_horizon | 0.2215351891366717 |
| unemployment_rate_above_five_percent_at_horizon | 0.21308122460757983 |
| federal_funds_rate_above_four_percent_at_horizon | 0.10820558835902361 |
| industrial_production_growth_above_two_percent_at_horizon | 0.04930437453560799 |
| unemployment_rate_above_seven_percent_within_horizon | 0.04089948720429104 |
| treasury_yield_curve_inverted_within_horizon | 0.035106720203318176 |
| economy_in_recession_at_horizon_date | 0.020065041526040384 |
| federal_funds_rate_below_one_percent_within_horizon | -0.019725853516504577 |
| consumer_price_inflation_above_five_percent_within_horizon | -0.026856369680941627 |
| consumer_price_inflation_above_three_percent_at_horizon | -0.026995313874851323 |

## Verdict: CONFIRMED_IN_SAMPLE (provisional on the judged review)

- **PROMISING:** the 90% lower bound 0.0403 > 0. Met.
- **CONFIRMED_IN_SAMPLE:** the 96.67% lower bound 0.0341 > 0. Met.
- **HARMFUL:** no horizon's 90% interval lies entirely below −0.02. The upper bounds are 0.0875, 0.1118 and 0.2080. Not harmful. The five-year lower bound is −0.0226, but the interval is not entirely below −0.02.
- **VOID check (a):** audits exit 0 at 2000-03-01 and 2022-03-01.
- **VOID check (b):** the independent judged review has not been done. The reviewer must rule on the D5 path.
- **Reference's own audits:** I read `control-0008`'s `exit_codes.json` (main at `99f232d`) without touching that worktree. It records both audits at exit 0.
- **Ceiling:** CONFIRMED_IN_SAMPLE is the ceiling, per `stated_in_advance`. Adoption needs a separate recorded decision.

## Required checks and diagnostics

- **look_ahead:** passed. Three tests (unpublished conditions do not reach the forecast, a published one does, no outcome does) and both audits.
- **Pre-registered diagnostics:** B3 names none.
- **Secondaries** (post-hoc, not endpoints): `secondary_measurements.py`, with outputs in `secondary_measurements_*.json`. It reproduces 0007's pinned reference numbers exactly.
- **Arm minus R2, model-sample:**
  - 12 months: −0.007684525379257956, 90% [−0.02842467655793349, 0.011557368561774223]. **NOT SHOWN**, so 0007's "not beaten by the chain" gate passes. The reference fails it: −0.06914653422928149, 90% [−0.11479810765376595, −0.02921245236972729].
  - 60 months: +0.008499222566882653, 90% [−0.06112968482442772, 0.05635680829039972]. NOT SHOWN.
  - 120 months: −0.08725394620432038, 90% [−0.11863681993429409, −0.01805352910281352]. **REGIMES DO NOT HELP.**
- **Pooled skill against R1 beside the mean of ratios:**
  - 12 months: pooled 0.2741032243653815, mean 0.24005794923967647. Same sign.
  - 60 months: pooled 0.14710560515244142, mean 0.09698286555806143. Same sign.
  - 120 months: pooled 0.23757293847251748, mean −0.0548082067975033. **Signs disagree, so NOT ESTABLISHED at ten years.** The reference has the same split.
- **0007 gates for the arm, with R1 as the benchmark:**
  - One year: skill 0.2401, 90% [0.1715, 0.3113]; robustness, honesty and "not beaten by the chain" all pass. The **calibration test is not implemented, so the verdict is undetermined.**
  - Five years: skill and robustness fail, so SHIP BASE RATE.
  - Ten years: skill, honesty and "not beaten by the chain" fail, so SHIP BASE RATE.

## Prediction versus outcome

- **Registered prediction:** "PROMISING at one year with probability 0.55; ten-year difference positive." **Both held.** One year reached CONFIRMED_IN_SAMPLE, and ten years is +0.1561 with its 90% interval above zero.
- **The mechanism held only halfway.**
  - The hypothesis was that an equal blend usually beats the better of its two forecasters.
  - At one year, against R1, the chain is the better one: 0.2477 against the model's 0.1786.
  - The blend scores 0.2401. It beats the model and the average of the two (0.2132), but not the chain (−0.0077, interval spans zero).
  - At ten years the chain beats the blend, with the interval entirely below zero.
  - So the gain is mostly the chain's own advantage. In sample this does not favour the blend over R2 alone. R2 cannot ship directly, and this arm is one route that lets it.
- **Per indicator:** the gains are in recession timing, unemployment and the funds-rate level. The losses are in inflation and the funds rate near the zero bound. This matches the 2026-09-25 review.
- **Five-year 0001 gates:** only calibration fails now, but the verdict is still SHIP BASE RATE.
- **Not done:**
  - the judged review;
  - the D5 correction;
  - 0007's calibration test;
  - `submit` unchanged, which would mislabel the blend as `model_probability` on this branch.
- **Runtime:** 1 h 02 min, under load from the parallel arms.

Files are in this directory:
- `exit_codes.json`
- `paired.json`
- `paired_series_start.json`
- `compare.json`
- `look_ahead_audit.txt`
- `look_ahead_audit_2022.txt`
- `secondary_measurements.py`
- `secondary_measurements_arm.json`
- `secondary_measurements_reference-0008.json`
