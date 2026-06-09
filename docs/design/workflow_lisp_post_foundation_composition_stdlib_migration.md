# Workflow Lisp Post-Foundation Composition And Stdlib Migration

Status: draft design
Kind: follow-on architecture / migration target design
Created: 2026-06-08
Updated: 2026-06-09
Scope: work that should begin after the runtime migration foundation is
accepted: nested structured-control composition, typed result translation,
generic effectful composition, imported/std `.orc` reuse,
`review-revise-loop` stdlib convergence, private executable context bridging,
certified adapter call surfaces and run-state/resource-transition ownership,
typed projections for deterministic bundle publication, entrypoint
bootstrap/defaults, canonical `resume-or-start` validation, and parent-callable
workflow-family parity.

Authority:

- `docs/design/workflow_lisp_runtime_migration_foundation.md` is the hard
  prerequisite for this document.
- Normative DSL/runtime behavior remains in `specs/`.
- `docs/design/workflow_lisp_frontend_specification.md` remains the umbrella
  frontend contract.
- This document does not by itself promote any `.orc` workflow to primary.
- A behavior described here is implementation-complete only when the listed
  verification evidence passes.

Related docs:

- `docs/design/workflow_lisp_runtime_migration_foundation.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_unified_frontend_design.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/design/workflow_lisp_compile_time_parametric_specialization.md`
- `docs/design/workflow_lisp_structural_parametric_constraints.md`
- `docs/design/workflow_lisp_runtime_closures_boundary.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/reports/2026-06-09-design-delta-drain-orc-migration-frontend-runtime-findings.md`
- `docs/plans/LISP-FRONTEND-DESIGN-DELTA-DRAIN-ORC-MIGRATION/parent_drain_readiness_blockers.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/state.md`

## 1. Purpose

This document defines the next Workflow Lisp target after the runtime migration
foundation is complete.

The foundation target hardens five lower-level authority seams:

1. command structured-output conformance;
2. frontend-lowered typed value transport;
3. provider structured-output target binding;
4. machine-readable migration promotion gates; and
5. centralized generated state/path allocation.

This document starts after those seams are reliable. Its job is to make higher
level `.orc` composition and stdlib reuse implementation-ready without
recreating compiler-special forms, hidden command glue, or YAML-shaped
frontends.

The 2026-06-09 design-delta drain migration
(`docs/reports/2026-06-09-design-delta-drain-orc-migration-frontend-runtime-findings.md`)
tested this target against a real workflow family and demonstrated that the
remaining blockers are composition blockers, not syntax blockers. Typed leaf
workflows compile; the family does not compose. The drain produced eleven
findings (F1-F11). One was fixed in place (F1); the remaining ten map onto
this document's tranches and are treated here as driving evidence, not as
optional follow-ups.

The target is practical: one real workflow family should reach
machine-computed `non_regressive=true` and, when eligible for primary
replacement, strict `--require-promotable` success through `.orc`, with visible
effects, source maps, deterministic generated state/path allocation, no
compiler-special review-loop branch, and no parent `.orc` wrapper that hides
workflow semantics inside command glue or YAML state files.

## 2. Executive Decision

After `workflow_lisp_runtime_migration_foundation.md` is accepted and its
verification evidence passes, implement the next tranche as an
inventory-driven hardening and promotion pass rather than a from-zero rebuild.

The work order is:

1. Current implementation inventory and stale-claim repair, seeded with the
   2026-06-09 design-delta findings.
2. Nested structured-control composition (P0). Structured `match`,
   structured `repeat_until`, and stdlib `review-revise-loop` must compose
   inside branch scopes and procedure calls while still passing shared
   validation.
3. Typed result translation hardening (P1): union-to-union variant
   normalization and variant-scoped output field identity.
4. Imported/std `.orc` expansion and reuse hardening, including stdlib forms
   used inside branch scopes and reusable calls.
5. `review-revise-loop` promoted-route convergence and parity proof, including
   nested-composition fixtures.
6. Private executable context bridge (P0), subsuming entrypoint context
   bootstrap and input defaults.
7. Certified adapter call surface, retained-helper classification, and
   run-state/resource-transition ownership (P0 for family parity).
8. Typed projection for selection/bundle publication (P1).
9. Canonical `resume-or-start` reusable-state validation.
10. Parent-callable workflow-family composition: work-item and
    `backlog-drain` abstractions, plus leaf-versus-parent-callable parity
    evidence labeling.
11. Focused adapter lint inventory and staged enforcement.
12. Optional `orchestrate explain` only after source maps, Semantic IR layout,
    effects, and path allocation are stable enough to explain.

The P0/P1 labels mirror the priority work items in the 2026-06-09 findings
report. The three P0 items — nested structured control, the private executable
context bridge, and run-state/resource-transition ownership — gate
parent-callable migration for the drain family. Until they land, migrations of
that family must continue as typed leaf candidates plus explicit bridge
records, with YAML remaining primary.

This document deliberately does not prioritize runtime closures, broad legacy
YAML lint hard errors, or explain tooling before the composition and migration
surfaces are stable.

## 3. Prerequisite Boundary

This document is blocked until the runtime migration foundation has completed
its success criteria:

- command structured-output tests pass for runtime env precedence, parent
  creation, and missing-bundle fail-closed behavior;
- frontend-lowered private scalar, collection, record-like, and nested relpath
  values validate, materialize as views, publish, consume, and render through
  shared runtime contracts;
- provider structured-output target binding exists for `output_bundle.path` and
  `variant_output.path`, wrong-path bundle writes fail closed, and
  provider-session/managed-job wrappers preserve the binding;
- prompt extern source semantics distinguish `asset_file` from `input_file`
  and preserve string shorthand as source-relative assets;
- `migration-parity` has strict gate behavior and schema/version validation;
- `StateLayout` / `PathAllocator` owns the blocking generated path families;
- generated path provenance is present in source maps and Semantic IR; and
- compiler-owned `__write_root__...` inputs are not exposed at public workflow
  entrypoints;
- compatibility proof paths that traverse `resume-or-start` have certified
  validator/writer bindings available through the normal compiler-owned
  command-boundary route.

If any of those remain incomplete, this document may be used for planning but
must not be used to justify more `.orc` primary-promotion work.

The design-delta findings do not reopen the foundation. The private executable
context bridge in this document builds on the foundation's private value
transport and `StateLayout` / `PathAllocator` boundary; it does not redefine
them. Any identity or path-shape changes the bridge needs are routed through
`workflow_lisp_state_layout.md`, not redesigned here.

## 4. Driving Evidence

The 2026-06-09 design-delta drain migration executed the foundation gate,
domain module, feasibility probes, plan phase, implementation phase, selector,
design-gap architect, work-item leaves, and a parent-drain readiness
assessment against this target. Durable evidence:

- findings report:
  `docs/reports/2026-06-09-design-delta-drain-orc-migration-frontend-runtime-findings.md`;
- parent-drain blocker record:
  `docs/plans/LISP-FRONTEND-DESIGN-DELTA-DRAIN-ORC-MIGRATION/parent_drain_readiness_blockers.md`;
- committed leaf candidates for plan, implementation, selector, design-gap
  architect, and work-item pieces; and
- feasibility test module
  `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`.

Finding-to-tranche mapping:

| Finding | Severity | Status | Owning tranche in this document |
| --- | --- | --- | --- |
| F1 imported `PhaseCtx` recognition was name-local | High | fixed | Architecture invariant (Section 9); no tranche work beyond regression coverage |
| F2 nested structured control rejected after lowering | High | unresolved | Tranche 1 (Section 10) |
| F3 union-to-union mapping assumes source case name | High | unresolved | Tranche 2 (Section 11) |
| F4 variant output field names globally unique | Medium | unresolved, mitigated | Tranche 2 (Section 11) |
| F5 public boundaries need private runtime context | High | unresolved | Tranche 5 (Section 14) |
| F6 stateful scripts need certified adapters / native effects | High | unresolved | Tranche 6 (Section 15) |
| F7 selector/bundle publication needs typed projection | Medium | unresolved | Tranche 7 (Section 16) |
| F8 `review-revise-loop` not first-class in branches | High | unresolved | Tranches 3-4 (Sections 12-13) |
| F9 work-item/parent-drain composition model missing | High | unresolved | Tranche 9 (Section 18) |
| F10 adapter calling ergonomics too low-level | Medium | unresolved | Tranche 6 (Section 15) |
| F11 leaf compile success mistakable for parity | Medium | unresolved | Tranche 9 (Section 18) and parity evidence rules (Section 20) |

F1's durable lesson is recorded as an invariant: stdlib and phase forms must
recognize capability/shape contracts across module boundaries through
structural validation plus source provenance, never through short authored-name
matching.

## 5. Current Implementation Inventory

This document must start from durable current state, not from older roadmap
phrasing. The next drain should first verify this inventory against source,
fixtures, tests, parity artifacts, and run state. If a row is stale, repair the
inventory before selecting implementation work.

| Surface | Current state | Remaining post-foundation work |
| --- | --- | --- |
| Runtime foundation | Implemented foundation in the completed runtime-foundation drain | Treat as prerequisite evidence; reopen only if a listed success criterion regresses. |
| Generic effectful composition | Partial/implemented across existing lowering and stdlib fixtures; design-delta drain proved top-level shapes work | Inventory supported shapes, harden missing branch/proof/effect cases, and add negative diagnostics. |
| Nested structured control | Gap; structured `match` / `repeat_until` accepted only top-level, branch-local generated refs invisible to shared validation (F2) | Design and implement the nested lowering/validation route; acceptance fixture in Section 10. |
| Union-to-union result translation | Bug/gap; lowering normalizes by enclosing matched case name and raises `KeyError` for legitimate cross-union mappings (F3) | Derive output variant from the returned variant expression; tests in Section 11. |
| Variant output field identity | Gap, mitigated by verbose variant-specific field naming (F4) | Variant-scoped artifact/json-pointer identity, or an explicit documented restriction. |
| Imported/std `.orc` reuse | Partial/implemented for stdlib modules and review-loop route; imported-name canonicalization bug fixed (F1) | Verify import expansion, specialization identity, hygienic generated names, effect visibility, source maps, and denylist coverage. |
| `review-revise-loop` stdlib route | Implemented first route through `stdlib_modules/std/phase.orc`; works for leaf/top-level patterns; does not compose inside typed branches (F8) | Do not rebuild from zero; prove promoted route has no name-special compiler branch, then make the loop valid wherever typed effectful procedures are valid. |
| ProcRef specialization and structural constraints | Implemented/partial substrate from prior drains | Verify no runtime ProcRef/provider/prompt/type leakage through imported stdlib routes. |
| Private executable context | Gap; required lints correctly reject raw `state/` path inputs at high-level `.orc` boundaries, but no private bridge exists for runtime-owned context (F5) | Specify and implement the private executable context bridge in Section 14. |
| Entrypoint bootstrap/defaults | Partial; still blocks YAML-equivalent wrapper parity in some families | Subsumed into the private context bridge; specify hidden RunCtx/PhaseCtx/default binding contract and public/private boundary inspection. |
| Certified adapter call surface | Gap; `.orc` authors hand-assemble argv for helper scripts (F10) | Importable certified-adapter declarations with typed fields; Section 15. |
| Run-state / resource transitions | Gap; YAML family helpers mutate run state, decide routing, and reconcile recovery outside any certified boundary (F6) | Classify retained helpers; move state transitions toward typed runtime effects or certified adapters; Section 15. |
| Selection/bundle publication | Gap; deterministic publication scripts stand between provider decisions and downstream callers (F7) | Native typed projection preferred; certification as bridge; Section 16. |
| Work-item / parent-drain composition | Gap; leaf candidates compile, parent drain intentionally blocked (F9) | `backlog-drain`-shaped typed abstraction after the P0 tranches; Section 18. |
| `resume-or-start` validation | Existing reusable-state validation plus certified writer-binding alignment | Canonicalize failure taxonomy and promoted-wrapper proof paths; avoid treating pointer files or reports as state authority. |
| Migration parity gates | Strict gate hardening implemented in foundation; leaf-versus-family distinction relies on prose labels in migration records (F11) | Machine-checkable parent-callable parity criteria; `--require-promotable` must fail on leaf-only evidence; Sections 18 and 20. |
| Adapter lint inventory | Not the main foundation target | Inventory and staged enforcement only; avoid broad legacy hard errors before migration evidence. |

## 6. Authority And Dependency Direction

### 6.1 This Document Consumes

- `workflow_lisp_runtime_migration_foundation.md` owns command output
  authority, private typed value transport, strict promotion gates, and the
  first generated path allocation boundary.
- `workflow_lisp_frontend_specification.md` owns the baseline Workflow Lisp
  compiler pipeline and authority rule: `.orc` lowers into the existing
  validated workflow model.
- `workflow_lisp_unified_frontend_design.md` owns future/deferred frontend
  surfaces, including the rule that future features must lower into the
  existing validated model or a separately accepted future runtime contract.
- `workflow_lisp_stdlib_lowering.md` owns the stdlib lowering rule: high-level
  forms should be ordinary `.orc` stdlib code unless accepted as primitives.
- `workflow_lisp_review_revise_stdlib_parametric_integration.md` owns the
  review/revise migration rationale, shape, and historical route.
- `workflow_lisp_state_layout.md` owns generated path identity, run/phase/
  call/loop path ownership, and layout invariants; the private context bridge
  here consumes that contract.
- `workflow_lisp_runtime_closures_boundary.md` owns the decision to keep
  runtime closures deferred.
- `workflow_command_adapter_contract.md` owns adapter certification policy,
  classification vocabulary, and lint policy; this document sequences which
  helpers must be classified and certified for family parity.
- `workflow_lisp_key_migration_parity_architecture.md` owns promotion evidence
  and family-level parity policy.
- `docs/reports/2026-06-09-design-delta-drain-orc-migration-frontend-runtime-findings.md`
  supplies the concrete composition-gap evidence this revision responds to.

### 6.2 This Document Owns

- the post-foundation implementation sequence for Workflow Lisp composition;
- the current-state inventory required before new implementation;
- the acceptance boundary for nested structured-control composition;
- the acceptance boundary for typed result translation: union-to-union variant
  normalization and variant-scoped field identity;
- the acceptance boundary for generic effectful composition;
- the acceptance boundary for ordinary imported/std `.orc` reuse, including
  stdlib forms in branch scopes;
- the post-foundation target for `review-revise-loop` convergence;
- the composition-facing contract for the private executable context bridge,
  including the YAML interop bridge for legacy `state/` values;
- the sequencing requirement that retained workflow-family helpers be
  classified, and that run-state/resource transitions move to typed runtime
  effects or certified adapters before parent-callable parity is claimed;
- the `.orc` certified-adapter call-surface requirement;
- the typed-projection preference order for deterministic bundle publication;
- the entrypoint bootstrap/defaults gap that prevents YAML parity for wrapper
  workflows;
- the canonical `resume-or-start` validation gap;
- the parent-callable workflow-family composition target, including the
  `backlog-drain` abstraction boundary and leaf-versus-parent-callable parity
  evidence labels; and
