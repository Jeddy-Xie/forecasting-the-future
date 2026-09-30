"""The research paper's figures, tables and named numbers, built from the record.

``paper/main.tex`` prints numbers from three places, and this module is the only
road from each of them to the page:

1. **Committed records**, read here and never retyped:
   - the adopted blend's and the regime model alone's backtest forecasts
     (``baselines/reference-adopted-blend`` and ``baselines/reference-0008``);
   - measurement 0010's skill tables (``research/reports/skill-at-every-horizon/``);
   - the shipped submission (``submission/``).
2. **The walk-forward's own artifacts in ``.cache/``**, which ``forecast
   check-gates`` rebuilds byte for byte: the regime distribution each forecast
   used, the regime names, and both rules' verdicts. Their configuration hash is
   checked against the approved one before anything is read from them.
3. **Numbers typed into the prose.** :func:`unsourced_numbers` finds every decimal
   the paper states and requires each to appear in a committed record at the
   precision printed. A test runs it on the real paper, so a mistyped number fails
   the suite rather than reaching a reader.

Nothing here fits a model or runs a bootstrap. Every interval the paper prints was
computed by the pipeline and committed before this module reads it.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

from economic_regime_forecasting.configuration.run_settings import PROJECT_ROOT
from economic_regime_forecasting.evaluation.calibration import assess_calibration
from economic_regime_forecasting.evaluation.scoring import (
    ScoringError,
    area_under_the_curve,
    brier_score,
    brier_skill_score,
)
from economic_regime_forecasting.reporting import latex

PAPER_DIRECTORY: Final[Path] = PROJECT_ROOT / "paper"
GENERATED_DIRECTORY: Final[Path] = PAPER_DIRECTORY / "generated"
SKILL_CURVE_DIRECTORY: Final[Path] = (
    PROJECT_ROOT / "research" / "reports" / "skill-at-every-horizon"
)
BLEND_BASELINE: Final[str] = "reference-adopted-blend"
MODEL_ALONE_BASELINE: Final[str] = "reference-0008"
MODEL_ALONE_CONFIGURATION_HASH: Final[str] = "fec79a040f9ca6f9"
"""The two-chain regime model without the blend (ADR 0010), the blend's regime half."""

BLEND = "blend"
MODEL_ALONE = "regime model alone"
CHAIN = "condition chain"
AVERAGE = "historical average"
SERIES_START_AVERAGE = "series-start average"
FORECASTERS: Final[tuple[str, ...]] = (MODEL_ALONE, CHAIN, BLEND)

SHORT_QUESTION_NAMES: Final[dict[str, str]] = {
    "consumer_price_inflation_above_five_percent_within_horizon": "Inflation above 5%, any time",
    "consumer_price_inflation_above_three_percent_at_horizon": "Inflation above 3%, at the horizon",
    "federal_funds_rate_below_one_percent_within_horizon": "Funds rate below 1%, any time",
    "federal_funds_rate_above_four_percent_at_horizon": "Funds rate above 4%, at the horizon",
    "treasury_yield_curve_inverted_within_horizon": "Yield curve inverts, any time",
    "industrial_production_growth_above_two_percent_at_horizon": (
        "Output growth above 2%, at the horizon"
    ),
    "unemployment_rate_above_seven_percent_within_horizon": "Unemployment above 7%, any time",
    "unemployment_rate_above_five_percent_at_horizon": "Unemployment above 5%, at the horizon",
    "economy_in_recession_within_horizon": "Recession, any time",
    "economy_in_recession_at_horizon_date": "Recession, in the horizon month",
}
"""The ten questions in the order the paper lists them: the model's own inputs
first, then what it never observes. The order is the argument of Table 3."""

RECORD_PATTERNS: Final[tuple[str, ...]] = (
    "README.md",
    "docs/*.md",
    "docs/adr/*.md",
    "proving/experiments/*/experiment.json",
    "research/experiments-drafts/*.md",
    "research/ledger/decisions.md",
    "research/ledger/delegated-decisions/*.json",
    "research/briefings/*.md",
    "research/reports/skill-at-every-horizon/*.txt",
    "research/reports/skill-at-every-horizon/*/*.txt",
    "research/reports/0002-slate/report.html",
    "research/reports/0002-slate/prose/*.html",
    "submission/README.md",
    "forecasts/README.md",
    "paper/generated/*.tex",
)
"""Where a number typed into the paper may come from. Every one is committed."""

DECIMAL = re.compile(r"(?<![\w.])([+\-\u2212])?\s?(\d+\.\d+)(?![\w.])")
"""A decimal with an optional sign: a hyphen, a plus, or a true minus."""

NOT_CHECKED = re.compile(
    r"\\derived\{[^{}]*\}"
    r"|\\cite[pt]?\*?(\[[^\]]*\])*\{[^}]*\}"
    r"|%[^\n]*"
    r"|\d+\.\d+(\\linewidth|\\textwidth|\\columnwidth|pt|em|ex|cm|mm)(?![A-Za-z])"
)
"""Spans the number check skips: numbers derived in the text by arithmetic the
reader can redo (marked ``\\derived{...}``), citation keys, comments, and layout
lengths such as a column's ``0.46\\linewidth``, which are not claims."""


