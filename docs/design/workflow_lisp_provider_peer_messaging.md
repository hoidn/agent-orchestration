# Workflow Lisp Provider Peer Messaging

- **Status:** accepted Stage-7 v1.1 design; implementation requires a reviewed
  execution plan
- **Kind:** feature / recorded provider-to-provider messaging and static
  provider-group composition
- **Owner:** Workflow Lisp frontend + provider runtime
- **Created:** 2026-07-24
- **Review:** independent specification `DESIGN_SPEC_APPROVED`; ordered
  quality `DESIGN_QUALITY_APPROVED` on 2026-07-24
- **Related design:**
  - `docs/design/workflow_lisp_provider_live_binding.md`
  - `docs/design/workflow_lisp_frontend_specification.md`
  - `docs/design/workflow_lisp_executable_ir.md`
  - `docs/design/workflow_lisp_provider_prompt_queue.md`
  - `specs/providers.md`, `specs/io.md`, `specs/state.md`,
    `specs/versioning.md`, and `specs/observability.md`
- **Roadmap owner:** Stage 7 v1.1 in
  `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`

## Summary

Stage 7 v1.1 adds recorded free-form messaging among a statically declared
group of provider members. A member addresses another member by binding name
through the runtime-owned `orchestrator peer-send` surface. The single-writer
group coordinator records each accepted message in the exact receiver
attempt's append-only ledger before an opt-in interactive-session adapter
offers it to the provider client for the next natural turn.

The amendment is additive:

- target DSL `2.16`, `with-live-providers`, and
  `provider_supervision.v1` remain byte- and behavior-compatible;
- target DSL `2.17` adds `with-live-provider-peers` and the closed
  `provider_peer_group.v1` node schema;
- peer groups contain a literal, statically bounded list of two through eight
  members;
- peer messaging never cancels, resumes, replaces, selects, or settles a
  member;
- a separate cooperative `peer-finish` receipt closes a member after its
  typed bundle is frozen and all accepted incoming messages are acknowledged;
  and
- the v1 `STEER` path remains the only successful forcing move. A v1.1 peer
  group has no directive or forcing edge.

This separation is deliberate. Combining queued peer input with a forced
replacement turn would need a new rule for message ownership across native
session attempts. V1.1 rejects that combination instead of silently
retargeting or dropping a message.

## Authority And Non-Regression Boundary

The implemented v1 contract remains authoritative for:

- observation-only panes;
- exactly one worker and one supervisor;
- `ProviderSteeringDirective`;
- one `CONTINUE|STEER` decision;
- exact-session cancellation and bounded resume;
- `LiveSupervisionEffect`; and
- `provider_supervision.v1`.

Nothing in this design changes those source, IR, runtime, state, evidence, or
resume semantics. Existing target-`2.16` artifacts must remain identical.

V1.1 reuses only established infrastructure that is semantically compatible:

- one serial workflow cursor;
- one single-writer coordinator per composite node;
- provider-attempt allocation;
- provisional typed output bundles;
- atomic settlement publication;
- group-visit quarantine after controller interruption; and
- process-boundary cleanup proof.

The v1 observation pane is not reused as an input path. It runs `tail -F`
over a display file and remains observation-only.

## Feasibility Result

### Current transport finding

The current provider executor cannot deliver a later message:

- `STDIN` mode writes the initial prompt and closes the pipe;
- ARGV mode has no later input channel;
- session resume launches a new process and is reserved for the v1 forcing
  path; and
- the live observation pane contains a tail process, not the provider client.

Therefore neither the closed stdin nor the observation target is a v1.1
capability.

### Fresh real-client probe

A bounded Codex `0.145.0` probe on 2026-07-24 established the narrower
feasibility claim needed here:

1. the real interactive client ran in a runtime-owned tmux pane;
2. its first turn started a bounded `sleep`;
3. literal follow-up text was submitted without Escape, interrupt,
   cancellation, or a resume command;
4. the client visibly queued the follow-up;
5. the first turn completed naturally;
6. the queued next turn ran and wrote the expected acknowledgement file; and
7. a provider-declared `/exit` command produced natural client termination.

No provider session id, raw prompt, or response content is retained in this
design. The probe proves that an interactive queued-input adapter is viable.
It does not make pane text authoritative and does not by itself prove that a
model semantically understood a message.

The implementation gate must reproduce the behavior through the runtime
adapter and cooperative receipts described below. Fixtures alone cannot ship
the live-delivery claim.

