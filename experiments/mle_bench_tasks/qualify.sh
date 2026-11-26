#!/usr/bin/env bash
# The qualification check of one competition on containers (MLE-bench family plan, decisions M2 to M4, Task 7). No
# model call, no provider CLI, no Kaggle access. Steps:
#  1. setup: ~/mle-cache with recordings/ (a directory of its own, mode 700, which the wrapper requires), logs/ with
#     the tranche's two host-side files (written once, refused when they differ), and hvenv, a link to the ladder's
#     harness environment (Harbor 0.25.0, podman-compose 1.6.0);
#  2. the images, each built with rootless Podman and no network and named <name>@sha256:<digest>: the verifier's
#     base (BASE, the benchmark's source at its pinned commit, the pinned wheels installed offline), then wrap.py's
#     agent and verifier contexts. The packages (wrap.py) name both images by digest;
#  3. the withholding check (withhold_check.py) on the agent image's file system, exported from a container that is
#     never started; a fail stops here (exit 1);
#  4. the four controls of M2, built by qualify.py inside the verifier image with no network, outside Harbor;
#  5. through Harbor, on the CPU set, with the allowlist overlay of the tranche's criterion, the limits file and the
#     relay's compose file as an attempt has them: the answers and sample legs (oracle agent) and the untouched leg
#     (nop agent) twice each, and each control once (oracle agent);
#  6. prints qualify.py's ten lines (exit 0 when all are ok, 1 otherwise). FIXTURE_CHECKS=1 then runs the fixture's
#     six checks of Task 7 and prints one "check <name>: ok|FAIL ..." line each: digest-start, tag-refused,
#     rebuilt-image, withholding, symlink, relay. Their probe images are removed at the end; the competition's images
#     are kept (their digests are what tasks.json records).
# Everything else goes to $OUT/qualify.log; Harbor's trials are under $OUT/jobs/<label>/, the outcomes in
# $OUT/outcomes.json, the controls in $OUT/controls/, the images' references and sizes in $OUT/images.txt.
# Refusals before anything is built: "qualify.sh: refused: <reason>" on stderr, exit 2.
#
# Usage: qualify.sh <task name> <competition dir> <data dir>
#   <competition dir>, <data dir> as wrap.py takes them (the data dir holds <id>/prepared/{public,private}/).
# Env: MLE (~/mle-cache), OUT ($MLE/qualify/<task name>; must be empty or new), TRANCHE (screen-cpu), CLASS (cpu),
#      CPUS (8-31), PUBLIC_SAMPLE (wrap.py's --public-sample), FLOOR (the sample's listed score), FIXTURE_CHECKS (0),
#      BENCH (~/lh-cache/mle/src), WHEELS (~/lh-cache/mle/wheels), HOME_FREE_GB (60), ROOT_FREE_GB (20),
#      TRIAL_TIMEOUT_S (1800), PY (python3: a Python with PyYAML).
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
LADDER_KIT=$REPO/experiments/long_horizon_tasks
MLE=${MLE:-$HOME/mle-cache} TRANCHE=${TRANCHE:-screen-cpu} CLASS=${CLASS:-cpu} CPUS=${CPUS:-8-31}
PUBLIC_SAMPLE=${PUBLIC_SAMPLE:-} FLOOR=${FLOOR:-} FIXTURE_CHECKS=${FIXTURE_CHECKS:-0}
BENCH=${BENCH:-$HOME/lh-cache/mle/src} WHEELS=${WHEELS:-$HOME/lh-cache/mle/wheels}
HOME_FREE_GB=${HOME_FREE_GB:-60} ROOT_FREE_GB=${ROOT_FREE_GB:-20} TRIAL_TIMEOUT_S=${TRIAL_TIMEOUT_S:-1800}
PY=${PY:-python3}
# The base of both images: python:3.11-slim, pulled once by this digest (2026-11-26); bash is in it (Harbor's probe).
BASE=docker.io/library/python@sha256:61e01f72680f86a5279ad510818ab7b2ee9f049822589d4e34e33e044360356c
# The grader's dependencies at the versions of the benchmark's own image (plan M3; scout report A), installed from
# the checked wheel directory with no index. kaggle is left out: grading never imports it.
PINNED="appdirs diskcache numpy==1.26.4 pandas==2.2.2 scikit-learn==1.5.1 scipy==1.14.1 joblib==1.4.2 py7zr==0.22.0
  pyppmd==1.1.1 pillow==10.4.0 pyyaml tenacity tqdm"
