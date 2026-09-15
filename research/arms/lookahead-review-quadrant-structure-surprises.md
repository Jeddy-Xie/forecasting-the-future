# Look-ahead review: arm A3, quadrant-structure-surprises (experiment 0002)

Independent reviewer: I did not write this arm. Reviewed 2026-09-15.
Change: `git diff 2e025b7...research/quadrant-structure-surprises`, with the code at `ea76a67` and the
outputs at `5565fc1`. Paths are relative to the worktree at `ea76a67`. I did not modify the
worktree, and `git status` was clean before and after. Every run below used scratch copies and a
scratch cache, through `ECONOMIC_REGIME_FORECASTING_CACHE`.

## quadrant-structure-surprises
VERDICT: CLEAN

I found no path by which information from after a forecast date reaches that forecast, either in the
walk-forward or in `forecast_now`. The code implements the REGISTERED recursive design, not just one
the audit would pass. Evidence follows.

### 1. Deterministic audit
- `exit_codes.json`: `look_ahead_audit_exit` 0, commit `ea76a677`.
- `look_ahead_audit.txt`: "PASS: no forecast issued on or before 2000-03-01 changed when every
  observation unavailable at 2000-03-01 was perturbed". Both of its runs report "4 regimes chosen on
  the burn-in window, 7 fits computed from scratch", so the audit ran the arm and not main.

### 2. The recursive AR(1). Registered: OLS on months strictly before s, expanding, 60 months before the first surprise
- Function: `src/economic_regime_forecasting/features/transforms.py:214`,
  `recursive_autoregressive_surprise`. The boundary is at `:266-267`: `last_pair = positions - 2`,
  `pair_count = positions - 1`. Entry k of each running sum covers the pairs (x[j-1], x[j]) for
  j = 1..k+1. The fit for position s therefore covers j = 1..s-1, which is months 0..s-1: strictly
  `<` s. The forecast reads x[s-1] and the surprise reads x[s] (`:283-284`). The first position is 60
  (`:207`), so the first fit has exactly 60 months behind it.
- **On real data**, which I ran: at as_of 1994-03-01 (458 surprises) and 2026-09-15 (848 surprises),
  in both columns, every surprise equals an explicit `lstsq` fit on months < s to within 8.9e-15.
  Truncating the series at four points leaves the prefix byte-identical. The matrix columns the
  model reads are exactly these series, the rates column is unchanged, and the last month is
  unchanged. The recursive surprises differ from ONE regression over each date's own panel by up to
  0.039 to 0.093 standardised units. The distinction the arm raised is therefore material, and the
  code is on the registered side of it.
- **The arm's tests discriminate.** I ran `tests/test_surprise_quadrants.py` against three scratch
  copies of `src/`, with each session printing which `transforms.py` it imported. A first attempt
  was void: `pyproject.toml:55` `pythonpath = ["src"]` overrides `PYTHONPATH`, so it silently tested
  the unmodified code. I overrode it with `-o pythonpath=`.

  | source under test | result |
  |---|---|
  | unmodified | 19 passed |
  | M1: one regression over the whole series (the non-recursive design) | 4 failed: explicit-lstsq `:144`, byte-identical invariance `:157`, companion `:172`, one-for-one `:185` |
  | M2: month s enters its own fit (`<=` instead of `<` at the boundary) | 2 failed: explicit-lstsq `:144`, one-for-one `:185` |

  The byte-identical invariance test (`:157`) passes on M2, as it must, because M2 reads nothing
  after s. So the `<` boundary is pinned by the explicit-lstsq and one-for-one tests, not by the
  invariance test. The companion test (`:172`) checks its own leaky helper AND the production
  function, and it fails on M1.

### 3. Surprise taken after the expanding standardisation
- `transforms.py:180-201`, unchanged from main: `frame.expanding(min_periods=36)`, so row t is scaled
  by rows 1..t only.
- `features/observation_matrix.py:140-185`: the surprise is applied to `matrix.standardised`. The
  standardised value z_j uses months ≤ j, the AR at s uses z_0..z_{s-1}, and the surprise uses z_s. The
  latest observation the surprise at s touches is month s itself. The panel starts in 1950-12 at both
  1994-03 and 2026-09, so the expanding origin does not move with as_of.
- Nothing is standardised again afterwards, so the quadrant boundary is literally zero
  (`models/surprise_quadrants.py:75-76`).

