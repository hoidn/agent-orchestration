# Phased Execution At Target 2.39 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` to implement this plan task by task.
> Use `superpowers:test-driven-development` for behavior changes and
> `superpowers:verification-before-completion` before success claims. Steps use
> checkbox syntax for tracking. The coordinator integrates and verifies; a
> reviewer distinct from the author reviews each substantive slice.

**Goal:** restore phased task/materialization delivery through the evaluated
runtime for target-2.39 `provider-result`, including deterministic public CLI
execution, bounded correction, safe interruption recovery and committed replay.

**Architecture:** retain the authored `:delivery :phased` option and use one
checked `provider_phased` coordinator effect with normal provider request data.
Reuse the interactive terminal adapter, phased protocol/endpoint/ledger and
coordinator; replace the retired parent-state publication with prepared evidence,
evaluator memo commit and settlement/reconciliation. Uncommitted visits rerun
at a fresh ordinal only after exact prior-attempt cleanup; committed visits
settle/replay without another provider call.

**Tech Stack:** existing Python, Workflow Lisp frontend/WCC/closed program,
evaluated memo runtime, tmux interactive transport, pytest and pytest-xdist.
No new dependency, public form, Agent abstraction or workflow executor.

**Tradeoff:** a crash before memo commit can repeat the whole paid provider
visit. Recovery needs durable ownership facts for cleanup; inability to prove
cleanup prevents redispatch. Retaining literal bounded materialization policy
makes dynamic retry policy and cross-provider phase continuation unavailable.

## Authority, scope and sequencing

Selected by the user on 2026-10-16. Worktree:
`.worktrees/phased-execution-239`, branch `feat/phased-execution-239`, base
`be3e3040`. Read `docs/index.md` first. Contract owners are
`specs/providers.md`, `specs/state.md`, and
`docs/design/workflow_lisp_phased_contract_delivery.md`; the latter's selected
2.39 architecture governs the detailed receipt/proof fields. Historical Q5
records remain historical. The state ML/K4 at-least-once contract supersedes
historical sticky interruption quarantine.

Implement Task 1 first while runtime bindings remain unavailable. A newly
compiled phased effect must fail closed until Task 4 supplies its own dispatch;
it must never fall through to ordinary provider execution. Tasks 2 and 3 may
be assigned independently only with explicit file ownership: Task 2 owns the
shared coordinator and adapter; Task 3 owns new evaluated binding files.
Integrate their interface before Task 4. Task 5 closes behavioral evidence;
Task 6 closes current guidance; Task 7 closes independent review and verification.

No old executor resurrection, Agent-valued phased call, session continuation,
context capture, parallel phased workers, public confinement admission, peer/group port, automatic
roadmap gate closure or paid live qualification is selected. Preserve composed
behavior and the admitted 2.35–2.38 source/import contracts. Keep frozen
pre-2.35 source fixtures and historical evidence unchanged.

## File and ownership map

| Boundary | Files / responsibility |
| --- | --- |
| Source and WCC policy | `orchestrator/workflow_lisp/typecheck_effects.py`, `typecheck_agents.py`, `wcc/model.py`, `wcc/elaborate.py`: exact target/policy checks and complete payload traversal |
| Closed construction and checking | `orchestrator/workflow_lisp/closed/build.py`, `effects.py`, `preparation_check.py`, `artifact.py`; `orchestrator/contracts/closed_program/check.py`, `node_walk.py`, `command_check.py`: phased class emission, independent artifact checks, owner-target/import checks and existing confined-provider refusal |
| Existing phased state machine | `orchestrator/workflow/provider_phased_delivery/bindings.py`, `coordinator.py`, `models.py`: prepare boundary, immutable candidates and terminal lifecycle; retain `endpoint.py`, `frames.py`, `ledger.py`, `protocol.py` unless a demonstrated caller change requires an edit |
| Interactive process ownership | `orchestrator/providers/interactive_terminal.py`: durable private transport identity and bounded exact-attempt cleanup; reuse `executor.py:prepare_interactive_invocation` and registry capability validation |
| Evaluated binding owner | Create `orchestrator/workflow/evaluated/phased_providers.py`: input resolution/composition, concrete coordinator bindings, candidate IO, receipt/proof, prepared projection, cleanup and settlement/reconciliation |
| Shared prompt/IO owner | `orchestrator/workflow/evaluated/prompts.py`, `providers.py`, `effect_inputs.py`: one captured dependency snapshot, one canonical cut and existing input/replay guards |
| Publication and recovery | `orchestrator/workflow/evaluated/effect_execution.py`, `runtime.py`, `memo_reducer.py`, `resume_prefix.py`, `parallel.py`: external prepared outcome, typed memo proof, settle-before-dependent-work and replay inventory. `replay.py` and `memo.py` already consult coordinator classification; change only when tests reveal an omitted obligation |
| New executable checks | `tests/test_workflow_lisp_phased_239.py`, `tests/test_workflow_evaluated_phased.py`, `tests/test_workflow_evaluated_phased_recovery.py`, `tests/workflow_evaluated_phased_helpers.py`, `tests/fixtures/workflow_lisp/phased_239/main.orc`, `tests/fixtures/providers/fake_phased_interactive.py` |
| Current guidance | `docs/lisp_workflow_drafting_guide.md`, `docs/capability_status_matrix.md`, `docs/design/README.md`, `docs/index.md`, `tests/README.md`, `specs/versioning.md`, `specs/acceptance/index.md`: accurate public scope, recipe, selectors and qualification limit |

