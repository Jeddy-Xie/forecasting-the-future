"""A baseline records the commit it was captured on, including inside a worktree.

Every research arm runs in a linked git worktree, where `.git` is a file pointing
elsewhere. Until 2026-09-29 `git_commit_of` read only a `.git` directory, so a
baseline captured in a worktree recorded `null` for its commit.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from economic_regime_forecasting.regression_baseline import git_commit_of

GIT = shutil.which("git")


def _git(directory: Path, *arguments: str) -> str:
    assert GIT is not None
    completed = subprocess.run(  # noqa: S603 -- the git on PATH, fixed arguments
        [GIT, "-C", str(directory), *arguments],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


@pytest.mark.skipif(GIT is None, reason="git is not installed")
def test_the_commit_is_read_in_a_checkout_and_in_both_kinds_of_worktree(tmp_path: Path) -> None:
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q", "-b", "main")
    (main / "file.txt").write_text("one\n")
    _git(main, "add", "file.txt")
    _git(main, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "one")
    first = _git(main, "rev-parse", "HEAD")

    branch = tmp_path / "branch"
    _git(main, "worktree", "add", "-q", "-b", "arm", str(branch))
    (branch / "file.txt").write_text("two\n")
    _git(branch, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "two")
    second = _git(branch, "rev-parse", "HEAD")

    detached = tmp_path / "detached"
    _git(main, "worktree", "add", "-q", "--detach", str(detached), first)

    assert git_commit_of(main) == first
    assert git_commit_of(branch) == second
    assert git_commit_of(detached) == first
    assert git_commit_of(tmp_path / "not-a-checkout") is None
