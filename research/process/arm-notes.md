# Arm-specific notes — appended to each arm's brief as {ARM_SPECIFIC_NOTES}

These are code pointers, found by the orchestrator on 2026-09-15, so each arm spends its budget on
the idea rather than rediscovering the codebase. They are pointers, not the specification: the
pre-registration is the specification. Verify each pointer by opening the file; line numbers move.

---

## A0-aa-control
You change NO code. Run setup and run, then write the report. This arm exists to prove the
measuring instrument, and the pre-registration fixes its only acceptable outcome in advance:
- the paired difference is exactly 0.0 with interval [0.0, 0.0] at all three horizons;
- the plain comparison reports zero MOVED fields.
If EITHER fails, say so plainly in the first line of your report, and in your reply. Per the
pre-registration, that voids every other arm, so it is the most important number in the slate. Do not
explain a difference away; report it with the rows that moved.

## A1-sticky-dirichlet-prior
- The maximisation step lives in `src/economic_regime_forecasting/models/gaussian_hidden_markov_model.py`,
  inside `_run_expectation_maximisation` (called from `fit`). The transition update is currently
  expected counts divided by row totals. That is the one line the prior changes.
- `fit()` is called from three places, and ALL three must pass the prior through, or the arm tests a
  mixture: `models/state_selection.py::sweep_state_counts` (the burn-in and today's sweeps),
  `backtest/walk_forward.py::fit_regime_model` (every refit), and whatever `forecast_now` uses.
- Derive beta and kappa from D = 30 and M = 60 at the state count being fitted, as the
  pre-registration's derivation says. Put D and M on RunSettings. beta and kappa are derived, never stored.
- `required_check`: beta = kappa = 0 reproduces the current fit BIT FOR BIT. Test it with
  array equality, not a tolerance.
- The posterior mean has no zeros, so `_safe_log` of the transition matrix is exercised less. Check
  that nothing downstream assumed exact zeros (the state labelling, the stationary distribution).
- Report lambda2 at the first and last refit, beside main's (0.9777 at 1994-03, 0.9845 at 2026-03).
- **The fitting loop has a monotonicity guard.** It raises when the log-likelihood falls between
  iterations by more than an allowance (1e-3 relative, ADR 0007; wired into the loop on 2026-09-15
  after the look-ahead audit found it had never been called). A posterior-MEAN transition update is not the maximiser of the likelihood's
  auxiliary function, so expectation maximisation with your prior is NOT guaranteed to be monotone
  in the likelihood, and the guard may fire. If the guard fires on your
  fits, that is a finding. Adapt the monitored quantity for YOUR fit where the maths says so (for
  example the log-posterior rather than the log-likelihood), document it, and report both. Do NOT
  widen the shared allowance: every other fit in the project depends on it, and widening it to make
  your arm converge is tuning, which the pre-registration forbids.

## A2-quadrant-structure-levels
- Initialisation lives in `gaussian_hidden_markov_model.py`: `_initial_model` and
  `_seed_means_by_furthest_point`. Replace the furthest-point seeding of MEANS with the four quadrant
  centroids; keep whatever per-restart perturbation already exists.
- The expanding median must be computed point in time over the panel being fitted, month by month,
  using only months up to each one. It must not be a single median of the whole panel. That would be
  a small leak inside each fit and it breaks the rule that standardisation expands.
- The state count used for FORECASTING is fixed at 4. The burn-in sweep in
  `backtest/state_count_on_burn_in.py` still runs, because it supplies the regimes-exist evidence to
  0001's first gate. Only its choice is overridden. `forecast_now` and today's fit also use K = 4.
- `models/state_labelling.py::canonicalise` sorts states by growth mean. Check that it still gives
  stable labels for four quadrant-initialised states across refits.

## A3-quadrant-structure-surprises
- The observation vector is built in `src/economic_regime_forecasting/features/observation_matrix.py`,
  with transforms in `features/transforms.py`. `features/` may import only `configuration`.
- A surprise at month s uses AR(1) coefficients estimated by ordinary least squares on months STRICTLY
  BEFORE s. That is a recursive fit, one per month. Vectorise it with running sums if it is slow, but
  do not replace it with one full-panel regression. That is precisely the leak the pre-registration's
  leakage_note warns about.
- Decide, and state in the report, whether surprises are computed before or after the expanding
  standardisation. The pre-registration does not pin it. Pick whichever keeps everything point in
  time, and justify it in one line.
- The first 60 months of each panel have no surprise and drop out. Check that the burn-in panel is
  still long enough (main's is 518 months at 1994-03), and that the first forecast date is unchanged.
  If it moves, report the new date; do not force it back.
- K = 4 and quadrant initialisation as in A2. The boundaries are zero, so there is no median.

## A4-two-timescale-chains
- This is the largest arm. Build a new model class in `src/economic_regime_forecasting/models/` that
  the walk-forward and the forecast composition can use WITHOUT modification. Find every attribute and
  method they call on `GaussianHiddenMarkovModel`: at least `state_count`, `transition_matrix`,
  `filtered_state_probabilities`, `second_largest_eigenvalue_modulus`, `stationary_distribution`,
  `project_state_distribution`, `expected_state_durations`, `to_dictionary` / `from_dictionary` (the
  fitted-model cache), and `fit_report`. Grep for them rather than trusting this list.
- The product transition matrix is `numpy.kron(A_growth, A_levels)`. The joint emission log-density is
  the SUM of the growth block's and the levels block's log-densities. Filtering is the existing
  forward pass over K_g * K_l states. E-step: joint posteriors over the product space. M-step:
  marginalise the expected transition counts and the state occupancies to each chain.
- Choose K_g on the growth column alone, and K_l on the inflation and rates columns alone, each by the
  existing burn-in selection rule over candidates 1-4 (`models/state_selection.py::sweep_state_counts`).
  The orchestrator's precursor measured K = 4 and K = 4 at 1994-03, so expect up to 16 product
  states; conditional rates per product state will be thin, and the existing shrinkage handles that.
- Test that with K_g = 1 the model reduces EXACTLY to a single-chain model on the levels block, and
  vice versa. That is the cheapest proof the product construction is right.
- Canonical labelling must make product states stable across refits. Sort each chain's states
  independently (growth by growth mean, levels by inflation mean) BEFORE forming the product.
- **The fitting loop has a monotonicity guard.** It raises when the log-likelihood falls between
  iterations by more than an allowance (1e-3 relative, ADR 0007; wired into the loop on 2026-09-15
  after the look-ahead audit found it had never been called). Your product-space fit ties parameters across chains, so check that each
  maximisation step still increases the joint likelihood; if it does not, the guard will say so. If the guard fires on your
  fits, that is a finding. Adapt the monitored quantity for YOUR fit where the maths says so (for
  example the log-posterior rather than the log-likelihood), document it, and report both. Do NOT
  widen the shared allowance: every other fit in the project depends on it, and widening it to make
  your arm converge is tuning, which the pre-registration forbids.

## A5-direct-horizon-rates
- Rates are estimated in `models/indicator_forecast.py::estimate_conditional_rates` and composed by
  `compose_point_in_time` / `compose_any_time_within_horizon` / `forecast_indicator`. They are wired up
  in `backtest/walk_forward.py::fit_regime_model`.
- `IndicatorHistory.outcomes_by_horizon[h]` (in `walk_forward.py`) holds each forecast date's resolved
  outcome, indexed by forecast date s. The outcome for s is KNOWN at s + h months, plus the resolution
  series' publication lag, and it may be used only at refit dates on or after that.
  `condition_available_at` shows the existing pattern for the lag; the recession series' lag is 400
  days. Getting this wrong is a look-ahead of up to ten years, so test the boundary explicitly: a
  refit date one day before availability must exclude the row, and one on the day must include it.
- gamma for historical months comes from the model fitted at the refit date, filtered (never smoothed),
  exactly as main's existing rates use it.
- Keep the Beta shrinkage at strength 10 toward the pooled resolved rate. That is main's
  `conditional_rate_shrinkage_strength`, unchanged.
- **The outcome-timing rule already exists; REUSE it.** On 2026-09-15 the look-ahead audit found that
  main's own climatology benchmark admitted an outcome h months after its forecast date, before its
  last observation was published. The fix, in `walk_forward.py::_expanding_climatology`, is the
  project's single definition of 'this outcome was knowable at t': label (s + h months) plus
  `publication_lag_days`, on or before t. Your direct rates need EXACTLY that boundary. Call or share
  that logic rather than writing a second version; two implementations of one boundary drift, and
  the reviewer is told to treat a second one as a finding.

## A6-fixed-climatology-blend
- The model is unchanged, so after setup your fitted models should all be cache hits: the model cache
  key covers the configuration hash. Adding the blend setting to `RunSettings` WILL change the hash
  and force refits unless it goes into the omission map. Either path is fine. Just report which, and
  whether the fits were hits.
- The blend must apply wherever a probability is issued: every walk-forward row
  (`backtest/walk_forward.py::run_walk_forward`, where `predicted_probability` is set) AND today's
  forecast (`forecast_now` in `command_line_interface.py`). The walk-forward row already carries
  `climatology_probability`, the expanding climatology, which is point in time.
- If `climatology_probability` is ever NaN at a forecast date, a blend would silently produce NaN or
  something worse. Check whether that ever happens at a date from 1994-03 onward. If it does, stop and
  report it; do not paper over it. "No silent fallbacks" is a project rule.
- Keep the unblended model probability in the frame too, under its own column, so the report can show
  both.
- The `climatology_probability` you blend with became genuinely point in time only on 2026-09-15.
  Before that fix it let each outcome in 32-400 days early (docs/adr/0009). You inherit the fixed
  version by branching from main. Confirm in your report that your branch contains the fix commit;
  if it does not, your blend imports a leak.
