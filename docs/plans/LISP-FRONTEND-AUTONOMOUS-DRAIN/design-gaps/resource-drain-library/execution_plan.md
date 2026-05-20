# Resource And Drain Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the bounded Stage 6 Workflow Lisp frontend slice for resource and drain orchestration: `ItemCtx` / `DrainCtx`, `resource-transition`, `finalize-selected-item`, compile-time-only workflow refs for drain roles, bounded union workflow returns across `call`, and `backlog-drain` lowering through shared runtime surfaces.

**Architecture:** Keep all new authoring-time ownership inside `orchestrator/workflow_lisp/` and continue lowering through the existing read -> syntax -> macro expansion -> definitions/procedures/workflows -> typecheck -> lowering -> shared-validation seam. Reuse Stage 5 phase stdlib, structured-result contracts, certified adapter bindings, and shared `repeat_until` / `call` / `variant_output` surfaces; do not add runtime-native queue/resource primitives, dynamic workflow loading, YAML generation, pointer-as-state, or inline semantic shell/Python glue.

**Tech Stack:** Python 3, dataclasses, the existing `orchestrator.workflow_lisp` compiler/typecheck/lowering modules, shared `orchestrator.workflow` validation/runtime surfaces, certified adapters invoked as `python -m orchestrator.workflow_lisp.adapters.*`, pytest, and `.orc` fixtures under `tests/fixtures/workflow_lisp/`.

---

## Fixed Inputs

Treat these files as the authority for this implementation slice:

- `docs/index.md`
- `docs/steering.md`
  - empty in this checkout; there is no additional local steering text beyond repo policy
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resource-drain-library/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`
  - currently `{"ledger_version":1,"events":[]}`; do not infer prior completion from the ledger

Authoritative interpretation already resolved by the work-item context:

- implement only the selected Stage 6 resource/drain tranche;
- keep workflow refs compile-time-only and restricted to stdlib operand roles `:selector`, `:run-item`, and `:gap-drafter`;
- keep ordinary workflow-boundary legality for `Provider` and `Prompt` unchanged;
- lower resource movement only through one certified adapter, `apply_resource_transition`;
- allow union workflow returns only through the existing structured-result projection machinery;
- prefer the richer Stage 6 end-to-end examples over shorthand examples when shorthand would force hidden ambient state.

## Current Checkout Facts

Do not rediscover these during implementation:

- The Stage 6 file footprint already exists in this checkout and should be treated as in-scope modification targets, not new file creation:
  - `orchestrator/workflow_lisp/resource.py`
  - `orchestrator/workflow_lisp/resource_stdlib.py`
  - `orchestrator/workflow_lisp/drain_stdlib.py`
  - `orchestrator/workflow_lisp/adapters/apply_resource_transition.py`
  - `tests/test_workflow_lisp_resource_stdlib.py`
  - `tests/test_workflow_lisp_drain_stdlib.py`
  - `tests/fixtures/workflow_lisp/valid/resource_stdlib_transition.orc`
  - `tests/fixtures/workflow_lisp/valid/resource_stdlib_finalize_selected_item.orc`
  - `tests/fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain.orc`
  - `tests/fixtures/workflow_lisp/invalid/item_ctx_contract_invalid.orc`
  - `tests/fixtures/workflow_lisp/invalid/drain_ctx_contract_invalid.orc`
  - `tests/fixtures/workflow_lisp/invalid/resource_transition_uncertified_adapter.orc`
  - `tests/fixtures/workflow_lisp/invalid/backlog_drain_workflow_ref_signature_invalid.orc`
  - `tests/fixtures/workflow_lisp/invalid/backlog_drain_union_call_boundary_invalid.orc`
- `orchestrator/workflow_lisp/compiler.py` already augments certified adapter bindings for Stage 5 surfaces; extend that pattern instead of inventing a second adapter-registration path.
- `orchestrator/workflow_lisp/contracts.py` already contains the structured-result contract derivation machinery that must be reused for union workflow returns.
- `orchestrator/workflow_lisp/workflows.py`, `typecheck.py`, `expressions.py`, `lowering.py`, `diagnostics.py`, and `macros.py` are the primary shared touchpoints for Stage 6 surface integration.
- The runtime smoke tests already exist:
  - `tests/test_lisp_frontend_autonomous_drain_runtime.py`
  - `tests/test_neurips_steered_backlog_runtime.py`

Execution rule: if a substep looks already implemented, prove it with the listed test before moving on. Do not widen scope for symmetry or cleanup.

## Hard Scope Limits

Implement only this bounded slice:

- frontend-local `ItemCtx` / `DrainCtx` contract checks and deterministic layout helpers;
- frontend AST, typechecking, diagnostics, and lowering for:
  - `resource-transition`
  - `finalize-selected-item`
  - `backlog-drain`
- one named certified adapter backend:
  - `apply_resource_transition`
- one compile-time workflow-ref authority surface limited to:
  - same-file workflows
  - compiler-registered imported bundles
  - stdlib roles `:selector`, `:run-item`, `:gap-drafter`
- one compile-time extern-rebinding path for provider/prompt-bearing workflow refs;
- one bounded drain loop substrate lowered through shared `repeat_until`;
- one narrow workflow-boundary revision allowing union workflow returns across `call` via generated structured-result outputs.

Explicitly out of scope:

- runtime-native queue/resource transaction effects;
- public first-class `WorkflowRef[...]` authoring or runtime workflow loading;
- a public general `loop/recur` language feature;
- module/import/export work;
- YAML generation, report parsing, pointer-as-state, inline semantic Python/shell glue, or uncataloged wrappers;
- redesign of shared Core AST, Semantic IR, proof graph, queue semantics, pointer authority, or runtime state schema.

## Locked Contracts

These decisions are already made and must not be reopened during implementation.

### Context Contracts

`RunCtx` stays unchanged. Add or complete frontend-local contract checkers for:

```text
ItemCtx
  run: RunCtx
  item-id: String
  state-root: relpath under state
  artifact-root: relpath under artifacts
  ledger: relpath under state

