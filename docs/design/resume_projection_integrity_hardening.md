# Resume Projection-Integrity Hardening

## Metadata

- **Status:** accepted
- **Kind:** architecture decision and runtime-state compatibility clarification
- **Owner:** workflow runtime and state owners
- **Reviewers:** runtime-state specification review, resume architecture review,
  and documentation quality review
- **Created:** 2026-07-16
- **Last material update:** 2026-07-16
- **Related docs / plans:**
  - `docs/design/workflow_lisp_procedure_migration_identity_compatibility.md`
  - `docs/design/workflow_lisp_state_layout.md`
  - `docs/plans/2026-07-13-resume-projection-integrity-hardening-design-plan.md`
  - `specs/state.md`
  - `specs/acceptance/index.md`
- **Characterization authority:** Task 1 evidence at `1cd60767` in
  `tests/test_workflow_state_projection.py`,
  `tests/test_subworkflow_calls.py`, and `tests/test_resume_command.py`
- **Implementation target:**
  `docs/plans/2026-07-13-resume-projection-integrity-hardening-implementation-plan.md`

## Summary

Checksum-compatible resume uses one shared, pure, generic **scoped** auditor at
two existing lifecycle boundaries:

1. root scope, after schema validation, current bundle load, and the existing
   root checksum guard; and
2. callee scope, synchronously inside ordinary call execution after the current
   parent call visit/start has been published and after the reached call's
   existing input/finalization/write-root/checksum/resume-bound validation, but
   before `_CallFrameStateManager`, child `WorkflowExecutor`, mutation of the
   immediately selected callee frame/state, or callee effects.

The CLI performs an early root audit before observability override,
executor-session/process metadata, executor construction, or prologue. A
`WorkflowExecutor` reruns the authoritative root checksum and root audit
immediately before prologue only when its state manager is structurally a root
`StateManager`, not a `CallFrameStateManager` carrying a parent frame. Child
executors never run this root guard; their scope was already audited
synchronously by the enclosing `CallExecutor`. There is no receipt or bypass
flag. The duplicate O(root-scope size) root work is accepted to avoid trusting
a stale CLI preflight result.

Projection-integrity and root-checksum failures have explicit envelopes:

- early root projection failure uses a dedicated atomic recorder that changes
  only root run `status`, `error`, and `updated_at`;
- the initial CLI checksum precheck remains byte-immutable, while a direct or
  post-CLI-race executor checksum mismatch uses structured
  `workflow_checksum_mismatch` and the same three-field root delta; and
- a nested/callee projection diagnostic propagates unchanged through every
  enclosing call rather than being wrapped in `call_failed`. Ordinary ancestor
  step/current/visit/call-frame/run persistence and session closure still
  occur. Only the immediately selected callee frame whose pre-construction
  audit fails is not created or mutated.

The state schema remains `2.1`. Existing root and callee checksum error types,
ordering, and mutation behavior remain distinct from projection-integrity
failure.

## Context And Authority

`specs/state.md` owns persisted identities, call frames, schema boundaries,
root/callee checksum behavior, run failure state, and future state upgraders.
`specs/acceptance/index.md` owns public acceptance clauses.
`WorkflowStateProjection` owns executable-IR-derived mapping between runtime
identity and persisted compatibility surfaces.

The prior compatibility design identifies a checksum-compatible gap and
requires:

- retained entry projection ownership for root state;
- parent call-boundary ownership of each persisted caller identity;
- current-callee selection through that current boundary under existing
  import/checksum rules;
- selected-callee projection ownership of frame-local state; and
- projection-owned loop-qualified resolution.

Task 1 characterization establishes:

- completed stale or presentation-mismatched explicit IDs currently pass;
- projection APIs generate qualified loop/call IDs but do not reverse-resolve
  them;
- duplicate non-completed frames select by mapping order;
- stale caller identity can be ignored and create a fresh child;
- current parent bundles can select distinct imported bundles recursively;
- root failure currently follows CLI/prologue mutation;
- direct executor failure currently follows prologue binding;
- stale callee-local identity currently mutates parent/child state before
  failure; and
- callee checksum mismatch already occurs inside ordinary call execution after
  parent-level lifecycle has begun and before child construction/effects.

The last fact governs this design. Callee checksum and callee-local audit stay
at that call boundary rather than moving to root entry.

## Problem

A checksum-compatible run can contain explicit persisted identities that do not
belong to the current projection for their scope:

- a stale `steps.*.step_id`;
- a valid ID under another presentation key;
- a loop-qualified ID inconsistent with persisted loop progress;
- a frame `call_step_id` that names no current parent boundary;
- more than one non-completed frame competing for one boundary;
- a persisted alias that disagrees with the current boundary; or
- stale callee-local identity after the selected callee checksum succeeds.

Current behavior may accept the state, choose by map order, create a fresh
frame, or detect the defect only after child mutation. Planner-only validation
cannot solve parent-boundary ownership, current-callee selection, frame
classification, or call checksum precedence.

The solution must use one policy owner while preserving actual root and call
lifecycle order.

## Goals And Non-Goals

### Goals

- Validate every explicit resume identity presented to a current scope against
  exactly one owning `WorkflowStateProjection`.
- Reject root-scope defects before CLI/prologue mutations.
- Preserve ordinary call execution order and existing callee checksum
  precedence.
- Audit selected callee-local state after checksum and before child
  construction/effects.
- Resolve caller ID against the parent boundary; select callee from the current
  boundary, not persisted alias alone.
- Classify completed history, non-Workflow-Lisp resumable frames, and complete
  Workflow Lisp retry lineages without map-order selection.
- Add projection-owned loop reverse resolution without caller-side ID parsing.
- Preserve only the exact supported optional-ID lane.
- Keep pre-v2.0 and pre-`schema_version: "2.1"` reusable-call rejection.
- Provide stable persisted diagnostics with exact failure envelopes.
- Keep schema `2.1` and prohibit evidence/name/family coupling.

### Non-Goals

- Root-time audit of nested callee-local state.
- Moving callee checksum ahead of ordinary call execution.
- Suppressing ordinary parent step/visit/current failure persistence for nested
  call failure.
- Running root checksum/audit guards inside child executors.
- Changed-source resume, remapping, aliasing, or an upgrader.
- Backfilling omitted IDs.
- Changing fresh execution, force restart, exports, or artifact semantics.
- Reading migration/retirement evidence.

## Decision

### Chosen architecture

Add one pure `ResumeProjectionIntegrityAuditor` that audits one workflow scope:

```text
audit_scope(
    bundle: LoadedWorkflowBundle,
    state: Mapping[str, Any],
    scope_path: ResumeScopePath,
) -> None
```

It validates:

- local step-result/current-step explicit identities;
- loop progress before constructing loop-qualified candidates;
- caller identity and persisted-alias shape for every locally stored mapping
  call frame; and
- deterministic frame grouping/cardinality and retry-lineage shape.

It does not load/checksum child bundles or write state.

Adapters invoke it:

- root CLI before resume metadata;
- structurally root executor immediately before prologue, after independent
  root checksum revalidation; and
- ordinary `CallExecutor.execute_call` after current call validations and
  callee checksum, before child construction.

### Architecture comparison

| Architecture | Direct coverage | Root failure ordering | Actual callee boundary | TOCTOU behavior | Cohesion | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| CLI-only root audit | Missing | Early | Could preserve | Outer result may go stale | Wrong owner | Rejected |
| Executor-prologue only | Strong | CLI metadata already exists | Could preserve | Fresh check | Too late for public root envelope | Rejected |
| Planner-owned | Indirect | Too late | Planner lacks callee/checksum ownership | Fresh only at planner | Wrong responsibility | Rejected |
| Separate root and call validators | Strong | Can be early | Natural | Depends on adapters | Duplicated policy | Rejected |
| Shared scoped auditor; CLI early audit; root-manager executor rerun; call adapter after existing checksum | Strong | Early initial CLI failure; direct/post-entry structured failure | Preserved exactly | No receipt; root executor reruns | One policy owner | Selected |

### Tradeoffs

- CLI success performs root audit twice.
- A race introduced after the early CLI audit can be caught by the executor
  rerun after CLI metadata is already open; that second failure follows the
  already-open outer lifecycle envelope, not the early-root envelope.
- Nested projection failure intentionally allows normal parent failure
  persistence because the parent call visit has already started.
- Workflow Lisp failed retry history is recursively checksum/audit validated
  after a running member's checksum/resume-bound guards but before its local
  audit/resume, and before fresh retry/allocation when no running member exists.
  Both paths therefore increase resume cost with lineage length and reject
  stale history that was formerly ignored.
- Each deeper scope is audited only when its ordinary call boundary is reached.

## Design Details

### Projection resume-slot APIs

`WorkflowStateProjection` gains typed public APIs:

```text
enumerate_resume_slots(state) -> ResumeProjectionSlotIndex
resolve_resume_step_id(slot_index, step_id, presentation_key?)
    -> ResumeIdentityResolution
resolve_call_boundary(slot_index, call_step_id)
    -> ResumeCallBoundaryResolution
```

The slot index contains:

- body and finalization slots;
- structurally generated loop-local slots;
- loop-contained call-boundary runtime IDs created with existing
  `repeat_until_runtime_step_id`, `for_each_runtime_step_id`, and
  `call_boundary_runtime_step_id`;
- candidate tuples so duplicates are not overwritten; and
- explicit persisted rows unclaimed by an exact slot.

Resolution is exact candidate lookup. The auditor, CLI, executor, planner, and
call executor do not split, prefix-match, normalize, or reconstruct qualified
IDs.

`CallBoundaryProjection` additionally exposes the current imported alias
derived from executable IR. Persisted alias is validation input, not selection
authority.

### Loop progress validation

Loop progress is validated before candidate generation.

For `for_each`:

- container is a mapping;
- `items` is a list;
- `completed_indices` is a list of unique non-boolean, nonnegative integers;
- every completed index is less than `len(items)`;
- `current_index` is `null` or a non-boolean integer in the same range;
- `current_index` is not also completed; and
- no conflicting duplicate/current state is accepted.

For `repeat_until`:

- container is a mapping;
- `completed_iterations` is a list of unique non-boolean, nonnegative integers;
- `condition_evaluated_for_iteration` is `null` or a non-boolean,
  nonnegative integer;
- `last_condition_result` is `null` or boolean;
- `exhausted`, when present, is boolean; and
- every completed/condition/current index is below the projection's declared
  `max_iterations`.

Four progress forms are valid.

Active:

- `current_iteration` is a non-boolean, nonnegative integer;
- it is not in `completed_iterations`;
- completed iterations form valid prior history for the current iteration;
- `condition_evaluated_for_iteration` is `null` or equals
  `current_iteration`;
- `last_condition_result` is `null` exactly when the condition has not been
  evaluated, otherwise it is boolean; and
- `exhausted` is absent or `false`.

Terminal success:

- `current_iteration` is `null`;
- `completed_iterations` is nonempty and its greatest member is the terminal
  iteration;
- `condition_evaluated_for_iteration` equals that terminal iteration;
- `last_condition_result` is `true`; and
- `exhausted` is absent or `false`.

Terminal exhaustion with successful `on_exhausted` outputs:

- `current_iteration` is `null`;
- declared `max_iterations` is present and positive;
- completed iterations cover the declared iteration range and the greatest
  member is `max_iterations - 1`;
- `condition_evaluated_for_iteration` equals that terminal iteration;
- `last_condition_result` is `false`; and
- `exhausted` is `true`; and
- the enclosing repeat frame has `status: completed`.

Terminal failed exhaustion without `on_exhausted` outputs:

- `current_iteration` is `null`;
- declared `max_iterations` is present and positive;
- completed iterations cover the declared iteration range and the greatest
  member is `max_iterations - 1`;
- `condition_evaluated_for_iteration` equals that terminal iteration;
- `last_condition_result` is `false`;
- `exhausted` is absent or `false`; and
- the enclosing repeat frame has `status: failed` with
  `error.type: repeat_until_iterations_exhausted`.

Completed iteration IDs continue to generate projection candidates in all
terminal forms. These rules match current persistence, which writes
`current_iteration: null` on success and exhaustion. Implementation may refine
only a finer-grained ordering detail if an executable fixture proves current
runtime state differs; it may not reject either terminal form or weaken their
mutual-consistency checks.

Wrong containers/types use reason `unsupported_shape`. Domain/range/conflict
failures use `invalid_loop_progress`. Invalid progress cannot generate
candidate identities.

### Exact optional-ID compatibility lane

Omission compatibility applies to every recognized schema-valid `steps.*`
step-result row for which the existing runtime supports presentation/name/order
fallback. It is not status-restricted. This includes completed, skipped,
failed, and any schema-supported running loop-frame/result shape. It includes
top-level, finalization, and loop-local step-result rows. The auditor leaves
the field absent and retains the existing fallback. Whenever `step_id` is
present, it is audited exactly.

There is no omission compatibility for:

- `current_step.step_id`;
- `call_frames.*.call_step_id`;
- call-frame current position;
- loop/current progress identity fields; or
- any non-step-result selector whose schema requires explicit identity.

Missing required identity fails `missing_required_identity`. Unsupported
step-result containers or row shapes fail according to schema/shape rules, not
because of terminal versus nonterminal status.

### Call-frame classes, retry lineage, and deterministic selection

Every mapping frame is validated for caller-ID and alias shape, including
historical and retry-history frames. Non-mapping frames fail
`unsupported_shape`.

Allowed statuses are exactly `completed`, `running`, and `failed`:

- `completed`: historical, never resumable, unlimited in count if individually
  valid;
- `running`: non-completed resumable candidate;
- `failed` with a non-Workflow-Lisp selected target: non-completed resumable
  candidate;
- `failed` with a Workflow Lisp selected target: retry-history member whose
  selected-callee checksum and local explicit identities must validate before
  resume or fresh retry is authorized.

Workflow Lisp target capability is derived from the loaded selected bundle's
typed frontend capability/provenance, never a file suffix,
workflow/module/procedure basename, or family string. The current
`workflow_path.suffix == ".orc"` test is replaced by that typed capability.

Add a typed `CallFrameRetryLineageIndex` API. It centralizes the existing
`::retry::N` compatibility parsing so the auditor and call adapters consume
typed lineage members and never split frame IDs themselves:

```text
index_retry_lineage(
    boundary_step_id: str,
    frame_items: Iterable[(frame_id, frame)],
) -> CallFrameRetryLineage

CallFrameRetryLineage:
  base_frame_id: str
  completed_members: tuple[FrameMember, ...]
  failed_predecessors: tuple[RetryFrameMember, ...]  # ordinal 0..N
  running_member: FrameMember | null

next_unused_retry_frame_id(lineage) -> str
```

The base failed frame has ordinal `0`; `::retry::N` members have positive
integer ordinals. Duplicate ordinals, missing/invalid ordinals, nested retry
markers, mixed base lineages for one boundary, or a retry member whose
caller/alias/boundary differs fail closed. Allocation returns the deterministic
next unused positive ordinal from the validated lineage, not a key selected by
mapping iteration.

Selection algorithm:

1. group frames by exactly resolved parent boundary runtime ID;
2. validate every frame's caller ID and persisted alias;
3. exclude completed frames from resume candidates;
4. classify the selected target by typed frontend capability;
5. for non-Workflow-Lisp targets, allow at most one non-completed member;
6. for Workflow Lisp targets, build and validate one retry lineage, allow zero
   or one running member, and retain any number of failed predecessors;
7. if a Workflow Lisp running member exists, checksum it and validate its
   resume-bound inputs first; if both pass, checksum and recursively audit
   every failed predecessor in ordinal order, then audit the running member's
   local scope and resume it;
8. if no Workflow Lisp running member exists, checksum and recursively audit
   every failed predecessor in ordinal order, then allocate the deterministic
   next unused retry ID and start fresh.

Failed predecessor local state is never exempt from audit. This is a deliberate
fail-closed strengthening over current behavior. Multiple running members fail
`ambiguous_resumable_call_frame`. Mixed lineages and duplicate ordinals use the
same ambiguity reason; malformed lineage syntax/status uses
`unsupported_shape`. Frame mapping order is never consulted.

### Root CLI ordering

For ordinary non-force resume:

1. load state;
2. apply existing schema rejection;
3. load current root bundle;
4. apply existing lowering-schema checks;
5. apply existing root checksum guard;
6. run early root `audit_scope`;
7. if it fails, use the early-root recorder, print error, return `1`;
8. if it passes, persist requested observability override;
9. open/persist executor session;
10. write process metadata;
11. construct executor; and
12. call executor resume.

Early root audit failure occurs before override/session/process/construction/
prologue. It does not invoke planner, quarantine, call, step, or effect paths.

### Structurally root executor revalidation

`WorkflowExecutor.execute(resume=True)` performs root checksum/audit
revalidation only when its state manager is structurally root state:

```text
is_root_resume_manager =
    isinstance(state_manager, StateManager)
    and not isinstance(state_manager, CallFrameStateManager)
    and not isinstance(getattr(state_manager, "frame_id", None), str)
```

The concrete implementation should use the existing runtime-checkable
`CallFrameStateManager` protocol as the primary discriminator, with the
`frame_id` check as a defensive invariant. It must not infer scope from
workflow name, path, bundle provenance, or a caller-supplied bypass flag.

For a structurally root manager, execution:

1. loads current state;
2. applies schema guard;
3. resolves authoritative current workflow path from the loaded bundle's
   `WorkflowProvenance.workflow_path`;
4. compares persisted `state.workflow_checksum` with the current path using
   existing `StateManager.calculate_checksum`/checksum validation semantics;
5. on mismatch, records structured `workflow_checksum_mismatch`, sets root
   `status: failed` and `updated_at`, leaves current step/steps/visits/frames
   unchanged, and does not run projection audit;
6. on checksum success, reruns root `audit_scope`; and
7. only then enters `_execute_prologue`.

No receipt, flag, outer assertion, or caller-provided result can bypass steps
3-6 for a root manager. CLI therefore audits twice. Direct executor
construction has occurred, but direct failure is pre-prologue.

A child executor has a `CallFrameStateManager`/`frame_id` and skips this entire
root guard. Its selected local scope was synchronously checksum/audited by the
enclosing `CallExecutor` before `_CallFrameStateManager` construction. No flag
is passed to the child and there is no second child audit.

The provenance workflow path is authoritative for the current bundle. The
persisted workflow file is not allowed to redirect checksum calculation away
from that loaded bundle.

### Actual reached-call ordering

The nested adapter remains inside ordinary `CallExecutor.execute_call`. The
order is:

1. select current imported bundle from the current step/boundary alias;
2. resolve authored bound inputs;
3. rederive the deterministic frame group/typed retry lineage and revalidate
   caller/alias/cardinality for races after scope-entry audit;
4. finalize managed/runtime-context bound inputs;
5. validate write-root bindings;
6. if a running Workflow Lisp member exists, apply its existing callee
   checksum validation and then its persisted resume-bound-input validation;
   either failure wins immediately;
7. for Workflow Lisp failed history, checksum and recursively audit every
   predecessor in ordinal order;
8. for a non-Workflow-Lisp resumable member, apply existing callee checksum and
   persisted resume-bound-input validation;
9. run callee-local `audit_scope` for the resumable member, including the
   running Workflow Lisp member after its history passes;
