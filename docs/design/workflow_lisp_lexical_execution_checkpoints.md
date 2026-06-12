# Workflow Lisp Lexical Execution Checkpoints And Durable Resource Resumability

Status: draft target design (future target; describes intended behavior, not
the current checkout)
Kind: architecture / runtime resumability target
Created: 2026-06-12
Scope: private lexical execution checkpoints over WCC program identity;
effect-boundary resume policies; the separation between execution
resumability and domain durability; retirement of authored resume plumbing
from public `.orc` boundaries.

Authority:

- Normative runtime and DSL behavior remains in `specs/`. This document
  defines a target; nothing here changes current resume semantics until its
  tranches land with evidence.
- `docs/design/workflow_lisp_core_calculus_middle_end.md` owns the WCC
  calculus: structured control, second-class join points, scopes, proof
  state, effect rows, and environment identity. This design consumes that
  identity as the checkpoint substrate; it adds no calculus constructs.
- `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`
  owns `Resource<TState>`, `Transition<TRequest, TResult>`, idempotency,
  audit, conflict handling, and boundary authority classes. This design
  consumes those contracts unchanged; it does not redefine durability.
- `docs/design/workflow_lisp_state_layout.md` owns generated path identity
  and allocation rules. Checkpoint storage receives new allocation roles;
  identity rules are not redefined here.
- `docs/design/workflow_lisp_runtime_migration_foundation.md` owns validated
  structured output and private value transport — the only channel through
  which completed effect results may be reused.
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  (Tranche 8) owns near-term canonical resume/reuse validation and the
  migration-parity resume evidence for family promotion. This design is the
  long-term substrate beyond that tranche and must not be used to relitigate
  or block it.

Related docs:

- `docs/design/workflow_lisp_core_calculus_middle_end.md`
- `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_runtime_migration_foundation.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/lisp_workflow_drafting_guide.md`
- `specs/state.md`

## 1. Purpose

Two questions are currently answered by one entangled mechanism:

1. Execution resumability: where was this workflow in the program?
2. Domain durability: what semantic workflow state changed?

Today both are served by a mixture of step-granular run state, generated
state bundles, loop-frame machinery, schema-versioned fail-closed checks,
and — the part this design exists to remove — authored plumbing. Workflows
thread `run_state` paths through loop state, accept summary and pointer
target paths as public inputs, and pass prior-state paths into
`resume-or-start` partly so that a future resume has something durable to
find. The reference drain carries its run-state path through every loop
iteration; `resume-or-start` takes an authored `:resume-from` state path.
Some of that is genuine domain state. Some of it exists only because
execution position has no private home of its own.

The target separates the ledgers:

```text
Execution position  -> private lexical checkpoints (runtime-owned, disposable)
Semantic change     -> typed resources and transitions (durable, audited)
```

A lexical checkpoint records where the program is — continuation, bindings,
frames, proofs, pending effect — in terms of WCC program identity. A
resource transition records what the workflow did to the world. Neither
substitutes for the other: checkpoints make resumption cheap and invisible;
resources make outcomes auditable and parity-comparable. Authored `.orc`
code stops carrying paths whose only purpose is to let the runtime find its
place.

This is a future target. The current checkout resumes at step granularity
with fail-closed lowering-schema checks and resume-stable generated path
identity; those mechanisms remain authoritative until the tranches here
land with evidence.

## 2. Alternatives Considered

### 2.1 Resource-only resumability (rejected)

Make every resumable position a domain resource: loop counters, branch
positions, intermediate bindings all become `Resource<TState>` with
transitions.

Rejected because it conflates position with meaning and maximizes authoring
burden. A drain's iteration counter is not a domain fact; forcing it into
the resource ledger pollutes audit evidence with execution mechanics,
forces authors to design state types for what is really control flow, and
reproduces the current disease at a higher level: workflows shaped around
the runtime's memory instead of the domain's meaning. It also makes parity
noisy — domain comparisons would have to filter out position records.

### 2.2 Checkpoint-only resumability (rejected)

Make checkpoints the universal mechanism: snapshot the whole execution
environment, restore it on resume, and drop typed resources as a separate
concept.

