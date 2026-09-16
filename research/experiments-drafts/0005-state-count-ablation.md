# Diagnostic 0005 — is A4's gain the two timescales, or just sixteen states?

Committed 2026-09-16, BEFORE the ablation runs. This file's git timestamp is the evidence.

## Why
Arm A4 replaces main's one six-state chain with two four-state chains, sixteen joint regimes. Two
things changed at once, and briefing 04 (`research/briefings/04-factorial-regime-models.md`) says the
measured gain cannot be attributed to either alone:

- the **structure**: growth on its own chain, inflation and rates on another, so each runs at its own
  persistence;
- the **granularity**: conditional base rates cut on sixteen cells instead of six, with effective
  sample per regime falling from about 112 months to about 45, and free parameters from 89 to 58.

The one-year gain landed on the at-horizon questions (+0.0884) rather than the any-time ones
(+0.0297), which is the opposite of the arm's stated hypothesis. That is what makes the confound worth
one run rather than an argument.

## What changes
One setting on a branch cut from `main`: `hidden_state_counts_to_search = (16,)`, so the burn-in sweep
can only choose sixteen states for main's SINGLE full-covariance chain. Nothing else: same seed, same
schedule, same panels, same decision rule, same audit. Main at sixteen states carries 399 free
parameters against A4's 58, which is the point of the comparison.

## How it will be read, fixed now
Let d16 be main-at-sixteen minus main-at-six on the one-year paired Brier skill difference, and let
A4's registered result be +0.0590, 90% [+0.0275, +0.0877].

- **STATE-COUNT EFFECT** if d16's one-year 90% lower bound is above zero AND its point estimate is at
  least half of A4's (+0.0295). The "two clocks" account is then not supported: most of what A4 buys
  is available from more regimes alone, and the recommendation for adoption must say so.
- **STRUCTURE EFFECT** if d16's one-year 90% interval includes zero, or its point estimate is below
  half of A4's. The factorisation is then doing the work, not the granularity, and A4's account stands.
- **INCONCLUSIVE** if the sixteen-state fit fails to converge, or any of the five gates fails, or the
  look-ahead audit exits non-zero. A model that cannot be fitted is not evidence either way, and this
  outcome is itself worth reporting: it would mean sixteen unrestricted regimes are unreachable on this
  sample, which is the factorisation's practical argument.

In every case, report d16 beside A4's number at all three horizons, with the effective sample per
regime and the free-parameter count for each.

## What this is NOT
- It does not change A4's registered verdict under experiment 0002. That verdict is decided by 0002's
  rule and its look-ahead review, both closed.
- It is not a new candidate for adoption. Main at sixteen states is a diagnostic, not a proposal.
