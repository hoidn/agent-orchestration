# Workflow Lisp Frontend Specification: Historical Sections

Status: **Historical.** Extracted original sections; original tense, review
labels, measurements and acceptance language are evidence, not current
authority or permission to execute/select work. Current owner: [workflow_lisp_frontend_specification.md](../../design/workflow_lisp_frontend_specification.md).

## 45. Core Workflow AST

Historical syntax-neutral flat structure; YAML authoring and flat execution
are retired. Retained typed/shared readers do not restore that backend.

Suggested shape:

```python
CoreWorkflow(
    name: QualifiedName,
    version: DslVersion,
    inputs: list[CoreInput],
    outputs: list[CoreOutput],
    statements: list[CoreStmt],
    source_map: SourceMap,
)
```

Core statements:

- `CoreMaterializeArtifacts`
- `CoreProviderStep`
- `CoreCommandStep`
- `CoreCallStep`
- `CorePureProjectionStep`
- `CoreMaterializeViewStep`
- `CoreOutputBundle`
- `CoreVariantOutput`
- `CorePreSnapshot`
- `CoreSelectVariantOutput`
- `CoreMatch`
- `CoreRepeatUntil`
- `CorePublish`
- `CoreAssert`
- `CoreResourceTransitionStep`
- `CoreProviderSupervisionStep`

Generated pure projections, materialized views, and resource transitions are
first-class Core statement families on the WCC/schema-2 route. Certified
command-adapter lowering remains available only when an explicit compatibility
contract declares the adapter backend for the same typed effect.

## 46. Validated Core Workflow AST

After shared validation.

Adds:

- `ReferenceCatalog`
- `ContractCatalog`
- `ProofContext` graph
- `WorkflowCallGraph`
- snapshot declarations
- artifact availability table
- effect graph
- pointer authority checks

This is where existing v2.14 validation should run.

## 47. Semantic IR

Semantic IR is validated and type-rich.

Suggested shape:

```python
SemanticWorkflowIR(
    workflows: dict[QualifiedName, SemanticWorkflow],
    types: TypeCatalog,
    contracts: ContractCatalog,
    refs: ReferenceCatalog,
    effects: EffectGraph,
    proofs: ProofGraph,
    state_layout: StateLayout,
    source_map: SourceMap,
)
```

`state_layout` records projections derived from `StateLayout` /
`PathAllocator` allocation metadata. The allocator returns neutral allocation
records; runtime binding, workflow-boundary projection, source maps, and
Semantic IR each consume those records rather than synthesizing generated paths
independently.

Semantic step examples:

```python
SemanticProviderResult(
    id,
    provider_ref,
    prompt_contract,
    return_type,
    variant_contract,
    artifact_contracts,
    effects,
)

SemanticVariantSelection(
    id,
    snapshot_ref,
    candidates,
    return_union,
    atomic_commit,
)

SemanticWorkflowCall(
    id,
    callee,
    args,
    return_type,
    version_policy,
)

SemanticProviderSupervision(
    id,
    worker_member,
    supervisor_member,
    observation_edge,
    directive_type,
    settlement_type,
    effects,
)
```

Semantic IR is the authoritative compiler output.

For a provider result with typed prompt dependencies,
`SemanticPromptSurface` carries the validated
`CompilerPromptDependencyContract`. The adjacent source map carries lineage for
the clause and each required/optional operand. Semantic IR describes the
compiled prompt contract; it does not own runtime file bytes or evidence
acceptance.

## 48. Executable IR

Runtime-ready form.

Contains:

- ordered executable steps
- resolved provider invocations
- resolved command invocations
- materialization actions
- snapshot capture actions
- atomic write actions
- runtime guards
- state projections
- observability hooks

Provider executable configuration carries the optional typed
`CompilerPromptDependencyContract` beside ordinary `depends_on` configuration.
Executable validation requires the side table and provider-step set to
reconcile exactly. The public `runtime_plan` deliberately omits dependency
operands, injection policy, compiler-contract data, content digests, and
evidence metadata; it remains topology/checkpoint planning only.

`ExecutableNodeKind.PROVIDER_SUPERVISION` carries a
`provider_supervision.v1` node-local schema. Its validated config contains the
two immutable member provider configs, the supervisor-to-worker observation
edge, worker and directive result contracts, pure settlement payload and
result contract, bounded member/step deadlines, `max_steers: 1`, and
visit/member/turn-qualified provisional paths. Runtime-plan and Semantic-IR
projections expose one composite node and one atomic result boundary, not two
independent workflow steps.

Executable IR no longer contains macros, procedures, or unresolved type forms.

Dedicated stdlib proving fixtures may also compile under a named
runtime-proof validation profile. That lane still has to assemble ordinary
`LoadedWorkflowBundle` values, derive Semantic IR / runtime-plan projections,
and pass executable IR validation, but it does not by itself certify that the
same workflow is promotion-ready as a public or parent-callable boundary.

## 49. Runtime Plan

Final runtime plan includes:

- step order
- dependencies
- state paths
- artifact publication plan
- snapshot storage plan
- error handling plan
- observability spans
- resume checkpoints

It does not include provider prompt-dependency paths, injection policy,
compiler-contract metadata, snapshot bytes/digests, or evidence locations.
Those belong to validated executable/semantic ownership and per-attempt state
or evidence, not topology.

## Part IX. Elaboration And WCC Projection Rules

This part describes how surface forms enter the WCC route and what flat Core
AST projection they may produce after WCC elaboration, ANF normalization,
scope/effect/proof analysis, and defunctionalization.

