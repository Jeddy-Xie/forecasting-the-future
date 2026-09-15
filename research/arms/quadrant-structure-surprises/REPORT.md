# Arm A3 · quadrant-structure-surprises

Experiment 0002, arm `A3-quadrant-structure-surprises`. Branch
`research/quadrant-structure-surprises`, implementation commit `ea76a67`, run on
`ea76a67`. One run, with the registered hyperparameters. Nothing was
tuned, swept or re-run.

## What changed

The arm's registered `change` has three parts. All three are implemented, with no
additions.

1. **Growth and inflation become surprises.** For each month s,
   `surprise = x[s] - (a_s + b_s * x[s-1])`, where `a_s` and `b_s` are the
   intercept and slope of an ordinary least squares regression of `x[j]` on
   `x[j-1]` over j = 1 .. s-1. Only months up to s-1 enter the fit. It is
   refitted for every month (recursive and expanding), and the first surprise is
   issued with 60 months behind it. The rates column is unchanged.
   - `src/economic_regime_forecasting/features/transforms.py`:
     `recursive_autoregressive_surprise`, `MINIMUM_MONTHS_BEFORE_FIRST_SURPRISE = 60`.
     It computes one regression per month from running sums (`numpy.cumsum`,
     which accumulates in order), so the sums behind month s are bit-identical
     however many months follow.
   - `src/economic_regime_forecasting/features/observation_matrix.py`:
     `replace_growth_and_inflation_with_surprises`, and `observations_as_configured`,
     the single place that decides whether the step is taken. Every caller that
     fits or filters a model passes its matrix through it: each refit, each
     forecast date's filter, the burn-in choice, the panel-length start search and
     the command line interface.
2. **K = 4 for every fit.** The burn-in sweep still runs, is still reported and
   still feeds the regimes-exist gate, but it no longer chooses. Its
   recommendation is kept in the new field `state_count_recommended_by_the_sweep`
   on the burn-in choice.
   - `src/economic_regime_forecasting/models/surprise_quadrants.py`: `QUADRANT_COUNT = 4`,
     `state_count_fixed_by_the_quadrant_structure`.
   - `src/economic_regime_forecasting/backtest/state_count_on_burn_in.py`: the
     choice carries 4, and the sweep's recommendation and reason are kept.
   - `src/economic_regime_forecasting/backtest/walk_forward.py`: `fit_regime_model`
     refuses any other count under the arm rather than overriding it silently.
   - `src/economic_regime_forecasting/command_line_interface.py`: `forecast-now`
     fits with 4.
3. **Quadrant initialisation.** Every expectation-maximisation restart starts its
   emission means at the centroids of the four quadrants cut by
   sign(growth surprise) and sign(inflation surprise). The boundaries are zero, so
   none is estimated. Each centroid is the mean of its quadrant's months in all
   three columns, rates included. A surprise of exactly zero counts as at-or-below.
   An empty quadrant raises rather than falling back to a random start. Each
   restart keeps the fitter's existing perturbation: a random persistence level
   and transition jitter.
   - `src/economic_regime_forecasting/models/surprise_quadrants.py`:
     `surprise_quadrant_centroids`.
   - `src/economic_regime_forecasting/models/gaussian_hidden_markov_model.py`:
     `fit(..., initial_means=...)`, which replaces k-means++ seeding only when it
     is given.

**The switch.** `RunSettings.growth_and_inflation_surprise_quadrants`
(`src/economic_regime_forecasting/configuration/run_settings.py`).
`DEFAULT_RUN_SETTINGS` sets it to True, so every command on this branch runs the
arm. See the deviations section for why the field's own dataclass default is
False.

**Before or after standardisation: after.** The surprise is the last step, so
the column the model reads is the surprise itself, and its zero is the quadrant
boundary with nothing estimated. Both inputs are point in time: the standardised
value at s uses months up to s, and the regression behind its surprise uses
standardised values strictly before s. Taking surprises of natural-unit values
and then standardising them would also have been point in time, but it would move
the column's zero to an estimated running mean of surprises. The registration says
"none is estimated at all".

**Burn-in and start date**, measured on the live cache with the worktree's code:

