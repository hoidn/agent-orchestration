# Effectful Match Arm Normalization Implementation Architecture

Status: draft
Design gap id: `effectful-match-arm-normalization`
Target design: `docs/design/workflow_lisp_unified_frontend_design.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice adds only the bounded lowering/export support required for
effectful `match` arms in the current Workflow Lisp frontend:

- allow `MatchExpr` arms to lower from effectful branch expressions instead of
  only direct `RecordExpr` projections;
- preserve the current proof-carrying `match` subject and branch-binding model
  already enforced by typechecking;
- project joined branch outputs through the existing branch-terminal and
  output-contract helpers already used by authored `if`;
- preserve deterministic step ids, source maps, hidden inputs, and
  shared-validation authority for provider, command, workflow, phase-stdlib,
  and procedure effects that occur inside one match arm;
- extend private/reusable workflow export checks so they agree with the new
  lowering contract instead of hard-coding record-only arms.

This slice does not implement:

- general support for `match` as an arbitrary effectful binding expression
  outside the currently supported lowering positions;
- new proof rules, new match syntax, or a redesign of `MatchExpr` typing;
- runtime-native branch effects, new adapters, helper scripts, or hidden
  command glue;
- runtime closures, dynamic dispatch, or new runtime value types;
- redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog,
  SourceMap, pointer authority, or provider/command runtime semantics.

The work stays bounded to the selected gap. It is an implementation
architecture for one missing branch-normalization seam, not a broader
effectful-composition rewrite.

## Problem Statement

The current checkout already has most of the semantic substrate required by the
target design:

- `expressions.py` elaborates authored `MatchExpr` with explicit variant names,
  binding names, and branch bodies;
- `typecheck.py` already allows any branch body shape whose type joins across
  all arms, merges branch effects, and installs variant proof facts inside each
  arm;
- `lowering.py` already has a shared branch-lowering path for authored `if`
  through `_lower_conditional_branch_expr(...)`,
  `_conditional_case_outputs(...)`, and `_output_contracts_for_type(...)`;
- loop lowering already supports effectful `match` arms inside
  `_lower_loop_body_expr(...)` by projecting branch terminals back onto the
  loop result contract.

What is missing is the general non-loop `match` lowering seam. Today generic
match lowering is still hard-coded to one narrow shape:

- `_lower_match_expr(...)` rejects any arm body that is not a `RecordExpr`;
- `_lower_match_output_field(...)` only knows how to project return fields from
  a record expression;
- `_match_outputs_are_step_backed(...)` likewise treats exportability as
  record-only, so private/generated workflow analysis disagrees with the target
  design even before real lowering runs.

That leaves a concrete mismatch in the current implementation:

- typechecking already accepts effectful arm bodies when their types join;
- conditional lowering already knows how to lower effectful branches into one
  joined result;
- generic `match` still fails only because its lowering path is narrower than
  the typed frontend semantics.

The selected gap is therefore not a new semantic rule. It is a bounded
normalization problem:

```text
typed MatchExpr
  -> resolve step-backed subject terminal
  -> install branch-local structured refs for the matched variant binding
  -> lower each arm body through the existing branch-terminal path
  -> project joined outputs back onto one authored match step
```

If a match arm body cannot already lower to the existing step-backed output
model, the match remains invalid.

## Design Constraints

The architecture must preserve the governing repo and design invariants:

- `docs/design/workflow_lisp_unified_frontend_design.md`
  - `21. Feature Summary`
  - `22. Current Gap`
  - `23. Design Goal`
  - `24. Expression Categories`
  - `26. Effectful match`
  - `29. Reusable Workflow Boundary Write Roots`
  - `31. Acceptance Gate for Effectful Composition`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `11. Pattern Matching`
  - `14. Workflow Calls`
  - `16. Effect System`
  - `53. match Lowering`
  - `59. Validation Sequence`
  - `63. Variant Proof Validation`
  - `74. Source Map Requirements`
  - `95. Lowering Tests`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/work_instructions.md`

The slice must also preserve the current implementation guardrails:

