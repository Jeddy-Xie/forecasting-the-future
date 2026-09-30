"""Research arm B2 of experiment 0008: the model observes what it forecasts.

With ``observe_the_unemployment_rate_and_the_term_spread`` on, the growth chain also
reads the unemployment rate and the inflation-and-rates chain also reads the
ten-year minus three-month term spread. The registration
(``proving/experiments/0008-condition-aware-regime-forecasts/experiment.json``) names
two required checks, and each has tests here:

- ``off_reproduces_main``: with the setting off, nothing moves. The digest is
  reference-0008's, the observation matrix is the three columns byte for byte, and a
  two-chain model on main's columns serialises exactly as it did.
- ``honest_start``: a series that joins the model is held to the same honest-start
  rule as the three that were always there. A synthetic unemployment vintage too
  short to fit on makes the pre-flight refuse; on the live cache the honest start is
  still 1994-03 with the setting on.

The rest pins the mechanism: which columns each chain reads, that the extra columns
are standardised on an expanding window, that the product model's likelihood and
filtered distribution still factorise with the wider blocks, and that the walk-forward,
the burn-in choice and the look-ahead audit run on the arm's configuration.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from economic_regime_forecasting import command_line_interface as interface
from economic_regime_forecasting import look_ahead_audit
from economic_regime_forecasting.backtest import schedule as schedule_module
from economic_regime_forecasting.backtest.state_count_on_burn_in import (
    choose_state_count_on_burn_in_window,
)
from economic_regime_forecasting.backtest.walk_forward import (
    find_first_fully_point_in_time_date,
    fit_regime_model,
    forecast_dates_using_the_publication_lag_fallback,
    prepare_indicator_history,
    run_walk_forward,
)
from economic_regime_forecasting.configuration import registry as registry_module
from economic_regime_forecasting.configuration.registry import (
    BinaryIndicator,
    Composition,
    DerivedSeries,
    EconomicSeries,
    EconomicSeriesRegistry,
    IndicatorResolution,
    ModelDimension,
    RegistryError,
    ResolutionRule,
    Transform,
    load_economic_series_registry,
    load_registries,
)
from economic_regime_forecasting.configuration.run_settings import (
    DEFAULT_RUN_SETTINGS,
    SETTINGS_OMITTED_FROM_THE_HASH_WHEN_THEY_HOLD_THE_SHIPPED_VALUE,
    CacheLayout,
    RunSettings,
)
from economic_regime_forecasting.data import transforms
from economic_regime_forecasting.data.cache import (
    ArtifactStore,
    SeriesCache,
    SeriesRequest,
    SeriesSnapshot,
)
from economic_regime_forecasting.data.panel import assemble_point_in_time_panel
from economic_regime_forecasting.data.vintage import LookAheadError, VintagePolicy
from economic_regime_forecasting.features.observation_matrix import (
    COLUMN_NAMES,
    DIMENSION_ORDER,
    build_observation_matrix,
)
from economic_regime_forecasting.models import two_timescale_hidden_markov_model as two_timescale
from economic_regime_forecasting.models.gaussian_hidden_markov_model import (
    GaussianHiddenMarkovModel,
    HiddenMarkovModelError,
)
from economic_regime_forecasting.models.model_loading import regime_model_from_dictionary
from economic_regime_forecasting.models.state_labelling import describe_regimes, label_for
from economic_regime_forecasting.models.two_timescale_hidden_markov_model import (
    GROWTH_COLUMNS,
    LEVELS_COLUMNS,
    TwoChainStateCount,
    TwoTimescaleHiddenMarkovModel,
    chain_columns,
)
from economic_regime_forecasting.models.two_timescale_state_selection import (
    sweep_state_counts_for_two_chains,
)

SWITCH = "observe_the_unemployment_rate_and_the_term_spread"
REFERENCE_0008_HASH = "fec79a040f9ca6f9"
"""experiment 0008's reference_run.configuration_hash: main at the registering commit."""

ARM_DIMENSIONS = (
    ModelDimension.GROWTH,
    ModelDimension.INFLATION,
    ModelDimension.RATES,
    ModelDimension.GROWTH,
    ModelDimension.RATES,
)
"""growth, inflation, rates, then the unemployment rate and the term spread."""


def _settings(
    root: Path, observe: bool = True, separate_chains: bool = True, seed: int = 7
) -> RunSettings:
    return RunSettings(
        random_seed=seed,
        hidden_state_counts_to_search=(1, 2),
        expectation_maximisation_restarts=2,
        expectation_maximisation_max_iterations=60,
        minimum_observations_before_first_fit=120,
        refit_every_n_months=12,
        forecast_horizons_in_months=(12,),
        cache=CacheLayout(root),
        separate_chains_for_growth_and_for_inflation_with_rates=separate_chains,
        observe_the_unemployment_rate_and_the_term_spread=observe,
    )


# ------------------------------------------------------------------ settings