| | main | arm A3 |
|---|---|---|
| observation matrix as of 1994-03-01 (the burn-in panel) | 518 months, 1950-12 .. 1994-01 | **458 months, 1955-12 .. 1994-01** |
| panel-length first forecast date (240 months needed) | 1971-12 | 1976-12 |
| first forecast date under the honest start | 1994-03 | **1994-03, unchanged** |
| forecast dates, refits | 391, 33 | 391, 33 |

The 60 months that drop are exactly the surprise burn-in. The honest start is
still set by the consumer price index vintages (the last fallback month is
1994-02), not by panel length, so it does not move. The sweep's 20% holdout on
458 months is 92 months.

## Tests

`tests/test_surprise_quadrants.py`, 19 tests, all passing. The arm has no
`required_check` field. Its leakage note ("the audit must confirm that each
surprise uses parameters estimated strictly before the month it describes") is
pinned four ways:

- each surprise equals an explicit `lstsq` fit on months 0 .. s-1 (to 1e-10);
- perturbing any month after s leaves every surprise up to s **byte-identical**,
  and truncating the series after s gives the identical prefix;
- the same invariance check **fails** on a single full-sample regression, so a
  pass is not vacuous;
- changing x[s] moves the surprise at s one for one, so the month being described
  is read only as the value and never by the fit.

The hyperparameters (K = 4, 60 months, "AR(1) with intercept, recursive") are read
back from `experiment.json` and compared with the constants in force.
`RunSettings()` still hashes to main's reference digest `ad7fcc1affd0746a`;
the arm's does not.

**Full suite:** `pytest -m "not network"`: `5 failed, 487 passed, 2 skipped, 1 deselected in 159.54s (0:02:39)`, the five failures being exactly those listed below (19 of the passes are the new `tests/test_surprise_quadrants.py`). `ruff check .`, `ruff format --check .` and `mypy` are clean.
Five existing tests fail. None was edited, because tests are additive only:

- `test_configuration_hash_compatibility.py::test_the_omission_map_holds_only_the_two_documented_switches`
  pins the omission map's membership. The arm adds a third entry,
  `growth_and_inflation_surprise_quadrants: False`, which is legitimate by the
  map's own rule (False reproduces main exactly). The test's docstring says it
  "must be revisited ... the day a legitimate third entry is added".
- Four tests in `test_honest_start_date_against_the_live_cache.py` pin main's
  measured defaults on the live cache: the shipped start at 1971-12 with the
  honest-start switch off (the arm gives 1976-12, because 60 months of surprise
  burn-in drop), the widest schedule, and the burn-in sweep choosing 6 states at
  1994-03 and 2 at 1971-12 (the arm fixes 4). Any branch whose default changes the
  observation matrix or the state count fails them. They measure main's default,
  not an invariant.

## Look-ahead audit

Every row of `docs/TECHNICAL_DEBT.md`'s audit table, plus the one path this arm
adds.

| path | touched by A3? | status on this branch, and why |
|---|---|---|
| **Expectation model (new)** | **yes, new path** | **clean.** The AR(1) behind the surprise at month s is fitted on standardised values of months 0 .. s-1 only, one fit per month. At the first forecast date, 1994-03-01, the panel's first surprise is 1955-12, built from coefficients fitted on 1950-12 .. 1955-11. The last is 1994-01, built from coefficients fitted on 1950-12 .. 1993-12. Pinned by the byte-identical invariance test and by the test that shows a full-sample regression failing it. |
| Training panel assembly | no | clean. Panels are still assembled `as_of` each date by `assemble_point_in_time_panel`, and the surprise step only reads the matrix built from that panel. The fallback pre-flight is unchanged: 0 of 391 forecast dates use the publication-lag fallback. |
| Standardisation window | adjacent | clean. Unchanged: expanding, minimum 36 months. Surprises are computed from its output, and the standardised value at s uses months up to s. No second standardisation. |
| State probabilities used in forecasts | no | clean. Only filtered probabilities reach a forecast (`filtered_state_probabilities` in `run_walk_forward`). The surprise columns enter the same forward pass. |
| Model parameters at each refit | yes | clean. Refitted from scratch on the refit date's point-in-time matrix. The quadrant centroids are computed from that same matrix, which ends strictly before the refit date. |
| Number of regimes | yes | clean. Fixed at 4 by the pre-registration, an a priori constant. The sweep still runs on the burn-in window as of 1994-03-01 (panel 1955-12 .. 1994-01, strictly before) and only feeds the regimes-exist gate. |
| Conditional rates | no | clean. Unchanged: only conditions whose publication lag had passed. They are learned against the arm's filtered state probabilities. |
| Benchmark (climatology) | no | clean. Unchanged since ADR 0009. |
| Outcome resolution | no | clean by design. |
| Condition values feeding rate estimation | no | approximation, unchanged (D5). |
| Every run setting | yes | clean. One switch and two constants (K = 4, 60 months), all fixed by the registration before any arm ran. The quadrant boundary is zero, not estimated. |
| Acceptance thresholds | no | clean. Unchanged. |
| Canonicalisation rule | no | clean. Same fixed sort by emission mean, which now reads the growth-surprise mean first. |
| Indicator thresholds | no | weak, unchanged (D12). |
| **Future-perturbation invariance** | runs on this branch | **`forecast audit-look-ahead` exit 0, PASS**, run by `research_arm.sh` on this branch, with every fit recomputed from scratch in both runs. Verbatim: "PASS: no forecast issued on or before 2000-03-01 changed when every observation unavailable at 2000-03-01 was perturbed". Full record in `look_ahead_audit.txt`. |

**What the invariance audit can and cannot see here.** Every quantity at forecast
date t is rebuilt from the panel as of t, and every month in that panel was
published by t. So a regression fitted once on the whole *as-of-t* panel would
**not** move any forecast when data unpublished at the cutoff is perturbed, and
the audit would pass it. That within-panel version is still what the registration
forbids: it restates history the way a full-sample z-score does. Only the
transform-level invariance test catches it. The audit does catch an expectation
model fitted on a *later* panel, such as today's, or any coefficient cached
across dates. The two checks cover different leaks; the transform-level test passes, and the audit's result is in the row above.

## Results

Exit codes from `exit_codes.json`: `check_gates_exit` 0, `compare_exit` 1, `paired_exit` 0, `look_ahead_audit_exit` 0.


Every number below is read by code from the run's outputs in this directory, not retyped. Baseline `main` is configuration `ad7fcc1affd0746a`; this run is `dfd3d31928c59eb6`. Both cover 391 forecast dates from 1994-03-01, with 33 refits. Forecast dates using the publication-lag fallback: baseline 0, this run 0. Paired keys: 9702 resolved forecasts in both, 0 only in the baseline, 0 only in this run (`same_forecasts`: True). Bootstrap: moving block, 10000 resamples, seed 20260908, block length the horizon in months. Confidence levels in the output: [0.9, 0.9833].

### Primary endpoint and harm guards: paired difference in mean Brier skill score, arm minus main

From `paired.json`, at full precision:

| horizon | main skill | arm skill | difference | 90% interval | 98.33% interval | independent obs | resamples used |
|---|---|---|---|---|---|---|---|
| 12 months **(primary)** | 0.21537738742364834 | 0.2337626306814431 | 0.018385243257794753 | [-0.00503989745784288, 0.04042582442114756] | [-0.014957561819215344, 0.05114805461893997] | 31.5 | 9953 |
| 60 months | 0.07276206990291953 | 0.021076597760047888 | -0.05168547214287164 | [-0.1097214440160844, -0.01834959259068851] | [-0.145082267975994, -0.0033906837052748253] | 5.5 | 7495 |
| 120 months | -0.352769097290159 | -0.47083301107811576 | -0.11806391378795678 | [-0.2330510632438104, 0.06894729710712985] | [-1.273835731401695, 0.12020327348501042] | 2.25 | 5443 |

The same table as the tool rendered it, `paired.txt` verbatim:

```
horizon     in both  only baseline  only this run  baseline skill  this run skill  difference  90% interval        98.33% interval     independent obs  resamples
----------  -------  -------------  -------------  --------------  --------------  ----------  ------------------  ------------------  ---------------  ---------
12 months   3754     0              0              +0.2154         +0.2338         +0.0184     [-0.0050, +0.0404]  [-0.0150, +0.0511]  31.5             9953
60 months   3274     0              0              +0.0728         +0.0211         -0.0517     [-0.1097, -0.0183]  [-0.1451, -0.0034]  5.5              7495
120 months  2674     0              0              -0.3528         -0.4708         -0.1181     [-0.2331, +0.0689]  [-1.2738, +0.1202]  2.2              5443
```

Per-indicator paired differences (point estimates; the interval belongs to the mean), `paired.txt` verbatim:

```
indicator                                                   12 months  60 months  120 months
----------------------------------------------------------  ---------  ---------  ----------
consumer_price_inflation_above_five_percent_within_horizon  +0.0098    -0.0707    +0.1467
consumer_price_inflation_above_three_percent_at_horizon     +0.0010    -0.0426    +0.0437
economy_in_recession_at_horizon_date                        +0.0835    +0.0475    +0.0782
economy_in_recession_within_horizon                         +0.0043    -0.0744    -1.3935
federal_funds_rate_above_four_percent_at_horizon            +0.0980    -0.0865    -0.0933
federal_funds_rate_below_one_percent_within_horizon         +0.0317    +0.0747    -0.0069
industrial_production_growth_above_two_percent_at_horizon   +0.0767    +0.0356    +0.0336
treasury_yield_curve_inverted_within_horizon                +0.0424    -0.1094    +0.2216
unemployment_rate_above_five_percent_at_horizon             -0.0971    -0.0859    -0.0306
unemployment_rate_above_seven_percent_within_horizon        -0.0664    -0.2051    -0.0690
```

### 0001's five-gate verdict, thresholds unchanged

The arm's from `.cache/models/verdicts.parquet`, written by this run's `evaluate`. Main's from the committed `baselines/main.json`.

| horizon | main verdict | main failing gates | arm verdict | arm failing gates | arm mean skill [90% bounds] |
|---|---|---|---|---|---|
| 12 months | SHIP BASE RATE | calibration | SHIP BASE RATE | calibration | 0.2337626306814431 [0.11763426370280945, 0.345843287765201] |
| 60 months | SHIP BASE RATE | skill, calibration, robustness | SHIP BASE RATE | skill, calibration, robustness | 0.021076597760047888 [-0.2798326660143726, 0.16569083605468346] |
| 120 months | SHIP BASE RATE | skill, calibration, robustness, honesty | SHIP BASE RATE | skill, calibration, robustness | -0.47083301107811576 [-0.5981714727628572, -0.11059197798652477] |

`compare.json` (the plain comparison, exit 1): counts {'ADDED': 0, 'IDENTICAL': 108, 'MOVED': 279, 'NUMERICAL': 0, 'REMOVED': 0}. The categorical moves, verbatim:

- `run` (run) `configuration_hash`: 'ad7fcc1affd0746a' -> 'dfd3d31928c59eb6'
- `run` (run) `state_count`: 6 -> 4
- `horizons` 120 `failing_gates`: 'skill, calibration, robustness, honesty' -> 'skill, calibration, robustness'

### Calibration error and log loss against main

**Pooled expected calibration error**, the figure 0001's calibration gate reads (threshold 0.10, 10 bins). The pipeline does not export it, so it is derived here by calling the verdict's own three functions on each run's forecasts: `evaluation.verdict._skill_matrix`, `evaluation.calibration.cross_sectional_design_effect` and `evaluation.calibration.assess_calibration`. The arm's one-year value reproduces the 0.1169 in this run's `check_gates.log`, which shows it is the same computation.

| horizon | main pooled ECE | arm pooled ECE | arm minus main | main reversals beyond noise | arm reversals beyond noise |
|---|---|---|---|---|---|
| 12 months | 0.12495346662661265 | 0.1169077761181062 | -0.008046 | 0 | 0 |
| 60 months | 0.19421638468146912 | 0.23924969670520227 | +0.045033 | 0 | 0 |
| 120 months | 0.11558085146718161 | 0.16429924971379864 | +0.048718 | 0 | 2 |

The registration asks for this beside the distribution a *perfectly* calibrated forecaster would produce at the same sample size. The pipeline does not compute that distribution, and this arm did not build a new simulation for it. The reference on record is briefing 01's derivation (`research/briefings/derivations/sim_calibration.py`, on a synthetic logit-normal forecaster, not this run's probabilities): at about 31 independent one-year observations, a perfectly calibrated forecaster fails ECE < 0.10 about 91% of the time, with median ECE 0.153. Both runs' one-year values sit below that median, so neither one-year calibration failure is, on its own, evidence of miscalibration.

