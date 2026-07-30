# Provider At-Least-Once Recovery Component Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan
> task-by-task. Use `superpowers:test-driven-development` for every behavior
> change. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute ML-1 by replacing sticky interrupted-provider quarantine
with guarded discard-and-rerun recovery for ordinary, session, supervision,
peer-group, and phased provider visits.

**Architecture:** Keep every existing projection, source, checksum, bound-input,
checkpoint, and completed-result guard. Family-specific code continues to
validate its own cursor and evidence layout, then hands one exact interrupted
visit to a small shared recovery mutation that marks available partial evidence
`interrupted`, clears only the matching live cursor, and lets ordinary step
dispatch allocate the next unused attempt ordinal. Recovery emits the named
operator-visible diagnostic `provider_attempt_interrupted_rerun`; no recovery
logic enters provider prompts.

**Tech stack:** Python 3.13, pytest/xdist, persisted schema-2.1 run state,
Workflow Lisp runtime plans, and subprocess crash/resume fixtures.

**Status:** ML-1 complete. ML-0 was selected at commit
`e2e39422f8fe52ad35dd6a174bc108f65bcf2050`. Tasks 1–7, focused and broad
non-security gates, and the final ordered reviews are complete. The commit
containing this execution record closes ML-1 and hands off to ML-2.

## Authority and bounds

This plan executes ML-1 from
`docs/plans/2026-07-26-provider-at-least-once-loosening-amendment.md` under
`docs/plans/2026-07-26-substrate-maintenance-track.md`. The normative contract
is `specs/state.md`; `specs/cli.md`, `specs/providers.md`,
`specs/observability.md`, `specs/versioning.md`, and
`specs/acceptance/index.md` are dependent normative routes.

- A compatible completed provider boundary is reused without provider
  invocation. This plan changes only a validated in-flight visit.
- Missing, malformed, ambiguous, foreign, or checksum-incompatible state still
  fails closed. Recovery is not a force restart and never bypasses projection
  or checkpoint validation.
- A discarded ordinal is never reused for different execution content.
- Existing partial evidence is audit-only. Mark it interrupted where that can
  be done truthfully; missing or torn evidence does not block recovery.
- The target-2.23 phased path joins ML-1. Its same-attempt
  materialization-only retry remains unchanged; only controller interruption
  of the whole visit moves from quarantine to fresh-attempt rerun.
- Historical sticky quarantine records may recover only when their exact
  step/visit identity can be reconstructed and validated. Otherwise they fail
  closed.
- Managed provider jobs, declared resource-transition ledgers, artifact
  lineage, peer message record-before-offer ledgers, natural-shutdown proof,
  and atomic result publication are unchanged.
- Provider-isolation implementation, bundle-transfer journal, isolation
  specification section, dashboard, and every security surface are excluded.
  ML-3 remains deferred; this plan neither weakens nor re-reviews it.
- No Q5, Q4, or L-series gate is reopened or re-reviewed.

What this makes harder: an interrupted provider call may be paid for twice,
and the last attempt may have incomplete forensic evidence. The stable
diagnostic makes the re-spend explicit; deterministic correctness continues
to come from ordinary guards and atomic result publication.

## Task 1: Characterize all interrupted-visit routes

**Files:**

- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py`
- Modify: `tests/test_provider_supervision_resume.py`
- Modify: `tests/test_provider_peer_group_resume.py`
- Modify: `tests/test_workflow_lisp_phased_delivery_runtime.py`

- [x] Add one RED fixture per ordinary/session/supervision/peer/phased route.
  Each fixture must distinguish a committed result from an in-flight visit and
  prove that only the latter requests a fresh attempt.
- [x] Add both-direction integrity cases: one exact validated interrupted visit
  becomes recoverable; malformed, ambiguous, or projection-mismatched state
  remains rejected before provider launch.
- [x] Characterize legacy sticky quarantine records separately from live
  cursors.
- [x] Run:

  ```bash
  pytest --collect-only -q \
    tests/test_resume_command.py \
    tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py \
    tests/test_provider_supervision_resume.py \
    tests/test_provider_peer_group_resume.py \
    tests/test_workflow_lisp_phased_delivery_runtime.py
  pytest -q \
    tests/test_resume_command.py \
    tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py \
    tests/test_provider_supervision_resume.py \
    tests/test_provider_peer_group_resume.py \
    tests/test_workflow_lisp_phased_delivery_runtime.py \
    -k 'interrupted and (rerun or at_least_once)'
  ```

  Expected RED: each newly added positive case observes quarantine or no
  recovery instead of a fresh attempt; integrity negative controls continue
  to pass.

## Task 2: Introduce the bounded recovery disposition

**Files:**

- Modify: `orchestrator/workflow/resume_planner.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_resume_command.py`

- [x] First add
  `test_interrupted_provider_visit_disposition_requests_rerun` and
  `test_interrupted_provider_visit_integrity_error_never_invokes_provider`.
  Run:

  ```bash
  pytest -q tests/test_resume_command.py \
    -k 'interrupted_provider_visit_disposition or interrupted_provider_visit_integrity'
  ```

  Expected RED: the exact visit still returns a quarantine disposition; the
  no-launch negative remains green.
- [x] Replace quarantine decisions with an exact `rerun_interrupted_visit`
  disposition after the existing family-specific integrity checks.
- [x] Implement one shared state mutation that validates the matching
  `current_step`, records an interrupted evidence disposition when an owning
  metadata file is available, clears only that cursor, clears a reconstructible
  legacy quarantine error, and leaves terminal results untouched.
- [x] Emit `provider_attempt_interrupted_rerun` once when ordinary dispatch is
  about to re-pay the provider call. Include family, step id, discarded visit,
  and next visit in structured logging context without prompt prose.
- [x] Prove no provider invocation occurs when recovery preparation fails.
- [x] Run the Task 2 selectors and request independent specification review,
  then quality review, once each.
- [x] Commit with subject `Replace provider quarantine with rerun recovery`.

## Task 3: Migrate session and ordinary provider recovery

**Files:**

- Modify: `orchestrator/cli/commands/resume.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py`
- Modify: `tests/test_observability_report.py`
- Modify: `tests/test_cli_report_command.py`

- [x] First add
  `test_resume_interrupted_provider_session_reruns_with_next_attempt` and
  `test_resume_completed_provider_session_reuses_without_invocation` to
  `tests/test_resume_command.py`. Run:

  ```bash
  pytest -q tests/test_resume_command.py \
    -k 'interrupted_provider_session_reruns or completed_provider_session_reuses'
  ```

  Expected RED: the interrupted case persists the legacy quarantine; the
  completed-reuse control passes.
- [x] Make an interrupted session-enabled visit and any already-supported
  ordinary provider interruption re-enter normal execution with the next
  attempt identity.
- [x] Remove the session quarantine fast-fail constants and error rendering.
  Preserve read-only rendering of unrelated historical errors.
- [x] Prove a completed boundary still reuses the committed value with provider
  invocation count unchanged.
- [x] Run focused tests, ordered specification then quality review, and commit
  with subject `Rerun interrupted provider sessions`.

## Task 4: Migrate supervision and peer-group recovery

**Files:**

- Modify: `orchestrator/workflow/resume_planner.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_provider_supervision_resume.py`
- Modify: `tests/test_provider_peer_group_resume.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/e2e/test_e2e_provider_supervision.py`
- Modify: `tests/e2e/test_e2e_provider_peer_delivery.py`

- [x] First add
  `test_interrupted_supervision_visit_reruns_fresh_members` and
  `test_interrupted_peer_group_visit_reruns_fresh_members` in their owning
  resume modules. Run:

  ```bash
  pytest -q \
    tests/test_provider_supervision_resume.py \
    tests/test_provider_peer_group_resume.py \
    -k 'interrupted and reruns_fresh_members'
  ```

  Expected RED: both routes return their sticky quarantine failures.
- [x] Retain the exact cursor/visit checks and family cleanup, but replace the
  terminal quarantine mutation with interrupted evidence plus fresh group
  visit dispatch.
- [x] Never reuse member panes, endpoints, attempts, provisional bundles, or
  settlement candidates from the discarded visit.
- [x] Preserve peer message ledgers as immutable partial evidence and preserve
  record-before-offer semantics for the fresh visit.
- [x] Prove each route emits one re-spend diagnostic and a malformed family
  relationship still fails before member launch.
- [x] Run focused tests, ordered specification then quality review, and commit
  with subject `Rerun interrupted provider groups`.

## Task 5: Migrate phased-delivery recovery

**Files:**

- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/provider_phased_delivery/runtime_bindings.py`
- Modify: `orchestrator/workflow/provider_phased_delivery/diagnostics.py`
- Modify: `tests/test_workflow_lisp_phased_delivery_runtime.py`
- Modify: `tests/test_workflow_lisp_phased_delivery_e2e.py`
- Modify: `tests/e2e/test_e2e_provider_phased_contract_delivery.py`

- [x] First add
  `test_interrupted_phased_visit_reruns_from_task_turn_with_fresh_attempt` and
  its malformed-cursor no-launch negative. Run:

  ```bash
  pytest -q tests/test_workflow_lisp_phased_delivery_runtime.py \
    -k 'interrupted_phased_visit_reruns or interrupted_phased_visit_malformed'
  ```

  Expected RED: the valid interruption produces
  `provider_phased_interrupted_visit_quarantined`; the malformed negative
  remains green.
- [x] Replace sticky phased quarantine with whole-visit discard-and-rerun.
- [x] Keep task/materialization turn partitioning, within-attempt
  materialization retry, receipts, freeze, natural close/join, and joint
  publication unchanged.
- [x] Prove partial ledgers and candidates cannot become result authority and
  that the fresh attempt starts from the task turn.
- [x] Run focused tests, ordered specification then quality review, and commit
  with subject `Rerun interrupted phased provider visits`.

## Task 6: Remove obsolete quarantine vocabulary

**Files:**

