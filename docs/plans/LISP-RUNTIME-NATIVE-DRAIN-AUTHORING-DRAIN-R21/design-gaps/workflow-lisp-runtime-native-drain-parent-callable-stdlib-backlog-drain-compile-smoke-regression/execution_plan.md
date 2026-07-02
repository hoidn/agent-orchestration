# Parent-Callable Stdlib Backlog-Drain Compile/Smoke Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the live `lisp_frontend_design_delta/drain::drain` parent-callable route so the Section-14 compile, the focused parent-drain feasibility slice, and the design-gap runtime smoke all pass without cross-run evidence binding or stale smoke expectations.

**Architecture:** The causal failure is two-part and both parts are shared-contract issues, not family-local cleanup. First, `orchestrator/workflow_lisp/build.py` binds reference-family evidence by falling through to stale call-scoped `existing-architecture-index.md` artifacts and by ignoring run-state history when resolving the implementation-architecture root; that makes the compile gate fail even though the owning run root has coherent completed-gap summaries and architecture files. Second, `tests/test_lisp_frontend_autonomous_drain_runtime.py::test_lisp_frontend_drain_design_gap_runtime_smoke` asserts `__provider_calls == 7` even though the test itself requires an eight-provider route with `require_all_providers=True`. Fix the evidence binding generically in shared resolver code, retarget the inconsistent smoke to the authored eight-step route, and treat all other autonomous-drain or Design Delta failures as residual classification unless a focused proof lane says otherwise. What this makes harder later: sibling-gap failures can no longer hide behind this slice's verification ladder; they will need their own owner-lane repair or explicit routing.

**Tech Stack:** Python 3, Workflow Lisp build/conformance modules under `orchestrator/workflow_lisp/`, Design Delta `.orc` workflow family, checked evidence manifests under `workflows/examples/inputs/workflow_lisp_migrations/`, `pytest`, and `python -m orchestrator compile`.

---

## Fixed Inputs And Authority

Treat these as the required source bundle for execution:

- `docs/index.md`
- `docs/work_definition_model.md`
- `docs/steering.md`
- `docs/design/README.md`
- `docs/capability_status_matrix.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21/design-gaps/workflow-lisp-runtime-native-drain-parent-callable-stdlib-backlog-drain-compile-smoke-regression/implementation_architecture.md`
- `state/workflow_lisp/calls/20260701T220811Z-w1vkti/root.drain_lisp_frontend_work_0.lisp_frontend_drain_iteration.route_selection.desig_f289187df7d2/lisp-frontend-design-delta-design-gap-architect-v214/de14bca20ef59f36.json/work_item_context.md`
- `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R38/drain/run_state.json`
- `artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R38/drain-summary.json`

Acceptance authority, in order:

- target-design Sections 11, 13, and 14 as narrowed by the re-entry implementation architecture;
- `implementation_architecture.md` for this gap, especially `Regression Evidence`, `Completion-Inventory Evidence Binding`, `Drain-Iteration Smoke Expectation Alignment`, `Focused Runtime Reclassification`, and `Residual Failure Routing`;
- the focused proof lanes in this plan; and
- fresh command output from the verification ladder below.

Non-authority but still required evidence:

- versioned run-root artifacts under `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R38/` and `artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R38/`;
- checked manifests under `workflows/examples/inputs/workflow_lisp_migrations/`; and
- generated per-call prompt artifacts under `state/workflow_lisp/calls/**`, which may be inspected as clues but must not become gate authority unless they are explicitly owned by the run root under validation.

## Causal Failure Summary

Do not treat this as a generic "Design Delta parent route is red" bug. The current work item is narrower.

1. `build.py::_reference_family_implementation_root_from_run_state(...)` only reads `architecture_path` from `blocked_design_gaps`. The active R38 run records the needed architecture path in history events, so the resolver silently falls back to an unversioned docs root.
2. `build.py::_resolve_reference_family_architecture_index(...)` falls through from versioned run-root iteration artifacts to a global `state/workflow_lisp/calls/**/existing-architecture-index.md` glob, then chooses the lexicographically last hit. That binds a stale call-scoped prompt artifact as compile-gate authority.
3. The reference-family completion-inventory surface then fails with `reference_family_conformance_invalid / reference_family_completed_gap_artifact_missing`, specifically because `missing_from_architecture_index` names this gap while other detail lists are empty.
4. Separately, `test_lisp_frontend_drain_design_gap_runtime_smoke` hard-codes `__provider_calls == 7` while supplying eight provider writers and requiring all of them to run. That assertion is internally inconsistent even if the workflow route is correct.

Implementation must fix those causes directly. It must not hand-edit `state/**` or `artifacts/work/**` evidence, backfill stale architecture indexes, or widen this slice into selector, blocked-recovery, review, or implementation-phase repairs unless one of the focused proof lanes below fails for the same cause.

