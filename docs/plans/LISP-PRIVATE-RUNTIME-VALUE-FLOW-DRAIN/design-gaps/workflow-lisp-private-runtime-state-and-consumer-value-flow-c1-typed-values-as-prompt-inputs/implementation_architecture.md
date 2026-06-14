# Workflow Lisp Private Runtime Value Flow C1 Typed Values As Prompt Inputs Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-private-runtime-state-and-consumer-value-flow-c1-typed-values-as-prompt-inputs`
Target design: `docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected C1 gap:

- allow provider prompt inputs to bind typed Workflow Lisp values directly;
- render those typed values through registered deterministic renderers at the
  provider prompt-composition seam;
- avoid producer-authored prompt-input files and phase prompt-input
  `materialize_artifacts` steps for C1-eligible prompt inputs;
- record renderer id, renderer version, typed value identity, source value
  provenance, and rendered bytes digest in composed-prompt evidence; and
- prove that provider structured-output authority is unchanged.

Out of scope for this slice:

- observability-derived human summaries;
- entrypoint `:publish` syntax or terminal-boundary publication lowering;
- compatibility bridge generation, deletion, or bridge-retirement metadata;
- durable/ephemeral rendering cleanup beyond prompt-rendering rows selected by
  C0;
- retiring body-level `materialize-view` rows whose consumer is not provider
  prompt injection;
- changing provider or command structured-output target binding;
- changing renderer byte formats, renderer ids, renderer versions, or
  target-path allocation;
- adding scripts, inline Python/shell, command steps, or certified adapters;
- changing checkpoint schema, restore behavior, effect-boundary policies,
  transition-aware resume, or default-resume selection; and
- redefining Core Workflow AST, Semantic Workflow IR, Executable IR,
  TypeCatalog, SourceMap, pointer authority, variant proof, provider output
  authority, or transition semantics.

This is an implementation architecture for one Track C behavior slice. It is
not a replacement product design and it does not complete C2-C5.

## Problem Statement

C0 added `workflow_lisp_consumer_rendering_census.v1` and the current checkout
has checked prompt-injection rows for the Design Delta parent-drain family.
Those rows prove which prompt-input files are render-only plumbing and which
provider/prompt extern bindings currently consume them. They do not yet change
execution behavior.

The current lowering still routes phase/provider prompt inputs through
producer-owned file materialization:

- `_build_phase_prompt_input_prelude(...)` and
  `_build_phase_stdlib_prompt_input_prelude(...)` flatten typed inputs into
  `materialize_artifacts` values and compatibility pointer paths;
- lowered provider steps still expose only `input_file` or `asset_file` prompt
  sources plus `consumes`/`prompt_consumes`;
- `PromptComposer` reads file-backed prompt sources and injects consumed
  artifacts, but it has no runtime-owned typed prompt-input rendering lane;
- Semantic IR prompt surfaces record `input_file`, `asset_file`, and
  `prompt_consumes`, but not typed rendered prompt inputs; and
- prompt audit logs can show the composed prompt text, but there is no
  machine-readable evidence that a typed value was rendered at the prompt seam.

The selected gap is therefore a narrow runtime/frontend transport lane:
provider prompts should consume typed values as prompt inputs without an
earlier workflow step writing prompt-input files solely for that consumer.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md`
  Sections 7.2, 8, 10 C0-C1, 11, 12, 13, 15, 16.3, and 17;
- `docs/design/workflow_lisp_frontend_specification.md` Sections 16, 17.1,
  18.1, 19.2, 20, 22, 22.2, 22.3, 45, 47, 48, 59, 61, 62, 66, 74, 76.1, and
  105.1;
- `specs/providers.md` for normative prompt composition, provider prompt
  source separation, `consumes` injection, output-contract suffixes, and
  runtime-owned structured-output targets;
- `docs/design/workflow_lisp_runtime_migration_foundation.md` for private
  value transport, provider prompt composition authority, and fail-closed
  structured-output behavior;
- `docs/design/workflow_lisp_state_layout.md` for generated path allocation
  ownership, which this slice does not widen for ephemeral prompt rendering;
- `docs/design/workflow_command_adapter_contract.md` for the rule that this
  slice must not replace render-only prompt plumbing with command glue;
