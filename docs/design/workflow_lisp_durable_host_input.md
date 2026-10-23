# Durable Host Input On Evaluated Workflows

- **Kind:** current feature architecture and component contract
- **Authority:** evaluated execution, retained frontend types and the normative
  state, CLI, IO, security and observability specifications
- **Target:** DSL 2.40 on the evaluated execution profile
- **Companion:** [Python authoring frontend](workflow_python_frontend.md)

This component contract is integrated with the [evaluated baseline](workflow_lisp_evaluated_execution.md#95-durable-host-requests-at-target-240)
and normative [DSL](../../specs/dsl.md#evaluated-durable-host-input-target-240),
[state](../../specs/state.md#evaluated-durable-host-input-target-240) and
[CLI](../../specs/cli.md#evaluated-host-input-target-240). Implementation selection,
progress and verification evidence belong in the [delivery plan](../plans/2026-10-22-durable-host-input-plan.md).
This document defines durable behavior and boundaries; it does not qualify a
release or select provider expenditure.

## Outcome And Scope

A workflow asks for a typed decision, durably stops, and exits without running
its continuation. A host answers or cancels the exact request. Ordinary resume
replays the validated reply and continues the workflow. Expiration is a third
typed outcome, committed by resume. Lisp `request-input` and Python `ask` share
this one effect, contract and lifecycle.

The design adds one evaluated effect class, `request_input`, and one public
host API. It reuses effect identity, attempt allocation, append-only memo,
writer locks, prompt rendering, typed transport validation, report projections
and the monitor. It does not restore the retired executor, use `state.json` as
authority, keep a Python stack alive, poll a provider, or add an approval service.

One run has at most one outstanding host request. Sequential questions in
procedures and loops are supported. Requests under `par-map`, including
transitive calls, are rejected. Parallel work before or after a serial request
keeps its existing contract; no progressive execution crosses a pending request.
Multiple simultaneously pending questions would require revisiting this
restriction and the run-level suspension projection.

## Owners And Existing Boundaries

Read [the documentation index](../index.md), [capability matrix](../capability_status_matrix.md),
[frontend contract](workflow_lisp_frontend_specification.md),
[evaluated execution](workflow_lisp_evaluated_execution.md),
[language principles](workflow_language_design_principles.md) and the normative
[state](../../specs/state.md), [CLI](../../specs/cli.md),
[IO](../../specs/io.md) and [security](../../specs/security.md) contracts together.
Historical `HumanReply` data does not admit an evaluated request.

| Boundary | Existing owner and required extension |
| --- | --- |
| Authored form and inferred effect | `workflow_lisp/expressions.py`, `typecheck_effects.py`, `effects.py`; extend retained `RequestInputExpr` and subject-free `HostInputEffect` |
| Checked closed form | `workflow_lisp/closed/effects.py`, `closed/build.py`, `contracts/closed_program/check.py`; replace the located unsupported-effect refusal only at 2.40 |
| Sites and dynamic identity | `contracts/closed_program/sites.py`, `workflow/evaluated/machine.py`; ordinary procedure activation, local site and loop indices |
| Input preparation and replay | `workflow/evaluated/effect_inputs.py`, `replay.py`, `resume_prefix.py`; integrate request inputs and recovery with existing prefix validation |
| Attempt and publication | `workflow/evaluated/runtime.py`, `attempts.py`, `memo.py`, `memo_reducer.py`; retain exact existing row fields and extend the strict reducer |
| Host mutation | New public `orchestrator.host_input`; runtime-owned request helpers validate and publish under `memo_writer_lock` and retained `WorkspaceFiles` |
| CLI | `cli/main.py`, `cli/commands/human_input.py`; thin clients of the public API, with historical read routing retained |
| Reports/dashboard | `workflow/evaluated/views.py`, `dashboard/*`, `cli/commands/report.py`; derive pending request and attribution from checked memo |
| Monitor | `monitor/models.py`, `classifier.py`, `ledger.py`, `messages.py`; one suspension notification per request using existing delivery |

The reducer admits `suspended` only for checked target-2.40 host requests. An
ordinary commit closes its pending start without a coordinator settlement.
Host input uses that ordinary commit rule: there is no separate
external system to reconcile after publishing the reply, and no `settled` row.
The existing coordinator `proof` and `settled.by` fields retain their meaning.

## Language And Types

```lisp
(import std/host :only (HostReply))
(defenum Approval APPROVED DENIED)

(defproc approve ((question String)) -> HostReply[Approval]
  (request-input question :returns Approval :timeout-sec 86400))
```

The standard module exports an ordinary first-order generic union:

```lisp
(defunion HostReply :forall (A)
  (ANSWERED (value A) (by String))
  (CANCELLED (by String))
  (EXPIRED))
```

`request-input` has this grammar at 2.40:

```lisp
(request-input question
  :returns AnswerType
  :timeout-sec positive-integer-expression
  :show (path-expression ...))
```

`:returns` is required. `:timeout-sec` and `:show` are optional, each at most
once. The question is either a `String` expression or an ordinary fully applied
`defprompt` with its existing typed `:fills`/`:doc` semantics. Prompt applications
are admitted directly at this new question position; they do not become general
runtime prompt values. A declared prompt return contract, if present, must agree
with `:returns`; it describes the answer type, not the `HostReply` wrapper.
The host question does not append provider-specific output-file instructions.

```lisp
(defprompt approval-question
  (:fills (summary :text) (report :doc ReportPath)) -> Approval
  "Approve this recovery? {summary}")

(request-input (approval-question :summary diagnosis.summary :report diagnosis.report)
  :returns Approval
  :timeout-sec 86400
  :show (v.evidence bundle.logs))
```

The parentheses after `:show` are a syntactic list of path expressions, like
other keyword operand lists. In this example `v.evidence` and `bundle.logs` are
two field projections. There is no `v.evidence` callable, new view language or
`materialize-view` effect. Each expression must have an admitted typed `relpath`
type; plain strings and arbitrary JSON objects are refused statically. The
snapshot reader requires a regular file and refuses directories at runtime;
the existing path type does not statically distinguish files from directories. Empty
`:show ()` means no evidence. The normal workspace path and no-follow file
rules govern resolution and hashing. Source order is retained.

Answer types are `String`, enums, or closed unions whose complete instantiated
payload is admitted by the existing structured provider-transport type rules.
This admits a free-text question without forcing an artificial one-field record.
It does not admit `Any`, open unions, handles, procedure references, runtime
closures, generic type variables or other types excluded by that transport.
The host passes the JSON encoding of `A`, not a provider output file or the
`HostReply` envelope. Both the answer and the complete wrapper are validated
before publication. The runtime constructs `by`; the caller cannot insert a
different principal by submitting a forged wrapper.

The effect summary contains the existing subject-free `(host-input)` effect.
At targets 2.39 and later, omission infers procedure effects; an explicit
`:effects` declaration is a checked restriction. Thus `:effects ((host-input))`
is optional, and `:effects ()` refuses a procedure that asks directly or
transitively. Imports retain their defining source's target rules. Target 2.40
must preserve capabilities already admitted at 2.39, including phased providers;
exact comparisons with `"2.39"` must not accidentally exclude the new target.

The checker rejects host input transitively in `par-map`, pure functions and
every child program invoked by `run-ref`, including confined children. Child
admission refuses before creating or launching the child. Ordinary `defproc`
and workflow calls in the same run/memo remain supported. Child runs have
independent locks and require completed results today; propagating suspension
across a parent/child boundary is outside this contract. Checked-program
admission independently enforces these restrictions.

## Checked Form And Result Provenance

The new checked `perform` uses `class: request_input`, its normal assigned site,
question operands, optional timeout operand, ordered show operands, and complete
closed descriptors for `A` and `HostReply[A]`. These descriptors and any required
transport contract carry the same constraints as the frontend's instantiated
types. A type name or a list of variant tags alone is insufficient.

The request preparation path reuses shared prompt rendering and content snapshot
validation without routing through a provider adapter. It produces one semantic
input-parts map, the complete rendered question, and presentation evidence.
No provider is selected or called by this effect.

On load and replay, the checked node, stored full answer/reply contracts,
contract digests, result digest and inline value must agree. Restore the value
with `coerce_evaluated_value` using the full reply descriptor, the request's
dependencies and its committed effect identity. Refinement and generic union
provenance must survive restore so ordinary `match` exposes only fields from
the selected variant. Forged `ANSWERED` values, unknown fields, contract changes
and malformed expiration provenance fail closed before the continuation.
The existing memo reducer receives only a site-class table: it validates row
shape and transitions, not nominal type authority. A shared checked request
validator must bind its projection back to `RunAuthority.program` and validate
the full contracts/value on every production read, replay and mutation.
Trusting the memo's own claimed contract would be circular. Read-only pending,
report and dashboard paths run this validator without repairing tails or
publishing views. `discover_prefix` still stops at an uncommitted effect frontier;
a suspended frontier is neither a failed evaluation nor a pure halt.

## Identity, Inputs And Time

Dynamic effect identity uses the evaluated machine's existing owner/site,
procedure activation and loop-index construction. It is not the question text.
Two loop visits or procedure activations therefore cannot settle one another.
The attempt uses the existing monotonically allocated ordinal.

`request_id` is a versioned canonical SHA-256 identity binding the immutable run
identity, `program_digest`, dynamic effect identity and attempt ordinal. The
run binding includes `run_id` and the immutable run-header identity digest, so
requests in separately created runs cannot be substituted even when authors
choose the same display run name in separate workspaces. The header digest is
the canonical SHA-256 of the complete validated immutable run header; no new
random-ID store is needed. Moving/copying a run does not mint new requests or authorize violating
the run root's existing identity constraints. A complete copy of the same run
authority remains the same run, rather than a separately authenticated tenancy.

Semantic input parts bind the rendered question, prompt source and `:doc` bytes,
answer/reply contracts, timeout duration or absence, ordered evidence paths and
their declared path contracts, and ordinary operand dependencies. Neither
`time.time()` nor a recomputed deadline enters that semantic input digest.

At the first durable `started` append, choose `created_at` from the runtime
clock and set `deadline = created_at + timeout_sec`, or `null` when omitted.
The duration must be an exact positive integer, never boolean or floating
point, and the absolute deadline must be finite. The stored start time and
deadline are immutable for that attempt. Recovery of the same attempt reuses
both. A newly invalidated/reissued request gets a new ordinal and deadline.
Wall-clock adjustments can affect when a deadline is observed; monotonic clocks
cannot supply a durable cross-process absolute deadline.

## Memo Lifecycle

All rows retain the existing schema's required identity, input digest/parts,
implementation evidence, result path, dependencies and time fields where
applicable. The following are extensions, not replacement abridged schemas.

| Transition | Authoritative fields and behavior |
| --- | --- |
| Absent → `started` | Reserve normal ordinal/path; add `host_request` containing the complete immutable request payload. `implementation_files` remains the normal empty map for this effect. |
| `started` → `suspended` | Row contains identity, attempt and `request_id`; it refers to that start's payload. The reducer admits it only for `request_input`, once, with no other outstanding request. |
| `suspended` → `committed` | Normal commit carries validated `HostReply[A]` inline and `host_reply` settlement provenance. Input fields/path match the start exactly. |
| Suspended → invalidated | Existing suffix invalidation removes pending state together with affected active commits; the old request ID becomes stale. |

`host_request` contains a schema version, request ID, rendered question and its
digest, complete answer and reply contracts and their digests, ordered show
rows, created time, deadline, and the dependencies needed for external commit
validation. Each show row contains the logical workspace-relative file path,
path contract and content SHA-256 observed when the request was created. The
request's canonical payload digest binds those exact bytes and timestamps.
This frozen payload digest is distinct from the repeatable semantic input
digest; recomputing a new clock value must never cause replay divergence.

`host_reply` contains the request ID, origin (`host` or `runtime`), optional
opaque attestation, the explicit `accept_changed_evidence` boolean even when
there are no differences, and any accepted evidence differences. A host
answer/cancel has `origin: host`; its nonempty principal is the `by` field in
the typed value. Expiration has `origin: runtime`, reason `deadline`, and no
host principal or attestation. Commit time is the runtime's observation time.
The reducer rejects missing/extra provenance appropriate to the selected
variant. `result_digest` hashes the canonical inline reply, not a view file.

The pending-request projection is derived from starts/suspensions/invalidation,
not persisted as a second registry. While suspended, the evaluator appends no
terminal and returns an ordinary suspension exit code of `0`. Its writer lock
is released when the process exits. A subsequent run/resume without a reply
returns the same suspension and request ID, without another ordinal, suspension
row, or provider invocation.

An answer/cancel commit settles only the question; it does not execute the
continuation or append a workflow terminal. Once its writer lock is released,
the existing nonterminal/no-writer projection is `interrupted`, meaning resume
is required. A request commit is already complete and never needs a coordinator
`settled` row. Ordinary resume is the only continuation door.

## Recovery And Publication Order

The entire immutable payload is in `started` because attempt creation and view
publication happen after that append. This is the recovery anchor for a crash
before `suspended`; a file written between two memo rows cannot be authority.

Resume first performs its normal source/program/inputs and committed-prefix
preflight, then validates the pending request against the reached effect. It
repairs a torn tail only under the writer lock after successful preflight.

| Surviving boundary | Resume/host behavior |
| --- | --- |
| No complete start | Nothing was requested; normal execution may create the first attempt. |
| Complete start; missing/partial attempt views; no suspension | Resume recreates checked views from the start, appends the one suspension, then returns suspended or expires it. It preserves the ordinal, ID and deadline. Host settlement refuses `host_input_not_suspended` until resume finishes recovery. |
| Suspension durable; view missing/stale | Memo supplies pending data. Read APIs remain read-only; resume or the next successful writer can repair views. |
| Reply append torn | No complete commit exists; normal writer recovery discards only the validated torn tail and retries settlement. |
| Commit durable; views or process completion fail | Reply is already authoritative. An identical duplicate returns it. Resume consumes it without asking again. |

For an active suspension, resume compares its clock to the frozen deadline
after prefix validation. At or after the deadline it appends the complete
`EXPIRED` reply with runtime provenance and immediately continues from that
value. Before the deadline, or without a deadline, it exits suspended. Read-only
inspection may display `deadline_elapsed`, but never expires a request.

Answer, cancel, invalidation, expiration and resume serialize through the same
run writer lock. The external API rereads checked authority and memo after
acquiring that lock and checks the deadline immediately before its commit.
At or after the deadline it refuses `host_input_deadline_elapsed` without
writing; resume owns expiration. The acceptance instant is the runtime timestamp
sampled after validation and immediately before appending under the lock, not
the later completion of fsync. A valid host commit accepted before the deadline wins
and can never be overwritten by later expiration. If expiration wins the lock
and commits first, a late answer is a conflicting settlement. No caller-supplied
timestamp can backdate a reply.

## Evidence Drift And Invalidation

The rendered prompt and its `:doc` reads are semantic inputs governed by the
ordinary content-bound replay rules. Source/manifest changes follow ordinary
rebuild refusal (`resume_program_changed` or compile error); changed runtime
prompt inputs refuse with
`effect_input_diverged`; `accept_changed_evidence` cannot waive those rules or
any changed producer's own replay obligations.
Ordinary input contracts also remain in force: a missing workflow input marked
`:must-exist true` fails preflight even when the same path appears in `:show`
and the host accepts changed presentation evidence.

`:show` file bytes are a frozen presentation snapshot: its paths/contracts are
semantic inputs, while its original content hashes belong to `host_request`.
External settlement reads and hashes the current files under the normal safe
workspace reader. A changed, absent or unreadable show file refuses by default
with `shown_evidence_changed`. A path-safety violation, such as traversal
or a forbidden link, remains an unconditional refusal.

With `accept_changed_evidence=True`, a host may explicitly accept changed,
missing or unreadable presentation evidence. The commit records each original
digest, observed current digest or concrete absence/read-error classification,
and the host's override. It does not rewrite the original request or pretend
that the old bytes are the new bytes. The override is checked again against
the observed snapshot immediately before publication where practical; the
contract records bytes actually read, not a promise that an external writer
cannot subsequently change them.

After a reply commits, replay verifies the frozen request and accepted snapshot
from the memo; it does not require current show-only bytes to match either
snapshot. Otherwise a knowingly accepted drift would make resume inevitably
fail. Changes to the same file when also bound through `:doc`, other operands
or an earlier effect remain subject to those independent semantic checks.
This narrowly defined presentation rule is the only replay exception here.

Existing `invalidate RUN_ID IDENTITY` continues to anchor an active
commit. Its suffix includes later pending starts/suspensions, including a host
request; clearing that suffix makes all those request IDs stale. An answered
request is an ordinary commit and may itself anchor invalidation, subject to
the existing guards for other effects in the suffix. There is no new direct
pending-request invalidation command: cancel provides a typed outcome; changing
the question requires invalidating an earlier committed dependency or starting
a new run. Invalidating a prefix must never leave a pending request eligible
for settlement after its dependencies were removed.

## Public Host API And CLI

```python
from orchestrator.host_input import pending, answer, cancel

request = pending(run_root)  # mapping or None; read-only
reply = answer(run_root, request_id, value="APPROVED", by="alice",
               attestation=None, accept_changed_evidence=False, workspace=None)
reply = cancel(run_root, request_id, by="alice",
               attestation=None, accept_changed_evidence=False, workspace=None)
```

Both mutators require exact `request_id` and nonempty, non-whitespace, NUL-free
`by`. `attestation` is an optional opaque string retained without interpretation.
Local writer access authorizes mutation; a supplied principal/attestation is
attribution, not independently verified authentication. An authentication or
remote approval service may wrap this API but is not part of it.

The API validates immutable run authority, target/profile, checked site and full
contracts, active request lineage, finite JSON value, evidence and deadline
under `memo_writer_lock`. A new settlement runs the side-effect-free ordinary
resume rebuild/program/input and reached-prefix preflight before appending; it
must not settle a request whose semantic dependencies already diverged. Reuse
that preflight owner rather than creating weaker host-specific source checks.
An identical retry of an already committed settlement reads its recorded
identity/value and does not require changed source or evidence to be usable. It uses descriptor-relative `WorkspaceFiles` for run
and workspace reads/writes. A held writer returns `memo_busy`; it does not wait
inside an interactive workflow or acquire a different host-input lock.

`workspace` defaults to the current working directory. Mutators verify its
run-relative result root against the immutable header by the same rule as
ordinary resume; they never infer a workspace by stripping `.orchestrate/runs`
from `run_root`. This supports custom state directories without adding persisted
workspace authority. `pending` needs only run authority.

An identical retry against any noninvalidated committed request in this run
succeeds without another row, including while a later question is pending and
after the original deadline or workflow completion. Identity
includes answer-versus-cancel, canonical typed value, exact principal,
attestation and override choice. Its equality check uses the stored settlement,
not newly read evidence or a new timestamp. A different reply is
`request_already_settled`. An unknown, cross-run or invalidated ID
is `host_input_stale`. Type/shape failures are `host_input_answer_invalid` and
leave the request suspended. Invalid requests never repair a tail, update a
view, or append a failed terminal as a side effect of validation failure.

```sh
orchestrator input get RUN_ID
orchestrator input answer RUN_ID REQUEST_ID --value '"APPROVED"' --by alice
orchestrator input cancel RUN_ID REQUEST_ID --by alice
orchestrator resume RUN_ID
```

Answer/cancel also accept `--attestation STRING` and
`--accept-changed-evidence`; state-directory selection follows existing CLI
conventions. `--value` is strict JSON, rejecting duplicate keys and non-finite
numbers; there is no untyped text-to-enum coercion. CLI output is JSON from the
same API, and refusals use the existing command exit `2`. `input get` remains
the historical read-compatible door, dispatching evaluated reads to `pending`
and retired data to the retained reader. Historical answer/cancel remains
`workflow_execution_profile_retired`; old `--text` does not become a second
typed settlement interface.

## Evidence Views And Operations

Use the existing attempt directory:

```text
effects/<sha256(effect-identity)>/attempt-<ordinal>/
  request.prompt.txt
  request.json
  reply.json
```

These files are rebuildable evidence views. The ordinary memo `result_path`
remains `.../result.json` as the conventional locator for existing effect tooling;
this inline-only effect does not materialize a redundant result file. `reply.json`
is the requested human-readable result evidence. Neither locator nor evidence
file is read to decide host settlement or restore the typed reply. Reuse existing safe atomic publication and retained
root checks; no separate request journal, receipts, status file or service exists.

Reports and the read-only dashboard expose `suspended` before the generic
no-writer/interrupted case, the exact request ID, question, answer contract,
evidence paths/digests, deadline and reply attribution. They distinguish a
pending request from an expired-in-clock-but-uncommitted one. The dashboard
does not offer answer/cancel endpoints in this design. Malformed evaluated
authority fails closed instead of falling back to legacy state readers.
A durable suspension projects `status: suspended` even while the publishing
writer still holds its lock: this is an intentional stop, not a process-liveness
inference. Thus the persisted view is already correct when the process releases
the lock. No post-unlock mutation is needed.

The monitor gains `SUSPENDED` classification using the authoritative evaluated
view. Its existing delivery configuration and emailer remain unchanged; no
notification daemon is introduced. Suspension email includes request ID,
deadline and the inspection/answer/resume command shapes, with the existing
privacy limits on previews. Do not embed evidence-file bodies or attestation
strings in email. The existing ledger key is extended for suspension events
with `request_id`, so two sequential requests notify independently and repeated
scans of one request do not. Other event keys and prior ledger entries retain
their meaning. A pending request is never classified as crashed merely because
its process deliberately released the lock. Notification delivery never mutates
or settles the run; tests use a recording email transport, never real mail.

## Compatibility And Required Documentation

Target 2.40 is added at every source/import/checked-program admission owner,
including `contracts/closed_program/targets.py` and `workflow/run_ref/config.py`.
Do not change the historical `HumanReply = ANSWERED(text String) | CANCELLED`
contract or reinterpret its stored state. Old targets continue refusing new
host-input execution. New generic `HostReply` belongs to `std/host`; Python
reexports that same descriptor rather than emitting a second nominal type.

DSL, state, CLI, IO, observability, security and versioning specs own their
respective normative rules; the evaluated and frontend baselines incorporate
these effect/memo/type rules. Capability routing, the drafting/library guides,
monitor/dashboard guidance and the workflow catalog describe current use and
prerequisites. Implementation chronology and evidence belong in the plan/report.
The [maintained diagnose/recover example](../../workflows/examples/durable_host_input/README.md)
identifies its provider and command manifests and supplies stub setup; the
[Lisp](../lisp_workflow_drafting_guide.md#durable-host-input) and
[Python](../python_workflow_drafting_guide.md) guides provide provider-free recipes.

## Verification And Acceptance

No provider calls, judge calls or live notifications are required or selected.
Deterministic scripted provider executors test the real public compile/run,
memo, host API, CLI and resume path. They replace only external provider work,
not the evaluator, request lifecycle, validation or storage.

| Contract | Required evidence |
| --- | --- |
| Typing/admission | String, enum and transported closed union answers; ordinary generic `HostReply` import/match; full constraints retained; optional effects inference; old target, invalid type and transitive `par-map`/child-run refusals; 2.39 features retained at 2.40 |
| Identity | Same site in different loop visits/procedure activations produces different IDs; same logical request replay retains ID; cross-run ID rejected |
| Durability | Faults after start, attempt creation, suspension, commit and view publication; torn rows; repeated resume without reply; deleted view files; no duplicate provider/command dispatch |
| Settlement | Invalid/extra/missing JSON fields, duplicate keys, empty principal, forged wrapper, identical duplicate (including an earlier committed question while a later one waits), conflicting duplicate, stale invalidated ID, custom state-directory workspace binding, active lock contention |
| Expiration | No deadline, fixed deadline across crash/resume, exact deadline boundary, answer-before-expiry, late-answer refusal, expiry-wins race, runtime-only provenance |
| Evidence | Changed/missing show bytes refuse by default; override persists both snapshots and allows resume; :doc and producer divergence still refuse; unsafe paths never waived |
| Invalidation | Earlier commit invalidation retires later pending request; invalidated answered request gets a new ordinal; existing coordinator/session guards preserved |
| Observation | Pending/report/dashboard values derive from memo; missing/stale views harmless; suspension distinguished from interruption; two sequential monitor notifications and one notification for repeated scans |
| Python parity | Native `ask`, lazy typed branches and procs emit the same effect/contract; generated source survives source-module edits/removal on resume; source attribution survives diagnostics |

The end-to-end acceptance workflow diagnoses a fault with a stub provider,
verifies that diagnosis with a command, asks for `Approval` with the verified
evidence, and runs the repair command only for
`ANSWERED(APPROVED, by)`. `ANSWERED(DENIED, by)`, `CANCELLED(by)` and `EXPIRED`
all invoke the workflow's explicit escalation path. Run it from both Lisp and
native Python authoring, inspect pending via CLI/API, settle via the other door,
resume, and resume again. Assert exact command/provider call counts and final
typed outcomes, plus source/effect/request attribution in reports. Do not test
literal question wording.

Use narrow tests first, collect new/renamed test modules, and include this public
orchestrator smoke before broader pytest runs. Required broad runs use the
repository's tmux and `pytest -q -n 16 --dist=worksteal` rules. An independent
review must inspect both implementation and fault-boundary evidence. Revise the
design if implementation needs a second execution authority, provider polling,
parallel pending requests, weakened replay validation or a retired executor.