## File Map

Primary owner surfaces:

- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow_lisp/reference_family_conformance.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_reference_family_conformance.py`
- `tests/test_lisp_frontend_autonomous_drain_runtime.py`

Focused route/regression surfaces:

- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- `tests/test_workflow_lisp_value_flow_census.py`
- `tests/test_workflow_lisp_resume_plumbing_retirement.py`
- `tests/test_workflow_lisp_lowering.py`

Surfaces that should stay untouched unless a focused proof lane proves otherwise:

- `workflows/library/lisp_frontend_design_delta/*.orc`
- `orchestrator/workflow_lisp/typecheck_calls.py`
- `orchestrator/workflow_lisp/lowering/workflow_calls.py`
- `orchestrator/workflow_lisp/phase_family_boundary.py`
- selector, blocked-recovery, done-review, and implementation-phase tests outside the focused selectors below

## Tasks

### Task 1: Reproduce The Exact Failure Classes Before Editing

**Files:**

- Read: `orchestrator/workflow_lisp/build.py`
- Read: `orchestrator/workflow_lisp/reference_family_conformance.py`
- Read: `tests/test_lisp_frontend_autonomous_drain_runtime.py`
- Read: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Read: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] **Step 1: Re-run the focused compile and smoke reproduction commands**

Run:

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py \
  -k 'selected_item_stdlib or parent_drain_build_and_execution_smoke or runtime_view_fixture' -q
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_lisp_frontend_drain_design_gap_runtime_smoke -q
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc \
  --entry-workflow lisp_frontend_design_delta/drain::drain \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
```

Expected before the fix:

- the focused feasibility slice fails only on the parent-drain build/execution smoke;
- the compile command fails with `reference_family_conformance_invalid`;
- the diagnostic detail shows `reference_family_completed_gap_artifact_missing` and `missing_from_architecture_index` naming this gap; and
- the runtime smoke fails on the inconsistent `__provider_calls == 7` assertion.

- [ ] **Step 2: Confirm the live source still matches the causal chain**

Confirm in code:

- `build.py::_reference_family_implementation_root_from_run_state(...)` only consults `blocked_design_gaps`;
- `build.py::_resolve_reference_family_architecture_index(...)` still falls back to `state/workflow_lisp/calls/**/existing-architecture-index.md`;
- `build.py::_resolve_reference_family_evidence_paths()` still threads that result into compile-time evidence resolution; and
- `test_lisp_frontend_drain_design_gap_runtime_smoke` still supplies eight provider writers but asserts `7`.

- [ ] **Step 3: If any tests are added or renamed later, run collect-only before proceeding**

Run only if test names or modules change:

```bash
python -m pytest --collect-only \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_reference_family_conformance.py \
  tests/test_lisp_frontend_autonomous_drain_runtime.py -q
```

### Task 2: Write The Failing Shared Evidence-Binding Proof First

**Files:**

- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_reference_family_conformance.py`

- [ ] **Step 1: Add a failing build-artifact test for run-state-owned evidence binding**

The new or updated test must prove all of these:

- the implementation-architecture root can be recovered from run-state-recorded architecture paths even when `blocked_design_gaps` omits `architecture_path`;
- the architecture-index resolver does not bind a stale per-call prompt artifact from `state/workflow_lisp/calls/**`;
- if the owning run root has no admissible architecture index, the resolver either:
  - degrades to direct architecture-root reconciliation, or
  - fails closed with explicit profile metadata naming the missing run-root-owned index;
- the fallback source is visible in the emitted profile or diagnostic rather than silently masquerading as recorded evidence.

Prefer to express this through the existing `_build_design_delta_parent_drain(...)` helper and aligned reference-family fixtures instead of inventing one-off ad hoc harnesses.

- [ ] **Step 2: Add or tighten the conformance-profile proof for missing run-root index coverage**

Use `tests/test_workflow_lisp_reference_family_conformance.py` to prove the profile behavior directly. Required coverage:

- missing architecture-index coverage still fails when the selected gap is genuinely absent from admissible evidence;
- a run-root without an owned architecture index does not become a pass just because an unrelated call artifact exists elsewhere in the repo;
- profile payload or diagnostics make the fallback or missing-owned-index status inspectable.

- [ ] **Step 3: Run the narrow tests to verify they fail for the intended reason**

Run:

```bash
python -m pytest tests/test_workflow_lisp_reference_family_conformance.py -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k 'reference_family' -q
```

Expected before the implementation change:

- at least one newly added or tightened assertion fails;
- the failure points at stale cross-run evidence binding or missing run-state-owned architecture-path recovery, not at unrelated Design Delta route behavior.

### Task 3: Implement The Generic Reference-Family Evidence Resolver Repair

**Files:**

