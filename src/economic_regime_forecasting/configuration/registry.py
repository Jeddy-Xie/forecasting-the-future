"""Load and validate the two registries that declare what this project does.

``economic_series.yaml`` says what is fetched. ``binary_indicators.yaml`` says
what is forecast. Both are read exactly once, here, and turned into frozen
dataclasses so that nothing downstream passes dictionaries around and mistypes a
key. Validation failures raise; a registry that does not parse is not a registry
that half-works.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, Final

import yaml

_REGISTRY_DIRECTORY: Final[Path] = Path(__file__).resolve().parent
ECONOMIC_SERIES_FILE: Final[Path] = _REGISTRY_DIRECTORY / "economic_series.yaml"
BINARY_INDICATORS_FILE: Final[Path] = _REGISTRY_DIRECTORY / "binary_indicators.yaml"

SUPPORTED_SCHEMA_VERSION: Final[int] = 1


class RegistryError(ValueError):
    """A registry file is missing a field, or names something that does not exist."""


class Transform(str, Enum):
    """How a raw series is converted before use.

    ``level`` leaves the series alone. The two year-over-year forms are the
    reason index rebasings do not corrupt the point-in-time work: rescaling a
    whole series by a constant leaves its log differences untouched, so a vintage
    published on a 1967 index base and one published on a 2017 base give the same
    growth rate.
    """

    LEVEL = "level"
    YEAR_OVER_YEAR_LOG_CHANGE = "year_over_year_log_change"
    YEAR_OVER_YEAR_PERCENT_CHANGE = "year_over_year_percent_change"


class ModelDimension(str, Enum):
    """The three axes of the model's observation vector."""

    GROWTH = "growth"
    INFLATION = "inflation"
    RATES = "rates"


class Composition(str, Enum):
    """How an indicator's probability is assembled from a regime path."""

    POINT_IN_TIME = "point_in_time"
    ANY_TIME_WITHIN_HORIZON = "any_time_within_horizon"


class ResolutionRule(str, Enum):
    """The six ways a series becomes a zero or a one.

    Three read a single month at the horizon; three read every month between the
    forecast date and the horizon. The registry pairs each with a composition,
    and :func:`EconomicSeriesRegistry.validate_against` checks the pairing is
    coherent, because a within-horizon rule composed point-in-time is a silent
    and systematic underestimate.
    """

    LEVEL_ABOVE_THRESHOLD_AT_HORIZON = "level_above_threshold_at_horizon"
    LEVEL_ABOVE_THRESHOLD_WITHIN_HORIZON = "level_above_threshold_within_horizon"
    LEVEL_BELOW_THRESHOLD_WITHIN_HORIZON = "level_below_threshold_within_horizon"

    @property
    def reads_whole_path(self) -> bool:
        """True when the rule inspects every month up to the horizon."""
        return self.value.endswith("_within_horizon")

    @property
    def condition_is_above_threshold(self) -> bool:
        """Whether the monthly condition is a value above the threshold or below it.

        Every rule reduces to one monthly condition of one of these two shapes,
        which is what lets a single per-regime rate serve every horizon.
        """
        return "above" in self.value


@dataclass(frozen=True)
class EconomicSeries:
    """One fetched series and the facts the pipeline needs about it."""

    name: str
    series_id: str
    description: str
    role: str
    model_dimension: ModelDimension | None
    frequency: str
    units: str
    transform: Transform
    publication_lag_days: int
    observation_start: date
    is_revised: bool

    @property
    def is_model_input(self) -> bool:
        return self.model_dimension is not None


@dataclass(frozen=True)
class DerivedSeries:
    """A series computed from two fetched ones rather than downloaded."""

    name: str
    description: str
    operation: str
    minuend: str
    subtrahend: str
    units: str


@dataclass(frozen=True)
class IndicatorResolution:
    """How one indicator's realised outcome is read out of history."""

    series: str
    rule: ResolutionRule
    transform: Transform
    threshold: float | None


