"""Re-run the whole method through history, one month at a time.

At each forecast date the engine rebuilds the world as it stood then: the panel
an observer would have had, a model fitted only on that panel, per-regime rates
estimated only from conditions already observable, and a climatological benchmark
computed only from outcomes already resolved. It then issues forecasts at one,
five and ten years and moves on.

Three things about the design are worth reading before the code.

**Refitting is annual, not monthly.** A transition matrix estimated on four
hundred months barely moves when one more arrives, and refitting every month
across fifty-five years would multiply the cost by twelve for a difference in the
fourth decimal. Between refits the parameters are held fixed and only the filtered
state distribution advances, which is exactly what a forecaster running this live
on an annual model review would do. The cadence is a setting and is recorded in
the manifest.

**Only the filtered distribution advances.** Not the smoothed one. This is the
line between a backtest and a recollection, and it is enforced by the model's
interface rather than by discipline.

**The benchmark expands with the data.** Comparing a model against the base rate
computed over the whole sample would hand the model a benchmark that knew the
future. The climatology here at month t averages only the outcomes that had
resolved by month t, which is what a forecaster in month t could actually have
quoted.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from economic_regime_forecasting.configuration.registry import (
    BinaryIndicator,
    EconomicSeriesRegistry,
)
from economic_regime_forecasting.configuration.run_settings import RunSettings
from economic_regime_forecasting.data import indicator_outcomes
from economic_regime_forecasting.data.cache import ArtifactStore, SeriesCache
from economic_regime_forecasting.data.panel import assemble_point_in_time_panel, load_final_series
from economic_regime_forecasting.features.observation_matrix import build_observation_matrix
from economic_regime_forecasting.models import gaussian_hidden_markov_model as hidden_markov
from economic_regime_forecasting.models import indicator_forecast
from economic_regime_forecasting.models.gaussian_hidden_markov_model import (
    GaussianHiddenMarkovModel,
)
from economic_regime_forecasting.models.indicator_forecast import ConditionalRates
from economic_regime_forecasting.models.state_labelling import canonicalise

logger = logging.getLogger(__name__)

RESULT_COLUMNS: tuple[str, ...] = (
    "indicator",
    "forecast_date",
    "horizon_months",
    "predicted_probability",
    "climatology_probability",
    "realised_outcome",
    "composition",
    "effective_sample_size",
    "distance_to_stationary",
    "regime_distribution",
    "state_count",
    "refit_date",
    "configuration_hash",
    "seed",
)


class BacktestError(RuntimeError):
    """The walk-forward run could not be completed."""


@dataclass(frozen=True)
class FittedRegimeModel:
    """A model fitted at one refit date, with the rates learned alongside it."""

    refit_date: date
    model: GaussianHiddenMarkovModel
    rates_by_indicator: dict[str, ConditionalRates]
    months_fitted_on: int


@dataclass(frozen=True)
class IndicatorHistory:
    """Everything about one indicator that history can tell us.

    ``monthly_condition`` is whether the condition held in each month, which the
    forecaster learns per-regime rates from. ``outcomes_by_horizon`` is what
    actually happened over each horizon, which is used to score forecasts after
    the fact and never as an input to one.
    """

    indicator: BinaryIndicator
    monthly_condition: pd.Series
    outcomes_by_horizon: dict[int, pd.Series]
    climatology_by_horizon: dict[int, pd.Series]
    publication_lag_days: int


def prepare_indicator_history(
    indicators: Sequence[BinaryIndicator],
    registry: EconomicSeriesRegistry,
    cache: SeriesCache,
    horizons_in_months: Sequence[int],
) -> dict[str, IndicatorHistory]:
    """Resolve outcomes, monthly conditions and the expanding climatology.

    Conditions and outcomes are read from final-revision data. For outcomes that
    is correct: what happened is what happened, and the forecaster never saw it.
    For conditions it is a stated approximation, since a forecaster in 1975 saw
    the 1975 vintage. It is defensible because the series involved are barely
    revised -- the funds rate, the ten-year yield and the bill rate not at all,
    the unemployment rate only through seasonal factors, and recession dates are
    settled decades later -- and because the timing is still enforced: a condition
    is only used once its publication lag has passed. The one series where
    revisions are material, industrial production, is measured in the data audit
    so the size of the approximation is on the record rather than assumed away.
    """
    source_names = indicator_outcomes.required_series_names(indicators)
    final_series = load_final_series(registry, cache, source_names)

    histories: dict[str, IndicatorHistory] = {}
    for indicator in indicators:
        source = final_series[indicator.resolution.series]
        outcomes: dict[int, pd.Series] = {}
        climatology: dict[int, pd.Series] = {}
        for horizon in horizons_in_months:
            resolved = indicator_outcomes.resolve(indicator, source, horizon).outcomes
            outcomes[horizon] = resolved
            climatology[horizon] = _expanding_climatology(resolved, horizon)

        derived = registry.derived_by_name(indicator.resolution.series)
        lag = (
            max(
                registry[derived.minuend].publication_lag_days,
                registry[derived.subtrahend].publication_lag_days,
            )
            if derived is not None
            else registry[indicator.resolution.series].publication_lag_days
        )

        histories[indicator.name] = IndicatorHistory(
            indicator=indicator,
            monthly_condition=indicator_outcomes.monthly_condition(indicator, source),
            outcomes_by_horizon=outcomes,
            climatology_by_horizon=climatology,
            publication_lag_days=lag,
        )
    return histories


def _expanding_climatology(outcomes: pd.Series, horizon_in_months: int) -> pd.Series:
    """The base rate a forecaster could have quoted at each date.

    An outcome for a forecast made in month s is known in month s plus the
    horizon. So the average available in month t covers forecast dates up to t
    minus the horizon, and no further.
    """
    running_mean = outcomes.expanding(min_periods=1).mean()
    available = running_mean.shift(horizon_in_months)
    return available.rename("climatology")


def _condition_available_at(history: IndicatorHistory, as_of: date) -> pd.Series:
    """The indicator's monthly condition, censored to what had been published."""
    condition = history.monthly_condition.dropna()
    publication_dates = condition.index + pd.Timedelta(days=history.publication_lag_days)
    return condition[publication_dates <= pd.Timestamp(as_of)]


