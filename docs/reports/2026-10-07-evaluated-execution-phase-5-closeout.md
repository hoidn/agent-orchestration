# Evaluated Execution Phase 5 Execution Record

Status: **implementation in progress**. Task 0 is prepared; Task 1 compilation
and checked read-back and Task 2 read-only replay are accepted after independent
contract/quality reviews and coordinator acceptance.
Task 3's lifecycle/item-cwd seams have bounded acceptance; its authored parallel
CLI qualification remains partial. Task 4's bounded workers are accepted after
independent contract/quality PASS; integration into main remains pending.
The [Phase 5 plan](../plans/2026-10-07-evaluated-execution-phase-5-plan.md) owns
pending runtime/public qualification. Parallel-map delivery is not complete.

## Decisions And Current Baseline

The owner selected D1 **2.37** on 2026-10-12; W3 retains 2.36. D2 item cwd/path
contracts and D3 independent-prefix replay/checked representation retain their
original independent design acceptance at prepared-plan SHA-256
`9d2e02a8be309cd4339c59039fb2fb3b5ad8e1a563ca9a31f6b98a803b8873f0`.
The plan's contract delta owns the exact proposal and diagnostics; acceptance
does not establish implementation, read-back compatibility or runtime behavior.

Task 4 scheduling refinement (2026-10-13): path run references share one
exclusive E1 lifecycle per parent ledger; other effect classes may progress.
The existing globally adjacent acknowledgements, launch head and settlement
pair require this restriction. Independent design review accepted the bounded
refinement after adding a complete read-only recovery-obligation check before
any reconciliation write. Existing historical committed pairs remain valid
without being the global head. No new owner decision, schema or class refusal
is introduced. `E/phase5-runref-coordinator-seam-review.md`,
`E/phase5-runref-scheduling-design.md` (SHA-256
`235aedb0d1466f4a18bf352788db3913577ffe3e06472c1374ffc1ca4483d071`)
and `E/phase5-runref-scheduling-design-review.md` retain the source findings,
R1 correction and independent design PASS. The [Task 4 cut](#task-4--bounded-workers-and-coordinator)
records implementation and focused concurrency/recovery evidence; Task 5's
public interruption/invalidation campaign remains pending.

At Task 0 entry on 2026-10-13, worktree
`.worktrees/orc-consolidation-20261012` (W) was at documentation closure `2feb6db7`, with product/test bytes qualified at
`bfd0f32411cec03241a9b2f54a6fcae118c75bd5`. The
[consolidation closeout](2026-10-12-workflow-lisp-consolidation-closeout.md) records
independent review and coordinator acceptance of bounded Tasks 0–4/Gates A–D:
268 integrated cases passed, the original 53 corpus outcomes/38 Built artifact
bytes are unchanged, one corpus case was added, and six retained families were
qualified. The full remains RED (275 failed, 23,511 passed); its cause taxonomy,
58-case canonical-interpreter PASS and separate five PASS/one XFAIL rerun retain
their limitations. None of this proves parallel execution or authorizes retirement.

Evidence directory **E** is `.worktrees/orc-consolidation-evidence-20261012`.
`E/phase5-current-entry.md` records actual owners, caller edges and source hashes,
SHA-256 `06a5a547af46a561f159b153b27d6a51030354130af2976d2532e95f2f7a801b`.
Its inventoried product hashes were rechecked unchanged at entry. Its earlier
wording that consolidation qualification blocks implementation is historical;
the final accepted consolidation report resolves that prerequisite.

Salient additional owners beyond the plan's initial table are shared
`contracts/closed_program/command_check.py` for command projection/control scope,
`workflow_lisp/lowering/command_transport_decisions.py` for continuation demands,
and the target registries in `workflow/validation.py` and
`workflow/run_ref/{config,bundle_transport}.py`. Frontend semantic identities in
`closed/names.py` and `procedure_typecheck.py` must preserve absent optional
fields, not merely JSON omission. `workflow/evaluated/capture.py` and its view
replay injection are later compatibility owners when prefix replay changes.
The inventory is a source-read record, not proof that those edits alone suffice.

## Reuse And New Proofs Still Required

**C5** and **C3** keep the physical locations and original receipt owners named
in the plan. C5 decisions/design-review records and all six named C3 Task 17
reports are present in the main checkout; this entry checked availability, not
a new review of their historical campaigns. Their original tested revisions,
hashes, scope and limitations remain unchanged. The delivered Phase 6a pilot
also remains baseline evidence. Reuse only unchanged contracts; none establishes
parallel-map feasibility, delivery or acceptance at the new target.

At entry, source rewrote serial `ListMapEffectExpr`, rejected another pending
effect identity and required global runtime/view replay order. Command/provider
launch and result paths used the outer workspace; their parallel changes remain
pending. These are implementation
constraints, not failures newly demonstrated by this entry. Tasks 1–7 must prove
the new checked control and target/import/read-back gates; command/adapter/path
run-reference cwd behavior; independent interleaved prefixes and journal-ordered
validation; nested-map liveness and one-writer concurrent publication; and public
kill/resume/invalidate, retained-package and consumer/live qualification where
required. Existing serial REPL capture must remain source-free and read-only.

That entry involved no new compiler execution. The frontend checks below now
supply bounded evidence; no concurrent runtime or new cwd/replay/concurrency
proof is claimed. Phase 6b migration and Phase 7 retirement gates remain unchanged.


## Task 1A — Bounded Frontend Cut

The cut registers target 2.37 and admits the parsed/typed parallel form while
preserving serial rewriting and absent-field identities. It covers frontend
binder/capture propagation and old-entry/new-helper import direction; WCC,
closed construction/checking/sites and runtime parallel execution remain pending.
Independent contract and quality reviews passed; the quality reviewer found no
findings and confirmed the 17-path tested snapshot unchanged. The coordinator
accepted this bounded frontend cut; Task 1 overall remains open.

| Evidence under E | Result and scope |
| --- | --- |
| `phase5-frontend-red.json`, `.log`, `.xml` | Initial RED retained: 16 failed/15 passed, exit 1; fixture failures are not all valid product counterexamples |
| `phase5-frontend-direction-red.json`, `.log`, `.xml` | Meaningful old-entry/new-import direction RED: 4 failed, exit 1 |
| `phase5-frontend-revision-red.json`, `.log`, `.xml` | Real pure-inline pipeline revision RED: 2 failed/4 passed, exit 1; reproduced and corrected |
| `phase5-frontend-collect-renames.json`, `.log`, `.xml` | Earlier changed-module collection: 85 collected, exit 0 |
| `phase5-frontend-revision-collect.json`, `.log`, `.xml` | Revised frontend test module: 49 collected, exit 0 |
| `phase5-frontend-revision-green-scoped.json`, `.log`, `.xml` | Revised frontend module: 49 passed, exit 0, 1.44s pytest |
| `phase5-frontend-controls-revised.json`, `.log`, `.xml` | Existing controls: 437 passed, exit 0, 8.39s pytest; `-n 16 --dist=worksteal` |
| `phase5-frontend-cli.json` | Initial pure 2.37 public compile refused module/path mismatch, exit 2; retained |
| `phase5-frontend-cli-corrected.json` | Corrected pure 2.37 public compile accepted, exit 0; this does not execute a parallel program |

Receipts retain exact argv/cwd/exits; frontend tests use canonical Python 3.13.
The real-pipeline revision distinguishes pure inline workspace/body acceptance
from impure-workspace refusal and the retained authored one-call body rule.
Earlier RED and intermediate receipts remain historical; final scoped receipts
own the revised code's claims.

The additional quality probe `E/phase5-quality-inline-probe/results.json`
accepts a `defproc` inline `UsesCommand` helper at both 2.36 and 2.37: the former
retains `LoopRecurExpr`, the latter retains `ListMapEffectExpr`. This is a
reviewer's source/typecheck probe, not a new pytest campaign or parallel runtime
qualification.

`E/phase5-frontend-revised-snapshot.json` pins the tested paths, SHA-256
`0ca647cb05369e0be660e26b14ea067fbff5ffecf5199535a1d63c377ad52597`.
`E/phase5-frontend-revision-complexity.json` records Radon 6.0.1 with assertions
and closures included: 34 new functions, maximum CC 9; new production/test
modules are 104/284 physical lines. The modified existing
`_check_map_effect_body` is CC 11, previously 8. These checks do not prove the
pending WCC representation, checked read-back, artifact/site agreement, runtime
admission or concurrent lifecycle; Task 1's overall checkboxes remain open.

## Task 1B — Bounded WCC Retention

The cut retains one `WccParallelMap` through elaboration and ANF. Its source
stays outside the item binder; its pure workspace region and item body bind the
item. Existing joins retain the outer continuation without redirecting item
halts. Hygiene, capture propagation, use-site renaming, analysis and shared
command-demand traversal recognize both regions. The workspace region will use
the existing pure-block representation in the next closed-construction cut.
No flat lowering or concurrent runtime is added.

The ten product/test owners are pinned by
`E/phase5-wcc-product-hashes.json`, SHA-256
`19879b30a15d74390bf171b16f60f86292fba95b6706ee5767d0ccd4520e7f4c`,
against worktree HEAD `147e7cc0`. The additional required owners
`wcc/use_site_scope.py` and `lowering/command_transport_decisions.py` were
identified and accepted before their edits.

| Evidence under E | Result and scope |
| --- | --- |
| `phase5-wcc-red.*`, `phase5-wcc-use-site-red.*` | Genuine missing-retention and binder-renaming failures, retained before fixes |
| `phase5-wcc-narrow.*` | 60 passed, exit 0, 2.09s: 11 WCC cases and 49 frontend controls |
| `phase5-wcc-collect.*` | 11 new WCC cases collected, exit 0 |
| `phase5-wcc-controls.*` | RED: 5 failed, 421 passed, 2 xfailed, exit 1; canonical Python 3.13, `-n 16 --dist=worksteal` in tmux |
| `phase5-wcc-controls-baseline-comparison.json` | All five characterization failures match exact node IDs and messages in both `baseline-retest.xml` and `after-full.xml`; no golden was changed |
| `phase5-wcc-cli.*` | Public imported-asset run/completed-resume regression: 1 passed, exit 0, 7.62s |
| `phase5-wcc-contract-probes.json`, `phase5-wcc-contract-review-verification.json` | Independent contract review PASS, seven valid preparation probes; ten hashes and receipt counts independently verified |

Expanded RED receipts also contain two invalid source fixtures; they are not
product counterexamples. `E/phase5-wcc-complexity.json` records new production
helper CC 4, new test maximum CC 11 with assertions, and a 178-line new test
module. The coordinator independently checked the diff, unchanged hashes,
public CLI result and both baseline comparisons. Independent code-quality review
also passed without findings, including a real-preparation probe with a serial
map followed by a parallel map reusing the item name. The coordinator accepted
this bounded cut; no product bytes changed after qualification.

This cut does not qualify closed emission, preparation comparison, command-scope
projection, source-free read-back/sites or parallel runtime. The full suite was
not repeated for this intermediate cut; its Phase 5 campaign remains required.
Task 1 overall and parallel public availability remain pending.

## Task 1C — Checked Compilation And Read-Back

The compiler emits one target-2.37 `par-map` in the existing `table/1`
representation. Source, item binder, pure workspace block, local item body,
types, bounds, labels and provenance pass independent checked read-back.
Existing site, call, capture, command-index and provider-IO walks reach the new
regions. No runtime execution or new effect class is added.

Independent contract review found a frontend prerequisite defect: a pure inline
helper containing another parallel map was incorrectly checked as if its
expanded implementation were call arguments. The correction reuses retained
binding identity and helper-expansion provenance. A new positive case preserves
both maps; four negative cases retain the authored-call and pure-argument rules.
Independent contract review accepted the correction. A distinct code-quality
reviewer accepted the frozen cut without findings; the coordinator inspected
the diff, final hashes and verification receipts before integration.

| Evidence under E | Result and scope |
| --- | --- |
| `phase5-closed-red.*` | Initial missing closed translation: 1 failed |
| `phase5-nested-inline-red.*`, `phase5-nested-inline-green.*` | Reproduced inline-helper defect; corrected positive and four negative cases pass |
| `phase5-nested-inline-final-collection.*` | 60 new/changed compiler and read-back cases collected |
| `phase5-nested-inline-final-narrow.*` | 120 passed: frontend, WCC, construction and malformed read-back |
| `phase5-nested-inline-controls.*` | 1,025 passed, including public CLI compilation, existing compiler/contract controls, compiler-free isolation and imported-provider IO; canonical Python, tmux, `-n 16 --dist=worksteal` |
| `phase5-nested-inline-corpus.*` | All 53 original corpus outcomes and 38 Built artifacts unchanged at fixed identity inputs; the current 54-case corpus retains its one pre-existing additional case |
| `phase5-old-reader.*` | Reader from `bfd0f324` rejects the new target and, with an older header, the unknown control |
| `phase5-serial-helper-index.json` | Old/current serial helper index-reset witness unchanged |
| `phase5-review-contract-final-recheck.json`, `phase5-review-contract-final-tests.*` | Independent contract PASS: original reproducer, five tests, eleven hashes and specific malformed-control refusals |

`E/phase5-closed-handoff.md` and its revision addendum distinguish the original
115/918-case receipts from the final corrected checks. The current eleven-path
snapshot is `E/phase5-nested-inline-path-hashes.json`, SHA-256
`be35578ceca86e94420a1646ac51e7d10701f74f1128603e627aa3852eedf0c3`.
Independent quality review also verified all eleven hashes and compiled/read
three additional cases: command roots/index under an item, maps inside a
`match` helper, and a second map consuming generated run-reference results. New test modules remain
below 500 lines and new functions below CC 12, including assertions; the
existing large structural typechecker changed from CC 56 to 59. Earlier malformed
test assumptions are recorded separately from product defects.

These results qualify compiler/read-back behavior only. Concurrent execution,
independent-prefix replay, item cwd, durable recovery, consumer qualification and
the final full-suite campaign remain pending. Task 1 is closed for compilation
and read-back; no runnable parallel authoring recipe or retirement claim follows.


## Task 2 — Independent-Prefix Replay

Runtime preflight and source-free views now share one stored-value traversal
through the existing evaluator. It discovers all independent item prefixes,
then runtime validates committed inputs in journal order before checking retry
frontiers. It preserves each item's sequential order, required coordinator
settlements, the map barrier and whole-suffix invalidation. The ordinary live
effect handler still refuses parallel maps; this cut launches no workers.

Independent contract review found that the first implementation kept the item
ordering rule active throughout the serial continuation. The correction separates
the item rule from a persistent map barrier: subsequent starts must follow the
map, while ordinary serial behavior remains unchanged. Pure/empty maps preserve
existing barriers without multiplying them. Twelve regression cases cover that
boundary; independent contract re-review and distinct quality review passed.
The coordinator inspected the final diff, seven frozen hashes and raw receipts
before accepting the cut.

| Evidence under E | Result and scope |
| --- | --- |
| `phase5-replay-red-semantic.*` | Valid interleaved completed journal refused before implementation |
| `phase5-replay-narrow-initial.*` | 69 passed: initial 13 new cases and 56 existing replay/view controls |
| `phase5-replay-controls.*` | 59 passed: isolation, provider IO, imported-assets public run/completed resume, REPL/capture and input-document replay; canonical Python in tmux with `-n 16 --dist=worksteal` |
| `phase5-replay-serial-tail-red-semantic.*` | Six genuine serial-policy failures and six passing controls before the review correction |
| `phase5-replay-serial-tail-green.*`, `phase5-replay-serial-tail-collect.*` | Corrected module: 41 passed; 41 collected |
| `phase5-replay-public-report.*` | Public CLI report after source/closure deletion, outputs in input order and unchanged run-file hashes; also exercised by the corrected module |
| `phase5-contract-settlement.*` | Independent reviewer: six existing real run-reference settlement controls passed |
| `phase5-contract-serial-tail-corrected.json`, `phase5-contract-corrected.*` | Original review reproducer accepts all six valid cases in runtime and views; four targeted barrier/nesting controls pass |

`E/phase5-replay-handoff.md` distinguishes the reused controls from final corrected
checks. `E/phase5-replay-owner-metrics.json` pins seven production/test owners,
SHA-256 `db158d7ef0202495d9e25cc17f0a4fed0c3213c202ef2d68ce5c9bf3b0a157fd`.
The new replay module has 185 physical lines and maximum function/closure CC 8;
the new tests/helper have 383/117 lines and maximum CC 9/6, including assertions.
The prior snapshot remains separate; final hashes are not attributed to older
campaigns. The first setup failure exhausted `/tmp`; later tests used dedicated
`/home` temporary roots. Fixture compilation/site-index mistakes are recorded
separately from product defects. `E/phase5-contract-final-review.md` and
`E/phase5-quality-final-review.md` retain the independent PASS dispositions.

These receipts qualify read-only replay and preflight over checked parallel
artifacts. Actual item cwd binding, concurrent execution, public interruption and
consumer qualification remain Tasks 3–6. The final full-suite campaign remains
Task 7; its existing RED baseline is not converted to PASS by these controls.

## Task 3 — Attempt Lifecycle And Item Cwd Seams

Serial execution now uses the extracted prepare → external performance → finish
path. Finish owns typed-result validation, C4 rehash, commit and E1 result
projection/settlement. Durable allocation/publication hooks remain actual hooks;
moved launch hooks and their tests were updated together. Pure item-workspace
values and dependencies reach C7/C9 without filesystem access in view replay.
Commands/providers retain outer path authority while using the item's launch
directory, with D2's absolute runtime IO coordinates and reserved environment
handling. Command closure selection remains local to the reached command.

| Evidence under E | Result and scope |
| --- | --- |
| `phase5-attempt-cwd-red-valid.*` | Four intended missing lifecycle/cwd failures before implementation |
| `phase5-logical-launchers-red.*` | Retrospective differential check: five failures/eight passes against the old shared launchers; exact modified bytes restored |
| `phase5-attempt-broad.*` | Initial 568-case union: 560 passed/eight failed; six pending-frontier failures from an undefined variable, two strict old-provider-call parity failures |
| `phase5-attempt-final-narrow.*` | Corrected final bytes: 81 passed, including all 38 new cases, 41 parallel-replay cases and two strict provider parity controls |
| `phase5-attempt-collect-final.*` | 38 new cases collected in three modules |
| `phase5-attempt-broad-final.*` | Same 568-case union passed with canonical Python in tmux, `-n 16 --dist=worksteal`; includes public serial run/resume, process-kill recovery, imported assets and unchosen-command closure checks |

Independent contract and distinct code-quality review passed without open
findings; the coordinator inspected the diff, raw receipts and all 27 final
hashes. `E/phase5-attempt-source-freeze.json` has SHA-256
`b7e1b6029982526f3185267d33a43bdcada15f4923145d33e29cb1c2faeac1a8`;
the original failing snapshot remains separate. The static inventory records
58 new functions/closures, maximum CC 11 including assertions; the four new
modules contain 83/377/229/294 physical lines. The handoff
`E/phase5-attempt-cwd-handoff.md`, receipt ledger
`E/phase5-attempt-receipts.json` and contract/quality review files preserve exact
scope, cases, hashes and the corrections, including preliminary fixture errors.

Real subprocess witnesses cover item/outer homonyms, closure mutation and retry,
workspace relocation, absolute document/result paths with external state roots,
adapter containment, provider artifacts, nested serial CLI environment clearing,
and E1 clone/proof/settlement under outer parent authority. Inline certified
transport uses an explicit custom binding; the existing builtin review adapter
is qualified through its carrier argv, without changing its manifest.

This is bounded seam qualification, not full Task 3 public acceptance. At this
Task 3 cut live `par-map` still refused; [Task 4](#task-4--bounded-workers-and-coordinator)
subsequently supplies workers, coordinator-owned E1 driver events and six
bounded public CLI cases. Those cases do not discharge all D2 clauses in the plan.
The original pinned-controller compatibility campaign and full suite remain
Task 7. Changed package bytes retain truthful pin refusals; current-package
serial tests do not establish universal old-run compatibility.

## Task 4 — Bounded Workers And Coordinator

**Accepted bounded Task 4 cut after independent contract and quality PASS.
Integration into main remains pending.** This cut executes checked target-2.37
parallel maps; it does not close Task 3's full public gate or Phase 5.
The 12-path product/test freeze `E/phase5-parallel-source-freeze.json` has SHA-256
`fc4c61b46ab2dd631323f261e5bbf92e95443312c9f27540c48c162018dbffe7`;
the final handoff `E/phase5-parallel-workers-handoff.md` has SHA-256
`cd5ceea4f96902756ce5b427e3905b0686e00a2eab3b48b9fbf1221d01e828d6`.
Independent contract review `E/phase5-workers-contract-review.md` has SHA-256
`a3ec5c9cc728d77c322f0616e319f001846741058216c0d6495a11963045a7f0`;
distinct quality review `E/phase5-workers-quality-review.md` has SHA-256
`1086882de546328777c22a769fc226ebec8dd43e1f118f3bcf6c94633b2f07ad`.
The coordinator accepted this cut after rechecking the freeze hash, all 12
product/test hashes, both review hashes, raw exit-zero receipt and final XML
(494 cases, no failures/errors/skips), the production delta and clean diff check.
No executor cutover or retirement is claimed.

Each live map uses its own bounded stdlib pool and the parent's single
publication coordinator; nested maps share that coordinator. Source, cap and
all item cwd checks precede that batch's reservations. Bodies remain sequential,
results retain input order, and bounds are per map. E1 is serialized from
preparation through settlement per parent ledger, while command/provider siblings
can progress. Ordinary body/external failures drain queued and running siblings;
publication/acknowledgement/authority failures stop new reservations and parent
writes, release waiters and retain descriptors until external work drains.
The existing serial path, APIs, schemas, identities and admitted effect classes
are preserved.

| Evidence under E | Result and limit |
| --- | --- |
| `phase5-parallel-initial-affected-run.*` | 487 cases: 486 PASS / 1 old replay-expectation FAIL, 117.34 s. Updated for Task 4's ordinary body-failure drain; sibling validation and orphan refusal retained. |
| `phase5-parallel-8d-qualified-affected-final-run.*` | Intermediate freeze: 492 PASS, 118.05 s; the later failed-fsync gap was not covered. |
| `phase5-parallel-failed-sync-red-readable.*` | Real RED: 1 FAIL, 2.07 s. A complete readable `failed` row after failed fsync incorrectly permitted another E1 start. The preceding `failed-sync-red` receipt was a fixture failure, kept separately. |
| `phase5-parallel-failed-sync-green.*` | Corrected fatal publication classification: 15 PASS, 15.34 s; no new grants/writes after failed fsync, with ordinary failure controls retained. |
| `phase5-parallel-affected-fsync-final-collect.*` | Historical cf71 freeze: 493 collected, exit 0, 3.20 s; collection is not execution. |
| `phase5-parallel-cf-qualified-affected-fsync-final-run.*` | Historical cf71 freeze: 493 PASS, exit 0, 77.75 s across 23 owner modules; the later deferred-reuse recursion gap was not covered. |
| `phase5-parallel-deferred-fifo-red.*` | P5Q-1 RED: 1 FAIL, exit 1, 1.34 s; immediate E1 reuses beyond the recursion limit exhausted the recursive deferred drain. |
| `phase5-parallel-deferred-fifo-green.*` | Iterative, reentry-guarded FIFO drain: 10 PASS, exit 0, 3.79 s, including the new regression. |
| `phase5-parallel-affected-fifo-final-collect.*` | Final fc4 freeze: 494 collected, exit 0, 3.09 s; collection is not execution. |
| `phase5-parallel-affected-fifo-final-run.*` | Final fc4 freeze: 494 PASS, exit 0, 71.77 s across the same 23 owner modules; real command/provider/child subprocess cases supply bounded integration/smoke evidence. |

Original failed receipts and intermediate freezes remain separate. The cf71
contract PASS and quality REQUEST_CHANGES remain preserved in
`E/phase5-workers-cf-contract-review.md` and
`E/phase5-workers-quality-review-cf-request-changes.md`; their verdicts do not
qualify the corrected bytes. P5Q-1 changes only the deferred drain and its
regression test; the reviews reuse unchanged evidence and check the new delta.
The final static census (`E/phase5-parallel-static.json`) records 177 new functions/closures,
maximum Radon CC 11 including assertions, and new modules of at most 499 physical
lines. Historical shared-owner complexity remains identified.

Six public cwd CLI cases cover literal/absolute argv, explicit outer closures,
external cwd/documents/results, builtin argv carrier, custom certified inline
binding and relative provider artifacts. The builtin input signature does not
declare the `schema_version` field its implementation expects; builtin inline
qualification is not claimed. Remaining Task 3 public variants include prior
disappearance/new homonyms, symlink/component order, C4/destination overlap,
package shadow/unsafe paths, relocation and poisoned nested orchestrator/child
environments; the retained direct witnesses still need mapping or public evidence.

Tasks 5–7 remain pending: external process-group SIGKILL/recovery and public C8
invalidation, best-of-N including the configured-provider smoke, and old pinned
controllers/full-suite compatibility. Crash hooks must be checked by caller:
parallel external work uses `effect_execution.perform_external`, while the serial
path uses the imported runtime alias; W9 follows append plus view. This cut
establishes neither general availability nor consumer adoption, Phase 5 closure,
a retirement cutoff or deletion authority.
