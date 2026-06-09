# Let-Proc Compile-Time Local Proc Bindings Implementation Architecture

Status: draft
Design gap id: `let-proc-compile-time-local-proc-bindings`
Target design: `docs/design/workflow_lisp_unified_frontend_design.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice adds only the bounded V1 `let-proc` surface from the unified future
design:

- one lexical local procedure binding per `let-proc`;
- explicit residual parameters, return type, and `:captures (...)`;
- compile-time closure conversion into a generated private `defproc`-equivalent;
- `(proc-ref local-name)` resolution inside the lexical body only;
- reuse of the existing `defproc`, `ProcRef`, `bind-proc`, typecheck, effect,
  specialization, lowering, and shared-validation pipeline;
- deterministic diagnostics, provenance, and tests for the selected gap.

This slice does not implement:

- nested `let-proc`;
- multiple local bindings in one form;
- direct calls to a local procedure by bare name;
- implicit captures, capture expressions, or capture aliases;
- recursive or mutually recursive local procedures;
- runtime procedure values, runtime closures, or dynamic dispatch;
- general effectful-composition completion beyond what ordinary generated
  `defproc` bodies already support.

The work stays bounded to the selected design gap. It is an implementation
architecture for one compile-time authoring feature, not a rewrite of the
frontend or a reopening of the current `ProcRef` baseline.

## Problem Statement

The current checkout already has the required substrate that the unified design
names as baseline:

- same-file and imported `defproc` catalogs in
  `orchestrator/workflow_lisp/procedures.py`;
- compile-time `ProcRef[...]`, `(proc-ref ...)`, and `bind-proc` support across
  `type_expressions.py`, `procedure_refs.py`, `typecheck.py`, `compiler.py`,
  and `lowering.py`;
- deterministic specialized hidden procedures before executable lowering;
- explicit runtime-transport rejection for compile-time callable values;
- procedure-aware provenance and lowering lineage.

What is missing is the lexical authoring layer that lets a workflow or
procedure define a short local procedure near the use site without widening the
runtime model. Today there is no `let-proc` syntax, no lexical local procedure
scope, no generated local-procedure metadata, and no targeted diagnostics for
local capture validation or local-procedure scope escape.

The selected gap is therefore not a new runtime callable model. It is a
frontend normalization problem:

```text
authored let-proc
  -> lexical local procedure binding
  -> generated private procedure definition
  -> existing ProcRef / bind-proc / defproc path
  -> no residual runtime procedure value
```

If the generated private procedure cannot typecheck or lower through the
current procedure pipeline, the authored `let-proc` must reject.

## Design Constraints

The architecture must preserve the repo and target-design invariants:

- `let-proc` remains compile-time only.
- Shared validation remains authoritative.
- No second lowering path may be introduced.
- No hidden provider, command, workflow, state, or resource effects may be
  hidden by the new syntax.
- Reports remain views, pointer files remain representations, and command
  semantics stay governed by the existing typed command boundary.
- Existing `ProcRef` and `bind-proc` behavior is baseline input, not a redesign
  target.

`docs/design/workflow_command_adapter_contract.md` was reviewed as an authority
constraint. This slice does not add scripts, adapters, or runtime-native
effects, but generated local procedures may contain the same `command-result`
or adapter-backed bodies already allowed in ordinary `defproc`. `let-proc`
must therefore lower through the same explicit command-boundary path rather
than inventing a hidden helper-command escape hatch.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- No prior implementation architectures are listed in the generated index for
  this unified-design drain iteration.
- Additional historical slices reviewed for coherence:
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
  - `docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/design-gaps/procref-static-surface-and-resolution/implementation_architecture.md`
  - `docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/design-gaps/procref-bind-proc-specialization-lowering/implementation_architecture.md`
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-validation-diagnostics-pipeline/implementation_architecture.md`

### Decisions Reused

- Reuse the current staged frontend pipeline in `compiler.py` instead of adding
  a separate `let-proc` compiler.
- Reuse `ProcedureDef`, `ProcedureSignature`, `TypedProcedureDef`,
  `ProcedureCatalog`, and the existing effect-summary and specialization path.
- Reuse compile-time `ProcRef` authority and runtime-transport rejection.
- Reuse existing source-map lineage concepts, expansion stacks, and lowering
  origin notes rather than defining a second provenance model.
- Reuse the current rule that generated callables use deterministic hidden
  names and disappear before runtime artifacts.

### New Decisions In This Slice

