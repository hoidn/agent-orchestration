# User-Facing YAML Retirement Program (Stage 6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to execute this plan task by task.
> Use TDD for implementation changes and obtain specification and code-quality
> review at every review gate.

**Goal:** Retire YAML and YML as user-facing workflow-authoring formats. `.orc`
becomes the only authored workflow surface. Persisted run data and internal
debug serialization are outside this program.

**Current selector:** Task 7 final verification. Tasks 1-6 are complete, and
Task 7 has implemented the ORC-only fresh frontend, removed the user-facing
loader and project PyYAML dependency, and preserved the bounded state-only
terminal-run compatibility surface. Its consolidated focused gate and fresh
production `.orc` dry-run smoke pass. The final scoped broad comparison and
both independent reviews remain open, so Stage 6 is not yet complete. Task 4's
historical reviewed implementation record is
`docs/plans/2026-07-17-yaml-deprecation-surface-implementation-plan.md`.

**Architecture:** The content-addressed handoff in
`docs/plans/2026-07-13-procedure-first-reuse-inventory.json` is the exact work
list. It partitions the original authored YAML/YML estate into five queues: two
ports, one owner-directed delete row under the unchanged
`hold_non_progress_step_back` queue ID, one Design Delta historical archive, and
deletion of the remaining estate. All five queues are drained. Shared validation
remains available to the `.orc` frontend and persisted-run compatibility after
the YAML parser is removed.

**Steering decision:** Retirement is deletion-first. The only workflows that
receive new `.orc` ports are `verified_iteration_drain` and
`generic_run_watchdog`. The seven demoted Design Delta YAML twins are preserved
only through content-addressed git history before deletion. At
`2026-07-23T16:06:20-07:00`, owner Ollie personally selected DELETE, not port,
for the non-progress step-back workflow; the reviewed handoff requeued it for
deletion with no replacement. Its reference and supported-run-consumer gates
subsequently passed and the path is retired. Every deletion, archive, and port
queue is now drained. Task 7's parser-removal product work is implemented and
awaits the final broad comparison and independent reviews.

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
- The supported run-root scope and unsupported/abandoned matching-consumer
  disposition are closed by the owner ruling recorded on 2026-07-23.
  Store-wide totals remain visible as non-gating hygiene.
- A deletion is not authorized by this plan alone. Its queue gate and the
  applicable Stage-6 owner or review boundary must be satisfied first; once
  those conditions pass, the deletion-first steering authorizes the independent
  non-survivor tranche without a port prerequisite.
- The owner DELETE decision releases the step-back holdout-specific working-tree
  fence for deletion purposes. This handoff update itself does not modify the
  formerly fenced paths or adopt unrelated working-tree changes.
- The final target's fresh repository-reference and supported-consumer checks
  passed in its deletion transaction. The frozen handoff retains its capture
  status and is not rewritten as synthetic execution state.

## Released holdout-specific working-tree fence

At `2026-07-23T16:06:20-07:00`, owner Ollie selected DELETE, not port, and
released the holdout-specific fence for deletion purposes. The seven paths
formerly covered by that fence are:

- `docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md`
- `docs/plans/2026-07-01-workflow-audit-tier-fixes.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md`
- `state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt`
- `tests/test_workflow_non_progress_step_back_demo.py`
- `workflows/examples/non_progress_step_back_demo.yaml`
- `workflows/library/prompts/workflow_step_back/diagnose_non_progress.md`

These paths are no longer fenced by the YAML-retirement program. This reviewed
handoff update does not modify or stage them, and later deletion work must still
preserve unrelated working-tree edits, stage explicit paths, and satisfy the
ordinary reference, supported-consumer, retention, and review rules. Step-back
mechanics remain available from Git history and the recovery-plan documentation;
live retention or retirement now follows those ordinary rules.

## Stage-6 Queue Manifest

The manifest below is an exact summary of the machine-readable handoff. Queue
membership and counts are tested in both directions; no sixth queue and no
unclassified authored YAML/YML path are permitted.

