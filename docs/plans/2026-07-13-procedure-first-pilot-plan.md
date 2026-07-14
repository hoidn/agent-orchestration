# Procedure-First Tracked Plan Phase Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** paused. Identity-compatibility Tasks 1-6 are implemented, but the
prerequisite plan's Task 8 full verification and independent reviews have not
yet passed. Do not select or make a pilot source edit while paused.

**Goal:** Convert only the internal `tracked-plan-phase` in `design_plan_impl_review_stack_v2_call.orc` from a workflow call to an inline typed procedure while retaining `design-plan-impl-review-stack` as the public boundary and proving full executable parity.

**Architecture:** Retain the frozen pre-change contract snapshot for the public
entry, then, only after the pre-edit evidence gate passes, make the smallest
source migration: `tracked-plan-phase` becomes `defproc :lowering inline`, and
its one caller uses an ordinary positional procedure call. The public wrapper
continues to own inputs, outputs, artifacts, effects, state, effect-owned
checkpoints, source maps, and runtime execution. Public identities remain
strict; eligible old internal call-boundary identities may be retired only by
the reviewed evidence path defined below.

**Tech Stack:** Workflow Lisp `.orc`, WCC compiler, executable and Semantic IR, source maps, migration parity tooling, orchestrator CLI, pytest.

---

## Authority, prerequisites, and boundaries

- Accepted contract: `docs/design/workflow_lisp_procedure_first_reuse_contract.md`
- Accepted identity compatibility clarification:
  `docs/design/workflow_lisp_procedure_migration_identity_compatibility.md`
- Current prerequisite plan:
  `docs/plans/2026-07-13-procedure-migration-identity-compatibility-plan.md`
