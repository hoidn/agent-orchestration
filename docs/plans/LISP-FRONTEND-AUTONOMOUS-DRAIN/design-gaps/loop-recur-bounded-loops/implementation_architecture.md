# Loop/Recur Bounded Loops Implementation Architecture

## Scope

This design gap covers only the bounded author-facing `loop/recur` tranche
selected by the current drain state:

- add a public Workflow Lisp `(loop/recur ...)` expression surface that matches
  the full design's bounded loop contract;
- add the compiler-owned loop-body forms required by that surface:
  one special `fn` binder plus `continue` and `done`;
- typecheck loop state and terminal result without introducing a general lambda
  system, recursion, or cross-iteration proof leakage;
- lower the new surface through the existing shared `repeat_until` substrate
  and current authored-mapping -> shared-validation seam;
- add focused fixtures, diagnostics, and regression coverage proving the new
  surface composes with existing typed expressions, lowering, and resume-safe
  `repeat_until` behavior.

Out of scope for this tranche:

- general first-class lambdas, closures, or user-authored `fn` values outside
  `loop/recur`;
- recursion, unbounded loops, or `defproc` cycle support;
- a second loop executor, runtime-native loop IR promotion, or shared runtime
  redesign;
- new command adapters, scripts, or hidden command semantics;
- redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog,
  SourceMap, pointer authority, or variant proof;
- refactoring `review-revise-loop` or `backlog-drain` into the new generic
  surface as a completion requirement for this slice.

This is an implementation architecture for the selected bounded-loop gap only.
It does not authorize broad control-flow redesign beyond the public
`loop/recur` surface required by the full Workflow Lisp design.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_frontend_specification.md`
  Sections 13.1, 57, 58, 59, 63, 74, and 104;
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  especially the deferred/non-goal boundaries around `loop/recur`,
  higher-order evaluation, and runtime redesign;
- `docs/design/workflow_command_adapter_contract.md`;
- `docs/steering.md`;
- the Stage 1-9 frontend package boundaries and lowering seam already
  established in prior implementation architectures.

The slice must also preserve these guardrails:

- keep `orchestrator/workflow_lisp/` as the frontend-owned package and keep
  shared runtime semantics under `orchestrator/workflow/`;
- reuse the staged frontend pipeline:
  read -> syntax -> macro expansion -> definitions/functions/procedures/
  workflows -> typecheck -> lowering -> shared validation;
- reuse `SourcePosition`, `SourceSpan`, `LispFrontendDiagnostic`,
  macro-expansion provenance, and `LoweringOriginMap` as the only provenance
  channel;
- reuse the existing structured-result and boundary-flattening helpers rather
  than inventing a loop-only contract system;
- keep typed bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- preserve the shared `repeat_until` runtime behavior, including existing
  failure-on-exhaustion semantics when no authored exhaustion override exists;
- do not widen the command boundary: `loop/recur` lowering must not rely on
  inline Python, shell, heredocs, or hidden adapters;
- do not treat the empty `docs/steering.md` file in this checkout as implicit
  permission to broaden scope.

`docs/design/workflow_command_adapter_contract.md` remains authoritative here
even though the recommended implementation does not add a command adapter.
`loop/recur` explicitly chooses the existing `repeat_until` core substrate over
command-backed or runtime-native alternatives, so the adapter contract still
governs what this slice must avoid.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/core-workflow-ast-shared-contract/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defun-pure-helper-surface/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/executable-ir-runtime-plan/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-cli-artifact-emission/implementation_architecture.md`
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

- Reuse the existing staged frontend pipeline and package ownership split.
- Reuse the current provenance substrate:
  `SourcePosition`,
  `SourceSpan`,
  `LispFrontendDiagnostic`,
  macro expansion stacks,
  and `LoweringOriginMap`.
- Reuse the Stage 2 proof model:
  proof is created by `match`, remains frontend-local during typechecking, and
  does not automatically survive across control-flow boundaries.
