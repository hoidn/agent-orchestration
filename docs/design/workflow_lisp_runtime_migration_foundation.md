# Workflow Lisp Runtime Migration Foundation

Status: draft design
Kind: architecture decision / migration foundation
Created: 2026-06-08
Updated: 2026-06-08
Scope: command structured-output conformance; frontend-lowered typed value transport; provider structured-output target binding; migration promotion gate hardening; and generated state/path allocation ownership.

Authority:

- Normative command IO behavior lives in `specs/io.md`.
- Normative provider prompt/source behavior lives in `specs/providers.md`.
- Normative DSL/runtime surface behavior lives in `specs/dsl.md`.
- Normative runtime state behavior lives in `specs/state.md`.
- This document is a migration foundation and implementation-sequencing design.
- This document does not by itself promote any `.orc` workflow to primary surface.
- A behavior described here is implementation-complete only when the listed verification evidence passes.

Related docs:

- `specs/io.md`
- `specs/dsl.md`
- `specs/providers.md`
- `specs/state.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_semantic_workflow_ir.md`
- `docs/design/workflow_lisp_executable_ir.md`
- `docs/design/workflow_lisp_source_map.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
- `docs/reports/2026-06-08-generic-review-revise-orc-runtime-gap-report.md`
- `docs/lisp_workflow_drafting_guide.md`

## 1. Purpose

This document records the runtime/migration foundation required before additional Workflow Lisp promotion work depends on command-result bundles, provider-result bundles, private frontend-lowered typed values, machine-readable parity gates, or compiler-owned generated path layout.

It is a consuming architecture. It does not replace `specs/io.md`, `specs/dsl.md`, `specs/providers.md`, `specs/state.md`, or `docs/design/workflow_lisp_state_layout.md`; it identifies the runtime, spec, CLI, provider, and frontend deltas needed to make those surfaces promotion-grade together.

This document does not by itself promote any `.orc` workflow to primary. YAML remains authoritative for a workflow family until the migration parity process computes non-regressive parity for that family and a promotion gate derives primary-surface eligibility.

This document also does not make every frontend-lowered internal value shape a public authored-YAML surface. The distinction between public authored DSL compatibility and private executable values lowered from Workflow Lisp is intentional.

## 2. Executive Decision

Implement one migration foundation in five ordered tranches:

1. command structured-output conformance;
2. frontend-lowered typed value transport;
3. provider structured-output target binding;
4. machine-readable migration promotion gates; and
5. centralized generated state/path allocation.

The common theme is authority.

Declared command bundle files must be the semantic authority for structured command results rather than stdout or caller-selected environment values. Frontend-lowered typed values must cross runtime boundaries as validated values rather than flattened pointer-file workarounds. Provider structured-output targets must be runtime-owned bindings, not prompt-only suggestions. Migration promotion must be computed from validated evidence rather than asserted in manifests or hand-authored reports. Compiler-generated paths must be allocated through one layout/provenance contract rather than scattered lowering-helper conventions.

This document is not a runtime spec. Normative command IO behavior remains in `specs/io.md`; normative provider behavior remains in `specs/providers.md`; normative DSL behavior remains in `specs/dsl.md`; normative run-state behavior remains in `specs/state.md`; and executable/runtime authority remains with the validated executable workflow path.

This document defines the implementation and evidence boundary required before further `.orc` promotion work should proceed.

## 3. Authority And Dependency Direction

### 3.1 This Document Consumes

- `specs/io.md` owns normative command IO behavior. It already states that command steps with `output_bundle.path` receive `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, that the runtime-owned value wins over any caller-provided value, that the runtime creates or validates the parent directory before command launch, and that the bundle file is semantic authority. It also states provider structured-bundle target binding for provider steps with `output_bundle.path` or `variant_output.path`.
- `specs/providers.md` owns provider prompt source behavior, prompt composition, consumed-artifact prompt injection, provider template invocation, and provider-session transport boundaries.
- `specs/dsl.md` owns `output_bundle`, `variant_output`, `materialize_artifacts`, `publishes`, `consumes`, authored public contract families, and version gating.
- `specs/state.md` owns runtime state authority and resume identity.
- `docs/design/workflow_lisp_state_layout.md` owns target state/path derivation principles.
- `docs/design/workflow_lisp_key_migration_parity_architecture.md` owns the existing parity evidence shape and non-regression computation.
- `docs/design/workflow_command_adapter_contract.md` owns the policy boundary between legitimate command adapters and hidden semantic glue.
- `docs/lisp_workflow_drafting_guide.md` owns author-facing migration discipline and semantic-authority rules.
- `docs/reports/2026-06-08-generic-review-revise-orc-runtime-gap-report.md` supplies concrete runtime-gap evidence from launching the generic review/revise `.orc` workflow.

### 3.2 This Document Owns

- the required runtime hardening for command structured-output authority;
- the private executable/runtime value-transport contract needed by frontend-lowered Workflow Lisp values;
- the provider structured-output target-binding conformance needed for provider `output_bundle` and `variant_output` steps;
- the strict-gate behavior needed before `migration-parity` is used as a release gate;
- the first implementation boundary for `StateLayout` / `PathAllocator`; and
- the minimum acceptance evidence before additional `.orc` primary-promotion work depends on these surfaces.

### 3.3 This Document Does Not Own

- full command adapter lint policy;
- full public-DSL collection artifact design;
- full state layout path-shape migration;
- review/revise-loop semantics;
- runtime closures or dynamic procedure values;
- semantic diffing beyond explicit parity evidence;
- arbitrary child-process filesystem sandboxing; or
- deep domain correctness of provider outputs.

### 3.4 Target Dependency Directions

Command structured-output authority:

```text
command-result / command step
  -> declared output_bundle contract
  -> runtime path-safety resolution
  -> runtime-owned ORCHESTRATOR_OUTPUT_BUNDLE_PATH
  -> parent directory readiness
  -> command execution
  -> declared bundle validation
  -> typed artifacts / state
```

Frontend-lowered typed value transport:

```text
authored .orc type/value
  -> typed Core / executable contract
  -> runtime value normalization
  -> runtime contract validation
  -> optional materialized view file
  -> publish/consume dataflow
  -> prompt rendering or downstream typed ref
```

Provider structured-output target binding:

```text
provider-result / provider step
  -> declared output_bundle or variant_output contract
  -> runtime path-safety resolution
  -> runtime-owned structured-output target binding
  -> prompt contract text plus out-of-band binding
  -> provider execution
  -> declared bundle validation
  -> typed artifacts / state
```

Migration promotion gate:

```text
target manifest
  -> evidence commands / accepted waivers
  -> schema-validated generated report
  -> computed non_regressive
  -> promotion eligibility
  -> gate/view primary_surface decision
```

Generated path allocation:

```text
semantic allocation request
  -> StateLayout
  -> PathAllocator
  -> neutral allocation metadata
  -> runtime binding + workflow boundary projection + source-map projection + Semantic IR projection
```

### 3.5 Prohibited Dependency Directions

Command structured-output anti-pattern:

```text
authored env var
  -> command-chosen bundle path
  -> stdout JSON or arbitrary file
  -> semantic state
```

