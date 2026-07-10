#!/usr/bin/env bash
set -u

usage() {
  cat <<'EOF'
Usage:
  scripts/watch_codex_session.sh <codex-session-id>
  scripts/watch_codex_session.sh --check <codex-session-id>

Watches a live codex TUI session and auto-types a prompt into its tmux pane
whenever the session stops on a trigger pattern (default: a provider
"at capacity" error). Detection is two-layer:
  1. edge-triggered on new rollout-file bytes matching PATTERN, and
  2. fallback on PATTERN visible in the pane while the TUI is idle
     (rate-limited by PANE_COOLDOWN).
A send only happens while the TUI is idle (no BUSY_PATTERN on screen). The
target pane is re-resolved every poll from whichever codex process holds the
session's rollout file open, so the watcher survives codex restarts and pane
moves. The pane is looked up on the default tmux server even if the watcher
itself runs inside tmux on another socket.

--check resolves the session (rollout, driver pid, pane, busy/idle) and exits.

Run it forever in a detached tmux session, e.g.:
  tmux new-session -d -s codex-watch-<shortid> \
    "while true; do ~/Documents/agent-orchestration/scripts/watch_codex_session.sh <session-id>; sleep 10; done"

Environment:
  PROMPT         text typed + Enter on trigger (default: proceed)
  PATTERN        case-insensitive grep -E pattern for the stop condition (default: at capacity)
  BUSY_PATTERN   pattern marking an in-flight turn on screen (default: esc to interrupt)
  POLL_SECONDS   poll interval (default: 20)
  PANE_COOLDOWN  min seconds between pane-text-triggered sends (default: 600)
  HEARTBEAT      seconds between alive log lines (default: 1800)
  LOG            log path (default: /tmp/codex-session-watch-<first 8 chars of id>.log)
  ROLLOUT        explicit rollout path (default: newest ~/.codex/sessions/**/rollout-*<id>.jsonl)
  PREFERRED_PID  pin the driver codex PID (default: newest codex process holding the rollout)
EOF
}

CHECK_ONLY=0
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi
if [[ "${1:-}" == "--check" ]]; then
  CHECK_ONLY=1
  shift
fi
if [[ -z "${1:-}" ]]; then
  echo "Missing required argument: codex session id" >&2
  usage >&2
  exit 2
fi

SESSION_ID="$1"
SHORT_ID="${SESSION_ID:0:8}"
PROMPT="${PROMPT:-proceed}"
PATTERN="${PATTERN:-at capacity}"
BUSY_PATTERN="${BUSY_PATTERN:-esc to interrupt}"
POLL_SECONDS="${POLL_SECONDS:-20}"
PANE_COOLDOWN="${PANE_COOLDOWN:-600}"
HEARTBEAT="${HEARTBEAT:-1800}"
LOG="${LOG:-/tmp/codex-session-watch-${SHORT_ID}.log}"
PREFERRED_PID="${PREFERRED_PID:-}"

if [[ -z "${ROLLOUT:-}" ]]; then
  ROLLOUT="$(
    find "$HOME/.codex/sessions" -type f -name "rollout-*${SESSION_ID}.jsonl" \
      -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-
  )"
fi
if [[ -z "$ROLLOUT" || ! -f "$ROLLOUT" ]]; then
  echo "No rollout file found for session $SESSION_ID under ~/.codex/sessions" >&2
  exit 2
fi

log() {
  printf '%s %s\n' "$(date -Is)" "$*" >> "$LOG"
}

# The codex pane lives on the user's default tmux server; strip $TMUX so this
# works even when the watcher runs inside tmux on another socket.
utmux() {
  env -u TMUX tmux "$@"
}