**Per-indicator calibration error and log loss**, averaged across the ten indicators by code from `compare.json`'s indicator rows (each row there quotes both runs; these are plain means of them):

| metric | horizon | main, mean of 10 | arm, mean of 10 | arm minus main |
|---|---|---|---|---|
| expected_calibration_error | 12 months | 0.159923 | 0.138879 | -0.021044 |
| expected_calibration_error | 60 months | 0.250160 | 0.288100 | +0.037940 |
| expected_calibration_error | 120 months | 0.281918 | 0.286376 | +0.004458 |
| logarithmic_loss | 12 months | 0.594038 | 0.581818 | -0.012220 |
| logarithmic_loss | 60 months | 0.758704 | 0.785610 | +0.026907 |
| logarithmic_loss | 120 months | 0.692559 | 0.706562 | +0.014003 |

### Lambda2 and the implied information horizon

The second-largest eigenvalue modulus of each backtest refit's transition matrix, computed from the cached fitted models (the arm's under its own configuration hash, main's under `ad7fcc1affd0746a`). Half-life is ln 0.5 / ln lambda2, in months.

| run | refits | first refit | last refit | median | min | max | median half-life |
|---|---|---|---|---|---|---|---|
| main | 33 | 1994-03-01: 0.9777 | 2026-03-01: 0.9845 | 0.9777 | 0.9534 | 0.9985 | 30.8 months |
| arm A3 | 33 | 1994-03-01: 0.9569 | 2026-03-01: 0.9896 | 0.9849 | 0.9569 | 0.9909 | 45.6 months |

