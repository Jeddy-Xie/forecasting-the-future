# Are the next three proposals provable here? What this sample can and cannot resolve

Research briefing · compiled 2026-09-20 · for `forecasting-the-future`

**Scope.** `research/reports/impact-analysis/changes.json` field `next_candidates` names three things
to do next, in the owner's words. Briefing 04 ranks the same ideas on their mechanisms and the
literature. This briefing asks one question about each, and only that question: **could a claim about
it be established or refuted with the data and machinery this project actually has?** Not whether it
is a good idea. Whether an experiment here could settle it, and if so, how.

The three, verbatim from `changes.json`:

1. **Couple the two chains** — "the only one that makes the model more than two separate chains.
   Diagonal coupling costs four parameters… It carries a free falsifier: the joint second eigenvalue
   equals the slower chain's only while the chains are independent."
2. **Time-varying transitions on the growth chain** — "the factorial structure cuts the parameter cost
   about twentyfold against putting them on a joint chain, which converts an objection the earlier
   briefing treated as fatal into a survivable one."
3. **A state-count ablation main's gate will accept** — "The K = 16 ablation could not be fitted.
   Separating structure from granularity needs a new pre-registration at a count the regimes-exist
   gate admits."

Briefing 04's ranking (coupling 1st, TVTP 2nd deferred, ablation named as the thing to run *before*
funding anything) is treated here as an input, not an answer. On power it comes out in a different
order.

**The tree moved while this was being written, and one thing here depends on it.** This briefing was
begun at `15d6636` and finished at **`d95f3ce`, which adopts the two-chain model as the pipeline's
method** (ADR 0010). Two consequences, both checked rather than assumed:

- **"Main" still means the single chain where it matters.** `baselines/main.json` was **not**
  recaptured: it still carries `ad7fcc1affd0746a`, six states, single chain, untouched since
  `628a77d` [measured]. Every `paired.json` used in §2 was computed against exactly that file, so the
  whole detectable-effect derivation and every protocol below that says "against main" are unaffected.
  What changed is the *default configuration* — a branch cut today inherits two chains at 4×4, hash
  `fec79a040f9ca6f9`. The two must not be confused, and the registration in §5 states which it means.
- **The correlation claim this briefing set out to check was retracted and replaced mid-session**, with
  a derivation committed at `research/briefings/derivations/within_state_cross_block_correlation.py`.
  §6.2 and §7 record what that changes: my independent computation now **corroborates** the
  replacement rather than contradicting the original.

Adoption also raises the stakes on proposal 3. ADR 0010 states plainly, under "What this decision does
not claim", that "the mechanism is not established" and that "the ablation that would separate them
cannot be fitted on this sample" [measured]. §5 shows it can be — from the other side.

**Evidence discipline.** This briefing fetched nothing. Every number is from a file in this repository
or in `forecasting-the-future-arms/`, and each is labelled:

- **[derived]** — computed here from repository files; the arithmetic or the code is in §6 so it can
  be re-checked.
- **[measured]** — read directly from a run's own output file, with the file named.
- **[E1]** — my reasoning from the above, asserted as such.

**One discovery constraint, stated up front.** `proving/PROTOCOL.md` does not exist. The project's
pre-registration practice had to be read off the two registrations themselves
(`proving/experiments/0001-…`, `0002-…`), the three diagnostic drafts in `research/experiments-drafts/`,
and `research/tools/score_slate.py`, which computes verdicts from the rule file rather than restating
it. That reading is in §1 and everything downstream depends on it being right.

---

## Executive summary

**1. The detectable effect is not one number — it scales with how much an arm moves the forecasts.**
Backed out of the paired bootstrap's own interval half-widths, the standard error of the one-year
paired difference runs from **0.0109** for an arm that only changes fitting (A1) to **0.0301** for one
that post-processes every forecast (A6) [derived, §2]. The smallest difference distinguishable from
zero is `z × s`: **0.018 to 0.050 at 90%**, and **0.026 to 0.072 at the 98.33% family-wise level**. Any
proposal whose plausible effect sits under its own row of that table cannot be settled here, however
long it runs.

**2. Family size is a lever the owner controls, and it is worth 31%.** The 98.33% bar was
`1 − 0.10/6` because six arms were registered at once. A registration of **one** hypothesis confirms at
`1 − 0.10/1 = 90%`, i.e. `z` falls 2.394 → 1.645 [derived, §2.3]. Registering three instead of six
buys 96.67% and `z = 2.128`. This is the cheapest power available and it costs no compute.

**3. Coupling cannot deliver what the correlation measurement promises, because they are different
quantities.** The dependence A4 discards is *contemporaneous*, in the emission covariance. Diagonal
coupling changes the *transition* matrix and leaves the block-diagonal covariance exactly as it is. It
cannot represent contemporaneous correlation at all [E1, §3.1]. Briefing 04 calls it "the cheap way to
buy back the dependence"; it is not the same dependence.

**4. The discarded cross-block dependence is real, and now independently corroborated at about 0.6 of
the kept one.** Recomputing from the arm's own 35 cached fits and its own point-in-time panels gives
occupancy-weighted mean |ρ| of **0.205** with inflation and **0.222** with rates, against **0.342** for
the pair the model keeps — a discarded/kept ratio of **0.61–0.62** [derived, §6.2]. The repository's own
newly committed derivation, run here, returns **0.203 / 0.207 / 0.344**, ratios **0.59 and 0.60**
[measured]. Two computations that share no code agree to within 0.015. The earlier published triple
(0.191 / 0.144 / 0.288) has been retracted in favour of a range, and the range is right.

**5. The repository has already measured what discarding that dependence is worth, in the only
direction available: it is worth nothing bad.** Main carried a full 3×3 covariance. A4 threw the
cross-block terms away — and beat main by +0.0590. Buying back a dependence whose removal coincided
with the largest gain in the slate is unlikely to be worth more than the 0.018–0.030 detectable floor
[E1 on measured inputs, §3.1].

