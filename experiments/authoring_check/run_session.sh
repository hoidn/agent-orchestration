#!/usr/bin/env bash
# Start one authoring-check session, then run check.py on what it wrote.
#
#   AUTHORING_CHECK_SPEND_AUTHORIZED=yes run_session.sh ENV_DIR SESSIONS_ROOT
#
# ENV_DIR is an arm built by build_env.py. The session gets
# SESSIONS_ROOT/<arm>-<n>/work (GUIDE.md and line_count.sh only) as its
# directory; transcript.jsonl, claude.stderr, check.json and session.json are
# written beside work/. n is the first free number from 1 to 3; with three
# sessions of the arm already there, this refuses, so no session is ever
# retried and the arm cannot exceed three sessions (six in all, at most
# USD 2 each). This script spends provider calls: it refuses to start unless
# AUTHORING_CHECK_SPEND_AUTHORIZED is exactly "yes".
set -euo pipefail

MODEL=claude-haiku-5-5   # exact model; no fallback model is passed
CAP_USD=2                # --max-budget-usd, per session
WALL_SEC=1200            # 20-minute wall limit
SESSIONS_PER_ARM=3

if [ "${AUTHORING_CHECK_SPEND_AUTHORIZED:-}" != yes ]; then
  echo "run_session.sh: refused: this starts a paid $MODEL session; set AUTHORING_CHECK_SPEND_AUTHORIZED=yes once the budget is approved" >&2
  exit 3
fi
if [ $# -ne 2 ]; then
  echo "usage: AUTHORING_CHECK_SPEND_AUTHORIZED=yes run_session.sh ENV_DIR SESSIONS_ROOT" >&2
  exit 2
fi

KIT=$(cd "$(dirname "$0")" && pwd -P)
ENV_DIR=$(cd "$1" && pwd -P)
mkdir -p "$2"
ROOT=$(cd "$2" && pwd -P)
COMMON=$(git -C "$KIT" rev-parse --path-format=absolute --git-common-dir)
CHECKOUT=$(dirname "$COMMON")
for dir in "$ENV_DIR" "$ROOT"; do
  case "$dir/" in "$CHECKOUT"/*) echo "run_session.sh: refused: $dir is inside the checkout $CHECKOUT" >&2; exit 3;; esac
done
ARM=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["arm"])' "$ENV_DIR/env.json")
CLAUDE=$(command -v claude) || { echo "run_session.sh: no claude on PATH" >&2; exit 3; }

SESSION=
for n in $(seq 1 "$SESSIONS_PER_ARM"); do
  if mkdir "$ROOT/$ARM-$n" 2>/dev/null; then SESSION="$ROOT/$ARM-$n"; break; fi
done
[ -n "$SESSION" ] || { echo "run_session.sh: refused: $ROOT already holds $SESSIONS_PER_ARM $ARM sessions" >&2; exit 3; }
mkdir "$SESSION/work"
cp "$ENV_DIR/GUIDE.md" "$KIT/line_count.sh" "$SESSION/work/"

# The arm's installed orchestrator first on PATH; no PYTHONPATH; no variable that remaps models.
ARM_ENV=(env -u PYTHONPATH -u ANTHROPIC_MODEL -u ANTHROPIC_SMALL_FAST_MODEL -u ANTHROPIC_DEFAULT_HAIKU_MODEL
         -u ANTHROPIC_DEFAULT_SONNET_MODEL -u ANTHROPIC_DEFAULT_OPUS_MODEL -u CLAUDE_CODE_SUBAGENT_MODEL
         "PATH=$ENV_DIR/venv/bin:$PATH")
# Shell and file tools only; no subagent tool, no MCP server, no skills; user settings, CLAUDE.md and hooks not loaded.
FLAGS=(-p "$(cat "$KIT/task.md")" --model "$MODEL" --max-budget-usd "$CAP_USD"
       --tools Bash,Read,Write,Edit --strict-mcp-config --setting-sources project --disable-slash-commands
       --permission-mode bypassPermissions --no-session-persistence --output-format stream-json --verbose)

STARTED=$(date +%s)
set +e
(cd "$SESSION/work" && "${ARM_ENV[@]}" timeout --kill-after=30 "$WALL_SEC" "$CLAUDE" "${FLAGS[@]}" \
   < /dev/null > "$SESSION/transcript.jsonl" 2> "$SESSION/claude.stderr")
CLAUDE_EXIT=$?
ENDED=$(date +%s)
"${ARM_ENV[@]}" python3 "$KIT/check.py" "$SESSION/work" > "$SESSION/check.json"
CHECK_EXIT=$?
set -e

python3 - "$SESSION/session.json" <<EOF
import json, sys
json.dump({"arm": "$ARM", "env_dir": "$ENV_DIR", "commit": json.load(open("$ENV_DIR/env.json"))["commit"],
           "model": "$MODEL", "cap_usd": $CAP_USD, "wall_limit_sec": $WALL_SEC, "checkout": "$CHECKOUT",
           "started": $STARTED, "ended": $ENDED, "claude_exit": $CLAUDE_EXIT, "check_exit": $CHECK_EXIT},
          open(sys.argv[1], "w"), indent=2, sort_keys=True)
EOF
echo "$SESSION: claude exit $CLAUDE_EXIT, check exit $CHECK_EXIT"
