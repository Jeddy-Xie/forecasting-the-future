"""Figures for the notebooks. Presentation only; nothing here computes a result.

Every function takes numbers that were computed elsewhere and returns a figure.
That separation is what keeps a chart from quietly becoming the only place a
calculation lives.

Colour follows the job it does rather than the order things happen to be in.
Regimes are an identity, so they get a fixed categorical order that never
re-assigns when a regime is added or dropped. Skill scores have a meaningful
zero, so they get a diverging pair around a neutral midpoint. Nothing uses a
rainbow, nothing uses two vertical scales, and every chart with more than one
series carries a legend so identity never rests on colour alone.
"""

from __future__ import annotations

from collections.abc import Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Patch

# A fixed categorical order, validated for colour-vision deficiency separation
# against a light surface. Slots are assigned by position and never cycled.
REGIME_COLOURS: tuple[str, ...] = (
    "#2a78d6",  # blue
    "#eb6834",  # orange
    "#1baf7a",  # aqua
    "#eda100",  # yellow
    "#e87ba4",  # magenta
    "#4a3aa7",  # violet
)
POSITIVE_COLOUR = "#2a78d6"
NEGATIVE_COLOUR = "#e34948"
NEUTRAL_INK = "#52514e"
GRID_INK = "#d8d7d2"
RECESSION_SHADE = "#dedddc"
SURFACE = "#fcfcfb"


def _style(axes: Axes, title: str, ylabel: str = "", xlabel: str = "") -> None:
    """Recessive grid and axes; the data is the only thing with weight."""
    axes.set_title(title, fontsize=11, color="#0b0b0b", loc="left", pad=10)
    if ylabel:
        axes.set_ylabel(ylabel, fontsize=9, color=NEUTRAL_INK)
    if xlabel:
        axes.set_xlabel(xlabel, fontsize=9, color=NEUTRAL_INK)
    axes.grid(True, color=GRID_INK, linewidth=0.6, alpha=0.8)
    axes.set_axisbelow(True)
    for side in ("top", "right"):
        axes.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axes.spines[side].set_color(GRID_INK)
    axes.tick_params(colors=NEUTRAL_INK, labelsize=9)


def _new_figure(width: float, height: float) -> tuple[Figure, Axes]:
    figure, axes = plt.subplots(figsize=(width, height), facecolor=SURFACE)
    axes.set_facecolor(SURFACE)
    return figure, axes


def plot_series_panel(series_by_name: dict[str, pd.Series], columns: int = 3) -> Figure:
    """One small multiple per economic series. Single line each, so no legend."""
    rows = int(np.ceil(len(series_by_name) / columns))
    figure, grid = plt.subplots(
        rows, columns, figsize=(4.6 * columns, 2.6 * rows), facecolor=SURFACE
    )
    flattened = np.atleast_1d(grid).ravel()
    for axes, (name, series) in zip(flattened, series_by_name.items(), strict=False):
        axes.set_facecolor(SURFACE)
        axes.plot(series.index, series.to_numpy(), linewidth=1.2, color=POSITIVE_COLOUR)
        _style(axes, name.replace("_", " "))
    for axes in flattened[len(series_by_name) :]:
        axes.set_visible(False)
    figure.tight_layout()
    return figure


