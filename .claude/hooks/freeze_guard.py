#!/usr/bin/env python3
"""The pre-registration is frozen. This is the check that says so.

CLAUDE.md states the one forbidden act plainly:

    The decision rule does not move. Acceptance thresholds live in
    proving/experiments/.../experiment.json and were committed before the
    first backtest ran. Changing one after seeing results is the single
    forbidden act.

Prose in a context window is advisory. This is the same rule compiled into a
PreToolUse hook, which is not.

Two jobs, one file:

  (hook)      Refuse any Edit/Write/NotebookEdit to a frozen path unless a
              single-use thaw token is present. Reads a JSON payload on stdin,
              prints a deny decision, and always exits 0 — a guard that can
              crash a session is worse than no guard.

  --check     Assert from git history that no frozen file has been modified
              since the commit that registered it. Exit 0 clean, 1 on drift,
              2 when the question cannot be answered (no git, no file). Safe
              to wire into CI or check-gates.

`submission/forecasts.csv` and `submission/manifest.json` are frozen for a
related reason: they are the only artifacts that leave this repository, and since
2026-09-09 the pipeline default is the honest configuration, which is not the one
that produced them (ADR 0008). Regenerating them is Jeddy's call, not a side
effect of a routine run, so a hand edit is denied here and a `forecast submit`
that would overwrite them is refused at runtime by
`configuration/shipping_approval.py` — a second reader of this file's token,
never a second idiom.

Thawing, deliberately, is possible: a frozen file nobody can ever change is a
file people route around. `--thaw "<reason>"` writes a token that authorises
exactly one write and records who asked and why. The point is that moving a
threshold becomes a decision with a name on it, not a convenience.

One exception, and it is the whole reason `SHIPPING_GLOBS` exists: a bare
`--thaw` sweeps every frozen file *except* the two outward-facing ones. Shipping
takes an explicit `--subject submission/forecasts.csv`, so a thaw minted for some
unrelated file cannot authorise a re-ship through this file's second reader.

Stdlib only. Python 3.9+.
"""

from __future__ import annotations

import argparse
import getpass
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# ---------------------------------------------------------------- what is frozen

FROZEN_GLOBS = [
    "proving/experiments/*/experiment.json",
    "forecasts/register.jsonl",
    "forecasts/resolutions.jsonl",
    "submission/forecasts.csv",
    "submission/manifest.json",
]

SHIPPING_GLOBS = [
    "submission/forecasts.csv",
    "submission/manifest.json",
]
"""Frozen like everything else, but never swept into a token by default.

`--thaw "<reason>"` with no `--subject` covers every frozen file, which is the
right default for the pre-registration and the ledgers: the reason names what the
operator is about to edit and the token is consumed by that one write. It is the
wrong default here. These two files are the only artifacts that leave the
repository, and `configuration/shipping_approval.py` is a *second reader* of this
same token, so a broad sweep would let a thaw minted to fix a typo in
`experiment.json` silently authorise the next `forecast submit` to overwrite the
committed submission. Shipping is a named act (ADR 0008), so it takes an explicit
`--subject submission/forecasts.csv` and nothing else will do."""

DEFAULT_THAW_GLOBS = [pattern for pattern in FROZEN_GLOBS if pattern not in SHIPPING_GLOBS]

TOKEN_PATH = ".claude/thaw-token.json"

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_CANNOT_TELL = 2


# ---------------------------------------------------------------- helpers


def repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / ".git").exists():
            return candidate
    return start


def relative_to_root(path_string: str, root: Path) -> str:
    try:
        path = Path(path_string)
        if not path.is_absolute():
            path = (root / path).resolve()
        return path.resolve().relative_to(root).as_posix()
    except Exception:
        return str(path_string).replace("\\", "/")


def is_frozen(relative_path: str) -> bool:
    return any(Path(relative_path).match(pattern) for pattern in FROZEN_GLOBS)


def is_outward_facing(relative_path: str) -> bool:
    """Is this one of the two files that leave the repository? See SHIPPING_GLOBS."""
    return any(Path(relative_path).match(pattern) for pattern in SHIPPING_GLOBS)


def frozen_files(root: Path, patterns: list[str] | None = None) -> list[str]:
    found: list[str] = []
    for pattern in FROZEN_GLOBS if patterns is None else patterns:
        found.extend(sorted(p.relative_to(root).as_posix() for p in root.glob(pattern)))
    return found


def git(root: Path, *arguments: str) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return completed.returncode, (completed.stdout or "").strip()
    except Exception as error:  # git missing, or a repository that is not one
        return 127, str(error)


# ---------------------------------------------------------------- the thaw token


