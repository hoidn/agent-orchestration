#!/usr/bin/env bash
set -u

usage() {
  cat <<'EOF'
Usage:
  TARGET=<tmux-pane> RUN_ID=<run-id> WORKSPACE=<repo> scripts/watch_workflow_usage_limit.sh

Environment:
  TARGET                 tmux pane target, for example easyspin-drain-resume:0.0
  RUN_ID                 orchestrator run id to resume
  WORKSPACE              repository root where orchestrator resume should run
  LOG                    watchdog log path (default: /tmp/workflow-usage-watchdog-$RUN_ID.log)
  POLL_SECONDS           monitor interval while workflow is active (default: 60)
  CONDA_SH               conda profile script (default: /home/ollie/miniconda3/etc/profile.d/conda.sh)
  CONDA_ENV              conda environment for workflow process (default: ptycho311)
  AGENT_ORCHESTRATION    path prepended to PYTHONPATH (default: /home/ollie/Documents/agent-orchestration)
  PROVIDER_SHIM_PATH     path prepended to PATH, optional (default: /tmp/easyspin-claude-provider)
  PROVIDER_SHIM          EASYSPIN_WORKFLOW_PROVIDER_SHIM value, optional (default: claude-opus-4-7)
  RESUME_EXTRA_ARGS      extra args for orchestrator resume (default: --stream-output)
  RUN_EXTRA_ARGS         extra args for orchestrator run after provider-limit blocked recovery (default: --stream-output)
  CLAUDE_BIN             Claude CLI used for readiness probes (default: /home/ollie/.local/bin/claude)
  CLAUDE_PROBE_MODEL     Claude model to probe (default: PROVIDER_SHIM or claude-opus-4-7)
  CLAUDE_PROBE_EFFORT    probe effort (default: high)
  PROBE_RETRY_SECONDS    retry delay when no reset time can be parsed (default: 300)
  PROBE_BUFFER_SECONDS   buffer after a parsed reset time before re-probing (default: 90)
  PROBE_TIMEOUT_SECONDS  timeout for one Claude probe attempt (default: 120)
  LIMIT_PATTERN          extended regex for provider limit detection
EOF
}

parse_reset_epoch() {
  local input
  input="$(cat)"
  WATCHDOG_PARSE_TEXT="$input" \
  python - <<'PY'
import os
import re
import subprocess
import sys
import time

text = os.environ.get("WATCHDOG_PARSE_TEXT", "")
now = int(time.time())

snippets = [
    m.group(0)
    for m in re.finditer(
        r"(?is)(?:usage limit|rate limit|hit your limit|limit reached|try again|reset|resets|available|until|after).{0,220}",
        text,
    )
]
if not snippets:
    snippets = [text]

def emit(epoch: int) -> None:
    if epoch < now - 60:
        epoch += 24 * 60 * 60
    print(epoch)
    raise SystemExit(0)

for snippet in snippets:
    match = re.search(
        r"(?:(\d+)\s*(?:h|hr|hrs|hour|hours)(?:\s*(?:and\s*)?(\d+)\s*(?:m|min|mins|minute|minutes))?|(\d+)\s*(?:m|min|mins|minute|minutes))",
        snippet,
        re.I,
    )
    if match and (match.group(1) or match.group(2) or match.group(3)):
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or match.group(3) or 0)
        if hours or minutes:
            emit(now + hours * 3600 + minutes * 60)

    for candidate in re.findall(
        r"(?:at|after|until|resets?)\s+([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4},?\s+\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?(?:\s+[A-Z]{2,5})?|"
        r"\d{4}-\d{2}-\d{2}[ T]\d{1,2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?|"
        r"\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?(?:\s+[A-Z]{2,5})?|"
        r"\d{1,2}\s*(?:AM|PM|am|pm))",
        snippet,
        re.I,
    ):
        try:
            output = subprocess.check_output(["date", "-d", candidate, "+%s"], text=True).strip()
            emit(int(output))
        except Exception:
            pass

raise SystemExit(1)
PY
}

if [[ "${1:-}" == "--parse-reset-epoch" ]]; then
  parse_reset_epoch
  exit $?
fi

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required environment variable: $name" >&2
    usage >&2
    exit 2
  fi
}

require_env TARGET
require_env RUN_ID
require_env WORKSPACE

