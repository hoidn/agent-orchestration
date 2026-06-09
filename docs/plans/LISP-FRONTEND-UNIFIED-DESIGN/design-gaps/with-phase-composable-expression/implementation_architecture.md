# With-Phase Composable Expression Implementation Architecture

Status: draft
Design gap id: `with-phase-composable-expression`
Target design: `docs/design/workflow_lisp_unified_frontend_design.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice adds only the bounded effectful-composition support required to make
`with-phase` usable as a composed expression in the current Workflow Lisp
frontend:

- allow `WithPhaseExpr` to appear in effectful expression positions that the
  current frontend already models, especially `let*` bindings and other
  lowering helpers that reuse the same step-backed export path;
- preserve the current compile-time-only `with-phase` semantics while making
  the wrapper export the lowered body's terminal outputs as a local binding
  value;
- keep phase identity, bundle roots, target roots, snapshot roots, and
  generated write roots deterministic when `with-phase` is not the outermost
  workflow or procedure body;
- preserve source maps and shared-validation ownership for provider, command,
  call, loop, and phase-stdlib effects that occur inside a composed
  `with-phase`.

This slice does not implement:

- generic effectful-composition completion for every expression family;
- nested `with-phase` support beyond the current rejection;
- new `PhaseCtx` construction syntax or changes to `phase-target`;
- new standard-library semantics for `review-revise-loop`,
  `resume-or-start`, `resource-transition`, or `backlog-drain`;
- runtime closures, runtime phase objects, or any new runtime value type;
- runtime-native write-root allocation, adapter promotion, or command-boundary
  redesign.

The work stays bounded to the selected design gap. It is an implementation
architecture for one missing composition seam, not a replacement design for the
frontend or its runtime substrate.

## Problem Statement

The current checkout already has most of the required phase substrate:

- `expressions.py` elaborates `WithPhaseExpr`;
- `typecheck.py` typechecks `WithPhaseExpr`, installs one active phase scope,
  and rejects nested scopes;
- `phase.py` and `lowering.py` derive `_ActivePhaseScope` values from generic
  `PhaseCtx` or the legacy implementation bridge;
- `_lower_with_phase()` lowers the wrapper by copying the lowering context with
  that active phase scope and lowering only the body.

What is missing is the composition layer that lets this existing wrapper behave
like an effectful intermediate value instead of only a top-level body wrapper.
Today the same AST node is accepted by typechecking, but lowering still treats
it as a special-case boundary:

- `_binding_type_for_expr()` does not recognize `WithPhaseExpr`;
- `let*` lowering therefore fails with
  `workflow_return_not_exportable: Stage 3 lowering does not support let* binding 'WithPhaseExpr'`;
- reusable/private-workflow export checks already unwrap `WithPhaseExpr` in a
  few places, so the implementation is internally inconsistent about whether
  the wrapper is semantically transparent.

The selected gap is therefore not a new phase feature. It is a normalization
gap:

```text
authored with-phase in a binding
  -> resolve deterministic active phase scope
  -> lower body under that scope
  -> export the body's terminal outputs as the binding's local value
  -> preserve existing shared validation, write-root rules, and source maps
```

If the wrapped body cannot already lower to step-backed outputs with
deterministic roots, the composed `with-phase` must reject. This slice must not
invent a second lowering path or a hidden runtime phase object.

## Design Constraints

The architecture must preserve the governing repo and design invariants:

- `docs/design/workflow_lisp_unified_frontend_design.md`
  - `24. Expression Categories`
  - `25. Effectful let*`
  - `26. Effectful match`
  - `27. with-phase as Composable Expression`
  - `29. Reusable Workflow Boundary Write Roots`
  - `31. Acceptance Gate for Effectful Composition`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `19. Context Types`
  - `21. Phase Context`
  - `26. run-provider-phase`
  - `27. review-revise-loop`
  - `57. review-revise-loop Lowering`
  - `95. Lowering Tests`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/work_instructions.md`

The slice must also preserve the current implementation guardrails:

- keep `with-phase` compile-time only; it does not become a runtime step;
- shared validation remains authoritative;
- phase roots derive from validated context data, not from authored strings or
  unstable expression identity;
- no provider, command, workflow, state, resource, or adapter effect may be
  hidden by phase composition;
- reusable/private workflows must still expose managed write roots as explicit
  generated inputs when the existing lowering rules require that boundary;
- the command-adapter contract remains authoritative for any `command-result`
  or adapter-backed behavior inside a `with-phase` body. This slice must not
  introduce wrapper scripts, inline shell/Python glue, or hidden helper
  commands to make composition work.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/let-proc-compile-time-local-proc-bindings/implementation_architecture.md`
- Additional historical slices reviewed for coherence:
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`

### Decisions Reused

- Reuse `WithPhaseExpr` as the authored AST surface; no new syntax node is
  needed.
