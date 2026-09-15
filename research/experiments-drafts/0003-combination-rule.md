# Experiment 0003 — the combination: rule drafted BEFORE any 0002 arm has reported

Drafted 2026-09-15, while every 0002 arm is still implementing and none has produced a number. The
point of writing it now is that the rule for turning qualifying arms into ONE combined configuration is
fixed before anyone knows which arms qualify. Which arms qualify does depend on 0002's results, so 0003
is a POST-SELECTION experiment and is labelled so everywhere. But the step from "these arms qualified"
to "this is the combination" has no discretion left in it.

This draft becomes `proving/experiments/0003-*/experiment.json` through a single-use thaw after 0002
reports and before the combination runs. The only thing filled in then is WHICH arms qualified, by the
eligibility rule below, as computed by `score_slate.py`.

## Eligibility, computed by code from 0002's scored output

An arm is ELIGIBLE for combination if and only if every one of these holds:
- its 0002 verdict is PROMISING or CONFIRMED_IN_SAMPLE;
- it is not HARMFUL at any horizon;
- it is not VOID, either by the deterministic audit or by the judged review;
- its look-ahead review is exactly `VERDICT: CLEAN`, never PENDING or UNREADABLE.

No arm may be added because it "nearly" qualified. No eligible arm may be left out because the
combination "looks better" without it.

## The arms fall into two kinds, and the kind decides how they combine

| kind | arms | why |
|---|---|---|
| **stackable layers**: each changes a different stage, so any subset composes | A1 (the transition prior, in fitting), A5 (per-horizon rates, in composition), A6 (the fixed climatology blend, in post-processing) | they touch disjoint code paths |
| **exclusive structures**: each REPLACES the state space, so at most one can be used | A2 (quadrant levels), A3 (quadrant surprises), A4 (two-timescale chains) | two different state spaces cannot both be the model |

## The combination, determined by the eligible set

1. **Structure.** If no exclusive-structure arm is eligible, keep main's structure. If exactly one is,
   use it. If more than one is, use the one with the HIGHEST one-year paired difference in 0002. That is
   the only comparison made, and it is on 0002's registered primary endpoint, not a new one.
2. **Layers.** Stack EVERY eligible stackable layer on top of the structure, in the pipeline's own order:
   prior (A1), then rates (A5), then blend (A6).
3. **Hyperparameters.** Each component keeps EXACTLY its 0002-registered value. Nothing is re-tuned for
   the combination. A combination that needs re-tuning to work is not the combination of these arms.
4. **If nothing is eligible, there is no combination to run.** That is a result. The systematic method
   is then main as it stands, and the report says so.

## How 0003 is judged

- **Primary:** the one-year paired difference, combination minus main, exactly as in 0002 (same
  statistic, same bootstrap, same seed).
- **The honest bar is higher than 0002's**, because the combination is built from arms selected on this
  data. It is reported against the 90% level, and it is described as "consistent with the selected arms"
  rather than as fresh evidence. No CONFIRMED label is available to a post-selection experiment.
- **It must also beat its best single component.** A combination that does not beat its strongest
  eligible arm alone adds complexity without evidence, and that arm is recommended instead.
- The same VOID rule: the deterministic audit, plus an independent judged review.
- **Out-of-sample confirmation** comes only from forward registration. The combination's forecasts are
  proposed for `forecasts/register.jsonl` beside the shipped configuration's, both scored as they
  resolve from 2027-07-01. That registration is the owner's call, because it is outward-facing.

## What this rule deliberately does NOT allow

- Choosing among exclusive structures on anything other than 0002's registered one-year paired
  difference.
- Dropping an eligible layer.
- Re-running any 0002 arm with different hyperparameters to make it eligible.
- Calling the combination CONFIRMED.
