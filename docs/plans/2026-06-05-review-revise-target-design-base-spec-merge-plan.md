# Review/Revise Target Design Base Spec Merge Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Audit the implemented portions of `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md` section by section and merge accepted/current behavior into `docs/design/workflow_lisp_frontend_specification.md`.

**Architecture:** Treat the frontend specification as the baseline contract and the review/revise integration design as a target-delta source. Merge only implemented or accepted-current behavior into the base spec; leave future prerequisites, optional extensions, and migration history in the target design with explicit status notes. Avoid duplicating long plan text in the base spec.

**Tech Stack:** Markdown design docs, repo-local run evidence, `rg`, focused markdown/search verification.

---

## File Map

- Modify: `docs/design/workflow_lisp_frontend_specification.md`
  - Merge implemented review/revise stdlib contracts, generic substrate, loop exhaustion, structural constraints, effects/source-map/evidence rules, diagnostics, fixtures, and staging updates.
- Modify: `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - Add or update implementation-state notes so the document is clearly a historical/target-delta companion where portions have been promoted to the base spec.
- Possibly modify: `docs/index.md`
  - Only if discoverability currently implies the target design is the sole owner after the base spec gains the implemented contract.

## Tasks

### Task 1: Section Audit

- [ ] Map target design sections 1-10 to base-spec sections and identify implemented portions.
- [ ] Map target design sections 11-23 to base-spec sections and identify implemented portions.
- [ ] Map target design sections 24-30 to base-spec sections and identify implemented portions.
- [ ] Record remaining future-only or optional material that must stay in the target design.

### Task 2: Merge Implemented Contract Into Base Spec

- [ ] Update base-spec prerequisite/boundary sections with implemented preflight and generic-substrate state.
- [ ] Update type, defproc, ProcRef, loop, stdlib, and lowering sections with current parametric/review-loop behavior.
- [ ] Update validation, diagnostics, source-map, testing, and staging sections with implemented acceptance surfaces.
- [ ] Keep base-spec prose concise and normative; avoid embedding execution-plan detail.

### Task 3: Mark Target Design State

- [ ] Add a current implementation-state section or update existing state language in the target design.
- [ ] Clarify which portions have been promoted into the base spec.
- [ ] Keep open questions and optional extensions as future design material.

### Task 4: Verify

- [ ] Run `rg` checks for stale claims that the target design is the only schema owner.
- [ ] Run markdown heading/search checks for the new base-spec sections.
- [ ] Run `git diff --check`.
- [ ] Summarize changed files and remaining unmerged future material.
