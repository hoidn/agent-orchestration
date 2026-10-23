# Typed Python Workflows

Build inspectable Workflow Lisp from typed Python, then run a local command
loop through the existing evaluated runtime.

Status: informative current-authoring guide. The [Python frontend
design](design/python_workflow_frontend.md) owns generation; [CLI](../specs/cli.md)
and [evaluated execution](design/workflow_lisp_evaluated_execution.md) own execution
and recovery.

## What It Is

Python authoring registers typed declarations and traces symbolic expressions
into ordinary `.orc` files. It adds no interpreter or scheduler. The compiler
checks generated source, and the evaluated runtime owns commands, provider calls,
validated results and memo reuse. Ordinary `run` still requires `.orc`; Python
source enters through `py build`, `py check` or `py run`. YAML remains retired.
Python imports and tracing execute trusted code with your permissions, including
during checking and frozen builds. They are not sandboxed or hermetic.

## Run The Local Example

1. Obtain this repository, use Python 3.11 or newer, and install its dependencies
   using the [repository setup](../README.md#try-it). Run from the repository
   root. Open [the workflow](../workflows/examples/python_command_loop.py),
   [command manifest](../workflows/examples/python_command_loop.commands.json)
   and [output-bundle tool](../workflows/examples/python_command_loop_tool.py).
   These checked-in inputs require no provider account, external dataset or
   network service.
2. Run this complete command sequence. The entry and manifest are explicit;
   the named input `limit` controls the iteration budget.

```sh
python -m orchestrator py build workflows/examples/python_command_loop.py --entry-workflow run --command-boundaries-file workflows/examples/python_command_loop.commands.json
python -m orchestrator py check workflows/examples/python_command_loop.py --entry-workflow run --command-boundaries-file workflows/examples/python_command_loop.commands.json
python -m orchestrator py run workflows/examples/python_command_loop.py --entry-workflow run --command-boundaries-file workflows/examples/python_command_loop.commands.json --input limit=3
python -m orchestrator py run workflows/examples/python_command_loop.py --entry-workflow run --command-boundaries-file workflows/examples/python_command_loop.commands.json --input limit=0
python -m orchestrator py check workflows/examples/python_command_loop.py --entry-workflow run --command-boundaries-file workflows/examples/python_command_loop.commands.json --frozen
```

3. Inspect the generated entry at `source_path` in the build/check JSON, and its
   `source_map_path`. Retained sources and configuration live below
   `.orchestrate/python/`; the compiler artifact lives at
   `.orchestrate/build/<build_key>/closed_program.json`. Use
   `artifact_paths.closed_program` from the build/check JSON to locate it. Find
   each run directory under `.orchestrate/runs/`; its `state.json` view shows `bound_inputs`,
   `workflow_outputs` and completed `steps`. With `limit=3`, the integer result
   is 2 after two work commands; with `limit=0`, exhaustion returns 0 without a
   work command. The tool writes its validated integer through the runtime's
   output bundle. The run command itself can be silent.

## Run Through The Python API

From the repository root, the public API runs the same local example and
returns the ordinary structured runtime result:

```sh
python - <<'PYTHON'
from orchestrator.py import run

result = run(
    "workflows/examples/python_command_loop.py",
    entry_workflow="run",
    command_boundaries_file="workflows/examples/python_command_loop.commands.json",
    inputs={"limit": 3},
)
assert result.exit_code == 0
print(result.run_id)
print(dict(result.workflow_outputs))
PYTHON
```

The runtime workspace is the current working directory, as with ordinary `run`.

## What Happens

- Build imports captured local source in a fresh worker, traces reachable
  definitions, emits source and a Python source map, and invokes ordinary closed
  compilation. Successful build/run updates an entry-specific frozen pin.
- Check validates through the same path without runtime effects or pin updates.
  Frozen mode requires an existing pin and refuses changed captured Python,
  prompt, imported `.orc` or manifest inputs, even if generated source is equal.
  Installed dependencies and hidden environmental IO are not frozen inputs.
- Run delegates the retained source roots, manifests and inputs to ordinary
  execution. Resume uses that saved `.orc` recipe without importing Python;
  use `python -m orchestrator resume RUN_ID`, replacing `RUN_ID` with the run
  directory's name. Existing closure freshness,
  compiler drift and memo rules still apply.

## Author Your Own Workflow

Import declarations from orchestrator.py. Required parameter/return annotations
cover primitives, string-valued enums, records, closed variant unions, paths,
supported lists and optional types. Decorators register workflows, procedures
and pure helpers; source-backed local modules are required. Native Python
conditionals, iteration and coercions cannot consume symbolic runtime values.

Use lazy when branches, exhaustive match arms and bounded loop with explicit
continuation, completion and exhaustion. Branch callbacks are traced at build
time; only the selected generated branch performs runtime effects. The example
shows these controls without provider spend.

The module's `TARGET` defaults to 2.39; admitted targets are 2.35–2.39.
Procedures infer effects at 2.39. Older targets require explicit effect
descriptors and emit inline lowering; imported definitions keep their own rules.
Supply repeatable `--source-root` paths for additional source libraries, select
an exported entry with `--entry-workflow`, and supply the relevant provider,
prompt, command or imported-bundle manifests. There are no default extern
bindings. The [design](design/python_workflow_frontend.md#public-authoring-surface)
documents the declaration API and concrete `.orc` imports.

Agent sessions, parallel mapping, macro authoring and Python runtime callbacks
or ProcRef construction are outside this serial frontend. Existing Lisp library
features do not automatically become Python APIs. Local command and compile
checks establish mechanics, not live-provider qualification or editor proof.
