You are implementing and running ONE research arm of a pre-registered experiment. You are the single
writer for your arm, and you work ONLY in your arm's git worktree. Other arms run in parallel in their
own worktrees; never touch theirs, and never touch main's working tree.

Main repository: /Users/jpmorgan/Projects/forecasting-the-future
Your arm: {ARM}   (branch research/{ARM})
Your experiment: {EXPERIMENT}
Your worktree: run `/Users/jpmorgan/Projects/forecasting-the-future/scripts/research_arm.sh path {ARM}`

## Read first, in this order
1. Your experiment's registration: {REGISTRATION}. Find your arm. Its `change`, `hyperparameters` and
   `required_checks` are the whole specification: implement EXACTLY that. Read `decision_rule` and
   `stated_in_advance` too; they say how your result will be judged.
2. `proving/experiments/0007-successor-evaluation-rule/experiment.json`: the rule every new claim is
   read by, including the two reference forecasters every backtest row now carries
   (`model_sample_climatology_probability`, `condition_chain_probability`).
3. `CLAUDE.md`: the rules that bind every session here. The first is "No look-ahead, ever."
4. `docs/REGRESSION_TESTING.md`: how your run is compared against the reference.
5. `docs/TECHNICAL_DEBT.md`, the "Look-ahead audit" table: every path by which future information could
   reach a forecast. Your report must fill it in for your change.

## The non-negotiables
- **Hyperparameters are fixed by the registration.** Do not tune, sweep or adjust any, and do not "try a
  quick variant to see". One scored run, with the registered values. If you find a genuine bug after
  running, the fix may not change a hyperparameter, and you report BOTH runs.
- **No look-ahead.** Everything your change estimates at a date may use only data published by that
  date. Standardisation expands. Only filtered (never smoothed) state probabilities are used. Outcomes
  are used only once they had resolved and been published.
- **The worktree trap.** The package is an editable install pointing at MAIN's src/. Every Python command
  you run must set `PYTHONPATH=<your worktree>/src`, or you will silently run main's code and report it as
  yours. Before each test or script run, check that
  `python -c "import economic_regime_forecasting as m; print(m.__file__)"` prints a path inside your
  worktree. Use the interpreter `/Users/jpmorgan/Projects/forecasting-the-future/.venv/bin/python`.
- **Settings, not literals.** Implement your change behind a clearly named `RunSettings` field whose
  default ON YOUR BRANCH is the arm's behaviour. Names spelled out in full (project rule). If the field's
  "off" value is the pre-existing behaviour, add it to `SETTINGS_OMITTED_FROM_THE_HASH_WHEN_THEY_HOLD_THE_SHIPPED_VALUE`
  so the reference's hash does not move. Respect the layer table in the package docstring; the suite
  enforces it.
- Never edit anything under `proving/`, `submission/`, `forecasts/` or `baselines/`. Never mint a thaw
  token. Never merge or push. Never delete or weaken an existing test; tests are additive only.
- Do not spawn subagents.
- **Crash-only.** Commit to your branch as you go: the implementation and its tests BEFORE the long run,
  the outputs after.
- A shell hook refuses any Bash command that names a path under `tests/` together with something it reads
  as a rewrite. Edit test files with the Edit or Write tools, and run tests with pytest.

## Steps
1. From the main repository root: `scripts/research_arm.sh setup {ARM}`. This creates your worktree on
   branch `research/{ARM}` from main, copies main's cache in, and verifies isolation. It may already
   exist; then it is reused.
2. Implement the change, with tests that pin it, including every `required_check` your arm names. Run the
   full suite with PYTHONPATH set (`pytest -m "not network" -q`), plus `ruff check .`,
   `ruff format --check .`, `mypy` and `python3 scripts/layer_check.py`, all clean. Commit.
3. Run any pre-registered diagnostic your arm names BEFORE the scored run, and commit its output.
4. The scored run, from the main repository root, with the experiment's parameters:
   `{HARNESS_ENVIRONMENT} scripts/research_arm.sh run {ARM}`
   It runs the five gates in your worktree, compares against the reference (plain, paired on the primary
   benchmark, paired on the series-start benchmark as a secondary), and runs the look-ahead audit at both
   cutoffs. The 2022-03-01 audit takes about thirty minutes. Outputs land in `<worktree>/research/arms/{ARM}/`.
   If the gates fail, it makes no comparison and writes NO_COMPARISON.txt: report that, do not work
   around it.
5. Write `<worktree>/research/arms/{ARM}/REPORT.md`:
   - What changed, in plain words, with the file paths.
   - **Look-ahead audit**: the TECHNICAL_DEBT.md audit table, each row stating whether your change touches
     it and why it is still clean. Be specific about dates.
   - **Results**: quote from `paired.json`, `paired_series_start.json` and `compare.json`; do not retype or
     round into new values. Give:
     - the one-year paired difference with its 90% and family-wise intervals (the primary endpoint);
     - the five- and ten-year differences;
     - your arm's 0001 verdicts per horizon;
     - per-indicator one-year differences.
   - **Verdict under the registered rule**: PROMISING, CONFIRMED_IN_SAMPLE, HARMFUL, INCONCLUSIVE or
     none. Show the arithmetic.
   - **Required checks and diagnostics**: each with its outcome.
   - **Prediction versus outcome**, and anything surprising or anything you could not do.
6. Commit the outputs and the report to `research/{ARM}`.

## Report back
- Branch and final commit hash.
- The one-year paired difference with its 90% and family-wise intervals.
- Your verdict under the rule, and each required check's outcome.
- The check-gates exit code and both audit exit codes.
- Any deviation from the specification, with its reason.

If anything blocked you (a hook, a failing gate, a missing artifact, a network refusal), say exactly what,
and stop rather than working around it.
