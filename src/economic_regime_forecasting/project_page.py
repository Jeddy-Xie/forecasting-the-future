"""The project page's data and images, built from the same committed records as the paper.

``site/`` is the project's public front page, served by GitHub Pages. Its charts are
drawn in the browser from ``site/data.json``, which this module writes and nothing
else does. Like ``research_paper``, it reads only committed records and checks them
against one another before writing, so the page and the paper cannot disagree:

- the blend's and the regime model alone's baselines;
- measurement 0010's skill tables;
- the shipped submission.

The two static images, the skill curve for the README and the regime chains for the
page, are drawn by the paper's own figure functions. The regime image also reads the
cached backtest, as the paper's does.
"""

from __future__ import annotations

import html
import json
import math
import re
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from economic_regime_forecasting import research_paper
from economic_regime_forecasting.configuration.run_settings import PROJECT_ROOT

SITE_DIRECTORY: Final[Path] = PROJECT_ROOT / "site"
PAGE_DATA_FILE: Final[Path] = SITE_DIRECTORY / "data.json"
ASSET_DIRECTORY: Final[Path] = SITE_DIRECTORY / "assets"
PNG_METADATA: Final[dict[str, Any]] = {"Software": None}
"""No version string in the PNGs, so a rebuild on the same record is byte-identical."""

DIGITS: Final[int] = 4


def _number(value: float) -> float | None:
    """A JSON-safe number: rounded, and null where it is not finite."""
    return round(float(value), DIGITS) if math.isfinite(float(value)) else None


def _curve(curves: pd.DataFrame, forecaster: str) -> list[list[float | None]]:
    rows = curves[curves["forecaster"] == forecaster].sort_values("horizon_in_months")
    return [
        [
            int(row["horizon_in_months"]),
            _number(row["mean_skill"]),
            _number(row["lower_bound"]),
            _number(row["upper_bound"]),
        ]
        for row in rows.to_dict("records")
    ]


def _differences(differences: pd.DataFrame) -> list[list[float | None]]:
    rows = differences.sort_values("horizon_in_months")
    return [
        [
            int(row["horizon_in_months"]),
            _number(row["difference"]),
            _number(row["lower_bound"]),
            _number(row["upper_bound"]),
        ]
        for row in rows.to_dict("records")
    ]


def _shipped(rows: pd.DataFrame, years: int, column: str) -> float | None:
    """One shipped number for one question, by horizon in years."""
    return _number(float(rows[column].astype("float64").loc[years]))


def page_data(records: research_paper.PaperRecords) -> dict[str, Any]:
    """Everything the page draws, as plain JSON-ready values.

    One-year timelines carry all three forecasters and the historical average for
    every question on the same forecast dates, so the page can switch between them
    without a second request.
    """
    forecasts = records.forecasts
    curves = records.curves
    informative = curves.loc[curves["informative"].astype(bool), "horizon_in_months"]
    one_year = forecasts[forecasts["horizon_months"] == 12]
    dates = sorted(one_year["forecast_date"].unique())
    timelines: dict[str, Any] = {}
    for indicator, short_name in research_paper.SHORT_QUESTION_NAMES.items():
        rows = one_year[one_year["indicator"] == indicator].set_index("forecast_date")
        rows = rows.reindex(dates)
        timelines[indicator] = {
            "question": short_name,
            "blend": [_number(value) for value in rows[research_paper.BLEND]],
            "model": [_number(value) for value in rows[research_paper.MODEL_ALONE]],
            "chain": [_number(value) for value in rows[research_paper.CHAIN]],
            "average": [_number(value) for value in rows[research_paper.AVERAGE]],
            "outcome": [_number(value) for value in rows["realised_outcome"]],
        }
    by_question = research_paper.skill_by_indicator(forecasts, 12)
    submission = records.submission
    shipped = []
    for indicator, short_name in research_paper.SHORT_QUESTION_NAMES.items():
        subset = submission[submission["indicator"] == indicator].set_index("horizon_years")
        shipped.append(
            {
                "indicator": indicator,
                "short": short_name,
                "question": str(subset.at[1, "question"]),
                "one_year": _shipped(subset, 1, "probability"),
                "model_half": _shipped(subset, 1, "regime_model_probability"),
                "chain_half": _shipped(subset, 1, "condition_chain_probability"),
                "five_years": _shipped(subset, 5, "probability"),
                "ten_years": _shipped(subset, 10, "probability"),
            }
        )
    return {
        "configuration": records.approved_configuration_hash,
        "forecast_dates": len(dates),
        "first_month": pd.Timestamp(dates[0]).strftime("%Y-%m"),
        "last_month": pd.Timestamp(dates[-1]).strftime("%Y-%m"),
        "forecasts": len(forecasts),
        "resolved": int(np.isfinite(forecasts["realised_outcome"]).sum()),
        "horizons": {
            "blend": records.blend_last_horizon_with_skill,
            "model": records.model_last_horizon_with_skill,
        },
        "informative_through": int(informative.max()),
        "curves": {
            "blend": _curve(curves, research_paper.BLEND),
            "model": _curve(curves, research_paper.MODEL_ALONE),
            "chain": _curve(curves, research_paper.CHAIN),
        },
        "blend_minus_chain": _differences(records.blend_minus_chain),
        "slopes": {
            "blend": _number(research_paper.calibration_slope(forecasts, research_paper.BLEND, 12)),
            "model": _number(
                research_paper.calibration_slope(forecasts, research_paper.MODEL_ALONE, 12)
            ),
            "chain": _number(research_paper.calibration_slope(forecasts, research_paper.CHAIN, 12)),
        },
        "by_question": [
            {
                "question": str(question),
                "model": _number(values[research_paper.MODEL_ALONE]),
                "chain": _number(values[research_paper.CHAIN]),
                "blend": _number(values[research_paper.BLEND]),
            }
            for question, values in by_question.iterrows()
        ],
        "dates": [pd.Timestamp(value).strftime("%Y-%m") for value in dates],
        "timelines": timelines,
        "shipped": shipped,
    }


