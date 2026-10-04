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
  RESUME_LOCK_WAIT_SECONDS
                         bound on waiting for another active run in WORKSPACE to end (default: 3600).
                         A resume or run refused with workspace_run_already_active is sent again every
                         POLL_SECONDS; once this bound is reached the watchdog logs the refusal and
                         exits 1, leaving the target stopped. Other failures are not retried.
  CONDA_SH               conda profile script (default: /home/ollie/miniconda3/etc/profile.d/conda.sh)
  CONDA_ENV              conda environment for workflow process (default: ptycho311)
  AGENT_ORCHESTRATION    path prepended to PYTHONPATH (default: /home/ollie/Documents/agent-orchestration)
  PROVIDER_SHIM_PATH     path prepended to PATH, optional (default: /tmp/easyspin-claude-provider)
  PROVIDER_SHIM          EASYSPIN_WORKFLOW_PROVIDER_SHIM value, optional (default: claude-opus-4-7)
  IMPLEMENTATION_PROVIDER_SHIM
                         EASYSPIN_IMPLEMENTATION_PROVIDER_SHIM value, optional (default: claude-sonnet-4-6)
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
RESUME_LOCK_WAIT_SECONDS="${RESUME_LOCK_WAIT_SECONDS:-3600}"
CONDA_SH="${CONDA_SH:-/home/ollie/miniconda3/etc/profile.d/conda.sh}"
CONDA_ENV="${CONDA_ENV:-ptycho311}"
AGENT_ORCHESTRATION="${AGENT_ORCHESTRATION:-/home/ollie/Documents/agent-orchestration}"
export PYTHONPATH="${AGENT_ORCHESTRATION}:${PYTHONPATH:-}"
PROVIDER_SHIM_PATH="${PROVIDER_SHIM_PATH:-/tmp/easyspin-claude-provider}"
PROVIDER_SHIM="${PROVIDER_SHIM:-claude-opus-4-7}"
IMPLEMENTATION_PROVIDER_SHIM="${IMPLEMENTATION_PROVIDER_SHIM:-claude-sonnet-4-6}"
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
PENDING_CMD=""
PENDING_TOKEN=""
LOCK_WAITED=0

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

is_evaluated_state() {
  python -c 'import json,sys; from orchestrator.workflow.evaluated.authority import PROFILE; raise SystemExit(json.load(sys.stdin).get("result_persistence_profile") != PROFILE)' <<< "$1"
}

recent_limit_log_hits() {
  local state
  state="$(read_run_state "$RUN_ROOT" 2>> "$LOG")" || return 0
  if ! is_evaluated_state "$state"; then
    find "$RUN_ROOT" \
      -type f \( -name '*.stderr' -o -name '*.stdout' -o -name '*.log' -o -name '*.txt' \) \
      -mmin -10 -print0 2>/dev/null \
      | xargs -0 -r rg -i "$LIMIT_PATTERN" 2>/dev/null || true
    return 0
  fi
  python -c "$(cat <<'PY'
import json, re, sys
from pathlib import Path

def selected_row(state):
    current = state["current_step"]
    identity = current["identity"] if current is not None else state["next_effect"]
    if identity is None:
        identity = next((key for key, row in reversed(state["steps"].items()) if row["status"] != "invalidated"), None)
    return state["steps"].get(identity, {})

def stream_hits(root, row, pattern):
    paths = () if not row or row["status"] == "invalidated" else ("stdout.txt", "stderr.txt")
    for name in paths:
        try:
            path = (root / Path(row["result_path"]).parent / name).resolve(strict=True)
            path.relative_to(root)
            if not path.is_file() or path.name.endswith("prompt.txt") or "provider_sessions" in path.parts:
                continue
            with path.open(encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    if pattern.search(line):
                        print(line.rstrip())
        except (OSError, ValueError):
            continue

state = json.load(sys.stdin)
pattern = re.compile(sys.argv[2], re.I)
row = selected_row(state)
error = state["error"] or (None if row.get("status") == "invalidated" else row.get("error"))
if error and pattern.search(json.dumps(error, ensure_ascii=False)):
    print(json.dumps(error, ensure_ascii=False))
stream_hits(Path(sys.argv[1]).resolve(), row, pattern)
PY
)" "$RUN_ROOT" "$LIMIT_PATTERN" <<< "$state"
}

