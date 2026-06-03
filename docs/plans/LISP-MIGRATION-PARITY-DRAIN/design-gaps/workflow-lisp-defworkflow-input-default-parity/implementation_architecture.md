# Workflow Lisp Defworkflow Input-Default Parity Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-defworkflow-input-default-parity`
Target design: `docs/design/workflow_lisp_key_migration_parity_architecture.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected migration-parity gap:

- add authored `:default` support on `defworkflow` boundary parameters;
- lower authored defaults onto the existing workflow input contract `default`
  field instead of relying on ad hoc frontend-only behavior;
- keep caller override precedence aligned with the existing runtime binding
  rules for workflow inputs and imported workflow calls;
- typecheck default literals at compile time where the authored type is known,
  while leaving path-root and existence enforcement with the existing shared
  contract/runtime validators;
- preserve current public/internal compiled-workflow input surfaces so defaults
  appear only on public authored inputs and never on compiler-managed hidden
  inputs;
- fold the current top-level `PhaseCtx` auto-default helper into a generalized
  default-attachment path so authored defaults become the primary contract and
  compatibility defaults remain subordinate.

Out of scope for this slice:

- defaults on `defproc`, `defun`, local bindings, record fields, or workflow
  call-site `with:` bindings;
- dynamic or effectful defaults, computed defaults, environment-dependent
  defaults, or defaults that require macro-time filesystem access;
- defaults for structured record-valued boundary parameters that flatten to
  multiple workflow inputs;
- review-loop composition, carried findings, command-result bundle ownership,
  `resume-or-start`, reusable-state validation, or promotion-report policy;
- changes to `specs/dsl.md`, `specs/io.md`, runtime command execution, source
  map schemas, Core Workflow AST, Semantic IR, or Executable IR.

This is a bounded implementation architecture for one gap only. It does not
replace the parent migration architecture or reopen the umbrella Workflow Lisp
frontend contract.

## Problem Statement

The selected target design already chose the intended workflow-default model:

- Workflow Lisp should support defaults at the `defworkflow` boundary.
- Those defaults should lower to the existing DSL workflow input `default`
  contract.
- Caller-provided values must override defaults.
- Literal default kinds should be checked at compile time, with path and
  existence constraints enforced by the existing contract/runtime layers.

The current checkout still falls short in four concrete ways:

1. `workflows.py` only accepts two-item workflow parameters, `(name Type)`, so
   the authored `:default` surface does not parse.
2. `WorkflowParam` and `WorkflowSignature` carry no authored default metadata,
   so typecheck and lowering cannot distinguish explicit boundary defaults from
   ordinary parameters.
3. `derive_workflow_signature_contracts(...)` attaches defaults only through
   `_apply_workflow_input_defaults(...)`, which is a narrow compatibility helper
   for top-level `PhaseCtx` parameters rather than a public `.orc` authoring
   contract.
4. The runtime already knows how to apply workflow input defaults
   (`bind_workflow_inputs(...)` and imported-call binding both honor
   `spec["default"]`), but there is no `.orc` fixture or regression coverage
   proving that authored defaults reach those existing paths.

The gap is therefore not "invent workflow defaults" and not "change runtime
binding precedence." The gap is to expose the existing DSL/runtime default
contract at the Workflow Lisp `defworkflow` boundary and validate that
authored defaults survive parse, typecheck, lowering, build artifacts, loader
surfaces, and runtime binding.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
  - `Required Changes By Gap`
  - `Compiler And Lowering Layer`
  - `Workflow Input Defaults`
  - `Dependencies And Sequencing`
  - `Verification Strategy`
- `docs/design/workflow_lisp_frontend_specification.md`
  - Sections 8.9, 19, 45, 50, 59-62, 74, 76.1, 95, 100
- `docs/design/workflow_command_adapter_contract.md`
- `docs/lisp_workflow_drafting_guide.md`
- `specs/dsl.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`
- `docs/steering.md`

The slice must preserve these guardrails:

- keep Workflow Lisp boundary defaults as typed contract data, not prompt text,
  report text, pointer files, or runtime side effects;
- keep the runtime as the authority for applying input defaults once a compiled
  workflow contract exists;
- keep shared contract validation authoritative for relpath roots, path safety,
  and `must_exist`/`must_exist_target` enforcement;
- keep compiled-workflow public/internal input separation intact so authored
  defaults only apply to public user-bindable inputs;
- keep frontend-owned logic under `orchestrator/workflow_lisp/` and avoid
  widening runtime ownership under `orchestrator/workflow/`;
- do not treat the empty `docs/steering.md` file as permission to broaden the
  slice.

`docs/design/workflow_command_adapter_contract.md` remains authoritative even
though this slice should not add command adapters or command-step behavior.
Workflow defaults must not become a side path for hidden semantic glue.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-command-result-compiler-owned-bundle-paths/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-findings-structured-dataflow/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-loop-generic-effectful-composition/implementation_architecture.md`