def test_the_setting_is_on_by_default_only_on_this_arms_branch() -> None:
    assert getattr(DEFAULT_RUN_SETTINGS, SWITCH) is True
    assert SETTINGS_OMITTED_FROM_THE_HASH_WHEN_THEY_HOLD_THE_SHIPPED_VALUE[SWITCH] is False


def test_with_the_setting_off_the_digest_is_reference_0008s() -> None:
    """off_reproduces_main, at the level of identity: off leaves no trace in the
    digest, so every cached fit and artifact of the reference is read back as its own."""
    off = dataclasses.replace(DEFAULT_RUN_SETTINGS, **{SWITCH: False})
    on = dataclasses.replace(DEFAULT_RUN_SETTINGS, **{SWITCH: True})
    assert off.configuration_hash() == REFERENCE_0008_HASH
    assert on.configuration_hash() != REFERENCE_0008_HASH


# ------------------------------------------------------------------ registry


def test_the_shipped_registry_declares_the_two_forecast_targets_on_the_registered_chains() -> None:
    """The registration: UNRATE, a revised level at a 36-day lag, joins the growth chain;
    GS10 minus TB3MS, both unrevised market data at 32 days, joins the levels chain."""
    registry, _ = load_registries()
    columns = registry.forecast_target_columns
    assert [column.name for column in columns] == [
        "unemployment_rate",
        "ten_year_minus_three_month_term_spread",
    ]
    unemployment, spread = columns
    assert unemployment.dimension is ModelDimension.GROWTH
    assert unemployment.transform is Transform.LEVEL
    assert unemployment.fetched_series == ("unemployment_rate",)
    assert registry["unemployment_rate"].series_id == "UNRATE"
    assert registry["unemployment_rate"].is_revised is True
    assert registry["unemployment_rate"].publication_lag_days == 36

    assert spread.dimension is ModelDimension.RATES
    assert spread.transform is Transform.LEVEL
    assert spread.fetched_series == ("ten_year_treasury_yield", "three_month_treasury_bill_rate")
    for leg in spread.fetched_series:
        assert registry[leg].is_revised is False
        assert registry[leg].publication_lag_days == 32
    assert [registry[leg].series_id for leg in spread.fetched_series] == ["GS10", "TB3MS"]


def test_the_registry_as_loaded_observes_the_three_dimensions_only() -> None:
    registry, _ = load_registries()
    assert registry.forecast_targets_are_observed is False
    assert [column.name for column in registry.observation_columns] == list(COLUMN_NAMES)
    assert registry.series_observed_by_the_model == registry.model_inputs


def test_configured_for_the_arm_the_registry_observes_five_columns_from_five_series() -> None:
    registry, _ = load_registries()
    arm = registry.configured_for(DEFAULT_RUN_SETTINGS)
    assert [column.name for column in arm.observation_columns] == [
        "growth",
        "inflation",
        "rates",
        "unemployment_rate",
        "ten_year_minus_three_month_term_spread",
    ]
    assert tuple(column.dimension for column in arm.observation_columns) == ARM_DIMENSIONS
    assert [entry.series_id for entry in arm.series_observed_by_the_model] == [
        "INDPRO",
        "CPIAUCSL",
        "TB3MS",
        "UNRATE",
        "GS10",
    ]
    # model_inputs keeps its contract: one series per dimension.
    assert arm.model_inputs == registry.model_inputs


def test_configured_for_is_idempotent_and_the_settings_always_win() -> None:
    registry, _ = load_registries()
    off = dataclasses.replace(DEFAULT_RUN_SETTINGS, **{SWITCH: False})
    arm = registry.configured_for(DEFAULT_RUN_SETTINGS)
    assert arm.configured_for(DEFAULT_RUN_SETTINGS) is arm
    assert registry.configured_for(off) is registry
    assert arm.configured_for(off) == registry


def test_one_chain_with_the_setting_on_is_refused_rather_than_silently_ignored() -> None:
    registry, _ = load_registries()
    one_chain = dataclasses.replace(
        DEFAULT_RUN_SETTINGS, separate_chains_for_growth_and_for_inflation_with_rates=False
    )
    with pytest.raises(RegistryError, match="one chain"):
        registry.configured_for(one_chain)
    # With the setting off as well, one chain is main's pre-A4 configuration and loads.
    both_off = dataclasses.replace(one_chain, **{SWITCH: False})
    assert registry.configured_for(both_off).observation_columns == registry.observation_columns


def test_a_registry_declaring_no_forecast_targets_is_unaffected_by_the_setting(
    three_dimension_registry: EconomicSeriesRegistry,
) -> None:
    one_chain = dataclasses.replace(
        DEFAULT_RUN_SETTINGS, separate_chains_for_growth_and_for_inflation_with_rates=False
    )
    configured = three_dimension_registry.configured_for(one_chain)
    assert configured.observation_columns == three_dimension_registry.observation_columns


