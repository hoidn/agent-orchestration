# Procedure-First Migration Waves Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate reviewed internal workflow-as-function sites to typed procedures in independently testable families, reclassify evidence-held adapters, preserve durable public workflows, and hand compatibility-only YAML rows to the existing Stage 6 retirement program.

**Architecture:** Treat `2026-07-13-procedure-first-reuse-inventory.json` as a reviewed planning queue, never as implementation truth by itself. Each wave first resolves and reclassifies its exact rows from current compile/runtime evidence, then migrates one family behind retained public wrappers with computed parity; compatibility/legacy rows are not translated and move to YAML retirement only after their `.orc` replacement and archive gates are independently proven. Shared compiler changes are forbidden in a family commit and return to the substrate queue.

**Tech Stack:** JSON inventory, Workflow Lisp `.orc`, YAML compatibility estate, WCC compiler, migration-parity and route-readiness tooling, pytest, orchestrator CLI.

---

## Authority, order, and invariants

**Status:** Current selector (activated 2026-07-16). Task 1's post-hardening
rebaseline is complete at `4983afff` with its narrative correction at
`fa16bcf0`. **Current sub-selector: Task 2 Step 2,
`design-plan-impl-implementation-phase`.** Task 2 Step 1's bounded
`docs/plans/2026-07-16-tracked-design-phase-identity-retirement-plan.md`
closed by a fail-closed eligibility stop: the completed pilot store retains 26
supported old-identity consumers, so `tracked-design-phase` remains a workflow
and its inventory row is now `effect-adapter`. This is not a new design or a
reordering of the remaining Task 2 work or Tasks 3-8. The prerequisite
`docs/plans/2026-07-13-resume-projection-integrity-hardening-implementation-plan.md`
completed at `fdf1e06b` with fresh focused acceptance evidence, a deterministic
public CLI smoke, broad baseline equivalence, and independent specification and
quality reviews. No Task 2 family migration is complete, and no later task is
activated or reordered by this status transition.

- Accepted contract: `docs/design/workflow_lisp_procedure_first_reuse_contract.md`
- Reviewed queue: `docs/plans/2026-07-13-procedure-first-reuse-inventory.json`
- Human-readable inventory: `docs/plans/2026-07-13-procedure-first-reuse-inventory.md`
- Stage 6 owner: `docs/plans/2026-07-07-yaml-retirement-program.md`
- Migration parity owner: `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- Accepted resume-integrity design:
  `docs/design/resume_projection_integrity_hardening.md`
- Resume-integrity implementation gate:
  `docs/plans/2026-07-13-resume-projection-integrity-hardening-implementation-plan.md`
- Completed design/specification/plan artifact provenance:
  `docs/plans/2026-07-13-resume-projection-integrity-hardening-design-plan.md`
- Typed result guidance, the effect substrate plan, the tracked-plan pilot, and
  the full resume projection-integrity hardening implementation are complete
  and independently reviewed with fresh acceptance evidence. The hardening
  implementation plan records the implementation evidence; its accepted design
  and planning artifacts alone remain insufficient proof.
- The hardening implementation gate passed, and Task 1 rebaselined that
  evidence and the inventory on the post-hardening checkout. Task 2 is now the
  first authorized family source migration. Production-family Tasks 5–6 retain
  every later prerequisite in this plan.
- Preserve the inventory's separate `public-entry` records. In particular, never migrate:
  - `workflows/library/lisp_frontend_design_delta/drain.orc::drain` away from `defworkflow`; or
  - `workflows/examples/design_plan_impl_review_stack_v2_call.orc::design-plan-impl-review-stack` away from `defworkflow`.
- A source row changes classification only through a reviewed inventory update that names fresh evidence. Source edits alone do not reclassify it.
- No family task may include shared compiler/runtime substrate. A new substrate need stops the family and gets its own plan.
- No YAML file is archived/deleted here. This plan marks Stage 6 eligibility and invokes the existing retirement plan's gates later.

## Protected working-tree guard

The following user-owned dirty paths are outside every task in this plan:

- `docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md`
- `docs/plans/2026-07-01-workflow-audit-tier-fixes.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md`
- `state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt`
- `tests/test_workflow_non_progress_step_back_demo.py`
- `workflows/examples/non_progress_step_back_demo.yaml`
- `workflows/library/prompts/workflow_step_back/diagnose_non_progress.md`

Before every commit, run `git diff --cached --name-only`, then run:

```bash
git diff --cached --name-only -- \
  'docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md' \
  'docs/plans/2026-07-01-workflow-audit-tier-fixes.md' \
  'docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md' \
  'state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt' \
  'tests/test_workflow_non_progress_step_back_demo.py' \
  'workflows/examples/non_progress_step_back_demo.yaml' \
  'workflows/library/prompts/workflow_step_back/diagnose_non_progress.md'
