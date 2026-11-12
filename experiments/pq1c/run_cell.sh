#!/usr/bin/env bash
# Run ONE PQ-1c cell on a fresh clone of the fixture repository, then file its evidence.
#
#   PQ1C_SPEND_AUTHORIZED=yes run_cell.sh RUNTIME CELL RESULTS_ROOT      (a paid run)
#   PQ1C_REHEARSAL_STANDINS=DIR run_cell.sh RUNTIME CELL RESULTS_ROOT     (a rehearsal; no spend variable)
#
# RUNTIME is the frozen checkout whose `orchestrator` package runs the cell and whose workflows/examples
# sources are compared. CELL is exactly one of variant-clean, variant-resumed, baseline-clean,
# baseline-resumed. A paid cell makes four claude-haiku-5-5 calls, each through cell_claude.sh (user-level
# Claude Code setup left out, USD 0.5 per call), under --max-cost-usd 10 for the run (the cap prices at the
# highest tier, 5x Haiku's ordinary rate). Before anything is launched it refuses: without
# PQ1C_SPEND_AUTHORIZED=yes; a binding other than claude-haiku-5-5 on the Claude metered template; a kit file
# whose SHA-256 differs from manifest.json; a CLI version other than the first cell's (recorded in the
# ledger); a claude that is a blocking no-provider stub; a cell
# name outside the four; a used slot; a retry beyond the kit's one; a run PATH where another directory
# holds a claude or codex; in a paid run, uncommitted changes in the kit or in the runtime's
# orchestrator/ or workflows/examples/. Slots are claimed once, for good, in $HOME/.local/state/pq1c
# (a rehearsal: $HOME/.local/state/pq1c-rehearsal), whatever RESULTS_ROOT is.
# PQ1C_INFRA_RETRY="<reason>" runs the kit's single infrastructure retry (slot <cell>-retry): allowed once
# in all, and only for a cell whose first attempt finished as an infrastructure failure (readout.py
# --retry-check) or died without filing its record. A rehearsal runs only a stand-in carrying the kit's
# stand-in marker line, and never while a spend authorization is set.
# Output: RESULTS_ROOT/<slot>/{cell.json,workspace/,run.log,resume.log,report.json,invalidate.json,...}.
set -euo pipefail

MODEL=claude-haiku-5-5                        # every call; checked by exact id
TEMPLATE=claude_unrestricted_workspace_metered
CAP_USD=10                                    # see criterion.json "spend": the per-call ceiling is the real bound
STOPPED=75                                    # the stop driver's exit right after the selected record
STANDIN_MARKER='# pq1c-rehearsal-stand-in: makes no provider call'

refuse() { echo "run_cell.sh: refused: $*" >&2; exit 3; }
PREP= SEED=
cleanup() { rm -rf ${PREP:+"$PREP"} ${SEED:+"$SEED"}; }
trap cleanup EXIT

if [ -n "${PQ1C_REHEARSAL_STANDINS:-}" ]; then
  [ -z "${PQ1C_SPEND_AUTHORIZED:-}" ] || refuse "a rehearsal never runs while PQ1C_SPEND_AUTHORIZED is set"
  REHEARSAL=true
else
  [ "${PQ1C_SPEND_AUTHORIZED:-}" = yes ] ||
    refuse "this starts paid $MODEL calls; set PQ1C_SPEND_AUTHORIZED=yes once the owner has approved the tranche"
  REHEARSAL=false
fi
if [ $# -ne 3 ]; then
  echo "usage: PQ1C_SPEND_AUTHORIZED=yes run_cell.sh RUNTIME CELL RESULTS_ROOT" >&2
  exit 2
fi
KIT=$(cd "$(dirname "$0")" && pwd -P)
RUNTIME=$(realpath -e "$1") || refuse "no runtime at $1"
CELL=$2
ROOT=$(realpath -m "$3")
case $CELL in
  variant-clean|variant-resumed|baseline-clean|baseline-resumed) ;;
  *) refuse "$CELL is not one of the four cells: variant-clean variant-resumed baseline-clean baseline-resumed";;
