# Frontend Validation And Diagnostics Pipeline Implementation Architecture

## Scope

This design gap covers only the bounded validation and diagnostics pipeline
slice selected for the Workflow Lisp frontend:

- define one implementation-ready validation pipeline over the existing staged
  `.orc` compiler;
- assign each validation category to the frontend, shared validation, or a
  split handoff with explicit boundaries;
- make diagnostic emission deterministic across parse, module, macro, typing,
  effect, lowering, source-map, and shared-validation failures;
- map the full-design validation and error-taxonomy sections onto the current
  implementation substrate without fabricating unavailable Core AST or
  Semantic IR surfaces;
- preserve structured subject-ref remapping and authored provenance through the
  shared validation bridge.

Out of scope for this tranche:

- new language forms, new stdlib forms, or behavior changes to parsing,
  modules, macros, procedures, workflow refs, phase/resource/drain lowering,
  or runtime execution;
- redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog,
  SourceMap, pointer authority, variant proof, queue semantics, or persisted
  state layout;
- new command-adapter certification policy, new legacy-adapter policy, or
  runtime-native effect promotion;
- a second validator, YAML-as-authority fallback, or report/pointer recovery
  logic outside explicit typed contracts.

This is an implementation architecture for the selected validation/diagnostics
gap only. It does not replace the product design in
`docs/design/workflow_lisp_frontend_specification.md`.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_frontend_specification.md`
  - `59. Validation Sequence`
  - `60. Type Validation`
  - `61. Effect Validation`
  - `62. Contract Validation`
  - `63. Variant Proof Validation`
  - `64. Snapshot Validation`
  - `65. Pointer Authority Validation`
  - `66. Report-Authority Validation`
  - `67. Frontend Parse/Module Errors`
  - `68. Macro Errors`
  - `69. Type Errors`
  - `70. Effect Errors`
  - `71. Authority Errors`
  - `72. Lowering Errors`
  - `73. Existing v2.14 Errors Reused`
  - `74. Source Map Requirements`
  - `76.1 Editor And Lint Tooling Compatibility`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `9. Source Spans And Diagnostics`
  - `10. Validation`
  - `14. Implementation Stages`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/steering.md`

The slice must also preserve the guardrails established by prior
implementation-architecture documents:

- keep `orchestrator/workflow_lisp/` as the frontend-owned package and keep
  shared runtime semantics under `orchestrator/workflow/`;
- reuse the staged frontend pipeline:
  read -> syntax -> modules -> macro expansion -> definitions/callables ->
  typecheck/effects -> lowering -> shared validation -> executable/runtime
  artifacts;
- reuse `SourcePosition`, `SourceSpan`, recursive syntax provenance,
  `LispFrontendDiagnostic`, `LoweringOriginMap`, structured validation subject
  refs, and the persisted source-map bridge rather than inventing parallel
  provenance systems;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- reuse the existing authored-mapping ->
  `elaborate_surface_workflow(...)` ->
  `lower_surface_workflow(...)` seam rather than creating a second validator.

`docs/design/workflow_command_adapter_contract.md` is authoritative here
because the validation pipeline must classify and diagnose `.orc`
`command-result`, `resume-or-start`, `resource-transition`, and other
command-backed boundaries without allowing hidden workflow semantics in shell
text, pointer files, or report parsing.

