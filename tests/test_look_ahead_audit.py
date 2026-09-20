"""The look-ahead audit passes what is clean, and can fail.

A leakage check that has never been seen to fail is not evidence. The centre of
this file is a leak injected on purpose -- a model fitted on a panel assembled two
years after its refit date -- and the assertion that the audit exits 1 and names
the forecast date where that leak enters. Around it: the perturbation does
exactly what the specification says and nothing more, the cache being audited is
never written, two audits agree byte for byte, and a check that cannot be made
exits 2 rather than passing.

Everything is synthetic and offline, except one test that reads the live cache
and asserts it comes out byte-identical.
"""

from __future__ import annotations

import dataclasses
import hashlib
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from economic_regime_forecasting import command_line_interface as interface
from economic_regime_forecasting import look_ahead_audit
from economic_regime_forecasting.backtest import schedule as schedule_module
from economic_regime_forecasting.backtest import walk_forward
from economic_regime_forecasting.configuration.registry import (
    BinaryIndicator,
    Composition,
    EconomicSeries,
    EconomicSeriesRegistry,
    IndicatorResolution,
    ModelDimension,
    ResolutionRule,
    Transform,
)
from economic_regime_forecasting.configuration.run_settings import (
    ARTIFACTS,
    DEFAULT_RUN_SETTINGS,
    CacheLayout,
    RunSettings,
)
from economic_regime_forecasting.data.cache import (
    ArtifactStore,
    SeriesCache,
    SeriesRequest,
    SeriesSnapshot,
)

FIRST_FORECAST = date(2000, 1, 1)
LAST_FORECAST = date(2002, 12, 1)
CUTOFF = date(2002, 1, 1)
"""The third refit, and a forecast date: 25 forecast dates and 3 refits audited."""

TODAY = date(2003, 1, 1)
LEAK_MONTHS = 24


# ------------------------------------------------------------------ fixtures


def _series_entry(
    name: str,
    series_id: str,
    dimension: ModelDimension,
    transform: Transform,
    is_revised: bool,
) -> EconomicSeries:
    return EconomicSeries(
        name=name,
        series_id=series_id,
        description=f"synthetic {name}",
        role=dimension.value,
        model_dimension=dimension,
        frequency="monthly",
        units="units",
        transform=transform,
        publication_lag_days=45,
        observation_start=date(1960, 1, 1),
        is_revised=is_revised,
    )


@pytest.fixture(scope="module")
def registry() -> EconomicSeriesRegistry:
    return EconomicSeriesRegistry(
        series=(
            _series_entry(
                "synthetic_output",
                "SYNOUT",
                ModelDimension.GROWTH,
                Transform.YEAR_OVER_YEAR_LOG_CHANGE,
                True,
            ),
            _series_entry(
                "synthetic_prices",
                "SYNCPI",
                ModelDimension.INFLATION,
                Transform.YEAR_OVER_YEAR_LOG_CHANGE,
                True,
            ),
            _series_entry(
                "synthetic_rate", "SYNRATE", ModelDimension.RATES, Transform.LEVEL, False
            ),
        ),
        derived=(),
    )


@pytest.fixture(scope="module")
def indicators() -> tuple[BinaryIndicator, ...]:
    return (
        BinaryIndicator(
            name="rate_above_three_at_horizon",
            question="is the rate above three at the horizon",
            resolution=IndicatorResolution(
                series="synthetic_rate",
                rule=ResolutionRule.LEVEL_ABOVE_THRESHOLD_AT_HORIZON,
                transform=Transform.LEVEL,
                threshold=3.0,
            ),
            composition=Composition.POINT_IN_TIME,
            horizons_in_years=(1,),
        ),
        BinaryIndicator(
            name="rate_below_one_within_horizon",
            question="does the rate fall below one within the horizon",
            resolution=IndicatorResolution(
                series="synthetic_rate",
                rule=ResolutionRule.LEVEL_BELOW_THRESHOLD_WITHIN_HORIZON,
                transform=Transform.LEVEL,
                threshold=1.0,
            ),
            composition=Composition.ANY_TIME_WITHIN_HORIZON,
            horizons_in_years=(1,),
        ),
    )


def _snapshot(
    observations: pd.Series, series_id: str, vintage_date: date | None = None
) -> SeriesSnapshot:
    return SeriesSnapshot(
        request=SeriesRequest(
            source="federal_reserve_economic_data",
            series_id=series_id,
            transform="as_published",
            vintage_date=vintage_date,
        ),
        observations=observations.rename(series_id),
        source_url=f"https://example.invalid/{series_id}",
        units="units",
        retrieved_at=datetime(2026, 9, 15, tzinfo=UTC),
        payload_digest="0" * 64,
    )