- Reuse the Stage 3 and Stage 9 flattening/projection helpers in
  `contracts.py` for carried loop state and typed terminal results instead of
  adding a loop-only contract dialect.
- Reuse the Stage 5 and Stage 7 decision that higher-level looping should hand
  off through ordinary authored mappings and shared `repeat_until`, not a
  frontend-only executor.
- Reuse the shared runtime's existing `repeat_until` resume bookkeeping,
  loader gating, and failure-on-exhaustion behavior.
- Reuse the current expression/lowering style where effectful frontend
  expressions lower into deterministic generated steps, not hidden scripts.

### New Decisions In This Slice

- Add a public `loop/recur` expression surface and keep it as a compiler-owned
  special form rather than a user-extensible macro or a general function
  value.
- Add a loop-body-only `fn` binder shape plus `continue` and `done` forms.
  These are valid only inside `loop/recur`; they do not become general
  top-level language constructs.
- Introduce one frontend-local loop control type and lowering plan so the body
  can typecheck as a typed `CONTINUE | DONE` control result while the authored
  `loop/recur` expression itself still types to the terminal result.
- Lower generic bounded loops through the existing shared `repeat_until`
  substrate with carried projected state/result outputs and a deterministic
  post-loop normalization step.
- Keep loop exhaustion on the shared runtime's existing failure path rather
  than introducing a new authored exhaustion surface in this tranche.
- Allow carried loop state and terminal result only when they can lower
  through existing structured-result and boundary projection helpers.

### Conflicts Or Revisions

The Stage 6 resource/drain slice intentionally deferred a public generic loop:

- `backlog-drain` received a compiler-owned drain loop substrate;
- `review-revise-loop` already lowers through `repeat_until`;
- a public general `loop/recur` authoring surface remained deferred.

This slice revises that assumption narrowly:

- `loop/recur` becomes legal authored syntax;
- the new generic loop surface reuses the same shared `repeat_until` substrate
  already proven by `review-revise-loop` and `backlog-drain`;
- the drain and phase libraries remain valid consumers of `repeat_until`, but
  they are no longer the only loop-shaped frontend forms.

The revision is intentionally narrow:

- no shared runtime loop semantics are redefined;
- no new command boundary is introduced;
- no cross-iteration proof model is added;
- no prior slice is reversed on shared concepts such as Core Workflow AST,
  Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant
  proof.

## Ownership Boundaries

This slice owns:

- frontend AST/elaboration for authored `loop/recur` plus its compiler-owned
  `fn`, `continue`, and `done` subforms;
- frontend-local loop typing, including state/result validation and
  `continue`/`done` placement rules;
- frontend-local loop control metadata and lowering plans;
- deterministic projection of carried loop state and terminal result onto the
  shared `repeat_until.outputs` surface using existing contract helpers;
- lowering of authored loops into generated `repeat_until` steps plus
  post-loop normalization;
- source-map/origin tracking for generated loop seed steps, body projections,
  frame outputs, and post-loop normalization;
- focused fixtures and tests for syntax, typing, lowering, source maps, and
  shared-loop regression coverage.

This slice intentionally does not own:

- generic lambda values, closures, or arbitrary higher-order evaluation;
- recursion or a `loop/recur`-driven procedure recursion policy;
- runtime execution of `repeat_until`, resume bookkeeping, or state-schema
  changes under `orchestrator/workflow/`;
- command adapters, runtime-native resource transitions, or any other command
  boundary policy;
- redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog,
  SourceMap, pointer authority, variant proof, or workflow-call transport.

## Current Checkout Facts

The current checkout already contains loop-adjacent implementation, but not the
selected public surface:

- `orchestrator/workflow_lisp/expressions.py` already defines
  `ReviewReviseLoopExpr` and `BacklogDrainExpr`, but there is no public
  `LoopRecurExpr`, `ContinueExpr`, or `DoneExpr`.
