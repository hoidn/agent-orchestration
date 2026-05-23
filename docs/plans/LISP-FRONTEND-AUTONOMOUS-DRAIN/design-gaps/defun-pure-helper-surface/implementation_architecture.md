# `defun` Pure Helper Surface Implementation Architecture

## Scope

This design gap covers only the bounded pure-helper `defun` surface required by
the full Workflow Lisp design and selected by the current drain iteration:

- add top-level `defun` definition parsing/elaboration and forward-reference
  binding;
- add same-file and imported pure-function catalogs that participate in the
  existing module graph;
- support positional pure-function calls inside Workflow Lisp expressions,
  procedures, and workflows;
- validate that `defun` bodies stay pure and never become a loophole for
  effectful workflow behavior;
- normalize `defun` calls into the existing typed-expression surface before
  workflow/procedure lowering so no new runtime boundary is introduced;
- preserve authored provenance from helper definitions and call sites through
  diagnostics and lowered-source remapping.

Out of scope for this tranche:

- new pure standard-library forms such as arithmetic, string concatenation, or
  path-join primitives that do not already exist in the frontend;
- a general compile-time evaluator, user-visible constant-folding language, or
  arbitrary compile-time code execution;
- effectful helpers, `defproc` redesign, workflow-boundary redesign, or new
  runtime-callable helper surfaces;
- new command adapters, legacy-adapter migration work, or runtime-native
  effects;
- redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog,
  SourceMap, pointer authority, variant proof, queue semantics, or persisted
  workflow state;
- replacement of the product design in
  `docs/design/workflow_lisp_frontend_specification.md`.

This is an implementation architecture for exactly the selected
`defun-pure-helper-surface` gap. It does not broaden into a general pure
language, evaluator, or runtime refactor.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_frontend_specification.md`
  - `8.6 defun`
  - `10. Sequential Binding: let*`
  - `11. Pattern Matching`
  - `38. Intermediate Overview`
  - `44. Typed Frontend AST`
  - `50. defworkflow Lowering`
  - `51. defproc Lowering`
  - `60. Type Validation`
  - `61. Effect Validation`
  - `74. Source Map Requirements`
  - `99. Stage 1: Frontend Core Without Workflow Execution`
  - `Final Design Center`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `2. Relationship To The Full Specification`
  - deferred non-goals around `defun`
  - `14. Implementation Stages`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/steering.md`

The slice must also preserve the guardrails established by the current
implementation and prior architecture documents:

- keep `orchestrator/workflow_lisp/` as the frontend-owned package and keep
  shared runtime semantics under `orchestrator/workflow/`;
- reuse the staged frontend pipeline:
  read -> syntax -> modules -> macro expansion -> definitions/callables ->
  typecheck/effects -> lowering -> shared validation;
- reuse `SourcePosition`, `SourceSpan`, recursive syntax provenance,
  `LispFrontendDiagnostic`, `EffectSummary`, `LoweringOriginMap`, and the
  persisted source-map bridge rather than inventing parallel tracking systems;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- reuse the existing authored-mapping ->
  `elaborate_surface_workflow(...)` ->
  `lower_surface_workflow(...)` seam instead of generating YAML text or adding
  a second validator;
- keep `defproc` as the effectful reusable-behavior surface and keep
  `defworkflow` as the runtime-callable boundary.

`docs/design/workflow_command_adapter_contract.md` is authoritative here even
though this slice does not add new command boundaries. `defun` purity must
explicitly forbid bodies that smuggle workflow semantics through:

- `command-result`;
- `provider-result`;
- workflow `call`;
- stdlib forms backed by certified adapters or runtime-native effects;
- inline shell/Python glue or report parsing reachable through helper bodies.

