# Workflow Core AST Lowering And Structured Results Implementation Architecture

## Scope

This design gap covers only the bounded Stage 3 lowering slice required by the
Workflow Lisp frontend MVP:

- elaborate `defworkflow` forms into a dedicated workflow-definition layer;
- register same-file workflow signatures before body checking so `call`
  supports forward references within one `.orc` file;
- extend the Stage 2 expression/typechecking layer for `call`,
  `provider-result`, and `command-result`;
- derive deterministic structured-result contracts for `provider-result` and
  `command-result`, using `output_bundle` for record results and
  `variant_output` for union results;
- lower typed workflow bodies into authored workflow mappings that reuse the
  existing elaboration and lowering seam used by the validator and runtime
  pipeline;
- preserve source-origin diagnostics for generated workflows, steps, hidden
  write-root inputs, prompt assets, and flattened workflow-boundary contract
  fields.

Out of scope for this tranche:

- `defproc`, `defmacro`, imports/modules, higher-order workflow refs, or any
  broader procedural/module system work;
- standard-library phase/resource/drain forms such as `with-phase`,
  `phase-target`, `produce-one-of`, `review-revise-loop`,
  `resume-or-start`, `resource-transition`, `finalize-selected-item`, or
  `backlog-drain`;
- runtime loader/CLI integration for `.orc`, new runtime execution semantics,
  or real NeurIPS phase translation;
- union workflow-boundary exports, optional workflow outputs, or any new call
  surface beyond the existing imported-workflow mechanism;
- transport of `Provider` or `Prompt` values across workflow boundaries;
- legacy adapters, report parsing, adapter registries, pointer-materialization
  policy changes, or runtime-native effects;
- redesign of shared `SourceMap`, Core Workflow AST, Semantic Workflow IR,
  TypeCatalog, pointer authority, or runtime proof semantics.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `6. Lowering Contract`
  - `7. Provider And Command Results`
  - `9. Source Spans And Diagnostics`
  - `10. Validation`
  - `14. Implementation Stages`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `14. Workflow Calls`
  - `22. Provider Result`
  - `23. Command Result`
  - `44. Typed Frontend AST`
  - `50. defworkflow Lowering`
  - `52. call Lowering`
  - `54. provider-result Lowering`
  - `59. Validation Sequence`
  - `60. Type Validation`
  - `61. Effect Validation`
  - `74. Source Map Requirements`
- `docs/design/workflow_language_design_principles.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/workflow_drafting_guide.md`
- `docs/steering.md`
- `specs/dsl.md`
- `specs/security.md`
- `specs/acceptance/index.md`

This slice must preserve the frontend guardrails already established by the
earlier implementation architectures:

- keep `orchestrator/workflow_lisp/` isolated from `orchestrator/workflow/`;
- reuse Stage 1 definitions as the only top-level type authority;
- reuse Stage 2 lexical typing and variant-proof checking rather than
  introducing a parallel effectful checker;
- keep structured bundles authoritative and reports as views;
- hand off through the existing authored-workflow elaboration and lowering seam
  instead of generating YAML text or building a second validator.

`command-result` is the only direct command boundary in scope, so the command
adapter contract is authoritative here. The frontend must reject new hidden
semantic glue on this high-level surface, including:

- `python -c`
- `python -`
- `bash -c`
- `sh -c`
- heredoc-style shell wrappers
- single-string shell wrappers that imply hidden parsing

Stage 3 recognizes only two allowed command-boundary classes:

- plain `external_tool` invocations whose semantics stay outside the workflow
  and whose only workflow-facing contract is a declared structured result; and
- `certified_adapter` invocations for commands that carry workflow semantics
  such as typed state normalization, outcome routing, resource movement,
  reusable-state decisions, or other adapter-contract behavior classes.

Generic typed script wrappers are not allowed. For workflow-semantic commands,
Stage 3 must require boundary metadata that preserves the minimum command
adapter facts it depends on:

- stable command identity/path;
- typed input and output contracts;
- visible effects and path-safety expectations;
- source-map behavior;
- fixture coverage and negative-test coverage.

If a `command-result` cannot be classified as a plain external tool, and no
certified-adapter metadata is available for it, the frontend must reject it
instead of treating an arbitrary script as a valid typed command boundary.

The reusable-call write-root contract is also authoritative in this slice:

- any lowered workflow that may be used through `call` must surface every
  DSL-managed write root as a typed workflow `input` with `type: relpath`;
- same-file call lowering must bind distinct relpath values for those managed
  inputs at each call site;