Rejected because it is too weak for semantic audit and parity. A checkpoint
proves where the program was, not what it legitimately did: it carries no
idempotency keys, no transition preconditions, no conflict detection, no
audit projection, and no domain record that two implementations can be
compared on. Restoring copied domain state from a checkpoint is exactly the
failure mode the transition contract exists to prevent — state changes
re-entering the world without version checks or evidence. Checkpoint-only
designs also age badly: a checkpoint is bound to one executable's identity,
while domain state must outlive recompiles.

### 2.3 Hybrid: lexical checkpoints plus typed transitions (chosen)

Checkpoints own execution position; resources and transitions own semantic
change; explicit resume policies govern every effect boundary between them.
Each ledger does what only it can do. The checkpoint is a disposable cache:
losing one costs recomputation from the last consistent boundary, never
correctness. The resource ledger is the record: losing it is data loss, and
nothing in this design weakens it. On any inconsistency between the two,
the domain ledger wins.

## 3. Current-State Anchors

What exists today, stated as consumed fact rather than redesigned:

- Resume operates at step granularity from run state, with a resume
  planner, loop-frame handling, and fail-closed rejection when the lowering
  schema version of recorded state does not match the executable.
- Generated path identity is resume-stable: the same run and
  call-frame/loop identity reconstructs the same concrete generated path
  (`workflow_lisp_state_layout.md`), and generated pure-projection bundles
  already resume at step-visit scope.
- Validated structured output is the only sanctioned reuse channel for
  provider/command results (runtime migration foundation).
- `resume-or-start` is the authored surface for domain-state reuse: it
  validates prior canonical state against a typed contract and either
  returns it or runs fresh.
- The reusable-state diagnostic taxonomy is fail-closed with preserved
  inner causes.
- Authored resume plumbing exists in real families: run-state paths carried
  in loop state, prior-phase state paths passed as inputs, summary/pointer
  targets exposed publicly — shapes the boundary-authority work already
  classifies as bridges or bookkeeping.

Tranche R0 re-verifies these anchors against the checkout before any
behavior changes.

## 4. Authority And Dependency Direction

### 4.1 This document consumes

- WCC program identity: join points, ANF binding structure, scope and
  proof analysis, effect rows, environment identity, lowering schema
  version.
- `Resource<TState>` / `Transition<TRequest, TResult>` semantics:
  versions, preconditions, idempotency keys, conflict policy, audit.
- StateLayout allocation identity and provenance rules.
- Validated structured output and the private value lane.
- The boundary authority classes (`public_authored`,
  `compatibility_bridge`, `runtime_derived`, `generated_internal`,
  `materialized_view`).

### 4.2 This document owns

- The lexical checkpoint content model, identity, validity, and
  storage contract.
- The effect-boundary resume policy taxonomy and its declaration surface.
- The certified resume protocol requirement for non-idempotent external
  effects.
- The cross-ledger consistency rule (domain wins).
- The retirement target for resume-only authored plumbing.
- The resumability failure-mode taxonomy and its diagnostics.

### 4.3 This document does not own

- Transition execution semantics (generic-core design).
- WCC pass structure or calculus changes.
- Concrete checkpoint path names or allocation identity rules
  (state layout doc; this design adds roles).
- Near-term migration resume evidence and promotion gating
  (post-foundation Tranche 8).
- `resume-or-start` domain semantics (frontend spec / stdlib); this design
  narrows its *usage*, not its contract.

### 4.4 Sequencing relative to the generic-core target

This design is a separate target implemented after
`workflow_lisp_generic_core_expression_surface_adapter_retirement.md`, not
a candidate for merging into it. The dependency is one-way — this design
consumes the generic core's contracts; the generic core needs nothing from
this design — and the two answer different questions (what the language
can express and what the runtime knows, versus where the program was).

Hard ordering:

- Tranche R4 requires the generic core's transition runtime (its G3):
  idempotency keys and audit records are the evidence R4 resumes through.
- Tranche R5 requires the generic core's boundary authority machinery and
  census (its G0/G7): R5 retires the `resume_only` subset of the same
  plumbing that work classifies.

