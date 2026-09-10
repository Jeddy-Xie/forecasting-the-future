"""Forecasts made about the actual future, and the scoring of them once it arrives.

The walk-forward backtest scores 19,740 retrodictions. That measures the method
against history. It does not measure this model against the future, and the two
are different claims: a Brier skill score of +0.232 computed over 1971-2026 and
the same number computed forward from 2026 are not the same evidence.

``submission/forecasts.csv`` already holds real claims about 2027, 2031 and 2036.
Nothing scores them, and nothing ever will, because nothing records *when* they
were made or *when* they come due. This module is that record:

    register.jsonl      append-only. One line per forecast, carrying the
                        configuration hash that produced it and the date it
                        resolves. Never rewritten — a forecast that could be
                        edited after the fact is not a forecast.

    resolutions.jsonl   append-only. One line per forecast whose resolution date
                        has passed, with what actually happened and its Brier
                        score against both the model and the climatological
                        base rate that was shipped alongside it.

Resolution reuses ``data.indicator_outcomes.resolve`` — the same rule the
backtest scores against, so a live forecast and a historical one are graded by
identical code. Nothing here is a second implementation of anything.

A forecast registered ``as_of`` a date in the past resolves immediately, which is
how this machinery is exercised before 2027: backdate a registration, resolve it,
and the whole path runs against real outcomes today.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import TypedDict

import numpy as np
import pandas as pd

from economic_regime_forecasting.configuration.registry import (
    BinaryIndicator,
    load_registries,
)
from economic_regime_forecasting.configuration.run_settings import PROJECT_ROOT
from economic_regime_forecasting.data import indicator_outcomes
from economic_regime_forecasting.evaluation import scoring

REGISTER_DIRECTORY = PROJECT_ROOT / "forecasts"
REGISTER_FILE = REGISTER_DIRECTORY / "register.jsonl"
RESOLUTIONS_FILE = REGISTER_DIRECTORY / "resolutions.jsonl"


class HorizonScore(TypedDict):
    """One horizon's live scoring."""

    n: int
    brier: float
    brier_climatology: float
    skill: float


class Scorecard(TypedDict):
    """Live skill so far. `inert` is true below the ten resolved forecasts this
    repository requires before a skill score is allowed to mean anything."""

    n: int
    inert: bool
    brier: float
    brier_climatology: float
    skill: float
    by_horizon: dict[str, HorizonScore]


class ResolutionSummary(TypedDict):
    """What one `forecast resolve` run did."""

    registered: int
    due: int
    resolved_now: int
    pending_data: int
    unknown_indicators: list[str]
    records: list[dict[str, object]]


class RegisterError(ValueError):
    """The register was asked to do something that would corrupt the record."""


@dataclass(frozen=True)
class RegisteredForecast:
    """One probability, one indicator, one horizon, and when it comes due."""

    indicator: str
    question: str
    horizon_years: int
    probability: float
    source: str
    model_probability: float
    climatological_base_rate: float
    data_as_of: str
    made_on: str
    resolves_on: str
    configuration_hash: str
    package_version: str

    @property
    def key(self) -> tuple[str, int, str, str]:
        """Identity of a claim: this indicator, this horizon, this run."""
        return (self.indicator, self.horizon_years, self.data_as_of, self.configuration_hash)

    @property
    def resolution_date(self) -> date:
        return date.fromisoformat(self.resolves_on)

    @property
    def forecast_date(self) -> date:
        return date.fromisoformat(self.data_as_of)


def _add_years(start: date, years: int) -> date:
    """The same calendar day, ``years`` later. February 29 lands on the 28th."""
    try:
        return start.replace(year=start.year + years)
    except ValueError:
        return start.replace(year=start.year + years, day=28)


def read_register(path: Path = REGISTER_FILE) -> list[RegisteredForecast]:
    if not path.exists():
        return []
    entries: list[RegisteredForecast] = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entries.append(RegisteredForecast(**json.loads(line)))
        except (json.JSONDecodeError, TypeError) as error:
            raise RegisterError(
                f"{path}:{number} is not a forecast record: {error}. The register is "
                "append-only and machine-written; a hand edit is the usual cause."
            ) from error
    return entries


