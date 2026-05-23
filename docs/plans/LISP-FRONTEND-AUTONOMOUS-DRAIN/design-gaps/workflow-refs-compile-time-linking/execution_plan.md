# Workflow Refs Compile-Time Linking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the bounded compile-time `WorkflowRef[...]` slice so higher-order Workflow Lisp procedures and workflows accept typed workflow references, resolve them to compile-time concrete targets, specialize them away before runtime-boundary lowering, and keep the drain/Stage 7 translation path compiling through one generic frontend-owned workflow-ref layer.

**Architecture:** Keep all new behavior inside `orchestrator/workflow_lisp/`. Add one generic `workflow_refs.py` authority/specialization layer, extend the existing parser/type surface just enough to recognize `WorkflowRef[...]` parameter types and workflow-ref literals, and specialize higher-order callables before workflow-boundary flattening so lowering still targets the existing canonical-callable-key and imported-bundle/shared-validation seam. `WorkflowRef` remains compile-time-only in v0.1 and must not survive into runtime-facing workflow signatures, structured bundles, or shared runtime state.

**Tech Stack:** Python 3 dataclasses, `orchestrator.workflow_lisp`, `orchestrator.workflow.loaded_bundle.LoadedWorkflowBundle`, module-link canonical callable keys in `orchestrator.workflow_lisp.modules`, frontend provenance via `LoweringOriginMap`, pytest, and `.orc` fixtures under `tests/fixtures/workflow_lisp/`.

---

## Fixed Inputs

Treat these as authoritative for execution:

- `docs/index.md`
- `docs/steering.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `7.7 Workflow References`
  - `15. Higher-Order Workflow Parameters`
  - `52. call Lowering`
  - `58. backlog-drain Lowering`
  - `74. Source Map Requirements`
  - `108. Workflow Refs`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `2. Relationship To The Full Specification`
  - `3. Non-Goals`
  - `4.2 Definitions`
  - `14. Implementation Stages`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-full-restart-20260523T081550Z/iterations/4/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-full-restart-20260523T081550Z/iterations/4/design-gap-architect/check_commands.json`

Reference current seams before editing:

- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/drain_stdlib.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/modules.py`
- `orchestrator/workflow_lisp/procedures.py`
- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/resource.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/workflows.py`
- `tests/test_workflow_lisp_workflow_refs.py`
- `tests/test_workflow_lisp_drain_stdlib.py`
- `tests/test_workflow_lisp_stage7_translation.py`

## Current Checkout Baseline

Assume this exact starting state:

- Stage 1 through Stage 7 Workflow Lisp infrastructure already exists, including module linking, typed procedures, Stage 3 lowering, drain stdlib lowering, and Stage 7 translation fixtures.
- `docs/steering.md` is empty in this checkout. Treat that as no extra local steering, not scope permission.
- `progress_ledger.json` is empty, so there is no later recorded implementation event superseding this gap.
- `tests/test_workflow_lisp_workflow_refs.py` already exists, but it still locks in the temporary "workflow refs are out of scope" behavior. Part of this work is to replace that placeholder coverage with true in-scope regression tests.
- `orchestrator/workflow_lisp/resource.py` still owns the provisional drain-scoped workflow-ref authority dataclasses:
  - `WorkflowRefAuthoritySource`
  - `WorkflowRefRequirement`
  - `WorkflowExternRebindingPlan`
  - `ResolvedWorkflowRef`
  - `WorkflowRefCallPlan`
  - `WorkflowRefEnvironment`
- `orchestrator/workflow_lisp/typecheck.py` still performs direct drain-specific selector/run-item/gap-drafter checks via `_workflow_ref_signature(...)` and related helpers.
- `orchestrator/workflow_lisp/lowering.py` still performs drain-specific rebound specialization through `_specialize_backlog_drain_call_target(...)`.
- `orchestrator/workflow_lisp/modules.py` already owns canonical callable keys and import/export resolution; reuse it rather than adding a second workflow-identity scheme.
- `orchestrator/workflow_lisp/reader.py` currently rejects `[` and `]`, so `WorkflowRef[...]` needs a narrow reader/parser change without enabling arbitrary vector syntax.

## Hard Scope Limits

Implement only this bounded slice:

- `WorkflowRef[...]` as a frontend-owned parameter type for `defworkflow` and `defproc`
- compile-time resolution of workflow-ref literals to:
  - same-file workflows
  - linked module exports
  - explicitly registered imported bundles
- compile-time structural signature checks
- compile-time extern-closure checks
- deterministic specialization of higher-order procedures and workflows so workflow-ref parameters disappear before runtime-boundary lowering
- direct-call lowering back onto canonical callable keys or imported bundles after specialization
- drain/resource migration onto the generic workflow-ref layer

