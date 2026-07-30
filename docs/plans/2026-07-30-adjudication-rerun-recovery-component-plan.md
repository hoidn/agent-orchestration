# Adjudication Rerun Recovery Component Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan
> task-by-task. Use `superpowers:test-driven-development` for every behavior
> change. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute ML-4 by replacing fail-closed adjudication-sidecar mismatch
with exact-scope cleanup and a fresh ordinary adjudicated-step attempt.

**Architecture:** Reconciliation still reuses a visit only when every
authoritative state field and sidecar agrees. A mismatch classifies the old
visit as discarded, but recovery proceeds only when the runtime can prove the
exact run-owned step/visit scope to remove; it then clears only that partial
adjudication projection and re-enters normal dispatch. The re-spend is exposed
as `adjudication_state_mismatch_rerun`.

**Tech stack:** Python 3.13, pytest, adjudication state/sidecars, atomic
filesystem operations, and Workflow Lisp end-to-end fixtures.

**Status:** active. ML-4 is current after ML-2 closed at
`b8783f66db4680bdec048e1b54ac14c1ae8b4d1b`, tree
`b833b03cb91396cddf64a12cbbbc8d016cd306ad`; Task 1 closed at
`c45928f4399dbe1cb1105136a320638b95b9c3a8`, tree
`c0ea1821d573ecfe9d3c5d98b1cab5d02be3e7f3`; Task 2 closes through the
commit `b3370858b27b7d3924556193e499b2c6de106750`, tree
`d26c9a6399a5c400a3d36aeaf9bf024a9891bc9d`; Task 3 closes at
`ed19624cae6b8cc89c930c29ec7a3c6cc581d88f`, tree
`2de3a125f357a2daa5db64e5986da11cd11cf2c6`, and Task 4 is current.

## Authority and bounds

This plan executes ML-4 from the adopted provider at-least-once amendment.
`specs/state.md` owns reconciliation and rerun semantics.

- Fully consistent completed adjudication continues to reuse without provider
  invocation.
- Root/imported workflow checksums, projection identity, bound inputs,
  checkpoints, output contracts, candidate validation, scoring, and promotion
  preimage checks are unchanged and run before recovery can launch a provider.
- Only sidecars belonging to the exact mismatched run/step/visit may be
  removed. Unknown, ambiguous, escaping, or aliased paths fail closed and make
  no mutation.
- No candidate output, score, ledger row, or promotion from the discarded
  visit may become result or lineage authority.
- Provider isolation, security surfaces, dashboard, Q/L gates, and ML-3 are
  excluded.

What this makes harder: a torn adjudication may repeat candidate and evaluator
calls and loses incomplete visit-local sidecars. The named diagnostic records
that cost; promotion and ordinary state publication remain atomic.

## Task 1: Classify reconciliation outcomes

**Files:**

- Modify: `orchestrator/workflow/adjudication_resume.py`
- Modify: `tests/test_adjudicated_provider_runtime.py`
- Modify: `tests/test_adjudicated_provider_outcomes.py`

- [x] Convert existing mismatch fixtures into a closed
  `reuse | rerun_exact_scope | integrity_error` classification.
- [x] Add RED cases for each mismatch family plus unknown/ambiguous/escaping
  scope. Only exact-scope mismatches are recoverable.
- [x] Run:

  ```bash
  pytest -q \
    tests/test_adjudicated_provider_runtime.py \
    tests/test_adjudicated_provider_outcomes.py \
    -k 'resume_mismatch or rerun_exact_scope or integrity_error'
  ```

  Expected RED: exact-scope mismatches still return
  `adjudication_resume_mismatch`; integrity negatives remain green.
- [x] Keep consistent-state reuse and all source/projection guard precedence
  unchanged.
- [x] Run focused tests, ordered specification then quality review, and commit
  with subject `Classify adjudication rerun recovery`.

Task 1 candidate evidence: the new decision API first failed collection, and
the fresh-sidecar integrity case then failed on the legacy diagnostic. The
exact plan selector now passes 9 tests; both owning modules pass 94, the
adjacent resume module passes 12, and compile/diff checks pass. Exact mismatches
remain transitional failures until cleanup and redispatch land; no provider is
launched by this task. Ordered review returned `ML4_TASK1_SPEC_APPROVED`
followed by `ML4_TASK1_QUALITY_APPROVED`, with no material findings and no
replay.

