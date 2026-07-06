# Design Delta Implementation-Phase Boundary Authority Registry Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to execute this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees.

**Goal:** Reconcile the checked `design_delta_parent_drain.boundary_authority.json` registry with the current `lisp_frontend_design_delta/implementation_phase` compiled evidence so the parent-drain compile gate and the focused feasibility selector no longer stop with `workflow_boundary_authority_unclassified` on a stale `implementation_phase` registry row, keeping the fail-closed gate intact.

**Architecture:** Verify-first. Fresh read-only inspection shows the rebaseline likely landed as uncommitted work (the stale row's generated hash segments are gone from the dirty checked registry), so Task 1 proves the current state with fresh command output before any edit. Only if a lane is red does Task 2 reconcile registry rows against compiled expected evidence. What this makes harder later: the checked registry describes only live compiled rows, so future `implementation_phase` route changes must rebaseline the registry and its focused guards together instead of relying on tolerated stale rows.

**Tech Stack:** shared compile/build validation, checked manifest reconciliation, `python -m orchestrator compile`, `pytest`, `rg`

---

## Fixed Inputs And Authority

- `docs/index.md`
- `docs/design/workflow_lisp_runtime_native_drain_authoring.md` (Sections 12.1, 13.4)
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_command_adapter_contract.md` (fail-closed checked-manifest discipline)
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21/design-gaps/workflow-lisp-design-delta-implementation-phase-boundary-authority-registry-repair/implementation_architecture.md`

Acceptance authority, highest first: the implementation architecture's
required capability, ownership, allowed/forbidden shapes, and acceptance
conditions; then target design Sections 12.1/13.4; then the command-adapter
contract.

## Current Causal State

1. The dependent slice
   `workflow-lisp-design-delta-compatibility-carrier-retirement` completed its
   approved carrier-retirement work; its remaining red check was the compile
   gate failing with `[workflow_boundary_authority_unclassified] stale
   boundary authority registry row does not match compiled evidence` for a
   `managed_write_root` row of
   `lisp_frontend_design_delta/implementation_phase::implementation-phase`
   keyed to a superseded review-revise-loop write-root shape
   (`...validate_review_findings_v1__result_bundle`).
2. That row is `implementation_phase` checkout drift, unrelated to the
   carrier lane, so the dependent stopped `BLOCKED` on this prerequisite.
3. The working tree has since accumulated uncommitted rebaseline work: the
   dirty checked registry no longer contains the stale row's generated hash
   segments, and its `implementation_phase` rows are keyed to current
   compiled shapes.
4. Therefore the likely remaining work is fresh verification evidence and, if
   any lane regressed, a bounded registry reconciliation in Task 2.

## Scope Guards

- Do not weaken, bypass, or make advisory the
  `workflow_boundary_authority_unclassified` gate or the stale-row rejection
  contract.
- Do not edit `value_flow_census.json`, `consumer_rendering_census.json`,
  `transition_authoring.json`, `resume_plumbing_retirement.json`, or the
  reference-family parity inputs; those lanes belong to sibling gaps.
- Do not edit family or stdlib `.orc` sources to regenerate the superseded
  registry shape.
- Do not hand-edit runtime-owned artifacts under `artifacts/work/`.
- Do not relabel stale rows as compatibility bridges or generated-internal
  values merely to satisfy the manifest.
- Completion requires fresh command output; inspection alone is insufficient.

## File Map

Owned (modify only if Task 1 proves a lane red):

- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json`
- `tests/test_workflow_lisp_build_artifacts.py` (focused boundary-authority
  guards only, and only where an expectation encodes the superseded row)

Read-only gate and evidence surfaces:

- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow_lisp/phase_family_boundary.py`
- `workflows/library/lisp_frontend_design_delta/implementation_phase.orc`
- `workflows/library/lisp_frontend_design_delta/drain.orc`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json`

## Task 1: Prove The Current Registry State With Fresh Evidence

- [ ] **Step 1: Run the focused registry-coverage guards**

```bash
pytest tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_boundary_authority_registry_covers_expected_rows \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_boundary_authority_report_for_all_target_workflows \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_rejects_stale_boundary_authority_registry_row_mismatch \
  -q
```

Expected: 3 passed — checked registry matches compiled expected rows, the
report covers every target workflow including `implementation_phase`, and a
genuinely stale row still fails closed.

- [ ] **Step 2: Run the focused feasibility selector from the blocker record**

```bash
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "selected_item_stdlib or parent_drain_build_and_execution_smoke" -q
```

Expected: no failure with `workflow_boundary_authority_unclassified`. If a
selector fails on a later checked-input gate owned by a sibling slice (for
example reference-family conformance), record the failure verbatim and treat
it as out of scope for this gap.

- [ ] **Step 3: Prove the compile gate progression**

```bash
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc \
  --entry-workflow lisp_frontend_design_delta/drain::drain \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
```

Expected: the compile must not fail with
`[workflow_boundary_authority_unclassified]` on an `implementation_phase`
registry row. Success, or a fail-closed stop on a later sibling-owned gate,
both satisfy this gap; record the observed first failure verbatim either way.

- [ ] **Step 4: Route on the evidence**

If Steps 1-3 all meet expectations, skip Task 2 and complete via Task 3. If a
boundary-authority lane is red, proceed to Task 2. If the failure is a
different gate class, stop and record the new first failing causal defect
instead of expanding this slice.

## Task 2: Reconcile The Registry (Only If Task 1 Proved The Lane Red)

- [ ] **Step 1: Derive the compiled expected rows**

Use the compiled boundary-authority report/expected-row projection from the
focused build-artifact tests (or the compile diagnostics) to enumerate the
current `(workflow_name, field_name, surface_kind)` rows for the parent-drain
route, including all `implementation_phase` target workflows.

- [ ] **Step 2: Rebaseline only provably stale or missing rows**

In `design_delta_parent_drain.boundary_authority.json`: remove or update only
rows whose key no longer appears in compiled evidence (including the stale
`implementation_phase` `managed_write_root` review-revise-loop row named by
the blocker); add rows only for genuinely unclassified live evidence. Keep
authority classifications honest — no relabeling to dodge the gate.

- [ ] **Step 3: Align focused guards only where they encode the stale shape**

Update boundary-authority guard expectations in
`tests/test_workflow_lisp_build_artifacts.py` only if they assert the
superseded row; keep the stale-row rejection and path-like mismatch guards
green and unweakened.

- [ ] **Step 4: Re-run the Task 1 ladder from the top**

All Task 1 steps must now meet expectations.

## Task 3: Record Completion Evidence

- [ ] **Step 1: Re-run the full acceptance set and capture output**

Run every command in the architecture's Acceptance Conditions section and
capture fresh output. If tests were added or renamed, also run:

```bash
pytest --collect-only tests/test_workflow_lisp_build_artifacts.py -q
```

- [ ] **Step 2: Confirm scope hygiene**

```bash
git status --porcelain
git diff --check
```

Expected: only owned files changed (none, if Task 2 was skipped); no
whitespace errors; sibling-lane checked manifests untouched.

## Completion Criteria

- Every acceptance condition in the implementation architecture holds with
  fresh command output on the execution checkout.
- The parent-drain direct compile's first failure (if any) is not the
  boundary-authority gate.
- The fail-closed contract is intact: genuinely stale registry rows still
  fail, and no gate was weakened or bypassed.
