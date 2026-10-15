# Workflow Lisp Value And Continuation Composition: Historical Sections

Status: **Historical.** Extracted original sections; original tense, review
labels, measurements and acceptance language are evidence, not current
authority or permission to execute/select work. Current owner: [workflow_lisp_value_and_continuation_composition.md](../../design/workflow_lisp_value_and_continuation_composition.md).

## Increment 4: Portable Provider Context, Before Native Continuations

Implemented at target 2.31 for the supported ordinary Codex codec. The
[owning contract](../../design/workflow_lisp_provider_context_values.md) distinguishes this
slice from native/cross-provider proposals; the plan records actual usage limits.

Use the existing provider-context contract, beginning with ordinary calls and
portable capture/bind. Do not create a second memory API. The initial supported
content and coverage must be explicit, and capture must come from the adapter's
exposed conversation, not a model-authored approximation labelled as history.

Within that supported scope, a procedure receives context and returns both result
and context; another procedure can transform, branch, and bind the captured value
to a declared provider. The runtime owns the result/context pair and existing
storage owns its content. An unchanged call does no capture. A summary remains
an explicit lossy transformation; a context reference remains distinct from the
filesystem or a mutable session ID.

Prove a real capture and destination binding first, then ordinary imported
arguments/returns, aggregates, loop carriage, and two consumers of the same
snapshot. A different provider requires separate real transfer evidence. Report
unsupported content or explicit conversion; do not silently discard it. Use
increments 1–3 only where those actual compositions require them. Do not force
all context work to wait for every unrelated language improvement.

Native checkpoint capture/fork is a separate follow-on under the same owner,
not a prerequisite for useful portable context. Neither representation gets a
root-only exception that masquerades as a first-class value. Remove superseded
handoff packaging where capture genuinely replaces it; keep artifact handoffs
when they are simpler or carry information the provider never exposed.

## Increment 5: One Human Question As A Host Interaction

This is a new capability, unlike ordinary value composition. The target is one
host-mediated request operation: ask a question, wait without a live provider
process, receive an answer or explicit cancellation, and continue the same
workflow at that expression. Initial replies are text, with a distinct cancelled
outcome; structured forms and multiple simultaneous requests are not required.
The target permits one outstanding request per root at a time; sequential
questions are allowed after the previous request is consumed. An overlapping
request must be diagnosed, never silently replace the pending question.
The operation and its ordinary reply union must compose inside a procedure and
loop, not only at an entrypoint.

The implemented source spelling is `(request-input question)`, where `question`
has exact type `String`. It returns the ordinary closed builtin union
`HumanReply = ANSWERED(text String) | CANCELLED`. Astra reviewed this preparation
contract. Target **2.32** is admitted after the portable-context target 2.31.
Public CLI tests cover imported conversational loops, answer/cancel recovery
after downstream failure, and interruption after consumption before checkpoint
publication. The state/CLI/frontend specifications own current behavior.
Model it as one recorded `host-input` effect
through the normal compiler/runtime path, not a provider impersonating the user,
a busy polling workflow, or a hidden task scheduler.

The runtime records the pending question against its existing run/frame/visit
identity and suspends the run. Reuse the existing suspended run status and state
store where feasible; a pending request is not a crash or failed provider call.
The host lists the pending question and submits a response for that exact
request through one runtime API. CLI and interactive-agent integrations are
clients of the same API, not separate implementations. No new web UI is needed.

Response submission records data; ordinary resume continues execution. Resuming
without a response leaves the request pending. An identical repeated submission
is idempotent; a conflicting or stale response is rejected without overwriting
the accepted one. Once consumed, the reply is an ordinary value and completed
upstream work is not replayed. Cancellation is a caller-visible outcome, not an
invented answer. A request inside a loop has a distinct visit on each iteration.

The question cannot mutate the original run inputs or program identity. The
workflow explicitly incorporates the answer into its next brief/context value.
This distinguishes conversational continuation from changing an old checkpoint.
No arbitrary call-stack serialization, approval framework, or event bus is part
of the design.

### Reviewed Preparation Contract

Use one new leaf operation, `request_input`, with a typed question source and
the fixed reply contract. Thread it through the existing expression, inferred
effect, WCC perform, executable validation, and dispatch owners. Do not encode
it as a provider or a command. The new unparameterized effect follows the
existing subject-free effect pattern; this is not an effect-ledger redesign.

