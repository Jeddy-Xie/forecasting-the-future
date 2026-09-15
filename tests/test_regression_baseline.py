"""The regression baseline: what it records, and what it refuses to call a pass.

This is the instrument every later experiment is scored with, so the tests here
are mostly about the two ways an instrument like this fails silently. A tolerance
that absorbs the difference it exists to detect makes every comparison decorative
(ADR 0008 on ``assert_frame_equal``), and a byte-identity check fails for
environment reasons that are not regressions. Both are pinned below, from both
sides: 1e-13 must not be a regression and 1e-6 must be.

Every fixture here is synthetic and offline. The numbers are made up; what is
being tested is the classification, not the pipeline that produced them.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from economic_regime_forecasting import command_line_interface, regression_baseline
from economic_regime_forecasting.configuration.run_settings import ARTIFACTS, DEFAULT_RUN_SETTINGS
from economic_regime_forecasting.data.cache import ArtifactStore
from economic_regime_forecasting.evaluation import verdict as verdict_module

CONFIGURATION_HASH = "ad7fcc1affd0746a"
INDICATORS = ("recession_within_horizon", "unemployment_above_six_percent_at_horizon")
HORIZONS = (12, 60, 120)


def _backtest_results() -> pd.DataFrame:
    """Two forecast dates, one refit, one configuration. The identity columns a
    baseline reads, and the three a forecasts file records; the numbers in those
    three are placeholders, scored only by the paired tests' own frame below."""
    rows = []
    for forecast_date in ("1994-03-01", "1994-04-01", "1995-03-01"):
        for indicator in INDICATORS:
            for horizon in HORIZONS:
                rows.append(
                    {
                        "indicator": indicator,
                        "forecast_date": pd.Timestamp(forecast_date),
                        "horizon_months": horizon,
                        "predicted_probability": 0.25,
                        "climatology_probability": 0.3,
                        "realised_outcome": 1.0 if indicator == INDICATORS[0] else 0.0,
                        "refit_date": pd.Timestamp(forecast_date[:4] + "-03-01"),
                        "state_count": 6,
                        "configuration_hash": CONFIGURATION_HASH,
                        "seed": 20260908,
                    }
                )
    return pd.DataFrame(rows)


def _verdicts() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "horizon_months": list(HORIZONS),
            "horizon_years": [1, 5, 10],
            "verdict": ["SHIP BASE RATE", "SHIP BASE RATE", "SHIP BASE RATE"],
            "mean_brier_skill_score": [0.21275102068469728, 0.0721876491663, -0.3523874],
            "skill_lower_bound": [0.09729042168250875, -0.198648, -0.420812],
            "skill_upper_bound": [0.3250341810756218, 0.217625, -0.121172],
            "effective_independent_observations": [31.5, 5.5, 2.25],
            "failing_gates": [
                "calibration",
                "skill, calibration, robustness",
                "skill, calibration, robustness, honesty",
            ],
        }
    )


def _evaluation_metrics() -> pd.DataFrame:
    """Six rows. One ``area_under_the_curve`` is missing, as it is on the live
    cache, because a horizon whose resolved outcomes are all one class has no
    curve to measure."""
    rows: list[dict[str, Any]] = []
    for position, indicator in enumerate(INDICATORS):
        for offset, horizon in enumerate(HORIZONS):
            step = position * 3 + offset
            rows.append(
                {
                    "indicator": indicator,
                    "horizon_months": horizon,
                    "resolved_forecasts": 367 - step,
                    "base_rate": 0.1226158038147139 + step / 100,
                    "brier_score": 0.08942725780369012 + step / 100,
                    "climatology_brier_score": 0.16363499585854965 + step / 100,
                    "brier_skill_score": 0.45349552316429076 - step / 100,
                    "logarithmic_loss": 0.33623057014268876 + step / 100,
                    "area_under_the_curve": (
                        float("nan") if step == 5 else 0.7403036576949621 - step / 100
                    ),
                    "expected_calibration_error": 0.10261618873161059 + step / 100,
                    "reliability": 0.022513649404115668 + step / 100,
                    "resolution": 0.040232575333146725 + step / 100,
                    "mean_distance_to_stationary": 0.4172544946118196 - step / 100,
                    "mean_effective_sample_size": 118.36305100878882 - step,
                }
            )
    return pd.DataFrame(rows)


def _variant_comparison() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "variant": ["both"] * 3 + ["shipped"] * 3,
            "configuration_hash": [CONFIGURATION_HASH] * 3 + ["9f95b12dba40d138"] * 3,
            "forecast_date_count": [3] * 3 + [658] * 3,
            "forecast_dates_using_fallback": [0] * 3 + [267] * 3,
            "horizon_months": list(HORIZONS) * 2,
        }
    )


@pytest.fixture
def artifacts(tmp_path: Path) -> ArtifactStore:
    """A cache holding exactly the artifacts a baseline is assembled from."""
    store = ArtifactStore(tmp_path / "models")
    store.write_table(ARTIFACTS.backtest_results, _backtest_results())
    store.write_table(ARTIFACTS.verdicts, _verdicts())
    store.write_table(ARTIFACTS.evaluation_metrics, _evaluation_metrics())
    store.write_table(ARTIFACTS.variant_comparison, _variant_comparison())
    store.write_json(
        ARTIFACTS.burn_in_state_count_choice,
        {"state_count": 6, "chosen_as_of": "1994-03-01", "reason": "6 states wins"},
    )
    store.write_json(
        ARTIFACTS.backtest_fallback_record,
        regression_baseline.fallback_record(
            CONFIGURATION_HASH,
            pd.DatetimeIndex(pd.to_datetime(["1994-03-01", "1994-04-01", "1995-03-01"])),
            [],
        ),
    )
    return store


@pytest.fixture
def baselines(tmp_path: Path) -> Path:
    directory = tmp_path / "baselines"
    directory.mkdir()
    return directory


def _current(artifacts: ArtifactStore) -> dict[str, Any]:
    return regression_baseline.assemble_run_summary(artifacts)


def _captured(artifacts: ArtifactStore, name: str = "main") -> dict[str, Any]:
    return regression_baseline.build_baseline(artifacts, name, deterministic=True)


def _perturbed(document: dict[str, Any]) -> dict[str, Any]:
    """A deep copy, so a test that mutates one cannot reach the other."""
    return json.loads(json.dumps(document))


def _workspace(artifacts: ArtifactStore) -> command_line_interface.Workspace:
    """A workspace carrying nothing but the artifact store the baseline reads.

    The baseline commands never touch the registry or the series cache, and
    constructing them would make an offline test reach for files it does not need.
    Only the paired comparison reads the run settings, and its tests supply them.
    """
    return command_line_interface.Workspace(
        registry=None,  # type: ignore[arg-type]
        indicators=(),
        cache=None,  # type: ignore[arg-type]
        artifacts=artifacts,
        settings=None,  # type: ignore[arg-type]
    )


# ------------------------------------------------------------------ assembly


