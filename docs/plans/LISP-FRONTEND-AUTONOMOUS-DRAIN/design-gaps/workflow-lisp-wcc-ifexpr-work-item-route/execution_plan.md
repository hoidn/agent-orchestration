# WCC IfExpr Work-Item Route Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add WCC support for already-accepted authored `IfExpr` so `lisp_frontend_design_delta/work_item::run-work-item` advances past the current `unsupported IfExpr` blocker without adding a bespoke helper-hoisting or legacy lowering route.

**Architecture:** Extend the accepted WCC route with one compiler-internal conditional body node that carries a pure/projectable Bool condition, typed then/else bodies, source/proof/effect metadata, participates in every WCC body traversal/control rewrite, and defunctionalizes to the existing shared authored `if` step. The public `if` surface, condition typing, and legacy shared branch runtime already exist; this plan makes that surface compose through WCC M4/default lowering and preserves the frontend baseline authority boundary.

**Tech Stack:** Python, dataclass-based Workflow Lisp frontend AST/WCC model, existing shared authored `if` lowering utilities, pytest characterization and feasibility suites.

---

## Governing Context

Read these before implementation:

- `docs/index.md`
- `docs/design/README.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/post_wcc_reconciliation_index.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- `docs/design/workflow_lisp_core_calculus_middle_end.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/if-conditionals-pure-proven-values/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-child-returned-variant-work-item-prerequisite/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect/work_item_context.md`

Current blocker evidence:

- `tests/test_workflow_lisp_build_artifacts.py::_assert_design_delta_work_item_blocked_by_wcc_ifexpr` expects only `wcc_lowering_route_unsupported` with `unsupported IfExpr`.
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::_assert_design_delta_work_item_candidate_wcc_ifexpr_boundary_failure` expects the same blocker and explicitly proves the old returned-variant/private-workflow blockers are gone.
- `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/work_item.orc` contains private-workflow procedures `finalize-approved-review-state` and `finalize-approved-nonblocked` whose bodies use `if` and currently trigger the WCC route blocker.

Non-negotiable boundaries:

- Do not add a second helper-hoisting route or new schema-1 behavior.
- Do not change public `if` syntax, proof semantics, branch runtime semantics, or condition language.
- Do not make `if` create variant proof.
- Do not expose `PhaseCtx`, state roots, write roots, generated context inputs, typed projection, resource transitions, parent drain composition, adapter certification, or promotion evidence as part of this slice.
- Do not solve this by scripts, raw command text, report parsing, pointer files, or hidden state rewrites.

## File Map

- Modify `orchestrator/workflow_lisp/wcc/model.py`: add `WccIf` dataclass and include it in `WccBody`; optionally define a stable route constant only if the implementation intentionally introduces `wcc_m5`. Prefer extending `wcc_m4` unless tests show a schema distinction is required.
- Modify `orchestrator/workflow_lisp/wcc/route.py`: allow `IfExpr` in the WCC M4/default route and recurse through condition, then branch, and else branch.
- Modify `orchestrator/workflow_lisp/wcc/elaborate.py`: import `IfExpr`, elaborate it into `WccIf`, infer `IfExpr` result type, preserve inherited proof context/effect metadata, and thread `WccIf` through `_retarget_loop_continue` and `_replace_halts_with_jump`.
- Modify `orchestrator/workflow_lisp/wcc/anf.py`: normalize `WccIf.condition`, then/else bodies, and any non-atomic condition value in the same style as `WccCase.subject`.
- Modify `orchestrator/workflow_lisp/wcc/analysis.py`: traverse `WccIf` branches; record branch scopes if useful, but do not treat conditionals as variant-proof-producing arms.
- Modify `orchestrator/workflow_lisp/wcc/defunctionalize.py`: defunctionalize `WccIf` to one shared authored `if` step, using existing condition rendering and branch-output helpers where possible; handle `WccIf` in `_frontend_expr_from_wcc_loop_body` and `_frontend_expr_from_wcc_loop_result_body` so loop emitters do not accept shapes that fail later.
- Test `tests/test_workflow_lisp_wcc_characterization.py`: add characterization for WCC conditionals in tail position, a non-tail `if` binding, and an `if` inside a `loop/recur` body; ensure WCC M4 and the default WCC route compile the accepted shapes.
- Test `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`: invert the work-item blocker expectation so the fixture no longer accepts `unsupported IfExpr`; assert the route advances to compile/shared validation or to the next owned downstream blocker.
- Test `tests/test_workflow_lisp_build_artifacts.py`: update the build-artifact blocker assertion in the same way as the feasibility suite.
- Fixtures/goldens under `tests/fixtures/workflow_lisp/characterization/`: add minimal WCC `if` sources and golden structural snapshots, or reuse existing `if_conditionals_minimal.orc` style fixtures through the characterization manifest if they fit the harness.

