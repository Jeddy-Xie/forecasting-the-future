# submission/

The only artifact that leaves this repository:
- `forecasts.csv`: a probability for each of ten indicators at one, five and ten years, with every number it was
  made from beside it;
- `manifest.json`: the configuration that produced it, the data date, and the rule it was shipped under.

## What ships, and under which rule

Shipped 2026-09-29 under **rule 0007**, the successor to the frozen 2026-09-08 rule, by delegated decision P2-2
(claude-fable-5-1, delegated by Jeddy Xie; ADR 0013). This is not the owner's own approval, and nothing here is
pushed until he confirms.

| horizon | what ships | source column |
|---|---|---|
| 1 year | an equal-weight blend of the two-chain regime model and a regime-free two-rate chain on each indicator's own condition | `blend of regime model and condition chain` |
| 5 years | the base rate over the model's own sample (R1) | `base rate (model-sample climatology, R1)` |
| 10 years | the same | the same |

Each row also carries:
- the regime model's probability and the chain's;
- both base rates (R1, and 0001's series-start climatology);
- both rules' verdicts.

## Read this before using the numbers

- **The one-year blend comes from experiment 0008's arm B3.**
  - It was CONFIRMED_IN_SAMPLE: +0.0615 over the model at one year, 96.67% [+0.0341, +0.0961].
  - Every 0007 gate passes at one year.
- **Five and ten years ship R1** because the blend fails 0007's skill gate there.
- **The blend is not shown to beat the chain alone** at one year (−0.0077, 90% [−0.0284, +0.0116]), and the chain
  beats it at ten years.
- **Everything is in sample.**
  - The arm was designed after this sample's results were seen.
  - The forward register, first resolving 2027-07-01, is the only out-of-sample test.
- **Under the frozen 0001** the same run reads SHIP MODEL at one year and the base rate at five and ten. Both
  rules' verdicts are in the manifest.
- **Two small class-B approximations reach the chain half.** Both are scheduled for correction on 2026-10-06,
  and neither moves a verdict:
  - revised condition values, +0.0007;
  - the recession announcement boundary, −0.0007.

## History

| dates | configuration | rule | note |
|---|---|---|---|
| until 2026-09-29 | `9f95b12dba40d138` | 0001 | carried two look-ahead paths, closed by ADR 0008 |
| 2026-09-29, first re-ship | `fec79a040f9ca6f9` | 0001 | the two-chain model alone (ADR 0012) |
| 2026-09-29, second re-ship | `7647c129be85291e` | 0007 | the blend, after experiment 0008 reported |

All three are on the forward register and are scored as they resolve.
