"""One run can register several forecasters' claims; each is its own claim.

Delegated decision P2-6: the shipped method, the regime model alone, the single
chain, the condition chain R2 and the model-sample climatology R1 are all
registered forward. Two of them can share a configuration hash, so the register's
identity for a claim gains the forecaster, and a line written before the field
existed still reads, as its source.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from economic_regime_forecasting import forecast_register
from economic_regime_forecasting.forecast_register import RegisteredForecast


def _claim(forecaster: str | None, source: str = "regime model") -> RegisteredForecast:
    return RegisteredForecast(
        indicator="an_indicator",
        question="does it happen",
        horizon_years=1,
        probability=0.3,
        source=source,
        model_probability=0.3,
        climatological_base_rate=0.2,
        data_as_of="2026-08-01",
        made_on="2026-09-29",
        resolves_on="2027-08-01",
        configuration_hash="abc",
        package_version="1.0.0",
        forecaster=forecaster,
    )


def test_a_line_written_before_the_field_existed_reads_as_its_source(tmp_path: Path) -> None:
    line = {key: value for key, value in _claim(None).__dict__.items() if key != "forecaster"}
    register = tmp_path / "register.jsonl"
    register.write_text(json.dumps(line) + "\n")
    (entry,) = forecast_register.read_register(register)
    assert entry.forecaster is None
    assert entry.claimant == "regime model"
    assert entry.key[-1] == "regime model"


def test_two_forecasters_under_one_hash_are_two_claims_and_a_repeat_is_none(tmp_path: Path) -> None:
    register = tmp_path / "register.jsonl"
    written, skipped = forecast_register.register_forecasts(
        [_claim("condition_chain"), _claim("model_sample_climatology")], register
    )
    assert (written, skipped) == (2, 0)
    written, skipped = forecast_register.register_forecasts([_claim("condition_chain")], register)
    assert (written, skipped) == (0, 1)


def test_a_claim_with_no_forecaster_is_written_exactly_as_lines_always_were(
    tmp_path: Path,
) -> None:
    register = tmp_path / "register.jsonl"
    forecast_register.register_forecasts([_claim(None)], register)
    assert "forecaster" not in json.loads(register.read_text())


def test_a_grid_shipped_under_0007_registers_the_blend_against_r1(tmp_path: Path) -> None:
    grid = pd.DataFrame(
        [
            {
                "indicator": "an_indicator",
                "question": "does it happen",
                "horizon_years": 1,
                "probability": 0.6,
                "source": "blend of regime model and condition chain",
                "blend_probability": 0.6,
                "regime_model_probability": 0.8,
                "condition_chain_probability": 0.4,
                "model_sample_base_rate": 0.3,
                "climatological_base_rate": 0.22,
                "verdict_0001": "SHIP MODEL",
                "verdict_0007": "SHIP MODEL",
                "composition": "point_in_time",
                "effective_sample_size": 250.0,
                "distance_to_stationary": 0.3,
            }
        ]
    )
    grid.to_csv(tmp_path / "forecasts.csv", index=False)
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "configuration_hash": "7647c129be85291e",
                "data_as_of": "2026-08-01",
                "package_version": "1.0.0",
                "governing_rule": "0007",
            }
        )
    )
    (claim,) = forecast_register.forecasts_from_submission(
        tmp_path / "forecasts.csv", tmp_path / "manifest.json", date(2026, 9, 29)
    )
    assert claim.model_probability == 0.6
    assert claim.climatological_base_rate == 0.3
    assert claim.forecaster == "blend of regime model and condition chain"
    assert claim.resolves_on == "2027-08-01"


def test_a_resolution_names_the_forecaster_so_it_is_never_resolved_twice(tmp_path: Path) -> None:
    register = tmp_path / "register.jsonl"
    resolutions = tmp_path / "resolutions.jsonl"
    past = RegisteredForecast(
        **{
            **_claim("condition_chain").__dict__,
            "indicator": "unemployment_rate_above_five_percent_at_horizon",
            "data_as_of": "2000-01-01",
            "resolves_on": "2001-01-01",
        }
    )
    register.write_text(json.dumps(forecast_register._as_line(past)) + "\n")
    index = pd.date_range("1999-01-01", "2002-12-01", freq="MS")
    series = {"unemployment_rate": pd.Series(6.0, index=index)}
    first = forecast_register.resolve(series, date(2026, 9, 29), register, resolutions)
    second = forecast_register.resolve(series, date(2026, 9, 29), register, resolutions)
    assert first["resolved_now"] == 1
    assert second["resolved_now"] == 0
    assert json.loads(resolutions.read_text())["forecaster"] == "condition_chain"