- Add a frontend-local `LetProcExpr` surface with one explicit local procedure
  binding and one lexical body.
- Introduce a compiler-private lexical local-procedure environment distinct
  from both ordinary value bindings and top-level procedure names.
- Closure-convert each `let-proc` binding into a generated private
  `ProcedureDef` plus metadata before ordinary procedure body typing/lowering.
- Keep direct local bare-name calls invalid in V1 even though lexical ProcRef
  variable calls remain valid elsewhere in the language.
- Preserve local-procedure identity in diagnostics and lineage through new
  local-binding metadata instead of overloading existing ProcRef-specialization
  notes.

### Conflicts Or Revisions

The current implementation treats any lexical bound name in call position as a
candidate `ProcedureCallExpr`, which is correct for ProcRef value calls such as
`(runner input)` but too permissive for V1 `let-proc`. This slice narrows that
frontend-local assumption:

- local procedure names become visible only to `(proc-ref local-name)` inside
  the lexical body;
- local procedure names do not become ordinary callable value bindings;
- bare local calls such as `(run-impl selected)` must raise
  `let_proc_bare_name_invalid`.

This is a frontend-surface revision only. It does not redefine shared concepts
such as Core Workflow AST, Semantic Workflow IR, TypeCatalog, SourceMap,
pointer authority, or variant proof.

## Ownership Boundaries

This slice owns:

- `let-proc` expression parsing and elaboration;
- V1 lexical local-procedure scope tracking;
- explicit capture-list validation;
- generated local-procedure naming and metadata;
- closure conversion from `let-proc` to compiler-private `ProcedureDef`
  instances;
- local-procedure-aware ProcRef resolution and scope diagnostics;
- targeted tests and fixtures for V1 acceptance and rejection cases.

This slice intentionally does not own:

- runtime execution semantics;
- shared validation, Core AST, Semantic IR, or executable IR redesign;
- new command adapters, helper scripts, or runtime-native effects;
- effectful-composition completion beyond what current generated `defproc`
  bodies already support;
- runtime closures, first-class procedures, or procedure transport through
  records, unions, outputs, or state.

## Proposed Package Boundary

The implementation should stay inside `orchestrator/workflow_lisp/` and extend
the existing procedure/ProcRef path:

```text
orchestrator/workflow_lisp/
  compiler.py         # discover, queue, and typecheck generated local procs
  diagnostics.py      # add stable let-proc diagnostic codes
  expressions.py      # LetProcExpr syntax + lexical-scope elaboration rules
  lowering.py         # provenance notes for generated local procedures only
  procedure_refs.py   # lexical local-proc proc-ref resolution layer
  procedures.py       # generated local-procedure metadata + name helper
  typecheck.py        # LetProcExpr typing, local proc environments, effect join
```

Primary responsibilities:

- `expressions.py`
  - add `LetProcExpr`, `LetProcBinding`, and residual-parameter syntax nodes;
  - validate one-binding V1 syntax, explicit `:captures`, and no nested
    `let-proc`;
  - thread a `lexical_local_proc_names` set so bare local calls can be rejected
    during elaboration without weakening ProcRef call-through elsewhere.
- `procedures.py`
  - add compiler-private metadata for generated local procedures;
  - add deterministic name generation for generated local callables;
  - add helpers that materialize generated `ProcedureDef` and
    `ProcedureSignature` objects from `LetProcExpr`.
- `procedure_refs.py`
  - extend ProcRef authority resolution with a lexical local-procedure layer;
  - classify lexical local references distinctly from imported or top-level
    procedures for diagnostics and explain output.
- `compiler.py`
  - queue generated local procedures before ordinary body typing/lowering;
  - typecheck generated local procedures through `_typecheck_procedure_definitions`;
  - detect local-procedure scope escape and recursion;
  - include generated local procedures in effect-summary convergence and
    lowering inputs.
- `typecheck.py`
  - typecheck `LetProcExpr` by creating a generated local procedure entry,
    typing its body through the ordinary procedure path, and then typing the
    outer lexical body with a local ProcRef environment;
  - merge generated-procedure effects into the outer expression summary only
    through ordinary ProcRef consumers or specialized calls.
