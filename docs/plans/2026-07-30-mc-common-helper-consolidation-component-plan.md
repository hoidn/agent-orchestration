# MC Common-Helper Consolidation Component Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to execute this plan task by task.
> Use `superpowers:test-driven-development` for every production change and
> `superpowers:verification-before-completion` before recording any gate as
> complete. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Phase MC by replacing the admitted non-security helper
clones with one small `orchestrator/_common/` package while preserving every
current wire value, error contract, state transition, and protocol-specific
distinction except the explicitly tested rejection of non-finite timeout
values and cleanup of failed atomic-write temporaries.

**Architecture:** Four narrow common modules own shared mechanics:
`canonical.py`, `validation.py`, `status.py`, and `io_atomic.py`. Callers keep
domain policy: path-template rules, protocol-specific canonical profiles,
exception families, status state machines, and persistence strategy do not
move into the common package. Each migration begins with golden vectors plus
an architecture RED proving the clone still exists, then deletes the clone in
the same task.

**Tech stack:** Python 3.13, pathlib/os/tempfile atomic replacement,
JSON/SHA-256 golden vectors, frozen provider/session records, pytest/xdist,
AST/grep architecture checks, and tmux for the broad gate.

---

## Task 6 external-resolution contract

**Implementation evidence:** complete. The frozen baseline is commit
`db01eb6a14e1c9c959b4359630667c62aeb4b507`, tree
`fd6f54416f4f39090c679bb81d768b1fa7c7cff5`. Task 0 landed at `786c1fe4`,
Task 1 at `2e6e58f9`, Task 2 at `ff9351bb`, Task 3 at `390f24d0`, Task 4 at
`f2453d06`, and Task 5 at commit
`71f61b267300d09ec18bbfca817ad18804e79503`, tree
`fe4fade1749955d23fe58cced2ff166eb271b406`. The broad-gate compatibility
correction then landed at commit
`a15c38623afe3da7b29a016aa44a66b726842a1c`, tree
`ac7a7bf5272928ba985ffe57bce634b08492e9e8`, with subject
`Preserve atomic replacement path compatibility`, after ordered
`MC_CORRECTION_SPEC_APPROVED` then `MC_CORRECTION_QUALITY_APPROVED` review.

Checked-in bytes do not encode a live pending/completed flag for Task 6. The
deterministic external record
`/home/ollie/.tmp/mc-common-helper-20260730/closure-verdicts.md` is the sole
terminal-status resolver: a valid record binding ordered
`MC_FINAL_SPEC_APPROVED` then `MC_FINAL_QUALITY_APPROVED` review, the exact
unchanged closure commit, and its passing postcommit selector makes MC
historical complete through that commit; an absent, unreadable, or
mismatching record means MC is not complete. This rule is time-invariant and
does not let checked-in prose attest to its own commit or postcommit control.
No successor roadmap tranche is selected or dispositioned.

## Authority, selection, and baseline

This plan executes only Phase MC from:

- `docs/plans/2026-07-26-substrate-maintenance-track.md`;
- `docs/plans/2026-07-26-provider-at-least-once-loosening-amendment.md`
  under “Phase MC: Common-Helper Consolidation”;
- `docs/index.md`;
- `docs/capability_status_matrix.md`; and
- `AGENTS.md`.

The frozen Task-0 census baseline is commit
`db01eb6a14e1c9c959b4359630667c62aeb4b507`, tree
`fd6f54416f4f39090c679bb81d768b1fa7c7cff5`. M0 and Q0 are historical
complete, so MC's entry conditions are satisfied.

The exact Task-0 candidate comprising this plan, the parent-track selection,
the `docs/index.md` route, and the routing-test update selects MC only after
it receives `MC_PLAN_SPEC_APPROVED` followed by `MC_PLAN_QUALITY_APPROVED` and
is committed unchanged. No production edit is authorized before that commit.
Listing later tasks does not pre-complete them.

MR-4 is independently historical complete at
`836721cef1e1628d9e88d680bb6975ad750125bd`. This plan corrects aggregate
“MR unselected” wording so that completion is visible, but it neither selects
nor re-sequences any remaining MR tranche. MR-1, MR-2, MR-3, MR-5a, MR-5b,
and MR-5c remain unselected; the missed pre-M3 conditions need a separate
disposition before any of those tranches can execute.

## Approach and deliberate cost

The direct approach is to share only mechanics whose exact current behavior
can be characterized, then migrate one semantic family at a time. Distinct
protocol serializers and validators remain local rather than being forced
through a misleading universal API.

