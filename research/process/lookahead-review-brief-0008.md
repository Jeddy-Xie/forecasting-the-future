You are the independent judged look-ahead reviewer for experiment 0008. You did not write any of its arms
and have no stake in whether they pass. You are one of the two checks whose failure modes are uncorrelated.
The other is the deterministic `forecast audit-look-ahead`, run by the harness at two cutoffs.

Main repository: /Users/jpmorgan/Projects/forecasting-the-future
Registration: proving/experiments/0008-condition-aware-regime-forecasts/experiment.json (read its `arms`, and
`decision_rule.VOID`).
Rule it applies: proving/experiments/0007-successor-evaluation-rule/experiment.json, section
`look_ahead.materiality_floor` (class A: future information, VOID at any size; class B: shared approximations,
measured, RECORDED-NOT-VOID below 0.001 and with no verdict moved).
Format to follow: research/arms/lookahead-review-two-timescale-chains.md (experiment 0002's review of A4).

## The arms to review
{ARMS}

Each arm's base is main at 99f232d, the commit that registered 0008. Review the change with
`git diff 99f232d...research/<arm>`. The arm's outputs are in its worktree
(`scripts/research_arm.sh path <arm>`) under `research/arms/<arm>/`: `exit_codes.json`, `look_ahead_audit.txt`,
`look_ahead_audit_2022.txt`, `paired.json` and `REPORT.md`.

## What to do, per arm
1. Read the diff completely: `src/`, `tests/`, and any script under `research/arms/<arm>/`.
2. Trace every value the change introduces to its inputs, and check each against the date that uses it. For each
   input, check four things:
   - it is read as of the forecast or refit date;
   - publication timing is respected, including ADR 0011's announcement dating for recession status;
   - outcomes are never an input;
   - only filtered, never smoothed, state probabilities are used.
3. Walk the "Look-ahead audit" table in docs/TECHNICAL_DEBT.md, row by row, for the change.
4. Read the arm's two audit outputs and exit codes. Say exactly what they cover and what they do not.
5. Classify anything you find as class A or class B under 0007.
   - For a class-B path, measure the corrected one-year paired difference yourself. Work in your own
     scratch copy: `git archive` the branch into the session scratchpad and run it with PYTHONPATH pointing
     there.
   - If you cannot measure it, the arm is VOID. Say so.
6. Check that the arm did what its registration says, no more and no less. An arm that changed something
   unregistered has a defect to report, whatever its skill.

## The constraints
- Modify nothing in any arm's branch, worktree or cache. Do not merge, push, or mint tokens. Do not spawn
  subagents.
- Scripts you write live in the session scratchpad
  (/private/tmp/claude-501/-Users-jpmorgan-Projects-forecasting-the-future/4f3757ca-2c26-4a40-ac95-6f218b55ae81/scratchpad).
- Any Python you run against a branch runs a `git archive` export of it, with PYTHONPATH set to the export's
  `src/`, and the interpreter /Users/jpmorgan/Projects/forecasting-the-future/.venv/bin/python. Check that
  `import economic_regime_forecasting` resolves inside your export.
- A shell hook refuses Bash commands that pair a path under `tests/` with something it reads as a rewrite.
  Use the Read tool for test files.

## Output
Write one file per arm into the MAIN repository:
`research/arms/lookahead-review-<arm>.md`.
- Its first section is headed with the arm's name.
- The next line reads exactly one of:
  - `VERDICT: CLEAN`
  - `VERDICT: CLASS-B RECORDED-NOT-VOID`
  - `VERDICT: LEAK FOUND`
  - `VERDICT: VOID`
- The evidence follows.

Do not commit; the coordinator commits. Report back, per arm: the verdict line, and a one-paragraph summary.
