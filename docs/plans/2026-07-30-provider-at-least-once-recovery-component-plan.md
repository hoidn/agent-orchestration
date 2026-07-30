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

**Status:** ML-0 reviewed-plan candidate. Implementation is not started and
begins only after ordered specification then quality approval of the exact
ML-0 specification-and-plan candidate and its selection commit.

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

- [ ] Add one RED fixture per ordinary/session/supervision/peer/phased route.
  Each fixture must distinguish a committed result from an in-flight visit and
  prove that only the latter requests a fresh attempt.
- [ ] Add both-direction integrity cases: one exact validated interrupted visit
  becomes recoverable; malformed, ambiguous, or projection-mismatched state
  remains rejected before provider launch.
- [ ] Characterize legacy sticky quarantine records separately from live
  cursors.
- [ ] Run:

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

- [ ] First add
  `test_interrupted_provider_visit_disposition_requests_rerun` and
  `test_interrupted_provider_visit_integrity_error_never_invokes_provider`.
  Run:

  ```bash
  pytest -q tests/test_resume_command.py \
    -k 'interrupted_provider_visit_disposition or interrupted_provider_visit_integrity'
  ```

  Expected RED: the exact visit still returns a quarantine disposition; the
  no-launch negative remains green.
- [ ] Replace quarantine decisions with an exact `rerun_interrupted_visit`
  disposition after the existing family-specific integrity checks.
- [ ] Implement one shared state mutation that validates the matching
  `current_step`, records an interrupted evidence disposition when an owning
  metadata file is available, clears only that cursor, clears a reconstructible
  legacy quarantine error, and leaves terminal results untouched.
- [ ] Emit `provider_attempt_interrupted_rerun` once when ordinary dispatch is
  about to re-pay the provider call. Include family, step id, discarded visit,
  and next visit in structured logging context without prompt prose.
- [ ] Prove no provider invocation occurs when recovery preparation fails.
- [ ] Run the Task 2 selectors and request independent specification review,
  then quality review, once each.
- [ ] Commit with subject `Replace provider quarantine with rerun recovery`.

## Task 3: Migrate session and ordinary provider recovery

**Files:**

- Modify: `orchestrator/cli/commands/resume.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py`
- Modify: `tests/test_observability_report.py`
- Modify: `tests/test_cli_report_command.py`

- [ ] First add
  `test_resume_interrupted_provider_session_reruns_with_next_attempt` and
  `test_resume_completed_provider_session_reuses_without_invocation` to
  `tests/test_resume_command.py`. Run:

  ```bash
  pytest -q tests/test_resume_command.py \
    -k 'interrupted_provider_session_reruns or completed_provider_session_reuses'
  ```

  Expected RED: the interrupted case persists the legacy quarantine; the
  completed-reuse control passes.
- [ ] Make an interrupted session-enabled visit and any already-supported
  ordinary provider interruption re-enter normal execution with the next
  attempt identity.
- [ ] Remove the session quarantine fast-fail constants and error rendering.
  Preserve read-only rendering of unrelated historical errors.
- [ ] Prove a completed boundary still reuses the committed value with provider
  invocation count unchanged.
- [ ] Run focused tests, ordered specification then quality review, and commit
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

- [ ] First add
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
- [ ] Retain the exact cursor/visit checks and family cleanup, but replace the
  terminal quarantine mutation with interrupted evidence plus fresh group
  visit dispatch.
- [ ] Never reuse member panes, endpoints, attempts, provisional bundles, or
  settlement candidates from the discarded visit.
- [ ] Preserve peer message ledgers as immutable partial evidence and preserve
  record-before-offer semantics for the fresh visit.
- [ ] Prove each route emits one re-spend diagnostic and a malformed family
  relationship still fails before member launch.
- [ ] Run focused tests, ordered specification then quality review, and commit
  with subject `Rerun interrupted provider groups`.

## Task 5: Migrate phased-delivery recovery

**Files:**

- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/provider_phased_delivery/runtime_bindings.py`
- Modify: `orchestrator/workflow/provider_phased_delivery/diagnostics.py`
- Modify: `tests/test_workflow_lisp_phased_delivery_runtime.py`
- Modify: `tests/test_workflow_lisp_phased_delivery_e2e.py`
- Modify: `tests/e2e/test_e2e_provider_phased_contract_delivery.py`

- [ ] First add
  `test_interrupted_phased_visit_reruns_from_task_turn_with_fresh_attempt` and
  its malformed-cursor no-launch negative. Run:

  ```bash
  pytest -q tests/test_workflow_lisp_phased_delivery_runtime.py \
    -k 'interrupted_phased_visit_reruns or interrupted_phased_visit_malformed'
  ```

  Expected RED: the valid interruption produces
  `provider_phased_interrupted_visit_quarantined`; the malformed negative
  remains green.
- [ ] Replace sticky phased quarantine with whole-visit discard-and-rerun.
- [ ] Keep task/materialization turn partitioning, within-attempt
  materialization retry, receipts, freeze, natural close/join, and joint
  publication unchanged.
- [ ] Prove partial ledgers and candidates cannot become result authority and
  that the fresh attempt starts from the task turn.
- [ ] Run focused tests, ordered specification then quality review, and commit
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

- [ ] Grep production code for
  `provider_*_interrupted_visit_quarantined` and
  `quarantined_interrupted_visit`; leave no active runtime producer or
  selector.
- [ ] Before removing compatibility vocabulary, add
  `test_active_runtime_exposes_no_interrupted_visit_quarantine_error_type` to
  `tests/test_resume_command.py`. Run:

  ```bash
  pytest -q tests/test_resume_command.py \
    -k active_runtime_exposes_no_interrupted_visit_quarantine_error_type
  ```

  Expected RED: active production still exposes at least one legacy quarantine
  type.
- [ ] Retain only narrowly named legacy-read compatibility if Task 3's fixture
  proves it necessary; do not preserve an active quarantine route.
- [ ] Run the complete ML-1 focused aggregate and a no-provider-launch negative
  control.
- [ ] Request ordered specification then quality review and commit with subject
  `Retire provider interruption quarantine`.

## Task 7: Close ML-1

- [ ] Run one subprocess kill-mid-provider crash/resume E2E for each of
  ordinary, session, supervision, peer, and phased. Each completes through a
  fresh attempt and emits exactly one
  `provider_attempt_interrupted_rerun`.
- [ ] Run the repository-standard broad non-security suite with
  `pytest -q -n 16 --dist=worksteal`, excluding only the owner-directed
  security selectors.
- [ ] Record exact commands, counts, hashes, commits, and remaining ML-2/ML-4
  handoff in this plan.
- [ ] Request one final ordered specification review followed by one quality
  review. Replay only after a material finding.
- [ ] Commit with subject `Close ML1 provider rerun recovery`.