This makes future changes to canonicalization, scalar acceptance, timeout
semantics, and atomic durability harder: a caller can no longer change a
private helper without updating shared golden vectors and every admitted
consumer. It also leaves intentionally distinct protocol-specific helpers in
place, so the common package is not a universal serialization or policy
layer.

## Load-bearing bounds

- **Behavior is frozen by outputs, not helper names.** Exact JSON bytes,
  digest prefixes/lengths, Unicode handling, `default=str`, NaN handling,
  exception class/message, state status, and atomic replacement results are
  locked before migration.
- **Two bounded corrections only.**
  - Provider timeout values already described as positive JSON numbers fail
    closed on `bool`, NaN, positive/negative infinity, zero, and negatives
    before provider launch or state mutation.
  - Non-durable atomic replacement always removes its unique temporary after
    a failed write or replace. Destination bytes remain unchanged.
- **No digest migration.** Existing persisted/checkpoint digests do not
  change. A semantic mismatch discovered by a golden vector stops the task;
  it does not get normalized in MC.
- **Domain policy stays with its owner.** Supervision and peer path-component
  rules, placeholder counts, phased u63 ceilings, custom exception families,
  append-only ledger ordering, and state-machine transitions stay local.
- **File-mode parity is mechanical, not a policy change.** The common atomic
  primitive must retain each admitted writer's existing new-file mode/umask
  behavior; restrictive and ordinary-umask writers may pass an explicit
  mechanical mode. MC does not choose or harden a mode policy.
- **Net deletion.** Relative to the frozen baseline, the exact admitted
  production-path manifest must be net LOC negative. Test additions and
  documentation are reported separately and may not be reduced to make the
  production gate pass.
- **Security exclusion.** Do not edit or test the report/monitor symlink-policy
  pair (`orchestrator/cli/commands/report.py`,
  `orchestrator/monitor/scanner.py`), provider isolation, dashboard, secrets,
  safety/security selectors, descriptor-relative/no-follow policy, file-mode
  policy, or any other security surface. The run-directory helper row is
  deferred, not silently satisfied.
- **Other explicit deferrals.** Dashboard helpers, isolation fd-IO,
  experiment/E-series writers, append-only peer/phased ledgers, provider
  observation transcript finalization, WCC middle-end helpers, and
  transactional multi-target commit remain outside MC. The monitor ledger's
  simple payload replacement and the transition executor's independent
  pending-replay write are admitted; monitor scanning and transactional
  promotion remain excluded.
- **Machine-checkable census.**
  `tests/test_common_helper_architecture.py` owns the exact admitted
  file/symbol/pattern manifest. Each task first adds its category's
  no-private-clone assertion as RED; Task 6 runs every category together.
- **No adjacent roadmap work.** MC does not reopen Q/L gates, select E/P,
  admit M3b/M3c, or decide M4.

## Frozen current census

Line numbers identify the frozen baseline and will move during execution.

### Canonical JSON and digest clones admitted

The exact lexical profile is sorted compact JSON, ASCII escaping,
`default=str`, permissive NaN, UTF-8 encoding, full SHA-256, and a
`sha256:` prefix:

- `workflow_lisp/lexical_checkpoints.py:67-75`;
- `workflow_lisp/lexical_checkpoint_restore.py:98-106`;
- `workflow_lisp/lexical_checkpoint_effect_policies.py:68-76`;
- `workflow_lisp/lexical_checkpoint_transition_resume.py:54-58`.

`workflow_lisp/build_artifacts.py` and
`workflow_lisp/lexical_checkpoint_default_resume.py` import an accidental
lexical owner and migrate to the common owner without changing bytes.
`workflow_lisp/wcc/defunctionalize.py` has an equivalent private helper but is
excluded by the track's WCC middle-end bound; its existing output remains a
golden control rather than a migration target.

Provider supervision/peer path records and phased-delivery records duplicate
sorted compact ASCII JSON in
`workflow/provider_supervision/{bindings,contracts,models,paths,directive}.py`,
`workflow/provider_peer_group/{paths,bindings,ledger,protocol,coordinator}.py`,
and
`workflow/provider_phased_delivery/{bindings,models,frames,ledger,protocol,coordinator}.py`.
They may share the same exact serializer while retaining local newline/frame
ownership and current `allow_nan` behavior. Strict UTF-8 prompt identity,
prompt-fragment, pure-expression, adjudication, experiment, WCC-identity,
truncated-digest, and unprefixed-digest profiles are distinct and excluded
from semantic collapse.

