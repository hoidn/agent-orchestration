# Workflow Lisp StateLayout / PathAllocator Foundation Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-state-layout-path-allocator-foundation`
Target design: `docs/design/workflow_lisp_runtime_migration_foundation.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected Tranche 5 allocator-foundation gap:

- add one shared `StateLayout` / `PathAllocator` boundary for compiler-owned
  generated private write paths;
- route the first required allocation families through that boundary:
  command-result bundle roots,
  provider-result bundle roots,
  variant-projection bundle paths,
  reusable-call write roots,
  entrypoint managed write roots,
  and value-view paths;
- make allocation metadata the shared provenance source for workflow-boundary
  explanation, `source_map.json`, Semantic IR state-layout entries, and
  runtime-owned hidden write-root binding;
- preserve the current public authored workflow surface while hiding
  compiler-owned generated write roots from public inputs;
- make promotion-relevant private generated paths run-isolated by default and
  resume-stable within the same run/call-frame/loop identity.

Out of scope for this slice:

- redesigning authored `RunCtx`, `PhaseCtx`, `ItemCtx`, `DrainCtx`, or the
  broader high-level context semantics from the baseline frontend design;
- public-path or artifact-surface migration beyond the generated private path
  families named above;
- Tranche 1 command structured-output conformance, Tranche 2 typed-value
  transport semantics, Tranche 3 provider target binding, or Tranche 4
  migration-gate hardening beyond reusing the path families those slices
  already introduced;
- retiring existing compatibility command helpers, certifying new adapters, or
  promoting any runtime-native effect;
- queue/resource semantics, review/revise-loop semantics, reusable-state
  validation, or general prompt/provider behavior changes;
- widening public workflow entrypoints, exposing `__write_root__...` as user
  inputs, or weakening source-map / Semantic IR provenance requirements.

This is a bounded implementation architecture for the selected allocator
foundation only. It does not replace the parent runtime-migration foundation,
the baseline Workflow Lisp frontend specification, or the broader state-layout
design.

## Problem Statement

The target runtime-migration foundation is explicit: promotion-relevant
generated private paths must stop being synthesized independently by lowering
helpers, runtime entry binding, source-map serialization, and Semantic IR
projection.

The current checkout still spreads that responsibility across incompatible
local seams:

1. Multiple lowering modules synthesize hidden write-root names and path
   templates directly from step ids:
   `lowering/effects.py`,
   `lowering/values.py`,
   `lowering/phase_resource.py`,
   `lowering/phase_flow.py`,
   and `lowering/control_match.py`.
2. Reusable workflow calls synthesize a second path family independently in
   `lowering/workflow_calls.py::_managed_write_root_bindings(...)`, and the
   loop-scoped compatibility helper writes yet another concrete location under
   `.orchestrate/workflow_lisp/call_bindings/.../__managed_write_roots.json`.
3. Entrypoint runtime binding synthesizes its own concrete write-root paths in
   `WorkflowExecutor._entry_managed_write_root_bindings(...)` under
   `.orchestrate/workflow_lisp/entry/<run_id>/<workflow>/...`, with no shared
   allocation metadata connecting that runtime path to lowering-time path
   requests.
4. `WorkflowProvenance` records only the names of
   `managed_write_root_inputs` and `runtime_context_inputs`; it does not carry
   role, privacy, resume scope, compatibility class, or stable semantic
   identity for generated paths.
5. `LoweringContext.generated_path_spans`, `source_map.json`, and Semantic IR
   all carry partial provenance, but none of them own a neutral allocation
   object that runtime, source maps, and Semantic IR can project from.
6. `SemanticStateLayoutEntry` currently records presentation keys, checkpoints,
   managed write-root input names, and runtime-context input names, but it
   does not yet emit typed state-layout entries for generated bundle paths,
   reusable-call roots, variant-projection bundles, or value-view files.

The result is the exact risk called out by the target design:

- one helper can change a concrete path shape without source-map or Semantic IR
  noticing;
- one runtime entrypoint can become run-isolated while reusable-call
  write-root paths remain static and collision-prone;
- hidden input names remain the only durable compatibility signal instead of a
  shared allocation identity and provenance contract;
- migration evidence can accidentally rely on path shapes that are not
  recorded as compatibility-only.

The selected gap is therefore not “rename write-root helpers.” The missing work
is one neutral allocation/provenance boundary that all selected generated path
families route through before they are projected into authored mappings,
runtime-owned hidden inputs, source maps, or Semantic IR.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_runtime_migration_foundation.md`
  - `14. Tranche 5: StateLayout / PathAllocator Foundation`
  - `15.5 StateLayout / PathAllocator Contract`
  - `16.1 Runtime`
  - `16.3 Workflow Lisp Frontend`
  - `17. Dependencies And Sequencing`
  - `19. Evidence And Implementation Boundaries`
  - `21.6 StateLayout Tests`
  - `22.5 Generated Path Allocation`
  - `23. Success Criteria`
