#!/usr/bin/env bash
# Everything, in order, from a clean checkout. Stops at the first failure.
#
# Operational glue: each line is a command documented in docs/RUNNING.md, and
# nothing here contains logic of its own.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> environment"
poetry install

echo "==> tests"
poetry run pytest -m "not network"

echo "==> lint and types"
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy

echo "==> data"
poetry run forecast fetch-data

echo "==> gates"
poetry run forecast check-gates

echo "==> submission"
poetry run forecast submit

echo "==> notebooks"
poetry run python scripts/execute_notebooks.py

echo
echo "Done. The submission is in submission/, the write-up in notebooks/04_report.ipynb."
