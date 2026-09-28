#!/bin/bash
# Usage: MODEL=<sonnet|luna> run_trial.sh <n> — fresh repository worktree on the RAM disk, one real workflow run.
V="$(cd "$(dirname "$0")" && pwd)"
MAIN=/home/ollie/Documents/agent-orchestration
T=/dev/shm/ab4/t$1
rm -rf "$T"; mkdir -p "$T" "$T/tmp"
git -C "$MAIN" worktree prune
git -C "$MAIN" worktree add --detach "$T/repo" 468e7908 -q || exit 1
mkdir -p "$T/repo/bugs/loop_result_paths" && cp -r "$V/repro/." "$T/repo/bugs/loop_result_paths/"
( cd "$T/repo" && git add -A bugs && git -c user.name=trial -c user.email=trial@example.invalid commit -qm "trial baseline: bug report" )
git -C "$T/repo" rev-parse HEAD > "$T/baseline"
cp "$V/reviewed_change.$MODEL.orc" "$T/reviewed_change.orc"; cp "$V/providers.$MODEL.json" "$T/providers.json"
ln -s repo/artifacts "$T/artifacts"
python3 - "$V" "$T" <<'PY'
import json, sys
from pathlib import Path
v, t = Path(sys.argv[1]), sys.argv[2]
Path(t, "inputs.json").write_text(json.dumps({
    "task": (v / "task.txt").read_text().replace("REPO_PATH", t + "/repo"),
    "intent": (v / "intent.txt").read_text(),
    "repo": t + "/repo",
}))
PY
cd "$T" || exit 1
export TRIAL_ROOT="$T" TMPDIR="$T/tmp" PATH="$V/bin:$PATH" PYTHONPATH="/dev/shm/ab5/runner"
start=$(date +%s)
python -m orchestrator run reviewed_change.orc \
  --entry-workflow reviewed_change::reviewed-change \
  --provider-externs-file providers.json --input-file inputs.json > run.log 2>&1
echo "exit=$? seconds=$(( $(date +%s) - start ))" > "$T/finished"
