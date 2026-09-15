# A6 — fixed-climatology-blend: STOPPED before implementation

**Status: blocked.** No code was changed on this branch. The pre-run check the
brief requires (`climatology_probability` must never be `NaN` at a forecast
date from 1994-03 onward, or the arm must stop and report rather than paper
over it) fails. Per the brief: *"If `climatology_probability` is ever NaN at a
forecast date, a blend would silently produce NaN or something worse... If it
does, stop and report it; do not paper over it."* It does. This report is that
stop, at the point the brief specifies.

## Point-in-time climatology, confirmed

Branch `research/fixed-climatology-blend` is at commit `2e025b7`, and
`git merge-base --is-ancestor 628a77d HEAD` exits 0: commit `628a77d`
(`fix(benchmark): an outcome counts only once it was published, and main
passes the audit`, ADR 0009) is an ancestor of `HEAD`. The
`climatology_probability` this arm would blend with is genuinely point in
time — an outcome enters the expanding average at date t only once the value
it rests on was published by t — not the pre-fix version that let each
outcome in 32-400 days early. Confirmed as the brief asks.

## The blocking finding

Checked whether `climatology_probability` is ever `NaN` at a forecast date
from 1994-03 onward, using main's own committed baseline
(`baselines/main.forecasts.parquet`, unmodified, read with
`PYTHONPATH=<worktree>/src` pointed at this worktree's own code — isolation
verified, `economic_regime_forecasting.__file__` resolves inside this
worktree).

It is NaN on 39 of 11,730 rows, and every one of them is at the two most
recent forecast dates in the file:

- **2026-09-01 — today's forecast.** This is the maximum `forecast_date` in
  the file, i.e. the row set `forecast_now` produces. **All 30 rows are
  affected: every one of the 10 indicators, at all 3 horizons.**
  `predicted_probability` is present and finite on every one of these 30
  rows; `climatology_probability` is `NaN` on every one of them.
- **2026-08-01.** 9 more rows: 3 indicators
  (`consumer_price_inflation_above_five_percent_within_horizon`,
  `consumer_price_inflation_above_three_percent_at_horizon`,
  `industrial_production_growth_above_two_percent_at_horizon`) at all 3
  horizons.

`realised_outcome` is also `NaN` on all 39 rows (nothing to compare with the
brief's caveat: these are honestly unresolved observations, not a
resolution bug), but that is beside the point for the blend. The blend
consumes `climatology_probability`, not `realised_outcome`, and it is asked
to produce a number for **today's forecast** — the one place a person
actually reads a probability off this pipeline live — for every single
indicator.

```
p = 0.5 * p_model + 0.5 * p_climatology
```

At `forecast_date = 2026-09-01`, `p_climatology` is `NaN` for all ten
indicators at all three horizons, so `p` is `NaN` for all ten indicators at
all three horizons on `forecast_now`'s output — the whole current forecast,
gone. Two ways to make that not-NaN both fail the project's rules:

1. **Fall back to the model probability alone when `climatology_probability`
   is NaN.** This is exactly the silent fallback the brief names and
   `CLAUDE.md` forbids ("No silent fallbacks... A fallback that is taken
   deliberately is recorded in the manifest" — this would be undeclared,
   indistinguishable downstream from a real 50/50 blend, and would make
   today's forecast quietly stop being the arm's hypothesis for every
   indicator, every month, forever, since the live edge is NaN by
   construction — see below).
2. **Raise loudly instead.** Consistent with "a failed fetch... raises with a
   message saying what to do next," but it converts every `check-gates` run
   and every `forecast-now` invocation into a hard failure on this branch,
   because the live edge is reached on every run, not on some unlucky
   historical date. That is not an arm that can be run once and scored; it is
   an arm that cannot complete step 4 (`research_arm.sh run`) at all. This is
   also not what the pre-registration's hypothesis or prediction describe —
   nothing in `A6-fixed-climatology-blend`'s entry in
   `proving/experiments/0002-research-slate-2026-09/experiment.json` names
   this as expected behaviour to design around.

Why this happens, mechanically: `climatology_probability` in
`backtest/walk_forward.py::run_walk_forward` is looked up by exact date
(`_lookup`, a `pandas.Series.get(stamp, np.nan)`) against
`history.climatology_by_horizon[horizon]`, an expanding average built in
`prepare_indicator_history` / `_expanding_climatology` over
`indicator_outcomes.resolve(...).outcomes`, the full history of an
indicator's own resolution series. `_expanding_climatology` requires at least
one *prior* forecast date's outcome to have resolved **and been published**
by the row's own `forecast_date` before it will report a number
(`resolved_count > 0`); at the live edge, no prior row's deciding value has
both a complete `horizon`-months-ahead window and a publication date on or
before "now," so no prior row anchors the average and the lookup returns the
`np.nan` default. This is not a bug in `climatology_probability` itself — it
is behaving exactly as ADR 0009 and the "no look-ahead" rule require, by
correctly refusing to manufacture a number it does not have. It is a real
property of the pipeline at the live edge, present on main today, unrelated
to anything this arm would have changed. This arm's specific failure is that
its hypothesis needs a `climatology_probability` at exactly the dates where
none exists.

