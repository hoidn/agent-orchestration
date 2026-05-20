# Phase Context And Standard Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the selected Stage 5 Workflow Lisp frontend slice: generic `RunCtx` / `PhaseCtx`, generalized `with-phase` / `phase-target`, and the bounded standard-library forms `produce-one-of`, `run-provider-phase`, `review-revise-loop`, and `resume-or-start`, while preserving the existing Stage 4 implementation-attempt translation as a compatibility regression.

**Architecture:** Keep frontend ownership in `orchestrator/workflow_lisp/` and shared execution semantics in `orchestrator/workflow/`. Reuse the existing read -> syntax -> macro expansion -> definitions/procedures/workflows -> typecheck -> lowering -> shared-validation seam; derive phase layout paths from typed phase context instead of manual bundle/target fields; lower the new stdlib forms only through existing runtime surfaces (`provider-result`, `command-result`, `pre_snapshot`, `select_variant_output`, `repeat_until`) plus certified adapter backends where the architecture explicitly allows them.

**Tech Stack:** Python 3, dataclasses, existing `orchestrator.workflow_lisp` Stage 1-4 modules, shared workflow loader/validator/runtime, `CertifiedAdapterBinding`, pytest, `.orc` fixtures under `tests/fixtures/workflow_lisp/`, and adapter entrypoints under `python -m orchestrator.workflow_lisp.adapters.*`.

---

## Fixed Inputs

Treat these as the implementation authority:

- `docs/index.md`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `19. Context Types`
  - `20. Canonical State Layout`
  - `21. Phase Context`
  - `24. Produced Outcome`
  - `26. run-provider-phase`
  - `27. review-revise-loop`
  - `28. resume-or-start`
  - `57. review-revise-loop Lowering`
  - `103. Stage 5: Phase And Context Library`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `2. Relationship To The Full Specification`
  - `3. Non-Goals`
  - `14. Implementation Stages`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_source_map.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`
- `artifacts/review/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/architecture-review.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/4/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/4/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

Current checkout notes that must not be rediscovered during implementation:

- `docs/steering.md` is empty in this checkout, so it adds no extra local steering beyond repo instructions.
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` currently has no events, so do not infer partial completion from the ledger.

## Hard Scope Limits

Implement only this bounded slice:

- minimal prelude/type additions for authored `RunCtx` / `PhaseCtx`:
  - `RunId`
  - `Symbol`
  - `Path.state-root`
  - `Path.artifact-root`
- generic `PhaseCtx` support for new phase stdlib forms;
- one explicit `ImplementationAttemptPhaseCtx` compatibility bridge for the existing Stage 4 implementation-attempt regression only;
- derived phase layout paths from phase context roots plus authored phase symbol;
- expression, typechecking, diagnostics, and lowering for:
  - `produce-one-of`
  - `run-provider-phase`
  - `review-revise-loop`
  - `resume-or-start`
- one static reusable-state validator binding:
  - `validate_reusable_phase_state`
- compiler-generated fixed-output loader bindings:
  - `load_canonical_phase_result__<ReturnTypeName>`
- regression coverage for Stage 4 implementation-attempt translation on top of the generalized phase substrate.

Explicit non-goals:

- no `phase-ctx`, `item-ctx`, `drain-ctx`, or other context-construction syntax;
- no `resource-transition`, `finalize-selected-item`, `backlog-drain`, workflow refs, `loop/recur`, or drain orchestration;
- no widening of shared runtime/state schema, pointer authority, variant proof, or source-map core contracts;
- no runtime-native reusable-state primitive;
- no report parsing, pointer-as-state, inline semantic shell/Python glue, or ad hoc wrappers;
- no widening of Stage 3 record-only workflow return boundaries;
- no relpath-valued `repeat_until.on_exhausted.outputs`.

## File Ownership

Create:

- `orchestrator/workflow_lisp/adapters/__init__.py`
- `orchestrator/workflow_lisp/adapters/load_canonical_phase_result.py`
- `orchestrator/workflow_lisp/adapters/validate_reusable_phase_state.py`
- `orchestrator/workflow_lisp/phase_stdlib.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/fixtures/workflow_lisp/valid/phase_stdlib_run_provider_phase.orc`
- `tests/fixtures/workflow_lisp/valid/phase_stdlib_review_loop.orc`
- `tests/fixtures/workflow_lisp/valid/phase_stdlib_resume_or_start.orc`
- `tests/fixtures/workflow_lisp/invalid/phase_ctx_contract_invalid.orc`
- `tests/fixtures/workflow_lisp/invalid/phase_ctx_legacy_bridge_misuse.orc`
- `tests/fixtures/workflow_lisp/invalid/phase_target_unknown_generic.orc`
- `tests/fixtures/workflow_lisp/invalid/review_loop_result_contract_invalid.orc`
- `tests/fixtures/workflow_lisp/invalid/resume_or_start_contract_invalid.orc`
- `tests/fixtures/workflow_lisp/invalid/resume_or_start_uncertified_adapter.orc`

Modify:

- `orchestrator/workflow_lisp/__init__.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/phase.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/workflows.py`
- `tests/test_loader_validation.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_phase_translation.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_structured_results.py`
- `tests/test_neurips_plan_gate_recovery.py`
- `tests/fixtures/workflow_lisp/valid/neurips_implementation_attempt.orc`
- existing invalid phase fixtures only if the new generic contracts make them stale.

Modify only if a focused failing test proves the need:

- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/workflows.py` beyond command-boundary registration helpers

