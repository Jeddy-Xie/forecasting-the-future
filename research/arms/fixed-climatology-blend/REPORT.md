# A6 — fixed-climatology-blend

## Sequence of this report (the coordinator asked this be on the record)

1. **Stopped, before writing any blend code.** The brief's own pre-implementation
   check ("check whether `climatology_probability` is ever NaN at a forecast
   date from 1994-03 onward... if it does, stop and report it") found it is:
   `NaN` on every one of today's 30 forecasts (10 indicators x 3 horizons) and
   on 39 of 11,730 historical backtest rows, in main's own committed baseline.
   Diagnosed (wrongly) as the benchmark refusing to report a value because
   nothing had resolved. Reported and stopped, per the brief, rather than
   papering over it.
2. **Corrected diagnosis from the coordinator**, matching what `submit()`
   already does for the shipped base rate: the NaN is an **index-coverage**
   problem, not a resolution problem. `climatology_probability` is looked up
   by exact date against a series indexed on the resolution series' own
   months, and that index simply ends before the forecast schedule does.
   Thousands of outcomes have resolved and been published by today; the
   benchmark is well-defined, it just has no entry filed under today's date.
   No scored row was ever affected (every one of the 39 backtest rows has an
   unresolved `realised_outcome`), and the same shape existed on the
   pre-fix run from 2026-09-10.
3. **Implemented** the carry-forward: at a forecast date past the benchmark's
   own last entry, use the most recent value **on or before** that date
   (`pandas.Series.asof`, which cannot look ahead by construction — the same
   rule `submit()`'s `latest_climatology` already applies to the shipped base
   rate). Recorded, never silent. Tests added, additive only. Full suite,
   ruff and mypy clean.
4. **Ran** `scripts/research_arm.sh run fixed-climatology-blend` once, on
   commit `e3f70e5c0eb571c7045560bbfd272fd65acca195`, tree clean at start and
   end. This report's numbers are from that run.

## What changed

Pure post-processing of the model's own forecasts; the model itself, the
walk-forward schedule, the panel, and every other setting are untouched.

- `src/economic_regime_forecasting/configuration/run_settings.py` —
  `RunSettings.climatology_blend_model_weight: float = 0.5` (the arm's
  behaviour, default on this branch), validated to `[0.0, 1.0]` in
  `__post_init__`. Added to `SETTINGS_OMITTED_FROM_THE_HASH_WHEN_THEY_HOLD_THE_SHIPPED_VALUE`
  at `1.0` (pure model, the value that reproduces the behaviour that preceded
  this field). Two new `ArtifactNames` entries for the carry-forward record
  (below).
- `src/economic_regime_forecasting/backtest/walk_forward.py` — three new
  functions: `climatology_probability_for_blend` (the exact-date lookup, or
  the most recent value on or before the forecast date, with a `bool` saying
  which), `blend_model_and_climatology_probability` (the weighted sum, raising
  on any non-finite input rather than producing or propagating a `NaN`), and
  `climatology_carry_forward_record` (the deliberate-fallback record: row
  counts and the exact indicator/date/horizon of every row that used it).
  `run_walk_forward` now writes the blend into `predicted_probability`, the
  unblended number into a new `model_probability` column, the value actually
  used for the blend into a new `climatology_probability_used_in_blend`
  column, and whether it was carried forward into a new
  `climatology_carried_forward` column. `climatology_probability` itself is
  untouched — still the exact-date lookup, still `NaN` on exactly the rows it
  always was, because `evaluation.verdict.compute_metrics` and
  `_skill_matrix` drop a row from scoring on that `NaN`, and this arm must
  not change which rows that is.
- `src/economic_regime_forecasting/command_line_interface.py` — `forecast_now`
  applies the same blend to today's forecast (the brief's second required
  site), writes the same four columns, and both `forecast_now` and
  `run_backtest` write a carry-forward record artifact and print a one-line
  summary of it.
- Tests, listed under "Every edit to an existing test" and "New tests" below.

## Confirmed: the climatology this arm blends with is point in time

