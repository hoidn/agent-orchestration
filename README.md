# Agent Orchestration

A compiler and runtime for LLM-agent workflows: typed workflow programs in
which coding agents and shell commands are effectful steps, and the toolchain
— not the author — owns intermediate storage, input/output contracts, output
verification, routing proof, resume, and provenance. Every run leaves
filesystem-native evidence under `.orchestrate/runs/<run_id>/`.

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
and that workflow authoring should look like typed programming against an
unreliable, effectful coprocessor:

| A CPU toolchain gives you | Hand-rolled in agent pipelines today | Owned by the toolchain here |
| --- | --- | --- |
| Storage layout: the compiler assigns addresses, you name variables | Inventing file paths for every intermediate artifact and threading them everywhere | Generated state layout: state bundles, snapshots, result bundles, and write roots are allocated by the runtime (`StateLayout`/`PathAllocator`), private by default, provenance-tracked; authored code references typed values |
| Calling conventions: types define the ABI | Output formats described in prose, differently in every prompt | The declared result type is rendered into the prompt as a deterministic output-contract block, and the output location is a managed binding the agent receives — not a path the author invents |
| Type checking | Stringly-typed everything; status fields compared by convention | Records, tagged unions, enums, and path contracts checked before execution; outcome-dependent fields are unreachable without `match` proof, at compile time and behind runtime guards |
| Defined failure semantics | "Looks done" means done; partial junk left on disk | Fail-closed validation: agent output is parsed and verified by the runtime against the declared contract, and nothing becomes canonical state until it passes (validate, write temp, atomic rename) |
| Compiled control flow | Routing by parsing model output | Branches and bounded loops over typed outcomes compile to a guarded, resumable step graph |
| Debugger and symbols | Scrolling transcripts | Source maps from every runtime step back to the authored form, plus inspectable run state, composed prompts, and logs on the filesystem |
| Crash recovery | Rerun and pray | `resume <run_id>` continues from validated state |

## What That Looks Like

In Workflow Lisp (`.orc`), the typed frontend, an implementation phase is a
typed expression over an agent step:

```lisp
(defunion ImplementationAttempt
  (COMPLETED
    (execution-report Path.execution-report))
  (BLOCKED
    (progress-report Path.progress-report)
    (blocker-class BlockerClass)
    (blocker-reason String)))

(let* ((attempt
         (provider-result providers.execute
           :prompt prompts.implementation.execute
           :inputs (inputs.design inputs.plan)
           :returns ImplementationAttempt)))
  (match attempt
    ((COMPLETED c)
      (review-completed-implementation :report c.execution-report))
    ((BLOCKED b)
      b)))
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
`result["status"]` still happens at every consumer. The `.orc` version is
complete as written; the next step costs another typed declaration, not
another copy of this.

What the typed declarations buy:

- The `ImplementationAttempt` union becomes the agent's output contract: a
  deterministic contract block is appended to the composed prompt, and the
  structured result is written to a runtime-managed location.
- The returned bundle is validated against the type before anything
  downstream can see it. There is no parsing code to write, and a
  wrong-shape or wrong-path result fails closed instead of flowing onward.
- `match` is the only way to reach `c.execution-report` or
  `b.blocker-class`. Touching a variant field without proof is a compile
  error; the lowered graph keeps a runtime guard.
- The bookkeeping — phase state bundles, snapshots, candidate and result
  paths — never appears in the source. It is allocated, tracked, and kept
  private by the runtime; the agent's human-readable report is a view, not
  the state.
- Every generated step maps back to this source form, and the whole run is
  resumable from its last validated state.

The same contracts exist on the mature YAML surface (`variant_output`,
`match`, injected output contracts); the Lisp frontend is the typed,
composable way to author them.

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
- Pure computation (comparison, counting, defaults, message construction)
  is a closed, total, deterministic in-language operator surface — not a
  helper script.
- Runs are deterministic where the workflow is, sequential by default, and
  leave complete local evidence. There is no service dependency.

## Two Authoring Surfaces

- **YAML DSL** (`specs/dsl.md`) — the mature, normative surface. Workflows
  across versions 1.x–2.14 run in production today; `specs/` is the
  authority when documents disagree.
- **Workflow Lisp** (`.orc`) — the typed frontend. It compiles through a
  real middle-end (typed elaboration, ANF normalization,
  defunctionalization) into the same validated runtime. Migration is
  evidence-gated: a YAML workflow stays authoritative until its `.orc`
  replacement passes computed parity gates, never because the `.orc`
  version merely compiles.

Use [`docs/capability_status_matrix.md`](docs/capability_status_matrix.md) to
check whether a given surface is implemented, partial, designed, or legacy
before copying it.

## Architecture

Both frontends lower into one validated substrate:

```text
.orc source                                    YAML workflow
  -> frontend AST                                   |
  -> macro/import expansion,                        |
     compile-time procedure specialization          |
  -> typecheck                                      |
  -> core-calculus elaboration (ANF)                |
  -> scope/effect/proof analysis                    |
  -> defunctionalization                            |
          \                                         |
           +--> flat Core workflow AST <------------+
                  -> shared validation
                  -> Semantic IR (semantic authority)
                     + Executable IR (executable authority)
                  -> flat, resumable runtime