`docs/steering.md` is empty in this checkout. That does not widen scope. The
selector bundle, target contract, prior implementation architectures, and
current repo evidence remain the effective steering surfaces.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/core-workflow-ast-shared-contract/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/executable-ir-runtime-plan/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-required-lints/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-validation-diagnostics-pipeline/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/hygienic-defmacro-system/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/lisp-frontend-cli-diagnostics-surface/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/module-import-export-resolution/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resource-drain-library/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resume-or-start-reusable-state-validation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/semantic-workflow-ir-shared-contract/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-boundary-type-flattening/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md`

### Decisions Reused

- Reuse the existing staged frontend pipeline and the package ownership split
  between `orchestrator/workflow_lisp/` and `orchestrator/workflow/`.
- Reuse the current provenance substrate:
  `SourcePosition`,
  `SourceSpan`,
  recursive syntax objects,
  `LispFrontendDiagnostic`,
  macro expansion stacks,
  `LoweringOriginMap`,
  and the persisted `source_map.json` bridge.
- Reuse the Stage 2 typed-expression and proof substrate for `let*`,
  `record`, field access, and `match` rather than inventing a second pure
  expression checker.
- Reuse the module/import/export slice's canonical module keys, linked compile
  order, import scopes, and export surfaces rather than introducing a separate
  helper-library loader.
- Reuse the defproc slice's effect-summary model and its separation between
  pure frontend structure and effectful reusable behavior.
- Reuse lowering through the existing authored mapping ->
  `elaborate_surface_workflow(...)` ->
  `lower_surface_workflow(...)` seam, with no YAML text intermediate and no
  second runtime executor.

### New Decisions In This Slice

- Add a dedicated frontend-only `defun` layer with pure helper definitions,
  signatures, call-graph metadata, and import/export support.
- Add one explicit pure-function call expression surface and keep it distinct
  from workflow `call` and effectful `defproc` calls.
- Treat visible `defun` and `defproc` names as one shared direct-head call
  namespace. Workflows remain separate because they are invoked only through
  explicit `call`.
- Support same-file and imported `defun` forward references by building a
  function catalog before body typechecking, mirroring the existing procedure
  and workflow catalog flow.
- Choose deterministic pre-lowering normalization rather than a general
  compile-time evaluator:
  `defun` calls are rewritten into existing pure expression forms before
  workflow/procedure lowering, so the runtime never sees a pure-helper
  boundary.
- Make purity a hard authored contract:
  `defun` bodies may use only pure expression forms and other `defun` calls;
  they may not call procedures, workflows, providers, commands, adapters, or
  resource/drain stdlib forms.

### Conflicts Or Revisions

The parser/core, module, macro, and compiler slices currently assume that the
non-type top-level callable surfaces are only `defproc`, `defworkflow`, and
`defmacro`. This slice revises that assumption narrowly:

- `defun` becomes an admitted top-level form;
- `defun` is not added to `WorkflowLispModule.definitions` because it is not
  top-level type authority;
- definition-only filtering must explicitly strip `defun` the same way it
  strips workflows, procedures, and macros.

The module/import/export slice currently exposes types, macros, procedures, and
workflows. This slice revises that export model narrowly:

- add `functions_by_name` to the module export surface;
- add function bindings to import scopes and linked compilation state;
- keep functions compile-time/frontend-local and do not invent imported
  runtime bundles for them.

The defproc slice assumes bare list heads map only to procedures after special
form checks. This slice narrows that assumption:

- bare list heads may resolve to `defun` or `defproc`;
- visible-name conflicts between those two callable surfaces become compile
  errors instead of order-dependent resolution;
- workflows still require explicit `call` and are not part of this direct-head
  namespace.

No prior slice is revised on shared concepts such as spans, diagnostics, Core
Workflow AST, Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority,
or variant proof.

## Ownership Boundaries

This slice owns:

- `defun` elaboration and validation;
- same-file and imported function catalogs, signatures, and call-graph checks;
- direct-head pure-function call elaboration and typechecking;
- authored purity validation for helper bodies;
- pre-lowering normalization/inlining of pure-function calls into existing
  expression forms;
- helper-aware provenance notes for diagnostics and lowered source remapping;
- focused fixtures and tests for syntax, imports/exports, purity, arity,
  return typing, call cycles, normalization, and provenance.

This slice intentionally does not own:

- new pure standard-library operators or a general compile-time evaluator;
- new runtime call-step semantics, workflow boundary semantics, or imported
  runtime bundle semantics for helper functions;
- shared path safety, contract refinement, pointer authority, snapshot
  validation, state persistence, or runtime observability contracts;
- command-adapter certification policy, legacy-adapter migration, or
  runtime-native promotion;
- new persisted artifacts beyond the existing compile/build diagnostics and
  source-map surfaces.

## Current Checkout Facts

- `orchestrator/workflow_lisp/definitions.py` currently elaborates only
  `defenum`, `defpath`, `defrecord`, and `defunion`; there is no `defun`
  definition model.
- `orchestrator/workflow_lisp/compiler.py` still admits `defworkflow` and
  `defproc` as special top-level non-definition forms, but no `defun` form is
  recognized in definition-only filtering or Stage 1 top-level validation.
- `orchestrator/workflow_lisp/macros.py` reserves and validates top-level
  heads for `defworkflow`, `defproc`, and other existing forms, but not
  `defun`.
- `orchestrator/workflow_lisp/modules.py` exposes export/import namespaces only
  for types, macros, procedures, and workflows; there is no function namespace.
- `orchestrator/workflow_lisp/expressions.py` already has `ProcedureCallExpr`
  for bare-head reusable calls, but no pure-function call node.
- `orchestrator/workflow_lisp/typecheck.py` already carries `effect_summary`
  on every `TypedExpr`. That is reusable for proving helper-call purity, but it
  does not provide function catalogs, import resolution, or call normalization
  by itself.
- `docs/steering.md` is empty in this checkout and does not change the bounded
  nature of the selected gap.

## Proposed Package Boundary

Extend the current frontend package with one dedicated pure-helper layer and
narrow updates to existing compilation modules:

```text
orchestrator/workflow_lisp/
  compiler.py            # add defun-aware catalog build and linked compilation
  definitions.py         # admit defun in top-level filtering without folding it into type defs
  diagnostics.py         # add defun-specific diagnostic codes
  expressions.py         # add FunctionCallExpr and visible helper-call resolution
  functions.py           # new defun AST, catalog, purity, normalization
  lowering.py            # lower normalized expressions and preserve helper provenance notes
  macros.py              # reserve/allow defun as a top-level expanded form
  modules.py             # export/import function namespace and call-head conflicts
  procedures.py          # validate shared direct-head namespace with defun
  typecheck.py           # typecheck pure-function calls and merge argument effects
  workflows.py           # allow workflows to typecheck against imported/local defuns
