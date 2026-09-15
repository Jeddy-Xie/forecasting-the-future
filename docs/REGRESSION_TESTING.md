# Regression testing

`forecast baseline` answers "what did this change move?" the same way every time,
rather than by a bespoke investigation. It closed D13 in
[TECHNICAL_DEBT.md](TECHNICAL_DEBT.md). The code is
`src/economic_regime_forecasting/regression_baseline.py`; the paired statistic is
`evaluation/paired_skill_comparison.py`.

## What a baseline is

Two committed files under `baselines/`, written together by one capture or not at
all:

| file | holds |
|---|---|
| `<name>.json` | `format_version`, the run's identity, the three horizon verdicts and the thirty per-indicator metric rows |
| `<name>.forecasts.parquet` | every backtest forecast: indicator, forecast date, horizon, predicted probability, climatology probability, realised outcome, configuration hash |

Both are read off artifacts the pipeline already wrote; nothing is recomputed.
They are **not cache**. They live in `baselines/`, are committed and are never
rebuilt, because they are the record a change is measured against, and
`rm -rf .cache` must not be able to erase it. The forecasts file is the one
piece of the backtest frame small enough to commit that still carries what a
skill score is computed from.

`forecast check-gates` ends by writing the same JSON structure to
`.cache/models/run_summary.json`, using the same function, so a fresh run and a
baseline cannot disagree about their own format.

## The plain comparison: did anything move?

`forecast baseline compare` lines every field up against the baseline and puts
each difference in a band:

| band | condition | meaning |
|---|---|---|
| `IDENTICAL` | the difference is exactly 0 | bit for bit |
| `NUMERICAL` | 0 < abs(difference) <= 1e-9 | environment drift, not a regression |
| `MOVED` | abs(difference) > 1e-9 | a real change; reported |

**Why 1e-9.** A fit reproduced across a numpy or BLAS change drifts at about
1e-13 (ADR 0008). A byte-identity check would fail on that, and a check that
cries wolf gets switched off. The smallest quantity in a baseline a reader would
act on is around 1e-4. So 1e-9 sits four orders of magnitude above the drift and
five below anything that matters. It is a constant, not a flag, because a tolerance
a caller can widen after seeing a result is the failure ADR 0008 records:
`assert_frame_equal` passing a 1e-13 difference silently at its default
tolerance. `--tolerance-band` changes which rows are printed and never how one is
classified.

The verdict, the failing gates and every field of the run's identity are compared
for exact equality, and any difference is `MOVED`. They are **listed first, under
their own heading**, above every numeric move. The likeliest way this report fails
is a verdict flip lost among forty routine numeric deltas.

A row or field on one side only is `ADDED` or `REMOVED`, never skipped. Exit 0
when nothing moved, 1 when something did, 2 when the comparison could not be made.

## The paired comparison: better, or only different?

`forecast baseline compare --paired` is **the one to trust when judging whether a
change is an improvement.**

Two runs' headline skill scores, each with its own interval, cannot tell an
improvement from noise. At ten years each interval rests on about two independent
observations, and the two overlap for almost any change worth making. Most of that
width is shared: both runs forecast the same indicators on the same dates against
the same outcomes, so a decade that is hard for one is hard for the other. The
paired comparison scores both runs on the *same* resampled dates and takes the
difference each time, which cancels the shared part.

Per horizon it reports this run's mean Brier skill score minus the baseline's,
with a moving-block bootstrap interval:

- **The statistic is the verdict's own**, imported from `evaluation/verdict.py`
  rather than restated. When the two runs cover the same forecasts, each side's
  number is exactly what its own verdict reports. The command checks that on
  every run and refuses if it fails.
- **Forecast dates are resampled in blocks as long as the horizon**, as the
  pre-registration says. Every indicator on a date is kept together (ADR 0007),
  and one draw of dates per resample is applied to both runs.
- **Seed, resample count and default confidence level come from `RunSettings`**
  and are printed with the result. A test pins them to the pre-registration's
  values.
- **Runs with different start dates are compared on the intersection** of their
  resolved (indicator, forecast date, horizon) keys. The output states how many
  rows are in both, only in the baseline and only in this run, and the dates of
  each. Nothing is dropped without being counted.
- Per-indicator differences are shown too, as point estimates only. Thirty
  intervals printed side by side invite reading the widest swing as a finding.

`--confidence-level` is repeatable. `--confidence-level 0.90 --confidence-level
0.9833` gives one interval per level, every one read off the same resamples, so
the higher level's interval always contains the lower one's. Every interval is
labelled with its exact level, in the table and in the JSON.

**The A/A check.** A run paired with itself gives a difference of exactly 0.0 on
the interval [0.0, 0.0]. It is a test, and it proves the pairing: two different
draws of dates could not produce an interval of zero width.

`--paired` measures and does not judge. It exits 0 whenever the measurement could
be made and 2 when it could not (a horizon with no shared forecasts, a missing
forecasts file, a format mismatch). `--format json` emits the whole of it.

## The format version

Every baseline and every run summary records an integer `format_version`,
currently 1. A serialization change silently invalidates stored baselines, so both
comparisons refuse a baseline written in any other version, naming both and
saying to re-capture.

**Bump `FORMAT_VERSION`** in `regression_baseline.py`, in the same commit, when
the fields a baseline records change (their names, types or blocks) or the
forecasts file's columns do. Do not bump it because a run produces different
numbers; that is what the comparison is there to report. There is no migration:
re-capture.

## The workflow for a branch

On `main`, after a passing `forecast check-gates`:

```bash
poetry run forecast baseline capture --name main --force
git add baselines/ && git commit
```

`main`'s baseline is re-captured only when a change landing on `main` is meant to
move its numbers, and in the same commit as that change. A branch never
re-captures it.

