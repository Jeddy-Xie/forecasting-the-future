"""Refuse to ship a configuration nobody approved.

`submission/forecasts.csv` is the only artifact that leaves this repository. It
was produced by one configuration, and a person decided to ship it. Since
2026-09-09 the pipeline default is a *different*, honest configuration, so a
routine run of `scripts/run_full_pipeline.sh` would otherwise overwrite that
record with numbers nobody had looked at — silently, as step six of seven.

This module is the runtime half of stopping that. It is deliberately small and
deliberately stdlib-only: nothing here imports the rest of the package, so it
sits at the bottom of the declared layering with the rest of `configuration`.

**It is not a second freeze/thaw idiom.** The token file, its format and the
command that mints it all belong to `.claude/hooks/freeze_guard.py`, which
already exists for exactly this kind of decision. This is a second *reader* of
that one file. `tests/test_shipping_approval.py` mints a real token by invoking
that script and consumes it here, so the two readers cannot drift apart in
silence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CONFIGURATION_HASH_APPROVED_FOR_SHIPPING = "9f95b12dba40d138"
"""The configuration whose numbers Jeddy approved to ship.

`submission/forecasts.csv` is the only artifact that leaves this repository. It
was produced by this configuration. Since 2026-09-09 the pipeline default is a
different, honest configuration, so shipping is no longer something a routine run
may do by accident. Changing this line IS the re-ship decision: it belongs in the
same commit as the regenerated submission, with the reason in docs/adr/."""

# ruff's S105 fires on any name containing "TOKEN". This is a repository-relative
# file path, not a credential; the token it points at is a countersigned decision
# record, and it is deliberately world-readable inside the checkout.
AUTHORISATION_TOKEN_PATH = ".claude/thaw-token.json"  # noqa: S105
"""Owned by `.claude/hooks/freeze_guard.py`. Read here, never invented here."""

SHIPPING_SUBJECT = "submission/forecasts.csv"
"""The path a token must name before it authorises a submission write."""

SUBMISSION_DIRECTORY_NAME = "submission"


class SubmissionNotApprovedError(RuntimeError):
    """`forecast submit` was asked to ship a configuration nobody approved."""


@dataclass(frozen=True)
class ShippingAuthorisation:
    """A named, single-use decision to ship an unapproved configuration."""

    reason: str
    by: str
    minted_at: str

    def as_manifest_entry(self) -> dict[str, str]:
        """What goes into `manifest.json`, so the decision carries a name."""
        return {"reason": self.reason, "by": self.by, "minted_at": self.minted_at}


def consume_shipping_authorisation(repo_root: Path) -> ShippingAuthorisation | None:
    """Read and delete a single-use token naming `submission/forecasts.csv`.

    Read-then-unlink, matching `freeze_guard.consume_token`, so one deliberate
    decision authorises exactly one write. A token scoped to some other frozen
    path is left alone and authorises nothing here.

    The subject must be named **explicitly**. A token with no subjects at all
    authorises nothing here either: `freeze_guard.mint_token` keeps the two
    outward-facing paths out of the default sweep precisely so that a broad thaw
    cannot become a ship, and this reader refuses to infer the intent that the
    minting side deliberately declines to imply. Fail closed; the operator mints
    a second, named token, which is one command.
    """
    token_file = repo_root / AUTHORISATION_TOKEN_PATH
    try:
        payload = json.loads(token_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None

    subjects = payload.get("subjects") or []
    if SHIPPING_SUBJECT not in subjects:
        return None

    try:
        token_file.unlink()
    except OSError:
        return None

    return ShippingAuthorisation(
        reason=str(payload.get("reason", "")),
        by=str(payload.get("by", "")),
        minted_at=str(payload.get("minted_at", "")),
    )


def _guards_this_destination(destination: Path, repo_root: Path) -> bool:
    """Is this the repository's own `submission/`, or somewhere else entirely?

    The guard protects the *committed* artifact, not any directory that happens
    to be called submission. A test writing to a temporary path is not the
    shipped record, and the command line offers no way to point `submit`
    anywhere but the repository's own directory. The residual gap — a Python
    caller that monkeypatches the destination — writes somewhere that is not the
    thing being protected. Stated rather than hidden.
    """
    try:
        return destination.resolve() == (repo_root / SUBMISSION_DIRECTORY_NAME).resolve()
    except OSError:
        return False


def refusal_message(live_configuration_hash: str, producing_configuration_hash: str) -> str:
    """The whole of what to do next, which is what the project rule demands."""
    return (
        "refusing to write submission/forecasts.csv.\n"
        "\n"
        f"  approved for shipping  : {CONFIGURATION_HASH_APPROVED_FOR_SHIPPING}\n"
        f"  this run's settings    : {live_configuration_hash}\n"
        f"  produced the artifacts : {producing_configuration_hash}   "
        "(backtest_results.parquet)\n"
        "\n"
        "The committed submission is the only outward-facing claim this repository makes,\n"
        "and it was produced by the approved configuration. Nothing regenerates it by\n"
        "accident.\n"
        "\n"
        "To see what would change, without writing anything:\n"
        "    poetry run forecast submit --verify-only\n"
        "\n"
        "To ship this run deliberately — a decision with your name on it:\n"
        '    python3 .claude/hooks/freeze_guard.py --thaw "<why this run should ship>" \\\n'
        f"        --subject {SHIPPING_SUBJECT} --by <you>\n"
        "    poetry run forecast submit\n"
        "\n"
        f"The --subject is required: {SHIPPING_SUBJECT} is deliberately left out of a bare\n"
        '`--thaw "<reason>"`, so a thaw minted for the pre-registration or a ledger cannot\n'
        "authorise a ship. A token that does not name it is left alone and refused here.\n"
        "\n"
        "That token is single-use and has two readers: this guard, and the PreToolUse\n"
        "hook in freeze_guard.py that denies hand edits to the submission. Whichever\n"
        "acts first consumes it, so an editor touching submission/ after you mint one\n"
        "will eat it and this refusal will come back. Mint it immediately before the\n"
        "submit.\n"
        "\n"
        f"Then set CONFIGURATION_HASH_APPROVED_FOR_SHIPPING to {live_configuration_hash} in\n"
        "src/economic_regime_forecasting/configuration/shipping_approval.py in the same\n"
        "commit, and put the reason in docs/adr/."
    )


def authorise_shipping(
    *,
    destination: Path,
    repo_root: Path,
    live_configuration_hash: str,
    producing_configuration_hash: str,
) -> ShippingAuthorisation | None:
    """Raise unless this run may write the tracked submission.

    Returns ``None`` when there is nothing to authorise — either ``destination``
    is not the repository's own `submission/` directory, or both hashes already
    equal the approved one. Returns the consumed authorisation when a token
    permitted an unapproved run, so the caller can record who asked and why.
    Raises ``SubmissionNotApprovedError`` otherwise, having written nothing.
    """
    if not _guards_this_destination(destination, repo_root):
        return None
    if (
        live_configuration_hash == CONFIGURATION_HASH_APPROVED_FOR_SHIPPING
        and producing_configuration_hash == CONFIGURATION_HASH_APPROVED_FOR_SHIPPING
    ):
        return None

    authorisation = consume_shipping_authorisation(repo_root)
    if authorisation is not None:
        return authorisation

    raise SubmissionNotApprovedError(
        refusal_message(live_configuration_hash, producing_configuration_hash)
    )
