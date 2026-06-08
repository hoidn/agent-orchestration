# Workflow Lisp Post-Foundation Composition And Stdlib Migration

Status: draft design
Kind: follow-on architecture / migration target design
Created: 2026-06-08
Scope: work that should begin after the runtime migration foundation is
accepted: generic effectful composition, imported/std `.orc` reuse,
`review-revise-loop` stdlib convergence, entrypoint bootstrap/defaults, and
canonical `resume-or-start` validation.

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
- `specs/dsl.md`
- `specs/io.md`
- `specs/state.md`

## 1. Purpose

This document defines the next Workflow Lisp target after the runtime migration
foundation is complete.

The foundation target hardens three lower-level authority seams:

1. command structured-output conformance;
2. machine-readable migration promotion gates; and
3. centralized generated state/path allocation.

This document starts after those seams are reliable. Its job is to make higher
level `.orc` composition and stdlib reuse implementation-ready without
recreating compiler-special forms, hidden command glue, or YAML-shaped
frontends.

The target is practical: one real workflow family should reach
machine-computed `non_regressive=true` through `.orc`, with visible effects,
source maps, deterministic generated state/path allocation, and no
compiler-special review-loop branch.

## 2. Executive Decision

After `workflow_lisp_runtime_migration_foundation.md` is accepted and its
verification evidence passes, implement the next tranche in this order:

1. Generic effectful composition.
2. Imported/std `.orc` expansion and reuse hardening.
3. `review-revise-loop` as ordinary imported/std `.orc`.
4. Entrypoint context bootstrap and input defaults.
5. Canonical `resume-or-start` reusable-state validation.
6. Focused adapter lint inventory and staged enforcement.
7. Optional `orchestrate explain` only after source maps, Semantic IR layout,
   effects, and path allocation are stable enough to explain.

This document deliberately does not prioritize runtime closures, broad legacy
YAML lint hard errors, or explain tooling before the composition and migration
surfaces are stable.

## 3. Prerequisite Boundary

This document is blocked until the runtime migration foundation has completed
its success criteria:

- command structured-output tests pass for runtime env precedence, parent
  creation, and missing-bundle fail-closed behavior;
- `migration-parity` has strict gate behavior and schema/version validation;
- `StateLayout` / `PathAllocator` owns the blocking generated path families;
- generated path provenance is present in source maps and Semantic IR; and
- compiler-owned `__write_root__...` inputs are not exposed at public workflow
  entrypoints.

If any of those remain incomplete, this document may be used for planning but
must not be used to justify more `.orc` primary-promotion work.

## 4. Authority And Dependency Direction

### 4.1 This Document Consumes

- `workflow_lisp_runtime_migration_foundation.md` owns command output
  authority, strict promotion gates, and the first generated path allocation
  boundary.
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
- `workflow_lisp_runtime_closures_boundary.md` owns the decision to keep
  runtime closures deferred.
- `workflow_command_adapter_contract.md` owns adapter certification and lint
  policy.
- `workflow_lisp_key_migration_parity_architecture.md` owns promotion evidence
  and family-level parity policy.

### 4.2 This Document Owns

- the post-foundation implementation sequence for Workflow Lisp composition;
- the acceptance boundary for generic effectful composition;
- the acceptance boundary for ordinary imported/std `.orc` reuse;
- the post-foundation target for `review-revise-loop` convergence;
- the entrypoint bootstrap/defaults gap that prevents YAML parity for wrapper
  workflows;
- the canonical `resume-or-start` validation gap; and
- which later work remains optional or deferred.

### 4.3 This Document Does Not Own

- command structured-output runtime rules;
- migration report schema and strict gate CLI behavior;
- the first `StateLayout` / `PathAllocator` implementation boundary;
- runtime closures;
- a full semantic diff engine;
- broad hard-error linting for all legacy YAML; or
- operator explain tooling as a prerequisite for stdlib migration.

## 5. Target Dependency Direction

The desired post-foundation dependency direction is:

```text
authored .orc
  -> imported/std .orc definitions
  -> macro/procedure expansion, if any
  -> generic effectful block normalization
  -> Core AST with explicit statements, effects, proof scopes, and source maps
  -> shared validation
  -> Semantic IR / Executable IR
  -> existing runtime
  -> migration-parity strict gate
  -> primary-surface decision, only if non_regressive and eligible
```

The prohibited direction is:

```text
authored .orc
  -> compiler recognizes a library form by name
  -> hidden Python lowerer builds workflow control
  -> generated paths are synthesized locally
  -> effects or proof scopes appear only after the fact
  -> compile/dry-run success is treated as promotion parity
```

## 6. Goals

- Complete generic effectful composition so new high-level forms do not need
  one-off lowerers.
- Make imported/std `.orc` definitions reusable through the ordinary compiler
  pipeline.
- Keep provider, command, workflow, state, artifact, and resource effects
  visible after expansion.
- Preserve source maps through imported definitions, generated statements,
  generated paths, and selected compile-time procedure hooks.
- Keep `ProcRef`, `bind-proc`, specialization details, and procedure choices
  compile-time-only.
- Express `review-revise-loop` as ordinary imported/std `.orc`, or through a
  thin macro that expands to ordinary `.orc` semantics, with no promoted
  compiler-name special case.
- Add entrypoint context bootstrap and input defaults so `.orc` wrappers can
  match YAML public boundaries.
- Specify canonical `resume-or-start` validation so reusable state recovery is
  typed and parity-testable.
- Produce at least one real workflow-family `.orc` parity report with
  computed `non_regressive=true`.

## 7. Non-Goals

- Do not add runtime closures.
- Do not add runtime procedure values or dynamic dispatch.
- Do not make `orchestrate explain` a prerequisite for this tranche.
- Do not hard-error all legacy YAML inline glue before migration inventory.
- Do not use report parsing, pointer files, stdout, debug YAML, or generated
  summaries as semantic authority.
- Do not replace YAML primaries based on compile, shared validation, or dry-run
  alone.
- Do not expand the foundation tranches in this document; fix missing
  foundation work in the foundation design or its implementation plans.

## 8. Architecture Invariants

- Workflow Lisp remains a frontend over the existing validated workflow model.
- Shared validation remains authoritative after lowering.
- Future frontend features may add authoring power only by lowering into the
  existing validated workflow model or into a separately accepted future
  runtime contract.
- All effects introduced by imported/std `.orc` code are visible.
- Every generated statement, path, helper, and selected ProcRef body has
  source-map provenance.
- Generated state/path allocation goes through `StateLayout` / `PathAllocator`.
- No runtime state, artifact contract, provider result, command result, or
  workflow output contains `ProcRef`, provider ref, prompt ref, closure,
  unresolved type parameter, or runtime type object.
- Reports and debug projections are views.
- Migration promotion is machine-computed by strict parity evidence.

## 9. Tranche 1: Generic Effectful Composition

### 9.1 Contract

Generic effectful composition is the compiler substrate that turns authored
expression structure into explicit executable statements without one-off
lowering per high-level form.

Representative normalization:

```text
authored expression
  -> typed expression/effect tree
  -> effectful block normalization
  -> explicit statements with dependencies
  -> proof/effect/source-map annotations
  -> Core AST
  -> shared validation
```

### 9.2 Required Shapes

The first tranche should cover:

- effectful `let*`;
- effectful `match` arms;
- same-file calls with locally constructed records;
- reusable procedures containing provider/command/workflow effects;
- generated write roots across reusable call boundaries; and
- proof-preserving projection from normalized branches.

### 9.3 Acceptance

- A non-review imported `.orc` fixture uses the same effectful composition
  route as later stdlib forms.
- Provider and command effects inside reusable procedures remain visible to
  shared validation and runtime planning.
- Variant proof scopes survive normalization.
- Source maps identify authored forms and generated statements.
- Generated write roots use `StateLayout` / `PathAllocator`.
- Unsupported effectful compositions fail before lowering with actionable
  diagnostics.

