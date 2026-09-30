#!/usr/bin/env bash
# Build the research paper: regenerate its figures, tables and named numbers from the
# committed record, then typeset paper/main.pdf.
#
# Operational glue: each line is a command documented in docs/RUNNING.md, and nothing
# here contains logic of its own. Needs `forecast check-gates` to have run (the regime
# figure reads the cached backtest) and `tectonic` on the path (brew install tectonic).
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v tectonic >/dev/null 2>&1; then
    echo "build_paper: tectonic is not installed. Install it with 'brew install tectonic'," >&2
    echo "or typeset paper/main.tex with any TeX Live 2023+ pdflatex and bibtex." >&2
    exit 2
fi

echo "==> figures, tables and named numbers"
poetry run forecast paper-assets

echo "==> typeset"
(cd paper && tectonic -X compile main.tex)

echo "wrote paper/main.pdf"