### Scalar validation clones admitted

Exact `ValueError` closed-mapping and non-empty-string mechanics are duplicated
across:

- `providers/interactive_terminal.py`;
- `workflow/provider_attempts.py`;
- `workflow/provider_supervision/{bindings,models,paths}.py`;
- `workflow/provider_peer_group/{bindings,ledger,models,paths,protocol}.py`;
- `workflow/{prompt_identity,prompt_dependency_evidence}.py` through their
  existing diagnostic wrappers.

Positive/non-negative ordinary-integer helpers with the same `bool` rejection
and `ValueError` behavior are admitted. Phased `TypeError` validators, u63
ceilings, role-specific exception constructors, and path-template/component
rules remain local.

Finite-positive timeout validation is duplicated in
`providers/types.py`, `providers/interactive_terminal.py`,
`workflow/provider_peer_group/models.py`,
`workflow/provider_peer_group/protocol.py`, and
`workflow/provider_phased_delivery/runtime_bindings.py`. The last two omit
`isfinite`; MC brings them under the already-correct finite-positive rule
while preserving each caller's public error class/message.

### Status and owning-type predicate clones admitted

- Run-terminal status is exactly `completed|failed`.
- Step-settled status is exactly `completed|failed|skipped`.
- Resume-entry terminality remains the distinct existing
  `ResumePlanner.entry_is_terminal` rule, `completed|skipped`.
- `SessionIdentitySnapshot` owns the four identical assistant-text eligibility
  ladders currently copied in `providers/executor.py`.

Call sites include `workflow/{call_frame_state,executor,loops}.py`,
`workflow/prompt_dependency_evidence.py`,
`workflow_lisp/lexical_checkpoints.py`,
`observability/report.py`, and the non-path-classification portion of
`monitor/classifier.py`. CLI report path/status recursion and monitor scanning
remain excluded with the security-adjacent run-directory row.

### Atomic-write clones admitted

- Durable owner: `state_locking.py:10-46`, currently consumed by phased
  runtime bindings.
- General non-fsync replacement: `state.py` JSON writes,
  `workflow/executor.py` bytes/text helpers,
  `workflow/adjudication/utils.py::_atomic_write_text`,
  `observability/live_notes.py`, and the simple independent writes in
  `observability/summary.py`, `monitor/ledger.py`, and
  `workflow/transition_executor.py::_write_pending_replay`.
- Simple adapter writes:
  `workflow_lisp/adapters/{apply_resource_transition,reusable_phase_state_common,write_reusable_phase_state_v1}.py`.

Copy-then-replace, transactional multi-file commits, append-only/fsynced
ledgers, observation transcript finalization, monitor scanning policy, and
experiment writers are distinct or excluded.

## Review and commit discipline

For Tasks 1–5:

1. dispatch one implementation agent against the exact task and current HEAD;
2. add the named RED/golden/architecture tests first and capture the failure;
3. implement only the task;
4. run the narrow owner tests and `git diff --check`;
5. request an independent specification review;
6. after `MC_TASK<N>_SPEC_APPROVED`, request a distinct quality review;
7. address material findings with TDD and restart the ordered pair only when
   production/test behavior changes; and
8. commit the exact approved bytes.

Do not repeat reviews in the absence of a material finding. Task 6 performs
one final ordered review over the complete phase candidate.

## Task 0: Freeze the census, review the plan, and select MC

**Files:**

- Create:
  `docs/plans/2026-07-30-mc-common-helper-consolidation-component-plan.md`