def read_token(root: Path) -> dict | None:
    token_file = root / TOKEN_PATH
    try:
        if not token_file.exists():
            return None
        return json.loads(token_file.read_text())
    except Exception:
        return None


def consume_token(root: Path, relative_path: str) -> bool:
    """Single-use, and scoped: a thaw for one file does not thaw another.

    Read-then-unlink, so one deliberate decision authorises exactly one write.
    """
    token = read_token(root)
    if not token:
        return False
    subjects = token.get("subjects") or []
    if subjects and relative_path not in subjects:
        return False
    try:
        (root / TOKEN_PATH).unlink()
    except Exception:
        return False
    return True


def mint_token(root: Path, reason: str, subjects: list[str], by: str) -> int:
    """Write the token. A bare `--thaw` never reaches the outward-facing files.

    With no `--subject`, the default is every frozen file EXCEPT `SHIPPING_GLOBS`
    — see that constant for why. Naming a submission path explicitly still works
    and is the only way to authorise a ship.
    """
    if not reason.strip():
        print("freeze_guard: --thaw needs a reason. Say what changed and why.", file=sys.stderr)
        return EXIT_CANNOT_TELL
    swept = not subjects
    targets = subjects or frozen_files(root, DEFAULT_THAW_GLOBS)
    if not targets:
        if swept and frozen_files(root, SHIPPING_GLOBS):
            print(
                "freeze_guard: the only frozen files here are outward-facing, and a bare "
                "--thaw never covers them. Shipping is a named act: pass "
                "--subject submission/forecasts.csv if that is what you mean.",
                file=sys.stderr,
            )
            return EXIT_CANNOT_TELL
        print("freeze_guard: nothing frozen to thaw.", file=sys.stderr)
        return EXIT_CANNOT_TELL
    token = {
        "reason": reason.strip(),
        "subjects": targets,
        "by": by,
        "minted_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "single_use": True,
    }
    path = root / TOKEN_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(token, indent=2) + "\n")
    print(f"THAWED (one write): {', '.join(targets)}")
    print(f"  reason: {reason.strip()}")
    print(f"  by:     {by}")
    print("The token is consumed by the next write to one of those paths.")
    withheld = frozen_files(root, SHIPPING_GLOBS) if swept else []
    if withheld:
        print(
            f"NOT thawed: {', '.join(withheld)} — a bare --thaw does not authorise shipping.\n"
            "  To ship deliberately, mint a token that names it:\n"
            '      --thaw "<why this run should ship>" --subject submission/forecasts.csv'
        )
    return EXIT_OK


# ---------------------------------------------------------------- --check


def check(root: Path) -> int:
    """Has any frozen file moved since the commit that registered it?"""
    targets = frozen_files(root)
    if not targets:
        print("freeze_guard: no frozen files found. Nothing to check.", file=sys.stderr)
        return EXIT_CANNOT_TELL

    code, _ = git(root, "rev-parse", "--git-dir")
    if code != 0:
        print("freeze_guard: not a git repository — history cannot be read.", file=sys.stderr)
        return EXIT_CANNOT_TELL

    drifted: list[str] = []
    untracked: list[str] = []
    for relative_path in targets:
        code, log = git(
            root, "log", "--follow", "--format=%h %ad %s", "--date=short", "--", relative_path
        )
        if code != 0 or not log:
            print(f"UNTRACKED  {relative_path}")
            print(
                "           no commit registers this file, so nothing pins it. "
                "Commit it before it counts as pre-registered."
            )
            untracked.append(relative_path)
            continue

        commits = log.splitlines()
        registered = commits[-1]
        modifications = commits[:-1]

        # An append-only ledger grows by design; a decision rule does not.
        append_only = relative_path.endswith(".jsonl")

        if not modifications or append_only:
            note = "unmodified"
            if append_only and modifications:
                note = f"{len(modifications)} append(s)"
            print(f"FROZEN     {relative_path}")
            print(f"           registered {registered}; {note} since.")
        else:
            drifted.append(relative_path)
            print(f"DRIFTED    {relative_path}")
            print(f"           registered {registered}")
            for commit in modifications:
                print(f"           modified   {commit}")

    # Uncommitted working-tree edits count as drift too: git history cannot see them.
    code, dirty = git(root, "status", "--porcelain", "--", *targets)
    if code == 0 and dirty:
        for line in dirty.splitlines():
            path = line[3:].strip()
            if not path.endswith(".jsonl") and path not in drifted:
                drifted.append(path)
                print(f"DIRTY      {path}")
                print("           uncommitted changes in the working tree.")

    print()
    if drifted:
        print(
            f"freeze_guard: {len(drifted)} frozen file(s) MOVED. "
            "A threshold changed after results exist invalidates the pre-registration; "
            "if the change was deliberate, the reason belongs in docs/adr/."
        )
    if untracked:
        print(
            f"freeze_guard: {len(untracked)} frozen file(s) are not committed yet, so "
            "nothing pins them. This is the expected state right after they are first "
            "written — commit them and they become checkable."
        )
    if drifted or untracked:
        return EXIT_DRIFT

    print(f"freeze_guard: {len(targets)} frozen file(s) intact.")
    return EXIT_OK


