"""A committed record of what a run produced, and the diff that says what moved.

``.cache/`` is git-ignored and rebuilt, so until now there was no output in the
repository to compare a change against. Answering "what did this change move?"
cost a bespoke investigation every time: the unit that closed D2 needed a new
command, a new artifact and a hand-written comparison section, none of which
generalised. This module is the general answer.

    baselines/<name>.json   committed. The run's identity, the three horizon
                            verdicts and the thirty per-indicator metric rows,
                            assembled from artifacts the pipeline already wrote.
                            Small enough for git, rich enough to catch a move.

    baselines/<name>.forecasts.parquet
                            committed beside it. Every forecast the run made --
                            indicator, date, horizon, the model's probability,
                            the climatology's and the outcome -- which is what
                            the paired comparison scores both runs on.

    .cache/models/run_summary.json
                            the same structure, written by the last step of
                            ``forecast check-gates`` from the *same* assembly
                            function, so a baseline and a fresh run can never
                            disagree about their own format.

Nothing here recomputes a number. Every value is read off
``backtest_results.parquet``, ``verdicts.parquet``, ``evaluation_metrics.parquet``,
``burn_in_state_count_choice.json`` or ``backtest_fallback_record.json``, each
written by the run being summarised and never by another command. A baseline that re-derived its own
contents would be measuring this module rather than the pipeline.

**The two traps this is built around.** Both are on the record from the D2 unit
and either one would have made the instrument worthless.

The first is a tolerance that absorbs the difference it exists to detect.
``pandas.testing.assert_frame_equal`` with default arguments passes silently on a
1e-13 difference, which made an acceptance criterion decorative until
``check_exact=True`` was required (ADR 0008). A comparison that looks like
evidence and is not is worse than no comparison.

The second is the equal and opposite one. Fitted models reproduce byte-identically
within one environment and drift at about the thirteenth decimal across a numpy or
BLAS change, so a byte-identity baseline would fail for a reason that is not a
regression, and a check that cries wolf gets switched off.

So a numeric difference is classified into a band rather than reduced to one
boolean, and the categorical fields are never banded at all.

**Two comparisons, for two questions.** ``compare`` asks *did anything move*:
field by field, in bands, with every categorical move listed above every numeric
one. ``compare_paired`` asks *is this run better, or only different*: the change
in the verdict's own mean skill score on the forecasts both runs made, with a
bootstrap interval in which both runs are scored on the same resampled dates.
Aggregate metrics cannot answer the second question, because two runs' separate
intervals overlap for almost any change worth making.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from economic_regime_forecasting import __version__
from economic_regime_forecasting.configuration.run_settings import ARTIFACTS, PROJECT_ROOT
from economic_regime_forecasting.data.cache import ArtifactStore, now_in_utc
from economic_regime_forecasting.evaluation import paired_skill_comparison

BASELINE_DIRECTORY = PROJECT_ROOT / "baselines"
"""Where committed baselines live. Not under ``.cache/``: these are the record a
change is measured against, so they are in git and are never rebuilt."""

FORMAT_VERSION = 1
"""The version of what a baseline holds and how it is laid out.

A serialization change silently invalidates every stored baseline. A renamed
field, a new block, a number written differently or a forecasts file with other
columns shows up either as a wall of differences that are facts about this module
rather than about the run, or -- worse -- as nothing at all. The project's
research ledger adopted the constraint that follows: version the run format in
the manifest. So every baseline and every run summary carries the version it was
written in, and both comparisons refuse a baseline written in any other, naming
the two versions and saying to re-capture.

**The rule.** Bump this, in the same commit, whenever the fields a baseline
records change -- their names, their types, the block they sit in -- or the
columns of the forecasts file do. Do not bump it because a run produces different
numbers; reporting that is what the comparison is for. There is no migration:
re-capturing takes seconds, and a migration is code that runs once and is then
never tested again."""

NUMERICAL_DRIFT_TOLERANCE = 1e-9
"""The boundary between environment drift and a real move, in absolute difference.

Four orders of magnitude above the ~1e-13 drift measured when the same fit is
reproduced across a numpy or BLAS change, and five below any difference
that could matter to a probability, a Brier score or a skill score -- the
smallest quantity in a baseline that a reader would act on is around 1e-4. A
difference larger than this is reported; a difference smaller than it is named
``NUMERICAL`` and is still shown on request, never silently dropped.

It is a module constant on purpose. No command line flag moves it, because a
tolerance a caller can widen after seeing a result is the decorative-tolerance
failure this module exists to avoid."""

IDENTICAL = "IDENTICAL"
"""Bit for bit: the difference is exactly zero."""

NUMERICAL = "NUMERICAL"
"""Non-zero but within ``NUMERICAL_DRIFT_TOLERANCE``: environment drift, not a
regression."""

MOVED = "MOVED"
"""A real change. Every categorical difference lands here whatever its size."""

REMOVED = "REMOVED"
"""Structural: the row or field is in this run and not in the baseline."""

ADDED = "ADDED"
"""Structural: the row or field is in the baseline and not in this run.

Both words are read from the baseline's side, which is the opposite of a source
diff's orientation. A row the baseline does not have was removed from it; a row
only the baseline has was added to it. The orientation is written down because a
reader who guesses will guess the other way."""

BANDS: tuple[str, ...] = (IDENTICAL, NUMERICAL, MOVED, REMOVED, ADDED)

RUN_FIELDS: tuple[str, ...] = (
    "configuration_hash",
    "random_seed",
    "state_count",
    "state_count_chosen_as_of",
    "first_forecast_date",
    "last_forecast_date",
    "forecast_date_count",
    "refit_count",
    "forecast_dates_using_fallback",
)
"""Run identity. Every one of these is compared for exact equality: a run with a
different seed or a different number of forecast dates is a different run, and
saying so in the fourth decimal would be the wrong sentence."""

HORIZON_KEY_FIELDS: tuple[str, ...] = ("horizon_months",)
HORIZON_TEXT_FIELDS: tuple[str, ...] = ("verdict", "failing_gates")
HORIZON_NUMERIC_FIELDS: tuple[str, ...] = (
    "mean_brier_skill_score",
    "skill_lower_bound",
    "skill_upper_bound",
    "effective_independent_observations",
)

INDICATOR_KEY_FIELDS: tuple[str, ...] = ("indicator", "horizon_months")
INDICATOR_TEXT_FIELDS: tuple[str, ...] = ()
INDICATOR_NUMERIC_FIELDS: tuple[str, ...] = (
    "resolved_forecasts",
    "base_rate",
    "brier_score",
    "climatology_brier_score",
    "brier_skill_score",
    "logarithmic_loss",
    "area_under_the_curve",
    "expected_calibration_error",
    "reliability",
    "resolution",
    "mean_distance_to_stationary",
    "mean_effective_sample_size",
)

INFORMATIONAL_KEYS: tuple[str, ...] = ("name", "package_version", "capture")
"""Top-level keys the comparison ignores.

``capture`` holds the wall-clock time and the commit, which say when a baseline
was taken and not what it contains. ``package_version`` is metadata about the
code; the ``configuration_hash`` inside ``run`` is what answers whether two runs
should agree about a number. ``name`` is the file's own label.

``format_version`` is deliberately not among them. It is not compared at all: it
is checked before anything else, and a mismatch stops the comparison."""

FORECAST_KEY_COLUMNS: tuple[str, ...] = ("indicator", "forecast_date", "horizon_months")
"""One forecast. The paired comparison lines two runs up on exactly these."""

FORECAST_COLUMNS: tuple[str, ...] = (
    *FORECAST_KEY_COLUMNS,
    "predicted_probability",
    "climatology_probability",
    "realised_outcome",
    "configuration_hash",
)
"""What ``baselines/<name>.forecasts.parquet`` holds: every backtest forecast,
restricted to what a skill score is computed from, plus the configuration that
made it. The regime distributions and diagnostics are left out; they are most of
the backtest frame's size and none of its score."""


