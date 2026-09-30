"""Research arm B1 of experiment 0008: point-in-time questions through the condition chain.

The registration (proving/experiments/0008-condition-aware-regime-forecasts/experiment.json)
changes one thing. A point-in-time question -- does the condition hold in the single
month at the horizon -- is composed through the joint regime-by-condition chain,
started from the model's filtered regime distribution and the last published value
of the condition, stepped over the publication gap and then the horizon, with the
entry hazard and persistence the any-time path already estimates. Any-time questions
are unchanged.

Its two required checks are pinned here:

- **function-level identity**: at one regime, B1's composition equals the reference
  chain's on the same rates, bit for bit (array equality, never a tolerance);
- **end-to-end identity**, at unit scale on synthetic data: a one-regime walk-forward
  with the setting on writes point-in-time forecasts equal, by array equality, to the
  reference chain at refit cadence, and any-time forecasts equal to main's own
  composition at one regime. The same check on the real cache is the arm's
  pre-registered diagnostic, run by a script under research/arms/.

The rest pin that the setting reaches both places a point-in-time forecast is
composed -- the walk-forward and `forecast forecast-now` -- that it moves nothing
else, that the look-ahead audit still passes with it on, and that it is off at main's
configuration hash.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from economic_regime_forecasting import command_line_interface, look_ahead_audit
from economic_regime_forecasting.backtest import schedule as schedule_module
from economic_regime_forecasting.backtest import walk_forward
from economic_regime_forecasting.backtest.walk_forward import (
    RESULT_COLUMNS,
    ConditionChainCadence,
    run_walk_forward,
)
from economic_regime_forecasting.configuration.registry import (
    BinaryIndicator,
    Composition,
    EconomicSeries,
    EconomicSeriesRegistry,
    IndicatorResolution,
    ModelDimension,
    ResolutionRule,
    Transform,
)
from economic_regime_forecasting.configuration.run_settings import (
    ARTIFACTS,
    DEFAULT_RUN_SETTINGS,
    SETTINGS_OMITTED_FROM_THE_HASH_WHEN_THEY_HOLD_THE_SHIPPED_VALUE,
    CacheLayout,
    RunSettings,
)
from economic_regime_forecasting.data.cache import ArtifactStore, SeriesRequest, SeriesSnapshot
from economic_regime_forecasting.models import gaussian_hidden_markov_model as hidden_markov
from economic_regime_forecasting.models.gaussian_hidden_markov_model import (
    GaussianHiddenMarkovModel,
)
from economic_regime_forecasting.models.indicator_forecast import (
    SINGLE_REGIME_DISTRIBUTION,
    SINGLE_REGIME_TRANSITION_MATRIX,
    ForecastCompositionError,
    compose_through_the_condition_chain,
    estimate_conditional_rates,
    forecast_indicator,
)

SETTING = "compose_point_in_time_questions_through_the_condition_chain"
REFERENCE_0008_HASH = "fec79a040f9ca6f9"
"""baselines/reference-0008.json's configuration hash: main when this arm was cut."""


# ------------------------------------------------------------ function level


def _indicator(composition: Composition) -> BinaryIndicator:
    rule = (
        ResolutionRule.LEVEL_ABOVE_THRESHOLD_WITHIN_HORIZON
        if composition is Composition.ANY_TIME_WITHIN_HORIZON
        else ResolutionRule.LEVEL_ABOVE_THRESHOLD_AT_HORIZON
    )
    return BinaryIndicator(
        name=f"an_indicator_{composition.value}",
        question="does the thing happen",
        resolution=IndicatorResolution(
            series="a_series", rule=rule, transform=Transform.LEVEL, threshold=1.0
        ),
        composition=composition,
        horizons_in_years=(1, 5, 10),
    )


def _one_regime_model() -> GaussianHiddenMarkovModel:
    return GaussianHiddenMarkovModel(
        initial_distribution=np.ones(1),
        transition_matrix=np.ones((1, 1)),
        means=np.zeros((1, 1)),
        covariances=np.ones((1, 1, 1)),
    )


def _two_regime_model() -> GaussianHiddenMarkovModel:
    return GaussianHiddenMarkovModel(
        initial_distribution=np.array([0.5, 0.5]),
        transition_matrix=np.array([[0.97, 0.03], [0.06, 0.94]]),
        means=np.array([[-1.0], [1.0]]),
        covariances=np.array([[[1.0]], [[1.0]]]),
    )


