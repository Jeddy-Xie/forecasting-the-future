# 0003. A source-layout package with names spelled out in full

Date: 2026-09-08 · Status: accepted

## Context and problem
The brief specified an `include/` directory for importable modules. `include/` is
a C and C++ convention; in a Python project a reader has to be told what it means,
and the tooling has to be argued with to make it importable. The Foundry Python
standard, which this repository treats as ground truth for structure, specifies a
source layout with a single `pyproject.toml` carrying build metadata and every
tool's configuration.

Separately, the owner's naming rule: assume the reader has no domain expertise.
An abbreviation that is obvious inside a field is opaque outside it, and the
saving is a few characters against a permanent cost in legibility.

## Decision
- `src/economic_regime_forecasting/` holds every importable module. The package
  name says what the project does rather than repeating the repository's title.
- Names are spelled out. `federal_funds_rate`, not `ffr`. `three_month_treasury_bill_rate`,
  not `t_bill_3m`. `command_line_interface.py`, not `cli.py`. Module names are
  noun phrases a non-specialist can read: `indicator_outcomes`, `state_labelling`,
  `walk_forward`.
- The command line interface lives in the package behind a Poetry entry point, so
  `scripts/` holds only operational glue that nothing imports.
- Package layering is declared in the top-level docstring and dependencies point
  one way: configuration, then data and features, then models, then backtest,
  with evaluation depending on none of them.

## Consequences
- Good: `poetry install` alone makes every import work, with no path manipulation
  in any notebook or test.
- Good: an import line documents itself. `from economic_regime_forecasting.models.state_labelling
  import canonicalise` needs no glossary.
- Bad / accepted cost: import lines are long, and a few wrap. Legibility for a
  reader beats brevity for a typist.
- Bad / accepted cost: a departure from the brief's stated layout, which a reader
  comparing the two will notice. That is what this record is for.

## Options considered
- Follow the brief literally with `include/` — rejected: needs explaining, fights
  the packaging tools, and contradicts the structural ground truth the same brief
  points at.
- A flat module directory with short names — rejected: the naming rule is
  explicit, and the layering is what keeps the modules from becoming a junk drawer.