- Reuse `build_phase_scope()` and the current `PhaseScope` validation rules in
  `phase.py`.
- Reuse `_ActivePhaseScope`, `_resolve_active_phase_scope()`, and
  `_copy_context_with_phase_scope()` as the authoritative lowering-time phase
  substrate.
- Reuse the existing rule that `with-phase` itself emits no runtime step and
  only changes the lowering context for its body.
- Reuse current managed-write-root behavior in phase stdlib lowering and
  reusable/private workflow boundary projection rather than adding a second root
  policy just for `with-phase`.
- Reuse current source-map and origin-note plumbing instead of inventing a
  separate provenance channel for composed phase scopes.

### New Decisions In This Slice

- Treat `WithPhaseExpr` as a phase-scoped effectful block in the lowering
  normalization path, not only as an outer workflow body wrapper.
- Add one shared lowering helper that resolves the active phase scope and
  lowers the wrapped body under a child context wherever a step-backed binding
  export is needed.
- Make `let*` binding export logic, reusable/private workflow export analysis,
  and branch/local projection helpers treat `with-phase` as semantically
  transparent around the already-lowerable body.
- Keep deterministic phase identity anchored to resolved context roots plus the
  authored phase name. The binding name may affect generated step prefixes for
  diagnostics, but it must not become semantic authority for phase bundle,
  snapshot, candidate, or target roots.
- Keep nested `with-phase` rejected in this slice; the architecture only makes
  one scope composable, not recursively nestable.

### Conflicts Or Revisions

The current implementation implicitly assumes that `with-phase` is only valid
where `_lower_expression()` encounters it directly. That assumption now
conflicts with the accepted target design and with the existing private-body
helpers that already unwrap the wrapper in some places.

This slice revises that assumption narrowly:

- `with-phase` remains special for context installation;
- `with-phase` stops being special for exportability;
- the wrapped body, not the wrapper node class, determines whether the composed
  expression is lowerable and exportable.

This revision does not redefine shared concepts such as Core Workflow AST,
Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant
proof.

## Ownership Boundaries

This slice owns:

- lowering-time normalization for `WithPhaseExpr` when it appears in a composed
  expression position;
- deterministic phase-scope installation for step-backed binding export;
- `let*` binding-type resolution and local-value projection for `WithPhaseExpr`;
- reusable/private workflow export checks when a body or binding is wrapped in
  `with-phase`;
- source-mapped diagnostics for phase-scoped composed-expression rejection;
- focused tests for successful and rejected composed `with-phase` lowering.

This slice intentionally does not own:

- authored context-construction forms such as `phase-ctx`, `item-ctx`, or
  `drain-ctx`;
- broader effectful-composition normalization for every expression family;
- nested phase composition, runtime closures, dynamic dispatch, or runtime
  callable values;
- new command adapters, scripts, or runtime-native effects;
- redesign of shared state layout, bundle schemas, pointer policy, or provider
  execution semantics.

## Proposed Package Boundary

Keep the work inside the existing frontend package and reuse the current phase
modules:

```text
orchestrator/workflow_lisp/
  compiler.py       # private/reusable workflow export checks
  lowering.py       # composed with-phase normalization and binding export
  phase.py          # existing phase-scope derivation reused as-is or with
                    # small helper extraction only
  typecheck.py      # current type/effect rules reused; only narrow diagnostic
                    # alignment if needed

tests/
  test_workflow_lisp_lowering.py
  test_workflow_lisp_phase_stdlib.py
  test_workflow_lisp_procedures.py
  test_workflow_lisp_examples.py
```

Primary responsibilities:

- `lowering.py`
  - recognize `WithPhaseExpr` in `_binding_type_for_expr()` and other local
    type/export helpers;
  - provide one shared helper that lowers a phase-scoped body under a copied
    lowering context and returns the body's `_TerminalResult`;
  - project the terminal outputs into local binding values exactly as if the
    body had appeared directly in that position;
  - keep hidden generated inputs and source-map origins attached to the inner
    body steps, not to a synthetic wrapper step.
- `compiler.py`
  - make private/reusable workflow export checks rely on the same composed
    `with-phase` export helper so step-backed-output validation stays
    consistent between compile-time boundary analysis and real lowering.
- `phase.py`
  - remain the authority for phase-scope derivation and validation;
  - optionally expose a tiny helper if `lowering.py` and `compiler.py` need to
    share phase-scope installation logic, but no new phase data model is
    introduced.
- `typecheck.py`
  - keep the current `WithPhaseExpr` type/effect behavior;
  - keep `phase_scope_nested_unsupported` and existing `PhaseCtx` validation
    diagnostics authoritative.

## Internal Lowering Contract

### 1. Phase-Scoped Binding Normalization

Add one lowering-only contract for composed `with-phase` expressions:

```text
lower_composed_with_phase(expr, result_type, context, local_values)
  -> resolve active phase scope from expr.ctx_expr
  -> copy lowering context with that scope
  -> lower expr.body under the scoped context
  -> return the body's steps + terminal result
```

