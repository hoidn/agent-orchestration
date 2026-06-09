# Workflow Lisp Track A Denylist And Architecture Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the bounded Track A promoted-route denylist so promoted Workflow Lisp compilation rejects the current review-loop compatibility bridge with stable frontend diagnostics while explicit legacy mode still permits the bridge, and lock that boundary in with the required architecture tests.

**Architecture:** Keep the public `review-revise-loop` surface macro-bindable and keep the current `__stdlib-specialization__ phase-review-loop` bridge intact for explicit legacy compilation only. Route the new denylist behavior through small review-loop owner/helper modules under `orchestrator/workflow_lisp/` and `orchestrator/workflow_lisp/lowering/`, keep `compiler.py`, `expressions.py`, `typecheck.py`, and `lowering/core.py` limited to keyword-threading and delegation glue, and add checkout-aware architecture plus diagnostics tests that prove promoted mode fails closed on the current bridge while legacy mode still works intentionally.

**Tech Stack:** Python, Workflow Lisp frontend modules under `orchestrator/workflow_lisp/`, imported `std/phase` fixtures, `pytest`

---

## Scope Guardrails

- Primary authorities:
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-track-a-denylist-architecture-tests/implementation_architecture.md`
  - `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-owner-seam-split-prerequisite/implementation_architecture.md`
  - `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/2/design-gap-architect/work_item_context.md`
  - `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

- Additional governing context:
  - `docs/plans/2026-06-02-workflow-lisp-generic-orc-expansion-refactor.md`
  - `docs/design/workflow_lisp_refactor_architecture.md`
  - `docs/design/workflow_command_adapter_contract.md`
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`

- Current-checkout prerequisite facts:
  - `orchestrator/workflow_lisp/compiler.py`, `expressions.py`, `typecheck.py`, and `lowering/core.py` are still 3,064 / 2,797 / 5,855 / 9,907 physical lines in this checkout.
  - The target design's hard preflight says follow-on Track A work must not add new behavior directly inside oversized frontend facades; new denylist logic must land in explicit owner/helper modules and the facades may receive only narrow delegation glue.
  - The landed owner-seam prerequisite already established the pattern for this repo: keep large public modules as compatibility/coordinator surfaces and route follow-on behavior into small owner files.

- In scope:
  - add one Stage 3 compile-policy surface with modes `allow` and `deny`, defaulting to `allow`;
  - create or extend explicit small review-loop owner/helper modules so the denylist policy, typed bridge checks, and lowering guard do not land as new inline behavior in oversized facades;
  - reject the current review-loop compatibility bridge in promoted denylist mode at elaboration, typecheck, and lowering boundaries;
  - add stable frontend diagnostics for promoted-route bridge rejection;
  - add the required Stage 4 architecture tests:
    `test_no_review_loop_expr_in_core_ast_union`,
    `test_review_revise_loop_not_reserved_core_macro_name`,
    `test_review_revise_loop_not_elaborated_by_head_name`,
    `test_typecheck_does_not_import_review_loop_expr`,
    `test_lowering_does_not_import_review_loop_expr`;
  - add one negative promoted compile test and one explicit legacy-opt-in compile test against the same public review-loop fixture through `compile_stage3_module(...)`, plus paired direct `compile_stage3_entrypoint(...)` deny/allow coverage so both public Stage 3 entry surfaces are exercised;
  - add dedicated diagnostics-surface verification in `tests/test_workflow_lisp_diagnostics.py` for the new denylist diagnostic metadata.

- Explicitly out of scope:
  - imported `.orc` inline expansion, imported source-map/effect visibility work, or generic specialization;
  - deletion of `StdlibSpecializationExpr`, `phase-review-loop`, `_typecheck_stdlib_specialization_expr(...)`, `_validate_review_loop_result_contract(...)`, `_review_loop_result_case_outputs(...)`, or `_review_loop_result_output_contracts(...)`;
  - parametric `defproc`, structural constraints, `loop/recur` exhaustion projection, or authored stdlib replacement logic;
  - shared validation/runtime changes under `orchestrator/workflow/`;
  - edits to `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` beyond compatibility-preserving inspection;
  - unrelated frontend refactors, registry redesign, or docs churn outside this plan artifact.

## Files And Responsibilities

- New or expanded review-loop owner/helper surfaces:
  - Modify: `orchestrator/workflow_lisp/phase_stdlib.py`
  - Create: `orchestrator/workflow_lisp/phase_stdlib_typecheck.py`
  - Create: `orchestrator/workflow_lisp/lowering/phase_stdlib.py`
  - Modify: `orchestrator/workflow_lisp/diagnostics.py`

- Delegation-only facade updates:
  - Modify: `orchestrator/workflow_lisp/compiler.py`
  - Modify: `orchestrator/workflow_lisp/expressions.py`
  - Modify: `orchestrator/workflow_lisp/typecheck.py`
  - Modify: `orchestrator/workflow_lisp/lowering/core.py`

- Reused configuration/contract surfaces:
  - Inspect only unless a tiny helper reuse is unavoidable: `orchestrator/workflow_lisp/form_registry.py`
  - Inspect only: `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
  - Modify if helper-owner metadata needs to stay current: `orchestrator/workflow_lisp/stdlib_contracts.py`

