# Experiment 0008, arm B2 (observe what is forecast)

> The arm agent's own write of this file was refused by the session harness ("Subagents should return
> findings as text"); it returned this text instead and did not route around the refusal. The
> coordinator committed it verbatim after checking the paired differences and exit codes against
> `paired.json` and `exit_codes.json`.

**Verdict under the registered rule: HARMFUL** at ten years. Not PROMISING and not CONFIRMED_IN_SAMPLE at one year. This is conditional on the VOID rule's judged look-ahead review, which is outstanding. The deterministic half passed at both cutoffs.

- **Primary endpoint** (one-year paired difference against R1, model-sample): **-0.00879438891023196**, 90% [-0.04143304765975944, 0.02502846562739024], 96.67% [-0.051542507717228805, 0.033980775340465244].
- **Ten years:** -0.11762920420291081, 90% [-0.1622826213076869, -0.04955465123310211].

**Branch** `research/observe-what-is-forecast`:

| commit | contents |
|---|---|
| `98b103f` | implementation and tests |
| `4bf1abd` | the pre-run required checks |
| `85e301d` | the scored run's outputs and the secondary diagnostics |

**Scored run.** Made at `4bf1abd` with `RESEARCH_ARM_REFERENCE=reference-0008 RESEARCH_ARM_BENCHMARK=model-sample RESEARCH_ARM_FAMILY_LEVEL=0.9667`. `exit_codes.json` records `tree_clean_at_start_and_end: true`.

| step | exit code |
|---|---|
| check-gates | 0 |
| plain compare | 1 |
| paired | 0 |
| paired, series-start | 0 |
| audit, 2000-03-01 | 0 |
| audit, 2022-03-01 | 0 |

## What changed

With `observe_the_unemployment_rate_and_the_term_spread` on, the model reads five columns instead of three.

- **Growth chain:** growth, plus UNRATE. UNRATE enters as a level, read from its archival vintage as of each date.
- **Inflation-and-rates chain:** inflation and rates, plus GS10 minus TB3MS. Each leg is unrevised and censored at 32 days, and the difference is taken on the months both legs cover.
- **Pipeline:** every column goes through the existing bridge, transform, align and expanding standardisation (minimum 36 months). Each chain's state count is still chosen by the burn-in sweep, candidates 1..4.

| file | change |
|---|---|
| `configuration/run_settings.py` | The new field, True on this branch only, added to the hash-omission map at False. |
| `configuration/economic_series.yaml` | UNRATE declares `model_dimension_when_forecast_targets_are_observed: growth`; the derived term spread declares `rates`. |
| `configuration/registry.py` | `ObservationColumn`, `forecast_target_columns`, `observation_columns`, `series_observed_by_the_model` and `configured_for(settings)`. The last refuses the setting when there is only one chain. The loader rejects a model input that is also declared a target. |
| `data/panel.py` | A panel defaults to every series the model observes. |
| `features/observation_matrix.py` | Builds from the registry's columns; a difference comes from its two point-in-time legs. The matrix carries `column_dimensions` and `column_names`. |
| `models/two_timescale_hidden_markov_model.py` | `chain_columns` assigns columns to chains by dimension. The assignment is threaded through the model, the fit and the EM step, and serialised only when it is not main's. |
| `models/two_timescale_state_selection.py` | Blocks are sliced per chain. |
| `models/state_labelling.py` | Labels follow the column names. |
| `backtest/state_count_on_burn_in.py`, `backtest/walk_forward.py` | Call `configured_for(settings)`, so settings are the one source of truth. The vintage pre-flight and the fallback scan read every observed series. |
| `command_line_interface.py` | `Workspace.open` configures the registry. fetch-data and the missing-vintage check cover UNRATE. fit-regimes passes the blocks and names. |
| `tests/test_observe_what_is_forecast.py` (new) | 31 tests, two on the live cache. |

**Suite:** 597 passed, 2 skipped. ruff, ruff format, mypy and `layer_check.py` are clean.

**Burn-in** (as of 1994-03-01, 455 months, 1956-03-01..1994-01-01): **3 growth × 3 levels = 9 joint regimes**, against the reference's 4 × 4 = 16. In both chains the held-out likelihood chose 3 and the information criterion preferred 4. Every refit is `states3x3`.

