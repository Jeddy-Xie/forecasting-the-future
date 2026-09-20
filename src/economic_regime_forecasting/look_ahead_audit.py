"""Prove by execution that no forecast saw what had not been published yet.

A forecast issued on date t may depend only on information published by t. So if
every piece of information a forecaster at a cutoff date C could *not* have seen is
replaced with garbage, every forecast issued on or before C must come out
byte-identical. If one moves, some path lets post-cutoff information reach a
pre-cutoff forecast. That is a look-ahead, and the rows that moved say where it
enters.

The check needs no understanding of the code under test, which is the point. A
reviewer reads a diff and judges; this executes and measures. It is the
deterministic half of the look-ahead requirement in the research slate's decision
rule, and its failure mode is uncorrelated with a reader's.

**What is perturbed.** A copy of the series cache in a temporary directory, never
the cache itself, written through ``data/cache.py`` like every other cache write.
Two things are rewritten as ``value * 1.7 + 11.0``, which is deterministic, never
the identity and large enough to move every derived quantity:

1. every value of every archival vintage dated after C, including values for
   months before C, because a vintage published after C carries revisions nobody
   had at C;
2. in every current-vintage file, every observation not yet published at C: its
   label is on or after C, or its label plus that series' registered
   ``publication_lag_days`` falls after C. Unavailable means unpublished, as the
   pre-registered decision rule says, not merely unlabelled. A value labelled a
   month before C with a 44-day lag was still unpublished at C, and reading it is
   the classic one-month look-ahead. The label clause keeps the rule a superset of
   the boundary invariant in ``data.vintage`` whatever the lag.

Archival vintages dated on or before C are left alone: everything in one had been
published by its vintage date. The derived term spread is never cached. It is
computed from its two legs, each perturbed by its own lag, so a spread value is
perturbed exactly when its label plus the larger of the two lags falls after C.
That is the lag ``prepare_indicator_history`` gives it.

Until the rule became publication-aware, part 2 was on labels alone, and a leak
reading a value inside its publication lag passed. A test keeps both halves of
that on the record.

A perturbed entry's payload digest is recomputed from the values it now holds, so
it can never be mistaken for the response the service returned.

**What is run.** Two walk-forward runs over the same schedule -- the configured
one, truncated to forecast dates on or before C -- one on an unperturbed copy and
one on the perturbed copy. Each has its own empty fitted-model store, so every fit
and the burn-in state-count choice are computed from scratch. Reusing a cached fit
would hide exactly the leak being tested for: a fit that used future data would be
read back rather than recomputed.

**What is compared.** Every row, keyed on indicator, forecast date and horizon,
for *exact* equality of ``predicted_probability``, ``regime_distribution``,
``climatology_probability`` (so the benchmark is checked too), ``state_count`` and
``refit_date``. Fits are byte-identical within one environment and one process, so
any tolerance would only be room for a leak to hide in. ``realised_outcome`` is not
compared: it legitimately depends on the future, and is scoring data, not an
input to a forecast.

**What it does not cover**, stated so nobody over-trusts it:

- Revised values of observations labelled *before* C, in the current-vintage
  files. The conditions per-regime rates are estimated from read final revised
  data with publication timing enforced, a documented approximation
  (``docs/TECHNICAL_DEBT.md``, D5). Perturbing them would fail main by design and
  prove nothing new.
- A publication lag that is itself wrong. The check takes each series' lag from
  the registry, the figure the pipeline censors by. A lag set too short there is
  too short here as well, and invisible to both.
- Leaks shorter than the distance to C. For a forecast issued at t before C the
  check sees information from on or after C, not from between t and C. The
  forecast issued at C itself is the sharpest test, which is why the default
  cutoff is both a forecast date and a refit date.

Exit codes follow ``forecast baseline compare``: 0 nothing moved, 1 something did,
2 the check could not be made. The third is never a pass.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from economic_regime_forecasting.backtest.schedule import ForecastSchedule
from economic_regime_forecasting.backtest.state_count_on_burn_in import (
    state_count_for_the_backtest,
)
from economic_regime_forecasting.backtest.walk_forward import run_walk_forward
from economic_regime_forecasting.configuration import (
    business_cycle_announcements as announcements,
)
from economic_regime_forecasting.configuration.registry import (
    BinaryIndicator,
    EconomicSeriesRegistry,
)
from economic_regime_forecasting.configuration.run_settings import RunSettings
from economic_regime_forecasting.data.cache import (
    ArtifactStore,
    SeriesCache,
    SeriesRequest,
    SeriesSnapshot,
    digest_of,
)

logger = logging.getLogger(__name__)

CHECK_NAME = "future-perturbation invariance"

PERTURBATION_SCALE = 1.7
PERTURBATION_SHIFT = 11.0
PERTURBATION_RULE = f"value * {PERTURBATION_SCALE} + {PERTURBATION_SHIFT}"
"""No random draw, so two audits of one commit perturb identically."""

DEFAULT_CUTOFF_MONTHS_AFTER_FIRST_FORECAST = 72
"""The default cutoff is the first refit at least this long after the first
forecast date. Six years gives the check several refits, the burn-in choice among
them, while keeping the run to a few minutes."""

KEY_COLUMNS: tuple[str, ...] = ("indicator", "forecast_date", "horizon_months")

COMPARED_FIELDS: tuple[str, ...] = (
    "predicted_probability",
    "regime_distribution",
    "climatology_probability",
    "state_count",
    "refit_date",
)
"""Every input-derived field of a forecast row. ``realised_outcome`` is absent on
purpose: it is what happened, which depends on the future by definition."""

NOT_COMPARED = (
    "realised_outcome is not compared: it is scoring data and legitimately depends on the future"
)

OUT_OF_SCOPE = (
    "revised values of observations already published at the cutoff, in the current-vintage "
    "files. Per-regime rates are estimated from conditions read off final revised data with "
    "publication timing enforced, a documented approximation (docs/TECHNICAL_DEBT.md, D5); "
    "perturbing them would fail main by design and prove nothing new. Nor does the check see a "
    "publication lag that is itself wrong: it takes each series' lag from the registry, the "
    "figure the pipeline censors by. And for a forecast issued before the cutoff it sees "
    "information unpublished at the cutoff, not information published between that "
    "forecast's date and the cutoff; the forecast issued at the cutoff is its sharpest test."
)


class LookAheadAuditError(RuntimeError):
    """The check could not be made. That is never a pass."""


# ------------------------------------------------------------------ perturbation


def perturb(values: np.ndarray) -> np.ndarray:
    """The garbage that replaces what nobody at the cutoff could have seen."""
    return values * PERTURBATION_SCALE + PERTURBATION_SHIFT


def publication_lag_days_by_series(registry: EconomicSeriesRegistry) -> dict[str, int]:
    """Each series' publication lag, from the registry, keyed by series identifier."""
    return {entry.series_id: entry.publication_lag_days for entry in registry.series}


