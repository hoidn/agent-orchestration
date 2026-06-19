# Workflow Lisp Runtime-Native Drain Gap-Drafter Callable-Boundary Over Imported `backlog-drain` Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-runtime-native-drain-gap-drafter-callable-boundary-over-imported-backlog-drain`
Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the shared prerequisite named in
`docs/design/workflow_lisp_runtime_native_drain_authoring.md`
Section 9.1.2:

- prove that imported `std/drain/backlog-drain` can carry a typed selector
  `GAP` payload across the fixed `gap-drafter` workflow-ref boundary;
- keep that boundary fixed to `DrainCtx` plus one typed gap payload record;
- generalize the shared lowering route so payload carriage is record-shaped and
  not hardcoded to one field name; and
- make the proof machine-visible in the shared stdlib verification lane so the
  later Design Delta stdlib-adoption slice can cite it directly.

This slice is intentionally bounded to shared lowering, shared proof fixtures,
and shared verification/reporting for the fixed `gap-drafter` boundary.

Out of scope for this slice:

- rewriting `workflows/library/lisp_frontend_design_delta/drain.orc`,
  `work_item.orc`, `selector.orc`, `stdlib_adapters.orc`, or
  `design_gap_architect.orc` as a family-adoption effort;
- widening the imported `backlog-drain` `gap-drafter` arity;
- changing the accepted shared parent-loop semantics, the callable child-owner
  boundary, or the later parent terminal reprojection contract;
- changing the shared `run-item` workflow-ref shape or the child-phase
  `PhaseCtx` transport prerequisites;
- redesigning typed provider request records, typed bootstrap projection,
  entry-boundary publication, domain transitions, or `std/phase` ownership;
- introducing compatibility-bundle rereads, placeholder carriers, new scripts,
  inline command glue, report parsing, or pointer-state authority; and
- claiming YAML-primary promotion.

This is an implementation architecture for one bounded shared prerequisite. It
does not replace the parent runtime-native drain design or the accepted
Workflow Lisp baseline.

## Problem Statement

The shared imported `backlog-drain` route already proves adjacent facts:

1. parent workflows can lower `(backlog-drain ...)` as one call to
   `std/drain::backlog-drain`;
2. the callable child owner boundary preserves the accepted parent-loop
   contract;
3. later parent workflows may reproject the stdlib terminal result after the
   child call returns; and
4. the shared stdlib lane already has focused fixtures for selector blocking,
   selected-item continue re-entry, and terminal finalization parity.

Those facts are necessary, but they do not yet satisfy the stricter
gap-drafter prerequisite named in the target design. What is still missing is
one explicit shared owner-lane proof that:

- selector-produced `GAP` payload fields can cross the imported
  `backlog-drain` child route without widening the fixed `gap-drafter`
  boundary;
- payload carriage is generic over the declared record shape rather than
  hardcoded to a one-field `gap-id` protocol;
- the proof route stays on ordinary typed workflow-call lowering with source
  maps, hidden bindings, and route identity intact; and
- later families do not need wrapper workflows whose only purpose is to smuggle
  selector-produced gap fields across the fixed boundary.

Current checkout facts show the gap precisely:

- `orchestrator/workflow_lisp/lowering/phase_drain.py` already flattens the
  selected-item payload generically via `_flatten_boundary_leaf_paths(...)`,
  but it still hardcodes the gap payload as:
  `{"gap-id": "self.steps.<selector>.artifacts.return__gap__gap-id"}`.
- `tests/test_workflow_lisp_drain_stdlib.py` currently asserts that the child
  `gap-drafter` call binds only `gap__gap-id`; there is no shared positive
  proof for a richer typed payload.
- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc` keeps the authored
  boundary fixed to `(ctx DrainCtx)` plus `(gap GapPayload)`, which is correct,
  but the shared proof lane only exercises a minimal one-field payload.
- the Design Delta family already models a richer gap carrier in
  `workflows/library/lisp_frontend_design_delta/types.orc`:
  `DesignDeltaGapPayload` carries `work_item_id`, `plan_target_path`, and
  `architecture_path`;
- the Design Delta family already routes that richer payload into
  `draft-design-gap-stdlib`, but that family-local route is not the required
  shared owner-lane proof for imported `backlog-drain`.

The missing capability is therefore narrow and concrete: shared generic
gap-payload carriage over the fixed `gap-drafter` boundary.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
  Sections 2.1, 7.7, 8.1-8.3, 9.1.2, 10, 11, 13.4, 14, 15, 16, and 18;
- `docs/design/workflow_lisp_frontend_specification.md`
  Sections 7.4-7.5, 11, 14-17, 29, 31, 44.1, 45-48, 56-59, 61-66, 74, 86-87,
  95, 97, and 104-105;
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`;
- `docs/design/workflow_command_adapter_contract.md`;
- `docs/workflow_lisp_g6_verification_gate.json`;
- `docs/capability_status_matrix.md`; and
- the reviewed prior implementation architectures listed in the generated
  index.

