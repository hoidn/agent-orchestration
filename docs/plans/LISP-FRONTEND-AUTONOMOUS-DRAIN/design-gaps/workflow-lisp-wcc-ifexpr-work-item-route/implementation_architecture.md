# Workflow Lisp WCC IfExpr Work-Item Route Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-wcc-ifexpr-work-item-route`
Target design: `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected post-WCC compiler-lane gap:

- make authored `IfExpr` lower through the WCC schema-2 route instead of the
  legacy schema-1 conditional lowerer;
- unblock the real
  `lisp_frontend_design_delta/work_item::run-work-item` parent-callable
  candidate from its current `wcc_lowering_route_unsupported` diagnostic for
  unsupported `IfExpr`;
- preserve the accepted WCC route: typed Workflow Lisp elaborates into WCC,
  normalizes through ANF, receives scope/effect/proof analysis, and
  defunctionalizes into the existing validated flat workflow model;
- keep `if` proof-neutral: conditions do not create variant proof and branch
  bodies inherit only the proof scope already available at the authored form;
- add focused WCC characterization, build-artifact, source-map, shared
  validation, and work-item feasibility coverage.

Out of scope for this slice:

- adding a general predicate language beyond the existing pure Bool condition
  shapes already admitted by the frontend;
- making `if` a variant-proof-producing form;
- private executable context, hidden reusable-call binding, `PhaseCtx`
  bootstrap, or public/private boundary rehabilitation beyond exposing the next
  post-`IfExpr` blocker;
- selector typed projection, certified adapter declarations, or
  resource-transition ownership;
- parent backlog-drain composition or promotion eligibility;
- replacing or weakening the existing command-adapter contract for work-item
  helper commands already present in the fixtures;
- changing shared runtime `if` execution semantics, Core Workflow AST
  authority, Semantic IR authority, pointer authority, TypeCatalog, or
  source-map ownership.

The success condition is narrow: the real work-item route must advance past the
WCC `IfExpr` unsupported-node failure. Any later failure must be another
documented tranche diagnostic, not an old private-workflow `IfExpr` export
blocker hidden under a different name.

## Problem Statement

The current checkout already implements authored Workflow Lisp `if` for the
legacy lowering route:

- `orchestrator/workflow_lisp/expressions.py` defines `IfExpr`;
- `orchestrator/workflow_lisp/conditionals.py` classifies pure Bool literal or
  Bool-ref conditions and renders shared typed predicates;
- `orchestrator/workflow_lisp/typecheck_dispatch.py` enforces Bool type,
  condition purity, projectability, branch type equality, and proof-neutral
  behavior;
- `orchestrator/workflow_lisp/lowering/control_dispatch.py` lowers legacy
  `IfExpr` into the shared authored `if` step shape;
- existing diagnostics and fixtures cover invalid condition type, effectful
  condition, and non-projectable condition.

The gap is below that surface. WCC schema 2 is now the default for migrated
post-foundation composition, but `orchestrator/workflow_lisp/wcc/elaborate.py`
does not elaborate `IfExpr`. The real design-delta work-item runtime fixture
uses `if` in three parent-callable places:

- `finalize-approved-review-state`, checking
  `terminal.implementation_review_exhausted`;
- `finalize-approved-nonblocked`, checking
  `terminal.plan_review_exhausted`;
- the `run-work-item` approved plan arm, checking
  `terminal.implementation_blocked`.

Fresh verification before this draft:

```bash
pytest -q tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_work_item_candidate_is_blocked_by_phase_family_boundary
```

Result: `1 passed in 0.47s`. The test passes because the route is currently
expected to fail with `wcc_lowering_route_unsupported` for unsupported
`IfExpr` in `lisp_frontend_design_delta/work_item::run-work-item`.

## Design Constraints

The implementation must stay coherent with:

- `docs/index.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/post_wcc_reconciliation_index.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  - Tranche 1, nested structured-control composition;
  - Tranche 3A, phase-family boundary rehabilitation prerequisite;
  - UAF-04 inactive-branch guard inheritance;
  - UAF-05 WCC `IfExpr` as immediate work-item blocker;
