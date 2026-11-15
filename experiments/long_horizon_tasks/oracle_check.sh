#!/usr/bin/env bash
# Oracle check of the long-horizon plan (D1, Task 2b) through the published Harbor harness on rootless Podman.
# No model call: the `oracle` agent runs the task's reference solution and the `nop` agent does nothing, each
# graded by the task's own verifier on the task's two pinned images. For each task named:
#  1. its two pinned images are pulled by digest under their docker.io/ full name (D1's host-side step), unless
#     already in the store; a pull first needs its compressed plus unpacked size (tasks.json) above the stop;
#  2. its cached 4.1.0 package ($LH/tasks41/<task>/x) is copied and the copy's task.toml gets the two agent-phase
#     keys (D1, D3): network_mode "allowlist" and the hosts below plus the task's extra_hosts from tasks.json.
#     Removing those two lines must give back the package's task.toml byte for byte; the SHA-256 of the two lines
#     is the overlay digest;
#  3. with INSTALL=1, the pinned CLI is installed once on the agent image by the harness's own path
#     (claude-code --install-only: the public CLI is downloaded; no session starts, no API request is made);
#  4. REPEATS rounds of one oracle and one nop trial, up to CONCURRENCY at once. Before each launch: the disk
#     stop, every image the task needs present under its recorded id, and the load gate (1- and 5-minute load at
#     or below GATE; "none" turns it off, as in the first pass). The gate's two-hour clock runs only while no
#     trial of the run is in flight (D2); two hours closed ends the run with exit 4. Each trial runs under the CPU
#     set CPUS (an affinity every container inherits) and writes meta.txt beside its harness job: load at start
#     and end, wall time and its bound, image ids, overlay digest; `samples` adds load, free space, each
#     container's affinity and cgroup peak memory, and each sidecar's network policy (`network-policy show`,
#     sampled: an agent phase shorter than the sampling interval can fall between two samples);
#  5. the images this run pulled are deleted (never with -f) unless KEEP_IMAGES=1; one that cannot be deleted
#     stays listed in pulled.txt for the next release.
# Stops. The harness runs in its own session (setsid), so its pid is its process group. A stop sends SIGTERM to
# the harness (Harbor 0.25.0 cancels the phase in hand or lets it finish, then takes its containers down and
# exits 130), then SIGKILL to the whole group after STOP_GRACE_S, then removes every container and network still
# named after the trial. A trial stops: when free
# space on / or /home falls under STOP_GB (the run then ends with exit 3); at its wall bound (the task's agent,
# verifier and both build limits plus WALL_MARGIN_S; the run goes on); and when the script gets SIGINT or SIGTERM
# (exit 5: every running trial is stopped this way, then the images are released).
# vba-userform-port-uidfix is the labelled modified task of owner question 4 (coordinator ruling, Task 2b fix
# round 1): the package with the verifier's one-line uid bound change (1000000000 -> 55000), run on the verifier
# image recorded under `variant` in tasks.json (`image_check.py variant` builds and records it once; this script
# only checks its id, and restores its name from the keeper name if a teardown removed it).
# Results: $JOBS/<agent>/<label>/<round>/ (agent oracle, nop or install); summarize.py reads them. JOBS must be
# empty or new, unless RESUME=1.
#
# Usage: oracle_check.sh <task>...      (names as in tasks.json without the "terminal-bench/" prefix)
# Env: LH (default ~/lh-cache), TASKS (default tasks.json beside this script), JOBS (default $LH/jobs/oracle), REPEATS (1), CONCURRENCY (1), CPUS (8-31),
#      GATE (24), INSTALL (0), KEEP_IMAGES (0), RESUME (0), LAUNCH_GAP_S (5: seconds between two launches),
#      STOP_GB (25), STOP_GRACE_S (120), WALL_MARGIN_S (1800), WALL_BOUND_S (set: overrides every trial's bound)
# Needs: $LH/hvenv (harbor 0.25.0 + podman-compose 1.6.0), $LH/logs/containers-override.conf (README), taskset,
#      setsid.
set -uo pipefail
LH=${LH:-$HOME/lh-cache}
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)  # the repository root, two levels above this script
JOBS=${JOBS:-$LH/jobs/oracle} REPEATS=${REPEATS:-1} CONCURRENCY=${CONCURRENCY:-1} CPUS=${CPUS:-8-31}
GATE=${GATE:-24} INSTALL=${INSTALL:-0} KEEP_IMAGES=${KEEP_IMAGES:-0} RESUME=${RESUME:-0}
LAUNCH_GAP_S=${LAUNCH_GAP_S:-5} STOP_GB=${STOP_GB:-25} STOP_GRACE_S=${STOP_GRACE_S:-120}
WALL_MARGIN_S=${WALL_MARGIN_S:-1800} GATE_WAIT_S=${GATE_WAIT_S:-7200} GATE_POLL_S=${GATE_POLL_S:-60}
CLI_VERSION=2.1.311 MODEL=claude-haiku-5-5
HARNESS=${HARNESS:-$LH/hvenv/bin/python -I $HERE/harbor_patient.py}  # ponytail: word-split; paths have no spaces
CLEAN_PATH=$REPO/experiments/thread_m/no_provider:$LH/hvenv/bin:/usr/local/bin:/usr/bin:/bin
LIMITS=$LH/logs/limits-compose.yaml PULLED=$JOBS/pulled.txt STOP_FLAG=$JOBS/.stop TASKS=${TASKS:-$HERE/tasks.json}
WALL_BOUND_S_SET=${WALL_BOUND_S:-} IMAGES= OVERLAY=  # the last two: set by prepare for the task in hand
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