- `docs/design/workflow_lisp_frontend_specification.md`
  - Sections 19-21, 45-48, 59, 65, 74-76, 95, 103-104
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_executable_ir.md`
- `docs/design/workflow_lisp_semantic_workflow_ir.md`
- `docs/design/workflow_lisp_source_map.md`
- `docs/design/workflow_command_adapter_contract.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/state.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/4/selector/selection.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/4/design-gap-architect/architecture-targets.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/4/design-gap-architect/existing-architecture-index.md`
- `docs/steering.md`

The slice must preserve these guardrails:

- keep shared path allocation, runtime-owned hidden-input binding, loaded-bundle
  transport, and Semantic IR state-layout projection under
  `orchestrator/workflow/`;
- keep Workflow Lisp lowering responsible for form-specific allocation requests
  and source provenance, not for inventing a second runtime path system;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files or value-view files as representations only;
- keep public authored workflow compatibility unchanged unless a separate
  versioned spec change widens that surface deliberately;
- keep hidden generated write-root inputs hidden from public workflow
  signatures and public migration-parity surfaces;
- keep run-isolation requirements strict for promotion-relevant private
  generated paths, while labeling preserved non-isolated shapes as
  compatibility-only;
- do not treat the empty `docs/steering.md` file as permission to widen scope.

`docs/design/workflow_command_adapter_contract.md` is authoritative here
because one currently reused compatibility seam,
`_managed_write_root_binding_step(...)`, is still a command-step helper with
inline Python. This slice may route that helper’s paths through the allocator,
but it must not expand the gap into uncertified new glue or pretend that path
centralization itself retires the helper’s command-boundary debt.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/executable-ir-runtime-plan/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-promoted-entry-hidden-reusable-call-binding/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-runtime-command-structured-output-conformance/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-private-artifact-catalog-state-lane/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-owner-seam-split-prerequisite/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`

### Decisions Reused

- Reuse the current frontend/runtime ownership split:
  Workflow Lisp lowering formulates typed requests and shared runtime modules
  own durable execution/state/path semantics.
- Reuse `WorkflowProvenance`, `LoadedWorkflowBundle`, `WorkflowRuntimePlan`,
  `SemanticWorkflowIR`, and `source_map.json` as the existing metadata carriers
  instead of inventing a parallel bundle format.
- Reuse the promoted-entry slice’s hidden-input rule:
  runtime-owned generated bindings stay off the public workflow boundary even
  when they are required for runtime execution.
- Reuse the source-map/runtime-lineage slice’s requirement that every generated
  path or hidden input have one authored origin and one stable traceable key.
- Reuse the command/provider structured-result lowering families and the
  private artifact lane from earlier runtime-foundation slices rather than
  redefining their semantics here.
- Reuse the state-layout design’s run-isolation invariant and the runtime-plan
  slice’s rule that derived views stay derived views, not second authorities.

### New Decisions In This Slice

- Add one shared allocation contract in `orchestrator/workflow/state_layout.py`
  that owns:
  allocation request normalization,
  concrete path selection,
  privacy classification,
  resume scope,
  stable semantic identity,
  and projection hints.
- Add one Workflow Lisp lowering bridge,
  `orchestrator/workflow_lisp/lowering/generated_paths.py`,
  as the only frontend-owned place that translates lowering situations into
  allocation requests.
- Persist generated path allocations as typed metadata on
  `WorkflowProvenance`, then derive:
  hidden generated inputs,
  workflow-boundary projection explanation,
  source-map entries,
  Semantic IR state-layout entries,
  and runtime-owned entry bindings
  from the same metadata.
