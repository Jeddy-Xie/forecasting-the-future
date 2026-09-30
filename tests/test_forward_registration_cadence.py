"""The monthly forward round, and the check that stands in for a scheduler.

Delegated decision P1-8: register forward on the first of every month, beside the
shipped configuration. Nothing schedules that, so the pipeline warns when the
register has gone a round without one, and `forecast register --check` fails.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from economic_regime_forecasting import command_line_interface, forecast_register


def _register_with_round_made_on(path: Path, made_on: str) -> Path:
    record = {
        "indicator": "an_indicator",
        "question": "does it happen",
        "horizon_years": 1,
        "probability": 0.3,
        "source": "regime model",
        "model_probability": 0.3,
        "climatological_base_rate": 0.2,
        "data_as_of": "2026-08-01",
        "made_on": made_on,
        "resolves_on": "2027-08-01",
        "configuration_hash": "abc",
        "package_version": "1.0.0",
    }
    path.write_text(json.dumps(record) + "\n")
    return path


def test_a_register_with_a_round_this_month_is_current(tmp_path: Path) -> None:
    register = _register_with_round_made_on(tmp_path / "register.jsonl", "2026-09-29")
    assert forecast_register.days_since_last_round(date(2026, 10, 1), register) == 2
    assert forecast_register.staleness_warning(date(2026, 10, 1), register) is None


def test_a_register_past_forty_five_days_is_stale_and_says_what_to_run(tmp_path: Path) -> None:
    register = _register_with_round_made_on(tmp_path / "register.jsonl", "2026-09-09")
    warning = forecast_register.staleness_warning(date(2026, 10, 25), register)
    assert warning is not None
    assert "46 days old" in warning
    assert "monthly round" in warning


def test_an_empty_register_is_reported_rather_than_read_as_current(tmp_path: Path) -> None:
    warning = forecast_register.staleness_warning(date(2026, 10, 1), tmp_path / "absent.jsonl")
    assert warning is not None and "empty" in warning


def test_the_command_line_carries_the_round_flags() -> None:
    parser = command_line_interface.build_parser()
    check = parser.parse_args(["register", "--check"])
    assert check.check is True and check.source_directory is None
    source = parser.parse_args(["register", "--from", "forecasts/companions/x"])
    assert source.source_directory == Path("forecasts/companions/x")
    destination = parser.parse_args(["submit", "--destination", "elsewhere"])
    assert destination.destination == Path("elsewhere") and destination.verify_only is False
