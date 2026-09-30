"""The research paper's generated assets and its typed numbers are tied to the record.

Two checks run on the real repository: the tables and named numbers committed under
``paper/generated/`` are exactly what the committed records give, and every decimal
the paper's prose states appears in a committed record at the precision printed.
The rest pin the machinery on small synthetic frames.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from matplotlib.figure import Figure

from economic_regime_forecasting import research_paper
from economic_regime_forecasting.configuration.shipping_approval import (
    CONFIGURATION_HASH_APPROVED_FOR_SHIPPING,
)
from economic_regime_forecasting.evaluation.scoring import brier_skill_score
from economic_regime_forecasting.regression_baseline import read_baseline_forecasts
from economic_regime_forecasting.reporting import latex, paper_figures

BLEND_HASH = "blendblendblend0"


def _baselines(dates: int = 24, seed: int = 7) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A blend baseline and a model-alone baseline over the ten questions."""
    generator = np.random.default_rng(seed)
    rows = []
    for indicator in research_paper.SHORT_QUESTION_NAMES:
        for month in pd.date_range("2000-01-01", periods=dates, freq="MS"):
            model = float(generator.uniform(0.05, 0.95))
            chain = float(generator.uniform(0.05, 0.95))
            rows.append(
                {
                    "indicator": indicator,
                    "forecast_date": month,
                    "horizon_months": 12,
                    "model": model,
                    "chain": chain,
                    "realised_outcome": float(generator.integers(0, 2)),
                    "climatology_probability": float(generator.uniform(0.2, 0.6)),
                    "model_sample_climatology_probability": float(generator.uniform(0.2, 0.6)),
                }
            )
    frame = pd.DataFrame(rows)
    shared = [
        "indicator",
        "forecast_date",
        "horizon_months",
        "realised_outcome",
        "climatology_probability",
        "model_sample_climatology_probability",
    ]
    blend = frame[shared].assign(
        predicted_probability=0.5 * frame["model"] + 0.5 * frame["chain"],
        condition_chain_probability=frame["chain"],
        configuration_hash=BLEND_HASH,
    )
    model_alone = frame[shared].assign(
        predicted_probability=frame["model"],
        condition_chain_probability=frame["chain"],
        configuration_hash=research_paper.MODEL_ALONE_CONFIGURATION_HASH,
    )
    return blend, model_alone


# ------------------------------------------------------------------ LaTeX output


def test_signed_numbers_print_their_sign_and_never_a_negative_zero() -> None:
    assert latex.signed(-0.056, 3) == "$-0.056$"
    assert latex.signed(0.24, 3) == "$+0.240$"
    assert latex.signed(-0.0004, 3) == "$+0.000$"
    assert latex.interval(-0.1, 0.2, 2) == "[$-0.10$, $+0.20$]"


def test_plain_text_is_escaped_before_it_reaches_latex() -> None:
    assert latex.escape("Inflation above 5% & rising_fast") == (
        r"Inflation above 5\% \& rising\_fast"
    )


def test_a_named_number_must_be_a_name_latex_can_read() -> None:
    assert r"\newcommand{\BlendHorizon}{46}" in latex.macros({"BlendHorizon": "46"})
    for unreadable in ("Blend_Horizon", "Horizon46", "blend-horizon"):
        with pytest.raises(latex.LatexError):
            latex.macros({unreadable: "46"})


def test_a_table_refuses_a_row_with_the_wrong_number_of_cells() -> None:
    with pytest.raises(latex.LatexError, match="row 1 has 1 cells"):
        latex.tabular(["a", "b"], [["1", "2"], ["3"]], "rr")


def test_a_long_table_must_carry_its_own_caption_and_label() -> None:
    with pytest.raises(latex.LatexError):
        latex.tabular(["a"], [["1"]], "r", long=True)
    text = latex.tabular(["a"], [["1"]], "r", long=True, caption="c", label="tab:x")
    assert r"\begin{longtable}{r}" in text and r"\label{tab:x}" in text


# --------------------------------------------------------- numbers typed in prose


def test_a_stated_number_is_sourced_when_a_record_rounds_to_it() -> None:
    records = ["skill +0.2401 [+0.1715, +0.3113]"]
    assert research_paper.unsourced_numbers("skill of $+0.240$ and 0.24", records) == []


def test_a_stated_number_with_the_wrong_sign_is_not_sourced() -> None:
    records = ["the difference is \N{MINUS SIGN}0.0582"]
    assert research_paper.unsourced_numbers("$-0.058$", records) == []
    assert research_paper.unsourced_numbers("$+0.058$", records) == ["+0.058"]