```

The choices that carry the design:

- **The target is deliberately flat.** The runtime is a durable step
  machine: every effect is an addressable, individually resumable step,
  validated before its results become canonical. The compiler's job is the
  same transformation family that gives `async/await` its state machines —
  nested, typed control flow in; flat, durable steps out. Concentrating
  the cleverness at compile time means it can be checked there, including
  by dual-compiling against the legacy lowering and diffing.
- **The middle end is a small core calculus in ANF** — roughly ten
  constructs (atoms, `let`, effect performs, variant inject/case, join
  points, bounded recursion, calls, halt), with an elaboration-totality
  contract on the migrated subset: programs that typecheck lower, so there
  is no "well-typed but dies after lowering" class of failure.
- **ANF rather than SSA or CPS** because it makes the runtime's
  obligations syntactic: the `let` spine totally orders effects, which is
  exactly what a durable step list needs; join points map one-to-one onto
  steps and routing, so there is no out-of-SSA reconstruction; dominance
  is lexical nesting; and continuations are second-class by scoping, so
  there are no runtime closures and defunctionalization is total.
- **Identity is semantic and versioned.** Step and generated-path identity
  derive from semantic ownership — module, role, call frame, loop scope —
  plus a lowering schema version, never from source spans. Resume fails
  closed across schema boundaries instead of replaying into a graph with
  different meaning.
- **Two IR authority lanes.** Semantic IR records what a workflow means
  (types, effects, provenance — what review and migration parity consume);
  Executable IR is what runs. Generated debug YAML is a projection, never
  authority.
- **Pure computation has one semantics.** The runtime evaluator owns the
  closed operator surface; compile-time constant folding must agree with
  it (shared golden vectors). Maximal pure regions fold into single
  visible projection steps with private managed results.

Deeper reading:
[`docs/design/workflow_lisp_core_calculus_middle_end.md`](docs/design/workflow_lisp_core_calculus_middle_end.md)
(calculus and middle-end),
[`docs/design/workflow_lisp_runtime_migration_foundation.md`](docs/design/workflow_lisp_runtime_migration_foundation.md)
(structured output, private value transport, path allocation),
[`docs/design/workflow_lisp_frontend_specification.md`](docs/design/workflow_lisp_frontend_specification.md)
(language baseline).

## Start Here

| Goal | Read or run |
| --- | --- |
| Understand the repo map | [`docs/index.md`](docs/index.md) |
| Learn the execution model | [`docs/orchestration_start_here.md`](docs/orchestration_start_here.md) |
| Author or revise workflow YAML | [`docs/workflow_drafting_guide.md`](docs/workflow_drafting_guide.md) |
| Author Workflow Lisp `.orc` | [`docs/lisp_workflow_drafting_guide.md`](docs/lisp_workflow_drafting_guide.md) |
| Check the normative DSL contract | [`specs/index.md`](specs/index.md) and [`specs/dsl.md`](specs/dsl.md) |
| Find runnable examples | [`workflows/README.md`](workflows/README.md) |
| Compare Workflow Lisp to YAML | [`docs/workflow_lisp_mvp_comparison.md`](docs/workflow_lisp_mvp_comparison.md) |

If you are new to the repo, first validate the call-based design -> plan ->
implementation example below. It is self-contained and does not execute
provider commands when run with `--dry-run`.

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

The CLI program name is `orchestrate`, but the examples use
`python -m orchestrator` so they work directly from a checkout.

## First Dry Run

Validate the modular design -> plan -> implementation stack:

```bash
python -m orchestrator run \
  workflows/examples/design_plan_impl_review_stack_v2_call.yaml \
  --dry-run