```

The literal protected-path command must print nothing; the full staged list
must be a subset of the active task's `Files` list. Never stage, restore, or
rewrite a protected path. Record its initial `git status --short` output only
as a guard baseline; user changes to those paths are not plan failures.

## Current queue after Task 2 Step 1

| Class | Count | Disposition |
| --- | ---: | --- |
| `procedure-candidate` | 31 | Migrate by `.orc` family after parity. |
| `effect-adapter` | 26 | Reclassify only after effect, identity, artifact/publication, source-map, child-call, checkpoint, state-consumer, and resume evidence. |
| `legacy-retire` | 38 | Do not translate; coordinate with Stage 6 after replacement evidence. |
| `public-boundary` | 3 separate entries | Preserve as workflows and negative regression coverage. |

The v2 inventory also contains one append-only `migrated` history row for the
completed pilot call; history is separate from the 95 active records above.

## Per-family migration protocol

Every migration family in Tasks 2, 3, 5, and 6 repeats these steps; do not
collapse them across families:

1. Resolve each inventory ID to its enclosing caller, callee definition/import, exports, workflow-entry registration, and current effect summary.
2. Write RED tests requiring `defproc :lowering inline`, ordinary procedure application, and retained public wrapper/non-candidate boundaries.
3. Capture semantic before-state for public inputs/defaults/outputs, artifacts/publications, terminal outcomes, effects, source maps, state/write roots, checkpoint IDs, and resume behavior.
4. Migrate only the selected family definitions/calls.
5. Run compile plus shared validation, dry-run where the family has a runnable entry, end-to-end/runtime evidence, and computed migration parity.
6. Move disappeared call-site records into the inventory's append-only history
   with evidence; keep active counts limited to current-source records and
   preserve stable IDs plus source-commit provenance.
7. Commit source/tests first, evidence/inventory second. Obtain specification and quality reviews before starting the next family.

### Task 1: Rebaseline Guidance, Substrate, Pilot, And Inventory

**Files:**
- Inspect: `docs/plans/2026-07-10-workflow-lisp-typed-result-guidance-plan.md`
- Inspect: `docs/plans/2026-07-13-procedure-first-substrate-gaps-plan.md`
- Inspect: `docs/plans/2026-07-13-procedure-first-pilot-plan.md`
- Inspect: `docs/plans/2026-07-13-resume-projection-integrity-hardening-design-plan.md`
- Inspect: `docs/design/resume_projection_integrity_hardening.md`
- Inspect: `docs/plans/2026-07-13-resume-projection-integrity-hardening-implementation-plan.md`
- Modify: `docs/plans/2026-07-13-procedure-first-reuse-inventory.json`
- Modify: `docs/plans/2026-07-13-procedure-first-reuse-inventory.md`
- Test: `tests/test_workflow_lisp_procedure_first_migrations.py`

- [x] **Step 1: Verify prerequisite completion evidence**

Confirm typed result guidance is complete, the direct/transitive effect
substrate gate passed, the tracked-plan pilot passed all applicable strict or
reviewed-retirement parity gates, and resume projection-integrity hardening is
accepted, implemented, and independently reviewed with fresh completion
evidence. Rebaseline the inventory and family selectors against that
post-hardening checkout. Do not duplicate or reopen direct-root/guidance
semantics, and stop before any migration if the hardening implementation gate
cannot be proven. The accepted design, completed planning tranche, or presence
of the implementation-plan file is not sufficient proof.

- [x] **Step 2: Regenerate source locations and current commit provenance**

```bash
rg -n --glob '*.orc' '\(call\s+' workflows | sort
rg -n --glob '*.yaml' --glob '*.yml' '^[[:space:]-]*call:[[:space:]]' workflows | sort
python -m json.tool docs/plans/2026-07-13-procedure-first-reuse-inventory.json >/dev/null
```

Upgrade the inventory once to
`procedure_first_reuse_inventory.v2` before recording any completed migration.
Keep `records` as the active current-source population and add an append-only
`history` array. A history entry contains the original stable `id`, the last
active record, `disposition` (`migrated`, `retired`, or `retained-public`),
`completed_at_commit`, and `evidence_paths`. Move the disappeared pilot call
from `records` to `history` with `disposition: migrated`; do not invent a
current source locator for it. Active classification counts cover `records`
only, while separate history counts reconcile every completed disposition.
Update `source_commit`, current line locators, and active totals without
changing IDs merely because lines moved.

- [x] **Step 3: Add retained-public-boundary tests**

Assert the Design Delta `drain` and design-plan stack entry remain exported `defworkflow` entries, are present in route readiness/public entry evidence, and are not procedure-migration candidates.

Add a reusable production-route harness in
`tests/test_workflow_lisp_procedure_first_migrations.py` with these selectors:

- `test_procedure_first_design_delta_public_wrapper_runtime_contract` executes
  the current `.orc` drain through deterministic provider/command doubles and
  captures typed public output, artifacts/publication, effects, source-map
  owners, and checkpoint identities; and
- `test_procedure_first_design_delta_public_wrapper_resume_contract` fails
  after one committed effect, resumes the same `run_id`, proves the effect is
  not replayed, and compares final output/artifacts with a clean run.

These baseline harness tests run before any Design Delta family edit and are
rerun after every Task 3, 5, and 6 source commit. They are behavioral runtime/E2E
gates, not compile or dry-run aliases.

- [x] **Step 4: Run the queue gate and commit**

```bash
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py -k 'public_boundary or inventory or procedure_first_design_delta_public_wrapper'
git diff --check -- docs/plans/2026-07-13-procedure-first-reuse-inventory.json docs/plans/2026-07-13-procedure-first-reuse-inventory.md tests/test_workflow_lisp_procedure_first_migrations.py
git add docs/plans/2026-07-13-procedure-first-reuse-inventory.json docs/plans/2026-07-13-procedure-first-reuse-inventory.md tests/test_workflow_lisp_procedure_first_migrations.py
git commit -m "Rebaseline procedure-first migration inventory"
```

#### Task 1 closeout evidence (2026-07-16)

- Inventory/schema implementation: `4983afff`; narrative-total correction:
  `fa16bcf0`.
- Collection and tests: 109 collected; queue selector 4 passed, 105
  deselected; full module 108 passed, 1 skipped.
- Runtime evidence: an actual production Design Delta public-wrapper clean run
  and same-run resume after a committed effect, with no effect replay and
  equal typed public output, artifacts/publication, effects, source-map owners,
  and checkpoint identities.
- Inventory evidence: JSON extraction and validation, authored-source
  extraction, active/history reconciliation, and clean diff checks.
- Reviews: final independent specification review PASS and independent quality
  review APPROVED for `4983afff` plus `fa16bcf0`.

### Task 2: Finish The Small Example Families

**Files:**
- Modify: `workflows/examples/design_plan_impl_review_stack_v2_call.orc`
- Modify: `workflows/examples/same_file_record_call_binding.orc`
- Modify: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Modify: `tests/test_workflow_lisp_examples.py`
- Modify: `tests/test_workflow_lisp_key_migrations.py`
- Modify conditionally: `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- Modify: `docs/plans/2026-07-13-procedure-first-reuse-inventory.json`
- Modify: `docs/plans/2026-07-13-procedure-first-reuse-inventory.md`