**6. The confound is already leaning, and the evidence was on disk.** A4's own burn-in sweep table
prices every (K_growth, K_levels) cell on held-out log likelihood, on the same 518-month burn-in panel
main uses. At **matched cell count** — two chains at 2×3 = six joint states against main's single chain
at six — the factorial structure is **0.0225 nats/month worse** (−3.1026 against −3.0801), on 30 free
parameters instead of 89. Going 6 → 16 cells *inside* the factorial family buys **+1.114 nats/month**
[derived, §3.3]. On this evidence the structure buys nothing and the granularity buys everything.

**7. And the granularity that pays is in the wrong chain for the arm's own hypothesis.** Decomposing
that same table: holding growth at 2 and taking levels 2 → 4 gains **+1.088** nats/month; holding
levels at 2 and taking growth 2 → 4 gains **+0.384**. **74% of the likelihood gain comes from resolving
the inflation-and-rates block more finely, 26% from growth** [derived, §3.3]. A4's hypothesis was that
*growth* needed its own faster chain. This is the third independent thing pointing away from it, after
the at-horizon/any-time split and the λ₂ identity.

**8. Verdicts: none of the three is provable as written.** Two are underpowered and one is not
falsifiable as stated. But the third has a rewrite that *is* provable, is powered by a wide margin,
needs no new modelling code, and answers the question the project's own `limits` section names as the
top open item about its only confirmed method.

---

## 1. How this project decides things, and what a new registration inherits

Read off `proving/experiments/0002-research-slate-2026-09/experiment.json` and
`research/tools/score_slate.py`, which reads the rule from that file so the two cannot drift [measured].

| element | value | where |
|---|---|---|
| primary endpoint | paired difference in mean Brier skill score, arm − main, at **12 months** | `metric.primary` |
| interval | moving-block percentile bootstrap, block = horizon in months, 10,000 resamples, seed 20260908 | `metric.primary` |
| resampled unit | forecast date, every indicator on it kept together | `paired.json.bootstrap` |
| both levels | from **one** set of resamples (`levels_share_resamples: true`) | `paired.json.bootstrap` |
| PROMISING | one-year 90% interval entirely above zero | `decision_rule` |
| CONFIRMED_IN_SAMPLE | one-year interval at `1 − 0.10/family_size` entirely above zero | `decision_rule` |
| HARMFUL | at any horizon, 90% interval entirely below −0.02 | `decision_rule` |
| VOID | `forecast audit-look-ahead` exit ≠ 0, **or** an independent judged review finding any leak path | `decision_rule` |
| one run per arm | a bug fix may not change a hyperparameter; both runs reported | `decision_rule` |
| the forbidden act | changing any hyperparameter or threshold after an arm has produced a number | `stated_in_advance` |

Three inheritances bind any new registration, and all three matter below.

**The VOID rule has no materiality floor.** A6 was voided for a leak that moves its one-year difference
by 0.0002, because the rule voids for any path [measured, `changes.json` decisions]. Whether a floor
should exist is already on the owner's open-decision list. Until it does, any proposal that touches
outcome resolution or the climatology inherits a near-certain VOID.

**Both confidence levels must be requested at run time.** `scripts/research_arm.sh` passes
`--confidence-level 0.90 --confidence-level 0.9833` explicitly; the repository records that an earlier
version asked for one level, which would have made CONFIRMED unreachable while looking like an honest
non-result [measured, `changes.json` LEVELS]. A new registration must state its own second level.

**The effective independent sample is fixed by arithmetic, not by effort.**
`evaluation/bootstrap.py::effective_independent_sample_size` is literally `sample_size / block_length`
[measured]. At one year: 378 forecast dates / 12 = **31.5**. At five years 5.5, at ten 2.25. No change
to the model alters these. More compute cannot buy more of them; only calendar time can.

---

## 2. The detectable effect, derived from the bootstrap's own output

### 2.1 The observable, and how to invert it

`paired.json` reports, per horizon, a `difference` and one interval per confidence level. The intervals
are percentile intervals from a moving-block bootstrap, both levels read off the same 10,000 resamples.
Write `HW(L)` for the half-width at two-sided level `L`.

If the resampling distribution of the paired difference is approximately Gaussian with standard error
`s`, then

```
HW(L) = z_{(1+L)/2} · s
```

Because two levels come off **one** set of resamples, this is over-identified and can be checked rather
than assumed. The prediction is

```
HW(0.9833) / HW(0.90) = z_0.991665 / z_0.95 = 2.393980 / 1.644854 = 1.4554
```

