#!/usr/bin/env bash
# One recording: a harness trial of the scratch task against stub_api.py, reached through the `relay`
# service of relay-compose.yaml (route B of the plan's D4): the stub listens on a unix socket on the
# host, bind-mounted into the relay alone; the host opens no TCP port. While the trial runs, the egress
# log is followed out of the sidecar (teardown deletes it) and every container of the trial is
# inspected once (name, network mode, mounts). No key exists: the harness starts with an empty
# environment plus a dummy key name; the agent phase is on an allowlist (`relay` and the Python index).
#
# Usage: [AUTH=token] [STUB_ARGS=...] record.sh <name> <scenario> <agent: oracle|nop|claude-code> [harbor args...]
#        AUTH=token runs the CLI in subscription-token mode: CLAUDE_CODE_OAUTH_TOKEN set to a fake value,
#        no API key (the harness's CLAUDE_FORCE_OAUTH route).
#        record.sh make_task      (scratch copy: neutral instruction, probe as the reference solution,
#                                  the two network keys)
# Needs: $LH/hvenv (harbor 0.25.0 + podman-compose 1.6.0); $LH/logs/containers-override.conf with
# `[engine] compose_warning_logs = false` (podman 4.9 ignores PODMAN_COMPOSE_WARNING_LOGS, and its
# banner on stderr breaks the harness's package-manager probe); $LH/logs/limits-compose.yaml.
# Output: $LH/recordings/<name>/ (stub.jsonl, egress-*.log, containers.txt, harbor.out, jobs/, rc).
set -uo pipefail
LH=${LH:-$HOME/lh-cache}
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)  # the repository root, two levels above this script
[ "$(git -C "$HERE" rev-parse --show-toplevel 2>/dev/null)" = "$REPO" ] \
  || { echo "$(basename "$0"): $REPO is not this script's repository root" >&2; exit 2; }
NO_PROVIDER=$REPO/experiments/thread_m/no_provider
[ -x "$NO_PROVIDER/claude" ] || { echo "$(basename "$0"): no provider guard at $NO_PROVIDER" >&2; exit 2; }
MODEL=claude-haiku-5-5
RELAY=relay:8080
SOCKET_DIR=$LH/relay
SRC=${SRC:-$LH/src/tb/tasks/sound-change-cascade}
TASK=$LH/scratch/recording-task
CLEAN_PATH=$NO_PROVIDER:$LH/hvenv/bin:/usr/local/bin:/usr/bin:/bin
# Every TCP port the host listens on, for the probe's scan.
HOST_PORTS=$(ss -ltnH | awk '{print $4}' | sed 's/.*://' | sort -un | paste -sd, -)
HOST_IP=$(ip -4 route get 1.1.1.1 | awk '{for (i = 1; i < NF; i++) if ($i == "src") print $(i + 1)}')

make_task() {
  rm -rf "$TASK"; mkdir -p "$(dirname "$TASK")"; cp -r "$SRC" "$TASK"
  printf 'Recording session for a stand-in model API. Follow the tool calls; there is no task.\n' > "$TASK/instruction.md"
  cp "$HERE/allowlist_probe.py" "$TASK/solution/probe.py"
  printf '#!/bin/bash\npython3 /solution/probe.py %s %s %s\n' "$RELAY" "$HOST_IP" "$HOST_PORTS" > "$TASK/solution/solve.sh"
  grep -q '^\[agent\]' "$TASK/task.toml" || { echo "make_task: no [agent] table in $SRC/task.toml" >&2; exit 2; }
  sed -i '/^\[agent\]/a network_mode = "allowlist"\nallowed_hosts = ["relay", "pypi.org", "files.pythonhosted.org"]' "$TASK/task.toml"
  check_allowlist
}

check_allowlist() {  # the agent phase must be on the allowlist that lists the relay and not the vendor's API
  grep -q '^network_mode = "allowlist"$' "$TASK/task.toml" \
    && grep -q '^allowed_hosts = \["relay", "pypi.org", "files.pythonhosted.org"\]$' "$TASK/task.toml" \
    || { echo "record.sh: $TASK/task.toml is not on the recording allowlist; run make_task" >&2; exit 2; }
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

[ "${1:-}" = make_task ] && { set -e; make_task; exit; }
name=${1:-} scenario=${2:-} agent=${3:-}; shift 3 || exit 2
[[ $name =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "record.sh: bad recording name '$name'" >&2; exit 2; }
check_allowlist
OUT=$LH/recordings/$name
trap 'kill $(jobs -p) 2>/dev/null' EXIT  # the stub and the log followers stop with the script
rm -rf "$OUT"; mkdir -p "$OUT"; mkdir -m 700 -p "$SOCKET_DIR"
python3 -I "$HERE/stub_api.py" --unix "$SOCKET_DIR/passthrough.sock" --model "$MODEL" --scenario "$scenario" \
  --log "$OUT/stub.jsonl" ${STUB_ARGS:-} > "$OUT/stub.out" 2>&1 &
stub=$!
sleep 1
agent_args=(--agent "$agent")
auth_env=(LH_DUMMY_KEY=lh-dummy-not-a-key)
[ "$agent" = claude-code ] && agent_args+=(-m "anthropic/$MODEL" --base-url "http://$RELAY")
if [ "${AUTH:-key}" = token ]; then
  auth_env=(CLAUDE_FORCE_OAUTH=1 CLAUDE_CODE_OAUTH_TOKEN=lh-fake-oauth-token-not-real)
  agent_args+=(--skip-credential-checks)
elif [ "$agent" = claude-code ]; then
  agent_args+=(--api-key-name LH_DUMMY_KEY)
fi
env -i HOME="$HOME" XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" PATH="$CLEAN_PATH" \
  HARBOR_TELEMETRY=0 DO_NOT_TRACK=1 CONTAINERS_CONF_OVERRIDE="$LH/logs/containers-override.conf" \
  LH_RELAY_SOCKET_DIR="$SOCKET_DIR" "${auth_env[@]}" \
  "$LH/hvenv/bin/python" -I "$HERE/harbor_patient.py" run --path "$TASK" "${agent_args[@]}" --env podman \
  -n 1 -o "$OUT/jobs" -q -y --extra-docker-compose "$LH/logs/limits-compose.yaml" \
  --extra-docker-compose "$HERE/relay-compose.yaml" "$@" > "$OUT/harbor.out" 2>&1 &
harbor=$!
follow "$harbor"
wait "$harbor"; echo "harbor rc=$?" > "$OUT/rc"
sleep 2
cat "$OUT/rc"