# A sticky condition: long spells on and off, so whether it holds now matters.
STICKY_CONDITION = np.array(([1.0] * 18 + [0.0] * 42) * 8)


def _one_regime_rates(composition: Composition):  # type: ignore[no-untyped-def]
    return estimate_conditional_rates(
        _indicator(composition), STICKY_CONDITION, np.ones((STICKY_CONDITION.size, 1)), 10.0
    )


def _two_regime_rates(composition: Composition):  # type: ignore[no-untyped-def]
    # The condition holds mostly in the second regime, so the rates differ by regime.
    weights = np.where(STICKY_CONDITION[:, None] > 0.5, [[0.2, 0.8]], [[0.85, 0.15]])
    return estimate_conditional_rates(_indicator(composition), STICKY_CONDITION, weights, 10.0)


@pytest.mark.parametrize("held", [False, True])
@pytest.mark.parametrize("gap", [0, 1, 2, 13])
def test_at_one_regime_b1_is_the_reference_chain_bit_for_bit(held: bool, gap: int) -> None:
    """Required check `function_level_identity`: array equality, never a tolerance."""
    indicator = _indicator(Composition.POINT_IN_TIME)
    rates = _one_regime_rates(Composition.POINT_IN_TIME)
    horizons = (1, 12, 60, 120)
    through_b1 = np.array(
        [
            forecast_indicator(
                indicator,
                _one_regime_model(),
                np.ones(1),
                rates,
                horizon,
                held,
                point_in_time_through_the_condition_chain=True,
                months_since_condition_last_published=gap,
            ).probability
            for horizon in horizons
        ]
    )
    reference_chain = np.array(
        [
            compose_through_the_condition_chain(
                SINGLE_REGIME_TRANSITION_MATRIX,
                SINGLE_REGIME_DISTRIBUTION,
                rates,
                Composition.POINT_IN_TIME,
                horizon,
                held,
                gap,
            )
            for horizon in horizons
        ]
    )
    assert np.array_equal(through_b1, reference_chain)

    # And both are the closed form: the two-state chain stepped gap + h months.
    entry, persistence = float(rates.entry_hazard[0]), float(rates.persistence[0])
    step = np.array([[1 - entry, entry], [1 - persistence, persistence]])
    start = np.array([0.0, 1.0]) if held else np.array([1.0, 0.0])
    closed_form = [(start @ np.linalg.matrix_power(step, gap + h))[1] for h in horizons]
    np.testing.assert_allclose(through_b1, closed_form, rtol=0, atol=1e-13)


@pytest.mark.parametrize("held", [False, True])
def test_with_regimes_b1_is_the_joint_chain_on_the_models_own_parameters(held: bool) -> None:
    indicator = _indicator(Composition.POINT_IN_TIME)
    model = _two_regime_model()
    rates = _two_regime_rates(Composition.POINT_IN_TIME)
    filtered = np.array([0.9, 0.1])
    for gap, horizon in ((0, 1), (2, 12), (13, 60), (1, 120)):
        got = forecast_indicator(
            indicator,
            model,
            filtered,
            rates,
            horizon,
            held,
            point_in_time_through_the_condition_chain=True,
            months_since_condition_last_published=gap,
        ).probability
        expected = compose_through_the_condition_chain(
            model.transition_matrix,
            filtered,
            rates,
            Composition.POINT_IN_TIME,
            horizon,
            held,
            gap,
        )
        assert got == expected


@pytest.mark.parametrize("held", [False, True])
def test_the_setting_leaves_any_time_questions_and_every_diagnostic_unchanged(
    held: bool,
) -> None:
    model = _two_regime_model()
    filtered = np.array([0.3, 0.7])
    for composition in Composition:
        indicator = _indicator(composition)
        rates = _two_regime_rates(composition)
        for horizon in (12, 60, 120):
            off = forecast_indicator(indicator, model, filtered, rates, horizon, held)
            on = forecast_indicator(
                indicator,
                model,
                filtered,
                rates,
                horizon,
                held,
                point_in_time_through_the_condition_chain=True,
                months_since_condition_last_published=2,
            )
            assert on.effective_sample_size == off.effective_sample_size
            assert on.distance_to_stationary == off.distance_to_stationary
            assert on.projected_state_distribution == off.projected_state_distribution
            if composition is Composition.ANY_TIME_WITHIN_HORIZON:
                assert on == off
            else:
                assert on.probability != off.probability


