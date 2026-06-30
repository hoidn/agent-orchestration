# Public Boundary Bootstrap Path Retirement Architecture

Status: draft
Design gap id: `workflow-lisp-runtime-native-drain-public-boundary-bootstrap-path-retirement`
Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
Baseline design: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice contracts the promoted public boundary of
`lisp_frontend_design_delta/drain::drain` by removing these bootstrap/state
paths from public authored inputs:

- `architecture_bundle_path`
- `manifest_path`
- `progress_ledger_path`

The retained public authored boundary for this slice is domain or selected-gap
input:

- `steering_path`
- `target_design_path`
- `baseline_design_path`
- `architecture_targets`
- `existing_architecture_index_path`

`run_state_path` is not reopened by this architecture. Imported
`backlog-drain`, selected-item routing, gap drafting, child phase reuse,
terminal reprojection, provider request records, summary publication, and
adapter retirement are outside this selected gap.

## Problem Statement

The current checked-in `drain.orc` entrypoint still lists
`architecture_bundle_path`, `manifest_path`, and `progress_ledger_path` as
ordinary parameters.

That shape contradicts the runtime-native drain target: bootstrap files,
architecture bundle files, and progress ledgers are routine workflow
bookkeeping, not caller-authored domain facts for a promoted parent drain
entrypoint.

## Ownership

The Workflow Lisp frontend owns boundary projection, public/private input
classification, source maps, and Semantic IR visibility for generated inputs.

The runtime and state-layout substrate own generated path allocation, runtime
bootstrap values, and private executable context. Generated paths must be
recorded as generated or runtime-derived values, never inferred from public
parameter names.

The Design Delta family owns the domain meaning of its drain context.

The command-adapter contract owns any retained script or command boundary. If a
remaining adapter consumes one of the retired values, that dependency must stay
certified with typed input signatures. This slice must not add inline Python,
shell glue, pointer-as-state behavior, or report parsing.

## Boundary Contract

The promoted boundary for `lisp_frontend_design_delta/drain::drain` must not
include `architecture_bundle_path`, `manifest_path`, or `progress_ledger_path`
in `public_input_names`, public workflow input contracts, or public input hash
basis.

`DesignDeltaDrainCtx` may continue to contain fields required by existing
stdlib adapters or selection payloads during migration, but the source of those
fields must be private boundary projection rather than public entrypoint
parameters.

## Source Surfaces

The implementation may touch only surfaces needed to enforce that contract:

- `workflows/library/lisp_frontend_design_delta/drain.orc`
- `workflows/library/lisp_frontend_design_delta/types.orc` only if the context
  type needs a non-public bootstrap carrier adjustment
- Design Delta family profile or boundary-classification helpers under
  `orchestrator/workflow_lisp/`
- command-boundary metadata only when a certified adapter still consumes a
  retired path
- focused tests and fixtures that assert the public/private boundary contract

Outside this selected gap, any workflow or helper that sees these names must
follow the same rule: `architecture_bundle_path`, `manifest_path`, and
`progress_ledger_path` are not promoted public authored inputs unless a
different accepted design explicitly marks that workflow as a legacy public
surface. Internal consumers must receive them through typed domain payloads,
runtime-derived context, or generated internals.

## Allowed Shapes

The preferred shape is private derivation from the entry run context,
StateLayout allocation, selected design-gap subject, or existing typed
`architecture_targets` value.

Adapter use is allowed only for already certified external or legacy behavior.
If `materialize_lisp_frontend_work_item_inputs` or another certified adapter
still receives `manifest_path` or `architecture_bundle_path`, the adapter
signature remains the typed contract until a separate adapter-retirement slice
removes that dependency.

## Forbidden Shapes

This slice must not:

- reclassify the three fields as public authored inputs with new wording;
- thread the paths through a wider `backlog-drain`, `run-item`, or
  `gap-drafter` workflow-ref signature;
- keep the paths alive by adding wrapper workflows whose only purpose is
  transport;
- treat pointer files, rendered reports, debug YAML, or command stdout as
  semantic authority;
- add inline Python/shell or ad hoc JSON rewrites to recover the fields;
- broaden this gap into provider request-record migration, terminal
  finalization, gap re-entry, or full adapter retirement; or
- claim YAML-primary promotion from compile success alone.

## Acceptance

The slice is accepted when `lisp_frontend_design_delta/drain::drain` shows:

- the three retired names are absent from public input contracts and
  `public_input_names`;
- internal consumers still receive the needed values through private or
  generated inputs; and
- certified adapters that still consume retired values have typed inputs.

The scope is complete only for the selected public-boundary contraction. It
does not certify broader runtime-native drain completion or Design Delta YAML
primary replacement.
