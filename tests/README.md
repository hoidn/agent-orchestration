# End-to-End (E2E) Testing Guide

Purpose: Central place for how to run, scope, and reason about E2E tests in this repo. This document is informative; acceptance criteria remain in `specs/acceptance/index.md`.

## General Testing Practice
- Run commands from the repository root so imports, relative paths, and fixture layout stay stable.
- Treat fresh command output as mandatory evidence. Do not claim a change is verified unless you just ran the relevant check.
- Prefer the narrowest relevant `pytest` selector first. Expand to broader suites only when the changed surface justifies it.
- If you add or rename tests, run `pytest --collect-only` on those modules before claiming coverage exists.
- Do not weaken verification just to get green. If a test or smoke check is wrong, fix the test or the implementation and document the reason.
- Changes that affect workflow execution, provider prompting, artifact contracts, or demo trial mechanics should rerun at least one orchestrator/demo smoke check in addition to unit tests.

## Test Placement
- Default to flat test modules under `tests/`, named `test_<subject>.py`.
- Put end-to-end coverage under `tests/e2e/`.
- Introduce a subdirectory like `tests/<domain>/` only when a test surface is large enough to justify grouped fixtures, helpers, or selectors.
- Do not create new test subtrees preemptively; use them when the flat layout is no longer helping.

## Test Taxonomy
- Unit: Small, isolated modules with fast feedback.
- Integration: Cross-module behavior under the same process; no real providers.
- E2E: Full workflows and provider CLI integration, realistic filesystem effects, queue semantics.

## Pytest Markers
- `@pytest.mark.e2e` — marks end-to-end tests. These are opt-in and may require network and/or secrets.
- `@pytest.mark.requires_secrets` — tests that should be skipped when required environment secrets are absent.

Register markers in `pytest.ini` (already configured in this repo).

## Environment & Secrets
- E2E tests should detect missing secrets and skip gracefully:
  - Prefer `pytest.skip("missing <SECRET_NAME>")` when `os.getenv("SECRET_NAME")` is empty.
  - Do not hardcode secret values in tests or fixtures.
- Network access: CI/local runs without network should skip E2E that require it. Keep default test runs network-free.

## Running E2E Tests
```bash
# From project root, in an activated virtualenv
pytest -v -m e2e

# Run a single E2E test module
pytest -v -m e2e tests/e2e/test_end_to_end_flow.py

# Combine markers: only E2E tests that do not require secrets
pytest -v -m "e2e and not requires_secrets"
```

## Artifact-Contract Prototype Selectors

Use these selectors for the deterministic handoff prototype (`expected_outputs`, contract validation, prompt injection, and example loops):

```bash
pytest tests/test_loader_validation.py -k "expected_outputs or inject_output_contract" -v
pytest tests/test_output_contract.py -v
pytest tests/test_workflow_output_contract_integration.py -v
pytest tests/test_prompt_contract_injection.py -v
pytest tests/test_workflow_examples_v0.py -v
```

Runtime-focused smoke selector:

```bash
pytest tests/test_workflow_examples_v0.py -k runtime -v
```

Prompt-file-backed multi-step E2E selector:

```bash
ORCHESTRATE_E2E=1 pytest -v -m e2e tests/e2e/test_e2e_multistep_prompted_loop.py
```

## Recommended Workflow
1) Local development: default to unit/integration (`pytest -m "not e2e" -v`).
2) Before merging a feature that touches orchestration flow or provider integration, run E2E locally (with required secrets).
3) CI: keep E2E in a separate job or schedule (nightly). Skip when secrets/network are unavailable.

## Workflow And Demo Smoke Checks

Use these when the change touches workflow semantics, prompts, demo provisioning, or trial execution:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/generic_task_plan_execute_review_loop.yaml --dry-run

pytest tests/test_demo_provisioning.py -q
pytest tests/test_demo_linear_classifier_evaluator.py -q
```

If you add or change the trial runner, also run the targeted trial smoke or runner tests for that surface.

## Conventions
- Keep E2E fixtures explicit about filesystem layout (e.g., `inbox/`, `processed/`, `failed/`, `artifacts/`).
- Prefer real provider CLI invocations only when necessary; otherwise, simulate via test doubles that honor `specs/providers.md` contracts.
- Assert observable state via `state.json`, `logs/`, and on-disk artifacts rather than parsing agent prose.

## Examples
- Narrative E2E examples with YAML workflows live in `specs/examples/e2e.md` (informative). Use those flows as references when authoring new E2E tests.