- which later work remains optional or deferred.

### 6.3 This Document Does Not Own

- command structured-output runtime rules;
- private typed value transport runtime rules;
- migration report schema and strict gate CLI behavior;
- the first `StateLayout` / `PathAllocator` implementation boundary, or
  generated path identity rules;
- adapter certification policy vocabulary or lint policy details;
- runtime closures;
- a full semantic diff engine;
- broad hard-error linting for all legacy YAML; or
- operator explain tooling as a prerequisite for stdlib migration.

## 7. Target Dependency Direction

The desired post-foundation dependency direction is:

```text
authored .orc
  -> imported/std .orc definitions
  -> macro/procedure expansion, if any
  -> generic effectful block normalization, including nested structured control
  -> Core AST with explicit statements, branch scopes, effects, proof scopes,
     and source maps
  -> shared validation, seeing branch-scoped generated steps and private
     executable context contracts
  -> Semantic IR / Executable IR
  -> existing runtime, with typed effects or certified adapters for state
     transitions
  -> migration-parity strict gate with parent-callable evidence
  -> primary-surface decision, only if non_regressive and eligible
```

The prohibited direction is:

```text
authored .orc
  -> compiler recognizes a library form by name
  -> hidden Python lowerer builds workflow control
  -> generated paths are synthesized locally
  -> generated state roots become public authored inputs
  -> run-state mutation hides inside uncertified command glue
  -> effects or proof scopes appear only after the fact
  -> leaf compile/dry-run success is treated as family promotion parity
```

## 8. Goals

- Make nested structured control — structured `match`, structured
  `repeat_until`, and stdlib `review-revise-loop` — valid inside branch scopes
  and procedure calls, surviving lowering and shared validation with agreeing
  generated step IDs, branch-local visibility, source maps, Semantic IR
  layout, and `StateLayout` entries.
- Make union-to-union result translation derive the output variant from the
  returned variant expression, never from the enclosing matched source case.
- Give variant output fields variant-scoped lowered identity so the same
  logical field name can appear in different variants; or, if deferred,
  document the restriction explicitly in the drafting guide.
- Inventory, verify, harden, and generalize existing generic effectful
  composition so new high-level forms do not need one-off lowerers.
- Harden imported/std `.orc` definitions through the ordinary compiler
  pipeline rather than reimplementing completed stdlib routes.
- Keep provider, command, workflow, state, artifact, and resource effects
  visible after expansion.
- Preserve source maps through imported definitions, generated statements,
  generated paths, and selected compile-time procedure hooks.
- Keep `ProcRef`, `bind-proc`, specialization details, and procedure choices
  compile-time-only.
- Prove the existing `review-revise-loop` imported/std `.orc` route is the
  promoted route: no compiler-name special case, no hidden bridge dependency,
  no runtime ref leakage, valid in nested composition contexts, and parity
  evidence for real workflow families.
- Define a private executable context bridge so high-level `.orc` boundaries
  exclude generated state roots while the compiler/runtime injects run, state,
  artifact, phase, selection, and recovery context internally with source-map
  and Semantic IR provenance, including a YAML interop bridge for legacy
  `state/` values during migration.
- Add entrypoint context bootstrap and input defaults so `.orc` wrappers can
  match YAML public boundaries.
- Classify every retained workflow-family helper as pure typed projection,
  certified adapter, resource/state-transition primitive, or migration debt;
  move run-state and recovery transitions toward typed runtime effects or
  certified adapters.
- Give `.orc` an importable certified-adapter call surface with typed fields
  so authors do not hand-assemble argv in high-level workflow code.
- Replace deterministic publication scripts with native typed projections
  where feasible, with certification only as a migration bridge.
- Specify canonical `resume-or-start` validation so reusable state recovery is
  typed and parity-testable.
- Make the work-item and parent-drain family parent-callable through a typed
  `backlog-drain`-shaped abstraction rather than a wrapper over YAML state
  files.
- Keep parity evidence honest: leaf compile evidence is labeled as such,
  parent-callable behavior is proven separately, and `--require-promotable`
  fails until the full family is callable and non-regressive.
- Produce at least one real workflow-family `.orc` parity report with
  computed `non_regressive=true`, and require `--require-promotable` before any
  YAML-primary replacement.

## 9. Non-Goals

- Do not add runtime closures.
- Do not add runtime procedure values or dynamic dispatch.
- Do not make `orchestrate explain` a prerequisite for this tranche.
- Do not hard-error all legacy YAML inline glue before migration inventory.
- Do not use report parsing, pointer files, stdout, debug YAML, or generated
  summaries as semantic authority.
- Do not replace YAML primaries based on compile, shared validation, or dry-run
  alone.
- Do not treat `non_regressive=true` by itself as a primary-surface decision
  when the candidate is not promotion-eligible.
- Do not treat leaf compile success as workflow-family migration evidence.
- Do not weaken the required lints that reject raw generated `state/` paths at
  public high-level `.orc` boundaries; the fix is a private bridge, not lint
  relaxation.
- Do not write a parent `.orc` drain that wraps uncertified helper scripts or
  legacy YAML state files to simulate composition.
- Do not rebuild implemented review/revise stdlib or ProcRef/specialization
  substrate from scratch; audit and harden the current route.
- Do not expand the foundation tranches in this document; fix missing
  foundation work in the foundation design or its implementation plans.
- Do not redesign `StateLayout` identity rules or adapter certification policy
  here; route those deltas to their owning documents.

## 10. Architecture Invariants

- Workflow Lisp remains a frontend over the existing validated workflow model.
- Shared validation remains authoritative after lowering.
- Future frontend features may add authoring power only by lowering into the
  existing validated workflow model or into a separately accepted future
  runtime contract.
- Composition regularity: a typed effectful form that is valid at workflow top
  level is valid in any branch scope or procedure position where its type and
  effects are valid, or it fails before lowering with an owned diagnostic that
  names the composition restriction. Silent post-lowering rejection of
  well-typed nested forms is a defect.
- Stdlib and phase forms recognize capability/shape contracts across module
  boundaries through structural validation plus source provenance, never
  through short authored-name matching (F1 lesson).
- Union result translation derives the output variant from the returned
  variant expression; the enclosing matched case is control flow, not output
  identity.
- Generated state roots, run roots, phase roots, and recovery state are never
  public authored inputs; runtime-owned context crosses workflow boundaries
  only through the private executable context bridge.
- Run-state mutation, recovery recording, prerequisite reconciliation, and
  terminal drain updates are typed runtime effects or certified adapters;
  hidden semantic glue in command steps is migration debt.
- All effects introduced by imported/std `.orc` code are visible.
- Every generated statement, path, helper, branch scope, and selected ProcRef
  body has source-map provenance.
- Generated state/path allocation goes through `StateLayout` / `PathAllocator`.
- No runtime state, artifact contract, provider result, command result, or
  workflow output contains `ProcRef`, provider ref, prompt ref, closure,
  unresolved type parameter, or runtime type object.
- Reports and debug projections are views.
- Migration promotion is machine-computed by strict parity evidence.
- `non_regressive` is evidence; `--require-promotable` is required before a
  primary-surface decision.
- Leaf compile evidence is necessary but never sufficient for family
  promotion; parity evidence carries explicit leaf-versus-parent-callable
  labels.

## 11. Tranche 1: Nested Structured-Control Composition

### 11.1 Contract

This is the highest-priority post-foundation tranche (P0, F2). Structured
control forms must compose. The blocking shape is concrete: the implementation
phase of the drain family naturally branches on a typed attempt result and
runs the stdlib review loop inside the completed branch:

```text
attempt = execute(...)            ; provider-result -> ImplementationAttempt
match attempt:
  COMPLETED -> run checks, then review-revise-loop(...)  ; bounded loop
  BLOCKED   -> typed terminal blocked result
```

Today this fails after lowering/shared validation because:

- structured `repeat_until` is accepted only at top level;
- structured `match` is accepted only at top level;
- generated branch-local refs point at steps not visible to shared validation;
  and
- review-loop generated steps become invalid when nested under a match branch.

The consequence is that the implementation phase, the work item, and the
parent drain cannot become single parent-callable `.orc` workflows; they must
be split into artificial leaves.

The principled fix adds a frontend/lowering/shared-validation route for nested
structured control. Two implementation routes are acceptable; the
implementation architecture for this tranche must choose one and defend it:

1. lower nested structured forms into validation-compatible top-level step
   graphs with explicit branch scopes, so shared validation sees branch-local
   generated steps with correct visibility; or
2. introduce an executable IR layer that preserves nesting until rendering,
   with shared validation extended to walk branch scopes.

Under either route, generated step IDs, branch-local visibility rules, source
maps, Semantic IR layout entries, and `StateLayout` allocations must agree on
the same branch-scope identity.

### 11.2 Required Shapes

- structured `match` nested inside a `match` branch;
- structured `repeat_until` nested inside a `match` branch;
- stdlib `review-revise-loop` invoked inside a `match` branch;
- nested structured control inside a reusable procedure body invoked from a
  branch; and
- branch-local provider/command results feeding nested loops.

### 11.3 Required Implementation Detail

The implementation architecture for this tranche must specify:

- the branch-scope representation carried into shared validation, including
  generated step ID namespacing and visibility rules;
- how `StateLayout` / `PathAllocator` identity incorporates branch-scope and
  loop identity so repeated branches and iterations cannot collide;
- how resume identity is preserved for steps generated inside branch scopes;
- source-map frames for authored branch forms and generated branch-local
  statements;
- Semantic IR layout entries for branch-scoped generated state; and
- diagnostics for any nested shape that remains intentionally unsupported,
  emitted before lowering and naming the restriction.

### 11.4 Acceptance

The acceptance fixture is the implementation-phase shape from the design-delta
drain:

```text
provider-result -> ImplementationAttempt
match ImplementationAttempt:
  COMPLETED -> command-result -> review-revise-loop -> ImplementationPhaseResult
  BLOCKED   -> ImplementationPhaseResult
```

Required evidence for the fixture:

- compile/typecheck;
- shared validation;
- source-map generated-path entries for branch-scoped steps;
- Semantic IR state-layout entries for branch-scoped state;
- dry-run or fake-provider smoke; and
- resume identity stability for branch-scoped generated steps.

Additional acceptance:

- nested `match`-in-`match` and `repeat_until`-in-`match` fixtures pass the
  same evidence set;
- variant proof scopes survive nesting;
- unsupported nested shapes fail before lowering with actionable diagnostics;
  and
- the previously split `execute-implementation-attempt` /
  `review-completed-implementation` leaves can be recomposed into one
  parent-callable implementation phase.

## 12. Tranche 2: Typed Result Translation Hardening

### 12.1 Contract

Typed workflows translate inner control-state unions into outer domain result
unions. That translation must be principled in two ways.

Union-to-union variant normalization (F3). When a `match` arm over one union
returns a variant of a different result union, lowering must derive the output
variant from the returned `variant` expression, not from the enclosing matched
case name. The current behavior raises `KeyError` for legitimate mappings such
as:

```text
match ReviewLoopResult.APPROVED:
  -> DesignDeltaImplementationPhaseResult.COMPLETED
```

This pushes authors toward compatibility-shaped unions whose variant names are
dictated by inner loops, leaking intermediate control states into outer domain
types. Inner control states and outer terminal states intentionally have
different names; the frontend must support that.

Variant-scoped field identity (F4). Lowered `variant_output` currently
requires output field names to be globally unique across variants, because
artifact names and JSON pointers are derived without variant scope. Authors
are forced into `approved_plan_path` / `blocked_plan_path` /
`exhausted_plan_path` style naming, shaping domain types around output-bundle
implementation details. The target is variant-scoped lowered identity:
`APPROVED.plan_path` and `BLOCKED.plan_path` are distinct lowered artifact
identities even when the logical field name is the same.

### 12.2 Tasks

- In union-return normalization, resolve the output variant from the returned
  variant expression.
- Remove any lowering path that keys result normalization on the enclosing
  matched case name.
- Add variant-scoped artifact/json-pointer identity for `variant_output`
  lowering, derived through `StateLayout` allocation identity so variant scope
  participates in generated identity rather than being string-mangled locally.
- If variant-scoped identity is deferred beyond this tranche, add the
  documented restriction and required naming style to
  `docs/lisp_workflow_drafting_guide.md` with examples, and record the
  deferral in the inventory.

### 12.3 Acceptance

- `ReviewLoopResult.APPROVED -> ImplementationPhaseResult.COMPLETED` lowers
  and validates.
- `ReviewLoopResult.EXHAUSTED -> ImplementationPhaseResult.REVIEW_EXHAUSTED`
  lowers and validates.
- `ImplementationAttempt.BLOCKED -> ImplementationPhaseResult.BLOCKED` lowers
  and validates.
- No lowering path raises `KeyError` for well-typed cross-union mappings; any
  rejected mapping has a typed diagnostic.
- Either: the same logical field name validates in two variants of one result
  union with distinct lowered identities; or: the restriction is documented in
  the drafting guide with the required naming style, and a diagnostic names
  the restriction at compile time.

## 13. Tranche 3: Generic Effectful Composition And Imported/Std `.orc` Reuse Hardening

### 13.1 Contract

Generic effectful composition is the compiler substrate that turns authored
expression structure into explicit executable statements without one-off
lowering per high-level form. Imported/std `.orc` definitions must be reusable
through the ordinary compiler pipeline. A stdlib form may provide ergonomic
syntax, but the control flow must belong to grammar-accepted `.orc`
definitions or to generic compiler machinery available to ordinary `.orc`.

This tranche begins with inventory: identify which shapes are already
implemented, which are only supported by special-case lowering, and which fail
without owned diagnostics.

Representative normalization:

```text
authored expression
  -> typed expression/effect tree
  -> effectful block normalization
  -> explicit statements with dependencies and branch scopes
  -> proof/effect/source-map annotations
  -> Core AST
  -> shared validation
```

### 13.2 Required Shapes

- effectful `let*`;
- effectful `match` arms, including nested structured control per Tranche 1;
- same-file calls with locally constructed records;
- reusable procedures containing provider/command/workflow effects;
- imported stdlib forms invoked from branch scopes and reusable calls;
- generated write roots across reusable call boundaries; and
- proof-preserving projection from normalized branches.

### 13.3 Tasks

- Specify the expansion pipeline stage that normalizes effectful expressions,
  and its pass order relative to import expansion, ProcRef specialization,
  typecheck, and lowering.
- Specify the effect-summary representation carried into shared validation.
- Specify how proof scopes transfer through `let*`, `match`, calls, and
  projections.
- Load stdlib `.orc` through ordinary import resolution.
- Clone parsed imported bodies through a hygienic imported-definition boundary.
- Expand or specialize imported definitions without hidden runtime semantics.
- Resolve compile-time ProcRef substitutions and specialization identity before
  lowering; re-typecheck specialized helpers before ordinary lowering.
- Recognize imported capability/shape contracts structurally: any stdlib form
  that depends on a special record shape such as `PhaseCtx` must validate the
  authored record definition structurally with provenance, not match short
  local names (F1 regression coverage).
