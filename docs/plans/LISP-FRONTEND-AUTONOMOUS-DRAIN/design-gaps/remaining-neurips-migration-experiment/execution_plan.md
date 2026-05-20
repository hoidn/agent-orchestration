# Remaining NeurIPS Migration Experiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the bounded Stage 7 Workflow Lisp frontend slice by translating the remaining NeurIPS composition surface (`run-selected-item`, top-level `backlog-drain`, and the real plan-gate `resume-or-start` integration), then emit a measured recommendation report that can conclude continue, revise, or stop.

**Architecture:** Keep all authoring-time ownership in `orchestrator/workflow_lisp/` and continue lowering through the existing read -> syntax -> macro expansion -> definitions/procedures/workflows -> typecheck -> lowering -> shared-validation seam. Reuse the Stage 4 implementation-attempt translation, Stage 5 phase stdlib, and Stage 6 resource/drain stdlib exactly as the generic substrate; the only Stage 7 widening is the narrow `resume-or-start :start` union-returning workflow `call` shape when it matches the declared `:returns` contract and lowers through the existing structured-result workflow-call path.

**Tech Stack:** Python 3, `orchestrator.workflow_lisp` compiler/typecheck/lowering modules, shared `orchestrator.workflow` validation/runtime, imported workflow bundles, `.orc` fixtures under `tests/fixtures/workflow_lisp/`, pytest, and the checked-in NeurIPS YAML/v2.14 workflows used as metrics and equivalence baselines.

---

## Fixed Inputs

Treat these files as authoritative for this slice:

- `docs/index.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
- `docs/steering.md`
  - empty in this checkout; it does not broaden scope
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`
  - currently `{"ledger_version":1,"events":[]}`; do not infer prior Stage 7 completion
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/6/design-gap-architect/work_item_context.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/6/design-gap-architect/check_commands.json`

Stage 7 design sections already resolved by those inputs:

- full spec: Sections 21, 28, 30, 31, 89, 90, 91, 96, 98, 105
- MVP spec: Sections 13, 14, 16

## Current Checkout Facts

These facts are already established and should not be rediscovered during implementation:

- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/6/design-gap-work-item/plan-phase/plan_path.txt` already points at `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/execution_plan.md`.
- The execution-plan target did not exist before this plan was written.
- The Stage 7 test modules do not exist yet and must be created:
  - `tests/test_workflow_lisp_stage7_translation.py`
  - `tests/test_workflow_lisp_stage7_metrics.py`
- The Stage 7 `.orc` fixtures also do not exist yet and must be created:
  - `tests/fixtures/workflow_lisp/valid/neurips_plan_gate_resume.orc`
  - `tests/fixtures/workflow_lisp/valid/neurips_selected_item.orc`
  - `tests/fixtures/workflow_lisp/valid/neurips_remaining_drain.orc`
  - `tests/fixtures/workflow_lisp/invalid/neurips_selected_item_signature_invalid.orc`
  - `tests/fixtures/workflow_lisp/invalid/neurips_remaining_drain_ref_invalid.orc`
  - `tests/fixtures/workflow_lisp/invalid/neurips_plan_gate_resume_contract_invalid.orc`
- Existing Stage 5 and Stage 6 tests and fixtures already exist and must be treated as regression surfaces, not rewritten from scratch:
  - `tests/test_workflow_lisp_phase_stdlib.py`
  - `tests/test_workflow_lisp_resource_stdlib.py`
  - `tests/test_workflow_lisp_drain_stdlib.py`
  - `tests/fixtures/workflow_lisp/valid/phase_stdlib_resume_or_start.orc`
  - `tests/fixtures/workflow_lisp/valid/resource_stdlib_finalize_selected_item.orc`
  - `tests/fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain.orc`
- Existing runtime smoke modules already exist and should be extended rather than replaced:
  - `tests/test_lisp_frontend_autonomous_drain_runtime.py`
  - `tests/test_neurips_steered_backlog_runtime.py`
