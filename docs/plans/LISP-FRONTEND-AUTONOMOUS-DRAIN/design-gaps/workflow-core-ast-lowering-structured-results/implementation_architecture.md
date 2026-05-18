# Workflow Core AST Lowering And Structured Results Implementation Architecture

## Scope

This design gap covers only the bounded Stage 3 lowering slice required by the
Workflow Lisp frontend MVP:

- elaborate and register typed `defworkflow` signatures;
- reuse the Stage 2 expression layer while extending it for `call`,
  `provider-result`, and `command-result`;
- typecheck workflow parameters, call bindings, effectful result forms, and
  workflow return values against Stage 1 and Stage 2 type authority;
- generate deterministic `output_bundle` and `variant_output` contracts from
  record and union return types;
- lower typed workflow bodies into the shared workflow handoff boundary used
  for validation, while preserving source-origin diagnostics for generated
  steps and contracts.

Out of scope for this tranche:

- `defproc`, `defmacro`, imports/modules, higher-order workflow refs, or
  standard-library phase procedures;
- `with-phase`, `phase-target`, `produce-one-of`, `review-revise-loop`,
  `resume-or-start`, `resource-transition`, `finalize-selected-item`, or
  `backlog-drain`;
- new runtime execution semantics, new loader/CLI `.orc` entrypoints, or real
  phase translation work;
- new runtime-native effects, command-adapter registries, legacy adapters, or
  report parsing;
- redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog,
  SourceMap, pointer authority, or runtime proof semantics.

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
- `docs/design/workflow_command_adapter_contract.md`
- `docs/steering.md`

This slice must preserve the frontend guardrails already established by the
earlier implementation architectures:

- keep the isolated `orchestrator/workflow_lisp/` package boundary;
- reuse Stage 1 definitions as the only top-level type authority;
- reuse Stage 2 typed expressions, lexical environments, and variant-proof
  rules rather than re-checking those concepts in a parallel system;
- keep structured bundles authoritative and reports as views;
- hand off to shared workflow validation rather than inventing a second
  validator or YAML text generator.

`command-result` must follow the command-adapter contract. In this high-level
frontend surface, inline semantic glue is an error, not migration debt to add
casually. The lowering layer must reject:

- `python -c`
- `python -`
- `bash -c`
- `sh -c`
- heredoc-style shell wrappers or equivalent single-string shell launchers

This slice may lower `command-result` only to explicit command steps whose
structured outputs are declared and validated. Certified-adapter metadata and
legacy-adapter handling remain outside this tranche.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`

### Decisions Reused

- Keep the frontend in `orchestrator/workflow_lisp/` rather than mixing Lisp
  compilation into `orchestrator/workflow/`.
- Reuse `SourcePosition`, `SourceSpan`, `SyntaxNode`,
  `WorkflowLispModule`, `LispFrontendDiagnostic`, and the Stage 1 reader and
  definition pipeline.
- Reuse `FrontendTypeEnvironment`, `ValueEnvironment`, `ProofScope`, and the
  Stage 2 expression checker as the authority for pure expressions and
  variant-specific field availability.
- Keep pre-runtime frontend compilation as explicit APIs rather than silently
  extending `WorkflowLoader`.

### New Decisions In This Slice

- Add a workflow-definition layer with explicit signature registration before
  body checking so `call` can resolve same-file workflows, including forward
  references.
- Extend the bounded expression surface with effectful nodes for `call`,
  `provider-result`, and `command-result`, but keep their semantics visible in
  typed lowering artifacts rather than hiding them in command text or
  generated YAML.
- Add a contract-derivation layer that converts frontend record and union
  types into deterministic shared output-contract surfaces.
- Add a lowering-origin map that records generated workflow names, step ids,
  contract fields, and bundle paths back to `.orc` spans so shared-validation
  errors can be remapped to authored source locations.

### Conflicts Or Revisions

No prior slice needs reversal. Stage 2 explicitly deferred effectful forms and
lowering; this slice extends that expression infrastructure rather than
replacing it.

The repo does not yet expose a separately documented shared Core Workflow AST
package for the Lisp frontend. Until that internal contract is finalized, this
slice uses the existing typed workflow handoff boundary in
`orchestrator/workflow/surface_ast.py` as the implementation bridge into
shared validation and lowering. The architecture still treats that bridge as a
handoff seam, not as permission to collapse the Lisp frontend into YAML text.

## Ownership Boundaries

This slice owns:

- `defworkflow` syntax elaboration and signature registration;
- effectful expression nodes and their typing rules for `call`,
  `provider-result`, and `command-result`;
- frontend-local derivation of structured result contracts from record and
  union types;
- deterministic generated bundle-path naming for structured result steps;
- lowering from typed frontend workflow bodies into the shared workflow
  handoff boundary;
- origin-map data needed to remap shared-validation failures back to `.orc`
  spans;
- focused tests for signature checking, structured-result lowering, and
  shared-validation handoff.

This slice intentionally does not own:

- Stage 1 parsing, syntax objects, definition elaboration, or base diagnostics;
- Stage 2 proof rules or the meaning of `match` beyond reusing its checked
  typed form during lowering;
- shared output-contract validation, prompt-contract injection, workflow-call
  execution, pointer-authority checks, or runtime resume/state behavior;
- runtime-native effects, command-adapter registries, legacy-adapter fixtures,
  or report-parsing compatibility layers;
- phase-library path derivation or the broader state-layout contract.

## Proposed Package Boundary

Extend the existing package with the minimum additional Stage 3 surface:

```text
orchestrator/workflow_lisp/
  __init__.py
  compiler.py            # add Stage 3 compilation entrypoints
  contracts.py           # new frontend type -> shared contract lowering
  expressions.py         # extend with call/provider-result/command-result nodes
  lowering.py            # new workflow lowering + origin-map bridge
  workflows.py           # new defworkflow AST + signature registration
