# Typed Python Workflows

Generate Workflow Lisp from typed Python and run a local command loop.

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
during checking and frozen builds. They are not sandboxed.

## Run The Local Example

1. Obtain this repository, use Python 3.11 or newer, and install its dependencies
   using the [repository setup](../README.md#try-it). Run from the repository
   root. Open [the workflow](../workflows/examples/python_command_loop.py),
   [command manifest](../workflows/examples/python_command_loop.commands.json)
   and [output-bundle tool](../workflows/examples/python_command_loop_tool.py).
   These inputs need no provider account or network.
2. Run this sequence. `limit` controls the iteration budget.

```sh
python -m orchestrator py build workflows/examples/python_command_loop.py --entry-workflow run --command-boundaries-file workflows/examples/python_command_loop.commands.json
python -m orchestrator py check workflows/examples/python_command_loop.py --entry-workflow run --command-boundaries-file workflows/examples/python_command_loop.commands.json
python -m orchestrator py run workflows/examples/python_command_loop.py --entry-workflow run --command-boundaries-file workflows/examples/python_command_loop.commands.json --input limit=3
python -m orchestrator py run workflows/examples/python_command_loop.py --entry-workflow run --command-boundaries-file workflows/examples/python_command_loop.commands.json --input limit=0
python -m orchestrator py check workflows/examples/python_command_loop.py --entry-workflow run --command-boundaries-file workflows/examples/python_command_loop.commands.json --frozen
```

3. Inspect the generated entry at `source_path` in the build/check JSON, and its
   `source_map_path`. The map supplements diagnostics; generated source and the
   checked program retain runtime identity. Retained sources, configuration and
   the map live below `.orchestrate/python/`; the compiled artifact is at
   `artifact_paths.closed_program` below `.orchestrate/build/`. Find each run directory under
   `.orchestrate/runs/`; its `state.json` view shows `bound_inputs`,
   `workflow_outputs` and completed `steps`. With `limit=3`, the integer result
   is 2 after two work commands; with `limit=0`, exhaustion returns 0 without a
   work command. The tool writes its validated integer through the runtime's
   output bundle. The run command itself can be silent.

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

The module's `TARGET` defaults to 2.39; admitted targets are 2.35–2.40.
Procedures infer effects at 2.39 and later. Older targets require explicit effect
descriptors and emit inline lowering; imported definitions keep their own rules.
Supply repeatable `--source-root` paths for additional source libraries, select
an exported entry with `--entry-workflow`, and supply the relevant provider,
prompt, command or imported-bundle manifests. There are no default extern
bindings. The [design](design/python_workflow_frontend.md#public-authoring-surface)
documents the declaration API and concrete `.orc` imports.

## Ask For A Durable Decision

Select explicit `TARGET = "2.40"` in the module; the default stays 2.39.
Use `ask` with a string or fully applied typed prompt and `returns=...` to bind
an ordinary generic `HostReply[A]`. Match its ANSWERED, CANCELLED and EXPIRED
cases; compare an enum answer with supported equality inside lazy `when`
branches using `then` and `else_`. `host_input` is the descriptor for explicit
procedure effect restrictions. A question can use local, decorated or imported
prompts with ordinary Text/Value/Doc fills; provider-only `Prompt.extern`
questions are unsupported.

Follow the complete [Lisp/Python approval example](../workflows/examples/durable_host_input/README.md)
for a local recording provider diagnosis, command verification, typed evidence,
settlement and conditional action. It supplies every manifest and the provider
shim, needs no credentials and makes no network request. The first run exits
successfully while suspended. External answer/cancel records a reply; ordinary
resume continues. Serial loops and imported asking procedures share the Lisp
runtime's request identity and recovery rules. One request is pending at a time;
parallel-worker and child-run asks refuse.

`timeout_sec=None` has no deadline; a reached timeout must be an exact positive
integer. `show` contains typed file paths for frozen presentation evidence.
Runtime Doc bytes remain semantic replay inputs. Explicit evidence override
cannot waive document/producer divergence or unsafe paths. The
[host CLI contract](../specs/cli.md#evaluated-host-input-target-240) owns strict
JSON answers, principal attribution, cancellation and resume-only expiration.

Agent sessions, parallel mapping, macro authoring and Python runtime callbacks
or ProcRef construction are outside this serial frontend. Existing Lisp library
features do not automatically become Python APIs. Local command and compile
checks establish mechanics, not live-provider qualification or editor proof.
