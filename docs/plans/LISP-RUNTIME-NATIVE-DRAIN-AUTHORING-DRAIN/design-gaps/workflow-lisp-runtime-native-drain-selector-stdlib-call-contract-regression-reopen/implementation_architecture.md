# Workflow Lisp Runtime-Native Drain Selector Stdlib Call Contract Regression Reopen Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-runtime-native-drain-selector-stdlib-call-contract-regression-reopen`
Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`
Command-adapter authority: `docs/design/workflow_command_adapter_contract.md`

## Scope

This slice covers exactly the selected target-design gap:

- restore the typed selector-to-stdlib call contract for the Design Delta
  parent drain route;
- update
  `lisp_frontend_design_delta/stdlib_adapters::select-next-work-stdlib` so it
  calls `lisp_frontend_design_delta/selector::select-next-work` through the
  current single-`ctx` selector boundary;
- preserve the imported `std/drain::backlog-drain` selector workflow-ref
  contract, where the selector is called as `:ctx ctx` and returns the family
  selection union; and
- keep source-map, private carried context, workflow-call, and boundary
  authority evidence for the repaired route.

Out of scope:

- changing `std/drain::backlog-drain` loop semantics or workflow-ref arity;
- widening selector, `run-item`, or `gap-drafter` signatures;
- changing call typechecking, WCC lowering, Core Workflow AST, Semantic
  Workflow IR, executable IR, SourceMap, variant proof, or pointer-authority
  contracts;
- refactoring selector projection duplication between `stdlib_adapters.orc`
  and `stdlib_payloads.orc`;
- changing provider request records, prompt externs, command-boundary
  manifests, runtime transitions, gap re-entry convergence, or terminal
  reprojection;
- adding scripts, command adapters, inline Python, report parsing, pointer
  files, stdout JSON, or compatibility-bundle rereads; and
- claiming YAML-primary promotion.

This is a bounded implementation architecture for one regression reopen. It
does not replace the runtime-native drain target design or the accepted
Workflow Lisp frontend baseline.

## Problem Statement

The Design Delta selector workflow already has the current target boundary:

```lisp
(defworkflow select-next-work
  ((ctx DesignDeltaDrainCtx))
  -> SelectorPublicResult
  ...)
```

`workflows/library/lisp_frontend_design_delta/selector.orc` also builds a
typed `SelectorRequest` prompt subject from `ctx`, so the selector no longer
needs a flattened public call surface.

The adapter used by imported `backlog-drain` has drifted from that contract.
`workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc` defines:

```lisp
(defworkflow select-next-work-stdlib
  ((ctx DesignDeltaDrainCtx))
  -> DesignDeltaSelectionResult
  ...)
```

but its body still calls the selector with removed flat keyword bindings:

```lisp
(call select-next-work
  :steering ctx.steering_path
  :target_design ctx.target_design_path
  :baseline_design ctx.baseline_design_path
  :manifest ctx.manifest
  :progress_ledger ctx.progress_ledger_path
  :run_state ctx.run_state_path)
```

Fresh selection evidence reports the resulting parent-drain compile failure as
`workflow_signature_mismatch` in `stdlib_adapters.orc`. The failing binding is
the stale flat selector call, not a missing stdlib surface or missing compiler
capability.

The implementation problem is therefore narrow: align one family-owned
adapter call site to the typed selector boundary that already exists.

## Design Constraints

This slice must preserve these contracts:

- `docs/design/workflow_lisp_runtime_native_drain_authoring.md` Sections 9.1,
  13.4, 14, and 15 require the Design Delta parent route to use imported
  `backlog-drain` without family-local loop emulation, widened workflow refs,
  compatibility-bundle rereads, or public path threading.
- `docs/design/workflow_lisp_frontend_specification.md` requires workflow
  calls to compile through ordinary imports, typechecking, WCC lowering,
  workflow-call validation, shared validation, source maps, Semantic IR, and
  executable IR projection.
- `docs/design/workflow_command_adapter_contract.md` forbids repairing hidden
  workflow semantics with uncertified scripts or opaque command text. This
  slice has no command-adapter work; the fix is typed Workflow Lisp dataflow.
- Prior runtime-native drain slices keep shared stdlib prerequisites separate
  from downstream Design Delta family adoption. This slice fixes one
  family-owned adapter regression and does not claim a broader shared owner
  lane.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The generated architecture index for this request listed these prior slices,
and this architecture was drafted against them:

- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-family-specific-compiler-hook-retirement/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-gap-drafter-callable-boundary-over-imported-backlog-drain/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-literal-name-stdlib-intrinsic-retirement/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-selector-stdlib-single-ctx-signature-alignment-regression-reopen/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-shared-std-phase-owner-lane-self-hosting-regression-reopen/implementation_architecture.md`

### Decisions Reused

- Reuse the family-specific compiler-hook retirement slice's rule that Design
  Delta regressions must not be repaired with new family-name compiler or build
  hooks.
- Reuse the gap-drafter callable-boundary slice's owner split: imported
  `backlog-drain` keeps fixed workflow-ref boundaries, and family adapters
  conform to those boundaries through typed values.
