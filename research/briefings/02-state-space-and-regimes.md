# State-space and regime modelling: what is worth adding to the Gaussian HMM

Research briefing · compiled 2026-09-12 · for `forecasting-the-future`

**Scope.** The project fits a five-state Gaussian HMM to monthly US growth, inflation and the
three-month bill, on point-in-time data, walk-forward, against a pre-registered decision rule
(`proving/experiments/0001-regime-conditional-forecast-skill/experiment.json`). 908 monthly
observations; the most likely regime changes about 30 times. The transition matrix's second
eigenvalue modulus is 0.983 (half-life 41 months), nine of twenty off-diagonal entries are
exactly zero, and the reported information horizon is five years. The question is which
extensions to the plain HMM earn their complexity.

**Evidence discipline.** Every source cited below was opened. Where only an abstract or a
repository record could be opened, that is said at the citation. Where a number came from a
search snippet rather than a fetch, it is not used. Claims are labelled by evaluation class:

- **(a)** in-sample, full-sample parameters
- **(b)** pseudo-out-of-sample — recursive/rolling re-estimation, but revised data and a model
  form chosen after seeing the sample
- **(c)** genuine real-time — vintage data *and* a specification fixed before the test window

This project is one of the very few things in this briefing that is structurally **(c)** on the
data axis. Almost nothing published is. That is worth stating in the paper, because it makes the
project's numbers look worse and be comparable to almost nothing else.

---

## Executive summary

**1. The single most valuable finding is diagnostic, not an extension.** The project's λ₂ = 0.978–0.983
is far outside the published range for business-cycle regime models, and matches almost exactly
the published range for *volatility* regimes. Converted to a common footing:

| Source | Freq. | p₁₁ | p₂₂ | λ₂ = p₁₁+p₂₂−1 | Half-life | Monthly-equiv. λ₂ |
|---|---|---:|---:|---:|---:|---:|
| Hamilton 1989, via EViews docs | quarterly | 0.90 | 0.75 | 0.650 | 1.6 q ≈ 4.8 mo | 0.866 |
| Hamilton 1989, via statsmodels replication | quarterly | 0.9041 | 0.7547 | 0.659 | 1.7 q ≈ 5.0 mo | 0.870 |
| Chauvet–Hamilton 2006, NBER-implied (Hamilton HB Table 1) | quarterly | 0.95 | 0.78 | 0.730 | 2.2 q ≈ 6.6 mo | 0.900 |
| Chauvet–Hamilton 2006, GDP-alone MLE | quarterly | 0.92 | 0.74 | 0.660 | 1.7 q ≈ 5.0 mo | 0.871 |
| Doz–Ferrara–Pionnier MS-DFM, **growth** chain, posterior | monthly | 0.91 | 0.98 | 0.890 | 5.9 mo | — |
| Ang–Bekaert 2002, equities | monthly | 0.8552 | 0.9804 | 0.836 | 3.9 mo | — |
| Ang–Timmermann 2011 Table 1, 3-month T-bill | monthly | 0.8789 | 0.9499 | 0.829 | 3.7 mo | — |
| Ang–Timmermann 2011 Table 1, US equities | monthly | 0.9770 | 0.9512 | 0.928 | 9.3 mo | — |
| Kritzman–Page–Turkington, inflation | monthly | 0.98 | 0.95 | 0.930 | 9.6 mo | — |
| **Doz–Ferrara–Pionnier MS-DFM, *volatility* chain, posterior** | monthly | **0.99** | **0.98** | **0.970** | **22.8 mo** | — |
| **This project** | monthly | — | — | **0.978–0.983** | **31–41 mo** | — |

Every *growth/cycle* chain in the literature has a monthly-equivalent λ₂ between 0.83 and 0.93.
The project's 0.983 sits with the *volatility/level* chains. The regime table in `docs/RESULTS.md`
says the same thing in words — "the second regime is stagflation and the first is the zero-rate
world after 2008" are secular monetary-environment regimes, not expansions and contractions.
**The model is not a business-cycle model and should stop being read as one.** Nothing is broken;
but it means the business-cycle literature's persistence estimates are the wrong benchmark, and
the right comparison — Doz–Ferrara–Pionnier's volatility chain at λ₂ = 0.97 — is a good deal
closer and still below 0.983.

**2. The horizon result is not a limitation of this implementation. It is the algebra of the
model class, and Hamilton wrote it down.** Hamilton's Handbook chapter, eq. (3)–(4), shows the
regime-mean process is *exactly* an AR(1) with coefficient λ = p₁₁ − p₂₁ = p₁₁ + p₂₂ − 1 — the
second eigenvalue — and the k-step regime forecast is Pᵏξ̂ₜ. Krolzig (2000) eq. (21) gives the
same thing for the multivariate case: ŷ_{t+h|t} = E[X_{t+h}]β̄ + E[X_{t+h}]B**F**ʰξ̂_{t|t}, where
F's eigenvalues are the persistence parameters, and he states that "for h → ∞ the forecasts
ŷ_{t+h|t} converge to the unconditional mean." The project's five-year information horizon is a
theorem about this model class, not a disappointing empirical result. **Cite Hamilton eq. (3)–(4)
and Krolzig eq. (21) in the paper; they turn the finding from a confession into a derivation.**

