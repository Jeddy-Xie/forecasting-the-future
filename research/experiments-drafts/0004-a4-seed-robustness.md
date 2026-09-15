# Diagnostic 0004 — is arm A4's result robust to its random seed?

Committed 2026-09-15, BEFORE either variant ran. This file's git timestamp is the evidence.

## Why
Arm A4 (two-timescale chains) is the only experiment-0002 arm that clears the bar. Its one-year paired
98.33% interval is entirely above zero: CONFIRMED_IN_SAMPLE on its own arithmetic, pending the
independent look-ahead review. Its fits are expectation maximisation over 16 joint states from random
initialisations, so one lucky local optimum could produce a result of this size. If the result is real,
other seeds should reproduce it.

## What this is NOT
- It is not a re-run of A4. Experiment 0002's one-run rule stands, and nothing here can change A4's
  registered verdict. That verdict is decided by 0002's rule and by its look-ahead review.
- It changes only how strongly the consolidated report may state A4's result, and whether A4 can be
  recommended as the systematic method.

## What changes
Only `RunSettings.random_seed`, in two branches cut from `research/two-timescale-chains` with no other
code change: 20260909 and 20260910, the next two integers after the registered 20260908. They were
chosen mechanically, before any variant ran. The seed drives every fit's initialisation (and the
burn-in state-count sweep, so each chain's state count may legitimately differ). It also seeds the
paired bootstrap's resampling, which leaves the point estimate unchanged and moves the intervals only
by resampling noise.

## How it will be read, fixed now
- **ROBUST TO INITIALISATION** if, for BOTH variant seeds, the one-year paired 90% interval against main
  has its lower bound above zero.
- **SEED-DEPENDENT** if either variant's one-year 90% lower bound is at or below zero. A4 would then not
  be recommended as the systematic method without further work, whatever its registered verdict.
- In either case, report both variants' one-year point estimates and intervals beside the registered
  seed's, and each variant's chosen state count per chain.
- The same look-ahead audit applies. A variant whose audit exits non-zero is void.