Guardrails:

- keep the imported `gap-drafter` boundary fixed to exactly two parameters:
  `DrainCtx` and one typed gap payload record;
- use typed workflow-call lowering and record projection, not scripts,
  compatibility bundles, stdout parsing, or report parsing;
- preserve the callable imported `backlog-drain` owner split:
  parent owns one call, child owns loop control;
- preserve source maps, generated hidden-input provenance, managed write roots,
  and ordinary route identity on the promoted WCC/schema-2 route;
- keep later family adoption work separate; this slice must not depend on a
  Design Delta-only wrapper to count as shared proof; and
- keep any surviving command boundary, such as
  `validate_lisp_frontend_design_gap_architecture.py`, governed by the command
  adapter contract rather than turning payload carriage into a new hidden file
  protocol.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

From the generated architecture index for this body of work:

- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-backlog-drain-finalize-selected-item-adoption/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-callable-imported-backlog-drain-boundary/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-callable-imported-backlog-drain-parent-loop-parity/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-callable-imported-backlog-drain-terminal-finalization-parity/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-called-workflow-result-branching-terminal-reprojection/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-domain-transition-operations/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-entry-boundary-publication-adoption/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-item-context-first-child-phase-reuse/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-parent-terminal-reprojection-over-imported-backlog-drain/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-shared-phase-family-boundary-prerequisite/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-shared-std-phase-owner-lane-self-hosting-prerequisite/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-stdlib-backlog-drain-parent-loop-contract/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-typed-provider-request-records/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-work-item-bootstrap-typed-projection/implementation_architecture.md`

Cross-body design docs reviewed and reused here:

- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- `docs/design/workflow_lisp_runtime_native_drain_authoring.md`

### Decisions Reused

- Reuse the callable imported `backlog-drain` boundary slice's decision that
  promoted parent workflows own one call to `std/drain::backlog-drain` while
  the loop body remains in the child owner boundary.
- Reuse the callable parent-loop parity slice's decision that shared drain
  routing semantics are proved by inspecting the child owner boundary, not by
  recreating parent-local loops or wrappers.
- Reuse the parent terminal reprojection slice's decision that any distinct
  family/public terminal union stays caller-owned and happens only after the
  stdlib result exists as an ordinary bound value.
- Reuse the item-context-first child-phase reuse, shared phase-family
  prerequisite, called-workflow nested-branch prerequisite, and shared
  `std/phase` self-hosting prerequisite as adjacent but separate owner-lane
  work. This slice does not redesign private context transport, nested
  finalizer proof, or imported phase helper ownership.
- Reuse the typed provider request-record, typed bootstrap projection,
  entry-boundary publication, and domain-transition slices as fixed consumers.
  This slice does not reopen prompt-subject shape, bootstrap authority, summary
  publication, or durable mutation.
- Reuse the command-adapter contract's rule that missing workflow semantics
  must move to typed workflow structure or runtime-native/shared lowering, not
  to hidden helper scripts or uncertified adapters.

### New Decisions In This Slice

- Treat the fixed `gap-drafter` callable-boundary proof as its own shared
  prerequisite after callable child-boundary preservation and parent-loop
  parity; it is not implied by those earlier proofs.
- Replace the current hardcoded `gap-id` projection with generic record-leaf
  carriage for the selector `GAP` payload, parallel to the already generic
  selected-item payload route.
- Keep the proof boundary fixed to `DrainCtx + gap payload`. Richer payload
  carriage must happen through typed record fields on that second parameter, not
  through widened arity, public path threading, or compatibility rereads.
- Require one focused positive shared fixture whose selector `GAP` payload has
  more than one semantic field, and whose `gap-drafter` call consumes that
  payload through imported `backlog-drain` on the promoted route.
- Keep later Design Delta family wrappers as downstream consumers only. They
  may continue to exist during migration, but they do not count as the shared
  owner-lane proof for this slice.

### Conflicts Or Revisions

- The earlier callable imported `backlog-drain` boundary and parent-loop parity
  slices assumed the fixed `gap-drafter` boundary would follow the same shared
  route as selector and run-item calls. This slice narrows that assumption into
  an explicit proof obligation because the current lowering still hardcodes the
  payload shape.
- The later backlog-drain / finalize-selected-item adoption architecture named
  this exact prerequisite in advance. This slice supplies the missing shared
  owner-lane proof and therefore continues to block family adoption until it
  lands.
- No shared concepts such as spans, diagnostics, Core Workflow AST, Semantic
  IR, TypeCatalog, SourceMap, pointer authority, or variant proof are
  redefined here.

## Current Checkout Facts

- `orchestrator/workflow_lisp/lowering/phase_drain.py`:
  - flattens the selected-item payload generically by walking the declared
    record type; but
  - still constructs `gap_value` from exactly one field,
    `return__gap__gap-id`, before calling `_build_call_bindings_from_record_value(...)`.
- `tests/test_workflow_lisp_drain_stdlib.py`:
  - asserts the child `gap-drafter` call binds only `gap__gap-id`;
  - has positive callable-boundary and parent-loop parity proof for the child
    route; but
  - does not contain a positive proof for a richer selector `GAP` payload.
- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`:
  - keeps the authored `gap-drafter` call shape fixed to `(call gap-drafter
    :ctx ctx :gap gap_case.gap)` in the inline-compat macro; and
  - delegates the promoted route to `backlog-drain-callable-boundary`.