Frontend-lowered typed value anti-pattern:

```text
list / record / typed prompt-input value
  -> ad hoc pointer file
  -> markdown/prose encoding
  -> downstream parser
  -> semantic state
```

Provider structured-output anti-pattern:

```text
prompt text mentions target path
  -> provider guesses a sibling directory or filename
  -> runtime copies wrong-path bundle into expected path
  -> semantic state
```

Migration promotion anti-pattern:

```text
hand-authored report
  -> asserted non_regressive=true
  -> primary surface
```

Generated path allocation anti-pattern:

```text
lowering helper A synthesizes path string
lowering helper B synthesizes hidden input
executor helper C synthesizes resume identity
source map reconstructs after the fact
```

Current checkout already contains partial implementation evidence for several surfaces, but this document treats them as foundation-ready only after the verification criteria below pass.

## 4. Current Status Snapshot

| Surface | Current normative status | Current implementation status | Evidence required before foundation-ready |
| --- | --- | --- | --- |
| command `output_bundle.path` env injection | Normative in `specs/io.md` | Must be verified in runtime executor | env override, parent creation/validation, missing-bundle failure tests |
| command `variant_output.path` | Conditional unless accepted in normative specs | Do not assume as foundation behavior | normative spec update, or `output_bundle.path` plus compiler-owned validator/projection |
| provider `output_bundle.path` target binding | Normative in `specs/io.md` / `specs/dsl.md` | Implemented enough to launch, but needs focused conformance evidence | provider target-binding tests and provider spec/readme alignment |
| provider `variant_output.path` target binding | Normative in `specs/io.md` / `specs/dsl.md` | Runtime validates expected path; wrong-path provider output exposed the need for focused coverage | provider target-binding tests and wrong-path failure diagnostic |
| private collection contracts | Not ordinary public authored-YAML boundary | Frontend-lowered executable workflows can expose gaps | validator tests for list/map/record-like values and nested relpaths |
| scalar/list/map materialized value views | Public YAML `pointer.path` remains relpath-only unless widened | Needed for uniform `.orc` prompt-input materialization | string/list/map view tests; pointer-as-view invariants |
| collection publish/consume | Public artifact registry is primarily relpath/scalar | Collection consume can fail at provider boundary | collection artifact publish/consume tests with embedded contracts |
| prompt extern source semantics | `asset_file` is source-relative; `input_file` is workspace-relative | `.orc` extern strings are easy to mislaunch | explicit extern manifest model and docs/examples |
| `migration-parity` report generation | Tool/evidence surface; promotion policy in migration docs | Existing tool computes `non_regressive` | schema validation, strict gate mode, stable nonzero exit tests |
| `non_regressive` | Must be tooling-computed | Existing reports compute it from evidence | target-manifest and hand-authored-report negative tests |
| StateLayout / PathAllocator | Draft design direction | Partial/scattered generated path evidence | one allocation/provenance boundary plus source-map and Semantic IR tests |
| hidden `__write_root__...` inputs | Compatibility mechanism, not public API | Existing generated/private binding mechanics | public-boundary inspection tests and runtime-contract visibility tests |

The remaining gap is coherence: these surfaces are implemented in several places, but not yet hardened as one promotion-grade foundation.

## 5. Problem

Workflow Lisp migration confidence is limited by five related failure modes.

First, command structured-output authority can drift. If authored environment variables can override the runtime-owned `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, a command can write semantic state somewhere other than the contract path. If the runtime does not create or validate the bundle parent before launch, adapters must carry path setup logic that should belong to the runtime contract.

Second, frontend-lowered typed values are richer than the public authored-YAML subset in several places. Generic `.orc` workflows can lower lists, records, typed prompt-input bundles, and nested relpath-containing values into executable contracts. If the runtime still assumes only relpath/scalar values at materialization, publish, consume, and prompt-rendering boundaries, typechecked `.orc` workflows can fail after shared validation.

Third, provider structured-output bundle paths need the same concrete conformance pressure as command bundles. Provider steps may receive `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, and prompt text may contain the expected path, but the observed generic review/revise run showed that a provider can still create a plausible sibling bundle path. Runtime correctly rejected that wrong path; the foundation must prove the provider binding, wrapper, and diagnostics are strong enough that this failure class is rare and explainable.

Fourth, the migration promotion gate is currently stronger than a report but not yet always a hard release valve. It computes `non_regressive`, but a caller can still treat a generated report as advisory unless there is an explicit gate mode, strict report validation, and clear distinction between `non_regressive` and `eligible_for_primary_surface`.

Fifth, generated path allocation is scattered across lowering helpers, managed write-root inputs, source-map generation, semantic IR projection, call binding, and executor entry binding. This makes it easy to fix one path family while leaving another family with stale resume identity, public hidden inputs, or parallel-run collisions.

## 6. Goals

- Make declared command `output_bundle.path` files the semantic authority for command structured outputs.
- Treat command `variant_output.path` as conditional until accepted by normative DSL/IO specs, or lower command-produced unions through `output_bundle.path` plus compiler-owned validator/projection.
- Ensure the runtime, not command adapters, owns structured command bundle target injection and parent-directory readiness.
- Define a private executable/runtime value-transport contract for frontend-lowered scalar, relpath, list, map, record-like, and nested relpath-containing values.
- Keep public authored-YAML compatibility restrictions unless a versioned spec change intentionally widens them.
- Allow frontend-lowered private materialization to write scalar/list/map value-view files without making those files semantic authority.
- Allow frontend-lowered private collection artifacts to publish and consume through runtime dataflow when their embedded contracts are available.
- Prove provider structured-output target binding for provider steps with `output_bundle.path` or `variant_output.path`.
- Preserve post-execution validation as the final authority for provider and command structured outputs.
- Make prompt extern source semantics explicit for Workflow Lisp authoring.
- Make migration promotion fail closed when required evidence is missing, stale, malformed, regressive, or ineligible.
- Keep `non_regressive` computed only by tooling.
- Keep `primary_surface` as a gate/view derivation from computed non-regression and promotion eligibility, not a required report-owned field.
- Introduce a single path/layout allocation boundary for compiler-generated write roots, bundle paths, state paths, materialized view paths, and generated path provenance.
- Preserve existing public API behavior while hiding compiler-owned `__write_root__...` inputs from public entrypoints.
- Preserve source-map and Semantic IR evidence for generated paths.

## 7. Non-Goals

- Do not redesign review/revise-loop, `resume-or-start`, generic effectful composition, or adapter lint policy in this document.
- Do not ban command steps.
- Do not replace YAML primaries based on this design alone.
- Do not introduce a generic semantic diff engine for migration parity.
- Do not rewrite all existing generated paths in one change.
- Do not make reports, stdout, pointer files, materialized value views, or debug YAML semantic authority.
- Do not make `kind: collection` a normal public authored-YAML artifact kind unless a separate versioned DSL decision does that explicitly.
- Do not treat provider environment bindings as sufficient for every raw LLM CLI; prompt contract text remains necessary, but not sufficient as authority.
- Do not silently reinterpret all Workflow Lisp prompt extern strings as workspace-relative prompt files.
- Do not recover from wrong-path provider bundles by copying sibling files into the expected bundle path.

