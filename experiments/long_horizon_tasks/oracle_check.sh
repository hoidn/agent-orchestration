#!/usr/bin/env bash
# Oracle check of the long-horizon plan (D1, Task 2b) through the published Harbor harness on rootless Podman.
# No model call: the `oracle` agent runs the task's reference solution and the `nop` agent does nothing, each
# graded by the task's own verifier on the task's two pinned images. For each task named:
#  1. its two pinned images are pulled by digest under their docker.io/ full name (D1's host-side step), unless
#     already in the store;
#  2. its cached 4.1.0 package ($LH/tasks41/<task>/x) is copied and the copy's task.toml gets the two agent-phase
#     keys (D1, D3): network_mode "allowlist" and the hosts below plus the task's extra_hosts from tasks.json.
#     Removing those two lines must give back the package's task.toml byte for byte; the SHA-256 of the two lines
#     is the overlay digest;
#  3. with INSTALL=1, the pinned CLI is installed once on the agent image by the harness's own path
#     (claude-code --install-only: the public CLI is downloaded; no session starts, no API request is made);
#  4. REPEATS rounds of one oracle and one nop trial, up to CONCURRENCY at once. Each trial waits for the load
#     gate (1- and 5-minute load at or below GATE; "none" turns it off, as in the first pass; closed for two
#     hours ends the run with exit 4), runs under the CPU set CPUS (an affinity every container inherits), and
#     writes meta.txt beside its harness job: load at start, end and highest, wall time, free space low point,
#     the affinity seen on each container's processes and its cgroup's peak memory, image ids, overlay digest;
#  5. the images this run pulled or built are deleted (never with -f) unless KEEP_IMAGES=1.
# Free space under 25 GB on / or /home stops the run (exit 3): a running trial is interrupted and cleaned up.
# vba-userform-port-uidfix is the labelled modified task of owner question 4: the package with the verifier's
# one-line uid bound change (1000000000 -> 55000), run on a verifier image derived from the pinned one by that
# same one-line change, because the pinned verifier image carries its own copy of the tests.
# Results: $JOBS/<agent>/<label>/<round>/ (agent oracle, nop or install); summarize.py reads them.
#
# Usage: oracle_check.sh <task>...      (names as in tasks.json without the "terminal-bench/" prefix)
# Env: LH (default ~/lh-cache), JOBS (default $LH/jobs/oracle), REPEATS (1), CONCURRENCY (1), CPUS (8-31),
#      GATE (24), INSTALL (0), KEEP_IMAGES (0), LAUNCH_GAP_S (5: seconds between two launches)
# Needs: $LH/hvenv (harbor 0.25.0 + podman-compose 1.6.0), $LH/logs/containers-override.conf (README), taskset.
set -uo pipefail
LH=${LH:-$HOME/lh-cache}
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)  # the repository root, two levels above this script
JOBS=${JOBS:-$LH/jobs/oracle} REPEATS=${REPEATS:-1} CONCURRENCY=${CONCURRENCY:-1} CPUS=${CPUS:-8-31}
GATE=${GATE:-24} INSTALL=${INSTALL:-0} KEEP_IMAGES=${KEEP_IMAGES:-0} LAUNCH_GAP_S=${LAUNCH_GAP_S:-5}
STOP_GB=25 GATE_WAIT_S=7200 CLI_VERSION=2.1.311 MODEL=claude-haiku-5-5
# D3's list as drafted for the oracle passes: the relay, the Python, Node and Rust indexes, the package
# mirrors of the three base distributions (Debian, Ubuntu, Fedora). Task 3 freezes the ladder's list.
ALLOWLIST=(relay pypi.org files.pythonhosted.org registry.npmjs.org crates.io index.crates.io static.crates.io
  deb.debian.org security.debian.org archive.ubuntu.com security.ubuntu.com mirrors.fedoraproject.org
  dl.fedoraproject.org)
UIDFIX_SED='s/secrets\.randbelow(1000000000)/secrets.randbelow(55000)/'

# ---- pure parts (tests/test_long_horizon_oracle_check.py) ----------------------------------------------