def read_resolutions(path: Path = RESOLUTIONS_FILE) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _append(path: Path, records: Iterable[dict[str, object]]) -> int:
    """Append records, creating nothing when there are none.

    An empty ledger and an absent one say different things, and only the absent
    one is honest about a run that resolved nothing.
    """
    pending = list(records)
    if not pending:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        for record in pending:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    return len(pending)


def forecasts_from_submission(
    submission_csv: Path,
    manifest_json: Path,
    made_on: date,
) -> Iterator[RegisteredForecast]:
    """Read what `forecast submit` wrote and turn it into dated claims."""
    if not submission_csv.exists():
        raise RegisterError(
            f"no submission at {submission_csv}. Run `forecast submit` first — the "
            "register records what was shipped, it does not produce forecasts."
        )
    if not manifest_json.exists():
        raise RegisterError(
            f"no manifest at {manifest_json}. The manifest carries the configuration "
            "hash and the data as-of date, without which a forecast cannot be tied "
            "to the code that produced it."
        )

    manifest = json.loads(manifest_json.read_text())
    for field in ("configuration_hash", "data_as_of", "package_version"):
        if not manifest.get(field):
            raise RegisterError(f"manifest is missing {field!r}; refusing to register.")

    data_as_of = date.fromisoformat(str(manifest["data_as_of"]))
    table = pd.read_csv(submission_csv)

    for record in table.to_dict("records"):
        horizon_years = int(record["horizon_years"])
        yield RegisteredForecast(
            indicator=str(record["indicator"]),
            question=str(record["question"]),
            horizon_years=horizon_years,
            probability=float(record["probability"]),
            source=str(record["source"]),
            model_probability=float(record["model_probability"]),
            climatological_base_rate=float(record["climatological_base_rate"]),
            data_as_of=data_as_of.isoformat(),
            made_on=made_on.isoformat(),
            resolves_on=_add_years(data_as_of, horizon_years).isoformat(),
            configuration_hash=str(manifest["configuration_hash"]),
            package_version=str(manifest["package_version"]),
        )


def register(
    submission_csv: Path,
    manifest_json: Path,
    made_on: date,
    register_file: Path = REGISTER_FILE,
) -> tuple[int, int]:
    """Append every forecast not already recorded. Returns (written, skipped).

    Re-registering the same run is a no-op rather than an error: the operator
    who runs `forecast submit && forecast register` twice has made no claim
    twice. A *different* configuration hash for the same indicator and horizon
    is a new claim and is appended alongside the old one — the record keeps both,
    because which one you believed at the time is exactly what is being tested.
    """
    existing = {entry.key for entry in read_register(register_file)}
    written, skipped = [], 0
    for forecast in forecasts_from_submission(submission_csv, manifest_json, made_on):
        if forecast.key in existing:
            skipped += 1
            continue
        existing.add(forecast.key)
        written.append(asdict(forecast))
    return _append(register_file, written), skipped


# ---------------------------------------------------------------- resolution


def _indicator_by_name(indicators: Iterable[BinaryIndicator]) -> dict[str, BinaryIndicator]:
    return {indicator.name: indicator for indicator in indicators}


def due(entries: Iterable[RegisteredForecast], today: date) -> list[RegisteredForecast]:
    return [entry for entry in entries if entry.resolution_date <= today]