DrainCtx
  run: RunCtx
  state-root: relpath under state
  manifest: relpath under state
  ledger: relpath under state
```

The checker must validate field roles and relpath-under-root equivalence. It must not require one literal `defpath` name when an authored path contract satisfies the same role.

Derived helpers required by this slice:

```text
ItemLayout
  item_state_bundle_path
  item_temp_bundle_path
  outcome_bundle_path
  summary_target_path
  phase_root_prefix

DrainLayout
  run_state_bundle_path
  run_state_temp_bundle_path
  iteration_root_prefix
  summary_target_path
  gap_request_path
```

### Resource Transition

`resource-transition` must lower only through one static certified adapter:

```text
adapter name: apply_resource_transition
stable command: python -m orchestrator.workflow_lisp.adapters.apply_resource_transition
output type name: ResourceTransitionResult
declared effects: resource_transition, ledger_update
```

Minimum stable hard-failure codes:

```text
resource_transition_path_escape
resource_transition_missing_source
resource_transition_destination_conflict
resource_transition_ledger_update_failed
resource_transition_invalid_result
```

The authored adapter payload must cover transition name, source/resource identity, `from`, `to`, ledger path, derived state roots when needed, and the ledger event label.

### Finalization

`finalize-selected-item` uses the richer Stage 6 end-to-end calling convention:

```text
:ctx
:selected
:queue-transition
:roadmap
:plan
:implementation
```

It returns `SelectedItemResult` and may emit zero or one terminal `resource-transition`.

### Workflow Ref Roles

Workflow refs remain compile-time-only in this slice. Support only these frontend-local planning types:

```text
WorkflowRefAuthoritySource
WorkflowRefEnvironment
WorkflowRefRequirement
ResolvedWorkflowRef
WorkflowExternRebindingPlan
WorkflowRefCallPlan
```

Allowed role contracts:

- `selector`
  - accepts `DrainCtx` plus compile-time-rebound provider-bearing operands when required
  - returns union `SelectionResult`
- `run_item`
  - accepts `ItemCtx`, selected branch payload, and provider-bearing operands via compile-time extern rebinding
  - returns union `SelectedItemResult`
- `gap_drafter`
  - accepts `DrainCtx`, gap branch payload, and provider-bearing operands via compile-time extern rebinding
  - returns a record or union that the drain normalizer can convert into continue or blocked behavior

Provider/prompt rule:

- ordinary workflow boundaries still reject `Provider` and `Prompt`;
- stdlib `:providers` data is compile-time extern metadata, not a runtime `call` argument bundle;
- specialization must happen before `lowering.py` emits an ordinary `call` step.

### Union Workflow Boundary Projection

Widen workflow return signatures from record-only to:

```text
RecordTypeRef | UnionTypeRef
```

Implementation rule:

- the authored return type remains authoritative;
- `contracts.py` derives union boundary outputs from the same structured-result machinery already used by `provider-result` and `command-result`;
- `workflows.py` owns signature legality and flattened output metadata;
- `lowering.py` emits ordinary output refs plus explicit proof-aware handling for variant-only fields.

No new runtime union transport object is allowed.

## File Ownership

Primary modification targets:

- `orchestrator/workflow_lisp/__init__.py`
- `orchestrator/workflow_lisp/adapters/apply_resource_transition.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/contracts.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/drain_stdlib.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/macros.py`
- `orchestrator/workflow_lisp/resource.py`
- `orchestrator/workflow_lisp/resource_stdlib.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/workflows.py`
- `tests/test_workflow_lisp_resource_stdlib.py`
- `tests/test_workflow_lisp_drain_stdlib.py`
- `tests/test_workflow_lisp_workflows.py`
- `tests/test_workflow_lisp_structured_results.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_lisp_frontend_autonomous_drain_runtime.py`
- `tests/test_neurips_steered_backlog_runtime.py`
- the five Stage 6 valid/invalid fixture files under `tests/fixtures/workflow_lisp/`

Modify shared modules under `orchestrator/workflow/` only if a failing test proves the current shared seam cannot carry the bounded union-return projection without it. If that happens, keep the change minimal and directly tied to the failing selector/item/drain call path.

## Task 1: Lock The Stage 6 Contract Surface With Tests And Fixtures

**Files:**

- Modify: `tests/test_workflow_lisp_resource_stdlib.py`
- Modify: `tests/test_workflow_lisp_drain_stdlib.py`
- Modify: `tests/test_workflow_lisp_workflows.py`
- Modify: `tests/test_workflow_lisp_structured_results.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`
- Modify: `tests/test_neurips_steered_backlog_runtime.py`
- Modify: `tests/fixtures/workflow_lisp/valid/resource_stdlib_transition.orc`
- Modify: `tests/fixtures/workflow_lisp/valid/resource_stdlib_finalize_selected_item.orc`
- Modify: `tests/fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain.orc`
- Modify: `tests/fixtures/workflow_lisp/invalid/item_ctx_contract_invalid.orc`
- Modify: `tests/fixtures/workflow_lisp/invalid/drain_ctx_contract_invalid.orc`
- Modify: `tests/fixtures/workflow_lisp/invalid/resource_transition_uncertified_adapter.orc`
- Modify: `tests/fixtures/workflow_lisp/invalid/backlog_drain_workflow_ref_signature_invalid.orc`
- Modify: `tests/fixtures/workflow_lisp/invalid/backlog_drain_union_call_boundary_invalid.orc`

- [ ] **Step 1: Align the valid fixtures to the locked Stage 6 contracts**

Ensure the valid fixtures express:

- legal authored `ItemCtx` / `DrainCtx` contracts;
- one legal `resource-transition`;
- one legal `finalize-selected-item` using `:queue-transition` and `:roadmap`;
- one legal `backlog-drain` using the bounded workflow-ref roles.

- [ ] **Step 2: Align the invalid fixtures to exactly the bounded failure cases**

Keep the invalid fixtures focused on:

- invalid `ItemCtx` contract;
- invalid `DrainCtx` contract;
- uncertified `resource-transition`;
- workflow-ref role/signature mismatch;
- illegal union workflow boundary or call-site projection.

- [ ] **Step 3: Add or tighten failing tests before implementation changes**

Cover:

- context-contract acceptance and rejection;
- elaboration of the three Stage 6 forms;
- workflow-ref resolution and role validation;
- union workflow return acceptance and rejection;
- lowering shape for adapter-backed resource movement and `repeat_until` drain lowering;
- runtime smoke expectations for autonomous drain and NeurIPS steered backlog flows.

- [ ] **Step 4: Run collection for the dedicated Stage 6 test modules**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_resource_stdlib.py tests/test_workflow_lisp_drain_stdlib.py -q
```