| Queue ID | Paths | Legacy rows | Status | Prerequisite queues | Disposition and gate |
|---|---:|---:|---|---|---|
| `delete_non_survivor_estate` | 100 | 53 | `complete` | none | Retired in dependency-ordered batches after the reference and supported-run-consumer gates passed. |
| `archive_design_delta_yaml_twin` | 7 | 10 | `complete` | `delete_non_survivor_estate` | Pre-delete blob identities remain in git history; the replacement, registry, parity, and drain-plan gates passed and the YAML twins are retired. |
| `port_verified_iteration` | 1 | 0 | `complete` | none | The dedicated `.orc` is promoted and remains the new-launch route. The YAML twin passed the Task 6 reference and supported-run deletion gates and is retired. |
| `port_generic_run_watchdog` | 1 | 0 | `complete` | none | The dedicated `.orc` is promoted and remains the new-launch route. The YAML twin passed the Task 6 reference and supported-run deletion gates and is retired. |
| `hold_non_progress_step_back` | 1 | 0 | `complete` | none | Owner Ollie selected DELETE, not port, at `2026-07-23T16:06:20-07:00`; no `.orc` port was built, both deletion gates passed, and the YAML path is retired. |

### Task 1: Close the `.orc` language-gap list — ENABLING

- [x] Reconcile `docs/workflow_yaml_orc_gap_list.md` against only the two port
  queues and the then-protected holdout. A feature used exclusively by deleted
  workflows receives a recorded `drop` decision, not speculative `.orc`
  implementation.
- [x] Every surviving gap has one of: implemented design, named blocking gate,
  or explicit owner waiver. No entry may use an unbound “TBD”.
- [x] Review the final list before either port begins.

**Task 1 evidence:** `docs/workflow_yaml_orc_gap_list.md` reconciles exactly the
two port queues and the then-protected holdout, records one YAML-only `drop`,
and closes every other observed mechanic as implemented or a named fail-closed
gate with no owner waiver. The structural contract passed 5 tests; the handoff
projection passed 27, workflow-specific checks passed 30, and relevant Workflow Lisp
capability lanes passed 173. Independent specification review returned PASS and
quality review returned APPROVED. These results close only Task 1; they do not
close any queue, scan, port, promotion, or deletion gate.

### Task 2: Move dashboard structure reads to the typed surface — ENABLING

- [x] Replace raw YAML structure reclassification in the dashboard with the
  loaded typed surface (`SurfaceStepKind` / executable IR).
- [x] Preserve the public dashboard behavior with contract and dataflow tests;
  do not test literal prompt or warning wording.
- [x] Run the focused dashboard suite and an import or endpoint smoke.

**Task 2 evidence:** New build bundles persist a canonical, digest-bound typed
workflow surface, and `.orc` dashboard reads decode only that artifact while
legacy YAML remains isolated behind `WorkflowLoader`. Source deletion/edit
smokes covered both a one-node workflow and an imported three-node workflow.
The persisted-surface producer passed 174 focused checks, the dashboard reader
passed 126 dashboard/CLI checks, and both halves received independent
specification PASS and quality APPROVED reviews. The fresh broad run completed
with 5099 passed, 17 skipped, and only the six already-adjudicated unrelated
failures. Historical retirement comparisons retain their frozen meaning by
projecting only the four additive dashboard-surface provenance fields; the
retirement module passed 306 checks. The reviewed design revisions landed at
`81b511a7` and `e5335da5`, the producer at `8e81855a`, the historical-evidence
amendment at `1db310e6`, its implementation at `53d416ed`, and the dashboard
reader at `816f61ca`.

### Task 3: Split YAML parsing from shared validation — ENABLING

- [x] Move validation and normalization used by both frontends into a shared
  module. Keep YAML parsing and file loading isolated behind the legacy loader.
- [x] Redirect `.orc` lowering to the shared validation module without changing
  executable-IR semantics.