- shared validation remains authoritative;
- `match` lowering keeps using the existing authored/runtime `match` step
  surface instead of inventing a second branch runtime;
- variant-specific references remain justified by the existing typecheck proof
  path; lowering only projects already-proven refs;
- no provider, command, workflow, state, or resource effect may be hidden by
  branch normalization;
- reusable/private workflow write-root policy remains unchanged;
- the command-adapter contract remains authoritative for any adapter-backed
  command behavior inside a match arm. This slice must not introduce wrapper
  scripts, inline Python/shell glue, or hidden command shims to make branch
  lowering work.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/let-proc-compile-time-local-proc-bindings/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/same-file-call-bindings-for-locally-constructed-records/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/with-phase-composable-expression/implementation_architecture.md`
- Additional historical slice reviewed for coherence:
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/if-conditionals-pure-proven-values/implementation_architecture.md`

### Decisions Reused

- Reuse `MatchExpr`, current variant proof typing, and existing arm type-join
  rules in `typecheck.py`; no new authored match surface is needed.
- Reuse the current `_TerminalResult` model, branch output contracts, projection
  anchors, and source-map origin plumbing in `lowering.py`.
- Reuse `_lower_conditional_branch_expr(...)`,
  `_inline_output_refs_for_expr(...)`, and `_conditional_case_outputs(...)` as
  the authoritative branch-to-terminal normalization path for joined outputs.
- Reuse `_binding_terminal_for_inline_match(...)` and
  `_build_output_step_local_value(...)` as the current way to expose a matched
  structured result as branch-local refs.
- Reuse the with-phase slice rule that composed `WithPhaseExpr` bodies are
  valid only when the wrapped body is already lowerable through the ordinary
  step-backed path.
- Reuse the current authored/runtime `match` step shape and existing branch id
  policy instead of inventing a new branch representation.

### New Decisions In This Slice

- Replace the record-only `_lower_match_expr(...)` arm contract with a generic
  branch-lowering contract that accepts any arm body already supported by the
  shared branch-terminal path.
- Derive joined match outputs from the typed match result and project each arm
  through `_conditional_case_outputs(...)` rather than field-by-field record
  extraction.
- Seed each arm with a structured local value for the variant binding name so
  effectful nested expressions can keep referring to matched variant fields via
  the existing inline/local-value helpers.
- Extend private/reusable workflow exportability checks for `MatchExpr` to
  recurse through branch bodies using the same branch-local binding model
  instead of requiring direct `RecordExpr` returns.
- Keep match subjects step-backed and structured exactly as required today; the
  selected slice widens arm bodies, not subject transport.

### Conflicts Or Revisions

The current implementation assumes that generic `match` branch joins can be
implemented purely by projecting fields from `RecordExpr` arms. That
assumption now conflicts with:

- the accepted unified design, which calls for effectful match arms with
  branch-specific statements and joined results; and
- the current typed frontend, which already accepts effectful arms when their
  result types join.

This slice revises that assumption narrowly:

- `RecordExpr` arms remain valid;
- generic `match` no longer requires `RecordExpr` arms when the arm can lower
  through the existing branch-terminal path;
- runtime match steps, proof authority, write-root policy, and shared
  validation ownership stay unchanged.

No prior slice is revised on shared concepts such as Core Workflow AST,
Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant
proof.

## Ownership Boundaries

This slice owns:

- lowering-time normalization of generic `MatchExpr` arms into branch-local
  statements plus joined outputs;
- branch-local matched-value projection for generic match lowering;
- exportability checks for match arms in private/generated workflow analysis;
- source-mapped diagnostics for non-exportable effectful match arms;
- focused regression tests proving the selected gap is closed.

This slice intentionally does not own:

- `MatchExpr` parsing, exhaustiveness, or proof-rule redesign;
- generic support for `match` as an arbitrary effectful binding source;
- new command adapters, scripts, or runtime-native effects;
- runtime execution semantics for the shared `match` step;
- redesign of shared state layout, bundle schemas, provider execution, or
  pointer authority.

## Proposed Package Boundary