**3. Of every extension considered, exactly one has a clearly positive expected-gain-to-cost
ratio: a sticky Dirichlet prior on the transition matrix.** It is standard practice with fetched
precedent in macro (Kim–Nelson 1998 via Doz–Ferrara–Pionnier's Beta(90,7)/Beta(470,7) priors) and
in machine learning (dynamax's Dir(β·1 + κ·e_k); hmmlearn's `transmat_prior`), it fixes a defect
the project has already logged (D1), and it *reduces* rather than increases overfitting risk. Its
correct form is **sticky**, not flat: a symmetric Dirichlet penalises the diagonal as hard as the
off-diagonal, which is why the project's own sensitivity table shows a flat Dirichlet(2) cutting
the half-life from 41 to 10 months. That over-corrects.

**4. The second most valuable extension is to split the single chain into two independent chains
— one for the conditional mean, one for the conditional variance.** This is the Doz–Ferrara–Pionnier
structure (Sₜ and Vₜ, "two independent first-order Markov-Switching processes"), and the
literature's strongest and most replicated in-sample finding supports it: Sims & Zha (2006) find
variances-only switching beats every coefficient-switching specification by ≥50 log points of
marginal data density; Ang & Timmermann (2011) report that across equities, interest rates and FX
"we cannot reject that the regime-dependent means are equal to each other, µ₀ = µ₁, but
overwhelmingly reject that σ₀ = σ₁." The project's five regimes are currently labelled by their
emission *means*. If they are in fact separated mostly by covariance, the labels — and the
conditional base rates read off them — are resting on the weaker half of the signal.

**5. Almost everything else is negative or marginal for this project specifically.** MS-VAR nearly
doubles the parameter count for a result Krolzig himself called "disappointing." TVTP adds 20
parameters per driver against an effective sample of ~30 observed switches, and the best current
Monte Carlo evidence says TVTP misspecification changes one-step point forecasts by under 1%.
MS-GARCH wins convincingly, but on *daily equity tails*, not monthly macro. Particle filters are
strictly worse than the exact HMM filter for a discrete-state Gaussian-emission model and break
determinism. The sticky HDP-HMM's *good idea* (the κ self-transition bias) can be imported for
fifty lines without importing its MCMC.

**6. One factual correction the project should record.** ADR 0004 rejects statsmodels partly on
the grounds that "it has the same smoothed-output problem." That is not correct.
`MarkovSwitchingResults` exposes `filtered_marginal_probabilities` *and*
`predicted_marginal_probabilities` (p(Sₜ | y_{1:t−1}) — arguably the more honest object for a
walk-forward backtest than the filtered one) alongside `smoothed_marginal_probabilities`, and it
supports time-varying transition probabilities via `exog_tvtp`. The *other* reasons in ADR 0004
(determinism control, no dependency, exact control of the forward pass) still stand, and
statsmodels has no multivariate regime switching, so the decision survives — but the stated reason
is wrong and should be amended rather than left in the record. hmmlearn, by contrast, genuinely
has no filtered API and *is* disqualified.

---

## Ranked extensions, with cost-benefit

Ranked by (expected gain) / (implementation cost + overfitting risk). Cost is in the project's own
terms: lines of code in `models/`, new dependencies, new pre-registration required.

### Rank 1 — Sticky Dirichlet prior on the transition matrix · **DO THIS**

**Gain: high. Cost: low. Overfitting risk: negative (it reduces it).**

**What it solves that plain Baum–Welch does not.** The M-step ratio of expected counts is
unregularised maximum likelihood. From 908 observations the model currently asserts that nine
specific regime transitions are *impossible*. The honest sample size for the transition matrix is
not 908 — it is the ~30 observed switches, spread over 20 off-diagonal cells, averaging 1.5 each.
Under a uniform Poisson(1.5), the expected number of empty cells is 20·e^{−1.5} = **4.5**; with any
realistic heterogeneity, nine is entirely unremarkable. **The nine zeros are a small-sample
artefact of a 30-event sample, not a structural finding about the US economy.** They also bias λ₂
upward: forbidden transitions can only make the chain more persistent, so the 41-month half-life
and the five-year information horizon are, as D1 already suspects, optimistic.

**What standard practice is.** Two fetched precedents, one from each side of the field.

*Macro.* Doz, Ferrara & Pionnier, *Business cycle dynamics after the Great Recession: An Extended
Markov-Switching Dynamic Factor Model* (PSE working paper, US monthly 1970M01–2017M12), place
conjugate Beta priors on every transition probability in a Gibbs sampler and calibrate them to the
NBER record: "Following Kim and Nelson (1998), we rely on informative priors reflecting the number
and length of recessions over the estimation sample: u^S₀₀ = 90; u^S₀₁ = u^S₁₀ = 7; u^S₁₁ = 470.
The NBER estimates that the US economy has known seven recession episodes between January 1970 and
December 2017, covering 90 months in total." Posterior update is the textbook conjugate one,
PrS11 | S ~ beta(u₁₁ + n₁₁, u₁₀ + n₁₀). Their reported prior/posterior pairs: Beta(90,7) → prior
mean 0.93, posterior 0.91 (sd 0.023); Beta(470,7) → prior 0.99, posterior 0.98 (sd 0.0046). **Note
the prior strength: 574 pseudo-counts against 576 months of data.** An informative prior on a
transition matrix is not a light touch in this literature; it is roughly as heavy as the sample.
[fetched: https://extranet.parisschoolofeconomics.eu/docs/doz-catherine/doz-ferrara-pionnier-_-business-cycle-dynamics-after-the-great-recession--an-extended-ms-dfm-(pse-wp).pdf]

*Machine learning.* dynamax states the prior explicitly as `p(A) = ∏_{k=1}^K Dir(A_k | β·1_K + κ·e_k)`
with `transition_matrix_concentration` = β and `transition_matrix_stickiness` = κ, the latter
documented as biasing "the prior toward transition matrices with larger values along the diagonal";
the M-step is literally `tfd.Dirichlet(self.concentration + expected_trans_counts).mode()` with
default `concentration=1.1`. hmmlearn exposes `transmat_prior`, "Parameters of the Dirichlet prior
distribution for each row of the transition probabilities." Gauvain & Lee established MAP-EM for
HMMs with exactly this structure — a "product of a Dirichlet density and gamma-normal densities" —
motivated by "the insufficient training data problem" and offered as "a unified approach for
parameter smoothing."
[fetched: https://probml.github.io/dynamax/api.html · https://aclanthology.org/H91-1053.pdf]

**Why *sticky* and not flat, with arithmetic.** A symmetric Dirichlet(α) adds α−1 pseudo-counts to
the diagonal as well as the off-diagonal, so it shrinks persistence at the same time as it fills
the zeros. That is why D1's own sensitivity table shows Dirichlet(2) taking λ₂ from 0.983 to 0.931
and the half-life from 41 to 10 months — a 4× cut in persistence that no external evidence
supports. The sticky form separates the two jobs: β fills the zeros, κ encodes a belief about
duration. With K = 5 and prior-mean visit length D, the hyperparameters are

    κ = β·(D·(K−1) − K),    prior row strength M = K·β + κ = β·D·(K−1)

**A practical constraint worth knowing before implementing.** MAP-EM takes the *mode* of the
Dirichlet, which requires α > 1 in every cell, hence β > 1. At K = 5, that forces the prior row
strength to at least β·D·(K−1):

| prior mean visit D | β = 1.05 | β = 1.5 | β = 2.0 |
|---|---:|---:|---:|
| 24 months | 101 | 144 | 192 |
| 30 months | 126 | 180 | 240 |

against ~180 expected transitions per row. **Any MAP-EM prior that both eliminates the zeros and
encodes a realistic two-to-three-year visit must be roughly as heavy as the data** — which is
exactly where Doz et al. landed, so this is normal, but it should be a conscious choice rather
than a surprise. The alternative is to take the posterior *mean* rather than the mode, which is
well-defined for β < 1 and lets a much weaker prior do the job:

| β, κ (posterior mean, D = 30, strength 60) | off-diagonal floor at n_i ≈ 180 | implied expected wait |
|---|---:|---:|
| β = 0.50, κ = 57.5 | 0.0021 | ~480 months |

That is the right answer: the forbidden transitions become *rare*, not *impossible*, which is all
the data can support.

**Calibrate κ externally, not to preserve the current answer.** It would be easy, and wrong, to
pick κ so that λ₂ stays at 0.983. The external evidence (table in the executive summary) puts
monthly λ₂ for slow macro state variables at 0.93–0.97, i.e. visits of 10–23 months rather than
31–42. A prior centred on D = 24–30 months is defensible from published estimates; a prior centred
on D = 41 is defensible only from the unregularised fit it is supposed to correct. **Expect the
information horizon to shorten. That is the point of the exercise, and it strengthens rather than
weakens the paper's thesis.**

**Pre-registration consequence.** Adding a prior changes the model, so the five gates must be
re-run and the change recorded. It does not change any threshold, so it is not the forbidden act.
The honest framing is: D1 was raised before the prior went in, the sensitivity was published in
advance in `docs/TECHNICAL_DEBT.md`, and the direction of the effect was predicted. That is a
stronger position than most published work occupies.

**Implementation.** ~50 lines in the existing M-step; no new dependency; determinism unaffected.
Test: the prior with β = 1, κ = 0 must reproduce the current fit bit-for-bit.

---

### Rank 2 — Separate the mean chain from the variance chain · **DO THIS, after Rank 1**

**Gain: high. Cost: medium. Overfitting risk: low (it adds one chain, not K² parameters).**

**What it solves.** A single chain must explain both "growth is low" and "everything is volatile"
with the same state variable. The literature's most robust in-sample finding is that these are
different processes with different speeds.

- **Sims & Zha (2006)**, "Were There Regime Switches in U.S. Monetary Policy?", monthly US
  1959:1–2003:3, six variables, 13 lags. Log marginal data densities: constant parameters
  **12,998.20**; best variances-only model (9 states) **13,544.07**; best monetary-policy
  coefficient-switching model (4 states) **13,480.18**. Variances-only beats constant by ~546 log
  points and beats the best coefficient-switching model by **63.9**, against their own stated
  MCMC error of ±2 to ±4. Their mechanism sentence matters for this project: ignoring stochastic
  volatility "strongly biases — toward a finding of changed parameters — tests of the stability of
  the forecasting equations." **Class (a).**
  [fetched: https://conference.nber.org/confer/2004/si2004/me/sims.pdf — April 2004 conference
  version, not the 2006 AER text; verify table numbers against the AER before external citation]
- **Ang & Timmermann (2011)**, NBER WP 17182, *Regime Changes and Financial Markets*, Table 1,
  monthly: "regimes are mostly identified by volatility. In all cases, conditional on there being
  two regimes, we cannot reject that the regime-dependent means are equal to each other, µ₀ = µ₁,
  but overwhelmingly reject that σ₀ = σ₁." **Class (a).**
  [fetched: https://www.nber.org/system/files/working_papers/w17182/w17182.pdf]
- **Doz, Ferrara & Pionnier** run exactly the two-chain structure: "Sₜ and Vₜ are two independent
  first-order Markov-Switching processes." Their posteriors separate cleanly — growth chain
  λ₂ ≈ 0.89 (half-life 5.9 months), volatility chain λ₂ ≈ 0.97 (half-life 22.8 months).
- The out-of-sample evidence is weaker but real and, importantly, it is *density* evidence, which
  is what a Brier-scored project cares about. **Clark (2011)**, *Real-Time Density Forecasts from
  VARs with Stochastic Volatility*, **class (b) on real vintages from the Philadelphia Fed RTDSM**,
  1985–2008:Q3: adding SV to a BVAR improves the average log score from 8.536 to 7.350 at h=1Q and
  10.533 to 9.724 at h=2Q; Amisano–Giacomini tests give p = 0.000 at 1Q, 0.022 at 2Q, and
  **0.380 at 1Y** — the gain does not survive to a one-year horizon except for inflation, where it
  grows (0.209 at 1Y, 0.233 at 2Y, both significant). Point-forecast gains are small.
  [fetched: https://www.chicagofed.org/-/media/others/research/research-calendar-attachments/seminars-2009/sem-clark012910-pdf.pdf]

**Why this is the right second move for *this* project.** The project's λ₂ = 0.983 matches the
published *volatility* chain, not the growth chain. If a single chain is currently being pulled to
the volatility timescale, the growth signal — which is where the one-year skill of +0.232 lives,
and specifically the +0.390 on any-time-within-horizon questions — is being carried by a chain
tuned to the wrong frequency. Splitting them is the direct test: fit Sₜ (fast, growth) and Vₜ
(slow, volatility/level) as independent chains and see whether the one-year skill rises and the
ten-year honesty gate fails *harder*, which is the predicted direction.

**Cheap precursor, do this first.** Before writing any new model: measure how much of the
five-regime separation is in the emission means versus the covariances. A Kullback–Leibler or
Bhattacharyya decomposition between each pair of fitted emission densities, split into the
mean-difference term and the covariance term, costs a few hours and either motivates this whole
rank or kills it. It also directly answers whether `state_labelling.py`'s mean-based labels are
describing the dominant axis of separation.

**Cost.** The Kim (1994) filter for a product chain over K_S × K_V states is the existing forward
pass over a larger state space with a structured transition matrix — real work, but the algorithm
is unchanged. Parameter count: two chains of 2–3 states each are far cheaper than one chain of 5.

---

### Rank 3 — Interval estimates on λ₂ and honest treatment of K · **DO THIS; cheapest item here**

**Gain: medium-high (credibility). Cost: very low. Overfitting risk: none.**

The project reports λ₂ = 0.983 as a point estimate and the information horizon as a consequence of
it. Two fetched results say that point estimate deserves an interval.

**The regime count is not identified by the criteria used.** Hamilton's Handbook chapter is
explicit that the BIC used in the `regimes_exist` gate has no asymptotic justification here:
"Popular methods such as Schwarz's (1978) Bayesian criterion rely for their asymptotic
justification on the same regularity conditions whose failure causes the likelihood ratio statistic
to have a nonstandard distribution." Under the null of N regimes the extra regime's parameters are
unidentified, the score is identically zero, the information matrix is degenerate and the
transition probabilities sit on the boundary. Kuan's lecture notes state the same for the two-state
case, and note the useful corollary that the null of *no* persistence is exactly
`H₀: p₀₀ + p₁₁ = 1`, i.e. **λ₂ = 0** — the second eigenvalue is the persistence parameter, and
testing for it is the non-standard problem.
[fetched: https://hoover-s3-website.s3.us-west-2.amazonaws.com/s3fs-public/hamilton-handbook_regimes.pdf ·
https://homepage.ntu.edu.tw/~ckuan/pdf/Lec-Markov_note.pdf]

**Kasahara & Shimotsu (arXiv:1801.06862, UBC / University of Tokyo)** show contiguous alternatives
approach the null at rate n^{−1/8}, and on quarterly US GDP per capita 1960Q1–2014Q4 report that
LRT selects M = 4, AIC selects M = 3 and **BIC selects M = 1** under a common-variance
specification. Three criteria, three answers, spanning "four regimes" to "no regime structure at
all," on 55 years of US macro data. **Class (a).**
[fetched: https://arxiv.org/pdf/1801.06862]

**Replication spread on persistence specifically.** Hamilton's own 1989 model gives quarterly
p₁₁ = 0.90 (EViews docs) or 0.9041 (statsmodels replication, consistent with its reported
10.43-quarter duration) depending on the replication. Kritzman, Page & Turkington report standard
errors of **5–15 percentage points** on two-state persistence estimates fitted to 60+ years of
monthly data — their economic-growth event regime is 0.68 with a 95% interval spanning roughly
0.46–0.90. Persistence is the parameter that replicates worst.

**What to do.** The moving-block bootstrap machinery already exists for the skill gates. Run it on
the fitted λ₂ and publish the interval. Report the state-count sweep with *all three* criteria
(held-out log likelihood, BIC, and an LRT-flavoured comparison) rather than the two currently
gated, and say plainly that K = 5 is a modelling choice the data cannot adjudicate — which the
pre-registration is the right place to have fixed, and did. Add a one-paragraph
episode-alignment check: do the five inferred state paths line up with recognisable macro
episodes? `docs/RESULTS.md` already says they do ("the second regime is stagflation and the first
is the zero-rate world after 2008; neither was put there by hand"). Make that an explicit
validation rather than an aside — it is the standard defence in the literature (Guidolin &
Timmermann validate against 1979–82, 1984, 1987, 1990/91, 2002).

---

### Rank 4 — Time-varying transition probabilities (Filardo, TVTP) · **DEFER**

**Gain: low at K = 5. Cost: medium. Overfitting risk: high.**

**What it solves.** In a fixed-P chain, the probability of leaving a regime is constant. TVTP makes
pᵢⱼ a function of observables: Hamilton's Handbook eq. (14),
`Prob(sₜ = j | sₜ₋₁ = i, …, Ωₜ₋₁) = pᵢⱼ(xₜ₋₁; λ)`, citing Diebold, Lee & Weinbach (1994) and
Filardo (1994). Filardo's own abstract (JBES 12(3), 299–308) reports "high correlation between the
evolution of the phases inferred from the model and traditional reference cycles for monthly
output data" and that "many of the economic variables that determine the time-varying probabilities
help to predict turning points." **Class (a).**
[fetched: econpapers/ideas records and the statsmodels Filardo example; the T&F full text returned 403]

**Why it is the wrong move here, quantitatively.** A logistic TVTP with q drivers adds K(K−1)·q
parameters. At K = 5 that is **20 new parameters per driver**, to be estimated against an effective
sample of **~30 observed regime switches**. That is not a close call.

**And the best current evidence says the payoff is in characterisation, not forecasting.**
Modée, Li, Westgaard & Bethuelsen (University of Bergen / NTNU), *Multi-regime Markov-switching
models with time-varying transition probabilities: An application to U.S. Treasury yields*
(arXiv:2605.14976v2, 7 Aug 2026, submitted to *International Journal of Forecasting*) run a
systematic K = 2,3 Monte Carlo across three TVTP specifications and report: "Across all DGPs and
sample sizes, the forecast metrics are remarkably stable: MAFE and MSFE differ by **less than 1%**
whether the correctly specified or a misspecified model is fitted… The one-step-ahead forecast
ŷ_{t|t−1} = Σᵢ µ̂ᵢ P̂(zₜ = i | I_{t−1}) is dominated by the regime means µ̂ᵢ, which are robustly
recovered under all specifications." They also find "the TVTP driving coefficients are harder to
identify" and that the GAS score coefficient "appears to be statistically non-identifiable, due to
a ridge in the likelihood surface linking it to the regime variance." Their own conclusion: "the
value of correct specification lies in characterizing the regime dynamics rather than in
short-horizon forecasting."

Their caveat cuts the other way for this project and should be recorded: "The study considers only
one-step-ahead point forecasts, which is precisely the setting where transition dynamics matter
least. At longer horizons the transition matrix is applied repeatedly and misspecification would
likely compound into visible differences. Density and interval forecasts would also discriminate
more sharply." This project forecasts *probabilities* at 12, 60 and 120 months — exactly the
setting they say they did not test. So TVTP is not refuted here; it is unmeasured.

*Source assessment:* four authors with named institutional affiliations at the University of Bergen
and NTNU, an open-source R package, 18 pages, submitted to a real journal, arXiv date four months
before today. Nothing suspicious. It is a preprint and should be labelled as one.
[fetched: https://arxiv.org/abs/2605.14976 and the v2 PDF]

**If it is ever done**, the only defensible version is a heavily restricted one: collapse to a
two-state "stressed / not" chain (2 new parameters per driver, not 20), use a single driver with a
strong prior reason to be there (the term spread is the literature's default), and pre-register it
as a separate experiment. statsmodels supports this directly via `exog_tvtp`.

---

### Rank 5 — Mixed-frequency / nowcasting front end · **DEFER; high cost, narrow benefit**

**Gain: medium at one year only. Cost: high. Overfitting risk: medium.**

**What it would buy.** Nothing at five or ten years. At one year it could sharpen the filtered
state at the moment a forecast is issued, which is where the project's skill already is
(+0.232 mean, +0.390 on any-time questions).

**The closest precedent is very close indeed, and it is honest.** Chauvet & Piger (2008),
"A Comparison of the Real-Time Performance of Business Cycle Dating Methods," *JBES* 26(1), 42–49,
run a Markov-switching **dynamic factor** model on four monthly coincident series (payrolls, IP,
real personal income ex transfers, real manufacturing and trade sales) on **genuine real-time
vintages** — IP and employment from the Philadelphia Fed archive, the other two hand-collected —
with a decision rule fixed in advance (declare a phase shift when P(Sₜ=1 | ·) ≥ 0.8 for three
consecutive months). **This is the only class (c) precedent in the whole briefing.** Results:
turning-point dates "usually within one month, never more than two months" from the NBER date; **no
false positives**; troughs identified on average **249 days (~8 months)** before the NBER
announcement. And the honest half: "neither method improves on the speed of identifying peaks."
[fetched: https://jeremypiger.com/assets/files/Chauvet_Piger_2008_JBES.pdf]

**A trap worth writing into a test.** The FRED series `RECPROUSM156N`, "Smoothed U.S. Recession
Probabilities," is derived from that model but is **smoothed** — two-sided, full-sample. It is not
the filtered object the 2008 real-time paper evaluated, and under this project's rules it cannot be
used as a target, a feature, or a benchmark. Same model, different object.
[fetched: https://fred.stlouisfed.org/series/RECPROUSM156N]

**What the nowcasting literature actually measures, and the rung it sits on.** This matters more
than any individual method, because it is the best available calibration for how much a published
forecasting number is inflated by evaluation design.

*Atlanta Fed GDPNow* (Higgins, FRB Atlanta WP 2014-7): bridge equations plus a dynamic factor model
plus Bayesian VARs over 200+ series, 13 GDP subcomponents, BEA chain-weighting, no judgment. On a
**pseudo-out-of-sample** exercise with revised data and a stylised release calendar, GDPNow's RMSFE
is **1.15** against 1.73 for the best statistical benchmark (a Schorfheide–Song mixed-frequency
BVAR), 1.95 for a factor-augmented AR(2) and 2.43 for a rolling AR(2). Higgins says plainly: "due
to the data intensive nature of the GDPNow model, it is not feasible to use real-time data for a
long sample." On the **genuinely real-time** record (2011Q3–2014Q1, N = 11), GDPNow's RMSE is
**0.94 against the Blue Chip consensus's 0.81** — it loses to a human consensus published three
weeks earlier. His verdict: "it is probably safe to say that the GDPNow model forecasts are not as
accurate as the best judgmental forecasts." By 2019 the gap had closed (MAE 0.53 vs 0.56 over
2014Q2–2019Q2) but GDPNow's forecast standard deviation is 1.07 against Blue Chip's 0.69, i.e. it
is nearly as volatile as the target itself.
[fetched: https://www.econstor.eu/bitstream/10419/101002/1/wp1407.pdf ·
https://auber.org/wp-content/uploads/2019/11/HigginsOct13th2019GDPNowPresentationC.pdf]

*NY Fed Staff Nowcast* (Bok, Caratelli, Giannone, Sbordone & Tambalotti, FRBNY SR 830, 2017 →
*Annual Review of Economics* 2018): mixed-frequency dynamic factor model in state-space form,
Kalman filter, news decomposition; Mariano–Murasawa (2003) aggregation; Bańbura–Modugno (2014) for
arbitrary missing data. Backtested on reconstructed weekly vintages, 2000–2017. Suspended
September 2021 when pandemic volatility destabilised estimation; relaunched September 2023 as
"Nowcast 2.0" with a COVID factor fixed to zero outside March–September 2020 and stochastic
volatility with outlier scaling. **The most transferable sentence in the whole nowcasting
literature is 2.0's footnote 3**: "This reconstruction provides a representation of the predictions
that would have been obtained in real time using this updated model framework. We acknowledge that
the techniques used in this nowcasting model were developed more recently; therefore, we describe
these forecasts as 'historical reconstructions'." Vintage-correct data closes the data-snooping
channel; it does not close the specification-search channel. **This project should say the same
about its own backtest.** Nowcast 2.0's own numbers are modest: pre-pandemic final MSE 1.3 vs the
legacy model's 1.5, and at one month out the *legacy* model is better (1.4 vs 1.5).
[fetched: https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr830.pdf ·
https://www.newyorkfed.org/medialibrary/media/research/blog/2023/NYFed-Staff-Nowcast_technical-paper]

*Bańbura & Modugno* (ECB WP 1189 → *JAE* 29(1), 133–160, 2014) give the ragged-edge machinery — EM
for factor models with arbitrary missing-data patterns, which handles mixed frequency, unequal
sample starts and publication delays in one mechanism. Two results worth carrying: missingness is
cheap (idiosyncratic AR MAE 0.135 → 0.021 as T goes 50 → 1000 with 20% missing, essentially the
same as with no missing data), and **more series is not better** — their ~100-series model is worse
than their ~15-series model at Q(0)M3 (0.23–0.25 vs 0.19–0.20 RMSFE). And their own honest label,
footnote 24: "The real-time vintages are not available for all the variables of interest and whole
evaluation period, therefore the exercise is 'pseudo real-time'. That is, we use the final figures
as of October 2009, but we observe the real-time data availability." **Class (b) precisely defined.**
[fetched: https://www.ecb.europa.eu/pub/pdf/scpwps/ecbwp1189.pdf]

*MIDAS.* Ghysels, Santa-Clara & Valkanov's foundational result is an **asymptotic efficiency**
theorem, not a measured forecast gain: "MIDAS regressions projecting Yₜ onto Xₜ^(m) will always
improve efficiency when compared to distributed lag models involving projections of Yₜ onto Xₜ^(1).
Hence, the common practice of aggregating all the data to the common least frequently sampled
process will always be less efficient." They state the symmetric caveat too. **There are no
out-of-sample macro RMSEs in the source paper.** Bai, Ghysels & Wright's comparison with state-space
models concludes: "Kalman filter forecasts are typically a little better, but MIDAS regressions can
be more accurate if the state-space model is mis-specified or over-parameterized." Since this
project already *is* a state-space model, MIDAS offers a robustness check, not an upgrade.
[fetched: https://rady.ucsd.edu/_files/faculty-research/valkanov/midas-touch.pdf ·
https://kenaninstitute.unc.edu/publication/state-space-models-and-midas-regressions/ — note an
attribution conflict on that record, see "What I could not verify"]

**How to add higher-frequency data without creating look-ahead.** Three fetched, concrete rules:

1. **Vintages, not stylised calendars.** ALFRED ("Economic data time travel since 2006", 1.7M+
   series) and the Philadelphia Fed Real-Time Data Set (24 variables, monthly and quarterly
   vintages, created by Croushore & Stark, *J. Econometrics* 105, 2001) are the two archives. The
   FRED-MD vintage archive (`stlouisfed.org/research/fred-md/monthly/YYYY-MM.csv`) begins
   **1999-08** — anything assembled before that date is revised data wearing a vintage label, which
   matters a great deal for a project whose walk-forward starts in December 1971.
   [fetched: https://alfred.stlouisfed.org/ ·
   https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/real-time-data-set-for-macroeconomists ·
   https://www.columbia.edu/~sn2294/papers/freddata.pdf]
2. **Revisions do not merely add noise; they change conclusions in both directions.** Croushore's
   *Frontiers of Real-Time Data Analysis* (*JEL* 49(1), 2011) collects the cases: Diebold &
   Rudebusch (1991) find the index of leading indicators' predictive ability "in real time is much
   less than with latest-available data"; Koenig (2003) finds the markup predicts inflation with
   latest-available data "but not in real time"; Croushore (2005) finds consumer confidence has no
   out-of-sample power for consumption spending though revised data and in-sample fitting both
   inflate it. But Molodtsova (2008) finds exchange rates predictable *only* with real-time data.
   And Bernanke & Boivin (2003) find that for large factor models it "does not have much impact" —
   averaging washes out idiosyncratic revision error.
   [fetched: https://facultystaff.richmond.edu/~dcrousho/docs/croushore%20real%20time%20frontiers%2009dec.pdf]
3. **McCracken & Ng's warning:** "We have not made outlier adjustments to the data." Outlier
   handling is the user's problem and post-2020 it is a large one.

**Verdict.** High cost, benefit confined to the horizon that already passes, and a real risk of
importing the 1999-08 vintage floor into a 1971-start backtest. Revisit only if the one-year result
is the thing being pushed.

---

### Rank 6 — MS-VAR (regime-switching autoregressive dynamics) · **DO NOT**

**Gain: low. Cost: high. Overfitting risk: high.**

**Parameter arithmetic against this project.** Current model: 20 transitions + 15 means + 30
covariance parameters = **65**, against 908 × 3 = 2,724 data points, i.e. 42 observations per
parameter. Adding a VAR(1):

| Specification | Parameters | Obs/param |
|---|---:|---:|
| current (K=5, N=3, no lags) | 65 | 41.9 |
| MS-VAR(1), regime-invariant AR | 74 | 36.8 |
| MS-VAR(1), switching AR | 110 | 24.8 |
| MS-VAR(2), switching AR | 155 | 17.6 |

**The literature's own verdict, from the person who wrote the book on MS-VARs.** Krolzig (2000),
*Predicting Markov-Switching Vector Autoregressive Processes* (Nuffield College, Oxford), runs both
a Monte Carlo with Hamilton's own fitted model as the DGP and an empirical comparison:

- Monte Carlo, DGP = Hamilton's MSM(2)-AR(4): "the MS-AR is clearly best at short horizons on
  RMSE… The improvement in the forecast performance is relatively small and occurs only at short
  horizons." I.e. **even when the regime model is literally true, the gain is small and short-lived.**
- Empirically: "compared to results of the Monte Carlo… **the empirical forecasting performance of
  the MS-AR model is disappointing**." He attributes this to structural breaks in the forecast
  period, citing Clements & Krolzig (1998) on "the structural instability of two-regime business
  cycle models."
- The one positive: an MSIH(3)-VAR(1) on output and employment, 1990:3–1996:4, "is again
  consistently outperforming the linear VAR(1) model." **Class (b)**, one series pair, one window.
- And the theoretical result the project should quote regardless: eq. (21),
  ŷ_{t+h|t} = E[X_{t+h}]β̄ + E[X_{t+h}]B**F**ʰξ̂_{t|t}; ρ = p₁₁ + p₂₂ − 1 is named "the regime
  persistence parameter" and is the eigenvalue of F in the two-regime case; "for h → ∞ the
  forecasts ŷ_{t+h|t} converge to the unconditional mean."

[fetched: https://www.nuff.ox.ac.uk/economics/papers/2000/w31/msvarfor.pdf]

**Also relevant:** statsmodels has no MS-VAR. Getting one means dynamax (and a JAX determinism
project) or writing it. Against a "disappointing" published record, that is not a good trade.

---

### Rank 7 — Markov-switching GARCH · **DO NOT (wrong asset class)**

**Gain: high but not here. Cost: high. Overfitting risk: medium.**

The out-of-sample evidence is genuinely good — and genuinely about daily equity returns. **Ardia,
Bluteau, Boudt & Catania (2018)**, *Forecasting risk with Markov-switching GARCH models: A
large-scale performance study*, *IJF* 34(4), 733–747: "MSGARCH models yield more accurate
Value-at-Risk, expected shortfall, and left-tail distribution forecasts than their single-regime
counterparts for daily, weekly, and ten-day equity log-returns. Also… accounting for parameter
uncertainty improves the left-tail predictions." **Class (b), large scale.** The MSGARCH R package
(Ardia, Bluteau, Boudt, Catania, Trottier, *JSS* 2019) implements it and exposes filtered regime
probabilities.
[fetched: https://research.vu.nl/en/publications/forecasting-risk-with-markov-switching-garch-models-a-large-scale ·
https://www.jstatsoft.org/article/view/v091i04/1321 — ScienceDirect returned 403]

Two reasons it does not transfer. First, monthly macro series have nothing resembling the daily
volatility clustering GARCH exists to model. Second, MS-GARCH carries a genuine technical wart: the
path-dependence problem, where the conditional variance depends on the entire regime history, which
Gray (1996) and Klaassen (2002) handle by ad-hoc collapsing and Haas, Mittnik & Paolella (2004,
*JFEc* 2(4), 493–530) avoid by letting each state's GARCH evolve independently. If the project ever
wants time-varying conditional variance, Rank 2's second Markov chain on the variance is the
cheaper and better-evidenced route.

---

### Rank 8 — Duration dependence · **DO NOT**

**Gain: low here. Cost: medium. Overfitting risk: high.**

Durland & McCurdy (1994), *JBES* 12(3), 279–288, extend Hamilton's filter so "first-order
conditional transition probabilities are functions of both the inferred current state and also the
number of periods the process has been in that state," summarised by an inferred duration variable
in a τ-order Markov system. On US postwar real GNP growth they find "evidence in support of
nonlinearity, asymmetry between recessions and expansions, and **duration dependence for recessions
but not for expansions**." **Class (a).**
[fetched: https://econpapers.repec.org/RePEc:bes:jnlbes:v:12:y:1994:i:3:p:279-88 — abstract record;
the author-hosted PDF 404s and SSRN returns 403]

The finding is about *recessions*, which are short, quarterly, and not what this project's five
states are. It multiplies the state space by τ, and it would be estimated from the same ~30
switches. A worse version of Rank 4's problem.

---

### Rank 9 — Sticky HDP-HMM / infinite HMM · **DO NOT adopt the machinery; DO steal the idea**

**Gain: medium. Cost: very high. Overfitting risk: low but replaced by determinism risk.**

Beal, Ghahramani & Rasmussen, *The Infinite Hidden Markov Model* (NIPS 14, 2001/2002), use a
hierarchical Dirichlet process to integrate out infinitely many transition parameters, leaving
three hyperparameters controlling self-transition time scale, transition sparsity and the expected
number of distinct states — sidestepping the model-selection problem entirely.
[fetched: https://proceedings.neurips.cc/paper_files/paper/2001/file/e3408432c1a48a52fb6c74d926b38886-Paper.pdf]

Fox, Sudderth, Jordan & Willsky, *A sticky HDP-HMM with application to speaker diarization*,
*Annals of Applied Statistics* 5(2A), 1020–1056 (2011), identify and fix the pathology that matters
here: "the basic HDP-HMM tends to over-segment the audio data — creating redundant states and
rapidly switching among them"; the sticky parameter κ, entering via ρ = κ/(α + κ), "provides
effective control over the switching rate," with κ and α given gamma priors and learned.
[fetched: https://arxiv.org/abs/0905.2592 and the v3 PDF]

There is a live macro-finance application: **Li, Maheu & Yang**, *An Infinite Hidden Markov Model
with Stochastic Volatility* (MPRA 115456, Nov 2022 → *Journal of Forecasting*, 2024). Its result is
exactly the shape this project should care about, and it contains a warning. On four series
including **US IP growth**, the SV-IHMM has the best log predictive likelihood everywhere (log
Bayes factors of 12.7 to 169 over benchmarks on IP growth) — but on IP growth it has the **worst
RMSFE of all fourteen models** (1.6058 against 1.5753 for TV-GJR-GARCH). **The nonparametric regime
machinery buys density and tail accuracy on macro, and costs point-forecast accuracy.** For a
Brier-scored project that is mostly good news, but it is a precise statement of what is and is not
on offer.
[fetched: https://mpra.ub.uni-muenchen.de/115456/1/MPRA_paper_115456.pdf]

**Verdict.** Adopting an HDP-HMM means MCMC, a new dependency, label-switching (Hamilton's Handbook
flags this: "the role of label switching, as discussed by Celeux, Hurn and Robert (2000),
Frühwirth-Schnatter (2001), and Geweke (2007)"), and a fight with the determinism rule. **But the
sticky parameter κ is the entire good idea, and Rank 1 imports it for fifty lines.** Take κ; leave
the Dirichlet process.

---

### Rank 10 — Particle filters and continuous latent states · **DO NOT**

**Gain: none for this model. Cost: high. Determinism risk: severe.**

Creal, *A Survey of Sequential Monte Carlo Methods for Economics and Finance* (*Econometric Reviews*
31(3), 245–296), states the boundary exactly: the filtering recursion can be solved analytically in
two useful cases — linear-Gaussian (Kalman) and "when the state variable xₙ is **discrete valued**"
(the HMM filter). The particle filter "generalizes the Kalman filter and hidden Markov model (HMM)
filter to nonlinear, non-Gaussian state space models." **This project is exactly the HMM-filter
case. A particle filter would be strictly worse.**

And it would break the determinism rule in a way seeding alone does not fix: "the log-likelihood
function is not a continuous function of the parameters. The discontinuity is created from the
resampling stage within a particle filter and can cause problems for gradient-based optimizers."
[fetched: https://degree.ubvu.vu.nl/repec/vua/wpaper/pdf/20090018.pdf]

For scale, Herbst & Schorfheide (*JAE* 29(7), 1073–1098) show SMC precision rises in proportion to
N — halving the Monte Carlo standard error costs **4× the particles** — and report, over 20
independent runs of the Smets–Wouters model, a log marginal data density of −901.739 with SD
**0.33** for SMC against −902.626 with SD **2.34** for random-walk Metropolis-Hastings. An SD of
2.34 is larger than most model-comparison differences people report.
[fetched: https://www.nber.org/system/files/working_papers/w19152/w19152.pdf]

**On continuous latent states more generally**, the honest summary of the fetched evidence is that
the out-of-sample payoff is concentrated almost entirely in the second moment and fades by one
year. Stock & Watson's UCSV model (*JMCB* 39(s1), 2007) is the canonical continuous-latent-state win
for macro — relative MSFEs of 0.77–0.88 (1970–83) and 0.83–0.96 (1984–2004) against a recursive
AR(AIC) — but **read their own Table 4 note: the UC-SV rows are "Fixed-parameter models (not
pseudo out-of-sample)."** The clean recursive competitor is a rolling MA(1), which they say
"performs very well — nearly as well as the UC-SV model — in both periods." They also replaced the
Gaussian SV innovations with a jump-like mixture of normals precisely to test a regime alternative
and found the smoothed estimates "qualitatively and quantitatively close" — **smooth and jumpy
volatility were empirically indistinguishable.**
[fetched: https://www.princeton.edu/~mwatson/papers/Stock_Watson_JMCB_2007.pdf]

The "volatility dominates coefficients" consensus is real but contested: Primiceri (2005) concludes
"the high volatility of the exogenous non-policy shocks seems to explain a larger fraction of the
outbursts of inflation and unemployment of the 70s and early 80s," while Cogley & Sargent (2005)
state on the same three-variable US system that "much of our earlier evidence for drifting
coefficients survives after we take stochastic volatility into account," and add the important
methodological point that standard stability tests "have low power against our particular model of
drifting coefficients." Both **class (a)**.
[fetched: https://faculty.wcas.northwestern.edu/gep575/tvsvar_final_july_04.pdf — July 2004 WP
version · https://www.econstor.eu/bitstream/10419/100738/1/wp2003-25.pdf]

One implementation landmine if SV is ever adopted: Del Negro & Primiceri's corrigendum (*ReStud*
82(4), 1342–1345) corrects the *ordering* of the MCMC steps in Primiceri's algorithm — "the main
difference in the new algorithm is the ordering of the various Markov Chain Monte Carlo steps, with
each individual step remaining the same." A sampler with the wrong step order looks perfectly
healthy and targets the wrong posterior.
[fetched: https://www.newyorkfed.org/research/staff_reports/sr619.html — abstract page only]

---

### Rank 11 — Smooth-transition (STAR) or threshold (TAR) models · **INTERESTING, NOT NOW**

Worth one paragraph because it removes a whole class of hazard rather than adding to it. In a
TAR/STAR model the "regime" is an *observable* function of past data, so there is no filtering, no
latent-state uncertainty, and structurally no filtered-versus-smoothed trap. Potter (FRBNY Staff
Report 87, 1999) puts the distinction precisely: "In the threshold model regimes are defined by the
past values of the time series itself, in the Markov switching case regimes are defined by the
exogenous state of the Markov chain." The logistic transition F(y; γ, r) nests both endpoints —
"for very large γ the smooth transition model might effectively be the same as a threshold model,"
and "if γ ≈ 0… there is really only one regime" — and it is specifically robust to the thing this
project's point-in-time discipline cares about: "Consider the case where one is forecasting US GDP
and the initial release is slightly below the threshold but the subsequent revision is above the
threshold. A threshold model would imply large changes in the forecast."
[fetched: https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr87.pdf]

This is a different model class, not an extension, and swapping would discard the project's whole
apparatus. Note it as the road not taken.

---

## Implementations worth using

Assessed 2026-09-12. Commit counts from the GitHub API (`/commits?since=2025-09-12`), versions and
dates from the PyPI JSON API. **None of these is currently installed** — `pyproject.toml` pins
`>=3.11,<3.14` and depends only on numpy, pandas, scipy, pyyaml, matplotlib, pyarrow. Every option
is a net-new dependency.

The decisive axis is whether the library exposes **filtered** (time-t) state probabilities, not
just smoothed ones.

| Library | Latest | Released | Commits 12mo | requires-python | Filtered probs? | TVTP? | Verdict |
|---|---|---|---:|---|---|---|---|
| [statsmodels](https://www.statsmodels.org/stable/tsa.html) | 0.15.0 | 2026-08-27 | 1673 | `>=3.10` | **Yes** — `filtered_marginal_probabilities`, `predicted_marginal_probabilities` | **Yes** — `exog_tvtp` | **Adopt if anything** |
| [dynamax](https://probml.github.io/dynamax/) | 1.0.2 | 2026-06-25 | 23 | `>=3.10` | **Yes** — `hmm_filter → filtered_probs` | **Yes** — 3-D matrix or `transition_fn` | Only for multivariate + priors + TVTP together |
| [hmmlearn](https://github.com/hmmlearn/hmmlearn) | 0.3.3 | 2024-10-31 | **0** | `>=3.8` | **No** — smoothed only | No | **Reject** |
| [pomegranate](https://github.com/jmschrei/pomegranate) | 1.1.2 | 2025-02-07 | **0** | — | Yes — `DenseHMM.forward()` | No | Reject (stale; drags in PyTorch) |
| [pykalman](https://github.com/pykalman/pykalman) | 0.11.2 | 2026-01-31 | 19 | `>=3.10,<3.15` | Yes | Linear-Gaussian only | Not a substitute |
| [sktime](https://www.sktime.net/) | 1.1.0 | 2026-07-28 | 773 | `>=3.10,<3.15` | **No** — wraps hmmlearn | No | **Reject** |
| [statsforecast](https://nixtlaverse.nixtla.io/statsforecast/) | 2.1.1 | 2026-07-16 | 94 | `>=3.10` | n/a — no such model | n/a | **Reject** |
| [pymc-extras](https://github.com/pymc-devs/pymc-extras) | 0.14.0 | 2026-07-28 | 145 | **`>=3.12`** | **Yes** — `filtered_posterior` | via model code | Raises Python floor |
| [particles](https://github.com/nchopin/particles) | 0.4 (PyPI stale) | 2023-11-06 | 4 | `>=3.9` | Yes by construction | Yes | Only if nonlinear filtering ever needed |
| [lindermanlab/ssm](https://github.com/lindermanlab/ssm) | no PyPI | — | **0** | — | Yes (source install) | Yes | Abandoned → use dynamax |
| [filterpy](https://github.com/rlabbe/filterpy) | 1.4.5 | **2018-10-10** | **0** | — | Yes | n/a | Reject |

**statsmodels** — the only mainstream library with TVTP built in, and the correction to ADR 0004.
`MarkovSwitchingResults` exposes four reshaped arrays: `predicted_marginal_probabilities`
(p(Sₜ | y_{1:t−1})), `filtered_marginal_probabilities` (p(Sₜ | y_{1:t})),
`smoothed_marginal_probabilities` (p(Sₜ | y_{1:T})) and `expected_durations`, backed by separate
`HamiltonFilterResults` and `KimSmootherResults` classes. Its own Hamilton (1989) replication
notebook reports p[0→0] = 0.7547, p[1→0] = 0.0959, regime constants −0.3588 and +1.1635 over
1951Q2–1984Q4, and demonstrates both `filtered_marginal_probabilities[0]` and
`smoothed_marginal_probabilities[0]`; its Filardo example passes
`exog_tvtp=sm.add_constant(dta_filardo.iloc[1:-1]["dmdlleading"])`.
[fetched: https://www.statsmodels.org/stable/examples/notebooks/generated/markov_autoregression.html]

Two live hazards if adopted. **Determinism:** `fit(..., search_reps=0, ..., rng=None)` — the docs
state that if `rng` is None "a new Generator is created using fresh entropy from the operating
system." Any `search_reps > 0` without an explicit `rng` breaks byte-identical reruns. **API
stability:** `MarkovAutoregression`'s docs still say "This model is new and API stability is not
guaranteed." And the limitation that keeps ADR 0004's *conclusion* alive: statsmodels has
`MarkovRegression` and `MarkovAutoregression` only — **no multivariate regime switching**, which is
what this project needs. It would serve as an independent cross-check on a univariate slice, not as
a replacement.

`statsmodels.tsa.statespace.dynamic_factor_mq.DynamicFactorMQ` is the mixed-frequency nowcasting
workhorse if Rank 5 is ever attempted — monthly plus `endog_quarterly`, `fit_em()` by default,
Kalman filtered and smoothed states, news decomposition.

**dynamax** — technically the best fit and the only one with the sticky Dirichlet prior already
implemented (`p(A) = ∏ Dir(A_k | β·1_K + κ·e_k)`, M-step
`tfd.Dirichlet(self.concentration + expected_trans_counts).mode()`, `concentration=1.1` default).
Its inference API is the cleanest surveyed: `hmm_filter` returns `HMMPosteriorFiltered` with
`filtered_probs` (p(zₜ | y_{1:t})) and `predicted_probs` (p(zₜ | y_{1:t−1})); `hmm_smoother` returns
a *different type* carrying `smoothed_probs`, so the leak cannot happen by accident. TVTP is native
at the inference layer. **The cost is jax + jaxlib + optax + tensorflow-probability, plus real work
to get byte-identical reruns** (`jax.config.update("jax_enable_x64", True)`, disabling fast-math).
Worth it only if Ranks 2 and 4 are both taken.

**hmmlearn is disqualified, and this vindicates ADR 0004's decision if not its reasoning.** Its
README says "This package is under limited-maintenance mode"; zero commits in twelve months; last
release 2024-10-31. More decisively, `predict_proba` returns γ from `score_samples`, documented as
"State-membership probabilities for each sample" — the **smoothed** posterior. `fwdlattice` is a
local variable inside `_score_log`, produced by the private Cython `_hmmc.forward_log(...)` and
never returned. Getting filtered probabilities means calling a private C extension. Using
`predict_proba` in a walk-forward backtest is a silent look-ahead leak of exactly the kind the
project rules forbid. It does, however, have `transmat_prior` — "Parameters of the Dirichlet prior
distribution for each row of the transition probabilities" — which is a useful reference
implementation for Rank 1 even though the library is not usable. **sktime's `GaussianHMM`,
`GMMHMM` and `PoissonHMM` are thin wrappers over hmmlearn and inherit the defect.**

**pymc-extras statespace** is the serious Bayesian route and carries a trap worth writing into a
test if ever adopted: `forecast(self, idata, ..., filter_output="smoothed", ...)` — **the default
is smoothed**. In a walk-forward backtest that default is a look-ahead leak; pass
`filter_output="filtered"` or `"predicted"` explicitly. It also raises the Python floor to 3.12.

**Recommendation.** Rank 1 needs no library at all — it is a change to the existing M-step. Keep
the hand-rolled model. If a cross-check is wanted, add statsmodels as a *test-only* dependency and
assert that the hand-rolled filtered probabilities match `MarkovRegression`'s
`filtered_marginal_probabilities` on a univariate slice to tolerance. That is a genuinely
independent computation of the load-bearing quantity, which is what ADR 0004 says it wants.

---

## The sceptical case against regime-based allocation

Included because the project's natural next question is "can this drive an allocation," and the
answer the literature actually supports is much weaker than the answer it is usually quoted as
supporting. **Assessment: the evidence does not support regime-based allocation as a
return-generating strategy. It weakly supports it as a risk-reduction strategy.**

**1. The positive literature's own numbers are modest, and the headline figures are selected by
citers rather than authors.**

*Ang & Bekaert (2002)*, "International Asset Allocation With Regime Shifts," *RFS* 15(4),
1137–1187, is cited as the foundation. Its actual finding: the cost of ignoring regimes in the
all-equity three-country system at γ = 5, one-year horizon, is **0.21 to 0.38 cents per dollar**;
for the US–UK–German benchmark, **0.14 and 0.05 cents**. The cost of *not diversifying
internationally* is **0.94 to 3.39 cents** — three to ten times larger. Regime value only becomes
material (≈2.70 cents) once a conditionally risk-free asset is added and the short rate drives the
transition probabilities, i.e. the gain comes from the *cash* option. Intertemporal hedging demands
from regime switching are "economically negligible and statistically insignificant." **Class (a),
no transaction costs**, and the authors say so: "With transaction costs, or learning about the
regime, it is less likely to be worthwhile for investors to change their allocations."
[fetched: https://business.columbia.edu/sites/default/files-efs/pubfiles/1971/1137.pdf]

*Ang & Bekaert (2003, NBER WP 10080)* is the source of the famous Sharpe ratio: RS strategy 1.07 vs
world market 0.52 vs non-regime-dependent 0.90, **class (b)**, monthly re-estimation from 1985.
Four caveats the citing literature drops: no transaction costs ("we exaggerate the performance of
the models"); no constraints at all, with a **short position in Japan exceeding 50%**; the edge is
concentrated in the late-1990s window; and most of the headline gap is *optimisation*, not regime
detection — regime-dependent beats non-regime-dependent by only 0.17 Sharpe. The authors' own
disclaimer: "we do not want to claim that the success of the RS strategy shown here is a good
indicator for future success."
[fetched: https://www.nber.org/system/files/working_papers/w10080/w10080.pdf]

*Guidolin & Timmermann (2008)*, "International Asset Allocation under Regime Switching, Skew and
Kurtosis Preferences," *RFS* 21(2), 889–935, is the best-documented positive result. Two states,
persistence 0.90 (bear) and 0.94 (bull); a Monte Carlo *with* estimation error still gives "an
increase in the certainty equivalent return of about two percent per annum"; a recursive **class
(b)** experiment from 1985:12 to 2005:12 gives a CER 2% above the single-state model and 80 bp
above the ICAPM at one month. Their own footnote: "An investment strategy based on the two-state
model fails to produce the highest out-of-sample mean return which is now associated with the
ICAPM." **The two-state model wins on utility via 2–3% lower volatility, not on return. No
transaction costs.**
[fetched: https://rady.ucsd.edu/_files/faculty-research/timmermann/skew_kurtosis.pdf]

*Kritzman, Page & Turkington (2012)*, *FAJ* 68(3) — note the published "(corrected)" erratum. The
FAJ text is paywalled; the numbers below come from the authors' own State Street presentation of
the same study, **which its disclaimer labels "for marketing and/or informational purposes only"**
and which is nonetheless more numerically candid than the academic literature.

| Dynamic asset allocation backtest, Feb 1973 – Dec 2009 | Static | With dynamic tilts |
|---|---:|---:|
| Annualised return | 9.45% | **9.29%** |
| Annualised volatility | 9.88% | 8.98% |
| Annual 5% VaR | −10.44% | −8.34% |
| Worst year | −34.93% | −29.51% |

"Includes transaction costs of 40 basis points. Average yearly turnover associated with the dynamic
tilts is 34%." **The flagship regime-based allocation backtest earns 16 bp per year *less* than the
static allocation.** The entire benefit is risk reduction. Their investable-risk-premia backtest
does better (IR 0.72 → 0.92, max drawdown −41.5% → −32.7%, also net of 40 bp) — but the tilt rules
were read off an in-sample conditional-performance table running to December 2009, the last date of
the backtest. **The regime model is recursive; the strategy is not.** That is specification-search
look-ahead, and it is the standard failure mode in this literature. Their standard errors on
persistence are 5–15 percentage points.
[fetched: https://boston.qwafafew.org/wp-content/uploads/sites/3/2017/01/Regime-Shifts_Turkington_QWAFAFEW.pdf ·
record at https://rpc.cfainstitute.org/research/financial-analysts-journal/2012/regime-shifts-implications-for-dynamic-strategies-corrected]

**2. The founding negative result: misclassification eats the edge.** Dacco & Satchell (1999), "Why
do regime-switching models forecast so badly?", *Journal of Forecasting* 18(1), 1–16. **I could not
open the primary source** (Wiley and Semantic Scholar both refused). The mechanism is confirmed via
a fetched secondary: Cheung & Erlandsson (HKIMR WP 5/2005) state "Dacco and Satchell (1999) argue
that the forecast performance of Markov switching models is very sensitive to misclassification of
regimes," alongside "Marsh (2000)… shows that Markov switching models for exchange rates are
unstable over time and not suitable for forecasting." The mechanism: even with the true model and
true parameters, the loss from applying the wrong regime's mean is quadratic in the gap between
regime means — the very gap that makes the model attractive in-sample. **The more distinct the
regimes, the more a misclassification costs.**
[fetched: https://people.ucsc.edu/~cheung/WorkingPapers/HKIMR/FXMarkovSwitching_HKIMR2005.pdf]

Confirmed by simulation: Bessec & Bouabdallah (2005), "What causes the forecasting failure of
Markov-Switching models? A Monte Carlo study," *SNDE* 9(2) — "MS models generally display a
superior in-sample fit relative to linear models, [but] the gain in prediction remains small," and
decomposing forecast error into four components, "the main source of error is due to the
misclassification of future regimes." **In-sample fit and out-of-sample forecast value are nearly
decoupled in MS models, and misclassification is why.**
[fetched: https://econpapers.repec.org/RePEc:wpa:wuwpem:0503018 — abstract record]

**3. The estimation-error critique, and why regime models make it worse.** DeMiguel, Garlappi &
Uppal (2009), "Optimal Versus Naive Diversification," *RFS* 22(5), 1915–1953: **of 14 models across
7 datasets, none is consistently better than 1/N** on Sharpe ratio, certainty-equivalent return or
turnover. The estimation window needed for sample-based mean-variance to beat 1/N is ~3,000 months
for 25 assets and ~6,000 months for 50 — 250 and 500 years.
[fetched: https://lbsresearch.london.edu/id/eprint/407/ — record; findings via
https://scixindex.com/external-research-anthology/victor-demiguel-lorenzo-garlappi-raman-uppal-2009/optimal-versus-naive-diversification-how-inefficient-is-the-1-n-portfolio-strategy/]

A regime model makes this *harder*, not easier: it splits an already-short sample into per-regime
sub-samples and estimates a separate mean vector and covariance in each. Ang & Bekaert say so
directly — "as far fewer observations are inferred to belong to regime 1, estimates of the
conditional mean in that regime are hard to pin down, leading to large standard errors" — and in
their own model a likelihood ratio test **fails to reject equal means across regimes (p = 0.1165)**.
The return differential motivating the whole exercise is not statistically distinguishable from
zero. Michaud (1989, *FAJ* 45(1), 31–42): "The major problem with MV optimization is its tendency
to maximize the effects of errors in the input assumptions," and unconstrained MV "can yield
results that are inferior to those of simple equal weighting schemes."
[fetched: https://rpc.cfainstitute.org/research/financial-analysts-journal/1989/the-markowitz-optimization-enigma-is-optimized-optimal — partial summary]

**4. The one paper claiming profitability net of costs proves the point.** Bulla, Mergner, Bulla,
Sesboüé & Chesneau, "Markov-switching Asset Allocation: Do Profitable Strategies Exist?" (MPRA
21154, 2010): daily US/Japan/Germany equity indices over ~40 years, "profitable after taking
transaction costs into account," **volatility reduced on average by 41%**, annualised excess returns
**18.5 to 201.6 basis points**. A working paper with no journal publication on the record page, and
the lower bound of that return range is indistinguishable from zero. Same shape as everyone else:
the robust effect is volatility reduction.
[fetched: https://mpra.ub.uni-muenchen.de/21154/]

**5. Nothing in this literature is class (c).** Every "out-of-sample" result fixes the model form,
the regime count and often the tilt schedule after seeing the full sample. Kritzman et al. read
tilt rules off an in-sample table ending on the backtest's last date. Shu & Mulvey (arXiv:2410.14841,
Princeton ORFE — a careful **class (b)** study with 5 bp costs and a one-day delay, IR rising from
0.05 to ~0.44) tune the jump-model hyperparameters, including the jump penalty that sets
persistence, by cross-validation on the test period.
[fetched: https://arxiv.org/pdf/2410.14841]

**6. Bottom line.** If an allocation application is ever contemplated: the defensible claim is
**volatility and drawdown reduction at flat-to-slightly-negative return**, and any backtest must
cost turnover and fix the decision rule before seeing the period — which is exactly the discipline
the existing `experiment.json` already imposes on the forecasting problem. That discipline is the
project's comparative advantage against this entire literature and should not be given up to enter
it.

**One constructive note.** Nystrup, Lindström & Madsen, "Learning hidden Markov models with
persistent states by penalizing jumps" (*Expert Systems with Applications* 150, 2020, art. 113307),
open on a criticism of HMMs that is the mirror image of this project's situation: "When the model
is misspecified or misestimated, however, it often leads to unrealistically rapid switching
dynamics." Their statistical jump model claims explicit control over the transition rate, faster
joint estimation of states and parameters, less initialisation sensitivity and better behaviour as
K grows. This project has the *opposite* pathology — unrealistically *slow* switching — which is
the same misspecification with the opposite sign, and is the strongest independent reason to take
Rank 1 seriously.
[fetched: https://orbit.dtu.dk/en/publications/learning-hidden-markov-models-with-persistent-states-by-penalizin — abstract record]

---

## What I could not verify

**Could not open at all — cited only where a fetched secondary or a bibliographic record carries
the claim, and never for a number:**

- Hamilton (1989), *Econometrica* 57(2), 357–384 — the primary source. Its transition-probability
  estimates above come from two independent replications (EViews documentation; statsmodels'
  `markov_autoregression` notebook) plus Hamilton's own Handbook Table 1, which reports
  Chauvet–Hamilton (2006) figures for 1947Q2–2004Q2. **The replications disagree**: EViews gives
  p₁₁ = 0.90, statsmodels 0.9041, and one secondary source reports 0.9688 — inconsistent with its
  own stated 10.43-quarter duration, so I used 0.9041. Treat Hamilton's persistence as 0.90 ± 0.01
  quarterly, not a precise number.
- Dacco & Satchell (1999) — mechanism taken from Cheung & Erlandsson's characterisation. The
  segmented-trend analytics and DM/dollar illustration are **unverified**.
- Clements & Krolzig (1998), *Econometrics Journal* 1(1), C47–C75 — Oxford Academic, SSRN and the
  Reading repository all refused. Its conclusion reaches this briefing only through Krolzig (2000)
  citing it.
- Hansen (1992) *JAE* 7(S1), Garcia (1998) *IER* 39(3), Cho & White (2007) *Econometrica*, Carter &
  Steigerwald (2012) *Econometrica* comment, Psaradakis & Sola (1998), Guidolin & Timmermann JEDC
  (2007) numbers, Chopra & Ziemba's 11×/21× figures, Nystrup et al. *JPM* 2015/2018 numbers,
  Durland & McCurdy full text, Mariano & Murasawa (2003), Croushore & Stark (2001),
  Schorfheide & Song *JBES* (2015) magnitudes, Camacho–Pérez-Quirós–Poncela numbers (image-only
  PDF), Carriero–Clark–Marcellino (403/paywalled), van Dijk–Teräsvirta–Franses (2002) full text,
  Teräsvirta–van Dijk–Medeiros (2005) — **citations verified, contents not read, no numbers used.**
- Rabiner (1989) — the UCSB-hosted PDF is an image scan with no text layer (30 bytes extracted). His
  specific recommended floor on probability estimates is **unverified**; Gauvain & Lee and dynamax
  carry the same point and were opened.
- Published GDPNow headline accuracy ("MAE 0.77 / RMSE 1.17 since 2011") — appears in search
  snippets attributed to the GDPNow landing page, but every fetch of that page returned truncated
  content or 404. **Do not quote it.** Higgins' 2014 and 2019 figures above are the verified
  substitutes.

**Working-paper versus published divergence — verify before external citation:** Primiceri (July
2004 WP, not the 2005 ReStud), Sims & Zha (April 2004 conference version, not the 2006 AER),
Clark (2009 KC Fed RWP, not the 2011 JBES), Ang & Bekaert FAJ 2004 (used the 2003 NBER WP),
Guidolin & Timmermann RFS 2008 (used the August 2007 WP).

**Metadata conflict, unresolved:** the Kenan Institute record for "State Space Models and MIDAS
Regressions" credits **Ghysels alone**, *Journal of Econometrics* 172(2), 2013; other indexes give
**Bai, Ghysels & Wright**, *Econometric Reviews* 32(7), 779–813. The abstract text matches the
Bai–Ghysels–Wright paper. An institutional-listing error, not a fabricated source, but resolve it
before citing.

**Synthetic-source check.** No future-dated papers were used. Two 2026-dated arXiv preprints
surfaced and were assessed:

- **arXiv:2605.14976v2** (Modée, Li, Westgaard, Bethuelsen, TVTP) — **used, and clean**: four named
  authors at the University of Bergen and NTNU, submitted to the *International Journal of
  Forecasting*, an open-source R package with a compiled C backend, submitted 14 May 2026 and
  revised 7 August 2026, both before today. Labelled as a preprint wherever cited.
- **arXiv:2606.06190** ("Multi-Scale Markov Switching GARCH") — surfaced in search, **not fetched
  and not used**. Unassessed.

Several other 2026-dated arXiv items appeared in searches (2603.04441, 2606.02657); none was opened
or used.

**Claims I am asserting rather than citing, flagged as such (E0/E1):**

- The identification of the project's λ₂ = 0.983 with volatility/level regimes rather than
  business-cycle regimes is *my* inference from the fetched comparison table plus the regime labels
  in `docs/RESULTS.md`. It is a hypothesis with a cheap test (Rank 2's precursor), not a result.
- The Poisson arithmetic on the nine zeros (20 cells, 30 switches, 4.5 expected empty cells) is my
  own computation from the project's stated quantities. The 30-switch figure comes from
  `docs/RESULTS.md`; the nine-zeros figure from `docs/TECHNICAL_DEBT.md` D1.
- The sticky-prior hyperparameter formulas (κ = β(D(K−1) − K); prior row strength β·D·(K−1)) are
  derived here from the Dirichlet mode, not quoted. The arithmetic is elementary and needs no
  replication, but it has not been checked against a fitted model — the actual effect on λ₂ requires
  a real MAP-EM run, and as D1 already notes, "a real prior would also change the E-step
  responsibilities and the model would partly refit around the smoother transitions, so the true
  effect is smaller."
- The parameter counts for MS-VAR variants are my arithmetic from K = 5, N = 3, T = 908.