@dataclass(frozen=True)
class BinaryIndicator:
    """One forecast target."""

    name: str
    question: str
    resolution: IndicatorResolution
    composition: Composition
    horizons_in_years: tuple[int, ...]

    @property
    def horizons_in_months(self) -> tuple[int, ...]:
        return tuple(years * 12 for years in self.horizons_in_years)


@dataclass(frozen=True)
class EconomicSeriesRegistry:
    """Every series, fetched and derived, addressable by name."""

    series: tuple[EconomicSeries, ...]
    derived: tuple[DerivedSeries, ...]

    def __post_init__(self) -> None:
        names = [item.name for item in self.series] + [item.name for item in self.derived]
        duplicates = {name for name in names if names.count(name) > 1}
        if duplicates:
            raise RegistryError(
                f"series names must be unique; these are repeated: {sorted(duplicates)}. "
                "Rename one of them in economic_series.yaml."
            )

    def __getitem__(self, name: str) -> EconomicSeries:
        for item in self.series:
            if item.name == name:
                return item
        raise RegistryError(
            f"no fetched series named {name!r}. Known names: "
            f"{sorted(item.name for item in self.series)}"
        )

    def derived_by_name(self, name: str) -> DerivedSeries | None:
        return next((item for item in self.derived if item.name == name), None)

    def knows(self, name: str) -> bool:
        return any(item.name == name for item in self.series) or (
            self.derived_by_name(name) is not None
        )

    @property
    def model_inputs(self) -> tuple[EconomicSeries, ...]:
        """The three series forming the observation vector, in dimension order."""
        by_dimension = {item.model_dimension: item for item in self.series if item.is_model_input}
        missing = [dimension for dimension in ModelDimension if dimension not in by_dimension]
        if missing:
            raise RegistryError(
                "the observation vector needs exactly one series per dimension; missing "
                f"{[dimension.value for dimension in missing]}. Set model_dimension on a series "
                "in economic_series.yaml."
            )
        return tuple(by_dimension[dimension] for dimension in ModelDimension)

    def validate_against(self, indicators: Sequence[BinaryIndicator]) -> None:
        """Check every indicator names a real series and a coherent rule.

        Raises on the first problem, naming the indicator and what to fix.
        """
        for indicator in indicators:
            if not self.knows(indicator.resolution.series):
                raise RegistryError(
                    f"indicator {indicator.name!r} resolves against unknown series "
                    f"{indicator.resolution.series!r}. Add it to economic_series.yaml or "
                    "correct the name in binary_indicators.yaml."
                )
            rule = indicator.resolution.rule
            if indicator.resolution.threshold is None:
                raise RegistryError(
                    f"indicator {indicator.name!r} uses rule {rule.value!r}, which needs a "
                    "threshold. Add `threshold:` under its resolution block."
                )
            expected = (
                Composition.ANY_TIME_WITHIN_HORIZON
                if rule.reads_whole_path
                else Composition.POINT_IN_TIME
            )
            if indicator.composition is not expected:
                raise RegistryError(
                    f"indicator {indicator.name!r} pairs rule {rule.value!r} with composition "
                    f"{indicator.composition.value!r}, but that rule requires "
                    f"{expected.value!r}. A within-horizon question composed point-in-time "
                    "understates its probability systematically."
                )


def _require(mapping: Mapping[str, Any], key: str, context: str) -> Any:
    if key not in mapping:
        raise RegistryError(f"{context} is missing required field {key!r}")
    return mapping[key]


def _check_schema_version(document: Mapping[str, Any], path: Path) -> None:
    version = document.get("schema_version")
    if version != SUPPORTED_SCHEMA_VERSION:
        raise RegistryError(
            f"{path.name} declares schema_version {version!r}; this code reads version "
            f"{SUPPORTED_SCHEMA_VERSION}. Update the loader or the file."
        )


