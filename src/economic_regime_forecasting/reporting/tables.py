"""Tables formatted for a reader rather than for a file.

The model works in the units its transforms produce: a year-over-year log change
for growth and inflation, a plain level for the interest rate. Printing those side
by side gives a table where growth reads 0.034 and the interest rate reads 4.57,
which invites the reader to compare two numbers that are not on the same scale.

Converting is a presentation decision, so it lives here rather than in the model.
The artifacts written to disk keep the raw values; only what a person reads is
converted, and the column names say which unit they are in.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from economic_regime_forecasting.configuration.registry import (
    EconomicSeriesRegistry,
    Transform,
)
from economic_regime_forecasting.features.observation_matrix import COLUMN_NAMES
from economic_regime_forecasting.models.state_labelling import RegimeDescription


def to_percent_per_year(value: float, transform: Transform) -> float:
    """Put one dimension's mean into percent a year, whatever units it arrived in.

    A year-over-year log change of 0.034 is a growth rate of 3.5% a year, not 0.034
    of anything. The exponential is used rather than multiplying by a hundred
    because the difference matters once the rate is large: the stagflation regime's
    0.092 is 9.6% a year, not 9.2%.
    """
    if transform in (Transform.YEAR_OVER_YEAR_LOG_CHANGE,):
        return float((np.exp(value) - 1.0) * 100.0)
    return float(value)


def dimension_units(registry: EconomicSeriesRegistry) -> tuple[str, ...]:
    """The unit each of the three model dimensions is reported in."""
    return tuple(
        "percent a year" if entry.transform is Transform.YEAR_OVER_YEAR_LOG_CHANGE else entry.units
        for entry in registry.model_inputs
    )


def regime_display_table(
    descriptions: Sequence[RegimeDescription], registry: EconomicSeriesRegistry
) -> pd.DataFrame:
    """One row per regime, in units a reader can compare across columns."""
    transforms = [entry.transform for entry in registry.model_inputs]
    rows = []
    for item in descriptions:
        row: dict[str, object] = {"state": item.state, "regime": item.compact_label}
        for name, value, transform in zip(
            COLUMN_NAMES, item.natural_means, transforms, strict=True
        ):
            row[_column_name(name, transform)] = round(to_percent_per_year(value, transform), 2)
        row["share of months"] = f"{item.population_share:.0%}"
        row["typical visit"] = f"{item.expected_duration_in_months:.0f} months"
        rows.append(row)
    return pd.DataFrame(rows)


def _column_name(dimension: str, transform: Transform) -> str:
    if transform is Transform.YEAR_OVER_YEAR_LOG_CHANGE:
        return f"{dimension} %/yr"
    return f"{dimension} %"


def sweep_display_table(sweep_table: pd.DataFrame) -> pd.DataFrame:
    """The state sweep with the columns a reader actually compares, in order."""
    view = sweep_table.copy()
    if "growth_chain_states" in view.columns:
        # A two-chain run sweeps each chain separately, so persistence and population
        # belong to a chain, not to a pair. Showing those columns empty would read as
        # "measured, and blank"; the pair and its joint quantities are what this table has.
        return pd.DataFrame(
            {
                "joint states": view["states"],
                "growth x levels": (
                    view["growth_chain_states"].astype(int).astype(str)
                    + " x "
                    + view["levels_chain_states"].astype(int).astype(str)
                ),
                "parameters": view["free_parameters"],
                "criterion (lower better)": view["bayesian_information_criterion"].round(0),
                "held-out (higher better)": view["held_out_log_likelihood_per_month"].round(3),
                "admissible": view["admissible"],
            }
        )
    single_state = view["states"] == 1
    # A one-state model has no second state to leave for, so its expected visit is
    # the length of the sample. Printing 1e12 months is noise; printing nothing
    # says the quantity does not apply.
    view.loc[single_state, "shortest_expected_duration_months"] = np.nan
    view.loc[single_state, "smallest_population_share"] = np.nan
    return pd.DataFrame(
        {
            "states": view["states"],
            "parameters": view["free_parameters"],
            "criterion (lower better)": view["bayesian_information_criterion"].round(0),
            "held-out (higher better)": view["held_out_log_likelihood_per_month"].round(3),
            "smallest state": view["smallest_population_share"].map(
                lambda v: "" if pd.isna(v) else f"{v:.0%}"
            ),
            "shortest visit": view["shortest_expected_duration_months"].map(
                lambda v: "" if pd.isna(v) else f"{v:.0f} months"
            ),
            "admissible": view["admissible"],
        }
    )


def forecast_display_table(forecasts: pd.DataFrame) -> pd.DataFrame:
    """The current grid as ten rows by three horizons, probabilities as percents."""
    grid = forecasts.pivot(index="indicator", columns="horizon_months", values="probability")
    grid.columns = [f"{int(months) // 12} year" for months in grid.columns]
    return (grid * 100).round(1)