- [x] **Step 1: Resolve `tracked-design-phase` without an ineligible migration**

Task 2 Step 1's initial TDD experiment reached the global identity stop: public contract
shape remained viable, but the old internal workflow-call/checkpoint identity
set cannot remain exact after inline lowering. Execute
`docs/plans/2026-07-16-tracked-design-phase-identity-retirement-plan.md` as the
bounded prerequisite. Its reviewed known-store correction identified the
completed tracked-plan pilot root, and the generic scanner found 26 supported
old-identity consumers there using a five-identity witness subset. The accepted
`reviewed_internal_identity_retirement` class requires zero consumers, so the
source remains byte-unchanged and the active row is retained as
`effect-adapter`. The durable scan binding and replay test are recorded in that
plan. This closes the global stop without weakening identity rules; Step 2 is
now selected.

Historical unexecuted migration instructions, retained only as the
counterfactual that triggered the stop, were to add a RED assertion named
`test_tracked_design_phase_is_inline_procedure_with_public_wrapper` that
requires the definition to be `defproc :lowering inline`, its one use to be an
ordinary procedure application, and the public stack to remain the only
exported workflow. Verify it fails on the workflow definition/call, make only
that source change, then run:

```bash
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py tests/test_workflow_lisp_key_migrations.py -k 'design_plan_impl_stack'
python -m orchestrator compile workflows/examples/design_plan_impl_review_stack_v2_call.orc --entry-workflow design-plan-impl-review-stack --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.commands.json
```

Expected: PASS with unchanged public outputs, artifacts, effects, resume
behavior, and every public or preserved checkpoint ID. The exact eligible
old-internal/new-inline identity delta is accepted only through the validated
retirement record; it is never baseline-refreshed or described as unchanged.

No phase/source migration commit exists or is permitted under the observed
store evidence.

- [ ] **Step 2: Migrate and review `design-plan-impl-implementation-phase`**

Add a separate RED assertion named
`test_stack_implementation_phase_is_inline_procedure_with_public_wrapper`,
verify the current definition/call fails it, then convert only that phase and
its one use. Rerun the same design-stack test and compile commands from Step 1.
Commit as `Migrate stack implementation phase to a procedure`, then obtain
independent specification and quality PASS before continuing.

- [ ] **Step 3: Migrate and review `same_file_record_call_binding.orc`**

Convert only the internal `build-checks` callee and its call to an inline procedure. Retain its existing exported workflow entry. Add output/effect/source-map assertions to `test_same_file_record_call_binding_orc_compiles_with_shared_validation`.

Add
`test_same_file_record_call_binding_public_wrapper_runtime_after_procedure_migration`
to `tests/test_workflow_lisp_procedure_first_migrations.py`. Execute the
exported wrapper with the deterministic `run_checks` command double and assert
the same typed `WorkflowOutput`, command artifact, caller-visible command
effect, and public entry identity as the pre-migration baseline.

```bash
pytest -q tests/test_workflow_lisp_examples.py tests/test_workflow_lisp_procedure_first_migrations.py -k 'same_file_record_call_binding'
python -m orchestrator compile workflows/examples/same_file_record_call_binding.orc --entry-workflow run-same-file-record-call-binding --command-boundaries-file tests/fixtures/workflow_lisp/cli/commands.json
python -m orchestrator run workflows/examples/same_file_record_call_binding.orc --entry-workflow run-same-file-record-call-binding --command-boundaries-file tests/fixtures/workflow_lisp/cli/commands.json --input report_path=artifacts/work/defproc_procedural_substrate_execution_report.md --dry-run
```

