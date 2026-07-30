# Provider Attempt Allocator Simplification Component Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan
> task-by-task. Use `superpowers:test-driven-development` for every behavior
> change. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute ML-2 by replacing per-allocation process coordination and
append-only lifecycle events with one run-lifetime lock and a plain monotonic
attempt counter.

**Architecture:** `orchestrate run` and `orchestrate resume` each hold one
non-blocking exclusive `RUN_ROOT/run.lock` for the lifetime of the command.
Inside that single-writer boundary, attempt allocation takes the existing
in-process lock, increments `last_allocated_ordinal`, and persists through the
ordinary atomic state writer. Evidence publication writes evidence only; it
does not mutate an allocation event ledger.

**Tech stack:** Python 3.13, `fcntl.flock`, multiprocessing/subprocess pytest
fixtures, JSON schema-2.1 state, and atomic temp-file rename.

**Status:** active. ML-1 closed at commit
`9c14dae37310755bd9cbd3de03b9256433acd9fe`, tree
`0b149f96ace8873b0381a4cd530468b1d24a083f`; ML-2 Task 1 is current.

## Authority and bounds

This plan executes ML-2 from the adopted provider at-least-once amendment.
`specs/state.md` owns the target state contract.

- Attempt ordinals remain monotonic per exact scope. One ordinal never names
  two different executions, and an attempt directory containing partial
  content is never reused.
- Compatible completed-result reuse, root/callee checksum guards, checkpoint
  validation, prompt identity, artifact lineage, and atomic result publication
  remain unchanged.
- Legacy state containing a valid lifecycle `events` list remains readable;
  new writes canonicalize to the counter-only form. Invalid legacy state still
  fails closed.
- The run lock rejects concurrent execution of the same run; it does not lock
  unrelated runs or read-only reporting.
- `durable_atomic_write` remains available as the shared atomic-write
  primitive. This plan removes only allocation-specific locking, durability
  latches, repair barriers, and reload-merge layers.
- Provider-isolation implementation, isolation bundle-transfer state, every
  security surface, dashboard, Q/L gates, and ML-3 are excluded.

What this makes harder: attempt-allocation state is no longer independently
fsynced before every provider launch, and a power-loss edge may leave less
forensic evidence. The run-lifetime single-writer invariant and ordinary
atomic state replacement preserve runtime uniqueness without the former
per-feature persistence stack.

## Task 1: Specify and test the run-lifetime lock

**Files:**

- Create: `orchestrator/run_lock.py`
- Create: `tests/test_run_lock.py`
- Modify: `tests/test_runtime_failure_persistence.py`
- Modify: `tests/test_resume_command.py`

- [x] Write RED subprocess fixtures proving a second writer for the same run
  fails fast with `run_already_active`, while distinct runs and read-only
  report operations remain independent.
- [x] Run:

  ```bash
  pytest --collect-only -q tests/test_run_lock.py
  pytest -q tests/test_run_lock.py
  ```

  Expected RED: import/collection fails because `orchestrator.run_lock` does
  not exist yet.
- [x] Implement a minimal context manager around non-blocking `flock` that
  keeps the descriptor alive for the caller lifetime.
- [x] Reuse the existing run-root/path-opening policy without changing it.
  Add no path-hardening branch and do not add, alter, or run security tests.
- [x] Run focused tests, ordered specification then quality review, and commit
  with subject `Add run lifetime writer lock`.

Task 1 evidence: collection first failed because `orchestrator.run_lock` did
not exist, then collected 3 tests. The lock plus adjacent runtime/report
selection passed 21 tests; the closure candidate plus roadmap routing passed
88. Ordered review returned `ML2_TASK1_SPEC_APPROVED` followed by
`ML2_TASK1_QUALITY_APPROVED`.

## Task 2: Hold the lock across run and resume

**Files:**

- Modify: `orchestrator/cli/commands/run.py`
- Modify: `orchestrator/cli/commands/resume.py`
- Modify: `tests/test_runtime_failure_persistence.py`
- Modify: `tests/test_resume_command.py`

- [ ] First add
  `test_run_holds_writer_lock_through_executor_exit` to
  `tests/test_runtime_failure_persistence.py` and
  `test_resume_rejects_second_writer_before_state_or_provider_mutation` to
  `tests/test_resume_command.py`. Run:

  ```bash
  pytest -q \
    tests/test_runtime_failure_persistence.py \
    tests/test_resume_command.py \
    -k 'holds_writer_lock or rejects_second_writer'
  ```

  Expected RED: both commands can currently enter mutable execution
  concurrently.
- [ ] Acquire after the exact run root exists and before mutable run state is
  created or loaded for execution; release on every terminal or exceptional
  exit.
- [ ] Ensure resume projection validation and the complete executor lifetime
  stay inside the lock.
- [ ] Prove the second command makes no provider invocation or state mutation.
- [ ] Run focused tests, ordered specification then quality review, and commit
  with subject `Serialize run writers for command lifetime`.