## 8. Architecture Invariants

- Declared command bundle files are semantic authority for structured command results; stdout is not.
- Runtime-owned environment values cannot be overridden by authored environment values.
- Declared provider bundle files are semantic authority for structured provider results; prompt text is guidance, not the only write-location authority.
- Provider wrong-path bundle writes fail; the runtime must not silently copy wrong-path bundles into the expected target.
- Private frontend-lowered typed values remain typed values even when materialized as files for prompt or adapter compatibility.
- Materialized value-view files are views, not semantic authority, unless a contract explicitly says otherwise.
- Public authored-YAML compatibility restrictions remain intact unless a versioned spec deliberately widens them.
- Collection values in private executable workflows must carry enough contract metadata to validate, publish, consume, and render deterministically.
- Prompt consume rendering is a view over resolved consume values; it is not the consume dataflow authority.
- `asset_file` remains workflow-source-relative; `input_file` remains workspace-relative.
- `non_regressive` is computed, never authored.
- Reports are evidence objects, not workflow semantic authority; only schema-valid, gate-accepted reports may contribute to promotion decisions.
- Hidden `__write_root__...` inputs are not public entrypoint inputs.
- Generated private paths are source-mapped and represented in Semantic IR.
- Path allocation failures are diagnostics, not silent fallback to helper-generated strings.
- Existing resume identity is preserved unless an explicit compatibility boundary says otherwise.

## 9. Tranche 1: Command Structured-Output Spec Conformance

### 9.1 Contract

This tranche does not introduce a new semantic rule for `output_bundle.path`. It makes the runtime, tests, and migration evidence conform to the already-normative `specs/io.md` command structured-bundle contract.

For command steps with `output_bundle.path`, implementation evidence must prove that the runtime:

1. resolves the path through the existing output-contract path-safety logic;
2. sets `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` unconditionally to that resolved workspace-relative target;
3. overrides any authored `env.ORCHESTRATOR_OUTPUT_BUNDLE_PATH`;
4. creates or validates the bundle parent directory before command launch;
5. validates the bundle file after successful command exit; and
6. fails the step as an output-contract failure if exit is `0` but the bundle is missing or invalid.

Stdout JSON remains debug/captured output unless the step explicitly uses `output_capture: json`. It must not become structured command state when an `output_bundle` contract is present.

For command-produced union results, this tranche is conditional:

- use `variant_output.path` only after that surface is accepted by the normative DSL/IO specs; or
- lower through an authoritative `output_bundle.path` containing the raw discriminant and payload, followed by a compiler-owned validator/projection step that establishes variant-proof-compatible typed refs.

### 9.2 Tasks

- Resolve the declared bundle path through existing output-contract path-safety logic.
- Set `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` after authored env merge, so the runtime value wins.
- Create or validate the parent directory before command launch.
- Validate the declared bundle after successful command exit.
- Preserve nonzero command exit as primary failure.
- Treat stdout JSON as debug/capture unless the step explicitly uses `output_capture: json`.
- Add or update normative spec text for every structured command-bundle surface covered by this rule.

### 9.3 Acceptance

- Authored env override cannot redirect structured output.
- Runtime creates the bundle parent before launch.
- Exit `0` plus missing bundle fails as output-contract failure.
- Exit `0` plus invalid bundle fails as output-contract failure.
- Nonzero command exit remains primary.
- Stdout JSON does not satisfy a missing bundle.
- Covered command `variant_output` behavior is either normatively specified or explicitly deferred.

### 9.4 Normative Spec Deltas

`output_bundle.path` behavior is already normative in `specs/io.md`.

`variant_output.path` remains conditional in this document. If command-produced `variant_output` with an explicit bundle path is intended to be a promotion foundation surface, update `specs/io.md` and `specs/dsl.md` so that it uses the same runtime-owned environment, parent-readiness, path-safety, and post-exit validation contract as `output_bundle.path`.

## 10. Tranche 2: Frontend-Lowered Typed Value Transport

### 10.1 Contract

Frontend-lowered executable workflows may contain private/internal typed value contracts that are richer than the ordinary public authored-YAML boundary currently exposes.

These private executable values may include:

- scalar values;
- relpath values;
- lists;
- maps;
- record-like JSON objects;
- tagged structured results after validation/projection; and
- nested relpath-containing collection or record values.

The runtime must validate and transport these values coherently across output-contract validation, materialization, artifact publication, artifact consumption, provider prompt rendering, and source-map/layout provenance.

This contract does not by itself widen public authored YAML. Public top-level authored `inputs`, `outputs`, and `artifacts` remain governed by the current DSL version unless `specs/dsl.md` explicitly changes them.

### 10.2 Value Normalization Rules

Runtime validators must apply one shared normalization contract for private frontend-lowered values:

- immutable mapping schemas and plain mapping schemas are equivalent as contract definitions;
- native JSON arrays/objects are accepted directly for list/map contracts;
- JSON string payloads may be decoded as list/map values only at explicitly allowed runtime join or materialization boundaries;
- decoded values are validated identically to native values;
- nested relpath values are normalized and path-checked through the same output-contract path-safety logic used for structured bundles;
- validation errors preserve nested path details; and
- validation failure remains a runtime contract violation, not a provider prompt failure.

The runtime must not require the Workflow Lisp frontend to flatten lists into ad hoc relpath pointer files or encode lists into report prose merely to satisfy older public-YAML assumptions.

### 10.3 Materialized Value Views

A materialized value view is a file representation of a typed value for prompt injection, debugging, compatibility adapters, or legacy command boundaries. It is not semantic authority unless an explicit contract promotes it.

For public authored YAML, `materialize_artifacts.pointer.path` may remain relpath-only unless `specs/dsl.md` intentionally widens that surface.

For frontend-lowered private materialization, the runtime may write value-view files for validated scalar and collection values.

Recommended encoding:

| Value kind | View-file encoding |
| --- | --- |
| string | UTF-8 string plus trailing newline |
| integer / float / bool / null | canonical JSON scalar plus trailing newline |
| list / map | stable canonical JSON plus trailing newline |
| relpath | existing relpath pointer semantics after path-safety normalization |

The value view must retain provenance:

- source typed value;
- contract used for validation;
- source-map origin;
- layout allocation identity, when generated; and
- whether the view is compatibility-only or public artifact materialization.

The term `pointer` should remain reserved for relpath indirection when possible. New docs and diagnostics should prefer `value view`, `materialized view`, or `compatibility view` for scalar/list/map materializations.

### 10.4 Collection Publish/Consume Dataflow

If a frontend-lowered executable workflow publishes a private collection value, the runtime artifact ledger may record it as a collection artifact only when the embedded contract and origin metadata are available.

A private collection artifact record should include at least:

```json
{
  "kind": "collection",
  "private": true,
  "origin": "workflow_lisp_lowering",
  "contract": {
    "type": "list",
    "element": {
      "type": "relpath",
      "under": "docs/design"
    }
  }
}
```

Consume preflight for collection artifacts must:

- validate the selected value against its embedded contract;
- preserve nested validation errors;
- expose native lists/maps in `_resolved_consumes`;
- respect artifact version/producer identity like scalar and relpath artifacts;
- render prompt consume blocks deterministically when prompt injection is enabled; and
- remain a runtime dataflow contract, not merely a prompt-rendering feature.

Prompt rendering for collection consumes must:

- preserve list order;
- stable-sort object keys;
- use deterministic JSON-like formatting unless a more specific renderer is declared;
- include contract/type labels when helpful; and
- never become the authority for the consumed value.

### 10.5 Tasks

- Add or centralize a runtime contract utility for private frontend-lowered scalar/list/map/record-like validation.
- Normalize immutable mapping schema definitions and plain mapping definitions uniformly.
- Decode JSON string list/map payloads only at declared join/materialization boundaries.
- Validate nested relpaths through output-contract path-safety logic.
- Add private materialized value-view support for scalar/list/map values.
- Keep public authored-YAML `pointer.path` compatibility restrictions unless a DSL spec change widens them.
- Allow collection-valued private artifacts to be recorded in `artifact_versions` when they include embedded contracts.
- Allow `consumes` preflight to resolve and validate private collection artifacts.
- Render collection consumes deterministically in provider prompt injection.
- Add source-map and StateLayout provenance for generated value-view files.

### 10.6 Acceptance

- A frontend-lowered `List[DesignDocPath]` value validates as a private executable contract.
- Immutable nested contract schemas and plain dict-like schemas validate equivalently.
- Native list/map values and allowed JSON-string list/map payloads validate to the same normalized value.
- Nested relpath values inside lists/maps are path-safe and constrained by contract.
- String, scalar, list, and map values can be materialized as private value views.
- Value-view files are marked as views and do not become semantic artifact authority.
- Public authored YAML still rejects unsupported collection artifacts unless a versioned DSL decision changes that.
- Collection artifacts published by frontend-lowered workflows can be consumed by downstream provider steps.
- `_resolved_consumes` may contain native list/map values.
- Provider prompt injection renders collection consumes deterministically.
- Collection consume failures are ordinary contract violations with nested details.

### 10.7 Normative Spec Deltas

Add a spec note, either in `specs/dsl.md` or a dedicated executable-value section, stating that collection and record-like contracts may be valid private executable contracts for frontend-lowered workflows even when they are not ordinary public authored-YAML boundary contracts.

Add a `materialize_artifacts` clarification:

- public authored YAML `pointer.path` remains relpath-only unless widened;
- frontend-lowered private materialization may write scalar/list/map value views; and
- value views are representations, not semantic authority.

Add a `publishes`/`consumes` clarification:

- private collection artifacts may be published and consumed only with embedded contracts and provenance; and
- prompt injection is a deterministic rendering over resolved consume values, not the dataflow authority.

## 11. Tranche 3: Provider Structured-Output Target Binding

### 11.1 Contract

For provider steps with `output_bundle.path` or `variant_output.path`, the runtime must resolve the declared structured-output bundle target before provider invocation and expose that target to the provider process through a reserved runtime-owned binding.

The prompt contract may repeat the path and schema, but prompt text is not the only authority for the write location. Post-execution validation accepts only the declared runtime target. Wrong-path bundle writes fail.

Recommended binding name:

```text
ORCHESTRATOR_OUTPUT_BUNDLE_PATH
```

If a provider implementation cannot receive environment variables or a provider template requires a different transport, the provider spec may define an equivalent reserved binding. The invariants remain the same:

- runtime resolves the target;
- runtime-owned binding wins over provider-template or authored values;
- prompt text remains guidance;
- validation accepts only the declared target; and
- wrong-path files are not copied into place as recovery.

### 11.2 Provider Template Interaction

Provider templates may be ordinary CLI commands. The structured-output binding must be applied after provider template/default/step parameter resolution and before process launch.

In argv or stdin provider modes, the composed prompt should still include the output contract suffix. The out-of-band target binding is an additional authority channel for provider wrappers, tool-using providers, local CLIs, and structured-output adapters; it is not a reason to remove prompt guidance.

Provider session and managed-job wrappers must preserve the structured-output binding when they wrap the provider invocation.

### 11.3 Tasks

- Resolve provider `output_bundle.path` and `variant_output.path` through runtime path-safety logic before launch.
- Expose the resolved target through `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` or an accepted provider-equivalent reserved binding.
- Ensure runtime-owned binding wins over template/default/authored values.
- Create or validate the target parent directory before provider launch when the provider is expected to write the bundle directly.
- Preserve prompt output-contract suffix generation.
- Validate only the declared target after provider execution.
- Reject wrong-path bundle writes with clear diagnostics.
- Do not silently copy sibling `result_bundle.json` files into the expected target.
- Update provider-session and managed-job wrappers to preserve the binding.

### 11.4 Acceptance

- Provider `output_bundle.path` receives a runtime-owned structured-output target binding.
- Provider `variant_output.path` receives a runtime-owned structured-output target binding.
- Provider-template or authored env values cannot redirect the structured-output target.
- The provider prompt still contains the structured output contract when injection is enabled.
- Runtime creates or validates the bundle parent before provider launch when applicable.
- A provider that writes the bundle to the declared target succeeds if the bundle validates.
- A provider that writes a valid-looking bundle to a sibling path fails with `missing_bundle_file` or an equivalent clear contract error.
- Wrong-path bundles are not copied into the expected target.
- Provider session and managed-job modes preserve the binding.

### 11.5 Normative Spec Deltas

Provider `output_bundle.path` and `variant_output.path` structured-output target binding is already represented in `specs/io.md` and `specs/dsl.md`. This tranche hardens implementation evidence and documentation alignment.

Update `specs/providers.md` if needed so provider-template and provider-session transport text explicitly preserves the runtime-owned binding.

If command-produced `variant_output.path` remains conditional, keep that distinction explicit: this provider tranche does not by itself accept command-produced `variant_output.path` as a promotion foundation surface.

## 12. Companion Authoring Contract: Prompt Extern Source Semantics

### 12.1 Contract

Workflow Lisp prompt externs must make the source surface explicit enough that reusable libraries and workspace-owned project prompts are not confused.

Current runtime source semantics remain:

- `asset_file` is workflow-source-relative and may not escape the workflow source tree;
- `input_file` is workspace-relative and may be used for workspace-owned or runtime-generated prompt material.

Recommended Workflow Lisp extern manifest model:

```json
{
  "prompts.design-docs.review": {
    "asset_file": "prompts/workflows/review_revise_design_docs/review.md"
  },
  "prompts.project.review": {
    "input_file": "prompts/workflows/project_review/review.md"
  }
}
```

String shorthand remains backward-compatible and means `asset_file`:

```json
{
  "prompts.design-docs.review": "prompts/workflows/review_revise_design_docs/review.md"
}
```

Reusable stdlib/library prompts should normally be bundled assets. Workspace-owned project prompts should use explicit `input_file`.

### 12.2 Acceptance