esac
ARM=${CELL%-*}
MODE=${CELL#*-}
PYTHON=$(command -v "${PQ1C_PYTHON:-python3}") || refuse "no python3"

[ -f "$RUNTIME/orchestrator/__init__.py" ] || refuse "$RUNTIME holds no orchestrator package"
RUNTIME_COMMIT=$(git -C "$RUNTIME" rev-parse HEAD) || refuse "$RUNTIME is not a git checkout"
CHECKOUT=$(dirname "$(git -C "$RUNTIME" rev-parse --path-format=absolute --git-common-dir)")
case "$ROOT/" in "$CHECKOUT"/*) refuse "results root $ROOT is inside the checkout $CHECKOUT";; esac
DIRTY=$(git -C "$RUNTIME" status --porcelain -- orchestrator workflows/examples)
if [ "$ARM" = variant ]; then
  SOURCE=workflows/examples/design_review_execute_agents.orc ENTRY=design_review_execute_agents::run
  STOP_RECORD=settled                         # an agent turn settles after its commit
else
  SOURCE=workflows/examples/design_review_execute.orc ENTRY=design_review_execute::run
  STOP_RECORD=committed                       # a plain provider step ends at its commit
fi

# The bindings: models only through the two inputs, both exactly $MODEL; both provider aliases on the
# Claude metered template, which sets no model of its own; the source binds :model to those inputs only.
PYTHONPATH=$RUNTIME PYTHONDONTWRITEBYTECODE=1 "$PYTHON" - "$KIT" "$RUNTIME/$SOURCE" "$MODEL" "$TEMPLATE" <<'EOF' ||
import json, re, sys
from pathlib import Path
from orchestrator.providers.registry import ProviderRegistry
kit, source, model, name = sys.argv[1:]
def fail(message):
    sys.exit(f"run_cell.sh: bindings: {message}")
inputs = json.loads(Path(kit, "inputs.json").read_text())
if set(inputs) != {"task", "planner_model", "reviewer_model"}:
    fail(f"inputs.json has keys {sorted(inputs)}")
for key in ("planner_model", "reviewer_model"):
    if inputs[key] != model:
        fail(f"{key} is {inputs[key]!r}, not {model}")
providers = json.loads(Path(kit, "providers.json").read_text())
if providers != {"providers.claude": name, "providers.codex": name}:
    fail(f"providers.json binds {providers}, not both aliases to {name}")
template = ProviderRegistry().get(name)
if template is None or template.command[0] != "claude" or template.defaults.get("model") not in (None, model):
    fail(f"template {name} is missing, not a claude call, or defaults to another model")
operands = set(re.findall(r":model\s+([^\s()]+)", Path(source).read_text()))
if not operands or operands - {"planner_model", "reviewer_model"}:
    fail(f"{source} binds :model to {sorted(operands)}, not only to the planner_model and reviewer_model inputs")
EOF
  refuse "a binding is not $MODEL on $TEMPLATE"

# What defines the experiment is frozen in manifest.json: the criterion, the readout, this launcher, the
# wrapper, the task and bindings. Each cell records the manifest's SHA-256; the readout refuses another.
KIT_FILES=$("$PYTHON" - "$KIT" <<'EOF'
import hashlib, json, sys
from pathlib import Path
kit = Path(sys.argv[1])
frozen = json.loads((kit / "manifest.json").read_text())
found = {name: hashlib.sha256((kit / name).read_bytes()).hexdigest() for name in sorted(frozen)}
changed = sorted(name for name in frozen if found[name] != frozen[name])
if changed:
    sys.exit(f"run_cell.sh: {', '.join(changed)} differ from manifest.json")
print(json.dumps(found, sort_keys=True))
EOF
) || refuse "the kit's files are not the frozen ones"
MANIFEST_SHA256=$(sha256sum "$KIT/manifest.json" | cut -d' ' -f1)

is_stub() {
  case "$1" in */no_provider/*|*/provider-guard/*) return 0;; esac
  grep -qs -e 'no provider calls' -e 'test provider guard' "$1"
}
CALLER_CLAUDE=$(command -v claude || true)
if [ "$REHEARSAL" = true ]; then
  CLAUDE=$(realpath -e "$PQ1C_REHEARSAL_STANDINS/claude") || refuse "no stand-in claude in $PQ1C_REHEARSAL_STANDINS"
  case "$CLAUDE" in "$HOME"/.local/share/claude/*) refuse "$CLAUDE is an installed Claude CLI, not a stand-in";; esac
  [ -z "$CALLER_CLAUDE" ] || [ "$(readlink -f "$CALLER_CLAUDE")" != "$CLAUDE" ] ||
    refuse "$CLAUDE is the claude on PATH, not a stand-in"
  [ "$(stat -c %s "$CLAUDE")" -lt 1000000 ] && grep -qxF "$STANDIN_MARKER" "$CLAUDE" ||
    refuse "$CLAUDE is not one of the kit's stand-ins (no marker line)"
  LEDGER=$HOME/.local/state/pq1c-rehearsal
else
  [ -n "$CALLER_CLAUDE" ] || refuse "no claude on PATH"
  CLAUDE=$(readlink -f "$CALLER_CLAUDE")
  LEDGER=$HOME/.local/state/pq1c
fi
! is_stub "$CLAUDE" || refuse "claude resolves to the blocking no-provider stub $CLAUDE; a rehearsal needs PQ1C_REHEARSAL_STANDINS"
if [ "$REHEARSAL" = false ]; then
  [ -z "$DIRTY" ] || refuse "the runtime $RUNTIME has uncommitted changes under orchestrator/ or workflows/examples/"
  KIT_STATE=$(git -C "$KIT" status --porcelain -- . 2>/dev/null) || refuse "the kit $KIT is not in a git checkout"
  [ -z "$KIT_STATE" ] || refuse "the kit $KIT has uncommitted changes"
fi

# Slots. A first run of each cell, and one infrastructure retry in all: at most 20 paid calls.
RETRY_REASON=${PQ1C_INFRA_RETRY:-}
if [ -n "$RETRY_REASON" ]; then
  SLOT=$CELL-retry
  USED=$(find "$LEDGER" -mindepth 1 -maxdepth 1 -name '*-retry' 2>/dev/null | head -1 || true)
  [ -z "$USED" ] || refuse "the kit's one infrastructure retry is used ($USED)"
  [ -d "$LEDGER/$CELL" ] || refuse "$CELL has not run, so there is nothing to retry"
  FIRST=$(sed -n 1p "$LEDGER/$CELL/claimed")
  FIRST_PID=$(sed -n 2p "$LEDGER/$CELL/claimed")
  [ "$(dirname "$FIRST")" = "$ROOT" ] || refuse "the first attempt of $CELL is under $(dirname "$FIRST"), not $ROOT"
  if [ ! -f "$FIRST/cell.json" ]; then
    ! { kill -0 "$FIRST_PID" 2>/dev/null && grep -qa run_cell.sh "/proc/$FIRST_PID/cmdline"; } ||
      refuse "the first attempt of $CELL is still running (pid $FIRST_PID)"
  else
    "$PYTHON" -B "$KIT/readout.py" --retry-check "$FIRST" >&2 ||
      refuse "the first attempt of $CELL is not an infrastructure failure"
  fi
else
  SLOT=$CELL
  [ ! -e "$LEDGER/$SLOT" ] || refuse "slot $SLOT is used ($LEDGER/$SLOT); an infrastructure retry needs PQ1C_INFRA_RETRY"
fi
CELL_DIR=$ROOT/$SLOT
[ ! -e "$CELL_DIR" ] || refuse "$CELL_DIR exists"
VERSION=$(env -i "HOME=$HOME" PATH=/usr/bin:/bin DISABLE_AUTOUPDATER=1 "$CLAUDE" --version) || refuse "$CLAUDE --version failed"
# The CLI version is fixed by the first cell; the operator's other sessions can update a shared install.
[ ! -f "$LEDGER/claude-version" ] || [ "$(cat "$LEDGER/claude-version")" = "$VERSION" ] ||
  refuse "claude is $VERSION, but the first cell ran $(cat "$LEDGER/claude-version")"
PYTHON_VERSION=$("$PYTHON" -c 'import sys; print(sys.version.split()[0])')
PRICE_TABLE_SHA256=$(sha256sum "$RUNTIME/orchestrator/providers/price_table.json" | cut -d' ' -f1)

# One fixture repository per results root, built the same way every time (same commit id) and moved into
# place whole, so parallel first launches agree: the documents of the consumer tests' `design_docs` fixture.
mkdir -p "$ROOT" "$LEDGER"
FIXTURE=$ROOT/fixture.git
GIT_FIXED=(env GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_AUTHOR_NAME="PQ-1c fixture"
           GIT_AUTHOR_EMAIL=fixture@example.invalid GIT_COMMITTER_NAME="PQ-1c fixture"
           GIT_COMMITTER_EMAIL=fixture@example.invalid GIT_AUTHOR_DATE=2026-11-12T00:00:00Z
           GIT_COMMITTER_DATE=2026-11-12T00:00:00Z)
if [ ! -d "$FIXTURE" ]; then
  SEED=$(mktemp -d "$ROOT/.seed-XXXXXX")
  for relpath in AGENTS.md docs/index.md docs/templates/design_template.md; do
    mkdir -p "$SEED/src/$(dirname "$relpath")"
    printf '# %s\n' "$relpath" > "$SEED/src/$relpath"
  done
  printf '.orchestrate/\nworkflows/\nmanifests/\ninputs.json\n' > "$SEED/src/.gitignore"
  "${GIT_FIXED[@]}" git -C "$SEED/src" init -q -b main
  "${GIT_FIXED[@]}" git -C "$SEED/src" add -A
  "${GIT_FIXED[@]}" git -C "$SEED/src" commit -q -m "PQ-1c fixture"
  "${GIT_FIXED[@]}" git clone -q --bare "$SEED/src" "$SEED/fixture.git"
  mv -T "$SEED/fixture.git" "$FIXTURE" 2>/dev/null || [ -d "$FIXTURE" ] || refuse "could not place $FIXTURE"
fi
FIXTURE_COMMIT=$(git -C "$FIXTURE" rev-parse HEAD)

PREP=$(mktemp -d "$ROOT/.prep-XXXXXX")
"${GIT_FIXED[@]}" git clone -q "$FIXTURE" "$PREP/workspace"
mkdir -p "$PREP/workspace/$(dirname "$SOURCE")" "$PREP/workspace/manifests" "$PREP/bin"
cp "$RUNTIME/$SOURCE" "$PREP/workspace/$SOURCE"
cp "$KIT/providers.json" "$PREP/workspace/manifests/providers.json"
cp "$KIT/inputs.json" "$PREP/workspace/inputs.json"
cp "$KIT/cell_claude.sh" "$PREP/bin/claude"
printf '%s\n' "$CLAUDE" > "$PREP/bin/claude.target"
# Nothing here is bound to codex; a call to it fails and is logged beside the cell.
printf '#!/bin/sh\necho "codex $*" >> "$(dirname "$0")/../codex-calls.log"\necho "pq1c: codex is not bound" >&2\nexit 97\n' \
  > "$PREP/bin/codex"
chmod +x "$PREP/bin/claude" "$PREP/bin/codex"
SOURCE_SHA256=$(sha256sum "$RUNTIME/$SOURCE" | cut -d' ' -f1)
FRONTEND=("$SOURCE" --entry-workflow "$ENTRY" --source-root workflows/examples
          --provider-externs-file manifests/providers.json)

# Every orchestrator invocation goes through this driver: tmux observation off (best effort, it never
# changes execution, and a stopped process would leak its server), and with PQ1C_STOP_RECORD set the
# consumer tests' STOP_AFTER_RECORD wrapper: exit 75 right after that record of PQ1C_STOP_TURN is durable.
DRIVER='import os, sys
import orchestrator
frozen = os.environ["PYTHONPATH"]
if not os.path.realpath(orchestrator.__file__).startswith(frozen + os.sep):
    sys.exit("pq1c: orchestrator imports from " + orchestrator.__file__ + ", not from the runtime " + frozen)
from orchestrator.workflow.evaluated import agent_turns, attempts, runtime
def observation_off():
    raise RuntimeError("pq1c: provider observation is off")
runtime.observation_backend = observation_off
if os.environ.get("PQ1C_STOP_RECORD"):
    append = runtime.append_record
    def stop(path, record, **kwargs):
        entry = append(path, record, **kwargs)
        if record["record"] == os.environ["PQ1C_STOP_RECORD"] and record.get("identity", "").endswith(os.environ["PQ1C_STOP_TURN"]):
            os._exit(75)
        return entry
    attempts.append_record = runtime.append_record = agent_turns.append_record = stop
from orchestrator.cli import main
sys.argv = ["orchestrator", *sys.argv[1:]]
sys.exit(main())'
# A fresh environment: the cell's bin (the claude wrapper, the codex stub) first and no other directory
# holding a claude or codex; every model variable pinned to $MODEL; advisor, CLAUDE.md files, auto memory,
# the refusal fallback and the auto-updater off.
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
orc_stopping() { (cd "$WS" && run_env PQ1C_STOP_RECORD="$STOP_RECORD" "PQ1C_STOP_TURN=/ feedback" "$PYTHON" -c "$DRIVER" "$@"); }

BIN=$PREP/bin WS=$PREP/workspace
IFS=: read -r -a RUN_DIRS <<< "$(run_path)"
for dir in "${RUN_DIRS[@]:1}"; do
  for cli in claude codex; do
    [ ! -e "$dir/$cli" ] || refuse "$dir/$cli is on the cell's PATH after the wrapper; the agent could reach it"
  done
done
orc compile "${FRONTEND[@]}" > "$PREP/compile.json" 2> "$PREP/compile.stderr" ||
  { cat "$PREP/compile.stderr" >&2; refuse "the $ARM program does not compile with the kit's bindings"; }

# Claim the slot, then move the prepared cell into place; from here on the cell is filed whatever happens.
mkdir "$LEDGER/$SLOT" || refuse "slot $SLOT was claimed meanwhile"
printf '%s\n%s\n%s\n' "$CELL_DIR" "$$" "$(date -u +%FT%TZ)" > "$LEDGER/$SLOT/claimed"
[ -f "$LEDGER/claude-version" ] || printf '%s\n' "$VERSION" > "$LEDGER/claude-version"
mv "$PREP" "$CELL_DIR"
PREP=
BIN=$CELL_DIR/bin WS=$CELL_DIR/workspace

memo_fact() {   # memo_fact run_id|feedback|stop: one fact of the cell's single run, from its memo
  "$PYTHON" - "$WS" "$1" <<'EOF'
import json, sys
from pathlib import Path
workspace, fact = Path(sys.argv[1]), sys.argv[2]
runs = sorted((workspace / ".orchestrate" / "runs").glob("*/memo.jsonl"))
if fact == "run_id":
    print(runs[0].parent.name if len(runs) == 1 else "")
    sys.exit()
rows = [json.loads(line) for line in runs[0].read_text().splitlines()]
if fact == "feedback":
    print(next(row["identity"] for row in rows if row["record"] == "committed" and row["identity"].endswith("/ feedback")))
    sys.exit()
started = {(row["identity"], row["attempt"]) for row in rows if row["record"] == "started"}
closed = {(row["identity"], row["attempt"]) for row in rows if row["record"] in ("committed", "failed")}
attempts = len(list(runs[0].parent.glob("effects/*/attempt-*/prompt.txt")))
print(json.dumps({"pending": len(started - closed), "last_record": rows[-1]["record"],
                  "last_identity": rows[-1].get("identity", ""), "attempts": attempts}))
EOF
}
tree_digest() { (cd "$1" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1); }

