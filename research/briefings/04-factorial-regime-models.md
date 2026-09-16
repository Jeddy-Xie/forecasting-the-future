# Factorial regime models: what the two-timescale chain already is, and what can be added to it

Research briefing · compiled 2026-09-16 · for `forecasting-the-future`

**Scope.** Research arm A4 (`research/two-timescale-chains`, experiment 0002) replaces main's single
six-state Gaussian HMM with two independent chains: a growth chain driving the growth column, a
levels chain driving inflation and rates. The joint transition matrix is `kron(A_g, A_l)`, the joint
emission log density is the sum of the two blocks', filtering is the inherited forward pass over the
16 joint states, and fitting is expectation maximisation over joint states with expected counts
summed down to each chain. It came back CONFIRMED_IN_SAMPLE: one-year paired difference +0.0590,
98.33% interval [+0.0147, +0.1019]. This briefing asks what model class that is, what is known about
it, and what can be added.

Briefing 02 covered the single-chain extensions and is not repeated. Where it already settled a
question — MS-VAR, MS-GARCH, particle filters, duration dependence, HDP-HMM machinery, the
Hamilton/Krolzig convergence theorem — this briefing cites it and moves on.

**Evidence discipline.** Same as briefings 01 and 02. Every claim is labelled:

- **[fetched]** — I retrieved the source and read the passage quoted.
- **[metadata]** — title, authors, venue and DOI verified against Crossref and/or OpenAlex, but the
  full text could not be opened. **No number is taken from any [metadata] source.**
- **[derived]** — computed here by
  `research/briefings/derivations/factorial_regime_algebra.py` (deterministic, seed 20260916).
- **[E1]** — my own reasoning from the above, asserted as such.

**Two discovery constraints, stated up front.** The session's web-search budget was exhausted
(200/200) before this briefing began, so discovery used only URLs I could name directly plus the
Crossref, OpenAlex and Semantic Scholar APIs. And one guessed DOI resolved to the wrong paper — see
"What I could not verify"; the correction is on the record there.

---

## Executive summary

**1. The model already has a name, and it is not new.** It is a **factorial hidden Markov model**
(Ghahramani & Jordan 1997), sitting in the one corner of that class where everything difficult about
factorial HMMs does not happen. In econometrics the identical restriction is Sims, Waggoner & Zha's
"independent Markov processes", `Q = Q¹ ⊗ ··· ⊗ Q^κ`. Both are [fetched] in full text.

**2. The project is in the exactly-tractable corner because its emission block-separates.** In the
canonical factorial HMM every chain contributes to one observation, which couples the chains a
posteriori and makes exact inference intractable. Here growth is a child of the growth chain only
and (inflation, rates) of the levels chain only, so the chains have no common child, the posterior
factorises, and EM is exact and cheap. The arm's own tests pin this: the joint filter equals the
product of the two chains' filters. **The 16 joint states are bookkeeping, not a coupled model.**

**3. The λ₂ result is a theorem, not a finding.** `spec(A ⊗ B) = {λᵢμⱼ}`, both factors are
row-stochastic so λ₁ = μ₁ = 1, hence the joint second eigenvalue is exactly `max(|λ₂|, |μ₂|)` — the
slower chain's — for any two chains, on any data, at every refit. Verified on all 16 cells of the
arm's own sweep and on random matrices to 2.1e-15 [derived]. The REPORT records "joint λ₂ equals the
slower chain's" as a confirmed prediction; it could not have come out otherwise. It is a good
implementation check and no evidence at all for the two-timescale hypothesis.

