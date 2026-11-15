#!/usr/bin/env bash
# The long-horizon live probe (plan Task 4, "The live probe", items 1 to 4): three sessions of the recordings'
# scratch task, one after another at effort low, medium and high, in the ladder's configuration (CLI 2.1.311 in
# the task container, token mode with a fake token per session, the relay as base URL, the deny list, the
# recordings' allowlist, model claude-haiku-5-5, verification off), through passthrough.py on the owner's
# subscription token. It runs only under the coordinator's approval row in the plan's ledger: exactly one table
# row of the plan reads `| <date> | Live probe approved | <the kit's commit> <the limits> |`, its second cell
# exactly that phrase and its third cell starting with the kit's commit in full (40 hex characters) and a space or
# a period. The kit's commit is the last commit that changed this directory; the row is committed after it.
#
#   LH_PROBE_SPEND_AUTHORIZED=yes LH_PROBE_COMMIT=<the kit's last commit> LH_TOKEN_FILE=<path> \
#     live_probe.sh OUT                                                   (the probe: subscription usage)
#   LH_PROBE_SPEND_AUTHORIZED=yes LH_PROBE_COMMIT=<the kit's commit> LH_PROBE_STAND_IN=<stub_api.py scenario> \
#     LH_PROBE_STATE=<dir> LH_TRANSCRIPTS=<dir> [LH_PROBE_LEDGER=<file>] live_probe.sh OUT
#                                                                         (against stub_api.py: no token, no spend)
#
# OUT is normally $LH/recordings/live-probe; cutting fixtures from it and hashing it into recordings.json is done
# afterwards, as for the other recordings. A stand-in run puts stub_api.py behind the passthrough's rehearsal
# switch, whose canary stands for the token.
#
# Refuses (exit 3) before anything starts: without LH_PROBE_SPEND_AUTHORIZED=yes; a kit commit other than
# LH_PROBE_COMMIT; no single approval row for it in the ledger, or more than one (the plan; LH_PROBE_LEDGER in a
# stand-in run only); for the
# probe, a kit with uncommitted changes or no LH_TOKEN_FILE; for a stand-in run, a token file, or no LH_PROBE_STATE
# or LH_TRANSCRIPTS (a stand-in run never reads the agents' transcripts); no provider guard; a scratch task off the
# recordings' allowlist; an existing OUT; a probe that has run. Its state directory ($HOME/.local/state/lh-probe
# for the probe) is claimed once, for good (no second try under one approval row), and only once the passthrough
# reports it is listening: a start the passthrough refuses claims nothing, and its state is moved aside to
# STATE.start-<time> by the next run. The passthrough runs with an empty environment but PATH.
#
# Limits (item 1), enforced by the passthrough's meter: 6 requests and priced USD 0.15 per session, 18 and USD
# 0.45 in all; the CLI's own budget USD 0.10 a session. Each session has its own slot and fake token, and only
# that slot is open while it runs. Stop rule (item 3), read after each session from the passthrough's log and
# events, the session's stream, its egress log and the runtime check: a vendor status other than 200, a refusal by
# the passthrough (a limit), a response naming another model, a stop or closed starts, isUsingOverage other than
# false, the CLI's budget stop, an allowed connection to anything but the relay, a runtime-check finding. The
# probe then ends at once; there is no second try. Within a session the passthrough's --stop-on-non-200 makes the
# first answer other than 200 a stop, so the CLI's own retries of it are refused.
# The runtime check, per session, before its containers are removed (they are kept by the harness's
# keep_containers): every container of the trial is inspected, each one's process environments are read every 2 s
# while the harness runs, and the agent container's exported file system is streamed through token_scan.py.
# At the end: token_scan.py over the file set (OUT, the probe's state, $LH/recordings, this checkout, the agents'
# transcripts); a stand-in run makes it the canary check. Then OUT/probe.json: what item 2 records and item 4's
# verdict (exit 0 when the probe passes, 1 when it does not).
set -euo pipefail