class TestWhatABaselineHolds:
    def test_the_run_block_names_the_one_configuration_that_produced_the_artifacts(
        self, artifacts: ArtifactStore
    ) -> None:
        run = _current(artifacts)["run"]
        assert run == {
            "configuration_hash": CONFIGURATION_HASH,
            "random_seed": 20260908,
            "state_count": 6,
            "state_count_chosen_as_of": "1994-03-01",
            "first_forecast_date": "1994-03-01",
            "last_forecast_date": "1995-03-01",
            "forecast_date_count": 3,
            "refit_count": 2,
            "forecast_dates_using_fallback": 0,
        }

    def test_every_horizon_and_every_indicator_row_is_recorded(
        self, artifacts: ArtifactStore
    ) -> None:
        summary = _current(artifacts)
        assert len(summary["horizons"]) == len(HORIZONS)
        assert len(summary["indicators"]) == len(INDICATORS) * len(HORIZONS)

    def test_rows_come_out_in_one_order_whatever_order_the_artifact_was_written_in(
        self, tmp_path: Path
    ) -> None:
        """Two captures of one run must be byte-identical, which a row order that
        followed the parquet's would not survive."""
        store = ArtifactStore(tmp_path / "shuffled")
        store.write_table(ARTIFACTS.backtest_results, _backtest_results())
        store.write_table(ARTIFACTS.verdicts, _verdicts().iloc[::-1])
        store.write_table(
            ARTIFACTS.evaluation_metrics, _evaluation_metrics().sample(frac=1.0, random_state=3)
        )
        rows = regression_baseline.assemble_run_summary(store)["indicators"]
        assert [(row["indicator"], row["horizon_months"]) for row in rows] == [
            (indicator, horizon) for indicator in sorted(INDICATORS) for horizon in HORIZONS
        ]

    def test_an_undefined_metric_is_written_as_null_rather_than_a_number(
        self, artifacts: ArtifactStore
    ) -> None:
        """``area_under_the_curve`` does not exist for a cell whose outcomes never
        varied. ``NaN`` would make the file something other than JSON."""
        rows = _current(artifacts)["indicators"]
        undefined = [row for row in rows if row["area_under_the_curve"] is None]
        assert len(undefined) == 1
        assert "NaN" not in regression_baseline.as_json_text(_captured(artifacts))

    def test_a_count_stays_an_integer_and_a_rate_stays_a_float(
        self, artifacts: ArtifactStore
    ) -> None:
        row = _current(artifacts)["indicators"][0]
        assert isinstance(row["resolved_forecasts"], int)
        assert isinstance(row["base_rate"], float)

    def test_a_cache_describing_two_runs_is_refused_rather_than_summarised(
        self, artifacts: ArtifactStore
    ) -> None:
        mixed = _backtest_results()
        mixed.loc[0, "configuration_hash"] = "something_else"
        artifacts.write_table(ARTIFACTS.backtest_results, mixed)
        with pytest.raises(regression_baseline.BaselineError, match="more than one run"):
            _current(artifacts)

    def test_a_missing_artifact_names_the_command_that_produces_it(self, tmp_path: Path) -> None:
        empty = ArtifactStore(tmp_path / "empty")
        with pytest.raises(regression_baseline.BaselineError, match="forecast backtest"):
            regression_baseline.assemble_run_summary(empty)

    def test_an_artifact_missing_a_column_a_baseline_records_fails_loudly(
        self, artifacts: ArtifactStore
    ) -> None:
        artifacts.write_table(
            ARTIFACTS.evaluation_metrics, _evaluation_metrics().drop(columns=["reliability"])
        )
        with pytest.raises(regression_baseline.BaselineError, match="reliability"):
            _current(artifacts)

    def test_a_burn_in_choice_from_a_different_run_is_refused(
        self, artifacts: ArtifactStore
    ) -> None:
        """Two artifacts from two runs describe no single run, and picking one is
        exactly the silent fallback this project does not do."""
        artifacts.write_json(
            ARTIFACTS.burn_in_state_count_choice,
            {"state_count": 2, "chosen_as_of": "1971-12-01"},
        )
        with pytest.raises(regression_baseline.BaselineError, match="different runs"):
            _current(artifacts)

    def test_a_burn_in_recommendation_may_differ_from_what_was_used_to_forecast(
        self, artifacts: ArtifactStore
    ) -> None:
        """Research arm A2-quadrant-structure-levels: the burn-in sweep still runs
        and still recommends its own count (2, here), as evidence for the
        regimes-exist gate, while the number actually used to fit is a
        pre-registered constant (6, matching ``_backtest_results``'s
        ``state_count`` column). ``state_count_used_for_forecasting`` is the
        field the consistency check reads; when it agrees with the backtest,
        the sweep's own, different ``state_count`` is no longer treated as a
        contradiction -- it is reported evidence, not the number used."""
        artifacts.write_json(
            ARTIFACTS.burn_in_state_count_choice,
            {
                "state_count": 2,
                "state_count_used_for_forecasting": 6,
                "chosen_as_of": "1971-12-01",
            },
        )
        run = regression_baseline.assemble_run_summary(artifacts)["run"]
        assert run["state_count"] == 6
        assert run["state_count_chosen_as_of"] == "1971-12-01"

    def test_the_fallback_count_is_null_when_no_artifact_records_it(self, tmp_path: Path) -> None:
        """Only ``forecast compare-variants`` writes it, and that is a forty-minute
        one-off. A cache that has never run it says so rather than guessing zero."""
        store = ArtifactStore(tmp_path / "no_variants")
        store.write_table(ARTIFACTS.backtest_results, _backtest_results())
        store.write_table(ARTIFACTS.verdicts, _verdicts())
        store.write_table(ARTIFACTS.evaluation_metrics, _evaluation_metrics())
        assert store is not None
        summary = regression_baseline.assemble_run_summary(store)
        assert summary["run"]["forecast_dates_using_fallback"] is None
        assert summary["run"]["state_count_chosen_as_of"] is None


# ----------------------------------------------- acceptance criterion 1 and 2


class TestCaptureIsDeterministic:
    def test_two_deterministic_captures_of_one_run_are_byte_identical(
        self, artifacts: ArtifactStore, baselines: Path
    ) -> None:
        """Acceptance criterion 1, checked with sha256 the way the spec asks."""
        digests = []
        for _ in range(2):
            regression_baseline.write_baseline(
                _captured(artifacts, "test"), "test", baselines, force=True
            )
            digests.append(
                hashlib.sha256(
                    (baselines / "test.json").read_bytes(),
                ).hexdigest()
            )
        assert digests[0] == digests[1]

    def test_the_deterministic_flag_omits_the_capture_block_rather_than_blanking_it(
        self, artifacts: ArtifactStore
    ) -> None:
        assert "capture" not in _captured(artifacts)
        stamped = regression_baseline.build_baseline(artifacts, "test", deterministic=False)
        assert set(stamped["capture"]) == {"captured_at", "git_commit"}

    def test_capturing_and_immediately_comparing_finds_nothing_moved(
        self, artifacts: ArtifactStore
    ) -> None:
        """Acceptance criterion 2."""
        comparison = regression_baseline.compare(_captured(artifacts), _current(artifacts))
        assert comparison.in_band(regression_baseline.MOVED) == []
        assert comparison.structural == ()
        assert comparison.exit_code == 0

    def test_the_capture_time_and_the_commit_are_never_compared(
        self, artifacts: ArtifactStore
    ) -> None:
        stamped = regression_baseline.build_baseline(artifacts, "test", deterministic=False)
        stamped["capture"]["git_commit"] = "a different commit entirely"
        stamped["package_version"] = "99.0.0"
        stamped["name"] = "renamed"
        assert regression_baseline.compare(stamped, _current(artifacts)).exit_code == 0

    def test_a_baseline_is_never_overwritten_without_being_asked_twice(
        self, artifacts: ArtifactStore, baselines: Path
    ) -> None:
        regression_baseline.write_baseline(_captured(artifacts), "main", baselines)
        with pytest.raises(regression_baseline.BaselineError, match="--force"):
            regression_baseline.write_baseline(_captured(artifacts), "main", baselines)


