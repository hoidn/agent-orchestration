# Workflow Lisp Runtime-Native Drain Selector Stdlib Single-Context Signature Alignment Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-runtime-native-drain-selector-stdlib-single-ctx-signature-alignment-regression-reopen`
Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`
Command-adapter authority: `docs/design/workflow_command_adapter_contract.md`

## Scope

This slice covers exactly the reopened selector stdlib adapter alignment gap:

- restore `lisp_frontend_design_delta/stdlib_adapters::select-next-work-stdlib`
  so it calls `lisp_frontend_design_delta/selector::select-next-work` through
  the current single-`ctx` selector boundary;
- preserve the imported `std/drain/backlog-drain` selector workflow-ref
  contract: selector refs accept exactly one `DrainCtx`-shaped parameter and
  return the family selection union;
- keep the Design Delta parent drain on the accepted WCC/imported-stdlib route;
  and
- retain source-map, workflow-call, and private-context boundary evidence for
  the carried selector context.

Out of scope:

- changing `std/drain::backlog-drain` routing semantics;
- widening selector, `run-item`, or `gap-drafter` workflow-ref shapes;
- changing Workflow Lisp call typechecking, WCC lowering, variant proof,
  SourceMap, Core Workflow AST, Semantic Workflow IR, executable IR, or
  pointer-authority contracts;
- refactoring selector provider request records, projection duplication,
  gap-drafter payload carriage, work-item finalization, terminal reprojection,
  or gap re-entry convergence;
- adding scripts, command adapters, inline command glue, report parsing,
  pointer files, or compatibility-bundle rereads; and
- claiming YAML-primary promotion.

This is a bounded implementation architecture, not a replacement target design
or a broad Design Delta migration plan.

## Problem Statement

The family selector workflow already uses the target single-context boundary:

```lisp
(defworkflow select-next-work
  ((ctx DesignDeltaDrainCtx))
  -> SelectorPublicResult
  ...)
```

The stdlib adapter still calls that workflow through the removed flattened
keyword boundary:

```lisp
(call select-next-work
  :steering ctx.steering_path
  :target_design ctx.target_design_path
  :baseline_design ctx.baseline_design_path
  :manifest ctx.manifest
  :progress_ledger ctx.progress_ledger_path
  :run_state ctx.run_state_path)
```

Fresh selection evidence names this as the blocking failure for the Design
Delta parent drain: the imported `backlog-drain` owner route reaches
`select-next-work-stdlib`, but that adapter calls `select-next-work` with
stale flattened bindings. The expected compiler diagnostic is
`workflow_signature_mismatch` on the unexpected binding `steering`.

The selected gap is therefore not a missing stdlib or compiler capability. It
is a stale family-owned adapter call site that no longer matches the
family-owned selector boundary.

## Design Constraints

This slice must preserve these contracts:

- `docs/design/workflow_lisp_runtime_native_drain_authoring.md` Sections 9.1,
  13.4, and 15 require imported `backlog-drain` adoption to use the shared
  stdlib owner lane without family-local loop emulation or widened
  workflow-ref boundaries.
- `docs/design/workflow_lisp_frontend_specification.md` requires imported
  stdlib forms and workflow calls to compile through ordinary imports,
  typechecking, WCC lowering, workflow-call validation, source maps, shared
  validation, and Semantic IR / executable IR projection.
- `docs/design/workflow_command_adapter_contract.md` forbids hidden workflow
  semantics in scripts or opaque command text. This slice must not solve a
  typed call mismatch by adding command glue.
- Prior runtime-native drain slices keep shared stdlib prerequisites separate
  from downstream Design Delta family adoption. This slice fixes one family
  adapter regression and does not claim broader shared stdlib proof.

## Current Checkout Facts

- `workflows/library/lisp_frontend_design_delta/selector.orc` defines
  `select-next-work ((ctx DesignDeltaDrainCtx)) -> SelectorPublicResult`.
- `workflows/library/lisp_frontend_design_delta/selector.orc` already renders a
  typed `SelectorRequest` prompt subject from `ctx`, so the selector no longer
  needs a flattened call boundary.
- `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc` defines
  `select-next-work-stdlib ((ctx DesignDeltaDrainCtx)) ->
  DesignDeltaSelectionResult`, but its internal call to `select-next-work`
  still passes flattened keyword arguments.
- `workflows/library/lisp_frontend_design_delta/drain.orc` passes
  `select-next-work-stdlib` as the `:selector` workflow ref to imported
  `std/drain::backlog-drain`.
- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc` calls the selector
  workflow ref as `(call selector :ctx ctx)`, which is the fixed owner-route
  shape this slice must preserve.
