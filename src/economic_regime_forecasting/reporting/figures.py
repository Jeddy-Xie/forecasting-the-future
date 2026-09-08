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


def plot_regime_probabilities(
    dates: pd.DatetimeIndex,
    state_probabilities: np.ndarray,
    regime_labels: Sequence[str],
    recession_flag: pd.Series | None = None,
) -> Figure:
    """Filtered regime probabilities through time, with recessions shaded.

    Stacked because the probabilities sum to one and the question is which regime
    holds the mass. Recessions are a neutral shade rather than a series colour, so
    the reference band never competes with the data for identity.
    """
    figure, axes = _new_figure(11.0, 4.2)

    if recession_flag is not None:
        flag = recession_flag.reindex(dates).fillna(0.0).to_numpy()
        axes.fill_between(
            dates, 0, 1, where=flag > 0.5, color=RECESSION_SHADE, linewidth=0, zorder=0
        )

    axes.stackplot(
        dates,
        state_probabilities.T,
        colors=REGIME_COLOURS[: state_probabilities.shape[1]],
        labels=list(regime_labels),
        edgecolor=SURFACE,
        linewidth=0.4,
        zorder=2,
    )
    axes.set_ylim(0, 1)
    axes.margins(x=0)
    _style(axes, "Filtered regime probabilities", ylabel="probability")
    axes.grid(False)

    handles = [
        Patch(facecolor=REGIME_COLOURS[index], label=label)
        for index, label in enumerate(regime_labels)
    ]
    if recession_flag is not None:
        handles.append(Patch(facecolor=RECESSION_SHADE, label="recession"))
    axes.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.12),
        ncol=2,
        frameon=False,
        fontsize=9,
        labelcolor=NEUTRAL_INK,
    )
    figure.tight_layout()
    return figure


def plot_regime_means(regime_table: pd.DataFrame) -> Figure:
    """Where each regime sits on growth, inflation and rates, in natural units."""
    dimensions = ("growth", "inflation", "rates")
    figure, grid = plt.subplots(1, 3, figsize=(12.0, 3.4), facecolor=SURFACE)
    positions = np.arange(len(regime_table))
    for axes, dimension in zip(grid, dimensions, strict=True):
        axes.set_facecolor(SURFACE)
        values = regime_table[f"{dimension}_natural"].to_numpy()
        axes.barh(
            positions,
            values,
            height=0.62,
            color=[REGIME_COLOURS[index] for index in range(len(values))],
        )
        axes.set_yticks(positions)
        axes.set_yticklabels([f"regime {index}" for index in positions], fontsize=9)
        axes.invert_yaxis()
        _style(axes, dimension, xlabel="natural units")
        for position, value in zip(positions, values, strict=True):
            axes.text(value, position, f"  {value:.3g}", va="center", fontsize=8, color=NEUTRAL_INK)
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
    axes.plot(
        horizons,
        mixing_table["mean_distance_to_stationary"],
        linewidth=2.0,
        color=POSITIVE_COLOUR,
        marker="o",
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
    for horizon, value in zip(horizons, mixing_table["mean_distance_to_stationary"], strict=True):
        axes.annotate(
            f"{value:.3f}",
            (horizon, value),
            textcoords="offset points",
            xytext=(0, 9),
            ha="center",
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
