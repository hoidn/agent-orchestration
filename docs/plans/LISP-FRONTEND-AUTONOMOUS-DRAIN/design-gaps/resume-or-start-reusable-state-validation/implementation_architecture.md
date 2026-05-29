# Resume-Or-Start Reusable-State Validation Implementation Architecture

## Scope

This design gap covers only the missing reusable-state validation contract for
the Workflow Lisp frontend's `resume-or-start` form:

- define the compile-time contract that decides when prior canonical state may
  be reused;
- define how the compiler derives reusable-variant and required-artifact
  requirements from the authored return type;
- define the certified validator and canonical-bundle loader boundaries used by
  `resume-or-start`;
- define stale-state, invalid-state, and normalization behavior for resumed and
  fresh branches;
- keep the lowering on the existing Stage 3 structured-result and Stage 5 phase
  stdlib substrate.

Out of scope for this tranche:

- `with-phase`, `phase-target`, `run-provider-phase`, `produce-one-of`,
  `review-revise-loop`, `resource-transition`, `finalize-selected-item`, or
  `backlog-drain` beyond the exact `resume-or-start` contract they already
  depend on;
- redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog,
  SourceMap, pointer authority, variant proof, or runtime state persistence;
- runtime-native reusable-state effects or generalized resume primitives;
- report parsing, pointer-file authority, inline semantic Python or shell, or
  unnamed script wrappers;
- a replacement for the product design in
  `docs/design/workflow_lisp_frontend_specification.md`.

This is an implementation architecture for exactly the selected reusable-state
validation gap. It does not reopen the rest of Stage 5.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_frontend_specification.md`
  - `28. resume-or-start`
  - `54. provider-result Lowering`
  - `59. Validation Sequence`
  - `62. Contract Validation`
  - `64. Snapshot Validation`
  - `65. Pointer Authority Validation`
  - `66. Report-Authority Validation`
  - `74. Source Map Requirements`
  - `103. Stage 5: Phase And Context Library`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `2. Relationship To The Full Specification`
  - `3. Non-Goals`
  - `14. Implementation Stages`
- `docs/design/workflow_command_adapter_contract.md`
  - `Classification Model`
  - `Certified Command Adapter`
  - `Adapter Validation`
  - `resume-or-start Requirement`
  - `Runtime-Native Promotion Criteria`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_source_map.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/steering.md`
- `specs/dsl.md`
- the previously drafted Lisp frontend implementation architectures, especially
  the Stage 3 lowering, `defproc`, Stage 5 phase stdlib, and Stage 6
  resource/drain slices.

Additional constraints:

- keep the frontend in `orchestrator/workflow_lisp/` and keep shared runtime
  semantics under `orchestrator/workflow/`;
- reuse the current read -> syntax -> macro expansion ->
  definitions/procedures/workflows -> typecheck -> lowering ->
  shared-validation seam;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- keep `resume-or-start` on typed structured-result and `match` surfaces, not
  handwritten recovery gates;
- keep command-backed semantics inside the certified command-adapter boundary
  required by `docs/design/workflow_command_adapter_contract.md`.