- Test surfaces:
  - Modify: `tests/test_workflow_lisp_macros.py`
  - Modify: `tests/test_workflow_lisp_expressions.py`
  - Modify: `tests/test_workflow_lisp_phase_stdlib.py`
  - Modify: `tests/test_workflow_lisp_lowering.py`
  - Modify: `tests/test_workflow_lisp_diagnostics.py`

Files intentionally not owned in this slice:

- `orchestrator/workflow_lisp/modules.py`
- `orchestrator/workflow_lisp/procedures.py`
- `orchestrator/workflow_lisp/workflow_refs.py`
- `orchestrator/workflow_lisp/procedure_specialization.py`
- shared runtime/validation modules under `orchestrator/workflow/`

## Implementation Architecture

### Unit 1: Review-Loop Bridge Policy Owner

- Own the bridge-policy contract in `orchestrator/workflow_lisp/phase_stdlib.py`.
- Stable contract:
  - `review_loop_legacy_bridge_policy: Literal["allow", "deny"] = "allow"` remains a frontend-local Stage 3 compile concern only.
  - `phase_stdlib.py` owns the review-loop bridge request-kind constants, small helper dataclasses or predicates needed to classify `phase-review-loop`, and the shared deny-diagnostic builder/helper used by later stages.
  - `compile_stage3_module(...)` and `compile_stage3_entrypoint(...)` may grow the keyword-only policy argument, but `compiler.py` must remain a coordinator that threads the value into owner helpers instead of accumulating new review-loop semantics.
  - `expressions.py` may keep the public elaboration entrypoints, but the review-loop-specific deny decision must delegate into the owner helper rather than add new inline policy branches to the facade.
  - The policy must not become a CLI flag, environment variable, shared-validation knob, or runtime switch.

### Unit 2: Review-Loop Typed Bridge Owner

- Own the review-loop compatibility typecheck path in `orchestrator/workflow_lisp/phase_stdlib_typecheck.py`.
- Stable contract:
  - Move or wrap the review-loop-specific typed bridge helpers there before adding new denylist behavior:
    `_validate_review_loop_result_contract(...)`,
    `_typecheck_stdlib_specialization_expr(...)`,
    and the generated-review-loop rewrite helpers they depend on.
  - `typecheck.py` may keep import-compatible wrapper functions or dispatch glue, but it must stop being the only owner of new review-loop denylist behavior.
  - Promoted deny mode must fail with `stdlib_special_form_disallowed` if a review-loop compatibility `StdlibSpecializationExpr` still reaches typed elaboration.
  - Legacy allow mode must keep the current typed bridge behavior intact.

### Unit 3: Review-Loop Lowering Owner

