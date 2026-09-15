"""The look-ahead audit catches an off-by-one at the direct horizon rates' boundary.

Research arm A5 learns each horizon's rate from outcomes, so its one new way to
leak is admitting an outcome before the value it rests on was published. This
injects the two likeliest versions of that mistake and requires the audit, the
deterministic half of experiment 0002's VOID rule, to exit 1 on each:

1. the publication lag ignored, so an outcome enters once its deciding value is
   labelled rather than once it is published;
2. the horizon one month short, so an outcome enters a month early.

The audited window is the synthetic one ``test_look_ahead_audit.py`` builds,
reused rather than rebuilt: refits on 2000-01-01, 2001-01-01 and the cutoff
2002-01-01, with a 45-day lag on every series. Around the cutoff the synthetic
rate sits in its low regime (0.34 labelled 2001-12, 0.72 labelled 2002-01), so a
leaked twelve-month "rate above three" outcome resting on either value turns from
no into yes when perturbed. Each leak therefore moves that indicator's forecast on
the cutoff and nothing earlier: at the 2001-01-01 refit, whatever a leak admits
had been published by the cutoff, so it is unperturbed.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from economic_regime_forecasting import look_ahead_audit
from economic_regime_forecasting.backtest import walk_forward
from economic_regime_forecasting.backtest.walk_forward import IndicatorHistory
from economic_regime_forecasting.configuration.registry import (
    BinaryIndicator,
    EconomicSeriesRegistry,
)
from economic_regime_forecasting.configuration.run_settings import RunSettings
from tests import test_look_ahead_audit as audit_suite

registry = audit_suite.registry
indicators = audit_suite.indicators
source_root = audit_suite.source_root
settings = audit_suite.settings


def _admitted_once_labelled(
    history: IndicatorHistory, horizon_in_months: int, as_of: date
) -> pd.Series:
    """Leak 1: the deciding value's label, with its publication lag forgotten."""
    outcomes = history.outcomes_by_horizon[horizon_in_months]
    deciding_labels = pd.DatetimeIndex(outcomes.index) + pd.DateOffset(months=horizon_in_months)
    return outcomes[deciding_labels <= pd.Timestamp(as_of)].dropna()


def _admitted_one_month_early(
    history: IndicatorHistory, horizon_in_months: int, as_of: date
) -> pd.Series:
    """Leak 2: the publication lag kept, the horizon counted one month short."""
    outcomes = history.outcomes_by_horizon[horizon_in_months]
    deciding_labels = pd.DatetimeIndex(outcomes.index) + pd.DateOffset(months=horizon_in_months - 1)
    published = deciding_labels + pd.Timedelta(days=history.publication_lag_days)
    return outcomes[published <= pd.Timestamp(as_of)].dropna()


def _audit(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    source_root: Path,
    settings: RunSettings,
    directory: Path,
) -> look_ahead_audit.LookAheadAudit:
    return look_ahead_audit.audit_look_ahead(
        registry,
        indicators,
        look_ahead_audit.series_cache_at(source_root),
        settings,
        audit_suite._configured_schedule,
        directory,
        cutoff=audit_suite.CUTOFF,
    )


@pytest.mark.parametrize(
    "leaky_boundary",
    [_admitted_once_labelled, _admitted_one_month_early],
    ids=["publication_lag_ignored", "horizon_one_month_short"],
)
def test_an_off_by_one_at_the_direct_rate_boundary_fails_the_audit(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    source_root: Path,
    settings: RunSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    leaky_boundary: Callable[[IndicatorHistory, int, date], pd.Series],
) -> None:
    assert settings.estimate_each_horizon_rate_directly is True
    monkeypatch.setattr(walk_forward, "outcomes_available_at", leaky_boundary)

    audit = _audit(registry, indicators, source_root, settings, tmp_path)

    assert audit.exit_code == 1
    assert {row.forecast_date for row in audit.moved} == {audit_suite.CUTOFF}
    # Only the forecast moves: the benchmark calls the shared boundary directly,
    # not through the patched function, so it stays honest and does not move.
    assert {move.field for row in audit.moved for move in row.moves} == {"predicted_probability"}
    assert "rate_above_three_at_horizon" in {row.indicator for row in audit.moved}


def test_the_honest_boundary_passes_the_same_audit(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    source_root: Path,
    settings: RunSettings,
    tmp_path: Path,
) -> None:
    """The control: the same window, the direct rates on, nothing patched."""
    assert settings.estimate_each_horizon_rate_directly is True
    audit = _audit(registry, indicators, source_root, settings, tmp_path)
    assert audit.exit_code == 0
    assert audit.moved == ()
