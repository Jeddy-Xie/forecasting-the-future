"""Resolve what actually happened, so a forecast made in the past can be scored.

Each of the six resolution rules turns one economic series into a zero or a one
for a given forecast date and horizon. Two conventions run through all of them
and both are load-bearing:

The horizon window is *open at the start and closed at the end*: the months
considered are the forecast date plus one through the forecast date plus the
horizon. "Will a recession happen in the next five years" therefore does not
count a recession already under way this month, which is the reading a
forecaster would give the question.

An outcome that cannot be resolved is missing, never zero. If the horizon runs
past the end of the data, or a month inside the window has no observation, the
answer is unknown. Filling unknowns with zero is how a base rate quietly becomes
wrong, and how a model gets credit for calling non-events that were merely
unobserved.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from economic_regime_forecasting.configuration.registry import (
    BinaryIndicator,
    ResolutionRule,
)
from economic_regime_forecasting.features import transforms


class ResolutionError(ValueError):
    """An indicator could not be resolved against the series it names."""


@dataclass(frozen=True)
class ResolvedOutcomes:
    """Realised outcomes for one indicator at one horizon."""

    indicator_name: str
    horizon_in_months: int
    outcomes: pd.Series
    """Indexed by forecast date. Values are 1.0, 0.0, or missing when unknown."""

    @property
    def resolved_count(self) -> int:
        return int(self.outcomes.notna().sum())

    @property
    def positive_count(self) -> int:
        return int((self.outcomes == 1.0).sum())

    @property
    def base_rate(self) -> float:
        """Unconditional frequency over everything resolved. Missing if nothing is."""
        resolved = self.outcomes.dropna()
        return float("nan") if resolved.empty else float(resolved.mean())


def _forward_extreme(series: pd.Series, horizon_in_months: int, kind: str) -> pd.Series:
    """Extreme value over the months strictly after t and up to t plus horizon.

    Implemented by reversing, taking a backward-looking rolling extreme, reversing
    back and shifting by one. ``min_periods`` equal to the window makes any
    incomplete or gappy window resolve to missing rather than to a partial answer.
    """
    reversed_series = series.iloc[::-1]
    rolling = reversed_series.rolling(window=horizon_in_months, min_periods=horizon_in_months)
    extreme = (rolling.max() if kind == "max" else rolling.min()).iloc[::-1]
    return extreme.shift(-1)


def _value_at_horizon(series: pd.Series, horizon_in_months: int) -> pd.Series:
    """The observation exactly ``horizon_in_months`` months after each date."""
    return series.shift(-horizon_in_months)


def resolve(
    indicator: BinaryIndicator,
    series: pd.Series,
    horizon_in_months: int,
) -> ResolvedOutcomes:
    """Apply an indicator's rule to its series across every forecast date."""
    monthly = transforms.to_month_start(series)
    if monthly.empty:
        raise ResolutionError(
            f"indicator {indicator.name!r} resolves against an empty series "
            f"{indicator.resolution.series!r}"
        )
    complete_grid = pd.date_range(monthly.index[0], monthly.index[-1], freq="MS")
    monthly = monthly.reindex(complete_grid)
    prepared = transforms.apply_transform(monthly, indicator.resolution.transform)

    rule = indicator.resolution.rule
    threshold = indicator.resolution.threshold
    if threshold is None:  # pragma: no cover - the registry validates this
        raise ResolutionError(f"indicator {indicator.name!r} has no threshold")

    if rule is ResolutionRule.LEVEL_ABOVE_THRESHOLD_AT_HORIZON:
        at_horizon = _value_at_horizon(prepared, horizon_in_months)
        outcomes = (at_horizon > threshold).where(at_horizon.notna())

    elif rule is ResolutionRule.LEVEL_ABOVE_THRESHOLD_WITHIN_HORIZON:
        highest = _forward_extreme(prepared, horizon_in_months, "max")
        outcomes = (highest > threshold).where(highest.notna())

    elif rule is ResolutionRule.LEVEL_BELOW_THRESHOLD_WITHIN_HORIZON:
        lowest = _forward_extreme(prepared, horizon_in_months, "min")
        outcomes = (lowest < threshold).where(lowest.notna())

    else:  # pragma: no cover - the enum is exhaustive and the registry validates it
        raise ResolutionError(f"no implementation for resolution rule {rule!r}")

    return ResolvedOutcomes(
        indicator_name=indicator.name,
        horizon_in_months=horizon_in_months,
        outcomes=outcomes.astype("float64").rename(indicator.name),
    )


def resolve_all(
    indicators: Sequence[BinaryIndicator],
    series_by_name: dict[str, pd.Series],
    horizons_in_months: Sequence[int],
) -> dict[tuple[str, int], ResolvedOutcomes]:
    """Resolve every indicator at every horizon, keyed by name and horizon."""
    resolved: dict[tuple[str, int], ResolvedOutcomes] = {}
    for indicator in indicators:
        source_name = indicator.resolution.series
        if source_name not in series_by_name:
            raise ResolutionError(
                f"indicator {indicator.name!r} needs series {source_name!r}, which was not "
                f"loaded. Loaded series are {sorted(series_by_name)}."
            )
        for horizon in horizons_in_months:
            resolved[(indicator.name, horizon)] = resolve(
                indicator, series_by_name[source_name], horizon
            )
    return resolved


def required_series_names(indicators: Sequence[BinaryIndicator]) -> list[str]:
    """Every series the indicator registry depends on, without duplicates."""
    seen: list[str] = []
    for indicator in indicators:
        if indicator.resolution.series not in seen:
            seen.append(indicator.resolution.series)
    return seen


def monthly_condition(indicator: BinaryIndicator, series: pd.Series) -> pd.Series:
    """Does this indicator's condition hold in each individual month?

    Every indicator reduces to one condition on one month: a value above a
    threshold, or below one. The horizon question is then built from that
    condition, either by asking about the horizon month alone or by asking whether
    it ever holds along the way.

    Separating the monthly condition from the horizon question is what lets a
    single per-regime rate serve all three horizons. The alternative, estimating a
    separate rate for each horizon, starves at ten years: an outcome resolved by a
    given date needs ten years of history after the forecast, so there are barely
    a handful of independent observations behind it.
    """
    monthly = transforms.to_month_start(series)
    if monthly.empty:
        raise ResolutionError(
            f"indicator {indicator.name!r} resolves against an empty series "
            f"{indicator.resolution.series!r}"
        )
    complete_grid = pd.date_range(monthly.index[0], monthly.index[-1], freq="MS")
    prepared = transforms.apply_transform(
        monthly.reindex(complete_grid), indicator.resolution.transform
    )
    threshold = indicator.resolution.threshold
    if threshold is None:  # pragma: no cover - the registry validates this
        raise ResolutionError(f"indicator {indicator.name!r} has no threshold")

    holds = (
        prepared > threshold
        if indicator.resolution.rule.condition_is_above_threshold
        else prepared < threshold
    )
    return holds.where(prepared.notna()).astype("float64").rename(indicator.name)