Tranches R0-R2 depend only on WCC and state layout, which are landed, but
they are still sequenced after the generic core's substrate tranches as
lane discipline: both touch the executor and resume machinery, and two
concurrent compiler/runtime lanes in the same files is a known fork
hazard. This document must not be registered as drain-selectable until
the generic core's transition tranche has acceptance evidence.

### 4.5 Relationship to authority inversion (deferred enablement)

The WCC design defers, without rejecting, a nesting-native runtime
(authority inversion). This design is deliberately substrate-portable
groundwork for that path: program-point identity, per-frame schemas,
environment serialization, and effect-boundary resume policies are exactly
the assets such a runtime would consume. Two consequences are recorded as
design intent:

- Frame schemas are static per call site; a stack of frames serializes as
  a list of statically shaped activations. The checkpoint schema therefore
  accommodates dynamic control depth without redesign, should a future
  runtime support it. Nothing in this design may bake a
  flat-executor-only assumption into checkpoint content beyond what
  Section 8.2 states.
- The named open problem for bounded general recursion is activation
  identity: per-call-site activation ordinals generalizing loop ordinals,
  on which result reuse, StateLayout identity, and source-mapped
  diagnostics would key. That problem is out of scope here and owned by
  the authority-inversion thread in the WCC design.

Sequencing is strict: checkpoints are proven on the current flat runtime
first, where differential verification against unchanged authority is
cheap. This document must not be cited to justify replacing the execution
substrate; it lowers the cost of that future decision without taking it.

### 4.6 Prohibited dependency directions

```text
checkpoint content        -> raw Python objects                PROHIBITED
checkpoint content        -> unvalidated pointer/report paths  PROHIBITED
resume of effect results  -> anything but validated bundles    PROHIBITED
transition resume         -> restored copies of resource state PROHIBITED
public .orc boundary      -> checkpoint/generated runtime path PROHIBITED
domain durability         -> checkpoint availability           PROHIBITED
parity evidence           -> checkpoint internals              PROHIBITED
```

The last two state the disposability rule from both sides: no domain
outcome may depend on a checkpoint surviving, and no parity comparison may
reach into checkpoint internals — checkpoints are invisible to everything
except the resuming runtime.

## 5. Goals

1. A crashed or interrupted run resumes from its last consistent execution
   position — inside a branch arm, between bindings, mid-loop-iteration —
   without re-running completed effects and without any authored support.
2. Authored `.orc` workflows carry no pointer paths, run-state paths,
   summary target paths, checkpoint paths, or generated bundle paths whose
   only justification is resume.
3. Typed resources and transitions remain the sole record of semantic
   change, with idempotency, conflict, audit, and parity semantics exactly
   as the generic-core design specifies.
4. Every effect boundary has an explicit, declared resume policy; the
   default for non-idempotent external effects is fail-closed.
5. Checkpoints are schema-versioned, executable-digest checked,
   source-mapped, and validated before use; a stale, corrupt, or
   mismatched checkpoint degrades to a coarser consistent boundary, never
   to undefined behavior.
6. Variant proof scopes survive resume soundly: restored by re-proof from
   validated values, never by trusting recorded claims.
7. Public boundary inspection can prove goal 2 mechanically.

## 6. Non-Goals

- Not a distributed or parallel execution design; resume remains
  single-run, sequential, local.
- Not time-travel debugging, speculative replay, or cross-run memoization
  of checkpoints (deferred; the identity model deliberately leaves room).
- Not a replacement for `resume-or-start`: authored domain reuse — "this
  phase's approved result is still valid, keep it" — remains an authored,
  typed decision. This design removes the *execution-position* burden from
  that surface, not the domain judgment.
- Not a journal/replay execution model: the runtime does not re-execute
  history to reconstruct state; it restores position and reuses validated
  results.
- Not an excuse to weaken step-level run-state observability: run state,
  logs, and reports remain inspectable evidence.
- Does not make resources obsolete, optional, or implicit — the resource
  ledger is load-bearing in this design, not legacy.

## 7. Architecture Invariants

1. Two ledgers, one authority. Execution checkpoints are a private,
   disposable cache of position; resources/transitions are the durable
   record of meaning. On inconsistency, the domain ledger wins and the
   checkpoint is discarded back to the last boundary consistent with audit
   evidence.
