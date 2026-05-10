# Inline Glue Policy Documentation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a discoverable inline-glue and certified-command-adapter policy to the workflow language docs.

**Architecture:** Keep the rule in one focused design note, then reference it from the workflow drafting guide, language principles, Lisp frontend spec, legacy adapter doc, and standard-library lowering doc. The policy distinguishes hidden semantic glue from legitimate command execution.

**Tech Stack:** Markdown docs under `docs/`.

---

### Task 1: Add Command Adapter Contract

**Files:**
- Create: `docs/design/workflow_command_adapter_contract.md`

- [x] Document the difference between hidden inline glue, certified command adapters, legacy adapters, runtime-native effects, and ordinary external commands.
- [x] Define certified adapter metadata, validation, testing, source-map, effect, and path-safety requirements.
- [x] Define versioned lint severity, allowlist metadata, migration sequence, provider-output-protocol handling, and runtime-native promotion criteria.

### Task 2: Wire The Policy Into Existing Docs

**Files:**
- Modify: `docs/design/workflow_language_design_principles.md`
- Modify: `docs/workflow_drafting_guide.md`
- Modify: `docs/design/workflow_lisp_frontend_specification.md`
- Modify: `docs/design/workflow_lisp_legacy_adapter.md`
- Modify: `docs/design/workflow_lisp_stdlib_lowering.md`
- Modify: `docs/index.md`

- [x] Add the compact principle: command steps are allowed; hidden workflow semantics in inline command text are migration debt.
- [x] Link the command adapter contract from the docs index and Lisp frontend dependency list.
- [x] Clarify that `resume-or-start` requires canonical reusable-state validation.
- [x] Clarify that provider results should become structured bundles, with reports as views.

### Task 3: Verify Discoverability

**Files:**
- Check touched Markdown files.

- [x] Run `rg` for the new doc path and main policy terms.
- [x] Run a simple local Markdown link check for touched docs.
- [x] Review `git diff --stat` and keep unrelated dirty files out of the patch scope.
