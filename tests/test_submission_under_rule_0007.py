"""The submission under rule 0007: what ships, what each column is, and what refuses.

Delegated decision P2-2 made `submit` rule-driven. Under 0007 a horizon ships the
method's probability (the blend of the regime model and the condition chain) where
0007's verdict is SHIP MODEL, and R1, the model-sample climatology, where it is SHIP
BASE RATE. Every number the row was made from sits beside it under its own name.
The rule-0001 path is unchanged and pinned by tests/test_submission.py.
"""

from __future__ import annotations

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


def _verdicts(by_horizon: dict[int, str]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"horizon_months": horizon, "verdict": verdict} for horizon, verdict in by_horizon.items()]
    )


@pytest.fixture
def prepared(tmp_path: Path):  # type: ignore[no-untyped-def]
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
    artifacts.write_json(ARTIFACTS.burn_in_state_count_choice, {"state_count": 2})
    artifacts.write_table(
        ARTIFACTS.current_forecasts,
        pd.DataFrame(
            [
                {
                    "indicator": item.name,
                    "horizon_months": horizon,
                    "probability": 0.6,
                    "model_probability": 0.8,
                    "condition_chain_probability": 0.4,
                    "composition": item.composition.value,
                    "effective_sample_size": 250.0,
                    "distance_to_stationary": 0.3,
                    "question": item.question,
                }
                for item in indicators
                for horizon in HORIZONS
            ]
        ),
    )
    artifacts.write_table(
        ARTIFACTS.backtest_results,
        pd.DataFrame(
            [
                {
                    "indicator": item.name,
                    "forecast_date": pd.Timestamp("2000-01-01") + pd.DateOffset(months=offset),
                    "horizon_months": horizon,
                    "climatology_probability": 0.2 + 0.01 * offset,
                    # The latest value is 0.30; earlier ones must not be the one shipped.
                    "model_sample_climatology_probability": 0.1 + 0.1 * offset,
                    "configuration_hash": "abc",
                }
                for item in indicators
                for horizon in HORIZONS
                for offset in range(3)
            ]
        ),
    )
    artifacts.write_table(
        ARTIFACTS.verdicts,
        _verdicts({12: "SHIP MODEL", 60: "SHIP BASE RATE", 120: "SHIP BASE RATE"}),
    )
    artifacts.write_table(
        ARTIFACTS.successor_verdicts,
        _verdicts({12: "SHIP MODEL", 60: "SHIP BASE RATE", 120: "SHIP BASE RATE"}),
    )
    workspace = interface.Workspace(
        registry=registry,
        indicators=indicators,
        cache=SeriesCache(settings.cache.raw, settings.cache.vintage),
        artifacts=artifacts,
        settings=settings,
    )
    return workspace, artifacts, tmp_path / "elsewhere"


def _submitted(prepared, monkeypatch: pytest.MonkeyPatch) -> tuple[pd.DataFrame, dict]:  # type: ignore[no-untyped-def]
    workspace, _, destination = prepared
    monkeypatch.setattr(
        interface.Workspace,
        "observation_matrix_as_of",
        lambda self, today: type("M", (), {"dates": pd.DatetimeIndex(["2026-08-01"])})(),
    )
    monkeypatch.setattr(
        interface,
        "assemble_point_in_time_panel",
        lambda registry, today, cache: type("P", (), {"policy_counts": lambda self: {}})(),
    )
    assert interface.submit(workspace, date(2026, 9, 29), destination=destination, rule="0007") == 0
    return (
        pd.read_csv(destination / "forecasts.csv"),
        json.loads((destination / "manifest.json").read_text()),
    )


def test_a_ship_model_horizon_ships_the_blend_and_names_its_parts(prepared, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    grid, _ = _submitted(prepared, monkeypatch)
    one_year = grid[grid["horizon_years"] == 1]
    assert set(one_year["source"]) == {interface.BLEND_SOURCE}
    assert one_year["probability"].eq(0.6).all()
    assert one_year["blend_probability"].eq(0.6).all()
    assert one_year["regime_model_probability"].eq(0.8).all()
    assert one_year["condition_chain_probability"].eq(0.4).all()


def test_a_base_rate_horizon_ships_the_latest_model_sample_base_rate(prepared, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    grid, _ = _submitted(prepared, monkeypatch)
    later = grid[grid["horizon_years"] > 1]
    assert set(later["source"]) == {interface.MODEL_SAMPLE_BASE_RATE_SOURCE}
    assert later["probability"].eq(0.3).all()
    assert later["model_sample_base_rate"].eq(0.3).all()
    assert later["climatological_base_rate"].eq(0.22).all()
    assert set(later["verdict_0007"]) == {"SHIP BASE RATE"}


def test_the_grid_carries_every_column_the_decision_named(prepared, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    grid, _ = _submitted(prepared, monkeypatch)
    assert list(grid.columns) == [
        "indicator",
        "question",
        "horizon_years",
        "probability",
        "source",
        "blend_probability",
        "regime_model_probability",
        "condition_chain_probability",
        "model_sample_base_rate",
        "climatological_base_rate",
        "verdict_0001",
        "verdict_0007",
        "composition",
        "effective_sample_size",
        "distance_to_stationary",
    ]
    assert "model_probability" not in grid.columns


def test_the_manifest_records_the_governing_rule_and_both_verdicts(prepared, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _, manifest = _submitted(prepared, monkeypatch)
    assert manifest["governing_rule"] == "0007"
    assert manifest["verdict_by_horizon_0007"]["1_year"] == "SHIP MODEL"
    assert manifest["verdict_by_horizon_0001"]["5_year"] == "SHIP BASE RATE"
    assert manifest["verdict_by_horizon"] == manifest["verdict_by_horizon_0007"]
    assert manifest["base_rate_definition"].startswith("R1")


def test_a_structure_the_backtest_never_scored_refuses_before_anything_is_written(
    prepared,  # type: ignore[no-untyped-def]
) -> None:
    workspace, artifacts, destination = prepared
    artifacts.write_json(
        ARTIFACTS.burn_in_state_count_choice,
        {"state_count": 9, "growth_chain_state_count": 3, "levels_chain_state_count": 3},
    )
    with pytest.raises(interface.SubmissionStructureError, match="3 x 3"):
        interface.submit(workspace, date(2026, 9, 29), destination=destination, rule="0007")
    assert not destination.exists()


def test_the_command_line_ships_under_0007_unless_told_otherwise() -> None:
    parser = interface.build_parser()
    assert parser.parse_args(["submit"]).rule == "0007"
    assert parser.parse_args(["submit", "--rule", "0001"]).rule == "0001"
    with pytest.raises(SystemExit):
        parser.parse_args(["submit", "--rule", "0002"])


def test_an_unknown_rule_is_refused_by_the_function_too(prepared) -> None:  # type: ignore[no-untyped-def]
    workspace, _, destination = prepared
    with pytest.raises(ValueError, match="no rule"):
        interface.submit(workspace, date(2026, 9, 29), destination=destination, rule="0002")
