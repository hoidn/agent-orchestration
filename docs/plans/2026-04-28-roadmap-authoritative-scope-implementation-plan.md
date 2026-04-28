# Roadmap-Authoritative Scope Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Prevent a narrowed implementation slice from completing a broader major-project tranche unless roadmap revision has authorized the scope change.

**Architecture:** Add a deterministic selected-tranche scope boundary artifact, pass it through major-project plan and implementation phases, let implementation review escalate directly to roadmap revision, and run a completion guard before `APPROVE` becomes an item-level `APPROVED`. Keep semantic scope authority in roadmap revision; keep provider prompts local; keep final completion routing deterministic.

**Tech Stack:** Python workflow helper scripts, YAML DSL workflows, Codex provider prompts, pytest workflow regression tests.

---

## Files

- Create: `workflows/library/scripts/major_project_scope_boundary.py`
  - Owns scope-boundary generation and completion-guard checks.
- Modify: `workflows/library/scripts/select_major_project_tranche.py`
  - Adds `scope_boundary_path` to selected-tranche handoff.
- Modify: `workflows/library/scripts/major_project_tranche_phase_routes.py`
  - Runs the completion guard before final approval and routes scope mismatch to roadmap revision.
- Modify: `workflows/library/major_project_tranche_design_plan_impl_stack.yaml`
  - Accepts/publishes `scope_boundary_path`, materializes the boundary, and passes it to plan/implementation phases.
- Modify: `workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml`
  - Forwards `scope_boundary_path`.
- Modify: `workflows/library/major_project_tranche_plan_phase.yaml`
  - Consumes the scope boundary in draft/review/revise planning.
- Modify: `workflows/library/major_project_tranche_implementation_phase.yaml`
  - Consumes the scope boundary, accepts `ESCALATE_ROADMAP_REVISION`, and routes it terminally.
- Modify: `workflows/library/major_project_tranche_drain_iteration.yaml`
  - Publishes and forwards `scope_boundary_path`.
- Modify: `workflows/examples/major_project_tranche_design_plan_impl_stack_v2_call.yaml`
  - Publishes and forwards `scope_boundary_path` from the inline selector.
- Modify: `workflows/examples/major_project_tranche_continue_from_approved_design_v2_call.yaml`
  - Publishes and forwards `scope_boundary_path`.
- Modify: `workflows/library/prompts/major_project_stack/draft_plan.md`
  - Makes roadmap-scope authority explicit.
- Modify: `workflows/library/prompts/major_project_stack/review_plan.md`
  - Rejects local rechartering.
- Modify: `workflows/library/prompts/major_project_stack/review_implementation.md`
  - Adds direct roadmap escalation and approval boundary language.
- Modify: `workflows/library/prompts/major_project_stack/fix_implementation.md`
  - Forbids treating blocked-state honesty as completion.
- Modify: `workflows/README.md`
  - Documents the new boundary/guard behavior.
- Modify: `tests/test_major_project_workflows.py`
  - Adds workflow contract and runtime regression coverage.

## Task 1: Add Scope Boundary Helper

- [x] **Step 1: Write tests for helper behavior**

Add tests in `tests/test_major_project_workflows.py` that import the helper and verify:

- `write_scope_boundary()` derives a boundary from a selected manifest tranche.
- `check_completion()` returns `COMPLETE` for approved reports with no blocker language.
- `check_completion()` returns `SCOPE_MISMATCH` when an approved report says required work is deferred and no roadmap-authorized deferral exists.
- `check_completion()` returns `COMPLETE` when the boundary explicitly authorizes deferred work.

Run: `pytest tests/test_major_project_workflows.py -q -k 'scope_boundary or completion_guard'`

- [x] **Step 2: Implement helper**

Create `workflows/library/scripts/major_project_scope_boundary.py` with:

- `write_scope_boundary(...)`
- `check_completion(...)`
- CLI subcommands `write-boundary` and `check-completion`

The first guard version should be conservative: approved reports that mention unresolved blocked/deferred/unimplemented tranche work without roadmap authorization produce `SCOPE_MISMATCH`.

- [x] **Step 3: Verify helper tests**

Run: `pytest tests/test_major_project_workflows.py -q -k 'scope_boundary or completion_guard'`

Expected: helper tests pass.

## Task 2: Thread Scope Boundary Through Workflows

- [x] **Step 1: Update selector handoffs**

Add `scope_boundary_path` to `select_major_project_tranche.py` payloads and to the output bundles in:

- `workflows/library/major_project_tranche_drain_iteration.yaml`
- `workflows/examples/major_project_tranche_continue_from_approved_design_v2_call.yaml`
- `workflows/examples/major_project_tranche_design_plan_impl_stack_v2_call.yaml`

- [x] **Step 2: Update tranche stack inputs**