- Stage 3 may not rely on hard-coded `output_bundle.path`,
  `variant_output.path`, `expected_outputs.path`, or similar managed write
  roots inside imported same-file callees.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`

### Decisions Reused

- Keep the frontend in `orchestrator/workflow_lisp/` rather than mixing Lisp
  compilation into `orchestrator/workflow/`.
- Reuse `SourcePosition`, `SourceSpan`, `SyntaxNode`,
  `WorkflowLispModule`, and `LispFrontendDiagnostic` from the Stage 1 slice.
- Reuse `FrontendTypeEnvironment`, `ValueEnvironment`, `ProofScope`, and the
  Stage 2 type/proof checker as the authority for expression typing and
  variant availability.
- Keep pre-runtime frontend compilation as explicit APIs rather than extending
  `WorkflowLoader` in this tranche.

### New Decisions In This Slice

- Add a dedicated workflow-definition/signature layer so same-file workflows
  can typecheck and lower before any module/import system exists.
- Add a lowering bridge that emits authored-shape workflow mappings and routes
  them through the existing `elaborate_surface_workflow(...)` ->
  `lower_surface_workflow(...)` path, without YAML text as an intermediate.
- Keep workflow-boundary lowering on the subset the current loader and call
  surfaces already support:
  - workflow parameters may lower only through existing scalar/relpath boundary
    contracts and records composed of those fields;
  - workflow returns are record-only in Stage 3;
  - union results remain supported inside `provider-result` and
    `command-result`, but they do not cross the workflow boundary yet.
- Treat `Json` as a frontend-only non-boundary primitive in Stage 3:
  - it may remain available to earlier/frontend-local typing work;
  - it may not appear in workflow parameters, workflow return records, or any
    generated `output_bundle` or `variant_output` field contract;
  - any attempted Stage 3 lowering of `Json` emits a dedicated frontend
    diagnostic instead of coercing it to `string` or inventing new shared DSL
    behavior.
- Treat `Provider` and `Prompt` as compiler-known extern references rather
  than ordinary workflow-boundary values. Stage 3 lowers those externs directly
  into the existing provider-step fields (`provider` and `asset_file`) instead
  of flattening them into workflow `inputs`.
- Lower same-file `call` sites through compiler-generated aliases and
  out-of-band `imported_bundles`, not through authored `imports` path strings
  or generated workflow files.
- Add compiler-generated hidden relpath workflow inputs for every managed
  structured-result write root so same-file callees remain legal reusable
  workflows under the current `call` contract.
- Lower workflow returns only through existing exportable surfaces:
  direct step artifacts or structured statement outputs. Stage 3 does not add
  a new runtime notion of “final typed workflow value.”
- Add a lowering-origin map that remaps shared-validation errors on generated
  workflow surfaces back to authored `.orc` spans.

### Conflicts Or Revisions

No prior slice requires reversal. Stage 2 explicitly deferred effectful forms
and lowering; this slice layers workflow signatures, structured-result
contracts, compiler-known provider/prompt externs, managed write-root inputs,
workflow-output projection rules, and shared-surface lowering on top of the
existing expression and proof model.

The repo does not yet expose a separately documented runtime-integrated Core
Workflow AST package for the frontend. Until that internal seam is formalized,
this slice must target the existing authored-workflow validation seam:
frontend lowering produces in-memory workflow mappings shaped for
`elaborate_surface_workflow(...)`, then reuses
`orchestrator/workflow/surface_ast.py` only as the post-elaboration artifact.
That is a temporary bridge choice, not a change to the frontend’s design
target.

## Ownership Boundaries

This slice owns:

- `defworkflow` elaboration and same-file signature registration;
- effectful frontend expression nodes and typing rules for `call`,
  `provider-result`, and `command-result`;
- deterministic derivation of structured result contracts from record and
  union types for provider and command steps;
- compile-time classification of `command-result` boundaries as plain external
  tools or certified adapters, without permitting generic semantic script
  wrappers;
- compiler-generated hidden relpath workflow inputs for managed structured
  write roots;
- deterministic naming for generated step ids, local call aliases, and
  call-scoped structured-result paths;
- a compile-time extern environment for provider and prompt references;
- lowering from typed frontend workflows into authored workflow mappings plus a
  local validation bridge that reuses the existing loader/elaboration path;
- in-memory same-file imported bundles for local `call` lowering;
- a frontend-local lowering-origin map used only for source remapping;
- focused tests for workflow signatures, structured-result lowering, provider
  or prompt extern lowering, export projection, and shared-validation remapping.

This slice intentionally does not own:

- Stage 1 parsing, syntax, definition elaboration, or base diagnostic records;
- Stage 2 variant-proof semantics beyond reusing its checked typed forms;
- shared workflow execution semantics, prompt-contract injection, path-safety
  enforcement, pointer-authority checks, state layout, or resume behavior;
- adapter registries, legacy-adapter fixtures, report parsing, or
  runtime-native effect promotion;
- a workflow-boundary representation for union returns or boundary transport
  for provider/prompt values;
- the future shared `SourceMap`, Core Workflow AST, Semantic Workflow IR, or
  executable IR contracts.

## Proposed Package Boundary

Extend the existing package with one bounded lowering layer:

```text
orchestrator/workflow_lisp/
  __init__.py
  compiler.py            # Stage 1-3 pipeline orchestration
  contracts.py           # frontend type -> shared contract lowering
  expressions.py         # effectful expression elaboration
  lowering.py            # new typed workflow -> shared surface lowering
  workflows.py           # defworkflow AST + signature registration