- [x] Run focused lowering, loader, characterization, collect-only, and one
  end-to-end route smoke before review.

**Task 3 evidence:** `orchestrator/workflow/validation.py` is the single
in-memory mapping-to-bundle authority used by the legacy YAML frontend and
Workflow Lisp lowering; authored YAML parsing and recursive file loading remain
isolated in `orchestrator/loader.py`. The final guard module passed 27 tests,
the complete focused lane passed 624, the dashboard/CLI regression passed 126,
and fresh `.orc` dry-run validation succeeded. The broad rerun recorded 5137
passed and 17 skipped with only the same six established unrelated failures.
The reviewed plan and sequencing amendment landed at `c587995e` and
`15da1291`; characterization, implementation, permanent guard, and the
verified-drain typed-load smoke correction landed at `a375b1bd`, `88102b9a`,
`631434c3`, and `7cc6f1d2`. Independent specification review returned PASS and
code-quality review returned APPROVED for exact HEAD `7cc6f1d2`.

### Task 4: Add the deprecation surface — GATE ALREADY SATISFIED

**Task 4 design:**
`docs/plans/2026-07-17-yaml-deprecation-surface-design.md` defines the exact
fresh-root event schema, persisted-read suppression (including `.orc` rebuilds
with legacy YAML bundle dependencies), and new-author routing boundary.

- [x] The promoted Design Delta `.orc` primary satisfies this task's real-target
  gate; warning work need not wait for either new Task-5 port. Warn once on
  fresh YAML/YML loads. Existing persisted-run resume behavior remains
  separately governed.
- [x] Route new authors and templates to `.orc`.
- [x] Test warning behavior and routing, not literal warning phrasing.

**Task 4 evidence:** Explicit fresh YAML/YML roots now emit the structured
advisory event once per root; persisted resume, report, dashboard, and `.orc`
rebuild compatibility reads suppress it without changing build identity. The
loader event, normalization guard, persisted suppression, fresh-route
integration, and author routing landed at `3871099b`, `4e0a700d`, `30b1bd48`,
`ee0e520a`, and `b329c4b3`. Final verification passed 550 focused and 45
routing tests; `.orc` and YAML dry-run smokes observed respectively zero and one
event; the broad suite recorded 5181 passed and 17 skipped with exactly the six
established unrelated failures. Independent specification review returned PASS
and quality review returned APPROVED for exact HEAD `b329c4b3` and tree
`00b1a2d1`. At the Task 4 closeout this closed only Task 4: YAML remained
executable and `Legacy`, both Task-5 port rows retained every per-row gate,
Task 6 retained every deletion gate, and Task 7 parser removal remained
incomplete. The Task 5 table below records subsequent family progress.

### Task 5: Build and promote exactly two `.orc` ports — COMPLETE

| Family | Required promotion evidence | Family status |
|---|---|---|
| `verified_iteration_drain` | Dedicated `.orc` source; parity-target registration; passing typed parity report; promoted launch routing; fresh `.orc` workflow smoke; then reference and supported-run deletion gates. | **Promotion gates closed; Task 6 retirement closed.** `.orc` is the primary launch route; final report: `artifacts/work/YAML-RETIREMENT-TASK5/parity/verified-iteration-final/verified_iteration_drain.json`. The former YAML twin is retired. |
| `generic_run_watchdog` | Dedicated `.orc` source; parity-target registration; passing typed parity report; promoted launch routing; fresh `.orc` workflow smoke; then reference and supported-run deletion gates. | **Promotion gates closed; Task 6 retirement closed.** `.orc` is the primary launch route; final report: `artifacts/work/YAML-RETIREMENT-TASK5/parity/generic-run-watchdog-final/generic_run_watchdog.json`. The former YAML twin is retired. |

For each row, use one reviewable promotion sequence:

- [x] Author the `.orc` workflow without changing family behavior.
- [x] Register it in the existing parity target and readiness machinery.
- [x] Produce a passing parity report with all required roles and artifact
  lineage present.
