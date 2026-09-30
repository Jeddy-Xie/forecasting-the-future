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

The default model fits two regime chains, one for growth and one for inflation with interest rates:
sixteen joint regimes. It was walked forward over 391 monthly forecast dates from 1994-03, the first
month every input is on a genuine point-in-time vintage. It is scored by two rules.

- **0001** was committed before the first backtest ran, and is frozen.
- **0007** has governed new claims since 2026-09-29. It uses a fairer benchmark, a calibration test
  sized for this sample, and a forecaster with no regimes as the bar to clear.

| horizon | 0001 | skill vs climatology | 0007 | skill vs the model's own sample |
|---|---|---:|---|---:|
| 1 year | **ship the model** | +0.267 [+0.165, +0.365] | ship the base rate | +0.179 [+0.102, +0.258] |
| 5 years | ship the base rate | +0.119 | ship the base rate | +0.069 |
| 10 years | ship the base rate | −0.162 | ship the base rate | −0.211 |

What that means:

- **The regimes carry information for about two and a half years.** Measured month by month, the model
  beats the historical average for 29 months, and for 39 against 0001's more generous benchmark.
- **A forecaster without regimes does at least as well.** A two-state Markov chain on each indicator's
  own monthly condition beats the model at one year (−0.058, 98.33% [−0.112, −0.009]), and is never
  worse at any horizon.
- **Regimes help where the model observes the question, and not elsewhere.** They add skill on
  inflation and the zero lower bound, which the model observes. They add none on unemployment or
  recession dating, which it does not. Against a fair benchmark its recession skill is below zero.
- **What ships.** Under 0001, one year ships the model and five and ten years ship the base rate. Under
  0007 every horizon would ship the base rate. The model is also overconfident: its calibration slope
  is 0.61.
- **Experiment 0008** tests three ways to keep what regimes add while taking what the chain has.

Full numbers and the reasoning are in `docs/RESULTS.md`. The month-by-month curve is in
`research/reports/skill-at-every-horizon/`. The rule change and why are in ADR 0012.

## The honest finding this repository is built to produce

A regime transition matrix mixes. The distance between a projected regime
distribution and the model's long-run stationary distribution decays like
`|second largest eigenvalue|^h`. Past some horizon the projection *is* the
unconditional base rate, carrying no information about today. This repository
measures that horizon rather than hiding it, calls it the **information horizon**,
and ships the climatological base rate for any horizon beyond it.

It turned out to need a second honest finding.
- **Skill against a base rate does not show that regimes are the reason for it.**
  - Much of the skill is persistence: whether the condition holds now.
  - A chain that knows only that, and nothing about regimes, forecasts as well or better.
- **So the repository scores that chain beside every forecast**, and asks every new claim to beat it
  (ADR 0012).

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
| `proving/experiments/0007-.../experiment.json` | the successor rule every new claim is read by |
| `forecasts/` | forecasts registered forward, monthly, and scored as they resolve |
| `research/ledger/delegated-decisions/` | decisions the owner delegated, with their reasons, verbatim |
| `docs/TECHNICAL_DEBT.md` | proposed fixes that were **not** made, and what each would change |
| `notebooks/04_report.ipynb` | the write-up, including what this method cannot do |
| `CLAUDE.md` | the rules that bind anyone, human or agent, working in this repository |
| `docs/TOOLING.md` | what is in `.claude/`, what each check refuses, and how to drive it |

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