set +e
RUN_ID= RESUME_EXIT=null STOP=null RESUME_SEC=0
START=$(date +%s)
if [ "$MODE" = clean ]; then
  orc run "${FRONTEND[@]}" --input-file inputs.json --max-cost-usd "$CAP_USD" > "$CELL_DIR/run.log" 2>&1
  RUN_EXIT=$?
  RUN_SEC=$(( $(date +%s) - START ))
  RUN_ID=$(memo_fact run_id)
else
  orc_stopping run "${FRONTEND[@]}" --input-file inputs.json --max-cost-usd "$CAP_USD" > "$CELL_DIR/run.log" 2>&1
  RUN_EXIT=$?
  RUN_SEC=$(( $(date +%s) - START ))
  RUN_ID=$(memo_fact run_id)
  [ -z "$RUN_ID" ] || STOP=$(memo_fact stop | "$PYTHON" -c 'import json, sys; print(json.dumps({**json.load(sys.stdin), "exit": int(sys.argv[1])}))' "$RUN_EXIT")
  # Resume only a run the wrapper stopped with nothing in flight; anything else is filed as it stands.
  if [ "$RUN_EXIT" -eq "$STOPPED" ] && [ "$STOP" != null ] && [ "$(echo "$STOP" | "$PYTHON" -c 'import json, sys; print(json.load(sys.stdin)["pending"])')" = 0 ]; then
    START=$(date +%s)
    orc resume "$RUN_ID" --max-cost-usd "$CAP_USD" > "$CELL_DIR/resume.log" 2>&1
    RESUME_EXIT=$?
    RESUME_SEC=$(( $(date +%s) - START ))
  fi
