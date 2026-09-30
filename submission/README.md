# submission/

The only artifact that leaves this repository: `forecasts.csv`, a probability for each of ten
indicators at one, five and ten years, and `manifest.json`, which records the configuration that
produced it and the data it was produced from.

## What ships, and why

Re-shipped 2026-09-29 with the pipeline's default, the two-chain model `fec79a040f9ca6f9`, under the
frozen 2026-09-08 decision rule (experiment 0001), exactly as that rule computes today:

| horizon | 0001's verdict | what ships |
|---|---|---|
| 1 year | SHIP MODEL | the model's probability |
| 5 years | SHIP BASE RATE | the climatological base rate |
| 10 years | SHIP BASE RATE | the climatological base rate |

The previous submission, made 2026-09-09, came from `9f95b12dba40d138`, a configuration with two known
look-ahead paths (ADR 0008). The re-ship was a delegated decision (P1-9): claude-fable-5-1, delegated by
Jeddy Xie, recorded in `research/ledger/delegated-decisions/` and ADR 0012. It is not yet the owner's
own call, and nothing here is pushed until he confirms it.

## Read this before using the one-year rows

- **One-year rows ship the model under the frozen 2026-09-08 rule.**
- **A forecaster without regimes beats it.** On 2026-09-25 a review measured a regime-free two-rate
  condition chain beating this model at one year on the same sample. Reproduced from committed code:
  −0.0582, 98.33% interval [−0.1119, −0.0089].
- **Its recession skill is below zero against a fair benchmark.** Against a climatology restricted to
  the model's own sample, both recession indicators score below zero.
- **Measurement 0010.** The model carries skill only to about 29 months, and is never better than the
  chain at any horizon.
- **Registered forward.** This model and the single-chain model are registered forward beside this
  submission. The chain and the fair climatology join the register from the next monthly round.
- **The next re-ship is governed by rule 0007.** That rule judges skill against the fair benchmark,
  and requires the method not to be beaten by the chain. Under it, this model is expected to ship the
  base rate at one year too.