- Modify: `docs/plans/2026-07-26-substrate-maintenance-track.md`
- Modify: `docs/index.md`
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`

- [x] Re-census current helpers and call sites against baseline
  `db01eb6a`; do not reuse the amendment's stale 2026-07-26 line numbers.
- [x] Bound admitted and deferred surfaces explicitly, including the complete
  security exclusion and the MR-4 routing correction.
- [x] Run:

  ```bash
  git diff --check
  pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py
  ```

- [x] Obtain `MC_PLAN_SPEC_APPROVED` followed by
  `MC_PLAN_QUALITY_APPROVED` against the exact Task-0 candidate.
- [x] Commit unchanged with subject
  `Select common helper consolidation`.
- [x] From the committed tree, rerun the routing selector. Only then may Task
  1 begin.

**Actual evidence:** the exact reviewed selection candidate landed at Task 0
commit `786c1fe4`; its committed-tree routing selector passed before Task 1.

## Task 1: Consolidate lexical canonical JSON and digests

**Files:**

- Create: `orchestrator/_common/__init__.py`
- Create: `orchestrator/_common/canonical.py`
- Create: `tests/test_common_canonical.py`
- Create: `tests/test_common_helper_architecture.py`
- Modify: `orchestrator/workflow_lisp/lexical_checkpoints.py`
- Modify: `orchestrator/workflow_lisp/lexical_checkpoint_restore.py`
- Modify:
  `orchestrator/workflow_lisp/lexical_checkpoint_effect_policies.py`
- Modify:
  `orchestrator/workflow_lisp/lexical_checkpoint_transition_resume.py`
- Modify: `orchestrator/workflow_lisp/build_artifacts.py`
- Modify:
  `orchestrator/workflow_lisp/lexical_checkpoint_default_resume.py`
- Modify: owning lexical-checkpoint/WCC tests
- Modify: `tests/test_workflow_lisp_build_artifacts.py`

- [x] Add golden vectors for key order, ASCII and non-ASCII text, nested
  mappings/lists, Path/unknown objects through `default=str`, NaN/Inf,
  full prefix, exact digest length, and bytes-vs-text/newline boundaries.
- [x] Add an architecture RED requiring the common owner and forbidding the
  four admitted local definitions. Assert that the excluded WCC helper and
  its output remain unchanged.
- [x] Freeze the complete admitted file/symbol/pattern manifest in
  `tests/test_common_helper_architecture.py`; add and satisfy only the
  canonical category's no-clone assertion in this task.
- [x] Implement the minimum shared ASCII canonical serializer and prefixed
  JSON digest with explicit fallback behavior. Do not expose strict UTF-8,
  truncated, or unprefixed profiles through this task.
- [x] Migrate the exact clone set and accidental import consumers; prove all
  existing persisted/checkpoint digest fixtures remain byte-identical.
- [x] Run:

  ```bash
  pytest --collect-only -q \
    tests/test_common_canonical.py \
    tests/test_workflow_lisp_lexical_checkpoints.py \
    tests/test_workflow_lisp_lexical_checkpoint_restore.py
  pytest -q \
    tests/test_common_canonical.py \
    tests/test_workflow_lisp_lexical_checkpoints.py \
    tests/test_workflow_lisp_lexical_checkpoint_restore.py \
    tests/test_workflow_lisp_lexical_checkpoint_default_resume.py \
    tests/test_workflow_lisp_build_artifacts.py \
    tests/test_workflow_lisp_provider_peer_group_e2e.py
  ```

- [x] Obtain `MC_TASK1_SPEC_APPROVED` then
  `MC_TASK1_QUALITY_APPROVED`; commit with subject
  `Consolidate lexical canonical digests`.

**Actual evidence:** the canonical owner, frozen vectors, architecture guard,
and admitted lexical migrations landed after the ordered reviews at Task 1
commit `2e6e58f9`.

## Task 2: Consolidate provider scalar and canonical mechanics

**Files:**

- Create: `orchestrator/_common/validation.py`
- Modify: `orchestrator/_common/canonical.py`
- Create: `tests/test_common_validation.py`
- Modify: `tests/test_common_helper_architecture.py`
- Modify: `orchestrator/providers/interactive_terminal.py`
- Modify: `orchestrator/workflow/provider_attempts.py`
- Modify: `orchestrator/workflow/prompt_identity.py`
- Modify: `orchestrator/workflow/prompt_dependency_evidence.py`
- Modify: `orchestrator/workflow/provider_supervision/bindings.py`
- Modify: `orchestrator/workflow/provider_supervision/contracts.py`
- Modify: `orchestrator/workflow/provider_supervision/models.py`
- Modify: `orchestrator/workflow/provider_supervision/paths.py`
- Modify: `orchestrator/workflow/provider_supervision/directive.py`
- Modify: `orchestrator/workflow/provider_peer_group/bindings.py`
- Modify: `orchestrator/workflow/provider_peer_group/ledger.py`
- Modify: `orchestrator/workflow/provider_peer_group/models.py`
- Modify: `orchestrator/workflow/provider_peer_group/paths.py`
- Modify: `orchestrator/workflow/provider_peer_group/protocol.py`
- Modify: `orchestrator/workflow/provider_peer_group/coordinator.py`
- Modify: `orchestrator/workflow/provider_phased_delivery/bindings.py`
- Modify: `orchestrator/workflow/provider_phased_delivery/models.py`
- Modify: `orchestrator/workflow/provider_phased_delivery/frames.py`
- Modify: `orchestrator/workflow/provider_phased_delivery/ledger.py`
- Modify: `orchestrator/workflow/provider_phased_delivery/protocol.py`
- Modify: `orchestrator/workflow/provider_phased_delivery/coordinator.py`
- Modify: exact owning provider contract tests

- [x] Add golden matrices for closed mappings, key-order diagnostics,
  empty/non-string text, `bool` vs integer, minimum boundaries, Unicode
  strings, and exact exception class/message. Canonical vectors cover both
  permissive-NaN and rejecting-NaN ASCII profiles plus zero/one/two trailing
  newline ownership.
- [x] Add an architecture RED enumerating every admitted local generic clone.
- [x] Implement only `closed_mapping`, `nonempty_string`, and ordinary integer
  validation shapes needed by exact `ValueError` consumers. A helper must not
  accept an exception/message customization API unless two admitted callers
  demonstrably require it.
- [x] Reuse Task 1's exact compact-ASCII canonical serializer for provider
  records with the same wire contract. Preserve each caller's current
  `allow_nan` choice and keep JSONL/turn-frame trailing newlines local.
- [x] Keep supervision/peer path policy, phased TypeError/u63 validators,
  prompt-role exceptions, and all distinct canonical profiles local.
- [x] Run:

  ```bash
  pytest --collect-only -q tests/test_common_validation.py
  pytest -q \
    tests/test_common_validation.py \
    tests/test_provider_interactive_terminal.py \
    tests/test_provider_attempt_allocation.py \
    tests/test_prompt_identity.py \
    tests/test_prompt_dependency_evidence.py \
    tests/test_provider_supervision_ir.py \
    tests/test_provider_supervision_resume.py \
    tests/test_provider_peer_group_contracts.py \
    tests/test_provider_peer_group_protocol.py \
    tests/test_provider_peer_group_ir.py \
    tests/test_provider_phased_delivery_contracts.py \
    tests/test_provider_phased_delivery_identity.py \
    tests/test_provider_phased_delivery_coordinator.py
  ```

- [x] Obtain `MC_TASK2_SPEC_APPROVED` then
  `MC_TASK2_QUALITY_APPROVED`; commit with subject
  `Consolidate provider scalar helpers`.

**Actual evidence:** provider scalar and compact-ASCII mechanics plus their
golden/architecture coverage landed after the ordered reviews at Task 2
commit `ff9351bb`.

## Task 3: Consolidate status and session-snapshot predicates

**Files:**

- Create: `orchestrator/_common/status.py`
- Create: `tests/test_common_status.py`
- Modify: `orchestrator/providers/session_transport.py`
- Modify: `orchestrator/providers/executor.py`
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/cli/commands/resume.py`
- Modify: `tests/test_common_helper_architecture.py`
- Modify: `orchestrator/workflow/resume_planner.py`
- Modify: `orchestrator/workflow/call_frame_state.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/loops.py`
- Modify: `orchestrator/workflow/prompt_dependency_evidence.py`
- Modify: `orchestrator/workflow_lisp/lexical_checkpoints.py`
- Modify: `orchestrator/observability/report.py`
- Modify: `orchestrator/monitor/classifier.py`
- Modify: exact owning status/session tests

