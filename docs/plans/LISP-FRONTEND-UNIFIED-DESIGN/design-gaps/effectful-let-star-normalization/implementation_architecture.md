# Effectful Let-Star Normalization Implementation Architecture

Status: draft
Design gap id: `effectful-let-star-normalization`
Target design: `docs/design/workflow_lisp_unified_frontend_design.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice adds only the bounded Stage 3 normalization needed so authored
`let*` forms can sequence effectful intermediate bindings through one shared
statement/dataflow contract instead of a growing list of one-off lowering
exceptions:

- normalize each `let*` binding into either:
  - an inline compile-time or pure local value; or
  - a step-backed binding with deterministic generated step ids, terminal refs,
    projected local values, and carried hidden inputs;
- reuse that same binding-normalization helper in both ordinary workflow body
  lowering and the existing loop-body `let*` path so the two surfaces cannot
  drift;
- allow binding expressions that are already lowerable through existing Stage 3
  helpers to participate in sequential composition, including current
  provider/command/stdlib forms, workflow or procedure calls, composed
  `with-phase`, lowered `if`, and lowered `match` results whose subjects are
  already step-backed;
- align private/generated workflow exportability checks with the same
  step-backed binding-local-value contract used by real lowering;
- preserve source maps, hidden-input accumulation, managed write-root
  determinism, and shared-validation authority.

This slice does not implement:

- a new runtime statement kind, runtime closure surface, or dynamic dispatch;
- a redesign of `let*` syntax, typechecking, or compile-time `ProcRef` /
  `bind-proc` behavior;
- general support for every possible expression as a binding source if that
  expression still lacks a valid Stage 3 lowering contract;
- new command adapters, helper scripts, inline shell/Python glue, or
  runtime-native promotion;
- redesign of shared Core Workflow AST, Semantic Workflow IR, Executable IR,
  TypeCatalog, SourceMap, pointer authority, or provider/command runtime
  semantics.

The work stays bounded to the selected design gap. It is an implementation
architecture for one shared binding-normalization seam, not a broad rewrite of
effectful composition.

## Problem Statement

The current checkout already has most of the substrate that Section 25 of the
unified design expects:

- `typecheck.py` accepts sequential `let*` bindings, typechecks each binding in
  order, merges binding effect summaries, and then types the body under the
  extended local environment;
- `lowering.py` already knows how to lower many effectful expression families
  to `_TerminalResult` values with output refs, hidden inputs, source maps, and
  deterministic step ids;
- prior slices already added bounded support for:
  - effectful `match` arms;
  - composed `with-phase`;
  - same-file calls from locally constructed records;
  - deterministic reusable-boundary write-root bindings.

What is still missing is the shared sequential-binding normalization layer.
Today the lowering seam remains fragmented:

- `_lower_let_star(...)` contains one manual split between inline bindings and
  effectful bindings;
- `_lower_loop_body_expr(...)` reimplements a similar split for its own nested
  `let*` path;
- `_binding_type_for_expr(...)` hard-codes a closed list of effectful binding
  node classes and still falls back to the generic diagnostic
  `Stage 3 lowering does not support let* binding ...`;
- `_lower_expression(...)` still has no generic entrypoint for `MatchExpr`, so
  a composed `match` result can lower in some positions but not as a binding
  source;
- `_private_workflow_binding_local_value(...)` uses a separate exportability
  approximation that can drift from the real lowering behavior.

That leaves a concrete target-delta mismatch:

- the frontend already models `let*` as ordered dataflow;
- several expression families already lower successfully when they appear as
  outer bodies or branch bodies;
- sequential binding still depends on ad hoc allowlists and duplicated local
  projection logic.

The selected gap is therefore not a new semantic rule. It is a bounded
normalization problem:

```text
typed let* bindings
  -> classify inline vs step-backed binding
  -> derive binding result type through one shared helper
  -> lower step-backed bindings to explicit ordered statements
  -> project deterministic local values for later bindings
  -> reuse the same contract for reusable-boundary export checks
