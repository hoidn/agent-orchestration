# Workflow Lisp Review/Revise Stdlib Integration With Refactor Preconditions and Parametric Constraints

Status: implemented companion design / target-delta history
Kind: incremental architecture / stdlib migration spec / consuming design for parametric Workflow Lisp
Created: 2026-06-03
Scope: `review-revise-loop` first; later reusable review/revise/fix orchestration forms with the same shape.

Related docs:

- `docs/design/workflow_lisp_refactor_architecture.md`
- `docs/plans/2026-05-23-workflow-lisp-refactoring-backlog.md`
- `docs/plans/2026-06-02-workflow-lisp-low-hanging-refactor-plan.md`
- `docs/plans/2026-06-02-workflow-lisp-generic-orc-expansion-refactor.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-owner-seam-split-prerequisite/implementation_architecture.md`
- `docs/design/workflow_lisp_compile_time_parametric_specialization.md`
- `docs/design/workflow_lisp_structural_parametric_constraints.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/lisp_frontend_review_fix_loops.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/plans/2026-06-01-review-revise-loop-stdlib-feasibility-proof.md`
- `specs/dsl.md`

## 1. Purpose

This document records the target-delta architecture and implementation history
for moving `review-revise-loop` from a compiler-special Workflow Lisp form into
an ordinary imported `.orc` standard-library component.

The implemented first-tranche contract has been promoted into
`docs/design/workflow_lisp_frontend_specification.md`. That frontend
specification is now the baseline authority for current behavior. This document
remains useful for migration rationale, prerequisite ordering, optional
extensions, open questions, and the design-gap trail that produced the current
route.

This document is self-contained with respect to the prerequisite refactoring. It
incorporates the recommended behavior-preserving refactor preflight, the generic
`.orc` expansion Track A, and the minimal parametric type-system work needed
before the thin-macro parity bridge can be retired in favor of ordinary generic
stdlib code.

This document does not by itself promote any YAML primary to `.orc`. The
key-migration parity architecture remains the authority for promotion evidence
and non-regressive parity. The review/revise compiler bridge has been retired
for the promoted frontend route, but YAML-primary replacement still requires
machine-computed parity evidence.

This document does not replace the refactor architecture. The refactor
architecture remains the primary source for behavior-preserving frontend
refactor boundaries: module ownership, traversal, context objects, lowering
splits, registries, cleanup, and verification. That architecture says the
refactor is not a language redesign and must preserve authored `.orc` semantics,
generated workflow behavior, runtime execution semantics, diagnostics, source
maps, effect visibility, and validation behavior.

This document also does not turn the general refactoring backlog into feature
work. The backlog explicitly says missing language features and missing shared
contracts should remain tracked by design-gap work, while the backlog itself is
about reducing maintenance cost without changing `.orc` language behavior or
weakening diagnostics, source provenance, type safety, effect visibility, or
lowering correctness.

The review/revise-loop migration therefore has three distinct classes of work:

Class A: behavior-preserving refactor preflight
: Make the frontend safe to extend without semantic drift.

Class B: generic `.orc` expansion substrate
: Make imported `.orc` definitions expand, typecheck, preserve effects/source
  maps, specialize compile-time refs, and lower through the ordinary path.

Class C: missing language/type-system features
: Add only the minimal generic loop exhaustion-authoring surface, authored
  loop-state, ProcRef, and structural-parametric support required to express
  `review-revise-loop` as stdlib code.

`review-revise-loop` itself should not be implemented as stdlib until Class A
and the relevant Class B substrate have landed.

## 2. Executive Decision

Implement this follow-on convergence in the following order after the active
parity tranche lands, or if the migration-parity architecture is explicitly
revised to adopt the parametric route:

1. Add this integration document as the target architecture.
2. Behavior-preserving refactor preflight:
   - fix concrete hazards;
   - add characterization coverage;
   - decide the lowering package/facade boundary;
   - land the selected owner-seam split when procedure seams still live only in
     oversized public facades;
   - decompose `lowering/core.py` by lowering family when it remains the
     mixed owner for non-procedure lowering behavior after the owner-seam split;
   - decompose `typecheck.py` by typechecking family before structural
     constraints or parametric specialization add more behavior there;
   - introduce shared expression traversal coverage;
   - optionally add `TypecheckContext` and coherent lowering helper extraction
     where needed.
3. Generic `.orc` expansion Track A:
   - `FormKind` / `FormSpec` registry;
   - reserved macro names derived from the registry;
   - registry-routed elaboration;
   - architectural denylist tests;
   - tiny imported `.orc` expansion;
   - imported-source source maps;
   - imported effect visibility;
   - generic compile-time ProcRef specialization.
4. Minimal parametric feature substrate:
   - authored/imported `loop/recur :on-exhausted` plus typed exhaustion
     projection;
   - authorable parametric loop-frame state for imported generic `.orc`;
   - `:forall` and monomorphic helper specialization;
   - structural record/union constraints;
   - ordinary `ProcRef` parameter typing over signatures that mention
     specialized type parameters;
   - variant-proof preservation through `match`.
5. `std/phase.orc` `review-revise-loop`:
   - caller-owned completed/input records;
   - exact stdlib-owned `ReviewLoopResult`;
   - compile-time review/fix ProcRefs;
   - ordinary `loop/recur` + `match` + projection lowering;
   - evidence identity carried by state/inputs.
6. Remove or quarantine the old promoted-path compiler special case:
   - `ReviewReviseLoopExpr`;
   - `_elaborate_review_revise_loop`;
   - review-loop-specific typecheck branches;
   - review-loop-specific lowerer branches;
   - reserved macro treatment that blocks stdlib ownership.
7. Continue broader cleanup backlog after the semantic route is stable.

The generic `.orc` expansion refactor already defines a two-track migration:
Track A is the architectural substrate, and Track B is review-loop compatibility.
Track A includes the form registry, reserved-name derivation, registry-routed
elaboration, denylist tests, generic imported `.orc` expansion, source maps,
imported-effect visibility, and generic ProcRef specialization; that plan
explicitly says Track A must land first or Track B risks becoming another
hand-coded migration path.

Until the migration-parity architecture is revised, that same Track A substrate
still feeds the accepted thin macro bridge for the active rescue slice. The
parametric `defproc` route in this document is the intended follow-on
replacement, not a second concurrent authority for the current tranche.

## 3. Problem

`review-revise-loop` currently behaves like a high-level reusable workflow
abstraction, but the promoted path still depends on compiler logic that knows
the form by name.

That creates five design problems.

First, the compiler contains review-loop-specific semantic knowledge that should
belong either in `.orc` stdlib code or in generic type-system machinery. The
structural-constraints design identifies the current issue directly:
`review-revise-loop` accepts a caller-owned `:returns` union, but the compiler
currently needs to know that the union contains terminal variants such as
`APPROVED`, `BLOCKED`, and `EXHAUSTED`; that structural validation is encoded
directly in Python for one form.

Second, the stdlib lowering contract says the default implementation path for
high-level library forms is ordinary `.orc` stdlib code compiled through shared
effectful composition. It also states that `review-revise-loop` is not accepted
as a compiler-special primitive for the key-workflow migration tranche, and that
its parity path is ordinary stdlib/generic composition emitting executable
surfaces such as `repeat_until`, structured provider results, `match`,
projection/materialization, source maps, and resume-safe loop state.

Third, `review-revise-loop` is only conditionally feasible as ordinary stdlib
code with the current architecture. The stdlib lowering design says the proof
route is a stdlib `defproc` over compile-time ProcRef review/fix hooks plus
generic `loop/recur` exhaustion projection, while the existing
`ReviewReviseLoopExpr` lowerer remains a shape reference, not acceptance
evidence for ordinary stdlib composition.

Fourth, the frontend has accumulated pass-level complexity that makes new forms
easy to miss in some walkers or passes. The refactor architecture names
repeated expression-tree walkers, module-global compiler state, private helper
imports, duplicated registries, and large pass modules as debt patterns; it
warns that the risk is semantic drift, where a future form is parsed and
typechecked but missed by purity checks, extern discovery, ProcRef
specialization, source-map generation, or lowering analysis.

Fifth, if the generic expansion refactor is skipped, a supposed "stdlib"
implementation can become a renamed compiler special case: a macro that emits a
Python-authored AST, a typechecker branch keyed to `review-revise-loop`, or a
lowerer branch that still constructs the review/fix loop directly. The generic
expansion refactor frames the decisive question as whether the implementation is
a generic `.orc` expansion/specialization mechanism usable by arbitrary `.orc`,
or a review-loop-specific compiler branch with a new name.

The desired architecture is:

```text
review-revise-loop
  authored/imported as std/phase.orc code
  reached through the generic form registry/import path
  checked through generic structural constraints
  specialized into a monomorphic helper/private workflow
  lowered through ordinary Core AST and DSL surfaces
  validated by shared validation
  executed by the runtime as ordinary workflow control
```

The prohibited architecture is:

```text
review-revise-loop
  recognized by Python as a magic form
  typechecked by review-loop-specific code
  lowered by a hand-built ReviewReviseLoopExpr branch
  treated by runtime or shared validation as a special concept
```

## 4. Authority And Dependency Direction

### 4.1 This Document Is A Consuming Architecture

This document consumes, but does not redefine:

- behavior-preserving refactor architecture;
- low-hanging refactor execution plan;
- generic `.orc` expansion Track A;
- compile-time parametric specialization;
- structural parametric constraints;
- macro surface contract;
- ProcRef semantics;
- state layout;
- DSL `repeat_until` semantics;
- migration parity policy.

The ownership split is:

`workflow_lisp_refactor_architecture.md`
: Owns behavior-preserving refactor boundaries, traversal/context/lowering/
  registry cleanup principles, module-boundary direction, and preservation
  invariants.

`2026-05-23-workflow-lisp-refactoring-backlog.md`
: Owns the general cleanup backlog, maintenance-cost reduction goals, and the
  separation between refactor work and missing feature work.

`2026-06-02-workflow-lisp-low-hanging-refactor-plan.md`
: Owns the first behavior-preserving implementation tranche, concrete hazards,
  characterization coverage, lowering package/facade decision, shared
  expression traversal utility, lowering extern/type helper extraction, and
  package-root narrowing.

`docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-owner-seam-split-prerequisite/implementation_architecture.md`
: Owns the dedicated prerequisite slice that lands the exact post-split owner
  modules required by Sections 8.1, 9.4, and Stage 1 whenever those seams still
  live only inside oversized public facades.

`2026-06-02-workflow-lisp-generic-orc-expansion-refactor.md`
: Owns Track A generic `.orc` expansion substrate, form registry and extension
  boundary, denylist tests for old review-loop special casing, imported `.orc`
  expansion/source-map/effect visibility, and generic ProcRef specialization
  substrate.

`workflow_lisp_key_migration_parity_architecture.md`
: Owns the active review-loop rescue tranche. It currently requires generic
  `.orc` expansion plus a thin macro or equivalent monomorphic-helper bridge and
  explicitly does not require parametric imported `defproc` support in that
  tranche.

`workflow_lisp_compile_time_parametric_specialization.md`
: Owns `:forall` type parameters, call-site type resolution, concrete
  monomorphic helper/private-workflow specialization, specialization identity,
  runtime erasure of type parameters, compile-time-only ProcRef treatment,
  first-tranche generic clause ordering (`:forall`, parameter list, `:where`,
  return type), the accepted first-tranche pipeline (`constraint check ->
  instantiate -> typecheck instantiated helper -> lower`), and source-map
  obligations for generated specializations. Pre-instantiation generic-body
  checking remains deferred follow-on diagnostic work rather than a tranche-one
  acceptance gate.

`workflow_lisp_structural_parametric_constraints.md`
: Owns `has-field` constraints, `has-union-variant` constraints,
  `has-shared-union-field` constraints, `is-record` / `is-union` constraints,
  variant-proof preservation, and diagnostics for unsatisfied constraints.

This document owns the review/revise stdlib follow-on replacement sequence once
the parity tranche is ready to retire the thin bridge, which refactor work is
prerequisite versus follow-up cleanup, the exact first-tranche
`ReviewFindings` carrier, minimum `ReviewFindings.v1` artifact envelope,
`ReviewDecision` / `ReviewLoopResult` stdlib schemas, the
`std/phase.orc` `review-revise-loop` API shape,
approve/revise/blocked/exhausted routing semantics, evidence-authority rules,
loop/recur exhaustion projection requirement, fixture and promotion matrix, and
removal of `ReviewReviseLoopExpr` from the promoted path.

### 4.2 Target Dependency Direction

The three parametric design docs consume one first-tranche specialization rule:

```text
resolve concrete call-site types
  -> check explicit structural constraints
  -> instantiate a monomorphic helper/private workflow
  -> typecheck the instantiated helper
  -> lower through ordinary Core AST, shared validation, and existing runtime
```

That rule keeps `review-revise-loop` on ordinary imported `.orc` stdlib code
plus generic language machinery. It also fixes diagnostic ownership for this
tranche: unsatisfied structural constraints fail against the generic definition
and call site, while ordinary typing, proof-gated union behavior, effect
visibility, and lowering correctness are checked on the instantiated helper.
For the author-facing/internal terminology pairing, see "Pattern Matching" in
`docs/design/workflow_lisp_frontend_specification.md`. Pre-instantiation
generic-body checking is intentionally deferred.

Target dependency direction:

```text
public syntax
  -> optional thin macro
  -> imported std/phase.orc definition
  -> generic macro/procedure expansion
  -> generic typechecking and structural constraints
  -> compile-time specialization
  -> ordinary Core AST
  -> shared validation
  -> executable workflow DSL
```

Prohibited dependency direction:

```text
public syntax
  -> parser recognizes review-revise-loop
  -> ReviewReviseLoopExpr
  -> review-loop-specific typechecker branch
  -> review-loop-specific lowerer hand-builds match/loop/projection tree
  -> executable workflow DSL
```

## 5. Goals

