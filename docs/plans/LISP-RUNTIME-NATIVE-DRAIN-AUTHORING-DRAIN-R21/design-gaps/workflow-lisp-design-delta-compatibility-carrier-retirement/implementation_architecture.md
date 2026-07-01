# Design Delta Compatibility-Carrier Retirement Implementation Architecture

Status: draft implementation architecture
Design gap id: `workflow-lisp-design-delta-compatibility-carrier-retirement`
Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
Baseline context: `docs/design/workflow_lisp_frontend_specification.md`
Command/effect authority: `docs/design/workflow_command_adapter_contract.md`

## Scope

This architecture closes exactly the selected Design Delta compatibility-carrier
gap: imported Design Delta drain composition must no longer depend on
`run_state_path` / `run-state` as ordinary internal workflow data.

The bounded retirement surface is:

- shared stdlib result and workflow-ref contracts that still force or tolerate
  a run-state carrier;
- Design Delta family types or adapters that still expose a `run-state` payload
  for selection or terminal routing;
- frontend private compatibility-bridge admission and lowering classification
  that still treats `run_state_path` as an omittable internal caller/callee
  value; and
- certified adapter rows whose only remaining role is retired or quarantined
  lineage.

The architecture does not redesign provider request records, gap re-entry
convergence, public publication, consumer-side rendering, YAML-primary
promotion, report/census generation, migration evidence, or the whole
`std/drain` API. It may touch shared code only where that shared code is the
owner of carrier admission, validation, lowering, or certified-adapter policy.

## Current Checkout Baseline

The current checkout is already partly carrier-free:

- `std/drain::SelectionResult` has `EMPTY` and reason-only `BLOCKED`.
- `std/drain::GapResult.CONTINUE` carries no payload.
- `std/resource::SelectedItemResult` carries summary and blocker values, not
  run-state.
- `DesignDeltaDrainCtx`, `DesignDeltaSelectionResult`,
  `DesignDeltaGapResult.CONTINUE`, `drain.orc`, `selector.orc`, and
  `stdlib_adapters.orc` no longer thread `run_state_path` through the primary
  parent-drain route.
- `drain-run-state` resource state in `std/drain.orc` and Design Delta
  `transitions.orc` is runtime-native `state-layout` backed.
- `materialize_lisp_frontend_work_item_inputs` is checked into the command
  boundary manifest with `retirement_status: retired`.

The remaining pressure is narrower and must be retired or quarantined:

- `lisp_frontend_design_delta/types.orc` still contains an older
  `SelectionResult.DONE (run-state StateExisting)` shape.
- `orchestrator/workflow_lisp/typecheck_calls.py` still has explicit
  compatibility-bridge omission for `run_state_path`.
- `orchestrator/workflow_lisp/phase_family_boundary.py`,
  `orchestrator/workflow_lisp/lowering/workflow_calls.py`, and
  `orchestrator/workflow_lisp/lowering/phase_scope.py` still classify
  `run_state_path` as a known compatibility bridge input or source binding.
- Tests still contain a mix of negative fixtures, historical compatibility
  behavior, and live-route assertions around `run_state_path` / `run-state`.
- Historical run-state files used by build/reference-family evidence still
  exist as run evidence; those files are not automatically forbidden, but they
  must not become typed composition transport.

## Ownership

The Design Delta workflow family owns domain records and projections under
`workflows/library/lisp_frontend_design_delta/`. It must keep selector, gap,
selected-item, work-item, and terminal composition typed and carrier-free. If an
older family type remains for historical compatibility, it must be quarantined
outside the promoted parent route and excluded from ordinary stdlib
composition.

The imported `std/drain` owner lane owns the fixed `backlog-drain` call shape:
`selector`, `run-item`, and `gap-drafter` are typed workflow refs with fixed
arity. That owner lane must not require `run-state` fields for `EMPTY`,
`BLOCKED`, `GAP.CONTINUE`, `run-item CONTINUE`, or `run-item BLOCKED` typed
value return.

The `std/resource` owner lane owns selected-item finalization and
runtime-native selected-item outcome transitions. It must return typed
`SelectedItemResult` values without using summary files or run-state paths as
hidden value-return prerequisites.

