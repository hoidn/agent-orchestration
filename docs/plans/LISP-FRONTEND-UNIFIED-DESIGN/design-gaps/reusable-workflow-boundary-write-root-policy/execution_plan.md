# Reusable Workflow Boundary Write-Root Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make managed write-root transport deterministic across same-file workflow calls, private-workflow procedure calls, loop-managed reusable calls, and `resume-or-start` workflow-call recovery without changing authored syntax, runtime value types, or shared runtime ownership.

**Architecture:** Keep the change inside `orchestrator/workflow_lisp/`. Treat `WorkflowBoundaryProjection.generated_internal_inputs` entries with `reason == "managed_write_root"` as the preferred same-file lowered-callee authority, keep raw `__write_root__...` input-name scans only as a compatibility fallback, and keep imported-bundle compatibility through `workflow_managed_write_root_inputs(...)`. Route `_lower_call_expr(...)`, the private-workflow branch of `_lower_procedure_call_expr(...)`, `_managed_call_step(...)`, and the workflow-call path inside `_resume_start_bundle_ref(...)` through one discovery helper and one deterministic caller-binding allocator that preserve the existing `.orchestrate/workflow_lisp/calls/...` layout and `${loop.index}` disambiguation.

**Tech Stack:** Python 3, `orchestrator.workflow_lisp.lowering`, `orchestrator.workflow_lisp.contracts`, typed loaded bundles from `orchestrator.workflow.loaded_bundle`, shared workflow validation/runtime, pytest, `compile_stage3_module(..., validate_shared=True)`

---

## Fixed Inputs

Treat these as implementation authority:

- `docs/index.md`
- `docs/design/workflow_lisp_unified_frontend_design.md`
  - `29. Reusable Workflow Boundary Write Roots`
  - `30. Standard-Library Lowering Completion`
  - `74. Dependency Graph`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `16. Effect System`
  - `19. Context Types`
  - `20. Canonical State Layout`
  - `21. Phase Context`
  - `26. run-provider-phase`
  - `27. review-revise-loop`
  - `28. resume-or-start`
  - `51. defproc Lowering`
  - `57. review-revise-loop Lowering`
  - `74. Source Map Requirements`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/work_instructions.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/reusable-workflow-boundary-write-root-policy/implementation_architecture.md`
- `state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/4/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/4/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-UNIFIED-DESIGN/progress_ledger.json`

Current checkout facts that must not be rediscovered during implementation:

- `state/LISP-FRONTEND-UNIFIED-DESIGN/progress_ledger.json` currently has no events.
- `lower_workflow_definitions(...)` already promotes terminal `hidden_inputs` into authored hidden inputs and boundary-projection metadata.
- `_lower_call_expr(...)`, the private-workflow branch of `_lower_procedure_call_expr(...)`, and `_managed_call_step(...)` each currently allocate managed write-root bindings independently.
- `_resume_start_bundle_ref(...)` currently reconstructs workflow-call bundle paths separately from ordinary call lowering.

## Hard Scope Limits

Implement only this bounded slice:

- one shared lowering helper for managed write-root requirement discovery;
- one shared lowering helper for deterministic caller-owned binding allocation;
- refactors of same-file workflow calls, private-workflow procedure calls, loop-managed reusable calls, and `resume-or-start` workflow-call bundle recovery to use those helpers;
- focused regression coverage for deterministic managed write-root transport.

Explicit non-goals:

- no new authored syntax, type-system surfaces, runtime value types, adapters, scripts, or runtime-native effects;
- no redesign of `run-provider-phase`, `review-revise-loop`, `resume-or-start`, provider semantics, command semantics, or shared validation ownership;
- no change to visible generated input names, `.orchestrate/workflow_lisp/calls/...` layout, `${loop.index}` loop disambiguation, runtime collision checks, pointer authority, or path-safety enforcement;
- no widening of private-workflow export rules, same-file call record flattening, `with-phase` semantics, or effectful composition scope beyond this write-root-policy seam.

## File Ownership

Modify:

- `orchestrator/workflow_lisp/lowering.py`
- `tests/test_workflow_lisp_drain_stdlib.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_examples.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_subworkflow_calls.py`

Modify only if a focused failing test proves the need:

- `orchestrator/workflow_lisp/contracts.py`

Do not modify unless verification forces it:

- shared runtime modules under `orchestrator/workflow/`
- `.orc` fixtures already covering `run-provider-phase`, `review-revise-loop`, or `resume-or-start`

## Required Contract To Implement

Keep the implementation centered on two internal helpers.

Discovery helper contract:

```python
def _managed_write_root_requirements_for_callable(
    *,
    lowered_callee: LoweredWorkflow | None,
    imported_bundle: LoadedWorkflowBundle | None,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> tuple[str, ...]:
    ...
```

Rules:

- If `lowered_callee` is available, prefer `lowered_callee.boundary_projection.generated_internal_inputs` filtered to `reason == "managed_write_root"`.
- If same-file projection metadata is absent or empty, allow one compatibility fallback to the current raw authored-input prefix scan against the lowered mapping.
- If only `imported_bundle` is available, use `workflow_managed_write_root_inputs(imported_bundle)`.
- Sort returned names deterministically before emitting bindings.
- Do not infer new write roots from reports, path strings, or terminal output text.

Allocation helper contract:

```python
def _managed_write_root_bindings(
    *,
    caller_workflow_name: str,
    call_step_name: str,
    callee_name: str,
    managed_inputs: tuple[str, ...],
    iteration_scope: str | None = None,
) -> dict[str, str]:
    ...
```

Rules:

- Emit `.orchestrate/workflow_lisp/calls/<caller>/<call-step>/<callee>/<generated-input>.json` when `iteration_scope` is `None`.
- Emit `.orchestrate/workflow_lisp/calls/<caller>/<call-step>/<iteration-scope>/<callee>/<generated-input>.json` when loop scope is present.
- For private-workflow procedure calls, `callee_name` must remain the procedure signature `canonical_name` for the stored path segment even though the runtime `call` target stays `procedure.generated_workflow_name`; this preserves the current visible layout and avoids leaking generated private-workflow names into caller-owned write-root paths.
- Preserve the current caller-owned prefix and the existing generated input names exactly.
- Keep hidden-input provenance behavior unchanged where the caller already records generated origins.

`resume-or-start` workflow-call recovery must use the same policy:

- keep command-result and phase-scoped provider paths unchanged;
- when `:start` is a workflow call, recover the canonical bundle input name from the lowered/imported callee’s structured-result contract, validate that it belongs to the discovered managed-input set, and derive the path through `_managed_write_root_bindings(...)` instead of hand-formatting a parallel path.

## Task 1: Lock The Expected Regression Surface In Tests

**Files:**

- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_drain_stdlib.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_examples.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_subworkflow_calls.py`

- [ ] Extend `tests/test_workflow_lisp_lowering.py` so same-file workflow calls assert managed write-root bindings are derived from the callee boundary contract and still land under `.orchestrate/workflow_lisp/calls/...`.
- [ ] Add or extend a private-workflow regression in `tests/test_workflow_lisp_procedures.py` that compiles a reusable helper around `review-revise-loop` or `run-provider-phase` and asserts the generated private workflow call uses the same managed-binding path shape as authored workflow calls.
- [ ] Make that private-workflow regression assert the exact current identifier split: runtime `call` points at `procedure.generated_workflow_name`, while the caller-owned managed write-root path keeps the procedure signature `canonical_name` in the `<callee>` segment.
- [ ] Extend `tests/test_workflow_lisp_drain_stdlib.py` so the existing backlog-drain lowering assertions remain the dedicated proof that `_managed_call_step(...)` preserves `.orchestrate/workflow_lisp/calls/.../${loop.index}/<callee>/...` layout for selector, run-item, and gap-drafter reusable calls after the shared-allocator refactor.
- [ ] Extend `tests/test_workflow_lisp_phase_stdlib.py` so the workflow-call branch of `resume-or-start` asserts the `START` arm recovers the canonical bundle path for `plan-run` through the shared policy instead of merely asserting that a call step exists.
- [ ] Add a focused imported-bundle `resume-or-start` regression in `tests/test_workflow_lisp_phase_stdlib.py` that compiles a workflow-call `START` arm against an imported validated bundle and asserts canonical bundle-path recovery comes from the shared managed write-root policy rather than same-file-only metadata.
- [ ] Keep `tests/test_workflow_lisp_examples.py::test_kiss_backlog_item_orc_compiles_to_typed_phase_stack` as the integration-style compile proof that reusable workflow calls still bind generated write roots in real example workflows; strengthen its assertions only if needed to pin the deterministic path layout more tightly.
- [ ] Keep `tests/test_workflow_lisp_build_artifacts.py` asserting `generated_internal_inputs[*].reason == "managed_write_root"` so the preferred same-file authority surface remains covered.
- [ ] Keep `tests/test_subworkflow_calls.py` runtime guardrails proving hard-coded or colliding write-root bindings still fail; do not replace those checks with frontend-only assertions.

Suggested test targets to add or tighten:

- `test_lowering_same_file_workflow_call_uses_managed_write_root_boundary_projection`
- `test_private_workflow_call_reuses_managed_write_root_allocator`
- `test_lowering_backlog_drain_uses_repeat_until_with_typed_accumulator`
- `test_resume_or_start_workflow_call_uses_shared_managed_write_root_bundle_path`
- `test_resume_or_start_imported_workflow_call_uses_shared_managed_write_root_bundle_path`

**Blocking verification after Task 1:**

- [ ] Run:
  - `python -m pytest --collect-only tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_examples.py tests/test_workflow_lisp_build_artifacts.py tests/test_subworkflow_calls.py -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_drain_stdlib.py::test_lowering_backlog_drain_uses_repeat_until_with_typed_accumulator -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_lowering.py::test_lowering_same_file_workflow_call_uses_managed_write_root_boundary_projection -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_procedures.py::test_private_workflow_call_reuses_managed_write_root_allocator -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_phase_stdlib.py::test_resume_or_start_workflow_call_uses_shared_managed_write_root_bundle_path -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_phase_stdlib.py::test_resume_or_start_imported_workflow_call_uses_shared_managed_write_root_bundle_path -q`

Expected before implementation: the new or tightened tests fail because same-file/private-workflow call lowering and both same-file and imported-bundle `resume-or-start` recovery still rely on duplicated prefix scans and path formatting instead of one shared boundary policy.

## Task 2: Implement Shared Managed Write-Root Requirement Discovery

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify only if clearly helpful: `orchestrator/workflow_lisp/contracts.py`

- [ ] Add one lowering-local helper that returns managed write-root requirement names for a call target from either a lowered same-file callee or an imported bundle.
- [ ] Prefer `lowered_callee.boundary_projection.generated_internal_inputs` filtered by `reason == "managed_write_root"` when a lowered same-file or generated private workflow callee is available.
- [ ] Keep one compatibility fallback for lowered same-file callees that still scans authored input names for the `__write_root__` prefix only when projection metadata is unavailable.
- [ ] Reuse `workflow_managed_write_root_inputs(imported_bundle)` for imported bundles instead of duplicating surface-input scans.
- [ ] Raise existing narrow diagnostics if a lowered same-file callee is internally inconsistent enough that managed write-root requirements cannot be recovered deterministically.
- [ ] Keep helper return values deterministic by sorting names before downstream allocation.

Implementation guardrails:

- Do not invent a new runtime-facing metadata schema.
- Do not make authored inputs or debug reports the new semantic authority.
- Do not remove the imported-bundle compatibility path.

**Blocking verification after Task 2:**

- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_build_artifacts.py::test_source_map_serializes_generated_semantic_effects_for_frontend_build -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_lowering.py::test_lowering_same_file_workflow_call_uses_managed_write_root_boundary_projection -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_procedures.py::test_private_workflow_call_reuses_managed_write_root_allocator -q`

Expected after Task 2: discovery tests still may fail at the binding-path assertion stage, but the callee requirement set should now come from one helper and preserve existing metadata-driven reasons.

## Task 3: Implement Shared Caller Allocation And Refactor All Call-Site Consumers

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_drain_stdlib.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_examples.py`

- [ ] Add one helper that maps the discovered managed input names to deterministic caller-owned `.json` paths, with optional `iteration_scope`.
- [ ] Refactor `_lower_call_expr(...)` to:
  - flatten authored bindings exactly as today;
  - fetch managed requirements through the shared discovery helper;
  - append write-root bindings through the shared allocator;
  - leave normal call outputs and output projections unchanged.
- [ ] Refactor the private-workflow branch of `_lower_procedure_call_expr(...)` to use the same discovery and allocation helpers, while leaving inline procedure lowering unchanged and preserving the current identifier split between runtime `call: procedure.generated_workflow_name` and caller-path `<callee> = procedure.signature.name`.
- [ ] Refactor `_managed_call_step(...)` to stop formatting loop-managed call paths inline and instead call the shared allocator with `iteration_scope="${loop.index}"`; keep `hidden_inputs[...] = _origin_from_context_source(...)` behavior unchanged.
- [ ] Preserve current call-step names, IDs, and visible generated input names so existing example and runtime tests remain meaningful.

Implementation guardrails:

- Do not add a second call-lowering path for private workflows.
- Do not collapse loop-managed bindings into invariant paths.
- Do not weaken or bypass the runtime collision checks asserted in `tests/test_subworkflow_calls.py`.

**Blocking verification after Task 3:**

- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_drain_stdlib.py::test_lowering_backlog_drain_uses_repeat_until_with_typed_accumulator -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_lowering.py::test_lowering_same_file_workflow_call_uses_managed_write_root_boundary_projection -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_procedures.py::test_private_workflow_call_reuses_managed_write_root_allocator -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_examples.py::test_kiss_backlog_item_orc_compiles_to_typed_phase_stack -q`
- [ ] Run:
  - `python -m pytest tests/test_subworkflow_calls.py::test_call_rejects_colliding_write_root_bindings -q`
- [ ] Run:
  - `python -m pytest tests/test_subworkflow_calls.py::test_call_rejects_colliding_write_root_bindings_without_imported_legacy_magic -q`

Expected after Task 3: same-file, private-workflow, and loop-managed reusable calls all allocate managed write-root bindings through one path formatter, private-workflow calls keep their current `canonical_name` path segment despite calling a generated workflow target, and the runtime still rejects illegal or colliding caller-supplied roots.

## Task 4: Align `resume-or-start` Workflow-Call Bundle Recovery With The Shared Policy

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_lowering.py`

- [ ] Refactor the workflow-call branch of `_resume_start_bundle_ref(...)` to recover the canonical managed bundle input from the callee’s structured-result contract and then derive the path through `_managed_write_root_bindings(...)`.
- [ ] Update `_call_result_bundle_input_name(...)` and `_workflow_result_bundle_input_name(...)` only as much as needed so canonical bundle-input recovery remains strict about one terminal structured-result step, but no longer duplicates the caller path policy.
- [ ] Validate that the canonical bundle input selected for a workflow-call start arm is one of the discovered managed write-root requirements; keep `resume_or_start_contract_invalid` when that proof fails.
- [ ] Keep `CommandResultExpr`, `RunProviderPhaseExpr`, `ProduceOneOfExpr`, and phase-scoped `ProviderResultExpr` bundle-path handling unchanged.
- [ ] Ensure imported-bundle workflow calls still use the validated bundle surface rather than same-file-only metadata, and prove that path through the focused imported-bundle regression instead of relying on generic imported-bundle compile coverage.

**Blocking verification after Task 4:**

- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_phase_stdlib.py::test_resume_or_start_workflow_call_uses_shared_managed_write_root_bundle_path -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_phase_stdlib.py::test_resume_or_start_imported_workflow_call_uses_shared_managed_write_root_bundle_path -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_phase_stdlib.py::test_resume_or_start_supports_union_start_workflow_call -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_phase_stdlib.py::test_shared_validation_accepts_resume_or_start -q`

Expected after Task 4: same-file and imported-bundle `resume-or-start` workflow-call `START` arms recover the same canonical managed bundle path ordinary call lowering would allocate, without changing the non-workflow-call branches.

## Task 5: Final Verification And Evidence Capture

**Files:**

- No new code files; verification only

- [ ] Run:
  - `python -m pytest --collect-only tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_examples.py tests/test_workflow_lisp_build_artifacts.py tests/test_subworkflow_calls.py -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_examples.py tests/test_workflow_lisp_build_artifacts.py tests/test_subworkflow_calls.py -q`
- [ ] If any tests were renamed while implementing, rerun the relevant `--collect-only` command immediately and update the selectors in this plan’s execution notes before claiming completion.
- [ ] Record in the implementation summary:
  - which helper names were introduced or renamed;
  - which call sites now consume the shared discovery/allocation helpers;
  - which pytest selectors were run and their fresh outcomes;
  - which selector proves imported-bundle `resume-or-start` bundle recovery now follows the shared policy;
  - confirmation that runtime collision and hard-coded-root guardrails still pass.

Completion criteria:

- same-file reusable callees expose managed write-root requirements through one explicit frontend boundary contract;
- same-file workflow calls, private-workflow procedure calls, and loop-managed reusable calls allocate caller-owned write-root bindings through one deterministic helper;
- loop-managed reusable calls keep the existing `${loop.index}` disambiguation and current drain path layout as proven by the dedicated drain-stdlib lowering assertions;
- `review-revise-loop` and `run-provider-phase` remain reusable inside private workflows without bespoke call-site path logic;
- `resume-or-start` workflow-call start arms recover canonical bundle paths through the same managed write-root policy;
- imported-bundle `resume-or-start` workflow-call start arms prove the same bundle-recovery policy through the validated bundle surface;
- imported-bundle compatibility, runtime collision checks, and path-safety guardrails remain intact.