10. for fresh Workflow Lisp retry, allocate the next ID through the typed
   lineage API;
11. construct `_CallFrameStateManager`;
12. construct child `WorkflowExecutor`; and
13. execute child workflow.

The parent call step visit/start/current-step publication has already occurred
before this method. The design does not introduce a pre-publication seam or a
special result handoff.

### Split error precedence

There is no single global ordering across scope entry and future reached calls.

Scope-entry audit precedence:

1. existing schema rejection;
2. root checksum guard for root scope;
3. local step/current/loop projection validation;
4. locally stored call-frame shape, caller boundary resolution, persisted
   alias validation, and cardinality/retry-lineage validation.

This audit occurs before any future reached call's bound-input work. A locally
stored nested frame defect can therefore fail at scope entry before execution
ever reaches that call.

Reached-call revalidation precedence, including races after scope audit:

1. missing current imported bundle;
2. existing authored bound-input resolution error;
3. revalidated malformed frame/caller identity, alias mismatch,
   cardinality/retry-lineage ambiguity;
4. existing bound-input finalization or write-root error;
5. running Workflow Lisp member checksum error;
6. running Workflow Lisp member persisted resume-bound-input error;
7. failed retry-history checksum error in ordinal order;
8. failed retry-history local projection-integrity error in ordinal order;
9. non-Workflow-Lisp resumable-member checksum/resume-bound error;
10. resumable-member callee-local projection-integrity error; and
11. frame allocation, child construction, or child execution error.

A callee local-scope audit includes that callee's locally stored nested frame
defects. It can therefore expose them before those future nested calls' own
binding work.

An existing callee checksum mismatch before local audit keeps
`call_resume_checksum_mismatch`; it is not wrapped or replaced. A checksum
mismatch introduced after a previously successful attempt is still reported
before any local projection defect. If checksum is repaired and local identity
remains invalid, the next attempt reaches and reports
`resume_projection_integrity_error`.

### Split failure envelopes

#### Initial CLI checksum precheck mismatch

The existing CLI checksum check remains the first source-compatibility gate
after bundle/lowering-schema checks. On mismatch it:

- prints the existing checksum-mismatch message;
- returns exit code `1`;
- does not construct an executor or open a session; and
- leaves the entire persisted run tree byte-for-byte unchanged.

This envelope has no persisted structured diagnostic because mutation itself
would violate the established byte-immutable contract.

#### Early CLI or direct root projection-audit failure

A dedicated atomic recorder changes exactly:

- root `status` to `failed`;
- root `error`; and
- root `updated_at`.

It does not change current step, step results, visits, loops, frames, artifacts,
outputs, observability, session/process metadata, logs, backups, or sidecars.

For early CLI failure, override/session/process/construction/prologue have not
occurred. For direct failure, executor construction has occurred but prologue
has not.

The recorder leaves an unchanged `current_step` even if it says `running`.
That is valid forensic state: run-level `status: failed` and
`error.type: resume_projection_integrity_error` are authoritative. Status,
heartbeat, and stalled-run interpretation must not treat that current step as
live. A later resume after repair reruns schema, checksum, root audit, and then
the existing current-step planner.

#### Root-executor checksum recheck mismatch

The new direct/post-entry recheck uses:

```text
error.type: "workflow_checksum_mismatch"
error.message: "Workflow has been modified since the run started"
error.context:
  workflow_file: string or null
  persisted_checksum: string or null
  current_checksum: string or null
  reason: "workflow_modified" | "missing_recorded_checksum"
          | "missing_workflow_path" | "workflow_unavailable"
```

It atomically changes only root `status`, `error`, and `updated_at`.
`current_step`, steps, visits, loops, frames, artifacts, and outputs remain
unchanged. A direct executor returns the resulting failed root state.

For a source race after the initial CLI precheck, session/process metadata may
already exist. The CLI prints the structured mismatch, returns `1`, and closes
the already-open session as failed. Session closure may update its own
observability/session fields but cannot replace `workflow_checksum_mismatch`.
The projection auditor and prologue do not run.

#### Post-CLI root projection race

If checksum remains compatible but root identity state changes after the early
CLI audit, the structurally root executor's second audit catches it after
session/process metadata may already be open. It uses the same atomic
projection recorder as other root projection-audit failures:

- change only root `status`, `error`, and `updated_at`;
- preserve already-written session/process metadata;
- leave current step/steps/visits/loops/frames/artifacts/outputs unchanged
  except for the external identity mutation that caused the failure;
- return before prologue and before sticky step-routing classification; and
- close the opened session as failed without replacing
  `resume_projection_integrity_error`.

The CLI prints the projection diagnostic and returns exit code `1`.

#### Nested/callee projection-integrity propagation

The call boundary uses ordinary typed result propagation:

```text
projection_integrity_failed_result(diagnostic) -> StepResult:
  status: "failed"
  exit_code: 2
  error: diagnostic

propagate_child_error(child_state) -> StepResult:
  if child_state.error.type == "resume_projection_integrity_error":
      return projection_integrity_failed_result(child_state.error)
  return existing_call_failed_wrapper(child_state.error)

classify_terminal_result(result) -> TerminalResultClass:
  if result.error.type == "resume_projection_integrity_error":
      return STICKY_PROJECTION_INTEGRITY_FAILURE
  return existing_result_classification(result)
```

A pre-construction selected-callee audit failure is first promoted into the
current caller/parent scope as that call step's failed result and as the
caller scope/run error. The selected callee frame/state remains untouched. Each
already-existing ancestor `CallExecutor` returns and persists the same
diagnostic object/value unchanged rather than wrapping it in `call_failed`, and
promotes it into its own caller scope. This repeats until the root state error
equals the original diagnostic.

Ordinary parent step/current/visit/call-frame snapshots, ancestor state
mutation, run failure persistence, epilogue, and already-open session closure
remain required. Only the immediately selected callee frame/state whose
pre-construction audit fails is not created or mutated. At a deeper failure,
ancestor frames necessarily already exist and persist their ordinary failed
snapshots.

`STICKY_PROJECTION_INTEGRITY_FAILURE` is non-routable and terminal after the
ordinary failing step/current/visit persistence completes:

- bypass authored failure, success, and `always` routes;
- ignore `on_error=continue`;
- propagate immediately out of loop/container execution;
- force failed termination in the current scope and every enclosing caller;
- do not convert the diagnostic into an exception unwind; and
- require no state-schema change.

