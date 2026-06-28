# Workflow Lisp Runtime-Native Drain Selector Stdlib Single-Context Signature Alignment Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-runtime-native-drain-selector-stdlib-single-ctx-signature-alignment-regression-reopen`
Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the regression identified by the selected target
design gap:

- restore `lisp_frontend_design_delta/stdlib_adapters::select-next-work-stdlib`
  so it calls `lisp_frontend_design_delta/selector::select-next-work` through
  the current single-`ctx` selector boundary;
- preserve the imported `std/drain/backlog-drain` selector workflow-ref
  contract: selector refs accept exactly one `DrainCtx`-shaped parameter and
  return a `SelectionResult`-shaped union;
- keep the Design Delta parent drain compiling through the accepted
  WCC/imported-stdlib route; and
- retain source-map and private-context boundary evidence for the carried
  selector context.

Out of scope:

- changing `std/drain::backlog-drain` semantics;
- widening the selector, `run-item`, or `gap-drafter` workflow-ref shapes;
- changing Workflow Lisp typecheck rules for `workflow_signature_mismatch`;
- introducing a command adapter, helper script, report parser, pointer file, or
  compatibility-bundle reread for selector routing;
- reworking provider request records, gap-drafter payload carriage, work-item
  finalization, terminal reprojection, or gap re-entry convergence; and
- claiming YAML-primary promotion.

## Problem Statement

The target selector workflow has already moved to the intended single-context
shape:

```lisp
(defworkflow select-next-work
  ((ctx DesignDeltaDrainCtx))
  -> SelectorPublicResult
  ...)
```

`select-next-work-stdlib` still calls that workflow through the old flattened
keyword boundary:

```lisp
(call select-next-work
  :steering ctx.steering_path
  :target_design ctx.target_design_path
  ...)
```

Fresh current-checkout evidence confirms the selected failure:

```text
pytest -q tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_parent_drain_entrypoint_adopts_stdlib_owner_routes
```

fails with:

```text
workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc:64:26:
[workflow_signature_mismatch] call binding `steering` does not match the callee signature
```

The failure is therefore not a missing compiler feature. It is a stale
family-owned stdlib adapter call site that no longer matches the family-owned
selector boundary.

## Design Constraints

This slice must preserve these contracts:

- `docs/design/workflow_lisp_runtime_native_drain_authoring.md` Sections 9.1,
  13.4, and 15 require imported `backlog-drain` adoption to use the shared
  stdlib owner lane without family-local loop emulation or widened workflow-ref
  boundaries.
- `docs/design/workflow_lisp_frontend_specification.md` requires imported
  stdlib forms to compile through ordinary imports, typechecking, WCC lowering,
  workflow-call validation, source maps, and shared validation.
- `docs/design/workflow_command_adapter_contract.md` forbids hidden workflow
  semantics in scripts or opaque command text. This slice must not solve a
  typed call mismatch by adding command glue.

## Owned Components

This slice owns:

- `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc`
  - align `select-next-work-stdlib` with the current `select-next-work`
    signature;
  - keep its return type as `DesignDeltaSelectionResult`;
  - keep the exported adapter name stable because `drain.orc` imports it as
    the selector workflow ref.
- focused tests in
  `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py` and
  `tests/test_workflow_lisp_build_artifacts.py`
  - maintain or tighten assertions around imported selector context carriage,
    owner-route adoption, and boundary evidence.
- fixture mirror files only if an existing runtime fixture copies
  `stdlib_adapters.orc` and must remain aligned with production source.

This slice intentionally does not own:

- `orchestrator/workflow_lisp/typecheck_calls.py`;
- `orchestrator/workflow_lisp/typecheck_dispatch.py`;
- `orchestrator/workflow_lisp/lowering/phase_drain.py`;
- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`;
- command-boundary manifests; or
- shared concepts such as spans, diagnostics, Core Workflow AST, Semantic IR,
  TypeCatalog, SourceMap, pointer authority, or variant proof.

If implementation discovers that typechecking or WCC lowering rejects
`(call select-next-work :ctx ctx)` despite the callee signature matching, that
is a separate compiler bug and must be split from this gap.

## Implementation Shape

Update `select-next-work-stdlib` to call the selector by its current boundary:

```lisp
(let* ((selection
         (call select-next-work
           :ctx ctx))
       ...)
  ...)
