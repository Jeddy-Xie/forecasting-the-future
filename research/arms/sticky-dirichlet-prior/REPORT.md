# A1 — sticky-dirichlet-prior

Research arm A1 of `proving/experiments/0002-research-slate-2026-09/experiment.json`.
Branch `research/sticky-dirichlet-prior`, commit `7ca7b93`. Judged against main at
`ad7fcc1affd0746a` (the post-ADR-0009 reference run, per amendment 1).

## What changed

- `src/economic_regime_forecasting/models/gaussian_hidden_markov_model.py`
  - `derive_sticky_dirichlet_prior(state_count, prior_mean_visit_months, prior_row_strength)`
    computes `beta = M / (D * (K - 1))`, `kappa = M - K * beta`, returning `(0.0, 0.0)` for a
    one-state chain or zero row strength.
  - `_dirichlet_posterior_mean_transition_matrix(transition_counts, beta, kappa)`: the M-step's
    transition update, `A[k,j] = (n[k,j] + beta + kappa*1{j=k}) / (n[k] + K*beta + kappa)`,
    extracted as a pure function so it is unit-tested directly against hand-built counts.
  - `_log_transition_prior_density`: the prior's log density at the current transition matrix,
    used only by the monotonicity guard (below).
  - `fit(..., transition_prior_beta=0.0, transition_prior_kappa=0.0)`: defaults reproduce the
    unregularised fit; `_run_expectation_maximisation` and `_maximisation_step` thread the two
    values through.
- `src/economic_regime_forecasting/configuration/run_settings.py`
  - `RunSettings.sticky_dirichlet_prior_mean_visit_months: float = 30.0` (D)
  - `RunSettings.sticky_dirichlet_prior_row_strength: float = 60.0` (M)
  - These defaults are this branch's own behaviour, per the brief's instruction; main does not
    carry these fields at all.
- `src/economic_regime_forecasting/models/state_selection.py` — `sweep_state_counts` derives
  `(beta, kappa)` per candidate `state_count` and passes them into `hidden_markov.fit`.
- `src/economic_regime_forecasting/backtest/state_count_on_burn_in.py` and
  `src/economic_regime_forecasting/command_line_interface.py` (`fit_regimes` gate) — both callers
  of `sweep_state_counts` now pass `settings.sticky_dirichlet_prior_mean_visit_months` and
  `settings.sticky_dirichlet_prior_row_strength` through, so the burn-in sweep and today's fit see
  the same prior as every walk-forward refit rather than a mixture.
- `src/economic_regime_forecasting/backtest/walk_forward.py::fit_regime_model` — derives
  `(beta, kappa)` from `settings` at each refit's `state_count` and passes them to
  `hidden_markov.fit`. `command_line_interface.py::forecast_now` calls this same function
  directly, so it is covered by the same change, not a separate one.
- Tests (additive only): `tests/test_gaussian_hidden_markov_model.py` (11 new tests: the
  pre-registration's own D=30/M=60 worked examples at K=5 and K=6; the one-state and
  zero-row-strength edge cases; the closed-form Dirichlet posterior mean against hand-built
  counts; the required check, beta=kappa=0 reproduces the unregularised fit bit for bit, by
  array equality; a fit under the real hyperparameters has no exact-zero transition entries;
  the prior log density is exactly 0.0 with no prior; the monotonicity guard's monitored
  quantity), `tests/test_state_labelling_and_selection.py` (2 new tests: the sweep with zero row
  strength matches the sweep with no arguments at all, bit for bit; a positive prior reaches
  every candidate in the sweep), `tests/test_walk_forward_backtest.py` (2 new tests: a real
  `fit_regime_model` call with the prior differs from one without it; one with zero row strength
  reproduces a direct `hidden_markov.fit` call bit for bit).

