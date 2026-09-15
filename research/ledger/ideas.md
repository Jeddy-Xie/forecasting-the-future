# Idea ledger — every idea ever pitched, forever

Compact index; one line per idea. Statuses: ADOPTED · REJECTED(reason) ·
WATCHING(tripwire) · SUPERSEDED(by) · KILLED(objection; resurrection trigger).
Novelty is computed against THIS file, never against model memory. A
re-pitch without its recorded resurrection trigger firing is flagged as a
strike against the pipeline, not presented to the stakeholder.

Format:
`- <id> | <status> | <date> | <one-line> | <reason/trigger>`

- arxiv-2609.07492 | WATCHING(applied to tolerance policy) | 2026-09-10 | FPScan: constraint-based floating-point anomaly detection | promoted W37; tripwire: revisit when the comparator's epsilon is chosen — tripwire FIRED 2026-09-15 (epsilon fixed at 1e-9 by measurement); decision requested
- arxiv-2512.18088 | WATCHING(false-positive base rate) | 2026-09-10 | Flaky tests in quantum software (Qiskit Terra) | promoted W37; tripwire: revisit when the first unchanged-code rerun diff appears — tripwire FIRED 2026-09-15 (first unchanged-code reruns: 0 of 2 differed); decision requested
- gh-syrupy-v6.0.0 | ADOPTED | 2026-09-10 | A serialization change silently invalidates stored baselines; version the run format in the manifest | promoted W37; adopted as a design constraint, not as a dependency
- arxiv-2609.05879 | WATCHING(oracle) | 2026-09-10 | Oracle conversion in specification-based test generation | tripwire: the comparison report acquires a pass/fail gate — tripwire FIRED 2026-09-15 (compare now exits 0/1/2, an oracle); decision requested
- arxiv-2609.06413 | WATCHING(distributional claims) | 2026-09-10 | Shrinkage invalidates the Hosmer-Lemeshow test | tripwire: comparison makes distributional rather than per-row claims — tripwire FIRED 2026-09-15 (paired bootstrap intervals; calibration gate fails an oracle ~91% at n=31); decision requested
- gh-scipy-v1.18.1 | WATCHING(provenance) | 2026-09-10 | SciPy 1.18.1 | tripwire: first whole-grid diff with no code change — tripwire FIRED 2026-09-15 (first no-code-change whole-grid diff: 387/387 identical); decision requested
- arxiv-2609.14758 | WATCHING(promoted W38, undived; awaiting decision) | 2026-09-15 | Tool-augmented agents assert values their tools did not return (14.10%) | machine-extract every agent-reported number
- arxiv-2609.13299 | WATCHING(promoted W38, undived; awaiting decision) | 2026-09-15 | Coordinators carry forward conclusions an experiment does not justify | state each arm's evidence tier separately in the slate report
- ijf-S0169207026000890 | WATCHING(promoted W38, undived, CONTENT UNREAD; awaiting decision) | 2026-09-15 | IJF editorial on reproducibility (doi 10.1016/j.ijforecast.2026.08.004) | read the text before any claim about it
- gh-syrupy-v6.1.1 | WATCHING(new-evidence delta on gh-syrupy-v6.0.0) | 2026-09-15 | Concurrent writers to one snapshot file silently drop entries | tripwire: two processes writing baselines/ concurrently
- arxiv-2609.13345 | WATCHING(reference) | 2026-09-15 | Survey on probabilistic forecasting | tripwire: a calibration method beyond the fixed blend is needed
- doi-10.1002/for.70213 | WATCHING(deferred extension) | 2026-09-15 | Macro forecasting with high-frequency predictors | tripwire: mixed-frequency nowcasting is registered
- arxiv-2609.14082 | WATCHING(prior sensitivity) | 2026-09-15 | Dangers of Bayesian analyses | tripwire: arm A1 reports
- arxiv-2609.15122 | WATCHING(review budget) | 2026-09-15 | When deeper auditing yields more reliable conclusions | tripwire: review depth traded against number of arms