Reuse without widening ownership:

- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/macros.py`
- `orchestrator/workflow_lisp/procedures.py`
- shared modules under `orchestrator/workflow/`

## Required Contracts

Keep these implementation contracts fixed:

- Authored generic context surface:

```lisp
(defrecord RunCtx
  (run-id RunId)
  (state-root Path.state-root)
  (artifact-root Path.artifact-root))

(defrecord PhaseCtx
  (run RunCtx)
  (phase-name Symbol)
  (state-root Path.state-root)
  (artifact-root Path.artifact-root))
```

- `with-phase` accepts either:
  - normative `PhaseCtx`; or
  - legacy `ImplementationAttemptPhaseCtx` only when preserving the existing Stage 4 regression.
- `run-provider-phase` requires `:ctx PhaseCtx` and a union `:returns`.
- `produce-one-of` is the only selected form that may use `pre_snapshot` + `select_variant_output`.
- `review-revise-loop` lowers through `repeat_until`, carries `last-review-report` through ordinary loop outputs, and uses scalar-only `on_exhausted.outputs`.
- `resume-or-start` uses:

```text
validate_reusable_phase_state
load_canonical_phase_result__<ReturnTypeName>
```

and never hides recovery behavior behind inline glue.

- Stable error taxonomy for hard reuse failures:

```text
resume_state_path_unsafe
resume_state_pointer_authority_forbidden
resume_state_bundle_schema_invalid
resume_state_required_artifact_missing
resume_state_contract_invalid
resume_state_loader_contract_invalid
resume_state_loader_schema_invalid
```

## Task 1: Add Fixtures And Failing Tests For The New Slice

**Files:**

- Create: `tests/test_workflow_lisp_phase_stdlib.py`
- Create: all new valid and invalid `.orc` fixtures listed above
- Modify: `tests/test_workflow_lisp_phase_translation.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_structured_results.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/fixtures/workflow_lisp/valid/neurips_implementation_attempt.orc`

- [ ] **Step 1: Create the new valid fixture surface**

Create one fixture per major stdlib form:

- `phase_stdlib_run_provider_phase.orc`
  - includes `RunCtx`, `PhaseCtx`, a union return type, and one workflow using `run-provider-phase`;
  - includes one workflow using `produce-one-of` so snapshot-evidence lowering is exercised without creating another file.
- `phase_stdlib_review_loop.orc`
  - includes a return union with exact `APPROVED`, `BLOCKED`, and `EXHAUSTED` variants;
  - uses `last-review-report` on the `EXHAUSTED` branch.
- `phase_stdlib_resume_or_start.orc`
  - includes one record-returning resume form and one union-returning resume form;
  - keeps `:start` on locally lowerable expressions or `command-result`, not union-returning workflow `call`.

- [ ] **Step 2: Create the new invalid fixture surface**

Add focused invalid fixtures for:

- generic `PhaseCtx` contract violations;
- misuse of the legacy `ImplementationAttemptPhaseCtx` bridge in a new generic workflow;
- unknown generic phase target name;
- bad `review-revise-loop` return union contract;
- bad `resume-or-start` `:resume-from` / `:valid-when` / `:returns` combinations;
- attempted use of an uncertified adapter path for `resume-or-start`.

- [ ] **Step 3: Update the existing Stage 4 regression fixture**

Keep `tests/fixtures/workflow_lisp/valid/neurips_implementation_attempt.orc` as the compatibility proof:

- it must still compile and execute through the existing implementation-attempt flow;
- it must keep `ImplementationAttemptPhaseCtx`;
- it must be the only remaining allowed consumer of the legacy bridge.

- [ ] **Step 4: Write failing tests before implementation**

Add or extend tests so they fail on the current tree and cover:

- generic `PhaseCtx` typing;
- rejection of new generic misuse of `ImplementationAttemptPhaseCtx`;
- `run-provider-phase` and `produce-one-of` elaboration/type errors;
- `review-revise-loop` result-contract validation;
- `resume-or-start` reusable-variant validation and adapter certification requirements;
- Stage 4 regression still compiling with the bounded bridge;
- shared loader validation continuing to reject relpath `repeat_until.on_exhausted.outputs`.

Suggested test names:

```python
test_typecheck_accepts_generic_phase_ctx_for_run_provider_phase
test_typecheck_rejects_legacy_phase_ctx_bridge_in_generic_stdlib
test_lowering_run_provider_phase_derives_phase_bundle_path
test_lowering_produce_one_of_uses_pre_snapshot_and_select_variant_output
test_lowering_review_loop_carries_last_review_report_through_loop_outputs
test_typecheck_rejects_invalid_review_loop_result_contract
test_lowering_resume_or_start_registers_generated_loader_binding
test_typecheck_rejects_resume_or_start_without_certified_adapter
```

- [ ] **Step 5: Run collection checks**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_phase_stdlib.py -q
python -m pytest --collect-only tests/test_workflow_lisp_phase_translation.py -q
```

