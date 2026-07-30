# Workflow Lisp Provider Live Binding

- **Status:** v1 target-`2.16` supervision and additive v1.1 target-`2.17`
  peer messaging are implemented. Their original interrupted-visit quarantine
  sections describe the pre-ML behavior and are superseded by the normative
  at-least-once contract in `specs/state.md`; ML-1 runtime implementation is
  pending and does not reopen the completed v1/v1.1 feature gates.
- **Kind:** feature / provider observation, bounded concurrency, and
  turn-boundary supervision architecture
- **Owner:** Workflow Lisp frontend + provider runtime
- **Review:** original independent specification PASS and quality APPROVED;
  evidence-driven resume-boundary amendment independently
  `SPEC_COMPLIANT`, quality `APPROVED`, and behavior simulation `PASS` on
  2026-07-23; the initial 2026-07-24 peer-messaging amendment review returned
  `CHANGES_REQUIRED`, and the revised additive design then received
  `DESIGN_SPEC_APPROVED` and ordered `DESIGN_QUALITY_APPROVED`; v1.1
  implementation tasks received ordered specification and quality review
- **Created:** 2026-07-13
- **Last material update:** 2026-07-24
- **Normative recovery note (2026-07-30):** preserve all member, settlement,
  message-ledger, cleanup, and completed-result rules below. Read any
  interrupted-visit quarantine wording as historical design provenance; the
  ML-0 spec pivot replaces only that policy with guarded discard-and-rerun.
