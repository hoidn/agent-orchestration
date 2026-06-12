# Workflow Lisp Lexical Checkpoint Resumability

Status: draft future target design
Kind: architecture decision / runtime target
Created: 2026-06-12
Scope: Workflow Lisp execution resume based on lexical execution checkpoints,
continuation identity, typed value snapshots, effect-boundary replay, and the
separation of execution resumability from workflow-domain resource state.

Authority:

- Normative runtime and DSL behavior remains in `specs/`.
- `docs/design/workflow_lisp_frontend_specification.md` remains the
  authoritative Workflow Lisp language baseline.
- `docs/design/workflow_lisp_core_calculus_middle_end.md` owns WCC, ANF,
  second-class join points, effect rows, proof scopes, and current
  defunctionalization into the flat validated runtime model.
- `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`
  owns the near-term generic runtime core target: `RunCtx`,
  `Resource<TState>`, `Transition<TRequest, TResult>`, pure projection,
  materialized views, and adapter retirement.
- `docs/design/workflow_lisp_state_layout.md` owns generated path and
  allocation identity. This document consumes that identity model for
  checkpoint storage and value-bundle references.
- `docs/design/workflow_lisp_semantic_workflow_ir.md` and
  `docs/design/workflow_lisp_executable_ir.md` own current semantic and
  executable authority surfaces. This document proposes a future executable
  runtime target; it does not change the current checkout contract.
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  owns parent-callable migration evidence and promotion policy. This document
  supplies a possible later simplification target for resume mechanics after
  WCC and the generic core are established.

Related docs:

- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_core_calculus_middle_end.md`
- `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`
- `docs/design/workflow_lisp_runtime_migration_foundation.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_semantic_workflow_ir.md`
- `docs/design/workflow_lisp_executable_ir.md`
- `docs/design/workflow_language_design_principles.md`
- `specs/state.md`
- `specs/dsl.md`

## 1. Purpose

The current migration direction correctly moves durable workflow-domain updates
out of opaque files and Python adapters into typed resources and transitions.
That is the right model for semantic domain state: backlog item status, drain
terminal records, recovery ledgers, transition audit, and parity-comparable
business outcomes.

It is not necessarily the best long-term model for execution resumability.
Resuming "where the workflow was" should not require every workflow author to
model execution position as a domain resource, pass pointer paths through `.orc`
calls, or encode control-flow progress into queue/status files. The runtime can
often resume execution by restoring the workflow's lexical execution state:
current continuation, lexical bindings, loop frame, variant proof scope, and
completed effect results.

This document defines a future target in which:

```text
execution progress is resumed from lexical checkpoints;
workflow-domain durability is expressed with typed resources and transitions;
materialized files remain views or external-effect payloads;
public `.orc` boundaries do not expose checkpoint, pointer, or generated path mechanics.
```

The goal is to reduce long-term `.orc` resource-management burden without
weakening typed effects, validation-before-commit, source-map provenance, or
promotion evidence.

## 2. Executive Decision

Adopt lexical checkpoints as the long-term execution-resume substrate for
Workflow Lisp, after WCC/schema 2 and the generic core have proven the typed
composition route on real workflow families.

The target runtime stores checkpoints at effect boundaries and safe control
boundaries:

```text
Checkpoint =
  run identity
  workflow/procedure identity
  lowering schema and executable schema
  current continuation / join-point identity
  lexical environment bindings
  loop/call frame stack
  active variant proof scopes
  completed effect result references
  pending effect boundary, if any
  StateLayout allocation namespace
  source-map / Semantic IR bridge identity
