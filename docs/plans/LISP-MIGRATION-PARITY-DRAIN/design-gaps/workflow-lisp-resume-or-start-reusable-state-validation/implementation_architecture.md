# Workflow Lisp Resume-Or-Start Reusable-State Validation Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-resume-or-start-reusable-state-validation`
Target design: `docs/design/workflow_lisp_key_migration_parity_architecture.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected migration-parity gap:

- add the target `ReusablePhaseState.v1` reusable-state summary for
  phase-output reuse;
- keep `resume-or-start` authoring and typed fresh-vs-reuse normalization
  intact while upgrading its internal reusable-state contract;
- classify reusable-state validation with the target parity outcomes:
  `REUSABLE`, `STALE`, `MISSING_ARTIFACT`, `FAILED_PRIOR_STATE`,
  `SCHEMA_MISMATCH`, and `UNSUPPORTED_VERSION`;
- derive reusable-state hashes, fingerprints, and referenced-artifact checks
  from the compiled Workflow Lisp workflow boundary and typed return contract;
- preserve the explicit certified command-adapter boundary for reusable-state
  validation and canonical-result loading;
- keep compiler-owned summary paths and managed write roots off the public
  workflow API.

Out of scope for this slice:

- review-loop composition, carried findings, workflow input defaults, or
  command-result bundle-path ownership beyond reusing their existing decisions;
- migration promotion reports, `non_regressive` computation, or YAML
  deprecation;
- redesign of Core Workflow AST, Semantic IR, Executable IR, TypeCatalog,
  SourceMap, pointer authority, or variant proof;
- runtime-native reusable-state primitives, runtime closures, or runtime-carried
  procedure/provider/prompt/workflow refs;
- report parsing, pointer-as-state compatibility, inline shell/Python glue, or
  uncataloged command wrappers.

This is a bounded implementation architecture for one gap only. It does not
replace the parent migration architecture or reopen the umbrella Workflow Lisp
frontend contract.

## Problem Statement

The selected target design already chose the intended reusable-state model:

- reusable-state validation should operate over a canonical
  `ReusablePhaseState.v1` summary, not raw bundle-shape coincidence;
- the summary should capture input-hash, producer-fingerprint, compatibility
  metadata, reusable terminal status, and artifact checksum evidence;
- `resume-or-start` should distinguish stale, missing-artifact, failed,
  schema-mismatch, and unsupported-version cases instead of collapsing them
  into `START` or opaque hard failure;
- canonical result bundles remain semantic authority, while the reusable-state
  summary is a derived validation aid.

The current checkout still implements the older Stage 5 contract:

1. `ReusableStateValidationSpec` carries only structured-contract fingerprint,
   reusable variants, and required artifact paths.
2. `validate_reusable_phase_state.py` reads `:resume-from` as the canonical
   bundle itself, validates that bundle directly, emits only `REUSE` or
   `START`, and hard-fails all richer incompatibilities.
3. `tests/test_workflow_lisp_phase_stdlib.py` and
   `tests/test_neurips_plan_gate_recovery.py` currently lock down that narrow
   behavior.
4. There is no compiler-owned `ReusablePhaseState.v1` sidecar, no
   producer-fingerprint, no public-input hash basis, and no typed distinction
   between stale state and incompatible state.

The gap is therefore no longer “invent `resume-or-start`.” The current gap is
to replace the older bundle-fingerprint reuse test with the parity design’s
summary-backed reusable-state contract while preserving the existing typed
author surface and reuse/load normalization.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
  - `Reusable State Contract`
  - `Dependencies And Sequencing`
  - `Verification Strategy`
- `docs/design/workflow_lisp_frontend_specification.md`
  - Sections 19, 20, 28, 59, 64, 65, 95, 103
- `docs/design/workflow_command_adapter_contract.md`
  - `Classification Model`
  - `Certified Command Adapter`
  - `Adapter Validation`
  - `resume-or-start Requirement`
  - `Runtime-Native Promotion Criteria`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/lisp_workflow_drafting_guide.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/state.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`
