"""Reconstruct economic series as they stood on a past date.

Macroeconomic data is revised, sometimes for years. A model fitted on today's
numbers and backtested against history is answering a question nobody could have
asked at the time. Everything in this module exists to stop that.

Three policies, each correct for a different kind of series, each recorded in the
run manifest so a reader can see which one produced a given panel:

``UNREVISED_SERIES``
    Market interest rates are never revised, so today's file *is* the historical
    file. Only publication timing matters, and censoring by publication lag gives
    exact point-in-time data.

``ARCHIVAL_VINTAGE``
    The archival service returns the series exactly as it stood on the requested
    date, revisions and all. No further censoring is applied, because a vintage
    already reflects what had been published by then. Censoring it a second time
    would silently discard the most recent month.

``PUBLICATION_LAG_FALLBACK``
    Used when the archive has no usable vintage that far back. The current series
    is censored by publication lag, which gets the timing right but shows revised
    values the observer would not have seen. It is the weaker path, so it is
    detected rather than assumed, and it is reported.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from enum import Enum

import pandas as pd

from economic_regime_forecasting.configuration.registry import EconomicSeries
from economic_regime_forecasting.data import federal_reserve_client
from economic_regime_forecasting.data.cache import SeriesCache

logger = logging.getLogger(__name__)

MINIMUM_USABLE_VINTAGE_MONTHS = 240
"""The shortest archival vintage worth using instead of the fallback.

The first version of this rule compared a vintage's start date to the registry's
declared start, which turned out to answer the wrong question. Old vintages are
routinely not backfilled -- the 1971 industrial production vintage begins in 1954
rather than 1919 -- and that is a normal vintage, not a broken one. What decides
usability is whether there is enough history to fit a model on.

Twenty years is that bar, and it is the same twenty years the model's burn-in
requires, deliberately: a vintage too short to fit on is no use however faithful
it is. It also catches the case this check exists for, where the archive answers
a pre-1994-03 consumer price index request with about twenty rows of recent
history. That response parses cleanly and would produce a model fitted on twenty
months with no exception raised anywhere.