The Core AST sketches below are projection shapes, not permission for
surface-specific direct flat-step lowerers. For promoted routes, construct
classes covered by WCC must elaborate to WCC first. Direct schema-1/per-form
lowerers are legacy compatibility or characterization paths only.

## 50. `defworkflow` Elaboration

Source:

```lisp
(defworkflow implementation/run
  ((ctx PhaseCtx)
   (inputs ImplementationInputs)
   (providers ImplementationProviders))
  -> ImplementationResult
  body)
```

WCC and Core projection:

```text
defworkflow boundary
  -> WCC module/function boundary
  -> defunctionalized CoreWorkflow
  inputs:
    ctx fields as structured inputs or flattened inputs
    inputs fields
    providers fields
  outputs:
    union discriminant
    union fields by variant
  statements:
    lowered body
```

Semantic IR:

```text
SemanticWorkflow
  typed input signature
  typed output union
  workflow call entrypoint
  effect summary
```

## 51. `defproc` Elaboration

A `defproc` elaborates to a WCC function after import expansion,
specialization, and typechecking. The compiler may project it as inline WCC or
as a private workflow boundary before Core AST generation.

Inline projection:

- required for workflow-to-procedure migrations;
- use when the caller owns runtime state, checkpoint, resume, and debug
  identity; and
- preserve procedure-definition, specialization/ProcRef, and call-site source
  provenance on generated nodes.

Private subworkflow projection:

- use only when migration contract/evidence identifies a private state
  namespace or independently useful private resume/debug boundary;
- keep the boundary internal and deterministic; and
- do not replace a public workflow invocation or publication boundary.

The current slice records that namespace need as reviewed evidence, not a new
source annotation. `auto` may choose either projection only when that choice is identity-free. It
does not promise stable persisted routing. Reuse count and body size may inform
compiler cost decisions but do not by themselves justify a private identity.

Generated private names are deterministic:

```text
%neurips.implementation.ensure-approved-plan.v1
```

Source maps point back to the original `defproc`.
Imported private-subworkflow projections elaborate against the defining
module's type environment. Specialized procedures use the defining module's
environment for free-name resolution and extend it with specializing-unit
concrete bindings for type arguments, ProcRefs, and values.

After those bindings resolve, the accepted effect-validation route must
recompute the specialized helper's caller-visible transitive effects before
either projection is chosen. The chosen projection must preserve public-wrapper
outputs, artifacts, publication ownership, state layout, checkpoint identity,
and resume behavior.

## 52. `call` Elaboration

Source:

```lisp
(call implementation/run
  :ctx implementation-ctx
  :inputs implementation-inputs
  :providers providers.implementation)
```

WCC and Core projection:

```text
perform workflow call
  -> CoreCallStep
  callee: implementation/run
  args:
    ctx: ...
    inputs: ...
    providers: ...
  expected_return: ImplementationResult
```

Validation:

- same target DSL version
- argument contract compatibility
- provider ref compatibility
- workflow ref known
- return type bound

## 53. `match` Elaboration

Source:

```lisp
(match result
  ((COMPLETED c) ...)
  ((BLOCKED b) ...))
```

WCC and Core projection:

```text
case result.variant
  join branch exits
  -> CoreMatch or defunctionalized routing equivalent
  discriminant_ref: result.variant
  arms:
    COMPLETED:
      proof_context: result == COMPLETED
      statements: ...
    BLOCKED:
      proof_context: result == BLOCKED
      statements: ...
```

Semantic IR:

- `ProofContext` entered for branch
- `VariantArtifactEntry` availability narrowed
- runtime `requires_variant` guard retained

## 54. `provider-result` Elaboration

Source:

```lisp
(provider-result providers.execute
  :ctx ctx
  :prompt prompts.implementation.execute
  :inputs (inputs.design inputs.plan)
  :model inputs.model
  :effort inputs.effort
  :timeout-sec 7200
  :prompt-dependencies
    (:required (inputs.design inputs.plan)
     :optional (inputs.prior-review)
     :position prepend)
  :returns ImplementationAttempt)
```

WCC and Core projection:

```text
perform provider call :effect provider_call
  -> CoreProviderStep
  provider: providers.execute
  prompt: prompts.implementation.execute
  provider_call_policy: {model: inputs.model, effort: inputs.effort}
  timeout_sec: 7200
  depends_on: required/optional content injection from typed bindings
  compiler_prompt_dependency_contract: typed side-table entry
  prompt_contract: generated from ImplementationAttempt
  output_bundle: generated canonical bundle
  variant_output: generated if return type is union
```

Semantic IR:

```text
SemanticProviderResult
  VariantContract(ImplementationAttempt)
  PromptContract(...)
  CompilerPromptDependencyContract(...)
  AtomicBundleValidation(...)
```

For a target-2.20 fragment application, the same provider step additionally
carries the validated `CompilerPromptFragmentContract` and exact
`compiled_prompt_fragment_identity`. Document fills lower through the
`workflow_lisp_prompt_fragment` dependency origin; rendered fills remain in the
compiler fragment contract. Classic and WCC/schema-2 lowering must produce the
same normalized contract, result contract, and identity.

## 54.1 `with-live-providers` Elaboration (Target 2.16)

Source:

```lisp
(with-live-providers
  ((worker (run-worker request))
   (supervisor (run-supervisor policy)
     :observes worker))
  worker)
```

