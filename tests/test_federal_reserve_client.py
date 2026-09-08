"""Parsing the Federal Reserve's comma-separated responses.

The response format has three quirks that would each corrupt a series silently:
a missing observation is written as a single dot, the value column is named after
the series and carries a vintage stamp when one was requested, and a vintage
predating the archive comes back as a header row with no value column at all.
"""

from __future__ import annotations

from datetime import date

import pytest

from economic_regime_forecasting.data.federal_reserve_client import (
    LATEST_ENDPOINT,
    VINTAGE_ENDPOINT,
    FederalReserveError,
    build_request,
    build_url,
    fetch,
    parse_comma_separated_values,
)

_LATEST_RESPONSE = """observation_date,INDPRO
1919-01-01,4.8739
1919-02-01,4.6585
1919-03-01,4.5628
"""

_VINTAGE_RESPONSE = """observation_date,INDPRO_19900102
1919-01-01,10.2
1919-02-01,9.7
"""

_RESPONSE_WITH_A_GAP = """observation_date,DGS10
2020-01-01,.
2020-01-02,1.88
"""


def test_a_latest_response_parses_to_a_dated_float_series() -> None:
    parsed = parse_comma_separated_values(_LATEST_RESPONSE, "INDPRO")
    assert parsed.size == 3
    assert parsed.name == "INDPRO"
    assert parsed.iloc[0] == pytest.approx(4.8739)
    assert str(parsed.index[0].date()) == "1919-01-01"


def test_a_vintage_stamped_value_column_parses_the_same_way() -> None:
    """The column is called INDPRO_19900102, not INDPRO. Position, not name, is
    what the parser keys on."""
    parsed = parse_comma_separated_values(_VINTAGE_RESPONSE, "INDPRO")
    assert parsed.size == 2
    assert parsed.iloc[0] == pytest.approx(10.2)


def test_a_dot_becomes_a_missing_value_not_a_zero() -> None:
    """Reading a dot as zero would put a ten year Treasury yield of nought percent
    into the panel on every market holiday."""
    parsed = parse_comma_separated_values(_RESPONSE_WITH_A_GAP, "DGS10")
    assert bool(parsed.isna().iloc[0])
    assert parsed.iloc[1] == pytest.approx(1.88)


def test_a_vintage_older_than_the_archive_is_reported_rather_than_returned_empty() -> None:
    with pytest.raises(FederalReserveError, match="predates its archive"):
        parse_comma_separated_values("observation_date\n", "CPIAUCSL")


def test_an_empty_response_is_reported() -> None:
    with pytest.raises(FederalReserveError, match="empty response"):
        parse_comma_separated_values("", "INDPRO")


def test_an_unparseable_date_names_the_row_it_is_on() -> None:
    with pytest.raises(FederalReserveError, match="row 3"):
        parse_comma_separated_values("observation_date,X\n1919-01-01,1.0\nnot-a-date,2.0\n", "X")


def test_the_latest_and_vintage_endpoints_are_addressed_correctly() -> None:
    assert build_url("INDPRO", None) == f"{LATEST_ENDPOINT}?id=INDPRO"
    vintage_url = build_url("INDPRO", date(1990, 1, 2))
    assert vintage_url.startswith(VINTAGE_ENDPOINT)
    assert "vintage_date=1990-01-02" in vintage_url


def test_requests_for_different_vintages_are_different_cache_entries() -> None:
    assert build_request("INDPRO").cache_key != build_request("INDPRO", date(1990, 1, 2)).cache_key


def test_this_client_refuses_requests_it_does_not_serve() -> None:
    from dataclasses import replace

    foreign = replace(build_request("INDPRO"), source="some_other_service")
    with pytest.raises(FederalReserveError, match="this client serves"):
        fetch(foreign)


@pytest.mark.network
def test_the_service_still_serves_vintages_without_an_api_key() -> None:
    """The project's central data assumption, checked against the live service.

    If this fails, the archival endpoint has changed and the point-in-time
    discipline needs rebuilding, so it is worth one network call.
    """
    snapshot = fetch(build_request("INDPRO", date(1990, 1, 2)), units="index")
    assert snapshot.observations.size > 800
    assert snapshot.observations.index[-1].date() < date(1990, 1, 2)