1994-03-01 is the measured boundary, not an estimate: it is the first vintage
date on which the archive returns a usable consumer price index (565 observations
covering 1947-01 .. 1994-01), and every earlier date returns a rolling window of
roughly nineteen. It is never hardcoded — `backtest.walk_forward
.find_first_fully_point_in_time_date` computes it, and a test pins the computed
answer against the live cache, so a backfill would move the code and fail the
test loudly. See ADR 0008 for the probe evidence.
"""


class VintagePolicy(str, Enum):
    UNREVISED_SERIES = "unrevised_series"
    ARCHIVAL_VINTAGE = "archival_vintage"
    PUBLICATION_LAG_FALLBACK = "publication_lag_fallback"


class LookAheadError(AssertionError):
    """A point-in-time series contained an observation nobody could have seen."""


@dataclass(frozen=True)
class PointInTimeSeries:
    """One series as an observer would have had it on ``as_of``."""

    name: str
    series_id: str
    as_of: date
    observations: pd.Series
    policy: VintagePolicy
    vintage_date_used: date | None
    note: str

    def manifest_entry(self) -> dict[str, object]:
        return {
            "name": self.name,
            "series_id": self.series_id,
            "as_of": self.as_of.isoformat(),
            "policy": self.policy.value,
            "vintage_date_used": (
                self.vintage_date_used.isoformat() if self.vintage_date_used else None
            ),
            "observation_count": int(self.observations.size),
            "latest_observation": (
                self.observations.index[-1].date().isoformat()
                if not self.observations.empty
                else None
            ),
            "note": self.note,
        }


def censor_by_publication_lag(
    observations: pd.Series, publication_lag_days: int, as_of: date
) -> pd.Series:
    """Drop observations that had not been published by ``as_of``.

    ``publication_lag_days`` counts from the observation's period-start label,
    which is how the registry defines it. A monthly value labelled the first of
    January is published partway through February, so its lag is around forty
    days, not ten.
    """
    if observations.empty:
        return observations
    publication_dates = observations.index + pd.Timedelta(days=publication_lag_days)
    return observations[publication_dates <= pd.Timestamp(as_of)]


def _vintage_is_usable(observations: pd.Series) -> bool:
    """Does this vintage response cover enough history to fit on?"""
    return int(observations.dropna().size) >= MINIMUM_USABLE_VINTAGE_MONTHS


def observe(
    series: EconomicSeries,
    as_of: date,
    cache: SeriesCache,
) -> PointInTimeSeries:
    """Return ``series`` as it stood on ``as_of``, by the best available policy."""
    if not series.is_revised:
        snapshot = cache.get_or_fetch(
            federal_reserve_client.build_request(series.series_id),
            federal_reserve_client.fetcher_for(series.units),
        )
        censored = censor_by_publication_lag(
            snapshot.observations, series.publication_lag_days, as_of
        )
        result = PointInTimeSeries(
            name=series.name,
            series_id=series.series_id,
            as_of=as_of,
            observations=censored,
            policy=VintagePolicy.UNREVISED_SERIES,
            vintage_date_used=None,
            note=(
                "Market rate, never revised, so the current file is the historical file. "
                f"Censored at a {series.publication_lag_days} day publication lag."
            ),
        )
        _assert_no_look_ahead(result)
        return result

    archival = cache.get_or_fetch(
        federal_reserve_client.build_request(series.series_id, vintage_date=as_of),
        federal_reserve_client.fetcher_for(series.units),
    )
    if _vintage_is_usable(archival.observations):
        result = PointInTimeSeries(
            name=series.name,
            series_id=series.series_id,
            as_of=as_of,
            observations=archival.observations,
            policy=VintagePolicy.ARCHIVAL_VINTAGE,
            vintage_date_used=as_of,
            note="Series exactly as published on this date, revisions and all.",
        )
        _assert_no_look_ahead(result)
        return result

    covered_from = (
        f"{archival.observations.index[0].date().isoformat()} "
        f"({archival.observations.dropna().size} months)"
        if not archival.observations.empty
        else "nothing"
    )
    logger.warning(
        "vintage_fallback series=%s as_of=%s archive_covers_from=%s",
        series.series_id,
        as_of,
        covered_from,
    )
    latest = cache.get_or_fetch(
        federal_reserve_client.build_request(series.series_id),
        federal_reserve_client.fetcher_for(series.units),
    )
    censored = censor_by_publication_lag(latest.observations, series.publication_lag_days, as_of)
    result = PointInTimeSeries(
        name=series.name,
        series_id=series.series_id,
        as_of=as_of,
        observations=censored,
        policy=VintagePolicy.PUBLICATION_LAG_FALLBACK,
        vintage_date_used=None,
        note=(
            f"The archive's vintage for this date covers only {covered_from}, fewer than the "
            f"{MINIMUM_USABLE_VINTAGE_MONTHS} months needed to fit on. Fell back to the current "
            f"series censored at a {series.publication_lag_days} day publication lag: the timing "
            "is right, the values are revised."
        ),
    )
    _assert_no_look_ahead(result)
    return result


def _assert_no_look_ahead(result: PointInTimeSeries) -> None:
    """The invariant every point-in-time series must satisfy.

    No observation may carry a period label on or after the date the panel claims
    to have been assembled. This is checked here, at the boundary, rather than
    trusted, because every downstream number depends on it.
    """
    if result.observations.empty:
        return
    latest_label = result.observations.index[-1].date()
    if latest_label >= result.as_of:
        raise LookAheadError(
            f"{result.series_id} as of {result.as_of.isoformat()} contains an observation "
            f"labelled {latest_label.isoformat()}, which had not happened yet. "
            f"Policy in use was {result.policy.value}."
        )


def summarise_policies(observed: list[PointInTimeSeries]) -> dict[str, int]:
    """Count how many series used each policy, for the run manifest."""
    counts = dict.fromkeys((policy.value for policy in VintagePolicy), 0)
    for item in observed:
        counts[item.policy.value] += 1
    return counts
