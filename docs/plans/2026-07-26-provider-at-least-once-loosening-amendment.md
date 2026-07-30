# Provider At-Least-Once Loosening And Estate Amendment

- **Status:** adopted — absorbed into the substrate track's shape
  (`docs/plans/2026-07-26-substrate-maintenance-track.md`) on 2026-07-26 by
  owner direction (provider-repeat cost model and incorporation request);
  retained as the direction-and-audit evidence record and as the
  tranche-level scope/gate owner for ML, MC, MR, and the M1 inventory
  extension. The track owns sequencing. Nothing is selected by listing:
  every phase still requires its own component plan (ML-0's reviewed spec
  amendment first). ML-3 is now explicitly deferred under the owner's
  security-surface exclusion; the M4 scope conflict remains separately gated.
- **Driver:** owner direction recorded 2026-07-26: the no-provider-repeat
  constraint is too conservative — provider calls are not so expensive that
  they can never be repeated or "wasted". This amendment converts that
  direction into a contract change (exactly-once → at-least-once provider
  attempts) plus the deletions it unlocks.
- **Relation:** extends the substrate track between M1 and M2. It is aligned
  with M2's existing "loud re-spend" bound (a memo miss may re-pay a provider
  call, loudly); ML applies the same cost model to crash/interrupt recovery.
  The Q-track (`docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`)
  is untouched except for one Q-/L-coordinated tranche (MR-4, compiler
  session state, below), on whose compile-path reentrancy later L stages
  depend.
- **Owner decisions:** (1) at-least-once adoption — RECORDED 2026-07-26
  (owner direction; ML-0's spec amendment still passes ordered
  specification/quality review before code changes); (4) phase-MR
  acceptance with MR-4's deletion-bound exception — RECORDED 2026-07-26
  (incorporation request); (2) ML-3 deferral — RECORDED by the owner's
  instruction to skip security-related work, so no provider-isolation
  implementation or normative journal section enters ML-0/1/2/4. Still
  pending as the track's M4 go/no-go question: (3) whether boundary redraw
  (neutral IR package) joins the M4 scope.
- **Copy safety:** this is a plan, not authority. Runtime behavior stays
  owned by `specs/` until ML-0 lands; the audit appendix records evidence at
  the 2026-07-26 checkout and will go stale as phases execute.

## Objective

Replace the exactly-once provider-attempt persistence stack with at-least-once
semantics: an interrupted attempt (orchestrator crash, kill, torn write) is
treated like a failed attempt — discard partial evidence, allocate a fresh
ordinal, re-run under normal control flow. Runs stop dying in quarantine, and
the machinery that exists only to prevent provider re-invocation is deleted
rather than maintained.

Approach in two sentences: amend the normative contract first (ML-0), then
delete downward — quarantine, crash-durable allocation ledgers, the
bundle-transfer journal, adjudication resume reconciliation — replacing each
with discard-and-rerun. What this makes harder is recorded in
"What This Makes Harder" below and must be re-read at each ML gate.

## Audit Evidence (2026-07-26 checkout)

A ten-category structural audit plus a persistence deep dive produced a
65-finding inventory (condensed appendix below). The findings that motivate
this amendment:

- **The exactly-once stack is large and test-heavy.** Attempt
  allocation/lifecycle: `orchestrator/workflow/provider_attempts.py` 1,811
  LOC; evidence: `orchestrator/workflow/prompt_dependency_evidence.py` 1,625;
  journal: `orchestrator/providers/isolation_bundle_broker.py` 2,695;
  state manager share: ~850 of `orchestrator/state.py`'s 1,984. Tests bound
  to this machinery: ~65k LOC ≈ 21% of the test estate (isolation 25.8k,
  supervision 13.8k, peer 8.6k, prompt-dependency 7.9k, adjudication 4.6k,
  attempt allocation 4.3k).