2. Checkpoint loss is never a correctness event. Any checkpoint may be
   deleted at any time; the run must still resume (more coarsely) or fail
   closed with a taxonomy diagnostic — never produce different semantics.
3. Checkpoints are private runtime state: allocated through StateLayout
   under private roles, never authored, never public inputs/outputs, never
   prompt-visible, never parity evidence.
4. Checkpoint validity is checked, not assumed: schema version match,
   executable digest match, structural validation, and typed revalidation
   of every stored value or bundle reference before any of it re-enters
   scope.
5. Typed content only. Checkpoints store typed lexical values or validated
   bundle references. No raw interpreter objects, no closures, no
   unvalidated paths, no provider session handles.
6. Effect results re-enter execution only through validated structured
   output — the same fail-closed channel that admitted them originally.
7. Transitions resume through evidence: a committed transition is
   recognized by its idempotency key and audit record; resource state is
   re-read from the resource ledger at its current version, never restored
   from checkpoint copies.
8. Pending non-idempotent external effects fail closed on resume unless
   the effect declares a certified resume protocol; "probably didn't run"
   is not a policy.
9. Proof is re-established, not remembered: a restored `match` scope is
   sound only because the runtime re-proves the variant from the validated
   scrutinee value; the checkpoint's record of proof state is an
   optimization hint, not an authority.
10. Materialized views are never restored; they are regenerated from typed
    values when needed.
11. WCC metadata stays internal: continuations, join identities, and
    environment structure never surface as public workflow values or
    authored types.

## 8. Core Model

### 8.1 The two ledgers

```text
Lexical checkpoint (private, disposable)     Resource ledger (durable, audited)
------------------------------------------   ----------------------------------
program point (join/continuation identity)   resource identity + version
typed lexical environment                    typed state (validated)
call frames / loop frames                    transition audit records
active proof scopes (re-proof required)      idempotency keys
completed effect result references           conflict/precondition evidence
pending effect boundary + policy             parity-comparable outcomes
allocation namespace cursor
```

The left column answers "where was the program"; the right answers "what
did the workflow do". The runtime resumes by validating a checkpoint,
re-binding its environment from validated values, re-proving its scopes,
reconciling its completed-effect references against bundles and audit
records, and continuing from its program point. If no usable checkpoint
exists, the runtime falls back to the coarser boundary semantics (today's
step-visit granularity is the floor).

### 8.2 Checkpoint content model

A checkpoint is a typed record with, at minimum:

- **Program point.** The WCC-derived identity of the resumption site: join
  point or continuation identity, within which call frame and loop frame
  (loop identity plus iteration ordinal). This is defunctionalized
  identity — a name in the lowered program — not a serialized
  continuation object.
- **Lexical environment.** The live bindings at that point, each stored as
  a typed scalar/record/union value (validated on restore against its
  declared type) or as a reference to a validated structured-output bundle
  (revalidated on restore). Bindings whose types are runtime-forbidden in
  transport (provider refs, prompt refs, `ProcRef`/`WorkflowRef`) are
  never stored; they are rebound from configuration on restore, which is
  sound because they are compile-time/wiring values by construction.
- **Proof scopes.** The stack of active variant proofs: which scrutinee
  binding, which variant. Stored as claims to be re-proved (invariant 9).
- **Completed effect results.** For each effect boundary already crossed
  in the current region: the effect's identity, its policy class, and the
  reference to its validated result (bundle reference, transition
  idempotency key + audit reference, or projection payload digest).
- **Pending effect boundary.** If the run stopped at an effect: the
  effect identity, its declared resume policy, and enough evidence to
  apply that policy (e.g., the idempotency key it would have used).
- **Allocation namespace cursor.** The StateLayout namespace state needed
  to keep generated identity stable across the resume — consumed from the
  state layout doc's identity rules, not reinvented.
- **Validity envelope.** Checkpoint schema version; the executable digest
  of the exact Executable IR (and lowering schema version) it belongs to;
  source-map linkage for diagnostics; run identity.

### 8.3 Identity and validity

A checkpoint is usable only if all of the following hold, checked in
order, each failure fail-closed with its own diagnostic code:

1. checkpoint schema version is supported
   (`checkpoint_schema_unsupported`);
2. executable digest matches the executable being resumed
   (`checkpoint_executable_mismatch`) — a recompiled or edited workflow
   invalidates execution checkpoints by construction, exactly as the
   lowering-schema rule works today, with fallback to the coarsest
   consistent boundary or a fresh run;
3. structural validation of the checkpoint record passes
   (`checkpoint_invalid`);
4. every stored value revalidates against its declared type and every
   bundle reference revalidates through the structured-output validator
   (`checkpoint_value_invalid`);
5. cross-ledger reconciliation passes: every referenced transition's
   idempotency key is found committed in audit, and every referenced
   resource version is current or supersedable under the transition
   contract's conflict policy (`checkpoint_domain_conflict`); on conflict
   the checkpoint is discarded back to the last consistent effect
   boundary — the domain ledger wins.

### 8.4 Effect-boundary resume policies

Every effect boundary in the lowered program carries a resume policy,
derived from its form and declarations:

| Boundary | Policy | Mechanics |
| --- | --- | --- |
| Pure projection | `replay_or_reuse` | Deterministic: reuse the bundle if present and digest-valid, else re-evaluate; semantically equivalent either way. |
| Provider result | `reuse_validated_or_rerun` | If a validated structured-output bundle exists for this boundary's identity, reuse it (no re-prompt); otherwise re-run the provider from the boundary. Never resume "inside" a provider. |
| Command result (declared idempotent) | `reuse_validated_or_rerun` | Same as provider: bundle reuse or full re-run. |
| Command result (non-idempotent, no protocol) | `fail_closed` | If the checkpoint shows this boundary pending (started, completion unknown), resume refuses with `pending_effect_unsafe`, naming the step, the source form, and the operator's options. |
| Command result (certified resume protocol) | `protocol` | The adapter declares how to determine completion (e.g., an idempotency receipt or completion probe) and the runtime applies it; the protocol is part of adapter certification. |
| Workflow call | `recursive` | Resume descends into the callee's own checkpoint/boundary structure. |
| Resource transition | `evidence` | Committed = idempotency key present in audit: skip re-application, re-read the resource at current version. Not committed: re-apply through the full transition contract (version check, preconditions, conflict policy). Never restore resource state from the checkpoint. |
| Materialized view | `regenerate` | Views are never reused as authority; regenerate from the typed value if a consumer needs the file. |

The pending-effect rule deserves emphasis because it is where real systems
corrupt themselves: if the run died *after starting* a non-idempotent
external command and *before validating* its result, there is no safe
automatic answer. The design's answer is honesty — fail closed, say
exactly which boundary is unsafe and why, and make safe-by-declaration
(idempotence or a certified protocol) the path to automation.

### 8.5 What authors see

Nothing new, and less than today. No checkpoint form, no checkpoint type,
no resume annotations on ordinary code. The visible changes are
subtractive: loop state stops carrying run-state paths; public boundaries
stop accepting summary/pointer/bundle targets that existed for resume;
`resume-or-start` remains exactly the authored surface for *domain* reuse
(typed prior-state validation) and stops being pressed into service as an
execution-position mechanism. The single authored addition is at the FFI
edge: a certified adapter may declare a resume protocol, and a
non-idempotent command without one is simply not auto-resumable.

## 9. Tranche R0: Resume Semantics Census And Characterization

### 9.1 Contract

Freeze what resume does today and which authored surfaces exist to serve
it, so later tranches change behavior against a characterized baseline.

### 9.2 Tasks

- Characterization tests for current resume semantics: step-visit
  granularity, loop-frame behavior, lowering-schema rejection,
  generated-path reconstruction, `resume-or-start` reuse validation.
- Census of authored resume plumbing across the reference families: every
  public input, loop-state field, and record field whose justification is
  wholly or partly "so resume can find it", labeled with its boundary
  authority class and a `resume_only` / `mixed` / `domain` tag.
- Map every effect boundary kind in the lowered programs to its de facto
  current resume behavior, as the baseline for the Section 8.4 table.

### 9.3 Acceptance

