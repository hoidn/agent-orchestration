# Pure-Result Replay Feasibility Component Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan
> task-by-task. Use `superpowers:test-driven-development` for every behavior
> change. Use `superpowers:verification-before-completion` before recording
> any task or gate as complete. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Close the executable prerequisite for substrate Phase M2 component
(a) by proving value-free successful pure-result persistence and deterministic
resume replay through the real compiler, state manager, fresh executor, and a
new executor's ordinary resume path.

**Architecture:** New state created explicitly with
`derived_pure_replay.v1` keeps only an exact value-free completion shell for an
eligible successful pure projection. A small replay module derives a transient
typed dependency index from the validated executable, audits the closed
profile, and reconstructs required values into an in-memory overlay. State
begin/settlement operations make visit/cursor/shell transitions atomic, while
checkpoint selection filters only proven replay-eligible pure points and
otherwise preserves the existing nearest-durable failure rules. Historical
state remains on the byte-compatible bundle-backed path.

**Tech stack:** Python 3.13, Workflow Lisp compiler and executable IR, schema
2.1 run and call-frame state, atomic JSON state replacement, lexical
checkpoints, pytest, and the existing pure-expression evaluator.

**Status:** historical complete. The review baseline is
`19a98c8b`; Task 0 landed at `09c286dc`, Task 1 at `159a8f5e`, Task 2 at
`5644bd73`, Task 3 at `cf0490d1`, and its completed-resume compatibility
correction at `ce02cd17`.
`M2_FEASIBILITY_PLAN_SPEC_APPROVED` then
`M2_FEASIBILITY_PLAN_QUALITY_APPROVED` approved the corrected execution plan.
The executable criteria, final broad verification, and ordered closure reviews
passed. M2 component (a) is historical complete; M3a is eligible but
unselected pending its separate reviewed plan.

## Authority and bounds

This plan executes only component (a) of Phase M2 under:

- `docs/design/workflow_lisp_pure_result_replay.md`;
- `docs/plans/2026-07-26-substrate-maintenance-track.md`;
- `docs/reports/2026-07-26-m0-decision-brief.md`;
- `specs/state.md`; and
- the lexical checkpoint designs routed by `docs/design/README.md`.

The following constraints are load-bearing:

- The feasibility fixture selects `derived_pure_replay.v1` only through a
  generic production state-initialization argument. No fixture flag, evidence
  file, debug projection, or replay-helper call controls runtime behavior.
- Normal `orchestrate run` and `orchestrate resume` creation stays on the
  historical profile throughout this plan. CLI activation belongs to a
  separate reviewed M3a plan after M2 acceptance.
- The runtime derives its replay dependency index in memory from only
  validator-owned reference fields and the exact compiled projection catalog.
  It does not add fields to serialized executable IR or runtime plans.
- Root/callee checksums, source and projection identity, bound inputs, effect
  rows, checkpoint records, output contracts, public artifacts, settlement,
  and historical corruption diagnostics remain as strict as today.
- No provider, command, resource transition, call boundary, materialized view,
  loop/recur visit, or other multiply visited node is replayed or elided.
- Component (b) memo keys, M3b/M3c, MC, MR, M4, the E and P programs, provider
  isolation, and all owner-excluded security work are outside this plan.
- The bounded M2/M3a correctness exception to the track's deletion preference
  covers only the profile, exact shell, atomic progress/settlement, transient
  typed dependency index, fail-closed persistence audit, and replay/checkpoint
  preparation. Source line change must be reported. Durable value count and
  state/sidecar bytes must both strictly decrease on the feasibility fixture.
- Every behavior task gets one ordered independent specification review
  followed by one independent quality review. Replay a review only after a
  material finding.

What this makes harder: the implementation carries two explicit persistence
profiles and a narrow frame-entry resume mode before the default profile
changes. It also defers positive nested-frame rollout and normal CLI creation
to M3a. That separation is intentional: the M2 proof can fail or be revised
without changing new user runs.

## Execution discipline

For each task:

1. add or tighten the named RED test first;
2. run the narrow selector and preserve its fresh failing output;
3. implement only enough production behavior to turn that selector green;
4. run the complete owning modules and `git diff --check`;
5. request ordered specification then quality review;
6. correct and replay only a materially affected review; and
7. commit the green reviewed task before starting the next task.

