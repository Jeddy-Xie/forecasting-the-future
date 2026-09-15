"""Research arm A5, direct horizon rates: what it computes, and when it may learn.

Experiment 0002 registers the change. For every indicator and horizon h, the
forecast is today's filtered regime distribution dotted with per-regime rates of
the h-month outcome itself, rate[k] = sum_s gamma_s[k] * y_s,h / sum_s gamma_s[k],
shrunk toward the pooled resolved rate at strength 10. The sum runs over forecast
months s whose outcome had resolved and been published by the refit date: label
s + h months, plus the resolution series' publication lag, on or before it.

Three groups. The arithmetic, counted by hand. The boundary, pinned to the day on
both sides, and pinned to be the benchmark's own boundary rather than a second
copy of it. And the wiring: with the setting on, the walk-forward issues the
direct probability and nothing else; with it off, main's compositions and main's
configuration digest. ``test_direct_horizon_rates_look_ahead.py`` shows the
look-ahead audit catching an off-by-one at the boundary.
"""

from __future__ import annotations

import dataclasses
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from economic_regime_forecasting.backtest import walk_forward
from economic_regime_forecasting.backtest.walk_forward import (
    BacktestError,
    IndicatorHistory,
    _expanding_climatology,
    count_of_outcomes_published_by,
    outcomes_available_at,
)
from economic_regime_forecasting.configuration.registry import (
    BinaryIndicator,
    Composition,
    EconomicSeriesRegistry,
    IndicatorResolution,
    ResolutionRule,
    Transform,
)
from economic_regime_forecasting.configuration.run_settings import (
    DEFAULT_RUN_SETTINGS,
    RunSettings,
)
from economic_regime_forecasting.data.cache import SeriesCache
from economic_regime_forecasting.data.panel import assemble_point_in_time_panel
from economic_regime_forecasting.features.observation_matrix import build_observation_matrix
from economic_regime_forecasting.models.gaussian_hidden_markov_model import (
    GaussianHiddenMarkovModel,
)
from economic_regime_forecasting.models.indicator_forecast import (
    ConditionalRates,
    ForecastCompositionError,
    compose_any_time_within_horizon,
    compose_point_in_time,
    estimate_conditional_rates,
    estimate_direct_horizon_rate,
    forecast_indicator,
)
from tests import test_walk_forward_backtest as walk_forward_suite

# The synthetic forty-year, two-regime world the walk-forward tests run on, reused
# rather than rebuilt, so both files exercise one fixture.
synthetic_registry = walk_forward_suite.synthetic_registry
synthetic_indicators = walk_forward_suite.synthetic_indicators
filled_cache = walk_forward_suite.filled_cache
settings = walk_forward_suite.settings

REFERENCE_RUN_CONFIGURATION_HASH = "ad7fcc1affd0746a"
"""Main's digest, recorded as experiment 0002's reference run."""

STRENGTH = 10.0
"""Main's conditional_rate_shrinkage_strength, which the arm keeps unchanged."""


def _indicator(
    composition: Composition = Composition.POINT_IN_TIME, name: str = "test_indicator"
) -> BinaryIndicator:
    rule = (
        ResolutionRule.LEVEL_ABOVE_THRESHOLD_WITHIN_HORIZON
        if composition is Composition.ANY_TIME_WITHIN_HORIZON
        else ResolutionRule.LEVEL_ABOVE_THRESHOLD_AT_HORIZON
    )
    return BinaryIndicator(
        name=name,
        question="does the thing happen",
        resolution=IndicatorResolution(
            series="test_series", rule=rule, transform=Transform.LEVEL, threshold=1.0
        ),
        composition=composition,
        horizons_in_years=(1, 5, 10),
    )


def _model() -> GaussianHiddenMarkovModel:
    """Two persistent regimes, one calm and one turbulent."""
    return GaussianHiddenMarkovModel(
        initial_distribution=np.array([0.5, 0.5]),
        transition_matrix=np.array([[0.97, 0.03], [0.06, 0.94]]),
        means=np.array([[-1.0], [1.0]]),
        covariances=np.array([[[1.0]], [[1.0]]]),
    )