- **Related docs / plans:**
  - `docs/design/workflow_lisp_frontend_specification.md`
  - `docs/design/workflow_lisp_executable_ir.md`
  - `docs/design/workflow_lisp_provider_prompt_queue.md`
  - `docs/design/workflow_lisp_provider_peer_messaging.md`
  - `docs/design/workflow_lisp_lexical_execution_checkpoints.md`
  - `docs/design/workflow_lisp_native_transportable_returns.md`
  - `docs/plans/2026-07-23-provider-live-binding-t3-behavior-simulation.md`
  - `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
  - `specs/providers.md`, `specs/io.md`, `specs/state.md`,
    `specs/versioning.md`, and `specs/observability.md`
- **Implementation target:** v1 is complete through `4d4f05c7`; the additive
  v1.1 capability, runtime, target-`2.17` frontend, executable projections,
  and real-provider gates landed in `4f28ffde` through `b08c04a6`

## Summary

One provider invocation cannot currently observe another provider invocation
while both are active, and the only runtime-owned intervention is timeout
termination. The first version of this design proposed ordinary tmux
`send-keys` as same-turn steering. Fresh T3 probes disproved that premise:
Claude queued the message until after the original answer, and Codex required
an explicit interrupt that left the prior tool process running.

This revision follows the roadmap's adverse-T3 stop/revise path. It adds:

1. **One live observation pane per provider invocation.** Existing provider
   pipes and structured transports remain authoritative. A run-scoped tmux
   pane mirrors normalized live output for observation only, so tmux cannot
   alter result bytes, session JSONL, or exit handling.
2. **`with-live-providers`.** The v1 form composes exactly one worker and one
   supervisor as one executable node with one atomic workflow-state/result
   commit. The supervisor observes the worker's pane and returns a
   compiler-owned, validated directive:
   `CONTINUE` or `STEER` with free-form guidance.
3. **One bounded turn-boundary correction.** `CONTINUE` accepts the active
   worker turn. For active-turn cancellation, `STEER` requires one
   codec-validated resume-boundary-readiness snapshot—a unique provider
   session id, an observed provider-specific readiness marker, and no exact
   terminal event—then terminates and reaps the runtime-owned worker process
   group. A worker that completes successfully before cancellation may use
   its complete frozen natural boundary when the unique identity and
   readiness marker were observed. Either path performs exactly one resume
   turn with the guidance. Only the selected completed turn's validated
   bundle can become the worker result.

4. **Recorded peer messaging (owner amendment, 2026-07-24).** The implemented
   additive contract lives in
   `workflow_lisp_provider_peer_messaging.md`: target `2.17` adds a separate
   static peer-group form and node, while target `2.16` and this v1
   supervision contract remain unchanged.

The runtime interprets only the directive discriminant. It never interprets
the guidance, pane text, or provider stdout as workflow data.

## Context And Authority

Verified current behavior this design builds on:

- The workflow cursor is serial. Concurrency must remain inside one executable
  node.
- `ProviderExecutor` has distinct ordinary, streaming, and session JSONL
  execution paths. Their raw stdout, stderr, exit, timeout, and metadata
  behavior is authoritative.
- Current provider `STDIN` mode delivers one initial prompt and closes stdin.
  It is not a live-input capability.
- The builtin Codex templates already declare session fresh/resume commands
  and the metadata mode intended for strict session parsing. The current
  parser is incompatible with the installed real event shape, so the shared
  codec repair remains a T1 prerequisite. Other templates may omit session
  support.
- `StateManager` already serializes its own mutations. The remaining
  concurrency issue is `WorkflowExecutor` ownership: its current step,
  dataflow, provider attempts, sessions, artifacts, and evidence are not
  reentrant.
- Executable IR currently has no provider-group node. Workflow Lisp lowering
  must introduce one through the ordinary WCC/schema-2 route; a
  surface-specific direct lowerer is not permitted.
- The only runtime pure-expression language is the validated
  `pure_projection` payload. An arbitrary effectful last expression cannot
  execute inside one atomic group node.
- Provider-side sessions and live panes are external, non-content-addressed
  state. They cannot be resume authority.

### T3a observed outcome

The pre-plan probe is closed as adverse for direct TTY steering:

- Claude interactive input submitted during a running tool was processed
  only after the original response.
- Codex ordinary input was explicitly queued for after the next tool call.
- Codex Escape plus a new message created an interrupt/new-turn transition,
  while the prior shell tool remained alive in the background.
- `codex exec`, `claude -p`, and the current executor's `STDIN` mode are
  one-turn transports.
- A real installed-Codex JSONL invocation emitted
  `thread.started.thread_id` before `turn.started`, then
  `item.completed`, and finally `turn.completed`. The current parser looks
  only for `session_id` and treats any `*.completed` event as terminal, so
  real-shape canonical identity extraction and exact turn-terminal detection
  are T1 prerequisites.

Therefore ordinary `send-keys` is not steering capability, and client-owned
interrupt acknowledgement is not process-quiescence proof. The detailed
trace and compared alternatives live in the T3 behavior-simulation report.

### Task 3 stop/revise feasibility result

The first real Codex gate exposed a narrower provider boundary than the
identity-only design assumed. The evidence retained here is structural only:

| Installed provider version | Exact event at cancellation gate | Unique identity | `resume_boundary_seen` | `terminal_seen` | Complete owned-process boundary | Same-identity resume succeeded |
| --- | --- | --- | --- | --- | --- | --- |
| Codex `0.145.0` | `thread.started` | true | false | false | true | false |
| Codex `0.145.0` | `turn.started` | true | true | false | true | true |

The first row is the immediate-failure incident: a canonical identity plus
complete cancellation/reaping proof did not make the native session
resumable. The second row proves the narrower feasibility claim used by this
design: cancellation after the exact top-level `turn.started` event, while
the identity remained unique and no exact terminal event had been seen, was
preterminal and resumable. No provider session id, prompt, raw event payload,
or response content is retained in this design record.

Installed `0.145.0` source ordering places `turn.started` after an awaited
persistence attempt/flush, but persistence errors may be logged and swallowed
before event delivery, and no governing provider contract promises rollout
durability at that point. Therefore `resume_boundary_seen` is a necessary
codec-validated boundary-eligibility fact, not proof of native persistence
and not a guarantee that resume will succeed. `resume_boundary_seen` is the
truthful field name: only a successful exact-identity resume proves
resumability. An attempted resume must still match identity, complete
successfully, and validate its bundle; otherwise the group fails with no
output promotion.

## Problem

The system needs a truthful way for a supervisor provider to:

- see another invocation's progress while it is active;
- decide whether the current turn should continue or be corrected;
- deliver free-form corrective guidance without inventing a provider-specific
  UI-key contract;
- prevent an interrupted turn and its replacement from both remaining active;
  and
- preserve one typed, validated result and one atomic workflow-state/result
  boundary.

The mechanism must also avoid making the workflow executor reentrant or
feeding terminal-rendered bytes into strict provider metadata parsers.

## Goals And Non-Goals

### Goals

1. Every provider invocation attempts one addressable live observation pane
   by default; the live-supervision form requires it, while ordinary calls
   degrade to their unchanged provider path if observation is unavailable.
2. A Workflow Lisp form composes one worker and one supervisor concurrently
   after both calls specialize to eligible provider operations.
3. The supervisor can return one validated free-form steering directive.
4. A steered active worker resumes the same provider session only after the
   codec reports a unique, preterminal, resume-boundary-seen snapshot and the
   prior process leader is reaped, its runtime-owned process group is empty,
   and its executor future and capture threads are joined. A clean naturally
   completed worker may use its complete frozen boundary when its final
   identity remains unique and the readiness marker was observed.
5. One coordinator owns all workflow state, checkpoint, dataflow, attempt,
   artifact, and final-result mutations.
6. Results travel only through typed validated bundles. Pane text,
   transcripts, and stdout remain evidence.
7. The form is one atomic workflow-state/result boundary; controller
   interruption quarantines the visit before any later provider launch.
8. Mechanics are structural and never branch on provider, workflow, family,
   module, or domain names.

### Non-Goals

- same-turn steering through any input channel, and unrecorded direct
  `send-keys` by member agents to raw pane ids;
- provider-native duplex protocols such as Codex app-server or Claude
  stream-json;
- more than one steering directive or more than one resume turn;
- N-member directive supervision in v1 or v1.1; the v1.1 amendment instead
  adds static cooperative peer groups with no forcing edge;
- dynamic member counts;
- effectful settlement bodies;
- durable live handles or durable provider-native session reuse;
- partial group checkpointing or member-level workflow resume;
- cross-run binding;
- general background launch/join primitives;
- multi-step member procedures; and
- a YAML authoring surface;
- filesystem transactionality or rollback of member workspace writes; and
- process containment stronger than the runtime-owned POSIX process group;
  cgroup, PID-namespace, detached-child, and remote-work containment require
  a separate design.

## Decision

Retain the `with-live-providers` name but narrow v1 to a two-member,
one-direction supervision form. Use an observation-only pane mirror and a
runtime-mediated, typed turn-boundary directive.

### Chosen approach

- provider execution remains on the current pipe/JSONL transports;
- every invocation receives an additional tmux display pane;
- the form has one observed worker and one observing supervisor;
- the supervisor returns `ProviderSteeringDirective`;
- `STEER` requires a codec-validated resume-boundary-seen snapshot, cancels
  an active worker or verifies a clean natural completion, proves the
  runtime-owned leader/PGID/future/capture boundary, and performs one session
  resume;
- a single coordinator aggregates member outcomes and publishes one atomic
  workflow-state/result commit; and
- a validated pure settlement expression determines the form's final value.

### Recorded peer messaging (owner amendment, 2026-07-24)

The adverse T3a result rejected *same-turn* steering; it did not reject
free-form input queued for a later natural turn. A fresh real Codex
`0.145.0` probe on 2026-07-24 confirmed that narrower capability without
Escape, cancellation, or a resume command.

The initial amendment text was nevertheless incomplete: the shipped executor
closes stdin, its observation pane tails a file rather than hosting the
provider, and append-before-delivery proves only a runtime offer rather than
model consumption. It also left readiness, exact attempt attribution,
completion races, teardown, and static N-member settlement unspecified.

The implemented v1.1 decision is therefore additive and is normative in
`workflow_lisp_provider_peer_messaging.md`:

- target `2.16`, `with-live-providers`, and
  `provider_supervision.v1` remain unchanged;
- target `2.17` adds `with-live-provider-peers` and
  `provider_peer_group.v1` for a static `2..8` member group;
- every member uses an explicit provider-neutral interactive queued-input
  capability; neither stdin nor the observation pane implies it;
- `peer-ready`, `peer-send`, `peer-ack`, and cooperative `peer-finish`
  requests round-trip through an exact attempt-bound runtime endpoint;
- the coordinator fsyncs an append-only receiver ledger before offering
  literal text, and distinguishes `recorded`, `offered`, and
  `receiver_acknowledged` without claiming semantic understanding;
- a provider-declared normal close command and full process-boundary proof
  are required before settlement; and
- the peer group has no directive or forcing edge. This v1 `STEER` path
  remains the only successful forcing move.

Mixing queued messages with forced worker replacement is deferred because a
message must never be silently retargeted across provider attempts.

The shipped v1.1 route uses the declared
`interactive_terminal_turn_queue.v1` capability, one attempt-bound local
endpoint per group visit, receiver-owned append-only ledgers, and one
single-writer `provider_peer_group.v1` coordinator. A real one-member adapter
gate plus real two- and three-member peer gates proved natural queued delivery
and cleanup without changing the target-`2.16` `provider_supervision.v1`
artifacts or behavior.

### Alternatives rejected

1. **Ordinary `send-keys` same-turn steering.** Rejected by the T3a behavior
   probe. This rejection covers only the same-turn framing; free-form
   messaging with turn-boundary delivery is in scope through the 2026-07-24
   owner amendment above.
2. **Client-owned Escape/interruption.** Rejected because the observed client
   acknowledgement did not terminate the prior tool process.
3. **Wait for the worker to complete and always steer afterward.** Safe, but
   post-hoc rather than live correction. The selected design may fall through
   to this boundary when the worker naturally completes before the directive,
   but it does not make that the only path.
4. **Provider-native duplex protocol.** Potentially stronger, but it creates a
   separate persistent transport, event, and lifecycle architecture. It is a
   future proposal.
5. **Concurrent calls into `WorkflowExecutor`.** Rejected because the executor
   is not reentrant. Member threads may call only the low-level provider
   executor with immutable prepared requests.
6. **Arbitrary N-member dataflow settlement.** Rejected for v1 because
   steering arbitration, member ownership, and effectful-body lowering are
   not closed.

### Accepted tradeoffs

- tmux is a required dependency for `with-live-providers`; ordinary calls
  retain their provider result when the default observation mirror is
  unavailable;
- a steered first turn may consume time and provider capacity before
  cancellation;
- a provider may expose a stable identity before it exposes a validated
  resume boundary, and providers/codecs without such a marker cannot occupy
  the observed-worker role;
- v1 supports one worker, one supervisor, and at most one correction;
- an interrupted group gets no partial credit and is quarantined rather than
  replayed automatically; and
- the compiler-owned directive introduces a small typed control vocabulary,
  while its guidance remains free-form.

## Authoring And Type Contract

Illustrative surface:

```lisp
(with-live-providers
  ((w (procs.run-migration plan))
   (m (procs.supervise policy)
      :observes w))
  (make-supervised-outcome
    :work w
    :directive m))
