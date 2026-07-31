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
remain historical. The first Task 4 broad gate exposed three pre-existing M2
compatibility assumptions on production shapes, so closure also includes the
small generic replay correction for typed literal binding leaves,
metadata-bearing consumer value documents, and sparse union outputs. It
changes no profile selection, checkpoint authority, state schema, serialized
IR, or compiler algorithm.

**Tech Stack:** Python 3.13, Workflow Lisp validated bundles and provenance,
schema-2.1 root/call-frame state, the accepted pure-result replay runtime,
pytest, and repository routing tests.

---

**Status:** Task 4 closure candidate; after the first final quality rejection,
the restarted final specification review found and rejected a relevant-cursor
cache-hit bypass. Its TDD correction passes the refreshed focused gate; the
refreshed broad gate also passes; restarted ordered final reviews remain before
the exact closure commit and postcommit control. Tasks 1–3 landed at
`3442aef2`, `b931b7b8`, and `8a01bc2b`. Baseline commit `480e7e2f`, tree
`1886104a`. Ordered plan review approved corrected proposal commit `6e06b4c0`,
tree `6a4c4d6d`, plan SHA-256
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
Tasks 1–3 change only who selects that profile when creating new state. Task 4
owns any generic correctness correction required by the first activation-wide
broad gate; it may not weaken replay validation or expand the selected
activation/eligibility boundary.

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

- [x] Add a RED public-run test that compiles a real `.orc` workflow through
  `run_workflow(...)`, then inspects its persisted state before any resume.
  Require:
  `result_persistence_profile == "derived_pure_replay.v1"`, successful
  eligible pure rows use exact shells, no eligible pure bundle is written,
  and declared outputs equal the existing explicit-profile control.
- [x] Add a RED force-restart test that binds a deterministic new run ID and
  proves the newly initialized `.orc` root carries the profile while the
  source run remains byte-for-byte unchanged.
- [x] Add or tighten the opposing ordinary-resume control: an existing
  absent-profile root remains absent-profile after ordinary resume. This test
  must fail if resume backfills the field.
- [x] Run the RED selectors:

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
- [x] Import `DERIVED_PURE_REPLAY_PROFILE` in each command module and pass it
  only to the new-root `StateManager.initialize(...)` call:

  ```python
  state_manager.initialize(
      ...,
      result_persistence_profile=DERIVED_PURE_REPLAY_PROFILE,
  )
  ```

  Do not modify `StateManager.initialize` defaults or the non-force-restart
  branch.