def fit_regime_model(
    as_of: date,
    registry: EconomicSeriesRegistry,
    cache: SeriesCache,
    histories: dict[str, IndicatorHistory],
    settings: RunSettings,
    state_count: int,
    artifacts: ArtifactStore | None = None,
) -> FittedRegimeModel:
    """Fit at one refit date and learn the per-regime rates that go with it.

    Fitted models are cached to disk under a key covering the date, the number of
    states, the seed and the configuration, so a re-run costs a file read.
    """
    matrix = build_observation_matrix(
        assemble_point_in_time_panel(registry, as_of, cache), registry
    )
    cache_name = (
        f"model_{as_of.isoformat()}_states{state_count}_seed{settings.random_seed}"
        f"_{settings.configuration_hash()}.json"
    )

    model: GaussianHiddenMarkovModel | None = None
    if artifacts is not None and artifacts.has(cache_name):
        model = GaussianHiddenMarkovModel.from_dictionary(artifacts.read_json(cache_name))
        if model.state_count != state_count:  # pragma: no cover - key covers it
            model = None
    if model is None:
        model = canonicalise(
            hidden_markov.fit(
                matrix.values,
                state_count=state_count,
                # The date enters the seed so that consecutive refits do not share
                # a starting point and inherit each other's local optimum.
                seed=settings.random_seed + as_of.year * 100 + as_of.month,
                restarts=settings.expectation_maximisation_restarts,
                max_iterations=settings.expectation_maximisation_max_iterations,
                tolerance=settings.expectation_maximisation_tolerance,
            )
        )
        if artifacts is not None:
            artifacts.write_json(cache_name, model.to_dictionary())

    filtered = model.filtered_state_probabilities(matrix.values)
    filtered_series = pd.DataFrame(filtered, index=matrix.dates)

    rates: dict[str, ConditionalRates] = {}
    for name, history in histories.items():
        condition = _condition_available_at(history, as_of)
        aligned_condition, aligned_states = condition.align(filtered_series, join="inner", axis=0)
        if aligned_condition.empty:
            raise BacktestError(
                f"indicator {name!r} has no months in common with the observation matrix as of "
                f"{as_of.isoformat()}. Its source series probably starts later than the panel; "
                "check the registry."
            )
        rates[name] = indicator_forecast.estimate_conditional_rates(
            history.indicator,
            aligned_condition.to_numpy(dtype="float64"),
            aligned_states.to_numpy(dtype="float64"),
            shrinkage_strength=settings.conditional_rate_shrinkage_strength,
        )

    return FittedRegimeModel(
        refit_date=as_of,
        model=model,
        rates_by_indicator=rates,
        months_fitted_on=len(matrix),
    )


