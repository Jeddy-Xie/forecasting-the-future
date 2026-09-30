# Look-ahead review: arm B3, equal-blend-with-the-chain (experiment 0008)

I did not write this arm and have no stake in whether it passes. Reviewed 2026-09-29 under
`research/process/lookahead-review-brief-0008.md`.

- **Change reviewed:** `git diff 99f232d...research/equal-blend-with-the-chain`. The branch head is a92a700.
  - The code and tests are in 9b25221.
  - 90ab242 and a92a700 add only files under `research/arms/equal-blend-with-the-chain/`. `git show --name-only` lists no other path for either.
  - The arm touches nothing under `proving/`, `baselines/` or `docs/`.
- **Files:** in `src/…` and `tests/…` paths below, line numbers are on the branch.
- **Scope of my own work:**
  - I modified nothing in the arm's branch, worktree or cache.
  - Scripts live in the session scratchpad. Each ran against a `git archive` export of the branch, with `PYTHONPATH` at the export's `src/`; the import resolved inside the export.
  - Each ran on a scratch copy of the arm's cache, to which I added the UNRATE archival vintages from a copy of arm B2's cache.

## equal-blend-with-the-chain
VERDICT: CLASS-B RECORDED-NOT-VOID

**No class-A path.**

**No outcome and no benchmark value reaches the blend.** This is the difference from 0002's voided A6, and I confirmed it two ways.
- **By reading the code.** R2 reads only the published condition.
- **By execution on the real data.** Every realised outcome was flipped and both benchmarks rebuilt from the flipped outcomes. The issued blend and R2 stayed bit-identical on all 11,730 rows, while outcomes moved on 9,702, the series-start benchmark on 11,681 and R1 on 11,721.

**Two class-B paths, both opened by putting R2 into the issued probability:**
1. **Final revised condition values (D5-class).** They enter R2's rates, which are re-learned at every forecast date, and R2's starting condition, at every indicator on a revised series.
2. **The recession boundary (D14-class).** On 11 forecast dates, where recession dating's condition series ends is set by an NBER trough announcement that came after the forecast date. This moves both recession indicators through R2's gap and its rate sample. The reference shares the dependence: its own forecasts move on 51 rows under the same correction.

**The corrected number.** With both corrected, B3 minus reference-0008 at one year, on the model-sample benchmark, is **+0.061488107820240806**:
- 90% interval [+0.04108019435668044, +0.08690922326420251]; 96.67% interval [+0.03488409831188374, +0.09496574956166959].
- The shift is **+0.000026**.
- Each path alone is also under 0.001: −0.000714 and +0.000740. The ruling does not rest on their cancelling.
- Every wider variant is under 0.001 too. All vintage months give +0.000149. Correcting the model half's rates in both runs as well gives +0.000119.
- No verdict moves at any level or horizon. It is still PROMISING and CONFIRMED_IN_SAMPLE, with no HARMFUL horizon, and the 0001 verdicts are unchanged.
- Under 0007, +0.0615 is the number to report.

### 1. Deterministic audits: passed. What they cover, and what they do not

`exit_codes.json` records, at commit 9b25221: both audits exit 0, and `tree_clean_at_start_and_end: true`.

| cutoff | forecast dates | refits | rows compared | perturbed | run time |
|---|---|---|---|---|---|
| 2000-03-01 | 73 | 7 | 2,190, all identical | 747 vintages whole; 9 current files; 723,523 values | 402 s |
| 2022-03-01 | 337 | 29 | 10,110, all identical | 136 vintages; 12 current files; 151,739 values | 1,822 s |

- **What they cover.** The audits compare `predicted_probability`, which is the blend, and `condition_chain_probability` for exact equality. So R2's reads of every condition unpublished at the cutoff are tested, by announcement dating for recession as well.
- **The 282 WARNING lines** are pre-1994 vintage fallbacks from the honest-start scan, as on main.
- **What they do not cover:**
  - Revised values of published months (path 1).
  - A boundary that is itself wrong. The announcement table is code, and the perturbation never moves a boundary, so path 2 is invisible by construction. The arm's own look-ahead tests have the same property: they flip values with the dating held fixed.
  - The 54 dates after 2022-03-01, and today's grid. The arm pins today's grid to the walk-forward row by a test.

### 2. Every value the change introduces, traced to its inputs

The issued number is `blend_equally_with_the_condition_chain(model, R2)` (`models/indicator_forecast.py:416-441`). The weight is a constant 0.5 (`:408`), and a missing or out-of-range value raises.

| input | read as of | publication timing | outcome? | filtered? |
|---|---|---|---|---|
| Model half | s | Main's unchanged path. All 34 cached fits under the arm hash 7647c129be85291e are byte-identical to main's. | no | filtered (`walk_forward.py:590`) |
| R2 rates | s | `condition_chain_rates(indicator, condition_now, model_sample_starts, …)` (`walk_forward.py:111-128`, `:616-621`). Condition months ≥ the model sample's first month (1950-12), published by s under label plus lag, or ADR 0011. | **no**: the monthly condition only, one regime, weights of one | n/a |
| R2 start and gap | s | `condition_chain_at_every_horizon` (`:131-159`). The last published condition, and `months_between(last label, s)`. | no | n/a |

