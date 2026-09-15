You are implementing and running ONE research arm of a pre-registered experiment. You are the single
writer for your arm, and you work ONLY in your arm's git worktree. Several other arms run in parallel
in their own worktrees; never touch theirs, and never touch main's working tree.

Main repository: /Users/jpmorgan/Projects/forecasting-the-future
Your arm: {ARM}
Your worktree: run `/Users/jpmorgan/Projects/forecasting-the-future/scripts/research_arm.sh path {ARM}`

## Read first, in this order
1. `proving/experiments/0002-research-slate-2026-09/experiment.json` — find your arm under `arms`.
   Its `change` and `hyperparameters` are the whole specification. Implement EXACTLY that.
   Also read `decision_rule` and `stated_in_advance`: they say how your result will be judged.
2. `CLAUDE.md` — the rules that bind every session here. The first one is "No look-ahead, ever."
3. `docs/REGRESSION_TESTING.md` — how your run is compared against main.
4. `docs/TECHNICAL_DEBT.md`, the "Look-ahead audit" table — every path by which future information
   could reach a forecast. Your report must fill this table in for your change.

## The non-negotiables
- **Hyperparameters are fixed by the pre-registration.** Do not tune, sweep or adjust any of them,
  and do not "try a quick variant to see". One run, with the registered values. If you find a genuine
  bug after running, the fix may not change a hyperparameter, and you report BOTH runs.
- **No look-ahead.** Everything your change estimates at a date may use only data published by that
  date. Standardisation expands. Only filtered (never smoothed) state probabilities are used.
  Outcomes are used only once they had resolved and been published.
- **The worktree trap.** The package is an editable install pointing at MAIN's src/. Every Python
  command you run must set `PYTHONPATH=<your worktree>/src`, or you will silently run main's code and
  report it as yours. `research_arm.sh` asserts this for its own commands; you must do it for yours.
  Before each test or script run, check: `python -c "import economic_regime_forecasting as m; print(m.__file__)"`
  must print a path inside your worktree.
- Never edit anything under `proving/`, `submission/` or `forecasts/`. Never mint a thaw token.
  Never merge or push to main. Never delete or weaken an existing test; tests are additive only.
- Do not spawn subagents.
- **Crash-only.** Commit to your branch as you go, so an interruption leaves resumable work:
  commit the implementation and its tests BEFORE the long run, and commit the outputs after.

## Steps
1. `scripts/research_arm.sh setup {ARM}` (from the main repository root). This creates your
   worktree on branch `research/{ARM}`, copies main's cache in, and verifies isolation.
2. Implement the change in your worktree, behind a clearly named `RunSettings` field whose default ON
   YOUR BRANCH is the arm's behaviour. Names spelled out in full (project rule). Respect the layer
   order in the package docstring: `models/` may not import `data/`.
3. Add tests that pin the change, including any `required_check` your arm names in the
   pre-registration. Run the full suite with PYTHONPATH set: `pytest -m "not network"`, plus
   `ruff check .`, `ruff format --check .` and `mypy`, all clean. Commit.
4. `scripts/research_arm.sh run {ARM}` (from the main repository root). This runs the five gates in
   your worktree and compares against main, plain and paired. It takes minutes to tens of minutes.
   Outputs land in `<worktree>/research/arms/{ARM}/`.
5. Write `<worktree>/research/arms/{ARM}/REPORT.md`:
   - What changed, in plain words, with the file paths.
   - **Look-ahead audit**: the TECHNICAL_DEBT.md audit table, with each row stating whether your
     change touches it and why it is still clean. Be specific about dates.
   - **Results**: the one-year paired difference and its 90% interval (the primary endpoint), and the
     five- and ten-year ones; your arm's five-gate verdicts under 0001; calibration error and log loss
     against main; lambda2 if your change affects it. Quote the numbers from `paired.json` and
     `compare.json`; do not retype or round them into new values.
   - **Verdict under the pre-registered rule**: PROMISING, CONFIRMED_IN_SAMPLE, HARMFUL,
     or none. Show the arithmetic. The Bonferroni level is 98.33%. If the paired output does not
     carry a 98.33% interval, say so and do not claim CONFIRMED.
   - **Prediction versus outcome**: what the pre-registration predicted, and what happened.
   - Anything surprising, and anything you could not do.
6. Commit the outputs and the report to `research/{ARM}`.

## Report back
Branch and final commit hash; the one-year paired difference with its 90% interval; your verdict
under the rule; the check-gates exit code; and any deviation from the specification, with its reason.
If anything blocked you (a hook, a failing gate, a missing artifact), say exactly what, and stop
rather than working around it.

{ARM_SPECIFIC_NOTES}
