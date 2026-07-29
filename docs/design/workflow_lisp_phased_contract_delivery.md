# Workflow Lisp Phased Contract Delivery

- **Status:** partial. Implementation is activated through `bceb03e4`, but the
  Task 13 stop recorded at `3fc3a09e` still governs and Task 14 has not
  started. The F1/F2 evidence-surfacing correction at `492b1171`, merged into
  this lineage at `92515f98`, still requires
  `Q5_F1_F2_FIX_SPEC_APPROVED` then `Q5_F1_F2_FIX_QUALITY_APPROVED`; both are
  required, not issued. Only after those reviews may the unchanged combined
  invalid-then-valid real-provider gate be re-attempted. No split proof
  satisfies that gate.
- **Kind:** target-2.23 frontend and provider-runtime design
- **Owner:** Workflow Lisp call policy, prompt composition, and provider
  attempt runtime
- **Target:** DSL 2.23
- **Depends on:** implemented Q1/Q2 prompt calculus, the landed and accepted
  Q3 attempt-identity/evidence substrate, and the deadline-aware target-2.17
  interactive-adapter extension with its closed start outcome/proof defined
  below
- **Motivating consumer:**
  `workflows/examples/review_revise_design_docs.orc`
- **Related authority:**
  - `docs/design/workflow_lisp_prompt_calculus.md` (implemented Q1/Q2
    fragment, result, output-position, validation, identity, and resume
    contracts)
  - `docs/design/workflow_lisp_prompt_identity_diagnostics.md` (accepted Q3
    canonical-composition identity contract)
  - `docs/design/workflow_lisp_provider_peer_messaging.md` (implemented
    `interactive_terminal_turn_queue.v1` capability and adapter primitives,
    but not an ordinary-call coordinator)
  - `docs/design/workflow_language_design_principles.md` principles 27–30
  - `specs/providers.md` and `specs/state.md`

## Summary

Q5 adds an explicit, additive call policy for a fragment-backed
`provider-result`: deliver the one canonical composed prompt in a task turn
followed by a materialization turn, while keeping both turns inside one
interactive provider attempt. A failed materialization may be corrected in the
same client without re-offering the task payload.

Target 2.23 is cumulative. Q5 preserves the compiled Q1/Q2 fragment identities,
but its phased attempt evidence requires the accepted Q3 role identity,
one-render trace, binding plan, and attempt-evidence publication substrate.
Q5 has no Q4 judgment dependency. Its design review may proceed in parallel
with Q3 implementation, but Q5 implementation planning and implementation may
not start until the Q3 substrate has landed and passed its ordered acceptance
gates.

Q5 does not reuse `provider_peer_group.v1`, its single-writer group
coordinator, `peer-ready`, `peer-send`, `peer-ack`, or `peer-finish`. Those
contracts settle static groups and cannot be treated as a proven lifecycle for
an ordinary provider call. Q5 owns a new single-attempt
`PhasedProviderAttemptCoordinator`. It reuses only:

- the exact structural provider capability
  `interactive_session_support.schema_version =
  "interactive_terminal_turn_queue.v1"`; and
- the implemented `InteractiveTerminalTurnQueueAdapter` primitives
  `start`, `offer`, `offer_close`, `join`, and `abort`.

Before `start`, the submit binding and candidate endpoint locator are inert
immutable process-local values and reserve no address or resource. The actual
address bind is the first endpoint-resource action and occurs only after a
successful closed start outcome. Cleanup evidence uses one exact
`provider_cleanup_proof:
null|NoBackendAllocationProof|PhasedFailedCleanupEvidence` projection whose
admitted member is selected by cleanup status. The existing adapter
`FailedCleanupProof` remains handle-bound and is never itself ledger evidence.

The ordinary composed path remains the default. Explicit phased delivery fails
closed when the exact capability is absent, malformed, or unsupported; it
does not substitute composed delivery.

## Problem And Goals

The existing canonical prompt `C` asks the provider to perform two kinds of
work at once:

1. make the task judgment expressed by the fragment and its injected context;
   and
2. materialize the required output files and structured result exactly.

Q2 already validates the output-position artifacts and structured bundle
jointly and publishes neither mapping unless both validate. A mechanical
near-miss nevertheless loses the whole ordinary provider attempt. Q5 seeks to
contain that re-spend without weakening Q2 authority.

The design must:

1. offer the task payload exactly once per provider attempt;
2. queue the initial materialization payload durably for the next natural
   client turn;
3. run the complete Q2 artifact-plus-result validation on every submitted
   candidate;
4. permit a bounded materialization-only correction in the same client;
5. publish only one frozen, jointly valid candidate after proved natural
   shutdown;
6. keep canonical prompt bytes, Q1/Q2 compiled fragment identities, composed
   Q3 attempt-identity-v1/functional-v2 evidence, result authority, and
   ordinary completed-boundary reuse unchanged;
7. version phased Q3 attempt identity/evidence so canonical `C` and actual
   ordered deliveries are distinct claims; and
8. provide content-free, non-authoritative evidence for the actual phase
   offers and outcomes;
9. terminalize every failed-start, pre-ingress, T2 cleanup-pending,
   T2 cleanup-finished, and post-proof failure through one closed grammar
   without inferred allocation, duplicate cleanup, or duplicate ingress;
10. project every closed reason through one total diagnostic metadata
    registry; and
11. validate ledger digests from ledger-only inputs by separating
    recomputable seals from opaque equality-bound references;
12. keep pre-start endpoint identity as inert values and allocate/bind the
    actual endpoint only after successful provider start; and
13. project all cleanup evidence through one closed status-selected proof
    union without admitting the adapter's handle-bound proof type.

The irreversible transport point is the adapter returning one validated,
complete, zero-exit `NaturalShutdownProof`. At that instant the coordinator
atomically transitions in memory from `JOINING` to
`JOINED_PENDING_COMMIT`, before attempting to append or fsync
`join_succeeded`. No evidence failure can move that point later or authorize an
abort of the now-terminal handle.

Q5 does not claim that phasing improves task quality. It does not add
same-turn steering, a peer group, an authored prompt queue, a third semantic
phase, dynamic attempt caps, provider-native duplex transport, a new result
channel, or tolerant boundary normalization.

## Target-2.23 Call Policy

### Surface

Target 2.23 adds two closed `provider-result` call-policy keywords:

```lisp
(provider-result providers.design-docs.review
  :prompt (review-design-doc ...)
  :delivery :phased
  :materialization-attempts 2
  :model inputs.review_model
  :effort inputs.review_effort
  :timeout-sec 3600)
```

`:delivery` accepts only the primitive enum values `:composed` and
`:phased`.

- Omitted `:delivery` means composed delivery and preserves the pre-Q5
  compiler, IR, prompt, and runtime path byte-for-byte.
- Explicit `:delivery :composed` selects the same transport behavior while
  remaining explicit program input.
- `:delivery :phased` selects the Q5 coordinator and requires a
  fragment-backed `provider-result` with a non-empty generated result-contract
  suffix.

`:materialization-attempts` is a literal integer. It is legal only with
explicit `:delivery :phased`, has closed range `1..3`, and defaults to `2`
when phased delivery omits it. The value is the total number of candidate
submissions, including the initial submission. Thus `1` permits no correction,
`2` permits one correction, and `3` permits two. It is not a provider-attempt
retry count and cannot be a bound expression.

These are additive author-facing and IR policy surfaces, not hidden runtime
inference. Their primitive enum/integer shapes satisfy principle 29 without
introducing a nominal delivery taxonomy.

### Target and carriage

Every Q5-specific keyword below target 2.23 fails with
`provider_phased_delivery_requires_dsl_2_23`. Target 2.23 is the cumulative
release number after target 2.22 and consumes the landed Q3
attempt-identity/evidence substrate. It does not consume Q4 judgment values,
views, or reporting authority.

When phased delivery is selected, the compiler carries exactly:

```json
{
  "provider_call_policy": {
    "delivery": "phased",
    "materialization_attempts": 2
  }
}
```

Omitted delivery carries neither field. Explicit composed delivery carries
only `"delivery": "composed"` and forbids
`"materialization_attempts"`. Explicit phased delivery always carries both
fields, including the defaulted value `2`.

The two fields remain paired through the typed provider application, Core,
Semantic IR, Executable IR, persisted provider configuration, lexical
checkpoint configuration, and `RuntimeStep`. Classic and WCC lowering must
produce equal values and source ownership. Missing, extra, default-invented,
out-of-range, or unequal carriage fails with
`provider_phased_delivery_carriage_mismatch` before provider preparation.

The present policy participates in existing source, program, checkpoint, and
completed-boundary compatibility just like model, effort, and timeout policy.
The fields do not become workflow values or a separate state authority.

A target-2.23 phased call also carries the existing Q3 field
`prompt_attempt_identity_version` with the exact new value
`workflow_prompt_attempt_identity.v2` and retains the accepted
`compiler_prompt_attempt_binding_plan.v1`. The carrier follows the same typed,
Semantic IR, Executable IR, persisted configuration, lexical checkpoint, and
`RuntimeStep` boundaries. Runtime maps identity v2 to
`workflow_prompt_fragment_snapshot.functional.v3`; there is no authored
evidence-version keyword. A target-2.23 composed call retains identity v1 and
functional evidence v2. Identity/policy target, delivery, or boundary
disagreement is `provider_phased_delivery_carriage_mismatch` before start.

### Capability admission

Phased delivery requires the resolved provider template to declare the exact
closed `interactive_session_support` capability with:

```text
schema_version: interactive_terminal_turn_queue.v1
turn_boundary_messages: true
command: exactly one unescaped ${PROMPT}
message_submit_keys: non-empty closed non-forcing key sequence
graceful_close_text: non-empty normal client command
graceful_close_submit_keys: non-empty closed non-forcing key sequence
```

The compiler checks a statically resolved provider. Runtime repeats validation
against the exact resolved template before attempt allocation. A dynamically
resolved provider is checked at that runtime boundary. Admission is never
inferred from provider name, TTY presence, `session_support`,
`turn_boundary_resume`, peer-group eligibility, or adjacent capabilities.

The refusal codes are:

| Code | Meaning |
| --- | --- |
| `provider_phased_delivery_requires_dsl_2_23` | a Q5 keyword or carrier appears below the target gate |
| `provider_phased_interactive_capability_missing` | the resolved template declares no `interactive_session_support` |
| `provider_phased_interactive_capability_invalid` | the declared capability is malformed or not the exact supported schema |
| `provider_phased_delivery_policy_invalid` | the delivery enum, literal cap, legality pairing, or fragment/result-suffix requirement is invalid |
| `provider_phased_delivery_carriage_mismatch` | typed/Core/IR/persisted/checkpoint/runtime policy or attempt-identity/evidence version carriage is missing, extra, or unequal |
| `provider_phased_isolation_unsupported` | the step requires provider isolation (`provider_isolation_attempt_factory` configured); phased delivery excludes isolation-required attempts in this tranche |

Isolation-required attempts are excluded fail-closed rather than supported:
`specs/io.md` places the isolated bundle parent in an invocation-private
scratch directory and begins brokerage only after the provider and every
descendant are quiescent, which contradicts Q5's mid-attempt
validate/freeze/reset of live candidates. Lifting the exclusion is a
separate future io.md/providers.md brokerage amendment, not part of this
design.

A phased attempt is one process with one environment: it receives the
standard `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` binding at launch per
`specs/providers.md`, unchanged. Early-write discipline is owned by the
candidate-absence preflight and the submit protocol, not by environment
scoping.

An explicit phased call receiving any of these diagnostics does not execute a
composed invocation.

### Deadline-aware adapter extension prerequisite

The shipped target-2.17 adapter gives `join` and `abort` an absolute monotonic
deadline, but `start`, `offer`, and `offer_close` currently create independent
configured operation deadlines. Q5 cannot enforce one whole-attempt deadline
through that interface. Before Q5 implementation planning, the production
adapter, its public protocol, and the target-2.17 peer coordinator must land
this additive signature extension:

```text
start(invocation, *, deadline) -> InteractiveTerminalStartOutcome
offer(handle, literal_message, *, deadline) -> OfferReceipt
offer_close(handle, *, deadline) -> CloseOfferReceipt
join(handle, deadline) -> NaturalShutdownProof
abort(handle, deadline) -> FailedCleanupProof
```

`FailedCleanupProof` above is the existing target-2.17 adapter type and remains
unchanged:

```text
FailedCleanupProof =
  {"disposition":"failed_cleanup",
   "handle_id":H,
   "pane_absent":B,
   "server_absent":B,
   "cleanup_complete":B,
   "error_code":S|null}
```

`H` is the exact non-empty opaque identity of the `InteractiveMemberHandle`
passed to `abort`, `B` is a JSON Boolean, and `S` is a non-empty token from the
adapter's closed error-code registry. Q5 does not rename, widen, make
content-free, or otherwise change this interface. Existing target-2.17 callers
continue to receive and validate the same handle-bound proof. Q5 may project
that proof only after the active-handle check defined below, following the
existing `PeerFailedCleanupEvidence.from_proof` boundary rather than reusing
the adapter type as persisted evidence.

Every `deadline` is one finite absolute timestamp from the adapter's monotonic
clock. For each backend action inside `start`, `offer`, or `offer_close`, the
adapter passes:

```text
min(configured_operation_timeout, deadline - monotonic_now)
```

after proving the remainder is positive. If the caller deadline is already
exhausted, the adapter starts no backend action and raises exactly
`offer_timeout` or `close_offer_timeout` for those selected operations. For
`start`, the same pre-call condition returns the closed failed outcome with
`error_code: "start_timeout"` and exact
`none/not_required/true/NoBackendAllocationProof`; it never escapes as an
exception. If the deadline expires between start backend actions, no later
backend action starts and the adapter returns the applicable exact
`possible_or_allocated` completed-or-incomplete cleanup outcome with
handle-free `PhasedFailedCleanupEvidence`, never `FailedCleanupProof`. A
backend helper, subprocess, waiter, or adapter-owned thread may not outlive the
supplied caller deadline. Failure cleanup is separately bounded by the same
remaining caller deadline; it may report incomplete cleanup but may not create
a fresh operation-duration budget.

This extension is a prerequisite, not a Q5-local wrapper. Its executable proof
must show:

- the existing target-2.17 peer-group fixtures and real adapter gate remain
  behavior-compatible when the peer coordinator supplies the already-owned
  member/group deadline, including unchanged handle-bound
  `abort -> FailedCleanupProof`;
- every possible-or-allocated failed start carries handle-free
  `PhasedFailedCleanupEvidence`, because it returns no handle;
- start, initial offer, retry offer, and close offer each receive less
  remaining time than the configured adapter operation timeout and every
  backend call receives only that smaller remainder;
- deadline exhaustion before each operation makes zero backend calls; start
  returns its exact no-allocation failed outcome and offer/close return their
  named timeout failures; and
- no backend action or background waiter remains live after the coordinator
  deadline.

Passing a per-operation relative budget instead of an absolute deadline would
be equivalent only if the public interface names that alternative explicitly,
converts it once against the adapter's monotonic clock, and proves the same
no-outliving invariant. One implementation may not accept both shapes
ambiguously.

## Canonical Byte Cut

### One rendering, two slices

The existing prompt owners first render one canonical composed prompt `C` as
strict UTF-8. Q5 does not independently render a task prompt and a contract
prompt. It selects one byte cut at the exact call to the existing
output-contract suffix owner.

Let `P` be the complete prompt bytes immediately before
`PromptComposer.apply_output_contract_prompt_suffix`, and let `B` be the
existing ordered contract blocks. `P` already contains, with their current
separators and position rules:

- the rendered fragment template and all substituted text/value/path slots;
- the Q1 required-document dependency block, including its exact instruction
  and framing;
- any other admitted dependency contribution; and
- any consumed-artifact contribution, whether disabled, empty, prepended, or
  appended.

The output-contract owner constructs the suffix delta `S` exactly as today:

```text
if P is empty:          S = B
else if P ends in LF:   S = LF || B
else:                   S = LF || LF || B
```

For a Q2 call, `B` is the exact output-position block followed by `LF || LF`
and the exact structured-result block. For a Q1-only call, `B` is the exact
structured-result block. Authored `ReturnSpec` description, format hint,
example, guidance context, and variant guidance remain inside the existing
structured-result block whenever present.

Q5 defines:

```text
T1 = P
T2 = S
C  = T1 || T2
```

The equality is byte-for-byte: no normalization, newline repair, re-rendering,
loss, overlap, or duplicated separator is permitted. `T1` and `T2` are slices
of one rendering, not new prompt authorities.

For the motivating consumer, the `review_report_target_path` value has the two
appearances Q2 already requires: its authored fragment placeholder in `T1`
and its generated expected-output row in `T2`. Phasing adds no third
appearance. Q1 permits repeated rendered placeholders in other fragments, so
the general rule is byte partition, not a universal occurrence count.

### Protocol bytes are outside `C`

Provider-visible phase framing is necessary to explain turn order and the
attempt-bound submit command. It is not silently inserted into either
canonical slice. A versioned runtime renderer,
`provider_phased_protocol_frame.v1`, produces:

- `F_task`, the task-turn frame;
- `F_materialization`, the initial materialization/submit frame; and
- `F_retry(d)`, the retry frame containing bounded named validation
  diagnostics `d`.

Each frame owns every separator needed to join itself to its canonical slice.
The exact delivered turn bytes are:

```text
task turn:                    F_task            || T1
initial materialization:     F_materialization || T2
materialization correction:  F_retry(d)        || T2
```

The protocol renderer must expose the exact frame bytes, canonical-slice
bytes, and final concatenated bytes from the same operation. The phase ledger
records byte counts and SHA-256 digests for all three, plus the declared
submit-key sequence digest. Runtime framing, the submit command instruction,
and diagnostic prose therefore remain fully accounted without changing `C` or
the Q1/Q2 compiled identities. The same frame/turn projections enter the
phased Q3 v2 actual-delivery array and composition seal.

Tests must assert the byte algorithm and digests, not literal English prompt
phrasing.

## Principle-30 Classification

Phasing changes when the generated contract suffix arrives. It does not
magically remove mechanical prose already authored into the fragment.

Authored `ReturnSpec` guidance follows this rule:

- guidance that resolves a genuine semantic ambiguity remains authored
  guidance and is retained verbatim in `T2`;
- guidance that merely restates a mechanically checkable type, path, or
  token rule is `p30_missing_mechanism` debt and remains until a separate
  accepted mechanism absorbs it; and
- Q5 never deletes or reclassifies guidance based on guessed intent.

The motivating `review-design-doc` has no authored `ReturnSpec` guidance. Its
residual template lines classify as follows:

| Template obligation | Classification | Missing mechanism / reason retained |
| --- | --- | --- |
| the standalone `{review_report_target_path}` occurrence | `p30_missing_mechanism` | Q2 requires an output-position slot to satisfy the ordinary rendered-placeholder rule even though the generated contract also carries the path |
| “Treat structured inputs and artifact paths as authority” | `semantic_ambiguity` | this tells the reviewer how to weigh conflicting evidence; a validator cannot choose that judgment |
| APPROVE / REVISE / BLOCKED meanings and concrete-finding expectations | `semantic_ambiguity` | these are the task’s judgment criteria |
| exact `ReviewFindings.v1` spelling and rejected spelling variants | `p30_missing_mechanism` | `ReviewFindings.schema_version` is still `String`, not an exact literal/refinement normalized by the result boundary |
| the referenced findings file must be an object with top-level `items` | `p30_missing_mechanism` | the result contract carries a relpath but does not validate the referenced JSON file’s schema in the same boundary |

All these authored bytes remain in `T1`. Phasing therefore does not remove the
motivating consumer’s literal/schema or referenced-artifact debt. Tolerant
normalization, literal-refined fields, referenced-artifact schema validation,
and output-slot placeholder discharge remain separate design questions.

## `PhasedProviderAttemptCoordinator`

### Ownership boundary

One `PhasedProviderAttemptCoordinator` owns one ordinary provider attempt from
allocation through result publication. It is the sole writer for:

- the immutable attempt-bound submit-binding value and candidate endpoint
  locator, and the submit endpoint only after it is actually allocated;
- phase lifecycle state;
- `provider_prompt_phase_ledger.v1`;
- candidate digest manifests and frozen candidate bytes;
- adapter calls and receipts; and
- final result/artifact publication.

It also owns every listener, request worker, queued submit, and local endpoint
resource. No terminal coordinator result is externally observable until
ingress is disabled, every admitted or queued request has received its exact
terminal receipt, the listener is closed, and every coordinator-owned worker
has joined.

The provider-visible command is exactly:

```text
orchestrator provider-materialization-submit
```

It takes no run id, step id, attempt ordinal, path, pane target, or endpoint
argument. A thin client reads an opaque
`ORCHESTRATOR_PHASED_PROVIDER_BINDING`, sends one bounded request with a
client request id to the attempt-bound local endpoint, waits for the
coordinator receipt, and never writes workflow state, the phase ledger, or
adapter input.

The coordinator does not construct a one-member peer group. It does not call
peer protocol commands or mutate peer-group ledgers, settlement state, or
resume state.

### Candidate set and preparation

The candidate set is closed before launch:

1. resolve every Q2 `expected_outputs.path` and the one structured
   `output_bundle.path` or `variant_output.path`;
2. run the existing Q2 name, containment, pairwise destination, and
   bundle-alias checks;
3. require each exact candidate file path to be absent; a pre-existing path
   fails with `provider_phased_candidate_path_preexisting`; and
4. retain the ordered resolved path set in private coordinator state.

The absence requirement makes retry cleanup safe and makes “retry must
recreate every candidate” mechanically checkable. Q5 never deletes a
pre-existing user file and never scans or clears an output directory.

The runtime validates call-policy carriage and provider capability, allocates
the existing root-owned provider-attempt ordinal, consumes the Q3 one-render
trace/binding plan to build and validate the five roles plus canonical `C` in
memory, creates and fsyncs the phase-ledger header, derives an opaque submit
binding and a candidate endpoint locator as immutable process-local values,
and prepares the interactive invocation. Those two values are inert data:
deriving them creates no socket or address bind, port or pathname reservation,
filesystem entry, listener, worker, thread, descriptor, subprocess, or other
coordinator-owned endpoint resource. The candidate locator is only an
unbound namespace-and-nonce description, not an allocated or usable endpoint
address. The invocation carries only the opaque binding value.

Only after a successful closed start outcome may the coordinator begin
endpoint allocation. Entry to that operation creates its local endpoint owner
and atomically changes ingress from `NOT_ALLOCATED` to `NOT_STARTED`; it then
chooses and binds the actual address against the candidate locator, creates
the listener/workers, and activates the binding-to-endpoint association before
the initial materialization offer. An allocation failure, including loss of
an address race, maps to `submit_endpoint_allocation_failed`, offers no turn,
and terminalizes through T1 so any partial local endpoint resources receive
the one truthful finished-or-failed shutdown outcome. Before this post-start
operation, T0 discards the two inert values and has exactly zero
coordinator-owned endpoint resources. Thus every failed start is structurally
T0 `ingress: NOT_ALLOCATED`, even though its provider cleanup may be complete
or truthfully incomplete. The terminal functional-v3 record cannot be sealed
yet because no actual delivery exists; it is published from the immutable
coordinator trace only after the delivery sequence closes as defined below.
Failure before `start` launches no client.

### Lifecycle

The closed lifecycle is:

```text
ALLOCATED
  -> STARTING
  -> LIVE
  -> INITIAL_MATERIALIZATION_QUEUED
  -> VALIDATING
       -> RETRY_QUEUED -> VALIDATING        (while submissions remain)
  -> VALID_FROZEN
  -> CLOSING
  -> INGRESS_STOPPING
  -> JOINING
  -> JOINED_PENDING_COMMIT
  -> PUBLISHED
```

Any state before the adapter returns a validated successful natural-join proof
may enter `TERMINALIZING`. That state owns two monotonic substate variables:
`provider_cleanup = NOT_REQUIRED|PENDING|COMPLETE|INCOMPLETE` and
`ingress = NOT_ALLOCATED|NOT_STARTED|STARTED|COMPLETE|INCOMPLETE`. A live
pre-proof handle takes exactly one `abort(handle, deadline)` call. A failed
start takes zero later `abort` calls because it returns no live handle, but
absence of a handle is not cleanup evidence. Its closed start outcome below
sets the cleanup substate from adapter-owned allocation and proof facts. The
cleanup phase always has exactly one logical `cleanup_finished` outcome
overall, including `NOT_REQUIRED` and `INCOMPLETE`; a later failure consumes
an already-finished outcome instead of emitting it again. An allocated
endpoint takes at most one `ingress_shutdown_started` action and at most one
corresponding success-or-failure outcome. Terminalization consults these
substates instead of re-entering an earlier action, so a failure during or
after ingress never emits a duplicate ingress pair.

The deadline-aware adapter prerequisite replaces the exception-only start
boundary with this exact closed tagged outcome:

```text
InteractiveTerminalStartOutcome =
  {"status":"started",
   "handle":InteractiveMemberHandle}
| {"status":"failed",
   "error_code":S,
   "backend_allocation":"none"|"possible_or_allocated",
   "cleanup_status":"not_required"|"completed"|"incomplete",
   "provider_zero_survivor_proven":B,
   "proof":NoBackendAllocationProof|PhasedFailedCleanupEvidence}
```

`S` is one non-empty token from the adapter's closed error-code registry and
`B` is a JSON Boolean. The two proof objects are exact and content-free:

```text
NoBackendAllocationProof =
  {"disposition":"no_backend_allocation",
   "backend_resource_allocated":false,
   "proof_complete":true}

PhasedFailedCleanupEvidence =
  {"disposition":"failed_cleanup",
   "pane_absent":B,
   "server_absent":B,
   "cleanup_complete":B,
   "error_code":S|null}
```

`PhasedFailedCleanupEvidence` is a Q5 handle-free evidence type, analogous to
the implemented `PeerFailedCleanupEvidence`; it is not the adapter's existing
handle-bound `FailedCleanupProof`. A failed start has no
`InteractiveMemberHandle`, so the `possible_or_allocated` branch constructs
this evidence directly from the adapter's internal cleanup observations. It
cannot call `abort`, invent a handle identity, or return
`FailedCleanupProof`.

`NoBackendAllocationProof` is adapter-issued, immutable, and obtainable from
the adapter's created state without a backend call. Pre-start coordinator
failure embeds that exact proof as
`cleanup_finished.provider_cleanup_proof`; the `none` failed-start outcome
reuses the same proof authority. Coordinator knowledge that it has no handle
is never a substitute.

The union admits exactly three failed-start combinations:

1. `none`, `not_required`, and true require
   `NoBackendAllocationProof` exactly. This is an explicit adapter assertion
   that no server, pane, helper, or other backend resource was allocated;
   returning no handle, throwing before handle construction, or failing a
   caller-side precheck proves none of those facts.
2. `possible_or_allocated`, `completed`, and true require
   `PhasedFailedCleanupEvidence` with `pane_absent`, `server_absent`, and
   `cleanup_complete` all true and `error_code` null.
3. `possible_or_allocated`, `incomplete`, and false require
   `PhasedFailedCleanupEvidence` with at least one proof Boolean false or a
   non-null closed `error_code`. No producer may emit `not_required` or true
   for this branch.

No other field, combination, null proof, thrown start exception, or
producer-invented allocation state is legal. On success the handle reference
is the exact adapter authority and no cleanup fields are present. On failure
the proof is the exact authority and no handle field is present. The
production error `interactive_terminal_start_cleanup_incomplete` maps
deterministically to combination 3 with that exact token in both outcome
`error_code` and `PhasedFailedCleanupEvidence.error_code`; unavailable
pane/server absence is represented by false, not by omission. The coordinator
maps adapter `completed` to ledger `cleanup_status: "complete"` and otherwise
preserves the start outcome verbatim.

After the adapter returns a validated successful natural-join proof, the
coordinator atomically enters `JOINED_PENDING_COMMIT` in memory before any
`join_succeeded` ledger append. That state may transition only to `PUBLISHED`
or directly to `FAILED`: the adapter handle is already terminal, so every
later failure makes zero `abort` calls, emits no `cleanup_finished`, and does
not repeat ingress shutdown. `PUBLISHED` and `FAILED` are externally terminal
only after the endpoint terminalization contract below has either proved
zero coordinator-owned survivors or recorded the truthful
`endpoint_shutdown_status: "incomplete"` failure. A materialization retry is a
submission transition inside the same provider attempt; it does not allocate
another provider attempt or restart the task turn.

The successful control flow is:

1. The coordinator records `task_start_requested`; deadline-aware `start`
   launches the exact attempt with `F_task || T1` and returns the closed
   `started` outcome; then the coordinator records `task_started` with the
   content-free receipt projection. A closed failed outcome instead records
   `task_start_failed`, projects its proof, and enters T0 without guessing
   from handle absence.
2. Without waiting for or inferring task completion from pane text, the
   coordinator enters and performs the actual-address bind and endpoint
   allocation described above, then appends and fsyncs
   `turn_offer_requested` for `F_materialization || T2`. This is the first
   endpoint-resource action. An address race or any other allocation failure
   is `submit_endpoint_allocation_failed`, offers no turn, and terminalizes
   through T1 with complete or truthfully incomplete endpoint shutdown.
3. It calls deadline-aware `offer` on the exact handle and appends and fsyncs
   `turn_offered` or `turn_offer_failed`. An offer receipt proves only exact
   client input submission. The client itself holds the input until its next
   natural turn boundary.
4. In the materialization turn, the provider recreates every candidate file
   and invokes `orchestrator provider-materialization-submit`.
5. The coordinator serializes the request, assigns a one-based
   `submission_ordinal`, snapshots exact candidate identities and digests, and
   runs the complete Q2 validation in fixed
   output-position-then-structured-result order. Neither local validation
   mapping is published.
6. If both contracts validate, the coordinator copies and seals the exact
   candidate bytes into a private immutable frozen candidate, rechecks source
   identities/digests against the snapshot, appends `candidate_frozen` with
   the complete embedded manifest, and enters `VALID_FROZEN`.
7. While the submit request remains active, it records
   `close_offer_requested`, resolves the request as `accepted_closing`, and
   waits for that receipt to flush to the submit client. `accepted_closing`
   means that the submission was accepted and the coordinator durably
   committed to an immediate graceful close; it does not claim that the close
   has already been offered or executed. If the receipt cannot be flushed,
   the coordinator offers no graceful close and enters T1 terminalization.
   An endpoint protocol closure is `submit_lifecycle_invalid`; expiry while
   delivering the active submit's receipt is
   `deadline_exhausted_during_submit`.
8. Only after the accepted-closing receipt is flushed, the coordinator calls
   deadline-aware `offer_close`, durably records `close_offered`, disables
   ingress, returns the exact terminal failed receipt for every later or queued
   submit, closes the listener, and joins all endpoint workers. The current
   provider turn can finish, allowing the queued normal close to reach the next
   natural boundary. Only a complete `ingress_shutdown_finished` projection
   permits `join` to begin.
9. The coordinator calls `join` under the remaining whole-step deadline and
   accepts only a complete zero-exit `NaturalShutdownProof`. Receipt of that
   validated proof atomically changes the in-memory lifecycle from `JOINING`
   to `JOINED_PENDING_COMMIT` before any ledger write. It then attempts to
   append and fsync `join_succeeded`. That event proves transport shutdown
   only; it is not result, publication, or step-success evidence.
10. If the `join_succeeded` append/fsync fails, the coordinator transitions
    directly from `JOINED_PENDING_COMMIT` to `FAILED`, makes zero `abort`
    calls, and publishes no result or artifact mapping. When the ledger channel
    can still accept a later canonical row, `terminal_failed` carries the
    validated natural-shutdown proof as non-authoritative provisional failure
    material; otherwise the truthful ledger ends at `join_started`.
11. In `JOINED_PENDING_COMMIT`, the coordinator restores or verifies every
   exact bound destination from the frozen bytes, seals and publishes the
   functional-v3 attempt record from the immutable delivery trace, and
   performs one atomic workflow-state commit containing the structured
   result, merged disjoint artifact map, terminal step state, and
   `current_step` clearance.
12. A successful state commit makes the step authoritative and transitions
    to `PUBLISHED`; `publication_succeeded` is appended before returning the
    coordinator success receipt when the evidence channel remains writable.
    The state commit, not that ledger row, is completion authority.
13. Functional-v3 evidence publication, frozen restoration, verification, or
    state-commit failure transitions directly from
    `JOINED_PENDING_COMMIT` to `FAILED`. It retains frozen and any restored
    provisional candidate bytes as non-authoritative evidence, publishes no
    result or artifact mapping, and never calls `abort` on the terminal
    handle. The coordinator appends `publication_failed` and then
    `terminal_failed` only if the ledger channel is still writable. A
    filesystem or state failure may make those appends impossible, so the
    design does not claim that post-join publication failure is always
    recordable in the ledger.

Every failure before a validated natural proof preserves its first diagnostic
as primary and invokes the boundary-indexed terminalizer defined with the
ledger grammar below. A live handle receives exactly one bounded `abort`.
That existing call returns handle-bound `FailedCleanupProof`. Before using its
cleanup observations, the coordinator validates its exact type and closed
fields, requires `proof.handle_id` to equal the exact active handle identity
passed to `abort`, and validates its disposition, Booleans, and closed
error-code token. Only then does it construct
`PhasedFailedCleanupEvidence` by copying the five content-free fields and
omitting `handle_id`. A wrong type or missing/mismatched handle identity is
`adapter_cleanup_failed` supplemental evidence, forces cleanup
`incomplete/false`, and produces null `provider_cleanup_proof`; neither the
raw nor invalid adapter proof may enter the ledger.