Refit for refit, the arm's lambda2 is above main's at 24 of 33 refit dates.

## Verdict under the pre-registered rule

The rule, from `decision_rule` in `experiment.json`, applied by code to `paired.json`:

- **PROMISING** needs the one-year 90% interval entirely above zero. Its lower bound is -0.00503989745784288, not above zero: **not met**.
- **CONFIRMED_IN_SAMPLE** needs the one-year interval at 1 - 0.10 / 6 = 98.33% entirely above zero. `paired.json` carries a 0.9833 interval, lower bound -0.014957561819215344: **not met**.
- **HARMFUL** needs the 90% interval entirely below -0.02 at any horizon, meaning its upper bound is below -0.02:

| horizon | 90% interval | test | entirely below -0.02 |
|---|---|---|---|
| 12 months | [-0.00503989745784288, 0.04042582442114756] | 0.04042582442114756 < -0.02 ? | no |
| 60 months | [-0.1097214440160844, -0.01834959259068851] | -0.01834959259068851 < -0.02 ? | no |
| 120 months | [-0.2330510632438104, 0.06894729710712985] | 0.06894729710712985 < -0.02 ? | no |

  **not met**. Five years comes closest: its upper bound -0.01834959259068851 misses the harm line by +0.001650. Its 98.33% interval [-0.145082267975994, -0.0033906837052748253] also lies entirely below zero. The arm is measurably worse than main at five years, but not by enough to be called harmful under the registered threshold.

