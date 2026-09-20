"""The submission chooses, per horizon, between the model and the base rate.

This is the last decision the pipeline makes and the only one a reader of the
final grid sees. It has real logic in it -- which number ships, and what the row
says it is -- so it is tested directly rather than left to the end-to-end run.
"""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from economic_regime_forecasting import command_line_interface as interface
from economic_regime_forecasting.configuration.registry import load_registries
from economic_regime_forecasting.configuration.run_settings import (
    ARTIFACTS,
    CacheLayout,
    RunSettings,
)
from economic_regime_forecasting.data.cache import ArtifactStore, SeriesCache
from economic_regime_forecasting.models.gaussian_hidden_markov_model import (
    GaussianHiddenMarkovModel,
)

HORIZONS = (12, 60, 120)


@pytest.fixture
def prepared(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """A workspace whose artifacts are already written, so submit has inputs."""
    settings = RunSettings(cache=CacheLayout(tmp_path / "cache"))
    settings.cache.create_directories()
    registry, indicators = load_registries()
    artifacts = ArtifactStore(settings.cache.models)

    model = GaussianHiddenMarkovModel(
        initial_distribution=np.array([0.5, 0.5]),
        transition_matrix=np.array([[0.95, 0.05], [0.05, 0.95]]),
        means=np.array([[-1.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
        covariances=np.repeat(np.eye(3)[None, :, :], 2, axis=0),
    )
    artifacts.write_json(ARTIFACTS.selected_model, model.to_dictionary())

    forecasts = pd.DataFrame(
        [
            {
                "indicator": item.name,
                "horizon_months": horizon,
                "probability": 0.8,
                "composition": item.composition.value,
                "effective_sample_size": 250.0,
                "distance_to_stationary": 0.3,
                "question": item.question,
            }
            for item in indicators
            for horizon in HORIZONS
        ]
    )
    artifacts.write_table(ARTIFACTS.current_forecasts, forecasts)

    results = pd.DataFrame(
        [
            {
                "indicator": item.name,
                "forecast_date": pd.Timestamp("2000-01-01") + pd.DateOffset(months=offset),
                "horizon_months": horizon,
                "climatology_probability": 0.2,
                "predicted_probability": 0.8,
                "realised_outcome": 1.0,
                "composition": item.composition.value,
                "effective_sample_size": 250.0,
                "distance_to_stationary": 0.3,
                "regime_distribution": "0.5,0.5",
                "state_count": 2,
                "refit_date": pd.Timestamp("2000-01-01"),
                "configuration_hash": "abc",
                "seed": 1,
            }
            for item in indicators
            for horizon in HORIZONS
            for offset in range(3)
        ]
    )
    artifacts.write_table(ARTIFACTS.backtest_results, results)

    monkeypatch.setattr(interface, "SUBMISSION_DIRECTORY", tmp_path / "submission")
    workspace = interface.Workspace(
        registry=registry,
        indicators=indicators,
        cache=SeriesCache(settings.cache.raw, settings.cache.vintage),
        artifacts=artifacts,
        settings=settings,
    )
    return workspace, artifacts, tmp_path / "submission"


def _write_verdicts(artifacts: ArtifactStore, verdict_by_horizon: dict[int, str]) -> None:
    artifacts.write_table(
        ARTIFACTS.verdicts,
        pd.DataFrame(
            [
                {
                    "horizon_months": horizon,
                    "horizon_years": horizon // 12,
                    "verdict": verdict,
                    "mean_brier_skill_score": 0.05,
                    "skill_lower_bound": 0.01,
                    "skill_upper_bound": 0.09,
                    "effective_independent_observations": 5.0,
                    "failing_gates": "none" if verdict == "SHIP MODEL" else "honesty",
                }
                for horizon, verdict in verdict_by_horizon.items()
            ]
        ),
    )


def test_a_horizon_that_ships_the_model_carries_the_model_probability(prepared) -> None:  # type: ignore[no-untyped-def]
    workspace, artifacts, directory = prepared
    _write_verdicts(artifacts, dict.fromkeys(HORIZONS, "SHIP MODEL"))
    assert interface.submit(workspace, date(2026, 9, 8)) == 0

    submission = pd.read_csv(directory / "forecasts.csv")
    assert set(submission["source"]) == {"regime model"}
    assert submission["probability"].eq(0.8).all()


def test_a_horizon_that_fails_a_gate_ships_the_base_rate_instead(prepared) -> None:  # type: ignore[no-untyped-def]
    """A well calibrated base rate beats an overconfident model under Brier
    scoring, so this is a result rather than a retreat."""
    workspace, artifacts, directory = prepared
    _write_verdicts(artifacts, {12: "SHIP MODEL", 60: "SHIP MODEL", 120: "SHIP BASE RATE"})
    interface.submit(workspace, date(2026, 9, 8))

    submission = pd.read_csv(directory / "forecasts.csv")
    ten_year = submission[submission["horizon_years"] == 10]
    assert set(ten_year["source"]) == {"base rate"}
    assert ten_year["probability"].eq(0.2).all()
    assert ten_year["model_probability"].eq(0.8).all()


def test_the_model_number_is_kept_beside_the_shipped_one(prepared) -> None:  # type: ignore[no-untyped-def]
    """A reader must be able to see what the model said even where it was not
    shipped, otherwise the base-rate decision is unauditable."""
    workspace, artifacts, directory = prepared
    _write_verdicts(artifacts, dict.fromkeys(HORIZONS, "SHIP BASE RATE"))
    interface.submit(workspace, date(2026, 9, 8))

    submission = pd.read_csv(directory / "forecasts.csv")
    assert {"model_probability", "climatological_base_rate", "source"} <= set(submission.columns)
    assert submission["model_probability"].notna().all()


def test_the_grid_is_ten_indicators_by_three_horizons(prepared) -> None:  # type: ignore[no-untyped-def]
    workspace, artifacts, directory = prepared
    _write_verdicts(artifacts, dict.fromkeys(HORIZONS, "SHIP MODEL"))
    interface.submit(workspace, date(2026, 9, 8))

    submission = pd.read_csv(directory / "forecasts.csv")
    assert len(submission) == 30
    assert submission["indicator"].nunique() == 10
    assert sorted(submission["horizon_years"].unique()) == [1, 5, 10]


def test_the_manifest_records_what_is_needed_to_reproduce_the_run(prepared) -> None:  # type: ignore[no-untyped-def]
    import json

    workspace, artifacts, directory = prepared
    _write_verdicts(artifacts, dict.fromkeys(HORIZONS, "SHIP MODEL"))
    interface.submit(workspace, date(2026, 9, 8))

    manifest = json.loads((directory / "manifest.json").read_text())
    for field in (
        "generated_on",
        "configuration_hash",
        "random_seed",
        "regimes",
        "second_largest_eigenvalue_modulus",
        "data_as_of",
        "verdict_by_horizon",
        "vintage_policy_counts",
        "pre_registration",
    ):
        assert field in manifest, field
    assert manifest["random_seed"] == workspace.settings.random_seed
    assert manifest["indicator_count"] == 10


def test_a_two_chain_manifest_records_how_its_regimes_factor(prepared) -> None:  # type: ignore[no-untyped-def]
    """Sixteen joint regimes say nothing about the two chains that make them, and the
    factorisation is what a reader needs to rebuild the model. ADR 0010 made the two-chain
    model the default, so the manifest this writes is the one that describes a real run."""
    from economic_regime_forecasting.models.two_timescale_hidden_markov_model import (
        TwoTimescaleHiddenMarkovModel,
    )

    workspace, artifacts, directory = prepared
    growth = GaussianHiddenMarkovModel(
        initial_distribution=np.array([0.5, 0.5]),
        transition_matrix=np.array([[0.9, 0.1], [0.1, 0.9]]),
        means=np.array([[-1.0], [1.0]]),
        covariances=np.repeat(np.eye(1)[None, :, :], 2, axis=0),
    )
    levels = GaussianHiddenMarkovModel(
        initial_distribution=np.array([0.4, 0.3, 0.3]),
        transition_matrix=np.array([[0.9, 0.05, 0.05], [0.05, 0.9, 0.05], [0.05, 0.05, 0.9]]),
        means=np.array([[-1.0, 0.0], [0.0, 1.0], [1.0, -1.0]]),
        covariances=np.repeat(np.eye(2)[None, :, :], 3, axis=0),
    )
    artifacts.write_json(
        ARTIFACTS.selected_model, TwoTimescaleHiddenMarkovModel(growth, levels).to_dictionary()
    )
    _write_verdicts(artifacts, dict.fromkeys(HORIZONS, "SHIP MODEL"))

    assert interface.submit(workspace, date(2026, 9, 8)) == 0

    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["regimes"] == 6
    assert manifest["regimes_by_chain"] == {"growth": 2, "inflation_and_rates": 3}


def test_a_single_chain_manifest_says_nothing_about_chains(prepared) -> None:  # type: ignore[no-untyped-def]
    """The factorisation is absent rather than null for a model that has none, so a
    single-chain manifest is byte-identical to the ones already on the record."""
    workspace, artifacts, directory = prepared
    _write_verdicts(artifacts, dict.fromkeys(HORIZONS, "SHIP MODEL"))

    assert interface.submit(workspace, date(2026, 9, 8)) == 0

    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["regimes"] == 2
    assert "regimes_by_chain" not in manifest


def test_every_probability_in_the_grid_is_a_probability(prepared) -> None:  # type: ignore[no-untyped-def]
    workspace, artifacts, directory = prepared
    _write_verdicts(artifacts, {12: "SHIP MODEL", 60: "SHIP BASE RATE", 120: "SHIP BASE RATE"})
    interface.submit(workspace, date(2026, 9, 8))

    with (directory / "forecasts.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    for row in rows:
        assert 0.0 <= float(row["probability"]) <= 1.0
        assert row["question"]