Explicit non-goals:

- no runtime workflow loading, dynamic code lookup, or second executor
- no storing, returning, serializing, materializing, or transporting `WorkflowRef` through workflow inputs/outputs, records, unions, provider results, command results, or path contracts
- no redesign of shared runtime modules under `orchestrator/workflow/`
- no user-authored provider/prompt extern rebinding surface
- no queue/resource semantic redesign beyond replacing the temporary resolver
- no widening into general higher-order runtime values

## Non-Negotiable Rules

Do not re-decide any of these while executing:

- `WorkflowRef` is compile-time-only for v0.1.
- No unresolved `WorkflowRefTypeRef` may survive into lowered runtime workflow signatures.
- Reuse the current staged pipeline:
  `read -> syntax -> macro expansion -> definitions/procedures/workflows -> typecheck -> lowering -> shared validation`
- Reuse module-link canonical callable keys and the imported-bundle/shared-validation seam.
- Reuse `LoweringOriginMap`, authored spans, and macro-expansion provenance for all generated specializations.
- Preserve typed bundles as authority, reports as views, and pointer files as representations.
- Preserve drain role semantics for `selector`, `run-item`, and `gap-drafter`; only the workflow-ref authority layer changes.
- `docs/design/workflow_command_adapter_contract.md` remains binding: workflow refs must not become a loophole for hidden command semantics.

## File Map

Create:

- `orchestrator/workflow_lisp/workflow_refs.py`
- `tests/fixtures/workflow_lisp/valid/workflow_refs_same_file.orc`
- `tests/fixtures/workflow_lisp/valid/workflow_refs_forwarding.orc`
- `tests/fixtures/workflow_lisp/modules/valid/workflow_refs/imported_entry.orc`
- `tests/fixtures/workflow_lisp/modules/valid/workflow_refs/imported_helper.orc`
- `tests/fixtures/workflow_lisp/invalid/workflow_ref_literal_required.orc`
- `tests/fixtures/workflow_lisp/invalid/workflow_ref_runtime_transport_invalid.orc`
- `tests/fixtures/workflow_lisp/invalid/workflow_ref_signature_invalid.orc`
- `tests/fixtures/workflow_lisp/invalid/workflow_ref_specialization_cycle.orc`
- `tests/fixtures/workflow_lisp/invalid/workflow_ref_extern_unsatisfied.orc`

Modify:

- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/drain_stdlib.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/modules.py`
- `orchestrator/workflow_lisp/procedures.py`
- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/resource.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/workflows.py`
- `tests/test_workflow_lisp_drain_stdlib.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_modules.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_stage7_translation.py`
- `tests/test_workflow_lisp_workflow_refs.py`
- `tests/test_workflow_lisp_workflows.py`

Modify only if a failing test proves it necessary:

- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `tests/test_workflow_lisp_diagnostics.py`

## Required Diagnostics

Reuse existing codes where they still fit:

- `workflow_signature_mismatch`
- `workflow_ref_unknown`
- `workflow_ref_signature_invalid`
- `workflow_ref_return_type_invalid`
- `workflow_call_unknown`
- `variant_ref_unproved`
- `module_export_missing`
- `module_import_ambiguous`

Add or preserve these workflow-ref-specific codes:

- `workflow_ref_type_invalid`
- `workflow_ref_literal_required`
- `workflow_ref_runtime_transport_forbidden`
- `workflow_ref_extern_rebinding_unsatisfied`
- `workflow_ref_specialization_cycle`

If an existing placeholder code such as `workflow_call_signature_erased` is no longer the right contract, replace it in tests and implementation with the approved workflow-ref-specific diagnostics above.

### Task 1: Replace Placeholder Coverage With Real Workflow-Ref Regressions

**Files:**

- Create: `tests/fixtures/workflow_lisp/valid/workflow_refs_same_file.orc`
- Create: `tests/fixtures/workflow_lisp/valid/workflow_refs_forwarding.orc`
- Create: `tests/fixtures/workflow_lisp/modules/valid/workflow_refs/imported_entry.orc`
- Create: `tests/fixtures/workflow_lisp/modules/valid/workflow_refs/imported_helper.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/workflow_ref_literal_required.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/workflow_ref_runtime_transport_invalid.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/workflow_ref_signature_invalid.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/workflow_ref_specialization_cycle.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/workflow_ref_extern_unsatisfied.orc`
- Modify: `tests/test_workflow_lisp_workflow_refs.py`
- Modify: `tests/test_workflow_lisp_modules.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_workflows.py`
- Modify: `tests/test_workflow_lisp_lowering.py`

