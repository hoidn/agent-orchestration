# Agent Orchestration

Deterministic, sequential workflow orchestration for command and provider-driven agent loops.

This repo defines a YAML DSL, strict runtime contracts, and filesystem-native run state so execution is reproducible and debuggable.

## Quickstart

```bash
cd /home/ollie/Documents/agent-orchestration
conda create -n agent-orch python=3.11 -y
conda activate agent-orch
pip install -e ".[dev]"
python -m orchestrator --help
python -m orchestrator run workflows/examples/prompt_audit_demo.yaml --debug
```

## What It Does

- Runs stepwise workflows (`command` or `provider`) with deterministic control flow.
- Supports retries, timeouts, `goto` routing, and `for_each` loops.
- Enforces typed output contracts (`expected_outputs` and v1.3 `output_bundle`).
- Supports artifact lineage via v1.2+ `artifacts`/`publishes`/`consumes`.
- Stores run state and logs under `.orchestrate/runs/<run_id>/`.

## Version Snapshot

- `1.1`: baseline DSL.
- `1.1.1`: dependency injection (`depends_on.inject`).
- `1.2`: artifact publish/consume dataflow (`artifacts`, `publishes`, `consumes`).
- `1.3`: deterministic JSON bundles (`output_bundle`, `consume_bundle`).

Authoritative versioning details: [specs/versioning.md](specs/versioning.md)

## Start Here

- Global docs index (informative): [docs/index.md](docs/index.md)
- Master spec (normative): [specs/index.md](specs/index.md)
- Acceptance criteria (normative): [specs/acceptance/index.md](specs/acceptance/index.md)
- CLI contract (normative): [specs/cli.md](specs/cli.md)
- Orchestration concept model (informative): [docs/orchestration_start_here.md](docs/orchestration_start_here.md)
- Runtime execution lifecycle (informative): [docs/runtime_execution_lifecycle.md](docs/runtime_execution_lifecycle.md)
- Workflow drafting guide (informative): [docs/workflow_drafting_guide.md](docs/workflow_drafting_guide.md)
- Example workflows: [workflows/examples](workflows/examples)
- Example runbook: [workflows/examples/README_v0_artifact_contract.md](workflows/examples/README_v0_artifact_contract.md)
- Test guide: [tests/README.md](tests/README.md)

## Common Commands

```bash
# Validate workflow and context without executing steps
python -m orchestrator run workflows/examples/backlog_plan_execute_v1_2_dataflow.yaml --dry-run

# Resume a run
python -m orchestrator resume <run_id>

# Generate a human-readable run status report
python -m orchestrator report --run-id <run_id> --format md

# Enable advisory step summaries (async by default)
python -m orchestrator run workflows/examples/observability_runtime_config_demo.yaml --debug --step-summaries

# Deterministic summary mode (blocks each step until summary result/error is written)
python -m orchestrator run workflows/examples/observability_runtime_config_demo.yaml --debug --step-summaries --summary-mode sync

# Unit/integration default loop
pytest -m "not e2e" -v
```

## Runtime Observability

- Observability is runtime-configured (CLI flags), not workflow DSL.
- `--step-summaries` enables advisory per-step summaries.
- `--summary-mode async|sync` controls mode:
  - `async` (default): non-blocking, best-effort.
  - `sync`: deterministic/blocking summary execution.
- Summary artifacts are written under `.orchestrate/runs/<run_id>/summaries/`.
- Summaries are never consumed by `consumes` and never used for control-flow gating.

## Debugging Runs

Primary artifacts for a run:

- `state.json`: step results, artifacts, and errors.
- `logs/<Step>.prompt.txt`: fully composed provider prompt (after injections).
- `logs/<Step>.stdout` / `logs/<Step>.stderr`: command/provider execution traces.

Tip: if agent behavior looks wrong, inspect `logs/<Step>.prompt.txt` first.
