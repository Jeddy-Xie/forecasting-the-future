"""The audit measures the data instead of trusting the registry about it.

The point of these tests is the direction of authority: when the registry and the
service disagree, the audit reports the service's answer and the gate fails. A
declared fact that nothing checks goes stale silently.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest

from economic_regime_forecasting.configuration.registry import EconomicSeriesRegistry
from economic_regime_forecasting.data.audit import (
    audit_revisions,
    audit_series,
    audit_table,
    revision_table,
)
from economic_regime_forecasting.data.cache import SeriesCache, SeriesSnapshot
from economic_regime_forecasting.data.federal_reserve_client import build_request


@pytest.fixture
def audited_cache(
    cache: SeriesCache,
    three_dimension_registry: EconomicSeriesRegistry,
    monthly_index: pd.DatetimeIndex,
    snapshot_factory: Callable[..., SeriesSnapshot],
) -> SeriesCache:
    generator = np.random.default_rng(20260908)
    for entry in three_dimension_registry.series:
        values = 100.0 * np.exp(np.cumsum(generator.normal(0.003, 0.01, size=len(monthly_index))))
        cache.write(snapshot_factory(pd.Series(values, index=monthly_index), entry.series_id))
    return cache


def test_the_audit_measures_what_is_there_rather_than_what_was_declared(
    audited_cache: SeriesCache, three_dimension_registry: EconomicSeriesRegistry
) -> None:
    audits = audit_series(three_dimension_registry, audited_cache)
    assert len(audits) == 3
    for item in audits:
        assert item.observed_start == date(1960, 1, 1)
        assert item.observation_count == 600
        assert item.start_matches_registry


def test_a_declared_start_that_disagrees_with_the_data_is_flagged(
    audited_cache: SeriesCache, three_dimension_registry: EconomicSeriesRegistry
) -> None:
    wrong = EconomicSeriesRegistry(
        series=tuple(
            replace(entry, observation_start=date(1900, 1, 1))
            for entry in three_dimension_registry.series
        ),
        derived=(),
    )
    audits = audit_series(wrong, audited_cache)
    assert not any(item.start_matches_registry for item in audits)


def test_the_audit_table_carries_every_column_the_gate_reads(
    audited_cache: SeriesCache, three_dimension_registry: EconomicSeriesRegistry
) -> None:
    table = audit_table(audit_series(three_dimension_registry, audited_cache))
    assert {
        "series",
        "identifier",
        "declared_start",
        "observed_start",
        "observed_end",
        "observations",
        "missing",
        "publication_lag_days",
        "revised",
        "start_matches_registry",
    } <= set(table.columns)


def test_missing_values_are_counted_rather_than_dropped(
    cache: SeriesCache,
    three_dimension_registry: EconomicSeriesRegistry,
    monthly_index: pd.DatetimeIndex,
    snapshot_factory: Callable[..., SeriesSnapshot],
) -> None:
    for entry in three_dimension_registry.series:
        values = pd.Series(np.full(len(monthly_index), 100.0), index=monthly_index)
        values.iloc[[10, 20]] = np.nan
        cache.write(snapshot_factory(values, entry.series_id))
    assert all(
        item.missing_value_count == 2 for item in audit_series(three_dimension_registry, cache)
    )


def test_revisions_are_measured_only_on_series_that_are_revised(
    audited_cache: SeriesCache,
    three_dimension_registry: EconomicSeriesRegistry,
    monthly_index: pd.DatetimeIndex,
    snapshot_factory: Callable[..., SeriesSnapshot],
) -> None:
    """The unrevised rate series has no revision to measure, so it does not appear."""
    as_of = date(2005, 1, 1)
    for entry in three_dimension_registry.series:
        values = 100.0 * np.exp(
            np.cumsum(np.random.default_rng(3).normal(0.003, 0.01, size=len(monthly_index)))
        )
        published = pd.Series(values, index=monthly_index)
        published = published[published.index < pd.Timestamp(as_of) - pd.DateOffset(months=1)]
        audited_cache.write(snapshot_factory(published, entry.series_id, vintage_date=as_of))

    revisions = audit_revisions(three_dimension_registry, audited_cache, [as_of])
    measured = {item.name for item in revisions}
    assert "test_rate" not in measured
    assert measured == {"test_output", "test_prices"}


def test_an_unrevised_vintage_shows_no_revision(
    audited_cache: SeriesCache,
    three_dimension_registry: EconomicSeriesRegistry,
    snapshot_factory: Callable[..., SeriesSnapshot],
) -> None:
    """A vintage identical to today's file must measure as zero revision, which is
    the check that the comparison aligns on dates rather than on positions."""
    as_of = date(2005, 1, 1)
    for entry in three_dimension_registry.series:
        current = audited_cache.read(build_request(entry.series_id)).observations
        published = current[current.index < pd.Timestamp(as_of) - pd.DateOffset(months=1)]
        audited_cache.write(snapshot_factory(published, entry.series_id, vintage_date=as_of))

    revisions = audit_revisions(three_dimension_registry, audited_cache, [as_of])
    assert revisions
    for item in revisions:
        assert item.largest_absolute_revision == pytest.approx(0.0, abs=1e-12)
        assert item.policy == "archival_vintage"


def test_the_revision_table_records_which_policy_produced_each_row(
    audited_cache: SeriesCache,
    three_dimension_registry: EconomicSeriesRegistry,
    monthly_index: pd.DatetimeIndex,
    snapshot_factory: Callable[..., SeriesSnapshot],
) -> None:
    as_of = date(2005, 1, 1)
    for entry in three_dimension_registry.series:
        published = pd.Series(np.full(len(monthly_index), 100.0), index=monthly_index)
        published = published[published.index < pd.Timestamp(as_of) - pd.DateOffset(months=1)]
        audited_cache.write(snapshot_factory(published, entry.series_id, vintage_date=as_of))
    table = revision_table(audit_revisions(three_dimension_registry, audited_cache, [as_of]))
    assert {"series", "vintage", "policy", "months_compared"} <= set(table.columns)
    assert set(table["policy"]) <= {"archival_vintage", "publication_lag_fallback"}