def test_a_number_no_record_contains_is_reported() -> None:
    assert research_paper.unsourced_numbers("a slope of 0.871", ["slope 0.870"]) == ["0.871"]


def test_a_number_more_precise_than_its_record_is_not_sourced() -> None:
    assert research_paper.unsourced_numbers("0.8700", ["slope 0.870"]) == ["0.8700"]


def test_derived_numbers_citations_and_comments_are_not_checked() -> None:
    tex = "about \\derived{0.33} of it \\citep[p.~3.5]{key} % 9.99 in a comment\n"
    assert research_paper.unsourced_numbers(tex, []) == []


def test_layout_lengths_are_not_checked_but_prose_beside_a_unit_word_is() -> None:
    tex = "\\begin{tabular}{p{0.46\\linewidth}} \\vspace{1.5em} a weight of 0.5 in each"
    assert research_paper.unsourced_numbers(tex, []) == ["0.5"]


def test_the_preamble_is_not_checked_but_the_body_is() -> None:
    tex = "\\geometry{margin=2.54cm}\n\\begin{document}\nskill 0.24\n\\end{document}"
    assert research_paper.unsourced_numbers(tex, []) == ["0.24"]


# ---------------------------------------------------------------- the forecasts


def test_the_paper_reads_the_blend_and_the_model_alone_side_by_side() -> None:
    blend, model_alone = _baselines()
    forecasts = research_paper.paper_forecasts(blend, model_alone, BLEND_HASH)
    assert len(forecasts) == len(blend)
    assert np.allclose(
        forecasts[research_paper.BLEND],
        0.5 * forecasts[research_paper.MODEL_ALONE] + 0.5 * forecasts[research_paper.CHAIN],
    )


def test_the_paper_refuses_a_blend_that_is_not_half_model_and_half_chain() -> None:
    blend, model_alone = _baselines()
    blend.loc[3, "predicted_probability"] += 0.01
    with pytest.raises(research_paper.PaperAssetError, match="half the regime model"):
        research_paper.paper_forecasts(blend, model_alone, BLEND_HASH)


def test_the_paper_refuses_baselines_from_the_wrong_configuration() -> None:
    blend, model_alone = _baselines()
    with pytest.raises(research_paper.PaperAssetError, match="expected"):
        research_paper.paper_forecasts(blend, model_alone, "someotherconfig0")


def test_the_paper_refuses_baselines_whose_references_differ() -> None:
    blend, model_alone = _baselines()
    model_alone.loc[5, "model_sample_climatology_probability"] += 0.1
    with pytest.raises(research_paper.PaperAssetError, match="not captured on the same data"):
        research_paper.paper_forecasts(blend, model_alone, BLEND_HASH)


def test_skill_by_question_is_the_brier_skill_score_of_each_question() -> None:
    blend, model_alone = _baselines()
    forecasts = research_paper.paper_forecasts(blend, model_alone, BLEND_HASH)
    table = research_paper.skill_by_indicator(forecasts, 12)
    assert list(table.index) == list(research_paper.SHORT_QUESTION_NAMES.values())
    indicator, short_name = next(iter(research_paper.SHORT_QUESTION_NAMES.items()))
    rows = forecasts[forecasts["indicator"] == indicator]
    expected = brier_skill_score(
        rows[research_paper.BLEND].to_numpy(),
        rows["realised_outcome"].to_numpy(),
        rows[research_paper.AVERAGE].to_numpy(),
    )
    assert table.loc[short_name, research_paper.BLEND] == pytest.approx(expected)


def test_recession_months_are_read_off_the_one_year_outcomes() -> None:
    blend, model_alone = _baselines(dates=3)
    forecasts = research_paper.paper_forecasts(blend, model_alone, BLEND_HASH)
    recession = forecasts["indicator"] == "economy_in_recession_at_horizon_date"
    forecasts.loc[recession, "realised_outcome"] = [0.0, 1.0, 0.0]
    assert list(research_paper.recession_months(forecasts)) == [pd.Timestamp("2001-02-01")]


# ------------------------------------------------------- the curve and the regimes


def test_consecutive_months_collapse_into_ranges() -> None:
    ranges = research_paper.month_ranges([1, 2, 3, 8, 114, 115, 120])
    assert ranges == [(1, 3), (8, 8), (114, 115), (120, 120)]
    assert research_paper.describe_ranges(ranges) == "1--3, 8, 114--115 and 120"
    assert research_paper.describe_ranges([]) == "none"