The form has exactly two bindings and one sibling `:observes` edge. The
observed member is the worker; its peer is the supervisor. The worker returns
any transportable type `T`, the supervisor returns the compiler-owned
non-shadowable `ProviderSteeringDirective`, and the settlement body is a pure
expression over both values whose type is the form's result type.

A member is eligible only when post-specialization recursive expansion of
direct `:lowering inline` procedure calls yields one straight-line region with
exactly one unconditional provider perform and a pure result projection.
Residual calls, workflow boundaries, branches, loops, a second perform, or
other effects reject with source-mapped diagnostics.

WCC elaboration produces one closed `WccProviderSupervision` term and records
the member provider effects plus
`LiveSupervisionEffect(supervisor, worker)`. Defunctionalization emits one
generated Core provider-supervision statement. Shared validation requires the
worker provider template's structural `turn_boundary_resume` capability; the
supervisor needs no session capability.

Semantic and executable projection preserve the two members, observation edge,
directive contract, pure settlement contract, source ownership, and one
atomic workflow-state/result boundary. Member provisional bundles, panes, and
transcripts are invocation evidence. Only the selected validated worker value
and directive enter settlement, and only the validated settlement value is the
node result.

## 54.2 `with-live-provider-peers` Elaboration (Target 2.17)

Source:

```lisp
(with-live-provider-peers
  ((planner
     (provider-result providers.planner
       :prompt prompts.planner
       :inputs ()
       :timeout-sec 300
       :returns String))
   (reviewer
     (provider-result providers.reviewer
       :prompt prompts.reviewer
       :inputs ()
       :timeout-sec 300
       :returns Bool))
   (builder
     (provider-result providers.builder
       :prompt prompts.builder
       :inputs ()
       :timeout-sec 300
       :returns String)))
  (record TeamResult
    :plan planner
    :approved reviewer
    :notes builder))
```

The literal binding list contains two through eight unique members in authored
order. Each binding has only a name and provider-producing expression: there
is no `:observes`, role, access-control, or dynamic-membership spelling.
Every member may address every other member by binding name, while self-send
is rejected. A member expression cannot capture a sibling result.

After recursive specialization of direct `:lowering inline` procedures, each
member must close to exactly one unconditional provider perform followed only
by a pure result projection. Residual calls, workflow boundaries, branches,
loops, extra effects, or a second provider perform reject with source-mapped
diagnostics.

Member results and the settlement result may use any declared transportable
type. The form imposes no peer-specific nominal wrapper: an author may use
ordinary scalar, collection, record, or union contracts and narrow them only
when the workflow needs stronger guarantees. The settlement body is a pure
expression over exactly the authored member bindings, and its type is the
form's result type.

WCC elaboration produces one closed `WccProviderPeerGroup`, preserving authored
member order, each member's provider effects, and
`LivePeerMessagingEffect(members=<authored-order ids>)`. It does not produce
`LiveSupervisionEffect`. Defunctionalization emits one compiler-generated Core
peer-group statement and one `provider_peer_group.v1` executable node. The
closed config preserves the member provider/result contracts, pure settlement
payload and contract, `all_other_members` policy, required
`interactive_terminal_turn_queue.v1` capability, generated paths, source
ownership, positive timeouts, and `max_steers: 0`.

At runtime every member has one attempt-bound opaque endpoint credential.
`peer-ready` forms an all-member barrier; accepted `peer-send` requests are
fsynced into the exact receiver attempt's ledger before input is offered;
`peer-ack` records the receiver's exact message-id acknowledgement; and
`peer-finish` freezes the validated member bundle before the declared natural
close is offered. Only after every member proves natural termination does the
coordinator evaluate and atomically publish the pure settlement.

The endpoint and client handles are ephemeral runtime values. Message content,
pane text, transcripts, member provisional bundles, and message ledgers do not
become workflow values or alternate result authorities. An interrupted
nonterminal visit is at-least-once: after exact-visit integrity validation,
ordinary resume preserves partial ledgers as audit-only evidence, discards the
partial result authority, emits exactly one
`provider_attempt_interrupted_rerun`, and enters a fresh group visit through
ordinary dispatch. Messages are never retargeted, and member sessions,
attempts, endpoints, panes, bundles, and settlements from the interrupted
visit are never reused. Missing, malformed, conflicting, or ambiguous
authoritative recovery state fails closed before provider launch; compatible
completed-group reuse remains invocation-free.

Targets below `2.17` reject `with-live-provider-peers`. Target `2.17` continues
to accept the target-`2.16` `with-live-providers` form without changing its
`provider_supervision.v1` lowering.

## 55. `produce-one-of` Elaboration

Source:

```lisp
(produce-one-of ImplementationAttempt
  :ctx ctx
  :producer ...
  :candidates ...)
```

WCC and Core projection:

```text
perform snapshot
perform producer
perform select-variant-output
  -> CorePreSnapshot
  -> CoreProducerStep
  -> CoreSelectVariantOutput
```

Semantic IR:

- `SnapshotEntry`
- `SnapshotDiffEvidence`
- `VariantSelection`
- `AtomicBundleWriter`

This aligns with the v2.14 selection model: snapshot evidence, exactly-one
changed candidate, validation before commit, and artifacts exposed only after
successful commit.

## 56. `resource-transition` Elaboration

Compatibility lowering A: certified command adapter.

```text
perform certified adapter transition
  -> CoreCommandStep
  -> CoreOutputBundle
  -> CorePublish
```

Declared-transition lowering B: generated runtime-native transition.