`docs/steering.md` is empty in this checkout. That is not permission to widen
scope. The selector bundle, target contract, and prior implementation
architectures remain the effective steering surfaces.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/executable-ir-runtime-plan/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/hygienic-defmacro-system/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/lisp-frontend-cli-diagnostics-surface/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/module-import-export-resolution/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resource-drain-library/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resume-or-start-reusable-state-validation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-boundary-type-flattening/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md`

### Decisions Reused

- Reuse the existing frontend package ownership split and staged compile
  pipeline rather than centralizing semantics under `orchestrator/workflow/`.
- Reuse `LispFrontendDiagnostic` as the only user-visible diagnostic channel,
  with source spans, form paths, expansion provenance, and source-map remap
  notes preserved across passes.
- Reuse `LoweringOriginMap`, structured validation subject refs, and the
  persisted `source_map.json` lineage bridge rather than inventing a second
  remap mechanism for shared-validation failures.
- Reuse existing command-boundary classification:
  `external_tool` versus `certified_adapter`, including
  `command_adapter_missing_contract` and declared `source_map_behavior`.
- Reuse the honesty rule from the CLI/build and source-map slices:
  do not fabricate `core_workflow_ast` or `semantic_ir` validation surfaces
  before the shared codebase exposes them as first-class implemented
  contracts.

### New Decisions In This Slice

- Add one dedicated frontend-owned validation pipeline layer that orders all
  existing local validators and the shared-validation bridge under one pass
  catalog.
- Split diagnostic metadata into:
  - coarse `phase` for CLI/build compatibility;
  - exact `validation_pass` for spec-level ownership and filtering;
  - `authority_layer` to distinguish frontend-local failures from preserved
    shared-validation errors.
- Implement report-authority and pointer-authority checks as a split model:
  frontend preflight forbids invalid authored surfaces, while shared validation
  remains authoritative for lowered pointer/publication/path semantics.
- Treat the lint names in `workflow_command_adapter_contract.md` as hard
  frontend diagnostics on new high-level `.orc` workflows when those patterns
  appear in command-backed lowering surfaces.
- Keep validation orchestration internal to compilation and diagnostic
  serialization. This slice does not add a new persisted `validation_report`
  artifact.

### Conflicts Or Revisions

The Stage 1 parser/core slice and later feature slices describe validation
inside feature-local modules such as `definitions.py`, `typecheck.py`,
`procedures.py`, and `workflows.py`. This slice revises the implementation
shape narrowly:

- those modules remain the authorities for the rules they own;
- `validation.py` becomes the single orchestrator that invokes them in a fixed
  order and classifies the resulting diagnostics by pass.

The CLI/diagnostics slice already defined a serialized diagnostic envelope with
`phase`. This slice extends that contract narrowly:

- keep `phase` for backward-compatible grouping;
- add `validation_pass` and `authority_layer`;
- keep `code` as the authoritative machine key.

The full design lists separate passes for snapshot, pointer authority,
workflow-call, and state-layout validation. The current implementation bridge
cannot honestly reimplement those checks in a parallel frontend validator.
This slice therefore makes the ownership split explicit:

- frontend validates authored shape, lowerability, and authority violations it
  can know before lowering;
- shared validation remains authoritative for lowered snapshot refs, pointer
  publication conflicts, call-boundary validity, contract refinement, and
  state-layout/path safety.

No prior slice is revised on shared concepts such as spans, diagnostics, Core
Workflow AST, Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority,
or variant proof.

## Ownership Boundaries

This slice owns:

- the pass catalog, pass ordering, blocking rules, and diagnostic aggregation
  for Workflow Lisp compilation;
- frontend-local validation passes for parse, module, macro, type, effect,
  reference, contract-preflight, proof, authority-preflight, lowering-surface,
  and source-map coverage checks;
- diagnostic metadata mapping:
  `phase`,
  `validation_pass`,
  `authority_layer`,
  shared-code reuse, and deterministic severity classification;
- the remap adapter that converts shared-validation failures with structured
  subject refs into source-mapped frontend diagnostics while preserving shared
  codes;
- focused tests for pass ordering, ownership mapping, shared-code preservation,
  command-boundary errors, authority failures, and subject-ref remapping.

This slice intentionally does not own:

- parse grammar, module semantics, macro semantics, procedure semantics,
  workflow-ref semantics, phase/resource/drain behavior, or boundary lowering
  rules already owned by prior slices;
- shared runtime/path/snapshot/pointer/call validation semantics under
  `orchestrator/workflow/`;
- the source-map schema, executable IR schema, runtime plan schema, or CLI
  command parsing beyond carrying richer diagnostic metadata through existing
  serialization;
- new command adapters, legacy adapters, or runtime-native promotion policy.

## Current Checkout Facts

The current checkout already contains most of the feature-local rules this
slice needs to coordinate:

- parser/core syntax owns read, header, definition-shape, and unknown-type
  diagnostics;
- typed-expression, module, macro, workflow, procedure, phase/resource/drain,
  and workflow-ref slices already define pass-local diagnostics and ownership;
- the CLI/build slice already serializes diagnostics and exposes a `phase`
  field in `diagnostics.json`;
- the source-map slice already defines the structured-subject remap direction
  and executable/runtime lineage coverage model;
- shared validation remains the existing authority for authored workflow
  elaboration, path safety, contract refinement, pointer publication, bundle
  validation, workflow-call semantics, and executable lowering.

What is still missing is one implementation-ready document that says:

- which pass runs when;
- which layer owns each check;
- which codes are frontend-local versus preserved shared codes;
- how authority-related checks from the command-adapter contract surface on
  `.orc` workflows without duplicating the shared validator.

## Proposed Package Boundary

Extend the current frontend package with one dedicated orchestration layer and
narrow diagnostic metadata additions:

```text
orchestrator/workflow_lisp/
  validation.py        # new pass catalog, ordering, gating, result model
  diagnostics.py       # extend metadata mapping and shared-code remap helpers
  compiler.py          # invoke validation pipeline across staged compile steps
  build.py             # serialize validation metadata through diagnostics.json
  reader.py            # parse-pass contributor, reused
  modules.py           # module/reference-pass contributor, reused
  macros.py            # macro-pass contributor, reused
  definitions.py       # definition/header contributor, reused
  typecheck.py         # type/proof-pass contributor, reused
  effects.py           # effect-pass contributor, reused
  workflows.py         # workflow/reference/contract contributor, reused
  procedures.py        # procedure/effect/reference contributor, reused
  contracts.py         # contract-preflight contributor, reused
  lowering.py          # lowering + origin-map + subject binding contributor
  source_map.py        # source-map coverage validator input, reused