- the U0 shared-census architecture;
- the C0 rendering-census architecture and checked C0 manifest/report;
- the R1 through R6 implementation architectures as completed Track R context
  that this Track C slice must not reopen; and
- `docs/capability_status_matrix.md` when implementation work needs current
  surface status.

Guardrails:

- Typed values, structured provider/command bundles, resources, and transition
  audit remain semantic authority.
- Rendered prompt text is a view delivered to the provider. It is never a typed
  semantic input, artifact value, pointer file, or provider output authority.
- Provider structured output still comes only from the declared
  `output_bundle.path` or `variant_output.path`, with the runtime-owned
  `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` binding unchanged.
- Prompt text, prompt audit files, rendered prompt fragments, and renderer
  evidence must not satisfy output bundles, variant bundles, route decisions,
  or parity semantic output.
- C1 eligibility comes from checked C0 rows with
  `consumer_lane: prompt_injection`, not from field-name inference.
- Existing YAML and legacy `.orc` prompt sources continue to work. C1 is an
  additive prompt-input lane for Workflow Lisp lowered provider steps.
- No new renderer may depend on target allocation, wall-clock time, random
  values, filesystem reads, provider output text, command stdout, or pointer
  files.
- The empty `docs/steering.md` file in this checkout does not widen scope.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-c0-rendering-census-and-renderer-seam-verification/implementation_architecture.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-u0-shared-census/implementation_architecture.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-r1-checkpoint-schema-shadow-emission/implementation_architecture.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-r2-restore-for-pure-and-structured-regions/implementation_architecture.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-r3-effect-boundary-resume-policies/implementation_architecture.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-r4-transition-aware-resume/implementation_architecture.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-r5-resume-only-authored-plumbing-retirement/implementation_architecture.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-r6-default-flip-and-legacy-cleanup/implementation_architecture.md`

### Decisions Reused

- Reuse U0's checked value-flow census as the inventory authority for
  prompt-rendering path plumbing.
- Reuse C0's `workflow_lisp_consumer_rendering_census.v1` rows to identify
  prompt-injection candidates. C1 does not create a second render-only census.
- Reuse C0 consumer lanes and durability classes. C1 only consumes rows where
  `consumer_lane == "prompt_injection"`.
- Reuse `orchestrator/workflow_lisp/consumer_rendering_census.py` and its C0
  report as prerequisite evidence.
- Reuse `orchestrator/workflow/view_renderer.py` as the renderer registry and
  deterministic byte-rendering authority.
- Reuse the existing prompt extern source model in
  `orchestrator/workflow_lisp/workflows.py`: prompt externs still identify the
  base prompt asset/input source. Typed prompt inputs are additional prompt
  composition inputs, not a replacement prompt extern format.
- Reuse `PromptComposer` as the runtime prompt-composition owner.
- Reuse Semantic IR prompt-surface and executable provider-step projections as
  derived evidence surfaces, extending them additively.
- Reuse R1-R6 checkpoint/resume decisions by leaving private checkpoint
  records, restore reports, and transition audit untouched.
- Reuse the command-adapter contract by keeping C1 runtime-native prompt
  rendering out of command steps and adapter scripts.

### New Decisions In This Slice

- Add a C1 prompt-rendering schema:
  `workflow_lisp_typed_prompt_input.v1`.
- Add a C1 prompt-rendering evidence schema:
  `workflow_lisp_typed_prompt_input_evidence.v1`.
- Add a C1 build/runtime report schema:
  `workflow_lisp_typed_prompt_input_report.v1`.
- Add a lowered provider-step field, tentatively `typed_prompt_inputs`, whose
  entries name a typed value source, renderer descriptor, source-map origin,
  and C0/U0 row lineage.
- Add an internal prompt-rendering lane in `PromptComposer` that renders
  `typed_prompt_inputs` in memory immediately before provider invocation.
- Add composed-prompt evidence sidecars or prompt-audit metadata that record
  renderer id/version, typed value digest, rendered bytes digest, source value
  lineage, C0 row id, prompt surface id, provider step id, and insertion order.
- Treat C1 rendered prompt fragments as ephemeral by default. They allocate no
  durable view path and are not published unless a later C3/C4/C5 slice adds a
  separate publication or bridge policy.
- Update Design Delta C0 prompt-injection rows from `KEEP_TYPED` prerequisite
  evidence to C1 runtime evidence only after the provider step no longer needs
  the producer-authored prompt-input materialization for that row.

### Conflicts Or Revisions

C0 explicitly left typed prompt input rendering out of scope and recorded
prompt rows as evidence only. C1 consumes those rows and implements the
behavior for prompt-injection candidates. This is an additive continuation of
C0, not a replacement of its census schema.

Current phase lowering materializes prompt inputs through
`materialize_artifacts` plus pointer paths. C1 revises that lowering only for
C1-eligible prompt-injection rows. Rows whose consumer is
`timed_body_materialization`, `human_observability`, `entry_publication`, or
`compatibility_bridge` remain governed by their existing C0 decisions and later
C2-C5 slices.

No R1-R6 checkpoint/resume decision is revised. No shared concepts are
redefined. Core Workflow AST, Semantic Workflow IR, Executable IR, TypeCatalog,
SourceMap, pointer authority, variant proof, provider/command output
authority, and resource-transition semantics remain owned by their existing
documents and modules.

## Ownership Boundaries

This slice owns:

- a small prompt-input helper module, proposed
  `orchestrator/workflow_lisp/typed_prompt_inputs.py`, for C1 schema
  constants, deterministic value serialization, renderer binding validation,
  digesting, report construction, and diagnostics;
- additive frontend lowering changes in
  `orchestrator/workflow_lisp/lowering/phase_scope.py` and the WCC
  provider-result path to emit `typed_prompt_inputs` instead of prompt-input
  materialization for C1-eligible rows;
- additive Core Workflow AST / executable provider-step fields for typed
  prompt inputs, only as an internal executable transport;
- additive Semantic IR prompt-surface fields that expose typed prompt-input
  lineage and renderer descriptors for diagnostics and explain output;
- `PromptComposer` support for in-memory typed prompt-input rendering through
  the existing renderer registry;
- composed-prompt evidence emission and validation for typed prompt inputs;
- build integration that joins C0 prompt-injection rows with compiled provider
  surfaces and emits `typed_prompt_input_report.json`;
- focused tests for schema validation, lowering selection, prompt composition,
  evidence emission, source-map lineage, and provider output authority
  isolation; and
- one Design Delta parent-drain compile/build or dry-run smoke proving a
  provider prompt consumes a typed value without a producer-authored
  prompt-input file.

This slice intentionally does not own:

- renderer byte format changes or a general renderer plugin system;
- prompt extern source semantics beyond preserving current `asset_file` /
  `input_file` behavior;
- provider/command structured-output validators or bundle target binding;
- materialized-view runtime semantics;
- observability summary rendering;
- entrypoint publication policy;
- compatibility bridge metadata or bridge retirement;
- command adapter certification, command-boundary manifests, or adapter
  execution;
- checkpoint schema, checkpoint restore, effect policies, transition-aware
  resume, default-resume selection, or resume-only cleanup;
- migration promotion thresholds or primary-surface selection; or
- repo-wide strict lint enforcement.

## Proposed Data Model

### Lowered Typed Prompt Input

Each C1-eligible provider step receives an internal `typed_prompt_inputs`
sequence:

```json
{
  "schema_version": "workflow_lisp_typed_prompt_input.v1",
  "binding_name": "plan_inputs",
  "renderer": {
    "renderer_id": "canonical-json",
    "renderer_version": 1,
    "accepted_shape": "any_pure_value"
  },
  "value_source": {
    "kind": "typed_binding_ref",
    "type_name": "PlanPromptContext",
    "binding_ref": "root.steps.BuildPlanPromptContext.outputs.context",
    "value_digest": "sha256:..."
  },
  "lineage": {
    "u0_row_id": "plan_phase.prompt.draft",
    "c0_row_id": "c0.plan_phase_prompt_draft",
    "source_map_origin_key": "..."
  },
  "injection": {
    "position": "prepend",
    "label": "plan_inputs"
  }
}
```

The `value_source` is a typed value or validated private value reference
already available to the provider step. It is not a file path unless the typed
value itself is a path value. Rendered bytes are computed by the runtime
composer and are not written as durable artifacts.

### Runtime Prompt Evidence

For every rendered typed prompt input, the runtime records evidence:

```json
{
  "schema_version": "workflow_lisp_typed_prompt_input_evidence.v1",
  "workflow_name": "lisp_frontend_design_delta/plan_phase::run-plan-phase",
  "step_id": "DraftPlan",
  "prompt_surface_id": "prompt:lisp_frontend_design_delta/plan_phase::run-plan-phase:DraftPlan",
  "binding_name": "plan_inputs",
  "renderer_id": "canonical-json",
  "renderer_version": 1,
  "typed_value_identity": {
    "type_name": "PlanPromptContext",
    "value_digest": "sha256:...",
    "source_ref": "root.steps.BuildPlanPromptContext.outputs.context"
  },
  "rendered_bytes_digest": "sha256:...",
  "source_map_origin_key": "...",
  "u0_row_id": "plan_phase.prompt.draft",
  "c0_row_id": "c0.plan_phase_prompt_draft",
  "authority": "prompt_view_only"
}
```

The evidence may live beside existing prompt audit logs or in a structured
run-local sidecar referenced by prompt audit metadata. The evidence is
diagnostic and parity-supporting. It is not a workflow output, artifact,
checkpoint, or semantic result.

### Build Report

Add a build artifact for selected Workflow Lisp families:

```text
.orchestrate/build/<hash>/typed_prompt_input_report.json
```

Top-level shape:

```json
{
  "schema_version": "workflow_lisp_typed_prompt_input_report.v1",
  "target_family": "lisp_frontend_design_delta_parent_drain",
  "source_census": {},
  "consumer_rendering_census": {},
  "prompt_input_rows": [],
  "provider_surfaces": [],
  "materialization_retirements": [],
  "authority_checks": [],
  "diagnostics": [],
  "status": "pass"
}
```

The report fails when:

- a C0 prompt-injection row has no matching provider prompt surface;
- a selected provider step still requires a generated prompt-input file for
  the same row;
- a typed prompt input lacks renderer metadata, value type, source-map origin,
  C0/U0 lineage, or deterministic value digest;
- a rendered prompt fragment is consumed as typed semantic input;
- output-contract evidence points at prompt evidence instead of a declared
  bundle target; or
- rendered bytes depend on generated target allocation.

## Lowering And Runtime Flow

1. C1 eligibility starts from the checked C0 report. Only rows with
   `consumer_lane: prompt_injection` and valid prompt/provider extern evidence
   can be selected.
2. The Workflow Lisp lowering path preserves the base prompt extern. It does
   not remove `asset_file` / `input_file` from the provider step unless the
   prompt extern itself changes under existing rules.
3. For selected typed values, lowering emits `typed_prompt_inputs` on the
   provider step and suppresses the old prompt-input materialization prelude
   for the same C0 row.
4. Core AST, Semantic IR, executable IR, runtime plan, and source map carry the
   typed prompt-input metadata as internal prompt-composition evidence.
5. At runtime, `PromptComposer` reads the base prompt source, applies asset and
   dependency injection, renders typed prompt inputs in memory with the
   registered renderer, applies existing `consumes` injection and output
   contract suffixes, and returns the composed prompt.
6. Provider execution proceeds through the existing provider executor. The
   runtime-owned `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` binding and bundle
   validation rules are unchanged.
7. Prompt audit/evidence records the typed prompt-input renderings and their
   digests. The evidence is linked to the provider step and source-map origin.

The insertion order must be deterministic. Recommended order:

1. `asset_depends_on` content blocks;
2. typed prompt-input blocks;
3. base prompt text;
4. existing `consumes` injection according to its configured prepend/append
   policy; and
5. output-contract suffix.

If this order conflicts with existing prompt fixtures during implementation,
the implementation plan must preserve normative `specs/providers.md` behavior
and document the chosen insertion point in tests. The architecture requirement
is deterministic evidence-backed rendering, not a new prompt templating
language.

## Provider Authority Preservation

C1 changes provider input composition only. It must not change:

- provider alias resolution;
- provider command template selection;
- provider session handling;
- managed-job wrapping;
- output bundle path resolution;
- `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` precedence;
- output bundle or variant bundle validation;
- stdout/stderr capture semantics; or
- retry/timeout behavior.

Provider structured output remains authoritative only after the runtime
validates the declared bundle at the declared runtime-owned target. Prompt
rendering evidence is never accepted as output evidence.

## Diagnostics

Add stable diagnostics:

- `typed_prompt_input_row_missing`: C0 prompt-injection row has no compiled
  provider prompt surface.
- `typed_prompt_input_value_unavailable`: selected typed value cannot be
  projected at the provider step.
- `typed_prompt_input_renderer_unknown`: renderer id/version is not
  registered.
- `typed_prompt_input_renderer_shape_mismatch`: value document does not match
  the renderer's accepted shape.
- `typed_prompt_input_source_map_missing`: source-map origin or C0/U0 lineage
  is absent.
- `typed_prompt_input_materialization_still_required`: a selected row still
  depends on producer-owned prompt-input file materialization.
- `typed_prompt_input_rendered_view_used_as_state`: rendered bytes or prompt
  evidence are consumed as typed semantic input.
- `typed_prompt_input_provider_authority_violation`: prompt evidence is used
  as provider output authority or bundle evidence.

Diagnostics should include workflow name, provider step id, prompt surface id,
C0 row id, U0 row id, source-map origin key when available, and the selected
renderer descriptor.

## Feasibility Proof

This slice relies on three existing capabilities:

- C0 can identify prompt-injection rows and prove renderer target
  independence through `consumer_rendering_census.py`.
- The renderer registry can render pure typed value documents deterministically
  through `render_view(...)`.
- `PromptComposer` already owns in-memory prompt composition and therefore is
  the correct runtime seam for rendering prompt-only views.

Implementation must add one narrow proof before broad Design Delta use:

- a minimal `.orc` fixture with a provider step whose prompt input is a typed
  record or pure projection value;
- compile evidence showing the provider step has `typed_prompt_inputs` and no
  prompt-input `materialize_artifacts` producer for that row;
- runtime or dry-run evidence showing the composed prompt includes the rendered
  typed value and writes C1 evidence; and
- negative evidence showing the provider output bundle still must be written to
  the declared bundle target.

If the current executable provider-step schema cannot carry internal
`typed_prompt_inputs` without widening public YAML behavior, the implementation
must keep the field executable-private and record the missing public-schema
support as an implementation prerequisite. It must not encode typed prompt
inputs through hidden `input_file` rewrites.

## Verification Plan

Focused checks:

- unit tests for `typed_prompt_inputs.py` schema validation, value digesting,
  renderer validation, and evidence serialization;
- prompt-composer tests proving typed values render in memory, in deterministic
  order, with evidence digests and without disk prompt-input files;
- lowering tests proving C1-eligible rows suppress old phase prompt-input
  materialization for the same row;
- Semantic IR / executable IR tests proving prompt surfaces expose typed
  prompt-input metadata and source maps;
- negative tests for unknown renderer, shape mismatch, missing C0 row, missing
  source-map origin, rendered view used as typed state, and prompt evidence used
  as output authority; and
- provider structured-output tests proving wrong-path bundles still fail even
  when typed prompt rendering succeeds.

Family-level checks:

- build the Design Delta parent-drain entrypoint with the checked provider,
  prompt, command-boundary, U0, and C0 manifests;
- assert `consumer_rendering_census_report.json` remains passing;
- assert `typed_prompt_input_report.json` passes and references the expected
  C0 prompt-injection rows; and
- run at least one provider dry-run or local fake-provider smoke that captures
  composed-prompt evidence without requiring a producer-authored prompt-input
  file.

## Implementation Handoff

Recommended implementation order:

1. Add C1 schemas and pure helpers in
   `orchestrator/workflow_lisp/typed_prompt_inputs.py`.
2. Extend provider-step data carriers additively with internal
   `typed_prompt_inputs`.
3. Extend lowering to emit typed prompt inputs for one small fixture, then for
   checked C0 prompt-injection rows.
4. Extend `PromptComposer` to render typed prompt inputs and return structured
   evidence alongside prompt text.
5. Wire evidence into prompt audit/runtime sidecars and Semantic IR prompt
   surfaces.
6. Add build report generation and Design Delta family reconciliation.
7. Add negative authority checks and provider-output preservation tests.

The first implementation tranche should select one prompt-injection row, such
as `plan_phase.prompt.draft` or `selector.prompt.select_next_work`, and prove
the seam before flipping every Design Delta prompt row.

