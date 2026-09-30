"""C. The size of rule 0007's calibration test, measured before the test is used.

Rule 0007 replaces 0001's ten-bin calibration gate, which a perfectly calibrated
forecaster fails about 91% of the time at n = 31 (section A of sim_calibration.py),
with a logistic recalibration test: the fitted slope's interval must contain 1 and
the intercept's must contain 0. The registration requires, before use, that a
perfectly calibrated forecaster pass it at least 80% of the time at this project's
sample size. If it does not, the fallback fixed in the registration applies: the
slope test alone.

The simulated panel is shaped like the real one:
- 378 monthly dates by 10 indicators, the one-year horizon's resolved sample;
- each indicator's true probability a persistent logit AR(1);
- outcomes serially correlated through an AR(1) Gaussian copula, as overlapping
  one-year windows are, and correlated across indicators through a shared factor.

The forecaster reports the true probability, so it is perfectly calibrated by
construction. The test runs exactly as the pipeline runs it (evaluation/calibration
assess_recalibration), with 12-month blocks and the skill gate's seed. Each
replication uses 1,000 resamples rather than the gate's 10,000, to keep the
simulation to minutes. The percentile interval's coverage does not depend on that.

Run: .venv/bin/python research/briefings/derivations/sim_recalibration_test_size.py
"""

from __future__ import annotations

import numpy as np
from scipy.stats import norm

from economic_regime_forecasting.evaluation.calibration import assess_recalibration

DATES, INDICATORS, REPLICATIONS, RESAMPLES = 378, 10, 200, 1000
PROBABILITY_PERSISTENCE, OUTCOME_PERSISTENCE, SHARED_FACTOR = 0.97, 0.92, 0.3
SEED = 20260929


def ar1(generator: np.random.Generator, persistence: float, shape: tuple[int, int]) -> np.ndarray:
    """Unit-variance AR(1) paths along the first axis."""
    shocks = generator.normal(size=shape)
    path = np.empty(shape)
    path[0] = shocks[0]
    scale = np.sqrt(1.0 - persistence**2)
    for time in range(1, shape[0]):
        path[time] = persistence * path[time - 1] + scale * shocks[time]
    return path


def one_panel(generator: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    levels = generator.normal(-1.0, 0.8, size=INDICATORS)
    log_odds = levels + 1.2 * ar1(generator, PROBABILITY_PERSISTENCE, (DATES, INDICATORS))
    probability = 1.0 / (1.0 + np.exp(-log_odds))
    common = ar1(generator, OUTCOME_PERSISTENCE, (DATES, 1))
    own = ar1(generator, OUTCOME_PERSISTENCE, (DATES, INDICATORS))
    latent = np.sqrt(SHARED_FACTOR) * common + np.sqrt(1.0 - SHARED_FACTOR) * own
    uniform = norm.cdf(latent)
    return probability, (uniform < probability).astype("float64")


def main() -> None:
    generator = np.random.default_rng(SEED)
    joint = slope_only = failed_to_fit = 0
    for replication in range(REPLICATIONS):
        predicted, realised = one_panel(generator)
        try:
            test = assess_recalibration(
                predicted,
                realised,
                block_length=12,
                resamples=RESAMPLES,
                seed=20260908 + replication,
            )
        except ValueError:
            failed_to_fit += 1
            continue
        slope_ok = test.slope_interval[0] <= 1.0 <= test.slope_interval[1]
        intercept_ok = test.intercept_interval[0] <= 0.0 <= test.intercept_interval[1]
        joint += int(slope_ok and intercept_ok)
        slope_only += int(slope_ok)
    scored = REPLICATIONS - failed_to_fit
    print(
        f"C. A perfectly calibrated forecaster, {DATES} dates x {INDICATORS} indicators, "
        f"12-month blocks, {RESAMPLES} resamples, {scored} of {REPLICATIONS} replications fitted"
    )
    print(f"  passes the joint test (slope contains 1 AND intercept contains 0): {joint / scored:.1%}")
    print(f"  passes the slope test alone:                                  {slope_only / scored:.1%}")
    print(f"  registered bar: at least 80% for the joint test, else the slope test alone applies")
    print(f"  applies: {'the joint test' if joint / scored >= 0.80 else 'the slope test alone'}")


if __name__ == "__main__":
    main()