This is not a new AST node, runtime step, or workflow boundary. It is a shared
helper used by:

- `_lower_let_star()`
- binding-type inference/export helpers
- private/reusable workflow export checks
- any branch helper that already accepts an effectful expression and wants
  `with-phase` to be transparent around the lowerable body

The helper must preserve the existing `_lower_with_phase()` semantics. The only
change is that those semantics become reusable outside the direct
`_lower_expression()` dispatch path.

### 2. Binding Type And Local Value Projection

Composed `with-phase` bindings must export their bodies using the same rules as
other effectful bindings:

- if the body result type is a record or union, export a step-backed mapping
  built from the body's terminal output refs;
- if the body result type is a primitive or path leaf with a `return` output,
  export that return ref directly;
- otherwise reject with the existing `workflow_return_not_exportable` class and
  a message that names `with-phase` composition rather than the raw
  `WithPhaseExpr` implementation detail.

This architecture intentionally does not allow `with-phase` to fabricate inline
values. If the wrapped body does not already lower to step-backed outputs, the
binding remains invalid.

### 3. Deterministic Phase Identity And Write Roots

Phase identity stays derived from validated context data:

- `PhaseCtx` or the bounded legacy bridge provides the state and artifact roots;
- the authored phase symbol selects the phase namespace under those roots;
- generated bundle, snapshot, candidate, and named-target refs come from
  `_ActivePhaseScope`;
- repeated calls, inline procedure expansion, and loop iterations continue to
  disambiguate generated step names and managed write roots through the current
  `step_name_prefix`, call counters, and stdlib-specific hidden-input
  mechanisms.

The binding name does not define phase identity. It may appear in generated
step ids for observability, but canonical phase paths remain a function of:

```text
resolved context roots + authored phase name + existing call/loop prefix policy
```

This is the answer to the target design's write-root requirement for this
slice: composed `with-phase` reuses the current deterministic root policy; it
does not introduce a new one.

### 4. Reusable Workflow Boundary Policy

Composable `with-phase` must not smuggle ambient phase state across workflow or
procedure boundaries.

The rule is:

```text
If the wrapped body would require explicit generated relpath inputs or
step-backed output projection across a reusable boundary, the composed
with-phase requires the same explicit boundary shape.
```

Consequences:

- private/generated workflows that analyze body exportability must inspect the
  wrapped body under the resolved phase scope rather than rejecting the wrapper
  class outright;
- managed write roots already exposed as generated hidden inputs remain
  generated hidden inputs;
- `with-phase` does not add a hidden global, implicit root registry, or
  runtime phase-object transport channel.

### 5. Diagnostics And Source Maps

Preserve current diagnostic ownership whenever possible:

- keep `phase_scope_nested_unsupported`,
  `phase_target_outside_with_phase`,
  `phase_context_invalid`, and
  `phase_translation_body_invalid` as the existing scope/context diagnostics;
- keep `workflow_return_not_exportable` as the class for non-exportable
  composed bodies, but rewrite the message so authored source sees
  `with-phase` composition, not only the internal Python class name;
- attach step origins to the inner provider/command/call/loop steps exactly as
  they are today, with the enclosing `with-phase` span preserved in the source
  map stack or origin note chain when the error is attributable to the
  composed scope.

This slice should not add a second provenance system. It should make composed
`with-phase` use the one the frontend already has.

## Test Strategy

Required positive coverage:

- a workflow fixture where `let*` binds a `with-phase` block and later returns
  or projects that binding;
- a reusable/private-workflow path where a body wrapped in `with-phase`
  remains exportable under current boundary rules;
- a phase-stdlib fixture showing that generated hidden write roots still route
  through explicit inputs when the `with-phase` block is composed rather than
  top-level;
- source-map coverage proving generated diagnostics still point to the authored
  `with-phase` body or binding site.

Required negative coverage:

- nested `with-phase` remains rejected with
  `phase_scope_nested_unsupported`;
- a composed `with-phase` whose body is not step-backed/exportable still fails
  with `workflow_return_not_exportable`;
- invalid `PhaseCtx` or legacy-bridge inputs still fail with existing phase
  diagnostics rather than silently degrading to ad hoc path construction;
- no new helper command, script, or adapter boundary appears just to support
  composition.

## Acceptance Conditions

This design gap is complete when:

- `WithPhaseExpr` can be lowered from the selected composed expression
  positions without changing runtime semantics;
- the wrapped body's provider/command/call effects remain visible and
  source-mapped;
- phase bundle roots, candidate roots, snapshot roots, and managed write roots
  remain deterministic under repeated call and loop prefixes;
- reusable/private workflow export analysis and real lowering agree about
  whether a composed `with-phase` is exportable;
- unsupported cases still fail explicitly instead of falling back to hidden
  runtime state or path reconstruction.