def _monthly_rates(indicator: BinaryIndicator | None = None) -> ConditionalRates:
    return estimate_conditional_rates(
        indicator or _indicator(),
        np.array([0.0, 1.0, 1.0, 0.0, 1.0, 0.0]),
        np.array([[1.0, 0.0]] * 3 + [[0.0, 1.0]] * 3),
        STRENGTH,
    )


# ------------------------------------------------------------------ the arithmetic


def test_without_shrinkage_a_direct_rate_is_the_filtered_probability_weighted_frequency() -> None:
    """Hard assignments, so it can be counted by hand: forecasts made in the first
    regime came true three times in four, in the second once in three."""
    outcomes = np.array([1.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0])
    weights = np.array([[1.0, 0.0]] * 4 + [[0.0, 1.0]] * 3)
    rate = estimate_direct_horizon_rate(_indicator(), 60, outcomes, weights, 0.0)
    np.testing.assert_allclose(rate.rate, [0.75, 1 / 3])
    np.testing.assert_allclose(rate.sample_size, [4.0, 3.0])
    assert rate.pooled_rate == pytest.approx(4 / 7)
    assert rate.months_used == 7


def test_partial_regime_evidence_enters_each_rate_in_proportion() -> None:
    outcomes = np.array([1.0, 0.0, 1.0])
    weights = np.array([[0.6, 0.4], [0.2, 0.8], [0.5, 0.5]])
    rate = estimate_direct_horizon_rate(_indicator(), 12, outcomes, weights, 0.0)
    np.testing.assert_allclose(rate.rate, [(0.6 + 0.5) / 1.3, (0.4 + 0.5) / 1.7])
    np.testing.assert_allclose(rate.sample_size, [1.3, 1.7])


def test_the_shrinkage_is_mains_beta_prior_at_strength_ten_toward_the_pooled_resolved_rate() -> (
    None
):
    """rate[k] = (sum gamma y + 10 * pooled) / (sum gamma + 10), pooled being the
    plain mean of every outcome used. A regime with three forecasts behind it lands
    near the pooled rate; one with ninety-seven barely moves."""
    assert DEFAULT_RUN_SETTINGS.conditional_rate_shrinkage_strength == STRENGTH
    outcomes = np.array([1.0] * 3 + [0.0] * 97)
    weights = np.array([[1.0, 0.0]] * 3 + [[0.0, 1.0]] * 97)
    rate = estimate_direct_horizon_rate(_indicator(), 120, outcomes, weights, STRENGTH)
    pooled = 3 / 100
    np.testing.assert_allclose(
        rate.rate, [(3.0 + 10 * pooled) / (3 + 10), (0.0 + 10 * pooled) / (97 + 10)]
    )
    assert rate.pooled_rate == pytest.approx(pooled)
    assert rate.shrinkage_strength == STRENGTH


def test_a_direct_forecast_is_todays_filtered_distribution_dotted_with_the_rate() -> None:
    """Today's distribution, not the projected one: the rate already conditions on
    the regime at the forecast date, so projecting first would count it twice."""
    rate = estimate_direct_horizon_rate(
        _indicator(),
        60,
        np.array([1.0, 0.0, 0.0, 0.0]),
        np.array([[1.0, 0.0]] + [[0.0, 1.0]] * 3),
        0.0,
    )
    today = np.array([0.8, 0.2])
    composed = forecast_indicator(
        _indicator(), _model(), today, _monthly_rates(), 60, False, direct_horizon_rate=rate
    )
    assert composed.probability == pytest.approx(0.8)
    projected = _model().project_state_distribution(today, 60)
    assert composed.probability != pytest.approx(float(projected @ rate.rate))
    assert composed.effective_sample_size == pytest.approx(0.8 * 1.0 + 0.2 * 3.0)


