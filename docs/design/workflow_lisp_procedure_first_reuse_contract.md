# Workflow Lisp Procedure-First Reuse Contract

Current substrate: typed procedures and static ProcRefs specialize into the
checked closed program. Historical flat lowering/projection evidence does not
restore that backend. Identity comparisons apply to supported evaluated callers;
old-run recovery and explicit retirement are governed by
[executor retirement](workflow_lisp_executor_retirement.md).

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

Procedure composition follows the definition’s origin. Origins 2.35–2.38
retain role-based authored lowering: migrations use `:lowering inline`,
`private-workflow` requires a reviewed private namespace need, and `auto`
promises no persisted identity. Definitions originating at 2.39 reject
`:lowering` and compose inline in the caller. A 2.39 caller preserves imported
2.35–2.38 policy; an intentional new boundary uses `defworkflow` plus `call`.

Procedure composition is statically resolved. Direct body effects and
caller-visible transitive effects are distinct, and the compiler recomputes
the transitive summary after generic specialization and ProcRef resolution.
No runtime procedure values, closures, dynamic dispatch, hidden effects, or
implicit publication are introduced.

The resolved-effect substrate implements that split.
`TypedProcedureDef.direct_effect_summary` retains the body-local effect atoms
and procedure-call edges, while `transitive_effect_summary` is recomputed over
the fully materialized monomorphic procedure set after generic and `ProcRef`
specialization. The frontend owns each procedure’s origin-selected lowering
policy and any retained old-origin private-workflow name. WCC consumes those
compiler-owned resolved effects and decisions rather than deriving substitutes.
Classic lowering is historical evidence, not an executable route.

## Context And Authority

The parent
[Workflow Lisp Frontend Specification](workflow_lisp_frontend_specification.md)
owns the durable source-language contract. This document records the focused
decision rationale, migration test, non-candidate rules, and feasibility
evidence. The effect graph, state layout, source map, ProcRef, native-return,
and other current component documents continue to own their contracts. Current
route claims are owned by the route-readiness registry and its cited direct
owner behavioral tests; the migration-parity architecture and frozen reports
remain historical evidence only.

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

The retained 2.35–2.38 `inline`, `private-workflow`, and `auto` lowering modes
also need an identity policy. Code cannot claim resume or checkpoint parity while
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

For definitions originating at 2.35–2.38, including imports into a 2.39 caller:

| Mode | Accepted role | Identity contract |
| --- | --- | --- |
| `inline` | Default for procedure-first migrations and caller-owned internal composition | Generated execution belongs to the caller's workflow, state layout, source-map expansion stack, and checkpoint route. |
| `private-workflow` | Internal procedure whose migration contract and evidence identify a separate private state, resume, or debug namespace | The generated boundary is deterministic and private. It is not externally invocable, published, or a substitute for a retained public workflow. The namespace need is evidence in the current slice, not a new source annotation. |
| `auto` | Identity-free helper for which either lowering has equivalent observable behavior | The compiler may choose either route. The choice is not a stable checkpoint, resume, state-path, or debug identity promise. |

A migration at those origins must write `:lowering inline`; it must not rely
on `auto`. A retained `private-workflow` use must identify its namespace
obligation and prove deterministic identity, state layout, effects, source
maps and resume behavior. Reuse count or body size alone does not justify it.

