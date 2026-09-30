"""The two reference forecasters rule 0007 measures every claim against.

R1 is the climatology restricted to the model's own sample; R2 is a two-state
Markov chain on each indicator's own monthly condition, with no regimes. Both ride
beside every backtest forecast as columns, so these tests pin the arithmetic each
one rests on, against closed forms where one exists and against the code it must
agree with where it does not.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from economic_regime_forecasting import command_line_interface, regression_baseline
from economic_regime_forecasting.backtest import walk_forward
from economic_regime_forecasting.configuration.registry import Composition
from economic_regime_forecasting.models import indicator_forecast
from economic_regime_forecasting.models.indicator_forecast import (
    SINGLE_REGIME_DISTRIBUTION,
    SINGLE_REGIME_TRANSITION_MATRIX,
    ConditionalRates,
    ForecastCompositionError,
    compose_through_the_condition_chain,
    compose_through_the_condition_chain_at_every_horizon,
)


def _rates(entry: list[float], persistence: list[float]) -> ConditionalRates:
    count = len(entry)
    return ConditionalRates(
        indicator_name="an_indicator",
        occupancy_rate=np.full(count, 0.3),
        entry_hazard=np.asarray(entry, dtype="float64"),
        persistence=np.asarray(persistence, dtype="float64"),
        occupancy_sample_size=np.full(count, 100.0),
        entry_sample_size=np.full(count, 80.0),
        persistence_sample_size=np.full(count, 20.0),
        pooled_occupancy_rate=0.3,
        pooled_entry_hazard=float(np.mean(entry)),
        pooled_persistence=float(np.mean(persistence)),
        shrinkage_strength=10.0,
        months_used=100,
    )


TRANSITIONS = np.array([[0.9, 0.08, 0.02], [0.05, 0.9, 0.05], [0.1, 0.1, 0.8]])
REGIMES = np.array([0.2, 0.5, 0.3])
THREE_REGIME_RATES = _rates([0.02, 0.1, 0.3], [0.7, 0.85, 0.95])


# ------------------------------------------------ the chain with no regimes


@pytest.mark.parametrize("held", [False, True])
@pytest.mark.parametrize("gap", [0, 1, 13])
def test_with_one_regime_a_point_in_time_question_is_the_two_state_chain_stepped(
    held: bool, gap: int
) -> None:
    entry, persistence = 0.04, 0.9
    step = np.array([[1 - entry, entry], [1 - persistence, persistence]])
    start = np.array([0.0, 1.0]) if held else np.array([1.0, 0.0])
    curve = compose_through_the_condition_chain_at_every_horizon(
        SINGLE_REGIME_TRANSITION_MATRIX,
        SINGLE_REGIME_DISTRIBUTION,
        _rates([entry], [persistence]),
        Composition.POINT_IN_TIME,
        24,
        held,
        gap,
    )
    for horizon in (1, 12, 24):
        expected = (start @ np.linalg.matrix_power(step, gap + horizon))[1]
        assert curve[horizon - 1] == pytest.approx(expected, abs=1e-13)


@pytest.mark.parametrize("held", [False, True])
@pytest.mark.parametrize("gap", [0, 2, 13])
def test_with_one_regime_an_any_time_question_is_one_minus_survival(held: bool, gap: int) -> None:
    entry, persistence = 0.04, 0.9
    step = np.array([[1 - entry, entry], [1 - persistence, persistence]])
    start = np.array([0.0, 1.0]) if held else np.array([1.0, 0.0])
    at_forecast = start @ np.linalg.matrix_power(step, gap)
    curve = compose_through_the_condition_chain_at_every_horizon(
        SINGLE_REGIME_TRANSITION_MATRIX,
        SINGLE_REGIME_DISTRIBUTION,
        _rates([entry], [persistence]),
        Composition.ANY_TIME_WITHIN_HORIZON,
        60,
        held,
        gap,
    )
    for horizon in (1, 12, 60):
        never = at_forecast[0] * (1 - entry) ** horizon + at_forecast[1] * (1 - persistence) * (
            1 - entry
        ) ** (horizon - 1)
        assert curve[horizon - 1] == pytest.approx(1.0 - never, abs=1e-13)


# ------------------------------------------------ with regimes


@pytest.mark.parametrize("held", [False, True])
def test_with_no_gap_the_any_time_path_agrees_with_the_one_the_model_uses(held: bool) -> None:
    """The pipeline's any-time composition starts from the last published condition
    as if it were this month's. With no gap to step, the chain must agree with it."""

    class Model:
        transition_matrix = TRANSITIONS

    for horizon in (1, 12, 120):
        existing = indicator_forecast.compose_any_time_within_horizon(
            Model(),  # type: ignore[arg-type]
            REGIMES,
            THREE_REGIME_RATES,
            horizon,
            held,
        )
        chained = compose_through_the_condition_chain(
            TRANSITIONS,
            REGIMES,
            THREE_REGIME_RATES,
            Composition.ANY_TIME_WITHIN_HORIZON,
            horizon,
            held,
            0,
        )
        assert chained == pytest.approx(existing, rel=1e-12, abs=1e-14)