class BaselineError(RuntimeError):
    """A baseline could not be assembled, read, or lined up against a run."""


# --------------------------------------------------------------------- assembly


def _require_table(artifacts: ArtifactStore, name: str, what_to_run: str) -> pd.DataFrame:
    """One artifact, or the sentence that says how to produce it."""
    if not artifacts.has(name):
        raise BaselineError(
            f"{name} is not in {artifacts.directory}, and a baseline is read off the "
            f"artifacts a run already wrote rather than recomputed. Run `{what_to_run}` "
            "first."
        )
    return artifacts.read_table(name)


def _the_one_value(frame: pd.DataFrame, column: str, artifact: str) -> Any:
    """The single distinct value in a column, or a refusal.

    Two values mean the artifact was assembled from more than one run, which has
    no single identity to record. That is a defect in the cache, not something to
    pick a winner from.
    """
    found = sorted({str(value) for value in frame[column]})
    if len(found) != 1:
        raise BaselineError(
            f"{artifact} carries {len(found)} distinct values of {column!r} {found[:4]}, so "
            "it describes more than one run and has no single identity to record. Re-run "
            "`forecast backtest` under one configuration."
        )
    return frame[column].iloc[0]


def _number(value: Any, *, integral: bool) -> float | int | None:
    """A JSON number at full precision, or ``None`` where the metric is undefined.

    ``integral`` comes from the column's dtype rather than from the value, so a
    count stays a count and a rate that happens to land on 0.0 does not silently
    become an integer in one capture and a float in the next.

    ``area_under_the_curve`` is not defined for a horizon whose resolved outcomes
    are all one class, and one of the thirty rows on the live cache is exactly
    that. Writing it as ``NaN`` would produce a file that is not JSON; writing it
    as ``null`` keeps the file readable and lets the comparison say
    ``null -> 0.83`` out loud, which is a real change and is reported as one.
    """
    if value is None or pd.isna(value):
        return None
    return int(value) if integral else float(value)


def _rows(
    frame: pd.DataFrame,
    artifact: str,
    key_fields: Sequence[str],
    text_fields: Sequence[str],
    numeric_fields: Sequence[str],
) -> list[dict[str, Any]]:
    """The declared fields of a table, as plain JSON rows in a fixed order.

    The field list is declared here rather than taken from the table's columns.
    What a baseline holds is the project's statement about what counts as a
    regression, so a column appearing in an artifact must not silently enlarge it;
    a column disappearing must fail loudly, which is what the check below does.
    """
    wanted = [*key_fields, *text_fields, *numeric_fields]
    missing = [name for name in wanted if name not in frame.columns]
    if missing:
        raise BaselineError(
            f"{artifact} has no column(s) {missing}, which a baseline records. The artifact "
            "and this module have drifted apart; fix one to match the other in a commit "
            "that says which and why."
        )

    integral = {name: bool(pd.api.types.is_integer_dtype(frame[name])) for name in numeric_fields}
    rows: list[dict[str, Any]] = []
    for record in frame.to_dict("records"):
        row: dict[str, Any] = {}
        for name in key_fields:
            row[name] = str(record[name]) if name == "indicator" else int(record[name])
        for name in text_fields:
            row[name] = str(record[name])
        for name in numeric_fields:
            row[name] = _number(record[name], integral=integral[name])
        rows.append(row)
    # Sorted on the raw key values, so 12 comes before 120 and 60 after it. A
    # lexicographic sort would put "120" between them, which is deterministic but
    # is not the order a reader of the file expects.
    return sorted(rows, key=lambda item: tuple(item[name] for name in key_fields))


def fallback_record(
    configuration_hash: str, forecast_dates: pd.DatetimeIndex, fallback_dates: Sequence[date]
) -> dict[str, Any]:
    """What a backtest records about its own schedule's vintage policy.

    ``forecast backtest`` writes it beside ``backtest_results.parquet``, from the
    fallback dates it measured over its own schedule when it ran. The schedule's
    identity is recorded with the count so the summary can refuse a record that
    describes some other run.
    """
    return {
        "configuration_hash": configuration_hash,
        "first_forecast_date": forecast_dates[0].date().isoformat(),
        "last_forecast_date": forecast_dates[-1].date().isoformat(),
        "forecast_date_count": len(forecast_dates),
        "forecast_dates_using_fallback": len(fallback_dates),
        "fallback_dates": [item.isoformat() for item in fallback_dates],
    }


def _forecast_dates_using_fallback(
    artifacts: ArtifactStore,
    configuration_hash: str,
    first_forecast_date: str,
    last_forecast_date: str,
    forecast_date_count: int,
) -> int | None:
    """How many forecast dates fed the model revised values, as the run measured it.

    ``forecast backtest`` measures this over its own schedule, with the scan its
    pre-flight uses, and writes ``backtest_fallback_record.json`` beside the
    results. The summary reads that record and nothing else.

    Until 2026-09-15 it borrowed the count from ``variant_comparison.parquet``,
    ``forecast compare-variants``' artifact, looked up by configuration hash.
    Every research arm has a hash of its own and starts from a copy of main's
    cache, so every arm would have found nothing there. That is a ``null`` against
    the baseline's 0, which is a categorical MOVED on run identity in every arm's
    comparison, for a reason unrelated to its idea.

    A cache whose backtest predates the record has none, and the field is
    ``null``: explicitly unknown, never inherited from elsewhere. A ``null`` on
    one side and a number on the other is still reported as ``MOVED``, because a
    run that cannot say how many dates fell back is not the same evidence as one
    that says none did. A record describing another run -- a different
    configuration or schedule -- is refused.
    """
    if not artifacts.has(ARTIFACTS.backtest_fallback_record):
        return None
    record = artifacts.read_json(ARTIFACTS.backtest_fallback_record)
    expected: dict[str, object] = {
        "configuration_hash": configuration_hash,
        "first_forecast_date": first_forecast_date,
        "last_forecast_date": last_forecast_date,
        "forecast_date_count": forecast_date_count,
    }
    recorded = {key: record.get(key) for key in expected}
    if recorded != expected:
        raise BaselineError(
            f"{ARTIFACTS.backtest_fallback_record} describes {recorded}, but "
            f"{ARTIFACTS.backtest_results} is {expected}. The two come from different runs; "
            "re-run `forecast backtest` so the cache describes one rather than choosing."
        )
    return int(str(record["forecast_dates_using_fallback"]))


def _state_count_chosen_as_of(artifacts: ArtifactStore, state_count: int) -> str | None:
    """The date the number of regimes was chosen on, or ``None``.

    ``burn_in_state_count_choice.json`` exists only when a burn-in sweep ran
    before the first forecast date. A run that read the count off the
    full-sample sweep chose it as of today and records no artifact saying so,
    so the field is ``null`` for that configuration.

    The consistency check below compares ``state_count`` (what
    ``backtest_results.parquet`` was actually fitted with) against
    ``state_count_used_for_forecasting`` -- not against the sweep's own
    ``state_count`` field, which is its unconstrained recommendation and may
    legitimately differ from what was used.

    Research arm A2-quadrant-structure-levels
    (proving/experiments/0002-research-slate-2026-09/experiment.json) is why
    that distinction exists: there, the burn-in sweep still runs and still
    recommends its own count (say 6), as evidence for the regimes-exist gate,
    while the number actually used to fit is a pre-registered constant (4).
    ``_state_count_for_the_backtest`` in the command-line interface writes
    both into the one artifact, so a reader still sees the sweep's finding
    (``state_count``) and what was used (``state_count_used_for_forecasting``)
    side by side, and this check verifies the latter rather than silencing
    itself. An artifact written before this field existed has no
    ``state_count_used_for_forecasting``; ``state_count`` was always what was
    used in that case, so it is the fallback.
    """
    if not artifacts.has(ARTIFACTS.burn_in_state_count_choice):
        return None
    choice = artifacts.read_json(ARTIFACTS.burn_in_state_count_choice)
    used_count = int(str(choice.get("state_count_used_for_forecasting", choice["state_count"])))
    if used_count != state_count:
        raise BaselineError(
            f"{ARTIFACTS.burn_in_state_count_choice} says {used_count} regimes were used for "
            f"forecasting but {ARTIFACTS.backtest_results} was run with {state_count}. The two "
            "artifacts come from different runs; re-run `forecast backtest` so the cache "
            "describes one."
        )
    return str(choice["chosen_as_of"])