overlay_lines() {  # <host>...: the two agent-phase keys
  local hosts
  hosts=$(printf '"%s", ' "$@")
  printf 'network_mode = "allowlist"\nallowed_hosts = [%s]\n' "${hosts%, }"
}

overlay_task() {  # <package dir> <copy dir> <host>...: copy with the two keys after [agent]; prints their SHA-256
  local src=$1 dst=$2 keys
  shift 2
  [ "$(grep -cx '\[agent\]' "$src/task.toml")" = 1 ] || { echo "overlay: not one [agent] table in $src" >&2; return 2; }
  grep -qE '^[[:space:]]*(network_mode|allowed_hosts)[[:space:]]*=' "$src/task.toml" \
    && { echo "overlay: $src/task.toml already sets a network key" >&2; return 2; }
  keys=$(overlay_lines "$@")
  rm -rf "$dst" && mkdir -p "$(dirname "$dst")" && cp -r "$src" "$dst" || return 2
  awk -v keys="$keys" '{ print } $0 == "[agent]" { print keys }' "$src/task.toml" > "$dst/task.toml"
  cmp -s <(grep -vxF -f <(printf '%s\n' "$keys") "$dst/task.toml") "$src/task.toml" \
    || { echo "overlay: removing the two keys does not give back $src/task.toml" >&2; return 2; }
  printf '%s\n' "$keys" | sha256sum | cut -d' ' -f1
}

gate_open() {  # <gate> [loadavg file]: 0 when the 1- and 5-minute load are at or below the gate, or the gate is none
  [ "$1" = none ] && return 0
  awk -v g="$1" '{ exit !($1 <= g && $2 <= g) }' "${2:-/proc/loadavg}"
}

room_ok() {  # <free bytes>...: 0 when every figure is at least STOP_GB
  local free
  for free in "$@"; do [ "$free" -ge $((STOP_GB * 1000000000)) ] || return 1; done
}

free_bytes() {  # free space on / and on /home (the image store), in bytes
  df -B1 --output=avail / /home | tail -2 | paste -sd' '
}

uidfix() {  # <app_worker.py>: the labelled one-line change; refuses unless exactly one line carries the bound
  [ "$(grep -cF 'secrets.randbelow(1000000000)' "$1")" = 1 ] || { echo "uidfix: not one bound line in $1" >&2; return 2; }
  sed -i "$UIDFIX_SED" "$1"
}

# ---- the run -------------------------------------------------------------------------------------------

run_harbor() {  # the harness with an empty environment: no credential of any kind reaches it
  env -i HOME="$HOME" XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" PATH="$CLEAN_PATH" \
    HARBOR_TELEMETRY=0 DO_NOT_TRACK=1 CONTAINERS_CONF_OVERRIDE="$LH/logs/containers-override.conf" \
    taskset -c "$CPUS" "$LH/hvenv/bin/python" -I "$HERE/harbor_patient.py" run --env podman -n 1 -q -y \
    --extra-docker-compose "$LIMITS" "$@"
}

task_field() {  # <task> <field>: a field of the task's tasks.json entry, as JSON (a KeyError if either is missing)
  python3 -I -c 'import json, sys
tasks = {t["name"]: t for t in json.load(open(sys.argv[1]))["tasks"]}
print(json.dumps(tasks["terminal-bench/" + sys.argv[2]][sys.argv[3]]))' "$HERE/tasks.json" "$1" "$2"
}

ensure_image() {  # <ref>: pull by digest unless present; prints the image id; notes images this run brought
  podman image exists "$1" || { podman pull -q "docker.io/$1" > /dev/null && echo "$1" >> "$PULLED"; } || return 1
  podman image inspect -f '{{.Id}}' "$1"
}