- Modify: `orchestrator/workflow_lisp/build.py`
- Modify only if the surface contract needs explicit metadata or diagnostics: `orchestrator/workflow_lisp/reference_family_conformance.py`

- [ ] **Step 1: Recover implementation-architecture roots from all run-state-owned records**

Update `_reference_family_implementation_root_from_run_state(...)` so it collects candidate `architecture_path` values from the run-state structures that actually own them on the live route, not just `blocked_design_gaps`.

Required behavior:

- inspect blocked-gap records, completed-gap records when present, and run-state history/event records that carry `architecture_path`;
- prefer repo-relative `docs/plans/.../design-gaps/...` roots actually recorded by the run state;
- return the first existing recorded root before any docs fallback; and
- keep fallback behavior generic, not keyed to this gap id or to Design Delta workflow names.

- [ ] **Step 2: Remove cross-call architecture-index binding**

Update `_resolve_reference_family_architecture_index(...)` and the surrounding resolver path so that:

- admissible architecture indexes come only from the versioned run root under validation;
- global `state/workflow_lisp/calls/**` scanning is removed from the compile-gate authority path;
- missing run-root-owned architecture index never resolves by incidental lexicographic ordering; and
- the chosen fallback, if any, is deterministic and owner-scoped.

- [ ] **Step 3: Make the no-index path explicit rather than accidental**

Choose the smallest generic shape that makes the current R38 compile surface correct without editing run evidence.

Allowed shape:

- when the run root lacks an owned architecture index, rely on direct reconciliation against the resolved implementation-architecture root and emit profile-visible metadata explaining that the run-root index was absent.

Also allowed:

- fail closed with an explicit missing-owned-index diagnostic, but only if the focused compile acceptance can still be satisfied for the live route through another generic owner-scoped path recorded by the run.

Forbidden:

- backfilling or rewriting `state/**` artifacts;
- introducing a Design Delta-specific resolver branch;
- keeping the global call-artifact fallback in place behind a new condition; or
- weakening `reference_family_completed_gap_artifact_missing` so real summary/root mismatches slip through.

- [ ] **Step 4: Re-run the shared conformance/build proof set**

Run:

```bash
python -m pytest tests/test_workflow_lisp_reference_family_conformance.py -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k 'reference_family' -q
```

Expected:

- both commands pass;
- the profile still rejects genuine summary/root/index mismatches; and
- no test depends on call-scoped `existing-architecture-index.md` artifacts outside the run root under validation.

- [ ] **Step 5: Re-run the compile and focused feasibility slice**

Run:

```bash
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc \
  --entry-workflow lisp_frontend_design_delta/drain::drain \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py \
  -k 'selected_item_stdlib or parent_drain_build_and_execution_smoke or runtime_view_fixture' -q
```

Expected:

- the compile command passes with the conformance gate still enforced;
- the focused feasibility slice passes;
- `test_design_delta_parent_drain_build_and_execution_smoke_emit_default_resume_artifact` is green; and
- no `.orc` source or hidden-context lane needed to change just to repair evidence binding.

### Task 4: Retarget The Design-Gap Smoke To The Authored Eight-Step Route

**Files:**

- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Change the failing smoke only at the inconsistent expectation**

Keep the provider sequence exactly as authored:

- `SelectNextWork`
- `DraftDesignGapArchitecture`
- `ReviewDesignGapArchitecture`
- `DraftPlan`
- `ReviewPlan`
- `ExecuteImplementation`
- `ReviewImplementation`
- `SelectNextWork`

Required change:

- retarget the smoke so the provider-call count and the required provider sequence agree.

Preferred shape:

- assert `__provider_calls == 8`, or otherwise derive the expected count from the supplied provider list inside the test/helper.

Forbidden:

- lowering `require_all_providers=True`;
- removing the terminal selector call from the provider list;
- deleting the provider-count assertion without replacing it with an equivalent contract-level check; or
- absorbing unrelated blocked/recovery/review behavior into this test.

