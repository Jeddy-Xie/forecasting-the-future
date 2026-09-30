"""Skill at every horizon from one month to ten years, and where it runs out.

The pre-registered verdict scores three horizons: one, five and ten years. Those
three points say the model is worth shipping at one year and not at five, but not
where between them it stops, nor how it decays. This module scores every month.

Each forecaster is scored exactly as the verdict scores the model: the mean Brier
skill score against the climatology over the indicators whose skill is defined on
the full sample, with a moving-block bootstrap interval over forecast dates. The
statistic is the verdict's own, imported rather than restated, so at 12, 60 and
120 months the curve reproduces the verdict's point estimates to the digit.

**The block length is the horizon, but never less than twelve months.** The
pre-registration asks for blocks at least as long as the horizon, which is what
decorrelates overlapping windows. Below a year that rule alone would allow
one-month blocks, and forecasts a month apart are not independent at a one-month
horizon either: the regime and the indicator's own condition are both persistent,
and the loss differential was measured to decorrelate only within about a year.
Twelve months is therefore a floor, fixed before the curve was computed.

**Carrying skill** at a horizon means what the verdict's skill gate means: mean
skill above +0.02 and the 90% interval's lower bound above zero. The
**ship-the-average horizon** is the first horizon after which the model fails that
test at every longer horizon: the last horizon at which it carries skill. Beyond
it the historical average is as good as the model, as far as this sample can say.
A horizon whose effective sample -- resolved dates over the block length -- is
below 5.5 is **uninformative**, and no crossing is read there.

Plain arrays and frames in, plain numbers out, as the layer table requires.
"""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from economic_regime_forecasting.evaluation import paired_skill_comparison as paired
from economic_regime_forecasting.evaluation.paired_skill_comparison import ForecastMatrices
from economic_regime_forecasting.evaluation.verdict import _mean_skill_over, _scoreable_columns

LONGEST_HORIZON_IN_MONTHS = 120
"""Ten years, the longest horizon the project forecasts."""

MINIMUM_BLOCK_LENGTH_IN_MONTHS = 12
"""The floor on the bootstrap block, for the reason in the module docstring."""

MINIMUM_MEAN_SKILL = 0.02
"""The verdict's skill bar, read here as a description, never as a new threshold."""

CONFIDENCE_LEVEL = 0.90

MINIMUM_INFORMATIVE_INDEPENDENT_OBSERVATIONS = 5.5
"""Below this many effective independent observations a horizon is labelled
uninformative: the five-year horizon's own count, the least any verdict reads."""

FORECASTER_COLUMNS: dict[str, str] = {
    "regime model": "predicted_probability",
    "condition chain": "condition_chain_probability",
}
"""Each forecaster the curve scores, and the results column holding its forecasts."""

BENCHMARK_COLUMNS: dict[str, str] = {
    "series-start": "climatology_probability",
    "model-sample": "model_sample_climatology_probability",
}
"""Each climatology the curve scores against: 0001's, and rule 0007's."""


class SkillByHorizonError(ValueError):
    """The curve could not be computed from the forecasts given."""


@dataclass(frozen=True)
class HorizonSkill:
    """One forecaster's skill at one horizon, with its interval."""

    horizon_in_months: int
    forecaster: str
    mean_skill: float
    lower_bound: float
    upper_bound: float
    pooled_skill: float
    """One minus total Brier over total climatology Brier, across every scored
    forecast. Reported beside the mean of ratios, which near-certain indicators
    dominate at long horizons."""
    block_length: int
    dates: int
    scoreable_indicators: int
    benchmark: str = "series-start"

    @property
    def carries_skill(self) -> bool:
        return self.mean_skill > MINIMUM_MEAN_SKILL and self.lower_bound > 0.0

    @property
    def effective_independent_observations(self) -> float:
        return self.dates / self.block_length

    @property
    def informative(self) -> bool:
        return (
            self.effective_independent_observations >= MINIMUM_INFORMATIVE_INDEPENDENT_OBSERVATIONS
        )

    def as_row(self) -> dict[str, object]:
        return {
            **asdict(self),
            "carries_skill": self.carries_skill,
            "effective_independent_observations": self.effective_independent_observations,
            "informative": self.informative,
        }


@dataclass(frozen=True)
class HorizonDifference:
    """The regime model's skill minus the reference chain's, paired on dates."""

    horizon_in_months: int
    difference: float
    lower_bound: float
    upper_bound: float
    block_length: int
    benchmark: str = "series-start"

    def as_row(self) -> dict[str, object]:
        return asdict(self)


