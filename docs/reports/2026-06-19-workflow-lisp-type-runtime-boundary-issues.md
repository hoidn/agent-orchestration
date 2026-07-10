# Workflow Lisp Type And Runtime Boundary Issues

Date: 2026-06-19
Status: diagnostic report; dispositioned 2026-07-08 (accepted with
modifications). Retained as a historical record — where a recommendation has
been absorbed by newer authority, the pointer in "Disposition Of
Recommendations" governs, not this report's original wording.
Scope: issues uncovered while reasoning about refined match binders, branch-local
fields, stdlib drain results, executable output contracts, source maps, and
runtime validation.

Related current authority:

- `docs/design/workflow_lisp_parametric_type_system.md` — generic `defproc`
  mechanism and the Tranche 2 drain migration (recommendations 3, 5, 7)
- `docs/plans/2026-07-07-drain-migration-g8-retirement.md` — name-specific hook
  retirement and bridge-augmentation retirement (recommendations 5, 6)
- `docs/plans/2026-07-07-yaml-retirement-program.md` — YAML-surface end state
  (recommendation 7's parity framing)
- `docs/design/workflow_lisp_shared_owner_lane_prerequisites.md` — the one
  design doc that has adopted refined-match-binder terminology so far
  (recommendations 1–2)
- `docs/plans/2026-07-07-refactoring-dead-code-and-lowering-consolidation.md`
  — Task 3's fixture disposition interacts with recommendation 8

## Disposition Of Recommendations (2026-07-08)

| Rec | Status | Owner / action |
|---|---|---|
| 1–2 (refined-binder terminology; proof internal-only) | **Open, actionable now** | Doc sweep: author-facing surfaces say "refined match binders"; "proof" reserved for compiler metadata, diagnostics, source maps, resume evidence. Adopted so far only in `workflow_lisp_shared_owner_lane_prerequisites.md`; the frontend specification and five other design docs still front "proof-gated". Implementation already conforms — authors write ordinary `match`. |
| 3 (variant-scoped output contracts) | **Partially absorbed** | Entry-publication/variant handling advanced under the design-delta certification work; the constraint surface is owned by the parametric type system. Residual gap tracked by open question 1. |
| 4 (shared contract representations) | **Partially realized** | The converged executable IR plus shared surface validation is the shared substrate; "one contract model drives typechecker and runtime validators" remains directional. |
| 5 (retire name-specific hooks) | **Absorbed** | Parametric type system Tranche 2 + `2026-07-07-drain-migration-g8-retirement.md` Phases 1–2; the G8 deletion inventory enumerates the lowerer, monomorphizer, name-keyed validators, and registry heads this report asked to retire. |
| 6 (bridges/views at consumer boundaries) | **Absorbed** | Bridge declarations with owner/schema/consumer/retirement metadata exist; the compiler-hook bridge augmentation flagged here retires with the certification bundle (drain plan Phase 3). |
| 7 (generic lifecycle types) | **Mechanism landed; application pending; parity sentence amended** | `std/drain.orc` already owns `DrainResult`, `SelectionResult`, `GapResult`, `SelectionPayload`, `GapPayload`, `DrainLoopTerminal`; parametric generics enable the `DrainResult<TSummary>` shape during the drain migration. See the amended parity note in issue 7. |
| 8 (negative tests) | **Amended to a coverage audit** | See the amended recommendation; resolves a live collision with the Phase-1 refactoring plan's orphaned-fixture deletion. |
| 9 (unified typed-return semantics) | **Directional, gated** | Needs a frontend-spec update before implementation; conflicts today with the `record-drain-outcome` contract. Not implementation authority. |
| 10 (interpreter-like evaluation) | **Directional** | WCC + lexical checkpoints are the current path; roadmap-level only. |
| 11 (demote workflow as reuse unit) | **Directional, partially enacted** | Enacted for drain (`backlog-drain-proc` is authored as a `defproc`, not a workflow); generalizing beyond drain needs a frontend-spec update. |

## Summary

The recurring problem is not that Workflow Lisp lacks a type system. The
problem is that type information is currently crossing several boundaries:
surface `.orc`, WCC, lowered workflow contracts, shared validation, runtime
output bundles, source maps, resume records, and migration parity evidence.

The intended model is sound:

```text
authored typed value
-> WCC refined binding / join parameter
-> executable output/resource/artifact contract
-> runtime validation of concrete bundles and files
-> source-mapped diagnostics and parity evidence
```

The friction comes from places where that projection is incomplete or too
special-cased. When type facts are not carried into executable contracts, the
runtime cannot validate concrete outputs correctly. When runtime validation
tries to rediscover type facts from generated names, paths, or workflow-specific
hooks, the implementation becomes brittle and leaks internal mechanics into
authoring design.

## Issues Encountered

### 1. Refined match binders are the right user model, but proof metadata still leaks into design language

Authors should be able to write:

```lisp
(match result
  ((BLOCKED blocked)
    blocked.blocker-class)
  ((DONE done)
    done.summary))
```

In that surface model, `blocked` is the `BLOCKED` payload. The author should
not need to think in terms of proof tokens. Internally, the compiler still
needs proof metadata so lowering and shared validation know that
`blocked.blocker-class` is legal only in the `BLOCKED` branch.

Current design text and implementation discussion often says "proof-gated
field access." That is technically accurate internally, but it is a poor
author-facing abstraction. It makes a normal pattern-match refinement sound
like a separate proof system authors must manage.

Implication: target designs should describe the authored surface as refined
pattern matching and reserve proof terminology for compiler metadata,
diagnostics, shared validation, and source-map evidence.

### 2. Compile-time typechecking and runtime validation are related but not identical

The typechecker validates source expressions:

- does a field exist;
- is it available in this branch;
- do all match arms return the declared type;
- does a call receive arguments of the expected types.

Runtime validation checks produced data:

- did the active variant actually appear;
- did the output bundle match the active variant schema;
- are required artifacts present;
- do JSON pointers resolve;
- did a provider or command write the declared target rather than a wrong path.

These should share a single typed contract model, but they cannot be the same
pass. Compile time has lexical scopes and expressions. Runtime has concrete
bundles, files, JSON, artifacts, and persisted state.

Implication: the principled architecture is not "runtime repeats the type
checker." It is "types generate contracts, and both compile-time and runtime
validators consume those contracts against different evidence."

### 3. Executable output contracts need variant-scoped type information

For a union such as:

```lisp
(defunion DrainResult
  (DONE
    (summary Summary))
  (BLOCKED
    (summary Summary)
    (blocker Blocker)))
```

The compiler knows `blocker` exists only on `BLOCKED`. The executable output
contract must preserve the same fact:

```text
DrainResult.DONE exports summary
DrainResult.BLOCKED exports summary, blocker
```

If lowering flattens that into unscoped artifact names or loses active-variant
metadata, runtime validation can over-require inactive fields, allow impossible
fields, collide repeated field names, or produce diagnostics against generated
step names instead of authored union fields.

Implication: output contracts and source maps need variant-scoped identities
derived from type definitions. This is a projection of type information, not a
second independent source of truth.

### 4. Source maps are doing semantic work because generated artifacts erase context

Lowered workflows produce generated step names, artifacts, JSON pointers, and
runtime bundles. Those are not enough to explain why an output is valid or
invalid. Source maps need to connect:

```text
authored union field
-> refined branch binding
-> lowered output/artifact field
-> runtime bundle key / JSON pointer
-> diagnostic or parity evidence
```

Without that chain, errors such as "missing blocker-class" cannot reliably say
"the `BLOCKED.blocker-class` field of `DrainResult` was not produced." They
instead point at implementation details such as generated step names or private
bridge outputs.

Implication: source maps should not be treated as optional explanation sugar.
For typed workflow lowering, they are part of preserving the type/runtime
contract boundary.

### 5. Stdlib drain results should be ordinary typed values, but current support still has transitional seams

Conceptually, a `std/drain::DrainResult` should be just another evaluated
typed expression. If a family needs a different public result, it should use
ordinary `.orc` projection:

```lisp
(match stdlib-result
  ((COMPLETED done) ...)
  ((BLOCKED blocked) ...)
  ((EXHAUSTED exhausted) ...))
```

The fact that the result came from `std/drain.backlog-drain` should not matter
to the compiler. Recent work is moving in that direction, but the codebase
still has transitional machinery around stdlib drain lowering, terminal
carriage, managed paths, bridge augmentation, and runtime proof lanes.

Implication: the final target should retire name-based handling for
`std/drain`, `backlog-drain`, `finalize-selected-item`, and family-specific
Design Delta bridge augmentation. Any remaining mechanism must be generic over
typed calls, unions, projections, resources, and publications.

### 6. Compatibility bridges and materialized views are still obscuring the core model

Files remain necessary for public artifacts, legacy compatibility, provider
reports, source documents, and runtime state. The problem is not file use. The
problem is when file paths and materialized views become semantic authority
inside the typed workflow.

The desired distinction is:

- typed values are semantic authority inside `.orc`;
- materialized views are consumer-facing representations;
- compatibility bridges are declared migration surfaces with owner/schema/
  consumer/retirement metadata;
- runtime state/resource updates are typed transitions or certified adapters.

When compatibility bridges are injected by core compiler hooks or threaded
through normal workflow parameters, the authoring model regresses toward
YAML-shaped path choreography.

Implication: compatibility bridges should be declared at generic boundary or
publication seams and retired from internal module-to-module workflow
composition.

### 7. Workflow-family wrapper types should collapse toward generic lifecycle types plus domain payloads

Some current family-specific types exist because the migration preserves
YAML-era bundles, pointer paths, report summaries, compatibility outputs, and
run-state views. Those are not all domain concepts. Many are representations
of a smaller lifecycle shape that should be owned by generic stdlib types.

A cleaner target is:

```text
DrainResult<TSummary>
Selection<TItem, TGap>
WorkItemResult<TSummary>
GapDraft<TGap>
```

The Design Delta family should then provide only the payload/schema types that
are actually domain-specific:

```text
DesignDeltaItem
DesignDeltaGap
DesignDeltaSummary
```

This avoids inventing or preserving names such as `DesignDeltaDrainResult`,
`DesignDeltaSelectionBundle`, `DesignGapDraftBundle`, `WorkItemSummaryBundle`,
and path-heavy summary wrappers when they merely rename generic
`DONE`/`BLOCKED`/`EXHAUSTED`, selected-item, draft-gap, or summary concepts.

What should remain family-specific:

- item payloads;
- gap payloads;
- summary content;
- provider request records;
- domain validation rules;
- public compatibility projections that are still required while legacy YAML
  remains a supported comparison target.

What should go away or become views:

- `selection_bundle_path` as semantic authority;
- `work_item_bundle_path` as semantic authority;
- family-specific terminal result types that only rename generic lifecycle
  variants;
- compatibility bridge records inside ordinary internal composition;
- path-heavy wrapper records whose only purpose is to preserve legacy
  materialization mechanics.

Implication: the stdlib should own generic lifecycle unions and callable
boundaries. Workflow families should supply typed payloads and ordinary
projections to public outputs or legacy views.

**Amendment (2026-07-08)** to the original parity claim ("exact replication of
the YAML state-machine representation should not be a parity requirement"):
this is the correct *end state*, and it is strengthened by the decision to
retire user-facing YAML (`docs/plans/2026-07-07-yaml-retirement-program.md`).
It is **not** license to weaken the current migration gates: the
census-fingerprint and manifest-row strictness in the certification lane is
intentionally load-bearing *while* the migration is in flight, and it retires
with the bundle (drain plan Phase 3), not before. Distinguish migration-time
evidence (strict, structural, temporary) from end-state parity (semantic
terminal results, payloads, public artifacts, accepted compatibility views).

### 8. The current vocabulary risks over-modeling if every boundary gets its own concept

The discussion has accumulated terms such as proof, refined binding, source
map, executable contract, output bundle, bridge, materialized view, resource
transition, private context, publication, adapter, parity evidence, and
runtime proof. Most of these concepts are real, but exposing all of them to
authors would make Workflow Lisp feel bureaucratic.

The simpler organizing principle is:

```text
Authors write typed composition.
Compiler preserves lexical/refined meaning through WCC.
Runtime validates concrete effects using contracts derived from types.
Files/views/bridges exist only at declared consumer boundaries.
```

Implication: design docs should separate the author-facing model from
compiler/runtime implementation obligations. The surface should be small even
when the implementation evidence is detailed.

### 9. Workflow and function semantics should share typed return values

Separating typed return values from publication weakens the old reason for
treating workflows as a different semantic universe from ordinary functions.
A workflow body should evaluate to a typed value the same way a pure helper or
effectful procedure does. Publication, bridge generation, resource mutation,
adapter execution, and audit emission are external effects attached to a
boundary or explicit effect form, not the mechanism that makes return work.

The remaining distinction is operational, not value-semantic:

- a pure helper has an empty effect set and can be checked as deterministic
  typed expression/projection logic;
- an effectful procedure may call providers, commands, child workflows,
  transitions, or publications and must expose those effects to WCC, shared
  validation, Semantic IR, source maps, and runtime validators; and
- a workflow entrypoint is a resumable/public executable boundary with runtime
  context, checkpointing, observability, artifact lineage, failure policy, and
  declared publication/bridge/resource effects.

This means `(publish result)` can remain a low-level or timed/intermediate
effect form, but ordinary terminal publication should usually be boundary
policy over the returned value. A parent workflow should not need a publication
or `record-drain-outcome`-style side effect merely to receive a typed child
result.

Implication: the final authoring model should converge toward one expression
language with typed return semantics and tracked effects. `defworkflow`,
`defproc`, and pure helpers should differ mainly by effect set, resumability,
exported boundary metadata, and runtime evidence obligations.

### 10. Interpreter-like value semantics would help, but opaque interpreter state is not enough

Several of the current terminal-reprojection and branch-local-field problems
would be less visible in a direct interpreter. An interpreter can keep a
lexical environment such as `blocked = <BLOCKED payload>` and evaluate the
parent constructor normally. That naturally preserves scoped field access,
ordinary `match` refinement, and value return without generated step-name or
bundle-shape detours.

That does not remove the durable orchestration problem. Provider calls,
commands, child workflow calls, resource transitions, publication, bridge
generation, retries, resume, artifact lineage, output-bundle validation, and
parity evidence still need explicit effect-boundary contracts. Opaque
interpreter state would make those external effects harder to inspect, resume,
deduplicate, validate, and compare.

The better target is not "compiler only" or "interpreter only." It is
interpreter-like typed evaluation for pure and structured regions, plus
compiled/projected effect-boundary metadata for durable external work. WCC,
lexical checkpoints, and contract projection are the current path toward that
hybrid: preserve source-language value semantics while still giving the
runtime concrete contracts for validation, resume, source maps, and parity.

Implication: future runtime simplification should move toward evaluating typed
values directly between effect boundaries, but it should not hide effect
boundaries inside opaque interpreter state.

### 11. "Workflow" is probably overextended as a reusable-code abstraction

The current migration still tends to model reusable units as workflows calling
workflows. That is often the wrong abstraction. Many reusable `.orc` units are
really ordinary Lisp-style functions or procedures: they reshape typed values,
branch over unions, normalize terminal results, or construct provider request
records. Forcing those units through workflow-call boundaries makes them inherit
too much runtime machinery: public inputs, hidden context, generated paths,
artifact/result projection, compatibility bridges, and parity surfaces.

Provider calls are the more useful notion of "step" here. The authoring model
should separate:

- regular pure functions for deterministic value computation;
- effectful functions/procedures for typed composition that may call effects;
- provider steps with prompt/input/output contracts;
- command/resource/publish/bridge steps for other explicit external effects;
  and
- workflow entrypoints as durable run boundaries.

Under that model, `workflow` is not the default unit of reuse. It is the
top-level executable boundary that owns run identity, resume/checkpoint policy,
observability, artifact lineage, operator reporting, and public input/output
projection. Internal composition should look like normal typed Lisp evaluation
with explicit effect forms where external work occurs.

Implication: the runtime-native target should not make "workflow call" carry
all composition semantics. It should converge toward regular function calls
plus explicit provider/effect steps, with workflow as an operational boundary
rather than a distinct value-semantic universe.

## Root Cause Interpretation

The root cause is an impedance mismatch between a typed, lexical, expression
language and a flat executable workflow model whose runtime authority is based
on steps, artifacts, bundles, JSON pointers, files, and resume records.

WCC addresses the compiler side by giving Workflow Lisp a real middle end:
`match` becomes `case`, loops become recursive joins, branch outputs flow
through join parameters, and proof/refinement metadata survives lowering. But
WCC alone does not finish the runtime boundary. The executable contract still
needs enough type-derived structure to validate actual outputs and effects
without relying on generated names or workflow-specific patches.

So the main architectural task is contract projection:

```text
type definitions and refined WCC bindings
-> variant-scoped executable contracts
-> runtime validators over concrete bundles/artifacts/resources
-> source-mapped diagnostics and parity evidence
```

## Recommended Direction

1. Keep refined match binders as the author-facing model.

   Authors should see `blocked` as a `BLOCKED` payload, not a proof token.

2. Treat proof metadata as compiler/runtime evidence only.

   It should appear in source maps, diagnostics, shared validation, and resume
   metadata, not as ordinary authored values.

3. Derive executable output contracts from typed unions and records.

   Variant-scoped output identity should be generated from type definitions
   and preserved through lowering.

4. Share contract representations between compile-time and runtime validation.

   Do not duplicate rules by hand. The same contract model should drive the
   typechecker, output bundle validator, artifact checker, source maps, and
   parity evidence.

5. Retire name-specific stdlib/family hooks.

   If `backlog-drain` results need projection, use ordinary typed projection.
   If bridge outputs are needed, declare them through generic boundary or
   publication metadata.

6. Keep bridges and materialized views at consumer boundaries.

   Internal `.orc` modules should pass typed values. Views should be produced
   for prompts, public outputs, observability, or explicitly declared legacy
   consumers.

7. Collapse family wrapper types into generic lifecycle types where possible.

   Keep `DrainResult`, `Selection`, `WorkItemResult`, and `GapDraft` generic.
   Keep Design Delta-specific types for item, gap, summary, provider request,
   validation, and public compatibility payloads.

8. Audit negative-path coverage against the case list below; wire or recreate
   only the gaps.

   **Amendment (2026-07-08)** — originally "add focused negative tests." A
   coverage audit must come first: the variant-proofs suite already covers part
   of this list behaviorally, and three orphaned fixtures created in this
   report's spirit were never wired to any test
   (`tests/fixtures/workflow_lisp/invalid/if_variant_proof_missing.orc`,
   `review_loop_result_contract_invalid.orc`,
   `backlog_drain_hidden_compatibility_bridge_reread_invalid.orc`). Resolve the
   audit against
   `docs/plans/2026-07-07-refactoring-dead-code-and-lowering-consolidation.md`
   Task 3 **before** that task's fixture deletion runs: wire a fixture into a
   behavioral test if its case is uncovered; let the deletion stand if the case
   is already covered elsewhere. Per repo test policy, assert behavior and
   diagnostics contracts, not literal prompt or message text.

   Audit case list (unchanged from the original recommendation):

   - access `blocked.blocker-class` outside a `BLOCKED` match arm;
   - return a union whose repeated field names collide after lowering;
   - omit an active variant's required output bundle field;
   - provide an inactive variant field and confirm it is rejected or ignored
     according to contract;
   - lose source-map attribution from runtime output failure to authored union
     field;
   - make a stdlib drain projection pass only through name-specific compiler
     handling and confirm the generic route catches it.

9. Keep typed return semantics common across pure helpers, procedures, and
   workflows.

   Workflows should be special because they are effectful, resumable,
   observable executable boundaries, not because they return values through a
   different mechanism. Publication and bridge effects should consume returned
   typed values; they should not be required for parent composition.

   *Disposition (2026-07-08): directional only — this is a language-semantics
   commitment that requires a frontend-specification update before any
   implementation, and it conflicts today with the `record-drain-outcome`
   contract. This report is not implementation authority for it.*

10. Prefer interpreter-like evaluation between explicit effect boundaries.

   Pure and structured Workflow Lisp regions should behave like ordinary typed
   expression evaluation with lexical environments and refined match binders.
   External work should cross explicit effect boundaries that carry contracts
   for validation, resume, source maps, artifacts, and parity evidence.

   *Disposition (2026-07-08): directional only — WCC and lexical checkpoints
   are the current path toward this hybrid; roadmap-level, no near-term
   action.*

11. Shrink workflow to the durable executable boundary.

   Reusable domain logic should be ordinary Lisp-style functions/procedures.
   Provider calls and other external operations should be explicit steps.
   Workflow entrypoints should own run/resume/public-boundary obligations, not
   serve as the default abstraction for every reusable helper.

   *Disposition (2026-07-08): partially enacted — the drain migration authors
   `backlog-drain-proc` as a `defproc`, not a workflow
   (`docs/plans/2026-07-07-drain-migration-g8-retirement.md` Phase 1).
   Generalizing beyond drain requires a frontend-specification update; this
   report is not implementation authority for that generalization.*

## Open Questions

- How much of the executable output contract can be generated directly from
  the existing type environment today, and how much still lives in bespoke
  output-contract code? *(Still open; sharpened by the parametric constraint
  surface now owning the type-side vocabulary.)*
- Which current stdlib drain/runtime-proof allowances are genuinely generic,
  and which are still name-specific transitional scaffolding?
  *(Answered 2026-07-08: enumerated by the G8 deletion inventory in
  `docs/plans/2026-07-07-drain-migration-g8-retirement.md` Phase 2 — the
  phase-drain lowerer, drain-terminal intrinsic paths, the monomorphizer,
  name-keyed validators, and three `compatibility_route_only` registry heads
  are the name-specific set.)*
- Do bridge/publication declarations already provide enough metadata to replace
  the Design Delta-specific compile-result augmentation hooks?
  *(Answered 2026-07-08: yes, contingent on the certification-bundle
  retirement — drain plan Phase 3 retires the augmentation hooks while
  preserving the generic bridge/publication metadata.)*
- Are source maps currently complete enough to map runtime output failures back
  to variant-scoped authored fields? *(Still open; belongs to the
  recommendation 8 coverage audit.)*
- Should the frontend spec explicitly rename author-facing "proof-gated field
  access" to "refined match binders" while retaining proof terminology for
  internal metadata? *(Answered 2026-07-08: yes — execute as the
  recommendations 1–2 terminology sweep;
  `workflow_lisp_shared_owner_lane_prerequisites.md` already models the
  wording.)*
- Should the frontend spec make the effect-set distinction explicit enough
  that pure helpers, effectful procedures, and workflow entrypoints share one
  return-value model while differing by resumability and runtime boundary
  obligations? *(Open — this is the recommendation 9 design-doc gate.)*
- Should the runtime roadmap explicitly target interpreter-like evaluation for
  pure/structured regions while keeping providers, commands, child workflow
  calls, transitions, publication, and bridges as compiled effect boundaries?
  *(Open, roadmap-level — recommendation 10.)*
- Should the frontend/runtime roadmap demote reusable workflow calls in favor
  of regular functions plus explicit provider/effect steps, leaving workflow as
  the durable public run boundary? *(Partially answered by the drain migration
  authoring `backlog-drain-proc` as a `defproc`; generalization is the
  recommendation 11 design-doc gate.)*

## Bottom Line

The type system should remain the source of truth, but runtime validation still
needs projected contracts because it validates concrete outputs after type
erasure and lowering. The elegant solution is not to expose more proof machinery
to authors. It is to make refined pattern matching the surface model and ensure
that WCC, executable contracts, source maps, runtime validation, and parity
evidence all preserve the same typed union/record structure. Longer term, the
runtime should feel interpreter-like for typed values between effect
boundaries, while keeping those effect boundaries explicit and inspectable.
In that shape, provider/effect steps are the primary durable step abstraction;
workflow is the public/resumable execution boundary, not the normal unit of
internal reuse.

*(2026-07-08: this bottom line has held up. The contract-projection root cause
is the same conclusion the parametric type system work reached independently.
For current status per recommendation, see "Disposition Of Recommendations"
above; where a disposition names a newer owner, that owner governs.)*