- The characterization suite passes against the current checkout and is
  adopted as the regression floor for all later tranches.
- The plumbing census exists as a checked artifact; every `resume_only`
  entry names its retirement tranche (R5).

## 10. Tranche R1: Checkpoint Model, Schema, And Shadow Emission

### 10.1 Contract

Define and implement the checkpoint record (Section 8.2) and its validity
envelope (Section 8.3), and emit checkpoints in shadow mode — written and
validated on real runs, consumed by nothing.

### 10.2 Tasks

- Checkpoint schema v1 with structural validator; executable digest
  definition over Executable IR (content digest covering step structure,
  contracts, and lowering schema version).
- StateLayout allocation roles for checkpoint storage (private generated,
  run-isolated); atomic write protocol (temp + rename); retention policy
  (latest N consistent boundaries, deletable at will per invariant 2).
- WCC-side: export stable program-point identity (join/frame naming)
  through lowering into the Executable IR so checkpoints can name
  resumption sites; source-map linkage for every program point.
- Shadow emission at effect boundaries and loop back-edges in WCC-routed
  runs; validation-on-write plus a sampling validator that re-reads and
  revalidates emitted checkpoints.

### 10.3 Acceptance

- Real family runs emit schema-valid checkpoints at every boundary class
  with correct digests and source-map links; deleting all of them changes
  nothing observable (shadow property).
- Mutation tests: corrupted records, wrong digests, and unsupported
  schemas are rejected with the Section 8.3 diagnostic codes.

## 11. Tranche R2: Execution Restore For Pure And Structured Regions

### 11.1 Contract

Consume checkpoints to restore execution position in regions whose
boundaries are deterministic: between pure bindings, at branch arms, and
at loop back-edges. Behind a flag, with the characterization suite as a
differential oracle.

### 11.2 Tasks

- Restore protocol: validate (8.3), re-bind environment from typed
  values/validated bundles, re-prove proof scopes from scrutinee values,
  re-seat the allocation cursor, continue from the program point.
- Branch-local resume: re-enter a `match` arm with proof re-established.
- Loop resume: continue iteration N of a value-carrying `loop/recur` from
  its frame — including loops with no domain resources at all.
- Mid-`let*` resume between completed effect boundaries, reusing
  completed pure-projection results by digest.
- Differential evidence: for a corpus of interrupted runs, flag-on resume
  reaches the same terminal typed results, artifacts, and resource
  versions as flag-off (coarse) resume and as uninterrupted runs.

### 11.3 Acceptance

- The three scenario classes (branch-local, loop-without-resources,
  mid-binding) resume correctly under crash injection at every eligible
  point, with no authored support and no re-run of completed effects.
- Proof-soundness negative test: a checkpoint whose recorded proof claim
  disagrees with its stored scrutinee value fails re-proof and is
  rejected, never restored.

## 12. Tranche R3: Effect-Boundary Resume Policies

### 12.1 Contract

Implement the Section 8.4 policy table for provider, command, and workflow
boundaries, including the fail-closed rule and the certified resume
protocol surface.

### 12.2 Tasks

- Boundary policy derivation in lowering (form + declarations -> policy,
  recorded in Executable IR); effect rows surface the policy class.
- Provider/command reuse path: boundary identity -> validated bundle
  lookup -> revalidation -> rebinding; re-run path from the boundary
  otherwise.
- Idempotence declaration for commands; certification schema extension
  for resume protocols (owned mechanically by the adapter contract doc;
  this design owns the requirement); `pending_effect_unsafe` diagnostics
  with source-mapped boundary identification.
- Workflow-call recursive resume across checkpoint structures.

### 12.3 Acceptance

- Crash injection immediately before, during, and after each boundary
  class produces the policy table's exact behavior, including: completed
  provider results reused without re-prompting; pending non-idempotent
  command without protocol refusing resume fail-closed; certified
  protocol commands resuming through their declared probe.

## 13. Tranche R4: Transition-Aware Resume

### 13.1 Contract

Integrate with the generic-core transition runtime: transitions resume
through idempotency and audit evidence, and checkpoints never carry
resource state.

### 13.2 Tasks