Measured across the six arms at 12 months [derived from each arm's `paired.json`]:

| arm | HW(90%) | HW(98.33%) | ratio | s from 90% | s from 98.33% |
|---|---:|---:|---:|---:|---:|
| A1 sticky-dirichlet-prior | 0.017899 | 0.026333 | 1.4712 | 0.010882 | 0.011000 |
| A2 quadrant-levels | 0.021952 | 0.031785 | 1.4479 | 0.013346 | 0.013277 |
| A3 quadrant-surprises | 0.022733 | 0.033053 | 1.4540 | 0.013821 | 0.013807 |
| A4 two-timescale | 0.030106 | 0.043594 | 1.4480 | 0.018303 | 0.018210 |
| A5 direct-horizon-rates | 0.043068 | 0.061869 | 1.4365 | 0.026183 | 0.025844 |
| A6 climatology-blend | 0.049646 | 0.071915 | 1.4486 | 0.030183 | 0.030040 |

Every ratio is within **1.3%** of the Gaussian prediction, and the two levels agree on `s` to within
**1%** for every arm. The inversion is sound. This is a derivation from the files, not a rule of thumb:
the second confidence level, which the project requested for a different reason, is what makes it
checkable.

### 2.2 The minimum detectable effect

An interval excludes zero exactly when `|d| > z · s`. So the smallest one-year difference this sample
can distinguish from zero is `MDE(L) = z_{(1+L)/2} · s`, taking `s` from the class of change:

| class of change | example | s | MDE 90% | MDE 96.67% (family 3) | MDE 98.33% (family 6) |
|---|---|---:|---:|---:|---:|
| fitting only | A1 | 0.0109 | **0.0180** | 0.0233 | **0.0262** |
| state space, fewer cells | A2, A3 | 0.0133–0.0138 | 0.0219–0.0227 | 0.0283–0.0294 | 0.0319–0.0331 |
| state space, more cells | A4 | 0.0183 | **0.0300** | 0.0389 | **0.0437** |
| composition / post-processing | A5, A6 | 0.0260–0.0301 | 0.0428–0.0496 | 0.0554–0.0641 | 0.0623–0.0721 |

Two consequences worth stating plainly.

**`s` is a property of the arm, not of the sample.** A0, which changes nothing, has `s` exactly 0 and
intervals exactly [0, 0] [measured]. The more an arm moves the individual forecasts, the wider its own
paired interval. So "what can this sample detect" has no single answer, and quoting A4's 0.0301 for a
four-parameter tweak would overstate the bar by about 70%.

**The comparator is a design choice with a large power consequence.** An arm built *on top of* A4 and
paired against **A4** is a small perturbation: `s` near the A1 row, MDE ≈ 0.018 at 90%. The same arm
paired against **main** inherits all of A4's displacement as well: `s` near 0.0183, MDE ≈ 0.030. The
harness supports either — `forecast baseline capture --name a4` then
`forecast baseline compare --against a4 --paired` — with no new code
(`regression_baseline.py::capture_baseline`, `baselines/`) [measured]. Choosing the right baseline is
worth roughly a 40% reduction in the detectable effect and costs nothing.

### 2.3 Family size is worth 31%

`score_slate.py` computes `confirm_level = round(1 - 0.10/family, 4)` from the rule file's
`family_size` [measured]. So the confirmation bar is set by how many hypotheses are registered together:

| family size | confirm level | z | MDE at A1-class s = 0.0109 |
|---:|---:|---:|---:|
| 6 | 98.33% | 2.3940 | 0.0262 |
| 3 | 96.67% | 2.1280 | 0.0233 |
| 2 | 95.00% | 1.9600 | 0.0214 |
| 1 | 90.00% | 1.6449 | 0.0180 |

Registering one hypothesis rather than six lowers the bar by **31%** for identical data [derived]. The
honesty condition is that it must genuinely be one pre-registered hypothesis — running three and
reporting the best one under a family of one is the forking path the 0002 registration already names
and declines to take. Stated as a rule the owner can adopt: **the family is the number of arms whose
results you will look at before deciding, not the number you write down.**

---

## 3. Proposal 1 — Couple the two chains

### 3.1 The claim, and the quantity mismatch at its centre

**Falsifiable form.** *Letting each of the levels chain's four self-transition probabilities depend on
the growth state — four scalars, direction fixed as growth → levels before fitting — raises the
one-year paired mean Brier skill score of the two-chain model, measured against the two-chain model
with those four scalars held at zero.*

**Detectable effect.** The change is the smallest structural perturbation in the slate's history: 4
parameters added to 58, the E-step untouched, the emission untouched, the cell count untouched, the
forecast composition untouched. It is strictly smaller than A1, which rewrote every transition
probability at every fit and produced `s = 0.0109`. Paired against A4 it is therefore an A1-class arm
or smaller:

- **90%: 0.0180** · **96.67% (family of 3): 0.0233** · **98.33% (family of 6): 0.0262** [derived, §2.2]

Paired against main instead, it inherits A4's displacement and the floor rises to **0.0300 / 0.0389 /
0.0437**.

**Plausible effect.** Three in-repo measurements bound it, and all three point the same way.

*First, the correlation the proposal invokes is not the quantity coupling changes.* The discarded
dependence is contemporaneous — the within-state covariance between the growth residual and the
inflation/rates residuals, which `models/two_timescale_hidden_markov_model.py` sets to zero by
construction (block-diagonal covariances). Diagonal transition coupling changes `A_l` conditional on
`S_g`. It leaves the covariance block-diagonal. A model with coupled transitions and block-diagonal
emissions still cannot represent contemporaneous correlation between growth and inflation in any
month [E1]. The measured 0.20–0.22 is evidence for a *covariance* extension, not for this one.

This now matters more than it did when briefing 04 wrote it, because **ADR 0010 carries the same
inference into an accepted decision record**: under "What this decision does not claim" it says "a
dependence is discarded… Coupling the chains is the first extension this argues for", citing the
correlation derivation [measured]. The measurement is sound and the inference from it is not. What the
correlation argues for is restoring cross-block *covariance* terms; diagonal transition coupling leaves
that covariance exactly as block-diagonal as it found it. If coupling is built on this rationale it
will be built to fix something it cannot reach [E1].

*Second, the repository has already measured what removing that covariance was worth.* Main carried a
full 3×3 covariance across all three columns. A4 deleted the cross-block terms and scored **+0.0590**
against it [measured, `paired.json`]. Whatever the cross-block dependence contributes to a one-year
forecast, removing it was compatible with the largest gain in the slate. Restoring it is not plausibly
worth more than the 0.018 floor [E1 on measured inputs].

*Third, A1 is the repository's own yardstick for "what a wholesale change to the transition matrix
buys at one year".* A1 removed nine exact zeros, moved λ₂ from 0.9777 to 0.9700 and the half-life from
30.7 to 22.8 months, and produced a one-year difference of **+0.0046, 90% [−0.0126, +0.0232]**
[measured]. A four-parameter conditional adjustment to one chain's diagonal is a far smaller
intervention than that. Its plausible one-year effect is of order **+0.005**, against a floor of
**0.018**.

**Verdict: UNDERPOWERED.** The plausible effect is roughly a quarter of the smallest difference this
sample can distinguish from zero, at the most favourable comparator and the most favourable family
size. A skill experiment on diagonal coupling would return an interval spanning zero whether or not the
coupling is real, and that outcome would carry no information.

**A logical note on the "free falsifier".** The proposal says the joint second eigenvalue "equals the
slower chain's only while the chains are independent". The implication runs one way only. Briefing 04
proves `λ₂(A ⊗ B) = max(|λ₂(A)|, |λ₂(B)|)` for *any* two independent chains [derived there, to 2.1e-15].
A *departure* from that maximum therefore proves the coupling estimated to something non-zero. But
*no departure* does not prove independence — a coupled chain can have a second eigenvalue that happens
to equal the maximum. As a falsifier it is sound in one direction and silent in the other [E1].

**Proof rung now, and the cheapest step up.** The skill claim is **unproven**, and the cheapest step up
is *not* protocol-drafted, because the protocol would be underpowered by a factor of four and writing
it would commit a run that settles nothing. The cheapest genuinely informative step is to promote a
*different, structural* claim to **estimated**: fit the coupled model once and measure whether the four
coupling scalars are non-zero and whether joint λ₂ departs from the maximum. That is a deterministic
measurement on a single fit. It needs no bootstrap, no walk-forward, no baseline comparison and no
look-ahead review, because nothing is being claimed about forecasts.

**The protocol, for the version that is provable.** Register it as a diagnostic in
`research/experiments-drafts/`, in the shape 0004 and 0005 already use.

- *What changes.* `_maximisation_step` in `models/two_timescale_hidden_markov_model.py` currently
  marginalises the joint transition counts to each chain via `counts.sum(axis=(1,3))` and
  `counts.sum(axis=(0,2))`. The coupled M-step replaces the levels marginalisation with a per-growth-state
  restricted update: for each growth state `g`, re-estimate only the diagonal of `A_l` from
  `counts[g].sum(axis=0)`, keeping the off-diagonal shape from the pooled estimate and renormalising.
  Four scalars. The E-step is unchanged, because the joint chain remains an ordinary 16-state Markov
  chain and the emission still block-separates.
- *What is measured.* At each of the 35 refits: the four coupling scalars; joint λ₂; and
  `max(λ₂_growth, λ₂_levels)`; plus the joint log likelihood against the uncoupled fit.
- *The decision rule, fixed in advance.* **COUPLED** if at a majority of refits the coupling scalars
  differ from their uncoupled values by more than 0.01 in absolute probability **and** joint λ₂ departs
  from `max(λ₂_g, λ₂_l)` by more than 1e-6 (the identity holds to 2.1e-15 when they are independent, so
  1e-6 is six orders of margin). **INDEPENDENT** if neither holds. **INCONCLUSIVE** if the coupled fit
  fails the monotonicity guard or does not converge at a majority of refits.
- *Required check.* Coupling scalars pinned at the uncoupled values must reproduce A4's fit bit for
  bit, tested with array equality, not a tolerance — the same check A1's brief required [measured].
- *What is a failure.* INDEPENDENT is a publishable negative result at a cost of four parameters, and
  it is the outcome that retires briefing 04's rank 1. INCONCLUSIVE is a failure of the diagnostic and
  must be reported as such rather than re-run with a widened allowance.
- *What it does not license.* No skill claim. The diagnostic says whether the chains are coupled, not
  whether coupling forecasts better, and the registration must say so in its own "What this is NOT"
  section.

**Cost.** 35 fits over the burn-in and refit panels, no walk-forward, no bootstrap: single-digit
minutes of compute, the panels are already cached. Implementation is one function. It displaces
nothing — it does not consume a slate slot, because it is not scored against the 0002 endpoint.

### 3.2 If the owner wants the covariance question instead

The measurement in §6.2 supports a *different* extension: restoring the cross-block covariance terms.
That is a larger change (two extra covariance parameters per joint state, tied or untied) and it is
the one the correlation number actually speaks to. Its plausible effect is bounded the same way by the
second argument above — main had those terms, A4 deleted them and gained +0.0590 — so it is
underpowered on the same arithmetic. Recorded here so that the option is not later mistaken for
untried.

### 3.3 The evidence that was already on disk

While pricing the ablation (§5) I read A4's own burn-in joint sweep table out of its `check_gates.log`.
It prices every (K_growth, K_levels) pair on held-out log likelihood per month, on the same 518-month
burn-in panel (1950-12 to 1994-01) that main uses, and main's own burn-in line prices its single chain
on the same panel [measured, both `check_gates.log` files]:

| model | joint cells | free parameters | held-out log likelihood per month |
|---|---:|---:|---:|
| two chains (1,1) | 1 | 7 | −4.1834 |
| two chains (2,2) | 4 | 20 | −3.4615 |
| **two chains (2,3)** | **6** | **30** | **−3.1026** |
| **main, single chain** | **6** | **89** | **−3.0801** |
| two chains (4,2) | 8 | 36 | −3.0772 |
| two chains (2,4) | 8 | 42 | −2.3730 |
| two chains (3,3) | 9 | 37 | −2.7525 |
| two chains (4,4) | 16 | 58 | −1.9887 |

Two things fall straight out [derived]:

**At matched cell count the factorial structure buys nothing.** Six joint cells as 2×3 scores −3.1026;
main's single chain at six states scores −3.0801. The factorial version is **0.0225 nats/month worse**,
on 30 free parameters against 89. Whatever A4 is buying, it is not being bought by factorising at
constant granularity.

**Granularity buys a great deal, and it buys it in the wrong chain.** Within the factorial family,
6 → 16 cells is worth **+1.1139 nats/month**. Decomposing from (2,2):

- levels 2 → 4, growth held at 2: −3.4615 → −2.3730, **+1.0885**
- growth 2 → 4, levels held at 2: −3.4615 → −3.0772, **+0.3843**
- total (2,2) → (4,4): **+1.4728**

So **73.9% of the gain comes from resolving the inflation-and-rates block more finely, and 26.1% from
growth** [derived]. A4's registered hypothesis was that *growth* was being dragged onto the slow
timescale and needed its own chain. The held-out likelihood says the payoff is mostly in the block that
was already slow.

This is an **estimated**-rung result, not a **proven** one: held-out log likelihood on the burn-in panel
is not the registered endpoint, and a model can win on likelihood while losing on Brier skill — briefing
02 records exactly that pattern in Li, Maheu & Yang, where nonparametric regime machinery had the best
log predictive likelihood on US industrial production and the worst RMSFE of fourteen models. It is a
strong prior and a cheap one, and it is the third independent signal pointing away from the
two-timescale mechanism, after the at-horizon/any-time split (+0.0884 against +0.0297, the opposite of
the prediction) and the non-falsifiable λ₂ identity.

---

## 4. Proposal 2 — Time-varying transitions on the growth chain

### 4.1 What it asserts, and what it leaves unasserted

As written, the proposal makes an arithmetic claim, not a forecasting one: that the factorial structure
cuts TVTP's parameter cost "about twentyfold". That much is **already settled, and it is correct**.
With `q` drivers, TVTP on the joint 16-state chain costs `16 × 15 × q = 240q`; on the growth chain
alone it costs `4 × 3 × q = 12q`; the ratio is exactly **20×** [derived]. Briefing 04's number checks
out. But an affordability claim is not a hypothesis about forecasts, so the falsifiable version has to
be supplied.

**Falsifiable form.** *Making the growth chain's transition probabilities a logistic function of the
registered ten-year-minus-three-month term spread, with the coefficients estimated at each refit on
data published strictly before that refit date, raises the one-year paired mean Brier skill score
against the fixed-transition two-chain model.*

The driver exists: `ten_year_minus_three_month_term_spread` is a registered derived series in
`configuration/economic_series.yaml` [measured], so the data plumbing is real and the arm would not
need a new fetch.

**Detectable effect.** TVTP changes every transition probability at every month, so it moves forecasts
more than A1 does and probably about as much as a state-space change. Paired against A4 as baseline,
`s` sits between the A1 and A4 rows — call it 0.011 to 0.018:

- **90%: 0.018 to 0.030** · **96.67%: 0.023 to 0.039** · **98.33%: 0.026 to 0.044** [derived, §2.2]

**Plausible effect.** The parameter arithmetic has genuinely improved, and the improvement is larger
than briefing 04 claims. Briefing 02 killed TVTP on 20 parameters against ~30 observed switches — 1.5
switches per parameter. Main's chain switches **30 times over 908 months** [measured,
`check_gates.log`]. The growth chain's half-life is **12.6 months** against main's **30.7** [derived in
briefing 04 from the measured λ₂], so a chain with that persistence turns over roughly 2.4× as often,
giving on the order of **70 switches**. At `q = 1` that is 12 parameters against ~70 switches, about
**6 switches per parameter** — a fourfold improvement on the ratio that sank it [E1, from measured
half-lives]. Briefing 04 is right that the objection becomes survivable.

