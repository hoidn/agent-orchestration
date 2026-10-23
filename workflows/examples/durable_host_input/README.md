# Durable host input: diagnose, verify, approve, recover

This example runs the same typed approval workflow through the Lisp and native
Python frontends. A deterministic local provider diagnoses an input, and a
command checks the typed cause and evidence file, then returns its path as typed
evidence. A typed host approval controls whether the action repairs or
escalates. The displayed evidence comes from the command result; the prompt
also reads a separate runtime policy document.

The provider is an executable local shim named `codex`. It runs the checked-in
`stub_provider.py`, which returns a response derived from the effect identity
and records it in `providers.log`. It makes no network request and needs no
provider credentials. `action.py` is the declared command for verification,
repair and escalation; `providers.json` and `commands.json` are the complete
provider and command manifests used below.

## Run it

Use the repository's Python 3.11+ environment with the package installed
(`python -m pip install -e '.[dev]'` from the repository root). Start this
script from the repository root. It copies the example into a temporary
workspace, so generated runs and logs stay separate from the maintained
sources.

Set `FRONTEND` to `lisp` or `python`. Set `DECISION` to `APPROVED`, `DENIED`,
or `CANCELLED`; the default demonstrates the repair path.

```bash
set -euo pipefail
EXAMPLE_DIR="$PWD/workflows/examples/durable_host_input"
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
DEMO_ROOT="$(mktemp -d)"
FRONTEND="${FRONTEND:-lisp}"
DECISION="${DECISION:-APPROVED}"

cp "$EXAMPLE_DIR/approval.orc" "$EXAMPLE_DIR/approval.py" \
   "$EXAMPLE_DIR/providers.json" "$EXAMPLE_DIR/commands.json" \
   "$EXAMPLE_DIR/stub_provider.py" "$EXAMPLE_DIR/action.py" "$DEMO_ROOT/"
mkdir -p "$DEMO_ROOT/bin" "$DEMO_ROOT/artifacts" "$DEMO_ROOT/docs"
printf 'verified recovery evidence\n' > "$DEMO_ROOT/artifacts/verification.txt"
printf 'Use the verified cause to select a safe recovery.\n' > "$DEMO_ROOT/docs/recovery-policy.md"

cat > "$DEMO_ROOT/bin/codex" <<'PY'
#!/usr/bin/env python3
from runpy import run_path
run_path("stub_provider.py", run_name="__main__")
PY
chmod 700 "$DEMO_ROOT/bin/codex"
export PATH="$DEMO_ROOT/bin:$PATH"
cd "$DEMO_ROOT"

RUNS="$DEMO_ROOT/runs-$FRONTEND"
mkdir -p "$RUNS"
COMMON=(--source-root "$DEMO_ROOT"
  --provider-externs-file "$DEMO_ROOT/providers.json"
  --command-boundaries-file "$DEMO_ROOT/commands.json"
  --input 'problem=damaged artifact'
  --input 'report=artifacts/verification.txt'
  --input 'guide=docs/recovery-policy.md'
  --state-dir "$RUNS" --quiet)
case "$FRONTEND" in
  lisp)
    python -B -m orchestrator run "$DEMO_ROOT/approval.orc" --entry-workflow approval::recover "${COMMON[@]}"
    ;;
  python)
    python -B -m orchestrator py run "$DEMO_ROOT/approval.py" --entry-workflow recover "${COMMON[@]}"
    ;;
  *)
    echo 'FRONTEND must be lisp or python' >&2
    exit 2
    ;;
esac

RUN_ID="$(python -c 'from pathlib import Path; import sys; print(next(Path(sys.argv[1]).iterdir()).name)' "$RUNS")"
python -B -m orchestrator input get "$RUN_ID" --state-dir "$RUNS" > "$DEMO_ROOT/request.json"
REQUEST_ID="$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["request_id"])' "$DEMO_ROOT/request.json")"
python -c 'import json,sys; request=json.load(open(sys.argv[1])); print(request["question"]); print("Shown evidence:", request["show"][0]["path"])' "$DEMO_ROOT/request.json"

case "$DECISION" in
  APPROVED|DENIED)
    python -B -m orchestrator input answer "$RUN_ID" "$REQUEST_ID" \
      --value "\"$DECISION\"" --by operator --state-dir "$RUNS"
    ;;
  CANCELLED)
    python -B -m orchestrator input cancel "$RUN_ID" "$REQUEST_ID" \
      --by operator --state-dir "$RUNS"
    ;;
  *)
    echo 'DECISION must be APPROVED, DENIED, or CANCELLED' >&2
    exit 2
    ;;
esac
python -B -m orchestrator resume "$RUN_ID" --state-dir "$RUNS"
python -B -m orchestrator resume "$RUN_ID" --state-dir "$RUNS"
python -B -m orchestrator report --run-id "$RUN_ID" --runs-root "$RUNS" --format json
printf 'Run evidence retained at %s\n' "$DEMO_ROOT"
```

Only `ANSWERED(APPROVED)` invokes `repair`. `ANSWERED(DENIED)` and
`CANCELLED` invoke the explicit escalation command. The runtime deadline is
one hour in the source; deterministic `EXPIRED` behavior is covered without
waiting by the public integration tests, which use a controlled clock:

```bash
python -m pytest -q tests/test_workflow_host_input_e2e.py
```

The temporary workspace remains after the script exits so you can inspect
`providers.log`, `commands.log`, the request/reply views and the durable run
memo. They show the provider identity and each verification/action invocation;
the request ID, typed answer and settled principal are also in the report.
Remove the printed workspace path when you no longer need its evidence.