The command-adapter contract is authoritative here because this slice is
specifying the `resume_state_reuse` behavior class directly. New implementation
must not hide reusable-state semantics in inline command text, report parsing,
pointer reads, or ad hoc JSON rewrites.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/hygienic-defmacro-system/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/lisp-frontend-cli-diagnostics-surface/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/module-import-export-resolution/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resource-drain-library/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-boundary-type-flattening/implementation_architecture.md`

### Decisions Reused

- Reuse the current staged frontend pipeline and the existing authored-mapping
  -> shared-validation handoff.
- Reuse `SourcePosition`, `SourceSpan`, `LispFrontendDiagnostic`,
  expansion-stack provenance, and `LoweringOriginMap` as the only provenance
  channel.
- Reuse Stage 3 structured-result contract derivation, `command-result`
  classification, and the fixed `CertifiedAdapterBinding.output_type_name`
  contract.
- Reuse Stage 2 proof checking and ordinary `match` lowering for the `REUSE`
  vs `START` decision branch.
- Reuse Stage 5 `resume-or-start` surface syntax and its validator-step ->
  branch -> loader-step skeleton rather than inventing a second recovery form.
- Reuse the Stage 5 generated fixed-output loader-binding pattern because it
  already fits the existing top-level `command-result` substrate for record and
  union results.
- Reuse the module/import slice rule that imported command-backed semantics
  transport existing certified-adapter metadata rather than inventing a second
  module-local command boundary.
- Reuse the workflow-boundary flattening slice rule that
  `orchestrator/workflow_lisp/contracts.py` remains the owned boundary
  projection surface, while authored workflow signatures stay authoritative.
- Reuse the CLI/diagnostics slice rule that generated helper steps and adapter
  boundaries must remain explainable through the persisted frontend provenance
  channel rather than ad hoc runtime-only logging.

### New Decisions In This Slice

- Add a frontend-local `ReusableStateValidationSpec` that makes reusable-state
  validation explicit at compile time instead of leaving it as adapter-local
  convention.
- Treat the derived structured-result contract fingerprint as the
  reusable-state schema/version authority for `resume-or-start`; this slice
  does not invent a second bundle-version system.
- Derive reusable artifact requirements from the authored return type and the
  reusable variants, rather than requiring authored field-name lists.
- Require the validator to emit both the canonical bundle path and a content
  digest for the approved reusable bundle, so the loader can reject mutation
  between the decision step and the load step.
- Distinguish `START` from hard failure:
  only missing prior state or a non-reusable terminal variant may fall back to
  `START`; stale, malformed, pointer-backed, unsafe, or contract-mismatched
  prior state must fail with stable error codes.
- Support record and union return types with one rule:
  union returns require a reusable-variant set from `:valid-when`;
  record returns are reusable as a single record-shaped terminal result and
  therefore forbid `:valid-when`.

### Conflicts Or Revisions

The Stage 5 phase-context architecture intentionally left `resume-or-start`
partly underspecified so the broader phase stdlib slice could proceed. This
slice narrows that ambiguity:

- `required_artifact_fields` is revised into a compiler-derived
  `ReusableArtifactRequirement` manifest keyed by the reusable result shape;
- `expected_return_type` alone is no longer sufficient adapter input;
  validator and loader contracts must also carry an
  `expected_contract_fingerprint`;
- stale-state behavior is now explicit:
  stale or invalid prior state is a hard failure, not a silent fresh start;
- loader revalidation of the approved bundle digest is now part of the
  normative contract.

These revisions stay frontend-local. They do not redefine shared concepts such
as Core Workflow AST, Semantic Workflow IR, TypeCatalog, SourceMap, pointer
authority, or variant proof.

No newer reviewed slice supersedes this contract. The Stage 7 NeurIPS
migration architecture depends on Stage 5 `resume-or-start`; this document
therefore tightens the reusable-state contract it is allowed to rely on rather
than changing the selected-item or drain composition surface.

## Ownership Boundaries

This slice owns:

- frontend-local representation of reusable-state validation requirements for
  `resume-or-start`;
- derivation of reusable-variant sets and reusable-artifact requirements from
  authored record and union return types;
- compile-time derivation of a reusable-state contract fingerprint from the
  existing structured-result contract machinery;
- the static certified validator binding,
  `validate_reusable_phase_state`;
- the shared canonical-bundle loader backend plus compiler-generated fixed
  loader bindings of the form
  `load_canonical_phase_result__<ReturnTypeName>`;
- `resume-or-start` typechecking, lowering, source-map frames, diagnostics, and
  stable adapter error taxonomy;
- focused tests and fixtures for reusable-state validation, digest
  revalidation, stale-state rejection, and plan-gate recovery regressions.

This slice intentionally does not own:

- general phase-context derivation, resource/drain lowering, workflow refs, or
  runtime-native transition semantics;
- shared path-safety enforcement, pointer-authority rules, or provider/command
  execution semantics beyond the frontend-owned certified-adapter metadata;
- redesign of shared structured-result contract validation, state persistence,
  resume checkpoint storage, or runtime observability;
- a new shared bundle-version format or a second schema-validation subsystem.

## Proposed Package Boundary

This slice extends the existing Stage 5 surface with one bounded contract
helper and two bounded adapter backends:

```text
orchestrator/workflow_lisp/
  adapters/load_canonical_phase_result.py
  adapters/validate_reusable_phase_state.py
  compiler.py
  contracts.py
  diagnostics.py
  lowering.py
  phase_stdlib.py
  typecheck.py