- Modify: `orchestrator/workflow/resume_planner.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/cli/commands/resume.py`
- Modify: `orchestrator/workflow/provider_phased_delivery/diagnostics.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_observability_report.py`
- Modify: `tests/test_cli_report_command.py`
- Modify: `tests/test_provider_supervision_resume.py`
- Modify: `tests/test_provider_peer_group_resume.py`
- Modify: `tests/test_provider_phased_delivery_diagnostics.py`

- [x] Grep production code for
  `provider_*_interrupted_visit_quarantined` and
  `quarantined_interrupted_visit`; leave no active runtime producer or
  selector.
- [x] Before removing compatibility vocabulary, add
  `test_active_runtime_exposes_no_interrupted_visit_quarantine_error_type` to
  `tests/test_resume_command.py`. Run:

  ```bash
  pytest -q tests/test_resume_command.py \
    -k active_runtime_exposes_no_interrupted_visit_quarantine_error_type
  ```

  Expected RED: active production still exposes at least one legacy quarantine
  type.
- [x] Retain only narrowly named legacy-read compatibility if Task 3's fixture
  proves it necessary; do not preserve an active quarantine route.
- [x] Run the complete ML-1 focused aggregate and a no-provider-launch negative
  control.
- [x] Request ordered specification then quality review and commit with subject
  `Retire provider interruption quarantine`.

## Task 7: Close ML-1

- [x] Run one subprocess kill-mid-provider crash/resume E2E for each of
  ordinary, session, supervision, peer, and phased. Each completes through a
  fresh attempt and emits exactly one
  `provider_attempt_interrupted_rerun`.
- [x] Run the repository-standard broad non-security suite with
  `pytest -q -n 16 --dist=worksteal`, excluding only the owner-directed
  security selectors.
- [x] Record exact commands, counts, hashes, commits, and remaining ML-2/ML-4
  handoff in this plan.
- [x] Request one final ordered specification review followed by one quality
  review. Replay only after a material finding.
- [x] Commit with subject `Close ML1 provider rerun recovery`.

## Execution record

ML-0 selected the tranche at commit
`e2e39422f8fe52ad35dd6a174bc108f65bcf2050`, tree
`c35119ba87125f15b79e48b6bd0ffb6466f7b738`. The implementation commits are:

- Task 2: `cf3a7a5cfeef0dd43919457a3f9fc875e5a41998`, tree
  `83f424261838070d628735c2f118cc9d40f19789`;
- Task 3: `da178b8b53ee3bf90df27f74fdcf021e24a489d7`, tree
  `2a3313d989aea4e59be6dc8df4bec165b776be90`;
- Task 4: `60d9370b0bc7af7bc3d3b3edb80f2fe066948535`, tree
  `70a7660a8c87cbad9db4c5eab0b1ae8c2e3f24d3`;
- Task 5: `79a1a88a3620a45006557a055a763dbd7545893d`, tree
  `ffb7f1e413557b85f6d4c2f56b75687363376f95`; and
- Task 6: `bf6fe7c7d95391ab4675e7cae38b744bc484313e`, tree
  `93f28e07418a35356b058df68d15c3aaf9768941`.

Task 7 verification:

- `pytest --collect-only -q tests/test_provider_rerun_subprocess_e2e.py`
  collected 5 cases. `pytest -q tests/test_provider_rerun_subprocess_e2e.py`
  passed all 5. The fixture SHA-256 is
  `35a16613675d17ba7b186e61a212b2634f20c6c758fcbaf2897ad1e1cdb7a0b4`.
- The complete 14-module ML-1 focused aggregate passed 539 tests and skipped
  6. Six explicit malformed/projection-mismatch controls passed without
  provider launch.
- The first broad command used only the keyword backstop and produced
  9,975 passed, 19 skipped, and 5 failures: four stale quarantine
  expectations and one explicitly excluded provider-launch-shim security
  test. The four in-scope expectations were corrected without changing
  production behavior; their exact selector passed 4 tests.
- The authoritative repository-standard command used all 21 explicit
  security/isolation `--ignore` selectors plus
  `-k 'not security and not secret and not isolation and not safety'`. It
  passed 9,687 tests and skipped 19 in 136.23 seconds.
- `git diff --check` passed. The final Task 7 test-file SHA-256 values are
  `92b0817f3db66f80d467f4d8ef31988db698c135f1804fbec000569ea72a6594`
  for `tests/test_provider_peer_group_ir.py` and
  `882a89e994fc58dab3fe9c917764dcb6012cfe2a02a8cb30081cff61779a754e`
  for `tests/test_workflow_state_projection.py`.
- Final specification review approved. Final quality review found one material
  test-cleanup defect; after process-group cleanup was added, the single
  permitted replay returned `ML1_FINAL_SPEC_APPROVED` followed by
  `ML1_FINAL_QUALITY_APPROVED`. No other final review replay occurred.

The next selected tranche is ML-2 under
`2026-07-30-provider-attempt-allocator-simplification-component-plan.md`,
followed by ML-4 under
`2026-07-30-adjudication-rerun-recovery-component-plan.md`. ML-3,
provider-isolation implementation, and every security surface remain excluded.
