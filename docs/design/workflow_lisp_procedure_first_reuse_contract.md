# Workflow Lisp Procedure-First Reuse Contract

- **Status:** accepted
- **Kind:** frontend architecture decision and migration contract
- **Owner:** Workflow Lisp frontend specification
- **Reviewers:** Stage 4 specification and quality review
- **Created:** 2026-07-13
- **Last material update:** 2026-07-13
- **Related docs:**
  - `docs/design/workflow_lisp_frontend_specification.md`
  - `docs/design/workflow_lisp_parametric_type_system.md`
  - `docs/design/workflow_lisp_proc_refs_partial_application.md`
  - `docs/design/workflow_lisp_native_transportable_returns.md`
  - `docs/design/workflow_lisp_effect_graph.md`
  - `docs/design/workflow_lisp_state_layout.md`
  - `docs/design/workflow_lisp_source_map.md`
  - `docs/design/workflow_lisp_key_migration_parity_architecture.md`
  - `docs/design/workflow_lisp_procedure_migration_identity_compatibility.md`
  - `docs/plans/2026-07-13-procedure-first-stage4-design-and-planning.md`
- **Implementation target:** independently reviewed substrate, pilot, and
  migration-wave plans selected by the procedure-first roadmap

## Summary

Workflow Lisp uses workflows as durable public run, resume, invocation, and
publication boundaries. Typed procedures are the normal unit for reusable
internal behavior. Both use the same typed return model, but they do not have
the same operational identity.

Procedure lowering is a role-based hybrid. A workflow-to-procedure migration
uses explicit `:lowering inline` so the retained public workflow owns the
runtime route. `:lowering private-workflow` is reserved for a private state,
resume, or debug namespace need recorded in migration evidence. The
`:lowering auto` mode remains compatible for
identity-free helpers, but its compiler-selected route is not a persisted
identity promise.

Procedure composition is statically resolved. Direct body effects and
caller-visible transitive effects are distinct, and the compiler recomputes
the transitive summary after generic specialization and ProcRef resolution.
No runtime procedure values, closures, dynamic dispatch, hidden effects, or
implicit publication are introduced.

That effect split is an accepted semantic target, not a claim about today's
carrier fields. The current `procedure_typecheck.direct_effects` carrier
conservatively includes callee transitive effects. A dedicated Stage 5
substrate change must represent or derive the body-local direct view and
recompute the transitive view after specialization before the pilot may start.

## Context And Authority

The parent
[Workflow Lisp Frontend Specification](workflow_lisp_frontend_specification.md)
owns the durable source-language contract. This document records the focused
decision rationale, migration test, non-candidate rules, and feasibility
evidence. The effect graph, state layout, source map, ProcRef, native-return,
and migration-parity documents continue to own their component contracts.

This decision resolves the type/runtime boundary report's procedure-first
recommendations without treating that historical diagnostic as implementation
authority. It also closes two stale ambiguities:

- a reusable unit is not a `defworkflow` merely because another unit calls it
  or because it belongs in a library; and
- `WorkflowRef` and `ProcRef` values are compile-time/module-link references,
  never runtime-transported values.

The native transportable return contract is already settled. Procedures,
provider and command results, workflow calls, and workflow boundaries share
the same transportable types. Direct-root results use compiler-owned
`__result__` carriage with an empty JSON pointer; authored code sees the
declared type, not an envelope. Typed result guidance is additive and does not
change this reuse or identity model.

## Problem

Some authored workflow calls represent real public boundaries. Others use a
workflow only as a function-shaped reuse mechanism. Treating both alike adds
registry entries, workflow-call state, and resume identities where ordinary
typed procedure composition is the intended abstraction. Treating every call
as inline procedure composition has the opposite failure: it can erase an
external invocation surface, publication contract, checkpoint namespace, or
operator-visible run identity.

The existing `inline`, `private-workflow`, and `auto` lowering modes also need
an identity policy. Code cannot claim resume or checkpoint parity while
allowing `auto` to change the persisted route. Generic procedures need a
matching effect policy: copying a pre-specialization summary while resolving
effectful ProcRef hooks would hide caller-visible effects.