**Verdict: none.** Not PROMISING, not CONFIRMED_IN_SAMPLE, not HARMFUL. Check (a), the deterministic audit, **passed** (exit 0). Check (b), the judged look-ahead review by an agent that did not write this arm, is outside this arm's remit and has not been run here. The arm is not void on (a); whether it stands depends on (b).

## Prediction versus outcome

The pre-registration predicted "Lambda2 well below main's, since surprises are far
less persistent than levels. One-year skill lower than A2."

- **Lambda2: the prediction failed.** Main's median refit lambda2 is 0.9777; the arm's is 0.9849, higher rather than well below, and above main's at 24 of 33 refit dates. Surprises are far less persistent than levels, as the registration reasoned. But the rates column is unchanged, and the states separate on rates: in the gate-2 sweep every state's growth and inflation surprise means lie within +/-0.06 while its rates means span -1.47 to +2.47. The chain's persistence comes from rates. Consistent with that, ten-year `honesty` (distance to the stationary distribution) now passes where main failed it: a slower-forgetting chain stays further from stationary.
- **One-year skill: lower than A2?** Not assessable here, because A2's result was not available to this arm. Against main, the one-year point estimate is higher (0.018385243257794753) with a 90% interval [-0.00503989745784288, 0.04042582442114756] that spans zero. `stated_in_advance` expected A2 and A3 to underperform main. At one year that is not what happened. At five years it is, with an interval entirely below zero, but not below the harm line.
- `stated_in_advance` also said an interval spanning zero is the likeliest outcome for any single arm. At the primary horizon, that is what happened.