Expected:

- both modules collect successfully;
- several tests still fail if run, because implementation is not in place yet.

## Task 2: Generalize Prelude Types And Phase Scope

**Files:**

- Modify: `orchestrator/workflow_lisp/type_env.py`
- Modify: `orchestrator/workflow_lisp/phase.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_phase_translation.py`

- [ ] **Step 1: Extend the frontend prelude with the minimal context surface**

In `type_env.py`:

- add `RunId` and `Symbol` to `PRELUDE_TYPE_NAMES`;
- add compiler-owned synthetic path contracts for:
  - `Path.state-root`
  - `Path.artifact-root`
- represent those synthetic paths as `PathTypeRef`s backed by fixed `PathDef`-like metadata rather than asking authors to define them locally.

- [ ] **Step 2: Replace the Stage 4 hard-coded phase scope with a generic model**

In `phase.py` introduce:

- `PhaseLayout`
  - `phase_name`
  - `state_root_ref`
  - `artifact_root_ref`
  - `state_bundle_path`
  - `temp_bundle_path`
  - `snapshot_root`
  - `candidate_root`
  - `target_refs`
- `PhaseScope`
  - normative `PhaseCtx` metadata plus derived layout
- one explicit helper for the legacy bridge:
  - converts `ImplementationAttemptPhaseCtx` to an internal `PhaseLayout` only for the existing Stage 4 workflow.

- [ ] **Step 3: Enforce generic and legacy phase contracts explicitly**

Implement validation helpers that:

- accept authored `PhaseCtx` for new generic stdlib forms;
- reject `ImplementationAttemptPhaseCtx` in new generic forms with `phase_ctx_legacy_bridge_invalid`;
- reject unresolved generic phase targets with `phase_target_contract_unresolved`;
- produce `phase_name_mismatch` if authored symbol and runtime `ctx.phase-name` diverge in the generated validation path.

- [ ] **Step 4: Run focused phase-contract tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "phase_ctx" -q
python -m pytest tests/test_workflow_lisp_phase_translation.py -k "implementation_attempt or phase_ctx or phase_target" -q
```

Expected:

- generic phase tests start passing;
- Stage 4 regression tests still pass;
- stdlib-form tests still fail where new expression and lowering work is missing.

## Task 3: Add Stdlib Expression Nodes, Elaboration, And Typechecking

**Files:**

- Modify: `orchestrator/workflow_lisp/expressions.py`
- Create: `orchestrator/workflow_lisp/phase_stdlib.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/__init__.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] **Step 1: Add explicit expression nodes for the selected stdlib forms**

In `expressions.py`, add dataclasses for:

- `RunProviderPhaseExpr`
- `ProduceOneOfExpr`
- `ReviewReviseLoopExpr`
- `ResumeOrStartExpr`

plus the smallest helper nodes needed to keep their operands structured, such as:

- candidate/variant descriptors for `produce-one-of`;
- reusable-variant lists for `resume-or-start`;
- optional check-step metadata for `review-revise-loop`.

Do not encode these forms as macros or opaque lists.

- [ ] **Step 2: Elaborate the new forms with deterministic argument validation**

Add elaboration helpers that reject malformed surfaces early with dedicated diagnostics:

- `run_provider_phase_return_invalid`
- `produce_one_of_candidate_invalid`
- `review_loop_result_contract_invalid`
- `resume_or_start_contract_invalid`
- `resume_or_start_reusable_variant_invalid`

Keep the existing unquoted-symbol handling for `phase-target`.

- [ ] **Step 3: Add frontend-local typing rules**

In `typecheck.py`:

- `run-provider-phase`
  - `:ctx` must resolve to generic `PhaseCtx`;
  - `:returns` must resolve to a union.
- `produce-one-of`
  - validate declared candidates against the union variants and required artifact path fields.
- `review-revise-loop`
  - validate the return union has `APPROVED`, `BLOCKED`, `EXHAUSTED`;
  - validate the required report-path fields are present on the correct variants.
- `resume-or-start`
  - `:resume-from` must be a canonical bundle relpath, not a pointer path;
  - `:valid-when` variants must exist on the declared return union;
  - `:start` must typecheck to the exact authored `:returns` type;
  - union-returning workflow `call`s in `:start` stay rejected in this slice.

- [ ] **Step 4: Record reusable-state metadata on the typed expression**

Add a typed helper record in `phase_stdlib.py`, for example:

```python
@dataclass(frozen=True)
class ResumeValidationSpec:
    resume_from_expr: ExprNode
    return_type_ref: RecordTypeRef | UnionTypeRef
    valid_variants: tuple[str, ...]
    required_artifact_fields: Mapping[str, tuple[str, ...]]
    validator_adapter_name: str
    decision_type_name: str
    source_map_behavior: str
```

Store this on typed `resume-or-start` expressions so lowering does not have to recompute the contract.

- [ ] **Step 5: Run focused stdlib typing tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "run_provider_phase or produce_one_of or review_loop or resume_or_start" -q
```

Expected:

- elaboration/type errors now match the new diagnostics;
- lowering-oriented tests still fail until generated workflow mappings exist.

## Task 4: Lower Generic Phase Forms, `run-provider-phase`, And `produce-one-of`

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `orchestrator/workflow_lisp/phase.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] **Step 1: Generalize active phase scope handling in lowering**

Replace the current implementation-only lowering path with generic phase layout derivation:

- keep `with-phase` compile-time only;
- resolve active `PhaseLayout` from either generic `PhaseCtx` or the legacy bridge;
- derive deterministic:
  - canonical bundle path
  - temp bundle path
  - snapshot root
  - candidate root
  - named target refs

Do not read or synthesize manual state-path fields for generic `PhaseCtx`.

- [ ] **Step 2: Lower `run-provider-phase` through existing `provider-result` machinery**

Generate the same structured provider step shape used by Stage 3:

- provider extern stays on the existing extern boundary;
- `variant_output.path` binds to the derived canonical phase bundle path;
- generated artifacts and paths are added to the lowering-origin map;
- reports remain views; the bundle remains authoritative.

- [ ] **Step 3: Lower `produce-one-of` through evidence-based shared surfaces**

Generate:

- `pre_snapshot`
- producer step
- `select_variant_output`

with:

- `snapshot_diff` evidence only;
- canonical selected bundle path from `PhaseLayout`;
- no report parsing, no mtime routing, no best-guess candidate selection.

- [ ] **Step 4: Extend lowering tests to inspect the generated mappings**

Assert in `tests/test_workflow_lisp_phase_stdlib.py` or `tests/test_workflow_lisp_lowering.py` that:

- `run-provider-phase` lowers to a provider step plus typed result projection;
- `produce-one-of` lowers to `pre_snapshot` and `select_variant_output`;
- derived bundle and snapshot paths are stable and workspace-relative.

- [ ] **Step 5: Run focused lowering tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "run_provider_phase or produce_one_of" -q
python -m pytest tests/test_workflow_lisp_structured_results.py -k "command_result or variant_output" -q
```

Expected:

- new phase-producer lowering tests pass;
- existing structured-result tests still pass unchanged.

## Task 5: Lower `review-revise-loop` Through `repeat_until` Plus Post-Loop Normalization

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_lowering.py`