def load_economic_series_registry(path: Path = ECONOMIC_SERIES_FILE) -> EconomicSeriesRegistry:
    """Read and validate the series registry."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    _check_schema_version(document, path)

    series: list[EconomicSeries] = []
    for entry in _require(document, "observation_series", path.name):
        name = _require(entry, "name", f"{path.name} observation_series entry")
        dimension_value = entry.get("model_dimension")
        series.append(
            EconomicSeries(
                name=name,
                series_id=_require(entry, "series_id", f"series {name!r}"),
                description=_require(entry, "description", f"series {name!r}").strip(),
                role=_require(entry, "role", f"series {name!r}"),
                model_dimension=ModelDimension(dimension_value) if dimension_value else None,
                frequency=_require(entry, "frequency", f"series {name!r}"),
                units=_require(entry, "units", f"series {name!r}"),
                transform=Transform(_require(entry, "transform", f"series {name!r}")),
                publication_lag_days=int(
                    _require(entry, "publication_lag_days", f"series {name!r}")
                ),
                observation_start=_as_date(
                    _require(entry, "observation_start", f"series {name!r}")
                ),
                is_revised=bool(_require(entry, "is_revised", f"series {name!r}")),
            )
        )

    derived: list[DerivedSeries] = []
    for entry in document.get("derived_series") or []:
        name = _require(entry, "name", f"{path.name} derived_series entry")
        operation = _require(entry, "operation", f"derived series {name!r}")
        if operation != "difference":
            raise RegistryError(
                f"derived series {name!r} declares operation {operation!r}; only 'difference' "
                "is implemented. Add the operation to features/transforms.py before using it."
            )
        derived.append(
            DerivedSeries(
                name=name,
                description=_require(entry, "description", f"derived series {name!r}").strip(),
                operation=operation,
                minuend=_require(entry, "minuend", f"derived series {name!r}"),
                subtrahend=_require(entry, "subtrahend", f"derived series {name!r}"),
                units=_require(entry, "units", f"derived series {name!r}"),
            )
        )

    registry = EconomicSeriesRegistry(series=tuple(series), derived=tuple(derived))
    for item in registry.derived:
        for leg in (item.minuend, item.subtrahend):
            if not any(existing.name == leg for existing in registry.series):
                raise RegistryError(
                    f"derived series {item.name!r} references {leg!r}, which is not a fetched "
                    "series in economic_series.yaml."
                )
    return registry


def load_binary_indicators(path: Path = BINARY_INDICATORS_FILE) -> tuple[BinaryIndicator, ...]:
    """Read and validate the indicator registry."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    _check_schema_version(document, path)

    indicators: list[BinaryIndicator] = []
    for entry in _require(document, "indicators", path.name):
        name = _require(entry, "name", f"{path.name} indicators entry")
        resolution = _require(entry, "resolution", f"indicator {name!r}")
        threshold = resolution.get("threshold")
        indicators.append(
            BinaryIndicator(
                name=name,
                question=_require(entry, "question", f"indicator {name!r}").strip(),
                resolution=IndicatorResolution(
                    series=_require(resolution, "series", f"indicator {name!r} resolution"),
                    rule=ResolutionRule(
                        _require(resolution, "rule", f"indicator {name!r} resolution")
                    ),
                    transform=Transform(resolution.get("transform", Transform.LEVEL.value)),
                    threshold=None if threshold is None else float(threshold),
                ),
                composition=Composition(_require(entry, "composition", f"indicator {name!r}")),
                horizons_in_years=tuple(
                    int(years)
                    for years in _require(entry, "horizons_in_years", f"indicator {name!r}")
                ),
            )
        )

    names = [indicator.name for indicator in indicators]
    duplicates = {name for name in names if names.count(name) > 1}
    if duplicates:
        raise RegistryError(f"indicator names must be unique; repeated: {sorted(duplicates)}")
    return tuple(indicators)


def _as_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def load_registries() -> tuple[EconomicSeriesRegistry, tuple[BinaryIndicator, ...]]:
    """Load both registries and cross-validate them. The usual entry point."""
    series_registry = load_economic_series_registry()
    indicators = load_binary_indicators()
    series_registry.validate_against(indicators)
    return series_registry, indicators