## Goals And Non-Goals

### Goals

- Make workflows the durable public execution boundary and procedures the
  normal internal reuse unit.
- Preserve one typed return model across pure, procedural, effect, call, and
  workflow boundaries.
- Preserve public inputs, defaults, outputs, artifacts, publications, terminal
  outcomes, source maps, checkpoint identity, and resume behavior during a
  reuse migration.
- Distinguish a procedure's direct body effects from its caller-visible
  transitive effects.
- Keep all procedure selection and specialization compile-time deterministic.
- Give each lowering mode an explicit state/resume/identity meaning.
- Define a migration test that requires executable parity, not compilation
  alone.

### Non-goals

- Runtime procedure or workflow values, closures, dynamic dispatch, or
  provider/command-selected behavior.
- Authored generic `defworkflow` entrypoints.
- Hidden provider, command, filesystem, state, transition, publication, bridge,
  or child-workflow effects.
- Implicit artifact publication from a procedure return.
- Silent checkpoint renaming, remapping, or loss of resume compatibility.
- Reopening transportable result types, direct-root wire shape, `__result__`,
  or typed result guidance.
- Reclassifying every workflow family in this durable design; the reviewed
  current-source inventory and its totals remain planning evidence.

## Decision

### Boundary roles

Use `defworkflow` when the unit owns at least one durable public role:

- externally invocable CLI/API entry or workflow-entry registry/export;
- an independently addressable child-workflow invocation identity;
- independent run or resume identity;
- operator-visible workflow lifecycle or debug boundary;
- public input/default/output contract;
- public artifact name or publication policy; or
- a checkpoint/state namespace that callers must address independently.

Use `defproc` for typed internal behavior reused within a retained public
workflow, including provider/command phases, transitions, loops, projections,
and orchestration over statically selected procedures. Library membership and
being called from another unit do not make a unit a workflow. Ordinary module
export of a reusable procedure is not workflow-entry registration.

`defun` remains the pure reuse unit. A macro remains syntax transformation and
must not own semantic behavior or hide effects.

### Lowering and identity policy

| Mode | Accepted role | Identity contract |
| --- | --- | --- |
| `inline` | Default for procedure-first migrations and caller-owned internal composition | Generated execution belongs to the caller's workflow, state layout, source-map expansion stack, and checkpoint route. |
| `private-workflow` | Internal procedure whose migration contract and evidence identify a separate private state, resume, or debug namespace | The generated boundary is deterministic and private. It is not externally invocable, published, or a substitute for a retained public workflow. The namespace need is evidence in the current slice, not a new source annotation. |
| `auto` | Identity-free helper for which either lowering has equivalent observable behavior | The compiler may choose either route. The choice is not a stable checkpoint, resume, state-path, or debug identity promise. |

A migration must write `:lowering inline`; it must not rely on the current
choice made by `auto`. A new `private-workflow` use must identify the private
namespace obligation and prove its deterministic name, state layout, effect
summary, source maps, and resume behavior. Reuse count or body size alone does
not justify a private workflow.

### Effects

Each procedure has two related summaries:

- **direct effects:** effects lexically introduced by its body, excluding the
  bodies of called procedures, selected ProcRefs, and called workflows; and
- **caller-visible transitive effects:** the direct effects joined with every
  statically resolved callee and selected hook reachable from that procedure.

The accepted model requires generic declarations to retain their direct body
effects. After type parameters and ProcRefs resolve, the specialized
monomorphic body must be authoritatively typechecked and its caller-visible
transitive effects recomputed before lowering. Lowering must consume that
recomputed summary; inline structural visibility is supporting evidence, not a
substitute for a truthful summary.

This is accepted semantics. In the current implementation,
`procedure_typecheck.direct_effects` is a conservative carrier that already
includes callee transitive effects; it is not evidence of a distinct
body-local direct summary. Before any procedure-first pilot, mandatory Stage 5
substrate work must add a distinct representation or derivation for the
body-local direct view, recompute the caller-visible transitive view after
generic/ProcRef specialization, and prove both through Semantic IR and
lowering tests. Until then, inline structural visibility does not authorize a
family migration.

