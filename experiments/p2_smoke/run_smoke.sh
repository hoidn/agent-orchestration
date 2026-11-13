#!/usr/bin/env bash
# The Phase 2 live smoke (tranche T1): the parallel best-of-N consumer, killed mid-map, resumed, reported.
#
#   P2SMOKE_SPEND_AUTHORIZED=yes run_smoke.sh RUNTIME RESULTS_DIR          (the paid run)
#   P2SMOKE_REHEARSAL_STANDINS=DIR run_smoke.sh RUNTIME RESULTS_DIR         (a rehearsal; no spend variable)
#   P2SMOKE_INFRA_RETRY="<reason>" ... run_smoke.sh RUNTIME RESULTS_DIR      (the one retry, by resume)
#
# RUNTIME is the frozen checkout whose `orchestrator` package runs the smoke and whose
# experiments/orc_vs_single_call/workflows/best_of_n.orc is the program. The workspace gets a copy of that
# source with the parallel map the deterministic tests add (`:parallel 2 :workspace repo`), target 2.40, every
# `:model` literal set to claude-haiku-5-5, every `:effort` to "high" and every `:timeout-sec` to 600 (ten minutes
# per call), both aliases bound to the Claude metered template,
# and four candidate repositories. P2SMOKE_MANIFEST_SHA256 must equal the digest of manifest.json (the
# plan ledger's value). Steps: compile; `run` under --max-cost-usd 3, killed (SIGKILL) once two coders have
# committed and the coders of gamma and delta are held by the wrapper before their CLI starts; `resume`;
# `report --format json`; smoke.json. Five paid calls: two coders, then on resume two coders and the judge.
# `resume` runs without --max-cost-usd: the held attempts were cut off by the kill, so a capped resume
# stops with spend_cap_unmetered by contract (specs/cli.md, "Spend cap"); the wrapper (smoke_claude.sh)
# keeps the smoke's cap instead: seven launches at most, USD 0.5 per call, USD 3 for the smoke.
# Before anything is launched it refuses: inside a smoke (nested); without P2SMOKE_SPEND_AUTHORIZED=yes;
# without the ledger's manifest digest, or a kit file differing from manifest.json; a binding other than
# claude-haiku-5-5 on the Claude metered template; a claude that is the blocking no-provider stub; a
# rehearsal stand-in without the kit's marker; a used slot or a second retry, or a retry of an observation;
# in a paid run, a CLI that is a stand-in or is not the pinned version (criterion.json), a runtime or kit with
# uncommitted changes, or a kit that is not the runtime's own experiments/p2_smoke; a CLI other than the first
# slot's; a price table or program copy other than the pinned ones; a run PATH where another directory holds
# a claude or codex; a program that does not compile. When the run stops, for any reason, and when this script
# exits, every call the wrapper started that is still alive is terminated and listed in smoke.json. Slots are claimed
# once, for good, in $HOME/.local/state/p2smoke (a rehearsal: RESULTS_DIR/rehearsal-ledger).
# Output: RESULTS_DIR/<slot>/{smoke.json,workspace/,bin/,run.log,resume.log,report.json,...}.
set -euo pipefail

MODEL=claude-haiku-5-5                        # every call; checked by exact id
TEMPLATE=claude_unrestricted_workspace_metered
CAP_USD=3                                     # the run's --max-cost-usd and the wrapper's smoke ceiling
TARGET=2.40                                   # the target the repository admits; parallel map is available
SOURCE=experiments/orc_vs_single_call/workflows/best_of_n.orc
ENTRY=best_of_n::best-of-n
CANDIDATES=(alpha beta gamma delta)           # gamma and delta are the coders held at the kill
STANDIN_MARKER='# p2smoke-rehearsal-stand-in: makes no provider call'

