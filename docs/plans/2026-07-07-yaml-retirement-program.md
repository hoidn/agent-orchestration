# User-Facing YAML Retirement Program (Stage 6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to execute this plan task by task.
> Use TDD for implementation changes and obtain specification and code-quality
> review at every review gate.

**Goal:** Retire YAML and YML as user-facing workflow-authoring formats. `.orc`
becomes the only authored workflow surface. Persisted run data and internal
debug serialization are outside this program.

**Architecture:** The content-addressed handoff in
`docs/plans/2026-07-13-procedure-first-reuse-inventory.json` is the exact work
list. It partitions every authored YAML/YML path into five queues: two ports,
one protected holdout, one Design Delta historical archive, and deletion of the
remaining estate. Shared validation remains available to the `.orc` frontend
and persisted-run compatibility after the YAML parser is removed.

**Steering decision:** Retirement is deletion-first. The only workflows that
receive new `.orc` ports are `verified_iteration_drain` and
`generic_run_watchdog`. The seven demoted Design Delta YAML twins are preserved
only through content-addressed git history before deletion. The protected
non-progress step-back workflow stays held until its owner records a
disposition. Every other authored YAML/YML file is deleted after the reference
and supported-run gates pass. The `delete_non_survivor_estate` queue is an
early independent tranche: Stage 6 may execute it as soon as its own gates and
reviews pass, without waiting for Tasks 1–5 or either new port. The Design
Delta archive remains ordered after that deletion queue.

## Entry gate

- `docs/plans/2026-07-13-procedure-first-reuse-inventory.json` contains a
  validated `yaml_retirement_handoff` at schema version
  `procedure_first_yaml_retirement_handoff.v1`.
- `docs/workflow_yaml_estate_triage.md` is an exact human-readable projection
  of the handoff, not an independently maintained work list.
- Re-validate both with
  `tests/test_workflow_lisp_procedure_first_migrations.py` before mutating a
  workflow.

## Global constraints

- Run all commands from the repository root.
- Stage explicit paths only; never use broad staging commands.
- Do not create worktrees.
- Use narrow tests before broad tests and fresh command output as evidence.
- Execute deletion batches in import-dependency order and limit each batch to
  at most 15 workflow files.
- Do not infer live or supported use from store-wide status totals. Deletion
  gates use match-scoped, supported-root scans of top-level and nested workflow
  consumers. Missing or unreadable status is nonterminal and fails closed.
- The supported run-root scope is **pending adjudication** until an owner-bound
  record closes it. Store-wide totals remain visible as non-gating hygiene.
- A deletion is not authorized by this plan alone. Its queue gate and the
  applicable Stage-6 owner or review boundary must be satisfied first; once
  those conditions pass, the deletion-first steering authorizes the independent
  non-survivor tranche without a port prerequisite.
- Do not modify the protected in-flight step-back recovery files while their
  queue remains on hold.
- Task 7's handoff intentionally defers the repository-reference capture and
  supported-root run-consumer scan to Stage 6. Their machine statuses remain
  `pending_stage_6_scan` and `pending_adjudication`; the handoff contains no
  synthetic eligibility claim.

## Protected working-tree guard

These seven user-owned paths remain outside this program until their owning
work changes their disposition:

- `docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md`
- `docs/plans/2026-07-01-workflow-audit-tier-fixes.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md`
- `state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt`
- `tests/test_workflow_non_progress_step_back_demo.py`
- `workflows/examples/non_progress_step_back_demo.yaml`
- `workflows/library/prompts/workflow_step_back/diagnose_non_progress.md`

Before every commit, print the complete cached path list, then run this literal
guard; it must print nothing:

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

Never stage, restore, rewrite, format, or delete a protected path.

## Stage-6 Queue Manifest

The manifest below is an exact summary of the machine-readable handoff. Queue
membership and counts are tested in both directions; no sixth queue and no
unclassified authored YAML/YML path are permitted.

| Queue ID | Paths | Legacy rows | Status | Prerequisite queues | Disposition and gate |
|---|---:|---:|---|---|---|
| `delete_non_survivor_estate` | 100 | 53 | `pending` | none | Early independent deletion in dependency-ordered batches of at most 15 after zero unclassified active references and zero supported matching nonterminal top-level or nested consumers. |
| `archive_design_delta_yaml_twin` | 7 | 10 | `pending` | `delete_non_survivor_estate` | Record each pre-delete blob identity in git history, verify the structured `.orc`, registry, parity, and drain-plan evidence, then delete; do not create a live archive copy. |
| `port_verified_iteration` | 1 | 0 | `pending` | none | Use the structured Task-15 plan input, then create and promote one dedicated `.orc` port through the parity contract before applying its deletion gates. |
| `port_generic_run_watchdog` | 1 | 0 | `pending` | none | Create and promote one dedicated `.orc` port through the parity contract, then apply the deletion gates to its YAML source. |
| `hold_non_progress_step_back` | 1 | 0 | `pending` | none | No mutation until the step-back recovery owner records an explicit delete-or-port disposition; then requeue through a reviewed handoff update. |

### Task 1: Close the `.orc` language-gap list — ENABLING

- [ ] Reconcile `docs/workflow_yaml_orc_gap_list.md` against only the two port
  queues and the protected holdout. A feature used exclusively by deleted
  workflows receives a recorded `drop` decision, not speculative `.orc`
  implementation.