## 10. Tranche 2: Imported/Std `.orc` Reuse Hardening

### 10.1 Contract

Imported/std `.orc` definitions must be reusable through the ordinary compiler
pipeline. A stdlib form may provide ergonomic syntax, but the control flow must
belong to grammar-accepted `.orc` definitions or to generic compiler machinery
available to ordinary `.orc`.

### 10.2 Tasks

- Load stdlib `.orc` through ordinary import resolution.
- Expand or specialize imported definitions without hidden runtime semantics.
- Preserve source maps for caller, imported definition, generated helpers, and
  generated paths.
- Preserve effect summaries for imported provider/command/workflow calls.
- Keep compile-time `ProcRef` values out of runtime artifacts.
- Add architectural denylist tests for promoted name-special compiler paths.

### 10.3 Acceptance

- A tiny imported `.orc` helper expands, typechecks, lowers, and validates.
- An imported `.orc` helper with provider/command effects exposes those
  effects.
- An imported `.orc` helper with `match` preserves variant proof.
- An imported `.orc` helper with loop state preserves source maps and
  generated path provenance.
- Promoted fixtures fail if they use compiler branches keyed to stdlib form
  names rather than the generic import/expansion route.

## 11. Tranche 3: `review-revise-loop` Stdlib Convergence

### 11.1 Contract

`review-revise-loop` must be an ordinary imported/std `.orc` abstraction in the
promoted route. It may use compile-time ProcRefs, generic loop exhaustion
projection, structural constraints, or a thin macro that expands to ordinary
`.orc`, but it must not depend on a promoted compiler branch that recognizes
the literal name `review-revise-loop`.

### 11.2 Required Behavior

- `APPROVE` exits with typed completion.
- `REVISE` invokes fix and continues; it is not completion.
- `BLOCKED` exits with typed non-completion.
- `EXHAUSTED` is explicit typed non-completion.
- Review findings are validated structured state, not markdown extraction.
- Report paths and findings paths are independently seeded and projected.
- Carried evidence identity comes from inputs/state, not review-provider
  replacement fields.

### 11.3 Acceptance

- Disable promoted review-loop-specific typechecker/lowerer paths.
- Compile `review-revise-loop` through imported/std `.orc`.
- Generated workflow contains ordinary provider, command, match, loop,
  projection, and materialization surfaces.
- Source maps include caller, stdlib definition, generated helper, generated
  paths, review ProcRef, and fix ProcRef.
- Runtime artifacts contain no ProcRef, provider ref, prompt ref, closure, or
  unresolved type parameter.
- APPROVE, REVISE->APPROVE, BLOCKED, and EXHAUSTED fixtures pass.
- A real workflow-family parity report computes `non_regressive=true` before
  any YAML-primary replacement.

## 12. Tranche 4: Entrypoint Bootstrap And Defaults

### 12.1 Contract

Promoted `.orc` entrypoints must not expose fake runtime context inputs or
extra public defaults that YAML users did not need. Runtime-owned contexts such
as `RunCtx` and `PhaseCtx` must be introduced through an accepted bootstrap
surface and kept out of public workflow signatures.

### 12.2 Acceptance

- A promoted `.orc` wrapper can call reusable workflows requiring runtime-owned
  context without exposing `run_id`, write roots, or synthetic `PhaseCtx` inputs
  at the public boundary.
- `.orc` input defaults match the corresponding YAML public boundary where
  parity is claimed.
- Shared validation and migration parity inspect the public boundary, not only
  private generated bindings.
- Source maps identify generated context/default bindings.

## 13. Tranche 5: Canonical `resume-or-start` Validation

### 13.1 Contract

`resume-or-start` must become a typed reusable-state validation surface, not a
prettier recovery gate over ad hoc files or report text.

It validates prior reusable state, normalizes resumed and fresh branches to the
same return type, and exposes explicit recoverable outcomes when prior state is
stale, missing, incompatible, or unsupported.

### 13.2 Acceptance

