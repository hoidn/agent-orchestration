#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
export PATH="$PWD/.venv/bin:$PATH"
python_bin="$PWD/.venv/bin/python"
frontend=(adversarial.orc --entry-workflow adversarial::run
  --provider-externs-file providers.json --prompt-externs-file prompts.json
  --command-boundaries-file commands.json)
case "${1:-compile}" in
  compile) exec "$python_bin" -m orchestrator compile "${frontend[@]}" ;;
  dry-run) exec "$python_bin" -m orchestrator run "${frontend[@]}" --input-file inputs.json --dry-run ;;
  run) exec "$python_bin" -m orchestrator run "${frontend[@]}" --input-file inputs.json ;;
  resume) exec "$python_bin" -m orchestrator resume "${2:?supply run ID}" ;;
  report) exec "$python_bin" -m orchestrator report --run-id "${2:?supply run ID}" --format json ;;
  test) exec "$python_bin" -m pytest tests -q ;;
  *) echo 'Usage: bash run.sh compile|dry-run|run|resume RUN_ID|report RUN_ID|test' >&2; exit 2 ;;
esac
