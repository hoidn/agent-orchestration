#!/bin/sh
# The `claude` of the P2 live smoke. run_smoke.sh copies it to <slot>/bin/claude, first on the run's PATH, with
# the CLI's path (P2SMOKE_CLAUDE_BIN, or the rehearsal stand-in) in bin/claude.target and the slot ledger's path
# in bin/ledger. In order:
#  1. A claude started from inside the smoke (the agent's shell inherits P2SMOKE_IN_RUN) is refused and
#     logged to <slot>/nested-calls.log: the agent cannot start an unmetered session of any model.
#  2. While P2SMOKE_HOLD names a directory (the first `run` only), a call whose cwd is candidate gamma or delta
#     writes held-<pid> there and stops itself before any CLI starts: the exit test's held coders, held
#     before they cost anything. run_smoke.sh kills the run once both are held.
#  3. A launch slot is claimed in the ledger (launch-1 .. launch-7, mkdir, so parallel calls never share one);
#     past the seventh the call is refused and logged to <slot>/refused-calls.log.
#  4. At once, before anything else, the launch records its process: pid, start time (field 22 of
#     /proc/<pid>/stat) and session id (the runtime starts each provider in its own session, so this is the
#     call's session and process group), plus its bundle, the binary it will execute and whether that binary
#     is the rehearsal stand-in. run_smoke.sh terminates only a process whose pid, start time and session all
#     match such a record.
#  5. The gate: the call goes on only while <slot>/gate names this invocation's phase (P2SMOKE_PHASE);
#     run_smoke.sh closes the gate before each sweep, so a call that was starting when the run stopped either
#     is caught by the sweep (its record is already written) or stops here (marked `gated`, no call).
#  6. The spend check: the call is refused (marked `refused`) when the smoke's spend could pass USD 3 with it:
#     the runtime's own cap figure (`cap_cost`: the larger of the CLI's reported cost and the highest-tier
#     price) of every earlier launch, and USD 0.5 for each launch without complete usage yet, this one included.
#     Refused and gated launches made no call and are left out of the figure.
#  7. The CLI runs with user-level settings, plugins, hooks, MCP servers, skills and slash commands left
#     out and a per-call ceiling of USD 0.5.
here=$(cd "$(dirname "$0")" && pwd -P)
if [ -n "${P2SMOKE_IN_RUN:-}" ]; then
  echo "$(date -u +%FT%TZ) $*" >> "$here/../nested-calls.log"
  echo "p2smoke: a claude started inside the smoke is refused" >&2
  exit 97
fi
fields=$(sed 's/.*) //' "/proc/$$/stat")          # the fields after "(comm)": state is field 3
starttime=$(printf '%s' "$fields" | cut -d' ' -f20) sid=$(printf '%s' "$fields" | cut -d' ' -f4)
gate_open() { [ "$(cat "$here/../gate" 2>/dev/null)" = "${P2SMOKE_PHASE:-unset}" ]; }
if [ -n "${P2SMOKE_HOLD:-}" ]; then
  case ${PWD##*/} in
    gamma|delta)
      gate_open || exit 96
      printf '{"pid": %s, "start": "%s", "sid": "%s", "bundle": "%s"}\n' "$$" "$starttime" "$sid" \
        "${ORCHESTRATOR_OUTPUT_BUNDLE_PATH:-}" > "$P2SMOKE_HOLD/.held-$$"
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
launch=$ledger/launch-$n
printf '%s %s %s\n' "$$" "$starttime" "$sid" > "$launch/proc.tmp" && mv "$launch/proc.tmp" "$launch/proc"
printf '%s\n' "${ORCHESTRATOR_OUTPUT_BUNDLE_PATH:-}" > "$launch/bundle"
target=$(cat "$here/claude.target")
printf '%s\n' "$target" > "$launch/target"
if grep -qxF '# p2smoke-rehearsal-stand-in: makes no provider call' "$target" 2>/dev/null; then
  echo yes > "$launch/standin"
else
  echo no > "$launch/standin"
fi
# 2b. the gate
if ! gate_open; then
  : > "$launch/gated"
  echo "p2smoke: the run has stopped; this call is not started" >&2
  exit 96
fi
if ! python3 - "$ledger" <<'EOF'
import json, sys
from pathlib import Path
from orchestrator.providers.pricing import cap_cost, load_price_table
table, total = load_price_table(), 0.0
for launch in Path(sys.argv[1]).glob("launch-*"):
    if (launch / "refused").exists() or (launch / "gated").exists():
        continue
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
  : > "$launch/refused"
  exit 98
fi
P2SMOKE_IN_RUN=1
export P2SMOKE_IN_RUN
exec "$target" --setting-sources project --strict-mcp-config --disable-slash-commands \
  --max-budget-usd 0.5 "$@"