## Goals

1. Allow every member of one static live group to send free-form UTF-8 text
   to any other member by binding name.
2. Record the exact sender attempt, receiver attempt, content, order, and
   delivery lifecycle before and after each offer.
3. Deliver only at the provider client's natural turn boundary.
4. Keep all workflow state, attempt, ledger, lifecycle, and settlement
   mutations under one coordinator.
5. Preserve typed bundle authority and one atomic workflow-state/result
   commit.
6. Reject stale, ambiguous, self, terminal, and cross-attempt delivery
   fail-closed.
7. Remain structural: no provider, workflow, family, module, or domain name
   selects behavior.

## Non-Goals

- same-turn steering;
- raw-pane addressing by member agents;
- unrecorded `send-keys`;
- provider stdout, pane text, or transcript parsing as result authority;
- a claim that `offered` means model-seen or semantically understood;
- `STEER` or any other forcing move inside a peer group;
- combining peer messages with v1 worker replacement;
- dynamic member counts;
- dynamic spawn or join;
- multiple supervisors, voting, directive arbitration, or an observation
  graph;
- cross-run messaging;
- member-level workflow resume or checkpointing;
- repeated provider-session resume commands as message delivery;
- provider-native duplex APIs;
- effectful settlement;
- filesystem rollback; and
- stronger containment than the runtime-owned process and tmux resources.

## Language Contract

### Surface

Illustrative target-`2.17` source:

```lisp
(with-live-provider-peers
  ((planner  (procs.plan request))
   (reviewer (procs.review policy))
   (builder  (procs.build inputs)))
  (make-team-result
    :plan planner
    :review reviewer
    :build builder))
```

The form is distinct from v1 `with-live-providers`. Its rules are:

- the binding list is literal and contains `2..8` members;
- binding names are unique and become canonical member ids after hygiene;
- each binding is `(<name> <provider-producing-expression>)`; there is no
  `:observes`, `:role`, dynamic membership, or message ACL syntax;
- every member may message every other member; self-targeting is forbidden;
- a member expression cannot refer to a sibling result;
- every expression must satisfy the existing post-specialization provider
  member shape: exactly one unconditional provider perform followed only by
  a pure result projection;
- a direct procedure invocation remains eligible only through recursive
  `:lowering inline` specialization;
- every member result may be any transportable type;
- the settlement body is a pure expression over all member results;
- the settlement result must be transportable; and
- the form's type is the settlement type.

The fixed upper bound is the language constant
`MAX_STATIC_LIVE_PROVIDER_PEERS = 8`. Raising it requires a versioned
contract change.

### Effects

The form's effect summary is:

- the union of every member's provider effects; plus
- `LivePeerMessagingEffect(members=<authored-order member ids>)`.

It does not emit `LiveSupervisionEffect`, because there is no observation or
steering edge.

### Target gate

- Targets below `2.17` reject `with-live-provider-peers`.
- Target `2.16` keeps the exact v1 `with-live-providers` behavior.
- Target `2.17` also continues to accept the v1 form; it does not silently
  upgrade it to a peer group.
- The new form name is reserved beginning at target `2.17`.

### WCC and lowering

The form lowers through the ordinary specialization and WCC/schema-2 route:

1. parse and typecheck every binding independently;
2. recursively inline eligible specialized procedures;
3. close each member to the canonical one-provider-perform region;
4. reject residual calls, branches, loops, extra effects, or sibling result
   references at the authored member source;
5. preserve all members in authored order in one
   `WccProviderPeerGroup` term;
6. validate the pure settlement environment against exactly that member set;
   and
7. defunctionalize to one Core/executable peer-group node.

There is no surface-to-Core escape path.

## Executable Contract

The form emits `ExecutableNodeKind.PROVIDER_PEER_GROUP` with node-local schema
`provider_peer_group.v1`.

Its typed config contains:

- stable node id and source ownership;
- an authored-order tuple of `2..8` member configs;
- closed all-other-members messaging policy;
- the pure settlement payload and result contract;
- one required timeout per member and the ordinary whole-step timeout;
- an explicit visit-root path plan;
- one initial attempt/evidence/bundle/ledger path set per member;
- interactive delivery capability requirements;
- prompt-audit/source-map ownership; and
- `max_steers: 0`.