def test_a_model_input_cannot_also_be_declared_a_forecast_target(tmp_path: Path) -> None:
    document = yaml.safe_load(registry_module.ECONOMIC_SERIES_FILE.read_text())
    industrial = next(
        entry for entry in document["observation_series"] if entry["series_id"] == "INDPRO"
    )
    industrial["model_dimension_when_forecast_targets_are_observed"] = "growth"
    broken = tmp_path / "doubled.yaml"
    broken.write_text(yaml.safe_dump(document))
    with pytest.raises(RegistryError, match="model input already"):
        load_economic_series_registry(broken)


def test_a_forecast_target_dimension_must_be_a_real_dimension(tmp_path: Path) -> None:
    document = yaml.safe_load(registry_module.ECONOMIC_SERIES_FILE.read_text())
    document["derived_series"][0]["model_dimension_when_forecast_targets_are_observed"] = "labour"
    broken = tmp_path / "bad_dimension.yaml"
    broken.write_text(yaml.safe_dump(document))
    with pytest.raises(RegistryError, match="labour"):
        load_economic_series_registry(broken)


# -------------------------------------------------------- which chain reads what


def test_chain_columns_on_mains_three_columns_are_the_constants() -> None:
    assert chain_columns(DIMENSION_ORDER) == (GROWTH_COLUMNS, LEVELS_COLUMNS)


def test_chain_columns_put_unemployment_with_growth_and_the_spread_with_the_levels() -> None:
    assert chain_columns(ARM_DIMENSIONS) == ((0, 3), (1, 2, 4))


def test_chain_columns_refuse_a_matrix_one_chain_would_not_read() -> None:
    with pytest.raises(HiddenMarkovModelError, match="do not split"):
        chain_columns((ModelDimension.INFLATION, ModelDimension.RATES))


# ------------------------------------------------------------ the product model

GROWTH_CHAIN_TWO_COLUMNS = GaussianHiddenMarkovModel(
    initial_distribution=np.array([0.6, 0.4]),
    transition_matrix=np.array([[0.9, 0.1], [0.2, 0.8]]),
    means=np.array([[-1.0, 0.8], [1.0, -0.6]]),
    covariances=np.array([[[0.5, -0.2], [-0.2, 0.6]], [[0.7, 0.1], [0.1, 0.4]]]),
)
LEVELS_CHAIN_THREE_COLUMNS = GaussianHiddenMarkovModel(
    initial_distribution=np.array([0.3, 0.7]),
    transition_matrix=np.array([[0.95, 0.05], [0.08, 0.92]]),
    means=np.array([[-0.5, 0.2, 0.4], [1.2, 0.9, -0.7]]),
    covariances=np.array(
        [
            [[1.0, 0.3, 0.1], [0.3, 0.7, 0.0], [0.1, 0.0, 0.5]],
            [[0.6, -0.1, 0.2], [-0.1, 0.9, 0.1], [0.2, 0.1, 0.8]],
        ]
    ),
)
FIVE_COLUMN_OBSERVATIONS = np.array(
    [
        [0.1, -0.2, 0.3, 0.5, -0.1],
        [0.9, 1.2, -0.1, -0.4, 0.6],
        [-1.1, 0.4, 0.2, 1.0, 0.3],
        [1.2, 1.6, -0.5, -0.8, -0.9],
        [0.3, -0.4, 0.1, 0.2, 0.4],
    ]
)


def _five_column_model() -> TwoTimescaleHiddenMarkovModel:
    return TwoTimescaleHiddenMarkovModel(
        GROWTH_CHAIN_TWO_COLUMNS,
        LEVELS_CHAIN_THREE_COLUMNS,
        growth_columns=(0, 3),
        levels_columns=(1, 2, 4),
    )


def test_with_wider_blocks_the_joint_likelihood_is_still_the_sum_of_the_chains() -> None:
    model = _five_column_model()
    growth = FIVE_COLUMN_OBSERVATIONS[:, [0, 3]]
    levels = FIVE_COLUMN_OBSERVATIONS[:, [1, 2, 4]]
    assert model.log_likelihood(FIVE_COLUMN_OBSERVATIONS) == pytest.approx(
        GROWTH_CHAIN_TWO_COLUMNS.log_likelihood(growth)
        + LEVELS_CHAIN_THREE_COLUMNS.log_likelihood(levels),
        rel=1e-12,
    )
    np.testing.assert_allclose(
        model.filtered_state_probabilities(FIVE_COLUMN_OBSERVATIONS),
        np.stack(
            [
                np.kron(growth_row, levels_row)
                for growth_row, levels_row in zip(
                    GROWTH_CHAIN_TWO_COLUMNS.filtered_state_probabilities(growth),
                    LEVELS_CHAIN_THREE_COLUMNS.filtered_state_probabilities(levels),
                    strict=True,
                )
            ]
        ),
        rtol=1e-10,
        atol=1e-12,
    )


def test_the_product_places_each_chains_means_on_its_own_columns() -> None:
    model = _five_column_model()
    # Joint state g * K_l + l.
    for growth_state in range(2):
        for levels_state in range(2):
            joint = growth_state * 2 + levels_state
            np.testing.assert_array_equal(
                model.means[joint, [0, 3]], GROWTH_CHAIN_TWO_COLUMNS.means[growth_state]
            )
            np.testing.assert_array_equal(
                model.means[joint, [1, 2, 4]], LEVELS_CHAIN_THREE_COLUMNS.means[levels_state]
            )
            assert model.covariances[joint][0, 1] == 0.0
            assert model.covariances[joint][3, 4] == 0.0