@dataclass(frozen=True)
class PerturbationSummary:
    """What one copy of the cache did to the entries it copied."""

    cutoff: date | None
    entries_copied: int
    vintages_perturbed_entirely: int
    snapshots_perturbed_from_the_cutoff: int
    observations_perturbed: int
    publication_lag_days_by_series: dict[str, int] | None = None
    """The lags the current-vintage files were perturbed by; ``None`` for labels alone."""

    def as_dictionary(self) -> dict[str, Any]:
        return {
            "rule": PERTURBATION_RULE,
            "cutoff": None if self.cutoff is None else self.cutoff.isoformat(),
            "unavailable_means": (
                "in an archival vintage dated after the cutoff, every value; in a current-vintage "
                "file, every observation labelled on or after the cutoff or whose label plus its "
                "series' publication lag falls after it; nothing in a vintage dated on or before it"
            ),
            "publication_lag_days_by_series": self.publication_lag_days_by_series,
            "entries_copied": self.entries_copied,
            "archival_vintages_dated_after_the_cutoff_perturbed_entirely": (
                self.vintages_perturbed_entirely
            ),
            "current_vintage_files_with_unpublished_observations_perturbed": (
                self.snapshots_perturbed_from_the_cutoff
            ),
            "observations_perturbed": self.observations_perturbed,
        }