fi
REPORT_EXIT=null
if [ -n "$RUN_ID" ]; then
  orc report --run-id "$RUN_ID" --format json > "$CELL_DIR/report.json" 2> "$CELL_DIR/report.stderr"
  REPORT_EXIT=$?
fi
# The invalidate axis, on a copy of a completed clean run (the cell's own run is never changed).
if [ "$MODE" = clean ] && [ "$RUN_EXIT" -eq 0 ]; then
  cp -a "$WS" "$CELL_DIR/invalidate-copy"
  FEEDBACK=$(memo_fact feedback)
  COPY_RUN=$CELL_DIR/invalidate-copy/.orchestrate/runs/$RUN_ID
  BEFORE=$(tree_digest "$COPY_RUN")
  WS=$CELL_DIR/invalidate-copy orc invalidate "$RUN_ID" "$FEEDBACK" > "$CELL_DIR/invalidate.log" 2>&1
  INVALIDATE_EXIT=$?
  AFTER=$(tree_digest "$COPY_RUN")
  grep -q invalidate_coordinator_committed "$CELL_DIR/invalidate.log"; COMMITTED=$?
  "$PYTHON" -c 'import json, sys; e, i, c, b, a = sys.argv[1:6]
json.dump({"exit": int(e), "identity": i, "coordinator_committed": c == "0", "bytes_unchanged": b == a}, open(sys.argv[6], "w"), indent=2)' \
    "$INVALIDATE_EXIT" "$FEEDBACK" "$COMMITTED" "$BEFORE" "$AFTER" "$CELL_DIR/invalidate.json"
