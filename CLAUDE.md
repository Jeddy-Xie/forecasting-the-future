# Forecasting the Future

Probability forecasts for ten binary macroeconomic indicators at one, five and
ten year horizons, from a hidden Markov model over latent economic regimes.
Owner: Jeddy Xie. Work happens directly on `main`; commits are the history.

## Layout
- `src/economic_regime_forecasting/` — every piece of reusable logic. Notebooks
  and scripts import from here and contain none of their own. Layer order is
  declared in the package docstring and dependencies point one way only.
- `scripts/` — operational glue that nothing imports. The command line interface
  is `src/economic_regime_forecasting/command_line_interface.py`, exposed by
  Poetry as `forecast`.
- `notebooks/` — exactly four, one per stage: audit, model, backtest, report.
- `tests/` — pytest. Test names state the requirement they pin.
- `.cache/` — all fetched and derived data, git-ignored, rebuilt from the
  registries by `forecast fetch-data`. Nothing here is ever committed.
- `proving/experiments/` — the pre-registered decision rule the evaluation obeys.
- `docs/adr/` — numbered architecture decision records.

## Rules that bind every session here
- **No look-ahead, ever.** Every function that assembles a training panel takes
  an `as_of` date; there is no code path that assembles one without it.
  Standardisation windows expand, they never span the full sample. Backtests use
  filtered state probabilities, never smoothed. Conditional base rates estimated
  at time `t` use only outcomes that had already resolved by `t`.
- **Every cache write goes through `data/cache.py`.** No loose `read_csv` or
  `to_parquet` anywhere else. Entries are keyed by a content hash of the request
  and carry a sidecar manifest recording what was fetched and when.
- **No silent fallbacks.** A failed fetch, a non-converging fit or a failed gate
  raises with a message saying what to do next. A gate that errors is not a gate
  that passed. A fallback that is taken deliberately is recorded in the manifest.
- **The decision rule does not move.** Acceptance thresholds live in
  `proving/experiments/0001-regime-conditional-forecast-skill/experiment.json`
  and were committed before the first backtest ran. Changing one after seeing
  results is the single forbidden act. A negative result is a finding.
- **Determinism.** Seeds are fixed and recorded in every run manifest. Two runs
  of the same configuration produce byte-identical outputs.
- **Notebooks hold no logic.** A cell defining behaviour that exists nowhere in
  `src/` is a defect. Outputs are stripped before commit.
- **Names are for readers without domain expertise.** Spell it out:
  `federal_funds_rate`, not `ffr`. If a brief read does not tell you what a
  module does, it is named wrong.
- **Documentation ships with the behaviour it describes**, in the same commit.

## Commands
- Environment: `poetry install`
- Suite: `poetry run pytest` (add `-m "not network"` when offline)
- Lint and types: `poetry run ruff check . && poetry run ruff format --check . && poetry run mypy`
- Data: `poetry run forecast fetch-data`
- Gates: `poetry run forecast check-gates`
- Everything, in order: `./scripts/run_full_pipeline.sh`

## Compact instructions
When compacting, always preserve: which of the five gates have passed, the list
of modified files, the suite and gate commands, and any unresolved finding.