On the branch, after its own `forecast check-gates`:

```bash
poetry run forecast baseline compare                 # what moved, categorical changes first
poetry run forecast baseline compare --paired        # the skill difference, with intervals
poetry run forecast baseline compare --paired --format json > comparison.json
```

Read the plain comparison first: if a verdict or the run's identity moved, that
is the headline. The paired comparison then says whether the change in skill is
distinguishable from noise. `forecast baseline list` shows every committed
baseline with its format and run identity.

## The look-ahead audit: could any forecast have seen the future?

`forecast audit-look-ahead` asks a different question from the baseline. It does
not ask what moved between two runs. It asks whether any forecast depended on
something not yet published. The code is
`src/economic_regime_forecasting/look_ahead_audit.py`. It is the deterministic
half of the research slate's VOID rule
(`proving/experiments/0002-research-slate-2026-09/experiment.json`): an arm is void
unless this exits 0 on its branch, and main must pass it before any arm runs.

**How it works.** Pick a cutoff date C. On a copy of the cache in a temporary
directory, written through `data/cache.py`, replace everything a forecaster at C
could not have seen with `value * 1.7 + 11.0`:

- every value of every archival vintage dated after C, months before C included,
  because a later vintage carries revisions nobody had at C;
- every observation in a current-vintage file that was still unpublished at C:
  labelled on or after C, or labelled so recently that its series' publication
  lag, taken from the registry, runs past C. Archival vintages dated on or before
  C are left alone, since everything in one had been published by its date. The
  derived term spread is computed from its two legs, each perturbed by its own
  lag, so it is perturbed exactly where the larger lag runs past C.

Then run the walk-forward twice over the same schedule truncated at C, once on an
unperturbed copy and once on the perturbed one. Each run gets an empty
fitted-model store, so every fit and the burn-in state-count choice are
recomputed rather than read back. Every row must agree **exactly** on
`predicted_probability`, `regime_distribution`, `climatology_probability`,
`state_count` and `refit_date`. `realised_outcome` is not compared, because it
depends on the future by definition.

**Why exact, when the baseline uses 1e-9.** The band above exists for
comparisons across environments. Both runs here are in one process, where fits
are byte-identical (measured 2026-09-15), so any tolerance would only be room for
a leak to hide in.

| exit | meaning |
|---|---|
| 0 | every compared field identical on every row |
| 1 | at least one row moved: a look-ahead. Moved rows are listed earliest forecast date first; the earliest is where the leak enters |
| 2 | the check could not be made: no cache, an empty truncated schedule, rows on one side only, a run that crashed. Never a pass |

The default cutoff is the first refit at least 72 months after the first forecast
date. On the default schedule that is 2000-03-01, covering 73 forecast dates and 7
refits (the burn-in choice among them) in about six minutes. `--cutoff` picks
another. The record, with every moved row, goes to
`.cache/models/look_ahead_audit.json`. It replaces any earlier record even when the
check could not be made, so a stale pass is never read as today's answer. Two
audits of one commit write byte-identical records.

**What it does not cover.**
- Revised values of observations already published at C, in the current-vintage
  files. Per-regime rates read final revised conditions with publication timing
  enforced, a documented approximation (D5 in `TECHNICAL_DEBT.md`), and
  perturbing them would fail by design.
- A publication lag that is itself wrong. The check takes each series' lag from
  the registry, the figure the pipeline censors by, so a lag set too short there
  is invisible to both.
- For a forecast issued before C, information published between its date and C.

The forecast issued at C itself is the sharpest test, which is why the default
cutoff is a forecast date and a refit date.

**It has been seen to fail, twice.** First, a test injects a leak: every model is
fitted on the panel as it stood two years after its refit date. The audit exits 1,
and its earliest moved row is the first refit whose borrowed panel reaches past
the cutoff. Second, the audit's first run on main, on the pipeline as of 9bf13d6,
**exited 1**:

    LOOK-AHEAD: 12 of 2190 forecasts issued on or before 2000-03-01 changed when
    only information unavailable at 2000-03-01 was perturbed, on 1 forecast date(s)
    from 2000-03-01 to 2000-03-01. The earliest is where the leak enters.

    2000-03-01  consumer_price_inflation_above_five_percent_within_horizon  12
                climatology_probability  0.375  ->  0.37662337662337664

All twelve moved rows are `climatology_probability` at the cutoff itself. The
benchmark at a forecast date t counted the outcome of the forecast made at t − h,
which resolves on the value labelled t. That value is published weeks later, or
400 days later for recession dating. **Main failed this audit at the commit that
introduced it** (fb926ff). The look-ahead audit table in `TECHNICAL_DEBT.md`
records it.

The next commit makes an outcome wait until the value it rests on is published,
by the rule the conditions already obeyed (ADR 0009). The audit on main then
exits 0, in 333 seconds:

    PASS: no forecast issued on or before 2000-03-01 changed when every
    observation unavailable at 2000-03-01 was perturbed

**Unavailable means unpublished.** Until 2026-09-15 the second rule above went by
labels alone. The pre-registered decision rule says every observation
*unavailable* at the cutoff. A value labelled a month before C with a 44-day lag
was unavailable at C, and it was left untouched. So the classic one-month
look-ahead would have passed. The benchmark leak above was caught only because it
touched a value labelled exactly C.

A test keeps both halves on the record. A rate series censored by label instead
of by its 45-day lag passes the label rule, exit 0: the leak is invisible. The
same leak fails the publication rule, exit 1: the forecast issued at the cutoff
moves, and no earlier one. The publication-aware audit on main exits 0, in 343
seconds, having perturbed 627,617 values where the label rule perturbed 627,596:

    PASS: no forecast issued on or before 2000-03-01 changed when every
    observation unavailable at 2000-03-01 was perturbed