- Preserve cache/reuse behavior without changing source-map identity.
- Preserve source maps for caller, imported definition, generated helpers, and
  generated paths.
- Preserve effect summaries for imported provider/command/workflow calls.
- Keep compile-time `ProcRef` values out of runtime artifacts.
- Add architectural denylist tests for promoted name-special compiler paths.
- Check reserved names against the form registry so stdlib ownership is not
  blocked by stale compiler-special classifications.
- Add diagnostics for unsupported effectful composition before ordinary
  lowering.

### 13.4 Acceptance

- A non-review imported `.orc` fixture uses the same effectful composition
  route as later stdlib forms.
- A tiny imported `.orc` helper expands, typechecks, lowers, and validates.
- An imported `.orc` helper with provider/command effects exposes those
  effects to shared validation and runtime planning.
- An imported `.orc` helper with `match` preserves variant proof.
- An imported `.orc` helper with loop state preserves source maps and
  generated path provenance.
- An imported `.orc` helper invoked from a `match` branch passes the Tranche 1
  evidence set.
- An imported phase-context record from another module validates structurally
  and is accepted everywhere the short-name-local check previously applied.
- Variant proof scopes survive normalization.
- Generated write roots use `StateLayout` / `PathAllocator`.
- Promoted fixtures fail if they use compiler branches keyed to stdlib form
  names rather than the generic import/expansion route.
- Unsupported effectful compositions fail before lowering with actionable
  diagnostics.

## 14. Tranche 4: `review-revise-loop` Promoted-Route Convergence

### 14.1 Contract

`review-revise-loop` must remain an ordinary imported/std `.orc` abstraction in
the promoted route, and it must be first-class: valid wherever a typed
effectful procedure with its signature is valid, including inside `match`
branches, reusable workflow calls, parent workflow modules, and nested phase
contexts (F8).

Current checkout evidence already includes a first stdlib route through
`orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`, using compile-time
ProcRef hooks, loop/recur exhaustion projection, command-result validation,
match, and typed stdlib unions. The design-delta drain proved the route works
for leaf/top-level patterns, including the plan phase, and fails inside richer
typed branches. This tranche is therefore a convergence, composition, and
parity tranche, not a from-zero implementation.

It may keep a thin macro only when that macro expands to ordinary `.orc`
semantics. It must not depend on a promoted compiler branch that recognizes the
literal name `review-revise-loop`.

### 14.2 Required Behavior

- `APPROVE` exits with typed completion.
- `REVISE` invokes fix and continues; it is not completion.
- `BLOCKED` exits with typed non-completion.
- `EXHAUSTED` is explicit typed non-completion.
- Review findings are validated structured state, not markdown extraction.
- Report paths and findings paths are independently seeded and projected.
- Carried evidence identity comes from inputs/state, not review-provider
  replacement fields.
- Branch proof, effects, generated paths, source maps, loop state, and resume
  identity are preserved when the loop is invoked from a nested context.

### 14.3 Remaining Risk Focus

- nested-composition validity: the loop inside `match` cases, reusable
  workflow calls, parent workflow modules, and nested phase contexts;
- loop-result-to-domain-result translation through the Tranche 2 variant
  normalization fix;
- promoted-route denylist and no `ReviewReviseLoopExpr` dependency;
- historical bridge quarantine and documentation cleanup;
- imported review-loop resume checkpoint identity, including under branch
  scopes;
- report path versus findings path split;
- provider structured-output target binding in real review/fix provider steps;
- public boundary and hidden generated-input inspection; and
- real workflow-family parity through strict migration gates.

### 14.4 Acceptance

- Disable promoted review-loop-specific typechecker/lowerer paths.
- Compile `review-revise-loop` through imported/std `.orc`.
- Generated workflow contains ordinary provider, command, match, loop,
  projection, and materialization surfaces.
- Source maps include caller, stdlib definition, generated helper, generated
  paths, review ProcRef, and fix ProcRef.
- Runtime artifacts contain no ProcRef, provider ref, prompt ref, closure, or
  unresolved type parameter.
- APPROVE, REVISE->APPROVE, BLOCKED, and EXHAUSTED fixtures pass.
- The same four fixtures pass with the loop invoked inside a `match` branch,
  inside a reusable workflow call, and from a parent workflow module, with
  stable resume checkpoint identity.
- Loop terminal variants translate into a differently named domain result
  union through the Tranche 2 route.
- A real workflow-family parity report computes `non_regressive=true`.
- Any YAML-primary replacement passes `--require-promotable`.

## 15. Tranche 5: Private Executable Context Bridge, Entrypoint Bootstrap, And Defaults

### 15.1 Contract

This tranche is P0 (F5) and subsumes the earlier entrypoint bootstrap/defaults
tranche.

The YAML drain family exposes many low-level `state/` paths as ordinary
inputs: `state_root`, `manifest_path`, `progress_ledger_path`,
`run_state_path`, phase state roots, and selection bundle paths. High-level
`.orc` must not reproduce that boundary. The required lints that reject raw
generated `state/` paths at public `.orc` boundaries are directionally
correct and stay; what is missing is the principled alternative.

The private executable context bridge is that alternative:

- the public authored `.orc` boundary excludes generated state roots, run
  roots, phase roots, selection state, and recovery state;
- the compiler/runtime injects run/state/artifact roots, phase roots,
  generated write roots, selection state, and recovery state internally, as
  private executable context values;
- runtime-owned contexts such as `RunCtx` and `PhaseCtx` are introduced
  through an accepted bootstrap surface and kept out of public workflow
  signatures;
- reusable calls receive internal context through the bridge, not through
  public inputs;
- source maps and Semantic IR expose provenance for every generated context
  value;
- shared validation sees the executable/runtime context contracts without
  treating them as public inputs;
- path identity for bridged context values comes from `StateLayout` /
  `PathAllocator`, and any new identity families needed are specified in
  `workflow_lisp_state_layout.md`; and
- a YAML interop bridge can pass legacy `state/` values into private context
  during migration, so a YAML-compatible wrapper does not need to surface
  legacy paths as normal `.orc` inputs.

This tranche needs a pre-implementation design before code changes. It is not
a convenience patch: parity architecture has already exposed missing
phase-context binding as a real wrapper-promotion failure mode, and synthetic
top-level `PhaseCtx` inputs are not acceptable promotion evidence.

### 15.2 Required Design Detail

- how `RunCtx`, `PhaseCtx`, and other runtime-owned contexts are derived and
  injected;
- the full vocabulary of bridged context values: run roots, state roots,
  artifact roots, phase roots, generated write roots, selection state, and
  recovery state;
- which generated inputs are runtime-owned versus public;
- how public inputs exclude run/state/artifact roots and generated write
  roots, and how the existing lints verify that;
- how reusable calls and nested branch scopes receive internal context;
- how defaults are represented in Core AST, Semantic IR, and executable IR;
- how resume reconstructs the same private context values;
- how the YAML interop bridge maps legacy `state/` inputs into private context
  with explicit migration-bridge labeling and an expiry expectation;
- how source maps explain generated context/default bindings; and
- how migration parity inspects public versus private boundaries.

### 15.3 Acceptance

- Public input inspection proves generated write roots, state roots, and phase
  roots are hidden from the public boundary of plan, selector, architect,
  work-item, and parent candidates.
- A promoted `.orc` wrapper can call reusable workflows requiring runtime-owned
  context without exposing `run_id`, write roots, or synthetic `PhaseCtx`
  inputs at the public boundary.
- Resume reconstructs the same private context paths for the same run and
  call-frame identity.