- `lowering.py`
  - keep lowering authority unchanged;
  - add provenance notes so generated steps can point back to the `let-proc`
    form, the local procedure signature, and the consuming `(proc-ref ...)`
    site.

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/spans.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/workflows.py`
- shared runtime and validation modules under `orchestrator/workflow/`

## Data Model

### New Frontend Expression Nodes

Add a dedicated authored surface:

- `LetProcBinding`
  - `local_name`
  - `params`
  - `return_type_name`
  - `capture_names`
  - `local_body_syntax` or elaborated local body expression
  - source span, form path, expansion stack
- `LetProcExpr`
  - `binding`
  - `body`
  - source span, form path, expansion stack

V1 requires exactly one binding. Multiple bindings should be rejected in
elaboration before any generated procedure is created.

### Generated Local Procedure Metadata

Add compiler-private metadata separate from ordinary ProcRef specialization:

- `GeneratedLocalProcedure`
  - `authored_local_name`
  - `generated_name`
  - `owner_callable_name`
  - `capture_names`
  - `residual_params`
  - `origin_span`
  - `origin_form_path`
  - `body_span`

This metadata should be attached to the generated `TypedProcedureDef` and
should also be available to ProcRef resolution and provenance rendering.

### Name Generation

Use a deterministic hidden procedure name aligned with the current generated
callable naming style:

```text
%let-proc.<module-or-owner>.<local-name>.<stable-hash>
```

Stable-hash inputs should cover:

- owning module identity;
- owner callable identity;
- `let-proc` source span;
- local name;
- residual signature;
- ordered capture list;
- normalized local body identity.

The implementation may render the name with dot-delimited normalization rather
than the slash-delimited sketch in the design doc so it stays coherent with the
current `%proc-ref...` and generated private-workflow naming conventions.

## Elaboration And Lexical Scope Rules

### 1. Parse `let-proc` as a dedicated special form

`expressions.py` should recognize:

```lisp
(let-proc (name ((param ParamType) ...) -> ReturnType
             :captures (capture-name ...)
             local-body)
  outer-body)
