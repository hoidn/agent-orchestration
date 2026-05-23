# Loop/Recur Bounded Loops Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the author-facing bounded `loop/recur` Workflow Lisp surface, including loop-body-only `fn`, `continue`, and `done`, while keeping typing, provenance, and runtime behavior aligned with the existing shared `repeat_until` substrate.

**Architecture:** Keep ownership inside `orchestrator/workflow_lisp/` and reuse the existing read -> syntax -> definitions/functions/procedures/workflows -> typecheck -> lowering -> shared-validation pipeline. Add one frontend-local loop helper layer for data modeling and deterministic naming, elaborate the new authored forms in `expressions.py`, typecheck them with a frontend-local loop control type in `typecheck.py`, and lower them through generated `repeat_until` plus typed state/result projection in `lowering.py`. Do not add a second executor, command adapter glue, or runtime-native loop semantics.

**Tech Stack:** Python 3 dataclasses, the existing `orchestrator.workflow_lisp` compiler/typecheck/lowering pipeline, shared `repeat_until` loader/runtime behavior, pytest, and `.orc` fixtures under `tests/fixtures/workflow_lisp/`.

---

## Fixed Inputs

Treat these as implementation authority:

- `docs/index.md`
- `docs/design/workflow_lisp_frontend_specification.md`
  - bounded `loop/recur` surface and compiler/lowering sections
  - source-map and validation requirements
  - staging guidance that keeps loops frontend-owned and runtime-reused
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - MVP scope
  - non-goals around general lambdas, recursion, and runtime redesign
- `docs/design/workflow_command_adapter_contract.md`
  - use it as the guardrail for what this slice must not introduce
- `docs/steering.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/loop-recur-bounded-loops/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-full-restart-20260523T081550Z/iterations/6/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-full-restart-20260523T081550Z/iterations/6/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

Current checkout facts that should not be rediscovered during execution:

- `docs/steering.md` is empty in this checkout, so it does not expand scope.
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` has no events, so no later implementation record supersedes this work item.
- `orchestrator/workflow_lisp/expressions.py` already supports compiler-owned loop-like forms (`ReviewReviseLoopExpr`, `BacklogDrainExpr`) but has no public `LoopRecurExpr`, `ContinueExpr`, or `DoneExpr`.
- `orchestrator/workflow_lisp/lowering.py` already lowers loop-like forms through generated `repeat_until` mappings and already owns `LoweringOriginMap`.
- `orchestrator/workflow_lisp/contracts.py` already owns the flattening/projection helpers that must be reused for carried loop state and terminal result.
- `tests/test_workflow_lisp_expressions.py`, `tests/test_workflow_lisp_lowering.py`, `tests/test_workflow_lisp_phase_stdlib.py`, `tests/test_workflow_lisp_drain_stdlib.py`, `tests/test_loader_validation.py`, and `tests/test_resume_command.py` already provide the adjacent coverage surface.
- There is no dedicated `tests/test_workflow_lisp_loop_recur.py` module and no author-facing `loop_recur_*.orc` fixtures yet.

## Hard Scope Limits

Implement only this bounded slice:

- authored `(loop/recur :max ... :state ... (fn (...) ...))`
- loop-body-only compiler-owned `fn`, `continue`, and `done`
- exact carried state typing, terminal result inference, and proof reset per iteration
- deterministic lowering through shared `repeat_until`
- carried state/result projection through existing contract helpers
- source-map coverage for generated loop steps
- focused syntax/type/lowering/regression verification

Explicit non-goals:

- no general-purpose lambdas, closures, or first-class `fn`
- no recursion, unbounded loops, or new procedure recursion policy
- no runtime-native loop IR, executor changes, or shared runtime redesign
- no command adapters, inline Python/shell glue, or hidden workflow semantics
- no redesign of Core Workflow AST, Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant proof
- no required migration of `review-revise-loop` or `backlog-drain` to the new public surface

## File Ownership

Create:

- `orchestrator/workflow_lisp/loops.py`
- `tests/test_workflow_lisp_loop_recur.py`
- `tests/fixtures/workflow_lisp/valid/loop_recur_minimal.orc`
- `tests/fixtures/workflow_lisp/valid/loop_recur_union_result.orc`
- `tests/fixtures/workflow_lisp/invalid/loop_recur_missing_done.orc`
- `tests/fixtures/workflow_lisp/invalid/loop_recur_continue_type_mismatch.orc`
- `tests/fixtures/workflow_lisp/invalid/loop_recur_done_type_mismatch.orc`
- `tests/fixtures/workflow_lisp/invalid/loop_recur_fn_outside_loop.orc`

Modify:

- `orchestrator/workflow_lisp/__init__.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/contracts.py`
- `orchestrator/workflow_lisp/compiler.py`
- `tests/test_workflow_lisp_expressions.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_loader_validation.py`
- `tests/test_resume_command.py`