For definitions originating at 2.39, no authored `:lowering` clause is admitted:
procedures and their specializations are caller-owned inline composition.
Use an ordinary `defworkflow` invoked with `call` for an intentional
call/frame/checkpoint boundary. Unexported workflows limit imports but can
still be selected explicitly as local entries. Their runtime inputs/results
must satisfy concrete workflow transport contracts; generic parameters,
ProcRef and WorkflowRef cannot become runtime workflow inputs. Bind them to
concrete definitions or keep a thin procedure calling a concrete workflow.
Converting an old private procedure to an explicit workflow gives it a new
definition identity and promises no old fingerprint or cross-version resume.
The [frontend contract](workflow_lisp_frontend_specification.md#106-procedure-lowering-policy-resolved)
owns these origin rules.

### Effects

Authored contracts follow [EL-1](workflow_lisp_effect_ledger_simplification.md):
2.39-origin restrictions apply to fully specialized transitive effect
identities (omission infers; empty requires none; named requires a subset).
Imported 2.35–2.38 definitions retain their existing exactness and
specialization rules. These source restrictions are distinct from the
compiler’s internal direct/transitive summary split.

Each procedure has two related summaries:

- **direct effects:** effects lexically introduced by its body, excluding the
  bodies of called procedures, selected ProcRefs, and called workflows; and
- **caller-visible transitive effects:** the direct effects joined with every
  statically resolved callee and selected hook reachable from that procedure.

Generic declarations retain their direct body effects. After type parameters
and ProcRefs resolve, the compiler authoritatively typechecks each specialized
monomorphic body and recomputes its caller-visible transitive effects before
lowering. Inline and private-workflow lowering consume that recomputed
`transitive_effect_summary`; inline structural visibility remains supporting
evidence, not a substitute for the resolved summary.

The substrate's existence does not authorize a family migration by itself.
Each adoption still requires caller-owned inline composition under its
definition-origin rules, effect visibility through
Semantic IR, route-readiness identity, direct owner behavioral evidence,
identity compatibility, and the family-specific review gates. Frozen parity
reports may explain a historical promotion decision but do not authorize a
current change. The classic schema-1 iteration-scope inline-to-private override
remains compatibility behavior only and cannot be used to support a WCC
migration or promotion claim.

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
4. The migrated definition composes inline: explicit `:lowering inline` for
   origins 2.35–2.38; no `:lowering` clause for origins at 2.39. Imported
   definitions preserve their original policy.
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
- route/readiness and behavioral compatibility cannot be established from
  production-path direct owner evidence.

At origins 2.35–2.38, a unit needing a private state/resume/debug namespace
may retain `defproc :lowering private-workflow`, with reviewed evidence of
that need. At 2.39 use an explicit concrete `defworkflow` plus `call` instead;
the transport and new-identity obligations above apply. Neither case permits
erasing a required public boundary or adds a namespace source annotation.

<a id="feasibility-evidence"></a>

Historical procedure-first feasibility cases and consumer inventory. Current migration claims still require all durable tests above. See the [preserved record](../reports/documentation-history/workflow_lisp_procedure_first_reuse_contract-history.md#feasibility-evidence).

## Compatibility And Migration

Admitted 2.35–2.38 definitions retain existing `defworkflow`, `defproc` and
`auto` semantics, including in a 2.39 caller; pre-2.35 source is not admitted.
New 2.39 definitions use implicit inline procedures and explicit workflow
boundaries. Origin-aware composition and public wrappers remain required
for adoption and migration claims.

No wrapper record is introduced or removed by this decision. Every
transportable return type remains valid everywhere already allowed by the
native-return contract. Direct roots remain direct JSON documents behind the
compiler-owned `__result__` artifact. Typed guidance remains optional metadata
and does not affect lowering, identity, effects, or migration classification.

## Implementation Sequencing

The resolved-effect and compiler-owned lowering-decision substrates are
implemented prerequisites. Procedure-first adoption remains family-gated: the
pilot and later waves must prove origin-appropriate inline composition,
resolved effect visibility,
Semantic IR and source-map lineage, checkpoint/state compatibility, runtime
behavior, and the applicable identity-retirement or strict-compatibility path.
No family may claim procedure-first promotion from this accepted design or the
generic substrate alone. Current adoption status belongs in the capability
matrix and procedure-first roadmap, not this durable contract.

## Verification Strategy

Each substrate or family implementation must include:

- type/effect tests proving direct versus recomputed transitive summaries,
  including a specialized generic with effectful ProcRef hooks;
- lowering tests for retained 2.35–2.38 policies, including imports into 2.39,
  and non-promotion of identity-sensitive `auto` use;
- 2.39 tests for implicit inline composition, rejection of authored `:lowering`,
  and concrete explicit workflow boundaries;
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
- Procedure-first migrations require caller-owned inline composition under
  definition-origin rules. Retained 2.35–2.38 private lowering needs reviewed
  identity evidence and `auto` promises no persisted identity; new 2.39
  boundaries are explicit concrete workflows.
- WorkflowRef is compile-time/module-link only, matching ProcRef's no-runtime-
  values boundary.
- The migration test preserves public, artifact, source-map, checkpoint, and
  resume contracts and rejects compile-only promotion claims.
- Native returns, direct roots, and typed guidance remain compatible and are
  not reopened.
