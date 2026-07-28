# Q5 Phased Turn-Queue Coordinator Diagnosis Task

- **Status:** owner-directed task brief (2026-07-28); execution requires no new
  design authority, but any fix it motivates lands under the stopped Q5
  implementation plan's own review discipline
- **Owner surface:** the Q5 phased-delivery acceptance path —
  `docs/design/workflow_lisp_phased_contract_delivery.md` and
  `docs/plans/2026-07-27-workflow-lisp-phased-contract-delivery-implementation-plan.md`
  (its stop record governs; see Constraints)
- **Kind:** bounded, provider-free diagnosis. Not a re-attempt of the
  acceptance proof, not a refactor, not a Q5 status change.

## Problem

The Q5 real-provider acceptance path has failed twice at the same seam with no
root cause established:

1. **2026-07-27 acceptance attempt (plan task 13):** the live provider session
   sat blocked at the phased driver handshake for roughly 55 minutes with the
   phase ledger silent from 10:33 onward. No timeout, no structured failure, no
   diagnostic surfaced. The run was abandoned; the provider process was gone
   when inspected.
2. **2026-07-28 combined invalid→valid real-provider proof:** failed. The
   failure is durably recorded by the `Record phased consumer gate stop`
   commit, which added a stop record to the Q5 implementation plan explicitly
   forbidding split-proof substitution, marking Q5 complete, or starting
   Task-14 closure from the stop record itself. (Commit currently exists in
   the active working lineage, not yet on the canonical repository's main;
   cite it by its stop-record section once transplanted, not by hash.)

Q5's implementation is otherwise fully landed and activated (mainline through
`Activate phased contract delivery`). The design and implementation plan are
accepted. Only the real-provider acceptance evidence chain is open.

## Why This Is a Design-Level Contradiction, Not Just a Flaky Run

The accepted Q5 design makes provider waits total: deadline-aware `start` /
`offer` / `offer_close`, fail-closed capability and deadline admission, and
total finite provider timeouts were explicitly implemented (mainline commits
`Accept total finite provider timeouts`, `Add deadline-aware interactive start
outcomes`, `Close phased provider deadline races`). Under that contract **a
silent multi-hour hang at the handshake should be impossible**: every wait
state in the coordinator/adapter path is supposed to be deadline-bounded, and
every deadline expiry is supposed to surface as a structured outcome in the
phase ledger.

The observed stall therefore implies at least one of:

- **H1 — an unbounded wait:** some wait state in the
  `PhasedProviderAttemptCoordinator` or the
  `interactive_terminal_turn_queue.v1` adapter path
  (`start`/`offer`/`offer_close`/`join`/`abort`) is reachable without a
  deadline attached (e.g., a pre-admission handshake step, a join on an
  already-dead peer, or a state entered only on a specific interleaving);
- **H2 — a swallowed expiry:** a deadline fired but its outcome was not
  surfaced — no ledger entry, no terminal outcome, no diagnostic — leaving the
  run indistinguishable from a healthy long wait;
- **H3 — the coordinator path is clean** and the failure is provider-side
  behavior (the provider never engaged the handshake in a way the adapter
  could observe), in which case no amount of coordinator code changes will
  help and the lever is the acceptance provider itself.

The task is to discriminate between H1/H2 and H3 with a cheap, deterministic,
provider-free experiment before any third real-provider attempt is made. A
blind re-run is explicitly ruled out: it spends a live provider session to
reproduce a failure we cannot yet interpret.

## Task

Drive the **real** `PhasedProviderAttemptCoordinator` and the real
`interactive_terminal_turn_queue.v1` adapter through the full invalid→valid
attempt sequence using a **scripted synthetic provider** (a deterministic
driver standing in for the provider side of the turn queue), with every
deadline path instrumented. Concretely:

1. **Enumerate wait states.** Produce a complete list of every blocking wait
   the coordinator/adapter path can enter between attempt admission and
   terminal outcome, from the code, not from the design's claims. For each:
   the deadline that bounds it, where that deadline is admitted, and where its
   expiry surfaces (ledger entry / outcome / diagnostic).
2. **Prove or refute totality executably.** For each enumerated wait state,
   an executable fixture forces the synthetic provider to stall at exactly
   that point and asserts the wait terminates within its deadline **and** the
   expiry surfaces as the contract requires. A wait state that cannot be
   forced must be shown unreachable, not skipped.
3. **Replay the observed failure shapes.** Script the synthetic provider to
   reproduce the two observed behaviors — (a) never engaging the handshake,
   (b) engaging then going silent mid-phase — and record what the coordinator
   actually does, including exact ledger contents. Compare against the silent
   ledger observed on 2026-07-27.
4. **Validate ledgers offline.** Run the existing offline phased-ledger
   validation over every fixture's ledger; a silent or incomplete ledger in
   any forced-stall fixture is itself a confirmed H2 finding.

The diagnosis is complete when either a concrete defect (H1/H2) is identified
with a failing fixture, or every wait state is proven deadline-bounded and
surfacing (H3), with the fixture set as evidence.