def page_data_text(records: research_paper.PaperRecords) -> str:
    """The page data as the committed file holds it: sorted keys, one line, a newline."""
    return json.dumps(page_data(records), sort_keys=True, separators=(",", ":")) + "\n"


def write_page_assets(
    records: research_paper.PaperRecords,
    backtest_results: pd.DataFrame,
    site_directory: Path = SITE_DIRECTORY,
) -> list[Path]:
    """Write ``data.json`` and the two static images the page and the README show."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from economic_regime_forecasting.reporting import paper_figures

    found = sorted({str(value) for value in backtest_results["configuration_hash"]})
    if found != [records.approved_configuration_hash]:
        raise research_paper.PaperAssetError(
            f"the cached backtest carries configuration {found}, not the approved "
            f"{records.approved_configuration_hash}. Run `forecast check-gates` first."
        )
    assets = site_directory / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    data_file = site_directory / "data.json"
    data_file.write_text(page_data_text(records), encoding="utf-8")
    written.append(data_file)

    chains = research_paper.regime_chains(
        backtest_results,
        4,
        4,
        research_paper.GROWTH_STATE_NAMES,
        research_paper.LEVELS_STATE_NAMES,
    )
    figures = {
        "skill_curves.png": paper_figures.skill_curves(
            records.curves,
            {
                research_paper.MODEL_ALONE: records.model_last_horizon_with_skill,
                research_paper.BLEND: records.blend_last_horizon_with_skill,
            },
        ),
        "regime_chains.png": paper_figures.regime_chains(
            [
                ("Growth chain: industrial production growth", chains.growth),
                ("Levels chain: inflation and the three-month bill rate", chains.levels),
            ],
            research_paper.recession_months(records.forecasts),
        ),
    }
    for name, figure in figures.items():
        path = assets / name
        figure.savefig(path, format="png", dpi=200, metadata=PNG_METADATA)
        plt.close(figure)
        written.append(path)
    return written


# ------------------------------------------------------------ the page's own text

HIDDEN_ELEMENTS: Final = re.compile(r"<(script|style|svg|pre)\b.*?</\1>", re.DOTALL | re.IGNORECASE)
TAG: Final = re.compile(r"<[^>]+>")
LOCAL_REFERENCE: Final = re.compile(r"""(?:href|src)="(?!https?:|#|mailto:)([^"]+)\"""")


def visible_text(page: str) -> str:
    """The text a reader sees: tags, scripts, styles, drawings and code removed."""
    text = HIDDEN_ELEMENTS.sub(" ", page)
    text = TAG.sub(" ", text)
    return html.unescape(text)


def local_references(page: str) -> list[str]:
    """Every file the page links to or loads from its own site."""
    return sorted(set(LOCAL_REFERENCE.findall(page)))


DEPLOYED_FROM: Final[dict[str, Path]] = {"paper.pdf": PROJECT_ROOT / "paper" / "main.pdf"}
"""Files the Pages workflow copies into the site at deploy time, and where from."""