def resolve(
    series_by_name: dict[str, pd.Series],
    today: date,
    register_file: Path = REGISTER_FILE,
    resolutions_file: Path = RESOLUTIONS_FILE,
) -> ResolutionSummary:
    """Score every forecast that has come due and is not already resolved.

    A forecast whose date has passed but whose outcome the data cannot yet
    settle — the series is not published that far forward — is reported as
    pending, never as a miss. Silence about an unresolvable forecast would be a
    silent fallback, which this repository does not do.
    """
    entries = read_register(register_file)
    already = {
        (r["indicator"], r["horizon_years"], r["data_as_of"], r["configuration_hash"])
        for r in read_resolutions(resolutions_file)
    }
    _series_registry, indicators = load_registries()
    by_name = _indicator_by_name(indicators)

    resolved, pending, unknown = [], 0, []
    for entry in due(entries, today):
        if entry.key in already:
            continue
        indicator = by_name.get(entry.indicator)
        if indicator is None:
            unknown.append(entry.indicator)
            continue
        source_name = indicator.resolution.series
        if source_name not in series_by_name:
            raise RegisterError(
                f"forecast for {entry.indicator!r} needs series {source_name!r}, which "
                "was not loaded. Run `forecast fetch-data` first."
            )
        outcomes = indicator_outcomes.resolve(
            indicator, series_by_name[source_name], entry.horizon_years * 12
        ).outcomes
        stamp = pd.Timestamp(entry.forecast_date).to_period("M").to_timestamp()
        realised = outcomes.get(stamp, np.nan)
        if realised is None or (isinstance(realised, float) and np.isnan(realised)):
            pending += 1
            continue
        realised = float(realised)
        resolved.append(
            {
                "indicator": entry.indicator,
                "horizon_years": entry.horizon_years,
                "data_as_of": entry.data_as_of,
                "configuration_hash": entry.configuration_hash,
                "resolves_on": entry.resolves_on,
                "resolved_on": today.isoformat(),
                "outcome": realised,
                "probability": entry.probability,
                "climatological_base_rate": entry.climatological_base_rate,
                "source": entry.source,
                "brier": round((entry.probability - realised) ** 2, 6),
                "brier_climatology": round((entry.climatological_base_rate - realised) ** 2, 6),
            }
        )

    written = _append(resolutions_file, resolved)
    return ResolutionSummary(
        registered=len(entries),
        due=len(due(entries, today)),
        resolved_now=written,
        pending_data=pending,
        unknown_indicators=sorted(set(unknown)),
        records=resolved,
    )


def scorecard(resolutions_file: Path = RESOLUTIONS_FILE) -> Scorecard:
    """Live skill against the climatology that shipped beside each forecast.

    Below ten resolved forecasts the numbers are printed and the inference is
    refused. A skill score on three observations is a number, not evidence, and
    the register exists to stop exactly that kind of claim being made.
    """
    records = read_resolutions(resolutions_file)
    if not records:
        return Scorecard(
            n=0,
            inert=True,
            brier=float("nan"),
            brier_climatology=float("nan"),
            skill=float("nan"),
            by_horizon={},
        )

    predicted = np.array([r["probability"] for r in records], dtype=float)
    reference = (
        np.array([r["climatological_base_rate"] for r in records], dtype=float)
        if "climatological_base_rate" in records[0]
        else None
    )
    realised = np.array([r["outcome"] for r in records], dtype=float)
    brier = float(np.mean([r["brier"] for r in records]))
    brier_climatology = float(np.mean([r["brier_climatology"] for r in records]))

    by_horizon: dict[str, HorizonScore] = {}
    for horizon in sorted({int(r["horizon_years"]) for r in records}):  # type: ignore[call-overload]
        subset = [r for r in records if r["horizon_years"] == horizon]
        model = float(np.mean([r["brier"] for r in subset]))
        climate = float(np.mean([r["brier_climatology"] for r in subset]))
        by_horizon[str(horizon)] = HorizonScore(
            n=len(subset),
            brier=round(model, 6),
            brier_climatology=round(climate, 6),
            skill=round(1.0 - model / climate, 4) if climate > 0 else float("nan"),
        )

    if reference is not None and reference.size == predicted.size:
        overall_skill = scoring.brier_skill_score(predicted, realised, reference)
    else:
        overall_skill = 1.0 - brier / brier_climatology if brier_climatology > 0 else float("nan")

    return Scorecard(
        n=len(records),
        inert=len(records) < 10,
        brier=round(brier, 6),
        brier_climatology=round(brier_climatology, 6),
        skill=round(float(overall_skill), 4),
        by_horizon=by_horizon,
    )
