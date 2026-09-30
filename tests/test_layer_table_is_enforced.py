"""The layer table in the package docstring is a specification, and this runs it.

`scripts/layer_check.py` reads the table and reports every import that points the
wrong way. For a long time nothing ran it, so seven violations accumulated while it
sat correct and unused (debt D16). A check nobody runs is advice; this makes it a
failing test.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]


def test_every_import_points_the_way_the_package_docstring_declares() -> None:
    completed = subprocess.run(  # noqa: S603 -- this interpreter, a script in this repository
        [sys.executable, str(REPOSITORY / "scripts" / "layer_check.py"), "--json"],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPOSITORY,
    )
    report = json.loads(completed.stdout)
    assert report["violations"] == [], report["violations"]
    assert completed.returncode == 0
