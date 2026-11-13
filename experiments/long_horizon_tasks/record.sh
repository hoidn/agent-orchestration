#!/usr/bin/env bash
# One recording: a harness trial of the scratch task against stub_api.py, with the egress log
# followed out of the sidecar while it runs (teardown deletes the sidecar). No key exists:
# the harness is started with an empty environment plus a dummy key name; the agent phase is on
# an allowlist (the stub's host address and the Python index), so the vendor's API is unreachable.
#
# Usage: record.sh <name> <scenario> <agent: oracle|nop|claude-code> [extra harbor run args...]
# Needs: $LH/hvenv (harbor 0.25.0 + podman-compose 1.6.0); `make_task` below run once;
# $LH/logs/containers-override.conf with `[engine] compose_warning_logs = false` (podman 4.9 ignores
# PODMAN_COMPOSE_WARNING_LOGS, and its banner on stderr breaks the harness's package-manager probe).
# Output: $LH/recordings/<name>/ (stub.jsonl, egress-*.log, harbor.out, jobs/, rc).
set -uo pipefail
LH=${LH:-/home/ollie/lh-cache}
HERE=$(cd "$(dirname "$0")" && pwd)
HOST_IP=${HOST_IP:-192.168.4.59}
PORT=${PORT:-18471}
MODEL=claude-haiku-5-5
SRC=${SRC:-$LH/src/tb/tasks/sound-change-cascade}
TASK=$LH/scratch/recording-task
NO_PROVIDER=/home/ollie/Documents/agent-orchestration/experiments/thread_m/no_provider
CLEAN_PATH=$NO_PROVIDER:$LH/hvenv/bin:/usr/local/bin:/usr/bin:/bin

make_task() {  # scratch copy: neutral instruction, probe as the reference solution, the two network keys
  rm -rf "$TASK"; cp -r "$SRC" "$TASK"
  printf 'Recording session for a stand-in model API. Follow the tool calls; there is no task.\n' > "$TASK/instruction.md"
  cp "$HERE/allowlist_probe.py" "$TASK/solution/probe.py"
  printf '#!/bin/bash\npython3 /solution/probe.py %s %s\n' "$HOST_IP" "$PORT" > "$TASK/solution/solve.sh"
  sed -i "/^\[agent\]/a network_mode = \"allowlist\"\nallowed_hosts = [\"$HOST_IP\", \"pypi.org\", \"files.pythonhosted.org\"]" "$TASK/task.toml"
}

follow_egress() {  # copy each sidecar's log out while it lives
  local seen=" "
  while kill -0 "$1" 2>/dev/null; do
    for c in $(podman ps --format '{{.Names}}' | grep egress-control-sidecar); do
      case "$seen" in *" $c "*) continue ;; esac
      seen="$seen$c "; podman logs -f "$c" > "$OUT/egress-$c.log" 2>&1 &
    done
    sleep 2
  done
}

[ "${1:-}" = make_task ] && { make_task; exit; }
name=$1 scenario=$2 agent=$3; shift 3
OUT=$LH/recordings/$name
rm -rf "$OUT"; mkdir -p "$OUT"
python3 -I "$HERE/stub_api.py" --host "$HOST_IP" --port "$PORT" --model "$MODEL" --scenario "$scenario" \
  --log "$OUT/stub.jsonl" > "$OUT/stub.out" 2>&1 &
stub=$!
sleep 1
agent_args=(--agent "$agent")
[ "$agent" = claude-code ] && agent_args+=(-m "anthropic/$MODEL" --base-url "http://$HOST_IP:$PORT"
  --api-key-name LH_DUMMY_KEY)
env -i HOME="$HOME" XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" PATH="$CLEAN_PATH" \
  HARBOR_TELEMETRY=0 DO_NOT_TRACK=1 CONTAINERS_CONF_OVERRIDE="$LH/logs/containers-override.conf" LH_DUMMY_KEY=lh-dummy-not-a-key \
  "$LH/hvenv/bin/python" -I "$HERE/harbor_patient.py" run --path "$TASK" "${agent_args[@]}" --env podman \
  -n 1 -o "$OUT/jobs" -q -y --extra-docker-compose "$LH/logs/limits-compose.yaml" "$@" > "$OUT/harbor.out" 2>&1 &
harbor=$!
follow_egress "$harbor"
wait "$harbor"; echo "harbor rc=$?" > "$OUT/rc"
sleep 2; kill "$stub" $(jobs -p) 2>/dev/null
cat "$OUT/rc"
