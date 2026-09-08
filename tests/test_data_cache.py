"""The cache must prove that a hit answers the question that was asked.

The brief's requirement is exact: entries are keyed by a content hash of source,
series, transform and vintage date, and a cache hit must be provably the same
request. These tests pin the key's stability across processes, its sensitivity to
each of the four fields, the round trip through Parquet, and the refusal to serve
an entry whose sidecar disagrees with the request.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from economic_regime_forecasting.data.cache import (
    ArtifactStore,
    CacheError,
    SeriesCache,
    SeriesRequest,
    SeriesSnapshot,
)

_BASE = SeriesRequest(
    source="federal_reserve_economic_data",
    series_id="INDPRO",
    transform="as_published",
    vintage_date=None,
)


def test_cache_key_is_stable_for_an_unchanged_request() -> None:
    """A key computed twice, in any order of construction, is the same key."""
    other = SeriesRequest(
        vintage_date=None,
        transform="as_published",
        series_id="INDPRO",
        source="federal_reserve_economic_data",
    )
    assert _BASE.cache_key == other.cache_key
    assert len(_BASE.cache_key) == 64


def test_cache_key_is_pinned_to_a_known_value() -> None:
    """Pinned so an accidental change to the key recipe cannot silently orphan
    every cached file on every machine."""
    assert _BASE.cache_key.startswith("dca0186b3a95f109")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source", "somewhere_else"),
        ("series_id", "CPIAUCSL"),
        ("transform", "level"),
        ("vintage_date", date(1990, 1, 1)),
    ],
)
def test_changing_any_identifying_field_changes_the_key(field: str, value: object) -> None:
    """All four fields are part of the identity, so all four must move the key."""
    changed = replace(_BASE, **{field: value})
    assert changed.cache_key != _BASE.cache_key


def test_latest_and_vintage_entries_are_stored_apart(
    cache: SeriesCache, rising_series: pd.Series, snapshot_factory: Callable[..., SeriesSnapshot]
) -> None:
    cache.write(snapshot_factory(rising_series))
    cache.write(snapshot_factory(rising_series, vintage_date=date(1990, 1, 1)))
    assert cache.contains(
        SeriesRequest("federal_reserve_economic_data", "TESTSERIES", "as_published", None)
    )
    assert cache.contains(
        SeriesRequest(
            "federal_reserve_economic_data", "TESTSERIES", "as_published", date(1990, 1, 1)
        )
    )


def test_a_written_series_reloads_with_identical_values(
    cache: SeriesCache, rising_series: pd.Series, snapshot_factory: Callable[..., SeriesSnapshot]
) -> None:
    written = snapshot_factory(rising_series)
    cache.write(written)
    reloaded = cache.read(written.request)
    # check_freq is off because a Parquet round trip drops the index's inferred
    # frequency attribute. The dates themselves must match exactly, and do.
    pd.testing.assert_series_equal(reloaded.observations, written.observations, check_freq=False)
    assert list(reloaded.observations.index) == list(written.observations.index)
    assert reloaded.source_url == written.source_url
    assert reloaded.units == written.units


def test_missing_values_survive_the_round_trip(
    cache: SeriesCache, rising_series: pd.Series, snapshot_factory: Callable[..., SeriesSnapshot]
) -> None:
    """The service writes a dot for a missing observation; it must stay missing."""
    with_gaps = rising_series.copy()
    with_gaps.iloc[[3, 40, 100]] = float("nan")
    cache.write(snapshot_factory(with_gaps))
    reloaded = cache.read(snapshot_factory(with_gaps).request)
    assert int(reloaded.observations.isna().sum()) == 3


def test_second_lookup_is_a_hit_and_does_not_refetch(
    cache: SeriesCache, rising_series: pd.Series, snapshot_factory: Callable[..., SeriesSnapshot]
) -> None:
    calls: list[SeriesRequest] = []

    def fetch(request: SeriesRequest) -> SeriesSnapshot:
        calls.append(request)
        return snapshot_factory(rising_series)

    request = snapshot_factory(rising_series).request
    cache.get_or_fetch(request, fetch)
    cache.get_or_fetch(request, fetch)

    assert len(calls) == 1
    assert cache.statistics.hits == 1
    assert cache.statistics.misses == 1
    assert cache.statistics.hit_rate == 0.5


def test_a_sidecar_that_records_a_different_request_is_refused(
    cache: SeriesCache,
    rising_series: pd.Series,
    snapshot_factory: Callable[..., SeriesSnapshot],
    tmp_path: Path,
) -> None:
    """Provably-the-same-request means the sidecar is checked, not assumed."""
    snapshot = snapshot_factory(rising_series)
    cache.write(snapshot)
    sidecar_path = next((tmp_path / "raw").glob("*.json"))
    tampered = json.loads(sidecar_path.read_text())
    tampered["request"]["series_id"] = "SOMETHINGELSE"
    sidecar_path.write_text(json.dumps(tampered))

    with pytest.raises(CacheError, match="answers"):
        cache.read(snapshot.request)


def test_reading_an_absent_entry_says_what_to_do(cache: SeriesCache) -> None:
    with pytest.raises(CacheError, match="forecast fetch-data"):
        cache.read(_BASE)


def test_a_fetcher_returning_the_wrong_series_is_caught(
    cache: SeriesCache, rising_series: pd.Series, snapshot_factory: Callable[..., SeriesSnapshot]
) -> None:
    def wrong_fetch(_: SeriesRequest) -> SeriesSnapshot:
        return snapshot_factory(rising_series, series_id="A_DIFFERENT_SERIES")

    with pytest.raises(CacheError, match="when asked for"):
        cache.get_or_fetch(snapshot_factory(rising_series).request, wrong_fetch)


def test_sidecar_records_everything_a_reader_needs_to_audit_the_fetch(
    cache: SeriesCache, rising_series: pd.Series, snapshot_factory: Callable[..., SeriesSnapshot]
) -> None:
    cache.write(snapshot_factory(rising_series))
    entry = cache.entries()[0]
    for field in (
        "retrieved_at",
        "source_url",
        "series_id",
        "units",
        "observation_start",
        "observation_end",
        "observation_count",
        "payload_digest",
    ):
        assert field in entry, field


def test_artifact_store_round_trips_tables_and_manifests(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "models")
    frame = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    store.write_table("table.parquet", frame)
    pd.testing.assert_frame_equal(store.read_table("table.parquet"), frame)

    store.write_json("manifest.json", {"seed": 20260908})
    assert store.read_json("manifest.json") == {"seed": 20260908}
    assert store.has("manifest.json")
    with pytest.raises(CacheError, match="Produce it first"):
        store.read_json("absent.json")
