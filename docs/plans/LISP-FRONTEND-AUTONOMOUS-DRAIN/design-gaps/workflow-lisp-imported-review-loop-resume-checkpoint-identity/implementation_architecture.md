# Workflow Lisp Imported Review-Loop Resume Checkpoint Identity Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-imported-review-loop-resume-checkpoint-identity`
Target design: `docs/design/workflow_lisp_key_migration_parity_architecture.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected prerequisite gap:

- make imported stdlib `review-revise-loop` persist its `repeat_until` frame
  under one stable identity shared by the lowered authored mapping,
  `WorkflowStateProjection`, runtime-plan checkpoints, persisted `state.json`,
  and resume lookup;
- ensure the typed repeat-until executor reuses the projection-owned frame key
  for loop-frame persistence instead of re-deriving state keys from ad hoc
  generated names or nested specialization details;
- preserve the existing imported stdlib specialization route and nested
  iteration-owned call-boundary checkpoint metadata while proving that a
  forced `REVISE` interruption resumes through the same loop frame;
- refresh the focused imported review-loop resume proof so it exercises the
  current runtime-owned hidden write-root policy and the selected checkpoint
  contract together.

Out of scope for this slice:

- redesign of `review-revise-loop` specialization, findings validation,
  `resume-or-start`, reusable-state sidecars, workflow input defaults, or the
  family-level `design_plan_impl_stack` parity rewrite;
- changes to command bundle-path ownership, `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`,
  managed write-root policy, command-adapter certification, or runtime-native
  effects beyond consuming the already-selected contracts;
- new authored Workflow Lisp syntax, new stdlib result schemas, report
  parsing, pointer-authority exceptions, or hidden shell/Python glue;
- a general runtime state-key redesign for every structured control form.

This is a bounded implementation architecture for one selected prerequisite
gap. It does not replace the parent migration architecture or reopen the full
Workflow Lisp frontend contract.

## Problem Statement

The selected migration architecture requires one stable imported review-loop
checkpoint identity across specialization, persisted runtime state, and resume
lookup. The required proof is narrower than generic loop support:

- the imported stdlib route already compiles to one top-level `repeat_until`
  frame;
- the runtime plan already exposes a `repeat_until_frame` checkpoint for that
  frame;
- the remaining prerequisite is durable execution-state continuity under the
  authored/generated loop presentation key after an interruption.

Current checkout evidence shows two distinct facts that must both shape the
implementation:

1. Compile-time metadata is already close to correct.
   The focused compile proof
   `tests/test_workflow_lisp_key_migrations.py::test_review_loop_parity_fixture_compiles_to_resume_safe_repeat_until_via_imported_stdlib_route`
   proves that the imported fixture lowers to a top-level loop named
   `rl_rl18_5_h_1__loop`, emits a `repeat_until_frame` runtime-plan checkpoint
   whose `presentation_key` equals that authored step name, and records a
   `WorkflowStateProjection.repeat_until_nodes["root.rl_rl18_5_h_1__loop"]`
   entry with the same frame key plus iteration-owned nested call-boundary
   metadata.
2. The execution proof is currently blocked before it can validate that
   checkpoint contract.
   The focused runtime proof
   `tests/test_workflow_lisp_key_migrations.py::test_review_loop_imported_stdlib_route_resumes_after_revise_checkpoint`
   still manually binds runtime-owned `__write_root__*` inputs. Under the
   already-selected compiler-owned bundle-path policy, that causes a
   pre-execution `managed_write_root_override` failure, no provider calls, and
   an empty persisted `repeat_until` map. The older recovery notes captured the
   downstream symptom as `KeyError: 'rl_rl18_5_h_1__loop'`, but the current
   checkout shows that the proof fixture must first stop violating the reused
   hidden-input contract before the checkpoint identity can be exercised.

The architectural gap is therefore not "invent a new loop id." It is:

- promote the existing projection/runtime-plan frame identity into the only
  persistence and resume authority for typed imported review loops; and
- update the focused proof so it reaches the loop and asserts that state is
  written and resumed under that same authority.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
  - `Newly Exposed Prerequisite Gaps`
  - `Required Generic .orc Support`
  - `Compiler And Lowering Layer`
  - `Dependencies And Sequencing`
  - `Evidence And Implementation Boundaries`
  - `Verification Strategy`
  - `Success Criteria`
- `docs/design/workflow_lisp_frontend_specification.md`
  - Sections 13, 14, 16, 27, 45-48, 53, 57-59, 63-66, 74, 95, 103-104
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/lisp_frontend_review_fix_loops.md`
- `specs/dsl.md`
  - structured `repeat_until`
  - `call`
  - workflow inputs
- `specs/state.md`
  - `steps`
  - `repeat_until`
  - `call_frames`
  - `current_step.step_id`
  - presentation key versus durable `step_id`
