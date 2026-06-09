# Workflow Lisp Typecheck Family Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` to execute this plan task-by-task. Do not create a git worktree; `AGENTS.md` forbids worktrees for this repo. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the standalone `workflow-lisp-typecheck-family-decomposition` prerequisite by splitting `orchestrator/workflow_lisp/typecheck.py` into explicit typechecking-family owners behind the existing `orchestrator.workflow_lisp.typecheck` compatibility surface, while preserving current `.orc` behavior, diagnostics, proof behavior, effect visibility, and public imports.

**Architecture:** Follow [the selected implementation architecture](./implementation_architecture.md), not the older design text alone. Keep `typecheck.py` as the stable facade, introduce `typecheck_context.py`, `typecheck_dispatch.py`, `typecheck_proofs.py`, `typecheck_effects.py`, and `typecheck_calls.py`, move `let-proc` and generated local-procedure typing into `procedure_typecheck.py`, and expand `phase_stdlib_typecheck.py` so the temporary review-loop bridge no longer lives in the facade. Each extraction is behavior-preserving and must land with focused characterization tests before the next family moves.

**Tech Stack:** Python 3, dataclasses, the existing `orchestrator.workflow_lisp` frontend pipeline, shared workflow validation/runtime integration in `orchestrator.workflow`, and pytest.

---

## Fixed Inputs

Treat these as authority for this slice:

- `docs/index.md`
- `docs/steering.md`
  - currently empty in this checkout; there are no local steering overrides that widen scope
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - especially sections `8.1`, `9.6.1`, and `Stage 1 - Behavior-Preserving Refactor Preflight`
- `docs/design/workflow_lisp_refactor_architecture.md`
- `docs/design/workflow_lisp_compile_time_parametric_specialization.md`
- `docs/design/workflow_lisp_structural_parametric_constraints.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/2026-05-23-workflow-lisp-refactoring-backlog.md`
- `docs/plans/2026-06-02-workflow-lisp-low-hanging-refactor-plan.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-typecheck-family-decomposition/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/6/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/6/prerequisite-selector/selection.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/6/design-gap-architect/architecture-targets.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/6/design-gap-architect/existing-architecture-index.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`
  - currently `{"ledger_version":1,"events":[]}`; no later ledger event supersedes this prerequisite

## Current Checkout Starting Point

Implementation must start from the current checkout, not from the older design snapshot:

- `orchestrator/workflow_lisp/typecheck.py` is still 5,932 lines and still owns:
  - `TypedExpr`
  - `ValueEnvironment`
  - `ProofFact`
  - `ProofScope`
  - `typecheck_expression(...)`
  - recursive `_typecheck(...)`
  - provider/command typing
  - workflow/function/workflow-ref call typing
  - `let-proc` typing
  - the temporary `StdlibSpecializationExpr` review-loop bridge typing
  - `_raise_required_lint(...)` and `_raise_error(...)`
- `orchestrator/workflow_lisp/procedure_typecheck.py` already exists at 655 lines and already owns:
  - `typecheck_procedure_definitions(...)`
  - `typecheck_procedure_call_expr(...)`
  - generated-procedure typing and parametric specialization request collection
- `orchestrator/workflow_lisp/phase_stdlib_typecheck.py` already exists at 51 lines but still only guards the legacy review-loop bridge policy and delegates the real typing back into `typecheck.py`
- none of these owner files exist yet:
  - `orchestrator/workflow_lisp/typecheck_context.py`
  - `orchestrator/workflow_lisp/typecheck_dispatch.py`
  - `orchestrator/workflow_lisp/typecheck_proofs.py`
  - `orchestrator/workflow_lisp/typecheck_effects.py`
  - `orchestrator/workflow_lisp/typecheck_calls.py`
- the public import surface that must remain stable is already in use by:
  - `orchestrator/workflow_lisp/__init__.py`
  - `orchestrator/workflow_lisp/functions.py`
  - `orchestrator/workflow_lisp/workflows.py`
  - `orchestrator/workflow_lisp/compiler.py`
  - tests importing `typecheck_expression`, `TypedExpr`, `ProofFact`, `ProofScope`, and generated-local-procedure state helpers