- [ ] **Step 1: Replace the current "out of scope" tests with in-scope expectations**

In `tests/test_workflow_lisp_workflow_refs.py`, remove the current assertions that `WorkflowRef[...]` parsing and `(workflow-ref ...)` literals fail by construction. Replace them with tests that expect successful elaboration/typechecking for:

- same-file higher-order workflow parameters
- explicit `(workflow-ref target-name)` literals
- forwarding through `defproc`
- imported-module workflow-ref resolution

- [ ] **Step 2: Add invalid fixtures for the bounded compile-time-only contract**

Add failing fixtures that lock down:

- non-literal or computed workflow-ref arguments
- runtime transport of workflow refs through workflow outputs or structured records
- structural signature mismatch
- specialization recursion through the same specialization key
- unsatisfied provider/prompt extern closure

- [ ] **Step 3: Extend neighboring suites instead of inventing new broad tests**

Add focused assertions to:

- `tests/test_workflow_lisp_modules.py`
  Verify imported workflow-ref targets resolve through canonical callable keys and surface module ambiguity/missing-export diagnostics at the use site.
- `tests/test_workflow_lisp_procedures.py`
  Verify higher-order `defproc` specializations are reused and forwarded bindings must match exactly.
- `tests/test_workflow_lisp_workflows.py`
  Verify higher-order `defworkflow` specialization removes workflow-ref parameters from runtime boundaries and preserves union-proof requirements.
- `tests/test_workflow_lisp_lowering.py`
  Verify specialized callable-key determinism and source-map remapping for rebound calls.

- [ ] **Step 4: Run collection before implementation**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_workflow_refs.py tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_lowering.py -q
```

Expected: collection succeeds and includes the new workflow-ref regressions.

- [ ] **Step 5: Run the new focused module and confirm it fails for the right reasons**

Run:

```bash
python -m pytest tests/test_workflow_lisp_workflow_refs.py -q
```

Expected: failures point to missing `WorkflowRef[...]` parsing, missing literal elaboration, unresolved specialization, or old placeholder diagnostics rather than unrelated shared-runtime errors.

### Task 2: Add The `WorkflowRef[...]` Type Surface

**Files:**

- Modify: `orchestrator/workflow_lisp/reader.py`
- Modify: `orchestrator/workflow_lisp/type_env.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `orchestrator/workflow_lisp/procedures.py`

- [ ] **Step 1: Make the reader accept only the narrow bracket surface needed for type expressions**

Update `reader.py` so `[` and `]` can participate in the `WorkflowRef[...]` type syntax without turning the language into generic vector syntax. Keep the change minimal and reject arbitrary bracketed expressions.

- [ ] **Step 2: Introduce a frontend-only `WorkflowRefTypeRef`**

Add to `type_env.py`:

- `WorkflowRefTypeRef`
  - `param_type_refs: tuple[TypeRef, ...]`
  - `return_type_ref: RecordTypeRef | UnionTypeRef`

Also add helpers for:

- structural type rendering for diagnostics
- recursive containment checks so runtime-boundary surfaces can reject embedded workflow refs
- exact type comparison for forwarded workflow-ref bindings

- [ ] **Step 3: Parse `WorkflowRef[...]` in workflow and procedure parameter elaboration**

Update `_elaborate_param(...)` in both `workflows.py` and `procedures.py` so parameters can carry a structured type expression rather than only a plain type name. Restrict legality to parameter positions only.

- [ ] **Step 4: Reject illegal positions at the type-environment layer**

Teach type resolution and boundary analysis to reject `WorkflowRef[...]` inside:

- record fields
- union fields
- workflow returns
- command/provider return contracts
- path contracts
- any runtime-boundary lowering surface

Raise `workflow_ref_type_invalid` or `workflow_ref_runtime_transport_forbidden` at the authored site.