def block_length_for(horizon_in_months: int) -> int:
    return max(horizon_in_months, MINIMUM_BLOCK_LENGTH_IN_MONTHS)


def matrices_at(
    results: pd.DataFrame, horizon_in_months: int, forecast_column: str, climatology_column: str
) -> ForecastMatrices:
    """Date-by-indicator matrices at one horizon, laid out as the verdict lays them out."""
    at_horizon = results[results["horizon_months"] == horizon_in_months]
    scored = at_horizon.dropna(subset=["realised_outcome", climatology_column])
    if scored.empty:
        raise SkillByHorizonError(
            f"no forecast at {horizon_in_months} months has both a resolved outcome and a "
            "benchmark; the sample does not reach that far"
        )

    def wide(column: str) -> np.ndarray:
        return (
            scored.pivot(index="forecast_date", columns="indicator", values=column)
            .sort_index()
            .sort_index(axis=1)
            .to_numpy(dtype="float64")
        )

    return ForecastMatrices(
        predicted=wide(forecast_column),
        realised=wide("realised_outcome"),
        climatology=wide(climatology_column),
    )


def _pooled_skill(matrices: ForecastMatrices) -> float:
    usable = np.isfinite(matrices.realised) & np.isfinite(matrices.climatology)
    forecast_error = np.sum((matrices.predicted[usable] - matrices.realised[usable]) ** 2)
    benchmark_error = np.sum((matrices.climatology[usable] - matrices.realised[usable]) ** 2)
    return float(1.0 - forecast_error / benchmark_error) if benchmark_error > 0 else float("nan")


def score_forecaster(
    matrices: ForecastMatrices,
    horizon_in_months: int,
    forecaster: str,
    *,
    resamples: int,
    seed: int,
    benchmark: str = "series-start",
) -> HorizonSkill:
    """One forecaster's mean skill and interval at one horizon."""
    columns = _scoreable_columns(matrices.predicted, matrices.realised, matrices.climatology)
    if not columns:
        raise SkillByHorizonError(
            f"no indicator's skill is defined at {horizon_in_months} months; the benchmark has "
            "no error to improve on"
        )

    def statistic(positions: np.ndarray) -> float:
        return _mean_skill_over(
            positions,
            matrices.predicted,
            matrices.realised,
            matrices.climatology,
            columns,
            require_every_indicator=True,
        )[0]

    positions = np.arange(matrices.shape[0])
    block_length = block_length_for(horizon_in_months)
    (interval,) = paired.intervals_from_one_set_of_resamples(
        statistic,
        positions,
        block_length=block_length,
        resamples=resamples,
        seed=seed,
        confidence_levels=(CONFIDENCE_LEVEL,),
    )
    return HorizonSkill(
        horizon_in_months=horizon_in_months,
        forecaster=forecaster,
        mean_skill=statistic(positions),
        lower_bound=interval.lower_bound,
        upper_bound=interval.upper_bound,
        pooled_skill=_pooled_skill(matrices),
        block_length=block_length,
        dates=int(matrices.shape[0]),
        scoreable_indicators=len(columns),
        benchmark=benchmark,
    )


def paired_difference(
    reference: ForecastMatrices,
    model: ForecastMatrices,
    horizon_in_months: int,
    *,
    resamples: int,
    seed: int,
    benchmark: str = "series-start",
) -> HorizonDifference:
    """Model minus reference on identical resamples of dates."""
    block_length = block_length_for(horizon_in_months)
    result = paired.paired_mean_skill_difference(
        reference,
        model,
        block_length=block_length,
        resamples=resamples,
        seed=seed,
        confidence_levels=(CONFIDENCE_LEVEL,),
    )
    if result.interval is None:
        raise SkillByHorizonError(
            f"the paired interval at {horizon_in_months} months could not be computed: "
            f"{result.interval_note}"
        )
    return HorizonDifference(
        horizon_in_months=horizon_in_months,
        difference=result.difference,
        lower_bound=result.interval.lower_bound,
        upper_bound=result.interval.upper_bound,
        block_length=block_length,
        benchmark=benchmark,
    )


