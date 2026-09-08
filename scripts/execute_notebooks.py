#!/usr/bin/env python3
"""Execute every notebook top to bottom and fail if any cell raises.

Operational glue. Nothing imports this; it exists so that "the notebooks run
clean" is a command rather than a claim. Outputs are written to a temporary copy
and thrown away, so running it never dirties the tracked notebooks.

    poetry run python scripts/execute_notebooks.py
    poetry run python scripts/execute_notebooks.py notebooks/02_regime_model.ipynb
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_DIRECTORY = PROJECT_ROOT / "notebooks"
CELL_TIMEOUT_SECONDS = 900


def execute(path: Path) -> str | None:
    """Run one notebook. Returns None on success, or the failure message."""
    notebook = nbformat.read(path, as_version=4)
    client = NotebookClient(
        notebook,
        timeout=CELL_TIMEOUT_SECONDS,
        kernel_name="python3",
        resources={"metadata": {"path": str(path.parent)}},
    )
    try:
        client.execute()
    except CellExecutionError as error:
        return str(error).strip().splitlines()[-1]
    with tempfile.NamedTemporaryFile(suffix=".ipynb", delete=True) as sink:
        nbformat.write(notebook, sink.name)
    return None


def main(argv: list[str]) -> int:
    paths = (
        [Path(argument).resolve() for argument in argv]
        if argv
        else sorted(NOTEBOOK_DIRECTORY.glob("*.ipynb"))
    )
    if not paths:
        print(f"no notebooks found under {NOTEBOOK_DIRECTORY}")
        return 1

    failures = 0
    for path in paths:
        print(f"running {path.name} ... ", end="", flush=True)
        failure = execute(path)
        if failure is None:
            print("ok")
        else:
            failures += 1
            print(f"FAILED\n    {failure}")
    print(f"\n{len(paths) - failures} of {len(paths)} notebooks ran clean")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
