"""Turn a point-in-time panel into the matrix the hidden Markov model reads.

The model sees a three-column matrix of standardised growth, inflation and
interest-rate observations, one row per month. Building it is four steps, in this
order and no other:

1. normalise every series to month-start timestamps;
2. apply each series' registered transform, which is what makes vintages with
   different index bases comparable;
3. align the three on the months all of them cover;
4. standardise each column with an expanding window, so no row is scaled using
   information from a later row.

The column order is fixed by ``ModelDimension`` -- growth, inflation, rates --
because state labelling later reads emission means by position, and a permuted
column order would silently rename every regime.

Research arm A3 of experiment 0002 adds a fifth step, taken only when
``RunSettings.growth_and_inflation_surprise_quadrants`` is set: the standardised
growth and inflation columns are replaced by their surprises
(``replace_growth_and_inflation_with_surprises``). ``observations_as_configured``
is the one place that decides whether it is taken.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from economic_regime_forecasting.configuration.registry import (
    EconomicSeriesRegistry,
    ModelDimension,
)
from economic_regime_forecasting.configuration.run_settings import RunSettings
from economic_regime_forecasting.data.panel import PointInTimePanel
from economic_regime_forecasting.features import transforms

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
    """Rows are months, columns are growth, inflation and rates, in that order."""

    transformed: pd.DataFrame
    """The same months in their natural units, kept for interpreting regimes."""

    bridged_months: tuple[pd.Timestamp, ...]
    """Months whose raw value was interpolated across a one-month hole in the
    source data. Recorded so the manifest can say which numbers were imputed."""

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
    inputs = {item.model_dimension: item for item in registry.model_inputs}

    columns: dict[str, pd.Series] = {}
    bridged: list[pd.Timestamp] = []
    for dimension in DIMENSION_ORDER:
        entry = inputs[dimension]
        raw = transforms.to_month_start(panel[entry.name])
        repaired, filled = transforms.bridge_isolated_missing_months(raw)
        bridged.extend(filled)
        columns[dimension.value] = transforms.apply_transform(repaired, entry.transform)

    transformed = pd.DataFrame(columns).dropna(how="any")
    if transformed.empty:
        raise ObservationMatrixError(
            f"no month as of {panel.as_of.isoformat()} has all three model inputs. The binding "
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
        standardised=standardised[list(COLUMN_NAMES)],
        transformed=transformed.loc[standardised.index, list(COLUMN_NAMES)],
        bridged_months=tuple(sorted(set(bridged))),
    )


def replace_growth_and_inflation_with_surprises(
    matrix: ObservationMatrix, minimum_months_before_first_surprise: int
) -> ObservationMatrix:
    """Research arm A3: the growth and inflation columns become their surprises.

    Taken after the expanding standardisation, so the surprise is the last step
    and the column the model reads is the surprise itself. Its zero is then the
    expected value of a surprise, which is where the quadrant boundaries sit, with
    nothing estimated to put them there. A second standardisation afterwards would
    move that zero to an estimated running mean.

    It is point in time throughout. The standardised value at month s uses months
    up to s; the autoregression behind its surprise is fitted on standardised
    values strictly before s (``transforms.recursive_autoregressive_surprise``).

    The rates column is unchanged. The first ``minimum_months_before_first_surprise``
    standardised months have no surprise, so they drop out of all three columns.
    The last month never moves.
    """
    standardised = matrix.standardised.copy()
    for dimension in (ModelDimension.GROWTH, ModelDimension.INFLATION):
        standardised[dimension.value] = transforms.recursive_autoregressive_surprise(
            standardised[dimension.value], minimum_months_before_first_surprise
        )
    standardised = standardised.dropna(how="any")
    if standardised.empty:
        raise ObservationMatrixError(
            f"as of {matrix.as_of.isoformat()} there are {len(matrix)} standardised months, "
            f"not more than the {minimum_months_before_first_surprise} an autoregression must "
            "have behind it before its first surprise."
        )
    transforms.assert_strictly_monthly(standardised)
    if standardised.index[-1] != matrix.standardised.index[-1]:  # pragma: no cover - by design
        raise ObservationMatrixError(
            "replacing growth and inflation with their surprises moved the last month from "
            f"{matrix.standardised.index[-1]:%Y-%m} to {standardised.index[-1]:%Y-%m}; a "
            "surprise step may only drop months from the start."
        )
    if not np.isfinite(standardised.to_numpy(dtype="float64")).all():  # pragma: no cover
        raise ObservationMatrixError(
            "the surprise columns contain non-finite values, which would make every "
            "emission likelihood undefined"
        )
    return ObservationMatrix(
        as_of=matrix.as_of,
        standardised=standardised[list(COLUMN_NAMES)],
        transformed=matrix.transformed.loc[standardised.index, list(COLUMN_NAMES)],
        bridged_months=matrix.bridged_months,
    )


def observations_as_configured(
    matrix: ObservationMatrix, settings: RunSettings
) -> ObservationMatrix:
    """The matrix the configured model reads.

    Unchanged under main's configuration. With
    ``growth_and_inflation_surprise_quadrants`` set, growth and inflation are
    replaced by their surprises. Every caller that fits or filters a regime model
    passes its matrix through here, so the model and its inputs cannot disagree
    about which columns they mean.
    """
    if not settings.growth_and_inflation_surprise_quadrants:
        return matrix
    return replace_growth_and_inflation_with_surprises(
        matrix, transforms.MINIMUM_MONTHS_BEFORE_FIRST_SURPRISE
    )