Reuse without widening ownership:

- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/phase_stdlib.py`
- `orchestrator/workflow_lisp/drain_stdlib.py`
- shared runtime/loader modules under `orchestrator/workflow/`

Modify only if a focused failing regression proves the need:

- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_drain_stdlib.py`

## Required Behavioral Contract

Keep these rules fixed during implementation:

- `loop/recur` accepts exactly `:max`, `:state`, and one loop-body `fn`.
- the `fn` binder accepts exactly one bound state name and one body expression.
- `fn`, `continue`, and `done` are valid only inside an active `loop/recur` body.
- `:state` determines the carried state type exactly.
- every `continue` payload must match the carried state type exactly.
- every reachable `done` payload must agree on one exact terminal result type.
- a loop body with no reachable `done` is invalid.
- iteration proof scope resets each iteration; no variant proof leaks across loop boundaries.
- carried state and terminal result types must be projectable through the existing contract helpers.
- lowering must use only ordinary supported surfaces such as `repeat_until`, `match`, `output_bundle`, `variant_output`, `materialize_artifacts`, and call/provider/command steps already supported by the frontend.
- loop exhaustion must remain the shared runtime’s existing `repeat_until` failure behavior. Do not synthesize a frontend-only exhaustion result.

Reject carried types that cannot honestly cross the generated loop-output surface:

- `Provider`
- `Prompt`
- `Json`
- `WorkflowRef[...]`
- any future type the current projection helpers cannot flatten or reconstruct deterministically

## Task 1: Lock The Public Surface With Fixtures And Failing Tests

**Files:**

- Create: `tests/test_workflow_lisp_loop_recur.py`
- Create: `tests/fixtures/workflow_lisp/valid/loop_recur_minimal.orc`
- Create: `tests/fixtures/workflow_lisp/valid/loop_recur_union_result.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/loop_recur_missing_done.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/loop_recur_continue_type_mismatch.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/loop_recur_done_type_mismatch.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/loop_recur_fn_outside_loop.orc`
- Modify: `tests/test_workflow_lisp_expressions.py`
- Modify: `tests/test_workflow_lisp_lowering.py`

- [ ] **Step 1: Add minimal valid fixtures that exercise both record and union results**

Create one pure minimal fixture and one union-result fixture that lock the public authored shape:

- `loop_recur_minimal.orc` should use only existing typed forms plus `loop/recur`, `continue`, and `done`, and should compile without new extern dependencies.
- `loop_recur_union_result.orc` should prove that a union-valued carried state or terminal result still requires local `match` proof rather than leaked cross-iteration proof.

- [ ] **Step 2: Add invalid fixtures for the selected failure modes**

Create invalid fixtures for:

- body missing any reachable `done`
- `continue` payload type mismatch
- `done` payload type mismatch
- loop-body-only `fn` usage outside `loop/recur`

If a non-projectable carried-type rejection needs a dedicated fixture instead of inline test text, add it here rather than inventing ad hoc temporary modules later.

- [ ] **Step 3: Add failing tests before implementation**

Add or extend tests so the current tree fails on the missing public loop behavior rather than on unrelated parsing:

- `tests/test_workflow_lisp_expressions.py`
  - elaboration of valid `(loop/recur ...)`
  - rejection of malformed loop-body `fn`
  - rejection of `fn` outside `loop/recur`
- `tests/test_workflow_lisp_loop_recur.py`
  - exact `continue`/`done` typing
  - missing-`done` failure
  - proof reset across iterations
  - rejection of non-projectable carried types
- `tests/test_workflow_lisp_lowering.py`
  - one compiled fixture lowers through a generated `repeat_until`
  - origin map covers generated loop steps and outputs

Suggested test names:

```python
test_elaborate_expression_supports_loop_recur
test_elaborate_expression_rejects_fn_outside_loop_recur
test_typecheck_loop_recur_requires_reachable_done
test_typecheck_loop_recur_rejects_continue_type_mismatch
test_typecheck_loop_recur_rejects_done_type_mismatch
test_typecheck_loop_recur_resets_variant_proof_each_iteration
test_lowering_loop_recur_uses_repeat_until_with_typed_outputs
test_lowering_loop_recur_preserves_origin_map_for_generated_steps
```

- [ ] **Step 4: Run collection checks for the new module and touched tests**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_loop_recur.py tests/test_workflow_lisp_lowering.py tests/test_loader_validation.py tests/test_resume_command.py -q
```

Expected:

- collection succeeds
- the new `tests/test_workflow_lisp_loop_recur.py` tests appear
- any failures are implementation failures, not import or collection failures

## Task 2: Add The Frontend-Local Loop Data Model And Public AST Surface

**Files:**

- Create: `orchestrator/workflow_lisp/loops.py`
- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/__init__.py`

