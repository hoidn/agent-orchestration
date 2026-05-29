# Agent Orchestration

Deterministic workflow orchestration for command steps, provider-driven agent
loops, and reusable design -> plan -> implementation stacks.

This repo is built around three ideas:

- workflows are authored in a strict YAML DSL;
- runtime state, outputs, artifacts, and routing are contract-checked;
- every run leaves filesystem-native evidence under
  `.orchestrate/runs/<run_id>/` so it can be inspected, resumed, and reported.

The project is useful when an agent workflow needs more structure than an ad
hoc shell script: typed inputs and outputs, reusable subworkflows, bounded
review/fix loops, artifact lineage, resumable state, and local observability.

## License

This project is licensed under the Functional Source License, Version 1.1,
MIT Future License (`FSL-1.1-MIT`). See [`LICENSE.md`](LICENSE.md).

## Start Here

| Goal | Read or run |
| --- | --- |
| Understand the repo map | [`docs/index.md`](docs/index.md) |
| Learn the execution model | [`docs/orchestration_start_here.md`](docs/orchestration_start_here.md) |
| Author or revise workflow YAML | [`docs/workflow_drafting_guide.md`](docs/workflow_drafting_guide.md) |
| Check the normative DSL contract | [`specs/index.md`](specs/index.md) and [`specs/dsl.md`](specs/dsl.md) |
| Find runnable examples | [`workflows/README.md`](workflows/README.md) |
| Compare the Lisp MVP to YAML | [`docs/workflow_lisp_mvp_comparison.md`](docs/workflow_lisp_mvp_comparison.md) |

If you are new to the repo, first validate the call-based design -> plan ->
implementation example. It is self-contained and does not execute provider
commands when run with `--dry-run`.

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

Validate the current modular design -> plan -> implementation stack:

```bash
python -m orchestrator run \
  workflows/examples/design_plan_impl_review_stack_v2_call.yaml \
  --dry-run
```

Expected result:

- the workflow loads successfully;
- imported subworkflows validate;
- typed inputs and outputs validate;
- no provider command is executed.

This example exercises the current reusable stack:

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

That run will:

- read the example brief;
- draft and review a design;
- draft and review an execution plan;
- execute implementation work and run the implementation review/fix loop;
- write run state and logs under `.orchestrate/runs/<run_id>/`;
- write workflow artifacts under the paths declared by the workflow.

If the run stops partway through, resume it:

```bash
python -m orchestrator resume <run_id> --stream-output
```

## Observability

The first places to inspect after a run are:

- `.orchestrate/runs/<run_id>/state.json`: step status, artifacts, and errors;
- `.orchestrate/runs/<run_id>/logs/<Step>.prompt.txt`: composed provider
  prompt;
- `.orchestrate/runs/<run_id>/logs/<Step>.stdout` and `.stderr`: command or
  provider execution traces.

Generate a readable run report:

```bash
python -m orchestrator report --run-id <run_id> --format md
```

Serve the local read-only dashboard:

```bash
python -m orchestrator dashboard --workspace "$(pwd)"
```

For long workflows, optional summaries can make run review easier:

```bash
python -m orchestrator run \
  workflows/examples/design_plan_impl_review_stack_v2_call.yaml \
  --stream-output \
  --step-summaries \
  --summary-profile phase-performance
```

Summary files are observability artifacts only. They must not drive workflow
routing or recovery decisions.

For headless email alerts when runs complete, fail, crash, or stall across
multiple workspaces, see [`docs/workflow_monitoring.md`](docs/workflow_monitoring.md).

## What The Repo Contains

| Path | Purpose |
| --- | --- |
| [`orchestrator/`](orchestrator/) | Loader, validator, executor, CLI, dashboard, observability, and experimental Workflow Lisp compiler code. |
| [`specs/`](specs/) | Normative DSL, CLI, state, provider, observability, and acceptance contracts. |
| [`docs/`](docs/) | Informative guides, design notes, runbooks, and implementation plans. |
| [`workflows/examples/`](workflows/examples/) | Runnable examples and validation fixtures. |
| [`workflows/library/`](workflows/library/) | Reusable imported subworkflows and bundled prompt assets. |
| [`prompts/`](prompts/) | Shared prompt catalog. |
| [`tests/`](tests/) | Unit, runtime, loader, workflow, and fixture tests. |

Important entry points:

- [`docs/index.md`](docs/index.md): documentation hub and recommended read
  order;
- [`workflows/README.md`](workflows/README.md): workflow catalog;
- [`prompts/README.md`](prompts/README.md): prompt catalog;
- [`tests/README.md`](tests/README.md): test and smoke-check guidance;
- [`docs/workflow_lisp_mvp_comparison.md`](docs/workflow_lisp_mvp_comparison.md):
  side-by-side Workflow Lisp MVP vs YAML comparison.

## Common Commands

Validate a workflow without executing steps:

```bash
python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.yaml --dry-run
```

Run with live provider output:

```bash
python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.yaml --stream-output
```

Resume an existing run:

```bash
python -m orchestrator resume <run_id> --stream-output
```

Render the latest run report:

```bash
python -m orchestrator report --format md
```

Serve the dashboard:

```bash
python -m orchestrator dashboard --workspace "$(pwd)"
```

Validate an observability-focused example:

```bash
python -m orchestrator run workflows/examples/observability_runtime_config_demo.yaml --debug --step-summaries
```

Run the default non-e2e test loop:

```bash
pytest -m "not e2e" -v
```

## Versioning

The repo contains workflows across multiple DSL versions, including older `1.x`
examples and newer `2.x` structured-control, reusable-call, provider-session,
managed-job, and v2.14 materialization/variant examples.

Authoritative versioning details live in:

- [`specs/index.md`](specs/index.md)
- [`specs/versioning.md`](specs/versioning.md)

## Debugging Rule Of Thumb

If agent behavior looks wrong, inspect the composed provider prompt before
changing workflow logic:

```bash
less .orchestrate/runs/<run_id>/logs/<Step>.prompt.txt
```

If routing or artifact lineage looks wrong, inspect `state.json` and the
workflow's declared `outputs`, `publishes`, `consumes`, `expected_outputs`, and
`output_bundle` contracts before changing prompts.