But survivability of the parameter count is not an effect size, and the repository's own measurement of
this specific driver is discouraging. Experiment 0002 records, as an external reference computed from
public data in briefing 01, that a **real-time yield-curve spread model** scores "about +0.06 over
1975–2025; **−0.10 after 1990 and −0.41 after 2006**; every interval spans zero" [measured,
`experiment.json` `external_references`]. This project's backtest runs **1994-03 to 2026-09**. The
driver TVTP would condition on has measured *negative* skill across the whole window the experiment is
scored on, and the repository wrote that down before any arm ran.

Set against that, the in-repo yardstick for changing how transitions are estimated remains A1's
**+0.0046**. A plausible effect of order +0.005 sits against a floor of 0.018 at best.

**Verdict: UNDERPOWERED.** And of the three it is the weakest: the mechanism's only available driver
has measured negative skill in exactly this sample, so even the sign of the plausible effect is not
established.

**Proof rung now, and the cheapest step up.** The parameter-cost claim is **proven** (arithmetic, 240q
→ 12q, verified here). The forecasting claim is **unproven**. The cheapest step up is *not* a TVTP
implementation — that is weeks of work behind an underpowered endpoint — but an **estimated** static
bound that would have to come out favourably before any implementation is justified: does the growth
chain's realised switch hazard depend on the term spread at all, in this sample?

