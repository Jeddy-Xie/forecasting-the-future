"""Metrics are checked against values worked out by hand.

Brier and the skill score get hand-computed cases because they are the headline
numbers and a sign error in either would flatter or damn the model without any
other test noticing.
"""

from __future__ import annotations

import numpy as np
import pytest

from economic_regime_forecasting.evaluation.bootstrap import (
    BootstrapError,
    effective_independent_sample_size,
    moving_block_bootstrap,
)
from economic_regime_forecasting.evaluation.calibration import assess_calibration
from economic_regime_forecasting.evaluation.scoring import (
    ScoringError,
    area_under_the_curve,
    brier_score,
    brier_skill_score,
    logarithmic_loss,
    murphy_decomposition,
)


def test_brier_score_matches_a_hand_computed_value() -> None:
    """Squared errors of 0.01, 0.01, 0.04 and 0.09 average to 0.0375."""
    predicted = np.array([0.9, 0.1, 0.8, 0.3])
    realised = np.array([1.0, 0.0, 1.0, 0.0])
    assert brier_score(predicted, realised) == pytest.approx(0.0375)


def test_a_perfect_forecast_scores_zero_and_a_reversed_one_scores_one() -> None:
    realised = np.array([1.0, 0.0, 1.0])
    assert brier_score(realised, realised) == 0.0
    assert brier_score(1.0 - realised, realised) == 1.0


def test_the_skill_score_is_zero_against_the_forecaster_itself() -> None:
    predicted = np.array([0.7, 0.2, 0.9, 0.4])
    realised = np.array([1.0, 0.0, 1.0, 0.0])
    assert brier_skill_score(predicted, realised, predicted) == pytest.approx(0.0)


def test_the_skill_score_is_negative_when_the_model_is_worse_than_the_base_rate() -> None:
    realised = np.array([1.0, 1.0, 0.0, 0.0])
    confident_and_wrong = np.array([0.1, 0.1, 0.9, 0.9])
    assert brier_skill_score(confident_and_wrong, realised, np.full(4, 0.5)) < 0.0


def test_a_perfect_benchmark_makes_the_skill_score_undefined_rather_than_infinite() -> None:
    realised = np.array([1.0, 1.0, 1.0])
    with pytest.raises(ScoringError, match="undefined"):
        brier_skill_score(np.full(3, 0.9), realised, realised)


def test_log_loss_clips_so_a_confident_mistake_is_finite() -> None:
    loss = logarithmic_loss(np.array([0.0]), np.array([1.0]), clip=(0.01, 0.99))
    assert loss == pytest.approx(-np.log(0.01))


def test_log_loss_of_a_certain_correct_forecast_is_nearly_zero() -> None:
    assert logarithmic_loss(np.array([1.0, 0.0]), np.array([1.0, 0.0])) == pytest.approx(
        -np.log(0.99)
    )


def test_area_under_the_curve_is_one_for_perfect_ranking_and_a_half_for_none() -> None:
    realised = np.array([1.0, 1.0, 0.0, 0.0])
    assert area_under_the_curve(np.array([0.9, 0.8, 0.2, 0.1]), realised) == pytest.approx(1.0)
    assert area_under_the_curve(np.full(4, 0.5), realised) == pytest.approx(0.5)
    assert area_under_the_curve(np.array([0.1, 0.2, 0.8, 0.9]), realised) == pytest.approx(0.0)


def test_area_under_the_curve_is_undefined_when_nothing_ever_happens() -> None:
    assert np.isnan(area_under_the_curve(np.array([0.3, 0.7]), np.array([0.0, 0.0])))


def test_the_murphy_identity_is_exact_when_forecasts_are_constant_within_bins() -> None:
    """The textbook identity holds only in that case, which is why the general
    case reports a residual instead of pretending."""
    generator = np.random.default_rng(20260908)
    predicted = generator.choice([0.05, 0.35, 0.65, 0.95], size=4000)
    realised = (generator.uniform(size=4000) < predicted).astype("float64")
    decomposition = murphy_decomposition(predicted, realised, bin_count=10)
    assert decomposition.binning_residual == pytest.approx(0.0, abs=1e-12)
    assert (
        decomposition.reliability - decomposition.resolution + decomposition.uncertainty
    ) == pytest.approx(brier_score(predicted, realised), abs=1e-12)


def test_the_binning_residual_shrinks_as_the_bins_get_finer() -> None:
    generator = np.random.default_rng(21)
    predicted = generator.uniform(size=4000)
    realised = (generator.uniform(size=4000) < predicted).astype("float64")
    coarse = murphy_decomposition(predicted, realised, bin_count=4)
    fine = murphy_decomposition(predicted, realised, bin_count=50)
    assert abs(fine.binning_residual) < abs(coarse.binning_residual)
    assert coarse.brier_score == pytest.approx(brier_score(predicted, realised))