Failed start performs no later abort and records `cleanup_finished` from its
already handle-free start outcome: `not_required` only with the explicit
no-allocation proof, `complete` only with complete
`PhasedFailedCleanupEvidence`, and otherwise `incomplete`. The production
`interactive_terminal_start_cleanup_incomplete` path is therefore T0 with
truthful incomplete/false provider cleanup, not structural absence. The
terminalizer then completes the one allocated ingress shutdown if it has not
started, finishes only the already-started shutdown if it has, or reuses the
already-durable zero-survivor projection if ingress is complete. Endpoint
terminalization never calls an adapter primitive. Every endpoint request wait
is capped by the whole-attempt deadline, so expiry releases its worker before
the coordinator's final local join.

`cleanup_finished` names completion of the cleanup decision, not proof of
successful cleanup. Its one proof slot is
`provider_cleanup_proof:
null|NoBackendAllocationProof|PhasedFailedCleanupEvidence`; the cleanup status
selects the exact legal member below. If abort returns a valid handle-bound
`FailedCleanupProof`, the coordinator stores only its handle-free
`PhasedFailedCleanupEvidence` projection. If abort raises, times out, is not
called because its before-check expired, returns no proof, or returns a proof
whose type, fields, or handle identity fail the validation above, the
post-start contract permits null in that slot, records
`cleanup_status: "incomplete"`, a closed supplemental cleanup diagnostic, and
`provider_zero_survivor_proven: false`; no proof object is invented. Likewise,
failure to complete endpoint shutdown records
`endpoint_shutdown_status: "incomplete"` rather than a false zero-survivor
claim. Either condition is terminal failure, can never be hidden by success,
and still runs every remaining fail-safe close/join action permitted by the
same deadline. A terminal row is evidence of the truthful outcome, not
permission to abandon a thread or subprocess.

The projection examples are closed:

| Cleanup source | Required validation | `provider_cleanup_proof` |
| --- | --- | --- |
| failed start, `none/not_required/true` | exact `NoBackendAllocationProof` in the closed start outcome | that exact handle-free proof |
| failed start, `possible_or_allocated/completed/true` | exact all-true/null-error `PhasedFailedCleanupEvidence` in the closed start outcome | that exact handle-free evidence |
| failed start, `possible_or_allocated/incomplete/false` | exact incomplete `PhasedFailedCleanupEvidence` in the closed start outcome | that exact handle-free evidence |
| post-start abort returns complete or incomplete `FailedCleanupProof` | exact existing adapter type and fields; `handle_id` equals the active handle passed to abort | newly constructed `PhasedFailedCleanupEvidence` containing only disposition, three cleanup Booleans, and error code |
| post-start abort returns wrong type, malformed fields, or missing/mismatched `handle_id` | fail `adapter_cleanup_failed`; never trust cleanup observations | null |
| post-start abort is not called because its before-check observes expiry, raises, times out, or returns no proof | applicable closed supplemental cleanup diagnostic | null |

Candidate files are provisional workspace files before step commit. Current
provider isolation does not make arbitrary workspace writes invisible. The
contractual guarantee is that no candidate mapping, structured result,
artifact lineage, successful step state, or routing value becomes
authoritative or state-visible before a valid frozen candidate, natural close,
and the atomic state commit.

### Invalid materialization

Every submit runs both sides of Q2 validation even when one side is already
invalid, so evidence distinguishes at least:

- invalid or missing expected artifact with an otherwise valid structured
  result; and
- valid expected artifacts with an invalid or missing structured result.

For an invalid submission, the coordinator:

1. appends and fsyncs `validation_rejected` with closed phased-diagnostic
   wrappers that retain each exact existing Q2 violation type;
2. embeds the complete closed
   `provider_phased_candidate_digest_manifest.v1` defined below in that
   rejection row; there is no separate manifest file or digest-only
   reference;
3. removes only the exact bound regular candidate files and proves every
   bound path absent; any identity race, non-regular replacement, unlink
   failure, or remaining path fails terminally with
   `provider_phased_candidate_reset_failed`; and
4. requires the next submission to recreate every candidate from absence.

If submissions remain, it renders `F_retry(d) || T2`, appends and fsyncs
`retry_queued` and the retry offer-request row, calls `offer`, appends and
fsyncs the offer outcome, and only then returns a `retry_queued` submit
receipt. The task payload is not included. The provider stays live.

If no submission remains, the coordinator records
`provider_phased_materialization_attempts_exhausted`, clears the exact
provisional candidates, aborts and joins cleanup, and publishes no result or
artifact mapping.

### Submit receipts and replay

`provider_phased_submit_receipt.v1` has the closed status set
`retry_queued|accepted_closing|failed`. It binds the exact attempt, client
request id, submission ordinal, configured total, remaining submissions, and
one complete `provider_phased_delivery_diagnostic.v1` or null. It contains no
prompt, result, artifact, or diagnostic free text. `accepted_closing` asserts
acceptance plus a durable coordinator commitment to immediate graceful close;
it does not assert that the close action has already run.

An exact duplicate request id and payload returns the prior durable receipt
without another validation or offer. Reuse of a request id with a different
payload, a foreign/stale binding, or a submit in the wrong lifecycle state is
`provider_phased_submit_protocol_invalid`.

## Evidence And Identity

### Canonical identities remain canonical

Q5 does not change `compiled_prompt_fragment_identity.v1` or `.v2`. Those Q1/Q2
digests continue to identify the compiled fragment program and output role,
not the ordered turns.

Q5 does not reuse `workflow_prompt_attempt_identity.v1` for phased delivery.
That Q3 schema names `final_prompt` as the exact prompt supplied to
`ProviderExecutor.prepare_invocation`. Recording `C` there would falsely claim
that the composed bytes were delivered as one prompt even though the adapter
starts with `F_task || T1` and later offers one or more materialization turns.

Target 2.23 therefore adds the exact carrier
`prompt_attempt_identity_version =
"workflow_prompt_attempt_identity.v2"` and evidence schema
`workflow_prompt_fragment_snapshot.functional.v3` for phased calls only. The
five Q3 roles remain, but the provider-policy role uses
`workflow_prompt_attempt_provider_policy.v2` with this exact payload:

```json
{
  "provider_name": "codex",
  "model": "gpt-5",
  "effort": "high",
  "timeout_sec": 1800,
  "transport": {
    "kind": "interactive_terminal_turn_queue",
    "schema_version": "interactive_terminal_turn_queue.v1"
  },
  "phased_call_policy": {
    "delivery": "phased",
    "materialization_attempts": 2
  }
}
```

`provider_name`, `model`, `effort`, and `timeout_sec` keep Q3's existing
canonical meanings and nullability. `transport.kind`, its schema token, and
the two phased-call-policy fields are exact. The payload contains no provider
command token, argv, environment, submit or close text, key token, pane or
endpoint value, prompt/frame byte, credential, or secret. A change in this
role remains `provider_policy_drift`.

`workflow_prompt_attempt_identity.v2` has exactly:

```json
{
  "schema_version": "workflow_prompt_attempt_identity.v2",
  "roles": {
    "fragment_program": {},
    "resolved_bindings": {},
    "injected_dependencies": {},
    "runtime_contributions": {},
    "provider_policy": {}
  },
  "canonical_composed": {
    "bytes": 0,
    "sha256": "sha256:..."
  },
  "actual_deliveries": [
    {
      "delivery_ordinal": 0,
      "phase": "task",
      "submission_ordinal": null,
      "protocol_frame": {
        "bytes": 0,
        "sha256": "sha256:..."
      },
      "canonical_slice": {
        "bytes": 0,
        "sha256": "sha256:..."
      },
      "delivered_turn": {
        "bytes": 0,
        "sha256": "sha256:..."
      },
      "submit_keys": {
        "count": 0,
        "sha256": "sha256:..."
      }
    }
  ],
  "composition_sha256": "sha256:..."
}
```

The five role keys and wrappers remain the closed Q3 set except for the
provider-policy v2 wrapper above. `canonical_composed` is the exact length and
digest of `C`; it is not called `final_prompt` and is not a delivery claim.
`actual_deliveries` contains one row for each successfully started or offered
provider turn, in exact adapter-receipt order. `delivery_ordinal` is
contiguous from zero:

- row zero is `phase: "task"`, `submission_ordinal: null`, and binds
  `F_task`, `T1`, and `F_task || T1`; its submit-key projection is the digest
  of canonical JSON `[]`, exactly `count: 0` and
  `sha256:4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`,
  because `start` supplies prompt bytes through the capability command rather
  than a queued key sequence;
- the next row is `phase: "initial_materialization"`,
  `submission_ordinal: 1`, and binds `F_materialization`, `T2`, and their
  concatenation; and
- each later row is `phase: "retry_materialization"` with the exact next
  one-based submission ordinal and binds that retry's exact `F_retry(d)`,
  the unchanged `T2`, and their concatenation.

An attempted start or offer without a success receipt is not an actual
delivery row. The phase ledger still records its requested digest envelope and
failure. For offered materialization turns, the `submit_keys` digest covers
canonical JSON of the exact declared ordered key-token sequence and stores
only its count and digest, not the key tokens. The row equations are checked
byte-for-byte:

```text
delivered_turn.bytes  =
  protocol_frame.bytes + canonical_slice.bytes
delivered_turn.sha256 =
  sha256(protocol_frame_bytes || canonical_slice_bytes)
```

The v2 composition seal is the SHA-256 of canonical JSON containing exactly
`schema_version: "workflow_prompt_attempt_composition.v2"`, the five ordered
role digests, `canonical_composed`, `protocol_schema_version:
"provider_phased_protocol_frame.v1"`, and the complete ordered
`actual_deliveries` array. Thus the seal covers the actual turn order and every
protocol-frame digest rather than implying that `C` was one delivered prompt.

The v3 evidence record has exactly these top-level keys:

```text
schema
record_kind
run
compiler_contract
attempt
authored_rows
canonical_groups
instruction
injection
compiled_prompt_fragment_identity
canonical_composed
prompt_attempt_identity
record_sha256
```

`schema` is exactly
`workflow_prompt_fragment_snapshot.functional.v3`;
`record_kind` is `prompt_snapshot`. `run`, `compiler_contract`, `attempt`,
`authored_rows`, `canonical_groups`, `instruction`, and `injection` retain the
closed functional-v2/Q3 meanings. `compiled_prompt_fragment_identity` remains
exactly v1 or v2 as selected by Q1/Q2. `canonical_composed` has exactly
`bytes` and `sha256` and equals the v2 identity's object byte-for-byte.
`prompt_attempt_identity` is the complete v2 identity above.
`record_sha256` uses the existing functional-record seal over the complete
record without that field. `final_prompt` is forbidden.

V3 validates the retained dependency/fragment projection under its existing
rules, proves `canonical_composed` from the single canonical composition
operation, validates every Q3 binding-plan/role correspondence, and then
validates the actual-delivery rows and v2 composition seal. It is sealed from
the coordinator's immutable in-memory composition/delivery trace; it is never
reconstructed by parsing the phase ledger. On the success path it is published
after natural join and before the authoritative state commit. If that
publication fails, the coordinator follows post-join publication failure:
terminal failure, no abort, no result authority. On an earlier failed attempt,
the coordinator may publish the same schema over the successfully delivered
prefix only when the evidence channel remains writable; absence of that
best-effort terminal record does not erase the phase-ledger prefix or authorize
recovery.

### Q3/Q5 report and comparison amendment

Q5 replaces the report-only
`workflow_prompt_context_report.v1` projection with the exact additive
`workflow_prompt_context_report.v2` projection. This is a versioned report/API
change, not an execution, evidence, state, checkpoint, result, or resume
change. The report's top-level `run`, `progress`, `steps`, and `prompt_context`
keys remain exact; only `prompt_context.schema_version` changes to v2 and the
fixed attempt-row `identity` projection is versioned as defined here.

Every non-null `identity` has exactly:

```json
{
  "identity_version": "workflow_prompt_attempt_identity.v2",
  "composition_sha256": "sha256:...",
  "legacy_final_prompt_sha256": null,
  "canonical_composed": {
    "bytes": 0,
    "sha256": "sha256:..."
  },
  "actual_deliveries": [],
  "role_sha256": {
    "fragment_program": "sha256:...",
    "resolved_bindings": "sha256:...",
    "injected_dependencies": "sha256:...",
    "runtime_contributions": "sha256:...",
    "provider_policy": "sha256:..."
  }
}
```

The six top-level identity keys and five `role_sha256` keys are exact.
`identity_version` is exactly `workflow_prompt_attempt_identity.v1` or `.v2`.
For v1, `legacy_final_prompt_sha256` is the validated
`prompt_attempt_identity.final_prompt.sha256`,
`canonical_composed` is null, and `actual_deliveries` is null. For v2,
`legacy_final_prompt_sha256` is null, `canonical_composed` is the exact
validated `{bytes, sha256}` object, and `actual_deliveries` is the complete
validated ordered array, including an empty successfully-delivered prefix for
a best-effort failed-attempt snapshot. No report field is named
`final_prompt_sha256`; canonical `C` is never projected as a delivered prompt.
`composition_sha256` and every role digest come from the strictly validated
identity of the same record.

Record qualification and fixed row behavior are:

| `record_status` | Qualified evidence | `identity` | `comparison` |
| --- | --- | --- | --- |
| `snapshot` | strictly validated functional-v2/identity-v1 or Q5 functional-v3/identity-v2 `record_kind=prompt_snapshot` | exact projection above | same-version comparison against the selected predecessor, or unavailable with a closed reason |
| `legacy_snapshot` | strictly validated functional-v1 snapshot | null | unavailable / `legacy_snapshot_only` |
| `failure` | strictly validated existing dependency or Q3 preparation-failure record | null | unchanged Q3 failure reason |
| `allocation_only` | allocated ordinal with no qualified record | null | unavailable / `current_record_missing` |
| `invalid` | present candidate that fails its exact version validator | null | unavailable / `current_record_invalid` |

Q5's functional-v3 validator, not a schema-token check, qualifies identity-v2
snapshots. It validates every v3 cross-field equality, actual-delivery row, and
composition seal before report projection. A malformed v3 record is `invalid`;
it never falls back to functional-v2 interpretation. Functional-v1/v2
qualification keeps the exact Q3 rules.

The report-v2 projection validator then enforces the fixed attempt-row keys,
the table's status/identity nullability, exact identity-version token, digest
grammar, v1/v2 mutually exclusive fields, complete role key set, actual-row
ordering, and equality to the already validated source record. A projection
cannot qualify itself by carrying plausible digests. Any producer-side
projection mismatch fails report construction with the existing report
validation failure channel; it never downgrades a valid phased snapshot to v1
or emits a partial identity object.

Predecessor selection keeps Q3's scope and ordinal authority: choose the
greatest earlier published `record_kind=prompt_snapshot` ordinal in the same
`ProviderAttemptScope`, without skipping a newer invalid or legacy candidate.
The selected current and predecessor records are comparable only when both
strictly validate and carry the same `identity_version`. A v1/v2 pair is
unavailable with the new exact reason `identity_version_mismatch`; it is never
coerced through `legacy_final_prompt_sha256` or `canonical_composed`.

Same-version v1 comparison is byte-for-byte Q3 behavior. Same-version v2
comparison applies the five Q3 role classifications in their existing order.
If all five roles and `canonical_composed` agree but the ordered
`actual_deliveries` array or v2 composition seal differs, the sole additional
classification is `actual_delivery_drift`. If all roles, canonical composition,
actual deliveries, and the composition seal agree, the classification remains
`prompt_context_unchanged`. Equal roles with unequal canonical composition
remain the existing fail-closed `prompt_identity_composition_mismatch`; an
invalid seal remains record invalidity rather than drift.

The closed v2 report comparison reasons are the Q3 set plus exactly
`identity_version_mismatch`. Its closed available classifications are the Q3
set plus exactly `actual_delivery_drift`. Attempt-row keys, nullability,
ordering, predecessor ordinals, invalid-record behavior, and report rendering
otherwise remain Q3's. Once Q5 ships, v2 is emitted for reports of every DSL
target, including historical runs; persisted evidence is neither rewritten nor
upgraded. Consumers requiring the old v1 identity object must version-gate on
`prompt_context.schema_version` rather than infer shape from target DSL.

Compatibility and version gating are exact:

- targets 2.20 and 2.21 retain
  `workflow_prompt_fragment_snapshot.functional.v1` and compiled fragment
  identity v1/v2 exactly as already selected;
- target 2.22 and target-2.23 composed calls retain
  `workflow_prompt_attempt_identity.v1` inside
  `workflow_prompt_fragment_snapshot.functional.v2`, including the existing
  exact composed `final_prompt`;
- only target-2.23 explicit phased calls require attempt identity v2 and
  functional evidence v3;
- a phased call carrying attempt identity v1 or functional evidence v2, a
  composed call carrying attempt identity v2 or functional evidence v3, a
  target below 2.23 carrying the v2 identity token, or any mixed
  identity/evidence pair fails before provider start; and
- no target upgrade recalculates `compiled_prompt_fragment_identity.v1` or
  `.v2`.

The identity and evidence records and the phase ledger are provenance only.
None is result, checkpoint, publication, comparison-selection, or resume
authority.

### `provider_prompt_phase_ledger.v1`

Q5 deliberately adds one new record kind. Each phased provider attempt owns
one append-only JSONL sidecar at:

```text
workflow_lisp/prompt_dependencies/<step_key>/<visit_key>/
  attempt-<six-digit-ordinal>-provider-prompt-phases.jsonl
```

The path is derived from the same `ProviderAttemptScope` and ordinal as the
attempt's prompt snapshot. It is not a peer message ledger and is not appended
to a Q1/Q3 prompt snapshot.

Every line is UTF-8 canonical JSON with sorted object keys, compact separators,
JSON literals only, ASCII escaping, and exactly one trailing LF. The header is
sequence zero. Event rows start at one and increase contiguously without a
duplicate or gap. The first fsynced row has exactly these keys:

```json
{
  "schema_version": "provider_prompt_phase_ledger.v1",
  "record_kind": "header",
  "seq": 0,
  "attempt": {},
  "target_dsl": "2.23",
  "delivery": "phased",
  "materialization_attempts": 2,
  "prompt_attempt_identity_version": "workflow_prompt_attempt_identity.v2",
  "protocol_schema_version": "provider_phased_protocol_frame.v1",
  "canonical_composed": {"bytes": 0, "sha256": "sha256:..."},
  "task_slice": {"bytes": 0, "sha256": "sha256:..."},
  "materialization_slice": {"bytes": 0, "sha256": "sha256:..."},
  "created_at": "2026-07-27T00:00:00Z"
}
```

`attempt` is the existing closed Q3 object with exactly `scope`,
`scope_sha256`, `step_key`, `visit_key`, and `ordinal`; its nested `scope` is
the existing closed `ProviderAttemptScope` projection. The three byte
projections have exactly `bytes` and `sha256`. `created_at` is a syntactically
valid UTC timestamp for operator correlation only.

Every event row has exactly the common keys
`schema_version`, `record_kind`, `seq`, `event`, `attempt`, `observed_at`, and
`payload`. `schema_version` remains
`provider_prompt_phase_ledger.v1`, `record_kind` is `"event"`, and `attempt`
must equal the header object byte-for-byte. `observed_at` is a syntactically
valid UTC timestamp. Neither timestamp orders events, participates in Q3/Q5
identity, resolves a race, or authorizes a result; only `seq` does.

A `turn` payload is exactly one actual-delivery row shape from
`workflow_prompt_attempt_identity.v2`. In a requested or failed event it is an
intended-turn digest projection and does not become an actual delivery. The
closed events and their exact `payload` keys are:

| Event | Exact payload keys |
| --- | --- |
| `task_start_requested` | `turn` |
| `task_started` | `turn`, `receipt` |
| `task_start_failed` | `turn`, `diagnostic`, `start_failure_outcome` |
| `turn_offer_requested` | `turn` |
| `turn_offered` | `turn`, `receipt` |
| `turn_offer_failed` | `turn`, `diagnostic` |
| `submit_received` | `client_request_id_sha256`, `submission_ordinal`, `configured_total`, `remaining_before` |
| `validation_rejected` | `submission_ordinal`, `diagnostics`, `candidate_manifest` |
| `candidate_reset` | `submission_ordinal`, `postcondition` |
| `retry_queued` | `rejected_submission_ordinal`, `next_submission_ordinal`, `turn` |
| `candidate_frozen` | `submission_ordinal`, `candidate_manifest` |
| `close_offer_requested` | `submission_ordinal`, `close_projection` |
| `close_offered` | `submission_ordinal`, `close_projection`, `receipt` |
| `close_offer_failed` | `submission_ordinal`, `close_projection`, `diagnostic` |
| `ingress_shutdown_started` | `terminal_response` |
| `ingress_shutdown_finished` | `terminal_response`, `queued_requests_rejected`, `active_requests_drained`, `listener_closed`, `workers_joined`, `endpoint_zero_survivor_proven` |
| `ingress_shutdown_failed` | `terminal_response`, `queued_requests_rejected`, `active_requests_drained`, `listener_closed`, `workers_joined`, `endpoint_zero_survivor_proven`, `diagnostic` |
| `join_started` | `submission_ordinal`, `remaining_budget_ms` |
| `join_succeeded` | `submission_ordinal`, `natural_shutdown_proof` |
| `join_failed` | `submission_ordinal`, `diagnostic` |
| `publication_started` | `submission_ordinal` |
| `publication_succeeded` | `submission_ordinal`, `commit_status` |
| `publication_failed` | `submission_ordinal`, `diagnostic` |
| `cleanup_finished` | `cleanup_status`, `abort_calls`, `provider_cleanup_proof`, `cleanup_diagnostic`, `provider_zero_survivor_proven` |
| `terminal_failed` | `diagnostic`, `cleanup_status`, `cleanup_diagnostic`, `endpoint_shutdown_status`, `natural_shutdown_proof` |

No other event or payload key is legal. Exact nested shapes are:

- `receipt` is
  `{"status":"started|offered|close_offered",
  "handle_id_sha256":"sha256:..."}`. It hashes the opaque handle identifier
  and never stores that identifier or a pane/endpoint. The notation does not
  admit a combined literal: `task_started` requires exactly `"started"`,
  `turn_offered` requires exactly `"offered"`, and `close_offered` requires
  exactly `"close_offered"`.
- `close_projection` is exactly
  `{"close_text":{"bytes":N,"sha256":"sha256:..."},
  "submit_keys":{"count":N,"sha256":"sha256:..."}}`; it records no close text
  or key token.
- `diagnostic` is one complete
  `provider_phased_delivery_diagnostic.v1` object defined below.
- `diagnostics` is a non-empty ordered array of those complete objects in Q2's
  fixed output-position-then-structured-result validation order.
- `start_failure_outcome` is the failed branch of
  `InteractiveTerminalStartOutcome` above with the same exact five fields
  after `status`; its proof is exactly `NoBackendAllocationProof` or
  `PhasedFailedCleanupEvidence`, is embedded content-free, and contains no
  handle, endpoint, command, or digest. `FailedCleanupProof` is not admitted.
  The coordinator validates the union and adapter error token before appending
  `task_start_failed`. The immediately following T0 `cleanup_finished` has
  `abort_calls: 0`, copies the exact proof into `provider_cleanup_proof`, maps
  adapter `completed` to ledger `complete`, and otherwise preserves cleanup
  status and provider-zero-survivor truth. The production incomplete token
  requires supplemental reason
  `adapter_start_cleanup_incomplete`; the primary start diagnostic remains
  `adapter_start_failed` or the applicable start deadline reason.
- `postcondition` is exactly `"all_bound_paths_absent"`;
  `commit_status` is exactly `"authoritative_state_committed"`; and
  `cleanup_status` is exactly `"not_required"`, `"complete"`,
  `"incomplete"`, or `"not_permitted"`.
  `cleanup_finished.cleanup_status` admits only the first three values because
  that event is pre-proof. `terminal_failed.cleanup_status` copies the
  preceding cleanup outcome before proof and uses `not_permitted` only after a
  validated natural proof. `not_required` is legal only when the adapter
  supplies the exact complete `NoBackendAllocationProof`, either from its
  untouched created state or in a failed-start outcome; lack of a live adapter
  handle is insufficient.
- `terminal_response` is exactly
  `{"status":"failed",
  "code":"provider_phased_submit_protocol_invalid",
  "reason":"submit_lifecycle_invalid"}`. Every queued or later request receives
  its complete request-bound `provider_phased_submit_receipt.v1`; this ledger
  projection records only their common deterministic terminal decision.
- `queued_requests_rejected`, `active_requests_drained`, and `workers_joined`
  are non-boolean nonnegative integers. In
  `ingress_shutdown_finished`, `listener_closed` and
  `endpoint_zero_survivor_proven` are exactly true and the counts are final;
  no false-valued finished projection is legal. In
  `ingress_shutdown_failed`, the counts and Boolean `listener_closed` are the
  last truthful observations and `endpoint_zero_survivor_proven` is exactly
  false. `endpoint_shutdown_status` is exactly `"not_allocated"`,
  `"complete"`, or `"incomplete"`. It is `complete` exactly when a matching
  `ingress_shutdown_finished` exists, `not_allocated` exactly when no endpoint
  was allocated, and otherwise `incomplete`, including every
  `ingress_shutdown_failed`.
- `remaining_budget_ms` is a non-boolean nonnegative integer sampled only for
  evidence. It does not extend or replace the monotonic deadline.
- `abort_calls` is exactly zero or one. It is one exactly when the coordinator
  invoked `abort` on a live pre-proof handle and zero otherwise.
  `provider_cleanup_proof` is exactly
  `null|NoBackendAllocationProof|PhasedFailedCleanupEvidence`, using the exact
  content-free shapes defined above. No raw or hashed handle occurs in either
  evidence projection. In particular, handle-bound `FailedCleanupProof` is
  never a legal ledger member.
  `provider_zero_survivor_proven` is exactly true for `not_required` only with
  the adapter-issued no-allocation proof, and for `complete` only when the
  handle-free cleanup evidence has `pane_absent`, `server_absent`, and
  `cleanup_complete` all true; it is false for `incomplete`.
- `natural_shutdown_proof` is null or the exact content-free projection
  `{"disposition":"natural_exit","return_code":0,"pane_absent":true,
  "server_absent":true,"proof_complete":true}`.
- `cleanup_status: "not_required"` requires
  `provider_cleanup_proof` to be the exact embedded adapter-issued
  `NoBackendAllocationProof`, `cleanup_diagnostic: null`, `abort_calls: 0`,
  and `provider_zero_survivor_proven: true`. No other status admits
  `NoBackendAllocationProof`.
- `cleanup_status: "complete"` requires
  `provider_cleanup_proof` to be exact `PhasedFailedCleanupEvidence` with
  `pane_absent`, `server_absent`, and `cleanup_complete` all true and
  `error_code: null`, `cleanup_diagnostic: null`, and
  `provider_zero_survivor_proven: true`.
- `cleanup_status: "incomplete"` requires a non-null closed
  `cleanup_diagnostic` and `provider_zero_survivor_proven: false`. A
  failed-start outcome always copies its exact non-null incomplete
  `PhasedFailedCleanupEvidence`. A post-start abort that returns a valid
  handle-bound `FailedCleanupProof` projects to exact incomplete
  `PhasedFailedCleanupEvidence`: at least one evidence Boolean is false or
  `error_code` is a non-null closed adapter token. Null is legal only for the
  explicitly enumerated post-start cases where the cleanup before-check
  expired, abort raised or timed out, returned no proof, returned the wrong
  proof type or fields, or returned a missing/mismatched handle identity. Each
  invalid returned proof selects supplemental `adapter_cleanup_failed`; no raw
  proof becomes ledger evidence. No other branch admits null.
- In `terminal_failed`, the cleanup diagnostic equals the one in
  `cleanup_finished`; otherwise it is null.
- In `join_succeeded` the natural proof is required. In `terminal_failed` it
  is null before natural join and is the exact validated proof after natural
  join, including the case where appending `join_succeeded` failed. A
  post-proof row requires `cleanup_status: "not_permitted"` and null
  `cleanup_diagnostic`. No extra provider output is copied.

Every ledger scalar and cross-row relation is closed:

- `u63` means a JSON integer that is not a Boolean and lies in
  `0..9223372036854775807`; `positive_u63` means `1..9223372036854775807`.
  `seq`, every zero-based contract/delivery ordinal, byte/count field, remaining
  count, rejected/queued count, worker count, and `remaining_budget_ms` is
  `u63`. Attempt and submission ordinals are `positive_u63`.
- Every digest string has exact grammar
  `sha256:` followed by 64 lowercase hexadecimal characters. Uppercase,
  missing-prefix, shortened, expanded, or non-hex strings are payload-invalid
  before digest-category dispatch.
- `created_at` and `observed_at` are canonical UTC RFC 3339 strings with exact
  form `YYYY-MM-DDTHH:MM:SSZ` or
  `YYYY-MM-DDTHH:MM:SS.ffffffZ`, valid calendar/time fields, and no offset,
  leap-second, shortened fraction, or trailing whitespace.
- Header `seq` is exactly zero; event `seq` is exactly the preceding `seq + 1`
  without u63 overflow. Header `target_dsl`, `delivery`,
  `prompt_attempt_identity_version`, and `protocol_schema_version` are the
  exact literals shown above. Header `materialization_attempts` is a
  non-Boolean integer in `1..3`.
- The header attempt ordinal is `positive_u63`; every event attempt object is
  byte-for-byte equal to the header attempt. No event may change scope,
  scope digest, step key, visit key, or ordinal.
- `delivery_ordinal` starts at zero and advances by exactly one for each
  successful `task_started` or `turn_offered` receipt. Requested/failed turns
  carry the next prospective ordinal but do not consume it. Task phase requires
  submission ordinal null. Initial materialization requires submission ordinal
  one. Retry materialization requires the exact
  `retry_queued.next_submission_ordinal`.
- `submit_received.configured_total` equals the header
  `materialization_attempts`. For submission ordinal `n`,
  `remaining_before` equals `configured_total - n + 1`, and
  `1 <= n <= configured_total`. The first admitted submit is ordinal one;
  every later admitted submit is exactly the preceding ordinal plus one.
- `validation_rejected`, `candidate_reset`, and `candidate_frozen` use the
  immediately preceding `submit_received.submission_ordinal`.
  `retry_queued.rejected_submission_ordinal` equals that rejected ordinal,
  `next_submission_ordinal` equals it plus one without overflow, and retry is
  legal only when `next_submission_ordinal <= configured_total`. The next
  `submit_received` must use that exact ordinal.
- Every close, join, publication, and manifest submission ordinal
  equals the most recent admitted submit ordinal. Manifest contract ordinals
  start at zero and are contiguous; the manifest submission ordinal equals its
  containing event. A terminal failure before any submit uses no invented
  submission ordinal because its payload has none.
- `queued_requests_rejected`, `active_requests_drained`, and `workers_joined`
  are monotonically final counts for that one shutdown. The finished counts
  cannot be smaller than any corresponding count already observed by the
  coordinator, and `active_requests_drained` includes the accepted submit whose
  receipt had to flush before shutdown began.

#### Offline digest partition

The ledger validator has only ledger bytes. It never opens a candidate,
reconstructs a prompt/frame, reads a provider template, resolves a handle or
request id, or consults functional evidence. Every legal digest field belongs
to exactly one of two categories below. `CJSON(x)` means UTF-8 bytes of JSON
with sorted object keys, compact separators, `ensure_ascii=true`, JSON
literals only, and no trailing LF.

| Category | Exact ledger path | Offline preimage or binding |
| --- | --- | --- |
| recomputable seal | `header.attempt.scope_sha256` and every byte-identical event copy | SHA-256 of `CJSON(header.attempt.scope)`; the recomputed value must also satisfy the existing Q3 `ProviderAttemptScope.key` rule |
| recomputable seal | every task-phase `turn.submit_keys.sha256` | SHA-256 of `CJSON([])`, exactly `sha256:4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`; `count` is zero |
| recomputable seal | `candidate_manifest.manifest_sha256` | SHA-256 of `CJSON(candidate_manifest without manifest_sha256)`, including the opaque row references as embedded strings |
| opaque reference | `header.canonical_composed.sha256` | header singleton bound to its adjacent byte count; no offline equality target |
| opaque reference | `header.task_slice.sha256` | equals every task-phase `turn.canonical_slice.sha256` |
| opaque reference | `header.materialization_slice.sha256` | equals every initial/retry materialization `turn.canonical_slice.sha256` |
| opaque reference | every `turn.protocol_frame.sha256` | requested/outcome copies for the same `(delivery_ordinal, phase, submission_ordinal)` are exact |
| opaque reference | every `turn.canonical_slice.sha256` | requested/outcome copies are exact and also obey the applicable header-slice binding above |
| opaque reference | every `turn.delivered_turn.sha256` | requested/outcome copies for the same turn are exact; byte-count arithmetic is checked, but no hash concatenation is attempted without bytes |
| opaque reference | non-task `turn.submit_keys.sha256` | requested/outcome copies for the same turn are exact and remain bound to that turn's ordinal |
| opaque reference | every `receipt.handle_id_sha256` | all successful start/offer/close receipts in the attempt carry one exact value |
| opaque reference | `submit_received.client_request_id_sha256` | unique to its admitted submission ordinal; exact request replay adds no new row |
| opaque reference | every `close_projection.close_text.sha256` | requested/outcome close projections are exact |
| opaque reference | every `close_projection.submit_keys.sha256` | requested/outcome close projections are exact |
| opaque reference | every regular `candidate_manifest.rows[].sha256` | bound to the enclosing submission ordinal and deterministic contract-row order; no candidate bytes are opened |

The `natural_shutdown_proof` and every admitted
`provider_cleanup_proof` member above contain no digest. No other ledger field
may carry digest semantics. The adapter's handle-bound `FailedCleanupProof`
and its `handle_id` are not ledger fields, opaque digest sources, or hashed
references; only validated content-free `PhasedFailedCleanupEvidence` may be
projected.
The runtime computes opaque references from the live bytes or opaque
identifiers it owns before appending the row; that runtime computation does
not make those bytes available to the offline validator.

Offline digest checking is deterministic:

1. malformed digest syntax is `payload_invalid`;
2. a recomputable seal with a valid-shaped but unequal recomputation is
   `digest_mismatch`;
3. for an opaque reference required to equal the tuple selected by the current
   event/ordinal, a value equal to a different already-recorded legal tuple is
   `opaque_digest_order_mismatch`;
4. any other failure of a required opaque equality is
   `opaque_digest_equality_mismatch`; and
5. an opaque singleton with no equality target is accepted after grammar,
   scalar, and ordinal validation and is never offline-recomputed.

Scalar/ordinal validation precedes these rules. Event-order validation then
selects the one expected tuple. Opaque equality/order checks precede
recomputable-seal checks, so one row has one stable first digest reason.

The event grammar is closed over the row kind plus the coordinator's monotonic
`provider_cleanup`, `ingress`, and natural-proof substates. The ordinary
forward edges are:

```text
task_start_requested
  -> task_started | task_start_failed
task_start_failed
  -> cleanup_finished(pre-proof)
task_started
  -> turn_offer_requested(initial)
turn_offer_requested(initial|retry)
  -> turn_offered(same turn) | turn_offer_failed(same turn)
turn_offer_failed
  -> cleanup_finished(pre-proof)
turn_offered
  -> submit_received | cleanup_finished(pre-proof)
submit_received
  -> validation_rejected | candidate_frozen | cleanup_finished(pre-proof)
validation_rejected
  -> candidate_reset | cleanup_finished(pre-proof)
candidate_reset
  -> retry_queued | cleanup_finished(pre-proof)
retry_queued
  -> turn_offer_requested(retry)
candidate_frozen
  -> close_offer_requested
close_offer_requested
  -> close_offered | close_offer_failed
  | cleanup_finished(pre-proof, accepted-closing flush unproven)
close_offer_failed
  -> cleanup_finished(pre-proof)
close_offered
  -> ingress_shutdown_started(normal)
ingress_shutdown_started(normal)
  -> ingress_shutdown_finished(normal)
  | cleanup_finished(pre-proof, ingress already started)
ingress_shutdown_finished(normal)
  -> join_started | cleanup_finished(pre-proof, ingress already complete)
cleanup_finished(pre-proof, ingress not started)
  -> ingress_shutdown_started(terminalizing)
cleanup_finished(pre-proof, ingress already started)
  -> ingress_shutdown_finished(terminalizing)
  | ingress_shutdown_failed(terminalizing)
ingress_shutdown_started(terminalizing)
  -> ingress_shutdown_finished(terminalizing)
  | ingress_shutdown_failed(terminalizing)
ingress_shutdown_finished(terminalizing)
  -> terminal_failed(endpoint complete)
ingress_shutdown_failed(terminalizing)
  -> terminal_failed(endpoint incomplete)
join_started
  -> join_succeeded
  | join_failed
  | terminal_failed(validated natural proof; join row unavailable)
join_failed
  -> cleanup_finished(pre-proof, ingress already complete)
join_succeeded
  -> publication_started | terminal_failed(post-proof)
publication_started
  -> publication_succeeded | publication_failed
publication_failed
  -> terminal_failed(post-proof)
```

Every pre-proof failure then selects exactly one of these terminalization
productions from the substate at failure admission:

```text
T0 endpoint allocation never entered:
  failure -> cleanup_finished
          -> terminal_failed(endpoint not_allocated;
                             zero coordinator-owned endpoint resources)

T1 endpoint allocation entered after successful start, ingress not started:
  failure -> cleanup_finished
          -> ingress_shutdown_started(terminalizing)
          -> ingress_shutdown_finished(terminalizing)
             -> terminal_failed(endpoint complete)
           | ingress_shutdown_failed(terminalizing)
             -> terminal_failed(endpoint incomplete)

T2a failure after ingress starts normally, cleanup still pending:
  failure -> cleanup_finished
          -> ingress_shutdown_finished(terminalizing)
             -> terminal_failed(endpoint complete)
           | ingress_shutdown_failed(terminalizing)
             -> terminal_failed(endpoint incomplete)

T2b failure after ingress starts terminalizing, cleanup already finished:
  failure -> ingress_shutdown_finished(terminalizing)
             -> terminal_failed(endpoint complete)
           | ingress_shutdown_failed(terminalizing)
             -> terminal_failed(endpoint incomplete)

T3 failure after the single ingress pair but before validated natural proof:
  failure -> cleanup_finished
          -> terminal_failed(endpoint complete)

T4 failure after validated natural proof / JOINED_PENDING_COMMIT:
  failure -> terminal_failed(endpoint complete, natural proof retained)
```

`failure` in T0–T3 is either the explicit preceding failure event or a
coordinator-local failure carried as the primary diagnostic in the eventual
terminal row. T0 discards the inert submit-binding and candidate-locator
values; because endpoint allocation was never entered, it owns no endpoint
socket, address, reservation, listener, worker, or other endpoint resource.
In T2a, cleanup is pending at failure admission: exactly one
cleanup outcome is recorded, then the already-started endpoint action runs
every still-possible fail-safe listener/worker close/join action and records
exactly one finished-or-failed outcome. In T2b, cleanup was already recorded
before the terminalizing ingress start: no second `cleanup_finished` is legal,
and the endpoint records its one finished-or-failed outcome directly. Neither
branch emits a second `ingress_shutdown_started`; only the complete
zero-survivor branch emits `ingress_shutdown_finished`, while failure emits
`ingress_shutdown_failed` with false endpoint proof. T4 performs zero abort or
cleanup calls, emits no `cleanup_finished`, and repeats no ingress event. If
`join_succeeded` could not be made durable, T4's recorded edge is directly
`join_started -> terminal_failed` with the validated proof.

Exactly one `cleanup_finished` exists overall in T0–T3, including failed
start, incomplete cleanup, and T2b's already-finished substate. Its outgoing
edge is determined solely by ingress state: `NOT_ALLOCATED`, `COMPLETE`, or
`INCOMPLETE` goes directly to `terminal_failed`; allocated `NOT_STARTED` goes
to the one terminalizing ingress start and its one outcome; `STARTED` goes
directly to that one outcome without another start. An ingress-finished row
reached from `close_offered` continues to `join_started`; the same row reached
after cleanup continues only to `terminal_failed`. The validator tracks
normal-versus-terminalizing context plus whether cleanup is pending or
finished, so the identical event names do not create an ambiguous outgoing
edge.

Thus `task_start_failed`, `turn_offer_failed`, `close_offer_failed`, and
`join_failed` always reach exactly one `cleanup_finished`, the endpoint's
structural-not-allocated or durable zero-survivor outcome, and
`terminal_failed`. A live pre-proof handle has exactly one abort call; failed
start has zero later abort calls and imports only its explicit adapter cleanup
evidence. A live abort imports no adapter proof object: after exact handle
validation it projects only `PhasedFailedCleanupEvidence`. Cleanup failure is
not a grammar escape: it yields an incomplete cleanup row with its supplemental
diagnostic, continues through the applicable T0–T3 production, and makes no
provider-zero-survivor claim.
`publication_succeeded` and `terminal_failed` are terminal; no event may
follow either.

A retry turn's `submission_ordinal` must equal
`retry_queued.next_submission_ordinal`; every other adjacent ordinal,
turn-digest, manifest, diagnostic, proof, and attempt projection must match
the preceding request or coordinator state exactly. An unavailable evidence
channel may truncate this grammar only as the non-authoritative valid-prefix
case defined below; it never legalizes a later row or changes the logical
terminalizer actions.

The coordinator appends and fsyncs `task_start_requested`,
`turn_offer_requested`, `close_offer_requested`, `ingress_shutdown_started`,
`join_started`, and `publication_started` before the corresponding adapter,
endpoint, or publication action.
It appends and fsyncs each success/failure outcome before returning an external
submit/coordinator receipt or initiating a later action that depends on that
outcome. `submit_received` is durable before validation;
`validation_rejected` is durable before reset; `candidate_reset` and
`retry_queued` are durable before the retry offer; `candidate_frozen` is
durable before close or an `accepted_closing` receipt;
`close_offer_requested` is durable before that receipt, the receipt is flushed
before `offer_close`, and `close_offered` is durable before ingress shutdown;
and
`ingress_shutdown_finished` is durable before join begins, and
`ingress_shutdown_failed` is durable before its terminal row whenever the
evidence channel remains writable. Receipt of a valid natural-shutdown proof
moves lifecycle authority before the `join_succeeded`
append: if that append fails, the truthful prefix may end at `join_started`, or
a later `terminal_failed` may preserve the proof when the channel recovers.
After natural join, publication failure rows are best effort because the same
filesystem/state failure may make the ledger unwritable; their possible
absence does not permit abort, success, replay, or reconstruction.

Record-before-action governs the normal ingress shutdown path. If its requested
row cannot be made durable, success is already impossible, but mandatory
fail-safe terminalization still disables/closes/joins the endpoint without
inventing an event. Safety cleanup is the only action permitted after that
evidence failure.

### Embedded candidate manifest

`provider_phased_candidate_digest_manifest.v1` is an embedded object, never a
separate sidecar:

```json
{
  "schema_version": "provider_phased_candidate_digest_manifest.v1",
  "submission_ordinal": 1,
  "disposition": "rejected",
  "rows": [
    {
      "contract_ordinal": 0,
      "role": "expected_output",
      "logical_name": "review_report",
      "workspace_relative_path": "artifacts/review.json",
      "presence": "regular",
      "byte_length": 123,
      "sha256": "sha256:..."
    }
  ],
  "manifest_sha256": "sha256:..."
}
```

The top-level keys are exactly `schema_version`, `submission_ordinal`,
`disposition`, `rows`, and `manifest_sha256`. `disposition` is
`rejected|frozen`. Rows are the complete bound candidate set in deterministic
contract order: all expected outputs, then the one structured bundle. A row's
keys are exactly `contract_ordinal`, `role`, `logical_name`,
`workspace_relative_path`, `presence`, `byte_length`, and `sha256`.
`contract_ordinal` is contiguous from zero; `role` is
`expected_output|structured_bundle`; `logical_name` is the declared artifact
name or the exact reserved token `__structured_result_bundle__`; and the path
is normalized workspace-relative POSIX text equal to the preflight binding.
`presence` is `missing|regular|invalid`. Only `regular` permits a nonnegative
`byte_length` and exact SHA-256; the other states require both fields null. A
frozen manifest requires every row to be `regular`.

`manifest_sha256` seals canonical JSON of the complete object without that
field. `validation_rejected` embeds the complete rejected manifest and
`candidate_frozen` embeds the complete frozen manifest. A digest without its
complete in-row manifest is invalid; no orphan digest-only manifest or
manifest file can satisfy either event.

The ledger stores no prompt/frame/diagnostic prose, resolved slot values,
candidate contents, structured result, dependency content, stdout/stderr,
provider command/argv, environment, secret, raw request id, raw handle id,
endpoint, pane text, or key tokens. Its allowed relative paths, sizes,
digests, codes, source locations, and attempt identity are metadata, not
result authority.

### Ledger validation and authority

The offline validator returns exactly:

```json
{
  "schema_version": "provider_prompt_phase_ledger_validation.v1",
  "status": "valid_prefix",
  "reason": "nonterminal_prefix",
  "row_count": 1,
  "last_contiguous_seq": 0,
  "terminal_event": null
}
```

`status` is `complete|valid_prefix|malformed|truncated`. `reason` is exactly
`complete`, `nonterminal_prefix`, `missing_header`, `invalid_utf8`,
`invalid_json`, `noncanonical_json`, `unknown_key`, `unknown_event`,
`sequence_invalid`, `attempt_mismatch`, `payload_invalid`,
`event_order_invalid`, `opaque_digest_order_mismatch`,
`opaque_digest_equality_mismatch`, `digest_mismatch`, or
`truncated_final_row`.
`row_count` is the `u63` number of complete decoded rows;
`last_contiguous_seq` is `u63` or null before a valid header;
and `terminal_event` is `publication_succeeded|terminal_failed|null`.
A missing final LF or partial final JSON object is `truncated` with
`truncated_final_row`; other syntax/schema/order failures are `malformed`.
A canonical prefix with no terminal event is `valid_prefix`, including a
post-join publication failure whose evidence channel became unwritable.

Validation scans complete rows in file order and reports the first failure in
this fixed precedence:

```text
invalid_utf8
  -> invalid_json
  -> noncanonical_json
  -> missing_header
  -> unknown_key
  -> unknown_event
  -> sequence_invalid
  -> attempt_mismatch
  -> payload_invalid
  -> event_order_invalid
  -> opaque_digest_order_mismatch
  -> opaque_digest_equality_mismatch
  -> digest_mismatch
```

`sequence_invalid` owns non-u63, noncontiguous, duplicate, gap, and overflowed
`seq`. `attempt_mismatch` owns any event attempt unequal to the valid header.
`payload_invalid` owns every wrong JSON type, Boolean-as-integer, out-of-range
integer, malformed digest string, wrong literal/nullability, ordinal/count
arithmetic violation, header disagreement, nested-key violation, and
cross-event scalar mismatch defined above. `event_order_invalid` applies only
after both rows are individually payload-valid and their event kinds violate
the closed grammar. The two opaque-reference reasons apply only to fields in
the opaque partition and follow its tuple-selection algorithm;
`digest_mismatch` applies only to a recomputable seal whose ledger-only
preimage hashes differently. The offline validator never maps an opaque
reference to `digest_mismatch`. `truncated_final_row` is evaluated before this
row-validation precedence only for the incomplete final physical line. The
validator never guesses a later, more specific reason after the first
governing failure.

Runtime publication and resume never invoke this validator or parse the
ledger to validate, reconstruct, choose, retry, settle, continue, or reuse a
result. A malformed, truncated, missing, or nonterminal ledger cannot
invalidate an otherwise committed result and cannot make a failed/interrupted
visit resumable. It is reported only as non-authoritative evidence damage.

### Closed refusal diagnostic

Every Q5 compiler/runtime refusal and every retryable Q2 validation rejection
uses one closed `provider_phased_delivery_diagnostic.v1`:

```json
{
  "schema_version": "provider_phased_delivery_diagnostic.v1",
  "code": "provider_phased_delivery_policy_invalid",
  "reason": "attempts_out_of_range",
  "rejected_value": {
    "type": "integer",
    "canonical_value": 4,
    "summary": "attempts_out_of_range"
  },
  "primary_source": {
    "kind": "authored_span",
    "owner": "materialization_attempts_keyword",
    "path": "workflows/example.orc",
    "span": {
      "start_line": 10,
      "start_column": 3,
      "end_line": 10,
      "end_column": 34
    }
  },
  "related_sources": [
    {
      "kind": "authored_span",
      "owner": "provider_application",
      "path": "workflows/example.orc",
      "span": {
        "start_line": 8,
        "start_column": 1,
        "end_line": 14,
        "end_column": 2
      }
    }
  ]
}
```

The top-level keys are exact. `code` is exactly one of:

```text
provider_phased_delivery_requires_dsl_2_23
provider_phased_delivery_policy_invalid
provider_phased_isolation_unsupported
provider_phased_interactive_capability_missing
provider_phased_interactive_capability_invalid
provider_phased_delivery_carriage_mismatch
provider_phased_preparation_failed
provider_phased_evidence_failed
provider_phased_start_failed
provider_phased_start_timeout
provider_phased_turn_offer_failed
provider_phased_turn_offer_timeout
provider_phased_submit_timeout
provider_phased_submit_protocol_invalid
provider_phased_provider_exited_before_submit
provider_phased_candidate_path_preexisting
provider_phased_validation_rejected
provider_phased_candidate_reset_failed
provider_phased_candidate_freeze_failed
provider_phased_materialization_attempts_exhausted
provider_phased_graceful_close_failed
provider_phased_graceful_close_timeout
provider_phased_ingress_shutdown_failed
provider_phased_ingress_shutdown_timeout
provider_phased_natural_close_failed
provider_phased_publication_failed
provider_phased_cleanup_failed
provider_phased_interrupted_visit_quarantined
```

Each existing Q2 contract violation is wrapped as
`provider_phased_validation_rejected`; its exact existing violation type is
the content-safe `rejected_value.canonical_value`, and `reason` identifies the
output-position or structured-result validator. `reason` is one of the closed
tokens below.
`rejected_value` has exactly `type`, `canonical_value`, and `summary`.
`type` is one of:

```text
absent
boolean
integer
enum
schema_token
range
pairing
fragment_shape
capability_shape
carriage_shape
candidate_shape
deadline_state
lifecycle_state
validation_code
publication_stage
```

`canonical_value` is null or the exact content-safe JSON boolean, integer, or
bounded compiler/runtime token selected by the reason's value profile.
Independently of that nullability, `summary` is always the exact `reason`
token. It is never null, prose, a source label, or a substitute for the
canonical value. Prompt, fragment, dependency, result, diagnostic prose,
command/argv, environment, credential, secret, endpoint, handle, pane, and
candidate bytes are never projected. Profiles for those values use
`canonical_value: null`; they still use the exact reason token as `summary`.