def test_a_column_assignment_that_does_not_share_out_every_column_is_refused() -> None:
    with pytest.raises(HiddenMarkovModelError, match="each column exactly once"):
        TwoTimescaleHiddenMarkovModel(
            GROWTH_CHAIN_TWO_COLUMNS,
            LEVELS_CHAIN_THREE_COLUMNS,
            growth_columns=(0, 3),
            levels_columns=(1, 2, 3),
        )


def test_the_column_assignment_round_trips_and_mains_payload_is_unchanged() -> None:
    wide = _five_column_model()
    payload = json.loads(json.dumps(wide.to_dictionary()))
    assert payload["growth_columns"] == [0, 3]
    assert payload["levels_columns"] == [1, 2, 4]
    restored = regime_model_from_dictionary(payload)
    assert isinstance(restored, TwoTimescaleHiddenMarkovModel)
    assert (restored.growth_columns, restored.levels_columns) == ((0, 3), (1, 2, 4))
    assert restored.to_dictionary() == wide.to_dictionary()

    # On main's three columns the payload has exactly the keys it always had, so every
    # cached fit of the reference is byte-identical when written again.
    growth = GaussianHiddenMarkovModel(
        initial_distribution=np.array([0.7, 0.3]),
        transition_matrix=np.array([[0.9, 0.1], [0.3, 0.7]]),
        means=np.array([[-1.0], [1.0]]),
        covariances=np.array([[[0.5]], [[0.8]]]),
    )
    levels = GaussianHiddenMarkovModel(
        initial_distribution=np.array([0.4, 0.6]),
        transition_matrix=np.array([[0.95, 0.05], [0.1, 0.9]]),
        means=np.array([[-0.5, 0.2], [1.5, -0.3]]),
        covariances=np.array([[[1.0, 0.3], [0.3, 0.7]], [[0.6, -0.1], [-0.1, 0.9]]]),
    )
    mains = TwoTimescaleHiddenMarkovModel(growth, levels).to_dictionary()
    assert set(mains) == {"model_class", "growth_chain", "levels_chain", "fit_report"}


def _simulated_five_column_sample(months: int = 240, seed: int = 13) -> np.ndarray:
    generator = np.random.default_rng(seed)
    growth_transitions = np.array([[0.9, 0.1], [0.15, 0.85]])
    levels_transitions = np.array([[0.97, 0.03], [0.04, 0.96]])
    growth_means = np.array([[-1.0, 0.9], [1.0, -0.7]])
    levels_means = np.array([[-1.0, -0.8, 0.6], [1.2, 1.0, -0.5]])
    growth_state = levels_state = 0
    rows = []
    for _ in range(months):
        growth_state = int(generator.choice(2, p=growth_transitions[growth_state]))
        levels_state = int(generator.choice(2, p=levels_transitions[levels_state]))
        growth = generator.multivariate_normal(growth_means[growth_state], 0.2 * np.eye(2))
        levels = generator.multivariate_normal(levels_means[levels_state], 0.2 * np.eye(3))
        rows.append([growth[0], levels[0], levels[1], growth[1], levels[2]])
    return np.array(rows)


def test_the_fit_reads_each_chains_block_and_is_deterministic() -> None:
    sample = _simulated_five_column_sample()
    first = two_timescale.fit(
        sample, 2, 2, seed=9, restarts=3, growth_columns=(0, 3), levels_columns=(1, 2, 4)
    )
    second = two_timescale.fit(
        sample, 2, 2, seed=9, restarts=3, growth_columns=(0, 3), levels_columns=(1, 2, 4)
    )
    assert first.to_dictionary() == second.to_dictionary()
    assert first.growth_chain.dimension_count == 2
    assert first.levels_chain.dimension_count == 3
    assert (first.growth_columns, first.levels_columns) == ((0, 3), (1, 2, 4))
    # The growth chain found the growth block's two regimes: canonical order sorts
    # them by the growth column, and the unemployment-like column moves against it.
    growth_means = first.growth_chain.means
    assert growth_means[0, 0] < growth_means[1, 0]
    assert growth_means[0, 1] > growth_means[1, 1]


def test_the_sweep_on_wider_blocks_recommends_a_model_with_the_same_blocks() -> None:
    sample = _simulated_five_column_sample()
    sweep = sweep_state_counts_for_two_chains(
        sample, (1, 2), seed=7, restarts=2, growth_columns=(0, 3), levels_columns=(1, 2, 4)
    )
    model = sweep.recommended_model
    assert (model.growth_columns, model.levels_columns) == ((0, 3), (1, 2, 4))
    assert model.dimension_count == 5