def test_a_well_calibrated_forecaster_has_low_reliability_and_real_resolution() -> None:
    generator = np.random.default_rng(7)
    predicted = generator.uniform(0.05, 0.95, size=5000)
    realised = (generator.uniform(size=5000) < predicted).astype("float64")
    decomposition = murphy_decomposition(predicted, realised)
    assert decomposition.reliability < 0.005
    assert decomposition.resolution > 0.05


def test_forecasts_outside_the_unit_interval_are_refused() -> None:
    with pytest.raises(ScoringError, match="unit interval"):
        brier_score(np.array([1.4]), np.array([1.0]))


def test_outcomes_that_are_not_zero_or_one_are_refused() -> None:
    with pytest.raises(ScoringError, match="zero or one"):
        brier_score(np.array([0.5]), np.array([0.4]))


def test_unresolved_forecasts_are_dropped_rather_than_scored_as_zero() -> None:
    predicted = np.array([0.9, 0.1, 0.8])
    realised = np.array([1.0, np.nan, 1.0])
    assert brier_score(predicted, realised) == pytest.approx(np.mean([0.01, 0.04]))


def test_scoring_nothing_is_reported_rather_than_returning_zero() -> None:
    with pytest.raises(ScoringError, match="nothing can be scored"):
        brier_score(np.array([0.5, 0.5]), np.array([np.nan, np.nan]))


# ------------------------------------------------------------- calibration


def test_a_calibrated_forecaster_has_a_small_calibration_error() -> None:
    generator = np.random.default_rng(11)
    predicted = generator.uniform(0.05, 0.95, size=20000)
    realised = (generator.uniform(size=20000) < predicted).astype("float64")
    report = assess_calibration(predicted, realised)
    assert report.expected_calibration_error < 0.02
    assert report.is_monotone


def test_an_overconfident_forecaster_is_caught_by_the_calibration_error() -> None:
    """Forecasts pushed toward the extremes while outcomes stay moderate."""
    generator = np.random.default_rng(12)
    truth = generator.uniform(0.3, 0.7, size=20000)
    predicted = np.clip((truth - 0.5) * 3.0 + 0.5, 0.01, 0.99)
    realised = (generator.uniform(size=20000) < truth).astype("float64")
    assert assess_calibration(predicted, realised).expected_calibration_error > 0.10


def test_a_reversed_forecaster_breaks_monotonicity() -> None:
    """Higher forecasts followed by lower observed rates is an ordering failure
    that no amount of recalibration can repair."""
    generator = np.random.default_rng(13)
    truth = generator.uniform(0.05, 0.95, size=20000)
    realised = (generator.uniform(size=20000) < truth).astype("float64")
    report = assess_calibration(1.0 - truth, realised)
    assert not report.is_monotone
    assert report.monotonicity_violations > 0


def test_the_reliability_table_covers_every_populated_bin() -> None:
    generator = np.random.default_rng(14)
    predicted = generator.uniform(size=2000)
    realised = (generator.uniform(size=2000) < predicted).astype("float64")
    report = assess_calibration(predicted, realised, bin_count=10)
    assert len(report.populated_bins) == 10
    assert int(report.table()["count"].sum()) == 2000


def test_a_reliability_diagram_needs_at_least_two_bins() -> None:
    with pytest.raises(ScoringError, match="at least two bins"):
        assess_calibration(np.array([0.5]), np.array([1.0]), bin_count=1)


# --------------------------------------------------------------- bootstrap


def test_the_effective_sample_size_divides_by_the_block_length() -> None:
    """Six hundred and sixty overlapping ten-year forecasts are worth about five
    independent observations, which is the number a reader needs to see."""
    assert effective_independent_sample_size(660, 120) == pytest.approx(5.5)


def test_a_block_bootstrap_interval_brackets_the_point_estimate() -> None:
    values = np.random.default_rng(15).normal(loc=2.0, size=400)

    def mean_of(positions: np.ndarray) -> float:
        return float(values[positions].mean())

    interval = moving_block_bootstrap(
        mean_of, np.arange(400), block_length=12, resamples=500, seed=1
    )
    assert interval.lower_bound < interval.point_estimate < interval.upper_bound
    assert interval.point_estimate == pytest.approx(2.0, abs=0.2)
    assert interval.excludes_zero


def test_longer_blocks_widen_the_interval_on_dependent_data() -> None:
    """The whole point of the block bootstrap: dependence must cost width. A
    strongly autocorrelated series resampled in long blocks gives a wider
    interval than the same series resampled one point at a time."""
    generator = np.random.default_rng(16)
    series = np.zeros(600)
    for index in range(1, 600):
        series[index] = 0.97 * series[index - 1] + generator.normal(scale=0.2)

    def mean_of(positions: np.ndarray) -> float:
        return float(series[positions].mean())

    narrow = moving_block_bootstrap(mean_of, np.arange(600), 1, 800, seed=2)
    wide = moving_block_bootstrap(mean_of, np.arange(600), 120, 800, seed=2)
    assert (wide.upper_bound - wide.lower_bound) > 3.0 * (narrow.upper_bound - narrow.lower_bound)
    assert wide.effective_independent_sample_size == pytest.approx(5.0)