- **Interrupted visits quarantine the run instead of re-running.** Three
  detector/executor pairs — `workflow/executor.py:2184-2395`,
  `workflow/resume_planner.py:259-614` — mark the run failed with sticky
  `provider_{session,supervision,peer_group}_interrupted_visit_quarantined`
  errors; only force-restart or a new run recovers. This is the purest
  expression of the withdrawn cost model, and the triplet has already
  drifted (peer settlement checks `current_step` before publishing,
  supervision after).
- **The allocator defends a writer topology that does not exist.** Every
  allocation takes two process file locks (`.state-mutation.lock` +
  `workflow_lisp/prompt_dependencies/.aggregate.lock`), reloads state from
  disk, fsyncs file and directory, and maintains append-only per-scope
  lifecycle event ledgers plus a permanent repair-barrier file
  (`state.py:373-464`, `state_locking.py:26-44`). Only the CLI constructs
  `StateManager` (`cli/commands/run.py:425`, `cli/commands/resume.py:324,549`);
  the isolation backend's `os.fork()` children exec sandbox helpers and never
  write root state. Loading any state containing
  `provider_attempt_allocations` latches durable mode forever
  (`state.py:1317-1318`), and every direct write then re-reads the state file
  to merge an allocator projection that no other process advances
  (`state.py:1328-1340`).
- **Moving one bundle file uses a five-state journal.** The
  `provider_isolation_bundle_transfer.v1` contract (specs/state.md §202-277)
  binds device, inode, and mount IDs with a fail-closed recovery matrix —
  proportionate only if a torn transfer may never be re-run.
- **Adjudication resume fails closed on any sidecar mismatch**
  (`adjudication_resume_mismatch`, specs/state.md §564-573); the spec itself
  anticipates the alternative: "unless a future explicit force-rerun path is
  used".

The remaining audit findings (package cycles, god modules, duplicate-helper
drift, error-style inconsistency, dead migration machinery beyond the track's
M1 list) are routed to the M1 extension, the MC phase, the M4 scope note, or
the not-selected backlog — see below.

## Target Contract: At-Least-Once Provider Attempts

ML-0 amends the normative text before any code changes. The contract after
amendment:

- Provider attempts are at-least-once. Crash, interrupt, or torn-write
  recovery discards the partial attempt (evidence retained where cheap,
  marked `interrupted`), allocates the next ordinal, and re-runs the step
  through normal control flow. Re-execution is an accepted cost, consistent
  with the track's principle-28 "loud re-spend" bound: recovery-triggered
  re-runs emit a named diagnostic.
- Attempt ordinals still never identify two different executions: ordinals
  remain monotonic per scope, and a discarded partial attempt's directory is
  never reused for new content. What is dropped is crash-durability of the
  allocation *record*, not uniqueness of the identity.
- Attempt records and prompt-dependency evidence remain audit-only (already
  non-authoritative per spec) and become best-effort: their absence or
  incompleteness after a crash is not a failure.

Explicitly preserved (not loosened):

- **Managed provider jobs (v2.13):** external jobs carry real external cost;
  runtime-owned recovery without relaunch is unchanged.
- **Declared resource transitions (v2.14):** idempotency-key audit ledgers
  are the correct replay mechanism and are the model ML moves *toward*, not
  away from.
- **Root/imported workflow checksum guards** and resume projection identity
  auditing: resuming across changed source remains rejected.
- **Artifact lineage/versioning** (`artifact_versions`/`consumes` and private
  ledgers): semantic dataflow correctness, unrelated to provider cost.
- **Atomic state writes** (temp + rename): unchanged; fsync becomes policy
  rather than a per-feature escalation.
- **Peer-group messaging ledgers:** append-before-offer ordering serves
  cooperative messaging semantics and survives; only the quarantine path
  around the group visit changes.
- **Committed-result reuse:** a provider boundary whose result committed
  before the interruption still restores on resume without re-invocation
  (`specs/state.md:173-175`); discard-and-rerun applies only to attempts
  in flight at the interruption. This is the exact property Q0's Task-6
  E2E gate asserts ("provider invocation count remains one" when
  interrupted after the committed boundary); ML must keep that fixture
  green unchanged.

