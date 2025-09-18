# End-to-End (E2E) Testing Guide

Purpose: Central place for how to run, scope, and reason about E2E tests in this repo. This document is informative; acceptance criteria remain in `specs/acceptance/index.md`.

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

## Recommended Workflow
1) Local development: default to unit/integration (`pytest -m "not e2e" -v`).
2) Before merging a feature that touches orchestration flow or provider integration, run E2E locally (with required secrets).
3) CI: keep E2E in a separate job or schedule (nightly). Skip when secrets/network are unavailable.

## Conventions
- Keep E2E fixtures explicit about filesystem layout (e.g., `inbox/`, `processed/`, `failed/`, `artifacts/`).
- Prefer real provider CLI invocations only when necessary; otherwise, simulate via test doubles that honor `specs/providers.md` contracts.
- Assert observable state via `state.json`, `logs/`, and on-disk artifacts rather than parsing agent prose.

## Examples
- Narrative E2E examples with YAML workflows live in `specs/examples/e2e.md` (informative). Use those flows as references when authoring new E2E tests.