### Decisions Reused

- Reuse the public/internal compiled-workflow input split established by the
  command-result managed-write-root slice. Authored defaults belong only on the
  public input contracts.
- Reuse the existing runtime binding precedence in
  `orchestrator/workflow/signatures.py` and `orchestrator/workflow/calls.py`:
  caller-provided value first, then contract default, then required-input
  failure.
- Reuse the existing Workflow Lisp package boundary: parse/typecheck/lowering
  changes stay in `orchestrator/workflow_lisp/`; runtime binding logic remains
  in `orchestrator/workflow/`.
- Reuse the current build-manifest and boundary-projection model where the
  flattened input `contract_definition` is the authoritative serialized
  location for input-default data.

### New Decisions In This Slice

- Extend `defworkflow` parameter syntax to allow one bounded default form:
  `(name Type :default <literal>)`.
- Restrict authored defaults in this slice to parameters whose boundary type
  lowers to exactly one scalar or relpath workflow input contract.
- Normalize authored defaults during frontend typecheck into the same plain
  JSON-compatible scalar values the runtime already expects in workflow input
  contracts.
- Give authored defaults precedence over the existing generated `PhaseCtx`
  compatibility helper when both could target the same flattened input.

### Conflicts Or Revisions

The current checkout implicitly treats autogenerated top-level `PhaseCtx`
defaults as the only Workflow Lisp input-default mechanism. This slice narrows
that assumption:

- authored `defworkflow` defaults become the primary public contract;
- the existing `PhaseCtx` helper becomes a compatibility fallback only;
- runtime default application semantics are unchanged.

No shared concepts are redefined. Core Workflow AST, Semantic IR, TypeCatalog,
SourceMap, pointer authority, variant proof, and runtime execution ownership
remain with their existing owners.

## Ownership Boundaries

This slice owns:

- `defworkflow` parameter parsing and authored-default representation in
  `orchestrator/workflow_lisp/workflows.py`;
- frontend diagnostics for malformed, unsupported, or type-invalid workflow
  defaults;
- default-aware workflow signature and boundary-contract derivation in
  `orchestrator/workflow_lisp/contracts.py`;
- focused fixtures and tests for parse/typecheck/lowering/build/runtime
  propagation of authored defaults.

This slice intentionally does not own:

- runtime default-application precedence in
  `orchestrator/workflow/signatures.py` or `orchestrator/workflow/calls.py`,
  except to rely on their current semantics;
- record-valued or collection-valued default authoring;
- command adapters, provider contracts, reusable-state validation, or
  review-loop semantics;
- new build-artifact schema families or source-map schema changes;
- changes to normative DSL/runtime specs, because the existing DSL input
  default contract is already sufficient.

## Current Checkout Facts

The current checkout already contains the main substrate this slice should
reuse:

- `specs/dsl.md` already defines workflow input contracts with an optional
  `default` field.
- `bind_workflow_inputs(...)` in `orchestrator/workflow/signatures.py` already
  applies the precedence required by the target design:
  provided value, then `default`, then missing-required failure.
- imported workflow call binding in `orchestrator/workflow/calls.py` already
  follows the same precedence for callee inputs.
- prior parity work already separated public inputs from generated internal
  write-root inputs in `orchestrator/workflow/loaded_bundle.py`.