class PaperAssetError(ValueError):
    """A record the paper is built from is missing, stale, or inconsistent."""


# ------------------------------------------------------------------ the forecasts


def paper_forecasts(
    blend_run: pd.DataFrame,
    model_alone_run: pd.DataFrame,
    approved_configuration_hash: str,
) -> pd.DataFrame:
    """The blend's and the model alone's backtest forecasts, side by side.

    Both baselines carry the same reference columns, because the references do not
    depend on the forecaster. That is checked, not assumed, and so is the identity
    that defines the blend: half the model plus half the chain, exactly.
    """
    for frame, expected, name in (
        (blend_run, approved_configuration_hash, BLEND_BASELINE),
        (model_alone_run, MODEL_ALONE_CONFIGURATION_HASH, MODEL_ALONE_BASELINE),
    ):
        found = sorted({str(value) for value in frame["configuration_hash"]})
        if found != [expected]:
            raise PaperAssetError(
                f"baselines/{name} carries configuration {found}, expected {expected}. "
                "Recapture it from that configuration, or point the paper at the right one."
            )
    keys = ["indicator", "forecast_date", "horizon_months"]
    merged = blend_run.merge(model_alone_run, on=keys, suffixes=("", "_model_alone"))
    if len(merged) != len(blend_run) or len(merged) != len(model_alone_run):
        raise PaperAssetError(
            f"the two baselines do not cover the same forecasts ({len(blend_run)} and "
            f"{len(model_alone_run)} rows, {len(merged)} in common)"
        )
    for column in (
        "realised_outcome",
        "climatology_probability",
        "model_sample_climatology_probability",
        "condition_chain_probability",
    ):
        left = merged[column].to_numpy(dtype="float64")
        right = merged[f"{column}_model_alone"].to_numpy(dtype="float64")
        if not np.array_equal(left, right, equal_nan=True):
            raise PaperAssetError(
                f"{column} differs between the two baselines, so they were not captured on "
                "the same data and cannot be compared row by row"
            )
    rebuilt = (
        0.5 * merged["predicted_probability_model_alone"]
        + 0.5 * merged["condition_chain_probability"]
    )
    if not np.allclose(rebuilt, merged["predicted_probability"], rtol=0.0, atol=1e-12):
        raise PaperAssetError(
            "the blend is not half the regime model plus half the chain on every row; "
            "the baselines do not describe the configuration the paper says they do"
        )
    return pd.DataFrame(
        {
            "indicator": merged["indicator"],
            "forecast_date": pd.to_datetime(merged["forecast_date"]),
            "horizon_months": merged["horizon_months"].astype(int),
            BLEND: merged["predicted_probability"].astype("float64"),
            MODEL_ALONE: merged["predicted_probability_model_alone"].astype("float64"),
            CHAIN: merged["condition_chain_probability"].astype("float64"),
            AVERAGE: merged["model_sample_climatology_probability"].astype("float64"),
            SERIES_START_AVERAGE: merged["climatology_probability"].astype("float64"),
            "realised_outcome": merged["realised_outcome"].astype("float64"),
        }
    )


def _at_horizon(forecasts: pd.DataFrame, horizon_in_months: int) -> pd.DataFrame:
    rows = forecasts[forecasts["horizon_months"] == horizon_in_months]
    if rows.empty:
        raise PaperAssetError(f"no forecast at {horizon_in_months} months")
    return rows


def _skill_or_nan(predicted: np.ndarray, realised: np.ndarray, reference: np.ndarray) -> float:
    try:
        return brier_skill_score(predicted, realised, reference)
    except ScoringError:
        return float("nan")


def skill_by_indicator(
    forecasts: pd.DataFrame,
    horizon_in_months: int,
    benchmark: str = AVERAGE,
    forecasters: Sequence[str] = FORECASTERS,
) -> pd.DataFrame:
    """Brier skill against a benchmark, one row per question, one column per forecaster.

    Rows follow :data:`SHORT_QUESTION_NAMES` and are labelled with its short names.
    A question whose outcome never varies has no defined skill and reads NaN.
    """
    rows = _at_horizon(forecasts, horizon_in_months)
    table: dict[str, dict[str, float]] = {}
    for indicator, short_name in SHORT_QUESTION_NAMES.items():
        subset = rows[rows["indicator"] == indicator]
        if subset.empty:
            raise PaperAssetError(f"no forecasts for {indicator} at {horizon_in_months} months")
        realised = subset["realised_outcome"].to_numpy()
        reference = subset[benchmark].to_numpy()
        table[short_name] = {
            forecaster: _skill_or_nan(subset[forecaster].to_numpy(), realised, reference)
            for forecaster in forecasters
        }
    return pd.DataFrame.from_dict(table, orient="index")[list(forecasters)]


