# Research arm A5: direct horizon rates

> Written to disk by the orchestrator, verbatim from the text the arm agent returned. The harness
> refused the agent's own write of a report file ("Subagents should return findings as text"), and
> the agent stopped rather than write it another way. Every number below should be checked against
> `paired.json` and `compare.json` in this directory, as the look-ahead reviewer's brief requires.

Experiment 0002, arm `A5-direct-horizon-rates`. Branch `research/direct-horizon-rates`.
Implementation commit `0136e6f`; run outputs are in `3919f08`. One run, with the registered
hyperparameters (shrinkage strength 10). Nothing was tuned, swept or re-run.

**Verdict under the pre-registered rule: HARMFUL.** At one year the paired 90% interval is
[-0.1447628450626253, -0.0586262624083289], entirely below -0.02. The verdict is provisional
until two checks outside this arm come back: the judged half of the VOID rule, and control arm
A0. The deterministic half, `forecast audit-look-ahead`, exited 0.

## What changed

One setting, `RunSettings.estimate_each_horizon_rate_directly`, defaults to `True` on this
branch.

- **The forecast.** For every indicator and horizon h (12, 60 and 120 months), the probability
  is today's filtered regime distribution dotted with
  `rate[k] = (sum_s gamma_s[k] * y_s,h + 10 * pooled) / (sum_s gamma_s[k] + 10)`, where `pooled`
  is the plain mean of the outcomes used.
  - This replaces both compositions for every indicator and horizon.
  - The transition matrix now enters only the `distance_to_stationary` diagnostic.
- **Which outcomes.** Only forecast months s whose outcome had resolved and been published by
  the refit date: label (s + h months) plus the resolution series' publication lag, on or before
  it.
- **Which gamma.** The filtered distribution from the model fitted at the refit date, never
  smoothed. It is the same array main's monthly rates are weighted by.
- **Shrinkage.** Main's Beta prior at strength 10 toward the pooled resolved rate, unchanged.
- **Off switch.** `False` reproduces main.
  - The field is in the hash omission map at `False`, so the off configuration hashes to main's
    `ad7fcc1affd0746a`. A test pins this.
  - The arm's default hashes to `224dc4027b23b1c7`.

Files:

- `models/indicator_forecast.py`: adds `DirectHorizonRate`, `estimate_direct_horizon_rate`
  (reusing `_shrink`) and `compose_direct_horizon`. `forecast_indicator` takes an optional
  `direct_horizon_rate`. `models/` still imports nothing from `data/`.
- `backtest/walk_forward.py`:
  - **One boundary, not two.** ADR 0009's rule moves out of `_expanding_climatology` into
    `count_of_outcomes_published_by`, which both the benchmark and the new
    `outcomes_available_at` call.
  - `fit_regime_model` estimates the direct rates. If a horizon has no published outcome yet it
    raises `BacktestError`; there is no silent fallback.
  - `run_walk_forward` passes the rates through.
- `command_line_interface.py`: `forecast_now` uses the same path as the backtest.
- `configuration/run_settings.py`: the field and its omission-map entry.
- `docs/TECHNICAL_DEBT.md`: an audit-table row for the new path, and a note on D4.
- `tests/test_direct_horizon_rates.py` (new):
  - Arithmetic counted by hand.
  - The boundary on the day before (excluded) and on the day (included), for 12 and 120 months
    at lags of 31, 45 and 400 days.
  - At every date, the admitted set equals what the benchmark averages.
  - Wiring on and off; the off switch reproduces main's digest.
- `tests/test_direct_horizon_rates_look_ahead.py` (new): the audit exits 1 on two injected
  off-by-ones (publication lag forgotten; horizon one month short) and 0 without them.
- `tests/test_configuration_hash_compatibility.py`: two lines added (see Deviations).

Checks:

- **Before the run:**
  - Full offline suite: 506 passed, 2 skipped, 1 deselected (network). Both skips are the
    live-cache test looking for fitted models under the arm's hash, which didn't exist yet.
  - `ruff check`, `ruff format --check` and `mypy`: clean.
  - The refactored benchmark is byte-identical to 2e025b7's on the real cache, 30 of 30
    indicator-horizon series.
- **From the run:**
  - All 34 fitted models the arm wrote are byte-identical to main's.
  - `mean_distance_to_stationary`, `climatology_brier_score`, `base_rate` and
    `resolved_forecasts` are IDENTICAL in all 30 rows.

## Look-ahead audit

