# Experiment 0008 — RESULT

Registered 2026-09-29 at `99f232d` (`proving/experiments/0008-condition-aware-regime-forecasts/`), before any arm
ran; judged by rule 0007.
- **Reference:** `baselines/reference-0008`, the two-chain default `fec79a040f9ca6f9`. It passed the deterministic
  look-ahead audit at both cutoffs before any arm was read.
- **How each arm ran:** once, in its own worktree, through `scripts/research_arm.sh` with
  `RESEARCH_ARM_REFERENCE=reference-0008 RESEARCH_ARM_BENCHMARK=model-sample RESEARCH_ARM_FAMILY_LEVEL=0.9667`.
- **Reports:** each arm agent's REPORT.md was refused by the session harness. The coordinator committed each
  one verbatim to its branch after checking the numbers against the arm's `paired.json` and `exit_codes.json`.

## The slate

| arm | branch head | one year, model-sample | 90% | 96.67% | harm guard | look-ahead review | verdict |
|---|---|---:|---|---|---|---|---|
| CONTROL | `8cab4bf` | 0.0000 | [0.0000, 0.0000] | [0.0000, 0.0000] | exact zero at every horizon, both benchmarks | not needed | **passes**; the slate is valid |
| B1, point-in-time through the regime × condition chain | `65afa32` | **+0.0535** | [+0.0259, +0.0857] | [+0.0174, +0.0940] | none below −0.02 | CLASS-B RECORDED-NOT-VOID (corrected +0.0530, shift −0.0005; read as covering only the paths a change opens, P2-9) | **CONFIRMED_IN_SAMPLE** |
| B2, observe unemployment and the term spread | `2433c5f` | −0.0088 | [−0.0414, +0.0250] | [−0.0515, +0.0340] | **10 years −0.1176 [−0.1623, −0.0496]** | CLEAN | **HARMFUL** |
| B3, 50/50 blend of the model with R2 | `a92a700` | **+0.0615** | [+0.0403, +0.0875] | [+0.0341, +0.0961] | none below −0.02 | CLASS-B RECORDED-NOT-VOID (corrected +0.0615, shift +0.00003) | **CONFIRMED_IN_SAMPLE** |

All three arms' deterministic audits exited 0 at 2000-03-01 and at 2022-03-01, and every run's tree was clean
from start to end.

## What else was measured

**Against the regime-free chain R2** (0007's "regimes help", one year, model-sample):

| run | minus R2 | 90% | reading |
|---|---:|---|---|
| reference | −0.0691 | [−0.1148, −0.0292] | REGIMES DO NOT HELP |
| B1 | −0.0157 | [−0.0550, +0.0273] | NOT SHOWN |
| B3 | −0.0077 | [−0.0284, +0.0116] | NOT SHOWN |
| B2 | −0.0824 | [−0.1348, −0.0316] | REGIMES DO NOT HELP |

At ten years R2 still beats B1 and B3.

**Rule 0007's full verdict at one year**, computed with main's code on each arm's backtest:

| run | 0007 verdict | why |
|---|---|---|
| B3 | **SHIP MODEL** | Every gate passes. Skill against R1 +0.2401 [+0.1715, +0.3113], calibration slope 0.870 [0.603, 1.198], robustness 4 of 4, chain gate passes. |
| B1 | ship R1 | Fails calibration only: slope 0.651 [0.465, 0.880]. |
| the reference | ship R1 | Fails calibration and the chain. |
| B2 | ship R1 | Fails calibration and the chain. |

**B1's registered secondaries.**
- Cadence effect: −0.0035 [−0.0062, −0.0008], as P1-11 predicted, about −0.004.
- Pure regime effect on point-in-time rows: +0.0118 [−0.0242, +0.0528]. Most of B1's gain is persistence, not
  regimes.

## Prediction versus outcome

| stated in advance | outcome |
|---|---|
| control passes (0.97) | passed |
| B3 PROMISING or better (0.55) | CONFIRMED_IN_SAMPLE |
| B1 PROMISING (0.45) | CONFIRMED_IN_SAMPLE, and larger than the +0.03 predicted |
| B2 no verdict (0.6) or HARMFUL (0.15) | HARMFUL |

## What it means

- **Taking persistence into the forecast is what pays.** B1 does it inside the model, B3 by blending in the
  chain. Both clear the family-wise bar, and neither is distinguishable from the chain alone at one year.
- **Observing the forecast variables directly did not help.** B2 helped the unemployment questions, but cost
  inflation and rates, and did harm at ten years.
- **All of this is in sample.** Every arm was designed after the review's per-indicator results were seen.
  CONFIRMED_IN_SAMPLE is the ceiling, and forward registration is the only out-of-sample test.

## Adoption

By delegated decision P2-1 (claude-fable-5-1, delegated by Jeddy Xie), **B3 is adopted alone**. Merged at
`025ffe2`, it is the default configuration `7647c129be85291e`.
- **Acceptance on merged main:**
  - the gates pass;
  - the paired difference against reference-0008 reproduces the arm to the digit;
  - the backtest frame, verdicts and metrics equal the arm's own run;
  - the 34 fits are byte-identical to main's.
- **Why B3.** It is the only run that 0007 reads as SHIP MODEL at one year: every gate passes, with a
  calibration slope of 0.870 [0.603, 1.198].
- **B1 is confirmed but not adopted.** It fails 0007's calibration gate (slope 0.651 [0.465, 0.880]) and
  stays a validated candidate on its branch. Its extra value inside the blend is bounded by its pure regime
  effect, about +0.006 over all rows, below what this sample can detect, so no combination was registered.
- **B2 is closed as a negative finding.** Unemployment's information turned out to live in the condition
  chain, not in the regime state space.
- **B1's review verdict rests on a reading.** P2-9 reads 0007's floor as covering only the paths a change
  opens. Under the wider reading B1 would be void by about 0.0001. That reading is recorded in 0007 as a
  dated clarification.

The blend is **not shown to beat the chain alone** at one year (−0.0077, 90% [−0.0284, +0.0116]), and the
chain beats it at ten. That is stated wherever the blend ships.