- [ ] **Step 1: Create `loops.py` as the loop-local metadata home**

Add frontend-local dataclasses and helpers here rather than scattering loop state across lowering/typecheck:

- `LoopRecurSpec`
- `LoopBodyBinding`
- `LoopControlTypeRef`
- `LoopValueProjection`
- `LoopLoweringPlan`

Also centralize deterministic generated-name helpers for:

- carried status output
- carried state/result projection prefixes
- generated seed step
- generated repeat frame
- generated body projection step(s)
- generated post-loop normalization step

The names chosen here must be stable and asserted by tests, but they do not need to be public API outside the frontend package.

- [ ] **Step 2: Extend `expressions.py` with the new loop nodes**

Add:

- `LoopRecurExpr`
- `LoopBodyFnExpr`
- `ContinueExpr`
- `DoneExpr`

Update `ExprNode` and the elaboration dispatcher so:

- `loop/recur` parses as one public special form
- loop-body `fn` is accepted only in the body slot of `loop/recur`
- `continue` and `done` elaborate only inside an active loop-body context
- ordinary parsing and symbol handling in `reader.py` and `syntax.py` stay unchanged

- [ ] **Step 3: Keep placement errors explicit and authored**

Use stable diagnostics for:

- `loop_recur_contract_invalid`
- `loop_recur_fn_invalid`
- `loop_recur_continue_outside_loop`
- `loop_recur_done_outside_loop`

Every error must point at the authored loop form span and form path, not at generated helper logic.

- [ ] **Step 4: Export the new public surface**

Update `orchestrator/workflow_lisp/__init__.py` so the new expression nodes and any intentionally public loop types are importable in tests and by adjacent frontend code. Do not expose private helper names that are only lowering internals.

- [ ] **Step 5: Run the focused expression tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_expressions.py -q
```

Expected:

- public elaboration behavior is locked
- failures, if any, are now in typing/lowering rather than surface parsing

## Task 3: Implement Loop Typing, Result Inference, And Proof Reset

**Files:**

- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/loops.py`
- Modify: `tests/test_workflow_lisp_loop_recur.py`

- [ ] **Step 1: Typecheck `loop/recur` from the carried state outward**

In `typecheck.py`:

- typecheck `:state` first and use that exact type as the carried state type
- require `:max` to typecheck as `Int`
- reject carried state types that cannot be projected honestly
- bind the loop state name only within the loop-body `fn`

- [ ] **Step 2: Add a frontend-local loop control type**

Use `LoopControlTypeRef` only during frontend checking:

- `continue` should produce control state carrying the next iteration state
- `done` should produce the same control shape carrying the terminal result
- authored `loop/recur` itself must still type to the terminal result type, not to the control type

Do not add this type to shared runtime/schema surfaces.

- [ ] **Step 3: Infer one exact terminal result type**

The typechecker must:

- collect reachable `done` payload types
- reject loops with no reachable `done`
- reject mismatched `done` payload types
- validate that the chosen result type is also projectable through existing contract helpers

Use loop-specific diagnostics where needed:

- `loop_recur_max_invalid`
- `loop_recur_state_type_invalid`
- `loop_recur_result_type_invalid`
- `loop_recur_continue_type_mismatch`
- `loop_recur_done_type_mismatch`
- `loop_recur_missing_done`

- [ ] **Step 4: Reset proof scope at iteration boundaries**

Do not let `ProofScope` facts flow across iterations. The loop body starts each iteration with:

- the carried state binding
- outer lexical names
- no retained variant proof from the prior iteration

Add at least one test that proves a union field accessed without a fresh `match` still fails under `variant_ref_unproved` after a `continue`.

- [ ] **Step 5: Run the focused loop typing tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_loop_recur.py -q
```

Expected:

- missing-`done`, placement, and exact-type errors are stable
- proof-reset coverage passes without changing the existing Stage 2 proof model

## Task 4: Reuse Projection Helpers And Lower Through Shared `repeat_until`

**Files:**

- Modify: `orchestrator/workflow_lisp/contracts.py`
- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/loops.py`
- Modify: `tests/test_workflow_lisp_lowering.py`

- [ ] **Step 1: Generalize only the projection logic that must be shared**

In `contracts.py`, reuse the existing flattening/boundary helpers for loop-carried values. If current helper names are too boundary-specific, add the smallest loop-facing abstraction needed rather than copying logic.

The loop path must support:

- scalar and enum carried values
- relpath carried values
- records via flattened fields
- unions via discriminant, shared fields, and variant-only fields

- [ ] **Step 2: Teach lowering about `LoopRecurExpr`**

In `lowering.py`:

- treat `LoopRecurExpr` as an effectful expression that can appear in `let*`
- extend `_binding_type_for_expr(...)` or its equivalent to resolve the inferred loop result type
- add a dedicated lowering helper that turns one authored loop into:
  - a generated seed step
  - one generated `repeat_until`
  - generated body projection/normalization steps
  - one final result reconstruction step

- [ ] **Step 3: Preserve shared runtime semantics**

The generated `repeat_until` must:

- continue while the carried status output is `CONTINUE`
- stop when the body yields `DONE`
- rely on the shared runtime’s existing exhaustion failure path
- avoid `on_exhausted` overrides or synthetic fallback outputs for this slice

Do not add helper scripts, adapter calls, or inline shell/Python glue to drive loop state.

- [ ] **Step 4: Preserve authored provenance on every generated node**

Extend `LoweringOriginMap` coverage so loop-generated artifacts are source-mapped:

- seed step
- repeat frame
- loop-body projection step(s)
- post-loop normalization step
- any generated output/path projections for union or record carried values

Shared-validation failures on those generated names must still remap to the authored `loop/recur` span.

- [ ] **Step 5: Thread the new helper module through the compiler surface**

Update `compiler.py` only as needed so Stage 3 compile entrypoints can elaborate, typecheck, lower, and validate `.orc` modules containing `loop/recur` without adding any new top-level compile path.

- [ ] **Step 6: Run focused lowering coverage**

Run:

```bash
python -m pytest tests/test_workflow_lisp_lowering.py -k 'loop_recur or repeat_until' -q
```

Expected:

- loop fixtures lower through one shared `repeat_until` frame
- deterministic loop output names are asserted
- existing review/drain loop lowering is not broken by the shared helper reuse

## Task 5: Prove Shared Validation And Resume-Safe Runtime Substrate Regressions Stay Intact

**Files:**

- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_workflow_lisp_lowering.py`

- [ ] **Step 1: Add or adjust only the narrow regression assertions needed**

Use these modules to prove the public loop surface still hands off cleanly to the already-owned runtime substrate:

- `tests/test_loader_validation.py`
  - loader accepts the lowered `repeat_until` shape produced by the frontend
  - no new forbidden surface or version mismatch is introduced
- `tests/test_resume_command.py`
  - existing `repeat_until` resume assumptions still hold for the shared substrate
  - no frontend-generated shape breaks checkpoint or iteration bookkeeping expectations

These tests are regression guards for the handoff seam, not an excuse to redesign shared runtime behavior.

- [ ] **Step 2: Keep the regression bounded**

Do not broaden this work into generic runtime loop changes. If a runtime test fails, first treat it as a frontend lowering-shape bug unless the failure proves a pre-existing shared contract gap.

- [ ] **Step 3: Run the shared substrate regression selectors**

Run:

```bash
python -m pytest tests/test_loader_validation.py -k repeat_until -q
python -m pytest tests/test_resume_command.py -k repeat_until -q
```

Expected:

- existing shared `repeat_until` loader and resume behavior remains green
- no new resume-specific surface needs to be invented for the public loop form

## Task 6: Run The Required Verification Sequence And Record Evidence

**Files:**

- No code changes; this task captures the required verification evidence.

- [ ] **Step 1: Run the required command sequence from the repo root**

Run these commands in order:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_loop_recur.py tests/test_workflow_lisp_lowering.py tests/test_loader_validation.py tests/test_resume_command.py -q
python -m pytest tests/test_workflow_lisp_loop_recur.py -q
python -m pytest tests/test_workflow_lisp_lowering.py -k 'loop_recur or repeat_until' -q
python -m pytest tests/test_loader_validation.py -k repeat_until -q
python -m pytest tests/test_resume_command.py -k repeat_until -q
python -m orchestrator compile tests/fixtures/workflow_lisp/valid/loop_recur_minimal.orc --validate-shared
```

The last command is the required frontend/shared-validation smoke check for this slice.

- [ ] **Step 2: Record fresh command output, not inferred success**

For each command capture:

- pass/fail status
- exact failing test names or CLI error if anything breaks
- whether the compile smoke validated through the shared pipeline

Do not weaken selectors or skip the compile smoke to make a failure disappear.

## Completion Notes

Implementation is complete for this work item only when all of the following are true:

- authored `loop/recur` is legal Workflow Lisp syntax and remains bounded to `:max`, `:state`, and one loop-body `fn`
- `continue` and `done` are legal only inside `loop/recur` bodies and enforce exact carried state/result typing
- loop state and terminal result stay on existing structured projection helpers rather than loop-specific ad hoc contracts
- generic loops lower through shared `repeat_until` and preserve current exhaustion semantics
- no cross-iteration variant proof is introduced
- generated loop steps and outputs remain source-mapped through `LoweringOriginMap`
- the six ordered verification commands above pass from the repo root
