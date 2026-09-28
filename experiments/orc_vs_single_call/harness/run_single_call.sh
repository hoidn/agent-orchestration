#!/bin/bash
# Usage: run_single.sh <name> <model> — one repository copy, one implementation call, no selection.
V="$(cd "$(dirname "$0")" && pwd)"; MAIN=/home/ollie/Documents/agent-orchestration
T=/dev/shm/ab5/$1; rm -rf "$T"; mkdir -p "$T/tmp" "$T/artifacts/review"
git -C "$MAIN" worktree prune
git -C "$MAIN" worktree add --detach "$T/cand1" 468e7908 -q || exit 1
mkdir -p "$T/cand1/bugs/loop_result_paths" && cp -r "$V/repro/." "$T/cand1/bugs/loop_result_paths/"
( cd "$T/cand1" && git add -A bugs && git -c user.name=trial -c user.email=trial@example.invalid commit -qm "trial baseline: bug report" )
git -C "$T/cand1" rev-parse HEAD > "$T/baseline"
cp "$V/best_of_n.$2.orc" "$T/best_of_n.orc"; cp "$V/providers.$2.json" "$T/providers.json"
python3 - "$V" "$T" <<'PY'
import json, sys
from pathlib import Path
v, t = Path(sys.argv[1]), sys.argv[2]
Path(t, "inputs.json").write_text(json.dumps({"task": (v / "task.txt").read_text(), "repo": f"{t}/cand1"}))
PY
cd "$T" || exit 1
export TRIAL_ROOT="$T" TMPDIR="$T/tmp" PATH="$V/bin:$PATH" PYTHONPATH="/dev/shm/ab5/runner"
start=$(date +%s)
python -m orchestrator run best_of_n.orc --entry-workflow best_of_n::implement-one \
  --provider-externs-file providers.json --input-file inputs.json > run.log 2>&1
echo "exit=$? seconds=$(( $(date +%s) - start ))" > "$T/finished"