- Prompt extern string values lower to `asset_file` and are documented as workflow-source-relative.
- Prompt extern object values can declare `asset_file` or `input_file` explicitly.
- `asset_file` prompt externs reject `..` traversal outside the workflow source tree.
- `input_file` prompt externs resolve workspace-relative prompt files.
- Checked-in examples use the correct source surface.
- Diagnostics say whether a missing prompt was resolved as source-relative asset or workspace-relative input.

## 13. Tranche 4: Migration Promotion Gate Hardening

### 13.1 Contract

Keep the existing manifest-driven `migration-parity` model, but harden it into a release gate. The promotion command must define strict gate modes with stable exit semantics.

At minimum, `--require-non-regressive` exits nonzero when any selected target lacks valid, complete, current, computed non-regression evidence.

Gate modes:

`--require-non-regressive`

- selected targets must have `report_valid=true`;
- selected targets must have `evidence_complete=true`;
- selected targets must have computed `non_regressive=true`;
- ineligible targets may pass this gate but must not become primary.

`--require-promotable`

- selected targets must satisfy all `--require-non-regressive` requirements;
- selected targets must also have `eligible_for_primary_surface=true`;
- aggregate promotion decisions may derive `primary_surface` only under this mode.

Decision table:

| `report_valid` | `evidence_complete` | `non_regressive` | `eligible_for_primary_surface` | `--require-non-regressive` | `--require-promotable` | gate-layer `primary_surface` |
| --- | --- | --- | --- | --- | --- | --- |
| false | any | any | any | fail | fail | not derived |
| true | false | any | any | fail | fail | not derived |
| true | true | false | any | fail | fail | not derived |
| true | true | true | false | pass | fail | `yaml` |
| true | true | true | true | pass | pass | `orc` |

The command must validate both freshly generated reports and reused existing reports against the same schema/version contract before including them in an aggregate index.

Existing reports are not authority merely because they are JSON objects. `non_regressive` remains computed from evidence. Target manifests and hand-authored reports must not provide it.

Per-target parity reports stay evidence-only artifacts. If the CLI needs a machine-readable strict-gate result beyond markdown/index rendering, it should emit a separate versioned gate-evaluation object rather than turning the report itself into promotion policy authority.

Gate-layer or derived-view `primary_surface` is derived from:

```text
computed non_regressive
AND promotion_eligibility.eligible_for_primary_surface
```

When `non_regressive=true` but `eligible_for_primary_surface=false`, reports and derived gate views must make the distinction explicit: the candidate may be non-regressive against recorded evidence but still not promotable.

### 13.2 Required Report Fields

The strict gate report schema must include at least:

- `schema_version`;
- `workflow_family`;
- `candidate`;
- `yaml_primary`;
- `target_identity`;
- `evidence`;
- `evidence_freshness`;
- `promotion_eligibility`;
- tooling-computed `non_regressive`;
- `generated_at`;
- `generated_by`;
- `tool_version`; and
- optional accepted waivers with owner and expiry.

`target_identity` must contain the exact identity material strict reuse checks will validate:

- `targets_schema_version`;
- `target_manifest_path`;
- `target_manifest_sha256`;
- `target_index` or another stable selected-target key within that manifest;
- `workflow_family`;
- `candidate_path`;
- `candidate_sha256`;
- `yaml_primary_path`; and
- `entry_workflow`.

`evidence_freshness` must carry the freshness inputs strict gating uses:

- `generated_at`;
- `compile_manifest_path`, when compile evidence produced one;
- `compile_manifest_sha256`, when compile evidence produced one;
- `compiled_workflow_checksum`, when compile/run evidence exposes it;
- `required_artifact_paths` for emitted required compile artifacts; and
- per-role evidence references needed to prove the report still corresponds to the selected target and current evidence set.

`report_valid` and `evidence_complete` are gate-derived checks, not authored fields:

- `report_valid=true` only when the report schema version matches, all required fields above are present, authored computed fields are absent, and `target_identity` matches the selected manifest row exactly.
- `evidence_complete=true` only when required evidence roles are present, required compile artifacts are present, waivers are still valid, and `evidence_freshness` proves the report still matches the selected manifest, compile manifest, and candidate workflow checksum.

`primary_surface` is a gate-layer or derived-view delta in this document. It must be derived by tooling from computed non-regression and eligibility; it is not authored in the target manifest and it is not a required parity-report field.

### 13.3 Acceptance

- Target manifests cannot provide `non_regressive`.
- Hand-authored reports cannot provide authoritative `non_regressive`.
- Reused reports validate schema/version, selected target identity, manifest/checksum freshness, and required evidence references before contributing to an aggregate gate.
- `--require-non-regressive` exits nonzero when any selected target lacks valid, complete, current, computed non-regression evidence.
- `--require-promotable` exits nonzero unless selected targets are both non-regressive and eligible for primary surface.
- Non-regressive but ineligible candidates do not become primary, and `primary_surface` remains a gate/view derivation rather than a report-owned authority field.

## 14. Tranche 5: StateLayout / PathAllocator Foundation

### 14.1 Contract

Introduce a concrete `StateLayout` / `PathAllocator` boundary without forcing a large path migration in the first patch.

The first implementation should centralize allocation and provenance for:

- generated command result bundle write roots;
- generated provider result bundle write roots;
- generated variant projection bundle paths;
- generated value-view files;
- generated internal inputs such as `__write_root__...`;
- reusable call write-root bindings;
- entrypoint runtime-owned managed write roots;
- allocation metadata consumed by source-map projection; and
- allocation metadata consumed by Semantic IR state-layout projection.

The initial allocator should preserve current concrete path shapes where practical; the first migration is ownership/provenance centralization, not a path-shape migration. The important first step is that every generated path family goes through one allocation interface and one provenance interface.

After that interface is stable, path families can move toward the `workflow_lisp_state_layout.md` target: private generated write paths are run-isolated by default, resume reconstructs the same private path for the same run/call-frame/loop identity, and authored stable workspace artifacts remain explicit.

### 14.2 Tasks

- Add a concrete allocation request shape with stable semantic identity, provenance, privacy, resume scope, and path-safety policy.
- Route command-result bundle allocation through the new boundary.
- Route provider-result bundle allocation through the new boundary.
- Route private value-view allocation through the new boundary.
- Route reusable-call write-root allocation through the new boundary.
- Keep downstream projection owners explicit: runtime/executable binding owns generated hidden-input projection, workflow boundary projection owns public boundary explanation, SourceMap owns traceability entries, and Semantic IR owns typed state-layout entries derived from allocation metadata.
- Keep compiler-owned generated write roots hidden from public workflow signatures.
- Preserve current concrete path shapes where practical.

### 14.3 Acceptance

- Generated command result bundle paths route through the allocator.
- Generated provider result bundle paths route through the allocator.
- Generated value-view paths route through the allocator.
- Generated internal inputs remain hidden from public inputs and present in executable/runtime contracts where required.
- Source maps and Semantic IR contain matching generated path/layout entries derived from allocation metadata.
- Repeated calls, loop iterations, and match arms produce collision-proof allocations.
- Resume reconstructs the same allocation identity for the same run and call-frame/loop identity.
- Formatting-only source-span changes do not change stable allocation identity.

### 14.4 StateLayout Non-Goals

