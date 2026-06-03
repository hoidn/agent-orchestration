# Workflow Lisp Command-Result Compiler-Owned Bundle Paths Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-command-result-compiler-owned-bundle-paths`
Target design: `docs/design/workflow_lisp_key_migration_parity_architecture.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected migration-parity gap:

- keep `command-result` structured-output bundle targets compiler/runtime-owned
  rather than public `__write_root__...` workflow inputs;
- preserve the existing explicit `command-result` command boundary, structured
  output contract, and source-map coverage;
- split compiled Workflow Lisp input surfaces into public boundary inputs and
  internal managed write-root inputs;
- let runtime-owned entry-workflow binding allocate deterministic managed
  bundle paths so users do not pass them manually;
- preserve existing reusable/private workflow call-site managed write-root
  bindings without treating those internal bindings as public authoring API.

Out of scope for this slice:

- review-loop generic composition, carried findings, or `review-revise-loop`
  lowering;
- `resume-or-start`, reusable-state validation, or workflow input defaults;
- promotion reports, `non_regressive` computation, or deprecating YAML
  primaries;
- changing the normative `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` runtime contract in
  `specs/io.md` or `specs/dsl.md`;
- new runtime-native effects, adapter families, inline Python/shell glue, or
  report parsing;
- broad provider-result or phase-context write-root redesign outside the
  `command-result` lowering family.

This is a bounded implementation architecture for one gap only. It does not
replace the parent migration architecture or reopen the umbrella Workflow Lisp
frontend contract.

## Problem Statement

The selected target design already established the intended ownership model:

- `command-result` bundle targets are compiler/runtime-owned;
- managed bundle roots may exist in the current lowering representation, but
  they are internal implementation details rather than public entrypoint API;
- the runtime, not the user, owns the final binding of
  `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`;
- parity promotion is blocked if users must pass `__write_root__...` inputs
  manually.

The current checkout still leaks that internal representation as public surface
in three places:

1. `_lower_command_result(...)` creates a generated `__write_root__...` name
   and `lower_workflow_definitions(...)` appends it to `authored_mapping["inputs"]`.
2. typed bundle helpers and key-migration tests still treat those names as
   visible workflow inputs rather than provenance-tagged internal inputs.
3. top-level runtime execution for migrated `.orc` fixtures still binds those
   names manually, proving that entry-workflow ownership is not yet runtime
   complete.

The gap is therefore no longer "invent a structured command bundle path
contract." The specs already define that contract. The remaining gap is to make
the compiler/runtime own those paths end-to-end without weakening explicit
command boundaries or forcing users to know internal write-root names.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
  - `Required Changes By Gap`
  - `2. Compiler And Lowering Layer`
  - `Command Structured Output Contract`
  - `Dependencies And Sequencing`
  - `Evidence And Implementation Boundaries`
  - `Verification Strategy`
- `docs/design/workflow_lisp_frontend_specification.md`
  - Sections 16, 17, 22, 23, 45-57, 63, 65, 74, 76.1, 95, 102
- `docs/design/workflow_language_design_principles.md`
- `docs/design/workflow_command_adapter_contract.md`
- `specs/dsl.md`
- `specs/io.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`

The slice must preserve these guardrails:

- keep command semantics explicit: `command-result` still lowers to a declared
  command step plus a structured result contract;
- keep structured bundles authoritative and stdout/debug output non-authoritative;
- keep compiler-generated values source-mapped and ownership-tagged;
- keep shared validation authoritative rather than bypassing it with ad hoc
  runtime exceptions;
- keep imported/reusable workflow call-site write-root bindings deterministic
  and caller-owned;
- keep command-adapter rules from
  `docs/design/workflow_command_adapter_contract.md` authoritative for any
  command invoked through `command-result`;
- do not treat the empty `docs/steering.md` file as permission to widen scope.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-loop-generic-effectful-composition/implementation_architecture.md`
- additional coherence reference reviewed because this slice reuses its write-root
  policy instead of redefining it:
  - `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/reusable-workflow-boundary-write-root-policy/implementation_architecture.md`

### Decisions Reused

- Reuse the existing generated-input provenance surface:
  `WorkflowBoundaryProjection.generated_internal_inputs` with reason
  `managed_write_root`.
- Reuse the current deterministic call-site allocator in
  `_managed_write_root_bindings(...)` for reusable/private workflow calls.
- Reuse the current explicit `command-result` lowering family and certified
  command-boundary checks; no wrapper script or inline shell bridge is added.
- Reuse the normative runtime command-bundle contract already documented in
  `specs/dsl.md` and `specs/io.md`.
- Reuse the rule that debug/lowered projections may expose internal compiler
  values so long as provenance marks them as generated and public API helpers do
  not require users to bind them.

### New Decisions In This Slice

- Public compiled-workflow input surfaces must exclude managed `__write_root__`
  bundle roots even if the lowered mapping still carries them for shared
  validation compatibility.
