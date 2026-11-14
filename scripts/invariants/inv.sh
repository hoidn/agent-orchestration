#!/bin/bash
# inv.sh REV OUT_DIR: the two identity invariants of revision REV of the repository in the current directory.
# Exports REV to a scratch directory, compiles every .orc of the export (OUT_DIR/compile.json) and snapshots the
# corpus (OUT_DIR/digests.json), then prints the SHA-256 of both. Run it for a task's base and for its tip with
# two output directories: the files are byte-identical when no compile outcome and no digest moved.
# Scratch space (about 150 MB, removed on exit) is taken under TMPDIR; JOBS sets the parallel compiles (8).
set -eu
REV=$1; mkdir -p "$2"; OUT=$(cd "$2" && pwd); KIT=$(cd "$(dirname "$0")" && pwd)
WORK=$(mktemp -d); trap 'chmod -R u+rwx "$WORK"; rm -rf "$WORK"' EXIT
mkdir "$WORK/tree" "$WORK/tmp"
git archive "$REV" | tar -x -C "$WORK/tree"
export PATH="$WORK/tree/experiments/thread_m/no_provider:$PATH" TMPDIR="$WORK/tmp"
export PYTHONPATH="$WORK/tree${PYTHONPATH:+:$PYTHONPATH}"
(cd "$WORK/tree" && python "$KIT/digests.py" "$OUT/digests.json")
(cd "$WORK" && python "$KIT/compile_all.py" "$WORK/tree" "$OUT/compile.json" "${JOBS:-8}")
sha256sum "$OUT/compile.json" "$OUT/digests.json"
