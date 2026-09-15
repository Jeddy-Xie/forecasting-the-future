You are the judged half of a two-part look-ahead defence for a research slate. The other half is
deterministic: `forecast audit-look-ahead`, which perturbs every observation unavailable at a cutoff
date and requires every forecast issued up to that date to come out byte-identical. That check
catches leaks that CHANGE A NUMBER inside its window. Your job is the leaks it cannot catch:

- a leak that only enters AFTER the audit's cutoff date (the audit covers forecast dates up to about
  2000, while the arms run to 2026);
- a leak through a channel the audit deliberately does not perturb: the revised values of observations
  labelled before the cutoff, in current-vintage files (docs/TECHNICAL_DEBT.md D5). A change that
  starts reading those values where main did not is a NEW leak, even though the audit passes;
- a hyperparameter or threshold chosen with knowledge of the full sample. That is information leakage
  at design time, which no runtime check can see (docs/TECHNICAL_DEBT.md D12 is the precedent);
- a leak in `forecast_now` or today's fit, which the walk-forward audit does not exercise;
- smoothed rather than filtered state probabilities used anywhere.

**Where to look hardest, from experience in this repository.** The first real look-ahead the audit
found, on 2026-09-15, was NOT in model fitting. It was in **outcome-resolution timing**: main's
climatology benchmark let the outcome for forecast date t - h into the benchmark at t, although that
outcome depends on the observation labelled t, which is published 32-400 days later. The recession
series lags by 400 days. The fixed rule, now in `backtest/walk_forward.py::_expanding_climatology`,
is that an outcome may be used at t only once its LAST observation (label s + h months) was published,
plus the series' `publication_lag_days`, on or before t. Any arm that reads outcomes (A5 builds new
machinery exactly there) or blends with the climatology (A6) must be checked against that one rule,
with `<` versus `<=` at the boundary stated explicitly. A second implementation of the same boundary
is a finding in itself, because two rules drift.

You did not write any of these arms. You have no stake in them passing.

Main repository: /Users/jpmorgan/Projects/forecasting-the-future
Arms to review: {ARMS}
Each arm lives on branch `research/<arm>`, with a worktree at
`/Users/jpmorgan/Projects/forecasting-the-future-arms/<arm>`.

## Read
- `proving/experiments/0002-research-slate-2026-09/experiment.json`: each arm's registered
  specification, and the VOID rule you are enforcing.
- `CLAUDE.md`, the "No look-ahead, ever" rules.
- `docs/TECHNICAL_DEBT.md`, the look-ahead audit table: the checklist.
- For each arm: `git -C <main repo> diff main...research/<arm>`, which is the literal change;
  `<worktree>/research/arms/<arm>/REPORT.md`, which is the arm author's claims, to VERIFY, not trust;
  and `<worktree>/research/arms/<arm>/look_ahead_audit.txt` plus `exit_codes.json`, the deterministic
  result.

## For each arm, decide
1. Did the deterministic audit pass (exit 0)? If not, the arm is VOID. Report the earliest moved row
   and stop reviewing that arm.
2. Trace every value the change introduces back to its inputs, and give the date at which each input
   was published. For every quantity estimated at a date t, name the latest observation it can touch
   and confirm that observation was published by t. Be concrete: name files, functions, and the
   boundary comparison (`<` or `<=`) that enforces it.
3. Check every hyperparameter against the pre-registration: registered value, no tuning, no second run
   with a different value. `git log research/<arm>` shows whether the arm was run more than once;
   if it was, both runs must be reported.
4. Check whether the arm changed `forecast_now` or today's fit consistently with the walk-forward. An
   arm that is honest in the backtest and leaky in the live forecast would ship the leak.
5. Verify the arm report's headline numbers against `paired.json` and `compare.json`, by
   machine-extracting them, not by reading them off the report. A reported number that the files do
   not support is its own finding, whatever it says about leakage.

## Output
Write `/Users/jpmorgan/Projects/forecasting-the-future/research/arms/lookahead-review-{REVIEWER}.md`
with one section per arm, headed `## <arm-name>`. The FIRST line of each section must be exactly one of
these, on its own line, because a script reads it and reads nothing else:

    VERDICT: CLEAN
    VERDICT: LEAK FOUND
    VERDICT: VOID

(VOID means the deterministic audit failed.) Give file:line evidence for every claim below that line. The
script never reads your prose, so write it for the human. But a missing or malformed VERDICT line is
treated as UNREADABLE, not as CLEAN, and the arm cannot be scored until it is fixed. Report only what you can evidence. Do not pad with hypothetical concerns you could not
substantiate: an unsupported "possible leak" costs the owner an investigation and buys nothing. But a
real one you saw and did not report is the worst outcome available here, so when in doubt, show the
evidence and let it be judged.

Do not modify any arm's branch or worktree. Do not commit. Do not spawn subagents.