```text
perform runtime-native resource transition
  -> compiler-generated resource_transition step
  -> CoreResourceTransitionStep
  -> ExecutableNodeKind.RESOURCE_TRANSITION
```

Rule:

If the form promises atomic move + ledger update, the selected backend must
actually provide that property.

If only a command adapter exists, the language must say:

```text
atomicity is adapter-certified and fixture-tested
```

not pretend it is a core runtime transaction.

For the declared runtime-native route, the runtime must own transition schema
validation, version checks, idempotency, audit append, and replay semantics.

## 57. `review-revise-loop` Elaboration Contract

Source:

```lisp
(review-revise-loop implementation-review ...)
```

The stdlib definition must compile through ordinary imported/std `.orc` into
WCC. After specialization and WCC analysis, defunctionalization may project a
Core AST shape equivalent to:

```text
loop/recur or bounded rec-join
  -> CoreRepeatUntil or equivalent defunctionalized routing
  iteration state
  call specialized review ProcRef
  match decision
  optional call specialized fix ProcRef
  final projection to stdlib-owned terminal result
```

Semantic IR must expose:

- `BoundedLoop`
- stdlib-owned `ReviewDecision`
- stdlib-owned `ReviewLoopResult`
- effects of the selected review/fix procedures
- artifact refs by branch

The generated monomorphic helper uses ordinary loop state. A conceptual
loop-frame contains the current completed value, latest review report, latest
findings, optional blocker class, optional reason, iteration count, and a scalar
decision marker. After specialization all fields are concrete; no type
parameter or ProcRef may remain in lowered state.

Review decisions elaborate through ordinary proof-gated `match` / WCC `case`:

- `APPROVE` materializes the current completed value, review report, findings,
  and terminal decision marker.
- `REVISE` calls the specialized fix ProcRef, materializes its returned
  completed value plus the review report/findings, and continues.
- `BLOCKED` materializes the current completed value, review report, findings,
  blocker class, and terminal decision marker.
- max-iteration exhaustion uses the authored loop exhaustion projection to set
  an `EXHAUSTED` marker and then constructs `ReviewLoopResult.EXHAUSTED` from
  the final loop-frame outputs.

The final projection must read loop-frame outputs. It must not read only the
first review step or a body-local step that was not materialized onto the loop
frame.

Promoted elaboration must not depend on `ReviewReviseLoopExpr`, a lowerer branch
keyed to literal `review-revise-loop`, or review-loop-specific Python
construction of terminal variants. Legacy bridge fixtures, if any remain, must
be explicitly marked legacy.

## 58. `backlog-drain` Elaboration

Source:

```lisp
(backlog-drain neurips
  :selector selector/run
  :run-item selected-item/run
  :gap-drafter gap/draft
  :ctx ctx
  :max-iterations max)
```

WCC and Core projection:

```text
loop/recur or bounded rec-join
  -> CoreRepeatUntil or defunctionalized routing equivalent
  call selector
  match SelectionResult
    EMPTY -> done
    GAP -> call gap_drafter, continue
    SELECTED -> call run_item, match SelectedItemResult
```

Semantic IR:

- loop state type
- `WorkflowRef` signatures
- `DrainResult` union
- effect summary

## Part XV. Example End-To-End Design

## 88. Types

```lisp
(defmodule neurips/types
  (:language workflow-lisp "0.1")
  (:target-dsl "2.14")

  (import std/paths :as path)
  (import std/phase :as phase)

  (defenum BlockerClass
    missing_resource
    unavailable_hardware
    roadmap_conflict
    external_dependency_outside_authority
    user_decision_required
    unrecoverable_after_fix_attempt)

  (defrecord Blocker
    (class BlockerClass)
    (reason String)
    (retryable Bool)
    (owner Optional[String]))

  (defrecord ImplementationInputs
    (design path/design)
    (plan path/plan)
    (check-commands path/check-commands)
    (execution-report-target path/work-report-target)
    (checks-report-target path/checks-report-target)
    (review-report-target path/review-report-target))

  (defrecord ImplementationProviders
    (execute Provider)
    (review Provider)
    (fix Provider))

  (defunion ImplementationAttempt
    (COMPLETED
      (execution-report path/work-report))

    (BLOCKED
      (progress-report path/work-report)
      (blocker Blocker)))

  (defunion ImplementationResult
    (APPROVED
      (execution-report path/work-report)
      (review_report path/review-report)
      (findings phase/ReviewFindings))

    (EXECUTION_BLOCKED
      (progress-report path/work-report)
      (blocker Blocker))

    (REVIEW_BLOCKED
      (execution-report path/work-report)
      (review_report path/review-report)
      (blocker_class BlockerClass)
      (findings phase/ReviewFindings))

    (EXHAUSTED
      (execution-report path/work-report)
      (last_review_report path/review-report)
      (findings phase/ReviewFindings)
      (reason String))))
```

## 89. Implementation Phase