Expected: compile and dry-run exit 0 through the source's exported
`run-same-file-record-call-binding` entry and shared command-contract
validation.

Commit this source/tests slice as
`Migrate same-file record helper to a procedure`, then obtain independent
specification and quality PASS before continuing.

- [ ] **Step 4: Rerun design-plan runtime/parity and example route readiness**

```bash
pytest -q tests/test_workflow_lisp_key_migrations.py tests/test_workflow_lisp_migration_parity.py -k 'design_plan_impl_stack'
pytest -q tests/test_workflow_lisp_examples.py tests/test_workflow_lisp_route_readiness.py -k 'same_file_record_call_binding or design_plan_impl_review_stack'
```

- [ ] **Step 5: Record the two migrations and retained Step 1 disposition**

The pilot record is already in v2 history. Keep the Step 1
`tracked-design-phase` call active as `effect-adapter` with its eligibility-stop
evidence. Move exactly the two newly completed example call records from active `records` to
append-only `history` with `disposition: migrated`, completion commits, and
evidence selectors. Recompute active counts and history counts, retain the
design-stack `public-entry` negative as an active record, and keep the
same-file exported wrapper protected by its behavioral negative test.

```bash
python -m json.tool docs/plans/2026-07-13-procedure-first-reuse-inventory.json >/dev/null
git diff --check -- docs/plans/2026-07-13-procedure-first-reuse-inventory.json docs/plans/2026-07-13-procedure-first-reuse-inventory.md workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json
```

- [ ] **Step 6: Commit the reviewed inventory evidence**

```bash
git add docs/plans/2026-07-13-procedure-first-reuse-inventory.json docs/plans/2026-07-13-procedure-first-reuse-inventory.md workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json
git commit -m "Record example procedure migration evidence"
```

Stage only files that changed. Obtain specification and quality PASS on the
v2 history/count reconciliation before starting Task 3.

### Task 3: Migrate The Design Delta Library And Stdlib Adapters

**Files:**
- Modify: `workflows/library/lisp_frontend_design_delta/design_gap_architect.orc`
- Modify: `workflows/library/lisp_frontend_design_delta/selector.orc`
- Modify: `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc`
- Modify: `tests/test_workflow_lisp_design_delta_smoke.py`
- Modify: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Modify: `tests/test_workflow_lisp_source_map.py`
- Modify: `tests/test_workflow_lisp_checkpoint_identity_comparison.py`
- Modify: `docs/plans/2026-07-13-procedure-first-reuse-inventory.json`
- Modify: `docs/plans/2026-07-13-procedure-first-reuse-inventory.md`

- [ ] **Step 1: Resolve the seven candidate rows**

Resolve the four `design_gap_architect.orc` calls and three `stdlib_adapters.orc`
calls. Confirm each callee has no independent public-entry evidence. If any
owns a public/child-workflow identity, keep or reclassify its internal-call row
as `effect-adapter`, add or preserve a separate `public-entry` record classified
`public-boundary`, and do not migrate it.

The exact active IDs are:

- `stdlib_adapters.orc:select-next-work:1`;
- `stdlib_adapters.orc:draft-design-gap-architecture-stdlib:1`;
- `stdlib_adapters.orc:validate-design-gap-architecture-stdlib:1`;
- `design_gap_architect.orc:project-design-gap-architecture-targets:1` and `:2`;
- `design_gap_architect.orc:project-design-gap-architecture-targets-stdlib:1` and `:2`.

Use their full `internal-call:workflows/library/lisp_frontend_design_delta/...`
prefixes from the inventory when updating history.

- [ ] **Step 2: Migrate `stdlib_adapters.orc` first**

Run three independent RED/green cycles in this order: `select-next-work`,
`draft-design-gap-architecture-stdlib`, then
`validate-design-gap-architecture-stdlib`. Each RED test names the callee and
requires `defproc :lowering inline`, ordinary procedure application in the
adapter, retained public drain, and unchanged transitive effects. Convert only
that callee plus its adapter use, preserve explicit effects, run the focused
checks below, commit `Migrate Design Delta <callee> adapter to a procedure`,
and obtain independent specification and quality PASS before starting the
next callee.

```bash
pytest -q tests/test_workflow_lisp_design_delta_smoke.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_checkpoint_identity_comparison.py -k 'stdlib_adapter or design_delta'
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py -k 'procedure_first_design_delta_public_wrapper'
```

- [ ] **Step 3: Migrate `design_gap_architect.orc`**

Run two independent RED/green cycles: first
`project-design-gap-architecture-targets` and its two call IDs, then the
`-stdlib` callee and its two call IDs. Each RED test names both active IDs,
requires the callee to become `defproc :lowering inline`, and preserves the
imported module signature, artifacts, effect graph, source-map origins, state
roots, checkpoints, and resume behavior. Commit and obtain independent
specification/quality PASS after each callee group.

```bash
pytest -q tests/test_workflow_lisp_design_delta_smoke.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_checkpoint_identity_comparison.py -k 'design_gap_architect'
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py -k 'procedure_first_design_delta_public_wrapper'
```

