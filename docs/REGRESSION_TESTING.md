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
