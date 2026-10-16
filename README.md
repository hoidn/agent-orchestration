# Agent Orchestration

A compiler and runtime for LLM-agent workflows. Workflow Lisp (`.orc`) programs
compose coding-agent calls, shell commands and ordinary computation with declared
input/output contracts. The compiler and runtime manage intermediate files,
validate results and record execution evidence. Typed profiles provide checked
recovery; this branch also supports an explicit native 3.0 profile with internal
functions and closures, strict boundary schemas and fresh-only execution.
The default run root is `.orchestrate/runs/<run_id>/`.

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
boundaries. Supported forms and recovery depend on the selected profile:

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
  error; the lowered graph keeps a runtime guard. Target 2.26 also supports
  proof from typed discriminant comparisons in conditionals.
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
  updates, and queue/ledger movement are declared or inferred — semantics
  hidden inside inline shell or Python glue is treated as migration debt,
  with certified command adapters as the sanctioned FFI for genuine
  external tools.
- Pure computation uses in-language operators with shared deterministic
  semantics and defined runtime errors; native 3.0 also admits ordinary internal
  functions and closures. It does not require a helper script for arithmetic.
- Runs are deterministic where the workflow is, sequential by default, and
  record local execution evidence. There is no service dependency.

## Workflow Source And Core Contract

- **Workflow Lisp** (`.orc`) — the only fresh workflow frontend. The declared
  target selects typed flat, typed evaluated or native dynamic compilation.
- **Core workflow contract** (`specs/dsl.md`) — the normalized mapping for the
  flat route. Evaluated typed and native programs have separate checked
  representations. The former authored YAML/YML frontend and its production
  parser are retired.

Fresh `run` accepts only a path whose suffix compares case-insensitively as
`.orc`; every other source path fails with `.orc required` before run state is
created. Reports and dashboards may render persisted legacy state without
parsing its source. Resume rejects every recorded non-`.orc` source with
`.orc required`, regardless of run terminality or force-restart selection.

Use [`docs/capability_status_matrix.md`](docs/capability_status_matrix.md) to
check whether a given surface is implemented, partial, designed, or legacy
before copying it.

## Architecture

Choose the execution profile explicitly; source target selects the representation
and runtime. Availability is bounded by each profile's admitted forms/effects:

| Source target | Compilation and execution | Recovery |
| --- | --- | --- |
| Typed through 2.34 | Typed elaboration, ANF and compile-time procedure specialization/defunctionalization lower to flat Core, Semantic IR and Executable IR; no runtime closures | Legacy checked state and profile-specific resume |
| Typed 2.35/2.36 | Checked closed program executed with lexical values and a memo; 2.36 adds bounded W3 local hooks and capture/signature inference | Checked committed-result replay, ordinary resume and suffix invalidation within the implemented subset |
| Branch-qualified native 3.0 | Ordinary `define`/`fn`, immutable captures and real imports; strict declared workflow/prompt/command boundary schemas; entry operation budget | Fresh sequential runs, zero retries, stop-on-error; no resume, invalidation or result reuse |

Native functions/captures are internal values, not serialized capabilities at
external boundaries. Native parallel/child/trial/resource/host-input and
session/context/phased/live-provider surfaces remain unavailable. An operation
error may occur after earlier effects; a corrected fresh run may repeat those
calls and writes. Target 3.0 remains branch-qualified: it selects neither a new
default nor application adoption.

Identity and compatibility are checked by the selected profile's program,
runtime and persistence contracts. Legacy parametric lowering can retain
path-sensitive identity; do not assume source relocation preserves artifact
identity or makes an existing run resumable. Reports and debug projections do
not replace execution authority.

