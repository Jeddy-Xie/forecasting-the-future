# 0008. Eliminating two look-ahead paths, and what honesty cost

Date: 2026-09-09 · Status: accepted

## Context and problem

The look-ahead audit in `docs/TECHNICAL_DEBT.md` found two paths by which
information from the whole sample reached a walk-forward decision. Both are now
closed, and the pipeline default is the configuration with both closed. This
record says what was measured, what the fixes cost, and what was deliberately not
done.

### Path one — the number of regimes (debt entry D2)

`forecast fit-regimes` swept one to six states on the panel as it stands **today**
and wrote the winner to `selected_model.json`. `forecast backtest` read
`state_count` off that artifact and used it for all 55 refits, including the one
that issued forecasts for 1972. Five regimes was chosen using data through 2026
and applied to a forecast made in 1971.

**Scope, verified rather than assumed.** `run_backtest` read the full-sample
artifact for exactly one thing, `model.state_count`. No emission mean, covariance
or transition probability crossed over. One integer leaked, and nothing else.

### Path two — the vintage fallback in the model's own inputs

`data/vintage.py` falls back to `PUBLICATION_LAG_FALLBACK` — final revised values
with correct publication timing — when the archive has no vintage carrying at
least 240 observations. Measured over the cached vintage requests:

| series | usable (n ≥ 240) | first usable | fallback dates | fallback range |
|---|---:|---|---:|---|
| CPIAUCSL | 393 | 1994-03-01 | 268 | 1970-12 .. 1994-02 |
| INDPRO | 649 | 1970-12-01 | 12 | 1971-12 .. 1972-11 |

The shipped walk-forward ran 1971-12-01 .. 2026-09-01, 658 forecast dates.
**267 of those 658 (41%) fitted the model on revised consumer price index
values.** The audit table had called training panel assembly "clean"; it was
understated, and the row now says so.

