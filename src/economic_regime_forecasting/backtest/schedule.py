"""When forecasts are made and when the model is refitted.

Both the data layer and the backtest need this answer, and they must give the
same one: the cache is populated for exactly the dates the walk-forward will
later ask for, or the backtest discovers a missing vintage halfway through a
forty-minute run.

Three ideas, kept apart because they are different:

*Forecast dates* are every month at which a forecast is issued, starting once
there is enough history to fit on.

*Refit dates* are the subset of those at which the model is actually refitted.
Refitting every month across seventy years is expensive and buys little, since a
transition matrix estimated on 480 months barely moves when one more arrives.
Between refits the transition matrix and emission parameters are held fixed and
only the filtered state distribution advances, which is exactly what a forecaster
running this live would do.

*Scoreable dates* are the forecast dates whose outcome has since resolved. A
ten-year forecast issued in 2020 cannot be scored yet, and counting it as
anything other than pending would be an error.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


class ScheduleError(ValueError):
    """The requested schedule is empty or incoherent."""


@dataclass(frozen=True)
class ForecastSchedule:
    """The dates a walk-forward run visits."""

    forecast_dates: pd.DatetimeIndex
    refit_dates: pd.DatetimeIndex

    def __len__(self) -> int:
        return int(len(self.forecast_dates))

    def most_recent_refit_on_or_before(self, forecast_date: pd.Timestamp) -> pd.Timestamp:
        """Which fitted model a given forecast date uses."""
        eligible = self.refit_dates[self.refit_dates <= forecast_date]
        if len(eligible) == 0:
            raise ScheduleError(
                f"no refit on or before {forecast_date:%Y-%m}; the schedule starts at "
                f"{self.refit_dates[0]:%Y-%m}"
            )
        latest: pd.Timestamp = eligible[-1]
        return latest

    def describe(self) -> str:
        return (
            f"{len(self.forecast_dates)} forecast dates from "
            f"{self.forecast_dates[0]:%Y-%m} to {self.forecast_dates[-1]:%Y-%m}, "
            f"{len(self.refit_dates)} refits"
        )


def build_schedule(
    first_forecast_date: date,
    last_forecast_date: date,
    refit_every_n_months: int,
) -> ForecastSchedule:
    """Monthly forecast dates, with refits every ``refit_every_n_months``.

    The first forecast date is always a refit date, since there is no earlier
    model to reuse.
    """
    if refit_every_n_months < 1:
        raise ScheduleError(f"refit_every_n_months must be at least 1, got {refit_every_n_months}")
    forecast_dates = pd.date_range(
        start=pd.Timestamp(first_forecast_date), end=pd.Timestamp(last_forecast_date), freq="MS"
    )
    if len(forecast_dates) == 0:
        raise ScheduleError(
            f"no months between {first_forecast_date} and {last_forecast_date}. There is not "
            "enough history for a walk-forward run; check the burn-in setting."
        )
    return ForecastSchedule(
        forecast_dates=forecast_dates,
        refit_dates=forecast_dates[::refit_every_n_months],
    )


def first_forecast_date_after_burn_in(
    observation_dates: pd.DatetimeIndex, minimum_observations: int
) -> date:
    """The earliest month with enough history behind it to fit a model.

    The returned date is the month *after* the last observation of the burn-in
    window, because a forecast made in month t uses observations through t minus
    one; month t itself has not been published.
    """
    if len(observation_dates) < minimum_observations:
        raise ScheduleError(
            f"only {len(observation_dates)} observations are available, fewer than the "
            f"{minimum_observations} the burn-in requires. Either fetch more history or lower "
            "minimum_observations_before_first_fit."
        )
    last_burn_in_month: pd.Timestamp = observation_dates[minimum_observations - 1]
    return (last_burn_in_month + pd.DateOffset(months=1)).date()