Ordinary configured finalization may still run under existing finalization
semantics, but it cannot wrap, replace, clear, or downgrade the exact projection
diagnostic. Any finalization failure is supplemental in finalization state; the
scope/run `error` remains the original
`resume_projection_integrity_error`. Epilogue and session closure preserve it.

Write ordering is:

1. construct the stable projection-integrity diagnostic;
2. promote it into the current caller/parent failed call-step result and
   scope/run error without constructing the selected callee frame manager;
3. at each existing ancestor, persist the ordinary failed call result/current/
   visit/frame snapshot with the exact same diagnostic;
4. persist root run `status: failed` and the exact diagnostic as root `error`;
5. run ordinary failed epilogue/session closure without replacing root
   `error`.

Session closure may update `runtime_observability`, `updated_at`, and its own
session row; it must not overwrite or downgrade the root diagnostic. There is
no mutation-free exception unwind and no three-field-only promise for nested
failure.

### Diagnostic schema

For projection-integrity errors, every context field is present:

```text
error.type: "resume_projection_integrity_error"
error.message: stable bounded summary
error.context:
  diagnostic_schema: "resume_projection_integrity_error.v1"
  reason: stable enum
  scope_path: ordered identity-only root/call-frame components
  field: stable field kind or relative path
  offending_value: JSON value or null when absent
  expected_owner:
    workflow_file: string
    workflow_checksum: string
    projection_scope: string
  candidate_count: integer or null
  call_boundary_step_id: string or null
```

Missing values use JSON `null`; fields are not omitted.

Reasons include:

- `unknown_explicit_step_id`;
- `presentation_slot_mismatch`;
- `out_of_scope_step_id`;
- `unclaimed_explicit_step_row`;
- `missing_required_identity`;
- `missing_call_boundary`;
- `ambiguous_call_boundary`;
- `ambiguous_resumable_call_frame`;
- `persisted_import_alias_mismatch`;
- `missing_imported_bundle`;
- `unsupported_shape`;
- `invalid_loop_progress`.

Imported-bundle ambiguity is not a reason: the current loaded-bundle imports
surface is a mapping with one value per alias, so ambiguity is structurally
impossible after a valid load. Workflow Lisp already rejects duplicate import
aliases. Classic YAML currently has silent last-wins duplicate-key behavior, so
generic duplicate import-alias rejection is a named implementation
prerequisite: the classic loader must detect and reject duplicate authored
aliases, preferably duplicate mapping keys at the import boundary, before
bundle construction. The runtime resolver then observes only a unique bundle
or a missing alias. Missing alias/bundle remains fail closed.

Diagnostics expose only identity metadata already needed by operators. They do
not expose bound inputs, context, artifacts, prompts, provider output, secrets,
whole frame state, or whole projections.

CLI exit code is `1`. Existing status/report surfaces render root `error`; no
new report schema is required.

## Contracts And Interfaces

### Old behavior

- Stale completed IDs may pass.
- Stale callers may create a fresh child.
- Duplicate non-completed frames may select by map order.
- Workflow Lisp fresh retry may ignore failed predecessor child-local defects.
- Every executor follows the same prologue path regardless of root/frame scope.
- Nested child failures are wrapped in `call_failed`.
- Callee-local stale state may mutate child frame before failure.

### New behavior

- CLI root projection defects fail before resume metadata; only structurally
  root executors recheck checksum/audit before prologue.
- Initial CLI checksum mismatch is byte-immutable; direct/post-entry executor
  mismatch persists structured `workflow_checksum_mismatch`.
- Callee lifecycle order and checksum precedence remain actual/current.
- Callee-local audit is inserted after checksum and resume-bound validation,
  before child manager/executor.
- Nested projection diagnostics propagate unchanged through ancestors while
  ordinary ancestor failure state persists.
- Projection-integrity results are sticky terminal failures that bypass
  authored routes, continuation policy, and loop/container continuation.
- Exact frame classes preserve completed history and typed Workflow Lisp retry
  lineages without map-order selection; failed history is checksum/local
  audited after running checksum/resume-bound guards but before running local
  audit/resume, or before fresh retry.
- Optional omission applies to every schema-recognized step-result row that
  supports existing fallback, independent of status.
- Active and all terminal success/successful-exhaustion/failed-exhaustion loop
  progress is validated before candidate generation.

### Interface impact

- New projection slot/reverse-resolution APIs.
- Current alias on `CallBoundaryProjection`.
- New typed frame classification and `CallFrameRetryLineageIndex` APIs,
  including deterministic next-ID allocation.
- New pure scoped auditor and exact diagnostic.
- New early-root atomic recorder.
- Root-manager-only executor checksum/audit path with no bypass/receipt.
- Structured `workflow_checksum_mismatch` for the executor recheck envelope.
- Typed call-result promotion preserves
  `resume_projection_integrity_error` unchanged instead of `call_failed`.
- Typed terminal-result classifier recognizes sticky projection-integrity
  failure across step routing, loop/container propagation, finalization, and
  epilogue.
- Classic YAML loader rejects duplicate authored import aliases before bundle
  construction; Workflow Lisp retains its existing duplicate-alias diagnostic.
- No state/report schema version change.

## Dependencies And Sequencing

Implementation requires:

1. classic YAML duplicate import-alias/key rejection plus loader tests;
2. normative state/acceptance text;
3. typed projection slots plus loop validation/reverse resolution;
4. boundary alias metadata;
5. typed frame classifier/retry-lineage index with bundle frontend-capability
   input;
6. pure scoped auditor/diagnostic;
7. early-root recorder and forensic current-step/status behavior;
8. early CLI audit plus root-manager-only executor checksum/audit rerun and
   structured mismatch recorder;
9. call adapter after existing checksum/resume-bound validation, including
   failed-history recursive audit;
10. unchanged typed diagnostic propagation through call results, epilogue, and
   session closure; and
11. public integration, loader structural-impossibility, and no-evidence-read
   tests.

No receipt or pre-publication call seam is part of the implementation.

## Invariants And Failure Modes

### Invariants

- Root checksum precedes each root audit.
- Only structurally root managers run executor root checksum/audit; child
  executors never do.
- Callee checksum precedes callee-local audit at the existing call boundary.
- Parent visit/start publication remains ordinary.
- Exactly one current projection owns an accepted explicit identity.
- Qualified IDs are not caller-parsed.
- Completed frames are never resumable.
- Non-Workflow-Lisp boundaries have at most one non-completed frame.
- Workflow Lisp boundaries have one validated retry lineage, zero/one running
  member, and any number of audited failed predecessors.