```lisp
(defmodule neurips/implementation
  (:language workflow-lisp "0.1")
  (:target-dsl "2.14")

  (import std/context :as ctx)
  (import std/phase :as phase)
  (import std/provider :as provider)
  (import neurips/types :as nt)

  (export run)

  (defworkflow run
    ((phase-ctx ctx/PhaseCtx)
     (inputs nt/ImplementationInputs)
     (providers nt/ImplementationProviders))
    -> nt/ImplementationResult

    :effects
      ((reads inputs.design inputs.plan inputs.check-commands)
       (uses-provider providers.execute providers.review providers.fix)
       (writes inputs.execution-report-target
               inputs.checks-report-target
               inputs.review-report-target)
       (updates-state phase-ctx))

    (phase/with-phase phase-ctx implementation
      (let* ((attempt
               (provider/provider-result providers.execute
                 :ctx phase-ctx
                 :prompt prompts.implementation.execute
                 :inputs
                   (inputs.design
                    inputs.plan
                    inputs.execution-report-target)
                 :returns nt/ImplementationAttempt
                 :artifacts
                   ((COMPLETED
                      (execution-report
                        :target inputs.execution-report-target
                        :format markdown))

                    (BLOCKED
                      (progress-report
                        :target (phase/target phase-ctx 'progress-report)
                        :format markdown)))))

             (result
               (match attempt
                 ((COMPLETED completed)
                  (match
                    (phase/review-revise-loop implementation-review
                      :ctx phase-ctx
                      :completed completed
                      :inputs inputs
                      :review (proc-ref implementation-review)
                      :fix (proc-ref implementation-fix)
                      :max 40)

                    ((APPROVED approved)
                     (nt/ImplementationResult.APPROVED
                       :execution-report completed.execution-report
                       :review_report approved.review_report
                       :findings approved.findings))

                    ((BLOCKED blocked)
                     (nt/ImplementationResult.REVIEW_BLOCKED
                       :execution-report completed.execution-report
                       :review_report blocked.review_report
                       :blocker_class blocked.blocker_class
                       :findings blocked.findings))

                    ((EXHAUSTED exhausted)
                     (nt/ImplementationResult.EXHAUSTED
                       :execution-report completed.execution-report
                       :last_review_report exhausted.last_review_report
                       :findings exhausted.findings
                       :reason exhausted.reason))))

                 ((BLOCKED blocked)
                  (nt/ImplementationResult.EXECUTION_BLOCKED
                    :progress-report blocked.progress-report
                    :blocker blocked.blocker)))))

        result))))
```

Notes:

- the stdlib loop returns `phase/ReviewLoopResult`; workflow-specific terminal
  unions are projected by caller code with an ordinary `match` using
  refined match binders
- no manual state path
- no markdown extraction
- no explicit snapshot name
- no candidate-path bookkeeping
- no manual `requires_variant`
- no pointer file authority

## 90. Selected Item Workflow

```lisp
(defworkflow run-selected-item
  ((item-ctx ItemCtx)
   (selection SelectionInput)
   (providers NeuripsProviders))
  -> SelectedItemResult

  (let* ((selected
           (resolve-selected-item item-ctx selection))

         (queue-transition
           (resource-transition backlog-item
             :ctx item-ctx
             :when selected.active?
             :resource selected.item
             :from Queue.active
             :to Queue.in-progress
             :ledger item-ctx.ledger
             :event SELECTED))

         (roadmap
           (call roadmap/sync
             :ctx (phase-ctx item-ctx 'roadmap-sync)
             :selected selected
             :providers providers.roadmap))

         (plan
           (resume-or-start plan-gate
             :ctx (phase-ctx item-ctx 'plan)
             :resume-from selected.final-plan-gate-state
             :valid-when APPROVED
             :start
               (call plan/run
                 :ctx (phase-ctx item-ctx 'plan)
                 :selected selected
                 :roadmap roadmap
                 :providers providers.plan)
             :returns PlanGateResult))

         (implementation
           (call implementation/run
             :ctx (phase-ctx item-ctx 'implementation)
             :inputs (make-implementation-inputs item-ctx selected plan)
             :providers providers.implementation)))

    (finalize-selected-item
      :ctx item-ctx
      :selected selected
      :queue-transition queue-transition
      :roadmap roadmap
      :plan plan
      :implementation implementation)))
```

## 91. Top-Level Drain

```lisp
(defworkflow drain
  ((ctx DrainCtx)
   (providers NeuripsProviders)
   (max-iterations Int))
  -> DrainResult

  (backlog-drain neurips
    :ctx ctx
    :selector selector/run
    :run-item selected-item/run
    :gap-drafter gap/draft
    :providers providers
    :max-iterations max-iterations))
```

This is the kind of compression that could genuinely improve composability and
size.

## Part XVIII. Implementation Staging

These stages are retained as provenance for the frontend rollout. They are not
the current compiler-lane roadmap where they conflict with WCC. The current
compiler substrate is WCC/schema 2 for the migrated M0-M5 route subset;
legacy schema 1 is a predecessor compiler identity, and the flat executor and
historical-run resume are retired (§44.1, §78).

WCC compiler-lane work is governed by this baseline plus the component
contracts it routes to: private executable context, typed projection,
certified adapters/resource transitions, parent-callable family parity,
promotion evidence, and post-promotion simplification.

## 99. Stage 1: Frontend Core Without Workflow Execution

Implement:

- parser
- syntax objects
- modules
- imports/exports
- `defenum`
- `defpath`
- `defrecord`
- `defunion`
- `defun`
- basic type checking

No effects yet.

## 100. Stage 2: Procedural Substrate

Implement:

- `defworkflow`
- `defproc`
- `call`
- `let*`
- `match`
- effect signatures
- source maps
- WCC elaboration and Core AST projection

A trivial workflow should compile to core AST and semantic IR.

## 101. Stage 3: Macro System

Implement:

- `defmacro`
- hygiene
- macro expansion frames
- macro determinism checks
- macro error mapping

Keep macros small initially.

## 102. Stage 4: Provider/Command Structured Results

Implement:

- `provider-result`
- `command-result`
- structured bundles
- union return types
- prompt contract generation
- variant output lowering