- [ ] **Step 1: Generate the loop frame using the current shared contract**

Lower `review-revise-loop` to one `repeat_until` frame with:

- stable `repeat_until.id`;
- carried loop outputs for scalar terminal state;
- carried loop outputs for the latest typed review artifacts, including `last-review-report`;
- review/fix provider or command steps lowered through existing Stage 3 surfaces.

- [ ] **Step 2: Keep exhaustion overrides scalar-only**

Implement the generated loop so that:

- `repeat_until.on_exhausted.outputs` contains only scalar fields such as terminal decision, exhausted flag, and reason;
- no relpath artifact field is emitted there;
- `EXHAUSTED.last-review-report` comes from an ordinary loop output in a post-loop normalization step.

- [ ] **Step 3: Add the typed normalization step after the loop**

Generate one post-loop step that maps the loop-frame outputs into the authored result union:

- `APPROVED`
- `BLOCKED`
- `EXHAUSTED`

and keeps source-map blame anchored to the `review-revise-loop` form.

- [ ] **Step 4: Add shared loader-validation regression coverage**

In `tests/test_loader_validation.py`, add or extend a test that proves:

- relpath-valued `repeat_until.on_exhausted.outputs` are still rejected by shared validation;
- the new frontend lowering never emits that invalid shape.

- [ ] **Step 5: Run review-loop and loader-validation tests**

Run:

```bash
python -m pytest tests/test_loader_validation.py -k "repeat_until_on_exhausted or relpath_output_override" -q
python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "review_loop or exhausted or last_review_report" -q
```

Expected:

- loader validation remains strict;
- review-loop lowering passes without widening the shared runtime contract.

## Task 6: Implement `resume-or-start` Adapters, Binding Registration, And Lowering

**Files:**

- Create: `orchestrator/workflow_lisp/adapters/__init__.py`
- Create: `orchestrator/workflow_lisp/adapters/validate_reusable_phase_state.py`
- Create: `orchestrator/workflow_lisp/adapters/load_canonical_phase_result.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `orchestrator/workflow_lisp/phase_stdlib.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_neurips_plan_gate_recovery.py`

- [ ] **Step 1: Implement the reusable-state validator backend**

Create `validate_reusable_phase_state.py` as a deterministic CLI module that:

- reads a structured input payload containing:
  - `resume_from`
  - `expected_return_type`
  - `valid_variants`
  - `required_artifact_fields`
- emits one decision union:
  - `REUSE` with `source_bundle_path`
  - `START` with `reason_code`
- exits nonzero for hard failures in the approved error taxonomy;
- treats pointer authority violations as hard failures, not `START`.

- [ ] **Step 2: Implement the canonical-bundle loader backend**

Create `load_canonical_phase_result.py` as a deterministic CLI module that:

- reads:
  - `bundle_path`
  - `expected_return_type`
- validates the canonical bundle shape against the authored type name supplied by the binding;
- emits the authored top-level record or union directly so existing `command-result` lowering can reuse `output_bundle` or `variant_output`.

- [ ] **Step 3: Register certified bindings without widening their contract**

In `workflows.py` and `compiler.py`:

- merge one default `validate_reusable_phase_state` binding into the command-boundary environment when a module uses `resume-or-start`;
- generate one deterministic loader binding per authored return type:
  - `load_canonical_phase_result__PlanGateResult`
  - `load_canonical_phase_result__SomeRecordResult`
- keep `CertifiedAdapterBinding.output_type_name` fixed and exact.

Use a compiler-owned template like:

```python
CertifiedAdapterBinding(
    name="validate_reusable_phase_state",
    stable_command=("python", "-m", "orchestrator.workflow_lisp.adapters.validate_reusable_phase_state"),
    input_contract={...},
    output_type_name="ResumeReuseDecision",
    effects=("resume_state_reuse", "structured_result"),
    path_safety={...},
    source_map_behavior="step",
    fixture_ids=(...),
    negative_fixture_ids=(...),
)
```

- [ ] **Step 4: Lower `resume-or-start` into validator -> match -> loader/start**

Generate:

- validator `command-result`;
- `match` on `REUSE` vs `START`;
- `REUSE` branch loader `command-result` using the generated fixed-output binding;
- `START` branch lowering of the authored expression;
- normalization to a single authored return type.

Reject uncertified or malformed backends with:

- `resume_or_start_uncertified_backend`
- `resume_or_start_contract_invalid`

- [ ] **Step 5: Add runtime/recovery smoke coverage**

Use `tests/test_workflow_lisp_phase_stdlib.py` for direct frontend coverage and keep `tests/test_neurips_plan_gate_recovery.py` as the nearest recovery smoke. Only edit the latter if a failing assertion proves the reusable-state contract needs a clearer regression case.

- [ ] **Step 6: Run focused resume tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "resume_or_start or reusable_state or load_canonical_phase_result or generated_loader_binding or fixed_output_loader" -q
python -m pytest tests/test_neurips_plan_gate_recovery.py -q
```