## What was and was not done

- **Not implemented:** no `RunSettings` field, no blend logic in
  `backtest/walk_forward.py` or `command_line_interface.py::forecast_now`, no
  tests, no cache/model changes.
- **Not run:** `scripts/research_arm.sh run fixed-climatology-blend` was not
  invoked. There is no gate output, no `compare.json`, no `paired.json`, no
  `look_ahead_audit.txt` for this arm. Running the five gates on an
  unmodified branch would only reproduce main's own numbers (as the A0
  control is separately doing) and would not test the A6 hypothesis; it was
  skipped rather than used to manufacture a report that looks more complete
  than the work is.
- **Model refit status:** not applicable — no configuration changed, so no
  fits were attempted, cache-hit or otherwise.

## Look-ahead audit table (`docs/TECHNICAL_DEBT.md`), for this change

No code changed on this branch, so every row is exactly main's, unmodified.
Listed for completeness, as the brief asks, with the row this arm's diagnosis
actually touched called out.

| path | status on this arm |
|---|---|
| Training panel assembly | unchanged from main — clean |
| Standardisation window | unchanged from main — clean |
| State probabilities used in forecasts | unchanged from main — clean |
| Model parameters at each refit | unchanged from main — clean |
| Number of regimes | unchanged from main — clean |
| Conditional rates | unchanged from main — clean |
| **Benchmark (climatology)** | unchanged from main — clean and point-in-time since 628a77d (confirmed above). This is the row the blocking finding sits next to: the benchmark is correctly refusing to report a value at the live edge rather than leaking one, and this arm's blend has no way to consume "correctly absent" without either faking a value or crashing. Not a look-ahead defect; a real absence this arm's design does not handle. |
| Outcome resolution | unchanged from main — clean by design |
| Condition values feeding rate estimation | unchanged from main — approximation, D5 |
| Every run setting | unchanged from main — clean |
| Acceptance thresholds | untouched — `proving/` was not edited |
| Canonicalisation rule | unchanged from main — clean |
| Indicator thresholds | unchanged from main — weak, D12, untouched |
| Future-perturbation invariance (`forecast audit-look-ahead`) | not run on this branch — no code changed to audit, and running it would only re-confirm main's own already-recorded pass. Skipped for the reason given above under "What was and was not done." |

## Results

None. No run was performed, so there is no `paired.json` or `compare.json`
for this arm to quote from. No one-year, five-year or ten-year paired
difference exists to report; no calibration error, log loss or lambda2
figures were produced.

## Verdict under the pre-registered rule

**None** — not PROMISING, not CONFIRMED_IN_SAMPLE, not HARMFUL. The decision
rule in `proving/experiments/0002-research-slate-2026-09/experiment.json`
computes all three from a paired 90%/98.33% interval that requires a
completed run; none exists. This is a stop, not a negative result: HARMFUL
specifically requires an observed paired interval entirely below -0.02 at
some horizon, and none was computed.

## Prediction versus outcome

The pre-registration predicted: "One-year calibration error falls; the
one-year paired skill difference is small, and its sign is not predicted; the
ten-year difference is positive." None of that could be tested. The
prediction implicitly assumes a blend can be formed at every forecast date
the model issues one, including today's; that assumption fails at the live
edge on main as it stands, before any A6-specific code was written. This is
also a comment on `why_fixed_and_not_fitted` and the "most likely to reduce
the largest errors, and the least likely to be harmful" framing in
`stated_in_advance`: those predictions were about the blend's effect where it
can be computed, and did not anticipate that the benchmark it blends with is
sometimes, by design, not yet computable.

## Anything surprising, and anything I could not do

Surprising: `climatology_probability` is `NaN` for **every single indicator**
in main's own already-committed `current_forecasts` row
(`forecast_date = 2026-09-01`), not an occasional gap. This means main today,
right now, cannot report a climatology benchmark for its own newest month at
any horizon — a fact `docs/TECHNICAL_DEBT.md`'s look-ahead audit table does
not currently record (it records the benchmark as "clean since 2026-09-15,"
which is about correctness, not about completeness at the live edge — both
things are true at once: the benchmark is honest, and it is absent exactly
where an arm like this one needs it). That gap is not something I fixed,
edited, or worked around; `docs/TECHNICAL_DEBT.md` is Jeddy's list to update,
so I am naming it here rather than adding an entry to it.

Could not do: implement or run the blend at all, for the reason above. Did
not attempt a partial or historical-only version of the blend (e.g. applying
it only where `climatology_probability` happens to be defined) because that
would be exactly the kind of undeclared, inconsistent behaviour "no silent
fallbacks" rules out, and because it would silently change what "today's
forecast" means for ten indicators without saying so.
