"""The one place this project writes fetched or derived data to disk.

Every cache entry is addressed by a content hash of the request that produced it
-- the source, the series identifier, the transform and the vintage date -- and
is stored as a Parquet file beside a JSON sidecar recording where the bytes came
from and when. Reading an entry re-checks the sidecar against the request being
made, so a cache hit is provably an answer to the same question and not a
coincidence of file names.

Nothing else in the project opens a data file. If you find yourself reaching for
``read_parquet`` somewhere else, the seam is in the wrong place.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

OBSERVATION_DATE_COLUMN = "observation_date"
VALUE_COLUMN = "value"


class CacheError(RuntimeError):
    """A cache entry is unreadable, or does not answer the request that found it."""


@dataclass(frozen=True)
class SeriesRequest:
    """The identity of one fetch. Two equal requests must return equal data.

    ``vintage_date`` of ``None`` means the most recent data the service has. Any
    other value means the series exactly as it stood on that date, which is a
    different question with a different answer and therefore a different key.
    """

    source: str
    series_id: str
    transform: str
    vintage_date: date | None

    def as_dictionary(self) -> dict[str, str | None]:
        return {
            "source": self.source,
            "series_id": self.series_id,
            "transform": self.transform,
            "vintage_date": self.vintage_date.isoformat() if self.vintage_date else None,
        }

    @property
    def cache_key(self) -> str:
        """Stable digest of the four identifying fields.

        Canonical JSON with sorted keys, so the digest does not depend on field
        order, dictionary iteration order or the Python version.
        """
        encoded = json.dumps(self.as_dictionary(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @property
    def is_point_in_time(self) -> bool:
        return self.vintage_date is not None

    def describe(self) -> str:
        vintage = self.vintage_date.isoformat() if self.vintage_date else "latest"
        return f"{self.series_id} ({self.transform}, vintage {vintage})"


@dataclass(frozen=True)
class SeriesSnapshot:
    """Observations plus everything needed to explain where they came from."""

    request: SeriesRequest
    observations: pd.Series
    """Indexed by observation date, named after the series identifier."""

    source_url: str
    units: str
    retrieved_at: datetime
    payload_digest: str
    """Digest of the raw response text, so an identical refetch is detectable."""

    @property
    def observation_start(self) -> date | None:
        return None if self.observations.empty else self.observations.index[0].date()

    @property
    def observation_end(self) -> date | None:
        return None if self.observations.empty else self.observations.index[-1].date()

    def sidecar(self) -> dict[str, object]:
        return {
            "cache_key": self.request.cache_key,
            "request": self.request.as_dictionary(),
            "series_id": self.request.series_id,
            "source_url": self.source_url,
            "units": self.units,
            "retrieved_at": self.retrieved_at.isoformat(),
            "payload_digest": self.payload_digest,
            "observation_start": self.observation_start.isoformat()
            if self.observation_start
            else None,
            "observation_end": self.observation_end.isoformat() if self.observation_end else None,
            "observation_count": int(self.observations.size),
            "missing_value_count": int(self.observations.isna().sum()),
        }


@dataclass
class CacheStatistics:
    """Hit and miss counters. The data audit gate asserts a second run is all hits."""

    hits: int = 0
    misses: int = 0
    writes: int = 0

    @property
    def lookups(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        return 0.0 if self.lookups == 0 else self.hits / self.lookups

    def summary(self) -> str:
        return (
            f"{self.hits} hit(s), {self.misses} miss(es), {self.writes} write(s); "
            f"hit rate {self.hit_rate:.0%}"
        )


class SeriesCache:
    """Content-addressed storage for economic series.

    Latest-vintage entries and point-in-time entries live in separate directories
    so that a glance at the cache tells you which discipline produced a file.
    """

    def __init__(self, latest_directory: Path, vintage_directory: Path) -> None:
        self._latest_directory = latest_directory
        self._vintage_directory = vintage_directory
        self.statistics = CacheStatistics()

    def _directory_for(self, request: SeriesRequest) -> Path:
        return self._vintage_directory if request.is_point_in_time else self._latest_directory

    def _paths_for(self, request: SeriesRequest) -> tuple[Path, Path]:
        directory = self._directory_for(request)
        stem = f"{request.series_id}__{request.cache_key[:16]}"
        return directory / f"{stem}.parquet", directory / f"{stem}.json"

    def contains(self, request: SeriesRequest) -> bool:
        data_path, sidecar_path = self._paths_for(request)
        return data_path.is_file() and sidecar_path.is_file()

    def read(self, request: SeriesRequest) -> SeriesSnapshot:
        """Load a cached entry, proving it answers this exact request."""
        data_path, sidecar_path = self._paths_for(request)
        if not (data_path.is_file() and sidecar_path.is_file()):
            raise CacheError(
                f"no cache entry for {request.describe()}. Run `forecast fetch-data` first."
            )

        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        if sidecar.get("cache_key") != request.cache_key:
            raise CacheError(
                f"cache entry at {data_path.name} records key {sidecar.get('cache_key')!r} but "
                f"was found under key {request.cache_key!r}. Delete the file and refetch."
            )
        if sidecar.get("request") != request.as_dictionary():
            raise CacheError(
                f"cache entry at {data_path.name} answers {sidecar.get('request')!r}, not "
                f"{request.as_dictionary()!r}. Delete the file and refetch."
            )

        frame = pd.read_parquet(data_path)
        observations = pd.Series(
            frame[VALUE_COLUMN].to_numpy(),
            index=pd.DatetimeIndex(frame[OBSERVATION_DATE_COLUMN], name=OBSERVATION_DATE_COLUMN),
            name=request.series_id,
            dtype="float64",
        )
        return SeriesSnapshot(
            request=request,
            observations=observations,
            source_url=sidecar["source_url"],
            units=sidecar["units"],
            retrieved_at=datetime.fromisoformat(sidecar["retrieved_at"]),
            payload_digest=sidecar["payload_digest"],
        )

    def write(self, snapshot: SeriesSnapshot) -> None:
        """Persist an entry. Raw responses are immutable once written."""
        data_path, sidecar_path = self._paths_for(snapshot.request)
        data_path.parent.mkdir(parents=True, exist_ok=True)

        frame = pd.DataFrame(
            {
                OBSERVATION_DATE_COLUMN: snapshot.observations.index,
                VALUE_COLUMN: snapshot.observations.to_numpy(dtype="float64"),
            }
        )
        frame.to_parquet(data_path, index=False)
        sidecar_path.write_text(
            json.dumps(snapshot.sidecar(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        self.statistics.writes += 1
        logger.info(
            "cache_write series=%s vintage=%s rows=%d",
            snapshot.request.series_id,
            snapshot.request.vintage_date,
            snapshot.observations.size,
        )

    def get_or_fetch(
        self,
        request: SeriesRequest,
        fetch: Callable[[SeriesRequest], SeriesSnapshot],
    ) -> SeriesSnapshot:
        """Return the cached entry, or fetch and store it.

        This is the only path by which network data enters the project.
        """
        if self.contains(request):
            self.statistics.hits += 1
            return self.read(request)
        self.statistics.misses += 1
        snapshot = fetch(request)
        if snapshot.request != request:
            raise CacheError(
                f"fetcher returned data for {snapshot.request.describe()} when asked for "
                f"{request.describe()}"
            )
        self.write(snapshot)
        return snapshot

    def entries(self) -> list[dict[str, object]]:
        """Every sidecar on disk, for the audit and the run manifest."""
        found: list[dict[str, object]] = []
        for directory in (self._latest_directory, self._vintage_directory):
            if directory.is_dir():
                for sidecar_path in sorted(directory.glob("*.json")):
                    found.append(json.loads(sidecar_path.read_text(encoding="utf-8")))
        return found


@dataclass
class ArtifactStore:
    """Where fitted models and backtest tables are written.

    Kept alongside the series cache so that all derived state lives under one
    root and one ``rm -rf .cache`` restores a clean machine.
    """

    directory: Path
    written: list[Path] = field(default_factory=list)

    def path(self, name: str) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        return self.directory / name

    def write_table(self, name: str, frame: pd.DataFrame) -> Path:
        destination = self.path(name)
        frame.to_parquet(destination, index=False)
        self.written.append(destination)
        return destination

    def read_table(self, name: str) -> pd.DataFrame:
        destination = self.path(name)
        if not destination.is_file():
            raise CacheError(
                f"no artifact named {name!r} under {self.directory}. Produce it first."
            )
        return pd.read_parquet(destination)

    def write_json(self, name: str, payload: dict[str, object]) -> Path:
        destination = self.path(name)
        destination.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )
        self.written.append(destination)
        return destination

    def read_json(self, name: str) -> dict[str, object]:
        destination = self.path(name)
        if not destination.is_file():
            raise CacheError(
                f"no artifact named {name!r} under {self.directory}. Produce it first."
            )
        loaded: dict[str, object] = json.loads(destination.read_text(encoding="utf-8"))
        return loaded

    def has(self, name: str) -> bool:
        return (self.directory / name).is_file()


def digest_of(text: str) -> str:
    """Digest of a raw response body, recorded so refetches are comparable."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_in_utc() -> datetime:
    return datetime.now(tz=UTC)
