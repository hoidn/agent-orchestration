#!/usr/bin/env bash
set -u
cd -- /home/ollie/Documents/agent-orchestration/experiments/adversarial_daq
unset PYTHONPATH
while .venv/bin/python - "${1:?supply run ID}" <<'PYCODE'
import json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
result = subprocess.run([sys.executable, '-m', 'orchestrator', 'report', '--run-id', sys.argv[1], '--format', 'json'], capture_output=True, text=True)
if result.returncode:
    print(datetime.now(timezone.utc).isoformat(), 'REPORT_FAILED', result.stderr.strip(), flush=True)
    raise SystemExit(1)
report = json.loads(result.stdout)
Path('artifacts/launch/latest-report.json').write_text(result.stdout)
run = report['run']
step = run.get('current_step') or {}
print(datetime.now(timezone.utc).isoformat(), run['run_id'], run['status'], step.get('name', step), flush=True)
if run['status'] in ('completed', 'failed', 'interrupted', 'suspended'):
    Path('artifacts/launch/final-report.json').write_text(result.stdout)
    print('Observer stopped; no automatic retry or extra provider call.', flush=True)
    raise SystemExit(1)
PYCODE
do
  sleep 30
done
