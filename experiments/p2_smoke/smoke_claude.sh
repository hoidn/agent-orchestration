#!/bin/sh
# The `claude` of the P2 live smoke. run_smoke.sh copies it to <slot>/bin/claude, first on the run's PATH, with
# the resolved CLI's path in bin/claude.target and the slot ledger's path in bin/ledger. In order:
#  1. A claude started from inside the smoke (the agent's shell inherits P2SMOKE_IN_RUN) is refused and
#     logged to <slot>/nested-calls.log: the agent cannot start an unmetered session of any model.
#  2. While P2SMOKE_HOLD names a directory (the first `run` only), a call whose cwd is candidate gamma or delta
#     writes held-<pid> there and stops itself before any CLI starts: the exit test's held coders, held
#     before they cost anything. run_smoke.sh kills the run once both are held.
#  3. A launch slot is claimed in the ledger (launch-1 .. launch-7, mkdir, so parallel calls never share one);
#     past the seventh, or when the smoke's spend could pass USD 3 with this call, the call is refused and
#     logged to <slot>/refused-calls.log. The spend is the runtime's own cap figure (`cap_cost`: the larger of
#     the CLI's reported cost and the highest-tier price) of every earlier launch, and USD 0.5 for each launch
#     without complete usage yet, this one included.
#  4. The CLI runs with user-level settings, plugins, hooks, MCP servers, skills and slash commands left
#     out and a per-call ceiling of USD 0.5.
here=$(cd "$(dirname "$0")" && pwd -P)
if [ -n "${P2SMOKE_IN_RUN:-}" ]; then
  echo "$(date -u +%FT%TZ) $*" >> "$here/../nested-calls.log"
  echo "p2smoke: a claude started inside the smoke is refused" >&2
  exit 97
fi
if [ -n "${P2SMOKE_HOLD:-}" ]; then
  case ${PWD##*/} in
    gamma|delta)
      printf '{"pid": %s, "bundle": "%s"}\n' "$$" "${ORCHESTRATOR_OUTPUT_BUNDLE_PATH:-}" > "$P2SMOKE_HOLD/.held-$$"
      mv "$P2SMOKE_HOLD/.held-$$" "$P2SMOKE_HOLD/held-$$"
      kill -STOP $$
      exit 99;;
  esac
fi
ledger=$(cat "$here/ledger")
n=1
while [ $n -le 7 ] && ! mkdir "$ledger/launch-$n" 2>/dev/null; do n=$((n + 1)); done
if [ $n -gt 7 ]; then
  echo "$(date -u +%FT%TZ) count: seven launches used; $*" >> "$here/../refused-calls.log"
  echo "p2smoke: the smoke's seven provider calls are used" >&2
  exit 98
fi
printf '%s\n' "${ORCHESTRATOR_OUTPUT_BUNDLE_PATH:-}" > "$ledger/launch-$n/bundle"
if ! python3 - "$ledger" <<'EOF'
import json, sys
from pathlib import Path
from orchestrator.providers.pricing import cap_cost, load_price_table
table, total = load_price_table(), 0.0
for launch in Path(sys.argv[1]).glob("launch-*"):
    bundle = (launch / "bundle").read_text().strip() if (launch / "bundle").is_file() else ""
    usage = Path(bundle).parent / "usage.json" if bundle else None
    try:
        figure = cap_cost(json.loads(usage.read_text()), table) if usage and usage.is_file() else None
    except ValueError:       # an unreadable usage.json counts at the per-call ceiling, like a missing one
        figure = None
    total += 0.5 if figure is None else figure
sys.exit(f"spend: the smoke's figure would be {total:.4f} USD, above 3" if total > 3 else 0)
EOF
then
  echo "$(date -u +%FT%TZ) spend: launch-$n refused; $*" >> "$here/../refused-calls.log"
  exit 98
fi
P2SMOKE_IN_RUN=1
export P2SMOKE_IN_RUN
exec "$(cat "$here/claude.target")" --setting-sources project --strict-mcp-config --disable-slash-commands \
  --max-budget-usd 0.5 "$@"