@pytest.mark.parametrize("composition", list(Composition))
@pytest.mark.parametrize("condition_holds_now", [True, False])
def test_the_direct_rate_replaces_both_compositions(
    composition: Composition, condition_holds_now: bool
) -> None:
    """Whatever the registry declares, and whether or not the condition holds now."""
    indicator = _indicator(composition)
    rate = estimate_direct_horizon_rate(
        indicator,
        12,
        np.array([1.0, 0.0, 1.0]),
        np.array([[0.9, 0.1], [0.3, 0.7], [0.5, 0.5]]),
        STRENGTH,
    )
    today = np.array([0.35, 0.65])
    composed = forecast_indicator(
        indicator,
        _model(),
        today,
        _monthly_rates(indicator),
        12,
        condition_holds_now,
        direct_horizon_rate=rate,
    )
    assert composed.probability == float(np.dot(today, rate.rate))
    assert composed.composition is composition


def test_without_a_direct_rate_the_compositions_are_mains() -> None:
    """The off switch: given no direct rate, forecast_indicator composes as before."""
    today = np.array([0.35, 0.65])
    for composition in Composition:
        indicator = _indicator(composition)
        rates = _monthly_rates(indicator)
        composed = forecast_indicator(indicator, _model(), today, rates, 60, True)
        if composition is Composition.POINT_IN_TIME:
            expected = compose_point_in_time(_model().project_state_distribution(today, 60), rates)
        else:
            expected = compose_any_time_within_horizon(_model(), today, rates, 60, True)
        assert composed.probability == expected


def test_a_direct_rate_for_another_indicator_or_horizon_is_refused() -> None:
    rate = estimate_direct_horizon_rate(
        _indicator(), 12, np.array([1.0]), np.array([[1.0, 0.0]]), 0.0
    )
    with pytest.raises(ForecastCompositionError, match="handed the direct rate"):
        forecast_indicator(
            _indicator(),
            _model(),
            np.array([0.5, 0.5]),
            _monthly_rates(),
            60,
            False,
            direct_horizon_rate=rate,
        )
    other = _indicator(name="another_indicator")
    with pytest.raises(ForecastCompositionError, match="handed the direct rate"):
        forecast_indicator(
            other,
            _model(),
            np.array([0.5, 0.5]),
            _monthly_rates(other),
            12,
            False,
            direct_horizon_rate=rate,
        )


@pytest.mark.parametrize(
    ("outcomes", "message"),
    [
        (np.array([]), "no resolved"),
        (np.array([1.0, np.nan]), "unresolved"),
        (np.array([1.0, 0.5]), "either zero or one"),
    ],
)
def test_an_outcome_that_is_missing_or_not_binary_is_refused(
    outcomes: np.ndarray, message: str
) -> None:
    weights = np.full((outcomes.size, 2), 0.5)
    with pytest.raises(ForecastCompositionError, match=message):
        estimate_direct_horizon_rate(_indicator(), 12, outcomes, weights, STRENGTH)


def test_misaligned_outcomes_and_state_probabilities_are_refused() -> None:
    with pytest.raises(ForecastCompositionError, match="Align them"):
        estimate_direct_horizon_rate(
            _indicator(), 12, np.array([1.0, 0.0]), np.full((3, 2), 0.5), STRENGTH
        )


# -------------------------------------------------------------------- the boundary


def _history(
    outcomes: pd.Series, horizon_in_months: int, publication_lag_days: int
) -> IndicatorHistory:
    return IndicatorHistory(
        indicator=_indicator(),
        monthly_condition=pd.Series(dtype="float64"),
        outcomes_by_horizon={horizon_in_months: outcomes},
        climatology_by_horizon={},
        publication_lag_days=publication_lag_days,
    )


def _positive_outcomes_from(first_forecast: str) -> pd.Series:
    return pd.Series(1.0, index=pd.date_range(first_forecast, "2012-12-01", freq="MS"))