**The blend identity, checked on the scored run.**
- Over all 11,730 rows, `predicted_probability` equals `blend(reference-0008 predicted, reference-0008 condition_chain_probability)` exactly (`numpy.array_equal`).
- `condition_chain_probability` and every other column equal the reference's.
- So the refactor that moved R2 into `condition_chain_at_every_horizon` changed no R2 value.

**My replay reproduces the scored run exactly.** On the arm's cached fits, the replay equals `backtest_results.parquet` on every column, and my paired statistic reproduces `paired.json`: +0.061462008850023536.

**Today's grid.** `forecast_now` (`command_line_interface.py:382-429`) composes R2 with the same two functions, from conditions published by today and the as-of-today matrix's first month. Live, the announcement table holds only past announcements, so path 2 cannot occur in the live grid.

### 3. The class-B paths, measured

Script: scratchpad `measure.py`. It replays the arm with `walk_forward.condition_available_at` patched at the forecast-date read and takes the corrected `condition_chain_probability` from that replay. It then blends that with reference-0008's own, unchanged, model prediction using the package's `blend_equally_with_the_condition_chain`.

**Path 2: the recession boundary (D14-class).**
- **What a real-time observer had.** The 400-day lag, with months awaiting an announcement coded provisionally by the last announced turning point, instead of withheld.
- **Where it acts.** It changes the start only on 2003-01..07, 2010-08..09 and 2021-06..07. The pipeline starts 15 to 21 months back where the real-time start is 14, at the same value (1). The full table is in the B1 review.
- **Moves.** 66 rows, both recession indicators.
- **Size.** One-year shift **−0.000714**.

**Path 1: revised condition values (D5-class).**
- **The correction.** Conditions on industrial production, consumer prices and unemployment are read from the vintage dated each forecast date, never past the label the pipeline itself read. That affects R2's rates and its start alike.
- **Moves.** 2,277 rows on 386 dates. Because R2 re-learns its rates from each date's vintage, almost every date moves slightly.
- **Size.** One-year shift **+0.000740**.

**The correction I rule on, both paths together.**

| horizon | as scored | corrected | 90% corrected | 96.67% corrected |
|---|---:|---:|---|---|
| 12 | +0.061462 | **+0.061488** | [+0.041080, +0.086909] | [+0.034884, +0.094966] |
| 60 | +0.028019 | +0.029436 | [−0.021727, +0.112629] | [−0.037095, +0.132798] |
| 120 | +0.156105 | +0.157959 | [+0.054770, +0.209079] | [+0.049205, +0.523771] |

- The one-year shift is +0.000026.
- The 0001 verdicts are unchanged: 12 SHIP MODEL; 60 SHIP BASE RATE (calibration); 120 SHIP BASE RATE (skill, calibration, honesty).
- Series-start secondary: +0.052800 → +0.053110.

**Sensitivity.** Every variant stays under 0.001, and none moves a verdict.

| variant | one-year shift |
|---|---:|
| path 1 with all vintage months (including the unemployment release on Fridays the 1st) | +0.000863 |
| both paths, all vintage months | +0.000149 |
| both paths plus the model half's rates, corrected in **both** runs | +0.000119 |

### 4. The look-ahead audit table, row by row

| row | touched? | for B3 |
|---|---|---|
| Training panel assembly | no | R2 reads only the as-of-s matrix's first month. |
| Standardisation window | no | — |
| State probabilities used in forecasts | no | Model half filtered. R2 has one state. |
| Model parameters at each refit | no | Fits byte-identical to main's. |
| Number of regimes | no | 16 (4x4) from the burn-in window. |
| Conditional rates | **yes** | R2's rates now reach the forecast: timing is main's rule, applied at every forecast date. Paths 1 and 2. |
| Benchmark | never read | Confirmed by execution (above). |
| Outcome resolution | no | Never read. |
| Condition values feeding rate estimation | **yes** | Path 1, measured. |
| Every run setting | yes | One boolean. The 0.5 is a constant fixed by the registration. |
| Acceptance thresholds | no | Nothing under `proving/` changed. |
| Canonicalisation, indicator thresholds | no | D12, as on main. |
| Future-perturbation invariance | run | Passes at both cutoffs. Blind to paths 1 and 2. |

### 5. Did the arm do what it registered, no more and no less? Yes

**The registered change.** 0.5 × model + 0.5 × R2 at every indicator and horizon, with R2 at every-forecast-date cadence, the model unchanged, and a missing R2 raising.

**One scored run.** One burn-in choice and 33 refit fits under 7647c129be85291e, plus today's fit, all byte-identical to main's.

**Tests.** Edits only name the switch at False, add a set member, or add one test:
- `test_configuration_hash_compatibility.py`
- `test_two_timescale_chains.py`
- `test_look_ahead_audit.py`

No assertion was removed or loosened.

**Flagged by the arm and confirmed, outside look-ahead.** `submit` is unchanged on this branch, so it would label the blend as `model_probability`.
