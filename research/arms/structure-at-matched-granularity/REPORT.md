# Experiment 0006, arm structure-at-matched-granularity

> The arm agent's own write of this file was refused by the session harness ("Subagents should
> return findings as text, not write report files"); it returned this text instead and did not route
> around the refusal. The coordinator committed it verbatim after checking the one-year numbers and
> the exit codes against `paired.json` and `exit_codes.json`. Check every number against
> `paired.json`, `paired_model_sample.json`, `paired_pre_d14.json` and `compare.json` in this
> directory.

**Verdict under 0006's registered rule: STRUCTURE HELPS.** d6, one year, this configuration minus the
single six-state chain (`baselines/main-single-chain-d14`, `ad7fcc1affd0746a`), series-start benchmark:
**+0.05872680590955551**, 90% interval **[0.021610627548322114, 0.09338180192503258]**. Rule 0008's
words and rule 0007's reading are not applied: 0006 predates them.

Branch `research/structure-at-matched-granularity`. Implementation and tests `6221813`; the harness ran
at `6221813` (`exit_codes.json`: `tree_clean_at_start_and_end: true`); outputs `79601f0`. Exit codes:
check-gates 0, plain compare 1, paired 0, `audit-look-ahead` 0 at 2000-03-01 and 0 at 2022-03-01.
Harness: `RESEARCH_ARM_REFERENCE=main-single-chain-d14 RESEARCH_ARM_BENCHMARK=series-start
RESEARCH_ARM_FAMILY_LEVEL=0.90`. Arm hash `063f83b0fb59a509`.

## What changed

The two-chain state-count sweep offers only the pairs of chain counts whose product is six. The joint
state space then has exactly the six cells of the single chain. With per-chain candidates 1 to 4,
the pairs are 2x3 and 3x2. The pair is chosen by the existing rule, read on the joint rows:
- each chain has more than one state, and is persistent and populated enough;
- then the highest joint held-out log likelihood wins;
- the Bayesian information criterion is reported beside it, and a disagreement is stated.

Admissibility is per chain, and the joint held-out likelihood is the sum of the two chains'. So the
same rule applied over every pair reproduces the per-chain choice exactly. The restriction moves the
candidates and nothing else; a test checks this on 300 random tables. Everything else is main's
two-chain default: same seed, schedule, panels, audit.

