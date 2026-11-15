#!/usr/bin/env bash
# One recording: a harness trial of the scratch task against stub_api.py, reached through the `relay`
# service of relay-compose.yaml (route B of the plan's D4): the stub listens on a unix socket on the
# host, bind-mounted into the relay alone; the host opens no TCP port. While the trial runs, the egress
# log is followed out of the sidecar (teardown deletes it) and every container of the trial is
# inspected once (name, network mode, mounts). No key exists: the harness starts with an empty
# environment plus a dummy key name; the agent phase is on an allowlist (`relay` and the Python index).
#
# Usage: [AUTH=key|token|none|forced-empty] [STUB_ARGS=...] [STRACE=1|DECOY=1] record.sh <name> <scenario> <agent> [harbor args...]
#        AUTH=token runs the CLI in subscription-token mode (the harness's CLAUDE_FORCE_OAUTH route) with a
#        fake token in the launcher's per-slot form, `lh-fake-slot-` and 32 random hex digits; the stub
#        checks each request's bearer against it (`--expect-bearer`) and never logs it. AUTH=none gives the
#        CLI neither a key nor a token; AUTH=forced-empty sets CLAUDE_FORCE_OAUTH with an empty token.
#        STRACE=1 traces the CLI's file and process calls from the host (strace attached to the CLI process
#        of this trial's agent container, found by its PID namespace), into strace.<pid> files.
#        DECOY=1 (with AUTH=token) plants a decoy credential file, `.credentials.json` in the CLI's config
#        directory, holding a generated canary (`lh-canary-` and 32 hex digits, kept in canary.txt), and
#        traces the CLI from its first instruction: a `podman` wrapper first on the harness's PATH plants
#        the file just before the harness's `podman exec` of the CLI, then runs that exec under
#        `strace -f` (into strace.cli); every other podman call passes through. The stub counts the
#        canary in every request's text (`--watch`).
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

trials() {  # this recording's trial names, lower case (its containers are named <trial>__...)
  for t in "$OUT"/jobs/*/*/; do [ -d "$t" ] && basename "$t" | tr '[:upper:]' '[:lower:]'; done
}

ours() {  # is container $1 one of the trials in $2 (its name starts with <trial>__)?
  local t
  for t in $2; do case "$1" in "$t"__*) return 0 ;; esac; done
  return 1
}

follow() {  # copy each sidecar's log out while it lives; inspect each of this trial's containers once
  local seen=" " mine
  while kill -0 "$1" 2>/dev/null; do
    mine=$(trials)
    for c in $(podman ps --format '{{.Names}}'); do
      ours "$c" "$mine" || continue
      case "$seen" in *" $c "*) continue ;; esac
      seen="$seen$c "
      podman inspect "$c" --format '{{.Name}} network={{.HostConfig.NetworkMode}} mounts={{json .Mounts}}' \
        >> "$OUT/containers.txt" 2>&1
      case "$c" in *egress-control-sidecar*) podman logs -f "$c" > "$OUT/egress-$c.log" 2>&1 & ;; esac
    done
    sleep 2
  done
}

decoy_wrapper() {  # DECOY=1: a podman wrapper for the harness's PATH (see the header)
  mkdir -m 700 -p "$WRAP"
  cat > "$WRAP/podman" <<'WRAPPER'
#!/bin/bash
real=/usr/bin/podman
case "$1 $*" in exec\ *--output-format=stream-json*) ;; *) exec "$real" "$@" ;; esac
for a in "$@"; do case "$a" in *_main_1) c=$a ;; esac; done
canary=$(cat "$LH_DECOY_DIR/canary.txt")
printf '{"claudeAiOauth":{"accessToken":"%s","refreshToken":"%s-refresh","expiresAt":4102444800000,"scopes":["user:inference"],"subscriptionType":"max"}}\n' \
  "$canary" "$canary" | "$real" exec -i "$c" sh -c 'mkdir -p /logs/agent/sessions && cat > /logs/agent/sessions/.credentials.json' \
  || { echo "decoy: could not plant the credential file in $c" >&2; exit 97; }
exec strace -f -tt --pidns-translation -e trace=%file,%process -o "$LH_DECOY_DIR/strace.cli" "$real" "$@"
WRAPPER
  chmod 700 "$WRAP/podman"
}

