# Design Delta Compatibility-Carrier Retirement Implementation Architecture

Status: draft implementation architecture
Design gap id: `workflow-lisp-design-delta-compatibility-carrier-retirement`
Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
Baseline context: `docs/design/workflow_lisp_frontend_specification.md`
Command/effect authority: `docs/design/workflow_command_adapter_contract.md`

## Scope

This slice retires the live `run_state_path` compatibility carrier from
ordinary Design Delta drain, work-item, and stdlib child-call composition.

The selected gap is bounded to these current compatibility rows and the source
surfaces that produce them:

- `drain.loop.run_state_path`
- `work_item.loop.run_state_path`
- `transitions.resource.drain_run_state`

The slice does not redesign `backlog-drain`, `finalize-selected-item`,
provider request records, gap re-entry convergence, public boundary bootstrap,
or YAML-primary promotion. Those remain governed by their existing design gaps
and parity gates.

## Problem Statement

The current Design Delta route still uses `run_state_path` as an internal
transport value. It appears in drain context construction, selector prompt
subjects, selection payloads, selected-item stdlib adapters, work-item recovery
routes, and transition helpers. The retirement manifest still records
`KEPT_COMPATIBILITY` for the parent drain loop carrier, the work-item loop
carrier, and the `drain-run-state` bridge backing.

That shape conflicts with the target design's "No Internal
Compatibility-Carrier Lane" rule: a relpath such as `run_state_path` must not
cross stdlib child-call boundaries or ordinary family composition merely to keep
YAML-era state files alive.

## Ownership

The Design Delta workflow family owns the domain records and projections in
`workflows/library/lisp_frontend_design_delta/`. It owns whether selector,
work-item, gap, blocked-recovery, and terminal records carry domain facts or
compatibility carriers.

The imported `std/drain` route owns the fixed parent loop call shape. The
family must satisfy that shape with typed `DesignDeltaSelectionResult`,
`DesignDeltaSelectedItemPayload`, `DesignDeltaGapPayload`, and terminal values,
not by widening workflow refs or smuggling `run_state_path` through payloads.

The Workflow Lisp frontend and WCC lowering own private executable context,
hidden compatibility bridge projection, boundary authority reporting, source
maps, and Semantic IR visibility. They may expose a legacy bridge at a boundary,
but they must not make that bridge look like an ordinary typed value in
internal composition.

The runtime, `StateLayout`, and resource-transition substrate own private
checkpoint/resume state, runtime-derived resource identity, transition audit,
and idempotent transition replay. Repeated drain/work-item state mutation
targets the runtime-native declared transition lane.

`docs/design/workflow_command_adapter_contract.md` owns any retained script,
command step, certified adapter, or legacy adapter boundary. This slice must
not add inline Python or shell, report parsing, pointer-as-state behavior, or
uncertified scripts to replace the carrier.

## Source Surfaces

Expected source surfaces for this gap are limited to:

- `workflows/library/lisp_frontend_design_delta/drain.orc`
- `workflows/library/lisp_frontend_design_delta/selector.orc`
- `workflows/library/lisp_frontend_design_delta/stdlib_payloads.orc`
- `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc`
- `workflows/library/lisp_frontend_design_delta/work_item.orc`
- `workflows/library/lisp_frontend_design_delta/work_item_bridge_support.orc`
- `workflows/library/lisp_frontend_design_delta/transitions.orc`
- `workflows/library/lisp_frontend_design_delta/types.orc`
- focused tests for build artifacts, Design Delta compile feasibility,
  resource transitions, migration parity, and negative retirement diagnostics

Shared compiler or runtime code is in scope only when the carrier cannot be
removed without a generic private-context, resource-transition, source-map, or
boundary-authority fix. Any such shared change must be expressed as a generic
Workflow Lisp rule, not a Design Delta name check.

If files outside these surfaces still consume `run_state_path`, they must obey
the same rule: it is either a declared legacy/public compatibility bridge with
owner, consumer, authority class, and retirement condition, or it is removed
from ordinary internal composition. It must not be reclassified as
`runtime_derived`, repackaged under another field name, or threaded through
workflow refs as domain data.

## Contract

Typed values are the internal semantic channel. The promoted Design Delta
parent route must pass domain records, union variants, resource handles, and
transition results through drain and work-item composition.

`run_state_path` is allowed only in these forms:

- an explicitly declared public or legacy compatibility bridge for a named
  external/YAML-era consumer;
- a checked compatibility fixture that is not used as evidence for the
  promoted route;
