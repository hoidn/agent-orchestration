# CLAUDE.md — How to Run Ralph in This Repo

Purpose: Quick, minimal guide for running the Ralph loops and orienting within this repository. Keep this file concise and accurate. Do not put runtime status here.

### 1. Project Setup (First time only)

This project prefers standard Python packaging. Use an editable install when packaging is present; otherwise use the documented fallback.

1.  **Create `pyproject.toml` (optional)**: If missing and you plan to package locally, create it at the project root with this minimal content:
    ```toml
    [project]
    name = "orchestrator"
    version = "0.1.0"

    [tool.setuptools.packages.find]
    where = ["."]
    ```

2.  **Create a Virtual Environment**:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Editable install vs fallback**
    - Editable path (preferred when packaging is ready):
      ```bash
      pip install -e .
      pip install pytest pyyaml  # dev dependencies
      ```
    - Fallback (no packaging yet):
      ```bash
      export PYTHONPATH=$(pwd)
      pytest -m "not e2e" -v
      ```

4.  **Create `pytest.ini` (recommended)**
    Create a root-level `pytest.ini` to register markers and avoid warnings:
    ```ini
    [pytest]
    markers =
        e2e: end-to-end tests that may require network or secrets; skipped by default
        requires_secrets: tests that require secrets; must skip when secrets are absent
    ```

### 2. Testing notes 
#### Tier 1: Unit tests
#### Tier 2: Integration tests
#### Tier 3: End-to-End (E2E) Tests with Real agents
These tests are slow and require network access. They are essential for final validation but should not be overused.

-   **How to Run**: Use the `pytest` marker `-m e2e`.
    ```bash
    pytest -v -m e2e
    ```

### 3. Running Tests (Backpressure)

-   Default Hard Gate (full run without E2E):
    ```bash
    pytest -m "not e2e" -v
    ```
-   E2E (opt‑in):
    ```bash
    pytest -m e2e -v
    ```
-   Markers: register `e2e` in `pytest.ini` (when added) to silence marker warnings.
-   Network/secrets policy: tests marked `@pytest.mark.e2e` must skip when secrets/network are unavailable. No network is assumed for default runs.
-   If you see `0 tests collected`, add a smoke test (e.g., loader schema validation) before proceeding.

Repo map
- Specs (normative): `specs/index.md` (entry), modules in `specs/*.md`
- Acceptance list: `specs/acceptance/index.md`
- Architecture (ADRs): `arch.md`
- Prompts: `prompts/ralph_orchestrator_PROMPT.md`, `prompts/ralph_orchestrator_PLAN_PROMPT.md`
- Planning backlog: `fix_plan.md` (create/maintain)

Working method (succinct)
- Always read the relevant spec module(s) in `specs/` and the acceptance item first.
- Search before changing code: `rg -n "pattern"` across the repo.
- Do exactly one important item per loop; add/update targeted tests/examples for that item.
- Keep `fix_plan.md` up to date (Top‑10 + backlog); record evidence and DoD.
- Emit artifacts and logs as per specs when applicable; do not duplicate runtime info here.

Notes
- Use `arch.md` for implementation guidance when the spec is silent; if there is a conflict, prefer the spec and propose an `arch.md` update.
- This repo tracks the modular spec; implementation code may be in progress or external — tailor test/build steps accordingly.

Git hygiene and ignores
- Ensure `.gitignore` excludes runtime artifacts: `.orchestrate/`, `RUN_ROOT/logs/`, `**/*.tmp`, `**/*.task` (if generated). Don’t commit state or logs.

Don’ts
- Don’t put runtime status or long logs in this file.
- Don’t weaken DSL/spec strictness to make demos pass; align with `specs/`.
- use run_tests.py:sys.path.insert(0, str(project_root)). Instead do a pip -e local install

One‑liner backpressure checklist
- Targeted tests → Full run (not e2e) → Commit with AT‑IDs