```

Planned test and fixture surface:

```text
tests/
  test_loader_validation.py
  test_workflow_lisp_phase_stdlib.py
  test_workflow_lisp_lowering.py
  test_workflow_lisp_procedures.py
  test_neurips_plan_gate_recovery.py
  fixtures/workflow_lisp/valid/phase_stdlib_resume_or_start.orc
  fixtures/workflow_lisp/invalid/resume_or_start_contract_invalid.orc
  fixtures/workflow_lisp/invalid/resume_or_start_record_valid_when_invalid.orc
  fixtures/workflow_lisp/invalid/resume_or_start_pointer_authority_invalid.orc
  fixtures/workflow_lisp/invalid/resume_or_start_uncertified_adapter.orc
```

Responsibilities:

- `contracts.py`
  - expose a stable frontend helper that derives:
    contract kind,
    structured-result fingerprint,
    and reusable-artifact requirements from an authored return type;
  - reuse existing structured-result lowering helpers instead of creating a
    parallel schema system.
- `typecheck.py`
  - build `ReusableStateValidationSpec`;
  - enforce record vs union `:valid-when` rules;
  - reject pointer-shaped or noncanonical `:resume-from` inputs.
- `phase_stdlib.py`
  - keep the authored `resume-or-start` syntax form and own the
    frontend-local dataclasses for its compiled contract.
- `lowering.py`
  - lower `resume-or-start` into:
    validator `command-result` ->
    `match` over `ResumeReuseDecision` ->
    loader `command-result` or authored `:start` branch;
  - keep generated step ids and binding names deterministic.
- `compiler.py`
  - register the default validator binding when `resume-or-start` is used;
  - synthesize the deterministic fixed-output loader bindings before reuse
    branch typechecking and lowering.
- `adapters/validate_reusable_phase_state.py`
  - implement the read-only reusable-state decision backend.
- `adapters/load_canonical_phase_result.py`
  - implement the read-only canonical bundle loader backend with digest
    revalidation.

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/spans.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/effects.py`
- `orchestrator/workflow_lisp/procedures.py`
- `orchestrator/workflow_lisp/phase.py`
- shared workflow validation/runtime modules under `orchestrator/workflow/`

## Data Model

### `ReusableStateValidationSpec`

Add one frontend-local compile-time record for `resume-or-start`:

- `resume_from_expr`
  - the authored canonical bundle expression;
- `return_type_ref`
  - the authored `:returns` type;
- `structured_contract_kind`
  - `record` or `union`;
- `expected_contract_fingerprint`
  - deterministic schema/version authority derived from the existing
    structured-result contract shape;
- `reusable_variants`
  - non-empty set of reusable union variants, or empty for record returns;
- `artifact_requirements`
  - derived `ReusableArtifactRequirement` entries;
- `validator_binding_name`
  - fixed:
    `validate_reusable_phase_state`;
- `loader_binding_name`
  - deterministic:
    `load_canonical_phase_result__<ReturnTypeName>`;
- `source_map_behavior`
  - `step`.

### `ReusableArtifactRequirement`

Every reusable artifact requirement is compile-time derived, not authored by
field-name string:

- `variant_name`
  - union variant name, or `null` for record returns;
- `field_path`
  - stable dotted path to the reusable artifact field;
- `contract_ref`
  - the narrowed relpath contract already derived from the return type;
- `must_exist`
  - always `true` for reuse requirements;
- `workspace_root`
  - the root implied by the relpath contract, reused by existing path-safety
    checks.

Derivation rule:

- include every relpath-valued field that can appear in a reused result and
  whose contract already requires existence;
- recurse through nested record fields when they contribute reusable artifact
  paths;
- never derive pointer files or report-parsed values as reusable requirements.

### `ResumeContractFingerprint`

The reusable-state schema/version authority is one deterministic frontend value
derived from the existing structured-result contract machinery:

- target DSL version;
- authored return type name;
- contract kind:
  `record` or `union`;
- normalized structured-result contract digest.

The validator and loader use this fingerprint to prove that the prior canonical
bundle still matches the currently authored return contract. This slice does not
introduce a second version field inside canonical state.

### `ResumeReuseDecision`

The validator emits one decision-only internal union:

- `REUSE`
  - `source_bundle_path`
  - `source_bundle_sha256`
  - `matched_variant`
    - required for union returns;
- `START`
  - `reason_code`
    - one of:
      `MISSING_BUNDLE`,
      `VARIANT_NOT_REUSABLE`.