**The protocol, for the precursor.** Register as a diagnostic.

- *What changes.* No model code. Take the filtered joint state path A4 already writes at each refit,
  marginalise to the growth chain, and form the monthly indicator `switched[t] = 1` when the
  most-likely growth state at `t` differs from `t−1`. Regress it on the term spread as it stood at
  `t−1`, by logistic regression, using only months whose spread was published by `t−1` (both legs are
  market rates, `publication_lag_days` 32, so the boundary is unambiguous).
- *What is measured.* The coefficient, its bootstrap interval using the same moving-block machinery and
  seed, and the in-sample improvement in log likelihood over a constant-hazard model.
- *The decision rule, fixed in advance.* **WORTH BUILDING** if the coefficient's 90% interval excludes
  zero *and* its sign is the economically motivated one (a flatter or inverted curve raises the hazard
  of leaving expansion). **NOT WORTH BUILDING** otherwise, and TVTP is then closed in this repository
  rather than deferred again — a third deferral with no measurement is a decision not to decide.
- *What is a failure.* An interval spanning zero is the expected outcome and is the finding. It would
  mean the only defensible driver carries no information about this chain's switches in this sample,
  which retires briefing 04's rank 2 for a few hours' work.
- *What it does not license.* A favourable result does **not** license a skill claim; it licenses only
  proceeding to a registration, which would still face the 0.018–0.030 floor.

**Cost.** No fitting, no walk-forward, no network: minutes. The filtered paths are already on disk
across 35 refits. It displaces nothing.

---

## 5. Proposal 3 — A state-count ablation main's gate will accept

### 5.1 Why no such count exists