def indicator_metrics(forecasts: pd.DataFrame, forecaster: str) -> pd.DataFrame:
    """Per question and horizon: how many resolved, how often yes, and how well scored."""
    records = []
    for horizon in sorted(forecasts["horizon_months"].unique()):
        rows = _at_horizon(forecasts, int(horizon))
        for indicator, short_name in SHORT_QUESTION_NAMES.items():
            subset = rows[rows["indicator"] == indicator]
            resolved = subset[np.isfinite(subset["realised_outcome"].to_numpy())]
            realised = resolved["realised_outcome"].to_numpy()
            predicted = resolved[forecaster].to_numpy()
            varies = realised.size > 0 and 0.0 < realised.mean() < 1.0
            records.append(
                {
                    "question": short_name,
                    "horizon_years": int(horizon) // 12,
                    "resolved": int(realised.size),
                    "base_rate": float(realised.mean()) if realised.size else float("nan"),
                    "brier_score": brier_score(predicted, realised)
                    if realised.size
                    else float("nan"),
                    "skill_against_average": _skill_or_nan(
                        predicted, realised, resolved[AVERAGE].to_numpy()
                    ),
                    "skill_against_series_start": _skill_or_nan(
                        predicted, realised, resolved[SERIES_START_AVERAGE].to_numpy()
                    ),
                    "area_under_the_curve": area_under_the_curve(predicted, realised)
                    if varies
                    else float("nan"),
                }
            )
    return pd.DataFrame(records)


def reliability_table(
    forecasts: pd.DataFrame, forecaster: str, horizon_in_months: int
) -> pd.DataFrame:
    """The ten-bin reliability curve of one forecaster at one horizon, pooled over questions."""
    rows = _at_horizon(forecasts, horizon_in_months)
    return assess_calibration(
        rows[forecaster].to_numpy(), rows["realised_outcome"].to_numpy()
    ).table()


def forecast_timeline(
    forecasts: pd.DataFrame, indicator: str, horizon_in_months: int
) -> pd.DataFrame:
    """One question's shipped probability, base rate and outcome, by forecast date."""
    rows = _at_horizon(forecasts, horizon_in_months)
    subset = rows[rows["indicator"] == indicator].sort_values("forecast_date")
    return pd.DataFrame(
        {
            "forecast_date": subset["forecast_date"].to_numpy(),
            "probability": subset[BLEND].to_numpy(),
            "base_rate": subset[AVERAGE].to_numpy(),
            "outcome": subset["realised_outcome"].to_numpy(),
        }
    )


def recession_months(forecasts: pd.DataFrame) -> pd.DatetimeIndex:
    """Every month the recession-in-the-horizon-month question resolved yes.

    A one-year forecast made in month t resolves on month t + 12, so the months are
    read off the outcomes rather than fetched again.
    """
    rows = _at_horizon(forecasts, 12)
    yes = rows[
        (rows["indicator"] == "economy_in_recession_at_horizon_date")
        & (rows["realised_outcome"] == 1.0)
    ]
    return pd.DatetimeIndex(sorted(pd.to_datetime(yes["forecast_date"]) + pd.DateOffset(months=12)))


# --------------------------------------------------------- skill at every horizon

MEASUREMENT_LABELS: Final[dict[tuple[str, str], str]] = {
    ("model run", "regime model"): MODEL_ALONE,
    ("model run", "condition chain"): CHAIN,
    ("blend run", "regime model"): BLEND,
}
"""Measurement 0010 ran twice. Its tables call the scored column "regime model" in
both runs, and on the second run that column is the blend (0010's RESULT says so)."""


def skill_curves(model_run: pd.DataFrame, blend_run: pd.DataFrame, benchmark: str) -> pd.DataFrame:
    """Measurement 0010's two runs as one table, with each forecaster named for what it is.

    The chain is scored in both runs. The two copies must agree, since the chain does
    not depend on the model; they are checked and one is kept.
    """
    chain_in_model_run = model_run[
        (model_run["forecaster"] == "condition chain") & (model_run["benchmark"] == benchmark)
    ].reset_index(drop=True)
    chain_in_blend_run = blend_run[
        (blend_run["forecaster"] == "condition chain") & (blend_run["benchmark"] == benchmark)
    ].reset_index(drop=True)
    if not chain_in_model_run.equals(chain_in_blend_run):
        raise PaperAssetError(
            "measurement 0010's two runs score the condition chain differently; they were "
            "not run on the same data, so their curves cannot share a figure"
        )
    parts = []
    for (run, scored), name in MEASUREMENT_LABELS.items():
        table = model_run if run == "model run" else blend_run
        rows = table[(table["forecaster"] == scored) & (table["benchmark"] == benchmark)].copy()
        rows["forecaster"] = name
        parts.append(rows)
    return pd.concat(parts, ignore_index=True).sort_values(
        ["forecaster", "horizon_in_months"], ignore_index=True
    )


