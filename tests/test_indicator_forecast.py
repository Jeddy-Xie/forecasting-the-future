"""Turning per-regime rates into a horizon probability.

The two composition paths answer different questions and the tests keep them
apart. The one that matters most pins that an any-time question composed over the
path gives a larger answer than the same question composed point-in-time, and
grows with the horizon: getting this backwards is a silent, systematic
understatement that no other check would catch.
"""

from __future__ import annotations

import numpy as np
import pytest

from economic_regime_forecasting.configuration.registry import (
    BinaryIndicator,
    Composition,
    IndicatorResolution,
    ResolutionRule,
    Transform,
)
from economic_regime_forecasting.models.gaussian_hidden_markov_model import (
    GaussianHiddenMarkovModel,
)
from economic_regime_forecasting.models.indicator_forecast import (
    ForecastCompositionError,
    compose_any_time_within_horizon,
    compose_point_in_time,
    estimate_conditional_rates,
    forecast_indicator,
)


def _model() -> GaussianHiddenMarkovModel:
    """Two persistent regimes, one calm and one turbulent."""
    return GaussianHiddenMarkovModel(
        initial_distribution=np.array([0.5, 0.5]),
        transition_matrix=np.array([[0.97, 0.03], [0.06, 0.94]]),
        means=np.array([[-1.0], [1.0]]),
        covariances=np.array([[[1.0]], [[1.0]]]),
    )


def _indicator(composition: Composition) -> BinaryIndicator:
    rule = (
        ResolutionRule.LEVEL_ABOVE_THRESHOLD_WITHIN_HORIZON
        if composition is Composition.ANY_TIME_WITHIN_HORIZON
        else ResolutionRule.LEVEL_ABOVE_THRESHOLD_AT_HORIZON
    )
    return BinaryIndicator(
        name="test_indicator",
        question="does the thing happen",
        resolution=IndicatorResolution(
            series="test_series", rule=rule, transform=Transform.LEVEL, threshold=1.0
        ),
        composition=composition,
        horizons_in_years=(1, 5, 10),
    )


def _rates(condition: np.ndarray, weights: np.ndarray, shrinkage: float = 0.0):  # type: ignore[no-untyped-def]
    return estimate_conditional_rates(
        _indicator(Composition.POINT_IN_TIME), condition, weights, shrinkage
    )


def test_rates_with_no_shrinkage_are_the_plain_frequencies() -> None:
    """Hard state assignments, so the answer can be counted by hand: the first
    regime sees the condition in two of four months, the second in one of two."""
    condition = np.array([1.0, 0.0, 1.0, 0.0, 1.0, 0.0])
    weights = np.array([[1.0, 0.0]] * 4 + [[0.0, 1.0]] * 2)
    rates = _rates(condition, weights)
    assert rates.occupancy_rate[0] == pytest.approx(0.5)
    assert rates.occupancy_rate[1] == pytest.approx(0.5)
    assert rates.occupancy_sample_size[0] == pytest.approx(4.0)


def test_shrinkage_pulls_a_thin_regime_toward_the_pooled_rate() -> None:
    """A regime with two months behind it should not be trusted with an unshrunk
    frequency; a regime with hundreds should barely move."""
    condition = np.array([1.0] * 2 + [0.0] * 200)
    weights = np.array([[1.0, 0.0]] * 2 + [[0.0, 1.0]] * 200)
    unshrunk = _rates(condition, weights, shrinkage=0.0)
    shrunk = _rates(condition, weights, shrinkage=10.0)
    assert unshrunk.occupancy_rate[0] == pytest.approx(1.0)
    assert shrunk.occupancy_rate[0] < 0.35
    assert shrunk.occupancy_rate[1] == pytest.approx(unshrunk.occupancy_rate[1], abs=0.01)


def test_partial_state_evidence_is_used_in_proportion() -> None:
    """A month the model is sixty-forty unsure about contributes to both regimes."""
    condition = np.array([1.0, 0.0])
    weights = np.array([[0.6, 0.4], [0.6, 0.4]])
    rates = _rates(condition, weights)
    assert rates.occupancy_rate[0] == pytest.approx(0.5)
    assert rates.occupancy_sample_size[0] == pytest.approx(1.2)


def test_entry_and_persistence_are_estimated_separately() -> None:
    """A sticky condition has a low entry hazard and a high persistence, and
    collapsing them into one occupancy rate loses exactly that distinction."""
    condition = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0])
    weights = np.ones((10, 1))
    rates = estimate_conditional_rates(
        _indicator(Composition.ANY_TIME_WITHIN_HORIZON), condition, weights, 0.0
    )
    assert rates.entry_hazard[0] < 0.25
    assert rates.persistence[0] > 0.6


def test_a_point_in_time_forecast_is_the_projected_distribution_dotted_with_rates() -> None:
    condition = np.array([1.0] * 10 + [0.0] * 10)
    weights = np.array([[1.0, 0.0]] * 10 + [[0.0, 1.0]] * 10)
    rates = _rates(condition, weights)
    projected = np.array([0.25, 0.75])
    expected = 0.25 * rates.occupancy_rate[0] + 0.75 * rates.occupancy_rate[1]
    assert compose_point_in_time(projected, rates) == pytest.approx(expected)


