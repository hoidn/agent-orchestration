#!/bin/sh
# The `claude` of one PQ-1c cell. run_cell.sh copies it to <cell>/bin/claude, first on the run's PATH, with
# the resolved CLI's path in <cell>/bin/claude.target. Every call it passes on gets user-level settings,
# plugins, hooks, MCP servers, skills and slash commands left out, and a per-call spend ceiling.
# A claude started from inside a cell (the agent's own shell inherits PQ1C_IN_CELL) is refused and logged
# to <cell>/nested-calls.log, so the agent cannot start an unmetered, uncapped session of any model.
here=$(dirname "$0")
if [ -n "${PQ1C_IN_CELL:-}" ]; then
  echo "$(date -u +%FT%TZ) $*" >> "$here/../nested-calls.log"
  echo "pq1c: a claude started inside a cell is refused" >&2
  exit 97
fi
PQ1C_IN_CELL=1
export PQ1C_IN_CELL
exec "$(cat "$here/claude.target")" --setting-sources project --strict-mcp-config --disable-slash-commands \
  --max-budget-usd 0.5 "$@"