- `docs/steering.md`

The slice must preserve these guardrails:

- keep canonical result bundles authoritative and reusable-state summaries
  derived;
- keep compiler-owned state-summary paths, managed write roots, and loader
  metadata off the public workflow boundary;
- keep public-input/default resolution and managed-input separation aligned with
  the prior command-result and input-default parity slices;
- keep any executable reusable-state logic inside named certified adapters, not
  inline Python/shell or hidden nested subprocess glue;
- keep pointer files as representations only and forbid report prose as
  semantic authority;
- keep frontend-owned logic in `orchestrator/workflow_lisp/` and shared
  execution/state authority in `orchestrator/workflow/`;
- do not treat the empty `docs/steering.md` file as permission to widen scope.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-command-result-compiler-owned-bundle-paths/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-defworkflow-input-default-parity/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-findings-structured-dataflow/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-loop-generic-effectful-composition/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resume-or-start-reusable-state-validation/implementation_architecture.md`

### Decisions Reused

- Reuse the explicit `resume-or-start` stdlib surface, generated validator step,
  generated loader step, and typed branch normalization shape from the earlier
  Stage 5 architecture.
- Reuse the public/internal compiled-workflow input split and managed write-root
  provenance from the command-result parity slice.
- Reuse authored workflow-input default resolution from the input-default parity
  slice when deriving public input hash evidence.
- Reuse the imported-stdlib/generic-composition ownership model from the
  review-loop parity slice; this slice does not add a second recovery path.
- Reuse the certified command-adapter boundary and stable loader-binding pattern
  from the older autonomous-drain resume/state slice rather than promoting a
  new runtime-native effect.

### New Decisions In This Slice

- Add a compiler-owned `ReusablePhaseState.v1` sidecar summary adjacent to each
  canonical resumable phase-result bundle.
- Keep `:resume-from` authoring stable by continuing to point at the canonical
  phase-result bundle or phase-state handle, while reusable-state validation
  derives and validates the sidecar summary behind that handle.
- Expand the internal reusable-state decision surface from `REUSE`/`START` to
  typed parity outcomes plus one bounded compatibility `START` path for absent
  prior state.
- Add compiler-derived `source_inputs_hash` and `producer_fingerprint`
  computation as reusable-state evidence.
- Add one explicit summary-materialization adapter boundary instead of writing
  reusable-state summaries through hidden Python in the lowerer.

### Conflicts Or Revisions

The earlier autonomous-drain resume/state architecture treated the structured
result contract fingerprint as the reusable-state schema/version authority and
modeled reuse as:

- direct canonical-bundle validation;
- `REUSE` or `START` transport;
- hard failure for richer incompatibilities.

This slice narrows and revises that contract for parity migration:

- the structured result contract still constrains reusable results, but it is
  no longer the whole reusable-state contract;
- a compiler-owned `ReusablePhaseState.v1` sidecar becomes the reusable-state
  validation surface;
- stale, missing-artifact, failed-prior-state, schema-mismatch, and
  unsupported-version are no longer collapsed into `START` or undifferentiated
  hard failure;
- the generated loader-binding pattern is preserved, but it now consumes
  summary-validated bundle evidence instead of bundle-only reuse evidence.

No shared concepts are redefined. Core Workflow AST, Semantic IR, TypeCatalog,
SourceMap, pointer authority, variant proof, and runtime execution ownership
remain with their existing owners.

## Ownership Boundaries

This slice owns:

- reusable-state summary derivation metadata in
  `orchestrator/workflow_lisp/contracts.py` and `phase_stdlib.py`;
- `resume-or-start` typecheck and lowering updates in
  `orchestrator/workflow_lisp/typecheck.py` and `lowering.py`;
- compiler registration of reusable-state validator/materializer/loader command
  boundaries in `orchestrator/workflow_lisp/compiler.py`;
- one new summary-materialization adapter and the revision of the existing
  reusable-state validator adapter under
  `orchestrator/workflow_lisp/adapters/`;
- build-manifest/source-map exposure for generated reusable-state sidecars and
  decision/load steps;
- focused fixture and test coverage for reusable-state outcomes, summary
  generation, loader revalidation, and migration-facing plan-gate reuse.

This slice intentionally does not own:

- promotion-report generation or `non_regressive` policy;
- review-loop or findings semantics beyond preserving their existing contracts;
- new runtime-native reusable-state effects;
- general state-layout redesign outside the deterministic sidecar path owned by
  this slice;
- YAML workflow behavior outside the compiled Workflow Lisp reuse path.

## Current Checkout Facts

The current checkout already contains substrate this slice should reuse:

- `orchestrator/workflow_lisp/phase_stdlib.py` defines
  `ReusableStateValidationSpec`.
- `typecheck.py` already derives reusable variants and artifact requirements for
  `resume-or-start`.
- `compiler.py` already registers the certified
  `validate_reusable_phase_state` binding and generated
  `load_canonical_phase_result__<ReturnTypeName>` bindings.
- `lowering.py` already emits validator -> `match` -> loader/start lowering and
  keeps reuse/write-root metadata source-mapped.

The same checkout also shows the exact parity gap:

- `validate_reusable_phase_state.py` validates the bundle at `resume_from`
  directly, not a reusable-state summary.
- Missing bundle and non-reusable variant currently return `START`, while
  pointer authority, schema invalidity, and fingerprint mismatch return hard
  failure with no richer reusable-state classification.
- no compiler-generated reusable-state sidecar exists after the fresh branch;
- current tests assert `START` for missing bundle and `VARIANT_NOT_REUSABLE`,
  proving the old transport still governs behavior.
- the progress ledger for this drain is still empty, so nothing later in the
  repo supersedes the selected gap.

This makes the slice feasible without inventing a new runtime primitive. The
missing pieces are a compiler-owned summary artifact, summary-aware validator
and writer adapters, and updated lowering/typecheck contracts that normalize
the richer outcomes back onto the existing `resume-or-start` author surface.

## Proposed Architecture

### 1. Keep `resume-or-start` Authoring Stable

The public authoring form stays:

- `:resume-from` remains the resumable phase-state handle;
- `:start` remains the fresh branch;
- `:returns` remains the authored result type;
- resumed and fresh branches still normalize to that same authored type.

This slice does not introduce a new authored summary path or a second recovery
form. Instead, the compiler/runtime-owned reusable-state sidecar is derived
from the canonical result-bundle path already referenced by `:resume-from`.

Implementation decision:

- for a canonical bundle `state/.../phase-result.json`, the reusable-state
  sidecar path is a deterministic sibling:
  `state/.../phase-result.reusable_state.json`;
- debug/build surfaces may show that generated path with provenance;
- users do not bind or override it directly.

### 2. Add `ReusablePhaseState.v1` As A Compiler-Owned Sidecar

Fresh successful `resume-or-start` execution writes a reusable-state summary
adjacent to the canonical bundle. The canonical bundle remains the semantic
authority; the sidecar captures durable reuse evidence.

Minimum summary payload for this slice:

- all target-design minimum fields:
  `schema`,
  `source_run_id`,
  `source_step_id`,
  `source_call_frame_id`,
  `workflow_checksum`,
  `phase_id`,
  `producer_workflow`,
  `producer_compiler`,
  `terminal`,
  `source_inputs_hash`,
  `producer_fingerprint`,
  `result_type`,
  `artifact_refs`,
  `created_at`,
  `compatibility`;
- one bounded implementation field:
  `canonical_bundle_sha256`.

This extra digest is justified because the current loader already revalidates
bundle content, and the target minimum shape does not otherwise give the reuse
branch a durable canonical-bundle integrity check.

`artifact_refs` remain derived evidence, not a second authority surface. Each
entry records the authoritative artifact relpath plus the checksum used for
reuse validation.

### 3. Replace Bundle-Only Reuse Checks With Summary-Backed Validation

The existing `validate_reusable_phase_state` adapter is retained by name but
revised in responsibility:

- it receives the canonical bundle handle from `:resume-from`;
- it derives the deterministic reusable-state sidecar path;
- it validates sidecar schema/version/compatibility first;
- it then validates the canonical bundle against the structured result contract;
- it compares summary evidence against current policy:
  public-input hash,
  producer fingerprint,
  reusable terminal variant,
  artifact checksums,
  and canonical bundle digest.

Validator result surface:

- `REUSABLE`
  - carries `source_bundle_path`, `source_bundle_sha256`, and reusable metadata
    needed by the loader;
- `STALE`
- `MISSING_ARTIFACT`
- `FAILED_PRIOR_STATE`
- `SCHEMA_MISMATCH`
- `UNSUPPORTED_VERSION`
- compatibility-only `START`
  - reserved for the absence of any prior bundle/sidecar, so current “no prior
    state, run fresh” behavior stays intact.

Policy in this slice:

- `REUSABLE` routes to the loader branch;
- `START`, `STALE`, `MISSING_ARTIFACT`, and `FAILED_PRIOR_STATE` route to the
  fresh branch while preserving the outcome in execution state and diagnostics;
- `SCHEMA_MISMATCH` and `UNSUPPORTED_VERSION` remain deterministic failures,
  because silently starting fresh would hide compiler/runtime incompatibility.

This preserves the authored “reuse or run fresh” surface while exposing the
target parity outcomes to validation, tests, and migration evidence.

### 4. Derive Reusable-State Evidence From Public Inputs And Compiled Identity

The reusable-state sidecar needs compiler/runtime-owned evidence beyond the old
contract fingerprint.

Add one frontend-local reusable summary spec derived during typecheck/lowering:

- reusable result type and reusable variants;
- summary schema version:
  `ReusablePhaseState.v1`;
- public input hash basis;
- producer fingerprint basis;
- reusable artifact-reference manifest;
- deterministic sidecar path;
- validator binding, writer binding, and loader binding names.

Evidence rules:

- `source_inputs_hash` is computed from the public workflow-input view after
  authored defaults and caller overrides resolve; compiler-managed internal
  inputs are excluded.
- relpaths are normalized workspace-relative before hashing.
- `producer_fingerprint` is computed from:
  `.orc` source digest,
  imported stdlib digests,
  compiler version,
  target DSL version,
  lowering options that affect executable shape,
  and specialized provider/prompt/workflow/procedure refs.
- reusable artifact refs are derived from the reusable result shape and include
  checksum evidence for each required relpath artifact.

This slice deliberately reuses the public-input/default split from the prior
parity slices instead of inventing a second input-visibility model.

### 5. Add One Explicit Summary-Materialization Adapter

This slice adds one new certified adapter boundary:

- binding name:
  `write_reusable_phase_state_v1`
- stable command path:
  `python -m orchestrator.workflow_lisp.adapters.write_reusable_phase_state_v1`

Responsibilities:

- receive the validated fresh-branch result bundle path and reusable-summary
  payload inputs;
- compute artifact checksums after path-safety validation;
- write the `ReusablePhaseState.v1` sidecar atomically;
- emit a small structured acknowledgment bundle or record as needed for build
  visibility and negative-test coverage.

Why an adapter instead of inline lowerer logic:

- the command-adapter contract requires explicit semantic command boundaries;
- the sidecar needs file IO, hashing, path-safety checks, and a stable error
  taxonomy;
- this slice does not justify a runtime-native promotion because the behavior
  is specialized, testable, and currently rare.

### 6. Keep The Loader Boundary, But Tie It To Summary Evidence

The existing generated
`load_canonical_phase_result__<ReturnTypeName>` binding remains the reuse-load
backend. This slice does not replace it.

The only change is its input contract:

- it consumes the bundle path and digest already validated by the reusable-state
  decision step;
- it revalidates the bundle digest before returning the typed result;
- it does not re-decide staleness or compatibility on its own.

This preserves the earlier fixed-output loader pattern and avoids widening the
shared runtime executor.

### 7. Temporary Compatibility Boundary

Legacy bundle-only reuse remains compatibility debt, not the new contract.

Bounded compatibility rule:

- if neither the canonical bundle nor sidecar exists, validator returns the
  compatibility `START` outcome;
- if a canonical bundle exists but the reusable-state sidecar is absent, the
  validator must not silently pretend parity has been achieved.

Acceptable implementation choices for that second case:

- emit `FAILED_PRIOR_STATE` and route to fresh start; or
- allow one explicit adapter-local legacy mode for existing fixtures, clearly
  marked temporary and not exposed as a new high-level authoring contract.

The implementation plan must choose one path explicitly. New compiler-generated
Workflow Lisp runs in this slice must always write the sidecar.

## Proposed Code Footprint

- `orchestrator/workflow_lisp/phase_stdlib.py`
- `orchestrator/workflow_lisp/contracts.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/adapters/validate_reusable_phase_state.py`
- `orchestrator/workflow_lisp/adapters/load_canonical_phase_result.py`
- `orchestrator/workflow_lisp/adapters/write_reusable_phase_state_v1.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_neurips_plan_gate_recovery.py`
- `tests/test_workflow_lisp_key_migrations.py`
- `tests/fixtures/workflow_lisp/valid/phase_stdlib_resume_or_start.orc`
- `tests/fixtures/workflow_lisp/invalid/`

Shared components intentionally reused, not owned here:

- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/workflow/executor.py`
- `orchestrator/workflow/signatures.py`
- `orchestrator/workflow/calls.py`
- shared validation/runtime state authority in `orchestrator/workflow/`