- `orchestrator/workflow_lisp/lowering.py` already lowers both
  `review-revise-loop` and `backlog-drain` through generated `repeat_until`
  steps.
- `orchestrator/workflow_lisp/contracts.py` already provides
  `FlattenedContractField`,
  `derive_structured_result_contract(...)`,
  and `UnionWorkflowBoundaryProjection`, which can be reused for carried loop
  state/result projections.
- `tests/test_workflow_lisp_phase_stdlib.py` and
  `tests/test_workflow_lisp_drain_stdlib.py` already lock down compiler-owned
  `repeat_until` lowering paths.
- shared runtime and loader coverage for `repeat_until` already exists in
  `tests/test_loader_validation.py`,
  `tests/test_resume_command.py`,
  and related runtime-plan tests.
- there is no dedicated `tests/test_workflow_lisp_loop_recur.py` module and no
  dedicated author-facing `.orc` fixtures for generic bounded loops.
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` is still empty,
  so there is no later recorded implementation event that supersedes the
  selected `loop/recur` obligation.

This slice should reuse the proven loop substrate already in the checkout and
add the missing public authoring surface on top of it.

## Proposed Package Boundary

Extend the current frontend package with one new loop-focused helper module and
targeted updates to the existing expression/typecheck/lowering layers:

```text
orchestrator/workflow_lisp/
  compiler.py
  contracts.py
  diagnostics.py
  expressions.py
  loops.py            # new
  lowering.py
  typecheck.py
```

Planned test and fixture surface:

```text
tests/
  test_workflow_lisp_loop_recur.py
  test_workflow_lisp_expressions.py
  test_workflow_lisp_lowering.py
  test_workflow_lisp_drain_stdlib.py
  test_loader_validation.py
  test_resume_command.py
  fixtures/workflow_lisp/valid/loop_recur_minimal.orc
  fixtures/workflow_lisp/valid/loop_recur_union_result.orc
  fixtures/workflow_lisp/invalid/loop_recur_missing_done.orc
  fixtures/workflow_lisp/invalid/loop_recur_continue_type_mismatch.orc
  fixtures/workflow_lisp/invalid/loop_recur_done_type_mismatch.orc
  fixtures/workflow_lisp/invalid/loop_recur_fn_outside_loop.orc
```

Responsibilities:

- `loops.py`
  - define the frontend-local dataclasses for
    `LoopRecurSpec`,
    `LoopBodyBinding`,
    `LoopControlTypeRef`,
    `LoopValueProjection`,
    and `LoopLoweringPlan`;
  - centralize loop-specific carried-type validation and deterministic naming
    helpers for carried state/result outputs.
- `expressions.py`
  - elaborate authored `(loop/recur ...)` syntax;
  - recognize the loop-body-only `fn`, `continue`, and `done` forms;
  - keep `fn`, `continue`, and `done` rejected outside loop bodies.
- `typecheck.py`
  - infer the loop state type from `:state`;
  - validate `:max` as an integer-typed deterministic expression;
  - typecheck the loop body under one scoped state binding;
  - require every `continue` payload to match the state type exactly;
  - require all reachable `done` payloads to agree on one exact terminal
    result type;
  - reset proof scope at each iteration boundary so no variant proof leaks
    across iterations.
- `contracts.py`
  - reuse existing flattening/projection helpers for carried state/result;
  - add one loop-facing helper only if the current workflow-boundary helper
    names are too boundary-specific to be reused directly.
- `lowering.py`
  - lower generic loops through seeded carried outputs, generated
    `repeat_until`, and post-loop normalization;
  - emit ordinary generated steps only:
    `materialize_artifacts`,
    `output_bundle`,
    `variant_output`,
    `match`,
    and `repeat_until`;
  - preserve authored source spans on every generated step through the
    existing lowering-origin map.
- `compiler.py`
  - thread the new loop helper layer through the existing compile entrypoints
    without adding a new runtime or loader entrypoint.

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/functions.py`
- `orchestrator/workflow_lisp/macros.py`
- `orchestrator/workflow_lisp/procedures.py`
- `orchestrator/workflow_lisp/workflows.py`
- `orchestrator/workflow_lisp/phase_stdlib.py`
- `orchestrator/workflow_lisp/resource_stdlib.py`
- `orchestrator/workflow_lisp/drain_stdlib.py`
- shared validation/runtime modules under `orchestrator/workflow/`

