# Workflow Lisp Stdlib Review-Loop Ownership Bridge Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` to implement this plan task-by-task. Do not create a git worktree; `AGENTS.md` forbids worktrees for this repo. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the selected residual review-loop convergence slice by preserving `std/phase.orc` as the only promoted owner of the review-loop body, hidden seeds, public macro, and exact `ReviewLoopResult` protocol, by stabilizing the ordinary direct-route type/callback/result typing that direct ownership exposed across same-module and imported procedure boundaries, and by removing the remaining review-loop bridge expression surface and bridge-only policy/typecheck/lowering compatibility code.

**Architecture:** Treat the current checkout as a post-inline but pre-Stage-12 hybrid. The public route already expands through `std/phase/review-revise-loop-proc`, `std/phase.orc` already owns the inlined single-body loop implementation, and `std/phase_review_loop_support.orc` is already gone, but Python still carries a dead review-loop bridge centered on `StdlibSpecializationExpr`, `__stdlib-specialization__`, `phase-review-loop`, and allow/deny policy plumbing. The remaining bounded work is to stabilize the ordinary direct route that this ownership move now exercises, especially canonical local-versus-qualified type identity across review-loop signatures, imported procedure signatures, proc-ref callbacks/results, generated seeds, and `command-result` returns, then remove the bridge-only Python and test surfaces so promoted review-loop behavior is proven solely through ordinary stdlib module compilation, proc-ref specialization, `loop/recur`, `match`, `command-result`, and shared lowering/validation.

**Tech Stack:** Workflow Lisp `.orc` stdlib/modules, Python frontend modules under `orchestrator/workflow_lisp/`, shared validation/runtime reuse under `orchestrator/workflow/`, public `python -m orchestrator` compile/run smoke commands, and `pytest`.

---

## Fixed Inputs

Treat these artifacts as the governing inputs for this plan:

- `docs/index.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/design/workflow_lisp_frontend_specification.md`
  - especially Sections `27` and `57`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - especially Stage `10`, Stage `12`, Stage `28`, and the Section `12.3` note consumed by the work-item context
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/6/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`
  - currently `{"ledger_version":1,"events":[]}`; there is no later ledger event overriding this slice

Additional references selected through `docs/index.md` because the work-item context names them as authoritative for this bounded ownership-retirement slice:

- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_refactor_architecture.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-owner-seam-split-prerequisite/implementation_architecture.md`

`docs/steering.md` is empty in this checkout. It does not widen scope; the selected work-item context and target design remain the steering surfaces.

## Current Checkout Starting Point

Implementation must start from the current checkout facts, not from the older Stage 10 bridge-based plan:

- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` already defines:
  - `ReviewDecision`
  - `ReviewFindings`
  - `ReviewLoopResult`
  - `review-revise-loop-proc`
  - `review-revise-loop`
- the public review-loop macro in `std/phase.orc` already expands to the ordinary procedure call:
  - `(std/phase/review-revise-loop-proc ...)`
- `std/phase.orc` already owns the promoted loop body:
  - `loop/recur`
  - typed loop state
  - `:on-exhausted`
  - `command-result validate_review_findings_v1`
  - `APPROVED` / `BLOCKED` / `EXHAUSTED` projection
- `orchestrator/workflow_lisp/stdlib_modules/std/phase_review_loop_support.orc` is already absent and must stay absent from the promoted route
- Python still carries the retired bridge surface:
  - `StdlibSpecializationExpr` in `orchestrator/workflow_lisp/expressions.py`
  - `__stdlib-specialization__` and `phase-review-loop` registry metadata in `orchestrator/workflow_lisp/form_registry.py`
  - review-loop bridge policy helpers in `orchestrator/workflow_lisp/phase_stdlib.py`
  - review-loop bridge typecheck owner code in `orchestrator/workflow_lisp/phase_stdlib_typecheck.py`
  - review-loop bridge lowerer guards and output-contract helpers in `orchestrator/workflow_lisp/lowering/phase_stdlib.py`
  - bridge delegations in `typecheck_dispatch.py`, `compiler.py`, `functions.py`, `stdlib_contracts.py`, and related session/plumbing modules
- focused tests have already been partially rewritten toward the direct route:
  - several focused suites now assert absence of `StdlibSpecializationExpr` and bridge-only registry text
  - remaining failures should be treated as direct-route stabilization or bridge-retirement work, not as authority to recreate the support-module path
  - the work-item context still classifies any surviving bridge-shaped assertions as cleanup targets, not competing authority
- the direct route is now blocked on ordinary canonicalization seams such as:
  - `[type_mismatch] procedure argument expected \`ReviewReportPath\` but got \`std/phase::ReviewReportPath\``
  - imported procedure signatures and proc-ref callback/result typing that still preserve local-versus-qualified spelling differences for the same `std/phase` export
  - validator-binding discovery that still needs to recognize the inlined ordinary `command-result`/`loop-recur` ownership shape
