"""Pure transforms from a raw economic series to a modelling series.

Every function here takes values and returns values. There is no input or output,
no clock and no configuration, which is what makes them testable by writing down
an answer by hand.

Two properties are worth stating because the rest of the project leans on them:

Rebasing invariance
    Both year-over-year forms are ratios, so multiplying a whole series by a
    constant leaves them unchanged. This matters more than it sounds: the
    industrial production index has been rebased repeatedly, and a 1970 vintage
    puts January 1919 at 24.6 where a 2026 vintage puts it at 4.87. In levels
    those vintages are incomparable. In year-over-year growth they agree.

Expanding-window standardisation
    The mean and standard deviation used to standardise the observation at time
    t are computed from observations up to and including t, never from the whole
    sample. A full-sample z-score would leak the future into every early
    observation, and would additionally make each refit silently restate its own
    history.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from economic_regime_forecasting.configuration.registry import Transform

MONTHS_IN_A_YEAR = 12

MINIMUM_PERIODS_FOR_STANDARDISATION = 36
"""Three years. Below this the standard deviation of a macro series is too noisy
to divide by, and the resulting z-scores swamp the model's emission likelihood."""


class TransformError(ValueError):
    """A transform was asked for something it cannot do with the data given."""


def level(series: pd.Series) -> pd.Series:
    """Identity. Named so that the registry can say ``level`` and mean it."""
    as_float: pd.Series = series.astype("float64")
    return as_float


def year_over_year_log_change(series: pd.Series) -> pd.Series:
    """Log of this month's value minus log of the value twelve months earlier.

    Log changes rather than percent changes because they are symmetric and add
    across periods, which is the right scale for a Gaussian emission model.
    Non-positive values cannot be logged and become missing rather than raising,
    since a price or output index legitimately has no meaningful log below zero
    and the caller drops missing rows anyway.
    """
    positive = series.where(series > 0)
    changes: pd.Series = np.log(positive) - np.log(positive.shift(MONTHS_IN_A_YEAR))
    return changes


def year_over_year_percent_change(series: pd.Series) -> pd.Series:
    """Percent change over twelve months, in percentage points.

    Used for the inflation indicators, whose thresholds are quoted the way the
    press quotes them ("inflation above three percent"), not in log units.
    """
    earlier = series.shift(MONTHS_IN_A_YEAR)
    return 100.0 * (series / earlier.where(earlier != 0.0) - 1.0)


_TRANSFORM_FUNCTIONS = {
    Transform.LEVEL: level,
    Transform.YEAR_OVER_YEAR_LOG_CHANGE: year_over_year_log_change,
    Transform.YEAR_OVER_YEAR_PERCENT_CHANGE: year_over_year_percent_change,
}


def apply_transform(series: pd.Series, transform: Transform) -> pd.Series:
    """Dispatch to the named transform."""
    try:
        function = _TRANSFORM_FUNCTIONS[transform]
    except KeyError as error:
        raise TransformError(
            f"no implementation for transform {transform!r}; known transforms are "
            f"{[item.value for item in _TRANSFORM_FUNCTIONS]}"
        ) from error
    return function(series).astype("float64")


def difference(minuend: pd.Series, subtrahend: pd.Series) -> pd.Series:
    """Aligned difference of two series, on the dates both of them cover."""
    aligned_minuend, aligned_subtrahend = minuend.align(subtrahend, join="inner")
    if aligned_minuend.empty:
        raise TransformError(
            f"{minuend.name} and {subtrahend.name} share no observation dates, so their "
            "difference is empty. Check the frequencies and start dates in the registry."
        )
    return (aligned_minuend - aligned_subtrahend).astype("float64")


def to_month_start(series: pd.Series) -> pd.Series:
    """Normalise an index to the first of each month.

    The service labels monthly observations with the first of the month already;
    this guards against a series that does not, so that alignment across series
    is on identical timestamps rather than on nearly identical ones.
    """
    normalised = series.copy()
    normalised.index = pd.DatetimeIndex(series.index).to_period("M").to_timestamp()
    return normalised[~normalised.index.duplicated(keep="last")].sort_index()