## Data Model

### Frontend Expression Nodes

Add one public loop expression and three loop-body-only helper nodes:

- `LoopRecurExpr`
  - `max_iterations_expr`
  - `initial_state_expr`
  - `binding_name`
  - `body_expr`
  - `span`
  - `form_path`
  - `expansion_stack`
- `ContinueExpr`
  - `state_expr`
  - `span`
  - `form_path`
  - `expansion_stack`
- `DoneExpr`
  - `result_expr`
  - `span`
  - `form_path`
  - `expansion_stack`
- `LoopBodyFnExpr`
  - compiler-owned wrapper for `(fn (state) body)` used only during
    `loop/recur` elaboration;
  - not a general function value and not part of the public type surface.

### Frontend-Local Loop Type

Add one frontend-local control type:

- `LoopControlTypeRef`
  - `state_type_ref`
  - `result_type_ref`

Meaning:

- `continue` produces `LoopControlTypeRef(state_type_ref, result_type_ref)`
  where the payload is the next iteration state;
- `done` produces the same control type where the payload is the terminal
  result;
- the authored `loop/recur` expression itself does not expose the control type;
  it types to `result_type_ref` after body checking succeeds.

`LoopControlTypeRef` is frontend-local only. It must not be added to the shared
TypeCatalog or exposed across workflow boundaries.

### Projection Metadata

Add one frontend-local projection record reused by lowering:

- `LoopValueProjection`
  - `kind`: `state` or `result`
  - `flattened_fields`
  - `union_projection` when the carried type is a union
  - `placeholder_literals` for fields that are not authoritative on a given
    control branch but still require deterministic declared outputs

Add one lowering record:

- `LoopLoweringPlan`
  - `state_projection`
  - `result_projection`
  - `status_output_name`
  - `seed_step_name`
  - `repeat_step_name`
  - `body_projection_step_name`
  - `result_normalization_step_name`

The loop plan is frontend-local metadata consumed by `lowering.py`. It does not
become a shared runtime object.

## Author-Facing Surface

The authored bounded-loop shape remains aligned with the full design:

```lisp
(loop/recur
  :max max-iterations
  :state initial-state
  (fn (state)
    ...))
```

Loop body rules:

- the `fn` binder must contain exactly one bound name and one body expression;
- `fn` is valid only as the body form of `loop/recur`;
- the body may use the existing typed expression surface, including `let*`,
  `match`, `call`, `provider-result`, `command-result`, and other already
  supported effectful forms;
- loop progress is expressed only through:
  - `(continue next-state)`
  - `(done terminal-result)`
- `continue` and `done` are valid only inside an active `loop/recur` body.

The surface stays intentionally bounded:

- no general anonymous functions;
- no multi-parameter loop body;
- no explicit recursion keyword;
- no hidden ambient state;
- no command text as loop authority.

## Typechecking And Proof Model

### State And Result Inference

Typechecking sequence:

1. Typecheck `:state` with the ordinary expression checker and use that exact
   inferred type as the loop state type.
2. Validate that the carried state type is lowerable through existing
   structured projection helpers.
3. Typecheck the body with the loop binding name bound to that state type.
4. Collect every reachable `done` payload type and require exact agreement on
   one terminal result type.
5. Validate that the terminal result type is lowerable through existing
   structured projection helpers.
6. Type the authored `loop/recur` expression as that terminal result type.

Reject carried state/result types that cannot cross the generated loop-output
surface honestly:

- `Provider`
- `Prompt`
- `WorkflowRef[...]`
- `Json`
- any future non-projectable type that current `contracts.py` cannot flatten or
  project deterministically.

