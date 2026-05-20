# Defproc Procedural Substrate Implementation Architecture

## Scope

This design gap covers only the bounded `defproc` procedural substrate needed
to make reusable effectful procedures implementable on top of the current
Workflow Lisp frontend:

- add same-file `defproc` definition parsing/elaboration and forward-reference
  binding;
- represent explicit procedure effect signatures in a typed frontend-local
  form;
- support procedure invocation inside typed expressions and existing workflow
  bodies;
- compute transitive effect summaries for procedures and workflows without
  bypassing the current typed/lowered pipeline;
- choose deterministic `inline`, `private-workflow`, or `auto` lowering for
  each procedure;
- preserve source provenance from procedure definitions and call sites through
  generated lowering artifacts and shared-validation diagnostics;
- lower generated private procedures through the same authored-mapping ->
  shared-validation seam already used by ordinary Stage 3/4 workflows.

Out of scope for this tranche:

- generic standard-library procedures such as `run-provider-phase`,
  `review-revise-loop`, `resume-or-start`, `resource-transition`,
  `finalize-selected-item`, or `backlog-drain`;
- new runtime-native effects, resource-transition backends, queue/ledger
  semantics, or drain orchestration work;
- `defun`, modules/imports/exports, higher-order workflow refs, or dynamic
  workflow loading;
- CLI/loader support for `.orc` as a first-class runtime entrypoint;
- redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog,
  SourceMap, pointer authority, or variant proof;
- any replacement of the product design in
  `docs/design/workflow_lisp_frontend_specification.md`.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_frontend_specification.md`
  - `8.8 defproc`
  - `16. Effect System`
  - `38. Intermediate Overview`
  - `51. defproc Lowering`
  - `61. Effect Validation`
  - `74. Source Map Requirements`
  - `100. Stage 2: Procedural Substrate`
  - `106. Procedure Lowering Policy`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `2. Relationship To The Full Specification`
  - `3. Non-Goals`
  - `14. Implementation Stages`
- `docs/design/workflow_language_design_principles.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/steering.md`

This slice must also preserve the guardrails established by the existing
implementation architectures and the current codebase:

- keep the frontend in `orchestrator/workflow_lisp/` and keep shared runtime
  semantics under `orchestrator/workflow/`;
- reuse Stage 1 spans, diagnostics, syntax provenance, and macro expansion
  metadata rather than inventing a second source-tracking system;
- reuse Stage 2 expression typing and variant-proof rules, but extend them
  narrowly where procedure calls need effect summaries;
- reuse Stage 3 command-boundary classification and shared-validation handoff;
- reuse Stage 4 phase-scope behavior without widening this slice into a
  generic phase library;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations.

`docs/design/workflow_command_adapter_contract.md` is authoritative for this
slice because procedures may contain `command-result` forms or call other
procedures that do. `defproc` must not become a loophole for:

- inline Python or shell that carries hidden workflow semantics;
- script wrappers with undeclared state or path effects;
- markdown report parsing as semantic authority;
- ad hoc promotion of adapter-shaped behavior into opaque helper commands.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/hygienic-defmacro-system/implementation_architecture.md`

### Decisions Reused

- Reuse the existing staged frontend pipeline:
  read -> syntax -> macro expansion -> definitions/workflows -> typecheck ->
  lowering -> shared validation.
- Reuse `SourcePosition`, `SourceSpan`, `LispFrontendDiagnostic`, recursive
  syntax metadata, and macro expansion stacks as the frontend provenance
  substrate.
- Reuse `FrontendTypeEnvironment`, Stage 2 proof checking, Stage 3
  provider/prompt extern handling, and Stage 3 command-boundary
  classification.
- Reuse the existing authored-mapping lowering bridge and the
  `elaborate_surface_workflow(...) -> lower_surface_workflow(...)` shared
  validation seam instead of inventing a second validator or YAML text target.
- Reuse Stage 4 phase scoping as an ordinary typed-expression concern rather
  than introducing a new procedure-specific phase system.

### New Decisions In This Slice

- Add a dedicated procedure layer with explicit `defproc` definitions,
  signatures, typed bodies, call-graph metadata, and lowering mode selection.
- Add frontend-local effect-signature and effect-summary types so procedures
  and workflows can expose transitive effects without redefining the shared
  Semantic IR effect graph.
- Extend typed expressions so every checked expression carries an effect
  summary in addition to a resolved type.