No markdown extraction.

## 103. Stage 5: Phase And Context Library

Implement:

- `PhaseCtx`
- `with-phase`
- `phase-target`
- `run-provider-phase`
- `produce-one-of`
- `review-revise-loop`
- `resume-or-start`

Review/revise route:

- promoted `review-revise-loop` is implemented as a stdlib-owned macro/generic
  procedure route that lowers through ordinary typed forms;
- the promoted route uses exact stdlib-owned `ReviewDecision`,
  `ReviewFindings`, and `ReviewLoopResult`;
- review/fix hooks are compile-time ProcRefs;
- old compiler-special review-loop expression and stdlib-specialization bridge
  types are not part of the promoted expression table;
- any residual review-loop-specific helpers are compatibility/quarantine
  surfaces, not the semantic route.

## 104. Stage 6: Resource And Drain Library

Implement:

- `resource-transition`
- `finalize-selected-item`
- `backlog-drain`
- workflow refs
- `loop/recur`

Semantically critical `resource-transition` behavior lowers to the
runtime-native declared transition backend. Certified adapters remain explicit
compatibility backends when they implement the same typed transition contract.

## 105. Stage 7: NeurIPS Migration Experiment

Translate:

- implementation phase
- plan phase
- selected item
- top-level drain

Measure:

- LOC reduction
- gate-pattern reduction
- manual-state reduction
- manual-pointer reduction
- semantic equivalence

Reject the frontend design if translations remain YAML-shaped.

Baseline note: the WCC M0-M5 route supersedes the direct Core-AST
compiler-substrate interpretation of these stages. Migrated-route evidence
identifies the lowering route and schema version; promoted work uses
`wcc_default`/schema 2 as the current compiler guidance.

Promotion of YAML primaries was separate from implementation of frontend
capability: a `.orc` candidate needed machine-computed non-regressive parity
evidence before replacing a YAML primary, even if the candidate compiled,
validated, and dry-ran. The YAML frontend and that gate are retired (§78.1).

## 105.1 Runtime Migration Foundation Contract

Promotion-grade Workflow Lisp composition relies on these runtime-foundation
contracts:

- command structured-output conformance;
- frontend-lowered typed value transport;
- provider structured-output target binding;
- strict migration promotion gates;
- `StateLayout` / `PathAllocator` ownership for generated private paths;
- prompt extern source semantics;
- canonical `resume-or-start` proof alignment for compatibility paths that
  traverse reusable-state recovery.

Generic provider-heavy `.orc` workflows are valid promotion evidence only when
these contracts are satisfied by the exercised runtime path.

## 105.2 Post-Foundation Composition And Stdlib Migration

Composition and stdlib migration requires:

1. inventory the implemented composition and stdlib route;
2. harden generic effectful composition;
3. harden imported/std `.orc` reuse;
4. prove `review-revise-loop` through the ordinary stdlib route with no
   promoted compiler-name special case;
5. add entrypoint bootstrap/defaults so wrappers match YAML public boundaries;
6. keep canonical `resume-or-start` validation typed and parity-testable;
7. inventory adapter lint debt before strict enforcement;
8. use `--require-non-regressive` for evidence and `--require-promotable` for
   any primary-surface decision (retired gate flags, §78.1).

## 105.3 Native Transportable Returns And Typed Result Guidance

Wave 1 (native transportable returns) is landed: `defworkflow`, effectful
`defproc`, `provider-result`, `command-result`, and workflow calls share one
`is_transportable_result_type` decision instead of separate record/union
allowlists. Every currently transportable type (`String`, `Int`, `Float`,
`Bool`, enums, declared path refinements, `Optional[T]`, `List[T]`,
`Map[String, T]`, records, and unions) is valid in every return position.

A non-record/non-union ("root") result lowers to one generated
`output_bundle` field named `__result__` with `json_pointer: ""`; the
provider or command writes the direct JSON value, not an object wrapper.
Authored Workflow Lisp never names or projects `__result__`; the compiler
binds the validated artifact directly as the declared type. A reusable
workflow boundary declares exactly one generated output named `__result__`
for a root-valued return, and `call` carries it through the outer call-step
artifacts unchanged.

DSL v2.15 is the public wire version for this widened contract. Ordinary
loader entrypoints and Workflow Lisp shared validation accept it uniformly.
v2.14 authored YAML and existing record/union `.orc` programs are unaffected
and remain non-regressive.

Full contract, wire schema, and verification strategy:
[Workflow Lisp Native Transportable Returns And Typed Result Guidance](../../design/workflow_lisp_native_transportable_returns.md).
Typed result guidance is implemented. Plain returns remain canonical; an
annotated occurrence uses `(result T :description ... :format-hint ...
:example <pure-constant>)`, and record/union payload fields accept the same
three optional keys. Examples are typed pure constants; path examples enforce
path safety but not target existence. Composition preserves metadata without
including it in type or specialization identity.

Effect boundaries lower guidance into v2.15 bundle `guidance`, direct field
keys, ordered ancestor `guidance_context`, and discriminant-ordered
`guidance_by_variant`. Overall callable/workflow return guidance lowers once
to top-level `result_guidance` and survives Surface, Core, Semantic, and
Executable IR. It is not injected into provider prompts and does not change
outputs, runtime plans, value validation, fingerprints, checkpoints, or
resume.