```

On resume, the runtime reconstructs the executable lexical state and continues
from the next uncommitted effect boundary. Resource transitions remain the
durable semantic mutation mechanism; lexical checkpoints do not replace
resources, transition audit, or idempotency.

This design intentionally chooses a hybrid model:

```text
lexical checkpointing for execution progress;
typed transitions for domain state mutation;
materialized views for reports, prompts, and compatibility files;
certified commands/adapters only for external effects.
```

## 3. Problem

The current flat-runtime migration path can make resume mechanically correct
but authoring-heavy. Because the runtime resumes by step identity, generated
paths, bundles, and resource-transition records become visible pressure points.
That pressure shows up in `.orc` code as explicit `run_state_path`,
`item_summary_target_path`, `item_summary_pointer_path`, selection-bundle paths,
summary targets, and compatibility state files.

Some of those paths represent real external artifacts. Many are merely
execution transport or compatibility views. When they are passed through high
level `.orc` call sites, the workflow starts to look like it is manually
operating the runtime rather than describing the workflow.

Three distinct concerns are currently entangled:

| Concern | Proper owner | Current failure mode |
| --- | --- | --- |
| Execution progress | Runtime checkpoint/resume layer | Authored workflow state or generated path plumbing carries "where we are" |
| Domain state | Typed resources and transitions | File updates and adapters hide semantic mutation |
| Human/external representation | Materialized views and command artifacts | Pointer/report paths become mistaken for semantic authority |

The generic resource core addresses the second concern. This design addresses
the first.

## 4. Goals

- Make ordinary Workflow Lisp execution resumable by restoring lexical
  execution state rather than by requiring workflow authors to model execution
  position as domain state.
- Preserve WCC as the compiler representation that supplies continuation,
  scope, effect, proof, and environment identity.
- Preserve validation-before-commit: a resumed run must continue only from a
  validated executable/checkpoint pair whose schemas and digests match.
- Keep resource transitions for semantic durable mutation, including version
  checks, idempotency, conflict policy, audit, and parity evidence.
- Make checkpoint storage private runtime state allocated through
  `StateLayout`, never public authored workflow inputs.
- Keep source maps, Semantic IR, and executable IR able to explain where a
  resumed value, continuation, effect result, and generated allocation came
  from.
- Make replay behavior explicit at effect boundaries: pure computation may be
  recomputed, completed idempotent effects may be reused, and non-idempotent
  pending effects must be failed closed or resumed through a declared protocol.
- Reduce long-term `.orc` resource-management noise for parent workflows such
  as Design Delta Drain.

## 5. Non-Goals

- Do not make resources obsolete. Resources remain the model for durable
  workflow-domain state.
- Do not add first-class runtime closures or user-visible continuation values.
  Checkpoint continuations are runtime/internal executable state.
- Do not make WCC metadata public workflow values.
- Do not adopt Temporal-style unconstrained history replay where arbitrary user
  code is replayed until it happens to reach the previous state.
- Do not allow effect replay to duplicate provider calls, command writes,
  resource transitions, artifact publication, or external side effects.
- Do not treat materialized views, pointer files, reports, or debug YAML as
  resume authority.
- Do not change the current flat executable runtime as part of this document.
  This is a future target after the WCC and generic-core paths have sufficient
  evidence.

## 6. Target Model

### 6.1 Execution state vs domain state

Execution state answers:

```text
Where is this run in the executable program?
Which lexical values are available?
Which branch proof is active?
Which loop/call frame are we in?
Which effects have already committed?
```

Domain state answers:

```text
What is the backlog item state?
What terminal status was recorded?
Which recovery route was accepted?
Which audit record proves a transition occurred?
```

Lexical checkpoints own execution state. Resources and transitions own domain
state. A workflow may use both, but it should not need to create domain
resources merely to remember local control-flow position.

### 6.2 Checkpoint record

A checkpoint record is private runtime state. It should include at least:

```text
checkpoint_id
run_id
workflow_id
procedure_or_call_identity
lowering_schema_version
executable_ir_schema_version
executable_digest
checkpoint_schema_version
continuation_id
join_point_id, when applicable
program_counter / executable node id
call_frame_stack
loop_frame_stack
lexical_environment
active_variant_proofs
effect_commit_log_refs
pending_effect_boundary
state_layout_namespace
source_map_bridge_refs
created_at / updated_at as evidence, not semantic identity
```

The lexical environment contains typed values or references to typed bundles.
Large provider/command/workflow outputs should be stored by validated bundle
reference, not duplicated inline in every checkpoint.

### 6.3 Continuation identity

Continuation identity is derived from WCC and executable lowering metadata:

```text
module/procedure identity
specialization identity
join-point identity
scope identity
call-frame identity
loop-frame identity
lowering schema version
semantic owner chain
```

Formatting-only source edits must not change checkpoint identity. Semantic edits
that change control shape, binding ownership, type shape, effect order, or
continuation ownership must change the digest or schema in a way that fails
closed on resume unless an explicit migration exists.

### 6.4 Lexical environment

A checkpointed lexical environment contains only runtime-safe values:

- scalar values;
- typed records and unions whose schemas are available in the executable
  bundle;
- optional/list/map values when supported by the type catalog and value
  transport;
- variant proof tokens scoped to their producing value and continuation;
- references to validated provider/command/workflow result bundles;
- references to materialized views as views, not semantic authority;
- references to resources and resource versions as handles, not copied domain
  state.

It must not contain:

- unresolved `ProcRef`, provider ref, prompt ref, type parameter, or macro
  object;
- raw Python objects;
- runtime closures or user-visible continuation values;
- arbitrary file handles or process handles;
- unvalidated pointer/report paths as semantic values.

### 6.5 Effect boundary protocol

Checkpoints are written before and after effectful operations. Each effect class
must declare resume behavior.

| Effect class | Resume behavior |
| --- | --- |
| Pure projection | Recompute or reuse deterministic bundle if payload digest matches |
| Provider call | Reuse validated structured output if committed; otherwise rerun only if provider policy allows |
| Command / external adapter | Reuse validated structured output if committed; pending non-idempotent calls fail closed unless declared resumable |
| Workflow call | Resume child run/checkpoint if active; reuse typed child result if committed |
| Resource transition | Reuse idempotency/audit result if committed; otherwise execute through transition protocol |
| Materialized view | Recompute from typed value or reuse byte-identical validated view |
| Artifact publication | Reuse committed artifact identity; pending publication fails closed or runs declared atomic publish recovery |

No resume path may silently rerun a non-idempotent external effect.

### 6.6 Relationship to `resume-or-start`

`resume-or-start` remains a typed reusable-state surface for semantic reuse of
prior workflow results. Lexical checkpoints are a lower-level execution
mechanism.

```text
lexical checkpoint:
  resume this run's executable state