Paths in a row are an ownership census, not permission for incidental refactoring.
Reuse existing helpers and amend only callers affected by the new class/interface.
No exports or provider-template configuration are added unless the actual
interactive invocation requires them; the existing declared capability is the
admission authority.

All multi-module/broad commands below run in tmux using the `tmux` skill after
the narrow changed-test selector. Use `pytest -q -n 16 --dist=worksteal` for
those runs; collection and one narrow test/module may run directly.

## Task 1: Admit and independently check the exact 2.39 source boundary

**Role/artifact:** Implementation / compiler code and focused tests.

- [x] Add `tests/test_workflow_lisp_phased_239.py` with a fragment-backed 2.39
  provider fixture and test the default `materialization_attempts=2`, literals
  1 and 3, rejection of booleans/out-of-range/nonliteral values and attempts
  without phased delivery. Verify provider-bound model/effort remain distinct.
- [x] Cover 2.35, 2.36, 2.37 and 2.38 refusal, including a 2.39 caller importing
  a phased definition authored at an older target. Target gating belongs to
  the definition's owner, not merely the entry target. Keep Agent-valued phased
  calls, extern-prompt phased calls and unsupported context/session pairings
  rejected. Refuse phased effects reachable from `par-map`, including imported
  and specialized helper calls, in both source compilation and the source-free
  closed checker. Run the new module and record the expected initial failure.
- [x] Preserve `materialization_attempts` through
  `wcc/model.py:map_perform_payload_values`. Remove the selected phased-only
  blockers in `closed/build.py` and `closed/effects.py` for the admitted target;
  emit class `provider_phased`, `repeat=rerun`, a fragment prompt and literal
  paired policy. Keep class `provider` for absent/explicit composed delivery.
- [x] Independently validate this shape in `contracts/closed_program/check.py`.
  Cover missing/unknown fields, wrong class/policy pairing, forged target,
  missing fragment contract and malformed literal bounds using checked JSON
  with no frontend or source access. Update operand walkers, provider
  configuration checks and effect detection at every listed closed boundary.
- [x] Preserve existing confined-provider refusal for the new class; this is
  recognition of the same closed gate, not new confinement qualification.
  Prove ordinary composed artifact identity/behavior unchanged and prove a
  phased runtime request cannot dispatch as an ordinary provider before wiring.
- [x] Collect the new module, then run:

  ```bash
  pytest --collect-only -q tests/test_workflow_lisp_phased_239.py
  pytest -q -n 16 --dist=worksteal tests/test_workflow_lisp_phased_239.py tests/test_workflow_lisp_phased_delivery_carriage.py tests/test_workflow_lisp_wcc_closed_boundary.py tests/test_workflow_lisp_wcc_direct_carriers.py tests/test_workflow_lisp_closed_program_check.py tests/test_workflow_lisp_closed_program_artifact.py tests/test_workflow_lisp_closed_program_effects.py
  ```

  Expected: new admission and tampering cases pass; old targets and unsupported
  routes refuse before dispatch. Record changed test names for final collection.

- [x] Follow-up admission refinement: require explicit positive `Int` literal
  `:timeout-sec` for phased delivery in source and source-free closed checking,
  reusing the existing policy field. Test missing/boolean/nonpositive/nonliteral
  refusal and preserve composed optional-timeout controls. Collect changed
  modules and record fresh focused evidence; the earlier Task 1 evidence does
  not establish this added requirement.