The proposal asks for a single-chain ablation at "a count the regimes-exist gate admits", to separate
A4's structure from its granularity. The gate's floors are constants in
`models/state_selection.py` [measured]:

```
MINIMUM_EXPECTED_DURATION_IN_MONTHS = 3.0
MINIMUM_POPULATION_SHARE = 0.05
```

and `_choose` raises `StateSelectionError` when no candidate above one state clears both, with the
message "The data do not support regimes at this frequency; report that rather than lowering the
floors."

The binding floor is population, and the measured points bracket the answer [measured, main's
`check_gates.log` full-sample sweep and diagnostic 0005]:

| single-chain K | smallest population share | shortest visit | admissible |
|---:|---:|---:|---|
| 4 | 12.6% | 32.4 mo | yes |
| 5 | 11.9% | 19.1 mo | yes (wins on the full-sample panel) |
| 6 | **4.3%** | 17.8 mo | **no** — fails the 5% floor |
| 16 | **1.7%** | 5.6 mo | **no** — fails by a factor of three |

On the full-sample panel the largest admissible count is **5**. On the 518-month burn-in panel the rule
chose **6**, which is what the backtest runs [measured]. At **16** — the count that would match A4's
granularity — the smallest regime holds 1.7% against a 5% floor, and the look-ahead audit could not run
either, for the same reason [measured, diagnostic 0005 RESULT].

So the ablation the proposal asks for cannot exist. To separate the confound it must match A4's
sixteen cells; sixteen is measured to fail the gate by a factor of three; and every count that *does*
pass is at or below six, which is **what main already is**. An ablation at an admissible count is a
comparison of main against main. The only way to reach sixteen is to lower the floors, which is the
forbidden act under 0001 and which the gate's own error message refuses in words.

**Verdict: NOT FALSIFIABLE AS STATED.** There is no state count satisfying both conditions the proposal
imposes, so no experiment of the shape it describes can return either answer.

### 5.2 How to rewrite it — and this one is provable

The confound is symmetric, and the proposal attacks it from the side that is blocked. Main cannot be
pushed *up* to sixteen cells. **A4 can be pulled *down* to six.**

**Falsifiable form.** *Two chains at 2 × 3 — six joint regimes, exactly main's cell count — retain at
least half of A4's one-year paired gain against main. If the gain is structural it survives the
reduction; if it is granularity it collapses.*

This holds the thing that cannot be equalised on main's side fixed on A4's side instead. And it is
admissible: every row of A4's joint sweep table carries `admissible = True`, including (2,3) [measured].
The mechanism to fix the counts is the one A2 already used — A2's registered change was "The state
count is fixed at K = 4 for every fit", with the burn-in sweep still run and still feeding the
regimes-exist gate [measured, `experiment.json` A2]. Fixing per-chain counts at 2 × 3 is the direct
analogue of a change this project has already made and audited once.

**Detectable effect.** The arm differs from main by a state space, so `s` is an A4-class or slightly
smaller figure, 0.015 to 0.018:

- **90%: 0.025 to 0.030** · **90% as a family of one, which is also the confirm level: 0.025 to 0.030**
- 98.33% if registered inside a family of six: 0.036 to 0.044

**Plausible effect — and why this one is powered.** The power here does not come from resolving a
subtle difference. It comes from the two hypotheses predicting outcomes that are far apart:

- If the **structure** carries the effect, the 2 × 3 arm should retain most of A4's **+0.0590**, landing
  near +0.03 to +0.06.
- If **granularity** carries it, the 2 × 3 arm has six cells like main, ~112 months of effective sample
  per cell like main, and should land near **0.000**.

The separation between the two predictions is about **0.06**, against a detectable floor of **0.025 to
0.030** [derived]. The experiment discriminates by roughly a factor of two even at the pessimistic end
of `s`. That is the only one of the three proposals where the contrast the experiment must resolve is
larger than the interval it will produce.

The prior, from §3.3, is that it will come out GRANULARITY: at matched cell count on held-out
likelihood the factorial structure is already 0.0225 nats/month *worse* than main. A registered
experiment on the actual endpoint would convert that from **estimated** to **proven**, in the direction
the repository's own `limits` section says is the top open question about its only confirmed method.

**Proof rung now, and the cheapest step up.** Currently **estimated** — §3.3's held-out likelihood
decomposition is a measured static bound, obtained from files already on disk. The cheapest step up to
**proven** is one registered arm and one run.

**The protocol.** Registerable as written; nothing below needs a decision from me.

- *What changes.* One branch cut from `main` at `d95f3ce`, which since ADR 0010 already runs two chains
  at 4×4 by default — so the arm is now a *setting* change on the adopted method, not a re-implementation
  of it. The per-chain state counts are fixed at growth = 2, levels = 3 for every fit, overriding the
  sweep's choice exactly as A2 fixed K = 4. Fix it in
  `backtest/state_count_on_burn_in.py::state_count_for_the_backtest`, which since D15's closure
  (2026-09-20) is **the only place the question is answered** and is called by both the command-line
  interface and `look_ahead_audit` [measured]. That matters here specifically: D15 is the debt where an
  arm that fixed its count outside the sweep got audited with the default's count and never ran its own
  code, which is what happened to A2. Closing it is what makes this arm auditable at 2×3. The burn-in
  sweep still runs, is still reported, and still feeds 0001's regimes-exist gate; only its choice is
  overridden. Nothing else changes: same seed 20260908, same schedule, same panels, same shrinkage,
  same bootstrap, same audit.
- *Why 2 × 3 and not 3 × 2.* Fixed here, before the run: 2 × 3 gives the levels block the finer
  partition, which is the direction §3.3 measures as carrying 74% of the likelihood gain. 3 × 2 is a
  *second* hypothesis; if the owner wants both, the family is two and the confirm level is 95%.