def last_horizon_with_skill(summary: Mapping[str, object], benchmark: str) -> int:
    """Measurement 0010's ship-the-average horizon for the scored forecaster of a run."""
    readings = summary.get("readings")
    if not isinstance(readings, list):
        raise PaperAssetError("measurement 0010's summary has no readings")
    for reading in readings:
        if reading["forecaster"] == "regime model" and reading["benchmark"] == benchmark:
            return int(reading["ship_the_average_horizon"])
    raise PaperAssetError(f"measurement 0010's summary has no reading against {benchmark}")


def month_ranges(months: Iterable[int]) -> list[tuple[int, int]]:
    """Consecutive months collapsed into (first, last) pairs."""
    ranges: list[tuple[int, int]] = []
    for month in sorted(months):
        if ranges and month == ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], month)
        else:
            ranges.append((month, month))
    return ranges


def describe_ranges(ranges: Sequence[tuple[int, int]]) -> str:
    """Month ranges as the paper writes them: 1--8 and 114--120."""
    if not ranges:
        return "none"
    parts = [f"{first}--{last}" if first != last else str(first) for first, last in ranges]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


# ----------------------------------------------------------------- the regimes


@dataclass(frozen=True)
class RegimeChains:
    """The filtered probability of each state of each chain, at every forecast date."""

    growth: pd.DataFrame
    levels: pd.DataFrame


GROWTH_STATE_NAMES: Final[tuple[str, ...]] = (
    "state 1, weakest growth",
    "state 2",
    "state 3",
    "state 4, strongest growth",
)
LEVELS_STATE_NAMES: Final[tuple[str, ...]] = (
    "state 1, lowest inflation",
    "state 2",
    "state 3",
    "state 4, highest inflation",
)
"""Each chain's states named by rank, which is all that stays fixed across refits.

Every refit orders a chain's states by its first emission mean (growth for the
growth chain, inflation for the levels chain; ``state_labelling.canonicalise``).
So state 1 is always the weakest growth or lowest inflation *of that fit*, while
what that means in natural units drifts as the expanding window grows. The most
recent fit's natural-unit meaning is in the regime table, not in these names."""


def regime_chains(
    backtest_results: pd.DataFrame,
    growth_state_count: int,
    levels_state_count: int,
    growth_names: Sequence[str],
    levels_names: Sequence[str],
) -> RegimeChains:
    """Each chain's marginal filtered distribution at every forecast date.

    Every question on a date shares one regime distribution, so any one question's
    rows serve. The joint vector is reshaped to growth by levels and summed each way.
    """
    first = backtest_results.sort_values(["indicator", "horizon_months"]).iloc[0]
    rows = backtest_results[
        (backtest_results["indicator"] == first["indicator"])
        & (backtest_results["horizon_months"] == first["horizon_months"])
    ].sort_values("forecast_date")
    joint = np.array(
        [[float(value) for value in str(text).split(",")] for text in rows["regime_distribution"]]
    )
    expected = growth_state_count * levels_state_count
    if joint.shape[1] != expected:
        raise PaperAssetError(
            f"the regime distributions have {joint.shape[1]} states, expected "
            f"{growth_state_count} x {levels_state_count} = {expected}"
        )
    grid = joint.reshape(len(joint), growth_state_count, levels_state_count)
    dates = pd.DatetimeIndex(pd.to_datetime(rows["forecast_date"]))
    return RegimeChains(
        growth=pd.DataFrame(grid.sum(axis=2), index=dates, columns=list(growth_names)),
        levels=pd.DataFrame(grid.sum(axis=1), index=dates, columns=list(levels_names)),
    )


# -------------------------------------------------------------- tables as LaTeX


def _with_interval(point: float, lower: float, upper: float) -> str:
    """A signed estimate followed by its interval in small type."""
    return f"{latex.signed(point, 3)} {{\\scriptsize {latex.interval(lower, upper, 3)}}}"


def skill_curve_table(curves: pd.DataFrame, differences: pd.DataFrame) -> str:
    """Appendix table: every month from 1 to 120, each forecaster's skill and the gap."""
    wide = {
        name: curves[curves["forecaster"] == name].set_index("horizon_in_months")
        for name in FORECASTERS
    }
    gap = differences.set_index("horizon_in_months")
    rows = []
    for month in sorted(wide[BLEND].index):
        cells = [str(month)]
        for name in (MODEL_ALONE, BLEND, CHAIN):
            row = wide[name].loc[month]
            cells.append(
                _with_interval(
                    float(row["mean_skill"]), float(row["lower_bound"]), float(row["upper_bound"])
                )
            )
        difference = gap.loc[month]
        cells.append(
            _with_interval(
                float(difference["difference"]),
                float(difference["lower_bound"]),
                float(difference["upper_bound"]),
            )
        )
        cells.append(
            latex.unsigned(float(wide[BLEND].loc[month]["effective_independent_observations"]), 1)
        )
        rows.append(cells)
    return latex.tabular(
        ["Months", "Regime model alone", "Blend", "Condition chain", "Blend $-$ chain", "Indep."],
        rows,
        "rllllr",
        long=True,
        caption=(
            "Brier skill against the historical average (R1) at every horizon, with 90\\% "
            "moving-block bootstrap intervals. \\emph{Indep.} is the number of effectively "
            "independent observations behind each estimate. Source: measurement 0010, "
            "\\texttt{research/reports/skill-at-every-horizon/}."
        ),
        label="tab:every-month",
    )