## Amended Phase Sequence (proposed)

| Phase | Work | Entry condition | Completion gate |
| --- | --- | --- | --- |
| M0 | Green baseline (unchanged) | none | unchanged |
| M1 | Estate shrink + inventory extension below | M0 complete | unchanged gate, totals include extension items |
| ML | Provider at-least-once loosening (new) | M1 complete; owner adopts at-least-once; ML-0 spec amendment accepted | per-tranche gates below; crash-resume E2E green; broad non-security suite green |
| MC | Common-helper consolidation (new, small) | M0 complete; schedulable beside M1/ML | net LOC strictly negative; drift sites collapsed; touched-module suites green |
| MR | Scheduled structural refactors (new) | per-tranche: MR-5a after M0; MR-1 after ML-1; MR-2 after ML; MR-3 with/after ML-2; MR-4 Q-coordinated | behavior-preserving golden-parity gates per tranche; MR-1..MR-3 complete before M3 starts |
| M2 | Persistence-parsimony design (unchanged) | as in track, after ML | unchanged — ML shrinks the resume special-case surface M2 must cover |
| M3 | Persistence implementation (unchanged) | unchanged | unchanged |
| M4 | Structural decomposition (+ scope question) | unchanged | unchanged; owner decides whether boundary redraw joins |

Concurrency: ML, MR-1..MR-3, and MR-5b/c touch executor/resume/state
surfaces and are exclusive with M3's domain by the track's existing rule —
they run strictly before M3 (MR-1..MR-3 may overlap the M2 design window,
which is design-only). They additionally enter only after the active Q0
implementation gate: Q0's plan lists `orchestrator/state.py`,
`workflow/provider_attempts.py`, `workflow/prompt_dependency_evidence.py`,
`workflow/call_frame_state.py`, and `orchestrator/providers/` as protected
owners with an external-edit collision protocol, and may itself touch
`workflow/executor.py` and `workflow_lisp/lexical_checkpoint_restore.py`
on RED evidence. ML-0 (doc-only), M0/M1, MC, and MR-5a are Q0-safe now,
except MC defers call-site migration in any file on Q0's protected/if-RED
list until Q0 closes. MR-4 touches frontend compiler surfaces and is
scheduled only in coordination with the Q-track. After Q0 closes, ML and
the remaining MR tranches interleave freely with Q1-Q2, which churn
frontend/prompt surfaces only.

## Integration With The Post-Stage-8 Roadmap Structure

The post-Stage-8 estate is two roadmaps: the active Q-track
(`docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`,
language quality, Q0 in flight) and the proposed M-track substrate track
this document amends. This amendment deliberately creates no third
roadmap; it enriches the M-track, and the Q-track's selection authority,
bounds, and stage order are untouched.

Fold-in mechanics, two steps — step 2 executed 2026-07-26:

1. **Pre-decision (historical):** this document stood as the subordinate
   proposal; the track pointed at it and carried the consolidated pending
   decisions. Nothing executed from either document without a component
   plan.
2. **Adoption (done 2026-07-26):** ML/MC/MR and the M1 extension are
   inlined into the track's phase table, phase sections, bounds
   (deletion-bound exceptions now name MR-4; the isolation-freeze wording
   points ML-3 at its pending ruling), and concurrency rules; this
   document's status is flipped to adopted/evidence-record; the
   `docs/index.md` entries are updated and the routing gate rerun. The
   track owns the executable sequence; this document owns tranche scope,
   gates, and the audit evidence.

Cross-track junctions (semantic, beyond scheduling):

- **Q0 → ML:** ML preserves committed-result reuse (previous section), so
  Q0's interruption/resume E2E stays green under ML; conversely ML's
  executor/state tranches wait for Q0's gate because they edit Q0's
  protected owners.
