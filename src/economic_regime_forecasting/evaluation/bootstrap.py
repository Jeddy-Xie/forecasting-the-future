"""Confidence intervals for statistics computed on overlapping forecasts.

Monthly forecasts at a ten-year horizon overlap by a hundred and nineteen months.
Consecutive errors are therefore almost the same number, and an ordinary bootstrap
that resamples them independently treats each one as fresh evidence. It produces
intervals that are far too narrow -- on this data, narrow enough to declare skill
that is not there.

The moving-block bootstrap resamples contiguous blocks instead, preserving the
dependence inside each block. With a block at least as long as the horizon, two
different blocks share no underlying window, so the resample respects roughly the
same amount of independent information the original sample contained.

Alongside every interval this module reports the effective independent sample
size, which is the sample length divided by the block length. For a ten-year
horizon on fifty-five years of monthly forecasts that number is about five. Five
is a small number, and a reader who sees it will read the interval correctly.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np


class BootstrapError(ValueError):
    """The resample could not be constructed as asked."""


@dataclass(frozen=True)
class BootstrapInterval:
    """A statistic with a percentile interval and an honest sample size."""

    point_estimate: float
    lower_bound: float
    upper_bound: float
    confidence_level: float
    block_length: int
    sample_size: int
    effective_independent_sample_size: float
    resamples: int

    @property
    def excludes_zero(self) -> bool:
        """Whether the interval lies entirely on one side of zero.

        The skill gate asks exactly this: is the interval consistent only with
        the model beating the base rate?
        """
        return self.lower_bound > 0.0 or self.upper_bound < 0.0

    def describe(self) -> str:
        return (
            f"{self.point_estimate:+.4f} "
            f"[{self.lower_bound:+.4f}, {self.upper_bound:+.4f}] at "
            f"{self.confidence_level:.0%}, blocks of {self.block_length} months, "
            f"about {self.effective_independent_sample_size:.1f} independent observations"
        )

    def as_row(self) -> dict[str, object]:
        return {
            "point_estimate": self.point_estimate,
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "confidence_level": self.confidence_level,
            "block_length": self.block_length,
            "sample_size": self.sample_size,
            "effective_independent_sample_size": self.effective_independent_sample_size,
            "excludes_zero": self.excludes_zero,
        }


def effective_independent_sample_size(sample_size: int, block_length: int) -> float:
    """How many genuinely independent observations a dependent sample is worth."""
    if block_length < 1:
        raise BootstrapError(f"block length must be at least one, got {block_length}")
    return float(sample_size) / float(block_length)


def moving_block_bootstrap(
    statistic: Callable[[np.ndarray], float],
    sample_indices: np.ndarray,
    block_length: int,
    resamples: int,
    seed: int,
    confidence_level: float = 0.90,
) -> BootstrapInterval:
    """Percentile interval for a statistic of a time-ordered sample.

    ``statistic`` is handed an array of positions into the original sample and
    returns a number. Passing positions rather than values lets the caller keep
    forecasts, outcomes and benchmarks aligned without this module knowing
    anything about them.

    Resamples that the statistic cannot evaluate -- a block containing only one
    class, say -- are skipped rather than counted as zero, and the interval
    reports how many contributed.
    """
    positions = np.asarray(sample_indices)
    sample_size = int(positions.size)
    if sample_size == 0:
        raise BootstrapError("cannot bootstrap an empty sample")
    if block_length < 1:
        raise BootstrapError(f"block length must be at least one, got {block_length}")
    if not 0.0 < confidence_level < 1.0:
        raise BootstrapError(
            f"confidence level must be between zero and one, got {confidence_level}"
        )

    usable_block_length = min(block_length, sample_size)
    blocks_needed = int(np.ceil(sample_size / usable_block_length))
    last_start = sample_size - usable_block_length
    generator = np.random.default_rng(seed)

    estimates: list[float] = []
    for _ in range(resamples):
        starts = generator.integers(0, last_start + 1, size=blocks_needed)
        drawn = np.concatenate(
            [positions[start : start + usable_block_length] for start in starts]
        )[:sample_size]
        try:
            value = statistic(drawn)
        except (ValueError, ZeroDivisionError):
            continue
        if np.isfinite(value):
            estimates.append(float(value))

    if len(estimates) < max(20, resamples // 100):
        raise BootstrapError(
            f"only {len(estimates)} of {resamples} resamples could be scored, too few for an "
            "interval. This usually means the outcome barely varies in the sample."
        )

    tail = (1.0 - confidence_level) / 2.0
    values = np.array(estimates)
    return BootstrapInterval(
        point_estimate=float(statistic(positions)),
        lower_bound=float(np.quantile(values, tail)),
        upper_bound=float(np.quantile(values, 1.0 - tail)),
        confidence_level=confidence_level,
        block_length=usable_block_length,
        sample_size=sample_size,
        effective_independent_sample_size=effective_independent_sample_size(
            sample_size, usable_block_length
        ),
        resamples=len(estimates),
    )
