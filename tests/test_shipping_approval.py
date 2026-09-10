"""`forecast submit` must refuse to ship a configuration nobody approved.

Every case here uses a `tmp_path` repository root -- created with its own
`.git` marker so `freeze_guard.repo_root()` cannot walk out of it and up into
the real checkout, which is exactly the mistake recorded as incident D3 in
`build/changelog.md`. No real token is ever minted and the real `submission/`
directory is never written to; every CLI-level test monkeypatches
`interface.SUBMISSION_DIRECTORY` to a `tmp_path`, the same idiom
`tests/test_submission.py` already uses.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from economic_regime_forecasting import command_line_interface as interface
from economic_regime_forecasting.configuration import shipping_approval
from economic_regime_forecasting.configuration.registry import load_registries
from economic_regime_forecasting.configuration.run_settings import (
    ARTIFACTS,
    PROJECT_ROOT,
    CacheLayout,
    RunSettings,
)
from economic_regime_forecasting.data.cache import ArtifactStore, SeriesCache

FREEZE_GUARD = PROJECT_ROOT / ".claude" / "hooks" / "freeze_guard.py"
APPROVED = shipping_approval.CONFIGURATION_HASH_APPROVED_FOR_SHIPPING
NOT_APPROVED = "0000000000000000"


def _require_freeze_guard() -> None:
    if not FREEZE_GUARD.is_file():
        pytest.skip("`.claude/hooks/freeze_guard.py` is not present on this checkout")


@pytest.fixture
def fake_repo_root(tmp_path: Path) -> Path:
    """A repository root `freeze_guard.repo_root()` cannot escape.

    It walks up from `Path.cwd()` looking for a `.git` directory; without one
    here, it would find the real checkout's and mint a token into the actual
    repository -- the D3 incident. Creating one inside `tmp_path` stops it dead.
    """
    root = tmp_path / "fake_repo"
    root.mkdir()
    (root / ".git").mkdir()
    return root


def _mint_token(
    root: Path,
    reason: str = "test authorisation",
    subject: str = shipping_approval.SHIPPING_SUBJECT,
    by: str = "pytest",
) -> None:
    _require_freeze_guard()
    # A fixed, absolute path to the project's own script with a fixed set of
    # literal arguments -- nothing here comes from untrusted input.
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(FREEZE_GUARD),
            "--thaw",
            reason,
            "--subject",
            subject,
            "--by",
            by,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr


# ------------------------------------------------------------------ AC20


def test_the_approved_hash_matches_the_committed_manifest_it_guards() -> None:
    """AC20. Reads the real, committed `submission/manifest.json` -- read only,
    never written to."""
    manifest = json.loads((PROJECT_ROOT / "submission" / "manifest.json").read_text())
    assert manifest["configuration_hash"] == APPROVED


# ------------------------------------------------------------------ AC17


def test_authorise_shipping_raises_naming_both_hashes_and_both_remedies(
    fake_repo_root: Path,
) -> None:
    destination = fake_repo_root / "submission"
    with pytest.raises(shipping_approval.SubmissionNotApprovedError) as error:
        shipping_approval.authorise_shipping(
            destination=destination,
            repo_root=fake_repo_root,
            live_configuration_hash="live_hash_value",
            producing_configuration_hash="producing_hash_value",
        )
    message = str(error.value)
    assert APPROVED in message
    assert "live_hash_value" in message
    assert "producing_hash_value" in message
    assert "--verify-only" in message
    assert "--thaw" in message
    assert not destination.exists()  # nothing was written before the raise


def test_authorise_shipping_returns_none_when_both_hashes_are_already_approved(
    fake_repo_root: Path,
) -> None:
    result = shipping_approval.authorise_shipping(
        destination=fake_repo_root / "submission",
        repo_root=fake_repo_root,
        live_configuration_hash=APPROVED,
        producing_configuration_hash=APPROVED,
    )
    assert result is None


def test_authorise_shipping_returns_none_for_a_destination_outside_the_repos_submission(
    fake_repo_root: Path,
) -> None:
    """A test writing to a temporary path is not the shipped record, which is
    the property `tests/test_submission.py`'s six unmodified `submit()` cases
    rely on."""
    result = shipping_approval.authorise_shipping(
        destination=fake_repo_root / "elsewhere",
        repo_root=fake_repo_root,
        live_configuration_hash=NOT_APPROVED,
        producing_configuration_hash=NOT_APPROVED,
    )
    assert result is None


# ------------------------------------------------------------------ AC18


def test_a_token_minted_by_the_real_freeze_guard_authorises_exactly_one_write(
    fake_repo_root: Path,
) -> None:
    """This is the check that keeps the two readers of the token format --
    `freeze_guard.consume_token` and `shipping_approval.consume_shipping_authorisation`
    -- from drifting apart in silence."""
    _mint_token(fake_repo_root, reason="the two-reader contract", by="pytest-suite")

    authorisation = shipping_approval.consume_shipping_authorisation(fake_repo_root)
    assert authorisation is not None
    assert authorisation.reason == "the two-reader contract"
    assert authorisation.by == "pytest-suite"
    assert authorisation.minted_at

    token_file = fake_repo_root / shipping_approval.AUTHORISATION_TOKEN_PATH
    assert not token_file.exists()
    assert shipping_approval.consume_shipping_authorisation(fake_repo_root) is None


def test_a_token_naming_a_different_subject_does_not_authorise_shipping(
    fake_repo_root: Path,
) -> None:
    _mint_token(fake_repo_root, subject="proving/experiments/0001-x/experiment.json")
    result = shipping_approval.consume_shipping_authorisation(fake_repo_root)
    assert result is None
    # left alone: a thaw for one file must not be silently spent by another reader
    assert (fake_repo_root / shipping_approval.AUTHORISATION_TOKEN_PATH).exists()


def test_a_broadly_minted_token_for_an_unrelated_frozen_file_must_not_authorise_shipping(
    fake_repo_root: Path,
) -> None:
    """freeze_guard's own idiom lets `--thaw REASON` omit `--subject` entirely, in
    which case `mint_token` defaults to *every currently-frozen file*
    (`subjects or frozen_files(root)`). An operator thawing
    `proving/experiments/.../experiment.json` to fix something unrelated, and
    forgetting `--subject`, must not thereby also authorise `forecast submit` to
    overwrite the committed submission -- but `consume_shipping_authorisation` only
    checks list membership, not intent, so a broad token silently does exactly
    that. This is the D3-adjacent risk the plan named: two readers of one token
    file, drifting apart in what a token means.
    """
    _require_freeze_guard()
    (fake_repo_root / "submission").mkdir()
    (fake_repo_root / "submission" / "forecasts.csv").write_text("indicator,probability\n")
    (fake_repo_root / "submission" / "manifest.json").write_text("{}\n")
    experiment_directory = fake_repo_root / "proving" / "experiments" / "0001-x"
    experiment_directory.mkdir(parents=True)
    (experiment_directory / "experiment.json").write_text("{}\n")

    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(FREEZE_GUARD),
            "--thaw",
            "fix a typo in the experiment threshold",
            "--by",
            "operator",
        ],
        cwd=fake_repo_root,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr

    authorisation = shipping_approval.consume_shipping_authorisation(fake_repo_root)
    assert authorisation is None, (
        "a token minted to thaw an unrelated frozen file, with no --subject given, was "
        f"accepted as authorising a submission ship: {authorisation}"
    )


def test_a_token_lets_authorise_shipping_through_and_is_then_consumed(
    fake_repo_root: Path,
) -> None:
    _mint_token(fake_repo_root)
    destination = fake_repo_root / "submission"

    authorisation = shipping_approval.authorise_shipping(
        destination=destination,
        repo_root=fake_repo_root,
        live_configuration_hash=NOT_APPROVED,
        producing_configuration_hash=NOT_APPROVED,
    )
    assert authorisation is not None
    assert authorisation.by == "pytest"
    assert not (fake_repo_root / shipping_approval.AUTHORISATION_TOKEN_PATH).exists()
    assert not destination.exists()  # authorising is not writing

    # single-use: a second unapproved attempt with no token left refuses again
    with pytest.raises(shipping_approval.SubmissionNotApprovedError):
        shipping_approval.authorise_shipping(
            destination=destination,
            repo_root=fake_repo_root,
            live_configuration_hash=NOT_APPROVED,
            producing_configuration_hash=NOT_APPROVED,
        )


# ------------------------------------------------------- exhaustive invariant


def test_authorise_shipping_is_exhaustively_governed_by_one_rule(tmp_path_factory) -> None:  # type: ignore[no-untyped-def]
    """For every pair of hashes, `authorise_shipping` never writes anything, and
    it returns without raising if and only if the destination is unguarded, or
    both hashes are already the approved one, or a matching token existed."""
    hash_pairs = (
        (APPROVED, APPROVED),
        (APPROVED, NOT_APPROVED),
        (NOT_APPROVED, APPROVED),
        (NOT_APPROVED, NOT_APPROVED),
    )

    for live, producing in hash_pairs:
        for guarded in (True, False):
            for with_token in (True, False) if guarded else (False,):
                root = tmp_path_factory.mktemp("case")
                (root / ".git").mkdir()
                destination = root / ("submission" if guarded else "elsewhere")
                if with_token:
                    _mint_token(root)
                both_approved = live == APPROVED and producing == APPROVED
                should_pass = (not guarded) or both_approved or with_token
                case = f"live={live} producing={producing} guarded={guarded} token={with_token}"

                if should_pass:
                    result = shipping_approval.authorise_shipping(
                        destination=destination,
                        repo_root=root,
                        live_configuration_hash=live,
                        producing_configuration_hash=producing,
                    )
                    token_file = root / shipping_approval.AUTHORISATION_TOKEN_PATH
                    if guarded and with_token and not both_approved:
                        assert result is not None, case
                        assert not token_file.exists(), case
                    if guarded and with_token and both_approved:
                        # nothing needed authorising, so an unused token is left alone
                        assert result is None, case
                        assert token_file.exists(), case
                else:
                    with pytest.raises(shipping_approval.SubmissionNotApprovedError):
                        shipping_approval.authorise_shipping(
                            destination=destination,
                            repo_root=root,
                            live_configuration_hash=live,
                            producing_configuration_hash=producing,
                        )
                assert not destination.exists(), f"authorise_shipping wrote something: {case}"


# --------------------------------------------------- end-to-end through the CLI


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot(directory: Path) -> dict[str, tuple[int, str]]:
    if not directory.exists():
        return {}
    return {
        item.name: (item.stat().st_mtime_ns, _digest(item))
        for item in sorted(directory.iterdir())
        if item.is_file()
    }


@pytest.fixture
def workspace_with_backtest_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """A workspace whose `backtest_results.parquet` names one configuration hash,
    with `SUBMISSION_DIRECTORY` pointed at a `tmp_path` -- never the real one."""
    settings = RunSettings(cache=CacheLayout(tmp_path / "cache"))
    settings.cache.create_directories()
    registry, indicators = load_registries()
    artifacts = ArtifactStore(settings.cache.models)
    artifacts.write_table(
        ARTIFACTS.backtest_results,
        pd.DataFrame({"configuration_hash": [NOT_APPROVED] * 3}),
    )
    monkeypatch.setattr(interface, "SUBMISSION_DIRECTORY", tmp_path / "submission")
    workspace = interface.Workspace(
        registry=registry,
        indicators=indicators,
        cache=SeriesCache(settings.cache.raw, settings.cache.vintage),
        artifacts=artifacts,
        settings=settings,
    )
    return workspace, tmp_path / "submission"


def _write_committed_submission(directory: Path, configuration_hash: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "forecasts.csv").write_text("indicator,probability\na,0.5\n")
    (directory / "manifest.json").write_text(
        json.dumps({"configuration_hash": configuration_hash}, indent=2) + "\n"
    )


def test_verify_only_writes_nothing_and_returns_zero_when_the_manifest_is_approved(
    workspace_with_backtest_results,
) -> None:  # type: ignore[no-untyped-def]
    workspace, directory = workspace_with_backtest_results
    _write_committed_submission(directory, APPROVED)
    before = _snapshot(directory)

    assert interface.verify_submission(workspace, date(2026, 9, 8)) == 0

    assert _snapshot(directory) == before
    assert sorted(item.name for item in directory.iterdir()) == ["forecasts.csv", "manifest.json"]


def test_verify_only_writes_nothing_and_returns_one_when_the_manifest_is_not_approved(
    workspace_with_backtest_results,
) -> None:  # type: ignore[no-untyped-def]
    workspace, directory = workspace_with_backtest_results
    _write_committed_submission(directory, NOT_APPROVED)
    before = _snapshot(directory)

    assert interface.verify_submission(workspace, date(2026, 9, 8)) == 1

    assert _snapshot(directory) == before


def test_verify_only_writes_nothing_when_the_submission_directory_is_absent(
    workspace_with_backtest_results,
) -> None:  # type: ignore[no-untyped-def]
    workspace, directory = workspace_with_backtest_results
    assert not directory.exists()

    assert interface.verify_submission(workspace, date(2026, 9, 8)) == 1

    assert not directory.exists()


def test_verify_only_says_what_to_run_when_backtest_results_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sad path the v2 review's finding 2 added: a missing artifact must say
    what to run next, not crash with a traceback."""
    settings = RunSettings(cache=CacheLayout(tmp_path / "cache"))
    settings.cache.create_directories()
    registry, indicators = load_registries()
    artifacts = ArtifactStore(settings.cache.models)
    monkeypatch.setattr(interface, "SUBMISSION_DIRECTORY", tmp_path / "submission")
    workspace = interface.Workspace(
        registry=registry,
        indicators=indicators,
        cache=SeriesCache(settings.cache.raw, settings.cache.vintage),
        artifacts=artifacts,
        settings=settings,
    )
    with pytest.raises(SystemExit, match="forecast backtest"):
        interface.verify_submission(workspace, date(2026, 9, 8))


