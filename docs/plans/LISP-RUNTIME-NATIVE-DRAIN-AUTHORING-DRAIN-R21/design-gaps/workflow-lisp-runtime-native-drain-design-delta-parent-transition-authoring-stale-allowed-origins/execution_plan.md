# Design Delta Parent Transition-Authoring Stale Allowed-Origins Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to execute this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees.

**Goal:** Make the checked `design_delta_parent_drain.transition_authoring.json` manifest and the transition-authoring report agree with the live compiled parent-drain route so the direct compile and feasibility build no longer fail with `transition_authoring_invalid: stale_allowed_origins`, keeping the fail-closed gate intact.

**Architecture:** Verify-first. Fresh working-tree inspection shows the repair largely landed as uncommitted work (the three stale `imported_*_drain_result` rows are gone from the checked manifest, the imported-finalize row remains, and a sibling slice's blocked-run report records the transition-authoring suite passing on this checkout), so Task 1 proves the current state with fresh command output before any edit. Only if a lane is red does Task 2 implement the bounded repair, ordered causally: generic source-map kind fidelity first, then checked-manifest row reconciliation, then guard alignment. What this makes harder later: the checked manifest now describes only live compiled transition origins, so future route changes must update the manifest and its focused guards together instead of relying on tolerated stale rows.

**Tech Stack:** shared compile/build validation, source maps, checked manifest reconciliation, `python -m orchestrator compile`, `pytest`, `rg`

---

## Fixed Inputs And Authority

- `docs/index.md`
- `docs/design/workflow_lisp_runtime_native_drain_authoring.md` (Sections 7.4, 8.1, 12.1, 13.4)
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_command_adapter_contract.md` (fail-closed checked-manifest discipline)
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21/design-gaps/workflow-lisp-runtime-native-drain-design-delta-parent-transition-authoring-stale-allowed-origins/implementation_architecture.md`

Acceptance authority, highest first: the implementation architecture's
root-cause classification, ownership, allowed/forbidden shapes, and acceptance
conditions; then target design Sections 7.4/8.1/13.4; then the
command-adapter contract.

## Current Causal State

1. The dependent slice
   `workflow-lisp-runtime-native-drain-parent-callable-stdlib-backlog-drain-compile-smoke-regression`
   re-verified its own lanes green and classified the first live downstream
   blocker as this sibling lane: the transition-authoring report returned
   `status=fail` with `stale_allowed_origins` for the three
   `low_level.imported_*_drain_result` rows and the unmatched
   `low_level.imported_finalize_selected_item` row, failing the direct compile
   and the feasibility build at the `transition_authoring_invalid` gate.
2. The causal chain is: (a) the source-map authored-mapping fallback dropped
   the `resource_transition` kind for no-bundle finalizer steps, orphaning the
   correct imported-finalize row; (b) the three `std/drain` result-proc rows
   describe transitions that no longer exist because those procs are pure
   typed constructors on the live route; (c) the committed pass-case guard
   encoded the superseded drain-module attribution.
3. The working tree has since accumulated uncommitted repair work: the checked
   manifest now lists the family transitions rows plus
   `low_level.imported_finalize_selected_item` only.
4. Therefore the likely remaining work is fresh verification evidence and, if
   any lane regressed, the bounded repair in Task 2.

## Scope Guards

- Do not weaken or bypass `transition_authoring_invalid`, and do not downgrade
  `stale_allowed_origins` to a warning.
- Do not edit `boundary_authority.json`, `value_flow_census.json`,
  `consumer_rendering_census.json`, `rendering_cleanup.json`, or
  reference-family checked inputs; those lanes belong to sibling slices.
- Do not edit family or stdlib `.orc` sources to force the old evidence shape.
- Do not add Design Delta-specific branches to shared Python surfaces.
- Do not hand-edit runtime-owned artifacts under `artifacts/work/`.
- Do not assert prompt text or rendered report prose in guards.
- Completion requires fresh command output; inspection alone is insufficient.

## File Map

Owned (modify only if Task 1 proves a lane red):

- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.transition_authoring.json`
- `orchestrator/workflow_lisp/source_map.py`
- `orchestrator/workflow_lisp/transition_authoring.py` (generic
  filtering/matching logic only, last resort)
- `tests/test_workflow_lisp_transition_authoring.py`
- `tests/test_workflow_lisp_source_map.py`

Read-only route and boundary fixtures:

- `workflows/library/lisp_frontend_design_delta/drain.orc`
- `workflows/library/lisp_frontend_design_delta/work_item.orc`
- `workflows/library/lisp_frontend_design_delta/transitions.orc`
- `orchestrator/workflow_lisp/stdlib_modules/std/resource.orc`
- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
- `orchestrator/workflow_lisp/build.py` (gate stays untouched)

## Task 1: Prove The Current Transition-Authoring State With Fresh Evidence

- [ ] **Step 1: Run the three named selectors from the blocker record**

```bash
pytest tests/test_workflow_lisp_transition_authoring.py::test_transition_authoring_report_passes_for_checked_design_delta_family \
  tests/test_workflow_lisp_transition_authoring.py::test_transition_authoring_report_rejects_stale_allowed_origin_rows \
  tests/test_workflow_lisp_transition_authoring.py::test_transition_authoring_report_records_imported_finalize_selected_item_transition_origins \
  -q
```

Expected: 3 passed.

- [ ] **Step 2: Run the full transition-authoring and source-map suites**

```bash
pytest tests/test_workflow_lisp_transition_authoring.py -q
pytest tests/test_workflow_lisp_source_map.py -q
```

Expected: green.

- [ ] **Step 3: Prove the compile gate progression**

```bash
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc \
  --entry-workflow lisp_frontend_design_delta/drain::drain \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
```

Expected: the compile must not fail with `[transition_authoring_invalid]`.
Success, or a fail-closed stop on a later checked-input gate owned by a
sibling slice (boundary authority, reference-family conformance), both
satisfy this gap; record the observed first failure verbatim either way.

- [ ] **Step 4: Route on the evidence**

If Steps 1-3 all meet expectations, skip Task 2 and complete via Task 3. If
any lane is red, classify which of the three root-cause defects it matches and
proceed to Task 2 for that defect only. If the failure matches none of them,
stop and record the new first failing causal defect instead of expanding this
slice.

## Task 2: Implement The Bounded Repair (Only For Defects Task 1 Proved Open)

- [ ] **Step 1: Restore generic source-map kind fidelity first**

If lowered declared-transition steps on the no-bundle route serialize as kind
`step`: classify any authored-mapping fallback node carrying a declared
`resource_transition` config as step kind `resource_transition` in
`orchestrator/workflow_lisp/source_map.py`; no workflow-name, path-name, or
stdlib-specific branches. Add or update the focused behavioral regression in
`tests/test_workflow_lisp_source_map.py`. Then rerun:

```bash
pytest tests/test_workflow_lisp_source_map.py -q
pytest tests/test_workflow_lisp_transition_authoring.py -q
```

- [ ] **Step 2: Reconcile the checked manifest rows**

If the report still lists `stale_allowed_origins` after Step 1: remove only
rows whose transitions do not exist on the live compiled route (the three
`low_level.imported_*_drain_result` rows); keep
`low_level.imported_finalize_selected_item` and the family transitions rows.

- [ ] **Step 3: Align the guards to the live contract**

If the pass-case selector still fails on superseded expectations: rewrite its
assertions to status `pass`, empty violation buckets, low-level classification
for all origins, and finalize origins anchored to
`orchestrator/workflow_lisp/stdlib_modules/std/resource.orc`. Keep the
stale-row rejection and high-level rejection selectors green and unweakened.

- [ ] **Step 4: Touch report logic only as a last resort**

Inspect `orchestrator/workflow_lisp/transition_authoring.py` only if manifest
and guards already match compiled origins yet the report still disagrees; any
fix must stay generic to filtering/matching logic.

- [ ] **Step 5: Re-run the Task 1 ladder from the top**

All Task 1 steps must now meet expectations.

## Task 3: Record Completion Evidence

- [ ] **Step 1: Re-run the full acceptance set and capture output**

Run every command in the architecture's Acceptance Conditions section and
capture fresh output. If tests were added or renamed, also run:

```bash
pytest --collect-only tests/test_workflow_lisp_transition_authoring.py tests/test_workflow_lisp_source_map.py -q
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
  transition-authoring gate.
- The fail-closed contract is intact: genuinely stale allowed-origin rows
  still fail the report, and no gate was weakened or bypassed.