- the focused regression surface for this slice is already present in:
  - `tests/test_workflow_lisp_expressions.py`
  - `tests/test_workflow_lisp_variant_proofs.py`
  - `tests/test_workflow_lisp_diagnostics.py`
  - `tests/test_workflow_lisp_macros.py`
  - `tests/test_workflow_lisp_functions.py`
  - `tests/test_workflow_lisp_procedures.py`
  - `tests/test_workflow_lisp_workflow_refs.py`
  - `tests/test_workflow_lisp_workflows.py`
  - `tests/test_workflow_lisp_structured_results.py`
  - `tests/test_workflow_lisp_phase_stdlib.py`

## Scope Limits

In scope:

- adding the exact owner files named in the implementation architecture
- preserving `orchestrator.workflow_lisp.typecheck` as the public compatibility surface
- moving context/session state, dispatch routing, proof helpers, effect/command validation, call typing, `let-proc` typing, and temporary review-loop bridge typing into the selected owners
- tightening focused tests so future structural-constraint or imported-`.orc` work targets the landed owner files instead of the facade
- updating `orchestrator/workflow_lisp/README.md` so the code map matches the landed owner map

Out of scope:

- structural constraints or any new parametric typing behavior
- imported `.orc` expansion / Track A work
- lowering-family decomposition, command-adapter policy changes, or runtime changes
- deleting the temporary review-loop bridge
- unrelated cleanup in other large frontend modules

## Files And Responsibilities

Create:

- `orchestrator/workflow_lisp/typecheck_context.py`
- `orchestrator/workflow_lisp/typecheck_dispatch.py`
- `orchestrator/workflow_lisp/typecheck_proofs.py`
- `orchestrator/workflow_lisp/typecheck_effects.py`
- `orchestrator/workflow_lisp/typecheck_calls.py`

Modify:

- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/procedure_typecheck.py`
- `orchestrator/workflow_lisp/phase_stdlib_typecheck.py`
- `orchestrator/workflow_lisp/README.md`
- `orchestrator/workflow_lisp/__init__.py`
  - only if a re-export shim is needed after moving `TypedExpr`, `ProofFact`, or `ProofScope`
- `orchestrator/workflow_lisp/functions.py`
  - only if import cycles or compatibility wrappers require mechanical adjustment
- `orchestrator/workflow_lisp/workflows.py`
  - only if helper imports must shift to preserve the public facade
- `orchestrator/workflow_lisp/compiler.py`
  - only if generated-local-procedure helper imports need a compatibility shim
- `tests/test_workflow_lisp_expressions.py`
- `tests/test_workflow_lisp_variant_proofs.py`
- `tests/test_workflow_lisp_diagnostics.py`
- `tests/test_workflow_lisp_macros.py`
- `tests/test_workflow_lisp_functions.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_workflow_refs.py`
- `tests/test_workflow_lisp_workflows.py`
- `tests/test_workflow_lisp_structured_results.py`
- `tests/test_workflow_lisp_phase_stdlib.py`

Avoid widening into unrelated files unless a purely mechanical shim is required to preserve imports.

## Acceptance Target

This prerequisite is complete only when all of the following are true:

- these exact owner files exist and are the real owners for their families:
  - `typecheck_context.py`
  - `typecheck_dispatch.py`
  - `typecheck_proofs.py`
  - `typecheck_effects.py`
  - `typecheck_calls.py`
  - `procedure_typecheck.py`
  - `phase_stdlib_typecheck.py`
- `orchestrator.workflow_lisp.typecheck` remains the stable public compatibility surface for callers and tests
- `typecheck.py` is reduced to facade/coordinator behavior and falls below the 2,000-line maintained-module cap
- command-result and certified-adapter semantics remain explicit and visible under the command-adapter contract
- diagnostics remain stable for representative failures in:
  - command validation and macro-hidden-effect provenance
  - provider-result / command-result extern and bundle diagnostics
  - workflow/function/procedure calls
  - variant proof
  - `let-proc`
  - stdlib specialization
  - reusable-state typing
- the focused verification slice passes, or any pre-existing unrelated failures are recorded with exact command output before continuing

## Task 1: Add Owner-Boundary And Characterization Tests

**Files:**

- Modify: `tests/test_workflow_lisp_expressions.py`
- Modify: `tests/test_workflow_lisp_variant_proofs.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_workflow_refs.py`
- Modify: `tests/test_workflow_lisp_structured_results.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] **Step 1: Add facade and source-structure guards**

