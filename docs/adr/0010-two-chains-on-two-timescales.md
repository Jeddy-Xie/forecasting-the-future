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

Measured after the merge, as main's own pipeline, against the committed single-chain
baseline `ad7fcc1affd0746a`, which was deliberately NOT recaptured so the comparison
has a fixed anchor:

| horizon | baseline skill | this run | difference | 90% | 98.33% |
|---|---|---|---|---|---|
| 1 year | +0.2154 | +0.2744 | **+0.0590** | [+0.0275, +0.0877] | [+0.0147, +0.1019] |
| 5 years | +0.0728 | +0.1192 | +0.0465 | [+0.0249, +0.0953] | [+0.0132, +0.1295] |
| 10 years | −0.3528 | −0.1673 | +0.1855 | [+0.0843, +0.2228] | [+0.0700, +0.3834] |

These reproduce arm A4's figures to the digit, which is the point: the arm and the
adopted default are the same computation. 281 of 387 compared fields moved, 106 are
identical, and five moved categorically:

- the one-year verdict, **SHIP BASE RATE → SHIP MODEL**, because its failing gate goes
  from `calibration` to `none`;
- the ten-year failing gates lose `robustness`, keeping skill, calibration and honesty;
- the run's identity, `ad7fcc1affd0746a` → `fec79a040f9ca6f9`, at 6 → 16 regimes.

All five gates pass (`check-gates` exit 0), and the state count reaches the backtest
through the single shared function D15 introduced, so the look-ahead audit asks the
same question the backtest does.

- The default configuration hash becomes `fec79a040f9ca6f9`. Main's previous default
  `ad7fcc1affd0746a` and the shipped `9f95b12dba40d138` both still reproduce from the
  settings that produced them, so every result already on the record stays correctly
  labelled.
- `submission/forecasts.csv` and its manifest are NOT regenerated. Adoption changes
  what the pipeline computes; publishing that is a separate decision and still needs
  the owner's shipping token.
- Reverting is a branch revert plus a baseline recapture. Nothing outside `.cache/`
  and the committed baseline depends on the new default.

## Measured again, 2026-09-29

The +0.0590 above is a **pre-D14** comparison: both runs predate ADR 0011. D14 then moved the default's
one-year skill by −0.0071, while `baselines/main.json` was deliberately left pre-D14. So
`forecast baseline compare --against main --paired` on current code reads +0.0519: the adoption gain
with D14's shift folded in. Read that way, the number is misleading.

Measured on the same code, against the single chain re-run on current code
(`baselines/main-single-chain-d14`, captured for experiment 0006), the gain holds:

| horizon | series-start benchmark | 90% | 98.33% | model-sample benchmark (R1) |
|---|---:|---|---|---:|
| 1 year | **+0.0588** | [+0.0272, +0.0875] | [+0.0146, +0.1017] | +0.0646 |
| 5 years | +0.0457 | [+0.0239, +0.0934] | [+0.0122, +0.1265] | +0.0517 |
| 10 years | +0.1826 | [+0.0780, +0.2197] | [+0.0634, +0.3438] | +0.1886 |

Two caveats this record should have carried from the start:

- **Four by four sits at the top of its candidate range.** Each chain was swept over one to four
  states, and both chose four. That is the same boundary caveat ADR 0008 raised for the single chain's
  six of one to six: the range may be binding. It is deliberately not widened. A third configuration
  change would confound experiment 0006, which holds the joint count at six.
- **The adoption does not make the model better than a forecaster without regimes.**
  - The regime-free condition chain (ADR 0012) beats this model at one year by 0.0582.
  - The model is never better than the chain at any horizon from one month to ten years
    (measurement 0010).
  - What was adopted is a measured gain over the single chain, which the chain beats by more.

The delegated adjudication of the stress test (claude-fable-5-1, delegated by Jeddy Xie, 2026-09-29):
**adopted, provisionally**, classified FACTUAL. The falsifier's forward rule is applied at 2027-07-01,
2028-07-01 and 2029-07-01 to two chains against one, both now registered forward.