- [x] Golden-lock all run/step/resume status values, unknown values, `None`,
  and the failure/suspended resume distinction.
- [x] Add both-direction `SessionIdentitySnapshot` cases for missing, matching
  unique, mismatched unique, ambiguous, and invalid snapshots.
- [x] Add an architecture RED for the four executor ladders and admitted
  literal terminal/settled sets.
- [x] Put assistant-text eligibility on `SessionIdentitySnapshot` and migrate
  all four executor callers.
- [x] Share only run-terminal and step-settled predicates. Keep
  `ResumePlanner.entry_is_terminal` as the owner of its distinct rule and keep
  state-machine-specific terminal sets local. Extend the `StateStatus` type
  alias to include the already-written `suspended` runtime value without
  changing runtime behavior. Route resume's scalar `completed|skipped` check
  through the resume-owned scalar predicate without moving recursive
  ownership.
- [x] Run:

  ```bash
  pytest --collect-only -q tests/test_common_status.py
  pytest -q \
    tests/test_common_status.py \
    tests/test_provider_session_transport.py \
    tests/test_provider_execution.py \
    tests/test_provider_execution_control.py \
    tests/test_resume_command.py \
    tests/test_subworkflow_calls.py \
    tests/test_observability_report.py \
    tests/test_monitor_classifier.py
  ```