- [x] Run the RED selectors green, then:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_pure_result_replay.py \
    tests/test_resume_command.py \
    tests/test_runtime_failure_persistence.py
  ```

- [x] Obtain `M3A_TASK1_SPEC_APPROVED`, then
  `M3A_TASK1_QUALITY_APPROVED`, and commit with subject
  `Activate pure replay for new roots`.

## Task 2: Activate fresh non-iterative Workflow Lisp call frames

**Files:**

- Modify: `orchestrator/workflow/calls.py`
- Modify: `tests/test_subworkflow_calls.py`
- Read without changing: `orchestrator/workflow/call_frame_state.py`
- Read without changing:
  `tests/fixtures/workflow_lisp/valid/pure_result_replay_effect_barrier.orc`

- [x] Add a RED constructor-boundary test using the compiled parent/child
  fixture from `_compile_imported_pure_replay_call_fixture(...)`. A fresh
  non-iterative child whose typed provenance is Workflow Lisp must receive
  `DERIVED_PURE_REPLAY_PROFILE`; the parent profile must not be consulted.
- [x] Extend only that test fixture's parent with one eligible, data-dependent
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
- [x] Add a RED clean integration test that executes that compiled parent,
  verifies the child's persisted state carries the profile, checks A/B are
  exact value-free shells, finds no child pure bundles, and compares declared
  parent outputs with the explicit-profile control.
- [x] Add a RED interruption/resume integration test over the same parent:
  interrupt the child at E2 after E1 and its pure successors have committed,
  load the root through a fresh state manager/executor, resume through the
  parent, and require E1 exactly once, E2 exactly once, completed child
  settlement, exact output parity, and no pure value-bearing child surface.
  The expected RED is the missing child profile/value-elision assertions, not
  `lexical_default_resume_prior_boundary_missing`; the parent prefix must make
  the root resume path valid before production child activation changes.
- [x] Run:

  ```bash
  pytest -q tests/test_subworkflow_calls.py \
    -k 'fresh_noniterative_replay_profile or nested_pure_replay_resume'
  ```

  Expected RED: the child constructor receives `None`, and the full child uses
  historical bundles.
- [x] In `CallExecutor.execute_call`, pass the exact profile only at the
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
- [x] Run the RED selector green, then:

  ```bash
  pytest -q \
    tests/test_subworkflow_calls.py \
    tests/test_workflow_lisp_pure_result_replay.py \
    tests/test_runtime_step_lifecycle.py
  ```

- [x] Obtain `M3A_TASK2_SPEC_APPROVED`, then
  `M3A_TASK2_QUALITY_APPROVED`, and commit with subject
  `Activate pure replay for fresh call frames`.

## Task 3: Lock the activation boundary in both directions

**Files:**

- Modify: `tests/test_subworkflow_calls.py`
- Modify: `tests/test_workflow_lisp_list_traversal.py`
- Modify: `orchestrator/workflow/calls.py` only if a RED case exposes an
  activation-predicate defect

- [x] Preserve the existing non-Workflow-Lisp fresh-frame control and make it
  explicit that neither a profiled parent nor an `.orc`-looking path can
  activate a callee without typed Workflow Lisp provenance.
- [x] Add an existing-frame control: resume of an absent-profile typed child
  passes `None` to the constructor and leaves the selected frame bytes
  unchanged before normal child execution.
- [x] Add a fresh retry control: a new non-iterative Workflow Lisp retry frame
  after a failed predecessor receives the profile, while the failed
  predecessor stays byte-for-byte unchanged.
- [x] Add an iteration control that starts from an actively profiled root and
  executes one `list/map-effect` item. Require every iteration-owned child
  frame to omit `result_persistence_profile`, even though its callee has typed
  Workflow Lisp provenance, and retain the child's ordinary value-bearing
  output. A historical parent alone would not catch accidental parent-profile
  inheritance.
- [x] Retain the recurrent-pure M2 control proving a recurrent node remains
  fully durable inside an activated root.
- [x] Run:

  ```bash
  pytest -q tests/test_subworkflow_calls.py \
    -k 'replay_profile or workflow_lisp_retry or non_workflow_lisp'
  pytest -q tests/test_workflow_lisp_list_traversal.py \
    -k 'effect_map_runtime_commits_exact_calls_in_source_order'
  pytest -q tests/test_workflow_lisp_pure_result_replay.py \
    -k 'recurrent_pure_node_keeps_ordinary_durable_surfaces'
  ```

- [x] If all negatives pass without a production correction, commit the
  test-only boundary lock. If a predicate correction is necessary, make only
  the smallest change to the three-condition expression and rerun all Task 2
  owning modules.
- [x] Obtain `M3A_TASK3_SPEC_APPROVED`, then
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
- Modify, only if the broad gate exposes a generic replay correctness defect:
  `orchestrator/workflow/pure_result_replay.py`
- Modify, with TDD coverage for any such correction:
  `tests/test_workflow_lisp_pure_result_replay.py`
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`
- Do not modify the lexical-checkpoint design unless implementation changed
  its semantics; activation alone does not
- Do not modify E/P routing

- [x] Record the normative creation policy: typed public `.orc` run and
  force-restart roots plus fresh non-iterative typed Workflow Lisp child
  frames select the profile; generic initialization, existing roots/frames,
  non-Workflow-Lisp callees, and iteration-owned frames do not.
- [x] Mark the capability `Implemented` only for that supported policy. Keep
  recurrent/loop replay, component (b), M3b, and M3c explicitly unselected.
- [x] Compare an activated ordinary public root with the explicit-profile
  control and a route-identical historical absent-profile control. Record
  exact parity for outputs, artifacts, diagnostics, and settlement, plus
  durable leaf, `state.json`, and sidecar-byte reductions. The activated route
  must retain the M2 strict-decrease result.

  Fresh evidence at baseline `8a01bc2b`: all four parity fields are exact
  against both controls. Historical → activated public storage is durable
  leaves 106 → 98, `state.json` 6,539 → 6,199 bytes, and run-owned sidecars
  622,815 → 611,912 bytes. The external 1,983-byte measurement log has
  SHA-256
  `4017d50f06235cb2a3687d57f45de3abff2b737f66afe1fb574b5fc8e20036ea`.
  Independently compiled temporary-workspace program digests are not asserted
  because absolute source-origin provenance differs; this measurement changes
  no program, schema, or repository authority.
