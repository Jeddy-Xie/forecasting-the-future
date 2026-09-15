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

    hidden_state_counts_to_search: tuple[int, ...] = (1, 2, 3, 4, 5, 6)
    """The candidate numbers of latent regimes swept during model selection.

    One is in the list deliberately. A single-state model is not a regime model at
    all, it is a plain Gaussian, and it is the null the first acceptance gate tests
    against. Sweeping from two upward would have left the question "do regimes
    exist" with nothing to answer it, which is exactly what the gate caught the
    first time this ran."""

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

    select_state_count_on_a_burn_in_window: bool = True
    """Choose the number of regimes on the panel as it stood at the first forecast
    date, once, rather than on the panel as it stands today.

    False reproduces the shipped behaviour: `forecast fit-regimes` sweeps on today's
    panel and `forecast backtest` reads the winner off `selected_model.json`, so a
    forecast issued in 1972 uses a state count chosen with data through 2026."""

    start_walk_forward_when_every_input_is_point_in_time: bool = True
    """Begin the walk-forward at the first month where every model input is on a
    genuine point-in-time policy, rather than at the first month whose panel is
    merely long enough.

    False reproduces the shipped behaviour, in which 267 of 658 forecast dates fed
    the model revised consumer price index values through the publication-lag
    fallback -- 41% of the walk-forward, every month from 1971-12 to 1994-02."""

    cache: CacheLayout = field(default_factory=lambda: CacheLayout(_cache_root()))

    def configuration_hash(self) -> str:
        """Short stable digest of every setting that changes a result.

        The cache layout is excluded on purpose: where files live does not change
        what the numbers are. So is any field in
        ``SETTINGS_OMITTED_FROM_THE_HASH_WHEN_THEY_HOLD_THE_SHIPPED_VALUE`` that
        holds exactly the value that field's behaviour had before it existed --
        see that map for why.
        """
        import hashlib
        import json

        payload = {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in self.__dict__.items()
            if key != "cache"
            and not (
                key in SETTINGS_OMITTED_FROM_THE_HASH_WHEN_THEY_HOLD_THE_SHIPPED_VALUE
                and value == SETTINGS_OMITTED_FROM_THE_HASH_WHEN_THEY_HOLD_THE_SHIPPED_VALUE[key]
            )
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


SETTINGS_OMITTED_FROM_THE_HASH_WHEN_THEY_HOLD_THE_SHIPPED_VALUE: dict[str, object] = {
    "select_state_count_on_a_burn_in_window": False,
    "start_walk_forward_when_every_input_is_point_in_time": False,
}
"""Fields left out of the digest when they hold the behaviour that preceded them.

The digest answers exactly one question: *would two runs produce the same
numbers?* A field added after a run was published, set to the behaviour that was
in force before the field existed, changes no number -- so it must not change the
digest. Without this rule, adding a setting would silently re-label every result
already on the record: `submission/manifest.json`, thirty entries in
`forecasts/register.jsonl` and fifty-six cached fits under `.cache/models/` all
carry `9f95b12dba40d138`, and the numbers they describe did not move.

**This map is append-only and every entry is permanent.** Removing an entry, or
changing the value one maps to, retroactively changes the digest of runs already
published, which is the failure it exists to prevent. Adding a field here is only
legitimate when its listed value reproduces the behaviour of the code before that
field was introduced.
"""


@dataclass(frozen=True)
class ArtifactNames:
    """The file each stage writes, named once so notebooks and the command line
    interface cannot drift apart on a string."""

    data_audit: str = "data_audit.parquet"
    revision_audit: str = "revision_audit.parquet"
    state_count_sweep: str = "state_count_sweep.parquet"
    selected_model: str = "selected_model.json"
    regime_descriptions: str = "regime_descriptions.parquet"
    mixing_diagnostics: str = "mixing_diagnostics.parquet"
    current_forecasts: str = "current_forecasts.parquet"
    backtest_results: str = "backtest_results.parquet"
    evaluation_metrics: str = "evaluation_metrics.parquet"
    verdicts: str = "verdicts.parquet"
    gate_reports: str = "gate_reports.parquet"
    run_summary: str = "run_summary.json"
    run_manifest: str = "run_manifest.json"
    burn_in_state_count_choice: str = "burn_in_state_count_choice.json"
    variant_comparison: str = "variant_comparison.parquet"
    variant_comparison_manifest: str = "variant_comparison_manifest.json"
    look_ahead_audit: str = "look_ahead_audit.json"
    backtest_fallback_record: str = "backtest_fallback_record.json"

    def backtest_results_for_variant(self, variant: str) -> str:
        """One cell of the look-ahead comparison, kept apart from the default run."""
        return f"backtest_results_{variant}.parquet"

    def verdicts_for_variant(self, variant: str) -> str:
        return f"verdicts_{variant}.parquet"


ARTIFACTS = ArtifactNames()

DEFAULT_RUN_SETTINGS = RunSettings()