def perturbed_snapshot(
    snapshot: SeriesSnapshot,
    cutoff: date,
    publication_lag_days: int = 0,
    dated_by_announcement: bool = False,
) -> tuple[SeriesSnapshot, int]:
    """``snapshot`` with every value unavailable at ``cutoff`` perturbed, and how many.

    An archival vintage dated after the cutoff is perturbed whole: it carries
    revisions to every month, including months before the cutoff. One dated on or
    before the cutoff had been published by then; only a label on or after the
    cutoff, which the boundary invariant forbids, would be touched. In a
    current-vintage file an observation is unavailable when its label is on or
    after the cutoff or its label plus ``publication_lag_days`` falls after it. A
    lag of zero, the default, leaves the label rule alone. A snapshot with nothing
    to perturb comes back unchanged, digest and all.

    With ``dated_by_announcement`` a value is published at the LATER of its
    constant-lag date and the announcement of the turning point opening its phase,
    which is what recession dating obeys (D14). The rule only ever delays. The
    announcement that settles a month is the most recent turning point at or before
    it and is routinely years older than the month itself, so taking it alone would
    date a value before the month it describes existed.

    The audit must apply the same rule as the pipeline, because where the two
    disagree it either leaves untested the post-trough months the pipeline calls
    unknowable, or scrambles values the pipeline legitimately used and fails for a
    leak that is not there.

    The publication date is computed here rather than borrowed from the pipeline's
    own rule, so that a mistake in that rule cannot agree with the check about it. The
    announcement dates come from the same verified table; the rule applying them does
    not.
    """
    observations = snapshot.observations
    vintage_date = snapshot.request.vintage_date
    labels = pd.DatetimeIndex(observations.index)
    stamp = pd.Timestamp(cutoff)
    if vintage_date is not None and vintage_date > cutoff:
        unavailable = np.ones(observations.size, dtype=bool)
    elif vintage_date is not None:
        unavailable = np.asarray(labels >= stamp, dtype=bool)
    else:
        published_on = labels + pd.Timedelta(days=publication_lag_days)
        if dated_by_announcement:
            published_on = pd.DatetimeIndex(
                [
                    max(pd.Timestamp(settled), fallback) if settled is not None else fallback
                    for settled, fallback in zip(
                        [announcements.announced_by(label.date()) for label in labels],
                        published_on,
                        strict=True,
                    )
                ]
            )
        unavailable = np.asarray((labels >= stamp) | (published_on > stamp), dtype=bool)
    count = int(unavailable.sum())
    if count == 0:
        return snapshot, 0

    values = observations.to_numpy(dtype="float64", copy=True)
    values[unavailable] = perturb(values[unavailable])
    changed = pd.Series(values, index=observations.index, name=observations.name, dtype="float64")
    return (
        replace(snapshot, observations=changed, payload_digest=digest_of(changed.to_csv())),
        count,
    )


def _request_from(recorded: object) -> SeriesRequest:
    """The request a sidecar says its entry answers."""
    if not isinstance(recorded, dict):
        raise LookAheadAuditError(
            f"a cache sidecar records its request as {recorded!r}, which is not a request. "
            "Delete the entry and run `forecast fetch-data`."
        )
    vintage = recorded.get("vintage_date")
    return SeriesRequest(
        source=str(recorded["source"]),
        series_id=str(recorded["series_id"]),
        transform=str(recorded["transform"]),
        vintage_date=None if vintage is None else date.fromisoformat(str(vintage)),
    )


def series_cache_at(root: Path) -> SeriesCache:
    """A series cache laid out under ``root`` the way the project's own is."""
    return SeriesCache(root / "raw", root / "vintage")


def _lag_for(series_id: str, lags: Mapping[str, int] | None) -> int:
    """A cached series' publication lag, or a refusal. Never a guessed default."""
    if lags is None:
        return 0
    if series_id not in lags:
        raise LookAheadAuditError(
            f"{series_id} is in the cache but not in the registry, so when its observations "
            "were published is unknown and what was unavailable at the cutoff cannot be said. "
            "Add it to economic_series.yaml or delete its cache entries."
        )
    return int(lags[series_id])