Add narrow tests that lock the intended post-split boundaries:

- `typecheck.py` still re-exports:
  - `typecheck_expression`
  - `TypedExpr`
  - `ProofFact`
  - `ProofScope`
  - `consume_generated_local_procedures`
  - `reset_generated_local_procedure_state`
  - `set_active_workflow_signature`
  - `clear_active_workflow_signature`
  - `set_active_reusable_state_producer_context`
  - `clear_active_reusable_state_producer_context`
- final owner files exist and become the real owners for:
  - proof types/helpers
  - provider/command validation
  - workflow/function/workflow-ref call typing
  - `let-proc` typing
  - temporary review-loop stdlib bridge typing
- `typecheck.py` no longer defines the real implementations for:
  - recursive `_typecheck(...)`
  - `ProofFact` / `ProofScope`
  - stdlib-bridge typing helpers
  - provider/command family helpers
  - `let-proc` family helpers

- [ ] **Step 2: Preserve current behavior guards instead of snapshots**

Keep the existing behavior-heavy regressions as the safety net for this split:

- variant-proof failures and proof-bearing field access
- provider-result / command-result contract validation
- workflow-ref call compatibility and specialization
- generated local-procedure behavior and state reset
- review-loop stdlib specialization typing and reusable-state validation

Do not replace them with full lowered-workflow snapshots or prompt-text assertions.

- [ ] **Step 3: Run collect-only on touched test modules**

Run:

```bash
pytest --collect-only \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_variant_proofs.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_workflow_refs.py \
  tests/test_workflow_lisp_structured_results.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  -q
```

Expected: collection succeeds and includes the new owner-boundary tests.

- [ ] **Step 4: Run the narrow failing boundary slice**

Run:

```bash
pytest \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_variant_proofs.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_workflow_refs.py \
  tests/test_workflow_lisp_structured_results.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  -k "facade or owner_split or proof or command_result or workflow_ref or let_proc or review_loop" \
  -q
```

Expected before implementation: the new source-structure / owner-boundary assertions fail because the family split has not landed yet.

- [ ] **Step 5: Commit**

```bash
git add \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_variant_proofs.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_workflow_refs.py \
  tests/test_workflow_lisp_structured_results.py \
  tests/test_workflow_lisp_phase_stdlib.py
git commit -m "test: lock workflow lisp typecheck family boundaries"
```

## Task 2: Add `typecheck_context.py` And Move Session State / Shared Helpers

**Files:**

- Create: `orchestrator/workflow_lisp/typecheck_context.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/__init__.py`
  - only if needed for re-export continuity
- Modify: `orchestrator/workflow_lisp/workflows.py`
  - only if a helper import must shift without changing behavior
- Modify: `orchestrator/workflow_lisp/compiler.py`
  - only if generated-local-procedure helper imports must shift without changing behavior

- [ ] **Step 1: Move passive data shapes and mutable session state**

Move into `typecheck_context.py`:

- `TypedExpr`
- `ValueEnvironment`
- a `TypecheckContext` dataclass carrying the recursive inputs currently threaded through `typecheck_expression(...)`
- a small mutable session-state object replacing the module globals for:
  - active ProcRef values
  - value-expression capture map
  - generated local procedures
  - `let-proc` rewrite results
  - active workflow signature
  - reusable-state producer context
  - review-loop bridge policy

Do not change the public `typecheck_expression(...)` signature.

- [ ] **Step 2: Move shared diagnostics helpers**

Move `_raise_error(...)` and `_raise_required_lint(...)` into `typecheck_context.py`, or wrap them there through a context-owned helper surface, while preserving:

- diagnostic codes
- source spans
- form paths
- expansion stacks

- [ ] **Step 3: Keep the facade import surface stable**

Make `typecheck.py` re-export the moved shapes and helper wrappers so existing imports from tests, `__init__.py`, `functions.py`, `workflows.py`, and `compiler.py` continue to work unchanged.

- [ ] **Step 4: Run focused checks**

Run:

```bash
python -m compileall orchestrator/workflow_lisp
pytest \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_workflows.py \
  -k "facade or generated_local_procedure or typecheck_expression" \
  -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add \
  orchestrator/workflow_lisp/typecheck_context.py \
  orchestrator/workflow_lisp/typecheck.py \
  orchestrator/workflow_lisp/__init__.py \
  orchestrator/workflow_lisp/workflows.py \
  orchestrator/workflow_lisp/compiler.py
git commit -m "refactor: add workflow lisp typecheck context seam"
```

## Task 3: Add `typecheck_dispatch.py` And Move Recursive Dispatch Routing

**Files:**

- Create: `orchestrator/workflow_lisp/typecheck_dispatch.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `tests/test_workflow_lisp_expressions.py`

- [ ] **Step 1: Move `_typecheck(...)` into the dispatch owner**

Create `typecheck_dispatch.py` and move the recursive dispatcher there. In this first pass, keep behavior unchanged by delegating family-specific branches back to existing helpers where needed.

The dispatch owner should become the only obvious routing point for:

- literals and names
- records and union constructors
- `let*`
- `if`
- `match`
- control-flow / phase / resource forms that are not moving into another owner in this slice
- explicit delegation to proofs, effects, calls, procedures, and stdlib bridge owners

- [ ] **Step 2: Keep `typecheck_expression(...)` as facade entrypoint**

`typecheck.py` should build the initial context/session state, call the dispatcher owner, and keep its public signature unchanged.

- [ ] **Step 3: Run focused checks**

Run:

```bash
pytest \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_workflows.py \
  -k "record or letstar or match or typecheck_expression" \
  -q
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add \
  orchestrator/workflow_lisp/typecheck_dispatch.py \
  orchestrator/workflow_lisp/typecheck.py \
  tests/test_workflow_lisp_expressions.py
git commit -m "refactor: move workflow lisp typecheck dispatch"
```

## Task 4: Extract Variant-Proof Ownership Into `typecheck_proofs.py`

**Files:**

- Create: `orchestrator/workflow_lisp/typecheck_proofs.py`
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `tests/test_workflow_lisp_variant_proofs.py`
- Modify: `tests/test_workflow_lisp_expressions.py`

- [ ] **Step 1: Move proof types and proof-scope helpers**

Move into `typecheck_proofs.py`:

- `ProofFact`
- `ProofScope`
- proof-scope creation for `match` arms
- proof-bearing field/projection checks
- diagnostics for variant-only field access outside proof-bearing contexts

Leave only re-exports in `typecheck.py`.

- [ ] **Step 2: Route field access and proof-bearing forms through the proof owner**

Update `typecheck_dispatch.py` so `FieldAccessExpr`, proof-sensitive `match` logic, and any proof-bearing `if`/loop helpers call into `typecheck_proofs.py` rather than keeping inline logic in the facade.

- [ ] **Step 3: Run focused proof checks**

Run:

```bash
pytest \
  tests/test_workflow_lisp_variant_proofs.py \
  tests/test_workflow_lisp_expressions.py \
  -q
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add \
  orchestrator/workflow_lisp/typecheck_proofs.py \
  orchestrator/workflow_lisp/typecheck_dispatch.py \
  orchestrator/workflow_lisp/typecheck.py \
  tests/test_workflow_lisp_variant_proofs.py \
  tests/test_workflow_lisp_expressions.py
git commit -m "refactor: extract workflow lisp proof typing"
```

## Task 5: Extract Provider / Command Validation Into `typecheck_effects.py`

**Files:**

- Create: `orchestrator/workflow_lisp/typecheck_effects.py`
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `tests/test_workflow_lisp_structured_results.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_diagnostics.py`
- Modify: `tests/test_workflow_lisp_macros.py`

- [ ] **Step 1: Move effect-bearing typecheck helpers**

Move into `typecheck_effects.py`:

- provider-result typing
- command-result typing
- expected extern operand validation
- command argv validation
- certified-adapter contract checks
- macro-hidden-effect diagnostics
- any effect compatibility helpers that belong to typechecking rather than the effect-atom registry

- [ ] **Step 2: Route effect-bearing forms through the new owner**

Update `typecheck_dispatch.py` so `ProviderResultExpr` and `CommandResultExpr` route through `typecheck_effects.py`.

Keep command-boundary semantics explicit; do not hide adapter validation inside unrelated generic helpers.

- [ ] **Step 3: Run collect-only on the effect and diagnostic suites**

Run:

```bash
pytest --collect-only \
  tests/test_workflow_lisp_structured_results.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_diagnostics.py \
  tests/test_workflow_lisp_macros.py \
  -q