The current checkout also shows the exact missing authoring behavior:

- `WorkflowParam` records only `name` and `type_name`.
- `_elaborate_param(...)` rejects any parameter list that is not exactly two
  items long.
- `derive_workflow_signature_contracts(...)` has no authored-default input and
  calls `_apply_workflow_input_defaults(...)`, which only synthesizes defaults
  for top-level `PhaseCtx` fields.
- there is no `.orc` fixture or test that proves an authored `:default`
  survives from `defworkflow` source into the compiled workflow input contract.

This makes the slice feasible without a new runtime primitive or spec delta.
The missing pieces are one bounded grammar extension, one typed/default-aware
workflow signature path, one generalized contract-attachment step, and the
regression coverage that proves the resulting compiled workflow already works
with the runtime’s existing input-default semantics.

## Proposed Architecture

### 1. Extend `defworkflow` Parameter Grammar With One Bounded Default Form

Accept exactly two parameter shapes in `defworkflow` signatures:

- `(name Type)`
- `(name Type :default <literal>)`

No other parameter keywords are introduced in this slice.

Parsing rules:

- reject unknown keywords with a frontend parse diagnostic;
- reject a missing value after `:default`;
- keep the parameter itself as the diagnostic span anchor so authored errors
  report at the workflow boundary rather than in later lowering;
- preserve macro expansion provenance on the parsed default just like the rest
  of the parameter.

This keeps the authoring surface narrow and avoids widening the slice into a
general keyword-parameter system.

### 2. Add Authored Default Metadata To Workflow Parameters And Signatures

`WorkflowParam` needs one optional authored-default field that retains:

- the authored syntax literal;
- the original span/form-path for diagnostics;
- the normalized frontend value once typecheck succeeds.

`WorkflowSignature` should then carry enough resolved metadata for contract
derivation to decide:

- whether a parameter has an authored default;
- whether that default is valid for the resolved boundary type;
- whether the parameter lowers to exactly one workflow input contract or to a
  structured multi-field boundary that this slice intentionally does not
  support.

This keeps default handling attached to the workflow-boundary contract path
instead of inventing a separate side table in lowering.

### 3. Restrict Authored Defaults To One-Field Scalar Or Relpath Boundaries

This slice intentionally does not solve structured record defaults.

Authoring rule:

- a `:default` is valid only when the parameter’s resolved boundary type lowers
  to exactly one flattened workflow input contract;
- the resolved contract must be scalar or relpath;
- if the parameter lowers to multiple flattened fields, frontend typecheck
  rejects the authored default for this slice.

Consequences:

- path-type parameters work and cover the target-design examples;
- scalar primitives and enum parameters can participate;
- record-typed params such as `PhaseCtx`, `ItemCtx`, and `DrainCtx` cannot gain
  authored `:default` through this slice;
- no record literal, list, map, union, `WorkflowRef`, or `ProcRef` defaults
  are added.

This is the smallest boundary-default surface that satisfies YAML default
parity pressure without reopening structured default design.

### 4. Normalize Literal Defaults During Frontend Typecheck

The frontend should typecheck authored defaults before they are attached to
workflow contracts.

Normalization policy for this slice:

- `String` and relpath/path-typed defaults use string literals;
- `Int`, `Float`, and `Bool` use the existing scalar literal forms;
- enum defaults use authored enum-symbol literals and normalize to the enum
  member string stored in workflow contracts;
- `nil`, collection literals, record literals, union literals, and effectful
  expressions are rejected for boundary defaults in this slice.

Validation ownership split:

- frontend typecheck validates literal shape and type compatibility;
- shared contract/runtime validation remains the authority for path-safety,
  root constraints, and target-existence rules once the default is embedded in
  the generated input contract.

This matches the target design’s requirement: compile-time literal-type
checking without duplicating the runtime’s contract validator.

### 5. Generalize Contract Attachment Around Authored Defaults

Replace the current "PhaseCtx-only" default attachment path with a generalized
attachment function that merges two sources:

1. authored workflow-param defaults;
2. compatibility-generated top-level `PhaseCtx` defaults.

Priority order:

- authored default wins when present;
- otherwise existing `PhaseCtx` compatibility defaults may still populate the
  flattened input definition;
- if neither source applies, the input contract remains unchanged.

This preserves current dry-run/example behavior while making authored defaults
the public contract and preventing the compatibility helper from blocking the
new surface.

### 6. Keep Lowering And Runtime Binding Contract-Shaped

No new executable step, runtime hook, or source-map schema is needed.

The implementation should rely on the existing path:

- `defworkflow` parse/typecheck resolves a normalized default;
- boundary-contract derivation writes `definition["default"] = ...` on the
  flattened public input contract;
- build artifacts and typed loaded bundles expose that default through the
  ordinary workflow input contract surfaces;
- runtime entry binding and imported workflow call binding continue using the
  same existing precedence logic with no Lisp-specific branch.

This is the core bounded decision of the slice: defaults remain contract data,
not an execution feature.

### 7. Preserve Public/Internal Input Separation

Authored defaults apply only to public authored boundary inputs.

They must not:

- attach to compiler-generated `__write_root__...` internal inputs;
- change `generated_internal_inputs` provenance or ownership;
- require callers to bind hidden inputs manually;
- alter runtime-managed write-root allocation rules established by the
  command-result slice.

If a compiled workflow contains both authored defaults and internal generated
inputs, the public input helpers should expose only the authored defaults on
the public names and leave internal input handling unchanged.

### 8. Keep Build Artifacts And Diagnostics Minimal

No new build-artifact schema is required for this slice.

The authoritative serialized evidence of a successful default lowering is:

- the `default` field inside the flattened input `contract_definition`;
- the compiled workflow input contract visible through the loader helpers;
- runtime binding behavior when the caller omits the corresponding input.

Frontend diagnostics should remain local to the `defworkflow` parameter site.
One bounded diagnostic family is sufficient for:

- malformed `:default` syntax;
- unsupported boundary type shape for defaults;
- literal/type mismatch;
- invalid enum member.

## Proposed Code Footprint

- `orchestrator/workflow_lisp/workflows.py`
- `orchestrator/workflow_lisp/contracts.py`
- `tests/test_workflow_lisp_workflows.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_lisp_frontend_autonomous_drain_runtime.py`
- `tests/fixtures/workflow_lisp/valid/`
- `tests/fixtures/workflow_lisp/invalid/`

Shared components intentionally reused, not owned here:

- `orchestrator/workflow/signatures.py`
- `orchestrator/workflow/calls.py`
- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/workflow_lisp/source_map.py`
- `specs/dsl.md`

## Acceptance Conditions

- Workflow Lisp accepts authored `defworkflow` parameters with
  `:default <literal>` in the bounded supported shapes.
- The frontend rejects malformed or unsupported defaults with parameter-local
  diagnostics.
- Successful defaults appear in the compiled workflow input contract as the
  existing DSL `default` field.
- Caller-provided workflow inputs still override defaults for both entry
  workflow binding and imported workflow calls.
- Authored defaults do not appear on compiler-generated internal inputs and do
  not disturb managed write-root ownership.
- The existing autogenerated `PhaseCtx` compatibility defaults continue to
  function only when no authored default is present.
- No new runtime primitive, command adapter, report parsing path, pointer
  authority path, or source-map schema is introduced.

## Verification Strategy

Use focused checks that prove each layer of the contract:

- parse/typecheck coverage for valid and invalid authored defaults;
- lowering/build-artifact coverage proving the flattened input contract stores
  the `default` field;
- runtime entry-binding coverage proving omitted inputs bind from the compiled
  default;
- imported-call coverage proving callee defaults still work through the
  existing runtime precedence path;
- migration-facing coverage proving the new surface closes the parity gap
  without reintroducing hidden inputs or widening unrelated workflow behavior.

## Summary

This slice keeps workflow input default parity deliberately small: authored
`defworkflow` defaults become a first-class boundary contract for one-field
scalar/relpath parameters, lower directly onto the existing DSL input `default`
field, reuse existing runtime precedence, and subordinate the current
`PhaseCtx` auto-default helper instead of treating it as the public feature.