BOUNDARY_CASES = [
    # (first forecast, horizon, lag, the day its outcome is published)
    # 1999-03-01 + 12 months is 2000-03-01; plus 31 days is 2000-04-01.
    ("1999-03-01", 12, 31, date(2000, 4, 1)),
    # The same value with the 45-day lag most monthly series carry.
    ("1999-03-01", 12, 45, date(2000, 4, 15)),
    # Recession dating: 2000-03-01 plus 400 days is 2001-04-05.
    ("1999-03-01", 12, 400, date(2001, 4, 5)),
    # Ten years: 1989-03-01 rests on 1999-03-01, published 400 days later, 2000-04-04.
    ("1989-03-01", 120, 400, date(2000, 4, 4)),
]


@pytest.mark.parametrize(("first", "horizon", "lag", "published_on"), BOUNDARY_CASES)
def test_a_refit_one_day_before_an_outcome_is_published_excludes_it(
    first: str, horizon: int, lag: int, published_on: date
) -> None:
    """The pre-registration's required boundary, the day before: excluded."""
    history = _history(_positive_outcomes_from(first), horizon, lag)
    assert outcomes_available_at(history, horizon, published_on - timedelta(days=1)).empty


@pytest.mark.parametrize(("first", "horizon", "lag", "published_on"), BOUNDARY_CASES)
def test_a_refit_on_the_day_an_outcome_is_published_includes_it(
    first: str, horizon: int, lag: int, published_on: date
) -> None:
    """And on the day itself: included, and nothing after it."""
    history = _history(_positive_outcomes_from(first), horizon, lag)
    available = outcomes_available_at(history, horizon, published_on)
    assert list(available.index) == [pd.Timestamp(first)]


def test_the_direct_rates_admit_each_outcome_on_the_day_the_benchmark_does() -> None:
    """One boundary, not two. At every date, the outcomes the direct rates may
    learn from are exactly the resolved outcomes whose deciding value (label
    s + h months, plus the lag) was published on or before that date, and the
    benchmark at that date is their average.

    Restated from the specification rather than by stepping one month past the
    last admitted outcome: the month after it may be unresolved, and so absent for
    that reason rather than for being unpublished."""
    generator = np.random.default_rng(5)
    index = pd.date_range("1980-01-01", "2005-12-01", freq="MS")
    outcomes = pd.Series(generator.integers(0, 2, len(index)).astype("float64"), index=index)
    # Windows with a gap resolve to missing, never to zero.
    outcomes.iloc[[40, 41, 200]] = np.nan
    for horizon, lag in ((12, 45), (60, 32), (120, 400)):
        history = _history(outcomes, horizon, lag)
        climatology = _expanding_climatology(outcomes, horizon, lag)
        published_on = index + pd.DateOffset(months=horizon) + pd.Timedelta(days=lag)
        for stamp in index:
            available = outcomes_available_at(history, horizon, stamp.date())
            expected = outcomes[published_on <= stamp].dropna()
            assert list(available.index) == list(expected.index)
            if available.empty:
                assert np.isnan(climatology[stamp])
                continue
            assert climatology[stamp] == pytest.approx(available.mean(), rel=1e-12)
            last = available.index[-1]
            assert last + pd.DateOffset(months=horizon) + pd.Timedelta(days=lag) <= stamp


def test_an_unresolved_outcome_is_dropped_never_read_as_zero() -> None:
    """1999-03 to 1999-05 are published by 2000-06-01 at a 31-day lag; 1999-04's
    window had a gap, so it is not an outcome at all."""
    outcomes = _positive_outcomes_from("1999-03-01")
    outcomes.iloc[1] = np.nan
    available = outcomes_available_at(_history(outcomes, 12, 31), 12, date(2000, 6, 1))
    assert list(available.index) == [pd.Timestamp("1999-03-01"), pd.Timestamp("1999-05-01")]
    assert (available == 1.0).all()


def test_forecast_dates_out_of_order_are_refused() -> None:
    dates = pd.DatetimeIndex(["2000-02-01", "2000-01-01"])
    with pytest.raises(BacktestError, match="ascend"):
        count_of_outcomes_published_by(dates, 12, 31, dates)