- **ML → M2 depth:** the track's pending M2 depth decision (pure-replay
  only, or memo-first) partially presupposes this amendment: M2(b)'s
  memo-first resume re-pays memo misses, which is only contractually
  coherent once at-least-once is adopted. If the owner declines ML-0, the
  M2 depth decision effectively collapses to (a) pure-result replay only.
- **Q3 → M2:** unchanged existing junction (identity definition feeds memo
  keys).
- **MR-4 ↔ Q1:** one scheduling seam the owner should place explicitly:
  running MR-4 (compiler session state) between Q0 and Q1 gives Q1's
  prompt-core elaboration a reentrant, session-owned foundation; running
  it after Q1 avoids delaying the language work but builds Q1 on the
  module-global registers. Either is workable; concurrent execution is
  not.
- **MR-2 → M4:** unchanged — pipeline extraction defines the seams M4
  splits along.

Resulting lane picture (entry conditions abbreviated):

| Window | Q-track | M-track |
| --- | --- | --- |
| now | Q0 implementation | M0; then M1(+extension); MC (minus Q0-listed files); MR-5a; ML-0 upon adoption |
| after Q0 gate | Q1 (or MR-4 first, owner call) | ML-1..ML-4 (ML-3 per isolation ruling); MR-1..MR-3; MR-5b/c; MC remainder |
| after Q3 | Q4 | M2 design (consumes Q3 identity + ML contract) |
| then | — | M3 (exclusive), M4 (go/no-go, + scope question) |

The historical numbered roadmap needs no change: its post-Stage-8 handoff
already delegates successor selection, and both current tracks plus this
amendment are indexed from `docs/index.md`.

## Phase ML: Provider At-Least-Once Loosening

Each tranche requires its own component plan (TDD, RED fixtures first) per
track rules; this section fixes scope and gates only.

### ML-0 — Spec amendment (contract pivot, no code)

Amend `specs/state.md`: §Provider Prompt-Dependency Attempt State And Resume
(drop crash-durable allocation and closed append-only event sequences;
ordinals become plain monotonic state), §Provider-Supervision and
§Provider-Peer-Group resume (quarantine → interrupted-visit
discard-and-rerun), the later-landed §Phased Contract Delivery route (whole
interrupted visit → fresh attempt while same-attempt materialization retry
stays unchanged), §Adjudicated Provider State (mismatch → exact-scope re-run),
and the v2.10 session-quarantine bullets. Touch `specs/providers.md` where
attempt allocation/recovery is referenced; align `specs/cli.md`,
`specs/observability.md`, `specs/versioning.md`, and
`specs/acceptance/index.md`. Grep-audit remaining active quarantine references
across `specs/` and update `docs/index.md` clarification rows.

The Provider-Isolation Bundle-Transfer Journal is explicitly not amended.
ML-3 is deferred under the owner-directed security exclusion; its existing
contract and implementation remain unchanged until a separate re-entry act.

Gate: ordered independent specification and quality reviews of the amended
spec text; capability/status rows updated.

### ML-1 — Quarantine → discard-and-rerun

Delete the three resume-guard detector/executor pairs
(`workflow/executor.py:2184-2395`, dispatch at 3034-3067;
`workflow/resume_planner.py:259-614` and its three error-type constants) and
the session variant. Resume treats a running provider/session/supervision/
peer cursor as an interrupted attempt: mark visit metadata `interrupted`
(evidence-only), clear the cursor, re-enter the step. Named diagnostic per
re-spend (principle 28).

Gate: kill-mid-provider crash-resume E2E fixture proving the run completes
with a fresh attempt and one named re-spend diagnostic per family
(ordinary/session/supervision/peer); quarantine error types absent from
runtime; supervision/peer resume suites rewritten smaller.

### ML-2 — Allocator to plain counter + one run-lifetime lock