CLEAN_PATH=$REPO/experiments/thread_m/no_provider:$MLE/hvenv/bin:/usr/local/bin:/usr/bin:/bin
NAME_RE='^[a-z0-9][a-z0-9-]{0,11}$'  # wrap.NAME
CONTROLS=(bronze-past bronze-short median-past median-short)

refuse() { echo "qualify.sh: refused: $*" >&2; exit 2; }

free_gb() { df -BG --output=avail "$1" | tail -1 | tr -dc 0-9; }

preflight() {  # <name> <competition dir> <data dir>: every refusal before anything but recordings/ is written
  [ $# = 3 ] || refuse "usage: qualify.sh <task name> <competition dir> <data dir>"
  [[ $1 =~ $NAME_RE ]] || refuse "$1: a task name is 1 to 12 lower-case letters, digits and hyphens, not first a hyphen"
  [ -f "$2/config.yaml" ] || refuse "$2: no config.yaml (not a competition directory)"
  [ -d "$3" ] || refuse "$3: not a data directory"
  OUT=${OUT:-$MLE/qualify/$1}
  [ -z "$(ls -A "$OUT" 2> /dev/null)" ] || refuse "$OUT holds earlier runs; use a new OUT"
  [ ! -L "$MLE" ] && [ ! -L "$MLE/recordings" ] || refuse "$MLE/recordings must be a directory of its own, not a link"
  mkdir -m 700 -p "$MLE" && mkdir -m 700 -p "$MLE/recordings" && chmod 700 "$MLE/recordings" \
    || refuse "$MLE/recordings cannot be made"
  [ -e "$MLE/hvenv" ] || { [ -x "$HOME/lh-cache/hvenv/bin/python" ] && ln -s "$HOME/lh-cache/hvenv" "$MLE/hvenv"; }
  [ -x "$MLE/hvenv/bin/python" ] || refuse "no harness environment at $MLE/hvenv (the ladder's ~/lh-cache/hvenv)"
  [ -x "$REPO/experiments/thread_m/no_provider/claude" ] || refuse "no provider guard"
  [ "$(free_gb /home)" -ge "$HOME_FREE_GB" ] && [ "$(free_gb /)" -ge "$ROOT_FREE_GB" ] \
    || refuse "free disk under ${HOME_FREE_GB} GB on /home or ${ROOT_FREE_GB} GB on /"
  COMMIT=$($PY -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["benchmark"]["commit"])' "$HERE/family.json")
  [ "$(git -C "$BENCH" rev-parse HEAD 2> /dev/null)" = "$COMMIT" ] || refuse "$BENCH is not the benchmark at $COMMIT"
}

log() { echo "$(date -Is) $*" >> "$LOG"; }
die() { log "stop: $*"; echo "qualify.sh: stop: $* (see $LOG)" >&2; exit 1; }

host_files() {  # the tranche's two host-side files, as the launcher compares them
  $PY -I - "$HERE/tranches/$TRANCHE/ladder.json" "$MLE/logs" << 'EOF'
import json, pathlib, sys
side = json.load(open(sys.argv[1]))["harness"]["host_side"]
logs = pathlib.Path(sys.argv[2])
logs.mkdir(mode=0o700, exist_ok=True)
for name, key in (("containers-override.conf", "containers_override"), ("limits-compose.yaml", "limits_compose")):
    path, want = logs / name, side[key]["content"]
    if path.exists() and path.read_text() != want:
        sys.exit(f"{path} is not the criterion's")
    path.write_text(want)
EOF
}

build() {  # <context dir> <image name>: built with no network; prints <name>@sha256:<digest>
  podman build --network none -q -t "$2:qualify" "$1" >> "$LOG" 2>&1 || return 1
  printf '%s@%s\n' "$2" "$(podman image inspect -f '{{.Digest}}' "$2:qualify")"
}

verifier_base() {  # the base image's context under $MLE/images and its build
  local ctx=$MLE/images/verifier-base-${COMMIT:0:7}
  rm -rf "$ctx" && mkdir -p "$ctx" && cp -r "$WHEELS" "$ctx/wheels" && cp -r "$BENCH" "$ctx/mle-bench" \
    && rm -rf "$ctx/mle-bench/.git" || return 1
  printf 'FROM %s\nRUN --mount=type=bind,source=wheels,target=/wheels pip install --no-cache-dir --no-index \\\n  --find-links /wheels %s\nCOPY mle-bench/ /opt/mle-bench/\n' \
    "$BASE" "$(echo $PINNED)" > "$ctx/Dockerfile"
  build "$ctx" localhost/mle-bench/verifier-base
}

withhold() {  # <image ref> <result file>: the check on the file system of a container that is never started
  local id rc
  id=$(podman create "$1" true 2>> "$LOG") || return 2
  podman export -o "$OUT/export.tar" "$id" 2>> "$LOG"
  rc=$?
  podman rm "$id" > /dev/null 2>&1
  [ $rc = 0 ] || return 2
  (cd "$REPO" && $PY -m experiments.mle_bench_tasks.withhold_check --image-ref "$1" --competition "$CID" \
    --export "$OUT/export.tar" --private "$DATA/$CID/prepared/private" --grader "$COMP" \
    --leaderboard "$COMP/leaderboard.csv" --public "$DATA/$CID/prepared/public" --out "$2") >> "$LOG" 2>&1
  rc=$?
  rm -f "$OUT/export.tar"
  return $rc
}

trial() {  # <label> <package dir> <agent>: one Harbor trial as an attempt's path runs it; its rewards recorded
  local label=$1 copy=$OUT/run/$1 jobs=$OUT/jobs/$1
  mkdir -p "$OUT/run" "$jobs" "$OUT/relay"
  (cd "$REPO" && $PY -I "$HERE/qualify.py" overlay "$2" "$copy" "$HERE/tranches/$TRANCHE/ladder.json") >> "$LOG" 2>&1 \
    || { log "$label: overlay refused"; return 0; }
  log "$label: start ($3) load $(cut -d' ' -f1-3 /proc/loadavg)"
  timeout -k 60 "$TRIAL_TIMEOUT_S" setsid env -i HOME="$HOME" PATH="$CLEAN_PATH" \
    XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" HARBOR_TELEMETRY=0 DO_NOT_TRACK=1 \
    CONTAINERS_CONF_OVERRIDE="$MLE/logs/containers-override.conf" LH_RELAY_SOCKET_DIR="$OUT/relay" \
    taskset -c "$CPUS" "$MLE/hvenv/bin/python" -I "$LADDER_KIT/harbor_patient.py" run --env podman -n 1 -q -y \
    --path "$copy" --agent "$3" --job-name "$label" -o "$jobs" --ek keep_containers=true \
    --extra-docker-compose "$MLE/logs/limits-compose.yaml" --extra-docker-compose "$LADDER_KIT/relay-compose.yaml" \
    > "$jobs.out" 2>&1
  log "$label: harness exit $?"
  remove_trial "$label"
  $PY -I "$HERE/qualify.py" record "$label" "$jobs" "$OUT/outcomes.json" >> "$LOG" 2>&1
  images_kept || die "an image of the package left the store during $label"
}

# keep_containers=true, as the launcher's attempts run (ladder.attempt_command): without it Harbor's teardown runs
# `compose down --rmi local`, and podman-compose 1.6.0 then force-removes every localhost/ image the trial used, the
# packages' images included (first run, 2026-11-26). The containers are removed here by name, as the launcher does.
remove_trial() {  # <label>: the trial's containers and networks (Harbor names its projects <trial>__...)
  local name
  # --depend: the main container shares the egress sidecar's network namespace, which a plain rm of it refuses
  for name in $(podman ps -a --filter "name=^$1__" --format '{{.Names}}'); do
    podman container exists "$name" && podman rm -f -t 5 --depend "$name"
  done >> "$LOG" 2>&1
  for name in $(podman network ls --filter "name=^$1__" --format '{{.Name}}'); do podman network rm "$name"; done >> "$LOG" 2>&1
}

images_kept() { podman image exists "$AGENT_ID" && podman image exists "$VERIFIER_ID"; }  # by id: a retag keeps it

with_solution() {  # <package dir> <copy dir> <solve.sh text>: the package plus solution/solve.sh
  cp -r "$1" "$2" && rm -rf "$2/solution" && mkdir -p "$2/solution" && printf '%s\n' "$3" > "$2/solution/solve.sh" \
    && chmod 755 "$2/solution/solve.sh"
}

artifact() {  # <label> <path under the submission directory>: the file as Harbor carried it out of the agent
  cat "$OUT"/jobs/"$1"/*/*/artifacts/home/submission/"$2" 2> /dev/null
}

check() { printf 'check %s: %s %s\n' "$1" "$([ "$2" = 0 ] && echo ok || echo FAIL)" "$3"; }

reward_of() {  # <label> <key>: a recorded reward, or "none"
  $PY -I -c 'import json, sys; r = json.load(open(sys.argv[1])).get(sys.argv[2]); print("none" if r is None else r.get(sys.argv[3], "none"))' \
    "$OUT/outcomes.json" "$1" "$2"
}

check_digest() {  # the packages' images are local, named by digest, and a pull of them fails (no registry here)
  local pulled=0 ref
  for ref in "$AGENT" "$VERIFIER"; do timeout 120 podman pull -q "$ref" >> "$LOG" 2>&1 && pulled=1; done
  local unrewarded
  unrewarded=$($PY -I -c 'import json, sys; print(sum(v is None for v in json.load(open(sys.argv[1])).values()))' \
    "$OUT/outcomes.json")
  [ $pulled = 0 ] && [ "$unrewarded" = 0 ] && images_kept
  check digest-start $? "every trial started $AGENT and $VERIFIER and got a reward ($unrewarded without); both are still in the store; a pull of either fails (no registry at localhost)"
  local tagged=${AGENT%@*}:qualify
  "$PY" -I "$HERE/wrap.py" packages "$COMP" "$DATA" "$OUT/tagged" --name "$NAME" --class "$CLASS" \
    --agent-image "$tagged" --verifier-image "$VERIFIER" ${PUBLIC_SAMPLE:+--public-sample "$PUBLIC_SAMPLE"} \
    > /dev/null 2> "$OUT/tagged.err"
  [ $? = 2 ] && grep -q unpinned_image "$OUT/tagged.err" && [ ! -e "$OUT/tagged" ]
  check tag-refused $? "wrap.py packages with $tagged: $(head -c 120 "$OUT/tagged.err")"
}

check_rebuilt() {  # the agent image rebuilt under its name with the answers planted; the package still starts its own
  local ctx=$OUT/planted-context out
  mkdir -p "$ctx" && cp "$OUT/controls/answers.csv" "$ctx/planted-answers.csv"
  printf 'FROM %s\nCOPY planted-answers.csv /home/data/planted-answers.csv\n' "$AGENT" > "$ctx/Dockerfile"
  PLANTED=$(build "$ctx" "${AGENT%@*}") || die "the planted image did not build"
  echo "planted $PLANTED" >> "$OUT/images.txt"
  with_solution "$OUT/attempt" "$OUT/probe-planted" "mkdir -p /home/submission
if [ -e /home/data/planted-answers.csv ]; then echo planted; else echo absent; fi > /home/submission/probe.txt"
  trial probe-planted "$OUT/probe-planted" oracle
  # The rebuild takes the name from the original image, so <name>@<its digest> no longer resolves in the store:
  # the package's agent does not start (Podman tries a pull, which fails), or it starts the original and sees no file.
  out=$(artifact probe-planted probe.txt)
  [ -z "$out" ] && grep -qF "initializing source docker://$AGENT:" "$OUT/jobs/probe-planted.out" \
    && out="not started: $AGENT no longer resolves and its pull fails"
  [ "$PLANTED" != "$AGENT" ] && [ "$(podman image inspect -f '{{.Digest}}' "${AGENT%@*}:qualify")" = "${PLANTED#*@}" ] \
    && [[ $out == absent || $out == "not started"* ]]
  check rebuilt-image $? "${AGENT%@*}:qualify now names ${PLANTED#*@}; the package's trial: ${out:-no record}"
  withhold "$PLANTED" "$OUT/withholding-planted.json"
  local rc=$?
  $PY -I -c 'import json, sys; r = json.load(open(sys.argv[1])); w = json.load(open(sys.argv[2]))
hits = [f["path"] for f in w["findings"]["private_hash"]]
ok = r["verdict"] == "pass" and r["image"] == sys.argv[3] and w["verdict"] == "fail" and w["image"] == sys.argv[4] \
    and any(p.endswith("planted-answers.csv") for p in hits)
print(int(not ok), "%s on %s; %s on %s (private_hash: %s)" % (r["verdict"], r["image"], w["verdict"], w["image"], hits))' \
    "$OUT/withholding.json" "$OUT/withholding-planted.json" "$AGENT" "$PLANTED" > "$OUT/withholding.verdict" 2>> "$LOG"
  local detail="the rebuilt image's check exited $rc, not 1 (a fail)"
  if [ $rc = 1 ]; then read -r rc detail < "$OUT/withholding.verdict"; else rc=1; fi
  check withholding "$rc" "$detail"
  local planted_id  # the name back on the original first, so removing the planted image never prunes it as a parent
  planted_id=$(podman image inspect -f '{{.Id}}' "$PLANTED")
  podman tag "$AGENT_ID" "${AGENT%@*}:qualify" >> "$LOG" 2>&1 && podman rmi "$planted_id" >> "$LOG" 2>&1 \
    && podman image exists "$AGENT" || die "the agent image could not be named again after the planted check"
}

check_symlink() {  # a submission that is a symbolic link to the answers' path in the verifier earns reward 0
  local answers
  answers=$($PY -I -c 'import sys, yaml; print(yaml.safe_load(open(sys.argv[1]))["dataset"]["answers"])' "$COMP/config.yaml")
  with_solution "$OUT/attempt" "$OUT/probe-symlink" "mkdir -p /home/submission
ln -s /private/data/$answers /home/submission/submission.csv"
  trial probe-symlink "$OUT/probe-symlink" oracle
  [ "$(reward_of probe-symlink reward)" = 0 ] && [ "$(reward_of probe-symlink valid_submission)" = 0 ]
  check symlink $? "reward=$(reward_of probe-symlink reward) valid=$(reward_of probe-symlink valid_submission)"
}

check_relay() {  # the relay resolves in the agent's container and not in the verifier's (a probe verifier image)
  local ctx=$OUT/relay-probe-context probe
  mkdir -p "$ctx"
  cat > "$ctx/test.sh" << 'EOF'
#!/bin/bash
mkdir -p /logs/verifier
exec python3 -I -c '
import json, pathlib, socket
try:
    socket.getaddrinfo("relay", 8080)
    here = 1
except OSError:
    here = 0
seen = pathlib.Path("/home/submission/relay.txt")
agent = int(seen.is_file() and seen.read_text().strip() != "")
json.dump({"reward": int(agent and not here), "relay_in_verifier": here, "relay_in_agent": agent},
          open("/logs/verifier/reward.json", "w"))'
EOF
  printf 'FROM %s\nCOPY test.sh /tests/test.sh\nRUN chmod 755 /tests/test.sh\n' "$VERIFIER" > "$ctx/Dockerfile"
  probe=$(build "$ctx" localhost/mle-bench/relay-probe) || die "the relay probe image did not build"
  echo "relay-probe $probe" >> "$OUT/images.txt"
  with_solution "$OUT/attempt" "$OUT/probe-relay" "mkdir -p /home/submission
getent hosts relay > /home/submission/relay.txt || true"
  sed -i "s|^docker_image = \"$VERIFIER\"\$|docker_image = \"$probe\"|" "$OUT/probe-relay/task.toml"
  trial probe-relay "$OUT/probe-relay" oracle
  [ "$(reward_of probe-relay reward)" = 1 ]
  check relay $? "relay_in_agent=$(reward_of probe-relay relay_in_agent) relay_in_verifier=$(reward_of probe-relay relay_in_verifier)"
  podman rmi "$probe" >> "$LOG" 2>&1
}

main() {
  preflight "$@"
  NAME=$1 COMP=$(cd "$2" && pwd) DATA=$(cd "$3" && pwd)
  mkdir -p "$OUT" && LOG=$OUT/qualify.log
  host_files >> "$LOG" 2>&1 || die "the host-side files"
  podman image exists "$BASE" || podman pull -q "$BASE" >> "$LOG" 2>&1 || die "the base image $BASE"
  VBASE=$(verifier_base) || die "the verifier's base image"
  CID=$("$PY" -I "$HERE/wrap.py" contexts "$COMP" "$DATA" "$OUT" --agent-base "$BASE" --verifier-base "$VBASE" \
    ${PUBLIC_SAMPLE:+--public-sample "$PUBLIC_SAMPLE"} 2>> "$LOG" | tee "$OUT/contexts.json" \
    | $PY -I -c 'import json, sys; print(json.load(sys.stdin)["competition"])') || die "wrap.py contexts"
  AGENT=$(build "$OUT/agent-context" "localhost/mle-bench/$NAME-agent") || die "the agent image"
  VERIFIER=$(build "$OUT/verifier-context" "localhost/mle-bench/$NAME-verifier") || die "the verifier image"
  AGENT_ID=$(podman image inspect -f '{{.Id}}' "$AGENT") VERIFIER_ID=$(podman image inspect -f '{{.Id}}' "$VERIFIER")
  local ref
  for ref in "$VBASE" "$AGENT" "$VERIFIER"; do
    echo "$ref $(podman image inspect -f '{{.Size}}' "$ref")" >> "$OUT/images.txt"
  done
  "$PY" -I "$HERE/wrap.py" packages "$COMP" "$DATA" "$OUT" --name "$NAME" --class "$CLASS" --agent-image "$AGENT" \
    --verifier-image "$VERIFIER" ${PUBLIC_SAMPLE:+--public-sample "$PUBLIC_SAMPLE"} > "$OUT/packages.json" 2>> "$LOG" \
    || die "wrap.py packages"
  withhold "$AGENT" "$OUT/withholding.json" || die "the withholding check did not pass on $AGENT"
  mkdir -p "$OUT/controls" && cp "$OUT/answers/solution/submission.csv" "$OUT/controls/answers.csv" \
    && cp "$OUT/sample/solution/submission.csv" "$OUT/controls/sample.csv" || die "the controls' inputs"
  podman run --rm --network none -v "$OUT/controls:/work" -v "$HERE/qualify.py:/kit/qualify.py:ro" "$VERIFIER" \
    python3 -I /kit/qualify.py controls /work >> "$LOG" 2>&1 || die "the controls"
  local leg n label
  for leg in answers sample untouched; do
    for n in 1 2; do
      case $leg in untouched) trial "$leg-$n" "$OUT/attempt" nop ;; *) trial "$leg-$n" "$OUT/$leg" oracle ;; esac
    done
  done
  for label in "${CONTROLS[@]}"; do
    [ -f "$OUT/controls/$label.csv" ] || continue
    cp -r "$OUT/answers" "$OUT/control-$label" && cp "$OUT/controls/$label.csv" "$OUT/control-$label/solution/submission.csv"
    trial "control-$label" "$OUT/control-$label" oracle
  done
  $PY -I "$HERE/qualify.py" lines "$OUT/outcomes.json" "$OUT/controls/controls.json" ${FLOOR:+--floor "$FLOOR"}
  local rc=$?
  if [ "$FIXTURE_CHECKS" = 1 ]; then
    check_digest
    check_rebuilt
    check_symlink
    check_relay
  fi
  exit $rc
}

main "$@"