Allowed carried types in this tranche:

- scalar primitives and enums already supported by the frontend;
- relpath contracts;
- records;
- unions, provided they are re-proved with `match` whenever a branch needs
  variant-only fields.

### `continue` And `done`

Rules:

- every `continue` payload must typecheck to the exact loop state type;
- every `done` payload must typecheck to the exact terminal result type chosen
  by the loop body;
- a loop body with no reachable `done` is invalid;
- a loop body with mismatched `done` payload types is invalid;
- `continue`/`done` outside loop scope are invalid.

### Proof Boundaries

Each loop iteration starts with only:

- the state binding; and
- the ordinary lexical environment outside the loop.

No variant proof survives from one iteration to the next. If loop state or
result is a union, authors must re-enter proof with `match` inside the body or
after the loop result is produced.

This preserves the Stage 2 proof contract instead of inventing a hidden
cross-iteration proof graph.

## Lowering Model

### Selected Backend

This slice chooses one lowering backend only:

- lower generic `loop/recur` through the existing shared `repeat_until`
  statement substrate.

Rejected backend choices for this tranche:

- generated recursive workflow calls;
- command-backed loop control;
- runtime-native loop IR promotion.

### Generated Shape

Lower one authored `loop/recur` expression into:

1. one generated seed step that materializes the initial projected state;
2. one generated `repeat_until` frame carrying:
   - loop status;
   - projected state fields;
   - projected result fields;
3. generated body-projection steps that normalize `continue` and `done`
   outcomes into those carried outputs;
4. one generated post-loop normalization step that reconstructs the typed final
   result from the carried result projection.

The loop-frame condition stays simple and deterministic:

- continue while `self.outputs.<status>` is `CONTINUE`;
- stop when the body yields `DONE`.

The loop body keeps using ordinary generated steps from existing lowering.
There is no hidden shell wrapper, no temporary pointer authority, and no
special runtime callback.

### Projection Rules

State and terminal result projections must reuse the existing flattened-field
machinery:

- records lower through flattened leaf contracts;
- unions lower through discriminant + shared fields + variant-only fields;
- scalar/path values lower through their ordinary existing contract
  definitions.

Implementation rules:

- carried outputs use deterministic generated names with a loop-owned prefix;
- `continue` branches must overwrite the carried state projection and set loop
  status to `CONTINUE`;
- `done` branches must overwrite the carried result projection and set loop
  status to `DONE`;
- fields that are not authoritative on a branch must still satisfy declared
  output contracts through deterministic placeholders or branch-invariant
  carried values, never by omitting declared outputs.

### Exhaustion Semantics

This slice does not invent a new authored exhaustion surface.

If the loop body continues through all `max_iterations` without producing
`DONE`, lowering relies on the shared runtime's existing `repeat_until`
behavior:

- the loop fails with the existing exhaustion runtime path;
- no fake authored result is synthesized;
- no hidden adapter is inserted to reinterpret exhaustion.

That keeps the bounded loop slice aligned with the current shared runtime
contract and avoids broadening into a second exhaustion-routing design.

## Shared Workflow Handoff And Source Maps

The selected form still hands off through the existing authored workflow
mapping bridge:

- typed loop forms lower to ordinary authored mappings compatible with
  `elaborate_surface_workflow(...)`;
- shared validation continues to run on ordinary `repeat_until`, `match`,
  `materialize_artifacts`, `output_bundle`, `variant_output`, and other
  supported surfaces;
- any shared-validation failure on generated loop steps remaps through
  `LoweringOriginMap` back to the authored `loop/recur` span.

Required source-map coverage:

- the generated seed step;
- the generated `repeat_until` frame id;
- generated body projection steps for `continue` and `done`;
- the generated post-loop normalization step;
- any union projection artifacts surfaced from loop state or terminal result.

This slice does not redefine the shared `SourceMap` contract. It extends the
frontend-local origin coverage so loop-generated runtime and validation events
continue to resolve back to `.orc` source.

