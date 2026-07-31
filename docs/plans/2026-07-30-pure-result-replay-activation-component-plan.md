# Pure-Result Replay Activation Component Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan
> task-by-task. Use `superpowers:test-driven-development` for every behavior
> change. Use `superpowers:verification-before-completion` before recording
> any task or gate as complete. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Activate the accepted `derived_pure_replay.v1` profile for ordinary
new Workflow Lisp roots and fresh non-iterative Workflow Lisp call frames
without backfilling existing state or expanding replay eligibility.

**Architecture:** The three typed creation points select the already
implemented profile: public `.orc` run creation, `.orc` force-restart creation,
and fresh call-frame construction for a callee whose validated provenance says
`frontend_kind == "workflow_lisp"` and whose resolved call boundary is not
iteration-owned. Generic state initialization remains opt-in, ordinary resume
loads the persisted profile unchanged, and existing or iteration-owned frames
remain historical. No replay, checkpoint, state-schema, or compiler algorithm
changes.

**Tech Stack:** Python 3.13, Workflow Lisp validated bundles and provenance,
schema-2.1 root/call-frame state, the accepted pure-result replay runtime,
pytest, and repository routing tests.

---

**Status:** reviewed implementation plan; Task 1 selected. Baseline commit
`480e7e2f`, tree `1886104a`. Ordered review approved corrected proposal commit
`6e06b4c0`, tree `6a4c4d6d`, plan SHA-256
`6b12b9c3071dc1325b62cb91d56cb201a8ccaeb50cc843912c26dee71630647d`,
with `M3A_ACTIVATION_PLAN_SPEC_APPROVED` followed by
`M3A_ACTIVATION_PLAN_QUALITY_APPROVED`.

## Authority and settled design

This is the separately reviewed M3a activation plan required by:

- `docs/design/workflow_lisp_pure_result_replay.md`;
- `specs/state.md`;
- `docs/design/workflow_lisp_state_layout.md`;
- `docs/plans/2026-07-26-substrate-maintenance-track.md`; and
- the historical-complete
  `docs/plans/2026-07-30-pure-result-replay-feasibility-component-plan.md`.

M2 already proved the profile, exact value-free shell, atomic witness
transitions, transient dependency index, persistence audit, replay runtime,
checkpoint filtering, validated frame entry, and historical compatibility.
M3a changes only who selects that profile when creating new state.

The considered activation approaches are:

1. **Selected — typed creation-point selection.** Pass the exact profile at
   public `.orc` root creation and at a fresh, non-iterative call frame whose
   validated callee provenance identifies Workflow Lisp.
2. **Rejected — generic initializer inference.** Inferring from a filename,
   suffix, or caller-provided workflow path would turn a generic persistence
   API into a frontend classifier and would make tests and embedding callers
   activate implicitly.
3. **Rejected — parent-profile inheritance.** Copying a parent profile would
   misclassify non-Workflow-Lisp callees and iteration-owned frames, while a
   historical parent could suppress a valid fresh Workflow Lisp child.

The following constraints are load-bearing:

- “Ordinary new Workflow Lisp roots” means a successfully compiled typed
  `.orc` root created by `orchestrate run`, plus a new `.orc` root created by
  `orchestrate resume --force-restart`.
- Ordinary resume never chooses or backfills a profile. It validates and uses
  the profile already persisted in the selected root or frame.
- `StateManager.initialize(...)` keeps its default `None`; embeddings and
  tests must still opt in explicitly.
- A fresh child selects the profile from the callee's validated typed
  provenance, not a suffix, parent profile, authored alias, or step ID.
- `child_existing_frame is not None` always preserves that frame's persisted
  profile. Passing the activation profile to an existing historical frame is
  forbidden.
- `boundary.iteration_owner_node_id is not None` keeps the child frame
  historical. This includes `list/map-effect`, loop/recur-owned calls, and
  other multiply visited call boundaries.
- A fresh non-iterative Workflow Lisp retry frame after a failed predecessor
  is new state and therefore selects the profile; predecessor bytes remain
  untouched.
- Recurrent/loop-owned pure nodes remain noneligible and durable even within a
  profiled root.
- Component (b) memo keys, M3b/M3c, MC, MR, M4, E/P routing, provider
  isolation, and all owner-excluded security work remain out of scope.
- Existing checksum, projection-integrity, bound-input, checkpoint, result,
  and output-contract guards are neither reordered nor weakened.