The Workflow Lisp frontend, WCC lowering, shared validation, Semantic IR,
source-map, and build-artifact layers own private context binding,
compatibility bridge classification, generated path authority, and diagnostics.
Any shared repair for this gap must be a generic rule, not a Design
Delta-specific compiler, lowerer, validator, or report exception.

The runtime, `StateLayout`, and transition executor own runtime-native
`RESOURCE_STATE` and `TRANSITION_AUDIT` paths. A runtime-native resource state
path is not a Workflow Lisp `run_state_path` compatibility carrier.

`docs/design/workflow_command_adapter_contract.md` owns any retained script,
command step, command-boundary manifest row, certified adapter, legacy adapter,
or runtime-native promotion decision touched by this slice.

## Source Surfaces

Primary source surfaces are:

- `orchestrator/workflow_lisp/typecheck_calls.py`
- `orchestrator/workflow_lisp/phase_family_boundary.py`
- `orchestrator/workflow_lisp/lowering/workflow_calls.py`
- `orchestrator/workflow_lisp/lowering/phase_scope.py`
- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
- `orchestrator/workflow_lisp/stdlib_modules/std/resource.orc`
- `workflows/library/lisp_frontend_design_delta/*.orc`
- focused tests for Design Delta feasibility, stdlib drain/resource behavior,
  workflow-call/lowering behavior, bridge compatibility, typed prompt inputs,
  and build artifacts.

Report, census, parity, and checked-manifest files are conditional consumers,
not primary source surfaces for this slice. Update them only when a changed
executable contract produces a concrete diff that a current public/runtime
consumer reads.

Conditional source surfaces are in scope only when carrier retirement exposes a
generic WCC/schema-2 prerequisite failure:

- match/proof lowering;
- child-workflow value return;
- imported stdlib terminal reprojection;
- source-map or Semantic IR projection for private context and resource
  transitions.

If any file outside these surfaces still uses `run_state_path` or `run-state`
for ordinary Workflow Lisp composition, it follows the same rule: remove the
carrier or isolate it as an explicit public/legacy bridge with owner, consumer,
schema, authority class, and retirement condition. It must not be reclassified
as `runtime_derived`, renamed as another relpath carrier, or threaded through
workflow refs as domain data.

## Contract

Typed values are the semantic channel for the promoted Design Delta parent
route. Drain and work-item composition passes records, unions, resource handles,
transition results, and materialized views only at declared consumer seams.

`run_state_path` / `run-state` is allowed only as:

- historical-run evidence outside typed composition;
- a negative fixture proving the carrier is rejected;
- a compatibility fixture that is not promoted-route evidence;
- an explicitly declared public or legacy bridge with named consumer, owner,
  authority class, schema, and retirement condition; or
- a certified adapter input where the adapter remains live for a real external
  or legacy protocol and satisfies the command-adapter contract.

It is forbidden as:

- a field on high-level drain, selector, selected-item, gap, work-item, or
  terminal records used for imported stdlib composition;
- a parent loop-state or child loop-state field;
- an invisible value injected to satisfy `selector`, `run-item`, `gap-drafter`,
  finalizer, or transition-wrapper workflow-ref validation;
- a provider prompt fact unless the provider is explicitly judging a declared
  compatibility bridge;
- a materialized view consumed as typed state;
- a resource identity for runtime-native `drain-run-state`; or
- a hidden prerequisite for returning `DrainResult`, `SelectedItemResult`, or a
  family terminal union.

Shared stdlib contracts must preserve carrier-free value return:

- selector `EMPTY` is a typed terminal condition with no run-state payload;
- selector `BLOCKED` carries typed reason data only;
- `gap-drafter` `CONTINUE` is control flow with no payload carrier;
- `run-item` / `SelectedItemResult` returns summary and blocker values, not
  run-state transport;
- terminal effects such as `record-drain-outcome`, publication, summary
  rendering, compatibility bridges, or adapter calls are explicit consumers
  after typed value return; and
- validator checks preserve fixed arity and typed payload requirements without
  requiring path-carrier fields only because historical stdlib shapes had them.

## Command Adapter And Runtime-Native Policy

No new inline Python, shell, heredocs, stdout JSON semantics, report parsing,
pointer-as-state behavior, ad hoc JSON rewrites, or uncertified scripts are
allowed in this slice.

`materialize_lisp_frontend_work_item_inputs` may remain in the command-boundary
manifest only as a certified row with retired or quarantined compatibility
status. It must not be invoked by the promoted Design Delta parent route, used
to reconstruct typed work-item state, or counted as evidence that an internal
carrier remains acceptable.

