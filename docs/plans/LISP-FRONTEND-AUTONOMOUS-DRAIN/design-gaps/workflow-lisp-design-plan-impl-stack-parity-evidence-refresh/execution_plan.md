# Workflow Lisp Design/Plan/Impl Stack Parity-Evidence Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refresh the durable `design_plan_impl_stack` parity evidence so the checked-in manifest, canonical JSON report, derived markdown/index, and drain-facing summary all truthfully reflect the current family proof state.

**Architecture:** Treat `python -m orchestrator migration-parity` and `orchestrator/workflow_lisp/migration_parity.py` as the only authority for report execution and `non_regressive` computation. Start with an explicit audit gate over the current family `.orc` source, focused migration tests, and manifest selectors; then align the manifest and focused assertions to the audited family route, regenerate the family parity artifacts through the CLI, and reconcile any stale summary docs to the regenerated JSON report. If the audit proves the family route is still incomplete, preserve a truthful regressive outcome and update the blocker wording instead of fabricating success.

**Tech Stack:** Workflow Lisp migration-parity manifest and reports, `pytest`, `python -m orchestrator`, markdown status docs, JSON artifacts

---

## Fixed Inputs

Treat these as implementation authority:

- `docs/index.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/steering.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/state.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/run_state.json`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/8/design-gap-architect/work_item_context.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/8/design-gap-architect/check_commands.json`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-design-plan-impl-stack-parity-evidence-refresh/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-design-plan-impl-stack-review-loop-parity/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-design-plan-impl-stack-review-loop-parity/execution_plan.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-migration-promotion-parity-report-gate/implementation_architecture.md`

## Current Checkout Facts

Do not rediscover these during implementation:

- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json` is still `{"ledger_version":1,"events":[]}`, so no later ledger event supersedes this work item.
- `docs/steering.md` is empty at this checkout and does not widen scope.
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/run_state.json` records `workflow-lisp-design-plan-impl-stack-review-loop-parity` as completed on `2026-06-03T11:28:02.880267Z`, but that event is historical evidence only and must not be edited by this slice.
- `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json` still gives `design_plan_impl_stack` a dry-run command with explicit `--input` bindings, generic `review_loop_parity_fixture` selectors for four evidence roles, and the old deprecated mechanic `full YAML review-revise loop with carried findings extraction`.
- `tests/test_workflow_lisp_migration_parity.py::test_design_plan_impl_stack_manifest_uses_defaulted_dry_run_and_family_specific_evidence` already expects the opposite: no explicit dry-run `--input`, no old deprecated mechanic, family-specific selectors, and a resume selector that targets reusable-state parity.
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json` and the derived markdown/index still report `non_regressive=false` and still carry the old YAML-loop blocker wording.
- `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md` still says the family is regressive.
- The checked-in family `.orc` sources still appear pre-refresh: `workflows/examples/design_plan_impl_review_stack_v2_call.orc` defines the phase workflows inline, and the three library modules remain single-pass draft or execute plus one review flows.

## Hard Scope Limits

Implement only the selected evidence-refresh slice:

- audit whether the current checkout actually contains a family-specific post-prerequisite proof route for `design_plan_impl_stack`;
- align the durable parity manifest entry and focused evidence assertions to the audited route;
- rerun the family-only `migration-parity` command;
- refresh the authoritative family JSON report, its derived markdown report, and the aggregate parity index;
- reconcile stale family status wording in checked-in summary docs if they contradict the regenerated report.

Explicit non-goals:

- no rewrites of the family `.orc` workflows or generic Workflow Lisp substrate as part of this slice;
- no manual edits to `state/LISP-MIGRATION-PARITY-DRAIN/drain/run_state.json`, backlog state, queue files, or the progress ledger;
- no manual edits to generated `non_regressive` values;
- no new adapters, scripts, runtime effects, pointer-as-state behavior, or report-parsing authority;
- no family promotion claim unless the recomputed parity report actually supports it.

## File Ownership

Modify:

- `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- `tests/test_workflow_lisp_migration_parity.py`
- `tests/test_workflow_lisp_key_migrations.py`
  - only if narrowly required to point evidence at the actual family proof route
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json`
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.md`
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json`
- `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md`
  - only if it still contradicts the regenerated canonical report

Inspect first, then modify only if a concrete refresh defect is proven:

- `orchestrator/workflow_lisp/migration_parity.py`
- `orchestrator/cli/commands/migration_parity.py`

Inspect only:

- `workflows/examples/design_plan_impl_review_stack_v2_call.orc`
- `workflows/library/tracked_design_phase.orc`
- `workflows/library/tracked_plan_phase.orc`
- `workflows/library/design_plan_impl_implementation_phase.orc`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/run_state.json`