def test_regimes_are_labelled_by_every_column_they_are_described_in() -> None:
    names = (
        "growth",
        "inflation",
        "rates",
        "unemployment_rate",
        "ten_year_minus_three_month_term_spread",
    )
    assert label_for(np.array([-1.0, 0.0, 0.9, 1.3, -0.8]), names) == (
        "contracting growth, moderate inflation, high rates, high unemployment rate, "
        "low ten year minus three month term spread"
    )
    model = _five_column_model()
    descriptions = describe_regimes(
        model, FIVE_COLUMN_OBSERVATIONS, FIVE_COLUMN_OBSERVATIONS, column_names=names
    )
    assert len(descriptions) == 4
    row = descriptions[0].as_row()
    assert "unemployment_rate_standardised" in row
    assert "ten_year_minus_three_month_term_spread_natural" in row
    assert descriptions[0].compact_label.count(",") == 4


# ------------------------------------------------ a synthetic cache for the wiring

FIRST_FORECAST = date(2000, 1, 1)
CUTOFF = date(2001, 1, 1)
SHORTENED_UNEMPLOYMENT_VINTAGE = date(2000, 6, 1)


def _entry(
    name: str,
    series_id: str,
    dimension: ModelDimension | None,
    transform: Transform,
    revised: bool,
    forecast_target_dimension: ModelDimension | None = None,
) -> EconomicSeries:
    return EconomicSeries(
        name=name,
        series_id=series_id,
        description=f"synthetic {name}",
        role="test",
        model_dimension=dimension,
        frequency="monthly",
        units="units",
        transform=transform,
        publication_lag_days=45,
        observation_start=date(1960, 1, 1),
        is_revised=revised,
        model_dimension_when_forecast_targets_are_observed=forecast_target_dimension,
    )


@pytest.fixture(scope="module")
def registry() -> EconomicSeriesRegistry:
    """Three dimensions, plus a revised unemployment series and an unrevised long rate
    whose difference from the short rate is a spread, both declared as forecast targets."""
    change = Transform.YEAR_OVER_YEAR_LOG_CHANGE
    return EconomicSeriesRegistry(
        series=(
            _entry("synthetic_output", "SYNOUT", ModelDimension.GROWTH, change, True),
            _entry("synthetic_prices", "SYNCPI", ModelDimension.INFLATION, change, True),
            _entry("synthetic_rate", "SYNRATE", ModelDimension.RATES, Transform.LEVEL, False),
            _entry(
                "synthetic_unemployment",
                "SYNUNEMP",
                None,
                Transform.LEVEL,
                True,
                forecast_target_dimension=ModelDimension.GROWTH,
            ),
            _entry("synthetic_long_rate", "SYNLONG", None, Transform.LEVEL, False),
        ),
        derived=(
            DerivedSeries(
                name="synthetic_spread",
                description="synthetic long rate minus synthetic rate",
                operation="difference",
                minuend="synthetic_long_rate",
                subtrahend="synthetic_rate",
                units="percentage points",
                model_dimension_when_forecast_targets_are_observed=ModelDimension.RATES,
            ),
        ),
    )


@pytest.fixture(scope="module")
def indicators() -> tuple[BinaryIndicator, ...]:
    def indicator(
        name: str, series: str, rule: ResolutionRule, threshold: float, composition: Composition
    ) -> BinaryIndicator:
        return BinaryIndicator(
            name=name,
            question=name.replace("_", " "),
            resolution=IndicatorResolution(
                series=series, rule=rule, transform=Transform.LEVEL, threshold=threshold
            ),
            composition=composition,
            horizons_in_years=(1,),
        )

    return (
        indicator(
            "unemployment_above_six_at_horizon",
            "synthetic_unemployment",
            ResolutionRule.LEVEL_ABOVE_THRESHOLD_AT_HORIZON,
            6.0,
            Composition.POINT_IN_TIME,
        ),
        indicator(
            "spread_below_zero_within_horizon",
            "synthetic_spread",
            ResolutionRule.LEVEL_BELOW_THRESHOLD_WITHIN_HORIZON,
            0.0,
            Composition.ANY_TIME_WITHIN_HORIZON,
        ),
    )


def _snapshot(
    values: pd.Series, series_id: str, vintage_date: date | None = None
) -> SeriesSnapshot:
    return SeriesSnapshot(
        request=SeriesRequest(
            source="federal_reserve_economic_data",
            series_id=series_id,
            transform="as_published",
            vintage_date=vintage_date,
        ),
        observations=values.rename(series_id),
        source_url=f"https://example.invalid/{series_id}",
        units="units",
        retrieved_at=datetime(2026, 9, 29, tzinfo=UTC),
        payload_digest="0" * 64,
    )