- [ ] **Step 4: Run Design Delta integration without changing the public drain**

```bash
pytest -q tests/test_workflow_lisp_design_delta_smoke.py tests/test_workflow_lisp_generic_stdlib_composition.py tests/test_workflow_lisp_imported_stdlib_macro_payload_helper_composition.py tests/test_workflow_lisp_route_readiness.py
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
python -m orchestrator run workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json --input steering_path=docs/steering.md --input target_design_path=docs/design/workflow_lisp_runtime_native_drain_authoring.md --input baseline_design_path=docs/design/workflow_lisp_frontend_specification.md --input architecture_targets__design_gap_id=workflow-lisp-family1-promotion --input architecture_targets__architecture_path=docs/plans/2026-07-07-drain-migration-g8-retirement.md --input architecture_targets__work_item_context_path=artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R38/section14-parent-dry-run/work_item_context.md --input architecture_targets__check_commands_path=state/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/drain/iterations/4/design-gap-architect/check_commands.json --input architecture_targets__plan_target_path=docs/plans/2026-07-07-yaml-retirement-program.md --input existing_architecture_index_path=artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R38/section14-parent-dry-run/existing-architecture-index.md --dry-run
```

Expected: tests PASS, both CLI commands exit 0, and
`lisp_frontend_design_delta/drain::drain` remains an exported workflow. Rerun
the two CLI commands after every Task 3 source commit, not only at the final
integration step.

- [ ] **Step 5: Update history after the five reviewed source commits**

Move all seven disappeared active call records to v2 history with the exact
five source commit hashes and evidence, then recompute active/history counts.

```bash
python -m json.tool docs/plans/2026-07-13-procedure-first-reuse-inventory.json >/dev/null
git diff --check -- docs/plans/2026-07-13-procedure-first-reuse-inventory.json docs/plans/2026-07-13-procedure-first-reuse-inventory.md
git add docs/plans/2026-07-13-procedure-first-reuse-inventory.json docs/plans/2026-07-13-procedure-first-reuse-inventory.md
git commit -m "Record Design Delta library procedure evidence"
```

Obtain specification plus quality PASS before Task 4.

### Task 4: Reclassify The 25 YAML Effect-Adapter Rows From Evidence

**Files:**
- Modify: `docs/plans/2026-07-13-procedure-first-reuse-inventory.json`
- Modify: `docs/plans/2026-07-13-procedure-first-reuse-inventory.md`
- Modify: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Inspect exact YAML sources listed below; do not modify them in this task.

The ten reviewed groups are:

- `workflows/examples/dsl_follow_on_plan_impl_review_loop_v2_call.yaml` (2)
- `workflows/examples/lisp_frontend_autonomous_drain.yaml` (4)
- `workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml` (1)
- `workflows/examples/neurips_hybrid_resnet_plan_impl_review.yaml` (3)
- `workflows/examples/neurips_steered_backlog_drain.yaml` (3)
- `workflows/library/lisp_frontend_design_delta_done_review.v214.yaml` (2)
- `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml` (2)
- `workflows/library/lisp_frontend_work_item.v214.yaml` (2)
- `workflows/library/neurips_selected_backlog_item.v214.yaml` (3)
- `workflows/library/neurips_selected_backlog_item.yaml` (3)

- [ ] **Step 1: Audit one group at a time**

For each row record current callee resolution, public invocation/child-workflow role, provider/command/transition/publication effects, artifact ownership, source-map evidence, state/checkpoint identity, resume behavior, and whether an already-promoted `.orc` primary supersedes it.

- [ ] **Step 2: Apply only evidence-supported reclassifications**

- `legacy-retire`: when an accepted `.orc` primary already carries the behavior and the YAML row should retire rather than be translated.
- Keep or reclassify the internal call as `effect-adapter` when any named
  obligation remains unproven or fresh evidence shows that the callee owns an
  independent public/child-workflow identity. For the latter case, add or
  preserve a separate `public-entry` record classified `public-boundary`.

These 25 YAML rows must never become `procedure-candidate`: Task 4 does not
translate YAML, and that classification is reserved for a current `.orc`
internal call site. If fresh evidence discovers a live `.orc` candidate, add
its own current-source inventory record and route it to a bounded, reviewed
source-migration task before Task 8; do not transfer the YAML row's identity.
Every changed row must include evidence paths/selectors and an updated reason;
never infer classification merely from a matching filename. Internal-call rows
must never use `public-boundary`.

- [ ] **Step 3: Test counts, vocabulary, and public negatives**

```bash
python -m json.tool docs/plans/2026-07-13-procedure-first-reuse-inventory.json >/dev/null
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py -k 'inventory or public_boundary or effect_adapter'
git diff --check -- docs/plans/2026-07-13-procedure-first-reuse-inventory.json docs/plans/2026-07-13-procedure-first-reuse-inventory.md tests/test_workflow_lisp_procedure_first_migrations.py
```

- [ ] **Step 4: Commit each audited family group separately**

```bash
git add docs/plans/2026-07-13-procedure-first-reuse-inventory.json docs/plans/2026-07-13-procedure-first-reuse-inventory.md tests/test_workflow_lisp_procedure_first_migrations.py
git commit -m "Reclassify <family> reuse boundaries"
```