trace_cli() {  # strace each CLI process of this trial's agent container, from the host, as soon as it appears
  local main="" traced=" " p c t
  while kill -0 "$1" 2>/dev/null; do
    if [ -z "$main" ]; then  # this trial's agent container: <trial name, lower case>__env_main_1
      for t in $(trials); do
        c=${t}__env_main_1
        main=$(podman inspect -f '{{.State.Pid}}' "$c" 2>/dev/null) || main=""
        [ "${main:-0}" -gt 0 ] && { echo "$c pid=$main" > "$OUT/strace-target.txt"; break; }
        main=""
      done
    fi
    for p in $([ -n "$main" ] && pgrep --ns "$main" --nslist pid); do  # the CLI: an exe under claude/versions
      case "$traced" in *" $p "*) continue ;; esac
      case "$(readlink "/proc/$p/exe" 2>/dev/null)" in */claude/versions/*) ;; *) continue ;; esac
      traced="$traced$p "
      strace -f -tt -e trace=%file,%process -o "$OUT/strace.$p" -p "$p" 2>>"$OUT/strace.err" &
      echo "$p start_ticks=$(awk '{print $22}' "/proc/$p/stat") attach=$(date +%s.%N) uptime=$(cut -d' ' -f1 /proc/uptime)" \
        >> "$OUT/strace-target.txt"
    done
    sleep 0.01
  done
}

[ "${1:-}" = make_task ] && { set -e; make_task; exit; }
name=${1:-} scenario=${2:-} agent=${3:-}; shift 3 || exit 2
[[ $name =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "record.sh: bad recording name '$name'" >&2; exit 2; }
check_allowlist
OUT=$LH/recordings/$name
SOCKET_DIR=$LH/relay/$name  # one socket directory per recording, so two can run at once
WRAP=$LH/wrap/$name
trap 'kill $(jobs -p) 2>/dev/null; rm -rf "$SOCKET_DIR" "$WRAP"' EXIT  # the stub and the followers stop with the script
rm -rf "$OUT"; mkdir -p "$OUT"; mkdir -m 700 -p "$LH/relay" "$SOCKET_DIR"
TOKEN=lh-fake-slot-$(od -An -tx1 -N16 /dev/urandom | tr -d ' \n')
[ "${AUTH:-key}" = token ] && STUB_ARGS="${STUB_ARGS:-} --expect-bearer $TOKEN"
if [ "${DECOY:-0}" = 1 ]; then
  [ "${AUTH:-key}" = token ] || { echo "record.sh: DECOY=1 needs AUTH=token" >&2; exit 2; }
  echo "lh-canary-$(od -An -tx1 -N16 /dev/urandom | tr -d ' \n')" > "$OUT/canary.txt"
  STUB_ARGS="$STUB_ARGS --watch $(cat "$OUT/canary.txt")"
  decoy_wrapper
  CLEAN_PATH=$NO_PROVIDER:$WRAP:${CLEAN_PATH#"$NO_PROVIDER":}
fi
python3 -I "$HERE/stub_api.py" --unix "$SOCKET_DIR/passthrough.sock" --model "$MODEL" --scenario "$scenario" \
  --log "$OUT/stub.jsonl" ${STUB_ARGS:-} > "$OUT/stub.out" 2>&1 &
stub=$!
sleep 1
agent_args=(--agent "$agent")
auth_env=(LH_DUMMY_KEY=lh-dummy-not-a-key)
[ "$agent" = claude-code ] && agent_args+=(-m "anthropic/$MODEL" --base-url "http://$RELAY")
case "${AUTH:-key}" in
  token) auth_env=(CLAUDE_FORCE_OAUTH=1 CLAUDE_CODE_OAUTH_TOKEN="$TOKEN"); agent_args+=(--skip-credential-checks) ;;
  none) auth_env=(LH_NONE=1); agent_args+=(--skip-credential-checks) ;;
  forced-empty) auth_env=(CLAUDE_FORCE_OAUTH=1 CLAUDE_CODE_OAUTH_TOKEN=); agent_args+=(--skip-credential-checks) ;;
  key) [ "$agent" = claude-code ] && agent_args+=(--api-key-name LH_DUMMY_KEY) ;;
  *) echo "record.sh: unknown AUTH '$AUTH'" >&2; exit 2 ;;
esac
env -i HOME="$HOME" XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" PATH="$CLEAN_PATH" \
  HARBOR_TELEMETRY=0 DO_NOT_TRACK=1 CONTAINERS_CONF_OVERRIDE="$LH/logs/containers-override.conf" \
  LH_RELAY_SOCKET_DIR="$SOCKET_DIR" LH_DECOY_DIR="$OUT" "${auth_env[@]}" \
  "$LH/hvenv/bin/python" -I "$HERE/harbor_patient.py" run --path "$TASK" "${agent_args[@]}" --env podman \
  -n 1 -o "$OUT/jobs" -q -y --extra-docker-compose "$LH/logs/limits-compose.yaml" \
  --extra-docker-compose "$HERE/relay-compose.yaml" "$@" > "$OUT/harbor.out" 2>&1 &
harbor=$!
[ "${STRACE:-0}" = 1 ] && trace_cli "$harbor" &
follow "$harbor"
wait "$harbor"; echo "harbor rc=$?" > "$OUT/rc"
sleep 2
cat "$OUT/rc"