def _synthetic_values() -> dict[str, pd.Series]:
    """Output and unemployment on a fast chain; prices, the short rate and the long
    rate on a slow one, the long rate above the short one except in a tight regime."""
    index = pd.date_range("1960-01-01", "2004-12-01", freq="MS", name="observation_date")
    generator = np.random.default_rng(20260929)
    fast = np.array([[0.92, 0.08], [0.12, 0.88]])
    slow = np.array([[0.98, 0.02], [0.03, 0.97]])
    growth_state = levels_state = 0
    output, prices = [100.0], [100.0]
    rate, long_rate, unemployment = [], [], []
    for _ in range(len(index)):
        growth_state = int(generator.choice(2, p=fast[growth_state]))
        levels_state = int(generator.choice(2, p=slow[levels_state]))
        output.append(output[-1] * (1.0 + (0.004 if growth_state == 0 else -0.002)))
        prices.append(prices[-1] * (1.0 + (0.002 if levels_state == 0 else 0.006)))
        short = (4.5 if levels_state == 0 else 0.6) + float(generator.normal(0, 0.2))
        rate.append(max(short, 0.0))
        long_rate.append(max(short, 0.0) + (1.5 if levels_state == 0 else -0.3))
        unemployment.append((4.5 if growth_state == 0 else 7.0) + float(generator.normal(0, 0.3)))
    return {
        "SYNOUT": pd.Series(output[1:], index=index),
        "SYNCPI": pd.Series(prices[1:], index=index),
        "SYNRATE": pd.Series(rate, index=index),
        "SYNLONG": pd.Series(long_rate, index=index),
        "SYNUNEMP": pd.Series(unemployment, index=index),
    }


def _write_cache(root: Path, shorten_unemployment_at: date | None = None) -> None:
    cache = look_ahead_audit.series_cache_at(root)
    values = _synthetic_values()
    for series_id, series in values.items():
        cache.write(_snapshot(series, series_id))
    for series_id in ("SYNOUT", "SYNCPI", "SYNUNEMP"):
        series = values[series_id]
        for stamp in pd.date_range("1999-01-01", "2003-12-01", freq="MS"):
            as_published = series[series.index < stamp - pd.DateOffset(months=1)]
            if series_id == "SYNUNEMP" and stamp.date() == shorten_unemployment_at:
                # What the archive does before it has a usable vintage: a short,
                # recent window that parses cleanly and is too short to fit on.
                as_published = as_published.iloc[-20:]
            cache.write(_snapshot(as_published, series_id, stamp.date()))


@pytest.fixture(scope="module")
def source_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("observe_what_is_forecast_cache")
    _write_cache(root)
    return root


@pytest.fixture(scope="module")
def shortened_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("observe_what_is_forecast_short_vintage")
    _write_cache(root, shorten_unemployment_at=SHORTENED_UNEMPLOYMENT_VINTAGE)
    return root


def _schedule(_cache: object = None) -> schedule_module.ForecastSchedule:
    return schedule_module.build_schedule(FIRST_FORECAST, date(2001, 6, 1), 12)


# ------------------------------------------------------------ the matrix


def test_with_the_setting_off_the_matrix_is_mains_three_columns_byte_for_byte(
    registry: EconomicSeriesRegistry, source_root: Path, tmp_path: Path
) -> None:
    """off_reproduces_main, at the level of the data the model reads: a registry that
    declares forecast targets, configured off, builds exactly the matrix a registry
    that never heard of them builds."""
    cache = look_ahead_audit.series_cache_at(source_root)
    off = registry.configured_for(_settings(tmp_path, observe=False))
    never_heard = EconomicSeriesRegistry(series=registry.series[:3], derived=())
    as_of = date(2000, 7, 1)
    from_off = build_observation_matrix(assemble_point_in_time_panel(off, as_of, cache), off)
    from_three = build_observation_matrix(
        assemble_point_in_time_panel(never_heard, as_of, cache), never_heard
    )
    pd.testing.assert_frame_equal(from_off.standardised, from_three.standardised, check_exact=True)
    pd.testing.assert_frame_equal(from_off.transformed, from_three.transformed, check_exact=True)
    assert from_off.column_dimensions == DIMENSION_ORDER
    assert from_off.column_names == COLUMN_NAMES


def test_with_the_setting_on_the_matrix_carries_both_forecast_targets(
    registry: EconomicSeriesRegistry, source_root: Path, tmp_path: Path
) -> None:
    cache = look_ahead_audit.series_cache_at(source_root)
    arm = registry.configured_for(_settings(tmp_path))
    as_of = date(2000, 7, 1)
    panel = assemble_point_in_time_panel(arm, as_of, cache)
    assert set(panel.series) == {
        "synthetic_output",
        "synthetic_prices",
        "synthetic_rate",
        "synthetic_unemployment",
        "synthetic_long_rate",
    }
    assert panel.series["synthetic_unemployment"].policy is VintagePolicy.ARCHIVAL_VINTAGE
    matrix = build_observation_matrix(panel, arm)
    assert matrix.column_names == (
        "growth",
        "inflation",
        "rates",
        "synthetic_unemployment",
        "synthetic_spread",
    )
    assert matrix.column_dimensions == ARM_DIMENSIONS
    spread = transforms.difference(panel["synthetic_long_rate"], panel["synthetic_rate"])
    np.testing.assert_array_equal(
        matrix.transformed["synthetic_spread"].to_numpy(),
        spread.loc[matrix.dates].to_numpy(),
    )
    np.testing.assert_array_equal(
        matrix.transformed["synthetic_unemployment"].to_numpy(),
        panel["synthetic_unemployment"].loc[matrix.dates].to_numpy(),
    )
    assert matrix.dates[-1] < pd.Timestamp(as_of)