- the previously drafted broad final sweep can also be blocked by unrelated dirty-checkout reusable-phase-state relpath-contract failures under `orchestrator/contracts/output_contract.py`; those failures are not authority to widen this gap unless the failing stack traverses the touched review-loop footprint

## Scope Limits

In scope:

- preserve the already-landed single-body promoted review-loop implementation in `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- keep the promoted dependency on `orchestrator/workflow_lisp/stdlib_modules/std/phase_review_loop_support.orc` absent
- keep `review-revise-loop` as a thin syntax/ergonomics layer only:
  ordinary `std/phase` macro -> ordinary `review-revise-loop-proc` -> ordinary `loop/recur` / `match` / `command-result`
- finish the bounded same-module/imported type canonicalization and validator-binding visibility required by that direct route:
  local versus qualified `std/phase` type identity across procedure signatures, imported procedure signatures, proc-ref callbacks/results, loop-state carriers, generated seeds, and `command-result` return typing
- retire the review-loop-only bridge surface from Python:
  - `StdlibSpecializationExpr`
  - `__stdlib-specialization__`
  - `phase-review-loop`
  - review-loop allow/deny bridge policy plumbing
  - review-loop-only typecheck/lowering helpers that exist only for that bridge
- realign fixtures and tests so direct `std/phase` ownership is the only promoted route
- preserve the explicit findings-validation command boundary, typed loop-state behavior, `:on-exhausted` behavior, source maps, and review-loop result contracts

Out of scope:

- new imported `.orc` expansion capabilities
- new parametric specialization features, structural constraints, or loop-state authoring features
- runtime changes under `orchestrator/workflow/`
- redesign of other stdlib forms
- new scripts, new command adapters, report parsing, pointer-authority changes, or repo-wide cleanup outside this ownership footprint

## Locked Decisions

Do not reopen these during implementation:

- the Section `12.3` imported single-body consumer proof is already durable prerequisite evidence for this slice; consume it, do not re-implement it
- the findings-validation boundary stays explicit through `command-result validate_review_findings_v1`
- `ReviewLoopResult` remains the exact stdlib-owned terminal union; caller-specific terminal unions stay outside the stdlib loop
- `review-revise-loop` remains macro-bindable and importable from `std/phase`
- `review` and `fix` remain compile-time `ProcRef` hooks
- `EXHAUSTED` remains typed non-completion and is still authored through `:on-exhausted`
- reports remain views and typed state/artifact values remain authority
- authored local names such as `ReviewReportPath` and qualified references such as `std/phase/ReviewReportPath` are one semantic type identity when they resolve to the same `std/phase` export; fix canonicalization in the ordinary frontend route instead of introducing a new language feature or a new prerequisite gap
- do not begin bridge-expression, registry, typecheck, or lowering deletion until the focused direct-route canonicalization selectors pass; if canonical resolved-identity drift is still present, keep working inside this gap instead of escalating or recreating the bridge
- if a top-level compile helper must temporarily keep an outermost `review_loop_legacy_bridge_policy` keyword for call compatibility, it must become a dead compatibility shim only; no stage, context, or lowerer may still branch on it once this slice is complete
- unrelated dirty-checkout relpath-contract failures under `validate_reusable_phase_state` or `orchestrator/contracts/output_contract.py` are not authority to widen this gap unless the failing stack also traverses the touched review-loop footprint
- this checkout already contains unrelated live modifications in files that overlap the slice file map, so task checkpoints must not use unconditional `git add` / `git commit`; keep all verification unstaged, preserve unrelated edits, and use scoped `git status` / `git diff` evidence instead

## File Map

Modify:

- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- `orchestrator/workflow_lisp/modules.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/form_registry.py`
- `orchestrator/workflow_lisp/expression_traversal.py`
- `orchestrator/workflow_lisp/typecheck_dispatch.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/functions.py`
- `orchestrator/workflow_lisp/typecheck_effects.py`
- `orchestrator/workflow_lisp/stdlib_contracts.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/typecheck_context.py`
- `orchestrator/workflow_lisp/procedure_typecheck.py`
  - if focused direct-route canonicalization failures prove ordinary procedure-signature ownership needs the change
- `orchestrator/workflow_lisp/workflows.py`
  - if focused direct-route canonicalization failures prove ordinary workflow/proc callback ownership needs the change
- `orchestrator/workflow_lisp/lowering/core.py`
- `orchestrator/workflow_lisp/lowering/phase_scope.py`
- `orchestrator/workflow_lisp/README.md`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_expressions.py`
- `tests/test_workflow_lisp_macros.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_key_migrations.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_modules.py`
- `tests/test_workflow_lisp_diagnostics.py`