Add `scope_boundary_path` to:

- `major_project_tranche_design_plan_impl_stack.yaml`
- `major_project_tranche_plan_impl_from_approved_design_stack.yaml`

In `InitializeItemState`, call `major_project_scope_boundary.py write-boundary` so the selected item root owns a concrete `scope_boundary.json`.

- [x] **Step 3: Update plan and implementation phase inputs**

Add `scope_boundary_path` input/artifact publishing to:

- `major_project_tranche_plan_phase.yaml`
- `major_project_tranche_implementation_phase.yaml`

Consume the boundary in plan draft/review/revise and implementation execute/review/fix prompts.

- [x] **Step 4: Add structural workflow tests**

Update existing YAML-shape tests to assert:

- selected tranche output bundles include `scope_boundary_path`
- plan/implementation calls receive `scope_boundary_path`
- plan and implementation provider steps consume `scope_boundary`

Run: `pytest tests/test_major_project_workflows.py -q -k 'scope_boundary or interfaces or selector'`

## Task 3: Add Roadmap Escalation From Implementation Review

- [x] **Step 1: Expand implementation decision enums**

Add `ESCALATE_ROADMAP_REVISION` to implementation phase outputs, artifacts, loop condition, expected outputs, route cases, and finalization allowed values.

- [x] **Step 2: Route implementation roadmap escalation**

In `major_project_tranche_phase_routes.py`, when the current implementation visit final decision is `ESCALATE_ROADMAP_REVISION`, synthesize a roadmap change request from the implementation escalation context and finalize item outcome `ESCALATE_ROADMAP_REVISION`.

- [x] **Step 3: Update implementation review prompt**

Tell implementation review to use `ESCALATE_ROADMAP_REVISION` when the only correct fix is reducing, splitting, moving, or rechartering selected-tranche scope.

- [x] **Step 4: Add tests**

Add tests that:

- inspect the YAML enum/route shape
- run the tranche stack with mocked providers returning implementation `ESCALATE_ROADMAP_REVISION`
- assert item outcome is `ESCALATE_ROADMAP_REVISION`, not `APPROVED`

Run: `pytest tests/test_major_project_workflows.py -q -k 'implementation_phase or roadmap_escalation'`

## Task 4: Add Completion Guard Before Item Approval

- [x] **Step 1: Wire guard into phase route**

In `route_after_implementation()`, before `_finalize_approved()`, call `check_completion()` with:

- scope boundary path
- implementation decision
- execution report path
- implementation review report path
- implementation escalation context path

If the guard returns `COMPLETE`, finalize approved. If it returns `SCOPE_MISMATCH`, synthesize roadmap revision request and finalize `ESCALATE_ROADMAP_REVISION`. For missing evidence or invalid state, preserve a skipped/blocking item outcome rather than completed.

- [x] **Step 2: Add T26-style runtime regression**

Add a mocked-provider tranche-stack test where:

- scope boundary has no authorized deferral
- implementation review writes `APPROVE`
- execution/review report says required work remains deferred/blocked

Assert:

- workflow completes without marking item `APPROVED`
- `item_outcome.txt` is `ESCALATE_ROADMAP_REVISION`
- `final_roadmap_change_request_path.txt` exists

- [x] **Step 3: Add authorized-deferral regression**

Add a direct helper test or workflow test where the scope boundary contains `authorized_deferred_work` and matching blocked/deferred wording does not prevent completion.

Run: `pytest tests/test_major_project_workflows.py -q -k 'completion_guard or approved_slice'`

## Task 5: Update Prompt and Docs Surfaces

- [x] **Step 1: Update plan prompts**

Revise plan draft/review wording so "current implementation scope" cannot mean "new tranche completion boundary." Tie any follow-up work to `scope_boundary.json` authority.

- [x] **Step 2: Update implementation prompts**

Revise implementation review/fix wording so blocked-state honesty remains valid reporting but never target-behavior completion.

- [x] **Step 3: Update workflow index**

Update `workflows/README.md` to mention roadmap-authoritative scope boundary and implementation roadmap escalation.

## Task 6: Verify

- [x] **Step 1: Collect tests**

Run: `pytest tests/test_major_project_workflows.py --collect-only -q`

- [x] **Step 2: Run focused workflow tests**

Run: `pytest tests/test_major_project_workflows.py -q`

- [x] **Step 3: Run workflow dry-run smoke**

Run: `python -m orchestrator run workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml --dry-run --input project_brief_path=workflows/examples/inputs/major_project_brief.md --input project_roadmap_path=docs/plans/major-project-demo/project-roadmap.md --input tranche_manifest_target_path=state/major-project-demo/tranche_manifest.json --input drain_state_root=state/major-project-demo/tranche-drain`

- [x] **Step 4: Check diff hygiene**

Run: `git diff --check`