- Keep the existing `__write_root__...` input-name shape as a compatibility
  projection in the first patch, but make the allocator metadata, not the
  hidden input name, the durable authority for generated private write paths.
- Introduce explicit compatibility labeling in allocation metadata so any
  preserved non-run-isolated concrete shape is machine-visible and excluded
  from promotion evidence.

### Conflicts Or Revisions

The promoted-entry hidden-binding slice and the command structured-output slice
already made hidden-input transport and runtime-owned bundle paths stricter, but
they still allowed path-family-specific helpers to synthesize their own
concrete locations. This slice narrows that implementation shape:

- hidden generated inputs remain valid;
- their names remain a compatibility projection;
- concrete path selection must move behind one shared allocator.

The source-map/runtime-lineage slice also treated generated-path provenance as
an origin-mapping problem. This slice revises that boundary narrowly:

- source-map origin coverage remains required;
- source maps stop being the only structured record of generated-path
  provenance;
- allocation identity, privacy, resume scope, and compatibility class now live
  upstream of `source_map.json` and are projected into it.

No shared concept is redefined. Core Workflow AST, Semantic IR,
ExecutableWorkflow, pointer authority, variant proof, and public authored
workflow contracts remain owned by their existing designs and specs.

## Ownership Boundaries

This slice owns:

- one shared allocation request/metadata schema for compiler-owned generated
  private paths;
- one shared allocator facade for concrete path selection;
- lowering-side request construction for the selected path families;
- provenance transport of generated allocations through
  `WorkflowProvenance` / `LoadedWorkflowBundle`;
- runtime/executable consumption of allocation metadata for entrypoint managed
  write-root binding;
- workflow-boundary, source-map, and Semantic IR projection from allocation
  metadata;
- focused tests for collision-proof allocation identity, run isolation,
  resume-stable reconstruction, hidden-input visibility, and provenance
  alignment.

This slice intentionally does not own:

- general public path-shape cleanup outside the selected generated private path
  families;
- retirement of the current inline command compatibility helper used for loop
  write-root binding;
- new runtime-native effects, new command adapters, or a change to adapter
  certification policy;
- review/revise-loop semantics, reusable-state validation semantics, provider
  prompt semantics, or collection publish/consume dataflow semantics beyond
  routing value-view paths once those files are materialized;
- redesign of public `artifacts`, `inputs`, `outputs`, or authored workflow
  path contracts.

## Current Checkout Facts

The current checkout already contains the substrate this slice should reuse,
and it also shows the exact missing boundary:

- `orchestrator/workflow_lisp/lowering/effects.py`,
  `lowering/values.py`,
  `lowering/phase_resource.py`,
  `lowering/phase_flow.py`,
  and `lowering/control_match.py`
  each synthesize `__write_root__{step_id}__result_bundle` directly and record
  only an origin span for the resulting path template.
- `orchestrator/workflow_lisp/lowering/workflow_calls.py::_managed_write_root_bindings(...)`
  synthesizes reusable-call write-root locations directly under
  `.orchestrate/workflow_lisp/calls/<caller>/<step>/<scope>/<callee>/...`
  instead of routing them through a shared allocation owner.
- `orchestrator/workflow_lisp/lowering/workflow_calls.py::_managed_write_root_binding_step(...)`
  still uses inline `python -c` to materialize loop-scoped binding bundles at
  `.orchestrate/workflow_lisp/call_bindings/.../__managed_write_roots.json`.
- `WorkflowExecutor._entry_managed_write_root_bindings(...)` independently
  synthesizes entrypoint hidden paths under
  `.orchestrate/workflow_lisp/entry/<run_id>/<workflow>/...`.
- `WorkflowProvenance` records `managed_write_root_inputs` and
  `runtime_context_inputs`, but it has no field for generated-path allocation
  metadata.
- `LoadedWorkflowBundle` already carries `surface`, `core_workflow_ast`,
  `semantic_ir`, `ir`, `projection`, `runtime_plan`, and `provenance`, so it
  is already the right transport seam for additional allocation metadata.
- `source_map.py` already serializes `generated_paths`, but those entries carry
  origin coverage only; they do not record privacy, resume scope, allocation
  role, or compatibility class.