read_run_state() {
  python - "$1" "$WORKSPACE" <<'PY'
import json
import sys
from pathlib import Path
from orchestrator.workflow.evaluated.views import has_evaluated_authority, load_evaluated_view

try:
    root = Path(sys.argv[1]).resolve()
    root.relative_to(Path(sys.argv[2]).resolve())
    if has_evaluated_authority(root):
        state = load_evaluated_view(root)
    else:
        try:
            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            print(f"legacy state read failed: {exc}", file=sys.stderr)
            state = {}
    print(json.dumps(state, ensure_ascii=False, allow_nan=False))
except (OSError, ValueError) as exc:
    raise SystemExit(f"state read failed {getattr(exc, 'code', 'memo_inconsistent')}: {exc}")
PY
}

write_state_summary() {
  read_run_state "$RUN_ROOT" 2>> "$LOG" | python -c '
import json, sys
try:
    state = json.load(sys.stdin)
    print("state", state.get("status"), "updated_at", state.get("updated_at"), "current_step", state.get("current_step"))
except ValueError:
    pass
' >> "$LOG" 2>&1
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

# Type PENDING_CMD into the target pane as a new attempt. The attempt prints a start line
# and an exit line that carry a token unique to it.
start_attempt() {
  PENDING_TOKEN="$(date +%s%N)"
  clear_target_pane
  log "relaunching workflow: $PENDING_CMD"
  tmux send-keys -t "$TARGET" -l "echo orchestrator-attempt-$PENDING_TOKEN; $PENDING_CMD; echo \"orchestrator-exit-$PENDING_TOKEN=\$?\""
  tmux send-keys -t "$TARGET" Enter
}

# Print what the pending attempt printed, from its start line through its exit line. Reads
# the pane's whole history, so an exit line that later output pushed out of capture_target's
# lines is still found. Fails while the attempt has not exited.
attempt_output() {
  tmux capture-pane -p -J -t "$TARGET" -S - 2>/dev/null | awk -v token="$PENDING_TOKEN" '
    { sub(/[ \t]+$/, "") }
    $0 == "orchestrator-attempt-" token { started = 1; out = ""; next }
    started { out = out $0 "\n" }
    started && $0 ~ ("orchestrator-exit-" token "=[0-9]+$") { printf "%s", out; found = 1; exit }
    END { exit !found }
  '
}

# Follow the pending attempt for up to $1 seconds. An attempt still running then was admitted;
# the main loop follows it again every poll, so a later exit is still decided here. While the
# workspace lock refuses the command it is sent again every POLL_SECONDS, for at most
# RESUME_LOCK_WAIT_SECONDS; any other exit ends the command.
follow_orchestrator_command() {
  local seconds="$1" deadline output refusal
  while true; do
    deadline=$(( SECONDS + seconds ))
    until output="$(attempt_output)"; do
      (( SECONDS < deadline )) || return 0
      sleep 1
    done
    PENDING_TOKEN=""
    refusal="$(printf '%s\n' "$output" | grep -Eo 'workspace_run_already_active: (run [^ ]+ is active|another run is starting)' | tail -n 1)"
    if [[ -z "$refusal" ]]; then
      log "workflow command ended: ${output##*$'\n'}"
      return 0
    fi
    if (( LOCK_WAITED >= RESUME_LOCK_WAIT_SECONDS )); then
      log "still refused after ${LOCK_WAITED}s (RESUME_LOCK_WAIT_SECONDS=$RESUME_LOCK_WAIT_SECONDS): $refusal; watchdog exiting"
      exit 1
    fi
    log "refused: $refusal; retrying in ${POLL_SECONDS}s (waited ${LOCK_WAITED}s of ${RESUME_LOCK_WAIT_SECONDS}s)"
    sleep_with_target_checks "$POLL_SECONDS" || return 0
    LOCK_WAITED=$(( LOCK_WAITED + POLL_SECONDS ))
    start_attempt
    seconds="$POLL_SECONDS"
  done
}

# Send an orchestrator run/resume command to the target pane and follow it for one poll.
send_orchestrator_command() {
  PENDING_CMD="$1"
  LOCK_WAITED=0
  start_attempt
  follow_orchestrator_command "$POLL_SECONDS"
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
  if [[ -n "$IMPLEMENTATION_PROVIDER_SHIM" ]]; then
    cmd+=" && export EASYSPIN_IMPLEMENTATION_PROVIDER_SHIM=$(quote "$IMPLEMENTATION_PROVIDER_SHIM")"
  fi
  cmd+=" && python -m orchestrator resume $(quote "$RUN_ID") ${RESUME_EXTRA_ARGS}"
  printf '%s\n' "$cmd"
}

refresh_run_metadata() {
  local state
  state="$(read_run_state "$RUN_ROOT" 2>> "$LOG")" || return 1
  if is_evaluated_state "$state"; then
    return 1
  fi
  WORKFLOW_FILE="$(python -c 'import json,sys; print(json.load(sys.stdin).get("workflow_file", ""))' <<< "$state")" || return 1
  BOUND_INPUT_ARGS="$(python -c "$(cat <<'PY'
import json, shlex, sys
state = json.load(sys.stdin)
for key, value in (state.get("bound_inputs") or {}).items():
    if isinstance(value, (str, int, float, bool)):
        print("--input " + shlex.quote(f"{key}={value}"))
PY
)" <<< "$state")"
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
  if [[ -n "$IMPLEMENTATION_PROVIDER_SHIM" ]]; then
    cmd+=" && export EASYSPIN_IMPLEMENTATION_PROVIDER_SHIM=$(quote "$IMPLEMENTATION_PROVIDER_SHIM")"
  fi
  cmd+=" && python -m orchestrator run $(quote "$WORKFLOW_FILE") ${BOUND_INPUT_ARGS//$'\n'/ } ${RUN_EXTRA_ARGS}"
  printf '%s\n' "$cmd"
}

refresh_run_id_from_latest_running() {
  local new_run_id
  new_run_id="$(python - "$WORKSPACE" "$WORKFLOW_FILE" <<'PY'
import json, sys
from datetime import datetime
from pathlib import Path
from orchestrator.workflow.evaluated.views import has_evaluated_authority, load_evaluated_view

workspace = Path(sys.argv[1]).resolve()
workflow_file = sys.argv[2]

def candidate(path):
    root = path.resolve(strict=True)
    root.relative_to(workspace)
    if has_evaluated_authority(root):
        state = load_evaluated_view(root)
        if state["status"] not in {"running", "settling"}:
            return None
        try:
            rank = datetime.fromisoformat(state["started_at"]).timestamp()
        except ValueError:
            rank = 0
    else:
        state_path = root / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("status") != "running":
            return None
        rank = state_path.stat().st_mtime
    if workflow_file and state.get("workflow_file") != workflow_file:
        return None
    return rank, state.get("run_id"), path

candidates = []
for path in (workspace / ".orchestrate/runs").iterdir():
    try:
        item = candidate(path)
    except (OSError, ValueError):
        continue
    if item is not None:
        candidates.append(item)
if candidates:
    print(max(candidates)[1])
PY
  )"
  if [[ -n "$new_run_id" && "$new_run_id" != "$RUN_ID" ]]; then
    log "watchdog switching from completed run_id=$RUN_ID to new running run_id=$new_run_id"
    RUN_ID="$new_run_id"
    RUN_ROOT="${WORKSPACE}/.orchestrate/runs/${RUN_ID}"
  fi
}