```

If a binding expression cannot already lower to the existing Stage 3
step-backed model with deterministic write roots and source maps, the binding
must still reject.

## Design Constraints

The architecture must preserve the governing repo and design invariants:

- `docs/design/workflow_lisp_unified_frontend_design.md`
  - `21. Feature Summary`
  - `22. Current Gap`
  - `23. Design Goal`
  - `24. Expression Categories`
  - `25. Effectful let*`
  - `29. Reusable Workflow Boundary Write Roots`
  - `30. Standard-Library Lowering Completion`
  - `31. Acceptance Gate for Effectful Composition`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `10. Sequential Binding: let*`
  - `11. Pattern Matching`
  - `14. Workflow Calls`
  - `16. Effect System`
  - `57. review-revise-loop Lowering`
  - `59. Validation Sequence`
  - `74. Source Map Requirements`
  - `95. Lowering Tests`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/work_instructions.md`

The slice must also preserve the current implementation guardrails:

- shared validation remains authoritative;
- pure and compile-time-only values such as `proc-ref`, `bind-proc`, and local
  compile-time procedure metadata remain erased before runtime artifacts;
- each lowered effectful binding must expose deterministic step ids derived
  from authored lexical order and binding names, not from unstable runtime
  state;
- generated write roots remain governed by the reusable-boundary write-root
  policy; this slice must not invent a second allocation policy;
- no provider, command, workflow, state, or resource effect may be hidden by
  binding normalization;
- the command-adapter contract remains authoritative for any `command-result`
  or adapter-backed binding expression. This slice must not introduce wrapper
  scripts, inline command glue, or hidden helper commands to make `let*`
  lowering work.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/effectful-match-arm-normalization/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/executable-ir-component-contract/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/let-proc-compile-time-local-proc-bindings/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/reusable-workflow-boundary-write-root-policy/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/same-file-call-bindings-for-locally-constructed-records/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/with-phase-composable-expression/implementation_architecture.md`

### Decisions Reused

- Reuse the current authored surfaces: `LetStarExpr`, `MatchExpr`,
  `WithPhaseExpr`, `CallExpr`, `ProcedureCallExpr`, stdlib result expressions,
  and compile-time `ProcRef` / `bind-proc` bindings.
- Reuse the `_TerminalResult` model, hidden-input accumulation, step-origin
  tracking, and output-ref projection already used by provider, command,
  conditional, match-arm, loop, and phase lowering.
- Reuse the effectful match-arm slice's branch-lowering helpers
  `_lower_conditional_branch_expr(...)` and `_conditional_case_outputs(...)`
  instead of inventing a second branch model for `match` results in binding
  position.
- Reuse the composed with-phase slice's rule that `WithPhaseExpr` is
  semantically transparent around an already-lowerable body and must not become
  a wrapper runtime step.
- Reuse the same-file call slice's rule that record-valued locals remain local
  structured projections until a runtime call boundary flattens them into
  ordinary ref leaves.
- Reuse the reusable-boundary write-root slice's caller-owned managed input
  policy unchanged.
- Reuse the executable-IR component-contract slice's constraint that this work
  only changes validated lowered step structure, not executable node kinds or
  runtime value strata.

### New Decisions In This Slice

- Introduce one lowering-only binding-normalization contract that classifies a
  `let*` binding as inline or step-backed and returns the exact local value,
  terminal, and emitted steps for later bindings.
- Generalize binding-position `match` lowering so a `MatchExpr` can be lowered
  when its subject already resolves to step-backed local refs, rather than only
  when `match` appears in one special body position immediately after a
  binding.
- Replace the closed `_binding_type_for_expr(...)` allowlist with a shared
  binding-result-type helper that can recurse through already-supported
  composed expressions instead of falling back to generic node-class
  rejections.
- Make ordinary `let*`, loop-body `let*`, and private/generated workflow
  exportability checks consume the same step-backed binding-local-value rules.
- Keep compile-time-only bindings inline only; the shared helper must reject
  any path that would serialize a procedure value or other compile-time author
  value into runtime state.

### Conflicts Or Revisions

The current implementation assumes that supporting a new effectful binding form
is mainly a matter of adding another case to `_binding_type_for_expr(...)` and
maybe another special case to `_lower_effectful_binding_expr(...)`. That
assumption now conflicts with the unified design and with the already-landed
composition slices, because it leaves `let*`, loop lowering, and
private-workflow exportability on three separate models.

This slice revises that assumption narrowly:

- expression-family-specific lowering stays where it already lives;
- `let*` normalization becomes the single place that sequences bindings and
  projects later local values;
- exportability checks mirror the same binding contract instead of maintaining
  a weaker approximation.

No prior slice is revised on shared concepts such as Core Workflow AST,
Semantic Workflow IR, Executable IR, TypeCatalog, SourceMap, pointer authority,
or variant proof.

## Ownership Boundaries

This slice owns:

- lowering-time normalization of sequential `let*` bindings into inline or
  step-backed binding results;
- deterministic binding step-name allocation and hidden-input accumulation for
  sequential effectful bindings;
- binding-position `match` lowering when the match subject already resolves to
  step-backed local refs;
- parity between ordinary `let*`, loop-body `let*`, and private/generated
  workflow exportability checks for supported binding shapes;
- source-mapped diagnostics for non-exportable composed bindings;
- focused regression tests for the selected binding-normalization seam.

This slice intentionally does not own:

- `let*` parsing or typechecking redesign;
- new proof rules, new `match` syntax, or a general runtime `match` redesign;
- new command adapters, scripts, legacy adapters, or runtime-native effects;
- reusable-boundary write-root allocation policy;
- shared runtime execution semantics, provider execution, command execution, or
  state persistence;
- runtime closures, dynamic dispatch, or transport of compile-time callable
  values.

## Proposed Package Boundary

Keep the work inside the existing frontend lowering package and confine code
changes to the current binding/export seam:

```text
orchestrator/workflow_lisp/
  lowering.py       # shared let* binding normalization and exportability mirror