- Every Workflow Lisp failed predecessor is checksum/audited in ordinal order
  after the running member's checksum/resume-bound guards but before its local
  audit/resume, or before fresh allocation when no running member exists.
- Workflow Lisp capability comes from the typed loaded bundle, not names,
  suffixes, or family strings.
- A pre-construction audit never creates/mutates the immediately selected
  callee frame/state/effects; ancestor frames may persist ordinary failure.
- Projection diagnostics propagate unchanged through call boundaries.
- Projection-integrity failure is sticky/non-routable after ordinary failure
  persistence; routes, `on_error=continue`, and loop/container continuation
  cannot consume it.
- Finalization/epilogue/session closure cannot replace the diagnostic.
- Root diagnostic survives parent persistence and session closure.
- Optional ID omission is limited by recognized step-result schema/fallback
  support, not status.
- Runtime never reads evidence records or selects by family/name/basename.

### Failure table

| Condition | Precedence and result |
| --- | --- |
| Unsupported schema | Existing schema rejection before bundle/audit |
| Initial CLI root checksum mismatch | Existing byte-immutable exit `1`; no session/executor |
| Direct/post-entry root checksum mismatch | Structured `workflow_checksum_mismatch`; status/error/updated_at only; no projection audit |
| Root explicit identity invalid | Early root recorder changes only status/error/updated_at |
| Loop progress malformed | `unsupported_shape` before candidate generation |
| Loop progress conflicting/out of domain | `invalid_loop_progress` before candidate generation |
| Valid terminal repeat success/successful exhaustion/failed exhaustion | Completed iteration candidates retained; resume accepted |
| Current-step/caller required identity absent | `missing_required_identity` |
| Completed historical frame valid | Retained, never resumable |
| Non-Workflow-Lisp has more than one non-completed frame | `ambiguous_resumable_call_frame`; no map-order choice |
| Workflow Lisp has multiple running members/mixed lineages/duplicate ordinals | Ambiguous or `unsupported_shape` as defined by lineage validation |
| Workflow Lisp failed history, no running member | Checksum/audit every predecessor, then allocate deterministic next retry ID |
| Workflow Lisp running member plus failed history | Running checksum/resume-bound first; then history checksum/audit; then running local audit/resume |
| Missing current imported bundle | Projection failed call result before checksum/child |
| Persisted alias mismatch | Projection failed call result; no redirection |
| Callee checksum mismatch | Existing `call_resume_checksum_mismatch`; local audit not run |
| Resume-bound input mismatch | Existing error; local audit not run |
| Callee-local explicit identity invalid | Sticky diagnostic promoted unchanged; immediate callee frame/state/effect absent; no authored route/continue |
| Deeper callee-local explicit identity invalid | Same diagnostic reaches root; ordinary ancestor failed snapshots persist |
| Missing optional schema-supported step-result ID | Existing fallback; no backfill |
| Unknown frame status/non-mapping frame | `unsupported_shape` |
| Duplicate authored import alias | Loader/bundle rejection before resume; no runtime ambiguity reason |

## Security, Operations, And Performance

The auditor adds no authority or credentials. It reads only the current
scope's bundle/state. Call execution performs existing import/checksum reads.
No evidence store is read.

Diagnostics are bounded and identity-only.

CLI performs two O(root-scope size) scans. Each reached call scans the selected
callee local scope. A Workflow Lisp running-member resume additionally
checksum/audits each failed predecessor after running checksum/resume-bound
guards and before running local audit/resume; a fresh-retry path does so before
allocation. Cost on both paths is linear in validated retry-history state.
This is accepted for anti-TOCTOU and fail-closed history correctness. No cache
or receipt is persisted.

Operators see the stable root error. A failed run with unchanged running
`current_step` is not live because root status/error are authoritative.

## Evidence And Implementation Boundaries

Implementation proof must use default paths, not:

- direct calls only to checksum/resolver helpers;
- CLI-only audit;
- a receipt/flag that bypasses executor revalidation;
- planner-only validation;
- root-time nested callee audit;
- a pre-parent-publication call seam;
- a helper-only failed result handoff;
- map-order frame selection;
- persisted alias as bundle authority;
- evidence/name/family branches; or
- report parsing.

Required evidence:

- exact early CLI default/override ordering;
- root-manager-only executor checksum/audit immediately pre-prologue;
- initial CLI byte-immutable mismatch plus direct/post-entry structured
  `workflow_checksum_mismatch` envelopes;
- root three-field projection/mismatch deltas and forensic unchanged-current-
  step behavior;
- actual `CallExecutor.execute_call` ordering through input/finalization/
  write-root/checksum/resume-bound/local-audit/retry-allocation/child
  construction;
- checksum-before/after mutation scenario;
- exact unchanged projection diagnostic promotion through one- and two-level
  calls, epilogue, and session close;
- no immediate selected-callee frame/state/effect mutation, with promotion into
  the current caller/parent and ordinary ancestor failed snapshots;
- typed Workflow Lisp multi-predecessor lineage, running-member, invalid-
  lineage, running-checksum/resume-bound-before-history ordering,
  fresh-history ordering, and next-ID behavior;
- sticky classifier bypasses authored routes, `always`, `on_error=continue`,
  and loop/container continuation while preserving ordinary failure records;
- configured finalization may run but cannot replace the projection diagnostic;
- loop active/terminal-success/successful-exhaustion/failed-exhaustion positives
  plus malformed/conflict negatives;
- structurally valid loop bookkeeping with a stale/out-of-scope loop-local
  explicit `step_id` fails exact generated-candidate lookup before effects,
  without parsing or backfill;
- structurally valid loop bookkeeping with a stale/out-of-scope loop-contained
  call-boundary ID fails exact boundary-candidate lookup before call effects,
  without parsing or backfill;
- classic YAML and Workflow Lisp loader rejection of duplicate imported
  aliases before bundle construction;
- symlink-aware whole-run-tree snapshots; and
- tripwired absence of evidence readers.

Task 1 tests are characterization, not target implementation proof.

## Compatibility And Migration

Retained:

- schema `2.1`;
- exact schema-supported step-result omission lane;
- initial CLI root checksum byte-immutable behavior;
- callee checksum behavior and actual boundary;
- completed frame history;
- legitimate typed Workflow Lisp multi-retry history and fresh retry;
- ordinary parent nested-failure persistence;
- fresh execution and force restart.

Stricter:

- invalid explicit root/local identities;
- malformed loop progress;
- missing required current/caller identity;
- non-Workflow-Lisp duplicate non-completed frames;
- malformed/mixed Workflow Lisp retry lineage and stale failed history;
- classic YAML duplicate import aliases that previously resolved last-wins;
- stale caller/alias state.