# ---------------------------------------------------------------------- the wiring


def _filtered_as_of(
    fitted: walk_forward.FittedRegimeModel,
    registry: EconomicSeriesRegistry,
    cache: SeriesCache,
    as_of: date,
) -> pd.DataFrame:
    matrix = build_observation_matrix(
        assemble_point_in_time_panel(registry, as_of, cache), registry
    )
    return pd.DataFrame(
        fitted.model.filtered_state_probabilities(matrix.values), index=matrix.dates
    )


def test_every_direct_rate_at_a_refit_rests_only_on_outcomes_published_by_then(
    synthetic_registry: EconomicSeriesRegistry,
    synthetic_indicators: tuple[BinaryIndicator, ...],
    filled_cache: SeriesCache,
    settings: RunSettings,
) -> None:
    """Recomputed by hand from the specification, at a refit inside the history."""
    as_of = date(2000, 1, 1)
    histories = walk_forward.prepare_indicator_history(
        synthetic_indicators, synthetic_registry, filled_cache, settings.forecast_horizons_in_months
    )
    fitted = walk_forward.fit_regime_model(
        as_of, synthetic_registry, filled_cache, histories, settings, 2
    )
    filtered = _filtered_as_of(fitted, synthetic_registry, filled_cache, as_of)
    stamp = pd.Timestamp(as_of)

    for indicator in synthetic_indicators:
        history = histories[indicator.name]
        for horizon in settings.forecast_horizons_in_months:
            outcomes = history.outcomes_by_horizon[horizon].dropna()
            published_on = (
                outcomes.index
                + pd.DateOffset(months=horizon)
                + pd.Timedelta(days=history.publication_lag_days)
            )
            usable = outcomes[published_on <= stamp]
            usable = usable[usable.index.isin(filtered.index)]
            weights = filtered.loc[usable.index].to_numpy()
            observed = usable.to_numpy()
            pooled = observed.mean()
            expected = (weights.T @ observed + STRENGTH * pooled) / (weights.sum(axis=0) + STRENGTH)

            direct = fitted.direct_horizon_rate(indicator.name, horizon)
            assert direct is not None
            np.testing.assert_allclose(direct.rate, expected, rtol=1e-12)
            assert direct.months_used == len(usable)
            assert direct.pooled_rate == pytest.approx(pooled, rel=1e-12)
            last = usable.index[-1]
            following = last + pd.DateOffset(months=1)
            lag = pd.Timedelta(days=history.publication_lag_days)
            assert last + pd.DateOffset(months=horizon) + lag <= stamp
            assert following + pd.DateOffset(months=horizon) + lag > stamp


def test_the_walk_forward_issues_the_direct_probability_when_the_setting_is_on(
    synthetic_registry: EconomicSeriesRegistry,
    synthetic_indicators: tuple[BinaryIndicator, ...],
    filled_cache: SeriesCache,
    settings: RunSettings,
) -> None:
    """On a refit date, every row is today's filtered distribution dotted with the
    direct rate, for both indicators at both horizons, bit for bit."""
    assert settings.estimate_each_horizon_rate_directly is True
    results = walk_forward_suite._run(
        synthetic_registry, synthetic_indicators, filled_cache, settings, months=12
    )
    refit = date(2000, 1, 1)
    histories = walk_forward.prepare_indicator_history(
        synthetic_indicators, synthetic_registry, filled_cache, settings.forecast_horizons_in_months
    )
    fitted = walk_forward.fit_regime_model(
        refit, synthetic_registry, filled_cache, histories, settings, 2
    )
    today = _filtered_as_of(fitted, synthetic_registry, filled_cache, refit).to_numpy()[-1]

    on_the_refit_date = results[results["forecast_date"] == pd.Timestamp(refit)]
    assert len(on_the_refit_date) == len(synthetic_indicators) * 2
    for row in on_the_refit_date.itertuples():
        direct = fitted.direct_horizon_rate(str(row.indicator), int(row.horizon_months))
        assert direct is not None
        assert row.predicted_probability == float(np.dot(today, direct.rate))