The validator does not emit the authored return type directly. The typed value
continues to flow through a top-level fixed-output loader `command-result` so
record and union reuse stay on the already supported Stage 3 structured-result
path.

## Validator And Loader Contracts

### Certified Validator Binding

The reusable-state validator remains one named certified adapter:

- binding name:
  `validate_reusable_phase_state`
- owner module:
  `orchestrator/workflow_lisp/adapters/validate_reusable_phase_state.py`
- stable command:
  `python -m orchestrator.workflow_lisp.adapters.validate_reusable_phase_state`
- behavior classes:
  `resume_state_reuse`,
  `structured_result`
- declared effects:
  read-only workspace inspection plus structured-result emission;
- state writes:
  none beyond the generated structured-result output path;
- source-map behavior:
  `step`.

Validator input contract:

- `resume_from`
  - canonical bundle relpath value, not a pointer file;
- `expected_return_type`
  - authored type name;
- `expected_contract_fingerprint`
  - current reusable-state schema/version authority;
- `reusable_variants`
  - explicit reusable union variants, empty for record returns;
- `artifact_requirements`
  - serialized `ReusableArtifactRequirement` manifest.

Validator obligations:

- enforce workspace path safety before opening the bundle;
- reject pointer files as semantic authority;
- load and validate the bundle against the current structured-result contract
  fingerprint;
- reject contract mismatch or malformed structured state as hard failure;
- reject missing required artifacts as hard failure;
- on success, emit `REUSE` with the bundle digest and matched reusable variant;
- emit `START` only when the bundle is absent or its terminal union variant is
  outside the reusable set.

### Canonical Loader Binding Template

The loader remains one shared backend with compiler-generated fixed-output
bindings:

- owner module:
  `orchestrator/workflow_lisp/adapters/load_canonical_phase_result.py`
- stable command:
  `python -m orchestrator.workflow_lisp.adapters.load_canonical_phase_result`
- generated binding name:
  `load_canonical_phase_result__<ReturnTypeName>`
- generated binding metadata:
  - `output_type_name` equals the authored `:returns` type exactly;
  - `stable_command` stays fixed to the shared backend command;
  - input metadata is cloned from one compiler-owned template.

Loader input contract:

- `bundle_path`
  - validator-approved canonical bundle path;
- `expected_return_type`
  - authored type name;
- `expected_contract_fingerprint`
  - current reusable-state schema/version authority;
- `expected_bundle_sha256`
  - digest emitted by the validator.

Loader obligations:

- re-read the canonical bundle from `bundle_path`;
- recompute and compare the digest before emitting any typed result;
- reject mutation between validator and loader as stale state;
- validate the bundle against the current structured-result contract
  fingerprint;
- emit the authored return type through ordinary top-level `command-result`
  lowering:
  - record return -> `output_bundle`
  - union return -> `variant_output`.

The loader remains read-only apart from its declared structured-result output
path.

## Typing And Lowering Model

Typechecking requirements:

- `:resume-from` must resolve to a workspace relpath for canonical structured
  state, not a pointer file or prose report;
- union returns require `:valid-when` and it must name a non-empty subset of
  variants on the declared return type;
- record returns forbid `:valid-when`;
- `:start` must typecheck to the same return type as `:returns`;
- reusable artifact requirements must be derivable from the declared return
  type without markdown parsing, pointer inspection, or authored field-name
  strings;
- validator and loader bindings must resolve to certified adapter metadata, not
  plain unclassified scripts.

Lowering sequence:

1. derive `ReusableStateValidationSpec` from the authored form;
2. synthesize or reuse the deterministic fixed-output loader binding for the
   authored return type;
3. lower a validator `command-result` step bound to
   `validate_reusable_phase_state`;
4. lower a `match` over `ResumeReuseDecision`;
5. on `REUSE`, lower a fixed-output loader `command-result` step bound to
   `load_canonical_phase_result__<ReturnTypeName>`;
6. on `START`, lower the authored `:start` expression directly;
7. normalize both branches to the authored return type without wrapper records
   or nested unions.

Generated step ids, binding names, and branch locals must be deterministic and
must map back to the authored `resume-or-start` span through the existing
origin-map channel.

## Failure Semantics

`resume-or-start` has exactly two fallback cases:

- canonical bundle missing;
- canonical bundle present but its terminal union variant is not reusable.