# ---------------------------------------------------------------- the hook path


def deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(EXIT_OK)


def run_hook() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        sys.exit(EXIT_OK)  # unreadable payload: allow rather than brick the session

    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not isinstance(file_path, str) or not file_path:
        sys.exit(EXIT_OK)

    root = repo_root(Path(payload.get("cwd") or ".").resolve())
    relative_path = relative_to_root(file_path, root)

    if not is_frozen(relative_path):
        sys.exit(EXIT_OK)

    if consume_token(root, relative_path):
        sys.exit(EXIT_OK)

    if relative_path.endswith(".jsonl"):
        deny(
            f"'{relative_path}' is an append-only forecast ledger. Rewriting it in place "
            "would silently restate a forecast that was already made, which is the whole "
            "thing the register exists to prevent. Append through "
            "`forecast register` / `forecast resolve`, or thaw deliberately:\n"
            f"    python3 {TOKEN_PATH.replace('thaw-token.json', 'hooks/freeze_guard.py')} "
            '--thaw "<why>" --subject ' + relative_path
        )

    if is_outward_facing(relative_path):
        deny(
            f"'{relative_path}' is one of the two artifacts that leave this repository, and "
            "since ADR 0008 the pipeline default is not the configuration that produced them. "
            "Regenerating or hand-editing them is Jeddy's call, never a side effect.\n"
            'A bare `--thaw "<why>"` deliberately does NOT cover these paths, so shipping '
            "cannot be authorised by accident. Name it, and the decision carries your name:\n"
            '    python3 .claude/hooks/freeze_guard.py --thaw "<why this run should ship>" '
            f"--subject {relative_path} --by <you>\n"
            "Then regenerate through `poetry run forecast submit` rather than by hand — that "
            "path records reason, who and when in submission/manifest.json. To see what would "
            "change without writing anything: `poetry run forecast submit --verify-only`."
        )

    deny(
        f"'{relative_path}' holds the pre-registered decision rule, and CLAUDE.md names "
        "changing it after seeing results as the single forbidden act. It was committed "
        "before the first backtest ran; every claim this repository makes depends on it "
        "not having moved since.\n"
        "If the change is genuinely legitimate — a typo, a new experiment, a threshold "
        "for work that has not been run yet — make it a decision with your name on it:\n"
        '    python3 .claude/hooks/freeze_guard.py --thaw "<why>" --subject '
        f"{relative_path}\n"
        "That authorises exactly one write, and the reason belongs in docs/adr/."
    )


# ---------------------------------------------------------------- entry point


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="freeze_guard.py",
        description="Keep the pre-registered decision rule from moving.",
    )
    parser.add_argument(
        "--check", action="store_true", help="assert from git history that no frozen file has moved"
    )
    parser.add_argument("--list", action="store_true", help="print what is currently frozen")
    parser.add_argument(
        "--thaw", metavar="REASON", help="mint a single-use token authorising one write"
    )
    parser.add_argument(
        "--subject", action="append", default=[], help="limit --thaw to this path (repeatable)"
    )
    parser.add_argument("--by", default=None, help="who is thawing (default: the shell user)")
    arguments = parser.parse_args()

    root = repo_root(Path.cwd())

    if arguments.list:
        found = frozen_files(root)
        if not found:
            print("nothing frozen")
            return EXIT_CANNOT_TELL
        for path in found:
            print(path)
        return EXIT_OK

    if arguments.thaw is not None:
        try:
            who = arguments.by or getpass.getuser()
        except Exception:
            who = arguments.by or "unknown"
        subjects = [relative_to_root(s, root) for s in arguments.subject]
        return mint_token(root, arguments.thaw, subjects, who)

    if arguments.check:
        return check(root)

    parser.print_help()
    return EXIT_CANNOT_TELL


if __name__ == "__main__":
    if sys.stdin is not None and not sys.stdin.isatty() and len(sys.argv) == 1:
        run_hook()  # a payload is waiting: this is the hook path
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as error:  # never brick a session on a guard's own bug
        print(f"freeze_guard: {error}", file=sys.stderr)
        raise SystemExit(EXIT_CANNOT_TELL) from error