Not introduced:

- pre-v2.0 or pre-`2.1` reusable-call resume;
- changed-source resume;
- identity backfill/remap;
- runtime imported-bundle ambiguity reason;
- runtime evidence exceptions.

If current supported retry state cannot be classified by the exact typed rules,
stop and revise rather than fall back to map order.

## Verification Strategy

### Projection/loop tests

- exact body/finalization/loop/call candidates;
- active, terminal-success, successful-exhaustion, and failed-exhaustion repeat
  progress;
- terminal completed iteration candidates remain resolvable;
- malformed type/domain/conflict/terminal-consistency loop negatives;
- no candidates generated from invalid progress;
- valid loop bookkeeping plus stale/out-of-scope loop-local explicit
  `step_id`, and loop-contained call-boundary ID where applicable, fails exact
  candidate lookup before effects without parsing or backfill;
- exact qualified reverse resolution without caller parsing;
- completed/skipped/failed and supported running step-result missing-ID
  compatibility;
- present IDs remain audited;
- missing current/caller/non-step-result required identity rejection.

### Frame tests

- unlimited valid completed frames;
- unique running resumable frame;
- unique failed non-Workflow-Lisp resumable frame;
- Workflow Lisp failed predecessor histories with ordinals `0..N`;
- Workflow Lisp running member plus failed history;
- running checksum and resume-bound mismatch precedence before stale history;
- checksum/local audit of every failed predecessor before running local audit/
  resume or fresh retry;
- deterministic next unused retry ID;
- multiple running, mixed lineage, duplicate/malformed ordinal rejection;
- unknown status/non-mapping rejection;
- non-Workflow-Lisp multi-noncompleted combinations ambiguous;
- typed target capability proof independent of names and file suffixes.

### Root integration

- early CLI root audit before override/session/process/construction;
- initial CLI checksum mismatch is byte-immutable;
- root-manager executor checksum and audit rerun before prologue with no bypass;
- child executor proves the structural guard is skipped;
- direct authoritative provenance-path checksum;
- direct and post-CLI-race mismatch persist structured
  `workflow_checksum_mismatch`;
- post-CLI checksum-compatible identity race uses the three-field projection
  recorder, preserves opened session/process metadata, and closes failed
  without diagnostic overwrite;
- three-field early-root delta;
- unchanged current step is forensic and not live in status/heartbeat/stall.

### Call integration

- actual order through current validations/checksum/local audit;
- checksum mismatch hides later local projection defect;
- after checksum repair, local defect is reported;
- exact diagnostic remains unchanged across one/two-level promotion;
- ordinary parent step/current/visit/frame/run persistence;
- pre-construction failure is first recorded in the current caller/parent, not
  in an unconstructed selected-callee scope;
- root diagnostic survives epilogue/session closure;
- no immediate failing selected-callee frame/state/effect mutation;
- ancestor frames persist ordinary failed snapshots for deeper failure;
- sticky projection failure bypasses routing/continue and exits containers;
- finalization failure remains supplemental and cannot replace root diagnostic;
- one-level and two-level current-callee ownership.

### Architecture checks

- no receipt symbols;
- no imported ambiguity reason;
- loader rejects duplicate import aliases before resume;
- classic YAML duplicate-key/import-boundary loader tests prove last-wins is no
  longer accepted;
- no pre-publication seam;
- no evidence reader/name/suffix/family predicate;
- schema remains `2.1`;
- focused, smoke, and broad suites pass.

## Declarative Acceptance / Integration Scenarios

| Scenario | Expected result |
| --- | --- |
| Valid root resume | Early CLI audit passes; executor independently passes checksum/audit; prologue continues |
| Initial CLI root checksum mismatch | Exit `1`; persisted run tree remains byte-identical; no session/executor |
| Direct root-executor checksum mismatch | Structured `workflow_checksum_mismatch`; status/error/updated_at only; failed result before prologue/audit |
| Source race after CLI checksum precheck | Root executor catches mismatch; CLI exits `1`; opened session closes failed without replacing diagnostic |
| Identity race after early CLI root audit | Checksum remains compatible; executor second audit records only status/error/updated_at, preserves opened session/process metadata, returns before prologue, and session closes failed without replacing diagnostic |
| Child executor starts after enclosing audit | Child skips root checksum/audit structural guard; no bypass flag/receipt |
| Stale root completed ID | Early root failure; only status/error/updated_at change |
| Optional completed/skipped/failed step-result ID absent | Existing schema-supported fallback; field remains absent |
| Optional supported running loop-frame/result ID absent | Existing schema-supported fallback; field remains absent |
| Missing current-step ID | `missing_required_identity`; no omission fallback |
| Pre-v2.0 state | Existing schema rejection |
| Pre-`2.1` reusable-call state | Existing schema rejection |
| Valid loop progress/ID | Exact candidate resolves |
| Terminal-success repeat resume | `current_iteration: null`, final completed/evaluated iteration, last result true, not exhausted; accepted |
| Successful exhausted repeat resume | Declared max completed/evaluated, last false, exhausted true, repeat completed; accepted |
| Failed exhausted repeat resume | Declared max completed/evaluated, last false, exhausted absent/false, repeat failed with `repeat_until_iterations_exhausted`; accepted |
| Malformed/conflicting loop progress | Stable shape/progress reason; no candidates generated |
| Valid loop progress with stale loop-local explicit ID | Exact generated candidate is absent; projection failure occurs before effects with no parsing/backfill |
| Valid loop progress with stale loop-contained call boundary | Exact boundary candidate is absent; projection failure occurs before call effects with no parsing/backfill |
| Valid completed frame history | All completed frames validate and none is resumable |
| Valid one-level running frame | Caller/alias/boundary resolves; selected independent of map position |
| Valid two-level running frames | Each parent owns its local frame and selected callee audit recurses at the reached boundary |
| Missing call boundary | `missing_call_boundary` at scope entry |
| Ambiguous call-boundary projection candidates | `ambiguous_call_boundary` at scope entry |
| Unique failed non-Workflow-Lisp frame | Resumed and checksum/local audited |
| Workflow Lisp failed retry history, no running member | Every predecessor checksum/local audit passes; deterministic next unused retry ID allocated |
| Workflow Lisp running member plus failed history | Running checksum/resume-bound passes first; then every failed predecessor checksum/local audit; then running local audit/resume |
| Running Workflow Lisp checksum mismatch plus stale predecessor | Running checksum mismatch wins; predecessor history is not audited |
| Workflow Lisp stale failed predecessor | Running resume or fresh retry denied with checksum or projection diagnostic |
| Workflow Lisp multiple running/mixed lineage/duplicate ordinal | Ambiguous or unsupported failure; no allocation |
| Non-Workflow-Lisp multiple non-completed frames | Ambiguous failure |
| Stale parent caller/alias | Root/local scoped failure; no fresh frame selected |
| Missing imported bundle | Failed call result before checksum/child |
| Classic YAML duplicate authored import alias | Loader rejects before bundle construction instead of previous silent last-wins; runtime ambiguity reason is unreachable |
| Workflow Lisp duplicate authored import alias | Existing duplicate-alias diagnostic rejects before bundle construction |
| Callee checksum mismatch plus stale local ID | Existing checksum error wins; local audit not run |
| Checksum repaired, stale local ID unchanged | Projection error now wins after checksum |
| Callee-local projection failure | Exact diagnostic becomes current parent failed call-step/scope error and reaches root; selected callee frame/state/effect absent |
| Two-level nested callee projection failure | Exact diagnostic remains unchanged through both calls; ancestor frame snapshots persist; immediate failing callee absent |
| Projection failure with authored failure/success/always routes or `on_error=continue` | Ordinary failed records persist, routes/continue are bypassed, and scope terminates failed |
| Projection failure inside loop/container | Container propagates immediately without another iteration/branch |
| Projection failure plus configured finalization failure | Finalization may run; its failure is supplemental and original projection diagnostic remains root error |
| Early root failed status with unchanged running current step | Status/report show run error; heartbeat/stall do not treat step as live; repaired resume reruns all guards |
| Session closure after nested failure | Root projection diagnostic remains unchanged while session closes |
| Retirement evidence tripwired | CLI/direct/call behavior never reads it |