@pytest.fixture(scope="module")
def source_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Fifty years of two-regime data, with honest vintages around the audited window.

    This is the cache under audit, standing in for the project's own: every test
    that runs the audit also proves it was never written.
    """
    root = tmp_path_factory.mktemp("project_cache")
    cache = look_ahead_audit.series_cache_at(root)
    index = pd.date_range("1960-01-01", "2009-12-01", freq="MS", name="observation_date")
    generator = np.random.default_rng(20260915)
    transitions = np.array([[0.97, 0.03], [0.05, 0.95]])
    state = 0
    output, prices, rate = [100.0], [100.0], []
    for _ in range(len(index)):
        state = int(generator.choice(2, p=transitions[state]))
        output.append(output[-1] * (1.0 + (0.004 if state == 0 else -0.002)))
        prices.append(prices[-1] * (1.0 + (0.002 if state == 0 else 0.006)))
        rate.append((4.5 if state == 0 else 0.6) + float(generator.normal(0, 0.2)))
    values = {
        "SYNOUT": pd.Series(output[1:], index=index),
        "SYNCPI": pd.Series(prices[1:], index=index),
        "SYNRATE": pd.Series(np.clip(rate, 0.0, None), index=index),
    }
    for series_id, series in values.items():
        cache.write(_snapshot(series, series_id))
    # Vintages for the two revised inputs, through 2005 so the injected leak below
    # can borrow a panel two years past the last refit. A vintage dated the first
    # of a month holds data through two months earlier, as the archive does.
    for series_id in ("SYNOUT", "SYNCPI"):
        series = values[series_id]
        for stamp in pd.date_range("1999-01-01", "2005-12-01", freq="MS"):
            as_published = series[series.index < stamp - pd.DateOffset(months=1)]
            cache.write(_snapshot(as_published, series_id, stamp.date()))
    return root


@pytest.fixture(scope="module")
def settings(tmp_path_factory: pytest.TempPathFactory) -> RunSettings:
    return RunSettings(
        random_seed=7,
        hidden_state_counts_to_search=(1, 2),
        expectation_maximisation_restarts=2,
        expectation_maximisation_max_iterations=60,
        minimum_observations_before_first_fit=120,
        refit_every_n_months=12,
        forecast_horizons_in_months=(12,),
        cache=CacheLayout(tmp_path_factory.mktemp("unused_cache_layout")),
    )


def _configured_schedule(_cache: SeriesCache | None = None) -> schedule_module.ForecastSchedule:
    return schedule_module.build_schedule(FIRST_FORECAST, LAST_FORECAST, 12)


@pytest.fixture(scope="module")
def clean_audit(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    source_root: Path,
    settings: RunSettings,
    tmp_path_factory: pytest.TempPathFactory,
) -> look_ahead_audit.LookAheadAudit:
    return look_ahead_audit.audit_look_ahead(
        registry,
        indicators,
        look_ahead_audit.series_cache_at(source_root),
        settings,
        _configured_schedule,
        tmp_path_factory.mktemp("clean_audit"),
        cutoff=CUTOFF,
    )


def _run_command(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    source_root: Path,
    settings: RunSettings,
    models: Path,
    monkeypatch: pytest.MonkeyPatch,
    cutoff: date | None = CUTOFF,
) -> tuple[int, dict[str, Any]]:
    """`forecast audit-look-ahead` through the command's own function, and its record.

    The one substitution is the schedule: the real one scans the vintage archive
    back to 1971, which a synthetic cache does not hold.
    """
    monkeypatch.setattr(
        interface.Workspace, "backtest_schedule", lambda self, today: _configured_schedule()
    )
    workspace = interface.Workspace(
        registry=registry,
        indicators=indicators,
        cache=look_ahead_audit.series_cache_at(source_root),
        artifacts=ArtifactStore(models),
        settings=settings,
    )
    code = interface.audit_look_ahead(workspace, TODAY, cutoff)
    return code, ArtifactStore(models).read_json(ARTIFACTS.look_ahead_audit)


def _fingerprint(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _request(sidecar: dict[str, object]) -> SeriesRequest:
    recorded = sidecar["request"]
    assert isinstance(recorded, dict)
    vintage = recorded["vintage_date"]
    return SeriesRequest(
        source=recorded["source"],
        series_id=recorded["series_id"],
        transform=recorded["transform"],
        vintage_date=None if vintage is None else date.fromisoformat(vintage),
    )


# -------------------------------------------------------- the check has teeth


def test_a_model_fitted_on_a_panel_from_the_future_is_caught_and_exits_one(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    source_root: Path,
    settings: RunSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Acceptance criterion 2: a real leak, injected, and seen to fail the check.

    Every refit is handed the panel as it stood two years later. The 2000-01 refit
    borrows the panel as of 2002-01-01, the cutoff itself, which holds nothing
    labelled on or after it; so the forecasts it issues must not move. The 2001-01
    refit borrows 2003-01-01, past the cutoff, so the leak enters there and every
    forecast it issues must move. The audit must say exactly that.
    """
    honest_fit = walk_forward.fit_regime_model

    def fit_on_a_panel_two_years_ahead(as_of: date, *arguments: Any, **keywords: Any) -> Any:
        borrowed = (pd.Timestamp(as_of) + pd.DateOffset(months=LEAK_MONTHS)).date()
        return honest_fit(borrowed, *arguments, **keywords)

    monkeypatch.setattr(walk_forward, "fit_regime_model", fit_on_a_panel_two_years_ahead)
    code, record = _run_command(
        registry, indicators, source_root, settings, tmp_path / "models", monkeypatch
    )

    assert code == 1
    assert record["exit_code"] == 1
    assert record["passed"] is False
    moved = record["moved_rows"]
    assert moved[0]["forecast_date"] == "2001-01-01"
    assert "predicted_probability" in moved[0]["fields"]
    assert all(row["forecast_date"] >= "2001-01-01" for row in moved)
    moved_probabilities = {
        (row["indicator"], row["forecast_date"])
        for row in moved
        if "predicted_probability" in row["fields"]
    }
    leaky_dates = pd.date_range("2001-01-01", CUTOFF.isoformat(), freq="MS")
    assert moved_probabilities == {
        (indicator.name, stamp.date().isoformat())
        for indicator in indicators
        for stamp in leaky_dates
    }
    printed = capsys.readouterr().out
    assert "LOOK-AHEAD" in printed
    assert "The earliest is where the leak enters" in printed


