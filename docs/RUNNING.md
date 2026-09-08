# Running this project

Every command below is copy-pasteable and shows what success looks like, so you
can tell a working step from a broken one without reading the code.

## Set up, once

```bash
poetry install
```

That installs the package, the development tools and the notebook kernel. No API
key is needed anywhere; both Federal Reserve endpoints this project uses are
public and keyless (ADR 0001). Success looks like:

```
Installing the current project: economic-regime-forecasting (1.0.0)
```

Check it worked:

```bash
poetry run pytest -m "not network"
```

Roughly two hundred tests, a few seconds. One test is marked `network` and is
skipped by that flag; it asks the live service whether it still serves archival
vintages without a key, which is the project's central data assumption.

## Populate the cache

```bash
poetry run forecast fetch-data
```

This downloads nine series at their current vintage, then roughly thirteen
hundred archival vintages, one per forecast date for each of the two series that
get revised. Expect ten to fifteen minutes on a cold cache and a few seconds
afterwards. Success ends with:

```
cache holds 1355 entries
every vintage the backtest needs is cached
```

**On rate limits.** The service is free, public and publishes no quota, so
politeness is the client's job. It blocks an address that asks too fast, and the
block covers every endpoint including the ordinary ones. The client spaces its own
requests at about three a second and backs off for up to ninety seconds when
refused; raising `--workers` past the default of two will not make it faster and
may earn a block. If you are blocked, wait a few minutes and re-run the same
command. Anything already cached is skipped, so it resumes where it stopped.

## Run the pipeline

```bash
poetry run forecast check-gates
```

This runs all five stage gates in order and stops at the first failure. Twenty to
forty minutes on a cold cache; the walk-forward backtest is nearly all of it, and
its fitted models are cached so a second run is fast. Success ends with:

```
All five gates passed.
```

Each stage can also be run alone, in this order:

| command | gate | what it writes |
|---|---|---|
| `forecast audit-data` | 1 | the series audit and revision tables |
| `forecast fit-regimes` | 2 | the regime sweep, the chosen model, its description |
| `forecast forecast-now` | 3 | the current ten by three grid and the mixing table |
| `forecast backtest` | 4 | one row per indicator, date and horizon |
| `forecast evaluate` | 5 | every metric, and the verdict per horizon |
| `forecast submit` | — | `submission/forecasts.csv` and its manifest |

Add `--verbose` to any of them to see what each step is doing. Add
`--as-of YYYY-MM-DD` to run the whole thing as though it were an earlier date.

## Read the results

```bash
poetry run jupyter lab notebooks/
```

Four notebooks, in order. Each reads what the commands above wrote and displays
it; none of them computes anything of its own.

| notebook | answers |
|---|---|
| `01_economic_data_audit` | what was fetched, how much it has been revised |
| `02_regime_model` | how many regimes, what they are, how long they stay informative |
| `03_backtest_and_evaluation` | did it beat the base rate, and is it calibrated |
| `04_report` | the write-up, including what this method cannot do |

## When something fails

**`no cache entry for … Run 'forecast fetch-data' first.'`** — exactly that.

**`N archival vintages the run needs are not cached`** — the backtest checks up
front rather than dying forty minutes in. Run `forecast fetch-data`.

**`could not fetch … after N attempts`** — you are rate limited. Wait a few
minutes and re-run; see the note above.

**`… contains an observation labelled …, which had not happened yet`** — a
look-ahead guard fired at the panel boundary. This is the most important error in
the project and it is never a false alarm: some series is being read earlier than
it could have been known. Check the `publication_lag_days` of the series it names.

**`panel is not a complete monthly sequence`** — a series has a hole longer than
one month. October 2025 has no consumer price index or unemployment rate because
the government shut down and the surveys were never run; single-month holes are
interpolated and recorded, and anything longer needs a decision rather than a
straight line.

**`the data do not support regimes at this frequency`** — the state sweep found
nothing both persistent and populated. That is a finding, and the right response
is to report it, not to lower the floors in `models/state_selection.py`.

**A gate fails.** Read what it says. Every check prints its requirement and its
evidence. The pipeline stops there on purpose: a gate that is worked around is
not a gate.

## Starting over

```bash
rm -rf .cache && poetry run forecast fetch-data && poetry run forecast check-gates
```

Nothing outside `.cache/` and `submission/` is generated, and everything in
`.cache/` is reproducible from the registries.