```

Keep the existing projection from `SelectorPublicResult` to
`DesignDeltaSelectionResult` unless the implementation chooses to reuse the
already existing `lisp_frontend_design_delta/stdlib_payloads::project-selection-result`
helper. Reusing that helper is acceptable only if it stays an ordinary typed
workflow call and does not add a wrapper solely to bypass proof or signature
validation.

The direct shape is preferred for this bounded regression because it changes
one stale call boundary and leaves existing adapter exports and downstream
tests stable. This makes later removal of the adapter projection duplication
slightly harder because the selector-to-stdlib projection still exists in two
places; that cleanup is outside this selected gap.

## Data And Control Flow

1. Parent `drain.orc` constructs `DesignDeltaDrainCtx`.
2. Parent calls imported `std/drain::backlog-drain` with
   `:selector select-next-work-stdlib`.
3. Shared `backlog-drain` validation sees
   `select-next-work-stdlib ((ctx DesignDeltaDrainCtx)) ->
   DesignDeltaSelectionResult`.
4. `select-next-work-stdlib` calls `select-next-work :ctx ctx`.
5. `select-next-work` renders the typed selector request and returns
   `SelectorPublicResult`.
6. `select-next-work-stdlib` projects the selector public result into
   `DesignDeltaSelectionResult`.
7. Imported `backlog-drain` consumes that returned union through ordinary
   `match`/workflow-call lowering and routes `EMPTY`, `GAP`, `SELECTED`, and
   `BLOCKED` as before.

No rendered report, pointer file, stdout payload, or compatibility JSON bundle
participates in this selector routing decision.

## Source Maps And Boundary Evidence

The repaired route must preserve existing source-map and boundary-authority
evidence:

- `select-next-work-stdlib` remains a callable workflow bundle with one private
  carried `ctx` context binding;
- the carried context binding records `context_family = "DrainCtx"` and
  `bridge_class = "imported_adapter_carried_context"`;
- generated context input roles still map `ctx.run.run-id`,
  `ctx.run.state-root`, and `ctx.run.artifact-root` to runtime anchors; and
- source-map provenance points back to the `stdlib_adapters.orc` adapter call
  site and the imported selector call, not to a hidden command or generated
  compatibility side channel.

## Command Adapter Policy

No new command adapter is proposed. If a later implementation touches command
boundaries while repairing this gap, `docs/design/workflow_command_adapter_contract.md`
is authoritative: any command boundary carrying workflow semantics must be
certified with typed inputs, typed outputs, declared effects, fixtures, source
maps, path-safety expectations, error taxonomy, owner, and retirement path.

For this slice, selector signature alignment is typed Workflow Lisp dataflow,
not command behavior.

## Feasibility Proof

The bounded fix is feasible because:

- `select-next-work` already has the correct single-`ctx` signature in
  `workflows/library/lisp_frontend_design_delta/selector.orc`;
- `select-next-work-stdlib` already receives `ctx DesignDeltaDrainCtx`;
- `DesignDeltaSelectionResult`, `DesignDeltaSelectedItemPayload`, and
  `DesignDeltaGapPayload` already exist and match the selector result variants
  expected by the imported `backlog-drain` route;
- current typecheck rules already enforce the intended selector shape through
  `validate_selector_workflow_ref`; and
- the failing diagnostic names only stale call binding `steering`, not a
  missing record-field or WCC route capability.

## Verification

Minimum deterministic checks for the implementation slice:

```bash
pytest --collect-only tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py
pytest -q tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_parent_drain_entrypoint_adopts_stdlib_owner_routes
pytest -q tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_artifacts_record_imported_selector_carried_context
pytest -q tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_parent_drain_imported_selector_ctx_carried_context_smoke
```

Expected evidence:

- the compile/source-shape check no longer fails at
  `stdlib_adapters.orc:64`;
- the build-artifact check still records the imported selector carried-context
  binding for `select-next-work-stdlib`;
- the smoke check reaches the design-gap selector path through the imported
  selector context and completes without private context bootstrap failure; and
- no new command-boundary row is required.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-gap-drafter-callable-boundary-over-imported-backlog-drain/implementation_architecture.md`

### Decisions Reused

- Reuse the prior slice's decision that imported `backlog-drain` keeps fixed
  workflow-ref boundaries and proves owner-lane behavior through focused
  compile/build/smoke evidence.
- Reuse its separation between shared stdlib prerequisites and downstream
  Design Delta family adoption. This slice repairs only the selector adapter
  regression needed for the Design Delta parent drain to compile again.
- Reuse the command-adapter contract decision that typed workflow semantics
  belong in typed calls/projections, not helper scripts or hidden file
  protocols.

### New Decisions In This Slice

- Treat `select-next-work-stdlib` as the family-owned selector adapter whose
  public workflow-ref boundary must be single-context because the underlying
  selector is now single-context.
- Prefer the smallest direct `.orc` call-site correction:
  `(call select-next-work :ctx ctx)`.
- Keep projection duplication acceptable for this slice so the regression fix
  does not broaden into selector-projection refactoring.

### Conflicts Or Revisions

- No prior architecture decision is revised.
- The current checkout conflicts with the accepted target because the adapter
  still calls a removed flattened selector boundary. This slice resolves that
  conflict by aligning the adapter to the accepted single-`ctx` selector
  boundary.

## Handoff Notes

Implementation should be a small source change plus verification. If the
direct call fix reveals a downstream failure, classify it by diagnostic:

- `workflow_signature_mismatch` on a different selector/run-item/gap-drafter
  boundary is adjacent owner-lane work and should not be hidden inside this
  slice.
- provider extern or prompt extern failures belong to selector provider
  metadata, not selector signature alignment.
- runtime smoke failures after compile/build success should be recorded as
  downstream runtime evidence gaps unless they directly involve carried
  selector context.