Keep the work inside the existing frontend package and confine code changes to
the current branch-lowering and exportability seam:

```text
orchestrator/workflow_lisp/
  compiler.py       # reusable/private export checks if shared helper extraction is needed
  lowering.py       # generic match-arm branch normalization and projections
  typecheck.py      # existing match typing reused as-is or with narrow diagnostic alignment only

tests/
  test_workflow_lisp_lowering.py
  test_workflow_lisp_procedures.py
  test_workflow_lisp_phase_stdlib.py
  test_workflow_lisp_examples.py
```

Primary responsibilities:

- `lowering.py`
  - replace record-only generic match lowering with a shared branch helper;
  - install branch-local structured refs for each matched variant binding;
  - project joined arm outputs through existing output-contract helpers;
  - keep match step ids, branch ids, anchors, hidden inputs, and source-map
    origins deterministic.
- `compiler.py`
  - reuse the same branch exportability logic when private/generated workflow
    analysis asks whether a match body is step-backed enough to cross a
    reusable boundary.
- `typecheck.py`
  - preserve the current subject-is-union, exhaustive-arm, joined-type, and
    merged-effect rules;
  - only tighten diagnostic alignment if a lowering/exportability message needs
    the typed result available more directly.

No new package, module, or helper script is needed for this slice.

## Current Checkout Facts

Current implementation evidence in `orchestrator/workflow_lisp/lowering.py`
shows the exact seam this slice must change:

- `_lower_match_expr(...)`
  - requires a step-backed subject terminal;
  - rejects any arm whose body is not a `RecordExpr`;
  - projects outputs field-by-field through `_lower_match_output_field(...)`.
- `_lower_conditional_branch_expr(...)`
  - already lowers authored `if` branches from either direct refs or a nested
    lowered terminal;
  - already works with effectful expressions, not just direct records.
- `_conditional_case_outputs(...)`
  - already turns one branch terminal into deterministic output projections
    over a typed output contract.
- `_match_outputs_are_step_backed(...)`
  - still returns true only when every arm body is a `RecordExpr` whose leaves
    resolve to existing refs.
- `_private_workflow_body_exports_step_backed_outputs(...)`
  - already knows how to recurse through `LetStarExpr`, `IfExpr`,
    `ProcedureCallExpr`, `WithPhaseExpr`, and other composed shapes, so match
    is the remaining record-only special case.
- loop lowering in `_lower_loop_body_expr(...)`
  - already supports effectful `MatchExpr` arms by lowering each branch body
    and projecting it back onto loop output contracts.

That means the missing behavior is not branch typing, proof scope, or runtime
match support. It is generic branch lowering for non-loop `match`.

## Internal Lowering Contract

### 1. Shared Match Arm Branch Lowering

Add one generic match-arm helper in `lowering.py` that mirrors the authored
`if` branch path instead of inventing a second branch normalizer.

Recommended shape:

```python
def _lower_match_arm_expr(
    expr: Any,
    *,
    result_type: TypeRef,
    step_name: str,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    ...
```

Contract:

- first try direct output projection through the existing inline-output helper;
- otherwise lower the arm body through `_lower_expression(...)` under a branch
  step prefix;
- return the branch steps plus a terminal whose outputs can be joined back onto
  the enclosing match step.

This helper should either reuse `_lower_conditional_branch_expr(...)` directly
or share its logic through one common helper. The important rule is that
generic `match` and authored `if` must not drift into separate branch-output
models.

### 2. Branch-Local Matched Variant Binding

Each match arm needs one branch-local structured value for the authored binding
name.

Bounded rule:

- resolve the match subject through `_binding_terminal_for_inline_match(...)`;
- build a structured local mapping from the subject terminal output refs with
  `_build_output_step_local_value(...)`;
- install that mapping under `arm.binding_name` only inside the current arm;
- preserve all outer local values unchanged.

This does not create new proof authority. Typechecking already decided which
variant-only fields are legal. Lowering only gives those already-typed field
accesses a structured ref mapping that nested expressions can reuse.

### 3. Joined Output Projection

Generic match lowering must derive outputs from the typed match result, not
only from the workflow return record fields.