`StateLayout` does not own arbitrary child-process filesystem effects, provider report content, semantic artifact values, domain correctness of provider decisions, or queue movement semantics.

## 15. Design Details

### 15.1 Command Bundle Contract

The command execution path has five phases:

```text
resolve contract path
  -> prepare runtime-owned environment and parent directory
  -> run command
  -> validate declared bundle
  -> publish typed artifacts
```

The path passed through `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` is the same path used for post-exit validation. A command cannot select a different semantic target by writing a different env value or by printing JSON to stdout.

Required failure behavior:

| Case | Result |
| --- | --- |
| Authored env sets `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` | Runtime value wins |
| Bundle path unsafe | Step fails before command launch |
| Parent cannot be created/validated | Step fails before command launch |
| Command exits nonzero | Command failure remains primary |
| Command exits `0`, bundle missing | Output-contract failure |
| Command exits `0`, bundle invalid | Output-contract failure |
| Stdout contains valid JSON, bundle missing | Output-contract failure |

### 15.2 Provider Bundle Contract

The provider execution path has five phases:

```text
resolve contract path
  -> prepare runtime-owned structured-output binding and parent directory
  -> compose prompt with output contract
  -> run provider
  -> validate declared bundle
  -> publish typed artifacts
```

The runtime-owned structured-output binding identifies the target used for post-exit validation. Provider prompt text may repeat the target, but prompt text alone is not the authority boundary.

Required failure behavior:

| Case | Result |
| --- | --- |
| Provider template sets output-bundle env to a different value | Runtime value wins |
| Provider bundle path unsafe | Step fails before provider launch |
| Parent cannot be created/validated | Step fails before provider launch |
| Provider exits nonzero | Provider failure remains primary |
| Provider exits `0`, bundle missing | Output-contract failure |
| Provider exits `0`, bundle invalid | Output-contract failure |
| Provider writes valid bundle to sibling path | Output-contract failure |
| Prompt text contains valid schema but bundle missing | Output-contract failure |

### 15.3 Typed Value Transport Contract

Private executable values lowered from Workflow Lisp must have one runtime interpretation across validation, materialization, publication, consumption, and prompt rendering.

Value authority layers:

```text
typed source value
  -> executable contract
  -> normalized runtime value
  -> optional materialized view
  -> artifact ledger entry
  -> resolved consume value
  -> prompt rendering view
```

Authority rules:

- the normalized typed value is semantic authority;
- a structured bundle is authority only after validation;
- a materialized view file is a representation;
- a prompt consume block is a representation;
- a pointer file is a representation unless explicitly contracted otherwise;
- a report is a human-readable view; and
- debug YAML is a projection.

### 15.4 Promotion Gate Contract

The parity report is a machine-readable evidence object, not a checklist summary and not workflow semantic authority.

A report may contribute to promotion only when:

- its schema/version validates;
- it was generated from the selected target manifest;
- required evidence references are present and current;
- computed fields such as `non_regressive` are produced by tooling; and
- the aggregate gate derives promotion decisions from those computed fields.

A report has these evidence layers:

```text
target manifest
  -> evidence commands and accepted waivers
  -> generated report
  -> computed non_regressive
  -> derived aggregate index / gate evaluation
  -> optional primary-surface view or decision
```

Required evidence roles remain those already represented by the migration parity implementation and architecture:

- compile;
- shared validation;
- dry-run or smoke/integration;
- baseline characterization;
- output contract parity;
- terminal state parity;
- artifact parity;
- resume/reuse parity;
- generated-source provenance; and
- deprecated-mechanic replacement or accepted waiver.

The gate must distinguish:

- `report_valid`: the report schema and identity contract are valid for the selected target;
- `evidence_complete`: required evidence exists and is current enough for that selected target and candidate checksum;
- `non_regressive`: evidence proves no required parity regression;
- `eligible_for_primary_surface`: policy allows promotion; and
- `primary_surface`: a gate/view projection selected from those computed inputs, not a report-owned semantic field.

### 15.5 StateLayout / PathAllocator Contract

`StateLayout` owns semantic allocation requests. `PathAllocator` owns concrete path names for those requests. Together they return neutral allocation metadata. Adjacent layers own their own projections over that metadata.

`source_span` is provenance, not identity. Stable allocation identity must be derived from semantic ownership:

- workflow/module identity;
- generated role;
- authored semantic target;
- call-frame identity when applicable;
- loop identity and iteration/visit scope when applicable; and
- lowering schema version when path reconstruction semantics change.

Formatting-only source edits must not change resume identity unless the semantic owner changes.

Illustrative request shape:

```text
layout.allocate(
  owner="workflow_lisp",
  workflow_id="design-plan-stack::review-plan",
  source_span=...,  # provenance only
  semantic_role="provider_result_bundle",
  stable_identity="review-plan/run-review/result",
  privacy="private_generated",
  resume_scope="call_frame",
)
```

Initial semantic roles should use an explicit closed vocabulary rather than free-form strings:

- `command_result_bundle`;
- `provider_result_bundle`;
- `variant_projection_bundle`;
- `materialized_value_view`;
- `reusable_call_write_root`;
- `entrypoint_managed_write_root`;
- `generated_internal_input_binding`; and
- `compatibility_pointer_view`.

Initial privacy classes:

- `public_authored`;
- `public_artifact`;
- `private_generated`;
- `compatibility_view`; and
- `runtime_sidecar`.

Initial resume scopes:

- `none`;
- `run`;
- `call_frame`;
- `loop_frame`;
- `loop_iteration`; and
- `step_visit`.

The returned allocation contains:

```text
generated_input_name, when needed
concrete_path_template
semantic_identity
privacy
path_safety_policy
resume_identity
projection_hints
```

`StateLayout` does not decide semantic workflow outcomes. It decides where compiler/runtime-owned state and generated bundle/view files live, how they are hidden from public inputs, and how they are explained.

Projection ownership stays separate:

- runtime/executable lowering consumes allocation metadata to bind hidden runtime inputs and concrete bundle/write-root paths;
- workflow boundary projection consumes allocation metadata to explain hidden generated inputs without turning them into public authored inputs;
- `source_map.json` consumes allocation metadata plus source provenance to emit traceability entries; and
- Semantic IR consumes allocation metadata to emit `SemanticStateLayoutEntry` records and related bridges.

## 16. Contracts And Interfaces

### 16.1 Runtime

- `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` is runtime-owned for structured command bundle steps.
- Provider structured-output target binding is runtime-owned for provider `output_bundle.path` and `variant_output.path` steps.
- Runtime creates or validates structured bundle parents before launch when the child process is expected to write the bundle directly.
- Runtime validates output bundles after successful command/provider exit.
- Runtime validates private frontend-lowered typed values consistently across validation/materialization/publish/consume/prompt-rendering boundaries.
- Runtime entry binding for compiler-managed write roots remains hidden from public workflow inputs.

### 16.2 CLI

- `migration-parity` remains the machine-readable promotion evidence command.
- Strict gate modes exit nonzero according to the explicit `--require-non-regressive` and `--require-promotable` semantics above.
- CLI docs/specs must describe the command once it is relied on as a release gate.

### 16.3 Workflow Lisp Frontend