Every source object has exactly `kind`, `owner`, `path`, and `span`. `kind` is
one of `authored_span`, `provider_template`, `carrier_boundary`,
`runtime_attempt`, `adapter_operation`, or `state_commit`. `owner` is exactly
one of:

```text
delivery_keyword
materialization_attempts_keyword
provider_application
fragment_contract
result_contract_suffix
resolved_provider_template
provider_call_policy
semantic_ir
executable_ir
persisted_provider_config
lexical_checkpoint
runtime_step
submit_endpoint
q2_output_contract
candidate_set
phase_lifecycle
phase_ledger
interactive_adapter
workflow_state_commit
```

`path` is a normalized workspace-relative/source-root-relative path or null.
`span` is null or has exactly `start_line`, `start_column`, `end_line`, and
`end_column` as positive integers. The compiler uses the most specific
authored span. Runtime uses the exact retained source owner and adds the
runtime boundary as an ordered related source; it does not invent a source
location.

`related_sources` is not populated by "best available" lookup. The closed
source profile selected below gives its exact owner list and order; every
listed owner must contribute exactly one complete retained source object and
no unlisted owner may appear. The sole dynamic profile,
`S_CARRIAGE_PREFIX`, selects the first failing carrier and its exact validated
prefix by the fixed carrier order below. It never sorts by path, message text,
or object availability.

The closed reason tokens, grouped by decision class, are:

- target: `target_below_2_23`;
- surface syntax/type: `delivery_type_invalid`, `delivery_enum_invalid`,
  `attempts_literal_required`, `attempts_type_invalid`,
  `attempts_out_of_range`, `attempts_pairing_invalid`;
- eligibility: `fragment_application_required`,
  `contract_suffix_required`, `isolation_required_unsupported`;
- static/runtime capability: `interactive_capability_absent`,
  `interactive_capability_schema_unsupported`,
  `turn_boundary_messages_not_true`,
  `interactive_capability_malformed`;
- carriage/load: `call_policy_carriage_missing`,
  `call_policy_carriage_extra`, `call_policy_carriage_mismatch`,
  `attempt_identity_version_mismatch`,
  `attempt_evidence_version_mismatch`;
- preparation/candidate: `candidate_path_preexisting`,
  `preparation_failed`, `submit_endpoint_allocation_failed`,
  `evidence_append_failed`,
  `candidate_reset_failed`, `candidate_freeze_failed`,
  `ingress_shutdown_failed`;
- submit: `submit_binding_foreign`, `submit_binding_stale`,
  `submit_request_conflict`, `submit_duplicate_in_flight`,
  `submit_lifecycle_invalid`, `provider_exited_before_submit`;
- validation/cap: `output_validation_failed`,
  `structured_result_validation_failed`,
  `materialization_attempts_exhausted`;
- deadline:
  `deadline_exhausted_before_preparation`,
  `deadline_exhausted_during_preparation`,
  `deadline_exhausted_before_ledger_append`,
  `deadline_exhausted_during_ledger_append`,
  `deadline_exhausted_before_start`,
  `deadline_exhausted_during_start`,
  `deadline_exhausted_before_submit_endpoint_allocation`,
  `deadline_exhausted_during_submit_endpoint_allocation`,
  `deadline_exhausted_before_initial_offer`,
  `deadline_exhausted_during_initial_offer`,
  `deadline_exhausted_before_retry_offer`,
  `deadline_exhausted_during_retry_offer`,
  `deadline_exhausted_before_submit`,
  `deadline_exhausted_during_submit`,
  `deadline_exhausted_before_validation`,
  `deadline_exhausted_during_validation`,
  `deadline_exhausted_before_candidate_reset`,
  `deadline_exhausted_during_candidate_reset`,
  `deadline_exhausted_before_candidate_freeze`,
  `deadline_exhausted_during_candidate_freeze`,
  `deadline_exhausted_before_close_offer`,
  `deadline_exhausted_during_close_offer`,
  `deadline_exhausted_before_ingress_shutdown`,
  `deadline_exhausted_during_ingress_shutdown`,
  `deadline_exhausted_before_join`,
  `deadline_exhausted_during_join`,
  `deadline_exhausted_before_evidence_publication`,
  `deadline_exhausted_during_evidence_publication`,
  `deadline_exhausted_before_frozen_restoration`,
  `deadline_exhausted_during_frozen_restoration`,
  `deadline_exhausted_before_frozen_verification`,
  `deadline_exhausted_during_frozen_verification`,
  `deadline_exhausted_before_state_commit`,
  `deadline_exhausted_during_state_commit_preparation`,
  `deadline_exhausted_before_adapter_cleanup`,
  `deadline_exhausted_during_adapter_cleanup`;
- adapter/lifecycle: `adapter_start_failed`, `initial_offer_failed`,
  `retry_offer_failed`, `close_offer_failed`, `natural_join_failed`,
  `adapter_start_cleanup_incomplete`, `adapter_cleanup_failed`,
  `provider_zero_survivor_unproven`, `interrupted_nonterminal_visit`; and
- publication: `evidence_publication_failed`,
  `frozen_restoration_failed`, `frozen_verification_failed`,
  `workflow_state_commit_failed`.

Legal code/reason pairings are exact:

| Code | Allowed reason tokens |
| --- | --- |
| `provider_phased_delivery_requires_dsl_2_23` | `target_below_2_23` |
| `provider_phased_delivery_policy_invalid` | `delivery_type_invalid`, `delivery_enum_invalid`, `attempts_literal_required`, `attempts_type_invalid`, `attempts_out_of_range`, `attempts_pairing_invalid`, `fragment_application_required`, `contract_suffix_required` |
| `provider_phased_isolation_unsupported` | `isolation_required_unsupported` |
| `provider_phased_interactive_capability_missing` | `interactive_capability_absent` |
| `provider_phased_interactive_capability_invalid` | `interactive_capability_schema_unsupported`, `turn_boundary_messages_not_true`, `interactive_capability_malformed` |
| `provider_phased_delivery_carriage_mismatch` | `call_policy_carriage_missing`, `call_policy_carriage_extra`, `call_policy_carriage_mismatch`, `attempt_identity_version_mismatch`, `attempt_evidence_version_mismatch` |
| `provider_phased_preparation_failed` | `preparation_failed`, `submit_endpoint_allocation_failed`, `deadline_exhausted_before_preparation`, `deadline_exhausted_during_preparation`, `deadline_exhausted_before_submit_endpoint_allocation`, `deadline_exhausted_during_submit_endpoint_allocation` |
| `provider_phased_evidence_failed` | `evidence_append_failed`, `deadline_exhausted_before_ledger_append`, `deadline_exhausted_during_ledger_append` |
| `provider_phased_start_failed` | `adapter_start_failed` |
| `provider_phased_start_timeout` | `deadline_exhausted_before_start`, `deadline_exhausted_during_start` |
| `provider_phased_turn_offer_failed` | `initial_offer_failed`, `retry_offer_failed` |
| `provider_phased_turn_offer_timeout` | `deadline_exhausted_before_initial_offer`, `deadline_exhausted_during_initial_offer`, `deadline_exhausted_before_retry_offer`, `deadline_exhausted_during_retry_offer` |
| `provider_phased_submit_timeout` | `deadline_exhausted_before_submit`, `deadline_exhausted_during_submit`, `deadline_exhausted_before_validation`, `deadline_exhausted_during_validation` |
| `provider_phased_submit_protocol_invalid` | `submit_binding_foreign`, `submit_binding_stale`, `submit_request_conflict`, `submit_duplicate_in_flight`, `submit_lifecycle_invalid` |
| `provider_phased_provider_exited_before_submit` | `provider_exited_before_submit` |
| `provider_phased_candidate_path_preexisting` | `candidate_path_preexisting` |
| `provider_phased_validation_rejected` | `output_validation_failed`, `structured_result_validation_failed` |
| `provider_phased_candidate_reset_failed` | `candidate_reset_failed`, `deadline_exhausted_before_candidate_reset`, `deadline_exhausted_during_candidate_reset` |
| `provider_phased_candidate_freeze_failed` | `candidate_freeze_failed`, `deadline_exhausted_before_candidate_freeze`, `deadline_exhausted_during_candidate_freeze` |
| `provider_phased_materialization_attempts_exhausted` | `materialization_attempts_exhausted` |
| `provider_phased_graceful_close_failed` | `close_offer_failed` |
| `provider_phased_graceful_close_timeout` | `deadline_exhausted_before_close_offer`, `deadline_exhausted_during_close_offer` |
| `provider_phased_ingress_shutdown_failed` | `ingress_shutdown_failed` |
| `provider_phased_ingress_shutdown_timeout` | `deadline_exhausted_before_ingress_shutdown`, `deadline_exhausted_during_ingress_shutdown` |
| `provider_phased_natural_close_failed` | `deadline_exhausted_before_join`, `deadline_exhausted_during_join`, `natural_join_failed` |
| `provider_phased_publication_failed` | `deadline_exhausted_before_evidence_publication`, `deadline_exhausted_during_evidence_publication`, `deadline_exhausted_before_frozen_restoration`, `deadline_exhausted_during_frozen_restoration`, `deadline_exhausted_before_frozen_verification`, `deadline_exhausted_during_frozen_verification`, `deadline_exhausted_before_state_commit`, `deadline_exhausted_during_state_commit_preparation`, `evidence_publication_failed`, `frozen_restoration_failed`, `frozen_verification_failed`, `workflow_state_commit_failed` |
| `provider_phased_cleanup_failed` | `deadline_exhausted_before_adapter_cleanup`, `deadline_exhausted_during_adapter_cleanup`, `adapter_start_cleanup_incomplete`, `adapter_cleanup_failed`, `provider_zero_survivor_unproven` |
| `provider_phased_interrupted_visit_quarantined` | `interrupted_nonterminal_visit` |

#### Total diagnostic projection

Diagnostic construction is a total table-driven algorithm. A reason must
occur exactly once in either the static registry or the deadline-operation
registry below, and exactly once in the code/reason pairing table above.
Missing, duplicate, or cross-table reasons are schema-definition errors, not
runtime fallbacks.

Every reason selects one value profile:

| Value profile | Exact `rejected_value.type` | Exact `canonical_value` | Exact `summary` |
| --- | --- | --- | --- |
| `P_ABSENT` | `absent` | null | the reason token |
| `P_BOOL_FALSE` | `boolean` | false | the reason token |
| `P_INT_NULL` | `integer` | null | the reason token |
| `P_INT_EXACT` | `integer` | the rejected non-Boolean JSON integer when it lies in signed-64 range, otherwise null | the reason token |
| `P_ENUM_NULL` | `enum` | null | the reason token |
| `P_SCHEMA_NULL` | `schema_token` | null | the reason token |
| `P_SCHEMA_EXACT` | `schema_token` | the already-validated syntactic target token as its exact ASCII string | the reason token |
| `P_RANGE_EXACT` | `range` | the configured non-Boolean materialization-attempt total in `1..3` | the reason token |
| `P_PAIRING_NULL` | `pairing` | null | the reason token |
| `P_FRAGMENT_NULL` | `fragment_shape` | null | the reason token |
| `P_CAPABILITY_NULL` | `capability_shape` | null | the reason token |
| `P_CARRIAGE_NULL` | `carriage_shape` | null | the reason token |
| `P_CANDIDATE_NULL` | `candidate_shape` | null | the reason token |
| `P_DEADLINE_NULL` | `deadline_state` | null | the reason token |
| `P_LIFECYCLE_NULL` | `lifecycle_state` | null | the reason token |
| `P_VALIDATION_CODE` | `validation_code` | the exact existing closed Q2 violation-type token | the reason token |
| `P_PUBLICATION_NULL` | `publication_stage` | null | the reason token |

Null is a deliberate normalized value, not unavailable best effort.
`summary` is never null and never prose. In particular, no producer may choose
`enum` versus `string`, expose an arbitrary malformed token, truncate a value,
or substitute a source label.

Every reason also selects one source profile:

| Source profile | Exact primary owner | Exact ordered related owners |
| --- | --- | --- |
| `S_DELIVERY` | `delivery_keyword` | `provider_application` |
| `S_ATTEMPTS` | `materialization_attempts_keyword` | `provider_application` |
| `S_FRAGMENT` | `fragment_contract` | `provider_application` |
| `S_RESULT` | `result_contract_suffix` | `provider_application` |
| `S_PROVIDER` | `provider_application` | empty |
| `S_TEMPLATE` | `resolved_provider_template` | `provider_application` |
| `S_CARRIAGE_PREFIX` | first failing owner in `provider_call_policy`, `semantic_ir`, `executable_ir`, `persisted_provider_config`, `lexical_checkpoint`, `runtime_step` | the exact successfully validated prefix before that owner, in the same order |
| `S_CANDIDATE` | `candidate_set` | `runtime_step`, `phase_lifecycle` |
| `S_LEDGER` | `phase_ledger` | `runtime_step`, `phase_lifecycle` |
| `S_ENDPOINT` | `submit_endpoint` | `runtime_step`, `phase_lifecycle` |
| `S_Q2` | `q2_output_contract` | `runtime_step`, `candidate_set`, `phase_lifecycle` |
| `S_LIFECYCLE` | `phase_lifecycle` | `runtime_step` |
| `S_ADAPTER` | `interactive_adapter` | `runtime_step`, `phase_lifecycle` |
| `S_PUBLICATION` | `phase_lifecycle` | `runtime_step`, `phase_ledger` |
| `S_STATE` | `workflow_state_commit` | `runtime_step`, `phase_lifecycle` |

Authored owners use `kind: "authored_span"` and their one retained path/span.
`resolved_provider_template` uses `provider_template`. Carrier owners use
`carrier_boundary` and their retained source path/span. Runtime, candidate,
endpoint, Q2, lifecycle, and ledger owners use `runtime_attempt` with null
path/span; the adapter uses `adapter_operation` with null path/span; state
commit uses `state_commit` with null path/span. These mappings apply to both
primary and related objects. A producer may not omit a profile-required
related object, add a later boundary, or replace a null runtime span with an
invented authored location.

The static registry is ordered and exhaustive. Its row order is the
same-boundary precedence order:

```text
target_below_2_23                    P_SCHEMA_EXACT      S_DELIVERY
delivery_type_invalid                P_SCHEMA_NULL       S_DELIVERY
delivery_enum_invalid                P_ENUM_NULL         S_DELIVERY
attempts_literal_required            P_INT_NULL          S_ATTEMPTS
attempts_type_invalid                 P_INT_NULL          S_ATTEMPTS
attempts_out_of_range                 P_INT_EXACT         S_ATTEMPTS
attempts_pairing_invalid              P_PAIRING_NULL      S_ATTEMPTS
fragment_application_required        P_FRAGMENT_NULL     S_FRAGMENT
contract_suffix_required             P_FRAGMENT_NULL     S_RESULT
isolation_required_unsupported       P_CAPABILITY_NULL   S_PROVIDER
interactive_capability_absent        P_ABSENT            S_TEMPLATE
interactive_capability_schema_unsupported P_SCHEMA_NULL  S_TEMPLATE
turn_boundary_messages_not_true      P_BOOL_FALSE        S_TEMPLATE
interactive_capability_malformed     P_CAPABILITY_NULL   S_TEMPLATE
call_policy_carriage_missing         P_CARRIAGE_NULL     S_CARRIAGE_PREFIX
call_policy_carriage_extra           P_CARRIAGE_NULL     S_CARRIAGE_PREFIX
call_policy_carriage_mismatch        P_CARRIAGE_NULL     S_CARRIAGE_PREFIX
attempt_identity_version_mismatch    P_CARRIAGE_NULL     S_CARRIAGE_PREFIX
attempt_evidence_version_mismatch    P_CARRIAGE_NULL     S_CARRIAGE_PREFIX
candidate_path_preexisting           P_CANDIDATE_NULL    S_CANDIDATE
preparation_failed                   P_CANDIDATE_NULL    S_CANDIDATE
submit_endpoint_allocation_failed    P_LIFECYCLE_NULL    S_ENDPOINT
evidence_append_failed               P_PUBLICATION_NULL  S_LEDGER
candidate_reset_failed               P_CANDIDATE_NULL    S_CANDIDATE
candidate_freeze_failed              P_CANDIDATE_NULL    S_CANDIDATE
ingress_shutdown_failed              P_LIFECYCLE_NULL    S_ENDPOINT
submit_binding_foreign               P_LIFECYCLE_NULL    S_ENDPOINT
submit_binding_stale                 P_LIFECYCLE_NULL    S_ENDPOINT
submit_request_conflict              P_LIFECYCLE_NULL    S_ENDPOINT
submit_duplicate_in_flight           P_LIFECYCLE_NULL    S_ENDPOINT
submit_lifecycle_invalid             P_LIFECYCLE_NULL    S_ENDPOINT
provider_exited_before_submit        P_LIFECYCLE_NULL    S_LIFECYCLE
output_validation_failed             P_VALIDATION_CODE   S_Q2
structured_result_validation_failed  P_VALIDATION_CODE   S_Q2
materialization_attempts_exhausted   P_RANGE_EXACT       S_LIFECYCLE
adapter_start_failed                 P_LIFECYCLE_NULL    S_ADAPTER
initial_offer_failed                 P_LIFECYCLE_NULL    S_ADAPTER
retry_offer_failed                   P_LIFECYCLE_NULL    S_ADAPTER
close_offer_failed                   P_LIFECYCLE_NULL    S_ADAPTER
natural_join_failed                  P_LIFECYCLE_NULL    S_ADAPTER
adapter_start_cleanup_incomplete     P_LIFECYCLE_NULL    S_ADAPTER
adapter_cleanup_failed               P_LIFECYCLE_NULL    S_ADAPTER
provider_zero_survivor_unproven      P_LIFECYCLE_NULL    S_ADAPTER
interrupted_nonterminal_visit        P_LIFECYCLE_NULL    S_LIFECYCLE
evidence_publication_failed          P_PUBLICATION_NULL  S_PUBLICATION
frozen_restoration_failed            P_CANDIDATE_NULL    S_CANDIDATE
frozen_verification_failed           P_CANDIDATE_NULL    S_CANDIDATE
workflow_state_commit_failed         P_PUBLICATION_NULL  S_STATE
```