MODEL=claude-haiku-5-5
EFFORTS=(low medium high)
CAP_REQUESTS=6 CAP_USD=0.15 TOTAL_REQUESTS=18 TOTAL_USD=0.45 CLI_BUDGET=0.10
CLI_VERSION=2.1.311
RELAY=relay:8080
DENY=Task,CronCreate,CronDelete,CronList,EnterWorktree,ExitWorktree,ListAgents,Monitor,NotebookEdit,RemoteTrigger,ReportFindings,ScheduleWakeup,SendMessage,Skill,TaskStop,ToolSearch,Workflow,Write  # recording tok3-normal

refuse() { echo "live_probe.sh: refused: $*" >&2; exit 3; }
[ "${LH_PROBE_SPEND_AUTHORIZED:-}" = yes ] ||
  refuse "this uses the owner's subscription; set LH_PROBE_SPEND_AUTHORIZED=yes only under the ledger's approval row"
[ $# -eq 1 ] || { echo "usage: LH_PROBE_SPEND_AUTHORIZED=yes LH_PROBE_COMMIT=... live_probe.sh OUT" >&2; exit 2; }
HERE=$(cd "$(dirname "$0")" && pwd -P)
REPO=$(git -C "$HERE" rev-parse --show-toplevel)
LH=${LH:-$HOME/lh-cache}
NO_PROVIDER=$REPO/experiments/thread_m/no_provider
[ -x "$NO_PROVIDER/claude" ] || refuse "no provider guard at $NO_PROVIDER"
KIT_COMMIT=$(git -C "$REPO" log -1 --format=%H -- "$HERE")
APPROVAL="LH_PROBE_COMMIT must be the kit's last commit (git log -1 --format=%H -- $HERE), and exactly one ledger row must read '| <date> | Live probe approved | <that full 40-character hash> <the limits> |' (the hash first in the third cell, then a space or a period)"
[[ $KIT_COMMIT =~ ^[0-9a-f]{40}$ ]] || refuse "no 40-character commit for the kit; $APPROVAL"
[ "$KIT_COMMIT" = "${LH_PROBE_COMMIT:-}" ] || refuse "LH_PROBE_COMMIT is not the kit's commit $KIT_COMMIT; $APPROVAL"
LEDGER=$REPO/docs/plans/2026-11-13-long-horizon-task-family-and-seed-plan.md
if [ -n "${LH_PROBE_STAND_IN:-}" ]; then
  [ -z "${LH_TOKEN_FILE:-}" ] || refuse "a stand-in run never names a token file"
  [ -n "${LH_PROBE_STATE:-}" ] && [ -n "${LH_TRANSCRIPTS:-}" ] || refuse "a stand-in run needs LH_PROBE_STATE and LH_TRANSCRIPTS"
  STATE=$LH_PROBE_STATE TRANSCRIPTS=$LH_TRANSCRIPTS CREDENTIAL=rehearsal LEDGER=${LH_PROBE_LEDGER:-$LEDGER}
else
  [ -n "${LH_TOKEN_FILE:-}" ] || refuse "no LH_TOKEN_FILE"
  [ -z "$(git -C "$REPO" status --porcelain -- "$HERE")" ] || refuse "the kit has uncommitted changes"
  STATE=$HOME/.local/state/lh-probe TRANSCRIPTS=${LH_TRANSCRIPTS:-$HOME/.claude/projects} CREDENTIAL=live
fi
ROWS=$(awk -F'|' -v hash="$KIT_COMMIT" '
  function trim(s) { sub(/^ +/, "", s); sub(/ +$/, "", s); return s }
  substr($0, 1, 2) == "| " && trim($3) == "Live probe approved" {
    cell = $4; sub(/^ +/, "", cell)
    if (index(cell, hash) == 1 && substr(cell, length(hash) + 1, 1) ~ /^[ .]$/) rows++
  }
  END { print rows + 0 }' "$LEDGER" 2>/dev/null) || ROWS=0
[ "$ROWS" = 1 ] || refuse "$ROWS approval rows for $KIT_COMMIT in $LEDGER; $APPROVAL"
OUT=$(realpath -m "$1")
[ ! -e "$OUT" ] || refuse "$OUT exists"
TASK=$LH/scratch/recording-task
grep -qx 'network_mode = "allowlist"' "$TASK/task.toml" 2>/dev/null &&
  grep -qx 'allowed_hosts = \["relay", "pypi.org", "files.pythonhosted.org"\]' "$TASK/task.toml" ||
  refuse "$TASK/task.toml is not on the recordings' allowlist (record.sh make_task)"
PYTHON=$(command -v "${LH_PYTHON:-python3}") || refuse "no python3"
mkdir -p -m 700 "$(dirname "$STATE")"
[ ! -e "$STATE/claimed" ] || refuse "$STATE is claimed: the probe has run (one run, no second try)"
if [ -e "$STATE" ] || [ -e "$STATE.canary" ]; then  # a start that never claimed: no session ran under it
  aside=$STATE.start-$(date +%s)
  mkdir -m 700 "$aside"
  for f in "$STATE" "$STATE.canary"; do [ ! -e "$f" ] || mv "$f" "$aside/"; done
fi
mkdir -m 700 "$STATE"

PT=$STATE/passthrough SOCKET_DIR=$STATE/relay
FP=$PT/fingerprint.json
mkdir -m 700 "$PT" "$SOCKET_DIR"
export PATH="$NO_PROVIDER:$LH/hvenv/bin:/usr/local/bin:/usr/bin:/bin"
PASS= STUB= HARBOR=
cleanup() {
  local pid
  for pid in $HARBOR $PASS $STUB; do kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT

wait_for() {  # wait_for FILE TEXT PID: until FILE holds TEXT, while PID lives, 120 s at most
  local i
  for i in $(seq 1200); do
    grep -q "$2" "$1" 2>/dev/null && return 0
    kill -0 "$3" 2>/dev/null || break
    sleep 0.1
  done
  echo "live_probe.sh: $1 never showed '$2'" >&2
  exit 4
}

write_slots() {  # write_slots '<slots object>': the passthrough reads the file at every request, so replace it whole
  printf '{"total_usd": %s, "total_requests": %s, "slots": %s}\n' "$TOTAL_USD" "$TOTAL_REQUESTS" "$1" > "$PT/slots.json.new"
  mv "$PT/slots.json.new" "$PT/slots.json"
}

trial_prefix() {  # trial_prefix DIR: the container-name prefix of DIR's trial (podman-compose's project, lower case)
  local trial
  trial=$(ls -d "$1"/jobs/*/recording-task__*/ 2>/dev/null | head -1 || true)
  [ -z "$trial" ] || echo "$(basename "$trial" | tr '[:upper:]' '[:lower:]')__env_"
}

trial_containers() {  # trial_containers DIR [-a]: the names of this trial's containers only; other sessions' are left alone
  local prefix c
  prefix=$(trial_prefix "$1")
  [ -n "$prefix" ] || return 0
  podman ps ${2:-} --format '{{.Names}}' | while read -r c; do case "$c" in "$prefix"*) echo "$c" ;; esac; done
}

follow() {  # follow PID DIR: while the harness runs, read each trial container's process environments
  local c
  while kill -0 "$1" 2>/dev/null; do
    for c in $(trial_containers "$2"); do
      podman exec "$c" sh -c 'cat /proc/[0-9]*/environ 2>/dev/null; true' >> "$2/containers/$c.environ" 2>/dev/null || true
    done
    sleep 2
  done
}

scan_into() {  # scan_into FILE PATH...: append token_scan.py's lines and an `exit N` line to FILE
  local code=0
  "$PYTHON" -I "$HERE/token_scan.py" scan --fingerprint "$FP" "${@:2}" >> "$1" || code=$?
  echo "exit $code" >> "$1"
}

runtime_check() {  # runtime_check DIR: the kept containers' configuration, environments and the agent's file system
  local dir=$1 report=$1/runtime-scan.txt containers c main
  containers=$(trial_containers "$dir" -a)
  if [ -z "$containers" ]; then echo "exit 2 (no container of the trial was found)" > "$report"; return; fi
  for c in $containers; do
    podman inspect "$c" > "$dir/containers/$c.inspect.json" 2>&1 || true
    case "$c" in *egress-control-sidecar*) podman logs "$c" > "$dir/egress-$c.log" 2>&1 || true ;; esac
  done
  scan_into "$report" "$dir/containers"
  main=$(printf '%s\n' $containers | grep '_main_1$' || true)
  if [ -z "$main" ]; then echo "exit 2 (no agent container)" >> "$report"; return; fi
  if ! podman export "$main" | scan_into "$report" -; then echo "exit 2 (export of $main failed)" >> "$report"; fi
}

remove_containers() {  # remove_containers DIR: this trial's containers and networks
  local prefix c n
  prefix=$(trial_prefix "$1")
  [ -n "$prefix" ] || return 0
  for c in $(trial_containers "$1" -a); do podman rm -f -t 5 "$c" > /dev/null 2>&1 || true; done
  for n in $(podman network ls --format '{{.Name}}' 2>/dev/null); do
    case "$n" in "$prefix"*) podman network rm "$n" > /dev/null 2>&1 || true ;; esac
  done
}

