# Workflow Lisp Parametric Loop-State Authoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the bounded `loop-state` prerequisite so imported generic `.orc` procedures can carry one authored loop-frame carrier that mixes caller-specialized fields with fixed stdlib-owned fields, specializes to a monomorphic local record-like type before lowering, and flows through ordinary `loop/recur`, typed exhaustion projection, source maps, and shared validation without review-loop-specific hidden state synthesis.

**Architecture:** Treat this as a bounded audit-and-finish pass, not a greenfield feature. The checkout already contains a frontend-owned `loop-state` surface in `orchestrator/workflow_lisp/` and focused tests around it; implementation should verify those owners against the iteration-5 work-item bundle, then close only the remaining gaps in typing, lowering, imported-generic specialization, and future-consumer regression coverage. Keep authored-surface admission in `expressions.py` / `expression_traversal.py` / `form_registry.py` / `functions.py`, keep carrier metadata and semantic checks in `loop_state.py` behind `typecheck_dispatch.py`, keep value lowering in `lowering/values.py` plus loop-boundary acceptance in `lowering/control_loops.py`, and use `lowering/control_dispatch.py` / `lowering/core.py` only as routers.

**Tech Stack:** Python 3, pytest, Workflow Lisp frontend modules under `orchestrator/workflow_lisp/`, shared runtime reuse under `orchestrator/workflow/`, and repo-root verification commands.

---

## Fixed Inputs

Treat these artifacts as authority for implementation scope and correctness:

- `docs/index.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/design/workflow_lisp_frontend_specification.md`
  - Section `7` `Types`
  - Section `8.8` `defproc`
  - Section `9` `Pure Expressions`
  - Section `10` `Sequential Binding`
  - Section `11` `Pattern Matching`
  - Section `13` `Loops`
  - Section `16` `Effect System`
  - Section `44` `Typed Frontend AST`
  - Section `51` `defproc Lowering`
  - Section `57` `review-revise-loop Lowering Contract`
  - Section `63` `Variant Proof Validation`
  - Section `74` `Source Map Requirements`
  - Section `95` `Lowering Tests`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - Section `12.2` `Authorable Parametric Loop-State Dependency`
  - Section `16` `Loop State Model`
  - Section `18` `Loop Exhaustion Projection`
  - Section `21` `Source Maps And State Layout`
  - Section `24` / `Stage 7A - Authorable Parametric Loop-State Surface`
  - Section `27` `Acceptance Checks`
  - Section `30` `Summary Recommendation`
- `docs/design/workflow_lisp_compile_time_parametric_specialization.md`
- `docs/design/workflow_lisp_structural_parametric_constraints.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_refactor_architecture.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-parametric-loop-state-authoring/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/5/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/5/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

Related prerequisite slices are reused but not reopened here:

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/loop-recur-bounded-loops/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-loop-recur-on-exhausted-projection/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-parametric-defproc-specialization-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-structural-parametric-constraints/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-review-loop-report-findings-path-split/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-review-loop-resume-checkpoint-identity/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-stdlib-review-revise-loop-implementation/implementation_architecture.md`

## Verified Current-Checkout Facts

Start from these facts instead of rediscovering them:

- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` currently has no events.
- `orchestrator/workflow_lisp/loop_state.py` already exists as the dedicated loop-state owner module.
- `orchestrator/workflow_lisp/expressions.py` already defines `LoopStateField`, `LoopStateSeedExpr`, `LoopStateUpdateExpr`, and `loop-state` elaboration helpers.
- `tests/test_workflow_lisp_loop_state.py` already exists with focused loop-state coverage.
- `tests/test_workflow_lisp_loop_recur.py`, `tests/test_workflow_lisp_procedures.py`, and `tests/test_workflow_lisp_phase_stdlib.py` already contain loop-state-related tests or fixtures.
- `docs/lisp_workflow_drafting_guide.md` already documents `loop-state` in Section `17.1`.
- `orchestrator/workflow_lisp/phase_stdlib_typecheck.py` and `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` still belong to the legacy review-loop bridge and are not ownership targets for this slice.

Interpretation:

- this work item is not about inventing a new surface;
- it is about proving the chosen `loop-state` surface is complete, correctly owned, and sufficient for the iteration-5 prerequisite bundle;
- any gaps that still appear should be closed in the narrowest owner module rather than by widening into bridge retirement, reusable-phase-state redesign, or runtime changes.

## Scope Guard

In scope:

- one frontend-owned `loop-state` seed form with explicit `(field Type value)` entries;
- one frontend-owned `loop-state` update form with `:like` plus keyword overrides;
- synthetic local carrier generation after generic specialization has resolved concrete field types;
- ordinary record-like field access, `match`, `continue`, `done`, and `loop/recur :state` behavior on that carrier;
- runtime-forbidden-field rejection for `ProcRef`, `WorkflowRef`, provider refs, and prompt refs;
- ordinary lowering of seed/update values into inline record-shaped local values;
- loop-boundary acceptance and typed exhaustion projection using authored carrier outputs;
- source-map/origin coverage for authored carrier fields and generated loop-frame projections;
- imported generic `.orc` verification that carries a caller-specialized field plus fixed stdlib-owned fields;
- future-consumer regression coverage for strict `ReviewFindings.items_path` handling;
- guide updates only if the current documented surface no longer matches the implemented behavior.

Out of scope:

- generic top-level parametric `defrecord` or `defunion`;
- generic `defworkflow`;
- `std/phase.orc` implementation of ordinary stdlib `review-revise-loop`;
- retirement of the review-loop bridge or removal of `ReviewReviseLoopExpr`;
- reusable-phase-state validation redesign;
- new runtime-native loop/state semantics or changes under `orchestrator/workflow/`;
- new command adapters, hidden shell/Python glue, pointer-as-state mechanics, or report-parsing semantics;
- redesign of shared Core AST, Semantic IR, Executable IR, checkpoint identity, or shared validation.

Stop conditions:

- if the remaining failure is actually missing `:forall` specialization or structural-constraint machinery rather than loop-state carriage, stop and hand the failure back to the relevant prerequisite slice instead of widening this one;
- if a proposed fix requires changing bridge ownership in `phase_stdlib_typecheck.py` or authoring the full stdlib loop in `std/phase.orc`, stop and reopen the downstream stdlib implementation slice.

## Locked Decisions

Do not reopen these decisions during execution:

- `loop-state` is a frontend expression family, not a runtime primitive and not a top-level definition form.
- The surface has exactly two authored modes in this slice:
  - seed form with explicit typed fields
  - update form with `:like` and keyword overrides
- The generated carrier is local, monomorphic, compile-time-only, and not exported.
- Generic specialization still follows:
  - resolve concrete type arguments
  - check constraints
  - instantiate monomorphic helper
  - typecheck instantiated helper
  - lower through ordinary shared paths
- `loop/recur` stays on the existing shared `repeat_until` route.
- Final typed exhaustion projection must read authored loop-frame outputs, not Python-authored hidden review-loop state.
- Runtime-visible artifacts, Semantic IR, Executable IR, runtime plans, and persisted state must not leak generated `%loop-state` carrier names, `TypeParamRef`, `ProcRef`, `WorkflowRef`, provider refs, or prompt refs.

## File Map

Primary semantic owners:

- `orchestrator/workflow_lisp/loop_state.py`
- `tests/test_workflow_lisp_loop_state.py`
- `tests/test_workflow_lisp_loop_recur.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_phase_stdlib.py`

Routing or admission surfaces to edit only if characterization proves the need:

- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/expression_traversal.py`
- `orchestrator/workflow_lisp/form_registry.py`
- `orchestrator/workflow_lisp/functions.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/typecheck_dispatch.py`
- `orchestrator/workflow_lisp/lowering/values.py`
- `orchestrator/workflow_lisp/lowering/control_loops.py`
- `orchestrator/workflow_lisp/lowering/control_dispatch.py`
- `orchestrator/workflow_lisp/lowering/core.py`

Documentation surface to edit only if behavior/examples drift:

- `docs/lisp_workflow_drafting_guide.md`

Do not modify for this slice:

- `orchestrator/workflow_lisp/phase_stdlib_typecheck.py`
- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- shared runtime modules under `orchestrator/workflow/`
- `specs/`