def test_the_same_seed_gives_the_same_interval() -> None:
    values = np.random.default_rng(17).normal(size=200)

    def mean_of(positions: np.ndarray) -> float:
        return float(values[positions].mean())

    first = moving_block_bootstrap(mean_of, np.arange(200), 12, 300, seed=3)
    second = moving_block_bootstrap(mean_of, np.arange(200), 12, 300, seed=3)
    assert first.lower_bound == second.lower_bound
    assert first.upper_bound == second.upper_bound


def test_a_block_longer_than_the_sample_is_shortened_rather_than_refused() -> None:
    values = np.arange(50, dtype="float64")

    def mean_of(positions: np.ndarray) -> float:
        return float(values[positions].mean())

    interval = moving_block_bootstrap(mean_of, np.arange(50), 200, 200, seed=4)
    assert interval.block_length == 50
    assert interval.effective_independent_sample_size == pytest.approx(1.0)


def test_bootstrapping_an_empty_sample_is_reported() -> None:
    with pytest.raises(BootstrapError, match="empty sample"):
        moving_block_bootstrap(lambda _: 0.0, np.array([]), 12, 100, seed=5)


def test_a_statistic_that_never_evaluates_is_reported_rather_than_returning_zeros() -> None:
    def always_fails(_: np.ndarray) -> float:
        raise ValueError("cannot score this resample")

    with pytest.raises(BootstrapError, match="too few for an interval"):
        moving_block_bootstrap(always_fails, np.arange(100), 12, 200, seed=6)


# ------------------------------------- calibration on overlapping forecasts


def test_the_monotonicity_check_widens_its_noise_band_for_overlapping_forecasts() -> None:
    """A bin holding four hundred monthly one-year forecasts does not hold four
    hundred independent observations. Consecutive forecasts share eleven of their
    twelve months, so the binomial standard error on the raw count is about three
    and a half times too small and every wobble looks significant."""
    generator = np.random.default_rng(31)
    truth = np.repeat(np.linspace(0.05, 0.95, 40), 60)
    predicted = np.clip(truth + generator.normal(0, 0.02, size=truth.size), 0.01, 0.99)
    realised = (generator.uniform(size=truth.size) < truth).astype("float64")

    independent = assess_calibration(predicted, realised, dependence_block_length=1)
    overlapping = assess_calibration(predicted, realised, dependence_block_length=12)

    assert overlapping.monotonicity_violations <= independent.monotonicity_violations
    for wide, narrow in zip(overlapping.populated_bins, independent.populated_bins, strict=True):
        assert wide.standard_error >= narrow.standard_error


def test_a_block_length_of_one_reproduces_the_independent_computation() -> None:
    generator = np.random.default_rng(32)
    predicted = generator.uniform(size=3000)
    realised = (generator.uniform(size=3000) < predicted).astype("float64")
    report = assess_calibration(predicted, realised, dependence_block_length=1)
    assert report.monotonicity_violations == report.naive_monotonicity_violations
    for item in report.populated_bins:
        assert item.standard_error == pytest.approx(item.naive_standard_error)


def test_the_report_says_when_the_correction_changed_the_answer() -> None:
    """The correction must be visible in the output, not buried in a constant."""
    generator = np.random.default_rng(33)
    truth = np.repeat(np.linspace(0.1, 0.9, 20), 50)
    predicted = np.clip(truth, 0.01, 0.99)
    realised = (generator.uniform(size=truth.size) < truth).astype("float64")
    report = assess_calibration(predicted, realised, dependence_block_length=60)
    assert "independent observations" in report.describe()


def test_a_bin_smaller_than_the_block_is_still_worth_one_observation() -> None:
    """Not a fraction of one: a bin with ten forecasts inside a sixty month block
    still contains a piece of evidence."""
    generator = np.random.default_rng(34)
    predicted = np.concatenate([np.full(10, 0.95), generator.uniform(0.0, 0.5, size=500)])
    realised = (generator.uniform(size=510) < predicted).astype("float64")
    report = assess_calibration(predicted, realised, dependence_block_length=120)
    smallest = min(report.populated_bins, key=lambda item: item.count)
    assert smallest.effective_count == 1.0


def test_a_genuinely_reversed_forecaster_is_still_caught_despite_the_wider_band() -> None:
    """The correction must not disarm the check. A forecaster whose ordering is
    backwards fails it at any block length."""
    generator = np.random.default_rng(35)
    truth = generator.uniform(0.05, 0.95, size=20000)
    realised = (generator.uniform(size=20000) < truth).astype("float64")
    report = assess_calibration(1.0 - truth, realised, dependence_block_length=12)
    assert not report.is_monotone