Expected: collection succeeds with no import or syntax failures.

## Task 2: Complete Context Models, Workflow-Ref Planning, And Workflow Return Boundaries

**Files:**

- Modify: `orchestrator/workflow_lisp/resource.py`
- Modify: `orchestrator/workflow_lisp/contracts.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/diagnostics.py`
- Modify: `tests/test_workflow_lisp_workflows.py`
- Modify: `tests/test_workflow_lisp_structured_results.py`
- Modify: `tests/test_workflow_lisp_resource_stdlib.py`
- Modify: `tests/test_workflow_lisp_drain_stdlib.py`

- [ ] **Step 1: Finish the frontend-local resource/drain data models**

In `resource.py`, make the Stage 6 planning and layout types explicit and deterministic:

- `ItemLayout`
- `DrainLayout`
- `WorkflowRefAuthoritySource`
- `WorkflowRefEnvironment`
- `WorkflowRefRequirement`
- `ResolvedWorkflowRef`
- `WorkflowExternRebindingPlan`
- `WorkflowRefCallPlan`
- `DrainLoopPlan`
- `DrainAccumulator`

- [ ] **Step 2: Widen workflow return signatures to bounded union support**

Allow `WorkflowSignature.return_type_ref` to be `RecordTypeRef | UnionTypeRef`, while keeping ordinary parameter legality unchanged and continuing to reject `Provider` / `Prompt` at normal workflow boundaries.