Do not edit a test merely to accommodate an unexplained behavior change. Do
not assert literal prompt prose. Use generic names in production code,
diagnostics, fixtures, and tests.

## Task 0: Review and commit the bounded plan

**Files:**

- Create: this plan
- Modify: `docs/index.md`
- Modify: `docs/plans/2026-07-26-substrate-maintenance-track.md`
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`
- Do not modify the accepted design except for nonmaterial plan routing

- [x] Bind the candidate to baseline `19a98c8b`, the plan SHA-256, the complete
  diff SHA-256, and fresh routing-test output.
- [x] Keep the design proposed, the executable prerequisite open, normal CLI
  state historical-profile, M2 incomplete, and M3a unselected.
- [x] Run:

  ```bash
  git diff --check
  pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py
  ```

- [x] Request `M2_FEASIBILITY_PLAN_SPEC_APPROVED`, then
  `M2_FEASIBILITY_PLAN_QUALITY_APPROVED`, against the same candidate bytes.
  Replay only after a material finding.
- [x] Commit the exact reviewed plan/routing bytes with subject
  `Plan pure result replay feasibility`.

## Task 1: Land the real fixture and transient dependency index

**Status:** complete at `159a8f5e`.

**Files:**

- Create:
  `tests/fixtures/workflow_lisp/valid/pure_result_replay_effect_barrier.orc`
- Create: `tests/test_workflow_lisp_pure_result_replay.py`
- Read without changing:
  `tests/test_workflow_lisp_pure_projection_runtime.py`
- Read without changing:
  `tests/test_workflow_lisp_lexical_checkpoint_restore.py`

- [x] Author one generic compiled workflow with this observable spine:

  ```text
  bound input -> pure A -> counted deterministic effect E1
      -> pure B(A, E1) -> interruptible effect E2 -> settlement
  ```

  Include a pure-only prefix route so the same compiled fixture can exercise
  validated frame-entry replay. Keep provider calls and authored prompt prose
  out of the fixture.
- [x] Build a test harness through the public compiler, ordinary
  `StateManager.initialize`, `WorkflowExecutor.execute()`, a persisted
  interruption, a freshly loaded state manager, and a new
  `WorkflowExecutor(...).execute(resume=True)`. The harness may replace the
  deterministic command adapter to count E1/E2 calls; it may not invoke a
  replay function directly or use test-state surgery such as
  `_resume_failed_single_step`, `_force_single_generated_step_resume`, or
  direct `_write_state()` construction.
- [x] Add a passing historical-profile control that captures:
  canonical diagnostics, declared artifacts, settlement result, serialized
  executable/runtime-plan digests, state value count, state bytes, and
  run-owned sidecar bytes.
- [x] Prove the historical control still creates and reuses its ordinary pure
  bundle and does not contain the replay-profile field.
- [x] Collect and run:

  ```bash
  pytest --collect-only -q tests/test_workflow_lisp_pure_result_replay.py
  pytest -q tests/test_workflow_lisp_pure_result_replay.py \
    -k 'historical_profile or fixture_compiles'
  ```

  Expected: collection succeeds and the characterization control passes
  without production changes.
- [x] Keep the green characterization in the Task 1 candidate; do not commit a
  deliberate RED suite or request a separate review for unchanged historical
  behavior.

### Derive the transient typed replay index

**Files:**

- Create: `orchestrator/workflow/pure_result_replay.py`
- Modify: `orchestrator/workflow/runtime_plan.py` only if a read-only
  executable catalog seam is needed
- Modify: `tests/test_workflow_lisp_pure_result_replay.py`
- Modify: `tests/test_workflow_lisp_pure_projection_runtime.py` only for
  compatibility regression coverage

- [x] Add RED cases proving the compiled fixture's validated compatibility
  reference documents derive exact `WorkflowInputAddress` and
  `NodeResultAddress` objects with node, field/member, frame/scope, and output
  contract preserved.
- [x] Add both-direction negatives for unknown field/member/scope, duplicate
  address authority, arbitrary text containing a ref-like string,
  cross-frame authority, positional-only runtime dependencies, cycles,
  ambiguous reachability, inactive-branch non-evaluation, and loop/recur or
  multiply visited ownership.
- [x] Assert byte-identical serialized executable IR and runtime-plan
  projections before and after index derivation.
- [x] Run:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_pure_result_replay.py \
    tests/test_workflow_lisp_pure_projection_runtime.py \
    -k 'dependency_index or serialized_plan_unchanged or eligibility'
  ```

  Expected RED: no identity-neutral replay index exists.
