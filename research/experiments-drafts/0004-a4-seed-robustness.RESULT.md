# Diagnostic 0004: result

The reading rule was committed in `1a08ffb` (`0004-a4-seed-robustness.md`), before either variant ran.
This file is written by code from each run's `paired.json` and `exit_codes.json`, and it leaves the
rule's file untouched.

**Reading: ROBUST TO INITIALISATION.** Both variant seeds keep the one-year 90% lower bound above zero
(+0.0299 and +0.0296). Both audits exited 0, and each worktree matches the commit its run
names. This does not change A4's registered verdict, which 0002's rule and its look-ahead review decide.

| seed | commit | audit exit | 1 year: arm − main, 90% | 5 years | 10 years |
|---|---|---|---|---|---|
| 20260908 (registered) | `f5cbe91` | 0 | +0.0590 [+0.0275, +0.0877] | +0.0465 [+0.0249, +0.0953] | +0.1855 [+0.0843, +0.2228] |
| 20260909 | `837a9ea` | 0 | +0.0603 [+0.0299, +0.0874] | +0.0439 [+0.0234, +0.0990] | +0.1806 [+0.0724, +0.2336] |
| 20260910 | `8e80673` | 0 | +0.0603 [+0.0296, +0.0881] | +0.0420 [+0.0187, +0.0923] | +0.1940 [+0.0747, +0.2244] |

Each chain chose 4 states for every seed (growth × inflation-and-rates = 4 × 4), per each run's
`check_gates.log`.