- `docs/design/workflow_lisp_core_calculus_middle_end.md`
  - WCC schema 2 as default for migrated new compiles;
  - one WCC route rather than helper-hoisting or bespoke lowerers;
  - ANF normalization, scope/effect/proof analysis, and defunctionalization;
  - WCC metadata remaining compile-time only;
- `docs/design/workflow_lisp_frontend_specification.md`
  - Section 12, `if` only for pure or already-proven values;
  - Section 16, effect transparency;
  - Section 63, general `if` does not create variant proof;
  - Section 74, source-map requirements;
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/if-conditionals-pure-proven-values/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-child-returned-variant-work-item-prerequisite/implementation_architecture.md`
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_wcc_characterization.py`
- `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/work_item.orc`

`docs/design/workflow_command_adapter_contract.md` is authoritative because the
work-item route contains command-backed procedures. This slice may preserve
those existing certified or declared command boundaries in tests, but it must
not introduce new inline Python/shell semantics, report parsing, pointer-as-
state, or hidden state/resource rewrites to make the `IfExpr` route pass.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The generated architecture index was reviewed. Directly constraining slices:

- `core-workflow-ast-shared-contract`
- `defproc-procedural-substrate`
- `defun-pure-helper-surface`
- `frontend-validation-diagnostics-pipeline`
- `if-conditionals-pure-proven-values`
- `loop-recur-bounded-loops`
- `source-map-runtime-lineage`
- `typed-expressions-variant-proof`
- `workflow-core-ast-lowering-structured-results`
- `workflow-lisp-expression-traversal-prerequisite`
- `workflow-lisp-imported-child-returned-variant-work-item-prerequisite`
- `workflow-lisp-lowering-core-family-decomposition`
- `workflow-lisp-promoted-entry-hidden-reusable-call-binding`
- `workflow-lisp-state-layout-path-allocator-foundation`
- `workflow-lisp-typecheck-family-decomposition`

The full index-listed corpus was also scanned for scope, ownership, and
conflict sections to avoid redefining shared concepts such as spans,
diagnostics, Core Workflow AST, Semantic Workflow IR, TypeCatalog, SourceMap,
pointer authority, or variant proof.

### Decisions Reused

- Reuse the authored `if` typechecking contract from the
  `if-conditionals-pure-proven-values` slice: condition is exact `Bool`, pure,
  and projectable; branches have the same result type; `if` creates no proof.
- Reuse the legacy conditional lowerer's shared output shape as the runtime
  target: one authored `if` step with `then` and `else` branch blocks, branch
  outputs, and projection anchors when a branch has no steps.
- Reuse WCC's route discipline from the core-calculus middle-end: new
  post-foundation compiler-lane behavior extends WCC and must not add another
  helper-hoisting path.
- Reuse WCC effect rows, source frames, proof contexts, scope ids, and
  defunctionalized provenance rather than inventing a parallel conditional
  provenance channel.
- Reuse the imported-child returned-variant prerequisite's outcome: the work
  item no longer blocks on union-return ambiguity, so this slice must not
  "fix" `IfExpr` by renaming result variants or weakening returned-variant
  normalization.
- Reuse the expression traversal slice's fail-closed rule: newly introduced or
  reclassified expression containers must be visited by dependency, extern,
  specialization, typecheck, WCC, lowering, and source-map walkers.

### New Decisions In This Slice

- Add one WCC internal control body for predicate conditionals, named here
  `WccIf`, that carries:
  - condition value and condition shape;
  - then and else WCC bodies;
  - result type, effect row, proof context, source frame, phase scope, and
    scope id through ordinary `WccNodeMetadata`.
- Treat `WccIf` as compile-time control only. It is not a runtime primitive and
  must defunctionalize to the existing shared authored `if` step.
- Elaborate `IfExpr` to `WccIf` after frontend typechecking has already proven
  the condition is pure/projectable and both branches have the same result
  type.
- Extend WCC ANF normalization, scope/effect/proof analysis, and
  defunctionalization to traverse `WccIf` branch bodies.