- `workflows/library/lisp_frontend_design_delta/stdlib_payloads.orc` already
  contains `project-selection-result`, which can project
  `SelectorPublicResult` into `DesignDeltaSelectionResult`, but reusing it is
  optional and should not broaden this regression fix.
- `tests/test_workflow_lisp_build_artifacts.py` already has a focused
  `select-next-work-stdlib` boundary evidence assertion for private carried
  `ctx` context.

## Feasibility Proof

The bounded fix is feasible without new language or runtime work:

1. The callee and caller already agree on the semantic context type:
   `DesignDeltaDrainCtx`.
2. The stdlib route already calls selector workflow refs with exactly `:ctx`.
3. Existing call typechecking should accept `(call select-next-work :ctx ctx)`
   because it matches the callee boundary.
4. Existing projection code in `select-next-work-stdlib` can continue to build
   `DesignDeltaSelectionResult` from `SelectorPublicResult`.
5. The selected failure names only stale call binding shape, not missing
   fields, missing type refs, provider metadata, WCC expressivity, or runtime
   bundle validation.

If implementation discovers that `(call select-next-work :ctx ctx)` still
fails despite matching the callee signature, classify that as a separate
compiler/typecheck regression and do not hide it inside this slice.

## Ownership Boundaries

This slice owns:

- `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc`
  - update the `select-next-work-stdlib` call site to use `:ctx ctx`;
  - keep `select-next-work-stdlib` exported under the same name;
  - keep its return type as `DesignDeltaSelectionResult`; and
  - keep selector-to-stdlib projection behavior equivalent.
- Focused tests in:
  - `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`;
  - `tests/test_workflow_lisp_build_artifacts.py`.
- Any fixture mirror of `stdlib_adapters.orc`, only if a checked fixture copies
  the production source and must stay aligned.

This slice intentionally does not own:

- `orchestrator/workflow_lisp/typecheck_calls.py`;
- `orchestrator/workflow_lisp/typecheck_dispatch.py`;
- `orchestrator/workflow_lisp/lowering/phase_drain.py`;
- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`;
- command-boundary manifests;
- provider prompt rendering or typed request-record semantics;
- gap-drafter payload carriage;
- work-item/finalizer/terminal reprojection behavior; or
- YAML-primary promotion or parity adjudication.

## Implementation Shape

Change the selector call inside `select-next-work-stdlib` to the current
single-context boundary:

```lisp
(let* ((selection
         (call select-next-work
           :ctx ctx))
       ...)
  ...)