- `workflows/library/lisp_frontend_design_delta/types.orc` defines
  `DesignDeltaGapPayload` with:
  - `work_item_id`;
  - `plan_target_path`; and
  - `architecture_path`.
- `workflows/library/lisp_frontend_design_delta/stdlib_payloads.orc` already
  projects a selector result into that richer `DesignDeltaGapPayload`.
- `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc` already
  defines `draft-design-gap-stdlib ((ctx DesignDeltaDrainCtx) (gap
  DesignDeltaGapPayload)) -> DesignDeltaGapResult`, which shows the family-side
  consumer shape the shared owner lane must eventually support.
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
  already proves downstream Design Delta routes that reach design-gap drafting,
  but those assertions inspect family lowering and downstream architect calls.
  They do not replace a shared stdlib proof that imported `backlog-drain`
  generically carries a rich `GAP` payload.

## Feasibility Proof

This slice is feasible because the required pieces already exist in bounded
form:

1. The lowerer already has the generic record-leaf machinery needed for this
   route:
   `_flatten_boundary_leaf_paths(...)` plus
   `_build_call_bindings_from_record_value(...)` already carry the selected-item
   payload without hardcoded field names.
2. The callable imported `backlog-drain` child boundary already exists on the
   promoted WCC/schema-2 route, with managed write roots, source maps, hidden
   inputs, and one child owner boundary that tests can inspect.
3. The shared stdlib test lane already proves adjacent properties of the same
   child route: loop ownership, selector/provider rebinding, selector-blocked
   routing, selected-item continue re-entry, and terminal finalization.
4. The target family already provides a realistic richer consumer payload in
   `DesignDeltaGapPayload`, so the shared proof can be grounded in an actual
   downstream need without widening family scope.
5. The command-adapter contract already permits command-backed design-gap
   validation where needed; this slice only changes typed payload carriage to
   that existing command boundary, not the command boundary itself.

The remaining work is therefore not a new runtime surface. It is one generic
lowering correction plus one focused owner-lane proof.

## Ownership Boundaries

This slice owns:

- shared lowering changes in
  `orchestrator/workflow_lisp/lowering/phase_drain.py` needed to make selector
  `GAP` payload carriage generic over the declared record shape;
- any narrowly coupled shared call-type or lowering metadata changes required
  to preserve source maps, hidden bindings, and route identity for that
  payload;
- one focused positive shared proof fixture for richer `GAP` payload carriage;
- any paired negative fixtures or assertions needed to keep the fixed
  boundary sharp; and
- counted shared verification/gate wording updates if the shared proof lane
  needs an explicit new selector.

This slice intentionally does not own:

- production Design Delta `.orc` rewrites onto imported stdlib surfaces;
- shared parent-loop semantics already owned by `std/drain`;
- later parent terminal reprojection;
- fixed `run-item` workflow-ref shape or child `PhaseCtx` transport;
- `std/phase` ownership or self-hosting;
- boundary publication, typed request-record, or bootstrap redesign;
- new scripts, adapters, or runtime-native transition semantics; or
- YAML-primary promotion.

## Proposed Component Architecture

### 1. Generalize `GAP` Payload Projection In Shared Lowering

Replace the current one-field `gap_value` construction with the same record
projection model already used for `selection`.

Implementation direction:

- resolve the selector's `GAP` variant payload as a record-typed value;
- derive leaf refs from `self.steps.<selector>.artifacts.return__gap__...` for
  every declared field path in that record;
- build the second `gap-drafter` argument from those leaf refs through
  `_build_call_bindings_from_record_value(...)`; and
- keep the gap-drafter signature fixed to one record payload parameter.

This preserves the accepted authoring surface:

```lisp
(defworkflow gap-draft
  ((ctx DrainCtx)
   (gap GapPayload))
  -> GapResult
  ...)
```