find_driver_pid() {
  local cands=() pid
  for pid in $(pgrep -x codex); do
    [[ -e "/proc/$pid/fd" ]] || continue
    if ls -l "/proc/$pid/fd" 2>/dev/null | grep -qF "$SESSION_ID"; then
      cands+=("$pid")
    fi
  done
  [[ ${#cands[@]} -eq 0 ]] && return 1
  if [[ -n "$PREFERRED_PID" ]]; then
    for pid in "${cands[@]}"; do
      [[ "$pid" == "$PREFERRED_PID" ]] && { echo "$pid"; return 0; }
    done
  fi
  # newest process wins: a fresh `codex resume` replaces a stale one
  local best="" best_et=99999999 et
  for pid in "${cands[@]}"; do
    et="$(ps -o etimes= -p "$pid" 2>/dev/null | tr -d ' ')"
    [[ -n "$et" && "$et" -lt "$best_et" ]] && { best="$pid"; best_et="$et"; }
  done
  [[ -n "$best" ]] && echo "$best"
}

pane_for_pid() {
  local tty
  tty="$(ps -o tty= -p "$1" 2>/dev/null | tr -d ' ')"
  [[ -n "$tty" ]] || return 1
  utmux list-panes -a -F '#{pane_id} #{pane_tty}' 2>/dev/null \
    | awk -v t="/dev/$tty" '$2==t{print $1; exit}'
}

send_prompt() {
  local pane="$1" reason="$2"
  utmux send-keys -t "$pane" -l "$PROMPT" && sleep 1 && utmux send-keys -t "$pane" Enter
  log "SENT '$PROMPT' -> pane $pane (reason: $reason)"
}

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  echo "session:  $SESSION_ID"
  echo "rollout:  $ROLLOUT ($(stat -c %s "$ROLLOUT") bytes, mtime $(stat -c %y "$ROLLOUT"))"
  driver="$(find_driver_pid || true)"
  if [[ -z "$driver" ]]; then
    echo "driver:   none (no codex process holds the rollout)"
    exit 1
  fi
  echo "driver:   pid $driver ($(ps -o lstart= -p "$driver"))"
  pane="$(pane_for_pid "$driver" || true)"
  if [[ -z "$pane" ]]; then
    echo "pane:     none (driver tty not in any tmux pane on the default server)"
    exit 1
  fi
  loc="$(utmux list-panes -a -F '#{pane_id} #{session_name}:#{window_index}.#{pane_index}' | awk -v p="$pane" '$1==p{print $2}')"
  echo "pane:     $pane ($loc)"
  if utmux capture-pane -p -t "$pane" 2>/dev/null | grep -Eiq "$BUSY_PATTERN"; then
    echo "state:    busy (turn in flight)"
  else
    echo "state:    idle"
  fi
  exit 0
fi

offset="$(stat -c %s "$ROLLOUT" 2>/dev/null || echo 0)"
pending=0
last_send=0
last_beat=0
last_driver=""

log "watcher started: session=$SESSION_ID rollout=$ROLLOUT offset=$offset poll=${POLL_SECONDS}s pattern='$PATTERN' prompt='$PROMPT'"
while true; do
  size="$(stat -c %s "$ROLLOUT" 2>/dev/null || echo 0)"
  [[ "$size" -lt "$offset" ]] && offset="$size"
  if [[ "$size" -gt "$offset" ]]; then
    if tail -c +"$((offset + 1))" "$ROLLOUT" 2>/dev/null | head -c "$((size - offset))" | grep -aEiq "$PATTERN"; then
      pending=1
      log "trigger pattern in new rollout bytes ($offset..$size)"
    fi
    offset="$size"
  fi

  now="$(date +%s)"
  driver="$(find_driver_pid || true)"
  if [[ -z "$driver" ]]; then
    if (( now - last_beat >= HEARTBEAT )); then
      log "no codex process holds the session rollout; waiting"
      last_beat="$now"
    fi
    sleep "$POLL_SECONDS"
    continue
  fi
  if [[ "$driver" != "$last_driver" ]]; then
    log "driver pid: $driver"
    last_driver="$driver"
  fi
  pane="$(pane_for_pid "$driver" || true)"
  if [[ -z "$pane" ]]; then
    if (( now - last_beat >= HEARTBEAT )); then
      log "driver $driver has no tmux pane on the default server; waiting"
      last_beat="$now"
    fi
    sleep "$POLL_SECONDS"
    continue
  fi

  screen="$(utmux capture-pane -p -t "$pane" 2>/dev/null)"
  if ! printf '%s' "$screen" | grep -Eiq "$BUSY_PATTERN"; then   # TUI is idle
    if [[ "$pending" -eq 1 ]]; then
      send_prompt "$pane" "rollout trigger event"
      pending=0
      last_send="$now"
    elif printf '%s' "$screen" | grep -Eiq "$PATTERN" && (( now - last_send >= PANE_COOLDOWN )); then
      send_prompt "$pane" "trigger text visible on idle pane"
      last_send="$now"
    fi
  fi

  if (( now - last_beat >= HEARTBEAT )); then
    log "heartbeat (driver=$driver pane=$pane offset=$offset pending=$pending)"
    last_beat="$now"
  fi
  sleep "$POLL_SECONDS"
done
