#!/bin/bash
# Usage: run_trial.sh <n> [<candidates>] — N fresh repository copies on the RAM disk, one real best-of-N run.
V="$(cd "$(dirname "$0")" && pwd)"
MAIN=/home/ollie/Documents/agent-orchestration
T=/dev/shm/ab5/t$1
N=${2:-4}
rm -rf "$T"; mkdir -p "$T/tmp" "$T/artifacts/review"
git -C "$MAIN" worktree prune
for k in $(seq 1 "$N"); do
  git -C "$MAIN" worktree add --detach "$T/cand$k" 468e7908 -q || exit 1
  mkdir -p "$T/cand$k/bugs/loop_result_paths" && cp -r "$V/repro/." "$T/cand$k/bugs/loop_result_paths/"
  ( cd "$T/cand$k" && git add -A bugs && git -c user.name=trial -c user.email=trial@example.invalid commit -qm "trial baseline: bug report" )
done
git -C "$T/cand1" rev-parse HEAD > "$T/baseline"
cp "$V/best_of_n.${MODEL:-sonnet}.orc" "$T/best_of_n.orc"; cp "$V/providers.${MODEL:-sonnet}.json" "$T/providers.json"
python3 - "$V" "$T" "$N" <<'PY'
import json, sys
from pathlib import Path
v, t, n = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
Path(t, "inputs.json").write_text(json.dumps({
    "task": (v / "task.txt").read_text(),
    "intent": (v / "intent.txt").read_text(),
    "repos": [f"{t}/cand{k}" for k in range(1, n + 1)],
}))
PY
cd "$T" || exit 1
export TRIAL_ROOT="$T" TMPDIR="$T/tmp" PATH="${AGENT_BIN:-$V/bin}:$PATH" PYTHONPATH="/dev/shm/ab5/runner"
start=$(date +%s)
python -m orchestrator run best_of_n.orc \
  --entry-workflow best_of_n::best-of-n \
  --provider-externs-file providers.json --input-file inputs.json > run.log 2>&1
echo "exit=$? seconds=$(( $(date +%s) - start ))" > "$T/finished"
