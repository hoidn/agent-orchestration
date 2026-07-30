# Workflow Lisp LSP Diagnostic Lifecycle And Compile Progress

- **Status:** implemented, incorporated, and complete at
  `251d9d53674e863fddae4535ea4f7022914287cd`, tree
  `e2417d395cbcabe9adaffb136759ebff3d42b677`
- **Kind:** developer-tooling architecture amendment
- **Owner:** Workflow Lisp language server
- **Reviewers:** independent specification review
  `L4_DESIGN_SPEC_APPROVED`, then independent quality review
  `L4_DESIGN_QUALITY_APPROVED`; Task 1
  `L4_TASK1_SPEC_APPROVED` then `L4_TASK1_QUALITY_APPROVED`; Task 2
  `L4_TASK2_SPEC_APPROVED` then `L4_TASK2_QUALITY_APPROVED`; Task 3
  `L4_TASK3_SPEC_APPROVED` then `L4_TASK3_QUALITY_APPROVED`. Task 4 closure
  diff `c41e2e756f1d0c6bc27bbd9a8b8bbbfc57c59fc121b0bd46dc548709c286b990`
  received `L4_TASK4_SPEC_APPROVED` then `L4_TASK4_QUALITY_APPROVED` before
  commit `1f64f153`, tree `7790ee0e`. That exact tree received
  `L4_FINAL_SPEC_APPROVED`; final quality returned `CHANGES_REQUIRED` solely
  for stale review-status metadata. The corrected routing/status diff
  `29e0bc01037058f0c29dac15c0d461798a5e47a836fe8b3e8336beb937410951`
  landed at `251d9d53674e863fddae4535ea4f7022914287cd`, tree
  `e2417d395cbcabe9adaffb136759ebff3d42b677`, then passed a 357-test focused
  control. External closure-record SHA-256
  `94b47f87035549191d698c63bf93b706740791d1e3ec45a29750e662fa4bf804`
  records ordered `L4_FINAL_SPEC_APPROVED` then
  `L4_FINAL_QUALITY_APPROVED`; the prior rejection is superseded history
- **Created:** 2026-07-28
- **Last material update:** 2026-07-28
- **Related docs / plans:**
  - `docs/design/workflow_lisp_language_server.md`
  - `docs/design/workflow_language_design_principles.md`
  - `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`
  - `docs/reports/2026-07-28-workflow-lisp-l4-editor-lifecycle-probe.md`
- **Implementation record:** current-only diagnostic publication at
  `11629551`; transport-local compile progress at `0d5f7009`; repository-real
  Neovim acceptance in
  `tests/test_workflow_lisp_lsp_neovim_e2e.py`

## Summary

L4 makes diagnostic freshness visible by suppressing non-current
contributions from the publication view while retaining their exact internal
ownership. A current successful or language-error completion atomically makes
its replacement contribution visible again. This prevents dirty, pending,
invalidated, unavailable, or server-failed entries from leaving compiler
squiggles on text the compiler did not analyze.

L4 also adds one capability-gated LSP work-done progress lifecycle for each
serialized compile-pump busy interval. Generations coalesced or superseded
within that interval share the lifecycle. Progress is observability only:
failure to establish it never delays, cancels, validates, or changes a
compile.

## Context And Authority

The owning language-server design already establishes:

- one immutable state transition plus explicit effects for each lifecycle
  change;
- one serialized full-Stage-3 compile pump;
- exact accepted-generation, source-vector, and configuration-vector
  authority;
- per-entry diagnostic contribution ownership and deterministic multi-entry
  aggregation;
- atomic current completion replacement; and
- no dirty-buffer analysis.

The L4 roadmap requires a diagnostic-currentness policy and balanced
capability-gated progress based on observed editor behavior. The
[2026-07-28 editor probe](../reports/2026-07-28-workflow-lisp-l4-editor-lifecycle-probe.md)
found that Neovim advertises work-done progress and renders a balanced
lifecycle, but retains the exact old diagnostic after `didChange`.
`Diagnostic.data.accepted_generation` remains available to tools but is not a
visible freshness treatment.

This amendment inherits design principles 27–30. In particular, it preserves
deterministic compiler authority, does not invent a diagnostic to explain
withholding, imposes no authored type surface, and keeps mechanically owned
status out of provider instructions.

## Problem