- [x] Obtain `MC_TASK3_SPEC_APPROVED` then
  `MC_TASK3_QUALITY_APPROVED`; commit with subject
  `Consolidate runtime status predicates`.

**Actual evidence:** the bounded status owners and snapshot predicate with
both-direction coverage landed after the ordered reviews at Task 3 commit
`390f24d0`.

## Task 4: Make provider timeout validation uniformly finite

**Files:**

- Modify: `orchestrator/_common/validation.py`
- Modify: `tests/test_common_validation.py`
- Modify: `tests/test_common_helper_architecture.py`
- Modify: `orchestrator/providers/types.py`
- Modify: `orchestrator/providers/interactive_terminal.py`
- Modify: `orchestrator/workflow/provider_peer_group/models.py`
- Modify: `orchestrator/workflow/provider_peer_group/protocol.py`
- Modify:
  `orchestrator/workflow/provider_phased_delivery/runtime_bindings.py`
- Modify: exact owning provider/peer/phased tests

- [x] Add RED cases for `True`, `False`, NaN, both infinities, zero,
  negatives, positive int, and positive finite float at every admitted public
  boundary.
- [x] Add the timeout category's architecture RED so no admitted inline
  finite/positive ladder survives this task.
- [x] Prove invalid values cause no provider process launch, queue wait,
  deadline calculation, evidence publication, or state mutation.
- [x] Implement one finite-positive numeric validator while retaining each
  caller's existing error class and message.
- [x] Keep executable-IR positive-Int validation, prompt-identity role
  exceptions, adjudication's optional-timeout coercion, and all deadline state
  machines outside this helper.
- [x] Run:

  ```bash
  pytest -q \
    tests/test_common_validation.py \
    tests/test_provider_execution.py \
    tests/test_provider_interactive_terminal.py \
    tests/test_provider_peer_group_contracts.py \
    tests/test_provider_peer_group_protocol.py \
    tests/test_provider_phased_delivery_contracts.py \
    tests/test_workflow_lisp_phased_delivery_runtime.py
  ```

- [x] Obtain `MC_TASK4_SPEC_APPROVED` then
  `MC_TASK4_QUALITY_APPROVED`; commit with subject
  `Unify finite provider timeout validation`.

**Actual evidence:** all admitted timeout boundaries use the finite-positive
mechanic with pre-side-effect rejection coverage; the ordered-review candidate
landed at Task 4 commit `f2453d06`.

## Task 5: Consolidate atomic replacement mechanics

**Files:**