refuse() { echo "run_smoke.sh: refused: $*" >&2; exit 3; }
PREP= LEDGER= SLOT_DIR= CLAIMED=
# reap PHASE: terminate (SIGKILL to its session's process group) every call the wrapper started that is still
# alive, wait until each group is gone, and append each to SLOT_DIR/terminated.jsonl. The runtime starts each
# provider in its own session, so killing the run never reaches a call in flight.
reap() {
  [ -n "$CLAIMED" ] || return 0            # only calls of a slot this launch claimed
  "$PYTHON" - "$LEDGER" "$SLOT_DIR/terminated.jsonl" "$1" <<'EOF'
import json, os, signal, sys, time
from pathlib import Path
ledger, out, phase = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]

def alive(pid):
    try:
        return os.getsid(pid) == pid      # still the session the wrapper started (pid = sid = pgid)
    except ProcessLookupError:
        return False

for record in sorted(ledger.glob("launch-*/pid")):
    pid = int(record.read_text())
    if not alive(pid):
        continue
    os.killpg(pid, signal.SIGKILL)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    bundle = (record.parent / "bundle").read_text().strip()
    with out.open("a") as stream:
        stream.write(json.dumps({"launch": record.parent.name, "pid": pid, "bundle": bundle, "phase": phase}) + "\n")
EOF
}
cleanup() { reap exit || true; rm -rf ${PREP:+"$PREP"}; }
trap cleanup EXIT

[ -z "${P2SMOKE_IN_RUN:-}" ] || refuse "started from inside the smoke (P2SMOKE_IN_RUN is set): a nested session"
if [ -n "${P2SMOKE_REHEARSAL_STANDINS:-}" ]; then
  [ -z "${P2SMOKE_SPEND_AUTHORIZED:-}" ] || refuse "a rehearsal never runs while P2SMOKE_SPEND_AUTHORIZED is set"
  REHEARSAL=true
else
  [ "${P2SMOKE_SPEND_AUTHORIZED:-}" = yes ] ||
    refuse "this starts paid $MODEL calls; set P2SMOKE_SPEND_AUTHORIZED=yes once the tranche is approved"
  REHEARSAL=false