- Preserve proof neutrality by copying the inherited proof context into both
  branch bodies and never adding a proof token from the condition.
- Keep unsupported lower-level `IfExpr` shapes as frontend/typecheck
  diagnostics, not post-lowering `wcc_lowering_route_unsupported`, whenever
  the existing frontend can diagnose them.

### Conflicts Or Revisions

The accepted WCC design intentionally kept the calculus small and did not list
an `if` construct. This slice revises that implementation boundary narrowly:

- WCC needs one predicate-control body to represent an already-accepted
  frontend surface without abusing union `case` or hiding branch effects in an
  opaque value.
- The addition does not create a new runtime authority, does not add first-
  class control values, and does not bypass shared validation.
- If the implementation lands, the WCC design document should receive a small
  follow-up note listing `WccIf` as a predicate-control construct that
  defunctionalizes to the existing shared `if`.

No other shared concepts are revised.

## Ownership Boundaries

This slice owns:

- `orchestrator/workflow_lisp/wcc/model.py` additions for the WCC predicate
  conditional body;
- `orchestrator/workflow_lisp/wcc/elaborate.py` support for `IfExpr` in body
  position, non-tail binding position, loop body position, and type inference;
- `orchestrator/workflow_lisp/wcc/anf.py` traversal and atomization of
  `WccIf` condition values and branch bodies;
- `orchestrator/workflow_lisp/wcc/analysis.py` branch-scope, proof-context,
  and effect-summary traversal for `WccIf`;
- `orchestrator/workflow_lisp/wcc/defunctionalize.py` conversion from `WccIf`
  to the shared authored `if` step shape;
- WCC characterization fixtures and tests for simple, nested, loop-body, and
  work-item `IfExpr` routes;
- test updates that convert the current expected `wcc_lowering_route_unsupported`
  work-item assertions into "advanced past IfExpr" assertions.

This slice intentionally does not own:

- condition parsing or frontend `IfExpr` admission already implemented by the
  prior conditional slice;
- the command-boundary declarations used by work-item helper procedures;
- private context or hidden reusable-call binding;
- typed projection, selector bundle publication, adapter declaration
  ergonomics, resource-transition ownership, or parent-drain parity;
- shared runtime `if` semantics, provider/command execution, path safety, or
  resume schema migration for already-started schema-1 runs.

## Current Checkout Facts

- `IfExpr` is exported from `orchestrator/workflow_lisp/__init__.py` and is
  handled by typecheck and legacy lowering.
- WCC elaboration imports many expression nodes but not `IfExpr`.
- WCC `_elaborate_expr_to_body`, `_elaborate_expr_to_value`, and
  `_infer_expr_type` raise unsupported-node errors for `IfExpr`.
- `WccBody` currently covers `WccLet`, `WccCase`, `WccJoin`, `WccJump`,
  loop bodies, `WccRecJoin`, and `WccHalt`.
- WCC defunctionalization already has the reusable pieces needed for branch
  output projection:
  `_conditional_case_outputs`, `_conditional_output_refs`,
  `_build_match_projection_anchor_step`, `_lower_wcc_terminal_export`, and the
  legacy conditional output-contract derivation path.