## Required Decisions

These are fixed for this slice:

- The parity JSON report remains the authoritative family status surface; markdown, `index.json`, and historical execution summaries are derived views.
- The audit gate comes first. No report rewrite happens until the current family route is inspected and the focused evidence commands are rerun or validated.
- If the audited family route is still incomplete, the implementation must keep or regenerate a truthful regressive outcome with an updated blocker rather than preserving stale generic selectors or claiming success.
- If the focused family route already exists, the manifest must stop pointing at `review_loop_parity_fixture` and must use selectors that mention `design_plan_impl_stack`.
- The dry-run route must describe the real wrapper boundary. If defaults are genuinely part of the current boundary, remove explicit `--input` arguments. If the audit proves defaults are still absent, keep the dry-run truthful and update the focused assertions to match reality before regenerating the report.
- `resume_parity` must continue to point at reusable-state or `resume-or-start` family evidence rather than generic review-loop evidence.
- `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md` may be updated only to match the regenerated canonical report, never to overstate the family state.

## Task Checklist

### Task 1: Audit The Actual Family Evidence Route Before Any Report Rewrite

**Files:**

- Inspect: `workflows/examples/design_plan_impl_review_stack_v2_call.orc`
- Inspect: `workflows/library/tracked_design_phase.orc`
- Inspect: `workflows/library/tracked_plan_phase.orc`
- Inspect: `workflows/library/design_plan_impl_implementation_phase.orc`
- Inspect: `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- Inspect: `tests/test_workflow_lisp_migration_parity.py`
- Inspect: `tests/test_workflow_lisp_key_migrations.py`
- Inspect: `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json`
- Inspect: `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md`
- Inspect: `state/LISP-MIGRATION-PARITY-DRAIN/drain/run_state.json`

- [ ] Confirm that the progress ledger is still empty and that `run_state.json` is informational only for this slice.
- [ ] Audit the current family `.orc` wrapper and library modules and record whether they still represent the older single-pass family state.
- [ ] Compare the audited code state to the focused manifest assertion and identify whether the existing test expectation is already truthful or is ahead of the current checkout.
- [ ] Decide which of these branches is true and carry that decision into the remaining tasks:
  - `family_route_present`: family-specific post-prerequisite evidence exists or can be pointed to directly.
  - `family_route_absent_or_incomplete`: the family still lacks the intended post-prerequisite proof route, so the regenerated report must remain regressive or blocked with a truthful blocker.

**Blocking verification after Task 1:**

- [ ] `python -m pytest --collect-only tests/test_workflow_lisp_migration_parity.py tests/test_workflow_lisp_key_migrations.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "design_plan_impl_stack or review_loop_parity_fixture or resume_or_start_plan_gate_reusable_state_parity_path" -q`

### Task 2: Make The Manifest And Focused Assertions Match The Audited Family Route

**Files:**

- Modify: `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- Modify: `tests/test_workflow_lisp_migration_parity.py`
- Modify only if needed for truthful family selectors: `tests/test_workflow_lisp_key_migrations.py`

- [ ] Update the `design_plan_impl_stack` manifest entry so every evidence command describes the actual audited family route rather than a stale generic placeholder.
- [ ] Replace `review_loop_parity_fixture` selectors in `smoke_or_integration`, `output_contract_parity`, `terminal_state_parity`, and `artifact_parity` with family-specific selectors if those selectors are justified by the audit.
- [ ] Keep `resume_parity` aimed at reusable-state or `resume-or-start` family evidence.
- [ ] Remove the deprecated mechanic `full YAML review-revise loop with carried findings extraction` only if the audited family route genuinely no longer depends on that blocker.
- [ ] Decide whether the dry-run command should be defaulted or explicit based on the audited wrapper boundary, then make the test and manifest agree on that truthful route.
- [ ] If `tests/test_workflow_lisp_migration_parity.py::test_design_plan_impl_stack_manifest_uses_defaulted_dry_run_and_family_specific_evidence` is not truthful for the audited checkout, rewrite the assertion so it checks the truthful family route instead of the aspirational one.
- [ ] Touch `tests/test_workflow_lisp_key_migrations.py` only when a family-specific selector or family proof is missing and a narrow test adjustment is required to create a durable evidence target for the parity manifest.

**Blocking verification after Task 2:**

- [ ] `python -m pytest tests/test_workflow_lisp_migration_parity.py -k "design_plan_impl_stack_manifest_uses_defaulted_dry_run_and_family_specific_evidence" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "design_plan_impl_stack or review_loop_parity_fixture or resume_or_start_plan_gate_reusable_state_parity_path" -q`

### Task 3: Regenerate The Canonical Family Parity Artifacts Through The Existing CLI