- No test may assert prompt prose.

What this makes harder: generic embeddings do not automatically receive the
new policy, and an intentionally iterative child cannot elide even its
single-visit pure interior. Both limitations keep activation attributable to
typed provenance and keep multiply visited state durable.

## Execution discipline

For each behavior task:

1. write the named RED test first and capture the expected failure;
2. implement only the creation-point argument needed to turn it green;
3. run the narrow selector, then complete owning modules;
4. run `git diff --check`;
5. request one independent specification review followed by one independent
   quality review;
6. replay a review only after a material finding; and
7. commit the reviewed task before starting the next task.

Do not add an activation policy object, registry, new state field, new
diagnostic family, or helper module. The exact constant and existing typed
provenance/boundary fields are sufficient.

## Task 0: Commit and review the proposed activation plan

**Files:**

- Create: this plan
- Modify: `docs/index.md`
- Modify: `docs/plans/2026-07-26-substrate-maintenance-track.md`
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`
- Do not modify the accepted design, normative state contract, E/P routing, or
  production code

- [x] Record the proposed plan against M2 closure baseline `480e7e2f`, while
  keeping M3a eligible but implementation-unselected.
- [x] Add discoverability and a routing regression that distinguishes a
  proposed plan from a selected implementation tranche.
- [x] Run `git diff --check` and
  `pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py`.
- [x] Commit the proposed, unselected plan with subject
  `Propose pure replay activation plan`.
- [x] Request `M3A_ACTIVATION_PLAN_SPEC_APPROVED`, then
  `M3A_ACTIVATION_PLAN_QUALITY_APPROVED`, against the exact proposed-plan
  commit. Replay only after a material finding.
- [x] After both reviews approve, update only this status, the Task 0
  checkboxes, substrate/index routing, and their routing assertions to select
  Task 1; commit with subject `Select pure replay activation`.

## Task 1: Activate ordinary new Workflow Lisp roots

**Files:**

- Modify: `orchestrator/cli/commands/run.py`
- Modify: `orchestrator/cli/commands/resume.py`
- Modify: `tests/test_workflow_lisp_pure_result_replay.py`
- Modify: `tests/test_resume_command.py`
- Read without changing: `orchestrator/state.py`

- [ ] Add a RED public-run test that compiles a real `.orc` workflow through
  `run_workflow(...)`, then inspects its persisted state before any resume.
  Require:
  `result_persistence_profile == "derived_pure_replay.v1"`, successful
  eligible pure rows use exact shells, no eligible pure bundle is written,
  and declared outputs equal the existing explicit-profile control.
- [ ] Add a RED force-restart test that binds a deterministic new run ID and
  proves the newly initialized `.orc` root carries the profile while the
  source run remains byte-for-byte unchanged.
- [ ] Add or tighten the opposing ordinary-resume control: an existing
  absent-profile root remains absent-profile after ordinary resume. This test
  must fail if resume backfills the field.
- [ ] Run the RED selectors:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_pure_result_replay.py \
    -k 'public_run_activates_replay_profile'
  pytest -q \
    tests/test_resume_command.py \
    -k 'replay_profile and (force_restart or ordinary_resume)'
  ```

  Expected: new root assertions fail because both CLI creation paths omit the
  profile; the ordinary-resume negative is already green.
- [ ] Import `DERIVED_PURE_REPLAY_PROFILE` in each command module and pass it
  only to the new-root `StateManager.initialize(...)` call:

  ```python
  state_manager.initialize(
      ...,
      result_persistence_profile=DERIVED_PURE_REPLAY_PROFILE,
  )
  ```

  Do not modify `StateManager.initialize` defaults or the non-force-restart
  branch.