fi
if [ $# -ne 2 ]; then
  echo "usage: P2SMOKE_SPEND_AUTHORIZED=yes run_smoke.sh RUNTIME RESULTS_DIR" >&2
  exit 2
fi
KIT=$(cd "$(dirname "$0")" && pwd -P)
RUNTIME=$(realpath -e "$1" 2>/dev/null) || refuse "no runtime at $1"
ROOT=$(realpath -m "$2")
PYTHON=$(command -v "${P2SMOKE_PYTHON:-python3}") || refuse "no python3"
[ -f "$RUNTIME/orchestrator/__init__.py" ] || refuse "$RUNTIME holds no orchestrator package"
RUNTIME_COMMIT=$(git -C "$RUNTIME" rev-parse HEAD 2>/dev/null) || refuse "$RUNTIME is not a git checkout"
CHECKOUT=$(dirname "$(git -C "$RUNTIME" rev-parse --path-format=absolute --git-common-dir)")
case "$ROOT/" in "$CHECKOUT"/*) refuse "results dir $ROOT is inside the checkout $CHECKOUT";; esac

# What defines the smoke is frozen in manifest.json; the anchor is the digest in the plan's ledger.
KIT_FILES=$("$PYTHON" - "$KIT" <<'EOF'
import hashlib, json, sys
from pathlib import Path
kit = Path(sys.argv[1])
frozen = json.loads((kit / "manifest.json").read_text())
found = {name: hashlib.sha256((kit / name).read_bytes()).hexdigest() if (kit / name).is_file() else None
         for name in sorted(frozen)}
changed = sorted(name for name in frozen if found[name] != frozen[name])
if changed:
    sys.exit(f"run_smoke.sh: {', '.join(changed)} differ from manifest.json")
print(json.dumps(found, sort_keys=True))
EOF
) || refuse "the kit's files are not the frozen ones"
MANIFEST_SHA256=$(sha256sum "$KIT/manifest.json" | cut -d' ' -f1)
[ -n "${P2SMOKE_MANIFEST_SHA256:-}" ] || refuse "set P2SMOKE_MANIFEST_SHA256 to the manifest digest recorded in the plan's ledger"
[ "$P2SMOKE_MANIFEST_SHA256" = "$MANIFEST_SHA256" ] ||
  refuse "manifest.json is $MANIFEST_SHA256, not the ledger's $P2SMOKE_MANIFEST_SHA256"

read -r CLI_PIN PROGRAM_PIN PRICE_PIN TIMEOUT_SEC < <("$PYTHON" -c 'import json, sys; c = json.load(open(sys.argv[1]))
print(c["cli_version"], c["program_sha256"], c["price_table_sha256"], c["call_timeout_sec"])' "$KIT/criterion.json")

# The bindings: both aliases on the Claude metered template, which sets no model of its own; the source copy
# is the runtime's best_of_n.orc with exactly the listed changes, and every :model in it is $MODEL.
PROGRAM=$(PYTHONPATH=$RUNTIME PYTHONDONTWRITEBYTECODE=1 "$PYTHON" - "$KIT" "$RUNTIME/$SOURCE" "$MODEL" "$TEMPLATE" "$TARGET" "$TIMEOUT_SEC" <<'EOF'
import json, re, sys
from pathlib import Path
from orchestrator.providers.registry import ProviderRegistry
kit, source, model, name, target, timeout = sys.argv[1:]
def fail(message):
    sys.exit(f"run_smoke.sh: bindings: {message}")
inputs = json.loads(Path(kit, "inputs.json").read_text())
if set(inputs) != {"task", "intent"}:
    fail(f"inputs.json has keys {sorted(inputs)}")
providers = json.loads(Path(kit, "providers.json").read_text())
if providers != {"providers.coder": name, "providers.judge": name}:
    fail(f"providers.json binds {providers}, not both aliases to {name}")
template = ProviderRegistry().get(name)
if template is None or template.command[0] != "claude" or template.defaults.get("model") not in (None, model):
    fail(f"template {name} is missing, not a claude call, or defaults to another model")
text = Path(source).read_text()
changes = [('(:target-dsl "2.35")', f'(:target-dsl "{target}")', 1),
           ("(list/map-effect ((repo repos)) :max 8\n", "(list/map-effect ((repo repos)) :max 8 :parallel 2 :workspace repo\n", 1),
           (':model "claude-sonnet-5-5"', f':model "{model}"', 1), (':model "gpt-6-sol"', f':model "{model}"', 2),
           (':effort "medium"', ':effort "high"', 1), (":timeout-sec 5400", f":timeout-sec {timeout}", 3)]
for old, new, count in changes:
    if text.count(old) != count:
        fail(f"{source} holds {old.strip()!r} {text.count(old)} times, not {count}")
    text = text.replace(old, new)
operands = set(re.findall(r":model\s+([^\s()]+)", text))
if operands != {f'"{model}"'}:
    fail(f"the copy binds :model to {sorted(operands)}, not only to {model}")
efforts = set(re.findall(r":effort\s+([^\s()]+)", text))
if efforts != {'"high"'}:
    fail(f"the copy binds :effort to {sorted(efforts)}, not only to high")
if set(re.findall(r":timeout-sec\s+([^\s()]+)", text)) != {timeout}:
    fail(f"the copy has a :timeout-sec other than {timeout}")
print(text, end="")
EOF
) || refuse "a binding is not $MODEL on $TEMPLATE"

is_stub() {
  case "$1" in */no_provider/*|*/provider-guard/*) return 0;; esac
  grep -qs -e 'no provider calls' -e 'test provider guard' "$1"
}
CALLER_CLAUDE=$(command -v claude || true)
if [ "$REHEARSAL" = true ]; then
  CLAUDE=$(realpath -e "$P2SMOKE_REHEARSAL_STANDINS/claude" 2>/dev/null) ||
    refuse "no stand-in claude in $P2SMOKE_REHEARSAL_STANDINS"
  case "$CLAUDE" in "$HOME"/.local/share/claude/*) refuse "$CLAUDE is an installed Claude CLI, not a stand-in";; esac
  [ -z "$CALLER_CLAUDE" ] || [ "$(readlink -f "$CALLER_CLAUDE")" != "$CLAUDE" ] ||
    refuse "$CLAUDE is the claude on PATH, not a stand-in"
  [ "$(stat -c %s "$CLAUDE")" -lt 1000000 ] && grep -qxF "$STANDIN_MARKER" "$CLAUDE" ||
    refuse "$CLAUDE is not one of the kit's stand-ins (no marker line)"
  LEDGER=$ROOT/rehearsal-ledger
else
  [ -n "$CALLER_CLAUDE" ] || refuse "no claude on PATH"
  CLAUDE=$(readlink -f "$CALLER_CLAUDE")
  LEDGER=$HOME/.local/state/p2smoke
fi
! is_stub "$CLAUDE" || refuse "claude resolves to the blocking no-provider stub $CLAUDE; a rehearsal needs P2SMOKE_REHEARSAL_STANDINS"

# Slots: the smoke once, and one retry by resume, only of a first attempt that is an infrastructure failure.
RETRY_REASON=${P2SMOKE_INFRA_RETRY:-}
FIRST_DIR=$ROOT/smoke
if [ -n "$RETRY_REASON" ]; then
  SLOT=smoke-retry
  [ ! -e "$LEDGER/$SLOT" ] || refuse "the kit's one retry is used ($LEDGER/$SLOT)"
  [ -d "$LEDGER/smoke" ] || refuse "the smoke has not run, so there is nothing to retry"
  [ "$(sed -n 1p "$LEDGER/smoke/claimed")" = "$FIRST_DIR" ] ||
    refuse "the smoke ran under $(sed -n 1p "$LEDGER/smoke/claimed"), not $FIRST_DIR"
  [ -f "$FIRST_DIR/smoke.json" ] || refuse "the first attempt filed no smoke.json (still running, or died): no retry by resume"
  [ "$(cat "$FIRST_DIR/bin/claude.target")" = "$CLAUDE" ] ||
    refuse "the retry would run $CLAUDE, but the first slot ran $(cat "$FIRST_DIR/bin/claude.target")"
  "$PYTHON" -B "$KIT/readout.py" --retry-check "$ROOT" >&2 || refuse "the first attempt is not an infrastructure failure"
else
  SLOT=smoke
  [ ! -e "$LEDGER/$SLOT" ] || refuse "slot $SLOT is used ($LEDGER/$SLOT); an infrastructure retry needs P2SMOKE_INFRA_RETRY"
fi
SLOT_DIR=$ROOT/$SLOT
[ ! -e "$SLOT_DIR" ] || refuse "$SLOT_DIR exists"

if [ "$REHEARSAL" = false ]; then
  ! grep -qxF "$STANDIN_MARKER" "$CLAUDE" || refuse "$CLAUDE is a rehearsal stand-in; a paid run needs the real CLI"
fi
VERSION=$(env -i "HOME=$HOME" PATH=/usr/bin:/bin DISABLE_AUTOUPDATER=1 "$CLAUDE" --version) || refuse "$CLAUDE --version failed"
[ "$REHEARSAL" = true ] || [ "${VERSION%% *}" = "$CLI_PIN" ] ||
  refuse "claude is $VERSION, not the pinned $CLI_PIN (criterion.json cli_version)"
DIRTY=$(git -C "$RUNTIME" status --porcelain -- orchestrator "$SOURCE")
KIT_IN_RUNTIME=$([ "$KIT" = "$(realpath -m "$RUNTIME/experiments/p2_smoke")" ] && echo true || echo false)
if [ "$REHEARSAL" = false ]; then
  [ -z "$DIRTY" ] || refuse "the runtime $RUNTIME has uncommitted changes under orchestrator/ or in $SOURCE"
  KIT_STATE=$(git -C "$KIT" status --porcelain -- . 2>/dev/null) || refuse "the kit $KIT is not in a git checkout"
  [ -z "$KIT_STATE" ] || refuse "the kit $KIT has uncommitted changes"
  [ "$KIT_IN_RUNTIME" = true ] || refuse "the kit $KIT is not the runtime's own experiments/p2_smoke"
fi
[ ! -f "$LEDGER/claude-version" ] || [ "$(cat "$LEDGER/claude-version")" = "$VERSION" ] ||
  refuse "claude is $VERSION, but the first slot ran $(cat "$LEDGER/claude-version")"
PYTHON_VERSION=$("$PYTHON" -c 'import sys; print(sys.version.split()[0])')
PRICE_TABLE_SHA256=$(sha256sum "$RUNTIME/orchestrator/providers/price_table.json" | cut -d' ' -f1)
[ "$PRICE_TABLE_SHA256" = "$PRICE_PIN" ] || refuse "the runtime's price table is $PRICE_TABLE_SHA256, not the pinned $PRICE_PIN"

# Every orchestrator invocation: the frozen runtime's package, provider observation (tmux) off.
DRIVER='import os, sys
import orchestrator
frozen = os.environ["PYTHONPATH"]
if not os.path.realpath(orchestrator.__file__).startswith(frozen + os.sep):
    sys.exit("p2smoke: orchestrator imports from " + orchestrator.__file__ + ", not from the runtime " + frozen)
from orchestrator.workflow.evaluated import runtime
def observation_off():
    raise RuntimeError("p2smoke: provider observation is off")
runtime.observation_backend = observation_off
from orchestrator.cli import main
sys.argv = ["orchestrator", *sys.argv[1:]]
sys.exit(main())'
# A fresh environment: the slot's bin (the claude wrapper, the codex stub) first and no other directory holding
# a claude or codex; every model variable pinned to $MODEL; advisor, CLAUDE.md files, auto memory, the refusal
# fallback and the auto-updater off.
run_path() { printf '%s' "$BIN:$(dirname "$PYTHON"):/usr/bin:/bin"; }
run_env() {
  env -i "HOME=$HOME" "USER=${USER:-$(id -un)}" "LANG=${LANG:-C.UTF-8}" TERM=dumb \
    "PATH=$(run_path)" "PYTHONPATH=$RUNTIME" PYTHONDONTWRITEBYTECODE=1 \
    "ANTHROPIC_MODEL=$MODEL" "ANTHROPIC_DEFAULT_MODEL=$MODEL" "ANTHROPIC_DEFAULT_HAIKU_MODEL=$MODEL" \
    "ANTHROPIC_SMALL_FAST_MODEL=$MODEL" "ANTHROPIC_DEFAULT_SONNET_MODEL=$MODEL" \
    "ANTHROPIC_DEFAULT_OPUS_MODEL=$MODEL" "ANTHROPIC_DEFAULT_FABLE_MODEL=$MODEL" \
    "CLAUDE_CODE_SUBAGENT_MODEL=$MODEL" CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1 \
    CLAUDE_CODE_DISABLE_ADVISOR_TOOL=1 CLAUDE_CODE_DISABLE_REFUSAL_FALLBACK=1 \
    CLAUDE_CODE_DISABLE_CLAUDE_MDS=1 CLAUDE_CODE_DISABLE_AUTO_MEMORY=1 DISABLE_AUTOUPDATER=1 "$@"
}
orc() { (cd "$WS" && run_env "$PYTHON" -c "$DRIVER" "$@"); }
check_run_path() {
  local dir cli
  IFS=: read -r -a RUN_DIRS <<< "$(run_path)"
  for dir in "${RUN_DIRS[@]:1}"; do
    for cli in claude codex; do
      [ ! -e "$dir/$cli" ] || refuse "$dir/$cli is on the smoke's PATH after the wrapper; the agent could reach it"
    done
  done
}
FRONTEND=(workflows/best_of_n.orc --entry-workflow "$ENTRY" --source-root workflows
          --provider-externs-file manifests/providers.json)

mkdir -p "$ROOT" "$LEDGER"
if [ -z "$RETRY_REASON" ]; then
  # The workspace, prepared aside and moved into place whole: the program copy, its bindings, the slot's bin,
  # and four candidate repositories with the same seeded bug, committed the same way every time.
  PREP=$(mktemp -d "$ROOT/.prep-XXXXXX")
  mkdir -p "$PREP/workspace/workflows" "$PREP/workspace/manifests" "$PREP/bin" "$PREP/control"
  printf '%s\n' "$PROGRAM" > "$PREP/workspace/workflows/best_of_n.orc"
  [ "$(sha256sum "$PREP/workspace/workflows/best_of_n.orc" | cut -d' ' -f1)" = "$PROGRAM_PIN" ] ||
    refuse "the program copy is not the pinned one (criterion.json program_sha256)"
  cp "$KIT/providers.json" "$PREP/workspace/manifests/providers.json"
  GIT_FIXED=(env GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_AUTHOR_NAME="P2 smoke fixture"
             GIT_AUTHOR_EMAIL=fixture@example.invalid GIT_COMMITTER_NAME="P2 smoke fixture"
             GIT_COMMITTER_EMAIL=fixture@example.invalid GIT_AUTHOR_DATE=2026-11-13T00:00:00Z
             GIT_COMMITTER_DATE=2026-11-13T00:00:00Z)
  for name in "${CANDIDATES[@]}"; do
    repo=$PREP/workspace/candidates/$name
    mkdir -p "$repo"
    printf 'def add(a, b):\n    return a - b\n' > "$repo/calc.py"
    "${GIT_FIXED[@]}" git -C "$repo" init -q -b main
    "${GIT_FIXED[@]}" git -C "$repo" add calc.py
    "${GIT_FIXED[@]}" git -C "$repo" commit -q -m "Seed the bug"
  done
  FIXTURE_COMMIT=$(git -C "$PREP/workspace/candidates/alpha" rev-parse HEAD)
  cp "$KIT/smoke_claude.sh" "$PREP/bin/claude"
  printf '%s\n' "$CLAUDE" > "$PREP/bin/claude.target"
  printf '%s\n' "$LEDGER" > "$PREP/bin/ledger"
  printf '#!/bin/sh\necho "codex $*" >> "$(dirname "$0")/../codex-calls.log"\necho "p2smoke: codex is not bound" >&2\nexit 97\n' \
    > "$PREP/bin/codex"
  chmod +x "$PREP/bin/claude" "$PREP/bin/codex"
  BIN=$PREP/bin WS=$PREP/workspace
  check_run_path
  orc compile "${FRONTEND[@]}" > "$PREP/compile.json" 2> "$PREP/compile.stderr" ||
    { cat "$PREP/compile.stderr" >&2; refuse "the program copy does not compile with the kit's bindings"; }
  mkdir "$LEDGER/$SLOT" || refuse "slot $SLOT was claimed meanwhile"
  CLAIMED=1
  printf '%s\n%s\n%s\n' "$SLOT_DIR" "$$" "$(date -u +%FT%TZ)" > "$LEDGER/$SLOT/claimed"
  [ -f "$LEDGER/claude-version" ] || printf '%s\n' "$VERSION" > "$LEDGER/claude-version"
  mv "$PREP" "$SLOT_DIR"
  PREP=
  BIN=$SLOT_DIR/bin WS=$SLOT_DIR/workspace
  chmod -R a-w "$BIN"      # the agents run with bypassed permissions; a read-only bin/ is a speed bump, not a wall
  "$PYTHON" - "$KIT/inputs.json" "$WS" "${CANDIDATES[@]}" > "$WS/inputs.json" <<'EOF'
import json, sys
inputs, workspace, names = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3:]
print(json.dumps({**inputs, "repos": [f"{workspace}/candidates/{name}" for name in names]}, indent=2))
EOF
else
  BIN=$FIRST_DIR/bin WS=$FIRST_DIR/workspace
  check_run_path
  mkdir "$LEDGER/$SLOT" || refuse "slot $SLOT was claimed meanwhile"
  CLAIMED=1
  printf '%s\n%s\n%s\n' "$SLOT_DIR" "$$" "$(date -u +%FT%TZ)" > "$LEDGER/$SLOT/claimed"
  mkdir "$SLOT_DIR"
  FIXTURE_COMMIT=$(git -C "$WS/candidates/alpha" rev-parse HEAD)
fi
SOURCE_SHA256=$(sha256sum "$WS/workflows/best_of_n.orc" | cut -d' ' -f1)

set +e
KILL=null RESUME_EXIT=null REPORT_EXIT=null RUN_ID=
if [ -z "$RETRY_REASON" ]; then
  # The kill: `run` in its own session; once the wrapper holds both gamma and delta (so alpha and beta have
  # committed), SIGKILL the run's process group and the held wrappers. It stops waiting at a failed row, at
  # the run's own exit, or after 25 minutes (each call times out after 10), and kills whatever is left; `reap`
  # then terminates any call still in flight (each runs in its own session, out of the run's group).
  KILL=$(cd "$WS" && run_env "P2SMOKE_HOLD=$SLOT_DIR/control" "$PYTHON" - "$PYTHON" "$DRIVER" "$SLOT_DIR/run.log" \
    "${FRONTEND[@]}" --input-file inputs.json --max-cost-usd "$CAP_USD" <<'EOF'
import json, os, signal, subprocess, sys, time
from pathlib import Path
python, driver, log_path, *argv = sys.argv[1:]
control = Path(os.environ["P2SMOKE_HOLD"])

DEADLINE = 1500

def memo():
    found = list(Path(".orchestrate/runs").glob("*/memo.jsonl"))
    rows = []
    for line in found[0].read_text().splitlines() if len(found) == 1 else []:
        try:
            rows.append(json.loads(line))
        except ValueError:      # a line still being written
            continue
    return rows

with open(log_path, "wb") as log:
    process = subprocess.Popen([python, "-c", driver, "run", *argv], stdout=log, stderr=subprocess.STDOUT,
                               start_new_session=True)
start = time.monotonic()
while not (len(list(control.glob("held-*"))) >= 2 or process.poll() is not None
           or any(row.get("record") == "failed" for row in memo()) or time.monotonic() - start > DEADLINE):
    time.sleep(0.1)
held = [json.loads(path.read_text()) for path in sorted(control.glob("held-*"))]
for kill in (lambda: os.killpg(process.pid, signal.SIGKILL), *(lambda pid=h["pid"]: os.kill(pid, signal.SIGKILL) for h in held)):
    try:
        kill()
    except ProcessLookupError:
        pass
process.wait()
rows = memo()
print(json.dumps({"exit": process.returncode, "seconds": round(time.monotonic() - start),
                  "held": sorted(h["bundle"] for h in held), "timed_out": time.monotonic() - start > DEADLINE,
                  "committed_before": [row["identity"] for row in rows if row.get("record") == "committed"],
                  "failed_before": [row["identity"] for row in rows if row.get("record") == "failed"]}))
EOF
)
  RUN_ID=$(cd "$WS" && ls .orchestrate/runs 2>/dev/null | head -1)
  KILL=${KILL:-null}
  reap run
  # Resume only a run killed as planned: two coders committed, two held, nothing else in flight.
  if [ -n "$RUN_ID" ] && echo "$KILL" | "$PYTHON" -c 'import json, sys; k = json.load(sys.stdin)
