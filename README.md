# Forecasting the Future

Probability forecasts for **ten binary macroeconomic indicators** at horizons of
**one, five and ten years**, produced by inferring which latent *economic regime*
the United States economy currently occupies and projecting that regime forward.

The thesis being tested is narrow and falsifiable:

> The macroeconomy occupies a small number of persistent latent regimes
> characterised by growth, inflation and interest rates. If the current regime can
> be inferred probabilistically, and its evolution projected through a transition
> matrix, then conditional base rates give calibrated forecasts that beat
> unconditional climatology.

That thesis may be false, and it is expected to be false at the longest horizon.
The acceptance thresholds that decide it were written down and committed **before
the first backtest ran** (`proving/experiments/0001-regime-conditional-forecast-skill/`).
A negative result, correctly measured, is the deliverable when the thesis fails.

## What it found

A walk-forward run of 19,740 forecasts from 1971 to 2026, scored against a rule
committed before the first backtest ran:

| horizon | verdict | skill against climatology | 90% interval |
|---|---|---:|---|
| 1 year | **ship the model** | +0.232 | [+0.158, +0.301] |
| 5 years | ship the base rate | +0.102 | [−0.013, +0.197] |
| 10 years | ship the base rate | −0.221 | [−2.744, −0.014] |

Five persistent regimes, including a recognisable stagflation state and a
zero-rate state, neither put there by hand. The transition matrix's second
eigenvalue modulus is 0.983, a 41 month half life, which puts the information
horizon at five years. Almost all the one-year skill is in questions of the form
"does this happen at any point between now and then"; questions about where a
slow-moving level sits in one particular month are close to a coin flip.

Full numbers and the reasoning in `docs/RESULTS.md`.

## The honest finding this repository is built to produce

A regime transition matrix mixes. The distance between a projected regime
distribution and the model's long-run stationary distribution decays like
`|second largest eigenvalue|^h`. Past some horizon the projection *is* the
unconditional base rate, carrying no information about today. This repository
measures that horizon rather than hiding it, calls it the **information horizon**,
and ships the climatological base rate for any horizon beyond it.

## Repository map

| directory | job |
|---|---|
| `src/economic_regime_forecasting/` | every piece of reusable logic, importable and tested |
| `scripts/` | operational glue that nothing imports |
| `notebooks/` | four notebooks: audit, model, backtest, report. Narrative only; no logic |
| `tests/` | the test suite, named after the requirements it pins |
| `docs/` | operator manual, pre-registration, architecture decision records |
| `proving/` | the pre-registered experiment whose decision rule the evaluation obeys |
| `.cache/` | all fetched and derived data. Git-ignored, rebuilt by one command |

Inside the package:

| package | one reason to change |
|---|---|
| `configuration/` | which series are inputs and which indicators are targets |
| `data/` | how data is fetched, cached, and made point-in-time |
| `features/` | how raw series become a standardised observation matrix |
| `models/` | the hidden Markov model and everything computed from it |
| `backtest/` | how forecasts are produced walk-forward through history |
| `evaluation/` | how forecasts are scored and how the ship decision is made |
| `reporting/` | figures and tables for the notebooks. Presentation only |

## Where to read what

| document | its one job |
|---|---|
| this file | the front door: what this is, and how to start |
| `docs/RUNNING.md` | how to operate everything, with the output each step should print |
| `docs/adr/` | why each non-obvious decision was made, one numbered record each |
| `proving/experiments/0001-.../experiment.json` | the decision rule, committed before the first backtest ran |
| `docs/RESULTS.md` | every headline number, regenerated rather than typed |
| `notebooks/04_report.ipynb` | the write-up, including what this method cannot do |
| `CLAUDE.md` | the rules that bind anyone, human or agent, working in this repository |

## Getting started

```bash
poetry install                 # full environment, including notebook and dev tools
poetry run forecast fetch-data # populate .cache/ from the Federal Reserve
poetry run pytest              # the suite
poetry run forecast check-gates # the five acceptance gates, in order
```

No API key is required. See `docs/RUNNING.md` for the full operator walkthrough
and `docs/adr/` for why each non-obvious decision was made.

## What is deliberately not here

- **No look-ahead anywhere.** Every training panel is assembled `as_of` a date,
  every standardisation window is expanding, every backtest uses filtered rather
  than smoothed state probabilities, and conditional base rates at time `t` use
  only outcomes that had already resolved by `t`.
- **No silent fallbacks.** A failed fetch, a non-converging fit, or a failed gate
  raises. A gate that errors is not a gate that passed.
- **No tuning toward a positive result.** The decision rule is pre-registered and
  machine-evaluated.

## Licence

MIT.