`workflow_executable_ir.v1`, runtime-plan v1, semantic-IR v1, source-map v1,
and state schema `2.1` remain their envelope versions. Older runtimes reject
the unknown node kind. The separate node kind prevents a runtime from
mistaking an N-member cooperative group for a v1 directive node.

The member order, member configs and result contracts, messaging policy,
settlement payload, target version, node schema, and capability requirements
all participate in checkpoint identity.

## Structural Provider Capability

Every peer-group member must opt in through a new provider-neutral capability:

```text
interactive_session_support:
  schema_version: interactive_terminal_turn_queue.v1
  turn_boundary_messages: true
  command: <non-empty token list with exactly one ${PROMPT}>
  message_submit_keys: <closed adapter key sequence>
  graceful_close_text: <non-empty client command>
  graceful_close_submit_keys: <closed adapter key sequence>
```

Validation rules:

- the capability is never inferred from provider name, stdin, TTY presence,
  session support, observation support, or `turn_boundary_resume`;
- adapter selection may branch only on the declared schema version;
- the command contains the prompt exactly once and contains no provider
  session-resume placeholder;
- submit sequences come from the adapter's closed key vocabulary and may not
  contain Escape, Ctrl-C, signal, suspend, or other forcing input;
- graceful close is a normal provider-client command, not process
  cancellation;
- compile/load validation checks every statically resolved member template;
  runtime repeats the check before any launch; and
- a provider without the capability remains fully usable outside peer groups.

The first implementation adapter is
`interactive_terminal_turn_queue.v1`. It owns the actual provider TUI pane.
It is separate from `ProviderObservationManager` and its display pane.

The adapter interface is:

```text
start(invocation) -> InteractiveMemberHandle
offer(handle, literal_message) -> OfferReceipt
offer_close(handle) -> CloseOfferReceipt
join(handle, deadline) -> NaturalShutdownProof
abort(handle, deadline) -> FailedCleanupProof
```

`offer` may send only literal runtime framing, the verbatim message, and the
declared submit sequence. It may not invoke any v1 cancellation, resume, or
directive API. A successful offer proves input was offered to the exact
client, not that the model saw it.

## Runtime-Owned Peer Surface

### Commands

The member-visible surfaces are:

```text
orchestrator peer-ready
orchestrator peer-send <target-binding> <message>
orchestrator peer-ack <message-id>
orchestrator peer-finish
```

The Python client uses the same transport. These clients are thin:

- they read their opaque active-group binding from environment;
- they send one bounded request to the runtime endpoint;
- they return the coordinator's receipt; and
- they never write workflow state, a message ledger, a bundle, or tmux input.

There is no `--from`, run-root selector, arbitrary endpoint selector, raw pane
target, state path, or ledger path.

### Endpoint identity

One ephemeral local endpoint exists per active group visit and is bound to:

```text
run_id
step_name
node_id
visit_count
endpoint_instance_id
```

After serial attempt allocation, each member receives an opaque sender
binding that resolves server-side to:

```text
member_id
attempt_scope_key
attempt_ordinal
endpoint_instance_id
```

The endpoint and opaque binding are runtime handles. They never enter
workflow values, result state, checkpoint identity, or reusable evidence.

A listener may decode closed bounded requests on another thread, but it may
only enqueue immutable events and await receipts. The coordinator alone
validates membership, appends ledgers, offers input, changes lifecycle state,
freezes bundles, or publishes results.

### Message size and text

- Messages are non-empty well-formed UTF-8.
- The encoded content limit is 65,536 bytes.
- Newlines and ordinary Unicode are preserved verbatim.
- Runtime framing carries the message id and sender binding separately; it
  does not rewrite message content.
- A client request id is required. Exact replay returns the prior durable
  result; reuse with different content fails closed.

## Member Lifecycle

Each member has one long-lived interactive provider attempt:

```text
ALLOCATED
  -> STARTING
  -> READY_WAITING
  -> ACTIVE
  -> FINISH_REQUESTED
  -> CLOSING
  -> TERMINAL
```

Any nonterminal state may enter `FAILED`.

### Readiness

The initial prompt contains a structural peer-protocol injection owned by the
runtime. Each member's `peer-ready` request proves:

- the exact provider attempt reached its ordinary shell tool;
- the endpoint and opaque member binding round-tripped;
- the coordinator still owns the exact group visit; and
- the member has not begun closing.

`peer-ready` is an all-members barrier, not a per-member race:

1. the coordinator records each exact member in `READY_WAITING`;
2. the command remains blocked until all statically declared members have
   registered;