The concrete leaf contract below passed Astra re-review. Keep the operation
name `request_input` consistently through WCC and shared executable views; the
source/effect spellings remain `request-input` / `host-input`. WCC carries the
question as its ordinary typed positional operand. Before the atomic WCC boundary,
elaborate the question through existing body/prebinding and continuation
sequencing, retaining any prefix from a procedure call, `let*`, or control form.
The existing atomic elaborator rejects such prefixes, so later ANF alone is not
sufficient. Then use ordinary ANF/projection to obtain the literal/ref leaf.
Its existing result-type metadata identifies
the fixed builtin union; do not add a second descriptor payload when it can be
derived there. The shared leaf config is exactly
`request_input: {question: {literal: String}}` or
`request_input: {question: {ref: String}}`, using existing reference resolution
and dependency discovery. Validate exactly one source and its runtime String
value. No prompt template interpolation, provider options, bundle destination,
or per-question result type is involved.

Use the ordinary union artifact projection for the fixed reply: an answered
result exposes `variant = ANSWERED` and `text`; cancellation exposes only
`variant = CANCELLED`. The runtime validates the reply with the existing typed
value validator before atomic finalization. Compiler terminal refs and active
union metadata follow that same existing projection. The builtin type and
reserved form are target-gated, and the inferred `HostInputEffect` follows the
subject-free `RunsTrialEffect` pattern; its optional declared spelling is
`:effects ((host-input))`.

Extend the existing compiled-node result-contract owner for this bundle-free
operation: the fixed `variant` contract admits only `ANSWERED`/`CANCELLED`, and
`text` is String in the answered case. Member admission, durable dependency type
validation and value retrieval must use that contract, not just an artifact-name
allowlist. Validate the complete active reply before consumption; cancellation
never synthesizes or dereferences `text`. Preserve `returned_union_type_name`
and active-variant metadata through ordinary terminal binding. No provider bundle
or serialized descriptor payload is needed. Astra identified these replay and
pre-atomic sequencing obligations in its leaf-contract review.

Concrete propagation owners include the expression registry/traversal and type
prelude, WCC elaboration/defunctionalization, a leaf lowering function, shared
surface/core/executable types and conversions, persisted-surface encoding,
runtime-plan views, semantic coherence and dependency validation, and ordinary
plus loop executor dispatch. Use one operation-specific config, not fields on
all common step configuration. Register 2.32 only with the implemented capability;
an unimplemented intervening target must not be admitted merely to fill a number
gap. Input command registration lives in the existing CLI parser/dispatch and
commands package; it remains a thin client of the single runtime API below.
The explicit propagation map includes `workflow/elaboration.py`,
`workflow/runtime_plan.py`, `workflow/runtime_step.py`, `wcc/anf.py`, and
`workflow/pure_result_replay.py`; state serialization must handle the optional
root field in both `to_dict` and `from_dict`, omitting it when absent.

The read-only persisted workflow graph is a closed encoding, so this new leaf
requires `persisted_workflow_surface_graph.v6`; do not add it to v5 silently.
Select v6 exactly when a reachable step, nested body, finalizer or imported
workflow contains `request_input`. Otherwise retain the existing v5/v4/v3/v2/v1
selection and bytes. Unused imports do not select v6. Reachability includes all
retained control branches and actual transitive calls, independent of eventual
execution; existing unreachable-node rejection stays in force. The operation
map is required on `REQUEST_INPUT`, forbidden on other kinds, and gated by the
containing workflow node's target 2.32+, not just the entry's target. Reject null,
extra keys, both/neither sources and non-string payloads. A request-only graph
needs no provider context. Decoder shape, kind, target and graph-schema selection
must agree; diagnose `request_input_persistence_mismatch` before generic key
rejection hides that reason. Mixed
graphs retain provider-context, trial and Q2/Q3/Q5 carriage without relaxing their
individual contracts. This extends the graph reader, not the run-state schema,
question store or execution authority. Astra approved this bounded encoding
amendment; implementation and public target admission remain separate.