`git merge-base --is-ancestor 628a77d HEAD` exits 0 on this branch (HEAD is
`e3f70e5`): commit `628a77d` (the ADR 0009 fix, "an outcome counts only once
it was published") is an ancestor. The benchmark this arm blends with is the
publication-lag-aware one, not the version that let each outcome in 32-400
days early.

## Every edit to an existing test

Additive only; no assertion was removed or loosened. Full list:

- `tests/test_walk_forward_backtest.py` — `_valid_results()`, the fixture
  `validate_results` tests build a results frame from by hand, extended with
  the three new columns (`model_probability`,
  `climatology_probability_used_in_blend`, `climatology_carried_forward`), so
  those tests still describe a frame the current `RESULT_COLUMNS` accepts.
  Nothing about what `validate_results` is asked to check changed.
- `tests/test_verdict_and_gates.py` — `_results()`, the same kind of
  hand-built results frame used by the gate-four and evaluation tests,
  extended with the same three columns for the same reason. This one had a
  real, measured failure before the fix:
  `test_gate_four_passes_a_clean_run` failed, because `gate_four_backtest`
  checks `all(column in results.columns for column in RESULT_COLUMNS)` and
  the fixture was missing the three new ones. Not a pinned assertion about
  main's behaviour — a fixture that needed the schema update every other
  results-frame fixture in the suite also needed. Fixed the same way; the
  full suite is green (below), so there is no case here of the kind the
  coordinator asked to document as a legitimate main-pinned failure.
- `tests/test_configuration_hash_compatibility.py`:
  - `test_the_shipped_configuration_hashes_to_the_recorded_digest` —
    added `climatology_blend_model_weight=1.0` to the `RunSettings(...)` call
    so it still reproduces `SHIPPED_HASH`, alongside the two existing
    switches at their own shipped values.
  - `test_an_unconditional_omission_would_let_two_different_runs_share_one_hash` —
    generalised from booleans only (`isinstance(shipped_value, bool)`,
    `not shipped_value`) to also cover a float entry, via a new
    `_a_different_value` helper. The type check was **widened**
    (`isinstance(shipped_value, bool | float)`), not removed: this file's own
    test covenant refused my first attempt at this edit because it dropped
    that assertion entirely (2 to 1 in the loop body); the version actually
    committed keeps two assertions per iteration, generalised rather than cut.
  - `test_the_omission_map_holds_only_the_two_documented_switches` — renamed
    to `test_the_omission_map_holds_only_the_three_documented_settings` and
    its expected set extended with `"climatology_blend_model_weight"`. Same
    assertion, wider membership set, matching the map's actual, append-only
    contents.
  - Module docstring extended with a paragraph on the third entry.
  - Four new tests appended (listed below); nothing existing was shortened.

## New tests

- `tests/test_walk_forward_backtest.py`: six tests directly on
  `climatology_probability_for_blend` (exact match used when present; carries
  forward across a gap; **the boundary test — a value strictly after the
  forecast date is never read, requirement 1**; carries forward to a value
  exactly on the date, never one the day after; skips an internal `NaN` when
  carrying forward; reports `NaN` when nothing precedes the date); three on
  `blend_model_and_climatology_probability` (weight semantics at 0.5/1.0/0.0;
  raises rather than propagate a `NaN` climatology; raises on a non-finite
  model probability); one on `climatology_carry_forward_record`'s counting and
  naming; one full `run_walk_forward` integration test that engineers the real
  failure mode (a resolution-only series, not a model input, given a shorter
  cache than the model's own inputs) and checks, on real output: the
  carry-forward path is actually exercised, every carried-forward row's date
  is on or after the boundary (**requirement 1, end to end**), the exact-date
  `climatology_probability` stays `NaN` on those rows, **no row with both a
  resolved outcome and a non-`NaN` exact benchmark ever took the carry-forward
  (requirement 2)**, and every `predicted_probability` stays finite; and two
  algebraic ties between `predicted_probability` and its recorded inputs (the
  default weight 0.5, and weight 1.0 reproducing the unblended model number).
- `tests/test_configuration_hash_compatibility.py`: four tests on the new
  field — its default is 0.5 and not the omitted 1.0; the two weights hash
  differently; a weight outside `[0, 1]` (including `NaN`) is rejected at
  construction; the boundary weights 0.0 and 1.0 are accepted.

## Suite, lint, types

- `PYTHONPATH=<worktree>/src .venv/bin/python -m pytest -m "not network" -q`
  — full suite, exit 0, all passed (two pre-existing, unrelated skips).
  Isolation checked first every time: `economic_regime_forecasting.__file__`
  resolved inside this worktree's `src/`.
- `ruff check .` — all checks passed.
- `ruff format --check .` — all files already formatted.
- `mypy` — Success: no issues found in 39 source files.

## Look-ahead audit table (`docs/TECHNICAL_DEBT.md`), for this change

| path | status on this arm |
|---|---|
| Training panel assembly | unchanged — clean. The blend never touches the observation matrix or model fitting. |
| Standardisation window | unchanged — clean |
| State probabilities used in forecasts | unchanged — clean. `climatology_probability_for_blend` is applied to the already-filtered composed probability; it does not touch how the state distribution itself is computed. |
| Model parameters at each refit | unchanged — clean. `configuration_hash` changed (a new `RunSettings` field, see below), so every fit for this run was recomputed from scratch rather than read from main's cache, but the fitting code and its inputs are identical; 6 regimes chosen at the same burn-in window (1950-12 to 1994-01), the same held-out log likelihood (-3.0801/month) as main's recorded run. |
| Number of regimes | unchanged — clean |
| Conditional rates | unchanged — clean |
| **Benchmark (climatology)** | clean, and the row this arm's whole design turns on. `climatology_probability` (the column evaluation scores against) is untouched: exact-date lookup, `NaN` on exactly the same 39 of 11,730 backtest rows and today's 30 rows as before. The **new** thing, `climatology_probability_for_blend`, reads **only** dates on or before the forecast date (`pandas.Series.asof`; boundary pinned by a dedicated test and, end to end, by the audit below) — so it can use less information than a forecaster at that date had, never more. |
| Outcome resolution | unchanged — clean by design |
| Condition values feeding rate estimation | unchanged — approximation, D5 |
| Every run setting | unchanged in kind — one new setting added (`climatology_blend_model_weight`), a priori and pre-registered at 0.5 (arm A6), not derived from data |
| Acceptance thresholds | untouched — `proving/` was not edited |
| Canonicalisation rule | unchanged — clean |
| Indicator thresholds | unchanged — weak, D12, untouched |
| **Future-perturbation invariance** (`forecast audit-look-ahead`) | **ran on this branch: exit 0.** "PASS: no forecast issued on or before 2000-03-01 changed when every observation unavailable at 2000-03-01 was perturbed." Cutoff 2000-03-01, 73 forecast dates, 7 refits, 2190 rows compared (`predicted_probability` — the blended value — `regime_distribution`, `climatology_probability`, `state_count`, `refit_date`), 627,617 values perturbed across 1348 copied cache entries, wall time 357s. `predicted_probability` is the blended number in this comparison, so the audit is a direct end-to-end check that the blend itself introduces no look-ahead, not just the model underneath it. |

VOID check (a), the deterministic one, passes as shown above. VOID check (b),
the judged look-ahead review by an agent that did not write this arm, is
outside this report's scope — it is a separate review step.

## Results

Quoted from `research/arms/fixed-climatology-blend/paired.json` and
`compare.json`, this run's own artifacts, unrounded beyond what is shown.

**Primary endpoint — one-year paired difference in mean Brier skill score,
this run minus main**, 3754 forecasts in both, block length 12 months, about
31.5 independent observations:

```
difference   -0.020864164503446414
90% interval    [-0.06965666649548773, +0.029634503731571022]
98.33% interval [-0.08950485591771964, +0.05432523623681685]
```

**Five-year** (secondary), 3274 forecasts in both, ~5.5 independent
observations:

```
difference   +0.014086867005625614
90% interval    [-0.05151878804532016, +0.17424775593936376]
98.33% interval [-0.07885186465190011, +0.2905951383032996]
```

**Ten-year** (secondary, and the harm guard), 2674 forecasts in both, ~2.25
independent observations:

```
difference   +0.2779072602106567
90% interval    [+0.12042003037043993, +0.3309703222335998]
98.33% interval [+0.08043946550168865, +1.834216387168502]
```

Mean Brier skill scores this run produced, quoted the same way:
one year `+0.19451322292020193` (main `+0.21537738742364834`); five year
`+0.08684893690854514` (main `+0.07276206990291953`); ten year
`-0.07486183707950227` (main `-0.352769097290159`).

**0001's five-gate verdict, unchanged thresholds** (`compare.json`,
`check_gates.log`): all three horizons still ship the base rate, on both
runs — this arm does not flip a single 0001 verdict, consistent with
`why_not_the_0001_verdict`'s reasoning that this gate is not the route to a
finding.

- 1 year: SHIP BASE RATE on both runs. Failing gate identical: `calibration`.
- 5 year: SHIP BASE RATE on both runs. Failing gates identical:
  `skill, calibration, robustness`.
- 10 year: SHIP BASE RATE on both runs. Failing gates **differ**: main fails
  `skill, calibration, robustness, honesty`; this run fails only
  `skill, calibration, honesty` — the ten-year **robustness** gate now
  passes (`compare.json`'s only non-identity field besides
  `configuration_hash`: `failing_gates` at `row: "120"`,
  `MOVED` from `"skill, calibration, robustness, honesty"` to
  `"skill, calibration, honesty"`).

**Calibration error and log loss against main.** Two different numbers,
both honestly labelled:

*This run's own gate-5 pooled calibration error* (`check_gates.log`, the
number the calibration gate itself is judged on — every forecast at a
horizon pooled into one reliability curve, not indicator-by-indicator):
1 year `0.1142` (3754 forecasts, 9 populated bins, ~260 independent
observations, reliability curve monotone); 5 year `0.1481` (3274 forecasts,
10 bins, ~32 independent observations, 6 reversals beyond noise); 10 year
`0.1240` (2674 forecasts, 9 bins, ~22 independent observations, 2 reversals
beyond noise). Main's equivalent pooled figures are not stored in any
artifact this report reads (only per-indicator calibration is captured in
`compare.json`/`baselines/main.json`), so they are not quoted here to avoid
retyping a number this report cannot verify against main's own log.