Target 2.19 additionally implements exact opaque `Value` on the same shared
transport path. It does not widen or alias `Json`, records, unions, or any
other concrete type. Direct results retain the sole `__result__` / empty
JSON-pointer carriage with `type: value`; public boundaries use
`kind: value`. Classic and WCC lowering, state/report projection, checkpoint
identity, and resume preserve the declared type and recursively validated
strict-JSON payload. `Value` guidance permits description and format hint but
not an example. DSL 2.18 and earlier reject the source type and `value`
contract descriptor, while all v2.15 narrower-return and guidance behavior is
unchanged.

## 105.4 Procedure-First Reuse And Migration

Workflows are durable public run/resume/invocation/publication boundaries.
Typed procedures are the normal internal reuse unit. A workflow-to-procedure
migration keeps a public `defworkflow` wrapper and passes all of these tests:

The resolved-effect substrate is implemented:
`TypedProcedureDef.direct_effect_summary` retains the body-local view,
`transitive_effect_summary` is recomputed after generic/ProcRef
specialization, and lowering/Semantic IR consume the resolved caller-visible
view. Stage 3 owns resolved procedure lowering modes and generated names. A
pilot still must pass the family-specific effect, identity, runtime, parity,
and review gates below, and it may not depend on the classic schema-1
iteration-scope lowering override.

1. the callee owns no independently required external invocation, run/resume,
   publication, public output, or operator-visible identity;
2. its typed signature and every direct/transitive effect are supported on the
   procedure route;
3. migrated definitions and calls select `:lowering inline` explicitly;
4. specialization resolves type parameters and ProcRefs and recomputes the
   caller-visible transitive effect summary before lowering;
5. production WCC lowering and shared validation pass without a consumer-name
   special case; and
6. computed before/after evidence preserves public inputs/outputs, terminal
   outcomes, artifacts/publications, source maps, state/write roots,
   checkpoint identities, and resume/reuse behavior.

Persisted identity is strict-compatible by default. A mismatch stops the
migration unless a separately reviewed general atomic upgrader applies or the
accepted reviewed internal identity-retirement class applies; that evidence-
only exception is unavailable to public/exported callees, promoted/live routes,
or supported old-identity consumers. All other comparison axes above remain
unconditional, and no retirement record remaps old state. See
[Procedure-Migration Identity Compatibility](../../design/workflow_lisp_procedure_migration_identity_compatibility.md).

Compilation or dry-run alone is not promotion evidence. Keep a workflow when
it is externally run or resumed, is an independently addressable child
workflow, owns public publication/output lifecycle, requires a stable
independent checkpoint namespace without an accepted remap, or uses an
unproven procedure effect boundary. `:lowering private-workflow` is available
only when migration contract/evidence identifies a private
state/resume/debug namespace and does not turn a public boundary into an
internal one. That need is review evidence in the current slice, not a new
source annotation.

Detailed rationale, feasibility cases, and verification requirements:
[Workflow Lisp Procedure-First Reuse Contract](../../design/workflow_lisp_procedure_first_reuse_contract.md).

## 105.5 Provider Live Binding

The target-2.16 v1 surface is implemented as the bounded
`with-live-providers` form described in Section 54.1. Its shipped boundary is:

- exactly one worker and one supervisor;
- exactly one supervisor-to-worker observation edge;
- provider members that normalize to one unconditional provider effect plus a
  pure projection;
- the reserved `ProviderSteeringDirective` with `CONTINUE` and one bounded
  `STEER` correction;
- structural worker `turn_boundary_resume` eligibility;
- a pure settlement expression; and
- one `provider_supervision.v1` executable node and atomic result commit.

Observation panes are process-local views. Provider transport and validated
member bundles remain authoritative; pane bytes, transcripts, live targets,
and unselected provisional bundles never become workflow values or result
channels. Compatible completed groups remain invocation-free. After
exact-visit integrity validation, ordinary resume discards an interrupted
group's partial result authority, emits exactly one
`provider_attempt_interrupted_rerun`, and enters a fresh group through
ordinary dispatch. It never resumes interrupted member sessions or retargets
messages, and missing, malformed, conflicting, or ambiguous authoritative
recovery state fails closed before provider launch.

Target `2.17` implements the separate
`with-live-provider-peers` surface described in Section 54.2 and
`workflow_lisp_provider_peer_messaging.md`:

- a literal authored-order group of two through eight members;
- one eligible provider region and any transportable result type per member;
- the structural `interactive_terminal_turn_queue.v1` provider capability;
- exact-attempt ready/send/ack/finish through a runtime-owned endpoint;
- receiver-ledger record-before-offer ordering;
- cooperative natural close; and
- one pure atomic settlement through `provider_peer_group.v1`.

The v1.1 group has no observation or forcing edge and cannot use `STEER`,
cancel, resume, replace, or separately settle a member. Same-turn or
unrecorded raw-pane steering, dynamic membership, mixed peer-plus-STEER, and
cross-run messaging remain outside the language contract. Target `2.16` and
its `provider_supervision.v1` artifacts and behavior are unchanged.

## 105.6 Prompt Core

Target 2.20 implements the bounded Q1 prompt core described in Sections 8.7.1,
22.6, and 54. It includes import/export resolution for `defprompt`, fully
applied named fills, closed kind/refinement checking, deterministic renderer
selection, prompt-owned returns, classic/WCC parity, exact compiled-fragment
identity carriage, runtime rendering through the existing prompt composer,
schema-2.1 fragment snapshots, and compatible completed-boundary resume.

The migrated `review-design-docs` review call is the current real consumer.
Its fix call remains extern-backed. Q2 output positions and Q3
prompt-attempt identity/diagnostics are implemented. Q3 adds no authored
syntax beyond selecting target 2.22 for the direct fragment-backed call. Q4
judgment views remain a separate successor tranche.