sys.exit(0 if k and len(k["held"]) == 2 and len(k["committed_before"]) == 2 and not k["failed_before"] else 1)'; then
    orc resume "$RUN_ID" > "$SLOT_DIR/resume.log" 2>&1
    RESUME_EXIT=$?
    reap resume
  fi
else
  RUN_ID=$("$PYTHON" -c 'import json, sys; print(json.load(open(sys.argv[1]))["run_id"])' "$FIRST_DIR/smoke.json")
  orc resume "$RUN_ID" > "$SLOT_DIR/resume.log" 2>&1
  RESUME_EXIT=$?
  reap resume
fi
if [ -n "$RUN_ID" ]; then
  orc report --run-id "$RUN_ID" --format json > "$SLOT_DIR/report.json" 2> "$SLOT_DIR/report.stderr"
  REPORT_EXIT=$?
fi
set -e

# The record, written whole (temporary file, then rename): a readable smoke.json is a finished slot.
"$PYTHON" - "$SLOT_DIR/smoke.json" "$HOME" "$WS" "$LEDGER" "$SLOT_DIR/report.json" "$KILL" "$KIT_FILES" \
  slot "$SLOT" retry_reason "$RETRY_REASON" rehearsal "$REHEARSAL" model "$MODEL" template "$TEMPLATE" \
  cap_usd "$CAP_USD" target "$TARGET" claude_path "$CLAUDE" claude_version "$VERSION" runtime "$RUNTIME" \
  runtime_commit "$RUNTIME_COMMIT" runtime_dirty "$([ -n "$DIRTY" ] && echo true || echo false)" \
  source "$SOURCE" source_sha256 "$SOURCE_SHA256" manifest_sha256 "$MANIFEST_SHA256" python "$PYTHON" \
  python_version "$PYTHON_VERSION" price_table_sha256 "$PRICE_TABLE_SHA256" fixture_commit "$FIXTURE_COMMIT" \
  run_id "$RUN_ID" resume_exit "$RESUME_EXIT" report_exit "$REPORT_EXIT" kit "$KIT" kit_in_runtime "$KIT_IN_RUNTIME" <<'EOF'