### Task 1: Baseline And Failing Tests

**Files:**
- Modify: `tests/test_workflow_lisp_wcc_characterization.py`
- Modify: characterization manifest/golden files under `tests/fixtures/workflow_lisp/characterization/`
- Modify: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] **Step 1: Run the current blocker test and record the failure boundary**

Run:

```bash
pytest -q tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_work_item_candidate_is_blocked_by_phase_family_boundary
```

Expected now: PASS because the current expected blocker is `wcc_lowering_route_unsupported` with `unsupported IfExpr`.

- [ ] **Step 2: Add WCC characterization cases for `IfExpr`**

Add checked-in source fixtures that cover the accepted recursive route shapes:

- tail-position `if`;
- non-tail `if` binding whose result is consumed by later work; and
- `if` inside a `loop/recur` body, with one branch continuing and one branch finishing, or the closest existing loop shape that exercises `_frontend_expr_from_wcc_loop_body`.

For the tail-position case, use a Bool input or Bool record field condition and both branches returning the same record or union type. Prefer a new checked-in source such as:

```lisp
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule wcc_ifexpr_minimal)
  (export choose-summary)

  (defpath ReportPath
    :kind relpath
    :under "artifacts/work"
    :must-exist false)

  (defrecord Summary
    (report ReportPath))

  (defworkflow choose-summary
    ((enabled Bool)
     (approved_report ReportPath)
     (blocked_report ReportPath))
    -> Summary
    (if enabled
      (record Summary :report approved_report)
      (record Summary :report blocked_report))))
```

For the non-tail binding fixture, keep the shape small and make the `if` result feed a later expression so `_replace_halts_with_jump` must rewrite both branch terminals into the generated join:

```lisp
(let* ((chosen (if enabled
                 (record Summary :report approved_report)
                 (record Summary :report blocked_report))))
  (record Summary :report (field chosen report)))
```

For the loop fixture, place `if` directly inside the loop body so `_retarget_loop_continue` and the loop-body expression converters must traverse it:

```lisp
(loop/recur state initial-state
  :max-iterations 2
  (if enabled
    (done state)
    (continue state)))
```

Adapt field names to the existing loop fixture conventions rather than inventing parallel loop syntax. Wire the cases into the characterization manifest with a tag such as `ifexpr` or the closest existing route-flip tag, and decide whether each case is WCC-only or dual-compile with legacy. If adding a new tag, update `test_manifest_covers_required_m0_tags` and `test_manifest_tags_are_present_exactly_once`.

- [ ] **Step 3: Write expected post-fix assertions before implementation**

In `tests/test_workflow_lisp_wcc_characterization.py`, assert every new `ifexpr` case compiles under `LoweringRoute.WCC_M4` and under the default route, has no diagnostics, and emits a shared `if` step in the lowered mapping.

Use assertions shaped like:

```python
actual = build_structural_snapshot(case, tmp_path / case.case_id, lowering_route="wcc_m4")
assert actual["diagnostics"] == []
assert any("if" in step for wf in actual["lowered_workflows"] for step in wf["authored_mapping"]["steps"])
```

Use the actual snapshot structure helpers already present in the file; do not invent a parallel snapshot reader. Add explicit assertions that:

- the non-tail case no longer raises `unsupported WCC control rewrite node: WccIf`; and
- the loop case no longer raises `unsupported WCC loop body during defunctionalization: WccIf`.

- [ ] **Step 4: Invert the work-item blocker tests**

Update the helper assertions in `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py` so they no longer pass on `unsupported IfExpr`.