- [ ] Run the RED selectors green, then:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_pure_result_replay.py \
    tests/test_resume_command.py \
    tests/test_runtime_failure_persistence.py
  ```

- [ ] Obtain `M3A_TASK1_SPEC_APPROVED`, then
  `M3A_TASK1_QUALITY_APPROVED`, and commit with subject
  `Activate pure replay for new roots`.

## Task 2: Activate fresh non-iterative Workflow Lisp call frames

**Files:**

- Modify: `orchestrator/workflow/calls.py`
- Modify: `tests/test_subworkflow_calls.py`
- Read without changing: `orchestrator/workflow/call_frame_state.py`
- Read without changing:
  `tests/fixtures/workflow_lisp/valid/pure_result_replay_effect_barrier.orc`

- [ ] Add a RED constructor-boundary test using the compiled parent/child
  fixture from `_compile_imported_pure_replay_call_fixture(...)`. A fresh
  non-iterative child whose typed provenance is Workflow Lisp must receive
  `DERIVED_PURE_REPLAY_PROFILE`; the parent profile must not be consulted.
- [ ] Extend only that test fixture's parent with one eligible, data-dependent
  pure prefix consumed by the call:

  ```lisp
  (let* ((forwarded-seed (+ seed 0)))
    (call orchestrate
      :seed forwarded-seed
      :enabled enabled))
  ```

  Execute the parent under Task 1's activated new-root policy. Before
  interrupting the child, require the parent prefix to have an exact
  completion shell and no bundle. This supplies the validated prior replay
  boundary that root default resume needs; do not change checkpoint or
  `VALIDATED_FRAME_ENTRY_REPLAY` semantics to make a direct-call prefix pass.
- [ ] Add a RED clean integration test that executes that compiled parent,
  verifies the child's persisted state carries the profile, checks A/B are
  exact value-free shells, finds no child pure bundles, and compares declared
  parent outputs with the explicit-profile control.
- [ ] Add a RED interruption/resume integration test over the same parent:
  interrupt the child at E2 after E1 and its pure successors have committed,
  load the root through a fresh state manager/executor, resume through the
  parent, and require E1 exactly once, E2 exactly once, completed child
  settlement, exact output parity, and no pure value-bearing child surface.
  The expected RED is the missing child profile/value-elision assertions, not
  `lexical_default_resume_prior_boundary_missing`; the parent prefix must make
  the root resume path valid before production child activation changes.
- [ ] Run:

  ```bash
  pytest -q tests/test_subworkflow_calls.py \
    -k 'fresh_noniterative_replay_profile or nested_pure_replay_resume'
  ```

  Expected RED: the child constructor receives `None`, and the full child uses
  historical bundles.
- [ ] In `CallExecutor.execute_call`, pass the exact profile only at the
  existing child constructor:

  ```python
  result_persistence_profile=(
      DERIVED_PURE_REPLAY_PROFILE
      if (
          workflow_lisp_target
          and child_existing_frame is None
          and boundary.iteration_owner_node_id is None
      )
      else None
  )
  ```

  Use the already resolved `boundary`; do not parse step IDs or infer from
  paths. Do not move constructor, checksum, audit, or retry-lineage ordering.
- [ ] Run the RED selector green, then:

  ```bash
  pytest -q \
    tests/test_subworkflow_calls.py \
    tests/test_workflow_lisp_pure_result_replay.py \
    tests/test_runtime_step_lifecycle.py
  ```

- [ ] Obtain `M3A_TASK2_SPEC_APPROVED`, then
  `M3A_TASK2_QUALITY_APPROVED`, and commit with subject
  `Activate pure replay for fresh call frames`.

## Task 3: Lock the activation boundary in both directions

**Files:**

- Modify: `tests/test_subworkflow_calls.py`
- Modify: `tests/test_workflow_lisp_list_traversal.py`
- Modify: `orchestrator/workflow/calls.py` only if a RED case exposes an
  activation-predicate defect

- [ ] Preserve the existing non-Workflow-Lisp fresh-frame control and make it
  explicit that neither a profiled parent nor an `.orc`-looking path can
  activate a callee without typed Workflow Lisp provenance.
- [ ] Add an existing-frame control: resume of an absent-profile typed child
  passes `None` to the constructor and leaves the selected frame bytes
  unchanged before normal child execution.
- [ ] Add a fresh retry control: a new non-iterative Workflow Lisp retry frame
  after a failed predecessor receives the profile, while the failed
  predecessor stays byte-for-byte unchanged.
- [ ] Add an iteration control that starts from an actively profiled root and
  executes one `list/map-effect` item. Require every iteration-owned child
  frame to omit `result_persistence_profile`, even though its callee has typed
  Workflow Lisp provenance, and retain the child's ordinary value-bearing
  output. A historical parent alone would not catch accidental parent-profile
  inheritance.
- [ ] Retain the recurrent-pure M2 control proving a recurrent node remains
  fully durable inside an activated root.
- [ ] Run:

  ```bash
  pytest -q tests/test_subworkflow_calls.py \
    -k 'replay_profile or workflow_lisp_retry or non_workflow_lisp'
  pytest -q tests/test_workflow_lisp_list_traversal.py \
    -k 'effect_map_runtime_commits_exact_calls_in_source_order'
  pytest -q tests/test_workflow_lisp_pure_result_replay.py \
    -k 'recurrent_pure_node_keeps_ordinary_durable_surfaces'
  ```

- [ ] If all negatives pass without a production correction, commit the
  test-only boundary lock. If a predicate correction is necessary, make only
  the smallest change to the three-condition expression and rerun all Task 2
  owning modules.
- [ ] Obtain `M3A_TASK3_SPEC_APPROVED`, then
  `M3A_TASK3_QUALITY_APPROVED`, and commit with subject
  `Lock pure replay activation boundaries`.

## Task 4: Close M3a and preserve later gates

**Files:**

- Modify: `specs/state.md`
- Modify: `docs/design/workflow_lisp_pure_result_replay.md`
- Modify: `docs/design/workflow_lisp_state_layout.md`
- Modify: `docs/design/README.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/index.md`
- Modify: `docs/plans/2026-07-26-substrate-maintenance-track.md`
- Modify: this plan
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`
- Do not modify the lexical-checkpoint design unless implementation changed
  its semantics; activation alone does not