- Cross-ledger reconciliation (8.3 step 5) against transition audit and
  resource versions; `checkpoint_domain_conflict` handling that discards
  back to the last domain-consistent boundary.
- Committed-transition recognition by idempotency key; re-read of current
  resource state; non-committed re-application through the full contract.
- Negative machinery: a checkpoint that embeds resource state (rather
  than identity + version reference) fails structural validation by
  schema construction.

### 13.3 Acceptance

- Crash after commit, before commit, and mid-commit (atomic abort) each
  resume to the same audited outcome as an uninterrupted run, with
  exactly one committed transition in audit in all cases.
- Conflict scenario: resource advanced by an external actor between crash
  and resume; resume honors the transition's declared conflict policy
  rather than the checkpoint's stale view.

## 14. Tranche R5: Authored Plumbing Retirement

### 14.1 Contract

Retire the census's `resume_only` authored surfaces from the reference
families; narrow `resume-or-start` usage to genuine domain reuse.

### 14.2 Tasks

- Re-express the reference family shapes: loop state carries typed values
  only; run-state paths and summary/pointer targets leave public
  boundaries per their authority class (private, derived, or labeled
  bridge with a retirement route).
- Each retirement follows the dual-evidence protocol: the family resumes
  correctly through checkpoints in the scenarios its plumbing previously
  served, before the plumbing is removed.
- Boundary inspection gains the rule: no public input or output of a
  promoted workflow may be classified `resume_only`; checkpoint and
  generated runtime paths at a public boundary fail promotion.
- Drafting-guide and review-criteria deltas: resume is not an authoring
  concern; `resume-or-start` examples show domain reuse only.

### 14.3 Acceptance

- The reference family compiles and passes its full resume scenario suite
  with zero `resume_only` public surfaces, and boundary inspection proves
  it mechanically.
- Migration parity for the re-expressed family remains `non_regressive`
  (the resume behavior change is invisible at the domain ledger, which is
  the parity surface).

## 15. Tranche R6 (Evidence-Gated): Default Flip And Legacy Cleanup

### 15.1 Contract

Make checkpoint-based resume the default route once differential evidence
holds across the family corpus; retire resume machinery the new route
makes redundant. Deletion-only where evidence proves redundancy; gated on
R2-R5 acceptance.

### 15.2 Tasks

- Flip the default with the coarse route retained as fallback for
  checkpointless runs (invariant 2 makes this permanent, not
  transitional: the floor semantics must always exist).
- Retire loop-frame and state-clearing workarounds that exist only to
  approximate sub-step resume, after per-mechanism redundancy evidence.
- CI guards: no new authored surface classified `resume_only`; no
  checkpoint path in any public contract.

### 15.3 Acceptance

- Default-on across the corpus with the characterization suite green;
  fallback exercised by checkpoint-deletion tests; redundancy-evidenced
  machinery deleted with line-count deltas reported.

## 16. Failure Modes

| Failure | Detection | Response |
| --- | --- | --- |
| Checkpoint corrupt / truncated | structural validation (8.3.3) | discard; resume from previous consistent checkpoint or coarse boundary |
| Executable changed since checkpoint | digest mismatch (8.3.2) | fail closed for fine-grained resume; offer coarse boundary or fresh run; never best-effort map old positions onto new programs |
| Stored value fails type revalidation | 8.3.4 | discard checkpoint; taxonomy diagnostic with source-mapped binding identity |
| Checkpoint claims proof its value disproves | re-proof (invariant 9) | reject checkpoint; this is the soundness backstop against tampered or buggy proof records |
| Domain moved on (resource version advanced; transition conflict) | cross-ledger reconciliation (8.3.5) | domain wins; discard to last consistent boundary; apply transition conflict policy |
| Pending non-idempotent effect, no protocol | pending-boundary policy | `pending_effect_unsafe`, fail closed, name the boundary and the operator's options |
| Partial checkpoint write (crash during emission) | atomic write protocol | impossible by construction (temp + rename); a missing checkpoint is just coarser resume |
| All checkpoints lost | absence | coarse-boundary resume (the permanent floor); correctness unaffected by invariant 2 |
| Checkpoint storage leaks into prompts/contracts/parity | boundary inspection + prohibited-direction guards | compile/validation error; prohibited evidence |