- Make `review-revise-loop` ordinary imported stdlib code rather than a compiler
  primitive.
- Do the minimum behavior-preserving refactor preflight before adding new generic
  expansion or type-system behavior.
- Land generic `.orc` expansion Track A before review-loop compatibility work.
- Preserve review decisions as workflow-control authority.
- Preserve typed state and validated artifacts as semantic authority.
- Allow caller-specific records and result unions without compiler branches keyed
  to review-loop names.
- Keep ProcRef, provider refs, prompt refs, type parameters, and
  helper-generation details compile-time-only.
- Preserve provider and command effects after specialization.
- Preserve source-map provenance for authored code, imported stdlib code,
  generated helpers, generated paths, and selected ProcRef bodies.
- Make loop exhaustion an explicit typed terminal result, not hidden failed
  control flow.
- Keep runtime execution Lisp-agnostic: the runtime executes generated DSL
  surfaces, not a special review-loop primitive.
- Provide an incremental path that can coexist with the current legacy bridge
  until parity fixtures pass.

## 6. Non-Goals

This design does not add:

- runtime closures;
- runtime procedure values;
- runtime type values;
- runtime multiple dispatch;
- provider refs in runtime state;
- prompt refs in runtime state;
- implicit structural duck typing at workflow runtime;
- report parsing as semantic state;
- pointer-file choreography as semantic state;
- hidden command adapters for review/revise routing;
- broad style cleanup unrelated to this migration.

This design also does not require every backlog item to finish before
`review-revise-loop` moves to stdlib. The backlog is broader than this migration
and explicitly warns against using refactor cleanup to implement missing language
features.

## 7. Architecture Invariants

A promoted stdlib review loop must satisfy these invariants:

- Structured bundles and typed artifacts are authority.
- Reports, debug YAML, stdout, pointer files, and source maps are views unless a
  specific contract says otherwise.
- Review decisions route workflow control.
- `REVISE` is not completion.
- `EXHAUSTED` is explicit typed non-completion.
- Evidence identities are carried by state or inputs.
- Review-provider output cannot redirect carried evidence identity.
- All generated effects are visible.
- All generated statements and paths are source-mapped.
- All generated paths are deterministic and collision-safe.
- No runtime ProcRef, provider ref, prompt ref, type parameter, closure, or type
  object exists.
- The runtime executes generic DSL surfaces, not Lisp-specific review-loop
  behavior.
- Shared validation remains authoritative after lowering.

## 8. Refactor Prerequisite Model

The refactor work has three tiers.

### 8.1 Hard Preflight Before Track A

The following refactors are hard prerequisites before relying on generic `.orc`
expansion Track A:

- P0.1 Fix concrete review hazards.
- P0.2 Add characterization coverage for affected pass boundaries.
- P0.3 Decide the lowering package/facade boundary before extracting Track A
  helpers.
- P0.4 Introduce shared expression traversal coverage and migrate low-risk
  walkers.
- P0.5 Keep maintained Python frontend modules at or below 2,000 physical lines
  per file, or split them before adding new Track A/type-system behavior.

If a follow-on slice needs to add behavior in seams that are still owned only by
oversized public facades, that follow-on slice is blocked until a dedicated
owner-seam split prerequisite lands. The minimum owner-seam split for this
route must establish explicit post-split owners for:

- procedure-call typechecking integration;
- specialization discovery and materialization integration;
- procedure-call lowering, provenance, and lowering-boundary runtime-erasure
  checks.

For selection and planning purposes, treat that owner-seam split as a distinct
prerequisite gap rather than as incidental cleanup inside the blocked follow-on
feature slice. The intended prerequisite gap id is
`workflow-lisp-owner-seam-split-prerequisite`; future Track A or parametric
plans should route to that gap first whenever the required seam owners have not
already landed.

After that owner-seam split lands, do not treat the rest of
`lowering/core.py` as complete merely because the procedure-specific seams moved
out. If `lowering/core.py` remains a large mixed owner for provider/command
effects, records/unions/projection, control-flow lowering, workflow calls,
source-map/origin bookkeeping, stdlib/temp intrinsic lowering, and validation
remapping, the next refactor target is a separate family-decomposition gap. The
intended gap id is `workflow-lisp-lowering-core-family-decomposition`.

That follow-on gap is a target-delta obligation whenever later Track A,
parametric, or stdlib-review-loop work would otherwise add behavior to
`lowering/core.py`. It should split by semantic lowering family behind the
stable `orchestrator.workflow_lisp.lowering` facade, not by arbitrary line
ranges.

If a Track A, structural-constraints, loop-state, or other parametric
follow-on slice reaches a blocked run and fresh checkout evidence still shows
that these non-procedure lowering families have not been decomposed, the
blocked slice is not the surface to widen or repair. The next required
artifact is a standalone prerequisite architecture at
`docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-lowering-core-family-decomposition/implementation_architecture.md`,
and the blocked follow-on slice should stop after routing that prerequisite
rather than editing its own feature architecture or implementation plan as if
the owner split had already landed.

`typecheck.py` has the same status for structural constraints and parametric
specialization. If it remains the mixed owner for expression dispatch,
review-loop bridge validation, stdlib specialization typing, proof/field
helpers, command validation, workflow-ref checks, `let-proc` handling, lint
raising, and diagnostics, the next refactor target before structural-parametric
work is a separate typecheck-family decomposition gap. The intended gap id is
`workflow-lisp-typecheck-family-decomposition`.

That gap should introduce `TypecheckContext` or an equivalent explicit context
boundary, then split semantic typechecking families behind the stable
`orchestrator.workflow_lisp.typecheck` compatibility surface. It is a
target-delta obligation whenever structural constraints, parametric
specialization, imported `.orc` expansion, or stdlib-review-loop work would
otherwise add behavior directly to `typecheck.py`.

If a structural-constraints or other parametric follow-on slice reaches a
blocked run and fresh checkout evidence still shows that this mixed-owner state
has not been decomposed, the blocked slice is not the surface to widen or
repair. The next required artifact is a standalone prerequisite architecture at
`docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-typecheck-family-decomposition/implementation_architecture.md`,
and the blocked follow-on slice should stop after routing that prerequisite
rather than editing its own feature architecture or implementation plan as if
the owner split had already landed.

Shared expression traversal has the same status for duplicated pass-local
walkers. If `orchestrator/workflow_lisp/expression_traversal.py` or an
equivalent shared update point is still missing, the next refactor target
before Track A, loop-state, or other parametric follow-on work is a separate
traversal prerequisite gap. The intended gap id is
`workflow-lisp-expression-traversal-prerequisite`.

That gap should establish one small shared owner for `iter_child_exprs` /
`walk_expr`, migrate the low-risk walkers named in Section 9.7, and add the
coverage-style assertion that every current `ExprNode` union member is either
traversed by the shared helper or explicitly classified as leaf/specialized. It
is a target-delta obligation whenever Track A, parametric, or stdlib
review-loop work would otherwise add or update duplicated expression walking in
`functions.py`, `compiler.py`, ProcRef specialization discovery, or lowering
adjacent helpers.

If a Track A, loop-state, or other parametric follow-on slice reaches a blocked
run and fresh checkout evidence still shows that this shared traversal update
point has not landed, the blocked slice is not the surface to widen or repair.
The next required artifact is a standalone prerequisite architecture at
`docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-expression-traversal-prerequisite/implementation_architecture.md`,
and the blocked follow-on slice should stop after routing that prerequisite
rather than editing its own feature architecture or implementation plan as if
shared traversal had already landed.

Rationale: these items reduce the chance that a new generic expansion path is
parsed, elaborated, or typechecked correctly while being missed by purity checks,
extern discovery, ProcRef discovery, source maps, or lowering analysis.
The module-size cap is a refactor-safety rule, not a language semantic rule:
large compiler modules are harder to characterize, review, and extend without
accidentally adding another hidden special case.

### 8.2 Strongly Recommended Before Structural Parametric Work

The following refactors are strongly recommended before implementing structural
constraints and parametric specialization:

- R1 Introduce `TypecheckContext` or equivalent explicit context object.
- R2 Extract coherent lowering extern-discovery helpers.
- R3 Extract lowering-time type helpers.
- R4 Clarify source-map/build-artifact ownership.

These are not all hard gates for the first Track A fixtures, but they become
increasingly important once generic type parameters, variant proof, specialized
helpers, and imported ProcRef bodies are introduced.

### 8.3 Follow-Up Cleanup After Semantic Migration

The following backlog items should continue after the stdlib review-loop route
is stable:

- F1 Diagnostic builder consolidation.
- F2 Pass-local validation helper consolidation.
- F3 Package-root API narrowing.
- F4 Fixture-only code movement.
- F5 Migration scaffolding audit.
- F6 Module dependency audit.

Do not block review-loop stdlib migration on broad cleanup unless a specific
item affects the migration's correctness.

## 9. Hard Preflight: Behavior-Preserving Refactor Tranche

### 9.1 Fix Concrete Hazards

Before adding a generic expansion substrate, fix the concrete hazards called out
by the low-hanging refactor plan:

- remove shadowed duplicate lowering helpers;
- fix missing private-workflow `VariantCaseTypeRef` import or equivalent type
  reference;
- make `defun` purity checking fail closed for unknown `ExprNode` containers;
- guard macro hygiene shape assumptions so malformed macro output preserves
  provenance.

Acceptance:

- `python -m compileall orchestrator/workflow_lisp`
- `pytest tests/test_workflow_lisp_functions.py tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_lowering.py -q`
- `git diff --check`

Any pre-existing failures must be recorded with exact command output before
continuing.

### 9.2 Add Characterization Coverage

Add focused behavior assertions for pass boundaries that Track A and review-loop
stdlib migration depend on:

- provider-result structured outputs;
- command-result structured outputs;
- match variant proof and narrowing;
- loop/recur lowering;
- phase stdlib forms;
- resource/drain stdlib forms;
- workflow calls and workflow references;
- source-map origin serialization;
- validation-error remapping.

Acceptance:

- tests assert important generated boundaries exist;
- tests assert output contract kind where relevant;
- tests assert source-map origin exists for at least one generated step per
  family;
- tests assert workflow call targets remain present inside lowered
  loop/control-flow bodies;
- tests do not snapshot entire lowered workflows unless unavoidable.

### 9.3 Decide Lowering Package/Facade Boundary

Decide before extracting Track A helpers whether
`orchestrator/workflow_lisp/lowering.py` becomes a `lowering/` package facade or
remains a file with sibling helper modules for this tranche.

The low-hanging plan explicitly says Python cannot have both
`orchestrator/workflow_lisp/lowering.py` and an
`orchestrator/workflow_lisp/lowering/` package with the same import path, so this
structure decision should happen before helper extraction. It recommends
converting `lowering.py` into a package facade if the pure move is low-risk,
with sibling helper modules as the fallback only if package conversion causes
import instability.

Acceptance:

- lowering import inventory is recorded;
- package facade or sibling fallback is chosen;
- `orchestrator.workflow_lisp.lowering` remains the public import facade;
- maintained Python modules under `orchestrator/workflow_lisp/` touched by this
  migration are at or below 2,000 physical lines, excluding generated files,
  fixtures, and temporary migration evidence;
- any currently larger touched module is split behind the existing public import
  facade before new generic expansion or type-system behavior is added there;
- no behavior changes occur in the pure move;
- focused lowering tests pass.

### 9.4 Split Oversized Public Facade Owner Seams Before New Type-System Work

When the relevant seams still live only inside oversized public facades such as
`typecheck.py`, `compiler.py`, or `lowering.py`, the next prerequisite is not
Track A or parametric feature work. The next prerequisite is a dedicated
behavior-preserving owner-seam split that moves those responsibilities behind
the existing public facade before new generic-expansion or type-system behavior
lands there.

That prerequisite is not merely an acceptance note on the broader low-hanging
refactor tranche. It is a standalone prerequisite gap for selection and
handoff: `workflow-lisp-owner-seam-split-prerequisite`. If a blocked run shows
that the required seams still live only in the public facades, the next action
is to select or draft that gap rather than reopening the blocked Track A or
parametric slice.

This prerequisite may use a package facade or sibling helper modules, but the
result must make the seam ownership explicit enough that follow-on feature plans
can target a stable owner module instead of extending the public coordination
facade directly.

Required seam ownership after the split:

- procedure-call typechecking integration has an exact owner file path;
- specialization discovery and materialization integration has an exact owner
  file path;
- procedure-call lowering, provenance, and lowering-boundary runtime-erasure
  checks have an exact owner file path.

Acceptance:

- the exact post-split owner file path is recorded for each required seam;
- the public facades remain compatibility/import facades rather than the only
  seam owners;
- touched owner modules for those seams are at or below 2,000 physical lines,
  or are split again before new Track A or parametric/type-system behavior is
  added there;
- follow-on Track A or parametric plans cite the landed owner-module paths
  rather than naming only the public facade.

### 9.5 Decompose `lowering/core.py` By Lowering Family

After `workflow-lisp-owner-seam-split-prerequisite` lands, the remaining
`lowering/core.py` coordinator must not become the default home for every new
lowering feature. If it still owns multiple unrelated lowering families, draft
and run a separate behavior-preserving decomposition gap before adding new
Track A, parametric, or stdlib-review-loop behavior to those families.

The intended follow-on gap id is
`workflow-lisp-lowering-core-family-decomposition`.

The split should preserve the public facade:

- `orchestrator.workflow_lisp.lowering` remains the stable public import;
- `lowering/core.py` remains the coordinator for public lowering entrypoints,
  workflow ordering, and validation handoff;
- family modules own the actual behavior for their semantic area.

Initial target family owners:

- `lowering/origins.py` for lowering origins, source-map coverage, validation
  subject bindings, and generated semantic-effect provenance;
- `lowering/context.py` for lowering context/result structs and active lowering
  scope state;
- `lowering/effects.py` for `provider-result`, `command-result`, command
  boundary handling, and effect-output materialization;
