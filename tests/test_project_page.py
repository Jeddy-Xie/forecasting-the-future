"""The project page shows only what the record holds, and links only to files it has.

The page's charts are drawn from ``site/data.json``, which must be exactly what the
committed records give. The text a reader sees must state no decimal that a committed
record does not contain, and every file the page loads must exist when it is deployed.
"""

from __future__ import annotations

import json
import math

import pytest

from economic_regime_forecasting import project_page, research_paper
from economic_regime_forecasting.configuration.shipping_approval import (
    CONFIGURATION_HASH_APPROVED_FOR_SHIPPING,
)
from economic_regime_forecasting.regression_baseline import read_baseline_forecasts


@pytest.fixture(scope="module")
def committed_records() -> research_paper.PaperRecords:
    return research_paper.read_committed_records(
        read_baseline_forecasts(research_paper.BLEND_BASELINE),
        read_baseline_forecasts(research_paper.MODEL_ALONE_BASELINE),
        CONFIGURATION_HASH_APPROVED_FOR_SHIPPING,
    )


def _page() -> str:
    return (project_page.SITE_DIRECTORY / "index.html").read_text(encoding="utf-8")


def test_the_committed_page_data_is_what_the_record_gives(
    committed_records: research_paper.PaperRecords,
) -> None:
    committed = project_page.PAGE_DATA_FILE.read_text(encoding="utf-8")
    assert committed == project_page.page_data_text(committed_records), (
        "site/data.json is stale: run `forecast page-assets` and commit the result"
    )


def test_the_page_data_holds_only_finite_numbers() -> None:
    def refuse(constant: str) -> float:
        raise AssertionError(f"site/data.json holds {constant}; write null instead")

    json.loads(project_page.PAGE_DATA_FILE.read_text(encoding="utf-8"), parse_constant=refuse)


def test_every_timeline_blend_is_half_the_model_plus_half_the_chain() -> None:
    data = json.loads(project_page.PAGE_DATA_FILE.read_text(encoding="utf-8"))
    for series in data["timelines"].values():
        for blend, model, chain in zip(
            series["blend"], series["model"], series["chain"], strict=True
        ):
            if blend is None:
                continue
            assert math.isclose(blend, 0.5 * model + 0.5 * chain, abs_tol=1e-4)


def test_every_decimal_the_page_states_is_in_a_committed_record() -> None:
    text = project_page.visible_text(_page())
    unsourced = research_paper.unsourced_numbers_in_text(
        text, research_paper.committed_record_texts()
    )
    assert unsourced == [], (
        f"site/index.html states {unsourced}, which no committed record contains at the "
        "precision printed"
    )


def test_every_file_the_page_loads_exists_when_deployed() -> None:
    missing = []
    for reference in [*project_page.local_references(_page()), "data.json"]:
        source = project_page.DEPLOYED_FROM.get(reference, project_page.SITE_DIRECTORY / reference)
        if not source.is_file():
            missing.append(reference)
    assert missing == [], f"the page links to files that will not be deployed: {missing}"


def test_visible_text_drops_code_and_markup_but_keeps_prose() -> None:
    page = (
        "<style>.a { opacity: 0.85 }</style><p>skill <b>+0.240</b> &amp; more</p>"
        '<svg><path d="M0.5 1.5"/></svg><script>var x = 0.33;</script>'
    )
    text = project_page.visible_text(page)
    assert "+0.240" in text and "& more" in text
    assert "0.85" not in text and "0.5" not in text and "0.33" not in text


def test_plain_text_numbers_are_checked_after_a_percent_sign() -> None:
    assert research_paper.unsourced_numbers_in_text("41% of dates, then 0.87", ["0.870"]) == []
    assert research_paper.unsourced_numbers_in_text("41% of dates, then 0.88", ["0.870"]) == [
        "0.88"
    ]