```

Binding shape:

```text
(<name> <provider-producing-expression>)
(<name> <provider-producing-expression> :observes <sibling-name>)
```

Rules:

- There are exactly two bindings.
- Exactly one binding declares `:observes`; its peer is the worker.
- A member may be a direct provider-producing expression or a direct
  procedure invocation. Authored `(call ...)` is a workflow boundary and is
  rejected here.
- Both expressions must, after specialization and WCC elaboration, contain
  exactly one unconditional provider perform and a pure return projection.
  Branches, loops, additional effects, private workflow boundaries, and
  residual calls are rejected with source-mapped diagnostics.
- Thin procedures are allowed only when declared `:lowering inline`, because
  eligibility is checked after specialization and recursive inline expansion,
  not inferred from a set-valued effect summary.
- The worker may return any supported transportable type `T`.
- The supervisor must return the compiler-owned
  `ProviderSteeringDirective`.
- The body must lower to the existing validated pure-expression payload over
  `w` and `m`. Residual effects or control forms are rejected.
- The form's type is the pure body's type. For a body of `w`, the form is `T`.
- The form's effect summary is the union of both provider effects plus
  `LiveSupervisionEffect(supervisor, worker)`.
- The form requires target DSL `2.16`; earlier targets reject it.

### Post-specialization member extraction

Thin procedure calls are accepted by normalization, not by treating a
residual `WccCall` as a provider member:

1. Parse and typecheck each binding expression normally.
2. Resolve its monomorphic procedure specialization with the existing
   procedure-specialization environment.
3. Require every encountered procedure to declare `:lowering inline`, then
   inline the specialized callee body into a closed member region using the
   same substitution and source-provenance rules as ordinary inline procedure
   lowering. Recursively normalize eligible inline callees until no
   `WccCall` remains.
4. Accept only a canonical region whose control spine is straight-line
   `WccLet`/`WccHalt`, with exactly one unconditional provider `WccPerform`;
   all other bindings must be pure values/projections that feed that perform
   or project its declared result.
5. Reject `WccCall`, private workflow/call boundaries, `WccCase`, `WccIf`,
   loop/recursion terms, a second perform, or any non-provider effect after
   normalization. Diagnostics point to the original member call and the
   disqualifying specialized form.
6. Extract the provider owner payload and its pure result projection into a
   `WccProviderSupervisionMember`; do not emit the member as an ordinary
   sequential provider step.

The group elaborates to one new closed `WccProviderSupervision` term
containing the two extracted members, observation edge, and validated pure
settlement payload. WCC verification repeats the canonical-shape invariant.
Defunctionalization emits one Core/executable provider-supervision node.
There is no direct surface-to-Core lowering path.

## Steering Directive Contract

`ProviderSteeringDirective` is a compiler-owned tagged union with exact wire
forms:

```json
{"variant": "CONTINUE"}
```

```json
{
  "variant": "STEER",
  "guidance": "Free-form corrective guidance for the next provider turn"
}
```

Validation rules:

- `variant` is required and is exactly `CONTINUE|STEER`;
- `CONTINUE` forbids `guidance`;
- `STEER` requires a non-empty string `guidance`;
- unknown fields are rejected;
- the supervisor's provider contract receives field guidance explaining that
  `CONTINUE` accepts the worker's active turn and `STEER` replaces it at the
  next validated provider-session boundary; and
- the runtime consumes the validated value, not a prompt phrase, stdout
  fragment, pane scrape, or transcript.

The directive remains available to the pure settlement body. Its presence
does not make guidance a public artifact unless the body explicitly returns
it as part of its declared type.

### Language integration

`ProviderSteeringDirective` is a reserved, non-shadowable prelude
`UnionTypeRef`, equivalent to:

```lisp
(defunion ProviderSteeringDirective
  (CONTINUE)
  (STEER
    (guidance String
      :description
      "Corrective guidance for the replacement provider-session turn.")))