Expected post-fix behavior should be one of:

- compile/shared-validation success for `run-work-item`; or
- a new downstream diagnostic that is not `unsupported IfExpr`, not `union_return_variant_ambiguous`, not `union_return_variant_incompatible`, and not `proc_private_workflow_boundary_invalid`.

Write the assertion to make the next blocker visible without treating it as success if it belongs to another tranche. For example, keep a helper named for the new expected boundary once discovered by implementation, and include:

```python
assert not any("unsupported `IfExpr`" in diagnostic.message for diagnostic in exc.diagnostics)
```

- [ ] **Step 5: Run the new/updated tests and confirm they fail for the intended reason**

Run:

```bash
pytest -q tests/test_workflow_lisp_wcc_characterization.py -k "ifexpr or route_flip_corpus" -v
pytest -q tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_work_item_candidate_is_blocked_by_phase_family_boundary -v
pytest -q tests/test_workflow_lisp_build_artifacts.py -k "design_delta_work_item" -v
```

Expected before implementation: FAIL because WCC M4 rejects `IfExpr`, the non-tail binding exposes an unsupported WCC control rewrite node, the loop case exposes an unsupported WCC loop-body conversion node, or the work-item tests still see the old `unsupported IfExpr` diagnostic.

- [ ] **Step 6: Commit the failing tests**

```bash
git add tests/test_workflow_lisp_wcc_characterization.py tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py tests/fixtures/workflow_lisp/characterization
git commit -m "test: characterize WCC ifexpr route"
```

### Task 2: WCC Model, Route Validation, And Elaboration

**Files:**
- Modify: `orchestrator/workflow_lisp/wcc/model.py`
- Modify: `orchestrator/workflow_lisp/wcc/route.py`
- Modify: `orchestrator/workflow_lisp/wcc/elaborate.py`

- [ ] **Step 1: Add `WccIf` to the model**

Add:

```python
@dataclass(frozen=True)
class WccIf:
    metadata: WccNodeMetadata
    condition: WccValue
    condition_shape: object
    then_body: "WccBody"
    else_body: "WccBody"
```

Then include `WccIf` in the `WccBody` union. Keep `condition_shape` compiler-internal; it should not appear in runtime state, artifacts, source maps as a class name, or public debug YAML authority.

- [ ] **Step 2: Permit `IfExpr` in WCC M4 route validation**

Import `IfExpr` in `orchestrator/workflow_lisp/wcc/route.py`. In `_validate_wcc_m4_expr_supported`, recurse through:

- `expr.condition_expr`
- `expr.then_expr`
- `expr.else_expr`

Do not add `IfExpr` to WCC M1/M2/M3 unless a characterization test explicitly requires those older routes.

- [ ] **Step 3: Elaborate `IfExpr` into `WccIf`**

Import `IfExpr` and `classify_condition_expr`. In `_elaborate_expr_to_body`, add an `IfExpr` branch before generic effectful forms:

- elaborate the condition to a value through `_elaborate_expr_to_value` under a child scope such as `if-condition`;
- classify the original condition expression using `PrimitiveTypeRef(name="Bool")`;
- elaborate then/else with child scopes such as `if-then` and `if-else`;
- wrap any condition prefix lets around the `WccIf`;
- set metadata with `scope.body_metadata(role="if", type_ref=<result type>, source_span=expr.span, form_path=expr.form_path, expansion_stack=expr.expansion_stack, effect_summary=effect_summary, phase_scope=active_phase_scope)`.

Do not create or narrow proof facts. Both branches inherit the current proof context exactly as normal nested expression elaboration already does.

- [ ] **Step 4: Thread `WccIf` through elaboration control rewrites**

Import `WccIf` in `elaborate.py` where needed and update both WCC body rewrite helpers that pattern-match over `WccBody`:

- `_retarget_loop_continue`: recurse into `then_body` and `else_body`, retargeting any nested `WccLoopContinue` under the current loop name.
- `_replace_halts_with_jump`: recurse into `then_body` and `else_body`, replacing branch-tail `WccHalt` nodes with jumps to the generated join.