Deadline reasons are generated exactly twice per row below: the named
`before` and `during` reasons both use `P_DEADLINE_NULL`, the listed code, and
source profile. No other `deadline_exhausted_*` token is legal.

| Operation order | Before reason | During reason | Code | Source profile |
| --- | --- | --- | --- | --- |
| preparation | `deadline_exhausted_before_preparation` | `deadline_exhausted_during_preparation` | `provider_phased_preparation_failed` | `S_CANDIDATE` |
| ledger append | `deadline_exhausted_before_ledger_append` | `deadline_exhausted_during_ledger_append` | `provider_phased_evidence_failed` | `S_LEDGER` |
| adapter start | `deadline_exhausted_before_start` | `deadline_exhausted_during_start` | `provider_phased_start_timeout` | `S_ADAPTER` |
| submit endpoint allocation | `deadline_exhausted_before_submit_endpoint_allocation` | `deadline_exhausted_during_submit_endpoint_allocation` | `provider_phased_preparation_failed` | `S_ENDPOINT` |
| initial offer | `deadline_exhausted_before_initial_offer` | `deadline_exhausted_during_initial_offer` | `provider_phased_turn_offer_timeout` | `S_ADAPTER` |
| retry offer | `deadline_exhausted_before_retry_offer` | `deadline_exhausted_during_retry_offer` | `provider_phased_turn_offer_timeout` | `S_ADAPTER` |
| submit admission/snapshot | `deadline_exhausted_before_submit` | `deadline_exhausted_during_submit` | `provider_phased_submit_timeout` | `S_ENDPOINT` |
| Q2 validation | `deadline_exhausted_before_validation` | `deadline_exhausted_during_validation` | `provider_phased_submit_timeout` | `S_Q2` |
| candidate reset | `deadline_exhausted_before_candidate_reset` | `deadline_exhausted_during_candidate_reset` | `provider_phased_candidate_reset_failed` | `S_CANDIDATE` |
| candidate freeze | `deadline_exhausted_before_candidate_freeze` | `deadline_exhausted_during_candidate_freeze` | `provider_phased_candidate_freeze_failed` | `S_CANDIDATE` |
| close offer | `deadline_exhausted_before_close_offer` | `deadline_exhausted_during_close_offer` | `provider_phased_graceful_close_timeout` | `S_ADAPTER` |
| ingress shutdown | `deadline_exhausted_before_ingress_shutdown` | `deadline_exhausted_during_ingress_shutdown` | `provider_phased_ingress_shutdown_timeout` | `S_ENDPOINT` |
| natural join | `deadline_exhausted_before_join` | `deadline_exhausted_during_join` | `provider_phased_natural_close_failed` | `S_ADAPTER` |
| evidence publication | `deadline_exhausted_before_evidence_publication` | `deadline_exhausted_during_evidence_publication` | `provider_phased_publication_failed` | `S_PUBLICATION` |
| frozen restoration | `deadline_exhausted_before_frozen_restoration` | `deadline_exhausted_during_frozen_restoration` | `provider_phased_publication_failed` | `S_CANDIDATE` |
| frozen verification | `deadline_exhausted_before_frozen_verification` | `deadline_exhausted_during_frozen_verification` | `provider_phased_publication_failed` | `S_CANDIDATE` |
| state commit | `deadline_exhausted_before_state_commit` | `deadline_exhausted_during_state_commit_preparation` | `provider_phased_publication_failed` | `S_STATE` |
| adapter cleanup | `deadline_exhausted_before_adapter_cleanup` | `deadline_exhausted_during_adapter_cleanup` | `provider_phased_cleanup_failed` | `S_ADAPTER` |

Construction is exact: select the code from the pairing table, select the
value/source metadata from one registry, normalize the value, set summary to
the reason token, construct the primary source, then construct the exact
related-owner list. A Q2 wrapper uses its exact existing violation token only;
no other reason accepts a dynamic canonical token. The validator for
`provider_phased_delivery_diagnostic.v1` reruns this projection and rejects
any producer object whose code, value, summary, primary owner, related-source
presence/order, path/span policy, or precedence source differs.

The primary decision precedence is fixed:

```text
target
  -> surface syntax/type
  -> eligibility
  -> static capability
  -> carriage/load
  -> runtime capability
  -> runtime lifecycle
```

Within surface syntax/type the order is delivery type, delivery enum, attempts
literal/type, attempts range, then attempts pairing. Within eligibility it is
fragment, suffix, then isolation. Capability order is absent, schema,
turn-boundary-messages, then remaining malformed fields. Carriage order is
missing, extra, unequal, identity version, then evidence version. Runtime
lifecycle follows serialized event order; an earlier admitted event is primary
before consulting a later registry row. At one operation boundary, a
before-operation deadline refusal wins without starting the operation; an
operation failure wins only when the after-check still has positive budget;
otherwise the exact during-operation deadline reason wins. Q2 validation keeps
its fixed output-position-then-structured-result order, and publication uses
evidence publication, restoration, verification, state-commit preparation,
then the atomic commit linearization order. Adapter-cleanup reasons are always
supplemental to the already-selected pre-proof primary diagnostic and are
ordered before-timeout, during-timeout, failed-start incomplete cleanup,
adapter failure, then zero-survivor-unproven by the same before/after rule.
An abort result with the wrong type, malformed fields, or missing/mismatched
active `handle_id` selects `adapter_cleanup_failed` at the adapter-failure
position; it never reaches the zero-survivor or ledger-evidence projections.
The raw production token
`interactive_terminal_start_cleanup_incomplete` selects
`adapter_start_cleanup_incomplete` exactly; it never falls through to a
producer-selected generic reason.

When more than one rule is observable at the same boundary, the earliest rule
supplies the whole projected diagnostic. `related_sources` comes only from
that reason's selected source profile; later rejected rules never append
sources. This satisfies principle 28 without making diagnostics depend on how
many validators happened to run. It does not widen the authoring surface:
principle 29 remains the primitive `:composed|:phased` enum and literal integer
`1..3`, with no nominal delivery or attempt taxonomy.

## Races, Timeouts, And Failure

The coordinator owns one serialized event order. Listener and adapter threads
may enqueue immutable events and await receipts; they do not mutate state,
ledgers, candidates, or lifecycle directly.

| Race | Required outcome |
| --- | --- |
| two distinct submits overlap | serialize them; only the first request valid in the current state may validate, and the other receives `provider_phased_submit_protocol_invalid` |
| exact submit request replay | return the prior durable receipt without revalidation |
| deadline vs submit | only an event dequeued and fully admitted while `monotonic_now < deadline` enters serialized work; a queued event reached at or after expiry receives the exact terminal timeout receipt, and an admitted event that crosses expiry fails at its next mandatory after-check |
| candidate changes during digest/validation/freeze | fail with `provider_phased_candidate_freeze_failed`; do not publish or retry from an unbound snapshot |
| invalid reset vs provider rewrite | identity mismatch or a non-absent postcondition fails with `provider_phased_candidate_reset_failed` |
| failed start vs backend allocation | consume only the closed start outcome; no handle implies nothing, `not_required/true` requires the no-allocation proof, and `interactive_terminal_start_cleanup_incomplete` is T0 `incomplete/false` |
| candidate endpoint locator vs actual address race | the pre-start locator reserved nothing; after successful provider start, loss of the bind/allocation race is exactly `submit_endpoint_allocation_failed`, offers no turn, and follows T1 |
| provider exits before a submit | fail with `provider_phased_provider_exited_before_submit` |
| provider exits after valid freeze and close offer | `join` still must return the complete natural zero-exit proof |
| interruption before initial `T2` offer | abort and quarantine; no result publication |
| interruption during retry | abort and quarantine; retained digests are evidence only |
| interruption after valid freeze but before successful natural join | discard authority of the frozen candidate, abort/clean if possible, quarantine, and publish no result |
| interruption in `JOINED_PENDING_COMMIT` | fail publication directly, retain non-authoritative candidates, and never abort the terminal handle |
| close/join/state commit vs interruption | publication is legal only if natural join and the final state commit win before interruption |

The authored `:timeout-sec` is one whole-attempt deadline covering start,
initial offer, all submit waits, validation, resets, retry offers, close, join,
pre-proof adapter cleanup, endpoint terminalization, and publication. The
coordinator derives one finite absolute monotonic deadline exactly once after
policy/capability admission and before candidate, inert binding/locator, and
ledger preparation. Q5 adds no second authored timeout.

Every coordinator-local serialized operation and every adapter operation has
two mandatory clock observations against that same clock:

1. immediately before the operation starts; and
2. immediately after it returns, before its output can authorize another
   mutation, receipt, offer, publication stage, or state commit.

The closed coordinator-local operation order is ledger append-plus-fsync,
post-start submit-endpoint allocation, submit admission/snapshot, Q2
validation, candidate reset, candidate freeze, ingress shutdown, functional-v3
evidence publication, frozen restoration, frozen verification, and
state-commit preparation. Adapter operations are start, initial offer, retry
offer, close offer, join, and the one permitted pre-proof abort/cleanup.
Pre-start preparation uses the same observations and maps ordinary
non-deadline failures to
`provider_phased_preparation_failed`; its phase-ledger header append uses the
ledger-specific timeout reasons. Post-start endpoint allocation uses its exact
separate before/during reasons and maps ordinary failure to
`submit_endpoint_allocation_failed`.

If the before-check observes expiry, the operation makes zero calls and emits
its exact `deadline_exhausted_before_*` reason. If the operation starts with
positive budget but its after-check observes expiry, the coordinator discards
or retains its output only as non-authoritative provisional failure material,
starts no later normal action, and emits the exact
`deadline_exhausted_during_*` reason. Admission before expiry never shields
long validation, reset, freezing, evidence, restoration, verification, or
state preparation from this after-check.

The zero-call rule still applies to adapter cleanup: expiry before abort starts
zero adapter backend actions and records the supplemental
`deadline_exhausted_before_adapter_cleanup`; expiry during it records the
supplemental during reason and an incomplete cleanup outcome. The only
exception is mandatory coordinator-local endpoint fail-safe terminalization.
When ingress shutdown is reached with no remaining budget, normal ingress work
is not admitted, `deadline_exhausted_before_ingress_shutdown` becomes primary,
and the local close/cancel/join path reaps workers whose own waits were already
capped at that deadline. It cannot publish, return success, call the adapter
again, or create a new authored/runtime budget.

Every adapter operation receives no more than the remaining deadline through
the prerequisite interface and no adapter helper/background call may outlive
it. Every submit listener/worker wait is independently capped at the same
absolute deadline. Ingress shutdown first disables admission, replies to every
queued request, closes the listener, and joins workers that are already
deadline-bounded. It continues every permitted fail-safe action after a
timeout diagnostic, emits `ingress_shutdown_finished` only when the
zero-survivor postcondition is proved, and otherwise emits
`ingress_shutdown_failed` and follows the applicable T2a/T2b edge with
truthful incomplete endpoint status.

`join` has one irreversible ordering refinement: after return, validate the
complete natural zero-exit proof, atomically enter
`JOINED_PENDING_COMMIT`, then perform the after-check. If that check observes
expiry, `deadline_exhausted_during_join` fails directly from
`JOINED_PENDING_COMMIT`, records the proof when possible, and makes zero abort
calls.

The state owner prepares all blocking commit material non-authoritatively under
the state-commit-preparation observations. It then acquires the existing atomic
state lock and performs one final monotonic check at the commit linearization
point. Expiry there emits `deadline_exhausted_before_state_commit` and writes
nothing authoritative. Only a check with positive remainder may atomically
publish result, artifacts, terminal state, and `current_step` clearance. Once
that atomic linearization occurs, the commit—not a later wall-clock sample or
ledger row—wins; no after-deadline rollback is invented.

The post-commit `publication_succeeded` ledger append still receives before and
after observations, but it is best-effort evidence after authority already
linearized. Expiry before it makes zero append calls; expiry during it reports
only evidence damage when possible. Neither case can retroactively fail or
erase the committed result, and no later authoritative action depends on that
row.

First-admitted-event precedence applies only between listener, adapter,
interruption, and timer events whose admission checks all completed before
expiry. It orders those events but does not waive any operation's after-check.
When the coordinator next reaches an event queued at or after expiry, it
terminalizes it with the applicable exact deadline diagnostic and never begins
its requested action.

Each code below carries the exact closed diagnostic object and one of its
admitted reason tokens:

| Code | Terminal condition |
| --- | --- |
| `provider_phased_preparation_failed` | candidate-set, inert binding/locator, or interactive-invocation preparation fails before start, or submit-endpoint allocation fails after successful start |
| `provider_phased_evidence_failed` | the phase-ledger header or a required pre-receipt event cannot be made durable |
| `provider_phased_start_failed` | the interactive task turn returns the closed failed-start outcome on the exact attempt; its allocation/handle-free cleanup evidence controls T0 |
| `provider_phased_start_timeout` | the whole-attempt deadline is exhausted before or during adapter start |
| `provider_phased_turn_offer_failed` | initial or retry input cannot be durably offered |
| `provider_phased_turn_offer_timeout` | the deadline is exhausted before or during initial/retry offer |
| `provider_phased_submit_timeout` | no eligible submit completes before the whole-step deadline |
| `provider_phased_submit_protocol_invalid` | foreign, stale, conflicting, duplicate-in-flight, or wrong-state submit |
| `provider_phased_provider_exited_before_submit` | the provider exits before an eligible materialization submit |
| `provider_phased_candidate_path_preexisting` | a bound candidate path is not absent before launch |
| `provider_phased_candidate_reset_failed` | invalid candidate paths cannot be safely returned to exact absence |
| `provider_phased_candidate_freeze_failed` | candidate identity changes or immutable freezing fails |
| `provider_phased_materialization_attempts_exhausted` | the last permitted submission is invalid |
| `provider_phased_graceful_close_failed` | the normal close cannot be offered durably |
| `provider_phased_graceful_close_timeout` | the deadline is exhausted before or during close offer |
| `provider_phased_ingress_shutdown_failed` | endpoint admission cannot be disabled or its listener/workers cannot reach the mandatory zero-survivor postcondition |
| `provider_phased_ingress_shutdown_timeout` | endpoint shutdown starts too late or crosses the whole-attempt deadline; mandatory local cancellation/join still runs and its complete/incomplete proof status is recorded |
| `provider_phased_natural_close_failed` | complete natural zero-exit join proof is unavailable |
| `provider_phased_publication_failed` | terminal functional-v3 evidence publication, frozen candidate restoration/verification, state-commit preparation, or atomic state commit fails or crosses its applicable deadline gate |
| `provider_phased_cleanup_failed` | failed-start cleanup is incomplete, or the one later pre-proof cleanup operation fails, crosses the deadline, returns a wrong-type/malformed/missing-or-mismatched-handle proof, or cannot prove provider zero survivors; supplemental only |
| `provider_phased_interrupted_visit_quarantined` | controller interruption leaves a nonterminal phased visit |

Before successful natural join, terminal failure invokes exactly one `abort`
when a live handle exists, records the mandatory cleanup outcome when the
ledger remains writable, publishes no result/artifact mapping, and preserves
the named primary diagnostic. Cleanup failure is supplemental and cannot
convert failure into success or replace the primary diagnostic. In
`JOINED_PENDING_COMMIT`, failure performs no abort or cleanup call; it follows
T4 directly.

`provider_zero_survivor_proven: false` means exactly that the cleanup evidence
did not prove pane/server absence. It asserts neither presence nor absence.
The deadline-aware adapter still forbids a backend action or waiter from
outliving the supplied deadline, and the coordinator continues all permitted
local reaping, but neither the terminal row nor the surrounding prose upgrades
that execution guarantee into a missing proof.

## Resume

Q5 uses only the current interruption semantics and has no dependency on a
pending resume-semantics change.

- A compatible already-completed provider boundary is reused through the
  existing source, program, call-frame, bound-input, checkpoint, result
  contract, and completed-boundary guards. Resume does not read the phase
  ledger or reopen candidate files.