- Tests already characterize the current gap:
  - `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
    expects the work-item candidate and parent-call fixture to fail on WCC
    `IfExpr`;
  - `tests/test_workflow_lisp_build_artifacts.py` expects build-artifact
    compilation of the work-item surface to fail on WCC `IfExpr`;
  - WCC characterization tests cover M1-M4 and the implementation-phase nested
    fixture, but not an authored `IfExpr` WCC route.

## Proposed Architecture

### 1. WCC Model

Add:

```text
WccIf(
  metadata: WccNodeMetadata,
  condition: WccValue,
  condition_shape: ConditionShape,
  then_body: WccBody,
  else_body: WccBody,
)
```

`metadata.type_ref` is the conditional result type. `metadata.effect_summary`
is the union of branch effects; the condition remains effect-free by the
existing typechecker rule. `metadata.proof_context` is inherited from the
authoring site and does not change.

Add `WccIf` to `WccBody`. Do not add it to `WccValue`, provider payloads,
command payloads, runtime outputs, or serialized workflow state.

### 2. Elaboration

Import `IfExpr` into `wcc/elaborate.py` and add `_elaborate_if_to_body(...)`.

Elaboration steps:

1. Infer the `IfExpr` result type using the already typechecked branch type.
2. Elaborate `condition_expr` through `_elaborate_expr_to_value`.
3. Classify the condition with `classify_condition_expr(...)` using exact
   `Bool`; if this fails, surface the existing `if_condition_*` diagnostics.
4. Elaborate `then_expr` and `else_expr` in child scopes:
   `if-then` and `if-else`.
5. Build `WccIf` with the inherited phase scope and source frame.

Special handling:

- In `let*`, an `IfExpr` binding is a control binding. Reuse the existing
  `_elaborate_control_binding_to_body(...)` path so non-tail conditionals flow
  through a join parameter rather than an implicit branch projection.
- In loop bodies, `IfExpr` must elaborate under the current loop target. A
  branch may end in `continue`, `done`, another control node, or a value body
  accepted by the existing loop result rules.
- Do not allow WCC to accept an `IfExpr` that the frontend typechecker would
  reject. A post-typecheck unsupported `IfExpr` is a compiler defect.

### 3. ANF Normalization

Extend `normalize_wcc_body_to_anf(...)`:

- normalize the condition value and atomize it when needed;
- normalize both branch bodies recursively;
- preserve branch source frames and metadata;
- keep `condition_shape` unchanged because it is the frontend-checked lowering
  contract, not a value subject to ANF rewrites.

Branch values that flow out of non-tail `if` already go through join
parameters because elaboration uses the control-binding route. ANF should not
invent a second projection mechanism.

### 4. Scope, Effect, And Proof Analysis

Extend `analyze_wcc_body(...)` to walk `WccIf`:

- record child branch scopes for diagnostics/source maps if the existing
  `WccArmScope` structure is too variant-specific, either introduce a small
  `WccConditionalScope` record or reuse the broader source-map metadata
  without pretending `then` and `else` are variants;
- recurse into both branch bodies;
- union branch effect rows into the surrounding effect summary;
- preserve inherited proof context in both branches;
- do not record any new proof emitted by the condition.

The analyzer must still catch unsupported nested control as a WCC compiler
defect if a typechecked WCC body cannot be analyzed.

### 5. Defunctionalization

Add `_defunctionalize_if(...)` beside `_defunctionalize_case(...)`.

Lowering shape:

```yaml
name: <context.step_name_prefix>
id: <normalized id>
if: <rendered predicate>
then:
  id: <step>__then
  outputs: <then branch outputs>
  steps: <then branch steps or projection anchor>
else:
  id: <step>__else
  outputs: <else branch outputs>
  steps: <else branch steps or projection anchor>