- `lowering/control.py` for `let*`, `if`, `match`, and `loop/recur`
  integration;
- `lowering/values.py` for records, unions, projections, materialization, and
  output contract field construction;
- `lowering/workflow_calls.py` for workflow calls, workflow refs, callee
  specialization, and lowered-callee dependency integration;
- existing `lowering/procedures.py` remains the procedure lowering owner.

Acceptance:

- the family modules above exist or the implementation architecture records a
  narrower equivalent owner map with rationale;
- `lowering/core.py` no longer contains the real implementations for every
  major lowering family;
- `lowering/core.py` stays below the maintained-module line cap or records an
  explicit residual split target before more lowering behavior is added there;
- public imports through `orchestrator.workflow_lisp.lowering` remain
  compatible;
- focused lowering, source-map, validation-remapping, procedure, workflow-ref,
  provider/command, match/loop, and structured-result tests pass or any
  pre-existing unrelated failures are recorded with exact evidence.

#### 9.5.1 Prerequisite Handoff Contract

Treat `workflow-lisp-lowering-core-family-decomposition` as a first-class
design gap that can be selected and drafted independently of the blocked
feature slice it unblocks.

Selection trigger:

- fresh checkout evidence still shows `lowering/core.py` as the mixed owner
  for the lowering families named above;
- the expected post-split owner modules do not yet exist with recorded paths;
- a follow-on slice would otherwise add new lowering behavior, especially
  Track A imported `.orc` expansion, loop-state carrier lowering, parametric
  projection/materialization work, or stdlib review-loop lowering, to the
  mixed `lowering/core.py` surface.

Required drafting output:

- one bounded implementation architecture at
  `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-lowering-core-family-decomposition/implementation_architecture.md`;
- explicit owner-file paths for lowering context/result structs, lowering
  origins and validation-subject provenance, provider/command effect lowering,
  control-flow lowering, record/union/projection lowering, workflow-call
  lowering, and the residual coordinator responsibilities left in
  `lowering/core.py`;
- acceptance that preserves current lowering behavior, diagnostics remapping,
  source-map provenance, effect visibility, shared-validation handoff, and the
  public `orchestrator.workflow_lisp.lowering` import surface;
- focused verification proving the split is behavior-preserving before any
  Track A, loop-state, structural-constraints, or other parametric follow-on
  work resumes.

Unblock rule:

- Track A follow-ons, loop-state authoring, structural constraints, and stdlib
  review-loop follow-ons that need new lowering behavior stay blocked until
  this prerequisite lands;
- after it lands, any previously blocked lowering-dependent bundle must be
  refreshed against the actual post-decomposition owner map before a new
  executable implementation plan is approved.

### 9.6 Decompose `typecheck.py` By Typechecking Family

Before structural constraints or parametric specialization add more behavior to
`typecheck.py`, split the current mixed typechecker into explicit family owners
behind the existing `orchestrator.workflow_lisp.typecheck` compatibility
surface.

The intended follow-on gap id is
`workflow-lisp-typecheck-family-decomposition`.

The split should preserve current diagnostics, spans, form paths, expansion
stacks, effect summaries, proof behavior, and public imports. It should not
change Workflow Lisp semantics.

Initial target family owners:

- `typecheck/context.py` or equivalent for `TypecheckContext`, active catalogs,
  reusable-state context, active workflow signature, and shared diagnostic
  helpers;
- `typecheck/dispatch.py` or equivalent for the top-level expression dispatcher
  and family routing;
- `typecheck/proofs.py` for `ProofScope`, variant proof facts, field/projection
  proof checks, and variant-field access diagnostics;
- `typecheck/effects.py` for provider/command effect validation, command argv
  validation, certified-adapter checks, and effect compatibility helpers;
- `typecheck/calls.py` for workflow refs, workflow calls, function calls, and
  callable argument compatibility not already owned by procedure-specific
  modules;
- existing `procedure_typecheck.py` remains the procedure-call and generated
  procedure typing owner;
- a legacy/std-bridge owner, if still needed, isolates review-loop bridge and
  `StdlibSpecializationExpr` typing until the promoted stdlib route removes
  that path.

Acceptance:

- the family modules above exist or the implementation architecture records a
  narrower equivalent owner map with rationale;
- `typecheck.py` remains a compatibility/coordinator surface rather than the
  real owner for every major typechecking family;
- `typecheck.py` stays below the maintained-module line cap or records an
  explicit residual split target before more typechecking behavior is added
  there;
- diagnostics remain stable for representative failures in command validation,
  workflow/procedure calls, variant proof, `let-proc`, stdlib specialization,
  and reusable-state typechecking;
- focused typecheck, procedure, workflow-ref, phase-stdlib, command-adapter,
  and structural-result tests pass or any pre-existing unrelated failures are
  recorded with exact evidence.

#### 9.6.1 Prerequisite Handoff Contract

Treat `workflow-lisp-typecheck-family-decomposition` as a first-class design
gap that can be selected and drafted independently of the blocked structural
feature slice it unblocks.

Selection trigger:

- fresh checkout evidence still shows `typecheck.py` as the mixed owner for the
  families named above;
- the expected post-split owner modules do not yet exist with recorded paths;
- a follow-on slice would otherwise add new typing behavior, especially the
  structural-constraints shared-field hook, to the mixed `typecheck.py`
  surface.

Required drafting output:

- one bounded implementation architecture at
  `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-typecheck-family-decomposition/implementation_architecture.md`;
- explicit owner-file paths for shared typecheck context/diagnostic helpers,
  dispatcher routing, proof/field validation, provider/command validation,
  callable checks, and any remaining legacy/std-bridge typing;
- acceptance that preserves current diagnostics, source spans, expansion
  stacks, proof behavior, effect visibility, and the public
  `orchestrator.workflow_lisp.typecheck` import surface;
- focused verification proving the split is behavior-preserving before any
  structural-constraints or other parametric follow-on work resumes.

Unblock rule:

- structural constraints, imported `.orc` expansion follow-ons, and stdlib
  review-loop follow-ons that need new typechecking behavior stay blocked until
  this prerequisite lands;
- after it lands, any previously blocked structural-constraints bundle must be
  refreshed against the actual post-decomposition owner map before a new
  executable implementation plan is approved.

### 9.7 Introduce Shared Expression Traversal

Introduce a small shared traversal utility before adding more expression forms or
expansion outputs.

Required helper surface:

```python
def iter_child_exprs(expr: ExprNode) -> tuple[ExprNode, ...]:
    ...


def walk_expr(expr: ExprNode) -> Iterator[ExprNode]:
    ...
```

Required coverage:

- `LetStarExpr`
- `MatchExpr`
- `IfExpr`
- `RecordExpr`
- `ProviderResultExpr`
- `CommandResultExpr`
- `ProduceOneOfExpr`
- `ResumeOrStartExpr`
- `ResourceTransitionExpr`
- `BacklogDrainExpr`
- review-loop legacy node, if still present
- leaf expressions

The low-hanging plan calls expression traversal duplicated across multiple files
the highest-leverage refactor after immediate hazards, and requires a
coverage-style assertion that every current `ExprNode` union member is either
covered by traversal or explicitly classified as leaf/specialized.

Use traversal first in low-risk locations:

- function dependency scanning;
- provider/prompt extern collection;
- ProcRef specialization discovery where current environment handling is
  preserved;
- workflow extern collection if mechanical;
- let-proc escape/value-use checks only if scoped behavior remains obvious.

Do not force scoped walkers into the helper if doing so hides important scope
changes.

#### 9.7.1 Prerequisite Handoff Contract

Treat `workflow-lisp-expression-traversal-prerequisite` as a first-class design
gap that can be selected and drafted independently of the blocked follow-on
slice it unblocks.

Selection trigger:

- fresh checkout evidence still shows
  `orchestrator/workflow_lisp/expression_traversal.py` missing, or shows no
  narrower equivalent shared update point with recorded owner path;
- duplicated expression walking is still required across `functions.py`,
  `compiler.py`, ProcRef specialization discovery, or lowering-adjacent helper
  paths;
- a follow-on slice would otherwise add a new expression form or update an
  existing walker, especially for Track A imported `.orc` expansion,
  loop-state authoring, parametric specialization discovery, or stdlib
  review-loop follow-ons.

Required drafting output:

- one bounded implementation architecture at
  `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-expression-traversal-prerequisite/implementation_architecture.md`;
- explicit owner-file path for the shared traversal helper surface and the
  first low-risk adopter sites migrated to it;
- acceptance that preserves current `.orc` semantics, diagnostics, source-map
  provenance, ProcRef discovery behavior, and public frontend import surfaces;
- focused verification proving the shared helper covers the intended `ExprNode`
  variants and that unknown containers fail closed before any Track A,
  loop-state, or other parametric follow-on work resumes.

Unblock rule:

- Track A follow-ons, loop-state authoring, and stdlib review-loop follow-ons
  that need shared expression walking stay blocked until this prerequisite
  lands;
- after it lands, any previously blocked bundle that depends on shared
  traversal must be refreshed against the landed owner path and migrated
  adopter set before a new executable implementation plan is approved.

## 10. Track A: Generic `.orc` Expansion Substrate

Track A begins only after the hard preflight is complete.

### 10.1 Form Registry

Add a formal registry that classifies every compiler-known head.

Illustrative shape:

```python
class FormKind(Enum):
    CORE_SPECIAL = "core_special"
    CORE_EFFECT = "core_effect"
    STDLIB_EXTENSION = "stdlib_extension"
    TEMP_COMPILER_INTRINSIC = "temp_compiler_intrinsic"


@dataclass(frozen=True)
class FormSpec:
    name: str
    kind: FormKind
    owner: str
    introduced_in: str
    remove_by: str | None = None
    allowed_in_macro_definition: bool = True
    elaborator: str | None = None
    rationale: str = ""
```

Initial classification should be explicit and reviewable:

CORE_SPECIAL:
: `record`, `let*`, `if`, `match`, `call`, `proc-ref`, `workflow-ref`,
  `loop/recur`, `continue`, `done`.

CORE_EFFECT:
: `provider-result`, `command-result`, and other runtime bridge forms that
  directly lower to workflow execution effects.

STDLIB_EXTENSION:
: `review-revise-loop`.

TEMP_COMPILER_INTRINSIC:
: `run-provider-phase`, `produce-one-of`, `resume-or-start`,
  `resource-transition`, `finalize-selected-item`, `backlog-drain`, and other
  high-level forms still needing compiler help until ordinary `.orc` routes
  exist.

The generic expansion refactor gives the same registry direction: classify heads
as core language forms, core effect bridges, standard-library extensions, or
temporary compiler intrinsics scheduled for deletion; derive macro reserved
names from that registry or check parallel lists against it.

### 10.2 Registry-Routed Elaboration

Replace ad hoc head dispatch with registry dispatch.

Intermediate dispatch shape:

```python
spec = FORM_REGISTRY.get(head.resolved_name)

if spec is None:
    return elaborate_callable_or_name_reference(...)

if spec.kind is FormKind.STDLIB_EXTENSION:
    return elaborate_stdlib_extension_reference(...)

if spec.kind is FormKind.TEMP_COMPILER_INTRINSIC:
    warn_or_require_allowlisted_intrinsic(spec, datum)

return spec.elaborator(...)
```

The registry is not a new semantic engine. It is an extension boundary that
forces every compiler-known head to declare why the compiler knows it.

For `review-revise-loop`, the promoted route must be:

```text
head resolves as stdlib extension or imported binding
  -> imported .orc expansion/call
  -> ordinary typecheck/lowering
```

Not:

```text
head == "review-revise-loop"
  -> ReviewReviseLoopExpr
  -> review-loop-specific typecheck/lowering
```

### 10.3 Architectural Denylist Tests

Add tests that fail if promoted review-loop compilation uses semantic
review-loop compiler artifacts.

Denylisted artifacts:

- `ReviewReviseLoopExpr`
- `_elaborate_review_revise_loop`
- `__review-revise-loop__`
- `_lower_review_revise_loop`
- `_validate_review_loop_result_contract`
- typechecker branch keyed directly to `review-revise-loop`
- lowerer branch keyed directly to `review-revise-loop`
- compiler visitor logic keyed directly to `review-revise-loop`
- reserved macro treatment that prevents imported stdlib ownership

The generic expansion refactor explicitly lists these regression guards and says
the old branch may remain temporarily only as a shape oracle for golden fixtures,
not as the accepted semantic route.

### 10.4 Temporary Syntax Compatibility Shim

A temporary compatibility shim is allowed if public `(review-revise-loop ...)`
syntax cannot immediately become an imported macro because the current macro
system reserves the name.

Acceptable:

```python
def expand_review_revise_loop_compat(form: SyntaxList) -> SyntaxList:
    return SyntaxList(
        [introduced_identifier("std.phase/review-revise-loop"), ...],
        span=form.span,
        expansion_stack=push_expansion_frame(...),
    )
```

Unacceptable:

```python
def expand_review_revise_loop_compat(form):
    return ReviewReviseLoopExpr(...)


def lower_review_revise_loop(expr):
    return hand_built_match_loop_tree(...)
```

The compatibility shim must have a registry `remove_by` condition. Once imported
`.orc` macros can own the public name cleanly, remove the shim and unreserve
`review-revise-loop`.

### 10.5 Generic Expansion Metadata

If the compiler needs an internal expansion carrier, it must be generic.

Allowed carrier shape:

```python
@dataclass
class OrcExpansion:
    parsed_expansion_ast: ExprNode
    authored_call_site: SourceSpan
    imported_definition_source: SourceSpan
    specialization_bindings: Mapping[str, Type | ProcRef]
    generated_allocator_identity: GeneratedAllocatorIdentity
    expansion_stack: ExpansionStack
    source_map_frames: list[SourceMapFrame]
```

Disallowed carrier fields:

- `review_provider`
- `fix_provider`
- `review_prompt`
- `fix_prompt`
- `checks_report`
- `progress_report`
- `APPROVED` / `BLOCKED` / `EXHAUSTED` special schema fields

Preferred lifecycle:

```text
Syntax / frontend AST from imported .orc
  -> expansion engine clones/substitutes with ExpansionFrame metadata
  -> returns ordinary ExprNode
  -> normal typecheck
  -> normal lowering
```

Avoid a durable semantic `ExpandedOrcExpr` variant that downstream typechecking
or lowering must dispatch on. A lasting wrapper can recreate the same
special-case smell one level later.

### 10.6 Generic Imported `.orc` Inline-Procedure Expansion

Build a generic imported `.orc` expansion/specialization operation.

Illustrative operation:

```python
def expand_inline_procedure_call(
    call: ProcedureCallExpr,
    callee: TypedProcedureDef,
    ctx: ExpansionContext,
) -> ExprNode:
    ...
```

Required behavior:

- clone an already parsed/elaborated `.orc` body;
- substitute value parameters hygienically;
- substitute compile-time ProcRef parameters as resolved procedure refs;
- allocate generated names and paths through a shared allocator;
- push source-map frames for caller call site and imported definition;
- return ordinary `ExprNode`;
- re-typecheck the expanded expression through the normal typechecker;
- preserve all provider/command effects introduced by the imported definition.

`review-revise-loop` becomes one caller of this mechanism, not the reason the
mechanism is review-loop-shaped.

### 10.7 Imported Expansion Effect Visibility

Imported `.orc` expansion must preserve effects.

A stdlib helper that invokes `provider-result`, `command-result`, or a ProcRef
whose body invokes provider/command effects must expose those effects to:

typechecking, Semantic IR, shared validation, runtime planning, migration
evidence, and debug/explain output.

Invalid implementation:

```text
macro expands to opaque generated step
effects are known only to the macro implementation
validation cannot see provider/command effects until runtime
```

Valid implementation:

```text
imported definition expands to ordinary provider-result/command-result/call nodes
typechecker and lowering see those nodes normally
effect summaries include imported and selected ProcRef bodies
```

### 10.8 Imported Expansion Source Maps

Source maps must identify:

- authored caller call site;
- imported stdlib definition;
- macro expansion frame, if any;
- specialization arguments;
- generated helper/private workflow;
- generated loop frame;
- generated match arms;
- generated materialization/projection steps;
- generated paths and bundle roots;
- selected ProcRef definitions.

A generated executable node without imported-definition provenance is invalid for
promoted review-loop fixtures.

### 10.9 Track A Fixture Ladder

Track A must be proven before implementing stdlib `review-revise-loop`.

Required fixture order:

1. Static denylist for semantic use of review-loop-specific compiler artifacts.
2. Tiny imported `.orc` procedure with source maps for call site and imported
   definition.
3. Imported `.orc` procedure that emits provider or command effects visible to
   validation.
4. Imported `.orc` procedure that matches a union and uses ordinary variant
   proof.
5. Imported `.orc` procedure that uses the accepted loop form and terminal
   exhaustion projection.
6. Imported `.orc` procedure accepting compile-time ProcRef hooks without
   runtime closures.
7. Evidence-identity negative test.
8. No public hidden write-root input test.
9. Public `review-revise-loop` parity suite through the generic route.

### 10.10 Track A Acceptance Checks

Track A passes when:

- `FormKind` / `FormSpec` registry exists.
- `review-revise-loop` is classified as `STDLIB_EXTENSION` or
  `TEMP_COMPILER_INTRINSIC` scheduled for deletion, not `CORE_SPECIAL`.
- Reserved macro names derive from or are checked against the registry.
- Expression elaboration routes through the registry.
- Denylist tests fail on `ReviewReviseLoopExpr` use in promoted route.
- A tiny imported `.orc` procedure expands and lowers through ordinary
  typecheck/lowering.
- Imported expansion source maps include caller and imported definition.
- Imported expansion effects are visible.
- Imported ProcRef specialization works without runtime closures.
- No review-loop-specific compiler artifact is needed for the generic fixture
  ladder.

Only after Track A passes should the review-loop-specific stdlib implementation
begin.

## 11. Parametric Specialization Dependency

This document depends on compile-time parametric specialization.

The required specialization pipeline is:

```text
generic .orc definition
  -> infer concrete call-site types
  -> check explicit structural constraints
  -> instantiate monomorphic helper/private workflow
  -> typecheck the instantiated AST
  -> lower ordinary Core AST
```

For this design, specialization must provide:

- `:forall` type parameters;
- concrete call-site type resolution;
- compile-time ProcRef resolution;
- monomorphic helper/private-workflow generation;
- deterministic specialization identity;
- source-map frames for generated helpers;
- runtime erasure of type parameters and ProcRefs.

Executable runtime state must not contain:

- unresolved type parameters;
- procedure type values;
- ProcRef values;
- provider refs;
- prompt refs;
- runtime method choices;
- closure environments.

The first stable generic authoring surface here is `defproc`. If lowering later
emits a private/generated workflow, that workflow consumes already-specialized
monomorphic structure; a separate authored generic `defworkflow` surface is
explicitly deferred.

## 12. Structural Constraint Dependency

This document depends on structural parametric constraints.

The first useful constraint set is deliberately small:

```text
T has-field name Type
T has-union-variant VARIANT
T has-union-variant VARIANT (field Type ...)
T has-shared-union-field name Type
T is-record
T is-union
```

In the first tranche, `has-shared-union-field` means every concrete variant of
the specialized union declares the named field with an assignment-compatible
type. It permits only branch-free access to that one field; it does not provide
variant proof or arbitrary constructor authority.

For this design, constraints must support:

- caller-owned `CompletedT` record;
- caller-owned `InputsT` record;
- variant-proof preservation through `match`;
- caller-side projection only under proof;
- constraint failure before lowering.

`review` and `fix` remain ordinary procedure parameters whose declared
`ProcRef[...]` signatures may mention resolved type parameters. Their signature
checks happen in ordinary parameter typing after `CompletedT` and `InputsT`
resolve; they are not part of the first-tranche structural-constraint surface.

Constraint checking must happen before the specialized helper is accepted.
Lowering receives only concrete monomorphic definitions.

### 12.1 Authorable `loop/recur :on-exhausted` Dependency

The blocked Stage 10 implementation showed that ordinary imported `.orc` code
still cannot author the exhaustion route that the target review-loop lowering
assumes. The earlier `loop-recur-bounded-loops` gap intentionally preserved the
shared runtime's existing failure-on-exhaustion semantics and explicitly did
not add a public exhaustion-authoring surface, so that landed slice is not by
itself sufficient for Stage 10.

This dependency is about the public/frontend authoring route for exhaustion
projection, not about runtime `repeat_until` semantics. The runtime already has
`repeat_until.on_exhausted.outputs` for scalar overrides. The missing
prerequisite is the generic `.orc` surface that lets ordinary authored and
imported code request that lowering path without relying on the legacy
Python-owned review-loop bridge to inject `on_exhausted_result_expr` or an
equivalent hidden projection.

Required first-stable contract:

- generic `.orc` code can author `loop/recur :on-exhausted` in both local and
  imported definitions;
- elaboration and typechecking accept the authored exhaustion surface without
  routing through review-loop-specific bridge nodes or request kinds;
- lowering maps scalar exhaustion markers to
  `repeat_until.on_exhausted.outputs` and preserves the shared runtime's
  ordinary failure behavior for body, output-resolution, or predicate failures;
- imported or generated review-loop helpers no longer depend on Python-owned
  injection of `on_exhausted_result_expr` or a review-loop-only fallback path;
- source maps and effect visibility cover the authored exhaustion projection
  route the same way they cover other generic control-flow surfaces.

Selection trigger:

- if a blocked run shows ordinary `loop/recur` still accepts only `:max`,
  `:state`, and one loop-body `fn`, or fresh checkout evidence shows that typed
  exhaustion projection still exists only through the legacy review-loop
  bridge, stop the review-loop slice and select or draft prerequisite gap
  `workflow-lisp-loop-recur-on-exhausted-projection`.

Required drafting output:

- one bounded implementation architecture at
  `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-loop-recur-on-exhausted-projection/implementation_architecture.md`;
- one chosen authored exhaustion surface for `loop/recur`, rather than a
  review-loop-specific compatibility hook;
- fixture coverage proving ordinary local and imported `.orc` code can author
  `:on-exhausted`, preserve failure-vs-exhaustion semantics, and lower through
  shared `repeat_until` without review-loop-only injection.

Unblock rule:

- Stage 10 and any follow-on stdlib review-loop slice that depends on typed
  exhaustion projection stay blocked until this prerequisite lands whenever
  fresh checkout evidence still shows no ordinary authored/imported
  `:on-exhausted` surface.

### 12.2 Authorable Parametric Loop-State Dependency

Once the authored `loop/recur :on-exhausted` prerequisite in Section 12.1
lands, compile-time specialization, structural constraints, and that
exhaustion surface are still not enough by themselves. Ordinary imported `.orc`
code also needs one generic authoring route for the loop-frame state that
carries specialized `CompletedT`, `ReviewReportPath`, `ReviewFindings`,
blocker state, and exhaustion markers across iterations.

This dependency is about authored/frontend surface, not runtime loop semantics.
The runtime already has `repeat_until` state and scalar exhaustion overrides.
The missing prerequisite is the generic `.orc` authoring route that lets an
imported stdlib definition name and type the loop-frame outputs that the final
typed exhaustion projection reads from.

Required first-stable contract:

- generic `.orc` code can author or request a typed loop-frame carrier whose
  concrete fields become monomorphic before ordinary lowering;
- that carrier is available to arbitrary imported `.orc` definitions, not only
  `review-revise-loop`;
- imported generic procedure bodies can pass that carrier through ordinary
  `loop/recur :state`, `continue`, and final typed projection after
  specialization without leaving `TypeParamRef` or other unresolved type
  metadata in loop-state field contracts, loop outputs, or carried state;
- the carrier can hold caller-specialized fields such as
  `completed CompletedT` together with fixed stdlib-owned fields such as
  `latest_review_report ReviewReportPath`, `latest_findings ReviewFindings`,
  `latest_blocker_class BlockerClass`, and `exhaustion_reason String`;
- final typed exhaustion projection reads authored loop-frame outputs rather
  than Python-authored hidden helper state;
- source maps, effect visibility, shared validation, and runtime erasure of
  type parameters, ProcRefs, provider refs, and prompt refs are preserved.

Acceptable first-tranche implementation directions:

- parametric record authoring that specializes before lowering; or
- an equivalent generic loop-owned state-schema surface that ordinary imported
  `.orc` authors can use and that specializes before lowering.

Unacceptable direction:

- review-loop-specific Python synthesis of hidden loop-frame record/state as
  the only promoted route.

This prerequisite owns the authored carrier surface itself. It does not by
itself prove the later imported future-consumer composition used by Stage 10.
Section 12.3 owns that narrower proof once the carrier surface and its
standalone imported generic fixtures exist.

Selection trigger:

- if a blocked run shows Stage 10 still cannot be expressed in ordinary
  imported `.orc` because authored code still cannot declare the generic
  loop-frame carrier after the Section 12.1 exhaustion surface has landed,
  stop the review-loop slice and select or draft prerequisite gap
  `workflow-lisp-parametric-loop-state-authoring`.
- if a blocked run shows the authored carrier surface still cannot pass its own
  standalone imported-generic carrier fixtures, especially with
  `loop_recur_state_type_invalid` or unresolved `TypeParamRef` evidence at the
  loop-state field-contract boundary, treat that failure as the same
  prerequisite still being open rather than as Stage 10 implementation scope.

Required drafting output:

- one bounded implementation architecture at
  `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-parametric-loop-state-authoring/implementation_architecture.md`;
- one chosen authored loop-state surface with rationale, rather than parallel
  competing mechanisms;
- fixture coverage proving an imported generic `.orc` procedure can carry a
  caller-specialized field plus fixed stdlib-owned fields through
  `loop/recur`, then project a typed exhausted result from the last
  materialized loop frame;
- explicit acceptance that the same imported generic fixture lowers without
  unresolved `TypeParamRef` or equivalent unspecialized loop-state field
  contracts reaching ordinary `loop/recur` typing or lowering;
- acceptance that keeps the promoted route free of review-loop-specific hidden
  state synthesis, runtime type/procedure/provider/prompt leakage, and
  source-map gaps.

Unblock rule:

- Stage 10 remains blocked until this prerequisite lands whenever fresh
  checkout evidence still shows that ordinary imported `.orc` cannot author the
  loop-frame state required by the typed exhaustion route.
- This prerequisite is not considered landed if only concrete-record loop-state
  cases pass while the standalone imported-generic carrier fixtures still fail
  to transport specialized loop state through `loop/recur`.

### 12.3 Imported Generic Loop-State Consumer Proof Dependency

Even after the authored carrier surface in Section 12.2 lands, Stage 10 still
needs one narrower future-consumer proof for the review-loop-shaped imported
generic route. The remaining risk is not loop-state authoring in isolation. The
remaining risk is the composed authoring-time route where imported generic
definitions, compile-time `ProcRef` hooks, structural constraints, loop-state
carriers, and ordinary procedure composition meet inside one imported stdlib
consumer.

This dependency is about composed frontend behavior, not runtime loop
semantics. The runtime already has `repeat_until`, scalar exhaustion overrides,
and persisted loop state. The missing prerequisite is the future-consumer proof
that an imported generic `.orc` definition can use the Section 12.2 carrier in
the same shape Stage 10 needs without falling back to bridge-era Python-owned
state or compiler-special routing.

Required first-stable contract:

- one imported generic `.orc` future-consumer fixture can model the Stage 10
  control shape: caller-owned `CompletedT` / `InputsT`, fixed stdlib-owned
  loop-state fields, ordinary `loop/recur :state`, `continue`, final typed
  exhaustion projection, and compile-time `ProcRef` review/fix-like hooks or
  the equivalent compile-time call surfaces needed by the consumer;