def test_only_through_the_chain_does_whether_the_condition_holds_now_move_the_answer() -> None:
    """The hypothesis in one line: main's point-in-time composition ignores whether
    the condition holds now; B1 does not."""
    indicator = _indicator(Composition.POINT_IN_TIME)
    model = _two_regime_model()
    rates = _two_regime_rates(Composition.POINT_IN_TIME)
    filtered = np.array([0.5, 0.5])

    def probability(held: bool, through_the_chain: bool) -> float:
        return forecast_indicator(
            indicator,
            model,
            filtered,
            rates,
            12,
            held,
            point_in_time_through_the_condition_chain=through_the_chain,
            months_since_condition_last_published=2 if through_the_chain else None,
        ).probability

    assert probability(True, through_the_chain=False) == probability(False, through_the_chain=False)
    assert probability(True, through_the_chain=True) > probability(False, through_the_chain=True)


def test_the_chain_without_a_publication_gap_is_refused() -> None:
    with pytest.raises(ForecastCompositionError, match="months_since_condition_last_published"):
        forecast_indicator(
            _indicator(Composition.POINT_IN_TIME),
            _two_regime_model(),
            np.array([0.5, 0.5]),
            _two_regime_rates(Composition.POINT_IN_TIME),
            12,
            False,
            point_in_time_through_the_condition_chain=True,
        )


# ------------------------------------------------------------ settings


def test_the_setting_is_on_on_this_branch_and_off_at_reference_0008s_hash() -> None:
    assert getattr(DEFAULT_RUN_SETTINGS, SETTING) is True
    assert SETTINGS_OMITTED_FROM_THE_HASH_WHEN_THEY_HOLD_THE_SHIPPED_VALUE[SETTING] is False
    main = dataclasses.replace(DEFAULT_RUN_SETTINGS, **{SETTING: False})
    assert main.configuration_hash() == REFERENCE_0008_HASH
    assert DEFAULT_RUN_SETTINGS.configuration_hash() != REFERENCE_0008_HASH


# ------------------------------------------------------------ synthetic walk-forward


FIRST_FORECAST = date(2000, 1, 1)
CUTOFF = date(2001, 1, 1)


def _series_entry(
    name: str, series_id: str, dimension: ModelDimension, transform: Transform, revised: bool
) -> EconomicSeries:
    return EconomicSeries(
        name=name,
        series_id=series_id,
        description=f"synthetic {name}",
        role=dimension.value,
        model_dimension=dimension,
        frequency="monthly",
        units="units",
        transform=transform,
        publication_lag_days=45,
        observation_start=date(1960, 1, 1),
        is_revised=revised,
    )


@pytest.fixture(scope="module")
def registry() -> EconomicSeriesRegistry:
    change = Transform.YEAR_OVER_YEAR_LOG_CHANGE
    return EconomicSeriesRegistry(
        series=(
            _series_entry("synthetic_output", "SYNOUT", ModelDimension.GROWTH, change, True),
            _series_entry("synthetic_prices", "SYNCPI", ModelDimension.INFLATION, change, True),
            _series_entry(
                "synthetic_rate", "SYNRATE", ModelDimension.RATES, Transform.LEVEL, False
            ),
        ),
        derived=(),
    )


