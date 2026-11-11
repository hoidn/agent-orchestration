#!/usr/bin/env bash
set -euo pipefail
cd -- /home/ollie/Documents/agent-orchestration/experiments/adversarial_daq
unset PYTHONPATH
export PATH="$PWD/deployment/bin:$PWD/.venv/bin:/usr/bin:/bin"
export PYTHONUNBUFFERED=1
export DAQ_CODEX_HOME
DAQ_CODEX_HOME=$(python -c 'import json; print(json.load(open("artifacts/launch/deployment.json"))["provider_home"])')
trap 'rc=$?; printf "%s\n" "$rc" > artifacts/launch/live-resume.exit' EXIT
python -m orchestrator resume "${1:?supply run ID}" --stream-output
