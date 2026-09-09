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


def _display_table(regimes: int = 5) -> pd.DataFrame:
    """The shape reporting.tables.regime_display_table produces."""
    return pd.DataFrame(
        {
            "state": range(regimes),
            "regime": [f"regime {index}" for index in range(regimes)],
            "growth %/yr": np.linspace(-1.5, 6.1, regimes),
            "inflation %/yr": np.linspace(2.1, 9.6, regimes),
            "rates %": np.linspace(0.6, 9.4, regimes),
            "share of months": [f"{100 // regimes}%"] * regimes,
            "typical visit": [f"{months} months" for months in range(19, 19 + regimes)],
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


def test_the_timeline_gives_every_regime_its_own_lane() -> None:
    """A stacked area sits pinned at one wherever the model is confident, which is
    almost everywhere, so it spends the whole vertical axis saying so. Lanes make
    each regime's episodes directly readable."""
    dates = pd.date_range("1960-01-01", periods=240, freq="MS")
    generator = np.random.default_rng(1)
    probabilities = generator.dirichlet(np.ones(5), size=240)
    recession = pd.Series((generator.uniform(size=240) < 0.15).astype("float64"), index=dates)
    figure = figures.plot_regime_timeline(
        dates, probabilities, [f"regime {index}" for index in range(5)], recession
    )
    assert len(figure.axes) == 5


def test_the_timeline_names_each_regime_beside_its_lane_not_in_a_legend() -> None:
    dates = pd.date_range("1960-01-01", periods=60, freq="MS")
    probabilities = np.random.default_rng(2).dirichlet(np.ones(3), size=60)
    figure = figures.plot_regime_timeline(dates, probabilities, ["alpha", "beta", "gamma"], None)
    printed = " ".join(text.get_text() for axes in figure.axes for text in axes.texts)
    for name in ("alpha", "beta", "gamma"):
        assert name in printed
    assert all(axes.get_legend() is None for axes in figure.axes)


def test_the_regime_map_places_every_regime_and_labels_it() -> None:
    """One chart carrying all three dimensions beats three panels in three unit
    systems, which forced a reader to look across all of them to assemble a single
    regime's identity."""
    figure = figures.plot_regime_map(_display_table())
    labels = " ".join(text.get_text() for text in figure.axes[0].texts)
    for index in range(5):
        assert f"regime {index}" in labels


def test_regime_map_labels_do_not_land_on_top_of_each_other() -> None:
    """Two of the real regimes sit close together, so placement is checked rather
    than assumed."""
    crowded = _display_table()
    crowded.loc[2, "growth %/yr"] = crowded.loc[3, "growth %/yr"] + 0.05
    crowded.loc[2, "inflation %/yr"] = crowded.loc[3, "inflation %/yr"] + 0.05
    figure = figures.plot_regime_map(crowded)
    positions = [text.get_position() for text in figure.axes[0].texts]
    for first in range(len(positions)):
        for second in range(first + 1, len(positions)):
            assert positions[first] != positions[second]


def test_the_transition_heatmap_prints_every_cell() -> None:
    matrix = np.array([[0.9, 0.1], [0.2, 0.8]])
    figure = figures.plot_transition_heatmap(matrix, ["calm", "turbulent"])
    printed = {text.get_text() for text in figure.axes[0].texts}
    assert {"0.900", "0.100", "0.200", "0.800"} <= printed


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


# ------------------------------------------------------- reader-facing tables


def test_a_log_change_is_converted_to_a_rate_a_reader_recognises() -> None:
    """A year-over-year log change of 0.092 is 9.6 percent a year, not 9.2. The
    exponential matters once the rate is large, which for the stagflation regime
    it is."""
    from economic_regime_forecasting.configuration.registry import Transform
    from economic_regime_forecasting.reporting.tables import to_percent_per_year

    assert to_percent_per_year(0.092, Transform.YEAR_OVER_YEAR_LOG_CHANGE) == pytest.approx(
        9.636, abs=0.01
    )
    assert to_percent_per_year(4.57, Transform.LEVEL) == pytest.approx(4.57)


def test_the_regime_table_puts_every_column_in_a_named_unit() -> None:
    """The defect this fixes: growth printed as 0.034 beside an interest rate
    printed as 4.57, inviting a comparison between two different scales."""
    from economic_regime_forecasting.configuration.registry import load_registries
    from economic_regime_forecasting.models.state_labelling import RegimeDescription
    from economic_regime_forecasting.reporting.tables import regime_display_table

    registry, _ = load_registries()
    described = [
        RegimeDescription(
            state=index,
            label="a regime",
            standardised_means=(0.1, 0.2, 0.3),
            natural_means=(0.034, 0.092, 4.57),
            population_share=0.2,
            expected_duration_in_months=30.0,
        )
        for index in range(2)
    ]
    table = regime_display_table(described, registry)
    assert "growth %/yr" in table.columns
    assert "rates %" in table.columns
    assert table["growth %/yr"].iloc[0] == pytest.approx(3.46, abs=0.01)
    assert table["rates %"].iloc[0] == pytest.approx(4.57)
    assert table["share of months"].iloc[0] == "20%"


def test_a_one_state_model_shows_no_visit_length_rather_than_a_huge_one() -> None:
    """A single state never leaves, so its expected visit is the sample length.
    Printing 1e12 months is noise; printing nothing says it does not apply."""
    from economic_regime_forecasting.reporting.tables import sweep_display_table

    sweep = pd.DataFrame(
        {
            "states": [1, 2],
            "free_parameters": [9, 21],
            "bayesian_information_criterion": [5635.0, 4510.0],
            "held_out_log_likelihood_per_month": [-4.3, -3.7],
            "smallest_population_share": [1.0, 0.44],
            "shortest_expected_duration_months": [1e12, 39.9],
            "admissible": [True, True],
        }
    )
    view = sweep_display_table(sweep)
    assert view["shortest visit"].iloc[0] == ""
    assert view["shortest visit"].iloc[1] == "40 months"


def test_the_forecast_grid_reads_as_percentages_by_horizon() -> None:
    from economic_regime_forecasting.reporting.tables import forecast_display_table

    forecasts = pd.DataFrame(
        {
            "indicator": ["a", "a", "b", "b"],
            "horizon_months": [12, 120, 12, 120],
            "probability": [0.083, 0.694, 0.5, 0.25],
        }
    )
    grid = forecast_display_table(forecasts)
    assert list(grid.columns) == ["1 year", "10 year"]
    assert grid.loc["a", "1 year"] == pytest.approx(8.3)