```

Keep the existing inline projection from `SelectorPublicResult` to
`DesignDeltaSelectionResult` unless implementation chooses the already existing
`lisp_frontend_design_delta/stdlib_payloads::project-selection-result` helper.
That helper reuse is acceptable only if it remains an ordinary typed workflow
call and does not add a wrapper to bypass workflow-call validation, variant
proof, source maps, or private-context evidence.

The direct call-site correction is preferred. It repairs the regression in one
family-owned file and leaves later selector projection de-duplication for a
separate cleanup slice. The tradeoff is that projection logic remains
duplicated between `stdlib_adapters.orc` and `stdlib_payloads.orc` a little
longer.

## Data And Control Flow

1. `drain.orc` builds `DesignDeltaDrainCtx`.
2. `drain.orc` calls imported `std/drain::backlog-drain` with
   `:selector select-next-work-stdlib`.
3. Shared `backlog-drain` calls the selector workflow ref as `:ctx ctx`.
4. `select-next-work-stdlib` calls `select-next-work :ctx ctx`.
5. `select-next-work` renders the typed `SelectorRequest` provider prompt
   subject and returns `SelectorPublicResult`.
6. `select-next-work-stdlib` projects that result into
   `DesignDeltaSelectionResult`.
7. Imported `backlog-drain` consumes the returned union through ordinary
   match/workflow-call lowering and routes `EMPTY`, `GAP`, `SELECTED`, and
   `BLOCKED`.

No rendered report, pointer file, stdout payload, command output, or
compatibility JSON bundle participates in this selector routing decision.

## Source Maps And Boundary Evidence

The repaired route must preserve existing evidence:

- `select-next-work-stdlib` remains a callable workflow bundle with one private
  carried `ctx` binding;
- the binding records `context_family = "DrainCtx"` and
  `bridge_class = "imported_adapter_carried_context"`;
- generated context input roles continue to map `ctx.run.run-id`,
  `ctx.run.state-root`, and `ctx.run.artifact-root` to runtime anchors;
- `ctx__run_state_path` remains private carried context evidence, not a public
  authored input or runtime-derived authority claim; and
- source-map provenance points to `stdlib_adapters.orc` and the typed selector
  call, not to generated command glue or a compatibility side channel.

## Command Adapter Policy

No command adapter is proposed or needed. If implementation touches command
boundaries while repairing this gap, `docs/design/workflow_command_adapter_contract.md`
is authoritative: any command boundary carrying workflow semantics must be
certified with typed inputs, typed outputs, declared effects, path-safety
expectations, fixtures, negative fixtures, source-map behavior, owner, and
retirement path.

For this slice, selector signature alignment is typed Workflow Lisp dataflow.
Adding a script, command step, report parser, pointer file, or stdout JSON path
would violate the selected target.

## Verification

Minimum deterministic checks for the implementation slice:

```bash
pytest --collect-only tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py
pytest -q tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_parent_drain_entrypoint_adopts_stdlib_owner_routes
pytest -q tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_artifacts_record_imported_selector_carried_context
pytest -q tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_parent_drain_imported_selector_ctx_carried_context_smoke
```

Expected evidence:

- compile no longer fails in `stdlib_adapters.orc` on stale binding
  `steering`;
- `select-next-work-stdlib` still has a single private carried `ctx` context
  binding in build artifacts;
- the parent drain route reaches imported `backlog-drain` with
  `select-next-work-stdlib` as the selector workflow ref; and
- no new command-boundary row or compatibility bundle is required.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-family-specific-compiler-hook-retirement/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-gap-drafter-callable-boundary-over-imported-backlog-drain/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-literal-name-stdlib-intrinsic-retirement/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-shared-std-phase-owner-lane-self-hosting-regression-reopen/implementation_architecture.md`

### Decisions Reused

- Reuse the family-specific compiler-hook retirement slice's rule that a
  family regression must not be repaired with new Design Delta-specific
  compiler/build hooks.
- Reuse the gap-drafter callable-boundary slice's owner split: imported
  `backlog-drain` keeps fixed workflow-ref boundaries, and family adapters
  must conform to those boundaries rather than smuggling payloads through
  wrappers.
- Reuse the literal-name stdlib intrinsic retirement slice's rule that
  promoted stdlib behavior must arrive through imported stdlib composition and
  ordinary typed forms, not literal-name direct lowerers.
- Reuse the shared `std/phase` self-hosting regression slice's narrowness
  discipline: fix the broken owner boundary directly, and split any broader
  stdlib/compiler issue discovered by verification into its own gap.
- Reuse the command-adapter contract decision that typed workflow semantics
  belong in typed calls/projections or runtime-native effects, not helper
  scripts or hidden file protocols.

### New Decisions In This Slice

- Treat `select-next-work-stdlib` as the family-owned selector adapter whose
  external workflow-ref boundary is already correct and whose internal call
  site must be aligned to the selector's current single-`ctx` signature.
- Prefer the smallest direct `.orc` source correction:
  `(call select-next-work :ctx ctx)`.
- Leave selector projection de-duplication as future cleanup so this reopened
  regression does not expand into an unrelated refactor.

### Conflicts Or Revisions

- No prior architecture decision is revised.
- The current checkout conflicts with the accepted target because
  `select-next-work-stdlib` still calls a removed flattened selector boundary.
  This slice resolves that conflict by aligning the adapter to the accepted
  single-`ctx` selector boundary.
- If the direct call repair reveals a different failure in `std/drain`,
  gap-drafter payload carriage, `std/phase`, terminal reprojection, or Design
  Delta build evidence, that is an adjacent gap rather than a revision to this
  architecture.

## Handoff Notes

Implementation should be a small `.orc` source change plus focused
verification. Classify follow-on failures by diagnostic:

- `workflow_signature_mismatch` on another selector/run-item/gap-drafter
  boundary is adjacent owner-lane work.
- provider extern or prompt extern failures belong to selector provider
  metadata, not this signature alignment.
- runtime smoke failures after compile/build success should be recorded as
  downstream runtime evidence gaps unless they directly involve carried
  selector context.
