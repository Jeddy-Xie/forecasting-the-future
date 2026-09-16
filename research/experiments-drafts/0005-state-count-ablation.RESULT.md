# Diagnostic 0005: result

The reading rule was committed in `431582f`, before this ran. This file is written by code from the
run's own outputs.

**Reading: INCONCLUSIVE**, the third of the three outcomes the rule named, and the one it said would
itself be worth reporting.

Exit codes: check-gates 1, compare 0, paired
0, look-ahead audit 2. Commit `9daea2b`,
tree clean at start and end: true.

## What happened

Main's own regimes-exist gate refused the model, verbatim from `check_gates.log`:

> StateSelectionError: no candidate with more than one state is both persistent and populated enough: 16 states (shortest visit 5.6 months, smallest population 1.7%). The data do not support regimes at this frequency; report that rather than lowering the floors.

The look-ahead audit could not run either, for the same reason, verbatim from `look_ahead_audit.txt`:

> StateSelectionError: no candidate with more than one state is both persistent and populated enough: 16 states (shortest visit 4.7 months, smallest population 2.2%). The data do not support regimes at this frequency; report that rather than lowering the floors.

So sixteen unrestricted regimes are not merely worse on this sample: main's existing gate, unchanged,
rejects them because the regimes it finds are too short-lived and too small to be regimes at all.

## Do not read the comparison files in that directory

`compare` and `paired` both exited 0 and report +0.0000 at every horizon, which looks like a passing
control. It is not. Both sides carry main's own configuration hash (`ad7fcc1affd0746a` against
`ad7fcc1affd0746a`): the gates failed before the run wrote any artifact of its own, so the comparison read
main against itself. There are no K = 16 numbers to compare.

That is a weakness in the harness rather than in this diagnostic: a comparison whose gates failed should
refuse rather than emit zeros. Recorded here; it has not been changed, because changing the measuring
instrument mid-investigation is what the regression harness exists to prevent.

## What it does and does not establish

- **It does not separate the confound.** The question was whether A4's gain comes from the two-chain
  structure or from sixteen regimes instead of six. With no sixteen-state single-chain fit, that
  remains open, and answering it needs a new pre-registration at a state count main's gate accepts.
- **It does establish the factorisation's practical argument**, which the pre-registration named in
  advance: on this sample, sixteen unrestricted regimes cannot be fitted at all, while A4's sixteen
  factorised regimes pass the same gate on 58 free parameters against the 399 an unrestricted
  sixteen-state chain would need.