LOG="${LOG:-/tmp/workflow-usage-watchdog-${RUN_ID}.log}"
POLL_SECONDS="${POLL_SECONDS:-60}"
CONDA_SH="${CONDA_SH:-/home/ollie/miniconda3/etc/profile.d/conda.sh}"
CONDA_ENV="${CONDA_ENV:-ptycho311}"
AGENT_ORCHESTRATION="${AGENT_ORCHESTRATION:-/home/ollie/Documents/agent-orchestration}"
PROVIDER_SHIM_PATH="${PROVIDER_SHIM_PATH:-/tmp/easyspin-claude-provider}"
PROVIDER_SHIM="${PROVIDER_SHIM:-claude-opus-4-7}"
RESUME_EXTRA_ARGS="${RESUME_EXTRA_ARGS:---stream-output}"
RUN_EXTRA_ARGS="${RUN_EXTRA_ARGS:---stream-output}"
CLAUDE_BIN="${CLAUDE_BIN:-/home/ollie/.local/bin/claude}"
CLAUDE_PROBE_MODEL="${CLAUDE_PROBE_MODEL:-${PROVIDER_SHIM:-claude-opus-4-7}}"
CLAUDE_PROBE_EFFORT="${CLAUDE_PROBE_EFFORT:-high}"
CLAUDE_PROBE_PROMPT="${CLAUDE_PROBE_PROMPT:-Reply exactly: OK}"
PROBE_RETRY_SECONDS="${PROBE_RETRY_SECONDS:-300}"
PROBE_BUFFER_SECONDS="${PROBE_BUFFER_SECONDS:-90}"
PROBE_TIMEOUT_SECONDS="${PROBE_TIMEOUT_SECONDS:-120}"
LIMIT_PATTERN="${LIMIT_PATTERN:-usage limit|rate limit|hit your limit|you.?ve hit your limit|too many requests|insufficient[_ -]?quota|quota exceeded|credit balance|maximum.*usage|limit reached|try again later|429([^0-9]|$)}"
RUN_ROOT="${WORKSPACE}/.orchestrate/runs/${RUN_ID}"
WORKFLOW_FILE=""
BOUND_INPUT_ARGS=""
PROBE_OUTPUT=""
PROBE_EXIT_CODE=0
PROBE_RESET_EPOCH=""

log() {
  printf '%s %s\n' "$(date -Is)" "$*" >> "$LOG"
}

quote() {
  printf '%q' "$1"
}

target_session() {
  printf '%s\n' "$TARGET" | sed 's/:.*//'
}

target_exists() {
  tmux list-panes -a -F '#{session_name}:#{window_index}.#{pane_index}' 2>/dev/null | grep -Fxq "$TARGET"
}

capture_target() {
  tmux capture-pane -p -J -t "$TARGET" -S -260 2>&1 || true
}

clear_target_pane() {
  tmux send-keys -t "$TARGET" C-l 2>/dev/null || true
  sleep 0.2
  tmux clear-history -t "$TARGET" 2>/dev/null || true
}

recent_limit_log_hits() {
  find "$RUN_ROOT" \
    -type f \( -name '*.stderr' -o -name '*.stdout' -o -name '*.log' -o -name '*.txt' \) \
    -mmin -10 -print0 2>/dev/null \
    | xargs -0 -r rg -i "$LIMIT_PATTERN" 2>/dev/null || true
}

write_state_summary() {
  python - "$RUN_ROOT/state.json" >> "$LOG" 2>&1 <<'PY'
import json
import sys
from pathlib import Path

p = Path(sys.argv[1])
try:
    state = json.loads(p.read_text(encoding="utf-8"))
    print(
        "state",
        state.get("status"),
        "updated_at",
        state.get("updated_at"),
        "current_step",
        state.get("current_step"),
    )
except Exception as exc:
    print("state read failed", repr(exc))
PY
}

wait_for_target_shell() {
  local i cmd
  for i in $(seq 1 90); do
    cmd="$(tmux display-message -p -t "$TARGET" '#{pane_current_command}' 2>/dev/null || true)"
    case "$cmd" in
      bash|zsh|fish|sh)
        return 0
        ;;
    esac
    sleep 2
  done
  return 1
}

target_is_shell() {
  local cmd
  cmd="$(tmux display-message -p -t "$TARGET" '#{pane_current_command}' 2>/dev/null || true)"
  case "$cmd" in
    bash|zsh|fish|sh)
      return 0
      ;;
  esac
  return 1
}

sleep_with_target_checks() {
  local remaining="$1"
  local step
  while (( remaining > 0 )); do
    if ! target_exists; then
      log "target pane missing while waiting; watchdog exiting"
      exit 0
    fi
    if ! target_is_shell; then
      log "target is no longer at a shell while waiting; assuming it was manually resumed"
      return 2
    fi
    step="$remaining"
    if (( step > 60 )); then
      step=60
    fi
    sleep "$step"
    remaining=$(( remaining - step ))
  done
  return 0
}

