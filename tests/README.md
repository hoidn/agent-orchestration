# End-to-End (E2E) Testing Guide

Purpose: Central place for how to run, scope, and reason about E2E tests in this repo. This document is informative; acceptance criteria remain in `specs/acceptance/index.md`.

## General Testing Practice
- Run commands from the repository root so imports, relative paths, and fixture layout stay stable.
- Treat fresh command output as mandatory evidence. Do not claim a change is verified unless you just ran the relevant check.
- Prefer the narrowest relevant `pytest` selector first. Expand to broader suites only when the changed surface justifies it.
- Run broad, slow, or full suites in tmux with `pytest -q -n 16 --dist=worksteal`, adding the relevant selectors. Install `.[dev]` for the required pytest-xdist plugin.
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
- `@pytest.mark.e2e` — selects end-to-end checks, including deterministic infrastructure checks and live provider cases. The marker itself neither enables nor skips tests.
- `@pytest.mark.requires_secrets` — tests that should be skipped when required environment secrets are absent.

Register markers in `pyproject.toml` under `[tool.pytest.ini_options]`.
There is no global marker exclusion: plain `pytest` collects marked cases.
Provider-free E2E coverage such as the run-ref and trial modules is unmarked and
runs with the ordinary suite, including `-m "not e2e"`.

## Environment & Secrets
- E2E tests should detect missing secrets and skip gracefully:
  - Prefer `pytest.skip("missing <SECRET_NAME>")` when `os.getenv("SECRET_NAME")` is empty.
  - Do not hardcode secret values in tests or fixtures.
- Network access: CI/local runs without network should skip E2E that require it. Keep default test runs network-free.
- Live provider tests under `tests/e2e/` require `ORCHESTRATE_E2E=1` through `tests/e2e/conftest.py::skip_if_no_e2e`; the deterministic presence checks use the same opt-in. Selecting `-m e2e` alone does not enable them.
- Other live suites have their own prerequisites; see the [OMP upgrade runbook](../docs/omp_upgrade_runbook.md) for OMP acceptance checks.

## Running E2E Tests
```bash
# From project root, in an activated virtualenv and a tmux session
ORCHESTRATE_E2E=1 pytest -q -n 16 --dist=worksteal tests/e2e/test_e2e_provider_supervision.py tests/e2e/test_e2e_provider_peer_delivery.py

# Run one live provider module with its CLI and authentication available
ORCHESTRATE_E2E=1 pytest -q -m e2e tests/e2e/test_e2e_codex_provider_session_control.py

# Run deterministic provider-free E2E coverage
pytest -q tests/test_workflow_lisp_native_returns_e2e.py
```

The retained `test_e2e_codex_provider.py` and `test_e2e_claude_provider.py`
modules still construct retired YAML workflows and refer to the removed root
`orchestrate` wrapper. They require migration before they can supply current
acceptance evidence. Selecting every `e2e` marker with live opt-in includes
those legacy cases; use the explicit current selectors above.

## Artifact-Contract Selectors

Use these selectors for deterministic handoff (`expected_outputs`, contract validation, and prompt injection):

```bash
pytest tests/test_loader_validation.py -k "expected_outputs or inject_output_contract" -v
pytest tests/test_output_contract.py -v
pytest tests/test_workflow_output_contract_integration.py -v
pytest tests/test_prompt_contract_injection.py -v
```

Runtime-focused smoke selector:

```bash
pytest -q tests/test_workflow_lisp_native_returns_e2e.py
```

E2E infrastructure selector:

```bash
pytest --collect-only -q tests/e2e/test_e2e_presence.py
```

## Recommended Workflow
1) Local development: start with narrow owner tests. For the broad non-e2e loop, run `pytest -q -n 16 --dist=worksteal -m "not e2e"` in tmux.
2) Before merging a feature that touches orchestration flow or provider integration, run the relevant E2E checks locally, enabling live cases with their required opt-in, CLI, and authentication.
3) CI: keep E2E in a separate job or schedule (nightly). Skip when secrets/network are unavailable.

## Workflow And Demo Smoke Checks

Use these when the change touches workflow semantics, prompts, demo provisioning, or trial execution:

```bash
pytest tests/test_demo_provisioning.py -q
pytest tests/test_demo_linear_classifier_evaluator.py -q
```

The informal YAML-only trial runner was retired in Stage 6 Task 7. For changes
to retained demo workspace staging, run the provisioning coverage:

```bash
pytest tests/test_demo_provisioning.py tests/test_demo_nanobragg_provisioning.py -q
```

## Conventions
- Keep E2E fixtures explicit about filesystem layout (e.g., `inbox/`, `processed/`, `failed/`, `artifacts/`).
- Prefer real provider CLI invocations only when necessary; otherwise, simulate via test doubles that honor `specs/providers.md` contracts.
- Assert observable state via `state.json`, `logs/`, and on-disk artifacts rather than parsing agent prose.

## Examples
- Current workflow E2E examples use the same `.orc`-only
  frontend contract as production. Start new workflow fixtures from the
  [Workflow Lisp drafting guide](../docs/lisp_workflow_drafting_guide.md) and
  registry-approved `.orc` examples rather than historical YAML flows.
