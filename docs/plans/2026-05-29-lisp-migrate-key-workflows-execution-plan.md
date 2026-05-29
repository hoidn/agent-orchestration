# Design-Delta Prompt And API Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved design-delta boundary by keeping the autonomous Lisp frontend drain stable on full/MVP semantics while routing ProcRef and future design-delta drains through isolated target/baseline workflow and prompt variants.

**Architecture:** This plan executes the approved "copied design-delta variants" decision end-to-end. The autonomous full/MVP stack remains a pinned compatibility surface; the design-delta path owns target/baseline workflow APIs, prompt assets, and caller wiring; verification proves the two paths no longer share ambiguous semantics.

**Tech Stack:** YAML workflow DSL v2.14, Markdown prompt assets, Python loader/runtime tests, `python -m orchestrator` dry-run validation

---

## Scope

- Current implementation scope: the full approved design for `docs/backlog/active/LISP-PROC-REFS-PARTIAL-APPLICATION/2026-05-28-design-delta-prompt-api-boundary.md`.
- Primary authority: the consumed backlog/design item above.
- Additional scoped instructions: `docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/work_instructions.md`.
- This plan must fully implement the selected approach `2) keep the original full/MVP stack stable and create copied design-delta workflow/prompt variants`.
- The work includes workflow API cleanup, prompt-surface isolation, focused tests, discoverability updates, and at least one dry-run smoke check of `workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml`.
- The work does not include ProcRef language implementation, runtime semantic changes, `.orc` migration, removal of YAML workflows, or unrelated Lisp frontend refactors.
- Follow-up work: none. The approved design is already intentionally bounded; all material requirements belong in the current slice.

## Implementation Architecture

This work needs an Implementation Architecture section because correctness depends on a stable caller/API boundary between the autonomous full/MVP stack and the design-delta target/baseline stack, plus prompt-surface ownership that must not drift across those consumers.

### Unit 1: Caller And Workflow-API Boundary