After each commit, obtain independent specification and quality PASS for that
group's evidence, active/history counts, and retained public negatives before
auditing the next group. Do not combine NeurIPS, Design Delta, and generic
example groups in one review/commit.

### Task 5: Migrate The Production Work-Item Family

**Files:**
- Modify: `workflows/library/lisp_frontend_design_delta/bootstrap.orc`
- Modify: `workflows/library/lisp_frontend_design_delta/implementation_phase.orc`
- Modify: `workflows/library/lisp_frontend_design_delta/plan_phase.orc`
- Modify: `workflows/library/lisp_frontend_design_delta/projections.orc`
- Modify: `workflows/library/lisp_frontend_design_delta/work_item.orc`
- Modify: `tests/test_workflow_lisp_design_delta_smoke.py`
- Modify: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Modify: `tests/test_workflow_lisp_source_map.py`
- Modify: `tests/test_workflow_lisp_checkpoint_identity_comparison.py`
- Modify: `tests/test_workflow_lisp_key_migrations.py`
- Modify: `tests/test_workflow_lisp_migration_parity.py`
- Modify: `docs/plans/2026-07-13-procedure-first-reuse-inventory.json`
- Modify: `docs/plans/2026-07-13-procedure-first-reuse-inventory.md`

- [ ] **Step 1: Split the 21 calls into independently testable subfamilies**

Use enclosing definition/import resolution to produce and review this order before editing:

1. finalizer projections: `project-selected-item-finalizer-approved-plan:1/2`,
   `project-selected-item-finalizer-completed-implementation:1`, and
   `project-selected-item-finalizer-blocked-implementation:1`;
2. blocked recovery/finalization: `classify-blocked-implementation-recovery:1`
   and `finalize-selected-item-from-blocked-implementation:1` through `:5`;
3. phase orchestration: `project-work-item-inputs:1/2`, `run-plan-phase:1/2`,
   `implementation-phase:1/2`, `classify-work-item-terminal:1/2`, and
   `run-work-item-pending:1`; and
4. completed finalization:
   `finalize-selected-item-from-completed-implementation:1/2`.

Each shorthand has the full prefix
`internal-call:workflows/library/lisp_frontend_design_delta/work_item.orc:`.
These four groups reconcile exactly 4 + 6 + 9 + 2 = 21 active IDs.

Any call whose callee owns an independent public, publication, or checkpoint
namespace is not migrated: retain the internal-call row as `effect-adapter`
and add or preserve the callee's separate `public-entry` record classified
`public-boundary`.

- [ ] **Step 2: Migrate one subfamily at a time with RED parity tests**

For each group, add a RED test named for that group which enumerates its exact
IDs, requires the resolved callee definitions to be
`defproc :lowering inline`, rejects remaining workflow-call nodes for those
IDs, and asserts that exported `run-work-item` remains the public workflow.
`run-work-item-pending` is a phase-orchestration procedure candidate. If fresh
evidence proves it owns an independent public identity, retain it as a workflow,
reclassify its internal-call row to `effect-adapter`, and add or preserve its
separate `public-entry` record classified `public-boundary`.
Verify the test fails on the first still-workflow callee. Make only the group's
source change. Every source commit must keep public work-item
inputs/outputs, artifact names, effects, state/write roots, checkpoint IDs,
and resume behavior equal. Transition/finalization procedures must retain
their declared command/resource/ledger effects in Semantic IR.

```bash
pytest -q tests/test_workflow_lisp_design_delta_smoke.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_checkpoint_identity_comparison.py -k 'work_item'
```

- [ ] **Step 3: Run runtime and family parity after each subfamily**

```bash
pytest -q tests/test_workflow_lisp_key_migrations.py tests/test_workflow_lisp_migration_parity.py -k 'design_delta or work_item'
pytest -q tests/test_workflow_lisp_resource_transition_runtime.py tests/test_workflow_lisp_materialize_view_runtime.py -k 'design_delta or work_item or finalize'
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py -k 'procedure_first_design_delta_public_wrapper'
```

Expected: PASS. Do not batch the next subfamily if resume or checkpoint evidence is absent.

Also compile and dry-run the retained production owner after each group using
the fully qualified Design Delta drain command from Task 6. A group does not
advance on focused unit tests alone.

- [ ] **Step 4: Commit each subfamily separately**

```bash
git add workflows/library/lisp_frontend_design_delta/bootstrap.orc workflows/library/lisp_frontend_design_delta/implementation_phase.orc workflows/library/lisp_frontend_design_delta/plan_phase.orc workflows/library/lisp_frontend_design_delta/projections.orc workflows/library/lisp_frontend_design_delta/work_item.orc tests/test_workflow_lisp_design_delta_smoke.py tests/test_workflow_lisp_procedure_first_migrations.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_checkpoint_identity_comparison.py tests/test_workflow_lisp_key_migrations.py tests/test_workflow_lisp_migration_parity.py
git commit -m "Migrate Design Delta work-item <subfamily> procedures"
```