```

- The compiler installs and reserves this prelude type only when the module's
  target DSL is `2.16` or later. Such modules may reference it without
  importing or declaring it, and a module definition, schema, type parameter,
  or import alias may not shadow the reserved name.
- Targets below `2.16` neither receive nor reserve the name. They cannot use
  `with-live-providers`, but an existing authored type named
  `ProviderSteeringDirective` keeps its prior meaning.
- Existing `variant` constructors, `match` exhaustiveness, variant proof,
  type compatibility, WCC union carriage, pure-expression handling, Semantic
  IR, and source-map rules apply unchanged.
- The supervisor's provider result lowers through the ordinary
  `variant_output` contract with discriminant `/variant`, a `CONTINUE`
  variant with no payload, and a `STEER` variant requiring `/guidance`.
- The ordinary union validator enforces discriminant, selected payload, and
  forbidden cross-variant fields. Because general union bundles currently
  tolerate unrelated extra JSON keys, the group coordinator additionally
  requires the raw directive object key set to be exactly `{"variant"}` or
  `{"variant", "guidance"}` before accepting it as runtime control.
- The normalized WCC/runtime value uses the existing flattened union members
  `variant` and optional `guidance`; no bespoke control-value representation
  enters the type system.
- Prelude source spans own generated type/contract structure; the authored
  supervisor call and group observation clause remain the source-map owners
  for its use.

## Observation Pane Contract

### Pane identity

- Each successful pane allocation, including the optional worker resume turn,
  owns one distinct pane on a run-scoped tmux server.
- The pane is created before provider launch and destroyed only after the
  invocation is terminal and its transcript is finalized.
- Inside a supervision group, the fresh worker pane is retained until the
  supervisor directive and group are terminal, even when the fresh worker
  exits first, so the supervisor's declared observation target remains
  captureable. Other panes follow their invocation lifetime.
- Invocation-to-pane is 1:1; panes are never shared or reused.
- Live socket and target strings do not enter workflow values, bundles,
  `state.json`, result diagnostics, or later steps. They may appear in the
  supervisor's actual prompt and existing debug prompt/command evidence; such
  evidence is non-authoritative and the address is invalid after teardown.
- The dedicated pane record stores a stable invocation/member/turn identity
  and transcript path, not the live target.

### Non-interference

- Provider subprocesses continue to use the current authoritative stdin,
  stdout, stderr, streaming, and session JSONL paths.
- Existing callbacks append a normalized display stream to a member-local
  display file.
- The pane tails that display file. It is a view over execution, not the
  execution transport.
- Pane failure cannot substitute partial display data for provider output.
- Outside `with-live-providers`, allocation, tail-process, callback, tmux
  server, or teardown failure records observation status and leaves provider
  execution/result semantics unchanged.
- Inside `with-live-providers`, both initial panes are load-bearing:
  allocation failure stops before member launch, and loss while the supervisor
  is still active fails the group and triggers member cleanup. After a valid
  directive is committed to the arbiter, later mirror/teardown failure is
  evidence-only because observation can no longer change the control choice.
- Ordinary provider invocations outside the form also receive a pane. Their
  result, metadata, timeout, and output behavior must remain equivalent to
  the pre-pane path.

The supervisor receives the worker pane's process-local address plus a
runtime-owned observation preamble through a structural prompt-injection
record. Prompt-audit evidence records that the observation injection occurred;
tests do not assert literal prompt wording.

## Provider Capability Contract

The worker template must opt in structurally through:

```yaml
session_support:
  # existing metadata_mode, fresh_command, and resume_command
  turn_boundary_resume: true