- [x] Collect any new tests, run `git diff --check`, routing, and the complete
  focused gate. The pre-broad documentation candidate collected 548 tests,
  passed 67 routing tests and 947 focused tests; because the broad correction
  changed production and test bytes, the corrected candidate reran these
  gates: 563 tests collected in 1.99 seconds, 67 routing tests passed in 1.49
  seconds, and 962 focused tests passed in 9.42 seconds. The respective log
  SHA-256 values are
  `ad3b0e79575dbd8ecb17b9e2b9c633ed84641cc27f169eb1111c078ef8ce8412`,
  `a7cfb2a05670e0783139a2b4c300901aefefb247c8469eb24c39f420790a5136`,
  and
  `bb845812826f13961930ff78f95281d45d1de070f2e683b44f806b645bcb29c9`:
  the final docs/routing-only status delta retained 563 collected in 2.14
  seconds and 67 routing passes in 1.51 seconds, with log SHA-256 values
  `3c945922161cee1cccf1cacd21ef4293d978a102183b25b00ec967dde9e2a17d`
  and
  `46b0c0266cb3d00b18e9ea40adef91a4f626a56301b1fbc7107ef5fcd8533a18`.
  The final-quality TDD correction initially added five collected cases, so
  that intermediate exact collection was 568 tests in 2.15 seconds (log SHA-256
  `229e877192ba3fa4ad18965824985c770faef0b892b6d21df9ac8381e34f1beb`)
  and its focused gate passed 967 tests in 8.52 seconds (log
  SHA-256
  `ea3dea73094da1a0910e498ca3beed1b6bf5f4dc547d3755ca34ed6f1ff27ee0`).
  The relevant-cursor correction adds one opposing case. Current exact
  collection is 569 tests in 2.03 seconds (log SHA-256
  `b8f35e8a9ca53fa7f9f378f5cc7108d489b3de8c1bac2208ac83c6f488428d09`);
  the refreshed focused gate passes 968 tests in 9.72 seconds (log SHA-256
  `5c2b20743ae86b56b287b472a5c784731b179cf6aa66666babc530afefe298cd`).

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

- [x] Diagnose the first broad result without weakening the gate. It recorded
  10 failures, 9,865 passes, 19 skips, and 5 warnings in 147.13 seconds (log
  SHA-256
  `6fdffec5e5c8a177372efff2a81d760fd62f1776c7932a2837a49d50ba4e4482`).
  All 10 failures were activation-exposed generic replay defects:

  - typed pure binding value documents may contain compiler-valid literal
    leaves as well as exact ref leaves;
  - selected consumer/checkpoint value documents may contain JSON literals and
    compiler metadata beside exact ref leaves; and
  - union pure results contain only the discriminant, shared members, and
    active variant members, not every statically possible output.

- [x] Correct those three assumptions under TDD without changing activation,
  eligibility, serialized state/IR, checkpoint authority, or compiler output.
  Literal subtrees are checked against their payload binding type; malformed
  ref objects and wrong literal shapes/types still fail. Sparse union
  settlement requires the exact active member set, while replay completion is
  bound to the validated overlay row. After both cache-witness corrections,
  the complete pure-replay module passes 122 tests; the five production-shape
  modules containing all 10 original failures pass 259; and the six-module
  integration matrix therefore passes 381.
- [x] Obtain `M3A_INTEGRATION_FIX_SPEC_APPROVED`, then
  `M3A_INTEGRATION_FIX_QUALITY_APPROVED`, for the correction before regenerating
  final closure evidence. Both approved exact production/unit-test diff
  SHA-256
  `5ae2e6c279b6e3aa36bf28920debc5d3999254533c4f8e199ffb8d88888195f3`;
  the quality replay independently confirmed 116 module tests, clean
  `py_compile`, clean diff formatting, and no changed-helper pyright errors.