def plot_regime_timeline(
    dates: pd.DatetimeIndex,
    state_probabilities: np.ndarray,
    regime_labels: Sequence[str],
    recession_flag: pd.Series | None = None,
) -> Figure:
    """One lane per regime, filled where that regime was active.

    This replaces a stacked area, which was the obvious choice and the wrong one.
    The model is confident almost everywhere, so the stack sat pinned at one and
    spent the entire vertical axis saying so, leaving a solid block of switching
    colour that could only be read by looking away to a five-item legend for every
    band. Giving each regime its own lane costs vertical space and buys three
    things: each regime's episodes are directly visible, the name sits beside the
    data instead of in a legend, and recessions can be shaded behind rather than
    hidden underneath.
    """
    regime_count = state_probabilities.shape[1]
    figure = plt.figure(figsize=(11.5, 0.78 * regime_count + 0.9), facecolor=SURFACE)
    axes_list: list[Axes] = list(figure.subplots(regime_count, 1, sharex=True, squeeze=False)[:, 0])
    figure.subplots_adjust(hspace=0.32)

    recession = (
        recession_flag.reindex(dates).fillna(0.0).to_numpy() if recession_flag is not None else None
    )

    for state, axes in enumerate(axes_list):
        axes.set_facecolor(SURFACE)
        if recession is not None:
            axes.fill_between(
                dates,
                0,
                1,
                where=recession > 0.5,
                color=RECESSION_SHADE,
                linewidth=0,
                zorder=0,
            )
        axes.fill_between(
            dates,
            0,
            state_probabilities[:, state],
            color=REGIME_COLOURS[state % len(REGIME_COLOURS)],
            linewidth=0,
            zorder=2,
        )
        axes.set_ylim(0, 1)
        axes.set_yticks([])
        axes.margins(x=0)
        for side in ("top", "right", "left"):
            axes.spines[side].set_visible(False)
        axes.spines["bottom"].set_color(GRID_INK)
        axes.tick_params(colors=NEUTRAL_INK, labelsize=9)
        axes.text(
            -0.012,
            0.5,
            f"{state}  {regime_labels[state]}",
            transform=axes.transAxes,
            ha="right",
            va="center",
            fontsize=9,
            color="#0b0b0b",
        )

    axes_list[0].set_title(
        "When each regime was active", fontsize=11, color="#0b0b0b", loc="left", pad=10
    )
    if recession is not None:
        axes_list[-1].set_xlabel(
            "shaded bands are recessions dated by the National Bureau of Economic Research",
            fontsize=8.5,
            color=NEUTRAL_INK,
            labelpad=8,
        )
    figure.tight_layout()
    return figure


def plot_regime_map(display_table: pd.DataFrame) -> Figure:
    """Where each regime sits in inflation and growth, sized by how common it is.

    This replaces three separate bar panels, one per dimension, which forced a
    reader to look across all three to assemble a single regime's identity and
    printed growth in log units beside an interest rate in percent. Position on two
    axes carries the same information at a glance, and the interest rate rides
    along as a label because it is the third dimension of a point already placed by
    the other two.
    """
    figure, axes = _new_figure(8.4, 5.6)
    inflation = display_table.iloc[:, 3].to_numpy(dtype="float64")
    growth = display_table.iloc[:, 2].to_numpy(dtype="float64")
    rates = display_table.iloc[:, 4].to_numpy(dtype="float64")
    shares = np.array(
        [float(str(value).rstrip("%")) / 100.0 for value in display_table["share of months"]]
    )

    axes.axhline(0.0, color=NEUTRAL_INK, linewidth=1.0, zorder=1)
    axes.text(
        axes.get_xlim()[0],
        0,
        " output contracting below this line ",
        fontsize=8,
        color=NEUTRAL_INK,
        va="bottom",
        ha="left",
        zorder=1,
    )

    # Two regimes sit close together in this space, so labels are placed by trying
    # four positions around each point and taking the first that does not overlap a
    # label already placed. Five points make this cheap, and a collision here is
    # the difference between a chart that reads and one that has to be decoded.
    x_span = max(inflation.max() - inflation.min(), 1e-6)
    y_span = max(growth.max() - growth.min(), 1e-6)
    label_width, label_height = 0.46 * x_span, 0.17 * y_span
    placed: list[tuple[float, float]] = []

    def _free(centre: tuple[float, float]) -> bool:
        return all(
            abs(centre[0] - other[0]) > label_width * 0.85
            or abs(centre[1] - other[1]) > label_height * 0.95
            for other in placed
        )

    for index in range(len(display_table)):
        colour = REGIME_COLOURS[index % len(REGIME_COLOURS)]
        share = shares[index]
        axes.scatter(
            inflation[index],
            growth[index],
            s=260 + 5200 * share,
            color=colour,
            alpha=0.42,
            linewidth=0,
            zorder=2,
        )
        axes.scatter(
            inflation[index],
            growth[index],
            s=52,
            color=colour,
            edgecolor=SURFACE,
            linewidth=1.4,
            zorder=3,
        )

        radius = 0.055 * y_span + 0.10 * share * y_span
        candidates = [
            (inflation[index], growth[index] - radius - label_height * 0.75),
            (inflation[index], growth[index] + radius + label_height * 0.75),
            (inflation[index] + label_width * 0.62, growth[index]),
            (inflation[index] - label_width * 0.62, growth[index]),
        ]
        centre = next((spot for spot in candidates if _free(spot)), candidates[0])
        placed.append(centre)
        axes.annotate(
            f"{display_table['state'].iloc[index]}  "
            f"{display_table['regime'].iloc[index]}\n"
            f"short rate {rates[index]:.1f}%  ·  "
            f"{display_table['share of months'].iloc[index]} of months",
            centre,
            ha="center",
            va="center",
            fontsize=8.5,
            color="#0b0b0b",
            zorder=4,
        )

    axes.margins(0.34)
    _style(
        axes,
        "The five regimes, placed by what they felt like",
        ylabel="output growth, percent a year",
        xlabel="inflation, percent a year",
    )
    figure.tight_layout()
    return figure