def assemble_run_summary(artifacts: ArtifactStore) -> dict[str, Any]:
    """The whole comparable body of a run: its identity, verdicts and metrics.

    This is the single assembly function. ``forecast baseline capture`` writes its
    output to ``baselines/<name>.json`` and the last step of
    ``forecast check-gates`` writes it to ``.cache/models/run_summary.json``. One
    implementation means a committed baseline and a fresh run cannot disagree
    about their own format, which was the second half of what D13 asked for.
    """
    results = _require_table(artifacts, ARTIFACTS.backtest_results, "forecast backtest")
    verdicts = _require_table(artifacts, ARTIFACTS.verdicts, "forecast evaluate")
    metrics = _require_table(artifacts, ARTIFACTS.evaluation_metrics, "forecast evaluate")

    configuration_hash = str(
        _the_one_value(results, "configuration_hash", ARTIFACTS.backtest_results)
    )
    state_count = int(_the_one_value(results, "state_count", ARTIFACTS.backtest_results))
    forecast_dates = pd.to_datetime(results["forecast_date"])
    forecast_date_count = int(forecast_dates.nunique())

    run = {
        "configuration_hash": configuration_hash,
        "random_seed": int(_the_one_value(results, "seed", ARTIFACTS.backtest_results)),
        "state_count": state_count,
        "state_count_chosen_as_of": _state_count_chosen_as_of(artifacts, state_count),
        "first_forecast_date": forecast_dates.min().date().isoformat(),
        "last_forecast_date": forecast_dates.max().date().isoformat(),
        "forecast_date_count": forecast_date_count,
        "refit_count": int(pd.to_datetime(results["refit_date"]).nunique()),
        "forecast_dates_using_fallback": _forecast_dates_using_fallback(
            artifacts,
            configuration_hash,
            forecast_dates.min().date().isoformat(),
            forecast_dates.max().date().isoformat(),
            forecast_date_count,
        ),
    }
    if set(run) != set(RUN_FIELDS):  # pragma: no cover - guards a future edit
        raise BaselineError(
            f"the run block holds {sorted(run)} but RUN_FIELDS declares {sorted(RUN_FIELDS)}"
        )

    return {
        "format_version": FORMAT_VERSION,
        "run": run,
        "horizons": _rows(
            verdicts,
            ARTIFACTS.verdicts,
            HORIZON_KEY_FIELDS,
            HORIZON_TEXT_FIELDS,
            HORIZON_NUMERIC_FIELDS,
        ),
        "indicators": _rows(
            metrics,
            ARTIFACTS.evaluation_metrics,
            INDICATOR_KEY_FIELDS,
            INDICATOR_TEXT_FIELDS,
            INDICATOR_NUMERIC_FIELDS,
        ),
    }


def git_commit_of(repository_root: Path = PROJECT_ROOT) -> str | None:
    """The commit ``HEAD`` points at, read from ``.git`` rather than shelled out for.

    Informational only, and ``None`` outside a checkout. Nothing in a comparison
    reads it, so a missing answer costs nothing and is not worth a subprocess.
    """
    head = repository_root / ".git" / "HEAD"
    if not head.is_file():
        return None
    text = head.read_text(encoding="utf-8").strip()
    if not text.startswith("ref:"):
        return text or None
    reference = text.removeprefix("ref:").strip()
    direct = repository_root / ".git" / reference
    if direct.is_file():
        return direct.read_text(encoding="utf-8").strip() or None
    packed = repository_root / ".git" / "packed-refs"
    if packed.is_file():
        for line in packed.read_text(encoding="utf-8").splitlines():
            if line.startswith(("#", "^")):
                continue
            parts = line.split()
            if len(parts) == 2 and parts[1] == reference:
                return parts[0]
    return None