Procedure composition may use the supported typed boundaries below only when
the selected lowering path preserves their ordinary validation and Semantic IR
effects:

- provider structured results (`uses_provider`);
- command structured results and certified command adapters (`uses_command`);
- declared reads, writes, state updates, snapshots, ledgers, and materialized
  views;
- runtime-native resource transitions and their move/state/audit effects;
- statically resolved child-workflow calls (`calls_workflow`);
- explicit runtime bridge or compatibility-adapter effects; and
- explicit artifact publication owned by the retained public workflow
  (`publishes`).

An unsupported or unproven boundary is an effect-adapter obligation, not
permission to hide the effect. Procedure return values do not publish
themselves. Public names and publication policy remain on the retained
`defworkflow` even when a procedure computes the value or artifact.

### Static composition

`ProcRef` targets a named `defproc`; `WorkflowRef` targets a named
`defworkflow`. Both resolve at compile/module-link time, signatures are checked
statically, and specialization finishes before WCC/Core AST/Semantic IR
projection. Compile-time formal `ProcRef` and `WorkflowRef` parameters are
supported and erased. Neither reference may become a runtime-bound public
workflow input contract or cross an output, record, union, artifact, provider
result, command result, state, ledger, or loop-carried boundary.

Use `ProcRef` for internal reusable behavior. Reserve `WorkflowRef` for
statically selected whole-workflow public boundaries whose workflow identity
is itself part of the composition. Executable IR and runtime state contain no
unresolved procedure or workflow reference values.

## Preserved Contracts

Moving internal behavior from `defworkflow` to `defproc` must not silently
change:

- the retained public workflow's module-qualified entrypoint;
- public inputs, defaults, output type, generated output mapping, or terminal
  outcome;
- typed result shape, including direct-root `__result__` carriage;
- artifact identity, lineage, public publication names, or publication timing;
- provider/command target binding and validation-before-exposure;
- caller-visible transitive effects or effect-graph provenance;
- authored and generated source-map origins;
- state-layout ownership, write roots, checkpoint identifiers, or resume
  reconstruction; or
- child-workflow invocation semantics that remain public boundaries.

Inline lowering attributes generated nodes to the procedure definition,
specialization/ProcRef forms, and consuming call site while keeping the public
workflow as runtime owner. Private-workflow lowering additionally records the
deterministic private boundary. No compiler-generated private name becomes a
new public invocation or publication surface.

A procedure-first migration is strict-compatible by default. If it cannot
preserve a persisted identity exactly, it must stop unless a separately
reviewed general atomic upgrader preserves supported old-state consumers, or
the migration qualifies for the reviewed internal identity-retirement class
in the accepted
[Procedure-Migration Identity Compatibility](workflow_lisp_procedure_migration_identity_compatibility.md)
design. Identity retirement is never available to a public or exported callee,
a promoted or live route, or any migration with a supported consumer of the
old identity. It supplies evidence only and does not remap old state.

## Migration Test

An internal workflow call is a procedure candidate only when all of the
following are established:

1. The callee owns no required public invocation, run/resume, publication,
   output, or operator-visible identity.
2. Its signature and returns are expressible as an ordinary typed `defproc`.
3. Every direct and transitive effect is supported on the selected procedure
   route; ProcRef and child-workflow effects remain visible.
4. The migrated definition and all migrated calls choose `:lowering inline`.
5. Compile and shared validation pass through the production WCC route with no
   consumer-name special case.
6. Before/after executable comparison proves public inputs/outputs, terminal
   states, artifacts/publications, effects, source maps, state/write roots,
   checkpoint identities, and resume/reuse behavior equivalent. Every axis is
   unconditional except persisted identity: strict compatibility remains the
   default, while a general atomic upgrader or the accepted reviewed internal
   identity-retirement class may authorize its specifically bounded identity
   treatment. The retirement exception is unavailable to public/exported
   callees, promoted/live routes, or supported old-identity consumers.
7. A runtime or end-to-end family check exercises the retained public wrapper.

Compilation, typechecking, lowering, validation, or dry-run alone is necessary
but insufficient promotion evidence.

### Non-candidates