- Reviewed inventory row: `internal-call:workflows/examples/design_plan_impl_review_stack_v2_call.orc:tracked-plan-phase:1` in `docs/plans/2026-07-13-procedure-first-reuse-inventory.json`
- Existing family target: `design_plan_impl_stack` in `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- The following earlier prerequisites are complete:
  1. `docs/plans/2026-07-10-workflow-lisp-typed-result-guidance-plan.md` is complete; and
  2. `docs/plans/2026-07-13-procedure-first-substrate-gaps-plan.md` is complete and reviewed.
- Identity-compatibility prerequisite Tasks 1-6 are implemented in commits
  `d5eb0043` through `e4f2ecbe`. The frozen pilot source and old baseline have
  not been refreshed. Remain paused until Task 8 reruns the focused selectors,
  broad suite, smoke check, and independent specification/runtime-state and
  quality reviews, then records its final handoff.
- When resumed, this plan owns the genuine named-owner attestations for every
  known state store and either proves strict compatibility or applies the
  accepted reviewed internal identity-retirement exception. Missing,
  ambiguous, public/exported, promoted/live, or supported-consumer evidence
  stops the pilot without a source edit. A retirement record is evidence only
  and makes no old-state remap or cross-source resume claim.
- Modify no phase except `tracked-plan-phase`; `tracked-design-phase` and `design-plan-impl-implementation-phase` remain workflows for later waves.
- Retain the exported public `design-plan-impl-review-stack` workflow. Do not export the pilot procedure or register it as a workflow entry.
- Do not edit the YAML twin or archive anything in this plan. Stage 6 owns YAML retirement.
- Any public checkpoint/resume identity, public output, artifact, publication,
  effect, or source-map loss is a stop condition. An unreviewed or ineligible
  internal identity change also stops. Only an old internal identity accepted
  by the validated `reviewed_internal_identity_retirement` record may differ;
  that exception does not relax any other parity axis.

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

## File responsibility map

- `workflows/examples/design_plan_impl_review_stack_v2_call.orc`: the one family source edit.
- `tests/baselines/procedure_first/tracked_plan_phase.json`: reviewed pre-migration public/runtime contract, including the internal phase route that must be preserved or explicitly proven irrelevant.
- `tests/test_workflow_lisp_procedure_first_migrations.py`: exact before/after contract comparison and retained-public-boundary negative test.
- `tests/test_workflow_lisp_key_migrations.py`: existing compile and one-pass runtime smoke, extended only where the procedure route needs an assertion.
- `tests/test_workflow_lisp_migration_parity.py`: existing family parity/report gate; change only if the report lacks procedure-first evidence fields.
- `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`: existing commands and evidence roles; change only if a new named selector is required.
- `docs/workflow_lisp_route_readiness_registry.json`: change evidence references only after the pilot passes; do not promote the example's copy-safety.

## Mandatory pre-edit retirement gate

This gate runs before Task 2 and before any edit to the pilot `.orc` source.
It is not satisfied by earlier repository inspection or by a zero-match scan
of only the current workspace.

1. Confirm the identity-compatibility plan's Task 8 final handoff. Its fresh
   evidence must include the focused selectors for:
   - generic identity characterization and one-time Stage-3 resolution in
     `tests/test_workflow_lisp_procedures.py` and
     `tests/test_workflow_lisp_build_artifacts.py`;
   - inline checkpoint ownership in
     `tests/test_workflow_lisp_lexical_checkpoints.py`;
   - WCC inline provenance in `tests/test_workflow_lisp_source_map.py` and
     `tests/test_workflow_lisp_build_artifacts.py`;
   - the complete retirement validator suite in
     `tests/test_workflow_lisp_procedure_identity_retirement.py`; and
   - root/callee checksum characterization in `tests/test_resume_command.py`.
   Task 8's independent reviews must approve those prerequisite contracts;
   passing Tasks 1-6 selectors without the final reviews does not authorize a
   source edit.
2. Derive the old identity query from the unchanged
   `tests/baselines/procedure_first/tracked_plan_phase.json` and retained old
   source/build artifacts, and verify their content digests before editing.
   Enumerate the repository workspace
   `.orchestrate/runs` root and every other workspace or run root intentionally
   used for this example as separate prospective `known_state_stores` entries.
   Do not combine roots or treat a parent directory as proof about an
   unenumerated child store.
3. For every enumerated root call
   `scan_known_state_store(root, retired_identities=old_identities,
   query_version="procedure-identity-store-query.v1")`. Record the query time
   alongside the returned `normalized_scan_digest`,
   terminal/nonterminal/call-frame/consumer counts,
   checkpoint-index/checkpoint-record counts, retained-manifest and
   identity-metadata counts, and scanned-file count. Set
   `external_store_absence: not_asserted`. EasySpin, PtychoPINN, the paper
   repository, CI artifacts, backups, and copied workspaces remain unknown
   unless each concrete root is individually enumerated and scanned.
4. After each scan, obtain from a genuine named human owner of that exact store
   an independently attributable timestamped attestation that no supported
   live/nonterminal run or consumer of the queried old identities remains
   there. An agent must never synthesize, guess, default, paraphrase, or sign
   an owner name or attestation.
5. If any owner or attestation is missing, ambiguous, or not independently
   attributable, record exactly
   `STOP: missing known-store owner attestation`, keep
   `strict_compatibility` selected, and end without asking, retrying, editing
   source, or fabricating evidence under the standing unattended instruction.
   Any supported live/nonterminal run or consumer likewise selects strict
   compatibility and ends the source-edit path.

Only after all five steps pass may Task 2 make its one `.orc` edit. After that
edit, build content-addressed new artifacts while retaining the old source,
old build artifacts, frozen baseline, and pre-edit store evidence. Complete
the full old/new identity delta, keyed artifact-contract multiset, separate
execution-order comparison, new-ID clean-run and interruption/resume evidence,
and both checksum negative proofs. Validate the assembled record and obtain
independent specification and runtime-state approval before accepting any
retired identity. The record is evidence only, is never supplied to run or
resume, and makes no claim that an old run resumes across changed source.

### Task 1: Freeze The Pre-Migration Contract And Write RED Tests

**Execution note:** Completed by commit `453ad2f9`. The checked-in old baseline
and original-source observations are retained evidence. Do not regenerate,
refresh, or reinterpret them under the new source.

**Files:**
- Create: `tests/baselines/procedure_first/tracked_plan_phase.json`
- Create: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Inspect: `tests/test_workflow_lisp_key_migrations.py`
- Inspect: `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`

- [x] **Step 1: Capture the baseline from the unmodified source**

Compile `design-plan-impl-review-stack` through `compile_stage3_entrypoint` with the existing provider/prompt extern JSON files and empty command boundaries. Serialize stable, semantic fields only:

- public entry/module identity and exported workflow set;
- public inputs/defaults and output contracts;
- artifacts and publication refs;
- terminal outcome and lowered step order;
- caller-visible effect kinds/subjects;
- source-map origin keys and expansion/call-site lineage;
- state-layout write roots;
- runtime-plan checkpoint IDs, presentation keys, kinds, and resume identity hints; and
- the `tracked-plan-phase` call/procedure route needed to compare the migration.

Do not snapshot whole debug YAML or unstable object reprs.

- [x] **Step 2: Write the RED source-shape test**

Assert the module has exactly one exported `defworkflow`, `design-plan-impl-review-stack`; `tracked-plan-phase` is a `defproc` with requested/resolved lowering `inline`; and the public wrapper contains a procedure call rather than a child-workflow call for that phase.

- [x] **Step 3: Write the RED contract-comparison test**

Compile the checked-in source and compare its stable
public/output/artifact/effect/source-map/state/checkpoint/resume projection to
`tracked_plan_phase.json`. The frozen test records the old route; after the
source edit, compare it through the validated retirement evidence rather than
refreshing it. Require all public identities and every old identity not
explicitly classified as an eligible reviewed retirement to remain equal.

- [x] **Step 4: Run RED tests**

```bash
pytest --collect-only -q tests/test_workflow_lisp_procedure_first_migrations.py
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py -k 'tracked_plan_phase'
```

Expected: collection succeeds; source-shape and route assertions FAIL because `tracked-plan-phase` is still a `defworkflow` called with `call`.

- [x] **Step 5: Commit baseline and RED tests**

```bash
git add tests/baselines/procedure_first/tracked_plan_phase.json tests/test_workflow_lisp_procedure_first_migrations.py
git commit -m "test: freeze tracked plan procedure pilot parity"
```

### Task 2: Convert Only `tracked-plan-phase`

**Files:**
- Modify: `workflows/examples/design_plan_impl_review_stack_v2_call.orc`
- Test: `tests/test_workflow_lisp_procedure_first_migrations.py`

- [ ] **Step 1: Change the definition to an explicit inline procedure**

Do not begin this step until the Mandatory pre-edit retirement gate has passed.

Make the definition header equivalent to:

```lisp
(defproc tracked-plan-phase
  ((design_path DesignDocPath)
   (plan_target_path PlanDocTarget)
   (plan_review_report_target_path ReviewReportTarget))
  -> PlanPhaseOutput
  :effects ((uses-provider providers.plan.draft)
            (uses-provider providers.plan.review))
  :lowering inline
  ...)