- Treat procedure invocation as a same-file frontend call surface distinct
  from workflow `call`:
  ordinary workflows remain runtime-callable boundaries;
  procedures remain reusable internal behavior.
- Support three deterministic lowering modes:
  `inline`, `private-workflow`, and `auto` with `auto` resolved by a
  compiler-owned policy.
- Generate hidden private workflows only when the procedure signature can
  cross the current Stage 3 workflow boundary safely; otherwise the procedure
  is inline-only.
- Extend lowering-origin tracking with procedure frames so generated steps,
  paths, and diagnostics can point to both the call site and the defining
  `defproc`.

### Conflicts Or Revisions

The current Stage 2/3 implementation assumes:

- `TypedExpr` carries only `type_ref`;
- `call` is workflow-only;
- `workflows.py` is the only same-file callable registry.

This slice revises those frontend-local assumptions narrowly:

- `TypedExpr` must grow an `effect_summary` field;
- expression elaboration/typechecking must distinguish workflow calls from
  procedure calls;
- same-file callable registration must include both procedures and workflows.

These are frontend implementation revisions only. They do not redefine shared
concepts such as Core Workflow AST, Semantic Workflow IR, TypeCatalog,
SourceMap, pointer authority, or variant proof.

## Ownership Boundaries

This slice owns:

- top-level same-file `defproc` elaboration and validation;
- explicit procedure effect-clause parsing and canonicalization;
- a procedure catalog with forward-reference support and cycle checks;
- procedure-call expression elaboration and type checking;
- transitive effect-summary computation for procedures and workflows;
- deterministic lowering-mode selection for procedures;
- inline procedure lowering into caller workflow/procedure contexts;
- hidden private-workflow generation for eligible procedures;
- procedure-aware source-map/origin tracking for generated lowering artifacts;
- focused tests and fixtures for declaration shape, call typing, effect
  mismatch, lowering-mode selection, private-workflow eligibility, cycle
  rejection, and shared-validation remapping.

This slice intentionally does not own:

- standard-library procedure APIs or phase/resource/drain libraries;
- runtime-native effects, resource movement backends, or queue/ledger state
  semantics;
- modules/imports/exports, higher-order procedure values, or workflow-ref
  expansion;
- new shared runtime semantics for pointer materialization, path safety,
  variant proof, state persistence, or provider/command execution;
- any change to the command-adapter certification model beyond reusing the
  existing Stage 3 rules.

## Proposed Package Boundary

Extend the current frontend package with one new procedure module and one new
effect-summary module:

```text
orchestrator/workflow_lisp/
  __init__.py
  compiler.py            # add procedure-aware compilation graph
  diagnostics.py         # add defproc/effect/lowering diagnostics
  effects.py             # new frontend-local effect signature/summary types
  expressions.py         # add procedure-call expression elaboration
  lowering.py            # add inline/private procedure lowering + proc origins
  procedures.py          # new defproc AST, catalog, lowering policy
  typecheck.py           # attach effect summaries during checking
  workflows.py           # infer workflow summaries and share callable catalogs
```

Responsibilities:

- `effects.py`
  - define canonical frontend-local effect records and comparison helpers;
  - normalize declared effect clauses into deterministic sets;
  - expose summary-union helpers used by typecheck and lowering policy.
- `procedures.py`
  - elaborate `defproc` forms;
  - define `ProcedureDef`, `ProcedureSignature`, `TypedProcedureDef`,
    `ProcedureCatalog`, and lowering-mode enums;
  - resolve the deterministic `auto` lowering policy;
  - validate call graphs and private-workflow eligibility.
- `expressions.py`
  - add `ProcedureCallExpr`;
  - elaborate headed list forms whose head resolves to a same-file procedure;
  - keep reserved special forms and workflow `call` behavior unchanged.
- `typecheck.py`
  - compute effect summaries on every `TypedExpr`;
  - validate procedure-call arity, argument types, and return type;
  - derive direct-effect atoms for `provider-result`, `command-result`,
    workflow `call`, and procedure `call`.
- `workflows.py`
  - keep workflow signature elaboration authoritative;
  - add inferred workflow effect summaries so workflows can include nested
    procedure effects without adding a new authored workflow effect syntax in
    this slice.
- `lowering.py`
  - inline eligible procedures into caller lowering contexts with deterministic
    generated-name prefixes;
  - generate hidden workflow mappings for `private-workflow` procedures;
  - preserve procedure-origin stacks in `LoweringOriginMap`.
