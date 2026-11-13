#!/usr/bin/env bash
# Oracle check through the published Harbor harness on rootless Podman, no model call.
# For each task directory: run Harbor's `oracle` agent (reference solution) and its `nop`
# agent (untouched environment), each graded by the task's own separate verifier.
# Pass = oracle reward 1 and nop reward 0. Results land in $LH/jobs/<agent>/<task>/.
#
# Usage: oracle_check.sh <task_dir>...
# Needs: $LH/hvenv (harbor 0.25.0 + podman-compose 1.6.0), harbor_patient.py beside this file.
set -uo pipefail
LH=${LH:-/home/ollie/lh-cache}
HERE=$(cd "$(dirname "$0")" && pwd)
export PATH=/home/ollie/Documents/agent-orchestration/experiments/thread_m/no_provider:$LH/hvenv/bin:/usr/local/bin:/usr/bin:/bin
export HARBOR_TELEMETRY=0 DO_NOT_TRACK=1 PODMAN_COMPOSE_WARNING_LOGS=false
# A runaway task must not starve the shared host: cap processes per container.
LIMITS=$LH/logs/limits-compose.yaml
printf 'services:\n  main:\n    pids_limit: 4096\n' > "$LIMITS"

# Podman resolves short names differently from Docker ("fedora" -> registry.fedoraproject.org;
# "gogost/gost" has no search registry). Pre-pull from Docker Hub under the names the
# Dockerfiles use, so the local lookup finds them. ponytail: two known names; add more as found.
for ref in library/fedora:42@sha256:99e203b80b1c3d8f7e161ec10a68fd02b081ef83a3963553e513c82846b97814 \
           gogost/gost:3.2.7-nightly.20260602@sha256:afc0137758ab4ce399d47a299f9abbacbf522b52a17e59cbb4b4e7a1a66e9196; do
  podman image exists "docker.io/${ref%@*}" && continue
  podman pull -q "docker.io/${ref%%:*}@${ref#*@}" >/dev/null && podman tag "docker.io/${ref%%:*}@${ref#*@}" "docker.io/${ref%@*}"
done

for task in "$@"; do
  name=$(basename "$task")
  for agent in oracle nop; do
    out=$LH/jobs/$agent/$name
    rm -rf "$out"; mkdir -p "$out"
    start=$(date +%s)
    "$LH/hvenv/bin/python" -I "$HERE/harbor_patient.py" run --path "$task" --agent "$agent" \
      --env podman -n 1 -o "$out" -q -y --extra-docker-compose "$LIMITS" > "$out/harbor.out" 2>&1
    echo "$name $agent rc=$? wall_s=$(( $(date +%s) - start ))" | tee -a "$LH/logs/oracle_check.log"
    podman system df --format '{{.Type}} {{.Size}}' | sed -n 1p >> "$LH/logs/oracle_check.log"
  done
done