Everything else is a hard failure, not a fresh start:

- unsafe path;
- pointer file used as semantic authority;
- contract fingerprint mismatch;
- invalid structured-result schema;
- required artifact missing;
- bundle mutated between validator and loader;
- loader output schema mismatch.

Stale state means prior canonical state exists but no longer validates against
the current reusable-state contract or no longer preserves the validator's
approved digest. Stale state must fail with stable error codes. It must not be
treated as equivalent to "no prior state".

No mtime-only check is allowed anywhere in the reusable-state decision.

## Diagnostics And Error Taxonomy

Compile-time diagnostics added or tightened by this slice:

- `resume_or_start_contract_invalid`
- `resume_or_start_reusable_variant_invalid`
- `resume_or_start_record_valid_when_invalid`
- `resume_or_start_resume_path_invalid`
- `resume_or_start_uncertified_backend`

Stable adapter/runtime error codes:

- `resume_state_path_unsafe`
- `resume_state_pointer_authority_forbidden`
- `resume_state_contract_fingerprint_mismatch`
- `resume_state_bundle_schema_invalid`
- `resume_state_required_artifact_missing`
- `resume_state_bundle_mutated_before_load`
- `resume_state_loader_schema_invalid`

Every diagnostic must report the authored `resume-or-start` form span and keep
the standard-library form name in the expansion stack when the failure comes
from generated validator or loader steps.

## Test Strategy

### Frontend Unit Tests

- derive reusable-variant sets correctly for union returns;
- reject `:valid-when` on record returns;
- reject unknown or non-return-type variants;
- derive reusable-artifact requirements from nested reusable return fields;
- reject pointer-shaped `:resume-from` values;
- verify deterministic loader-binding names and inserted certified metadata.

### Adapter Fixture Tests

Validator positive fixtures:

- reusable union bundle accepted;
- reusable record bundle accepted;
- missing bundle returns `START`;
- non-reusable variant returns `START`.

Validator negative fixtures:

- pointer authority misuse;
- structured bundle schema mismatch;
- contract fingerprint mismatch;
- required artifact missing.

Loader positive fixtures:

- record result loads through `output_bundle`;
- union result loads through `variant_output`.

Loader negative fixtures:

- bundle digest changes between validation and load;
- loader schema mismatch;
- unsafe bundle path.

### Shared-Validation And Regression Tests

- lowering and shared-validation coverage for generated validator and loader
  steps;
- regression coverage for Stage 3 structured-result lowering and `defproc`,
  because `resume-or-start` reuses those layers;
- focused plan-gate recovery smoke coverage so the selected NeurIPS-style use
  case proves resumed and fresh branches normalize to one typed result.

## Implementation Sequence

1. Add reusable-state contract helpers and diagnostics in the frontend typing
   layer.
2. Implement the certified validator backend and fixture inventory.
3. Extend the shared canonical loader backend with digest revalidation and the
   required fixed-output binding template metadata.
4. Wire compiler registration, typechecking, and lowering for the generated
   validator and loader steps.
5. Add frontend, adapter, lowering, and recovery regression tests.
6. Run the focused verification commands for the selected slice.

## Acceptance Conditions

- `resume-or-start` has an explicit reusable-state validation contract covering:
  prior-state location,
  current schema/version authority,
  reusable variants,
  required artifact existence,
  stale-state failure semantics,
  and same-type branch normalization;
- reusable-state decisions stay on typed `command-result` + `match` surfaces;
- the validator and loader are both certified command adapters with stable
  commands, typed inputs and outputs, declared effects, fixture obligations,
  and source-map behavior;
- missing prior state and non-reusable variants fall back to `START`;
- malformed, stale, unsafe, or pointer-backed prior state fails with stable
  error codes;
- resumed record and union results both reuse the existing Stage 3 top-level
  structured-result lowering path;
- no new shared runtime primitive, pointer-authority exception, or inline
  semantic glue is introduced.

## Verification Plan

The deterministic verification commands for this slice should be written to:

`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect/check_commands.json`

Minimum verification coverage:

- collect-only for the targeted phase-stdlib, loader-validation, and recovery
  modules;
- focused phase-stdlib and loader-validation unit runs;
- lowering and procedure regressions because the generated validator and loader
  steps reuse those layers;
- at least one plan-gate recovery smoke test proving resumed and fresh paths
  normalize to the same typed result.