def copy_series_cache(
    source: SeriesCache,
    destination: Path,
    cutoff: date | None = None,
    publication_lag_days_by_series: Mapping[str, int] | None = None,
) -> PerturbationSummary:
    """Copy every entry of ``source`` into a new cache under ``destination``.

    Every entry is read with ``SeriesCache.read`` and written with
    ``SeriesCache.write``, so each sidecar is regenerated from the values it
    describes. ``source`` is only ever read. With a ``cutoff``, every value
    unavailable at that date is perturbed on the way across.
    ``publication_lag_days_by_series`` gives each current-vintage file's lag. The
    audit always passes the registry's lags. Without them every lag is zero, which
    is the label rule alone, and a series missing from them is refused.
    """
    entries = source.entries()
    if not entries:
        raise LookAheadAuditError(
            "the series cache holds no entries, so there is nothing to perturb and no run to "
            "compare. Run `forecast fetch-data` first."
        )
    target = series_cache_at(destination)
    vintages_whole = 0
    from_the_cutoff = 0
    observations = 0
    for sidecar in entries:
        snapshot = source.read(_request_from(sidecar.get("request")))
        if cutoff is not None:
            lag = _lag_for(snapshot.request.series_id, publication_lag_days_by_series)
            snapshot, count = perturbed_snapshot(
                snapshot,
                cutoff,
                lag,
                dated_by_announcement=(
                    snapshot.request.series_id == announcements.RECESSION_SERIES_ID
                ),
            )
            if count:
                observations += count
                vintage_date = snapshot.request.vintage_date
                if vintage_date is not None and vintage_date > cutoff:
                    vintages_whole += 1
                else:
                    from_the_cutoff += 1
        target.write(snapshot)
    return PerturbationSummary(
        cutoff=cutoff,
        entries_copied=len(entries),
        vintages_perturbed_entirely=vintages_whole,
        snapshots_perturbed_from_the_cutoff=from_the_cutoff,
        observations_perturbed=observations,
        publication_lag_days_by_series=(
            None
            if publication_lag_days_by_series is None
            else dict(sorted(publication_lag_days_by_series.items()))
        ),
    )


# ------------------------------------------------------------------ the schedule


def default_cutoff(schedule: ForecastSchedule) -> date:
    """The first refit at least six years after the first forecast date."""
    earliest = schedule.forecast_dates[0] + pd.DateOffset(
        months=DEFAULT_CUTOFF_MONTHS_AFTER_FIRST_FORECAST
    )
    eligible = schedule.refit_dates[schedule.refit_dates >= earliest]
    if len(eligible) == 0:
        raise LookAheadAuditError(
            f"no refit in the schedule ({schedule.describe()}) falls at least "
            f"{DEFAULT_CUTOFF_MONTHS_AFTER_FIRST_FORECAST} months after the first forecast date, "
            "so there is no default cutoff. Pass --cutoff with a date inside the schedule."
        )
    chosen: pd.Timestamp = eligible[0]
    return chosen.date()


def truncate_schedule(schedule: ForecastSchedule, cutoff: date) -> ForecastSchedule:
    """The configured schedule, restricted to forecast dates on or before ``cutoff``."""
    stamp = pd.Timestamp(cutoff)
    forecast_dates = schedule.forecast_dates[schedule.forecast_dates <= stamp]
    if len(forecast_dates) == 0:
        raise LookAheadAuditError(
            f"no forecast date falls on or before the cutoff {cutoff.isoformat()}; the schedule "
            f"is {schedule.describe()}. Choose a cutoff inside it."
        )
    return ForecastSchedule(
        forecast_dates=forecast_dates,
        refit_dates=schedule.refit_dates[schedule.refit_dates <= stamp],
    )


# ------------------------------------------------------------------- the runs


@dataclass(frozen=True)
class AuditRun:
    """One of the two walk-forward runs, as the audit record describes it."""

    label: str
    state_count: int
    runner_up_state_count: int | None
    fits_computed: int
    rows: int

    def as_dictionary(self) -> dict[str, Any]:
        return {
            "state_count_chosen_on_the_burn_in_window": self.state_count,
            "runner_up_state_count": self.runner_up_state_count,
            "fits_computed_from_scratch": self.fits_computed,
            "rows": self.rows,
        }