```

Presence of `turn_boundary_resume: true` is valid only when:

- `fresh_command` and `resume_command` are present;
- the resume command contains exactly one `${SESSION_ID}`;
- neither command contains the exact `--ephemeral` argument;
- the selected metadata codec can report exactly one stable session id and a
  validated resume-boundary marker before the fresh process becomes
  terminal;
- a resume result is checked against the requested session id; and
- the invocation uses the runtime's cancellable process-group lifecycle.

The supervisor needs no session capability.

`input_mode`, TTY allocation, or a provider name never imply the capability.
Compile/load validation rejects a worker whose resolved template lacks it or
whose resume-capable command uses `--ephemeral`. Runtime validation repeats
the capability check before launch.

### Session-transport codec

Preterminal observation and terminal parsing use one metadata-mode codec and
one identity accumulator. For `codex_exec_jsonl_stdout`:

- every immutable `SessionIdentitySnapshot` carries
  `resume_boundary_seen: bool`, owned by the codec and defaulting to `false`;
  codecs without a validated readiness marker leave it `false`;
- codec selection exposes the generic structural capability
  `supports_resume_boundary_observation`; static/runtime validation consults
  that capability rather than provider names or a fresh snapshot's default
  value;
- the codec owns an incremental UTF-8 JSONL line buffer across arbitrary
  callback chunk splits and coalesced lines, feeds every complete line
  exactly once, and parses a non-empty EOF tail exactly once;
- malformed UTF-8/JSON, a non-object event, or a malformed non-empty EOF tail
  permanently invalidates the accumulator;
- real `thread_id` and the retained compatibility `session_id` key both
  normalize to the public provider-session identity;
- a recognized key must contain a non-empty string;
- when both keys occur in one event, their values must match;
- the identity set across all observed events must remain exactly one;
- a later different identity or malformed recognized key permanently marks
  the stream invalid;
- after validating the event's identity fields, an event whose top-level
  `type` field is exactly `turn.started` sets `resume_boundary_seen` only when
  the accumulated identity is already unique and no exact terminal event has
  been seen; a nested, suffixed, status-like, or otherwise lookalike event
  does not set it;
- a `turn.started` observed before unique identity is not applied
  retroactively when identity later becomes unique;
- once set, `resume_boundary_seen` remains true as historical observation
  even if a later event makes the identity invalid/ambiguous or marks the turn
  terminal; invalid/ambiguous identity removes all eligibility, while
  terminal state removes active-cancellation eligibility and is separately
  adjudicated for clean natural success;
- `turn.completed` and the retained fixture/legacy
  `response.completed` spelling are the exact successful turn-terminal
  events; exact top-level `turn.failed` is an unsuccessful terminal event
  that sets `terminal_seen`, durably invalidates the transport with a
  structured failure, immediately removes all resume eligibility, and must
  resolve through natural/transport-failure precedence rather than the
  clean-success branch even if the process exits zero;
  `item.completed` is not terminal; and
- an `item.completed` event whose nested `item.type` is `agent_message`
  contributes nested `item.text` to normalized assistant output without
  changing terminal state. No suffix match, generic `completed|done` event,
  or `status: completed` value is terminal.

The in-flight readiness snapshot is provisional. After cancellation, the
coordinator joins the executor future and capture threads and rechecks the
final partial-stream accumulator before using the identity. An active fresh
turn is eligible for cancellation toward a resume attempt only while the
member and whole-step deadlines are live and the same snapshot satisfies all
three conditions:

```text
status == "unique"
and resume_boundary_seen
and not terminal_seen
```

If the fresh process completes successfully before cancellation becomes
authoritative, the separate clean-natural-completion branch may proceed only
when its frozen terminal snapshot proves the complete process boundary,
identity remains unique, `resume_boundary_seen` is true, and the whole-step
deadline remains live before the resume launch. That branch expects
`terminal_seen: true`; it does not claim active-turn cancellation. A
whole-step timeout wins over both active-cancellation and clean-natural
branches.

The readiness marker is necessary but not sufficient: actual exact-identity
resume remains the only resumability proof. Callback
exceptions cannot be the correctness channel because pipe capture currently
treats them as best-effort; invalidity is durable inside the accumulator
returned to the coordinator.

## Executable Contract

The form lowers through WCC/schema 2 to one
`ExecutableNodeKind.PROVIDER_SUPERVISION` node.

Its config has node-local schema
`provider_supervision.v1` and contains:

- stable node id and source ownership;
- worker and supervisor member ids;
- immutable provider configs for both members;
- one observation edge from supervisor to worker;
- the worker result contract;
- the compiler-owned supervisor directive contract;
- the validated pure settlement payload and its result contract;
- member-local timeout budgets plus the existing step budget;
- `max_steers: 1`;
- unique member/turn evidence and provisional bundle locations; and
- prompt-audit/source-map ownership for the form, bindings, observation
  clause, and settlement body.

`workflow_executable_ir.v1`, runtime-plan v1, semantic-IR v1, source-map v1,
and state schema 2.1 remain the envelope versions. The new node carries its
own required schema tag; older runtimes reject the unknown node kind, and
target DSL 2.16 prevents old workflows from emitting it. Existing node
encodings do not change.

The runtime plan shows one provider-supervision node with two initial members,
one atomic workflow-state/result commit, and an optional bounded resume
transition. Semantic IR explains the worker, supervisor, observation edge,
directive type, and settlement type.

## Runtime Ownership And Concurrency

One group coordinator runs on the serial workflow cursor and is the sole
owner of:

- `StateManager`;
- `current_step` and checkpoint publication;
- provider-attempt allocation;
- workflow variables and dataflow;
- provider-session bookkeeping exposed to workflow state;
- artifact/result validation and publication; and
- the terminal group result.

Before concurrency begins, the coordinator:

1. allocates the workflow group visit and unique member/turn paths;
2. creates the visit-qualified metadata/evidence record and persists the
   ordinary single group `current_step` before any pane or provider process;
3. creates the initial two display files and observation panes so the worker
   target exists;
4. composes the worker and supervisor prompts, substituting the live worker
   target only into the supervisor's execution prompt;
5. allocates and durably publishes one provider-attempt ordinal and immutable
   prompt-dependency snapshot for each initial member;
6. constructs immutable `ProviderInvocation` requests, gives both initial
   members their own cancellation controls, and binds the worker control to
   the fresh-session codec; and
7. launches both provider commands.

Member workers may:

- call `ProviderExecutor.execute` with their immutable request;
- append only to their member-local raw/display/transcript paths;
- emit in-memory lifecycle events to the coordinator; and
- return a `ProviderExecutionResult`.

They may not call workflow-step preparation/finalization, mutate
`StateManager`, allocate attempts, publish artifacts, change variables, or
clear `current_step`.

The coordinator consumes member events through one serialized arbiter and
performs every workflow-state mutation after joining or cancelling the
relevant provider work.

### Provider-attempt ownership

The group visit is not itself a provider attempt. Each actual provider
invocation owns one ordinary counter-allocated provider attempt:

- worker fresh turn;
- supervisor directive turn; and
- worker resume turn, only when `STEER` selects it.

Attempt scope is derived structurally from group step id, group visit, member
id, and turn ordinal. The coordinator allocates every ordinal serially through
the existing state-manager allocator. For the initial pair it persists both
counter advances and writes their immutable prompt-dependency snapshots before
concurrent launch. For a resume turn it allocates the ordinal only after the
fresh worker boundary is proved, writes the immutable snapshot before resume
launch, and gives that invocation its own cancellation control.

Each attempt has distinct prompt audit, invocation metadata, display
transcript, dependency snapshot, provisional result path, and terminal
outcome. The terminal group result records the supervisor attempt and the
selected worker attempt. Cancelled, failed, and unselected attempts remain
evidence; they never publish member artifacts or a group result. A new
authored retry uses a new group visit and new attempt ordinals.

### Cancellable executor control

An optional per-invocation `ProviderExecutionControl` is the only control
surface between the coordinator and `ProviderExecutor`:

- lifecycle is `NEW -> BOUND -> TERMINAL`, with `NEW -> TERMINAL` permitted
  only when process creation fails before bind;
- `bind(process, pgid)` occurs exactly once immediately after `Popen`;
- cancellation requested in `NEW` latches and executes immediately on bind;
- spawn failure terminalizes an unbound control with a frozen launch-failure
  disposition and wakes every readiness/cancellation waiter;
- session-codec updates publish immutable identity snapshots
  (`missing|unique|ambiguous|invalid`, ids, codec-owned
  resume-boundary-seen, exact-terminal-seen);
- `cancel_and_reap(grace)` is idempotent and returns a frozen disposition,
  leader return code, PGID-empty proof, and join status. It is invoked for
  every `STEER`, including after natural leader exit. An already-terminal
  invocation may skip signaling only when its frozen terminal snapshot
  already proves the leader reaped, the owned PGID empty, and capture work
  joined. A naturally exited leader with a still-live same-PGID child is
  cleaned up but remains a failed boundary and is not resumable; and
- terminal execution returns the untouched raw buffers plus a normal,
  cancelled-provisional, or failed result classification.

The coordinator resolves races as follows:

| Race | Required outcome |
| --- | --- |
| cancellation requested before process bind | latch; cancel immediately after bind; never expose a promotable result |
| `STEER` arrives before resume-boundary readiness | wait only until one snapshot has unique identity, `resume_boundary_seen: true`, and `terminal_seen: false`, or until worker terminal state or the earlier member/whole-step deadline; invalid/ambiguous identity fails immediately, while identity/readiness still missing at terminal or deadline fails unless the terminal state satisfies the clean-natural-success row below |
| successful natural exit before `STEER` cancellation | invoke the same idempotent boundary verifier; resume only when the frozen terminal snapshot proves leader reaped, owned PGID empty, executor/capture work joined, unique identity, and prior observation of the resume-boundary marker |
| successful leader exit with a lingering same-PGID child | clean the owned PGID, classify the prior boundary as failed, and do not resume |
| natural nonzero/transport failure before validated `STEER` | member failure wins; fail the group and do not resume |
| natural exit concurrent with cancellation | join once; if cancellation became authoritative, require the active-turn conjunction including `terminal_seen: false`; if clean natural success became authoritative, require its complete frozen terminal boundary plus unique identity and the sticky readiness observation; `STEER` still selects only the resume turn |
| repeated cancellation | same frozen cancellation result; no second signals or publication |
| unique id and readiness marker followed by malformed/conflicting input | `resume_boundary_seen` remains historical evidence, but the final snapshot is invalid/ambiguous; no resume |
| launch failure | member failure; cancel/join the sibling; no group publication |
| supervisor failure or timeout | cancel/join the worker; fail the group; no resume |
| worker timeout with `CONTINUE` | fail the group after cleanup |
| `STEER`-requested worker termination | classify the fresh result as expected `cancelled_provisional`; its nonzero exit is not a member failure and is never promotable |
| whole-step timeout | cancel/join both initial members or the active resume turn; fail the group |
| required mirror loss before directive | cancel/join both members; fail the group |
| mirror loss after validated directive | record evidence; preserve the already-selected control path |

Completion and cancellation that occur within one process-poll interval do
not have a portable wall-clock ordering. The executor therefore uses the
first zero-time completion probe after a newly latched cancellation as the
linearization point. A newly observed cancellation skips the ordinary wait
slice and forces that probe immediately. If the probe observes completion,
the natural result remains authoritative, including a natural nonzero
failure. If the probe observes the leader still incomplete, the executor
immediately attempts cancellation, which becomes authoritative only when
application is proved. Signal success cannot override natural completion
already observed by that zero-time probe. This observable rule preserves
fail-closed natural-failure precedence when physical ordering cannot be
reconstructed.

Every group invocation receives a control object so sibling failure and the
whole-step deadline can cancel and join the supervisor or active resume turn.
Provider calls outside a group may omit one and retain their existing
execution path.

## Turn-Boundary State Machine

### Launch

1. Start the worker in fresh-session mode and the supervisor concurrently.
2. Mirror normalized output into their distinct panes.
3. Capture candidate worker-session identity and resume-boundary observations
   through the shared metadata-mode codec and publish immutable snapshots only
   to the coordinator's in-memory arbiter.
4. Validate the supervisor's result bundle as
   `ProviderSteeringDirective`.

### `CONTINUE`

1. Record the validated directive.
2. Await the current worker process if it is still active.
3. Require a successful worker execution and valid worker bundle.
4. Select that bundle as the worker result.

### `STEER`

1. Record the validated directive. For an active worker, require exactly one
   stable session id, `resume_boundary_seen: true`,
   `terminal_seen: false`, and time remaining before both applicable
   deadlines. A worker already terminal enters the separate
   clean-natural-completion check below only while the whole-step deadline
   remains live.
2. If the active snapshot is not eligible yet, wait only until the codec
   publishes the complete active-turn conjunction, the worker becomes
   terminal, or the earlier worker/whole-step deadline.
   Invalid/ambiguous identity fails immediately. Identity or readiness still
   missing at terminal/deadline fails and cleans the group without resume. A
   terminal worker may proceed only through the
   clean-natural-completion branch.
3. Invoke `cancel_and_reap` for every `STEER`:
   - send graceful termination to the owned process group;
   - after a fixed bounded grace, send hard termination;
   - reap the process leader;
   - verify that the owned PGID is empty;
   - join the executor future and both capture threads; and
   - revalidate the final partial-stream snapshot against the authoritative
     branch: unique, resume-boundary-seen, and preterminal for active
     cancellation; or unique and resume-boundary-seen with a complete frozen
     successful terminal boundary for clean natural completion.
   An already-terminal invocation skips signals only when its frozen terminal
   snapshot already proves the complete boundary. If the leader exited while
   a same-PGID child remained, cleanup still runs but the boundary is failed.
4. If any process-group, join, or identity condition fails, fail the group.
   Do not launch a resume turn. Recheck the whole-step deadline before either
   branch launches the resume; timeout wins even after a clean natural
   completion.
5. If the fresh worker completed successfully before cancellation became
   authoritative and its frozen terminal snapshot proves the complete
   boundary, unique identity, and prior resume-boundary observation, treat its
   execution and transport as provisional and proceed. Once `STEER` is
   validated, the coordinator does not read or validate the unselected fresh
   business bundle. A lingering same-PGID child, natural nonzero exit,
   transport failure, missing readiness marker, or unusable final identity
   fails the group instead.
6. Launch exactly one resume invocation with the captured session id and the
   directive's free-form guidance as its conversational content. Render the
   worker's output contract again for the same declared type, bind
   `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` only to the resume turn's distinct
   provisional path, and append that replacement-turn contract to the
   guidance.
7. Require the returned session identity to match, the invocation to succeed,
   and the resumed worker bundle to validate.
8. Select only the resumed bundle as the worker result.

### Settlement

1. Both the supervisor directive and selected worker result must exist.
2. Evaluate the validated pure settlement payload.
3. Validate the settlement result against the form's declared type.
4. Commit one terminal group result and clear the single `current_step`.
5. Finalize member transcripts and destroy all group panes.

Directive/worker completion ordering does not change semantics:

- `CONTINUE` always selects the fresh turn;
- `STEER` always selects one resume turn;
- a fresh bundle is never selected on `STEER`; and
- the serialized arbiter prevents two publication paths from winning.

## Result And Evidence Authority

- Fresh worker, supervisor, and resumed worker turns use different
  runtime-owned provisional bundle paths.
- Every path is derived from group step id, visit, member id, and turn/attempt
  ordinal. The coordinator requires the file to be absent and creates its
  parent before launch; a stale preimage is a prelaunch failure, never a valid
  result.
- The fresh worker prompt renders the worker contract against the fresh path
  because `CONTINUE` may select it. The resume prompt renders the same
  contract against the resume path because `STEER` may select only that turn.
- No member writes directly to the group result path.
- The coordinator reads and validates the supervisor directive bundle only
  after the supervisor is terminal. It reads the fresh worker business bundle
  only when `CONTINUE` selects it, and reads the resume business bundle only
  when `STEER` selects it.
- On `STEER`, the fresh bundle is never promoted even if it is valid.
- On `STEER`, a missing or invalid fresh business bundle is ignored because
  it is unselected; execution, transport/session, and complete-boundary
  failures remain fatal.
- Only the selected worker value and validated directive enter the pure
  settlement environment.
- The settlement value is the only workflow result committed for the node.
  Its step result, artifact/dataflow publications, selected-attempt refs,
  terminal metadata, and exact matching `current_step` clearance land through
  one `finalize_step_with_dataflow`-equivalent state transaction.
- Pane mirrors, raw logs, normalized transcripts, cancellation records, and
  member timing are evidence only.

## Atomicity And Workspace Effects

The word **atomic** in this design applies only to workflow state, checkpoint
visibility, artifact/result publication, and the node's terminal commit. It
does not describe a filesystem transaction around provider activity.

- Both providers retain the ordinary provider execution authority of their
  calls. Their workspace or external effects may occur before a validated
  result exists.
- The design does not enforce a mutation-free supervisor and does not roll
  back worker or supervisor writes.
- A cancelled fresh worker may have changed the workspace. The resume turn
  starts from that current workspace and receives corrective guidance; it is
  not a clean-snapshot retry.
- Concurrent provider behavior and workspace bytes are therefore not
  deterministic. T2's determinism claim is limited to event arbitration,
  selected-result authority, workflow-state transitions, and publication.
- Authors are responsible for choosing worker/supervisor calls whose
  concurrent effects are compatible. Integration fixtures and the real smoke
  use an isolated toy workspace so their expected state is auditable.

A future mutation-containment or rollback contract would be a separate
feature. It is not implied by `with-live-providers`.

## Checkpoint, Retry, And Resume

- The whole form owns one checkpoint identity derived from its static
  structure, member calls, observation edge, pure settlement payload, and
  declared inputs.
- No member result, session id, pane target, steering progress, or
  cancellation state is a separately resumable checkpoint.
- A member failure, directive failure, cancellation failure, resume failure,
  or settlement failure fails the node and cleans up every active member.
- An authored retry is eligible only after the live coordinator has joined or
  cancelled every member and durably finalized the failed attempt. That retry
  starts the whole group with a fresh provider session and new panes.
- Before publishing the ordinary `current_step`, the coordinator creates a
  visit-qualified provider-supervision metadata record and member evidence
  paths. The record begins in `running`/`pending` state and remains secondary
  observability evidence; `state.json` is authoritative.
- If ordinary run resume finds `current_step.status: running` for a
  provider-supervision node without that exact visit's terminal group result,
  it quarantines the visit before restart-index planning, mutation for a new
  visit, or provider launch. It never fresh-replays the group, reuses a member
  session, or infers process death from stale process metadata.
- Quarantine atomically sets the run to failed, clears the exact matching
  `current_step`, preserves older terminal results, records a sticky
  `provider_supervision_interrupted_visit_quarantined` run error, and updates
  the visit metadata/evidence as interrupted. Later ordinary resume fails
  immediately from that marker.
- Only explicit `--force-restart` or a new run may cross that quarantine
  boundary, matching the existing provider-session external-state policy.
- A crash may leave partial member evidence, but no member bundle is
  authoritative unless the group terminal commit landed.
- Existing root checksum, callee checksum, lexical checkpoint, and projection
  validation remain unchanged.

## Invariants And Failure Modes

### Invariants

1. Every invocation attempts one pane; every successfully allocated pane has
   exactly one invocation and is never reused. A supervision member requires
   its pane.
2. The provider transport remains authoritative; the pane is a view.
3. Workflow state has one writer: the group coordinator.
4. Exactly one worker turn supplies the selected worker result.
5. `STEER` cannot resume until the final partial-stream snapshot still has a
   unique identity and `resume_boundary_seen: true`; the fresh leader is
   reaped, the owned PGID is empty, and its executor future and capture
   threads are joined. Active-turn cancellation additionally requires
   `terminal_seen: false` and live applicable deadlines. Clean natural
   completion instead requires the complete frozen successful terminal
   boundary and a live whole-step deadline immediately before resume launch.
   Whole-step timeout wins over either branch.
6. The supervisor directive is accepted only from its validated bundle.
7. Guidance is free-form content; the runtime interprets only
   `CONTINUE|STEER`.
8. Live targets and provider session ids never escape as workflow values;
   debug prompt/command evidence may retain a now-ephemeral target.
9. The group has one atomic workflow-state/result commit; an interrupted live
   visit is quarantined and never replayed by ordinary resume.
10. No mechanism consults provider, workflow, family, module, or domain
    names.

### Fail-closed cases

- wrong arity, missing/duplicate observation edge, unknown peer, ineligible
  member, or effectful settlement body;
- target DSL below 2.16;
- worker template missing valid turn-boundary capability, using an unsupported
  metadata codec, or including `--ephemeral` in a resume-capable command;
- required supervision-pane allocation or pre-directive display-mirror
  failure;
- supervisor failure or invalid directive;
- missing, empty, plural, changing, or late-only worker session identity;
  missing or lookalike-only resume-boundary marker; exact terminal event on
  the active-cancellation branch without a complete clean-success boundary;
  expired member deadline when `STEER` needs active-turn cancellation; or
  expired whole-step deadline before either branch launches resume;
- worker leader/PGID/future/capture-thread boundary not proved;
- resume identity mismatch;
- member timeout or nonzero exit;
- supervisor directive-contract failure or selected worker
  business-contract failure; an unselected fresh bundle is not read after
  `STEER`;
- provisional bundle path collision or contamination;
- pure settlement validation failure; or
- crash before the atomic terminal commit.

## Compatibility And Versioning

- Existing Workflow Lisp source and all existing provider steps keep their
  current provider transport and result contracts.
- Pane mirroring is attempted by default after T1 parity passes. Ordinary
  calls degrade observability rather than provider correctness when it is
  unavailable; the live form requires its initial mirrors.
- `with-live-providers` is new in target DSL 2.16.
- There is no YAML spelling.
- Providers without turn-boundary resume remain fully usable for ordinary
  calls and as supervisors; they are rejected only in the observed-worker
  position.
- A session codec without a validated readiness marker reports
  `resume_boundary_seen: false`; stable identity alone never upgrades that
  provider to observed-worker eligibility.
- Current file/inbox coordination, cross-run watchdogs, and sequential
  provider-session steps remain valid.

## Verification Strategy

### T1 — observation non-interference

Compare pane-disabled and pane-enabled execution for:

- ordinary non-stream provider calls;
- streaming calls;
- session JSONL calls, in-flight session-id extraction, and immutable
  resume-boundary observations;
- adjudicated candidate/evaluator invocations and managed-provider
  invocations;
- stdout, stderr, exit code, timeout, and normalized result;
- output bundles and provider-session metadata; and
- pane allocation failure, tail-process failure, tmux-server loss, callback
  failure, transcript finalization, and teardown.

The test must prove that terminal-rendered pane bytes never feed the raw
provider parser or result path.

### T2 — single-writer concurrency

Use scripted providers to prove:

- worker and supervisor overlap in wall-clock time;
- member workers receive immutable requests;
- member workers never call `StateManager` or workflow-executor mutation
  entrypoints;
- member-local ids and paths do not collide;
- group heartbeat and one `current_step` remain coherent;
- only the coordinator commits artifacts and the terminal result; and
- all coordinator event orderings produce one deterministic selected-result
  and workflow-state outcome; provider behavior and workspace bytes are not
  claimed deterministic.

### T3b — turn-boundary integration

Both-direction fixtures:

- `CONTINUE` selects the fresh worker result and never launches resume;
- `STEER` observes a live worker, captures one canonical session id, observes
  the exact `turn.started` readiness marker while preterminal, reaps the leader,
  empties the owned PGID, joins the executor/capture work, performs one resume,
  and selects only the resumed result;
- no session id rejects;
- plural/changing session ids reject;
- real `thread.started.thread_id` canonicalizes and becomes available before
  `turn.completed`;
- identity-only cancellation after `thread.started` remains ineligible;
- exact top-level `turn.started` sets `resume_boundary_seen` only after unique
  identity and before terminal; early, nested, suffixed, or status-like
  lookalikes do not set it, and codecs without a validated marker remain
  ineligible;
- a later invalid/ambiguous identity leaves the sticky observation visible but
  removes all eligibility; an exact successful terminal event removes
  active-cancellation eligibility but may enter the complete
  clean-natural-success branch, while exact `turn.failed` resolves through
  durable transport-failure precedence;
- real nested `item.completed.item` agent messages contribute normalized
  assistant text without marking the turn terminal;
- cross-key identity disagreement and malformed identity values reject;
- `item.completed` neither marks the provider turn terminal nor establishes
  resume-boundary readiness;
- invalid directive rejects;
- failed or ambiguous quiescence rejects before resume;
- successful leader exit with a lingering same-PGID child rejects without a
  resume, while a clean natural terminal exit may resume only through its
  complete frozen-boundary branch;
- resume identity mismatch rejects;
- stale fresh bundle never wins;
- a missing/invalid fresh business bundle fails `CONTINUE` but is not read
  after a valid `STEER` whose resume bundle succeeds;
- stale provisional preimages reject before launch;
- a missing resume bundle rejects even when a stale fresh bundle is valid;
- settlement failure commits no member result or artifact publication; the
  failed group finalization follows ordinary failure persistence;
- second steering is impossible; and
- live-coordinator retry starts fresh only after complete cleanup;
- controller-crash resume quarantines before any provider launch; and
- later ordinary resume fails immediately from the sticky quarantine marker.

One real-provider smoke must demonstrate a real supervisor observing a real
session-capable worker and producing a correction whose resumed typed result
differs as intended. If neither the complete active-cancellation boundary nor
the complete clean-natural-success boundary is available, the applicable
deadline expires, actual same-identity resume fails, or the
leader/owned-PGID/future/capture-thread boundary cannot be proved, Stage 7
stops at the fixture implementation and the live-correction claim is not
shipped.

### Frontend and IR

- parser/type diagnostics for every invalid form shape;
- target `2.16` installs/reserves the prelude directive while earlier targets
  neither install nor reserve that name;
- post-specialization member eligibility;
- supervisor directive type enforcement;
- body pure-projection enforcement;
- `LiveSupervisionEffect` and source ownership;
- executable, runtime-plan, semantic, source-map, checkpoint, and build
  artifact projections;
- target-DSL version rejection and acceptance; and
- end-to-end `.orc` compile/run/report behavior.

Tests assert behavior, contracts, lineage, and dataflow—not literal prompt
phrasing.

## Dependencies And Sequencing

The Stage 7 implementation order is:

1. **Observation and cancellation substrate.** Pane mirror behind a flag,
   cancellable provider execution, shared real-shape session codec,
   preterminal identity/readiness callback, T1 parity, and a minimal real
   Codex unique-identity + exact-readiness-marker → cancel/owned-PGID proof →
   same-identity-resume spike. This phase stops if the real boundary fails;
   frontend work may not begin on fixture evidence alone.
2. **Runtime group coordinator.** Hand-built executable nodes, immutable
   member execution, directive arbitration, one-turn resume, result
   promotion, atomic state, and T2/T3b fixtures.
3. **Workflow Lisp surface.** Syntax, specialization eligibility, typing,
   effects, WCC/schema-2 defunctionalization, executable projections, pure
   settlement, and DSL 2.16.
4. **Capability promotion and integration.** Structurally opt in eligible
   templates, run the real T3b smoke, update normative specs and authoring
   docs, enable the pane default, and close Stage 7 evidence.

Each phase must use TDD and receive specification-compliance and code-quality
review before the next dependent phase.

## Success Criteria

- This design passes independent review after the adverse T3a result is
  incorporated.
- T1 proves observation non-interference for every current provider execution
  path.
- The phase-1 real Codex spike proves canonical preterminal identity, an exact
  codec-owned resume-boundary marker, cancellation boundary, and actual
  same-identity session resume before group/frontend implementation.
- T2 proves the group coordinator is the only workflow-state writer.
- Fixture T3b proves both `CONTINUE` and `STEER`, including strict negative
  paths.
- The real T3b smoke proves effective live correction, the complete
  preterminal resume-eligibility conjunction, leader reaping, owned-PGID
  emptiness, and joined executor/capture work.
- DSL 2.16 frontend, IR, runtime, state, report, and typed-result checks pass.
- Existing provider behavior remains non-regressive.
- Normative specs, capability status, authoring guidance, and roadmap routing
  describe the implemented contract.

## Stop / Revise Criteria

- Raw provider behavior changes when the pane mirror is enabled: stop and keep
  ordinary mirrors opt-in until non-interference is restored.
- A real supported provider cannot expose a unique session id plus a
  codec-validated resume-boundary marker before an exact terminal event and
  the applicable deadline, or actual exact-identity resume still fails from
  that boundary: do not claim active-turn correction; revise to a separately
  designed native protocol.
- The runtime cannot prove the old worker's leader/owned-PGID/future/capture
  boundary: do not launch the resume turn.
- The implementation requires concurrent workflow-executor mutation: stop and
  preserve the single-writer boundary.
- The form cannot lower through WCC/schema 2 without a direct frontend escape
  path: stop and revise the frontend contract.
- Any mechanism requires provider- or workflow-name branching: stop; the
  abstraction is wrong.

## Documentation Impact

Implementation updates:

- `docs/design/workflow_lisp_executable_ir.md`;
- `docs/design/workflow_lisp_frontend_specification.md`;
- `specs/providers.md`, `specs/io.md`, `specs/state.md`,
  `specs/versioning.md`, `specs/observability.md`, and `specs/index.md`;
- `docs/capability_status_matrix.md`;
- the Workflow Lisp drafting guide;
- provider monitoring documentation;
- `docs/design/README.md` and `docs/index.md`; and
- the Stage 7 roadmap status and execution-plan links.

## Deferred Follow-Ons

Separate proposals are required for:

- provider-native active-turn protocols;
- repeated or unbounded steering;
- N-member or bidirectional supervision;
- effectful settlement;
- multi-step member procedures;
- cross-run live binding; and
- general background/join semantics.
