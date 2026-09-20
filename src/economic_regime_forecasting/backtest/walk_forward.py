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
quoted. Resolved means published: an outcome counts once the last value it rests
on has appeared, its label plus its publication lag, by the same rule that censors
the conditions the rates are learned from (ADR 0009).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from economic_regime_forecasting.configuration import (
    business_cycle_announcements as announcements,
)
from economic_regime_forecasting.configuration.registry import (
    BinaryIndicator,
    EconomicSeriesRegistry,
)
from economic_regime_forecasting.configuration.run_settings import RunSettings
from economic_regime_forecasting.data import federal_reserve_client, indicator_outcomes
from economic_regime_forecasting.data.cache import ArtifactStore, SeriesCache
from economic_regime_forecasting.data.panel import assemble_point_in_time_panel, load_final_series
from economic_regime_forecasting.data.vintage import LookAheadError, VintagePolicy
from economic_regime_forecasting.features.observation_matrix import build_observation_matrix
from economic_regime_forecasting.models import gaussian_hidden_markov_model as hidden_markov
from economic_regime_forecasting.models import indicator_forecast
from economic_regime_forecasting.models import two_timescale_hidden_markov_model as two_timescale
from economic_regime_forecasting.models.gaussian_hidden_markov_model import (
    GaussianHiddenMarkovModel,
)
from economic_regime_forecasting.models.indicator_forecast import ConditionalRates
from economic_regime_forecasting.models.model_loading import regime_model_from_dictionary
from economic_regime_forecasting.models.state_labelling import canonicalise
from economic_regime_forecasting.models.two_timescale_hidden_markov_model import (
    TwoChainStateCount,
)

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
    dated_by_announcement: bool = False
    """True where a constant lag cannot say when a value was knowable: see D14."""


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
    is only used once it had been published, which for recession dating means once
    the turning point opening its phase had been announced (D14, ADR 0011) and for
    every other series means once its publication lag has passed. The one series where
    revisions are material, industrial production, is measured in the data audit
    so the size of the approximation is on the record rather than assumed away.
    """
    source_names = indicator_outcomes.required_series_names(indicators)
    final_series = load_final_series(registry, cache, source_names)

    histories: dict[str, IndicatorHistory] = {}
    for indicator in indicators:
        source = final_series[indicator.resolution.series]
        # One lag per indicator, for both things read off final data: the
        # conditions the rates are learned from and the outcomes the benchmark
        # averages. A derived series is published when its later component is.
        derived = registry.derived_by_name(indicator.resolution.series)
        lag = (
            max(
                registry[derived.minuend].publication_lag_days,
                registry[derived.subtrahend].publication_lag_days,
            )
            if derived is not None
            else registry[indicator.resolution.series].publication_lag_days
        )

        # Recession dating is announced, not published on a schedule (D14).
        dated_by_announcement = indicator.resolution.series == announcements.RECESSION_SERIES_NAME

        outcomes: dict[int, pd.Series] = {}
        climatology: dict[int, pd.Series] = {}
        for horizon in horizons_in_months:
            resolved = indicator_outcomes.resolve(indicator, source, horizon).outcomes
            outcomes[horizon] = resolved
            climatology[horizon] = _expanding_climatology(
                resolved, horizon, lag, dated_by_announcement
            )

        histories[indicator.name] = IndicatorHistory(
            indicator=indicator,
            monthly_condition=indicator_outcomes.monthly_condition(indicator, source),
            outcomes_by_horizon=outcomes,
            climatology_by_horizon=climatology,
            publication_lag_days=lag,
            dated_by_announcement=dated_by_announcement,
        )
    return histories


def publication_dates(
    labels: pd.DatetimeIndex,
    publication_lag_days: int,
    *,
    dated_by_announcement: bool = False,
) -> pd.DatetimeIndex:
    """The date each observation was published: its period label plus the lag.

    The one publication rule the walk-forward applies to final data, whether to a
    condition the forecaster reads or to an outcome its benchmark counts. The lag
    counts from the period-start label, as the registry defines it and as
    ``data.vintage.censor_by_publication_lag`` applies it to the model's inputs.

    A constant lag is wrong for recession dating, which is debt D14: the National
    Bureau of Economic Research announces turning points rather than months, so a
    month's coding is knowable only once the turning point that opens its phase has
    been announced. With ``dated_by_announcement`` a month is published at the LATER
    of the constant lag and that announcement, so the rule only ever delays a value.
    Months the table cannot place keep the constant lag.

    It must only ever delay, and the ``max`` is what makes that true. The
    announcement settling a month's phase is the most recent turning point at or
    before it, which is routinely years OLDER than the month: the December 1992 call
    on the 1991 trough settles every month up to the 2001 peak. A first version of
    this let the announcement REPLACE the constant, which dated a value before the
    month it describes existed -- 1995-01 published 1992-12-22 -- so a panel built in
    1994 could read recession codings out to 2001. The look-ahead audit caught it at
    400 moved rows. D14's complaint was only ever that a constant lag is too SHORT
    after a trough; there is no direction in which it is too long.
    """
    published = pd.DatetimeIndex(labels) + pd.Timedelta(days=publication_lag_days)
    if not dated_by_announcement:
        return published
    settled = [announcements.announced_by(label.date()) for label in pd.DatetimeIndex(labels)]
    return pd.DatetimeIndex(
        [
            max(pd.Timestamp(announced), fallback) if announced is not None else fallback
            for announced, fallback in zip(settled, published, strict=True)
        ]
    )


def _expanding_climatology(
    outcomes: pd.Series,
    horizon_in_months: int,
    publication_lag_days: int,
    dated_by_announcement: bool = False,
) -> pd.Series:
    """The base rate a forecaster could have quoted at each date.

    The outcome of a forecast made in month s at horizon h rests on observations
    up to the one labelled s + h months: the value at the horizon, or the last
    month of the window. That value is published ``publication_lag_days`` after
    its label. So the average available at t covers exactly the forecast dates
    whose deciding value had been published on or before t.

    Until 2026-09-15 the average at t covered forecast dates up to t - h, which
    counted the outcome resting on the value labelled t itself: five weeks before
    that value was published for most series, 400 days for recession dating. The
    look-ahead audit found it; ADR 0009 records the fix and what it moved.
    """
    running_mean = outcomes.expanding(min_periods=1).mean().to_numpy(dtype="float64")
    deciding_labels = pd.DatetimeIndex(outcomes.index) + pd.DateOffset(months=horizon_in_months)
    published = publication_dates(
        deciding_labels, publication_lag_days, dated_by_announcement=dated_by_announcement
    )
    # How many forecast dates' outcomes had been published by each date. Both
    # indexes ascend, so one binary search answers it for every date at once, and
    # the outcomes it counts are always a prefix of the forecast dates.
    resolved_count = np.asarray(
        published.searchsorted(pd.DatetimeIndex(outcomes.index), side="right"), dtype=np.intp
    )
    available = np.full(len(outcomes), np.nan)
    any_resolved = resolved_count > 0
    available[any_resolved] = running_mean[resolved_count[any_resolved] - 1]
    return pd.Series(available, index=outcomes.index, name="climatology")


def condition_available_at(history: IndicatorHistory, as_of: date) -> pd.Series:
    """The indicator's monthly condition, censored to what had been published."""
    condition = history.monthly_condition.dropna()
    published = publication_dates(
        pd.DatetimeIndex(condition.index),
        history.publication_lag_days,
        dated_by_announcement=history.dated_by_announcement,
    )
    return condition[published <= pd.Timestamp(as_of)]


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
    # A TwoChainStateCount asks for two chains (research arm A4); an integer asks for
    # one, as it always has. Both chain counts go into the key, because 2x4 and 4x2
    # are the same number of joint states and different models.
    state_label = (
        state_count.label if isinstance(state_count, TwoChainStateCount) else str(state_count)
    )
    cache_name = (
        f"model_{as_of.isoformat()}_states{state_label}_seed{settings.random_seed}"
        f"_{settings.configuration_hash()}.json"
    )

    model: GaussianHiddenMarkovModel | None = None
    if artifacts is not None and artifacts.has(cache_name):
        model = regime_model_from_dictionary(artifacts.read_json(cache_name))
        if model.state_count != state_count:  # pragma: no cover - key covers it
            model = None
    if model is None:
        # The date enters the seed so that consecutive refits do not share a
        # starting point and inherit each other's local optimum.
        seed = settings.random_seed + as_of.year * 100 + as_of.month
        if isinstance(state_count, TwoChainStateCount):
            model = two_timescale.fit(
                matrix.values,
                growth_chain_state_count=state_count.growth_chain_state_count,
                levels_chain_state_count=state_count.levels_chain_state_count,
                seed=seed,
                restarts=settings.expectation_maximisation_restarts,
                max_iterations=settings.expectation_maximisation_max_iterations,
                tolerance=settings.expectation_maximisation_tolerance,
            )
        else:
            model = canonicalise(
                hidden_markov.fit(
                    matrix.values,
                    state_count=state_count,
                    seed=seed,
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
        condition = condition_available_at(history, as_of)
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
    # One pre-flight, before anything is fitted, so a schedule that breaks the
    # promise fails in seconds rather than fifteen minutes. This covers every path
    # that produces a results frame, because this is the only function that builds
    # one. A caller that reaches past it into `fit_regime_model` or
    # `assemble_point_in_time_panel` directly is outside the check; that is stated
    # rather than hidden.
    if settings.start_walk_forward_when_every_input_is_point_in_time:
        assert_every_forecast_date_is_fully_point_in_time(registry, cache, forecast_dates)

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
            condition_now = condition_available_at(history, forecast_date)
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


def _assert_every_vintage_is_cached(
    registry: EconomicSeriesRegistry,
    cache: SeriesCache,
    candidate_dates: pd.DatetimeIndex,
) -> None:
    """Refuse to scan when a vintage the scan needs would have to be downloaded.

    ``vintage.observe`` calls ``get_or_fetch``, so a scan over six hundred dates
    against a half-populated cache would quietly turn a check into a forty-minute
    download. This asks the cache first and says what to run instead.
    """
    absent: list[str] = []
    for entry in registry.model_inputs:
        if not cache.contains(federal_reserve_client.build_request(entry.series_id)):
            absent.append(f"{entry.series_id} (current vintage)")
        if not entry.is_revised:
            continue
        for stamp in candidate_dates:
            request = federal_reserve_client.build_request(entry.series_id, stamp.date())
            if not cache.contains(request):
                absent.append(f"{entry.series_id} as of {stamp.date().isoformat()}")
    if absent:
        raise BacktestError(
            f"{len(absent)} of the vintages this scan needs are not cached, first few "
            f"{absent[:3]}. Run `forecast fetch-data` first; it skips anything already "
            "there. This scan deliberately does not reach the network, because a check "
            "that silently downloads is not a check."
        )


def forecast_dates_using_the_publication_lag_fallback(
    registry: EconomicSeriesRegistry,
    cache: SeriesCache,
    candidate_dates: pd.DatetimeIndex,
) -> list[date]:
    """Every candidate date whose point-in-time panel falls back to revised values.

    Reads only from cache: a date whose vintage is not cached raises rather than
    reaching the network, because a scan that silently downloaded would turn a
    check into a forty-minute surprise.

    One definition of "which policy" serves both the honest-start finder and the
    pre-flight assertion, so the two cannot drift apart.
    """
    _assert_every_vintage_is_cached(registry, cache, candidate_dates)
    fallback_key = VintagePolicy.PUBLICATION_LAG_FALLBACK.value
    offending: list[date] = []
    for stamp in candidate_dates:
        as_of = stamp.date()
        panel = assemble_point_in_time_panel(registry, as_of, cache)
        if panel.policy_counts()[fallback_key]:
            offending.append(as_of)
    return offending


def find_first_fully_point_in_time_date(
    registry: EconomicSeriesRegistry,
    cache: SeriesCache,
    settings: RunSettings,
    earliest_candidate: date,
    last_forecast_date: date,
) -> date:
    """The earliest month from which *every later month too* is fully point in time.

    Not simply the first clean month: the fallback pattern is not monotone.
    Industrial production falls back for twelve months in 1971-72 and is clean on
    either side, while the consumer price index falls back continuously until
    1994-02. The answer is therefore the month after the *last* fallback month in
    the range, which on the live cache is 1994-03-01.

    The scan steps a month at a time, unlike ``find_first_forecast_date``, which
    steps a year: panel length is monotone in the date and fallback usage is not.
    """
    candidates = pd.date_range(
        start=pd.Timestamp(earliest_candidate), end=pd.Timestamp(last_forecast_date), freq="MS"
    )
    if len(candidates) == 0:
        raise BacktestError(
            f"no months between {earliest_candidate} and {last_forecast_date}, so there is "
            "no range in which to look for an honest start date."
        )
    offending = forecast_dates_using_the_publication_lag_fallback(registry, cache, candidates)
    if not offending:
        return earliest_candidate
    last_offending = offending[-1]
    if last_offending == candidates[-1].date():
        raise BacktestError(
            f"every month from {earliest_candidate} to {last_forecast_date} would have to "
            f"start on or before {last_offending}, which itself falls back to revised "
            f"values; {len(offending)} of {len(candidates)} candidates fall back. There is "
            "no fully point-in-time start inside this range. Either widen the range, fetch "
            "the missing archival vintages with `forecast fetch-data`, or set "
            "start_walk_forward_when_every_input_is_point_in_time to False and accept the "
            "documented fallback (docs/adr/0008)."
        )
    return (pd.Timestamp(last_offending) + pd.DateOffset(months=1)).date()


def assert_every_forecast_date_is_fully_point_in_time(
    registry: EconomicSeriesRegistry,
    cache: SeriesCache,
    forecast_dates: pd.DatetimeIndex,
) -> None:
    """Raise ``LookAheadError`` if any forecast date uses the publication-lag fallback.

    ``LookAheadError`` rather than a new exception: fitting on a publication-lag
    fallback means fitting on values revised later than the forecast date, which is
    information published in the future. That is exactly what the existing name
    means. One invariant, two places it can be violated.
    """
    offending = forecast_dates_using_the_publication_lag_fallback(registry, cache, forecast_dates)
    if not offending:
        return
    shown = ", ".join(item.strftime("%Y-%m") for item in offending[:5])
    raise LookAheadError(
        f"{len(offending)} of {len(forecast_dates)} forecast dates in this schedule fall back "
        f"to revised values: {shown} (first five of {len(offending)}). "
        "start_walk_forward_when_every_input_is_point_in_time promises that every model "
        "input is on a genuine point-in-time vintage. Either set it to False and accept the "
        "documented fallback (docs/adr/0008), or fetch the missing archival vintages with "
        "`forecast fetch-data`. ALFRED holds no usable consumer price index vintage before "
        "1994-03; see docs/adr/0008 for the probe evidence."
    )


def find_first_forecast_date(
    registry: EconomicSeriesRegistry,
    cache: SeriesCache,
    settings: RunSettings,
    earliest_candidate: date,
    latest_candidate: date,
) -> date:
    """The first month whose point-in-time panel is long enough to fit on.

    The obvious shortcut, counting months in today's panel, is wrong. A panel
    built as of 1970 is shorter than the same window of today's data, because the
    consumer price index has no usable vintage that far back and falls back to a
    publication-lag view that stops earlier. So the search asks the actual
    point-in-time panel, stepping forward a year at a time until one is long
    enough.
    """
    candidate = earliest_candidate
    while candidate <= latest_candidate:
        matrix = build_observation_matrix(
            assemble_point_in_time_panel(registry, candidate, cache), registry
        )
        if len(matrix) >= settings.minimum_observations_before_first_fit:
            return candidate
        candidate = (pd.Timestamp(candidate) + pd.DateOffset(years=1)).date()
    raise BacktestError(
        f"no month between {earliest_candidate} and {latest_candidate} has a point-in-time panel "
        f"with {settings.minimum_observations_before_first_fit} observations. Either the data "
        "starts later than expected or the burn-in is set too high."
    )