- the first-stable proof route uses one explicit supported composition pattern
  for the imported consumer body:
  one generic consumer `defproc` body;
- same-module helper `defproc` decomposition inside that imported generic
  consumer is not part of the first-stable Section 12.3 contract and remains a
  separate follow-on only if a later bounded prerequisite proves it;
- if the consumer pattern introduces local type names or specialized carrier
  aliases, those names resolve after specialization/typechecking without
  `type_unknown` for the specialized loop-state fields;
- the combined route carries specialized fields such as `CompletedT` through
  ordinary `loop/recur` state without `loop_recur_state_type_invalid`,
  unresolved `TypeParamRef`, or equivalent unspecialized loop-state field
  contracts;
- compile-time `ProcRef` review/fix bindings survive the specialization-to-
  lowering handoff far enough that lowering does not encounter symbolic
  `review` / `fix` callee names or other equivalent `procedure_call_unknown`
  failures for the chosen single-body pattern;
- source maps, effect visibility, shared validation, and runtime erasure of
  type parameters, ProcRefs, provider refs, and prompt refs are preserved
  across the full imported consumer shape.

Selection trigger:

- if a blocked Stage 10 or similar follow-on run shows the Section 12.2
  carrier surface appears present and its standalone imported-generic carrier
  fixtures pass, but an imported generic future-consumer definition still fails
  when composing that surface with ordinary procedure composition, especially
  with `procedure_call_unknown`, including symbolic `review` / `fix` callee
  names surviving into lowering, `type_unknown`,
  `loop_recur_state_type_invalid`, or unresolved `TypeParamRef` evidence, stop
  the review-loop slice and select or draft prerequisite gap
  `workflow-lisp-imported-generic-loop-state-consumer-proof`.

Required drafting output:

- one bounded implementation architecture at
  `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-generic-loop-state-consumer-proof/implementation_architecture.md`;
- one chosen single-body imported-consumer composition pattern with rationale,
  and explicit deferral of same-module helper decomposition rather than leaving
  helper-vs-single-body expectations ambiguous;
- fixture coverage proving an imported generic future-consumer definition
  composes the Section 12.2 carrier surface, structural constraints, and
  compile-time `ProcRef` selection through ordinary `loop/recur`;
- explicit acceptance that the chosen single-body pattern carries compile-time
  `ProcRef` bindings through specialization and lowering without symbolic
  callee leakage, with Stage 10 written to that same supported pattern;
- acceptance that runtime-visible artifacts contain no leaked `TypeParamRef`,
  `ProcRef`, provider ref, prompt ref, or review-loop-specific hidden state
  synthesis.

Unblock rule:

- Stage 10 remains blocked until this prerequisite lands whenever the
  standalone Section 12.2 loop-state fixtures pass but the imported generic
  future-consumer composition still fails.
- This prerequisite is not considered landed if only the carrier-surface
  fixtures pass while the chosen imported-consumer composition pattern remains
  unproven.

## 13. Target Compilation Architecture

The target architecture is:

```text
caller .orc
  imports std/phase.orc
  defines caller-owned review and fix procedures
  calls review-revise-loop with proc-ref hooks
        |
        v
form registry / import resolver
  classifies review-revise-loop as stdlib extension or imported binding
  refuses promoted compiler-special route
        |
        v
frontend import resolver
  loads stdlib .orc source
  records imported-definition provenance
        |
        v
macro expansion, if any
  expands only to grammar-accepted .orc
  does not own hidden provider/command effects
  does not own runtime semantics
        |
        v
generic expansion / specialization substrate
  clones imported .orc body
  substitutes value parameters
  substitutes compile-time ProcRef parameters
  allocates generated names/paths through shared allocator
  records source-map frames
        |
        v
generic type checker
  resolves concrete CompletedT / InputsT
  checks structural record/union/variant constraints
  checks ProcRef signatures and effects
  preserves variant proof through match
        |
        v
monomorphic helper/private workflow
  contains no type parameters
  contains no runtime ProcRefs
        |
        v
ordinary typecheck and lowering
  loop/recur
  match
  provider-result / command-result
  record/union construction
  materialization/projection
        |
        v
YAML-shaped Core DSL workflow
        |
        v
shared validation / Semantic IR / Executable IR
        |
        v
runtime
  executes repeat_until, provider steps, command steps, match, output contracts
```

The compiler sees the generated helper as ordinary monomorphic Workflow Lisp. The
runtime sees ordinary DSL.

## 14. Stdlib Surface

### 14.1 First Tranche: Concrete Review Decision, Findings, And Stdlib Terminal Protocol

The first stable implementation should avoid over-generalizing every part of the
loop. It keeps review decision, findings, and terminal outcome protocol as
stdlib-owned concrete types while allowing caller-owned completed/input records.

### 14.1.1 First-Tranche Schema Promoted To Base Spec

The exact first-tranche review/revise stdlib schema is now part of
`docs/design/workflow_lisp_frontend_specification.md`. The copy below is kept as
the migration-source shape and must not diverge from the base specification.

```lisp
(defpath ReviewFindingsJsonPath
  :kind relpath
  :under "artifacts/work"
  :must-exist true)

(defrecord ReviewFindings
  (schema_version String)
  (items_path ReviewFindingsJsonPath))

(defunion ReviewDecision
  (APPROVE
    (review_report ReviewReportPath)
    (findings ReviewFindings))
  (REVISE
    (review_report ReviewReportPath)
    (findings ReviewFindings))
  (BLOCKED
    (review_report ReviewReportPath)
    (blocker_class BlockerClass)
    (findings ReviewFindings)))

(defunion ReviewLoopResult
  (APPROVED
    (review_report ReviewReportPath)
    (findings ReviewFindings))
  (BLOCKED
    (review_report ReviewReportPath)
    (blocker_class BlockerClass)
    (findings ReviewFindings))
  (EXHAUSTED
    (last_review_report ReviewReportPath)
    (findings ReviewFindings)
    (reason String)))
```

`ReviewDecision` is the per-iteration review result. `ReviewLoopResult` is the
terminal loop result. `BLOCKED` is part of `ReviewDecision`, not a side channel
outside it, and blocked terminal state carries `blocker_class BlockerClass`,
not a plain string.

There is no first-tranche generic `ReviewFinding` item record. The stdlib loop
only standardizes the typed `ReviewFindings` carrier plus the minimum validated
artifact envelope at `items_path`.

`ReviewFindings` remains semantic metadata for a validated findings artifact.
The typed record and the validated JSON at `items_path` are authority; reports
and summaries remain views. In the first tranche, that carrier has one exact
owner-doc rule: `schema_version` must equal `"ReviewFindings.v1"`, `items_path`
must point to JSON under `artifacts/work`, that JSON must validate as a
non-pointer object with a top-level `items` member, and malformed findings fail
as an output-contract error rather than as a review decision.

That minimum `ReviewFindings.v1` envelope is intentionally narrower than a
generic per-item schema. Additional top-level fields, the type of the `items`
member, and each finding item's internal fields are outside the stdlib loop's
first-tranche contract. If a producing/consuming workflow needs stricter
payload guarantees, it must own them in a separate workflow-specific findings
schema or validator layered behind the same `ReviewFindings` carrier.

`workflow_lisp_structural_parametric_constraints.md` owns the structural
constraint vocabulary used around these types.
`workflow_lisp_compile_time_parametric_specialization.md` owns the compile-time
generic instantiation machinery. The frontend specification owns the current
first-tranche schema. Drafting-guide and companion-design examples may summarize
the contract, but any duplicate example must match the base-spec names, carrier
fields, terminal fields, and first-tranche generic clause ordering exactly.

The semantic contract is:

- `CompletedT` and `InputsT` are caller-owned records.
- `ReviewFindings.schema_version` must equal `"ReviewFindings.v1"`.
- `ReviewFindings.items_path` must point to JSON under `artifacts/work` that
  validates the owner-doc minimum `ReviewFindings.v1` envelope: non-pointer
  object with a top-level `items` member.
- findings validation runs before a `ReviewFindings` record is published to
  loop state and again before `fix` consumes findings after resume.
- stronger finding-item payload rules, if needed, belong to a separate
  workflow-specific findings schema/validator behind the same carrier.
- `review` and `fix` are compile-time ProcRefs.
- `review` returns a typed `ReviewDecision`.
- `fix` is findings-only:
  `ProcRef[(CompletedT InputsT ReviewFindings) -> CompletedT]`.
- the stdlib loop returns exact `ReviewLoopResult` variants.
- any workflow-specific terminal union is constructed by caller code after a
  `match` on `ReviewLoopResult` with refined match binders.
- `APPROVE` and `BLOCKED` are terminal.
- `REVISE` invokes fix and continues.
- `EXHAUSTED` is typed terminal non-completion.

### 14.2 Extended Model: Generic Decision And Findings

A later version may parameterize decision and findings types too, but that
should not block the first migration tranche unless a concrete caller requires
custom findings.

### 14.3 Deferred Extension: Caller-Owned Terminal Construction

If a future tranche wants the stdlib loop itself to construct caller-owned
terminal unions, it must first accept one stable route: exact protocol
normalization, explicit field-mapping constraints, or constructor ProcRefs.

Until then, the preferred model is:

```text
review-revise-loop returns ReviewLoopResult,
and caller code projects any richer workflow-specific terminal union.
```

Disallowed model: Python compiler branch constructs workflow-specific terminal
variants because it knows `review-revise-loop` by name.

## 15. Review/Revise Semantic Contract

The stdlib loop has four routes.

### 15.1 APPROVE

```text
review(completed, inputs) returns APPROVE
  -> loop exits
  -> terminal result is ReviewLoopResult.APPROVED
  -> review_report and findings come from the approving review decision
  -> any workflow-specific terminal projection happens in caller code after match
```

### 15.2 REVISE

```text
review(completed, inputs) returns REVISE
  -> fix(completed, inputs, findings) runs
  -> completed becomes fix result
  -> loop continues
  -> REVISE is not completion
```

### 15.3 BLOCKED

```text
review(completed, inputs) returns BLOCKED
  -> loop exits
  -> terminal result is ReviewLoopResult.BLOCKED
  -> review_report, findings, and blocker_class come from the blocking review decision
  -> any workflow-specific terminal projection happens in caller code after match
```

### 15.4 EXHAUSTED

```text
loop reaches max_iterations without APPROVE or BLOCKED
  -> loop exits through explicit exhaustion projection
  -> terminal result is ReviewLoopResult.EXHAUSTED
  -> last_review_report and findings come from the last completed review frame
  -> reason is a deterministic workflow-owned value such as "max_iterations_exhausted"
  -> any workflow-specific terminal projection happens in caller code after match
```

Exhaustion is not hidden control-flow failure. It is a typed non-completion
result.

## 16. Loop State Model

The generated monomorphic helper should lower to an explicit loop-frame state. A
conceptual frame is:

```lisp
(defrecord ReviewLoopFrame
  ((completed CompletedT)
   (decision_status ReviewDecisionStatus)
   (latest_review_report ReviewReportPath)
   (latest_findings ReviewFindings)
   (latest_blocker_class OptionalBlockerClass)
   (exhaustion_reason OptionalString)
   (iteration Int)))
```

After specialization, `CompletedT` is concrete. No type parameter appears in
lowered Core AST, Semantic IR, executable state, output contracts, provider
payloads, or command payloads.

The optional placeholder names in this conceptual frame are explanatory, not a
competing public schema surface. When present, `latest_blocker_class` carries a
`BlockerClass` value.

This conceptual frame is not by itself the missing authored surface. The
authorable route for expressing such loop-frame state in ordinary imported
`.orc` is the prerequisite owned by Section 12.2 and must land before Stage 10
promotion.

The frame is semantic state. It must not carry ProcRef values, provider refs,
prompt refs, type parameters, runtime closure environments, unvalidated report
text as structured findings, or evidence identities invented by review output.

## 17. Lowering Contract

A specialized stdlib review loop should lower to existing DSL surfaces.

Representative generated shape:

```text
generated/private review-loop helper
  repeat_until ReviewLoop:
    outputs:
      completed
      decision_status
      latest_review_report
      latest_findings
      latest_blocker_class
      exhaustion_reason

    condition:
      self.outputs.decision_status in ["APPROVE", "BLOCKED"]

    max_iterations:
      max_iterations

    on_exhausted.outputs:
      decision_status = "EXHAUSTED"
      exhaustion_reason = "max_iterations_exhausted"

    steps:
      ReviewOnce:
        call specialized review ProcRef
        produces ReviewDecision

      RouteReviewDecision:
        match ReviewDecision.discriminant
          APPROVE:
            materialize completed unchanged
            materialize latest_review_report
            materialize latest_findings
            set decision_status = "APPROVE"

          REVISE:
            call specialized fix ProcRef
            materialize completed = fix result
            materialize latest_review_report
            materialize latest_findings
            set decision_status = "REVISE"

          BLOCKED:
            materialize completed unchanged
            materialize latest_review_report
            materialize latest_findings
            materialize latest_blocker_class
            set decision_status = "BLOCKED"

  FinalReviewLoopProjection:
    match ReviewLoop.outputs.decision_status
      APPROVE:
        construct ReviewLoopResult.APPROVED
      BLOCKED:
        construct ReviewLoopResult.BLOCKED
      EXHAUSTED:
        construct ReviewLoopResult.EXHAUSTED

  CallerProjection:
    optional authored match over ReviewLoopResult
      constructs workflow-specific result union, if needed
```

The final projection must use loop-frame outputs. It must not reach into only
the first review step or into a body-local step that is not materialized onto the
loop frame.

## 18. Loop Exhaustion Projection

The DSL already has `repeat_until.on_exhausted.outputs`, but it is intentionally
narrow. It maps declared loop-frame output names to literal scalar overrides
only when the body succeeds, outputs resolve, the condition evaluates false, and
`max_iterations` is exhausted. Without `on_exhausted`, exhausting
`max_iterations` remains a failed loop with `error.type:
repeat_until_iterations_exhausted`. Body-step failures, output-resolution
failures, and predicate failures remain failures and do not use exhaustion
overrides.