def test_turning_the_setting_off_restores_mains_compositions_and_moves_no_regime(
    synthetic_registry: EconomicSeriesRegistry,
    synthetic_indicators: tuple[BinaryIndicator, ...],
    filled_cache: SeriesCache,
    settings: RunSettings,
) -> None:
    """Off, the rows are the compositions. The regime model is identical either
    way, because the setting touches only what the rates are learned from."""
    off = dataclasses.replace(settings, estimate_each_horizon_rate_directly=False)
    on_results = walk_forward_suite._run(
        synthetic_registry, synthetic_indicators, filled_cache, settings, months=12
    )
    off_results = walk_forward_suite._run(
        synthetic_registry, synthetic_indicators, filled_cache, off, months=12
    )
    pd.testing.assert_series_equal(
        on_results["regime_distribution"], off_results["regime_distribution"]
    )
    assert not np.array_equal(
        on_results["predicted_probability"].to_numpy(),
        off_results["predicted_probability"].to_numpy(),
    )
    assert on_results["configuration_hash"].iloc[0] != off_results["configuration_hash"].iloc[0]

    refit = date(2000, 1, 1)
    histories = walk_forward.prepare_indicator_history(
        synthetic_indicators, synthetic_registry, filled_cache, off.forecast_horizons_in_months
    )
    fitted = walk_forward.fit_regime_model(
        refit, synthetic_registry, filled_cache, histories, off, 2
    )
    assert fitted.direct_rates_by_indicator == {}
    today = _filtered_as_of(fitted, synthetic_registry, filled_cache, refit).to_numpy()[-1]
    on_the_refit_date = off_results[off_results["forecast_date"] == pd.Timestamp(refit)]
    for indicator in synthetic_indicators:
        condition = walk_forward.condition_available_at(histories[indicator.name], refit)
        holds_now = bool(condition.iloc[-1] > 0.5)
        for horizon in off.forecast_horizons_in_months:
            assert fitted.direct_horizon_rate(indicator.name, horizon) is None
            expected = forecast_indicator(
                indicator,
                fitted.model,
                today,
                fitted.rates_by_indicator[indicator.name],
                horizon,
                holds_now,
            ).probability
            row = on_the_refit_date[
                (on_the_refit_date["indicator"] == indicator.name)
                & (on_the_refit_date["horizon_months"] == horizon)
            ]
            assert row["predicted_probability"].item() == expected


def test_the_setting_off_is_the_reference_run_of_experiment_0002() -> None:
    """False must reproduce main's identity as well as main's numbers: the omission
    map leaves it out of the digest, so main's recorded hash comes out unchanged."""
    off = RunSettings(estimate_each_horizon_rate_directly=False)
    assert off.configuration_hash() == REFERENCE_RUN_CONFIGURATION_HASH
    assert DEFAULT_RUN_SETTINGS.estimate_each_horizon_rate_directly is True
    assert DEFAULT_RUN_SETTINGS.configuration_hash() != REFERENCE_RUN_CONFIGURATION_HASH


def test_a_horizon_with_nothing_published_yet_raises_rather_than_guessing(
    synthetic_registry: EconomicSeriesRegistry,
    synthetic_indicators: tuple[BinaryIndicator, ...],
    filled_cache: SeriesCache,
    settings: RunSettings,
) -> None:
    """At 1975-06 no five-year outcome inside the panel had been published: the
    earliest the panel holds is 1971, whose outcome waits until 1976. No silent
    fallback to the pooled rate or to the compositions."""
    histories = walk_forward.prepare_indicator_history(
        synthetic_indicators, synthetic_registry, filled_cache, settings.forecast_horizons_in_months
    )
    with pytest.raises(BacktestError, match="no 60-month outcome"):
        walk_forward.fit_regime_model(
            date(1975, 6, 1), synthetic_registry, filled_cache, histories, settings, 2
        )
