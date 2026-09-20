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

from economic_regime_forecasting.backtest.walk_forward import publication_dates
from economic_regime_forecasting.configuration import business_cycle_announcements as announcements
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


def test_recession_status_is_dated_by_the_announcement_that_settled_it() -> None:
    """A constant lag is the wrong shape for this series, and the right rule is
    narrow: a month's recession status became knowable when the committee announced
    the turning point that *opened the phase the month sits in* -- the most recent
    turning point at or before that month.

    Two earlier versions of this rule were wrong. One took the first turning point
    at or *after* the month; one took the later of the two surrounding
    announcements. Both agree with the right answer on most months, which is how
    they survived a reading, so every case below is one where they disagree.
    """
    cases = (
        (
            date(1999, 1, 1),
            date(1992, 12, 22),
            "deep in the expansion the 1991 trough call settled",
        ),
        (date(2001, 6, 1), date(2001, 11, 26), "inside the recession, settled by the peak call"),
        (date(2002, 6, 1), date(2003, 7, 17), "past the trough, unknowable until the trough call"),
        (date(2008, 6, 1), date(2008, 12, 1), "inside the recession, settled by the peak call"),
        (date(2020, 7, 1), date(2021, 7, 19), "past the 2020 trough, settled only in July 2021"),
    )
    for month, expected, why in cases:
        assert announcements.announced_by(month) == expected, f"{month}: {why}"


def test_a_publication_date_is_never_earlier_than_the_month_it_describes() -> None:
    """The invariant whose absence let a look-ahead through.

    A first version of announcement dating let the committee's call REPLACE the
    constant lag. That call settles the phase a month sits in and is usually OLDER
    than the month, so values were dated before they existed -- 1995-01 published
    1992-12-22 -- and a panel built in 1994 could read recession codings out to 2001.
    The suite was 509 green at the time and had nothing to say about it, because no
    test anywhere required a publication date to follow its own label. This is that
    sentence, written down.
    """
    labels = pd.date_range("1990-01-01", "2024-12-01", freq="MS")
    for lag in (0, 30, 400):
        published = publication_dates(labels, lag, dated_by_announcement=True)
        too_early = [
            f"{label.date()} would be published {stamp.date()}"
            for label, stamp in zip(labels, published, strict=True)
            if stamp < label
        ]
        assert not too_early, f"lag {lag}: {too_early[:3]}"


def test_announcement_dating_only_ever_delays_a_publication() -> None:
    """D14 records that a constant lag is too SHORT after a trough. There is no
    direction in which it is too long, so taking the later of the two dates is what
    keeps the rule from handing the forecaster something the lag alone withheld."""
    labels = pd.date_range("1990-01-01", "2024-12-01", freq="MS")
    for lag in (0, 30, 400):
        constant = publication_dates(labels, lag)
        announced = publication_dates(labels, lag, dated_by_announcement=True)
        assert (announced >= constant).all(), lag
        assert (announced > constant).any(), f"lag {lag} delayed nothing at all"


def test_both_keys_into_the_announcement_table_name_the_registrys_recession_series() -> None:
    """The two layers key the same rule off different things, so the keys are checked.

    The walk-forward has the registry to hand and keys announcement dating off the
    series NAME; the audit walks cache entries and keys off the series ID. If those
    two ever named different series the audit would silently stop applying the rule
    it exists to check, the pipeline and the check would disagree, and nothing would
    say so -- every test of the rule itself builds its own snapshot and would still
    pass. This is the one assertion that ties both constants to the registry.
    """
    registry = load_economic_series_registry()
    entry = registry[announcements.RECESSION_SERIES_NAME]
    assert entry.series_id == announcements.RECESSION_SERIES_ID


def test_a_month_before_the_first_recorded_turning_point_has_no_announcement() -> None:
    """The table starts at the 1990 peak. Earlier months are not settled by it, and
    saying so is what lets the caller fall back to the declared lag rather than
    silently borrowing a date from the wrong business cycle."""
    assert announcements.announced_by(date(1990, 1, 1)) is None


def test_the_settling_announcement_never_moves_earlier_as_the_month_advances() -> None:
    """Information does not become available sooner by waiting. This is the property
    that both wrong rules broke: each could hand a later month an earlier
    announcement date, which would mark a value knowable before the value it
    supersedes."""
    latest: date | None = None
    for stamp in pd.date_range("1990-01-01", "2024-12-01", freq="MS"):
        settled = announcements.announced_by(stamp.date())
        if settled is None:
            continue
        assert latest is None or settled >= latest, stamp.date()
        latest = settled


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
