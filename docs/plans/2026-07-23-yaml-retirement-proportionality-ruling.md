# YAML Retirement Proportionality Ruling

**Authority:** Ollie, owner of the YAML-retirement roadmap.

**Effective:** 2026-07-23.

**Status:** Active execution authority through Task 7 final verification. This
record changed execution proportion, not the frozen queue membership or the
product-safety meaning of a zero live reference. All queue work and Task-7
product implementation are complete; the final scoped broad comparison and two
independent reviews remain open.

## Decision

The evidence-first Task 6 execution path has eclipsed the deletion product.
Effective immediately:

1. The uncommitted Task 3 state-store and broad-comparison-correction candidate
   is deferred and removed from the active working tree. It produced no
   deletion commit and no Task 3 capture evidence. The adopted pre-edit broad
   baseline at commit `60ba78081d0f7d83bcfe717186500113178d2f9d` remains the
   sole before-sweep comparison baseline.
2. The prospective capture-window absorption implementation approved by
   `62a633506df1f92cce581d3d7addf1b454aa4ac4` is deferred until after Stage 6.
   Both local Task 3 capture-window rows are closed. No further Stage 6
   capture window will be opened.
3. The exact frozen queues in
   `docs/plans/2026-07-13-procedure-first-reuse-inventory.json` remain the work
   list. The 100-path `delete_non_survivor_estate` queue is deleted in
   dependency-safe ordinary commits of at most 15 workflow targets.
4. Before each target is deleted, a fresh fixed-string reference search must
   find no live reference outside the target or the same staged deletion
   transaction. Immutable historical plans, evidence, and inventory records
   may continue naming deleted paths, as the governing program already allows.
   Source, runtime, script, test, fixture, workflow, configuration, routing,
   and current user documentation references are live until removed or
   rewritten.
5. The existing supported-root/run-consumer deletion gate remains
   load-bearing. A matching consumer may be nonblocking only through the
   owner's explicit unsupported/abandoned disposition; raw run status alone is
   not a support decision. This ruling requires no new attestation lifecycle.
6. Each batch runs the narrowest focused pytest selectors that exercise its
   affected loader, workflow, test, fixture, or routing surfaces. The batch is
   staged by explicit path and lands as an ordinary commit after the cached path
   list confirms the intended scope.
7. The owner-adopted before-sweep baseline is sufficient through every queue
   commit. Run one `pytest -q -n 16 --dist=worksteal` on the Task 7 final
   parser-removal candidate after the queues have drained, not once per batch,
   task, or repair.
8. The seven Design Delta twins keep their existing history/archive,
   replacement, parity, and promoted-primary checks. The two promoted port
   twins keep their existing Task 6 deletion gates. At
   `2026-07-23T16:06:20-07:00`, owner Ollie selected DELETE, not port, for
   `hold_non_progress_step_back`; the reviewed handoff requeues that unchanged
   queue ID as pending deletion with no replacement. Its existing reference and
   supported-run-consumer gates remain.
9. No new evidence schema, repair class, attestation lifecycle, capture
   window, discretionary review layer, or process-recovery mechanism is added
   during this sweep.
10. After every deletable queue, including the owner-directed step-back row, is
    drained, execute Task 7 from
    `docs/plans/2026-07-07-yaml-retirement-program.md`: reject fresh YAML/YML
    execution, remove authored YAML parsing/loading, prove the authored workflow
    estate empty, run its focused checks and the one final broad comparison, run
    a fresh `.orc` smoke, and update routing/capability docs.
11. Report Stage 6 complete and stop. Stage 7 provider live binding starts only
    when the owner schedules its design review.

## Supported-Run Disposition

At `2026-07-23T12:38:06-07:00`, Ollie personally adopted the following
disposition through an explicit selection in his supervising session; that
session relayed the decision mechanically at his direction:

- the complete supported run-root scope is
  `/home/ollie/Documents/agent-orchestration/.orchestrate/runs`,
  `/home/ollie/Documents/agent-orchestration-2/.orchestrate/runs`,
  `/home/ollie/Documents/EasySpin/.orchestrate/runs`,
  `/home/ollie/Documents/PtychoPINN/.orchestrate/runs`, and
  `/home/ollie/Documents/ptychopinnpaper2/.orchestrate/runs`;