```

Responsibilities:

- `functions.py`
  - elaborate `defun` forms;
  - define `FunctionDef`, `FunctionSignature`, `TypedFunctionDef`,
    `FunctionCatalog`, and call-graph helpers;
  - validate helper purity and reject cycles;
  - normalize helper calls into existing pure expression forms before lowering.
- `expressions.py`
  - add `FunctionCallExpr`;
  - resolve visible helper calls after special-form dispatch;
  - keep workflow `call` and procedure-call behavior explicit and separate.
- `typecheck.py`
  - typecheck `FunctionCallExpr` arity, argument types, and return type;
  - merge call-site argument effect summaries without adding any direct helper
    effect atoms;
  - enforce pure helper return-type matching through the same typed-expression
    machinery used elsewhere.
- `modules.py`
  - export/import helper names explicitly;
  - resolve imported helper references to canonical module-qualified names;
  - reject visible-name collisions in the direct-head function/procedure
    namespace.
- `compiler.py`
  - orchestrate function catalog construction before procedure/workflow body
    typechecking;
  - thread imported/local helper definitions across linked module compilation;
  - run helper-call normalization before lowering workflows and procedures.
- `lowering.py`
  - treat normalized helper-expanded expressions as ordinary expression input;
  - preserve call-site provenance and add helper-definition notes where a
    lowered artifact originated from an inlined helper body.
- `definitions.py`, `macros.py`, and `procedures.py`
  - make narrow admission/reserved-name/collision changes required for `defun`
    to coexist with the already implemented surfaces.

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/spans.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/effects.py`
- `orchestrator/workflow_lisp/source_map.py`
- shared validation/runtime modules under `orchestrator/workflow/`