- `compiler.py`
  - orchestrate macro expansion, definition elaboration, callable-catalog
    registration, procedure/workflow body type checking, lowering-plan
    resolution, and shared-validation handoff.

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/spans.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/macros.py`
- `orchestrator/workflow_lisp/phase.py`
- shared validation/runtime modules under `orchestrator/workflow/`

## Data Model

### Procedure Definitions And Catalogs

Add a dedicated frontend-local procedure model:

- `ProcedureParam`
  - `name`
  - `type_name`
  - `span`
  - `form_path`
- `ProcedureLoweringMode`
  - `inline`
  - `private_workflow`
  - `auto`
- `ProcedureDef`
  - `name`
  - `params`
  - `return_type_name`
  - `declared_effects`
  - `requested_lowering_mode`
  - `body`
  - `span`
  - `form_path`
  - `expansion_stack`
- `ProcedureSignature`
  - resolved parameter and return `TypeRef`s
  - canonical declared effect signature
  - resolved lowering capability flags
- `TypedProcedureDef`
  - definition
  - signature
  - typed body
  - inferred direct and transitive effect summaries
  - resolved lowering mode
- `ProcedureCatalog`
  - signatures by name
  - definitions by name
  - call graph edges

Keep workflows and procedures in separate catalogs, but expose a small shared
callable lookup view to the type checker. That avoids overloading
`WorkflowCatalog` with procedure-only semantics while still allowing mixed
workflow/procedure bodies to resolve local callees deterministically.

### Effect Signatures And Summaries

Do not reuse raw strings as effect authority. Introduce typed frontend-local
effect entries:

- `ReadEffect(subject)`
- `WriteEffect(subject)`
- `PublishEffect(subject)`
- `UsesProviderEffect(subject)`
- `UsesCommandEffect(subject)`
- `CallsWorkflowEffect(subject)`
- `UpdatesStateEffect(subject)`

Two additional frontend-local structures are needed:

- `ProcedureCallEdge(callee_name)`
  - stored in the call graph, not exported as a shared effect kind;
- `EffectSummary`
  - `direct_effects`
  - `transitive_effects`
  - `procedure_edges`

Bounded rules for this slice:

- every `defproc` must declare `:effects`;
- the compiler derives an inferred direct summary from the typed body;
- the compiler computes a transitive summary by walking same-file procedure and
  workflow call edges;
- the canonical declared summary must match the inferred transitive summary
  exactly after normalization;
- effect kinds not yet exercised by the existing frontend/runtime substrate
  remain reserved and out of scope rather than encoded as opaque strings.

### Procedure Calls

Introduce one new expression node:

- `ProcedureCallExpr(callee_name, args, span, form_path, expansion_stack)`

Elaboration rule:

1. reserved special forms keep their existing meaning;
2. workflow calls still require `(call workflow-name :arg value ...)`;
3. any non-reserved headed list whose head resolves to a same-file procedure
   elaborates as `ProcedureCallExpr`;
4. this tranche supports positional procedure arguments only, matched against
   declared parameter order.

The positional rule keeps the selected gap bounded and matches the direct
procedure-call shape already illustrated in the full specification. Keyword
procedure arguments and module-qualified procedure calls remain future work.

## Compilation Pipeline

Extend the current Stage 3/4 compile path without renaming its public entry
point. The existing `compile_stage3_module(...)` API already backs the current
tests and should absorb procedure support rather than introducing an
unnecessary API fork.

Proposed pipeline:

1. read source and build syntax module;
2. expand macros using the existing hygienic expansion pass;
3. elaborate definition-only forms and build `FrontendTypeEnvironment`;
4. elaborate `defworkflow` and `defproc` definitions from expanded syntax;
5. build workflow and procedure signature catalogs before body checking;
6. typecheck procedure bodies against the combined callable view and record
   per-expression effect summaries;
7. compute procedure call graphs, reject cycles, and validate declared effects
   against inferred transitive summaries;
8. typecheck workflows against the same callable view and compute inferred
   workflow summaries;
9. resolve procedure lowering modes and lower workflows plus any generated
   private procedures;
10. validate all lowered authored mappings through the existing shared
    elaboration/lowering seam.

Why this ordering matters:

- forward references for procedures and workflows remain legal within one
  file;
- effect validation does not need shared runtime changes;
- workflow bodies can safely depend on procedure summaries without requiring
  procedure bodies to be lowered first;
- private generated workflows remain an implementation detail validated
  exactly like ordinary lowered workflows.

## Typechecking And Effect Propagation

### Typed Expression Revision

Revise `TypedExpr` to carry:

- `expr`
- `type_ref`
- `effect_summary`
- `span`
- `form_path`

Pure forms contribute an empty direct/transitive summary.

Effectful forms contribute direct effects:

- `provider-result`
  - `UsesProviderEffect`
  - `WriteEffect` for the generated structured-result root
- `command-result`
  - `UsesCommandEffect`
  - `WriteEffect` for the generated structured-result root
- workflow `call`
  - `CallsWorkflowEffect`
  - the callee workflow's inferred transitive summary
- procedure `call`
  - one `ProcedureCallEdge`
  - the callee procedure's declared effect signature during first-pass
    checking, then the canonical transitive summary during graph validation

`let*` and `match` aggregate child summaries in author order but do not create
new effect kinds themselves.

### Workflow Summary Inference

This slice does not add authored `:effects` to `defworkflow`. Instead:

- workflows keep their current authored surface;
- the compiler derives `TypedWorkflowDef.effect_summary` from the typed body;
- same-file workflow summaries become available to procedure lowering-policy
  resolution and later diagnostic reporting;
- the shared runtime remains unchanged because those summaries are still
  frontend-local metadata in this tranche.

### Effect Diagnostics

Add focused diagnostic codes for this slice:

- `procedure_definition_duplicate`
- `procedure_effect_missing`
- `procedure_effect_invalid`
- `procedure_call_unknown`
- `procedure_arity_mismatch`
- `procedure_return_type_invalid`
- `procedure_effect_mismatch`
- `proc_lowering_cycle`
- `proc_private_workflow_boundary_invalid`
- `proc_lowering_annotation_invalid`

The command-adapter diagnostics already used by `command-result` stay in
force inside procedure bodies.

## Lowering Policy

### Mode Selection

Honor the full-spec `:lowering` shape:

```lisp
(defproc foo ... :lowering inline ...)
(defproc bar ... :lowering private-workflow ...)
(defproc baz ... :lowering auto ...)
```

Default mode: `auto`.

Deterministic tranche policy:

- `inline`
  - always inline if the procedure call graph is acyclic;
  - never requires workflow-boundary-lowerable parameters or return types.
- `private-workflow`
  - allowed only when every parameter and the return type are already
    Stage-3-workflow-boundary-lowerable;
  - allowed only when every reachable same-file call site can lower each bound
    argument through the current imported-bundle call surface, meaning every
    generated call binding still resolves to workflow inputs after flattening
    and managed-write-root injection;
  - rejected when the signature contains `Json`, `Provider`, `Prompt`,
    unions, or any future non-boundary type.
- `auto`
  - chooses `private-workflow` only when:
    - the signature is private-workflow eligible; and
    - every reachable call site is private-workflow-call-lowerable through the
      existing same-file `call` binding seam; and
    - the procedure has more than one distinct call site in the same-file
      call graph;
  - otherwise resolves to `inline`.

This keeps `auto` deterministic and testable without pretending to have a
cost model or resume optimizer.

### Cycle Policy

Recursive or mutually recursive procedures are rejected in this slice.

Rationale:

- the existing frontend does not implement `loop/recur` or recursive lowering;
- recursive `defproc` would require a broader runtime and call-graph contract;
- the selected gap is reusable procedural composition, not recursion.

Emit `proc_lowering_cycle` with source spans for every participating
definition edge.

## Lowering Model

### Inline Procedures

Inline lowering does not clone syntax or re-run type checking. Instead:

1. lower each argument expression in author order inside the caller context;
2. bind those lowered values to the callee parameter names in a fresh lowering
   frame;
3. lower the already-typed callee body with a deterministic generated-name
   prefix derived from:
   caller workflow/procedure + procedure name + call ordinal;
4. merge the generated steps and artifacts back into the caller context.

Source provenance for every generated node must include:

- original procedure definition span/form path;
- procedure call-site span/form path;
- macro expansion stack, if any.

### Private Generated Workflows

For private-workflow lowering, generate one hidden workflow per procedure
definition with a deterministic name such as:

```text
%<module>.<procedure>.v1
```

Rules:

- hidden workflows reuse the existing workflow-boundary contract derivation;
- hidden workflows may add compiler-generated relpath inputs for managed
  write roots exactly as ordinary Stage 3 workflows already do;
- hidden workflows are validated through the same authored-mapping shared seam
  as ordinary lowered workflows;
- calling sites lower to ordinary same-file workflow `call` steps targeting
  the hidden workflow bundle;
- generated call bindings must continue to satisfy the current Stage 3 rule
  that same-file call arguments resolve to workflow inputs, not caller-local
  temporaries or other generated values that the imported-bundle seam cannot
  transport;
- private generated workflows are implementation detail only and are not
  exported as user-authored workflow definitions.

### Boundary Eligibility

Because the shared Stage 3 workflow boundary remains record/scalar/relpath
only, private procedure workflows are legal only when:

- parameters are lowerable through the current workflow input contract rules;
- return type is a lowerable record type;
- every reachable call site can lower each binding expression through the
  existing same-file call-step surface, including the flattened input-name
  mapping and generated managed-write-root bindings already required by the
  Stage 3 workflow lowering architecture;
- no `Provider`, `Prompt`, `Json`, or union type crosses the generated
  boundary.

If those conditions do not hold:

- explicit `private-workflow` is a compile error;
- explicit `private-workflow` is also a compile error when any call site binds
  from non-input locals or other values that the current Stage 3
  `_render_call_binding_ref(...)` seam cannot export;
- `auto` falls back to `inline`.

This preserves coherence with the existing Stage 3 lowering architecture
instead of silently widening workflow-boundary semantics through generated
helper workflows.

## Shared-Validation Handoff And Source Maps

Generated procedure workflows and inlined procedure fragments must continue to
flow through the current shared validation seam:

```text
typed frontend workflows/procedures
  -> authored workflow mappings
  -> elaborate_surface_workflow(...)
  -> lower_surface_workflow(...)
  -> loaded bundle diagnostics remapped to .orc origins
