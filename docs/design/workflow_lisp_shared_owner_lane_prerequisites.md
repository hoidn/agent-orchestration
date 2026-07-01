# Workflow Lisp Shared Owner-Lane Prerequisites

Status: reference target / prerequisite ledger
Kind: shared capability contracts gating imported stdlib adoption claims
Created: 2026-07-01
Scope: shared stdlib/compiler/runtime capability contracts that must exist
before a parent-callable workflow family may claim imported `std/drain`,
`std/phase`, or `std/resource` adoption; each prerequisite states a minimum
contract, a minimum behavior check, and an adoption-claim rule.

Current implementation status is tracked in
`docs/capability_status_matrix.md`. This document defines prerequisite
contracts and checks; it is not live completion state.

Authority:

- Normative runtime and DSL behavior remains in `specs/`.
- `docs/design/workflow_lisp_runtime_native_drain_authoring.md` owns the
  runtime-native drain authoring target, its invariants, and the Design Delta
  reference-family acceptance; this ledger owns the shared owner-lane
  prerequisites that document's adoption claims depend on.
- `docs/design/workflow_lisp_frontend_specification.md` owns the parent
  Workflow Lisp language contract and WCC lowering route.
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  owns parent-callable workflow-family migration and promotion gates.
- This document does not by itself promote any `.orc` workflow to primary
  surface.

Related docs:

- `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- `docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md`
- `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`
- `docs/lisp_workflow_drafting_guide.md`

## 1. How To Read This Ledger

Each prerequisite section states:

- the minimum contract the shared owner lane must provide;
- the minimum behavior check that demonstrates the contract; and
- the adoption-claim rule that applies while the contract is missing.

The adoption-claim rule is uniform. A family may adopt request-record,
projection, transition, publication, and cleanup slices that do not depend on
a missing prerequisite. It must not claim imported stdlib adoption by
re-implementing missing owner-lane behavior in family-local adapters, wrapper
workflows, widened boundaries, or compatibility rereads. When a slice hits a
missing prerequisite, the correct move is to stop the slice and select the
prerequisite gap.

These prerequisites were extracted, with renumbering and with workaround
details consolidated from the former Section 16 mirror bullets, from
Section 9 of `docs/design/workflow_lisp_runtime_native_drain_authoring.md`.
Former section numbers map as follows:

| Former section | This document |
| --- | --- |
| 9.1 | 2 |
| 9.1.0 | 2.1 |
| 9.1.0.1 | 2.1.1 |
| 9.1.1 | 2.2 |
| 9.1.1.1 | 2.2.1 |
| 9.1.2 | 2.3 |
| 9.1.2.1 | 2.3.1 |
| 9.1.3 | 2.4 |
| 9.2 | 3 |
| 9.2.1 | 3.1 |
| 9.2.2 | 3.2 |
| 9.2.3 | 3.3 |
| 9.2.4 | 3.4 |
| 9.2.5 | 3.5 |
| 9.3 | 4 |

## 2. Shared Parent-Loop Prerequisite

For any parent-callable family that intends to replace a handwritten
select/run/gap/repeat loop with imported `std/drain/backlog-drain`, the shared
stdlib owner lane must already support the parent's required routing semantics.
The minimum contract is:

- `SelectedItemResult.CONTINUE` may re-enter selection instead of forcing
  immediate terminal completion;
- direct selector-blocked outcomes are representable as typed terminal routing;
- gap work or blocked-recovery work may return control to selection when the
  family semantics require it; and
- typed iteration/accounting remains valid across repeated selected-item passes
  and authored exhaustion.

Until that shared contract exists, a family may still adopt request-record,
projection, transition, and publication slices, but it must not
claim imported `backlog-drain` adoption by re-implementing missing parent-loop
behavior in family-local adapters or handwritten compatibility wrappers.

### 2.1 Callable-Child Value Return Over Imported `backlog-drain`

For families whose promoted route preserves imported `std/drain::backlog-drain`
as a callable owner boundary, the shared parent/drain owner lane must first
support ordinary typed child value return. A simple call to imported
`backlog-drain` should return `DrainResult<TSummary>` to the parent without
requiring terminal publication, summary materialization, run-state-file
mutation, or drain-outcome recording as part of value return.

The minimum contract is:

- the parent workflow may preserve loop delegation as one call to imported
  `backlog-drain` while the child owner boundary still owns the `repeat_until`
  loop and its typed accumulator;
- the child route may materialize terminal classification from carried loop
  state and return the typed terminal `DrainResult` without falling back
  to stale direct `EmitDrain*`-style normalization or caller-owned terminal
  fan-in;
- optional terminal effects such as `record-drain-outcome`, public
  publication, audit projection, or external resource mutation are expressed as
  explicit boundary/resource forms outside the core `backlog-drain`
  value-return contract;
- shared validation accepts the loop-frame refs, nested-step refs, and
  exhaustion-carried terminal fields required by that route, with authored
  exhaustion staying within the accepted `repeat_until` output constraints
  rather than reopening ad hoc non-scalar terminal overrides; and
- the route does not depend on family-local wrappers, same-file-only special
  cases, compiler-name allowlists, rereading compatibility bundles, or
  compatibility-only marker steps to manufacture the returned value.

The minimum behavior check for this contract is:

- one compile/shared-validation fixture where the parent route lowers to one
  call to imported `backlog-drain` and the child owner boundary both owns the
  loop and returns a typed `DrainResult`;
- one runtime or smoke fixture showing that empty, completed, blocked, and
  exhausted callable-child terminals return the same typed result shape through
  ordinary child-call value return; and
- a positive check that the accepted route works for both imported and
  same-file promoted-callable `backlog-drain` authoring shapes without
  reopening handwritten terminal normalization.

If a family still needs durable terminal effects, those effects are separate:

- `:publish` materializes public terminal summaries from the returned typed
  value;
- a named domain transition records external resource state when there is a
  real external resource to mutate; and
- helpers such as `record-drain-outcome` are not prerequisites for returning
  `DrainResult<TSummary>`.

Until that route works, a family may still adopt request-record, projection,
transition, and publication slices, but it must not claim full
imported `backlog-drain` adoption on the callable owner-boundary route when the
child terminal value path still depends on compatibility-only normalization,
run-state-file side effects, or family-local repair wrappers.

#### 2.1.1 Terminal Responsibility Split

Do not use "terminal finalization" as a bundled mechanism. The target model
separates four lanes:

- child-call value return: imported `backlog-drain` returns
  `DrainResult<TSummary>` as an ordinary typed child-workflow value;
- variant/provenance preservation: refined match binders, `requires_variant`
  provenance, source maps, and variant-scoped contracts survive child calls and
  terminal reprojection;
- declared terminal effects: publication, resource transition, adapter calls,
  or external audit events run only when explicitly declared by a
  boundary/resource contract; and
- migration checks compare public behavior, typed terminal results, declared
  resource effects, artifacts, and resume/reuse behavior without becoming
  internal authoring semantics.

Pure helpers, effectful procedures, and workflow entrypoints share the same
typed return-value model. A `defworkflow` is special because it is an
executable/resumable boundary with declared effects and runtime state, not
because return values are transported through publication or
terminal-finalization machinery.

Any proposed `record-drain-outcome`-style helper must first answer which
consumer it serves:

- parent workflow: use the returned typed value directly;
- public report or dashboard: use publication policy;
- legacy YAML-era reader: use bridge metadata with owner, schema, consumer, and
  retirement condition;
- durable domain/resource state: use a typed resource transition; or
- resume: use runtime-owned checkpoint state, not authored drain bookkeeping.

If no consumer fits one of those cases, the helper is migration debt and must
not be required for `DrainResult<TSummary>` return.

### 2.2 Parent Terminal Reprojection Over Imported `backlog-drain`

For families whose public or parity-constrained terminal boundary still differs
from stdlib `DrainResult`, the shared parent-loop lane must also support one
accepted terminal reprojection route. When the family/public boundary also
omits or renames a child terminal field that exists on the imported stdlib
result, Section 2.2.1 is a separate narrower prerequisite inside this lane.
The minimum contract is:

- a parent workflow may place imported `backlog-drain` either as the terminal
  workflow body expression or as the input to one ordinary typed terminal
  projection step that remains on the supported WCC/schema-2 route;
- that projection may inspect the returned stdlib union through ordinary
  refined `match` and construct the family/public terminal union without
  reintroducing a handwritten select/run/gap loop, handwritten terminal fan-in,
  or compatibility-script routing;
- source maps and variant provenance remain attached to both the imported
  `backlog-drain` result and the projected terminal result; and
- the accepted route does not depend on nesting imported `backlog-drain`
  inside unsupported local-control positions whose only purpose is terminal
  post-projection.

The minimum behavior check for this contract is a compile/shared-validation
fixture that exercises this exact shape:

- imported `backlog-drain` on the parent route;
- ordinary typed terminal reprojection to a family/public union or boundary
  publication policy;
- no handwritten parent loop or handwritten drain-terminal compatibility path;
  and
- preserved source-map provenance for the projected terminal result.

Until that route works, a family may still adopt request-record, projection,
transition, and publication slices, but it must not claim full
imported `backlog-drain` adoption when the only remaining route depends on
unsupported local-control nesting or a restored handwritten terminal fan-in.

#### 2.2.1 Branch-Local Terminal Contract Alignment

For families whose public or parity-constrained terminal boundary omits,
renames, or otherwise does not preserve every imported stdlib terminal field
verbatim, the shared parent/drain owner lane must also support one accepted
branch-local contract-alignment route before the broader parent terminal
reprojection claim counts as satisfied.

The minimum contract is:

- a parent workflow may `match` the imported stdlib `DrainResult`, consume a
  branch-local child field such as `blocker-class`, carried typed data, or a
  stdlib-only classification payload, and then construct the family/public
  terminal result without re-exporting that field verbatim;
- the family/public terminal union does not need to mirror every stdlib child
  field name or carry every child-only field as a public output, provided the
  projection uses those fields through ordinary typed/proved bindings while the
  imported variant scope is still active;
- source maps, `requires_variant` provenance, and executable contract lineage
  remain attached from the imported stdlib result
  through that branch-local field consumption and into the projected terminal
  value or boundary publication; and
- the accepted route does not depend on widening the family/public boundary
  solely to echo stdlib child fields, on same-file-only terminal
  normalization, on family-local wrapper workflows, on handwritten
  drain-terminal fan-in, or on compatibility-bundle rereads to recover a
  dropped field.

The minimum behavior check for this contract is:

- one compile/shared-validation fixture where imported `backlog-drain` reaches
  a nontrivial terminal variant whose payload includes at least one field not
  preserved verbatim by the family/public boundary;
- one ordinary typed `match` route where the parent consumes that field and
  produces the family/public terminal union or publication policy result
  without adding the child field to the public boundary just for transport; and
- preserved source-map provenance for both the imported child result and the
  projected parent terminal value.

Until that route works, a family may not treat a simpler terminal
reprojection fixture as sufficient when its actual public/parity boundary still
depends on consuming a stdlib child field that is omitted or renamed at the
family boundary.

### 2.3 Gap-Drafter Callable-Boundary Over Imported `backlog-drain`

For families whose imported `backlog-drain` route can reach the selector
`GAP` branch, the shared parent/drain owner lane must also support one accepted
callable-boundary route for the fixed `gap-drafter` workflow-ref surface. The
minimum contract is:

- imported `backlog-drain` keeps the `gap-drafter` boundary fixed to
  `DrainCtx` plus the stdlib selector gap payload;
- a family must not satisfy that boundary by widening the imported
  `gap-drafter` arity, by flattening the typed gap payload into public or
  path-heavy parameters, or by reopening handwritten parent routing around the
  gap lane;
- when selector output or loop-frame state carries a typed gap payload, the
  `gap-drafter` child call may bind that payload through the ordinary
  WCC/schema-2 callable-boundary route using workflow inputs or prior outputs
  from the imported route, rather than requiring family-local rereads or
  compatibility bundles to reconstruct the payload;
- selector and `gap-drafter` failures diagnose the authored call boundary rather
  than a generated branch name; and
- the accepted route does not depend on family-local wrapper or projector
  workflows whose only purpose is to smuggle selector-produced gap fields
  across the fixed `gap-drafter` boundary, nor on fabricated placeholder
  carriers.

The minimum behavior check for this contract is a compile/shared-validation
fixture that exercises this exact shape:

- imported `backlog-drain` on the parent route;
- selector `GAP` output with a typed gap payload whose carried fields flow from
  selector output or loop-frame outputs on the imported route;
- a `gap-drafter` child workflow call through the fixed stdlib signature;
- no widened `gap-drafter` arity, public path threading,
  compatibility-bundle reread, or placeholder-carrier fabrication; and
- diagnostics identify selector and `gap-drafter` child-call failures at the
  authored call boundary.

Until that route works, a family may still adopt request-record, transition,
publication, and other parent/work-item cleanup slices that do not
depend on reachable imported-gap execution, but it must not claim full
imported `backlog-drain` adoption when the reachable `GAP` lane still depends
on family-local payload-smuggling wrappers or reopened call boundaries.

#### 2.3.1 Generic Gap-Payload Leaf Carriage

For families whose reachable selector `GAP` payload is a typed record with
multiple semantic fields, the shared callable-boundary prerequisite in
Section 2.3 also requires one narrower behavior check: imported
`backlog-drain` must carry that record across the fixed `gap-drafter`
boundary by the declared record-leaf shape, not by a one-field surrogate.

The minimum contract is:

- child-call binding derives every declared leaf of the selector `GAP` record
  from selector outputs or loop-frame outputs on the imported route;
- the shared lowering preserves the authored record shape rather than
  substituting a special one-field protocol such as `gap-id`;
- the fixed `gap-drafter` boundary remains exactly `DrainCtx` plus one record
  payload parameter, and richer payloads are expressed only by the fields of
  that record, not by widened arity or family-local recomposition; and
- the accepted route uses the same generic record-leaf call-binding model
  expected of other typed workflow-call boundaries, so later families can rely
  on shared lowering rather than local wrapper transport.

The minimum behavior check for this narrower contract is:

- one compile/shared-validation fixture whose selector `GAP` variant carries a
  record payload with more than one semantic field;
- positive assertions that the imported `gap-drafter` child call binds each
  leaf from prior outputs on the imported route rather than from family-local
  wrapper projection; and
- one negative check that a non-record `gap-drafter` payload still fails the
  fixed callable-boundary contract.

Until that route works, a family may not treat one-field `gap-id` carriage as
showing that the reachable imported `GAP` lane is ready for richer typed gap
payloads.

### 2.4 Family Gap Re-Entry Convergence Over Imported `backlog-drain`

For families whose real imported `backlog-drain` route can return `GAP` and
whose `gap-drafter` may return `CONTINUE`, there is a separate family-owned
prerequisite after the shared callable-boundary and payload-carriage checks:
the next selector pass must observe typed progress from the completed gap work
rather than reselecting the same gap until authored exhaustion.

The minimum contract is:

- a valid gap draft or validation pass records selector-visible typed progress
  before returning `GapResult.CONTINUE`;
- the next selector pass reads that progress through inputs it already
  consumes, such as typed run-state or progress-ledger state, rather than
  through hidden in-memory flags, forced fake-provider tuple sequencing,
  reread reports, or pointer files;
- authored `max_iterations_exhausted` remains the terminal result when the
  selector truly keeps returning non-terminal work without new progress
  state; and
- the accepted route does not change shared `std/drain` parent-loop semantics,
  widen `gap-drafter` arity, reopen handwritten parent routing, force
  selector `DONE`, or bypass the family loop to manufacture convergence.

The minimum behavior check for this contract is:

- one real-route smoke or fixture where the selector returns `GAP`, the
  `gap-drafter` returns `CONTINUE` after recording typed progress, and the
  next selector pass reaches the family's intended terminal route because of
  that recorded progress;
- one negative or exhaustion check where absent progress still yields
  `max_iterations_exhausted`; and
- preserved source-map provenance for the recorded progress state.

For the Design Delta reference family, this prerequisite is separate from the
shared `gap-drafter` callable-boundary check: fixed `DrainCtx + gap payload`
transport may already be green while the real `DRAFT_DESIGN_GAP` lane still
needs a family-owned progress transition so selector re-entry converges.

Until that route works, a family may still adopt request-record, transition,
publication, and shared gap-transport cleanup slices, but it must not claim
imported `backlog-drain` adoption on reachable gap routes that still exhaust
on unchanged selector inputs after a valid gap draft.

## 3. Shared Phase-Family Boundary Prerequisite

For any parent-callable family that intends to simplify ordinary work-item
authoring to an `item-ctx` plus typed-selection surface while still reusing
existing child phase workflows, the shared post-foundation phase-family
boundary lane must already support hidden private-context transport and
matched-union validation on the WCC route. The minimum contract is:

- internal reusable-call binding supplies phase/item context without exposing
  synthetic `PhaseCtx`, state roots, generated write roots, or checkpoint
  paths as public authored inputs;
- a high-level work-item workflow may `match` imported child-workflow union
  results and project them into family or stdlib terminal unions without
  `workflow_boundary_type_invalid` or lost `requires_variant` provenance;
- any generated helper/private workflow boundaries preserve producing-step
  identity, source maps, and private/compatibility boundary labeling needed by
  shared validation; and
- the route does not regain path-heavy `phase-ctx`-first signatures, bundle
  rereads, or family-local wrapper shapes whose only purpose is to bypass
  missing refinement/context transport.

This prerequisite decomposes into three shared capability contracts that must be
checked together for families adopting imported `backlog-drain` plus reused child
phase workflows:

### 3.1 Fixed `run-item` Workflow-Ref Shape

The imported `std/drain/backlog-drain` owner lane keeps the `run-item`
workflow-reference boundary fixed to the stdlib selected-item call shape:

- `ItemCtx`; and
- the stdlib selection payload.

If a family still needs additional authored domain inputs to reuse existing
child phase workflows, those inputs must reach the child workflows through one
of these shared routes:

- a typed selection/bootstrap payload already carried through that fixed
  `run-item` boundary; or
- hidden private reusable-call/context binding derived from `ItemCtx`,
  `RunCtx`, or other accepted runtime-owned anchors.

The family must not satisfy this prerequisite by widening the imported
`run-item` workflow-ref arity, by reintroducing public path-threading
parameters, or by adding family-local wrappers whose only purpose is to smuggle
extra authored inputs around the fixed stdlib call shape.

### 3.2 Generic Child-Phase Reuse For Item-Context-First Families

The shared phase-family route must support child-phase reuse for general
item-context-first workflow families, not only for one dedicated fixture
or caller-specific allowlist. The minimum behavior check for this contract shows
that:

- a work-item workflow entered through the fixed `run-item` stdlib shape may
  derive or reuse child phase workflows without exposing new public `PhaseCtx`
  or state-root inputs;
- family-authored typed domain inputs needed by those child phase workflows
  remain available through the accepted typed payload or hidden private-binding
  route rather than through reopened path-heavy signatures;
- matched child-workflow unions still preserve `requires_variant` provenance,
  source maps, and shared-validation boundary labeling on the WCC route; and
- the generalized route is owned by shared compiler/runtime contracts rather
  than by a family-specific caller name or one-off Design Delta branch.

Until that shared contract exists, a family may still adopt request-record,
projection, transition, publication, and shared parent-loop cleanup
slices, but it must not claim the simplified internal-signature plus
imported-child stdlib route for ordinary work-item composition.

### 3.3 Called-Workflow Result Branching And Terminal Reprojection

The shared phase-family route must also support the ordinary work-item branch
shape that imported `backlog-drain` families actually need after the fixed
`run-item` entrypoint is in place. The minimum contract is:

- the authored surface is ordinary refined pattern matching: inside
  `((BLOCKED blocked) ...)`, `blocked` has the `BLOCKED` payload type;
- a work-item workflow may call an imported child phase workflow, bind the
  returned union result, and immediately `match` that binding on the ordinary
  WCC/schema-2 route;
- inside a proved branch of that child-workflow result, the workflow may call a
  family or stdlib helper that returns a second union-like terminal or
  classification result and may `match` that second result without losing the
  producing-step identity needed by `requires_variant`;
- nested finalizers such as imported `std/resource/finalize-selected-item`, or
  equivalent typed family terminal reprojection, may appear under those proved
  branches without triggering `workflow_boundary_type_invalid` because the
  compiler retargeted refinement at a non-variant wrapper step; and
- the accepted route remains the shared compiler/runtime path rather than a
  family-local decomposition into path-heavy wrapper workflows, re-read
  compatibility bundles, or caller-name-specific validator exemptions.

The minimum behavior check for this contract is a compile/shared-validation
fixture that exercises this exact shape:

- fixed `run-item` stdlib entry;
- imported child phase call returning a union;
- `match` over that call result;
- branch-local call to a terminal-classification or recovery helper returning a
  second union; and
- branch-local call to imported `finalize-selected-item` or an equivalent typed
  terminal projection.

Until that route works, a family may still adopt the parent-loop, request-
record, projection, transition, and publication slices that do not
depend on this branching shape, but it must not claim completion of the
simplified item-context-first child-phase reuse route.

Feasibility: this does not require a new language feature beyond the accepted
WCC route. Surface `match` already elaborates to WCC `case`, `case` opens the
variant/refinement scope, and join parameters are the normal way for branch
results to leave that scope. The implementation work is to make the existing
refined match-binder model complete for called-workflow results, nested
finalizers, and terminal reprojection, with source maps and shared-validation
refinement metadata generated from those lexical bindings. A fix that exposes
refinement tokens as authored values, adds caller-name-specific refinement
allowlists, or
requires branch-local bundle rereads is a compatibility workaround, not the
target shape.

### 3.4 No Internal Compatibility-Carrier Lane

The final target has no hidden compatibility-carrier abstraction for ordinary
internal `.orc` composition. If a route still needs `run_state_path`, a
relpath, a summary path, or another compatibility value to cross a stdlib
child-call boundary, that is migration debt, not target completion.

The only accepted outcomes are:

- remove the carrier by passing typed values and using runtime-owned
  checkpoint/resource state;
- stop the current slice and select the prerequisite that removes the carrier.

A gap must not make progress claims by threading the carrier through more
domain payloads, widening workflow-ref signatures, adding family-local wrapper
workflows, reclassifying the carrier as private runtime context, or other
changes whose only purpose is to keep the carrier alive.

### 3.5 Work-Item Summary Ownership Over Imported `finalize-selected-item`

For families whose selected-item route still produces ordinary terminal or
blocked-recovery summary files inside the work-item body, imported
`finalize-selected-item` adoption requires one additional family-owned
prerequisite: summary files must stop being a hidden precondition for terminal
typed return.

The minimum contract is:

- imported `finalize-selected-item` may consume typed summary values, but it
  must not require body-owned summary materialization in order to return the
  typed `SelectedItemResult`;
- the accepted route does not keep `record-work-item-terminal-outcome`,
  `record-work-item-blocked-recovery-summary`, body-level summary
  `materialize-view` calls, or equivalent family-local summary writers as
  the mechanism that allows imported `finalize-selected-item` to complete.

The minimum behavior check for this contract is:

- one compile/shared-validation or runtime smoke fixture where imported
  `finalize-selected-item` returns the typed work-item terminal result without
  relying on body-owned summary materialization;
- one negative check that interior field-level publication or
  rendered-summary-as-authority still fails the promoted route.

Under this prerequisite, a failing smoke or regression that expects an interior
`item_summary.json` file on completed, exhausted, or blocked-recovery work-item
routes is stale compatibility coverage. The correct repair is to update that
expectation to typed terminal return plus declared boundary publication or
legacy bridge, not to restore body-owned `item_summary.json` materialization.

For the Design Delta reference family, this prerequisite stays separate from
the broader stdlib-adoption rewrite: the route may clear called-workflow
branching and imported finalizer placement while still being blocked if the
unblocked selected-item path only completes through interior summary
materialization.

Until that route works, a family may still adopt parent-loop, request-record,
and transition cleanup slices, but it must not claim imported
`finalize-selected-item` adoption on routes where ordinary work-item summary
durability still lives in the work-item body.

## 4. Shared `std/phase` Owner-Lane Self-Hosting Prerequisite

For any parent-callable family that reuses child phase workflows through the
imported `std/phase` lane, the shared stdlib owner lane must already support
ordinary `std/phase` compile and validation as an imported module on the same
WCC/schema-2 route the family is using. This is a separate prerequisite from
the family-specific `item-ctx` and `backlog-drain` wiring above.

The minimum contract is:

- `std/phase` resolves and exports its own authored review/fix types and
  helpers, including `ReviewDecision`, `ReviewFindings`, and
  `ReviewLoopResult`, without family-local aliases, copied type declarations,
  or compiler-name special cases;
- `review-revise-loop`, `phase-scope`, and any helper procedures they depend on
  compile through the ordinary imported-stdlib route with the same type
  environment and source-map visibility expected of other builtin stdlib
  modules;
- owner-lane behavior checks include at least one compile/shared-validation
  fixture that fails closed on missing local type resolution or builtin-module
  self-reference drift, rather than relying only on downstream family
  workflows to discover the failure; and
- a family does not satisfy this prerequisite by forking `std/phase`,
  restating the missing types in family modules, or broadening its own design
  scope to patch shared stdlib/compiler semantics under a family migration gap.

Until that shared contract exists, a family may still adopt request-record,
projection, transition, publication, parent-loop, and phase-boundary
cleanup slices that do not depend on the broken `std/phase` owner lane, but it
must not claim completion of the imported child-phase/stdlib route.