Runtime-native `resource-transition` remains the target for `drain-run-state`
and selected-item outcome mutation. Transition evidence must expose request and
result types, write set, idempotency fields, audit projection, source-map
provenance, backend kind, and fail-closed conflict behavior. If a legacy command
adapter remains for state mutation, it is a compatibility backend with the same
typed transition contract and explicit retirement metadata.

## Allowed Shapes

Allowed implementation shapes include:

- removing or quarantining stale Design Delta family `run-state` variants that
  are no longer part of promoted imported stdlib composition;
- removing shared `run_state_path` compatibility bridge omission and lowering
  classification when no declared public or legacy consumer owns that bridge;
- keeping runtime-native `drain-run-state` state-layout and audit evidence as
  resource-transition evidence rather than carrier evidence;
- preserving Design Delta source records that are already carrier-free;
- preserving historical run-state files as run evidence when they are not read
  as typed Workflow Lisp authority;
- keeping `materialize_lisp_frontend_work_item_inputs` as retired manifest
  lineage when it is unreferenced by the promoted route;
- leaving report/census/parity rows untouched when they are historical,
  diagnostic, or unchanged by the executable carrier retirement;
- maintaining negative coverage that rejects carrier reintroduction as public
  input, loop state, workflow-call binding, runtime-derived reclassification,
  pointer authority, materialized-view authority, report parsing, or adapter
  semantics; and
- repairing exposed generic WCC/schema-2 hidden-context, workflow-call,
  source-map, or terminal reprojection defects with non-Design-Delta fixture
  evidence.

## Forbidden Shapes

This slice must not:

- rename `run_state_path` to another internal relpath field and keep the same
  behavior;
- replace `run-state` with a one-field surrogate carrier;
- widen `backlog-drain`, `selector`, `run-item`, `gap-drafter`, or finalizer
  workflow-ref signatures;
- add wrapper workflows whose only purpose is preserving the carrier;
- rely on compatibility bundle rereads, pointer files, rendered reports,
  provider prose, debug YAML, or command stdout as semantic authority;
- make terminal effect execution a prerequisite for typed child-call value
  return;
- add Design Delta-specific compiler, lowerer, validator, source-map, or report
  exceptions;
- weaken variant proof, workflow-ref typechecking, structured-output
  validation, resource-transition validation, or path-safety checks; or
- claim YAML-primary replacement from compile, validation, smoke, or retirement
  evidence alone.

## Acceptance Conditions

The slice is accepted when all of the following hold:

- Design Delta drain, selector, stdlib adapter, work-item, type, and transition
  source stays free of `run_state_path` / `run-state` as internal composition
  data on the promoted parent route.
- Imported `std/drain::backlog-drain` compiles and validates through selector
  `EMPTY`, selector `BLOCKED`, `GAP.CONTINUE`, selected-item `CONTINUE`, and
  selected-item `BLOCKED` routes without run-state fields.
- Shared workflow-ref validation no longer forces `run-state` fields for
  carrier-free selector, run-item, gap-drafter, drain terminal, selected-item
  finalizer, or transition-wrapper routes.
- Any remaining `run_state_path` bridge classification is tied to a named
  public or legacy consumer with owner and retirement metadata; otherwise the
  bridge is removed.
- `materialize_lisp_frontend_work_item_inputs` is unreferenced by the promoted
  route and recorded only as retired or compatibility evidence that satisfies
  the command-adapter contract.
- Runtime-native `drain-run-state` remains resource-transition state, not a
  live `run_state_path` compatibility carrier.
- Source maps, Semantic IR, executable IR, and runtime validation preserve the
  private/public/compatibility distinction for any changed carrier boundary.
- Negative tests fail if the carrier is reintroduced as public input, loop
  state, workflow-call binding, runtime-derived reclassification, pointer
  authority, report parsing, materialized-view authority, or command-adapter
  semantics.
- At least one non-Design-Delta fixture or focused shared test proves any
  generic hidden-context, stdlib, validation, or lowering repair used by this
  slice.

This architecture closes only the selected compatibility-carrier retirement
gap. It does not certify full runtime-native drain completion, provider
request-record migration, gap convergence, consumer-side rendering completion,
or YAML-primary promotion.
