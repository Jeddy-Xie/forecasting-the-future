# Decision log — the stakeholder's calls, recorded at decision time

Journal fields captured live (never reconstructed): decision, his stated
reason, expected outcome + his probability, review date, and the
counterfactual that powers the kill criterion.

Format:
`## <date> · heat <W>`
`- ADOPT|REJECT|WATCH <id> — reason: … — expects: … (p=…) — review: <date>`
`  counterfactual (would he have found this unaided): YES | NO | MAYBE`
`  [modify-control: system said p=X, he set p=Y — both scored at resolution]`

Merged decisions on main are the ONLY decided truth; open PRs are
proposed-pending. Review judges process, not outcome — no "resulting":
lucky wins get audited exactly like unlucky losses.

## 2026-09-29 · delegated, not heat-driven

**Delegated.** Jeddy Xie delegated this session's decisions to claude-fable-5-1 ("for decisions use
fable and make the decisions for me"). The reasons are the decider's, not his, and live verbatim in
`research/ledger/delegated-decisions/`. Counterfactual here means: would the owner have reached the
same call unaided? Unknown until he reviews it.

- ADOPT P1-1 (the 2026-09-25 review, accepted as E2 with a delegated reading) — expects: the acceptance numbers reproduce from `src/` (p=0.85) — review: 2026-10-15
  counterfactual: MAYBE · resolved 2026-09-29: both reproduced (R1 exact; R2 after P1-11)
- ADOPT P1-2 (rule 0007, the successor evaluation rule) — expects: the default reads SHIP BASE RATE at one year under 0007 and SHIP MODEL under 0001 (p=0.6) — review: 2026-11-15
  counterfactual: MAYBE
- ADOPT P1-3 (experiment 0008: control, B1, B2, B3; 0006 run on a same-code anchor; 0009 after 0008) — expects: control passes (0.97), B3 promising (0.55), B1 promising (0.45), B2 no verdict (0.6) — review: 2026-11-15
  counterfactual: MAYBE
- ADOPT P1-4 (0001's calibration gate kept; a logistic-recalibration test sized for n≈31 for new claims) — expects: the test passes its size check (p=0.75) — review: 2026-10-15
  counterfactual: MAYBE
- ADOPT P1-5 (a class-based materiality floor for judged leaks, 0.001, not retroactive) — expects: B3 is scored rather than voided (p=0.7) — review: 2026-11-15
  counterfactual: MAYBE
- ADOPT P1-6 (D16: transforms moves below data; the table widened; the check enforced) — expects: 0 of 387 fields move (p=0.95) — review: 2026-10-15
  counterfactual: MAYBE · resolved 2026-09-29: 387 of 387 identical
- ADOPT P1-7 (A4 adjudicated: adopted provisionally; not a method that beats a regime-free chain) — expects: 0006 reads granularity (p=0.7) — review: 2027-07-15
  counterfactual: MAYBE
- ADOPT P1-8 (register forward now, monthly, with the single chain beside the default) — expects: rounds for 2026-11 and 2026-12 follow (p=0.6) — review: 2026-12-05
  counterfactual: MAYBE
- ADOPT P1-9 (re-ship now under 0001 with the default, with a disclosure) — expects: the owner endorses rather than reverses it (p=0.65) — review: 2026-11-15
  counterfactual: MAYBE
- ADOPT P1-10 (second audit cutoff standing; D5 reopened narrowed; record corrections; the skill curve) — expects: all land by 2026-10-10 (p=0.85) — review: 2026-10-15
  counterfactual: MAYBE
- ADOPT P1-11 (R2 re-learned every forecast date; the refit cadence kept as an argument for B1's checks) — expects: B1's end-to-end identity holds bit for bit (p=0.85) — review: 2026-10-15
  counterfactual: MAYBE