Rules:

- compute output contracts from the match result type using the same helper
  family that authored `if` uses;
- project each arm terminal through `_conditional_case_outputs(...)`;
- preserve the current branch-anchor behavior when an arm produces no child
  steps but still needs deterministic branch outputs;
- keep the enclosing authored `match` step as the single join point exposed to
  later lowering and shared validation.

Consequences:

- `RecordExpr` arms remain valid because they can still project inline refs;
- effectful arms become valid when they lower to a terminal exposing the same
  output contract;
- unsupported result shapes still fail under the existing
  `workflow_return_not_exportable` class.

### 4. Exportability Mirror For Reusable Boundaries

Private/generated workflow export checks must mirror the new lowering rule
instead of remaining record-only.

Recommended contract:

- extend `_match_outputs_are_step_backed(...)` so each arm evaluates under a
  branch-local binding mapping for `arm.binding_name`;
- let that helper accept any arm body that the existing step-backed-output
  predicate already understands, including nested `LetStarExpr`, `IfExpr`,
  composed `WithPhaseExpr`, procedure calls, provider/command results, and
  nested `MatchExpr` when those shapes are already step-backed;
- keep subject requirements unchanged: if the match subject does not resolve to
  a structured step-backed value, exportability still fails.

This preserves coherence between compile-time reusable-boundary analysis and
real lowering.

### 5. Diagnostics And Source Maps

Preserve current diagnostic ownership whenever possible:

- keep `workflow_return_not_exportable` as the class for a branch that still
  cannot project the joined output contract;
- replace the current record-only message with authored wording that names the
  failing match arm variant and the underlying exportability cause;
- keep existing subject failures source-mapped to the authored subject
  expression;
- attach step origins to child provider/command/call/phase steps exactly as
  they are today, with the enclosing match arm still visible in the origin note
  chain.

This slice should not add a new provenance system. It should make generic
match branches use the one the frontend already has.

## Test And Acceptance Surface

Implementation should add focused tests proving both the positive and negative
contracts of this slice.

Primary test targets:

- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_examples.py`

Required positive coverage:

- a workflow or procedure where one `match` arm lowers from a nested effectful
  expression instead of a direct `RecordExpr`;
- a branch that reuses matched variant fields through the authored arm binding
  name while still lowering nested effectful work;
- a composed `WithPhaseExpr` or existing phase-stdlib form inside a match arm,
  proving this slice composes with the earlier `with-phase` work instead of
  reintroducing a branch-local special case;
- a reusable/private-workflow path where exportability analysis agrees with
  real lowering for an effectful match arm;
- at least one integration-style compile path using `validate_shared=True` to
  prove the lowered authored `match` still passes through shared validation.

Required negative coverage:

- an arm body that still cannot project the joined result contract fails with
  `workflow_return_not_exportable`;
- a match subject that is not step-backed remains rejected with the existing
  authored diagnostic;
- a private/generated workflow body containing a non-exportable match arm still
  fails deterministically during exportability analysis;
- no helper script, adapter, or runtime effect is introduced to support the
  slice.

Acceptance conditions:

- generic `MatchExpr` lowering accepts effectful arms when each arm can lower
  through the existing branch-terminal path;
- branch effects remain visible and source-mapped;
- joined outputs remain deterministic and compatible with the typed match
  result;
- reusable/private workflow export analysis and real lowering agree about
  whether a match body is exportable;
- unsupported cases still fail explicitly instead of degrading to hidden
  runtime state, ad hoc JSON rewrites, or report parsing.

## Verification Expectations

When this slice is implemented, verification should include:

- focused `pytest` selectors for lowering, procedures, and phase stdlib tests;
- `pytest --collect-only` for any test modules that add or rename tests;
- at least one integration-style `compile_stage3_module(..., validate_shared=True)`
  check proving an effectful match arm lowers end-to-end through the current
  shared validation path;
- no orchestrator run smoke check beyond compilation is required unless the
  chosen test fixture exercises runtime-visible workflow behavior beyond the
  existing authored match surface.
