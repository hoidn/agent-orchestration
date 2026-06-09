# Workflow Lisp Design/Plan/Impl Stack Parity Surface Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` (or `superpowers:subagent-driven-development`) to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `design_plan_impl_stack` migration-parity surface truthful by removing the stale unresolved deprecated YAML mechanic from the checked-in family contract, keeping the focused parity test aligned, regenerating the canonical parity artifacts through the existing CLI, and updating the summary doc only if the regenerated report changes family status.

**Architecture:** Treat `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json` as the authored contract and `orchestrator/workflow_lisp/migration_parity.py` plus `python -m orchestrator migration-parity` as the only authority for `non_regressive`, JSON report generation, markdown rendering, and aggregate index refresh. Reuse the existing family-specific evidence selectors and explicit dry-run route; update only the stale `deprecated_yaml_mechanics` ownership, the focused regression test, and derived views regenerated from the canonical JSON report.

**Tech Stack:** JSON manifests, Python parity-report tooling, `pytest`, `python -m orchestrator migration-parity`, Markdown docs

---

## Fixed Inputs

Treat these files as authority for implementation:

- `docs/index.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/steering.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/9/design-gap-architect/work_item_context.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-design-plan-impl-stack-parity-surface-recovery/implementation_architecture.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/9/design-gap-architect/check_commands.json`
- `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- `orchestrator/workflow_lisp/migration_parity.py`
- `tests/test_workflow_lisp_migration_parity.py`
- `tests/test_workflow_lisp_key_migrations.py`
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json`
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.md`
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json`
- `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md`

Current checkout facts that must not be rediscovered during implementation:

- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json` is empty, so no later recorded event supersedes this slice.
- `docs/steering.md` is empty and does not widen scope.
- The current canonical family report already shows `compile`, `shared_validation`, `dry_run`, `smoke_or_integration`, `output_contract_parity`, `terminal_state_parity`, `artifact_parity`, and `resume_parity` all passing, and the required compile artifacts all passing.
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json` still computes `non_regressive: false` because `deprecated_yaml_mechanics` contains one unresolved entry: `full YAML review-revise loop with carried findings extraction`.
- `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json` still authors that stale unresolved mechanic.
- `tests/test_workflow_lisp_migration_parity.py::test_design_plan_impl_stack_manifest_uses_defaulted_dry_run_and_family_specific_evidence` still expects the stale mechanic to remain present.
- `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md` still says the `design_plan_impl_stack` family is regressive.
- `orchestrator/workflow_lisp/migration_parity.py` already enforces the right rule: unresolved deprecated mechanics keep `non_regressive` false, and the manifest may not author `non_regressive`.

## Scope Guardrails

Implement only this bounded slice:

- audit whether the current family remains regressive only because of stale deprecated-mechanic ownership;
- normalize the `design_plan_impl_stack` manifest entry so the stale YAML mechanic is either replaced by the completed family parity route or replaced by a real current blocker if the audit proves one exists;
- align the focused parity-manifest regression test to the truthful checked-in contract;
- regenerate `design_plan_impl_stack.json`, `design_plan_impl_stack.md`, and `index.json` through `python -m orchestrator migration-parity`;
- update `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md` only if its family status wording conflicts with the regenerated canonical report.

Explicit non-goals:

- do not edit `state/LISP-MIGRATION-PARITY-DRAIN/drain/run_state.json`, the progress ledger, backlog queues, or historical drain events;
- do not rewrite `.orc` workflows, parity-family behavior tests, reusable-state logic, workflow defaults, review-loop lowering, runtime semantics, or report schema unless a focused failing check proves a narrow defect in the existing parity tool blocks truthful regeneration;
- do not hand-edit generated parity JSON, markdown, or index artifacts;
- do not treat run-state completion markers as permission to author success by hand;
- do not add adapters, helper scripts, report parsing, pointer-authority exceptions, or unrelated refactors.

## File Ownership

Modify:

- `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- `tests/test_workflow_lisp_migration_parity.py`
- `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md`
  Only if the regenerated canonical report changes or clarifies family status wording.

Regenerate through the existing CLI, never by hand:

- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json`
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.md`
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json`

Inspect only unless a focused failure proves a narrow defect blocks truthful regeneration:

- `orchestrator/workflow_lisp/migration_parity.py`
- `orchestrator/cli/commands/migration_parity.py`
- `tests/test_workflow_lisp_key_migrations.py`

## Implementation Units

### Unit 1: Manifest Contract Owns The Deprecated-Mechanic Truth

Owns:

- `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`

Stable contract:

- Keep `manual markdown parity summary -> machine-readable parity JSON report` unchanged.
- Preserve the current family-specific evidence selectors and the explicit dry-run argv for `design_plan_impl_stack`.
- Stop authoring the stale unresolved `full YAML review-revise loop with carried findings extraction` mechanic.
- Preferred normalization is to keep the mechanic name but add a `replacement` string that points at the completed `.orc` family parity route in stable terms, for example:

```json
{
  "mechanic": "full YAML review-revise loop with carried findings extraction",
  "replacement": "family-specific .orc design_plan_impl_stack parity route with typed review decisions, validated artifacts, and reusable phase-state evidence"
}
```

- If the audit proves the family is still regressive for a different current reason, replace the stale wording with that real blocker instead of fabricating success.

### Unit 2: Focused Parity Test Owns The Checked-In Contract

Owns:

- `tests/test_workflow_lisp_migration_parity.py`

Stable contract:

- Keep the dry-run input count assertion and the family-specific evidence-selector assertions.
- Replace the stale expectation `assert "full YAML review-revise loop with carried findings extraction" in deprecated` with an assertion that the family no longer carries that mechanic as unresolved.
- Preferred shape:

```python
loop_entry = next(
    entry
    for entry in target["deprecated_yaml_mechanics"]
    if entry["mechanic"] == "full YAML review-revise loop with carried findings extraction"
)
assert loop_entry["replacement"] == (
    "family-specific .orc design_plan_impl_stack parity route with typed "
    "review decisions, validated artifacts, and reusable phase-state evidence"
)
stale = [
    entry
    for entry in target["deprecated_yaml_mechanics"]
    if entry["mechanic"] == "full YAML review-revise loop with carried findings extraction"
    and not entry.get("replacement")
    and not entry.get("waiver")
]
assert not stale
```

- Rename the test only if the old name becomes misleading after this contract change.

### Unit 3: Canonical JSON Owns Derived Parity Views

Owns:

- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json`
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.md`
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json`
- `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md`

Stable contract:

- Regenerate the family JSON report, markdown report, and aggregate index only through the migration-parity CLI.
- Treat `design_plan_impl_stack.json` as authority; markdown, index, and the summary doc are derived views.
- If regeneration makes `non_regressive=true`, update the summary doc so it no longer says the family is regressive.
- If regeneration keeps `non_regressive=false`, the report must name a real current blocker rather than the stale YAML-loop mechanic, and the summary doc should reflect that blocker at a high level.

## Task Checklist

### Task 1: Audit The Current Family Parity Surface Before Editing

**Files:**

- Inspect: `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- Inspect: `tests/test_workflow_lisp_migration_parity.py`
- Inspect: `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json`
- Inspect: `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.md`
- Inspect: `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json`
- Inspect: `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md`
- Inspect if needed: `orchestrator/workflow_lisp/migration_parity.py`

- [ ] Confirm the current family report already has all required evidence roles and required compile artifacts passing.
- [ ] Confirm the stale unresolved deprecated mechanic is the only visible reason `design_plan_impl_stack.json` still computes `non_regressive=false`.
- [ ] Confirm the family-specific evidence selectors and explicit dry-run route in the manifest are already the intended ones and do not need redesign.
- [ ] If the audit reveals a second real blocker, stop this plan and write a short design-gap note instead of normalizing the manifest to success.

**Audit verification:**

- [ ] `python -m pytest --collect-only tests/test_workflow_lisp_migration_parity.py tests/test_workflow_lisp_key_migrations.py -q`

Expected result: collection succeeds and confirms the focused parity module and family-evidence module still exist before any edits.

### Task 2: Normalize The `design_plan_impl_stack` Manifest Entry

**Files:**

- Modify: `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`

- [ ] Keep the `design_plan_impl_stack` `dry_run` command unchanged, including all seven `--input` pairs.
- [ ] Keep the current family-specific selectors for `smoke_or_integration`, `output_contract_parity`, `terminal_state_parity`, `artifact_parity`, and `resume_parity`.
- [ ] Replace the stale unresolved `full YAML review-revise loop with carried findings extraction` entry with the approved stable `replacement` string if the Task 1 audit confirmed it is the only blocker.
- [ ] If Task 1 found a different blocker, author that blocker explicitly instead of the stale YAML wording.
- [ ] Do not author `non_regressive` anywhere in the manifest.

**Blocking verification after Task 2:**

- [ ] `python -m pytest tests/test_workflow_lisp_migration_parity.py -k "design_plan_impl_stack_manifest_uses_defaulted_dry_run_and_family_specific_evidence" -q`

Expected result: the focused manifest test passes with the new non-stale deprecated-mechanic contract and unchanged dry-run and selector assertions.