- [x] Implement one immutable, identity-neutral in-memory index:
  walk only validator-owned reference-bearing fields; parse the closed surface
  grammar; resolve against the exact projection catalog and typed addresses;
  prove the eligible pure subgraph acyclic, single-visit, and non-iterative;
  and return closed classification failures rather than guessing.
- [x] Keep the executable and runtime-plan serializers byte-unchanged. Do not
  treat positional `dependencies` as dataflow and do not persist the derived
  index.
- [x] Map all index/classification failures to
  `pure_result_replay_unavailable` with the bounded
  `dependency_index_invalid`, `reachability_ambiguous`, or
  `multiple_visit_region` reason.
- [x] Run the focused selector, the two complete owning modules,
  `git diff --check`, obtain
  `M2_FEASIBILITY_TASK1_SPEC_APPROVED` followed by
  `M2_FEASIBILITY_TASK1_QUALITY_APPROVED`, and commit with subject
  `Derive pure replay dependency index`.

## Task 2: Add the profile, exact shell, and atomic witness operations

**Status:** complete at `5644bd73`.

**Files:**

- Modify: `orchestrator/state.py`
- Modify: `orchestrator/workflow/call_frame_state.py`
- Modify: `orchestrator/workflow/pure_result_replay.py`
- Modify: `orchestrator/workflow/outcomes.py`
- Modify: `tests/test_state_manager.py`
- Modify: `tests/test_runtime_step_lifecycle.py`
- Modify: `tests/test_workflow_lisp_pure_result_replay.py`

- [x] Add RED serialization tests for:
  absent historical profile, exact `derived_pure_replay.v1`, unknown profile
  rejection, and no resume-time backfill.
- [x] Add RED exact-shape tests for the successful completion shell. Reject
  every extra value/output/artifact/debug/duration/bundle field and do not use
  `StepResult.to_dict()` to build the shell.
- [x] Add crash-injection tests around an eligible-pure begin transaction.
  Observers may see only the old unstarted state or the new visit plus matching
  cursor, never a positive visit alone.
- [x] Add crash-injection tests around successful and failed settlement.
  Observers may see only the matching cursor or the exact shell/full failure
  plus cleared cursor.
- [x] Add the interrupted-pure case: resume reuses the existing visit and
  cursor, does not call ordinary visit increment, evaluates once, and settles
  that same visit.
- [x] Run:

  ```bash
  pytest -q \
    tests/test_state_manager.py \
    tests/test_runtime_step_lifecycle.py \
    tests/test_workflow_lisp_pure_result_replay.py \
    -k 'persistence_profile or pure_completion_shell or atomic_pure or same_visit or progress_witness'
  ```

  Expected RED: the profile and atomic eligible-pure witness operations do not
  exist.
- [x] Add the optional profile to `RunState` and the generic
  `StateManager.initialize` contract. Serialize it only when present; reject
  unknown values; do not change normal CLI callers.
- [x] Add dedicated exact shell build/validate helpers and guarded atomic
  root-state operations for:
  begin new eligible visit, reuse matching interrupted visit, settle success,
  and settle failure.
- [x] Give `_CallFrameStateManager` equivalent atomic operations, but do not
  activate or backfill the profile on existing frames. Any constructor path
  that loads an existing frame must audit before writing.
- [x] Classify every visit/cursor/row combination into unstarted, interrupted,
  derived-complete, durable failure/skip, or
  `progress_witness_invalid`.
- [x] Run focused and complete owning modules, `git diff --check`, obtain
  `M2_FEASIBILITY_TASK2_SPEC_APPROVED` followed by
  `M2_FEASIBILITY_TASK2_QUALITY_APPROVED`, and commit with subject
  `Add atomic pure replay witnesses`.