Replace per-mutation cross-process coordination with one exclusive
`RUN_ROOT/run.lock` (flock, fail-fast) acquired at `run`/`resume` start —
this also closes the real hazard (concurrent resume of one run) that the
current per-mutation locks only partially cover. Then delete: per-scope
lifecycle event ledgers and schema-2.2 lifecycle validation
(`provider_attempts.py:998-1597`), repair barrier
(`state.py:237-240,373-384`), capability sentinels (`state.py:28-30` and
cross-package importers), durable-mode latch and reload-merge
(`state.py:1317-1340`), the `_from`/`_already_process_locked` method triples,
and `provider_attempt_process_locks`/`record_only_publication_locks`
(`state_locking.py:26-44`; `durable_atomic_write` survives as the shared
atomic-write primitive). Allocation becomes: in-process lock, increment
`last_allocated_ordinal`, ordinary atomic write. Fold the
`RunState.to_dict`/`from_dict` consolidation into the same touch.

Gate: concurrent-resume rejection fixture (second process fails fast on
`run.lock`); allocation monotonicity property test; state.py sheds its
allocator-lock layers with suites green.

### ML-3 — Bundle transfer journal collapse (owner-gated)

`isolation_bundle_broker.py` 2,695 → target ≤ ~300 LOC:
write-tmp/fsync/rename/validate; recovery = canonical file present with
matching digest → accept, else delete partials and re-run the attempt.