def test_a_pipeline_with_no_leak_passes_and_exits_zero(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    source_root: Path,
    settings: RunSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Nothing moves at all, the benchmark included.

    Before ADR 0009 the benchmark at the cutoff counted an outcome resting on the
    value labelled the cutoff month, so this failed on climatology_probability.
    """
    code, record = _run_command(
        registry, indicators, source_root, settings, tmp_path / "models", monkeypatch
    )
    assert code == 0
    assert record["passed"] is True
    assert record["moved_rows"] == []
    printed = capsys.readouterr().out
    assert (
        f"PASS: no forecast issued on or before {CUTOFF.isoformat()} changed when every "
        f"observation unavailable at {CUTOFF.isoformat()} was perturbed"
    ) in printed


def test_without_an_injected_leak_no_model_output_moves(
    clean_audit: look_ahead_audit.LookAheadAudit,
) -> None:
    """The control for the test above: the same pipeline, unpatched.

    Whatever the benchmark does, the model's own outputs -- the probability, the
    regime distribution, the state count and the refit date -- do not move, so
    every move in the injected test is the injected leak's and nothing else's.
    """
    moved_fields = {move.field for row in clean_audit.moved for move in row.moves}
    assert moved_fields <= {"climatology_probability"}


# -------------------------------------------------- what gets run and compared


def test_every_fit_in_both_runs_is_computed_from_scratch(
    clean_audit: look_ahead_audit.LookAheadAudit,
) -> None:
    """A cached fit that saw the future would be read back, not recomputed."""
    for run in (clean_audit.original, clean_audit.perturbed):
        assert run.fits_computed == len(clean_audit.audited_schedule.refit_dates) == 3
        assert run.rows == 25 * 2
    assert clean_audit.rows_compared == 50


def test_the_audited_schedule_is_the_configured_one_truncated_at_the_cutoff(
    clean_audit: look_ahead_audit.LookAheadAudit,
) -> None:
    audited = clean_audit.audited_schedule
    assert audited.forecast_dates[0] == pd.Timestamp(FIRST_FORECAST)
    assert audited.forecast_dates[-1] == pd.Timestamp(CUTOFF)
    assert [stamp.date() for stamp in audited.refit_dates] == [
        date(2000, 1, 1),
        date(2001, 1, 1),
        date(2002, 1, 1),
    ]


def test_the_perturbation_counts_say_what_was_touched(
    clean_audit: look_ahead_audit.LookAheadAudit,
) -> None:
    """47 months of vintages after the cutoff for two series, and the three
    current files from the cutoff on. Vintages dated on or before the cutoff hold
    nothing labelled on or after it, so none of them is touched."""
    summary = clean_audit.perturbation
    assert summary.entries_copied == 3 + 2 * 84
    assert summary.vintages_perturbed_entirely == 2 * 47
    assert summary.snapshots_perturbed_from_the_cutoff == 3


def test_a_realised_outcome_that_differs_is_not_a_look_ahead() -> None:
    frame = _results_frame()
    changed = frame.copy()
    changed.loc[0, "realised_outcome"] = 1.0 - frame.loc[0, "realised_outcome"]
    assert look_ahead_audit.compare_runs(frame, changed) == ()


def test_a_difference_in_the_last_bit_is_a_move() -> None:
    """Exact equality: no tolerance for a leak to hide in."""
    frame = _results_frame()
    changed = frame.copy()
    changed.loc[1, "predicted_probability"] = np.nextafter(frame.loc[1, "predicted_probability"], 1)
    moved = look_ahead_audit.compare_runs(frame, changed)
    assert [(row.forecast_date, [move.field for move in row.moves]) for row in moved] == [
        (date(2000, 2, 1), ["predicted_probability"])
    ]


def test_a_missing_benchmark_on_both_sides_is_identical_and_on_one_side_is_a_move() -> None:
    frame = _results_frame()
    frame.loc[:, "climatology_probability"] = np.nan
    assert look_ahead_audit.compare_runs(frame, frame.copy()) == ()
    changed = frame.copy()
    changed.loc[0, "climatology_probability"] = 0.5
    moved = look_ahead_audit.compare_runs(frame, changed)
    assert moved[0].moves[0].original is None
    assert moved[0].moves[0].perturbed == 0.5


def test_moved_rows_come_out_earliest_forecast_date_first() -> None:
    frame = _results_frame()
    changed = frame.copy()
    changed.loc[:, "regime_distribution"] = "0.1,0.9"
    moved = look_ahead_audit.compare_runs(frame.iloc[::-1], changed)
    assert [row.forecast_date for row in moved] == sorted(row.forecast_date for row in moved)


def test_two_runs_that_hold_different_rows_are_not_compared() -> None:
    frame = _results_frame()
    with pytest.raises(look_ahead_audit.LookAheadAuditError, match="structural mismatch"):
        look_ahead_audit.compare_runs(frame, frame.iloc[1:])


def _results_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "indicator": ["a", "a", "b"],
            "forecast_date": pd.to_datetime(["2000-01-01", "2000-02-01", "2000-01-01"]),
            "horizon_months": [12, 12, 12],
            "predicted_probability": [0.25, 0.3, 0.7],
            "regime_distribution": ["0.5,0.5", "0.4,0.6", "0.5,0.5"],
            "climatology_probability": [0.4, 0.4, 0.6],
            "state_count": [2, 2, 2],
            "refit_date": pd.to_datetime(["2000-01-01"] * 3),
            "realised_outcome": [0.0, 1.0, 1.0],
        }
    )


# ------------------------------------------------------------ the perturbation


def _monthly(start: str, periods: int) -> pd.Series:
    index = pd.date_range(start, periods=periods, freq="MS", name="observation_date")
    return pd.Series(np.linspace(1.0, 50.0, periods), index=index)


def test_a_vintage_published_after_the_cutoff_is_perturbed_whole() -> None:
    """Including months before the cutoff: a later vintage carries revisions."""
    snapshot = _snapshot(_monthly("1999-01-01", 20), "X", vintage_date=date(2000, 10, 1))
    changed, count = look_ahead_audit.perturbed_snapshot(snapshot, date(2000, 6, 1))
    assert count == 20
    np.testing.assert_array_equal(
        changed.observations.to_numpy(), snapshot.observations.to_numpy() * 1.7 + 11.0
    )
    assert changed.request == snapshot.request
    assert changed.payload_digest != snapshot.payload_digest


def test_a_current_file_is_perturbed_from_the_cutoff_on_and_not_before() -> None:
    snapshot = _snapshot(_monthly("1999-01-01", 36), "X")
    cutoff = date(2000, 6, 1)
    changed, count = look_ahead_audit.perturbed_snapshot(snapshot, cutoff)
    before = snapshot.observations.index < pd.Timestamp(cutoff)
    assert count == int((~before).sum()) == 19
    np.testing.assert_array_equal(
        changed.observations[before].to_numpy(), snapshot.observations[before].to_numpy()
    )
    np.testing.assert_array_equal(
        changed.observations[~before].to_numpy(),
        snapshot.observations[~before].to_numpy() * 1.7 + 11.0,
    )


def test_a_vintage_dated_on_the_cutoff_is_left_exactly_as_it_was() -> None:
    """By the boundary invariant it holds nothing labelled on or after its date."""
    snapshot = _snapshot(_monthly("1999-01-01", 16), "X", vintage_date=date(2000, 6, 1))
    changed, count = look_ahead_audit.perturbed_snapshot(snapshot, date(2000, 6, 1))
    assert count == 0
    assert changed is snapshot


def test_a_missing_value_stays_missing() -> None:
    series = _monthly("2000-01-01", 12)
    series.iloc[8] = np.nan
    changed, _ = look_ahead_audit.perturbed_snapshot(_snapshot(series, "X"), date(2000, 6, 1))
    assert np.isnan(changed.observations.iloc[8])
    assert int(changed.observations.isna().sum()) == 1


def test_an_unperturbed_copy_reads_back_identical_to_its_source(
    source_root: Path, tmp_path: Path
) -> None:
    """The copy goes through the cache's own read and write, sidecars included."""
    source = look_ahead_audit.series_cache_at(source_root)
    summary = look_ahead_audit.copy_series_cache(source, tmp_path)
    copy = look_ahead_audit.series_cache_at(tmp_path)
    assert summary.entries_copied == len(source.entries())
    assert summary.observations_perturbed == 0
    assert copy.entries() == source.entries()
    for sidecar in source.entries():
        request = _request(sidecar)
        pd.testing.assert_series_equal(
            copy.read(request).observations, source.read(request).observations, check_exact=True
        )


def test_a_perturbed_copy_changes_what_it_says_and_nothing_else(
    source_root: Path, tmp_path: Path
) -> None:
    source = look_ahead_audit.series_cache_at(source_root)
    look_ahead_audit.copy_series_cache(source, tmp_path, cutoff=CUTOFF)
    copy = look_ahead_audit.series_cache_at(tmp_path)
    for sidecar in source.entries():
        request = _request(sidecar)
        original = source.read(request).observations
        perturbed = copy.read(request).observations
        if request.vintage_date is not None and request.vintage_date > CUTOFF:
            unavailable = np.ones(original.size, dtype=bool)
        else:
            unavailable = np.asarray(original.index >= pd.Timestamp(CUTOFF))
        np.testing.assert_array_equal(
            perturbed.to_numpy()[~unavailable], original.to_numpy()[~unavailable]
        )
        np.testing.assert_array_equal(
            perturbed.to_numpy()[unavailable], original.to_numpy()[unavailable] * 1.7 + 11.0
        )


# --------------------------------------------- the real cache is never touched


def test_the_audited_cache_and_the_project_model_store_are_never_written(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    source_root: Path,
    settings: RunSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance criterion 3, on the cache under audit.

    The project's model store is primed with garbage under the exact names the
    audit's fits and burn-in choice would be cached as. Were any of them read
    back rather than recomputed, the run would crash and exit 2.
    """
    models = tmp_path / "models"
    models.mkdir()
    configuration = f"seed{settings.random_seed}_{settings.configuration_hash()}"
    for name in (
        f"model_{FIRST_FORECAST.isoformat()}_states1_{configuration}.json",
        f"model_{FIRST_FORECAST.isoformat()}_states2_{configuration}.json",
        f"burn_in_state_count_choice_{FIRST_FORECAST.isoformat()}_{configuration}.json",
    ):
        (models / name).write_text("{not a model", encoding="utf-8")
    cache_before = _fingerprint(source_root)
    models_before = _fingerprint(models)

    code, record = _run_command(registry, indicators, source_root, settings, models, monkeypatch)

    assert code in (0, 1)
    assert record["runs"]["original"]["fits_computed_from_scratch"] == 3
    assert _fingerprint(source_root) == cache_before
    models_after = _fingerprint(models)
    assert set(models_after) == set(models_before) | {ARTIFACTS.look_ahead_audit}
    assert {name: models_after[name] for name in models_before} == models_before


@pytest.mark.slow
@pytest.mark.skipif(
    not DEFAULT_RUN_SETTINGS.cache.vintage.exists(),
    reason="no .cache/vintage on this checkout; run `forecast fetch-data` first",
)
def test_perturbing_a_copy_of_the_live_cache_leaves_the_live_cache_byte_identical(
    tmp_path: Path,
) -> None:
    """Acceptance criterion 3, on the project's own cache: read only, every byte."""
    layout = DEFAULT_RUN_SETTINGS.cache
    live = SeriesCache(layout.raw, layout.vintage)
    before = {"raw": _fingerprint(layout.raw), "vintage": _fingerprint(layout.vintage)}

    summary = look_ahead_audit.copy_series_cache(live, tmp_path, cutoff=date(2000, 3, 1))

    assert {"raw": _fingerprint(layout.raw), "vintage": _fingerprint(layout.vintage)} == before
    assert summary.entries_copied == len(live.entries())
    assert summary.vintages_perturbed_entirely > 0
    assert summary.observations_perturbed > 0


# ------------------------------------------------------------- determinism


def test_two_audits_write_byte_identical_records(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    source_root: Path,
    settings: RunSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance criterion 4. The record holds no timestamp, so the whole file."""
    first, _ = _run_command(
        registry, indicators, source_root, settings, tmp_path / "first", monkeypatch
    )
    second, _ = _run_command(
        registry, indicators, source_root, settings, tmp_path / "second", monkeypatch
    )
    assert first == second
    assert (tmp_path / "first" / ARTIFACTS.look_ahead_audit).read_bytes() == (
        tmp_path / "second" / ARTIFACTS.look_ahead_audit
    ).read_bytes()


# ------------------------------------------------- a check that cannot be made


def test_a_cutoff_before_the_first_forecast_exits_two_and_replaces_a_stale_pass(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    source_root: Path,
    settings: RunSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = tmp_path / "models"
    ArtifactStore(models).write_json(ARTIFACTS.look_ahead_audit, {"exit_code": 0, "passed": True})
    code, record = _run_command(
        registry, indicators, source_root, settings, models, monkeypatch, cutoff=date(1999, 6, 1)
    )
    assert code == 2
    assert record["exit_code"] == 2
    assert record["passed"] is False
    assert "no forecast date falls on or before" in record["error"]


def test_an_empty_cache_exits_two(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    settings: RunSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    code, record = _run_command(
        registry, indicators, tmp_path / "empty", settings, tmp_path / "models", monkeypatch
    )
    assert code == 2
    assert "fetch-data" in record["error"]


def test_a_state_count_read_off_the_full_sample_sweep_is_refused(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    source_root: Path,
    settings: RunSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shipped = dataclasses.replace(settings, select_state_count_on_a_burn_in_window=False)
    code, record = _run_command(
        registry, indicators, source_root, shipped, tmp_path / "models", monkeypatch
    )
    assert code == 2
    assert "D2" in record["error"]


def test_the_default_cutoff_is_the_first_refit_six_years_in() -> None:
    schedule = schedule_module.build_schedule(date(1994, 3, 1), date(2026, 9, 1), 12)
    cutoff = look_ahead_audit.default_cutoff(schedule)
    assert cutoff == date(2000, 3, 1)
    audited = look_ahead_audit.truncate_schedule(schedule, cutoff)
    assert len(audited.forecast_dates) == 73
    assert len(audited.refit_dates) == 7


def test_a_schedule_too_short_for_a_default_cutoff_asks_for_one() -> None:
    schedule = schedule_module.build_schedule(date(2000, 1, 1), date(2004, 1, 1), 12)
    with pytest.raises(look_ahead_audit.LookAheadAuditError, match="--cutoff"):
        look_ahead_audit.default_cutoff(schedule)


def test_the_command_takes_an_optional_cutoff() -> None:
    parser = interface.build_parser()
    assert parser.parse_args(["audit-look-ahead"]).cutoff is None
    arguments = parser.parse_args(["audit-look-ahead", "--cutoff", "2000-03-01"])
    assert arguments.command == "audit-look-ahead"
    assert arguments.cutoff == date(2000, 3, 1)


def test_the_output_says_what_the_check_does_not_cover(
    clean_audit: look_ahead_audit.LookAheadAudit,
) -> None:
    """D5 is out of scope by design, and the output must say so."""
    assert "D5" in clean_audit.describe()
    assert "D5" in clean_audit.as_dictionary()["not_covered"]
    assert "realised_outcome is not compared" in clean_audit.describe()


# ------------------------------------------ unavailable means unpublished, not unlabelled


def _current_request(series_id: str) -> SeriesRequest:
    return SeriesRequest(
        source="federal_reserve_economic_data",
        series_id=series_id,
        transform="as_published",
        vintage_date=None,
    )


@pytest.fixture(scope="module")
def month_old_vintage_root(source_root: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The same data, with revised-input vintages holding the month before their date.

    The main fixture's vintages stop two months back, so a rate read one month
    early would be dropped when the three inputs are aligned, and no leak through
    it could reach a forecast. Here it can.
    """
    source = look_ahead_audit.series_cache_at(source_root)
    root = tmp_path_factory.mktemp("month_old_vintages")
    target = look_ahead_audit.series_cache_at(root)
    current = {
        series_id: source.read(_current_request(series_id)).observations
        for series_id in ("SYNOUT", "SYNCPI", "SYNRATE")
    }
    for series_id, series in current.items():
        target.write(_snapshot(series, series_id))
    for series_id in ("SYNOUT", "SYNCPI"):
        series = current[series_id]
        for stamp in pd.date_range("1999-01-01", "2005-12-01", freq="MS"):
            target.write(_snapshot(series[series.index < stamp], series_id, stamp.date()))
    return root


def _every_lag_zero(registry: EconomicSeriesRegistry) -> dict[str, int]:
    """The label rule alone: what the audit perturbed until it became publication-aware."""
    return {entry.series_id: 0 for entry in registry.series}


def test_a_one_month_leak_inside_the_publication_lag_passes_labels_and_fails_publication(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    month_old_vintage_root: Path,
    settings: RunSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gap the label rule left, and the evidence that it is closed.

    The rate series is censored by label instead of by its 45-day publication lag,
    so the forecast issued on the first of a month reads last month's rate, which
    is not published until the middle of this one. Labelled before the cutoff, that
    value is never perturbed under the label rule, and the audit passes: the leak is
    invisible. Under the publication rule it is unpublished at the cutoff, and the
    forecast issued at the cutoff moves -- that forecast and no earlier one, since a
    month before the cutoff the value read had already been published.
    """
    from economic_regime_forecasting.data import vintage

    def censor_by_label_alone(
        observations: pd.Series, publication_lag_days: int, as_of: date
    ) -> pd.Series:
        return observations[observations.index < pd.Timestamp(as_of)]

    monkeypatch.setattr(vintage, "censor_by_publication_lag", censor_by_label_alone)

    def audit(directory: Path) -> look_ahead_audit.LookAheadAudit:
        return look_ahead_audit.audit_look_ahead(
            registry,
            indicators,
            look_ahead_audit.series_cache_at(month_old_vintage_root),
            settings,
            _configured_schedule,
            directory,
            cutoff=CUTOFF,
        )

    with monkeypatch.context() as label_rule:
        label_rule.setattr(look_ahead_audit, "publication_lag_days_by_series", _every_lag_zero)
        under_the_label_rule = audit(tmp_path / "label_rule")
    under_the_publication_rule = audit(tmp_path / "publication_rule")

    assert under_the_label_rule.exit_code == 0
    assert under_the_label_rule.perturbation.publication_lag_days_by_series == {
        "SYNCPI": 0,
        "SYNOUT": 0,
        "SYNRATE": 0,
    }
    assert under_the_publication_rule.exit_code == 1
    moved = under_the_publication_rule.moved
    assert {row.forecast_date for row in moved} == {CUTOFF}
    assert "predicted_probability" in {move.field for row in moved for move in row.moves}


def test_the_same_pipeline_without_the_leak_passes_the_publication_rule(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    month_old_vintage_root: Path,
    settings: RunSettings,
    tmp_path: Path,
) -> None:
    """The control: on the month-old vintages, the honest censoring moves nothing."""
    audit = look_ahead_audit.audit_look_ahead(
        registry,
        indicators,
        look_ahead_audit.series_cache_at(month_old_vintage_root),
        settings,
        _configured_schedule,
        tmp_path,
        cutoff=CUTOFF,
    )
    assert audit.exit_code == 0
    assert audit.perturbation.publication_lag_days_by_series == {
        "SYNCPI": 45,
        "SYNOUT": 45,
        "SYNRATE": 45,
    }


def test_a_value_labelled_before_the_cutoff_but_published_after_it_is_perturbed() -> None:
    """April 1 plus 44 days is May 15, published before a June 1 cutoff. May 1 plus
    44 days is June 14, not yet published, so May is perturbed even though it is
    labelled a month before the cutoff."""
    snapshot = _snapshot(_monthly("2000-01-01", 12), "X")
    changed, count = look_ahead_audit.perturbed_snapshot(snapshot, date(2000, 6, 1), 44)
    moved = snapshot.observations.index[
        changed.observations.to_numpy() != snapshot.observations.to_numpy()
    ]
    assert moved[0] == pd.Timestamp("2000-05-01")
    assert count == len(moved) == 8


def test_recession_status_stays_unavailable_until_the_committee_announced_it() -> None:
    """A constant lag is the wrong shape for this one series, in both directions.

    Every month of 2002 sits after the November 2001 trough but before the July 2003
    call that settled it, so on 10 July 2003 none of them was knowable -- while a
    400-day lag releases the first half of the year. Left on the constant lag the
    audit would leave those six months untouched and so never test them.
    """
    snapshot = _snapshot(_monthly("2002-01-01", 12), "USREC")
    cutoff = date(2003, 7, 10)
    _, by_lag = look_ahead_audit.perturbed_snapshot(snapshot, cutoff, 400)
    changed, by_announcement = look_ahead_audit.perturbed_snapshot(
        snapshot, cutoff, 400, dated_by_announcement=True
    )
    assert by_lag == 6
    assert by_announcement == 12
    june = pd.Timestamp("2002-06-01")
    assert changed.observations[june] != snapshot.observations[june]


def test_announcement_dating_never_releases_a_value_the_constant_lag_withheld() -> None:
    """The rule is one-directional, and this is the test that says so.

    A first version of it let the announcement REPLACE the constant lag. Because the
    announcement settling a month is the most recent turning point at or *before* it,
    and that call is routinely years older than the month, replacing dated values
    before the months they describe: every month of 1999 came out available at a
    March 2000 cutoff, and a panel built in 1994 could read recession codings out to
    2001. The audit caught it at 400 moved rows.

    So withholding is a floor. Announcement dating may add to what the constant lag
    withholds -- that is the post-trough leak D14 records -- and may never subtract.
    """
    snapshot = _snapshot(_monthly("1999-01-01", 12), "USREC")
    cutoff = date(2000, 3, 1)
    _, by_lag = look_ahead_audit.perturbed_snapshot(snapshot, cutoff, 400)
    _, by_announcement = look_ahead_audit.perturbed_snapshot(
        snapshot, cutoff, 400, dated_by_announcement=True
    )
    assert by_lag == 11
    assert by_announcement == 11


def test_the_audit_and_the_pipeline_agree_on_when_recession_status_settled() -> None:
    """Independent implementations, compared rather than trusted.

    ``perturbed_snapshot`` computes publication dates itself, deliberately, so that a
    mistake in the pipeline's rule cannot agree with the check about it. That
    independence is only worth having if the two are also compared, because where
    they disagree the audit either scrambles values the pipeline legitimately used --
    failing the audit for a leak that is not there -- or leaves untouched values it
    should have tested, which is the leak going unseen. Neither side's own tests can
    see that; only holding them side by side can.
    """
    labels = pd.date_range("1998-01-01", "2004-12-01", freq="MS")
    snapshot = _snapshot(_monthly("1998-01-01", len(labels)), "USREC")
    published = walk_forward.publication_dates(labels, 400, dated_by_announcement=True)
    for cutoff in (date(2000, 3, 1), date(2002, 1, 1), date(2003, 7, 10), date(2004, 6, 1)):
        changed, _ = look_ahead_audit.perturbed_snapshot(
            snapshot, cutoff, 400, dated_by_announcement=True
        )
        audit_withheld = changed.observations.to_numpy() != snapshot.observations.to_numpy()
        stamp = pd.Timestamp(cutoff)
        pipeline_withheld = (labels >= stamp) | (published > stamp)
        assert list(audit_withheld) == list(pipeline_withheld), cutoff


def test_a_value_published_exactly_on_the_cutoff_was_available() -> None:
    """May 1 plus 31 days is June 1, the cutoff: available. Plus 32 days is not."""
    snapshot = _snapshot(_monthly("2000-01-01", 12), "X")
    on_the_day, _ = look_ahead_audit.perturbed_snapshot(snapshot, date(2000, 6, 1), 31)
    a_day_late, _ = look_ahead_audit.perturbed_snapshot(snapshot, date(2000, 6, 1), 32)
    may = pd.Timestamp("2000-05-01")
    assert on_the_day.observations[may] == snapshot.observations[may]
    assert a_day_late.observations[may] == snapshot.observations[may] * 1.7 + 11.0


def test_the_publication_rule_contains_the_label_rule() -> None:
    """Whatever the lag, everything the label rule perturbs is still perturbed."""
    snapshot = _snapshot(_monthly("2000-01-01", 24), "X")
    cutoff = date(2000, 6, 1)
    by_label, _ = look_ahead_audit.perturbed_snapshot(snapshot, cutoff)
    original = snapshot.observations.to_numpy()
    labelled_on_or_after = by_label.observations.to_numpy() != original
    for lag in (0, 1, 32, 44, 400):
        by_publication, _ = look_ahead_audit.perturbed_snapshot(snapshot, cutoff, lag)
        published_after = by_publication.observations.to_numpy() != original
        assert bool(published_after[labelled_on_or_after].all())


def test_a_vintage_dated_on_or_before_the_cutoff_is_untouched_whatever_its_lag() -> None:
    """Everything in it had been published by its vintage date."""
    snapshot = _snapshot(_monthly("1999-01-01", 17), "X", vintage_date=date(2000, 6, 1))
    changed, count = look_ahead_audit.perturbed_snapshot(snapshot, date(2000, 6, 1), 400)
    assert count == 0
    assert changed is snapshot


def test_a_derived_spread_is_perturbed_where_either_leg_is_unpublished() -> None:
    """The term spread is computed from its legs, each perturbed by its own lag, so
    it is perturbed exactly where its label plus the larger lag falls after the
    cutoff -- the lag prepare_indicator_history gives it."""
    from economic_regime_forecasting.features import transforms

    cutoff = date(2000, 6, 1)
    long_leg = _monthly("2000-01-01", 12)
    short_leg = _monthly("2000-01-01", 12) * 0.5
    perturbed_long, _ = look_ahead_audit.perturbed_snapshot(_snapshot(long_leg, "L"), cutoff, 10)
    perturbed_short, _ = look_ahead_audit.perturbed_snapshot(_snapshot(short_leg, "S"), cutoff, 40)
    original = transforms.difference(long_leg, short_leg)
    spread = transforms.difference(perturbed_long.observations, perturbed_short.observations)
    labels = original.index
    stamp = pd.Timestamp(cutoff)
    expected = labels[(labels >= stamp) | (labels + pd.Timedelta(days=40) > stamp)]
    assert list(labels[spread.to_numpy() != original.to_numpy()]) == list(expected)


def test_a_cached_series_the_registry_does_not_know_is_refused(tmp_path: Path) -> None:
    """No lag, no answer: guessing one would be a silent fallback."""
    source = look_ahead_audit.series_cache_at(tmp_path / "source")
    source.write(_snapshot(_monthly("2000-01-01", 12), "UNREGISTERED"))
    with pytest.raises(look_ahead_audit.LookAheadAuditError, match="UNREGISTERED"):
        look_ahead_audit.copy_series_cache(
            source,
            tmp_path / "copy",
            cutoff=date(2000, 6, 1),
            publication_lag_days_by_series={"SOMETHING_ELSE": 30},
        )


def test_the_audit_record_names_the_lags_it_perturbed_by(
    clean_audit: look_ahead_audit.LookAheadAudit,
) -> None:
    perturbation = clean_audit.as_dictionary()["perturbation"]
    assert perturbation["publication_lag_days_by_series"] == {
        "SYNCPI": 45,
        "SYNOUT": 45,
        "SYNRATE": 45,
    }
    assert "publication lag" in perturbation["unavailable_means"]