*Derived* (not quoted — computed here, plainly, from `compare.json`'s
per-indicator `expected_calibration_error` and `logarithmic_loss` fields,
simple unweighted mean over the 10 indicators at each horizon):

```
                     calibration error (mean of 10)         log loss (mean of 10)
horizon   main        this run      difference       main        this run      difference
 1 year   0.159923    0.167425      +0.007502        0.594038    0.577630      -0.016408
 5 year   0.250160    0.258478      +0.008318        0.758704    0.755013      -0.003691
10 year   0.281918    0.284452      +0.002534        0.692559    0.709220      +0.016661
```

By this derived measure, one-year calibration error rose slightly rather
than fell (see "Prediction versus outcome" below); log loss fell slightly
at one and five years and rose slightly at ten.

**Lambda2 (second eigenvalue modulus) and the information horizon.**
Measured on this run: `0.9831`, half-life 41 months, information horizon 60
months (`check_gates.log`, gate 2 and gate 3). This arm does not touch model
fitting, so this is expected to be, and is, the same as main's own recorded
value (`docs/TECHNICAL_DEBT.md`, D1: "none (shipped) | 0.983 | 41 months").
Not affected by this change.

**Model refits: not cache hits.** `climatology_blend_model_weight` is a new
`RunSettings` field, and its arm-default (0.5) is not the value the omission
map treats as reproducing prior behaviour (1.0), so it is included in
`configuration_hash()`'s payload. This run's `configuration_hash` is
`43ab429af4c39560` against main's `ad7fcc1affd0746a` (`paired.json`,
`compare.json`) — a different hash, so every one of this run's fits was
computed from scratch into this worktree's own cache (35 model files under
the new hash in `.cache/models/`) rather than read back from the models main
had already cached. Chosen deliberately over the omission-map route, because
the arm's whole point is that its number differs from main's, and the two
configurations should not be able to claim one identity.

