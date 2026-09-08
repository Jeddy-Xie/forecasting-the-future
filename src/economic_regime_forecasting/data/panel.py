"""Assemble panels of economic data, always anchored to a date.

There are exactly two kinds of panel in this project and they answer different
questions:

A **point-in-time panel** is what an observer had on a given date. Every function
that builds one takes ``as_of``, and there is no code path that builds one
without it. This is what the model is fitted on.

A **final panel** is what we know today, and it exists for one purpose: to
resolve what actually happened, so a forecast made in 1975 can be scored. It is
never an input to a fit. Keeping the two in separate functions with separate
names is the cheapest available protection against confusing them.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import pandas as pd

from economic_regime_forecasting.configuration.registry import (
    EconomicSeriesRegistry,
    RegistryError,
)
from economic_regime_forecasting.data import federal_reserve_client, vintage
from economic_regime_forecasting.data.cache import SeriesCache
from economic_regime_forecasting.data.vintage import PointInTimeSeries
from economic_regime_forecasting.features import transforms

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PointInTimePanel:
    """Several series, each as it stood on the same date."""

    as_of: date
    series: dict[str, PointInTimeSeries]

    def __getitem__(self, name: str) -> pd.Series:
        try:
            return self.series[name].observations
        except KeyError as error:
            raise RegistryError(
                f"{name!r} is not in this panel. It holds {sorted(self.series)}."
            ) from error

    def manifest(self) -> list[dict[str, object]]:
        return [item.manifest_entry() for item in self.series.values()]

    def policy_counts(self) -> dict[str, int]:
        return vintage.summarise_policies(list(self.series.values()))


def assemble_point_in_time_panel(
    registry: EconomicSeriesRegistry,
    as_of: date,
    cache: SeriesCache,
    names: Sequence[str] | None = None,
) -> PointInTimePanel:
    """Build the panel an observer would have had on ``as_of``.

    ``names`` defaults to the three series forming the model's observation
    vector, which is the only panel a fit ever needs.
    """
    wanted = list(names) if names is not None else [item.name for item in registry.model_inputs]
    observed = {name: vintage.observe(registry[name], as_of, cache) for name in wanted}
    return PointInTimePanel(as_of=as_of, series=observed)


def load_final_series(
    registry: EconomicSeriesRegistry,
    cache: SeriesCache,
    names: Sequence[str],
) -> dict[str, pd.Series]:
    """Load series as they stand today, for resolving what actually happened.

    Derived series named in the registry are materialised here too, so a caller
    can ask for the term spread without knowing it is a subtraction.
    """
    resolved: dict[str, pd.Series] = {}
    fetched: dict[str, pd.Series] = {}

    def fetch_one(name: str) -> pd.Series:
        if name in fetched:
            return fetched[name]
        entry = registry[name]
        snapshot = cache.get_or_fetch(
            federal_reserve_client.build_request(entry.series_id),
            federal_reserve_client.fetcher_for(entry.units),
        )
        series = transforms.to_month_start(snapshot.observations).rename(name)
        fetched[name] = series
        return series

    for name in names:
        derived = registry.derived_by_name(name)
        if derived is not None:
            resolved[name] = transforms.difference(
                fetch_one(derived.minuend), fetch_one(derived.subtrahend)
            ).rename(name)
        else:
            resolved[name] = fetch_one(name)
    return resolved


def latest_common_observation_date(series_by_name: dict[str, pd.Series]) -> date:
    """The most recent month every one of these series covers.

    Used to decide how far a walk-forward backtest can run and how far outcomes
    can be resolved. Taking the earliest of the individual ends is the honest
    answer; taking the latest would silently extend a panel with missing values.
    """
    if not series_by_name:
        raise RegistryError("cannot take a common end date across no series")
    ends = [series.dropna().index[-1] for series in series_by_name.values() if not series.empty]
    if not ends:
        raise RegistryError("every series is empty; nothing has been fetched")
    earliest_end: pd.Timestamp = min(ends)
    return earliest_end.date()