resume_command() {
  local cmd
  cmd="cd $(quote "$WORKSPACE")"
  cmd+=" && source $(quote "$CONDA_SH")"
  cmd+=" && conda activate $(quote "$CONDA_ENV")"
  cmd+=" && export PYTHONPATH=$(quote "$AGENT_ORCHESTRATION"):\${PYTHONPATH:-}"
  if [[ -n "$PROVIDER_SHIM_PATH" ]]; then
    cmd+=" && export PATH=$(quote "$PROVIDER_SHIM_PATH"):\$PATH"
  fi
  if [[ -n "$PROVIDER_SHIM" ]]; then
    cmd+=" && export EASYSPIN_WORKFLOW_PROVIDER_SHIM=$(quote "$PROVIDER_SHIM")"
  fi
  cmd+=" && python -m orchestrator resume $(quote "$RUN_ID") ${RESUME_EXTRA_ARGS}"
  printf '%s\n' "$cmd"
}

refresh_run_metadata() {
  local state_path="$RUN_ROOT/state.json"
  if [[ ! -f "$state_path" ]]; then
    return 1
  fi
  WORKFLOW_FILE="$(
    python - "$state_path" <<'PY'
import json
import sys
from pathlib import Path

state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(state.get("workflow_file", ""))
PY
  )"
  BOUND_INPUT_ARGS="$(
    python - "$state_path" <<'PY'
import json
import shlex
import sys
from pathlib import Path

state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for key, value in (state.get("bound_inputs") or {}).items():
    if isinstance(value, (str, int, float, bool)):
        print("--input " + shlex.quote(f"{key}={value}"))
PY
  )"
}

run_command() {
  refresh_run_metadata || return 1
  if [[ -z "$WORKFLOW_FILE" ]]; then
    return 1
  fi
  local cmd
  cmd="cd $(quote "$WORKSPACE")"
  cmd+=" && source $(quote "$CONDA_SH")"
  cmd+=" && conda activate $(quote "$CONDA_ENV")"
  cmd+=" && export PYTHONPATH=$(quote "$AGENT_ORCHESTRATION"):\${PYTHONPATH:-}"
  if [[ -n "$PROVIDER_SHIM_PATH" ]]; then
    cmd+=" && export PATH=$(quote "$PROVIDER_SHIM_PATH"):\$PATH"
  fi
  if [[ -n "$PROVIDER_SHIM" ]]; then
    cmd+=" && export EASYSPIN_WORKFLOW_PROVIDER_SHIM=$(quote "$PROVIDER_SHIM")"
  fi
  cmd+=" && python -m orchestrator run $(quote "$WORKFLOW_FILE") ${BOUND_INPUT_ARGS//$'\n'/ } ${RUN_EXTRA_ARGS}"
  printf '%s\n' "$cmd"
}

refresh_run_id_from_latest_running() {
  local new_run_id
  new_run_id="$(
    python - "$WORKSPACE" "$WORKFLOW_FILE" <<'PY'
import json
import sys
from pathlib import Path

workspace = Path(sys.argv[1])
workflow_file = sys.argv[2]
candidates = []
for state_path in (workspace / ".orchestrate" / "runs").glob("*/state.json"):
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        continue
    if workflow_file and state.get("workflow_file") != workflow_file:
        continue
    if state.get("status") != "running":
        continue
    candidates.append((state_path.stat().st_mtime, state.get("run_id"), state_path))
if candidates:
    candidates.sort()
    print(candidates[-1][1])
PY
  )"
  if [[ -n "$new_run_id" && "$new_run_id" != "$RUN_ID" ]]; then
    log "watchdog switching from completed run_id=$RUN_ID to new running run_id=$new_run_id"
    RUN_ID="$new_run_id"
    RUN_ROOT="${WORKSPACE}/.orchestrate/runs/${RUN_ID}"
  fi
}