For the governing contracts, use [versioning](specs/versioning.md),
[evaluated execution](docs/design/workflow_lisp_evaluated_execution.md), the
[native profile](specs/versioning.md#branch-qualified-target-30) and
[capability status](docs/capability_status_matrix.md). The
[middle-end design](docs/design/workflow_lisp_core_calculus_middle_end.md)
describes the typed flat substrate; it is not the architecture of every profile.

## Start Here

| Goal | Read or run |
| --- | --- |
| Understand the repo map | [`docs/index.md`](docs/index.md) |
| Learn the execution model | [`docs/orchestration_start_here.md`](docs/orchestration_start_here.md) |
| Choose a copy-safe Workflow Lisp example | [`Which Example Should I Copy?`](workflows/README.md#which-example-should-i-copy) |
| Author Workflow Lisp `.orc` | [`docs/lisp_workflow_drafting_guide.md`](docs/lisp_workflow_drafting_guide.md) |
| Choose APIs for generation/selection, review/revise, evaluation or search | [Library task chooser](docs/lisp_library_reference.md#choose-by-task), including caller-prepared repositories and complete setup |
| Use typed 2.36 local hooks | [W3 contract](docs/design/workflow_lisp_write_once.md#63-language-changes-to-let-proc) and [complete typed examples](docs/lisp_library_reference.md#complete-typed-examples) |
| Author native 3.0 functions/captures | [Dynamic composition](docs/lisp_workflow_drafting_guide.md#2b-dynamic-composition-on-the-qualified-branch) and [complete native improvement consumer with setup](docs/lisp_workflow_drafting_guide.md#complete-imported-improvement-consumer) |
| Inspect typed 2.35/2.36 or native 3.0 run bindings | [REPL recipes and prerequisites](docs/lisp_workflow_drafting_guide.md#inspect-a-run-with-the-workflow-lisp-repl) |
| Translate or audit historical YAML | [Historical YAML reference](docs/workflow_drafting_guide.md) |
| Check the normative DSL contract | [`specs/index.md`](specs/index.md) and [`specs/dsl.md`](specs/dsl.md) |
| Find runnable examples | [`workflows/README.md`](workflows/README.md) |
| Compare Workflow Lisp to YAML | [`docs/workflow_lisp_mvp_comparison.md`](docs/workflow_lisp_mvp_comparison.md) |
| Author or run a target-2.25 trial | [Pinned child runs and trials](docs/lisp_workflow_drafting_guide.md#pinned-child-runs-and-trials); [CLI contract](specs/cli.md#workflow-lisp-trials-target-225) |

If you are new to the repo, start at the documentation index, choose a profile
and use the library reference or workflow catalog for complete examples. The
compile-only check below uses a targeted review/fix reference; use the catalog for current copy guidance and the compile check
only to validate source.

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

Run the compile-only source check for the targeted review/fix reference:

```bash
python -m orchestrator compile \
  workflows/examples/review_revise_design_docs.orc \
  --provider-externs-file workflows/examples/inputs/review_revise_design_docs/providers.json \
  --prompt-externs-file workflows/examples/inputs/review_revise_design_docs/prompts.json
```

This compile-only command deliberately omits `--entry-workflow` and runs no
provider. It is a source-check reference, not copy-safety or explicit-entry
evidence. Supplying
`--entry-workflow review_revise_design_docs::review-revise-design-docs` to the
run/dry-run route currently fails with `workflow_signature_mismatch`
(`entry_bootstrap_name_gate_denied`). Choose a new starting point from the
[workflow catalog](workflows/README.md#which-example-should-i-copy).

## Run For Real

Only run provider workflows after compile and dry-run checks succeed and your
provider CLI works in the same shell. Supply the selected `.orc` entrypoint's
declared typed inputs and extern files; the
[workflow catalog](workflows/README.md) records runnable and input-required
routes.

```bash
python -m orchestrator run \
  <workflow.orc> --entry-workflow <module::entry> \
  --provider-externs-file <providers.json> \
  --prompt-externs-file <prompts.json> \
  --input-file <inputs.json> \
  --stream-output
```

For a resumable typed run that stops partway through, use its recorded run ID:

```bash
python -m orchestrator resume <run_id> --stream-output
```

Typed retry/replay behavior follows its persisted profile and configured policy;
committed evaluated results are checked and reused. Native 3.0 fixes retries at
zero and refuses resume/invalidation. Correct the failure and launch a fresh run
only when repeating earlier external work is acceptable. See the
[CLI contract](specs/cli.md#dynamic-execution) for profile-specific options.

## Observability

Inspect the run's persisted profile before interpreting files. Paths below are
relative to the selected run root (by default `.orchestrate/runs/<run_id>/`):

| Profile | State authority | Prompt and execution logs |
| --- | --- | --- |
| Flat typed through 2.34 | Legacy `state.json` and its profile-owned artifacts | `logs/<Step>.prompt.txt`, `logs/<Step>.stdout` / `.stderr` as produced |
| Evaluated typed 2.35/2.36 | Checked `run.json`, `closed_program.json` and `memo.jsonl`; `state.json` is a derived view | Reached attempts under `effects/<effect-hash>/attempt-<n>/`: provider `prompt.txt`, `stdout.txt`, `stderr.txt`, `result.json` |
| Native 3.0 | Immutable `run.json` / `closed_program.json` pins and authoritative schema-3.1 `state.json`; no memo | Follow each state effect row's paths under `effects/<ordinal>/attempt-1/`; provider prompt and stdout/stderr/result files |

The [state contract](specs/state.md) owns authority and recovery. Logs and reports
are observations, not replacement state. The
[REPL guide](docs/lisp_workflow_drafting_guide.md#inspect-a-run-with-the-workflow-lisp-repl)
provides typed 2.35/2.36 and native 3.0 recipes for `:bindings`, `:result` and pure
expressions. With a loaded module, `:browse`, `:info` and `:source` expose declarations and
immutable source snapshots; `:type` analyzes typed expressions without execution,
while native queries report kinds and refuse compound expressions. Attached
`:where` locates checked typed performed-result files; native values retain no
file provenance. See the [introspection contract](docs/design/workflow_lisp_repl_introspection.md)
for limits. Inspection is read-only; explicit `:run` executes the workflow in
either profile. Native `:run` always creates a fresh run and may repeat external
effects.

Generate a readable run report:

```bash
python -m orchestrator report --run-id <run_id> --format md
```

Serve the local read-only dashboard:

```bash
python -m orchestrator dashboard --workspace "$(pwd)"
```

On profiles that support them, optional step summaries make long-run review
easier (`--step-summaries --summary-profile phase-performance`); native 3.0
refuses these options. Summary files are
observability artifacts only; they must not drive workflow routing or
recovery decisions. For headless email alerts across workspaces, see
[`docs/workflow_monitoring.md`](docs/workflow_monitoring.md).

## What The Repo Contains

| Path | Purpose |
| --- | --- |
| [`orchestrator/`](orchestrator/) | Workflow Lisp frontend/compiler, validator, executor, CLI, dashboard, and observability. |
| [`specs/`](specs/) | Normative DSL, CLI, state, provider, observability, and acceptance contracts. |
| [`docs/`](docs/) | Informative guides, design docs, runbooks, and implementation plans. |
| [`workflows/examples/`](workflows/examples/) | Runnable examples and validation fixtures. |
| [`workflows/library/`](workflows/library/) | Reusable imported subworkflows and bundled prompt assets. |
| [`prompts/`](prompts/) | Shared prompt catalog. |
| [`tests/`](tests/) | Unit, frontend, runtime, workflow, and fixture tests. |

## Common Commands

```bash
# Resume an existing resumable typed run (native 3.0 refuses)
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

The Core/runtime contract spans older `1.x` and typed `2.x` targets, including
flat and evaluated execution. This branch also admits the distinct, explicitly
selected native `3.0` profile; capabilities do not transfer automatically between
profiles. Typed 2.36 W3 hooks remain compile-time composition, distinct from
native runtime closures. Fresh authored source is `.orc`; authoritative versioning details live in
[`specs/index.md`](specs/index.md) and
[`specs/versioning.md`](specs/versioning.md).

## Debugging Rule Of Thumb

If agent behavior looks wrong, inspect the composed provider prompt before
changing workflow logic. Use the prompt path for the run's profile in the observability table above;
`logs/<Step>.prompt.txt` applies to the flat route, while evaluated/native
providers keep `prompt.txt` in their attempt directory.

If routing or artifact lineage looks wrong, inspect the profile's
[state authority](specs/state.md) and the
workflow's declared input/result and path contracts before changing prompts.
Flat-profile artifact lineage additionally uses `outputs`, `publishes`,
`consumes`, `expected_outputs` and `output_bundle`; those surfaces must not be
assumed available in native 3.0.

## License

This project is licensed under the Functional Source License, Version 1.1,
MIT Future License (`FSL-1.1-MIT`). See [`LICENSE.md`](LICENSE.md).