**The fitting loop's monotonicity guard** (ADR 0007, wired in the same day this arm was
registered) now watches log likelihood plus the prior's log density — the log posterior — rather
than the likelihood alone, because a posterior-MEAN transition update is not guaranteed to raise
the likelihood by itself. With `beta = kappa = 0` the prior's log density is exactly `0.0` and the
monitored quantity is exactly the likelihood, so the guard is unchanged on every other fit in the
project. **On this arm's real run, the guard never fired**: `grep -c "fell from"
research/arms/sticky-dirichlet-prior/check_gates.log` is 0.

## Look-ahead audit

Every row of `docs/TECHNICAL_DEBT.md`'s look-ahead audit table, and whether this arm's change
touches it:

| path | status | this arm |
|---|---|---|
| Training panel assembly | clean | untouched — the prior only changes the M-step formula inside a fit already given a point-in-time panel; nothing about panel assembly changed |
| Standardisation window | clean | untouched |
| State probabilities used in forecasts | clean | untouched — filtered only, never smoothed; the prior changes the transition matrix estimate the filter uses, not which method is used |
| Model parameters at each refit | clean | untouched in kind — still refit from scratch on the point-in-time panel at each refit date; only the M-step formula inside that refit differs, and it uses no information beyond the panel already available |
| Number of regimes | clean | the burn-in sweep still chooses once, on the panel as of 1994-03-01, strictly before the first forecast date — confirmed by this run's own log: "6 regimes chosen as of 1994-03-01 on 518 months of burn-in (1950-12-01 .. 1994-01-01), runner-up 4." Every candidate in that sweep now fits *with* the prior (state_selection.py threads it through), so the choice is a legitimate corresponding one, not a mixture of regularised and unregularised candidates |
| Conditional rates | clean | untouched |
| Benchmark (climatology) | clean | untouched — the ADR 0009 fix is unrelated to this arm and applies identically |
| Outcome resolution | clean | untouched |
| Condition values feeding rate estimation | approximation (D5), unchanged | untouched |
| Every run setting | clean | `sticky_dirichlet_prior_mean_visit_months` (D=30) and `sticky_dirichlet_prior_row_strength` (M=60) are the two new settings, and both are a priori constants fixed by the pre-registration, not derived from data — the same status every other RunSettings constant already has |
| Acceptance thresholds | clean | untouched (0001 is unchanged) |
| Canonicalisation rule | clean | verified nothing downstream assumed exact transition-matrix zeros: `state_labelling.canonical_order` sorts states by the growth **emission mean** only, never touches the transition matrix; `stationary_distribution()`'s eigendecomposition is defined identically whether or not entries are exactly zero. The one thing the prior removes (exact zeros in the transition matrix) is not a quantity either of these reads |
| Indicator thresholds | weak (D12), unchanged | untouched |
| Future-perturbation invariance (`forecast audit-look-ahead`) | must pass, publication-lag-aware | **ran on this branch, exit 0**, cutoff 2000-03-01, 73 forecast dates / 7 refits, 627,617 values perturbed across 1,348 copied cache entries. Verbatim: "PASS: no forecast issued on or before 2000-03-01 changed when every observation unavailable at 2000-03-01 was perturbed." Run time 377s. This is the sharpest test for this arm specifically, because `beta` and `kappa` are derived once from D, M (pre-registered constants) and the state count `K` being fitted — nothing about the derivation reads a date, so there is no path by which it could depend on information after a cutoff |

VOID check (a), the deterministic half, **passes**: `audit-look-ahead` exit 0 on this branch (see
`look_ahead_audit.txt`). VOID check (b), the judged look-ahead review by an agent that did not
write this arm, has not been requested as part of this task and is not run here.

## Results

Quoted verbatim from `paired.json` and `compare.json` in this directory (do not re-round any of
the following).

**Primary endpoint — one-year paired difference** (`paired.json`, `horizons[0]`):
mean Brier skill score, this run minus main: baseline `0.21537738742364834`, this run
`0.22002064177351857`, difference `0.0046432543498702294`. 90% interval
`[-0.01263514317587533, 0.023163751739519112]`. 98.33% interval
`[-0.020565486326839136, 0.032099737982122185]`. 31.5 effective independent observations, 3754
rows in both, 378 forecast dates in both.

**Five-year** (`horizons[1]`): baseline `0.07276206990291953`, this run `0.06978059526686702`,
difference `-0.002981474636052514`. 90% `[-0.04295952347611769, 0.057413481922742024]`. 98.33%
`[-0.05934474280027636, 0.08741335639337745]`. 5.5 independent observations.

**Ten-year** (`horizons[2]`): baseline `-0.352769097290159`, this run `-0.16231589553680079`,
difference `0.1904532017533582`. 90% `[0.08989604285940545, 0.2319794983328589]`. 98.33%
`[0.05487677574953365, 0.591317426624322]`. 2.25 independent observations.

**Plain comparison** (`compare.txt`): `110 IDENTICAL 0 NUMERICAL 277 MOVED 0 REMOVED 0 ADDED`,
exit 1 (a MOVED-anything comparison always exits 1; that is not itself a finding). **Exactly one
categorical MOVED field: `configuration_hash`** — this arm's own identity, `7239dd930035d4f8`
against main's `ad7fcc1affd0746a`. No verdict and no failing-gate set moved at any horizon.

**Five-gate verdicts under 0001, this run** (from `check_gates.log`, gate 5):
- 1 year: SHIP BASE RATE. Failed calibration only. Mean skill +0.2200 [+0.1109, +0.3260] at 90%.
  Expected calibration error 0.1229 (main: 0.1250, computed identically below). Honesty distance
  0.4792 against the 0.05 floor (main: 0.4167) — passes comfortably, same as main.
- 5 year: SHIP BASE RATE. Failed skill, calibration, robustness. Mean skill +0.0698
  [-0.1459, +0.1753]. Calibration error 0.2054 (main: 0.1942). Honesty distance 0.1052 (main:
  0.1197) — passes, same as main.
- 10 year: SHIP BASE RATE. Failed skill, calibration, robustness, honesty. Mean skill -0.1623
  [-0.2374, -0.0087]. Calibration error 0.1364 (main: 0.1156). **Honesty distance 0.0199 against
  the 0.05 floor** (main: 0.0373) — fails by a wider margin than main, 0.0301 short of the floor
  against main's 0.0127 short.

Main's calibration-error and honesty-distance figures above are not carried as horizon-level
fields in `paired.json`/`compare.json` (only per-indicator deltas are), so they were derived by
running `evaluation.verdict.evaluate_horizon` — the exact function `check-gates` itself calls —
on main's own cached `backtest_results.parquet` (`configuration_hash ad7fcc1affd0746a`, matching
`baselines/main.json`; mean skill scores reproduced to four decimals: 0.2154/0.0728/-0.3528,
cross-checked against `baseline_mean_brier_skill_score` in `paired.json` above). This is
computing the same statistic from the same code both runs use, not retyping a number.

**Log loss**, mean of per-indicator logarithmic loss (`evaluation.verdict.compute_metrics`, same
function and same cached `backtest_results.parquet` on both sides): main 0.5940 / 0.7587 / 0.6926
at 1/5/10 years; this arm 0.5778 / 0.7533 / 0.6540. Lower at every horizon.

**Lambda2 (second eigenvalue modulus of the transition matrix), first and last refit**, computed
from the cached fitted-model files this run wrote
(`model_1994-03-01_states6_seed20260908_7239dd930035d4f8.json` and
`model_2026-03-01_states6_seed20260908_7239dd930035d4f8.json`):
- 1994-03: **0.9700192614690768** (main: 0.9777)
- 2026-03: **0.9760916058361273** (main: 0.9845)

Both transition matrices' minimum entry is strictly positive (0.0023 and 0.0014 respectively) —
no exact zeros anywhere, on the actual real-data fits, not only in the unit tests.

**Burn-in state-count sweep** (`check_gates.log`, `run_backtest`): "6 regimes chosen as of
1994-03-01 on 518 months of burn-in (1950-12-01 .. 1994-01-01), runner-up 4." Main chose the same
6, with runner-up 2 (`tests/test_honest_start_date_against_the_live_cache.py`, unchanged). The
top choice is unmoved; the runner-up moved from 2 states to 4.

**Monotonicity guard**: never fired on this run (`grep -c "fell from" check_gates.log` = 0).

**Test suite**: `poetry run pytest -m "not network"` — 500 passed, 2 skipped (pre-existing,
unrelated to this change), 2 failed. Both failures are structural, expected consequences of this
arm's design, are not touched, and are explained in the commit message and in "Anything
surprising" below. `ruff check .`, `ruff format --check .` and `mypy` are all clean.

## Verdict under the pre-registered rule

Bonferroni level for `CONFIRMED_IN_SAMPLE` is 98.33% (`1 - 0.10 / 6`, across experiment 0002's
six arms). `paired.json` carries both the 90% and 98.33% intervals at every horizon (confirmed
above), so a CONFIRMED claim could be made if the arithmetic supported it.

- **PROMISING** requires the one-year paired 90% interval entirely above zero.
  `[-0.01263514317587533, 0.023163751739519112]` includes negative values. **Not promising.**
- **CONFIRMED_IN_SAMPLE** requires the one-year paired 98.33% interval entirely above zero.
  `[-0.020565486326839136, 0.032099737982122185]` also includes negative values. **Not
  confirmed.**
- **HARMFUL** requires some horizon's 90% interval entirely below -0.02.
  12 months: `[-0.0126, +0.0232]` — no. 60 months: `[-0.0430, +0.0574]` — no. 120 months:
  `[+0.0899, +0.2320]` — no. **Not harmful.**

**Verdict: none of the above.** The one-year interval spans zero, exactly the outcome the
pre-registration itself called the likeliest result for any single arm ("an interval that spans
zero is the likeliest outcome for any single arm," given ~31.5 independent one-year observations).

## Prediction versus outcome

The pre-registration's prediction for A1: *"lambda2 falls and the information horizon shortens;
the ten-year honesty gate fails by a wider margin; one-year skill moves by less than its interval
width. Direction of the one-year effect: not predicted."*

- **Lambda2 falls**: confirmed at both ends measured, 0.9777 → 0.9700 (1994-03) and
  0.9845 → 0.9761 (2026-03).
- **Information horizon shortens**: consistent with the honesty-distance figures above — at every
  horizon the arm's projected distribution is farther from main's own at one year (0.4792 vs
  0.4167, more information retained short-run) and closer to stationary at five and ten years
  (0.1052 vs 0.1197; 0.0199 vs 0.0373 — faster decay long-run), which is the shape a lower lambda2
  implies.
- **Ten-year honesty gate fails by a wider margin**: confirmed. Main is 0.0127 short of the 0.05
  floor; this arm is 0.0301 short — more than twice the shortfall.
- **One-year skill moves by less than its interval width**: confirmed. The difference is
  `+0.00464`; the 90% interval width is `0.0358` (`0.023164 - (-0.012635)`), about 7.7 times
  larger than the point difference.
- **Direction of the one-year effect, not predicted**: it came out positive, one of the two
  possible directions the pre-registration deliberately declined to call.

One thing the pre-registration did not predict and this run found: **the ten-year paired skill
difference is large and positive**, `+0.1905` with a 90% interval `[+0.0899, +0.2320]` entirely
above zero. Ten-year is a secondary endpoint and a harm guard, not the primary endpoint, and the
decision rule's PROMISING/CONFIRMED/HARMFUL classifications are defined only on the one-year
interval — so this does not change the verdict above. But as a secondary result it is the
opposite direction from "fails by a wider margin" read narrowly as skill: the *honesty gate*
(a calibration-style check on whether the model still carries information) fails more badly, while
the *raw ten-year Brier skill* is substantially less negative than main's. Both are consistent
with the same underlying mechanism — the model decays toward its own stationary distribution
faster, and the stationary distribution it decays toward happens to score better against the
climatology benchmark at ten years than main's slower, more-persistent chain's late trajectory
did. This is exactly the kind of secondary, per-metric nuance the pre-registration's metric list
anticipated by keeping calibration error, honesty distance and skill as separate reported
quantities rather than one number.

## Anything surprising, and anything not done

- **The ten-year skill improvement was not predicted and is the most notable secondary number in
  this run.** It is large relative to every other horizon and every other arm's stated
  expectation in `stated_in_advance`, and it is worth the project owner's attention even though it
  does not change this arm's verdict.
- **The monotonicity guard never fired**, despite the note in this arm's brief warning that it
  might, given a posterior-MEAN update is not guaranteed to raise the likelihood. Adapting the
  monitored quantity to the log posterior (see "What changed") was done pre-emptively and was not
  needed on this data — worth recording so a future reader does not assume it was untested.
- **Two pre-existing tests fail**, both left untouched (tests are additive only) because there is
  no way to make them pass without either changing behaviour this arm's own brief requires or
  editing a test:
  - `tests/test_configuration_hash_compatibility.py::test_the_shipped_configuration_hashes_to_the_recorded_digest`
    reconstructs main's shipped `RunSettings` by name (`select_state_count_on_a_burn_in_window=False,
    start_walk_forward_when_every_input_is_point_in_time=False`) and asserts its
    `configuration_hash()` equals a literal on the record. Any new `RunSettings` field changes
    that hash unless it is added to `SETTINGS_OMITTED_FROM_THE_HASH_WHEN_THEY_HOLD_THE_SHIPPED_VALUE`
    — and two OTHER pre-existing tests in the same file pin that map's membership to exactly the
    two existing boolean switches, and require every mapped value to be a `bool`. There is no
    value the two new float fields could take that avoids this without editing one of those three
    tests, so implementing this arm's own non-negotiable ("a clearly named RunSettings field")
    unavoidably breaks this one. It fails: `194f98a9f85f0df6 != 9f95b12dba40d138`.
  - `tests/test_honest_start_date_against_the_live_cache.py::test_the_burn_in_choice_reproduces_the_measured_sweep_at_1994_03`
    asserts `DEFAULT_RUN_SETTINGS`'s burn-in sweep on the real 1950-1994 panel picks 6 states with
    runner-up 2. `DEFAULT_RUN_SETTINGS` now carries this arm's prior by design (the brief:
    "default ON YOUR BRANCH is the arm's behaviour"), and the burn-in sweep choosing differently
    under that prior is the exact mechanism `research_arm.sh run`'s `check-gates` step depends on
    to make this arm's result different from main's when run with no special flags. It still picks
    6 states; the runner-up moved to 4 (`assert 4 == 2` fails) — itself the finding reported above,
    not a defect.

  Both are reported in the commit message (`7ca7b93`) at the time they were found, not discovered
  after the fact.
- **What was not done**: VOID check (b), the judged look-ahead review by an agent that did not
  write this arm, is outside what this task asked me to run. A0's own pass/fail was not
  independently re-verified here; this report's verdict is conditional on A0 passing, per the
  pre-registration.