- Runtime execution needs two input views: public/user-bindable inputs and
  merged runtime inputs that include compiler-managed write roots.
- Entry-workflow managed write-root values are runtime allocated and
  resume-stable; user-supplied overrides for those internal names are rejected.
- Imported workflow signature reconstruction stops inferring public surface by
  prefix filtering raw inputs and instead consumes provenance-aware public input
  views.

### Conflicts Or Revisions

The current checkout and several tests implicitly treat lowered
`authored_mapping["inputs"]` as the public workflow boundary for compiled `.orc`
workflows. This slice revises that assumption narrowly:

- raw lowered mappings remain valid debug/shared-validation artifacts;
- public workflow boundary helpers, signature reconstruction, and entry-runtime
  input requirements must instead use provenance-aware public input views;
- reusable/private call-site managed bindings remain unchanged semantically and
  are still internal compiler-generated transport, not public user API.

No shared concepts are redefined. Core Workflow AST, Semantic IR, TypeCatalog,
SourceMap, pointer authority, variant proof, and runtime command execution
ownership remain with their existing owners.

## Ownership Boundaries

This slice owns:

- `command-result` managed write-root classification in
  `orchestrator/workflow_lisp/lowering.py`;
- provenance-aware compiled-workflow input views in
  `orchestrator/workflow/loaded_bundle.py`;
- imported-bundle signature reconstruction alignment in
  `orchestrator/workflow_lisp/workflows.py`;
- top-level runtime managed-input binding and override rejection in
  `orchestrator/workflow/executor.py`;
- reusable call-runtime helper alignment in `orchestrator/workflow/calls.py`
  if helper signatures change;
- focused regression coverage for compiled workflow surfaces, key migrations,
  and runtime entry execution.

This slice intentionally does not own:

- changing the command-step environment contract in `specs/io.md`;
- redesigning provider-result, review-loop, or `resume-or-start` lowering;
- new adapter definitions, external scripts, or runtime-native effects;
- shared YAML authoring behavior outside the compiled Workflow Lisp path, other
  than generic helper reuse where unavoidable;
- promotion policy, parity report schemas, or deprecation mechanics.

## Current Checkout Facts

The current checkout already contains the main substrate this slice should
reuse:

- `_lower_command_result(...)` derives a structured bundle contract, points its
  `path` at `${inputs.__write_root__...}`, and returns the generated name in
  `_TerminalResult.hidden_inputs`.
- `lower_workflow_definitions(...)` already records those names as
  `generated_internal_inputs` with reason `managed_write_root`, but it also
  appends them to `authored_mapping["inputs"]`.
- `workflow_managed_write_root_inputs(...)` already has a provenance surface,
  but still falls back to raw `__write_root__` prefix scanning.
- imported workflow signature reconstruction in `workflows.py` still hides
  managed names by prefix filtering rather than by consuming a public/internal
  input split.
- key migration tests currently prove leakage directly:
  `tests/test_workflow_lisp_key_migrations.py` inspects hidden input names in
  compiled mappings and manually binds them during runtime execution.
- `specs/dsl.md` and `specs/io.md` already define
  `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` and bundle-file authority for command steps,
  so the remaining work is implementation alignment rather than a new spec gap.

This makes the slice feasible without a new runtime primitive: provenance,
managed-input metadata, and deterministic binding helpers already exist. The
missing piece is using them as the public/runtime ownership boundary.

## Proposed Architecture

### 1. Keep `command-result` Lowering Explicit, But Mark Its Bundle Root Internal

`command-result` remains a direct lowering to a workflow command step with
`output_bundle` or another structured result contract derived from the declared
return type. This slice does not replace that with stdout parsing, prompt-side
instructions, or a wrapper adapter.

The change is classification:

- the generated `__write_root__...__result_bundle` name remains the lowering
  seam used inside the lowered step contract;
- that name is authoritative as an internal generated input only through
  `generated_internal_inputs` / provenance metadata, not as public workflow API;
- the same rule applies to compiler-generated validator/projection bundle roots
  inside the `command-result` lowering family when such helper steps already
  exist for the selected contract path.

If shared validation still requires the raw lowered mapping to declare the
generated name under `inputs`, that is acceptable in this slice, but only as
an internal lowering representation. Public bundle helpers must no longer infer
user-bindable workflow inputs from that raw representation.

### 2. Introduce Explicit Public And Runtime Input Views

Compiled Workflow Lisp bundles need two distinct views:

1. `public inputs`
   - authored entrypoint/workflow-call parameters exposed to users and to
     imported-workflow signature reconstruction;
   - excludes every provenance-tagged managed write-root input.

2. `runtime inputs`
   - the public inputs plus compiler-managed generated inputs needed for
     execution;
   - used by runtime validation, command execution, and compiler-generated
     internal call bindings.

Implementation direction:

- keep `workflow_managed_write_root_inputs(...)` provenance-first and retain
  raw-prefix fallback only for older bundles that lack provenance;
