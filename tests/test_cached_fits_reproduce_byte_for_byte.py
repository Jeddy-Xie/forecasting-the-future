"""A cached fit, refitted from scratch, is byte-identical to the one on disk.

Written when the expectation-maximisation loop began using the monotonicity
allowance ADR 0007 decided on: a fall of up to a thousandth of the likelihood,
where the loop had kept a hard millionth. A raise aborts the whole fit, so every
fit that succeeded under the stricter guard never saw a fall between the two, and
takes the identical path under the wider one. This proves that on two real refits
rather than asserting it.

It reads the live cache and writes only to a temporary directory. It skips itself
on a checkout that has never run `forecast fetch-data` and `forecast backtest`.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from economic_regime_forecasting.backtest import walk_forward
from economic_regime_forecasting.configuration.registry import load_registries
from economic_regime_forecasting.configuration.run_settings import DEFAULT_RUN_SETTINGS
from economic_regime_forecasting.data.cache import ArtifactStore, SeriesCache

pytestmark = [
    pytest.mark.skipif(
        not DEFAULT_RUN_SETTINGS.cache.vintage.exists(),
        reason="no .cache/vintage on this checkout; run `forecast fetch-data` first",
    ),
    pytest.mark.slow,
]

STATE_COUNT = 6
"""The count the burn-in window chooses under the default configuration."""


@pytest.mark.parametrize("as_of", [date(1994, 3, 1), date(2020, 3, 1)])
def test_a_refit_from_scratch_reproduces_the_cached_model_byte_for_byte(
    as_of: date, tmp_path: Path
) -> None:
    settings = DEFAULT_RUN_SETTINGS
    name = (
        f"model_{as_of.isoformat()}_states{STATE_COUNT}_seed{settings.random_seed}"
        f"_{settings.configuration_hash()}.json"
    )
    cached = ArtifactStore(settings.cache.models)
    if not cached.has(name):
        pytest.skip(f"{name} is not cached on this checkout; run `forecast backtest` first")

    registry, indicators = load_registries()
    cache = SeriesCache(settings.cache.raw, settings.cache.vintage)
    histories = walk_forward.prepare_indicator_history(
        indicators, registry, cache, settings.forecast_horizons_in_months
    )
    fresh = ArtifactStore(tmp_path)
    walk_forward.fit_regime_model(
        as_of, registry, cache, histories, settings, STATE_COUNT, artifacts=fresh
    )

    assert cache.statistics.misses == 0
    assert fresh.path(name).read_bytes() == cached.path(name).read_bytes()