Two side effects follow from the registration itself:

1. **The sample starts later.** GS10 begins in 1953-04, so all columns align from there and the first standardised row is 1956-03, against 1950-12 in the reference. That is 63 fewer months, and the original three columns are also standardised from 1953-04.
2. **The benchmarks move with it.** R1 and R2 start at each date's own first matrix row (rule 0007). The arm's R1 therefore differs from the reference's on 11,629 of 11,730 rows, by a mean absolute 0.0237. The series-start benchmark is identical across the two runs.

## Look-ahead audit

| path | touched? | status |
|---|---|---|
| Training panel assembly | yes | **Clean.** Panels are still built `as_of` each date, with the boundary assertion on every series. UNRATE comes from the ALFRED vintage dated at that date, so no lag is involved; GS10 is censored at 32 days, like TB3MS. At 1994-03-01 both legs end at 1994-01, as UNRATE and CPI do. The pre-flight and honest-start scan now include UNRATE: 0 of 391 dates fall back, all read archival vintages, the shortest being 553 months (floor 240). |
| Standardisation window | yes | **Clean.** Same expanding function, with alignment moved to 1953-04. A test shows the matrix as of 1999-06 is exactly the head of the matrix as of 2003-06 on unrevised columns. |
| State probabilities | no | **Clean.** Filtered only, via the inherited forward pass over 9 states. |
| Model parameters at each refit | shape only | **Clean.** Refitted from scratch at all 33 refits. |
| Number of regimes | yes, input only | **Clean.** Chosen once, on a panel ending 1994-01-01. Both audit runs recompute it from scratch and get 9. |
| Conditional rates | no | **Clean except D14** (unchanged). |
| Benchmark | indirectly | **Clean.** Series-start is unchanged. R1 and R2 start at the arm's own first matrix row, computed from the panel at each date; this is a comparability caveat, not a leak. |
| Outcome resolution | no | Clean by design. |
| Condition values feeding rate estimation | no | **D5 approximation**, unchanged. The new inputs are not conditions and are exactly point-in-time. |
| Run settings | yes | **Clean.** One a-priori boolean. |
| Acceptance thresholds | no | Untouched. |
| Canonicalisation | yes | **Clean.** Fixed sort: growth then unemployment; inflation, then rates, then spread. Growth and inflation stay in columns 0 and 1, so the product order still holds. |
| Indicator thresholds | no | D12, unchanged. |
| Future-perturbation invariance | run | **2000-03-01: PASS, exit 0.** 2,190 of 2,190 rows identical; 7 fits plus the burn-in choice from scratch in each run; 951,951 values perturbed across 2,223 entries, including 1,038 vintages after the cutoff (UNRATE's among them), current-vintage UNRATE at 36 days and GS10 at 32 days; 329 s. **2022-03-01: PASS, exit 0.** 337 dates and 29 refits; 10,110 of 10,110 rows identical; 198,500 values perturbed (187 vintages after the cutoff, 12 current files); 1,241 s. |

Neither audit sees a wrong registry lag. The UNRATE input does not depend on one, because it comes from vintages. GS10 shares TB3MS's 32-day lag.

## Results

All quoted from `paired.json`, `paired_series_start.json` and `compare.json`. 9,702 resolved forecasts are in both runs, and none in only one.

**Primary: against R1 (model-sample).**

| horizon | reference skill | arm skill | difference | 90% interval | 96.67% interval |
|---|---|---|---|---|---|
| 12 months | 0.17859594038965293 | 0.16980155147942097 | **-0.00879438891023196** | [-0.04143304765975944, 0.02502846562739024] | [-0.051542507717228805, 0.033980775340465244] |
| 60 months | 0.0689640064251977 | 0.05734991867199757 | -0.011614087753200136 | [-0.030089150756507203, 0.02012907386864734] | [-0.03751702667829205, 0.02756681425969329] |
| 120 months | -0.21091324039179402 | -0.32854244459470483 | **-0.11762920420291081** | [-0.1622826213076869, -0.04955465123310211] | [-0.2292395677622217, -0.039667575500636286] |

**Secondary: against the series-start climatology** (printed values).

| horizon | difference | 90% interval | 96.67% interval |
|---|---|---|---|
| 12 months | -0.0284 | [-0.0625, +0.0061] | [-0.0728, +0.0155] |
| 60 months | -0.0314 | [-0.0503, +0.0041] | [-0.0582, +0.0126] |
| 120 months | -0.1138 | [-0.1840, -0.0568] | [-0.2833, -0.0487] |

**0001 verdicts.**

| horizon | reference-0008 | this arm |
|---|---|---|
| 1 year | SHIP MODEL, ECE 0.0893 | **SHIP BASE RATE**, failed calibration only: ECE 0.1181; skill +0.2389 [+0.1155, +0.3546] |
| 5 years | SHIP BASE RATE: skill, calibration, robustness | SHIP BASE RATE: skill, calibration, robustness |
| 10 years | SHIP BASE RATE: skill, calibration, honesty | SHIP BASE RATE: skill, calibration. Honesty now passes, total variation 0.1152 against 0.0499. |

**Per-indicator one-year differences** (`paired.json` `indicators[].difference`):

| indicator | 1-year difference |
|---|---|
| unemployment_rate_above_five_percent_at_horizon | +0.23952972387784588 |
| unemployment_rate_above_seven_percent_within_horizon | +0.06315052937921273 |
| treasury_yield_curve_inverted_within_horizon | +0.06300303516319039 |
| consumer_price_inflation_above_three_percent_at_horizon | +0.029778921985397222 |
| economy_in_recession_at_horizon_date | +0.0027683032717424894 |
| industrial_production_growth_above_two_percent_at_horizon | -0.02729035749619224 |
| federal_funds_rate_below_one_percent_within_horizon | -0.03349791453089934 |
| economy_in_recession_within_horizon | -0.06607355442372564 |
| consumer_price_inflation_above_five_percent_within_horizon | -0.16265375942139004 |
| federal_funds_rate_above_four_percent_at_horizon | -0.1966588169075012 |

**At ten years** the largest per-indicator moves are:
- recession within the horizon: -0.6600
- yield curve inverted within the horizon: -0.4296
- funds rate below 1% within the horizon: -0.3608
- inflation above 5% within the horizon: +0.1988

Mean effective sample size rose from about 45 to about 75 months, because there are 9 joint regimes instead of 16.

## Verdict under the registered rule

The family has 3 arms, so the family-wise level is 1 - 0.10/3 = 0.9667.

| clause | question | result |
|---|---|---|
| PROMISING | one-year 90% lower bound above 0? | -0.04143304765975944, no |
| CONFIRMED_IN_SAMPLE | one-year 96.67% lower bound above 0? | -0.051542507717228805, no |
| HARMFUL, 12 months | 90% upper bound below -0.02? | 0.02502846562739024, no |
| HARMFUL, 60 months | 90% upper bound below -0.02? | 0.02012907386864734, no |
| HARMFUL, 120 months | 90% upper bound below -0.02? | -0.04955465123310211, **yes** |

**HARMFUL**, which disqualifies the arm from adoption. VOID would override it only if:
- (a) an audit failed — both exited 0; or
- (b) the independent judged review, which is outstanding, finds a class-A path, or a class-B path that fails 0007's materiality floor.

## Required checks and diagnostics

**`off_reproduces_main`: passes.** Run through `run_with_the_setting_off.py`, which replaces only `Workspace.open`'s default settings (outputs in `off_*`):
- The hash is `fec79a040f9ca6f9` and check-gates exits 0.
- `baseline compare --require-own-artifacts --against reference-0008` reports "387 IDENTICAL 0 NUMERICAL 0 MOVED 0 REMOVED 0 ADDED … nothing moved", exit 0.
- Paired model-sample is +0.0000 on [+0.0000, +0.0000] at every horizon and for every indicator.
- Tests pin the hash, the three-column matrix byte for byte, and the unchanged two-chain payload.

**`honest_start`: passes** (`honest_start_check.txt`).
- `find_first_fully_point_in_time_date` returns 1994-03-01.
- The schedule is 391 dates, 1994-03..2026-09, with 33 refits.
- 0 dates fall back, and `assert_every_forecast_date_is_fully_point_in_time` passes.
- All 391 dates read an UNRATE archival vintage.
- `forecast fetch-data` fetched the 558 UNRATE vintages it needed into this worktree's cache only, with 0 failures and exit 0.
- In the widest schedule (from 1977-03), 204 dates fall back, all of them CPI before 1994-03; UNRATE falls back on none.
- Tests pin that a short synthetic unemployment vintage makes the scan and the pre-flight refuse when the setting is on, and that the live schedule starts at 1994-03.

**Secondary diagnostics** (not endpoints; `secondary_diagnostics.py` / `.json` / `.txt`, same seed, resamples and levels as the harness; a re-run reproduced the JSON byte for byte):

1. **Arm forecasts re-scored against the reference's R1, minus the reference.** The ten-year harm is not an artifact of the arm's later R1.

   | horizon | difference | 90% interval |
   |---|---|---|
   | 12 months | -0.031573368245675026 | [-0.06497545812090248, 0.003571008855816042] |
   | 60 months | -0.030230455537231152 | [-0.049916376221461875, 0.005052405927970941] |
   | 120 months | -0.1139667083141743 | [-0.17579424726982107, -0.05653920490771327] |

2. **0007 `regimes_help`, arm minus its own R2, one year (on R1):** -0.08237702404983091, 90% [-0.13478315843547767, -0.03159710631459399]: **REGIMES DO NOT HELP**. The reference minus its own R2 on the same basis is -0.06914653422928149, 90% [-0.11479810765376595, -0.02921245236972729].

3. **Pooled Brier skill against R1.**

   | horizon | reference | arm |
   |---|---|---|
   | 12 months | +0.2111 | +0.2068 |
   | 60 months | +0.1311 | +0.1091 |
   | 120 months | +0.2212 | +0.1242 |

   At ten years, pooled and mean-of-ratios disagree in sign for both runs, so neither run's ten-year skill claim is ESTABLISHED. The arm-minus-reference difference is negative on both measures.

## Prediction versus outcome

The registration predicted recession and unemployment would improve, inflation would be unchanged, and gave no verdict 0.6, HARMFUL 0.15.

- **Unemployment improved, as predicted.** +0.2395 for above 5% at the horizon, the largest gain; +0.0632 for above 7% within.
- **Recession did not.** Recession at the horizon is flat (+0.0028); recession within the horizon fell by 0.0661 at one year and 0.6600 at ten.
- **Inflation and rates got worse.** Inflation above 5% within: -0.1627. Funds above 4% at horizon: -0.1967. The levels chain now also carries the spread with one fewer state; that it crowds out the rate levels is an interpretation, not a measurement.
- **The mean is negative at every horizon**, and the 15%-probability outcome, HARMFUL, occurred.

**Surprising:**
- The one-year 0001 verdict flips to SHIP BASE RATE on calibration alone (ECE 0.0893 → 0.1181).
- The ten-year honesty gate now passes.

**Confounds the registered design does not separate:** five columns instead of three; 9 states instead of 16; a sample 63 months shorter.

**Not done:**
- The independent review, reserved for someone else.
- Notebooks 02/04 and `reporting/tables.regime_display_table` still assume three columns. They are off the scored path.

## Deviations, with reasons

1. **Three existing test files name the new switch off where they pin main's configuration.** No assertion was removed or loosened; A4 did the same. This needs the owner's review, because the brief says tests are additive only.
   - `test_configuration_hash_compatibility.py`: the shipped settings name it at False, and the omission-map set gains the key, as that test's own docstring prescribes.
   - `test_two_timescale_chains.py`: the main-hash test names it at False.
   - `test_honest_start_date_against_the_live_cache.py`: the main-configuration tests use settings with it off. The `backtest_schedule` test is unchanged and now pins the arm's 1994-03.
2. **Decided before the run, not spelled out in the registration:**
   - target columns follow the three dimension columns;
   - the derived spread enters as a level;
   - canonical-order ties are broken by the new columns last;
   - with the setting on and one chain, the registry refuses rather than ignoring it.
3. **Outside the harness:** the off-check wrapper and the secondary diagnostics, both committed.
4. **REPORT.md** could not be written by me; the harness refused it, and this text is the report.