Use `replace(body, then_body=..., else_body=...)` and preserve the original `WccIf` metadata, condition, and `condition_shape`. This is required before route validation can safely admit `IfExpr` recursively; otherwise non-tail `if` bindings and `if` inside loop bodies can pass route validation and fail later with unsupported-node `TypeError`s.

- [ ] **Step 5: Add `IfExpr` type inference**

In `_infer_expr_type`, handle `IfExpr` by inferring both branch types and returning the then branch type after confirming compatibility with the else branch. The public typechecker already enforces exact branch compatibility; this inference is for WCC metadata, so raising `TypeError` on impossible mismatch is acceptable.

- [ ] **Step 6: Run focused route/elaboration tests**

Run:

```bash
pytest -q tests/test_workflow_lisp_wcc_characterization.py -k "ifexpr" -v
```

Expected after this task: the route validation error should be gone, and failures must not come from `_retarget_loop_continue` or `_replace_halts_with_jump`. The test may still fail in ANF, analysis, defunctionalization, or loop expression conversion with an unsupported `WccIf` node.

- [ ] **Step 7: Commit model/route/elaboration**

```bash
git add orchestrator/workflow_lisp/wcc/model.py orchestrator/workflow_lisp/wcc/route.py orchestrator/workflow_lisp/wcc/elaborate.py
git commit -m "feat: elaborate ifexpr into WCC"
```

### Task 3: ANF And Analysis Traversal

**Files:**
- Modify: `orchestrator/workflow_lisp/wcc/anf.py`
- Modify: `orchestrator/workflow_lisp/wcc/analysis.py`

- [ ] **Step 1: Normalize `WccIf`**

Import `WccIf` in `anf.py`. In `_normalize_body`, add a case that:

- normalizes `body.condition` with `_normalize_value`;
- atomizes the condition if it is not an allowed atomic effect arg, using a purpose like `if:condition`;
- recursively normalizes `then_body` and `else_body`;
- wraps any pending condition lets around the replaced `WccIf`.

Preserve metadata and `condition_shape`.

- [ ] **Step 2: Traverse `WccIf` during analysis**

Import `WccIf` in `analysis.py`. In `walk`, recurse into `then_body` and `else_body`. In `_proof_scopes`, recurse into both branches. Do not add `WccArmScope` records for `if` unless implementation needs a separate debug observation; `if` is not variant elimination and should not look like a proof-producing case.

- [ ] **Step 3: Run focused tests**

Run:

```bash
pytest -q tests/test_workflow_lisp_wcc_characterization.py -k "ifexpr" -v
```

Expected after this task: failures, if any, should move to defunctionalization or output projection, not ANF/analysis unsupported-node errors.

- [ ] **Step 4: Commit ANF/analysis traversal**

```bash
git add orchestrator/workflow_lisp/wcc/anf.py orchestrator/workflow_lisp/wcc/analysis.py
git commit -m "feat: normalize WCC ifexpr bodies"
```

### Task 4: Defunctionalize WCC If To Shared Authored If And Loop Expressions

**Files:**
- Modify: `orchestrator/workflow_lisp/wcc/defunctionalize.py`

- [ ] **Step 1: Import needed symbols**

Import `IfExpr` if reconstructing branch expressions is useful, `WccIf`, and the existing condition helpers:

```python
from ..conditionals import render_condition_predicate
```

Prefer using `body.condition_shape` plus `local_values` to render the condition. If the ANF step rewrites the condition to a generated name, reconstruct a frontend expression from `body.condition` and classify/render it through the existing condition helper only when it preserves projectability.

- [ ] **Step 2: Add `_defunctionalize_if`**

Implement a helper similar to the existing legacy `_control_lower_if_expr_impl`, but operating on WCC bodies:

- build `step_name = context.step_name_prefix` and normalized `step_id`;
- render the pure condition to a shared typed predicate;
- compute `output_contracts` with `lowering_core._output_contracts_for_type`;
- defunctionalize then/else under child prefixes `f"{step_name}__then"` and `f"{step_name}__else"`;
- compute case outputs with `_conditional_case_outputs`;
- add projection-anchor steps with `_build_match_projection_anchor_step` when a branch emits no steps;
- merge branch hidden inputs;
- record the `if` step origin with `_record_step_origin`;
- return one step shaped as `{"name": step_name, "id": step_id, "if": condition, "then": {...}, "else": {...}}` or the exact shared authored `if` shape used by `_control_lower_if_expr_impl`.