## Task 2: Replace retired publication and make cleanup ownership durable

**Role/artifact:** Implementation / shared coordinator and adapter code/tests.

Selected adapter refinement: implement the design's
[reservation and ownership records](../design/workflow_lisp_phased_contract_delivery.md#adapter-reservation-and-resource-ownership)
and [leased command/recovery protocol](../design/workflow_lisp_phased_contract_delivery.md#leased-commands-and-exact-recovery).
These owners define private APIs, exact receipt shapes, all creation-client
leases, pre-exec group registration/revocation, guarded server cleanup and the
original absolute live deadline. Retain existing natural-proof and diagnostic
ledger shapes; only strengthen the adapter proof invariant.

Provider-free mechanism evidence is captured in
[lifecycle architecture](/tmp/orc-phased-239-evidence/task2-lifecycle/architecture.md),
[probe source](/tmp/orc-phased-239-evidence/task2-lifecycle/probe.py),
[lifecycle results](/tmp/orc-phased-239-evidence/task2-lifecycle/results.json)
and earlier [same-connection/lease results](/tmp/orc-phased-239-evidence/task2-feasibility/results.json).
The probes show that server termination alone leaves a resistant writer,
owned-group cleanup stops writes, delayed pre-exec observes revocation, the
wrapper retains its lease through child reap, and foreign group identity is
refused without signalling. These local temporary artifacts are mechanism
evidence, not production acceptance; the implementation checks below remain open.

- [x] Extend `tests/test_provider_phased_delivery_coordinator.py` to establish a
  prepared outcome after joint candidate validation, freeze, ingress shutdown
  and natural exit zero, with no parent publication by the coordinator.
  Preserve one task delivery and same-handle correction on rejected submissions.
- [x] Replace the old `atomic_success_commit` callback/receipt and synthetic
  parent-state commit contract with the design's prepared outcome and separate
  successful settlement. Enter `JOINED_PENDING_COMMIT` immediately on natural
  shutdown proof so later evidence failures cannot abort a terminal client.
  Emit historical `publication_succeeded` only after memo commit; retain the
  closed ledger grammar and revise/version it only where the selected terminal
  integration requires it. Migrate every current test caller; retain historical
  ledger decoding. Do not add a second selectable coordinator mode.
- [ ] Add adapter tests in `tests/test_provider_interactive_terminal.py` for
  persisting the exact private transport cleanup identity before backend launch,
  bounded cleanup without the original in-memory handle, absent resources and
  forged/foreign/symlinked ownership records. Reuse the adapter backend operations;
  do not serialize live handles or trust an arbitrary socket/session path.
- [ ] Exercise both `start_server` and `start_pane` creation leases, parent
  SIGKILL before/after each durable boundary, abnormal helper exit and an
  exhausted original deadline during lease wait, kill/reap or output settlement.
  Delayed pre-exec must recheck deadline/revocation immediately before exec.
  Cover missing server-PID record, delayed socket after failed/timed-out
  creation, replaced namespace/lock/socket and foreign group/server identities.
  Active/unresolved cleanup must preserve candidate files and block redispatch.
  Prove natural residual-group failure, including when later cleanup succeeds;
  run at least one public evaluated resume smoke after integration.
- [ ] Demonstrate that zero exit follows normal graceful close; timeout, nonzero
  exit, explicit abort, failed freeze and incomplete cleanup cannot produce a
  prepared success. Validate prestart failure and partial start cleanup too.
- [ ] Run the changed modules first, then the retained protocol owners:

  ```bash
  pytest -q -n 16 --dist=worksteal tests/test_provider_phased_delivery_coordinator.py tests/test_provider_interactive_terminal.py
  pytest -q -n 16 --dist=worksteal tests/test_provider_phased_delivery_contracts.py tests/test_provider_phased_delivery_diagnostics.py tests/test_provider_materialization_protocol.py tests/test_provider_phased_delivery_identity.py tests/test_cli_provider_materialization.py
  ```

## Task 3: Bind evaluated inputs, safe candidates and prepared evidence

**Role/artifact:** Implementation / evaluated phased binding code/tests.

- [ ] Add `tests/test_workflow_evaluated_phased.py` and helpers for one checked
  phased effect. Capture source/dependencies once and render the canonical
  task/materialization cut once; protocol frames stay outside that canonical
  identity. Test dependency mutation after capture without asserting prose.
- [ ] Implement `phased_providers.py` against Task 2's prepared interface, reusing shared
  provider input resolution, result validators, `WorkspaceFiles`, interactive
  invocation preparation and existing endpoint/ledger/frame owners. Use the
  evaluator's allocated identity/ordinal rather than allocate another attempt.
- [ ] Validate all output-position files and structured result in one submitted
  snapshot. Preflight unique candidate paths as absent; reject aliasing,
  preexisting content, traversal, escaping symlinks and runtime-owned paths.
  Reset only that attempt's owned candidates between materializations. Freeze
  immutable validated bytes, then restore/verify them after natural shutdown.
- [ ] Persist the design's minimal attempt-local receipt before backend launch;
  bind program/site/ordinal/input/result locator, candidate set and private
  cleanup identity. Use `phased-attempt.json` with schema
  `evaluated_phased_provider_attempt.v1` and the exact inline proof
  `evaluated_phased_provider_commit.v1` from the design. Persist prepared proof
  only after freeze and natural exit.
  Keep phase ledger, stdout and pane output audit-only. A torn optional ledger
  cannot authorize a result or block otherwise proven cleanup.
- [ ] Test explicit capability absence/malformed data before launch, model/effort
  translation, total deadline across operations, exhausted materializations,
  candidate mutation after submission, receipt/proof mismatch and result digest
  mismatch. No missing runtime binding may fall back to composed execution.
- [ ] Derive and test the design's original live deadline: capture `t0` before
  request composition/transport and add the authored positive literal once;
  refuse nonfinite conversion/addition or `deadline <= t0` before allocation.
  Cover composition time, task/correction sharing, shutdown/first-commit expiry
  and no per-phase renewal. K4 starts a fresh live budget only after separately
  bounded cleanup; provider/per-operation defaults supply no finite authority.
- [ ] Collect and run:

  ```bash
  pytest --collect-only -q tests/test_workflow_evaluated_phased.py
  pytest -q -n 16 --dist=worksteal tests/test_workflow_evaluated_phased.py tests/test_workflow_evaluated_prompts.py tests/test_workflow_evaluated_provider_io.py tests/test_workflow_evaluated_provider_reads.py tests/test_provider_phased_delivery_policy.py
  ```

## Task 4: Integrate memo commit, settlement and K4 recovery

**Role/artifact:** Implementation / evaluated runtime and recovery code/tests.

- [ ] Add reducer tests in `tests/test_workflow_evaluated_memo.py` and phased
  recovery tests for class/proof agreement, exact receipt binding, malformed
  proof refusal, mandatory settlement and blocked downstream/terminal records.
  Source-free memo validation must reject a phased proof relabeled as ordinary.
- [ ] Route `provider_phased` through its concrete external performer and return
  a prepared outcome in `effect_execution.py`. In `runtime.py`, project and
  validate that outcome, append the evaluator's sole authoritative `committed`,
  settle the exact attempt, then expose the typed result. Never publish early
  merely because the provider submitted valid candidate files.
- [ ] Check the original attempt deadline immediately before the first memo
  commit. Prove that expiry after successful preparation produces no `committed`
  record, while expiry after a durable commit does not prevent settlement or
  reconciliation and never authorizes another provider launch.
- [ ] Add `provider_phased` to coordinator classification and exact proof
  validation in `memo_reducer.py`; preserve existing invalidation refusal for
  committed coordinators and settle-before-dependent-work replay barriers.
- [ ] Integrate read-only preflight validation, writer-locked bounded cleanup
  and reconciliation into `effect_inputs.py`, `runtime.py` and `resume_prefix.py`.
  Before commit, validate and clean only the exact old attempt; allocate a fresh
  ordinal and rerun the whole visit. Never adopt an uncommitted prepared result
  and never send materialization-only continuation after controller restart.
- [ ] After memo commit but before settlement, reconcile from the inline commit
  proof without reopening candidate/result files or audit sidecars and without
  provider dispatch, then append `settled`. After
  settlement, completed resume remains read-only. Preserve input/divergence,
  path, memo and result-integrity guards. Unprovable cleanup leaves the attempt
  pending and prevents a new provider launch; do not silently quarantine it.
- [ ] Preserve parallel refusal through reachable calls; a forged phased site
  must not enter `parallel.py` or obtain ordinary-provider dispatch. Exercise
  the existing parallel, confinement and Agent negative controls alongside
  sequential helper/loop phased calls. Introduce no generic recovery framework.
- [ ] Collect new/changed modules and run:

  ```bash
  pytest --collect-only -q tests/test_workflow_evaluated_phased_recovery.py tests/test_workflow_evaluated_memo.py
  pytest -q -n 16 --dist=worksteal tests/test_workflow_evaluated_phased_recovery.py tests/test_workflow_evaluated_memo.py tests/test_workflow_evaluated_resume.py tests/test_workflow_evaluated_resume_retry.py tests/test_workflow_evaluated_run_ref_settlement.py tests/test_workflow_evaluated_agent_turn_recovery.py tests/test_workflow_evaluated_parallel_resume.py tests/test_workflow_evaluated_invalidate.py
  ```

## Task 5: Prove the public CLI and both commit gaps

**Role/artifact:** Implementation / deterministic integration fixtures/tests.

- [ ] Create `tests/fixtures/providers/fake_phased_interactive.py` and the 2.39
  `.orc` fixture. Run the public `python -m orchestrator run` path with a fake
  interactive provider through the real adapter/submit CLI. Use the declared
  provider capability and a subprocess environment, not monkeypatched dispatch.
  Fixture asserts/logs structured protocol events and request/process identity;
  tests must not assert literal prompt phrasing. No live API credentials needed.
- [ ] Prove valid first submission, invalid-then-valid correction and exhaustion:
  one process, one task delivery, bounded materialization turns, joint validation,
  natural zero exit, one commit, settlement, correctly typed downstream value.
- [ ] Use subprocess kill gates patterned on
  `tests/test_workflow_evaluated_resume_kills.py`. Kill after durable preparation
  but before memo commit: resume cleans the old attempt and reruns at ordinal 2.
  Kill immediately after memo commit but before settle: resume reconciles and
  settles ordinal 1 with no extra provider process or task delivery.
- [ ] Add kill gates before/after ownership receipt and backend allocation,
  task/materialization delivery, freeze and settlement, including a live old
  client before preparation. Exercise cleanup refusal,
  candidate/receipt/proof tampering and preexisting output path checks. Assert
  unrelated files/processes remain untouched. Repeat resume to prove idempotence.
  Assert report/monitor can read failed, pending, unsettled and completed states
  without becoming execution authority.
- [ ] Run the deterministic public smoke explicitly:

  ```bash
  pytest -q -n 16 --dist=worksteal tests/test_workflow_evaluated_phased.py tests/test_workflow_evaluated_phased_recovery.py
  pytest -q -n 16 --dist=worksteal tests/test_workflow_evaluated_providers.py tests/test_workflow_evaluated_provider_delivery.py tests/test_workflow_evaluated_resume_kills.py tests/test_workflow_evaluated_invalidate_smoke.py
  ```

  The first command must contain actual subprocess CLI/real-adapter cases and
  is the required orchestrator smoke, not merely coordinator mocks. If tmux is
  missing, report that prerequisite and leave this acceptance gate open; a skip
  is not passing public integration evidence.

## Task 6: Update current guidance and routing

**Role/artifact:** Revision / documentation and normative routing.

- [ ] Update the drafting guide with a minimal 2.39 fragment-backed phased call,
  literal bounds/default, interactive capability prerequisite, natural-close
  requirement, same-client correction and full-visit crash rerun semantics.
- [ ] Update `docs/capability_status_matrix.md`, `docs/design/README.md` and
  `docs/index.md` to route to the accepted 2.39 contract and this plan. Keep
  historical Q5 records and old fixtures frozen; distinguish deterministic
  implementation from paid live-provider qualification. Update provider result
  delivery guidance where its ordinary-only scope would otherwise be ambiguous.
- [ ] Add target-2.39 versioning/acceptance entries and current test selectors
  to `tests/README.md`. Search maintained docs for categorical phased-retired
  claims and repair only those contradicted by this selected implementation.
  Preserve unrelated confinement, LSP, roadmap and main delivery-phase gates.
- [ ] Run the guide's exact compile command against its new fixture and the
  public smoke from Task 5. Check routing links and inspect documentation diff.
  No prompt-literal tests and no mass rewrite of historical documentation.

## Task 7: Review and verify the integrated migration

**Role/artifact:** Review / whole-change evidence; coordinator / integration.

- [ ] Inspect the final diff, changed caller census and test results. Independent
  reviewer checks source-free target/import refusal, candidate ownership,
  capability failure, prepared-to-commit and commit-to-settle gaps, exactly one
  publication authority, no ordinary fallback and no old executor route.
- [ ] Run `pytest --collect-only -q` for every new or renamed test module.
  Reuse valid focused results unless integration changes touched their behavior.
- [ ] Run the broad/full suite from the worktree root in tmux using the `tmux`
  skill and the required command:

  ```bash
  pytest -q -n 16 --dist=worksteal
  ```

  Capture command, revision, exit code, counts, failures and log path. Compare
  against the fresh base run in `/tmp/orc-phased-239-baseline` with evidence in
  `/tmp/orc-phased-239-evidence`. Baseline failures do not block the selected
  deterministic migration automatically; every new failure must be fixed or
  explicitly shown unrelated with a controlled base/current probe. Do not
  weaken checks or claim a green suite when it is red.
- [ ] Complete both deterministic public CLI kill-gap cases and the source-free
  artifact tampering checks on the final relevant code. Update this plan's
  evidence/disposition below. State any missing external prerequisite and keep
  real-provider qualification separate. Final success requires all selected
  behavior, review and applicable verification obligations, not a paid run.

## Acceptance and execution evidence

Acceptance is the conjunction of Tasks 1–7: admitted 2.39 syntax/checked artifact,
older-owner refusal, one-client phased protocol with joint validation and bounded
correction, natural-zero-exit preparation, memo-only publication, safe K4 rerun,
no-dispatch committed reconciliation, path/tamper controls, public CLI smoke and
accurate current routing. Ordinary composed behavior remains compatible.

- Base focused evidence supplied by coordinator: 88 phased contract/policy tests
  passed before edits; retain the actual command/log in final evidence.
- Fresh full baseline at `be3e3040`: `python -m pytest -q -n 16
  --dist=worksteal --tb=short` completed with **75 failed, 15,871 passed,
  117 skipped, 1 xfailed** in 1,264.44 seconds. Exact failure node IDs are in
  `/tmp/orc-phased-239-evidence/baseline-failures.json`; command/exit receipt and
  complete output are `baseline-result.json` and `baseline.log` beside it.
  Classify these separately from new failures; this is not a green baseline.
- Task 1 complete at `6ded8dda`: checked target-2.39 admission, source/capsule
  owner refusal, nonempty semantic contracts, transitive parallel refusal and
  pre-dispatch runtime refusal. Independent spec-compliance and code-quality
  reviews approved. The affected broad selector passed **499** cases;
  post-import-cleanup focused checks passed **73**, and the new module collected
  **46**. These selections overlap and their counts are not additive. Logs:
  `/tmp/orc-phased-239-evidence/task1/broad-final.log` and exit receipt beside it.
- Task 2 coordinator slice complete at `9c3878eb`: `prepare()` returns
  `PhasedProviderAttemptPrepared` in `JOINED_PENDING_COMMIT`; `settle(outcome)`
  is exact-outcome-bound and idempotent after memo commit; `close()` closes only
  diagnostic output on commit failure. The old atomic parent-state commit API
  is deleted. Spec-compliance and code-quality reviews approved. Affected-owner
  tests passed **586** cases, narrow preparation checks passed **10**, and the
  changed coordinator module collected **194**. These selections overlap.
  Evidence: `/tmp/orc-phased-239-evidence/task2-coordinator/affected-owner.txt`,
  `narrow-preparation.txt` and `coordinator-collect.txt` beside it.
- Task 1 timeout follow-up complete at `0af16810`: source, imports and the
  source-free checker require explicit positive `Int` literal `:timeout-sec`
  for phased calls; composed omission remains admitted. New refusal cases were
  observed red before implementation. The final broad selector passed **544**
  cases, the phased module **53**, carriage/diagnostics **17**, and changed
  modules collected **64** cases; these selections overlap. Evidence:
  `/tmp/orc-phased-239-evidence/task1-timeout/broad.log` and `broad.exit`.
- Task 2 adapter lifecycle implementation is in progress: group quiescence
  and delayed-launch revocation are required in addition to server absence.
  Tasks 3–7 remain incomplete; runtime dispatch remains unavailable.
- Live-provider qualification: not selected; deterministic fixtures do not claim
  it and do not establish improved provider task quality.