# --------------------------------------- acceptance criteria 3, 4, 5 and more


class TestTheToleranceBands:
    def test_a_drift_of_one_part_in_ten_trillion_is_numerical_and_not_a_regression(
        self, artifacts: ArtifactStore
    ) -> None:
        """Acceptance criterion 3. A fitted model reproduces byte-identically
        within one environment and moves at about the thirteenth decimal across a
        numpy or BLAS change. Calling that a regression would make the check
        useless in the other direction."""
        baseline = _perturbed(_captured(artifacts))
        baseline["indicators"][0]["brier_skill_score"] += 1e-13

        comparison = regression_baseline.compare(baseline, _current(artifacts))
        drifted = [item for item in comparison.fields if item.band == regression_baseline.NUMERICAL]
        assert [item.field for item in drifted] == ["brier_skill_score"]
        assert comparison.in_band(regression_baseline.MOVED) == []
        assert comparison.exit_code == 0

    def test_a_move_of_one_part_in_a_million_is_reported(self, artifacts: ArtifactStore) -> None:
        """Acceptance criterion 4. The failure ADR 0008 records is a comparison
        that passes on a difference it exists to catch."""
        baseline = _perturbed(_captured(artifacts))
        baseline["indicators"][0]["brier_skill_score"] += 1e-6

        comparison = regression_baseline.compare(baseline, _current(artifacts))
        moved = comparison.in_band(regression_baseline.MOVED)
        assert [item.field for item in moved] == ["brier_skill_score"]
        assert moved[0].difference == pytest.approx(-1e-6, rel=1e-6)
        assert comparison.exit_code == 1

    def test_the_boundary_sits_where_the_constant_says_it_does(
        self, artifacts: ArtifactStore
    ) -> None:
        """The band is decided by one constant, and a difference exactly on it is
        drift while anything above it is a move."""
        tolerance = regression_baseline.NUMERICAL_DRIFT_TOLERANCE
        assert regression_baseline.classify(0.0, tolerance, exact=False) == (
            regression_baseline.NUMERICAL,
            tolerance,
        )
        band, _ = regression_baseline.classify(0.0, tolerance * 10, exact=False)
        assert band == regression_baseline.MOVED

    def test_an_exactly_equal_number_is_identical_rather_than_merely_close(
        self, artifacts: ArtifactStore
    ) -> None:
        band, difference = regression_baseline.classify(0.25, 0.25, exact=False)
        assert (band, difference) == (regression_baseline.IDENTICAL, 0.0)

    def test_a_changed_verdict_is_a_move_at_any_size(self, artifacts: ArtifactStore) -> None:
        """Acceptance criterion 5. A verdict has no fourth decimal to be within."""
        baseline = _perturbed(_captured(artifacts))
        baseline["horizons"][0]["verdict"] = "SHIP MODEL"

        comparison = regression_baseline.compare(baseline, _current(artifacts))
        moved = comparison.in_band(regression_baseline.MOVED)
        assert [(item.field, item.row) for item in moved] == [("verdict", "12")]
        assert comparison.exit_code == 1

    def test_a_changed_failing_gate_list_is_a_move(self, artifacts: ArtifactStore) -> None:
        baseline = _perturbed(_captured(artifacts))
        baseline["horizons"][1]["failing_gates"] = "none"
        assert regression_baseline.compare(baseline, _current(artifacts)).exit_code == 1

    def test_no_field_in_the_run_block_is_ever_banded_as_drift(
        self, artifacts: ArtifactStore
    ) -> None:
        """A seed or a forecast-date count differing at the thirteenth decimal is
        not a thing that happens; a different run is a different run."""
        baseline = _perturbed(_captured(artifacts))
        baseline["run"]["forecast_date_count"] = 3 + 1e-13

        comparison = regression_baseline.compare(baseline, _current(artifacts))
        assert [item.band for item in comparison.fields if item.section == "run"].count(
            regression_baseline.NUMERICAL
        ) == 0
        assert comparison.exit_code == 1

    def test_a_metric_that_was_undefined_and_now_is_not_is_a_move(
        self, artifacts: ArtifactStore
    ) -> None:
        """``null`` against a number has no magnitude, which is not the same as
        having no difference."""
        baseline = _perturbed(_captured(artifacts))
        baseline["indicators"][-1]["area_under_the_curve"] = 0.83

        comparison = regression_baseline.compare(baseline, _current(artifacts))
        moved = comparison.in_band(regression_baseline.MOVED)
        assert [item.field for item in moved] == ["area_under_the_curve"]
        assert moved[0].current is None
        assert comparison.exit_code == 1

    def test_the_band_filter_changes_what_is_printed_and_not_what_is_classified(
        self, artifacts: ArtifactStore
    ) -> None:
        """`--tolerance-band` must not become the widenable tolerance the module
        exists to avoid."""
        baseline = _perturbed(_captured(artifacts))
        baseline["indicators"][0]["brier_skill_score"] += 1e-6

        comparison = regression_baseline.compare(baseline, _current(artifacts))
        for bands in ([regression_baseline.IDENTICAL], [regression_baseline.NUMERICAL]):
            assert comparison.describe(bands) is not None
            assert comparison.exit_code == 1
        assert "brier_skill_score" in comparison.describe([regression_baseline.MOVED])


# ------------------------------------------- acceptance criteria 6 and 7


