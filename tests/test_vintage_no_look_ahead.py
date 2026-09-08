"""No panel may contain an observation nobody could have seen.

This is the single most load-bearing property in the project. A model fitted on
revised data and backtested against history produces numbers that look like
evidence and are not. The tests below pin all three vintage policies, the
detection of a truncated archive entry, and the boundary assertion that fires
when any of them slips.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

import pandas as pd
import pytest

from economic_regime_forecasting.configuration.registry import (
    EconomicSeries,
    ModelDimension,
    Transform,
    load_economic_series_registry,
)
from economic_regime_forecasting.data.cache import SeriesCache, SeriesSnapshot
from economic_regime_forecasting.data.vintage import (
    MINIMUM_USABLE_VINTAGE_MONTHS,
    LookAheadError,
    PointInTimeSeries,
    VintagePolicy,
    censor_by_publication_lag,
    observe,
    summarise_policies,
)
from economic_regime_forecasting.features import transforms


def _series_entry(
    name: str = "test_output",
    series_id: str = "TESTSERIES",
    is_revised: bool = True,
    publication_lag_days: int = 45,
    observation_start: date = date(1960, 1, 1),
) -> EconomicSeries:
    return EconomicSeries(
        name=name,
        series_id=series_id,
        description="a test series",
        role="growth",
        model_dimension=ModelDimension.GROWTH,
        frequency="monthly",
        units="index",
        transform=Transform.LEVEL,
        publication_lag_days=publication_lag_days,
        observation_start=observation_start,
        is_revised=is_revised,
    )


def test_publication_lag_censoring_keeps_only_what_had_been_published(
    rising_series: pd.Series,
) -> None:
    """A monthly value labelled the first of a month is published weeks later.

    With a forty-five day lag, the value labelled 1 November is published on
    16 December, so on 1 December it is not yet available and on 1 January it is.
    """
    censored = censor_by_publication_lag(rising_series, 45, date(1990, 1, 1))
    assert censored.index[-1] == pd.Timestamp("1989-11-01")
    assert pd.Timestamp("1989-12-01") not in censored.index


def test_a_longer_lag_withholds_more(rising_series: pd.Series) -> None:
    short = censor_by_publication_lag(rising_series, 32, date(1990, 1, 1))
    long = censor_by_publication_lag(rising_series, 62, date(1990, 1, 1))
    assert short.index[-1] > long.index[-1]


def test_an_unrevised_series_uses_todays_file_censored_by_lag(
    cache: SeriesCache, rising_series: pd.Series, snapshot_factory: Callable[..., SeriesSnapshot]
) -> None:
    """Market rates are never revised, so today's file is the historical file."""
    cache.write(snapshot_factory(rising_series))
    result = observe(_series_entry(is_revised=False), date(1990, 1, 1), cache)
    assert result.policy is VintagePolicy.UNREVISED_SERIES
    assert result.observations.index[-1] == pd.Timestamp("1989-11-01")


def test_an_archived_vintage_is_used_as_published_without_further_censoring(
    cache: SeriesCache, rising_series: pd.Series, snapshot_factory: Callable[..., SeriesSnapshot]
) -> None:
    """A vintage already reflects what had been published. Censoring it a second
    time would silently throw away its most recent month."""
    as_of = date(1990, 1, 1)
    vintage_view = rising_series[rising_series.index < pd.Timestamp("1989-12-01")]
    cache.write(snapshot_factory(vintage_view, vintage_date=as_of))

    result = observe(_series_entry(), as_of, cache)
    assert result.policy is VintagePolicy.ARCHIVAL_VINTAGE
    assert result.vintage_date_used == as_of
    assert result.observations.index[-1] == pd.Timestamp("1989-11-01")
    assert result.observations.size == vintage_view.size


def test_a_truncated_archive_entry_falls_back_instead_of_fitting_on_twenty_rows(
    cache: SeriesCache, rising_series: pd.Series, snapshot_factory: Callable[..., SeriesSnapshot]
) -> None:
    """The archival service really does return twenty rows of recent history for
    some old consumer price index vintages. Using one would be a disaster that no
    exception announces, so coverage is checked rather than trusted."""
    as_of = date(1990, 1, 1)
    truncated = rising_series[
        (rising_series.index >= pd.Timestamp("1988-05-01"))
        & (rising_series.index < pd.Timestamp("1989-12-01"))
    ]
    assert truncated.size < 25
    cache.write(snapshot_factory(truncated, vintage_date=as_of))
    cache.write(snapshot_factory(rising_series))

    result = observe(_series_entry(), as_of, cache)
    assert result.policy is VintagePolicy.PUBLICATION_LAG_FALLBACK
    assert result.observations.size > 300
    assert "1988-05-01" in result.note
    assert "19 months" in result.note
    assert result.observations.index[-1] == pd.Timestamp("1989-11-01")