def test_a_memoryless_condition_reduces_to_the_projected_regime_distribution() -> None:
    """When persistence equals the entry hazard, the condition is a fresh draw in
    each regime every month, and the point-in-time answer is the projection dotted
    with that rate -- the model's own point-in-time composition."""
    rate = np.array([0.1, 0.4, 0.7])
    rates = _rates(list(rate), list(rate))
    for gap, horizon in ((0, 1), (2, 12), (5, 60)):
        expected = REGIMES @ np.linalg.matrix_power(TRANSITIONS, gap + horizon) @ rate
        for held in (False, True):
            got = compose_through_the_condition_chain(
                TRANSITIONS, REGIMES, rates, Composition.POINT_IN_TIME, horizon, held, gap
            )
            assert got == pytest.approx(expected, abs=1e-13)


@pytest.mark.parametrize(
    "composition", [Composition.POINT_IN_TIME, Composition.ANY_TIME_WITHIN_HORIZON]
)
def test_one_horizon_and_the_whole_curve_agree_to_the_bit(composition: Composition) -> None:
    curve = compose_through_the_condition_chain_at_every_horizon(
        TRANSITIONS, REGIMES, THREE_REGIME_RATES, composition, 120, True, 3
    )
    for horizon in (1, 12, 60, 120):
        single = compose_through_the_condition_chain(
            TRANSITIONS, REGIMES, THREE_REGIME_RATES, composition, horizon, True, 3
        )
        assert single == curve[horizon - 1]


def test_any_time_probabilities_never_fall_as_the_window_grows() -> None:
    curve = compose_through_the_condition_chain_at_every_horizon(
        TRANSITIONS, REGIMES, THREE_REGIME_RATES, Composition.ANY_TIME_WITHIN_HORIZON, 120, False, 1
    )
    assert np.all(np.diff(curve) >= -1e-15)
    assert np.all((curve >= 0.0) & (curve <= 1.0))


def test_the_chain_refuses_what_it_cannot_compose() -> None:
    with pytest.raises(ForecastCompositionError, match="at least one month"):
        compose_through_the_condition_chain(
            TRANSITIONS, REGIMES, THREE_REGIME_RATES, Composition.POINT_IN_TIME, 0, False, 1
        )
    with pytest.raises(ForecastCompositionError, match="postdate"):
        compose_through_the_condition_chain(
            TRANSITIONS, REGIMES, THREE_REGIME_RATES, Composition.POINT_IN_TIME, 12, False, -1
        )
    with pytest.raises(ForecastCompositionError, match="cannot move"):
        compose_through_the_condition_chain(
            TRANSITIONS[:2, :2],
            REGIMES,
            THREE_REGIME_RATES,
            Composition.POINT_IN_TIME,
            12,
            False,
            1,
        )
    with pytest.raises(ForecastCompositionError, match="rates for 1 regimes"):
        compose_through_the_condition_chain(
            TRANSITIONS,
            REGIMES,
            _rates([0.1], [0.9]),
            Composition.POINT_IN_TIME,
            12,
            False,
            1,
        )


def test_the_single_regime_constants_cannot_be_changed_by_accident() -> None:
    with pytest.raises(ValueError):
        SINGLE_REGIME_TRANSITION_MATRIX[0, 0] = 0.5
    with pytest.raises(ValueError):
        SINGLE_REGIME_DISTRIBUTION[0] = 0.5


def test_months_between_counts_calendar_months() -> None:
    assert walk_forward.months_between(pd.Timestamp("2020-11-01"), pd.Timestamp("2021-02-01")) == 3
    assert walk_forward.months_between(pd.Timestamp("2021-02-01"), pd.Timestamp("2021-02-01")) == 0


# ------------------------------------------------ R1, the model-sample climatology


def _outcomes() -> pd.Series:
    dates = pd.date_range("1940-01-01", periods=240, freq="MS")
    values = (np.sin(np.arange(240) / 7.0) > 0.3).astype("float64")
    values[[5, 60, 61, 130]] = np.nan
    return pd.Series(values, index=dates)


def test_from_the_first_forecast_date_the_totals_reproduce_the_expanding_climatology() -> None:
    outcomes = _outcomes()
    horizon, lag = 12, 35
    expanding = walk_forward._expanding_climatology(outcomes, horizon, lag)
    totals = walk_forward.ResolvedOutcomeTotals.from_outcomes(
        outcomes, walk_forward.outcome_publication_dates(outcomes, horizon, lag)
    )
    for stamp in outcomes.index[::7]:
        got = totals.average_published_by(stamp, outcomes.index[0])
        if np.isnan(expanding[stamp]):
            assert np.isnan(got)
        else:
            assert got == pytest.approx(expanding[stamp], abs=1e-12)