resume-or-start:
  decide whether a prior semantic result is reusable for this workflow contract
```

A run may first try lexical checkpoint resume. If checkpoint resume is
incompatible or unavailable, the workflow may still use `resume-or-start` to
reuse previous semantic outputs according to its typed contract.

## 7. Architecture Invariants

- Checkpoints are private runtime state.
- Checkpoints are validated before use.
- Checkpoint schema, executable IR schema, lowering schema, and executable
  digest are part of resume compatibility.
- Pure lexical values may be restored; effectful work is restored only through
  committed effect evidence or declared effect-specific resume protocols.
- Resources remain the semantic mutation authority; checkpoints do not replace
  transition audit or resource versions.
- A checkpoint cannot make an invalid workflow valid. Shared validation and
  executable validation still precede execution.
- Variant proof tokens remain scoped and cannot be used outside the restored
  continuation where they are valid.
- Checkpoint paths and bundle paths are allocated by `StateLayout` and are
  never public authored inputs.
- Source maps and Semantic IR must explain restored continuations and bindings
  well enough for parity and debugging.
- Historical runs resume under their recorded execution/checkpoint schema or
  fail closed with a typed diagnostic.

## 8. Design Details

### 8.1 Runtime-owned checkpoint store

The runtime owns a checkpoint store behind an interface such as:

```text
load_latest_checkpoint(run_id, executable_digest) -> Checkpoint | None
write_checkpoint(run_id, checkpoint) -> CheckpointRef
commit_effect_result(checkpoint_ref, effect_result) -> CheckpointRef
mark_checkpoint_terminal(run_id, terminal_result_ref) -> None
```

The first implementation may be file-backed under `.orchestrate/`, but the
contract must not require a file-backed store. `StateLayout` owns the generated
checkpoint path role and path-safety rules.

### 8.2 Executable frame model

The executable runtime must carry enough structured frame state to restore:

```text
WorkflowFrame
ProcedureFrame
CallFrame
LoopFrame
JoinFrame
MatchArmFrame
EffectFrame
```

These are internal runtime frame records. They are not authored `.orc` values.

### 8.3 Checkpoint write placement

Required checkpoint points:

- at workflow entry after public/private boundary binding;
- before each non-pure effect boundary;
- after each committed effect result is validated and recorded;
- at loop iteration entry and after loop state update;
- at workflow/procedure-call entry and return;
- before terminal output publication;
- after terminal result commit.

Optional checkpoint points:

- after large pure projection outputs;
- after expensive deterministic materialized views;
- after long pure loops if such loops are ever admitted by the language.

### 8.4 Resume algorithm

On `orchestrator resume <run_id>`:

1. Load run metadata and the latest checkpoint candidate.
2. Validate checkpoint schema, executable schema, lowering schema, executable
   digest, type catalog digest, and source-map bridge compatibility.
3. Reconstruct runtime frames and lexical environment.
4. Revalidate referenced typed bundles, resource handles, materialized views,
   and effect commit records.
5. If the checkpoint is before a pending effect, apply the effect-specific
   resume protocol.
6. Continue execution from the restored continuation.
7. Write a new checkpoint before the next effect boundary.

If any compatibility check fails, resume must fail closed with a typed
diagnostic. It may then offer a separate semantic `resume-or-start` path only if
the workflow contract declares one.

### 8.5 Interaction with resources

Resource transitions remain explicit where domain state must be durable,
auditable, or parity-comparable.

Good resource uses:

- recording backlog item terminal outcome;
- recording drain terminal status;
- moving a recovery attempt through typed states;
- versioning a semantic work item;
- appending transition audit.

Bad resource uses after lexical checkpoints exist:

- storing "currently in branch X" solely for execution resume;
- storing loop counters solely so the runtime can continue the loop;
- passing pointer paths solely to let a child call find internal runtime state;
- materializing private generated bundle paths as public state.

### 8.6 Interaction with materialized views

Materialized views are outputs of typed values, not checkpoint authority. A
checkpoint may reference a materialized view for efficient reuse, but resume
must be able to validate the view against its typed producer or regenerate it.

### 8.7 Source maps and Semantic IR

Semantic IR should gain checkpoint bridge entries that explain:

```text
checkpoint identity
continuation / executable node identity
lexical binding identities
frame stack identities
effect commit refs
StateLayout checkpoint allocation
source spans for restored bindings and continuation owners
```

This is explanatory and evidentiary. The executable checkpoint remains runtime
state; Semantic IR does not become the resume engine.

## 9. Contracts And Interfaces

### 9.1 Frontend / WCC

The frontend must emit stable identity for:

- WCC join points;
- lexical scopes and environment bindings;
- call frames and loop frames;
- branch/proof scopes;
- effect boundaries;
- typed result schemas;
- source-map bridge owners.

These identities already exist in partial form for WCC defunctionalization and
StateLayout. This design requires them to be stable enough for runtime
checkpoint compatibility.

### 9.2 Executable IR

Executable IR must describe resumable nodes and frame shapes without exposing
WCC internals as public values. A future schema may add:

```text
checkpoint_schema_version
continuation_table
frame_descriptor_table
lexical_binding_descriptor_table
effect_resume_policy_table
```

### 9.3 Runtime

The runtime owns:

- checkpoint persistence;
- checkpoint validation;
- lexical environment restoration;
- effect-boundary replay/reuse decisions;
- fail-closed diagnostics;
- interaction with resource transition idempotency/audit;
- terminal checkpoint cleanup or retention policy.

### 9.4 StateLayout

StateLayout adds allocation roles such as:

```text
CHECKPOINT_STATE
CHECKPOINT_VALUE_BUNDLE
CHECKPOINT_EFFECT_COMMIT
```

These allocations are private generated runtime state. They are not public
authored workflow inputs and must not be consumed as semantic artifacts.

### 9.5 CLI

`orchestrator resume <run_id>` continues to be the public operator entrypoint.
The operator should not need to know whether a run resumes through flat step
state, lexical checkpoints, or a compatibility path. Diagnostics should report
which resume strategy was attempted and why it succeeded or failed.

## 10. Tranches

### C0: Checkpoint feasibility inventory

- Inventory current runtime resume state, step visit state, WCC identity,
  executable IR node identity, Semantic IR bridge identity, and StateLayout
  allocation identity.
- Identify which lexical values are already serializable through the typed value
  transport.
- Identify effect classes that lack safe resume/reuse policy.
- Produce failing fixtures for branch, loop, workflow-call, provider,
  resource-transition, and materialized-view resume.

Acceptance:

- The inventory maps every required checkpoint field to existing support,
  missing support, or explicit design gap.
- No implementation claims lexical checkpoint support based only on flat step
  resume.

### C1: Checkpoint schema and value serialization

- Define checkpoint schema version 1.
- Add typed serialization for lexical environments using existing value
  transport where possible.
- Add fail-closed validation for unknown type schema, executable digest
  mismatch, missing bundle, and stale checkpoint schema.

Acceptance:

- A pure Workflow Lisp workflow can checkpoint and restore scalar, record,
  union, optional, list, and map values supported by the current type catalog.
- Invalid or stale checkpoint records fail with typed diagnostics rather than
  Python exceptions or silent reruns.

### C2: Frame and continuation restoration

- Add runtime frame descriptors for procedure, call, loop, match, join, and
  effect frames.
- Restore execution from a checkpointed continuation in a no-external-effect
  fixture.
- Preserve variant proof scopes across restore.

Acceptance:

- A workflow checkpointed inside a `match` arm resumes with only that arm's
  proof valid.
- A workflow checkpointed inside a loop resumes with the correct loop state and
  budget.

### C3: Effect-boundary resume protocols

- Add effect-specific resume policy tables.
- Integrate provider, command, workflow-call, pure-projection,
  materialized-view, artifact-publication, and resource-transition behavior.
- Fail closed on pending non-idempotent external effects.

Acceptance:

- Completed effects are reused from validated structured output or audit
  evidence.
- Pending unsafe effects do not rerun silently.
- Resource transitions replay through idempotency/audit, not by restoring copied
  resource state from the checkpoint.

### C4: StateLayout and Semantic IR checkpoint visibility

- Add private checkpoint allocation roles to StateLayout.
- Add Semantic IR bridge entries for checkpoints and restored continuation
  provenance.
- Add source-map entries for restored lexical bindings and frame owners.

Acceptance:

- Checkpoint paths are private generated allocations.
- Debug/semantic views explain restored execution state without making
  checkpoint files semantic authority.

### C5: Operator resume integration

- Extend `orchestrator resume` to prefer lexical checkpoint resume when a
  compatible checkpoint exists.
- Keep legacy flat-step resume for historical schema runs.
- Add diagnostics that distinguish checkpoint-incompatible, effect-unsafe, and
  semantic-reuse fallback cases.

Acceptance:

- Historical runs continue under their recorded schema.
- New checkpoint-enabled runs resume through lexical checkpoints.
- Cross-schema resume fails closed unless an explicit migration exists.

### C6: Workflow-family simplification proof

- Select a parent-callable Workflow Lisp family that currently carries
  execution-position or generated-path plumbing.
- Remove resource/path plumbing that exists only for execution resume.
- Keep real domain transitions.
- Prove parity against the prior shape.

Acceptance:

- The family has fewer public/internal path parameters without losing resume.
- Domain state evidence remains typed and parity-comparable.
- No materialized view or checkpoint file is treated as semantic authority.

## 11. Alternatives Considered

### A. Resource-only resumability

Everything durable, including execution position, is modeled as resources and
transitions.

Benefits:

- one durable state abstraction;
- strong audit trail;
- fits current generic-core target.

Costs:

- high authoring burden;
- workflows expose or pass more state handles than their semantic model needs;
- execution position becomes confused with domain state.

This remains acceptable near term but is not the recommended long-term endpoint.

### B. Lexical checkpoint-only resumability

The runtime checkpoints lexical scope and workflow authors stop modeling durable
domain state.

Benefits:

- minimal workflow authoring overhead;
- strong "resume where I was" ergonomics.

Costs:

- weak semantic audit unless rebuilt elsewhere;
- poor parity for workflows whose meaning includes durable state mutation;
- hard to compare terminal/resource outcomes.

Rejected. Checkpoints resume execution; they do not define domain truth.

### C. Hybrid lexical checkpoints plus typed transitions

The runtime checkpoints execution state; workflows use resources/transitions for
domain state that matters outside execution mechanics.

Benefits:

- simpler `.orc` authoring;
- durable domain semantics remain explicit;
- non-idempotent effects stay controlled;
- WCC identity can power both flattening and future runtime execution.

Costs:

- requires a richer runtime checkpoint engine;
- requires strict schema/digest compatibility;
- requires effect-specific resume policy.

Chosen.

## 12. Failure Modes And Required Behavior

| Failure | Required behavior |
| --- | --- |
| Checkpoint schema mismatch | Fail closed with `checkpoint_schema_mismatch` |
| Executable digest mismatch | Fail closed unless explicit migration is available |
| Missing typed bundle | Fail closed or rerun only if the producing effect is declared deterministic and safe |
| Missing materialized view | Regenerate from typed value when possible; otherwise fail view validation |
| Resource version conflict | Use resource-transition conflict policy; do not restore resource state from checkpoint |
| Pending provider call | Rerun only if provider policy permits; otherwise fail closed |
| Pending command/adaptor call | Rerun only if declared idempotent/resumable; otherwise fail closed |
| Invalid variant proof | Reject checkpoint as corrupt/incompatible |
| Source-map bridge missing | Fail checkpoint provenance validation for promotion-quality runs |

## 13. Evidence And Implementation Boundaries

Required evidence:

- checkpoint schema validation tests;
- lexical value serialization round-trip tests;
- branch proof restore tests;
- loop budget restore tests;
- provider/command/resource-transition/materialized-view resume fixtures;
- negative tests for unsafe effect rerun;
- StateLayout private checkpoint allocation tests;
- Semantic IR/source-map checkpoint provenance tests;
- family simplification parity evidence.

Prohibited evidence:

- a test that passes only because the old flat step state resumed;
- a checkpoint that stores unvalidated report or pointer paths as semantic
  values;
- duplicated non-idempotent effects after resume;
- resource state restored from a stale checkpoint instead of transition/audit
  evidence;
- public `.orc` inputs for checkpoint paths or generated value bundles;
- WCC metadata exposed as public runtime output.

## 14. Compatibility And Migration

This target is additive and schema-gated.

- Existing runs continue under their recorded flat-step or legacy schema.
- New checkpoint-enabled runs record checkpoint schema and executable schema.
- Cross-schema resume fails closed unless an explicit migration is defined.
- Resource-transition evidence remains valid across both resume strategies.
- Compatibility bridge paths may remain during family migration, but they are
  not checkpoint authority.

The first production use should be opt-in for a narrow Workflow Lisp family. It
should not become the default resume path until all major effect classes have
declared resume policy and negative fixtures.

## 15. Verification Strategy

Positive fixtures:

- pure workflow resumes from lexical checkpoint;
- nested `match` resumes with correct proof scope;
- loop resumes with correct loop state and exhaustion budget;
- provider result committed before crash is reused;
- resource transition committed before crash replays through idempotency/audit;
- materialized view is regenerated from typed value;
- child workflow resumes from active child checkpoint;
- Design Delta-like parent loses pointer-path plumbing while preserving resume.

Negative fixtures:

- executable digest mismatch;
- checkpoint schema mismatch;
- stale type schema;
- pending non-idempotent command;
- invalid proof token;
- missing source-map bridge for promotion-quality run;
- checkpoint path exposed as public input;
- materialized view consumed as semantic authority.

Integration checks:

- `orchestrator resume <run_id>` against a checkpoint-enabled `.orc` fixture;
- parity report comparing old flat-step/resource-heavy shape with simplified
  lexical-checkpoint shape;
- source-map and Semantic IR inspection for checkpoint provenance.

## 16. Declarative Acceptance Scenarios

### 16.1 Branch-local resume

Initial state: a Workflow Lisp program enters a `match` arm, computes a
branch-local typed record, then crashes before the next provider call.

Entrypoint: `orchestrator resume <run_id>`.

Expected result: runtime restores the branch continuation, branch-local lexical
record, and active variant proof; execution continues to the provider call.

Forbidden result: the branch-local value is reconstructed from a pointer file or
the proof is accepted outside its branch.

### 16.2 Loop resume without domain resource state

Initial state: a bounded drain loop has lexical `iteration_count = 2` and no
domain transition has occurred in the current iteration.

Entrypoint: `orchestrator resume <run_id>`.

Expected result: runtime resumes iteration 2 from lexical checkpoint and
continues with the remaining loop budget.

Forbidden result: workflow authors must create or pass a domain resource solely
to remember the loop counter.

### 16.3 Resource transition remains semantic authority

Initial state: a work-item terminal transition committed, audit was written,
and the process crashed before rendering the summary view.

Entrypoint: `orchestrator resume <run_id>`.

Expected result: runtime restores execution after the committed transition,
reuses transition audit/idempotency evidence, and renders the missing summary
view.

Forbidden result: runtime restores copied resource state from a checkpoint and
bypasses transition audit.

### 16.4 Unsafe command does not rerun

Initial state: a non-idempotent external command was pending when the process
crashed.

Entrypoint: `orchestrator resume <run_id>`.

Expected result: resume fails closed with a diagnostic naming the unsafe pending
effect unless the command has a certified resume protocol.

Forbidden result: the command reruns silently.

## 17. Success Criteria

This target succeeds when:

- Workflow Lisp execution can resume from private lexical checkpoints for
  nested branches, loops, calls, and effect boundaries.
- Runtime checkpoint records are schema-versioned, digest-checked, validated,
  and private.
- Resources and transitions remain the only authority for durable domain
  mutation.
- Effect-specific resume protocols prevent duplicate non-idempotent side
  effects.
- StateLayout owns checkpoint paths and value-bundle paths.
- Semantic IR and source maps explain restored continuations, bindings, and
  effect evidence.
- Historical flat-step/legacy runs still resume or fail under their recorded
  schema rules.
- At least one real parent-callable Workflow Lisp family removes execution-only
  pointer/path plumbing while preserving strict parity and resume behavior.

## 18. Summary Recommendation

Use lexical checkpoint resumability as a future simplification target, not as a
near-term replacement for the generic resource core. The current WCC and
generic-core work should still land first: WCC supplies the continuation and
scope identity, and resources/transitions supply durable semantic mutation.

Once those are stable, move execution-position state into private runtime
checkpoints. That lets authored `.orc` code describe workflow logic with typed
values, calls, matches, loops, projections, views, and real domain transitions
instead of passing pointer paths around to keep the runtime resumable.
