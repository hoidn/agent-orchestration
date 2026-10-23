# Python Workflows With Durable Decisions

Current guide for bounded native Python authoring. Build a typed workflow, stop
for a host decision, settle it and resume through the ordinary evaluated runtime.

The [Python frontend contract](design/workflow_python_frontend.md),
[host-input contract](design/workflow_lisp_durable_host_input.md) and
[normative CLI](../specs/cli.md#python-authoring) own the behavior. The complete
script below is copyable from the repository root with the development package
installed (Python 3.11+, `python -m pip install -e '.[dev]'`). It needs no
credentials, provider CLI or external service. For diagnosis, command verification
and conditional repair with a recording provider stub, use the complete
[Lisp/Python approval example](../workflows/examples/durable_host_input/README.md)
and its supplied manifests/setup.

## What It Is

Python declarations emit ordinary target-2.40 `.orc` and a diagnostic source
map. The existing compiler checks types/effects; the existing evaluator,
append-only memo and host API own execution, settlement and resume. This is a
bounded authoring language, with trusted Python import/tracing at build time.
It does not serialize a Python stack or promise arbitrary Python replay.

| Supported names | Use |
| --- | --- |
| `workflow`, `proc` | Decorators with annotated parameters and explicit result; optional procedure effects infer or restrict |
| `record`, `variant`, `HostReply` | Closed typed values; named variant unions use `A \| B` or `typing.Union`; host reply imports the existing generic union |
| `RelPath` | Direct subclasses with `under=` and optional `must_exist=` |
| `Prompt`, `Text`, `Doc`, `Value`, `PathOf`, `Out` | Typed templates and fills |
| `Provider`, `Command` | Explicit extern names backed by supplied manifests |
| `host_input`, `uses_provider`, `uses_command` | Explicit procedure effect restrictions |
| `ask`, `match`, `when`, `build` | Requests, lazy branches and explicit checked build |

Use standard-library `Enum`; it is not reexported. Supported annotations include
`str`, `int`, `float`, `bool`, `list[T]`, closed records/enums/unions and typed
paths. Every parameter must be annotated and required: no defaults, positional-only
parameters, `*args` or `**kwargs`. Use `returns=` or a return
annotation, with no disagreement between them.

## Run An Approval

1. Save this one shell script at the repository root and run it. Its first
   steps create the complete input source and a unique local run directory.
   Set the named constants to choose answer and attribution; enum answers are
   JSON strings. The example reaches completion in seconds and spends no
   provider calls.

```bash
#!/usr/bin/env bash
set -euo pipefail
ANSWER='"APPROVED"'
PRINCIPAL='alice'
ENTRY='approval'
mkdir -p .orchestrate/python-guide
GUIDE_DIR=$(mktemp -d .orchestrate/python-guide/approval.XXXXXX)
STATE_DIR="$GUIDE_DIR/runs"
cat > "$GUIDE_DIR/approval.py" <<'PY'
from enum import Enum
from orchestrator.py import workflow, record, ask, match

class Approval(Enum):
    APPROVED = "APPROVED"
    DENIED = "DENIED"

@record
class Outcome:
    status: str

@workflow(returns=Outcome)
def approval():
    reply = ask("Approve this operation?", returns=Approval, timeout_sec=3600)
    return match(
        reply,
        ANSWERED=lambda answer: match(
            answer.value,
            APPROVED=lambda _: Outcome(status="approved"),
            DENIED=lambda _: Outcome(status="denied"),
        ),
        CANCELLED=lambda _: Outcome(status="cancelled"),
        EXPIRED=lambda _: Outcome(status="expired"),
    )
PY
python -m orchestrator py check "$GUIDE_DIR/approval.py" --entry-workflow "$ENTRY"
python -m orchestrator py build "$GUIDE_DIR/approval.py" --entry-workflow "$ENTRY"
python -m orchestrator py run "$GUIDE_DIR/approval.py" --entry-workflow "$ENTRY" --state-dir "$STATE_DIR"
RUN_ID=$(python -c 'from pathlib import Path; import sys; print(next(Path(sys.argv[1]).iterdir()).name)' "$STATE_DIR")
python -m orchestrator input get "$RUN_ID" --state-dir "$STATE_DIR" > "$GUIDE_DIR/request.json"
REQUEST_ID=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["request_id"])' "$GUIDE_DIR/request.json")
python -m orchestrator input answer "$RUN_ID" "$REQUEST_ID" --value "$ANSWER" --by "$PRINCIPAL" --state-dir "$STATE_DIR"
python -m orchestrator resume "$RUN_ID" --state-dir "$STATE_DIR"
python -m orchestrator resume "$RUN_ID" --state-dir "$STATE_DIR"
python -m orchestrator report --run-id "$RUN_ID" --runs-root "$STATE_DIR" --format json
```

2. Read the report: the final typed outcome is `approved` (or `denied` with the
   other enum token). The first run exits successfully while suspended;
   settlement records a reply and requires resume. Repeated resume reuses the
   committed outcome. For default `.orchestrate/runs` storage, [monitoring](workflow_monitoring.md)
   can notify once per request without settling it. For cancellation, follow the complete example's alternate path; deadline
   and evidence-change rules are in the [host settlement contract](../specs/cli.md#evaluated-host-input-target-240).

## What Happens

- Decorators retain bodies until explicit build; later-declared helpers work.
  Procedures trace once with symbolic parameters. `build(workflow_object, ...)`
  accepts workspace, source roots and ordinary manifest paths; CLI selects a
  decorated workflow by name, or requires exactly one export when omitted.
- `match` takes exhaustive one-parameter callbacks; `when` takes zero-parameter
  `then`/`otherwise` callbacks. Their branch effects stay lazy at runtime.
  Ordinary undecorated helpers run during tracing; use `proc` for emitted calls.
- Bundles live at `.orchestrate/generated/<entry>/<digest>/<entry>.orc` and
  `source_map.json`. Keep them while runs refer to them. Compiler diagnostics
  can include original Python lines; runtime reports name generated source and
  ordinary effect/request attribution. The map is supplementary evidence.
- Resume rebuilds recorded generated source/manifests without importing the
  author module. `Prompt(file=...)` snapshots UTF-8 templates at build; edits or
  removal cannot change an existing run. Runtime `Doc` contents remain semantic
  replay inputs and changed bytes can refuse resume.

## Boundaries And Additional Inputs

Importing/tracing trusted Python can perform normal file, network and process
operations; symbolic refusals are not a sandbox. Symbolic truth, iteration,
string conversion, formatting, equality, ordering and arithmetic refuse. Express
runtime branches with `match`/`when`; native loops, comprehensions, async,
generators, exception control, generic user records/unions, agents, child runs,
parallel maps and direct IR APIs are outside this subset. No placeholder exports
or standalone Python `run`/`resume` exist.

For provider/command workflows, supply the example's unchanged
`--provider-externs-file`, `--prompt-externs-file` when required and
`--command-boundaries-file`. Extern references supply no default binding/model;
commands include their full argv and declared explicit closure. `Provider`
accepts `model`, `effort`, `timeout_sec` call policy. `Prompt` requires exactly
one text/file source and exactly its declared named fills.

`ask` accepts a string/symbolic string or applied prompt, with `returns`, optional
positive-integer `timeout_sec`, and typed-path `show`. `None` timeout means no
deadline. One serial request is pending per run. [Host settlement](../specs/cli.md#evaluated-host-input-target-240)
requires a principal, accepts optional opaque attestation and explicit evidence
override, and cannot waive semantic document/provenance or path safety checks.
