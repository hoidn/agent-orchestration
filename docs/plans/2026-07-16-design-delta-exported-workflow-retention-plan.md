# Design Delta Exported-Workflow Retention Decision

> **For agentic workers:** Execute this decision with TDD and independent
> specification/quality review. Do not edit Workflow Lisp source or run an
> orchestrator workflow from this plan.

**Status:** Complete after independent specification PASS and quality
APPROVED, evaluated against source baseline commit `36c82693`.

**Goal:** Resolve the seven active procedure-candidate call rows selected by
Procedure-First Migration Waves Task 3 before any source migration.

**Approach:** Resolve each call to its callee export, CLI-entry eligibility,
effect ownership, and persisted checkpoint boundary, then apply the accepted
identity-compatibility classes. This keeps the decision generic and
evidence-driven.

**Tradeoff:** The Design Delta helpers remain workflow/effect adapters and the
inventory gains five explicit public boundaries. This makes procedure-first
compression of the current library harder until those exported entries are
retired through a separately reviewed public-contract change or a general
atomic state upgrader exists.

## Governing decision

`docs/design/workflow_lisp_procedure_migration_identity_compatibility.md`
permits `reviewed_internal_identity_retirement` only when the callee is not
exported, registered, or public. Strict compatibility is mandatory for an
exported/public boundary.

The frontend build selects entry workflows exclusively from an entry module's
exported workflows. An exported `defworkflow` is therefore a real externally
selectable CLI entry, not an ordinary reusable `defproc` export.

All five unique callees selected by the seven active rows are exported
workflows:

| Callee | Export owner | Active call rows | Owned boundary |
| --- | --- | ---: | --- |
| `select-next-work` | `selector.orc` | 1 | provider result/bundle |
| `draft-design-gap-architecture-stdlib` | `design_gap_architect.orc` | 1 | provider result/bundle |
| `validate-design-gap-architecture-stdlib` | `design_gap_architect.orc` | 1 | materialized view and command |
| `project-design-gap-architecture-targets` | `design_gap_architect.orc` | 2 | child-workflow call/checkpoint |
| `project-design-gap-architecture-targets-stdlib` | `design_gap_architect.orc` | 2 | child-workflow call/checkpoint |

The persisted Design Delta checkpoint baseline records all seven call
boundaries and the provider/materialization/command checkpoints inside the
exported callees. Inline lowering would remove or change those identities, so
the proposed inline migration cannot satisfy mandatory strict compatibility.

The three containing module routes are `migration_candidate`,
`leaf_compile_candidate`, and `migration_evidence_only`. Those route labels do
not independently block the narrow retirement class; exported/public status
does. No store scan, owner attestation, evidence root, retirement record, or
run is required after this earlier eligibility predicate fails.

## Required disposition

1. Keep all five exported callees as `defworkflow` and keep all seven calls
   explicit.
2. Reclassify the seven active internal-call rows from `procedure-candidate`
   to `effect-adapter`, naming exported/public strict compatibility as the
   unresolved obligation.
3. Add five distinct `public-entry` records classified `public-boundary`, one
   for each exported workflow.
4. Reconcile active internal counts from 29/28/38 to 22/35/38; public entries
   increase from three to eight; append-only history stays at one.
5. Treat Task 3 Steps 2 and 3 as prohibited counterfactual migrations, run the
   unchanged-boundary integration gate in Step 4, and close Task 3 through the
   reviewed inventory update in Step 5.

## TDD and verification

Add behavioral inventory coverage that fails until:

- the seven exact internal-call IDs are `effect-adapter`;
- the five exact exported workflow identities are separate public boundaries;
- their source definitions remain `defworkflow` and exported; and
- counts reconcile in both JSON and narrative surfaces.

Then run:

```bash
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py -k 'design_delta_exported_workflow or reuse_inventory_rebaselines'
pytest -q tests/test_workflow_lisp_design_delta_smoke.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_checkpoint_identity_comparison.py -k 'stdlib_adapter or design_delta'
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py -k 'procedure_first_design_delta_public_wrapper'
python -m json.tool docs/plans/2026-07-13-procedure-first-reuse-inventory.json >/dev/null
```

Run the full migration and routing modules with 16-worker work stealing, then
obtain independent specification and quality approval before selecting Task 4.

## Completion contract

This decision is complete only when source and run roots remain unchanged,
all seven call rows and five public entries reconcile, focused and broad gates
pass, routing advances without reordering Tasks 4-8 or Stage 6, and both
independent reviews approve the result.

## Protected working-tree guard

Never stage, restore, rewrite, or clean these user-owned paths:

- `docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md`
- `docs/plans/2026-07-01-workflow-audit-tier-fixes.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md`
- `state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt`
- `tests/test_workflow_non_progress_step_back_demo.py`
- `workflows/examples/non_progress_step_back_demo.yaml`
- `workflows/library/prompts/workflow_step_back/diagnose_non_progress.md`