The server currently retains an accepted contribution while an entry becomes
dirty, pending, dependency-invalidated, or server-failed. Retention prevents
flicker, but generic clients continue rendering the old range against current
buffer text. Because the server deliberately does not compile dirty buffers,
that rendered squiggle can claim a location and problem the compiler never
observed.

Full Stage-3 compilation is also intentionally serialized and may be visible
to a user as a pause. The server exposes no standard progress lifecycle, so a
temporarily empty diagnostic view after the freshness correction could
otherwise look like lost analysis rather than analysis in progress.

These are lifecycle-policy decisions, not local rendering fixes: both must
remain correct under multiple contribution owners, coalescing,
supersession, close, configuration staleness, and transport failure.

## Goals

- Make every published contribution visibly current for its owning entry.
- Preserve retained contribution ownership, generations, dependency
  targeting, and deterministic deduplication while a contribution is hidden.
- Replace the visible aggregate atomically on a current success or language
  error.
- Expose one balanced, capability-gated progress lifecycle for one logical
  serialized compile-pump busy interval.
- Coalesce superseded and newly queued generations without per-generation
  progress churn.
- Keep progress transport failure irrelevant to compile correctness and
  scheduling.
- Prove behavior through pure state/aggregation tests, server integration, a
  real stdio client, and a repository-real editor probe.

## Non-Goals

L4 adds no dirty-buffer or overlay compilation, tolerant parsing,
multi-diagnostic recovery, compile cache, incremental or parallel compiler,
debounce policy change, telemetry, runtime-session reporting, percentages,
editor extension, editor-specific API, diagnostic pull model, persistence, or
workspace mutation.

It does not repurpose `DiagnosticTag.Unnecessary`, rewrite compiler messages,
append stale prose, synthesize a freshness diagnostic, or treat
`Diagnostic.data` as a generally visible UI. It adds no public cancel-compiles
command: the progress item is non-cancellable and observes the driver's
existing generation cancellation/supersession rules.

## Decision

### Diagnostic presentation policy

Keep the accepted contribution tuple on its `CompileEntryState`, but include
that tuple in the published aggregate only when the owner is
**diagnostically current**:

1. the entry is open and `buffer_status == "clean"`;
2. `pending_generation is None`;
3. `compile_status` is `success` or `language_error`; and
4. every retained contribution's `accepted_generation` equals the entry's
   current `generation` and `compile_entry_uri` equals the entry URI.

An empty contribution tuple satisfies the fourth condition. The projection
validates the same owner/generation structure as the existing state boundary.
A malformed tuple raises and is logged as an internal server error; it is
never silently interpreted as an empty or merely hidden contribution set.

Dirty, unavailable, pending, clean-idle, dependency-invalidated,
server-failed, configuration-stale, closed, and unassociated entries
contribute no rows to the visible aggregate. Their retained contribution
tuples remain available only for ownership, reverse invalidation, replacement,
and clearing decisions. The diagnostic target URIs from those tuples remain
known.

Any transition that changes an owner's diagnostic currentness republishes the
union of that owner's old and new target URIs. Publication aggregates only
diagnostically current owners from the already-adopted state. Therefore:

- hiding one owner cannot erase an equivalent current contribution owned by
  another entry;
- dirtying or invalidating the sole owner publishes an empty diagnostic list
  for each old target;
- a current completion installs its replacement and reveals it in one state
  transition before publication; and
- a late or superseded completion remains unable to reveal anything.

### Compile progress policy

The server records whether the initialized client's
`window.workDoneProgress` capability is exactly `true`. When false or absent,
the server sends no progress-create request and no `$/progress` notification.

For a supporting client, one server-local progress controller observes the
logical compile pump. Its state is closed:

```text
inactive
creating(token, busy_interval)
active(token, busy_interval)
suppressed(busy_interval)
```

The first eligible queued generation after `inactive` opens one busy interval
and one unique, monotonically allocated process-local token. The controller
sends `window/workDoneProgress/create` without awaiting it on the compile
critical path. Compilation starts through the unchanged pump.

If creation succeeds while the same interval still has logical work, the
controller emits exactly one `begin` with `cancellable=false` and becomes
`active`. If the interval already closed, the token is left unused and no
`begin` is emitted. If creation fails, the server logs the transport error,
emits no progress notification for that interval, and becomes `suppressed`
until the interval closes. It does not retry until a later interval.
Compilation is unchanged in both cases.

