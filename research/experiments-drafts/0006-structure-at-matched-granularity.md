# Experiment 0006 — is it the two chains, or just more cells?

Registered 2026-09-20, BEFORE anything runs. This file's git timestamp is the evidence.

## Why this, and why now

ADR 0010 adopted the two-chain model on a measured forecasting difference and said plainly that the
mechanism is not established: the structure and the regime count changed together. Briefing 05 then
priced every proposal on the table and found this the only one whose contrast clears what this sample
can resolve. It also found evidence already on disk that points away from the arm's own hypothesis:
in A4's burn-in sweep, at six joint cells against main's six, the factorial structure scores 0.0225
nats per month WORSE than the single chain, while going from six cells to sixteen buys +1.114. Of the
gain, 74% comes from the levels block and 26% from growth — where the hypothesis was that growth
needed its own chain.

So the adopted method may be earning its difference from granularity rather than from separating
timescales. That is worth knowing before anything is built on the timescale story.

## What changes

One branch from `main`, restricting the two-chain sweep to candidate pairs whose product is six, so
the joint state space matches main's single six-state chain exactly. The sweep's own rule chooses
between the admissible pairs, as it always does. Nothing else moves: same seed, same schedule, same
panels, same decision rule, same audit.

Granularity is therefore held fixed and only the structure varies, which is the comparison neither
0002 nor diagnostic 0005 could make — 0005 failed because sixteen unrestricted regimes cannot be
fitted at all on this sample.

## How it will be read, fixed now

Let d6 be the one-year paired difference, this configuration minus main's single six-state chain, on
the committed baseline `ad7fcc1affd0746a`.

- **STRUCTURE HELPS** if d6's one-year 90% interval lies entirely above zero. Giving growth its own
  chain then buys something at matched granularity, and the timescale account survives.
- **GRANULARITY, NOT STRUCTURE** if that interval includes zero or lies below it. The adopted method's
  gain is then better explained by sixteen cells than by two clocks, and ADR 0010's caveat becomes its
  headline. Briefing 05's matched-cell arithmetic predicts this outcome; registering the rule before
  the run is what makes that prediction a risk rather than a story told afterwards.
- **INCONCLUSIVE** if any of the five gates fails, or the look-ahead audit exits non-zero. A
  configuration that cannot be fitted or audited is not evidence either way, and saying so is itself
  a result — it is what 0005 returned.

Report d6 at all three horizons beside A4's registered numbers, with the effective sample per regime
and the free-parameter count for each.

## The anchor, and a condition on it

`baselines/main.json` still holds `ad7fcc1affd0746a`, the single-chain configuration, and was
deliberately not recaptured when the two-chain model was adopted. That is what keeps both A4's
+0.0590 and this experiment's d6 comparable to the same fixed point. **If the baseline is ever
recaptured under the new default, this rule must be rewritten before the run, not after.**

## What this does not do

- It does not revisit A4's adoption. That was decided by experiment 0002's rule and recorded in ADR
  0010, and this experiment cannot move it.
- It is not a proposal to ship anything. Whatever it returns, the outcome is a sentence in ADR 0010
  and an entry in the impact ledger.
