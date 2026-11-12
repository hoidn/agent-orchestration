#!/usr/bin/env bash
# Start one authoring-check session, then run check.py on what it wrote.
#
#   AUTHORING_CHECK_SPEND_AUTHORIZED=yes run_session.sh ENV_DIR SESSIONS_ROOT
#
# This spends provider calls: it refuses to start unless AUTHORING_CHECK_SPEND_AUTHORIZED is exactly
# "yes". ENV_DIR is an arm built by build_env.py. Slots <arm>-1 to <arm>-3 are claimed once, for good, in
# $HOME/.local/state/authoring-check, whatever SESSIONS_ROOT is, so no session is retried and there are at
# most six sessions at USD 2 each. The first session records the claude CLI version there; a later session
# on another version refuses unless AUTHORING_CHECK_ALLOW_CLI_CHANGE=yes. The agent works in a fresh random
# directory under /tmp; afterwards it moves to SESSIONS_ROOT/<arm>-<n>/work, beside transcript.jsonl,
# claude.stderr, check.json, session.json and, if a stub was called, no-provider.log.
set -euo pipefail

MODEL=claude-haiku-5-5   # exact model; no fallback model is passed
CAP_USD=2                # --max-budget-usd, per session
WALL_SEC=1200            # 20-minute wall limit
SESSIONS_PER_ARM=3

refuse() { echo "run_session.sh: refused: $*" >&2; exit 3; }

[ "${AUTHORING_CHECK_SPEND_AUTHORIZED:-}" = yes ] ||
  refuse "this starts a paid $MODEL session; set AUTHORING_CHECK_SPEND_AUTHORIZED=yes once the budget is approved"
