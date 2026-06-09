# Workflow Lisp Typecheck Family Decomposition Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-typecheck-family-decomposition`
Target design: `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_mvp_specification.md`

## Scope

This slice covers exactly the bounded prerequisite selected by the current
drain state before structural constraints, imported `.orc` expansion follow-on
work, or stdlib review-loop follow-ons add more typing behavior:

- decompose the current mixed `orchestrator/workflow_lisp/typecheck.py` owner
  surface into explicit typechecking family owners behind the existing
  `orchestrator.workflow_lisp.typecheck` compatibility import;
- record one exact owner-file path for shared typecheck context and diagnostic
  helpers, dispatch routing, proof and field validation, provider and command
  effect validation, callable checks, and remaining legacy stdlib-bridge
  typing;
- keep `procedure_typecheck.py` as the procedure-call and generated-procedure
  typing owner, but widen it only where necessary to absorb `let-proc` and
  local-procedure helper typing that already belongs to procedure semantics;
- preserve current diagnostics, spans, form paths, expansion stacks, proof
  behavior, effect summaries, compile-time-only ProcRef and WorkflowRef rules,
  and the public `typecheck.py` import surface;
- add only the characterization and architecture-boundary tests needed to
  prove the move is behavior-preserving.

Out of scope for this slice:

- structural constraint semantics, parametric type inference changes, or new
  shared-field typing behavior;
- Track A imported `.orc` expansion, review-loop bridge removal, or form
  registry changes;
- lowering, runtime, shared validation, Core Workflow AST, Semantic Workflow
  IR, TypeCatalog, SourceMap, pointer-authority, or variant-proof redesign;
- new scripts, command adapters, runtime-native effects, or command-boundary
  policy changes;
- broad cleanup of unrelated frontend modules beyond what is required to stop
  `typecheck.py` from being the mixed owner for the families named here.

This is a bounded implementation architecture for the selected prerequisite
only. It does not replace the parent frontend design, the MVP baseline, or the
broader review/revise stdlib integration architecture.

## Problem Statement

The target design makes one prerequisite explicit: structural constraints and
other follow-on slices must not continue extending a 5,932-line
`typecheck.py` that still mixes dispatch, proof facts, provider and command
effect checks, workflow-call compatibility, legacy review-loop bridge typing,
and pass-local mutable state.

The current checkout confirms that this risk is still live:

1. `typecheck.py` is 5,932 physical lines and still owns the top-level
   `_typecheck(...)` dispatcher, `ProofFact` and `ProofScope`, field/projection
   proof helpers, workflow call validation, provider and command validation,
   reusable-state typing inputs, `let-proc` typing, and the bulk of
   review-loop `StdlibSpecializationExpr` typing.
2. The file still relies on module-global pass state such as
   `_ACTIVE_PROC_REF_VALUE_ENV`,
   `_ACTIVE_VALUE_EXPR_ENV`,
   `_ACTIVE_GENERATED_LOCAL_PROCEDURES`,
   `_ACTIVE_WORKFLOW_SIGNATURE`,
   `_ACTIVE_REUSABLE_STATE_PRODUCER_CONTEXT`, and
   `_ACTIVE_REVIEW_LOOP_LEGACY_BRIDGE_POLICY`.
3. Some owner seams already exist, but only partially:
   `procedure_typecheck.py` owns `ProcedureCallExpr` typing and parametric
   specialization requests,
   `phase_stdlib_typecheck.py` guards the legacy review-loop bridge policy,
   and `workflow_refs.py` owns compile-time workflow-ref resolution.
   The mixed typechecker still imports and coordinates all of those seams
   directly while remaining the real owner for most family behavior.
4. Follow-on structural-constraint work would otherwise need to add the shared
   field-access hook into the same mixed file that still owns proof facts,
   workflow-call checks, command-result adapter validation, and stdlib bridge
   typing.
5. The selected design-gap bundle already records the unblock condition:
   `workflow-lisp-structural-parametric-constraints` remains blocked until this
   prerequisite supplies an explicit owner map and behavior-preserving
   verification plan.

This gap is therefore not "clean up typecheck someday." It is the smallest
honest prerequisite that lets later type-system work target clear owners
instead of reopening the same mixed facade.

