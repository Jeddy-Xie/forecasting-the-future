"""A run's fallback count comes from the run itself, never from another command.

The defect this pins: the run summary took ``forecast_dates_using_fallback`` from
``variant_comparison.parquet``, the artifact of ``forecast compare-variants``,
looked up by configuration hash. A research arm has a hash of its own and starts
from a copy of main's cache, so it found nothing and reported ``null`` against the
baseline's 0. Every arm's comparison would have led with a categorical MOVED on run
identity, for a reason unrelated to its idea.

``forecast backtest`` now measures the count over its own schedule and records it
beside the results. The summary reads that record and nothing else.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from economic_regime_forecasting import regression_baseline
from economic_regime_forecasting.configuration.run_settings import ARTIFACTS
from economic_regime_forecasting.data.cache import ArtifactStore
from tests.test_regression_baseline import (
    CONFIGURATION_HASH,
    _backtest_results,
    _evaluation_metrics,
    _verdicts,
)

FORECAST_DATES = pd.DatetimeIndex(pd.to_datetime(["1994-03-01", "1994-04-01", "1995-03-01"]))
"""The three forecast dates of the shared backtest fixture."""


def _store(
    tmp_path: Path,
    *,
    record: dict[str, Any] | None = None,
    variant_comparison: pd.DataFrame | None = None,
) -> ArtifactStore:
    store = ArtifactStore(tmp_path / "models")
    store.write_table(ARTIFACTS.backtest_results, _backtest_results())
    store.write_table(ARTIFACTS.verdicts, _verdicts())
    store.write_table(ARTIFACTS.evaluation_metrics, _evaluation_metrics())
    if record is not None:
        store.write_json(ARTIFACTS.backtest_fallback_record, record)
    if variant_comparison is not None:
        store.write_table(ARTIFACTS.variant_comparison, variant_comparison)
    return store


def _variants_saying(count: int) -> pd.DataFrame:
    """compare-variants' artifact, for this very configuration, with its own count."""
    return pd.DataFrame(
        {
            "variant": ["both"] * 3,
            "configuration_hash": [CONFIGURATION_HASH] * 3,
            "forecast_date_count": [3] * 3,
            "forecast_dates_using_fallback": [count] * 3,
            "horizon_months": [12, 60, 120],
        }
    )


def _fallback_count(store: ArtifactStore) -> Any:
    return regression_baseline.assemble_run_summary(store)["run"]["forecast_dates_using_fallback"]


def test_the_summary_reads_the_count_the_run_measured_about_itself(tmp_path: Path) -> None:
    measured = [date(1994, 4, 1)]
    record = regression_baseline.fallback_record(CONFIGURATION_HASH, FORECAST_DATES, measured)
    assert record == {
        "configuration_hash": CONFIGURATION_HASH,
        "first_forecast_date": "1994-03-01",
        "last_forecast_date": "1995-03-01",
        "forecast_date_count": 3,
        "forecast_dates_using_fallback": 1,
        "fallback_dates": ["1994-04-01"],
    }
    assert _fallback_count(_store(tmp_path, record=record)) == 1


def test_another_commands_count_is_never_read_even_for_the_same_configuration(
    tmp_path: Path,
) -> None:
    """compare-variants' artifact carries this configuration and a count of 267.
    With no record from the run itself, the summary says it does not know."""
    store = _store(tmp_path, variant_comparison=_variants_saying(267))
    assert _fallback_count(store) is None


def test_the_runs_own_record_wins_over_another_commands_artifact(tmp_path: Path) -> None:
    record = regression_baseline.fallback_record(CONFIGURATION_HASH, FORECAST_DATES, [])
    store = _store(tmp_path, record=record, variant_comparison=_variants_saying(267))
    assert _fallback_count(store) == 0


def test_a_record_from_a_different_configuration_is_refused(tmp_path: Path) -> None:
    record = regression_baseline.fallback_record("0123456789abcdef", FORECAST_DATES, [])
    with pytest.raises(regression_baseline.BaselineError, match="different runs"):
        _fallback_count(_store(tmp_path, record=record))


def test_a_record_from_a_different_schedule_is_refused(tmp_path: Path) -> None:
    longer = pd.DatetimeIndex(pd.to_datetime(["1994-03-01", "1994-04-01", "1996-03-01"]))
    record = regression_baseline.fallback_record(CONFIGURATION_HASH, longer, [])
    with pytest.raises(regression_baseline.BaselineError, match="different runs"):
        _fallback_count(_store(tmp_path, record=record))


def test_a_missing_record_is_null_and_never_a_guessed_zero(tmp_path: Path) -> None:
    assert _fallback_count(_store(tmp_path)) is None