import json, os, re, sys
from pathlib import Path
out, home, workspace, ledger, report_path, kill, kit_files, *pairs = sys.argv[1:]
meta = dict(zip(pairs[::2], pairs[1::2]))
for key in ("cap_usd", "resume_exit", "report_exit"):
    meta[key] = json.loads(meta[key])
meta |= {"rehearsal": meta["rehearsal"] == "true", "runtime_dirty": meta["runtime_dirty"] == "true",
         "kit_in_runtime": meta["kit_in_runtime"] == "true",
         "retry_reason": meta["retry_reason"] or None, "kill": json.loads(kill), "kit_files": json.loads(kit_files)}
# The CLI's sessions for the workspace and its candidates (projects/<path, non-alphanumerics replaced by ->):
# each <id>.jsonl transcript and each <id>/ folder, and the hook records in the transcripts.
prefix = re.sub(r"[^A-Za-z0-9]", "-", str(Path(workspace).resolve()))
stores = [d for d in Path(home, ".claude", "projects").glob("*") if d.name == prefix or d.name.startswith(prefix + "-")]
meta["native_sessions"] = sorted({p.stem for d in stores for p in d.glob("*.jsonl")} |
                                 {p.name for d in stores for p in d.glob("*") if p.is_dir()})
traces = 0
for transcript in (p for d in stores for p in d.glob("*.jsonl")):
    for line in transcript.read_text(errors="replace").splitlines():
        try:
            attachment = json.loads(line).get("attachment")
        except (ValueError, AttributeError):
            continue
        traces += isinstance(attachment, dict) and ("hookEvent" in attachment or str(attachment.get("type", "")).startswith("hook_"))
