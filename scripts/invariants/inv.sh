#!/bin/bash
# inv.sh REV OUT_DIR: the two identity invariants of revision REV of the repository in the current directory.
# Exports REV to a scratch directory, compiles every .orc of the export (OUT_DIR/compile.json) and snapshots the
# corpus (OUT_DIR/digests.json), then prints the SHA-256 of both. Run it for a task's base and for its tip with
# two output directories: the files are byte-identical when no compile outcome and no digest moved.
# Scratch space (about 150 MB, removed on exit) is taken under TMPDIR; JOBS sets the parallel compiles (8).
# RUNREF=DIR also runs the run-reference test modules of the export serially and writes their program digests
# (OUT_DIR/runref.json, the test log OUT_DIR/runref.log); it takes 15 to 25 minutes. DIR, which must not exist,
# replaces the scratch directory: give both revisions the same DIR so their programs embed the same paths.
set -eu
REV=$1; mkdir -p "$2"; OUT=$(cd "$2" && pwd); KIT=$(cd "$(dirname "$0")" && pwd)
if [ -n "${RUNREF:-}" ]; then mkdir -m 700 "$RUNREF"; WORK=$(cd "$RUNREF" && pwd); else WORK=$(mktemp -d); fi; trap 'chmod -R u+rwx "$WORK"; rm -rf "$WORK"' EXIT
mkdir "$WORK/tree" "$WORK/tmp"
git archive "$REV" | tar -x -C "$WORK/tree"
export PATH="$WORK/tree/experiments/thread_m/no_provider:$PATH" TMPDIR="$WORK/tmp"
export PYTHONPATH="$WORK/tree${PYTHONPATH:+:$PYTHONPATH}"
(cd "$WORK/tree" && python "$KIT/digests.py" "$OUT/digests.json")
(cd "$WORK" && python "$KIT/compile_all.py" "$WORK/tree" "$OUT/compile.json" "${JOBS:-8}")
if [ -n "${RUNREF:-}" ]; then
  RR="$WORK/rr"
  # A failing test still leaves its programs; the log's last line, printed, says how the run ended.
  (cd "$WORK/tree" && python -m pytest -q -p no:xdist -p no:cacheprovider -p no:randomly --basetemp="$RR" \
    tests/test_workflow_lisp_run_ref*.py tests/test_workflow_evaluated_run_ref*.py \
    tests/test_workflow_lisp_closed_program_effects.py > "$OUT/runref.log" 2>&1) || true
  tail -1 "$OUT/runref.log"
  python "$KIT/program_digests.py" "$RR" "$OUT/runref.json"
  sha256sum "$OUT/runref.json"
fi
sha256sum "$OUT/compile.json" "$OUT/digests.json"