- Owns the caller-visible workflow inputs, imports, and library-routing split between:
- `workflows/examples/lisp_frontend_autonomous_drain.yaml`
- `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- `workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml`
- `workflows/library/lisp_frontend_selector.v214.yaml`
- `workflows/library/lisp_frontend_design_delta_selector.v214.yaml`
- `workflows/library/lisp_frontend_design_gap_architect.v214.yaml`
- `workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml`
- `workflows/library/lisp_frontend_work_item.v214.yaml`
- `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml`
- `workflows/library/lisp_frontend_plan_phase.v214.yaml`
- `workflows/library/lisp_frontend_design_delta_plan_phase.v214.yaml`
- `workflows/library/lisp_frontend_implementation_phase.v214.yaml`
- `workflows/library/lisp_frontend_design_delta_implementation_phase.v214.yaml`
- Owns these stable interfaces:
- autonomous caller surface: `full_design_path`, `mvp_design_path`, and existing full/MVP artifact names
- design-delta caller surface: `target_design_path`, `baseline_design_path`, and target/baseline consumed-artifact names
- variant import routing from the ProcRef wrapper through the design-delta drain into the design-delta library stack
- Must not own prompt prose beyond selecting the correct prompt asset path.
- Must not change runtime scripts, output-bundle schemas, provider output contracts, or the autonomous stack's full/MVP API names.

### Unit 2: Prompt-Surface Isolation

- Owns the prompt files that express design-role semantics:
- `workflows/library/prompts/lisp_frontend_selector/select_next_work.md`
- `workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md`
- `workflows/library/prompts/lisp_frontend_design_gap_architect/*.md`
- `workflows/library/prompts/lisp_frontend_design_delta_design_gap_architect/*.md`
- `workflows/library/prompts/lisp_frontend_plan_phase/*.md`
- `workflows/library/prompts/lisp_frontend_design_delta_plan_phase/*.md`
- `workflows/library/prompts/lisp_frontend_implementation_phase/*.md`
- `workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/*.md`
- Owns these stable boundaries:
- autonomous prompts speak only full/MVP semantics
- design-delta prompts speak only target/baseline semantics
- selector safety rules remain equivalent across both paths
- shared prompt roots contain no ProcRef-specific IDs unless intentionally project-specific
- Must not own changes to workflow control flow, review-loop mechanics, or provider output formats.

### Unit 3: Verification And Discoverability

- Owns the durable proof and maintainer-facing description of the split:
- `tests/test_lisp_frontend_autonomous_drain_runtime.py`
- `workflows/README.md`
- Owns these stable contracts:
- loader/runtime tests prove import routing, prompt semantics, and absence of shared ProcRef leakage
- README text explains which stack future target/baseline drains should import and which stack remains the autonomous full/MVP path
- Must not own broader frontend backlog policy, historical design-gap docs, or unrelated workflow migration work.

### Dependency Direction

- Unit 1 comes first because Units 2 and 3 depend on the finalized caller/library boundary.
- Unit 2 depends on Unit 1 because prompt assets must match the selected workflow API names and owned variant routes.
- Unit 3 depends on Units 1 and 2 because tests and docs should describe the final split, not an intermediate mixed state.

### Compatibility And Migration Boundaries

- Keep the autonomous drain on the full/MVP naming model unless a different design explicitly approves generalization.
- Keep the design-delta path on the target/baseline naming model without wrapper reinterpretation.
- Preserve existing v2.14 validation, run-state paths, review-loop shapes, output-bundle contracts, and helper-script boundaries.
- Do not broaden this item into ProcRef language implementation, runtime transport changes, or `.orc` conversion.

### Sequencing Constraints

- Do not mix autonomous full/MVP API renames into the same implementation unit as design-delta isolation.
- Do not edit prompt wording before the owning workflow routes are pinned.
- Do not update docs or tests until the target/baseline versus full/MVP ownership split is explicit in files.

## Task Checklist

### Task 1: Pin The Caller And Library Variant Boundary

**Files:**

- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Modify: `workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml`
- Modify: `workflows/library/lisp_frontend_design_delta_selector.v214.yaml`
- Modify: `workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml`
- Modify: `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml`
- Modify: `workflows/library/lisp_frontend_design_delta_plan_phase.v214.yaml`
- Modify: `workflows/library/lisp_frontend_design_delta_implementation_phase.v214.yaml`
- Inspect only for pinned compatibility: `workflows/examples/lisp_frontend_autonomous_drain.yaml`
- Inspect only for pinned compatibility: `workflows/library/lisp_frontend_selector.v214.yaml`
- Inspect only for pinned compatibility: `workflows/library/lisp_frontend_design_gap_architect.v214.yaml`
- Inspect only for pinned compatibility: `workflows/library/lisp_frontend_work_item.v214.yaml`
- Inspect only for pinned compatibility: `workflows/library/lisp_frontend_plan_phase.v214.yaml`
- Inspect only for pinned compatibility: `workflows/library/lisp_frontend_implementation_phase.v214.yaml`

- [ ] Normalize the design-delta caller path so every design-delta workflow surface accepts and forwards `target_design_path` and `baseline_design_path` directly, with no comments or wrapper conventions needed to explain the mapping.
- [ ] Ensure the ProcRef wrapper calls the design-delta drain with its dedicated target, baseline, backlog, state, and artifact roots, while the autonomous drain continues to call only the full/MVP stack.
- [ ] Verify each design-delta library workflow imports only design-delta variants for selector, design-gap architect, work-item, plan, and implementation phases.
- [ ] Preserve all existing output bundles, run-state paths, consume surfaces, and helper-script boundaries; this task changes ownership and naming surfaces, not runtime mechanics.

**Blocking verification after Task 1:**

- [ ] `pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_lisp_frontend_workflows_load -q`
- [ ] `pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_design_delta_drain_uses_design_delta_library_variants -q`
- [ ] `pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_proc_ref_delta_drain_uses_proc_ref_backlog_root -q`

### Task 2: Isolate Prompt Semantics By Owned Prompt Surface

**Files:**

- Modify: `workflows/library/prompts/lisp_frontend_selector/select_next_work.md`
- Modify: `workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md`
- Create or modify: `workflows/library/prompts/lisp_frontend_design_delta_design_gap_architect/draft_implementation_architecture.md`
- Create or modify: `workflows/library/prompts/lisp_frontend_design_delta_design_gap_architect/review_implementation_architecture.md`
- Create or modify: `workflows/library/prompts/lisp_frontend_design_delta_design_gap_architect/revise_implementation_architecture.md`
- Create or modify: `workflows/library/prompts/lisp_frontend_design_delta_plan_phase/draft_plan.md`
- Create or modify: `workflows/library/prompts/lisp_frontend_design_delta_plan_phase/review_plan.md`
- Create or modify: `workflows/library/prompts/lisp_frontend_design_delta_plan_phase/revise_plan.md`
- Create or modify: `workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/implement_plan.md`
- Create or modify: `workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/review_implementation.md`
- Create or modify: `workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/fix_implementation.md`
- Inspect only for pinned compatibility: `workflows/library/prompts/lisp_frontend_design_gap_architect/*.md`
- Inspect only for pinned compatibility: `workflows/library/prompts/lisp_frontend_plan_phase/*.md`
- Inspect only for pinned compatibility: `workflows/library/prompts/lisp_frontend_implementation_phase/*.md`

- [ ] Start each design-delta prompt variant from the corresponding full/MVP prompt content and keep the delta limited to the approved semantic substitutions required by target/baseline ownership.
- [ ] Keep the autonomous prompts on full/MVP terminology and confirm they no longer inherit design-delta wording.
- [ ] Preserve selector safety rules, bounded-refactor guidance, durable-evidence requirements, and output-contract reminders across both prompt families.
- [ ] Remove any ProcRef-specific IDs or examples from shared prompt surfaces; if a project-specific example is still needed, keep it only on the design-delta-owned surface.

**Blocking verification after Task 2:**

- [ ] `pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_design_delta_selector_prompt_defines_target_and_baseline -q`
- [ ] `pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_proc_ref_path_prompts_use_target_and_baseline_roles -q`
- [ ] `pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_shared_autonomous_prompt_roots_keep_full_mvp_semantics -q`
- [ ] `pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_shared_prompt_roots_do_not_include_procref_specific_ids -q`

### Task 3: Lock The Regression Proof And Discoverability

**Files:**

- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`
- Modify: `workflows/README.md`

- [ ] Add or update focused tests that prove the routing split, the full/MVP versus target/baseline prompt ownership split, and the absence of ProcRef-specific leakage into shared prompt roots.
- [ ] Keep prompt tests at the contract-shape level rather than exact sentence fragments so future prose edits do not create brittle failures.
- [ ] Update `workflows/README.md` to tell future maintainers that target/baseline drains should reuse the design-delta variant stack while the autonomous full/MVP stack remains the stable original path.
- [ ] If test names are added or renamed in `tests/test_lisp_frontend_autonomous_drain_runtime.py`, collect them explicitly before running the module.

**Blocking verification after Task 3:**

- [ ] `pytest --collect-only tests/test_lisp_frontend_autonomous_drain_runtime.py -q`
- [ ] `pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "design_delta or proc_ref or shared_autonomous_prompt_roots or shared_prompt_roots or workflows_load" -q`

### Task 4: Run The End-To-End Workflow Validation

**Files:**

- No maintained source files; this task validates the changed workflow and prompt contracts.

- [ ] Run the required dry-run smoke check for the approved design target: `python -m orchestrator run workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml --dry-run`
- [ ] If the dry-run fails, fix only the boundary-contract issue that caused the failure; do not broaden into unrelated ProcRef language work or runtime redesign.
- [ ] Confirm the dry-run still exercises the design-delta target/baseline stack, not the autonomous full/MVP stack, by checking the imported workflow path and generated state/artifact roots.

**Supporting verification after Task 4:**

- [ ] `python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml --dry-run --input steering_path=docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/work_instructions.md --input target_design_path=docs/design/workflow_lisp_proc_refs_partial_application.md --input baseline_design_path=docs/design/workflow_lisp_frontend_specification.md --input backlog_root=docs/backlog/active/LISP-PROC-REFS-PARTIAL-APPLICATION --input progress_ledger_path=state/LISP-PROC-REFS-PARTIAL-APPLICATION/progress_ledger.json --input drain_state_root=state/LISP-PROC-REFS-PARTIAL-APPLICATION/drain --input run_state_target_path=state/LISP-PROC-REFS-PARTIAL-APPLICATION/drain/run_state.json --input drain_summary_target_path=artifacts/work/LISP-PROC-REFS-PARTIAL-APPLICATION/drain-summary.json --input artifact_work_root=artifacts/work/LISP-PROC-REFS-PARTIAL-APPLICATION --input artifact_checks_root=artifacts/checks/LISP-PROC-REFS-PARTIAL-APPLICATION --input artifact_review_root=artifacts/review/LISP-PROC-REFS-PARTIAL-APPLICATION --input architecture_index_root=docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/design-gaps`

## Explicit Non-Goals

- Do not generalize the autonomous stack to target/baseline terminology in this item.
- Do not change runtime semantics, review-loop mechanics, helper scripts, or v2.14 output-contract behavior.
- Do not implement ProcRef language features, migrate these workflows to `.orc`, or remove the YAML workflows.
- Do not add durable inventory or report artifacts beyond the docs/tests already required by the approved design.