def _run_from_scratch(
    label: str,
    registry: EconomicSeriesRegistry,
    indicators: Sequence[BinaryIndicator],
    cache_root: Path,
    settings: RunSettings,
    schedule: ForecastSchedule,
    model_store: Path,
) -> tuple[AuditRun, pd.DataFrame]:
    """The burn-in choice and the walk-forward, on one copy, with nothing cached."""
    if model_store.exists() and any(model_store.iterdir()):
        raise LookAheadAuditError(
            f"the {label} run's fitted-model store {model_store} is not empty. Every fit must be "
            "computed from scratch, or a fit that saw the future would be read back rather than "
            "recomputed."
        )
    artifacts = ArtifactStore(model_store)
    cache = series_cache_at(cache_root)
    try:
        # The same question the backtest asks, so a configuration that decides its count
        # anywhere but the sweep is audited with the count it will actually run (D15).
        choice = state_count_for_the_backtest(
            registry,
            cache,
            settings,
            first_forecast_date=schedule.forecast_dates[0].date(),
            artifacts=artifacts,
        )
        results = run_walk_forward(
            registry,
            indicators,
            cache,
            settings,
            choice.state_count,
            schedule.forecast_dates,
            schedule.refit_dates,
            artifacts,
            progress_every=0,
        )
    except Exception as error:
        # A crash is neither a pass nor a moved row. Uncaught, it would leave the
        # process with exit code 1, which this command reserves for a leak.
        raise LookAheadAuditError(
            f"the {label} walk-forward could not complete: {type(error).__name__}: {error}"
        ) from error
    if cache.statistics.misses:
        raise LookAheadAuditError(
            f"the {label} run asked for {cache.statistics.misses} series its copy of the cache did "
            "not hold, and fetched them. The two runs then did not read the same data, so the "
            "comparison is void. Run `forecast fetch-data`, then audit again."
        )
    fits = sum(1 for path in artifacts.written if path.name.startswith("model_"))
    logger.info("look_ahead_audit run=%s rows=%d fits=%d", label, len(results), fits)
    return (
        AuditRun(
            label=label,
            state_count=choice.state_count,
            runner_up_state_count=choice.runner_up_state_count,
            fits_computed=fits,
            rows=len(results),
        ),
        results,
    )


# ------------------------------------------------------------------ comparison


def _json_value(value: Any) -> Any:
    """A compared value as JSON can hold it, at full precision."""
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, float | np.floating):
        return None if math.isnan(float(value)) else float(value)
    return value


def _identical(original: Any, perturbed: Any) -> bool:
    """Exact equality, with a missing value equal only to another missing value."""
    both_numbers = isinstance(original, float | np.floating) and isinstance(
        perturbed, float | np.floating
    )
    if both_numbers and (math.isnan(float(original)) or math.isnan(float(perturbed))):
        return math.isnan(float(original)) and math.isnan(float(perturbed))
    return bool(original == perturbed)


@dataclass(frozen=True)
class FieldMove:
    field: str
    original: Any
    perturbed: Any


@dataclass(frozen=True)
class MovedRow:
    """One forecast that changed when only unavailable information did."""

    indicator: str
    forecast_date: date
    horizon_months: int
    moves: tuple[FieldMove, ...]

    def as_dictionary(self) -> dict[str, Any]:
        return {
            "indicator": self.indicator,
            "forecast_date": self.forecast_date.isoformat(),
            "horizon_months": self.horizon_months,
            "fields": {
                item.field: {"original": item.original, "perturbed": item.perturbed}
                for item in self.moves
            },
        }


