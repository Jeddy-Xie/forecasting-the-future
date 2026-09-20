"""`forecast artifacts` is the index D10 says the pipeline never had.

The command's whole value is that a reader can trust what it says: that a file
listed as written exists, that one listed as missing really is missing, and that
the command named beside each file is the command that actually writes it. The
last of those is the one worth pinning, because the mapping is hand-written and
nothing else would notice it drifting from the call sites.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from economic_regime_forecasting import command_line_interface as interface
from economic_regime_forecasting.configuration.registry import load_registries
from economic_regime_forecasting.configuration.run_settings import (
    ARTIFACTS,
    CacheLayout,
    RunSettings,
)
from economic_regime_forecasting.data.cache import ArtifactStore, SeriesCache


@pytest.fixture
def workspace(tmp_path: Path) -> interface.Workspace:
    settings = RunSettings(cache=CacheLayout(tmp_path / "cache"))
    settings.cache.create_directories()
    registry, indicators = load_registries()
    return interface.Workspace(
        registry=registry,
        indicators=indicators,
        cache=SeriesCache(settings.cache.raw, settings.cache.vintage),
        artifacts=ArtifactStore(settings.cache.models),
        settings=settings,
    )


def test_every_named_artifact_is_attributed_to_a_command() -> None:
    """The mapping is hand-written, so it is checked against the names it describes.

    A name in `ArtifactNames` with no entry here would be listed by the command with
    a blank writer, and a name here that no longer exists would be listed forever as
    missing. Both are silent, so both are asserted.
    """
    declared = {
        value
        for field, value in vars(ARTIFACTS).items()
        if isinstance(value, str) and not field.startswith("_")
    }
    declared |= {
        getattr(ARTIFACTS, name)
        for name in dir(ARTIFACTS)
        if not name.startswith("_") and isinstance(getattr(ARTIFACTS, name), str)
    }
    assert declared, "no artifact names were discovered"
    assert set(interface.WRITTEN_BY) == declared, (
        "the artifact-to-command map and ArtifactNames disagree. Difference: "
        f"{declared.symmetric_difference(set(interface.WRITTEN_BY))}"
    )


def test_a_file_that_was_never_written_says_so(workspace, capsys) -> None:  # type: ignore[no-untyped-def]
    assert interface.artifacts(workspace, date(2026, 9, 21)) == 0
    printed = capsys.readouterr().out
    assert "not written" in printed
    assert ARTIFACTS.backtest_results in printed


def test_a_written_file_is_listed_with_its_size_and_its_command(workspace, capsys) -> None:  # type: ignore[no-untyped-def]
    """The row a reader actually uses: the file is there, and this is what made it."""
    workspace.artifacts.write_table(
        ARTIFACTS.backtest_results, pd.DataFrame({"indicator": ["x"], "probability": [0.5]})
    )
    assert interface.artifacts(workspace, date(2026, 9, 21)) == 0

    printed = capsys.readouterr().out
    row = next(line for line in printed.splitlines() if line.startswith(ARTIFACTS.backtest_results))
    assert "not written" not in row
    assert "backtest" in row, "the row must name the command that writes it"


def test_the_command_is_registered_and_dispatched() -> None:
    """A function nothing routes to is not a command. Both halves are pinned."""
    parser = interface.build_parser()
    parsed = parser.parse_args(["artifacts"])
    assert parsed.command == "artifacts"