- Do not modify E/P routing

- [ ] Record the normative creation policy: typed public `.orc` run and
  force-restart roots plus fresh non-iterative typed Workflow Lisp child
  frames select the profile; generic initialization, existing roots/frames,
  non-Workflow-Lisp callees, and iteration-owned frames do not.
- [ ] Mark the capability `Implemented` only for that supported policy. Keep
  recurrent/loop replay, component (b), M3b, and M3c explicitly unselected.
- [ ] Compare an activated ordinary root with the historical explicit control.
  Record exact parity for outputs, artifacts, diagnostics, and settlement,
  plus durable leaf, `state.json`, and sidecar-byte reductions. The activated
  route must retain the M2 strict-decrease result.
- [ ] Collect any new tests, run `git diff --check`, routing, and the complete
  focused gate:

  ```bash
  pytest --collect-only -q \
    tests/test_workflow_lisp_pure_result_replay.py \
    tests/test_subworkflow_calls.py \
    tests/test_resume_command.py \
    tests/test_workflow_lisp_list_traversal.py

  pytest -q -n 16 --dist=worksteal \
    tests/test_workflow_lisp_pure_result_replay.py \
    tests/test_workflow_lisp_pure_projection_runtime.py \
    tests/test_workflow_lisp_lexical_checkpoints.py \
    tests/test_workflow_lisp_lexical_checkpoint_default_resume.py \
    tests/test_workflow_lisp_lexical_checkpoint_restore.py \
    tests/test_runtime_step_lifecycle.py \
    tests/test_state_manager.py \
    tests/test_resume_command.py \
    tests/test_subworkflow_calls.py \
    tests/test_workflow_state_projection.py \
    tests/test_observability_report.py \
    tests/test_runtime_failure_persistence.py \
    tests/test_workflow_lisp_list_traversal.py

  pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py
  ```

- [ ] In tmux, run the repository-standard broad non-security suite:

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

- [ ] Request `M3A_FINAL_SPEC_APPROVED`, then
  `M3A_FINAL_QUALITY_APPROVED`, against the same complete closure bytes.
- [ ] Commit the exact reviewed closure with subject
  `Complete pure replay activation`.
- [ ] Run a non-mutating postcommit routing/focused selector and bind it in an
  external closure record. Do not add a checked-in self-attestation.

## Acceptance summary

M3a completes only when:

- typed public new roots and force-restart roots select the profile;
- ordinary resume and generic initialization never backfill it;
- fresh non-iterative typed Workflow Lisp children select it independently of
  the parent;
- existing, non-Workflow-Lisp, and iteration-owned frames remain historical;
- a fresh retry selects it without mutating failed predecessors;
- nested interruption/resume proves E1 and E2 exactly once with output parity;
- activated eligible pure results leave no durable value-bearing surface;
- recurrent/loop-owned state remains durable;
- focused, routing, and broad non-security gates pass; and
- ordered final reviews approve the exact closure.

M3a completion does not select component (b), M3b, M3c, MC, MR, M4, E, or P.