# ---- stops -------------------------------------------------------------------------------------------------

group_alive() { kill -0 -- "-$1" 2> /dev/null; }

stop_harness() {  # <pid>: SIGTERM to the harness (it cancels its trial), then SIGKILL to its process group
  local pid=$1 sig t
  for sig in TERM KILL; do
    [ "$sig" = TERM ] && kill -s TERM "$pid" 2> /dev/null
    [ "$sig" = KILL ] && kill -s KILL -- "-$pid" 2> /dev/null
    for t in $(seq "$STOP_GRACE_S"); do group_alive "$pid" || return 0; sleep 1; done
  done
}

remove_leftovers() {  # <out dir>: containers and networks still named after this trial (the harness names it)
  local out=$1 trial name
  trial=$(cd "$out" && ls -d */*/ 2> /dev/null | head -1 | cut -d/ -f2)
  [ -n "$trial" ] || return 0
  for name in $(podman ps -a --filter "name=^${trial,,}__" --format '{{.Names}}' 2> /dev/null); do
    podman rm -f -t 0 "$name" > /dev/null 2>&1 && echo "removed=container $name" >> "$out/meta.txt"
  done
  for name in $(podman network ls --filter "name=^${trial,,}__" --format '{{.Name}}' 2> /dev/null); do
    podman network rm "$name" > /dev/null 2>&1 && echo "removed=network $name" >> "$out/meta.txt"
  done
}

stop_reason() {  # <free bytes on / and /home> <seconds since launch>: why the trial must stop, if it must
  if ! room_ok $1; then echo "disk free $1"
  elif [ "$2" -ge "$WALL_BOUND_S" ]; then echo "wall bound ${WALL_BOUND_S}s"
  elif [ -e "$STOP_FLAG" ]; then echo "signal"
  fi
}

# ---- sampling ----------------------------------------------------------------------------------------------

sample_policy() {  # <out dir> <sidecar>: the sidecar's network policy, appended when it changes
  local out=$1 c=$2 shown
  shown=$(timeout 60 podman exec "$c" network-policy show 2> /dev/null) || return 0
  [ "$shown" = "${POLICY_SEEN[$c]:-}" ] && return 0
  POLICY_SEEN[$c]=$shown
  echo "policy $c mode=$(sed -n 's/^mode: //p' <<< "$shown" | tr ' ' _) hosts=$(grep -cE '^ *[0-9]+[[:space:]]' <<< "$shown")" \
    >> "$out/samples"
}

sample_containers() {  # <out dir> <prefix>: affinity and peak memory of each container named with the prefix
  # (timeout: a hung podman call must not hold the follower, and with it the trial's stops)
  local out=$1 prefix=$2 c cpid cg
  while read -r c cpid; do
    cg=$(cut -d: -f3 "/proc/$cpid/cgroup" 2> /dev/null) && [ -n "$cg" ] || continue  # exited meanwhile
    cg=/sys/fs/cgroup$cg
    echo "container $c peak=$(cat "$cg/memory.peak" 2> /dev/null) affinity=$(for p in $(cat "$cg/cgroup.procs" \
      2> /dev/null); do taskset -cp "$p" 2> /dev/null | sed 's/.*: //'; done | sort -u | paste -sd'|')" >> "$out/samples"
    case "$c" in *egress-control-sidecar*) sample_policy "$out" "$c" ;; *) continue ;; esac
    case "$FOLLOW_SEEN" in *" $c "*) continue ;; esac
    FOLLOW_SEEN="$FOLLOW_SEEN$c "
    podman logs -f "$c" > "$out/egress-$c.log" 2>&1 &
  done < <(timeout 60 podman ps --filter "name=^$prefix" --format '{{.Names}} {{.Pid}}' 2> /dev/null)
}

follow() {  # <harness pid> <out dir> <label>: sample until the harness exits; stop it when a stop applies
  # The trial directory appears only once the harness has built its trial (before any container), so the
  # follower finds containers by the label's prefix (compose lowercases it); summarize.py keeps the trial's own.
  local pid=$1 out=$2 prefix=${3,,}__ start=$SECONDS load free why
  FOLLOW_SEEN=" "
  declare -gA POLICY_SEEN=()
  while kill -0 "$pid" 2> /dev/null; do
    read -r load _ < /proc/loadavg
    free=$(free_bytes)
    printf 'load %s\nfree %s\n' "$load" "$free" >> "$out/samples"
    why=$(stop_reason "$free" $((SECONDS - start)))
    if [ -n "$why" ]; then
      echo "stop=$why" >> "$out/meta.txt"
      stop_harness "$pid"
      return 0
    fi
    sample_containers "$out" "$prefix"
    sleep 5
  done
}

# ---- the run -------------------------------------------------------------------------------------------

run_harbor() {  # the harness in its own session, with an empty environment: no credential of any kind reaches it
  # exec: the backgrounded subshell becomes setsid, which (not a group leader) becomes the harness in place, so
  # the caller's $! is the harness and its process group
  exec setsid env -i HOME="$HOME" XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" PATH="$CLEAN_PATH" \
    HARBOR_TELEMETRY=0 DO_NOT_TRACK=1 CONTAINERS_CONF_OVERRIDE="$LH/logs/containers-override.conf" \
    taskset -c "$CPUS" $HARNESS run --env podman -n 1 -q -y --extra-docker-compose "$LIMITS" "$@"
}

trial() {  # <label> <agent: oracle, nop or install> <round> <harness args>...: one trial and its meta.txt
  local label=$1 agent=$2 round=$3 out=$JOBS/$2/$1/$3 start rc pid
  shift 3
  rm -rf "$out" && mkdir -p "$out"
  start=$(date +%s)
  printf 'label=%s\nagent=%s\nround=%s\ncpus=%s\ngate=%s\noverlay_sha256=%s\nimages=%s\nwall_bound_s=%s\nload_start=%s\n' \
    "$label" "$agent" "$round" "$CPUS" "$GATE" "$OVERLAY" "$IMAGES" "$WALL_BOUND_S" "$(cut -d' ' -f1-3 /proc/loadavg)" \
    > "$out/meta.txt"
  run_harbor --path "$LH/oracle/tasks/$label" -o "$out" "$@" > "$out/harbor.out" 2>&1 &
  pid=$!
  follow "$pid" "$out" "$label"
  wait "$pid"
  rc=$?
  grep -q '^stop=' "$out/meta.txt" && remove_leftovers "$out"
  printf 'rc=%s\nwall_s=%s\nload_end=%s\n' "$rc" "$(($(date +%s) - start))" "$(cut -d' ' -f1-3 /proc/loadavg)" \
    >> "$out/meta.txt"
  kill $(jobs -p) 2> /dev/null  # the egress log followers
  echo "$label $agent round=$round rc=$rc wall_s=$(($(date +%s) - start)) load=$(cut -d' ' -f1-3 /proc/loadavg)" \
    | tee -a "$JOBS/oracle_check.log"
}

wait_gate() {  # D2: the two-hour clock runs only while no trial of this run is in flight
  local idle_since=$SECONDS
  until gate_open "$GATE"; do
    [ -e "$STOP_FLAG" ] && return 1
    [ -z "$(jobs -rp)" ] || idle_since=$SECONDS
    [ $((SECONDS - idle_since)) -lt "$GATE_WAIT_S" ] \
      || { echo "gate closed for two hours with no trial in flight" | tee -a "$JOBS/oracle_check.log"; return 1; }
    sleep "$GATE_POLL_S"
  done
}

wait_all() {  # every trial of the run, even when a signal interrupts the wait
  while [ -n "$(jobs -rp)" ]; do wait; done
}

task_json() {  # <python expression over the entry `t`> <task>: a value of the task's tasks.json entry
  python3 -I -c 'import json, sys
t = {e["name"]: e for e in json.load(open(sys.argv[1]))["tasks"]}["terminal-bench/" + sys.argv[3]]
print(eval(sys.argv[2]))' "$TASKS" "$1" "$2"
}

wall_bound() {  # <package dir>: the task's agent, verifier and both build limits plus WALL_MARGIN_S, in seconds
  python3 -I -c 'import sys, tomllib
c = tomllib.load(open(sys.argv[1] + "/task.toml", "rb"))
print(int(c["agent"]["timeout_sec"] + c["verifier"]["timeout_sec"] + c["environment"].get("build_timeout_sec", 600)
          + c["verifier"].get("environment", {}).get("build_timeout_sec", 600) + int(sys.argv[2])))' "$1" "$WALL_MARGIN_S"
}

ensure_image() {  # <ref> <bytes a pull needs>: pull by digest unless present (room first); prints the image id
  if ! podman image exists "$1"; then
    room_ok $(free_bytes | awk -v n="$2" '{ print $1 - n, $2 - n }') \
      || { echo "disk stop before pulling $1 (needs $2 bytes)" | tee -a "$JOBS/oracle_check.log" >&2; return 3; }
    podman pull -q "docker.io/$1" > /dev/null && echo "$1" >> "$PULLED" || return 1
  fi
  podman image inspect -f '{{.Id}}' "$1"
}

variant_image() {  # the labelled variant's recorded verifier image: name restored from the keeper if missing
  local name keeper id
  read -r name keeper id < <(task_json '" ".join(t["variant"][k] for k in ("image", "keeper", "image_id"))' vba-userform-port) \
    || { echo "uidfix: no recorded variant in tasks.json (run image_check.py variant)" >&2; return 2; }
  [ "$(podman image inspect -f '{{.Id}}' "$name" 2> /dev/null)" = "$id" ] && { echo "$name $id"; return 0; }
  [ "$(podman image inspect -f '{{.Id}}' "$keeper" 2> /dev/null)" = "$id" ] && podman tag "$id" "$name" \
    && { echo "$name $id"; return 0; }
  echo "uidfix: the recorded variant image $id is not in the store (run image_check.py variant)" >&2
  return 2
}

prepare_variant() {  # <label> <pinned verifier ref>: the copy gets the one-line change and the recorded image
  local label=$1 verifier_ref=$2 copy=$LH/oracle/tasks/$1 name id want
  uidfix "$copy/tests/app_worker.py" || return 2
  want=$(task_json 't["variant"]["sha256_after"]' vba-userform-port) || return 2
  [ "$(sha256sum < "$copy/tests/app_worker.py" | cut -d' ' -f1)" = "$want" ] \
    || { echo "uidfix: the copy's changed file is not the recorded image's" >&2; return 2; }
  read -r name id < <(variant_image) || return 2
  sed -i "s|^docker_image = \"$verifier_ref\"\$|docker_image = \"$name\"|" "$copy/task.toml"
  [ "$(grep -cxF "docker_image = \"$name\"" "$copy/task.toml")" = 1 ] \
    || { echo "uidfix: the verifier image line of $label was not replaced once" >&2; return 2; }
  IMAGES="$IMAGES verifier_derived:$id"
}

prepare() {  # <label>: images, the overlay copy, the wall bound, and for the uidfix label the recorded variant
  local label=$1 task=${1%-uidfix} agent_ref verifier_ref extra aid vid need_a need_v
  agent_ref=$(task_json 't["environment_image"]' "$task") && verifier_ref=$(task_json 't["verifier_image"]' "$task") \
    && read -r need_a need_v < <(task_json '" ".join(str(t["images"][r]["compressed"] + t["images"][r]["unpacked"]) for r in ("agent", "verifier"))' "$task") \
    || return 2
  mapfile -t extra < <(task_json '"\n".join(t["extra_hosts"] or [])' "$task" | sed '/^$/d')
  aid=$(ensure_image "$agent_ref" "$need_a") && vid=$(ensure_image "$verifier_ref" "$need_v") || return $?
  IMAGES="agent:$aid verifier:$vid"
  OVERLAY=$(overlay_task "$LH/tasks41/$task/x" "$LH/oracle/tasks/$label" "${ALLOWLIST[@]}" ${extra[@]+"${extra[@]}"}) || return 2
  WALL_BOUND_S=${WALL_BOUND_S_SET:-$(wall_bound "$LH/tasks41/$task/x")} || return 2
  [ "$label" = "$task" ] || prepare_variant "$label" "$verifier_ref"
}

images_ok() {  # every image id the task needs is still in the store (a teardown must not have removed one)
  local entry
  [[ "$IMAGES" == *verifier_derived:* ]] && { variant_image > /dev/null || return 1; }
  for entry in $IMAGES; do podman image exists "${entry#*:}" || { echo "image gone: $entry" >&2; return 1; }; done
}

launch_ok() {  # the checks before every launch; prints the exit code that ends the task, if one does
  [ -e "$STOP_FLAG" ] && { echo 5; return; }
  room_ok $(free_bytes) || { echo "disk stop" | tee -a "$JOBS/oracle_check.log" >&2; echo 3; return; }
  images_ok || { echo 6; return; }
  wait_gate || { [ -e "$STOP_FLAG" ] && echo 5 || echo 4; }
}

check_task() {  # <label>
  local label=$1 round agent code
  prepare "$label" || return $?
  [ "$INSTALL" = 1 ] && (trial "$label" install 1 --agent claude-code -m "anthropic/$MODEL" \
    --ak "version=$CLI_VERSION" --base-url http://relay:8080 --install-only)
  for round in $(seq 1 "$REPEATS"); do
    for agent in oracle nop; do
      while [ "$(jobs -rp | wc -l)" -ge "$CONCURRENCY" ]; do wait -n; done
      code=$(launch_ok)
      [ -z "$code" ] || { wait_all; return "$code"; }
      trial "$label" "$agent" "$round" --agent "$agent" &
      sleep "$LAUNCH_GAP_S"
    done
  done
  wait_all
  [ ! -e "$STOP_FLAG" ] || return 5
  ! grep -qs '^stop=disk' $(for round in $(seq 1 "$REPEATS"); do echo "$JOBS"/{oracle,nop}/"$label/$round/meta.txt"; done) \
    || return 3
}

release() {  # delete what this run pulled: never -f; an image still in use stays listed for the next release
  local ref kept=()
  [ "$KEEP_IMAGES" = 1 ] || [ ! -s "$PULLED" ] && return 0
  while read -r ref; do
    podman rmi "$ref" > /dev/null 2>&1 || { kept=("$ref" "${kept[@]}"); echo "left in place: $ref" | tee -a "$JOBS/oracle_check.log"; }
  done < <(tac "$PULLED")
  printf '%s' "${kept[@]/%/$'\n'}" > "$PULLED"
}

main() {
  [ "$(git -C "$HERE" rev-parse --show-toplevel 2> /dev/null)" = "$REPO" ] \
    || { echo "$(basename "$0"): $REPO is not this script's repository root" >&2; exit 2; }
  [ -x "$REPO/experiments/thread_m/no_provider/claude" ] || { echo "$(basename "$0"): no provider guard" >&2; exit 2; }
  [ "$RESUME" = 1 ] || [ -z "$(ls -A "$JOBS" 2> /dev/null)" ] \
    || { echo "$(basename "$0"): $JOBS holds earlier runs; use a new JOBS, or RESUME=1 to add to it" >&2; exit 2; }
  export PATH=$CLEAN_PATH
  mkdir -p "$JOBS" "$LH/oracle" && rm -f "$STOP_FLAG"
  printf 'services:\n  main:\n    pids_limit: 4096\n' > "$LIMITS"  # a runaway task must not starve the shared host
  # The egress sidecar's base image, under the name its Dockerfile uses (no search registry on this host).
  local gost=gogost/gost:3.2.7-nightly.20260602@sha256:afc0137758ab4ce399d47a299f9abbacbf522b52a17e59cbb4b4e7a1a66e9196
  podman image exists "docker.io/${gost%@*}" || { podman pull -q "docker.io/${gost%%:*}@${gost#*@}" > /dev/null \
    && podman tag "docker.io/${gost%%:*}@${gost#*@}" "docker.io/${gost%@*}"; }
  local label rc=0
  trap 'release' EXIT
  trap 'touch "$STOP_FLAG"' INT TERM  # the running trials' followers stop their harnesses
  for label in "$@"; do
    check_task "$label" || { rc=$?; break; }
    release
  done
  exit "$rc"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then main "$@"; fi  # sourced (the tests): functions only
