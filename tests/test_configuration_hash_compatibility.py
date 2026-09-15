"""The digest that ties every result to the configuration that produced it.

Adding the two look-ahead switches to `RunSettings` must not change the digest
of the configuration that is already on the record: `submission/manifest.json`,
thirty entries in `forecasts/register.jsonl` and fifty-six cached model files all
carry `9f95b12dba40d138`, and none of the numbers they describe moved. The
omission map in `run_settings.py` is what makes that true, and it is also the
single riskiest line in this change: if it ever omitted a field *unconditionally*
rather than only at that field's shipped value, two genuinely different runs
could claim one identity, and the "one configuration produced this run" check in
gate four would be defeated silently. Every test below is aimed at that map.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json

from economic_regime_forecasting.configuration.run_settings import (
    DEFAULT_RUN_SETTINGS,
    SETTINGS_OMITTED_FROM_THE_HASH_WHEN_THEY_HOLD_THE_SHIPPED_VALUE,
    CacheLayout,
    RunSettings,
)

SHIPPED_HASH = "9f95b12dba40d138"
OMISSION_MAP = SETTINGS_OMITTED_FROM_THE_HASH_WHEN_THEY_HOLD_THE_SHIPPED_VALUE


def test_the_shipped_configuration_hashes_to_the_recorded_digest() -> None:
    """AC1. The literal on the record must still come out of the computation."""
    shipped = RunSettings(
        select_state_count_on_a_burn_in_window=False,
        start_walk_forward_when_every_input_is_point_in_time=False,
        # Research arm A4's switch defaults on only on its own branch; the shipped
        # run had one chain, so it is named at that value here like the other two.
        separate_chains_for_growth_and_for_inflation_with_rates=False,
    )
    assert shipped.configuration_hash() == SHIPPED_HASH


def test_the_four_combinations_of_both_switches_give_four_distinct_hashes() -> None:
    """AC2. Four cells, four identities -- the 2x2's result files must be
    self-identifying, and `gate_four_backtest` must be able to tell them apart."""
    hashes = {
        RunSettings(
            select_state_count_on_a_burn_in_window=select_on_burn_in,
            start_walk_forward_when_every_input_is_point_in_time=start_honest,
        ).configuration_hash()
        for select_on_burn_in in (True, False)
        for start_honest in (True, False)
    }
    assert len(hashes) == 4


def test_the_default_settings_hash_is_not_the_shipped_hash() -> None:
    """AC2. `DEFAULT_RUN_SETTINGS` is the honest configuration, so it must not
    quietly collide with the record the shipped run left behind."""
    assert DEFAULT_RUN_SETTINGS.configuration_hash() != SHIPPED_HASH


def test_an_unconditional_omission_would_let_two_different_runs_share_one_hash() -> None:
    """The riskiest possible defect in the omission map, made executable.

    Each key in the map must be left out of the digest only when it holds its
    *shipped* value -- never regardless of value. Holding all other fields fixed
    and flipping one mapped field between its shipped value and its opposite must
    always change the hash. If it ever did not, the two settings objects below
    would be genuinely different runs (one honest on this dimension, one not)
    claiming the identical `configuration_hash`, which is exactly what would
    defeat gate four's "one configuration produced this run" check.
    """
    for key, shipped_value in OMISSION_MAP.items():
        assert isinstance(shipped_value, bool), key
        shipped = dataclasses.replace(DEFAULT_RUN_SETTINGS, **{key: shipped_value})
        opposite = dataclasses.replace(DEFAULT_RUN_SETTINGS, **{key: not shipped_value})
        assert shipped.configuration_hash() != opposite.configuration_hash(), (
            f"{key} at its shipped value ({shipped_value}) and at the opposite value produced "
            "the same configuration_hash. The omission map is being applied regardless of the "
            "field's value, which would let two genuinely different runs claim one identity."
        )


def test_a_field_at_its_shipped_value_hashes_identically_to_a_payload_missing_it_entirely() -> None:
    """The omission rule, stated once in `configuration_hash()`'s docstring, made
    into an executable invariant: a future field added to the map cannot silently
    shift a digest already on the record, because this test recomputes the digest
    by hand with the field dropped and requires the two to agree.
    """
    for key, shipped_value in OMISSION_MAP.items():
        settings = dataclasses.replace(DEFAULT_RUN_SETTINGS, **{key: shipped_value})
        payload_missing_the_key = {
            field_name: list(value) if isinstance(value, tuple) else value
            for field_name, value in settings.__dict__.items()
            if field_name not in ("cache", key)
        }
        encoded = json.dumps(payload_missing_the_key, sort_keys=True, separators=(",", ":"))
        expected = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
        assert settings.configuration_hash() == expected, key


def test_the_hash_is_a_pure_function_of_the_non_cache_fields(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Where the cache lives must never change what a run's numbers mean."""
    one = dataclasses.replace(DEFAULT_RUN_SETTINGS, cache=CacheLayout(tmp_path / "one"))
    other = dataclasses.replace(DEFAULT_RUN_SETTINGS, cache=CacheLayout(tmp_path / "two"))
    assert one.configuration_hash() == other.configuration_hash()


def test_the_omission_map_holds_only_the_two_documented_switches() -> None:
    """A guard against a third field being added to the map silently: the map's
    docstring says every entry is permanent and append-only, so its current
    membership is worth pinning even though this test must be revisited (by a
    reviewed, additive change, never a silent edit) the day a legitimate third
    entry is added."""
    assert set(SETTINGS_OMITTED_FROM_THE_HASH_WHEN_THEY_HOLD_THE_SHIPPED_VALUE) == {
        "select_state_count_on_a_burn_in_window",
        "start_walk_forward_when_every_input_is_point_in_time",
        # Research arm A4, experiment 0002: False is main's single chain.
        "separate_chains_for_growth_and_for_inflation_with_rates",
    }