@pytest.fixture(scope="module")
def indicators() -> tuple[BinaryIndicator, ...]:
    def indicator(name: str, rule: ResolutionRule, threshold: float, composition: Composition):
        return BinaryIndicator(
            name=name,
            question=name.replace("_", " "),
            resolution=IndicatorResolution(
                series="synthetic_rate", rule=rule, transform=Transform.LEVEL, threshold=threshold
            ),
            composition=composition,
            horizons_in_years=(1, 5),
        )

    return (
        indicator(
            "rate_above_three_at_horizon",
            ResolutionRule.LEVEL_ABOVE_THRESHOLD_AT_HORIZON,
            3.0,
            Composition.POINT_IN_TIME,
        ),
        indicator(
            "rate_below_one_within_horizon",
            ResolutionRule.LEVEL_BELOW_THRESHOLD_WITHIN_HORIZON,
            1.0,
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


@pytest.fixture(scope="module")
def source_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Forty-five years of two-regime data whose rate switches slowly, so the
    condition is sticky, with honest vintages around 2000."""
    root = tmp_path_factory.mktemp("condition_chain_cache")
    cache = look_ahead_audit.series_cache_at(root)
    index = pd.date_range("1960-01-01", "2004-12-01", freq="MS", name="observation_date")
    generator = np.random.default_rng(20260929)
    transitions = np.array([[0.98, 0.02], [0.03, 0.97]])
    state = 0
    output, prices, rate = [100.0], [100.0], []
    for _ in range(len(index)):
        state = int(generator.choice(2, p=transitions[state]))
        output.append(output[-1] * (1.0 + (0.004 if state == 0 else -0.002)))
        prices.append(prices[-1] * (1.0 + (0.002 if state == 0 else 0.006)))
        rate.append((4.5 if state == 0 else 0.6) + float(generator.normal(0, 0.8)))
    values = {
        "SYNOUT": pd.Series(output[1:], index=index),
        "SYNCPI": pd.Series(prices[1:], index=index),
        "SYNRATE": pd.Series(np.clip(rate, 0.0, None), index=index),
    }
    for series_id, series in values.items():
        cache.write(_snapshot(series, series_id))
    for series_id in ("SYNOUT", "SYNCPI"):
        series = values[series_id]
        for stamp in pd.date_range("1999-01-01", "2003-12-01", freq="MS"):
            as_published = series[series.index < stamp - pd.DateOffset(months=1)]
            cache.write(_snapshot(as_published, series_id, stamp.date()))
    return root


def _settings(root: Path, through_the_chain: bool = True) -> RunSettings:
    return RunSettings(
        random_seed=7,
        hidden_state_counts_to_search=(1, 2),
        expectation_maximisation_restarts=2,
        expectation_maximisation_max_iterations=60,
        minimum_observations_before_first_fit=120,
        refit_every_n_months=12,
        forecast_horizons_in_months=(12, 60),
        cache=CacheLayout(root),
        **{SETTING: through_the_chain},
    )


def _schedule(_cache: object = None) -> schedule_module.ForecastSchedule:
    return schedule_module.build_schedule(FIRST_FORECAST, date(2001, 6, 1), 12)


def _walk(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    source_root: Path,
    settings: RunSettings,
    state_count: int,
    cadence: ConditionChainCadence = ConditionChainCadence.EVERY_FORECAST_DATE,
) -> pd.DataFrame:
    schedule = _schedule()
    return run_walk_forward(
        registry,
        indicators,
        look_ahead_audit.series_cache_at(source_root),
        settings,
        state_count,
        schedule.forecast_dates,
        schedule.refit_dates,
        artifacts=None,
        progress_every=0,
        condition_chain_cadence=cadence,
    )


def _rows(frame: pd.DataFrame, composition: Composition) -> pd.DataFrame:
    return (
        frame[frame["composition"] == composition.value]
        .sort_values(["indicator", "forecast_date", "horizon_months"])
        .reset_index(drop=True)
    )


def test_at_one_regime_the_walk_forward_writes_the_reference_chain_at_refit_cadence(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    source_root: Path,
    tmp_path: Path,
) -> None:
    """Required check `end_to_end_identity`, at unit scale: point-in-time rows."""
    frame = _walk(
        registry, indicators, source_root, _settings(tmp_path), 1, ConditionChainCadence.REFIT
    )
    point_in_time = _rows(frame, Composition.POINT_IN_TIME)
    assert len(point_in_time) > 0
    assert np.array_equal(
        point_in_time["predicted_probability"].to_numpy(),
        point_in_time["condition_chain_probability"].to_numpy(),
    )


def test_at_one_regime_any_time_rows_are_mains_own_composition(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    source_root: Path,
    tmp_path: Path,
) -> None:
    """Required check `end_to_end_identity`, at unit scale: any-time rows, which B1
    leaves on the path that does not step the publication gap."""
    b1 = _walk(registry, indicators, source_root, _settings(tmp_path / "b1"), 1)
    main = _walk(
        registry, indicators, source_root, _settings(tmp_path / "main", through_the_chain=False), 1
    )
    b1_any_time = _rows(b1, Composition.ANY_TIME_WITHIN_HORIZON)
    main_any_time = _rows(main, Composition.ANY_TIME_WITHIN_HORIZON)
    assert len(b1_any_time) > 0
    assert np.array_equal(
        b1_any_time["predicted_probability"].to_numpy(),
        main_any_time["predicted_probability"].to_numpy(),
    )


def test_with_regimes_the_setting_moves_only_point_in_time_predicted_probabilities(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    source_root: Path,
    tmp_path: Path,
) -> None:
    on = _walk(registry, indicators, source_root, _settings(tmp_path / "on"), 2)
    off = _walk(
        registry, indicators, source_root, _settings(tmp_path / "off", through_the_chain=False), 2
    )
    untouched = [
        column
        for column in RESULT_COLUMNS
        if column not in ("predicted_probability", "configuration_hash")
    ]
    pd.testing.assert_frame_equal(on[untouched], off[untouched])
    assert on["configuration_hash"].unique().tolist() != off["configuration_hash"].unique().tolist()
    pd.testing.assert_frame_equal(
        _rows(on, Composition.ANY_TIME_WITHIN_HORIZON),
        _rows(off, Composition.ANY_TIME_WITHIN_HORIZON).assign(
            configuration_hash=on["configuration_hash"].iloc[0]
        ),
    )
    point_in_time_on = _rows(on, Composition.POINT_IN_TIME)["predicted_probability"]
    point_in_time_off = _rows(off, Composition.POINT_IN_TIME)["predicted_probability"]
    assert not point_in_time_on.equals(point_in_time_off)
    assert point_in_time_on.between(0.0, 1.0).all()


def test_the_look_ahead_audit_passes_with_the_setting_on(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    source_root: Path,
    tmp_path: Path,
) -> None:
    """The deterministic half of experiment 0008's void rule, at unit scale, on the
    arm's own configuration. The chain reads the last published condition and the
    months since it was published, both censored by publication date."""
    audit = look_ahead_audit.audit_look_ahead(
        registry,
        indicators,
        look_ahead_audit.series_cache_at(source_root),
        _settings(tmp_path / "unused"),
        _schedule,
        tmp_path / "audit",
        cutoff=CUTOFF,
    )
    assert audit.exit_code == 0
    assert audit.moved == ()


# ------------------------------------------------------------ forecast-now


@pytest.mark.parametrize("through_the_chain", [True, False])
def test_todays_grid_is_composed_by_the_method_that_was_backtested(
    registry: EconomicSeriesRegistry,
    indicators: tuple[BinaryIndicator, ...],
    source_root: Path,
    tmp_path: Path,
    through_the_chain: bool,
) -> None:
    """`forecast forecast-now` must ask the same composition the walk-forward asks,
    with the same publication gap, so the submitted grid is the backtested method."""
    today = date(2001, 3, 1)
    settings = _settings(tmp_path / "workspace", through_the_chain=through_the_chain)
    cache = look_ahead_audit.series_cache_at(source_root)
    artifacts = ArtifactStore(tmp_path / "workspace" / "models")
    workspace = command_line_interface.Workspace(
        registry=registry,
        indicators=indicators,
        cache=cache,
        artifacts=artifacts,
        settings=settings,
    )
    matrix = workspace.observation_matrix_as_of(today)
    selected = hidden_markov.fit(
        matrix.values, state_count=2, seed=7, restarts=2, max_iterations=60, tolerance=1e-6
    )
    artifacts.write_json(ARTIFACTS.selected_model, selected.to_dictionary())

    code, report = command_line_interface.forecast_now(workspace, today)
    assert code == 0, report.describe()
    grid = artifacts.read_table(ARTIFACTS.current_forecasts)

    histories = walk_forward.prepare_indicator_history(
        indicators, registry, cache, settings.forecast_horizons_in_months
    )
    fitted = walk_forward.fit_regime_model(
        today, registry, cache, histories, settings, 2, artifacts
    )
    filtered = fitted.model.filtered_state_probabilities(matrix.values)[-1]
    for indicator in indicators:
        condition = walk_forward.condition_available_at(histories[indicator.name], today)
        holds_now = bool(condition.iloc[-1] > 0.5)
        gap = walk_forward.months_between(pd.Timestamp(condition.index[-1]), pd.Timestamp(today))
        assert gap >= 1
        for horizon in settings.forecast_horizons_in_months:
            expected = forecast_indicator(
                indicator,
                fitted.model,
                filtered,
                fitted.rates_by_indicator[indicator.name],
                horizon,
                holds_now,
                point_in_time_through_the_condition_chain=through_the_chain,
                months_since_condition_last_published=gap,
            ).probability
            row = grid[(grid["indicator"] == indicator.name) & (grid["horizon_months"] == horizon)]
            assert row["probability"].tolist() == [expected]
            if through_the_chain and indicator.composition is Composition.POINT_IN_TIME:
                assert expected == compose_through_the_condition_chain(
                    fitted.model.transition_matrix,
                    filtered,
                    fitted.rates_by_indicator[indicator.name],
                    Composition.POINT_IN_TIME,
                    horizon,
                    holds_now,
                    gap,
                )
