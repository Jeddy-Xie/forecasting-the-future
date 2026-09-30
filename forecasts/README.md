# forecasts/

The register: probability forecasts about the **actual future**, and the scoring
of them once it arrives.

| file | what it is |
|---|---|
| `register.jsonl` | append-only. One line per forecast, carrying the configuration hash that produced it, the date it was made, and the date it resolves. |
| `resolutions.jsonl` | append-only. One line per forecast whose date has passed, with what happened and its Brier score against both the model and the climatology shipped beside it. |

Both are **committed**, and both are guarded by `.claude/hooks/freeze_guard.py`,
which refuses an in-place rewrite. Appending is the only way in. A forecast that
could be edited after the fact is not a forecast.

## Why this exists

The walk-forward backtest scores 19,740 retrodictions. That measures the method
against history. It does not measure this model against the future, and the two
are different claims: a Brier skill score of +0.232 computed over 1971–2026 and
the same number computed forward from 2026 are not the same evidence.

`submission/forecasts.csv` already holds real claims about 2027, 2031 and 2036.
Without this directory nothing would ever score them, because nothing would
record when they were made or when they came due.

## Operating it

    poetry run forecast submit      # produce the grid
    poetry run forecast register    # record it as dated claims
    poetry run forecast resolve     # score whatever has come due

### The monthly round

Since 2026-09-29 (delegated decision P1-8) a round is registered on the first of every
month, not only when the submission is re-shipped: every month not registered is
holdout evidence lost for good.

1. `forecast check-gates` (as of that day), so the grid is today's.
2. `forecast register` records the shipped grid in `submission/`.
3. `forecast register --from forecasts/companions/<name>` records each companion
   configuration beside it. Such a grid is written by `forecast submit --destination
   forecasts/companions/<name>`, run in a workspace whose settings are that
   configuration. Nothing is shipped from there, so no authorisation is needed. The
   first companion is the single chain, `ad7fcc1affd0746a`, which the two-chain
   adoption's falsifier needs forward beside the default.
4. `forecast resolve`.

Nothing schedules this, so it is checked instead. `forecast register --check` exits 1,
and `check-gates` and `submit --verify-only` print a warning, once the newest round is
more than 45 days old.

The first one-year forecast resolves **2027-07-01**; five-year in 2031; ten-year
in 2036. The scorecard prints `INERT` below ten resolved forecasts — the numbers
are shown, the inference is refused.
