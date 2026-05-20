# Lisp Frontend Path-List Prompt Injection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the Lisp frontend autonomous drain from embedding large design documents in provider prompts while preserving runtime dependency validation and path discoverability.

**Architecture:** Treat this as a runtime authoring-surface correction: large repo-local docs remain `depends_on.required`, but their prompt transport uses path-list injection rather than content injection. The prompts then instruct Codex to read those listed files from the checkout, and a workflow-family regression prevents reintroducing content injection on the Lisp frontend provider steps.

**Tech Stack:** Workflow YAML v2.14, provider prompt assets, Python pytest, `WorkflowLoader`.

---

## Principle

This is a DSL/runtime authoring-surface issue, not only prompt wording. Large
repo-local authority docs should be required by the runtime and listed by path
in the composed prompt. Full content injection should be reserved for small,
task-local files whose contents are meant to be the prompt payload.

## Files

- Modify: `workflows/library/lisp_frontend_design_gap_architect.v214.yaml`
- Modify: `workflows/library/prompts/lisp_frontend_design_gap_architect/draft_implementation_architecture.md`
- Modify: `workflows/library/prompts/lisp_frontend_design_gap_architect/review_implementation_architecture.md`
- Modify: `workflows/library/prompts/lisp_frontend_design_gap_architect/revise_implementation_architecture.md`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

## Tasks

### Task 1: Convert Large-Doc Transport To Path Lists

- [x] Change `DraftDesignGapArchitecture`, `ReviewDesignGapArchitecture`, and
  `ReviseDesignGapArchitecture` from `depends_on.inject.mode: content` to
  `mode: list`.
- [x] Keep the existing `depends_on.required` lists unchanged.
- [x] Update each injection instruction so it says the listed files must be
  read from the checkout.

### Task 2: Align Prompt Wording

- [x] Replace “injected steering/full design/...” wording with “listed
  steering/full design/...” wording.
- [x] Keep output-path and output-bundle instructions unchanged.
- [x] Avoid adding long negative lists or duplicating runtime contract details.

### Task 3: Add Regression Coverage

- [x] Add a helper that recursively visits nested workflow steps.
- [x] Add a test asserting the Lisp frontend workflow family uses no
  `depends_on.inject.mode: content` provider steps.
- [x] Keep the test structural; do not assert literal prompt phrasing.

### Task 4: Verify

- [x] Run:
  `python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "workflows_load or content_inject" -q`
- [x] Run:
  `python -m pytest tests/test_dependency_injection.py -q`
- [x] Run:
  `python -m pytest --collect-only tests/test_lisp_frontend_autonomous_drain_runtime.py -q`
- [x] Run:
  `python -m orchestrator run workflows/examples/lisp_frontend_autonomous_drain.yaml --dry-run --input steering_path=docs/steering.md --input progress_ledger_path=state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`
- [x] Run `git diff --check`.
