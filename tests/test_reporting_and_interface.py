"""Figures render, and the command line surface dispatches where it says it does.

Figures get smoke tests rather than pixel comparisons: the useful question is
whether every chart builds from the shapes the pipeline actually produces, since
a figure that raises at the end of a forty-minute run is the expensive failure.
"""

from __future__ import annotations

import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg")

from economic_regime_forecasting.command_line_interface import build_parser
from economic_regime_forecasting.reporting import figures


@pytest.fixture(autouse=True)
def close_figures():  # type: ignore[no-untyped-def]
    yield
    import matplotlib.pyplot as plt

    plt.close("all")


def _regime_table(regimes: int = 5) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "state": range(regimes),
            "regime": [f"regime {index}" for index in range(regimes)],
            "growth_natural": np.linspace(-0.02, 0.05, regimes),
            "inflation_natural": np.linspace(0.01, 0.09, regimes),
            "rates_natural": np.linspace(0.5, 9.0, regimes),
            "population_share": np.full(regimes, 1.0 / regimes),
            "expected_duration_months": np.linspace(19, 42, regimes),
        }
    )


def test_the_series_panel_builds_for_an_odd_number_of_series() -> None:
    """Nine series into three columns leaves blanks that must be hidden, not empty
    axes with ticks on them."""
    index = pd.date_range("1990-01-01", periods=120, freq="MS")
    series = {
        f"series_{number}": pd.Series(np.random.default_rng(number).normal(size=120), index=index)
        for number in range(9)
    }
    figure = figures.plot_series_panel(series)
    visible = [axes for axes in figure.axes if axes.get_visible()]
    assert len(visible) == 9


def test_regime_probabilities_render_with_recessions_shaded() -> None:
    dates = pd.date_range("1960-01-01", periods=240, freq="MS")
    generator = np.random.default_rng(1)
    probabilities = generator.dirichlet(np.ones(5), size=240)
    recession = pd.Series((generator.uniform(size=240) < 0.15).astype("float64"), index=dates)
    figure = figures.plot_regime_probabilities(
        dates, probabilities, [f"regime {index}" for index in range(5)], recession
    )
    assert figure.axes[0].get_ylim() == (0.0, 1.0)
    assert figure.axes[0].get_legend() is not None


def test_regime_probabilities_render_without_a_recession_series() -> None:
    dates = pd.date_range("1960-01-01", periods=60, freq="MS")
    probabilities = np.random.default_rng(2).dirichlet(np.ones(3), size=60)
    figures.plot_regime_probabilities(dates, probabilities, ["a", "b", "c"], None)


def test_regime_means_render_one_panel_per_dimension() -> None:
    figure = figures.plot_regime_means(_regime_table())
    assert len(figure.axes) == 3


def test_the_mixing_chart_marks_the_threshold() -> None:
    table = pd.DataFrame(
        {
            "horizon_months": [12, 60, 120],
            "horizon_years": [1, 5, 10],
            "mean_distance_to_stationary": [0.50, 0.15, 0.05],
            "largest_distance_to_stationary": [0.69, 0.32, 0.13],
            "smallest_distance_to_stationary": [0.24, 0.05, 0.01],
            "carries_information": [True, True, False],
        }
    )
    figure = figures.plot_mixing(table, threshold=0.05)
    labels = [text.get_text() for text in figure.axes[0].get_legend().get_texts()]
    assert any("threshold" in label for label in labels)


def test_reliability_diagrams_render_one_panel_per_horizon() -> None:
    tables = {
        horizon: pd.DataFrame(
            {
                "lower_edge": np.linspace(0, 0.9, 10),
                "upper_edge": np.linspace(0.1, 1.0, 10),
                "count": np.full(10, 40),
                "mean_forecast": np.linspace(0.05, 0.95, 10),
                "observed_rate": np.linspace(0.05, 0.95, 10),
                "standard_error": np.full(10, 0.05),
            }
        )
        for horizon in (12, 60, 120)
    }
    figure = figures.plot_reliability(tables, {12: 0.02, 60: 0.05, 120: 0.09})
    assert len(figure.axes) == 3


def _metrics() -> pd.DataFrame:
    names = [f"indicator_{number}" for number in range(10)]
    rows = []
    for horizon in (12, 60, 120):
        for position, name in enumerate(names):
            rows.append(
                {
                    "indicator": name,
                    "horizon_months": horizon,
                    "brier_skill_score": (position - 5) / 50.0,
                }
            )
    return pd.DataFrame(rows)


def test_skill_by_indicator_colours_positive_and_negative_apart() -> None:
    """Skill has a meaningful zero, so it gets a diverging pair rather than a
    categorical hue that would imply the indicators are the identity."""
    figure = figures.plot_skill_by_indicator(_metrics(), 12)
    colours = {patch.get_facecolor() for patch in figure.axes[0].patches}
    assert len(colours) == 2


def test_skill_by_horizon_labels_the_verdict_under_each_point() -> None:
    verdicts = pd.DataFrame(
        {
            "horizon_months": [12, 60, 120],
            "horizon_years": [1, 5, 10],
            "verdict": ["SHIP MODEL", "SHIP MODEL", "SHIP BASE RATE"],
            "mean_brier_skill_score": [0.09, 0.03, -0.01],
            "skill_lower_bound": [0.04, -0.01, -0.08],
            "skill_upper_bound": [0.14, 0.07, 0.05],
            "effective_independent_observations": [54.0, 10.8, 5.4],
            "failing_gates": ["none", "none", "honesty"],
        }
    )
    figure = figures.plot_skill_by_horizon(verdicts)
    labels = [text.get_text() for text in figure.axes[0].get_xticklabels()]
    assert "10 year\nSHIP BASE RATE" in labels


# ------------------------------------------------------- command line surface


def test_every_stage_has_a_subcommand() -> None:
    parser = build_parser()
    for command in (
        "fetch-data",
        "audit-data",
        "fit-regimes",
        "forecast-now",
        "backtest",
        "evaluate",
        "submit",
        "check-gates",
    ):
        assert parser.parse_args([command]).command == command


def test_a_run_can_pretend_today_is_an_earlier_date() -> None:
    from datetime import date

    arguments = build_parser().parse_args(["--as-of", "1990-01-01", "backtest"])
    assert arguments.as_of == date(1990, 1, 1)


def test_the_default_worker_count_is_deliberately_small() -> None:
    """Raising it does not make the fetch faster and can earn a block."""
    assert build_parser().parse_args(["fetch-data"]).workers == 2


def test_a_command_is_required() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([])
