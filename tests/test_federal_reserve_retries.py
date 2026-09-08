"""Retry, backoff, and the two ways the archive says it has nothing.

This is the code the live service taught us to write, so it gets tested against a
stubbed opener rather than against the service itself. A 404 must never be
retried, a rate-limit refusal must be waited out rather than hammered, and a
vintage the archive does not hold must come back as an empty snapshot rather than
as an exception that ends a forty minute run.
"""

from __future__ import annotations

import urllib.error
from datetime import date
from typing import Any

import pytest

from economic_regime_forecasting.data import federal_reserve_client as client
from economic_regime_forecasting.data.federal_reserve_client import (
    FederalReserveError,
    VintageNotArchivedError,
    build_request,
    fetch,
)

GOOD_RESPONSE = b"observation_date,INDPRO\n1919-01-01,4.87\n1919-02-01,4.66\n"


class _Response:
    status = 200

    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_: object) -> None:
        return None


@pytest.fixture
def no_waiting(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record how long the client wanted to sleep without actually sleeping."""
    slept: list[float] = []
    monkeypatch.setattr(client.time, "sleep", lambda seconds: slept.append(seconds))
    monkeypatch.setattr(client, "MINIMUM_SECONDS_BETWEEN_REQUESTS", 0.0)
    return slept


def _stub_opener(monkeypatch: pytest.MonkeyPatch, outcomes: list[Any]) -> list[str]:
    """Serve the given outcomes in order; anything callable is raised or returned."""
    attempts: list[str] = []
    remaining = list(outcomes)

    def fake_urlopen(request: Any, timeout: float = 0.0) -> _Response:
        attempts.append(request.full_url)
        outcome = remaining.pop(0) if remaining else _Response(GOOD_RESPONSE)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(client.urllib.request, "urlopen", fake_urlopen)
    return attempts


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://example.invalid", code, "no", {}, None)  # type: ignore[arg-type]


def test_a_successful_response_is_parsed_on_the_first_attempt(
    monkeypatch: pytest.MonkeyPatch, no_waiting: list[float]
) -> None:
    attempts = _stub_opener(monkeypatch, [_Response(GOOD_RESPONSE)])
    snapshot = fetch(build_request("INDPRO"), units="index")
    assert snapshot.observations.size == 2
    assert len(attempts) == 1
    assert not no_waiting


def test_a_transient_failure_is_retried_and_then_succeeds(
    monkeypatch: pytest.MonkeyPatch, no_waiting: list[float]
) -> None:
    attempts = _stub_opener(
        monkeypatch,
        [urllib.error.URLError("connection reset"), _Response(GOOD_RESPONSE)],
    )
    assert fetch(build_request("INDPRO"), units="index").observations.size == 2
    assert len(attempts) == 2
    assert no_waiting == [client._RETRY_DELAYS_SECONDS[0]]


def test_a_not_found_is_never_retried(
    monkeypatch: pytest.MonkeyPatch, no_waiting: list[float]
) -> None:
    """The archive saying a thing does not exist will not change with waiting."""
    attempts = _stub_opener(monkeypatch, [_http_error(404)])
    with pytest.raises(VintageNotArchivedError):
        fetch(build_request("INDPRO"), units="index")
    assert len(attempts) == 1
    assert not no_waiting


def test_a_rate_limit_switches_to_the_patient_backoff(
    monkeypatch: pytest.MonkeyPatch, no_waiting: list[float]
) -> None:
    """The service is up and asking us to slow down, which is a different
    situation from a flaky connection and deserves a longer wait."""
    _stub_opener(monkeypatch, [_http_error(403), _Response(GOOD_RESPONSE)])
    fetch(build_request("INDPRO"), units="index")
    assert no_waiting == [client._RATE_LIMIT_DELAYS_SECONDS[0]]


@pytest.mark.parametrize("status", [403, 429, 503])
def test_every_rate_limit_status_gets_the_patient_backoff(
    monkeypatch: pytest.MonkeyPatch, no_waiting: list[float], status: int
) -> None:
    _stub_opener(monkeypatch, [_http_error(status), _Response(GOOD_RESPONSE)])
    fetch(build_request("INDPRO"), units="index")
    assert no_waiting[0] >= client._RATE_LIMIT_DELAYS_SECONDS[0]


def test_giving_up_says_what_to_try(
    monkeypatch: pytest.MonkeyPatch, no_waiting: list[float]
) -> None:
    _stub_opener(monkeypatch, [urllib.error.URLError("down")] * 20)
    with pytest.raises(FederalReserveError, match="fewer parallel workers"):
        fetch(build_request("INDPRO"), units="index")


def test_a_vintage_the_archive_lacks_comes_back_empty_rather_than_raising(
    monkeypatch: pytest.MonkeyPatch, no_waiting: list[float]
) -> None:
    """A missing vintage is a fact about the archive, not an error. It becomes an
    empty snapshot, and the caller falls back to the publication-lag view."""
    _stub_opener(monkeypatch, [_http_error(404)])
    snapshot = fetch(build_request("CPIAUCSL", date(1970, 1, 1)), units="index")
    assert snapshot.observations.empty
    assert snapshot.request.vintage_date == date(1970, 1, 1)


def test_an_empty_body_for_a_missing_vintage_is_treated_the_same_way(
    monkeypatch: pytest.MonkeyPatch, no_waiting: list[float]
) -> None:
    """The archive uses both shapes depending on the series."""
    _stub_opener(monkeypatch, [_Response(b"observation_date\n")])
    snapshot = fetch(build_request("CPIAUCSL", date(1970, 1, 1)), units="index")
    assert snapshot.observations.empty


def test_a_broken_series_identifier_still_raises(
    monkeypatch: pytest.MonkeyPatch, no_waiting: list[float]
) -> None:
    """The empty-snapshot treatment is for vintages only. A current-vintage request
    that comes back with no value column means the identifier is wrong."""
    _stub_opener(monkeypatch, [_Response(b"observation_date\n")])
    with pytest.raises(FederalReserveError, match="no value column"):
        fetch(build_request("NOTASERIES"), units="index")


def test_the_client_spaces_its_own_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Politeness is the client's job: the service publishes no quota and blocks an
    address that asks too fast."""
    slept: list[float] = []
    monkeypatch.setattr(client.time, "sleep", lambda seconds: slept.append(seconds))
    monkeypatch.setattr(client, "_last_request_at", client.time.monotonic())
    _stub_opener(monkeypatch, [_Response(GOOD_RESPONSE)])
    fetch(build_request("INDPRO"), units="index")
    assert slept and slept[0] > 0.0