```

The frontend-local lowering-origin layer must therefore grow from a single
span pointer into a procedure-aware trail. Extend `LoweringOrigin` so it can
record:

- authored span;
- form path;
- macro expansion stack;
- ordered procedure frames:
  definition name, definition span, call-site span.

Required behavior:

- any generated step from an inlined procedure reports both the procedure
  definition and the call site;
- any generated private workflow path/input/output reports the originating
  `defproc`;
- shared-validation failures on generated hidden workflows remap to the
  authored `defproc` or procedure call that caused them;
- macro provenance remains intact when a macro expands into a procedure call
  or a procedure body contains macro-expanded forms.

This satisfies the full-spec source-map requirement without redefining the
shared `SourceMap` contract itself.

## Test Surface

Add a dedicated focused procedure test module plus fixtures:

```text
tests/
  test_workflow_lisp_procedures.py
  test_workflow_lisp_workflows.py
  test_workflow_lisp_expressions.py
  test_workflow_lisp_lowering.py
  test_workflow_lisp_phase_translation.py
  fixtures/workflow_lisp/valid/defproc_inline.orc
  fixtures/workflow_lisp/valid/defproc_private_workflow.orc
  fixtures/workflow_lisp/invalid/procedure_effect_mismatch.orc
  fixtures/workflow_lisp/invalid/procedure_cycle.orc
  fixtures/workflow_lisp/invalid/procedure_private_boundary_invalid.orc
  fixtures/workflow_lisp/invalid/procedure_arity_mismatch.orc