```

Responsibilities:

- `workflows.py`
  - elaborate `defworkflow` forms from syntax objects;
  - define workflow-definition, signature, and extern-reference dataclasses;
  - build a same-file workflow catalog before body checking.
- `expressions.py`
  - keep Stage 2 pure forms intact;
  - add `CallExpr`, `ProviderResultExpr`, and `CommandResultExpr`;
  - elaborate `:inputs (...)` and `:argv (...)` subforms without inventing a
    broader list-literal surface.
- `contracts.py`
  - lower record and union frontend types into shared contract definitions for
    structured provider or command results;
  - lower only loader-supported workflow-boundary contracts;
  - flatten temporary workflow-boundary fields needed by the current shared
    handoff bridge.
- `lowering.py`
  - lower typed workflows to authored workflow mappings compatible with
    `elaborate_surface_workflow(...)`;
  - assign deterministic step identifiers, hidden write-root input names,
    synthetic local call aliases, and source-relative prompt assets;
  - derive exportable workflow-output refs from the terminal typed body;
  - record origin metadata for generated workflow surfaces and lowered mapping
    fields.
- `compiler.py`
  - run the Stage 1 -> Stage 3 pipeline;
  - accept compiler-known provider/prompt extern bindings for the module;
  - accept compiler-known command boundary bindings for `command-result`;
  - optionally invoke shared validation by elaborating lowered mappings through
  the existing validation backend;
  - remap shared-validation failures through the lowering-origin map.

Do not add a loader entrypoint, YAML renderer, or separate frontend execution
engine in this tranche.

## Data Model

### Workflow Definition Layer

Introduce a bounded workflow-definition layer:

- `WorkflowDef(name, params, return_type_name, body, span, form_path)`
- `WorkflowParam(name, type_name, span, form_path)`
- `WorkflowSignature(name, params, return_type_ref, span, form_path)`
- `TypedWorkflowDef(definition, signature, typed_body)`
- `WorkflowCatalog(signatures_by_name, definitions_by_name)`

Rules:

- workflow names are file-local in the MVP;
- signature registration happens before any workflow body is typechecked;
- forward references are allowed within one file once the catalog exists;
- workflow return types must resolve to records in Stage 3;
- duplicate workflow names and duplicate parameter names are compile-time
  errors;
- workflow parameters may use only boundary-lowerable types:
  scalar/path values already supported by the shared surface, or records
  composed of those fields;
- `Json` is not a boundary-lowerable type in Stage 3, including inside any
  record reachable from workflow parameters or return records;
- `Provider` and `Prompt` are forbidden in workflow parameters, return records,
  and any record reachable from those workflow-boundary types.

### Compile-Time Provider And Prompt Externs

Stage 3 needs a concrete source of provider and prompt values that does not
pretend they are normal workflow inputs. Introduce a small compile-time extern
environment:

- `ExternEnvironment(bindings_by_name)`
- `ProviderExtern(name, provider_id, span=None)`
- `PromptExtern(name, asset_file, span=None)`

Rules:

- extern bindings are exact authored symbols such as `providers.execute` or
  `prompts.implementation.execute`;
- the Stage 2 exact-name resolution rule remains authoritative, so these
  dotted names resolve as single extern bindings rather than record traversal;
- externs are supplied by the compile API, not authored as workflow params;
- prompt externs must lower to workflow-source-relative prompt assets usable
  through `asset_file`;
- Stage 3 does not support computed prompt text, prompt transport through
  `call`, or prompt lowering through arbitrary `input_file` generation.

### Compile-Time Command Boundary Bindings

`command-result` needs an explicit boundary classification that is stronger
than "some argv list". Introduce a compile-time command-boundary environment:

- `CommandBoundaryEnvironment(bindings_by_name)`
- `ExternalToolBinding(name, stable_command, span=None)`
- `CertifiedAdapterBinding(name, stable_command, input_contract, output_type_name, effects, path_safety, source_map_behavior, fixture_ids, negative_fixture_ids, span=None)`
- `CommandBoundaryBinding = ExternalToolBinding | CertifiedAdapterBinding`

Rules:

- the authored `command-result` boundary name resolves through this
  environment;
- `ExternalToolBinding` is valid only when the invoked tool’s semantics remain
  outside workflow authoring and the workflow only depends on the tool's
  declared structured output;
- any command that carries workflow semantics covered by
  `workflow_command_adapter_contract.md` must resolve to a
  `CertifiedAdapterBinding`;
- Stage 3 does not need a runtime adapter registry, but it must reject
  semantic command boundaries that lack certified-adapter metadata;
- the lowered command argv must remain consistent with the binding’s stable
  command identity/path.

### Effectful Expression Nodes

Extend the Stage 2 expression layer with:

- `CallExpr(callee_name, bindings, span, form_path)`
- `ProviderResultExpr(provider, prompt, inputs, returns_type_name, span, form_path)`
- `CommandResultExpr(step_name, argv, returns_type_name, span, form_path)`

Typed forms must carry:

- resolved callee signatures for `call`;
- resolved record-or-union return types for all three forms;
- resolved provider/prompt extern bindings for `provider-result`;
- the authored span/form path for diagnostics;
- enough lowering metadata to derive a shared result contract later without
  re-parsing authored syntax.

These remain frontend AST nodes. They are not shared IR nodes and must not
skip the Stage 2 type/proof checker.

### Generated Lowering Metadata

Add frontend-local lowering records:

- `GeneratedManagedWriteInput(name, step_key, contract, span, form_path)`
- `GeneratedLocalCall(alias, callee_name, hidden_with_bindings, span, form_path)`
- `GeneratedStructuredResult(path_input_name, contract_kind, type_ref)`
- `WorkflowReturnPlan(exported_outputs, terminal_step_id=None)`

Rules:

- every lowered `provider-result` or `command-result` step gets one hidden
  relpath workflow input for its managed bundle path;
- the hidden input exists only on the lowered workflow boundary, not in the
  authored frontend signature;
- same-file `call` lowering auto-binds those hidden inputs in the generated
  `with:` map alongside authored arguments;
- hidden managed-write inputs are typed relpath contracts and are included in
  the imported workflow’s managed-write-root catalog seen by shared validation;
- `WorkflowReturnPlan` records how each return-record field becomes a legal
  `outputs[*].from` ref on the current DSL surface.

### Structured Result Contracts

Add frontend-local structured-result lowering artifacts:

- `GeneratedRecordBundle(path_input_name, fields, type_ref)`
- `GeneratedVariantBundle(path_input_name, discriminant, variants, type_ref)`

Derivation rules:

- record result type -> `output_bundle`
  - one hidden relpath workflow input that supplies the bundle path;
  - one contract field entry per record field;
  - `json_pointer` values rooted at `/<field_name>`.
- union result type -> `variant_output`
  - one hidden relpath workflow input that supplies the bundle path;
  - fixed discriminant field `variant` at `/variant`;
  - variant-specific field entries under the emitted variant definitions;
  - no report parsing, pointer reads, or prose-based selection.

Stage 3 contract restriction:

- `Json` fields do not lower into generated `output_bundle` or
  `variant_output` contracts;
- if a declared record or union result contains `Json` at any emitted field,
  the compiler emits a dedicated frontend diagnostic instead of weakening the
  field to `string` or inventing a new shared bundle-field type.

These artifacts exist only to construct the authored workflow mappings consumed
by the current elaboration bridge. Shared output validators remain
authoritative.

## Compilation And Lowering Pipeline

Stage 3 compilation extends the existing frontend pipeline:

1. `compile_stage1_module(path)`
   - produces the validated Stage 1 definition module.
2. `elaborate_workflow_definitions(module_syntax)`
   - extracts `defworkflow` forms into workflow-definition nodes.
3. `build_workflow_catalog(module, workflow_defs, type_env)`
   - registers same-file signatures and rejects duplicates, unsupported
     boundary types, or invalid return types.
4. `build_extern_environment(extern_bindings)`
   - validates compiler-supplied provider and prompt extern bindings.
5. `build_command_boundary_environment(command_bindings)`
   - validates compiler-supplied external-tool and certified-adapter bindings.
6. `typecheck_workflow_definitions(...)`
   - checks workflow parameters, workflow bodies, call bindings, and result
     forms using Stage 2 typing plus Stage 3 workflow-aware rules.
7. `lower_workflow_definitions(...)`
   - derives structured-result contracts, hidden write-root inputs,
     temporary workflow-boundary flattening, generated call aliases,
     provider-step fields, command-boundary-constrained command steps, prompt
     asset references, return-export plans, and authored workflow mappings.
8. `validate_lowered_workflows(...)`
   - topologically orders same-file workflows by local call dependency;
   - elaborates each lowered workflow mapping through
     `elaborate_surface_workflow(...)` with already-built imported bundles for
     its generated aliases;
   - runs `lower_surface_workflow(...)` and assembles real
     `LoadedWorkflowBundle` values for downstream callers;
   - remaps generated-surface failures through the lowering-origin map.

The Stage 3 compile result should carry:

- the Stage 1 definition module;
- the workflow catalog;
- the extern environment;
- the command boundary environment;
- typed workflow definitions;
- lowered authored workflow mappings;
- validated `LoadedWorkflowBundle` values when shared validation is enabled;
- the lowering-origin map or per-workflow origin records.

This remains a compile-time artifact. It does not imply `.orc` execution
through the normal loader or CLI.

## Typing And Lowering Rules

### Workflow Parameters And Returns

For each `defworkflow`:

- every parameter type resolves through `FrontendTypeEnvironment`;
- duplicate parameter names are rejected;
- the initial `ValueEnvironment` for body checking is seeded from the
  workflow parameters plus compiler-known extern bindings;
- the body type must exactly match the declared workflow return type;
- workflow return types must be records in Stage 3;
- workflow-boundary types must be lowerable to existing shared input/output
  contracts.

If a return type is a union or any parameter/return field requires a boundary
surface the current loader cannot represent, emit a dedicated Stage 3
diagnostic instead of inventing a new workflow-boundary mechanism.

`Json` is explicitly part of that rejection set in Stage 3, even though it
remains a frontend primitive type in the earlier slices.

### `call`

Rules:

- the callee must resolve through the same-file `WorkflowCatalog`;
- call bindings must match the callee signature exactly by keyword;
- every binding expression must typecheck against the declared parameter type;
- the typed result of `call` is the callee’s declared record return type;
- call bindings may not transport `Provider` or `Prompt` values because those
  are not valid workflow-boundary types in Stage 3.

Lowering contract:

- each same-file call lowers to the existing call-step surface with a
  compiler-generated alias;
- lowered authored workflow mappings omit `imports`; the validation bridge
  supplies same-file callees only through the out-of-band `imported_bundles`
  parameter;
- each call binding lowers to the callee’s flattened input names using the
  same temporary boundary flattening scheme used for workflow signatures;
- each generated call step also includes hidden `with:` bindings for the
  callee’s generated managed-write relpath inputs;
- the validation bridge must construct real imported `LoadedWorkflowBundle`
  values for these aliases before elaborating the caller;
- same-file forward references are allowed, but recursive or cyclic same-file
  call graphs are rejected in Stage 3 because the current imported-bundle
  runtime surface requires an already-loaded callee bundle.

### Generated Managed Write-Root Inputs

The Stage 3 bridge may not hard-code structured-result bundle paths inside a
workflow that can be imported through `call`.

Lowering rule:

- every `provider-result` or `command-result` step that emits
  `output_bundle` or `variant_output` gets one generated workflow input:
  `__write_root__<step-id>__result_bundle`;
- that input is a typed `relpath` contract on the lowered workflow surface;
- the lowered step’s `output_bundle.path` or `variant_output.path` references
  `${inputs.__write_root__<step-id>__result_bundle}`;
- same-file call lowering binds that hidden input to a distinct deterministic
  relpath under a compiler-owned workspace subtree, keyed by caller step id
  and callee step id;
- Stage 3 does not promise loop-safe multi-visit disambiguation because loop
  forms are outside this slice; later loop/resource slices must extend this
  strategy before using same-file local calls inside repeated execution.

This keeps same-file callees inside the current reusable-workflow subset
without weakening loader rules for imported workflows.

### `provider-result`

Rules:

- the provider expression must resolve to a `ProviderExtern`;
- the prompt expression must resolve to a `PromptExtern`;
- each `:inputs` expression reuses Stage 2 typing and proof rules;
- `:returns` must resolve to a `RecordTypeRef` or `UnionTypeRef`;
- the generated result contract is derived only from the declared return type.

Lowering requirements:

- lower `ProviderExtern.provider_id` into the shared provider-step `provider`
  field;
- lower `PromptExtern.asset_file` into the shared provider-step `asset_file`
  field using the `.orc` file as the workflow source root for resolution;
- record return -> provider step with `output_bundle`;
- union return -> provider step with `variant_output`;
- use the generated hidden relpath input for the managed bundle path instead
  of a hard-coded authored path;
- rely on shared prompt-contract injection at execution time;
- expose typed artifacts only after structured validation succeeds.

This keeps provider and prompt semantics on the runtime surfaces the repo
already owns, without inventing provider/prompt workflow inputs.

### `command-result`

Rules:

- the boundary name must resolve through `CommandBoundaryEnvironment`;
- `:returns` must resolve to a `RecordTypeRef` or `UnionTypeRef`;
- every `:argv` element must typecheck as a value that can be rendered as a
  deterministic command argument;
- `Json` may not appear in any emitted record/union field of the declared
  return type;
- the frontend must reject command shapes that hide workflow semantics in
  shell text.

Allowed boundary classes:

- `ExternalToolBinding`
  - valid only for deterministic tool invocations whose semantics remain
    outside workflow authoring;
  - the workflow may depend on the tool’s structured output, but not on hidden
    semantic behavior inside the tool text.
- `CertifiedAdapterBinding`
  - required for commands whose behavior decides workflow state, routing,
    artifact lineage, resource movement, resume reuse, or other semantic
    adapter-contract classes;
  - the binding must preserve stable command identity/path, typed input/output,
    visible effects, path-safety expectations, source-map behavior, and
    fixture/negative-test coverage.

Minimum argv validation in this tranche:

- reject `python -c` and `python -`;
- reject `bash -c` and `sh -c`;
- reject single-string shell wrappers and heredoc-equivalent launch shapes;
- require the lowered command identity to match the selected binding’s stable
  command path or argv head;
- allow stable executable or script launches such as
  `("python" "scripts/run_checks.py" ...)` or `("./bin/tool" ...)` only when
  the selected binding classifies them as plain external tools or certified
  adapters;
- reject unclassified generic script wrappers with
  `command_adapter_missing_contract` once the command carries workflow
  semantics.

Lowering requirements:

- record return -> command step with `output_bundle`;
- union return -> command step with `variant_output`;
- use the generated hidden relpath input for the managed bundle path instead
  of a hard-coded authored path;
- no prompt-contract injection;
- preserve boundary metadata in the origin map so generated command steps stay
  attributable to either an external-tool or certified-adapter boundary;
- shared output validation remains authoritative.

This is the narrowest Stage 3 interpretation consistent with
`workflow_command_adapter_contract.md`.

### Workflow Return And Export Lowering

Stage 3 must define how a typed record result becomes legal
`outputs[*].from` entries on the current workflow boundary.

Supported terminal lowering shapes:

- direct producer return:
  - terminal `call`, `provider-result`, or `command-result` returning a record;
  - each workflow output field lowers from
    `root.steps.<TerminalStep>.artifacts.<field>`.
- record projection return:
  - terminal `(record Type ...)` whose fields each lower to an existing
    exportable ref backed by a prior step artifact or statement output;
  - each workflow output field lowers directly from that ref.
- match return:
  - terminal `match` over a union where every arm produces the same record
    shape via direct producer return or record projection;
  - lower to a structured DSL `match` statement with explicit `outputs` for
    every return field;
  - each workflow output field lowers from
    `root.steps.<GeneratedMatchStep>.artifacts.return__<field>`.
- `let*` return:
  - lower bindings sequentially and apply the terminal rule above to the body.

Unsupported in Stage 3:

- returning union values across the workflow boundary;
- exporting fields that exist only as literals, pure computations, workflow
  inputs, or unmaterialized lexical values with no legal current-surface
  `from` ref;
- inventing a new runtime-owned return bundle or workflow outcome surface for
  frontend return transport.

Emit a dedicated Stage 3 diagnostic when a terminal typed value cannot be
projected onto existing step-artifact or statement-output refs.

## Shared Workflow Handoff

Stage 3 must reuse the current authored-workflow validation seam instead of
implying a new validator entrypoint. The repo’s existing flow is:

```text
authored mapping
  -> elaborate_surface_workflow(...)
  -> SurfaceWorkflow
  -> lower_surface_workflow(...)
  -> LoadedWorkflowBundle
