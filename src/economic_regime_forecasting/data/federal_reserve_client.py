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
import threading
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
_RATE_LIMIT_DELAYS_SECONDS: Final[tuple[float, ...]] = (5.0, 15.0, 40.0, 90.0)
"""Backoff for a service that is up but is asking us to slow down.

The keyless endpoint publishes no quota and answers a burst with 403 rather than
429, which reads like a permissions problem and is not one. Long waits are the
right response: the alternative is hammering a public service that has just asked
us not to."""
_RATE_LIMIT_STATUS_CODES: Final[frozenset[int]] = frozenset({403, 429, 503})

MINIMUM_SECONDS_BETWEEN_REQUESTS: Final[float] = 0.35
"""A floor on how fast this client will ask, enforced across threads.

Learned the hard way on 2026-09-08: ten parallel workers fetching archival
vintages earned a 403 on every request from this address, including the ordinary
current-vintage endpoint, and it stayed that way for a while. The service is free,
public and unmetered, which makes politeness the client's job rather than the
server's. Roughly three requests a second fetches a full cache in minutes and has
not been refused."""

_request_spacing_lock = threading.Lock()
_last_request_at = 0.0


def _wait_for_our_turn() -> None:
    """Space requests out, however many threads are asking."""
    global _last_request_at
    with _request_spacing_lock:
        elapsed = time.monotonic() - _last_request_at
        if elapsed < MINIMUM_SECONDS_BETWEEN_REQUESTS:
            time.sleep(MINIMUM_SECONDS_BETWEEN_REQUESTS - elapsed)
        _last_request_at = time.monotonic()


_MISSING_VALUE_MARKERS: Final[frozenset[str]] = frozenset({".", "", "NA", "NaN"})


class FederalReserveError(RuntimeError):
    """The service could not be reached, or returned something unusable."""


class VintageNotArchivedError(FederalReserveError):
    """The archive has no vintage of this series on this date.

    Distinct from a transient failure, and not retried. The archive answers a
    request for a vintage older than its holdings in one of two ways depending on
    the series: an empty response with no value column, or a plain HTTP 404. Both
    mean the same thing, and both are a fact about the archive rather than an
    error, so the caller falls back to the publication-lag view and records that
    it did.
    """


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
    """GET the URL, retrying transient failures, raising a useful message on defeat.

    A 404 is never retried: it is the archive saying the thing does not exist,
    which no amount of waiting will change.
    """
    headers = {"User-Agent": _USER_AGENT}
    api_key = os.environ.get("FRED_API_KEY")
    if api_key:
        # Only affects the service's rate limiting; the response body is the same.
        headers["X-Fred-Api-Key"] = api_key

    delays = list(_RETRY_DELAYS_SECONDS)
    last_error: Exception | None = None
    attempt = 0
    while attempt <= len(delays):
        if attempt > 0:
            time.sleep(delays[attempt - 1])
        attempt += 1
        _wait_for_our_turn()
        try:
            request = urllib.request.Request(url, headers=headers)  # noqa: S310 - fixed https host
            with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
                if response.status != 200:
                    raise FederalReserveError(f"HTTP {response.status} from {url}")
                return str(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise VintageNotArchivedError(f"the service has nothing at {url}") from error
            if error.code in _RATE_LIMIT_STATUS_CODES and delays != list(
                _RATE_LIMIT_DELAYS_SECONDS
            ):
                # Switch to the patient schedule and start the count again. The
                # service is up and is asking us to slow down, which is a
                # different situation from a flaky connection.
                logger.warning("rate_limited url=%s status=%d; backing off", url, error.code)
                delays = list(_RATE_LIMIT_DELAYS_SECONDS)
                attempt = 1
            last_error = error
        except (urllib.error.URLError, TimeoutError, FederalReserveError) as error:
            last_error = error
            logger.warning("fetch_retry attempt=%d url=%s error=%s", attempt, url, error)

    raise FederalReserveError(
        f"could not fetch {url} after {attempt} attempts. Last error: {last_error}. "
        "Check network access to fred.stlouisfed.org, and try fewer parallel workers."
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

    try:
        text = _download(url)
        observations = parse_comma_separated_values(text, request.series_id)
    except (VintageNotArchivedError, FederalReserveError) as error:
        # A request for a vintage the archive does not hold comes back either as a
        # 404 or as a header row with no value column. For a vintage request that
        # is a recorded fact -- an empty snapshot whose sidecar says so -- and the
        # caller falls back to the publication-lag view. For a current-vintage
        # request it is a broken series identifier and must be raised.
        if request.vintage_date is None or not _looks_like_a_missing_vintage(error):
            raise
        logger.info(
            "vintage_not_archived series=%s vintage=%s",
            request.series_id,
            request.vintage_date,
        )
        return SeriesSnapshot(
            request=request,
            observations=pd.Series(
                [],
                index=pd.DatetimeIndex([], name="observation_date"),
                name=request.series_id,
                dtype="float64",
            ),
            source_url=url,
            units=units,
            retrieved_at=now_in_utc(),
            payload_digest=digest_of(""),
        )
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


def _looks_like_a_missing_vintage(error: Exception) -> bool:
    """Both shapes the archive uses to say it has no vintage that far back."""
    return isinstance(error, VintageNotArchivedError) or "predates its archive" in str(error)


def fetcher_for(units: str) -> Callable[[SeriesRequest], SeriesSnapshot]:
    """Bind the units of a registry entry to the fetch callable."""

    def _fetch(request: SeriesRequest) -> SeriesSnapshot:
        return fetch(request, units=units)

    return _fetch
