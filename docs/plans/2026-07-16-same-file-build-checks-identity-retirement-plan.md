# Same-File Build-Checks Identity-Retirement Eligibility Decision

> **For agentic workers:** This decision is complete by strict compatibility
> stop. Do not execute a source migration, owner gate, or run from this file.

**Status:** Complete by fail-closed eligibility stop, evaluated against source
baseline commit `174b7351`. The source is an active `wcc_default`,
`leaf_runtime_candidate`, `preferred_current_guidance` route. The governing
identity-compatibility design makes `strict_compatibility` mandatory for every
promoted or live route, so the evidence-only
`reviewed_internal_identity_retirement` class is unavailable even though the
complete old-identity query found zero consumers in the two known retained
roots. No source, run root, run, owner attestation, retirement record, or hold
was created or changed.

**Goal:** Decide whether the internal `build-checks` workflow and its one call
in `workflows/examples/same_file_record_call_binding.orc` can become an inline
procedure under an accepted compatibility class.

**Executed architecture:** Compile the exact hypothetical inline conversion,
compare old/new production identities and the public wrapper contract, scan the
known retained roots with the complete retired query, then apply every
eligibility predicate before selecting a compatibility class. The route-status
predicate fails first and requires retention.

**Approach tradeoff:** The internal call remains a workflow/effect adapter even
though the hypothetical conversion compiles, preserves public behavior, and
has no known state consumer. This protects a current copy-safe runtime example
from changing persisted identities without strict compatibility.

## Governing decision

The authority is
`docs/design/workflow_lisp_procedure_migration_identity_compatibility.md`:

- `strict_compatibility` is mandatory for promoted/live routes; and
- `reviewed_internal_identity_retirement` requires the containing route to be
  neither promoted nor live.

The authoritative route record in
`docs/workflow_lisp_route_readiness_registry.json` identifies:

| Field | Value |
| --- | --- |
| `surface_id` | `workflows.examples.same_file_record_call_binding` |
| `path` | `workflows/examples/same_file_record_call_binding.orc` |
| `route_label` | `wcc_default` |
| `readiness_label` | `leaf_runtime_candidate` |
| `copy_safety` | `preferred_current_guidance` |
| `lowering_route` | `wcc_m4` |
| `lowering_schema_version` | `2` |

The active inventory also records the call with `live_status: live`. Route
labels are supporting evidence rather than a compiler input, but together
these authoritative planning surfaces establish that the containing route is
current/live. The plan must not encode a counterfactual `route_live: false`.

## Read-only feasibility evidence

The exact hypothetical edit would:

1. convert `defworkflow build-checks` to `defproc build-checks` with
   `:effects ((uses-command run_checks))` and `:lowering inline`; and
2. replace `(call build-checks :input input)` with `(build-checks input)`.

It compiles through WCC M4 and preserves the public wrapper contract, but exact
identity preservation is impossible:

- current/hypothetical source SHA-256:
  `f4d120a9...c4bc7` / `6af0e2da...04751`;
- old/new production projection SHA-256:
  `9bd8f96a...28474` / `c6cf423b...b0aa`;
- public parity projection SHA-256: `4f3d96e...f96c3`;
- retired identity delta: 25 domain rows / 23 unique raw identities; and
- full raw-query SHA-256: `9fdbda37...cd5a0`.

Both known retained roots returned zero matching terminal/nonterminal runs,
call frames, and consumers. The legacy root separately disclosed 4,074
terminal and 90 unrelated nonterminal runs; the completed pilot root disclosed
two terminal runs. Those match-scoped facts satisfy the store predicate but
cannot override the failed live-route predicate.

These feasibility facts are supporting diagnostics only. Because retirement
is already ineligible, no pre-edit evidence root, dedicated run root, owner
form, retirement record, or run authorization is required or permitted.

## Decision and routing

Therefore:

- `same_file_record_call_binding.orc` remains byte-unchanged;
- `build-checks` remains a workflow and its call remains explicit;
- no run ID or root mutation is authorized;
- the active inventory row moves from `procedure-candidate` to
  `effect-adapter`, with this decision and the route registry as evidence;
- Migration Waves Task 2 Step 3 closes without a migration; and
- Task 2 Step 4 is the next sub-selector.

Task 2 Step 4 must rerun the design-stack/same-file integration gates over the
retained boundaries. It must not reinterpret these stops as migrations.

## Completion contract

This decision is complete only when:

1. the route/live evidence and governing compatibility predicate are recorded;
2. source and all run roots remain unmodified;
3. the inventory reconciles after the row becomes `effect-adapter`;
4. routing selects Task 2 Step 4 without changing Tasks 3-8 or Stage 6;
5. focused/routing tests pass; and
6. independent specification and quality reviews approve the closeout.

No owner adoption is needed for this non-mutating strict-compatibility stop.
Reconsideration requires a separately reviewed change to the route's live or
promoted status; zero store consumers alone are insufficient.

## Protected working-tree guard

Never stage, restore, rewrite, or clean these user-owned paths:

- `docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md`
- `docs/plans/2026-07-01-workflow-audit-tier-fixes.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md`
- `state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt`
- `tests/test_workflow_non_progress_step_back_demo.py`
- `workflows/examples/non_progress_step_back_demo.yaml`
- `workflows/library/prompts/workflow_step_back/diagnose_non_progress.md`

Before commit, inspect `git diff --cached --name-only`, require the protected
query to print nothing, and run `git diff --cached --check`.