```

Coverage requirements:

- declaration parsing and forward-reference registration;
- positional procedure-call elaboration and type checking;
- exact declared-vs-inferred effect-summary matching;
- deterministic `auto` lowering selection;
- explicit `private-workflow` rejection on non-lowerable signatures;
- explicit `private-workflow` rejection and `auto` fallback when a reachable
  call site binds from values that are not exportable through the current
  same-file workflow-call seam;
- source-remapped diagnostics for both inline and hidden-workflow procedures;
- regression coverage proving procedures do not break existing structured
  results, macros, workflow lowering, or phase translation runtime behavior.

## Verification Plan

Run the exact deterministic verification contract generated for this slice:

```text
python -m pytest --collect-only tests/test_workflow_lisp_procedures.py -q
python -m pytest tests/test_workflow_lisp_procedures.py -q
python -m pytest tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_lowering.py -q
python -m pytest tests/test_workflow_lisp_phase_translation.py::test_runtime_completed_phase_translation_matches_oracle_shape tests/test_workflow_lisp_phase_translation.py::test_runtime_blocked_phase_translation_matches_oracle_shape -q
python -m pytest tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_phase_translation.py -q
python -m pytest tests/test_workflow_lisp_reader.py tests/test_workflow_lisp_definitions.py tests/test_workflow_lisp_diagnostics.py tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_variant_proofs.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_phase_translation.py tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_procedures.py -q
```