## Data Model

### Pure Helper Definitions

Add one dedicated frontend-local helper model:

- `FunctionParam`
  - `name`
  - `type_name`
  - `span`
  - `form_path`
  - `expansion_stack`
- `FunctionDef`
  - `name`
  - `params`
  - `return_type_name`
  - `body`
  - `span`
  - `form_path`
  - `expansion_stack`
- `FunctionSignature`
  - `name`
  - `params: tuple[(name, TypeRef), ...]`
  - `return_type_ref`
  - `span`
  - `form_path`
- `TypedFunctionDef`
  - `definition`
  - `signature`
  - `typed_body`
- `FunctionCatalog`
  - `signatures_by_name`
  - `definitions_by_name`
  - `call_graph`

Helper names use the same canonical module-qualified key shape already reused
for procedures and workflows:

```text
<module-name>::<member-name>
```

That keeps import resolution, linked compilation, and diagnostics consistent
with the rest of the frontend.

### Function Call Expression

Add one new frontend expression node:

- `FunctionCallExpr(callee_name, args, span, form_path, expansion_stack)`

This node is intentionally frontend-local:

- it is typechecked like any other expression;
- it contributes only the effect summaries of its arguments;
- it is erased by normalization before workflow/procedure lowering;
- it never becomes a runtime step or a shared workflow boundary.

### Helper Inline Provenance

Do not add a new persisted artifact. Use frontend-local provenance notes that
can flow into existing diagnostics and lowering-origin remaps:

- primary authored blame stays on the call site;
- helper definition span/name may be attached as an additional note or helper
  frame when the normalized body later participates in lowering diagnostics.

This keeps the source-map contract stable while still making inlined helper
origins explainable.

## Compilation And Purity Pipeline

### Top-Level Admission

`defun` uses the existing callable signature shape:

```lisp
(defun helper-name
  ((arg Type) ...)
  -> ReturnType
  body)
```

Required pipeline changes:

1. parser/syntax/macro-expanded top-level validation must admit `defun`;
2. definition-only extraction must strip `defun` before type-definition
   elaboration;
3. module export discovery must recognize `defun` names as exportable members;
4. linked compilation must collect helper definitions before any body
   typechecking that might call them.

### Catalog Build Order

For each expanded module:

1. elaborate type definitions;
2. elaborate raw helper definitions;
3. elaborate raw procedure definitions;
4. elaborate raw workflow definitions;
5. derive export surfaces including helper exports;
6. build import scope;
7. resolve helper signatures from local and imported definitions;
8. typecheck helper bodies;
9. typecheck procedures and workflows against the completed helper catalog.

This preserves forward references without requiring author order tricks.

### Purity Contract

`defun` bodies are authored pure expressions. In this tranche, the legal body
surface is the pure subset already implemented by the frontend plus nested
helper calls:

- literals;
- lexical name references;
- field access;
- `record`;
- `let*`;
- `match`;
- `FunctionCallExpr`.

The following forms are explicitly illegal anywhere inside a helper body:

- workflow `call`;
- `ProcedureCallExpr`;
- `provider-result`;
- `command-result`;
- `with-phase`;
- `phase-target`;
- `run-provider-phase`;
- `produce-one-of`;
- `review-revise-loop`;
- `resume-or-start`;
- `resource-transition`;
- `finalize-selected-item`;
- `backlog-drain`.

Emit `pure_function_has_effect` when a helper body contains one of those
surfaces, even if some later effect summary might be empty. This keeps the
language distinction stable:

- `defun` is the pure helper surface;
- `defproc` is the reusable effectful surface;
- `defworkflow` is the runtime-callable surface.