def ship_the_average_horizon(skills: Sequence[HorizonSkill]) -> int:
    """The first horizon after which the forecaster fails the skill test at every
    longer horizon: the last horizon at which it carries skill, or 0 if none.

    This is the reading measurement 0010 registered. Whether that horizon falls
    where the sample can still say anything is a separate question, answered by
    ``informative`` on the row itself.
    """
    carrying = [skill.horizon_in_months for skill in skills if skill.carries_skill]
    return max(carrying, default=0)


def skill_unbroken_from_one_month(skills: Sequence[HorizonSkill]) -> int:
    """The longest horizon up to which the forecaster carries skill at every
    horizon from one month on. Secondary to ``ship_the_average_horizon``."""
    reached = 0
    for skill in sorted(skills, key=lambda item: item.horizon_in_months):
        if skill.horizon_in_months != reached + 1 or not skill.carries_skill:
            break
        reached = skill.horizon_in_months
    return reached


def last_horizon_with_positive_skill(skills: Sequence[HorizonSkill]) -> int:
    """The longest horizon up to which the point estimate stays above zero throughout."""
    reached = 0
    for skill in sorted(skills, key=lambda item: item.horizon_in_months):
        if skill.horizon_in_months != reached + 1 or not skill.mean_skill > 0.0:
            break
        reached = skill.horizon_in_months
    return reached


def mean_distance_to_stationary_by_horizon(results: pd.DataFrame) -> dict[int, float]:
    """The honesty gate's measure at every horizon: how far the projection still is
    from the model's long-run distribution, averaged over forecast dates."""
    first_indicator = results["indicator"].iloc[0]
    one_indicator = results[results["indicator"] == first_indicator]
    means = one_indicator.groupby("horizon_months")["distance_to_stationary"].mean()
    return {
        int(horizon): float(distance)
        for horizon, distance in zip(means.index.to_numpy(), means.to_numpy(), strict=True)
    }


def _score_one_horizon(
    task: tuple[pd.DataFrame, int, int, int],
) -> tuple[list[HorizonSkill], list[HorizonDifference]]:
    """Every forecaster against every benchmark at one horizon, plus the paired
    differences. Each horizon's resamples depend only on the seed, so the order in
    which horizons are scored, and how many run at once, changes no number."""
    at_horizon, horizon, resamples, seed = task
    skills: list[HorizonSkill] = []
    differences: list[HorizonDifference] = []
    for benchmark, benchmark_column in BENCHMARK_COLUMNS.items():
        if benchmark_column not in at_horizon.columns:
            continue
        by_forecaster = {
            forecaster: matrices_at(at_horizon, horizon, column, benchmark_column)
            for forecaster, column in FORECASTER_COLUMNS.items()
            if column in at_horizon.columns
        }
        for forecaster, matrices in by_forecaster.items():
            skills.append(
                score_forecaster(
                    matrices,
                    horizon,
                    forecaster,
                    resamples=resamples,
                    seed=seed,
                    benchmark=benchmark,
                )
            )
        if len(by_forecaster) == len(FORECASTER_COLUMNS):
            differences.append(
                paired_difference(
                    by_forecaster["condition chain"],
                    by_forecaster["regime model"],
                    horizon,
                    resamples=resamples,
                    seed=seed,
                    benchmark=benchmark,
                )
            )
    return skills, differences