def test_the_two_runs_must_score_the_chain_identically() -> None:
    table = pd.DataFrame(
        {
            "horizon_in_months": [1, 1],
            "forecaster": ["regime model", "condition chain"],
            "benchmark": ["model-sample", "model-sample"],
            "mean_skill": [0.3, 0.5],
        }
    )
    changed = table.copy()
    changed.loc[1, "mean_skill"] = 0.4
    with pytest.raises(research_paper.PaperAssetError, match="differently"):
        research_paper.skill_curves(table, changed, "model-sample")
    curves = research_paper.skill_curves(table, table.copy(), "model-sample")
    assert sorted(curves["forecaster"]) == sorted(research_paper.FORECASTERS)


def test_each_chain_is_the_marginal_of_the_joint_regime_distribution() -> None:
    joint = np.arange(1, 17, dtype="float64")
    joint /= joint.sum()
    results = pd.DataFrame(
        {
            "indicator": ["a", "a"],
            "horizon_months": [12, 12],
            "forecast_date": pd.to_datetime(["2000-01-01", "2000-02-01"]),
            "regime_distribution": [",".join(f"{value:.6f}" for value in joint)] * 2,
        }
    )
    chains = research_paper.regime_chains(
        results,
        4,
        4,
        research_paper.GROWTH_STATE_NAMES,
        research_paper.LEVELS_STATE_NAMES,
    )
    grid = joint.reshape(4, 4)
    assert np.allclose(chains.growth.iloc[0].to_numpy(), grid.sum(axis=1), atol=1e-6)
    assert np.allclose(chains.levels.iloc[0].to_numpy(), grid.sum(axis=0), atol=1e-6)


# ---------------------------------------------------------------------- figures


def test_every_paper_figure_is_drawn_from_values_alone() -> None:
    months = np.arange(1, 121)
    curves = pd.concat(
        [
            pd.DataFrame(
                {
                    "horizon_in_months": months,
                    "forecaster": name,
                    "mean_skill": np.linspace(0.4, -0.1, months.size),
                    "lower_bound": np.linspace(0.3, -0.2, months.size),
                    "upper_bound": np.linspace(0.5, 0.0, months.size),
                    "informative": months <= 60,
                }
            )
            for name in research_paper.FORECASTERS
        ]
    )
    differences = curves[curves["forecaster"] == research_paper.BLEND].rename(
        columns={"mean_skill": "difference"}
    )
    blend, model_alone = _baselines()
    forecasts = research_paper.paper_forecasts(blend, model_alone, BLEND_HASH)
    reliability = research_paper.reliability_table(forecasts, research_paper.BLEND, 12)
    timeline = research_paper.forecast_timeline(
        forecasts, "economy_in_recession_within_horizon", 12
    )
    chain = pd.DataFrame(
        {"state 1": [1.0, 0.0], "state 2": [0.0, 1.0]},
        index=pd.to_datetime(["2000-01-01", "2000-02-01"]),
    )
    figures = [
        paper_figures.skill_curves(curves, {research_paper.BLEND: 46}),
        paper_figures.difference_curve(differences, "blend minus chain"),
        paper_figures.skill_by_indicator(
            research_paper.skill_by_indicator(forecasts, 12), research_paper.FORECASTERS
        ),
        paper_figures.reliability({research_paper.BLEND: reliability}, {research_paper.BLEND: "1"}),
        paper_figures.forecast_timelines([("Recession, any time", timeline)]),
        paper_figures.regime_chains([("growth", chain)], pd.DatetimeIndex([])),
    ]
    assert all(isinstance(figure, Figure) for figure in figures)


# ------------------------------------------------------------- the real record


@pytest.fixture(scope="module")
def committed_records() -> research_paper.PaperRecords:
    return research_paper.read_committed_records(
        read_baseline_forecasts(research_paper.BLEND_BASELINE),
        read_baseline_forecasts(research_paper.MODEL_ALONE_BASELINE),
        CONFIGURATION_HASH_APPROVED_FOR_SHIPPING,
    )


def test_the_committed_tables_and_numbers_are_what_the_record_gives(
    committed_records: research_paper.PaperRecords,
) -> None:
    for name, text in research_paper.record_texts_for_the_paper(committed_records).items():
        committed = (research_paper.GENERATED_DIRECTORY / name).read_text(encoding="utf-8")
        assert committed == text, (
            f"paper/generated/{name} is stale: run `forecast paper-assets` and commit the result"
        )


def test_every_decimal_the_paper_states_is_in_a_committed_record() -> None:
    tex = (research_paper.PAPER_DIRECTORY / "main.tex").read_text(encoding="utf-8")
    unsourced = research_paper.unsourced_numbers(tex, research_paper.committed_record_texts())
    assert unsourced == [], (
        "these numbers in paper/main.tex appear in no committed record at the precision "
        f"printed: {unsourced}. Correct them, or mark arithmetic done in the text "
        "with \\derived{}"
    )