- `semantic_ir.py` already emits `SemanticStateLayoutEntry` records, but only
  for presentation keys, resume checkpoints, managed write-root inputs, and
  runtime-context inputs; it does not yet emit entries for generated bundle or
  value-view paths.
- `loaded_bundle.workflow_public_input_contracts(...)` already hides managed
  write roots and runtime context inputs from public entrypoints, so the public
  boundary constraint for hidden generated inputs already exists.

## Feasibility Proof And Open Prerequisite

Short feasibility proof:

- the runtime already accepts typed build metadata carried through
  `LoadedWorkflowBundle`, `WorkflowProvenance`, `WorkflowRuntimePlan`, and
  `SemanticWorkflowIR`, so one more typed metadata family does not require a
  new bundle carrier;
- source-map and Semantic IR infrastructure already has stable id spaces,
  coverage validators, and serialized build artifacts, so allocation metadata
  can be projected rather than inventing a second provenance subsystem;
- entrypoint managed write roots are already runtime-owned and hidden, which
  proves the runtime can consume compiler-owned generated-path metadata without
  exposing it on the public boundary;
- call/write-root path families are already explicit enough in lowering to be
  classified by a closed role vocabulary instead of inferred from string
  prefixes later.

Open prerequisite that remains explicitly bounded:

- some reusable-call write-root locations still depend on the existing inline
  compatibility helper and, outside promoted-entry-style flows, may lack a
  runtime-owned run-scope ref. The first allocator patch must therefore:
  route those families through allocation metadata immediately,
  mark non-run-isolated preserved shapes as `compatibility_view`,
  and reserve promotion-grade `private_generated` status for call sites that
  have enough run/call-frame identity to satisfy the run-isolation invariant.
  Retiring the compatibility helper itself is separate command-adapter work.

## Architecture

### Shared Allocation Contract

Add one shared module, `orchestrator/workflow/state_layout.py`, that owns both
the semantic request shape and the concrete path allocator.

The request surface should be closed and typed, not free-form strings. The
first patch needs at least:

- `semantic_role`
  - `command_result_bundle`
  - `provider_result_bundle`
  - `variant_projection_bundle`
  - `materialized_value_view`
  - `reusable_call_write_root`
  - `entrypoint_managed_write_root`
- `privacy`
  - `public_authored`
  - `public_artifact`
  - `private_generated`
  - `compatibility_view`
  - `runtime_sidecar`
- `resume_scope`
  - `none`
  - `run`
  - `call_frame`
  - `loop_frame`
  - `loop_iteration`
  - `step_visit`
- `stable_identity`
- `workflow_name`
- `source provenance`
  - source span or lowering-origin key for traceability only
- `path_safety_policy`
- `projection_hints`
  - generated hidden-input name when needed
  - compatibility labels
  - selected runtime-scoping refs when runtime interpolation is required

The returned allocation metadata must include:

- `allocation_id`
- `semantic_role`
- `privacy`
- `resume_scope`
- `stable_identity`
- `concrete_path_template`
- `generated_input_name` when the path is injected through a hidden workflow
  input such as `__write_root__...`
- `path_safety_policy`
- `projection_hints`

The important architectural rule is negative: this metadata is not a finished
workflow-boundary projection, not a source-map entry, and not a Semantic IR
state-layout entry. It is the upstream shared object those projections must
derive from.

### Frontend Allocation Bridge

Add one lowering-owner bridge,
`orchestrator/workflow_lisp/lowering/generated_paths.py`, that converts
frontend lowering situations into allocation requests and records the returned
allocations on the lowering context.

This bridge becomes the only lowering-owned seam allowed to decide:

- which `semantic_role` a generated path belongs to;
- whether the path is `private_generated` or `compatibility_view`;
- which hidden generated input name, if any, is projected for runtime binding;
- which call-frame or loop identity participates in `stable_identity`;
- when a selected lowering route has enough runtime scope to satisfy the
  run-isolation invariant.

Existing path-string synthesis should move behind that bridge in these families:

- `provider-result` / `command-result` generated write roots
- `select_variant_output` or validator/projection bundle paths
- reusable workflow-call write roots
- loop-scoped binding-bundle helper paths
- future value-view file locations

`_LoweringContext.generated_path_spans` remains useful, but it becomes a
derived map keyed from recorded allocations rather than the primary generated
path registry. The allocator metadata is the thing persisted through the build
and runtime surfaces.