### Call Graph And Cycles

Build a helper call graph from `FunctionCallExpr` references and reject helper
cycles before lowering. This tranche keeps the rule simple and deterministic:

- direct recursion is invalid;
- mutual recursion is invalid;
- there is no helper recursion runtime model or compile-time evaluator.

Use a dedicated helper-cycle diagnostic rather than reusing procedure-lowering
cycle wording.

## Typechecking And Normalization Model

### Signature And Body Checking

Helper signatures resolve through the existing `FrontendTypeEnvironment`. There
is no workflow-boundary lowerability restriction on helper parameter or return
types because helpers are not runtime boundaries.

Body checking rules:

- parameters form the initial lexical environment;
- helper calls are positional and checked against `FunctionSignature`;
- helper return expressions must match the declared return type exactly;
- variant proof inside helpers reuses the existing Stage 2 `match` rules;
- helper bodies remain import-aware through canonical helper names supplied by
  module linking.

### Call-Site Effects

`FunctionCallExpr` itself contributes no direct effects. Its effect summary is:

```text
merge(arg_1.effects, ..., arg_n.effects)
```

Implications:

- helper calls inside helper bodies remain pure because helper-body validation
  already forbids effectful subexpressions;
- helper calls inside procedures or workflows may wrap effectful argument
  expressions, and those argument effects are preserved exactly once.

This is stricter and more composable than pretending helper calls are effects
or requiring helper arguments themselves to be literals only.

### Normalization Strategy

Choose one bounded implementation strategy for this tranche:

- do not add a general compile-time evaluator;
- do not add a new pure-expression IR layer;
- normalize helper calls into existing expression nodes before lowering.

The normalization rewrite is:

```text
(helper arg1 arg2)
  =>
(let* ((p1 arg1)
       (p2 arg2))
  helper-body)
```

where:

- `p1`, `p2`, ... are the helper's authored parameters;
- `helper-body` is the callee body cloned with preserved authored provenance;
- nested helper calls are normalized recursively until no `FunctionCallExpr`
  remains.

Why this shape:

- argument expressions remain evaluated once and in order;
- no capture-prone textual substitution is needed;
- the resulting tree uses only expression forms the current lowering stack
  already understands;
- helper semantics remain fully frontend-local and disappear before runtime
  surfaces.

### Where Normalization Runs

Run normalization after helper/procedure/workflow typechecking succeeds and
before any workflow/procedure lowering pass that expects only existing
lowerable expressions.

Normalized surfaces:

- typed helper bodies, so imported/local helpers can call other helpers;
- typed procedure bodies, before effectful lowering or private-workflow
  generation;
- typed workflow bodies, before authored mapping generation.

This keeps lowering changes narrow and prevents runtime-facing code from
needing first-class helper semantics.

## Module And Macro Integration

### Module Namespace

Add helpers as first-class import/export members:

- `ModuleExportSurface.functions_by_name`
- `ModuleImportScope.function_bindings`
- `resolve_function_name(...)`

Imported helpers remain compile-time/frontend-local only. Unlike workflows,
they do not require imported runtime bundles.

### Direct-Head Callable Namespace

Visible helper and procedure names share one direct-head namespace because both
use ordinary list-head invocation syntax. The compiler must reject collisions:

- local `defun` versus local `defproc`;
- imported helper versus imported procedure under the same visible name;
- imported alias/`:only` combinations that would make a helper and procedure
  indistinguishable at one call site.

Workflow calls remain separate because they require explicit `call`.

### Macro Expansion

Macro expansion already runs before definition/procedure/workflow elaboration.
This slice keeps that rule and makes only narrow macro changes:

- `defun` is reserved as a macro name;
- expanded top-level `defun` forms are legal output;
- helper bodies consume the same expansion provenance metadata as all other
  frontend forms.

This slice does not add compile-time evaluation by macros or allow macros to
run helpers during expansion.

## Lowering, Diagnostics, And Provenance

### Lowering Handoff