- filesystem enumeration under `/home/ollie/Documents` was used to bind those
  five repository-level roots as the complete supported scope, and no other
  supported run store is intentionally used; nested disposable test, probe,
  artifact, and scratch roots are outside that owner-bound supported scope;
- every matching nonterminal deletion-queue consumer in those roots is
  `unsupported_abandoned`; and
- the supporting live-process check found zero orchestrator processes, so the
  matching `running` and `suspended` labels are stale state from crashed or
  abandoned sessions.

This closes the supported-root and matching-consumer gate for the deletion
queues. It does not waive each target's fresh repository-reference check or
the separately retained Design Delta and port-twin gates. The newly requeued
step-back row still requires its own fresh reference and supported-consumer
checks before deletion; this handoff does not infer their result from the
earlier deletion-queue disposition.

## Non-Progress Step-Back Owner Disposition

At `2026-07-23T16:06:20-07:00`, Ollie personally adopted
`step-back-owner-disposition` as DELETE, not port, through an explicit selection
in his supervising session; that session relayed the decision mechanically at
his direction. The reviewed handoff updates only the existing
`hold_non_progress_step_back` row: its status remains `pending`, its disposition
is `delete`, its replacement kind is `none`, and its zero-reference and
supported-run-consumer gates are unchanged. No `.orc` port is authorized.

For deletion purposes, this decision releases the former seven-path
holdout-specific working-tree fence. The handoff update does not modify or stage
those paths, overwrite unrelated working-tree edits, or decide whether adjacent
step-back files are retained or retired. Step-back mechanics remain available
through Git history and the recovery-plan documentation; future live-surface
retention or retirement follows ordinary rules.

This records routing and authority only. It does not delete the YAML, attest
that either deletion gate passed, make Task 7 eligible, add a schema or evidence
process, or authorize mutation of run state.

## Completion Note

The owner-directed final batch subsequently passed its fresh reference,
five-root supported-consumer, and live-process checks and retired the YAML,
its dedicated test, and its YAML-only input helper without mutating run stores.
The authored workflow YAML/YML estate is empty, all Task 6 queue work is
drained, and Task 7 is now current and eligible. This note does not claim any
Task 7 parser-removal implementation at the Task-6 closeout boundary.

Task 7 subsequently made fresh execution ORC-only, retained only completed
legacy state-only resume/report/dashboard compatibility, removed the authored
YAML loader and project PyYAML dependency, retired the stale YAML demo runner,
and passed its consolidated focused gate with 821 passed and 5 skipped. A fresh
production `.orc` dry-run smoke also passed without changing the run-directory
count. The final scoped broad comparison and both independent reviews have not
yet run, so this note does not report Stage 6 complete.

## Supersession Boundary

For Stage 6 queue execution this ruling supersedes the Task 6 execution plan's
per-implementation and per-batch evidence materialization, broad-run,
attestation, capture-window, two-commit closure, execution-index, and
independent-review machinery. It also supersedes the program sentence that
requires a broad suite after every tranche.

It does not change:

- the five frozen queue memberships;
- the batch-size ceiling;
- dependency-safe deletion order;
- explicit-path staging;
- zero live references before deletion;
- explicit owner disposition of matching supported run consumers;
- the Design Delta archive and replacement checks;
- either promoted port twin's existing deletion gate;
- the requeued step-back row's zero-reference and supported-consumer gates; or
- Task 7's product-facing parser-removal checklist and final verification.

## Claims Not Made At Issuance

The claims below record what the ruling and owner disposition did not establish
when issued. The later completion and progress notes above supersede their
time-bound queue and Task-7 eligibility status without changing their authority
limits.

- This ruling does not attest that any queue is already empty.
- Closing the local capture window does not approve or land its deferred
  implementation candidate.
- The before-sweep broad baseline does not excuse a new final-suite regression.
- Historical text retention is not permission to retain an executable,
  routing, test, fixture, or current-documentation dependency on deleted YAML.
- The owner DELETE decision and reviewed handoff do not claim that the
  step-back YAML is deleted or that Task 7 is eligible.