- [x] Promote `.orc` launch routing while retaining the YAML source for one
  verification cycle.
- [x] Run a fresh `.orc` smoke or real launch and obtain both independent
  reviews.
- [x] Hand both unchanged YAML sources to Task 6's reference and supported-run
  pre-deletion gates without running ad hoc Task-5 scans or queuing either
  source for deletion.

Both rows have completed the source, registration, typed parity, promoted
launch, and fresh mocked-provider `.orc` smoke steps. The Task-5 implementation
commits culminate in verified-drain promotion at `927447d4` and watchdog
promotion at `e38b14de`. The final report paths remain recorded above, while
the handoff binds each tracked `.orc` source, registry, parity manifest, family
contract test, and Task-5 execution plan. Task 5 is complete. Task 6
subsequently closed the reviewed reference and supported-run pre-deletion gates
and retired both YAML twins without regenerating the final promotion reports.

### Task 6: Execute the gated archive and deletion queues — COMPLETE

Task 6 is governed by
`docs/plans/2026-07-17-yaml-retirement-task-6-execution-plan.md`. Task 5 did
not provide, replace, or pre-run Task 6's generic scanner or authorize either
port-twin deletion; those Task 6 gates have now closed for both port queues.

- [x] Classify each deletion transaction's tracked and working-tree references;
  retain only explicitly historical references.
- [x] Bind the five supported run roots and close every matching nonterminal
  consumer through the owner's unsupported/abandoned disposition.
- [x] Retire the exact seven `archive_design_delta_yaml_twin` paths after their
  replacement, history, parity, and blob-identity gates passed.
- [x] Drain `delete_non_survivor_estate` in dependency order and bounded batches,
  removing live imports, tests, fixtures, and routing in the same transactions.
- [x] Retire `hold_non_progress_step_back` after its owner DELETE decision and
  unchanged reference and supported-run-consumer gates passed; no port was made.
- [x] Preserve the frozen v1 inventory while closing all five queue projections
  and running each batch's narrow checks. The proportionality ruling assigns the
  one final broad comparison to Task 7's parser-removal candidate.

Historical prose may still name deleted files. Retirement does not require
zero textual history; it requires zero unclassified active references, exact
queue reconciliation, preserved content identities, and passing runtime gates.

### Task 7: Remove the user-facing YAML frontend — FINAL VERIFICATION

Both ports are promoted, every deletion and archive queue is drained, all five
queues reconcile to zero live authored YAML/YML paths, and Tasks 2–3 made
dashboard and `.orc` lowering independent of YAML parsing. Task 7 is therefore
eligible and current. The product-facing implementation and focused checks
subsequently landed; only the final scoped broad comparison and two ordered
independent reviews remain open.

- [x] Replace fresh YAML/YML execution in run and executable resume paths with
  a clear `.orc`-required error before new state or run-root mutation.
- [x] Remove YAML parsing and authored-file loading while retaining only the
  separately justified persisted-terminal-run compatibility surface.
- [x] Verify `find workflows -type f \( -name '*.yaml' -o -name '*.yml' \)` is
  empty and the machine inventory agrees.
- [x] Run focused CLI, fixture-adapter, lowering, dashboard, and
  migration-parity tests: the consolidated gate passed 821 with 5 skipped.
- [ ] Run the final scoped broad comparison under the active user-directed
  security-test exclusion with `pytest -q -n 16 --dist=worksteal` in tmux.
- [x] Run a fresh `.orc` production dry-run smoke and confirm the run-directory
  count is unchanged before updating capability and routing status.
- [ ] Obtain the final independent specification and code-quality reviews.

The user-facing `orchestrator/loader.py` boundary and the project PyYAML
dependency are absent. Fresh run accepts only a case-insensitive `.orc` suffix;
nonterminal or restarted legacy YAML/YML runs reject without mutation.
Completed legacy runs retain state-only resume/report/dashboard observability
without reopening authored source. These claims do not substitute for the
still-pending final broad comparison or independent reviews.

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