def indicator_skill_table(table: pd.DataFrame) -> str:
    """Main-text table: one-year skill by question for the three forecasters."""
    rows = []
    for question, values in table.iterrows():
        cells = [latex.escape(str(question))]
        best = np.nanmax(values.to_numpy())
        for forecaster in FORECASTERS:
            value = float(values[forecaster])
            text = latex.signed(value, 3)
            cells.append(rf"\textbf{{{text}}}" if math.isfinite(value) and value == best else text)
        rows.append(cells)
    means = table.mean(axis=0)
    rows.append(
        [r"\emph{Mean over the ten}"]
        + [latex.signed(float(means[name]), 3) for name in FORECASTERS]
    )
    return latex.tabular(
        ["Question (one year ahead)", "Regime model alone", "Condition chain", "Blend"],
        rows,
        "lrrr",
    )


def indicator_metrics_table(metrics: pd.DataFrame) -> str:
    """Appendix table: every question at every horizon, for the forecaster that ships."""
    rows = []
    for record in metrics.to_dict("records"):
        rows.append(
            [
                latex.escape(str(record["question"])),
                str(record["horizon_years"]),
                str(record["resolved"]),
                latex.unsigned(float(record["base_rate"]), 3),
                latex.unsigned(float(record["brier_score"]), 3),
                latex.signed(float(record["skill_against_average"]), 3),
                latex.signed(float(record["skill_against_series_start"]), 3),
                latex.unsigned(float(record["area_under_the_curve"]), 2),
            ]
        )
    return latex.tabular(
        [
            "Question",
            "Years",
            "Resolved",
            "Base rate",
            "Brier",
            "Skill (R1)",
            "Skill (series start)",
            "AUC",
        ],
        rows,
        "lrrrrrrr",
        long=True,
        caption=(
            "The blend's scores for every question and horizon. \\emph{Base rate} is how often the "
            "question resolved yes over the resolved forecasts. \\emph{AUC} is the area under the "
            "receiver operating characteristic curve, where 0.5 is no better than chance; it is "
            "blank where the outcome never varies. Computed from "
            "\\texttt{baselines/reference-adopted-blend}."
        ),
        label="tab:metrics",
    )


def shipped_forecasts_table(submission: pd.DataFrame) -> str:
    """Appendix table: what ships today, with both halves of the blend at one year."""
    rows = []
    for indicator, short_name in SHORT_QUESTION_NAMES.items():
        subset = submission[submission["indicator"] == indicator].set_index("horizon_years")
        one_year = subset.loc[1]
        rows.append(
            [
                latex.escape(short_name),
                latex.unsigned(float(one_year["probability"]), 3),
                latex.unsigned(float(one_year["regime_model_probability"]), 3),
                latex.unsigned(float(one_year["condition_chain_probability"]), 3),
                latex.unsigned(float(subset.loc[5]["probability"]), 3),
                latex.unsigned(float(subset.loc[10]["probability"]), 3),
            ]
        )
    return latex.tabular(
        ["Question", "1 year", "Model half", "Chain half", "5 years", "10 years"],
        rows,
        "lrrrrr",
    )


def regime_table(descriptions: pd.DataFrame) -> str:
    """Appendix table: the sixteen joint regimes of the most recent fit, in natural units."""
    rows = []
    for record in descriptions.sort_values("state").to_dict("records"):
        rows.append(
            [
                str(int(record["state"])),
                latex.escape(str(record["short_regime"])),
                latex.signed(100.0 * float(record["growth_natural"]), 1),
                latex.unsigned(100.0 * float(record["inflation_natural"]), 1),
                latex.unsigned(float(record["rates_natural"]), 2),
                latex.unsigned(100.0 * float(record["population_share"]), 1),
                latex.unsigned(float(record["expected_duration_months"]), 1),
            ]
        )
    return latex.tabular(
        ["", "Regime", "Growth", "Inflation", "Bill rate", "Share", "Visit"],
        rows,
        "rlrrrrr",
    )


# -------------------------------------------------- numbers typed into the prose


@dataclass(frozen=True)
class StatedNumber:
    """A decimal as the paper prints it: its sign, if any, and its digits."""

    sign: str
    digits: str

    @property
    def value(self) -> float:
        magnitude = float(self.digits)
        return -magnitude if self.sign == "-" else magnitude

    @property
    def places(self) -> int:
        return len(self.digits.split(".")[1])

    def __str__(self) -> str:
        return f"{self.sign}{self.digits}"