## Design Constraints

The implementation must stay coherent with:

- `docs/index.md`
- `docs/steering.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - `8.1 Hard Preflight Before Track A`
  - `9.6 Decompose typecheck.py By Typechecking Family`
  - `9.6.1 Prerequisite Handoff Contract`
  - `Stage 1 - Behavior-Preserving Refactor Preflight`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
- `docs/design/workflow_lisp_refactor_architecture.md`
- `docs/design/workflow_lisp_compile_time_parametric_specialization.md`
- `docs/design/workflow_lisp_structural_parametric_constraints.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/2026-05-23-workflow-lisp-refactoring-backlog.md`
- `docs/plans/2026-06-02-workflow-lisp-low-hanging-refactor-plan.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/6/prerequisite-selector/selection.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/6/design-gap-architect/architecture-targets.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/6/design-gap-architect/existing-architecture-index.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

The slice must also preserve these guardrails:

- keep `orchestrator/workflow_lisp/` as the frontend-owned package and shared
  runtime semantics under `orchestrator/workflow/`;
- reuse the staged frontend pipeline:
  read -> syntax -> macro expansion -> definitions/procedures/workflows ->
  typecheck -> lowering -> shared validation;
- preserve the public `orchestrator.workflow_lisp.typecheck` import surface for
  callers, tests, `__init__.py`, `functions.py`, `workflows.py`, and
  `compiler.py`;
- preserve current diagnostics, source spans, form paths, expansion stacks,
  proof behavior, effect summaries, and compile-time-only ProcRef and
  WorkflowRef restrictions;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- keep command-result and certified-adapter semantics visible to the typecheck
  effect surface rather than hiding them behind helper extraction.

`docs/design/workflow_command_adapter_contract.md` is authoritative here even
though this slice adds no new adapter. The mixed typechecker currently owns
`command-result` argv validation, certified-adapter usage checks, provider and
command effect classification, and macro-hidden-effect diagnostics. The owner
split must not create a loophole where command semantics become implicit or
unvalidated.

`docs/steering.md` is empty in this checkout. That is not permission to widen
scope.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The full index in
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/6/design-gap-architect/existing-architecture-index.md`
was reviewed for coherence. The directly reused slices for this gap are:

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-validation-diagnostics-pipeline/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/track-a-form-registry-elaboration-boundary/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-owner-seam-split-prerequisite/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-parametric-defproc-specialization-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-structural-parametric-constraints/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md`

### Decisions Reused

- Reuse the staged frontend pipeline and package ownership split.
- Reuse the owner-seam rule from the prerequisite procedure split:
  `procedure_typecheck.py` remains the owner for procedure-call typing and
  generated helper typing, and follow-on slices should not push that behavior
  back into the public facade.
- Reuse the existing provenance substrate:
  `SourcePosition`,
  `SourceSpan`,
  recursive syntax objects,
  `LispFrontendDiagnostic`,
  macro expansion stacks,
  and the existing source-map bridge remain authoritative.
- Reuse the compile-time-only ProcRef and WorkflowRef rules from the parametric
  specialization and workflow-ref linking slices.
- Reuse the current command-boundary policy: `command-result` and certified
  adapter checks remain explicit frontend typing behavior subject to the
  command-adapter contract.
- Reuse the current legacy review-loop bridge seam in
  `phase_stdlib_typecheck.py` instead of inventing a second temporary bridge
  owner.

### New Decisions In This Slice

- Keep `orchestrator/workflow_lisp/typecheck.py` as a compatibility facade
  file, not a new package facade. The sibling-module route is chosen here
  because the public import surface is already concentrated on
  `from orchestrator.workflow_lisp.typecheck import ...`, and unlike lowering,
  this slice does not need a new public subpackage path.
- Establish these exact post-split owner files:
  - `orchestrator/workflow_lisp/typecheck_context.py`
  - `orchestrator/workflow_lisp/typecheck_dispatch.py`
  - `orchestrator/workflow_lisp/typecheck_proofs.py`
  - `orchestrator/workflow_lisp/typecheck_effects.py`
  - `orchestrator/workflow_lisp/typecheck_calls.py`
  - existing `orchestrator/workflow_lisp/procedure_typecheck.py`
  - expanded `orchestrator/workflow_lisp/phase_stdlib_typecheck.py`