- Source-map and Semantic IR entries identify every generated context value.
- A YAML-compatible migration wrapper passes legacy `state/` values privately
  without making them normal `.orc` inputs, and the bridge values are labeled
  as migration bridges in provenance.
- `.orc` input defaults match the corresponding YAML public boundary where
  parity is claimed.
- Shared validation and migration parity inspect the public boundary, not only
  private generated bindings.

## 16. Tranche 6: Certified Adapter Surface And Run-State / Resource-Transition Ownership

### 16.1 Contract

This tranche is P0 for family parity (F6) plus the adapter ergonomics fix
(F10). Certification policy vocabulary remains owned by
`workflow_command_adapter_contract.md`; this tranche owns the sequencing for
the drain family and the `.orc` call surface.

The YAML drain family relies on helper scripts that encode real workflow
semantics: selection bundle publication, architecture index construction,
design-gap validation, work-item input materialization, terminal
classification, blocked-recovery route selection, run-state updates,
blocked-recovery outcome recording, and prerequisite/recovery reconciliation.
These helpers are not equivalent: some are deterministic projections, some
mutate run state, some decide routing or recovery semantics. A compileable
`command-result` wrapper around them is not migration parity; it is hidden
semantics behind an uncertified boundary.

Required classification. Every retained helper must be classified as exactly
one of:

- pure typed projection — candidate for native typed projection (Tranche 7)
  or certification as a deterministic projection;
- certified adapter — kept behind the certification contract: stable command
  prefix, typed input/output contract, declared effects, path-safety rules,
  exit taxonomy, fixtures, negative fixtures, and source-map behavior;
- resource-transition / state-transition primitive — target for first-class
  typed runtime effects where practical, certified adapter only as an interim
  bridge with replacement route recorded; or
- migration debt — scheduled for replacement, never wrapped into promoted
  `.orc`.

Required call surface. `.orc` authors must not hand-assemble argv for
adapters:

```lisp
;; prohibited at high-level boundaries
(command-result run_neurips_backlog_checks
  :argv ("python" "workflows/library/scripts/run_neurips_backlog_checks.py" ...))
```

The target is an importable certified-adapter surface or stdlib adapter
declaration: `.orc` calls a named adapter with typed fields; the adapter
declaration owns argv assembly, the command prefix, and the typed contract;
source-map and command-boundary evidence are preserved. The declaration makes
the helper's classification visible at the call site, so a reader can tell a
pure projection from a state transition without reading the script.

### 16.2 Tasks

- Inventory and classify every retained drain-family helper using the
  classification above; record the classification durably.
- Define the `.orc` adapter declaration surface: import form, typed
  field-to-argv binding, declared effects, and diagnostics.
- Lower adapter calls through the existing command-result/certified-adapter
  runtime route; do not invent a parallel execution path.
- Move run-state completion, blocked-recovery recording, prerequisite edge
  reconciliation, and terminal drain updates toward typed runtime effects;
  where an interim certified adapter is used, record the replacement route and
  expiry expectation.
- Keep argv assembly out of high-level `.orc`; allow raw `command-result`
  argv only for external tools and explicitly accepted temporary bridges.
- Preserve source maps and command-boundary evidence for adapter calls.

### 16.3 Acceptance

- Every retained drain-family helper has a recorded classification with a
  replacement route where applicable.
- An `.orc` fixture calls a certified adapter through the declaration surface
  with typed fields; the lowered workflow shows the certified command
  boundary, declared effects, and source-map entries.
- A declared adapter with a wrong-typed field fails at compile/typecheck, not
  at runtime argv assembly.
- Run-state mutation and recovery recording on the migration path go through
  typed runtime effects or certified adapters; no promoted `.orc` wraps an
  unclassified script.
- Negative fixture: a high-level `.orc` candidate that hand-assembles argv for
  a semantic helper is rejected or flagged by lint.

## 17. Tranche 7: Typed Projection For Selection And Bundle Publication

### 17.1 Contract

Deterministic publication steps must not stand between typed provider
decisions and downstream callers as opaque scripts (F7). The concrete case is
the selector: YAML returns `selection_status` from provider output, then runs
`publish_lisp_frontend_selection_bundle.py` to publish
`selection_bundle_path`; the first `.orc` selector candidate models only the
provider decision, so downstream workflow calls have no authoritative bundle
path and the parent drain cannot route work.

Preference order:

1. Native typed projection (preferred): derive `selection_bundle_path` from
   runtime-known provider output bundle identity; selection bundle publication
   becomes a typed projection over structured provider state, visible to
   shared validation, with `StateLayout`-allocated paths.
2. Certified adapter (migration bridge only): keep the publication script,
   certified explicitly as a deterministic projection per Tranche 6, with a
   recorded replacement route.
3. Private context bridge: keep the selection bundle path private to
   runtime/StateLayout and expose typed selection values to `.orc`, when
   downstream callers need values rather than paths.

### 17.2 Acceptance

- The `.orc` selector exposes a typed selection result whose bundle identity
  is authoritative for downstream calls.
- The projection route used is visible in lowered output: native projection,
  certified adapter, or private context, never an unlabeled script.
- The published bundle path is `StateLayout`-allocated with source-map and
  Semantic IR provenance.
- A downstream work-item fixture consumes the selection result without reading
  legacy pointer files or re-running publication glue.
- If the certified-adapter bridge is used, the certification record includes
  the native-projection replacement route.

## 18. Tranche 8: Canonical `resume-or-start` Validation

### 18.1 Contract

`resume-or-start` must become a typed reusable-state validation surface, not a
prettier recovery gate over ad hoc files or report text.

It validates prior reusable state, normalizes resumed and fresh branches to the
same return type, and exposes explicit recoverable outcomes when prior state is
stale, missing, incompatible, or unsupported.

### 18.2 Acceptance

- Reusable approved prior result resumes without rerunning fresh work.
- Stale input hash routes through typed stale-state handling.
- Missing artifact routes through typed missing-state handling.
- Schema mismatch routes through typed incompatible-state handling.
- Unsupported version routes through typed unsupported-state handling.
- Fresh branch normalizes to the same result type as resumed branch.
- Resume decisions are based on state/artifact contracts, not report parsing or
  pointer-file authority.

## 19. Tranche 9: Parent-Callable Workflow-Family Composition

### 19.1 Contract

The parent drain is not just a loop over work items (F9). It owns: normal
selection; prerequisite selection; design-gap drafting; selected work-item
execution; blocked implementation recovery; recovered-gap retry;
run-state/resource updates; bounded exhaustion; and resume/recovery
reconciliation.

Writing a parent `.orc` before the P0 tranches land would either call
incomplete surfaces or hide semantics in adapters, recreating YAML-shaped
Lisp. The design-delta migration correctly stopped before the parent drain;
the blocker record at
`docs/plans/LISP-FRONTEND-DESIGN-DELTA-DRAIN-ORC-MIGRATION/parent_drain_readiness_blockers.md`
remains in force until this tranche's prerequisites pass.

The principled sequence is:

1. Land Tranches 1-7 so the leaf modules become parent-callable: one complete
   implementation phase (Tranche 1), clean result translation (Tranche 2),
   composable stdlib loops (Tranches 3-4), private context (Tranche 5),
   certified state transitions (Tranche 6), and authoritative selection
   projection (Tranche 7).
2. Then introduce or harden a `backlog-drain`-shaped typed abstraction that
   owns selection, running, gap drafting, recovery, retry, terminal block, and
   bounded exhaustion. The parent drain is a typed loop with an accumulator
   and an explicit terminal result union, not a wrapper around YAML state
   files.
3. Only then assemble the parent `.orc` and compute family parity.