def stated_numbers(text: str) -> list[StatedNumber]:
    """Every signed or unsigned decimal in a text, minus signs normalised."""
    found = []
    for match in DECIMAL.finditer(text):
        sign = {"+": "+", "-": "-", "\u2212": "-"}.get(match.group(1) or "", "")
        found.append(StatedNumber(sign=sign, digits=match.group(2)))
    return found


def _paper_prose(tex: str) -> str:
    """The text whose numbers are checked: the document body, minus the skipped spans.

    The preamble holds layout lengths and package options, not claims, so checking
    starts at ``\\begin{document}`` when the text has one.
    """
    _, found, body = tex.partition("\\begin{document}")
    return NOT_CHECKED.sub(" ", body if found else tex)


def unsourced_numbers(tex: str, records: Iterable[str]) -> list[str]:
    """Decimals the paper states that no committed record contains.

    A stated number is sourced when some number in the records rounds to it at the
    precision printed, with the same sign when the paper gives one. So the paper may
    print +0.240 where a record holds +0.2401, but not +0.241, and not -0.240.
    """
    available: dict[int, set[tuple[str, str]]] = {}
    record_numbers = [number for text in records for number in stated_numbers(text)]
    unsourced = []
    for stated in stated_numbers(_paper_prose(tex)):
        places = stated.places
        if places not in available:
            available[places] = set()
            for number in record_numbers:
                if number.places >= places:
                    rounded = f"{abs(number.value):.{places}f}"
                    available[places].add((number.sign, rounded))
                    available[places].add(("", rounded))
        if (stated.sign, stated.digits) not in available[places]:
            unsourced.append(str(stated))
    return sorted(set(unsourced))


def committed_record_texts(root: Path = PROJECT_ROOT) -> list[str]:
    """The committed records a typed number may come from."""
    texts = []
    for pattern in RECORD_PATTERNS:
        for path in sorted(root.glob(pattern)):
            texts.append(path.read_text(encoding="utf-8"))
    return texts


# ------------------------------------------------------------ reading the record


@dataclass(frozen=True)
class PaperRecords:
    """Everything the paper reads from committed files, checked for consistency."""

    forecasts: pd.DataFrame
    curves: pd.DataFrame
    """Skill against R1 at every horizon, one row per forecaster and month."""
    blend_minus_chain: pd.DataFrame
    model_minus_chain: pd.DataFrame
    blend_last_horizon_with_skill: int
    model_last_horizon_with_skill: int
    submission: pd.DataFrame
    approved_configuration_hash: str


def _read_json(path: Path) -> dict[str, object]:
    import json

    if not path.is_file():
        raise PaperAssetError(f"{path} is missing. It is a committed record; restore it from git.")
    loaded: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise PaperAssetError(f"{path} is missing. It is a committed record; restore it from git.")
    return pd.read_csv(path)


def read_committed_records(
    blend_run: pd.DataFrame,
    model_alone_run: pd.DataFrame,
    approved_configuration_hash: str,
    root: Path = PROJECT_ROOT,
) -> PaperRecords:
    """Read measurement 0010's tables and the submission, and check them against the baselines.

    The one-year skill measurement 0010 committed for each forecaster must equal the
    mean skill recomputed here from the baselines, to the precision the table stores.
    That ties the curve to the forecasts behind it.
    """
    forecasts = paper_forecasts(blend_run, model_alone_run, approved_configuration_hash)
    directory = root / "research" / "reports" / "skill-at-every-horizon"
    model_run = _read_csv(directory / "skill.csv")
    blend_run_skill = _read_csv(directory / "adopted-blend" / "skill.csv")
    curves = skill_curves(model_run, blend_run_skill, "model-sample")
    one_year = skill_by_indicator(forecasts, 12).mean(axis=0)
    for forecaster in FORECASTERS:
        stored = float(
            curves[(curves["forecaster"] == forecaster) & (curves["horizon_in_months"] == 12)][
                "mean_skill"
            ].iloc[0]
        )
        if abs(stored - float(one_year[forecaster])) > 1e-6:
            raise PaperAssetError(
                f"measurement 0010 stores one-year skill {stored:+.6f} for the {forecaster}, "
                f"but the baselines give {float(one_year[forecaster]):+.6f}. The curve and the "
                "forecasts describe different runs."
            )
    blend_minus_chain = _read_csv(directory / "adopted-blend" / "blend_minus_chain.csv")
    model_minus_chain = _read_csv(directory / "model_minus_chain.csv")
    submission = _read_csv(root / "submission" / "forecasts.csv")
    manifest = _read_json(root / "submission" / "manifest.json")
    if manifest.get("configuration_hash") != approved_configuration_hash:
        raise PaperAssetError(
            f"submission/ was produced by {manifest.get('configuration_hash')}, not the approved "
            f"{approved_configuration_hash}. Re-ship, or build the paper from the shipped run."
        )
    return PaperRecords(
        forecasts=forecasts,
        curves=curves,
        blend_minus_chain=blend_minus_chain[blend_minus_chain["benchmark"] == "model-sample"],
        model_minus_chain=model_minus_chain[model_minus_chain["benchmark"] == "model-sample"],
        blend_last_horizon_with_skill=last_horizon_with_skill(
            _read_json(directory / "adopted-blend" / "summary.json"), "model-sample"
        ),
        model_last_horizon_with_skill=last_horizon_with_skill(
            _read_json(directory / "summary.json"), "model-sample"
        ),
        submission=submission,
        approved_configuration_hash=approved_configuration_hash,
    )