Therefore, `loop/recur` needs a generic frontend-level exhaustion projection:

```text
loop/recur :on-exhausted
  -> repeat_until.on_exhausted.outputs for scalar markers
  -> final typed projection from last materialized loop-frame outputs
```

Required behavior:

- if `max_iterations` exhausts after a completed iteration, set scalar marker
  `decision_status = EXHAUSTED`, preserve last completed loop-frame outputs, set
  `exhaustion_reason`, and construct typed `ReviewLoopResult.EXHAUSTED` in
  final projection;
- if body fails, ordinary failure, not `EXHAUSTED`;
- if output resolution fails, ordinary failure, not `EXHAUSTED`;
- if predicate evaluation fails, ordinary failure, not `EXHAUSTED`;
- if no explicit exhaustion projection exists, preserve DSL behavior:
  `repeat_until_iterations_exhausted`.

This is a generic loop feature, not a review-loop compiler branch. It depends
on both prerequisites in Sections 12.1 and 12.2: ordinary imported `.orc`
must be able to author `:on-exhausted`, and that authored exhaustion route is
still insufficient if code cannot also name and type the loop-frame outputs
that final projection reads from.

## 19. Evidence Authority

Review-provider output is decision evidence, not carried-artifact identity
authority.

For implementation review, consumed evidence such as `checks_report` must be
carried by inputs or loop state. The review provider may consume, inspect, and
judge that evidence, but it must not return a replacement `checks_report` path
that becomes authoritative.

Required rule:

```text
final_result.checks_report, or any equivalent carried evidence field,
must be copied from inputs/state, not from ReviewDecision.
```

The stdlib lowering document states this rule directly: consumed evidence
artifacts such as `checks_report` are loop inputs/consumes rather than
review-provider output fields; route and final projection steps carry evidence
refs from loop inputs/state; and negative validation should catch any lowering
where provider output can replace consumed evidence identity.

Required negative case:

```text
A review ProcRef returns a decision bundle containing a checks_report field.
The generic loop attempts to use that returned field as terminal evidence.
Compilation or shared validation fails with the current contract/authority
diagnostic for replacing carried evidence identity. A dedicated
evidence-authority diagnostic may be added later if the existing diagnostic is
too generic.
```

## 20. Effects Contract

A specialized review loop's effect summary is the union of visible effects from
the loop and all selected ProcRef hooks:

```text
effects(review-revise-loop[...])
  =
    effects(review)
  union effects(fix)
  union effects(on-approved), if bridge model is used
  union effects(on-blocked), if bridge model is used
  union effects(on-exhausted), if bridge model is used
  union effects(loop/recur)
  union effects(match)
  union effects(materialization/projection)
```

A macro or specialization that hides provider or command effects is invalid.

Compile-time specialization with procedure references must satisfy this
boundary:

```text
before runtime:
  all type parameters are concrete
  review and fix point to concrete named procedures
  provider and prompt externs used by those procedures are resolved inside those procedures
  no runtime state carries ProcRef, provider ref, prompt ref, or type parameter
```

## 21. Source Maps And State Layout

Generated loop state, bundle paths, temp paths, pointer paths, and artifact roots
should be requested semantically and derived by StateLayout.

The review-loop stdlib implementation must source-map:

- caller call site;
- imported stdlib definition;
- macro expansion frame, if any;
- specialization arguments;
- generated monomorphic helper/private workflow;
- generated `repeat_until` frame;
- generated match cases;
- generated projection steps;
- generated state paths;
- generated bundle roots;
- selected review ProcRef definition;
- selected fix ProcRef definition;
- selected terminal-constructor ProcRefs, if bridge model is used.

High-level `.orc` code should request semantic layout targets such as:

```lisp
(phase-state phase_ctx "review-loop-frame")
(phase-target phase_ctx "review-report")
(phase-target phase_ctx "review-findings")
```

The layout layer derives concrete paths. Exact paths are design choices, not
frontend syntax.

Missing source-map origin for any generated step, boundary field, or generated
path is a compile-time failure.

## 22. Macro Boundary

Macros remain syntax expansion. They do not own runtime semantics.

Allowed:

```text
(review-revise-loop ...)
  expands to a call of a generic stdlib definition
```

or:

```text
(review-revise-loop ...)
  expands to a generated monomorphic .orc helper
  whose generated source then typechecks and lowers ordinarily
```

Disallowed:

- macro expansion owns hidden provider/command effects;
- macro expansion bypasses shared validation;
- macro expansion creates runtime procedure values;
- macro expansion creates source-map gaps;
- macro expansion encodes review/revise terminal behavior outside ordinary
  `.orc`.

A macro may keep public syntax ergonomic, but the control structure belongs in
imported `.orc` source or in a generic typed template mechanism available to
arbitrary `.orc`.

## 23. Generic Specialization Identity

Every generated specialization must have a deterministic identity:

- source module;
- definition name;
- source definition digest;
- concrete type argument identities;
- compile-time ProcRef identities;
- target DSL version;
- language/compiler version;
- generated-name schema version;
- call-site identity, when needed for source-map or path obligations.

Equivalent call sites may share a specialization only if doing so preserves
source-map and generated-path obligations. Otherwise, the compiler should
generate per-call-site helpers.

Specialization identity chooses generated helpers, specialization caching, and
debug/source-map provenance. Persisted `repeat_until` checkpoint identity is a
separate contract owned by the shared semantic/executable bridge and runtime
state layout: for imported stdlib review loops it must stay anchored to the
authored loop-step identity exposed for that call site in the importing
workflow, not to a generated helper name.

Call-site provenance may force distinct helpers or richer source maps, but it
does not by itself redefine the persisted checkpoint key for the same authored
review-loop site in the same run. Generated helper names are implementation
details and must not become resume lookup keys.

## 24. Incremental Implementation Plan

### Stage 0 - Add This Integration Document And Wire Related-Doc References

Tasks:

- add `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`;
- add reciprocal related-doc links where useful;
- mark `ReviewReviseLoopExpr` path as legacy/bridge-only;
- document that behavior-preserving preflight and Track A are prerequisites for
  stdlib review-loop promotion.

Acceptance:

- design docs agree on ownership boundaries;
- review-loop stdlib work is not planned before hard preflight and Track A
  substrate;
- legacy path is explicitly non-promoted.

### Stage 1 - Behavior-Preserving Refactor Preflight

Tasks:

- fix concrete hazards in `lowering.py`, `functions.py`, and `macros.py`;
- add focused characterization coverage for affected pass boundaries;
- record any pre-existing failures with exact commands and outputs;
- decide lowering package/facade boundary;
- land the standalone
  `workflow-lisp-owner-seam-split-prerequisite` slice when the relevant
  typecheck, specialization, or lowering-boundary responsibilities still live
  only in the public facades;
- land the standalone
  `workflow-lisp-lowering-core-family-decomposition` slice when
  `lowering/core.py` remains the mixed owner for non-procedure lowering
  families that future Track A, parametric, or stdlib-review-loop work would
  need to extend;
- if a blocked follow-on run confirms that this slice is still missing, stop
  and route/draft
  `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-lowering-core-family-decomposition/implementation_architecture.md`
  before reopening the blocked feature bundle;
- land the standalone `workflow-lisp-typecheck-family-decomposition` slice when
  `typecheck.py` remains the mixed owner for typechecking families that
  structural constraints, parametric specialization, imported `.orc` expansion,
  or stdlib-review-loop work would need to extend;
- if a blocked follow-on run confirms that this slice is still missing, stop
  and route/draft
  `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-typecheck-family-decomposition/implementation_architecture.md`
  before reopening the blocked feature bundle;
- land the standalone
  `workflow-lisp-expression-traversal-prerequisite` slice when
  `orchestrator/workflow_lisp/expression_traversal.py` or a recorded narrower
  equivalent shared update point is still missing;
- if a blocked follow-on run confirms that this slice is still missing, stop
  and route/draft
  `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-expression-traversal-prerequisite/implementation_architecture.md`
  before reopening the blocked feature bundle;
- introduce shared expression traversal utility through that prerequisite
  slice;
- add traversal coverage over all `ExprNode` variants or explicit
  leaf/specialized classification.

Acceptance:

- compileall passes;
- focused tests pass or pre-existing failures are recorded;
- lowering package/facade decision is made before helper extraction;
- exact post-split owner paths are recorded for procedure-call typechecking,
  specialization discovery/materialization, and procedure-call lowering/
  provenance/runtime-erasure before new Track A or parametric behavior lands in
  those seams;
- exact post-split owner paths are recorded for provider/command effects,
  values/projection, control flow, workflow-call integration, source-map/origin
  bookkeeping, and validation-remapping before new behavior lands in those
  lowering families;
- exact post-split owner paths are recorded for typechecking context,
  dispatcher routing, proof/field validation, effect/command validation,
  callable checks, and any remaining stdlib bridge typing before new behavior
  lands in those typechecking families;
- exact owner path and first adopter set are recorded for the shared
  expression-traversal update point before new expression-form behavior lands
  in duplicated walkers;
- new expression forms have one obvious traversal update point;
- purity/extern/ProcRef discovery cannot silently miss unknown `ExprNode`
  containers.

### Stage 2 - Optional But Recommended Context And Helper Cleanup

Tasks:

- introduce `TypecheckContext` if needed before structural constraints;
- extract lowering extern discovery into a coherent helper module;
- extract lowering-time type helpers into a coherent helper module;
- preserve diagnostic codes, spans, form paths, and expansion stacks.

Acceptance:

- typecheck recursion has an explicit context value or equivalent stable
  boundary;
- variant-proof scope changes remain visible at match/control-flow boundaries;
- provider/prompt extern discovery behavior is unchanged;
- lowering-time type helper diagnostics are unchanged.

### Stage 3 - Track A Form Registry And Elaboration Boundary

Tasks:

- add `FormKind` / `FormSpec` registry;
- classify all recognized heads;
- derive or validate reserved macro names from registry;
- route expression elaboration through registry;
- classify `review-revise-loop` as `STDLIB_EXTENSION` or
  `TEMP_COMPILER_INTRINSIC` scheduled for removal.

Acceptance:

- each compiler-known head has owner, kind, rationale, and removal target where
  applicable;
- `review-revise-loop` is not classified as `CORE_SPECIAL`;
- ad hoc head dispatch is reduced or guarded.

### Stage 4 - Track A Denylist And Architecture Tests

Tasks:

- add promoted-mode denylist for `ReviewReviseLoopExpr` path;
- add `test_no_review_loop_expr_in_core_ast_union`;
- add `test_review_revise_loop_not_reserved_core_macro_name`;
- add `test_review_revise_loop_not_elaborated_by_head_name`;
- add `test_typecheck_does_not_import_review_loop_expr`;
- add `test_lowering_does_not_import_review_loop_expr`.

Acceptance:

- promoted route fails if review-loop-specific compiler artifacts are used;
- legacy fixtures may still opt into old path explicitly;
- tests distinguish syntax compatibility from semantic special casing.

### Stage 5 - Track A Tiny Imported `.orc` Expansion

Tasks:

- load stdlib `.orc` through normal reader/parser/import resolution;
- expand one tiny imported `defproc` call;
- clone/substitute imported body hygienically;
- return ordinary `ExprNode`;
- typecheck and lower through ordinary path;
- record source-map frames for caller and imported definition.

Acceptance:

- tiny imported `.orc` helper compiles;
- generated nodes source-map to both caller and imported definition;
- no review-loop-specific code is involved.

### Stage 6 - Track A Imported Effects And Match/Loop Fixtures

Tasks:

- add imported `.orc` procedure that emits provider or command effects;
- add imported `.orc` procedure using `match`;
- add imported `.orc` procedure using `loop/recur`;
- ensure effects are visible to validation and runtime planning;
- ensure match variant proof is ordinary, not stdlib-specific.

Acceptance:

- imported provider/command effects are visible;
- imported match fixture typechecks and lowers;
- imported loop fixture typechecks and lowers;
- source maps survive all fixtures.

### Stage 7 - Generic `loop/recur :on-exhausted`

Tasks:

- add authoring surface for `loop/recur` exhaustion projection;
- lower scalar markers to `repeat_until.on_exhausted.outputs`;
- add final typed projection from loop-frame outputs;
- preserve DSL failure behavior for body/output/predicate failures;
- reject direct non-scalar `on_exhausted` overrides.

Acceptance:

- imported or local `.orc` loop fixtures can author `:on-exhausted` without
  review-loop-specific bridge injection;
- generic loop fixture returns typed `EXHAUSTED` result;
- exhaustion without explicit projection still fails as
  `repeat_until_iterations_exhausted`;
- body failure during final iteration remains ordinary failure;
- non-scalar `on_exhausted` override is rejected.

### Stage 7A - Authorable Parametric Loop-State Surface

Tasks:

- select one generic authored surface for loop-frame carriers used by typed
  `loop/recur` exhaustion;
- ensure that surface can carry caller-specialized fields such as `CompletedT`
  together with fixed stdlib-owned fields such as `ReviewReportPath` and
  `ReviewFindings`;
- ensure imported generic proc bodies can feed that surface directly into
  `loop/recur :state`, reuse it across `continue`, and project the final typed
  exhausted result without `TypeParamRef` leaking into loop-state field
  contracts;
- specialize the carrier to monomorphic state before ordinary lowering;
- preserve source maps and runtime erasure across the carrier and its final
  projection path;
- reject review-loop-specific hidden Python state synthesis on the promoted
  route.

Acceptance:

- an imported generic `.orc` loop fixture can author state that includes a
  caller-specialized field plus fixed stdlib-owned fields;
- that imported generic fixture can carry the authored state through ordinary
  `loop/recur` typing and lowering without `loop_recur_state_type_invalid`
  failures caused by unresolved `TypeParamRef` at the state-contract boundary;