```

Expected: collection succeeds and includes any new effect-owner boundary cases.

- [ ] **Step 4: Run focused structured-result, macro, and diagnostic checks**

Run:

```bash
pytest \
  tests/test_workflow_lisp_structured_results.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_diagnostics.py \
  tests/test_workflow_lisp_macros.py \
  -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add \
  orchestrator/workflow_lisp/typecheck_effects.py \
  orchestrator/workflow_lisp/typecheck_dispatch.py \
  orchestrator/workflow_lisp/typecheck.py \
  tests/test_workflow_lisp_structured_results.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_diagnostics.py \
  tests/test_workflow_lisp_macros.py
git commit -m "refactor: extract workflow lisp effect typing"
```

## Task 6: Extract Workflow / Function / Workflow-Ref Calls Into `typecheck_calls.py`

**Files:**

- Create: `orchestrator/workflow_lisp/typecheck_calls.py`
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `tests/test_workflow_lisp_functions.py`
- Modify: `tests/test_workflow_lisp_workflow_refs.py`
- Modify: `tests/test_workflow_lisp_workflows.py`
- Modify: `tests/test_workflow_lisp_procedures.py`

- [ ] **Step 1: Move non-procedure call typing**

Move into `typecheck_calls.py`:

- workflow call typing
- workflow-ref literal and argument compatibility helpers used during call typing
- workflow-ref role validation for selector / run-item / gap-drafter paths
- function-call typing
- reusable call-binding checks not owned by `procedure_typecheck.py`

Keep `workflow_refs.py` as the compile-time workflow-ref resolution authority; `typecheck_calls.py` should consume it rather than duplicate it.

- [ ] **Step 2: Route call-bearing forms through the call owner**

Update `typecheck_dispatch.py` so `CallExpr`, `WorkflowRefLiteralExpr`, and `FunctionCallExpr` delegate into `typecheck_calls.py`.

- [ ] **Step 3: Run collect-only on the direct call suites**

Run:

```bash
pytest --collect-only \
  tests/test_workflow_lisp_functions.py \
  tests/test_workflow_lisp_workflow_refs.py \
  tests/test_workflow_lisp_workflows.py \
  tests/test_workflow_lisp_procedures.py \
  -q
```

Expected: collection succeeds and includes any new call-owner boundary cases.

- [ ] **Step 4: Run focused call checks**

Run:

```bash
pytest \
  tests/test_workflow_lisp_functions.py \
  tests/test_workflow_lisp_workflow_refs.py \
  tests/test_workflow_lisp_workflows.py \
  tests/test_workflow_lisp_procedures.py \
  -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add \
  orchestrator/workflow_lisp/typecheck_calls.py \
  orchestrator/workflow_lisp/typecheck_dispatch.py \
  orchestrator/workflow_lisp/typecheck.py \
  tests/test_workflow_lisp_functions.py \
  tests/test_workflow_lisp_workflow_refs.py \
  tests/test_workflow_lisp_workflows.py \
  tests/test_workflow_lisp_procedures.py