The authoritative root `RunState` has one optional `human_input` record, omitted
for old runs and unused workflows. It contains a persisted opaque request ID,
the existing root/frame/runtime-node/visit/loop identity, question text, status
(`pending`, `answered`, or `consumed`), and an optional typed reply. A UUID
allocated once at durable creation suffices; deriving another identity hash or
keeping a request registry is unnecessary. The existing state schema remains
compatible through this additive optional field; source and lowered admission
require the eventual selected target.

The closed record uses `request_id`, `resume_scope` (the existing
`{root_workflow_file, call_frame_ids}`), `runtime_step_id`, `enclosing_step`
(`{step_name, step_id, visit_count}`), `loop_iteration` (null or existing
`{kind, loop_step_id, iteration}`), `question`, `status`, and optional `reply`.
Reply is absent while pending, otherwise exactly the approved tagged answer or
cancellation. The containing root supplies run identity; nested states may not
own this field. Existing frame snapshots/cursors/visits remain ancestor authority,
not another copied suspended-stack record. Aggregate ownership validation alone
does not prove execution position: resume must also validate reached calls
against parent visits and loop progress before reusing them.

Retain the latest consumed record until another question replaces it. This
gives a bounded idempotency window: the identical reply to that latest request
is accepted even after consumption, while a conflict rejects. Once the next
request exists, earlier IDs are stale. An outstanding unanswered or answered
request cannot be replaced by a different request. Reaching the same suspended
leaf reuses its persisted identity and question; it does not create another
visit or silently change the question.

Use the existing root writer lock and aggregate-state transaction owner. One
transaction publishes the request, preserves the reached cursors, and marks only
the root run suspended. Reached child frames retain their existing incomplete
`running` status and cursors: they are resumable stack frames, not independently
running processes. The root request names the waiting leaf. This preserves the
existing same-frame retry-lineage selection without adding another frame status.
Submission reloads state under the
root writer lock, validates the exact request ID, and records an answer or
cancellation without running the workflow. Consumption publishes the ordinary
leaf result and marks that request consumed in one aggregate-root write. A
crash must not produce a consumed request without its result or expose an
unpersisted question. Nested state is already root-aggregated; do not add a
second request file, lock service, or independent frame-state authority.

Extend `StateManager._mutate_scoped_state` at its existing traversal owner to
accept root scope and a callback over the candidate root and reached state
chain; its present leaf-only, nonempty-path API cannot perform this transaction.
Reuse the aggregate ownership checks rather than treating their mutation lock
as a persistence transaction. Finalize a loop leaf using the existing
iteration-qualified result placement and dataflow rules inside the same write.
Do not return a result for later generic publication after marking it consumed.
Refresh live call-frame managers through the existing root-refresh helper after
success or rollback. After consumption, refresh the active deep-copied executor
state and retained call-frame projections before ordinary finalizers can publish
stale values. Suspension unwinds without further publication.

The reviewed private transaction interface retains the existing leaf
`commit_guard` and accepts exactly one of `mutation(leaf)` or
`scoped_mutation(candidate_root, reached_chain)`. Root scope is permitted and
has chain `(candidate_root,)`. Clone, traverse once, guard, mutate candidates,
rebuild bottom-up and write once. Callbacks never write or execute work.
Extract one non-writing `_apply_result_with_dataflow` helper in `state.py` and
route existing ordinary/loop/call-frame finalizers through it, preserving their
different guard and cursor-clear rules. Consumption invokes that helper inside
the scoped transaction; it cannot accept an arbitrary completion callback.

`workflow/human_input.py` owns record/query/submit/consume entrypoints.
`record_human_input(manager, ...)` derives scope from the existing aggregate
owner and returns a detached committed request. `get_human_input(run_root)`
reads the atomic snapshot. `submit_human_input(run_root, request_id, reply)`
loads inside the existing writer lock, writes only the accepted reply/status,
and never resumes. `consume_human_input(manager, request_id, *, result,
step_name, loop_name=None, index=None, <existing dataflow arguments>)` requires
an answered exact request, a successful result matching the complete reply,
and correct placement. Existing loop result keys differ from runtime node IDs;
validate both using the existing `IterationStepKeyProjection` and compiled nested
node ID supplied by execution. Check its frame key, presentation name and exact
runtime ID, then use `step_key` for publication; never derive the presentation
name from the runtime suffix. These are execution arguments, not new persisted
request identities. It publishes result/dataflow plus consumed/root-running state
in the same write, returning committed leaf state. Pending consumption fails;
already-consumed calls cannot republish results/dataflow. Re-entry at a consumed
identity uses ordinary completed-result replay, not another UUID.