**4. The parameter arithmetic is the real structural claim.** The factorial restriction takes an
unrestricted 16-state chain from **399** free parameters to **58**, and the arm carries 16 states on
**31 fewer** parameters than main carries 6 [derived, reproducing the repo's own convention exactly].
Sims, Waggoner & Zha's own formula gives the same 10× reduction on the transition block.

**5. The fit cannot be what produced the gain.** Because the likelihood factorises, the two-chain fit
*is* two separate fits — the arm's docstring says so. So the measured gain comes either from growth
no longer being dragged onto the slow timescale, or from the conditional base rates now being cut on
16 cells instead of 6. The second is a change to the forecasting layer, not the regime model, and it
cost mean effective sample size **112.4 → 45.3** [derived]. **One cheap run separates them and it is
not on the extension list: refit main's single chain at K = 16.** Do that before funding anything
below.

**6. The headline effect is not seed noise, and this is now measured.** Three seed variants of A4
exist on disk. Their one-year paired differences are +0.059014, +0.060345 and +0.060277 — a spread of
**0.0013** against a reported effect of +0.0590 and a 90% interval half-width of 0.0301 [derived].
Seed variability is about 2% of the effect. This retires the cheapest available objection to A4 and
demotes "average over seeds" from the top of the ranking, where it sat in this briefing's first draft.

**7. Ranked: coupling is the only extension that changes what the model can represent**, and the
codebase has already paid its computational cost without collecting the benefit.

**8. Nothing on the list changes the ceiling.** Every extension keeps the forecast converging to a
constant at a geometric rate. The one long-horizon lever is *what* it converges to, and A6 has
already measured that lever: ten-year +0.2779, 90% [+0.1204, +0.3310].

---

## 1. What this model already is, in the literature's terms

### 1.1 The model class and its original reference

**Ghahramani, Z. & Jordan, M. I. (1997), "Factorial Hidden Markov Models", *Machine Learning*
29(2–3), 245–273, doi:10.1023/A:1007425814087.** [fetched — Crossref-verified metadata; full text
obtained by downloading the Springer PDF and extracting it locally, because Springer redirects the
fetcher to an authentication endpoint despite OpenAlex reporting the article as open access.]

From the abstract, verbatim:

> "In an HMM, information about the past is conveyed through a single discrete variable—the hidden
> state. We discuss a generalization of HMMs in which this state is factored into multiple state
> variables and is therefore represented in a distributed manner. We describe an exact algorithm for
> inferring the posterior probabilities of the hidden state variables given the observations... Due
> to the combinatorial nature of the hidden state representation, this exact algorithm is
> intractable. As in other intractable systems, approximate inference can be carried out using Gibbs
> sampling or variational methods."

And the structural definition, which is the arm's model exactly:

> "We refer to these models as factorial hidden Markov models, as the state space consists of the
> cross product of these state variables... A natural structure to consider is one in which each
> state variable evolves according to its own dynamics, and is a priori uncoupled from the other
> state variables: P(Sₜ|Sₜ₋₁) = ∏ₘ P(Sₜ^(m)|Sₜ₋₁^(m))... The transition structure for this system
> can be represented as M distinct K × K matrices."

That is `kron(A_g, A_l)` written in the other direction. The arm is a factorial HMM with M = 2,
K_g = K_l = 4.

An earlier and genuinely different version exists — Ghahramani & Jordan, "Factorial Hidden Markov
Models", *NIPS 8* (1995), pp. 472–478 [fetched from
`https://papers.nips.cc/paper_files/paper/1995/hash/4588e674d3f0faf985047d4c3f13ed0d-Abstract.html`].
It contains only the mean-field approximation, not the structured variational one, and its abstract
already states the division of labour that matters here: "the M-step of our algorithm is exact and
can be solved analytically. However, due to the combinatorial nature of the hidden state
representation, the exact E-step is intractable." **Cite the 1997 journal version.**

### 1.2 Where this model sits inside that class — and why it is the easy corner

This is the most important paragraph in the briefing, because it determines which extensions are
cheap and which are not.

In the canonical factorial HMM the observation depends on **all** the chains at once. Ghahramani &
Jordan's Gaussian output model is additive, `μₜ = Σₘ W^(m) Sₜ^(m)`, and the consequence is stated
explicitly [fetched]:

> "The hidden state variables at one time step, although marginally independent, become conditionally
> dependent given the observation sequence... Since μₜ is a function of all the state variables, the
> probability of a setting of one of the state variables will depend on the setting of the other state
> variables. This dependency effectively couples all of the hidden state variables for the purposes of
> calculating posterior probabilities and **makes exact inference intractable for the factorial HMM**."

**This project's emission does not do that.** Growth is a child of the growth chain alone; inflation
and rates are children of the levels chain alone; the covariance is block-diagonal by construction
(`covariances = np.zeros(...)` with only the two diagonal blocks filled,
`models/two_timescale_hidden_markov_model.py`). The two chains therefore have **no common child**, so
d-separation never couples them, the posterior factorises, and:

- the joint filtered distribution is the Kronecker product of the two chains' filters (an arm test
  pins this);