- Own the lowering-side review-loop bridge helpers in `orchestrator/workflow_lisp/lowering/phase_stdlib.py`.
- Stable contract:
  - Move or wrap the review-loop-specific lowering helpers there before adding the last-resort deny guard:
    `_review_loop_result_case_outputs(...)` and `_review_loop_result_output_contracts(...)`.
  - `lowering/core.py` may keep import-compatible wrappers or one delegation call site, but it must not gain new review-loop-specific lowering logic for this slice.
  - Promoted deny mode must raise `review_loop_special_lowerer_used` if a denied bridge still reaches the lowering owner.
  - Keep source-map/provenance behavior unchanged except for the new fail-closed diagnostics.

### Unit 4: Checkout-Aware Architecture And Diagnostics Tests

- Own the regression tests in:
  `tests/test_workflow_lisp_macros.py`,
  `tests/test_workflow_lisp_expressions.py`,
  `tests/test_workflow_lisp_phase_stdlib.py`,
  `tests/test_workflow_lisp_lowering.py`,
  and `tests/test_workflow_lisp_diagnostics.py`.
- Stable contract:
  - historical `ReviewReviseLoopExpr` remains absent from the AST union and must not reappear under that old name;
  - direct elaboration dispatch must not regain a `review-revise-loop` head-name branch;
  - typecheck and lowering tests guard against reintroducing imports or explicit dependencies on the historical review-loop AST surface;
  - promoted-mode tests prove the current renamed bridge still fails closed through both `compile_stage3_module(...)` and `compile_stage3_entrypoint(...)`, while explicit legacy mode proves compatibility remains intentionally available on both surfaces;
  - diagnostics metadata tests live on the repo's dedicated diagnostics surface rather than only as incidental assertions inside the phase-stdlib suite.

### Dependency Direction

- Unit 1 lands first because the tests and later enforcement need a stable helper-owned policy surface to target.
- Unit 2 and Unit 3 depend on Unit 1 because the policy must be available at elaboration, typecheck, and lowering call sites.
- Unit 4 depends on Units 1-3 because the tests should lock the final helper-owned deny/allow behavior and diagnostic metadata, not a partial wiring.

### Sequencing Constraints

- Do not add new denylist semantics directly inside `compiler.py`, `expressions.py`, `typecheck.py`, or `lowering/core.py`; those files may only receive the minimum delegation glue required to call the new owner/helper modules.
- If helper extraction reveals a would-be owner file growing past 2,000 physical lines, split again before adding the denylist behavior there.
- Do not widen the policy into CLI flags, environment variables, or shared runtime knobs.
- Do not modify `std/phase.orc` to simulate imported `.orc` expansion in this slice.
- Do not delete the legacy bridge; only gate it behind explicit legacy mode.
- Do not weaken command/result authority rules while adding the denylist checks.
- Do not claim parity or promoted stdlib ownership; this slice proves the opposite by failing closed in promoted mode.

## Task Checklist

### Task 1: Add The Failing Architecture And Diagnostics Characterization Tests First

**Files:**

- Modify: `tests/test_workflow_lisp_macros.py`
- Modify: `tests/test_workflow_lisp_expressions.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_diagnostics.py`

- [ ] Add `test_review_revise_loop_not_reserved_core_macro_name` to prove `review-revise-loop` stays outside the reserved macro-name set while `__stdlib-specialization__` remains reserved.
- [ ] Add `test_no_review_loop_expr_in_core_ast_union` to prove the historical `ReviewReviseLoopExpr` path stays absent from the current frontend/Core AST union even though `StdlibSpecializationExpr` still exists as the temporary bridge carrier.
- [ ] Add `test_review_revise_loop_not_elaborated_by_head_name` to assert the elaboration route does not dispatch directly on public head name `review-revise-loop`; the only live bridge route should remain the temporary intrinsic `__stdlib-specialization__` plus request-kind tagging.
- [ ] Add `test_typecheck_does_not_import_review_loop_expr` and `test_lowering_does_not_import_review_loop_expr` as static architecture tests that fail if typecheck or lowering regains an import or symbol dependency on the historical AST name.
- [ ] Add `test_serialize_diagnostic_infers_stdlib_special_form_disallowed_metadata` and `test_serialize_diagnostic_infers_review_loop_special_lowerer_metadata` in `tests/test_workflow_lisp_diagnostics.py`, or extend the existing metadata parametrization with these two exact codes, so the repo's dedicated diagnostics surface owns the new metadata contract.