```

Responsibilities:

- `workflows.py`
  - elaborate `defworkflow` forms from syntax objects;
  - define `WorkflowDef`, `WorkflowParam`, and `WorkflowSignature`;
  - build a same-file signature catalog before body checking.
- `expressions.py`
  - keep Stage 2 pure nodes intact;
  - add `CallExpr`, `ProviderResultExpr`, and `CommandResultExpr`;
  - elaborate their special subforms such as `:inputs (...)` and `:argv (...)`
    without introducing a general list-literal language feature.
- `contracts.py`
  - lower `PrimitiveTypeRef`, `PathTypeRef`, `RecordTypeRef`, and
    `UnionTypeRef` into shared contract dictionaries and step output-contract
    payloads;
  - derive bundle schemas for `output_bundle` and `variant_output`.
- `lowering.py`
  - lower typed workflow bodies into `SurfaceWorkflow`, `SurfaceStep`, and
    `SurfaceContract` handoff objects;
  - assign deterministic step ids, generated bundle paths, and runtime-safe
    presentation names;
  - record a frontend-local origin map for remapping shared-validation errors.
- `compiler.py`
  - expose a Stage 3 orchestration API such as `compile_stage3_module(...)`;
  - run the pipeline from Stage 1 module compile through Stage 3 lowering and
    optional shared validation.
- `__init__.py`
  - export the Stage 3 helpers without changing existing Stage 1 and Stage 2
    names.

Do not add a runtime loader, YAML renderer, or a separate frontend execution
engine in this tranche.

## Data Model

### Workflow Definitions And Signatures

Introduce a bounded workflow-definition layer:

- `WorkflowDef(name, params, return_type_name, body, span, form_path)`
- `WorkflowParam(name, type_name, span, form_path)`
- `WorkflowSignature(name, params, return_type_ref, span, form_path)`
- `WorkflowCatalog(signatures_by_name, definitions_by_name)`

Rules:

- workflow names are file-local in the MVP;
- signature registration happens before any workflow body is typechecked;
- forward calls within one file are allowed once the signature catalog exists;
- duplicate workflow names are rejected deterministically.

Stage 3 should require workflow return types to resolve to a record or union.
That keeps call boundaries and structured result lowering aligned with the MVP
proof point instead of inventing unrelated scalar-only workflow surfaces first.

### Effectful Expression Nodes

Extend the Stage 2 expression AST with:

- `CallExpr(callee_name, bindings, span, form_path)`
- `ProviderResultExpr(provider, prompt, inputs, returns_type_name, span, form_path)`
- `CommandResultExpr(step_name, argv, returns_type_name, span, form_path)`

Typed forms should annotate:

- resolved callee workflow signature for `call`;
- resolved return type ref for all three forms;
- generated structured-result contract metadata for provider/command forms;
- source-origin ids used later by lowering.

These are still frontend AST nodes. They are not shared workflow IR, and they
must not bypass the existing typed-expression and proof machinery for nested
subexpressions.

### Structured Result Contract Derivation

Add a frontend-local lowering artifact used only by Stage 3:

- `GeneratedRecordBundle(path, fields, type_ref)`
- `GeneratedVariantBundle(path, discriminant, variants, type_ref)`

Derivation rules:

- record result type -> `output_bundle`
  - bundle path is compiler-generated;
  - each record field becomes one `fields[*]` entry;
  - `json_pointer` is the canonical top-level field pointer such as
    `/<field_name>`.
- union result type -> `variant_output`
  - bundle path is compiler-generated;
  - discriminant uses a fixed field name and pointer, e.g. `variant` at
    `/variant`;
  - each variant field is emitted under that variant's field list;
  - shared fields remain empty in the MVP because Stage 1 and Stage 2 do not
    model shared union fields separately.

This artifact is a lowering helper only. The shared output-contract validators
remain authoritative.

### Lowering Origin Map

Do not claim ownership of the future shared `SourceMap`. Stage 3 only needs a
frontend-local bridge that can remap shared-validation failures:

- `workflow_name -> source span`
- `step_id -> originating form span`
- `generated bundle path -> originating form span`
- `workflow input/output contract name -> source span`

The map should store enough information to transform a shared validation error
about a generated step or field into a `LispFrontendDiagnostic` pinned to the
authored `.orc` form.

## Compilation And Lowering Pipeline

Stage 3 compilation is a strict extension of the existing frontend pipeline:

1. `compile_stage1_module(path)`
   - produces the typed definition module.
2. `elaborate_workflow_definitions(module_syntax)`
   - extracts `defworkflow` forms into `WorkflowDef` nodes.
3. `build_workflow_catalog(module, workflow_defs)`
   - registers signatures and rejects duplicates or unknown return types.
4. `typecheck_workflow_definitions(...)`
   - checks workflow parameters, body expressions, call bindings, and return
     values using Stage 2 helpers plus new effectful-form rules.
5. `lower_workflow_definitions(...)`
   - derives structured output contracts, generated bundle paths, and shared
     workflow handoff records.
6. `validate_lowered_workflows(...)`
   - passes the lowered handoff records into shared workflow validation;
   - remaps any shared-validation failures through the lowering origin map.

The output is a Stage 3 compile result containing:

- the Stage 1 definition module;
- the workflow catalog;
- typed workflow definitions;
- lowered shared workflow handoff objects;
- the lowering origin map.

This remains a compile-time artifact. It does not imply `.orc` execution
through normal CLI paths in this tranche.

## Typing And Validation Rules

### Workflow Parameters And Returns

For each `defworkflow`:

- parameter types must resolve through `FrontendTypeEnvironment`;
- duplicate parameter names are rejected;
- the initial `ValueEnvironment` for body checking is seeded from those
  parameters;
- the body type must exactly match the declared workflow return type.

If the return type is not a record or union, emit a deterministic Stage 3
diagnostic rather than attempting to invent an ad hoc output-contract surface.

### `call`

Rules:

- callee name must resolve through the same-file `WorkflowCatalog`;
- bindings must match the callee signature exactly by keyword;
- every required callee parameter must be provided unless defaults become part
  of the workflow-signature design later;
- each binding expression must typecheck against the callee parameter type;
- the typed result of the `call` expression is the callee return type ref.

This slice owns the compile-time signature compatibility checks. Runtime call
execution, write-root binding rules, and nested workflow scheduling remain
owned by shared workflow code.

### `provider-result`

Rules:

- provider expression must typecheck as `Provider`;
- prompt expression must typecheck as `Prompt`;
- `:returns` must resolve to `RecordTypeRef` or `UnionTypeRef`;
- nested `:inputs` expressions reuse Stage 2 typing and proof rules;
- the generated output contract is derived solely from the declared return
  type, not from prompt text or markdown reports.

Lowering requirements:

- record return type -> provider step with `output_bundle`;
- union return type -> provider step with `variant_output`;
- rely on shared prompt-contract injection to append the derived contract at
  execution time;
- typed artifacts become available only through the validated bundle surface.

### `command-result`

Rules:

- `:returns` must resolve to `RecordTypeRef` or `UnionTypeRef`;
- every `:argv` element must be a typed expression whose runtime value can be
  rendered as a deterministic command argument;
- the command boundary must be explicit and contract-shaped, not inline
  procedural glue.

Lowering requirements:

- record return type -> command step with `output_bundle`;
- union return type -> command step with `variant_output`;
- no prompt-contract injection;
- shared output validation remains authoritative;
- the frontend must reject inline shell/python glue forms with hard diagnostics
  because `.orc` is a new high-level authoring surface.

Minimum argv validation for this tranche:

- reject `python -c` and `python -`;
- reject `bash -c` and `sh -c`;
- reject one-string shell wrappers that imply hidden parsing or heredocs;
- allow stable script or executable invocations such as
  `("python" "scripts/run_checks.py" ...)` or `("./bin/tool" ...)`.

This is the narrowest Stage 3 interpretation consistent with
`workflow_command_adapter_contract.md`.

## Structured Contract Generation

### Workflow Boundary Contracts

The frontend must preserve structured workflow signatures even if the current
shared handoff boundary needs a flatter representation.

Implementation rule:

- keep structured parameter and return types in frontend artifacts;
- localize any flattening needed by the current shared handoff bridge inside
  `contracts.py` and `lowering.py`;
- record the flattening map in the lowering origin map so diagnostics and
  later migration to a more explicit Core AST do not lose the authored shape.

The bridge layer may therefore flatten record leaves into generated workflow
input/output names, but that naming scheme must be:

- deterministic;
- reversible through the origin map;
- internal to the handoff adapter rather than a new source-language rule.

### Generated Bundle Paths

Because phase-library context and full state-layout rules are out of scope,
Stage 3 needs a compiler-owned temporary convention for structured result
bundles. Use one deterministic scheme for both provider and command results,
for example:

```text
.orchestrate/workflow_lisp/<workflow-name>/<step-id>/result.json
```

Requirements:

- path is workspace-relative and passes existing path-safety rules;
- path depends only on stable authored identity, not timestamps or execution
  order;
- path generation is owned by the lowering layer, not authored by workflow
  source;
- later state-layout work can replace the path strategy without changing
  frontend typing rules.

## Shared Workflow Handoff

Stage 3 should hand off through the existing shared typed workflow records:

- `SurfaceWorkflow`
- `SurfaceStep`
- `SurfaceContract`
- `WorkflowProvenance`

The lowering bridge should produce one lowered workflow per `defworkflow`,
with:

- `version: "2.14"` on generated workflows;
- generated step ids and presentation names derived from authored form paths;
- typed workflow `inputs` and `outputs` derived from parameter and return
  contracts;
- command/provider steps using only shared execution surfaces already supported
  by the runtime.

The bridge must not generate YAML text or rely on YAML parsing for validation.
It should construct the shared records directly and then call the existing
validation path that consumes those typed records.

## Diagnostics

Reuse existing codes whenever the meaning matches:

- `type_unknown`
- `type_mismatch`
- `workflow_signature_mismatch`
- `return_type_mismatch`
- `variant_ref_unproved`
- `variant_ref_wrong_variant`

Add Stage 3 frontend-local codes only where the earlier slices are too coarse:

- `workflow_definition_duplicate`
- `workflow_param_duplicate`
- `workflow_return_type_invalid`
- `workflow_call_unknown`
- `provider_result_return_type_invalid`
- `command_result_return_type_invalid`
- `command_result_argv_invalid`
- `inline_python_command_in_workflow`
- `inline_shell_command_in_workflow`
- `source_map_missing`

Diagnostic requirements:

- frontend-local typing errors point at the authored form span;
- shared-validation failures about generated steps or contract fields are
  remapped through the lowering origin map before surfacing;
- diagnostic payloads preserve `form_path` so later tooling can build richer
  explain/hover flows without rewriting this slice.

## Integration Strategy

This slice remains compile-and-validate only.

Recommended API shape:

```python
compile_stage3_module(path: Path, *, validate_shared: bool = True) -> Stage3CompileResult
```

Behavior:

- compile Stage 1 definitions;
- elaborate and typecheck workflows;
- lower them into shared handoff records;
- optionally run shared validation immediately;
- raise one typed compile error containing frontend and remapped shared
  diagnostics if anything fails.

Do not wire `.orc` into `WorkflowLoader`, `orchestrator run`, or `resume` in
this tranche. The goal is to prove lowering, structured contracts, and shared
validation compatibility before runtime integration or real workflow migration.

## Test Strategy

Add focused tests that prove the selected gap and no more.

Proposed test modules:

- `tests/test_workflow_lisp_workflows.py`
  - `defworkflow` elaboration and signature registration;
  - duplicate workflow/parameter rejection;
  - workflow body return-type checking;
  - same-file call signature validation.
- `tests/test_workflow_lisp_structured_results.py`
  - record return type -> generated `output_bundle`;
  - union return type -> generated `variant_output`;
  - generated bundle path determinism;
  - provider/prompt type enforcement.
- `tests/test_workflow_lisp_lowering.py`
  - direct lowering to shared handoff records;
  - origin-map coverage for generated steps and contracts;
  - remapping of shared-validation failures back to `.orc` spans;
  - `command-result` rejection of inline shell/python glue.

Fixture guidance:

- keep `.orc` fixtures under `tests/fixtures/workflow_lisp/`;
- add only the minimal fixtures needed for workflow definitions and structured
  result forms;
- assert codes, spans, lowered contract shapes, and generated handoff records
  rather than prose snapshots.

## Implementation Sequence

1. Add `workflows.py` and elaborate bounded `defworkflow` definitions.
2. Extend `expressions.py` for `call`, `provider-result`, and
   `command-result`.
3. Extend typing so workflow parameters seed the lexical environment and
   effectful forms resolve signatures and structured result types.
4. Add `contracts.py` to derive workflow boundary contracts plus generated
   `output_bundle` and `variant_output` payloads.
5. Add `lowering.py` to construct shared handoff records and origin maps.
6. Add `compile_stage3_module(...)` in `compiler.py`.
7. Add focused workflow/lowering/structured-result tests.
8. Run the new suites first, then the Stage 1 and Stage 2 frontend regression
   suites.

## Acceptance Conditions

This slice is complete when:

- bounded `defworkflow` forms elaborate into a dedicated workflow-definition
  layer with registered same-file signatures;
- `call`, `provider-result`, and `command-result` typecheck against Stage 1
  and Stage 2 authority rather than ad hoc dictionaries or prompt text;
- record and union result types generate deterministic `output_bundle` or
  `variant_output` contracts with compiler-owned bundle paths;
- lowered workflows hand off directly to shared validation through typed
  workflow records rather than YAML text;
- shared-validation failures can be traced back to authored `.orc` spans for
  generated steps and contract fields;
- `command-result` rejects inline semantic glue in accordance with the
  command-adapter contract.

## Verification Expectations

Implementation should verify this slice with narrow deterministic selectors
first:

- collect-only on the new workflow/lowering test modules;
- focused workflow-signature and structured-result suites;
- focused lowering/origin-map suite;
- final frontend regression run spanning the Stage 1, Stage 2, and new Stage 3
  tests.

## Risks And Mitigations

- Risk: Stage 3 accidentally collapses the frontend into YAML-shaped strings.
  Mitigation: lower directly to shared typed workflow records and keep YAML out
  of the authoritative pipeline.

- Risk: call lowering depends on runtime workflow-boundary details that are not
  yet generalized for structured records and unions.
  Mitigation: keep structured signatures authoritative in frontend artifacts
  and localize any temporary flattening to the handoff bridge plus origin map.

- Risk: generated bundle paths become accidental semantic state layout.
  Mitigation: keep path generation compiler-owned, deterministic, and explicitly
  replaceable by later state-layout work.

- Risk: `command-result` silently reintroduces hidden workflow semantics
  through shell wrappers.
  Mitigation: enforce hard compile-time rejection for inline shell/python glue
  and rely on explicit structured output contracts.

- Risk: shared-validation errors lose authored source locations after lowering.
  Mitigation: require origin-map coverage for every generated workflow, step,
  contract field, and bundle path before calling shared validation.