- Workflow Lisp may lower richer private typed values than public authored YAML exposes, but only into validated executable contracts with source-map provenance.
- Workflow Lisp must not flatten collections into report prose or ad hoc pointer files to work around runtime gaps.
- Workflow Lisp prompt externs must document and validate whether each prompt source is `asset_file` or `input_file`.
- Generated private write roots and materialized view paths must go through StateLayout/PathAllocator once that boundary exists.

### 16.4 Generated Artifacts

- `source_map.json` records generated paths, value views, and generated internal inputs from allocation metadata plus source provenance.
- Semantic IR records corresponding state-layout entries derived from the same allocation metadata.
- Validated parity JSON reports are machine-readable gate evidence.
- Parity JSON reports are not workflow semantic authority and do not redefine runtime behavior.
- Markdown parity reports and indexes are views.

## 17. Dependencies And Sequencing

Tranche 1 should land first because it proves runtime conformance to the normative command structured-bundle contract and strengthens every command-result migration.

Tranche 2 should land next or in parallel with the first StateLayout facade because generic `.orc` workflows already lower typed values that cross runtime boundaries. The public authored-YAML surface need not widen before private executable value transport is supported.

Tranche 3 should land with provider/spec/runtime conformance checks before generic provider-result review loops are used as migration evidence. Provider wrong-path structured output must remain fail-closed, and provider structured-output target binding should reduce avoidable wrong-path failures.

Tranche 4 can land after or alongside Tranche 1 because the command exists; hardening it does not require StateLayout to be complete. It should include any spec/CLI doc updates needed to treat the command as a gate.

Tranche 5 should follow as a staged refactor. It has broader blast radius and should start by routing existing allocation families through a shared boundary without changing all concrete paths at once.

Work that can proceed in parallel:

- report-schema validation for existing parity reports;
- CLI spec/doc alignment for `migration-parity`;
- focused tests for command bundle env precedence;
- focused tests for provider structured-output binding;
- runtime validation tests for private collection values;
- prompt extern docs/examples; and
- inventory of generated path families that currently bypass a shared layout interface.

Work that should wait for this foundation:

- treating additional `.orc` candidates as primary YAML replacements;
- broad strict adapter-lint enforcement;
- large-scale generated path shape changes;
- public authored-YAML collection artifact expansion; and
- any generic stdlib workflow promotion that depends on collection publish/consume or provider structured-output path authority.

## 18. Work Blocked Until This Foundation Lands

- Additional `.orc` candidates treated as primary YAML replacements.
- Generic review/revise `.orc` workflows used as promotion evidence while private typed value transport is unstable.
- Broad strict adapter-lint enforcement.
- Generated path-shape migration.
- Any feature that relies on compiler-owned write roots being hidden from public entrypoints.
- Any promotion report being used as a release gate without schema validation and strict gate semantics.
- Any workflow relying on provider structured-output bundle placement without runtime-owned target binding or explicit wrong-path failure coverage.
- Any public authored-YAML collection artifact design that bypasses private executable value transport evidence.

## 19. Evidence And Implementation Boundaries

### 19.1 Required Evidence

Implementation follows this design only if the default runtime command path sets structured bundle env values, creates/validates parents, and validates the declared bundle. Adapter-side `mkdir` calls and tests that manually write bundle files are not sufficient evidence.

Provider structured-output follows this design only if provider steps receive a runtime-owned structured-output target binding, wrong-path bundle writes fail, and provider-session/managed-job wrappers preserve the binding.

Typed value transport follows this design only if private frontend-lowered collection values validate, materialize, publish, consume, and render through shared runtime contracts. Frontend-specific workaround lowering is not sufficient evidence.

Migration promotion follows this design only if the CLI can fail as a gate. Generated reports that compute `non_regressive` but never affect exit behavior are useful evidence, but not a release valve.

State layout follows this design only if generated path families route through one allocation/provenance boundary. Existing helpers that merely keep producing `__write_root__...` names are compatibility mechanics, not the target architecture.

### 19.2 Prohibited Evidence

The following do not prove this foundation:

- a command adapter that creates its own bundle parent;
- a test that writes the bundle manually instead of using the runtime command path;
- a provider prompt that merely mentions the output bundle path;
- a provider that writes a valid bundle to a sibling path and relies on runtime copy-recovery;
- a collection value flattened into markdown prose;
- a list encoded in an ad hoc relpath pointer file without an embedded contract;
- a string/list/map view file treated as artifact authority;
- a parity JSON file with hand-authored `non_regressive`;
- a report accepted without schema/version validation;
- a reused report accepted without matching manifest hash or candidate/workflow checksum evidence;
- a generated path visible only in debug YAML but absent from source maps or Semantic IR; or
- an implementation that preserves `__write_root__...` public inputs and calls that "compatibility."

## 20. Compatibility And Migration

Existing YAML and `.orc` workflows remain valid.

Command steps that already honor `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` continue to work. Command steps that intentionally override that variable become invalid for structured bundle contracts because the runtime-owned value wins.

Provider steps that already write to the declared structured-output bundle path continue to work. Provider templates and wrappers should preserve the runtime-owned target binding. Provider steps that write structured bundles to sibling paths remain invalid; they should be fixed to write the declared target rather than rescued by copy-recovery.

Command adapters remain legitimate when they invoke external tools or certified adapters with declared inputs, outputs, effects, fixtures, and source maps. Hidden semantic glue in inline Python/shell, report parsing, pointer-as-state, or ad hoc JSON rewrites remains migration debt under `docs/design/workflow_command_adapter_contract.md`.

Private frontend-lowered collection and record-like values are compatibility additions to executable/runtime transport. They do not require public authored-YAML workflows to accept collection artifacts unless the DSL spec intentionally widens that surface.

Existing public `materialize_artifacts.pointer.path` behavior remains conservative. Private generated value views may use a broader internal materialization contract and should be marked as views.

Existing prompt extern string manifests remain valid as `asset_file` shorthand. New examples should prefer explicit object entries when there is any chance of confusing source-relative assets with workspace-relative prompt files.

Existing parity reports remain readable, but strict gate mode may reject old reports that lack schema/version fields, target-identity fingerprints, or required freshness evidence. That is expected: old evidence can remain historical, but it should not be promotion gate evidence.

StateLayout migration is incremental. The first implementation should preserve current concrete paths where practical and move ownership behind an allocator facade before changing path shapes.

## 21. Verification Strategy

### 21.1 Command Structured-Output Tests

- authored env sets `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` to an absolute path: runtime value wins, no escape occurs;
- authored env sets `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` to a different workspace-relative path: runtime value wins;
- runtime creates the bundle parent before command launch;
- bundle parent path containing `..` fails path-safety validation before launch;
- symlink-escape bundle parent fails path-safety validation according to security/path rules;
- `output_capture: json` plus `output_bundle.path`: stdout JSON is captured/debug only and the bundle remains semantic authority;
- stdout JSON without bundle fails as missing bundle;
- nonzero command exit remains primary over bundle validation;
- command exits zero and writes valid stdout JSON but no bundle: output-contract failure;
- command under reusable `call` preserves workspace-relative authored contract paths while runtime-owned identities remain namespaced;
- `variant_output.path` is tested only after normative spec support exists, or the `output_bundle.path` plus validator/projection route is tested instead.

