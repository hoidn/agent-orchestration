# Workflow Lisp Provider Prompt Queue

## Scope And Authority

This is the target design for **sequential turns in one native provider
session**, with `prompt-queue` as the bounded authoring surface. It is not
implemented syntax. Selection, delivery limits, and evidence disposition
belong to [PQ-1 in the evaluated-execution roadmap](../plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md#pq-1-sequential-native-session-turns).

This revision supersedes the earlier design's unconditional whole-queue
replay, lack of durable turn progress, and claim that dynamic length is
inherently incompatible with the runtime. It retains one logical provider
operation and one final typed result. Atomic result publication does not
make the agent's filesystem/tool effects transactional.

Governing contracts:

- [Evaluated execution](workflow_lisp_evaluated_execution.md), especially
  effect inputs/identity and the coordinator protocol in §9.3.
- [Provider Context Values](workflow_lisp_provider_context_values.md):
  portable history and native continuation are different capabilities.
- [Phased Contract Delivery](workflow_lisp_phased_contract_delivery.md):
  its task/materialization policy is not a general authored queue.
- [Providers](../../specs/providers.md), [Step IO](../../specs/io.md) and
  [State](../../specs/state.md): current normative behavior remains unchanged
  until a separately selected implementation amends it.

## Purpose And Alternatives

A caller supplies several instructions up front but wants the provider to
receive each only after finishing the previous turn. For example: investigate
a requested repository change, implement it, then self-review the result.
The self-review is not an independent reviewer.

| Approach | What it supplies | Boundary |
| --- | --- | --- |
| One combined prompt | One ordinary call | The agent sees all stages immediately; instructions do not enforce separate turns |
| Sequential calls with portable Context | Explicit, reusable, inspectable history; fresh calls can branch | Rebinding quoted history does not continue the native session; each call has a result contract |
| Native sequential turns | Delayed delivery in the same conversation, with only one final result contract | Requires a session-capable adapter and an explicit recovery contract |

Use ordinary context passing when it suffices. Native turns add conversation
continuity, not merely shorter syntax. Neither session reuse nor a queue
promises lower token cost, preserved hidden reasoning, or better task quality.

## Authoring Contract

Proposed example; `providers.agent`, the prompt externs and `ChangeOutcome`
would be declared by the consumer:

```lisp
(provider-result providers.agent
  :prompt (prompt-queue
            prompts.investigate
            prompts.implement
            prompts.self-review)
  :inputs (inputs.task)
  :returns ChangeOutcome)
```

The caller receives `ChangeOutcome`, not a session handle or a list of turn
results. No intermediate typed acknowledgment is required. The runtime waits
for a successful provider-native **turn boundary**, not a timeout, stdout
silence, or the model claiming that it is finished. This does not prove that
the turn's requested task was done correctly.

The bounded first delivery uses:

- One provider binding, model/effort policy and workspace for the whole call.
- A nonempty, explicitly enumerated sequence of existing prompt externs
  (`input_file` or `asset_file`) and an explicit final `:returns` contract.
  This avoids silently stripping intermediate typed-fragment output
  obligations. Queue items with `defprompt` output positions or result
  guidance need a reviewed composition rule before admission.
- Existing procedure, generic specialization and control-flow placement for
  the admitted provider form. No entry-root-only or positional exception is
  introduced for queues.
- One private native conversation; at most one turn is active at a time.
  A single-item queue uses the ordinary single-prompt path exactly, without
  allocating session machinery or requiring session support.

Before selection, PQ-1a must settle whether the existing `:timeout-sec`
bounds a complete multi-turn attempt or each turn, and how it applies to
resumed attempts. Neither multiplying the caller's budget by queue length
nor introducing new timeout knobs is implicit in this proposal.

A finite enumerated sequence is a first-delivery scope choice, not a language
principle or a consequence of the old flat runtime. Bounded computed queues,
typed prompt fragments and conditional follow-up can be reconsidered when a
consumer needs them; use ordinary expression/list/procedure mechanisms where
they fit. Do not invent a second programming language inside a queue.

External enqueueing, an agent mailbox, concurrent senders, provider switching,
exported mutable session handles, combined queue/context capture, and automatic
same-session materialization repair are outside this contract. They are not
prerequisites for native sequential turns or for portable context delivery.

## Turn Delivery And Result Authority

1. Prepare the declared prompt sources and bindings through their existing
   owners. Keep their snapshots stable for this logical operation; future
   turn payloads may be held by the runtime but are not sent to the provider
   ahead of their turn. This is a delivery rule, not a claim that an agent
   with repository tools cannot read a prompt's source file.
2. Deliver the first prompt with the call's shared input/dependency
   injections. For a multi-item queue, suppress the generated result
   contract and do not expose the final result-path binding.
3. Record successful completion before delivering the next prompt. Append
   that prompt to the same native conversation. Do not repeatedly inject the
   shared context or interpret an assistant's text as a queue command.
4. Only the final turn receives the generated result contract and its
   runtime-owned result destination. Validate the result and declared
   artifacts using the ordinary output owner before publication.
5. Publish one typed result to the caller. Intermediate assistant text and
   transport records are observations, not typed workflow results.
   Intermediate turns may still use tools and change workspace files.

Provider completion metadata and process outcome jointly decide intermediate
turn success; process exit zero alone is insufficient. Failure stops delivery
of later prompts and reports the turn index and source location. Final output
acceptance follows the owning result contract, not a new queue-only parser.
There is no fallback that concatenates the queue into one prompt.

The first delivery adds no automatic extra conversational repair turn after
a failed final result. Any later repair policy must be explicit about whether
the task may be repeated and reuse the existing delivery/validation owners.

## Language And Runtime Architecture

`prompt-queue` groups prompt sources in the existing `provider-result`
prompt slot. It is not a general queue expression, a new workflow kind, or
a second set of model/effort/result declarations.

The closed program retains ordered prompt plans and per-item provenance in
one provider effect. Membership, order, contents and bindings are semantic
program/input data: changing them must participate in the normal program and
resolved-input checks. The result type and ordinary provider effect remain;
this does **not** imply unchanged program digests or resume compatibility
after editing the queue.

Reuse the existing owners:

| Responsibility | Owner to reuse or extend |
| --- | --- |
| Provider binding and invocation | `ProviderSessionSupport`, `ProviderSessionRequest`, and `ProviderExecutor` in `orchestrator/providers/` |
| Native identity and completion decoding | `orchestrator/providers/session_transport.py`; identity alone is not a durable cursor |
| Prompt sources, dependency snapshots and final contract | Existing prompt composition/dependency/result-contract owners |
| Interactive turn delivery, if selected | `InteractiveTerminalTurnQueueAdapter` in `orchestrator/providers/interactive_terminal.py`; not a new terminal driver |
| Final result publication and resume | Evaluated execution's effect memo and coordinator protocol |
| Progress observations | Existing run/attempt storage and reporting conventions, not another session database or dashboard |

Start with one proven native fresh/resume transport. Session identity and
turn completion must be structural adapter capabilities, not provider-name
branches. Fresh/resume support does not by itself prove crash recovery.
Implementing both process-per-turn and persistent-process transports is not
a first-delivery requirement.

A small coordinator owns turn order and durable progress; it must reuse
transport and parsing rather than introduce another session manager.
The phased-delivery coordinator's task/materialization policy remains
distinct. Shared primitives are reused where proven; converting every
existing coordinator into a new generic framework is not a prerequisite.

## Recovery Contract

The queue has one caller-visible final result but records turn progress.
Keep only what recovery needs through the coordinator's attempt storage:
the operation/attempt binding, private session locator, ordered turn
starts and validated completions, plus final settlement evidence.
Transcripts remain observations; they cannot replace those records.

| State at interruption or failure | Required behavior |
| --- | --- |
| Before the first turn starts | Start normally |
| A successful prefix is durably recorded; the next turn has not started | Continue at the next turn only when the adapter can verify continuation of that recorded conversation |
| A turn started but has no durable successful completion | Do not infer success or resend blindly. Reconcile a provider receipt if the adapter can establish it; otherwise report an unresolved turn and stop automatic continuation |
| Native session is missing, advanced unexpectedly, or cannot be verified | Report the continuation failure; do not silently create a fresh session or substitute portable history |
| Final result prepared but not committed to the parent memo | Recover through the agreed coordinator protocol; an on-disk result file alone is not commit authority |
| Final result committed to the parent memo | Reuse it, complete settlement if needed, and send no further prompt |

Never redeliver a durably completed turn as automatic recovery of that queue.
An explicit decision to rerun the logical operation must be surfaced as a
new attempt under the owning retry policy, not disguised as continuation.
It may repeat tool work and does not roll back workspace changes.
An unresolved or failed turn is not automatically restartable merely because
the enclosing provider operation has no final result yet.

This requires a **bounded refinement of evaluated-execution recovery**, not
an assumption that the current protocol already supplies it. Its K4 rule
discards an uncommitted coordinator preparation and restarts a child; that
rule cannot be inherited unchanged for a retained native turn prefix.
Before implementation selection, specify how the same operation's turn
progress survives parent attempts, how abandoned preparations are treated,
and how final prepare/commit/settle stays consistent with K2–K5.
Do not edit the running first-release implementation to make room for this
later class. If the adapter cannot support the required distinction, revise
the design or retain a clearly diagnosed recovery limitation; do not claim
seamless continuation or default back to whole-queue replay.

## Feasibility Prerequisites

These are proof obligations, not claims that the complete queue works because
adjacent facilities exist. Their current disposition belongs in PQ-1.

- **Delivery:** one existing adapter exposes a unique native conversation,
  a successful natural turn boundary, and append-to-that-conversation.
  Three prompts arrive separately and in order; the second cannot arrive
  while the first is processing.
- **Recovery:** distinguish a recorded successful prefix from an uncertain
  in-flight turn. Prove continuation after a committed turn without
  redelivery; expose the missing-session and unresolved-turn outcomes.
  A session ID and a local counter alone do not establish this.
- **Coordinator integration:** demonstrate the K4 refinement and both
  final-result commit gaps through public run/resume; old classes retain
  their contracts. Specify the minimal additional progress facts instead
  of cloning the memo or storing rendered run state.
- **Authoring and composition:** a generic helper containing the queue works
  in admitted call/branch/loop positions. Prompt extern source kinds,
  input/dependency snapshots and final output validation survive closure.
  Any proposed broader prompt surface must preserve its typed output
  obligations rather than silently remove them.

Failure here is a reason to improve the relevant adapter or revisit a design
assumption. It is not proof that native conversation continuity has no value,
nor permission to keep adding parallel mechanisms without a consumer.

## Verification Strategy

Use one maintained consumer and its normal tools: investigate → implement →
self-review. Keep any independently reviewed outer workflow independent.
Compare with context passing only to identify practical differences and
authoring friction, not to require a new scored research study.

The minimal evidence includes:

- Public compile, run and resume of the consumer, with invocation counts,
  ordered delivery receipts and stable native conversation identity.
- An interruption after each completed turn, plus an unresolved in-flight
  interruption and a lost native session. Assert the recovery table, not
  automatic replay. A committed final result causes zero further turns.
- Delayed delivery, shared injections once, final result binding only on
  the final turn, and no premature publication. Assert structured invocation
  bindings and receipts, not literal prompt wording.
- Single-item compatibility and omitted-queue compatibility; empty queues
  and unsupported capabilities/forms produce located diagnostics before
  launching anything.
- One real supported-provider run in addition to deterministic stand-ins.
  Report recovery/adapter limits and actual usability; fake transport success
  is not evidence of native session persistence or task-quality improvement.

## Compatibility And Documentation

This is a later evaluated-execution capability, not an extension of its
first-release portable provider subset or a new feature on the retiring
flat runtime. Select its admission target in the implementation plan; do
not infer admission at target 2.35 from the existence of a proposal.

Existing ordinary, portable-context, phased, supervised and peer-group calls
keep their contracts. Combining them with queues needs an explicit composition
design; a queue is not automatically eligible for each specialized mode.
No YAML authoring surface or public session-ID plumbing is introduced.

At implementation, amend the frontend/closed-program contract and
`specs/providers.md`, `specs/io.md`, `specs/state.md` and
`specs/versioning.md`, including the scoped coordinator-recovery refinement.
Update the drafting guide and capability catalog only to the extent proved.
Roadmap entries and discovery links do not make the example runnable.