- `docs/plans/2026-06-01-review-revise-loop-stdlib-feasibility-proof.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/4/recovered-gap/work-item/blocked-implementation-recovery.json`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/5/blocked-recovery-decision.json`
- `docs/steering.md`

The slice must preserve these guardrails:

- keep imported review loops on the generic stdlib route; do not add a
  family-specific or literal-name compiler branch;
- keep runtime execution/state authority under `orchestrator/workflow/` and
  frontend lowering/specialization ownership under `orchestrator/workflow_lisp/`;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- keep the current runtime-owned hidden write-root policy intact; this slice
  must not relax override rejection to make the proof pass;
- reuse the existing `WorkflowStateProjection`, runtime-plan checkpoint, and
  call-boundary machinery rather than inventing a second loop-state identity
  system;
- keep any command-backed review-findings validation or reusable helper under
  the existing command-adapter contract; this slice must not add hidden
  scripts or adapter bypasses;
- do not treat the empty `docs/steering.md` file as permission to widen scope.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The full autonomous-drain index in
`state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/6/design-gap-architect/existing-architecture-index.md`
was reviewed for coherence. The directly reused slices for this gap are:

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/executable-ir-runtime-plan/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/loop-recur-bounded-loops/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-promoted-entry-hidden-reusable-call-binding/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-review-loop-generic-effectful-composition/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-review-loop-report-findings-path-split/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-command-result-compiler-owned-bundle-paths/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-design-plan-impl-stack-review-loop-parity/implementation_architecture.md`

### Decisions Reused

- Reuse the imported stdlib `review-revise-loop` specialization route and its
  generated top-level loop surface; this slice does not redesign how the loop
  is authored or lowered.
- Reuse the structured loop runtime substrate from the bounded-loops slice:
  typed loop bodies lower through one shared `repeat_until` frame plus stable
  nested body node ids.
- Reuse the shared runtime-plan and projection model:
  `RuntimeResumeCheckpoint`,
  `WorkflowStateProjection`,
  `IterationStepKeyProjection`,
  `presentation_key_by_node_id`,
  and iteration-owned call-boundary checkpoint metadata remain the only
  compatibility/resume surfaces.
- Reuse the source-map/runtime-lineage rule that generated executable nodes and
  generated control-flow scaffolding must remain explainable through one shared
  provenance channel.
- Reuse the compiler-owned hidden write-root contract from the bundle-path
  slice; runtime-owned hidden inputs remain off the public API and user
  overrides remain invalid.
- Reuse the promoted-entry hidden-binding slice's rule that runtime-owned
  internal inputs and compiled workflow/public input helpers are proof
  preconditions, not optional conveniences.

### New Decisions In This Slice

- The persisted identity for a typed imported review-loop frame is the
  projection-owned frame presentation key for the `repeat_until` node, not a
  node id, not a manually re-derived generated name, and not a nested call
  boundary alias.
- Typed `repeat_until` execution must obtain that frame key from
  `WorkflowStateProjection` / `IterationStepKeyProjection` when executable-IR
  loop metadata exists, then use it consistently for:
  - `state.steps[<frame key>]`
  - `state.repeat_until[<frame key>]`
  - iteration child presentation prefixes
  - restart bookkeeping after interruption
- If executable-IR typed loop metadata is present but its frame key cannot be
  resolved, execution should fail with an integrity-style runtime error rather
  than silently falling back to an ad hoc key and corrupting resume state.
- The focused imported review-loop resume proof must stop binding
  runtime-owned `__write_root__*` inputs manually and instead rely on the
  runtime-owned binding route already selected elsewhere. The checkpoint
  identity proof begins only after that precondition is met.

### Conflicts Or Revisions

The blocked recovery artifacts at
`state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/4/...` and iteration 5
accurately identified the missing prerequisite as absent imported review-loop
resume state under `rl_rl18_5_h_1__loop`. The current checkout introduces one
additional constraint after those artifacts were written:

- the runtime-owned managed write-root policy now rejects the focused proof's
  manual `__write_root__*` bindings before the loop executes.

This slice does not revise the selected prerequisite. It narrows the proof
route:

- keep the runtime-owned hidden-input policy unchanged;
- update the focused resume fixture so it reaches the loop under the current
  policy;
- then fix the selected checkpoint-identity contract on that real execution
  path.

No shared concepts are redefined. Core Workflow AST, Semantic IR, TypeCatalog,
SourceMap, pointer authority, variant proof, command-step semantics, and the
review-loop author-facing specialization surface remain with their existing
owners.

## Ownership Boundaries

This slice owns:

- runtime persistence-key selection for typed `repeat_until` frames in
  `orchestrator/workflow/loops.py`;
- any narrow projection helper needed so typed loop execution and resume can
  resolve the canonical frame presentation key from shared projection data;