git commit -m "refactor: extract workflow lisp call typing"
```

## Task 7: Finish Family Ownership Moves For `let-proc` And The Stdlib Bridge

**Files:**

- Modify: `orchestrator/workflow_lisp/procedure_typecheck.py`
- Modify: `orchestrator/workflow_lisp/phase_stdlib_typecheck.py`
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] **Step 1: Move `let-proc` typing into `procedure_typecheck.py`**

Move out of the facade and into `procedure_typecheck.py`:

- `LetProcExpr` typing
- local procedure capture validation
- scope-escape checks
- generated helper registration
- local ProcRef rewrite support

After this step, `typecheck.py` must no longer own the real `let-proc` family logic.

- [ ] **Step 2: Expand `phase_stdlib_typecheck.py` into the real stdlib-bridge owner**

Move into `phase_stdlib_typecheck.py`:

- `StdlibSpecializationExpr` typing for the temporary review-loop path
- review-loop result-contract validation
- generated review-loop helper typing utilities
- review-loop resume metadata derivation that currently lives in `typecheck.py`

Keep the bridge temporary, but stop scattering its typing logic across the generic facade.

- [ ] **Step 3: Run focused procedure and phase-stdlib checks**

Run:

```bash
pytest --collect-only \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  -q
```

Then run:

```bash
pytest \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  -k "let_proc or generated_local_procedure or review_loop or reusable_state or stdlib_specialization" \
  -q
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add \
  orchestrator/workflow_lisp/procedure_typecheck.py \
  orchestrator/workflow_lisp/phase_stdlib_typecheck.py \
  orchestrator/workflow_lisp/typecheck_dispatch.py \
  orchestrator/workflow_lisp/typecheck.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_phase_stdlib.py
git commit -m "refactor: finish workflow lisp typecheck family split"
```

## Task 8: Collapse The Facade, Update The Code Map, And Run Full Verification

**Files:**

- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/README.md`
- Modify: any touched compatibility import sites if a final shim is still needed

- [ ] **Step 1: Reduce `typecheck.py` to facade/coordinator behavior**

Leave in `typecheck.py` only:

- `typecheck_expression(...)`
- public re-exports needed by callers/tests
- compatibility wrappers for generated-local-procedure and active-workflow helper state
- no real family-owned implementations for proofs, effects, calls, `let-proc`, or stdlib bridge typing

- [ ] **Step 2: Update the package code map**

Update `orchestrator/workflow_lisp/README.md` so it records:

- the new typecheck owner files
- the unchanged public `typecheck.py` facade contract
- the fact that future structural-constraint/imported-`.orc` work must target the new owners rather than the facade

- [ ] **Step 3: Verify the line-cap acceptance target**

Run:

```bash
wc -l \
  orchestrator/workflow_lisp/typecheck.py \
  orchestrator/workflow_lisp/typecheck_context.py \
  orchestrator/workflow_lisp/typecheck_dispatch.py \
  orchestrator/workflow_lisp/typecheck_proofs.py \
  orchestrator/workflow_lisp/typecheck_effects.py \
  orchestrator/workflow_lisp/typecheck_calls.py \
  orchestrator/workflow_lisp/procedure_typecheck.py \
  orchestrator/workflow_lisp/phase_stdlib_typecheck.py
```

Expected: `typecheck.py` is below 2,000 physical lines; if not, do not claim completion.

- [ ] **Step 4: Run the full focused verification slice**

Run:

```bash
python -m compileall orchestrator/workflow_lisp
pytest \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_variant_proofs.py \
  tests/test_workflow_lisp_diagnostics.py \
  tests/test_workflow_lisp_macros.py \
  tests/test_workflow_lisp_functions.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_workflow_refs.py \
  tests/test_workflow_lisp_workflows.py \
  tests/test_workflow_lisp_structured_results.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  -q
git diff --check
```

Expected: all checks pass. If any unrelated pre-existing failure remains, record the exact command and output before stopping.

- [ ] **Step 5: Commit**

```bash
git add \
  orchestrator/workflow_lisp/typecheck.py \
  orchestrator/workflow_lisp/typecheck_context.py \
  orchestrator/workflow_lisp/typecheck_dispatch.py \
  orchestrator/workflow_lisp/typecheck_proofs.py \
  orchestrator/workflow_lisp/typecheck_effects.py \
  orchestrator/workflow_lisp/typecheck_calls.py \
  orchestrator/workflow_lisp/procedure_typecheck.py \
  orchestrator/workflow_lisp/phase_stdlib_typecheck.py \
  orchestrator/workflow_lisp/README.md \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_variant_proofs.py \
  tests/test_workflow_lisp_diagnostics.py \
  tests/test_workflow_lisp_macros.py \
  tests/test_workflow_lisp_functions.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_workflow_refs.py \
  tests/test_workflow_lisp_workflows.py \
  tests/test_workflow_lisp_structured_results.py \
  tests/test_workflow_lisp_phase_stdlib.py
git commit -m "refactor: decompose workflow lisp typecheck families"
```