`backlog-drain` follows the stdlib lowering rule: ordinary imported/std `.orc`
built on the generic composition substrate, with compile-time ProcRef hooks
for the family-specific phases, no compiler-name special casing, and full
effect/source-map/state-layout visibility.

### 19.2 Parity Evidence Labeling

Leaf compile success must never be mistakable for family parity (F11):

- every migration record labels each candidate as `leaf candidate`,
  `parent-callable candidate`, or `family candidate`;
- leaf compile evidence is necessary but insufficient; parent-callable
  behavior must be proven by fixtures that call the candidate from a parent
  context;
- output, terminal-state, artifact, resume/reuse, and recovery parity are
  machine-computed, never asserted;
- `--require-non-regressive` does not pass for a family target on leaf-only
  evidence; and
- `--require-promotable` fails until the full family is callable and
  non-regressive.

### 19.3 Acceptance

- A `backlog-drain` fixture drives selection, work-item execution, blocked
  recovery, retry, and bounded exhaustion as a typed loop with an explicit
  terminal result union.
- The parent drain `.orc` calls the implementation phase, work item, selector,
  and architect as single parent-callable workflows, not split leaves.
- No parent-drain semantics live in uncertified command glue or YAML state
  files.
- Run-state and recovery transitions on the drain path go through Tranche 6
  surfaces.
- Family parity evidence carries explicit candidate labels, and a family
  target with leaf-only evidence fails `--require-non-regressive`.
- The full family parity report computes `non_regressive=true` before any
  primary-surface decision, and `--require-promotable` passes before any
  YAML-primary replacement.

## 20. Tranche 10: Focused Adapter Lint Inventory

### 20.1 Contract

Adapter linting should be staged. New `.orc` and strict migration CI should
fail on hidden semantic glue. Legacy YAML should first receive inventory,
classification, and allowlist metadata rather than broad hard errors.

### 20.2 Acceptance

- Inventory covers inline Python, inline shell, heredocs, nested subprocesses,
  pointer reads/writes, markdown report parsing, stdout scraping, and manual
  JSON rewrites.
- Each occurrence is classified by behavior class and replacement route,
  consistent with the Tranche 6 classification of drain-family helpers.
- New `.orc` rejects hidden semantic glue unless it is behind a certified
  adapter or explicitly accepted temporary bridge.
- Strict migration CI rejects hidden glue unless allowlisted with owner,
  replacement, and expiry.

## 21. Deferred Work

### 21.1 Runtime Closures

Runtime closures remain deferred. The practical composition route is
compile-time `ProcRef`, `bind-proc`, `let-proc` where accepted, and
specialization before runtime artifacts are produced.

Do not use runtime closures to work around missing effectful composition,
nested structured control, stdlib expansion, or ProcRef specialization.

### 21.2 Broad Legacy YAML Lint Enforcement

Do not hard-error all legacy YAML inline glue as part of this tranche. Legacy
workflows may remain warning/allowlist surfaces until selected for migration or
strict CI.

### 21.3 `orchestrate explain`

`orchestrate explain` is valuable, but it should follow stable source maps,
Semantic IR layout entries, effect summaries, proof scopes, and path allocation
records. Until then, it risks becoming a brittle report generator over moving
internals.

## 22. Evidence And Implementation Boundaries

### 22.1 Required Evidence

Nested structured control follows this design only if the implementation-phase
acceptance fixture passes compile/typecheck, shared validation, source-map and
Semantic IR evidence, and dry-run or fake-provider smoke as one workflow.
Splitting the fixture into leaves is not evidence.

Typed result translation follows this design only if the three cross-union
mappings in Section 12 lower and validate; renaming variants to match is not
evidence.

The private context bridge follows this design only if public-boundary
inspection proves generated roots are hidden and resume reconstructs the same
private paths. A lint waiver that re-admits raw `state/` inputs is not
evidence.

Adapter and state-transition work follows this design only if every retained
drain-family helper has a recorded classification and the migration path's
state transitions go through typed effects or certified adapters. A
compileable `command-result` wrapper is not evidence.

Family composition follows this design only if the parent drain is a typed
loop over parent-callable workflows with machine-computed family parity.
Parent wrappers over YAML state files are not evidence.

### 22.2 Prohibited Evidence

The following do not prove this design:

- a nested-control fixture that only typechecks but is rejected by shared
  validation;
- leaves recomposed by a YAML parent while the `.orc` parent remains blocked,
  presented as family parity;
- a compatibility-shaped union whose variant names were chosen to avoid the
  union-translation defect;
- variant fields renamed to globally unique names presented as variant-scoped
  identity;
- a synthetic top-level `PhaseCtx` or `state_root` input presented as context
  bootstrap;
- legacy `state/` paths exposed as public `.orc` inputs under a lint waiver;
- an uncertified helper script wrapped in `command-result` presented as a
  certified adapter;
- raw argv assembly in high-level `.orc` presented as an adapter call surface;
- a publication script whose output path is consumed via pointer files rather
  than typed projection or private context;
- a leaf-only parity report passing a family-level gate; or
- a hand-labeled "parent-callable" claim without fixtures that call the
  candidate from a parent context.

## 23. Verification Strategy

Current-state inventory tests:

- verify `std/phase.orc` exports the current review/revise stdlib entrypoints;
- verify any claimed implemented route has focused compile/typecheck/lowering
  evidence before a new gap tries to rebuild it;
- verify design-index/status entries do not describe completed foundation work
  as future work;
- verify run-state or parity evidence backs any `implemented` status claim; and
- verify the design-delta findings rows in Section 5 still describe current
  behavior before selecting tranche work.

Nested structured-control tests:

- implementation-phase acceptance fixture (Section 11.4) end to end;
- `match` nested in a `match` branch;
- `repeat_until` nested in a `match` branch;
- `review-revise-loop` invoked in a `match` branch;
- nested structured control inside a reusable procedure invoked from a branch;
- branch-scope step ID collision fixtures across repeated branches and loop
  iterations;
- resume identity stability for branch-scoped generated steps;
- unsupported nested composition negative fixtures with pre-lowering
  diagnostics.

Typed result translation tests:

- `ReviewLoopResult.APPROVED -> ImplementationPhaseResult.COMPLETED`;
- `ReviewLoopResult.EXHAUSTED -> ImplementationPhaseResult.REVIEW_EXHAUSTED`;
- `ImplementationAttempt.BLOCKED -> ImplementationPhaseResult.BLOCKED`;
- cross-union mapping never raises `KeyError`; rejections are typed
  diagnostics;
- same logical field name in two variants with distinct lowered identities, or
  the documented-restriction compile-time diagnostic.

Generic effectful composition tests:

- effectful `let*` with provider and command results;
- effectful `match` branch normalization with variant proof;
- same-file call using locally constructed records;
- reusable procedure containing provider/command effects;
- unsupported composition negative fixtures.

Imported/std `.orc` tests:

- tiny imported helper;
- imported helper with visible provider/command effects;
- imported helper with match proof;
- imported helper with loop state and source-map provenance;
- imported helper invoked from a branch scope;
- imported phase-context record validated structurally across module
  boundaries (F1 regression);
- denylist test for promoted stdlib-name compiler special casing.

Review/revise tests:

- APPROVE;
- REVISE->APPROVE;
- BLOCKED;
- EXHAUSTED;
- the same four outcomes with the loop nested in a `match` branch, a reusable
  workflow call, and a parent module;
- loop terminal variants translated to a differently named domain union;
- findings validation;
- evidence redirection negative case;
- no runtime ProcRef/provider/prompt/type leak;
- source-map provenance;
- nested-invocation resume checkpoint identity.