Replace `<subfamily>` successively with `finalizer-projections`,
`blocked-recovery`, `phase-orchestration`, and `completed-finalization`; never
use one bulk commit. After each commit, obtain independent specification and
quality PASS for the exact ID group before starting the next.

- [ ] **Step 5: Update inventory in a separate evidence commit**

Move exactly 21 disappeared records into v2 history with their four source
commit hashes, reconcile 4/6/9/2 group counts, and attach evidence selectors.

```bash
python -m json.tool docs/plans/2026-07-13-procedure-first-reuse-inventory.json >/dev/null
git add docs/plans/2026-07-13-procedure-first-reuse-inventory.json docs/plans/2026-07-13-procedure-first-reuse-inventory.md
git commit -m "Record work-item procedure migration evidence"
```

Obtain specification plus quality PASS before Task 6.

### Task 6: Migrate The Internal Drain Builder Without Removing The Public Drain

**Files:**
- Modify: `workflows/library/lisp_frontend_design_delta/drain.orc`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_design_delta_smoke.py`
- Modify: `tests/test_workflow_lisp_migration_parity.py`
- Modify: `tests/test_workflow_lisp_checkpoint_identity_comparison.py`
- Modify: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Modify: `docs/plans/2026-07-13-procedure-first-reuse-inventory.json`
- Modify: `docs/plans/2026-07-13-procedure-first-reuse-inventory.md`

- [ ] **Step 1: Write RED positive and negative tests together**

Require `build-drain-runtime-owned` to become `defproc :lowering inline` only if its internal call has full parity. Simultaneously require `lisp_frontend_design_delta/drain::drain` to remain exported, externally invocable, resumable, and publication-owning.

Add two fresh production-route tests to
`tests/test_workflow_lisp_procedure_first_migrations.py`:

- `test_internal_drain_builder_migration_runs_public_entry_with_equal_outputs_artifacts_and_publication` executes the retained `.orc` public entry through the deterministic provider/command harness and compares a clean run with the pre-migration semantic baseline; and
- `test_internal_drain_builder_migration_resumes_same_public_run_without_replaying_completed_effects` fails after one committed effect, resumes the same `run_id`, and asserts completed effects are reused, checkpoint/presentation IDs are unchanged, and final public output/artifacts match the clean run.

Both tests also require the inline procedure shape, so they fail before the
source conversion rather than passing as characterization-only tests.

- [ ] **Step 2: Migrate the one candidate and preserve exact checkpoint identity**

Convert the one inventory row. Do not migrate the public `drain`, change its entry name, or rewrite checkpoint baselines to accept a new identity.

- [ ] **Step 3: Run strict drain evidence**

```bash
pytest -q tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_design_delta_smoke.py tests/test_workflow_lisp_checkpoint_identity_comparison.py -k 'design_delta and drain'
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py -k 'internal_drain_builder_migration'
python -m json.tool artifacts/work/review-parity-check/design_delta_parent_drain.json >/dev/null
pytest -q tests/test_workflow_lisp_design_delta_smoke.py tests/test_workflow_lisp_route_readiness.py -k 'design_delta or parent_drain'
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
python -m orchestrator run workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json --input steering_path=docs/steering.md --input target_design_path=docs/design/workflow_lisp_runtime_native_drain_authoring.md --input baseline_design_path=docs/design/workflow_lisp_frontend_specification.md --input architecture_targets__design_gap_id=workflow-lisp-family1-promotion --input architecture_targets__architecture_path=docs/plans/2026-07-07-drain-migration-g8-retirement.md --input architecture_targets__work_item_context_path=artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R38/section14-parent-dry-run/work_item_context.md --input architecture_targets__check_commands_path=state/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/drain/iterations/4/design-gap-architect/check_commands.json --input architecture_targets__plan_target_path=docs/plans/2026-07-07-yaml-retirement-program.md --input existing_architecture_index_path=artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R38/section14-parent-dry-run/existing-architecture-index.md --dry-run
```

Expected: the preserved historical promotion report parses and remains the
decision record; fresh production-owner smoke, route-readiness, and compile
checks pass with unchanged public boundary,
output/artifact/publication/effect/source-map/checkpoint/resume contracts. Do
not recreate or select the retired `design_delta_parent_drain` parity target.

- [ ] **Step 4: Commit and review the source migration**

```bash
git add workflows/library/lisp_frontend_design_delta/drain.orc tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_design_delta_smoke.py tests/test_workflow_lisp_migration_parity.py tests/test_workflow_lisp_checkpoint_identity_comparison.py tests/test_workflow_lisp_procedure_first_migrations.py
git commit -m "Migrate the internal drain builder to a procedure"
```

Obtain independent specification and quality PASS here. Fix and rerun the
source/runtime/resume checks before recording inventory evidence.

- [ ] **Step 5: Record reviewed history evidence**

Move the one disappeared builder-call record to v2 history with the reviewed
source commit and runtime/resume evidence, then recompute active/history
counts.

```bash
python -m json.tool docs/plans/2026-07-13-procedure-first-reuse-inventory.json >/dev/null
git add docs/plans/2026-07-13-procedure-first-reuse-inventory.json docs/plans/2026-07-13-procedure-first-reuse-inventory.md
git commit -m "Record internal drain procedure evidence"
```

Obtain specification plus quality PASS on the history/count update.

### Task 7: Hand Legacy Rows To Stage 6 Without Translating Them

**Files:**
- Modify: `docs/plans/2026-07-07-yaml-retirement-program.md`
- Modify: `docs/workflow_yaml_estate_triage.md`
- Modify: `docs/plans/2026-07-13-procedure-first-reuse-inventory.json`
- Modify: `docs/plans/2026-07-13-procedure-first-reuse-inventory.md`
- Test: `tests/test_workflow_lisp_procedure_first_migrations.py`

- [ ] **Step 1: Reconcile all 38 legacy-retire rows and newly reclassified rows**

For each YAML family, name its retained public `.orc` replacement or deletion rationale, parity evidence, external-reference search, archive destination, and Stage 6 task/gate. A `legacy-retire` call site is not proof that its containing file may be deleted.

- [ ] **Step 2: Add Stage 6 queue entries only**

Update the YAML retirement plan/triage with bounded family queues and prerequisites. Do not delete, archive, rename, or flip a primary in this task.

- [ ] **Step 3: Prove no live reference is silently removed**

```bash
rg -n 'workflows/(examples|library)/.*\.yaml' docs workflows tests README.md
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py -k 'legacy_retire or retirement_handoff'
python -m json.tool docs/plans/2026-07-13-procedure-first-reuse-inventory.json >/dev/null
git diff --check -- docs/plans/2026-07-07-yaml-retirement-program.md docs/workflow_yaml_estate_triage.md docs/plans/2026-07-13-procedure-first-reuse-inventory.json docs/plans/2026-07-13-procedure-first-reuse-inventory.md tests/test_workflow_lisp_procedure_first_migrations.py
```

- [ ] **Step 4: Commit the handoff**

```bash
git add docs/plans/2026-07-07-yaml-retirement-program.md docs/workflow_yaml_estate_triage.md docs/plans/2026-07-13-procedure-first-reuse-inventory.json docs/plans/2026-07-13-procedure-first-reuse-inventory.md tests/test_workflow_lisp_procedure_first_migrations.py
git commit -m "Route compatibility workflows to YAML retirement"
```

### Task 8: Close The Migration-Wave Gate

**Files:**
- Modify only after all reviews pass: `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
- Modify only after all reviews pass: `docs/capability_status_matrix.md`
- Modify only after all reviews pass: `docs/index.md`