tests/
  test_workflow_lisp_lowering.py
  test_workflow_lisp_loop_recur.py
  test_workflow_lisp_procedures.py
  test_workflow_lisp_examples.py
```

Primary responsibilities:

- `lowering.py`
  - add one shared binding-normalization helper for sequential lowering;
  - reuse or refactor existing type-resolution helpers so binding result types
    are derived through one recursive contract;
  - add a binding-position `match` lowering entrypoint that reuses the existing
    effectful-arm branch helper and step-backed subject projection;
  - reuse the same local-value projection rules in ordinary lowering and in
    private/generated workflow exportability analysis;
  - preserve current origin-note, hidden-input, and step-id behavior for
    emitted steps.
- `tests/*`
  - add focused coverage for sequential effectful bindings, mixed pure/effectful
    ordering, loop-body parity, private-workflow exportability, and binding-site
    diagnostic remapping.

No new package, module, command adapter, or helper script is needed for this
slice.

## Current Checkout Facts

Current implementation evidence in `orchestrator/workflow_lisp/lowering.py`
shows the exact seam this slice must change:

- `_lower_let_star(...)`
  - already lowers simple inline bindings without emitting steps;
  - already lowers some effectful bindings through `_lower_effectful_binding_expr(...)`;
  - still contains its own binding classification, type lookup, local-value
    projection, and hidden-input merge logic.
- `_lower_loop_body_expr(...)`
  - reimplements a second binding split for nested `let*` inside loop bodies;
  - already proves that loop semantics want the same ordered-binding model.
- `_binding_type_for_expr(...)`
  - unwraps `WithPhaseExpr`, handles several stdlib and call surfaces, and
    resolves `IfExpr` / `LoopRecurExpr`;
  - still rejects unsupported composed bindings generically and does not serve
    as the single binding-type authority.
- `_resolve_lowering_expr_type(...)`
  - already understands structural result typing for names, field access,
    records, `if`, `match`, nested `let*`, loop bodies, and `with-phase`;
  - does not by itself cover every step-backed effectful surface, so the
    checkout currently uses two partial type-resolution systems.
- `_lower_effectful_binding_expr(...)`
  - already centralizes the "step-backed binding becomes `_TerminalResult`"
    seam for some expressions;
  - is not yet the full normalization contract because it assumes the caller
    already knows the binding is supported and already knows the binding type.
- `_lower_expression(...)`
  - lowers most effectful expression families;
  - still has no generic `MatchExpr` dispatch even though effectful match-arm
    lowering exists elsewhere.
- `_private_workflow_binding_local_value(...)` and
  `_private_workflow_body_exports_step_backed_outputs(...)`
  - already mirror some binding/export behavior for reusable procedures;
  - use a narrower approximation than the real lowering path.

That means the missing behavior is not ordinary sequential semantics. It is
the shared normalization layer that makes supported effectful binding forms
flow through one contract everywhere the frontend sequences bindings.

## Internal Lowering Contract

### 1. Shared Normalized Binding Result

Add one lowering-only helper and result shape, conceptually:

```text
normalize_binding(binding_name, binding_expr, context, local_values, step_prefix_base)
  -> binding_type
  -> local_value
  -> emitted_steps
  -> binding_terminal?    # present for step-backed bindings
  -> hidden_inputs
```

Rules:

- inline and compile-time bindings emit no steps and may return only a local
  value;
- step-backed bindings must return a resolved `binding_type`, emitted steps,
  and a `_TerminalResult` whose output refs become the authoritative local
  binding value for later expressions;
- step prefixes remain deterministic:
  `"<enclosing_step_prefix>__<binding_name>"`;
- the helper is lowering-only; it must not introduce a new runtime node or a
  second validation path.

### 2. One Binding Result-Type Helper

Replace the closed binding-type allowlist with one recursive helper that
derives the binding result type for every binding shape this slice supports.

Expected resolution order:

- inline values:
  - names, field access, literals, record literals, `proc-ref`, `bind-proc`
    through the existing inline helpers;
- direct step-backed surfaces:
  - `provider-result`, `command-result`, `run-provider-phase`,
    `produce-one-of`, `review-revise-loop`, `resume-or-start`,
    `resource-transition`, `finalize-selected-item`, `backlog-drain`, ordinary
    workflow calls, and procedure calls through existing signature/contract
    resolution;
- transparent wrappers:
  - `WithPhaseExpr` resolves to its body type;
- composed control/dataflow:
  - `IfExpr` resolves by joined branch type;
  - `MatchExpr` resolves by joined arm type under the existing branch-local
    proof typing;
  - nested `LetStarExpr` or `LoopRecurExpr` resolve only when the result type
    can be derived through the same helper and current Stage 3 rules.

If the helper cannot derive a result type without inventing new runtime
behavior, the binding remains rejected.

### 3. Binding-Position Match Lowering

Generalize the existing match lowering seam so a `MatchExpr` can act as a
binding expression when its subject already lowers from structured local refs.

Conceptual contract:

```text
lower_match_binding(match_expr, result_type, context, local_values, step_name_prefix)
  -> resolve match subject terminal from local_values
  -> lower each arm body through existing branch helper
  -> project joined outputs onto one deterministic match step
  -> expose binding local value from the match terminal
```

Rules:

- the match subject must resolve to step-backed structured refs through the
  existing `_binding_terminal_for_inline_match(...)` path;
- branch-local proof and field availability remain exactly as already enforced
  by typechecking and the effectful match-arm slice;
- the emitted match step keeps deterministic case names and source maps based
  on the enclosing binding step prefix;
- no special "match binding runtime value" is introduced; the local binding
  value is just the match terminal's projected outputs.

### 4. Ordered Binding Sequencing

`_lower_let_star(...)` and the loop-body `let*` path should both become simple
consumers of the shared normalized-binding helper.

For each binding, in order:

1. normalize the binding;
2. append any emitted steps;
3. extend local values with the normalized local binding value;
4. extend local type bindings with the resolved binding type;
5. carry hidden inputs forward;
6. lower the remaining body under the extended environment.

This preserves the target design rules:

- binding order is sequential;
- later bindings may depend on earlier outputs;
- pure bindings may remain expression-level;
- effectful bindings acquire stable generated statement ids;
- hidden inputs and managed write roots stay deterministic.

### 5. Private-Workflow Exportability Mirror

The reusable/private workflow exportability path must rely on the same
binding-local-value rules as real lowering.

That means `_private_workflow_binding_local_value(...)` should stop being a
separate approximation over `returns_type_name` alone and instead mirror the
same supported binding families:

- transparent `WithPhaseExpr`;
- binding-position `MatchExpr` when its subject is already step-backed;
- stdlib result surfaces with declared return types;
- workflow and non-recursive private procedure calls whose bodies are already
  step-backed under current rules.

This does not require exportability to execute real lowering. It requires the
same acceptance boundary and the same local projection shape.

### 6. Diagnostics And Source Maps

Binding-normalization failures should surface the real lowering cause while
remapping the top diagnostic to the authored binding site whenever a composed
binding wrapper is involved.

Required behavior:

- prefer the existing specific diagnostic when one already exists;
- when remapping a composed binding wrapper, mention the authored surface
  rather than only the raw node class;
- keep spans and form paths anchored to the authored binding expression, not to
  a synthetic helper name;
- generated step names and hidden inputs must still record provenance back to
  the binding site and enclosing `let*`.

Examples of expected failure surfaces:

- non-step-backed `match` subject in binding position;
- unsupported composed binding result type;
- compile-time-only value escaping into a runtime binding;
- non-exportable reusable workflow binding body under the mirrored export path.

## Test And Acceptance Surface

Focused implementation tests for this slice should cover:

- positive sequential lowering for:
  - a mixed `let*` with pure binding, provider or command binding, then a
    second effectful binding that consumes the first;
  - a `let*` binding whose expression is a `match` over an already step-backed
    earlier binding;
  - a loop-body `let*` using the same supported effectful binding family and
    producing the same local projection shape;
  - a private-workflow or reusable-procedure body whose `let*` bindings are
    accepted by both exportability checks and real lowering;
  - deterministic generated binding step names and source-map lineage.
- negative cases for:
  - a `match` binding whose subject is not step-backed;
  - a composed binding whose result type cannot be resolved through the shared
    binding-result helper;
  - a binding that would transport a compile-time-only procedure value into a
    runtime result;
  - a non-exportable binding body whose diagnostic remaps to the binding site
    instead of surfacing only a raw helper failure.

An implementation pass should also add one integration-style compile example or
fixture that exercises a realistic ordered effectful binding stack, such as:

- provider result;
- branch-local match result;
- same-file call or reviewed phase step consuming the bound result.

That example should compile through Stage 3 and shared validation without
weakening the current reusable-boundary or command-boundary rules.

## Verification Expectations

When this architecture is implemented, verification should include at least:

- narrow `pytest` selectors for the new lowering tests;
- `pytest --collect-only` if new test files or selectors are introduced;
- at least one example or integration compile check that exercises sequential
  effectful bindings through real Workflow Lisp compilation;
- explicit evidence that reusable-boundary write-root behavior and command
  boundary contracts remain unchanged.

No implementation should claim completion based on inspection alone. The
selected gap is closed only when sequential effectful bindings lower through
one shared statement/dataflow model and the same model is reflected in
reusable-boundary exportability checks.
