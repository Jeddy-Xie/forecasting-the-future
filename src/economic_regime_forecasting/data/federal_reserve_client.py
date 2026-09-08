"""Fetch economic series from the Federal Reserve, current and point-in-time.

Two endpoints, both of which serve comma-separated values over plain HTTP with
no API key and no registration:

  fredgraph.csv    the series as it stands today
  alfredgraph.csv  the series exactly as it stood on a chosen past date

The second endpoint is what makes an honest backtest possible. Fitting a model on
today's revised numbers produces a backtest that could never have been run at the
time, and silently flatters every result downstream.

An API key is not required. If ``FRED_API_KEY`` is present in the environment it
is used only to raise the request rate limit; the code path and the answers are
identical without it.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import date
from typing import Final

import pandas as pd

from economic_regime_forecasting.data.cache import (
    SeriesRequest,
    SeriesSnapshot,
    digest_of,
    now_in_utc,
)

logger = logging.getLogger(__name__)

SOURCE_NAME: Final[str] = "federal_reserve_economic_data"
LATEST_ENDPOINT: Final[str] = "https://fred.stlouisfed.org/graph/fredgraph.csv"
VINTAGE_ENDPOINT: Final[str] = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"

_USER_AGENT: Final[str] = (
    "economic-regime-forecasting/1.0 (research; https://github.com/Jeddy-Xie/forecasting-the-future)"
)
_REQUEST_TIMEOUT_SECONDS: Final[float] = 60.0
_RETRY_DELAYS_SECONDS: Final[tuple[float, ...]] = (1.0, 3.0, 8.0)
_MISSING_VALUE_MARKERS: Final[frozenset[str]] = frozenset({".", "", "NA", "NaN"})


class FederalReserveError(RuntimeError):
    """The service could not be reached, or returned something unusable."""


def build_request(series_id: str, vintage_date: date | None = None) -> SeriesRequest:
    """The cache identity of one fetch from this source.

    The transform is recorded as ``as_published`` because this module never
    transforms anything. Transforms happen in ``features`` on data already
    cached, so the cache always holds exactly what the service returned.
    """
    return SeriesRequest(
        source=SOURCE_NAME,
        series_id=series_id,
        transform="as_published",
        vintage_date=vintage_date,
    )


def build_url(series_id: str, vintage_date: date | None) -> str:
    if vintage_date is None:
        return f"{LATEST_ENDPOINT}?{urllib.parse.urlencode({'id': series_id})}"
    parameters = {"id": series_id, "vintage_date": vintage_date.isoformat()}
    return f"{VINTAGE_ENDPOINT}?{urllib.parse.urlencode(parameters)}"


def _download(url: str) -> str:
    """GET the URL, retrying transient failures, raising a useful message on defeat."""
    headers = {"User-Agent": _USER_AGENT}
    api_key = os.environ.get("FRED_API_KEY")
    if api_key:
        # Only affects the service's rate limiting; the response body is the same.
        headers["X-Fred-Api-Key"] = api_key

    last_error: Exception | None = None
    for attempt, delay in enumerate((0.0, *_RETRY_DELAYS_SECONDS)):
        if delay:
            time.sleep(delay)
        try:
            request = urllib.request.Request(url, headers=headers)  # noqa: S310 - fixed https host
            with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
                if response.status != 200:
                    raise FederalReserveError(f"HTTP {response.status} from {url}")
                return str(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, FederalReserveError) as error:
            last_error = error
            logger.warning("fetch_retry attempt=%d url=%s error=%s", attempt, url, error)

    raise FederalReserveError(
        f"could not fetch {url} after {len(_RETRY_DELAYS_SECONDS) + 1} attempts. "
        f"Last error: {last_error}. Check network access to fred.stlouisfed.org."
    )


def parse_comma_separated_values(text: str, series_id: str) -> pd.Series:
    """Turn a service response into a dated float series.

    The service writes a single dot for a missing observation and names the value
    column after the series, suffixed with the vintage stamp when one was asked
    for. Both are handled here so no caller has to know the format.
    """
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration as error:
        raise FederalReserveError(
            f"empty response for {series_id}; the service returned no header row"
        ) from error

    if len(header) < 2:
        raise FederalReserveError(
            f"response for {series_id} has no value column (header was {header!r}). "
            "This is what the service returns when the requested vintage predates its archive."
        )

    observation_dates: list[pd.Timestamp] = []
    values: list[float] = []
    for row_number, row in enumerate(reader, start=2):
        if not row or len(row) < 2:
            continue
        raw_date, raw_value = row[0].strip(), row[1].strip()
        try:
            observation_dates.append(pd.Timestamp(raw_date))
        except ValueError as error:
            raise FederalReserveError(
                f"row {row_number} of the {series_id} response has an unparseable date {raw_date!r}"
            ) from error
        values.append(float("nan") if raw_value in _MISSING_VALUE_MARKERS else float(raw_value))

    return pd.Series(
        values,
        index=pd.DatetimeIndex(observation_dates, name="observation_date"),
        name=series_id,
        dtype="float64",
    )


def fetch(request: SeriesRequest, units: str = "") -> SeriesSnapshot:
    """Download one series. The function handed to the cache's ``get_or_fetch``."""
    if request.source != SOURCE_NAME:
        raise FederalReserveError(f"this client serves {SOURCE_NAME!r}, not {request.source!r}")
    url = build_url(request.series_id, request.vintage_date)
    text = _download(url)
    observations = parse_comma_separated_values(text, request.series_id)
    logger.info(
        "fetched series=%s vintage=%s rows=%d",
        request.series_id,
        request.vintage_date,
        observations.size,
    )
    return SeriesSnapshot(
        request=request,
        observations=observations,
        source_url=url,
        units=units,
        retrieved_at=now_in_utc(),
        payload_digest=digest_of(text),
    )


def fetcher_for(units: str) -> Callable[[SeriesRequest], SeriesSnapshot]:
    """Bind the units of a registry entry to the fetch callable."""

    def _fetch(request: SeriesRequest) -> SeriesSnapshot:
        return fetch(request, units=units)

    return _fetch
