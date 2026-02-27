# Agent Orchestration

Deterministic, sequential workflow orchestration for command and provider-driven agent loops.

This repo defines a YAML DSL, strict runtime contracts, and filesystem-native run state so execution is reproducible and debuggable.

## Quickstart

```bash
cd /home/ollie/Documents/agent-orchestration
python -m venv .venv
source .venv/bin/activate
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

- Master spec (normative): [specs/index.md](specs/index.md)
- Acceptance criteria (normative): [specs/acceptance/index.md](specs/acceptance/index.md)
- CLI contract (normative): [specs/cli.md](specs/cli.md)
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

# Unit/integration default loop
pytest -m "not e2e" -v
```

## Debugging Runs

Primary artifacts for a run:

- `state.json`: step results, artifacts, and errors.
- `logs/<Step>.prompt.txt`: fully composed provider prompt (after injections).
- `logs/<Step>.stdout` / `logs/<Step>.stderr`: command/provider execution traces.

Tip: if agent behavior looks wrong, inspect `logs/<Step>.prompt.txt` first.