A busy interval remains open while at least one current eligible generation
is queued or active. A cancellation paired atomically with a replacement
generation is supersession inside the same interval: it produces no `end` or
new token. Multiple entries and generations therefore share one lifecycle.

When no current eligible generation remains, an `active` interval emits
exactly one `end` and returns to `inactive`; `creating` and `suppressed`
intervals close without emitting an unmatched lifecycle frame. Success,
language error, server error, close, existing generation cancellation,
configuration staleness, unexpected pump failure, and pump-task cancellation
all pass through this same settlement rule. If other eligible work remains,
the interval continues.

LSP permits a client to send `window/workDoneProgress/cancel` even when the
server advertised `cancellable=false`. This cancels presentation only. An
`active` interval emits its one `end`, becomes `suppressed`, and continues
compilation without further progress for that interval. A `creating` interval
becomes `suppressed` without emitting `begin` or `end`. The notification never
mutates compile state, invalidates a ticket, or removes queued work. Only
quiescence returns `suppressed` to `inactive`, so cancellation cannot cause a
second token within the same busy interval.

Every successful create installs one pygls cancellation future for the token.
The controller retires that registration after `end`, client presentation
cancellation, or a late successful create for an already closed interval.
Tokens are never reused. A late callback is matched by both token and interval
identity and cannot begin, end, suppress, or otherwise affect a newer
interval. Cancellation for an unknown or already retired token follows
pygls's existing ignore-and-log behavior.

The controller emits no percentage because work can be coalesced after the
interval begins and the compiler exposes no honest fractional phase. Visible
title/message prose is presentation, not an API; tests assert capability
gating, token/order/cardinality, and settlement rather than literal wording.

## Design Details

### Ownership and visibility stay separate

`CompileEntryState.diagnostic_contributions` remains the sole internal
ownership tuple. L4 adds a pure visibility predicate and a pure
state-to-visible-contribution projection; it does not add a second
contribution store, mutate diagnostic values, or stamp presentation state into
compiler data.

`StateEffects.republish_uris` remains the only publication instruction.
Transitions that move between visible and hidden states calculate affected
URIs from the retained old/new tuples. The server consumes the final adopted
state and aggregates only visible owners. This preserves the existing
single-writer state boundary.

### Progress stays transport-local

Progress state belongs to `WorkflowLispLanguageServer`, not `LspState`,
`LspCompileDriver`, compiler session state, artifacts, or the workspace. It is
not persisted and is never consulted for compile acceptance, navigation,
diagnostics, retry, or restart.

The server already observes all scheduling and cancellation effects and owns
the async pump. The progress controller consumes those facts rather than
adding compiler callbacks. Blocking compiler execution remains in the current
`asyncio.to_thread` call, and an invalidated thread result remains discarded
by the existing driver ticket/currentness checks.

An existing cancellation may settle the visible interval before an
uninterruptible worker thread returns when no eligible generation remains.
The late worker result remains invalid and cannot reopen progress. A later
new generation opens a new interval and token.

## Contracts And Interfaces

L4 changes only server-to-client presentation:

- `textDocument/publishDiagnostics` may publish an empty list immediately
  when an entry becomes non-current, instead of retaining its old visible
  rows until the next accepted completion.
- Supporting clients may receive one
  `window/workDoneProgress/create` request and a balanced `$/progress`
  begin/end pair per logical compile busy interval.
- Progress `cancellable` is false; percentage is absent.

Compiler diagnostic identity, `Diagnostic.data`, source/configuration
currentness, compile requests, initialization options, CLI parity, navigation,
completion, workspace reads, and workspace writes do not change.

## Invariants And Failure Modes

- A hidden contribution is retained exactly; hiding never deletes ownership.
- Only diagnostically current owners enter publication aggregation.
- Malformed contribution ownership/generation state raises and logs; it is
  never projected as a successful empty publication.
- Publication still deduplicates by the existing structured parity identity
  and canonical owner order.
- Every emitted progress `begin` has exactly one later `end` for the same
  token while the transport remains available; `end` is never emitted without
  `begin`.
- Supersession with replacement does not split one busy interval.
- Capability absence and progress-create failure produce zero progress
  notifications and never affect compilation.
- A client cancellation notification for the non-cancellable token settles
  presentation exactly once, suppresses the remainder of that busy interval,
  and does not cancel compiler work or mutate LSP state.