- [ ] **Step 1: Validate the final inventory**

```bash
python -m json.tool docs/plans/2026-07-13-procedure-first-reuse-inventory.json >/dev/null
rg -n --glob '*.orc' '\(call\s+' workflows | sort
rg -n --glob '*.yaml' --glob '*.yml' '^[[:space:]-]*call:[[:space:]]' workflows | sort
```

Every current direct call is either resolved by a completed migration, retained as a reviewed public/effect boundary, or assigned to a specific Stage 6 retirement family.

- [ ] **Step 2: Run focused route, parity, source-map, checkpoint, and runtime suites**

```bash
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py tests/test_workflow_lisp_route_readiness.py tests/test_workflow_lisp_migration_parity.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_checkpoint_identity_comparison.py tests/test_workflow_lisp_key_migrations.py tests/test_workflow_lisp_design_delta_smoke.py
```

Expected: PASS.

- [ ] **Step 3: Run the broad suite in tmux**

Use the `tmux` skill:

```bash
pytest -q -n 16 --dist=worksteal
```

Expected: PASS except only established unrelated failures with fresh isolated reruns and explicit disposition.

- [ ] **Step 4: Obtain independent per-family and whole-wave reviews**

Each family needs specification and quality passes before the next begins. The final reviews check all inventory records, retained public negatives, effect-adapter evidence, migration parity, YAML-retirement handoff, stop-condition compliance, and absence of shared substrate changes in family commits.

- [ ] **Step 5: Advance routing only after the gate passes**

Record exact completed/migrated/retained/retirement counts, review evidence, and the next Stage 6 selector. Do not describe procedure-first adoption as universal if any effect-adapter remains.

```bash
git add docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md docs/capability_status_matrix.md docs/index.md
git commit -m "Close procedure-first migration waves"
```

## Global stop conditions

Stop the active family and do not start the next one when:

- a public invocation, child-workflow, run/resume, publication, or operator-visible boundary would disappear;
- exact persisted checkpoint/resume identity cannot be preserved;
- resume projection-integrity hardening design, implementation-plan, runtime
  implementation, or independent-review completion evidence is absent;
- an effect is absent from the recomputed caller-visible summary or Semantic IR;
- parity requires accepting a new output, artifact, terminal, source-map, state-root, or resume difference not already reviewed;
- a family needs compiler/runtime substrate, dynamic dispatch, runtime procedure values, or a new DSL contract;
- a YAML replacement is not promoted and independently evidenced; or
- the inventory cannot identify a current call site reproducibly.

Leave such an internal-call row `effect-adapter`; when the blocker is an
independent public identity, add or preserve its separate `public-entry` record
classified `public-boundary`. Record the blocker and evidence, and write a
separate reviewed plan. Never weaken a test, rewrite an identity baseline, or
broaden a family commit to force the wave forward.