## Task 3: Make allocation counter-only

**Files:**

- Modify: `orchestrator/state.py`
- Modify: `orchestrator/workflow/provider_attempts.py`
- Modify: `tests/test_provider_attempt_allocation.py`
- Modify: `tests/test_prompt_contract_injection.py`

- [ ] Add RED property coverage for strictly increasing next-unused ordinals,
  independent scopes, and no ordinal reuse after a failed partial attempt.
- [ ] Run:

  ```bash
  pytest -q tests/test_provider_attempt_allocation.py \
    -k 'counter_only or no_ordinal_reuse or independent_scope'
  ```

  Expected RED: new counter-only assertions observe lifecycle `events` and
  allocation-specific process coordination.
- [ ] Reduce allocation state to validated `scope` plus
  `last_allocated_ordinal`; allocate under the existing in-process mutex and
  ordinary state write.
- [ ] Remove allocation/publication event production. Evidence paths and
  offline evidence remain consumers of the frozen ordinal, never allocators.
- [ ] Run focused tests, ordered specification then quality review, and commit
  with subject `Simplify provider attempt allocation`.

## Task 4: Remove allocation persistence machinery

**Files:**

- Modify: `orchestrator/state.py`
- Modify: `orchestrator/state_locking.py`
- Modify: `orchestrator/workflow/provider_attempts.py`
- Modify: `orchestrator/workflow/prompt_dependency_evidence.py`
- Modify: `tests/test_state_manager.py`
- Modify: `tests/test_provider_attempt_allocation.py`
- Modify: `tests/test_prompt_dependency_evidence.py`
- Modify: `tests/test_prompt_contract_injection.py`
- Modify: `tests/test_prompt_attempt_result_binding.py`

- [ ] First add
  `test_allocator_uses_no_repair_barrier_or_process_lock_layer` to
  `tests/test_provider_attempt_allocation.py`, then run:

  ```bash
  pytest -q tests/test_provider_attempt_allocation.py \
    -k allocator_uses_no_repair_barrier_or_process_lock_layer
  ```

  Expected RED: the repair barrier and process-lock helpers remain active.
- [ ] Delete the provider-attempt repair barrier, durable-mode latch,
  state-reload allocator projection merge, allocation lifecycle-event
  validation, `_from`/`_already_process_locked` method variants, and
  allocation/publication process-lock helpers.
- [ ] Keep general atomic IO and any non-allocation lock owner still used by
  current features.
- [ ] Consolidate `RunState.to_dict`/`from_dict` only where the removed layers
  leave direct duplication; do not perform unrelated state-module refactoring.
- [ ] Prove production grep contains no removed capability sentinel, repair
  barrier, or lifecycle-event writer.
- [ ] Run focused tests, ordered specification then quality review, and commit
  with subject `Delete durable allocator ledger machinery`.

## Task 5: Preserve old-state read compatibility

**Files:**

- Modify: `orchestrator/state.py`
- Modify: `orchestrator/workflow/provider_attempts.py`
- Modify: `tests/test_provider_attempt_allocation.py`
- Modify: `tests/test_prompt_dependency_evidence.py`
- Modify: `tests/test_prompt_context_report.py`
- Modify: `tests/test_workflow_judgment_views.py`
- Modify: `tests/test_workflow_lisp_judgment_views_e2e.py`
- Modify:
  `tests/fixtures/workflow_lisp/phased_contract_delivery/ordinary_compatibility.golden`

- [ ] First add
  `test_legacy_allocation_events_read_then_canonicalize_counter_only` plus
  event/counter disagreement and partial-directory lower-bound negatives.
  Run:

  ```bash
  pytest -q tests/test_provider_attempt_allocation.py \
    -k 'legacy_allocation_events or event_counter_disagreement or partial_directory_lower_bound'
  ```

  Expected RED: current writers preserve lifecycle events and do not implement
  the counter-only canonicalization contract.
- [ ] Read a valid historical `events` sequence, derive its canonical
  `last_allocated_ordinal`, and omit `events` on the next write.
- [ ] Reject event/counter disagreement, duplicate ordinals, malformed scopes,
  and a counter lower than a bound on-disk partial attempt.
- [ ] Update golden fixtures mechanically only after semantic tests pass.
- [ ] Run focused tests, ordered specification then quality review, and commit
  with subject `Read legacy provider allocation ledgers`.

## Task 6: Close ML-2

- [ ] Run the concurrent-resume process fixture, allocation property suite,
  prompt-evidence suites, and the unchanged committed-result reuse E2E.
- [ ] Run `pytest -q -n 16 --dist=worksteal` over the broad non-security
  selection, excluding only owner-directed security selectors.
- [ ] Record exact deletion/addition totals; ML-2 must be net-negative.
- [ ] Request one final ordered specification review followed by one quality
  review. Replay only after a material finding.
- [ ] Commit with subject `Close ML2 allocator simplification`.