- any narrow executor/resume glue needed to treat missing typed-loop frame
  projection as a runtime integrity failure instead of silently drifting;
- focused imported-review-loop runtime fixtures and resume regressions;
- checkpoint-identity assertions that prove the imported stdlib loop writes and
  resumes under the expected authored/generated presentation key.

This slice intentionally does not own:

- imported stdlib review-loop specialization, result contracts, findings-path
  seeding, or `ProcRef` hook expansion;
- command bundle-path policy, runtime-owned write-root allocation, or hidden
  input/public input classification;
- reusable-state validation, `resume-or-start`, or promoted-entry context
  bootstrap;
- shared runtime-plan checkpoint schema redesign beyond consuming the existing
  fields;
- new adapters, new scripts, report parsing, or pointer-authority behavior.

## Current Checkout Facts

The current checkout already provides most of the identity substrate this slice
should reuse:

- `tests/test_workflow_lisp_key_migrations.py::test_review_loop_parity_fixture_compiles_to_resume_safe_repeat_until_via_imported_stdlib_route`
  proves the imported fixture lowers to one top-level loop step named
  `rl_rl18_5_h_1__loop`.
- The same compile proof asserts the validated bundle exposes a
  `repeat_until_frame` checkpoint whose `presentation_key` equals that loop
  step name.
- Inspection of the compiled bundle shows:
  - `RuntimeResumeCheckpoint(node_id="root.rl_rl18_5_h_1__loop", presentation_key="rl_rl18_5_h_1__loop")`
  - `WorkflowStateProjection.repeat_until_nodes["root.rl_rl18_5_h_1__loop"].frame_key == "rl_rl18_5_h_1__loop"`
  - iteration-owned call-boundary checkpoints for the generated review and fix
    wrapper calls already point back to `iteration_owner_node_id =
    "root.rl_rl18_5_h_1__loop"`.
- `orchestrator/workflow/loops.py` currently persists `repeat_until` progress
  by `step_name = step.get("name", ...)` and only uses typed-loop projection
  metadata for nested iteration step ids and nested presentation keys. The
  frame-key contract is therefore implicit rather than explicit.
- `orchestrator/workflow/resume_planner.py` already treats the top-level
  projection presentation key as the authoritative lookup key for both
  `steps[...]` and `repeat_until[...]`.
- Running the focused imported review-loop resume test in the current checkout
  fails before any provider call with a runtime-owned input violation:
  `error.context.reason == "managed_write_root_override"`.
  The persisted state then contains:
  - `steps == {}`
  - `repeat_until == {}`
  - no call frames
- The blocked recovery notes remain relevant because once the proof reaches the
  loop, it still must observe persisted `repeat_until["rl_rl18_5_h_1__loop"]`
  and resume through that same key rather than failing with a missing-key
  symptom.

This makes the slice feasible without reopening lowering or runtime-plan
generation. The missing work is to make execution/resume consume the already
generated frame identity explicitly and to align the focused proof with the
current hidden-input policy.

## Proposed Architecture

### 1. Promote The Projection Frame Key To The Persistence Authority

Typed imported review loops already have two identities at execution time:

- durable executable node id, such as `root.rl_rl18_5_h_1__loop`;
- compatibility presentation key, such as `rl_rl18_5_h_1__loop`.

For persisted state, the compatibility key remains authoritative because
`specs/state.md` requires `steps.<PresentationKey>` and
`repeat_until.<RepeatUntilStatement>` storage. This slice makes that explicit:

- when `LoopExecutor` can resolve typed-loop metadata, it must obtain the loop
  frame key from the shared projection, not from string reconstruction;
- `IterationStepKeyProjection.frame_key` is the canonical persisted key for the
  loop frame;
- the top-level projection entry and the loop projection must agree on that
  value.

Implementation consequence:

- add one narrow helper on the shared projection side or inside
  `LoopExecutor` that returns:
  - loop node id
  - frame presentation key
  - typed body node ids
  - `IterationStepKeyProjection`
- if any of those pieces disagree for a typed loop, execution fails with an
  integrity-style runtime error instead of falling back to `step["name"]`.

Untyped or legacy loop execution may keep the existing `step["name"]` fallback.
The new rule applies only when executable-IR typed loop metadata exists.

### 2. Use The Same Frame Key For Every Typed Repeat-Until Persistence Surface

Once the typed frame key is resolved, every loop-frame persistence write should
reuse it consistently:

- `state.steps[frame_key]` stores the loop-frame result snapshot;
- `state.repeat_until[frame_key]` stores loop bookkeeping;
- `state.steps[f"{frame_key}[i].<nested>"]` remains the per-iteration nested
  presentation-key namespace already implied by the current projection;
- restart and resume helpers look up loop progress by the same `frame_key`.