**Blocking verification after Task 1:**

- [ ] `pytest --collect-only tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_diagnostics.py -q`
- [ ] `pytest tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_diagnostics.py -k "review_revise_loop_not_reserved_core_macro_name or no_review_loop_expr_in_core_ast_union or review_revise_loop_not_elaborated_by_head_name or typecheck_does_not_import_review_loop_expr or lowering_does_not_import_review_loop_expr or stdlib_special_form_disallowed or review_loop_special_lowerer" -q`

### Task 2: Establish The Small Owner/Helper Surfaces And Thread The Stage 3 Policy

**Files:**

- Modify: `orchestrator/workflow_lisp/phase_stdlib.py`
- Create: `orchestrator/workflow_lisp/phase_stdlib_typecheck.py`
- Create: `orchestrator/workflow_lisp/lowering/phase_stdlib.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/lowering/core.py`
- Modify: `orchestrator/workflow_lisp/diagnostics.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] Expand `phase_stdlib.py` so it owns the review-loop bridge policy alias/constants and any shared helper records or predicates needed by elaboration, diagnostics, and Stage 3 policy threading.
- [ ] Extract or wrap the review-loop compatibility typecheck helpers into `phase_stdlib_typecheck.py` before introducing deny-mode behavior there; leave `typecheck.py` as a thin dispatcher or compatibility wrapper.
- [ ] Extract or wrap the review-loop-specific lowering helpers into `lowering/phase_stdlib.py` before introducing the last-resort deny guard there; leave `lowering/core.py` as a thin dispatcher or compatibility wrapper.
- [ ] Add the keyword-only Stage 3 policy argument to `compile_stage3_module(...)`, `compile_stage3_entrypoint(...)`, and the minimal internal compile helpers they call.
- [ ] Keep the default mode `allow` so untouched callers and fixtures remain legacy-compatible in this slice.
- [ ] Limit `compiler.py`, `expressions.py`, `typecheck.py`, and `lowering/core.py` changes to imports, argument threading, and direct delegation into the new owner/helper modules.
- [ ] Register stable diagnostic classification for `stdlib_special_form_disallowed` and `review_loop_special_lowerer_used` in `diagnostics.py` so serialized diagnostics report sensible `phase`, `validation_pass`, and `authority_layer` metadata.
- [ ] Extend the local review-loop compile helpers in `tests/test_workflow_lisp_phase_stdlib.py` so both `compile_stage3_module(...)` and direct `compile_stage3_entrypoint(...)` policy tests reuse the same externs, prompt bindings, command boundaries, and workspace setup instead of duplicating fixture wiring.
- [ ] Add `test_review_loop_entrypoint_policy_allow_smoke` with explicit `compile_stage3_entrypoint(..., review_loop_legacy_bridge_policy="allow")` against the existing public review-loop fixture so the new public API surface is verified before deny-mode enforcement is introduced.

**Blocking verification after Task 2:**

- [ ] `pytest tests/test_workflow_lisp_diagnostics.py -k "stdlib_special_form_disallowed or review_loop_special_lowerer" -q`
- [ ] `pytest tests/test_workflow_lisp_phase_stdlib.py -k "entrypoint_policy_allow" -q`
- [ ] `wc -l orchestrator/workflow_lisp/phase_stdlib.py orchestrator/workflow_lisp/phase_stdlib_typecheck.py orchestrator/workflow_lisp/lowering/phase_stdlib.py`

### Task 3: Enforce The Denylist At Elaboration, Typecheck, And Lowering, Then Add The Behavior Proofs

**Files:**

- Modify: `orchestrator/workflow_lisp/phase_stdlib.py`
- Modify: `orchestrator/workflow_lisp/phase_stdlib_typecheck.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_stdlib.py`
- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/lowering/core.py`
- Inspect only unless helper reuse is required: `orchestrator/workflow_lisp/form_registry.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] In the elaboration-side owner helper, reject `__stdlib-specialization__` request kind `phase-review-loop` when the policy is `deny`, using diagnostic code `stdlib_special_form_disallowed` and a message that clearly says promoted mode cannot use the legacy review-loop compatibility bridge.
- [ ] Keep elaboration behavior unchanged in `allow` mode, including the current shape validation for required review-loop keywords and request-kind handling.
- [ ] In `phase_stdlib_typecheck.py`, add a defense-in-depth deny check so manually constructed or future-surviving `StdlibSpecializationExpr(request_kind="phase-review-loop")` fails with the same `stdlib_special_form_disallowed` code instead of silently typechecking.
- [ ] In `lowering/phase_stdlib.py`, add the last-resort deny check before any review-loop-specific lowering helper path runs and raise `review_loop_special_lowerer_used` if deny mode somehow reaches the lowerer.
- [ ] Add one promoted negative compile test in `tests/test_workflow_lisp_phase_stdlib.py` that compiles `VALID_REVIEW_LOOP_FIXTURE` with `review_loop_legacy_bridge_policy="deny"` through `compile_stage3_module(...)` and expects diagnostic code `stdlib_special_form_disallowed`.
- [ ] Add one explicit legacy-opt-in compile test against the same fixture with `review_loop_legacy_bridge_policy="allow"` through `compile_stage3_module(...)` and prove existing typed/lowered behavior still succeeds.
- [ ] Add `test_review_loop_entrypoint_policy_deny_rejects_legacy_bridge` and tighten `test_review_loop_entrypoint_policy_allow_smoke` into the final allow-path assertion so the public entrypoint pipeline proves the policy is threaded beyond the module wrapper and fails closed only in deny mode.
- [ ] Keep the denylist mapping checkout-aware: historical names remain absent, but the live checks target the current equivalents `StdlibSpecializationExpr`, `_elaborate_phase_review_loop_specialization(...)`, and `phase-review-loop`.
- [ ] Do not add new form classifications or reserved-name policy unless a tiny helper reuse in `form_registry.py` is the smallest way to keep request-kind tagging centralized.

**Blocking verification after Task 3:**

- [ ] `pytest tests/test_workflow_lisp_phase_stdlib.py -k "legacy_bridge_policy or entrypoint_policy or review_loop_specializes_to_ordinary_typed_forms or shared_validation_accepts_review_revise_loop" -q`
- [ ] `pytest tests/test_workflow_lisp_lowering.py -k "review_loop or stdlib_contract_inventory" -q`

### Task 4: Run The Narrow Regression And Integration Proof

**Files:**

- No new maintained source files; this task validates the delivered boundary.

- [ ] Run `pytest --collect-only` for the touched modules if any new tests were added or renamed during implementation:
  `tests/test_workflow_lisp_macros.py`,
  `tests/test_workflow_lisp_expressions.py`,
  `tests/test_workflow_lisp_phase_stdlib.py`,
  `tests/test_workflow_lisp_lowering.py`,
  `tests/test_workflow_lisp_diagnostics.py`
- [ ] Run the touched test modules after implementation:
  `pytest tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_diagnostics.py -q`
- [ ] Run the narrow integration-style shared-validation proof that still exercises the imported `std/phase` review-loop fixture through the existing frontend pipeline:
  `pytest tests/test_workflow_lisp_phase_stdlib.py::test_shared_validation_accepts_review_revise_loop -q`
- [ ] Run the explicit promoted deny and legacy allow proof selectors again after the full module pass so the architecture boundary is demonstrated independently of unrelated fixture coverage.
- [ ] Record exact failing command output before broadening scope if verification exposes a hidden dependency outside this slice.

## Explicit Non-Goals

- Do not implement imported `.orc` expansion, imported source-map parity, imported effect visibility, or bridge retirement.
- Do not remove `StdlibSpecializationExpr`, `phase-review-loop`, review-loop-specific typecheck helpers, or review-loop-specific lowering helpers in this item; move/wrap them behind owner/helper modules only as needed to satisfy the preflight boundary.
- Do not add runtime or shared-validation awareness of promoted versus legacy mode.
- Do not rewrite prompt/docs/spec text to claim ordinary stdlib ownership of `review-revise-loop`.
- Do not add tests that assert exact prompt prose or unrelated rendered-YAML snapshots.