- The current narrow blocker is real and already present in code:
  - `orchestrator/workflow_lisp/typecheck.py` rejects a union-returning workflow `call` inside `resume-or-start :start`.
  - `orchestrator/workflow_lisp/lowering.py` only knows how to recover the canonical bundle path for `command-result`, `run-provider-phase`, `produce-one-of`, and `provider-result` resume starts.
- The Stage 6 drain boundary is already enforced and must remain unchanged:
  - `orchestrator/workflow_lisp/typecheck.py` requires `run-item` workflow refs to accept exactly `(ItemCtx, SELECTED.selection)` and return a union.
  - `orchestrator/workflow_lisp/lowering.py` already specializes provider/prompt transport through `backlog-drain :providers`.

## Hard Scope Limits

Implement only this bounded Stage 7 slice:

- translate the selected-item composition workflow centered on `run-selected-item`;
- translate the top-level drain wrapper centered on `backlog-drain`;
- admit the real plan-gate `resume-or-start` fresh branch when that branch is a union-returning workflow `call` matching the declared `:returns` type exactly;
- add Stage 7 metrics counting and recommendation-report generation against the checked-in YAML/v2.7 and v2.14 baselines;
- add compile/typecheck/lowering/shared-validation coverage plus runtime smoke coverage for the selected-item and drain experiment.

Explicitly out of scope:

- new generic macro, procedure, module/import/export, or debug-YAML work;
- redesign of Stage 5 `resume-or-start`, Stage 6 `resource-transition`, `finalize-selected-item`, or `backlog-drain`;
- widening `run-selected-item` to accept a third providers parameter;
- moving provider/prompt transport onto ordinary workflow-call parameters;
- runtime-native promotion of reusable-state validation or resource transitions;
- translating every imported NeurIPS callee into `.orc`;
- hiding remaining YAML-backed dependencies behind new wrapper scripts.

## Locked Contracts

These contracts are already decided and must stay fixed:

- `run-selected-item` remains the Stage 6 `run-item` role target:
  - signature: `((item-ctx ItemCtx) (selection SelectionPayload)) -> SelectedItemResult`
- `backlog-drain :providers` remains the only provider/prompt transport surface for selector, run-item, and gap-drafter role targets and any imported workflows they specialize.
- Ordinary workflow boundaries still reject `Provider` and `Prompt`.
- `resume-or-start` is the only approved reuse gate for the plan branch.
- The only new legal `resume-or-start :start` shape is:
  - expression kind: ordinary workflow `call`
  - workflow return type: union
  - enclosing `resume-or-start :returns`: that exact same union type
  - transport: the existing structured-result workflow-call boundary
- Shared-validation and runtime behavior stay authoritative; no new runtime transport object may be introduced for union workflow returns.
- Remaining imported YAML bundles are allowed only as explicit migration debt and must be counted in the Stage 7 recommendation report.

## Baselines And Deliverables

Metrics and equivalence must compare against these existing authored baselines:

- `workflows/library/neurips_selected_backlog_item.yaml`
- `workflows/library/neurips_selected_backlog_item.v214.yaml`
- `workflows/examples/neurips_steered_backlog_drain.yaml`
- `workflows/examples/neurips_steered_backlog_drain.legacy.yaml`

Stage 7 must leave these deliverables in place:

- compiled/frontend test coverage for the three new `.orc` fixtures;
- runtime smoke coverage for fresh-plan reuse, approved-plan reuse, continued drain iteration, and deterministic gap-draft or blocked routing;
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md`.

## File Ownership

Primary implementation targets:

- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/workflows.py`
- `tests/fixtures/workflow_lisp/valid/neurips_plan_gate_resume.orc`
- `tests/fixtures/workflow_lisp/valid/neurips_selected_item.orc`
- `tests/fixtures/workflow_lisp/valid/neurips_remaining_drain.orc`
- `tests/fixtures/workflow_lisp/invalid/neurips_selected_item_signature_invalid.orc`
- `tests/fixtures/workflow_lisp/invalid/neurips_remaining_drain_ref_invalid.orc`
- `tests/fixtures/workflow_lisp/invalid/neurips_plan_gate_resume_contract_invalid.orc`
- `tests/test_workflow_lisp_stage7_translation.py`
- `tests/test_workflow_lisp_stage7_metrics.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_resource_stdlib.py`
- `tests/test_workflow_lisp_drain_stdlib.py`
- `tests/test_lisp_frontend_autonomous_drain_runtime.py`
- `tests/test_neurips_steered_backlog_runtime.py`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md`

Keep these files unchanged unless a failing Stage 7 test proves a direct need:

- `orchestrator/workflow_lisp/phase_stdlib.py`
- `orchestrator/workflow_lisp/resource_stdlib.py`
- shared runtime/validation modules under `orchestrator/workflow/`

## Task 1: Add The Stage 7 Fixtures And Test Skeletons

**Files:**

- Create: `tests/fixtures/workflow_lisp/valid/neurips_plan_gate_resume.orc`
- Create: `tests/fixtures/workflow_lisp/valid/neurips_selected_item.orc`
- Create: `tests/fixtures/workflow_lisp/valid/neurips_remaining_drain.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/neurips_selected_item_signature_invalid.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/neurips_remaining_drain_ref_invalid.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/neurips_plan_gate_resume_contract_invalid.orc`
- Create: `tests/test_workflow_lisp_stage7_translation.py`
- Create: `tests/test_workflow_lisp_stage7_metrics.py`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`
- Modify: `tests/test_neurips_steered_backlog_runtime.py`

- [ ] **Step 1: Write the three valid Stage 7 fixtures**

Author fixtures that mirror the approved composition surface, not toy wrappers:

- `neurips_plan_gate_resume.orc`
  - models the real `resume-or-start` plan gate with a union-returning workflow `call` in `:start`
  - declares a `PlanGateResult` union and a small surface record used by assertions
- `neurips_selected_item.orc`
  - models `run-selected-item` with:
    - Stage 6 `resource-transition`
    - ordinary workflow `call` to roadmap sync
    - `resume-or-start` around the plan workflow call
    - ordinary workflow `call` to the already translated implementation workflow or an imported typed equivalent
    - Stage 6 `finalize-selected-item`
- `neurips_remaining_drain.orc`
  - models a top-level `backlog-drain` wrapper with explicit `DrainCtx`, provider extern rebinding, and typed workflow refs

- [ ] **Step 2: Write the invalid fixtures for the locked failure modes**

Encode these negative contracts:

- `neurips_selected_item_signature_invalid.orc`
  - illegal three-parameter `run-selected-item` or other forbidden `run-item` role widening
- `neurips_remaining_drain_ref_invalid.orc`
  - illegal workflow ref/imported bundle shape for selector, run-item, or gap-drafter
- `neurips_plan_gate_resume_contract_invalid.orc`
  - illegal `resume-or-start :start` union call whose return type does not exactly match the declared `:returns`

- [ ] **Step 3: Add failing translation tests**

Create `tests/test_workflow_lisp_stage7_translation.py` with focused tests that currently fail because the union-call `resume-or-start` path is still blocked. The module should cover:

- compile/typecheck success for `neurips_plan_gate_resume.orc`
- compile/typecheck/lowering/shared-validation success for `neurips_selected_item.orc`
- compile/typecheck/lowering/shared-validation success for `neurips_remaining_drain.orc`
- rejection of the three invalid fixtures
- explicit assertion that the `run-item` role remains exactly two parameters

- [ ] **Step 4: Add failing metrics tests**

Create `tests/test_workflow_lisp_stage7_metrics.py` with deterministic expectations for:

- authored LOC comparison versus the four YAML baselines
- semantic LOC for the translated outer workflows
- manual state-path count
- pointer-file count
- manual pointer/materialization surface count
- manual candidate-path count
- manually paired variant-check / variant-proof boilerplate count
- markdown/text extractor count
- shell/Python glue command or helper-script count
- string-status/gate-pattern count
- remaining imported YAML dependency count
- behavioral-equivalence evidence status for the Stage 7 runtime/translation suite
- recommendation outcome generation into `migration_experiment_recommendation_report.md`

Require the metrics tests to record every authority-defined surface explicitly, even when the expected Stage 7 value is zero.

