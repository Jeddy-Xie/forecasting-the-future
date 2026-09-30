"""Turn a point-in-time panel into the matrix the hidden Markov model reads.

The model sees a three-column matrix of standardised growth, inflation and
interest-rate observations, one row per month. Building it is four steps, in this
order and no other:

1. normalise every series to month-start timestamps;
2. apply each series' registered transform, which is what makes vintages with
   different index bases comparable;
3. align the columns on the months all of them cover;
4. standardise each column with an expanding window, so no row is scaled using
   information from a later row.

The column order is fixed by ``ModelDimension`` -- growth, inflation, rates --
because state labelling later reads emission means by position, and a permuted
column order would silently rename every regime.

When the registry is configured to observe the forecast targets (research arm B2
of experiment 0008), their columns follow the three, in registry order, and each
carries the dimension that says which regime chain reads it. A derived difference
is taken from its two point-in-time legs before step 2. Every column goes through
the same four steps, so the alignment in step 3 starts the matrix where its
shortest column starts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from economic_regime_forecasting.configuration.registry import (
    EconomicSeriesRegistry,
    ModelDimension,
    ObservationColumn,
)
from economic_regime_forecasting.data import transforms
from economic_regime_forecasting.data.panel import PointInTimePanel

DIMENSION_ORDER: tuple[ModelDimension, ...] = (
    ModelDimension.GROWTH,
    ModelDimension.INFLATION,
    ModelDimension.RATES,
)
COLUMN_NAMES: tuple[str, ...] = tuple(dimension.value for dimension in DIMENSION_ORDER)


class ObservationMatrixError(ValueError):
    """The panel could not be turned into a usable observation matrix."""


@dataclass(frozen=True)
class ObservationMatrix:
    """Standardised observations, plus the untransformed values behind them."""

    as_of: date
    standardised: pd.DataFrame
    """Rows are months, columns are growth, inflation and rates, in that order, then
    any forecast-target columns the registry is configured to observe."""

    transformed: pd.DataFrame
    """The same months in their natural units, kept for interpreting regimes."""

    bridged_months: tuple[pd.Timestamp, ...]
    """Months whose raw value was interpolated across a one-month hole in the
    source data. Recorded so the manifest can say which numbers were imputed."""

    column_dimensions: tuple[ModelDimension, ...] = DIMENSION_ORDER
    """The dimension of each column, in column order, which is what assigns a column
    to a regime chain. The three dimensions unless forecast targets are observed."""

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(str(name) for name in self.standardised.columns)

    @property
    def values(self) -> np.ndarray:
        """The matrix a model fit consumes, shaped observations by dimensions."""
        return np.ascontiguousarray(self.standardised.to_numpy(dtype="float64"))

    @property
    def dates(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(self.standardised.index)

    def __len__(self) -> int:
        return int(self.standardised.shape[0])

    def describe(self) -> str:
        if len(self) == 0:
            return f"empty observation matrix as of {self.as_of.isoformat()}"
        return (
            f"{len(self)} months from {self.dates[0]:%Y-%m} to {self.dates[-1]:%Y-%m}, "
            f"as of {self.as_of.isoformat()}"
        )


def build_observation_matrix(
    panel: PointInTimePanel,
    registry: EconomicSeriesRegistry,
    minimum_periods_for_standardisation: int = transforms.MINIMUM_PERIODS_FOR_STANDARDISATION,
) -> ObservationMatrix:
    """Build the standardised observation matrix from a point-in-time panel."""
    observed = registry.observation_columns
    names = [column.name for column in observed]

    columns: dict[str, pd.Series] = {}
    bridged: list[pd.Timestamp] = []
    for column in observed:
        raw = _raw_column(panel, column)
        repaired, filled = transforms.bridge_isolated_missing_months(raw)
        bridged.extend(filled)
        columns[column.name] = transforms.apply_transform(repaired, column.transform)

    transformed = pd.DataFrame(columns).dropna(how="any")
    if transformed.empty:
        raise ObservationMatrixError(
            f"no month as of {panel.as_of.isoformat()} has every model input. The binding "
            f"constraint is usually the shortest series: "
            f"{ {name: int(series.notna().sum()) for name, series in columns.items()} }"
        )
    transforms.assert_strictly_monthly(transformed)

    standardised = transforms.expanding_window_standardisation(
        transformed, minimum_periods=minimum_periods_for_standardisation
    ).dropna(how="any")
    if standardised.empty:
        raise ObservationMatrixError(
            f"as of {panel.as_of.isoformat()} there are {len(transformed)} aligned months, fewer "
            f"than the {minimum_periods_for_standardisation} needed before an expanding-window "
            "standard deviation is stable enough to divide by."
        )
    transforms.assert_strictly_monthly(standardised)

    if not np.isfinite(standardised.to_numpy(dtype="float64")).all():
        raise ObservationMatrixError(
            "standardised observations contain non-finite values, which would make every "
            "emission likelihood undefined"
        )

    return ObservationMatrix(
        as_of=panel.as_of,
        standardised=standardised[names],
        transformed=transformed.loc[standardised.index, names],
        bridged_months=tuple(sorted(set(bridged))),
        column_dimensions=tuple(column.dimension for column in observed),
    )


def _raw_column(panel: PointInTimePanel, column: ObservationColumn) -> pd.Series:
    """One column's untransformed values, month-start labelled.

    A difference is taken on the months both point-in-time legs cover, so it ends
    where the later-published leg ends: its publication lag is the larger of the two.
    """
    if column.subtracted_series is None:
        return transforms.to_month_start(panel[column.series])
    return transforms.difference(
        transforms.to_month_start(panel[column.series]),
        transforms.to_month_start(panel[column.subtracted_series]),
    ).rename(column.name)