*(A correction to `measured-facts.md`: that file quotes 268 of 658. The census
figure 268 counts CPIAUCSL's whole fallback range from 1970-12, which begins one
month before the walk-forward does. Within the shipped schedule the count is 267 —
every month from 1971-12 to 1994-02 inclusive — and 267 is what
`compare-variants` measured on all four cells. INDPRO's twelve fallback months
fall inside CPI's range and add nothing.)*

### "Fetch the archival vintages back to 1971" is not available. Proven, not assumed.

Direct probes of the keyless archival endpoint on 2026-09-09:

    alfredgraph.csv?id=CPIAUCSL&vintage_date=1994-03-01  -> HTTP 200, 565 obs, 1947-01 .. 1994-01
    alfredgraph.csv?id=CPIAUCSL&vintage_date=1994-02-01  -> HTTP 200,  19 obs, 1992-06 .. 1993-12
    alfredgraph.csv?id=CPIAUCSL&vintage_date=1980-01-01  -> HTTP 200,  19 obs, 1978-05 .. 1979-11
    ...&vintage_date=1980-01-01&cosd=1947-01-01&coed=1979-12-01 -> still 19 obs

The pre-1994 responses **are** genuine vintages — the 1980-01-01 values (193.4 ..
227.7) are on the 1967=100 base, not today's 1982-84=100 base — but the archive
holds only a rolling ~19-observation window for them. It is truncated, not
missing, and nineteen observations cannot support a 240-month burn-in. Widening
the date range does not widen the response.

**A trap worth writing down.** `fredgraph.csv`, as opposed to `alfredgraph.csv`,
silently *ignores* `vintage_date` and returns 956 rows of the current series. Any
code that fell back to that URL would manufacture look-ahead while appearing to
succeed.

## Decision

### Two switches on `RunSettings`, defaulting to honest

```python
select_state_count_on_a_burn_in_window: bool = True
start_walk_forward_when_every_input_is_point_in_time: bool = True
```

Booleans, not enums: each has exactly two states and there is no third in
prospect.

### The shipped digest is preserved, by one stated rule

`configuration_hash()` digests every `RunSettings` field except `cache`, and that
digest is written on every result row, into every fitted-model cache filename,
into `submission/manifest.json` and into thirty register entries. Adding two
fields naively would change the digest of the *shipped* configuration, which would
falsify the record: the same numbers would suddenly claim a different provenance.

So `SETTINGS_OMITTED_FROM_THE_HASH_WHEN_THEY_HOLD_THE_SHIPPED_VALUE` maps each new
field to the value that reproduces the behaviour in force before it existed, and
`configuration_hash()` omits a field holding exactly that value. The digest
answers one question — *would two runs produce the same numbers?* — and a field
set to the old behaviour changes no number, so it must not change the digest. The
map is append-only and every entry is permanent; that constraint is in its
docstring.

The four cells hash to `9f95b12dba40d138` (shipped), `e141ea4d70f7ce4a`
(state-count fix alone), `14a5a2ee596e28d6` (start fix alone) and
`ad7fcc1affd0746a` (both, the new default).

**What the omission rule actually buys is narrower than "it protects the shipped
record."** `submission/` and `forecasts/register.jsonl` are protected by this
unit's non-goals and, from now on, by the shipping guard below — not by the hash.
What preserving the digest buys is concrete and smaller: the shipped cell of the
comparison reuses 56 cached fits instead of spending ~13 minutes recomputing them,
and `gate_four_backtest`'s "a single configuration produced the whole run" check
keeps meaning something.

**The shipped cell reuses those 56 cached fits and never refits.** That matters
for reading `determinism-finding.md`, which measured a ~1e-13 difference between a
fresh fit and the 2026-09-08 cached artifacts, caused by a changed numpy/BLAS
build. That finding is real and still forbids asserting byte-identity for any cell
that refits. Its original conclusion — "the shipped cell must be re-run" — was
written before the digest-preserving rule existed and has been **superseded, not
ignored**; a correction is appended to that file. Because the shipped cell
performs no fit at all, byte-identity there is achievable, and it was verified
exactly (`check_exact=True`; the default tolerance passes a 1e-13 difference
silently, which was confirmed by negative control on this data).

### Fix A — burn-in state-count selection, in `backtest/`

`backtest/state_count_on_burn_in.py` sweeps the state count once, on the panel as
it stood at the first forecast date, and asserts `panel_end < chosen_as_of`. It
lives in `backtest/` because selecting on a burn-in window needs a point-in-time
panel, which is `data`, and the declared layering forbids `models` importing
`data`. The arithmetic that decides whether regimes exist stays in
`models/state_selection.py` as `regimes_exist_from_sweep_table`, lifted verbatim
from the command line interface so both paths ask that question with one
implementation. One thing it did not lift was the sad path: a sweep table with no
single-regime row — reachable through any `hidden_state_counts_to_search` that
omits 1, which nothing enforces — indexed an empty frame and raised a bare
`IndexError`, where the two hand-written siblings on `StateCountSweep` return
`False`. It now returns `False` with an evidence sentence naming the setting to
change, so a gate that cannot be answered reads as not passed rather than as a
traceback. The evidence sentence on the answerable path is unchanged, byte for
byte.

`selected_model.json` keeps its present meaning exactly: the model fitted on the
full panel as of today. Notebook 02, notebook 04, `forecast forecast-now` and
`forecast submit` are unaffected.

### Fix B — the honest start date, computed, never hardcoded

`find_first_fully_point_in_time_date` scans **monthly** — unlike
`find_first_forecast_date`, which steps a year at a time, because panel length is
monotone in the date and fallback usage is not. Industrial production falls back
for twelve months in 1971-72 and is clean on either side, while the consumer price
index falls back continuously until 1994-02, so the answer is the month after the
*last* fallback month in the range, not the first clean one.

On the live cache it returns **1994-03-01** in **1.3 seconds**, and it reads only
from cache: a date whose vintage is absent raises `BacktestError` naming
`forecast fetch-data` rather than reaching the network, because a check that
silently downloads is not a check.

1994-03-01 is never a literal in `src/`. It is the expected answer of a
computation, asserted against the live cache. If the archive backfills, the code
follows and the test fails loudly, which is the correct failure.

`run_walk_forward` makes one pre-flight call to
`assert_every_forecast_date_is_fully_point_in_time` before anything is fitted, so
a schedule that breaks the promise fails in seconds rather than fifteen minutes.
It raises the existing `LookAheadError` rather than a new exception: fitting on a
publication-lag fallback means fitting on values revised *later than the forecast
date*, which is information published in the future — exactly what that name
already means. One invariant, two places it can be violated.

The honest statement of coverage: the pre-flight protects every path that produces
a results frame, because `run_walk_forward` is the only function that builds one.
A caller reaching past it into `fit_regime_model` directly is outside the check.
An earlier draft proposed a second check inside the per-date loop and justified it
as the version no caller could bypass; **that justification was false and is
withdrawn** — both checks would have sat inside the same function over the same
dates, so the in-loop copy was dead code on every reachable input, and it was
dropped.

`Workspace.backtest_schedule` composes the two rules by construction rather than
by `max()`: the panel-length search runs first and unchanged, and the
point-in-time search takes its answer as the earliest candidate and can only move
the start later. `widest_backtest_schedule` ignores the start policy so that one
`fetch-data` serves the shipped run and all four cells — and so that the scan for
the honest start, which has to look back to 1971, is not starved by a fetch that
stopped at 1994.

## The result: the 2x2, against the unchanged decision rule

`experiment.json` was not edited and no thaw token was minted for it. Every cell
is judged by the same `evaluate_all_horizons` reading the same
`load_decision_rule()`. The only input that differs per cell is the regimes-exist
evidence, and it differs *towards* honesty: a cell that chose its state count on a
burn-in window has that sweep answer the gate, not the full-sample one it did not
use.

| variant | start | states | dates | fallback | horizon | verdict | skill | 90% interval | independent |
|---|---|---:|---:|---:|---:|---|---:|---|---:|
| shipped | 1971-12 | 5 | 658 | 267 | 1y | **SHIP MODEL** | +0.2320 | [+0.1578, +0.3011] | 53.8 |
| shipped | 1971-12 | 5 | 658 | 267 | 5y | SHIP BASE RATE | +0.1021 | [−0.0130, +0.1969] | 9.9 |
| shipped | 1971-12 | 5 | 658 | 267 | 10y | SHIP BASE RATE | −0.2205 | [−2.7437, −0.0137] | 4.5 |
| honest_state_count | 1971-12 | 2 | 658 | 267 | 1y | SHIP BASE RATE | +0.2414 | [+0.1723, +0.3050] | 53.8 |
| honest_state_count | 1971-12 | 2 | 658 | 267 | 5y | SHIP BASE RATE | +0.1147 | [+0.0248, +0.1865] | 9.9 |
| honest_state_count | 1971-12 | 2 | 658 | 267 | 10y | SHIP BASE RATE | −0.0197 | [−1.1474, +0.0632] | 4.5 |
| honest_start | 1994-03 | 5 | 391 | 0 | 1y | SHIP BASE RATE | +0.2462 | [+0.1325, +0.3566] | 31.5 |
| honest_start | 1994-03 | 5 | 391 | 0 | 5y | SHIP BASE RATE | +0.0619 | [−0.2163, +0.2030] | 5.5 |
| honest_start | 1994-03 | 5 | 391 | 0 | 10y | SHIP BASE RATE | −0.4940 | [−0.5273, −0.1265] | 2.2 |
| both | 1994-03 | 6 | 391 | 0 | 1y | SHIP BASE RATE | +0.2128 | [+0.0973, +0.3250] | 31.5 |
| both | 1994-03 | 6 | 391 | 0 | 5y | SHIP BASE RATE | +0.0722 | [−0.1986, +0.2176] | 5.5 |
| both | 1994-03 | 6 | 391 | 0 | 10y | SHIP BASE RATE | −0.3524 | [−0.4208, −0.1212] | 2.2 |

**The headline: the one-year SHIP MODEL verdict does not survive either fix.**
Every honest cell ships the base rate at every horizon. That is the finding. No
threshold was moved, and none will be.

The two fixes kill it for two entirely different reasons, and the difference
matters more than the shared outcome.

### Fix A kills it because regimes do not exist on the 1971 burn-in window

`honest_state_count` fails the **regimes-exist** gate at every horizon, and
therefore ships the base rate regardless of its skill. The gate asks whether more
than one state beats one on *both* the held-out log likelihood and the Bayesian
information criterion. On the 251-month panel as it stood at 1971-12 (1950-12 ..
1971-10):

| states | held-out log likelihood/month | information criterion |
|---:|---:|---:|
| 1 | **−5.7037** | 1,271 |
| 2 | −5.8281 | 1,040 |
| 3 | −5.9502 | 911 |
| 4 | −6.1991 | 852 |
| 5 | −6.2978 | **806** |
| 6 | −6.4209 | 812 |

**A single Gaussian wins the holdout outright.** The criterion prefers five
states, the holdout prefers one, and the gate requires both — so regimes-exist is
false and every horizon is SHIP BASE RATE. Note the skill scores in that cell are
not bad; the 10-year skill is −0.0197, the *best* of any cell. The verdict is
driven entirely by the gate, exactly as the pre-registration says it should be.

This is the honest reading, and it is uncomfortable: on the evidence an observer
actually had in 1971, there was no basis for a regime model at all. The shipped
run asserted five regimes on that window using data from the following
fifty-five years.

By 1994-03 the picture has changed — 518 months, two states beat one on the
holdout (−3.098 against −3.586) and six wins outright — which is why `both` passes
the regimes-exist gate and fails elsewhere.

### Fix B kills it because the sample is no longer large enough

`honest_start` and `both` pass regimes-exist and fail **calibration** at one year.
The start moves from 1971-12 to 1994-03, 658 forecast dates become 391, and the
independent observations behind the one-year verdict fall from **53.8 to 31.5**.
At five years 9.9 becomes 5.5; at ten years **4.5 becomes 2.2**.

**Any ten-year verdict from an honest run is close to uninformative by
construction.** The robustness gate cuts the sample into four chronological blocks
and is being asked to find a stable sign in roughly half an independent
observation per block. That is a real cost of removing the leak and it belongs in
these words. It is not grounds to keep the 1971 start, and it is not grounds to
move a threshold: a wide interval that fails the skill gate is a finding, not a
malfunction. "The honest sample cannot answer the ten-year question" is this
project's own thesis about information horizons applied to its own evidence base.

**The 1994-03 start also removes the entire stagflation episode from the
walk-forward.** The fitted panel still sees 1950–1994 — the 1994-03 vintage covers
1947 onward — so the model still *learns* the stagflation regime. But no forecast
is ever issued during it, so no forecast is ever scored on it. Expect the
"contracting growth, high inflation, high rates" regime to be present in the fit
and absent from the evaluation.

### A caveat on the six-state choice

`both` chooses six states, which is the **top of** `hidden_state_counts_to_search
= (1, …, 6)`. The choice is at the boundary, so the range may be binding and the
true preference may be seven or more. The range was deliberately not widened:
that is a third configuration change and would confound the 2x2. It is a candidate
debt entry.

## The shipping guard

`scripts/run_full_pipeline.sh` ran `poetry run forecast submit` unconditionally,
and `submit()` took `configuration_hash` live off the run's settings. With the
default flipped, the first routine run of the documented one-command pipeline
would have silently re-shipped `submission/forecasts.csv` under a configuration
nobody had looked at — the exact outward-facing move the goal reserves for Jeddy.

`configuration/shipping_approval.py` refuses at runtime. Before `submit()` writes
anything it takes the single configuration hash carried by
`backtest_results.parquet` (refusing outright if there is more than one — a
submission assembled from two runs has no provenance to check) and calls
`authorise_shipping`. That returns `None` when there is nothing to authorise —
the destination is not the repository's own `submission/`, or both hashes are
already the approved one — and otherwise raises `SubmissionNotApprovedError` with
the approved, live and producing hashes and the exact commands to proceed. `main()`
prints it to stderr and exits 2.

**Why the guard keys on the destination.** It protects the *committed* artifact,
not any directory named `submission`. `tests/test_submission.py` monkeypatches
the destination to a `tmp_path` and calls `submit()` six times with a placeholder
hash; an unconditional guard would break all six for no gain in safety. The
command line offers no way to point `submit` anywhere but the repository's own
directory. The residual gap — a Python caller that monkeypatches the destination —
writes somewhere that is not the shipped record, which is the thing being
protected. Stated rather than hidden.

**Why the pipeline step became `--verify-only`.** Three options were weighed.
Keeping `forecast submit` and letting the guard refuse was rejected: `set -euo
pipefail` means the documented pipeline would fail at step six of seven on every
run, and a pipeline that always fails is a pipeline someone "fixes" by deleting
the guard. Deleting the step was rejected: the routine run would then say nothing
about the submission, and the divergence between the honest default and the
shipped record — the most confusing fact this change creates — would go unreported
exactly where a reader would look for it. `forecast submit --verify-only` keeps
the pipeline green, writes nothing outward-facing, and prints the divergence every
time.

**No second freeze/thaw idiom.** The guard reuses `.claude/hooks/freeze_guard.py`'s
token file, format and minting command; it is a second *reader*, not a second
idiom. `submission/forecasts.csv` and `submission/manifest.json` were added to
`FROZEN_GLOBS`, so a hand edit is denied too.

**A bare `--thaw` does not authorise shipping, and that took a correction.**
Adding the two submission paths to `FROZEN_GLOBS` had a consequence the first
draft of this record missed. `mint_token` defaults to `subjects or
frozen_files(root)`, so `--thaw "<reason>"` with no `--subject` — its own
documented default — began minting a token whose `subjects` list *included*
`submission/forecasts.csv`. `consume_shipping_authorisation` checks membership,
not intent, so an operator thawing the pre-registration to fix a typo would also
have authorised the next `forecast submit` to overwrite the committed
submission. Silently. The guard built to stop accidental shipping had opened a
new path to it.

The fix is a new constant, `SHIPPING_GLOBS`, holding those two paths, and
`DEFAULT_THAW_GLOBS = FROZEN_GLOBS - SHIPPING_GLOBS`. A bare `--thaw` sweeps
`DEFAULT_THAW_GLOBS`, so it covers exactly what it covered before this unit
existed; the submission is reachable only by naming it,
`--subject submission/forecasts.csv`. The minting command prints the two paths it
withheld and how to name them, so the narrowing is visible at the moment it
applies rather than discovered later. `consume_shipping_authorisation` was
tightened in the same movement: it now requires the subject to be present,
where before an empty `subjects` list was read as "everything". Both readers now
agree that shipping is opt-in.

Three options were weighed. **Leaving the sweep broad and filtering in the
runtime guard alone** was rejected: the PreToolUse hook reads the same token, so a
broad thaw would still have let a hand edit through, and the two readers would
have disagreed about what one token means — which is the D3-adjacent failure the
plan named. **Recording an `explicit` flag on the token** and refusing to ship on
a defaulted one was rejected as a format change to a file two readers parse, to
carry information the subjects list can already carry by simply not containing
the path. **Narrowing the default sweep** wins because it makes the token itself
honest: what it names is what it authorises, for every reader, with no second
field to keep in step.

The cost is real and small: an operator who genuinely wants to thaw the
pre-registration *and* the submission mints two tokens instead of one. Given that
the second of those is the only outward-facing act this repository performs, a
second command is the correct price. It fails closed — the failure mode is a
refusal that says what to run, never a silent ship.

**The token has two consumers, and that is worth knowing before it bites.** Both
`freeze_guard.consume_token` and `consume_shipping_authorisation` read-then-unlink
`.claude/thaw-token.json`. Whichever acts first consumes it, so an editor touching
`submission/` after a token is minted for `forecast submit` will eat it, producing
a confusing "I thawed it and submit still refuses". The failure mode is always a
**refusal**, never a silent ship, so it is not blocking — but the refusal message
and `docs/TOOLING.md` both say it, and the advice is to mint the token immediately
before the submit.

A re-ship writes `shipped_under_authorisation` (reason, who, when) into the
manifest, which is what puts a name on the decision. The key is absent when
nothing needed authorising, so a manifest produced by the approved configuration
keeps exactly today's schema.

## Consequences

- Good: neither look-ahead path exists under the default, and the second is an
  executable assertion rather than an advisory rule.
- Good: the shipped record keeps its digest and its 56 cached fits, so the
  comparison's control column is exact rather than approximate.
- Good: the documented pipeline can no longer ship by accident, and shipping now
  carries a name — including from a bare `--thaw`, which deliberately withholds
  the two outward-facing paths.
- Bad / accepted: **the honest configuration ships the base rate at every
  horizon.** The project's one positive verdict was an artefact of two
  look-aheads. That is the result.
- Bad / accepted: 267 forecast dates and, at ten years, half the independent
  observations. The honest sample cannot answer the ten-year question.
- Bad / accepted: `docs/RESULTS.md`'s headline tables now describe a configuration
  that is not the default. They are labelled with `9f95b12dba40d138` rather than
  replaced, because replacing them without regenerating `forecasts.csv` would
  leave the submission and the report describing different runs.

### Today's forecast keeps the full-sample state count, and the objection to that

`forecast_now` still reads `selected_model.json` (five states) while the honest
backtest uses six, and `submission/forecasts.csv` is unchanged. The defence is
that at today's date the full sample contains no future, so a sweep on it leaks
nothing; selecting today's state count on a 1994 burn-in window would discard
thirty-two years of legitimately available data and would be worse, not more
honest.

**The residual objection, stated rather than buried:** under the burn-in policy
the *rule* is "select once, at the first forecast date", and today is not the
first forecast date, so the live forecast is not produced by literally the rule
the backtest validates. Resolving that either way changes `forecasts.csv`, which
this change is forbidden to touch and which the new guard now refuses to touch by
accident. **Flagged for Jeddy at re-ship time.**

### `gate_two_regime_model` still uses the full-sample sweep

That is deliberate, not an oversight. It is a gate on `fit-regimes` — a statement
about *today's* regimes, at today's date, where the full sample contains no
future. It is not a statement about the backtest, and the backtest no longer reads
its output.

## Options considered

- **Select the state count at every refit** — rejected. Fifty-five sweeps instead
  of one, and the measured behaviour is that the winner flips between adjacent
  counts for reasons that are not economic. A model whose number of regimes
  changes annually is tracking sampling noise in a holdout comparison, not the
  economy.
- **Stitch a "real-time diagonal" consumer price index** from the 19-month
  windows, taking each month's value from its own contemporaneous vintage —
  rejected, with the arithmetic. Vintages only start 1970-12, so a 240-month
  diagonal panel is not available until ~1991-12. That buys 27 months over the
  1994-03 boundary in exchange for a hybrid data definition that is neither a true
  vintage nor a final series.
- **Exclude the two new fields from the hash unconditionally** — rejected: it
  would break the digest's contract, letting two genuinely different runs claim
  one identity, and defeat gate four.
- **A separate `BacktestVariant` dataclass alongside `RunSettings`** — rejected:
  all four runs would then carry the same `configuration_hash`, contradicting the
  pre-registration's determinism clause, and fixing that would need a new result
  column.
- **A second token file and a `forecast submit --authorise` flag** — rejected: a
  second idiom for a decision this repository already has one idiom for, and a
  reason typed on a command line is recorded nowhere until the write succeeds.
- **Importing `freeze_guard.py` from `src/`** — rejected: it is stdlib-only
  operational tooling under `.claude/`, and importing across that boundary would
  make the package depend on the agent harness.

## A correction to the pre-registration's prose, which was not made

`proving/experiments/0001-*/experiment.json`'s known-limitations text says the
consumer price index has no usable vintage before **1997**. The measured boundary
is **1994-03**. `docs/adr/0002-three-vintage-policies.md` and the
`MINIMUM_USABLE_VINTAGE_MONTHS` docstring carried the same estimate and have both
been corrected, each keeping a note of what it previously said.

**`experiment.json` was deliberately not edited.** It is frozen, no thaw token was
minted for it, and the sentence in question is descriptive prose in a limitations
note, not a threshold. Correcting a frozen pre-registration to make it look better
informed after the fact is the wrong instinct even when the correction is true.
The right record is this one: the pre-registration says 1997, the measurement says
1994-03, and the discrepancy is noted here rather than edited away there.