3. one coordinator transition moves the whole group to `ACTIVE`; and
4. only then do all `peer-ready` calls receive success.

No member can issue a protocol request from its ordinary provider turn before
its `peer-ready` call returns. If any member fails or misses the applicable
deadline at the barrier, every waiting call receives failure and the group
cleans up. A target is addressable only after the group-wide `ACTIVE`
transition. A send while the group is not active, or to
`FINISH_REQUESTED|CLOSING|TERMINAL|FAILED`, is rejected without a ledger row
or delivery.

### Send and acknowledgement

For each accepted `peer-send`:

1. the coordinator validates the current sender and exact target attempt;
2. it appends and fsyncs the `recorded` ledger row;
3. it calls the target adapter's `offer`;
4. it appends and fsyncs `offered` or `offer_failed`;
5. only a durable `offered` outcome returns client success; and
6. after the queued turn receives the message, the receiver calls
   `peer-ack <message-id>`, producing a durable `receiver_acknowledged` row.

Acknowledgement proves that the receiver supplied the exact id back through
its ordinary tool channel. It does not claim semantic comprehension.

### Cooperative finish and natural close

A member writes its bound typed output bundle, then invokes `peer-finish`.
The coordinator serializes that request against every send:

- if a send is ordered first, finish remains ineligible until that incoming
  message is durably acknowledged;
- if finish is ordered first, the member enters `FINISH_REQUESTED` and later
  sends to or from it are rejected;
- finish with a recorded-but-unoffered or offered-but-unacknowledged incoming
  message returns a retryable `pending_messages` receipt and leaves the member
  `ACTIVE`; it does not close or fail the group;
- an `offer_failed` message has already failed the group and cannot be
  bypassed by finish;
- after all incoming messages are acknowledged, the coordinator validates
  and copies the exact member bundle into a coordinator-owned immutable
  frozen result;
- while the `peer-finish` tool call is still active, the adapter durably
  offers the provider-declared graceful close command for the next natural
  client boundary;
- only after that close offer succeeds does the coordinator return a
  successful finish receipt, allowing the tool call and current provider turn
  to complete; and
- the member becomes `TERMINAL` only after the client exits naturally and the
  provider/pane/helper process boundary is fully joined.

The `peer-finish` helper waits for that coordinator receipt. The queued close
cannot execute until the helper returns and the current turn reaches its
natural boundary, so this ordering has no finish/close deadlock. The frozen
bundle—not any later path mutation—is the member result candidate. Finish is
a separate cooperative lifecycle operation; `peer-send` itself never settles
the member.

If normal close does not complete before the member/whole-step deadline, the
group fails. Failure cleanup may terminate remaining owned processes, but no
result is published and the cleanup is not reclassified as successful
settlement.

## Message Ledger And Evidence

Each receiver attempt owns a distinct append-only JSONL sidecar:

```text
provider-peer-group/<node>/visits/<visit>/members/<member>/attempt-<ordinal>/
  prompt-dependencies.json
  injected-messages.jsonl
  evidence.json
  provisional-result.json
```

The immutable prompt-dependency snapshot remains no-replace and is never
rewritten with dynamic message content.

The coordinator creates and fsyncs an explicit ledger header before member
launch. An empty ledger is therefore evidenced, not inferred.

Message lifecycle rows are:

- `recorded`: coordinator sequence, request id, message id, exact sender and
  receiver attempt identities, verbatim content, content digest, and
  timestamp;
- `offered`: exact adapter/receiver binding and offer timestamp;
- `offer_failed`: structured failure and timestamp; and
- `receiver_acknowledged`: exact receiver attempt and timestamp.

Rows are append-only, monotonically sequenced, and canonicalized. A final
ledger digest and counts enter terminal group evidence. Message text does not
enter workflow state, ordinary results, Semantic IR, checkpoint identity, or
prompt-dependency JSON.

Allowed claims are exact:

- `recorded` means validation passed and the row is durable;
- `offered` means the runtime submitted literal input to the exact client;
- `receiver_acknowledged` means the exact receiver returned the message id;
  and
- no event is named `seen`, `model_seen`, `understood`, or `applied`.

## Coordinator And Atomic Settlement

Before concurrent launch, the coordinator:

1. publishes one group `current_step`;
2. derives and preflights the visit and all member paths;
3. allocates every member attempt in authored order;
4. creates every immutable prompt snapshot and empty message ledger;
5. starts the group ingress endpoint;
6. constructs immutable interactive invocations and opaque member bindings;
   and