# ------------------------------------------------------------- the named numbers


def calibration_slope(forecasts: pd.DataFrame, forecaster: str, horizon_in_months: int) -> float:
    """Rule 0007's recalibration slope, pooled over the questions at one horizon."""
    from economic_regime_forecasting.evaluation.calibration import fit_logistic_recalibration

    rows = _at_horizon(forecasts, horizon_in_months)
    resolved = rows[np.isfinite(rows["realised_outcome"].to_numpy())]
    return fit_logistic_recalibration(
        resolved[forecaster].to_numpy(), resolved["realised_outcome"].to_numpy()
    )[1]


EPISODES: Final[tuple[tuple[str, str, str, str], ...]] = (
    (
        "InflationBeforeSurge",
        "consumer_price_inflation_above_five_percent_within_horizon",
        "2021-07-01",
        BLEND,
    ),
    (
        "InflationAverageBeforeSurge",
        "consumer_price_inflation_above_five_percent_within_horizon",
        "2021-07-01",
        AVERAGE,
    ),
    (
        "InflationAfterSurge",
        "consumer_price_inflation_above_five_percent_within_horizon",
        "2021-08-01",
        BLEND,
    ),
    ("RecessionDuringTwoThousandOne", "economy_in_recession_within_horizon", "2001-04-01", BLEND),
    ("RecessionAfterTwoThousandOne", "economy_in_recession_within_horizon", "2002-07-01", BLEND),
)
"""One-year probabilities the paper quotes from two episodes: the 2021 inflation surge,
which the forecasts met only once readings above five percent were published, and the
2001 recession, which they registered only after it had ended."""


def headline_numbers(records: PaperRecords) -> dict[str, str]:
    """The numbers the paper names rather than types, each computed from the record."""
    forecasts = records.forecasts
    curves = records.curves

    def at(forecaster: str, month: int) -> pd.Series:
        return curves[
            (curves["forecaster"] == forecaster) & (curves["horizon_in_months"] == month)
        ].iloc[0]

    numbers: dict[str, str] = {
        "BlendHorizon": str(records.blend_last_horizon_with_skill),
        "ModelHorizon": str(records.model_last_horizon_with_skill),
        "ForecastDates": str(forecasts["forecast_date"].nunique()),
        "FirstForecastMonth": forecasts["forecast_date"].min().strftime("%B %Y"),
        "LastForecastMonth": forecasts["forecast_date"].max().strftime("%B %Y"),
        "ForecastCount": f"{len(forecasts):,}",
        "ResolvedCount": f"{int(np.isfinite(forecasts['realised_outcome']).sum()):,}",
        "BlendMinusChainBelow": describe_ranges(
            month_ranges(
                records.blend_minus_chain.loc[
                    records.blend_minus_chain["upper_bound"] < 0, "horizon_in_months"
                ]
            )
        ),
        "ModelMinusChainBelow": describe_ranges(
            month_ranges(
                records.model_minus_chain.loc[
                    records.model_minus_chain["upper_bound"] < 0, "horizon_in_months"
                ]
            )
        ),
        "BlendLeadsChain": describe_ranges(
            month_ranges(
                records.blend_minus_chain.loc[
                    records.blend_minus_chain["difference"] > 0, "horizon_in_months"
                ]
            )
        ),
    }
    for name, forecaster in (("Blend", BLEND), ("Model", MODEL_ALONE), ("Chain", CHAIN)):
        for label, month in (
            ("OneMonth", 1),
            ("OneYear", 12),
            ("FiveYears", 60),
            ("TenYears", 120),
        ):
            row = at(forecaster, month)
            numbers[f"{name}Skill{label}"] = latex.signed(float(row["mean_skill"]), 3)
            numbers[f"{name}Interval{label}"] = latex.interval(
                float(row["lower_bound"]), float(row["upper_bound"]), 3
            )
        numbers[f"{name}SlopeOneYear"] = latex.unsigned(
            calibration_slope(forecasts, forecaster, 12), 3
        )
    for label, month in (("OneMonth", 1), ("OneYear", 12), ("FiveYears", 60)):
        numbers[f"IndependentObservations{label}"] = latex.unsigned(
            float(at(BLEND, month)["effective_independent_observations"]), 1
        )
    one_year = _at_horizon(forecasts, 12)
    for name, indicator, month_text, forecaster in EPISODES:
        matching = one_year[
            (one_year["indicator"] == indicator)
            & (one_year["forecast_date"] == pd.Timestamp(month_text))
        ]
        if len(matching) != 1:
            raise PaperAssetError(f"no single one-year forecast of {indicator} on {month_text}")
        numbers[name] = latex.unsigned(float(matching[forecaster].iloc[0]), 3)
    return numbers