## 17. Verification Strategy

- Characterization-first: R0's suite is the floor for every later change.
- Crash-injection matrix: every boundary class × {before, during, after},
  plus loop back-edges and branch arms, under flag-on/flag-off
  differential comparison of terminal typed results, artifacts, resource
  versions, and audit records.
- Mutation testing of the validity envelope: schema, digest, structure,
  values, proofs, domain reconciliation — each with its diagnostic code.
- Checkpoint-deletion chaos test: randomly delete checkpoints mid-corpus;
  semantics must be unchanged (disposability evidence).
- Proof-soundness adversarial fixtures (tampered proof claims).
- Idempotency evidence: exactly-one-commit assertions under crash/resume
  for transitions; no-re-prompt assertions for completed provider
  boundaries.
- Boundary inspection tests for the `resume_only` rule and checkpoint
  path privacy.
- Determinism: pure-projection replay-vs-reuse equivalence under both
  paths.

## 18. Declarative Acceptance Scenarios

### 18.1 Branch-local resume

A run crashes inside the `COMPLETED` arm of a `match`, after the
implementation provider's result was validated but before the review call.
Resume re-validates the checkpoint, re-proves `COMPLETED` from the stored
attempt value, rebinds `c`, and continues at the review call. The
implementation provider is not re-prompted; no authored state was
involved.

### 18.2 Loop resume without domain resources

A pure value-carrying `loop/recur` (counter state, no resources, no
authored paths) crashes mid-iteration 3 of 6. Resume restores the loop
frame and continues iteration 3 with the same typed state, terminating
with the same result as an uninterrupted run. Nothing about the loop
touched the resource ledger or any public path.

### 18.3 Transition audit reuse

A run crashes after a drain status transition committed but before the
summary projection ran. Resume finds the transition's idempotency key in
audit, does not re-apply it, re-reads the resource at its current
version, regenerates the summary view from typed state, and completes.
Audit shows exactly one transition.

### 18.4 Unsafe command non-rerun

A run crashes while a non-idempotent external command (no certified
resume protocol) is pending. Resume fails closed with
`pending_effect_unsafe`, naming the step, its authored source form, and
the options: verify and mark, re-run explicitly, or certify a protocol.
No automatic re-execution occurs.

### 18.5 Plumbing-free public boundary

The re-expressed reference family exposes no run-state, summary-target,
pointer, checkpoint, or generated bundle path whose classification is
`resume_only`; boundary inspection proves it; the family still passes the
full crash/resume scenario suite.

### 18.6 Executable drift

A workflow is edited and recompiled between crash and resume. Fine-grained
resume refuses (digest mismatch) with a diagnostic that names both
digests; the operator chooses coarse-boundary resume or a fresh run; no
checkpoint from the old executable influences the new one.

## 19. Success Criteria

1. The four core scenarios (18.1-18.4) pass under crash injection with no
   authored resume support.
2. The reference family's public boundary has zero `resume_only` surfaces,
   proven by inspection, with domain parity `non_regressive`.
3. Checkpoint disposability holds corpus-wide (chaos evidence); domain
   outcomes never depend on checkpoint survival.
4. Every effect boundary class has a declared policy with crash-matrix
   evidence; non-idempotent-without-protocol fails closed everywhere.
5. Transitions show exactly-one-commit semantics under all crash/resume
   timings; checkpoints contain no resource state by schema construction.
6. WCC internals (continuations, join identity, environments) appear in no
   public value, authored type, prompt, or parity report.
7. The coarse resume floor remains available and tested permanently.

## 20. Summary Recommendation

Adopt the hybrid: private lexical checkpoints for execution position,
typed resources and transitions for semantic change, explicit policies at
every effect boundary between them. WCC already manufactures the
identities a checkpoint needs — join points, frames, scopes, proof state,
effect rows — so execution resumability becomes a runtime artifact of
compilation rather than an authoring obligation. Workflows shed the
pointer and run-state plumbing they carry today for the runtime's benefit;
the resource ledger keeps sole authority over what happened; and every
recovery path is either provably safe (validated reuse, idempotent
evidence, deterministic replay) or honestly refused.