def compare_runs(original: pd.DataFrame, perturbed: pd.DataFrame) -> tuple[MovedRow, ...]:
    """Every row whose compared fields differ, earliest forecast date first.

    Two runs that do not hold the same rows are not compared at all: a row present
    on one side only is a structural mismatch, and the check could not be made.
    """
    for frame, side in ((original, "original"), (perturbed, "perturbed")):
        missing = [name for name in (*KEY_COLUMNS, *COMPARED_FIELDS) if name not in frame.columns]
        if missing:
            raise LookAheadAuditError(f"the {side} run's results have no column(s) {missing}")
        repeated = int(frame.duplicated(subset=list(KEY_COLUMNS)).sum())
        if repeated:
            raise LookAheadAuditError(
                f"the {side} run's results repeat {repeated} (indicator, forecast date, horizon) "
                "keys, so no row can be lined up with exactly one other"
            )

    left = original.set_index(list(KEY_COLUMNS))[list(COMPARED_FIELDS)]
    right = perturbed.set_index(list(KEY_COLUMNS))[list(COMPARED_FIELDS)]
    only_original = left.index.difference(right.index)
    only_perturbed = right.index.difference(left.index)
    if len(only_original) or len(only_perturbed):
        raise LookAheadAuditError(
            f"the two runs do not hold the same rows: {len(only_original)} only in the original, "
            f"{len(only_perturbed)} only in the perturbed, first few "
            f"{[*only_original[:3], *only_perturbed[:3]]}. A row set that differs is a "
            "structural mismatch, not a comparison."
        )
    right = right.loc[left.index]

    moved: list[MovedRow] = []
    for key, left_row, right_row in zip(
        left.index,
        left.itertuples(index=False, name=None),
        right.itertuples(index=False, name=None),
        strict=True,
    ):
        moves = tuple(
            FieldMove(field, _json_value(before), _json_value(after))
            for field, before, after in zip(COMPARED_FIELDS, left_row, right_row, strict=True)
            if not _identical(before, after)
        )
        if moves:
            indicator, forecast_date, horizon = key
            moved.append(
                MovedRow(
                    indicator=str(indicator),
                    forecast_date=pd.Timestamp(forecast_date).date(),
                    horizon_months=int(horizon),
                    moves=moves,
                )
            )
    return tuple(
        sorted(moved, key=lambda row: (row.forecast_date, row.indicator, row.horizon_months))
    )


# ---------------------------------------------------------------------- result


def _months(stamps: pd.DatetimeIndex) -> list[str]:
    return [stamp.date().isoformat() for stamp in stamps]