def build_baseline(
    artifacts: ArtifactStore,
    name: str,
    *,
    deterministic: bool = False,
    repository_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    """A baseline document: the comparable body plus what the comparison ignores.

    ``deterministic`` omits the ``capture`` block entirely rather than blanking
    it, so two captures of one run produce byte-identical files and the tests can
    check that with sha256.
    """
    document: dict[str, Any] = {
        "name": name,
        "package_version": __version__,
        **assemble_run_summary(artifacts),
    }
    if not deterministic:
        document["capture"] = {
            "captured_at": now_in_utc().isoformat(),
            "git_commit": git_commit_of(repository_root),
        }
    return document


def as_json_text(document: dict[str, Any]) -> str:
    """Sorted keys, full float precision, one trailing newline.

    ``allow_nan`` is off: a ``NaN`` would produce a file that is not JSON, and the
    assembly converts every undefined metric to ``null`` before it gets here. If
    this raises, the conversion has a hole in it.
    """
    return json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"


def baseline_path(name: str, directory: Path = BASELINE_DIRECTORY) -> Path:
    return directory / f"{name}.json"


def write_baseline(
    document: dict[str, Any],
    name: str,
    directory: Path = BASELINE_DIRECTORY,
    *,
    force: bool = False,
) -> Path:
    """Write ``baselines/<name>.json``, refusing to overwrite one that exists.

    Plain ``json``, not the cache: a baseline is committed, is never keyed by a
    request hash and is never rebuilt, so it is not a cache entry and must not be
    written through one.
    """
    destination = baseline_path(name, directory)
    if destination.exists() and not force:
        raise BaselineError(
            f"{destination} already exists. A baseline is the record a change is measured "
            "against, so overwriting one silently would erase the comparison. Pass --force "
            "if replacing it is the intent, or capture under a different --name."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(as_json_text(document), encoding="utf-8")
    return destination


def read_baseline(name: str, directory: Path = BASELINE_DIRECTORY) -> dict[str, Any]:
    source = baseline_path(name, directory)
    if not source.is_file():
        available = (
            sorted(item.stem for item in directory.glob("*.json")) if directory.is_dir() else []
        )
        raise BaselineError(
            f"no baseline named {name!r} at {source}. "
            + (f"Available: {', '.join(available)}. " if available else "None are committed. ")
            + f"Run `forecast baseline capture --name {name}` to take one from the artifacts "
            "currently in the cache."
        )
    try:
        document: dict[str, Any] = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise BaselineError(
            f"{source} is not readable as JSON: {error}. A baseline is machine-written; a "
            "hand edit is the usual cause."
        ) from error
    return document


def forecasts_path(name: str, directory: Path = BASELINE_DIRECTORY) -> Path:
    return directory / f"{name}.forecasts.parquet"


def forecast_frame(artifacts: ArtifactStore) -> pd.DataFrame:
    """Every forecast in the cache's backtest, restricted to ``FORECAST_COLUMNS``.

    Sorted on the forecast key so two captures of one run write the same rows in
    the same order. Read off ``backtest_results.parquet`` like everything else
    here; nothing is recomputed.
    """
    results = _require_table(artifacts, ARTIFACTS.backtest_results, "forecast backtest")
    missing = [name for name in FORECAST_COLUMNS if name not in results.columns]
    if missing:
        raise BaselineError(
            f"{ARTIFACTS.backtest_results} has no column(s) {missing}, which the forecasts file "
            "records. The artifact and this module have drifted apart; fix one to match the "
            "other, and bump FORMAT_VERSION if it is this module that changes."
        )
    return (
        results.loc[:, list(FORECAST_COLUMNS)]
        .sort_values(list(FORECAST_KEY_COLUMNS), kind="mergesort")
        .reset_index(drop=True)
    )


@dataclass(frozen=True)
class Capture:
    """What ``capture_baseline`` wrote, and where."""

    document: dict[str, Any]
    forecast_count: int
    summary_path: Path
    forecasts_path: Path


def capture_baseline(
    artifacts: ArtifactStore,
    name: str,
    directory: Path = BASELINE_DIRECTORY,
    *,
    deterministic: bool = False,
    force: bool = False,
    repository_root: Path = PROJECT_ROOT,
) -> Capture:
    """Write ``<name>.json`` and ``<name>.forecasts.parquet`` together, or neither.

    Both destinations are checked before either is written, so a refused capture
    leaves the directory as it found it rather than pairing a new summary with an
    old forecasts file. The forecasts go through ``ArtifactStore`` because it is
    this project's one Parquet writer; they are committed record, not cache.
    """
    document = build_baseline(
        artifacts, name, deterministic=deterministic, repository_root=repository_root
    )
    forecasts = forecast_frame(artifacts)
    forecasts_destination = forecasts_path(name, directory)
    if forecasts_destination.exists() and not force:
        raise BaselineError(
            f"{forecasts_destination} already exists. A baseline is the record a change is "
            "measured against, so overwriting one silently would erase the comparison. Pass "
            "--force if replacing it is the intent, or capture under a different --name."
        )
    summary_destination = write_baseline(document, name, directory, force=force)
    ArtifactStore(directory).write_table(forecasts_destination.name, forecasts)
    return Capture(
        document=document,
        forecast_count=len(forecasts),
        summary_path=summary_destination,
        forecasts_path=forecasts_destination,
    )


def read_baseline_forecasts(name: str, directory: Path = BASELINE_DIRECTORY) -> pd.DataFrame:
    source = forecasts_path(name, directory)
    if not source.is_file():
        raise BaselineError(
            f"baseline {name!r} has no forecasts file at {source}, so there is nothing to pair "
            f"this run's forecasts with. Run `forecast baseline capture --name {name} --force` "
            "on the commit the baseline describes, which writes both files together."
        )
    return ArtifactStore(directory).read_table(source.name)


def list_baselines(directory: Path = BASELINE_DIRECTORY) -> list[dict[str, Any]]:
    """Every committed baseline with its run identity, newest name order."""
    if not directory.is_dir():
        return []
    listing: list[dict[str, Any]] = []
    for source in sorted(directory.glob("*.json")):
        document = read_baseline(source.stem, directory)
        run = document.get("run", {})
        capture = document.get("capture", {})
        listing.append(
            {
                "name": document.get("name", source.stem),
                "format_version": document.get("format_version"),
                "configuration_hash": run.get("configuration_hash"),
                "state_count": run.get("state_count"),
                "first_forecast_date": run.get("first_forecast_date"),
                "last_forecast_date": run.get("last_forecast_date"),
                "forecast_date_count": run.get("forecast_date_count"),
                "horizon_count": len(document.get("horizons", [])),
                "indicator_row_count": len(document.get("indicators", [])),
                "captured_at": capture.get("captured_at"),
                "git_commit": capture.get("git_commit"),
            }
        )
    return listing


# ------------------------------------------------------------------ comparison


@dataclass(frozen=True)
class FieldDifference:
    """One field, on one row, and how far apart the two sides are."""

    section: str
    row: str
    field: str
    baseline: Any
    current: Any
    band: str
    difference: float | None
    categorical: bool = False
    """Compared for exact equality: a verdict, the failing gates, or a field of
    the run's identity. Never banded, and when MOVED, always read first."""

    @property
    def leads(self) -> bool:
        """A categorical field that moved. These head the report."""
        return self.categorical and self.band == MOVED

    @property
    def sort_key(self) -> tuple[bool, bool, float]:
        """Categorical moves first, then largest absolute difference.

        A verdict that flipped sits above every number that moved, whatever the
        numbers' size. The likeliest way this report fails is not a wrong band but
        a reader who scans forty routine numeric deltas, says "looks fine" to the
        lot, and never reaches the one line that changed what ships.

        Within the numbers, anything unquantifiable comes first: a metric that went
        from ``null`` to a number has no size but is at least as worth reading as
        the biggest move that has one."""
        if self.difference is None:
            return (not self.leads, False, 0.0)
        return (not self.leads, True, -abs(self.difference))


@dataclass(frozen=True)
class StructuralDifference:
    """A row or a field present on one side and absent from the other.

    Never tolerated and never quietly skipped: a comparison that drops the rows it
    cannot align is the same failure as a tolerance that absorbs everything, and
    it is the failure that looks most like a pass.
    """

    section: str
    row: str
    band: str
    detail: str


@dataclass(frozen=True)
class Comparison:
    """What a baseline and a run disagree about, and whether it is a regression."""

    baseline_name: str
    baseline_run: dict[str, Any]
    current_run: dict[str, Any]
    fields: tuple[FieldDifference, ...]
    structural: tuple[StructuralDifference, ...]

    def in_band(self, band: str) -> list[FieldDifference]:
        return [item for item in self.fields if item.band == band]

    @property
    def categorical_moves(self) -> list[FieldDifference]:
        """Verdicts, failing gates and run-identity fields that changed."""
        return [item for item in self.fields if item.leads]

    @property
    def counts(self) -> dict[str, int]:
        counted = {band: 0 for band in BANDS}
        for item in self.fields:
            counted[item.band] += 1
        for entry in self.structural:
            counted[entry.band] += 1
        return counted

    @property
    def exit_code(self) -> int:
        """0 nothing moved, 1 something did, 2 the comparison could not be made.

        A structural mismatch outranks a moved number because it means the two
        sides are not describing the same thing, and a skill score compared across
        a different set of indicators is not a comparison at all.
        """
        if self.structural:
            return 2
        return 1 if self.in_band(MOVED) else 0

    def as_dictionary(self) -> dict[str, Any]:
        """The whole comparison, for the branch runner rather than for a reader."""
        return {
            "baseline_name": self.baseline_name,
            "baseline_run": self.baseline_run,
            "current_run": self.current_run,
            "format_version": FORMAT_VERSION,
            "numerical_drift_tolerance": NUMERICAL_DRIFT_TOLERANCE,
            "counts": self.counts,
            "categorical_moved": len(self.categorical_moves),
            "exit_code": self.exit_code,
            "structural": [
                {
                    "section": entry.section,
                    "row": entry.row,
                    "band": entry.band,
                    "detail": entry.detail,
                }
                for entry in self.structural
            ],
            "fields": [
                {
                    "section": item.section,
                    "row": item.row,
                    "field": item.field,
                    "baseline": item.baseline,
                    "current": item.current,
                    "band": item.band,
                    "difference": item.difference,
                    "categorical": item.categorical,
                }
                for item in sorted(self.fields, key=lambda item: item.sort_key)
            ],
        }

    def describe(self, bands: Sequence[str] = (MOVED,)) -> str:
        """The reader's view: what changed, largest first, and a count of the rest."""
        shown = {band.upper() for band in bands}
        counts = self.counts
        header = [
            f"baseline {self.baseline_name!r} "
            f"({self.baseline_run.get('configuration_hash')}, "
            f"{self.baseline_run.get('forecast_date_count')} forecast dates from "
            f"{self.baseline_run.get('first_forecast_date')}) against this run "
            f"({self.current_run.get('configuration_hash')}, "
            f"{self.current_run.get('forecast_date_count')} from "
            f"{self.current_run.get('first_forecast_date')})",
            "  ".join(f"{counts[band]} {band}" for band in BANDS),
            f"a difference is NUMERICAL up to {NUMERICAL_DRIFT_TOLERANCE:g} in absolute value "
            "and MOVED above it; every categorical difference is MOVED",
        ]
        leading = sorted(
            (item for item in self.fields if item.leads and item.band in shown),
            key=lambda item: (item.section, item.row, item.field),
        )
        if leading:
            header.append(
                f"{len(leading)} of the MOVED are categorical -- a verdict, a failing gate or the "
                "run's identity -- and are listed first"
            )

        lines: list[str] = []
        if self.structural:
            lines.append("")
            lines.append("structural — the two sides do not describe the same rows:")
            for entry in sorted(self.structural, key=lambda item: (item.section, item.row)):
                lines.append(f"  {entry.band:<8} {entry.section}  {entry.row}  {entry.detail}")

        selected = [item for item in self.fields if item.band in shown]
        if leading:
            lines.append("")
            lines.append("categorical fields that moved -- read these first:")
            lines.append(_field_table(leading))
        following = sorted(
            (item for item in selected if not item.leads), key=lambda item: item.sort_key
        )
        if following:
            lines.append("")
            lines.append(
                "numeric fields, largest difference first:"
                if not any(item.categorical for item in following)
                else "every other field shown, largest difference first:"
            )
            lines.append(_field_table(following))
        hidden = len(self.fields) - len(selected)
        if hidden:
            lines.append("")
            lines.append(
                f"{hidden} further field(s) not shown: "
                + ", ".join(
                    f"{counts[band]} {band}"
                    for band in BANDS[:3]
                    if band not in shown and counts[band]
                )
                + ". Pass --tolerance-band all to see them."
            )
        if not self.structural and not self.in_band(MOVED):
            lines.append("")
            lines.append("nothing moved.")
        return "\n".join([*header, *lines])


def _render(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, float):
        return f"{value:.10g}"
    return str(value)


def _field_table(items: Sequence[FieldDifference]) -> str:
    headings = ("band", "section", "row", "field", "baseline", "this run", "difference")
    rows = [
        (
            item.band,
            item.section,
            item.row,
            item.field,
            _render(item.baseline),
            _render(item.current),
            "" if item.difference is None else f"{item.difference:+.3e}",
        )
        for item in items
    ]
    return _text_table(headings, rows)


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


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def classify(baseline_value: Any, current_value: Any, *, exact: bool) -> tuple[str, float | None]:
    """One field's band, and the signed difference where one exists.

    ``exact`` covers every categorical field and every field in the run block: a
    verdict that changed from SHIP MODEL to SHIP BASE RATE is MOVED, and there is
    no size at which that is drift. A comparison against ``null`` is exact too,
    because a metric that was undefined and now is not has changed even though the
    change has no magnitude.
    """
    if exact or not _is_number(baseline_value) or not _is_number(current_value):
        return (IDENTICAL if baseline_value == current_value else MOVED), None
    difference = float(current_value) - float(baseline_value)
    if difference == 0.0:
        return IDENTICAL, 0.0
    if abs(difference) <= NUMERICAL_DRIFT_TOLERANCE:
        return NUMERICAL, difference
    return MOVED, difference


def _compare_fields(
    section: str,
    row: str,
    baseline_row: dict[str, Any],
    current_row: dict[str, Any],
    exact_fields: Sequence[str],
    fields: list[FieldDifference],
    structural: list[StructuralDifference],
) -> None:
    for name in sorted(set(baseline_row) | set(current_row)):
        if name not in baseline_row:
            structural.append(
                StructuralDifference(
                    section, row, REMOVED, f"field {name!r} is not in the baseline"
                )
            )
            continue
        if name not in current_row:
            structural.append(
                StructuralDifference(section, row, ADDED, f"field {name!r} is not in this run")
            )
            continue
        band, difference = classify(
            baseline_row[name], current_row[name], exact=name in exact_fields
        )
        fields.append(
            FieldDifference(
                section=section,
                row=row,
                field=name,
                baseline=baseline_row[name],
                current=current_row[name],
                band=band,
                difference=difference,
                categorical=name in exact_fields,
            )
        )


def _keyed(
    rows: Sequence[dict[str, Any]], key_fields: Sequence[str], section: str
) -> dict[tuple[str, ...], dict[str, Any]]:
    keyed: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        missing = [name for name in key_fields if name not in row]
        if missing:
            raise BaselineError(
                f"a {section} row has no {missing} to line it up by: {row}. Without a key "
                "there is no honest way to say which row it should be compared against."
            )
        key = tuple(str(row[name]) for name in key_fields)
        if key in keyed:
            raise BaselineError(
                f"{section} carries two rows keyed {key}, so a comparison would have to "
                "choose between them. Re-capture the baseline."
            )
        keyed[key] = row
    return keyed


def _compare_section(
    section: str,
    baseline_rows: Sequence[dict[str, Any]],
    current_rows: Sequence[dict[str, Any]],
    key_fields: Sequence[str],
    exact_fields: Sequence[str],
    fields: list[FieldDifference],
    structural: list[StructuralDifference],
) -> None:
    baseline_keyed = _keyed(baseline_rows, key_fields, f"the baseline's {section}")
    current_keyed = _keyed(current_rows, key_fields, f"this run's {section}")

    for key in sorted(set(baseline_keyed) | set(current_keyed)):
        label = " @ ".join(key)
        if key not in baseline_keyed:
            structural.append(
                StructuralDifference(
                    section, label, REMOVED, "this run has this row and the baseline does not"
                )
            )
            continue
        if key not in current_keyed:
            structural.append(
                StructuralDifference(
                    section, label, ADDED, "the baseline has this row and this run does not"
                )
            )
            continue
        _compare_fields(
            section,
            label,
            {name: value for name, value in baseline_keyed[key].items() if name not in key_fields},
            {name: value for name, value in current_keyed[key].items() if name not in key_fields},
            exact_fields,
            fields,
            structural,
        )


def check_format_version(
    baseline: dict[str, Any], current: dict[str, Any], name: str = "baseline"
) -> None:
    """Refuse a comparison across format versions, naming both, saying what to do.

    A baseline with no ``format_version`` at all predates versioning and is
    refused the same way: it cannot be known to be in the current format.
    """
    baseline_version = baseline.get("format_version")
    current_version = current.get("format_version")
    if baseline_version == current_version:
        return
    written = (
        f"format version {baseline_version}"
        if baseline_version is not None
        else "no format version (it predates versioning)"
    )
    raise BaselineError(
        f"baseline {name!r} was written in {written}, and this run is in format version "
        f"{current_version}. A comparison across formats reports the format change rather "
        f"than the run, so it is refused. Re-capture the baseline with `forecast baseline "
        f"capture --name {name} --force` on the commit it describes, then compare again."
    )


def compare(
    baseline: dict[str, Any], current: dict[str, Any], name: str = "baseline"
) -> Comparison:
    """Line a baseline up against a run summary and classify every difference.

    ``current`` is whatever ``assemble_run_summary`` produced for the artifacts in
    hand, so the two sides are the same shape by construction and any structural
    difference is a real one: an edited baseline, a changed indicator set, or a
    run that visited different horizons.

    A baseline written in another ``FORMAT_VERSION`` is refused before anything
    is compared, because every difference found would be about the format.
    """
    check_format_version(baseline, current, name)
    fields: list[FieldDifference] = []
    structural: list[StructuralDifference] = []

    for section in ("run", "horizons", "indicators"):
        if section not in baseline:
            structural.append(
                StructuralDifference(
                    section, "", REMOVED, "the baseline has no such block; it may predate it"
                )
            )
        if section not in current:  # pragma: no cover - assemble always writes all three
            structural.append(
                StructuralDifference(section, "", ADDED, "this run produced no such block")
            )

    baseline_run = dict(baseline.get("run", {}))
    current_run = dict(current.get("run", {}))
    _compare_fields("run", "", baseline_run, current_run, RUN_FIELDS, fields, structural)
    _compare_section(
        "horizons",
        baseline.get("horizons", []),
        current.get("horizons", []),
        HORIZON_KEY_FIELDS,
        HORIZON_TEXT_FIELDS,
        fields,
        structural,
    )
    _compare_section(
        "indicators",
        baseline.get("indicators", []),
        current.get("indicators", []),
        INDICATOR_KEY_FIELDS,
        INDICATOR_TEXT_FIELDS,
        fields,
        structural,
    )
    return Comparison(
        baseline_name=name,
        baseline_run=baseline_run,
        current_run=current_run,
        fields=tuple(fields),
        structural=tuple(structural),
    )


def describe_listing(
    listing: Sequence[dict[str, Any]], directory: Path = BASELINE_DIRECTORY
) -> str:
    """Every committed baseline, one row each."""
    if not listing:
        return (
            f"no baselines under {directory}. Run `forecast baseline capture "
            "--name main` after a passing `forecast check-gates`."
        )
    headings = (
        "name",
        "format",
        "configuration",
        "states",
        "dates",
        "from",
        "to",
        "captured",
        "commit",
    )
    rows = [
        (
            str(item["name"]),
            str(item["format_version"] or "none"),
            str(item["configuration_hash"]),
            str(item["state_count"]),
            str(item["forecast_date_count"]),
            str(item["first_forecast_date"]),
            str(item["last_forecast_date"]),
            str(item["captured_at"] or "not recorded")[:19],
            str(item["git_commit"] or "not recorded")[:12],
        )
        for item in listing
    ]
    return _text_table(headings, rows)


# ------------------------------------------------------------ paired comparison


PAIRED_STATISTIC = (
    "the pre-registered verdict's mean Brier skill score over its fixed set of scoreable "
    "indicators, this run minus the baseline, on the resolved forecasts both runs made"
)


@dataclass(frozen=True)
class PairedHorizon:
    """One horizon of a paired comparison: the key arithmetic, then the result."""

    horizon_months: int
    rows_in_both: int
    rows_only_in_baseline: int
    rows_only_in_this_run: int
    forecast_dates_in_both: int
    outcome_disagreements: int
    result: paired_skill_comparison.PairedSkillDifference | None
    baseline_indicators_scored: tuple[str, ...]
    this_run_indicators_scored: tuple[str, ...]
    note: str

    def as_dictionary(self) -> dict[str, Any]:
        result = self.result
        interval = None if result is None else result.interval
        return {
            "horizon_months": self.horizon_months,
            "rows_in_both": self.rows_in_both,
            "rows_only_in_baseline": self.rows_only_in_baseline,
            "rows_only_in_this_run": self.rows_only_in_this_run,
            "forecast_dates_in_both": self.forecast_dates_in_both,
            "outcome_disagreements": self.outcome_disagreements,
            "baseline_mean_brier_skill_score": (
                None if result is None else result.baseline_mean_skill
            ),
            "current_mean_brier_skill_score": None if result is None else result.current_mean_skill,
            "difference": None if result is None else result.difference,
            "intervals": [
                {
                    "confidence_level": item.confidence_level,
                    "lower_bound": item.lower_bound,
                    "upper_bound": item.upper_bound,
                }
                for item in (() if result is None else result.intervals)
            ],
            "block_length": None if interval is None else interval.block_length,
            "resamples_used": None if interval is None else interval.resamples,
            "effective_independent_observations": (
                None if interval is None else interval.effective_independent_sample_size
            ),
            "baseline_indicators_scored": list(self.baseline_indicators_scored),
            "this_run_indicators_scored": list(self.this_run_indicators_scored),
            "note": self.note,
        }


@dataclass(frozen=True)
class PairedIndicator:
    """One indicator at one horizon: each side's skill score and the difference.

    A point estimate only. Ten indicators at three horizons would be thirty
    intervals, those at the long horizons each resting on two or three independent
    observations; printed side by side they invite reading the widest swing as a
    finding. The interval belongs to the pooled statistic.
    """

    indicator: str
    horizon_months: int
    rows_in_both: int
    baseline_brier_skill_score: float | None
    current_brier_skill_score: float | None

    @property
    def difference(self) -> float | None:
        if self.baseline_brier_skill_score is None or self.current_brier_skill_score is None:
            return None
        return self.current_brier_skill_score - self.baseline_brier_skill_score

    def as_dictionary(self) -> dict[str, Any]:
        return {
            "indicator": self.indicator,
            "horizon_months": self.horizon_months,
            "rows_in_both": self.rows_in_both,
            "baseline_brier_skill_score": self.baseline_brier_skill_score,
            "current_brier_skill_score": self.current_brier_skill_score,
            "difference": self.difference,
        }


@dataclass(frozen=True)
class PairedComparison:
    """Is this run better than the baseline, or only different?"""

    baseline_name: str
    baseline_run: dict[str, Any]
    current_run: dict[str, Any]
    random_seed: int
    resamples: int
    confidence_levels: tuple[float, ...]
    """Ascending. Each horizon carries one interval per level, all read off the
    same resamples, so a higher level's interval always contains a lower one's."""
    horizons: tuple[PairedHorizon, ...]
    indicators: tuple[PairedIndicator, ...]
    only_in_baseline_forecast_dates: tuple[str, str] | None
    only_in_this_run_forecast_dates: tuple[str, str] | None

    @property
    def rows_in_both(self) -> int:
        return sum(item.rows_in_both for item in self.horizons)

    @property
    def rows_only_in_baseline(self) -> int:
        return sum(item.rows_only_in_baseline for item in self.horizons)

    @property
    def rows_only_in_this_run(self) -> int:
        return sum(item.rows_only_in_this_run for item in self.horizons)

    @property
    def same_forecasts(self) -> bool:
        return self.rows_only_in_baseline == 0 and self.rows_only_in_this_run == 0

    @property
    def exit_code(self) -> int:
        """0 when every horizon was measured, 2 when one could not be.

        There is no 1. This comparison measures and does not judge: whether a
        difference is a regression or the improvement a branch was built for is a
        question for the reader and the decision rule. ``compare`` is the check
        that says whether anything moved at all.
        """
        return 2 if any(item.result is None for item in self.horizons) else 0

    def as_dictionary(self) -> dict[str, Any]:
        """The whole paired comparison, for the branch runner."""
        return {
            "baseline_name": self.baseline_name,
            "format_version": FORMAT_VERSION,
            "baseline_run": self.baseline_run,
            "current_run": self.current_run,
            "statistic": PAIRED_STATISTIC,
            "bootstrap": {
                "method": "moving block",
                "resampled_unit": "forecast date, with every indicator on it kept together",
                "block_length": "the horizon in months",
                "paired": "one draw of forecast dates per resample, applied to both runs",
                "resamples": self.resamples,
                "random_seed": self.random_seed,
                "confidence_levels": list(self.confidence_levels),
                "levels_share_resamples": True,
            },
            "keys": {
                "compared_on": (
                    "the intersection of resolved (indicator, forecast_date, horizon_months)"
                ),
                "rows_in_both": self.rows_in_both,
                "rows_only_in_baseline": self.rows_only_in_baseline,
                "rows_only_in_this_run": self.rows_only_in_this_run,
                "same_forecasts": self.same_forecasts,
                "only_in_baseline_forecast_dates": self.only_in_baseline_forecast_dates,
                "only_in_this_run_forecast_dates": self.only_in_this_run_forecast_dates,
            },
            "exit_code": self.exit_code,
            "horizons": [item.as_dictionary() for item in self.horizons],
            "indicators": [item.as_dictionary() for item in self.indicators],
        }

    def describe(self) -> str:
        """The reader's view: the key arithmetic, one row per horizon, then indicators."""
        labels = [_percent(level) for level in self.confidence_levels]
        lines = [
            f"paired comparison against baseline {self.baseline_name!r} "
            f"({self.baseline_run.get('configuration_hash')}, "
            f"{self.baseline_run.get('forecast_date_count')} forecast dates from "
            f"{self.baseline_run.get('first_forecast_date')}) and this run "
            f"({self.current_run.get('configuration_hash')}, "
            f"{self.current_run.get('forecast_date_count')} from "
            f"{self.current_run.get('first_forecast_date')})",
            f"statistic: {PAIRED_STATISTIC}",
            f"interval: {' and '.join(labels)} moving-block bootstrap of forecast dates, blocks "
            "as long as the horizon in months, every indicator on a date kept together, one draw "
            "of dates per resample applied to both runs and read at every level; "
            f"{self.resamples} resamples, seed {self.random_seed}",
            "",
            f"resolved forecasts (indicator, forecast date, horizon): {self.rows_in_both} in both, "
            f"{self.rows_only_in_baseline} only in the baseline, {self.rows_only_in_this_run} "
            "only in this run",
        ]
        if self.same_forecasts:
            lines.append(
                "the two runs resolved the same forecasts, so each side's skill below is exactly "
                "what its own verdict reports"
            )
        else:
            lines.append(
                "the two runs do not cover the same forecasts. Every number below is on the "
                f"{self.rows_in_both} both resolved -- the intersection -- and never on either "
                "run's full set"
            )
            for label, span in (
                ("only in the baseline", self.only_in_baseline_forecast_dates),
                ("only in this run", self.only_in_this_run_forecast_dates),
            ):
                if span is not None:
                    lines.append(f"  {label}: forecast dates {span[0]} to {span[1]}")
        disagreements = sum(item.outcome_disagreements for item in self.horizons)
        if disagreements:
            lines.append(
                f"{disagreements} shared forecast(s) resolved to a different outcome in each run; "
                "each side is scored against its own"
            )

        rows: list[tuple[str, ...]] = []
        notes: list[str] = []
        for item in self.horizons:
            result = item.result
            interval = None if result is None else result.interval
            rows.append(
                (
                    f"{item.horizon_months} months",
                    str(item.rows_in_both),
                    str(item.rows_only_in_baseline),
                    str(item.rows_only_in_this_run),
                    _signed(None if result is None else result.baseline_mean_skill),
                    _signed(None if result is None else result.current_mean_skill),
                    _signed(None if result is None else result.difference),
                    *_interval_cells(result, len(self.confidence_levels)),
                    "n/a"
                    if interval is None
                    else f"{interval.effective_independent_sample_size:.1f}",
                    "n/a" if interval is None else str(interval.resamples),
                )
            )
            if result is None or interval is None:
                notes.append(f"at {item.horizon_months} months: {item.note}")
            if item.baseline_indicators_scored != item.this_run_indicators_scored:
                notes.append(
                    f"at {item.horizon_months} months the two verdicts score different "
                    f"indicators, so each mean is over its own set: the baseline "
                    f"{list(item.baseline_indicators_scored)}, this run "
                    f"{list(item.this_run_indicators_scored)}"
                )
        lines.append("")
        lines.append(
            _text_table(
                (
                    "horizon",
                    "in both",
                    "only baseline",
                    "only this run",
                    "baseline skill",
                    "this run skill",
                    "difference",
                    *(f"{label} interval" for label in labels),
                    "independent obs",
                    "resamples",
                ),
                rows,
            )
        )
        if notes:
            lines.append("")
            lines.extend(notes)

        horizons = [item.horizon_months for item in self.horizons]
        cells: dict[str, dict[int, str]] = {}
        for entry in self.indicators:
            if entry.rows_in_both == 0:
                cell = "not shared"
            elif entry.difference is None:
                cell = "undefined"
            else:
                cell = f"{entry.difference:+.4f}"
            cells.setdefault(entry.indicator, {})[entry.horizon_months] = cell
        lines.append("")
        lines.append(
            "brier skill score by indicator, this run minus the baseline (point estimates; "
            "the interval belongs to the mean above):"
        )
        lines.append(
            _text_table(
                ("indicator", *(f"{horizon} months" for horizon in horizons)),
                [
                    (indicator, *(by_horizon.get(horizon, "absent") for horizon in horizons))
                    for indicator, by_horizon in sorted(cells.items())
                ],
            )
        )
        return "\n".join(lines)


def _signed(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.4f}"


def _percent(level: float) -> str:
    """A confidence level as a reader should see it: 0.9 is 90%, and 1 - 0.10/6 is
    98.3333%, never rounded to a neighbour it could be mistaken for."""
    return f"{level * 100:.6g}%"


def _interval_cells(
    result: paired_skill_comparison.PairedSkillDifference | None, level_count: int
) -> list[str]:
    if result is None or not result.intervals:
        return ["n/a"] * level_count
    return [f"[{item.lower_bound:+.4f}, {item.upper_bound:+.4f}]" for item in result.intervals]


def _resolved_forecasts(frame: pd.DataFrame, document: dict[str, Any], side: str) -> pd.DataFrame:
    """One side's resolved forecasts, indexed by the forecast key.

    Resolved means what the verdict means by it: a realised outcome and a
    climatology benchmark both present. The forecasts must come from the run the
    summary beside them describes, which the configuration hash checks; a
    forecasts file paired with some other run's summary would make every number
    below it describe neither.
    """
    missing = [name for name in FORECAST_COLUMNS if name not in frame.columns]
    if missing:
        raise BaselineError(
            f"{side}'s forecasts have no column(s) {missing}. Re-capture the baseline so the "
            "forecasts file is in the current format."
        )
    recorded = document.get("run", {}).get("configuration_hash")
    found = sorted({str(value) for value in frame["configuration_hash"]})
    if found != [str(recorded)]:
        raise BaselineError(
            f"{side}'s forecasts carry configuration {found} but its summary records "
            f"{recorded}, so the two files do not describe the same run. Re-capture the "
            "baseline, or re-run `forecast check-gates`, so that they do."
        )
    resolved = frame.dropna(subset=["realised_outcome", "climatology_probability"]).assign(
        forecast_date=lambda table: pd.to_datetime(table["forecast_date"]),
        horizon_months=lambda table: table["horizon_months"].astype("int64"),
    )
    duplicated = resolved.duplicated(list(FORECAST_KEY_COLUMNS))
    if duplicated.any():
        raise BaselineError(
            f"{side} carries {int(duplicated.sum())} forecast(s) keyed twice by "
            f"{list(FORECAST_KEY_COLUMNS)}, so a pairing would have to choose between them."
        )
    return resolved.set_index(list(FORECAST_KEY_COLUMNS)).sort_index()


def _at_horizon(resolved: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """One horizon's forecasts, indexed by (indicator, forecast date)."""
    return resolved[resolved.index.get_level_values("horizon_months") == horizon].droplevel(
        "horizon_months"
    )


def _matrices(
    shared: pd.DataFrame, dates: Sequence[pd.Timestamp], names: Sequence[str]
) -> paired_skill_comparison.ForecastMatrices:
    """Date-by-indicator matrices, laid out exactly as the verdict lays them out:
    dates ascending, indicators in name order."""

    def wide(column: str) -> Any:
        return (
            shared[column]
            .unstack("indicator")
            .reindex(index=list(dates), columns=list(names))
            .to_numpy(dtype="float64")
        )

    return paired_skill_comparison.ForecastMatrices(
        predicted=wide("predicted_probability"),
        realised=wide("realised_outcome"),
        climatology=wide("climatology_probability"),
    )


def _recorded_mean_skill(document: dict[str, Any], horizon: int) -> Any:
    for row in document.get("horizons", []):
        if row.get("horizon_months") == horizon:
            return row.get("mean_brier_skill_score")
    return None


def _require_agreement_with_own_verdicts(
    baseline: dict[str, Any],
    current: dict[str, Any],
    horizon: int,
    result: paired_skill_comparison.PairedSkillDifference,
) -> None:
    """When both runs resolved the same forecasts, each side's mean skill must be
    exactly what its own verdict recorded. Checked on every paired comparison,
    not only in the tests: a mismatch means a forecasts file and the summary
    beside it do not describe one run, and every number would then be suspect."""
    for side, document, computed in (
        ("the baseline", baseline, result.baseline_mean_skill),
        ("this run", current, result.current_mean_skill),
    ):
        recorded = _recorded_mean_skill(document, horizon)
        if recorded != computed:
            raise BaselineError(
                f"at the {horizon} month horizon the paired statistic gives {side} a mean skill "
                f"score of {computed!r}, but {side}'s own verdict recorded {recorded!r} on the "
                "same forecasts. Its forecasts and its summary do not describe one run: re-run "
                "`forecast evaluate` if it is this run, or re-capture if it is the baseline."
            )


def _date_span(dates: Sequence[pd.Timestamp]) -> tuple[str, str] | None:
    if not dates:
        return None
    return (min(dates).date().isoformat(), max(dates).date().isoformat())


def compare_paired(
    baseline: dict[str, Any],
    baseline_forecasts: pd.DataFrame,
    current: dict[str, Any],
    current_forecasts: pd.DataFrame,
    *,
    random_seed: int,
    resamples: int,
    confidence_levels: Sequence[float],
    name: str = "baseline",
) -> PairedComparison:
    """This run's skill minus the baseline's, per horizon, on the forecasts both made.

    Every resolved (indicator, forecast date, horizon) key is counted into one of
    three bins -- in both, only in the baseline, only in this run -- and the
    statistic is computed on the first bin alone. Runs with different start dates
    are therefore compared on their overlap, and the output says so; nothing is
    dropped without being counted.

    ``confidence_levels`` may name several levels -- a nominal one and a
    family-wise one, say -- and every horizon then carries one interval per level,
    all read off one set of resamples.
    """
    check_format_version(baseline, current, name)
    try:
        levels = paired_skill_comparison.confidence_levels_in_order(confidence_levels)
    except paired_skill_comparison.PairedComparisonError as error:
        raise BaselineError(str(error)) from error
    baseline_resolved = _resolved_forecasts(baseline_forecasts, baseline, "the baseline")
    current_resolved = _resolved_forecasts(current_forecasts, current, "this run")

    horizons: list[PairedHorizon] = []
    indicators: list[PairedIndicator] = []
    only_in_baseline_dates: list[pd.Timestamp] = []
    only_in_this_run_dates: list[pd.Timestamp] = []

    every_horizon = sorted(
        {int(value) for value in baseline_resolved.index.get_level_values("horizon_months")}
        | {int(value) for value in current_resolved.index.get_level_values("horizon_months")}
    )
    for horizon in every_horizon:
        baseline_at = _at_horizon(baseline_resolved, horizon)
        current_at = _at_horizon(current_resolved, horizon)
        both = baseline_at.index.intersection(current_at.index)
        only_in_baseline = baseline_at.index.difference(current_at.index)
        only_in_this_run = current_at.index.difference(baseline_at.index)
        only_in_baseline_dates.extend(only_in_baseline.get_level_values("forecast_date"))
        only_in_this_run_dates.extend(only_in_this_run.get_level_values("forecast_date"))

        shared_baseline = baseline_at.loc[both]
        shared_current = current_at.loc[both]
        dates = sorted(set(both.get_level_values("forecast_date")))
        names = sorted({str(value) for value in both.get_level_values("indicator")})
        disagreements = int(
            (shared_baseline["realised_outcome"] != shared_current["realised_outcome"]).sum()
        )

        result: paired_skill_comparison.PairedSkillDifference | None = None
        baseline_matrices: paired_skill_comparison.ForecastMatrices | None = None
        current_matrices: paired_skill_comparison.ForecastMatrices | None = None
        if len(both) == 0:
            note = "no resolved forecast at this horizon is in both runs, so nothing can be paired"
        else:
            baseline_matrices = _matrices(shared_baseline, dates, names)
            current_matrices = _matrices(shared_current, dates, names)
            try:
                result = paired_skill_comparison.paired_mean_skill_difference(
                    baseline_matrices,
                    current_matrices,
                    block_length=horizon,
                    resamples=resamples,
                    seed=random_seed,
                    confidence_levels=levels,
                )
            except paired_skill_comparison.PairedComparisonError as error:
                note = str(error)
            else:
                note = result.interval_note
                if len(only_in_baseline) == 0 and len(only_in_this_run) == 0:
                    _require_agreement_with_own_verdicts(baseline, current, horizon, result)

        horizons.append(
            PairedHorizon(
                horizon_months=horizon,
                rows_in_both=len(both),
                rows_only_in_baseline=len(only_in_baseline),
                rows_only_in_this_run=len(only_in_this_run),
                forecast_dates_in_both=len(dates),
                outcome_disagreements=disagreements,
                result=result,
                baseline_indicators_scored=(
                    ()
                    if result is None
                    else tuple(names[column] for column in result.baseline_scoreable_columns)
                ),
                this_run_indicators_scored=(
                    ()
                    if result is None
                    else tuple(names[column] for column in result.current_scoreable_columns)
                ),
                note=note,
            )
        )

        shared_counts = both.get_level_values("indicator").value_counts()
        for indicator in sorted(
            {str(value) for value in baseline_at.index.get_level_values("indicator")}
            | {str(value) for value in current_at.index.get_level_values("indicator")}
        ):
            baseline_skill = current_skill = None
            if (
                baseline_matrices is not None
                and current_matrices is not None
                and indicator in names
            ):
                column = names.index(indicator)
                baseline_skill = paired_skill_comparison.indicator_skill(baseline_matrices, column)
                current_skill = paired_skill_comparison.indicator_skill(current_matrices, column)
            indicators.append(
                PairedIndicator(
                    indicator=indicator,
                    horizon_months=horizon,
                    rows_in_both=int(shared_counts.get(indicator, 0)),
                    baseline_brier_skill_score=baseline_skill,
                    current_brier_skill_score=current_skill,
                )
            )

    return PairedComparison(
        baseline_name=name,
        baseline_run=dict(baseline.get("run", {})),
        current_run=dict(current.get("run", {})),
        random_seed=random_seed,
        resamples=resamples,
        confidence_levels=levels,
        horizons=tuple(horizons),
        indicators=tuple(indicators),
        only_in_baseline_forecast_dates=_date_span(only_in_baseline_dates),
        only_in_this_run_forecast_dates=_date_span(only_in_this_run_dates),
    )
