# Workflow Lisp Loop/Recur On-Exhausted Projection Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-loop-recur-on-exhausted-projection`
Target design: `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected prerequisite gap from the target design:

- add one public authored `:on-exhausted` surface to `loop/recur` so ordinary
  local and imported `.orc` code can request typed exhaustion projection;
- wire that authored surface onto the existing frontend `LoopRecurExpr`
  carrier instead of relying on review-loop-specific hidden injection;
- lower the authored exhaustion route through the existing shared
  `repeat_until.on_exhausted.outputs` substrate plus the existing final typed
  result projection from loop-frame outputs;
- add the focused elaboration, typecheck, lowering, source-map, and
  shared-validation fixtures needed to prove the generic route works without a
  review-loop-only bridge.

Out of scope for this slice:

- authorable parametric loop-state carriers; that remains the separate
  `workflow-lisp-parametric-loop-state-authoring` gap;
- retirement of the promoted `review-revise-loop` bridge or replacement of the
  bridge with ordinary stdlib `.orc`; that remains the separate
  `workflow-lisp-stdlib-review-revise-loop-implementation` gap;
- runtime changes to `repeat_until` execution, checkpointing, or failure
  semantics;
- new command adapters, runtime-native effects, report parsing, pointer-as-
  authority behavior, or hidden shell/Python glue;
- redesign of shared Core Workflow AST, Semantic Workflow IR, Executable IR,
  TypeCatalog, SourceMap, pointer authority, or variant proof.

This is a bounded implementation architecture for one selected prerequisite
only. It does not replace the umbrella Workflow Lisp specification or the
review/revise stdlib integration design.

## Problem Statement

The selected target design names a narrow missing prerequisite: ordinary
`loop/recur` authoring still lacks a public `:on-exhausted` route even though
the runtime substrate already supports scalar `repeat_until.on_exhausted`
overrides and the review-loop lowering model expects typed exhaustion
projection.

Fresh checkout evidence shows the gap is specifically at the authored frontend
boundary:

1. `orchestrator/workflow_lisp/expressions.py` already defines
   `LoopRecurExpr.on_exhausted_result_expr`, but `_elaborate_loop_recur(...)`
   still accepts only `:max`, `:state`, and a final loop-body `fn`.
2. `orchestrator/workflow_lisp/typecheck_dispatch.py` already typechecks an
   exhaustion result expression for type equality and purity when one is
   present.
3. `orchestrator/workflow_lisp/lowering/control_loops.py` already lowers an
   exhaustion expression into `repeat_until.on_exhausted.outputs` plus final
   result normalization from loop-frame outputs.
4. `orchestrator/workflow_lisp/phase_stdlib_typecheck.py` still injects
   `on_exhausted_result_expr` for the review-loop bridge, proving the lowered
   substrate exists but is not yet reachable through generic authored syntax.
5. `tests/test_workflow_lisp_expressions.py` still exercises only the
   authored `:max` / `:state` shape, while review-loop tests assert exhaustion
   behavior only through bridge-owned lowering.

That is exactly the hidden-bridge condition the target design wants removed:

- the public frontend cannot yet author the exhaustion route;
- imported `.orc` stdlib code cannot own the route honestly;
- the bridge remains the only semantic producer of `on_exhausted_result_expr`.

The missing work is therefore not a new runtime capability and not a new loop
executor. It is the bounded authoring contract that makes the already-present
typed/lowered path reachable through ordinary `.orc` code.

## Design Constraints

The implementation must stay coherent with:

- `docs/index.md`
- `docs/steering.md`
  - empty in this checkout; no additional local steering text is present
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - `12.1 Authorable loop/recur :on-exhausted Dependency`
  - `18. Loop Exhaustion Projection`
  - `24. Incremental Implementation Plan`
    - `Stage 7 - Generic loop/recur :on-exhausted`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `13. Loops`
  - `44. Typed Frontend AST`
  - `58. backlog-drain Lowering`
  - `59. Validation Sequence`
  - `63. Variant Proof Validation`
  - `64. Snapshot Validation`
  - `74. Source Map Requirements`
  - `95. Lowering Tests`
  - `104. Stage 6: Resource And Drain Library`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/2/prerequisite-selector/selection.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/2/design-gap-architect/architecture-targets.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/2/design-gap-architect/existing-architecture-index.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

The slice must preserve these guardrails:

- keep `orchestrator/workflow_lisp/` as the frontend-owned package and shared
  runtime behavior under `orchestrator/workflow/`;
- reuse the staged frontend pipeline:
  read -> syntax -> macro expansion -> definitions/procedures/workflows ->
  typecheck -> lowering -> shared validation;
- keep `repeat_until` exhaustion semantics unchanged when no authored
  `:on-exhausted` clause is present;
- keep `repeat_until.on_exhausted.outputs` limited to scalar overrides, with
  non-scalar result fields reconstructed from loop-frame outputs during final
  normalization;
- keep typed state and artifact values authoritative, with reports remaining
  views and pointer files remaining representations;
- keep the command-adapter contract authoritative even though this slice adds
  no adapter surface; the new authoring route must not smuggle hidden command
  semantics into loop lowering;
- do not treat the empty `docs/steering.md` file as permission to widen scope.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The full index in
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/2/design-gap-architect/existing-architecture-index.md`
was reviewed for coherence. The directly reused slices for this gap are:

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/loop-recur-bounded-loops/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/track-a-form-registry-elaboration-boundary/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-expression-traversal-prerequisite/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-stdlib-review-revise-loop-implementation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-parametric-loop-state-authoring/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-review-loop-report-findings-path-split/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`

### Decisions Reused

- Reuse the bounded-loops decision that public `loop/recur` lowers through the
  shared `repeat_until` substrate rather than a second loop executor.
- Reuse the existing `LoopRecurExpr` carrier and the current provenance
  substrate:
  `SourcePosition`,
  `SourceSpan`,
  `LispFrontendDiagnostic`,
  macro expansion stacks,
  `LoweringOrigin`,
  and `LoweringOriginMap`.
- Reuse the current loop projection helpers in
  `orchestrator/workflow_lisp/lowering/control_loops.py` rather than inventing
  a second exhaustion-materialization path.
- Reuse the expression-traversal prerequisite's shared walking model; the
  authored exhaustion expression is just another child expression of
  `LoopRecurExpr`.
- Reuse the review-loop implementation slice's rule that typed `EXHAUSTED`
  construction must read loop-frame outputs, not hidden bridge-owned state.
- Reuse the state-layout and source-map ownership split; this slice does not
  invent loop-local path derivation rules.

### New Decisions In This Slice

- Extend authored `loop/recur` syntax with one optional keyword section:
  `:on-exhausted <expr>`.
- Keep the loop-body `fn` as the final positional argument. `:on-exhausted`
  becomes an optional keyword peer of `:max` and `:state`, not a new loop-body
  subform and not a review-loop-specific compatibility hook.
- Treat the authored exhaustion expression as the public producer of
  `LoopRecurExpr.on_exhausted_result_expr`. No new AST node is added.
- Lower authored exhaustion exactly through the already-existing two-stage
  route:
  scalar fields become `repeat_until.on_exhausted.outputs`, and the full typed
  result is reconstructed afterward from loop-frame outputs plus those scalar
  exhaustion markers.
- Keep missing `:on-exhausted` behavior unchanged for generic loops:
  exhausting `max_iterations` remains ordinary
  `repeat_until_iterations_exhausted` failure unless the author provides the
  explicit clause.

### Conflicts Or Revisions

The bounded-loops slice intentionally stopped short of a public exhaustion
surface and preserved shared runtime failure-on-exhaustion semantics only.
This slice revises that omission narrowly:

- `loop/recur` keeps the same lowered runtime substrate;
- authors gain one explicit way to request typed exhaustion projection;
- the default no-clause behavior remains unchanged.

This slice does not revise the separate loop-state prerequisite. A typed
`EXHAUSTED` result that depends on carried path or record fields still relies
on authored loop-frame outputs; this slice only exposes the exhaustion clause,
not the general loop-frame carrier design.

## Ownership Boundaries

This slice owns:

- authored `loop/recur :on-exhausted` syntax and elaboration in
  `orchestrator/workflow_lisp/expressions.py`;
- any small registry/admission updates needed so the public `loop/recur`
  surface keeps one authoritative keyword contract;
- frontend validation of authored exhaustion-shape errors that belong at
  elaboration or typecheck time;
- reuse of the existing lowering path in
  `orchestrator/workflow_lisp/lowering/control_loops.py` for authored
  exhaustion projections;
- source-map coverage for the authored exhaustion expression and generated
  loop/result steps;
- focused fixtures and tests for elaboration, typecheck, lowering, and review-
  loop regression behavior.

This slice intentionally does not own:

- general loop-state carrier authoring;
- review-loop bridge retirement;
- runtime `repeat_until` executor behavior, resume checkpoints, or persisted
  loop-frame schema;
- new command adapters, runtime-native effects, or report/pointer authority
  policy;
- redesign of shared Core Workflow AST, Semantic Workflow IR, Executable IR,
  TypeCatalog, SourceMap, or variant proof.

## Current Checkout Facts

Fresh checkout evidence shows the slice is both narrow and feasible:

- `orchestrator/workflow_lisp/expressions.py` already defines
  `LoopRecurExpr.on_exhausted_result_expr`.
- `orchestrator/workflow_lisp/typecheck_dispatch.py` already checks that an
  exhaustion expression is pure and has the same type as the loop's reachable
  `done` result.
- `orchestrator/workflow_lisp/lowering/control_loops.py` already emits
  `repeat_until.on_exhausted.outputs` only for scalar loop-result fields and
  keeps non-scalar fields on the loop frame for final normalization.
- `orchestrator/workflow_lisp/phase_stdlib_typecheck.py` still synthesizes an
  exhaustion result expression for the review-loop bridge, proving the lowered
  path exists before the public syntax does.
- `orchestrator/workflow_lisp/expression_traversal.py` already walks
  `on_exhausted_result_expr` when present.
- `_elaborate_loop_recur(...)` still hard-codes the older authored shape and
  rejects any public `:on-exhausted` clause.
- `tests/test_workflow_lisp_expressions.py` still lacks a public-syntax
  elaboration assertion for `:on-exhausted`.
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` remains empty,
  so there is no recorded event in the selected run state that supersedes the
  prerequisite rationale.

