# Workflow Lisp Agent Sessions

## Metadata And Summary

- **Status:** first slice implemented at additive evaluated target 2.38: `design_review_execute` with designer and reviewer agents on the Claude and Codex session adapters. [PQ-1a](../reports/2026-10-14-agent-sessions-pq1a-qualification.md) records deterministic proofs and bounded real-adapter smokes; acceptance comparison (PQ-1c) has not run. The `reviewed_change` coder variant remains a future second slice.
- **Kind:** architecture decision and bounded language extension.
- **Created:** 2026-10-13.
- **Scope:** run-local agent identity, sequential native turns, and a typed result per turn.
- **Design work:** [drafting plan](../plans/2026-10-13-agent-sessions-design-plan.md).
- **Implementation selection owner:** [PQ-1](../plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md#pq-1-sequential-native-session-turns), selected by the owner on 2026-10-14: first slice `design_review_execute` with two agents (designer on the Claude session adapter, reviewer on the Codex session adapter) at target 2.38, second slice the `reviewed_change` coder variant with its turn shape selected then. PQ-1a remains the single mechanism-qualification record, now a gate inside the implementation plan; the acceptance comparison required under verification is authorized separately. The drafting plan does not authorize implementation.

An agent is one runtime-owned conversation continued by `provider-result`. Two agents allow draft →
review → revise → execute: the designer handles draft/revise, the reviewer handles review/execute,
with four typed results. The same mechanism covers sequential turns on one coder agent beside an
independent reviewer. Native creation is lazy; authors do not thread session IDs or transcripts.

The conversation is mutable and has one writer. This deliberately makes rewinding, parallel sharing,
and recovery after an uncertain delivery stricter than ordinary fresh provider calls. It does not
require a general linear type system, a background process, or immutable native snapshots.

## Context And Authority

| Contract / substrate | Owner and boundary |
| --- | --- |
| Source types, composition and effects | [Frontend specification](workflow_lisp_frontend_specification.md), §8.8, and [runtime-closures boundary](workflow_lisp_runtime_closures_boundary.md), introduction and §§9–9.1; the reference exception below requires versioned admission |
| Effect identity, memo, recovery and invalidation | [Evaluated execution](workflow_lisp_evaluated_execution.md), §§6–9; [State](../../specs/state.md) and [CLI](../../specs/cli.md) remain normative for implemented behavior |
| Provider configuration and typed results | [Providers](../../specs/providers.md), [Step IO](../../specs/io.md); existing composition, validation and result-destination owners remain authoritative |
| Immutable history and branching | [Provider Context Values](workflow_lisp_provider_context_values.md); portable capture's 2.31 executable slice is historical, with no current evaluated capture port; native immutable checkpoints remain proposed |
| Historical sequential-turn analysis | [Provider Prompt Queue](workflow_lisp_provider_prompt_queue.md); superseded for first delivery by Agent Sessions; transport/recovery analysis is retained, not a selectable surface |
| Native transport | `ProviderSessionSupport`, `ProviderSessionRequest`, `ProviderExecutor`, and `session_transport.py` in `orchestrator/providers/` |
| Observation | [Observability](../../specs/observability.md); invocation-local streams remain evidence, never continuation authority |
| Concrete consumer | [design_review_execute.orc](../../workflows/examples/design_review_execute.orc); four independent provider calls at target 2.35 |

Evaluated admission still rejects session publication/context clauses in
`orchestrator/workflow_lisp/closed/effects.py`; the bounded `agent_turn` route at 2.38 owns native
continuation. The built-in Codex template has fresh/resume commands;
`claude_unrestricted_workspace` carries `session_support` (plain `claude` templates do not).
`SessionIdentitySnapshot` reports identity and turn-boundary observations, not an expected native
position or a recoverable append receipt; agent receipts and native-store adapters supply those facts.

## Decision And Alternatives

Add one constructor, `agent`, and one opaque run-local type, `Agent`. Extend the first operand of
existing `provider-result` to accept that value. Keep prompt composition, input fills, per-call
timeouts and return types unchanged.

Artifact handoffs remain sufficient without continuity. Portable `Context` rebinds history into a
fresh conversation; proposed `Context.Native` requires an immutable checkpoint and private fork on
every use. Neither is a mutable agent. The historical single-result queue did not express the
interleaving with four typed results. Ambient `:session "planner"` aliases conceal allocation and
are not introduced.

There is no mailbox, fleet, cross-run import, automatic repair turn, snapshot, transcript export or
global registry. Existing session bridges and context calls keep their contracts.

Retire `prompt-queue` as a separate first-delivery surface. Sequential agent calls cover its
single-coder use case (several typed turns on one coder agent) through ordinary `defproc` and loops
over ordinary data with statically resolved prompts; runtime prompt-reference lists remain forbidden. No new form,
helper or macro is introduced. Each turn has its own effect identity, validated typed result
and memo commit. Those intermediate results support dataflow and branching; they do not block
retiring the queue surface. The enclosing coder consumer may return only its final `Change`,
without hiding intermediate commits inside a second journal.

Use **one native-turn protocol/coordinator implementation and adapter qualification**, owned by the
evaluated provider layer. Carry the historical queue's delivery/completion/reconciliation obligations
into that qualification, recorded only by PQ-1a for the designer/reviewer and coder consumers. E3
reuses each committed turn of a prefix; the scoped K4 refinement concerns only an uncommitted turn,
not a prefix inside one effect. A turn without a typed result contract (from `:returns` or its typed
prompt) may be reconsidered only as an evidenced future extension; it is not admitted here and no
syntax sugar is reserved. Surface retirement
selects neither implementation nor an admission target.

## Authoring And Composition

Fragment admitted at target 2.38; prompt/type declarations are those of the consumer:

```lisp
(let* ((designer (agent providers.claude :model planner_model :effort "high"))
       (reviewer (agent providers.codex :model reviewer_model :effort "high"))
       (draft (provider-result designer :prompt (draft-design :task task)))
       (feedback (provider-result reviewer
                   :prompt (review-design :task task :design draft.doc)))
       (revised (provider-result designer
                  :prompt (revise-design :task task :design draft.doc
                           :draft_path draft.doc :blocking feedback.blocking
                           :notes feedback.notes))))
  (provider-result reviewer
    :prompt (execute-design :task task :design revised.doc)))
```

`agent` accepts a statically resolved provider extern and existing model/effort options. Resolve
defaults once; pin workspace, adapter/protocol, effective tool/security policy and native storage.
Allocation is an ordinary non-coordinator effect with its own checked effect class and no provider
launch: never constant-fold, deduplicate or admit it in pure expressions. Only turns are
coordinators; K8 does not protect an unused allocation from invalidation.

An agent call accepts the ordinary single-turn prompt/input/return/timeout surface.
Model/effort/provider/workspace overrides are rejected, even if apparently equal; change the
constructor instead. The bounded form excludes context capture/binding, session publication, phased
delivery, supervision and peer groups. These combinations need their own contracts.

| Position | First-slice rule |
| --- | --- |
| Local alias, record/list field, branch selection | Permitted; copying a handle aliases the same agent, never forks it |
| Same-run `defproc` argument/return, including imported and specialized helpers | Permitted through the ordinary evaluated call path; factories may return agents |
| Sequential loop | A handle created outside is reused; construction inside creates one instance per activation, including repeated identical inputs |
| Loop state (`loop-state` fields, `loop/recur` outputs) | Refused in the first slice; an outside handle is reused lexically inside the loop body |
| Conditional creation/use | Only the selected branch allocates or invokes; joins retain the selected handle |
| Parallel boundary | No agent may enter or leave a worker, including aggregates/captures; worker-local construction/use is a proposed extension pending public parallel proof |
| Workflow/child-run boundary | No agent in public `defworkflow`/`call` signatures, run-reference transport or child-run results, even when an evaluated call stays in the same process/run |
| Provider/command data, JSON, artifacts, extern manifests | No agent serialization, coercion, prompt fill or model-authored handle |
| Pure handling | Binding, projection and forwarding of existing handles are allowed; no user-visible equality, print/string/JSON conversion, public IDs, construction/casts, native-state read or implicit capture |

Escape checks recurse through aggregate types. A called workflow may create/use agents internally;
its public signature remains transportable even when `call` stays in the same process/run. There is
no root-only exception. Runtime-owned checkpoint encoding and authorized identity inspection are
allowed.

Frontend §8.8 admits the versioned, narrow exception at 2.38 for runtime-owned `Agent` descriptors
whose provider origins are fixed by checked source. It admits no arbitrary provider refs, executable
values or closure environments; other runtime-state restrictions remain.

An explicit `Agent` formal borrows run-local authority; an alias/aggregate copy does not snapshot or
transfer it. Implicit `let-proc`/`bind-proc` capture of an agent is rejected, as is every
runtime-closure capture. The closures boundary's identity/storage/effects/replay/capability
distinctions apply: this reference is authority, not an ordinary immutable by-value capture.
Invocation must accept its statically checked origins. Existing effect analysis must conservatively
propagate those origins through helpers, branches and loops; allocation/turns count as
`uses-provider`, forwarding does not. Proving this exception is an admission obligation, not an
assumed property of the JSON value pipeline.

## Identity, Lifetime And Turn Ordering

| Identity | Meaning |
| --- | --- |
| Agent identity | Owning run identity plus constructor effect site and full activation path, using existing effect identity rules |
| Provider configuration | Immutable resolved policy of that instance; identical configuration does not merge instances |
| Native locator | Attempt-private candidate until the first typed turn commits, then the accepted conversation binding; never logical identity or author input |
| Turn identity | Existing provider effect site plus activation path, bound to the selected agent and its predecessor turn |
| Attempt | Existing attempt ordinal for a turn; neither a new agent nor permission to replay a native append |
| Process / tmux pane | Optional transport and observation; neither lifetime nor continuation authority |

Allocation commits a runtime-produced `Agent` reference containing its run binding and allocation
identity. Its checked memo representation is an agent reference descriptor, not arbitrary JSON
accepted as `Agent`: decoding requires the matching active allocation commit and pinned
configuration in this run. Allocation inputs participate in normal input digests and divergence
checks. Replay reconstructs the same instance; another helper/loop activation or run gets another
identity. A failed allocation with no native work follows ordinary retry rules without inventing a
second logical identity.

An unused agent creates no native session. The first turn uses fresh transport; later turns continue
the committed binding. Only the explicit bootstrap retry below may replace a first-turn candidate.
Authority lasts for the run, including resume; restarting the interpreter reconstructs it, not the
conversation. A new run creates new agents and may repeat workspace side effects.

The run writer owns allocation and turn publication. At most one turn per agent may be active.
Sequential evaluation determines alias use order, with no race-winner or implicit queue policy. Each
turn's resolved input includes agent/allocation identity, pinned policy, predecessor committed turn
identity and continuation receipt digest (or the initial marker), plus all ordinary
prompt/input/contract evidence. Record the predecessor as a dependency even when the next prompt
does not consume its typed result.

During replay, maintain a logical cursor reconstructed in evaluation order. An old committed turn is
checked against its historical predecessor, then advances this replay cursor. Do not compare it with
the latest native position: that conversation may already contain later committed turns. Only before
a new append must the adapter confirm that the native head matches the recorded current position;
exclusive continuation is runtime-owned (see Architecture, Compatibility And Feasibility). A
committed memo hit, settled or not, uses its inline proof as sole continuation authority, with no new
attempt-receipt-file or live-session dependency. Existing artifact-integrity checks remain.
Uncommitted reconciliation still needs its required attempt evidence. Completed runs
remain readable/replayable after native-session deletion.

Transport closure releases process resources, not agent authority. Do not delete sessions at lexical
exit or recoverable failure. Existing run retention owns local evidence; document adapter-native
retention without promising remote durability or adding garbage collection. Lost native state blocks
future turns.

## Each Turn Owns Its Current Contract

Existing owners deliver each turn's current prompt, inputs, tool bindings, schema and fresh result
destination; history never supplies current bundle paths or schemas. Commit requires native
completion and normal result/artifact validation, not merely a session ID, assistant text or process
exit zero.

The reviewer can receive “Change nothing” during review and a later request to execute the revised
document. That is a new task instruction, not a tool-policy change or proof of a read-only sandbox.
Agent configuration must support both tasks from creation; actual tool/permission changes require
another agent. The adapter must support turn-local instructions and result contracts under the
pinned native configuration, or reject before delivery. It cannot claim that appending text removes
an incompatible retained system instruction.

## Persistence, Recovery And Invalidation

The memo owns allocation and typed results. Allocation has its own ordinary non-coordinator checked
effect class; only agent turns are coordinators subject to K8 and reuse `prepare`/`settle`/`reconcile`
through the shared native-turn owner. Uncommitted receipts live in effect-attempt storage; committed inline
proofs own settled lineage. There is no second run journal, session database or agent-head file.

The receipt retains only irreducible facts: run/agent/turn/attempt binding, predecessor and
resolved-input digest, delivery intent, native locator and adapter-verifiable append/completion
position, and prepared result digest/value when valid. Its monotone updates use existing atomic
durable-write owners. Synchronize intent before dispatch. The eventual memo commit binds the
prepared proof; settlement is idempotent local bookkeeping and sends no prompt. A result file alone
is never a prepared proof or a committed result. Provider records and tmux/transcript observations
cannot replace an adapter receipt.

| Boundary / failure | Required resume behavior |
| --- | --- |
| Allocation committed; no delivery intent | First use may start a fresh native session |
| Attempt reserved but demonstrably not dispatched | Preserve its evidence; ordinary next-attempt allocation is allowed |
| Intact delivery-intent receipt, but unknown locator or append/completion outcome | Unknown locator is uncertainty, not missing receipt authority; reconcile without resending, then bootstrap before the first committed turn or refuse `agent_turn_unresolved` |
| Adapter proves no dispatch/advance and unchanged predecessor | An explicit resume may allocate the next attempt; never infer this from missing stdout or a nonzero exit |
| Completed native turn; missing/invalid typed result | Record validation failure and advance evidence; explicit bootstrap may replace a first-turn candidate, but later turns refuse `agent_turn_result_invalid` |
| Native completion and valid result; interrupted before prepared proof | Recover only from adapter-confirmed exact completion and bound intact result evidence; otherwise apply bootstrap or refuse as unresolved |
| Prepared proof durable; parent memo not committed | Revalidate its immutable binding/result and commit the same pending attempt, without another append or new attempt ordinal |
| Memo committed; settlement incomplete | Reconcile/settle from committed proof, with no native append and no comparison of an old turn to the current head |
| Committed and settled | Reuse result, even if the native session is unavailable |
| Before a new turn, session missing/advanced elsewhere/configuration incompatible | Refuse `agent_session_unavailable`, `agent_session_diverged` or `agent_policy_mismatch`; never silently create/import another conversation |
| Operator deletes an attempt directory after launch | Tampering, outside supported crash recovery: missing directory is classified as never created; a first turn may redispatch without an abandonment record, while later turns are backstopped by the native-head check |

A failed/timed-out transport may have advanced. Quiesce it through existing cleanup before
reconciliation or append; inability to prove it stopped is `agent_turn_unresolved`. Receipt
corruption/missing required evidence is `memo_inconsistent`, never permission to retry. Timeouts are
per turn attempt; reconciliation sends no model work.

While native completion/result recovery remains unresolved, keep the original `started` pending:
append neither `failed` nor `terminal`. Public run/resume exits with the diagnostic; observation
derives transport failure/awaiting reconciliation from that attempt and its receipt, not a second
status authority. Resume reconciles the pending ordinal before dispatch and may commit its recovered
proof directly. A conclusively invalid result may close as `failed`, but is then permanently
ineligible for same-attempt recovery. This preserves the reducer's requirement that `committed`
match a pending start and the existing `_append_failed_terminal_if_clear` guard: no terminal while
any start/coordinator remains pending/unsettled. No new terminal state or failed-to-committed
transition is introduced; ordinary effect failure handling remains unchanged.

**Bootstrap retry policy:** on explicit public `resume`, an agent with no committed turn first
quiesces and reconciles all available evidence. A valid prepared or receipt-backed recoverable
result wins over restarting. If none can be recovered, it may start a fresh next attempt. Preserve
all evidence and durably mark the old native candidate abandoned before a new `started`; it can
never later be adopted. Then append `failed` if that attempt is still pending, before the next
ordinal's `started`. Resume completes this ordering after a crash; an existing `failed` is not
duplicated. A failed terminal may be appended only under the ordinary no-pending guard, and the new
`started` reopens it normally. Use the same logical agent and turn, a new attempt/native candidate, and an
`agent_bootstrap_restarted` diagnostic identifying the abandoned attempt. The new binding becomes
accepted only with its typed commit. This knowingly permits first-turn at-least-once tool work,
including orphaned native sessions, with no rollback or exactly-once claim. Locator absence does not
prove no side effects. No automatic in-run retry or new permission flag is added. After any
committed turn, unresolved/invalid continuation remains blocked; native history is never reset to
repair it. E3 reuses all earlier committed turns; an enclosing workflow's uncommitted final result
does not permit discarding that prefix.

This explicitly amends evaluated §8's ordinary at-least-once retry and §9.3 K4's discard/restart
rule for agent turns. K2/K3/K5 keep result/settlement authority; checked classification, memo
validation and dispatch enforce the exception. Other classes keep their contracts. Tools/workspace
edits are not transactional.

K8/C8 already forbid superseding a committed coordinator. Under the writer lock and after base
authority/anchor checks, a suffix containing any committed agent turn therefore refuses the existing
`invalidate_coordinator_committed`. Do this before the additional receipt checks, tail repair or any
write. Otherwise inspect **all agent attempt history** started at or after the cut: unreadable
required receipts refuse `memo_inconsistent`; dispatched, advanced or uncertain attempts refuse
`invalidate_agent_session_advanced`. Include abandoned bootstrap attempts. The start-order rule
protects undeclared file dependencies, not only typed value edges. Unused
allocations/proven-undispatched attempts can follow C8. A non-agent tail after the last session turn
may still invalidate.

`memo_reducer.py::is_coordinator_class` uses the checked coordinator classes `run_ref` and
`agent_turn`; memo invalidation, settlement and readers use that classification. Replay validation
performs every journal-only guard; receipt-based guards run at write preflight and resume-time
prefix validation (R1). A `started` row does not bind its agent, so the reducer's allocation guard
requires only some active allocation; the receipt and committed proof carry the binding. Start
order subsumes the dependency rule for before-cut attempts: invalidation receipt checks cover only
at/after-cut attempts closed with non-dispatched failure codes (R7). Resume validates receipts of
pending attempts and dispatched-failure attempts. Committed turns, settled or not, use inline
proofs and never consult receipt sidecars (R8). Allocation remains a non-coordinator.
Deleting memo records cannot rewind native history. Consequently the
artifact-handoff consumer can invalidate feedback and rerun its suffix; the session variant cannot
when that suffix contains a committed turn. A new run may repeat paid design/review work and
workspace effects. This is a concrete loss of recoverability, not a blanket ban on invalidation.

## Architecture, Compatibility And Feasibility

| Work | Existing owner to extend |
| --- | --- |
| `agent`, opaque reference admission, origins and escape checks | `workflow_lisp/expressions.py`, type/effect analysis, `closed/effects.py`; `contracts/closed_program/{program,sites}.py` |
| Allocation, same-run handle carriage and replay cursor | `workflow/evaluated/{machine,values,replay,effect_inputs}.py`; reuse site/activation identity and dependency machinery |
| Native turn coordination for both agent consumers | One bounded module under `workflow/evaluated/`, dispatched by `effect_execution.py`; reuse `providers.py`, `prompts.py`, result validation and provider executor; no queue coordinator or second session manager |
| Native position, completion and reconciliation evidence | `providers/{types,session_transport,executor}.py` and the selected adapter; structural capability, never provider-name dispatch |
| Authority, receipts, C8 and views | `workflow/evaluated/{memo,memo_reducer,attempts,views}.py`; existing durable-write/path-safety owners, no second authoritative head index |
| Instance observation | `providers/observation.py::ProviderObservationManager` over existing normalized attempt streams; no daemon or control channel |

Public compiled fixtures must prove reference carriage/escape and provider-origin analysis; stable
allocation/turn replay; original-attempt recovery across both commit gaps; and whole-suffix guards
for uncommitted advances. Adjacent generic resources or session flags establish none of these
combined capabilities.

Each adapter needs real proof of lazy creation, sequential append, completion identification,
turn-local contracts, compatible policy, exact-locator loss rejection and quiescence after cancel.
Exclusive continuation is runtime-owned, not a provider
requirement: the run writer lock and the one-active-turn rule prevent orchestrator-internal
overlapping appends, and before every new append the adapter reads the native store head and
compares it with the recorded committed position of the predecessor turn, refusing
`agent_session_diverged` on mismatch before dispatch; checking a session ID is insufficient. Native
active-writer exclusion is defense in depth; an adapter without it may still qualify. The
check-then-append window against a concurrent external writer (an operator resuming the same native
session from their own shell) is a documented operator limit, not a qualification blocker: external
advancement inside that window is detected at the next turn. Reconciliation distinguishes
completion, non-delivery and uncertainty. Transport alone proves none of this.
PQ-1a is the sole record of this shared mechanism's
qualification and adapter dispositions for both consumers, including delayed delivery, helper/loop
composition, current prompt sources/input snapshots and both pending-turn commit gaps. This design
does not create a second qualification record in the drafting plan.

Native sessions live in the provider's default home (`~/.codex`, `~/.claude`); no per-run
`CODEX_HOME`/`CLAUDE_CONFIG_DIR` and no credential provisioning are introduced. Locators are
provider UUIDs; the pre-append position check above detects external advancement. A run-private
native home is a possible later hardening, not required here.
The adapters honour `CODEX_HOME`/`CLAUDE_CONFIG_DIR` only when already present in the orchestrator's
environment; the orchestrator never sets them (D7).

Admission is additive at evaluated target 2.38, selected by the owner on 2026-10-14; the
2.35/2.36/2.37 contracts are unchanged and the Phase 5 (2.37) gates stay independent. Calls
with provider externs retain existing behavior and cost. No old run is relabeled/backfilled. Opt-in
consumers replace repeated provider configuration with construction. PQ-1 records the selection and
owns the consumer slices; `prompt-queue` is superseded for first
delivery, with no separate implementation lane.

## Instance Observation In Tmux

Provide one read-only logical view per agent instance (designer and reviewer for the two-agent
consumer, one coder view for the coder variant), aggregating that agent's normalized attempt
streams across all of its turns in turn order with turn/attempt boundaries and idle states. The
view follows the instance, not the call: invoking the same agent again continues its existing view
and never opens a second one, while each ordinary `provider-result` call keeps its own pane. Reuse
`ProviderObservationManager`; no `.orc` option, daemon, interactive instruction input or provider
keystroke injection is introduced. Attach is read-only. Reconstruction on runtime resume may
allocate different panes/socket targets: stable logical identity does not imply a stable physical
tmux target. Show current attach coordinates transiently; never persist them in `Agent`,
memo/checkpoints or stable status. Existing durable streams may feed a rebuilt view but never
authorize a turn, reconcile it or launch a provider.

The implemented observability amendment keeps ordinary calls under the current
one-invocation/one-pane contract, while agent instance views are derived above invocation-local
evidence. Observation failures, missing streams, attach/detach and teardown remain best-effort and
cannot affect execution. Normalized output provides no promise of complete tool or hidden-reasoning
visibility; provider transport and typed results remain the authorities.

## Verification, Risks And Handoff

Public `compile` → `run` → `resume` tests must execute the actual evaluated owners with
deterministic adapters, plus a real-provider smoke per advertised adapter. Exercise the maintained
consumer's A1/B1/A2/B2 flow: two distinct native identities, four valid typed results, preserved
predecessor lineage, updated result destinations and exactly four requested turns in the clean run.
Also exercise the opt-in coder variant of `reviewed_change.orc`: sequential coder turns on one
agent, one committed typed result per turn and the existing final `Change` interface, with the turn
shape selected when that slice is selected. Keep its independent outer reviewer/control flow and
explicitly select its model in the future variant. PQ-1a records mechanism qualification once for both consumers; these are distinct
usage checks of that mechanism. Use receipts and validated dataflow, not literal prompt text, as assertions.

Cover factory calls with equal inputs, branch-selected aliases, sequential reuse and per-iteration
construction; nested aggregate escape and parallel sharing must fail before dispatch. Independent
worker-local agents require public parallel integration proof before that placement is admitted.
Kill before/after intent, native completion, proof persistence, memo commit and settlement. Include
invalid output after native success, fresh-session orphan, external advancement, session loss,
old-turn replay after later commits, and clean completed replay after all native sessions disappear.
Invalidation must refuse an upstream non-agent commit whose suffix or outstanding attempt affects
advanced agent state, without modifying any authority. Unchanged ordinary provider and run-reference
recovery/invalidation remain regression controls. In particular, allocate A → command X writes a
file → turn T on A reads that file and advances natively without committing: invalidating X must
refuse `invalidate_agent_session_advanced` before tail repair or any authority write, even though A
predates X and T has no declared value dependency on X.

After committed designer A1, fail reviewer B1 with an unknown locator or invalid first result.
Explicit `resume` must keep A1, record abandonment and start only a fresh B1 attempt; a valid
recoverable B1 proof must instead commit without dispatch. A2/B2 failures cannot bootstrap. Corrupt
receipts/quiescence failure must refuse. Settled memo replay must not require old receipt sidecars.
For a transport timeout followed by adapter-confirmed completion and intact valid output, assert
the stop leaves the original start pending without `failed`/`terminal`; public resume commits that
same ordinal with zero redispatch. Kill between abandonment, failure closure and the next start to
prove old candidates cannot be adopted and terminal/retry ordering remains valid.
Show two logical tmux views across all four turns, attach/detach and runtime crash/ resume, with
changed physical targets permitted and zero observation-triggered side effects or redispatch. Retain
ordinary observation regressions.

Compare this consumer with its existing artifact handoff for retained useful context, repeated
investigation, friction, elapsed time and total provider usage, including first-turn repeats and
inability to invalidate feedback after session commits. Acceptance requires both clean and
failed/resumed comparison evidence plus an explicit judgment that retained context justifies lost
suffix recoverability and any repeated paid work; a clean success alone is insufficient. Continuity
promises neither lower cost nor preserved hidden reasoning. Long histories can grow, retain obsolete
instructions and contaminate later judgment; reviewer/implementer continuity is not an independent
final review. Recorded session locators use existing secret/path protections and private attempt
storage; native history stays in the provider default home (see Architecture, Compatibility And
Feasibility). Source-free inspection shows logical identities, typed results and continuation status
without opening a session or exposing its transcript.

The implementation plans and qualification record own the reviewed delivery and evidence for
frontend/closed-program contracts, `specs/{providers,io,state,cli,versioning,observability}.md`,
adapter documentation, the guide/catalog and consumer. Handoff: reference admission, qualified
transport, shared turn recovery, C8/readers/observation, then public acceptance. No new framework or
wholesale coordinator rewrite is authorized. Revise the design if safe continuation requires
unverifiable native state, silent replay, stronger snapshot semantics, or a second authority system.

## Open Questions Before Selection

Resolved or re-scoped by the owner selection of 2026-10-14. Rows marked as in-plan gates stay open
until proved under PQ-1a; the selection does not satisfy them. Their current evidence disposition is
recorded in the [qualification record](../reports/2026-10-14-agent-sessions-pq1a-qualification.md),
including real-provider limits. The table preserves the selection-time questions; it does not mark
the separate PQ-1c comparison or second consumer slice complete.

| Question / responsible component | Impact | Disposition at selection (2026-10-14) |
| --- | --- | --- |
| Can each provider adapter prevent internal append races, detect external divergence from the native store before append, and prove completion identification, locator loss rejection and quiescence? / provider transport owner | Determines supported adapters and diagnosable recovery limits | Re-scoped: exclusivity is runtime-owned and native active-writer exclusion is defense in depth. Native CLI probe (17 attempts): completion identification without stdout, exact-locator loss rejection and quiescence after cancel observed for both CLIs; Codex active-writer exclusion observed, its atomic expected-position continuation unqualified; Claude exclusive continuation not observed; exact interrupted-turn recovery inconclusive. Remains an in-plan gate for both admitted adapters, Claude and Codex, in the first slice |
| Do reference/origin analysis, shared coordination and crash-window proofs meet the proposed contracts? / frontend and evaluated-runtime owners | Determines whether this bounded reference and recovery exception are implementable | Remains an in-plan gate: deterministic-adapter proofs at target 2.38 in the first slice, as mechanism proofs independent of consumer |
| Does shared mechanism evidence support the named consumer slice? / PQ-1a owner | The single qualification record controls supported adapters and bounded scope; the drafting plan is not selection authority | Selected before that evidence; remains an in-plan gate under PQ-1a. First slice `design_review_execute` with two agents (designer on Claude, reviewer on Codex), second slice the `reviewed_change` coder variant with its turn shape selected then. PQ-1a stays the single record, now a gate inside the implementation plan rather than a precondition for writing it; the acceptance comparison against the artifact-handoff baseline is authorized separately |