- *Primary endpoint.* One-year paired difference in mean Brier skill score against **main**, computed
  by `forecast baseline compare --against main --paired --confidence-level 0.90 --confidence-level
  <confirm>`, identical statistic, bootstrap, block length and seed to 0002. **"Main" here means
  `baselines/main.json`**, which still holds the single-chain reference run `ad7fcc1affd0746a`, six
  states, and was not recaptured when ADR 0010 changed the default [measured]. This is the same file
  every 0002 arm was scored against, which is what makes A4's +0.0590 the right anchor for the rule
  below. If the owner recaptures the baseline to the adopted configuration before this runs, the anchor
  changes and the rule must be rewritten *before* the run, not after.
- *Secondary.* The same arm paired against **A4**, which measures the granularity increment directly.
  A4 is now the default, so capturing it needs no branch: `forecast baseline capture --name a4` on an
  unmodified checkout at `d95f3ce`. Also: five- and ten-year differences as harm guards; mean effective
  sample size per cell, which should return to roughly main's 112–118 from A4's 45–46 [measured]; free
  parameters; per-chain and joint λ₂.
- *The decision rule, fixed in advance.* Let `d6` be the one-year paired difference, 2 × 3 arm minus
  main. Mirroring diagnostic 0005's reading rule, inverted:
  - **STRUCTURE EFFECT** if `d6`'s one-year 90% interval lower bound is above zero **and** its point
    estimate is at least half of A4's, i.e. ≥ **+0.0295**. A4's account stands and the factorisation is
    doing the work.
  - **GRANULARITY EFFECT** if `d6`'s 90% interval includes zero, **or** its point estimate is below
    +0.0295. Most of what A4 buys is available from more cells alone, and any recommendation to adopt
    A4 must say so.
  - **INCONCLUSIVE** if the 2 × 3 fit fails to converge, any of the five gates fails, or the look-ahead
    audit exits non-zero. A model that cannot be fitted is not evidence either way.
- *Harm guard and VOID.* 0002's rules unchanged: HARMFUL if any horizon's 90% interval lies entirely
  below −0.02; VOID unless `forecast audit-look-ahead` exits 0 **and** an independent judged review
  finds no leak path. The arm reads no outcomes and does not touch the climatology, so it inherits none
  of A6's exposure.
- *What outcome I would call a failure.* Not GRANULARITY — that is the likely result and it is a
  finding, and the most valuable one available, because it would mean the project's only confirmed
  method is confirmed for a reason other than the one in its own hypothesis. The failure is
  **INCONCLUSIVE**: a 2 × 3 fit that will not converge or a gate that refuses it would leave the
  confound exactly where diagnostic 0005 left it, having spent a second run on it.
- *One-run rule.* One run, at these settings. A bug found afterwards may be fixed but may not change a
  setting, and both runs are reported.

**Cost.** `forecast check-gates` on a warm cache, which the arm worktree has — the repository documents
twenty to forty minutes with the walk-forward being nearly all of it [measured, `docs/RUNNING.md`];
`audit-look-ahead` about **359 seconds** on the A4 worktree [measured, its own audit record]; the two
paired comparisons a few minutes. **Call it an hour of wall clock and no network.** Implementation is a
settings change plus its wiring, on the pattern A2 already established. It displaces one slot of
reviewer attention — the judged look-ahead review is the scarce input, not the compute — and it
displaces nothing else, because on the analysis above neither of the other two proposals should be run.

---

## 6. Derived numbers

Everything labelled [derived] is reproducible from the two blocks below plus the files named. Both
scripts were run from
`/private/tmp/claude-501/-Users-jpmorgan-Projects-forecasting-the-future/fef399dd-82ac-469a-8700-323f793d878d/scratchpad/`,
which is temporary. **Decision for the owner:** if these are to stay re-checkable they should be
persisted to `research/briefings/derivations/`, as briefing 04's
`factorial_regime_algebra.py` was. They were not written there here, because this briefing was scoped
to add one file and nothing else.

### 6.1 The standard error and the detectable effect

Inputs are the `intervals` blocks of each arm's `paired.json` at `horizon_months == 12`. For each arm,
`HW(L) = (upper − lower)/2`; `s = HW(L) / z_{(1+L)/2}`; `MDE(L) = z_{(1+L)/2} · s`. Normal quantiles
used: `z_0.95 = 1.644854`, `z_0.983335 = 2.128045`, `z_0.991665 = 2.393980`. The over-identifying check
is `HW(0.9833)/HW(0.90)` against `1.4554`; measured values 1.4712, 1.4479, 1.4540, 1.4480, 1.4365,
1.4486, mean **1.4510**. Implied per-independent-observation dispersion, `σ = s·√31.5`: 0.061 for A1,
0.103 for A4.

### 6.2 Cross-block dependence — independently corroborated

```python
# For each of the 35 cached two-chain fits (hash fec79a040f9ca6f9) in the
# two-timescale-chains worktree: rebuild that refit's own point-in-time panel,
# take the joint responsibilities over the 16 states, and form the
# occupancy-weighted mean absolute within-state residual correlation.
model = regime_model_from_dictionary(json.loads(path.read_text()))
matrix = workspace.observation_matrix_as_of(as_of)          # Workspace.open(RunSettings(...))
observations  = matrix.standardised.to_numpy(dtype="float64")
probabilities = model.smoothed_state_probabilities(observations)
occupancy     = probabilities.sum(axis=0) / probabilities.sum()
for state in range(model.state_count):                       # 16 joint states
    weight    = probabilities[:, state]
    residuals = observations - model.means[state]            # columns: growth, inflation, rates
    # weighted correlation of residual columns i and j, accumulated as
    #   total[pair] += occupancy[state] * abs(corr_ij)
```

Result, mean over the 35 refits [derived]:

| responsibilities | growth~inflation | growth~rates | inflation~rates | discarded/kept |
|---|---:|---:|---:|---:|
| smoothed | **0.2046** | **0.2218** | **0.3419** | 0.623 |
| filtered | 0.2029 | 0.2095 | 0.3370 | 0.612 |