# ---------------------------------------------------------------- writing it all


FIGURE_METADATA: Final[dict[str, object]] = {"CreationDate": None, "Producer": None}
"""No timestamps in the PDFs, so two builds of the same record are byte-identical."""


def write_paper_assets(
    records: PaperRecords,
    backtest_results: pd.DataFrame,
    regime_descriptions: pd.DataFrame,
    output_directory: Path = GENERATED_DIRECTORY,
) -> list[Path]:
    """Write every generated figure, table and named number the paper reads.

    ``backtest_results`` and ``regime_descriptions`` are the walk-forward's own
    artifacts; the backtest must carry the approved configuration hash.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from economic_regime_forecasting.reporting import paper_figures

    found = sorted({str(value) for value in backtest_results["configuration_hash"]})
    if found != [records.approved_configuration_hash]:
        raise PaperAssetError(
            f"the cached backtest carries configuration {found}, not the approved "
            f"{records.approved_configuration_hash}. Run `forecast check-gates` first."
        )
    output_directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def save_figure(name: str, figure: object) -> None:
        path = output_directory / name
        with plt.rc_context({"pdf.fonttype": 42, "svg.hashsalt": "paper"}):
            figure.savefig(path, format="pdf", metadata=FIGURE_METADATA)  # type: ignore[attr-defined]
        plt.close(figure)  # type: ignore[arg-type]
        written.append(path)

    def save_text(name: str, text: str) -> None:
        path = output_directory / name
        path.write_text(text, encoding="utf-8")
        written.append(path)

    forecasts = records.forecasts
    save_figure(
        "skill_curves.pdf",
        paper_figures.skill_curves(
            records.curves,
            {
                MODEL_ALONE: records.model_last_horizon_with_skill,
                BLEND: records.blend_last_horizon_with_skill,
            },
        ),
    )
    save_figure(
        "blend_minus_chain.pdf",
        paper_figures.difference_curve(records.blend_minus_chain, "blend minus condition chain"),
    )
    save_figure(
        "skill_by_question.pdf",
        paper_figures.skill_by_indicator(skill_by_indicator(forecasts, 12), FORECASTERS),
    )
    save_figure(
        "reliability.pdf",
        paper_figures.reliability(
            {name: reliability_table(forecasts, name, 12) for name in (MODEL_ALONE, BLEND)},
            {
                name: latex.unsigned(calibration_slope(forecasts, name, 12), 3)
                for name in (MODEL_ALONE, BLEND)
            },
        ),
    )
    save_figure(
        "forecast_timelines.pdf",
        paper_figures.forecast_timelines(
            [
                (SHORT_QUESTION_NAMES[indicator], forecast_timeline(forecasts, indicator, 12))
                for indicator in (
                    "consumer_price_inflation_above_five_percent_within_horizon",
                    "federal_funds_rate_below_one_percent_within_horizon",
                    "unemployment_rate_above_seven_percent_within_horizon",
                    "economy_in_recession_within_horizon",
                )
            ]
        ),
    )
    state_count = int(backtest_results["state_count"].iloc[0])
    levels_state_count = 4
    if state_count != 16:
        raise PaperAssetError(
            f"the cached backtest fitted {state_count} joint regimes; the paper describes 4 x 4"
        )
    chains = regime_chains(
        backtest_results, 4, levels_state_count, GROWTH_STATE_NAMES, LEVELS_STATE_NAMES
    )
    save_figure(
        "regime_chains.pdf",
        paper_figures.regime_chains(
            [
                ("Growth chain: industrial production growth", chains.growth),
                ("Levels chain: inflation and the three-month bill rate", chains.levels),
            ],
            recession_months(forecasts),
        ),
    )
    for name, text in record_texts_for_the_paper(records).items():
        save_text(name, text)
    save_text("table_regimes.tex", regime_table(regime_descriptions))
    return written


def record_texts_for_the_paper(records: PaperRecords) -> dict[str, str]:
    """Every generated table and the named numbers that need only committed records.

    Separate from the figures and the regime table, which read ``.cache/``, so a
    test can rebuild these from the repository alone and compare them with what is
    committed under ``paper/generated/``.
    """
    return {
        "table_every_month.tex": skill_curve_table(records.curves, records.blend_minus_chain),
        "table_skill_by_question.tex": indicator_skill_table(
            skill_by_indicator(records.forecasts, 12)
        ),
        "table_metrics.tex": indicator_metrics_table(indicator_metrics(records.forecasts, BLEND)),
        "table_shipped.tex": shipped_forecasts_table(records.submission),
        "numbers.tex": latex.macros(headline_numbers(records)),
    }
