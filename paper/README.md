# The paper

*When to Ship the Historical Average: A Pre-Registered, Point-in-Time Test of Regime-Based Probability
Forecasts for the US Economy.* An arXiv-style write-up of the project for readers without an economics
background: the method, the results, and every table behind them.

| file | what it is |
|---|---|
| `main.tex` | the paper |
| `main.pdf` | the typeset paper, rebuilt by `scripts/build_paper.sh` |
| `references.bib` | the bibliography; every entry was checked against its publisher's record on 2026-09-29 |
| `generated/` | figures, tables and named numbers, written by `forecast paper-assets`. Never edit by hand |

## Where every number comes from

- **Figures, tables and named numbers** (`\BlendHorizon`, `\BlendSkillOneYear` and the rest in
  `generated/numbers.tex`) are computed by `forecast paper-assets` from committed records:
  - the blend's and the regime model alone's baselines (`baselines/reference-adopted-blend`,
    `baselines/reference-0008`);
  - measurement 0010's tables (`research/reports/skill-at-every-horizon/`);
  - the submission (`submission/`).

  The regime figure and the regime table also read the cached backtest, whose configuration hash
  must be the approved one.
- **Every other decimal in `main.tex`** must appear in a committed record at the precision printed.
  `tests/test_research_paper.py` checks this on every run of the suite. Arithmetic done in the text
  (the worked Brier examples) is marked `\derived{...}` and skipped.
- **The generated files are checked too.** The same test rebuilds every table and named number that
  needs only committed records, and fails if `generated/` is stale.

## Build

```bash
poetry run forecast check-gates   # once, so the cached backtest exists
./scripts/build_paper.sh          # regenerates generated/ and typesets main.pdf
```

The build needs `tectonic` (`brew install tectonic`). Any TeX Live 2023+ `pdflatex` plus `bibtex`
also works.

## Submitting to arXiv

- **Upload** `main.tex`, `references.bib`, a `main.bbl`, and `generated/`.
- **Getting `main.bbl`.** Make it with `tectonic -X compile --keep-intermediates main.tex`; arXiv
  requires the `.bbl` to carry the main file's name.
- **The abstract** is 1,224 characters, under arXiv's 1,920 limit.

Before submitting, the author should confirm two things:
- the competing-interests and funding statements, which are marked `% CONFIRM` in `main.tex`;
- that the repository link on the first page resolves to a public copy containing these commits.
