"""The registries are the project's contract with itself.

These tests pin the guarantees the rest of the code assumes without rechecking:
the shipped files load, names are unique, the observation vector has exactly one
series per dimension, and an indicator cannot silently pair a within-horizon
question with a point-in-time composition.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from economic_regime_forecasting.configuration import registry as registry_module
from economic_regime_forecasting.configuration.registry import (
    Composition,
    RegistryError,
    ResolutionRule,
    load_binary_indicators,
    load_economic_series_registry,
    load_registries,
)


def test_shipped_registries_load_and_cross_validate() -> None:
    series_registry, indicators = load_registries()
    assert len(series_registry.series) >= 3
    assert len(indicators) == 10


def test_project_forecasts_exactly_ten_indicators_at_three_horizons() -> None:
    _, indicators = load_registries()
    assert len(indicators) == 10
    for indicator in indicators:
        assert indicator.horizons_in_years == (1, 5, 10)
        assert indicator.horizons_in_months == (12, 60, 120)


def test_both_composition_paths_carry_real_weight() -> None:
    """A registry that is all point-in-time would never exercise path integration."""
    _, indicators = load_registries()
    compositions = [indicator.composition for indicator in indicators]
    assert compositions.count(Composition.POINT_IN_TIME) >= 3
    assert compositions.count(Composition.ANY_TIME_WITHIN_HORIZON) >= 3


def test_observation_vector_has_exactly_one_series_per_dimension() -> None:
    series_registry, _ = load_registries()
    inputs = series_registry.model_inputs
    assert len(inputs) == 3
    assert [item.model_dimension.value for item in inputs] == ["growth", "inflation", "rates"]


def test_every_indicator_names_a_series_the_registry_knows() -> None:
    series_registry, indicators = load_registries()
    for indicator in indicators:
        assert series_registry.knows(indicator.resolution.series), indicator.name


def test_within_horizon_rule_must_be_composed_over_the_whole_path(tmp_path: Path) -> None:
    """The pairing check exists because getting it wrong is silent and systematic."""
    document = yaml.safe_load(registry_module.BINARY_INDICATORS_FILE.read_text())
    entry = document["indicators"][0]
    assert ResolutionRule(entry["resolution"]["rule"]).reads_whole_path
    entry["composition"] = Composition.POINT_IN_TIME.value
    broken = tmp_path / "broken_indicators.yaml"
    broken.write_text(yaml.safe_dump(document))

    series_registry = load_economic_series_registry()
    indicators = load_binary_indicators(broken)
    with pytest.raises(RegistryError, match="understates its probability"):
        series_registry.validate_against(indicators)


def test_threshold_is_required_by_the_rules_that_use_one(tmp_path: Path) -> None:
    document = yaml.safe_load(registry_module.BINARY_INDICATORS_FILE.read_text())
    needing = next(
        entry
        for entry in document["indicators"]
        if entry["resolution"]["rule"] == ResolutionRule.LEVEL_ABOVE_THRESHOLD_AT_HORIZON.value
    )
    needing["resolution"].pop("threshold")
    broken = tmp_path / "no_threshold.yaml"
    broken.write_text(yaml.safe_dump(document))

    series_registry = load_economic_series_registry()
    with pytest.raises(RegistryError, match="needs a threshold"):
        series_registry.validate_against(load_binary_indicators(broken))


def test_unknown_series_in_an_indicator_is_rejected_by_name(tmp_path: Path) -> None:
    document = yaml.safe_load(registry_module.BINARY_INDICATORS_FILE.read_text())
    document["indicators"][0]["resolution"]["series"] = "series_that_does_not_exist"
    broken = tmp_path / "unknown_series.yaml"
    broken.write_text(yaml.safe_dump(document))

    series_registry = load_economic_series_registry()
    with pytest.raises(RegistryError, match="series_that_does_not_exist"):
        series_registry.validate_against(load_binary_indicators(broken))


def test_a_schema_version_the_loader_does_not_understand_is_refused(tmp_path: Path) -> None:
    document = yaml.safe_load(registry_module.ECONOMIC_SERIES_FILE.read_text())
    document["schema_version"] = 99
    future = tmp_path / "future_schema.yaml"
    future.write_text(yaml.safe_dump(document))
    with pytest.raises(RegistryError, match="schema_version"):
        load_economic_series_registry(future)


def test_duplicate_series_names_are_refused(tmp_path: Path) -> None:
    document = yaml.safe_load(registry_module.ECONOMIC_SERIES_FILE.read_text())
    document["observation_series"].append(dict(document["observation_series"][0]))
    duplicated = tmp_path / "duplicated.yaml"
    duplicated.write_text(yaml.safe_dump(document))
    with pytest.raises(RegistryError, match="unique"):
        load_economic_series_registry(duplicated)


def test_derived_series_must_reference_fetched_series(tmp_path: Path) -> None:
    document = yaml.safe_load(registry_module.ECONOMIC_SERIES_FILE.read_text())
    document["derived_series"][0]["minuend"] = "not_a_real_series"
    broken = tmp_path / "bad_derived.yaml"
    broken.write_text(yaml.safe_dump(document))
    with pytest.raises(RegistryError, match="not_a_real_series"):
        load_economic_series_registry(broken)