- Reuse the literal-name stdlib intrinsic retirement slice's rule that
  promoted stdlib behavior must arrive through imported stdlib composition and
  ordinary typed forms, not direct literal-name lowerers.
- Reuse the selector single-context alignment slice's central repair decision:
  `select-next-work-stdlib` should call `select-next-work` as
  `(call select-next-work :ctx ctx)`.
- Reuse the shared `std/phase` self-hosting slice's narrowness rule: if the
  direct repair reveals a different shared or family regression, split it into
  its own gap instead of broadening this one.

### New Decisions In This Slice

- Treat the currently selected gap as a regression reopen of the selector
  adapter call contract, with its own target path and output evidence.
- Keep selector projection duplication in place for this slice. Reusing
  `stdlib_payloads::project-selection-result` may be considered later, but it
  is not required to close this regression.
- Make the implementation acceptance center on parent Design Delta compile and
  build-artifact evidence for the imported selector carried context.

### Conflicts Or Revisions

No prior architecture decision is revised.

The current checkout conflicts with the accepted target because
`select-next-work-stdlib` still calls a removed flattened selector boundary.
This slice resolves that conflict by aligning the family adapter to the
already accepted single-`ctx` selector boundary.

No shared concepts such as spans, diagnostics, Core Workflow AST, Semantic
Workflow IR, TypeCatalog, SourceMap, pointer authority, variant proof,
resource transition, or command adapter certification are redefined here.

## Current Checkout Facts

- `workflows/library/lisp_frontend_design_delta/selector.orc` defines
  `select-next-work ((ctx DesignDeltaDrainCtx)) -> SelectorPublicResult`.
- `selector.orc` builds `SelectorInputs`, `SelectorPromptSubject`, and
  `SelectorRequest` from `ctx`, then invokes `provider-result` with
  `:inputs (request)`.
- `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc` defines
  `select-next-work-stdlib ((ctx DesignDeltaDrainCtx)) ->
  DesignDeltaSelectionResult`, but its internal call to `select-next-work`
  still passes flattened keyword arguments.
- `workflows/library/lisp_frontend_design_delta/drain.orc` passes
  `select-next-work-stdlib` as the `:selector` workflow ref to imported
  `std/drain::backlog-drain`.
- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc` calls selector
  workflow refs only as `(call selector :ctx ctx)`.
- `workflows/library/lisp_frontend_design_delta/types.orc` defines the target
  `DesignDeltaSelectionResult` union with `EMPTY`, `GAP`, `SELECTED`, and
  `BLOCKED` variants.
- `tests/test_workflow_lisp_build_artifacts.py` contains focused carried
  context evidence for
  `lisp_frontend_design_delta/stdlib_adapters::select-next-work-stdlib`.
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
  contains the parent route checks that should pass once the stale call no
  longer fails typechecking.

## Feasibility Proof

The slice is feasible without new language, runtime, or compiler work:

1. The callee and adapter already agree on the semantic context type:
   `DesignDeltaDrainCtx`.
2. Imported `std/drain::backlog-drain` already calls selector workflow refs
   with a single `:ctx` argument.
3. Existing Workflow Lisp call validation should accept
   `(call select-next-work :ctx ctx)` because it matches the callee boundary.
4. The existing projection in `select-next-work-stdlib` can continue to
   construct `DesignDeltaSelectedItemPayload`, `DesignDeltaGapPayload`, and
   `DesignDeltaSelectionResult` from the returned `SelectorPublicResult`.
5. No command boundary, report parser, pointer file, or compatibility bundle is
   needed to transport the selector result.

If `(call select-next-work :ctx ctx)` still fails after the call-site repair,
that failure is a separate typecheck, module-resolution, or WCC regression. The
implementation must record the new diagnostic and split it rather than hiding
it inside this slice.

## Owned Components

This slice owns:

- `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc`
  - replace the stale flat `select-next-work` call with `:ctx ctx`;
  - keep `select-next-work-stdlib` exported under the same name;
  - keep its input and output types unchanged; and
  - keep projection behavior equivalent for `SELECTED`, `GAP`, `EMPTY`, and
    `BLOCKED`.
- Focused regression tests in:
  - `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`;
  - `tests/test_workflow_lisp_build_artifacts.py`.
- Runtime fixture mirrors only if a checked mirror copies
  `stdlib_adapters.orc` and must stay byte-aligned.

This slice intentionally does not own:

- `orchestrator/workflow_lisp/typecheck_calls.py`;
- `orchestrator/workflow_lisp/typecheck_dispatch.py`;
- `orchestrator/workflow_lisp/lowering/phase_drain.py`;
- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`;
- `workflows/library/lisp_frontend_design_delta/selector.orc`, except as the
  callee contract being consumed;
- provider externs, prompt externs, command-boundary manifests, or certified
  adapters;
- source-map, Semantic IR, executable IR, resource transition, or runtime
  semantics; or
- migration parity promotion and YAML-primary selection.

## Implementation Shape

Change only the selector call inside `select-next-work-stdlib`:

```lisp
(let* ((selection
         (call select-next-work
           :ctx ctx))
       ...)
  ...)
```

The existing projection can remain in place:

- `selection.work_item_bootstrap` continues to populate
  `DesignDeltaSelectedItemPayload`;
- `selection.work_item_bootstrap` continues to populate
  `DesignDeltaGapPayload`;
- `selection.is_selected`, `selection.is_design_gap`, and
  `selection.is_done` continue to route the family selection union; and
- `selection.blocked_reason` continues to feed the `BLOCKED` variant.

The direct call-site correction is preferred because it fixes the regression in
one family-owned workflow file. It makes selector projection de-duplication
harder later only in the sense that the duplicate projection remains until a
separate cleanup selects it deliberately.

## Data And Control Flow

1. `drain.orc` constructs `DesignDeltaDrainCtx`.
2. `drain.orc` calls imported `std/drain::backlog-drain` with
   `:selector select-next-work-stdlib`.
3. `std/drain::backlog-drain` calls the selector workflow ref as `:ctx ctx`.
4. `select-next-work-stdlib` calls `select-next-work :ctx ctx`.
5. `select-next-work` renders the typed selector request and returns
   `SelectorPublicResult`.
6. `select-next-work-stdlib` projects that typed result into
   `DesignDeltaSelectionResult`.
7. Imported `backlog-drain` consumes `DesignDeltaSelectionResult` through
   ordinary typed matching and routes `EMPTY`, `GAP`, `SELECTED`, and
   `BLOCKED`.

No rendered report, pointer file, stdout payload, command output, or
compatibility JSON bundle participates in this routing decision.

## Source Maps And Boundary Evidence

The repaired route must preserve existing evidence:

- `select-next-work-stdlib` remains a callable workflow bundle with one private
  carried `ctx` context binding;
- the binding records `context_family = "DrainCtx"` and
  `bridge_class = "imported_adapter_carried_context"`;
- generated context input roles continue to map `ctx.run.run-id`,
  `ctx.run.state-root`, and `ctx.run.artifact-root` to runtime anchors;
- carried input sources continue to explain the fields projected from `ctx`;
- `ctx__run_state_path` remains private carried context or compatibility
  evidence, not a public authored selector input; and
- source-map provenance points to the `stdlib_adapters.orc` typed call, not to
  generated command glue or a compatibility side channel.

## Command Adapter Policy

No command adapter is proposed.

If implementation touches command-boundary manifests or scripts while repairing
this gap, it has left the selected scope. `docs/design/workflow_command_adapter_contract.md`
is authoritative for any such accidental adjacent work: a command boundary that
carries workflow semantics must be certified with typed inputs, typed outputs,
declared effects, path-safety expectations, fixtures, negative fixtures,
source-map behavior, owner module, and retirement path.

For this slice, adding inline Python, shell, report parsing, pointer-state
reads, stdout JSON, or a helper script would violate the target design.

## Verification Strategy

Minimum deterministic checks for the implementation slice:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_parent_drain_entrypoint_adopts_stdlib_owner_routes -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_artifacts_record_imported_selector_carried_context -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_parent_drain_imported_selector_ctx_carried_context_smoke -q
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
```

Expected evidence:

- compile no longer fails in `stdlib_adapters.orc` on stale flat bindings such
  as `steering`;
- `select-next-work-stdlib` still has a single private carried `ctx` context
  binding in build artifacts;
- the parent drain route reaches imported `std/drain::backlog-drain` with
  `select-next-work-stdlib` as the selector workflow ref;
- selector prompt request rendering remains owned by `selector.orc`; and
- no new command-boundary row, compatibility bundle, report parser, pointer
  sidecar, or public path-threading parameter is introduced.

## Acceptance Conditions

This slice is complete when:

- `select-next-work-stdlib` calls `select-next-work` with exactly `:ctx ctx`;
- `select-next-work-stdlib` keeps its public workflow-ref shape as
  `((ctx DesignDeltaDrainCtx)) -> DesignDeltaSelectionResult`;
- the parent Design Delta drain compiles through the imported
  `std/drain::backlog-drain` route without the stale selector
  `workflow_signature_mismatch`;
- build artifacts still record imported selector carried-context evidence for
  `select-next-work-stdlib`;
- the selector result projection preserves the `EMPTY`, `GAP`, `SELECTED`, and
  `BLOCKED` routes; and
- no compiler special case, widened workflow-ref arity, command adapter,
  script, report parser, pointer file, stdout JSON, or compatibility-bundle
  reread is needed to make the route compile.

## Implementation Handoff

The later implementation plan should:

1. add or confirm a failing regression check for the stale flat selector call;
2. update `select-next-work-stdlib` to call `select-next-work :ctx ctx`;
3. rerun the focused parent Design Delta compile and carried-context build
   artifact selectors;
4. run the explicit `orchestrator compile` command for the Design Delta parent
   route with the checked provider, prompt, and command-boundary externs; and
5. stop before refactoring projection duplication, changing `std/drain`,
   altering compiler/typechecker behavior, or touching command-boundary
   certification.

