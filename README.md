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

The model that runs and ships is an **equal-weight blend** of two forecasters:
- a two-chain regime model, one chain for growth and one for inflation with interest rates, sixteen joint
  regimes;
- a regime-free chain on each indicator's own monthly condition.

It was walked forward over 391 monthly forecast dates from 1994-03, the first month every input is on a genuine
point-in-time vintage. It is scored by two rules:
- **0001**, committed before the first backtest ran and frozen;
- **0007**, which has governed new claims and re-ships since 2026-09-29. It uses a fairer benchmark, a
  calibration test sized for this sample, and the regime-free chain as the bar to clear.

| horizon | 0001 | 0007 | skill vs the model's own sample | what ships |
|---|---|---|---:|---|
| 1 year | ship the model | **ship the model** | +0.240 [+0.172, +0.311] | the blend |
| 5 years | ship the base rate | ship the base rate | +0.097 | the base rate |
| 10 years | ship the base rate | ship the base rate | −0.055 | the base rate |

What that means:

- **Most of the skill is persistence, not regimes.** A chain that knows only whether each condition holds now
  beat the regime model alone at one year (−0.058, 98.33% [−0.112, −0.009]), and was never worse at any
  horizon.
- **The blend is what the evidence supports.** It is the regime model plus that chain, experiment 0008's
  confirmed arm: +0.0615 over the regime model at one year, 96.67% [+0.034, +0.096]. It is not shown to beat
  the chain alone.
- **Where regimes help.** Inflation and the zero lower bound, which the model observes. Not unemployment or
  recession dating.
- **How far the information reaches.** Measured month by month, the blend carries skill for about 46 months
  against a fair benchmark, and the regime model alone for 29. Past that, ship the base rate.
- **The two chains earn their keep through structure, not their count** (experiment 0006). A six-cell version
  matches the sixteen-cell one on half the parameters. Experiment 0011 will test it.
- **Every number here is in sample.** The forward register, monthly since 2026-09-29, is the only
  out-of-sample test. Its first one-year claims resolve on 2027-07-01.

The research paper, `paper/main.pdf`, tells the whole story for a reader without an economics
background. Full numbers and the reasoning are in `docs/RESULTS.md`. The rule change is in ADR 0012, the blend in ADR 0013,
and the month-by-month curve in `research/reports/skill-at-every-horizon/`. Decisions made on the owner's behalf
are recorded, with their reasons, in `research/ledger/delegated-decisions/`.

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
| `paper/` | the research paper; its figures and tables are generated from the committed record |
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
| `paper/main.pdf` | the research paper: method, results and every table, written for non-specialists |
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