```

V1 rejections owned at elaboration time:

- malformed syntax: `let_proc_syntax_invalid`
- multiple bindings: `let_proc_multiple_bindings_unsupported`
- nested `let-proc`: `let_proc_nested_unsupported`
- capture expressions or field selections: `let_proc_capture_not_identifier`

### 2. Keep local procedure names out of ordinary callable-name resolution

Outer-body elaboration must distinguish three namespaces:

- ordinary lexical value bindings;
- top-level/imported procedures and ProcRef-valued lexical bindings;
- V1 lexical local procedure names.

The local procedure name must be visible only for explicit ProcRef resolution,
not as an ordinary call head. If an outer-body call head matches a lexical
local procedure name, elaboration should raise `let_proc_bare_name_invalid`
instead of producing a `ProcedureCallExpr`.

### 3. Prevent scope escape

The local procedure name should be installed only while elaborating and
typechecking the outer lexical body of the containing `LetProcExpr`. Any
`(proc-ref local-name)` outside that scope must raise `let_proc_scope_escape`.

## Closure Conversion Strategy

### 1. Generate an ordinary private `ProcedureDef`

Each `let-proc` binding should lower first into a compiler-private procedure
definition with expanded parameters:

```text
(capture_1 ... capture_n residual_param_1 ... residual_param_m) -> ReturnType
```

The generated procedure body is the authored local body, and captures become
ordinary leading procedure parameters.

### 2. Materialize capture bindings as compile-time value bindings

The containing lexical environment provides capture values. The compiler should
record:

- capture names and resolved types;
- capture source spans;
- ProcRef-valued captures separately from ordinary value captures.

When the generated procedure is typed or specialized, capture bindings should
reuse the existing `ProcedureCallableSpecialization` path:

- ProcRef-valued captures become `proc_ref_bindings`;
- ordinary captures become `value_bindings`;
- no runtime closure object is created.

### 3. Reuse the ordinary procedure pipeline

The generated procedure must pass through the existing stages:

- signature resolution in `build_procedure_catalog(...)`;
- body typing in `_typecheck_procedure_definitions(...)`;
- effect-summary inference and cycle validation;
- ProcRef specialization if the local body itself consumes ProcRef bindings;
- ordinary lowering and shared-validation handoff.

No `let-proc`-specific executable lowerer is allowed.

## Typechecking And Effect Rules

### 1. Capture validation

For each `LetProcExpr`:

- every capture name must resolve in the surrounding lexical value environment;
- duplicate captures raise `let_proc_capture_duplicate`;
- capture names may not collide with residual parameter names;
- ProcRef capture types remain compile-time-only and cannot escape runtime
  surfaces through the local procedure return type or outer body.

### 2. Local body typing

The generated local procedure body must typecheck against the declared return
type through the ordinary procedure path. Any existing body-lowering or type
error should be preserved and augmented with local-procedure context, reported
as `let_proc_body_lowering_unsupported` only when the underlying failure is
specifically "generated ordinary defproc body cannot lower."

### 3. Outer body typing

While typechecking the outer lexical body:

- `(proc-ref local-name)` resolves to the generated procedure signature through
  a lexical local-procedure registry;
- the resulting value type is ordinary residual `ProcRef[...]`;
- direct use of the local name as a value remains invalid.

### 4. Effect visibility

`let-proc` itself introduces no runtime effect. The only visible effects are
the ones already carried by the generated procedure when it is selected or
called through ordinary ProcRef specialization. If the generated procedure
would expose provider, command, workflow, state, or resource effects as an
ordinary `defproc`, the same effects must remain visible here.

## ProcRef Resolution And Diagnostics

Extend `procedure_refs.py` with a lexical local-procedure authority layer:

- `kind="lexical_local_procedure"` on the authority source;
- lookup order inside active `LetProcExpr` scope:
  1. active lexical local procedures
  2. visible top-level/imported procedures
- authored references to generated hidden names must raise
  `let_proc_generated_name_private`

Required diagnostics for this slice:

- `let_proc_syntax_invalid`
- `let_proc_multiple_bindings_unsupported`
- `let_proc_nested_unsupported`
- `let_proc_recursive_unsupported`
- `let_proc_capture_unknown`
- `let_proc_capture_duplicate`
- `let_proc_capture_not_identifier`
- `let_proc_name_collision`
- `let_proc_bare_name_invalid`
- `let_proc_scope_escape`
- `let_proc_generated_name_private`
- `let_proc_body_lowering_unsupported`
- `let_proc_return_type_invalid`
- `let_proc_proc_ref_signature_invalid`

Where an existing diagnostic is more specific, keep it and add local-procedure
context rather than replacing it wholesale.

## Recursion And Rejection Rules

V1 should reject any self-reference path involving the local procedure:

- bare direct call is already invalid;
- `(proc-ref local-name)` inside the local procedure body is
  `let_proc_recursive_unsupported`;
- no nested `let-proc`, so mutually recursive local procedures are not in
  scope for this slice.

Generated local procedures must also remain subject to the existing procedure
cycle and ProcRef specialization cycle checks after closure conversion.

## Source Maps And Provenance

Generated local procedures must preserve authored lineage for:

- the `let-proc` form;
- the local procedure signature;
- each capture name;
- the local body;
- the outer-body `(proc-ref local-name)` use site;
- any generated specialized procedure name;
- lowered step, core-node, validation-subject, and executable-node origins.

Implementation rule:

- do not invent a separate source-map document section;
- extend existing lowering notes and generated-name origin tracking so local
  procedures show up as generated private procedures with authored `let-proc`
  context.

## Tests And Fixtures

Add focused fixtures under `tests/fixtures/workflow_lisp/` and focused tests in
the current frontend suites, primarily:

- `tests/test_workflow_lisp_expressions.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_source_map.py`
- `tests/test_workflow_lisp_lowering.py`

Positive coverage must include:

- one simple `let-proc` with one residual parameter;
- capture threading into the generated procedure;
- `(proc-ref local-name)` forwarded into a consumer expecting `ProcRef[...]`;
- deterministic generated hidden procedure naming;
- effect visibility preserved through selected local procedures;
- runtime artifacts containing no unresolved local procedure value.

Negative coverage must include:

- malformed syntax;
- multiple bindings;
- nested `let-proc`;
- unknown capture;
- duplicate capture;
- field-selection or alias capture;
- bare local call;
- scope escape;
- generated-name authored reference;
- self-reference / recursion attempt;
- ordinary body-lowering limitation surfaced with local-procedure context;
- runtime transport attempts through records, unions, workflow outputs, or loop
  state.

## Acceptance Gate

Do not mark this gap complete until the implementation proves:

- `let-proc` compiles away into generated private procedures plus existing
  ProcRef semantics;
- generated local procedures use the ordinary procedure catalog, effect
  inference, specialization, and lowering path;
- no runtime artifact contains a local procedure value, generated closure
  object, or generated-name dispatch string;
- source maps and diagnostics report authored `let-proc` locations rather than
  only hidden generated names;
- all V1 restrictions from Part I and Section 20 of
  `docs/design/workflow_lisp_unified_frontend_design.md` have deterministic
  tests.