MAXIMUM_BRIDGEABLE_GAP_IN_MONTHS = 1
"""How long a hole in a series may be before it stops being a plumbing problem.

October 2025 has no consumer price index and no unemployment rate: the federal
government shut down, the Bureau of Labor Statistics did not run the surveys, and
the value does not exist and never will. It is one month in the middle of an
otherwise complete series, with eleven months of data after it.

Ending the panel in September 2025 would discard nearly a year of history to
avoid one hole. Interpolating across it is an imputation, which is a modelling
choice and not plumbing, so it is done in one named place, bounded to a single
month, recorded in the run manifest, and refused for anything longer."""


def bridge_isolated_missing_months(
    series: pd.Series,
    maximum_gap_in_months: int = MAXIMUM_BRIDGEABLE_GAP_IN_MONTHS,
) -> tuple[pd.Series, tuple[pd.Timestamp, ...]]:
    """Fill single-month holes by linear interpolation; refuse longer ones.

    Returns the repaired series and the months that were filled, so the caller can
    put them in the manifest. A run of missing months longer than the limit raises,
    because a quarter-long hole is a different kind of problem and deserves a
    different decision than a silent straight line.
    """
    if series.empty:
        return series, ()
    on_a_complete_grid = series.reindex(pd.date_range(series.index[0], series.index[-1], freq="MS"))
    missing = on_a_complete_grid.index[on_a_complete_grid.isna()]
    if len(missing) == 0:
        return on_a_complete_grid, ()

    for month in missing:
        run_length = 1
        forward = month + pd.DateOffset(months=1)
        while forward in missing:
            run_length += 1
            forward = forward + pd.DateOffset(months=1)
        backward = month - pd.DateOffset(months=1)
        while backward in missing:
            run_length += 1
            backward = backward - pd.DateOffset(months=1)
        if run_length > maximum_gap_in_months:
            raise TransformError(
                f"{series.name} is missing {run_length} consecutive months around "
                f"{month:%Y-%m}, more than the {maximum_gap_in_months} this project will "
                "interpolate across. Decide explicitly what to do with that hole rather than "
                "drawing a straight line through it."
            )

    # Interpolate only between the first and last real observation. Extending a
    # straight line past either end would be extrapolation wearing a disguise.
    observed_positions = np.flatnonzero(on_a_complete_grid.notna().to_numpy())
    if observed_positions.size == 0:
        return on_a_complete_grid, ()
    first, last = int(observed_positions[0]), int(observed_positions[-1])
    repaired = on_a_complete_grid.copy()
    repaired.iloc[first : last + 1] = on_a_complete_grid.iloc[first : last + 1].interpolate(
        method="linear"
    )
    first_stamp = on_a_complete_grid.index[first]
    last_stamp = on_a_complete_grid.index[last]
    bridged = tuple(month for month in missing if first_stamp <= month <= last_stamp)
    return repaired.astype("float64"), bridged


def expanding_window_standardisation(
    frame: pd.DataFrame,
    minimum_periods: int = MINIMUM_PERIODS_FOR_STANDARDISATION,
) -> pd.DataFrame:
    """Standardise each column using only that column's own past.

    The value at row t is divided by statistics computed over rows one through t.
    Rows with fewer than ``minimum_periods`` observations behind them come back
    missing, and the caller drops them.

    A column that is constant over its window has zero standard deviation. Rather
    than dividing by zero and producing infinities that would poison a
    likelihood, those rows come back missing too.
    """
    if frame.empty:
        return frame

    expanding = frame.expanding(min_periods=minimum_periods)
    means = expanding.mean()
    standard_deviations = expanding.std(ddof=1)
    usable = standard_deviations.where(standard_deviations > 0.0)
    return ((frame - means) / usable).astype("float64")


def assert_strictly_monthly(frame: pd.DataFrame) -> None:
    """Fail loudly if a panel has gaps or duplicate months.

    A hidden Markov model reads its rows as consecutive time steps. A missing
    month is silently treated as no time having passed, which corrupts every
    transition probability and every expected duration derived from them.
    """
    if frame.empty:
        return
    index = pd.DatetimeIndex(frame.index)
    if index.has_duplicates:
        duplicated = index[index.duplicated()].strftime("%Y-%m").tolist()
        raise TransformError(f"panel has duplicate months: {duplicated[:5]}")
    expected = pd.date_range(start=index[0], end=index[-1], freq="MS")
    if len(expected) != len(index) or not (expected == index).all():
        missing = sorted(set(expected) - set(index))
        raise TransformError(
            f"panel is not a complete monthly sequence; {len(missing)} month(s) are missing, "
            f"first few: {[stamp.strftime('%Y-%m') for stamp in missing[:5]]}"
        )