```

There is no current shared validator API that accepts prebuilt
`SurfaceWorkflow` records as Stage 3 input. The frontend therefore lowers each
`defworkflow` to one authored workflow mapping, in memory, with:

- `version: "2.14"` on the generated workflow;
- no authored `imports` entries for same-file callees;
- typed `inputs` and record-only `outputs` derived from the frontend
  signature plus compiler-generated hidden relpath write-root inputs;
- generated provider or command steps using shared execution surfaces already
  supported by the runtime;
- provider-step `provider` and `asset_file` fields sourced from validated
  extern bindings;
- workflow outputs anchored only to legal existing `root.steps.*.artifacts.*`
  refs;
- provenance metadata sufficient to remap errors from generated workflow
  fields back to authored forms.

Validation bridge requirements:

- use a frontend-local validation backend that reuses `WorkflowLoader`
  validation behavior rather than duplicating call/output/path checks;
- call `elaborate_surface_workflow(...)` on the lowered mapping for each
  workflow with an `imported_bundles` mapping populated from already-validated
  same-file callees;
- rely on `imported_bundles`, not authored `imports`, to populate
  `SurfaceWorkflow.imports` metadata for local callees;
- immediately call `lower_surface_workflow(...)` after successful elaboration
  so the result is a real `LoadedWorkflowBundle`, matching the existing call
  validation and runtime surfaces;
- keep the whole bridge in-memory for Stage 3 tests and compile APIs; do not
  serialize YAML or add `.orc` loader integration in this tranche.

### Temporary Workflow-Boundary Flattening

The frontend must preserve structured signatures even if the current shared
handoff bridge still wants flat fields.

Implementation rule:

- keep structured parameter and return types authoritative in frontend
  artifacts;
- localize flattening to `contracts.py` and `lowering.py`;
- record every generated field in the origin map;
- reuse the same flattened field names in lowered call `with` bindings so
  caller/callee compatibility stays identical between frontend lowering and
  shared call validation.

Temporary flattening rules:

- record parameter field -> `<param>__<field>`
- scalar/path parameter -> `<param>`
- record return field -> `return__<field>`
- generated managed write input -> literal generated input name

No Stage 3 flattening rule exists for union workflow returns because the
current workflow-output and call surfaces cannot safely export
variant-conditional outputs. That work is deferred until the shared boundary
surface can represent it explicitly.

## Diagnostics

Reuse existing codes where the meaning already matches:

- `type_unknown`
- `type_mismatch`
- `workflow_signature_mismatch`
- `return_type_mismatch`
- `variant_ref_unproved`
- `variant_ref_wrong_variant`

Add Stage 3 frontend-local codes only where the prior slices are too coarse:

- `workflow_definition_duplicate`
- `workflow_param_duplicate`
- `workflow_boundary_type_invalid`
- `workflow_return_type_invalid`
- `workflow_call_unknown`
- `workflow_return_not_exportable`
- `provider_result_return_type_invalid`
- `provider_result_provider_invalid`
- `provider_result_prompt_invalid`
- `command_result_return_type_invalid`
- `command_result_argv_invalid`
- `command_adapter_missing_contract`
- `json_surface_unsupported`
- `inline_python_command_in_workflow`
- `inline_shell_command_in_workflow`
- `source_map_missing`

Diagnostic requirements:

- frontend-local typing errors point at authored spans;
- shared-validation failures on generated steps, hidden write-root inputs,
  prompt assets, or flattened contract fields remap through the
  lowering-origin map before surfacing;
- diagnostics preserve `form_path` so later tooling can build richer source
  navigation without rewriting this slice.

## Integration Strategy

This tranche remains compile-and-validate only.

Recommended API shape:

```python
compile_stage3_module(
    path: Path,
    *,
    provider_externs: Mapping[str, str] | None = None,
    prompt_externs: Mapping[str, str] | None = None,
    command_boundaries: Mapping[str, CommandBoundaryBinding] | None = None,
    validate_shared: bool = True,
) -> Stage3CompileResult
```

Behavior:

- compile Stage 1 definitions;
- elaborate and typecheck workflows;
- validate compiler-known provider and prompt extern bindings;
- validate compiler-known command boundary bindings;
- lower workflows into authored workflow mappings plus local call metadata;
- optionally run shared validation immediately through
  `elaborate_surface_workflow(...)` and `lower_surface_workflow(...)`;
- raise one typed compile error containing frontend and remapped shared
  diagnostics if anything fails.

Do not wire `.orc` into `WorkflowLoader`, `orchestrator run`, or `resume` in
this slice.

## Test Strategy

Add focused tests that prove the selected gap and no more.

Proposed test modules:

- `tests/test_workflow_lisp_workflows.py`
  - `defworkflow` elaboration and signature registration;
  - duplicate workflow or parameter rejection;
  - workflow-boundary rejection for union returns;
  - workflow-boundary rejection for `Json` params or return fields;
  - workflow-boundary rejection for `Provider` or `Prompt` params;
  - same-file `call` signature validation and cycle rejection;
  - hidden write-root input generation for structured-result callees.
- `tests/test_workflow_lisp_structured_results.py`
  - record return -> generated `output_bundle`;
  - union return -> generated `variant_output`;
  - `Json` rejection inside generated structured-result contracts;
  - provider extern and prompt extern enforcement;
  - `command-result` rejection of inline shell/python glue;
  - `command-result` rejection of semantic commands without certified-adapter
    metadata;
  - `command-result` acceptance for plain external tools and certified
    adapters with stable boundary metadata;
  - managed bundle paths lowered through hidden relpath inputs.
- `tests/test_workflow_lisp_lowering.py`
  - lowered authored workflow mapping shapes;
  - local-call lowering through out-of-band `imported_bundles`;
  - provider-result lowering to `provider` plus `asset_file`;
  - command-result lowering preserves external-tool vs certified-adapter origin
    metadata without changing the shared `command: string[]` surface;
  - workflow-output lowering from direct producer returns;
  - workflow-output lowering from `match` statement outputs;
  - validation bridge assembly into `LoadedWorkflowBundle`;
  - origin-map coverage for generated workflow surfaces;
  - remapping of shared-validation failures to authored spans.

Fixture guidance:

- keep `.orc` fixtures under `tests/fixtures/workflow_lisp/`;
- add only the minimal fixtures needed for workflow definitions,
  structured-result forms, provider/prompt extern lowering, return-export
  projection, and shared-validation remapping;
- assert codes, spans, generated contract shapes, lowered shared records, and
  exported `from` refs rather than prose snapshots.

## Implementation Sequence

1. Add or finalize `workflows.py` for bounded `defworkflow` elaboration and
   same-file signature registration.
2. Extend `expressions.py` and the Stage 2 typechecker for `call`,
   `provider-result`, and `command-result`, including explicit Stage 3 `Json`
   rejection on boundary/result surfaces.
3. Add compile-time command-boundary binding support for plain external tools
   and certified adapters.
4. Add or finalize `contracts.py` to derive loader-supported workflow-boundary
   contracts plus generated `output_bundle` and `variant_output` payloads.
5. Add `lowering.py` to construct authored workflow mappings, hidden managed
   write-root inputs, local call aliasing, provider/prompt extern lowering,
   return-export plans, and origin maps.
6. Extend `compiler.py` with a Stage 3 orchestration API, extern-binding
   validation, and optional shared validation via the existing
   elaboration/lowering seam.
7. Add focused workflow, structured-result, and lowering/remap tests.
8. Run the Stage 3 tests first, then the broader frontend regression suite.

## Acceptance Conditions

This slice is complete when:

- bounded `defworkflow` forms elaborate into a dedicated workflow-definition
  layer with registered same-file signatures;
- workflow boundaries reject unsupported types, especially union returns and
  any `Provider`, `Prompt`, or `Json` transport;
- `call`, `provider-result`, and `command-result` typecheck against Stage 1
  and Stage 2 authority, including exact signature matching and record/union
  return-type enforcement for provider/command structured results;
- record and union result types generate deterministic structured result
  contracts whose managed paths are supplied through generated hidden relpath
  workflow inputs rather than hard-coded write roots;
- generated `output_bundle` and `variant_output` contracts reject `Json`
  fields with a dedicated frontend diagnostic instead of inventing new shared
  DSL contract types;
- lowered provider steps derive `provider` and `asset_file` from validated
  compiler-known extern bindings;
- lowered `command-result` steps come only from validated plain external-tool
  bindings or certified-adapter bindings, never from unclassified generic
  script wrappers;
- lowered workflows hand off to shared validation through authored workflow
  mappings that reuse `elaborate_surface_workflow(...)` and
  `lower_surface_workflow(...)`;
- same-file `call` lowers through generated aliases plus out-of-band imported
  `LoadedWorkflowBundle` callees, without requiring authored `imports` paths;
- workflow returns lower only through existing exportable surfaces:
  step artifacts or structured statement outputs;
- shared-validation failures on generated steps, hidden write-root inputs,
  prompt assets, or flattened workflow-boundary fields remap to authored
  `.orc` spans;
- inline shell/python command glue is rejected at compile time.

## Verification Plan

Use the narrowest deterministic checks first:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py -q
python -m pytest tests/test_workflow_lisp_workflows.py -q
python -m pytest tests/test_workflow_lisp_structured_results.py -q
python -m pytest tests/test_workflow_lisp_lowering.py -q
python -m pytest tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py -q
python -m pytest tests/test_workflow_lisp_reader.py tests/test_workflow_lisp_definitions.py tests/test_workflow_lisp_diagnostics.py tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_variant_proofs.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py -q
```
