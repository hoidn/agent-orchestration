# Workflow Lisp Phased Contract Delivery

Status: selected target-2.39 evaluated migration; retained historical protocol.
The target-2.16/2.17 group and target-2.23 phased execution routes remain retired;
new calls, replay and mutation under those historical profiles are unavailable
in this package. [Executor retirement](workflow_lisp_executor_retirement.md) and
[CLI](../../specs/cli.md) govern refusal and demonstrated exact-release recovery.

Prompt fragment/output identities, one-render composition, content-free evidence, candidate validation before publication and bounded adapter cleanup remain shared contracts in [prompt calculus](workflow_lisp_prompt_calculus.md), [prompt identity](workflow_lisp_prompt_identity_diagnostics.md) and [Providers](../../specs/providers.md).

Validated provider capabilities must fail closed on absence, malformed data or
unsupported operations. Transcript/pane bytes, receipts and diagnostic views
are never typed result authority. Partial/member attempts cannot be published
as a complete result, and cleanup/recovery cannot fabricate a commit or target
a different attempt. These invariants survive in their shared owners; the
historical group-specific state machine supplies no current launch permission.

## Target 2.39 Evaluated Migration

**Design state: selected target; implementation and qualification are separate.**
The [migration plan](../plans/2026-10-16-phased-execution-239-plan.md) owns
completion evidence. This section specifies the
2.39 port; the retained anchors below continue to identify the historical
2.23 protocol. No old executable profile is reopened.

### Decision And Authority

Keep phased delivery as one provider effect with one interactive client, one
task delivery and bounded materialization correction. Reuse the retained
interactive adapter, submit protocol, phase state machine and output validators;
replace the old parent-state commit with evaluated `prepare`, `settle` and
`reconcile`. This makes interrupted work pay for a fresh task attempt and keeps
interactive capability a prerequisite; it does not provide native Agent
continuation, parallel phased workers or isolated phased execution.