Reuse existing scope/visit/loop value validators without fabricating a provider
attempt. Keep state-to-operation validator imports function-local. After write
failure reload the actual disk snapshot (a replacement may already be durable);
restore pretransaction state only if no snapshot exists. Refresh originating
call-frame managers in `finally`, after success or failure. Detached executor
state refresh is part of the implemented integration. This Astra-reviewed leaf adds
no independent traversal, store, lock, or generalized continuation service.

Expose a single query/submit runtime API with thin CLI clients:

```text
orchestrator input get RUN_ID
orchestrator input answer RUN_ID REQUEST_ID --text TEXT
orchestrator input cancel RUN_ID REQUEST_ID
orchestrator resume RUN_ID
```

The query returns structured request/status data; answering and cancelling do
not implicitly resume. Empty answer text is valid and differs from cancellation.
All input commands use the existing run lookup and `--state-dir` convention.
An unanswered resume validates the existing run and returns suspended before
the execution prologue can dispatch work. An answered resume reaches the same
leaf, validates its frame/node/visit, and consumes the recorded reply.

Reuse validated visits for every enclosing call/loop on the request's scope
chain before the executor increments visits or starts a new step, not just for
the final request leaf. A loop leaf uses its enclosing cursor/visit and existing
iteration-qualified runtime node ID: nested loop steps have no independent
top-level cursor. Do not put a nested node into top-level `current_step` or
allocate a replacement call frame before matching the pending request.

Propagate a dedicated `HumanInputSuspended(Exception)` through nested execution.
The executor's generic step exception handler must re-raise it without calling
`fail_run`; only the root catches it and returns the committed suspended state,
without a completion/failure epilogue. This bypasses the current child-call
conversion of non-completed results into failures. Calls and loops preserve
their cursors and completed work. Keep SIGINT handling unchanged. This is a
control transfer for one durable operation, not arbitrary stack serialization.

Suspension alone proves none of these paths. Regression evidence covers question/answer, cancellation,
restart while waiting, duplicate/stale submission, and two sequential questions
inside an imported loop without replaying preceding provider calls. Update the
CLI/state/effect contracts together when this new capability is accepted.
Inject failed writes during publication and consumption; assert no consumed
record lacks its finalized result. Check root suspension, running child frames,
and unchanged ancestor/leaf visits and frame IDs across unanswered and answered
resume. Keep existing checksum and bound-input validation intact.

Completed replies use the existing lexical checkpoint mechanism, with one
closed `reuse_validated_human_reply` policy (Astra-reviewed integration amendment,
2026-09-22). Its only requirement is
`human_reply: {result_contract_digest: ...}`, derived from the fixed reply
contract; both effect and boundary kinds must be `request_input`. A completed
reference contains the existing base identity, `evidence_kind: human_reply`,
the fixed contract digest and the canonical digest of the complete committed
artifact mapping. Reuse existing checkpoint scope/frame/iteration identity;
do not copy the request record or reply into another store or invent a bundle.

Collection prefers the committed leaf result supplied by the atomic finalizer.
Authoritative validation resolves the exact runtime node/visit in the validated
scope through existing state/iteration projections, requires one completed
candidate, validates the complete `HumanReply`, and compares both digests.
Neither a matching display name nor the highest visit is sufficient. The latest
root request is not historical authority: a later question replaces that record,
but does not invalidate earlier durable replies. Missing or mismatched evidence
fails closed; pending/answered requests retain the dedicated host-resume route.
No existing provider/command policy is repurposed: those require real bundle
evidence, whereas a human reply is a bundle-free durable value.

Admission evidence includes a provider-free question followed by downstream failure
and resume, two sequential questions, exact call/iteration identity, malformed
or missing artifacts, and interruption after atomic consumption but before
checkpoint publication. That interruption may recover the durable result or
fail closed, but must never issue a replacement question.

Until then, progressive execution retains its explicit `NeedsInput` return and
new invocation. It must not pretend that current `resume` accepts human answers.
Provider context may improve the information shown with a question, but is not
a dependency of asking one.