## Task 3: Elide values and resume through audited boundaries

**Status:** complete at `cf0490d1`, with broad-discovered completed-resume
compatibility correction `ce02cd17` accepted by
`M2_FEASIBILITY_TASK3_CORRECTION_SPEC_APPROVED` then
`M2_FEASIBILITY_TASK3_CORRECTION_QUALITY_APPROVED`.

### Suppress replay-profile persistence

**Files:**

- Modify: `orchestrator/workflow/pure_result_replay.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/outcomes.py`
- Modify: `orchestrator/workflow/steps/pure_projection.py`
- Modify: `orchestrator/workflow/dataflow.py`
- Modify: `orchestrator/workflow_lisp/lexical_checkpoints.py`
- Modify: `tests/test_workflow_lisp_pure_result_replay.py`
- Modify: `tests/test_workflow_lisp_pure_projection_runtime.py`
- Modify: `tests/test_workflow_lisp_lexical_checkpoints.py`

- [x] Add RED clean-run assertions that an explicitly initialized
  replay-profile run:
  keeps the normalized full A/B results only in the active executor overlay;
  durably records their exact shells; writes no pure bundle; writes no
  matching private artifact-version value; writes no pure checkpoint record;
  and does not place a pure value in a restore payload.
- [x] Add RED mixed-profile cases for a value-bearing successful eligible row,
  pure bundle, private lineage value, pure checkpoint record, and pure restore
  binding. Every case must fail with `profile_conflict` before any prologue,
  provider/effect dispatch, state write, or nested-frame constructor write.
- [x] Add historical both-direction controls: valid old row/bundle reuse stays
  byte-compatible, and each current malformed-bundle diagnostic remains
  unchanged.
- [x] Run:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_pure_result_replay.py \
    tests/test_workflow_lisp_pure_projection_runtime.py \
    tests/test_workflow_lisp_lexical_checkpoints.py \
    -k 'value_free or profile_conflict or historical_bundle or pure_checkpoint'
  ```

  Expected RED: replay-profile execution still writes ordinary pure values and
  bundles.
- [x] Move the closed profile/witness/forbidden-surface audit after ordinary
  source, checksum, projection, and bound-input validation but before executor
  prologue recovery or any existing-frame mutation.
- [x] On exact replay profile, branch before pure bundle path allocation,
  lookup, reuse, or write. Preserve the full result only in a replay overlay
  keyed by root/call-frame scope, executable node identity, exact result
  address, and visit identity. Persist and
  summarize the exact shell, and suppress only the proven eligible pure
  private-lineage/checkpoint/restore values.
- [x] Failed and skipped pure results remain ordinary full durable rows.
  Noneligible, recurrent, loop-owned, and historical pure results stay on the
  current durable path.
- [x] Keep replay algorithms out of `executor.py`; the executor coordinates
  audited results and calls the small replay module.
- [x] Keep this green suppression slice in the Task 3 candidate and proceed
  directly to resume selection. Do not request an extra review for the
  intermediate slice.

### Resume through the nearest durable boundary

**Files:**

- Modify: `orchestrator/workflow/pure_result_replay.py`
- Modify: `orchestrator/workflow/resume_planner.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow_lisp/lexical_checkpoint_default_resume.py`
- Modify: `orchestrator/workflow_lisp/lexical_checkpoint_restore.py`
- Modify: `tests/test_workflow_lisp_pure_result_replay.py`
- Modify: `tests/test_workflow_lisp_lexical_checkpoint_default_resume.py`
- Modify: `tests/test_workflow_lisp_lexical_checkpoint_restore.py`
- Modify: `tests/test_resume_command.py`

- [x] Add the RED main spine: interrupt E2 after committed E1 and settled B,
  construct a new state manager and executor, and call ordinary
  `.execute(resume=True)`. Require A/B replay before E2, E1 call count exactly
  one, final artifact/diagnostic/settlement parity with the historical clean
  control, and exact durable shells without pure values.
- [x] Add RED interrupted-current spines for both A and B. Each has one
  matching current cursor and visit but no shell; resume evaluates that node
  once, settles the same visit, and continues without invoking any effect
  during replay preparation. A exercises the pre-first-durable-boundary case.
- [x] Add both directions for checkpoint filtering:
  remove only replay-eligible pure points before selection; select E1's valid
  unique-nearest durable record; and retain the existing failure if that
  nearest remaining record is missing, malformed, ambiguous, or invalid.
  Never scan past it.
- [x] Add both directions for `VALIDATED_FRAME_ENTRY_REPLAY`: admit only a
  reached prefix made entirely of validated bound inputs and successful
  eligible shells with no node that should own a durable checkpoint. Reject a
  zero-record prefix containing any durable owner.
- [x] Add invalid replay-source cases for missing/invalid bound input, missing
  or invalid E1 durable result, unresolved binding, pure evaluation failure,
  and output-contract failure. Require
  `pure_result_replay_unavailable` before E2 dispatch.
- [x] Add an inactive-branch case proving an eligible projection outside the
  selected route is never evaluated. Add settlement/finalization-next cases
  proving the consumer's exact typed result addresses seed only the required
  replay dependency closure.
- [x] Run:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_pure_result_replay.py \
    tests/test_workflow_lisp_lexical_checkpoint_default_resume.py \
    tests/test_workflow_lisp_lexical_checkpoint_restore.py \
    tests/test_resume_command.py \
    -k 'pure_replay or frame_entry_replay or nearest_durable or interrupted_pure'
  ```

  Expected RED: the planner treats shells as ordinary completed rows and has
  no replay reconstruction path.