## Diagnostics

Add focused frontend diagnostics for:

- `loop_recur_contract_invalid`
- `loop_recur_fn_invalid`
- `loop_recur_max_invalid`
- `loop_recur_state_type_invalid`
- `loop_recur_result_type_invalid`
- `loop_recur_continue_outside_loop`
- `loop_recur_done_outside_loop`
- `loop_recur_continue_type_mismatch`
- `loop_recur_done_type_mismatch`
- `loop_recur_missing_done`

Reuse existing diagnostics whenever the meaning already matches:

- `type_mismatch`
- `union_match_non_exhaustive`
- `variant_ref_unproved`
- `variant_ref_wrong_variant`
- `workflow_return_not_exportable`

Every diagnostic must report the authored span, form path, and standard
expansion stack just like the existing frontend diagnostics.

## Test Strategy

### Frontend Unit Tests

- elaboration of valid authored `loop/recur` forms;
- rejection of malformed `fn`, `continue`, and `done` placement;
- exact state/result typing rules;
- rejection of non-projectable carried types;
- proof reset across iterations, especially with union-valued state.

### Lowering And Shared-Validation Tests

- generic `loop/recur` lowers through one generated `repeat_until` frame;
- lowering uses only ordinary supported workflow surfaces;
- carried state/result outputs project through deterministic flattened names;
- union-valued loop result reconstructs through existing structured-result
  helpers;
- shared validation accepts the generated authored mapping without YAML text or
  runtime changes.

### Regression Tests

- existing `review-revise-loop` lowering remains stable;
- existing `backlog-drain` lowering remains stable;
- existing loader and resume `repeat_until` behavior remains stable;
- existing workflow-lisp expression, lowering, and build regressions continue
  to pass.

## Implementation Sequence

1. Add the loop-local data model and diagnostics scaffold in `loops.py`.
2. Extend `expressions.py` to elaborate authored `loop/recur`, loop-only `fn`,
   `continue`, and `done`.
3. Extend `typecheck.py` with carried-type validation, body checking, and
   result-type inference.
4. Reuse or minimally generalize `contracts.py` projection helpers so carried
   state/result can lower without boundary-specific duplication.
5. Add generic `repeat_until` lowering plus post-loop result normalization in
   `lowering.py`.
6. Add focused fixtures and tests, then rerun the existing loop-adjacent
   regression selectors.

## Acceptance Conditions

- authored `loop/recur` is legal Workflow Lisp syntax and stays bounded to
  `:max`, `:state`, and one compiler-owned `fn` body;
- `continue` and `done` are legal only inside `loop/recur` bodies and enforce
  exact carried state/result typing;
- generic bounded loops lower through shared `repeat_until` rather than a
  second executor, runtime-native loop IR, or hidden scripts;
- carried state/result projections remain typed and source-mapped, using the
  existing structured projection helpers instead of ad hoc JSON/text glue;
- loop exhaustion keeps the shared runtime's existing failure semantics;
- no cross-iteration variant proof is introduced;
- shared validation continues to see only ordinary supported workflow surfaces;
- existing `review-revise-loop`, `backlog-drain`, loader, and resume regressions
  still pass.

## Verification Plan

Implementation should verify this slice with narrow selectors first:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_loop_recur.py tests/test_workflow_lisp_lowering.py tests/test_loader_validation.py tests/test_resume_command.py -q
python -m pytest tests/test_workflow_lisp_loop_recur.py -q
python -m pytest tests/test_workflow_lisp_lowering.py -k 'loop_recur or repeat_until' -q
python -m pytest tests/test_loader_validation.py -k repeat_until -q
python -m pytest tests/test_resume_command.py -k repeat_until -q
python -m orchestrator compile tests/fixtures/workflow_lisp/valid/loop_recur_minimal.orc --validate-shared
```

The implementation plan for this slice should record the same commands in the
generated check-command bundle and keep them deterministic.