- Introduce one explicit `TypecheckContext` seam rather than continuing to add
  parameters and module globals to the monolithic dispatcher.
- Move `let-proc` and local-procedure helper typing into
  `procedure_typecheck.py` because those behaviors already belong to
  procedure-local compilation rather than general expression dispatch.
- Expand `phase_stdlib_typecheck.py` from a guard wrapper into the full owner
  for the temporary `StdlibSpecializationExpr` review-loop typing path until
  the promoted stdlib route deletes that path.

### Conflicts Or Revisions

Earlier implementation slices and plans often named `typecheck.py` directly as
the owner for proof, call, effect, and stdlib-bridge typing. This slice
revises that implementation shape narrowly:

- `typecheck.py` remains the public compatibility surface;
- it stops being the real owner for the families named in the target design;
- follow-on structural-constraint, imported `.orc`, and review-loop slices must
  target the new owner files rather than extending the facade directly.

This slice does not revise shared concepts such as Core Workflow AST, Semantic
Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant proof.

## Ownership Boundaries

This slice owns:

- the exact post-split owner-file paths for shared typecheck context,
  dispatcher routing, proof and field validation, provider and command effect
  validation, callable checks, and remaining stdlib bridge typing;
- the behavior-preserving move from module-global pass state toward one
  internal `TypecheckContext` and session-state seam;
- compatibility re-exports and delegating wrappers that preserve the current
  `typecheck.py` import surface;
- focused tests that prove family ownership moved without changing semantics.

This slice intentionally does not own:

- new structural constraints, new parametric inference behavior, or imported
  `.orc` typing semantics;
- lowering family decomposition, command adapter registration, or runtime
  changes;
- new runtime effect categories, new shared validation rules, or new adapter
  policies;
- deletion of the legacy `StdlibSpecializationExpr` review-loop bridge.

## Current Checkout Facts

The current checkout already contains the beginnings of the target split, but
not the full owner map required by the design:

- `orchestrator/workflow_lisp/typecheck.py` is still 5,932 lines.
- `orchestrator/workflow_lisp/procedure_typecheck.py` exists at 655 lines and
  already owns:
  `typecheck_procedure_definitions(...)`,
  `typecheck_procedure_call_expr(...)`,
  parametric specialization request collection, and generated procedure typing.
- `orchestrator/workflow_lisp/phase_stdlib_typecheck.py` exists at 51 lines but
  still only wraps the legacy review-loop bridge policy and delegates most real
  review-loop typing back to `typecheck.py`.
- `orchestrator/workflow_lisp/workflow_refs.py` already owns compile-time
  workflow-ref resolution and signature validation, but workflow-call typing and
  drain-role workflow-ref checks still live in `typecheck.py`.
- `orchestrator/workflow_lisp/README.md` already documents the procedure and
  lowering owner seams, but still describes `typecheck.py` as the top-level
  expression dispatcher and compatibility surface.
- The public import surface that must remain stable is small and explicit:
  tests, `functions.py`, `workflows.py`, `compiler.py`, and
  `orchestrator/workflow_lisp/__init__.py` import
  `typecheck_expression`,
  `TypedExpr`,
  `ProofFact`,
  `ProofScope`,
  `consume_generated_local_procedures(...)`,
  `reset_generated_local_procedure_state(...)`,
  and the active-workflow and reusable-state setter helpers from
  `typecheck.py`.

This checkout also gives the feasibility proof the drafting skill requires.
The refactor does not depend on an unproven substrate:

- `lowering/__init__.py` already proves a facade-preserving family split works
  in this package;
- `procedure_typecheck.py` already proves behavior can move out of the public
  facade while the facade import survives;
- `phase_stdlib_typecheck.py` already proves the temporary review-loop bridge
  can be isolated behind a dedicated owner seam.

## Proposed Owner Map

### Chosen Boundary Strategy

Keep `typecheck.py` as a thin compatibility file and add sibling owner modules.

Rationale:

- the target design allows `typecheck/context.py` "or equivalent";
- unlike `lowering`, this slice does not need a new public package namespace;
- converting `typecheck.py` into a same-name package would add import churn and
  filesystem reshaping that is unnecessary for this prerequisite;
- sibling owners can still make future implementation plans cite exact files
  instead of the facade.

### Target File Layout

```text
orchestrator/workflow_lisp/
  typecheck.py                    # compatibility facade and public re-exports only
  typecheck_context.py            # TypecheckContext, session state, diagnostics helpers
  typecheck_dispatch.py           # internal expression dispatcher and family routing
  typecheck_proofs.py             # proof facts, proof scopes, field/projection proof checks
  typecheck_effects.py            # provider/command typing and adapter/effect validation
  typecheck_calls.py              # workflow calls, workflow refs, function calls, call arg checks
  procedure_typecheck.py          # procedure calls, let-proc, generated procedure typing
  phase_stdlib_typecheck.py       # temporary StdlibSpecializationExpr review-loop bridge typing
```

### `typecheck_context.py`

This module becomes the owner for context and pass-local state that currently
lives in module globals.

It should own:

- `TypedExpr` and `ValueEnvironment`;
- `TypecheckContext` with the recursive inputs now drilled through `_typecheck`:
  catalogs, value env, function catalog, extern environment, command boundary
  environment, phase scope, effect maps, ProcRef resolution context, and the
  active proof scope;
- one small session-state object for mutable pass-local state:
  active ProcRef values,
  value-expression capture map,
  generated local procedures,
  let-proc rewrite results,
  active workflow signature,
  reusable-state producer context,
  and review-loop bridge policy;
- shared error and lint helpers now implemented as `_raise_error(...)` and
  `_raise_required_lint(...)`;
- stable wrapper functions re-exported by the facade:
  `consume_generated_local_procedures(...)`,
  `reset_generated_local_procedure_state(...)`,
  `set_active_workflow_signature(...)`,
  `clear_active_workflow_signature(...)`,
  `set_active_reusable_state_producer_context(...)`, and
  `clear_active_reusable_state_producer_context(...)`.

The public `typecheck_expression(...)` signature stays unchanged. The facade
constructs an initial `TypecheckContext`, seeds the session state, and delegates
to `typecheck_dispatch.py`.

### `typecheck_dispatch.py`

This module becomes the owner for the internal dispatcher and family routing.

It should own:

- the recursive internal equivalent of `_typecheck(...)`;
- basic literal, name, record, union constructor, `let*`, `if`, `match`,
  `loop/recur`, `with-phase`, `phase-target`, `resume-or-start`,
  `resource-transition`, `finalize-selected-item`, and `backlog-drain`
  routing that is not otherwise moved to a dedicated family owner;
- one explicit routing point for each delegated family:
  calls,
  proofs,
  effects,
  procedures,
  and legacy stdlib bridge;
- type-label and simple compatibility helpers that are still generic dispatcher
  utilities rather than family-specific policy.

This keeps one obvious update point for future expression-family routing without
making the public facade the owner.

### `typecheck_proofs.py`

This module becomes the owner for proof-bearing field access and proof-scope
management.

It should own:

- `ProofFact` and `ProofScope`;
- field and projection proof helpers currently embedded in `typecheck.py`,
  including union-variant field checks and proof-gated field-access
  diagnostics;
- proof-scope construction for `match` arms and any helper needed to keep
  variant-only fields rejected outside proof-bearing contexts;
- branch-local proof utilities used by `if`, `match`, and loop-carried
  convergence when proof facts affect typing.

Structural constraints later add the shared-field capability hook here, not to
the facade.

### `typecheck_effects.py`

This module becomes the owner for provider and command typing behavior that
currently sits beside unrelated families.

It should own:

- `provider-result` typing and expected-extern operand validation;
- `command-result` typing, argv validation, and certified-adapter contract
  checks;
- macro-hidden-effect detection and related provenance-aware diagnostics;
- effect compatibility helpers that belong to typechecking rather than the
  hashable effect-atom registry in `effects.py`.

This preserves the command-adapter contract in one explicit owner file.

### `typecheck_calls.py`

This module becomes the owner for non-procedure callable checks.

It should own:

- workflow call typing and binding compatibility;
- workflow-ref literal and argument compatibility helpers used during call
  typing;
- workflow-ref role validation for `selector`, `run-item`, and `gap-drafter`;
- function-call typing;
- reusable call-binding checks and any call-specific helper that is not owned
  by `procedure_typecheck.py`.

`workflow_refs.py` remains the authority for compile-time workflow-ref
resolution and signature objects. `typecheck_calls.py` consumes that authority
for expression typing.

### `procedure_typecheck.py`

This module remains the owner for procedure semantics and expands narrowly to
absorb the procedure-local expression family that still sits in the facade.

It should own:

- `ProcedureCallExpr` typing;
- parametric specialization request collection and generated procedure typing;
- `let-proc` typing, local procedure capture validation, scope-escape checks,
  generated helper registration, and local ProcRef rewrite support.

This keeps local-procedure behavior aligned with the procedure seam already
established by the owner-split prerequisite.

### `phase_stdlib_typecheck.py`

This module expands from a policy guard into the real owner for the temporary
review-loop bridge.

It should own:

- review-loop legacy bridge policy guards;
- `StdlibSpecializationExpr` typing for the temporary review-loop path;
- review-loop result-contract validation;
- generated review-loop helper typing utilities and resume metadata derivation
  that are currently embedded in `typecheck.py`.

The bridge remains temporary, but it stops being scattered across the generic
facade.

### `typecheck.py`

After the split, this file should contain only:

- the public `typecheck_expression(...)` entrypoint wrapper;
- public re-exports needed by callers and tests;
- compatibility wrappers for generated-local-procedure and active-workflow
  session helpers;
- no family-owned logic for proofs, effects, workflow calls, let-proc, or the
  legacy stdlib bridge.

Acceptance target: the file becomes a coordinator surface and drops below the
2,000-line maintained-module cap in the selected design.

## Migration Sequence

Implement the decomposition in this order:

1. Add `typecheck_context.py` and move the passive data shapes, mutable session
   state, and error/lint helpers there while preserving the current public
   helper functions through `typecheck.py`.
2. Add `typecheck_dispatch.py` and move the recursive dispatcher there without
   changing any family logic yet.
3. Extract `typecheck_proofs.py` and update dispatch call sites to use it.
4. Extract `typecheck_effects.py` and move provider and command validation,
   macro-hidden-effect checks, and related helpers there.
5. Extract `typecheck_calls.py` and move workflow call, workflow-ref, and
   function-call typing there.
6. Move `let-proc` and local-procedure helper typing into
   `procedure_typecheck.py`.
7. Expand `phase_stdlib_typecheck.py` so all temporary review-loop bridge
   typing leaves the facade.
8. Reduce `typecheck.py` to a compatibility wrapper and update
   `orchestrator/workflow_lisp/README.md` to record the landed owner map.

At each step, keep imports stable and run the focused selectors before moving
to the next family.

## Verification

This slice is behavior-preserving. Verification must therefore prove stable
typing behavior, not just that the new files exist.

Minimum deterministic checks for the future implementation item:

```bash
python -m compileall orchestrator/workflow_lisp
pytest \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_variant_proofs.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_workflow_refs.py \
  tests/test_workflow_lisp_workflows.py \
  tests/test_workflow_lisp_structured_results.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  -q
git diff --check
```

If focused selectors fail for pre-existing unrelated reasons, the future
implementation plan must record the exact command output before continuing.

## Acceptance

This prerequisite is complete only when all of the following are true:

- exact owner-file paths are landed for context, dispatch, proofs, effects,
  calls, procedure typing, and the temporary stdlib bridge;
- `typecheck.py` remains the public compatibility surface but is no longer the
  real owner for those families;
- `typecheck.py` falls below the maintained-module line cap, or the same slice
  extracts the remaining facade-owned family before follow-on type-system work
  resumes;
- diagnostics remain stable for representative failures in command validation,
  workflow and procedure calls, variant proof, `let-proc`, stdlib
  specialization, and reusable-state typechecking;
- command-result and certified-adapter validation remain explicit and visible
  under the command-adapter contract;
- future structural-constraint and imported `.orc` plans can cite the landed
  owner-file paths instead of naming only `typecheck.py`.
