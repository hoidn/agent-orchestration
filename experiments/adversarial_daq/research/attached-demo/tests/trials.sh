#!/usr/bin/env bash
# Run the real workflow against a real model, several times, to see what it actually does.
#
#   AO_REPO=/path/to/agent-orchestration tests/trials.sh claude-haiku-5-5 1234 1235 1235
#
# Each trial runs in its own copy of the kit (the runtime allows one active run per workspace),
# all in parallel, under the same confinement as the demo (confine/claude: read the workspace,
# write only its evidence and result, no shell); then one line per trial: the model's label,
# what the check said, the outcome, and the model's own words. Judge those with a stronger
# reader than the model under test.
set -u
cd "$(dirname "$0")/.."
KIT="$PWD"; MODEL=$1; shift
: "${AO_REPO:=$KIT/../agent-orchestration}"
export PYTHONPATH="$AO_REPO${PYTHONPATH:+:$PYTHONPATH}"
OUT=$(mktemp -d "${TMPDIR:-/tmp}/daq-trials.XXXXXX")
i=0
for RUN in "$@"; do
  i=$((i + 1)); WS="$OUT/trial-$i-$RUN"; mkdir -p "$WS"
  (cd "$KIT" && tar -cf - confine fixtures inputs scripts workflows) | tar -xf - -C "$WS"
  (cd "$WS" && PATH="$WS/confine:$PATH" python3 -m orchestrator py run workflows/daq_diagnosis.py --entry-workflow diagnose_and_recover \
      --provider-externs-file inputs/providers.json --command-boundaries-file inputs/commands.json \
      --input-file "inputs/run_$RUN.json" --input "model=$MODEL" > trial.log 2>&1) &
done
wait
for WS in "$OUT"/trial-*; do
  (cd "$WS" && R=$(ls .orchestrate/runs) && python3 - "$R" "$KIT/scripts" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[2])
from show_run import Run
run = Run(sys.argv[1])
values = {name: (step.get("value") or {}) for name, _, step in run.steps()}
verdict, check = values.get("claude", {}), values.get("check_playbook", {})
outcome = (run.state.get("workflow_outputs") or {}).get("variant") or run.state.get("status")
if outcome == "failed" and check.get("variant") == "APPLICABLE":
    outcome = "waiting for approval"
print(f"run {run.header['bound_inputs']['run_number']}  {verdict.get('variant')} {verdict.get('cause', '')}"
      f"  check={check.get('variant')}  outcome={outcome}\n    fix: {verdict.get('fix') or verdict.get('missing')}")
PY
  )
done
echo "trial workspaces (prompts, evidence, model replies): $OUT"