def test_the_model_sample_climatology_counts_nothing_before_the_sample_starts() -> None:
    outcomes = _outcomes()
    horizon, lag = 12, 35
    published = walk_forward.outcome_publication_dates(outcomes, horizon, lag)
    totals = walk_forward.ResolvedOutcomeTotals.from_outcomes(outcomes, published)
    starts = pd.Timestamp("1950-12-01")
    as_of = pd.Timestamp("1958-06-01")
    counted = outcomes[(outcomes.index >= starts) & (published <= as_of)].dropna()
    assert totals.average_published_by(as_of, starts) == pytest.approx(counted.mean(), abs=1e-12)
    # Nothing published inside the sample yet: missing, never a borrowed number.
    assert np.isnan(totals.average_published_by(pd.Timestamp("1951-06-01"), starts))


# ------------------------------------------------ comparing on a benchmark


def _forecasts(configuration: str, with_model_sample: bool) -> pd.DataFrame:
    generator = np.random.default_rng(7)
    dates = pd.date_range("1995-01-01", periods=120, freq="MS")
    rows: list[dict[str, Any]] = []
    for indicator in ("first", "second"):
        outcomes = (generator.uniform(size=len(dates)) < 0.4).astype(float)
        noise = generator.normal(0, 0.1, len(dates))
        predicted = np.clip(0.4 + 0.3 * (outcomes - 0.4) + noise, 0.01, 0.99)
        for position, stamp in enumerate(dates):
            row = {
                "indicator": indicator,
                "forecast_date": stamp,
                "horizon_months": 12,
                "predicted_probability": float(predicted[position]),
                "climatology_probability": 0.5,
                "realised_outcome": float(outcomes[position]),
                "configuration_hash": configuration,
            }
            if with_model_sample:
                row["model_sample_climatology_probability"] = 0.4
            rows.append(row)
    return pd.DataFrame(rows)


def _summary(configuration: str) -> dict[str, Any]:
    return {
        "format_version": regression_baseline.FORMAT_VERSION,
        "run": {"configuration_hash": configuration},
        "horizons": [],
    }


def _compare(baseline: pd.DataFrame, current: pd.DataFrame, benchmark: str) -> Any:
    return regression_baseline.compare_paired(
        _summary("base"),
        baseline,
        _summary("run"),
        current.assign(configuration_hash="run"),
        random_seed=20260908,
        resamples=100,
        confidence_levels=(0.90,),
        benchmark=benchmark,
    )


def test_the_model_sample_benchmark_scores_against_its_own_column() -> None:
    frame = _forecasts("base", with_model_sample=True)
    model_sample = _compare(frame, frame, "model-sample")

    def skill(indicator: str, climatology: float) -> float:
        rows = frame[frame["indicator"] == indicator]
        outcome = rows["realised_outcome"].to_numpy()
        forecast_error = np.mean((rows["predicted_probability"].to_numpy() - outcome) ** 2)
        return float(1.0 - forecast_error / np.mean((climatology - outcome) ** 2))

    against_its_column = np.mean([skill(name, 0.4) for name in ("first", "second")])
    against_the_series_start = np.mean([skill(name, 0.5) for name in ("first", "second")])
    measured = model_sample.horizons[0].result.current_mean_skill
    assert measured == pytest.approx(against_its_column, abs=1e-12)
    assert measured != pytest.approx(against_the_series_start, abs=1e-6)
    assert model_sample.horizons[0].result.difference == 0.0
    assert model_sample.as_dictionary()["benchmark"]["name"] == "model-sample"
    assert "model-sample climatology" in model_sample.describe()


def test_a_baseline_without_the_model_sample_column_is_refused_not_read_on_another() -> None:
    old = _forecasts("base", with_model_sample=False)
    new = _forecasts("base", with_model_sample=True)
    with pytest.raises(regression_baseline.BaselineError, match="captured before rule 0007"):
        _compare(old, new, "model-sample")


def test_an_unknown_benchmark_is_refused() -> None:
    frame = _forecasts("base", with_model_sample=True)
    with pytest.raises(regression_baseline.BaselineError, match="no benchmark called"):
        _compare(frame, frame, "last-decade")


# ------------------------------------------------ the zeros trap


def test_a_run_whose_artifacts_another_configuration_wrote_cannot_be_compared() -> None:
    """Experiment 0005: gates failed before the backtest wrote anything, the cache
    still held main's artifacts, and the comparison read main against itself as
    +0.0000 at every horizon."""
    workspace = SimpleNamespace(settings=SimpleNamespace(configuration_hash=lambda: "arm"))
    with pytest.raises(regression_baseline.BaselineError, match="never wrote artifacts"):
        command_line_interface._require_artifacts_from_these_settings(
            workspace,  # type: ignore[arg-type]
            {"run": {"configuration_hash": "main"}},
        )
    command_line_interface._require_artifacts_from_these_settings(
        workspace,  # type: ignore[arg-type]
        {"run": {"configuration_hash": "arm"}},
    )