- [x] Select the restart boundary exactly once from audited witness states and
  pass it through checkpoint candidate selection, restore selection, and
  executor dispatch. Do not recompute a second positional restart.
- [x] Pass one profile-filtered checkpoint candidate tuple through
  nearest-prior selection, default decision, and restore candidate selection.
  Preserve node-local primacy, unique-nearest rules, and all existing durable
  record validation.
- [x] Activate the validated restore overlay first, reconstruct the exact
  transient dependency closure second, then dispatch the true boundary.
  `_result_for_node_id()` must consult the replay overlay by exact
  root/call-frame scope, executable node identity, result address, and visit
  identity before a persisted shell can mask the full value. Add a regression
  proving node-only or presentation-only lookup cannot retrieve replay
  authority.
- [x] Implement `VALIDATED_FRAME_ENTRY_REPLAY` as the one closed zero-prior
  case, not as a fallback past invalid durable authority.
- [x] Keep this green resume slice in the Task 3 candidate and proceed
  directly to the nested/recurrent compatibility edges.

### Close nested, recurrent, reporting, and compatibility edges

**Files:**

- Modify: `orchestrator/workflow/pure_result_replay.py`
- Modify: `orchestrator/workflow/calls.py`
- Modify: `orchestrator/workflow/call_frame_state.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_workflow_lisp_pure_result_replay.py`
- Modify: `tests/test_subworkflow_calls.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_runtime_step_lifecycle.py`
- Modify: status/report tests only if the exact owning module requires it

- [x] Add a fresh non-iterative call-frame classification control without
  activating profile inheritance in normal runtime. Add nested-frame
  mixed-profile conflicts for value rows, bundles, private lineage,
  checkpoints, and restore values.
- [x] Add a read-only existing-frame loader/audit seam and invoke it from call
  dispatch before constructing `_CallFrameStateManager`. Prove the frame is
  loaded, read, and audited without any constructor or bound-input validation
  write before a conflict is reported.
- [x] Prove every loop/recur body, multiple-visit projection, and
  iteration-owned call frame retains full durable results and ordinary
  checkpoint behavior.
- [x] Prove status and persisted-state summaries expose the exact completion
  shell, never a reconstructed value, while public artifacts, diagnostics, and
  settlement expose the ordinary final values.
- [x] Prove absent-profile state and existing nested frames retain current
  read/reuse/failure behavior byte-for-byte.