## Verdict under the pre-registered rule

Family size 6 (A1-A6), Bonferroni level `1 - 0.10/6 = 98.33%`, from
`proving/experiments/0002-research-slate-2026-09/experiment.json`.

- **PROMISING?** Requires the one-year paired 90% interval entirely above
  zero. `[-0.06965666649548773, +0.029634503731571022]` — lower bound is
  negative. **No.**
- **CONFIRMED_IN_SAMPLE?** Requires the one-year paired 98.33% interval
  entirely above zero. `[-0.08950485591771964, +0.05432523623681685]` —
  lower bound is negative (and the 90% interval already failed, so this
  cannot pass either). **No.**
- **HARMFUL?** Requires the paired 90% interval entirely below -0.02 at ANY
  horizon. One year `[-0.06966, +0.02963]` — upper bound is positive, not
  entirely below -0.02. Five year `[-0.05152, +0.17425]` — same. Ten year
  `[+0.12042, +0.33097]` — entirely positive. **No, at every horizon.**
- **Verdict: none.** The one-year 90% interval spans zero. Exactly what
  `stated_in_advance` called the likeliest outcome for any single arm at
  n ~ 31.5 independent one-year observations.

## Prediction versus outcome

The pre-registration (A6's entry) predicted: "One-year calibration error
falls; the one-year paired skill difference is small, and its sign is not
predicted; the ten-year difference is positive, since pulling toward
climatology helps wherever skill is negative."

- **One-year skill difference: small, sign not predicted.** Matches:
  `-0.0209`, small relative to the interval width (~0.10), sign negative —
  within what was explicitly left unpredicted.
- **Ten-year difference positive.** Matches strongly: `+0.2779`, and both
  the 90% and 98.33% intervals lie entirely above zero — the single clearest
  confirmed prediction in this arm's entry, consistent with the mechanism
  named (pulling a hugely negative ten-year skill, main's `-0.3528`, toward
  climatology, `+0.0` by construction, helps a lot when the model is that
  wrong).
- **One-year calibration error falls.** Does **not** match, on the only
  measure available: the derived simple mean across indicators rose by
  `+0.0075` (0.159923 to 0.167425). This is the one clearly wrong prediction
  in the entry, and it is reported as such rather than smoothed over. It may
  be an artefact of the plain unweighted mean used here (the gate's own
  pooled one-year calibration statistic, `0.1142`, has no main-run
  equivalent captured anywhere this report can read to check against) — but
  on the number actually available, the prediction did not hold.

## Anything surprising, and anything I could not do

Surprising, in order:

1. The corrected diagnosis was itself surprising after the first stop: the
   benchmark is well-defined at the live edge, decades of history deep, and
   the pipeline already has a working answer to exactly this problem
   (`submit()`'s `latest_climatology`) that this arm's first pass did not
   look for before stopping.
2. `climatology_carried_forward` is true on **all 30 of today's forecasts**
   (`climatology_carry_forward_forecast_record.json`) — not a rare edge
   case at the live edge but the *only* thing that ever happens there, for
   every indicator, at every horizon, every single day this pipeline is run.
   `forecast_now`'s blended probability depends on the carry-forward path
   unconditionally, by construction of how current the benchmark's own
   source data is relative to "today."
3. The ten-year robustness gate flipping to PASS was not predicted by A6's
   entry (which discusses ten-year skill, not the robustness sub-period
   gate specifically) but follows the same mechanism: pulling an
   inconsistent-by-sub-period model number toward a constant benchmark
   tends to make the sign of each sub-period's contribution more uniform.

Could not do: compare this run's pooled one-year (etc.) calibration error
against main's pooled figure directly, because main's pooled calibration
number is not stored in any committed artifact this report is permitted to
read (`baselines/main.json` and `compare.json` both carry only per-indicator
calibration) — reported as a derived, clearly-labelled substitute instead of
retyping a number that was not actually available to quote.