- Create: `orchestrator/_common/io_atomic.py`
- Create: `tests/test_common_io_atomic.py`
- Modify: `tests/test_common_helper_architecture.py`
- Delete: `orchestrator/state_locking.py`
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/provider_supervision/bindings.py`
- Modify: `orchestrator/workflow/provider_peer_group/bindings.py`
- Modify: `orchestrator/workflow/steps/runtime.py`
- Modify: `orchestrator/workflow/steps/materialize_view.py`
- Modify: `orchestrator/workflow/steps/pure_projection.py`
- Modify: `orchestrator/workflow/adjudication/utils.py`
- Modify:
  `orchestrator/workflow/provider_phased_delivery/runtime_bindings.py`
- Modify: `orchestrator/observability/live_notes.py`
- Modify: `orchestrator/observability/summary.py`
- Modify: `orchestrator/monitor/ledger.py`
- Modify: `orchestrator/workflow/transition_executor.py`
- Modify:
  `orchestrator/workflow_lisp/adapters/apply_resource_transition.py`
- Modify:
  `orchestrator/workflow_lisp/adapters/reusable_phase_state_common.py`
- Modify:
  `orchestrator/workflow_lisp/adapters/write_reusable_phase_state_v1.py`
- Modify: exact owning state/executor/adjudication/observability/adapter tests

- [x] Add RED/golden coverage for complete and short writes, write failure,
  replace failure, destination preservation, unique temporary names,
  temporary cleanup, bytes/text encoding, file fsync, parent fsync, and
  propagated exceptions. Directly prove restrictive versus ordinary-umask
  new-file mode parity.
- [x] Add the atomic category's architecture RED so every admitted simple
  writer, including the direct executor-method consumers, must leave its
  private implementation in this task.
- [x] Preserve the durable helper's current write/fsync/replace/fsync order.
  Provide one non-fsync bytes primitive and a UTF-8 text wrapper.
- [x] Replace only independent single-destination temp-and-rename clones.
  Leave copy-then-replace, append-only ledgers, observation finalization,
  batch transactions, monitor policy, experiments, and security-sensitive
  writers untouched.
- [x] Remove executor atomic methods from `StepRuntime`; step interpreters use
  the common helper directly.
- [x] Delete `state_locking.py` after its tests and only production consumer
  import the common durable owner.
- [x] Run:

  ```bash
  pytest --collect-only -q tests/test_common_io_atomic.py
  pytest -q \
    tests/test_common_io_atomic.py \
    tests/test_state_manager.py \
    tests/test_provider_attempt_allocation.py \
    tests/test_runtime_failure_persistence.py \
    tests/test_adjudicated_provider_baseline.py \
    tests/test_adjudicated_provider_promotion.py \
    tests/test_provider_supervision_runtime.py \
    tests/test_provider_peer_group_runtime.py \
    tests/test_monitor_ledger.py \
    tests/test_observability_live_notes.py \
    tests/test_observability_report.py \
    tests/test_observability_summary_modes.py \
    tests/test_observability_summary_profiles.py \
    tests/test_workflow_lisp_materialize_view_runtime.py \
    tests/test_workflow_lisp_phase_stdlib.py \
    tests/test_workflow_lisp_resource_transition_runtime.py \
    tests/test_workflow_lisp_pure_result_replay.py \
    tests/test_workflow_transition_executor.py \
    tests/test_workflow_lisp_lexical_checkpoints.py
  ```

- [x] Obtain `MC_TASK5_SPEC_APPROVED` then
  `MC_TASK5_QUALITY_APPROVED`; commit with subject
  `Consolidate atomic file replacement`.

**Actual evidence:** the bounded durable and non-durable atomic owners,
cleanup/failure coverage, and admitted caller migrations landed after the
ordered reviews at Task 5 commit
`71f61b267300d09ec18bbfca817ad18804e79503`, tree
`fe4fade1749955d23fe58cced2ff166eb271b406`; its postcommit owner control
passed 57 tests. The later broad-gate compatibility correction landed at
`a15c38623afe3da7b29a016aa44a66b726842a1c`, tree
`ac7a7bf5272928ba985ffe57bce634b08492e9e8`, with subject
`Preserve atomic replacement path compatibility`, after ordered
`MC_CORRECTION_SPEC_APPROVED` then `MC_CORRECTION_QUALITY_APPROVED` review;
its focused selector passed 29 tests and the full Task-5-plus-regressions
selector passed 671 tests.

## Task 6: Close Phase MC

**Files:**

- Modify:
  `docs/plans/2026-07-30-mc-common-helper-consolidation-component-plan.md`
- Modify: `docs/plans/2026-07-26-substrate-maintenance-track.md`
- Modify: `docs/index.md`
- Modify: `docs/capability_status_matrix.md` only if the final implementation
  changes a currently listed capability fact
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`

### Recorded Task 6 implementation evidence

- The refreshed exact architecture census passed 7 tests in 2.63 seconds
  (3.04 seconds
  elapsed); log SHA-256
  `323667f5885c57f9ba4fee3295aad2081889bfc8c979d74f87f7ec1307e6df6a`.
- The exact admitted production-path manifest contains 56 paths and has
  SHA-256
  `124fa184d3296e4e57402ec40adbb0d7a4d992836617af02540bedc627411789`.
  The refreshed outside-manifest proof found 0 excluded-path matches; log
  SHA-256
  `09a65712abec1aba4a055a0c085b96e6aea0b5b3d319c56b665ca8f6809c7576`.
- Baseline-through-correction numstat over the exact production manifest is
  523 additions, 524 deletions, net -1. Baseline-to-worktree totals are tests:
  4,227 additions and 32 deletions; documentation: 830 additions and 41
  deletions.
- Collection of every new test module found 115 tests in 2.16 seconds
  (2.53 seconds elapsed); log
  SHA-256
  `b6c66fce37a6453ebc885b76de1a86eb16efdcf8427a1565999afee637507e01`.
- The first broad attempt is retained as rejected evidence: 2 failed, 10,107
  passed, 19 skipped, and 5 warnings in 113.80 seconds (114.33 seconds
  elapsed); log SHA-256
  `7b19842fef3e04366acc7ef48cedc918647e6c51bda9738c536f9e54dffabbbb`.
  It exposed a `NAME_MAX` temporary basename and a direct-script relative
  import failure; correction `a15c3862` fixes both.