class TestWhatCannotBeCompared:
    def test_an_indicator_row_removed_from_the_baseline_is_reported_not_skipped(
        self, artifacts: ArtifactStore
    ) -> None:
        """Acceptance criterion 6. A comparison that quietly drops the rows it
        cannot align is the same failure as a tolerance that absorbs everything,
        and it is the one that looks most like a pass."""
        baseline = _perturbed(_captured(artifacts))
        dropped = baseline["indicators"].pop(3)

        comparison = regression_baseline.compare(baseline, _current(artifacts))
        assert [entry.band for entry in comparison.structural] == [regression_baseline.REMOVED]
        assert dropped["indicator"] in comparison.structural[0].row
        assert comparison.exit_code == 2

    def test_a_row_the_run_no_longer_produces_is_reported_too(
        self, artifacts: ArtifactStore
    ) -> None:
        current = _perturbed(_current(artifacts))
        current["horizons"].pop(2)

        comparison = regression_baseline.compare(_captured(artifacts), current)
        assert [entry.band for entry in comparison.structural] == [regression_baseline.ADDED]
        assert comparison.exit_code == 2

    def test_a_structural_mismatch_outranks_a_moved_number(self, artifacts: ArtifactStore) -> None:
        """Two sides describing different rows have produced no comparison at all,
        and a skill score compared across different indicator sets is not one."""
        baseline = _perturbed(_captured(artifacts))
        baseline["indicators"].pop(0)
        baseline["horizons"][0]["verdict"] = "SHIP MODEL"

        comparison = regression_baseline.compare(baseline, _current(artifacts))
        assert comparison.in_band(regression_baseline.MOVED)
        assert comparison.exit_code == 2

    def test_a_field_the_baseline_predates_is_structural_rather_than_ignored(
        self, artifacts: ArtifactStore
    ) -> None:
        baseline = _perturbed(_captured(artifacts))
        del baseline["indicators"][0]["reliability"]

        comparison = regression_baseline.compare(baseline, _current(artifacts))
        assert comparison.structural[0].band == regression_baseline.REMOVED
        assert "reliability" in comparison.structural[0].detail
        assert comparison.exit_code == 2

    def test_two_rows_with_one_key_are_refused_rather_than_arbitrated(
        self, artifacts: ArtifactStore
    ) -> None:
        baseline = _perturbed(_captured(artifacts))
        baseline["indicators"].append(_perturbed(baseline["indicators"][0]))
        with pytest.raises(regression_baseline.BaselineError, match="two rows keyed"):
            regression_baseline.compare(baseline, _current(artifacts))

    def test_a_baseline_that_does_not_exist_says_how_to_make_one(self, baselines: Path) -> None:
        """Acceptance criterion 7."""
        with pytest.raises(
            regression_baseline.BaselineError, match=r"forecast baseline capture --name main"
        ):
            regression_baseline.read_baseline("main", baselines)

    def test_a_hand_edited_baseline_says_so_rather_than_raising_a_traceback(
        self, baselines: Path
    ) -> None:
        (baselines / "broken.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(regression_baseline.BaselineError, match="hand edit"):
            regression_baseline.read_baseline("broken", baselines)


# ------------------------------------------------- acceptance criterion 8


class TestOneAssemblyFunction:
    def test_check_gates_writes_a_run_summary_equal_to_what_capture_would_produce(
        self, artifacts: ArtifactStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Acceptance criterion 8. The five stages are stubbed out because what is
        being pinned is that the last step of `check-gates` writes the same
        structure a baseline holds, not that the pipeline runs."""
        passing = command_line_interface.pipeline_gates.GateReport(number=1, name="stub", checks=())
        for stage in ("audit_data", "fit_regimes", "forecast_now", "run_backtest", "evaluate"):
            monkeypatch.setattr(
                command_line_interface,
                stage,
                lambda workspace, today, report=passing: (0, report),
            )

        assert command_line_interface.check_gates(_workspace(artifacts), date(2026, 9, 12)) == 0

        written = artifacts.read_json(ARTIFACTS.run_summary)
        captured = _captured(artifacts)
        assert written["indicators"] == captured["indicators"]
        assert written["horizons"] == captured["horizons"]
        assert written["run"] == captured["run"]

    def test_a_run_summary_compares_against_a_baseline_with_nothing_moved(
        self, artifacts: ArtifactStore
    ) -> None:
        """The point of sharing the assembly: a fresh run and a committed baseline
        cannot disagree about their own format."""
        summary = regression_baseline.assemble_run_summary(artifacts)
        assert regression_baseline.compare(_captured(artifacts), summary).exit_code == 0

    def test_a_failed_gate_writes_no_run_summary(
        self, artifacts: ArtifactStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A run that stopped at gate four has no evaluation to summarise, and a
        summary assembled from a half-finished cache would describe a run that
        never happened."""
        failing = command_line_interface.pipeline_gates.GateReport(number=1, name="stub", checks=())
        monkeypatch.setattr(
            command_line_interface,
            "audit_data",
            lambda workspace, today: (1, failing),
        )
        assert command_line_interface.check_gates(_workspace(artifacts), date(2026, 9, 12)) == 1
        assert not artifacts.has(ARTIFACTS.run_summary)


# ---------------------------------------------------- the command line surface


class TestTheCommandLineSurface:
    def test_baseline_carries_three_subcommands_of_its_own(self) -> None:
        parser = command_line_interface.build_parser()
        for action in ("capture", "compare", "list"):
            arguments = parser.parse_args(
                ["baseline", action, *(["--name", "main"] if action == "capture" else [])]
            )
            assert arguments.command == "baseline"
            assert arguments.baseline_command == action

    def test_compare_defaults_to_the_baseline_named_main(self) -> None:
        arguments = command_line_interface.build_parser().parse_args(["baseline", "compare"])
        assert arguments.against == "main"
        assert arguments.output_format == "table"
        assert arguments.tolerance_bands is None

    def test_capture_will_not_run_without_a_name(self) -> None:
        with pytest.raises(SystemExit):
            command_line_interface.build_parser().parse_args(["baseline", "capture"])

    def test_the_band_flag_only_ever_selects_what_is_printed(self) -> None:
        assert command_line_interface._bands_to_show(None) == [regression_baseline.MOVED]
        assert command_line_interface._bands_to_show(["all"]) == [
            regression_baseline.IDENTICAL,
            regression_baseline.NUMERICAL,
            regression_baseline.MOVED,
        ]
        assert command_line_interface._bands_to_show(["numerical"]) == [
            regression_baseline.NUMERICAL
        ]

    def test_capture_then_compare_exits_zero_through_the_command_line(
        self, artifacts: ArtifactStore, baselines: Path
    ) -> None:
        workspace = _workspace(artifacts)
        assert (
            command_line_interface.baseline_capture(workspace, "main", True, False, baselines) == 0
        )
        assert (
            command_line_interface.baseline_compare(
                workspace, "main", "table", [regression_baseline.MOVED], baselines
            )
            == 0
        )

    def test_comparing_against_a_baseline_that_does_not_exist_exits_two(
        self, artifacts: ArtifactStore, baselines: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Acceptance criterion 7, through the command line rather than the module."""
        code = command_line_interface.baseline_compare(
            _workspace(artifacts), "nothing_here", "table", [regression_baseline.MOVED], baselines
        )
        assert code == 2
        assert "forecast baseline capture" in capsys.readouterr().err

    def test_capturing_over_an_existing_baseline_exits_two(
        self, artifacts: ArtifactStore, baselines: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        workspace = _workspace(artifacts)
        command_line_interface.baseline_capture(workspace, "main", True, False, baselines)
        assert (
            command_line_interface.baseline_capture(workspace, "main", True, False, baselines) == 2
        )
        assert "--force" in capsys.readouterr().err

    def test_a_moved_number_exits_one_through_the_command_line(
        self, artifacts: ArtifactStore, baselines: Path
    ) -> None:
        workspace = _workspace(artifacts)
        command_line_interface.baseline_capture(workspace, "main", True, False, baselines)
        moved = json.loads((baselines / "main.json").read_text())
        moved["indicators"][0]["brier_skill_score"] += 1e-6
        (baselines / "main.json").write_text(json.dumps(moved), encoding="utf-8")

        assert (
            command_line_interface.baseline_compare(
                workspace, "main", "table", [regression_baseline.MOVED], baselines
            )
            == 1
        )

    def test_the_json_format_carries_the_whole_comparison_for_a_machine(
        self, artifacts: ArtifactStore, baselines: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        workspace = _workspace(artifacts)
        command_line_interface.baseline_capture(workspace, "main", True, False, baselines)
        capsys.readouterr()  # `--format json` must emit JSON and nothing else
        command_line_interface.baseline_compare(
            workspace, "main", "json", [regression_baseline.MOVED], baselines
        )
        emitted = json.loads(capsys.readouterr().out)
        assert emitted["exit_code"] == 0
        assert emitted["numerical_drift_tolerance"] == (
            regression_baseline.NUMERICAL_DRIFT_TOLERANCE
        )
        assert len(emitted["fields"]) == len(
            regression_baseline.compare(_captured(artifacts), _current(artifacts)).fields
        )

    def test_the_listing_gives_every_baseline_its_run_identity(
        self, artifacts: ArtifactStore, baselines: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        workspace = _workspace(artifacts)
        command_line_interface.baseline_capture(workspace, "main", False, False, baselines)
        assert command_line_interface.baseline_list(baselines) == 0
        printed = capsys.readouterr().out
        assert "main" in printed
        assert CONFIGURATION_HASH in printed

    def test_an_empty_baselines_directory_says_how_to_fill_it(
        self, baselines: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert command_line_interface.baseline_list(baselines) == 0
        assert "forecast baseline capture" in capsys.readouterr().out


# ------------------------------------------------ the committed baseline itself


def test_the_committed_main_baseline_is_readable_and_names_its_run() -> None:
    """The one baseline this repository commits. If this fails, every branch
    comparison in flight is comparing against something unreadable."""
    committed = regression_baseline.baseline_path("main")
    if not committed.is_file():  # pragma: no cover - only on a partial checkout
        pytest.skip("baselines/main.json is not present in this checkout")

    document = regression_baseline.read_baseline("main")
    assert document["name"] == "main"
    assert set(document["run"]) == set(regression_baseline.RUN_FIELDS)
    assert len(document["horizons"]) == 3
    assert len(document["indicators"]) == 30
    assert document["run"]["configuration_hash"] == CONFIGURATION_HASH


def test_the_committed_main_baseline_is_in_the_current_format_with_its_forecasts() -> None:
    """A committed baseline in a stale format would refuse every comparison a
    branch makes, and one without its forecasts could not be paired at all."""
    committed = regression_baseline.baseline_path("main")
    if not committed.is_file():  # pragma: no cover - only on a partial checkout
        pytest.skip("baselines/main.json is not present in this checkout")

    document = regression_baseline.read_baseline("main")
    assert document["format_version"] == regression_baseline.FORMAT_VERSION
    forecasts = regression_baseline.read_baseline_forecasts("main")
    assert tuple(forecasts.columns) == regression_baseline.FORECAST_COLUMNS
    assert set(forecasts["configuration_hash"]) == {document["run"]["configuration_hash"]}


# ----------------------------------------------------------- the format version


class TestTheFormatVersion:
    def test_every_baseline_and_every_run_summary_records_the_format_it_was_written_in(
        self, artifacts: ArtifactStore
    ) -> None:
        assert isinstance(regression_baseline.FORMAT_VERSION, int)
        assert _captured(artifacts)["format_version"] == regression_baseline.FORMAT_VERSION
        assert _current(artifacts)["format_version"] == regression_baseline.FORMAT_VERSION

    def test_a_baseline_in_another_format_is_refused_naming_both_versions(
        self, artifacts: ArtifactStore
    ) -> None:
        """A serialization change silently invalidates stored baselines. The
        refusal says which two versions met and what to do about it."""
        baseline = _perturbed(_captured(artifacts))
        baseline["format_version"] = regression_baseline.FORMAT_VERSION + 1

        with pytest.raises(regression_baseline.BaselineError) as refusal:
            regression_baseline.compare(baseline, _current(artifacts), "main")
        message = str(refusal.value)
        assert f"format version {regression_baseline.FORMAT_VERSION + 1}" in message
        assert f"format version {regression_baseline.FORMAT_VERSION}." in message
        assert "Re-capture" in message
        assert "forecast baseline capture --name main --force" in message

    def test_a_baseline_that_predates_versioning_is_refused_too(
        self, artifacts: ArtifactStore
    ) -> None:
        baseline = _perturbed(_captured(artifacts))
        del baseline["format_version"]
        with pytest.raises(regression_baseline.BaselineError, match="predates versioning"):
            regression_baseline.compare(baseline, _current(artifacts), "main")

    def test_a_format_mismatch_exits_two_through_either_comparison(
        self, artifacts: ArtifactStore, baselines: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        workspace = _workspace(artifacts)
        command_line_interface.baseline_capture(workspace, "main", True, False, baselines)
        stale = json.loads((baselines / "main.json").read_text())
        stale["format_version"] = regression_baseline.FORMAT_VERSION + 1
        (baselines / "main.json").write_text(json.dumps(stale), encoding="utf-8")
        capsys.readouterr()

        for paired in (False, True):
            code = command_line_interface.baseline_compare(
                workspace, "main", "table", [regression_baseline.MOVED], baselines, paired=paired
            )
            assert code == 2
            assert "format version" in capsys.readouterr().err


# ------------------------------------------------- categorical moves come first


class TestCategoricalMovesComeFirst:
    def test_a_flipped_verdict_is_listed_above_every_numeric_move_whatever_their_size(
        self, artifacts: ArtifactStore
    ) -> None:
        """The failure a stress test of this harness ranked likeliest: a verdict
        flip shipped in one undifferentiated list with dozens of routine numeric
        deltas, and a reviewer who says "looks fine" to the whole report."""
        baseline = _perturbed(_captured(artifacts))
        for row in baseline["indicators"]:
            row["brier_skill_score"] += 0.25
            row["brier_score"] -= 0.1
        baseline["horizons"][2]["verdict"] = "SHIP MODEL"

        comparison = regression_baseline.compare(baseline, _current(artifacts))
        lines = comparison.describe([regression_baseline.MOVED]).splitlines()
        categorical_heading = lines.index("categorical fields that moved -- read these first:")
        numeric_heading = lines.index("numeric fields, largest difference first:")
        moved_rows = [
            (position, line.split())
            for position, line in enumerate(lines)
            if line.startswith(regression_baseline.MOVED)
        ]
        verdict_rows = [position for position, cells in moved_rows if "verdict" in cells]
        numeric_rows = [position for position, cells in moved_rows if "verdict" not in cells]

        assert len(verdict_rows) == 1
        assert len(numeric_rows) == 2 * len(baseline["indicators"])
        assert categorical_heading < verdict_rows[0] < numeric_heading < min(numeric_rows)
        emitted = comparison.as_dictionary()
        assert emitted["fields"][0]["field"] == "verdict"
        assert emitted["fields"][0]["categorical"] is True
        assert emitted["categorical_moved"] == 1

    def test_a_changed_run_identity_field_leads_the_machine_output_too(
        self, artifacts: ArtifactStore
    ) -> None:
        baseline = _perturbed(_captured(artifacts))
        baseline["run"]["random_seed"] = 1
        baseline["indicators"][0]["brier_skill_score"] += 0.5

        emitted = regression_baseline.compare(baseline, _current(artifacts)).as_dictionary()
        moved = [item for item in emitted["fields"] if item["band"] == regression_baseline.MOVED]
        assert [(item["section"], item["field"], item["categorical"]) for item in moved] == [
            ("run", "random_seed", True),
            ("indicators", "brier_skill_score", False),
        ]
        assert emitted["fields"][0] == moved[0]

    def test_a_report_with_no_categorical_move_has_no_categorical_heading(
        self, artifacts: ArtifactStore
    ) -> None:
        baseline = _perturbed(_captured(artifacts))
        baseline["indicators"][0]["brier_skill_score"] += 1e-6
        report = regression_baseline.compare(baseline, _current(artifacts)).describe()
        assert "read these first" not in report
        assert "numeric fields, largest difference first:" in report


# --------------------------------------------------------- the forecasts file


class TestTheForecastsFile:
    def test_capture_writes_every_forecast_beside_the_baseline_with_the_declared_columns(
        self, artifacts: ArtifactStore, baselines: Path
    ) -> None:
        capture = regression_baseline.capture_baseline(
            artifacts, "main", baselines, deterministic=True
        )
        assert capture.forecasts_path == baselines / "main.forecasts.parquet"
        written = regression_baseline.read_baseline_forecasts("main", baselines)
        assert tuple(written.columns) == regression_baseline.FORECAST_COLUMNS
        assert len(written) == len(_backtest_results()) == capture.forecast_count
        assert [item["name"] for item in regression_baseline.list_baselines(baselines)] == ["main"]

    def test_two_captures_of_one_run_write_byte_identical_forecasts_files(
        self, artifacts: ArtifactStore, baselines: Path
    ) -> None:
        digests = []
        for _ in range(2):
            capture = regression_baseline.capture_baseline(
                artifacts, "test", baselines, deterministic=True, force=True
            )
            digests.append(hashlib.sha256(capture.forecasts_path.read_bytes()).hexdigest())
        assert digests[0] == digests[1]

    def test_a_capture_refused_for_either_file_writes_neither(
        self, artifacts: ArtifactStore, baselines: Path
    ) -> None:
        """A new summary paired with an old forecasts file would describe no run."""
        orphan = baselines / "main.forecasts.parquet"
        orphan.write_bytes(b"left by an earlier capture")
        with pytest.raises(regression_baseline.BaselineError, match="--force"):
            regression_baseline.capture_baseline(artifacts, "main", baselines, deterministic=True)
        assert not (baselines / "main.json").exists()
        assert orphan.read_bytes() == b"left by an earlier capture"


# ----------------------------------------------------- the paired comparison

PAIRED_HORIZONS = (12, 60)
PAIRED_DATES = pd.date_range("1990-01-01", periods=180, freq="MS")
SMALL_RESAMPLES = 200


def _scored_backtest_results(improvement: float = 0.0) -> pd.DataFrame:
    """Forecasts with outcomes worth scoring: two indicators, two horizons, fifteen
    years of monthly dates, and the most recent dates at each horizon unresolved.

    ``improvement`` moves every forecast that fraction of the way toward the
    outcome it forecasts, which is a run genuinely better by an amount the test
    controls. The outcomes are drawn before it is applied, so both runs forecast
    the same history."""
    generator = np.random.default_rng(20260915)
    rows: list[dict[str, Any]] = []
    for indicator in INDICATORS:
        for horizon in PAIRED_HORIZONS:
            truth = generator.uniform(0.1, 0.6, size=len(PAIRED_DATES))
            outcomes = (generator.uniform(size=len(PAIRED_DATES)) < truth).astype(float)
            noisy = np.clip(truth + generator.normal(0.0, 0.1, size=len(PAIRED_DATES)), 0.01, 0.99)
            predicted = noisy + improvement * (outcomes - noisy)
            unresolved_from = len(PAIRED_DATES) - horizon // 6
            for position, forecast_date in enumerate(PAIRED_DATES):
                rows.append(
                    {
                        "indicator": indicator,
                        "forecast_date": forecast_date,
                        "horizon_months": horizon,
                        "predicted_probability": float(predicted[position]),
                        "climatology_probability": 0.35,
                        "realised_outcome": (
                            float(outcomes[position]) if position < unresolved_from else np.nan
                        ),
                        "distance_to_stationary": 0.3,
                        "effective_sample_size": 50.0,
                        "refit_date": pd.Timestamp(year=forecast_date.year, month=1, day=1),
                        "state_count": 6,
                        "configuration_hash": CONFIGURATION_HASH,
                        "seed": 20260908,
                    }
                )
    return pd.DataFrame(rows)


def _scored_store(directory: Path, results: pd.DataFrame) -> ArtifactStore:
    """A cache whose verdicts and metrics were computed from its own forecasts, the
    way `forecast evaluate` computes them, so each side of a paired comparison has
    a real verdict to agree with."""
    rule = verdict_module.load_decision_rule()
    rule["gates"]["skill"]["bootstrap"]["resamples"] = SMALL_RESAMPLES
    horizons = sorted(int(value) for value in results["horizon_months"].unique())
    verdicts = verdict_module.evaluate_all_horizons(
        results, horizons, True, "stubbed", seed=20260908, decision_rule=rule
    )
    store = ArtifactStore(directory)
    store.write_table(ARTIFACTS.backtest_results, results)
    store.write_table(ARTIFACTS.verdicts, verdict_module.verdict_table(verdicts))
    store.write_table(
        ARTIFACTS.evaluation_metrics,
        verdict_module.metrics_table(verdict_module.compute_metrics(results)),
    )
    return store


def _paired(
    baseline_store: ArtifactStore, current_store: ArtifactStore
) -> regression_baseline.PairedComparison:
    return regression_baseline.compare_paired(
        regression_baseline.build_baseline(baseline_store, "main", deterministic=True),
        regression_baseline.forecast_frame(baseline_store),
        regression_baseline.assemble_run_summary(current_store),
        regression_baseline.forecast_frame(current_store),
        random_seed=20260908,
        resamples=SMALL_RESAMPLES,
        confidence_levels=(0.90,),
        name="main",
    )


def _recorded_skill(store: ArtifactStore) -> dict[int, float]:
    verdicts = store.read_table(ARTIFACTS.verdicts)
    return {
        int(horizon): float(skill)
        for horizon, skill in zip(
            verdicts["horizon_months"], verdicts["mean_brier_skill_score"], strict=True
        )
    }


class TestThePairedComparison:
    def test_a_run_compared_with_itself_differs_by_exactly_zero_on_a_zero_width_interval(
        self, tmp_path: Path
    ) -> None:
        """The A/A check. It also proves the pairing: had the two sides been
        scored on different resampled dates, the resampled differences would
        scatter around zero and the interval could not be [0.0, 0.0]."""
        store = _scored_store(tmp_path / "run", _scored_backtest_results())
        paired = _paired(store, store)

        assert paired.exit_code == 0
        assert paired.same_forecasts
        for horizon in paired.horizons:
            assert horizon.result is not None
            assert horizon.result.interval is not None
            assert horizon.result.difference == 0.0
            assert horizon.result.interval.lower_bound == 0.0
            assert horizon.result.interval.upper_bound == 0.0
        assert [item.difference for item in paired.indicators] == [0.0] * len(paired.indicators)

    def test_each_sides_mean_skill_is_exactly_what_its_own_verdict_reports(
        self, tmp_path: Path
    ) -> None:
        """The statistic is the verdict's, reused rather than restated. Exact
        equality, not approximate: the same code on the same numbers."""
        baseline_store = _scored_store(tmp_path / "baseline", _scored_backtest_results())
        current_store = _scored_store(
            tmp_path / "current", _scored_backtest_results(improvement=0.2)
        )
        paired = _paired(baseline_store, current_store)

        baseline_skill = _recorded_skill(baseline_store)
        current_skill = _recorded_skill(current_store)
        for horizon in paired.horizons:
            assert horizon.result is not None
            assert horizon.result.baseline_mean_skill == baseline_skill[horizon.horizon_months]
            assert horizon.result.current_mean_skill == current_skill[horizon.horizon_months]
            assert horizon.result.difference == (
                current_skill[horizon.horizon_months] - baseline_skill[horizon.horizon_months]
            )

    def test_a_genuinely_better_run_gets_an_interval_that_excludes_zero(
        self, tmp_path: Path
    ) -> None:
        baseline_store = _scored_store(tmp_path / "baseline", _scored_backtest_results())
        current_store = _scored_store(
            tmp_path / "current", _scored_backtest_results(improvement=0.2)
        )
        for horizon in _paired(baseline_store, current_store).horizons:
            assert horizon.result is not None
            assert horizon.result.interval is not None
            assert horizon.result.difference > 0.0
            assert horizon.result.interval.lower_bound > 0.0

    def test_the_per_indicator_scores_are_the_metric_tables_own(self, tmp_path: Path) -> None:
        baseline_store = _scored_store(tmp_path / "baseline", _scored_backtest_results())
        current_store = _scored_store(
            tmp_path / "current", _scored_backtest_results(improvement=0.2)
        )
        paired = _paired(baseline_store, current_store)

        def metric_table(store: ArtifactStore) -> dict[tuple[str, int], float]:
            table = store.read_table(ARTIFACTS.evaluation_metrics)
            return {
                (str(row["indicator"]), int(row["horizon_months"])): float(row["brier_skill_score"])
                for row in table.to_dict("records")
            }

        baseline_metrics = metric_table(baseline_store)
        current_metrics = metric_table(current_store)
        assert len(paired.indicators) == len(INDICATORS) * len(PAIRED_HORIZONS)
        for item in paired.indicators:
            key = (item.indicator, item.horizon_months)
            assert item.baseline_brier_skill_score == baseline_metrics[key]
            assert item.current_brier_skill_score == current_metrics[key]

    def test_runs_with_different_start_dates_are_compared_on_the_intersection_and_say_so(
        self, tmp_path: Path
    ) -> None:
        full = _scored_backtest_results()
        later = full[full["forecast_date"] >= PAIRED_DATES[24]].reset_index(drop=True)
        baseline_store = _scored_store(tmp_path / "baseline", full)
        current_store = _scored_store(tmp_path / "current", later)
        paired = _paired(baseline_store, current_store)

        resolved = full.dropna(subset=["realised_outcome"])
        earlier = int((resolved["forecast_date"] < PAIRED_DATES[24]).sum())
        assert paired.rows_only_in_baseline == earlier
        assert paired.rows_only_in_this_run == 0
        assert paired.rows_in_both == len(resolved) - earlier
        assert paired.only_in_baseline_forecast_dates == (
            "1990-01-01",
            PAIRED_DATES[23].date().isoformat(),
        )
        report = paired.describe()
        assert "the intersection" in report
        assert f"{earlier} only in the baseline" in report
        assert paired.exit_code == 0
        # This run's resolved set *is* the intersection, so it still equals its verdict.
        current_skill = _recorded_skill(current_store)
        for horizon in paired.horizons:
            assert horizon.result is not None
            assert horizon.result.current_mean_skill == current_skill[horizon.horizon_months]

    def test_a_forecast_only_this_run_resolved_is_counted_rather_than_dropped(
        self, tmp_path: Path
    ) -> None:
        full = _scored_backtest_results()
        later = full[full["forecast_date"] >= PAIRED_DATES[24]].reset_index(drop=True)
        paired = _paired(
            _scored_store(tmp_path / "baseline", later), _scored_store(tmp_path / "current", full)
        )
        assert paired.rows_only_in_baseline == 0
        assert paired.rows_only_in_this_run > 0
        assert paired.only_in_this_run_forecast_dates is not None
        assert f"{paired.rows_only_in_this_run} only in this run" in paired.describe()

    def test_a_horizon_the_runs_do_not_share_cannot_be_measured_and_exits_two(
        self, tmp_path: Path
    ) -> None:
        full = _scored_backtest_results()
        one_year_only = full[full["horizon_months"] == 12].reset_index(drop=True)
        paired = _paired(
            _scored_store(tmp_path / "baseline", full),
            _scored_store(tmp_path / "current", one_year_only),
        )
        unshared = [item for item in paired.horizons if item.horizon_months == 60]
        assert len(unshared) == 1
        assert unshared[0].result is None
        assert unshared[0].rows_in_both == 0
        assert paired.exit_code == 2
        assert "nothing can be paired" in paired.describe()

    def test_forecasts_from_another_run_than_the_summary_beside_them_are_refused(
        self, tmp_path: Path
    ) -> None:
        store = _scored_store(tmp_path / "run", _scored_backtest_results())
        foreign = regression_baseline.forecast_frame(store).assign(
            configuration_hash="9f95b12dba40d138"
        )
        with pytest.raises(regression_baseline.BaselineError, match="do not describe the same"):
            regression_baseline.compare_paired(
                regression_baseline.build_baseline(store, "main", deterministic=True),
                foreign,
                regression_baseline.assemble_run_summary(store),
                regression_baseline.forecast_frame(store),
                random_seed=20260908,
                resamples=SMALL_RESAMPLES,
                confidence_levels=(0.90,),
            )

    def test_a_verdict_that_no_longer_matches_its_forecasts_is_caught(self, tmp_path: Path) -> None:
        """When both runs cover the same forecasts each side's mean must be its
        own verdict's. A cache whose verdicts predate its backtest fails that."""
        store = _scored_store(tmp_path / "run", _scored_backtest_results())
        stale = store.read_table(ARTIFACTS.verdicts)
        stale.loc[0, "mean_brier_skill_score"] += 1e-6
        store.write_table(ARTIFACTS.verdicts, stale)
        with pytest.raises(regression_baseline.BaselineError, match="own verdict recorded"):
            _paired(store, store)

    def test_the_run_settings_bootstrap_is_the_one_the_pre_registration_fixed(self) -> None:
        """The verdict reads its resample count and confidence level from the
        pre-registration; the paired comparison reads them from the run settings.
        If the two ever disagree, the paired interval stops being the verdict's
        interval applied to a difference."""
        skill = verdict_module.load_decision_rule()["gates"]["skill"]
        assert DEFAULT_RUN_SETTINGS.bootstrap_resamples == skill["bootstrap"]["resamples"]
        assert DEFAULT_RUN_SETTINGS.bootstrap_confidence_level == skill["confidence_level"]
        assert DEFAULT_RUN_SETTINGS.random_seed == skill["bootstrap"]["seed"]


class TestThePairedCommandLine:
    def test_paired_json_records_the_seed_and_resample_count_the_run_settings_gave(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        store = _scored_store(tmp_path / "run", _scored_backtest_results())
        baselines = tmp_path / "baselines"
        settings = dataclasses.replace(DEFAULT_RUN_SETTINGS, bootstrap_resamples=150, random_seed=7)
        workspace = dataclasses.replace(_workspace(store), settings=settings)
        assert (
            command_line_interface.baseline_capture(workspace, "main", True, False, baselines) == 0
        )
        capsys.readouterr()

        code = command_line_interface.baseline_compare(
            workspace, "main", "json", [regression_baseline.MOVED], baselines, paired=True
        )
        emitted = json.loads(capsys.readouterr().out)
        assert code == 0 == emitted["exit_code"]
        assert emitted["bootstrap"]["resamples"] == 150
        assert emitted["bootstrap"]["random_seed"] == 7
        assert emitted["bootstrap"]["confidence_levels"] == [settings.bootstrap_confidence_level]
        for row in emitted["horizons"]:
            assert [item["confidence_level"] for item in row["intervals"]] == [
                settings.bootstrap_confidence_level
            ]
        assert emitted["keys"]["same_forecasts"] is True
        assert emitted["keys"]["rows_only_in_baseline"] == 0
        assert [row["horizon_months"] for row in emitted["horizons"]] == list(PAIRED_HORIZONS)
        assert [row["difference"] for row in emitted["horizons"]] == [0.0, 0.0]
        assert len(emitted["indicators"]) == len(INDICATORS) * len(PAIRED_HORIZONS)

    def test_the_paired_table_states_the_key_arithmetic(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        store = _scored_store(tmp_path / "run", _scored_backtest_results())
        baselines = tmp_path / "baselines"
        workspace = dataclasses.replace(_workspace(store), settings=DEFAULT_RUN_SETTINGS)
        regression_baseline.capture_baseline(store, "main", baselines, deterministic=True)
        workspace = dataclasses.replace(
            workspace,
            settings=dataclasses.replace(DEFAULT_RUN_SETTINGS, bootstrap_resamples=SMALL_RESAMPLES),
        )

        code = command_line_interface.baseline_compare(
            workspace, "main", "table", [regression_baseline.MOVED], baselines, paired=True
        )
        printed = capsys.readouterr().out
        assert code == 0
        assert "0 only in the baseline, 0 only in this run" in printed
        assert "exactly what its own verdict reports" in printed

    def test_a_baseline_without_its_forecasts_file_says_how_to_write_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        store = _scored_store(tmp_path / "run", _scored_backtest_results())
        baselines = tmp_path / "baselines"
        workspace = dataclasses.replace(_workspace(store), settings=DEFAULT_RUN_SETTINGS)
        capture = regression_baseline.capture_baseline(store, "main", baselines, deterministic=True)
        capture.forecasts_path.unlink()

        code = command_line_interface.baseline_compare(
            workspace, "main", "table", [regression_baseline.MOVED], baselines, paired=True
        )
        assert code == 2
        assert "forecast baseline capture --name main --force" in capsys.readouterr().err

    def test_paired_is_a_flag_on_compare_and_refuses_a_band_filter(self) -> None:
        parser = command_line_interface.build_parser()
        assert parser.parse_args(["baseline", "compare"]).paired is False
        assert parser.parse_args(["baseline", "compare", "--paired"]).paired is True
        with pytest.raises(SystemExit) as refusal:
            command_line_interface.main(
                ["baseline", "compare", "--paired", "--tolerance-band", "all"]
            )
        assert refusal.value.code == 2


FAMILY_WISE_LEVEL = 1 - 0.10 / 6
"""A Bonferroni family-wise level for six arms at ten percent: the second level the
experiments this harness scores are judged at."""


def _paired_at(
    baseline_store: ArtifactStore, current_store: ArtifactStore, levels: tuple[float, ...]
) -> regression_baseline.PairedComparison:
    return regression_baseline.compare_paired(
        regression_baseline.build_baseline(baseline_store, "main", deterministic=True),
        regression_baseline.forecast_frame(baseline_store),
        regression_baseline.assemble_run_summary(current_store),
        regression_baseline.forecast_frame(current_store),
        random_seed=20260908,
        resamples=SMALL_RESAMPLES,
        confidence_levels=levels,
        name="main",
    )


class TestSeveralConfidenceLevels:
    def test_a_higher_level_gives_an_interval_containing_the_lower_ones(
        self, tmp_path: Path
    ) -> None:
        """Two percentiles of one set of resampled estimates must nest. If they do
        not, the percentiles are being taken wrongly or from different resamples."""
        baseline_store = _scored_store(tmp_path / "baseline", _scored_backtest_results())
        current_store = _scored_store(
            tmp_path / "current", _scored_backtest_results(improvement=0.2)
        )
        paired = _paired_at(baseline_store, current_store, (FAMILY_WISE_LEVEL, 0.90))

        assert paired.confidence_levels == (0.90, FAMILY_WISE_LEVEL)
        for horizon in paired.horizons:
            assert horizon.result is not None
            nominal, family_wise = horizon.result.intervals
            assert (nominal.confidence_level, family_wise.confidence_level) == (
                0.90,
                FAMILY_WISE_LEVEL,
            )
            assert family_wise.lower_bound <= nominal.lower_bound
            assert family_wise.upper_bound >= nominal.upper_bound
            assert family_wise.resamples == nominal.resamples

    def test_every_level_is_read_off_the_resamples_a_single_level_would_draw(
        self, tmp_path: Path
    ) -> None:
        baseline_store = _scored_store(tmp_path / "baseline", _scored_backtest_results())
        current_store = _scored_store(
            tmp_path / "current", _scored_backtest_results(improvement=0.2)
        )
        alone = _paired_at(baseline_store, current_store, (0.90,))
        together = _paired_at(baseline_store, current_store, (0.90, FAMILY_WISE_LEVEL))
        for one, both in zip(alone.horizons, together.horizons, strict=True):
            assert one.result is not None
            assert both.result is not None
            assert one.result.intervals[0] == both.result.intervals[0]

    def test_each_level_is_labelled_exactly_in_the_table_and_the_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A reader must never mistake a 98.33% interval for a 90% one."""
        store = _scored_store(tmp_path / "run", _scored_backtest_results())
        baselines = tmp_path / "baselines"
        regression_baseline.capture_baseline(store, "main", baselines, deterministic=True)
        workspace = dataclasses.replace(
            _workspace(store),
            settings=dataclasses.replace(DEFAULT_RUN_SETTINGS, bootstrap_resamples=SMALL_RESAMPLES),
        )
        levels = [0.90, FAMILY_WISE_LEVEL]

        for output_format in ("table", "json"):
            code = command_line_interface.baseline_compare(
                workspace,
                "main",
                output_format,
                [regression_baseline.MOVED],
                baselines,
                paired=True,
                confidence_levels=levels,
            )
            assert code == 0
            printed = capsys.readouterr().out
            if output_format == "table":
                assert "90% interval" in printed
                assert "98.3333% interval" in printed
                continue
            emitted = json.loads(printed)
            assert emitted["bootstrap"]["confidence_levels"] == levels
            for row in emitted["horizons"]:
                assert [item["confidence_level"] for item in row["intervals"]] == levels

    def test_a_confidence_level_outside_zero_and_one_is_refused_with_exit_two(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        parser = command_line_interface.build_parser()
        for refused in ("1", "0", "1.5", "-0.1", "ninety"):
            with pytest.raises(SystemExit) as refusal:
                parser.parse_args(
                    ["baseline", "compare", "--paired", "--confidence-level", refused]
                )
            assert refusal.value.code == 2
            assert "strictly between 0 and 1" in capsys.readouterr().err
        with pytest.raises(regression_baseline.BaselineError, match="strictly between 0 and 1"):
            regression_baseline.compare_paired(
                {"format_version": regression_baseline.FORMAT_VERSION},
                pd.DataFrame(),
                {"format_version": regression_baseline.FORMAT_VERSION},
                pd.DataFrame(),
                random_seed=1,
                resamples=SMALL_RESAMPLES,
                confidence_levels=(1.0,),
            )

    def test_the_level_flag_is_repeatable_and_needs_paired(self) -> None:
        parser = command_line_interface.build_parser()
        repeated = ["--confidence-level", "0.9", "--confidence-level", "0.9833"]
        arguments = parser.parse_args(["baseline", "compare", "--paired", *repeated])
        assert arguments.confidence_levels == [0.9, 0.9833]
        assert parser.parse_args(["baseline", "compare"]).confidence_levels is None
        with pytest.raises(SystemExit) as refusal:
            command_line_interface.main(["baseline", "compare", "--confidence-level", "0.95"])
        assert refusal.value.code == 2