Delete if no remaining caller justifies keeping them:

- `orchestrator/workflow_lisp/phase_stdlib_typecheck.py`
- `orchestrator/workflow_lisp/lowering/phase_stdlib.py`

Verify absent and do not recreate:

- `orchestrator/workflow_lisp/stdlib_modules/std/phase_review_loop_support.orc`

Do not widen into unrelated files unless a focused failing test proves the need.

## Acceptance Target

This slice is complete only when all of the following are true:

- `std/phase.orc` is the only promoted stdlib owner of:
  - the review-loop body
  - hidden relpath seeds
  - the public `review-revise-loop` macro
  - the exact `ReviewDecision` / `ReviewFindings` / `ReviewLoopResult` protocol
- `std/phase.orc` does not import `std/phase_review_loop_support`, and the deleted support module stays absent
- ordinary same-module and imported references to the same `std/phase` export type-check as one canonical type identity at the direct review-loop boundaries, including procedure signatures, proc-ref callbacks/results, loop-state carriers, generated seeds, and `command-result` returns
- the promoted route no longer depends on `StdlibSpecializationExpr`, `__stdlib-specialization__`, or `phase-review-loop`
- there is no review-loop-only branch left in active typecheck/lowering/compiler code
- the promoted route compiles solely through ordinary imported stdlib/module compilation, shared lowering, and shared validation
- stale tests now prove:
  - direct stdlib ownership
  - bridge absence
  - unchanged typed review-loop behavior
- runtime-backed direct-route evidence proves `APPROVE`, `REVISE -> fix -> APPROVE`, `BLOCKED`, and `EXHAUSTED`
- a public `.orc` compile smoke and a public `.orc` `run --dry-run` smoke both pass for `phase_stdlib_review_loop.orc`
- findings validation still occurs before `fix` consumes findings and before final findings are published
- evidence-redirection rejection and source-map/build-artifact provenance still pass for the direct route
- source-map and build-artifact checks still pass for the direct route
- if broader reusable-phase-state selectors fail only through unrelated dirty-checkout relpath-contract changes outside the touched review-loop footprint, those failures are recorded exactly and not absorbed into this slice
- `git diff --check` passes

## Task 0: Freeze The Current Checkout Evidence

**Files:**

- Verify only: `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- Verify only: `orchestrator/workflow_lisp/expressions.py`
- Verify only: `orchestrator/workflow_lisp/form_registry.py`
- Verify only: `orchestrator/workflow_lisp/typecheck_dispatch.py`
- Verify only: `orchestrator/workflow_lisp/compiler.py`
- Verify only: `orchestrator/workflow_lisp/phase_stdlib.py`
- Verify only: `orchestrator/workflow_lisp/phase_stdlib_typecheck.py`
- Verify only: `orchestrator/workflow_lisp/lowering/phase_stdlib.py`
- Verify only: `tests/test_workflow_lisp_phase_stdlib.py`
- Verify only: `tests/test_workflow_lisp_procedures.py`

- [ ] **Step 1: Confirm the direct stdlib owner is already in place**

Run:

```bash
rg -n \
  "defproc review-revise-loop-proc|defmacro review-revise-loop|ReviewLoopResult|validate_review_findings_v1|phase_review_loop_support" \
  orchestrator/workflow_lisp/stdlib_modules/std/phase.orc
```

Expected: `std/phase.orc` already owns the promoted loop body, exports the
review-loop protocol, and contains the `command-result
validate_review_findings_v1` boundary directly.

- [ ] **Step 2: Confirm the retired bridge surfaces still exist only in Python**

Run:

```bash
rg -n \
  "StdlibSpecializationExpr|__stdlib-specialization__|phase-review-loop|review_loop_legacy_bridge_policy" \
  orchestrator/workflow_lisp
```

Expected: hits remain in Python owner modules only. There should be no reason
to recreate the deleted support-module route in `.orc`.

- [ ] **Step 3: Confirm the old support module stays absent**

Run:

```bash
test ! -e orchestrator/workflow_lisp/stdlib_modules/std/phase_review_loop_support.orc
```

Expected: success with no output.

- [ ] **Step 4: Freeze the current focused test surface before rewriting it**

Run:

```bash
rg -n \
  "ReviewReportPath|ReviewFindings|ReviewDecision|ReviewLoopResult" \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_macros.py \
  tests/test_workflow_lisp_modules.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_key_migrations.py
