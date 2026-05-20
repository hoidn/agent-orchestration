# Lisp Architecture Review Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic review/fix loop for Lisp frontend implementation-architecture drafts before they can drive plan and implementation phases.

**Architecture:** Keep the existing design-gap architect workflow as a narrow pre-work-item phase. Add `ReviewDesignGapArchitecture` and `ReviseDesignGapArchitecture` inside a `repeat_until` loop, then validate only after approval. Route blocked or invalid architecture outcomes at the top-level drain without calling the plan/implementation work-item stack.

**Tech Stack:** Agent-orchestration DSL v2.14 YAML, provider prompt Markdown, pytest runtime tests with mocked provider execution.

---

### Task 1: Add Design-Architecture Review Prompts

**Files:**
- Create: `workflows/library/prompts/lisp_frontend_design_gap_architect/review_implementation_architecture.md`
- Create: `workflows/library/prompts/lisp_frontend_design_gap_architect/revise_implementation_architecture.md`

- [ ] Add a review prompt that consumes the drafted architecture, work-item context, check commands, full design, MVP design, command-adapter contract, progress ledger, selector bundle, and prior architecture index.
- [ ] Require the reviewer to write an architecture review report and an `APPROVE` or `REVISE` decision.
- [ ] Add a revise prompt that consumes the review report and updates the same architecture, work-item context, check-command, and bundle targets.

### Task 2: Add The Architect Review Loop

**Files:**
- Modify: `workflows/library/lisp_frontend_design_gap_architect.v214.yaml`

- [ ] Extend `PrepareArchitectureTargets` to materialize an architecture review report target and pointer.
- [ ] Expand `DraftDesignGapArchitecture` output contracts to expose all bundle fields needed by later steps.
- [ ] Add `ArchitectureReviewLoop` with review, route, revise, and exhaustion behavior.
- [ ] Validate the architecture only on the approved route.
- [ ] Emit `BLOCKED` with a valid blocked bundle path when review exhausts.

### Task 3: Route Top-Level Drain On Architecture Status

**Files:**
- Modify: `workflows/examples/lisp_frontend_autonomous_drain.yaml`

- [ ] Replace the direct design-gap architect -> work-item handoff with a `match` on `architecture_validation_status`.
- [ ] Run the work-item stack only for `VALID`.
- [ ] Record a blocked design gap and return `BLOCKED` for `BLOCKED` or `INVALID`.

### Task 4: Add Runtime Coverage

**Files:**
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] Add provider fakes for architecture review approval, revision, and architecture revision.
- [ ] Update existing design-gap runtime flows to include architecture review approval.
- [ ] Add a revise-then-approve architecture test.
- [ ] Add an exhaustion test that records the design gap as blocked and does not call plan/implementation.

### Task 5: Verify

**Commands:**
- `python -m pytest --collect-only tests/test_lisp_frontend_autonomous_drain_runtime.py -q`
- `python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q`
- `python -m pytest tests/test_workflow_examples_v0.py::test_lisp_frontend_autonomous_drain_v214_runtime -q` if the selector exists; otherwise run the narrow Lisp frontend workflow selectors reported by collect-only.
