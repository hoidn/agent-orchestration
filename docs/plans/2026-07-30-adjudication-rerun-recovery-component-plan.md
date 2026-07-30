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

**Status:** ML-0 reviewed-plan candidate. ML-4 starts after ML-2 closes.

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

- [ ] Convert existing mismatch fixtures into a closed
  `reuse | rerun_exact_scope | integrity_error` classification.
- [ ] Add RED cases for each mismatch family plus unknown/ambiguous/escaping
  scope. Only exact-scope mismatches are recoverable.
- [ ] Run:

  ```bash
  pytest -q \
    tests/test_adjudicated_provider_runtime.py \
    tests/test_adjudicated_provider_outcomes.py \
    -k 'resume_mismatch or rerun_exact_scope or integrity_error'
  ```

  Expected RED: exact-scope mismatches still return
  `adjudication_resume_mismatch`; integrity negatives remain green.
- [ ] Keep consistent-state reuse and all source/projection guard precedence
  unchanged.
- [ ] Run focused tests, ordered specification then quality review, and commit
  with subject `Classify adjudication rerun recovery`.

## Task 2: Discard one exact partial visit

**Files:**

- Modify: `orchestrator/workflow/adjudication_resume.py`
- Modify: `orchestrator/workflow/adjudication_runner.py`
- Modify: `orchestrator/workflow/adjudication/paths.py`
- Modify: `orchestrator/workflow/adjudication/utils.py`
- Modify: `orchestrator/workflow/adjudication/promotion.py`
- Modify: `tests/test_adjudicated_provider_runtime.py`

- [ ] First add
  `test_exact_mismatch_discards_only_bound_adjudication_visit` and
  `test_unprovable_cleanup_scope_makes_no_mutation`. Run:

  ```bash
  pytest -q tests/test_adjudicated_provider_runtime.py \
    -k 'discards_only_bound_adjudication_visit or unprovable_cleanup_scope'
  ```

  Expected RED: the exact mismatch fails instead of cleaning/rerunning; the
  no-mutation negative remains green.
- [ ] Implement cleanup from canonical run-owned coordinates rather than
  trusting sidecar-provided paths.
- [ ] Remove only partial candidate metadata, scorer snapshots, packets,
  ledgers, and promotion staging for the exact discarded visit; clear its
  partial `steps.<Step>.adjudication` and matching live cursor atomically
  enough that a second interruption remains classifiable.
- [ ] Preserve already promoted, consistent completed visits.
- [ ] Prove cleanup failure stops before provider launch and reports an
  integrity error rather than claiming a clean rerun.
- [ ] Run focused tests, ordered specification then quality review, and commit
  with subject `Discard mismatched adjudication visits`.

## Task 3: Re-enter ordinary adjudication dispatch

**Files:**

- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/adjudication_runner.py`
- Modify: `orchestrator/workflow/adjudication/models.py`
- Modify: `tests/test_adjudicated_provider_runtime.py`
- Modify: `tests/test_adjudicated_provider_resume.py`

- [ ] First add
  `test_exact_adjudication_mismatch_reruns_with_fresh_identities` and
  `test_consistent_adjudication_resume_reuses_without_invocation`. Run:

  ```bash
  pytest -q \
    tests/test_adjudicated_provider_runtime.py \
    tests/test_adjudicated_provider_resume.py \
    -k 'mismatch_reruns_with_fresh_identities or consistent_adjudication_resume_reuses'
  ```

  Expected RED: mismatch still fails; consistent reuse remains green.
- [ ] Allocate the next visit/attempt identities through normal execution;
  never reuse a discarded candidate or score identity.
- [ ] Emit `adjudication_state_mismatch_rerun` exactly once with bounded
  mismatch class and old/new visit coordinates.
- [ ] Remove active production emission of `adjudication_resume_mismatch`.
- [ ] Prove all mismatch classes rerun successfully when exact and still fail
  closed when exact cleanup authority is unavailable.
- [ ] Run focused tests, ordered specification then quality review, and commit
  with subject `Rerun mismatched adjudicated providers`.

## Task 4: Prove reuse and publication invariants

**Files:**

- Modify: `tests/test_adjudicated_provider_runtime.py`
- Modify: `tests/test_adjudicated_provider_resume.py`
- Modify: `tests/test_adjudicated_provider_promotion.py`

- [ ] First add the kill-during-cleanup/fresh-rerun cases and a discarded-
  promotion non-authority assertion. Run:

  ```bash
  pytest -q \
    tests/test_adjudicated_provider_resume.py \
    tests/test_adjudicated_provider_promotion.py \
    -k 'kill_during or discarded_visit'
  ```

  Expected RED: there is no rerun recovery path to survive either interruption.
- [ ] Prove consistent completed state invokes neither candidate nor evaluator.
- [ ] Prove a rerun publishes only its newly selected outputs and lineage, with
  no discarded-visit score or promotion authority.
- [ ] Kill during cleanup and during fresh rerun; both subsequent resumes must
  either classify one exact recoverable visit or fail closed without duplicate
  publication.
- [ ] Run focused tests, ordered specification then quality review, and commit
  with subject `Prove adjudication rerun invariants`.

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