orchestrator/
  exceptions.py        # shared ValidationError/ValidationSubjectRef, reused
  workflow/
    elaboration.py     # shared validation authority, reused
    lowering.py        # executable lowering authority, reused
    executable_ir.py   # runtime/executable identity surface, reused
```

Responsibilities:

- `validation.py`
  - define the pass ids, pass order, blocking policy, and aggregate result;
  - call feature-local validators without re-implementing their semantics;
  - decide when shared validation is allowed to run.
- `diagnostics.py`
  - centralize pass-to-phase mapping and severity mapping;
  - preserve reused shared codes exactly;
  - render remap notes when subject-ref remapping or compatibility fallback was
    used.
- `compiler.py`
  - build the staged compilation state and invoke `run_validation_pipeline(...)`
    at the correct checkpoints.
- `build.py`
  - serialize the richer diagnostic metadata already produced by the pipeline;
  - keep `diagnostics.json` as the persisted surface instead of adding a new
    validation artifact.

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/source_map.py`
- `orchestrator/workflow_lisp/build.py` source-map artifact schema
- `orchestrator/workflow/surface_ast.py`
- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/runtime_observability.py`

## Data Model

### Validation Pass Catalog

Add one frontend-owned pass id enum:

- `parse`
- `module`
- `macro`
- `type`
- `effect`
- `reference`
- `contract`
- `proof`
- `authority`
- `lowering_surface`
- `source_map`
- `shared_validation`
- `executable`

The pass id is the precise machine-readable classification for implementation
ownership and test filtering. It is distinct from the broader CLI/build
`phase`.

### Validation Pipeline State

`validation.py` should orchestrate existing stage artifacts, not invent a new
semantic IR. One bounded aggregate is sufficient:

```text
ValidationPipelineState(
  module_graph?,
  expanded_modules?,
  callable_catalog?,
  typed_callables?,
  lowered_workflows?,
  source_map_document?,
  validated_bundles?,
  executable_workflows?,
)
```

Each field is optional because earlier passes may fail before later artifacts
exist.

### Pass Result

Each pass produces one deterministic record:

```text
ValidationPassResult(
  pass_id,
  authority_layer,
  blocking,
  diagnostics,
  artifact_ready,
)
```

`authority_layer` values:

- `frontend`
- `shared_validation`

This slice does not add a third authority. Split ownership is represented by
two passes contributing findings to the same spec-level category.

### Diagnostic Metadata

`LispFrontendDiagnostic` remains the authoritative frontend diagnostic record.
This slice extends the metadata it carries or serializes:

- `code`
- `message`
- `span`
- `form_path`
- `notes`
- `phase`
- `validation_pass`
- `authority_layer`

Rules:

- `code` stays the stable machine key;
- `phase` remains the coarse CLI/build grouping;
- `validation_pass` is the exact validation owner/filter key;
- shared-validation errors keep their shared code and receive
  `authority_layer = shared_validation`;
- subject refs are used internally for remapping and may be summarized in
  notes, but they are not promoted to a second user-visible error channel.

## Validation Model

### Ordered Pipeline

Run validation in this order:

1. `parse`
   - reader and root-form validation
   - blocks all later passes on failure
2. `module`
   - header, module-name, import/export, duplicate-definition, and graph checks
3. `macro`
   - macro lookup, arity, determinism, hygiene, and expansion-shape checks
4. `type`
   - expression typing, workflow/procedure signature checks, boundary-type
     legality, and return-type checks
5. `effect`
   - effect summary closure, declared-versus-inferred effect checks, hidden
     provider/command/state effects
6. `reference`
   - name resolution, extern binding resolution, same-file or cross-module
     callable lookup, workflow-ref linkage, and boundary dependency lookup
7. `contract`
   - frontend contract preflight:
     boundary lowerability,
     structured-result contract derivation,
     `Json` surface bans,
     reusable-state contract formation,
     adapter contract presence
8. `proof`
   - variant-proof availability and wrong-variant usage
9. `authority`
   - report-authority bans,
     pointer-authority authored-surface bans,
     inline command-glue bans,
     certified-adapter policy checks
10. `lowering_surface`
   - deterministic lowering feasibility,
     generated id stability,
     boundary projection coverage,
     backend availability
11. `source_map`
   - pre-shared-validation coverage of every generated validation subject and
     runtime-visible lowered surface
12. `shared_validation`
   - shared authored-mapping elaboration and lowering, preserving reused shared
     codes
13. `executable`
   - executable IR/runtime-lineage coverage and final executable-surface
     validation metadata

Passes `parse` through `authority` may accumulate multiple diagnostics in one
compile attempt. `lowering_surface`, `source_map`, `shared_validation`, and
`executable` run only when their required upstream artifacts exist.

### Spec-To-Implementation Ownership Map

| Full-design category | Implemented pass or split | Authority owner | Notes |
| --- | --- | --- | --- |
| Parse validation | `parse` | Frontend | Reader/root-form only. |
| Module validation | `module` | Frontend | Header/import/export/graph ownership. |
| Macro validation | `macro` | Frontend | Expansion rules stay frontend-local. |
| Type validation | `type` | Frontend | Includes workflow/procedure signature checks. |
| Effect validation | `effect` | Frontend | Uses effect summaries from existing slices. |
| Reference validation | `reference` | Frontend | Names, externs, workflow refs, callables. |
| Contract validation | `contract` + `shared_validation` | Split | Frontend checks lowerability; shared validation checks refinement and runtime-facing contract legality. |
| Variant proof validation | `proof` + `shared_validation` | Split | Frontend proves authored access; shared validation preserves lowered variant/output guards. |
| Snapshot validation | `shared_validation` | Shared validation | Frontend does not duplicate snapshot ref semantics. |
| Pointer authority validation | `authority` + `shared_validation` | Split | Frontend bans pointer-as-authority authoring; shared validation owns publication conflicts and lowered path semantics. |
| Report-authority validation | `authority` | Frontend | `.orc` must reject report parsing and hidden semantic prose recovery before lowering. |
| Workflow-call validation | `reference` + `shared_validation` | Split | Frontend checks signatures and linkage; shared validation owns lowered call surfaces and imported-bundle compatibility. |
| State-layout validation | `lowering_surface` + `shared_validation` | Split | Frontend checks generated placeholder coverage; shared validation owns path/layout legality. |
| Source-map coverage validation | `source_map` + `executable` | Frontend | Reuses source-map slice contract and executable lineage checks. |
| Executable lowering validation | `shared_validation` + `executable` | Split | Shared lowering builds executable artifacts; frontend verifies authored lineage and diagnostic surface. |

This mapping is the core scope boundary for the selected gap.

## Authority And Command-Boundary Validation

The `authority` pass is where the full-design authority rules and the
command-adapter contract meet the high-level `.orc` surface.

Required frontend failures:

- `semantic_field_extracted_from_report`
- `markdown_report_used_as_state`
- `pointer_used_as_semantic_authority`
- `noncanonical_pointer_sidecar`
- `legacy_adapter_missing_fixture`
- `legacy_adapter_not_deprecated`
- `command_adapter_missing_contract`
- `inline_python_command_in_workflow`
- `inline_shell_command_in_workflow`
- `inline_json_state_rewrite`
- `inline_pointer_write`
- `inline_subprocess_nested_command`

Policy:

- on new high-level `.orc` workflows, the lint names from
  `workflow_command_adapter_contract.md` are hard diagnostics, not warnings;
- `python -c`, `python -`, `bash -c`, `sh -c`, single-string shell wrappers,
  and heredoc-equivalent launch shapes are rejected before shared validation;
- any command boundary that decides workflow state, routing, artifact lineage,
  resume reuse, or resource movement must resolve to a certified adapter with
  declared contracts and fixtures;
- pointer files may exist only as representations. They may not become the
  semantic input to `.orc` stdlib forms such as `resume-or-start`.

This pass never parses reports, shell text, or pointer sidecars to recover
meaning. It only validates authored forms and declared boundary metadata.

## Shared Validation Bridge And Error Surface Mapping

### Bridge Contract

The `shared_validation` pass reuses the existing handoff:

```text
lowered authored workflow mappings
  -> elaborate_surface_workflow(...)
  -> lower_surface_workflow(...)
  -> LoadedWorkflowBundle / shared ValidationError