That evidence is the required feasibility proof for this slice: the missing
work is at the public frontend contract, not in runtime semantics.

## Proposed Architecture

### 1. Public `loop/recur` Syntax

Adopt one explicit authored shape:

```lisp
(loop/recur
  :max max-iterations
  :state initial-state
  :on-exhausted exhausted-result     ; optional
  (fn (state) ...))
```

Rules:

- `:max` and `:state` remain required.
- `:on-exhausted` is optional and may appear only once.
- the loop-body `fn` remains the final positional child of `loop/recur`.
- no other new keyword sections are introduced in this slice.

Implementation direction:

- change `_elaborate_loop_recur(...)` to parse keyword sections from all items
  before the final `fn`, rather than assuming the pre-gap fixed arity;
- populate `LoopRecurExpr.on_exhausted_result_expr` directly from authored
  syntax when the clause is present;
- keep the authored form path and expansion stack on that expression so later
  diagnostics and generated-step provenance remain precise.

This keeps the public surface minimal while making the existing internal field
authoritative for generic authored code.

### 2. Typechecking Contract

Reuse the existing `LoopRecurExpr` typechecking route in
`orchestrator/workflow_lisp/typecheck_dispatch.py`.

The authored `:on-exhausted` expression must satisfy:

- same result type as the loop body's reachable `done` result;
- no effects;
- no runtime-only values that the normal loop result could not transport.

