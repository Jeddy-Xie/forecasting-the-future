"""The walk-forward engine, run end to end on synthetic data.

Everything here is offline: a small registry, a cache filled with generated
series, and vintages that stop where real vintages would. That makes the run fast
enough to assert on, and it makes the look-ahead tests meaningful, because a
fixture that handed the engine the future would be caught by the same guards the
real data is.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
import pytest

from economic_regime_forecasting.backtest import schedule as schedule_module
from economic_regime_forecasting.backtest.walk_forward import (
    RESULT_COLUMNS,
    BacktestError,
    _expanding_climatology,
    blend_model_and_climatology_probability,
    climatology_carry_forward_record,
    climatology_probability_for_blend,
    condition_available_at,
    prepare_indicator_history,
    run_walk_forward,
    validate_results,
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
from economic_regime_forecasting.configuration.run_settings import RunSettings
from economic_regime_forecasting.data.cache import SeriesCache, SeriesRequest, SeriesSnapshot

MONTHS = 480
START = "1970-01-01"


def _series_entry(
    name: str,
    series_id: str,
    dimension: ModelDimension | None,
    transform: Transform,
    is_revised: bool,
    role: str = "growth",
) -> EconomicSeries:
    return EconomicSeries(
        name=name,
        series_id=series_id,
        description=f"synthetic {name}",
        role=role,
        model_dimension=dimension,
        frequency="monthly",
        units="units",
        transform=transform,
        publication_lag_days=45,
        observation_start=date(1970, 1, 1),
        is_revised=is_revised,
    )


@pytest.fixture
def synthetic_registry() -> EconomicSeriesRegistry:
    return EconomicSeriesRegistry(
        series=(
            _series_entry(
                "synthetic_output",
                "SYNOUT",
                ModelDimension.GROWTH,
                Transform.YEAR_OVER_YEAR_LOG_CHANGE,
                True,
            ),
            _series_entry(
                "synthetic_prices",
                "SYNCPI",
                ModelDimension.INFLATION,
                Transform.YEAR_OVER_YEAR_LOG_CHANGE,
                True,
                role="inflation",
            ),
            _series_entry(
                "synthetic_rate",
                "SYNRATE",
                ModelDimension.RATES,
                Transform.LEVEL,
                False,
                role="rates",
            ),
        ),
        derived=(),
    )


@pytest.fixture
def synthetic_indicators() -> tuple[BinaryIndicator, ...]:
    return (
        BinaryIndicator(
            name="rate_above_three_at_horizon",
            question="is the rate above three at the horizon",
            resolution=IndicatorResolution(
                series="synthetic_rate",
                rule=ResolutionRule.LEVEL_ABOVE_THRESHOLD_AT_HORIZON,
                transform=Transform.LEVEL,
                threshold=3.0,
            ),
            composition=Composition.POINT_IN_TIME,
            horizons_in_years=(1, 5),
        ),
        BinaryIndicator(
            name="rate_below_one_within_horizon",
            question="does the rate fall below one within the horizon",
            resolution=IndicatorResolution(
                series="synthetic_rate",
                rule=ResolutionRule.LEVEL_BELOW_THRESHOLD_WITHIN_HORIZON,
                transform=Transform.LEVEL,
                threshold=1.0,
            ),
            composition=Composition.ANY_TIME_WITHIN_HORIZON,
            horizons_in_years=(1, 5),
        ),
    )


@pytest.fixture
def filled_cache(
    cache: SeriesCache,
    synthetic_registry: EconomicSeriesRegistry,
    snapshot_factory: Callable[..., SeriesSnapshot],
) -> SeriesCache:
    """A cache holding forty years of two-regime data, with honest vintages."""
    index = pd.date_range(START, periods=MONTHS, freq="MS", name="observation_date")
    generator = np.random.default_rng(20260908)
    transitions = np.array([[0.97, 0.03], [0.05, 0.95]])
    state = 0
    output, prices, rate = [100.0], [100.0], []
    for _ in range(MONTHS):
        state = int(generator.choice(2, p=transitions[state]))
        output.append(output[-1] * (1.0 + (0.004 if state == 0 else -0.002)))
        prices.append(prices[-1] * (1.0 + (0.002 if state == 0 else 0.006)))
        rate.append((4.5 if state == 0 else 0.6) + float(generator.normal(0, 0.2)))

    values = {
        "SYNOUT": pd.Series(output[1:], index=index),
        "SYNCPI": pd.Series(prices[1:], index=index),
        "SYNRATE": pd.Series(np.clip(rate, 0.0, None), index=index),
    }
    for series_id, series in values.items():
        cache.write(snapshot_factory(series, series_id=series_id))
        for stamp in index:
            # A vintage dated the first of a month holds data through two months
            # earlier, which is what the archive really returns.
            as_published = series[series.index < stamp - pd.DateOffset(months=1)]
            if as_published.empty:
                continue
            cache.write(
                snapshot_factory(as_published, series_id=series_id, vintage_date=stamp.date())
            )
    return cache


@pytest.fixture
def settings(tmp_path) -> RunSettings:  # type: ignore[no-untyped-def]
    from economic_regime_forecasting.configuration.run_settings import CacheLayout

    return RunSettings(
        random_seed=99,
        expectation_maximisation_restarts=3,
        expectation_maximisation_max_iterations=80,
        minimum_observations_before_first_fit=180,
        refit_every_n_months=24,
        forecast_horizons_in_months=(12, 60),
        cache=CacheLayout(tmp_path / "artifacts"),
    )


def _run(registry, indicators, filled_cache, settings, months: int = 24):  # type: ignore[no-untyped-def]
    schedule = schedule_module.build_schedule(
        date(2000, 1, 1),
        (pd.Timestamp("2000-01-01") + pd.DateOffset(months=months - 1)).date(),
        settings.refit_every_n_months,
    )
    return run_walk_forward(
        registry,
        indicators,
        filled_cache,
        settings,
        2,
        schedule.forecast_dates,
        schedule.refit_dates,
        artifacts=None,
        progress_every=0,
    )


def test_a_run_produces_one_row_per_indicator_date_and_horizon(
    synthetic_registry, synthetic_indicators, filled_cache, settings
) -> None:  # type: ignore[no-untyped-def]
    results = _run(synthetic_registry, synthetic_indicators, filled_cache, settings, months=12)
    assert list(results.columns) == list(RESULT_COLUMNS)
    assert len(results) == 12 * len(synthetic_indicators) * 2
    assert not results.duplicated(subset=["indicator", "forecast_date", "horizon_months"]).any()


def test_every_probability_is_a_probability(
    synthetic_registry, synthetic_indicators, filled_cache, settings
) -> None:  # type: ignore[no-untyped-def]
    results = _run(synthetic_registry, synthetic_indicators, filled_cache, settings, months=12)
    probabilities = results["predicted_probability"]
    assert probabilities.between(0.0, 1.0).all()
    assert probabilities.notna().all()


def test_two_runs_of_the_same_configuration_are_identical(
    synthetic_registry, synthetic_indicators, filled_cache, settings
) -> None:  # type: ignore[no-untyped-def]
    """Determinism is a shipping requirement, so it is tested rather than hoped for."""
    first = _run(synthetic_registry, synthetic_indicators, filled_cache, settings, months=12)
    second = _run(synthetic_registry, synthetic_indicators, filled_cache, settings, months=12)
    pd.testing.assert_frame_equal(first, second)


def test_the_run_records_the_configuration_that_produced_it(
    synthetic_registry, synthetic_indicators, filled_cache, settings
) -> None:  # type: ignore[no-untyped-def]
    results = _run(synthetic_registry, synthetic_indicators, filled_cache, settings, months=12)
    assert results["configuration_hash"].nunique() == 1
    assert results["seed"].unique().tolist() == [settings.random_seed]
    assert results["state_count"].unique().tolist() == [2]


def test_the_model_is_refitted_on_the_declared_cadence(
    synthetic_registry, synthetic_indicators, filled_cache, settings
) -> None:  # type: ignore[no-untyped-def]
    results = _run(synthetic_registry, synthetic_indicators, filled_cache, settings, months=30)
    refits = sorted(results["refit_date"].unique())
    assert len(refits) == 2
    assert (pd.Timestamp(refits[1]) - pd.Timestamp(refits[0])).days > 700


def test_an_any_time_forecast_exceeds_its_point_in_time_twin_on_real_runs(
    synthetic_registry, synthetic_indicators, filled_cache, settings
) -> None:  # type: ignore[no-untyped-def]
    """Both indicators sit on the same series, so the composition path is the only
    difference between them at the same horizon."""
    results = _run(synthetic_registry, synthetic_indicators, filled_cache, settings, months=12)
    at_five_years = results[results["horizon_months"] == 60]
    any_time = at_five_years[
        at_five_years["composition"] == Composition.ANY_TIME_WITHIN_HORIZON.value
    ]
    assert (any_time["predicted_probability"] > 0.0).all()


# ------------------------------------------------------- climatology and timing


def test_the_climatology_at_a_date_uses_only_outcomes_resolved_by_then() -> None:
    """The benchmark must not know something the model could not.

    An outcome is resolved once the last observation it rests on is published:
    the value labelled s + h months, which appears ``publication_lag_days`` after
    its label. Until 2026-09-15 this test asserted that month one's outcome was
    known *in* month four, the month its deciding value is labelled, which is
    weeks before that value exists. The assertion encoded the look-ahead; the
    invariance audit found it (ADR 0009).
    """
    index = pd.date_range("2000-01-01", periods=10, freq="MS")
    outcomes = pd.Series([1.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0], index=index)
    climatology = _expanding_climatology(outcomes, horizon_in_months=3, publication_lag_days=36)

    # Month one's outcome rests on month four's value, published 2000-05-07. So
    # nothing has resolved in months one to five.
    assert bool(climatology.iloc[:5].isna().all())
    # In month six, month one's outcome has been published, and only it.
    assert climatology.iloc[5] == pytest.approx(1.0)
    # In month eight, months one to three have resolved: two of three were positive.
    assert climatology.iloc[7] == pytest.approx(2 / 3)


def _climatology_of_one_outcome(publication_lag_days: int) -> pd.Series:
    """The benchmark built from forecasts starting 1999-03-01, all positive.

    The first one's twelve-month outcome rests on the value labelled 2000-03-01,
    so the benchmark is missing until that value is published and 1.0 from then.
    """
    index = pd.date_range("1999-03-01", "2001-12-01", freq="MS")
    return _expanding_climatology(
        pd.Series(1.0, index=index),
        horizon_in_months=12,
        publication_lag_days=publication_lag_days,
    )


def test_an_outcome_published_on_the_forecast_date_is_in_that_dates_benchmark() -> None:
    """2000-03-01 plus 31 days is 2000-04-01: published on the forecast date."""
    climatology = _climatology_of_one_outcome(31)
    assert np.isnan(climatology[pd.Timestamp("2000-03-01")])
    assert climatology[pd.Timestamp("2000-04-01")] == 1.0


def test_an_outcome_published_one_day_after_the_forecast_date_is_not() -> None:
    """2000-03-01 plus 32 days is 2000-04-02, one day too late for 2000-04-01."""
    climatology = _climatology_of_one_outcome(32)
    assert np.isnan(climatology[pd.Timestamp("2000-04-01")])
    assert climatology[pd.Timestamp("2000-05-01")] == 1.0


def test_a_recession_outcome_waits_the_full_four_hundred_days() -> None:
    """Recession dating is announced about 400 days late. 2000-03-01 plus 400 days
    is 2001-04-05, so the outcome is out of the benchmark through 2001-04-01 and in
    from 2001-05-01. The old shift counted it from 2000-03-01, thirteen months early.
    """
    climatology = _climatology_of_one_outcome(400)
    assert bool(climatology[:"2001-04-01"].isna().all())
    assert climatology[pd.Timestamp("2001-05-01")] == 1.0


def test_the_benchmark_waits_for_the_same_publication_lag_as_the_conditions(
    synthetic_registry, synthetic_indicators, filled_cache
) -> None:  # type: ignore[no-untyped-def]
    """One publication rule, not two: the last outcome the benchmark counts at a
    date rests on exactly the last condition the forecaster may read then."""
    histories = prepare_indicator_history(
        synthetic_indicators, synthetic_registry, filled_cache, (12,)
    )
    history = histories["rate_above_three_at_horizon"]
    outcomes = history.outcomes_by_horizon[12].dropna()
    forecast_date = pd.Timestamp("1990-01-01")
    deciding_labels = outcomes.index + pd.DateOffset(months=12)
    published = outcomes[
        deciding_labels + pd.Timedelta(days=history.publication_lag_days) <= forecast_date
    ]

    assert history.climatology_by_horizon[12][forecast_date] == pytest.approx(
        published.mean(), rel=1e-12
    )
    last_counted_label = published.index[-1] + pd.DateOffset(months=12)
    assert condition_available_at(history, forecast_date.date()).index[-1] == last_counted_label


def test_a_condition_is_only_used_once_its_publication_lag_has_passed(
    synthetic_registry, synthetic_indicators, filled_cache
) -> None:  # type: ignore[no-untyped-def]
    histories = prepare_indicator_history(
        synthetic_indicators, synthetic_registry, filled_cache, (12, 60)
    )
    history = histories["rate_above_three_at_horizon"]
    available = condition_available_at(history, date(1990, 1, 1))
    assert available.index[-1] == pd.Timestamp("1989-11-01")


def test_a_longer_lag_withholds_more_of_the_condition(
    synthetic_registry, synthetic_indicators, filled_cache
) -> None:  # type: ignore[no-untyped-def]
    histories = prepare_indicator_history(
        synthetic_indicators, synthetic_registry, filled_cache, (12,)
    )
    history = histories["rate_above_three_at_horizon"]
    early = condition_available_at(history, date(1990, 1, 1))
    later = condition_available_at(history, date(1991, 1, 1))
    assert later.index[-1] > early.index[-1]


# ------------------------------------------------------------- result contract


def _valid_results() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "indicator": ["a", "a"],
            "forecast_date": pd.to_datetime(["2000-01-01", "2000-02-01"]),
            "horizon_months": [12, 12],
            "predicted_probability": [0.4, 0.6],
            "climatology_probability": [0.5, 0.5],
            "realised_outcome": [1.0, 0.0],
            "composition": ["point_in_time"] * 2,
            "effective_sample_size": [100.0, 100.0],
            "distance_to_stationary": [0.3, 0.3],
            "regime_distribution": ["0.5,0.5", "0.5,0.5"],
            "state_count": [2, 2],
            "refit_date": pd.to_datetime(["2000-01-01", "2000-01-01"]),
            "configuration_hash": ["abc", "abc"],
            "seed": [1, 1],
            # Research arm A6 (fixed-climatology-blend).
            "model_probability": [0.3, 0.7],
            "climatology_probability_used_in_blend": [0.5, 0.5],
            "climatology_carried_forward": [False, False],
        }
    )


def test_a_valid_results_frame_passes_validation() -> None:
    validate_results(_valid_results())


def test_a_probability_outside_the_unit_interval_is_caught() -> None:
    broken = _valid_results()
    broken.loc[0, "predicted_probability"] = 1.4
    with pytest.raises(BacktestError, match="outside the unit interval"):
        validate_results(broken)


def test_a_repeated_indicator_date_and_horizon_is_caught() -> None:
    broken = pd.concat([_valid_results(), _valid_results().iloc[[0]]])
    with pytest.raises(BacktestError, match="repeat an indicator"):
        validate_results(broken)


def test_an_outcome_that_is_neither_zero_nor_one_is_caught() -> None:
    broken = _valid_results()
    broken.loc[0, "realised_outcome"] = 0.5
    with pytest.raises(BacktestError, match="zero or one"):
        validate_results(broken)


def test_an_empty_run_is_caught() -> None:
    with pytest.raises(BacktestError, match="no rows"):
        validate_results(_valid_results().iloc[0:0])


def test_a_missing_column_is_named() -> None:
    with pytest.raises(BacktestError, match="missing columns"):
        validate_results(_valid_results().drop(columns=["seed"]))


def test_the_snapshot_factory_produces_what_the_cache_expects(
    snapshot_factory: Callable[..., SeriesSnapshot],
) -> None:
    snapshot = snapshot_factory(
        pd.Series([1.0], index=pd.date_range("2000-01-01", periods=1, freq="MS"))
    )
    assert isinstance(snapshot.request, SeriesRequest)
    assert snapshot.retrieved_at == datetime(2026, 9, 8, tzinfo=UTC)


# ------------------------------------ A6: the fixed climatology blend (backtest)
#
# Research arm A6 (fixed-climatology-blend). The corrected diagnosis this arm was
# built from: `climatology_probability` is NaN at the live edge not because
# nothing has resolved, but because the benchmark's own index -- the resolution
# series' own months -- ends before the forecast schedule does. The tests below
# pin that mechanism directly (`climatology_probability_for_blend`), the blend
# arithmetic (`blend_model_and_climatology_probability`), and the two properties
# the corrected design guarantees end to end: no look-ahead in the carry-forward,
# and no row evaluation would score ever takes it.


def test_climatology_for_blend_uses_the_exact_date_when_it_exists() -> None:
    climatology = pd.Series(
        [0.2, 0.3, 0.4], index=pd.date_range("2000-01-01", periods=3, freq="MS")
    )
    value, carried_forward = climatology_probability_for_blend(
        climatology, pd.Timestamp("2000-02-01")
    )
    assert value == pytest.approx(0.3)
    assert carried_forward is False


def test_climatology_for_blend_carries_forward_across_a_gap() -> None:
    """The benchmark's index simply has no 2000-04-01 entry -- main's live edge,
    reproduced directly rather than through the whole pipeline."""
    climatology = pd.Series(
        [0.2, 0.3, 0.4], index=pd.to_datetime(["2000-01-01", "2000-02-01", "2000-03-01"])
    )
    value, carried_forward = climatology_probability_for_blend(
        climatology, pd.Timestamp("2000-04-01")
    )
    assert value == pytest.approx(0.4)
    assert carried_forward is True


def test_climatology_for_blend_never_reads_past_the_forecast_date() -> None:
    """Requirement 1: the boundary test. A value exists strictly AFTER the
    forecast date and nothing on or before it; the carry-forward must not find
    it, because using it would be exactly the look-ahead this project forbids.
    """
    climatology = pd.Series([np.nan, 0.9], index=pd.to_datetime(["2000-01-01", "2000-03-01"]))
    value, carried_forward = climatology_probability_for_blend(
        climatology, pd.Timestamp("2000-02-01")
    )
    assert np.isnan(value)
    assert carried_forward is False


def test_climatology_for_blend_carries_forward_exactly_to_the_date_on_or_before() -> None:
    """The other half of the boundary: a value defined exactly ON the forecast
    date must be preferred over an earlier one, and a value the day after must
    never be used."""
    climatology = pd.Series([0.1, 0.5], index=pd.to_datetime(["2000-01-01", "2000-02-01"]))
    on_date, _ = climatology_probability_for_blend(climatology, pd.Timestamp("2000-02-01"))
    assert on_date == pytest.approx(0.5)

    day_before = climatology.copy()
    day_before.index = pd.to_datetime(["2000-01-01", "2000-02-02"])  # one day after 2000-02-01
    value, carried_forward = climatology_probability_for_blend(
        day_before, pd.Timestamp("2000-02-01")
    )
    assert value == pytest.approx(0.1)  # the 02-02 entry must not be used
    assert carried_forward is True


def test_climatology_for_blend_skips_an_internal_nan_when_carrying_forward() -> None:
    """`_expanding_climatology` can itself hold an internal NaN (nothing had
    resolved yet at that date); the carry-forward must reach past it to the last
    real value, exactly what `Series.asof` guarantees."""
    climatology = pd.Series(
        [0.25, np.nan, np.nan],
        index=pd.to_datetime(["2000-01-01", "2000-02-01", "2000-03-01"]),
    )
    value, carried_forward = climatology_probability_for_blend(
        climatology, pd.Timestamp("2000-04-01")
    )
    assert value == pytest.approx(0.25)
    assert carried_forward is True


def test_climatology_for_blend_reports_nan_when_nothing_precedes_the_date() -> None:
    climatology = pd.Series([np.nan, 0.6], index=pd.to_datetime(["2000-01-01", "2000-03-01"]))
    value, carried_forward = climatology_probability_for_blend(
        climatology, pd.Timestamp("2000-02-01")
    )
    assert np.isnan(value)
    assert carried_forward is False


def test_blend_averages_model_and_climatology_at_the_configured_weight() -> None:
    assert blend_model_and_climatology_probability(0.8, 0.2, model_weight=0.5) == pytest.approx(0.5)
    assert blend_model_and_climatology_probability(0.8, 0.2, model_weight=1.0) == pytest.approx(0.8)
    assert blend_model_and_climatology_probability(0.8, 0.2, model_weight=0.0) == pytest.approx(0.2)


def test_blend_raises_rather_than_produce_nan_from_a_nan_climatology() -> None:
    """No silent fallback: a caller that reaches this function with a raw,
    uncarried-forward NaN gets a loud error, never a quietly propagated NaN."""
    with pytest.raises(BacktestError, match="non-finite climatology"):
        blend_model_and_climatology_probability(0.8, float("nan"), model_weight=0.5)


def test_blend_raises_on_a_non_finite_model_probability() -> None:
    with pytest.raises(BacktestError, match="non-finite model probability"):
        blend_model_and_climatology_probability(float("nan"), 0.2, model_weight=0.5)


def test_the_carry_forward_record_counts_and_names_the_rows_that_used_it() -> None:
    record = climatology_carry_forward_record(
        configuration_hash="abc",
        indicator=pd.Series(["x", "x", "y"]),
        horizon_months=pd.Series([12, 12, 12]),
        forecast_date=pd.Series(pd.to_datetime(["2026-08-01", "2026-09-01", "2026-09-01"])),
        carried_forward=pd.Series([True, True, False]),
    )
    assert record["row_count"] == 3
    assert record["carried_forward_row_count"] == 2
    assert record["carried_forward_rows"] == [
        {"indicator": "x", "forecast_date": "2026-08-01", "horizon_months": 12},
        {"indicator": "x", "forecast_date": "2026-09-01", "horizon_months": 12},
    ]


def test_climatology_is_carried_forward_at_the_live_edge_and_never_on_a_scored_row(
    synthetic_registry, filled_cache, settings, snapshot_factory
) -> None:  # type: ignore[no-untyped-def]
    """The mechanism this arm was corrected to handle, exercised end to end
    through `run_walk_forward`. `synthetic_rate`'s own model-input cache runs
    the fixture's full 480 months, to 2009-12; a resolution-only series (not a
    model input, so the model keeps fitting fine) is given a shorter cache
    ending twelve months earlier, at 2008-12 -- main's live edge, reproduced on
    purpose. Forecast dates past that boundary must carry the benchmark forward,
    record having done so, never look ahead to do it, and never do it on a row
    that has both a realised outcome and an exact-date benchmark -- the two
    things `evaluation.verdict` requires before it will score a row.
    """
    live_edge_series = _series_entry("synthetic_live_edge", "SYNLIVE", None, Transform.LEVEL, False)
    registry = dataclasses.replace(
        synthetic_registry, series=(*synthetic_registry.series, live_edge_series)
    )
    live_edge_indicator = BinaryIndicator(
        name="live_edge_above_fifty_at_horizon",
        question="is the live-edge series above fifty at the horizon",
        resolution=IndicatorResolution(
            series="synthetic_live_edge",
            rule=ResolutionRule.LEVEL_ABOVE_THRESHOLD_AT_HORIZON,
            transform=Transform.LEVEL,
            threshold=50.0,
        ),
        composition=Composition.POINT_IN_TIME,
        horizons_in_years=(1, 5),
    )

    short_index = pd.date_range(START, periods=MONTHS - 12, freq="MS", name="observation_date")
    filled_cache.write(snapshot_factory(pd.Series(60.0, index=short_index), series_id="SYNLIVE"))

    schedule = schedule_module.build_schedule(
        date(2008, 6, 1), date(2009, 3, 1), settings.refit_every_n_months
    )
    results = run_walk_forward(
        registry,
        (live_edge_indicator,),
        filled_cache,
        settings,
        2,
        schedule.forecast_dates,
        schedule.refit_dates,
        artifacts=None,
        progress_every=0,
    )

    carried = results[results["climatology_carried_forward"]]
    assert not carried.empty, "the test did not exercise the carry-forward path"

    # Requirement 1: no look-ahead. Every carried-forward row's forecast date is
    # on or after the boundary where the benchmark's own index runs out.
    assert (carried["forecast_date"] >= pd.Timestamp("2008-12-01")).all()

    # The exact-date benchmark stays NaN on exactly these rows -- unchanged from
    # what it always was, which is what keeps evaluation's dropna excluding them.
    assert carried["climatology_probability"].isna().all()

    # Requirement 2: a carried-forward row is never a scored one.
    scored = results.dropna(subset=["realised_outcome", "climatology_probability"])
    assert not scored["climatology_carried_forward"].any()

    # The blend still produced a finite probability everywhere -- no NaN leaked
    # into gate three or gate four.
    assert results["predicted_probability"].notna().all()
    assert results["predicted_probability"].between(0.0, 1.0).all()


def test_the_blended_probability_matches_the_recorded_weight_and_inputs(
    synthetic_registry, synthetic_indicators, filled_cache, settings
) -> None:  # type: ignore[no-untyped-def]
    """`predicted_probability` must be exactly the configured blend of the two
    columns kept for that purpose -- an algebraic tie between what is recorded
    and what evaluation reads."""
    assert settings.climatology_blend_model_weight == 0.5  # the arm's default
    results = _run(synthetic_registry, synthetic_indicators, filled_cache, settings, months=12)
    expected = (
        settings.climatology_blend_model_weight * results["model_probability"]
        + (1.0 - settings.climatology_blend_model_weight)
        * results["climatology_probability_used_in_blend"]
    )
    pd.testing.assert_series_equal(results["predicted_probability"], expected, check_names=False)


def test_a_weight_of_one_reproduces_the_unblended_model_probability(
    synthetic_registry, synthetic_indicators, filled_cache, settings
) -> None:  # type: ignore[no-untyped-def]
    """1.0 is the value the omission map treats as "no blend"; this is the
    behavioural claim that value encodes, checked directly."""
    shipped_settings = dataclasses.replace(settings, climatology_blend_model_weight=1.0)
    results = _run(
        synthetic_registry, synthetic_indicators, filled_cache, shipped_settings, months=12
    )
    pd.testing.assert_series_equal(
        results["predicted_probability"],
        results["model_probability"],
        check_names=False,
    )
