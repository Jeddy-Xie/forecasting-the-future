# 0013 · The default blends the regime model equally with the condition chain, and ships under rule 0007

**Status:** accepted 2026-09-29, by **delegated decision**. Jeddy Xie delegated this session's decisions to
claude-fable-5-1. Its pass-two decisions P2-1 to P2-10 are recorded verbatim, with their reasons, in
`research/ledger/delegated-decisions/2026-09-29-pass-2.json`. They are not the owner's adjudication, and he can
reverse any of them.

## Context

Experiment 0008 (`proving/experiments/0008-condition-aware-regime-forecasts/`, result in
`research/experiments-drafts/0008-condition-aware-regime-forecasts.RESULT.md`) was registered before any arm
ran. It tested three ways of keeping what regimes add while taking what the regime-free condition chain R2 has.
The control reproduced the reference exactly.

| arm | one year vs reference, model-sample | 96.67% | worst horizon | verdict | 0007 at one year |
|---|---:|---|---|---|---|
| B1, point-in-time through the joint chain | +0.0535 | [+0.0174, +0.0940] | none harmful | CONFIRMED_IN_SAMPLE | ship R1 (calibration slope 0.651 [0.465, 0.880]) |
| B2, observe unemployment and the term spread | −0.0088 | [−0.0515, +0.0340] | 10 years −0.1176 [−0.1623, −0.0496] | HARMFUL | ship R1 |
| B3, 50/50 blend with R2 | **+0.0615** | [+0.0341, +0.0961] | none harmful | CONFIRMED_IN_SAMPLE | **SHIP MODEL**, every gate |

- **Look-ahead.** The deterministic audit passed for all three arms at both cutoffs.
- **Independent review:** B1 and B3 CLASS-B RECORDED-NOT-VOID, B2 CLEAN.
- **The floor reading.** B1's review turned on how 0007's materiality floor is read. The floor now covers the
  paths a change opens (P2-9, a dated clarification in 0007).

## Decision

- **B3 is adopted alone** (P2-1).
  - `blend_the_model_equally_with_the_condition_chain` defaults to True, with the weight fixed at the constant
    0.5.
  - The default configuration is `7647c129be85291e`.
  - `fec79a040f9ca6f9` (the model alone) and `ad7fcc1affd0746a` (the single chain) still reproduce from their
    settings.
- **Accepted on merged main before anything shipped:**
  - `check-gates` exits 0;
  - the paired difference against `reference-0008` reproduces the arm's +0.0615 [+0.0403, +0.0875] and
    [+0.0341, +0.0961] to the digit;
  - the backtest frame, verdicts and metrics equal the arm's own run field for field;
  - the 34 fits are byte-identical to main's;
  - both look-ahead audits pass.
  - The adopted run is captured as `baselines/reference-adopted-blend`.
- **Shipped under rule 0007** (P2-2).
  - One year ships the blend: 0007 reads SHIP MODEL, skill against R1 +0.2401 [+0.1715, +0.3113], calibration
    slope 0.870 [0.603, 1.198].
  - Five and ten years ship R1, the model-sample climatology.
  - Under 0001 the same run reads SHIP MODEL at one year and the base rate at five and ten. Both verdicts are in
    the manifest.
  - `submit` became rule-driven for this. Its rule-0001 path reproduces the previous submission byte for byte.
- **The approved hash becomes `7647c129be85291e`.** This is the second re-ship of 2026-09-29, and it was
  expected: ADR 0012 said the next re-ship would be governed by 0007.
- **Registered forward.** The blend is registered forward from this round. The model alone, the single chain, R2
  and R1 are registered beside it as companions.

## Why B3, and not B1 or both

- **0007 decides what ships.** Only B3 passes every one-year gate.
- **B1's extra value inside the blend is too small to detect.** It is bounded by B1's pure regime effect, about
  +0.006 over all rows, a third of what this sample can detect. A combination run would read NOT SHOWN whether
  or not the effect is real, so none was registered.
- **B3 is the smaller change.** It is post-processing with a fixed weight, the model is untouched, and R2 was
  already a reference column.

## What this decision does not claim

- **The blend is not shown to beat the chain alone** at one year (−0.0077, 90% [−0.0284, +0.0116]), and the chain
  beats it at ten years. Most of the gain over the model is the chain's own advantage: persistence. Rule 0007
  fixed in advance that R2 reaches the submission only through a registered arm, and B3 is that arm.
- **Everything is in sample.** The arms were designed after this sample's per-indicator results were seen.
  CONFIRMED_IN_SAMPLE is the ceiling. The forward register, first resolving 2027-07-01, is the only
  out-of-sample test.
- **Two class-B approximations reach the chain half.** Revised condition values move it +0.0007, and the
  recession announcement boundary (D17) −0.0007. Both are scheduled for correction on 2026-10-06, and neither
  moves a verdict.

## Also decided

- **Experiment 0006 read STRUCTURE HELPS** (P2-3). The smaller 3x2 two-chain model matches the 4x4 default at
  one year on 27 parameters against 58. That is an unregistered point estimate, so nothing changes on it.
  Experiment 0011 will test the smaller model under the blend, registered before it runs, with the −0.02 harm
  floor as its non-inferiority margin.
- **B2 is closed** (P2-4). Unemployment is not re-tested as an observation. Two consequences are kept:
  - `submit` now refuses when today's fitted structure differs from the backtest's;
  - 0007 now computes R1 and R2 on the reference's sample start.
- **The calibration fallback stands for everything already registered under 0007** (P2-5). A sized test, whose
  critical value comes from a simulated null, is to be added by dated amendment before 0011 or 0009 registers.
- **D17 is recorded** (P2-8).

## Scheduled (P2-6)

| date | work |
|---|---|
| 2026-10-06 | the D5 as_of-threaded condition read and the D17 provisional recession coding, two commits, each measured against `reference-adopted-blend`, both audits at both cutoffs, then `baselines/reference-2026-10-06`; register 0011, run by 2026-10-09 |
| 2026-10-13 | register 0009, the CPIAUCNS sample extension, run by 2026-10-20 |
| 2026-10-21 | the pass-three decision brief |
| 2026-11-01 | the monthly round with every companion |

## Reverting

- **The default:** set the blend switch to False, recapture a baseline, and set the approved hash back to
  `fec79a040f9ca6f9` with a re-ship.
- **The register cannot be reverted.** The rows registered today are permanent by design, and will be scored
  as they resolve.
