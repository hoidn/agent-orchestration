# Agent Orchestration

A compiler and runtime for LLM-agent workflows. Workflow Lisp (`.orc`) programs
compose coding-agent calls, shell commands and ordinary computation with declared
input/output contracts. The compiler and runtime manage intermediate files,
validate results and record execution evidence.

A source file's declared target picks one of two kinds of profile. Typed
profiles (through 2.36) check types before execution and support resume. The
native 3.0 profile runs ordinary functions and closures, validates declared
boundaries strictly, and runs fresh only, with no resume. Choose by need; see
[Architecture](#architecture). The default run root is
`.orchestrate/runs/<run_id>/`.

## The Missing Toolchain

When you compile a C program, you do not assign addresses to your variables,
invent a calling convention per function, or parse the bytes a callee leaves
behind. The toolchain does that. It is so transparent that it takes effort to
remember it is happening.

Programming with LLM agents today has no equivalent toolchain, so every
pipeline hand-rolls the same machinery at the level of assembly-era
programming: invent file paths for intermediate state and thread them through
prompts and glue scripts; describe the expected output format in prose inside
each prompt; parse what the model produces with regex or JSON-fishing; decide
"looks done" by inspection; rerun from scratch when something breaks halfway.

This project's thesis is that those are compiler and runtime responsibilities,
and that workflow authoring should use declared contracts against an
unreliable, effectful coprocessor. Typed profiles also check internal values
before execution; native 3.0 checks declared workflow, prompt and command
boundaries. Supported forms and recovery depend on the profile:

| A CPU toolchain gives you | Hand-rolled in agent pipelines today | Owned by the compiler and runtime here |
| --- | --- | --- |
| Storage layout: the compiler assigns addresses, you name variables | Inventing file paths for every intermediate artifact and threading them everywhere | Runtime-owned result/attempt layout; typed flat profiles also allocate managed state bundles, snapshots and write roots; native internal values need no authored result paths |
| Calling conventions: types define the ABI | Output formats described in prose, differently in every prompt | The declared result type is rendered into the prompt as a deterministic output-contract block, and the output location is a managed binding the agent receives — not a path the author invents |
| Type checking | Stringly-typed everything; status fields compared by convention | Typed profiles check records, unions, enums, paths and variant proof before execution; native 3.0 validates declared boundaries and checks internal operations when reached |
| Defined failure semantics | "Looks done" means done; partial junk left on disk | Fail-closed validation: agent output is parsed and verified by the runtime against the declared contract, and nothing becomes canonical state until it passes (validate, write temp, atomic rename) |
| Compiled control flow | Routing by parsing model output | Flat typed profiles lower to guarded steps; evaluated typed profiles execute checked closed programs; native 3.0 evaluates ordinary functions under an operation budget |
| Debugger and symbols | Scrolling transcripts | Source maps, profile-specific run evidence and a REPL for typed 2.35/2.36 or native 3.0 inspection |
| Crash recovery | Rerun and pray | Typed `resume <run_id>` continues from checked authority; native 3.0 refuses recovery and requires a fresh run |

## What That Looks Like

In the typed flat profiles through target 2.34, an implementation phase is a
typed expression over an agent step. This illustrative fragment omits the enclosing
module, path/enum declarations, extern bindings and helper implementations; it is
not a standalone module or a native 3.0 example:

```lisp
(defunion ImplementationAttempt          ; the outcome contract: a tagged union
  (COMPLETED
    (execution-report Path.execution-report))  ; path type: verified to exist
  (BLOCKED                               ; different outcome, different evidence
    (progress-report Path.progress-report)
    (blocker-class BlockerClass)         ; an enum, not free text
    (blocker-reason String)))

(let* ((attempt                          ; attempt : ImplementationAttempt
         (provider-result providers.execute       ; the agent role to invoke
           :prompt prompts.implementation.execute ; compile-time prompt source
           :inputs (inputs.design inputs.plan)    ; the prompt's typed inputs
           :returns ImplementationAttempt)))      ; injected into the prompt as
                                                  ; the output contract, enforced
                                                  ; on the result, fail-closed
  (match attempt
    ((COMPLETED c)             ; proof: c's fields exist only in this arm
      (review-completed-implementation c.execution-report))
    ((BLOCKED b)               ; typed blocker routes onward; nothing parsed
      (escalate-blocker b.blocker-class b.blocker-reason))))
```

Hand-rolled against the same CLI agent, with the same guarantees attempted,
the equivalent step is mostly bookkeeping:

```python
MAX_RETRIES = 3
BLOCKER_CLASSES = {"missing_resource", "unavailable_hardware", ...}
report_dir = "state/impl"                        # storage layout, invented by hand
state_path = f"{report_dir}/attempt.json"

def run_implementation(design_path, plan_path):
    if os.path.exists(state_path):               # hand-rolled resume
        prior = json.load(open(state_path))
        if looks_valid(prior):                   # re-validate: trust nothing
            return prior

    prompt = f"""Implement the plan.
Design: {design_path}
Plan: {plan_path}

When finished, write JSON to {report_dir}/result.json shaped like
  {{"status": "COMPLETED", "execution_report": "<path>"}}
or
  {{"status": "BLOCKED", "blocker_class": "...", "blocker_reason": "..."}}
"""                                              # the contract, restated as prose in every prompt

    for _ in range(MAX_RETRIES):                 # malformed output happens; retry by hand
        subprocess.run(["codex", "exec", prompt], capture_output=True, text=True)
        try:
            result = json.load(open(f"{report_dir}/result.json"))
        except (FileNotFoundError, json.JSONDecodeError):
            continue                             # wrote nothing, or not JSON

        if result.get("status") == "COMPLETED":
            report = result.get("execution_report")
            if not report or not os.path.exists(report):
                continue                         # claimed a report it never wrote
            if not report.startswith("artifacts/work/"):
                continue                         # or wrote it somewhere it shouldn't
        elif result.get("status") == "BLOCKED":
            if result.get("blocker_class") not in BLOCKER_CLASSES:
                continue                         # free text where an enum should be
        else:
            continue                             # unknown status string

        tmp = state_path + ".tmp"                # atomic-ish commit, by hand
        json.dump(result, open(tmp, "w"))
        os.replace(tmp, state_path)
        return result

    raise RuntimeError("implementation failed")  # nothing recorded what or why

# ...and the same again for every step, minus what never gets written:
# step-level resume identity, provenance, effect visibility, and any way
# to map a failure back to the line that caused it.
```

And this is one step, abridged — the stringly-typed routing on
`result["status"]` still happens at every consumer. The `.orc` step carries
no bookkeeping: the enclosing module adds only typed declarations, and the
next step costs one more declaration, not another copy of this.

What the typed declarations buy:

- The `ImplementationAttempt` union becomes the agent's output contract: a
  deterministic contract block is appended to the composed prompt, and the
  structured result is written to a runtime-managed location.
- The returned bundle is validated against the type before anything
  downstream can see it. There is no parsing code to write, and a
  wrong-shape or wrong-path result fails closed instead of flowing onward.
- `match` establishes the variant proof needed to reach `c.execution-report`
  or `b.blocker-class`. Touching a variant field without proof is a compile
  error; the lowered graph keeps a runtime guard. From target 2.26, typed
  discriminant comparisons in conditionals also establish proof.
- The bookkeeping — phase state bundles, snapshots, candidate and result
  paths — never appears in the source. It is allocated, tracked, and kept
  private by the runtime; the agent's human-readable report is a view, not
  the state.
- Generated steps retain source mapping; recovery follows this typed profile's
  validated-state contract. Native 3.0 has a different execution contract and
  does not inherit this fragment's compile-time proofs or resume behavior.

The lower-level flat Core contract contains surfaces such as `variant_output`,
`match` and injected output contracts. They are compiler targets and runtime
semantics for that route, not a second authored frontend.

## Guarantees The System Enforces

- Structured state is semantic authority; reports, logs, pointer files, and
  rendered summaries are views. Nothing routes on parsed prose.
- Validation precedes canonical state. Contracts may narrow downstream,
  never weaken.
- Effects are visible: provider use, command execution, writes, state
  updates, and queue/ledger movement are declared or inferred. Semantics
  hidden inside inline shell or Python glue is a defect to remove; certified
  command adapters are the sanctioned FFI for genuine external tools.
- Pure computation uses in-language operators with shared deterministic
  semantics and defined runtime errors; native 3.0 also admits ordinary internal
  functions and closures. It does not require a helper script for arithmetic.
- Runs are deterministic where the workflow is, sequential by default, and
  record local execution evidence. There is no service dependency.

## Workflow Source And Core Contract

- **Workflow Lisp** (`.orc`) is the only workflow frontend. The declared target
  selects typed flat, typed evaluated or native compilation.
- **Core workflow contract** ([`specs/dsl.md`](specs/dsl.md)) is the normalized
  mapping for the flat typed route. Evaluated typed and native programs have
  their own checked representations. The former YAML/YML frontend is retired.

`run` accepts only a source path whose suffix is `.orc` (case-insensitive);
any other path fails with `.orc required` before run state is created.
`resume` rejects every recorded non-`.orc` source the same way. Reports and
dashboards can still render persisted legacy state without parsing its source.

Use [`docs/capability_status_matrix.md`](docs/capability_status_matrix.md) to
check whether a surface is implemented, partial, designed or legacy before
copying it.

## Architecture

The source target selects the representation and runtime. Each profile admits
its own forms and effects:

| Source target | Compilation and execution | Recovery |
| --- | --- | --- |
| Typed through 2.34 | Typed elaboration, ANF and compile-time procedure specialization/defunctionalization lower to flat Core, Semantic IR and Executable IR; no runtime closures | Checked state and profile-specific resume |
| Typed 2.35/2.36 | A checked closed program runs with lexical values and a memo; 2.36 adds bounded local hooks and capture/signature inference | Checked committed-result replay, resume and suffix invalidation |
| Native 3.0 | Ordinary `define`/`fn`, immutable captures and real imports; strict declared workflow/prompt/command boundary schemas; an entry operation budget | Fresh sequential runs, zero retries, stop-on-error; no resume, invalidation or result reuse |

Choose a typed target when you want types checked before execution and the
ability to resume a run. Choose native 3.0 when you want ordinary internal
functions and closures and can rerun from scratch.

Native 3.0 limits:

- Functions and captures are internal values; they cannot cross an external
  boundary.
- Parallel, child-run, trial, resource, view and host-input effects, and provider
  session, context, phased and live surfaces, are not available.
- An operation error can occur after earlier effects. A corrected fresh run may
  repeat those provider calls, commands and writes.

Identity and compatibility are checked by each profile's program, runtime and
persistence contracts. Flat parametric lowering can retain path-sensitive
identity, so moving source files does not necessarily preserve artifact
identity or keep an existing run resumable. Reports and debug projections are
views, not execution state.

Contracts: [versioning](specs/versioning.md), the
[native profile](specs/versioning.md#native-target-30),
[evaluated execution](docs/design/workflow_lisp_evaluated_execution.md) and
[capability status](docs/capability_status_matrix.md). The
[middle-end design](docs/design/workflow_lisp_core_calculus_middle_end.md)
describes the flat typed route only.

## Start Here

| Goal | Read or run |
| --- | --- |
| Find any doc | [`docs/index.md`](docs/index.md) |
| Learn the execution model | [`docs/orchestration_start_here.md`](docs/orchestration_start_here.md) |
| Choose an example to copy | [Which Example Should I Copy?](workflows/README.md#which-example-should-i-copy) |
| Author Workflow Lisp `.orc` | [`docs/lisp_workflow_drafting_guide.md`](docs/lisp_workflow_drafting_guide.md) |
| Choose APIs for generation/selection, review/revise, evaluation or search | [Library task chooser](docs/lisp_library_reference.md#choose-by-task), with complete examples and setup |
| Use typed 2.36 local hooks | [Local hook contract](docs/design/workflow_lisp_write_once.md#63-language-changes-to-let-proc) and [complete typed examples](docs/lisp_library_reference.md#complete-typed-examples) |
| Author native 3.0 functions and closures | [Native 3.0 dynamic composition](docs/lisp_workflow_drafting_guide.md#2b-native-30-dynamic-composition) and the [complete imported improvement consumer](docs/lisp_workflow_drafting_guide.md#complete-imported-improvement-consumer) |
| Inspect typed 2.35/2.36 or native 3.0 run bindings | [REPL recipes and prerequisites](docs/lisp_workflow_drafting_guide.md#inspect-a-run-with-the-workflow-lisp-repl) |
| Check the normative contracts | [`specs/index.md`](specs/index.md) and [`specs/dsl.md`](specs/dsl.md) |
| Find runnable examples | [`workflows/README.md`](workflows/README.md) |
| Compare Workflow Lisp to YAML | [`docs/workflow_lisp_mvp_comparison.md`](docs/workflow_lisp_mvp_comparison.md) |
| Author or run a target-2.25 trial | [Pinned child runs and trials](docs/lisp_workflow_drafting_guide.md#pinned-child-runs-and-trials); [CLI contract](specs/cli.md#workflow-lisp-trials-target-225) |
| Read plans, reports or the retired YAML references | [History](docs/index.md#history) |

## Install

Requirements:

- Python 3.11+
- `bash`
- a checkout of this repository

Optional for real provider execution:

- the `codex` CLI available in your shell;
- whatever authentication your `codex exec` setup requires.

```bash
git clone <repo-url> agent-orchestration
cd agent-orchestration

python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Sanity check:

```bash
python -m orchestrator --help
```

The installed executable is `orchestrator`; examples use
`python -m orchestrator` so they also work directly from a checkout.

## First Compile Check

From the repository root, compile the `std/improve` review-loop example, then
dry-run it with its checked-in inputs:

```bash
python -m orchestrator compile workflows/examples/improve_experiment_proposal.orc \
  --entry-workflow improve_experiment_proposal::run-experiment \
  --provider-externs-file workflows/examples/inputs/improve_experiment_proposal/providers.json \
  --prompt-externs-file workflows/examples/inputs/improve_experiment_proposal/prompts.json \
  --command-boundaries-file workflows/examples/inputs/improve_experiment_proposal/commands.json

python -m orchestrator run workflows/examples/improve_experiment_proposal.orc \
  --entry-workflow improve_experiment_proposal::run-experiment \
  --provider-externs-file workflows/examples/inputs/improve_experiment_proposal/providers.json \
  --prompt-externs-file workflows/examples/inputs/improve_experiment_proposal/prompts.json \
  --command-boundaries-file workflows/examples/inputs/improve_experiment_proposal/commands.json \
  --input-file workflows/examples/inputs/improve_experiment_proposal/inputs.json \
  --dry-run
```

Both commands exit 0 without calling a provider. The dry-run prints `[LINT]`
warnings about generated write-root inputs; they do not affect the result. A
real run also needs `scripts/launch_experiment.py` in the workspace; the
[drafting guide](docs/lisp_workflow_drafting_guide.md#137-improve) describes
its protocol.

## Run For Real

Run provider workflows only after compile and dry-run succeed and your provider
CLI works in the same shell. Supply the entrypoint's declared typed inputs and
extern files; the [workflow catalog](workflows/README.md) lists what each
example needs.

```bash
python -m orchestrator run \
  <workflow.orc> --entry-workflow <module::entry> \
  --provider-externs-file <providers.json> \
  --prompt-externs-file <prompts.json> \
  --command-boundaries-file <commands.json> \
  --input-file <inputs.json> \
  --stream-output
```

Omit `--command-boundaries-file` when the workflow runs no commands.

To continue a typed run that stopped partway through, use its run ID:

```bash
python -m orchestrator resume <run_id> --stream-output
```

Typed retry and replay follow the run's persisted profile and configured
policy; committed evaluated results are checked and reused. Native 3.0 fixes
retries at zero and refuses resume and invalidation: fix the failure and start
a fresh run, accepting that earlier external work may repeat. See the
[CLI contract](specs/cli.md#dynamic-execution) for profile-specific options.

## Observability

Check the run's persisted profile before interpreting files. Paths are relative
to the run root (by default `.orchestrate/runs/<run_id>/`):

| Profile | State | Prompt and execution logs |
| --- | --- | --- |
| Flat typed through 2.34 | `state.json` and its profile-owned artifacts | `logs/<Step>.prompt.txt`, `logs/<Step>.stdout` / `.stderr` as produced |
| Evaluated typed 2.35/2.36 | Checked `run.json`, `closed_program.json` and `memo.jsonl`; `state.json` is a derived view | Reached attempts under `effects/<effect-hash>/attempt-<n>/`: provider `prompt.txt`, `stdout.txt`, `stderr.txt`, `result.json` |
| Native 3.0 | Immutable `run.json` / `closed_program.json` pins and schema-3.1 `state.json`; no memo | Each state effect row's paths under `effects/<ordinal>/attempt-1/`: provider prompt and stdout/stderr/result files |

The [state contract](specs/state.md) defines state and recovery; logs and
reports are observations. The
[REPL guide](docs/lisp_workflow_drafting_guide.md#inspect-a-run-with-the-workflow-lisp-repl)
has typed 2.35/2.36 and native 3.0 recipes for `:bindings`, `:result` and pure
expressions. With a loaded module, `:browse`, `:info` and `:source` show
declarations and immutable source snapshots. `:type` analyzes typed
expressions without running them; native queries report kinds and refuse
compound expressions. Attached `:where` locates checked typed result files;
native values carry no file provenance. Inspection is read-only; `:run`
executes the workflow, and a native `:run` always starts a fresh run that may
repeat external effects. Limits are in the
[introspection design](docs/design/workflow_lisp_repl_introspection.md).

Generate a readable run report:

```bash
python -m orchestrator report --run-id <run_id> --format md
```

Serve the local read-only dashboard:

```bash
python -m orchestrator dashboard --workspace "$(pwd)"
```

Profiles that support them accept optional step summaries
(`--step-summaries --summary-profile phase-performance`); native 3.0 refuses
these options. Summaries are for reading only and never drive routing or
recovery. For headless email alerts across workspaces, see
[`docs/workflow_monitoring.md`](docs/workflow_monitoring.md).

## What The Repo Contains

| Path | Purpose |
| --- | --- |
| [`orchestrator/`](orchestrator/) | Workflow Lisp frontend/compiler, validator, executor, CLI, dashboard, and observability. |
| [`specs/`](specs/) | Normative DSL, CLI, state, provider, observability, and acceptance contracts. |
| [`docs/`](docs/) | Guides, design docs and runbooks; `docs/plans/` and `docs/reports/` are historical records. |
| [`workflows/examples/`](workflows/examples/) | Runnable examples and validation fixtures. |
| [`workflows/library/`](workflows/library/) | Reusable imported subworkflows and bundled prompt assets. |
| [`prompts/`](prompts/) | Shared prompt catalog. |
| [`tests/`](tests/) | Unit, frontend, runtime, workflow, and fixture tests. |

## Common Commands

```bash
# Resume a typed run (native 3.0 refuses)
python -m orchestrator resume <run_id> --stream-output

# Render the latest run report
python -m orchestrator report --format md

# Serve the dashboard
python -m orchestrator dashboard --workspace "$(pwd)"

# Inspect the target-2.25 terminal trial entry
python -m orchestrator trial --help

# Inspect the typed/native REPL command surface
python -m orchestrator repl --help

# Run the broad non-e2e test loop from a tmux session
pytest -q -n 16 --dist=worksteal -m "not e2e"
```

## Versioning

Targets span `1.x`, typed `2.x` (flat through 2.34, evaluated 2.35/2.36) and
native `3.0`. Capabilities do not transfer between profiles: typed 2.36 local
hooks are compile-time composition, not native runtime closures. Workflow
source is `.orc`. Version details are in [`specs/index.md`](specs/index.md)
and [`specs/versioning.md`](specs/versioning.md).

## Debugging Rule Of Thumb

If agent behavior looks wrong, inspect the composed provider prompt before
changing workflow logic. Use the prompt path for the run's profile from the
observability table above: `logs/<Step>.prompt.txt` on the flat route,
`prompt.txt` in the attempt directory for evaluated and native runs.

If routing or artifact lineage looks wrong, inspect the profile's
[state](specs/state.md) and the workflow's declared input, result and path
contracts before changing prompts. Flat-profile artifact lineage also uses
`outputs`, `publishes`, `consumes`, `expected_outputs` and `output_bundle`;
native 3.0 does not have those surfaces.

## License

This project is licensed under the Functional Source License, Version 1.1,
MIT Future License (`FSL-1.1-MIT`). See [`LICENSE.md`](LICENSE.md).