def test_verify_only_refuses_a_backtest_results_carrying_two_configurations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A submission assembled from two runs has no single provenance to check
    the approved hash against -- `_hash_that_produced_the_artifacts`'s own sad
    path, exercised through the same `verify_submission` entry point `submit`
    uses."""
    settings = RunSettings(cache=CacheLayout(tmp_path / "cache"))
    settings.cache.create_directories()
    registry, indicators = load_registries()
    artifacts = ArtifactStore(settings.cache.models)
    artifacts.write_table(
        ARTIFACTS.backtest_results,
        pd.DataFrame({"configuration_hash": [APPROVED, NOT_APPROVED]}),
    )
    monkeypatch.setattr(interface, "SUBMISSION_DIRECTORY", tmp_path / "submission")
    workspace = interface.Workspace(
        registry=registry,
        indicators=indicators,
        cache=SeriesCache(settings.cache.raw, settings.cache.vintage),
        artifacts=artifacts,
        settings=settings,
    )
    with pytest.raises(shipping_approval.SubmissionNotApprovedError, match="2 configuration"):
        interface.verify_submission(workspace, date(2026, 9, 8))


# ---------------------------------------------------------- the --verify-only flag


def test_the_verify_only_flag_is_off_by_default_and_on_when_passed() -> None:
    """AC19's plumbing: the parser change that lets `submit` carry a flag must
    not disturb the flag's own default, which `verify_submission` branches on."""
    plain = interface.build_parser().parse_args(["submit"])
    assert plain.command == "submit"
    assert plain.verify_only is False

    verify_only = interface.build_parser().parse_args(["submit", "--verify-only"])
    assert verify_only.command == "submit"
    assert verify_only.verify_only is True