## 105.7 Implemented Prompt Output Positions

Q2's independently reviewed design-amendment and implementation-plan gates are
closed. Its minimum target is 2.21 and target-2.20 Q1 output remains
byte-for-byte unchanged. The bounded `:path :out` syntax is available for
authoring and is reflected in the capability/routing docs.

Implementation evidence includes parser/type/diagnostic negatives; classic
and WCC parity through Semantic and Executable IR; exact Q1 v1 and Q2 v2
identity tests; exact Q1 v1 carrier serialization plus v2
carrier/`expected_outputs` pair tests; generic paired-contract admission,
ordering, name-disjointness, and atomic failure tests; exact binding-ref/literal
path derivation and rendered/resolved equality; pre-launch pairwise and
structured-bundle destination-alias rejection; both-direction runtime checks
for missing file versus invalid bundle; checkpoint/resume reuse and drift
checks; and a real `review-design-docs` E2E. The E2E must show one authored
target fill drives both prompt rendering and the required-file postcondition
without weakening the prompt-owned `ReviewDecision`.

## 105.8 Implemented Prompt-Attempt Identity And Diagnostics

Q3 is implemented at target 2.22 through the exact carrier/binding-plan
carriage, one-render fragment and typed-evidence reuse, pure closed roles and
comparison, functional-v2/preparation-failure evidence, prelaunch publication,
and allocator-derived JSON/Markdown reporting described in Sections 8.7.3 and
22.8. Deterministic retry evidence proves independent input, dependency,
runtime-contribution, and provider-policy drift in fixed order; target-2.20 and
2.21 controls preserve their execution bytes and project validated v1 evidence
as `legacy_snapshot`. The surface remains direct-fragment-only and
non-authoritative.

## 105.9 Implemented Phased Contract Delivery

Q5 is implemented at target 2.23 through the exact call-policy carriage,
single-render `T1 || T2 == C` cut, deadline-aware interactive adapter,
attempt-bound submit endpoint, bounded materialization-only correction,
joint Q2 validation, immutable candidate freezing, natural shutdown, and
atomic publication described in Sections 8.7.4 and 22.9.

Attempt identity v2 and functional evidence v3 distinguish canonical
composition from exact actual deliveries. The canonical phase ledger,
candidate manifests, total diagnostics, and report-v2 projection are
content-free and non-authoritative. Omitted/explicit composed calls retain
their ordinary path and Q3 v1/v2 evidence; target-2.17 peer behavior is
unchanged. The migrated `review-design-docs` consumer and its real-provider
invalid-then-valid run prove one-client correction without pane-text
authority, cancellation, or a provider-session resume command.

## 105.10 Implemented Durable Host Input

Historical (target 2.32): the syntax/type contract below is retained;
`request-input` execution and `input answer`/`cancel` settlement are retired
(see the header note and [CLI](../../../specs/cli.md)).

Target 2.32 reserves `(request-input question)`, one exact-`String` operand,
and the closed builtin `HumanReply` union. The operation has one inferred
`host-input` effect; procedures declaring effects write `:effects
((host-input))`. A question may be literal, a typed reference, or a supported
computed expression whose ordinary prefixes have completed before the atomic
request leaf. The compiled leaf carries exactly one `request_input.question`
literal/ref source, while the fixed result contract supplies only `ANSWERED`
with `text: String` or `CANCELLED`. It has no provider options, prompt
interpolation, output bundle, per-call descriptor, or second result carrier.

At dispatch, the runtime creates at most one root-owned request, preserves the
reached call/loop cursor and visit, and marks only the aggregate root
`suspended`. Child frames remain ordinary incomplete frames. The host records
an exact answer or cancellation through the single durable API; that operation
does not execute the workflow. An unanswered resume stays suspended. An
answered resume checks the original scope, runtime node, visit, loop placement,
and complete reply before atomically publishing the ordinary result/dataflow
and marking the request consumed. Existing completed-effect replay may reuse
only the exact validated `HumanReply` boundary.

This is deliberately one durable host interaction, not native provider-session
resume, arbitrary continuation serialization, a second request store, or a
polling/event framework. Source targets through 2.31 reject the form. The
closed graph carries reachable request-input nodes in v6; unaffected graphs and
state retain their earlier version and bytes.

## Final Design Center

The Lisp frontend should be a typed procedural workflow language over the
existing deterministic runtime.

The minimal acceptable architecture is:

- `defmodule`
- `defenum` / `defpath` / `defrecord` / `defunion`
- `defun`
- `defmacro`
- `defproc`
- `defworkflow`
- `call`
- `let*`
- `match`
- `with-live-providers`
- `with-live-provider-peers`
- effect signatures
- source maps
- WCC elaboration and Core AST projection
- shared validation
- semantic IR

The minimal acceptable standard library is:

- `provider-result`
- `command-result`
- `run-provider-phase`
- `review-revise-loop`
- `resume-or-start`
- `resource-transition`
- `finalize-selected-item`
- `backlog-drain`

The non-negotiable semantic rules are:

- structured bundles are authority
- reports are views
- artifact values are authority
- pointer files are representations
- freshness uses snapshot evidence, not mtime
- variant refs require proof
- macros cannot hide effects
- the frontend targets core AST / semantic IR, not YAML

That is the difference between a cosmetic Lisp frontend and a language that can
actually improve composability, size, reusability, and modularity.
