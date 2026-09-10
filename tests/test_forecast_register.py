"""The forecast register: what it records, what it refuses, and how it scores.

Every test here pins a promise the register makes about the record it keeps. The
register's whole value is that a forecast cannot be quietly changed after the
outcome is known, so most of these are about refusing, not about computing.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from economic_regime_forecasting import forecast_register

SUBMISSION_COLUMNS = [
    "indicator",
    "question",
    "horizon_years",
    "probability",
    "source",
    "model_probability",
    "climatological_base_rate",
]


def write_submission(
    directory: Path,
    rows: list[dict[str, object]],
    *,
    data_as_of: str = "2020-07-01",
    configuration_hash: str = "abc123",
) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    csv_path = directory / "forecasts.csv"
    manifest_path = directory / "manifest.json"
    pd.DataFrame(rows, columns=SUBMISSION_COLUMNS).to_csv(csv_path, index=False)
    manifest_path.write_text(
        json.dumps(
            {
                "configuration_hash": configuration_hash,
                "data_as_of": data_as_of,
                "package_version": "1.0.0",
            }
        )
    )
    return csv_path, manifest_path


def a_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "indicator": "recession_within_horizon",
        "question": "Does a recession begin before the horizon?",
        "horizon_years": 1,
        "probability": 0.30,
        "source": "regime model",
        "model_probability": 0.30,
        "climatological_base_rate": 0.20,
    }
    row.update(overrides)
    return row


class TestResolutionDates:
    def test_resolution_date_is_the_as_of_date_plus_the_horizon(self, tmp_path: Path):
        csv_path, manifest_path = write_submission(
            tmp_path / "submission", [a_row(horizon_years=5)], data_as_of="2026-07-01"
        )
        entries = list(
            forecast_register.forecasts_from_submission(csv_path, manifest_path, date(2026, 9, 9))
        )
        assert entries[0].resolves_on == "2031-07-01"

    def test_the_horizon_counts_from_the_data_not_from_the_day_it_was_written(self, tmp_path: Path):
        """A forecast is about the future of the data it saw, not of the day the
        operator happened to run the command."""
        csv_path, manifest_path = write_submission(
            tmp_path / "submission", [a_row(horizon_years=1)], data_as_of="2026-07-01"
        )
        entries = list(
            forecast_register.forecasts_from_submission(csv_path, manifest_path, date(2026, 12, 25))
        )
        assert entries[0].made_on == "2026-12-25"
        assert entries[0].resolves_on == "2027-07-01"

    def test_a_leap_day_forecast_resolves_on_the_twenty_eighth(self, tmp_path: Path):
        csv_path, manifest_path = write_submission(
            tmp_path / "submission", [a_row(horizon_years=1)], data_as_of="2024-02-29"
        )
        entries = list(
            forecast_register.forecasts_from_submission(csv_path, manifest_path, date(2024, 3, 1))
        )
        assert entries[0].resolves_on == "2025-02-28"


class TestAppendOnly:
    def test_registering_the_same_run_twice_records_it_once(self, tmp_path: Path):
        csv_path, manifest_path = write_submission(tmp_path / "submission", [a_row()])
        register_file = tmp_path / "register.jsonl"

        first, skipped_first = forecast_register.register(
            csv_path, manifest_path, date(2026, 9, 9), register_file
        )
        second, skipped_second = forecast_register.register(
            csv_path, manifest_path, date(2026, 9, 10), register_file
        )

        assert (first, skipped_first) == (1, 0)
        assert (second, skipped_second) == (0, 1), "a claim made once is not a claim made twice"
        assert len(forecast_register.read_register(register_file)) == 1

    def test_a_new_configuration_hash_is_a_new_claim_kept_beside_the_old(self, tmp_path: Path):
        """Which forecast you believed at the time is exactly what is being
        tested, so a re-run under changed code appends rather than replaces."""
        register_file = tmp_path / "register.jsonl"
        first_csv, first_manifest = write_submission(
            tmp_path / "one", [a_row(probability=0.30)], configuration_hash="aaa"
        )
        second_csv, second_manifest = write_submission(
            tmp_path / "two", [a_row(probability=0.55)], configuration_hash="bbb"
        )

        forecast_register.register(first_csv, first_manifest, date(2026, 9, 9), register_file)
        forecast_register.register(second_csv, second_manifest, date(2026, 9, 9), register_file)

        entries = forecast_register.read_register(register_file)
        assert [entry.probability for entry in entries] == [0.30, 0.55]

    def test_a_hand_edited_register_is_refused_rather_than_half_read(self, tmp_path: Path):
        register_file = tmp_path / "register.jsonl"
        register_file.write_text('{"indicator": "x"}\nnot json at all\n')
        with pytest.raises(forecast_register.RegisterError, match="not a forecast record"):
            forecast_register.read_register(register_file)


class TestRefusals:
    def test_registering_without_a_submission_says_what_to_run(self, tmp_path: Path):
        with pytest.raises(forecast_register.RegisterError, match="forecast submit"):
            forecast_register.register(
                tmp_path / "missing.csv", tmp_path / "missing.json", date(2026, 9, 9)
            )

    def test_a_manifest_without_a_configuration_hash_is_refused(self, tmp_path: Path):
        directory = tmp_path / "submission"
        directory.mkdir()
        pd.DataFrame([a_row()], columns=SUBMISSION_COLUMNS).to_csv(
            directory / "forecasts.csv", index=False
        )
        (directory / "manifest.json").write_text(
            json.dumps({"data_as_of": "2026-07-01", "package_version": "1.0.0"})
        )
        with pytest.raises(forecast_register.RegisterError, match="configuration_hash"):
            forecast_register.register(
                directory / "forecasts.csv",
                directory / "manifest.json",
                date(2026, 9, 9),
                tmp_path / "register.jsonl",
            )


class TestDue:
    def test_only_forecasts_whose_date_has_passed_are_due(self, tmp_path: Path):
        csv_path, manifest_path = write_submission(
            tmp_path / "submission",
            [a_row(horizon_years=1), a_row(horizon_years=5), a_row(horizon_years=10)],
            data_as_of="2020-07-01",
        )
        register_file = tmp_path / "register.jsonl"
        forecast_register.register(csv_path, manifest_path, date(2020, 9, 1), register_file)
        entries = forecast_register.read_register(register_file)

        # As-of 2020-07-01, the three horizons resolve in 2021, 2025 and 2030.
        assert len(forecast_register.due(entries, date(2019, 1, 1))) == 0
        assert len(forecast_register.due(entries, date(2022, 1, 1))) == 1
        assert len(forecast_register.due(entries, date(2026, 9, 9))) == 2
        assert len(forecast_register.due(entries, date(2031, 9, 9))) == 3


class TestScorecard:
    def _resolutions(self, path: Path, count: int, probability: float, outcome: float) -> None:
        path.write_text(
            "\n".join(
                json.dumps(
                    {
                        "indicator": f"indicator_{index}",
                        "horizon_years": 1,
                        "data_as_of": "2020-07-01",
                        "configuration_hash": "abc123",
                        "resolves_on": "2021-07-01",
                        "resolved_on": "2021-07-02",
                        "outcome": outcome,
                        "probability": probability,
                        "climatological_base_rate": 0.5,
                        "source": "regime model",
                        "brier": round((probability - outcome) ** 2, 6),
                        "brier_climatology": round((0.5 - outcome) ** 2, 6),
                    }
                )
                for index in range(count)
            )
            + "\n"
        )

    def test_an_empty_register_scores_nothing_and_says_so(self, tmp_path: Path):
        card = forecast_register.scorecard(tmp_path / "none.jsonl")
        assert card["n"] == 0
        assert card["inert"] is True

    def test_below_ten_resolved_forecasts_the_scorecard_is_inert(self, tmp_path: Path):
        path = tmp_path / "resolutions.jsonl"
        self._resolutions(path, count=9, probability=0.9, outcome=1.0)
        card = forecast_register.scorecard(path)
        assert card["n"] == 9
        assert card["inert"] is True, "a skill score on nine observations is a number, not evidence"

    def test_at_ten_resolved_forecasts_the_scorecard_becomes_readable(self, tmp_path: Path):
        path = tmp_path / "resolutions.jsonl"
        self._resolutions(path, count=10, probability=0.9, outcome=1.0)
        card = forecast_register.scorecard(path)
        assert card["n"] == 10
        assert card["inert"] is False

    def test_a_confident_correct_forecast_beats_the_base_rate(self, tmp_path: Path):
        path = tmp_path / "resolutions.jsonl"
        self._resolutions(path, count=10, probability=0.9, outcome=1.0)
        card = forecast_register.scorecard(path)
        # Brier 0.01 against a climatology of 0.25 is a skill score of 0.96.
        assert card["brier"] == pytest.approx(0.01)
        assert card["brier_climatology"] == pytest.approx(0.25)
        assert card["skill"] == pytest.approx(0.96)

    def test_a_confident_wrong_forecast_loses_to_the_base_rate(self, tmp_path: Path):
        path = tmp_path / "resolutions.jsonl"
        self._resolutions(path, count=10, probability=0.9, outcome=0.0)
        card = forecast_register.scorecard(path)
        assert card["skill"] < 0, "being confidently wrong must score worse than climatology"

    def test_horizons_are_scored_separately(self, tmp_path: Path):
        path = tmp_path / "resolutions.jsonl"
        records = []
        for horizon, probability in ((1, 0.9), (10, 0.1)):
            for index in range(3):
                records.append(
                    {
                        "indicator": f"indicator_{index}",
                        "horizon_years": horizon,
                        "data_as_of": "2020-07-01",
                        "configuration_hash": "abc123",
                        "resolves_on": "2021-07-01",
                        "resolved_on": "2021-07-02",
                        "outcome": 1.0,
                        "probability": probability,
                        "climatological_base_rate": 0.5,
                        "source": "regime model",
                        "brier": round((probability - 1.0) ** 2, 6),
                        "brier_climatology": 0.25,
                    }
                )
        path.write_text("\n".join(json.dumps(record) for record in records) + "\n")

        card = forecast_register.scorecard(path)
        assert card["by_horizon"]["1"]["skill"] > 0
        assert card["by_horizon"]["10"]["skill"] < 0
