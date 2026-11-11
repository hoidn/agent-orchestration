#!/usr/bin/env bash
set -euo pipefail
cd -- /home/ollie/Documents/agent-orchestration/experiments/adversarial_daq
unset PYTHONPATH
export PATH="$PWD/deployment/bin:$PWD/.venv/bin:/usr/bin:/bin"
export PYTHONUNBUFFERED=1
export DAQ_CODEX_HOME
DAQ_CODEX_HOME=$(python -c 'import json; print(json.load(open("artifacts/launch/deployment.json"))["provider_home"])')
trap 'rc=$?; printf "%s\n" "$rc" > artifacts/launch/live.exit' EXIT
python -m orchestrator run adversarial_live.orc --entry-workflow adversarial_live::run \
  --provider-externs-file deployment/providers.json --prompt-externs-file prompts.json \
  --command-boundaries-file deployment/commands.json --input-file deployment/inputs.json \
  --stream-output