follow() {  # <harbor pid> <out dir> <label>: sample the label's containers until the harness exits
  # The harness names the trial directory only after its containers start, so containers are found by the
  # label's prefix (compose lowercases it); with CONCURRENCY above 1 summarize.py keeps the trial's own.
  local pid=$1 out=$2 prefix=${3,,}__ seen=" " stopped=0 c cg cpid load free
  while kill -0 "$pid" 2> /dev/null; do
    read -r load _ < /proc/loadavg
    free=$(free_bytes)
    printf 'load %s\nfree %s\n' "$load" "$free" >> "$out/samples"
    if [ "$stopped" = 0 ] && ! room_ok $free; then  # interrupt once: the harness then cleans up its containers
      echo "disk_stop=$free" >> "$out/meta.txt"
      kill -INT "$pid"
      stopped=1
    fi
    while read -r c cpid; do
      cg=$(cut -d: -f3 "/proc/$cpid/cgroup" 2> /dev/null) && [ -n "$cg" ] || continue  # exited meanwhile
      cg=/sys/fs/cgroup$cg
      echo "container $c peak=$(cat "$cg/memory.peak" 2> /dev/null) affinity=$(for p in $(cat "$cg/cgroup.procs" \
        2> /dev/null); do taskset -cp "$p" 2> /dev/null | sed 's/.*: //'; done | sort -u | paste -sd'|')" >> "$out/samples"
      case "$seen" in *" $c "*) continue ;; esac
      seen="$seen$c "
      case "$c" in *egress-control-sidecar*) podman logs -f "$c" > "$out/egress-$c.log" 2>&1 & ;; esac
    done < <(podman ps --filter "name=^$prefix" --format '{{.Names}} {{.Pid}}' 2> /dev/null)
    sleep 5
  done
}

trial() {  # <label> <agent: oracle, nop or install> <round> <harness args>...: one trial and its meta.txt
  local label=$1 agent=$2 round=$3 out=$JOBS/$2/$1/$3 start rc
  shift 3
  rm -rf "$out" && mkdir -p "$out"
  start=$(date +%s)
  printf 'label=%s\nagent=%s\nround=%s\ncpus=%s\ngate=%s\noverlay_sha256=%s\nimages=%s\nload_start=%s\n' \
    "$label" "$agent" "$round" "$CPUS" "$GATE" "$OVERLAY" "$IMAGES" "$(cut -d' ' -f1-3 /proc/loadavg)" > "$out/meta.txt"
  run_harbor --path "$LH/oracle/tasks/$label" -o "$out" "$@" > "$out/harbor.out" 2>&1 &
  local pid=$!
  follow "$pid" "$out" "$label"
  wait "$pid"
  rc=$?
  printf 'rc=%s\nwall_s=%s\nload_end=%s\n' "$rc" "$(($(date +%s) - start))" "$(cut -d' ' -f1-3 /proc/loadavg)" \
    >> "$out/meta.txt"
  kill $(jobs -p) 2> /dev/null  # the egress log followers
  echo "$label $agent round=$round rc=$rc wall_s=$(($(date +%s) - start)) load=$(cut -d' ' -f1-3 /proc/loadavg)" \
    | tee -a "$JOBS/oracle_check.log"
}

wait_gate() {
  local since=$SECONDS
  until gate_open "$GATE"; do
    [ $((SECONDS - since)) -lt $GATE_WAIT_S ] || { echo "gate closed for two hours" | tee -a "$JOBS/oracle_check.log"; return 1; }
    sleep 60
  done
}

prepare() {  # <label>: images, the overlay copy, and for the uidfix label the derived verifier image
  local label=$1 task=${1%-uidfix} agent_ref verifier_ref extra aid vid ctx derived
  agent_ref=$(task_field "$task" environment_image | tr -d '"') || return 2
  verifier_ref=$(task_field "$task" verifier_image | tr -d '"') || return 2
  mapfile -t extra < <(task_field "$task" extra_hosts | python3 -I -c 'import json, sys; [print(h) for h in json.load(sys.stdin) or []]')
  aid=$(ensure_image "$agent_ref") && vid=$(ensure_image "$verifier_ref") || return 1
  IMAGES="agent:$aid verifier:$vid"
  OVERLAY=$(overlay_task "$LH/tasks41/$task/x" "$LH/oracle/tasks/$label" "${ALLOWLIST[@]}" "${extra[@]}") || return 2
  [ "$label" = "$task" ] && return 0
  uidfix "$LH/oracle/tasks/$label/tests/app_worker.py" || return 2
  # No localhost/ prefix: podman-compose's teardown force-removes images named so, and the next trial lacks it.
  derived=lh-oracle/$label:verifier ctx=$(mktemp -d "$LH/oracle/uidfix.XXXXXX")
  cat > "$ctx/Containerfile" <<EOF
FROM docker.io/$verifier_ref
RUN test "\$(grep -cF 'secrets.randbelow(1000000000)' /tests/app_worker.py)" = 1 && sed -i '$UIDFIX_SED' /tests/app_worker.py
EOF
  podman build -q --pull=never --network none -t "$derived" "$ctx" > /dev/null || return 2
  rm -rf "$ctx"
  echo "$derived" >> "$PULLED"
  sed -i "s|^docker_image = \"$verifier_ref\"\$|docker_image = \"$derived\"|" "$LH/oracle/tasks/$label/task.toml"
  [ "$(grep -cxF "docker_image = \"$derived\"" "$LH/oracle/tasks/$label/task.toml")" = 1 ] \
    || { echo "uidfix: the verifier image line of $label was not replaced once" >&2; return 2; }
  IMAGES="$IMAGES verifier_derived:$(podman image inspect -f '{{.Id}}' "$derived")"
}

