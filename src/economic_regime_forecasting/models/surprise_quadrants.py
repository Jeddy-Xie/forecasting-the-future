"""Starting points for expectation maximisation at the four surprise quadrants.

Research arm A3 of experiment 0002. Bridgewater's All Weather framing divides the
economy by whether growth and inflation come in above or below what was expected.
Once the growth and inflation columns have been replaced by their surprises
(``features.observation_matrix.replace_growth_and_inflation_with_surprises``),
that division is simply the sign of each column. A surprise's expected value is
zero, so the boundaries are zero and nothing is estimated to place them.

Every month falls in one of four quadrants. A quadrant's centroid is the mean of
its months in every column, rates included. Every restart begins its emission
means at those four centroids. The likelihood, not the starting point, decides
where the fit ends up.

A surprise of exactly zero counts as at-or-below expectation. It is a measure-zero
event on continuous data, and a fixed rule is better than an arbitrary one.
"""

from __future__ import annotations

import numpy as np

from economic_regime_forecasting.configuration.run_settings import RunSettings
from economic_regime_forecasting.features.observation_matrix import COLUMN_NAMES

GROWTH_COLUMN = COLUMN_NAMES.index("growth")
INFLATION_COLUMN = COLUMN_NAMES.index("inflation")

QUADRANT_COUNT = 4
"""K for research arm A3: one state per quadrant. Fixed by the pre-registration
and never tuned; a test reads the registration and checks the two agree."""

QUADRANT_ORDER: tuple[tuple[bool, bool], ...] = (
    (False, False),
    (False, True),
    (True, False),
    (True, True),
)
"""(growth surprise above zero, inflation surprise above zero), for each quadrant
in turn. The order is only a convention: the fitted model is canonicalised by its
emission means afterwards, so no label depends on it."""


class QuadrantInitialisationError(ValueError):
    """The quadrant centroids could not be computed from the observations given."""


def state_count_fixed_by_the_quadrant_structure(settings: RunSettings) -> int | None:
    """The state count every regime fit must use, or None when the sweep chooses."""
    return QUADRANT_COUNT if settings.growth_and_inflation_surprise_quadrants else None


def surprise_quadrant_centroids(observations: np.ndarray) -> np.ndarray:
    """Four starting means, one per growth-surprise by inflation-surprise quadrant.

    ``observations`` is the observation matrix as the model reads it, with growth
    and inflation already surprises. The result is shaped (4, dimensions), in the
    order of ``QUADRANT_ORDER``.

    An empty quadrant raises rather than falling back to a random start. It would
    mean the surprises are not centred on zero at all, and that is a finding to
    report, not something to paper over.
    """
    observations = np.atleast_2d(np.asarray(observations, dtype="float64"))
    if observations.shape[1] != len(COLUMN_NAMES):
        raise QuadrantInitialisationError(
            f"observations have {observations.shape[1]} columns; quadrant centroids need the "
            f"{len(COLUMN_NAMES)} of the observation matrix, {COLUMN_NAMES}"
        )
    if not np.isfinite(observations).all():
        raise QuadrantInitialisationError(
            "observations contain non-finite values, so a quadrant centroid would be undefined"
        )

    growth_above = observations[:, GROWTH_COLUMN] > 0.0
    inflation_above = observations[:, INFLATION_COLUMN] > 0.0
    centroids: list[np.ndarray] = []
    for growth_is_above, inflation_is_above in QUADRANT_ORDER:
        members = (growth_above == growth_is_above) & (inflation_above == inflation_is_above)
        if not bool(members.any()):
            raise QuadrantInitialisationError(
                f"no month has a growth surprise {'above' if growth_is_above else 'at or below'} "
                f"zero together with an inflation surprise "
                f"{'above' if inflation_is_above else 'at or below'} zero, out of "
                f"{observations.shape[0]} months. Surprises that never land in a quadrant are "
                "not centred on their expected value; inspect the expectation model before "
                "fitting."
            )
        centroids.append(observations[members].mean(axis=0))
    return np.vstack(centroids)