```

Expected result: the workflow loads, imported subworkflows validate, typed
inputs and outputs validate, and no provider command executes.

The example exercises the reusable stack:

- top-level workflow:
  [`workflows/examples/design_plan_impl_review_stack_v2_call.yaml`](workflows/examples/design_plan_impl_review_stack_v2_call.yaml)
- design phase:
  [`workflows/library/tracked_design_phase.yaml`](workflows/library/tracked_design_phase.yaml)
- plan phase:
  [`workflows/library/tracked_plan_phase.yaml`](workflows/library/tracked_plan_phase.yaml)
- implementation phase:
  [`workflows/library/design_plan_impl_implementation_phase.yaml`](workflows/library/design_plan_impl_implementation_phase.yaml)
- input brief:
  [`workflows/examples/inputs/provider_session_resume_brief.md`](workflows/examples/inputs/provider_session_resume_brief.md)

## Run For Real

Only run provider workflows after `--dry-run` succeeds and your provider CLI
works in the same shell.

```bash
python -m orchestrator run \
  workflows/examples/design_plan_impl_review_stack_v2_call.yaml \
  --stream-output
```

That run reads the example brief, drafts and reviews a design, drafts and
reviews an execution plan, executes implementation work with a bounded
review/fix loop, and writes run state, logs, and declared artifacts.

If the run stops partway through, resume it:

```bash
python -m orchestrator resume <run_id> --stream-output
```

## Observability

The first places to inspect after a run:

- `.orchestrate/runs/<run_id>/state.json` — step status, artifacts, errors;
- `.orchestrate/runs/<run_id>/logs/<Step>.prompt.txt` — the composed
  provider prompt, including the injected output-contract block;
- `.orchestrate/runs/<run_id>/logs/<Step>.stdout` / `.stderr` — execution
  traces.

Generate a readable run report:

```bash
python -m orchestrator report --run-id <run_id> --format md
```

Serve the local read-only dashboard:

```bash
python -m orchestrator dashboard --workspace "$(pwd)"
```

For long workflows, optional step summaries make run review easier
(`--step-summaries --summary-profile phase-performance`). Summary files are
observability artifacts only; they must not drive workflow routing or
recovery decisions. For headless email alerts across workspaces, see
[`docs/workflow_monitoring.md`](docs/workflow_monitoring.md).

## What The Repo Contains

| Path | Purpose |
| --- | --- |
| [`orchestrator/`](orchestrator/) | Loader, validator, executor, CLI, dashboard, observability, and the Workflow Lisp compiler. |
| [`specs/`](specs/) | Normative DSL, CLI, state, provider, observability, and acceptance contracts. |
| [`docs/`](docs/) | Informative guides, design docs, runbooks, and implementation plans. |
| [`workflows/examples/`](workflows/examples/) | Runnable examples and validation fixtures. |
| [`workflows/library/`](workflows/library/) | Reusable imported subworkflows and bundled prompt assets. |
| [`prompts/`](prompts/) | Shared prompt catalog. |
| [`tests/`](tests/) | Unit, runtime, loader, workflow, and fixture tests. |

## Common Commands

```bash
# Resume an existing run
python -m orchestrator resume <run_id> --stream-output

# Render the latest run report
python -m orchestrator report --format md

# Serve the dashboard
python -m orchestrator dashboard --workspace "$(pwd)"

# Validate an observability-focused example
python -m orchestrator run workflows/examples/observability_runtime_config_demo.yaml --debug --step-summaries

# Run the default non-e2e test loop
pytest -m "not e2e" -v
```

## Versioning

The repo contains workflows across multiple DSL versions, including older
`1.x` examples and newer `2.x` structured-control, reusable-call,
provider-session, managed-job, and v2.14 materialization/variant examples.
Authoritative versioning details live in [`specs/index.md`](specs/index.md)
and [`specs/versioning.md`](specs/versioning.md).

## Debugging Rule Of Thumb

If agent behavior looks wrong, inspect the composed provider prompt before
changing workflow logic:

```bash
less .orchestrate/runs/<run_id>/logs/<Step>.prompt.txt
```

If routing or artifact lineage looks wrong, inspect `state.json` and the
workflow's declared `outputs`, `publishes`, `consumes`, `expected_outputs`,
and `output_bundle` contracts before changing prompts.

## License

This project is licensed under the Functional Source License, Version 1.1,
MIT Future License (`FSL-1.1-MIT`). See [`LICENSE.md`](LICENSE.md).
