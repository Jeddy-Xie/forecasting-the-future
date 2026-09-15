"""How far one run's skill is from another's, measured on the same forecasts.

Two runs' headline skill scores, each with its own bootstrap interval, cannot say
whether one run is better than the other. The intervals are wide -- the ten-year
horizon rests on about two independent observations -- and they overlap for almost
any change worth making, so a real improvement and a lucky one look the same.

Most of that width is shared. Both runs forecast the same indicators on the same
dates against the same outcomes, so a stretch of history that is hard for one run
is hard for the other. Differencing the two on each resample cancels the shared
part and leaves the part that belongs to the change. That only works if both runs
are scored on *identical* resamples, which is the whole design here: one
statistic, handed one set of resampled dates, returns the difference.

The skill statistic is the pre-registered verdict's own, imported rather than
restated so the two can never compute different things: the mean Brier skill
score over the indicators whose skill is defined on the full sample, with every
resample required to score that same fixed set (ADR 0007). Each run's point
estimate here is therefore exactly the number its own verdict reports whenever the
two runs cover the same forecasts.

Plain arrays in and plain numbers out, as the layer table requires of
``evaluation``. Lining two runs' forecasts up by indicator, date and horizon is
the caller's job.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from economic_regime_forecasting.evaluation import bootstrap as bootstrap_module
from economic_regime_forecasting.evaluation import scoring
from economic_regime_forecasting.evaluation.verdict import (
    _mean_skill_over,
    _scoreable_columns,
)


class PairedComparisonError(ValueError):
    """Two runs' forecasts could not be scored against each other as given."""


@dataclass(frozen=True)
class ForecastMatrices:
    """One run's forecasts at one horizon, shaped for the verdict's statistic.

    Rows are forecast dates in time order and columns are indicators. A forecast
    one run does not have is ``NaN`` in all three matrices at that cell. The date
    axis is what the bootstrap resamples, so every indicator forecast on a date
    travels with it.
    """

    predicted: np.ndarray
    realised: np.ndarray
    climatology: np.ndarray

    def __post_init__(self) -> None:
        shapes = {self.predicted.shape, self.realised.shape, self.climatology.shape}
        if len(shapes) != 1 or self.predicted.ndim != 2:
            raise PairedComparisonError(
                f"predicted, realised and climatology must be one date-by-indicator shape, "
                f"got {sorted(shapes)}"
            )

    @property
    def shape(self) -> tuple[int, int]:
        rows, columns = self.predicted.shape
        return int(rows), int(columns)


@dataclass(frozen=True)
class PairedSkillDifference:
    """Mean skill on each side, their difference, and paired intervals on it.

    ``intervals`` holds one interval per confidence level asked for, in ascending
    order of level, every one read off the same resamples. Empty when no interval
    could be formed, and ``interval_note`` then says why.
    """

    baseline_mean_skill: float
    current_mean_skill: float
    difference: float
    intervals: tuple[bootstrap_module.BootstrapInterval, ...]
    interval_note: str
    baseline_scoreable_columns: tuple[int, ...]
    current_scoreable_columns: tuple[int, ...]

    @property
    def interval(self) -> bootstrap_module.BootstrapInterval | None:
        """The interval at the lowest confidence level asked for."""
        return self.intervals[0] if self.intervals else None


def confidence_levels_in_order(levels: Sequence[float]) -> tuple[float, ...]:
    """Ascending and without repeats, or a refusal naming the level at fault."""
    if not levels:
        raise PairedComparisonError("at least one confidence level is needed for an interval")
    for level in levels:
        if not 0.0 < float(level) < 1.0:
            raise PairedComparisonError(
                f"{level} is not a confidence level: it must lie strictly between 0 and 1, "
                "such as 0.90"
            )
    return tuple(sorted({float(level) for level in levels}))