## Acceptance Conditions

- fresh successful `resume-or-start` execution writes a deterministic
  `ReusablePhaseState.v1` sidecar adjacent to the canonical result bundle;
- the sidecar contains target-design reusable-state evidence plus
  `canonical_bundle_sha256`;
- reusable-state validation distinguishes the selected parity outcomes instead
  of collapsing everything into `START` or opaque hard failure;
- public workflow inputs after defaults, not compiler-managed hidden inputs,
  drive `source_inputs_hash`;
- reusable artifact checks validate path safety and checksum evidence without
  using pointer files or markdown reports as authority;
- `SCHEMA_MISMATCH` and `UNSUPPORTED_VERSION` fail deterministically;
- `REUSABLE` still loads through the generated fixed-output loader binding and
  returns the authored `:returns` type unchanged;
- lowering/build manifests/source maps expose the validator, writer, and loader
  as explicit generated steps with generated-path provenance;
- no new public workflow inputs, inline glue, pointer-as-state behavior, or
  report-parsing semantics are introduced.

## Verification Strategy

Focused verification for this slice should prove:

- summary generation after a fresh branch;
- summary-backed validator classification for:
  `REUSABLE`,
  `STALE`,
  `MISSING_ARTIFACT`,
  `FAILED_PRIOR_STATE`,
  `SCHEMA_MISMATCH`,
  `UNSUPPORTED_VERSION`,
  and bounded compatibility `START`;
- loader digest revalidation against summary-approved bundle evidence;
- public-input/default interaction in `source_inputs_hash`;
- migration-facing plan-gate reuse coverage in
  `tests/test_neurips_plan_gate_recovery.py`;
- build/source-map coverage showing the generated sidecar path and adapter
  boundaries.

The deterministic command list for the eventual implementation work lives in:

`state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/4/design-gap-architect/check_commands.json`