session() {  # session EFFORT: one harness trial with its own slot and fake token
  local effort=$1 dir=$OUT/$1 fake rc=0
  mkdir -m 700 "$dir" "$dir/containers"
  fake=lh-fake-slot-$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')  # the form Task 2a records for the CLI
  write_slots "{\"probe-$effort\": {\"token\": \"$fake\", \"cap_usd\": $CAP_USD, \"cap_requests\": $CAP_REQUESTS}}"
  env -i HOME="$HOME" XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" PATH="$PATH" HARBOR_TELEMETRY=0 \
    DO_NOT_TRACK=1 CONTAINERS_CONF_OVERRIDE="$LH/logs/containers-override.conf" LH_RELAY_SOCKET_DIR="$SOCKET_DIR" \
    CLAUDE_FORCE_OAUTH=1 CLAUDE_CODE_OAUTH_TOKEN="$fake" \
    "$LH/hvenv/bin/python" -I "$HERE/harbor_patient.py" run --path "$TASK" --agent claude-code -m "anthropic/$MODEL" \
    --base-url "http://$RELAY" --skip-credential-checks --ak version=$CLI_VERSION --ak disallowed_tools=$DENY \
    --ak max_budget_usd=$CLI_BUDGET --ae CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000 --effort "$effort" \
    --disable-verification --agent-timeout-multiplier 0.05 --max-retries 0 --ek keep_containers=true --env podman \
    -n 1 -o "$dir/jobs" -q -y --extra-docker-compose "$LH/logs/limits-compose.yaml" \
    --extra-docker-compose "$HERE/relay-compose.yaml" > "$dir/harbor.out" 2>&1 &
  HARBOR=$!
  follow "$HARBOR" "$dir"
  wait "$HARBOR" || rc=$?
  HARBOR=
  echo "harbor rc=$rc" > "$dir/rc"
  write_slots '{}'  # the slot closes with its session
  runtime_check "$dir"
  remove_containers "$dir"
}