7. launches all members.

The runtime then drains one serialized event queue containing:

- peer protocol requests;
- adapter lifecycle and failure events;
- member deadlines;
- group deadline; and
- controller interruption.

Member threads and endpoint listeners may not mutate `StateManager`, attempts,
ledgers, artifacts, variables, or terminal group state.

After every member reaches proved natural `TERMINAL`:

1. validate every frozen member bundle;
2. evaluate the pure settlement over the authored-order member environment;
3. validate the settlement type;
4. finalize all message ledgers and group evidence;
5. drain and close the ingress endpoint and join its workers; and
6. commit one terminal group result, artifact/dataflow publication, and exact
   `current_step` clearance atomically.

Member bundles and message ledgers remain provisional/evidence-only. Only the
settlement value becomes the workflow result.

Any member failure, protocol failure, delivery failure, invalid bundle,
deadline, endpoint failure, or cleanup failure fails the whole node, cleans
and joins all live resources, and publishes no settlement.

## Races

Coordinator event order is authoritative:

| Race | Required result |
| --- | --- |
| two senders target one member | assign one coordinator order; append and offer in that order |
| send vs receiver finish | send first keeps receiver live until ack; finish first rejects send |
| send vs sender finish | send first completes normally; finish first rejects sender as stale |
| member exits before `peer-finish` | fail group; do not infer cooperative completion |
| message recorded, offer fails | retain failure evidence; fail group |
| message offered, outcome append fails | fail group; do not return CLI success |
| receiver acknowledges unknown/wrong-attempt id | reject and fail group |
| duplicate request id, same payload | return original durable receipt |
| duplicate request id, different payload | reject and fail group |
| endpoint closes with waiting clients | resolve every waiter with failure before join |
| controller crash | quarantine whole visit; never reuse endpoint, pane, attempt, or ledger |

There is no attempt transition inside a peer group and therefore no
fresh-to-resume retargeting rule.

## Checkpoint, Retry, And Resume

- The whole form owns one checkpoint.
- Members, interactive clients, messages, endpoints, and ledgers are not
  separately resumable.
- Ordinary resume that finds a running peer-group visit without its exact
  terminal result quarantines the visit before any provider launch.
- Quarantine retains partial ledgers and evidence, clears the exact
  `current_step`, and records a sticky interruption failure.
- A later ordinary resume fails from that marker.
- Only explicit force restart or a new run can start a new group visit, with
  new attempts, endpoint, panes, and empty ledgers.
- Existing root/callee checksums, lexical checkpoint validation, and
  projection integrity remain unchanged.

## Fail-Closed Cases

- target below `2.17`, member count outside `2..8`, duplicate binding, or
  effectful settlement;
- ineligible provider member or non-transportable member/settlement type;
- missing, malformed, or unsupported interactive delivery capability;
- capability inferred from provider name, stdin, tmux, or observation;
- preflight path collision or non-empty ledger/result preimage;
- endpoint creation, listener, prompt snapshot, or empty-ledger publication
  failure;
- member launch, readiness, pane, process, or deadline failure;
- malformed, oversized, non-UTF-8, replay-conflicting, unknown, self,
  ambiguous, stale, not-ready, closing, terminal, or cross-group send;
- sender or receiver attempt mismatch;
- ledger append/fsync failure before or after offer;
- adapter offer failure or use of a forcing key/action;
- missing, duplicate, unknown, or wrong-attempt acknowledgement;
- any finish path that closes or freezes while incoming messages remain
  outstanding instead of returning `pending_messages`;
- finish before a valid typed bundle;
- member natural exit before finish;
- graceful-close or join proof failure;
- ingress drain/unlink/join failure;
- settlement validation failure; or
- crash before atomic terminal publication.

## Compatibility And Versioning

- DSL `2.17` adds one form and one node kind.
- State schema remains `2.1`.
- Existing provider templates and ordinary provider calls are unchanged.
- Existing `with-live-providers` source and serialized v1 artifacts are
  unchanged at every target that accepts them.
- Providers without the new capability remain usable everywhere except the
  peer-group member position.
- There is no YAML spelling.
- Runtime-plan, Semantic IR, source-map, report, and build projections add
  peer-group cases without changing existing cases.

## Verification Strategy

### Capability and adapter