Typechecking behavior stays generic:

- missing `:on-exhausted` is allowed for ordinary loops;
- a mismatched exhaustion result reuses the loop result-type mismatch
  diagnostic path;
- an impure exhaustion expression fails at compile time;
- proof context for the authored exhaustion expression starts fresh from the
  loop binding environment, just like the existing hidden route.

This slice does not add a special compile-time error merely because a loop can
exhaust. The explicit clause remains opt-in, matching the target design's rule
that default exhaustion stays an ordinary runtime failure.

### 3. Lowering Contract

Lowering remains in the existing control-loop owner:
`orchestrator/workflow_lisp/lowering/control_loops.py`.

Required generated behavior:

- if `:on-exhausted` is absent:
  no `repeat_until.on_exhausted` block is emitted and shared runtime behavior
  remains unchanged;
- if `:on-exhausted` is present:
  lowering derives scalar overrides for
  `repeat_until.on_exhausted.outputs` from the authored result expression;
- path, record, and union payload fields that are not scalar are not written
  directly through `on_exhausted.outputs`; they continue to come from the last
  materialized loop-frame outputs during final normalization.

This preserves the target design's contract:

```text
loop/recur :on-exhausted
  -> repeat_until.on_exhausted.outputs for scalar markers
  -> final typed projection from last materialized loop-frame outputs
```

The slice should keep using the existing projection helpers instead of adding a
loop-only contract dialect.

### 4. Unsupported Exhaustion Shapes

The public authoring route must fail closed when the authored exhaustion result
cannot be expressed as:

- scalar override fields for `repeat_until.on_exhausted.outputs`; plus
- ordinary final normalization from carried loop-frame outputs.

That means:

- direct non-scalar exhaustion overrides are not allowed to bypass the loop
  frame;
- the implementation may keep reconstructing non-scalar outputs from carried
  state, but it must reject an authored exhaustion expression that requires a
  non-scalar write directly into `on_exhausted.outputs`.

Use precise diagnostics where possible:

- reuse existing type and purity diagnostics for those classes of error;
- use a lowering-time diagnostic for unsupported exhaustion materialization
  rather than silently dropping authored intent.

### 5. Imported `.orc` Compatibility

This slice does not own imported `.orc` expansion, but the authored exhaustion
surface must be import-agnostic:

- once a local form can elaborate and lower `:on-exhausted`, imported `.orc`
  definitions must reach the same `LoopRecurExpr` shape through the existing
  import/expansion route;
- no review-loop-specific request kind, temporary intrinsic, or bridge-owned
  helper should be required to make imported code reach the exhaustion path.

The implementation proof for this slice should therefore include one imported-
route fixture when the imported `.orc` substrate is available in the checkout.

### 6. Bridge Compatibility During Transition

The review-loop bridge may continue to populate
`LoopRecurExpr.on_exhausted_result_expr` during the transition, but it loses
semantic exclusivity once this slice lands.

Required compatibility rule:

- bridge-owned injection may remain as a temporary caller of the same generic
  field;
- generic authored syntax becomes the primary route;
- later stdlib review-loop work can then remove the bridge without reopening
  loop semantics.

## Proposed Package Boundary

Keep ownership narrow and frontend-local:

```text
orchestrator/workflow_lisp/
  expressions.py
  form_registry.py                 # only if keyword/dispatch metadata needs parity updates
  typecheck_dispatch.py
  expression_traversal.py          # likely unchanged, but part of the owned seam
  lowering/control_loops.py
  phase_stdlib_typecheck.py        # transitional consumer only
```

Planned test and fixture surface:

```text
tests/
  test_workflow_lisp_expressions.py
  test_workflow_lisp_loop_recur.py
  test_workflow_lisp_lowering.py
  test_workflow_lisp_phase_stdlib.py
  test_loader_validation.py
  fixtures/workflow_lisp/valid/loop_recur_on_exhausted_record.orc
  fixtures/workflow_lisp/valid/loop_recur_on_exhausted_union.orc
  fixtures/workflow_lisp/invalid/loop_recur_on_exhausted_impure.orc
  fixtures/workflow_lisp/invalid/loop_recur_on_exhausted_type_mismatch.orc
  fixtures/workflow_lisp/invalid/loop_recur_on_exhausted_non_scalar_override.orc
```

Shared components intentionally reused, not owned here:

- `orchestrator/workflow/` runtime and loader layers
- shared `repeat_until` validation and execution
- state-layout derivation
- source-map persistence schema
- loop-state carrier authoring surfaces introduced by later slices

## Acceptance Conditions

- public `loop/recur` accepts optional authored `:on-exhausted` syntax in the
  same generic route used by ordinary local code;
- authored exhaustion projections populate `LoopRecurExpr.on_exhausted_result_expr`
  directly, without requiring review-loop-specific bridge injection;
- typechecking rejects impure or wrong-typed exhaustion expressions;
- lowering emits `repeat_until.on_exhausted.outputs` only for scalar result
  fields and continues reconstructing non-scalar fields from loop-frame
  outputs;
- omitting `:on-exhausted` preserves existing
  `repeat_until_iterations_exhausted` runtime failure behavior;
- at least one review-loop or imported-loop regression fixture proves the
  bridge is no longer the only producer of exhaustion projection;
- source maps for the authored exhaustion expression and generated loop/result
  steps remain present and deterministic.

## Verification Strategy

Minimum deterministic verification for implementation of this slice:

1. elaboration coverage for public `loop/recur :on-exhausted` syntax;
2. focused loop typecheck coverage for purity and result-type mismatch;
3. lowering coverage proving scalar-only `on_exhausted.outputs` emission and
   loop-frame-backed non-scalar reconstruction;
4. shared-validation coverage showing no-clause exhaustion still fails
   ordinarily while explicit authored exhaustion lowers cleanly;
5. one review-loop regression or imported-route fixture proving the generic
   route exists independently of bridge-only injection.

Use the deterministic commands recorded in
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/2/design-gap-architect/check_commands.json`
when implementing this slice.