PROBE_PY=$(cat <<'EOF'
import glob, json, os, sys

MODEL, RELAY, EFFORTS = "claude-haiku-5-5", "relay:8080", ("low", "medium", "high")


def jsonl(path):
    rows = []
    for line in open(path) if os.path.exists(path) else []:
        try:
            rows.append(json.loads(line))
        except ValueError:  # a line that is not an event (or a cut last line) is not read
            pass
    return [r for r in rows if isinstance(r, dict)]


def trial(out, effort):
    found = sorted(glob.glob(f"{out}/{effort}/jobs/*/recording-task__*/"))
    return found[0] if found else None


def stream(out, effort):
    found = trial(out, effort)
    return jsonl(f"{found}agent/claude-code.txt") if found else []


def assistant_id(event):
    message = event.get("message")
    if event.get("type") == "assistant" and isinstance(message, dict) and message.get("model") != "<synthetic>":
        return message.get("id")
    return None


def session_ids(out, effort):
    """One id per message: the session file repeats a message's row once per content block."""
    found, ids = trial(out, effort), []
    for path in sorted(glob.glob(f"{found}agent/sessions/projects/*/*.jsonl")) if found else []:
        ids += [mid for mid in map(assistant_id, jsonl(path)) if mid and mid not in ids]
    return ids


def connections(out, effort):
    """Hosts the egress proxy connected to; a refused connection ends in `bypass` and never shows `<->`."""
    events = [e for path in sorted(glob.glob(f"{out}/{effort}/egress-*.log")) for e in jsonl(path)]
    return [e.get("host") for e in events if " <-> " in str(e.get("msg", ""))]


def lines(path):
    return [line.strip() for line in open(path)] if os.path.exists(path) else []


def runtime_checks(out, effort):
    return [line for line in lines(f"{out}/{effort}/runtime-scan.txt") if line.startswith("exit")]


def slot_rows(pt, effort):
    return [r for r in jsonl(f"{pt}/requests.jsonl") if r.get("slot") == f"probe-{effort}"]


def row_stops(rows):
    found = []
    for row in rows:
        if row.get("refused"):
            found.append(f"passthrough refused: {row['refused']}")
        elif row.get("status") != 200:
            found.append(f"vendor status {row.get('status')}")
        if row.get("response_model") not in (None, MODEL):
            found.append(f"response model {row['response_model']}")
    return found


def stream_stops(events):
    found = []
    for event in events:
        info = event.get("rate_limit_info") or {}
        if event.get("type") == "rate_limit_event" and info.get("isUsingOverage") is not False:
            found.append("isUsingOverage is not false")
        if event.get("terminal_reason") == "budget_exhausted":
            found.append("the CLI's budget stop")
    return found


def stops(out, pt, effort):
    found = row_stops(slot_rows(pt, effort)) + stream_stops(stream(out, effort))
    found += [f"passthrough {e['event']}: {e.get('reason')}" for e in jsonl(f"{pt}/tranche.jsonl")
              if e.get("event") in ("stop", "close_starts")]
    found += [f"allowed connection to {h}" for h in connections(out, effort) if h != RELAY]
    found += [f"runtime check {line}" for line in runtime_checks(out, effort) if line != "exit 0"]
    return found


def first(events, key, value):
    return next((e for e in events if e.get(key) == value), None)


def prompt_tokens(rows):
    """What the first request's prompt held: input, cache read and cache write tokens."""
    usage = (rows[0].get("usage") or {}) if rows else None
    return None if usage is None else sum(usage.get(k) or 0 for k in PROMPT)


REQUEST_KEYS = ("time", "status", "refused", "limit", "error", "effort", "tools", "beta", "cache_marks", "response_model",
                "message_id", "header_names", "headers", "usage", "usd", "worst_case", "passed_on", "credential")
RESULT_KEYS = ("terminal_reason", "api_error", "api_error_status", "total_cost_usd", "usage", "modelUsage")
PROMPT = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


def record(out, pt, effort):
    """Item 2 for one session."""
    rows, events = slot_rows(pt, effort), stream(out, effort)
    result = first(list(reversed(events)), "type", "result") or {}
    return {"effort": effort, "slot": f"probe-{effort}", "requests": [{k: r.get(k) for k in REQUEST_KEYS} for r in rows],
            "init": first(events, "subtype", "init"),
            "rate_limit_events": [e for e in events if e.get("type") == "rate_limit_event"],
            "result": {k: result.get(k) for k in RESULT_KEYS},
            "egress_logs": sorted(glob.glob(f"{out}/{effort}/egress-*.log")),
            "first_request_prompt_tokens": prompt_tokens(rows), "priced_usd": sum(r.get("usd") or 0 for r in rows),
            "session_message_ids": session_ids(out, effort), "runtime_check": lines(f"{out}/{effort}/runtime-scan.txt")}


def request_failures(rows, ids, effort, credential):
    """Every request of the session file is in the passthrough's log, answered 200 by the model at the effort."""
    by_id, want = {r.get("message_id"): r for r in rows}, (200, MODEL, effort, credential)
    bad = []
    for mid in ids or [None]:
        row = by_id.get(mid) or {}
        if (row.get("status"), row.get("response_model"), row.get("effort"), row.get("credential")) != want:
            bad.append(f"request {mid} is not in the passthrough's log as answered 200 by {MODEL} at {effort}")
    return bad


def failures(out, pt, rec, credential):
    """Item 4 for one session."""
    effort, result = rec["effort"], rec["result"]
    bad = [] if result.get("terminal_reason") == "completed" else ["the session did not end completed"]
    bad += request_failures(slot_rows(pt, effort), rec["session_message_ids"], effort, credential)
    cli = result.get("total_cost_usd")
    if cli is None or abs(rec["priced_usd"] - cli) > 0.01 * cli:
        bad.append(f"priced USD {rec['priced_usd']} against the CLI's {cli}: not within 1%")
    if not rec["egress_logs"]:
        bad.append("no egress log")
    bad += [f"allowed connection to {h}" for h in connections(out, effort) if h != RELAY]
    if runtime_checks(out, effort) != ["exit 0", "exit 0"]:  # configuration and environments, then the file system
        bad.append(f"runtime check {runtime_checks(out, effort)}")
    return [f"{effort}: {b}" for b in bad]


def verdict(out, pt, credential, stop):
    sessions, bad = [], []
    for effort in EFFORTS:
        if not os.path.isdir(f"{out}/{effort}"):
            bad.append(f"{effort}: not run")
            continue
        sessions.append(record(out, pt, effort))
        bad += failures(out, pt, sessions[-1], credential)
    scan = lines(f"{out}/file-set-scan.txt")
    if scan[-1:] != ["exit 0"]:
        bad.append("the file-set scan did not end clean")
    if stop:
        bad.insert(0, f"stopped: {stop}")
    events = [e for e in jsonl(f"{pt}/tranche.jsonl") if e.get("reason") != "passthrough down"]
    with open(f"{out}/probe.json", "w") as fh:
        json.dump({"pass": not bad, "failures": bad, "stopped": stop or None, "credential": credential,
                   "sessions": sessions, "tranche_events": events, "file_set_scan": scan}, fh, indent=1)
    print("probe:", "pass" if not bad else "fail")
    for failure in bad:
        print("  " + failure)
    return 0 if not bad else 1


if sys.argv[1] == "check":
    print("; ".join(stops(*sys.argv[2:5])))
else:
    sys.exit(verdict(*sys.argv[2:5], sys.argv[5] if len(sys.argv) > 5 else ""))
EOF
)
probe_py() { "$PYTHON" -I -c "$PROBE_PY" "$@"; }