Use existing helpers imported from `..lowering.control_match` where possible:

- `_build_match_projection_anchor_step`
- `_conditional_case_outputs`
- `_conditional_output_refs`

- [ ] **Step 3: Preserve union terminal metadata**

If both branches return a union and branch terminals carry compatible `returned_union_type_name`, preserve the returned union type on the `WccIf` terminal only when it is safe and required by downstream match normalization. Do not guess one target variant from the condition. If union pass-through is ambiguous, leave it to existing branch-output validation to report a normal owned diagnostic.

- [ ] **Step 4: Wire `_defunctionalize_body`**

In `_defunctionalize_body`, dispatch `WccIf` before the terminal export fallback:

```python
if isinstance(body, WccIf):
    return _defunctionalize_if(...)
```

Do not rebuild `IfExpr` and send it through the legacy route as the primary implementation unless the code path remains WCC-owned and still records WCC metadata/source origins.

- [ ] **Step 5: Convert `WccIf` when rebuilding loop frontend expressions**

Update the loop conversion helpers that currently rebuild frontend expressions from WCC bodies:

- `_frontend_expr_from_wcc_loop_body`: convert `WccIf` into `IfExpr(condition_expr=..., then_expr=..., else_expr=...)`, rebuilding the condition from `body.condition` / `body.condition_shape` and recursively converting `then_body` and `else_body`.
- `_frontend_expr_from_wcc_loop_result_body`: either inline linear `let` bindings through `WccIf` safely or delegate to `_frontend_expr_from_wcc_loop_body` when the result body is not a pure `WccHalt`. Do not drop `let` bindings that feed the condition or branch returns.

Preserve source span, form path, and expansion stack from `body.metadata`. If condition reconstruction cannot preserve projectability, emit an owned compiler diagnostic or keep the shape rejected before route admission; do not allow a late `TypeError` from the loop emitter.

- [ ] **Step 6: Run focused WCC tests**

Run:

```bash
pytest -q tests/test_workflow_lisp_wcc_characterization.py -k "ifexpr or wcc_m4 or loop" -v
```

Expected: PASS for all new `ifexpr` cases, including the non-tail binding and loop-body fixtures, and no regression for existing WCC M4 loop/review/implementation fixtures.

- [ ] **Step 7: Commit defunctionalization**

```bash
git add orchestrator/workflow_lisp/wcc/defunctionalize.py
git commit -m "feat: lower WCC ifexpr to shared if"
```

### Task 5: Work-Item Fixture And Build Artifact Transition

**Files:**
- Modify: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- No production source changes unless a narrow source-map or branch-output bug is exposed by the fixture.

- [ ] **Step 1: Run the real work-item fixture**

Run:

```bash
pytest -q tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_work_item_candidate_is_blocked_by_phase_family_boundary -v
```

Expected post-implementation:

- no diagnostic message contains `unsupported IfExpr`;
- no diagnostics include `union_return_variant_ambiguous`, `union_return_variant_incompatible`, or `proc_private_workflow_boundary_invalid`;
- if compilation succeeds, assert the lowered workflow set includes the private-workflow procedures containing `if`;
- if compilation finds the next blocker, update the helper name/message to identify that next blocker precisely and keep the test green only for that new owned downstream boundary.

- [ ] **Step 2: Run the parent-call work-item fixture**

Run the nearest parent-call selector in the same module. If the exact test name is unclear, list selectors first:

```bash
pytest --collect-only -q tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py | rg "work_item|parent_call"
pytest -q tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "work_item and parent" -v
```

Expected: the parent-call fixture must also advance past `unsupported IfExpr`; any remaining failure must be a distinct downstream tranche blocker.

- [ ] **Step 3: Update build-artifact assertion**

Run:

```bash
pytest -q tests/test_workflow_lisp_build_artifacts.py -k "design_delta_work_item" -v
```

Update the assertions that currently expect `_assert_design_delta_work_item_blocked_by_wcc_ifexpr`. The new assertion must check the actual post-fix boundary and explicitly reject old `unsupported IfExpr` diagnostics.