def intervals_from_one_set_of_resamples(
    statistic: Callable[[np.ndarray], float],
    sample_indices: np.ndarray,
    *,
    block_length: int,
    resamples: int,
    seed: int,
    confidence_levels: Sequence[float],
) -> tuple[bootstrap_module.BootstrapInterval, ...]:
    """One moving-block interval per level, every one read off the same resamples.

    ``moving_block_bootstrap`` returns one level. Its draw of dates depends only on
    the seed, the sample and the block length, so asking it once per level with
    the same seed draws the same dates every time, and the intervals cannot
    disagree for want of it. The statistic is memoised on the drawn dates, so each
    resample is scored once however many levels are asked for. A higher level's
    interval therefore always contains a lower one's: they are two percentiles of
    one set of numbers.
    """
    scored: dict[bytes, float] = {}
    unscoreable: set[bytes] = set()

    def memoised(drawn: np.ndarray) -> float:
        key = hashlib.blake2b(np.ascontiguousarray(drawn).tobytes(), digest_size=16).digest()
        if key in unscoreable:
            raise ValueError("this resample could not be scored the first time either")
        if key not in scored:
            try:
                scored[key] = statistic(drawn)
            except (ValueError, ZeroDivisionError):
                unscoreable.add(key)
                raise
        return scored[key]

    return tuple(
        bootstrap_module.moving_block_bootstrap(
            memoised,
            sample_indices,
            block_length=block_length,
            resamples=resamples,
            seed=seed,
            confidence_level=level,
        )
        for level in confidence_levels_in_order(confidence_levels)
    )


def _mean_skill(matrices: ForecastMatrices, columns: Sequence[int], positions: np.ndarray) -> float:
    return _mean_skill_over(
        positions,
        matrices.predicted,
        matrices.realised,
        matrices.climatology,
        columns,
        require_every_indicator=True,
    )[0]


def paired_mean_skill_difference(
    baseline: ForecastMatrices,
    current: ForecastMatrices,
    *,
    block_length: int,
    resamples: int,
    seed: int,
    confidence_levels: Sequence[float],
) -> PairedSkillDifference:
    """This run's mean skill minus the baseline's, with moving-block intervals.

    Each side keeps the indicator set its own verdict would score, decided once on
    the full sample. That is what makes each point estimate equal its own
    verdict's; the two sets are returned so a caller can say out loud when they
    differ.

    One ``statistic`` computes both sides from the same ``positions``, so every
    resample is a single draw of forecast dates applied to both runs. A resample
    either side cannot score is skipped for both, which keeps the pairing intact.
    Every confidence level's interval is read off that one set of resamples.
    """
    levels = confidence_levels_in_order(confidence_levels)
    if baseline.shape != current.shape:
        raise PairedComparisonError(
            f"the baseline's forecasts are {baseline.shape} and this run's are "
            f"{current.shape}; a paired comparison needs them on one grid of dates and "
            "indicators"
        )
    date_count = baseline.shape[0]
    if date_count == 0:
        raise PairedComparisonError("there is no forecast date both runs resolved")

    baseline_columns = _scoreable_columns(
        baseline.predicted, baseline.realised, baseline.climatology
    )
    current_columns = _scoreable_columns(current.predicted, current.realised, current.climatology)
    if not baseline_columns or not current_columns:
        raise PairedComparisonError(
            "no indicator has a defined skill score on the shared forecasts, on at least one "
            "side; the benchmark has no error to improve on"
        )

    def statistic(positions: np.ndarray) -> float:
        return _mean_skill(current, current_columns, positions) - _mean_skill(
            baseline, baseline_columns, positions
        )

    all_positions = np.arange(date_count)
    baseline_mean = _mean_skill(baseline, baseline_columns, all_positions)
    current_mean = _mean_skill(current, current_columns, all_positions)

    intervals: tuple[bootstrap_module.BootstrapInterval, ...]
    try:
        intervals = intervals_from_one_set_of_resamples(
            statistic,
            all_positions,
            block_length=block_length,
            resamples=resamples,
            seed=seed,
            confidence_levels=levels,
        )
    except bootstrap_module.BootstrapError as error:
        intervals = ()
        interval_note = f"interval unavailable: {error}"
    else:
        interval_note = ""

    return PairedSkillDifference(
        baseline_mean_skill=baseline_mean,
        current_mean_skill=current_mean,
        difference=current_mean - baseline_mean,
        intervals=intervals,
        interval_note=interval_note,
        baseline_scoreable_columns=tuple(baseline_columns),
        current_scoreable_columns=tuple(current_columns),
    )


def indicator_skill(matrices: ForecastMatrices, column: int) -> float | None:
    """One indicator's Brier skill score, computed as the metric table computes it.

    ``None`` where the score is undefined -- no resolved forecast, or a benchmark
    with no error to remove -- which is where the metric table writes ``NaN``.
    """
    usable = np.isfinite(matrices.realised[:, column]) & np.isfinite(
        matrices.climatology[:, column]
    )
    if not usable.any():
        return None
    try:
        return scoring.brier_skill_score(
            matrices.predicted[usable, column],
            matrices.realised[usable, column],
            matrices.climatology[usable, column],
        )
    except scoring.ScoringError:
        return None
