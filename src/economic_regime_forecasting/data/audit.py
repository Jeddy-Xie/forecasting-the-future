"""Facts about the fetched data, computed rather than asserted.

The registry declares what each series should look like. This module measures
what it actually looks like and reports the difference, which is the only way a
declared start date stays true a year from now.

It also measures revisions, which is the question the vintage machinery exists to
answer: how much does a number move after it is first published? The comparison
is made on the *transformed* series rather than the raw index, because the raw
index has been rebased repeatedly and a rebasing is not a revision. Year-over-year
growth is invariant to rebasing, so a difference in growth between two vintages
is a genuine restatement of what happened.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from economic_regime_forecasting.configuration.registry import (
    EconomicSeries,
    EconomicSeriesRegistry,
)
from economic_regime_forecasting.data import federal_reserve_client, vintage
from economic_regime_forecasting.data.cache import SeriesCache
from economic_regime_forecasting.features import transforms


@dataclass(frozen=True)
class SeriesAudit:
    """What one series actually contains, against what the registry claims."""

    name: str
    series_id: str
    role: str
    frequency: str
    units: str
    transform: str
    declared_start: date
    observed_start: date
    observed_end: date
    observation_count: int
    missing_value_count: int
    publication_lag_days: int
    is_revised: bool

    @property
    def start_matches_registry(self) -> bool:
        """The registry's declared start must be the observed one, to the month."""
        return (self.declared_start.year, self.declared_start.month) == (
            self.observed_start.year,
            self.observed_start.month,
        )

    def as_row(self) -> dict[str, object]:
        return {
            "series": self.name,
            "identifier": self.series_id,
            "role": self.role,
            "frequency": self.frequency,
            "units": self.units,
            "transform": self.transform,
            "declared_start": self.declared_start,
            "observed_start": self.observed_start,
            "observed_end": self.observed_end,
            "observations": self.observation_count,
            "missing": self.missing_value_count,
            "publication_lag_days": self.publication_lag_days,
            "revised": self.is_revised,
            "start_matches_registry": self.start_matches_registry,
        }


@dataclass(frozen=True)
class RevisionAudit:
    """How much a series moved between an old vintage and today, in growth terms."""

    name: str
    series_id: str
    vintage_date: date
    policy: str
    compared_months: int
    median_absolute_revision: float
    largest_absolute_revision: float

    def as_row(self) -> dict[str, object]:
        return {
            "series": self.name,
            "vintage": self.vintage_date,
            "policy": self.policy,
            "months_compared": self.compared_months,
            "median_absolute_revision": self.median_absolute_revision,
            "largest_absolute_revision": self.largest_absolute_revision,
        }


def audit_series(registry: EconomicSeriesRegistry, cache: SeriesCache) -> list[SeriesAudit]:
    """Measure every fetched series against its registry entry."""
    audits: list[SeriesAudit] = []
    for entry in registry.series:
        snapshot = cache.get_or_fetch(
            federal_reserve_client.build_request(entry.series_id),
            federal_reserve_client.fetcher_for(entry.units),
        )
        observations = snapshot.observations
        audits.append(
            SeriesAudit(
                name=entry.name,
                series_id=entry.series_id,
                role=entry.role,
                frequency=entry.frequency,
                units=entry.units,
                transform=entry.transform.value,
                declared_start=entry.observation_start,
                observed_start=observations.index[0].date(),
                observed_end=observations.index[-1].date(),
                observation_count=int(observations.size),
                missing_value_count=int(observations.isna().sum()),
                publication_lag_days=entry.publication_lag_days,
                is_revised=entry.is_revised,
            )
        )
    return audits


def audit_revisions(
    registry: EconomicSeriesRegistry,
    cache: SeriesCache,
    vintage_dates: Sequence[date],
) -> list[RevisionAudit]:
    """Compare each revisable series' past vintages with today's, in growth terms."""
    audits: list[RevisionAudit] = []
    for entry in registry.series:
        if not entry.is_revised:
            continue
        latest = _transformed_today(entry, cache)
        for vintage_date in vintage_dates:
            observed = vintage.observe(entry, vintage_date, cache)
            then = transforms.apply_transform(
                transforms.to_month_start(observed.observations), entry.transform
            ).dropna()
            aligned_then, aligned_now = then.align(latest, join="inner")
            if aligned_then.empty:
                continue
            differences = np.abs(aligned_now.to_numpy() - aligned_then.to_numpy())
            audits.append(
                RevisionAudit(
                    name=entry.name,
                    series_id=entry.series_id,
                    vintage_date=vintage_date,
                    policy=observed.policy.value,
                    compared_months=int(differences.size),
                    median_absolute_revision=float(np.nanmedian(differences)),
                    largest_absolute_revision=float(np.nanmax(differences)),
                )
            )
    return audits


def _transformed_today(entry: EconomicSeries, cache: SeriesCache) -> pd.Series:
    snapshot = cache.get_or_fetch(
        federal_reserve_client.build_request(entry.series_id),
        federal_reserve_client.fetcher_for(entry.units),
    )
    return transforms.apply_transform(
        transforms.to_month_start(snapshot.observations), entry.transform
    ).dropna()


def audit_table(audits: Sequence[SeriesAudit]) -> pd.DataFrame:
    return pd.DataFrame([item.as_row() for item in audits])


def revision_table(audits: Sequence[RevisionAudit]) -> pd.DataFrame:
    return pd.DataFrame([item.as_row() for item in audits])