def run_walk_forward(
    registry: EconomicSeriesRegistry,
    indicators: Sequence[BinaryIndicator],
    cache: SeriesCache,
    settings: RunSettings,
    state_count: int,
    forecast_dates: pd.DatetimeIndex,
    refit_dates: pd.DatetimeIndex,
    artifacts: ArtifactStore | None = None,
    progress_every: int = 60,
) -> pd.DataFrame:
    """Run the whole method through history and return one tidy results frame."""
    histories = prepare_indicator_history(
        indicators, registry, cache, settings.forecast_horizons_in_months
    )
    configuration_hash = settings.configuration_hash()
    refit_set = {stamp.date() for stamp in refit_dates}

    fitted: FittedRegimeModel | None = None
    rows: list[dict[str, object]] = []

    for position, stamp in enumerate(forecast_dates):
        forecast_date = stamp.date()
        if forecast_date in refit_set or fitted is None:
            fitted = fit_regime_model(
                forecast_date, registry, cache, histories, settings, state_count, artifacts
            )
            logger.info(
                "refit as_of=%s months=%d", forecast_date.isoformat(), fitted.months_fitted_on
            )

        matrix = build_observation_matrix(
            assemble_point_in_time_panel(registry, forecast_date, cache), registry
        )
        filtered_distribution = fitted.model.filtered_state_probabilities(matrix.values)[-1]
        regime_distribution = ",".join(f"{value:.6f}" for value in filtered_distribution)

        for indicator in indicators:
            history = histories[indicator.name]
            condition_now = _condition_available_at(history, forecast_date)
            condition_holds_now = (
                bool(condition_now.iloc[-1] > 0.5) if not condition_now.empty else False
            )

            for horizon in settings.forecast_horizons_in_months:
                composed = indicator_forecast.forecast_indicator(
                    indicator,
                    fitted.model,
                    filtered_distribution,
                    fitted.rates_by_indicator[indicator.name],
                    horizon,
                    condition_holds_now,
                )
                rows.append(
                    {
                        "indicator": indicator.name,
                        "forecast_date": stamp,
                        "horizon_months": horizon,
                        "predicted_probability": composed.probability,
                        "climatology_probability": _lookup(
                            history.climatology_by_horizon[horizon], stamp
                        ),
                        "realised_outcome": _lookup(history.outcomes_by_horizon[horizon], stamp),
                        "composition": indicator.composition.value,
                        "effective_sample_size": composed.effective_sample_size,
                        "distance_to_stationary": composed.distance_to_stationary,
                        "regime_distribution": regime_distribution,
                        "state_count": state_count,
                        "refit_date": pd.Timestamp(fitted.refit_date),
                        "configuration_hash": configuration_hash,
                        "seed": settings.random_seed,
                    }
                )

        if progress_every and position % progress_every == 0:
            logger.info("walk_forward %d/%d %s", position + 1, len(forecast_dates), forecast_date)

    results = pd.DataFrame(rows, columns=list(RESULT_COLUMNS))
    validate_results(results)
    return results


def _lookup(series: pd.Series, stamp: pd.Timestamp) -> float:
    value = series.get(stamp, np.nan)
    return float(value) if pd.notna(value) else float("nan")


def validate_results(results: pd.DataFrame) -> None:
    """Check the results frame keeps the promises the evaluation relies on."""
    missing = [column for column in RESULT_COLUMNS if column not in results.columns]
    if missing:
        raise BacktestError(f"results frame is missing columns {missing}")
    if results.empty:
        raise BacktestError("the walk-forward run produced no rows")

    probabilities = results["predicted_probability"].to_numpy(dtype="float64")
    if not np.isfinite(probabilities).all():
        raise BacktestError("some predicted probabilities are not finite")
    if probabilities.min() < 0.0 or probabilities.max() > 1.0:
        raise BacktestError(
            f"predicted probabilities range from {probabilities.min()} to {probabilities.max()}, "
            "outside the unit interval"
        )

    duplicated = results.duplicated(subset=["indicator", "forecast_date", "horizon_months"])
    if bool(duplicated.any()):
        raise BacktestError(
            f"{int(duplicated.sum())} rows repeat an indicator, date and horizon; each "
            "combination must appear exactly once"
        )

    realised = results["realised_outcome"].dropna().unique()
    unexpected = [value for value in realised if value not in (0.0, 1.0)]
    if unexpected:
        raise BacktestError(f"realised outcomes must be zero or one; found {unexpected[:5]}")