requeue_provider_limit_blocked_tranche() {
  python - "$RUN_ROOT/state.json" "$WORKSPACE" "$RUN_ID" <<'PY'
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

state_path = Path(sys.argv[1])
workspace = Path(sys.argv[2])
run_id = sys.argv[3]
if not state_path.is_file():
    raise SystemExit(1)

state = json.loads(state_path.read_text(encoding="utf-8"))
if state.get("status") != "completed":
    raise SystemExit(1)
outputs = state.get("workflow_outputs") or {}
if outputs.get("drain_status") != "BLOCKED":
    raise SystemExit(1)

state_text = json.dumps(state, ensure_ascii=False)
limit_pattern = re.compile(
    r"usage limit|rate limit|hit your limit|you.?ve hit your limit|too many requests|"
    r"insufficient[_ -]?quota|quota exceeded|credit balance|maximum.*usage|"
    r"limit reached|try again later|429(?:[^0-9]|$)",
    re.I,
)
if not limit_pattern.search(state_text):
    raise SystemExit(1)

bound_inputs = state.get("bound_inputs") or {}
manifest_rel = bound_inputs.get("tranche_manifest_target_path") or outputs.get("tranche_manifest_path")
if not isinstance(manifest_rel, str):
    raise SystemExit(1)
manifest_path = (workspace / manifest_rel).resolve()
if not manifest_path.is_relative_to(workspace.resolve()) or not manifest_path.is_file():
    raise SystemExit(1)

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
tranches = manifest.get("tranches")
if not isinstance(tranches, list):
    raise SystemExit(1)

chosen = None
for tranche in tranches:
    if not isinstance(tranche, dict):
        continue
    if tranche.get("status") != "blocked":
        continue
    if tranche.get("last_item_outcome") != "SKIPPED_AFTER_IMPLEMENTATION":
        continue
    execution_report = tranche.get("last_execution_report_path")
    summary = tranche.get("last_item_summary_path")
    execution_text = ""
    summary_payload = {}
    if isinstance(execution_report, str):
        p = workspace / execution_report
        if p.is_file():
            execution_text = p.read_text(encoding="utf-8", errors="replace")
    if isinstance(summary, str):
        p = workspace / summary
        if p.is_file():
            try:
                summary_payload = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                summary_payload = {}
    if "failed before producing a report" in execution_text.lower() or summary_payload.get("failed_phase") == "implementation":
        chosen = tranche
        break

if chosen is None:
    raise SystemExit(1)

previous = {
    "status": chosen.get("status"),
    "last_item_outcome": chosen.get("last_item_outcome"),
    "last_execution_report_path": chosen.get("last_execution_report_path"),
    "last_item_summary_path": chosen.get("last_item_summary_path"),
}
chosen["status"] = "pending"
chosen["provider_limit_recovery"] = {
    "requeued_at": datetime.now(timezone.utc).isoformat(),
    "source_run_id": run_id,
    "previous": previous,
    "reason": "provider_limit_during_implementation",
}
for key in ("last_item_outcome", "last_execution_report_path", "last_item_summary_path"):
    chosen.pop(key, None)

tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
tmp.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
tmp.replace(manifest_path)
print(chosen.get("tranche_id", ""))
PY
}

handle_completed_provider_limit_blocked_run() {
  local tranche_id cmd
  tranche_id="$(requeue_provider_limit_blocked_tranche 2>/dev/null || true)"
  if [[ -z "$tranche_id" ]]; then
    return 1
  fi

  log "requeued provider-limit blocked tranche=$tranche_id from completed run_id=$RUN_ID"
  if ! wait_until_claude_ready; then
    log "skipping fresh drain relaunch because target appears manually resumed"
    return 0
  fi
  if ! wait_for_target_shell; then
    log "target is not at a shell after provider-limit recovery wait; assuming it was manually resumed"
    return 0
  fi

  cmd="$(run_command)"
  if [[ -z "$cmd" ]]; then
    log "failed to build fresh drain run command after provider-limit recovery"
    return 1
  fi
  clear_target_pane
  log "starting fresh drain after provider-limit recovery: $cmd"
  tmux send-keys -t "$TARGET" -l "$cmd"
  tmux send-keys -t "$TARGET" Enter
  sleep 8
  refresh_run_id_from_latest_running
  return 0
}

