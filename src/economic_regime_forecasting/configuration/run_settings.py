"""Project paths, cache locations and the seeds that make a run reproducible.

Nothing here reads the network or the registries. It answers one question: where
does this project keep things, and what fixed numbers make two runs identical.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# The project root is the directory containing pyproject.toml. Resolving it from
# this file's location keeps every path anchored to the repository rather than to
# whatever directory a notebook happened to start in.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]


def _cache_root() -> Path:
    """Cache location, overridable so tests never touch the real cache."""
    override = os.environ.get("ECONOMIC_REGIME_FORECASTING_CACHE")
    return Path(override).expanduser().resolve() if override else PROJECT_ROOT / ".cache"


@dataclass(frozen=True)
class CacheLayout:
    """The four cache areas, each with a single kind of content.

    ``raw`` holds responses exactly as retrieved and is immutable once written.
    ``vintage`` holds point-in-time snapshots keyed by the date they were current.
    ``processed`` holds aligned panels derived from the two above.
    ``models`` holds fitted models and backtest artifacts.
    """

    root: Path

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def vintage(self) -> Path:
        return self.root / "vintage"

    @property
    def processed(self) -> Path:
        return self.root / "processed"

    @property
    def models(self) -> Path:
        return self.root / "models"

    def create_directories(self) -> None:
        for directory in (self.raw, self.vintage, self.processed, self.models):
            directory.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class RunSettings:
    """Everything a run needs in order to be repeatable by someone else.

    The defaults are the shipped configuration. A caller that changes one is
    producing a different run, and ``configuration_hash`` will say so.
    """

    random_seed: int = 20260908
    """Seed for every stochastic step. Recorded in each run manifest."""

    hidden_state_counts_to_search: tuple[int, ...] = (2, 3, 4, 5, 6)
    """The candidate numbers of latent regimes swept during model selection."""

    expectation_maximisation_restarts: int = 20
    """Random restarts per fit. The best log likelihood wins."""

    expectation_maximisation_max_iterations: int = 500
    expectation_maximisation_tolerance: float = 1e-6

    minimum_observations_before_first_fit: int = 240
    """Burn-in. Twenty years of monthly data before the first regime fit."""

    refit_every_n_months: int = 12
    """Walk-forward refit cadence. Between refits the transition matrix is held
    fixed and only the filtered state distribution advances."""

    forecast_horizons_in_months: tuple[int, ...] = (12, 60, 120)
    """One, five and ten years, expressed in the model's monthly time step."""

    conditional_rate_shrinkage_strength: float = 10.0
    """Beta prior strength pulling each per-regime rate toward the pooled rate."""

    information_horizon_total_variation_threshold: float = 0.05
    """Below this distance to the stationary distribution, a projected regime
    distribution carries no information the unconditional base rate lacks."""

    probability_clip: tuple[float, float] = (0.01, 0.99)
    """Log loss is unbounded at zero and one; probabilities are clipped for it."""

    bootstrap_resamples: int = 10000
    bootstrap_confidence_level: float = 0.90

    cache: CacheLayout = field(default_factory=lambda: CacheLayout(_cache_root()))

    def configuration_hash(self) -> str:
        """Short stable digest of every setting that changes a result.

        The cache layout is excluded on purpose: where files live does not change
        what the numbers are.
        """
        import hashlib
        import json

        payload = {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in self.__dict__.items()
            if key != "cache"
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


DEFAULT_RUN_SETTINGS = RunSettings()