- [ ] **Step 5: Run the focused type-surface tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_workflow_refs.py -k 'type_surface or runtime_transport' -q
```

Expected: valid parameter typing now passes; illegal transport positions fail with workflow-ref-specific diagnostics.

### Task 3: Add Generic Workflow-Ref Resolution And Higher-Order Typechecking

**Files:**

- Create: `orchestrator/workflow_lisp/workflow_refs.py`
- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/modules.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `orchestrator/workflow_lisp/procedures.py`

- [ ] **Step 1: Move generic authority records out of `resource.py` and into `workflow_refs.py`**

Implement frontend-owned dataclasses and helpers for:

- `WorkflowRefBinding`
- `WorkflowRefAuthoritySource`
- `WorkflowExternRebindingPlan`
- `ResolvedWorkflowRef`
- `WorkflowRefSpecializationKey`
- `WorkflowRefInstantiationPlan`
- optional `WorkflowRefEnvironment` reused by consumers

Preserve only drain-specific role contracts in `resource.py`.

- [ ] **Step 2: Implement deterministic resolution against the three approved authority sources**

In `workflow_refs.py`, resolve targets in this order:

1. same-file workflow catalog
2. linked module export via `modules.py`
3. explicitly registered imported bundle metadata

Normalize every resolved target to one canonical callable key before later typechecking or lowering.

- [ ] **Step 3: Implement structural signature compatibility and extern-closure checks**

The resolver must verify:

- exact parameter count
- structural compatibility of each parameter type
- structural compatibility of the return type
- compile-time extern closure, with optional compiler-owned rebinding metadata for stdlib consumers

If resolution fails, raise:

- `workflow_ref_unknown`
- `workflow_ref_signature_invalid`
- `workflow_ref_return_type_invalid`
- `workflow_ref_extern_rebinding_unsatisfied`

- [ ] **Step 4: Teach expression elaboration about workflow-ref literals and lexical workflow-ref bindings**

Update `expressions.py` so:

- bare or qualified workflow names can elaborate as workflow-ref literals when a `WorkflowRefTypeRef` is expected
- explicit `(workflow-ref target-name)` elaborates when no expected type is available
- `call` heads may be lexical workflow-ref bindings, but no other dynamic callee expression becomes legal

- [ ] **Step 5: Typecheck higher-order calls without widening runtime semantics**

Update `typecheck.py` so:

- workflow-ref parameters are tracked separately from runtime-boundary parameters
- higher-order call sites require compile-time-known workflow-ref values
- forwarding is legal only when the declared `WorkflowRefTypeRef` matches exactly
- workflow refs cannot be returned, stored, serialized, or embedded in runtime bundles
- union-return proof behavior remains unchanged once the workflow-ref target is resolved

- [ ] **Step 6: Run focused typechecking and module-resolution regressions**

Run:

```bash
python -m pytest tests/test_workflow_lisp_workflow_refs.py tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_workflows.py -q
```

Expected: same-file, imported-module, and forwarded workflow refs typecheck; invalid fixtures fail with the dedicated diagnostics above.

### Task 4: Specialize Higher-Order Callables Before Runtime-Boundary Lowering

**Files:**

- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `orchestrator/workflow_lisp/procedures.py`
- Modify: `tests/test_workflow_lisp_lowering.py`

- [ ] **Step 1: Add specialization planning before lowering**

In the compiler/lowering handoff, resolve workflow-ref arguments, build a deterministic `WorkflowRefSpecializationKey`, and instantiate or reuse a specialized callable before runtime-boundary flattening runs.

The specialization key must include:

- higher-order callable identity
- ordered `(param_name, resolved_workflow_key)` bindings

- [ ] **Step 2: Strip workflow-ref parameters from generated runtime boundaries**

The specialized callable must retain only runtime-boundary parameters. `WorkflowRef[...]` parameters must disappear before:

- workflow-boundary analysis
- flattened input contract construction
- imported-bundle registration
- shared validation handoff

- [ ] **Step 3: Lower rebound calls as ordinary direct calls**

Update `_lower_call_expr(...)` and any compile-stage helper path so calls through resolved workflow-ref bindings lower exactly like direct calls to:

- same-file canonical callable keys
- linked imported workflow exports
- registered imported bundles

Do not invent a runtime workflow-ref execution path.

- [ ] **Step 4: Preserve provenance and detect specialization cycles**

For every generated specialization:

- record authored definition span plus call-site span in `LoweringOriginMap`
- remap diagnostics back to the authored higher-order site
- reject direct or indirect recursion through the same specialization key with `workflow_ref_specialization_cycle`

- [ ] **Step 5: Run lowering-focused regressions**

Run:

```bash
python -m pytest tests/test_workflow_lisp_lowering.py -k 'workflow_ref or specialization or higher_order' -q
```

Expected: specialized callable keys are deterministic, lowered calls are direct, origins are preserved, and cycle fixtures fail with the dedicated cycle diagnostic.

### Task 5: Rebase Drain Stdlib And Resource Consumers Onto The Generic Layer

**Files:**

- Modify: `orchestrator/workflow_lisp/drain_stdlib.py`
- Modify: `orchestrator/workflow_lisp/resource.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `tests/test_workflow_lisp_drain_stdlib.py`
- Modify: `tests/test_workflow_lisp_stage7_translation.py`

- [ ] **Step 1: Remove drain ownership of generic workflow-ref resolution**

