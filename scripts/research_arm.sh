#!/usr/bin/env bash
# Run one research arm in its own git worktree and compare it against main.
#
# Operational glue: every step below is a documented command, and nothing here contains
# modelling logic of its own. See docs/REGRESSION_TESTING.md for what the comparison means.
#
#   scripts/research_arm.sh setup <arm>   create the worktree and its private cache
#   scripts/research_arm.sh run   <arm>   run the five gates there and compare against the reference
#   scripts/research_arm.sh path  <arm>   print the worktree path
#
# The reference, benchmark and family-wise level come from the experiment, through
# RESEARCH_ARM_REFERENCE (default main), RESEARCH_ARM_BENCHMARK (default series-start) and
# RESEARCH_ARM_FAMILY_LEVEL (default 0.9833, experiment 0002's six arms).
#
# Two traps this exists to close, both measured on 2026-09-15 rather than assumed:
#
#   1. The package is an EDITABLE install whose .pth points at main's src/. Run from a
#      worktree without intervention, `python -m economic_regime_forecasting...` imports
#      MAIN's code, so every arm would silently report main's results as its own. PYTHONPATH
#      is set to the worktree's src/, and every command asserts that the imported module
#      really lives in the worktree before it does anything else. A check, not a convention.
#
#   2. The cache root is derived from the module's location, so an arm writes fitted models
#      into its own .cache/. Raw series and archival vintages are copied in (24 MB, no
#      network needed); main's fitted models are copied too, so an arm whose configuration
#      matches main's reads them from cache rather than refitting.
set -euo pipefail

MAIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARMS_ROOT="${RESEARCH_ARMS_ROOT:-$(dirname "$MAIN_ROOT")/forecasting-the-future-arms}"
PYTHON="$MAIN_ROOT/.venv/bin/python"

usage() { echo "usage: $0 {setup|run|path} <arm-name>" >&2; exit 2; }
[ $# -eq 2 ] || usage
COMMAND="$1"; ARM="$2"
case "$ARM" in *[!a-z0-9-]*|"") echo "arm name must be lower-case letters, digits and hyphens: '$ARM'" >&2; exit 2;; esac
WORKTREE="$ARMS_ROOT/$ARM"
BRANCH="research/$ARM"

assert_isolated() {
    # Refuse to run anything unless the interpreter imports the worktree's own code.
    local imported
    imported="$(cd "$WORKTREE" && PYTHONPATH="$WORKTREE/src" "$PYTHON" -c \
        'import economic_regime_forecasting as m; print(m.__file__)')"
    case "$imported" in
        "$WORKTREE/src/"*) ;;
        *) echo "REFUSING: the worktree imports $imported, not its own src/. The arm would report" >&2
           echo "main's code as its own result. Check PYTHONPATH and the editable install." >&2
           exit 3;;
    esac
}