- [x] Run:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_pure_result_replay.py \
    tests/test_subworkflow_calls.py \
    tests/test_resume_command.py \
    tests/test_runtime_step_lifecycle.py \
    -k 'call_frame or nested_profile or loop or recurrent or status_shell'
  ```

  Expected RED: the closed nested conflict and reporting matrix is incomplete.
- [x] Implement only the missing generic audits and classification seams.
  Positive nested replay activation remains for M3a; do not add a second
  fixture-only profile path.
- [x] Run every Task 3 focused and complete owning module,
  `git diff --check`, obtain `M2_FEASIBILITY_TASK3_SPEC_APPROVED` followed by
  `M2_FEASIBILITY_TASK3_QUALITY_APPROVED`, and commit with subject
  `Implement pure replay feasibility runtime`.

## Task 4: Prove feasibility and close or revise M2

**Status:** historical complete. Closure evidence:

- collection: 100 tests;
- post-correction 11-module feasibility matrix: 694 passed in 8.31 seconds;
  log SHA-256
  `f374f391c96e6b1535bd212ac707cf77feae6f44fa630dfb4664c5b6e54b1336`;
- canonical executable IR SHA-256
  `d24c09692754cf5d3846f99a694a6e108013ee0a6764878a7f5a1101c7f224cc`
  and runtime-plan SHA-256
  `1857767685cf7e67d43acbb819105eb8ce9e5b6b62fc720bffef7ca365762bbb`
  are equal across historical and replay profiles;
- outputs, artifacts, diagnostics, and settlement have exact parity; replay
  calls are `[E1, E2]`, E1 executes exactly once, historical pure bundles count
  2, replay pure bundles count 0, and A/B replay rows are exact shells;
- equivalent resumed samples reduce durable leaves 80 → 72 (−8; 10.0%),
  `state.json` 4,975 → 4,636 bytes (−339; 6.814070%), and run-owned sidecars
  26,452 → 15,561 bytes (−10,891; 41.172690%);
- historical-profile public CLI smoke completed with output `count=3`,
  `label=tick`, and omitted `result_persistence_profile`;
- source numstat from `09c286dc` through `ce02cd17`: orchestrator
  +3,518/−84 across 12 files, tests +5,911/−15 across 12 files, total
  +9,429/−99 across 24 files; log SHA-256
  `e8144fdb40bf2ab36a9abb197fb18bd9e8672004e54ee5e82026ab829aff037c`;
- consolidated measurement log: 3,157 bytes, SHA-256
  `6f735d18c315cd746bd10a3d940ca8ec52c032ec96658fea7a18bd9c5c22483f`;
  and
- routing selector: 67 passed in 1.48 seconds; and
- corrected broad non-security gate: 9,868 passed, 19 skipped, 5 warnings in
  147.90 seconds; log SHA-256
  `76308a56635e67d21a84f1254b812e41d4eebde7dc2444fe9cb6dd31a1e7c637`.

The first broad candidate passed 9,867 tests with 19 skipped and 5 warnings but
failed
`tests/test_workflow_lisp_judgment_views_e2e.py::test_panel_missing_bound_evidence_changes_only_affected_view`
because Task 3 had removed the historical completed-state terminal sweep when
no restart node existed (log SHA-256
`dab15bbc475e88470060dc0234c099361d777b2c9117808633bdd19c9fb990f3`).
The exact generic correction `ce02cd17` distinguishes completed-state
revalidation from running post-body epilogue-only resume, preserves exact
completed phased reuse, and passed its ordered correction reviews, 160
affected-module tests, the 591-test Task 3 matrix, and the post-correction
694-test Task 4 matrix (log SHA-256
`f374f391c96e6b1535bd212ac707cf77feae6f44fa630dfb4664c5b6e54b1336`).

Ordered final review passed `M2_FEASIBILITY_FINAL_SPEC_APPROVED` then
`M2_FEASIBILITY_FINAL_QUALITY_APPROVED` against the same closure bytes.

**Files:**

- Modify: `docs/design/workflow_lisp_pure_result_replay.md`
- Modify: `docs/design/workflow_lisp_lexical_execution_checkpoints.md`
- Modify: `docs/design/workflow_lisp_state_layout.md`
- Modify: `docs/design/README.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/index.md`
- Modify: `docs/plans/2026-07-26-substrate-maintenance-track.md`
- Modify: `specs/state.md`
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`
- Modify: this plan
- Do not modify E- or P-series owner routing

