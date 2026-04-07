# Agent Orchestration

Deterministic, sequential workflow orchestration for command steps and provider-driven agent loops.

This repo defines:

- a YAML DSL for workflows
- strict runtime contracts for control flow, outputs, and artifact lineage
- filesystem-native run state under `.orchestrate/runs/<run_id>/` so runs are reproducible and debuggable

If you are new to the repo, start by validating a real design -> plan -> implement workflow. The first path below is self-contained and does not require provider credentials.

## Prerequisites

- Python 3.11+
- `bash`
- a checkout of this repository

Optional for real provider execution:

- the `codex` CLI available in your shell
- whatever auth/configuration your `codex exec` setup requires

## Install

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

## First Successful Run

Validate the full call-based design -> plan -> implement stack:

```bash
python -m orchestrator run \
  workflows/examples/design_plan_impl_review_stack_v2_call.yaml \
  --dry-run
```

Expected result:

- the workflow loads successfully
- imported subworkflows validate
- typed inputs/outputs validate
- no provider command is executed yet

This example is the best first read because it exercises the current modular stack:

- top-level workflow: [`workflows/examples/design_plan_impl_review_stack_v2_call.yaml`](workflows/examples/design_plan_impl_review_stack_v2_call.yaml)
- design phase: [`workflows/library/tracked_design_phase.yaml`](workflows/library/tracked_design_phase.yaml)
- plan phase: [`workflows/library/tracked_plan_phase.yaml`](workflows/library/tracked_plan_phase.yaml)
- implementation phase: [`workflows/library/design_plan_impl_implementation_phase.yaml`](workflows/library/design_plan_impl_implementation_phase.yaml)
- input brief: [`workflows/examples/inputs/provider_session_resume_brief.md`](workflows/examples/inputs/provider_session_resume_brief.md)

## Run The Same Workflow For Real

Only do this after `--dry-run` succeeds and `codex exec` works in your shell.

This uses the workflow's default output paths, so it will write example design, plan, and review artifacts into `docs/plans/`, `artifacts/review/`, and `artifacts/work/`.

```bash
python -m orchestrator run \
  workflows/examples/design_plan_impl_review_stack_v2_call.yaml \
  --stream-output
```

That run will:

- read the brief from `workflows/examples/inputs/provider_session_resume_brief.md`
- draft and review a design
- draft and review an execution plan
- execute implementation work and run the implementation review/fix loop
- write run state and logs under `.orchestrate/runs/<run_id>/`

After a run, generate a readable report:

```bash
python -m orchestrator report --format md
```

If a run stops partway through, resume it:

```bash
python -m orchestrator resume <run_id>
```

## What The Repo Contains

- [`docs/index.md`](docs/index.md): documentation hub and recommended read order
- [`specs/index.md`](specs/index.md): normative contract for the DSL, CLI, state, and acceptance scope
- [`workflows/README.md`](workflows/README.md): catalog of example and reusable workflows
- [`prompts/README.md`](prompts/README.md): curated prompt index
- [`tests/README.md`](tests/README.md): testing and smoke-check guidance

## Common Commands

Validate any workflow without executing steps:

```bash
python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.yaml --dry-run
```

Validate another example that demonstrates runtime observability flags:

```bash
python -m orchestrator run workflows/examples/observability_runtime_config_demo.yaml --debug --step-summaries
```

Run the default unit/integration test loop:

```bash
pytest -m "not e2e" -v
```

## Versioning

This repo contains workflows across multiple DSL versions, including older `1.x` examples and newer `2.x` structured-control and call-based examples.

Authoritative versioning details live in:

- [`specs/index.md`](specs/index.md)
- [`specs/versioning.md`](specs/versioning.md)

## Debugging Runs

The first places to inspect for a failed or confusing run are:

- `state.json`: step results, artifacts, and error context
- `logs/<Step>.prompt.txt`: the fully composed provider prompt
- `logs/<Step>.stdout` and `logs/<Step>.stderr`: command or provider execution traces

If agent behavior looks wrong, inspect `logs/<Step>.prompt.txt` before changing workflow logic.