After normalization, workflows and procedures lower through the existing path:

```text
typed frontend expressions
  -> authored workflow mapping
  -> shared elaboration
  -> shared lowering
  -> existing validation/runtime artifacts
```

There is no `defun`-specific runtime step, command boundary, state write,
bundle artifact, or imported runtime contract.

### Diagnostics

Add helper-specific diagnostics where the existing codes are insufficient:

- helper definition duplicate;
- helper call unknown;
- helper arity mismatch;
- helper cycle;
- pure helper has effect;
- helper return type mismatch where reuse of generic `return_type_mismatch`
  would be ambiguous.

Reuse existing codes where appropriate:

- `type_unknown`
- `type_mismatch`
- `name_unknown`
- `variant_ref_unproved`
- module import/export ambiguity codes

### Provenance

Because helpers normalize away before lowering:

- runtime/source-map authority still points primarily at workflow/procedure
  call sites and authored output-producing forms;
- helper definition provenance may be attached as a note when a normalized body
  causes a lowering or shared-validation failure;
- no new source-map artifact or coverage surface is required for this slice.

This stays aligned with the source-map and validation slices without pretending
that helpers create standalone runtime-observable nodes.

## Test Strategy

Add focused tests and fixtures for:

- valid local helper definitions and forward references;
- helper imports/exports across linked modules;
- helper/procedure visible-name collision rejection;
- helper purity rejection on every effectful expression family currently
  implemented;
- helper arity and return-type mismatches;
- helper cycle rejection;
- helper call normalization preserving single argument evaluation and typed
  result shape;
- lowering/shared-validation remaps that mention helper definition context when
  a normalized body later fails;
- macro expansion that emits `defun` or helper call sites.

Planned test surface:

```text
tests/
  test_workflow_lisp_functions.py
  test_workflow_lisp_modules.py
  test_workflow_lisp_expressions.py
  test_workflow_lisp_procedures.py
  test_workflow_lisp_workflows.py
  test_workflow_lisp_lowering.py
  test_workflow_lisp_macros.py
fixtures/workflow_lisp/
  valid/defun_local.orc
  valid/defun_forward_ref.orc
  modules/valid/imported_defun/...
  invalid/defun_effectful.orc
  invalid/defun_cycle.orc
  invalid/defun_proc_name_collision.orc
```

## Implementation Sequence

1. Add helper AST/catalog support in `functions.py` and compiler admission for
   top-level `defun`.
2. Extend modules/macros/definitions to recognize helper forms in top-level
   filtering, export surfaces, and reserved-name validation.
3. Add `FunctionCallExpr` and helper-call resolution in `expressions.py`.
4. Add helper-call typing, purity validation, and cycle checks.
5. Thread local/imported helper catalogs through linked compilation and Stage 3
   compile results.
6. Add helper-call normalization before workflow/procedure lowering.
7. Add provenance-aware diagnostics and regression tests.

## Acceptance Conditions

This slice is complete when:

1. `.orc` files may declare top-level `defun` helpers without tripping
   definition-form rejection.
2. Helpers support forward references and imported references through the
   existing linked module graph.
3. Helper bodies accept only pure expression forms and reject effectful forms
   with deterministic diagnostics.
4. Helper calls typecheck positionally and preserve argument effect summaries
   without adding direct helper effects.
5. Helper cycles are rejected deterministically.
6. Helper calls are normalized away before lowering, so no new runtime or
   shared-validator boundary is introduced.
7. Existing workflow/procedure lowering and shared-validation behavior remains
   intact for helper-free inputs.

## Verification Plan

Use deterministic checks that stay focused on helper syntax, purity, linked
imports, normalization, and existing lowering compatibility:

- collect-only on the helper-focused and touched regression modules;
- helper unit tests;
- linked-module import/export regressions;
- procedure/workflow/lowering regressions that exercise helper calls;
- one compile smoke command over a multi-module `.orc` fixture that uses an
  imported helper in a real workflow entrypoint.