run_claude_probe_once() {
  PROBE_OUTPUT=""
  PROBE_EXIT_CODE=0
  PROBE_RESET_EPOCH=""

  log "probing Claude readiness with model=$CLAUDE_PROBE_MODEL effort=$CLAUDE_PROBE_EFFORT"
  PROBE_OUTPUT="$(
    cd "$WORKSPACE" && timeout "$PROBE_TIMEOUT_SECONDS" "$CLAUDE_BIN" \
      -p \
      --model "$CLAUDE_PROBE_MODEL" \
      --effort "$CLAUDE_PROBE_EFFORT" \
      --dangerously-skip-permissions \
      --no-session-persistence \
      --output-format text \
      "$CLAUDE_PROBE_PROMPT" 2>&1
  )"
  PROBE_EXIT_CODE=$?

  {
    echo "--- claude probe exit=$PROBE_EXIT_CODE ---"
    printf '%s\n' "$PROBE_OUTPUT" | tail -n 80
  } >> "$LOG"

  if [[ "$PROBE_EXIT_CODE" -eq 0 ]] && ! printf '%s\n' "$PROBE_OUTPUT" | grep -Eiq "$LIMIT_PATTERN"; then
    log "Claude readiness probe succeeded"
    return 0
  fi

  PROBE_RESET_EPOCH="$(printf '%s\n' "$PROBE_OUTPUT" | parse_reset_epoch 2>/dev/null || true)"
  if [[ -n "$PROBE_RESET_EPOCH" ]]; then
    log "Claude readiness probe still limited; parsed reset epoch=$PROBE_RESET_EPOCH ($(date -d "@$PROBE_RESET_EPOCH" -Is 2>/dev/null || true))"
  else
    log "Claude readiness probe still limited or failed; no reset time parsed"
  fi
  return 1
}

wait_until_claude_ready() {
  local now sleep_for
  while true; do
    if ! target_exists; then
      log "target pane missing before Claude probe; watchdog exiting"
      exit 0
    fi
    if ! target_is_shell; then
      log "target is not at a shell before Claude probe; assuming it was manually resumed"
      return 2
    fi
    if run_claude_probe_once; then
      return 0
    fi

    now="$(date +%s)"
    if [[ -n "$PROBE_RESET_EPOCH" ]] && [[ "$PROBE_RESET_EPOCH" =~ ^[0-9]+$ ]]; then
      sleep_for=$(( PROBE_RESET_EPOCH - now + PROBE_BUFFER_SECONDS ))
      if (( sleep_for < PROBE_RETRY_SECONDS )); then
        sleep_for="$PROBE_RETRY_SECONDS"
      fi
      log "sleeping ${sleep_for}s until parsed Claude reset window, then probing again"
    else
      sleep_for="$PROBE_RETRY_SECONDS"
      log "sleeping ${sleep_for}s before next Claude readiness probe"
    fi

    sleep_with_target_checks "$sleep_for" || return 2
  done
}

interrupt_wait_and_resume() {
  local pane_out="$1"
  local log_hits="$2"

  log "detected provider usage/rate limit; interrupting $TARGET"
  {
    echo "--- recent pane ---"
    printf '%s\n' "$pane_out" | tail -n 120
    if [[ -n "$log_hits" ]]; then
      echo "--- recent log hits ---"
      printf '%s\n' "$log_hits"
    fi
  } >> "$LOG"

  tmux send-keys -t "$TARGET" C-c
  sleep 4
  if ! wait_for_target_shell; then
    log "target did not return to a shell after first interrupt; sending one more Ctrl-C"
    tmux send-keys -t "$TARGET" C-c
    sleep 4
    wait_for_target_shell || log "target still not at a recognized shell; provider-limit recovery will skip relaunch if it remains active"
  fi
  write_state_summary

  if ! wait_until_claude_ready; then
    log "skipping automatic relaunch because target appears manually resumed"
    return 0
  fi

  if ! target_exists; then
    log "target pane missing after provider-limit wait; watchdog exiting"
    exit 0
  fi

  if ! wait_for_target_shell; then
    log "target is not at a shell after provider-limit wait; assuming it was manually resumed, skipping automatic relaunch"
    return 0
  fi

  clear_target_pane
  local cmd
  cmd="$(resume_command)"
  log "relaunching workflow: $cmd"
  tmux send-keys -t "$TARGET" -l "$cmd"
  tmux send-keys -t "$TARGET" Enter
  sleep "$POLL_SECONDS"
}

mkdir -p "$(dirname "$LOG")"
log "watchdog started for target=$TARGET run_id=$RUN_ID workspace=$WORKSPACE probe_model=$CLAUDE_PROBE_MODEL"

while true; do
  if ! tmux has-session -t "$(target_session)" 2>/dev/null || ! target_exists; then
    log "target pane missing; watchdog exiting"
    exit 0
  fi

  pane_out="$(capture_target)"
  log_hits="$(recent_limit_log_hits)"
  if handle_completed_provider_limit_blocked_run; then
    continue
  fi
  if printf '%s\n%s\n' "$pane_out" "$log_hits" | grep -Eiq "$LIMIT_PATTERN"; then
    interrupt_wait_and_resume "$pane_out" "$log_hits"
    continue
  fi

  write_state_summary
  sleep "$POLL_SECONDS"
done