| path | touched? | status |
|---|---|---|
| Training panel assembly | no | Panel assembled `as_of` the refit date; 0 of 391 dates use the fallback |
| Standardisation window | no | Expanding, unchanged |
| State probabilities in forecasts | yes | Clean. Today's distribution is filtered on the forecast date's panel; gamma_s is filtered from the refit model over the refit date's panel. No smoothed call on this path |
| Model parameters at each refit | no | 34 of 34 fits byte-identical to main's; a test pins `regime_distribution` identical with the setting on or off |
| Number of regimes | no | 6, chosen on the burn-in window 1950-12-01 to 1994-01-01, as on main |
| Monthly conditional rates | no | Estimated as on main, unused when the direct path is on |
| Benchmark (climatology) | refactored only | Byte-identical to 2e025b7's, 30 of 30 series; its boundary is now the shared function |
| **Outcome resolution, now an input** | **yes** | Clean by construction; the audit passes. An outcome enters at refit t only when (s + h months) + lag ≤ t, decided by the same function and comparison as the benchmark |
| Condition and outcome values (D5) | extends | The same approximation as main: final revised values with timing enforced. Exact for recession dating and market rates; approximate for industrial production and unemployment |
| Run settings | one new | Registered in 0002; shrinkage strength is main's 10 |
| Acceptance thresholds | no | Nothing under `proving/` edited |
| Canonicalisation | no | Rates, gamma and today's distribution come from one canonicalised model |
| Indicator thresholds | no | Weak (D12), unchanged |
| **Future-perturbation invariance** | run | **PASS, exit 0 in 407 s.** "PASS: no forecast issued on or before 2000-03-01 changed when every observation unavailable at 2000-03-01 was perturbed". 2190 rows; 7 refits from scratch in both runs; 627617 values perturbed across 1348 entries, the same count amendment 1 records for main |

The boundary on real data. Each row gives the last forecast month admitted as "last s (deciding
label, published)", then when the next month's outcome would be published:

| series lag | as of | 12 months | 60 months | 120 months | next published |
|---|---|---|---|---|---|
| recession dating, 400 days | 1994-03-01 | 1992-01-01 (1993-01-01, 1994-02-05) | 1988-01-01 | 1983-01-01 | 1994-03-08 |
| recession dating, 400 days | 2000-03-01 | 1998-01-01 (1999-01-01, 2000-02-05) | 1994-01-01 | 1989-01-01 | 2000-03-07 |
| unemployment, 36 days | 2000-03-01 | 1999-01-01 (2000-01-01, 2000-02-06) | 1995-01-01 | 1990-01-01 | 2000-03-08 |
| consumer prices, 44 days | 2000-03-01 | 1999-01-01 (2000-01-01, 2000-02-14) | 1995-01-01 | 1990-01-01 | 2000-03-16 |
| funds rate and yield curve, 32 days | 2000-03-01 | 1999-01-01 (2000-01-01, 2000-02-02) | 1995-01-01 | 1990-01-01 | 2000-03-04 |
| industrial production, 47 days | 2000-03-01 | 1999-01-01 (2000-01-01, 2000-02-17) | 1995-01-01 | 1990-01-01 | 2000-03-19 |

In every row the next month's outcome is published after the as-of date, so it is excluded. The
observation matrix starts at 1950-12-01; outcomes before that have no gamma and do not enter a
rate.

## Results

Quoted from `paired.json`, `compare.json` and `check_gates.log`. Resolved forecasts: 9702 in both
runs, 0 on either side only.

| horizon | main | arm | difference | 90% interval | 98.33% interval | independent obs | resamples used |
|---|---|---|---|---|---|---|---|
| **12 months** | 0.21537738742364834 | 0.11372080830423811 | **-0.10165657911941023** | **[-0.1447628450626253, -0.0586262624083289]** | [-0.16581894090159943, -0.04208190982346677] | 31.5 | 9953 |
| 60 months | 0.07276206990291953 | -0.08555559755527015 | -0.15831766745818968 | [-0.22852093208626825, 0.0019225418624841926] | [-0.2653699065506756, 0.11138148191162835] | 5.5 | 7495 |
| 120 months | -0.352769097290159 | -0.08811868655033364 | +0.2646504107398253 | [0.04586924396545917, 0.252550656286844] | [0.0043378395034199034, 2.2252808054099726] | 2.25 | 5443 |

Per indicator, from `paired.txt` (point estimates only):

| indicator | 12 | 60 | 120 |
|---|---|---|---|
| consumer_price_inflation_above_five_percent_within_horizon | -0.2411 | -0.2397 | +0.0654 |
| consumer_price_inflation_above_three_percent_at_horizon | -0.0513 | -0.0148 | +0.2542 |
| economy_in_recession_at_horizon_date | +0.1044 | -0.0414 | +0.0803 |
| economy_in_recession_within_horizon | +0.1180 | +0.1513 | +2.6646 |
| federal_funds_rate_above_four_percent_at_horizon | -0.1054 | -0.2372 | -0.2566 |
| federal_funds_rate_below_one_percent_within_horizon | -0.2565 | -0.3021 | -0.4918 |
| industrial_production_growth_above_two_percent_at_horizon | -0.0060 | -0.1397 | -0.1051 |
| treasury_yield_curve_inverted_within_horizon | -0.2111 | -0.2893 | +0.0351 |
| unemployment_rate_above_five_percent_at_horizon | +0.0051 | -0.1279 | -0.2753 |
| unemployment_rate_above_seven_percent_within_horizon | -0.3725 | -0.3424 | -0.0807 |

Seven of ten indicators lose skill at one year and nine of ten at five years. At ten years five of
ten gain, and one question, recession within the horizon, carries the mean.