## Task 2: Discard one exact partial visit

**Files:**

- Modify: `orchestrator/workflow/adjudication_resume.py`
- Modify: `orchestrator/workflow/adjudication_runner.py`
- Modify: `orchestrator/workflow/adjudication/paths.py`
- Modify: `orchestrator/workflow/adjudication/utils.py`
- Modify: `orchestrator/workflow/adjudication/promotion.py`
- Modify: `tests/test_adjudicated_provider_runtime.py`

- [x] First add
  `test_exact_mismatch_discards_only_bound_adjudication_visit` and
  `test_unprovable_cleanup_scope_makes_no_mutation`. Run:

  ```bash
  pytest -q tests/test_adjudicated_provider_runtime.py \
    -k 'discards_only_bound_adjudication_visit or unprovable_cleanup_scope'
  ```

  Expected RED: the exact mismatch fails instead of cleaning/rerunning; the
  no-mutation negative remains green.
- [x] Implement cleanup from canonical run-owned coordinates rather than
  trusting sidecar-provided paths.
- [x] Remove only partial candidate metadata, scorer snapshots, packets,
  ledgers, and promotion staging for the exact discarded visit; clear its
  partial `steps.<Step>.adjudication` and matching live cursor atomically
  enough that a second interruption remains classifiable.
- [x] Preserve already promoted, consistent completed visits.
- [x] Prove cleanup failure stops before provider launch and reports an
  integrity error rather than claiming a clean rerun.
- [x] Run focused tests, ordered specification then quality review, and commit
  with subject `Discard mismatched adjudication visits`.

Task 2 candidate evidence: the exact selector first failed collection on the
missing candidate-visit path API, then failed behaviorally because the
transitional mismatch retained its adjudication block and visit trees. It now
passes both exact-scope cleanup and aliased-scope no-mutation cases. Promotion
discard coverage proves absent-root idempotence, prepared-state verification,
rollback for every later manifest status, exact backup hash/mode validation,
already-restored preimages, and fail-closed malformed or unrelated manifest
authority. The live retry counter remains at the new visit while prior-visit
state is inspected; only a successfully reusable prior visit rolls that
counter back. The first specification review found that a syntactically valid
manifest could otherwise nominate an unrelated workspace destination.
Correction now reconstructs the ordered promotion table and promoted-path map
from the current output contract, canonical selected-candidate workspace, and
digest-checked baseline snapshot, then requires exact manifest equality before
rollback. The focused four-module candidate passes 151 tests; compile and diff
checks pass. The required specification replay returned
`ML4_TASK2_SPEC_APPROVED`, followed by
`ML4_TASK2_QUALITY_APPROVED`; no further replay was needed.

## Task 3: Re-enter ordinary adjudication dispatch

**Files:**

- Modify: `orchestrator/workflow/adjudication/__init__.py`
- Modify: `orchestrator/workflow/adjudication/models.py`
- Modify: `orchestrator/workflow/adjudication/promotion.py`
- Modify: `orchestrator/workflow/adjudication_bindings.py`
- Modify: `orchestrator/workflow/adjudication_resume.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/adjudication_runner.py`
- Modify: `tests/test_adjudicated_provider_runtime.py`
- Modify: `tests/test_adjudicated_provider_resume.py`

- [x] First add
  `test_exact_adjudication_mismatch_reruns_with_fresh_identities` and
  `test_consistent_adjudication_resume_reuses_without_invocation`. Run:

  ```bash
  pytest -q \
    tests/test_adjudicated_provider_runtime.py \
    tests/test_adjudicated_provider_resume.py \
    -k 'mismatch_reruns_with_fresh_identities or consistent_adjudication_resume_reuses'
  ```

  Expected RED: mismatch still fails; consistent reuse remains green.
- [x] Allocate the next visit/attempt identities through normal execution;
  never reuse a discarded candidate or score identity.
- [x] Emit `adjudication_state_mismatch_rerun` exactly once with bounded
  mismatch class and old/new visit coordinates.
- [x] Remove active production emission of `adjudication_resume_mismatch`.
- [x] Prove all mismatch classes rerun successfully when exact and still fail
  closed when exact cleanup authority is unavailable.