Expected:

- direct `resume-or-start` tests pass;
- recovery smoke remains green.

## Task 7: Integrate Public Exports, Preserve Stage 4 Regression, And Run Cross-Slice Regressions

**Files:**

- Modify: `orchestrator/workflow_lisp/__init__.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `tests/test_workflow_lisp_phase_translation.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_structured_results.py`

- [ ] **Step 1: Export the new frontend surface**

Update `__init__.py` to export the new stdlib expression nodes and any public helpers that the tests or compiler use. Do not export internal lowering-only helpers unless a test needs them.

- [ ] **Step 2: Keep the existing Stage 4 translation as a required regression**

Ensure the generalized phase infrastructure does not replace the Stage 4 bridge:

- `neurips_implementation_attempt.orc` still compiles;
- the existing fake-provider execution tests still pass;
- new generic stdlib forms do not depend on `ImplementationAttemptPhaseCtx`.

- [ ] **Step 3: Run shared cross-slice regressions**

Run:

```bash
python -m pytest tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_structured_results.py -q
python -m pytest tests/test_workflow_lisp_phase_translation.py -k "implementation_attempt or phase_ctx or phase_target" -q
```

Expected:

- helper workflows, effect summaries, structured-result lowering, and the Stage 4 translation all remain valid.

## Task 8: Full Verification Sweep

**Files:**

- No new files; this task is verification-only.

- [ ] **Step 1: Run the exact required command set**

Run the deterministic verification suite from `check_commands.json`:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_phase_stdlib.py -q
python -m pytest --collect-only tests/test_workflow_lisp_phase_translation.py -q
python -m pytest tests/test_loader_validation.py -k "repeat_until_on_exhausted or relpath_output_override" -q
python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "phase_ctx or run_provider_phase or produce_one_of or review_loop or exhausted or last_review_report or resume_or_start or reusable_state or load_canonical_phase_result or generated_loader_binding or fixed_output_loader" -q
python -m pytest tests/test_workflow_lisp_phase_translation.py -k "implementation_attempt or phase_ctx or phase_target" -q
python -m pytest tests/test_workflow_lisp_structured_results.py -k "command_result or variant_output" -q
python -m pytest tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_structured_results.py -q
python -m pytest tests/test_neurips_plan_gate_recovery.py -q
python -m pytest tests/test_workflow_lisp_reader.py tests/test_workflow_lisp_definitions.py tests/test_workflow_lisp_diagnostics.py tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_variant_proofs.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_phase_translation.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_structured_results.py -q
```

- [ ] **Step 2: Do not claim completion without fresh evidence**

Record the actual command outputs in the implementation handoff. If any focused selector fails, fix the implementation or the test setup; do not weaken verification to hide a contract mismatch.

## Acceptance Checklist

- [ ] `RunId`, `Symbol`, `Path.state-root`, and `Path.artifact-root` exist as minimal frontend prelude surface.
- [ ] New generic phase forms type against `PhaseCtx` and derived targets.
- [ ] `ImplementationAttemptPhaseCtx` remains only as the explicit Stage 4 compatibility bridge.
- [ ] `run-provider-phase` lowers through structured provider-result semantics with derived canonical bundle paths.
- [ ] `produce-one-of` lowers through `pre_snapshot` plus `select_variant_output`.
- [ ] `review-revise-loop` lowers through `repeat_until` with scalar-only exhaustion overrides and carried `last-review-report`.
- [ ] `resume-or-start` uses the certified reusable-state validator plus compiler-generated fixed-output loader bindings.
- [ ] Invalid prior state fails deterministically; absent or non-reusable prior state normalizes to `START`.
- [ ] Shared validation still rejects relpath-valued `repeat_until.on_exhausted.outputs`.
- [ ] Union-returning workflow `call`s remain out of scope on the `resume-or-start :start` branch.
- [ ] Stage 4 translation, Stage 3 structured results, macros, and `defproc` regressions still pass.