- A nonterminal phased visit discovered by ordinary resume is quarantined and
  records sticky run failure
  `provider_phased_interrupted_visit_quarantined`.
- Quarantine retains content-free partial evidence, clears the exact
  `current_step` as the existing interruption envelope requires, and never
  reuses the endpoint, client, handle, candidate, or ledger.
- Ordinary resume neither continues nor reruns that visit. An explicit force
  restart or a new run is required.

There is no persisted phase cursor, materialization-submission resume point, or
ledger-driven recovery path.

## Compatibility And Normative Impact

- Calls that omit `:delivery` remain byte- and behavior-identical composed
  calls, regardless of whether the provider declares interactive capability.
- Explicit `:delivery :composed` uses the composed runtime path.
- Explicit phased delivery on an unsupported provider fails closed; capability
  absence is not fallback selection.
- Target 2.20/2.21 Q1/Q2 artifacts, compiled fragment identities, and behavior
  remain unchanged.
- Target-2.22 and target-2.23 composed calls retain Q3 attempt identity v1 and
  functional evidence v2 exactly. A phased target-2.23 call requires Q3
  attempt identity v2 plus functional evidence v3 and fails closed on every
  mixed or downgraded pair.
- Q5 requires the landed/accepted Q3 role, one-render, binding-plan,
  publication, validation, and comparison substrate. It has no Q4 judgment
  dependency.
- Q2 result and artifact authority remains unchanged: expected outputs and the
  structured bundle validate jointly, then their disjoint maps publish once.
- Execution/evidence bytes for composed targets remain unchanged. After Q5
  ships, the report-only prompt-context projection is globally
  `workflow_prompt_context_report.v2`; it retains old evidence in place and
  uses fixed nullable identity fields rather than projecting canonical `C` as
  `final_prompt`.
- State schema remains 2.1 because the new lifecycle evidence is an
  attempt-owned sidecar and interruption uses the existing sticky run-error
  envelope. The call policy remains program/configuration input.

If Q5 is accepted and selected for implementation, normative amendments are
required in:

- `specs/dsl.md` for target-2.23 syntax and diagnostics, including opening
  the closed compiler-owned `provider_call_policy` mapping (canonical
  model-then-effort order) to the two Q5 keys;
- `specs/providers.md` for the coordinator, capability admission, byte cut,
  deadline-aware adapter interface, closed start outcome/proof union, inert
  pre-start binding/locator values, post-start actual endpoint bind, the
  handle-free `PhasedFailedCleanupEvidence` projection, exact active-handle
  validation before projecting the unchanged target-2.17
  `FailedCleanupProof`, the closed `provider_cleanup_proof` event union,
  submit/endpoint terminalization protocol, validation, and publication,
  including the closed
  `provider_call_policy`/`call_policy_bindings` key sets: the Q5 delivery
  keys are runtime-consumed coordinator input, exempt from the
  binding-required provider argv translation, and never substituted into
  provider commands at `prepare_invocation`;
- `specs/state.md` for the sidecar, natural-proof-before-ledger
  `JOINED_PENDING_COMMIT` transition, post-join publication failure, completed
  reuse, and interrupted-visit quarantine;
- `specs/versioning.md` for the target and compatibility boundary;
- `docs/design/workflow_lisp_prompt_identity_diagnostics.md` (target 2.22)
  for attempt identity v2, functional evidence v3, actual-delivery rows,
  report-v2 fixed identity projection, version-gated comparison, and the rule
  that canonical `C` is not a delivered `final_prompt`; and
- `docs/design/workflow_lisp_frontend_specification.md` for exact frontend/IR
  carriage.

`specs/io.md` remains unamended in this tranche because isolation-required
attempts are excluded from phased admission; lifting that exclusion is a
separate future amendment.

The capability matrix must remain “designed/not available” until
implementation, executable evidence, normative updates, and final reviews
land.

## Feasibility Prerequisite

The existing code proves the individual
`InteractiveTerminalTurnQueueAdapter` primitives and proves their use inside a
peer-group lifecycle. It does not yet give `start`, `offer`, or `offer_close`
the caller's whole-attempt deadline; its exception-only failed-start boundary
can allocate a backend and return no handle or cleanup proof. In particular,
the current `interactive_terminal_start_cleanup_incomplete` exception is
evidence of incomplete cleanup, not evidence that cleanup was unnecessary.
Existing code also does not prove Q5’s ordinary-call lifecycle, multiple
materialization submissions, candidate reset, actual-delivery identity, or
valid-result publication. The peer-group coordinator and `peer-finish`
therefore cannot be used as feasibility evidence for this coordinator.

Before implementation planning, Q3 must be implemented and accepted, the
deadline-aware adapter extension plus target-2.17 compatibility proof must
land, and an executable proof must use that production adapter, its exact
structural capability, and a real supported interactive provider to
demonstrate:

1. the exact closed `InteractiveTerminalStartOutcome` on successful start and
   all three failed-start combinations, with the existing target-2.17 peer
   caller migrated to consume the union without changing its launch,
   settlement, cleanup, or evidence behavior; and the exact adapter-issued
   no-allocation proof from untouched created state with zero backend calls;
   the existing target-2.17 `abort` still returns handle-bound
   `FailedCleanupProof` with no type or field change;
2. one deadline-aware successful `start` with a counted task action;
3. two distinct literal `offer` payloads reaching two successive natural turn
   boundaries in the same client, without interpreting pane text;
4. deadline-aware `offer_close` followed by complete natural `join`;
5. an operation whose remaining whole-attempt budget is smaller than the
   configured adapter timeout and no call that outlives that remainder; and
6. no Q5 coordinator, submit endpoint, candidate validation/reset, peer-group
   coordinator, peer command, cancellation, session-resume command, pane-text
   authority, or second provider process.

The three failed-start fixtures are exact: explicit no-backend-allocation
proof gives `none/not_required/true`; a possibly allocated backend with
complete absence proof gives `possible_or_allocated/completed/true`; and the
production `interactive_terminal_start_cleanup_incomplete` path gives
`possible_or_allocated/incomplete/false` with its exact incomplete
`PhasedFailedCleanupEvidence`. Neither failed-start branch carries
`FailedCleanupProof`, because neither has a handle. The compatibility gate
must also prove that a missing handle alone cannot select the first branch,
that no start failure escapes as an exception without the closed outcome, and
that a post-start abort proof with a missing/mismatched active `handle_id`
fails closed as `adapter_cleanup_failed` and contributes no ledger evidence.

Failure of any item stops implementation planning and returns the design for
revision. A fake adapter cannot satisfy this prerequisite. Conversely, this
pre-planning probe must not implement or claim the Q5 coordinator, identity-v2,
functional-v3, candidate reset, invalid-then-valid correction, atomic
publication, or post-join failure behavior. Those are implementation
completion/review gates below, not circular prerequisites to writing their
implementation plan.

After a reviewed implementation plan authorizes Q5 work, implementation
completion requires the production coordinator and deterministic fixtures to
prove:

1. an invalid artifact-or-result candidate submitted through the attempt-bound
   command, complete digest recording, exact candidate reset, a diagnostic
   retry offer, and a valid second submission in the same client with one task
   action;
2. exact attempt-identity-v2/functional-v3 actual-delivery rows for task,
   initial materialization, and retry, with no claim that `C` was delivered
   whole;
3. the fixed report-v2 identity projection, same-version comparison,
   `actual_delivery_drift`, and `identity_version_mismatch` behavior;
4. endpoint disable/reject/drain/close/join with zero coordinator-owned
   survivors on success, every pre-join failure, and every post-join failure;
5. the before/after deadline matrix for coordinator-local and adapter
   operations, including admitted work that crosses expiry and therefore
   cannot authorize a later action or commit; and
6. `JOINED_PENDING_COMMIT` restoration/verification failure, state-commit
   failure, and `join_succeeded` ledger append/fsync failure. Each ends
   `FAILED`, retains only non-authoritative provisional evidence, makes zero
   abort calls after the validated natural-join proof, and records the proof in
   `terminal_failed` only when the ledger can accept that row;
7. all T0–T4 terminalization productions, including start/initial-offer/retry-
   offer/close/join failures, T2a cleanup-pending and T2b cleanup-finished
   ingress failure, terminalizing ingress success/failure outcomes, complete
   and incomplete cleanup, the three failed-start proof combinations, exact
   `provider_cleanup_proof` member/null legality, valid exact-active-handle
   projection from `FailedCleanupProof`, rejection of missing/mismatched
   handle identity with no raw proof in the ledger, pre-start T0 with zero
   endpoint resources, post-start endpoint-address race failure, one-or-zero
   abort calls as applicable, no duplicate ingress, and no cleanup after
   natural proof;
8. a generated bijection over all closed diagnostic reasons, their one legal
   code, value/source profiles, and before/during operation rows; and
9. offline ledger validation using only ledger bytes, with complete digest
   category coverage and distinct opaque equality/order versus recomputable
   seal mismatch results.

## Verification Matrix

| Contract | Required evidence |
| --- | --- |
| adapter feasibility | pre-planning only: landed deadline-aware `start`/`offer`/`offer_close`; exact successful plus three failed `InteractiveTerminalStartOutcome` fixtures with handle-free `PhasedFailedCleanupEvidence`; explicit no-allocation proof rather than handle inference; production start-cleanup-incomplete maps to incomplete/false; unchanged target-2.17 handle-bound `FailedCleanupProof` and peer compatibility; valid exact-active-handle post-start projection plus missing/mismatched-handle rejection; below-configured remaining-budget checks; zero backend calls after pre-call expiry; no background operation beyond the caller deadline; one real start/two-offer/close/join same-client probe with no Q5 coordinator claims |
| exact byte cut | `T1 || T2 == C` across empty/non-empty prompt, trailing-LF/no-trailing-LF, Q1-only/Q2 output-position, no-guidance/authored-guidance, and consumed-artifact disabled/empty/prepend/append/mixed variants |
| protocol accounting | exact frame, slice, final-offer, submit-key byte counts/digests; identity-v2 composition seal over exact successful task/initial/retry order; protocol bytes never enter `C` |
| target and IR | below-target rejection; literal/range/pairing diagnostics; exact paired call-policy and attempt-identity version carriage through classic/WCC, Core, Semantic IR, Executable IR, persisted config, checkpoint, and `RuntimeStep`; mixed v1/v2/v3 rejection |
| diagnostic totality | every static reason and every generated before/during reason occurs once in the reason registry and once in the code pairing; exact value type/nullability/normalization, `summary == reason` for every profile with zero null summaries, primary owner, related-source presence/order, and precedence revalidate from the diagnostic alone |
| capability refusal | missing, malformed, wrong-version, messages-disabled, inferred-only, and runtime-drift cases emit the exact table-derived `provider_phased_delivery_diagnostic.v1`, with zero provider starts and no composed fallback |
| invalid artifact | valid structured result plus missing/invalid expected output records a digest manifest, publishes nothing, clears exact paths, and retries only when budget remains |
| invalid result | valid expected output plus missing/malformed/wrong-contract bundle follows the same containment and no-publication rule |
| retry containment | each retry reuses exact `T2`, adds separately accounted diagnostic framing, requires complete candidate recreation, and never offers `T1` or calls `start` again |
| no early authority | no result, artifact map, lineage, successful step state, or route value before valid freeze plus natural join |
| interruption | separate cases before initial `T2` offer, during retry, and after valid freeze before close/join all quarantine sticky-failed and cannot be ordinarily resumed |
| phase ledger | canonical JSONL, exact header/common/event key sets and scalar domains, contiguous sequence from header zero, ordinal/count arithmetic, record-before-action/receipt ordering, embedded complete reject/freeze manifests, exhaustive recomputable-seal/opaque-reference partition, closed validator precedence and malformed/truncated mapping, and no resume/result authority |
| failure grammar | executable traces cover T0–T4 including T2a cleanup-pending and T2b cleanup-finished; every pre-proof path has exactly one cleanup outcome overall; each cleanup status admits exactly its closed handle-free `provider_cleanup_proof` member, with null limited to enumerated post-start no-projection or invalid-handle-proof cases; handle-bound `FailedCleanupProof` is never a ledger member; an allocated ingress has at most one start and one finished-or-failed outcome; terminalizing ingress failure emits `ingress_shutdown_failed` without duplicate cleanup/start; start/offer/close/join failures reach the appropriate structural or durable endpoint outcome and terminal row; incomplete cleanup is truthful; and post-proof paths have zero abort/cleanup |
| races and timeouts | request replay/conflict, concurrent submit, candidate mutation/reset race, provider early exit, pre-start locator with a competing actual-address claimant, post-start bind/allocation race classified as endpoint allocation failure, every before/during coordinator-local and adapter deadline reason, admitted-work expiry, shortened adapter budgets, offer failure, cap exhaustion, close failure, ingress shutdown, join timeout, and publication failure |
| endpoint terminality | pre-start binding/locator derivation creates and reserves no endpoint resource; T0 discards those inert values with zero coordinator-owned endpoint survivors; actual address bind begins only after successful start; ingress disables after the accepted-closing receipt; every queued/later submit receives the deterministic failed receipt; success and complete-failure paths prove listener/worker zero survivors; incomplete paths emit `ingress_shutdown_failed`, record exactly which provider or endpoint proof is absent, and never duplicate ingress/cleanup or claim success |
| post-join failure | receipt of validated natural proof changes lifecycle before `join_succeeded` evidence; join-row append, restoration/verification, evidence publication, and state-commit failure from `JOINED_PENDING_COMMIT` retain non-authoritative material, never abort the terminal handle, and conditionally record the proof only while writable |
| composed compatibility | omitted delivery on capable and incapable providers yields exact pre-Q5 prompt, invocation, IR omission, validation, result, evidence, and resume bytes |
| identity/evidence | Q1/Q2 compiled fragment identities unchanged; target-2.22 and target-2.23 composed Q3 v1/functional-v2 unchanged; phased identity-v2/functional-v3 distinguishes canonical `C` from exact actual deliveries and is never read by result/resume; report v2 projects fixed nullable legacy/canonical/delivery fields without a false final-prompt claim |
| real consumer | target-2.23 `review_revise_design_docs.orc` phased run proves exact Q2 path/result validation, task once, invalid-then-valid correction, natural close, atomic publication, and the principle-30 debt classification above |

Tests must assert behavioral, contract, artifact-lineage, and dataflow
properties. They must not assert literal prompt prose.

## Stop / Revise Criteria

Revise this design if:

- the real adapter cannot sustain invalid then valid submissions in one client
  without cancellation or a provider-session resume command;
- natural boundary delivery requires reading or interpreting pane text;
- candidate reset cannot be limited to preflight-absent bound files;
- the Q2 validators cannot validate and freeze both surfaces without partial
  state publication;
- Q1/Q2 compiled identity or composed-call Q3 v1/functional-v2 bytes must
  change;
- actual task/materialization/retry delivery cannot be represented without
  calling canonical `C` a delivered `final_prompt`;
- report projection cannot expose functional-v3 without a fixed versioned
  identity shape or same-version comparison;
- any adapter, coordinator-local operation, endpoint worker, or publication
  action can authorize a later action or commit after crossing the coordinator
  deadline;
- failed start can escape without the closed outcome, infer no allocation from
  a missing handle, claim `not_required/true` without the exact no-allocation
  proof, or fail to map production start-cleanup-incomplete to T0
  incomplete/false;
- `cleanup_finished` needs more than the one exact
  `null|NoBackendAllocationProof|PhasedFailedCleanupEvidence` slot, a cleanup
  status cannot select exactly one admitted member/null case, handle-bound
  `FailedCleanupProof` must enter the ledger, or null would be accepted outside
  the enumerated post-start no-projection/invalid-proof cases;
- the existing adapter `FailedCleanupProof` cannot remain handle-bound and
  target-2.17-compatible, the coordinator cannot validate exact active handle
  identity before projection, or a missing/mismatched proof could become
  ledger evidence;
- deriving the pre-start submit binding or candidate locator must bind or
  reserve an address, allocate any endpoint resource, or actual endpoint
  binding cannot remain strictly after successful provider start;
- endpoint terminalization cannot prove zero coordinator-owned survivors on
  success or cannot truthfully distinguish complete from incomplete proof on
  failure;
- any pre-proof path lacks exactly one cleanup outcome overall, T2a fails to
  finish pending cleanup, T2b emits cleanup again, terminalizing ingress
  failure lacks its failed outcome, ingress repeats, or any terminal edge is
  ambiguous; any post-proof failure calls abort;
- any closed diagnostic reason lacks one exact code/value/source/precedence
  projection, permits a null or non-reason summary, or permits producer-chosen
  enum/string, nullability, or related-source behavior;
- the offline ledger validator must read non-ledger bytes, recomputes an opaque
  digest, leaves a digest field uncategorized, or conflates opaque
  equality/order mismatch with recomputable-seal mismatch;
- post-join publication failure requires `abort` on a terminal handle;
- pre-planning adapter feasibility would require implementing the Q5
  coordinator, candidate reset, identity-v2, or publication behavior;
- implementation needs the peer-group coordinator or `peer-finish`;
- a provider or workflow name must select the path; or
- explicit phased delivery can only work by substituting composed delivery.