Leave drain-specific role validation in `resource.py`, but delete or relocate generic authority/resolution types and helpers so drain code becomes a consumer of `workflow_refs.py`.

- [ ] **Step 2: Rewire drain role validation onto generic workflow-ref signatures**

Replace the direct Stage 6 selector/run-item/gap-drafter checks in `typecheck.py` with calls into the generic workflow-ref compatibility layer, then keep only the role-specific contract assertions:

- selector shape requirements
- selected-item payload derivation
- gap-drafter shape requirements
- `DrainResult` union expectations

- [ ] **Step 3: Replace drain-only rebound logic with generic specialization plumbing**

Update `_lower_backlog_drain(...)` and related helpers so selector/run-item/gap-drafter targets flow through the same specialization and extern-closure machinery as ordinary higher-order calls. Preserve existing provider metadata validation and drain accumulator behavior.

- [ ] **Step 4: Run the drain-focused regressions**

Run:

```bash
python -m pytest tests/test_workflow_lisp_drain_stdlib.py -k 'workflow_ref_environment or workflow_ref_resolution or provider_metadata' -q
```

Expected: drain role validation still passes, provider metadata checks still hold, and the drain layer no longer owns a parallel resolver.

### Task 6: Final Verification, Documentation Touches, And Evidence

**Files:**

- Modify if behavior text changed: `docs/lisp_workflow_drafting_guide.md`
- Modify if discoverability changed: `docs/index.md`
- Modify if author-facing diagnostics/examples changed materially: the narrowest relevant `docs/design/...` page

- [ ] **Step 1: Run the exact deterministic verification bundle for this work item**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_workflow_refs.py tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_stage7_translation.py -q
python -m pytest tests/test_workflow_lisp_workflow_refs.py -q
python -m pytest tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_workflows.py -q
python -m pytest tests/test_workflow_lisp_lowering.py -k 'workflow_ref or specialization or higher_order' -q
python -m pytest tests/test_workflow_lisp_drain_stdlib.py -k 'workflow_ref_environment or workflow_ref_resolution or provider_metadata' -q
python -m pytest tests/test_workflow_lisp_stage7_translation.py -k 'remaining_drain or selected_item or workflow_ref' -q
```

Expected: all commands pass; no placeholder "workflow refs are out of scope" contract remains.

- [ ] **Step 2: Run one broader compile smoke if any Stage 7 fixture had to change materially**

Run one narrow compile smoke through the actual compile entrypoint for the affected drain-shaped fixture. Use the smallest command that exercises the end-to-end specialization path without inventing a new workflow run.

Expected: the drain-shaped translation compiles end to end through the generic workflow-ref layer.

- [ ] **Step 3: Update docs only if the author-facing surface changed materially**

If the implementation exposes new user-visible authoring rules beyond the approved design docs, update only the narrowest lasting docs page. Do not restate transient implementation details.

- [ ] **Step 4: Record completion evidence in the implementation summary**

When execution is done, the closing summary must include:

- what changed
- which files carried the new workflow-ref layer
- which temporary drain-owned pieces were removed or demoted
- the exact pytest commands run
- whether any docs were updated

## Acceptance Checklist

Execution is complete only when all of these are true:

- [ ] `WorkflowRef[...]` is accepted in `defworkflow` and `defproc` parameter positions.
- [ ] Workflow-ref literals resolve deterministically to same-file workflows, linked module exports, or registered imported bundles.
- [ ] Higher-order procedures and workflows specialize away workflow-ref parameters before runtime-boundary lowering.
- [ ] Calls through workflow-ref parameters lower as ordinary direct calls through the existing canonical-callable/imported-bundle seam.
- [ ] Workflow refs remain compile-time-only and cannot cross runtime boundaries.
- [ ] Drain/resource code consumes the generic workflow-ref layer instead of maintaining parallel resolution authority.
- [ ] Stage 7 drain-shaped translation still compiles through the revised layer.
- [ ] Specialized callables and rebound calls preserve authored provenance in `LoweringOriginMap`.

## Implementation Notes

Use these heuristics during execution:

- Prefer replacing placeholder tests before changing production code; they define the target contract.
- Keep `workflow_refs.py` generic and frontend-owned. Drain-specific names should not reappear there.
- If a current helper in `resource.py` or `lowering.py` is already generic, move it instead of copying it.
- Avoid broad parser work. This slice needs exactly one new surface: `WorkflowRef[...]` in type positions and `(workflow-ref target-name)` in expression positions.
- Do not weaken shared validation to accommodate workflow refs; specialize them away before that boundary.
- If a new diagnostic is needed, make it authored-site specific and source-mapped.