```

Expected: the review-loop protocol is already covered across focused suites,
and any remaining bridge-era assertions can be identified as cleanup targets
before Task 1 rewrites them.

## Task 1: Rewrite The Test Surface Around Direct Ownership

**Files:**

- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_expressions.py`
- Modify: `tests/test_workflow_lisp_macros.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify if needed: `tests/test_workflow_lisp_build_artifacts.py`
- Modify if needed: `tests/test_workflow_lisp_key_migrations.py`
- Modify if needed: `tests/test_workflow_lisp_procedures.py`
- Modify if needed: `tests/test_workflow_lisp_modules.py`
- Modify if needed: `tests/test_workflow_lisp_diagnostics.py`

- [ ] **Step 1: Replace stale bridge assertions with direct-ownership assertions**

Update the focused review-loop tests so they assert the current target shape instead of the old bridge:

- `std/phase.orc` contains the loop body or direct ownership markers rather than an imported support-module bridge
- `review-revise-loop` compiles without surviving `StdlibSpecializationExpr` nodes
- `review-revise-loop` remains importable from `std/phase`
- direct stdlib ownership preserves the current typed `ReviewLoopResult` behavior

Delete or rewrite tests that currently assert:

- bridge-policy allow/deny behavior on the promoted fixture
- literal `(__stdlib-specialization__ phase-review-loop` text in `std/phase.orc`
- `StdlibSpecializationExpr` / `__stdlib-specialization__` as the expected review-loop route

- [ ] **Step 2: Add or finish narrow architecture guards for bridge retirement**

Add source-structure assertions that express the promoted target state:

- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` must not import `std/phase_review_loop_support`
- `orchestrator/workflow_lisp/form_registry.py` must not register `__stdlib-specialization__` or `phase-review-loop`
- `orchestrator/workflow_lisp/expressions.py` must not define `StdlibSpecializationExpr`
- active owner modules must not reference `review_loop_legacy_bridge_policy` except for an outermost temporary compatibility shim if one is needed

- [ ] **Step 3: Preserve the behavioral selectors that prove direct stdlib behavior**

Keep the existing focused behavior suites as the primary review-loop regression owners:

- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_key_migrations.py`

Do not replace those with broad snapshots.

If the current checkout does not already have them, add deterministic direct-route runtime/integration proofs in `tests/test_workflow_lisp_key_migrations.py` for:

- `APPROVE`
- `REVISE -> fix -> APPROVE`
- `BLOCKED`
- `EXHAUSTED`
- evidence-redirection rejection

Keep those proofs on the existing `phase_stdlib_review_loop.orc` fixture and ordinary imported-stdlib route. Do not add a second bridge-only harness.

- [ ] **Step 4: Run the red-phase slice against the current hybrid checkout**

Run:

```bash
python -m pytest --collect-only \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_macros.py \
  tests/test_workflow_lisp_modules.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_key_migrations.py \
  tests/test_workflow_lisp_diagnostics.py \
  -q
```

Then run:

```bash
python -m pytest \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_macros.py \
  -k 'review_loop or stdlib' \
  -q
```

Expected at this stage: collect-only should pass, the support-module absence guard should already pass, and any remaining failures should come from the still-live bridge expression/registry/policy surfaces or the direct-route type canonicalization seam, not from recreating the removed support-module hop.

- [ ] **Step 5: Capture a scoped dirty-checkout checkpoint without staging**

```bash
git status --short -- \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_macros.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_key_migrations.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_modules.py \
  tests/test_workflow_lisp_diagnostics.py
git diff --stat -- \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_macros.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_key_migrations.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_modules.py \
  tests/test_workflow_lisp_diagnostics.py
```

Expected: only the task-owned test files show review-loop ownership cleanup for
this slice, no unrelated edits are staged, and any pre-existing modifications
outside this task remain untouched.

## Task 2: Stabilize The Direct Ownership Typing Route

**Files:**

- Modify: `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- Modify: `orchestrator/workflow_lisp/modules.py`
- Modify: `orchestrator/workflow_lisp/type_env.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/typecheck_effects.py`
- Modify if needed: `orchestrator/workflow_lisp/procedure_typecheck.py`
- Modify if needed: `orchestrator/workflow_lisp/workflows.py`
- Modify if needed: `orchestrator/workflow_lisp/typecheck_context.py`
- Modify if needed: `tests/fixtures/workflow_lisp/valid/phase_stdlib_review_loop.orc`
- Modify if needed: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify if needed: `tests/test_workflow_lisp_procedures.py`

- [ ] **Step 1: Finish local-versus-qualified type canonicalization for the direct route**

Keep `review-revise-loop-proc` in `std/phase.orc`, but finish the ordinary
frontend normalization that the inlined same-module route exposed so
procedure-signature compatibility, imported procedure signatures, proc-ref
callbacks/results, loop-state carriers, generated seeds, and command-result
return typing treat these as one canonical resolved type identity when they
refer to the same exported stdlib type:

- `ReviewReportPath` and `std/phase::ReviewReportPath`
- `ReviewFindings` and `std/phase::ReviewFindings`
- `ReviewDecision` and `std/phase::ReviewDecision`
- `ReviewLoopResult` and `std/phase::ReviewLoopResult`

Preserve the existing protocol and paths exactly. Do not redesign the result schema or the findings-validation command boundary.

If focused failures show that the remaining mismatch lives in the ordinary
procedure-signature owners rather than only `modules.py`/`type_env.py`, make
the minimal changes in `procedure_typecheck.py`, `workflows.py`, or
`typecheck_context.py` needed to compare canonical resolved identities there
too. Treat that as in-scope follow-through for this gap, not as a new
prerequisite.

- [ ] **Step 2: Keep validator-binding visibility explicit for the inlined route**

Ensure the direct route remains visible to the ordinary command/effect
surfaces:

- `validate_review_findings_v1` stays visible through ordinary
  `command-result` typing/effect discovery
- validator-binding discovery sees the inlined `loop/recur`/`command-result`
  ownership shape without bridge-specific detection
- no hidden Python fallback replaces the ordinary command boundary

- [ ] **Step 3: Keep the macro thin and keep the support-module route absent**

`review-revise-loop` should remain only an ergonomics layer that creates hidden
seed values and calls `std/phase/review-revise-loop-proc`. No fixture,
source-map assertion, or import path should recreate
`std/phase_review_loop_support.orc` as current authority.

- [ ] **Step 4: Run focused stdlib/procedure checks**

Run:

```bash
python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k review_loop -q
```

Then run:

```bash
python -m pytest tests/test_workflow_lisp_procedures.py -k 'review_loop or imported_generic_loop_state_consumer' -q
```

Then run:

```bash
python -m pytest tests/test_workflow_lisp_phase_stdlib.py::test_review_loop_entrypoint_smoke -q
```

Expected: review-loop behavior still passes with no support-module dependency,
and the canonical resolved-identity seam is closed before any bridge-removal
task begins.

- [ ] **Step 5: Capture a scoped dirty-checkout checkpoint without staging**

```bash
git status --short -- \
  orchestrator/workflow_lisp/stdlib_modules/std/phase.orc \
  orchestrator/workflow_lisp/modules.py \
  orchestrator/workflow_lisp/type_env.py \
  orchestrator/workflow_lisp/compiler.py \
  orchestrator/workflow_lisp/typecheck_effects.py \
  orchestrator/workflow_lisp/procedure_typecheck.py \
  orchestrator/workflow_lisp/workflows.py \
  orchestrator/workflow_lisp/typecheck_context.py \
  tests/fixtures/workflow_lisp/valid/phase_stdlib_review_loop.orc \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_procedures.py
git diff --stat -- \
  orchestrator/workflow_lisp/stdlib_modules/std/phase.orc \
  orchestrator/workflow_lisp/modules.py \
  orchestrator/workflow_lisp/type_env.py \
  orchestrator/workflow_lisp/compiler.py \
  orchestrator/workflow_lisp/typecheck_effects.py \
  orchestrator/workflow_lisp/procedure_typecheck.py \
  orchestrator/workflow_lisp/workflows.py \
  orchestrator/workflow_lisp/typecheck_context.py \
  tests/fixtures/workflow_lisp/valid/phase_stdlib_review_loop.orc \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_procedures.py
```

Expected: the diff stays inside the canonicalization and validator-visibility
owners for this slice, with no staging and no accidental bundling of unrelated
dirty-worktree edits.

Do not start Task 3 until the Task 2 selectors above pass. If they still fail
only on canonical resolved-identity drift, continue within this task rather
than widening the gap or reintroducing bridge scaffolding.

## Task 3: Remove The Review-Loop Bridge Expression And Registry Surface

**Files:**

- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/form_registry.py`
- Modify: `orchestrator/workflow_lisp/expression_traversal.py`
- Modify: `orchestrator/workflow_lisp/functions.py`
- Modify if needed: `orchestrator/workflow_lisp/compiler.py`
- Modify if needed: `tests/test_workflow_lisp_expressions.py`
- Modify if needed: `tests/test_workflow_lisp_macros.py`
- Modify if needed: `tests/test_workflow_lisp_lowering.py`

- [ ] **Step 1: Remove `StdlibSpecializationExpr` from the frontend expression surface**

Delete the review-loop-only bridge type and its elaboration helpers from `expressions.py`:

- `StdlibSpecializationExpr`
- `_elaborate_stdlib_specialization(...)`
- `_elaborate_phase_review_loop_specialization(...)`

Update the `ExprNode` union and any traversal helpers accordingly.

- [ ] **Step 2: Remove registry metadata that exists only for the bridge**

Delete the bridge-only registry surfaces:

- `__stdlib-specialization__`
- `_STDLIB_REQUEST_KIND_FEATURES["phase-review-loop"]`
- any feature-tag logic that exists only to detect the retired review-loop bridge

Keep `review-revise-loop` macro-bindable and import-routed through `std/phase`.

- [ ] **Step 3: Clean up review-loop-specific purity and discovery hooks**

Update helper modules that still classify review-loop through the removed bridge:

- `functions.py`
- `compiler.py`

Preserve any remaining direct-ownership detection that is still genuinely needed for validator-binding registration or fixture discovery, but remove all bridge-request-kind logic.

- [ ] **Step 4: Run expression/macro/lowering checks**

Run:

```bash
python -m pytest \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_macros.py \
  tests/test_workflow_lisp_lowering.py \
  -k 'review_loop or stdlib' \
  -q
```

Expected: review-loop is now represented only by ordinary macro/procedure/module surfaces.

- [ ] **Step 5: Capture a scoped dirty-checkout checkpoint without staging**

```bash
git status --short -- \
  orchestrator/workflow_lisp/expressions.py \
  orchestrator/workflow_lisp/form_registry.py \
  orchestrator/workflow_lisp/expression_traversal.py \
  orchestrator/workflow_lisp/functions.py \
  orchestrator/workflow_lisp/compiler.py \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_macros.py \
  tests/test_workflow_lisp_lowering.py
git diff --stat -- \
  orchestrator/workflow_lisp/expressions.py \
  orchestrator/workflow_lisp/form_registry.py \
  orchestrator/workflow_lisp/expression_traversal.py \
  orchestrator/workflow_lisp/functions.py \
  orchestrator/workflow_lisp/compiler.py \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_macros.py \
  tests/test_workflow_lisp_lowering.py
```

Expected: only the bridge-expression and registry-retirement files move at this
checkpoint, and the checkout remains fully unstaged.

## Task 4: Retire Bridge-Only Typecheck, Lowering, And Policy Plumbing

**Files:**

- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/typecheck_context.py`
- Modify: `orchestrator/workflow_lisp/procedure_typecheck.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `orchestrator/workflow_lisp/stdlib_contracts.py`
- Modify: `orchestrator/workflow_lisp/diagnostics.py`
- Modify: `orchestrator/workflow_lisp/lowering/core.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_scope.py`
- Delete if unused: `orchestrator/workflow_lisp/phase_stdlib_typecheck.py`
- Delete if unused: `orchestrator/workflow_lisp/lowering/phase_stdlib.py`
- Modify: `orchestrator/workflow_lisp/README.md`
- Modify if needed: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify if needed: `tests/test_workflow_lisp_diagnostics.py`

- [ ] **Step 1: Remove bridge-policy flow through typecheck and compile entrypoints**

Strip review-loop-only `review_loop_legacy_bridge_policy` branching from the active pipeline:

- typecheck session state/context
- compiler stage entrypoints
- workflow typecheck/build helpers
- lowering entrypoints

If an outer public helper must keep the keyword temporarily for compatibility, make it inert there and remove it from all internal state and control flow.

- [ ] **Step 2: Remove the bridge-only typecheck owner seam**

Delete the review-loop-specific delegation in `typecheck_dispatch.py` and remove `phase_stdlib_typecheck.py` if it has no remaining non-bridge responsibility.

Do not rehost that logic elsewhere. The direct stdlib route should no longer need:

- `typecheck_stdlib_specialization_expr(...)`
- `validate_review_loop_result_contract(...)`
- generated bridge wrapper/typecheck helpers

- [ ] **Step 3: Remove bridge-only lowering guards and output-contract helpers**

Delete the review-loop-special lowerer guard and any dead wrapper functions that exist only because lowering once saw `StdlibSpecializationExpr`.

After the bridge is gone:

- `lowering/core.py` should not import review-loop bridge helpers
- `lowering/phase_scope.py` should not proxy review-loop-only contract builders
- `lowering/phase_stdlib.py` should be deleted if it has no remaining owner role

- [ ] **Step 4: Realign diagnostics and contract inventories**

Update the supporting inventories so they reflect the direct route:

- remove diagnostics that only existed for the bridge if nothing still raises them
- update `stdlib_contracts.py` so the review-loop contract no longer claims `expr_type=StdlibSpecializationExpr` or bridge owner modules
- update `README.md` so the ownership map no longer advertises bridge-only modules

- [ ] **Step 5: Run focused diagnostics checks when bridge-retirement diagnostics or inventories move**

Run:

```bash
python -m pytest tests/test_workflow_lisp_diagnostics.py -k 'review_loop or stdlib_special_form_disallowed or review_loop_special_lowerer_used' -q
```

Expected: any retained or rewritten diagnostics around the retired bridge compile surface still prove the intended frontend error contract.

- [ ] **Step 6: Run focused lower/build/migration checks**

Run:

```bash
python -m pytest \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_key_migrations.py \
  -k 'review_loop or repeat_until or source_map' \
  -q
```

Expected: lower/build/provenance checks still pass with no bridge-only owner modules.

- [ ] **Step 7: Capture a scoped dirty-checkout checkpoint without staging**

```bash
git status --short -- \
  orchestrator/workflow_lisp/typecheck_dispatch.py \
  orchestrator/workflow_lisp/compiler.py \
  orchestrator/workflow_lisp/typecheck_context.py \
  orchestrator/workflow_lisp/procedure_typecheck.py \
  orchestrator/workflow_lisp/workflows.py \
  orchestrator/workflow_lisp/stdlib_contracts.py \
  orchestrator/workflow_lisp/diagnostics.py \
  orchestrator/workflow_lisp/lowering/core.py \
  orchestrator/workflow_lisp/lowering/phase_scope.py \
  orchestrator/workflow_lisp/phase_stdlib_typecheck.py \
  orchestrator/workflow_lisp/lowering/phase_stdlib.py \
  orchestrator/workflow_lisp/README.md \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_diagnostics.py
git diff --stat -- \
  orchestrator/workflow_lisp/typecheck_dispatch.py \
  orchestrator/workflow_lisp/compiler.py \
  orchestrator/workflow_lisp/typecheck_context.py \
  orchestrator/workflow_lisp/procedure_typecheck.py \
  orchestrator/workflow_lisp/workflows.py \
  orchestrator/workflow_lisp/stdlib_contracts.py \
  orchestrator/workflow_lisp/diagnostics.py \
  orchestrator/workflow_lisp/lowering/core.py \
  orchestrator/workflow_lisp/lowering/phase_scope.py \
  orchestrator/workflow_lisp/phase_stdlib_typecheck.py \
  orchestrator/workflow_lisp/lowering/phase_stdlib.py \
  orchestrator/workflow_lisp/README.md \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_diagnostics.py
```

Expected: the checkpoint shows only bridge-plumbing retirement changes and
keeps the overlapping dirty checkout unbundled.

## Task 5: Final Verification And Handoff

**Files:**

- Verify only: touched files from Tasks 1-4

- [ ] **Step 1: Re-run the work-item verification bundle exactly**

Run the direct review-loop verification bundle first. This bundle must close the
target-design Stage 13 evidence gap for this bounded slice by covering:

- compile/shared-validation through the direct imported-stdlib route;
- runtime-backed fake-provider integration for `APPROVE`, `REVISE -> APPROVE`,
  `BLOCKED`, and `EXHAUSTED`;
- evidence-redirection rejection;
- public `python -m orchestrator` compile and `run --dry-run` smoke commands
  against the promoted `.orc` fixture.

Run:

```bash
python -m pytest --collect-only \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_macros.py \
  tests/test_workflow_lisp_modules.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_key_migrations.py \
  tests/test_workflow_lisp_diagnostics.py \
  -q
```

```bash
python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k review_loop -q
```

```bash
python -m pytest tests/test_workflow_lisp_phase_stdlib.py::test_review_loop_entrypoint_smoke -q
```

```bash
python -m pytest tests/test_workflow_lisp_procedures.py -k 'review_loop or imported_generic_loop_state_consumer' -q
```

```bash
python -m pytest \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_macros.py \
  tests/test_workflow_lisp_modules.py \
  -k 'review_loop or stdlib' \
  -q
```

```bash
python -m pytest \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_key_migrations.py \
  -k 'review_loop or repeat_until or source_map' \
  -q
```

```bash
python -m pytest tests/test_workflow_lisp_diagnostics.py -k 'review_loop or stdlib_special_form_disallowed or review_loop_special_lowerer_used' -q
```

```bash
python -m pytest \
  tests/test_workflow_lisp_key_migrations.py::test_review_loop_parity_fixture_compiles_to_resume_safe_repeat_until_via_imported_stdlib_route \
  tests/test_workflow_lisp_key_migrations.py::test_review_loop_imported_stdlib_route_approves_via_fake_provider \
  tests/test_workflow_lisp_key_migrations.py::test_review_loop_imported_stdlib_route_revises_then_approves_via_fake_provider \
  tests/test_workflow_lisp_key_migrations.py::test_review_loop_imported_stdlib_route_blocks_via_fake_provider \
  tests/test_workflow_lisp_key_migrations.py::test_review_loop_imported_stdlib_route_exhausts_via_fake_provider \
  tests/test_workflow_lisp_key_migrations.py::test_review_loop_imported_stdlib_route_rejects_evidence_redirection \
  tests/test_workflow_lisp_key_migrations.py::test_review_loop_imported_stdlib_route_resumes_after_revise_checkpoint \
  tests/test_workflow_lisp_build_artifacts.py::test_review_loop_command_boundary_surfaces_validate_review_findings_adapter \
  tests/test_workflow_lisp_build_artifacts.py::test_review_loop_bundle_preserves_distinct_review_report_and_findings_seed_paths \
  -q
```

```bash
tmpdir=.orchestrate/tmp/workflow-lisp-review-loop-smoke
rm -rf "$tmpdir"
mkdir -p "$tmpdir"/prompts/implementation "$tmpdir"/artifacts/work
printf 'prompt\n' > "$tmpdir"/prompts/implementation/review.md
printf 'prompt\n' > "$tmpdir"/prompts/implementation/fix.md
printf 'seed\n' > "$tmpdir"/artifacts/work/seed_execution_report.md
printf 'seed\n' > "$tmpdir"/artifacts/work/design_review_prompt.md
printf 'seed\n' > "$tmpdir"/artifacts/work/fix_plan_prompt.md
cat > "$tmpdir"/providers.json <<'EOF'
{
  "providers.review": "fake-review",
  "providers.fix": "fake-fix"
}
EOF
cat > "$tmpdir"/prompts.json <<'EOF'
{
  "prompts.implementation.review": ".orchestrate/tmp/workflow-lisp-review-loop-smoke/prompts/implementation/review.md",
  "prompts.implementation.fix": ".orchestrate/tmp/workflow-lisp-review-loop-smoke/prompts/implementation/fix.md"
}
EOF
cat > "$tmpdir"/commands.json <<'EOF'
{
  "validate_review_findings_v1": {
    "kind": "external_tool",
    "stable_command": [
      "python",
      "-m",
      "orchestrator.workflow_lisp.adapters.validate_review_findings_v1"
    ]
  }
}
EOF
```

```bash
python -m orchestrator compile tests/fixtures/workflow_lisp/valid/phase_stdlib_review_loop.orc \
  --entry-workflow phase_stdlib_review_loop::review-revise-loop-demo \
  --provider-externs-file .orchestrate/tmp/workflow-lisp-review-loop-smoke/providers.json \
  --prompt-externs-file .orchestrate/tmp/workflow-lisp-review-loop-smoke/prompts.json \
  --command-boundaries-file .orchestrate/tmp/workflow-lisp-review-loop-smoke/commands.json \
  --emit-semantic-ir .orchestrate/tmp/workflow-lisp-review-loop-smoke/semantic_ir.json \
  --emit-source-map .orchestrate/tmp/workflow-lisp-review-loop-smoke/source_map.json \
  --emit-debug-yaml .orchestrate/tmp/workflow-lisp-review-loop-smoke/expanded.debug.yaml
```

```bash
python -m orchestrator run tests/fixtures/workflow_lisp/valid/phase_stdlib_review_loop.orc \
  --entry-workflow phase_stdlib_review_loop::review-revise-loop-demo \
  --provider-externs-file .orchestrate/tmp/workflow-lisp-review-loop-smoke/providers.json \
  --prompt-externs-file .orchestrate/tmp/workflow-lisp-review-loop-smoke/prompts.json \
  --command-boundaries-file .orchestrate/tmp/workflow-lisp-review-loop-smoke/commands.json \
  --input completed__execution_report_path=.orchestrate/tmp/workflow-lisp-review-loop-smoke/artifacts/work/seed_execution_report.md \
  --input inputs__design_review_prompt=.orchestrate/tmp/workflow-lisp-review-loop-smoke/artifacts/work/design_review_prompt.md \
  --input inputs__fix_plan_prompt=.orchestrate/tmp/workflow-lisp-review-loop-smoke/artifacts/work/fix_plan_prompt.md \
  --dry-run
```

```bash
git diff --check
```

Then, if the checkout is otherwise stable enough, run any broader reusable-phase-state compatibility selectors required by the current branch state. If those broader selectors fail only through unrelated `validate_reusable_phase_state` / `orchestrator/contracts/output_contract.py` relpath-contract paths and the failing stack does not traverse the touched review-loop footprint, record the exact failing command and stack summary as out-of-slice dirty-checkout evidence instead of widening this gap.

- [ ] **Step 2: Record any narrowly justified compatibility shim**

If the final code retains an outermost inert compatibility keyword for `review_loop_legacy_bridge_policy`, document exactly where and why. Otherwise state explicitly that the plumbing was fully removed.

- [ ] **Step 3: Handoff notes**

Record in the execution handoff:

- that `std/phase.orc` now owns the promoted route end-to-end
- whether `phase_review_loop_support.orc`, `phase_stdlib_typecheck.py`, and `lowering/phase_stdlib.py` were deleted
- which stale bridge assertions were rewritten
- the exact verification commands and outcomes
- whether any final commit was intentionally deferred because the checkout
  still contained overlapping unrelated edits