def plot_transition_heatmap(transition_matrix: np.ndarray, regime_labels: Sequence[str]) -> Figure:
    """The month-to-month switching probabilities as a grid rather than a table.

    Twenty-five numbers are hard to compare by reading. Shading them makes the
    strong diagonal, which is the whole reason these are regimes, visible before
    any number is read. Every cell is still printed, because the exact value is
    what a reader checks once the shape has told them where to look.
    """
    count = transition_matrix.shape[0]
    figure, axes = _new_figure(7.6, 5.4)
    axes.imshow(transition_matrix, cmap="Blues", vmin=0.0, vmax=1.0, aspect="auto")

    for row in range(count):
        for column in range(count):
            value = transition_matrix[row, column]
            axes.text(
                column,
                row,
                f"{value:.3f}",
                ha="center",
                va="center",
                fontsize=9,
                color=SURFACE if value > 0.5 else "#0b0b0b",
            )
    axes.set_xticks(range(count), [str(index) for index in range(count)], fontsize=9)
    axes.set_yticks(
        range(count),
        [f"{index}  {regime_labels[index]}" for index in range(count)],
        fontsize=9,
    )
    axes.set_xlabel("regime next month", fontsize=9, color=NEUTRAL_INK)
    axes.set_title(
        "Where the economy goes next month", fontsize=11, color="#0b0b0b", loc="left", pad=10
    )
    axes.tick_params(colors=NEUTRAL_INK, length=0)
    for side in ("top", "right", "bottom", "left"):
        axes.spines[side].set_visible(False)
    figure.tight_layout()
    return figure


def plot_mixing(mixing_table: pd.DataFrame, threshold: float) -> Figure:
    """How far each horizon's projection still is from the long-run distribution.

    The single most important chart in the project: where this curve crosses the
    threshold is the horizon beyond which the model has nothing to add.
    """
    figure, axes = _new_figure(7.0, 4.0)
    horizons = mixing_table["horizon_months"].to_numpy()

    axes.fill_between(
        horizons,
        mixing_table["smallest_distance_to_stationary"],
        mixing_table["largest_distance_to_stationary"],
        color=POSITIVE_COLOUR,
        alpha=0.14,
        linewidth=0,
        label="range across forecast dates",
    )
    # A marker per point reads as "measured here" and is right for a handful of
    # sampled horizons. Since D11 the curve is computed every month, where 240
    # markers would hide the line they sit on.
    dense = len(horizons) > 24
    axes.plot(
        horizons,
        mixing_table["mean_distance_to_stationary"],
        linewidth=2.0,
        color=POSITIVE_COLOUR,
        marker=None if dense else "o",
        markersize=6,
        label="mean across forecast dates",
    )
    axes.axhline(
        threshold,
        color=NEGATIVE_COLOUR,
        linewidth=1.4,
        linestyle="--",
        label=f"information threshold ({threshold:g})",
    )
    last = len(horizons) - 1
    for position, (horizon, value) in enumerate(
        zip(horizons, mixing_table["mean_distance_to_stationary"], strict=True)
    ):
        # The final label would hang off the right edge if it stayed centred.
        offset, align = (-6, "right") if position == last else (0, "center")
        axes.annotate(
            f"{value:.3f}",
            (horizon, value),
            textcoords="offset points",
            xytext=(offset, 9),
            ha=align,
            fontsize=8,
            color=NEUTRAL_INK,
        )
    _style(
        axes,
        "Distance from the projected regime to the long-run distribution",
        ylabel="total variation distance",
        xlabel="horizon in months",
    )
    axes.legend(frameon=False, fontsize=9, labelcolor=NEUTRAL_INK)
    figure.tight_layout()
    return figure