- [ ] **Step 4: Commit fixture transition**

```bash
git add tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py
git commit -m "test: advance work-item fixture past WCC ifexpr"
```

### Task 6: Regression Band And Documentation Notes

**Files:**
- Modify docs only if implementation changes a lasting user-visible behavior beyond making WCC support an already accepted surface.
- Likely no design-doc changes are required; the target design already names WCC `IfExpr` as the immediate blocker.

- [ ] **Step 1: Run invalid conditional diagnostics**

Run:

```bash
pytest -q tests/test_workflow_lisp_diagnostics.py -k "if_condition" -v
```

Expected: PASS. Existing invalid `if` diagnostics remain owned by the public typechecker/condition classifier.

- [ ] **Step 2: Run public frontend `if` and loop tests**

Run:

```bash
pytest -q tests/test_workflow_lisp_expressions.py -k "if" -v
pytest -q tests/test_workflow_lisp_lowering.py -k "if" -v
pytest -q tests/test_workflow_lisp_loop_recur.py -k "if" -v
```

Expected: PASS. Legacy/public `if` behavior remains compatible.

- [ ] **Step 3: Run WCC characterization**

Run:

```bash
pytest -q tests/test_workflow_lisp_wcc_characterization.py -v
```

Expected: PASS, with the new `IfExpr` case included in the manifest/golden expectations.

- [ ] **Step 4: Run design-delta feasibility band**

Run:

```bash
pytest -q tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -v
```

Expected: PASS or only expected xfail/skips already present. The work-item route must not stop at `unsupported IfExpr`.

- [ ] **Step 5: Run build artifacts coverage**

Run:

```bash
pytest -q tests/test_workflow_lisp_build_artifacts.py -v
```

Expected: PASS or only pre-existing unrelated failures. If this is too broad for local time, run the exact selectors touched by this plan and record why isolated checks are enough.

- [ ] **Step 6: Run collect-only if tests or fixtures were added/renamed**

Run:

```bash
pytest --collect-only -q tests/test_workflow_lisp_wcc_characterization.py tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py
```

Expected: collection succeeds and includes the new/renamed tests.

- [ ] **Step 7: Commit final adjustments**

```bash
git add orchestrator/workflow_lisp/wcc tests/fixtures/workflow_lisp/characterization tests/test_workflow_lisp_wcc_characterization.py tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py
git commit -m "feat: support ifexpr on WCC work-item route"
```

## Acceptance Criteria

- WCC M4/default route supports already-typed authored `IfExpr` with pure/projectable Bool conditions and same-type then/else branches.
- `IfExpr` compiles through WCC model, elaboration, ANF, analysis, elaboration control rewrites, loop-body expression conversion, and defunctionalization without serializing WCC metadata as runtime authority.
- Defunctionalized output uses the existing shared authored `if` runtime surface and existing branch output projection rules.
- Non-tail `if` bindings are rewritten through WCC joins without unsupported-node errors, and `if` inside `loop/recur` bodies is retargeted/converted without unsupported-node errors.
- Invalid conditional diagnostics still come from the existing typechecker/classifier and continue to reject non-Bool, effectful, or non-projectable conditions.
- The real work-item fixture no longer fails with `unsupported IfExpr` for `lisp_frontend_design_delta/work_item::run-work-item`.
- Any remaining work-item or parent-call failure is a clearly named downstream tranche blocker, not this gap.
- No new command adapters, resource transitions, typed projection, private executable context bridge, parent drain wrapper, or promotion evidence are added under this slice.

## Verification Summary To Record When Done

Record the exact command output for:

```bash
pytest -q tests/test_workflow_lisp_diagnostics.py -k "if_condition" -v
pytest -q tests/test_workflow_lisp_wcc_characterization.py -k "ifexpr or wcc_m4 or loop" -v
pytest -q tests/test_workflow_lisp_wcc_characterization.py -v
pytest -q tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -v
pytest -q tests/test_workflow_lisp_build_artifacts.py -k "design_delta_work_item" -v
pytest --collect-only -q tests/test_workflow_lisp_wcc_characterization.py tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py
```

If any broad suite is not run, document the reason and the narrower selectors that provide enough evidence for this bounded compiler-lane gap.