These tests should fail initially because the report generator and counts do not exist yet.

- [ ] **Step 5: Extend the runtime smoke modules with Stage 7 selectors**

Add targeted smoke tests that the later commands in `check_commands.json` will exercise:

- `tests/test_lisp_frontend_autonomous_drain_runtime.py`
  - `test_selected_item_fresh_plan`
  - `test_selected_item_reuses_approved_plan`
- `tests/test_neurips_steered_backlog_runtime.py`
  - `test_drain_continues_to_next_iteration`
  - `test_drain_gap_draft`
  - `test_drain_blocked`

- [ ] **Step 6: Run collect-only to lock the new module names and selectors**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_stage7_translation.py tests/test_workflow_lisp_stage7_metrics.py tests/test_lisp_frontend_autonomous_drain_runtime.py tests/test_neurips_steered_backlog_runtime.py -q
```

Expected:

- the two new Stage 7 modules collect successfully;
- the existing runtime modules collect with the new selectors visible;
- no import or syntax failures.

## Task 2: Admit The Narrow `resume-or-start` Union Workflow Call

**Files:**

- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `tests/test_workflow_lisp_stage7_translation.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/fixtures/workflow_lisp/valid/phase_stdlib_resume_or_start.orc`
- Modify: `tests/fixtures/workflow_lisp/valid/neurips_plan_gate_resume.orc`
- Modify: `tests/fixtures/workflow_lisp/invalid/neurips_plan_gate_resume_contract_invalid.orc`

- [ ] **Step 1: Tighten the failing tests to the exact new admissible shape**

Before implementation, make sure the tests explicitly assert:

- only workflow `call` is newly allowed in `resume-or-start :start`;
- the called workflow must return the exact union named in `:returns`;
- non-matching unions still fail;
- non-call union-producing expressions remain unsupported.

- [ ] **Step 2: Remove the blanket typecheck rejection and replace it with a shape check**

In `orchestrator/workflow_lisp/typecheck.py`, replace the current unconditional rejection of union-returning workflow calls inside `ResumeOrStartExpr` with logic that:

- resolves the callee signature through the existing workflow catalog;
- allows the call only when `start_signature.return_type_ref == declared_return_type`;
- preserves the existing error code `resume_or_start_contract_invalid` for mismatches;
- leaves all other `resume-or-start` checks intact.

- [ ] **Step 3: Extend lowering to recover the canonical bundle path for workflow-call starts**

In `orchestrator/workflow_lisp/lowering.py`, extend `_resume_start_bundle_ref(...)` so a legal Stage 7 workflow `call` can point `resume-or-start` at the canonical structured-result bundle produced by the existing workflow-call lowering path. Do not invent a new output transport; reuse the same bundle/projection naming already used for ordinary workflow calls and resumed canonical-bundle loading.

- [ ] **Step 4: Keep workflow boundary handling on the existing structured-result path**

Use `orchestrator/workflow_lisp/workflows.py` only for the minimal signature metadata or helper changes needed by the new lowering path. Do not widen ordinary workflow-boundary legality beyond the existing record-or-union support.

- [ ] **Step 5: Run the narrow regression commands**

Run:

```bash
python -m pytest tests/test_workflow_lisp_stage7_translation.py -k 'neurips_plan_gate_resume' -q
python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k 'resume_or_start or union_start_workflow_call' -q
```

Expected:

- the valid Stage 7 plan-gate fixture passes compile/typecheck/lowering assertions;
- the invalid contract fixture still fails with `resume_or_start_contract_invalid`;
- existing Stage 5 resume tests still pass.

## Task 3: Implement The Selected-Item Translation Surface

**Files:**

- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `tests/fixtures/workflow_lisp/valid/neurips_selected_item.orc`
- Modify: `tests/fixtures/workflow_lisp/invalid/neurips_selected_item_signature_invalid.orc`
- Modify: `tests/test_workflow_lisp_stage7_translation.py`
- Modify: `tests/test_workflow_lisp_resource_stdlib.py`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Finalize the selected-item fixture around the approved composition order**

Make `neurips_selected_item.orc` express, in order:

1. selected-item resolution from typed selector output;
2. Stage 6 queue transition through `resource-transition`;
3. roadmap sync through ordinary workflow `call`;
4. plan gate through `resume-or-start`;
5. implementation through ordinary workflow `call`;
6. selected-item finalization through `finalize-selected-item`.

Keep all phase outputs typed and explicit. Do not parse reports or read pointer files for semantics.

- [ ] **Step 2: Wire the imported workflow environment needed by the selected-item fixture**

In `orchestrator/workflow_lisp/compiler.py`, register the imported bundles or same-file workflow catalog entries needed by the selected-item Stage 7 fixture and runtime smoke path. Keep provider/prompt extern specialization on the existing compile-time transport.

- [ ] **Step 3: Make lowering preserve typed fan-in rather than ambient state**

In `orchestrator/workflow_lisp/lowering.py`, ensure the selected-item lowering feeds explicit typed inputs into `finalize-selected-item` and uses ordinary call projections for roadmap, plan, and implementation results. Any required change here must be about Stage 7 composition, not about redefining Stage 6 stdlib behavior.

- [ ] **Step 4: Protect the locked role signature**

Use the invalid fixture and translation test to keep `run-selected-item` at exactly two parameters. If the concrete selected-item fixture reveals pressure to add provider parameters, resolve it through extern rebinding instead of widening the signature.

- [ ] **Step 5: Run selected-item translation and runtime checks**

Run:

```bash
python -m pytest tests/test_workflow_lisp_stage7_translation.py -k 'neurips_selected_item or run_item_boundary' -q
python -m pytest tests/test_workflow_lisp_resource_stdlib.py -k 'finalize_selected_item' -q
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k 'selected_item_fresh_plan or selected_item_reuses_approved_plan' -q
```

Expected:

- the selected-item fixture passes compile/typecheck/lowering/shared-validation;
- the invalid signature fixture still fails;
- the runtime harness proves both a fresh plan path and an approved-plan reuse path.

## Task 4: Implement The Top-Level Drain Translation Surface

**Files:**

- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `tests/fixtures/workflow_lisp/valid/neurips_remaining_drain.orc`
- Modify: `tests/fixtures/workflow_lisp/invalid/neurips_remaining_drain_ref_invalid.orc`
- Modify: `tests/test_workflow_lisp_stage7_translation.py`
- Modify: `tests/test_workflow_lisp_drain_stdlib.py`
- Modify: `tests/test_neurips_steered_backlog_runtime.py`

- [ ] **Step 1: Finalize the top-level drain fixture as one `backlog-drain` wrapper**

Make `neurips_remaining_drain.orc` stay small and declarative:

- inputs: `DrainCtx`, typed providers, `max-iterations`
- body: one `backlog-drain` form
- role targets: selector, selected-item, gap-drafter
- provider transport: `:providers` only

- [ ] **Step 2: Reuse the Stage 6 workflow-ref environment unchanged**

In `orchestrator/workflow_lisp/workflows.py` and `lowering.py`, keep:

- selector role contract unchanged;
- run-item role contract unchanged;
- gap-drafter role contract unchanged;
- imported-bundle or same-file resolution on the existing Stage 6 workflow-ref surface.

The only acceptable changes here are narrow fixes required for the real Stage 7 fixture or provider extern rebinding through `:providers`.

- [ ] **Step 3: Prove provider/prompt transport stays off ordinary workflow parameters**

Use the Stage 7 drain fixture and drain stdlib tests to verify that provider-bearing targets are specialized before lowering emits ordinary `call` steps. Do not add `Provider` or `Prompt` to workflow boundary types.

- [ ] **Step 4: Run drain translation and runtime checks**

Run:

```bash
python -m pytest tests/test_workflow_lisp_stage7_translation.py -k 'neurips_remaining_drain' -q
python -m pytest tests/test_workflow_lisp_drain_stdlib.py -k 'backlog_drain or run_item_contract or providers_rebinding' -q
python -m pytest tests/test_neurips_steered_backlog_runtime.py -k 'drain_continues_to_next_iteration or drain_gap_draft or drain_blocked' -q
```

Expected:

- the valid drain fixture passes compile/typecheck/lowering/shared-validation;
- the invalid drain ref fixture still fails;
- runtime smoke proves continued iteration plus deterministic gap-draft or blocked termination.

## Task 5: Implement Metrics And Recommendation Output

**Files:**

- Modify: `tests/test_workflow_lisp_stage7_metrics.py`
- Create: `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md`
- Modify: `tests/test_workflow_lisp_stage7_translation.py`

- [ ] **Step 1: Implement deterministic Stage 7 metric counting in the test/support path**

Count, from checked-in sources rather than prose judgment:

- authored LOC for the three `.orc` fixtures;
- authored LOC for the four YAML/v2.7-v2.14 baselines;
- semantic LOC for the translated selected-item and drain surfaces;
- manual state-path occurrences;
- pointer-file occurrences;
- direct manual pointer/materialization surface;
- manual candidate-path occurrences;
- manually paired variant-check / variant-proof boilerplate occurrences;
- markdown/text extractor occurrences;
- shell/Python glue-command and helper-script occurrences kept in the translated surface;
- string-status/manual gate patterns;
- remaining YAML-backed imported workflow dependencies.

Treat zero as a measured result, not as omitted data. The support code or test fixtures should emit a stable table/dict that records every metric named by MVP Section 13 and full-spec Sections 98 and 105.

- [ ] **Step 2: Generate the recommendation report**

Write `migration_experiment_recommendation_report.md` with only measured evidence and a final recommendation:

- include one explicit metric row per authority-defined surface, including zeros for absent pointer files, extractors, glue commands, helper scripts, or variant-proof boilerplate;
- include behavioral-equivalence status from the Stage 7 translation/runtime suite alongside the static counts;
- `continue` only if the translated outer workflows materially reduce brittle authoring surfaces across the recorded metric set and preserve behavior;
- `revise` if behavior is preserved but key YAML-shaped seams remain in the recorded counts or dependency inventory;
- `stop` if the translated surface stays YAML-shaped, increases brittle-surface counts, or fails behavioral equivalence.

The report must explicitly name any remaining imported YAML-backed dependencies as migration debt.

- [ ] **Step 3: Run the metrics suite**

Run:

```bash
python -m pytest tests/test_workflow_lisp_stage7_metrics.py -q
```

Expected:

- counts are deterministic against the checked-in baselines;
- the recommendation report is emitted at the expected path;
- the recommendation outcome is derived from measured evidence rather than free-form prose.

## Final Verification

Run the exact required Stage 7 suite, in order, from the repo root:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_stage7_translation.py tests/test_workflow_lisp_stage7_metrics.py tests/test_lisp_frontend_autonomous_drain_runtime.py tests/test_neurips_steered_backlog_runtime.py -q
python -m pytest tests/test_workflow_lisp_stage7_translation.py -k 'neurips_plan_gate_resume or neurips_selected_item or neurips_remaining_drain or run_item_boundary' -q
python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k 'resume_or_start or union_start_workflow_call' -q
python -m pytest tests/test_workflow_lisp_resource_stdlib.py -k 'finalize_selected_item' -q
python -m pytest tests/test_workflow_lisp_drain_stdlib.py -k 'backlog_drain or run_item_contract or providers_rebinding' -q
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k 'selected_item_fresh_plan or selected_item_reuses_approved_plan' -q
python -m pytest tests/test_neurips_steered_backlog_runtime.py -k 'drain_continues_to_next_iteration or drain_gap_draft or drain_blocked' -q
python -m pytest tests/test_workflow_lisp_stage7_metrics.py -q
```

Expected final state:

- all eight commands pass;
- the selected-item and drain fixtures compile and validate through the shared runtime seam;
- runtime smoke covers both plan reuse modes and drain termination routes;
- `migration_experiment_recommendation_report.md` exists and reflects measured evidence.

## Completion Notes

When implementation is done, record:

- the files actually changed;
- any remaining YAML-backed imported bundles;
- the recommendation outcome and the metrics that drove it;
- the exact command output from the required verification suite.