### 21.2 Frontend-Lowered Typed Value Transport Tests

- collection-valued private executable contracts validate;
- immutable mapping schemas and plain mapping schemas validate equivalently;
- native list/map values validate;
- allowed JSON-string list/map payloads decode and validate at declared join/materialization boundaries;
- JSON-string collection payloads are rejected where decoding is not declared;
- nested relpaths inside lists/maps are path-safe and constrained by `under`;
- scalar/list/map materialized value views are written with stable encoding;
- value views are not recorded as semantic authority unless explicitly contracted;
- public authored YAML still rejects unsupported collection artifacts;
- private collection artifacts publish with embedded contracts and provenance;
- private collection artifacts consume with nested validation details;
- provider prompt consume injection renders collection values deterministically.

### 21.3 Provider Structured-Output Target Binding Tests

- provider `output_bundle.path` receives a runtime-owned structured-output binding;
- provider `variant_output.path` receives a runtime-owned structured-output binding;
- provider-template/default/authored env cannot redirect the target;
- provider prompt contract still includes the concrete path and schema when injection is enabled;
- runtime creates or validates the target parent before provider launch when applicable;
- provider writes valid bundle to declared target: step succeeds;
- provider writes valid bundle to sibling directory path: step fails with missing/invalid declared bundle;
- provider-session mode preserves the target binding;
- managed-job provider wrapper preserves the target binding;
- wrong-path bundle copy-recovery is absent.

### 21.4 Prompt Extern Tests

- prompt extern string defaults to `asset_file`;
- prompt extern object accepts `asset_file`;
- prompt extern object accepts `input_file`;
- `asset_file` rejects escape outside workflow source tree;
- `input_file` resolves workspace-relative prompt files;
- missing prompt diagnostics identify the source surface used.

### 21.5 Migration Gate Tests

- target manifest rejects authored `non_regressive`;
- hand-authored parity report `non_regressive` is rejected or ignored in favor of a computed value;
- strict reuse checks require target manifest hash and candidate/workflow checksum identity material in the report;
- reused report generated from a different target manifest hash is rejected;
- reused report generated from a different workflow checksum is rejected;
- strict gate exits nonzero for regressive eligible targets;
- strict gate exits zero for non-regressive eligible targets;
- non-regressive but ineligible target does not become primary;
- strict promotable mode exits nonzero for an ineligible target;
- markdown-only report never contributes to promotion;
- reused existing reports are schema/version validated;
- report validity and evidence completeness are derived from the report's identity/freshness fields rather than authored booleans;
- expired waivers, missing required evidence, missing required artifacts, and hidden managed write-root inputs force non-regression false;
- aggregate index or gate-evaluation view derives `primary_surface` from computed non-regression and promotion eligibility.

### 21.6 StateLayout Tests

- generated command result bundle paths route through the allocator;
- generated provider result bundle paths route through the allocator;
- generated value-view paths route through the allocator;
- generated internal inputs remain hidden from public inputs and present in runtime contracts;
- source maps and Semantic IR contain matching generated path/layout entries;
- repeated calls, loop iterations, and match arms produce collision-proof allocations;
- resume reconstructs the same allocation identity for the same run and call-frame/loop identity;
- formatting-only source-span changes do not change stable allocation identity;
- semantic target changes do change allocation identity;
- private generated path differs across independent runs when run-isolation is required;
- same procedure called from two call sites does not collide;
- absolute paths and `..` escapes are rejected.

## 22. Declarative Acceptance Scenarios

### 22.1 Command Bundle Authority

Initial state: a workflow has a command step with an `output_bundle.path` and an authored env value for `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`.

Entrypoint:

```bash
python -m orchestrator run ...
```

Expected result: runtime overrides the authored env value, the command sees the contract path, the bundle validates, and the step artifacts come from the bundle file.

Forbidden result: stdout JSON or the authored env path becomes semantic state.

### 22.2 Frontend-Lowered Collection Transport

Initial state: a `.orc` workflow lowers `context_docs` as a `List[DesignDocPath]`, materializes it for prompt input, publishes it, and a provider step consumes it.

Entrypoint:

```bash
python -m orchestrator run workflows/examples/review_revise_design_docs.orc ...
```

Expected result: the list validates as a private executable value, its materialized view is written as deterministic JSON, the artifact ledger records embedded contract/provenance, consume preflight resolves a native list, and the prompt consume block renders deterministically.

Forbidden result: the runtime rejects `artifact_kind: collection`, requires a relpath pointer workaround, or treats the materialized view file as semantic authority.

### 22.3 Provider Structured-Output Target Binding

Initial state: a provider review step declares a `variant_output.path` for a `ReviewDecision` union.

Entrypoint:

```bash
python -m orchestrator run workflows/examples/review_revise_design_docs.orc ...
```

Expected result: runtime resolves the variant bundle target, exposes it through a reserved binding, includes it in the prompt contract, and validates only that target after provider execution.

Forbidden result: the provider writes `.../__result_bundle/result_bundle.json`, runtime copies it to `.../__result_bundle.json`, and the workflow treats that as valid structured state.

### 22.4 Promotion Gate

Initial state: a parity target has compile and dry-run evidence but missing resume parity.

Entrypoint:

```bash
python -m orchestrator migration-parity \
  workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json \
  --require-non-regressive
```

Expected result: the report is generated, `non_regressive=false`, and the CLI exits nonzero for an eligible promotion target.

Forbidden result: the target appears as primary `.orc` because it compiled.

### 22.5 Generated Path Allocation

Initial state: a `.orc` workflow calls the same reusable procedure twice inside a loop, and each call lowers to a provider-result or command-result bundle.

Entrypoint: compile, shared validation, and dry-run/run.

Expected result: each generated bundle path has one allocator identity, one hidden runtime input when needed, matching source-map and Semantic IR entries, and no collision across calls or loop iterations.

Forbidden result: generated path strings are synthesized independently by lowering helpers with no common provenance.

## 23. Success Criteria

- Command structured-output tests pass for env precedence, parent creation, and missing-bundle fail-closed behavior.
- Frontend-lowered private collection values validate, materialize, publish, consume, and render through shared runtime contracts.
- Provider structured-output target binding exists for `output_bundle.path` and `variant_output.path`, with wrong-path bundle writes failing closed.
- Prompt extern source semantics are explicit, documented, and covered by examples/tests.
- `migration-parity` has a strict gate mode with focused CLI tests.
- Existing parity reports and indexes are still generated, but reused reports are schema/version checked.
- A `StateLayout` / `PathAllocator` implementation boundary exists and at least command-result, provider-result, reusable-call write-root, and value-view allocation route through it.
- Source-map and Semantic IR tests prove generated path provenance survives.
- No public workflow entrypoint exposes compiler-owned `__write_root__...` inputs.
- The generic design-doc review/revise workflow can route typed review decisions without frontend-specific runtime crashes, hidden prompt-path assumptions, collection-artifact failures, or provider structured-output placement failures.
- `git diff --check` passes.
