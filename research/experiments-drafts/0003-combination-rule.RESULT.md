# Experiment 0003: result

The combination rule was committed in `fa90354` (`0003-combination-rule.md`), before any 0002 arm
reported. This file is written by code from `score_slate.py`'s output. Nothing in it is chosen by hand.

**Plan: NO COMBINATION TO RUN: no layer is eligible, and of the eligible structures ['A2', 'A4'] the rule takes A4, which 0002 already ran alone.**

| arm | branch | kind | 0002 verdict | look-ahead review | eligible |
|---|---|---|---|---|---|
| A1 | sticky-dirichlet-prior | layer | none | CLEAN | no |
| A2 | quadrant-structure-levels | structure | CONFIRMED_IN_SAMPLE | CLEAN | yes |
| A3 | quadrant-structure-surprises | structure | none | CLEAN | no |
| A4 | two-timescale-chains | structure | CONFIRMED_IN_SAMPLE | CLEAN | yes |
| A5 | direct-horizon-rates | layer | none; HARMFUL at [12] months, disqualified from combination | CLEAN | no |
| A6 | fixed-climatology-blend | layer | none; PROVISIONAL: the look-ahead review has not reported | PENDING | no |

Eligible: A2, A4. The structure is A4, and the layers
are none.

A6's look-ahead review had not reported when this was written. It cannot change the eligible set: A6's
0002 verdict is none, which is ineligible whatever the review finds. The rule registers and runs 0003
only when the plan says RUN, so no experiment was registered under `proving/` and no thaw token was
used. The systematic method is the structure alone, as experiment 0002 already ran it.