- Transport shutdown may make delivery impossible; local lifecycle state is
  nevertheless settled and no workspace state is written.

## Evidence And Implementation Boundaries

The default production path must provide both changes:

- visibility is derived from production `LspState` and used by the production
  `_emit_transition_effects` aggregation path; and
- progress wraps the production deferred compile pump created by
  `create_server`, not a fixture-only compiler or test adapter.

The editor probe is selection evidence, not implementation evidence. The
minimal probe server proves client presentation only and must not be shipped
or treated as the L4 implementation.

## Compatibility And Migration

Clients that omit work-done progress capabilities retain the same protocol
surface except for currentness-driven empty diagnostic publications. Clients
that support progress require no configuration. Existing setup and
initialization options remain valid.

Users will see old squiggles disappear on unsaved change or while a saved
generation is pending, then see current diagnostics appear atomically after
completion. This intentionally accepts bounded flicker in exchange for honest
freshness. Saving remains the route to current analysis.

## Verification Strategy

### Pure and unit coverage

- Truth-table the diagnostic-currentness predicate, including success,
  language error, dirty, unavailable, pending, idle, server error, closed,
  and configuration-stale states; malformed generation/owner metadata must
  raise rather than become a successful empty projection.
- Prove dirty/pending/invalidation effects republish old target URIs without
  deleting retained tuples.
- Prove hiding one of two parity-identical owners leaves the other visible,
  hiding the last owner yields an empty publication, and current replacement
  reveals only the new tuple.
- Truth-table the progress controller for unsupported capability, create
  success/failure/late success, success, language error, server error, close,
  client presentation cancellation, configuration staleness, pump exception,
  task cancellation, and new work after settlement.
- Prove token registrations retire after end, client cancellation, and unused
  late create acknowledgment, and that a late callback cannot affect a newer
  interval.
- Prove cancellation-plus-replacement supersession retains one token and one
  begin/end pair.

### Integration and end-to-end coverage

- Drive the real deferred server with a blocked production-shaped builder:
  dirty, save, supersede, close, and two-entry coalescing must yield exact
  publish and progress order without accepting a late result.
- Drive real stdio with supporting and non-supporting capabilities. The
  supporting case must answer the create request and observe balanced frames;
  the other must observe none.
- Run a repository-real Neovim headless gate against `python -m
  orchestrator.lsp`: an invalid clean file first displays a diagnostic,
  unsaved change clears it, save displays one progress interval, and the
  current completion either publishes current diagnostics or an empty list.
  If Neovim is unavailable, the implementation gate does not pass; a protocol
  harness alone is not substituted.
- Prove the fixture workspace tree and `.orchestrate` absence are unchanged.

No test asserts literal diagnostic or progress prose.

## Declarative Acceptance Scenario

Two clean open entries contribute the same imported-file diagnostic. Entry A
becomes dirty; the real client receives a publication still containing entry
B's contribution. Entry A is saved, and while its current generation is
pending the supporting client observes one work-done `begin` and no stale A
diagnostic. A newer save supersedes A before completion and joins the same
progress interval. The late result is discarded. The replacement generation
finishes with a current language error on another target; the client receives
the atomic new aggregate and one `end`. No second progress token, compiler
write, runtime state, synthetic diagnostic, or stale navigation result
appears.

## Success Criteria

- The ordered design reviews accept this amendment and its editor evidence.
- An implementation plan maps every state/progress branch to TDD tasks and
  keeps baseline incorporation separate from behavior implementation.
- Focused LSP suites, the real stdio gates, the repository-real Neovim gate,
  and the roadmap's security-excluded broad comparison pass.
- Ordered implementation specification then quality reviews approve the exact
  committed bytes.

## Stop / Revise Criteria

- Honest visibility requires deleting or rewriting internal contributions
  rather than projecting them: revise the ownership seam.
- Progress requires blocking compilation on client acknowledgment or adding
  compiler callbacks: revise the controller boundary.
- A real generic client fails to clear hidden diagnostics, fails to surface a
  balanced lifecycle, or requires an editor-specific API: return to design
  review rather than shipping a client special case.
- Correct settlement requires parallel compiler execution, a compile cache,
  persisted progress, public cancellation, or telemetry: defer that behavior
  instead of expanding L4.