Retain a `defworkflow` when any of these is true:

- operators or external callers run or resume it directly;
- it owns an externally invocable workflow-entry registry/API/export contract
  or independently addressable child workflow call;
- it owns public inputs, outputs, artifacts, publication names, or terminal
  lifecycle semantics that cannot remain on a wrapper;
- an independent persisted checkpoint/state namespace is contractual and no
  accepted mapping preserves it;
- its effects require an unsupported procedure substrate; or
- migration parity cannot be computed from production-path evidence.

A unit that needs a private state/resume/debug namespace but no public role may
become a `defproc :lowering private-workflow`; this is not an exception to the
public-boundary rules. In the current slice the namespace need is recorded and
reviewed as migration evidence, not expressed through a new namespace source
annotation.

## Feasibility Evidence

The design is grounded by three distinct cases rather than by a compile-only
prototype:

- `std/drain.orc::backlog-drain-proc` demonstrates generic, effectful,
  ProcRef-composed inline procedure behavior on the promoted Design Delta
  route.
- `workflows/examples/design_plan_impl_review_stack_v2_call.orc::tracked-plan-phase`
  is an ordinary non-drain internal workflow with typed results and provider
  effects beneath a retained public stack wrapper. It is a positive migration
  candidate, subject to the full migration test.
- `workflows/library/lisp_frontend_design_delta/drain.orc::drain` is a negative
  case: it owns the promoted external run/resume and terminal publication
  contract and therefore remains a workflow even if its internal helpers move
  to procedures.

These examples prove that the boundary classification is meaningful. They do
not claim that every effect family or inventory row is already migratable.

## Compatibility And Migration

Existing `defworkflow`, `defproc`, and `auto` programs remain valid. The new
rule constrains adoption and migration claims: identity-sensitive code must
select an explicit lowering mode, and public wrappers stay workflows.

No wrapper record is introduced or removed by this decision. Every
transportable return type remains valid everywhere already allowed by the
native-return contract. Direct roots remain direct JSON documents behind the
compiler-owned `__result__` artifact. Typed guidance remains optional metadata
and does not affect lowering, identity, effects, or migration classification.

## Implementation Sequencing

The accepted procedure-first authoring and migration rules are Stage 5-gated.
Before the pilot, a separately reviewable substrate plan must close the current
effect-carrier gap: establish a body-local direct view, recompute the
caller-visible transitive view after specialization, feed the recomputed view
to lowering and Semantic IR, and add positive and negative effect-visibility
tests. No family may claim procedure-first promotion from this accepted design
alone. Current capability and adoption status belongs in the capability matrix
and procedure-first roadmap, not this durable contract.

## Verification Strategy

Each substrate or family implementation must include:

- type/effect tests proving direct versus recomputed transitive summaries,
  including a specialized generic with effectful ProcRef hooks;
- lowering tests for explicit `inline`, explicit `private-workflow`, and the
  rejection or non-promotion of identity-sensitive `auto` use;
- source-map checks spanning the procedure, ProcRef/specialization form, call
  site, generated nodes, and any private boundary;
- compiled before/after comparisons for public contracts, effects, artifacts,
  publications, state layout, and checkpoint identity;
- resume/reuse coverage when the original family has persisted state;
- a runtime/end-to-end check through the retained public wrapper; and
- negative coverage proving that a public run/resume/publication boundary is
  not erased.

## Acceptance Criteria

- The frontend specification and authoring guide teach one boundary rule:
  workflows are durable public execution boundaries; procedures are normal
  internal reuse.
- Direct and caller-visible transitive effects are separately defined and
  specialization recomputes the latter before lowering.
- Supported composed effects and their owners are explicit; publication is
  never inferred from a return.
- Procedure-first migrations require explicit inline lowering; private
  workflow lowering requires a declared private identity need; `auto` promises
  no persisted identity.
- WorkflowRef is compile-time/module-link only, matching ProcRef's no-runtime-
  values boundary.
- The migration test preserves public, artifact, source-map, checkpoint, and
  resume contracts and rejects compile-only promotion claims.
- Native returns, direct roots, and typed guidance remain compatible and are
  not reopened.