**Bound conflict:** the track freezes provider-isolation code ("days old;
let it stabilize"). ML-3 needs an explicit owner exception or waits for the
freeze to lift; ML-1/ML-2/ML-4 do not depend on it.

Gate: torn-transfer fixtures (missing/partial/duplicate/wrong-digest) all
converge to accept-or-rerun; journal recovery matrix and its test estate
retired.

### ML-4 — Adjudication resume mismatch → re-run

Replace `adjudication_resume_mismatch` fail-closed reconciliation
(`workflow/adjudication_resume.py`) with: reconcile if all sidecars are
consistent, otherwise discard the visit's adjudication sidecars and re-run
the adjudicated step (named re-spend diagnostic).

Gate: mismatch fixtures (each sidecar class) re-run instead of failing;
consistent-state fixtures still reuse without re-invocation.

## M1 Inventory Extension

Additional zero-consumer or vestigial items for M1's component plan, beyond
the track's retirement/run-store list (evidence at 2026-07-26 checkout):

1. `orchestrator/fsq/queue.py` dead half (`QueueManager`, `write_task`,
   `move_to_processed`, `move_to_failed`; only `WaitFor` is live via
   `exec/step_executor.py:15`) plus `fsq/__init__.py` re-exports. Resolve
   `specs/queue.md` in the same change (spec-precedence: amend, then delete).
2. Drain-gate cluster: `workflow_lisp/migration_parity.py` (3,393 LOC),
   `route_readiness.py`, `post_wcc_inventory.py`, their `cli/commands`
   wrappers and verbs (`cli/main.py:460-518,617-625`) whose defaults
   hardcode drained-run artifact paths.
3. Gate scripts `scripts/provider_prompt_dependency_broad_gate.py` (103 KB)
   and `scripts/validate_prompt_dependency_evidence.py` (thin wrapper over
   the live validator).
4. Vestigial multi-frontend dispatch: `frontend_kind` guards at
   `workflow/executor.py:483-489,587-589`, `frontend_origins.py:436-438`,
   `validation.py:3133-3135,6532-6535`; the only producer is the constant
   `"workflow_lisp"` (`workflow_lisp/lowering/core.py:2446`).
5. Packaging: exclude `orchestrator/demo/` (top-level `import torch`,
   undeclared; `.pt` fixture blobs) from the wheel or gate behind an extra.
6. Loader strays: `exceptions.py:59-63` docstring, orphaned
   `orchestrator/__pycache__/loader.cpython-311.pyc` (the broken test imports
   are already M0 item 1).

## Phase MC: Common-Helper Consolidation

Motivation is measured drift, not tidiness: three functions named
`_atomic_write_text` with three durability semantics
(`workflow/executor.py:7096-7110` leaks its temp file and never fsyncs;
`workflow/adjudication/utils.py:147-168`; `state_locking.durable_atomic_write`
is the only hardened one); ~12 canonical-JSON/sha256 clones disagreeing on
`default=str`/prefixing/truncation in a codebase that compares those digests;
terminal-status predicates in 9+ files with four divergent membership sets
(report vs monitor vs resume can disagree about the same run); ~20 strict-int
guards including five private re-definitions; timeout ladders differing on
`isfinite` across five provider modules.

Scope: one small `orchestrator/_common/` package — `io_atomic` (promote
`durable_atomic_write` + non-fsync variant), `canonical`
(`canonical_json_dumps`, `sha256_json`), `validation` (`closed_mapping`,
`nonempty_string`, `require_int`, `require_timeout_seconds`), `status`
(terminal/settled predicates) — plus predicate consolidation on owning
types: session-snapshot predicate methods replacing the literal ladders
copy-pasted four times in `providers/executor.py:1017-1024,2305-2498`, and
one `run_state_path`/`is_run_dir` pair with a single recorded symlink
policy for `cli/commands/report.py:53-62` and `monitor/scanner.py:42-44`
(today two policies diverge, so report and monitor disagree about symlinked
runs). Then mechanical migration of the ~60 call sites and deletion of
every private clone. Dashboard call sites stay untouched under the track's
dashboard exclusion; isolation fd-io consolidation is recorded but frozen
with ML-3's isolation ruling.

Gate: net LOC strictly negative (track's deletion-over-refactoring bound);
grep shows no residual private clones; touched-module suites green.

## Phase MR: Scheduled Structural Refactors

Behavior-preserving refactors with recorded correctness stakes; none is
cosmetic. Each tranche requires its own component plan with RED/golden
parity fixtures. Sequencing lives in the phase table and concurrency rules
above; MR-1 through MR-3 must complete before M3 starts (same exclusivity
domain).

### MR-1 — Provider-family descriptor parametrization

After ML-1 deletes the quarantine third, collapse the remaining
session/supervision/peer twins — prepare-visit, update-visit-metadata,
execute, finalize-settlement (`workflow/executor.py:1855-2117,9735-10105`,
~600 duplicated lines) — onto one sequence parametrized by a family
descriptor (family literal, sidecar layout, settlement ordering). The
component plan must record ONE settlement ordering: today peer checks
`current_step` before publishing artifacts (`executor.py:10008-10019`)
while supervision checks after (`executor.py:9886-9931`); the divergence is
undocumented and presumed accidental.

Gate: per-family golden parity fixtures pass against the unified sequence;
the chosen settlement ordering asserted for both families; net LOC
negative.

### MR-2 — Attempt pipeline and step-loop extraction (M4 prep)

Extract the per-attempt provider pipeline (compose → invoke → validate →
commit) from `_execute_provider_with_context` (~713 lines,
`workflow/executor.py:5816-6529`) with MR-1's family paths as consumers,
and split `_execute_step_loop` (~537 lines, `executor.py:3279-3816`) into
resume-activation and dispatch stages. The in-repo staged idiom
(`workflow_lisp/build.py`) is the template. This deliberately shrinks M4's
later work to module moves.

Gate: golden-run parity (diagnostics, artifacts, settlement results)
between pre- and post-extraction execution on recorded fixture runs.

### MR-3 — Call-frame lifecycle unification

`CallFrameStateManager` re-implements `StateManager`'s
start/heartbeat/clear/fail `current_step` mutations with its own dict
shapes (`workflow/call_frame_state.py:137-139,380-418` vs
`state.py:1804-1884`); resume reads both writers, so shape drift is a
latent correctness bug. Extract shared lifecycle mutation helpers operating
on `RunState`; each manager keeps only its persistence strategy.

Gate: one shared shape-builder is the only producer of `current_step`
payloads (grep gate); call-frame and resume suites green.

### MR-4 — Compiler session state (Q-track-coordinated)

Replace module-global compile-phase registers with an explicit per-compile
session: elaborator actives (`workflow_lisp/expressions.py:784-853`, ten
save/mutate/restore globals after Q1), carrier metadata
(`loop_state.py:42-143`), specialization requests
(`procedure_typecheck.py:109-124`), and intrinsic lowering counts
(`lowering/control_dispatch.py:73-91`) move onto session/context objects.
Closes a live reentrancy/staleness hazard for the long-lived LSP server.
The fifth originally scoped item — the path-keyed `lru_cache` over file
content in `lowering/pure_projection.py` — was confirmed as a live staleness
bug and fixed ahead of this tranche by L0 (`0549625e`, content-keyed cache
with both-direction tests). MR-4 inherits that cache as already
content-correct and does not relocate it merely to make process-local cache
lifetime match compile-session lifetime.

Entry: scheduled only in coordination with the Q-track and L-series
owners; not concurrent with Q1 elaboration churn; must complete before or
with L3, whose per-source entry selection multiplies per-process compiles
over the state MR-4 sessionizes. Gate: LSP double-compile reentrancy
fixture (one server process, sequential recompiles with edits, no state
bleed); grep gate: no module-level mutable phase state on the compile path.
May be net-LOC positive; recorded as the second exception to the
deletion-over-refactoring bound (owner decision 4).

### MR-5 — Scoped error-hygiene rider

Deliberately not the full error-contract unification (which stays
unselected): (a) replace the kwarg-compat `TypeError`-message-sniffing
ladder around provider invocation (`workflow/executor.py:6853-6898`, 2^3
fallback shapes, silent-swallow and double-execution hazard) with one
invocation signature — schedulable immediately after M0; (b) riding ML-2's
`state.py` touch, a typed exception family replacing the duplicated bare
builtins (`RuntimeError("State not initialized")` ×20,
`TypeError("ProviderAttemptScope required")` ×6); (c) one error-dict
constructor in `providers/executor.py` replacing the five copy-pasted
timeout payloads (lines 764, 856, 871, 978, 2372).

Gate: sniffing ladder absent (grep); provider-invocation suites green;
error payload shapes byte-identical on golden fixtures.

## M4 Scope Question (owner decision, no work selected here)

The audit adds one candidate to M4's existing executor/validation split,
behind the unchanged M4 go/no-go (MR-2 deliberately shrinks M4's blast
radius beforehand):

- **Neutral IR package.** `workflow` ↔ `workflow_lisp` is bidirectionally
  cyclic (48+ frontend→runtime edges; reverse edges include
  `lexical_checkpoint_restore.py:845` constructing `WorkflowExecutor`;
  `executable_ir.py:1596` bans frontend objects while `:1738` imports the
  frontend). Extracting the compiler middle-end (`core_ast`, `surface_ast`,
  `semantic_ir`, `executable_ir`, `runtime_plan`, …) into a neutral package
  and relocating checkpoint runtime services out of the frontend kills both
  cycles. Conflicts with the track's "WCC middle-end modules (stable)"
  out-of-scope line, hence owner-gated.

## Not Selected By This Amendment

Recorded for later selection; no phase includes them: full repo-wide error
contract unification beyond MR-5 (four coexisting failure styles in
`providers/executor.py`; span-dependent exception class at
`workflow_lisp/contracts.py:1541`; snake_case codes raised as `ValueError`
messages across the adapters family), executor collaborator injection
(`WorkflowExecutor.__init__` self-building ~15 collaborators — revisit at
M4), `providers/executor.py` prepare/execute lifecycle-variant
consolidation (candidate MR tranche once ML settles the invocation
surface), dashboard `FileReference` predicates and dashboard-side scanner
migration (excluded by the track's dashboard bound), isolation fd-io
consolidation (frozen with ML-3's ruling), clock-injection
standardization, secrets-source injection, and the descriptor-relative
no-follow checkpoint-open discipline review (posture question for ML-0's
review to note, not change).

## Verification

Track verification rules apply unchanged: narrowest owning checks first,
fresh command output as the only evidence, broad non-security suite at every
phase gate, `tests/test_workflow_lisp_drain_roadmap_routing.py` whenever
roadmap or routing docs change. ML additionally requires, at ML-1 and again
at phase close, one live kill-mid-provider crash-resume E2E and one
orchestrator demo smoke run, since ML changes workflow/runtime mechanics.

## What This Makes Harder

- A crash during a provider attempt now re-pays that attempt's provider cost
  (and its latency) instead of preserving it — accepted by the driver
  direction, bounded by named re-spend diagnostics.
- Re-running an interrupted agent attempt re-executes its workspace effects;
  this is identical in kind to today's retry-on-failure, but crash-window
  re-runs become more common. Workflows with DSL-level git rollback semantics
  keep their existing repo-local coexistence rules.
- The per-attempt forensic ledger weakens: lifecycle event sequences and the
  journal's recovery matrix disappear, so post-hoc reconstruction of a
  crashed attempt's exact progress gets coarser (visit metadata and logs
  remain).
- If a future deployment ever introduces genuine concurrent multi-process
  writers to one run root, the single run-lifetime lock model must be
  revisited; the deleted machinery should not be resurrected piecemeal but
  redesigned against the then-real topology.
- Formally reviewed exactly-once artifacts (bundle-journal contract,
  quarantine reviews, attempt-lifecycle evidence) become historical; their
  review lineage stays in git and plan docs.

## Appendix: Condensed Audit Inventory (2026-07-26)

High-severity findings not already covered above, with owning route:

| Finding | Evidence | Route |
| --- | --- | --- |
| `workflow/executor.py` 10,111 LOC single class; `_execute_provider_with_context` ~713 lines; `_execute_step_loop` ~537 | scout FC-1/FC-2 | MR-2 (extraction), then M4 (module split) |
| `workflow/validation.py` 6,677 LOC dual-concern validator | scout MOD | M4 |
| `state.py:672-1082` `_commit_validated_provider_result_from` ~410 lines, 13 params, mid-body imports invert layering | scout FC-3 | shrinks in ML-2/ML-3 |
| Session/supervision/peer family triplication ~600 lines with drift | scout FC-4 | ML-1 deletes quarantine third; MR-1 parametrizes remainder |
| providers ↔ workflow cycle (`isolation_lifecycle.py:14-20` ↔ `provider_attempts.py:760,1162`) | scout ARCH | mostly dissolves with ML-2 sentinel removal |
| Private `_*_CAPABILITY` sentinels as cross-package authorization | `state.py:28-30` | ML-2 |
| 9 atomic-write implementations, 3 durability semantics | scout ABS-1 | MC |
| ~12 canonical-JSON digest clones with semantic drift | scout ABS-3 | MC |
| Terminal-status predicate divergence across report/monitor/resume | scout COND-1 | MC |
| Four error styles in `providers/executor.py`; no typed exceptions in `state.py` | scout ERR-1/ERR-3 | MR-5 (scoped rider); full unification not selected |
| Compiler module-global phase state; LSP reentrancy hazard | scout DI-1/DI-2/DI-7 | MR-4 (Q-track-coordinated) |
| Dead estate beyond track M1 list (fsq queue, drain gates, gate scripts, frontend_kind, demo packaging) | scout ZOMBIE | M1 extension |

Medium/low findings not named above (error-pattern families beyond MR-5,
DI seams, parallel registry hierarchies) are retained in the session audit
record and can be re-derived by re-running the category audit.
`CallFrameStateManager` lifecycle duplication is scheduled as MR-3;
condition-predicate families land in MC.
