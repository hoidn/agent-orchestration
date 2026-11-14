#!/usr/bin/env bash
# One recording: a harness trial of the scratch task against stub_api.py, reached through the `relay`
# service of relay-compose.yaml (route B of the plan's D4): the stub listens on a unix socket on the
# host, bind-mounted into the relay alone; the host opens no TCP port. While the trial runs, the egress
# log is followed out of the sidecar (teardown deletes it) and every container of the trial is
# inspected once (name, network mode, mounts). No key exists: the harness starts with an empty
# environment plus a dummy key name; the agent phase is on an allowlist (`relay` and the Python index).
#
# Usage: record.sh <name> <scenario> <agent: oracle|nop|claude-code> [extra harbor run args...]
#        record.sh make_task      (scratch copy: neutral instruction, probe as the reference solution,
#                                  the two network keys)
# Needs: $LH/hvenv (harbor 0.25.0 + podman-compose 1.6.0); $LH/logs/containers-override.conf with
# `[engine] compose_warning_logs = false` (podman 4.9 ignores PODMAN_COMPOSE_WARNING_LOGS, and its
# banner on stderr breaks the harness's package-manager probe); $LH/logs/limits-compose.yaml.
# Output: $LH/recordings/<name>/ (stub.jsonl, egress-*.log, containers.txt, harbor.out, jobs/, rc).
set -uo pipefail
LH=${LH:-/home/ollie/lh-cache}
HERE=$(cd "$(dirname "$0")" && pwd)
MODEL=claude-haiku-5-5
RELAY=relay:8080
SOCKET_DIR=$LH/relay
SRC=${SRC:-$LH/src/tb/tasks/sound-change-cascade}
TASK=$LH/scratch/recording-task
NO_PROVIDER=/home/ollie/Documents/agent-orchestration/experiments/thread_m/no_provider
CLEAN_PATH=$NO_PROVIDER:$LH/hvenv/bin:/usr/local/bin:/usr/bin:/bin
# Every TCP port the host listens on, for the probe's scan.
HOST_PORTS=$(ss -ltnH | awk '{print $4}' | sed 's/.*://' | sort -un | paste -sd, -)
HOST_IP=$(ip -4 route get 1.1.1.1 | awk '{for (i = 1; i < NF; i++) if ($i == "src") print $(i + 1)}')

make_task() {
  rm -rf "$TASK"; mkdir -p "$(dirname "$TASK")"; cp -r "$SRC" "$TASK"
  printf 'Recording session for a stand-in model API. Follow the tool calls; there is no task.\n' > "$TASK/instruction.md"
  cp "$HERE/allowlist_probe.py" "$TASK/solution/probe.py"
  printf '#!/bin/bash\npython3 /solution/probe.py %s %s %s\n' "$RELAY" "$HOST_IP" "$HOST_PORTS" > "$TASK/solution/solve.sh"
  sed -i '/^\[agent\]/a network_mode = "allowlist"\nallowed_hosts = ["relay", "pypi.org", "files.pythonhosted.org"]' "$TASK/task.toml"
}

follow() {  # copy each sidecar's log out while it lives; inspect each container once
  local seen=" "
  while kill -0 "$1" 2>/dev/null; do
    for c in $(podman ps --format '{{.Names}}'); do
      case "$seen" in *" $c "*) continue ;; esac
      seen="$seen$c "
      podman inspect "$c" --format '{{.Name}} network={{.HostConfig.NetworkMode}} mounts={{json .Mounts}}' \
        >> "$OUT/containers.txt" 2>&1
      case "$c" in *egress-control-sidecar*) podman logs -f "$c" > "$OUT/egress-$c.log" 2>&1 & ;; esac
    done
    sleep 2
  done
}

[ "${1:-}" = make_task ] && { make_task; exit; }
name=$1 scenario=$2 agent=$3; shift 3
OUT=$LH/recordings/$name
rm -rf "$OUT"; mkdir -p "$OUT"; mkdir -m 700 -p "$SOCKET_DIR"
python3 -I "$HERE/stub_api.py" --unix "$SOCKET_DIR/passthrough.sock" --model "$MODEL" --scenario "$scenario" \
  --log "$OUT/stub.jsonl" ${STUB_ARGS:-} > "$OUT/stub.out" 2>&1 &
stub=$!
sleep 1
agent_args=(--agent "$agent")
[ "$agent" = claude-code ] && agent_args+=(-m "anthropic/$MODEL" --base-url "http://$RELAY" --api-key-name LH_DUMMY_KEY)
env -i HOME="$HOME" XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" PATH="$CLEAN_PATH" \
  HARBOR_TELEMETRY=0 DO_NOT_TRACK=1 CONTAINERS_CONF_OVERRIDE="$LH/logs/containers-override.conf" \
  LH_RELAY_SOCKET_DIR="$SOCKET_DIR" LH_DUMMY_KEY=lh-dummy-not-a-key \
  "$LH/hvenv/bin/python" -I "$HERE/harbor_patient.py" run --path "$TASK" "${agent_args[@]}" --env podman \
  -n 1 -o "$OUT/jobs" -q -y --extra-docker-compose "$LH/logs/limits-compose.yaml" \
  --extra-docker-compose "$HERE/relay-compose.yaml" "$@" > "$OUT/harbor.out" 2>&1 &
harbor=$!
follow "$harbor"
wait "$harbor"; echo "harbor rc=$?" > "$OUT/rc"
sleep 2; kill "$stub" $(jobs -p) 2>/dev/null
cat "$OUT/rc"