@dataclass(frozen=True)
class SkillCurve:
    """Measurement 0010's whole output: every forecaster, benchmark and horizon."""

    skills: tuple[HorizonSkill, ...]
    differences: tuple[HorizonDifference, ...]
    distance_to_stationary: dict[int, float]

    def skill_table(self) -> pd.DataFrame:
        table = pd.DataFrame([skill.as_row() for skill in self.skills])
        table["mean_distance_to_stationary"] = table["horizon_in_months"].map(
            self.distance_to_stationary
        )
        return table

    def difference_table(self) -> pd.DataFrame:
        return pd.DataFrame([difference.as_row() for difference in self.differences])

    def _of(self, forecaster: str, benchmark: str) -> list[HorizonSkill]:
        return [
            skill
            for skill in self.skills
            if skill.forecaster == forecaster and skill.benchmark == benchmark
        ]

    def readings(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for benchmark in BENCHMARK_COLUMNS:
            for forecaster in FORECASTER_COLUMNS:
                skills = self._of(forecaster, benchmark)
                if not skills:
                    continue
                crossing = ship_the_average_horizon(skills)
                at_crossing = next(
                    (skill for skill in skills if skill.horizon_in_months == crossing), None
                )
                rows.append(
                    {
                        "forecaster": forecaster,
                        "benchmark": benchmark,
                        "ship_the_average_horizon": crossing,
                        "crossing_is_informative": bool(
                            at_crossing is not None and at_crossing.informative
                        ),
                        "skill_unbroken_from_one_month_to": skill_unbroken_from_one_month(skills),
                        "last_informative_horizon": max(
                            (skill.horizon_in_months for skill in skills if skill.informative),
                            default=0,
                        ),
                    }
                )
        return rows

    def honesty_crossing(self, threshold: float = 0.05) -> int | None:
        """The first horizon at which the projection is within ``threshold`` of the
        stationary distribution, in total variation."""
        below = [
            horizon
            for horizon, distance in self.distance_to_stationary.items()
            if distance <= threshold
        ]
        return min(below) if below else None

    def summary(self, configuration_hash: str) -> dict[str, Any]:
        return {
            "measurement": "0010-skill-at-every-horizon",
            "configuration_hash": configuration_hash,
            "horizons": [min(self.distance_to_stationary), max(self.distance_to_stationary)],
            "carries_skill_means": (
                f"mean skill above {MINIMUM_MEAN_SKILL} and the {CONFIDENCE_LEVEL:.0%} lower "
                "bound above zero"
            ),
            "block_length": f"max(horizon, {MINIMUM_BLOCK_LENGTH_IN_MONTHS}) months",
            "uninformative_below_independent_observations": (
                MINIMUM_INFORMATIVE_INDEPENDENT_OBSERVATIONS
            ),
            "readings": self.readings(),
            "honesty_distance_first_at_or_below_0_05": self.honesty_crossing(),
        }

    def describe(self, every: int = 6) -> str:
        lines = ["skill at every horizon (mean Brier skill, 90% interval; * carries skill)"]
        for benchmark in BENCHMARK_COLUMNS:
            model = {
                skill.horizon_in_months: skill for skill in self._of("regime model", benchmark)
            }
            chain = {
                skill.horizon_in_months: skill for skill in self._of("condition chain", benchmark)
            }
            if not model:
                continue
            lines.append("")
            lines.append(f"against the {benchmark} climatology")
            lines.append(
                f"{'months':>6}  {'regime model':>28}  {'condition chain':>28}  informative"
            )
            for horizon in sorted(model):
                if horizon not in (1, 3) and horizon % every:
                    continue

                def cell(skill: HorizonSkill | None) -> str:
                    if skill is None:
                        return f"{'n/a':>28}"
                    mark = "*" if skill.carries_skill else " "
                    return (
                        f"{skill.mean_skill:+.3f} [{skill.lower_bound:+.3f}, "
                        f"{skill.upper_bound:+.3f}]{mark}".rjust(28)
                    )

                lines.append(
                    f"{horizon:>6}  {cell(model[horizon])}  {cell(chain.get(horizon))}  "
                    f"{'yes' if model[horizon].informative else 'no'}"
                )
        lines.append("")
        for reading in self.readings():
            lines.append(
                f"{reading['forecaster']} against the {reading['benchmark']} climatology: "
                f"ship the average after {reading['ship_the_average_horizon']} months"
                f"{'' if reading['crossing_is_informative'] else ' (in the uninformative range)'}"
                f"; unbroken from one month to {reading['skill_unbroken_from_one_month_to']}"
            )
        crossing = self.honesty_crossing()
        lines.append(
            f"the projection is within 0.05 of the stationary distribution from {crossing} months"
            if crossing
            else "the projection never comes within 0.05"
        )
        return "\n".join(lines)


def measure(
    results: pd.DataFrame,
    horizons: Sequence[int],
    *,
    resamples: int,
    seed: int,
    workers: int = 8,
) -> SkillCurve:
    """Score every horizon, in parallel, and assemble the curve in horizon order."""
    tasks = [
        (results[results["horizon_months"] == horizon], horizon, resamples, seed)
        for horizon in horizons
    ]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            scored = list(pool.map(_score_one_horizon, tasks))
    else:
        scored = [_score_one_horizon(task) for task in tasks]
    skills = tuple(skill for batch, _ in scored for skill in batch)
    differences = tuple(difference for _, batch in scored for difference in batch)
    distances = mean_distance_to_stationary_by_horizon(results)
    return SkillCurve(
        skills=skills,
        differences=differences,
        distance_to_stationary=distances,
    )