**Experiment 0001 gates, thresholds unchanged.** check-gates exit 0. The ship-or-not verdict is
SHIP BASE RATE at every horizon, for main and the arm alike.

| horizon | main's failing gates | arm's failing gates |
|---|---|---|
| 1 year | calibration | calibration, **robustness** (newly failed: 2 of 4 sub-periods positive) |
| 5 years | skill, calibration, robustness | unchanged |
| 10 years | skill, calibration, robustness, honesty | unchanged |

**Calibration error.** The arm's figures are from the gate log. Main's are recomputed with the
verdict's own `_skill_matrix` and `assess_calibration` from `baselines/main.forecasts.parquet`.
The same code reproduces the arm's logged values exactly.

| horizon | main | arm |
|---|---|---|
| 12 months | 0.12495346662661265 | 0.1400665232927758 |
| 60 months | 0.19421638468146912 | 0.2717628612446452 |
| 120 months | 0.11558085146718161 | 0.21958854053534205 |

It is worse at every horizon.

**Log loss.** There is no horizon-level figure; per indicator it is higher in 8 of 10 at one year,
9 of 10 at five years and 5 of 10 at ten years.

| indicator at 120 months | metric | main | arm |
|---|---|---|---|
| economy_in_recession_within_horizon (best) | Brier skill | -2.648516962 | 0.01604258315 |
| | log loss | 0.4604341833 | 0.1633860476 |
| | calibration error | 0.302086575 | 0.03202696304 |
| federal_funds_rate_below_one_percent_within_horizon (worst) | log loss | 0.6265955112 | 1.602250402 |

**Lambda2.** Unchanged, because the models are main's byte for byte: "The second eigenvalue
modulus is 0.9831, a half life of 41 months."

## Verdict

- **PROMISING:** not met. The one-year 90% lower bound is -0.1447628450626253, below zero.
- **CONFIRMED_IN_SAMPLE:** not met. The one-year 98.33% lower bound is -0.16581894090159943,
  below zero. The paired output does carry the 98.33% level.
- **HARMFUL:** met at one year. The 90% upper bound, -0.0586262624083289, is below -0.02.
  - Five years: upper bound 0.0019225418624841926, not met.
  - Ten years: the interval lies above zero, not met.
- **VOID:** (a) the audit exited 0. (b) The independent review is pending, and A0 must pass.

**HARMFUL, provisional.** A harmful arm is disqualified from combination.

## Prediction versus outcome

The pre-registration said: "The ten-year any-time underestimate shrinks sharply, and so does the
recession-within-ten-years miss. The one-year change is small."

- **The recession miss: repaired, as predicted.** Brier skill -2.648516962 → 0.01604258315, and
  calibration error 0.302086575 → 0.03202696304.
- **The ten-year any-time underestimate in general: only partly.** Three of the five any-time
  questions gain and two lose. Ten-year calibration error roughly doubles.
- **The one-year change is small: wrong.** It is -0.10165657911941023, and the five-year change
  is -0.15831766745818968.

Two candidate explanations, neither tested here:

1. The direct rate conditions only on the regime today. Main's composition also uses whether the
   condition holds now, and the largest one-year losses are the sticky within-horizon questions,
   where that matters most: unemployment above seven -0.3725, funds rate below one -0.2565,
   inflation above five -0.2411, inverted curve -0.2111.
2. A ten-year direct rate learns only from windows that closed more than a decade earlier, so it
   trails any change in how often an outcome occurs by that much. The funds-rate-below-one
   question fits this pattern.

Following either up would be a new, separately registered experiment.

## Surprising

- The ten-year point estimate, +0.2646504107398253, lies above its own 90% interval's upper bound
  of 0.252550656286844. The 98.33% upper bound is 2.2252808054099726, and only 5443 of 10000
  resamples were usable.
- The arm newly fails 0001's robustness gate at one year.
- `mean_effective_sample_size` moved in all 30 rows, to about 40-45 at 120 months. It is a
  reporting column only (see Deviations).

## Deviations

1. **`tests/test_configuration_hash_compatibility.py` gains two lines, removing no assertion.**
   The shipped-configuration test names the new field at `False`, and the pinned omission-map
   membership gains its third entry. No setting that is on by default can pass that file
   unchanged. Its docstring prescribes "a reviewed, additive change" for a legitimate new entry,
   and a new test pins that `False` reproduces `ad7fcc1affd0746a`. Needs review before any merge.
2. **Effective sample size for the direct path** is today's distribution dotted with each
   regime's gamma-weighted count of forecast months. Those months overlap, so it overstates
   independent evidence. Only gate 3's positivity check reads it.
3. **`forecast_now` also uses the direct path**, so the forecast that ships comes out of the path
   that was backtested. The current forecasts are not part of any endpoint.

## Could not do

- The judged look-ahead review. It must come from an agent that didn't write this arm.
- The perfectly calibrated reference distribution for calibration error. The tooling doesn't
  produce it, and I didn't improvise one.
- Per-indicator paired intervals, which `--paired` deliberately doesn't produce.
- Checking A0's result.
- Writing and committing `REPORT.md` itself: the harness blocked the write, as described above.