def _render(value: Any) -> str:
    if value is None:
        return "missing"
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _text_table(headings: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """Left-aligned columns under a rule, wide enough for their longest cell."""
    widths = [
        max(len(headings[column]), *(len(row[column]) for row in rows))
        for column in range(len(headings))
    ]
    lines = ["  ".join(heading.ljust(widths[i]) for i, heading in enumerate(headings)).rstrip()]
    lines.append("  ".join("-" * width for width in widths))
    for row in rows:
        lines.append("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip())
    return "\n".join(lines)


@dataclass(frozen=True)
class LookAheadAudit:
    """The two runs, what was perturbed between them, and every row that moved."""

    cutoff: date
    cutoff_chosen_by_default: bool
    configured_schedule: ForecastSchedule
    audited_schedule: ForecastSchedule
    perturbation: PerturbationSummary
    original: AuditRun
    perturbed: AuditRun
    rows_compared: int
    moved: tuple[MovedRow, ...]
    configuration_hash: str
    random_seed: int

    @property
    def exit_code(self) -> int:
        return 1 if self.moved else 0

    @property
    def verdict(self) -> str:
        cutoff = self.cutoff.isoformat()
        if not self.moved:
            return (
                f"no forecast issued on or before {cutoff} changed when every observation "
                f"unavailable at {cutoff} was perturbed"
            )
        dates = sorted({row.forecast_date for row in self.moved})
        return (
            f"{len(self.moved)} of {self.rows_compared} forecasts issued on or before {cutoff} "
            f"changed when only information unavailable at {cutoff} was perturbed, on "
            f"{len(dates)} forecast date(s) from {dates[0].isoformat()} to "
            f"{dates[-1].isoformat()}. The earliest is where the leak enters."
        )

    def _cutoff_reason(self) -> str:
        if not self.cutoff_chosen_by_default:
            return "given with --cutoff"
        first = self.configured_schedule.forecast_dates[0].date().isoformat()
        return (
            f"the first refit at least {DEFAULT_CUTOFF_MONTHS_AFTER_FIRST_FORECAST} months after "
            f"the first forecast date {first}"
        )

    def as_dictionary(self) -> dict[str, Any]:
        """The whole audit for a branch runner. Nothing in it depends on the clock."""
        return {
            "check": CHECK_NAME,
            "exit_code": self.exit_code,
            "passed": not self.moved,
            "verdict": self.verdict,
            "cutoff": self.cutoff.isoformat(),
            "cutoff_chosen": self._cutoff_reason(),
            "configuration_hash": self.configuration_hash,
            "random_seed": self.random_seed,
            "configured_schedule": {
                "first_forecast_date": self.configured_schedule.forecast_dates[0]
                .date()
                .isoformat(),
                "last_forecast_date": self.configured_schedule.forecast_dates[-1]
                .date()
                .isoformat(),
                "forecast_date_count": len(self.configured_schedule.forecast_dates),
                "refit_count": len(self.configured_schedule.refit_dates),
            },
            "audited_schedule": {
                "forecast_date_count": len(self.audited_schedule.forecast_dates),
                "first_forecast_date": self.audited_schedule.forecast_dates[0].date().isoformat(),
                "last_forecast_date": self.audited_schedule.forecast_dates[-1].date().isoformat(),
                "refit_dates": _months(self.audited_schedule.refit_dates),
            },
            "perturbation": self.perturbation.as_dictionary(),
            "runs": {
                self.original.label: self.original.as_dictionary(),
                self.perturbed.label: self.perturbed.as_dictionary(),
            },
            "comparison": {
                "keyed_on": list(KEY_COLUMNS),
                "fields": list(COMPARED_FIELDS),
                "equality": "exact",
                "not_compared": NOT_COMPARED,
                "rows_compared": self.rows_compared,
                "rows_moved": len(self.moved),
            },
            "not_covered": OUT_OF_SCOPE,
            "moved_rows": [row.as_dictionary() for row in self.moved],
        }

    def describe(self, rows_shown: int = 40) -> str:
        """The reader's view: what was covered, what was perturbed, and the answer."""
        audited = self.audited_schedule
        refits = ", ".join(stamp.strftime("%Y-%m") for stamp in audited.refit_dates)
        perturbation = self.perturbation
        cutoff = self.cutoff.isoformat()
        lines = [
            f"look-ahead audit: {CHECK_NAME}",
            f"cutoff       {cutoff}, {self._cutoff_reason()}",
            f"covered      {len(audited.forecast_dates)} forecast dates from "
            f"{audited.forecast_dates[0]:%Y-%m} to {audited.forecast_dates[-1]:%Y-%m} and "
            f"{len(audited.refit_dates)} refits ({refits}), of the configured "
            f"{len(self.configured_schedule.forecast_dates)} forecast dates",
            f"perturbed    {PERTURBATION_RULE} on every value of "
            f"{perturbation.vintages_perturbed_entirely} archival vintages dated after {cutoff}, "
            f"and on every observation still unpublished at {cutoff} (labelled on or after it, "
            "or within its series' publication lag of it) in "
            f"{perturbation.snapshots_perturbed_from_the_cutoff} current-vintage files: "
            f"{perturbation.observations_perturbed} values across "
            f"{perturbation.entries_copied} copied entries",
            "runs         two walk-forwards, each on its own copy of the cache with an empty "
            "fitted-model store",
        ]
        for run in (self.original, self.perturbed):
            lines.append(
                f"               {run.label:<10} {run.state_count} regimes chosen on the burn-in "
                f"window, {run.fits_computed} fits computed from scratch, {run.rows} rows"
            )
        lines += [
            f"compared     {', '.join(COMPARED_FIELDS)} on {self.rows_compared} rows keyed by "
            "indicator, forecast date and horizon, for exact equality; " + NOT_COMPARED,
            f"not covered  {OUT_OF_SCOPE}",
            "",
        ]
        if not self.moved:
            lines.append(f"PASS: {self.verdict}")
            return "\n".join(lines)

        lines.append(f"LOOK-AHEAD: {self.verdict}")
        table_rows = [
            (
                row.forecast_date.isoformat(),
                row.indicator,
                str(row.horizon_months),
                move.field,
                _render(move.original),
                _render(move.perturbed),
            )
            for row in self.moved[:rows_shown]
            for move in row.moves
        ]
        lines.append("")
        lines.append(
            _text_table(
                ("forecast date", "indicator", "horizon", "field", "original", "perturbed"),
                table_rows,
            )
        )
        if len(self.moved) > rows_shown:
            lines.append(
                f"... and {len(self.moved) - rows_shown} further moved rows, every one of them in "
                "the audit record"
            )
        return "\n".join(lines)


def failure_record(error: LookAheadAuditError, cutoff: date | None) -> dict[str, Any]:
    """What the audit record says when the check could not be made.

    Written over any earlier record, so a stale pass can never be read as this
    run's answer.
    """
    return {
        "check": CHECK_NAME,
        "exit_code": 2,
        "passed": False,
        "verdict": "the check could not be made, which is not a pass",
        "cutoff": None if cutoff is None else cutoff.isoformat(),
        "error": str(error),
        "not_covered": OUT_OF_SCOPE,
    }


# ------------------------------------------------------------------ the audit


def audit_look_ahead(
    registry: EconomicSeriesRegistry,
    indicators: Sequence[BinaryIndicator],
    source: SeriesCache,
    settings: RunSettings,
    schedule_for: Callable[[SeriesCache], ForecastSchedule],
    working_directory: Path,
    cutoff: date | None = None,
) -> LookAheadAudit:
    """Perturb what was unavailable at the cutoff, run twice, and compare exactly.

    ``source`` is only read. ``schedule_for`` computes the configured schedule
    from a cache, and is handed the unperturbed copy, never ``source``: the
    schedule search assembles panels, and a panel whose vintage is missing is
    fetched and written. ``working_directory`` receives both copies and both
    fitted-model stores, and must start empty of them.
    """
    if not settings.select_state_count_on_a_burn_in_window:
        raise LookAheadAuditError(
            "this configuration reads its state count off the full-sample sweep in "
            "selected_model.json, which is the look-ahead ADR 0008 closed (D2). This audit "
            "certifies configurations that choose the count on a burn-in window, recomputed in "
            "each run; set select_state_count_on_a_burn_in_window back to True."
        )

    original_series = working_directory / "original" / "series"
    perturbed_series = working_directory / "perturbed" / "series"
    copy_series_cache(source, original_series)

    schedule_cache = series_cache_at(original_series)
    try:
        configured = schedule_for(schedule_cache)
    except LookAheadAuditError:
        raise
    except Exception as error:
        raise LookAheadAuditError(
            f"the configured schedule could not be computed: {type(error).__name__}: {error}"
        ) from error
    if schedule_cache.statistics.misses:
        raise LookAheadAuditError(
            f"computing the schedule needed {schedule_cache.statistics.misses} series the cache "
            "does not hold. Run `forecast fetch-data` for the same --as-of date first."
        )

    chosen = cutoff if cutoff is not None else default_cutoff(configured)
    audited = truncate_schedule(configured, chosen)
    perturbation = copy_series_cache(
        source,
        perturbed_series,
        cutoff=chosen,
        publication_lag_days_by_series=publication_lag_days_by_series(registry),
    )
    logger.info(
        "look_ahead_audit cutoff=%s dates=%d refits=%d",
        chosen,
        len(audited.forecast_dates),
        len(audited.refit_dates),
    )

    original_run, original_results = _run_from_scratch(
        "original",
        registry,
        indicators,
        original_series,
        settings,
        audited,
        working_directory / "original" / "models",
    )
    try:
        perturbed_run, perturbed_results = _run_from_scratch(
            "perturbed",
            registry,
            indicators,
            perturbed_series,
            settings,
            audited,
            working_directory / "perturbed" / "models",
        )
    except LookAheadAuditError as error:
        raise LookAheadAuditError(
            f"{error}. The original run completed on the same schedule, so perturbed data "
            f"reached a computation on or before {chosen.isoformat()}: treat this as a "
            "look-ahead until shown otherwise."
        ) from error

    moved = compare_runs(original_results, perturbed_results)
    return LookAheadAudit(
        cutoff=chosen,
        cutoff_chosen_by_default=cutoff is None,
        configured_schedule=configured,
        audited_schedule=audited,
        perturbation=perturbation,
        original=original_run,
        perturbed=perturbed_run,
        rows_compared=len(original_results),
        moved=moved,
        configuration_hash=settings.configuration_hash(),
        random_seed=settings.random_seed,
    )