- reject malformed commands, placeholders, key sequences, and forcing keys;
- prove no provider-name or input-mode inference;
- literal UTF-8 and multiline content preservation;
- exact process/pane/attempt binding;
- offer failure, pane loss, process loss, close failure, and timeout;
- prove the adapter never calls cancellation, session resume, or v1
  directive APIs; and
- preserve every existing observation/provider execution test unchanged.

### Ingress and ledger

- CLI/API clients forward only through the endpoint;
- exact sender attribution and target lookup;
- unknown, ambiguous, self, stale, not-ready, closing, and terminal
  rejection with no delivery;
- append/fsync before offer;
- every failure direction after recording;
- idempotent exact replay and conflicting replay rejection;
- concurrent total ordering;
- acknowledgement binding;
- immutable prompt snapshot non-mutation; and
- endpoint drain with no blocked waiter.

### Frontend and IR

- target `2.16` byte-identical v1 non-regression;
- target `2.17` accepts 2, 3, and 8 members and rejects 1 and 9;
- duplicate names, sibling capture, member shape, type, effect, and
  settlement negatives;
- authored member order across WCC, Core, executable, runtime-plan, Semantic
  IR, source map, checkpoint, and build artifacts;
- closed-schema tamper/extra/missing member and path cases; and
- explicit `max_steers: 0`.

### Runtime

- N-way overlap with all attempts/ledgers allocated before launch;
- ready/send/ack/finish success;
- both send/finish race orderings;
- peer failure cancels and joins all;
- selected provisional bundle authority;
- one atomic workflow-state write;
- interruption quarantine; and
- retry creates wholly new identities.

### Real gates

1. One real supported interactive provider reproduces the bounded queue
   probe through the actual adapter:
   `peer-ready -> recorded -> offered -> receiver_acknowledged ->
   peer-finish -> natural close`, with one valid typed bundle and complete
   cleanup.
2. A two-real-member peer group proves one member invokes `peer-send` through
   its ordinary shell tool and the receiver's final typed result reflects the
   message.
3. A three-member `.orc` workflow proves static composition, messaging,
   pure settlement, reports, and one atomic result end to end.
4. Existing v1 real `CONTINUE|STEER` smoke remains green and byte-separated
   from the v1.1 node.

Tests assert behavior and contracts, never literal prompt wording.

## Implementation Sequence

1. Capability schema, fake interactive adapter, and strict validation.
2. Runtime endpoint, thin peer clients, message ledger, and serialized
   coordinator protocol.
3. Cooperative readiness/ack/finish and natural-close process proof.
4. Hand-built `provider_peer_group.v1` runtime fixtures and real one-member
   adapter gate.
5. Target-`2.17` frontend/WCC/IR/source-map/build surface.
6. Real two-member and three-member end-to-end gates.
7. Normative specs, authoring guidance, routing, broad comparison, and
   ordered independent reviews.

Every phase uses TDD and receives specification-compliance then code-quality
review before the next dependent phase.

## Success Criteria

- The design and execution plan receive independent approval.
- Target-`2.16` v1 artifacts and behavior remain unchanged.
- The real adapter proves durable record-before-offer, acknowledged
  turn-boundary delivery, valid bundle authority, and natural cleanup.
- Static `2..8` composition closes through WCC and all executable
  projections.
- The coordinator is the only state/evidence/lifecycle writer.
- Unknown, stale, racing, and partial-delivery cases fail closed.
- Real two- and three-member workflows pass.
- Focused and broad gates show no new failures.

## Stop / Revise Criteria

- The real client requires interruption, cancellation, or a resume command to
  deliver a peer message: stop.
- Readiness, acknowledgement, or finish cannot round-trip through the exact
  member attempt: stop.
- A successful close requires treating screen text, bundle appearance, or
  pane liveness as terminal proof: stop.
- The adapter cannot prohibit forcing key sequences: stop.
- The coordinator cannot preserve one-writer ordering for send/finish races:
  stop.
- Any implementation mutates `provider_supervision.v1` artifacts or v1
  behavior: stop.
- Any mechanism branches on provider, workflow, family, module, or domain
  names rather than a declared adapter schema: stop.

## Deferred Follow-Ons

Separate designs are required for:

- peer messaging combined with v1 `STEER`;
- provider-native duplex transports;
- dynamic group membership;
- per-edge message permissions;
- multiple supervisors or directive arbitration;
- cross-run messages;
- message-driven member checkpointing; and
- unbounded or repeated provider-session control.