```

Rules:

- run only after frontend-local blocking diagnostics are clear through
  `source_map`;
- preserve shared error codes exactly;
- remap spans, form paths, and provenance through structured validation
  subject refs first;
- fall back to generated-name message matching only when no structured subject
  ref exists, and attach an explicit compatibility note.

### Shared-Code Classification

Shared codes remain authoritative but are classified into exact validation
passes for diagnostics filtering and reporting:

| Shared code | `validation_pass` | Notes |
| --- | --- | --- |
| `contract_refinement_weakened` | `contract` | Shared refinement authority. |
| `contract_refinement_type_conflict` | `contract` | Shared refinement authority. |
| `invalid_variant_bundle` | `contract` | Structured-result bundle invalid. |
| `variant_required_field_missing` | `contract` | Bundle shape invalid. |
| `variant_forbidden_field_present` | `contract` | Bundle shape invalid. |
| `variant_ref_unproved` | `proof` | Lowered proof/runtime guard failure. |
| `variant_ref_wrong_variant` | `proof` | Lowered proof/runtime guard failure. |
| `variant_unavailable` | `proof` | Lowered availability failure. |
| `snapshot_ref_unknown_step` | `shared_validation` | Snapshot semantics remain shared-owned. |
| `snapshot_ref_unknown_name` | `shared_validation` | Snapshot semantics remain shared-owned. |
| `snapshot_candidate_unchanged` | `shared_validation` | Freshness/evidence failure. |
| `snapshot_candidate_ambiguous` | `shared_validation` | Freshness/evidence failure. |
| `pointer_authority_conflict` | `authority` | Shared lowered pointer/publication conflict. |
| `workflow_call_version_mismatch` | `reference` | Shared lowered call-boundary mismatch. |
| `atomic_commit_failed` | `executable` | Execution-facing commit failure. |
| `bundle_commit_aborted_invalid_candidate` | `executable` | Execution-facing bundle failure. |

If a later shared validator introduces a new stable code, this slice should
map it to an existing pass when the meaning is clear. It should not wrap it in
a new frontend alias.

### Reserved Lowering Codes

The full design names:

- `core_ast_invalid`
- `semantic_ir_invalid`
- `executable_ir_invalid`

Current implementation policy:

- `core_ast_invalid` remains reserved until the repo exposes a first-class
  shared Core AST validation surface;
- `semantic_ir_invalid` remains reserved until the repo exposes a first-class
  shared Semantic IR validation surface;
- `executable_ir_invalid` is valid only for the final executable/runtime-facing
  pass and must not be used as a generic synonym for ordinary shared-validation
  failures.

This preserves the "no fake surfaces" rule from prior slices.

## Diagnostics And Serialization

### Phase Mapping

Keep the coarse `phase` field for CLI/build compatibility:

- `read`
- `syntax`
- `macro`
- `typecheck`
- `lowering`
- `shared_validation`
- `source_map`
- `executable`
- `cli_request`

Deterministic mapping:

- `parse` -> `read`
- `module` -> `syntax`
- `macro` -> `macro`
- `type`, `effect`, `reference`, `contract`, `proof` -> `typecheck`
- `authority`, `lowering_surface` -> `lowering`
- `source_map` -> `source_map`
- `shared_validation` -> `shared_validation`
- `executable` -> `executable`

The coarse phase is not a substitute for `validation_pass`.

### Diagnostic Allocation Rules

- Reuse an existing code whenever the meaning already matches.
- Add a new frontend code only when an existing code is too coarse.
- Preserve shared codes exactly rather than translating them into frontend-only
  synonyms.
- Every diagnostic must carry:
  span,
  form path,
  validation pass,
  authority layer,
  and any macro/procedure/source-map notes needed to explain blame.

Representative frontend families by pass:

- `parse` / `module`
  - `frontend_parse_error`
  - `language_version_unsupported`
  - `target_dsl_unsupported`
  - `module_not_found`
  - `module_cycle`
  - `module_export_missing`
  - `module_import_ambiguous`
- `macro`
  - `macro_unknown`
  - `macro_arity_error`
  - `macro_keyword_unknown`
  - `macro_keyword_missing`
  - `macro_expansion_cycle`
  - `macro_hygiene_violation`
  - `macro_non_deterministic`
  - `macro_hidden_effect`
  - `macro_emits_invalid_ast`
  - `macro_weakens_contract`
- `type` / `proof`
  - `type_unknown`
  - `type_mismatch`
  - `record_field_unknown`
  - `record_field_missing`
  - `union_variant_unknown`
  - `union_match_non_exhaustive`
  - `workflow_signature_mismatch`
  - `proc_signature_mismatch`
  - `higher_order_workflow_signature_mismatch`
  - `return_type_mismatch`
  - `variant_ref_unproved`
  - `variant_ref_wrong_variant`
- `effect`
  - `pure_function_has_effect`
  - `macro_has_effect`
  - `effect_not_declared`
  - `effect_not_permitted`
  - `provider_effect_hidden`
  - `command_effect_hidden`
  - `state_update_hidden`
  - procedure effect diagnostics already defined by the `defproc` slice
- `contract` / `authority`
  - `workflow_boundary_type_invalid`
  - `workflow_return_type_invalid`
  - `json_surface_unsupported`
  - `resume_or_start_contract_invalid`
  - `resume_or_start_uncertified_backend`
  - `resource_transition_contract_invalid`
  - `resource_transition_uncertified_adapter`
  - `command_adapter_missing_contract`
  - authority diagnostics listed above
- `lowering_surface` / `source_map` / `executable`
  - `lowering_no_backend_for_form`
  - `proc_lowering_cycle`
  - `source_map_missing`
  - `source_map_duplicate_key`
  - `source_map_validation_ref_missing`
  - `source_map_executable_node_unmapped`
  - `source_map_runtime_trace_invalid`
  - `executable_ir_invalid`

## Test Strategy

Focused tests for this slice should exercise pipeline ownership and diagnostic
mapping rather than re-testing every feature slice in isolation.

Primary suites:

- `tests/test_workflow_lisp_diagnostics.py`
  - pass and phase classification
  - shared-code preservation
  - command-adapter and authority diagnostics
  - compatibility-fallback notes when structured subject refs are absent
- `tests/test_workflow_lisp_lowering.py`
  - subject-ref-first remapping
  - generated-origin coverage for lowered validation subjects
- `tests/test_workflow_lisp_structured_results.py`
  - inline command-glue rejection
  - certified-adapter requirement enforcement
- `tests/test_workflow_lisp_phase_stdlib.py`
  - pointer-authority and reusable-state validation failures
- `tests/test_workflow_lisp_resource_stdlib.py`
  - uncertified resource-transition adapter failures
- `tests/test_loader_validation.py`
  - preserved shared pointer/call/path validation errors
- `tests/test_workflow_lisp_build_artifacts.py`
  - diagnostic serialization and source-map coverage interaction
- `tests/test_runtime_observability.py`
  - executable/runtime-facing diagnostic provenance still lines up with source
    lineage

## Implementation Sequence

1. Add `validation.py` with the pass catalog, pass ordering, and aggregate
   result model.
2. Extend `diagnostics.py` so every emitted diagnostic carries stable
   `validation_pass` and `authority_layer` metadata while preserving the
   existing renderer contract.
3. Lift existing feature-local validators behind pass contributors in
   `compiler.py` without changing their rule ownership.
4. Implement the frontend `authority` pass using the command-adapter contract
   and existing stdlib boundary metadata.
5. Wire `lowering_surface` and `source_map` gating so every generated subject
   is covered before shared-validation remap relies on it.
6. Wire the `shared_validation` pass to preserve shared codes, use structured
   subject refs first, and mark message-text remapping as fallback-only.
7. Add the final `executable` pass for executable-lineage coverage and
   executable-only diagnostics.
8. Extend focused diagnostics, lowering, build-artifact, loader-validation,
   and runtime-observability tests.

## Acceptance Conditions

This slice is complete when:

- one deterministic validation pipeline governs Workflow Lisp compilation from
  parse through executable/runtime-facing validation surfaces;
- frontend-local and shared-validation ownership is explicit for every
  full-design validation category;
- every diagnostic emitted by Workflow Lisp compilation has a stable code,
  span, form path, coarse `phase`, exact `validation_pass`, and
  `authority_layer`;
- shared validation errors preserve their existing stable shared codes and
  remap to authored `.orc` provenance through structured subject refs whenever
  available;
- `.orc` workflows reject report parsing, pointer-as-authority, inline command
  glue, and uncertified semantic command boundaries before shared validation;
- the implementation does not fabricate `core_ast_invalid` or
  `semantic_ir_invalid` before those shared surfaces actually exist.

## Verification Plan

Future implementation work for this slice should verify with narrow selectors
first, then broader frontend coverage:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_diagnostics.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_resource_stdlib.py tests/test_loader_validation.py tests/test_workflow_lisp_build_artifacts.py tests/test_runtime_observability.py -q
python -m pytest tests/test_workflow_lisp_diagnostics.py -k "shared_validation or source_map or command_adapter_missing_contract" -q
python -m pytest tests/test_workflow_lisp_lowering.py -k "shared_validation or structured_validation_subject or source_map" -q
python -m pytest tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_resource_stdlib.py -k "command_adapter_missing_contract or pointer_authority or uncertified" -q
python -m pytest tests/test_loader_validation.py -k "pointer_authority_conflict or workflow_call_version_mismatch" -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py tests/test_runtime_observability.py -k "source_map or compiled_frontend or executable" -q
```