```

Implementation details:

- render the predicate with the existing `render_condition_predicate(...)`,
  using WCC local values after resolving the WCC condition value back into the
  equivalent frontend expression/value;
- lower branch bodies with branch step prefixes `<step>__then` and
  `<step>__else`;
- use `_conditional_case_outputs(...)` and `_conditional_output_refs(...)` for
  result projection, the same as match/legacy conditional lowering;
- when a branch emits no steps, emit the existing projection anchor step with a
  branch role of `then` or `else`;
- merge hidden inputs from both branches;
- record step origins for the `if` step and branch/projection anchors;
- preserve branch activation: branch-local steps stay inside the shared `then`
  or `else` block. If nested control must be hoisted by existing WCC match
  behavior, the hoisted step must inherit the parent conditional predicate as
  well as any nested case guard before this slice claims UAF-04 coverage.

The immediate work-item fixture should not require new command, provider, or
resource semantics; branch bodies lower through existing effect emitters.

### 6. Source Maps And Build Artifacts

Source-map and build-artifact output must not expose WCC route names or
`wcc-node` internals as public workflow surfaces. The following provenance must
remain visible through existing projections:

- authored `IfExpr` span and form path;
- generated shared `if` step;
- generated `then`/`else` branch block ids;
- projection anchors;
- child branch effect steps;
- any private workflow/procedure call produced inside either branch.

The build-artifact tests that currently expect the work-item route to fail on
WCC `IfExpr` should become evidence that runtime context inputs remain
internal after the route compiles, or else should fail on the next documented
post-`IfExpr` tranche diagnostic.

### 7. Diagnostics

No new author-facing conditional diagnostics are expected. Reuse:

- `if_condition_not_bool`;
- `if_condition_has_effect`;
- `if_condition_not_projectable`;
- `type_mismatch`;
- `variant_ref_unproved`;
- `variant_ref_wrong_variant`.

Keep `wcc_lowering_route_unsupported` only for genuinely unimplemented WCC
route restrictions unrelated to the accepted `IfExpr` surface. After this
slice lands, `unsupported IfExpr` must not appear for the real work-item route.

If branch hoisting cannot preserve activation guards, fail with an explicit WCC
compiler diagnostic before emitting invalid Core AST. Do not silently accept
branch-local leakage.

## Implementation Sequence

1. Add `WccIf` to `wcc/model.py` and update all WCC body unions/import lists.
2. Add WCC elaboration for `IfExpr`, including `_infer_expr_type` support and
   non-tail/control-binding handling through existing join machinery.
3. Extend ANF and analysis traversals to cover `WccIf` fail-closed.
4. Add defunctionalization to shared authored `if` steps using existing branch
   output projection helpers.
5. Add one minimal WCC characterization fixture for `IfExpr` in tail position
   and one for `IfExpr` nested under a `match` branch.
6. Add or update WCC loop/body coverage only if implementation touches loop
   body conversion helpers.
7. Convert work-item feasibility/build-artifact tests from expected
   unsupported `IfExpr` to "advanced past IfExpr" assertions.
8. Run focused tests first, then the WCC characterization and design-delta
   feasibility bands recorded in the check-command file.

## Test Strategy

Required focused tests:

- WCC characterization: pure Bool-ref `IfExpr` compiles under default WCC
  schema 2 and emits a shared `if` step.
- WCC nested control: `IfExpr` inside a `match` arm preserves the parent match
  proof for field access and does not expose branch-local refs outside the
  branch.
- WCC proof negative: `if` condition still does not prove a union variant.
- WCC branch effects: branch command/provider/workflow effects are visible in
  effect summaries and lowered branch steps.
- Work-item compile: the real design-delta work-item candidate no longer
  reports unsupported `IfExpr`; any remaining failure is a documented next
  tranche blocker.
- Parent-call fixture: the parent-call work-item fixture no longer reports
  unsupported `IfExpr`.
- Build artifacts: runtime context inputs remain internal, and command-boundary
  lineage still records the family adapters after the route advances past
  `IfExpr`.
- Inactive branch smoke or structural check: the inactive `if` branch does not
  execute branch-local effect steps in a controlled fake-provider run or
  equivalent shared-validation artifact.

Negative tests must keep the existing invalid conditional fixtures passing.

## Acceptance Conditions

- `IfExpr` is a supported WCC schema-2 control node and no longer routes to the
  legacy conditional lowerer for migrated WCC compiles.
- The real design-delta work-item candidate advances past the current
  `unsupported IfExpr` diagnostic.
- The parent-call work-item fixture advances past the same diagnostic.
- Any next failure is classified under another documented tranche, such as
  private context or resource-transition ownership; it is not a renamed
  `IfExpr` lowering failure.
- `if` remains proof-neutral and condition-pure.
- Branch effects are visible after WCC elaboration, ANF, analysis,
  defunctionalization, shared validation, and source-map projection.
- Lowered output uses the existing shared `if` branch surface and existing
  Core/runtime behavior.
- WCC metadata stays out of runtime state, artifacts, workflow outputs, and
  provider/command results.
- No new command adapter, inline command glue, report parsing, pointer
  authority, or runtime-native effect is introduced.

## Verification Plan

The deterministic implementation checks are recorded in:

`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect/check_commands.json`

The implementation should run the narrow selectors first, especially the WCC
characterization and design-delta work-item tests, before broadening to the
post-foundation regression band.