All integration scenarios use real bundles, state managers, and public
CLI/executor/call boundaries. Unit-only helper tests do not substitute.

## Success Criteria

The design was accepted after independent reviews confirmed:

- actual call ordering and checksum precedence are preserved;
- root and nested failure envelopes are distinct and complete;
- root-manager executor checksum/audit rerun has no bypass or receipt and child
  executors skip it structurally;
- initial and executor checksum mismatch envelopes remain distinct;
- frame classification covers completed/non-Workflow-Lisp/Workflow Lisp
  retry-lineage behavior;
- optional-ID lane is exact;
- loop progress validation is complete;
- diagnostic null/field-presence contract is exact;
- direct checksum path is authoritative and distinct;
- nested diagnostic value is unchanged through ancestor promotion;
- failed-root forensic current-step semantics are tested;
- schema remains `2.1`;
- no evidence/name/family coupling exists; and
- all declarative scenarios route to executable proof.

## Stop / Revise Criteria

Stop and revise if:

- implementation needs to move callee audit ahead of actual call lifecycle;
- existing checksum or resume-bound error precedence changes;
- executor root checksum/audit can be bypassed;
- child executors require a bypass flag to avoid root revalidation;
- anti-TOCTOU requires a receipt;
- parent ordinary nested-failure persistence cannot preserve root diagnostic;
- the immediately selected callee frame/state changes before local audit
  succeeds;
- legitimate retry state cannot be represented by one typed lineage;
- failed retry history cannot be checksum/local audited after running guards
  but before running local audit/resume, or before fresh retry;
- loop identities require caller-side parsing;
- optional omission cannot be derived from recognized step-result schema and
  existing fallback support;
- exact diagnostic fields/nulls cannot be preserved;
- schema bump/remap/backfill is required; or
- runtime requires evidence/name/family selection.

## Documentation Impact

This accepted design owns scoped insertion, checksum/audit precedence, frame
classification, failure envelopes, diagnostics, and schema decision.

Follow-on work updates:

- `specs/state.md`;
- `specs/acceptance/index.md`;
- the runtime implementation plan;
- runtime/operator docs for forensic current-step semantics; and
- routing/status surfaces after review and implementation evidence.

## Implementation Handoff

Suggested phases:

1. RED classic YAML duplicate import-alias/key loader tests and rejection.
2. RED projection/loop shape-domain-reverse-resolution tests.
3. Projection slot APIs and boundary alias metadata.
4. RED exact frame-classification/retry-lineage matrix.
5. Typed frame/lineage index with bundle-derived Workflow Lisp capability.
6. Pure scoped auditor and exact diagnostic schema.
7. Early-root three-field recorder plus forensic status/current-step tests.
8. Early CLI audit and root-manager-only executor provenance checksum/audit
   rerun plus structured checksum mismatch.
9. Call adapter inserted in actual `execute_call` order, including failed
   lineage checksum/audit and typed retry allocation.
10. Sticky typed-result classification, unchanged nested promotion, ancestor
    persistence, routing/continue/container bypass, and finalization/root
    epilogue/session-close tests.
11. Recursive, loader structural-impossibility, no-receipt,
    no-evidence-read, smoke, and broad verification.

Likely runtime files:

- `orchestrator/loader.py`
- `orchestrator/workflow/state_projection.py`
- `orchestrator/workflow/resume_projection_integrity.py` (new)
- `orchestrator/workflow/calls.py`
- `orchestrator/workflow/call_frame_state.py`
- `orchestrator/workflow/executor.py`
- `orchestrator/cli/commands/resume.py`
- `orchestrator/state.py`
- loader tests and the three characterization test modules

No workflow source, evidence record, or unrelated resume refactor belongs in
scope.

## Open Questions

None. Independent specification, architecture, and quality reviews approved
the complete document; the closed choices above are accepted.

## Appendix: Characterization-To-Proposed-Target Delta

| Characterized behavior | Proposed target |
| --- | --- |
| Root stale ID fails after CLI/prologue mutation | Early CLI root audit; executor rerun before prologue |
| Completed stale/mismatched ID passes | Exact owning-slot validation |
| Qualified APIs are forward-only | Projection-owned validated reverse slot index |
| Duplicate non-completed frames select by map order | Exact target-specific cardinality/lineage classification |
| Failed Workflow Lisp frame retries/resumes without validating history | Typed lineage; running checksum/bound guards first, then history before running local audit/resume; history before fresh allocation |
| Stale caller starts fresh child | Caller/boundary/alias validation prevents accidental selection |
| Callee checksum rejects before child | Existing actual boundary/order and error retained |
| Callee-local stale ID mutates child frame | Exact diagnostic promotion; immediate callee absent, ancestors persist normally |
| Root failure marks current step failed | Early recorder leaves current step forensic; root error/status are authoritative |