- [x] Run focused tests, ordered specification then quality review, and commit
  with subject `Rerun mismatched adjudicated providers`.

Task 3 candidate evidence: the fresh-identity selector first returned one
failure and one pass because exact mismatch still terminated while consistent
completed state already reused without invocation. The implementation now
validates consecutive canonical old/new visit coordinates before cleanup,
discards the exact old visit, enters ordinary candidate dispatch with
visit-derived fresh identities, and emits one closed
`sidecar_reconciliation_mismatch` diagnostic at that boundary. All four
canonical sidecar-mismatch families and the scorer-resolution transition rerun
successfully; aliased or unbound cleanup authority remains mutation-free and
fails with `adjudication_state_integrity_error`. Renamed/new test collection
finds 89 cases, the mismatch-focused matrix passes 28, and the four owning
adjudication modules pass 153. Compile and diff checks pass; ordered review is
complete with `ML4_TASK3_SPEC_APPROVED` followed by
`ML4_TASK3_QUALITY_APPROVED`, with no material findings and no replay.

## Task 4: Prove reuse and publication invariants

**Files:**

- Modify: `orchestrator/workflow/adjudication/__init__.py`
- Modify: `orchestrator/workflow/adjudication/paths.py`
- Modify: `orchestrator/workflow/adjudication_runner.py`
- Modify: `specs/state.md`
- Modify: `tests/test_adjudicated_provider_resume.py`
- Modify: `tests/test_adjudicated_provider_promotion.py`

- [x] First add the kill-during-cleanup/fresh-rerun cases and a discarded-
  promotion non-authority assertion. Run:

  ```bash
  pytest -q \
    tests/test_adjudicated_provider_resume.py \
    tests/test_adjudicated_provider_promotion.py \
    -k 'kill_during or discarded_visit'
  ```

  Expected RED: there is no rerun recovery path to survive either interruption.
- [x] Prove consistent completed state invokes neither candidate nor evaluator.
- [x] Prove a rerun publishes only its newly selected outputs and lineage, with
  no discarded-visit score or promotion authority.
- [x] Kill during cleanup and during fresh rerun; both subsequent resumes must
  either classify one exact recoverable visit or fail closed without duplicate
  publication.
- [x] Run focused tests, ordered specification then quality review, and commit
  with subject `Prove adjudication rerun invariants`.

Task 4 candidate evidence: the plan selector first returned one failure and
two passes. An interruption after candidate-root deletion stranded visit 1,
and the next resume incorrectly published visit 3; interruption during the
fresh provider rerun already discarded visits 1 and 2, completed visit 3 with
candidate/evaluator counts `3/2`, and published one artifact version. A
deterministic run-owned cleanup guard now binds the mismatch class, frame,
step, discarded visit, and next visit before multi-root cleanup. Successful
cleanup retires the guard before ordinary dispatch; an interruption preserves
the exact guard and every later resume fails with
`adjudication_state_integrity_error` before provider or publication. The
discarded-promotion fixture commits candidate `a` only as pre-publication
state, then proves the replacement visit alone selects and publishes candidate
`b`, with fresh candidate/score keys, one artifact version, and no old visit
roots. The selector now passes 3, the four owning adjudication modules pass
156, the two modified test modules collect 58, and compile/diff checks pass.
Ordered review returned `ML4_TASK4_SPEC_APPROVED` followed by
`ML4_TASK4_QUALITY_APPROVED`, with no material findings and no replay.

## Task 5: Close ML-4 and Phase ML

- [ ] Run the complete adjudication suite plus ML-1's five-family
  kill-mid-provider crash/resume aggregate and ML-2's concurrent-run-lock
  control.
- [ ] Run `pytest -q -n 16 --dist=worksteal` over the broad non-security
  selection, excluding only owner-directed security selectors.
- [ ] Grep active production and normative specs for obsolete quarantine and
  `adjudication_resume_mismatch` producers. Historical records need not be
  rewritten.
- [ ] Record exact commands, counts, hashes, commits, and net line change in
  the three component plans and substrate track.
- [ ] Request one final ordered specification review followed by one quality
  review. Replay only after a material finding.
- [ ] Commit with subject `Close provider at least once loosening`.