The repository's own derivation, committed during this session at
`research/briefings/derivations/within_state_cross_block_correlation.py` and run here, measures today's
selected model on today's 909-month panel with filtered responsibilities and returns **0.203 / 0.207 /
0.344**, ratios **0.59 and 0.60** [measured]. It shares no code with the computation above — different
panel, different model store, different loop — and agrees to within **0.015** on all three quantities.
That is the corroboration the claim needed.

Six alternative definitions were also tried, against the **retracted** triple 0.191 / 0.144 / 0.288:

| definition | growth~inflation | growth~rates | inflation~rates |
|---|---:|---:|---:|
| all refits, standardised, soft, absolute | 0.2046 | 0.2218 | 0.3419 |
| all refits, standardised, soft, **signed** | −0.0634 | +0.0918 | +0.1162 |
| all refits, standardised, **hard assignment** | 0.2145 | 0.2444 | 0.3498 |
| all refits, **natural units** | 0.2486 | 0.3125 | 0.5773 |
| **burn-in fit only** (1994-03-01) | 0.2463 | 0.2837 | 0.5260 |
| **today's fit only** (last refit) | 0.1807 | 0.1981 | 0.3547 |

None of them returns the retracted triple, and the spread across definitions — 0.18 to 0.31 on the
discarded pair, 0.35 to 0.58 on the kept one — is exactly why the replacement claim in `changes.json`
now states a **range, 0.51 to 0.67**, and says "the size is the finding and the third decimal is not"
[measured]. My pooled ratios, 0.61 (filtered) and 0.62 (smoothed), sit inside that range; so does the
committed script's 0.59–0.60. The retraction was the right call and the replacement is well supported.

### 6.3 The held-out likelihood decomposition

From A4's `check_gates.log` joint sweep table and main's burn-in choice line, both on the 518-month
burn-in panel ending 1994-01-01. Matched-cell comparison: (2,3) = −3.102579 against main's six-state
−3.0801, a difference of **−0.0225** nats/month. Within-family granularity: (2,2) = −3.461491,
(4,2) = −3.077161, (2,4) = −2.373005, (4,4) = −1.988675. Hence levels 2→4 at fixed growth = **+1.088486**;
growth 2→4 at fixed levels = **+0.384330**; total (2,2)→(4,4) = **+1.472816**; shares **73.9%** levels,
**26.1%** growth.

---

## 7. What I could not verify

**An integrity finding opened and closed during this briefing, and not by me.** At `15d6636`, where
this work started, the correlations 0.191 / 0.144 / 0.288 appeared in exactly two places —
`research/reports/impact-analysis/changes.json` and `research/reports/0002-slate/prose/arm-A4.html` —
both written by commits that touch only HTML (`90e4ff6`, `7e5a9ee`), with **no script in the tree that
computed them** [measured]. §6.2 could not reproduce them under six natural definitions. That was a
real finding: a number framing the next decisions that could not be re-derived.

It is now fixed, independently of this briefing. By `d95f3ce` the triple has been **retracted**, the
`limits` entry states a **range of 0.51 to 0.67** attributed to three named computations, the arm-A4
card carries the same correction, and a derivation is committed at
`research/briefings/derivations/within_state_cross_block_correlation.py` [measured]. Running it here
returns 0.203 / 0.207 / 0.344, and my independent computation over 35 cached fits returns
0.205 / 0.222 / 0.342 — agreement to within 0.015 on code that shares nothing (§6.2). **The claim is
now well supported and this briefing's role is corroboration, not correction.**

What survives as a caution is smaller and the repository already says it: the quantity moves with which
fitted model and which day's panel is measured — across the six definitions in §6.2 the discarded pair
ranges 0.18 to 0.31 and the kept one 0.35 to 0.58 — so it should be quoted as a size, never to three
decimals. The one thing still worth doing is making the committed script take the measurement it
reports: it reads `date.today()`'s panel and today's selected model, so its output will drift as the
panel grows, and a diagnostic whose number changes with the calendar should either pin its `as_of` or
print it prominently. It prints the panel end date, which is most of the way there.

**Wall-clock estimates are from documentation and one recorded run, not from timing anything here.**
`docs/RUNNING.md` states twenty to forty minutes for `check-gates` on a cold cache; the A4 arm's own
audit record states 359 s for `audit-look-ahead` [measured]. I did not run either. The one-hour figure
in §5.2 is an estimate built from those two.

**The ~70 switches on the growth chain is inferred, not counted.** It is scaled from main's measured 30
switches over 908 months by the ratio of the measured half-lives (30.7 / 12.6). The actual count is
available — it is one pass over the filtered growth-chain path A4 already writes — and the §4 protocol
computes it as a by-product. Labelled [E1] wherever it is used, and no verdict turns on it: proposal 2
is underpowered on the driver's measured skill regardless of the exact ratio.

**`proving/PROTOCOL.md` does not exist.** §1 reconstructs the project's pre-registration practice from
the two `experiment.json` files, the three drafts in `research/experiments-drafts/`, and
`score_slate.py`. If a written protocol exists elsewhere and differs, §1 is what should be corrected
first, because every power calculation here inherits its family-size and confidence-level reading.

**No external source was fetched.** Every figure is from this repository or the arms directory. Where
briefings 01, 02 and 04 are cited — the M-competition results, the Modée TVTP Monte Carlo, the
yield-curve reference numbers, the λ₂ identity — the citation is to *their* assessment, at the evidence
tier they assigned, and no new claim is made about any external paper.

**Claims I am asserting rather than measuring, flagged [E1]:** that diagonal transition coupling cannot
represent the contemporaneous dependence the correlation measurement describes; that A4's having
deleted the cross-block covariance while gaining +0.0590 bounds what restoring it could be worth; that
A1 is the right in-repo yardstick for a transition-matrix change; that the growth chain's switch count
scales with the inverse half-life; and that a family of one is defensible only when one hypothesis is
genuinely looked at. Each is reasoning from measured inputs, not a result.