meta["native_hook_traces"] = traces
def field(launch, name):
    return (launch / name).read_text().strip() if (launch / name).is_file() else None

meta["launches"] = [{"launch": d.name, "bundle": field(d, "bundle"), "target": field(d, "target"),
                     "standin": field(d, "standin") == "yes", "pid": int(field(d, "pid") or 0) or None,
                     "refused": (d / "refused").exists()}
                    for d in sorted(Path(ledger).glob("launch-*"), key=lambda d: int(d.name.split("-")[1]))]
terminated = Path(out).parent / "terminated.jsonl"
meta["terminated"] = [json.loads(line) for line in terminated.read_text().splitlines()] if terminated.is_file() else []
runs = sorted(Path(workspace, ".orchestrate", "runs").glob("*/memo.jsonl"))
rows = [json.loads(line) for line in runs[0].read_text().splitlines() if line.endswith("}")] if runs else []
meta["committed_after"] = [row["identity"] for row in rows if row["record"] == "committed"]
try:
    report = json.loads(Path(report_path).read_text())
except (OSError, ValueError):   # no report: the readout names the missing record
    report = {}
meta["status"] = (report.get("run") or {}).get("status")
meta["usage"] = {"steps": {step["identity"]: step["usage"] for step in report.get("steps", []) if "usage" in step},
                 "run": (report.get("run") or {}).get("usage")}
with open(out + ".tmp", "w") as stream:
    json.dump(meta, stream, indent=2, sort_keys=True)
os.replace(out + ".tmp", out)
EOF
echo "$SLOT_DIR: run $RUN_ID, resume exit $RESUME_EXIT, report exit $REPORT_EXIT"