## Required Behavioral Contract

Keep these implementation rules fixed:

- a seed form declares the complete carrier field set and rejects duplicate names;
- an update form must begin with `:like <existing-carrier>` and rejects unknown or duplicate overrides;
- field types may mention caller-specialized concrete types only after specialization; unresolved `TypeParamRef` must fail closed;
- runtime-forbidden values must be rejected in loop-state fields before lowering;
- update values preserve the exact base carrier type;
- ordinary record field access and `match` remain the proof model for loop-state contents;
- seed and update values lower to inline record-shaped local values, not to a new runtime primitive;
- `loop/recur` accepts loop-state carriers directly or through local aliases;
- final typed exhaustion projection uses authored carrier outputs and existing loop result normalization;
- source maps must point generated carrier fields and loop-frame projections back to authored `loop-state` spans;
- no hidden review-loop-specific state synthesis may survive in the promoted path exercised by these tests.

## Task 1: Rebaseline The Slice And Freeze The Missing Contract With Tests

**Files:**

- Review: `orchestrator/workflow_lisp/loop_state.py`
- Review: `orchestrator/workflow_lisp/expressions.py`
- Review: `orchestrator/workflow_lisp/typecheck_dispatch.py`
- Review: `orchestrator/workflow_lisp/lowering/values.py`
- Review: `orchestrator/workflow_lisp/lowering/control_loops.py`
- Modify: `tests/test_workflow_lisp_loop_state.py`
- Modify: `tests/test_workflow_lisp_loop_recur.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] **Step 1: Reconfirm the baseline selectors from the recorded iteration-5 command bundle**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_loop_state.py -q
python -m pytest tests/test_workflow_lisp_functions.py tests/test_workflow_lisp_loop_state.py -q
python -m pytest tests/test_workflow_lisp_loop_recur.py -k 'loop_state or on_exhausted' -q
python -m pytest tests/test_workflow_lisp_procedures.py -k 'loop_state' -q
python -m pytest tests/test_workflow_lisp_phase_stdlib.py::test_authored_loop_state_review_findings_keeps_strict_relpath_contracts -q
python -m pytest tests/test_workflow_lisp_phase_stdlib.py::test_phase_stdlib_review_loop_bridge_still_compiles_after_structural_constraints -q
```

Expected:

- collection works for the focused loop-state surface;
- any current failures identify the remaining gap precisely enough to keep edits in the narrow owner modules above.

- [ ] **Step 2: Expand tests only where the acceptance contract is still missing**

Audit the existing test files and add or tighten only the missing assertions for:

- imported generic `.orc` loop-state carriage with at least one caller-specialized field plus fixed stdlib-owned fields;
- `:like` update reuse of the same carrier type;
- rejection of runtime-forbidden field types;
- rejection of unknown or duplicate `:like` overrides;
- no leaked `%loop-state` names or unresolved type metadata in runtime-visible payloads;
- strict `ReviewFindings.items_path` preservation through authored loop-state carriage;
- unchanged bridge compile smoke after the bounded slice lands.

Prefer extending existing inline module fixtures in the current test files. Add new on-disk `.orc` fixtures only if source-map or imported-module path assertions cannot be expressed clearly inline.

- [ ] **Step 3: Run collect-only on any test modules that gain new or renamed tests**