This is intentionally narrower than a general state-schema rewrite. The state
format remains exactly the one already defined in `specs/state.md`. The change
is that typed loop execution no longer treats the persisted key as an informal
copy of the authored step name.

### 3. Keep Node Ids As Durable Resume Lineage, But Do Not Persist Them As Loop Keys

The durable lineage identity for the loop frame remains the runtime-plan node
id and step id:

- node id: `root.rl_rl18_5_h_1__loop`
- step id: `root.rl_rl18_5_h_1__loop`
- presentation key: `rl_rl18_5_h_1__loop`

This slice keeps that split:

- runtime-plan checkpoints and nested call-boundary ownership continue to use
  node ids and step ids;
- persisted state maps continue to use presentation keys;
- the executor/resume bridge becomes explicit about translating from durable
  node identity to persisted presentation-key identity through shared
  projection metadata.

That preserves the existing schema contract while removing the remaining
ambiguity for imported specialized loops.

### 4. Refresh The Focused Imported Review-Loop Proof To Reach The Real Gap

The targeted resume proof must be updated to consume the current runtime-owned
write-root policy before it can prove checkpoint identity:

- stop manually binding runtime-owned `__write_root__*` inputs in
  `test_review_loop_imported_stdlib_route_resumes_after_revise_checkpoint`;
- keep the existing explicit proof that such overrides are rejected elsewhere;
  this slice does not remove that guard;
- assert that the first run actually enters the imported review loop:
  at minimum, one review invocation should occur before the forced
  interruption;
- after the forced `REVISE` interruption, assert persisted state contains:
  - `repeat_until[repeat_step["name"]]["current_iteration"] == 1`
  - `completed_iterations == [0]`
  - a loop-frame result stored at `steps[repeat_step["name"]]`
- resume the same run and assert completion succeeds without `KeyError` or
  other projection-integrity failures.

This keeps the test focused on the selected prerequisite instead of conflating
it with the reused runtime-owned input contract.

### 5. Add One Narrow Regression Around Imported Loop Identity Drift

The imported review-loop path is more fragile than plain YAML loops because it
mixes:

- imported stdlib expansion;
- generated helper wrappers;
- iteration-owned call boundaries;
- typed repeat-until projection.

Add one narrow regression that proves the shared identity chain remains stable:

- compile proof:
  imported review-loop bundle still emits
  `repeat_until_frame.presentation_key == repeat_step["name"]`
  and call-boundary checkpoints remain owned by `root.<loop-node-id>`;
- runtime proof:
  interruption after a `REVISE` iteration persists state under that same
  `repeat_step["name"]`;
- resume proof:
  restart lookup re-enters the correct top-level loop frame and continues
  without replaying completed iteration-0 work.

This slice does not need a broader family workflow test. The selected
prerequisite is satisfied once the shared imported stdlib review-loop fixture
proves this behavior.

## Proposed Code Footprint

- `orchestrator/workflow/loops.py`
- `orchestrator/workflow/state_projection.py`
- `orchestrator/workflow/resume_planner.py`
- `tests/test_workflow_lisp_key_migrations.py`
- `tests/test_resume_command.py`
- `tests/test_workflow_state_projection.py`
- `tests/test_workflow_lowering_invariants.py`

Shared components intentionally reused, not owned here:

- `orchestrator/workflow/runtime_plan.py`
- `orchestrator/workflow/lowering.py`
- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/state.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`

## Acceptance Conditions

- the imported review-loop compile proof still emits one top-level
  `repeat_until_frame` checkpoint whose `presentation_key` equals the lowered
  authored loop step name;
- typed repeat-until execution resolves and persists the loop frame through the
  projection-owned frame key when typed loop metadata exists;
- the focused imported review-loop resume proof no longer binds runtime-owned
  hidden write roots manually and reaches the forced `REVISE` interruption;
- after that interruption, persisted state contains loop-frame progress under
  `repeat_until[repeat_step["name"]]` and the loop-frame result under
  `steps[repeat_step["name"]]`;
- resuming the run completes successfully and reuses the same imported loop
  frame identity instead of failing with a missing-key or alias drift error;
- existing runtime-owned write-root override rejection remains intact;
- no new author-facing syntax, new adapter surface, or family-specific
  review-loop workaround is introduced.

## Verification Strategy

Run the deterministic checks listed in:

`state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/6/design-gap-architect/check_commands.json`

They should cover:

- collect-only over the focused migration, resume, projection, and lowering
  invariant modules;
- compile-time proof that the imported review-loop fixture still lowers to a
  resume-safe `repeat_until` frame with the expected checkpoint metadata;
- projection/runtime-plan coverage for repeat-until frame keys and
  iteration-owned call-boundary checkpoint ids;
- the focused imported review-loop interruption/resume proof that persists and
  reloads state under the stable loop frame key.