write_slots '{}'
if [ -n "${LH_PROBE_STAND_IN:-}" ]; then
  "$PYTHON" -I "$HERE/stub_api.py" --unix "$STATE/stub.sock" --model "$MODEL" --scenario "$LH_PROBE_STAND_IN" \
    --log "$STATE/stub.jsonl" > "$STATE/stub.out" 2>&1 &
  STUB=$!
  wait_for "$STATE/stub.out" listening "$STUB"
  credential=(--rehearsal "$STATE/stub.sock" --canary-out "$STATE.canary")
else
  credential=(--token-file "$LH_TOKEN_FILE")
fi
env -i PATH=/usr/bin:/bin "$PYTHON" -I "$HERE/passthrough.py" --socket "$SOCKET_DIR/passthrough.sock" --state "$PT" \
  --slots "$PT/slots.json" --stop-on-non-200 "${credential[@]}" > "$PT/output.log" 2>&1 &
PASS=$!
wait_for "$PT/output.log" listening "$PASS"
mkdir -m 700 "$STATE/claimed" || refuse "$STATE was claimed by another run"
mkdir -p "$(dirname "$OUT")"
mkdir -m 700 "$OUT" || refuse "$OUT exists"

STOP=
for effort in "${EFFORTS[@]}"; do
  session "$effort"
  reasons=$(probe_py check "$OUT" "$PT" "$effort")
  if [ -n "$reasons" ]; then STOP="$effort: $reasons"; break; fi
done
cleanup
PASS= STUB=
set_scan=("$OUT" "$STATE" "$LH/recordings" "$REPO" "$TRANSCRIPTS")
if [ "$CREDENTIAL" = rehearsal ]; then
  code=0
  "$PYTHON" -I "$HERE/token_scan.py" canary --fingerprint "$FP" --canary "$STATE.canary" "${set_scan[@]}" \
    > "$OUT/file-set-scan.txt" || code=$?
  echo "exit $code" >> "$OUT/file-set-scan.txt"
else
  scan_into "$OUT/file-set-scan.txt" "${set_scan[@]}"
fi
probe_py verdict "$OUT" "$PT" "$CREDENTIAL" "$STOP"