```

Preserve its body and typed `PlanPhaseOutput` return exactly.

- [ ] **Step 2: Replace only its caller**

Replace the keyword `call` form with the positional procedure application:

```lisp
(tracked-plan-phase
  design.design_path
  plan_target_path
  plan_review_report_target_path)
```

Do not change the other two `(call ...)` forms.

- [ ] **Step 3: Run the source and compile parity tests**

```bash
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py -k 'tracked_plan_phase'
pytest -q tests/test_workflow_lisp_key_migrations.py -k 'design_plan_impl_stack_orc_compiles_with_phase_family_contracts'
```

Expected: PASS. The lowered workflow-name assertion in the existing key-migration test may need to distinguish the one removed internal workflow from the retained public and two untouched phase workflows; update that assertion, not the contract.

- [ ] **Step 4: Commit the one-phase migration**

```bash
git add workflows/examples/design_plan_impl_review_stack_v2_call.orc tests/test_workflow_lisp_procedure_first_migrations.py tests/test_workflow_lisp_key_migrations.py
git commit -m "Migrate tracked plan phase to an inline procedure"
```

### Task 3: Prove Runtime, Artifact, Checkpoint, And Resume Parity

**Files:**
- Modify: `tests/test_workflow_lisp_key_migrations.py`
- Modify only if a missing comparison is proven: `tests/test_workflow_lisp_procedure_first_migrations.py`

- [ ] **Step 1: Extend the existing single-pass runtime smoke**

Keep `_execute_design_plan_impl_stack_single_pass_runtime` as the family harness. Assert the completed public output has the same nine fields and values, the plan and review artifacts are created at the same caller-supplied paths, and no private/generated workflow entry named for `tracked-plan-phase` is externally invocable.

- [ ] **Step 2: Add a new-ID resume-after-plan-provider-boundary test**

Use the existing deterministic fake provider harness and `StateManager` to
start a run from the new source. Fail once after the plan draft/review
boundary, resume that new-source run with the same `run_id`, and assert already
completed provider work is reused and the final public output and artifacts
match a clean new-source run. Compare checkpoint IDs and presentation keys to
the full old/new identity delta: public and preserved entries remain exact;
only validator-approved retired internal entries may be absent, and new
effect-owned entries must be classified explicitly.

- [ ] **Step 3: Run runtime and resume tests**

```bash
pytest -q tests/test_workflow_lisp_key_migrations.py -k 'design_plan_impl_stack'
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py -k 'checkpoint or resume or artifact or public_boundary'
```

Expected: PASS.

- [ ] **Step 4: Stop on an unreviewed or ineligible identity mismatch**

If inline lowering changes a public identity, an identity classified as
preserved, or any internal identity outside the reviewed retirement class,
stop. Also stop if the new-source run cannot resume under its new identities.
Do not update the old baseline, claim cross-source old-run resume, or add an
implicit remap. Eligible internal call-boundary retirement proceeds only
through the complete validated record, substantive repository/store evidence,
root and callee checksum negatives, keyed artifact comparison, separate order
review, and independent approvals.

- [ ] **Step 5: Commit runtime evidence**

```bash
git add tests/test_workflow_lisp_key_migrations.py tests/test_workflow_lisp_procedure_first_migrations.py
git commit -m "Prove tracked plan procedure runtime parity"
```

### Task 4: Run Compile, Dry-Run, Semantic, And Family Parity Gates

**Files:**
- Modify only if a new evidence selector is required: `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- Modify only if the existing report cannot express the evidence: `tests/test_workflow_lisp_migration_parity.py`
- Refresh generated evidence: `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/`
- Modify after evidence passes: `docs/workflow_lisp_route_readiness_registry.json`