def test_the_forecast_target_columns_are_standardised_on_an_expanding_window(
    registry: EconomicSeriesRegistry, source_root: Path, tmp_path: Path
) -> None:
    """Row t is scaled by rows up to t only: the matrix as of an earlier date is the
    head of the matrix as of a later one, wherever the data did not change between.
    The long and short rates are never revised, so the spread's column must agree
    exactly on every shared month."""
    cache = look_ahead_audit.series_cache_at(source_root)
    arm = registry.configured_for(_settings(tmp_path))
    earlier = build_observation_matrix(
        assemble_point_in_time_panel(arm, date(1999, 6, 1), cache), arm
    )
    later = build_observation_matrix(
        assemble_point_in_time_panel(arm, date(2003, 6, 1), cache), arm
    )
    assert later.dates[0] == earlier.dates[0]
    shared = earlier.dates
    pd.testing.assert_series_equal(
        earlier.standardised["synthetic_spread"],
        later.standardised["synthetic_spread"].loc[shared],
        check_exact=True,
    )
    pd.testing.assert_series_equal(
        earlier.standardised["rates"], later.standardised["rates"].loc[shared], check_exact=True
    )


# ------------------------------------------------------------ honest start


def test_a_short_unemployment_vintage_is_found_by_the_fallback_scan_only_when_observed(
    registry: EconomicSeriesRegistry, shortened_root: Path, tmp_path: Path
) -> None:
    """honest_start: the scan that decides the honest start reads every series the
    model will observe. Off, the unemployment series is not read, so its short vintage
    is irrelevant; on, the date it falls back on is found."""
    cache = look_ahead_audit.series_cache_at(shortened_root)
    dates = _schedule().forecast_dates
    on = registry.configured_for(_settings(tmp_path))
    off = registry.configured_for(_settings(tmp_path, observe=False))
    assert forecast_dates_using_the_publication_lag_fallback(on, cache, dates) == [
        SHORTENED_UNEMPLOYMENT_VINTAGE
    ]
    assert forecast_dates_using_the_publication_lag_fallback(off, cache, dates) == []
    assert find_first_fully_point_in_time_date(
        registry, cache, _settings(tmp_path), FIRST_FORECAST, date(2001, 6, 1)
    ) == date(2000, 7, 1)
    assert (
        find_first_fully_point_in_time_date(
            registry, cache, _settings(tmp_path, observe=False), FIRST_FORECAST, date(2001, 6, 1)
        )
        == FIRST_FORECAST
    )


def test_the_walk_forward_refuses_to_run_the_arm_on_the_publication_lag_fallback(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    shortened_root: Path,
    tmp_path: Path,
) -> None:
    """The registration: the arm is never run on the fallback ADR 0008 closed. The
    pre-flight names the date, before any fit, whichever registry the caller passed."""
    cache = look_ahead_audit.series_cache_at(shortened_root)
    schedule = _schedule()
    as_loaded = registry.configured_for(_settings(tmp_path, observe=False))
    with pytest.raises(LookAheadError, match="2000-06"):
        run_walk_forward(
            as_loaded,
            indicators,
            cache,
            _settings(tmp_path),
            TwoChainStateCount(2, 2),
            schedule.forecast_dates,
            schedule.refit_dates,
            progress_every=0,
        )


# ------------------------------------------------------------ the wiring


def test_the_burn_in_choice_sweeps_each_chain_on_its_widened_block(
    registry: EconomicSeriesRegistry, source_root: Path, tmp_path: Path
) -> None:
    cache = look_ahead_audit.series_cache_at(source_root)
    settings = _settings(tmp_path)
    choice = choose_state_count_on_burn_in_window(registry, cache, settings, FIRST_FORECAST)
    assert isinstance(choice.state_count, TwoChainStateCount)
    assert choice.panel_end < FIRST_FORECAST
    assert len(choice.sweep_rows) == 4
    # Two columns in the growth chain and three in the levels chain: a two-state
    # full-covariance chain has 1 initial and 2 transition parameters, 2 x D means
    # and 2 x D(D+1)/2 covariance parameters.
    growth_two_states = next(row for row in choice.growth_chain_sweep_rows if row["states"] == 2)
    assert growth_two_states["free_parameters"] == 1 + 2 + 4 + 6
    levels_two_states = next(row for row in choice.levels_chain_sweep_rows if row["states"] == 2)
    assert levels_two_states["free_parameters"] == 1 + 2 + 6 + 12


