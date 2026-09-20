# 0004. The hidden Markov model is written out rather than imported

Date: 2026-09-08 · Status: accepted

## Context and problem
The dependency checklist says to prefer a well-maintained package over writing
code. `hmmlearn` exists, is maintained, and implements exactly the Gaussian hidden
Markov model this project needs. The default answer should have been to use it.

One requirement overturns that. A backtest may only use **filtered** state
probabilities: the distribution over the state at month t given observations up to
and including t. The libraries expose **smoothed** probabilities, which condition
on the whole sample including months after t. Using smoothed probabilities in a
walk-forward backtest is look-ahead of the purest kind, and it does not announce
itself. Every number stays plausible; they are merely impossible.

Getting filtered probabilities out of a library means reaching past its public
surface for the emission log-likelihood and running the forward pass yourself. At
that point the forward pass exists either way, and it is the part of the algorithm
most worth having under direct control.

## Decision
Implement the model in `models/gaussian_hidden_markov_model.py` on numpy and
scipy: forward-backward and Viterbi in log space, Baum-Welch fitting with
k-means++ seeding and random restarts spread across persistence levels.

Filtered and smoothed probabilities are separate methods with deliberately
different names, and the smoothed one carries a docstring saying it must not be
used in a backtest. The forward algorithm is checked against brute-force
enumeration of every state path on a short sequence, which is a genuinely
independent computation of the same quantity.

## Consequences
- Good: the one property the project rests on is a first-class method rather than
  a workaround, and it has a test that appending future observations leaves every
  earlier filtered probability untouched.
- Good: exact control over seeding, restarts and determinism. Two runs of the same
  configuration produce bit-identical models, which a library's internal random
  state would make harder to promise.
- Good: no dependency to pin, and no scikit-learn transitive tree for a three
  hundred line algorithm.
- Bad / accepted cost: this code is now ours to maintain and to get right.
  Mitigated by testing against enumeration, against the closed-form stationary
  distribution and second eigenvalue of a two-state chain, and by the fit raising
  if the likelihood ever falls, which expectation maximisation forbids.
- Bad / accepted cost: no community bug fixes. Accepted because the algorithm is
  fifty years old and does not change.

## Options considered
- Use `hmmlearn` and accept smoothed probabilities — rejected: that is the
  look-ahead this whole project exists to avoid.
- Use `hmmlearn` and reach into its internals for the forward pass — rejected:
  depends on private API for the load-bearing part, and still writes the pass.
- Use `statsmodels` Markov switching — rejected: its regression framing fits a
  different model, and it has the same smoothed-output problem.
  - **Correction, 2026-09-15.** The second half of that sentence is wrong.
    statsmodels' Markov-switching results compute `filtered_marginal_probabilities`
    in the Hamilton filter, separately from the smoothed ones
    (`statsmodels/tsa/regime_switching/markov_switching.py`, main branch, read
    2026-09-15), so there is no smoothed-output problem to avoid. The rejection
    stands, for a reason this record did not give: the same file raises "Must have
    univariate endogenous data." (line 567), and this model's observation vector has
    three dimensions. `research/briefings/02-state-space-and-regimes.md` raised the
    error; the check above confirmed it. The briefing's further claim, that the
    results also expose one-step predicted probabilities, was not confirmed by that
    check and is not repeated here.