- [ ] **Step 1: Compile through the production route**

```bash
python -m orchestrator compile workflows/examples/design_plan_impl_review_stack_v2_call.orc --entry-workflow design-plan-impl-review-stack --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.commands.json --emit-semantic-ir .orchestrate/tmp/procedure-first-pilot/semantic_ir.json --emit-source-map .orchestrate/tmp/procedure-first-pilot/source_map.json
```

Expected: exit 0; emitted Semantic IR includes both plan provider effects under the public entry, and the source map attributes them to `tracked-plan-phase` plus its consuming call site.

- [ ] **Step 2: Dry-run the retained public wrapper**

```bash
python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.orc --entry-workflow design-plan-impl-review-stack --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.commands.json --input brief_path=workflows/examples/inputs/major_project_brief.md --input design_target_path=docs/plans/parity-design.md --input design_review_report_target_path=artifacts/review/parity-design-review.md --input plan_target_path=docs/plans/parity-plan.md --input plan_review_report_target_path=artifacts/review/parity-plan-review.md --input execution_report_target_path=artifacts/work/parity-execution.md --input implementation_review_report_target_path=artifacts/review/parity-implementation-review.md --dry-run
```

Expected: exit 0.

- [ ] **Step 3: Rerun the existing family parity gate**

```bash
python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity --target design_plan_impl_stack
pytest -q tests/test_workflow_lisp_migration_parity.py -k 'design_plan_impl_stack'
```