- [x] Record the first final-review disposition. Specification approved exact
  complete diff SHA-256
  `d03dc3331f37ab65684d4ce2fd162c1cc78ef79544a770149db953d205b68f6e`,
  then quality correctly rejected it: a retained overlay row returned before
  validating the current visit/result witness. Four RED negative cases prove
  missing/non-one visits and missing/malformed rows fail closed. The opposing
  RED/green case preserves the intentional active-executor view, where
  `state["steps"]` retains the exact validated full result while the state
  manager persists the shell. A cache hit now first validates the visit and
  accepts only either the exact durable completion shell or an active result
  exactly equal to the private validated cache row. The new production/unit
  diff SHA-256 is
  `ebd17e4c307a1521f6ee51967bf9e893bbf1de80b41bf2b6fbe7457de727dcd5`.
- [x] Record the restarted final-specification disposition. It rejected exact
  complete diff SHA-256
  `3236b6844ed3ce63239f85a911b190c7d8bdbe8457fa0046e07ed891ce0c474f`:
  the exact cached active result still returned while a running cursor targeted
  the same presentation name/step identity. The new RED case first proves the
  closed classifier reports `progress_witness_invalid`; the runtime now rejects
  that same relevant cursor while the opposing active-result case retains an
  unrelated downstream cursor. Seven cache cases pass, the owner module passes
  122 tests, the unchanged production-shape set passes 259, and their combined
  matrix passes 381 (log SHA-256
  `da7204139fb105b1e92d980bbd7cea608e1277fb10ab60c5b05cf1b843f45a2f`).
  Current production/unit-test diff SHA-256 is
  `c36a5895c55da9cc887be5deb47095f1bf95d268cdb4c55c50452a2f4ce8f918`.
- [x] In tmux, run the repository-standard broad non-security suite:

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

  The first corrected replay passed all production behavior but failed one
  candidate-owned routing assertion that still required the pre-correction
  sentence `the final candidate must rerun these gates`: 9,889 passed, 1
  failed, 19 skipped, and 5 warnings in 150.67 seconds (log SHA-256
  `2b36ceadfc64a435be41b8faf45cc2030068a9a66d86fca16a89165f2eccc369`).
  After aligning that assertion with the already-recorded corrected evidence,
  the exact replay passed 9,890 tests, 19 skipped, and 5 warnings in 149.83
  seconds. Its log SHA-256 is
  `8787a8eb3411c707cd636287b56b68945d80ba63e83ecb82fa5648aff7d356d7`.
  A final docs/routing-only exact-candidate replay retained 9,888 passes, 19
  skips, and 5 warnings but exposed two unrelated load-sensitive failures:
  Q5 synthetic-provider ingress shutdown reported `failed` rather than
  `finished`, and the L4 Neovim client missed its initial progress settlement.
  Its log SHA-256 is
  `69ed15c075264934936ee6203a8eed3301da3b3425fa8e45c64cae742a0f9ece`.
  Neither failed module is candidate-owned or imported by the replay
  mechanism; both exact nodes passed immediately when replayed serially
  (8.96 and 1.92 seconds). These runs remain pre-cache-witness historical
  evidence. Because the final-quality correction changed production/unit-test
  bytes and added five collected cases, the 9,890-pass result does not satisfy
  the refreshed closure gate.

  The post-quality, pre-cursor-correction broad gate passed 9,895 tests with 19
  skipped and 5 warnings in 149.91 seconds. Its 12,036-byte log SHA-256 is
  `07615bb605d401a068a93aeed2476544104d0721fca4d45d80785ac57eafbab3`.
  It remains historical evidence because the restarted specification
  correction changed production/unit-test bytes and added one collected case;
  it is not the current closure gate.

  The post-cursor-correction broad gate passed 9,896 tests with 19 skipped and
  5 warnings in 147.72 seconds. Its 12,036-byte log SHA-256 is
  `d4324439f68b6881f353d5e3f436cc4d460f4728b0359d3b8297a795284efb6d`.
  Evidence-only status reconciliation after that run is covered by the routing
  replay before final review.

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
- typed literal binding leaves and metadata-bearing consumer value documents
  preserve exact-ref dependency indexing without accepting malformed refs or
  wrong literal types;
- sparse union results settle and replay with exactly their active output
  members while retaining the complete static address catalog;
- recurrent/loop-owned state remains durable;
- focused, routing, and broad non-security gates pass; and
- ordered final reviews approve the exact closure.

M3a completion does not select component (b), M3b, M3c, MC, MR, M4, E, or P.
