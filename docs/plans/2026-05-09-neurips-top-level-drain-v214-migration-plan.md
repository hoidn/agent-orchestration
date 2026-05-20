# NeurIPS Top-Level Drain v2.14 Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the actual top-level NeurIPS backlog drain workflow to public DSL `2.14`.

**Architecture:** Keep `workflows/examples/neurips_steered_backlog_drain.yaml` as the canonical top-level drain path, but change it to `version: "2.14"` and make every imported callee same-version. Preserve a legacy copy only for equivalence tests. Convert selector and gap-drafter library workflows as conservative v2.14 compatibility copies, while the selected-item branch uses the existing v2.14 substack.

**Tech Stack:** YAML workflow DSL, Python pytest fixtures, existing NeurIPS fake-provider workflow tests, orchestrator dry-run validation.

---

## Task 1: Preserve A Legacy Top-Level Fixture Surface

**Files:**
- Create: `workflows/examples/neurips_steered_backlog_drain.legacy.yaml`
- Modify: `tests/golden_state.py`

- [ ] Copy the current top-level `neurips_steered_backlog_drain.yaml` to `.legacy.yaml`.
- [ ] Update NeurIPS equivalence helpers so the `legacy` stack uses `.legacy.yaml`.
- [ ] Keep `.legacy.yaml` out of normal authoring docs except as a test baseline.

## Task 2: Add Same-Version v2.14 Selector And Gap-Drafter Callees

**Files:**
- Create: `workflows/library/neurips_backlog_selector.v214.yaml`
- Create: `workflows/library/neurips_backlog_gap_drafter.v214.yaml`
- Modify: `tests/golden_state.py`
- Modify: `tests/test_neurips_steered_backlog_runtime.py`

- [ ] Create conservative v2.14 copies of selector and gap-drafter.
- [ ] Change only `version` and workflow `name` unless a validation failure requires a narrow syntax update.
- [ ] Add the new library files to fixture-copy helpers.

## Task 3: Migrate The Canonical Top-Level Drain

**Files:**
- Modify: `workflows/examples/neurips_steered_backlog_drain.yaml`

- [ ] Set `version: "2.14"`.
- [ ] Rename the workflow to `neurips-steered-backlog-drain-v214`.
- [ ] Import `neurips_backlog_selector.v214.yaml`, `neurips_selected_backlog_item.v214.yaml`, and `neurips_backlog_gap_drafter.v214.yaml`.
- [ ] Leave deterministic top-level logic otherwise unchanged for this migration.

## Task 4: Validate And Document

**Files:**
- Modify: `workflows/README.md`
- Modify: tests as needed.

- [ ] Update workflow docs so the canonical top-level drain is described as v2.14.
- [ ] Run `pytest --collect-only` for touched test modules.
- [ ] Run the NeurIPS equivalence oracle.
- [ ] Run the steered backlog runtime test selector.
- [ ] Run a dry-run of the canonical top-level drain.