if [ $# -ne 2 ]; then
  echo "usage: AUTHORING_CHECK_SPEND_AUTHORIZED=yes run_session.sh ENV_DIR SESSIONS_ROOT" >&2
  exit 2
fi

KIT=$(cd "$(dirname "$0")" && pwd -P)
CHECKOUT=$(dirname "$(git -C "$KIT" rev-parse --path-format=absolute --git-common-dir)")
ENV_DIR=$(realpath -e "$1")
ROOT=$(realpath -m "$2")
for dir in "$ENV_DIR" "$ROOT"; do
  case "$dir/" in "$CHECKOUT"/*) refuse "$dir is inside the checkout $CHECKOUT";; esac
done
ARM=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["arm"])' "$ENV_DIR/env.json")
CLAUDE=$(readlink -f "$(command -v claude)") || refuse "no claude on PATH"
case "$CLAUDE" in */no_provider/*) refuse "claude on PATH is the no-provider stub $CLAUDE";; esac
VERSION=$(DISABLE_AUTOUPDATER=1 "$CLAUDE" --version)

LEDGER=$HOME/.local/state/authoring-check
mkdir -p "$LEDGER" "$ROOT"
if [ -f "$LEDGER/claude-version" ] && [ "$(cat "$LEDGER/claude-version")" != "$VERSION" ] &&
   [ "${AUTHORING_CHECK_ALLOW_CLI_CHANGE:-}" != yes ]; then
  refuse "claude is $VERSION but earlier sessions ran $(cat "$LEDGER/claude-version")"
fi
SLOT=
for n in $(seq 1 "$SESSIONS_PER_ARM"); do
  if mkdir "$LEDGER/$ARM-$n" 2>/dev/null; then SLOT=$ARM-$n; break; fi
done
[ -n "$SLOT" ] || refuse "all $SESSIONS_PER_ARM $ARM slots in $LEDGER are used"
[ -f "$LEDGER/claude-version" ] || printf '%s\n' "$VERSION" > "$LEDGER/claude-version"
SESSION=$ROOT/$SLOT
echo "$SESSION $(date -u +%FT%TZ)" > "$LEDGER/$SLOT/claimed"
mkdir "$SESSION" || refuse "slot $SLOT is claimed but $SESSION exists; nothing was spent"

WORK=$(mktemp -d /tmp/ac-XXXXXXXX)
STUBS=$(mktemp -d /tmp/ac-stubs-XXXXXXXX)
mkdir "$STUBS/bin"
cp "$KIT/../thread_m/no_provider/claude" "$KIT/../thread_m/no_provider/codex" "$STUBS/bin/"
cp "$ENV_DIR/GUIDE.md" "$KIT/line_count.sh" "$WORK/"

# A fresh environment: the arm's orchestrator first, then the no-provider stubs, so `claude` and `codex`
# in the session and in the check fail and log; models pinned; advisor, CLAUDE.md, auto memory and the
# refusal fallback off; no auto-update. Effort is not set: the CLI default applies.
BASE_ENV=(env -i "HOME=$HOME" "USER=${USER:-$(id -un)}" "LANG=${LANG:-C.UTF-8}" TERM=dumb
          "PATH=$ENV_DIR/venv/bin:$STUBS/bin:/usr/local/bin:/usr/bin:/bin")
MODEL_ENV=("ANTHROPIC_MODEL=$MODEL" "ANTHROPIC_DEFAULT_MODEL=$MODEL" "ANTHROPIC_DEFAULT_HAIKU_MODEL=$MODEL"
           "ANTHROPIC_SMALL_FAST_MODEL=$MODEL" "ANTHROPIC_DEFAULT_SONNET_MODEL=$MODEL"
           "ANTHROPIC_DEFAULT_OPUS_MODEL=$MODEL" "ANTHROPIC_DEFAULT_FABLE_MODEL=$MODEL"
           "CLAUDE_CODE_SUBAGENT_MODEL=$MODEL" CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1
           CLAUDE_CODE_DISABLE_ADVISOR_TOOL=1 CLAUDE_CODE_DISABLE_REFUSAL_FALLBACK=1
           CLAUDE_CODE_DISABLE_CLAUDE_MDS=1 CLAUDE_CODE_DISABLE_AUTO_MEMORY=1 DISABLE_AUTOUPDATER=1)
# Shell and file tools only; no subagent tool, no MCP server, no skills; user settings and hooks not loaded.
FLAGS=(-p "$(cat "$KIT/task.md")" --model "$MODEL" --max-budget-usd "$CAP_USD"
       --tools Bash,Read,Write,Edit --strict-mcp-config --setting-sources project --disable-slash-commands
       --permission-mode bypassPermissions --no-session-persistence --output-format stream-json --verbose)

STARTED=$(date +%s)
set +e
cd "$WORK"
# setsid makes the session its own process group, killed whole once it ends or hits the wall limit.
setsid "${BASE_ENV[@]}" "${MODEL_ENV[@]}" timeout --kill-after=30 "$WALL_SEC" "$CLAUDE" "${FLAGS[@]}" \
  < /dev/null > "$SESSION/transcript.jsonl" 2> "$SESSION/claude.stderr" &
GROUP=$!
wait "$GROUP"
CLAUDE_EXIT=$?
kill -KILL -- "-$GROUP" 2>/dev/null
cd /
ENDED=$(date +%s)
"${BASE_ENV[@]}" python3 "$KIT/check.py" "$WORK" > "$SESSION/check.json"
CHECK_EXIT=$?
set -e
[ ! -f "$STUBS/no-provider.log" ] || mv "$STUBS/no-provider.log" "$SESSION/"
rm -rf "$STUBS"
mv "$WORK" "$SESSION/work"

python3 -c 'import json, sys; keys = sys.argv[2::2]; values = sys.argv[3::2]
meta = dict(zip(keys, values))
for key in ("started", "ended", "claude_exit", "check_exit", "cap_usd", "wall_limit_sec"):
    meta[key] = int(meta[key])
json.dump(meta, open(sys.argv[1], "w"), indent=2, sort_keys=True)' "$SESSION/session.json" \
  arm "$ARM" slot "$SLOT" env_dir "$ENV_DIR" commit "$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["commit"])' "$ENV_DIR/env.json")" \
  model "$MODEL" effort "not set (CLI default)" cap_usd "$CAP_USD" wall_limit_sec "$WALL_SEC" \
  claude_path "$CLAUDE" claude_version "$VERSION" checkout "$CHECKOUT" home "$HOME" sessions_root "$ROOT" \
  work_during_session "$WORK" started "$STARTED" ended "$ENDED" claude_exit "$CLAUDE_EXIT" check_exit "$CHECK_EXIT"
echo "$SESSION: claude exit $CLAUDE_EXIT, check exit $CHECK_EXIT"
