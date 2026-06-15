# Workflow Lisp Private Runtime Value Flow C4 Compatibility Bridges As Metadata Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-private-runtime-state-and-consumer-value-flow-c4-compatibility-bridges-as-metadata`
Target design: `docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice drafts the bounded C4 handoff for compatibility bridges as metadata:

- define one metadata-driven bridge manifest and one bridge report for the
  Design Delta parent-drain family;
- select the checked C0 compatibility rows that C4 owns and describe how they
  lower through existing generated `materialize_view` behavior;
- require `authority_class: "compatibility_bridge"` for every generated bridge
  view while keeping bridge files as representations only;
- define fail-closed retirement when bridge metadata is removed but a legacy
  consumer still requires the file; and
- keep command-bound legacy consumers under the certified-adapter contract.

Out of scope:

- C5 cleanup, typed bootstrap replacement, or retirement of
  `materialize_lisp_frontend_work_item_inputs`;
- C3 public publication redesign or any new public artifact semantics;
- new renderer ids, renderer versions, or renderer byte formats;
- inline shell/Python, stdout-as-state, report parsing, or uncertified command
  glue;
- workflow source edits whose only purpose is bridge generation ceremony; and
- changes to Core Workflow AST, Semantic IR, Executable IR, TypeCatalog,
  SourceMap, pointer authority, variant proof, provider/command structured
  output transport, checkpoint semantics, or resource-transition semantics.

## Problem Statement

The target design already separates typed semantic authority from render-only
compatibility files, but the checked Design Delta family still carries bridge
debt as C0 inventory rows rather than as one C4 metadata owner.

The current gap is narrow:

- C0 already classifies compatibility rows and records
  `RETIRE_TO_BRIDGE_METADATA`, but it does not define the manifest that turns
  selected rows into generated bridges.
- `orchestrator/workflow/view_renderer.py` already owns deterministic view
  rendering, and `orchestrator/workflow_lisp/entry_publication.py` already
  shows the adjacent C3 report/helper pattern, but neither one owns C4 bridge
  metadata or retirement rules.
- Some bridge rows are still live compatibility debt because a certified
  adapter consumes the path today. C4 must record that debt explicitly instead
  of silently deleting the bridge.

The architecture therefore needs to define one metadata-driven bridge lane that
keeps typed values authoritative, keeps bridge files non-semantic, and fails
closed when a legacy consumer has not been retired.

## Design Constraints

This slice must stay coherent with:

- `docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md`,
  especially Track C C4, the consumer-lane taxonomy, fail-closed bridge
  retirement, and migration evidence requirements;
- `docs/design/workflow_lisp_frontend_specification.md` for generated
  `materialize_view`, StateLayout-owned generated targets, source maps,
  Semantic IR, executable IR, and boundary authority classes;
- `docs/design/workflow_command_adapter_contract.md` for certified adapters,
  `retire_to_view` bookkeeping, and the prohibition on inline shell/Python,
  stdout-as-state, report parsing, and uncertified command glue; and
- `docs/capability_status_matrix.md` for the implemented `materialize-view`,
  command-adapter, and Design Delta parent-family boundary surfaces.

Guardrails:

- C4 candidate selection starts from rows where
  `consumer_lane == "compatibility_bridge"` or
  `track_c_decision == "RETIRE_TO_BRIDGE_METADATA"`.
- Generated bridge files lower through existing `materialize_view` behavior
  with `authority_class: "compatibility_bridge"`.
- Bridge files are representations only and must never become typed semantic
  authority.
- Removing bridge metadata is a retirement request, not an unconditional
  delete. The build must fail closed when compiled legacy-consumer evidence
  still requires the bridge.
- Command-bound bridge consumers remain governed by
  `docs/design/workflow_command_adapter_contract.md`.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- U0 shared census
- C0 rendering census and renderer seam verification
- C1 typed values as prompt inputs
- C2 observability-derived human summaries
- C3 entry-boundary publish policy
- R1 checkpoint schema shadow emission
- R2 restore for pure and structured regions
- R3 effect-boundary resume policies
- R4 transition-aware resume
- R5 resume-only authored plumbing retirement
- R6 default flip and legacy cleanup

### Decisions Reused

- Reuse U0 row identity and C0 row selection as the checked source of bridge
  candidates.
- Reuse C0 consumer-lane and durability semantics, especially
  `compatibility_bridge` and `durable_bridge`.
- Reuse the C3 small-helper-plus-report pattern for schema constants, selected
  row joining, validation, deterministic serialization, and build artifact
  emission.
- Reuse `orchestrator/workflow/view_renderer.py` and the existing
  `materialize_view` runtime path for deterministic rendering and view digests.
- Reuse R3's treatment of deterministic view regeneration and fail-closed drift
  checks instead of inventing a second bridge runtime.
- Reuse the command-adapter contract for command-bound legacy consumers and
  their retirement bookkeeping.

### New Decisions In This Slice

- Add the C4 metadata schema id
  `workflow_lisp_compatibility_bridge_metadata.v1`.
- Add the C4 report schema id
  `workflow_lisp_compatibility_bridge_report.v1`.
- Define one C4 manifest that records bridge row identity, typed value source,
  renderer metadata, target metadata, retirement metadata, and command-boundary
  expectations.
- Define one C4 report that records selected rows, generated bridges, retired
  bridges, blocked bridges, orphan checks, diagnostics, and contract-isolation
  booleans.
- Treat the blocked command-bound row as explicit compatibility debt rather
  than silent retirement.

### Conflicts Or Revisions

- C0 intentionally stopped at classification and validation. C4 consumes those
  checked rows and adds the metadata-driven bridge-generation contract.
- C3 intentionally owns public publication only. C4 reuses the same renderer
  kernel but not the `public_artifact` authority class or public boundary
  semantics.
- R-track reports can be cited as usage evidence, but they do not retire bridge
  rows by themselves.

## Ownership Boundaries

This slice owns:

- one C4 helper module for schema constants, C0 row selection, metadata
  validation, command-boundary validation, deletion/orphan checks, report
  serialization, and diagnostics;
- one checked Design Delta bridge metadata manifest;
- additive build integration that loads the C4 manifest, reconciles it with U0
  and C0 evidence, lowers legal rows to generated bridge metadata, and emits a
  bridge report;
- additive Semantic IR, executable metadata, build artifact, and source-map
  lineage for generated bridges; and
- focused verification for schema validity, lowering, retirement, blocked
  command-bound rows, contract isolation, and migration parity prerequisites.

This slice does not own:

- renderer registration or renderer byte-format semantics;
- adapter implementation, adapter stable commands, or adapter retirement status
  changes;
- typed bootstrap replacement for `materialize_lisp_frontend_work_item_inputs`;
- public publication policy, prompt rendering, or observability rendering;
- StateLayout naming rules beyond consuming the existing generated-view lane;
- checkpoint, transition, or structured-output semantics; or
- any broader spec or parent-design rewrite.

## Current Checkout Facts

The current checkout already provides the evidence C4 must cite accurately:

- `orchestrator/workflow_lisp/consumer_rendering_census.py` owns C0 schema
  constants, consumer lanes, durability classes, and
  `RETIRE_TO_BRIDGE_METADATA` validation.
- `orchestrator/workflow_lisp/entry_publication.py` is adjacent C3 evidence for
  the small-helper-plus-report pattern only; C4 must not copy public-artifact
  semantics from it.
- `orchestrator/workflow/view_renderer.py` remains the deterministic renderer
  authority; C4 must not add command glue or alternate rendering rules.
- The checked Design Delta census rows selected for C4 are:
  - `c0.drain_bridge_architecture_bundle_path`
  - `c0.drain_bridge_manifest_path`
  - `c0.drain_bridge_progress_ledger_path`
  - `c0.work_item_bridge_architecture_bundle_path`
  - `c0.work_item_bridge_manifest_path`
  - `c0.work_item_bridge_progress_ledger_path`
  - `c0.work_item_pointer_selection_bundle_path`
  - `c0.work_item_command_selection_bundle_path`
- The first seven rows are current `RETIRE_TO_BRIDGE_METADATA` bridge rows.
- `c0.work_item_command_selection_bundle_path` is the blocked command-bound
  row. It still names the certified adapter
  `materialize_lisp_frontend_work_item_inputs` and must be treated as explicit
  compatibility debt.
- `c0.work_item_pointer_selection_bundle_path` is still a representation-only
  pointer bridge for the same legacy consumer and must not become semantic
  authority.

## Proposed Data Model

### Bridge Metadata Manifest

Add one checked manifest:

`workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.compatibility_bridges.json`

Top-level shape:

```json
{
  "schema_version": "workflow_lisp_compatibility_bridge_metadata.v1",
  "target_family": "lisp_frontend_design_delta_parent_drain",
  "source_census": {
    "path": "workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.value_flow_census.json",
    "schema_version": "workflow_lisp_private_runtime_value_flow_census.v1"
  },
  "source_consumer_rendering_census": {
    "path": "workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.consumer_rendering_census.json",
    "schema_version": "workflow_lisp_consumer_rendering_census.v1"
  },
  "bridges": []
}
```

Each bridge row must contain:

- bridge row identity linking back to `bridge_id`, `c0_row_id`, `u0_row_id`,
  and `workflow_surface`;
- owner and consumer metadata from the checked bridge row;
- renderer metadata: `renderer_id`, `renderer_version`, and accepted shape;
- typed value source metadata describing the value ref or typed source that the
  bridge renders;
- target metadata including generated target contract, durability, and
  `authority_class: "compatibility_bridge"`;
- retirement metadata describing when deletion is allowed and what replacement
  target retires the bridge; and
- command-boundary metadata when the bridge still feeds a certified adapter.

The manifest must keep the blocked adapter consumer explicit. For
`materialize_lisp_frontend_work_item_inputs`, C4 may record bridge metadata and
blocked status, but it must not claim adapter retirement or typed bootstrap
replacement.

### Bridge Report

Emit one build artifact:

`.orchestrate/build/<hash>/compatibility_bridge_report.json`

Top-level shape:

```json
{
  "schema_version": "workflow_lisp_compatibility_bridge_report.v1",
  "status": "pass",
  "selected_c0_rows": [],
  "generated_bridges": [],
  "retired_bridges": [],
  "blocked_bridges": [],
  "orphan_bridge_files": [],
  "contract_isolation": {
    "workflow_signature_unchanged": true,
    "call_contract_unchanged": true,
    "boundary_projection_public_inputs_unchanged": true,
    "typed_steps_do_not_consume_bridge_views": true
  },
  "diagnostics": []
}
```

`blocked_bridges` must record the command-bound legacy row
`c0.work_item_command_selection_bundle_path` so the report proves the bridge
was not silently retired.

## Lowering And Runtime Flow

1. Start from the checked C0 rows where
   `consumer_lane == "compatibility_bridge"` or
   `track_c_decision == "RETIRE_TO_BRIDGE_METADATA"`, then reconcile them with
   the C4 manifest.
2. Validate that each enabled manifest row names one selected C0 row, one U0
   row, one typed value source, one renderer, one bridge owner, one consumer,
   one target contract, and one retirement condition.
3. For legal enabled rows, lower through the existing generated
   `materialize_view` behavior. The executable node kind remains
   `materialize_view`, and the generated metadata must carry
   `authority_class: "compatibility_bridge"`.
4. Record bridge lineage in source maps, Semantic IR, executable metadata, and
   build artifacts so generated bridge views are explainable and auditable.
5. Treat generated bridge files as views only. Typed steps, typed results,
   reusable-state gates, transition inputs, and provider/command structured
   outputs must not consume the bridge file as state.
6. When bridge metadata is removed or disabled, interpret that as a retirement
   request. Recompute compiled legacy-consumer evidence before allowing the
   bridge to disappear.
7. If a live legacy consumer still requires the file, fail closed with
   `compatibility_bridge_required_metadata_missing` rather than deleting the
   bridge.
8. For the current checkout, keep
   `materialize_lisp_frontend_work_item_inputs` as a live certified-adapter
   consumer and report it as blocked compatibility debt.

## Contract Isolation

C4 bridge metadata must not alter workflow signatures, call contracts, public
authored inputs, or typed result identity.

The implementation must prove:

- generated bridges stay outside `WorkflowSignature` identity;
- generated bridge paths do not appear as new public authored inputs;
- bridge metadata does not change workflow-call typing or typed result
  semantics;
- bridge files are never re-imported as typed semantic authority;
- command-bound bridge consumers remain certified adapter boundaries rather
  than implicit workflow semantics; and
- migration parity evidence distinguishes typed semantic output from bridge
  views and reports.

## Validation And Diagnostics

Stable diagnostics for this slice:

- `compatibility_bridge_metadata_schema_invalid`
- `compatibility_bridge_c0_row_missing`
- `compatibility_bridge_required_metadata_missing`
- `compatibility_bridge_typed_source_missing`
- `compatibility_bridge_unknown_renderer`
- `compatibility_bridge_renderer_shape_mismatch`
- `compatibility_bridge_command_boundary_uncertified`
- `compatibility_bridge_command_glue_forbidden`
- `compatibility_bridge_orphan_file`
- `compatibility_bridge_view_used_as_state`
- `compatibility_bridge_contract_leak`

Diagnostic expectations:

- missing or non-selected C0 rows fail with
  `compatibility_bridge_c0_row_missing`;
- missing required metadata for a still-required bridge fails with
  `compatibility_bridge_required_metadata_missing`;
- uncertified command-bound consumers fail with
  `compatibility_bridge_command_boundary_uncertified`;
- inline shell/Python, stdout-as-state, report parsing, or uncertified bridge
  generation attempts fail with `compatibility_bridge_command_glue_forbidden`;
- bridge files produced without enabled metadata or without a declared legacy
  consumer fail with `compatibility_bridge_orphan_file`;
- bridge-view-as-state misuse fails with
  `compatibility_bridge_view_used_as_state`; and
- any workflow-signature, call-contract, public-input, or typed-result leakage
  fails with `compatibility_bridge_contract_leak`.

## Verification

The architecture bundle is verified by the recorded commands in
`state/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/drain/iterations/11/design-gap-architect/check_commands.json`.
Those commands must check:

- architecture/check artifact existence and JSON validity;
- draft-bundle field coherence against the selected design gap and approved
  plan target;
- presence of the required C4 section and terminology anchors:
  `## Relationship To Existing Implementation Architectures`,
  `workflow_lisp_compatibility_bridge_metadata.v1`,
  `workflow_lisp_compatibility_bridge_report.v1`,
  `consumer_lane == "compatibility_bridge"`,
  `RETIRE_TO_BRIDGE_METADATA`,
  `authority_class: "compatibility_bridge"`, and
  `materialize_lisp_frontend_work_item_inputs`;
- presence of the required diagnostic names:
  `compatibility_bridge_metadata_schema_invalid`,
  `compatibility_bridge_required_metadata_missing`,
  `compatibility_bridge_command_boundary_uncertified`,
  `compatibility_bridge_view_used_as_state`, and
  `compatibility_bridge_contract_leak`; and
- live evidence anchors for the eight selected C4 rows and the command-bound
  adapter consumer in the checked migration inputs.