- [ ] **Step 2: Run the narrow smoke**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_lisp_frontend_drain_design_gap_runtime_smoke -q
```

Expected:

- the smoke passes;
- the summary still reports `drain_status == "DONE"`;
- `completed_design_gaps == ["parser-syntax"]` still holds; and
- the architecture file placement assertion remains intact.

### Task 5: Re-run The Focused Regression Guards And Classify Residuals

**Files:**

- Verify: `tests/test_workflow_lisp_value_flow_census.py`
- Verify: `tests/test_workflow_lisp_resume_plumbing_retirement.py`
- Verify: `tests/test_workflow_lisp_lowering.py`
- Verify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify only if residual classification must be recorded: `artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R38/workflow-lisp-runtime-native-drain-parent-callable-stdlib-backlog-drain-compile-smoke-regression/progress_report.md`

- [ ] **Step 1: Run the focused final acceptance ladder**

Run:

```bash
python -m pytest tests/test_workflow_lisp_value_flow_census.py tests/test_workflow_lisp_resume_plumbing_retirement.py -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k 'resume_plumbing_retirement or parent_drain_census_alignment or reference_family' -q
python -m pytest tests/test_workflow_lisp_lowering.py -k 'work_item_wrapper_bootstraps_private_child_phase_binding or item_ctx_child_phase_reuse_imported_backlog_drain_carries_derived_phase_context_bindings' -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k 'phase_ctx__plan__phase_name or child_phase_reuse or private_runtime_context_bindings' -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k 'selected_item_stdlib or parent_drain_build_and_execution_smoke or runtime_view_fixture' -q
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_lisp_frontend_drain_design_gap_runtime_smoke -q
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc \
  --entry-workflow lisp_frontend_design_delta/drain::drain \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
```

Expected:

- every command passes;
- the compile gate remains active;
- hidden phase-context and retirement evidence guards remain green; and
- no public runtime-context or family-specific compiler special case is introduced.

- [ ] **Step 2: Re-run the broader suites once only for classification**

Run:

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q
```

Expected:

- either suite may still be red;
- residual failures are classification output, not automatic scope expansion for this gap.

- [ ] **Step 3: Route residual failures instead of absorbing them**

Use the implementation architecture's `Residual Failure Routing` exactly.

Keep a remaining failure in this gap only if both are true:

- one of the focused commands in Step 1 is still red for the same cause; or
- the broader failure is only a directly route-linked expectation update caused by the shared evidence-binding repair or the eight-step smoke fix.

Otherwise route the failure to its owner lane and do not patch it here.

- [ ] **Step 4: Record residual routing if either broad suite remains red**

If Step 2 leaves failures behind, append a short note to:

- `artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R38/workflow-lisp-runtime-native-drain-parent-callable-stdlib-backlog-drain-compile-smoke-regression/progress_report.md`

Record:

- which tests remain red;
- which owner gap or shared lane they route to;
- whether any directly route-linked expectation update stayed in this slice; and
- that this gap is complete once the focused acceptance ladder is green, even if the broad suites still expose sibling-lane failures.

### Task 6: Hygiene And Closeout

- [ ] **Step 1: Run collect-only if any test names changed**

Run only if applicable:

```bash
python -m pytest --collect-only \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_reference_family_conformance.py \
  tests/test_lisp_frontend_autonomous_drain_runtime.py -q
```

- [ ] **Step 2: Run diff hygiene**

Run:

```bash
git diff --check
```

Expected:

- no whitespace or conflict-marker errors.

- [ ] **Step 3: Confirm the diff stayed inside the approved slice**

Allowed final diff:

- generic evidence-resolution changes in `build.py` and, only if necessary, `reference_family_conformance.py`;
- matching conformance/build-artifact proof updates;
- the single design-gap runtime smoke expectation repair; and
- an optional residual-routing note in the active progress report.

Forbidden final diff:

- edits to run-state or artifact evidence files under `state/**` or `artifacts/work/**` except the optional progress-report note;
- Design Delta-specific compiler branches;
- selector, blocked-recovery, review, or implementation-phase behavior changes with no focused proof-lane cause; or
- weakening compile/conformance gates to make the slice pass.

## Acceptance Criteria

This plan is complete only when all of the following are true with fresh command output:

- `python -m orchestrator compile ... drain::drain ...` succeeds with the reference-family conformance gate still enforced;
- the compile gate no longer binds architecture-index authority from unrelated `state/workflow_lisp/calls/**` artifacts;
- the implementation-architecture root resolver honors run-state-recorded architecture paths before any docs fallback;
- missing run-root-owned architecture-index evidence is handled deterministically and visibly, not by incidental glob ordering;
- `tests/test_workflow_lisp_reference_family_conformance.py -q` passes;
- `tests/test_workflow_lisp_build_artifacts.py -k 'resume_plumbing_retirement or parent_drain_census_alignment or reference_family' -q` passes;
- `tests/test_workflow_lisp_value_flow_census.py`, `tests/test_workflow_lisp_resume_plumbing_retirement.py`, and the focused hidden-context lowering/build-artifact selectors all pass unchanged;
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k 'selected_item_stdlib or parent_drain_build_and_execution_smoke or runtime_view_fixture' -q` passes;
- `tests/test_lisp_frontend_autonomous_drain_runtime.py::test_lisp_frontend_drain_design_gap_runtime_smoke` passes with an internally consistent eight-provider expectation;
- no state or artifact evidence is hand-edited to satisfy the gate;
- no Design Delta-specific compiler or resolver branch is introduced; and
- any remaining broader-suite failures are explicitly routed to sibling owner lanes instead of being silently absorbed into this gap.