def test_the_walk_forward_fits_the_arms_model_and_reads_it_back_identically(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    source_root: Path,
    tmp_path: Path,
) -> None:
    cache = look_ahead_audit.series_cache_at(source_root)
    settings = _settings(tmp_path)
    schedule = _schedule()
    models = tmp_path / "models"

    def run() -> pd.DataFrame:
        return run_walk_forward(
            registry,
            indicators,
            cache,
            settings,
            TwoChainStateCount(2, 2),
            schedule.forecast_dates,
            schedule.refit_dates,
            artifacts=ArtifactStore(models),
            progress_every=0,
        )

    fresh = run()
    written = sorted(path.name for path in models.glob("model_*.json"))
    assert len(written) == 2
    loaded = regime_model_from_dictionary(ArtifactStore(models).read_json(written[0]))
    assert isinstance(loaded, TwoTimescaleHiddenMarkovModel)
    assert (loaded.growth_columns, loaded.levels_columns) == ((0, 3), (1, 2, 4))
    assert loaded.dimension_count == 5
    pd.testing.assert_frame_equal(fresh, run())
    assert fresh["predicted_probability"].between(0.0, 1.0).all()
    assert fresh["configuration_hash"].unique().tolist() == [settings.configuration_hash()]


def test_the_refit_learns_its_rates_on_the_arms_filtered_distribution(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    source_root: Path,
    tmp_path: Path,
) -> None:
    """The per-regime rates are read against the filtered distribution of the model
    that observes the targets, whichever registry the caller passed in."""
    cache = look_ahead_audit.series_cache_at(source_root)
    settings = _settings(tmp_path)
    histories = prepare_indicator_history(indicators, registry, cache, (12,))
    fitted = fit_regime_model(
        date(2000, 1, 1), registry, cache, histories, settings, TwoChainStateCount(2, 1)
    )
    assert fitted.model.dimension_count == 5
    assert isinstance(fitted.model, TwoTimescaleHiddenMarkovModel)
    assert fitted.model.growth_columns == (0, 3)


def test_the_look_ahead_audit_passes_on_the_arms_configuration(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    source_root: Path,
    tmp_path: Path,
) -> None:
    """The deterministic half of the void rule at unit scale, with the unemployment
    series and both legs of the spread in the perturbed cache."""
    audit = look_ahead_audit.audit_look_ahead(
        registry.configured_for(_settings(tmp_path / "unused")),
        indicators,
        look_ahead_audit.series_cache_at(source_root),
        _settings(tmp_path / "unused"),
        _schedule,
        tmp_path / "audit",
        cutoff=CUTOFF,
    )
    assert audit.exit_code == 0
    assert audit.moved == ()
    assert audit.perturbation.publication_lag_days_by_series is not None
    assert {"SYNUNEMP", "SYNLONG"} <= set(audit.perturbation.publication_lag_days_by_series)
    assert audit.original.fits_computed == 2


# ------------------------------------------------------------ the live cache

LIVE = pytest.mark.skipif(
    not DEFAULT_RUN_SETTINGS.cache.vintage.exists(),
    reason="no .cache/vintage on this checkout; run `forecast fetch-data` first",
)


@LIVE
@pytest.mark.slow
def test_on_the_live_cache_the_arms_honest_start_is_still_1994_03() -> None:
    """honest_start, against the real archive: with the unemployment rate observed, the
    honest start is 1994-03, every forecast date from it to 2026-09 has a usable
    UNRATE archival vintage, and none uses the publication-lag fallback."""
    workspace = interface.Workspace.open(DEFAULT_RUN_SETTINGS)
    assert workspace.registry.forecast_targets_are_observed
    schedule = workspace.backtest_schedule(date(2026, 9, 1))
    assert schedule.forecast_dates[0] == pd.Timestamp("1994-03-01")
    assert schedule.forecast_dates[-1] == pd.Timestamp("2026-09-01")
    assert len(schedule.forecast_dates) == 391
    assert (
        forecast_dates_using_the_publication_lag_fallback(
            workspace.registry, workspace.cache, schedule.forecast_dates
        )
        == []
    )
    cache = SeriesCache(DEFAULT_RUN_SETTINGS.cache.raw, DEFAULT_RUN_SETTINGS.cache.vintage)
    unemployment = workspace.registry["unemployment_rate"]
    for stamp in schedule.forecast_dates[::12]:
        panel = assemble_point_in_time_panel(workspace.registry, stamp.date(), cache)
        assert panel.series["unemployment_rate"].policy is VintagePolicy.ARCHIVAL_VINTAGE
        assert panel.series["unemployment_rate"].series_id == unemployment.series_id


@LIVE
@pytest.mark.slow
def test_on_the_live_cache_the_arms_matrix_starts_where_the_ten_year_yield_allows() -> None:
    """The spread's ten-year leg begins in 1953-04, so the aligned columns start there
    and the expanding standardisation's three-year minimum puts the first row at
    1956-03, where main's is 1950-12. Measured, not assumed."""
    workspace = interface.Workspace.open(DEFAULT_RUN_SETTINGS)
    matrix = workspace.observation_matrix_as_of(date(1994, 3, 1))
    assert matrix.dates[0] == pd.Timestamp("1956-03-01")
    assert matrix.dates[-1] == pd.Timestamp("1994-01-01")
    assert matrix.column_dimensions == ARM_DIMENSIONS
