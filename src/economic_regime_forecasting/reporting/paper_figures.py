"""Figures for the research paper. Presentation only; nothing here computes a result.

Sized for a single-column page, about 6.3 inches of text width, and drawn in the
notebooks' palette so a reader moving between the two sees the same colour mean
the same thing. Each forecaster keeps one colour everywhere: the blend that ships
is blue, the regime model alone is violet, the regime-free condition chain is
orange, and the historical average is grey.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from economic_regime_forecasting.reporting.figures import (
    GRID_INK,
    NEGATIVE_COLOUR,
    NEUTRAL_INK,
    RECESSION_SHADE,
    REGIME_COLOURS,
    SURFACE,
)

PAGE_WIDTH_INCHES = 6.3

FORECASTER_COLOURS: dict[str, str] = {
    "blend": "#2a78d6",
    "regime model alone": "#4a3aa7",
    "condition chain": "#eb6834",
    "historical average": "#8a8984",
}
"""One colour per forecaster, the same in every figure."""

FORECASTER_LABELS: dict[str, str] = {
    "blend": "blend (what ships)",
    "regime model alone": "regime model alone",
    "condition chain": "condition chain (no regimes)",
    "historical average": "historical average (R1)",
}


def _style(axes: Axes, title: str = "", ylabel: str = "", xlabel: str = "") -> None:
    """Recessive grid and axes; the data is the only thing with weight."""
    if title:
        axes.set_title(title, fontsize=9, color="#0b0b0b", loc="left", pad=6)
    if ylabel:
        axes.set_ylabel(ylabel, fontsize=8, color=NEUTRAL_INK)
    if xlabel:
        axes.set_xlabel(xlabel, fontsize=8, color=NEUTRAL_INK)
    axes.set_facecolor(SURFACE)
    axes.grid(True, color=GRID_INK, linewidth=0.5, alpha=0.8)
    axes.set_axisbelow(True)
    for side in ("top", "right"):
        axes.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axes.spines[side].set_color(GRID_INK)
    axes.tick_params(colors=NEUTRAL_INK, labelsize=7.5)


LegendLocation = Literal["upper right", "upper left", "lower right", "lower left"]


def _legend(axes: Axes, location: LegendLocation = "upper right", columns: int = 1) -> None:
    axes.legend(frameon=False, fontsize=7.5, labelcolor=NEUTRAL_INK, loc=location, ncol=columns)


def skill_curves(
    curves: pd.DataFrame,
    last_horizon_with_skill: Mapping[str, int],
    banded: Sequence[str] = ("blend", "condition chain"),
) -> Figure:
    """Mean skill against the benchmark at every horizon, one line per forecaster.

    ``curves`` has one row per forecaster and horizon, with ``mean_skill``,
    ``lower_bound``, ``upper_bound`` and ``informative``. Bands are drawn only for
    the forecasters named in ``banded``, because three overlapping bands hide each
    other. A dashed line marks the last horizon each forecaster carries skill.
    """
    figure, axes = plt.subplots(figsize=(PAGE_WIDTH_INCHES, 3.3), facecolor=SURFACE)
    uninformative = curves.loc[~curves["informative"].astype(bool), "horizon_in_months"]
    if not uninformative.empty:
        axes.axvspan(
            float(uninformative.min()) - 0.5,
            float(uninformative.max()) + 0.5,
            color=RECESSION_SHADE,
            alpha=0.55,
            linewidth=0,
            label="too few independent observations to read",
        )
    for forecaster in ("regime model alone", "condition chain", "blend"):
        rows = curves[curves["forecaster"] == forecaster].sort_values("horizon_in_months")
        if rows.empty:
            continue
        months = rows["horizon_in_months"].to_numpy()
        colour = FORECASTER_COLOURS[forecaster]
        if forecaster in banded:
            axes.fill_between(
                months,
                rows["lower_bound"].to_numpy(),
                rows["upper_bound"].to_numpy(),
                color=colour,
                alpha=0.14,
                linewidth=0,
            )
        axes.plot(
            months,
            rows["mean_skill"].to_numpy(),
            color=colour,
            linewidth=2.0 if forecaster == "blend" else 1.4,
            label=FORECASTER_LABELS[forecaster],
        )
    for forecaster, month in last_horizon_with_skill.items():
        axes.axvline(
            month, color=FORECASTER_COLOURS[forecaster], linewidth=1.0, linestyle=(0, (3, 2))
        )
        axes.annotate(
            f"{month} months",
            xy=(month, 0.60),
            xytext=(3, 0),
            textcoords="offset points",
            fontsize=7.5,
            color=FORECASTER_COLOURS[forecaster],
        )
    axes.axhline(0.0, color=NEUTRAL_INK, linewidth=0.9)
    axes.set_xlim(1, float(curves["horizon_in_months"].max()))
    axes.set_xticks([1, 12, 24, 36, 48, 60, 72, 84, 96, 108, 120])
    _style(
        axes,
        ylabel="Brier skill against the historical average",
        xlabel="forecast horizon in months",
    )
    _legend(axes, "lower left")
    figure.tight_layout()
    return figure


def difference_curve(differences: pd.DataFrame, label: str) -> Figure:
    """A paired difference at every horizon, its 90% band, and where it clears zero.

    ``differences`` has ``horizon_in_months``, ``difference``, ``lower_bound`` and
    ``upper_bound``. Months whose whole interval lies below zero are ticked along
    the bottom in red, and months whose whole interval lies above zero in blue.
    """
    figure, axes = plt.subplots(figsize=(PAGE_WIDTH_INCHES, 2.5), facecolor=SURFACE)
    rows = differences.sort_values("horizon_in_months")
    months = rows["horizon_in_months"].to_numpy()
    colour = FORECASTER_COLOURS["blend"]
    axes.fill_between(
        months,
        rows["lower_bound"].to_numpy(),
        rows["upper_bound"].to_numpy(),
        color=colour,
        alpha=0.16,
        linewidth=0,
        label="90% interval",
    )
    axes.plot(months, rows["difference"].to_numpy(), color=colour, linewidth=1.8, label=label)
    axes.axhline(0.0, color=NEUTRAL_INK, linewidth=0.9)
    floor = float(np.nanmin(rows["lower_bound"].to_numpy()))
    below = rows[rows["upper_bound"] < 0]["horizon_in_months"].to_numpy()
    above = rows[rows["lower_bound"] > 0]["horizon_in_months"].to_numpy()
    if below.size:
        axes.scatter(
            below,
            np.full(below.size, floor),
            marker="|",
            s=40,
            color=NEGATIVE_COLOUR,
            label="interval entirely below zero",
        )
    if above.size:
        axes.scatter(
            above,
            np.full(above.size, floor),
            marker="|",
            s=40,
            color=FORECASTER_COLOURS["blend"],
            label="interval entirely above zero",
        )
    axes.set_xlim(1, float(months.max()))
    axes.set_xticks([1, 12, 24, 36, 48, 60, 72, 84, 96, 108, 120])
    _style(axes, ylabel="difference in skill", xlabel="forecast horizon in months")
    _legend(axes, "upper right")
    figure.tight_layout()
    return figure


def skill_by_indicator(table: pd.DataFrame, forecasters: Sequence[str]) -> Figure:
    """One row per question, one dot per forecaster, against a zero line.

    ``table`` is indexed by the question's short name, with one column per
    forecaster. Rows keep the order they arrive in.
    """
    count = len(table)
    figure, axes = plt.subplots(figsize=(PAGE_WIDTH_INCHES, 0.33 * count + 1.1), facecolor=SURFACE)
    positions = np.arange(count)[::-1]
    offsets = np.linspace(-0.18, 0.18, len(forecasters))
    for offset, forecaster in zip(offsets, forecasters, strict=True):
        axes.scatter(
            table[forecaster].to_numpy(),
            positions + offset,
            s=26,
            color=FORECASTER_COLOURS[forecaster],
            label=FORECASTER_LABELS[forecaster],
            zorder=3,
        )
    for position in positions:
        axes.axhline(position, color=GRID_INK, linewidth=0.4, zorder=1)
    axes.axvline(0.0, color=NEUTRAL_INK, linewidth=0.9)
    axes.set_yticks(positions)
    axes.set_yticklabels(list(table.index), fontsize=7.5)
    _style(axes, xlabel="Brier skill against the historical average, one-year horizon")
    axes.grid(False)
    axes.grid(True, axis="x", color=GRID_INK, linewidth=0.5, alpha=0.8)
    axes.legend(
        frameon=False,
        fontsize=7,
        labelcolor=NEUTRAL_INK,
        loc="lower right",
        bbox_to_anchor=(1.0, 1.0),
        ncol=len(forecasters),
        handletextpad=0.2,
        columnspacing=1.0,
    )
    figure.tight_layout()
    return figure


def reliability(tables: Mapping[str, pd.DataFrame], slopes: Mapping[str, str]) -> Figure:
    """One reliability diagram per forecaster, side by side, on shared axes.

    Each table has ``mean_forecast``, ``observed_rate`` and ``count`` per bin.
    ``slopes`` holds the pre-formatted calibration slope for each panel's title.
    """
    figure, grid = plt.subplots(
        1,
        len(tables),
        figsize=(PAGE_WIDTH_INCHES, 3.0),
        facecolor=SURFACE,
        squeeze=False,
        sharey=True,
    )
    for axes, (forecaster, table) in zip(grid[0], tables.items(), strict=True):
        colour = FORECASTER_COLOURS[forecaster]
        axes.plot([0, 1], [0, 1], color=NEUTRAL_INK, linewidth=0.9, linestyle="--")
        sizes = 12.0 + 140.0 * table["count"] / max(float(table["count"].max()), 1.0)
        axes.plot(
            table["mean_forecast"], table["observed_rate"], color=colour, linewidth=1.2, alpha=0.6
        )
        axes.scatter(
            table["mean_forecast"],
            table["observed_rate"],
            s=sizes,
            color=colour,
            edgecolor=SURFACE,
            linewidth=0.8,
            zorder=3,
        )
        axes.set_xlim(0, 1)
        axes.set_ylim(0, 1)
        axes.set_aspect("equal")
        _style(
            axes,
            f"{FORECASTER_LABELS[forecaster]}: slope {slopes[forecaster]}",
            ylabel="how often it happened",
            xlabel="forecast probability",
        )
    figure.tight_layout()
    return figure


def forecast_timelines(panels: Sequence[tuple[str, pd.DataFrame]]) -> Figure:
    """The shipped one-year probability through history, beside what happened.

    Each panel's frame has ``forecast_date``, ``probability``, ``base_rate`` and
    ``outcome``. Months whose question resolved yes are shaded, so a reader can
    see whether the probability rose before the event rather than after it.
    """
    columns = 2
    rows = int(np.ceil(len(panels) / columns))
    figure, grid = plt.subplots(
        rows,
        columns,
        figsize=(PAGE_WIDTH_INCHES, 2.0 * rows + 0.4),
        facecolor=SURFACE,
        squeeze=False,
        sharex=True,
    )
    flattened = grid.ravel()
    for axes, (title, frame) in zip(flattened, panels, strict=False):
        dates = pd.to_datetime(frame["forecast_date"])
        happened = frame["outcome"].to_numpy() == 1.0
        axes.fill_between(
            dates, 0, 1, where=happened, color=RECESSION_SHADE, linewidth=0, step="mid"
        )
        axes.plot(
            dates,
            frame["base_rate"].to_numpy(),
            color=FORECASTER_COLOURS["historical average"],
            linewidth=1.0,
            label=FORECASTER_LABELS["historical average"],
        )
        axes.plot(
            dates,
            frame["probability"].to_numpy(),
            color=FORECASTER_COLOURS["blend"],
            linewidth=1.3,
            label=FORECASTER_LABELS["blend"],
        )
        axes.set_ylim(0, 1)
        _style(axes, title, ylabel="probability")
    for axes in flattened[len(panels) :]:
        axes.set_visible(False)
    for axes in flattened:
        axes.xaxis.set_major_locator(mdates.YearLocator(8))  # type: ignore[no-untyped-call]
        axes.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))  # type: ignore[no-untyped-call]
    flattened[0].legend(frameon=False, fontsize=7, labelcolor=NEUTRAL_INK, loc="upper left")
    figure.tight_layout()
    return figure


def regime_chains(
    chains: Sequence[tuple[str, pd.DataFrame]],
    recession_months: pd.DatetimeIndex,
) -> Figure:
    """One lane per state of each chain, filled with its filtered probability.

    Each frame is indexed by date with one column per state, labelled. Lanes are
    used rather than a stacked area for the reason ``figures.plot_regime_timeline``
    gives: the model is usually confident, and a stack spends its height saying so.
    Recessions are shaded behind every lane.
    """
    lane_count = sum(frame.shape[1] for _, frame in chains)
    spacer = 0.9
    ratios: list[float] = []
    for position_of_chain, (_, frame) in enumerate(chains):
        if position_of_chain:
            ratios.append(spacer)
        ratios.extend([1.0] * frame.shape[1])
    figure = plt.figure(
        figsize=(PAGE_WIDTH_INCHES, 0.40 * lane_count + 0.3 * len(chains) + 0.6),
        facecolor=SURFACE,
    )
    grid = figure.add_gridspec(len(ratios), 1, height_ratios=ratios, hspace=0.35)
    row = 0
    shared: Axes | None = None
    for position_of_chain, (chain_name, frame) in enumerate(chains):
        if position_of_chain:
            row += 1
        dates = pd.DatetimeIndex(frame.index)
        in_recession = dates.isin(recession_months)
        for state_position, label in enumerate(frame.columns):
            axes = figure.add_subplot(grid[row, 0], sharex=shared)
            shared = shared or axes
            axes.set_facecolor(SURFACE)
            axes.fill_between(
                dates, 0, 1, where=in_recession, color=RECESSION_SHADE, linewidth=0, step="mid"
            )
            axes.fill_between(
                dates,
                0,
                frame[label].to_numpy(),
                color=REGIME_COLOURS[state_position % len(REGIME_COLOURS)],
                linewidth=0,
                step="mid",
            )
            axes.set_ylim(0, 1)
            axes.set_yticks([])
            axes.margins(x=0)
            for side in ("top", "right", "left"):
                axes.spines[side].set_visible(False)
            axes.spines["bottom"].set_color(GRID_INK)
            last_lane_of_chain = state_position == frame.shape[1] - 1
            axes.tick_params(colors=NEUTRAL_INK, labelsize=7.5, labelbottom=last_lane_of_chain)
            axes.text(
                -0.01,
                0.5,
                str(label),
                transform=axes.transAxes,
                ha="right",
                va="center",
                fontsize=7.5,
                color="#0b0b0b",
            )
            if state_position == 0:
                axes.set_title(chain_name, fontsize=8.5, color="#0b0b0b", loc="left", pad=4)
            row += 1
    figure.subplots_adjust(left=0.27, right=0.98, top=0.95, bottom=0.05)
    return figure