- add one helper for public input contracts and one helper for merged runtime
  input contracts, or equivalent clearly named surfaces with the same split;
- stop using raw `workflow_input_contracts(...)` as a proxy for both public API
  and runtime execution when the bundle comes from Workflow Lisp lowering.

This is the core public-API correction for the selected gap.

### 3. Make Imported Signature Reconstruction Consume The Public View

Imported compiled workflows are part of the same authoring boundary problem.

`orchestrator/workflow_lisp/workflows.py` currently reconstructs imported
signatures by reading the full input map and then skipping names that start
with `__write_root__`. That is a compatibility workaround, not the intended
boundary contract.

This slice replaces that logic with the provenance-aware public input view:

- imported signatures reconstruct parameters only from public boundary inputs;
- managed write roots remain available separately through
  `workflow_managed_write_root_inputs(...)` for compiler-generated call binding;
- imported signature reconstruction no longer depends on naming conventions to
  decide which inputs are semantic.

This keeps reusable call typing coherent with the new entry-workflow surface.

### 4. Runtime Owns Entry-Workflow Managed Write-Root Binding

Top-level execution must stop requiring the caller to provide managed
`command-result` bundle roots manually.

Runtime behavior for entry workflows:

- before required-input validation, inspect provenance-managed write-root
  inputs for the selected loaded bundle;
- if the user supplied any of those names directly, reject the run as an
  override of a runtime-owned internal input;
- otherwise allocate deterministic workspace-relative relpaths for them under a
  run-scoped generated namespace;
- merge those values into the runtime input view before step execution and
  preserve them for resume on the same run id.

The concrete allocator must be deterministic and resume-stable. A valid shape
is:

```text
.orchestrate/workflow_lisp/entry/<run_id>/<workflow_name>/<managed_input>.json
```

using the same normalization rules already required for workflow-generated
paths. The exact helper name is an implementation detail, but the path must be:

- workspace-relative;
- collision-safe across runs;
- reproducible for resume of the same run;
- hidden from public entrypoint input requirements.

Once that runtime-owned relpath is present, existing command-step execution
continues to resolve `output_bundle.path` and inject
`ORCHESTRATOR_OUTPUT_BUNDLE_PATH` exactly as the specs already require.

### 5. Preserve Existing Reusable/Private Call Binding Semantics

This slice does not redesign compiler-generated workflow-call transport.

The current caller-owned managed binding path remains valid:

- lowered/private/imported callees declare managed write-root requirements
  through provenance/generated-internal metadata;
- caller-side lowering binds those names through deterministic internal
  `call.with` values;
- runtime call validation uses the runtime input view for the callee, not the
  public user-facing boundary view.

That means generated `call.with` entries containing `__write_root__...` names
may still appear in lowered debug output. They are internal compiler wiring,
not public authoring API, and this slice keeps them that way.

### 6. Preserve Debug Visibility, Source Maps, And Command-Boundary Auditing

The gap is public exposure, not traceability.

This slice keeps:

- `generated_internal_inputs` in boundary-projection artifacts;
- source-map entries for generated managed inputs and generated bundle paths;
- command-boundary inventory in source maps/build artifacts;
- raw lowered step contracts that still point to internal generated bundle
  paths when debug output is requested.

What changes is the public interpretation:

- debug YAML / lowered mappings may still show the internal path reference;
- build/runtime helpers that report public entrypoint inputs must not surface it
  as user work;
- tests should assert provenance-tagged internal ownership rather than raw
  public leakage.

### 7. Test Surface

The acceptance surface for this slice is narrow and should stay narrow:

- lowering/build tests prove `command-result` still emits a structured command
  boundary and still records `generated_internal_inputs`;
- public-surface tests prove compiled entry workflows no longer expose managed
  `__write_root__...` names through public input helpers;
- runtime tests prove entry execution succeeds without manual hidden-input
  binding and rejects user override attempts;
- imported workflow signature tests prove parameter reconstruction still works
  while ignoring internal managed inputs without prefix-based public inference;
- key migration tests prove at least one real `.orc` candidate no longer needs
  manual bundle-path input injection.

## Acceptance Conditions

- `command-result` bundle paths remain explicit structured result contracts and
  continue using the runtime command-bundle authority surface.
- Managed `__write_root__...__result_bundle` names remain provenance-tagged
  internal generated inputs with reason `managed_write_root`.
- Public compiled-workflow input surfaces exclude those managed names.
- Imported workflow signature reconstruction no longer relies on
  `__write_root__` prefix filtering to define the public boundary.
- Entry-workflow runtime execution auto-allocates deterministic managed bundle
  roots and no longer requires user-supplied hidden inputs.
- User attempts to override runtime-owned managed inputs at the entry boundary
  fail explicitly.
- Existing reusable/private workflow call-site managed write-root transport
  remains deterministic and continues to work.
- No uncertified wrapper command, inline Python/shell glue, pointer-as-state
  path, or stdout-as-authority shortcut is introduced.