- Reusable approved prior result resumes without rerunning fresh work.
- Stale input hash routes through typed stale-state handling.
- Missing artifact routes through typed missing-state handling.
- Schema mismatch routes through typed incompatible-state handling.
- Unsupported version routes through typed unsupported-state handling.
- Fresh branch normalizes to the same result type as resumed branch.
- Resume decisions are based on state/artifact contracts, not report parsing or
  pointer-file authority.

## 14. Tranche 6: Focused Adapter Lint Inventory

### 14.1 Contract

Adapter linting should be staged. New `.orc` and strict migration CI should
fail on hidden semantic glue. Legacy YAML should first receive inventory,
classification, and allowlist metadata rather than broad hard errors.

### 14.2 Acceptance

- Inventory covers inline Python, inline shell, heredocs, nested subprocesses,
  pointer reads/writes, markdown report parsing, stdout scraping, and manual
  JSON rewrites.
- Each occurrence is classified by behavior class and replacement route.
- New `.orc` rejects hidden semantic glue unless it is behind a certified
  adapter or explicitly accepted temporary bridge.
- Strict migration CI rejects hidden glue unless allowlisted with owner,
  replacement, and expiry.

## 15. Deferred Work

### 15.1 Runtime Closures

Runtime closures remain deferred. The practical composition route is
compile-time `ProcRef`, `bind-proc`, `let-proc` where accepted, and
specialization before runtime artifacts are produced.

Do not use runtime closures to work around missing effectful composition,
stdlib expansion, or ProcRef specialization.

### 15.2 Broad Legacy YAML Lint Enforcement

Do not hard-error all legacy YAML inline glue as part of this tranche. Legacy
workflows may remain warning/allowlist surfaces until selected for migration or
strict CI.

### 15.3 `orchestrate explain`

`orchestrate explain` is valuable, but it should follow stable source maps,
Semantic IR layout entries, effect summaries, proof scopes, and path allocation
records. Until then, it risks becoming a brittle report generator over moving
internals.

## 16. Verification Strategy

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
- denylist test for promoted stdlib-name compiler special casing.

Review/revise tests:

- APPROVE;
- REVISE->APPROVE;
- BLOCKED;
- EXHAUSTED;
- findings validation;
- evidence redirection negative case;
- no runtime ProcRef/provider/prompt/type leak;
- source-map provenance.

Entrypoint/default tests:

- runtime-owned context hidden from public boundary;
- defaults match YAML candidate;
- shared validation sees correct public/private split.

Resume-or-start tests:

- reusable approved prior result;
- stale input hash;
- missing artifact;
- schema mismatch;
- unsupported version;
- fresh/resumed branch normalization.

Migration evidence:

- compile;
- shared validation;
- dry-run or smoke;
- output contract parity;
- terminal state parity;
- artifact parity;
- resume/reuse parity;
- deprecated-mechanic replacement or accepted waiver; and
- strict `migration-parity` report computes `non_regressive=true`.

## 17. Success Criteria

This post-foundation tranche succeeds when:

- generic effectful composition is used by at least one non-review imported
  `.orc` fixture and the review/revise stdlib route;
- imported/std `.orc` definitions preserve effects, source maps, proof scopes,
  and generated path provenance;
- `review-revise-loop` compiles in promoted mode without compiler-name
  special casing;
- `.orc` entrypoints can hide runtime-owned context and expose YAML-equivalent
  defaults where parity is claimed;
- `resume-or-start` has canonical typed reusable-state validation;
- adapter linting has an inventory and staged enforcement policy; and
- at least one real workflow family reaches strict, machine-computed
  `non_regressive=true` through `.orc`.

## 18. Summary Recommendation

Use `workflow_lisp_runtime_migration_foundation.md` as the next immediate
implementation driver. Once it passes, use this document as the next target.

The key post-foundation move is to stop adding one-off frontend conveniences
and instead finish the composition substrate that makes stdlib `.orc` credible:
generic effectful blocks, imported/std definitions, visible effects, proof
preservation, source maps, generated path ownership, and strict migration
evidence.

