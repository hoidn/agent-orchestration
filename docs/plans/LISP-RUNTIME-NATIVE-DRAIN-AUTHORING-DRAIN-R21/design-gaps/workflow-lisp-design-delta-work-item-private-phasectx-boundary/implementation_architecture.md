# Design Delta Work-Item Private Phase Context Boundary Architecture

Status: revised implementation architecture
Scope: `workflow-lisp-design-delta-work-item-private-phasectx-boundary`

## Purpose

This slice preserves the repaired private `PhaseCtx` boundary for the Design
Delta work-item route while keeping the imported selected-item stdlib route
free of public or hidden run-state carrier plumbing.

The previous version of this gap was under-scoped because it assumed an
already-available hidden/private `run_state_path` lane on the selected-item
stdlib route. The implementation attempt proved that assumption false: the
current checkout no longer exposes a usable `.orc`-level source for that lane
outside the direct owner route. Requiring that lane here would reintroduce the
run-state carrier and compatibility bridge mechanics this target design is
trying to retire.

## Governing Contract

The owning target design is:

- `docs/design/workflow_lisp_runtime_native_drain_authoring.md`

The baseline frontend contract remains:

- `docs/design/workflow_lisp_frontend_specification.md`

For this gap, the durable contract is:

- `run-work-item` remains the Design Delta work-item owner boundary.
- `run-work-item` must not expose public `RunCtx`, `PhaseCtx`, generated roots,
  checkpoint paths, or public `run_state_path` inputs.
- The derived work-item phase context remains a private runtime binding with
  binding id `phase-ctx__work-item`.
- `run-selected-item-stdlib` remains the imported `std/drain` run-item route
  and must not gain a public `run_state_path`, a new hidden bridge input, a
  returned bridge target, or a bridge-carrier payload field.
- Internal composition should pass typed work-item values and typed terminal
  results, not compatibility files or pointer paths.

## Split-Out Compatibility Concern

Legacy `state/run_state.json` blocked-recovery fields are not part of this
private-context slice.

Specifically, this slice must not require:

- writing `blocked_recovery_reason` into `state/run_state.json`;
- writing `blocked_recovery_summary` into `state/run_state.json`;
- proving a hidden/private `run_state_path` lane exists on
  `run-selected-item-stdlib`;
- preserving or strengthening tests whose only purpose is to keep that legacy
  JSON write alive; or
- rebuilding a compatibility bridge as a prerequisite for the selected-item
  route to return its typed result.

If a live consumer still requires those legacy JSON fields, that requirement
belongs in a separate boundary/bridge-retirement slice. That slice must decide
whether to retire the consumer, move the write to a declared boundary, or keep a
certified compatibility writer with an explicit retirement condition. It must
not be smuggled into this private `PhaseCtx` boundary gap.

## Workspace Baseline Reconciliation

The current dirty checkout includes a partially landed run-state-carrier
retirement. That mechanical mismatch may still need repair before the private
context route can be verified:

- `stdlib_adapters.orc`, `stdlib_payloads.orc`, and `drain.orc` have already
  dropped parent-drain `run_state_path` carrier arguments.
- `transitions.orc` may still declare `record-design-gap-progress` and
  `record-drain-terminal-outcome-stdlib` with a leading `run_state_path`
  parameter.
- The narrowed callers are authoritative. Do not restore the caller-side
  carrier arguments and do not restore `DesignDeltaDrainCtx.run_state_path`.
- If those two helper signatures are still mismatched, drop the leading
  carrier parameter from the helper side and route their state changes through
  a state-layout-backed or otherwise carrier-free runtime-native resource.
- This reconciliation must not cause ordinary drain, gap-drafting, or
  selected-item stdlib routes to write legacy `state/run_state.json` fields.

This is a compile-baseline repair only. It is not permission to preserve the
legacy blocked-recovery JSON bridge in this gap.

## Allowed Implementation Shapes

Allowed:

- keep `run-selected-item-stdlib` as the fixed `ItemCtx + typed payload`
  callable route;
- keep `run-work-item` free of public `PhaseCtx` and public `run_state_path`;
- derive `phase-ctx__work-item` from accepted runtime/private context metadata;
- preserve typed blocked-recovery and terminal results as typed values;
- reconcile helper arity by removing stale carrier parameters from helper
  definitions rather than re-adding carrier arguments to callers;
- update tests that incorrectly treat legacy JSON fields as this slice's
  semantic output, or that pin the retired hidden `run_state_path` lane's
  existence in harness bindings or bound-input assertions, so they instead
  check typed result and private-boundary behavior; and
- create or reference a follow-up compatibility-boundary gap if legacy
  `state/run_state.json` consumers are still live.

Forbidden:

- adding a public `run_state_path` input to `run-work-item`,
  `run-selected-item-stdlib`, `run-selected-item-pending`, or internal worker
  routes;
- adding a new hidden compatibility bridge input to make this slice pass;
- returning a bridge target path or owner-private carrier inside
  `SelectedItemResult`, `WorkItemResult`, or intermediate domain payloads;
- widening the imported `std/drain::backlog-drain` run-item workflow-ref shape;
- preserving tests or metadata that require this private-context slice to write
  `blocked_recovery_reason` or `blocked_recovery_summary` into
  `state/run_state.json`; or
- teaching shared lowering/runtime code a Design Delta-specific bridge route.

## Acceptance Conditions

This gap is complete when:

- the Design Delta work-item family compiles with the narrowed carrier-less
  selected-item stdlib route;
- `run-work-item` exposes no public `PhaseCtx` and no public `run_state_path`;
- `run-selected-item-stdlib` exposes no public or hidden `run_state_path`
  carrier and returns typed `SelectedItemResult` behavior normally;
- boundary projection records the private work-item phase binding
  `phase-ctx__work-item`;
- direct and imported selected-item routes preserve typed terminal behavior
  without requiring legacy `state/run_state.json` blocked-recovery fields;
- fixture mirrors match the authoritative `.orc` modules; and
- any remaining legacy JSON compatibility requirement is explicitly outside
  this gap and routed to a separate boundary/bridge-retirement gap.

Compile success alone is not sufficient, but compatibility-file replication is
also not required for this slice. The evidence must prove the private boundary
and typed selected-item composition, not YAML-era run-state file choreography.