[Evaluated execution](workflow_lisp_evaluated_execution.md#93-coordinators) owns
identity, memo commits, K2/K3 settlement and K4 recovery. [Providers](../../specs/providers.md#evaluated-phased-provider-delivery-target-239)
and [State](../../specs/state.md#evaluated-phased-provider-attempts-target-239)
own the normative deltas. The historical Q5 protocol supplies transport and
candidate-validation invariants, not retired state/checkpoint authority. The
[at-least-once amendment](../plans/2026-07-26-provider-at-least-once-loosening-amendment.md)
and State's provider-attempt contract supersede historical quarantine.

### Authoring And Admission

```lisp
(provider-result providers.reviewer
  :prompt (review-document :document document :report report_path)
  :delivery :phased
  :materialization-attempts 2
  :model review_model
  :effort review_effort
  :timeout-sec 3600)
```

The existing `provider-result` form returns its normal transportable typed
result. The prompt must be a typed fragment application with a generated,
nonempty result-contract suffix. Expected output positions remain optional;
when present they join the structured-result candidate validation. Normal
model, effort, timeout, required documents and result-guidance contracts apply.

- Omitted delivery and explicit `:delivery :composed` retain the existing
  composed path and its exact request, artifact and memo shapes.
- `:delivery :phased` is admitted only when its defining source targets 2.39.
  An imported older definition does not gain admission from a 2.39 caller.
- `:materialization-attempts` is an integer literal in `1..3`, defaults to `2`
  for phased delivery, and is illegal otherwise. It counts total candidate
  submissions in this attempt, not provider attempts or crash retries.
- Phased delivery requires explicit `:timeout-sec` as a positive `Int` literal.
  Omission, booleans, nonpositive values and nonliteral operands are refused;
  no inherited finite timeout is supplied. Composed delivery retains its
  optional timeout contract.
- Admission requires the exact validated
  `interactive_terminal_turn_queue.v1` capability. Validate the selected
  template before dispatch and again at the runtime capability boundary;
  never infer support from provider name, TTY, native session support or
  peer-group eligibility, and never fall back to composed delivery.
- Agent-valued calls, session publication, context capture, supervision, peer
  groups, isolation/confinement and phased effects reached by `par-map`
  workers remain refused. Sequential helpers, branches and loops are admitted
  through normal full activation identity. Parallel refusal follows reachable
  calls, including imported and specialized helpers, and is checked again by
  the source-free closed reader.

### Closed Representation And Identity

Use one new internal effect class, `provider_phased`, with exactly the normal
provider fields: `k`, `class`, `result`, `repeat`, `site`, optional provenance,
`provider`, `prompt`, `inputs`, `dependencies`, `policy` and `contract`.
`repeat` is `rerun`; policy contains literal `delivery: phased` and literal
`materialization_attempts` in addition to existing ordinary policy operands.
Reuse the existing timeout policy operand for the required positive literal;
the source-free closed checker independently enforces this phased requirement.
Composed calls remain class `provider`; there is no runtime policy-based
reclassification. `provider_phased` is a coordinator class everywhere the
closed node, site table, memo, interpreter, replay, view or invalidation path
classifies effects. Provider binding, C6 reads, result-location handling,
closure traversal and effect analysis treat it as a provider request.

This is an additive target-2.39 shape under existing
`workflow-lisp/closed-program/1`, representation `table/1`; no existing node
changes meaning or canonical bytes. The closed checker enforces the target,
exact fields, policy pairing, fragment/result contract and excluded contexts
without source. Source and typed-import compilation additionally enforce the defining
source's target; a source-free reader cannot infer an original imported-source
target that the closed representation does not carry. Older readers reject the new class; no representation upgrade,
compatibility alias or persisted-program rewrite is added.

Use the existing evaluated identity, dependency vector, memo attempt ordinal
and exclusive attempt directory. There is no provider-allocation counter,
lexical checkpoint, synthetic workflow child or second evaluator. If the
interactive adapter requires the retained `ProviderAttemptScope` carrier,
derive it deterministically from the evaluated run/identity and ordinal as a
transport projection; it cannot allocate or become independent identity.

### One Render, Task Once, Materialization Retry

Extend the evaluated prompt assembler at its existing output-contract
insertion point to return the canonical prompt plus its exact byte cut.
Keep the string-returning composed interface unchanged. Capture input and
required-document bytes once through the existing evaluated provider reader.
With `T1` the complete bytes before output-contract insertion and `T2` the
separator-inclusive suffix, `C = T1 || T2` exactly. Use the evaluated
structured-result file rendering and ordinary absolute environment result
path; transport policy `phased` is distinct from the file-rendering selector.

Reuse `provider_phased_protocol_frame.v1` for task, initial materialization and
retry framing. Start one interactive client with `F_task || T1`, queue
`F_materialization || T2` for its next natural turn, and offer only
`F_retry(diagnostics) || T2` on correction. No retry re-renders the fragment,
restarts the client or includes `T1`. Frames remain outside `C`. Record byte
counts/digests of canonical composition and actual offered turns separately;
`prompt.txt` describes canonical composition and must not be represented as
the single delivered prompt. The existing composed input-parts algorithm is
unchanged; phased input parts additionally bind the protocol version and
canonical cut. Actual deliveries are outcome evidence, not pre-dispatch input.

The argument-free `orchestrator provider-materialization-submit` command and
opaque attempt binding remain the only submission door. Preserve exact
request replay, request-conflict refusal, serialized validation and the
`retry_queued|accepted_closing|failed` receipts. Deriving a binding/endpoint
locator allocates no endpoint; bind only after successful provider start.

Candidate preflight validates containment, names, destinations and aliases,
then proves every exact bound path absent. Never delete a pre-existing user
file or clear an output directory. Every submit snapshots all candidate bytes
and runs both output-position and typed-result validation, even when one
fails. Invalid submissions clear only those exact, stable regular-file
candidates and prove absence; retries must recreate the whole set. Exhaustion,
mutation, nonregular replacement, reset/freeze failure or early provider exit
publishes no typed result. A valid submission freezes the complete candidate.

Flush the accepted submit receipt before graceful-close bytes. Disable and
drain ingress, join every owned worker, and require the exact natural zero-exit
provider proof bound to the exact active handle before projecting away that
handle identity. The coordinator immediately enters `JOINED_PENDING_COMMIT`
when that proof is validated, before evidence writes; no later error may abort
that terminal client. Restore the frozen files through safe owners and verify
bytes before preparing the evaluated commit.

### Evaluated Prepare, Commit And Settlement

The retained coordinator becomes the single `prepare` implementation. Remove
its `atomic_success_commit` parent-state binding and the assertion that its
return itself means `authoritative_state_committed`. `prepare` returns the
validated value, canonical typed-value digest and a prepared proof after
natural shutdown, frozen restoration and verification. Before returning, it
atomically persists receipt state `prepared` with that exact proof (K2
pending commit). It writes no memo or parent state.
The evaluator alone writes `committed`; only then does `settle` mark the
attempt receipt settled and append the ordinary memo `settled`. On a memo hit,
`reconcile` performs the same idempotent local settlement using the inline
commit proof, without launching, offering, validating a new candidate or
reopening the phase ledger.

The closed inline proof has schema `evaluated_phased_provider_commit.v1` and
these exact fields:

| Field | Required meaning |
| --- | --- |
| `schema_version` | The exact schema above |
| `identity`, `attempt`, `input_digest` | Exact enclosing evaluated commit identity, positive ordinal and input digest |
| `result_path`, `result_digest` | Exact enclosing run-relative result locator and phased coordinator's canonical typed-value digest; the candidate manifest separately hashes raw bundle bytes |
| `candidate_manifest` | Ordered frozen `provider_phased_candidate_digest_manifest.v1`, including the same structured result and all declared expected outputs |
| `canonical_prompt_sha256` | Digest of `C`, equal to the reached request input part |
| `actual_deliveries_sha256` | Seal of ordered successful task/initial/retry turn projections, using existing canonical projection hashing |
| `natural_shutdown` | Exact content-free natural zero-exit proof: disposition, zero return code, pane/server absence and complete proof |

For `provider_phased`, compute `result_digest` from the validated value with
`canonical_sha256(value.json_value())`, as the `run_ref` coordinator does.
The ordinary provider/command result-file digest contract remains unchanged;
do not copy the raw-byte digest returned by `validate_effect_result` into the
phased commit proof.

The memo reducer validates closed shape and scalar domains; contextual replay
binds all identities, paths, input parts, candidate declarations and result
digests to the checked node and enclosing commit. A proof from another call,
loop activation, attempt or run never authorizes settlement. K5 is satisfied
by this inline proof; reports and the diagnostic phase ledger cannot repair a
missing or malformed proof. Before the first commit, safe file reads validate
the frozen bytes and result against their declared hashes and contracts.
After commit, normal evaluated memo reuse remains authoritative: settlement
does not reopen candidate/result files or require an audit sidecar to survive.
The inline proof is sufficient to recreate an absent/torn operational receipt
as the proof-only `settled` variant under a no-follow, memo-derived attempt
directory pinned for this operation; no transport locator or candidate is
reconstructed. A present receipt with foreign binding or root replacement
observed during the operation fails closed, never gets overwritten. This
claims no preserved file descriptor across process restarts and requires no
historical directory-inode record for nondestructive committed settlement.
Ordinary downstream file-freshness rules remain unchanged.

A committed coordinator cannot be invalidated or superseded (K8). Before
commit, K4 below applies even when `prepare` finished but the memo did not.
A settlement failure after memo commit preserves that commit and an unsettled
coordinator; it must never append `failed` for the committed attempt or
redispatch it.

### Durable Ownership And Interrupted Recovery

One attempt-local `phased-attempt.json` receipt uses schema
`evaluated_phased_provider_attempt.v1`. It is the coordinator's minimal
operational ownership record, separate from best-effort phase diagnostics.
Its closed states are `intent`, `prepared`, `settled`, `abandoned`. The first,
second and fourth variants carry immutable evaluated identity, ordinal, input
digest, run-relative result path, ordered candidate declarations and private
transport identity. `intent` records successful candidate-absence preflight
and is durable before any provider allocation. `prepared` adds the exact
commit proof; `abandoned` records complete prior-attempt cleanup. The terminal
`settled` variant has exactly `schema_version`, `state` and `proof`: it keeps
that proof unchanged, needs no transport ownership fields and can be
reconstructed from the memo alone.
A receipt never supplies a workflow value or a resume phase cursor. Live
failure may mark it `abandoned` only after proving both resource and exact
candidate cleanup; otherwise resume must complete the same cleanup before
allocating any replacement, even if the memo already contains `failed`.

#### Initial Ownership Publication And Absence Classification

Publish the initial receipt through a temporary file, file fsync, atomic rename
to `phased-attempt.json`, and containing-directory fsync before any backend
allocation. Failure or interruption before that sequence returns cannot launch
the provider. Every later receipt transition uses atomic replacement; no live,
failed, abandoned or settlement path removes the canonical receipt.

Recovery assumes that the retained filesystem honors those durability
guarantees. Under this crash model, a receipt published before dispatch cannot
disappear through an admitted operation. After authority/memo checks and under
the run writer lock, confirmed absence of the exact memo-derived attempt
directory or its canonical receipt therefore classifies that uncommitted
attempt as not dispatched. Confirm canonical-leaf absence through no-follow
owners; unsafe paths, permission failures and observed root replacement are
not absence. A present torn, malformed, nonregular or foreign-bound receipt
refuses recovery without mutation.

For this not-dispatched case, preserve existing files and directories, perform
no transport scan or candidate cleanup, and manufacture no `abandoned` receipt.
Continue ordinary K4 bookkeeping and allocate the next ordinal, whose candidate
preflight must still pass. An unpublished temporary file or `prompt.txt` is not
dispatch authority. An unrecorded pre-launch transport reservation can contain
reservation metadata only, never a server or provider process.

Deletion or rollback of previously durable ownership evidence is outside this
crash-recovery guarantee: external destruction cannot be distinguished from a
pre-publication interruption. No additional deletable marker would remove that
assumption, and arbitrary same-UID state mutation is not confined. Committed
attempts retain K3's inline-proof settlement rules.

#### Adapter Reservation And Resource Ownership

Extend `InteractiveTerminalTurnQueueAdapter` and its existing tmux backend;
the evaluated owner does not become a second tmux controller. The private APIs
are `reserve_recoverable(root) -> InteractiveTerminalReservation`, which only
creates the namespace and operation lease; `start(..., reservation=...)`,
which consumes that exact reservation; and
`recover_failed(reservation, *, deadline) -> PhasedFailedCleanupEvidence`,
which needs no reconstructed live handle. Persist the reservation in
`phased-attempt.json` before calling `start`. Live `abort(handle)` shares the
same cleanup implementation and projects its handle-bound proof. `join(handle,
...)` additionally proves the registered provider group naturally empty.
These are private adapter/evaluated-owner APIs, with no authored configuration.

The receipt's `transport` has exactly these fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | `interactive_terminal_reservation.v1` |
| `adapter_token` | Full non-reused UUID token |
| `namespace` | Relative locator under the selected trusted transport root |
| `namespace_dev`, `namespace_ino`, `namespace_uid` | Integer namespace identity |
| `lease_dev`, `lease_ino` | Integer operation-lock identity |
| `boot_id` | Linux boot ID |

Create the namespace exclusively with mode `0700` and its fixed `launch.lock`
exclusively with mode `0600`; the lock inode remains fixed. Derive `tmux.sock`,
`server.json`, `client.json`, `command.json`, `revoked` and the existing
exit-status file from that namespace, and the full session name from the full
adapter token. Persisted data cannot select arbitrary child paths. All records
have strict exact-shape parsing, owner/mode checks and no-follow descriptor-rooted
access; publication uses atomic replacement plus file and directory fsync.

The adapter owns these operational records, separate from memo and ledger:

| Record | Exact fields and durable boundary |
| --- | --- |
| `server.json` | `schema_version: interactive_terminal_server.v1`, `adapter_token`, `boot_id`, `server_pid`, `server_start_ticks`, `socket_dev`, `socket_ino`; written after server observation and before `start_pane` |
| `client.json` | `schema_version: interactive_terminal_client.v1`, `adapter_token`, `boot_id`, `leader_pid`, `pgid`, `sid`, `leader_start_ticks`; written by the pane's adapter-owned pre-exec helper before provider code |
| `command.json` | `schema_version: interactive_terminal_command.v1`, `adapter_token`, `operation_token`, `kind: start_server \| start_pane`, `state: active \| completed`; only the completed variant adds `outcome: success \| failed \| timed_out` |
| `revoked` | Exact adapter token; terminal revocation of provider launch |

Require `leader_pid == pgid == sid`; otherwise refuse launch. This is the
pane's isolated group, never the caller's inherited group. The pre-exec helper
takes the same operation lease, validates namespace/token, refuses revocation,
and makes the group record durable before executing the existing status-capturing
wrapper. Recheck both the deadline and revocation immediately before exec;
lease waiting consumes the original finite absolute live deadline. The lease
descriptor is close-on-exec. Preserve provider argv, exit-status publication,
terminal and input semantics. A delayed, unregistered pane can execute only
adapter validation until this boundary, never provider code or candidate writes.

#### Leased Commands And Exact Recovery

Acquire the operation lease before spawning the adapter-owned bounded command
helper; pass the already locked descriptor with `pass_fds`. The parent closes
its duplicate without `LOCK_UN`. The helper holds the lease through the tmux
client's execution, timeout handling, termination/reap and finite output
collection, including after parent death. This covers both server creation
and pane/window creation; every resource-creating operation must use this
runner. The closed command-kind grammar currently has only `start_server` and
`start_pane`.

While leased, write `active` before spawning the tmux child and `completed`
only after proving reap and output settlement. A missing command record means
no helper crossed its pre-spawn boundary. An `active` record with an obtainable
lease means incomplete cleanup and blocks candidate changes and redispatch;
an unlocked lease alone does not prove that no child can act. Ordinary parent
death leaves the helper holding the lease to finish its bounded work. Never
kill only that wrapper with an outer `subprocess.run(timeout=...)` and orphan
its tmux client. If helper failure or deadline expiry prevents proof of
kill/reap/output settlement, retain `active` and report incomplete cleanup.
A completed failed/timed-out client is not proof of no backend allocation:
it may have forked a server before the socket appeared.

Recovery validates the exact reservation and pinned namespace/lock identities,
then acquires the same lease with its separate finite recovery deadline.
Validate command completion and durably revoke future launch before examining
the provider record. A missing `client.json` is safe only after this
lease/revocation boundary. If present, validate its shape, token and boot binding,
then use existing owned-group TERM/KILL and finite waits. Recheck a positive
live leader's start token before signalling or escalation; mismatch, permission
failure or a nonempty group at deadline refuses cleanup.

Only then stop the bound private server. Revalidate namespace/socket identity
and use one tmux connection with an `if-shell -F` condition checking the full
reserved session token and, when recorded, server PID identity; its true branch
invokes `kill-server`, its false branch emits an explicit ownership-mismatch
marker. A false condition may exit zero, so return code alone is insufficient.
Verify bound server/socket disappearance afterward. A responding server without
the full reserved token is foreign or ambiguous; missing session is not server
absence. Missing socket after failed/timed-out creation remains unresolved:
find and stop the exact reserved server or refuse cleanup, since server startup
may still be pending.

Before `server.json` exists, the durable intent, unchanged exclusive namespace
and lease identities, completed creation command under lease, and full reserved
session token together authorize guarded cleanup through the same connection.
This covers server creation before PID observation without inventing a persisted
PID. Recovery records the exact server identity it observes in `server.json`
before signalling or closing resources, so another interruption after server
termination still permits the same cleanup to complete on the next resume.
Provider-pane creation is prohibited until the server record is durable.
Use `-f /dev/null` and an inert adapter-owned anchor; user tmux configuration
and an interactive login shell cannot run in the private server. Removing the
exact bound server closes delayed pane allocation, and revocation prevents a
delayed pre-exec helper from launching provider code.

Complete cleanup requires settled creation commands, the owned group empty,
and the bound server absent. No candidate cleanup or replacement attempt may
precede all three. Server termination alone does not prove group emptiness.
Natural completion likewise requires successful exit status, naturally empty
registered group and removal of the inert private server; a residual group
is a failure even if forced cleanup later succeeds. TERM/KILL cannot produce
natural success. Strengthen the adapter's `proof_complete=True` invariant
without changing the handle-bound proof shape or its existing five-field
content-free projection: `disposition`, `return_code`, `pane_absent`,
`server_absent`, `proof_complete`. Private group identity stays in the operational
records; add no scalar to shared proof types, inline proof or historical ledger.

Ownership retains the existing [provider group limit](../../specs/providers.md):
only processes remaining in that group are covered, not escaped descendants.
Retain R3's absent-leader policy: absence alone proves no group emptiness,
recorded lingering groups can be signalled, and a positive live leader token
mismatch is refused. The existing absent-leader/reused-group ambiguity remains.
Namespace/inode/token checks detect stale identity and ordinary replacement;
they do not confine an arbitrary same-UID process able to rewrite all receipts.
No global server enumeration, broad process killing, pidfd/ctypes dependency,
general supervisor or unvalidated `InteractiveMemberHandle` reconstruction is
selected.

#### Submit Endpoint Ownership And Recovery

The existing `PhasedSubmitEndpoint` owns its listener, workers and fixed
`submit.json` operational record inside the adapter reservation namespace.
It remains a controller-thread service. Evaluated bindings supply the validated
reservation and sequence recovery; they do not implement another endpoint.
Derive the existing `phased-{nonce}.sock` locator with the full adapter token
as nonce and the reserved namespace as socket root. Trusted runtime code selects
the short transport root, never receipt data or authored configuration. Validate
both encoded socket-path lengths before reservation; the submit path is 91 bytes
under `/tmp`. Binding derivation remains inert, and candidate preflight failure
creates no endpoint record or socket.

`submit.json` has exactly `schema_version`, `adapter_token`, `boot_id`,
`controller_pid`, `controller_start_ticks`, `state`, `socket_dev`, `socket_ino`.
The schema is `phased_submit_endpoint.v1`; token and boot ID match the reservation.
PID and start ticks are positive non-Boolean integers identifying the controller
incarnation. State `binding` requires both socket fields null; `bound` requires
the observed non-Boolean integer pair (`socket_dev >= 0`, `socket_ino > 0`);
`closed` preserves the preceding pair.
Reject extra fields, invalid domains and mixed-null pairs. Use pinned no-follow
namespace access, mode `0600`, atomic replacement and file/directory fsync.

After provider start, prove the fixed child absent and durably write `binding`
before bind. Bind through the pinned namespace, retain the observed inode
immediately, then durably write `bound` before listening or starting workers.
Record-publication failure does not discard the in-memory observation. Live
shutdown closes admission and listener, drains requests and joins all workers.
Unlink only the observed socket through the pinned namespace after checking
type, UID and device/inode; replacement refuses cleanup. Write `closed` only
after the existing zero-survivor proof includes path absence. Incomplete joins
never write `closed`, even if the pathname is already absent.

Recovery requires the run writer lock, but that lock alone does not prove that
endpoint workers died: incomplete shutdown can precede lock release. Before
any adapter cleanup, revocation, signalling, unlink or candidate mutation,
validate the receipt, reservation, endpoint record and fixed child read-only.
Missing record proves no endpoint dispatch only when the child is also absent.
A child without a record, malformed/torn record, foreign binding, replaced
namespace/lease, non-socket child or wrong UID refuses without mutation.
`closed` requires path absence; an unexpected child is preserved and refused.

For `binding` or `bound`, an exact retained local endpoint may complete ordinary
shutdown and publish `closed` using its zero-survivor proof. Without that handle,
require the recorded controller incarnation to be dead: confirmed absence or a
positively different process-start token proves this; matching or unreadable
identity refuses. Reuse the existing boot/process identity helpers and never
signal the controller. Connection failure, pathname absence and lock availability
alone prove no worker death.

After this admission and endpoint quiescence/death proof, complete adapter
recovery first. Then reacquire the validated namespace operation lease for
endpoint cleanup. A present `bound` child must match the recorded inode. For
`binding`, death may have occurred after bind but before observation became
durable: the unchanged exclusive namespace, exact fixed child, socket type/UID
and dead-controller proof authorize removal of that child. Observe and retain
its inode during cleanup. Revalidate immediately before descriptor-rooted unlink,
prove absence and durably write `closed`. Recorded or observed identity changes
always refuse; exclusive namespace ownership does not defeat arbitrary same-UID
mutation. Only after provider and endpoint cleanup may bindings clear owned
candidates, write `abandoned` and admit a fresh ordinal. Reuse no old endpoint,
binding or submission state, and add no field to the transport receipt.

On explicit resume, normal source/input/memo guards classify the exact latest
uncommitted phased attempt, including a pending start or a failed attempt that
is being retried. If its memo committed, K3 settles without transport. Otherwise:

1. Open only the memo-derived old attempt directory through pinned no-follow
   owners, and validate its ownership receipt against the checked effect,
   started/failed memo rows and captured candidate declarations. Never trust a
   receipt-supplied arbitrary path. Apply the initial-publication absence rule
   above before resource cleanup; present malformed or ambiguous ownership
   fails closed, not as historical quarantine.
2. Finish bounded cleanup of the old private provider/endpoint resources under
   the adapter ownership protocol above: settle creation commands, revoke late
   launch, prove the owned group empty and the exact private server absent.
   Cleanup has a fresh bounded recovery
   operation budget, never a renewed live-attempt or materialization budget.
3. Discard only exact provisional candidates owned by the old absence
   preflight. Compare their bound identities when observed, use safe regular
   file reads/unlinks, and refuse symlink, path replacement or ambiguous
   ownership. Preserve the old attempt directory and evidence; no directory
   scan is an ownership proof. Mark the receipt `abandoned` after cleanup.
4. Emit `provider_attempt_interrupted_rerun` and allocate the next ordinary
   evaluated ordinal. Re-resolve current permitted C6 inputs and start a new
   task turn. The old client, endpoint, candidate, phase cursor and submit
   receipt are never reused. Each attempt still offers its task at most once.

The cleanup receipt is necessary because a tmux server can survive the
orchestrator; absence of an in-memory handle proves nothing. Phase-ledger
absence/truncation alone does not block this recovery. A durable ownership
record is not optional audit evidence and cannot be reconstructed from pane
text, stdout or phase events. Recovery must also handle an absent/torn receipt
at every pre-launch kill point without leaving an unaddressable live server;
that ordering is an implementation feasibility gate, not an assumed adapter
capability.

### Deadlines, Files And Evidence

Capture monotonic `t0` once at the start of live attempt preparation, before
request composition or transport allocation. Derive `deadline = t0 +
authored_timeout_seconds` using the required positive literal; conversion and
addition must be finite and the result strictly greater than `t0`, or fail
before resource allocation. There is no finite default to infer from provider
or per-operation adapter timeouts.

This one original absolute monotonic deadline bounds live preparation, lease waits,
command/pre-exec helpers, start, offers, validation/reset/freeze, close/join,
TERM/KILL, reap, output settlement and pre-commit preparation. Reserve cleanup
time within the remaining interval; no wrapper or parent death renews it.
Existing stricter adapter operation limits still apply: derive each operation's
deadline once, bounded by the original attempt deadline, and retain it through
that operation's creation, observation, termination, reap and output settlement.
Task delivery and every materialization correction share the original attempt
deadline; no phase restarts the budget. A fresh K4 attempt receives a fresh live
budget only after the old attempt's separately bounded recovery cleanup completes.
Preserve existing before/after deadline checks and proof-selected cleanup grammar.
The evaluator checks the same deadline immediately before its first commit;
after a valid commit, idempotent settlement is not a renewed provider action
and remains recoverable even after that deadline. No timeout makes an
incomplete cleanup proof successful.

Use `WorkspaceFiles` and existing descriptor-rooted attempt allocation for
receipt, frozen bytes and results. Candidate operations must retain equivalent
no-follow containment and identity checks across snapshot, reset, restoration
and verification. Do not substitute `Path.resolve()` followed by unguarded
reads/unlinks. Recovery validates all persisted references before using them;
copying a correctly shaped receipt to another directory is insufficient.

Retain the phase ledger and its closed diagnostic grammar for content-free
transport evidence. Its historical `publication_succeeded` event may be
emitted only after the evaluated memo commit; it is not that commit. The new
versioned attempt receipt and inline commit proof supply evaluated K2/K3
bindings; renaming the old atomic-state receipt is insufficient. Existing
Q3/Q5 snapshot/report readers remain historical. Do not reintroduce the old
compiler binding-plan/checkpoint/functional-v3 publication stack merely to
emit the old report schema. Canonical prompt identity and actual-delivery
identity are preserved through evaluated input parts, the phase trace and
inline proof; none substitutes for another authority.

### Owners And Required Changes

| Owner | Change and reused contract |
| --- | --- |
| `workflow_lisp/closed/{build,effects,artifact}.py`, WCC payload walkers, `contracts/closed_program/{check,node_walk,command_check}.py`, site/identity walkers | Carry exact policy, admit `provider_phased`, reject unsupported targets/contexts, preserve normal provider dataflow |
| `workflow/evaluated/prompts.py`, `providers.py`, `inputs.py`, `effect_inputs.py` | One-render byte cut, ordinary reads/contract rendering and provider binding reuse; no second prompt renderer |
| `workflow/provider_phased_delivery/coordinator.py`, `bindings.py` | Convert the existing coordinator to prepared-result return; delete old direct authoritative commit binding and result types |
| Existing phased `frames.py`, `protocol.py`, `endpoint.py`, `models.py`, `ledger.py`, `diagnostics.py` | Reuse transport, request idempotence, candidate/turn projections and terminal grammar; adjust only evaluated publication integration |
| New `workflow/evaluated/phased_providers.py` | Concrete coordinator bindings, safe candidates, receipt/proof, prepare/settle/reconcile and interrupted cleanup integration |
| `providers/interactive_terminal.py` | Exact durable private ownership reservation and recovery cleanup, sharing live adapter backend operations |
| `workflow/evaluated/effect_execution.py`, `runtime.py`, `memo_reducer.py`, `replay.py`, `resume_prefix.py`, invalidation/views/parallel classification | One new coordinator class, proof checks, K2/K3/K4, K8 and no accidental ordinary-provider dispatch |
| Existing CLI materialization client and provider registry/policy preparation | Reuse the argument-free client and explicit interactive capability; policy keys never leak into provider argv |
| Specs, drafting guide, design/capability indices and workflow catalog | Distinguish selected port, implemented admission and live qualification; keep old-profile refusal |

No old `WorkflowExecutor`, `StateManager`, root provider-attempt counter,
lexical checkpoint, one-member peer group, Agent allocation or second phase
execution path enters this port. Delete displaced direct-commit hooks and
rewrite their tests against prepare/settle; retaining a dead old completion
mode beside the new one is not compatibility.

### Verification And Feasibility Gates

Existing isolated protocol tests are reuse evidence, not public migration
proof. The implementation must produce fresh evidence for:

- Source and source-free closed admission, policy literal/default/pairing,
  import target ownership, readback identity, loops/helpers, and refusal of
  Agent, confined and reachable parallel contexts. Composed artifacts and
  request bytes remain unchanged.
- Exact `T1 || T2 == C` including UTF-8 and newline boundaries, output
  positions, guidance and document dependencies; successful and failed offers
  have correct separate frame/slice/turn digests. Never assert English prose.
- A public CLI run with a real interactive stand-in process: one start and
  task, invalid artifact then valid correction, invalid structured result then
  correction, complete candidate recreation, one returned typed value and one
  memo commit. Both sides of candidate validation run on every submission.
- Missing/malformed/drifted capability gives zero starts and no fallback;
  candidate preexistence/path alias/symlink/mutation/reset races fail without
  deleting unrelated files. Cap exhaustion and provider/submit/close/join
  failures preserve cleanup and publication ordering.
- External kills before/after ownership receipt, backend allocation, task/T2
  delivery, candidate freeze, pending preparation, memo commit and settlement.
  Uncommitted resume cleans old resources/candidates and starts the next
  ordinal; committed resume makes zero provider calls. Repeat with a helper
  loop to prove full activation binding and forged/cross-attempt proof refusal.
- Source/input divergence, malformed receipt/proof, replaced namespace,
  foreign process/server and missing/torn audit ledger. No false cleanup,
  unbounded waiter, arbitrary deletion, committed redispatch or old-profile
  recovery. A moved workspace cannot retarget cleanup to a foreign resource.
- Existing phased adapter/coordinator/endpoint/protocol tests, affected
  evaluated provider/memo/replay/Agent/parallel/confinement suites, collected
  new test modules, an orchestrator smoke and the required broad pytest run.

The new adapter recovery API, safe candidate bindings and public two-commit
crash behavior are unproven integration points until these gates pass. They
must not be labeled implemented merely because the old coordinator exists.

Live-provider qualification is a separate gate, outside this selected
deterministic migration. It requires at least one bounded supported-provider
interactive smoke establishing natural turn queuing and graceful shutdown.
Keep that gate open until its evidence exists; deterministic stand-ins do not
establish live-provider readiness or authorize paid qualification runs.

<a id="summary"></a>
<a id="problem-and-goals"></a>
<a id="target-223-call-policy"></a>
<a id="surface"></a>
<a id="target-and-carriage"></a>
<a id="capability-admission"></a>
<a id="deadline-aware-adapter-extension-prerequisite"></a>
<a id="canonical-byte-cut"></a>
<a id="one-rendering-two-slices"></a>
<a id="protocol-bytes-are-outside-c"></a>
<a id="principle-30-classification"></a>
<a id="phasedproviderattemptcoordinator"></a>
<a id="ownership-boundary"></a>
<a id="candidate-set-and-preparation"></a>
<a id="lifecycle"></a>
<a id="invalid-materialization"></a>
<a id="submit-receipts-and-replay"></a>
<a id="evidence-and-identity"></a>
<a id="canonical-identities-remain-canonical"></a>
<a id="q3q5-report-and-comparison-amendment"></a>
<a id="provider_prompt_phase_ledgerv1"></a>
<a id="offline-digest-partition"></a>
<a id="embedded-candidate-manifest"></a>
<a id="ledger-validation-and-authority"></a>
<a id="closed-refusal-diagnostic"></a>
<a id="total-diagnostic-projection"></a>
<a id="races-timeouts-and-failure"></a>
<a id="resume"></a>
<a id="compatibility-and-normative-impact"></a>
<a id="feasibility-prerequisite"></a>
<a id="verification-matrix"></a>
<a id="stop--revise-criteria"></a>

The original executable protocol, recovery amendments and delivery evidence are historical. The target-2.39 contract above selects the evaluated migration independently; historical records do not establish its implementation or qualification. See the [preserved record](../reports/documentation-history/workflow_lisp_phased_contract_delivery-history.md#summary).