- [ ] **Step 3: Reuse structured-result contract machinery for union workflow returns**

Implement the boundary projection in `contracts.py` and consume it from `workflows.py` / `compiler.py` instead of introducing a second transport or parallel schema derivation path.

- [ ] **Step 4: Build the compile-time-only workflow-ref environment**

Support resolution only from:

- same-file workflows;
- compiler-registered imported bundles.

Reject unknown names, ambiguous authority sources, role/signature mismatches, and provider/prompt extern requirements that cannot be rebound exactly.

- [ ] **Step 5: Add focused diagnostics for the bounded failure modes**

Use stable frontend codes for:

- `workflow_ref_unknown`
- `workflow_ref_signature_invalid`
- `workflow_ref_return_type_invalid`
- `workflow_union_boundary_invalid`
- `item_context_invalid`
- `drain_context_invalid`

## Task 3: Finish Stage 6 Expression Elaboration And Typechecking

**Files:**

- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/resource_stdlib.py`
- Modify: `orchestrator/workflow_lisp/drain_stdlib.py`
- Modify: `orchestrator/workflow_lisp/diagnostics.py`
- Modify: `orchestrator/workflow_lisp/macros.py`
- Modify: `tests/test_workflow_lisp_resource_stdlib.py`
- Modify: `tests/test_workflow_lisp_drain_stdlib.py`

- [ ] **Step 1: Make the Stage 6 forms first-class expression nodes**

Ensure `expressions.py` supports bounded AST/elaboration coverage for:

- `ResourceTransitionExpr`
- `FinalizeSelectedItemExpr`
- `BacklogDrainExpr`

Preserve spans, expansion provenance, and focused early operand validation.

- [ ] **Step 2: Typecheck `resource-transition` against the certified-adapter contract**

Require:

- `:ctx` resolves to a supported resource scope owned by this slice;
- `:ledger` is a relpath under `state`;
- `:from` and `:to` are compatible locations;
- the return type is exactly `ResourceTransitionResult`;
- the active binding is the certified `apply_resource_transition` adapter.

- [ ] **Step 3: Typecheck `finalize-selected-item` against the richer Stage 6 signature**

Require:

- `:queue-transition` resolves to `ResourceTransitionResult`;
- `:plan` and `:implementation` match the existing Stage 5 phase stdlib result shapes;
- the form returns `SelectedItemResult`;
- any terminal move still routes through the certified adapter boundary.

- [ ] **Step 4: Typecheck `backlog-drain` against the bounded drain-role contracts**

Require:

- `:ctx` resolves to `DrainCtx`;
- `:selector`, `:run-item`, and `:gap-drafter` resolve through the bounded workflow-ref environment;
- `:max-iterations` is `Int`;
- the overall form type is `DrainResult`;
- variant-only field access still requires proof through `match`.

- [ ] **Step 5: Re-run focused Stage 6 unit tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_resource_stdlib.py -q
python -m pytest tests/test_workflow_lisp_drain_stdlib.py -q
python -m pytest tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py -q
```