- the complete-data likelihood separates by chain, so the marginalising M-step is the exact
  maximiser (the arm's docstring derives this, and it is correct);
- the model is **equivalent to two separate HMMs** — the docstring again: "it differs from two
  separate fits only in that restarts are paired and convergence is judged on the joint likelihood."

So the honest one-line description is: *a factorial HMM with a block-separable emission*, which is
the degenerate case in which the class's central difficulty is absent. Calling it simply "a factorial
HMM" overstates it; calling it "two HMMs and a product" understates what the forecasting layer then
does with the 16 cells. Both halves belong in the paper.

**Exact versus approximate inference, costed** [derived, from Ghahramani & Jordan's own complexity
expressions]:

| route | complexity | at M = 2, K = 4 |
|---|---|---|
| naive — translate to an HMM with Kᴹ states, run forward–backward | O(T·K^{2M}) | 256·T |
| Ghahramani & Jordan's exact junction-tree E step | O(T·M·K^{M+1}) | 128·T |
| **this model, exploiting block-separability** | O(T·M·K²) | **32·T** |

Their statement of the first two, verbatim [fetched]: "The resulting probability propagation algorithm
has time complexity O(TMK^{M+1})... The naive exact algorithm which consists of translating the
factorial HMM into an equivalent HMM with K^M states and using the forward–backward algorithm, has
time complexity O(TK^{2M})."

**The repo pays the 256·T naive cost.** It runs the inherited forward pass over all 16 joint states.
That is a deliberate and defensible simplicity choice — the arm inherits the filter, Viterbi, the
stationary distribution and the projection unchanged, and at T ≈ 900 the absolute cost is nothing.
But it is worth recording as a fact rather than discovering it later: **the project is already paying
for a coupled model and receiving an uncoupled one.** That is the single strongest argument for the
rank-1 extension below.

### 1.3 The same restriction, under its econometric name

**Sims, C. A., Waggoner, D. F. & Zha, T. (2008), "Methods for inference in large multiple-equation
Markov-switching models", *Journal of Econometrics* 146(2), 255–274,
doi:10.1016/j.jeconom.2008.08.023.** [fetched — Crossref-verified; full text read from the
open-access EconStor copy of **Federal Reserve Bank of Atlanta Working Paper 2006-22, November
2006**. Working-paper versus published divergence: verify section numbering before external
citation, per briefing 02's practice.]

Their section II.3.2, "Independent Markov processes", verbatim:

> "We now consider the case in which there are κ independent Markov processes... The transition
> matrix Q is therefore restricted to the form **Q = Q¹ ⊗ ··· ⊗ Q^κ**... Conditional on Q, the
> composite (overall) Markov process sₜ consists of κ independent Markov processes sₜᵏ. If Q were not
> restricted to this tensor product representation, then it would contain (∏ₖ hₖ)(∏ₖ hₖ − 1)
> parameters. With this nonlinear restriction, there are only Σₖ hₖ(hₖ − 1) parameters — **a
> substantial reduction**."

This matters for the paper more than the machine-learning citation does. It says the arm's structure
is not an exotic import: it is a standard restriction in the multiple-equation Markov-switching
literature, introduced by Sims, Waggoner and Zha for precisely the project's reason — that an
unrestricted transition matrix over a large state space has too many free parameters. The paper
should cite both, and lead with this one.

Instantiating their formula at the arm's 4 × 4 [derived]: unrestricted 16 × 15 = **240** free
transition parameters; tensor-product 4·3 + 4·3 = **24**; a **10×** reduction, matching their claim.

### 1.4 Why the joint chain's persistence behaves as measured

**It is an algebraic identity.** For any matrices, `(A ⊗ B)(x ⊗ y) = (Ax) ⊗ (By)`, so the spectrum of
`A ⊗ B` is the set of pairwise products `{λᵢ μⱼ}`. Both A and B are row-stochastic, so λ₁ = μ₁ = 1
and every modulus is ≤ 1. The largest product is 1·1 = 1; the second largest is therefore
`max(|λ₂|·1, 1·|μ₂|) = max(|λ₂|, |μ₂|)`, since every other product is bounded above by that. Hence:

> **The joint second eigenvalue equals the slower chain's, exactly, for any two chains, on any data,
> at every refit.**

Verified two independent ways [derived]:

- On the arm's **own burn-in sweep**, all 16 (K_g, K_l) cells satisfy
  `joint λ₂ = max(growth λ₂, levels λ₂)` with zero mismatches; the levels chain sets the rate in 13 of
  the 16.
- On random row-stochastic matrices across four shapes, the worst absolute discrepancy is
  **2.11e-15**, and the full joint spectrum equals the outer product of the two spectra.

**The consequence for how the result is written up.** The REPORT lists under "Prediction versus
outcome": *"Predicted: joint λ₂ equals the slower chain's. Confirmed exactly at every refit."* That
prediction was not falsifiable. It is a property of the Kronecker product, guaranteed before any data
was seen. It is a genuinely useful check that `kron` is being formed correctly and that the
canonicalisation has not permuted anything — but it is not evidence for the two-timescale hypothesis,
and presenting it beside the genuinely contingent predictions overstates the model's confirmed
content. **Say so in the paper.** [E1; the algebra is derived]

The same algebra settles the horizon. `Pʰ = Aʰ ⊗ Bʰ`, so the joint chain mixes at the slower chain's
rate. **Splitting the chains cannot lengthen the information horizon**; it can only stop the fast
chain from being dragged onto the slow one's clock. Measured: 60 months for both main and the arm.

Half-lives, `ln(0.5)/ln(λ₂)` [derived]: growth chain 0.9464 → **12.6 months**; levels chain 0.9821 →
**38.4 months**; main's six-state chain 0.9777 → **30.7 months**. The split is real and large — the
growth chain runs three times faster than the chain it was extracted from.

### 1.5 Parameter counts against an unrestricted chain of the same joint size

The repo's own convention is `K(K−1) + Kd + Kd(d+1)/2 + (K−1)` — transitions, means, covariances,
initial distribution. Validated against the arm's own `free_parameters` column at every cell it
reports [derived]:

| model | states | dims | free parameters | check |
|---|---:|---:|---:|---|
| growth chain | 4 | 1 | 23 | sweep says 23 ✓ |
| levels chain | 4 | 2 | 35 | sweep says 35 ✓ |
| **two-chain joint** | **16** | **3** | **58** | sweep says 58 ✓ |
| main, single chain | 6 | 3 | 89 | REPORT says 89 ✓ |
| **unrestricted single chain** | **16** | **3** | **399** | derived |

Two readings, both worth stating:

- The factorial restriction is what makes 16 states affordable at all: **399 → 58, a 6.9× reduction.**
- The arm carries **16 states on 31 fewer parameters than main carries 6.**

The founding paper makes exactly this argument, and names the failure mode the restriction avoids.
From the NIPS 8 version's discussion [fetched]: "The standard Baum-Welch procedure is intractable for
such architectures as the size of the state space generated from the cross product of d k-valued
features is O(kᵈ), and the time complexity of Baum-Welch is quadratic in this size. More importantly,
**unless special constraints are applied to this cross-product HMM architecture, the number of
parameters also grows as O(k²ᵈ), which can result in severe overfitting.**" The Kronecker restriction
is precisely such a special constraint, and 399 → 58 is what it buys here.

This is also Ghahramani & Jordan's own headline empirical finding in miniature. On the Bach chorales
[fetched]: "the time complexity is such that it is possible to consider models with significantly
larger state spaces; in particular, we fit models with up to 1000 states. Second, given the
componential parametrization of the factorial HMM, these large state spaces do not require excessively
large numbers of parameters relative to the number of data points. In particular, we saw no evidence
of overfitting even for the largest factorial HMM... the test set likelihood for the best factorial
HMM was an order of magnitude larger than the test set likelihood for the best HMM." Their
unconstrained HMMs overfit beyond 40 states; the best scored −9.0 bits per observation at 30 states.

### 1.6 What is actually doing the work — an unresolved confound

Because the likelihood factorises (§1.2), **none of the gain can come from joint estimation.** Two
candidates remain:

1. growth is no longer pulled onto the levels timescale (the arm's stated hypothesis); or
2. the conditional base rates are now cut on 16 cells instead of 6 — a finer conditioning of the
   *forecast composition*, not of the regime model.

The REPORT flags this honestly ("the arm changes the structure and the number of joint states (16
against 6) at once"). The cost of (2) is measured: mean effective sample size behind each forecast
fell **112.4 → 45.3** across all 30 indicator-horizon rows [derived]. A finer partition on thinner
evidence usually *hurts*; that it helped is the interesting part, and it is not explained by the
timescale story.

The per-indicator split argues against the arm's own mechanism at one year [derived from
`compare.json`]:

| horizon | any-time (`within_horizon`) | at-horizon |
|---:|---:|---:|
| 12 months | **+0.0297** | **+0.0884** |
| 60 months | +0.0732 | +0.0198 |
| 120 months | +0.2931 | +0.0524 |

The hypothesis predicted the gain would land on the any-time questions at one year. It landed on the
at-horizon questions, three times larger. The ten-year any-time number is dominated by
"recession within ten years" at +0.7300 — which is D4's compounding defect, not a regime-structure
effect. Skill improved on 26 of 30 rows, log loss on 26 of 30, calibration error on 25 of 30
[derived, confirming the REPORT's counts].

**The discriminating experiment is one setting, not an extension: refit main's single chain at
K = 16** (or at whatever K equalises the cell count) and see how much of the +0.0590 survives. If
most of it does, the win is conditioning granularity and the two-timescale story is decoration. This
should be run before any extension below is funded. [E1]

---

## 2. Which known extensions are worth trying next, ranked

Ranked by (expected gain) / (cost + overfitting risk + risk to the project's rules). "Cost" is in the
project's own terms: parameters against ~30 observed switches, lines in `models/`, new dependencies,
and whether a fresh pre-registration is needed.

### Rank 1 — Couple the two chains, in the cheap direction only · **DO THIS**

**Gain: high. Cost: low-to-medium. Overfitting risk: medium, and controllable.**

**Mechanism.** Let one chain's transition depend on the other's previous state, rather than being
independent of it. Ghahramani & Jordan's §5.2, "Introducing couplings", verbatim [fetched]:

> "The architecture for factorial HMMs presented in Section 2 assumes that the underlying Markov
> chains interact only through the observations. This constraint can be relaxed by introducing
> couplings between the hidden state variables (cf. Saul & Jordan, 1997). For example, if Sₜ^(m)
> depends on Sₜ₋₁^(m) and Sₜ₋₁^(m−1)... However, note that these couplings must be introduced with
> caution, as they may result in an exponential growth in parameters. For example, the above
> factorization requires transition matrices of size K² × K."

**References.** Ghahramani & Jordan 1997 §5.2 [fetched]. Brand, M., Oliver, N. & Pentland, A.,
"Coupled hidden Markov models for complex action recognition", *CVPR 1997*, 994–999,
doi:10.1109/CVPR.1997.609450 [metadata — 1058 citations per OpenAlex; not open access, full text not
read, no number used]. Saul, L. K. & Jordan, M. I., "Mixed Memory Markov Models: Decomposing Complex
Stochastic Processes as Mixtures of Simpler Ones", *Machine Learning* 37(1), 75–87,
doi:10.1023/A:1007649326333 [metadata; full text not read].

**Why this is rank 1 for *this* codebase specifically.** Three reasons, and the third is decisive.

1. **It is the only extension on this list that changes what the model can represent.** Everything
   else refines one chain or the layer above it. Without coupling the model is two separate HMMs
   (§1.2), and no amount of tuning changes that.
2. **It restores a capability the arm silently gave up.** The block-diagonal covariance means the
   model *cannot represent contemporaneous correlation between growth and inflation/rates at all* —
   main's full-covariance six-state model could. That is a deletion, and under the project's own
   doctrine a deletion is a decision that should be recorded with a reason. Coupling in the
   transition is the cheap way to buy back the dependence without a full covariance.
3. **The expensive part is already built and already being paid for.** The repo runs the exact
   forward–backward over all 16 joint states (§1.2). Coupling breaks the *M-step* factorisation — the
   complete-data likelihood no longer separates, so counts cannot be marginalised to each chain — but
   it leaves the **E-step completely unchanged**, because the joint chain is still an ordinary
   16-state Markov chain and the emission still block-separates. The M-step becomes the ordinary
   single-chain transition update on the joint counts, restricted to the coupled parameterisation.
   Exact E-step (already implemented), exact M-step (a restriction of one already implemented). **No
   variational approximation, no Gibbs sampler, no new dependency, no threat to determinism.**

**Cost, with the arithmetic that decides the form.** Coupling the levels chain's transitions on the
growth state costs 4 × 12 = 48 free transition parameters in place of 12, i.e. **+36**, taking the
model from 58 to 94 — above main's 89, against ~30 observed switches. That is the same arithmetic
that sank TVTP in briefing 02 Rank 4, and it should sink this form too.

**The form to actually build** is the diagonal-only coupling: a single scalar per growth state saying
how the growth state shifts the levels chain's *persistence*, leaving the off-diagonal shape alone.
That is **+4 parameters**, taking 58 → 62. Direction matters and should be pre-registered: activity
leading inflation and policy is the economically motivated one-way direction (growth → levels), so
this is a directional hypothesis rather than a fishing expedition.

**What should move if it is right.** A free, sharp diagnostic falls out of §1.4: the identity
`joint λ₂ = max(λ₂ᵍ, λ₂ˡ)` holds **if and only if** the chains are independent. So fit the coupled
model and check whether the joint λ₂ departs from the maximum of the two chains'. If it does not, the
coupling estimated to zero and the independence assumption is vindicated — a publishable negative
result at a cost of four parameters. If it does, the one-year at-horizon indicators (where the arm's
gain actually is, +0.0884) are where to look for it.

### Rank 2 — Transition probabilities that vary with an observable, on the growth chain only · **DEFER, but the arithmetic has changed**

**Gain: unmeasured at this project's horizons. Cost: medium. Overfitting risk: medium.**

**Mechanism.** `P(Sₜ | Sₜ₋₁, Xₜ)`. Ghahramani & Jordan call this the input-conditioned factorial HMM
and note [fetched] that "inference in input-conditioned factorial HMMs is a straightforward
generalization of the algorithms we have presented", with the transition structure modelled as "K
separate" conditional models, "one for each setting of Sₜ₋₁", using a softmax so that "a valid
probability transition matrix is defined at each point in input space". They also give the warning
that applies directly here: if the transition structure "is not decomposed as above, but has a complex
dependence on the previous state variable and input, inference may become considerably more complex",
and for general nonlinear forms "the M step can no longer be solved exactly and a gradient-based
generalized EM algorithm must be used."

**References.** Filardo, A. J., "Business-Cycle Phases and Their Transitional Dynamics", *JBES* 12(3),
299–308, doi:10.1080/07350015.1994.10524545 [metadata — 822 citations; not open access, full text not
read; briefing 02 Rank 4 fetched the surrounding records]. Bengio, Y. & Frasconi, P., "Input-output
HMMs for sequence processing", *IEEE TNN* 7(5), 1231–1249, doi:10.1109/72.536317 [metadata verified,
abstract fetched: "The model has a statistical interpretation we call input-output hidden Markov model
(IOHMM)... It can be trained by the estimation-maximization (EM) or generalized EM (GEM) algorithms"].
Diebold, Lee & Weinbach (1994) is the other standard economics citation; **the Philadelphia Fed
working-paper URL I tried 404s and I could not retrieve it — it is not relied on here.**

**What the factorial structure changes, and it is a real improvement.** Briefing 02 deferred TVTP on
decisive parameter arithmetic: K(K−1)·q new parameters, which at K = 5 is 20 per driver against ~30
switches. On the *joint* 16-state chain that would be 16·15·q = **240q** — hopeless. But on the
**growth chain alone** it is 4·3·q = **12q**, a 20× reduction, and it targets the one chain that
actually moves at business-cycle frequency (half-life 12.6 months). **The factorial structure converts
briefing 02's fatal objection into a survivable one.**

**Why it is still deferred.** Briefing 02's *other* objection is untouched: the best available Monte
Carlo evidence (Modée et al., arXiv:2605.14976v2, fetched there) finds forecast metrics differing by
under 1% between correct and misspecified TVTP specifications, and concludes the value "lies in
characterizing the regime dynamics rather than in short-horizon forecasting". Their own caveat — that
they tested only one-step-ahead point forecasts, and that at longer horizons misspecification "would
likely compound" — means this project's 12/60/120-month probability forecasts are the untested case,
not the refuted one. Unmeasured, not dead. It needs its own pre-registration and a single
theoretically-motivated driver (the term spread is the literature's default).

### Rank 3 — A prior on each chain's transition matrix · **DO, but expect little**

**Gain: low, and now measured. Cost: very low. Overfitting risk: negative.**

Briefing 02 ranked this first for the single-chain model, and the project ran it as arm A1. **The
result is in and it is close to nothing at one year:** paired difference +0.0046, 90% interval
[−0.0126, +0.0232], no verdict under the pre-registered rule. λ₂ fell as predicted (0.9777 → 0.9700 at
the first refit, 0.9845 → 0.9761 at the last) and every exact zero was removed from the transition
matrix. Ten-year skill rose +0.1905, 90% [+0.0899, +0.2320].

**Why to expect even less on the two-chain model** [E1]: main's problem was nine exact zeros among 20
off-diagonal cells estimated from ~30 switches. Each chain here has only 4 states and **12 free
transition parameters**, so the cells are better populated per parameter and the zero-cell pathology
is structurally smaller. The prior has less to fix.

**Reference.** Fox, E. B., Sudderth, E. B., Jordan, M. I. & Willsky, A. S., "A sticky HDP-HMM with
application to speaker diarization", *Annals of Applied Statistics* 5(2A), 1020–1056,
doi:10.1214/10-AOAS395 [metadata verified here; briefing 02 fetched the arXiv v3 and derived the
hyperparameter formulas — not repeated].

**On a nonparametric prior over the number of regimes:** briefing 02 Rank 9 already says adopt the
sticky parameter κ and leave the Dirichlet process, on grounds of MCMC, label switching and the
determinism rule. The factorial structure makes that verdict *stronger*, not weaker — you would need
one HDP per chain, and the number of joint states is their product. **Ruled out; see §4.**

Note the sequencing rule the project has already set: combining A1 with A4 is a **post-selection**
exercise and belongs to experiment 0003, which the 0002 pre-registration says must be registered
separately and labelled as such.

### Rank 4 — Averaging over restarts and over models rather than picking one fit · **DO the forecast-averaging form; the seed-audit motive is now retired**

**Gain: low-to-medium. Cost: low. Overfitting risk: none.**

**Mechanism and its founding observation.** The fit runs 20 restarts and keeps the argmax joint log
likelihood. Ghahramani & Jordan measured exactly this pathology in this exact model class [fetched]:

> "There was a large amount of variability in the final log likelihoods for the models learned by all
> the algorithms... One important remaining source of variance was the random seed used in each
> training run, which determined the initial parameters... **All algorithms appeared to be very
> sensitive to this random seed, suggesting that different runs on each training set found different
> local maxima or plateaus of the likelihood.** Some of this variability could be eliminated by
> explicitly adding a regularization term, which can be viewed as a prior on the parameters in maximum
> a posteriori parameter estimation. **Alternatively, Bayesian (or ensemble) methods could be used to
> average out this variability by integrating over the parameter space.**"

**But the obvious worry has now been checked, and it passes.** This briefing's first draft ranked this
first, on the theory that A4's headline might be a seed draw. Three seed variants exist on disk and
their one-year paired differences are **+0.059014, +0.060345, +0.060277** — a spread of **0.0013**,
standard deviation 0.00075, against a reported effect of +0.0590 and a 90% interval half-width of
0.0301 [derived]. **Seed variability is about 2% of the effect and about 4% of the interval
half-width.** The end-to-end result is robust to the seed, and the cheapest available objection to A4
is retired. Recording this is the most useful thing in this section.

**What remains worth doing** is averaging *forecasts* for calibration, not to guard against seed noise.
The supporting evidence is in briefing 01 (W1, W2): in M5 and M6 equal-weight combinations beat the
single best entrant, and the M6 organisers found averaging the top teams "consistently
outperform[ed]" the best individual. Hoeting, Madigan, Raftery & Volinsky, "Bayesian model averaging:
a tutorial", *Statistical Science* 14(4), 382–401, doi:10.1214/ss/1009212519 [metadata; full text not
read] is the standard reference for the Bayesian form.

**One hard constraint.** Average the **forecasts**, never the parameters. Under label switching,
averaging HMM parameters across restarts is incoherent; canonicalisation makes it *look* safe without
making it safe. Briefing 02 already flagged label switching via Hamilton's Handbook (Celeux, Hurn &
Robert; Frühwirth-Schnatter; Geweke).

**Related measured result.** A6 (fixed 50/50 climatology blend, zero fitted parameters) is the
already-run instance of "average rather than pick": one-year −0.0209, 90% [−0.0697, +0.0296];
**ten-year +0.2779, 90% [+0.1204, +0.3310]** [derived]. Averaging is worth little where the model has
skill and a great deal where it does not — which is exactly the shape §3 predicts.

### Rank 5 — Duration dependence / semi-Markov regimes · **DO NOT**

**Gain: low. Cost: medium. Overfitting risk: high.**

**Mechanism.** Replace the geometric dwell time a Markov chain implies with an explicit duration
distribution. Yu, S.-Z., "Hidden semi-Markov models", *Artificial Intelligence* 174(2), 215–243,
doi:10.1016/j.artint.2009.11.011 [metadata — 745 citations; the ScienceDirect PDF could not be
retrieved, full text not read, no number used]. Durland, J. M. & McCurdy, T. H.,
"Duration-Dependent Transitions in a Markov Model of U.S. GNP Growth", *JBES* 12(3), 279–288,
doi:10.1080/07350015.1994.10524543 [metadata verified — **see the DOI correction in §5**].

Briefing 02 Rank 8 already says DO NOT, on the grounds that the finding is about recessions (short,
quarterly, not what these states are), that it multiplies the state space by the duration cap τ, and
that it would be estimated from the same ~30 switches. **The factorial structure makes this strictly
worse:** the state space is already a product, so adding duration to each chain makes it a triple
product, K_g·τ_g·K_l·τ_l. At the arm's 4 × 4 with a modest τ = 24 that is 9,216 states.

**One caveat worth recording anyway, as a test rather than a model.** The geometric-dwell assumption
is what the entire λ₂ argument in §1.4 rests on — it is an eigenvalue statement about a Markov chain.
If regime dwell times are genuinely non-geometric, the information-horizon claim is wrong in a way no
amount of chain-splitting repairs. The cheap response is to **test** it, not model it: compare the
empirical distribution of regime run-lengths in the filtered path against the geometric implied by the
fitted diagonal. That is a diagnostic costing an afternoon, and it is the only thing in this section
worth doing. [E1]

---

## 3. What theory says about the ceiling

Briefing 02 §2 established the result and it is not repeated: the regime-mean process is exactly an
AR(1) in the second eigenvalue (Hamilton's Handbook eq. 3–4), Krolzig (2000) eq. (21) gives the
multivariate form, and "for h → ∞ the forecasts ŷ_{t+h|t} converge to the unconditional mean." The
question here is only what the factorial structure and its extensions do to that.

**The factorial structure changes nothing.** [derived] `Pʰ = Aʰ ⊗ Bʰ`. Each factor converges to its
own stationary distribution, so the joint converges to `π_g ⊗ π_l` at rate `max(|λ₂ᵍ|, |λ₂ˡ|)`. The
product of two ergodic chains is ergodic and mixes at the slower rate. **Splitting cannot beat the
slower chain**, which is why the information horizon is 60 months for both main and the arm.

Extension by extension:

- **Coupling (Rank 1).** The coupled joint process is still a finite, irreducible, aperiodic Markov
  chain, so it still converges geometrically at its own |λ₂|. Coupling changes *which* λ₂ — it can
  raise or lower it — but it cannot remove it. No ceiling change. [derived]
- **TVTP (Rank 2).** The forecast now depends on the path of X, so at horizon h you must forecast X
  too. If X is itself ergodic, the composite process is ergodic and the same convergence applies: the
  problem has moved, not gone. The only way to beat the ceiling is a driver that is itself predictable
  at h — which, if it existed, would already be the forecast. [derived/E1]
- **A prior on the transitions (Rank 3).** Strictly *lowers* the ceiling: it removes the forbidden
  transitions that can only make the chain more persistent. A1 measured it, λ₂ 0.9777 → 0.9700. It
  shortens the horizon, which briefing 02 correctly said was the point.
- **Averaging (Rank 4).** Each component converges to its own unconditional mean, so the average
  converges to a weighted average of unconditional means. Still a constant, still geometric. But see
  below — this is the one place the ceiling can be used rather than merely suffered.
- **Semi-Markov / duration (Rank 5).** The (state, elapsed-duration) pair is Markov, and if dwell
  times have finite mean the process is ergodic and converges as before. The *only* construction that
  changes the asymptote is a dwell-time distribution with **infinite mean** — a non-ergodic,
  long-memory regime process. That is a genuine mathematical escape hatch and a terrible modelling
  choice on 908 months of data. [derived/E1]
- **Nonparametric prior over K.** Changes K, not the algebra. No effect whatever on the ceiling.

**So the ceiling is a property of the model class, and every extension considered here is inside the
class.** Briefing 02's framing — the horizon result is a theorem, not a disappointment — survives
factorisation, coupling, time-varying transitions, priors and model averaging alike. That is a
stronger statement than briefing 02 could make, and it belongs in the paper.

**What the ceiling does *not* fix, and this is the live lever.** Convergence says the forecast becomes
a constant. It says nothing about whether that constant is any good. At ten years main scores −0.3528
and the arm −0.1673 — both *worse than climatology*. A model converging to a wrong constant loses to
one converging to the right one, and that is a statement about the unconditional distribution the
chain implies, not about λ₂. The repository has already measured the crudest possible intervention:
A6's parameter-free 50/50 climatology blend gives **ten-year +0.2779, 90% [+0.1204, +0.3310]**
[derived]. The arm's own ten-year gain (+0.1855) is plausibly the same mechanism — a better-centred
constant, or a faster approach to one — rather than better regime inference. [E1, on measured inputs]

**The recommendation that follows:** long-horizon work should target *what the model converges to*,
not the rate at which it gets there. Nothing on the ranked list does that; A6 already does, and it is
the arm whose ten-year interval is most decisively above zero.

---

## 4. What not to try, and why

1. **Do not present "joint λ₂ = the slower chain's" as a confirmed prediction without qualification.**
   It is an algebraic identity (§1.4), true before any data was seen. It is a sound implementation
   check and zero evidence for the two-timescale hypothesis.
2. **Do not adopt HDP-HMM or infinite-HMM machinery.** Briefing 02 Rank 9 (MCMC, label switching, a
   fight with the determinism rule). The factorial structure strengthens the verdict: one Dirichlet
   process per chain, and the joint state count is their product. Take κ, leave the DP — and A1 has
   now measured what taking κ buys at one year: +0.0046, interval spanning zero.
3. **Do not add duration dependence or go hidden-semi-Markov.** Briefing 02 Rank 8, reinforced by the
   product state space (§2 Rank 5): 4 × 4 with τ = 24 is 9,216 states from ~30 observed switches.
4. **Do not go to MS-VAR, MS-GARCH, particle filters, or continuous latent states.** Briefing 02 Ranks
   6, 7 and 10 settled these. The factorial structure supplies no new reason to reopen any of them.
5. **Do not average HMM parameters across restarts, seeds or models.** Label switching makes it
   incoherent. Average forecasts. (§2 Rank 4)
6. **Do not add a third chain.** Each chain multiplies the joint state count and divides the evidence
   behind every conditional rate again. Effective sample size is already 112.4 → 45.3; a third 4-state
   chain would take it to roughly 11. **The forecasting layer, not the fit, is the binding constraint
   on this model** — which is the single most useful thing §1.6 establishes.
7. **Do not re-run the direct-horizon-rates idea in its A5 form.** It came back **HARMFUL**: one-year
   90% interval [−0.1448, −0.0586], entirely below the −0.02 threshold. D4's compounding problem is
   real and still open, but this mechanism is refuted and a second attempt needs a different one.
8. **Do not treat the coupling extension as free because the E-step is already built.** It is cheap,
   not free: the naive +36-parameter form exceeds main's total parameter count against ~30 switches.
   Build the +4-parameter diagonal form or nothing.
9. **Do not fund any extension before the K = 16 single-chain control is run.** §1.6: the arm changed
   structure and cell count at once, and one setting separates them. Spending on extensions to a
   mechanism that may not be the mechanism is the expensive mistake available here.

---

## 5. What I could not verify

**Full text not opened — metadata verified via Crossref and/or OpenAlex, contents not read, and no
number in this briefing is taken from any of them:** Brand, Oliver & Pentland (CVPR 1997); Saul &
Jordan (*Machine Learning* 1999); Yu (*Artificial Intelligence* 2010); Filardo (*JBES* 1994); Durland
& McCurdy (*JBES* 1994); Teh, Jordan, Beal & Blei (*JASA* 2006, doi:10.1198/016214506000000302);
Hoeting, Madigan, Raftery & Volinsky (1999); Fox, Sudderth, Jordan & Willsky (2011 — briefing 02 read
the arXiv v3). Semantic Scholar returned a null abstract for every one of these DOIs except Bengio &
Frasconi, whose abstract was retrieved and is quoted.

**Could not retrieve at all, and therefore not relied on:** Diebold, Lee & Weinbach, "Regime Switching
with Time-Varying Transition Probabilities" — the Philadelphia Fed working-paper URL returns a 404
page. It is named in §2 Rank 2 as a standard reference only, with no claim attached.

**A DOI correction for the record.** My first guess at Durland & McCurdy's DOI,
`10.1080/07350015.1994.10524541`, resolves via Crossref to **Hamilton's "Associate Editor's
Introduction: Changes in Regime and the Business Cycle"** — a different paper in the same issue. The
correct DOIs are Durland & McCurdy `10.1080/07350015.1994.10524543` and Filardo
`10.1080/07350015.1994.10524545`. DOIs in this *JBES* 12(3) block are adjacent and trivial to
mis-cite; anything citing them should be checked against Crossref rather than pattern-matched.

**Access note on the primary source.** OpenAlex reports Ghahramani & Jordan (1997) as open access and
gives the Springer PDF as its best location, but Springer redirects an automated fetcher to an
authentication endpoint. The full text quoted here was obtained by downloading that PDF and
extracting the text locally. The NIPS 8 (1995) predecessor is separately and freely available from
`papers.nips.cc` and is a genuinely different, shorter paper — mean-field only, no structured
variational approximation. Quote the 1997 journal version.

**Working-paper versus published divergence.** The Sims, Waggoner & Zha text read here is **Atlanta
Fed Working Paper 2006-22 (November 2006)**, from EconStor, not the 2008 *Journal of Econometrics*
article. Section II.3.2 and the parameter-count formula should be checked against the published
version before external citation.

**Synthetic-source check.** No future-dated papers were used or needed. Every source in this briefing
is from 1989–2011 and each was confirmed against Crossref or OpenAlex with a citation count
consistent with its age and reputation. The two 2026-dated preprints assessed in briefing 02 are
referenced only through that briefing's own assessment.

**Claims I am asserting rather than citing, flagged as E1:** that the λ₂ identity's
non-falsifiability materially affects how the arm's prediction record should be read; that the
conditioning-granularity confound (§1.6) is the leading alternative explanation for the measured gain;
that the growth → levels direction is the economically motivated one for a one-way coupling; that the
block-diagonal covariance constitutes a capability deletion worth recording; and the reading of A6's
ten-year result as evidence about *what* the model converges to rather than how fast. Each is
reasoning from measured inputs, not a result.

---

## Derived numbers

Every **[derived]** figure above is produced by
`research/briefings/derivations/factorial_regime_algebra.py` — deterministic (seed 20260916), reading
only the arm output directories under `forecasting-the-future-arms/`, fetching nothing. Re-run it to
re-check any number in this briefing.