- [ ] Every surviving gap has one of: implemented design, named blocking gate,
  or explicit owner waiver. No entry may use an unbound “TBD”.
- [ ] Review the final list before either port begins.

### Task 2: Move dashboard structure reads to the typed surface — ENABLING

- [ ] Replace raw YAML structure reclassification in the dashboard with the
  loaded typed surface (`SurfaceStepKind` / executable IR).
- [ ] Preserve the public dashboard behavior with contract and dataflow tests;
  do not test literal prompt or warning wording.
- [ ] Run the focused dashboard suite and an import or endpoint smoke.

### Task 3: Split YAML parsing from shared validation — ENABLING

- [ ] Move validation and normalization used by both frontends into a shared
  module. Keep YAML parsing and file loading isolated behind the legacy loader.
- [ ] Redirect `.orc` lowering to the shared validation module without changing
  executable-IR semantics.
- [ ] Run focused lowering, loader, characterization, collect-only, and one
  end-to-end route smoke before review.

### Task 4: Add the deprecation surface — GATE ALREADY SATISFIED

- [ ] The promoted Design Delta `.orc` primary satisfies this task's real-target
  gate; warning work need not wait for either new Task-5 port. Warn once on
  fresh YAML/YML loads. Existing persisted-run resume behavior remains
  separately governed.
- [ ] Route new authors and templates to `.orc`.
- [ ] Test warning behavior and routing, not literal warning phrasing.

### Task 5: Build and promote exactly two `.orc` ports — GATED PER ROW

| Family | Required promotion evidence |
|---|---|
| `verified_iteration_drain` | Dedicated `.orc` source; parity-target registration; passing typed parity report; promoted launch routing; fresh `.orc` workflow smoke; then reference and supported-run deletion gates. |
| `generic_run_watchdog` | Dedicated `.orc` source; parity-target registration; passing typed parity report; promoted launch routing; fresh `.orc` workflow smoke; then reference and supported-run deletion gates. |

For each row, use one reviewable promotion sequence:

- [ ] Author the `.orc` workflow without changing family behavior.
- [ ] Register it in the existing parity target and readiness machinery.
- [ ] Produce a passing parity report with all required roles and artifact
  lineage present.
- [ ] Promote `.orc` launch routing while retaining the YAML source for one
  verification cycle.
- [ ] Run a fresh `.orc` smoke or real launch and obtain both independent
  reviews.
- [ ] Re-run the reference and supported-run scans before queuing the old YAML
  source for deletion.

### Task 6: Execute the gated archive and deletion queues

- [ ] Freeze an exact pre-edit scan over tracked repository references, working
  tree references, and the YAML import graph. Classify every reference as
  active, historical, test/fixture, or documentation. Deletion requires zero
  unclassified active references.
- [ ] Adjudicate and bind the supported run roots. Query exact old workflow
  identities and nested consumers. Deletion requires zero supported matching
  nonterminal runs and call frames. Missing or unreadable status fails closed;
  store-wide totals are disclosed but do not gate unrelated identities.
- [ ] For `archive_design_delta_yaml_twin`, verify the exact seven paths from
  the handoff, their existing `.orc` replacement, historical parity report,
  and a pre-delete blob ID for each file. Git history is the archive; do not
  persist a second live workflow bundle.
- [ ] For `delete_non_survivor_estate`, delete in dependency order and in
  batches of at most 15 paths. Remove or rewrite active imports, tests,
  fixtures, and routing in the same reviewed tranche.
- [ ] After an owner disposition, process `hold_non_progress_step_back` only
  through its newly reviewed queue assignment.
- [ ] After each tranche, regenerate the exact inventory and triage projection,
  run narrow behavioral tests, then run the broad suite in tmux.

Historical prose may still name deleted files. Retirement does not require
zero textual history; it requires zero unclassified active references, exact
queue reconciliation, preserved content identities, and passing runtime gates.

### Task 7: Remove the user-facing YAML frontend — FINAL GATE

This task begins only after both ports are promoted, the held workflow is
resolved, all five queues reconcile to zero live authored YAML/YML paths, and
Tasks 2–3 have made dashboard and `.orc` lowering independent of YAML parsing.

- [ ] Replace fresh YAML/YML execution in run and resume commands with a clear
  `.orc`-required error.
- [ ] Remove YAML parsing and authored-file loading while retaining only the
  separately justified persisted-terminal-run compatibility surface.
- [ ] Verify `find workflows -type f \( -name '*.yaml' -o -name '*.yml' \)` is
  empty and the machine inventory agrees.
- [ ] Run focused CLI, loader, lowering, dashboard, and migration-parity tests;
  then the broad suite with `pytest -q -n 16 --dist=worksteal` in tmux.
- [ ] Run a fresh `.orc` production smoke and update capability and routing docs
  only after executable verification passes.

## Program completion contract

Stage 6 is complete only when:

1. exactly the two specified `.orc` ports are primary and verified;
2. the handoff reconciles all 110 original authored YAML/YML paths through the
   five fixed queues;
3. git history preserves the seven Design Delta pre-delete blob identities;
4. no active or unclassified YAML/YML reference or supported old-identity
   consumer remains;
5. no authored workflow YAML/YML file remains under `workflows/`;
6. fresh YAML/YML execution is rejected while the separately documented
   persisted-run compatibility policy remains intact; and
7. focused, broad, end-to-end, specification, and code-quality checks pass on
   the final tree.