### 4. Every value the change introduces, traced to publication
| quantity at date t | inputs | latest observation touched | why it was published by t |
|---|---|---|---|
| growth and inflation surprise columns | the as-of-t panel from `assemble_point_in_time_panel` (unchanged), standardised, then the recursive AR | last month of the as-of-t panel | the panel is assembled `as_of` t: `backtest/walk_forward.py:240-243`, `:351-356`, `:583`; `command_line_interface.py:126-133` |
| quadrant centroids at refit r | that refit's own configured matrix (`walk_forward.py:276`) | last month of the as-of-r panel | same |
| K = 4 | constant `surprise_quadrants.py:29`; refit refuses any other count (`walk_forward.py:245`) | none | a priori |
| burn-in sweep as of 1994-03-01 | level matrix checked `panel_end < first_forecast_date` (`backtest/state_count_on_burn_in.py:165`, strict), then the surprise step (`:176`), which can only drop leading months (guard at `observation_matrix.py:169-174`) | 1994-01 | `check_gates.log:302`: "458 months of burn-in (1955-12-01 .. 1994-01-01)". Under the arm it is only reported; K is fixed (`:188`) |
| conditional rates at a refit | filtered probabilities indexed by the surprise matrix's OWN dates (`walk_forward.py:283-284`), inner-joined with `condition_available_at` | unchanged | main's publication-lag rule, untouched by the diff; the 60 dropped months cannot shift a probability onto another date |

- **Filtered only.** `walk_forward.py:357` takes `[-1]` of `filtered_state_probabilities`, and so
  does `command_line_interface.py:340`. The only calls to `smoothed_state_probabilities`
  (`models/state_labelling.py:173`, `models/state_selection.py:222`) are main's regime description
  and sweep. The diff does not touch them, and neither is on a forecast path.
- **The D5 channel.** The diff adds no data read: it uses the same panel and the same three inputs,
  and leaves the rates column unchanged. Outcome resolution and `_expanding_climatology` are not
  touched. The diff to `walk_forward.py` is only the three matrix call sites and the fit.
- **After the audit's cutoff.** The new code has no date-dependent branch. It is a pure function of
  each date's as-of panel. Fitted models are cached under as_of, state count, seed and configuration
  hash, so nothing carries from one date to another.

### 5. Hyperparameters
- K = 4 (`surprise_quadrants.py:29`) and 60 months (`transforms.py:207`).
  `tests/test_surprise_quadrants.py:105-115` reads both from `experiment.json`, and it passes. The
  boundary is 0, not estimated. The only other new constants are
  `MINIMUM_MONTHS_FOR_AN_AUTOREGRESSION = 3`, a guard that never binds at 60, and the tie rule: a
  surprise of exactly zero counts as at-or-below, which happens with probability zero on continuous
  data. Every other `RunSettings` field equals main's.
- **One run.** The branch has two commits: `ea76a67` (the code) and `5565fc1` (8 files, all under
  `research/arms/quadrant-structure-surprises/`). The reflog shows nothing else. Every refit model
  under the arm's hash `dfd3d31928c59eb6` was written between 15:55:42 and 20:57:15, after
  `ea76a67` at 15:50:26. Four burn-in files were written during development (15:38 to 15:46). All
  four show K = 4 and a panel starting in 1955-12, the 60-month drop, so no other value was tried.
- One of those four is the 1994-03 choice under `dfd3d31928c59eb6`, written at 15:46:32. It predates
  the commit, and check-gates read it from cache. I recomputed it from scratch with the committed
  code: byte-identical (`cmp`).
- Observation, not a leak: the 60-month constant is not in the configuration hash. K is, through the
  `states4` part of the model file name. A later change to the 60 would silently reuse cached
  models. As shown above, that did not happen in this run.

### 6. The switch was ON for every output
- With the switch set to True, `DEFAULT_RUN_SETTINGS` (`configuration/run_settings.py:238`) hashes
  to `dfd3d31928c59eb6`. `RunSettings()` hashes to `ad7fcc1affd0746a`, main's registered
  reference. I computed both.
- `src/` has no other `RunSettings(...)` construction. Every command enters through
  `Workspace.open(DEFAULT_RUN_SETTINGS)` (`command_line_interface.py:115`). `research_arm.sh`
  refuses to run unless the worktree imports its own `src/` (`assert_isolated`).
- **check-gates:** `check_gates.log:302` shows 4 regimes, "fixed by the surprise quadrant structure",
  on 458 months. `:311` shows configuration hash `dfd3d31928c59eb6`. `:382` shows all five gates
  passed.
- **The backtest:** `paired.json` `current_run` has configuration hash `dfd3d31928c59eb6` and
  state count 4. `compare.json`'s categorical moves are `ad7fcc1affd0746a` to `dfd3d31928c59eb6`
  and state count 6 to 4.