case "$COMMAND" in
    path)
        echo "$WORKTREE"
        ;;
    setup)
        REFERENCE="${RESEARCH_ARM_REFERENCE:-main}"
        [ -f "$MAIN_ROOT/baselines/$REFERENCE.json" ] || { echo "no baselines/$REFERENCE.json on main; run 'forecast baseline capture --name $REFERENCE' first" >&2; exit 2; }
        mkdir -p "$ARMS_ROOT"
        if [ -d "$WORKTREE" ]; then
            echo "worktree exists: $WORKTREE (branch $BRANCH), reusing it"
        else
            git -C "$MAIN_ROOT" worktree add -q -b "$BRANCH" "$WORKTREE" main
            mkdir -p "$WORKTREE/.cache"
            for area in raw vintage models processed; do
                [ -d "$MAIN_ROOT/.cache/$area" ] && cp -R "$MAIN_ROOT/.cache/$area" "$WORKTREE/.cache/"
            done
            echo "created $WORKTREE on branch $BRANCH, private cache copied from main"
        fi
        assert_isolated
        echo "isolation verified: the worktree imports its own src/"
        ;;
    run)
        [ -d "$WORKTREE" ] || { echo "no worktree for '$ARM'; run '$0 setup $ARM' first" >&2; exit 2; }
        assert_isolated
        # A run counts only for the code of the commit it names, so the tree must be clean before the run
        # and still clean, at the same commit, after it. Measured on 2026-09-15: an arm's code was edited
        # while its run was in progress, and exit_codes.json named a commit whose code never ran whole.
        tree_changes() { git -C "$WORKTREE" status --porcelain --untracked-files=all -- . ':(exclude)research/arms'; }
        if [ -n "$(tree_changes)" ]; then
            echo "REFUSING: the worktree has uncommitted changes outside research/arms/. Commit them first:" >&2
            tree_changes >&2
            exit 4
        fi
        COMMIT_AT_START="$(git -C "$WORKTREE" rev-parse HEAD)"
        OUT="$WORKTREE/research/arms/$ARM"; mkdir -p "$OUT"
        cd "$WORKTREE"
        export PYTHONPATH="$WORKTREE/src"
        CLI=("$PYTHON" -m economic_regime_forecasting.command_line_interface)
        # What the arm is judged against, set by the experiment rather than assumed. Defaults are
        # experiment 0002's; experiment 0008 sets REFERENCE=reference-0008, BENCHMARK=model-sample and
        # FAMILY_LEVEL=0.9667 (1 - 0.10/3), and reads the series-start benchmark as a secondary.
        REFERENCE="${RESEARCH_ARM_REFERENCE:-main}"
        BENCHMARK="${RESEARCH_ARM_BENCHMARK:-series-start}"
        FAMILY_LEVEL="${RESEARCH_ARM_FAMILY_LEVEL:-0.9833}"
        LEVELS=(--confidence-level 0.90 --confidence-level "$FAMILY_LEVEL")
        set +e
        "${CLI[@]}" check-gates > "$OUT/check_gates.log" 2>&1;                          GATES=$?
        COMPARE=-1; PAIRED=-1; PAIRED_SECONDARY=-1
        if [ "$GATES" -eq 0 ]; then
            "${CLI[@]}" baseline compare --require-own-artifacts --against "$REFERENCE"              > "$OUT/compare.txt"  2>&1; COMPARE=$?
            "${CLI[@]}" baseline compare --require-own-artifacts --against "$REFERENCE" --format json > "$OUT/compare.json" 2>/dev/null
            # Both levels from ONE set of resamples: 90% decides PROMISING, the family-wise level decides
            # CONFIRMED_IN_SAMPLE. Without the second no arm could ever be confirmed.
            "${CLI[@]}" baseline compare --require-own-artifacts --against "$REFERENCE" --paired --benchmark "$BENCHMARK" "${LEVELS[@]}"               > "$OUT/paired.txt"  2>&1; PAIRED=$?
            "${CLI[@]}" baseline compare --require-own-artifacts --against "$REFERENCE" --paired --benchmark "$BENCHMARK" "${LEVELS[@]}" --format json > "$OUT/paired.json" 2>/dev/null
            if [ "$BENCHMARK" != "series-start" ]; then
                "${CLI[@]}" baseline compare --require-own-artifacts --against "$REFERENCE" --paired --benchmark series-start "${LEVELS[@]}"               > "$OUT/paired_series_start.txt"  2>&1; PAIRED_SECONDARY=$?
                "${CLI[@]}" baseline compare --require-own-artifacts --against "$REFERENCE" --paired --benchmark series-start "${LEVELS[@]}" --format json > "$OUT/paired_series_start.json" 2>/dev/null
            fi
        else
            # A failed gate run leaves the arm's cache holding artifacts it inherited, and comparing them
            # reports +0.0000 everywhere: a failed arm dressed as a passing control (experiment 0005).
            echo "check-gates exited $GATES, so no comparison was made; read check_gates.log" > "$OUT/NO_COMPARISON.txt"
        fi
        # The deterministic half of the look-ahead defence, at both standing cutoffs: the default one
        # early in the sample, and 2022-03-01, which reaches every recession announcement since 1991.
        # An arm that fails either is void under the pre-registration, whatever its skill score says.
        "${CLI[@]}" audit-look-ahead > "$OUT/look_ahead_audit.txt" 2>&1;               AUDIT=$?
        "${CLI[@]}" audit-look-ahead --cutoff 2022-03-01 > "$OUT/look_ahead_audit_2022.txt" 2>&1; AUDIT_2022=$?
        set -e
        CLEAN_THROUGHOUT=false
        if [ "$(git rev-parse HEAD)" = "$COMMIT_AT_START" ] && [ -z "$(tree_changes)" ]; then CLEAN_THROUGHOUT=true; fi
        printf '{"arm": "%s", "branch": "%s", "commit": "%s", "reference": "%s", "benchmark": "%s", "family_level": %s, "tree_clean_at_start_and_end": %s, "check_gates_exit": %d, "compare_exit": %d, "paired_exit": %d, "paired_series_start_exit": %d, "look_ahead_audit_exit": %d, "look_ahead_audit_2022_exit": %d}\n' \
            "$ARM" "$BRANCH" "$COMMIT_AT_START" "$REFERENCE" "$BENCHMARK" "$FAMILY_LEVEL" "$CLEAN_THROUGHOUT" "$GATES" "$COMPARE" "$PAIRED" "$PAIRED_SECONDARY" "$AUDIT" "$AUDIT_2022" > "$OUT/exit_codes.json"
        [ "$CLEAN_THROUGHOUT" = true ] || echo "WARNING: the worktree changed during the run (HEAD moved or files were edited), so these outputs do not count" >&2
        echo "arm $ARM: check-gates exit $GATES, compare exit $COMPARE, paired exit $PAIRED, look-ahead audits exit $AUDIT and $AUDIT_2022; outputs in $OUT"
        ;;
    *) usage;;
esac