## Deviations, surprises, and what could not be done

- **Where the switch's default lives.** The brief asks for a `RunSettings` field
  whose default on this branch is the arm's behaviour. Setting the dataclass
  default to True was tried first, and it broke 22 existing tests that construct
  `RunSettings(...)` directly to exercise main's walk-forward and audit
  mechanics. Most pass `state_count=2`, which the arm refuses. The dataclass
  default is therefore False, and `DEFAULT_RUN_SETTINGS`, the object every command
  runs, sets it to True. Every command on the branch still runs the arm. The one
  cost is the omission-map membership test above.
- **The hyperparameters are constants, not fields.** K and the 60-month minimum
  are module constants beside the code that reads them, as
  `MINIMUM_PERIODS_FOR_STANDARDISATION` already is. Fields would have entered the
  digest and broken `RunSettings()`'s match to main's hash. The switch's own place
  in the digest identifies the arm, and a test reads both constants back from the
  registration.
- **Gate 2 (`fit-regimes`) is unchanged.** It still judges the full-sample
  sweep's winner. The registration's "no longer chooses K" is applied to every fit
  that issues a forecast (the backtest refits and `forecast-now`), not to the
  diagnostic sweep. On this branch it **passed**. The sweep on the full surprise
  matrix (848 months) chose 5 states on held-out log likelihood (0.3059 per month;
  the Bayesian information criterion prefers 6). The shortest expected visit is
  14.8 months, the smallest state holds 9.3%, and the path makes 30 switches in 848
  months, 0.42 a year.
- **The surprise columns barely separate the full-sample states.** In the gate-2
  winner, every state's growth and inflation surprise means lie within ±0.06,
  while its rates means run from −1.47 to +2.47. The regimes found on this matrix
  are rate regimes. The sweep's second eigenvalue moduli are 0.985 to 0.998, not
  below main's median refit value of 0.9777. The persistence the registration
  expected surprises to remove comes back through the unchanged rates column.
  This is an observation from the diagnostic sweep; the backtest refits' lambda2
  is in the results section.
- **The run was paused for 4 h 44 min by the machine, not the code.** The system log
  (`pmset -g log`) records "Entering Sleep state due to 'Low Power Sleep' ... Using Batt
  (Charge:1%)" at 2026-09-15 16:00:46 and "Wake from Hibernate ... Using AC" at
  20:44:16. The arm's refits run 28 to 41 seconds apart on either side of the gap
  (2001-03-01 written at 16:00:14, 2002-03-01 at 20:44:20), and three other arms
  running at the same time stalled with it. Hibernation preserves process state and
  the run is deterministic, so no number depends on the pause. The slate's wall-clock
  timings do.
- **More data per state.** Four states rather than six raise `mean_effective_sample_size` at 30 of 30 indicator-horizon rows in `compare.json`, by +28.57 to +49.83. That is the half of A2's reasoning ("more data per state") that this arm inherits. At one year, calibration improved too; at five and ten years it did not.
- **A2 comparison.** The prediction is stated relative to A2, whose result was not
  available to this arm. It runs in parallel, and this arm does not read other
  worktrees.