- final typed exhaustion projection reads those authored loop-frame outputs;
- runtime state contains no type parameters, ProcRefs, provider refs, or prompt
  refs originating from the carrier surface;
- source maps identify the authored carrier origin and the generated
  monomorphic helper/projection surfaces.

### Stage 8 - Track A Generic ProcRef Specialization Through Imported `.orc`

Tasks:

- resolve ProcRef arguments before lowering;
- allow imported `.orc` procedures to accept ProcRef parameters;
- specialize selected procedures into callable helper/private workflow form;
- preserve provider and command effects from selected procedures;
- reject ProcRef values in runtime state;
- reject provider/prompt refs in runtime state;
- detect specialization cycles.

Acceptance:

- imported `.orc` ProcRef fixture calls review/fix-like hooks inside a loop;
- effect graph includes provider/command effects from hooks;
- runtime state contains no ProcRef/provider/prompt/type values;
- specialization cycle produces compile-time diagnostic.

### Stage 9 - Minimal Structural Generics

Tasks:

- parse `:forall` on `defproc`;
- parse inline `:where` structural constraints;
- support `is-record` and `is-union` constraints;
- support `has-field` constraints;
- support `has-union-variant` constraints;
- support `has-shared-union-field` constraints with owner-doc semantics;
- support ordinary `ProcRef` parameters whose signatures mention specialized
  type parameters;
- instantiate monomorphic helper before ordinary lowering;
- typecheck instantiated helper;
- preserve variant proof through `match`.

Acceptance:

- pure generic `defproc` fixture passes;
- generic record-field fixture passes;
- generic union-match fixture passes;
- generic shared-union-field fixture passes with branch-free access to the
  constrained field only;
- effectful generic ProcRef fixture passes;
- unsatisfied constraint fails before lowering;
- variant field access without proof fails before lowering.

### Stage 9A - Imported Generic Loop-State Consumer Proof

Tasks:

- choose the first-stable imported-consumer composition pattern for the future
  Stage 10 route:
  one generic consumer `defproc` body;
- add one imported generic future-consumer fixture that combines
  caller-specialized loop-state fields, fixed stdlib-owned fields,
  compile-time `ProcRef` hooks, ordinary `loop/recur`, and final typed
  projection;
- keep same-module helper decomposition out of the first-stable route unless a
  later bounded prerequisite explicitly proves it;
- preserve source maps, effect visibility, and runtime erasure across that
  full imported consumer shape;
- reject bridge-era hidden state synthesis or carrier-local type/procedure/ref
  leakage on the promoted route.

Acceptance:

- the imported generic future-consumer fixture compiles and lowers without
  `procedure_call_unknown`, including symbolic `review` / `fix` callee names
  surviving into lowering, `type_unknown` for specialized loop-state fields,
  `loop_recur_state_type_invalid`, or unresolved `TypeParamRef`;
- the chosen imported-consumer composition pattern is explicit and covered by
  the future-consumer proof rather than left implicit, and that first-stable
  pattern is the single-body imported consumer shape;
- final typed projection reads authored loop-frame outputs through the same
  imported generic consumer shape Stage 10 will rely on;
- runtime-visible artifacts remain free of type parameters, ProcRefs, provider
  refs, prompt refs, and review-loop-specific hidden state from the consumer
  route.

### Stage 10 - Implement `std/phase.orc` `review-revise-loop`

This stage begins only after the prerequisites in Sections 12.1, 12.2, and
12.3 are landed and proven on ordinary authored/imported `.orc` code.

Tasks:

- define stdlib `ReviewDecision` and `ReviewFindings`, unless already defined;
- define stdlib `ReviewLoopResult`;
- keep those contracts aligned with Section 14.1.1;
- define generic `review-revise-loop` in `std/phase.orc`;
- accept caller-owned `CompletedT` and `InputsT`;
- accept review/fix as compile-time ProcRef parameters;
- lower through `loop/recur`, `match`, `provider-result` / `command-result`,
  materialization, and projection;
- carry evidence identity through inputs/state;
- document caller-side projection for workflow-specific terminal unions;
- add source-map fixtures.

Acceptance:

- `APPROVE` first pass returns `ReviewLoopResult.APPROVED`;
- `REVISE -> fix -> APPROVE` returns `ReviewLoopResult.APPROVED`;
- `BLOCKED` returns `ReviewLoopResult.BLOCKED`;
- `REVISE` until `max_iterations` returns `ReviewLoopResult.EXHAUSTED`;
- fix receives findings from the immediately preceding `REVISE` decision;
- terminal outputs come from loop frame/projection, not first review step;
- workflow-specific terminal unions are projected outside the stdlib loop;
- carried evidence cannot be redirected by `ReviewDecision` output.

### Stage 11 - Optional Caller-Owned Terminal Construction

Use this only if there is a concrete need for stdlib-internal construction of
caller-owned terminal unions after the first stable route lands.

Tasks:

- choose one extension surface: explicit field mapping, exact protocol
  normalization, or `on-approved` / `on-blocked` / `on-exhausted` constructor
  ProcRefs;
- ensure constructor ProcRefs are compile-time only;
- ensure constructor effects are visible;
- ensure constructor return types specialize to the concrete caller-owned
  terminal type;
- mark bridge as migration-compatible but not the preferred long-term model.

Acceptance:

- review loop compiles without direct arbitrary caller-owned terminal
  construction;
- runtime state still contains no constructor ProcRef values;
- source maps include constructor hooks;
- promotion remains blocked until either an explicit mapping route lands or the
  bridge is accepted as stable stdlib API.

### Stage 12 - Remove Promoted Dependency On Compiler-Special Review Loop

Tasks:

- remove `ReviewReviseLoopExpr` from promoted expression table;
- remove or quarantine `_lower_review_revise_loop`;
- remove or quarantine review-loop-only typecheck branch;
- remove or quarantine `_validate_review_loop_result_contract`;
- remove review-loop-specific compiler visitor logic;
- remove reserved macro treatment that prevents real `.orc` implementation;
- keep legacy fixtures explicitly marked legacy;
- ensure stdlib fixtures compile with special path disabled.

Acceptance:

- promoted review loop compiles without `ReviewReviseLoopExpr`;
- regression guard fails if lowerer recognizes literal `review-revise-loop`;
- generated workflow contains ordinary `repeat_until` / `match` /
  provider/command/projection surfaces.

### Stage 13 - Promotion Evidence

Tasks:

- compile stdlib review-loop candidate;
- run shared validation;
- run dry-run;
- run targeted fake-provider integration for `APPROVE`;
- run targeted fake-provider integration for `REVISE -> APPROVE`;
- run targeted fake-provider integration for `BLOCKED`;
- run targeted fake-provider integration for `EXHAUSTED`;
- run evidence-redirection negative test;
- run source-map provenance test;
- generate parity report;
- compute `non_regressive` mechanically.

`.orc` primary promotion remains blocked until evidence is non-regressive under
the migration parity policy.

### Stage 14 - Resume Broader Cleanup Backlog

After the stdlib route is stable, continue broader cleanup that was not required
as a hard precondition:

- diagnostic builder consolidation;
- pass-local validation helper consolidation;
- source-map/build-artifact ownership cleanup;
- package-root API narrowing;
- fixture-only code movement;
- migration scaffolding audit;
- module dependency audit.

The broader backlog's suggested order is characterization coverage,
`TypecheckContext`, lowering operation-family split, diagnostics/validation
consolidation, source-map/build-artifact ownership, and migration scaffolding
audit after shared Core AST and Semantic IR contracts are resolved.

## 25. Diagnostics

Add precise diagnostics. Avoid generic "type error" where the failure is
architectural.

Implementation-state note: the base frontend specification now lists the
current implemented diagnostic codes. The list below preserves the target
diagnostic intent from this migration design; some names have landed under
current implementation names such as `parametric_constraint_unsatisfied`,
`loop_state_unresolved_type_parameter`, or
`loop_state_runtime_transport_forbidden`, and some remain future diagnostic
names rather than current code strings.

`stdlib_special_form_disallowed`
: Compiler recognized `review-revise-loop` by name in promoted mode.

`review_loop_special_lowerer_used`
: Promoted fixture attempted to use `ReviewReviseLoopExpr` or equivalent legacy
  branch.

`form_registry_missing_classification`
: Compiler-known head lacks `FormSpec` classification.

`reserved_name_registry_mismatch`
: Reserved macro names diverge from `FormSpec` registry.

`stdlib_extension_missing_import_route`
: Stdlib extension cannot resolve through import/call path.

`imported_expansion_source_missing`
: Imported `.orc` expansion lacks imported-definition source provenance.

Dedicated imported-effect-hidden diagnostic, if current effect diagnostics are
too generic
: Imported `.orc` definition introduced provider/command effect not visible to
  validation.

`unknown_exprnode_not_classified`
: Expression traversal, purity, extern discovery, or ProcRef discovery
  encountered an unclassified `ExprNode`.

`refactor_characterization_missing`
: Track A attempted to change a pass boundary without focused characterization
  coverage.

`unresolved_type_parameter`
: Type parameter escaped specialization.

`ambiguous_type_argument`
: Call-site types do not determine one concrete type argument.

`unsatisfied_structural_constraint`
: Concrete type lacks required field, union variant, or compatible field type.

`unsupported_parametric_boundary`
: Generic type appeared where a monomorphic workflow boundary is required.

`specialization_cycle`
: Generic/proc-ref specialization recursively depends on itself.

`proc_ref_not_compile_time`
: ProcRef argument did not resolve to a named `defproc` at compile time.

`runtime_leaked_proc_ref`
: ProcRef appears in lowered runtime state or contract.

`runtime_leaked_provider_ref`
: Provider ref appears in lowered runtime state or contract.

`runtime_leaked_prompt_ref`
: Prompt ref appears in lowered runtime state or contract.

`runtime_leaked_type_parameter`
: Type parameter appears in Core AST, Semantic IR, Executable IR, artifact
  contract, output bundle, or provider/command payload.

`hidden_macro_effect`
: Macro introduced provider/command effect not visible in expanded AST.

`variant_field_without_proof`
: Generic body accessed a variant-only field outside proof-bearing match branch.

`non_exhaustive_review_match`
: Review decision match does not cover `APPROVE`, `REVISE`, and `BLOCKED`.

Dedicated exhaustion-projection-missing diagnostic, if current loop diagnostics
are too generic
: `loop/recur` needs typed `EXHAUSTED` result but no on-exhausted projection
  exists.

Dedicated invalid-exhaustion-projection diagnostic, if current loop diagnostics
are too generic
: On-exhausted attempted to override non-scalar loop output directly.

Dedicated loop-frame-projection-missing diagnostic, if current projection
diagnostics are too generic
: Final result projection reads a value not materialized onto the loop frame.

Dedicated evidence-authority diagnostic, if current contract/authority
diagnostics are too generic
: Reviewer-produced field attempts to replace carried evidence identity.

Dedicated source-map-origin-missing diagnostic, if current source-map
diagnostics are too generic
: Generated helper, step, field, path, or projection lacks source-map
  provenance.

## 26. Fixture Matrix

### 26.1 Behavior-Preserving Refactor Preflight Fixtures

- `lowering_duplicate_helper_guard`
- `private_workflow_variant_case_type_ref`
- `defun_purity_unknown_exprnode_negative`
- `macro_hygiene_malformed_match_preserves_provenance`
- `macro_hygiene_malformed_defworkflow_preserves_provenance`
- `refactor_characterization_provider_result`
- `refactor_characterization_command_result`
- `refactor_characterization_phase_stdlib`
- `refactor_characterization_resource_stdlib`
- `refactor_characterization_drain_stdlib`
- `refactor_characterization_source_map_origin`

### 26.2 Expression Traversal Fixtures

- `expression_traversal_covers_all_exprnode_variants`
- `expression_traversal_letstar`
- `expression_traversal_match`
- `expression_traversal_if`
- `expression_traversal_record`
- `expression_traversal_provider_result`
- `expression_traversal_command_result`
- `expression_traversal_produce_one_of`
- `expression_traversal_resume_or_start`
- `expression_traversal_resource_transition`
- `expression_traversal_backlog_drain`
- `expression_traversal_review_loop_legacy_if_present`
- `expression_traversal_leaf_classification`

### 26.3 Track A Architecture Fixtures

- `form_registry_classifies_all_known_heads`
- `reserved_names_derive_from_form_registry`
- `review_revise_loop_not_core_special`
- `review_revise_loop_promoted_route_denylist`
- `test_no_review_loop_expr_in_core_ast_union`
- `test_review_revise_loop_not_reserved_core_macro_name`
- `test_review_revise_loop_not_elaborated_by_head_name`
- `test_typecheck_does_not_import_review_loop_expr`
- `test_lowering_does_not_import_review_loop_expr`

### 26.4 Imported `.orc` Expansion Fixtures

- `imported_tiny_defproc_expands.orc`
- `imported_tiny_defproc_source_map.orc`
- `imported_provider_effect_visible.orc`
- `imported_command_effect_visible.orc`
- `imported_match_union_proof.orc`
- `imported_loop_recur.orc`
- `imported_proc_ref_specialization.orc`
- `imported_expansion_no_runtime_proc_ref_negative.orc`
- `imported_expansion_hidden_effect_negative.orc`

### 26.5 Generic Language Fixtures

- `generic_pure_identity.orc`
- `generic_record_field_constraint.orc`
- `generic_union_variant_constraint.orc`
- `generic_union_match_projection.orc`
- `generic_proc_ref_effectful_loop.orc`
- `generic_specialization_source_map.orc`
- `generic_specialization_cycle_negative.orc`
- `generic_ambiguous_type_argument_negative.orc`
- `runtime_leaked_type_parameter_negative.orc`
- `runtime_leaked_proc_ref_negative.orc`
- `variant_field_without_proof_negative.orc`
- `hidden_macro_effect_negative.orc`