- [x] Run collection for every new or renamed test module:

  ```bash
  pytest --collect-only -q tests/test_workflow_lisp_pure_result_replay.py
  ```

- [x] In tmux, run the full M2 feasibility matrix with the repository-required
  broad/slow parallelism:

  ```bash
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
    tests/test_observability_report.py
  ```

- [x] Record fresh proof that:
  serialized executable/runtime-plan digests are unchanged; clean and resumed
  artifacts/diagnostics/settlement match; E1 executes once; A/B values are
  absent from durable replay-profile state and sidecars; all profile and
  witness negatives fail before mutation/effect dispatch; and historical
  behavior remains compatible.
- [x] Compare the replay-profile fixture with Task 1's historical control.
  Record exact durable value counts and state/sidecar bytes. Both must strictly
  decrease. Record production and test source line changes honestly:

  ```bash
  git diff --numstat <task-0-commit>...HEAD -- \
    orchestrator tests
  ```

- [x] Run roadmap/routing verification:

  ```bash
  pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py
  ```

- [x] Run one ordinary Workflow Lisp compiler/runtime smoke check in addition
  to the unit modules, using the checked-in fixture through its public
  historical-profile route. This smoke must not activate the replay profile in
  CLI-created state.

- [ ] If any stop/revise criterion in the design is met, leave the design
  proposed, prepare a separate truthful revision candidate recording the exact
  failed criterion and evidence, and do not select M3a. Route that candidate
  through ordered review before committing it.
- [x] If every executable criterion passes, prepare the complete closure
  candidate before review. It must:
  mark the design accepted; specify the additive profile and exact shell in
  `specs/state.md`; update the lexical-checkpoint pure policy; distinguish
  retained compiled path carriage from new runtime writes in the state-layout
  design; update the capability matrix; mark M2 complete with exact task
  commits, measurements, and verification counts; make only M3a eligible while
  leaving it unselected pending its own plan; and update substrate/index/design
  routing and routing tests without touching E/P.
- [x] Re-run `git diff --check`, the complete focused matrix, and the routing
  selector against those complete closure bytes.
- [x] In tmux, run the repository-standard broad non-security suite against
  the complete closure candidate:

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
- [ ] Request `M2_FEASIBILITY_FINAL_SPEC_APPROVED` followed by
  `M2_FEASIBILITY_FINAL_QUALITY_APPROVED`. Bind both reviews to the same
  baseline, task commits, complete closure diff and file hashes, fresh
  test-log hashes, parity measurements, and reduction measurements. Replay
  only after a material finding.
- [ ] After both reviews approve, commit the exact reviewed closure bytes
  unchanged with subject `Prove pure result replay feasibility`.
- [ ] Run a non-mutating postcommit selector against the exact closure tree and
  bind it in an external closure record rather than a checked-in
  self-attestation.
- [ ] Immediately draft and route the separate M3a activation plan. It must
  activate the profile for new Workflow Lisp roots and fresh non-iterative
  call frames, add positive nested-frame coverage, make only activation-
  specific normative/capability adjustments, and retain every feasibility
  invariant. Do not begin M3a implementation until that plan receives ordered
  specification then quality approval.

## Acceptance summary

M2 component (a) completes only when all of the following are simultaneously
true:

- the fixture uses the real compiler, generic state initialization, fresh
  execution, durable interruption, state reload, and ordinary new-executor
  resume;
- every eligible successful pure value is transient and its durable row is the
  exact closed shell;
- no eligible pure value survives in a bundle, private lineage, checkpoint, or
  restore payload;
- replay reconstructs only the required dependency closure and never repeats
  E1;
- the interrupted-pure visit settles without a second increment;
- checkpoint filtering and validated frame entry pass both directions without
  weakening invalid-nearest failure;
- root/nested profile conflicts fail before mutation or effect dispatch;
- loops/recur and historical state preserve their durable behavior;
- public outputs, diagnostics, and settlement match the historical control;
- durable value count and state/sidecar bytes both strictly decrease;
- narrow, routing, and broad non-security gates pass; and
- ordered closure reviews accept the resulting design.

Passing this plan does not itself activate the profile in ordinary CLI-created
runs. That is the first responsibility of the separately reviewed M3a plan.