### Provenance Transport

Extend `WorkflowProvenance` with one typed `generated_path_allocations` field
that carries the allocator metadata across:

- `SurfaceWorkflow`
- `LoadedWorkflowBundle`
- imported-bundle metadata when needed for hidden write-root discovery
- frontend build artifacts

Compatibility rules for the first patch:

- keep `managed_write_root_inputs` for existing callers and public-input hiding;
- derive that list from `generated_path_allocations` where available;
- preserve prefix-based fallback only for old bundles without allocation
  metadata.

This lets the existing public/runtime input helpers keep their behavior while
stopping the hidden input name from being the only durable identifier.

### Downstream Projectors

Keep projection ownership explicit and split by layer.

Runtime / executable binding:

- `WorkflowExecutor` derives entrypoint managed write-root bindings from
  `generated_path_allocations` entries whose role is
  `entrypoint_managed_write_root`;
- override detection and resume-stable reuse continue to live in the runtime,
  but expected paths now come from allocator metadata rather than runtime-local
  string synthesis.

Workflow-boundary projection:

- `workflow_boundary_projection.json` continues to explain flattened inputs and
  generated internal inputs;
- generated internal inputs gain derived allocation references or role labels
  from the allocation metadata without becoming public user inputs.

Source maps:

- `source_map.json` emits generated-path entries from allocation metadata plus
  lowering provenance;
- source-map coverage still validates authored origin coverage, but it no
  longer has to infer path-family identity from strings alone.

Semantic IR:

- `semantic_ir.py` emits `SemanticStateLayoutEntry` rows for the selected
  generated path families using the allocator metadata;
- layout kinds should mirror the closed allocation roles rather than
  collapsing everything into `managed_write_root_input`;
- existing `managed_write_root_input` entries may remain as compatibility
  summaries when needed, but they stop being the only state-layout record for
  generated private write paths.

### Compatibility And Promotion Rules

The first patch must be honest about preserved shapes.

Allowed in the first allocator patch:

- preserve current hidden input names such as `__write_root__...` as
  compatibility projections;
- preserve current concrete path shapes only when they already satisfy run
  isolation or are explicitly marked `compatibility_view`;
- continue to use the current loop-scoped binding helper while routing its
  bundle path and emitted write-root values through allocator metadata.

Not allowed in the first allocator patch:

- silently treating static preserved shapes as promotion-grade private
  generated paths;
- deriving run-isolation only from a source span or formatting-sensitive key;
- adding a second ad hoc path allocator in lowering, runtime, or source-map
  code after the shared module exists.

The allocator must treat formatting-only source changes as provenance-only.
`stable_identity` must derive from semantic ownership:

- workflow identity
- semantic role
- authored target identity
- call-frame identity when applicable
- loop identity when applicable
- schema version when allocation semantics change

### Incremental Landing Order

The first implementation patch for this slice should land in this order:

1. Add shared allocation dataclasses and one allocator facade in
   `orchestrator/workflow/state_layout.py`.
2. Add the lowering bridge and route the selected generated path families to
   request allocations instead of synthesizing strings directly.
3. Persist allocation metadata on `WorkflowProvenance` and expose compatibility
   helpers from `loaded_bundle.py`.
4. Switch entrypoint managed write-root binding in `executor.py` to allocator
   metadata.
5. Project allocations into `workflow_boundary_projection.json`,
   `source_map.json`, and Semantic IR state-layout entries.
6. Add focused run-isolation, resume-stability, and collision-proof tests.

That order keeps the slice bounded: one metadata owner first, then projectors.

## Verification Targets

The implementation should be considered complete for this slice only when it
proves:

- command/provider result bundle paths, variant-projection bundle paths,
  reusable-call write roots, entrypoint managed write roots, and value-view
  paths all route through the shared allocator;
- generated internal inputs remain hidden from public workflow inputs;
- source-map and Semantic IR views both derive from the same allocation
  metadata;
- repeated calls, loop iterations, and match arms produce collision-proof
  allocation identities;
- resume reconstructs the same allocation for the same run and call-frame or
  loop identity;
- preserved non-isolated shapes are explicitly labeled
  `compatibility_view` and do not count as promotion evidence;
- `git diff --check` passes.