- The corrected broad rerun exited 0 with 10,111 passed, 19 skipped, and 5
  warnings in 114.71 seconds (115.40 seconds elapsed); log SHA-256
  `aefafa7d3547a4f9bedcde7e4f965d4f67496b98b84c6cbec1c993329fd8afc7`.
  Its repository-standard 16-worker command, with the exact 21 ignores and
  security exclusions, was:

  ```bash
  pytest -q -n 16 --dist=worksteal \
    --ignore=tests/test_at61_at62_wait_for_path_safety.py \
    --ignore=tests/test_cli_safety.py \
    --ignore=tests/test_execution_safety.py \
    --ignore=tests/test_provider_isolation_attestation.py \
    --ignore=tests/test_provider_isolation_backend.py \
    --ignore=tests/test_provider_isolation_backend_identity_negatives.py \
    --ignore=tests/test_provider_isolation_bundle_broker.py \
    --ignore=tests/test_provider_isolation_candidate.py \
    --ignore=tests/test_provider_isolation_controller_lifecycle.py \
    --ignore=tests/test_provider_isolation_environment.py \
    --ignore=tests/test_provider_isolation_environment_cli.py \
    --ignore=tests/test_provider_isolation_execution.py \
    --ignore=tests/test_provider_isolation_network_preflight.py \
    --ignore=tests/test_provider_isolation_policy.py \
    --ignore=tests/test_provider_isolation_runtime_authority.py \
    --ignore=tests/test_provider_isolation_schema_resources.py \
    --ignore=tests/test_provider_isolation_workflow_continuation.py \
    --ignore=tests/test_provider_isolation_workflow_lifecycle.py \
    --ignore=tests/test_provider_launch_shim.py \
    --ignore=tests/test_secrets.py \
    --ignore=tests/test_workflow_provider_isolation_integration.py \
    -k 'not security and not secret and not isolation and not safety'
  ```

- The final owner-module union, including both broad-discovered regression
  selectors, exited 0 with 2,673 passed in 63.51 seconds (64.38 seconds
  elapsed); log SHA-256
  `2eebeffa1cf28ec9abac7733e9a562d0183dd590ff84dd62f0ab03dcd11bb6d6`.

Review, commit, and postcommit occurrence are intentionally not represented as
live checkboxes or status prose in this file. The external-resolution contract
above is their sole terminal authority.

- [x] Run the architecture census and prove no admitted private clone remains.
  The check must use the exact manifest in
  `tests/test_common_helper_architecture.py`, not a repo-wide name ban that
  would erase intentional protocol-specific helpers.
- [x] Prove the phase diff contains no dashboard, provider-isolation,
  experiment/E-series, WCC, report/monitor symlink-policy, or other excluded
  security path.
- [x] Record `git diff --numstat` from the Task-0 selection baseline through
  the Task-5 implementation tip over an exact admitted production-path
  manifest and prove deletions exceed additions. Report test and documentation
  totals separately.
- [x] Run the union of all Task 1–5 owner modules and routing tests.
- [x] Run `pytest --collect-only` for every new or renamed test module.
- [x] In tmux, run the repository-standard broad suite with
  `pytest -q -n 16 --dist=worksteal`, excluding the standing security,
  safety, secrets, provider-isolation, and other owner-directed security
  selectors. Record the exact command, totals, duration, and log SHA-256.
- [x] Update status/routing facts without selecting MR, M3b, M3c, M4, E, or P.

### Externally resolved terminal operations

These operations are deliberately not live checked-in checkboxes:

1. obtain `MC_FINAL_SPEC_APPROVED` followed by
   `MC_FINAL_QUALITY_APPROVED` against the exact closure candidate;
2. commit the reviewed bytes unchanged with subject
   `Complete common helper consolidation`; and
3. run a non-mutating postcommit owner-plus-routing selector and bind its fresh
   result, the reviews, and the exact commit/tree in the deterministic
   external record.

## Completion contract

MC is complete only when:

1. the admitted mechanics have one common owner and no admitted clone;
2. all frozen bytes, digests, exception contracts, statuses, and normal
   timeout behavior retain parity;
3. non-finite provider timeouts fail before side effects;
4. failed non-durable atomic writes leave the destination unchanged and no
   temporary behind;
5. domain-specific and security-excluded helpers remain untouched;
6. admitted production LOC is net negative and test/doc totals are reported
   separately;
7. narrow, combined, routing, and broad non-security gates pass; and
8. ordered final reviews approve the exact committed closure bytes.

Completion does not select or disposition any other roadmap tranche.