Run narrow collect-only commands for whichever of these files change:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_loop_state.py -q
python -m pytest --collect-only tests/test_workflow_lisp_loop_recur.py -q
python -m pytest --collect-only tests/test_workflow_lisp_procedures.py -q
python -m pytest --collect-only tests/test_workflow_lisp_phase_stdlib.py -q
```

Expected: collection succeeds before semantic edits begin.

## Task 2: Keep `loop_state.py` As The Semantic Owner And Close Typing Gaps

**Files:**

- Modify: `orchestrator/workflow_lisp/loop_state.py`
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py`
- Modify: `orchestrator/workflow_lisp/diagnostics.py`
- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/expression_traversal.py`
- Modify: `orchestrator/workflow_lisp/form_registry.py`
- Modify: `orchestrator/workflow_lisp/functions.py`
- Test: `tests/test_workflow_lisp_loop_state.py`
- Test: `tests/test_workflow_lisp_procedures.py`

- [ ] **Step 1: Localize any admission or routing gaps without moving ownership**

If characterization shows missing admission behavior, keep fixes narrow:

- `expressions.py` only elaborates `LoopStateSeedExpr` / `LoopStateUpdateExpr`;
- `expression_traversal.py` only walks loop-state children;
- `form_registry.py` only classifies the public form;
- `functions.py` only preserves purity/external-dependency handling for loop-state children;
- `typecheck_dispatch.py` only routes loop-state typing into `loop_state.py`.

Do not reintroduce loop-state semantics into router or facade modules.

- [ ] **Step 2: Finish seed-form semantic checks in `loop_state.py`**

Make sure the seed path:

- resolves field types after specialization;
- rejects unresolved `TypeParamRef`;
- rejects runtime-forbidden field types;
- typechecks every field value against its declared type;
- creates one synthetic local carrier metadata record with stable field-origin tracking;
- rejects fields that cannot lower through the existing carried-state projection helpers.

- [ ] **Step 3: Finish update-form semantic checks in `loop_state.py`**

Make sure the update path:

- requires a genuine loop-state base carrier;
- rejects unknown or duplicate overrides;
- typechecks override values against the existing carrier field types;
- preserves the exact carrier type for the result;
- retains authored field-origin data so later lowering/source-map checks can point back to the correct seed or override field.

- [ ] **Step 4: Re-run the narrow typing selectors**

Run:

```bash
python -m pytest tests/test_workflow_lisp_functions.py tests/test_workflow_lisp_loop_state.py -q
python -m pytest tests/test_workflow_lisp_procedures.py -k 'loop_state' -q
```

Expected:

- loop-state surface tests pass;
- imported generic carriage tests pass without widening into specialization-ownership changes outside this slice.

## Task 3: Finish Lowering, Loop Integration, And Source-Map Lineage

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering/values.py`
- Modify: `orchestrator/workflow_lisp/lowering/control_loops.py`
- Modify: `orchestrator/workflow_lisp/lowering/control_dispatch.py`
- Modify: `orchestrator/workflow_lisp/lowering/core.py`
- Modify only if targeted tests fail: `orchestrator/workflow_lisp/source_map.py`
- Test: `tests/test_workflow_lisp_loop_state.py`
- Test: `tests/test_workflow_lisp_loop_recur.py`

- [ ] **Step 1: Keep record-shaped lowering in `lowering/values.py`**

Lower seed and update forms into ordinary inline record-shaped local values:

- seed forms should materialize explicit lowered fields with origin data;
- update forms should reuse the base carrier type, copy omitted fields from `:like`, and lower only explicit overrides;
- no loop-state-specific runtime primitive, helper step, or hidden bridge-owned state should be introduced.

- [ ] **Step 2: Keep loop-boundary acceptance in `lowering/control_loops.py`**

Ensure `loop/recur` accepts:

- direct seed values;
- local aliases that resolve to the same carrier;
- update values in `continue` paths;
- typed exhaustion projection from authored loop-frame outputs through the existing loop normalization route.

If the generated loop frame or final projection loses authored-field provenance, fix it in the loop-lowering owner rather than by special-casing tests.

- [ ] **Step 3: Touch dispatch/core routers only if tests show a real routing bug**

`lowering/control_dispatch.py` and `lowering/core.py` should remain routers. If a targeted failure requires a change there, keep it limited to dispatching the already-owned loop-state lowering path.

- [ ] **Step 4: Re-run the focused lowering selectors**

Run:

```bash
python -m pytest tests/test_workflow_lisp_loop_recur.py -k 'loop_state or on_exhausted' -q
python -m pytest tests/test_workflow_lisp_loop_state.py -q
```

Expected:

- loop-state carriers survive ordinary `loop/recur` carriage and typed exhaustion projection;
- source-map and origin assertions pass for authored loop-state fields and generated loop-frame projections;
- no `%loop-state` implementation detail leaks into lowered runtime-visible payloads.

## Task 4: Prove Future-Consumer Safety, Preserve Bridge Compatibility, And Align Docs

**Files:**

- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify if current text drifts: `docs/lisp_workflow_drafting_guide.md`
- Review only: `orchestrator/workflow_lisp/phase_stdlib_typecheck.py`
- Review only: `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`

- [ ] **Step 1: Keep the future-consumer check focused on strict findings-path behavior**

Use `tests/test_workflow_lisp_phase_stdlib.py::test_authored_loop_state_review_findings_keeps_strict_relpath_contracts` as the direct proof that authored loop-state carriage does not weaken `ReviewFindings.items_path` validation or relpath authority.

Do not absorb broader reusable-phase-state failures into this slice unless a loop-state edit directly causes them.

- [ ] **Step 2: Keep the bridge smoke selector unchanged**

Use `tests/test_workflow_lisp_phase_stdlib.py::test_phase_stdlib_review_loop_bridge_still_compiles_after_structural_constraints` as a regression guard only. The bridge remains in place; the test exists to prove this prerequisite does not break the still-active compatibility path.

- [ ] **Step 3: Update the drafting guide only if behavior or examples drift**

If implementation changes the observable author-facing rules, update `docs/lisp_workflow_drafting_guide.md` Section `17.1` so it matches:

- seed syntax;
- `:like` update syntax;
- local-only carrier scope;
- no runtime-forbidden field contents;
- use as the author-facing carrier for typed loop-frame state.

Skip doc edits if the current guide already matches the final behavior exactly.

- [ ] **Step 4: Run the targeted future-consumer and bridge checks**

Run:

```bash
python -m pytest tests/test_workflow_lisp_phase_stdlib.py::test_authored_loop_state_review_findings_keeps_strict_relpath_contracts -q
python -m pytest tests/test_workflow_lisp_phase_stdlib.py::test_phase_stdlib_review_loop_bridge_still_compiles_after_structural_constraints -q
```

Expected:

- authored loop-state carriage preserves strict findings-path contracts;
- the unchanged bridge still compiles after the bounded slice.

## Task 5: Run The Recorded Broader Sweep And Record Off-Footprint Handoffs

**Files:**

- Modify if needed: `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-parametric-loop-state-authoring/execution_plan.md`
- No code ownership expansion unless failures prove this slice caused them

- [ ] **Step 1: Run the broader coordination sweep from the recorded command bundle**

Run:

```bash
python -m pytest tests/test_workflow_lisp_functions.py tests/test_workflow_lisp_loop_state.py tests/test_workflow_lisp_loop_recur.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_phase_stdlib.py -q
```

Expected:

- all in-footprint selectors pass; or
- any remaining failures are clearly outside the bounded ownership of this slice and can be recorded as handoffs without widening the implementation.

- [ ] **Step 2: Classify remaining failures before touching more code**

Use this decision rule:

- if a failure is in `loop_state.py`, its immediate routing surfaces, loop lowering, imported generic carriage, or the strict findings-path regression, fix it here;
- if a failure is in reusable-phase-state validation, output-contract path authority, resume policy, or bridge retirement, record it as off-footprint and stop instead of widening the slice.

- [ ] **Step 3: Record what changed and what was verified**

Before closing the slice, summarize:

- files changed in the frontend owner path;
- whether guide text changed;
- which recorded commands passed;
- any remaining failures intentionally handed off because they belong to another owner slice.

## Completion Checklist

The slice is ready to mark complete only when all of these are true:

- imported generic `.orc` code can author one loop-state carrier with caller-specialized and fixed stdlib-owned fields;
- the carrier specializes to a monomorphic local record-like type before ordinary lowering;
- `loop/recur` carries that authored carrier through `continue` and final typed exhaustion projection without hidden review-loop-specific state synthesis;
- field access and `match` work through ordinary frontend rules;
- lowered artifacts contain no leaked `%loop-state` internals, unresolved type parameters, `ProcRef`, `WorkflowRef`, provider refs, or prompt refs from the carrier surface;
- source maps identify authored loop-state origins and generated loop-frame projection surfaces;
- strict `ReviewFindings.items_path` contracts survive authored loop-state carriage;
- the unchanged review-loop bridge still compiles on the targeted smoke selector;
- the broader recorded sweep is either green for this footprint or any remaining failures are explicitly classified as outside this slice.