Private context bridge tests:

- runtime-owned context hidden from public boundary for plan, selector,
  architect, work-item, and parent candidates;
- resume reconstructs identical private context paths;
- source-map/Semantic IR provenance for generated context values;
- YAML interop wrapper passes legacy `state/` values privately with
  migration-bridge labeling;
- defaults match YAML candidate;
- shared validation sees correct public/private split.

Certified adapter and state-transition tests:

- adapter declaration call with typed fields lowers to a certified command
  boundary;
- wrong-typed adapter field fails at compile/typecheck;
- classification record exists for every retained drain-family helper;
- run-state/recovery transition routes through a typed effect or certified
  adapter;
- negative fixture: raw argv assembly for a semantic helper at a high-level
  boundary is rejected or flagged.

Typed projection tests:

- selector exposes typed selection result with authoritative bundle identity;
- published bundle path is allocator-owned with provenance;
- downstream work-item consumes the selection result without pointer-file
  reads;
- bridge-certified publication records its native replacement route.

Resume-or-start tests:

- reusable approved prior result;
- stale input hash;
- missing artifact;
- schema mismatch;
- unsupported version;
- fresh/resumed branch normalization.

Family composition and parity tests:

- `backlog-drain` typed loop with accumulator and explicit terminal union;
- parent drain calls single parent-callable phase/work-item workflows;
- candidate labels (`leaf`, `parent-callable`, `family`) present in parity
  evidence;
- family target with leaf-only evidence fails `--require-non-regressive`;
- recovery and run-state parity machine-computed.

Migration evidence:

- compile;
- shared validation;
- dry-run or smoke;
- output contract parity;
- terminal state parity;
- artifact parity;
- resume/reuse parity;
- recovery parity for the drain family;
- deprecated-mechanic replacement or accepted waiver;
- strict `migration-parity` report computes `non_regressive=true`; and
- `--require-promotable` passes before any primary-surface replacement.

## 24. Declarative Acceptance Scenarios

### 24.1 Nested Implementation Phase

Initial state: an `.orc` implementation phase lowers
`provider-result -> ImplementationAttempt`, matches on the attempt, runs
`command-result` checks plus `review-revise-loop` in the `COMPLETED` branch,
and returns a typed `ImplementationPhaseResult` from both branches.

Entrypoint: compile, shared validation, and dry-run or fake-provider smoke.

Expected result: one parent-callable workflow validates, with branch-scoped
generated steps visible to shared validation, allocator-owned generated paths,
and matching source-map and Semantic IR entries.

Forbidden result: the phase must be split into `execute-implementation-attempt`
and `review-completed-implementation` leaves to pass validation.

### 24.2 Union Result Translation

Initial state: the implementation phase maps `ReviewLoopResult.APPROVED` to
`ImplementationPhaseResult.COMPLETED` and `ReviewLoopResult.EXHAUSTED` to
`ImplementationPhaseResult.REVIEW_EXHAUSTED`.

Entrypoint: compile/typecheck and lowering.

Expected result: the output variant comes from the returned variant
expression; both mappings lower and validate.

Forbidden result: lowering raises `KeyError`, or the author renames domain
variants to match inner loop states.

### 24.3 Private Context Wrapper

Initial state: a YAML-compatible `.orc` migration wrapper must call reusable
phase workflows that need run/state/phase roots, while the legacy YAML caller
still passes `state_root` and `run_state_path`.

Entrypoint: compile, public-boundary inspection, run, and resume.

Expected result: the wrapper's public boundary excludes all generated roots;
legacy values enter through the labeled YAML interop bridge; resume
reconstructs identical private paths; source maps and Semantic IR identify
every bridged value.

Forbidden result: `state_root` appears as an ordinary public `.orc` input, or
a synthetic `PhaseCtx` input is added to satisfy the type checker.

### 24.4 Certified Selector Projection

Initial state: the selector provider returns a typed selection decision; the
parent drain needs an authoritative selection bundle identity.

Entrypoint: compile and run of the selector plus a downstream work-item call.

Expected result: the bundle identity comes from a native typed projection or
an explicitly certified deterministic projection; the downstream call consumes
the typed selection result.

Forbidden result: the parent reads a pointer file written by an unclassified
script to discover the bundle path.

### 24.5 Family Parity Gate

Initial state: plan, implementation, selector, architect, and work-item
candidates compile as leaves; the parent drain `.orc` does not yet exist.

Entrypoint:

```bash
python -m orchestrator migration-parity \
  workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json \
  --require-non-regressive
```

Expected result: the family-level target fails the gate, and the evidence
labels each candidate as a leaf candidate.

Forbidden result: leaf compile evidence aggregates into a passing family gate,
or `--require-promotable` passes before the parent drain is parent-callable.

## 25. Success Criteria

This post-foundation tranche succeeds when:

- the nested implementation-phase fixture compiles, validates, and smokes as
  one parent-callable workflow, and nested `match` / `repeat_until` /
  `review-revise-loop` shapes pass the Tranche 1 evidence set;
- union-to-union result translation derives output variants from returned
  variant expressions, and variant field identity is variant-scoped or the
  restriction is explicitly documented with compile-time diagnostics;
- generic effectful composition is used by at least one non-review imported
  `.orc` fixture and the review/revise stdlib route;
- imported/std `.orc` definitions preserve effects, source maps, proof scopes,
  and generated path provenance, including from branch scopes, and stdlib
  shape recognition is structural across module boundaries;
- current review/revise stdlib implementation is inventoried and hardened,
  rather than rebuilt, compiles in promoted mode without compiler-name
  special casing, and composes in nested contexts with stable resume identity;
- `.orc` entrypoints hide runtime-owned context behind the private executable
  context bridge, expose YAML-equivalent defaults where parity is claimed, and
  a YAML interop bridge carries legacy `state/` values privately during
  migration;
- every retained drain-family helper is classified, run-state and recovery
  transitions go through typed runtime effects or certified adapters, and
  `.orc` calls adapters through a typed declaration surface rather than raw
  argv;
- deterministic selection/bundle publication is a typed projection or an
  explicitly certified bridge with a recorded replacement route;
- `resume-or-start` has canonical typed reusable-state validation;
- the parent drain is a typed `backlog-drain`-shaped loop over parent-callable
  workflows, with no semantics hidden in uncertified glue or YAML state files;
- parity evidence distinguishes leaf, parent-callable, and family candidates,
  and family gates fail on leaf-only evidence;
- adapter linting has an inventory and staged enforcement policy;
- at least one real workflow family reaches strict, machine-computed
  `non_regressive=true` through `.orc`; and
- any YAML-primary replacement also passes `--require-promotable`.

## 26. Summary Recommendation

Use this document as the next target only after a short current-state inventory
pass updates stale claims and confirms the foundation success criteria remain
implemented. The next implementation driver should select from the inventory,
not from roadmap wording that predates the completed stdlib and foundation
routes.

The 2026-06-09 design-delta drain sharpened the priority: the migration is not
blocked by Lisp syntax, it is blocked by first-class workflow composition.
Until nested structured control survives shared validation, runtime-owned
context crosses boundaries privately, and run-state transitions have certified
or native owners, the drain family must continue as typed leaf candidates plus
explicit bridge records, with YAML primary.

The key post-foundation move is to stop adding one-off frontend conveniences
and instead verify, harden, and generalize the composition substrate that makes
stdlib `.orc` credible: nested structured control, principled result
translation, generic effectful blocks, imported/std definitions, visible
effects, proof preservation, source maps, private executable context,
certified state transitions, generated path ownership, and strict
parent-callable migration evidence.
