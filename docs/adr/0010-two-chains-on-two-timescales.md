# 0010 · Two chains on two timescales replace the single regime chain

**Status** accepted, 2026-09-20. Supersedes the modelling decision in ADR 0004,
which stands as the record of the single-chain model it replaces.

## Context

ADR 0004 chose one hand-rolled Gaussian hidden Markov chain over growth, inflation
and rates. Measured on the point-in-time panels, that chain runs on the slow
timescale: its second eigenvalue is about 0.98, matching published volatility and
level chains rather than growth chains, while output growth fitted alone runs about
three times faster. One chain serving all three columns is pulled onto the slower
clock, and the faster signal is averaged away.

Experiment 0002 tested six pre-registered ideas against that chain, with the
decision rule, both confidence levels and a Bonferroni correction across the family
committed before any arm ran. Arm A4 gave each block its own chain.

## Decision

Two independent chains replace one. A growth chain drives the growth column; a
levels chain drives inflation and rates. The joint regime is the pair, so the joint
transition matrix is the Kronecker product, the joint emission log density is the
sum of the two blocks', and the fit is exact expectation maximisation because the
complete-data likelihood separates by chain. Sixteen joint regimes, chosen as four
by four on a burn-in window ending before the first scored forecast date.

## Why this one

- **It is the only arm that cleared the registered bar.** One-year paired difference
  +0.0590 in mean Brier skill score, 98.33% interval [+0.0147, +0.1019], against a
  rule that predates the data. Nine of ten indicators improve at one year and all
  ten improve on calibration.
- **Its independent look-ahead review is clean**, and the deterministic audit exits 0
  having fitted the arm's own sixteen regimes.
- **It is not a lucky seed.** Two further seeds, fixed before they ran, reproduce it:
  one-year lower bounds +0.0299 and +0.0296, both choosing four by four.
- **It costs less, not more.** Sixteen regimes on 58 free parameters, against six on
  89. An unrestricted sixteen-state chain would need 399, and main's own
  regimes-exist gate rejects one as too short-lived and too small to be regimes at
  all (diagnostic 0005).

## What this decision does not claim

- **The mechanism is not established.** Structure and regime count changed together,
  and the one-year gain landed on the at-horizon questions (+0.0884) rather than the
  any-time ones (+0.0297), the opposite of the arm's own hypothesis. The ablation
  that would separate them cannot be fitted on this sample. What is adopted is a
  measured forecasting difference, not the two-clocks story.
- **"Confirmed in sample" is the ceiling.** Every candidate was designed by someone
  who had already seen the incumbent's results. Only forward-registered forecasts,
  scored as they resolve, can test it out of sample, and matching the backtest's
  power that way runs to roughly the mid-2050s.
- **A dependence is discarded.** Within each joint regime the model assumes growth is
  uncorrelated with inflation and rates. Measured, that dependence runs at roughly
  half to two thirds of the one the model keeps
  (`research/briefings/derivations/within_state_cross_block_correlation.py`).

  An earlier draft of this record named *coupling the chains* as the extension this
  argues for. That was wrong, and briefing 05 shows why: the discarded dependence is
  contemporaneous, living in the emission covariance, while coupling the chains changes
  the transition structure and leaves the covariance block-diagonal. It cannot reach the
  quantity the correlation measures. The extension this actually argues for is a
  cross-block covariance term; coupling is a separate proposal with a separate claim,
  and briefing 05 finds that one underpowered on this sample.

- **The confound now has evidence, and it points away from the two-clocks story.** A4's
  own burn-in sweep prices every cell of the joint table. At matched cell count -- two
  growth states by three levels states, six joint cells against main's six -- the
  factorial structure is 0.0225 nats per month WORSE than the single chain, while going
  from six cells to sixteen buys +1.114. Decomposed, 74% of the gain comes from the
  levels block and 26% from growth, where the arm's hypothesis was that growth needed
  its own chain. This does not overturn the measured forecasting difference, which is
  what was adopted, but anyone reading this record should expect the mechanism to be
  granularity rather than timescale separation until an admissible-K ablation says
  otherwise.

## Consequences

- The default configuration hash becomes `fec79a040f9ca6f9`. Main's previous default
  `ad7fcc1affd0746a` and the shipped `9f95b12dba40d138` both still reproduce from the
  settings that produced them, so every result already on the record stays correctly
  labelled.
- `submission/forecasts.csv` and its manifest are NOT regenerated. Adoption changes
  what the pipeline computes; publishing that is a separate decision and still needs
  the owner's shipping token.
- Reverting is a branch revert plus a baseline recapture. Nothing outside `.cache/`
  and the committed baseline depends on the new default.