Expected: remaining failures, if any, are narrowed to lowering/runtime integration rather than elaboration or typechecking gaps.

## Task 4: Finish Certified Adapter Registration And Lowering

**Files:**

- Modify: `orchestrator/workflow_lisp/adapters/apply_resource_transition.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `orchestrator/workflow_lisp/resource.py`
- Modify: `orchestrator/workflow_lisp/resource_stdlib.py`
- Modify: `orchestrator/workflow_lisp/drain_stdlib.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_resource_stdlib.py`
- Modify: `tests/test_workflow_lisp_drain_stdlib.py`

- [ ] **Step 1: Keep adapter registration on the existing compiler augmentation path**

Extend `compile_stage3_module(...)` so `apply_resource_transition` is registered only when Stage 6 surfaces need it, with stable command, typed output, fixture metadata, declared effects, declared state writes, and source-map ownership matching the command adapter contract.

- [ ] **Step 2: Make the adapter backend deterministic and self-validating**

`adapters/apply_resource_transition.py` must:

- validate path safety;
- perform the resource move or fail with one stable hard error code;
- update the ledger or fail with one stable hard error code;
- emit exactly one `ResourceTransitionResult` bundle;
- avoid inline shell delegation or nested semantic wrappers.

- [ ] **Step 3: Lower `resource-transition` only through the certified adapter**

Emit:

- one generated command step;
- one authoritative structured output contract;
- source-map entries back to the originating stdlib form.

- [ ] **Step 4: Lower `finalize-selected-item` as typed fan-in**

Emit:

- explicit match/projection logic over selected outcome, roadmap, plan, and implementation;
- zero or one terminal `resource-transition`;
- authoritative `SelectedItemResult` publication;
- summary publication through the existing shared surfaces.

- [ ] **Step 5: Lower `backlog-drain` through one bounded `repeat_until` plan**

Emit:

- one explicit typed accumulator;
- selector / run-item / gap-drafter call plans;
- compile-time extern rebinding for provider-bearing callees;
- post-loop normalization into authored `DrainResult`;
- proof-aware references for variant-only downstream reads.

## Task 5: Run The Ordered Verification Suite And Record Evidence

**Files:**

- Modify: implementation files only as required by failures proven by the commands below

- [ ] **Step 1: Run the exact authoritative command list in order**

Run exactly:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_resource_stdlib.py tests/test_workflow_lisp_drain_stdlib.py -q
python -m pytest tests/test_workflow_lisp_resource_stdlib.py -q
python -m pytest tests/test_workflow_lisp_drain_stdlib.py -q
python -m pytest tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py -q
python -m pytest tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_procedures.py -q
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q
python -m pytest tests/test_neurips_steered_backlog_runtime.py -q
```

Expected: all seven commands pass in this order with no weakened selectors and no skipped runtime smoke replacement.

- [ ] **Step 2: If a command fails, fix only the proven Stage 6 cause and rerun from that command onward**

Rules:

- do not replace the authoritative command list with narrower final verification;
- do not relax assertions just to make the suite pass;
- do not widen scope beyond the bounded Stage 6 slice unless a failing shared-seam test proves it is necessary.

- [ ] **Step 3: Record completion evidence**

The implementation handoff must state:

- which files changed;
- which of the seven authoritative commands were run and passed;
- whether both runtime smoke modules passed;
- any residual risk that remains explicitly out of scope for this tranche.

## Acceptance Conditions

The slice is complete only when all of the following are true:

- `ItemCtx` and `DrainCtx` compile only when their relpath roles satisfy the deterministic layout contract for this slice.
- `resource-transition` lowers only through `apply_resource_transition`.
- `finalize-selected-item` uses typed lowering and authoritative structured outcome publication instead of handwritten selected-item fan-in.
- `backlog-drain` lowers through a bounded compiler-owned `repeat_until` substrate with explicit typed accumulator state.
- workflow refs remain compile-time-only and are legal only in the selected stdlib operand positions.
- provider/prompt-bearing workflow refs compile only through exact compile-time extern rebinding and never widen ordinary workflow-boundary transport.
- union-returning selector/item/drain workflows cross `call` through generated structured-result outputs and proof-aware field access, without a second runtime type transport.
- shared validation still sees only ordinary supported workflow surfaces.
- no runtime-native queue/resource effect is introduced.
- the seven-command verification suite above passes exactly as written.