## Outcome Routing

- **H1/H2 — coordinator/adapter defect found:** fix it under the stopped Q5
  implementation plan's discipline (TDD, the failing fixture becomes the
  regression test, ordered spec-then-quality review, reviewed-bytes commit).
  Only after the fix lands may the combined invalid→valid real-provider proof
  be re-attempted, and the re-attempt inherits the instrumentation so a
  recurrence is interpretable.
- **H3 — coordinator provably clean:** the failure is provider-behavioral.
  Stop; do not add code. Escalate to the owner with the evidence, for a
  decision among: a different acceptance provider model/effort, or a
  prompt-side change routed through the prompt-change queue
  (`docs/plans/workflow_prompt_change_queue.md`) for explicit owner approval.
- In both branches, Q5's recorded status does not move until the real
  combined proof passes. The stop record stays honest.

## Constraints

- The stop record in the Q5 implementation plan governs: no split-proof
  substitution, no marking Q5 complete, no Task-14 closure from this work.
- No provider prompt or prompt-queue changes without explicit owner approval.
- No speculative refactoring of the coordinator or adapter; the only code
  changes admitted are a confirmed-defect fix plus its regression fixtures.
- The synthetic provider is test infrastructure: it must exercise the real
  adapter surface (no bypassing the turn-queue capability boundary, no
  mocked-out coordinator internals).
- Standard commit discipline: pathspec commits of independently reviewed
  bytes only.

## Verification

- The wait-state enumeration is checked against the code by the reviewer, not
  accepted from prose.
- Every fixture runs under the narrowest relevant pytest selectors;
  `pytest --collect-only` on any new test modules.
- Offline ledger validation passes (or fails diagnostically) for every
  fixture-produced ledger.
- The final report states, per wait state: bounded/unbounded, surfaced/silent,
  fixture path, and verdict — and ends with exactly one of the two outcome
  routings above.

## Non-Goals

- No third real-provider acceptance attempt before this diagnosis concludes.
- No changes to Q5 identity/evidence contracts, the T1‖T2==C cut, or the
  materialization-retry lifecycle.
- No new diagnostic authority: findings surface through the existing ledger,
  outcome, and report contracts.

## Execution Environment Addendum (2026-07-28, owner-verified)

Read this before doing any git forensics; the confusing repository state has
been investigated and is explained here. Hashes below are execution-time
evidence pointers for this task, verified 2026-07-28.

1. **The canonical repository's HEAD is intact and authoritative.**
   `/home/ollie/Documents/agent-orchestration` at `bceb03e4` (`Activate phased
   contract delivery`, tip of `main`) contains the complete Q5 implementation:
   `git ls-tree HEAD orchestrator/workflow/` lists
   `provider_phased_delivery/`, and nine phased test modules exist at HEAD
   under `tests/`.
2. **The canonical working tree and index are a stomped foreign snapshot —
   not a revert of Q5.** The staged ~37k-line deletion of the phased
   implementation and the large unstaged additions (provider isolation
   surfaces, etc.) do not match any local branch tree; they are residue of a
   cross-workspace sync while multiple agents shared this checkout. Nobody
   decided to remove Q5. Treat the working tree and index as untrusted.
   **Do not** run `git restore`, `git reset`, `git checkout -- .`,
   `git clean`, `git stash`, or any commit in this checkout — the foreign
   snapshot may contain another agent's live work, and reconciliation is a
   separate owner-coordinated task. Ignore the stray `=` file and
   `pytest-of-ollie/` directories.
3. **The "active working lineage" is a fast-forward superset of canonical
   main**, located at `/home/ollie/.tmp/mr4-plan-pCBIen/repo` (a live
   workspace owned by another agent — read from it, never write to it). Its
   history is exactly canonical `bceb03e4` plus, in order: `3fc3a09e Record
   phased consumer gate stop` (parent verified = `bceb03e4`), the MR-4
   compiler-session commits, and the accepted L3 selection design. The stop
   record this brief cites is the plan-text change in `3fc3a09e`; read it
   with `git -C /home/ollie/.tmp/mr4-plan-pCBIen/repo show 3fc3a09e`.
4. **Prescribed execution substrate:** do not attempt the diagnosis in the
   canonical checkout. Make a fresh clone of
   `/home/ollie/Documents/agent-orchestration` in your own scratch area,
   check out `main` (`bceb03e4`) — the coordinator, adapter, and all phased
   tests are present there — and optionally
   `git fetch /home/ollie/.tmp/mr4-plan-pCBIen/repo 3fc3a09e` for the stop
   record text. All diagnosis fixtures, instrumentation, and any
   confirmed-defect fix are developed and committed in that clone; landing
   them anywhere else is a later, owner-coordinated transplant step.
5. The untracked-but-present copy of
   `docs/plans/2026-07-27-workflow-lisp-phased-contract-delivery-implementation-plan.md`
   in the canonical working tree is part of the same foreign snapshot; the
   authoritative version for this task is the one at canonical HEAD, and the
   stop-record amendment to it lives only in `3fc3a09e` for now.