requeue_provider_limit_blocked_tranche() {
  local state
  state="$(read_run_state "$RUN_ROOT" 2>> "$LOG")" || return 1
  if is_evaluated_state "$state"; then
    return 1
  fi
  python -c "$(cat <<'PY'
import json, re, sys
from datetime import datetime, timezone
from pathlib import Path

workspace = Path(sys.argv[1])
run_id = sys.argv[2]
state = json.load(sys.stdin)

def manifest_path(state):
    outputs = state.get("workflow_outputs") or {}
    if state.get("status") != "completed" or not isinstance(outputs, dict) or outputs.get("drain_status") != "BLOCKED":
        raise SystemExit(1)
    pattern = re.compile(r"usage limit|rate limit|hit your limit|you.?ve hit your limit|too many requests|"
        r"insufficient[_ -]?quota|quota exceeded|credit balance|maximum.*usage|"
        r"limit reached|try again later|429(?:[^0-9]|$)", re.I)
    if not pattern.search(json.dumps(state, ensure_ascii=False)):
        raise SystemExit(1)
    bound_inputs = state.get("bound_inputs") or {}
    relative = bound_inputs.get("tranche_manifest_target_path") or outputs.get("tranche_manifest_path")
    if not isinstance(relative, str):
        raise SystemExit(1)
    path = (workspace / relative).resolve()
    if not path.is_relative_to(workspace.resolve()) or not path.is_file():
        raise SystemExit(1)
    return path

def implementation_failed(tranche):
    execution_report = tranche.get("last_execution_report_path")
    summary = tranche.get("last_item_summary_path")
    execution_text = ""
    summary_payload = {}
    if isinstance(execution_report, str):
        path = workspace / execution_report
        if path.is_file():
            execution_text = path.read_text(encoding="utf-8", errors="replace")
    if isinstance(summary, str):
        path = workspace / summary
        if path.is_file():
            try:
                summary_payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                summary_payload = {}
    return "failed before producing a report" in execution_text.lower() or summary_payload.get("failed_phase") == "implementation"

def blocked_tranche(tranches):
    if not isinstance(tranches, list):
        raise SystemExit(1)
    for tranche in tranches:
        if not isinstance(tranche, dict):
            continue
        if tranche.get("status") != "blocked" or tranche.get("last_item_outcome") != "SKIPPED_AFTER_IMPLEMENTATION":
            continue
        if implementation_failed(tranche):
            return tranche
    raise SystemExit(1)

path = manifest_path(state)
manifest = json.loads(path.read_text(encoding="utf-8"))
chosen = blocked_tranche(manifest.get("tranches"))
previous = {key: chosen.get(key) for key in ("status", "last_item_outcome", "last_execution_report_path", "last_item_summary_path")}
chosen["status"] = "pending"
chosen["provider_limit_recovery"] = {"requeued_at": datetime.now(timezone.utc).isoformat(),
    "source_run_id": run_id, "previous": previous, "reason": "provider_limit_during_implementation"}
for key in ("last_item_outcome", "last_execution_report_path", "last_item_summary_path"):
    chosen.pop(key, None)
tmp = path.with_suffix(path.suffix + ".tmp")
tmp.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
tmp.replace(path)
print(chosen.get("tranche_id", ""))
PY
)" "$WORKSPACE" "$RUN_ID" <<< "$state"
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
  log "starting fresh drain after provider-limit recovery"
  send_orchestrator_command "$cmd"
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

  send_orchestrator_command "$(resume_command)"
}

mkdir -p "$(dirname "$LOG")"
log "watchdog started for target=$TARGET run_id=$RUN_ID workspace=$WORKSPACE probe_model=$CLAUDE_PROBE_MODEL"

while true; do
  if ! tmux has-session -t "$(target_session)" 2>/dev/null || ! target_exists; then
    log "target pane missing; watchdog exiting"
    exit 0
  fi

  if [[ -n "$PENDING_TOKEN" ]]; then
    follow_orchestrator_command 0
  fi
  pane_out="$(capture_target)"
  state="$(read_run_state "$RUN_ROOT" 2>> "$LOG")"
  if [[ -z "$state" ]]; then
    sleep "$POLL_SECONDS"
    continue
  fi
  if is_evaluated_state "$state"; then
    pane_out=""
  fi
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