check_task() {  # <label>
  local label=$1 round agent
  prepare "$label" || return $?
  [ "$INSTALL" = 1 ] && (trial "$label" install 1 --agent claude-code -m "anthropic/$MODEL" \
    --ak "version=$CLI_VERSION" --base-url http://relay:8080 --install-only)
  for round in $(seq 1 "$REPEATS"); do
    for agent in oracle nop; do
      while [ "$(jobs -rp | wc -l)" -ge "$CONCURRENCY" ]; do wait -n; done
      room_ok $(free_bytes) || { echo "disk stop" | tee -a "$JOBS/oracle_check.log"; wait; return 3; }
      wait_gate || { wait; return 4; }
      trial "$label" "$agent" "$round" --agent "$agent" &
      sleep "$LAUNCH_GAP_S"
    done
  done
  wait
  ! grep -qs '^disk_stop' "$JOBS"/*/"$label"/*/meta.txt || return 3
}

release() {  # delete what this run pulled or built: never -f, so an image a container uses stays
  local ref
  [ "$KEEP_IMAGES" = 1 ] && return 0
  tac "$PULLED" 2> /dev/null | while read -r ref; do
    podman rmi "$ref" > /dev/null 2>&1 || echo "left in place: $ref" | tee -a "$JOBS/oracle_check.log"
  done
  : > "$PULLED"
}

main() {
  [ "$(git -C "$HERE" rev-parse --show-toplevel 2> /dev/null)" = "$REPO" ] \
    || { echo "$(basename "$0"): $REPO is not this script's repository root" >&2; exit 2; }
  NO_PROVIDER=$REPO/experiments/thread_m/no_provider
  [ -x "$NO_PROVIDER/claude" ] || { echo "$(basename "$0"): no provider guard at $NO_PROVIDER" >&2; exit 2; }
  CLEAN_PATH=$NO_PROVIDER:$LH/hvenv/bin:/usr/local/bin:/usr/bin:/bin
  export PATH=$CLEAN_PATH
  mkdir -p "$JOBS" "$LH/oracle"
  LIMITS=$LH/logs/limits-compose.yaml  # a runaway task must not starve the shared host: cap processes
  printf 'services:\n  main:\n    pids_limit: 4096\n' > "$LIMITS"
  PULLED=$JOBS/pulled.txt
  # The egress sidecar's base image, under the name its Dockerfile uses (no search registry on this host).
  local gost=gogost/gost:3.2.7-nightly.20260602@sha256:afc0137758ab4ce399d47a299f9abbacbf522b52a17e59cbb4b4e7a1a66e9196
  podman image exists "docker.io/${gost%@*}" || { podman pull -q "docker.io/${gost%%:*}@${gost#*@}" > /dev/null \
    && podman tag "docker.io/${gost%%:*}@${gost#*@}" "docker.io/${gost%@*}"; }
  local label rc=0
  trap 'release' EXIT
  for label in "$@"; do
    check_task "$label" || { rc=$?; break; }
    release
  done
  exit "$rc"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then main "$@"; fi  # sourced (the tests): functions only