- historical-run compatibility metadata; or
- a certified adapter boundary that still consumes the path and declares typed
  inputs, outputs, effects, fixtures, path-safety rules, error taxonomy,
  source-map behavior, owner, and retirement condition.

`run_state_path` is not allowed as:

- a field of high-level drain, selection, selected-item, gap, or terminal
  records used for ordinary stdlib composition;
- a loop-state field used to resume or route the parent drain or work-item
  loop;
- a hidden value injected into selected-item or gap payloads to satisfy child
  calls;
- a required argument to domain finalizers, blocked-recovery projection, or
  terminal classification helpers;
- the semantic backing identity for `drain-run-state` on the promoted
  runtime-native transition route; or
- a provider prompt fact unless the provider is explicitly judging a declared
  compatibility bridge.

The `drain-run-state` resource must be identified by runtime-owned resource
identity or another typed transition subject on the promoted route. If a
bridge-backed resource alias remains for legacy behavior, it must be isolated
from `std/drain` and work-item composition and labeled as compatibility, not as
the target state model.

## Allowed Shapes

Allowed implementation shapes include:

- removing `run_state_path` from `DesignDeltaDrainCtx`,
  `DesignDeltaSelectedItemPayload`, `DesignDeltaSelectionResult`,
  `DesignDeltaGapResult`, and selected-item terminal results where those types
  are used for internal composition;
- replacing run-state path transport with typed terminal values, resource
  transition results, private checkpoint state, or runtime-derived resource
  handles;
- changing drain/work-item transition helpers so callers pass typed transition
  requests or domain values instead of a run-state relpath;
- keeping legacy bridge metadata only at named public or YAML compatibility
  boundaries;
- preserving runtime-native transition behavior while changing the resource
  backing away from `:backing (bridge run_state_path)`.

## Forbidden Shapes

This slice must not:

- rename `run_state_path` to another internal relpath field and keep the same
  transport behavior;
- widen imported `backlog-drain`, `run-item`, or `gap-drafter` workflow-ref
  signatures;
- add wrapper workflows whose only purpose is to carry the path through a fixed
  stdlib boundary;
- make rendered reports, pointer files, debug YAML, provider prose, command
  stdout, or compatibility bundles semantic routing authority;
- use a materialized view as the internal typed value;
- keep `record-drain-terminal-outcome-stdlib`,
  `record-design-gap-progress`, `record-work-item-blocked-recovery-summary`, or
  equivalent helpers path-shaped if they are part of the promoted route;
- add inline Python/shell, ad hoc JSON rewrites, or uncertified scripts; or
- claim YAML-primary replacement from compile, validation, or smoke success
  alone.

## Command Adapter And Runtime-Native Policy

Any retained command boundary touched by this slice follows the command-adapter
contract. Existing certified external tools may remain when they do real
external validation or legacy protocol work, but they cannot become a loophole
for hidden run-state mutation.

For transition behavior, the preferred target is runtime-native
`resource-transition` with declared request/result types, write set,
idempotency fields, audit projection, source-map provenance, and fail-closed
conflict behavior. A certified adapter may remain only as an explicit
compatibility backend with the same typed transition contract and retirement
metadata.

## Acceptance Conditions

The slice is accepted when the promoted Design Delta parent route shows all of
the following:

- `lisp_frontend_design_delta/drain::drain` compiles through WCC/schema 2 and
  passes shared validation with the imported `std/drain::backlog-drain` route.
- Parent drain, selector, stdlib payload/adapters, and work-item composition no
  longer carry `run_state_path` in ordinary record fields, loop state, workflow
  call inputs, provider prompt subjects, terminal variants, or selected-item
  payloads.
- `carry-drain-run-state-bridge`, `project-selected-compat`, and any equivalent
  helper are either unreferenced on the promoted route or quarantined as
  legacy fixtures.
- `drain-run-state` no longer uses `:backing (bridge run_state_path)` on the
  promoted runtime-native transition route. Any legacy bridge-backed alias is
  explicitly compatibility-only.
- Runtime-native transitions, source maps, and Semantic IR still expose
  transition effects and generated private state without inferring semantics
  from path names.
- Negative fixtures fail if the carrier is reintroduced as public input,
  loop-state field, call-signature input, runtime-derived reclassification, or
  checkpoint-as-authority evidence.

This architecture closes only the selected compatibility-carrier gap. It does
not certify full runtime-native drain completion, imported finalizer adoption,
provider request-record migration, or YAML-primary promotion.