def test_an_any_time_forecast_exceeds_the_point_in_time_one() -> None:
    """The central property. Asking whether something happens at any point in five
    years must give a bigger number than asking about the single month five years
    out, and the gap must widen with the horizon."""
    condition = np.array(([1.0] * 3 + [0.0] * 7) * 10)
    weights = np.tile(np.array([[0.5, 0.5]]), (100, 1))
    rates = estimate_conditional_rates(
        _indicator(Composition.ANY_TIME_WITHIN_HORIZON), condition, weights, 1.0
    )
    model = _model()
    start = np.array([0.5, 0.5])

    gaps = []
    for horizon in (12, 60, 120):
        any_time = compose_any_time_within_horizon(model, start, rates, horizon, False)
        point = compose_point_in_time(model.project_state_distribution(start, horizon), rates)
        assert any_time > point, horizon
        gaps.append(any_time - point)
    assert gaps == sorted(gaps)


def test_an_any_time_probability_rises_with_the_horizon() -> None:
    condition = np.array(([1.0] + [0.0] * 19) * 10)
    weights = np.tile(np.array([[0.5, 0.5]]), (200, 1))
    rates = estimate_conditional_rates(
        _indicator(Composition.ANY_TIME_WITHIN_HORIZON), condition, weights, 1.0
    )
    probabilities = [
        compose_any_time_within_horizon(_model(), np.array([0.5, 0.5]), rates, horizon, False)
        for horizon in (1, 12, 60, 120)
    ]
    assert probabilities == sorted(probabilities)
    assert all(0.0 <= value <= 1.0 for value in probabilities)


def test_a_condition_that_already_holds_raises_the_next_month_through_persistence() -> None:
    """Whether the condition holds today is observable at forecast time, so using
    it is information rather than look-ahead."""
    condition = np.array(([1.0] * 6 + [0.0] * 14) * 10)
    weights = np.tile(np.array([[1.0, 0.0]]), (200, 1))
    rates = estimate_conditional_rates(
        _indicator(Composition.ANY_TIME_WITHIN_HORIZON), condition, weights, 1.0
    )
    holding = compose_any_time_within_horizon(_model(), np.array([1.0, 0.0]), rates, 6, True)
    not_holding = compose_any_time_within_horizon(_model(), np.array([1.0, 0.0]), rates, 6, False)
    assert holding > not_holding


def test_a_condition_that_never_happens_forecasts_zero() -> None:
    condition = np.zeros(100)
    weights = np.tile(np.array([[0.5, 0.5]]), (100, 1))
    rates = estimate_conditional_rates(
        _indicator(Composition.ANY_TIME_WITHIN_HORIZON), condition, weights, 0.0
    )
    assert compose_any_time_within_horizon(
        _model(), np.array([0.5, 0.5]), rates, 120, False
    ) == pytest.approx(0.0)


def test_a_condition_that_always_holds_forecasts_one() -> None:
    condition = np.ones(100)
    weights = np.tile(np.array([[0.5, 0.5]]), (100, 1))
    rates = estimate_conditional_rates(
        _indicator(Composition.POINT_IN_TIME), condition, weights, 0.0
    )
    assert compose_point_in_time(np.array([0.5, 0.5]), rates) == pytest.approx(1.0)


def test_a_forecast_carries_its_evidence_and_its_distance_to_the_base_rate() -> None:
    condition = np.array(([1.0] * 4 + [0.0] * 16) * 10)
    weights = np.tile(np.array([[0.5, 0.5]]), (200, 1))
    indicator = _indicator(Composition.POINT_IN_TIME)
    rates = estimate_conditional_rates(indicator, condition, weights, 1.0)
    composed = forecast_indicator(indicator, _model(), np.array([0.9, 0.1]), rates, 12, False)
    assert 0.0 <= composed.probability <= 1.0
    assert composed.effective_sample_size > 0.0
    assert composed.distance_to_stationary >= 0.0
    assert len(composed.projected_state_distribution) == 2


def test_a_longer_horizon_leaves_less_distance_to_the_base_rate() -> None:
    condition = np.array(([1.0] * 4 + [0.0] * 16) * 10)
    weights = np.tile(np.array([[0.5, 0.5]]), (200, 1))
    indicator = _indicator(Composition.POINT_IN_TIME)
    rates = estimate_conditional_rates(indicator, condition, weights, 1.0)
    distances = [
        forecast_indicator(
            indicator, _model(), np.array([1.0, 0.0]), rates, horizon, False
        ).distance_to_stationary
        for horizon in (12, 60, 120, 480)
    ]
    assert distances == sorted(distances, reverse=True)
    assert distances[-1] < 0.01


def test_misaligned_condition_and_state_history_is_reported() -> None:
    with pytest.raises(ForecastCompositionError, match="Align them"):
        _rates(np.zeros(10), np.zeros((8, 2)))


def test_unresolved_months_in_the_condition_are_refused() -> None:
    """Treating an unknown month as a zero would bias every rate downward."""
    condition = np.array([1.0, np.nan, 0.0])
    with pytest.raises(ForecastCompositionError, match="unresolved months"):
        _rates(condition, np.ones((3, 1)))


def test_a_zero_month_horizon_is_meaningless_for_an_any_time_question() -> None:
    condition = np.zeros(10)
    rates = estimate_conditional_rates(
        _indicator(Composition.ANY_TIME_WITHIN_HORIZON), condition, np.ones((10, 1)), 0.0
    )
    with pytest.raises(ForecastCompositionError, match="at least one month"):
        compose_any_time_within_horizon(_model(), np.array([1.0]), rates, 0, False)