### 26.6 Loop/Exhaustion Fixtures

- `loop_recur_exhausted_projection.orc`
- `loop_recur_exhausted_without_projection_negative.orc`
- `loop_recur_body_failure_not_exhausted_negative.orc`
- `loop_recur_output_resolution_failure_not_exhausted_negative.orc`
- `loop_recur_non_scalar_on_exhausted_negative.orc`
- `loop_recur_source_map.orc`

### 26.7 Review-Loop Stdlib Fixtures

- `phase_stdlib_review_loop_approve.orc`
- `phase_stdlib_review_loop_revise_approve.orc`
- `phase_stdlib_review_loop_blocked.orc`
- `phase_stdlib_review_loop_exhausted.orc`
- `phase_stdlib_review_loop_malformed_decision_negative.orc`
- `phase_stdlib_review_loop_malformed_findings_negative.orc`
- `phase_stdlib_review_loop_evidence_redirection_negative.orc`
- `phase_stdlib_review_loop_missing_bundle_negative.orc`
- `phase_stdlib_review_loop_no_special_lowerer_negative.orc`
- `phase_stdlib_review_loop_caller_projection.orc`
- `phase_stdlib_review_loop_source_map.orc`
- `phase_stdlib_review_loop_resume_checkpoint_identity.orc`
- `phase_stdlib_review_loop_proc_ref_effects.orc`
- `phase_stdlib_review_loop_runtime_leak_negative.orc`

### 26.8 Migration/Parity Fixtures

- `review_loop_compile_pass`
- `review_loop_shared_validation_pass`
- `review_loop_dry_run_pass`
- `review_loop_fake_provider_approve_pass`
- `review_loop_fake_provider_revise_approve_pass`
- `review_loop_fake_provider_blocked_pass`
- `review_loop_fake_provider_exhausted_pass`
- `review_loop_output_contract_parity_pass`
- `review_loop_terminal_state_parity_pass`
- `review_loop_artifact_parity_pass`
- `review_loop_resume_parity_pass`
- `review_loop_non_regressive_report_pass`

## 27. Acceptance Checks

Before removing the promoted-path compiler-special review-loop branch, all of
the following must pass:

- Behavior-preserving preflight is complete.
- Concrete hazards are fixed or explicitly documented as not applicable.
- Characterization coverage exists for pass boundaries touched by Track A.
- Lowering package/facade boundary is decided before helper extraction.
- Procedure-call typechecking, specialization discovery/materialization, and
  lowering-boundary provenance/runtime-erasure each have an explicit post-split
  owner module rather than remaining only in oversized public facades.
- Non-procedure lowering families that Track A, parametric, or
  stdlib-review-loop work would extend have explicit owner modules rather than
  remaining only in `lowering/core.py`.
- Typechecking families that structural constraints, parametric specialization,
  imported `.orc` expansion, or stdlib-review-loop work would extend have
  explicit owner modules rather than remaining only in `typecheck.py`.
- Shared expression traversal covers every `ExprNode` variant or explicit
  leaf/specialized classification.
- Track A form registry exists.
- Registry-routed elaboration is active.
- Reserved names derive from or are checked against registry.
- `review-revise-loop` is not `CORE_SPECIAL`.
- Promoted route denylist catches `ReviewReviseLoopExpr` use.
- A non-review imported `.orc` fixture uses the same generic expansion
  mechanism.
- Imported `.orc` effects are visible.
- Imported `.orc` source maps include caller and imported definition.
- Imported `.orc` ProcRef specialization works.
- Generic `.orc` definitions can declare structural record and union constraints.
- Unsatisfied constraints fail before lowering.
- Specialization emits monomorphic helpers with no runtime type values.
- The chosen imported generic loop-state future-consumer proof passes before
  Stage 10 depends on that route.
- Variant-specific fields remain proof-gated after specialization.
- ProcRef hooks are compile-time only.
- Provider/command effects from ProcRef hooks are visible.
- `review-revise-loop` imports from `std/phase.orc`.
- `review-revise-loop` compiles with `ReviewReviseLoopExpr` disabled.
- `review-revise-loop` lowers to ordinary `repeat_until`, `match`,
  provider/command, materialization, and projection surfaces.
- The stdlib loop returns exact `ReviewLoopResult` variants.
- Workflow-specific terminal unions, if any, are built by caller-side
  `match` with refined match binders rather than review-loop-specific compiler
  semantics.
- `APPROVE`, `REVISE->APPROVE`, `BLOCKED`, and `EXHAUSTED` behavior pass.
- `EXHAUSTED` is typed non-completion.
- `REVISE` is not completion.
- Review-provider output cannot replace carried evidence identity.
- Source maps identify caller, stdlib, specialization, generated helper,
  ProcRefs, and generated paths.
- Runtime state contains no ProcRef, provider ref, prompt ref, closure, or type
  parameter.
- Shared validation accepts generated workflow.
- Parity report computes `non_regressive` mechanically.

## 28. Compatibility And Migration Policy

Existing YAML workflows remain valid and primary until promotion evidence passes.

Existing compiler-special review-loop support may remain temporarily as a legacy
bridge, but:

- legacy bridge fixtures must be marked legacy;
- promoted stdlib fixtures must run with the special path disabled;
- new review/revise feature work should target `std/phase.orc` plus generic
  constraints;
- no new caller should depend on `ReviewReviseLoopExpr` as the intended
  architecture.

Migration is additive:

1. Add behavior-preserving preflight fixes and characterization.
2. Add Track A generic expansion substrate.
3. Add generic constraints/specialization support needed by imported stdlib code.
4. Add stdlib `.orc` implementation.
5. Add fixtures and negative tests.
6. Compile and validate.
7. Run dry-run and targeted fake-provider integrations.
8. Generate parity report.
9. Let promotion tooling compute `non_regressive`.
10. Only then mark `.orc` primary or remove YAML primary.

## 29. Open Questions

The first implementation rule is fixed:

- P0.1-P0.5 are hard gates before Track A.
- R1-R4 remain recommendations, but they become mandatory before Stage 9 if
  Track A characterization exposes pass drift, ownership ambiguity, or missing
  typecheck/lowering context needed for safe structural-generic work.
- Stage 9 must check structural constraints, instantiate a monomorphic helper,
  and typecheck the instantiated helper before lowering.
- Stage 10 also depends on the Section 12.1, 12.2, and 12.3 prerequisites:
  if ordinary imported `.orc` still cannot author `loop/recur :on-exhausted`,
  select `workflow-lisp-loop-recur-on-exhausted-projection` before reopening
  the stdlib review-loop slice; if `:on-exhausted` exists but ordinary
  imported `.orc` still cannot author the loop-frame state consumed by typed
  exhaustion projection, select
  `workflow-lisp-parametric-loop-state-authoring` before reopening the same
  slice; if the standalone carrier surface passes but the imported future-
  consumer composition still fails with `procedure_call_unknown`, including
  symbolic `review` / `fix` callee names surviving into lowering,
  `type_unknown`, `loop_recur_state_type_invalid`, or unresolved
  `TypeParamRef` evidence, select
  `workflow-lisp-imported-generic-loop-state-consumer-proof` before reopening
  the same slice, and keep Stage 10 authored to the first-stable single-body
  imported-consumer pattern unless a later bounded prerequisite proves the
  helper-decomposition route.
- Pre-instantiation generic-body checking is deferred follow-on diagnostic work,
  not a first-tranche acceptance gate.

- Should generic `DecisionT` and `FindingsT` wait until a concrete caller needs
  custom decision/findings schemas?
- If a future tranche wants stdlib-internal construction of caller-owned
  terminal unions with phase-specific field names, should it use exact protocol
  aliases, explicit field-mapping constraints, or constructor ProcRefs?
- If a future tranche wants extra ergonomic sugar over the accepted generic
  `defproc`, should that wrapper be a macro or a generated private workflow,
  with any authored `defworkflow` surface considered only after the generic
  `defproc` route is proven?
- Which promotion gate should decide that any future caller-owned terminal
  construction extension is stable enough?
- Which existing high-level forms besides `review-revise-loop` should be
  reclassified from `TEMP_COMPILER_INTRINSIC` to `STDLIB_EXTENSION` after the
  generic expansion route is proven?

## 30. Summary Recommendation

Proceed in this order:

1. Add this integration doc and reciprocal related-doc links.
2. Complete hard behavior-preserving preflight:
   - concrete hazards;
   - characterization coverage;
   - lowering package/facade decision;
   - shared expression traversal coverage.
3. Land the standalone owner-seam prerequisite gap
   `workflow-lisp-owner-seam-split-prerequisite` whenever the selected
   procedure seams still live only inside oversized public facades.
4. Land the standalone lowering-family decomposition gap
   `workflow-lisp-lowering-core-family-decomposition` whenever
   `lowering/core.py` remains the mixed owner for non-procedure lowering
   families that Track A, parametric, or stdlib-review-loop work would extend.
   If a blocked lowering-dependent run proves this gap is still missing, the
   next artifact is
   `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-lowering-core-family-decomposition/implementation_architecture.md`,
   and the blocked bundle is refreshed only after that prerequisite lands.
5. Land the standalone typecheck-family decomposition gap
   `workflow-lisp-typecheck-family-decomposition` whenever `typecheck.py`
   remains the mixed owner for typechecking families that structural
   constraints, parametric specialization, imported `.orc` expansion, or
   stdlib-review-loop work would extend.
   If a blocked structural-constraints run proves this gap is still missing,
   the next artifact is
   `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-typecheck-family-decomposition/implementation_architecture.md`,
   and the blocked structural bundle is refreshed only after that prerequisite
   lands.
6. Land the standalone shared-traversal prerequisite gap
   `workflow-lisp-expression-traversal-prerequisite` whenever no shared
   expression-traversal update point exists yet for duplicated walkers. If a
   blocked Track A or loop-state run proves this gap is still missing, the next
   artifact is
   `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-expression-traversal-prerequisite/implementation_architecture.md`,
   and the blocked bundle is refreshed only after that prerequisite lands.
7. Implement Track A:
   - `FormKind` / `FormSpec` registry;
   - registry-routed elaboration;
   - reserved-name derivation/checking;
   - promoted-route denylist tests;
   - tiny imported `.orc` expansion;
   - imported source maps;
   - imported effect visibility;
   - generic ProcRef specialization.
8. Land prerequisite gap `workflow-lisp-loop-recur-on-exhausted-projection`
   whenever ordinary imported `.orc` still cannot author `loop/recur
   :on-exhausted` and the checkout still relies on bridge-owned exhaustion
   injection.
9. Land prerequisite gap `workflow-lisp-parametric-loop-state-authoring`
   whenever ordinary imported `.orc` still cannot author the specialized
   loop-frame state that typed exhaustion projection reads from, or when the
   standalone carrier fixtures still fail to transport specialized loop state
   through `loop/recur` without unresolved `TypeParamRef` evidence.
10. Add minimal structural generics:
   - `:forall`;
   - `is-record`;
   - `has-field`;
   - `has-union-variant`;
   - ordinary `ProcRef` parameter typing over signatures that mention resolved
     type parameters;
   - variant-proof preservation.
11. Land prerequisite gap
    `workflow-lisp-imported-generic-loop-state-consumer-proof` whenever the
    standalone loop-state surface passes but the first-stable single-body
    imported generic future-consumer composition still fails with
    `procedure_call_unknown`, including symbolic `review` / `fix` callee names
    surviving into lowering, `type_unknown`,
    `loop_recur_state_type_invalid`, or unresolved `TypeParamRef` evidence.
12. Implement `std/phase.orc` `review-revise-loop` returning exact
   `ReviewLoopResult`.
13. Project workflow-specific terminal unions outside the stdlib loop where
   needed, using ordinary `match` with refined match binders.
14. Use terminal-constructor ProcRefs or field-mapping extensions only if a
   later design explicitly reopens stdlib-internal caller-owned terminal
   construction.
15. Prove `APPROVE`, `REVISE->APPROVE`, `BLOCKED`, `EXHAUSTED`, source-map,
   resume, caller-projection, and evidence-authority fixtures.
16. Remove `ReviewReviseLoopExpr` from the promoted path.
17. Gate migration through machine-computed parity evidence.
18. Continue broader backlog cleanup after the semantic route is stable.

The key architectural move is not to move the existing Python branch into a
macro. The key move is to make the frontend refactor-safe first, then make
generic `.orc` expansion and the type system expressive enough that
`review-revise-loop` is just one ordinary effectful stdlib definition over
caller-owned typed state, exact stdlib-owned terminal protocol, compile-time
procedure hooks, proof-preserving match, and generic loop exhaustion
projection, with an explicit generic route for authoring the projected
loop-frame state, and with any richer workflow-specific terminal unions
authored outside the loop.

## Major Changes

This version explicitly incorporates the broader refactoring order. It
distinguishes hard preflight work from Track A, and Track A from missing
language/type-system features.

The hard preflight now includes concrete hazard fixes, characterization tests,
the lowering package/facade decision, and shared expression traversal coverage.
Broader backlog cleanup is deferred until after the semantic route is stable.

The document now treats
`docs/plans/2026-06-02-workflow-lisp-generic-orc-expansion-refactor.md` as the
Track A implementation prerequisite, while
`workflow_lisp_compile_time_parametric_specialization.md` and
`workflow_lisp_structural_parametric_constraints.md` remain the type-system
mechanism docs.

## Follow-On Observations

The `TypecheckContext` gate timing is not a live decision in this document.
Section 29 fixes the first-tranche rule: P0.1-P0.5 are hard gates before
Track A, R1-R4 remain conditional recommendations, and they become mandatory
before Stage 9 only if Track A characterization exposes the relevant typecheck
or lowering fragility.

The remaining open product question is narrower: whether any later tranche ever
needs stdlib-internal construction of caller-owned terminal unions at all. This
document keeps the first stable route on exact stdlib-owned terminal protocol
plus caller-side projection through `match` with refined match binders.