fi
# The CLI's native transcripts for this workspace (it names the directory after the path, every
# non-alphanumeric character replaced by -): the readout compares them with the sessions the attempts name.
NATIVE_SESSIONS=$("$PYTHON" -c 'import json, pathlib, re, sys
d = pathlib.Path(sys.argv[1]) / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(pathlib.Path(sys.argv[2]).resolve()))
print(json.dumps(sorted(p.stem for p in d.glob("*.jsonl"))))' "$HOME" "$WS")
set -e

# The record is written whole (temporary file, then rename), so a readable cell.json is a finished cell.
"$PYTHON" - "$CELL_DIR/cell.json" cell "$CELL" arm "$ARM" mode "$MODE" slot "$SLOT" retry_reason "$RETRY_REASON" \
  rehearsal "$REHEARSAL" model "$MODEL" template "$TEMPLATE" effort "high (fixed by the sources; not verified for Haiku)" \
  cap_usd "$CAP_USD" claude_path "$CLAUDE" claude_version "$VERSION" runtime "$RUNTIME" runtime_commit "$RUNTIME_COMMIT" \
  runtime_dirty "$([ -n "$DIRTY" ] && echo true || echo false)" source "$SOURCE" source_sha256 "$SOURCE_SHA256" \
  manifest_sha256 "$MANIFEST_SHA256" kit_files "$KIT_FILES" python "$PYTHON" python_version "$PYTHON_VERSION" \
  price_table_sha256 "$PRICE_TABLE_SHA256" native_sessions "$NATIVE_SESSIONS" fixture_commit "$FIXTURE_COMMIT" run_id "$RUN_ID" \
  run_exit "$RUN_EXIT" stop "$STOP" resume_exit "$RESUME_EXIT" report_exit "$REPORT_EXIT" run_sec "$RUN_SEC" \
  resume_sec "$RESUME_SEC" <<'EOF'
import json, os, sys
meta = dict(zip(sys.argv[2::2], sys.argv[3::2]))
for key in ("cap_usd", "run_exit", "run_sec", "resume_sec"):
    meta[key] = int(meta[key])
for key in ("stop", "resume_exit", "report_exit", "kit_files", "native_sessions"):
    meta[key] = json.loads(meta[key])
for key in ("rehearsal", "runtime_dirty"):
    meta[key] = meta[key] == "true"
meta["retry_reason"] = meta["retry_reason"] or None
with open(sys.argv[1] + ".tmp", "w") as out:
    json.dump(meta, out, indent=2, sort_keys=True)
os.replace(sys.argv[1] + ".tmp", sys.argv[1])
EOF
echo "$CELL_DIR: run exit $RUN_EXIT, resume exit $RESUME_EXIT"