Expected: the `design_plan_impl_stack` row passes compile, dry-run, runtime, artifact, output, and resume evidence. Do not alter unrelated target rows.

- [ ] **Step 4: Update route evidence without promotion**

Add the new procedure-first comparison selector to the existing route-readiness entry. Keep `route_label: migration_candidate`, `readiness_label: leaf_runtime_candidate`, and `copy_safety: migration_evidence_only` unchanged.

- [ ] **Step 5: Commit evidence routing**

```bash
git add workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json tests/test_workflow_lisp_migration_parity.py artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.md artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json docs/workflow_lisp_route_readiness_registry.json
git commit -m "Record tracked plan procedure pilot evidence"
```

Stage only the listed files that actually changed; never stage the parity
directory wholesale.

### Task 5: Complete The Pilot Gate

**Files:**
- No expected source changes.

- [ ] **Step 1: Run focused collection and integration suites**

```bash
pytest --collect-only -q tests/test_workflow_lisp_procedure_first_migrations.py tests/test_workflow_lisp_key_migrations.py tests/test_workflow_lisp_migration_parity.py
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py tests/test_workflow_lisp_key_migrations.py tests/test_workflow_lisp_migration_parity.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_checkpoint_identity_comparison.py tests/test_workflow_lisp_route_readiness.py
```

Expected: PASS.

- [ ] **Step 2: Run the broad suite in tmux**

Use the `tmux` skill:

```bash
pytest -q -n 16 --dist=worksteal
```

Expected: PASS except only established unrelated failures with fresh isolated reruns and explicit disposition.

- [ ] **Step 3: Review scope and public-negative preservation**

```bash
git diff --check HEAD~4..HEAD
git diff HEAD~4..HEAD -- workflows/examples/design_plan_impl_review_stack_v2_call.orc
rg -n '^  \(export|^  \(defworkflow|^  \(defproc tracked-plan-phase|\(call tracked-plan-phase' workflows/examples/design_plan_impl_review_stack_v2_call.orc
```

Expected: only `tracked-plan-phase` and its one call changed; `design-plan-impl-review-stack` remains the sole export/public workflow; no `(call tracked-plan-phase` remains.

- [ ] **Step 4: Obtain independent specification and quality reviews**

Specification review must check every migration-test axis in the accepted contract. Quality review must check that the baseline is semantic rather than textual, the runtime test is non-tautological, and no Stage 6 retirement leaked into the pilot. Resolve findings and rerun both reviews whole.

## Completion gate and stop conditions

The pilot is complete only when the mandatory pre-edit scans and genuine
owner attestations passed before the source edit; the complete retirement
record validates; the source-shape test, stable contract and keyed artifact
comparisons, separate execution-order review, new-ID one-pass runtime and
resume test, both checksum negatives, compile, dry-run, family parity, focused
suites, broad suite, and independent specification/runtime-state and quality
reviews pass. Retained old artifacts and the frozen baseline must still be
content-addressed and readable.

Stop without widening scope if:

- public `design-plan-impl-review-stack` inputs, outputs, artifacts, terminal behavior, or invocation identity change;
- either plan provider effect disappears from the caller-visible effect graph or Semantic IR;
- source-map lineage loses the procedure definition or consuming call site;
- any public or preserved checkpoint/resume identity changes, or an internal
  identity changes without validator-approved substantive eligibility,
  pre-edit scans and attestations, checksum negatives, artifact/order review,
  and independent approval;
- any known-store owner attestation is missing, ambiguous, unattributable, or
  agent-authored, or external-store absence is inferred rather than recorded
  as `not_asserted`;
- the root changed-source negative reaches executor construction or mutates
  the persisted run tree, or the callee negative reaches child execution or
  remaps child state;
- the migration requires changing another phase, the YAML twin, the runtime result transport, or the public DSL version; or
- the parity tool cannot distinguish the reviewed structural delta from a public contract regression.