### Task 3: Align The Focused Parity Regression Test

**Files:**

- Modify: `tests/test_workflow_lisp_migration_parity.py`

- [ ] Update the focused `design_plan_impl_stack` manifest test so it asserts the stale YAML-loop mechanic is no longer unresolved.
- [ ] Keep the test scoped to manifest contract truth, not parity-engine reimplementation.
- [ ] If a renamed test function reads more truthfully after the expectation change, rename it and rely on the collect-only command above to validate discovery.
- [ ] Do not weaken the selector assertions; they still need to catch regressions back to `review_loop_parity_fixture` or compile-only placeholders.

**Blocking verification after Task 3:**

- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "design_plan_impl_stack_orc_runtime_smoke_executes_single_pass_stack or design_plan_impl_stack_orc_runtime_output_contract_matches_stack_outputs or design_plan_impl_stack_orc_runtime_completes_with_expected_terminal_state or design_plan_impl_stack_orc_runtime_materializes_expected_artifacts or resume_or_start_plan_gate_reusable_state_parity_path" -q`

Expected result: the family evidence selectors referenced by the manifest still pass unchanged, proving this slice did not accidentally reopen family behavior work.

### Task 4: Regenerate The Canonical Family Parity Artifacts

**Files:**

- Regenerate: `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json`
- Regenerate: `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.md`
- Regenerate: `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json`

- [ ] Run the family-only parity CLI from the repo root using the checked-in manifest and output root.
- [ ] Verify the regenerated JSON report no longer contains the stale unresolved deprecated mechanic.
- [ ] Verify `index.json` reflects the regenerated family report’s `non_regressive`, candidate, and YAML primary fields.
- [ ] If the family remains regressive, confirm the regenerated report now names a real blocker rather than preserving the stale YAML-loop wording.
- [ ] Do not hand-edit the generated JSON, markdown, or index files.

**Blocking verification after Task 4:**

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
stale = [m for m in report['deprecated_yaml_mechanics'] if m.get('mechanic') == 'full YAML review-revise loop with carried findings extraction' and not m.get('replacement') and not m.get('waiver')]
assert not stale
print('design_plan_impl_stack parity surface is internally consistent and no longer carries the stale unresolved YAML-loop mechanic')
PY`

Expected result: the CLI completes successfully and the Python consistency check prints the success line shown above.

### Task 5: Reconcile The Summary Doc Only If The Regenerated Report Changed Family Status

**Files:**

- Modify if needed: `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md`

- [ ] Compare the regenerated canonical family report with the summary doc’s `Parity Status` section.
- [ ] If the report is now non-regressive, update the summary doc so `design_plan_impl_stack` no longer says `non_regressive=false`.
- [ ] If the report remains regressive, update the summary doc only if it still names the stale YAML-loop blocker instead of the regenerated report’s real blocker.
- [ ] Keep the summary doc high-level and derived; do not add implementation detail that belongs in the canonical JSON report.

**Final verification after Task 5:**

- [ ] Re-run `python -m pytest tests/test_workflow_lisp_migration_parity.py -k "design_plan_impl_stack_manifest_uses_defaulted_dry_run_and_family_specific_evidence" -q` if the summary update required any nearby doc-driven wording changes in the same patch.
- [ ] Re-open `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.md` and `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md` to confirm the high-level status wording agrees.

## Stop / Revise Criteria

Stop implementation and revise the plan instead of widening scope if any of these occur:

- the Task 1 audit shows a real remaining parity blocker beyond stale deprecated-mechanic ownership;
- the family-evidence selectors in `tests/test_workflow_lisp_key_migrations.py` fail before any manifest/test changes;
- truthful regeneration requires changes to Workflow Lisp family behavior, runtime semantics, parity schema, or new adapters rather than manifest/test repair;
- the migration-parity CLI or `compute_non_regressive(...)` proves defective in a way that cannot be fixed by a narrow local bugfix in the existing parity tool.

## Done Criteria

The slice is complete only when all of the following are true:

- `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json` no longer carries `full YAML review-revise loop with carried findings extraction` as an unresolved deprecated mechanic for `design_plan_impl_stack`;
- `tests/test_workflow_lisp_migration_parity.py` asserts the truthful non-stale manifest contract without weakening the dry-run or family-selector checks;
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json`, `design_plan_impl_stack.md`, and `index.json` are regenerated by the CLI and internally consistent;
- if `non_regressive` is still false, the report names a real blocker rather than the stale YAML-loop wording;
- `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md` agrees with the regenerated canonical report;
- no run-state files, progress ledgers, `.orc` family behavior surfaces, adapters, or unrelated runtime/frontend modules were changed.