**Files:**

- Refresh generated artifacts under `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/`
- Inspect first, modify only if the CLI cannot truthfully express the refreshed family state:
  - `orchestrator/workflow_lisp/migration_parity.py`
  - `orchestrator/cli/commands/migration_parity.py`

- [ ] Rerun the existing family-only parity command using the updated manifest and current checkout.
- [ ] Do not hand-edit the JSON, markdown, or index outputs.
- [ ] If the CLI rerun still yields `non_regressive=false`, inspect whether the blocker text is truthful; if it is stale, fix the parity tool only if the defect is in report rendering or selector wiring rather than the family implementation itself.
- [ ] If the audit showed the family route is absent or incomplete, ensure the regenerated report names that blocker rather than preserving the old YAML-loop blocker or promoting the family.

**Blocking verification after Task 3:**

- [ ] `python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity --target design_plan_impl_stack`
- [ ] `python - <<'PY'
import json
from pathlib import Path
report = json.loads(Path('artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json').read_text(encoding='utf-8'))
index = json.loads(Path('artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json').read_text(encoding='utf-8'))
entry = next(item for item in index['targets'] if item['workflow_family'] == 'design_plan_impl_stack')
assert entry['json_report'] == 'artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json'
assert entry['non_regressive'] == report['non_regressive']
assert entry['candidate'] == report['candidate']
assert entry['yaml_primary'] == report['yaml_primary']
print('design_plan_impl_stack parity artifacts are internally consistent')
PY`

### Task 4: Reconcile Derived Summary Docs To The Regenerated Canonical Report

**Files:**

- Modify only if needed: `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md`
- Inspect: `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.md`
- Inspect: `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json`
- Inspect: `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json`

- [ ] Compare the regenerated JSON report, derived markdown, and aggregate index for status and blocker wording consistency.
- [ ] Update the execution summary doc only if it still contradicts the regenerated JSON report on family status or the canonical execution-target wording.
- [ ] Keep the summary doc high-level and derived; do not copy transient log detail or hand-author a new parity result.

**Blocking verification after Task 4:**

- [ ] Re-read `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md` and confirm its family wording matches the regenerated JSON report.
- [ ] Re-read `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.md` and confirm it matches the JSON report's `non_regressive` result and blocker or deprecated-mechanic summary.

### Task 5: Run The Final Visible Verification Bundle

**Files:**

- No new files

- [ ] Re-run the deterministic command set from `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/8/design-gap-architect/check_commands.json`.
- [ ] Capture the outcome of each command in the implementation notes or final handoff so the refreshed evidence is backed by visible command output.
- [ ] Stop if any command fails and either fix the in-scope defect or return the blocker with the owning slice named explicitly.

**Required final verification commands:**

- [ ] `python -m pytest --collect-only tests/test_workflow_lisp_migration_parity.py tests/test_workflow_lisp_key_migrations.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_migration_parity.py -k "design_plan_impl_stack_manifest_uses_defaulted_dry_run_and_family_specific_evidence" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "design_plan_impl_stack or review_loop_parity_fixture or resume_or_start_plan_gate_reusable_state_parity_path" -q`
- [ ] `python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity --target design_plan_impl_stack`
- [ ] `python - <<'PY'
import json
from pathlib import Path
report = json.loads(Path('artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json').read_text(encoding='utf-8'))
index = json.loads(Path('artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json').read_text(encoding='utf-8'))
entry = next(item for item in index['targets'] if item['workflow_family'] == 'design_plan_impl_stack')
assert entry['json_report'] == 'artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json'
assert entry['non_regressive'] == report['non_regressive']
assert entry['candidate'] == report['candidate']
assert entry['yaml_primary'] == report['yaml_primary']
print('design_plan_impl_stack parity artifacts are internally consistent')
PY`

## Acceptance Checklist

- [ ] The `design_plan_impl_stack` manifest entry no longer contains stale generic selectors or stale deprecated-mechanic text that contradicts the audited family route.
- [ ] The focused manifest assertion in `tests/test_workflow_lisp_migration_parity.py` matches the truthful family route for this checkout.
- [ ] The family parity JSON report is regenerated through `python -m orchestrator migration-parity`, not hand-edited.
- [ ] The derived markdown report and `index.json` agree with the regenerated JSON report.
- [ ] Any checked-in summary doc that still mentions this family no longer contradicts the regenerated canonical report.
- [ ] If the family proof is still incomplete, the refreshed evidence names the real blocker instead of preserving the old YAML-loop blocker or claiming parity success.
- [ ] No run-state edits, no progress-ledger edits, no adapter additions, and no unrelated frontend or runtime refactors were introduced.