def plot_reliability(
    reliability_tables: dict[int, pd.DataFrame], calibration_errors: dict[int, float]
) -> Figure:
    """One reliability diagram per horizon, against the perfect-calibration line."""
    figure, grid = plt.subplots(
        1,
        len(reliability_tables),
        figsize=(4.2 * len(reliability_tables), 4.0),
        facecolor=SURFACE,
        squeeze=False,
    )
    for axes, (horizon, table) in zip(grid[0], sorted(reliability_tables.items()), strict=True):
        axes.set_facecolor(SURFACE)
        axes.plot(
            [0, 1],
            [0, 1],
            color=NEUTRAL_INK,
            linewidth=1.0,
            linestyle="--",
            label="perfect calibration",
        )
        sizes = 20.0 + 180.0 * table["count"] / max(table["count"].max(), 1)
        axes.scatter(
            table["mean_forecast"],
            table["observed_rate"],
            s=sizes,
            color=POSITIVE_COLOUR,
            edgecolor=SURFACE,
            linewidth=1.2,
            zorder=3,
            label="observed rate (area is count)",
        )
        axes.plot(
            table["mean_forecast"],
            table["observed_rate"],
            linewidth=1.4,
            color=POSITIVE_COLOUR,
            alpha=0.6,
        )
        axes.set_xlim(0, 1)
        axes.set_ylim(0, 1)
        _style(
            axes,
            f"{horizon // 12} year  (calibration error {calibration_errors[horizon]:.3f})",
            ylabel="observed frequency",
            xlabel="forecast probability",
        )
        axes.legend(frameon=False, fontsize=8, loc="upper left", labelcolor=NEUTRAL_INK)
    figure.tight_layout()
    return figure


def plot_skill_by_indicator(metrics: pd.DataFrame, horizon_in_months: int) -> Figure:
    """Skill against climatology, per indicator. Diverging around a meaningful zero."""
    at_horizon = (
        metrics[metrics["horizon_months"] == horizon_in_months]
        .sort_values("brier_skill_score")
        .reset_index(drop=True)
    )
    figure, axes = _new_figure(9.0, 0.42 * len(at_horizon) + 2.0)
    positions = np.arange(len(at_horizon))
    scores = at_horizon["brier_skill_score"].to_numpy()
    axes.barh(
        positions,
        scores,
        height=0.62,
        color=[POSITIVE_COLOUR if value > 0 else NEGATIVE_COLOUR for value in scores],
    )
    axes.axvline(0.0, color=NEUTRAL_INK, linewidth=1.2)
    axes.set_yticks(positions)
    axes.set_yticklabels([name.replace("_", " ") for name in at_horizon["indicator"]], fontsize=9)
    for position, value in zip(positions, scores, strict=True):
        axes.text(
            float(value) + (0.004 if value >= 0 else -0.004),
            float(position),
            f"{value:+.3f}",
            va="center",
            ha="left" if value >= 0 else "right",
            fontsize=8,
            color=NEUTRAL_INK,
        )
    _style(
        axes,
        f"Skill against climatology at {horizon_in_months // 12} year"
        + ("s" if horizon_in_months > 12 else ""),
        xlabel="Brier skill score (positive beats the base rate)",
    )
    handles = [
        Patch(facecolor=POSITIVE_COLOUR, label="beats the base rate"),
        Patch(facecolor=NEGATIVE_COLOUR, label="loses to the base rate"),
    ]
    axes.legend(
        handles=handles, frameon=False, fontsize=9, loc="lower right", labelcolor=NEUTRAL_INK
    )
    figure.tight_layout()
    return figure


def plot_skill_by_horizon(verdicts: pd.DataFrame) -> Figure:
    """Mean skill with its interval, one point per horizon, verdict labelled."""
    figure, axes = _new_figure(7.5, 4.0)
    positions = np.arange(len(verdicts))
    points = verdicts["mean_brier_skill_score"].to_numpy()
    lower = points - verdicts["skill_lower_bound"].to_numpy()
    upper = verdicts["skill_upper_bound"].to_numpy() - points

    axes.errorbar(
        positions,
        points,
        yerr=np.vstack([lower, upper]),
        fmt="o",
        markersize=9,
        color=POSITIVE_COLOUR,
        ecolor=POSITIVE_COLOUR,
        elinewidth=2.0,
        capsize=6,
        label="mean skill with a 90 percent block bootstrap interval",
    )
    axes.axhline(0.0, color=NEUTRAL_INK, linewidth=1.2)
    axes.set_xticks(positions)
    axes.set_xticklabels(
        [
            f"{int(row['horizon_months']) // 12} year\n{row['verdict']}"
            for row in verdicts.to_dict("records")
        ],
        fontsize=9,
    )
    axes.set_xlim(-0.5, len(verdicts) - 0.5)
    _style(axes, "Skill by horizon, with the verdict", ylabel="Brier skill score")
    axes.legend(frameon=False, fontsize=9, labelcolor=NEUTRAL_INK)
    figure.tight_layout()
    return figure
