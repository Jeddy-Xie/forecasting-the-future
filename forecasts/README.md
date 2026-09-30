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

The walk-forward backtest scores retrodictions. That measures the method against
history. It does not measure a model against the future, and the two are different
claims: a Brier skill score computed over 1994–2026 and the same number computed
forward from 2026 are not the same evidence.

`submission/forecasts.csv` holds real claims about 2027, 2031 and 2036. Without this
directory nothing would ever score them, because nothing would record when they
were made or when they came due.

## What is on the register

| round made | configuration | forecaster | what it is |
|---|---|---|---|
| 2026-09-09 | `9f95b12dba40d138` | (source) | the original shipped configuration, with two look-ahead paths since closed (ADR 0008) |
| 2026-09-29 | `fec79a040f9ca6f9` | (source) | the two-chain regime model alone, shipped between the two re-ships of 2026-09-29 |
| 2026-09-29 | `ad7fcc1affd0746a` | (source) | the single-chain model |
| 2026-09-29 | `7647c129be85291e` | blend of regime model and condition chain | **shipped**, under rule 0007 (ADR 0013) |
| 2026-09-29 | `7647c129be85291e` | condition_chain | R2, the regime-free chain |
| 2026-09-29 | `7647c129be85291e` | model_sample_climatology | R1, the base rate 0007 ships |

`forecaster` names whose claim a line is, because one run can register several. Lines written before
2026-09-29 have none and read as their `source`. A line made under rule 0007 carries:
- the method's probability in `model_probability`;
- R1 in `climatological_base_rate`.

**Which forward comparison each claim serves:**
- **The blend against R2:** does the shipped method beat the chain it contains?
- **The regime model alone against the single chain:** the two-chain adoption's falsifier (ADR 0010), read at
  2027-07-01, 2028-07-01 and 2029-07-01.
- **The regime model alone against R2:** do regimes help?
- **Anything against R1:** skill against a fair base rate.

**Read this before using the one-year rows.**
- The blend is experiment 0008's arm B3, confirmed in sample.
- It is not shown to beat the chain alone at one year, and the chain beats it at ten.
- Everything shipped is in sample. This register is the only test that is not.

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
3. `forecast register --companion condition-chain` and `--companion model-sample-climatology` record R2 and
   R1 from the same run.
4. `forecast register --from forecasts/companions/<name>` records each companion configuration. Such a grid is
   written by `forecast submit --rule 0001 --destination forecasts/companions/<name>`, run in a workspace whose
   settings are that configuration. Nothing is shipped from there, so no authorisation is needed. The companions
   are:
   - the regime model alone, `fec79a040f9ca6f9`;
   - the single chain, `ad7fcc1affd0746a`.
5. `forecast resolve`.

Nothing schedules this, so it is checked instead. `forecast register --check` exits 1,
and `check-gates` and `submit --verify-only` print a warning, once the newest round is
more than 45 days old.

The first one-year forecast resolves **2027-07-01**; five-year in 2031; ten-year
in 2036. The scorecard prints `INERT` below ten resolved forecasts — the numbers
are shown, the inference is refused.