The fix is specifically about how the shared lowerer carries the typed value to
that boundary, not about changing the boundary itself.

### 2. Add One Focused Positive Shared Proof Fixture

Add a shared stdlib fixture whose selector `GAP` variant carries a richer
record payload and whose `gap-drafter` consumes that payload through imported
`backlog-drain`.

Required proof shape:

- parent workflow imports `std/drain/backlog-drain`;
- parent lowers to one call to `std/drain::backlog-drain`;
- selector returns a `GAP` variant whose payload record has at least one field
  beyond a single id;
- child owner-boundary lowering binds every payload field onto the fixed
  `gap-drafter` `:gap` parameter; and
- no widened `gap-drafter` signature, compatibility-bundle reread, or wrapper
  workflow is needed to make the call compile.

The proof fixture should stay shared and generic. It may use field names that
mirror the downstream need, such as:

- `work-item-id`
- `plan-target-path`
- `architecture-path`

but it must remain a shared stdlib proof surface, not a Design Delta-only
production workflow.

### 3. Keep The Negative Boundary Sharp

The owner-lane proof must fail closed when a caller tries to bypass the fixed
boundary.

Negative cases to preserve or add:

- a `gap-drafter` workflow whose second parameter is not a record still fails
  with the existing stable signature diagnostic;
- selector/gap payload ambiguity across imported bundles still fails rather
  than guessing a carrier type; and
- no test or helper may count a family-local payload-smuggling wrapper,
  placeholder carrier, or compatibility-bundle reread as satisfying the shared
  prerequisite.

This slice should not invent new diagnostics if the existing workflow-signature
or type errors already describe the failure accurately.

### 4. Make The Shared Proof Discoverable To Downstream Family Adoption

The later Design Delta stdlib-adoption slice must be able to cite this shared
proof directly.

Implementation consequences:

- keep the positive proof in `tests/test_workflow_lisp_drain_stdlib.py` or a
  directly adjacent shared stdlib proof file;
- if `docs/workflow_lisp_g6_verification_gate.json` or a nearby counted-suite
  manifest needs wording changes, make them additive and route-specific;
- keep downstream Design Delta feasibility tests as consumers only:
  they may be rerun for regression confidence, but they must not become the
  primary owner-lane proof for this gap.

## Verification Strategy

Focused shared verification for this selected gap should include:

- compile/shared-validation of the new positive richer-gap-payload fixture on
  the promoted WCC/schema-2 route;
- lowered-child inspection proving the `gap-drafter` call binds every declared
  `GAP` payload field, not only `gap-id`;
- re-run of the existing callable imported `backlog-drain` boundary selector,
  so the one-call parent / child-owner split remains intact;
- re-run of the existing callable parent-loop parity selector, so the richer
  payload change does not regress loop ownership or terminal routing; and
- one focused downstream Design Delta compile selector, only for regression
  confidence that the shared route still supports the family's imported
  stdlib candidate without introducing family-local payload smuggling.

If the counted shared verification manifest changes, validate the JSON and keep
the reason text explicit that this is the fixed `gap-drafter` callable-boundary
proof, not a broader family-adoption claim.

## Acceptance Conditions

This slice is complete when:

- imported `backlog-drain` can carry a selector-produced typed `GAP` payload
  with more than one semantic field across the fixed `gap-drafter` boundary;
- the shared lowering route is generic over the declared record shape instead
  of hardcoded to `gap-id`;
- the proof route preserves the accepted owner split:
  parent owns one call, child owns loop control;
- the proof route preserves source maps, hidden-input provenance, and managed
  write-root behavior for the generated child call;
- no widened `gap-drafter` arity, public path threading,
  compatibility-bundle reread, or family-local payload-smuggling wrapper is
  needed to satisfy the proof; and
- the later backlog-drain / finalize-selected-item adoption slice can cite a
  shared owner-lane proof for the reachable `GAP` branch instead of reopening
  this missing substrate in family scope.

## Implementation Handoff

The later implementation plan for this slice should:

1. add one failing shared stdlib proof fixture with a richer selector `GAP`
   payload and a fixed-shape `gap-drafter`;
2. generalize the shared `GAP` payload binding path in
   `orchestrator/workflow_lisp/lowering/phase_drain.py`;
3. add lowered-child assertions that every payload leaf is bound onto the
   `gap-drafter` call;
4. keep or add narrow negative coverage for non-record or ambiguous gap
   payloads;
5. rerun the existing callable-boundary and parent-loop-parity selectors plus
   one downstream Design Delta compile selector; and
6. stop before the later Design Delta family-adoption rewrite. That consumer
   slice remains separate and should only consume the shared proof once it
   exists.