| file | change |
|---|---|
| `configuration/run_settings.py` | `restrict_the_two_chain_sweep_to_six_joint_states: bool = True` on this branch; in the hash-omission map at False |
| `models/two_timescale_state_selection.py` | `JOINT_STATE_COUNT_MATCHING_THE_SINGLE_CHAIN = 6`; `joint_state_count_the_sweep_requires`; `TwoChainStateCountSweep.joint_state_count_required` (restricted pairs, joint choice, reason, raise if nothing admissible); `sweep_state_counts_for_two_chains(..., joint_state_count_required=)`; `joint_state_count_required_by_a_joint_table` |
| `backtest/state_count_on_burn_in.py` | the burn-in sweep passes the restriction; the backtest and the look-ahead audit both read this |
| `command_line_interface.py` | the full-sample sweep (gate 2, today's forecast) passes the same restriction |
| `pipeline_gates.py` | `gate_two_from_tables` reads which sweep the run made from its own joint table, refuses a mixture, and refuses a model the tables did not choose |
| `tests/test_structure_at_matched_granularity.py` (new) | 18 tests |

Hashes:
- The arm is `063f83b0fb59a509`.
- At False, main's two-chain default stays `fec79a040f9ca6f9` and the single-chain anchor stays
  `ad7fcc1affd0746a`. A test pins both.

**Choice made.**
- **Burn-in**, as of 1994-03-01, on 518 months from 1950-12-01 to 1994-01-01: **3x2** wins with joint
  held-out −2.6708 per month against 2x3's −2.6867. The criterion prefers 2x3 (2,254 against 2,338).
  Unrestricted, each chain would have chosen 4x4.
- **Full-sample sweep, today:** also 3x2 (−3.0875 against −3.1000; the criterion prefers 2x3).

## Look-ahead audit

| path | touched? | status for this change |
|---|---|---|
| Training panel assembly | no | Same `as_of` panels. The burn-in panel's last label is 1994-01-01, strictly before 1994-03-01, and the boundary assertion is unchanged. 0 of 391 forecast dates use the publication-lag fallback. |
| Standardisation window | no | Expanding, untouched. |
| State probabilities used in forecasts | no | Filtered only; the joint forward pass is inherited. |
| Model parameters at each refit | no | Both chains are refitted from scratch at each of the 33 refits, at the chosen 3x2. |
| **Number of regimes** | **yes** | Clean. The restriction narrows the candidates of the one burn-in sweep, which is still chosen once on the panel ending 1994-01-01, before the first forecast 1994-03-01. The constant 6 is the single chain's own burn-in choice, made on that same panel as of 1994-03-01, and was fixed by the registration before the run. It carries nothing published after 1994-03-01. Both audits recomputed the choice from scratch in both runs: 6 regimes both times, at both cutoffs. |
| Conditional rates | no | Code unchanged; D14 is on both sides of d6. |
| Benchmark (climatology) | no | Unchanged. d6 is read on the series-start column, as registered. |
| Outcome resolution | no | Unchanged. |
| Condition values feeding rate estimation | no | The D5 approximation, unchanged. |
| Every run setting | yes | One boolean and one constant (6), both fixed a priori by the registration. |
| Acceptance thresholds | no | 0006's rule has no number beyond "the one-year 90% interval lies entirely above zero"; unchanged. |
| Canonicalisation rule | no | Fixed sort within each chain. |
| Indicator thresholds | no | Weak (D12), unchanged. |
| Future-perturbation invariance | — | **Pass at 2000-03-01**: 2190 rows identical, 7 fits from scratch in each run, 723,523 values perturbed, 380 s. **Pass at 2022-03-01**: 10,110 rows identical, 29 fits from scratch in each run, 151,739 values perturbed, 1,213 s. |

## Results

**d6, series-start benchmark, against `main-single-chain-d14` (`paired.json`, primary):**

| horizon | anchor skill | arm skill | d6 | 90% interval (= family-wise, level 0.90) |
|---|---|---|---|---|
| 12 months | 0.2084683250748939 | 0.2671951309844494 | **0.05872680590955551** | [0.021610627548322114, 0.09338180192503258] |
| 60 months | 0.07374483365946538 | 0.11264393671914741 | 0.03889910305968203 | [-0.012556214434740382, 0.12928002405337435] |
| 120 months | -0.34506835757487075 | -0.06626717369061418 | 0.27880118388425656 | [0.13961534779159268, 0.2998583867161505] |

9,702 resolved forecasts are in both runs; none are on one side only.

**Registered secondaries:**
- **Model-sample benchmark**, against `main-single-chain-d14` (`paired_model_sample.json`):
  - 12 months: 0.06404498909744821 [0.027653963133120765, 0.09761277110535747]
  - 60 months: 0.045715918496662504 [0.00016991337896109075, 0.12637659558616832]
  - 120 months: 0.2845440758408741 [0.14188619322483736, 0.3037187945867118]
- **Pre-D14**, against `baselines/main.json`, series-start benchmark (`paired_pre_d14.json`):
  - 12 months: 0.05181774356080107 [0.013725321576441206, 0.0869735011173151]
  - 60 months: 0.03988186681622788 [-0.011829060675858065, 0.1372884222143099]
  - 120 months: 0.2865019235995448 [0.15503902024912058, 0.30969239918657454]

**Beside A4's registered numbers** (A4 was measured against `baselines/main.json`, pre-D14):

| horizon | A4 (16 cells) | this arm, pre-D14 | d6 (same-code anchor) |
|---|---|---|---|
| 12 months | +0.0590 | +0.0518 | +0.0587 |
| 60 months | +0.0465 | +0.0399 | +0.0389 |
| 120 months | +0.1855 | +0.2865 | +0.2788 |

**Free parameters and effective sample, as the registration asks:**
- Free parameters, from the burn-in sweeps:
  - single chain, 6 states: 89
  - A4, 4x4: 58
  - this arm, 3x2: 27
- Effective sample behind each forecast. This is `mean_effective_sample_size`: the months of regime
  occupancy behind the per-regime rates, weighted by the forecast's regime distribution. Means over
  the ten indicators at 12 / 60 / 120 months:
  - anchor: 118.1 / 114.4 / 104.6
  - A4: 46.3 / 46.1 / 43.5
  - this arm: 141.7 / 133.2 / 127.3

**Verdicts under 0001**, arm (anchor in brackets):
- 1 year: **SHIP MODEL**, every gate passed; skill +0.2672 [+0.1683, +0.3571], calibration error
  0.0943 (anchor: SHIP BASE RATE, calibration).
- 5 years: SHIP BASE RATE, failing skill, calibration and robustness (anchor: the same three).
- 10 years: SHIP BASE RATE, failing skill, calibration and honesty; total variation 0.0204 against a
  floor of 0.05 (anchor: also failed robustness).

**Per-indicator one-year d6** (`paired.json`, point estimates). All ten are positive:

| indicator | d6 |
|---|---|
| consumer_price_inflation_above_five_percent_within_horizon | 0.03443365680574184 |
| consumer_price_inflation_above_three_percent_at_horizon | 0.0561446310403263 |
| economy_in_recession_at_horizon_date | 0.07596808722337878 |
| economy_in_recession_within_horizon | 0.008075262280880402 |
| federal_funds_rate_above_four_percent_at_horizon | 0.027600805964757447 |
| federal_funds_rate_below_one_percent_within_horizon | 0.0503187040927654 |
| industrial_production_growth_above_two_percent_at_horizon | 0.07834733771012448 |
| treasury_yield_curve_inverted_within_horizon | 0.0813170909965053 |
| unemployment_rate_above_five_percent_at_horizon | 0.14181689946778375 |
| unemployment_rate_above_seven_percent_within_horizon | 0.0332455835132911 |

## Verdict arithmetic

The rule reads the one-year 90% interval of d6 and has three outcomes:
- STRUCTURE HELPS if the interval lies entirely above zero;
- GRANULARITY, NOT STRUCTURE if it includes zero or lies below it;
- INCONCLUSIVE if any gate fails or the look-ahead audit exits non-zero.

Here all five gates passed (check-gates 0), and both audits exited 0, so this is not INCONCLUSIVE. The
lower bound is 0.021610627548322114, which is above 0, so the interval lies entirely above zero.
**STRUCTURE HELPS.**

The judged half of the look-ahead defence, an independent reviewer who did not write the change, has
not been done. 0006's rule names only the deterministic audit.

## Required checks and diagnostics

- The registration names no `required_checks` and no pre-run diagnostic; none was run.
- 18 new tests pass. They pin:
  - the switch and the hashes (`063f83b0fb59a509`; at False, `fec79a040f9ca6f9` and `ad7fcc1affd0746a`);
  - the candidates: 1x1 plus 2x3 and 3x2 only;
  - the rule: highest joint holdout wins; an inadmissible pair is never chosen; a criterion
    disagreement is reported; nothing admissible raises; the joint rule over every pair equals the
    per-chain rule on 300 random tables;
  - the regimes-exist gate reads only the offered pairs;
  - the wiring: a fitted restricted sweep chooses the simulated 2x3 and its criteria add up; the
    burn-in choice, `fit_regimes` and the look-ahead audit all run the restriction; gate 2 rebuilt
    from the run's tables equals the run's own gate.
- Suite: 584 passed, 2 skipped (the cached-fit byte test; no fit is cached under the arm's hash).
  ruff, ruff format, mypy and layer_check are all clean.

## Decided before the run, not written in the registration

- The single-regime pair 1x1 stays in the joint table as the null for the regimes-exist gate, for
  the same reason 1 is in `hidden_state_counts_to_search`.
- Each chain in an admissible pair must have more than one state, mirroring the per-chain rule. For
  a product of six with candidates up to 4, this changes nothing.
- Each chain is still swept over 1 to 4, so the per-chain tables are complete. The chains' own
  unrestricted choice (4x4) is printed in the reason.
- The restriction applies to both sweeps: burn-in (backtest and audit) and full sample (gate 2 and
  today's forecast).

## Deviations

- Existing tests were edited, with no assertion changed or removed. Six settings constructions across
  four files now name the switch at False, because no pair of candidates (1, 2) multiplies to six:
  - the fixtures in `test_burn_in_state_count_choice.py`, `test_look_ahead_audit.py` and
    `test_two_timescale_chains.py` (`_settings`);
  - main's hash test in `test_two_timescale_chains.py`;
  - the shipped-settings and omission-map tests in `test_configuration_hash_compatibility.py`.

  A4 and A5 did the same. This needs the owner's review.
- Family level 0.90 means `paired.json` carries one interval, and `paired_series_start.*` was not
  produced, because the primary benchmark is already series-start.

## Prediction versus outcome

**Predicted** (briefing 05): GRANULARITY, NOT STRUCTURE. **Outcome:** STRUCTURE HELPS.

**The prediction's evidence mixed two panels.** Briefing 05's "0.0225 nats/month worse" compared:
- 2x3 = −3.102579, from line 50 of A4's `check_gates.log`, in the `fit_regimes` section: the
  full-sample sweep, not the burn-in;
- against the single chain's −3.0801, from the 518-month burn-in sweep.

On the same burn-in panel, 2x3 is −2.6867 and 3x2 is −2.6708 against −3.0801. The factorial six-cell
model is better by about 0.39 to 0.41 nats/month. The source files are main's
`.cache/models/burn_in_state_count_choice_1994-03-01_seed20260908_{ad7fcc1affd0746a,fec79a040f9ca6f9}.json`.

**Surprises:**
- The chosen pair puts **three states on growth and two on inflation and rates**, the opposite of
  briefing 05's "granularity pays in the levels chain".
- The effective sample rose (118.1 to 141.7 at one year) with fewer free parameters (27 against 89).
- Unregistered, point estimate only, from committed numbers: the arm's one-year mean skill,
  0.2671951309844494, sits within 0.00006 of the 16-cell default on the same code
  (`baselines/reference-0008.json`, 0.2672554495944556).
- The 10-year d6 (+0.2788) rests on about 2.2 independent observations, and the arm fails the
  honesty gate there.