def test_a_vintage_that_was_never_backfilled_is_still_used_if_it_is_long_enough(
    cache: SeriesCache, rising_series: pd.Series, snapshot_factory: Callable[..., SeriesSnapshot]
) -> None:
    """Old vintages routinely start decades after the series does. The 1971
    industrial production vintage begins in 1954, not 1919, and that is a normal
    vintage rather than a broken one. What decides usability is whether there is
    enough history to fit on."""
    as_of = date(1990, 1, 1)
    not_backfilled = rising_series[
        (rising_series.index >= pd.Timestamp("1965-01-01"))
        & (rising_series.index < pd.Timestamp("1989-12-01"))
    ]
    assert not_backfilled.size >= MINIMUM_USABLE_VINTAGE_MONTHS
    cache.write(snapshot_factory(not_backfilled, vintage_date=as_of))
    assert observe(_series_entry(), as_of, cache).policy is VintagePolicy.ARCHIVAL_VINTAGE


def test_a_vintage_just_short_of_the_bar_falls_back(
    cache: SeriesCache, rising_series: pd.Series, snapshot_factory: Callable[..., SeriesSnapshot]
) -> None:
    """A vintage too short to fit on is no use however faithful it is."""
    as_of = date(1990, 1, 1)
    too_short = rising_series[rising_series.index < pd.Timestamp("1989-12-01")].iloc[
        -(MINIMUM_USABLE_VINTAGE_MONTHS - 1) :
    ]
    cache.write(snapshot_factory(too_short, vintage_date=as_of))
    cache.write(snapshot_factory(rising_series))
    assert observe(_series_entry(), as_of, cache).policy is VintagePolicy.PUBLICATION_LAG_FALLBACK


def test_the_boundary_assertion_fires_on_an_observation_from_the_future() -> None:
    """The invariant is checked at the boundary rather than trusted, because every
    number downstream depends on it."""
    future = pd.Series(
        [1.0], index=pd.DatetimeIndex([pd.Timestamp("1991-06-01")]), name="TESTSERIES"
    )
    with pytest.raises(LookAheadError, match="had not happened yet"):
        from economic_regime_forecasting.data import vintage as vintage_module

        vintage_module._assert_no_look_ahead(
            PointInTimeSeries(
                name="test_output",
                series_id="TESTSERIES",
                as_of=date(1990, 1, 1),
                observations=future,
                policy=VintagePolicy.ARCHIVAL_VINTAGE,
                vintage_date_used=date(1990, 1, 1),
                note="",
            )
        )


def test_a_panel_built_as_of_1990_contains_nothing_published_after_1990(
    cache: SeriesCache, rising_series: pd.Series, snapshot_factory: Callable[..., SeriesSnapshot]
) -> None:
    """The brief's explicit acceptance test, stated in its own terms."""
    as_of = date(1990, 1, 1)
    for lag in (32, 45, 62):
        entry = _series_entry(is_revised=False, publication_lag_days=lag)
        cache.write(snapshot_factory(rising_series))
        result = observe(entry, as_of, cache)
        latest_label = result.observations.index[-1].date()
        assert latest_label + timedelta(days=lag) <= as_of, (
            f"an observation labelled {latest_label} would not have been published "
            f"until {latest_label + timedelta(days=lag)}, after the panel date {as_of}"
        )


def test_every_shipped_series_declares_a_lag_that_withholds_the_current_month() -> None:
    """A monthly value is labelled with the month it describes and published during
    the following one. A lag under about thirty days would let a panel see a month
    that had not been released, which is the classic off-by-one look-ahead."""
    registry = load_economic_series_registry()
    for series in registry.series:
        assert series.publication_lag_days >= 30, series.name


def test_recession_dating_carries_the_long_lag_the_committee_actually_takes() -> None:
    """The dating committee announces a turning point six to eighteen months after
    it happens. Treating recession status as known in real time would hand the
    forecaster the single most useful fact it could not have had."""
    registry = load_economic_series_registry()
    assert registry["recession_indicator"].publication_lag_days >= 365


def test_policy_counts_cover_every_policy(rising_series: pd.Series) -> None:
    counts = summarise_policies(
        [
            PointInTimeSeries(
                "a", "A", date(1990, 1, 1), rising_series, VintagePolicy.ARCHIVAL_VINTAGE, None, ""
            )
        ]
    )
    assert set(counts) == {policy.value for policy in VintagePolicy}
    assert counts[VintagePolicy.ARCHIVAL_VINTAGE.value] == 1


def test_month_start_normalisation_removes_duplicate_months() -> None:
    messy = pd.Series(
        [1.0, 2.0, 3.0],
        index=pd.DatetimeIndex(["1990-01-01", "1990-01-15", "1990-02-01"]),
        name="TESTSERIES",
    )
    tidy = transforms.to_month_start(messy)
    assert list(tidy.index) == [pd.Timestamp("1990-01-01"), pd.Timestamp("1990-02-01")]
    assert tidy.iloc[0] == 2.0