- **Today's forecast:** `model_2026-09-15_states4_seed20260908_dfd3d31928c59eb6.json`, written at
  15:55:42 together with `current_forecasts.parquet`.
- **The audit:** "4 regimes chosen on the burn-in window" in both of its runs.
- Main's behaviour would have produced hash `ad7fcc1affd0746a` and 6 states. Neither appears in any
  of the arm's outputs.

### 7. forecast_now
In `command_line_interface.py:310-350`:
- The matrix is `observation_matrix_as_of(today)`, which is configured (`:126-133`).
- The model comes from `fit_regime_model(today, ..., 4)` (`:330-337`). That is the same function the
  walk-forward refits call: it builds the same configured matrix and learns the rates against its
  filtered probabilities.
- The forecast reads `filtered[-1]` (`:340`).
- `selected_model.json` supplies only a state count, and the arm overrides it with 4.

This is consistent with the backtest.

### 8. The five failing existing tests
I ran them on the worktree's code against a scratch cache. Exactly these five fail, with these
assertions:

| test | assertion | classification |
|---|---|---|
| `tests/test_configuration_hash_compatibility.py:107`, omission-map membership | the set now includes `growth_and_inflation_surprise_quadrants` | **Expected.** The entry holds main's value, False. With it, `RunSettings()` still hashes to `ad7fcc1affd0746a`. When the switch is False, `observations_as_configured` returns the matrix itself (`observation_matrix.py:202`) and K is not fixed (`surprise_quadrants.py:48-50`). The docstring (`:108-112`) anticipates a legitimate third entry. |
| `tests/test_honest_start_date_against_the_live_cache.py:72`, shipped start with the switch off | 1976-12 ≠ 1971-12 | **Expected.** The registered 60-month surprise burn-in delays the 240-month panel-length start by exactly 60 months. |
| same file `:87`, widest schedule | 1976-12 ≠ 1971-12 | **Expected**, same cause. The arm's backtest starts at 1994-03, and the two honest-start tests in this file pass. |
| same file `:107`, burn-in at 1994-03 | 4 ≠ 6 | **Expected.** K = 4 is registered, and the panel has 458 months rather than 518, 60 fewer. |
| same file `:125`, burn-in at 1971-12 | 4 ≠ 2 | **Expected.** K is fixed. |

None of the five is a defect in the arm. Each pins main's measured default, which A3 is registered
to change.

### 9. Headline numbers, extracted by code
- **Found verbatim in `REPORT.md`:** every number in `paired.json`'s horizon rows, namely both runs'
  skill, the difference, both interval bounds at 0.90 and at 0.9833, the independent observations
  and the resamples.
- All 30 per-indicator differences match the report's table.
- Keys: 9702 rows in both runs, 0 in only one of them, `same_forecasts` True.

| horizon | arm minus main | 90% interval | 98.33% interval |
|---|---|---|---|
| 12 months | +0.018385 | [-0.005040, +0.040426] | [-0.014958, +0.051148] |
| 60 months | -0.051685 | [-0.109721, -0.018350] | [-0.145082, -0.003391] |
| 120 months | -0.118064 | [-0.233051, +0.068947] | [-1.273836, +0.120203] |

- **The decision rule, applied by code:**
  - PROMISING: no 90% lower bound lies above zero, so not met.
  - CONFIRMED_IN_SAMPLE: no 98.33% lower bound lies above zero, so not met.
  - HARMFUL: no 90% upper bound lies below -0.02, so not met. Five years comes closest, at
    -0.018350.

  The report's "verdict none" is supported.
- **`compare.json`:** counts ADDED 0, IDENTICAL 108, MOVED 279, NUMERICAL 0, REMOVED 0; exit 1.
  These also match the report:
  - the three categorical moves;
  - the per-indicator means of expected calibration error and log loss, six rows;
  - the rise in effective sample size: 30 of 30 rows, +28.57 to +49.83.
- **Not re-derived:** the report's pooled calibration-error and lambda2 tables. They come from
  caches, not from these two files.

### Outside the verdict: not a look-ahead
Notebooks 02 and 04 build the matrix with `build_observation_matrix` directly
(`notebooks/02_regime_model.ipynb`, source line 60; `notebooks/04_report.ipynb`, cell 6). They then
filter the cached `selected_model.json` on it. That means level columns are fed to a model that,
under the arm, was fitted on surprises. The result would be a wrong figure, not a leak. No notebook
produced any of the arm's outputs, since `research_arm.sh` runs none. It matters only if the arm
ships.
