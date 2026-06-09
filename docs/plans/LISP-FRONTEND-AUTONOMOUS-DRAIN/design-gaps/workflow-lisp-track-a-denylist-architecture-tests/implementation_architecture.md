# Workflow Lisp Track A Denylist And Architecture Tests Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-track-a-denylist-architecture-tests`
Target design: `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_mvp_specification.md`

## Scope

This slice covers exactly the bounded Stage 4 Track A guardrail selected by the
current drain state:

- add one promoted-route denylist policy that can reject the legacy
  review-loop compatibility bridge without removing that bridge yet;
- add the architecture tests named by the target design:
  `test_no_review_loop_expr_in_core_ast_union`,
  `test_review_revise_loop_not_reserved_core_macro_name`,
  `test_review_revise_loop_not_elaborated_by_head_name`,
  `test_typecheck_does_not_import_review_loop_expr`,
  and `test_lowering_does_not_import_review_loop_expr`;
- add the minimum negative and legacy-opt-in fixture coverage needed to prove
  the denylist distinguishes public syntax compatibility from prohibited
  semantic special casing;
- keep the public `review-revise-loop` stdlib surface macro-bindable while
  making the promoted route fail closed until imported `.orc` expansion lands.

Out of scope for this slice:

- imported `.orc` inline expansion, imported source-map provenance, or imported
  effect visibility;
- removal of `__stdlib-specialization__`, `phase-review-loop`,
  `StdlibSpecializationExpr`, `_validate_review_loop_result_contract(...)`, or
  the current review-loop-specific lowering helpers;
- parametric `defproc`, structural constraints, loop exhaustion projection, or
  authored stdlib `review-revise-loop` replacement logic;
- runtime, shared-validation, Semantic IR, Executable IR, or command-adapter
  contract redesign;
- broad refactors of unrelated compiler passes beyond the narrow policy and
  test hooks needed to enforce this denylist.

This is a bounded implementation architecture for the denylist/test gap only.
It does not claim that the promoted review-loop route already works. The
promoted route is expected to fail closed in this slice because Stage 5 imported
`.orc` expansion has not landed yet.

## Problem Statement

The previous Track A slice established the form registry and reclassified the
public `review-revise-loop` surface as a `STDLIB_EXTENSION`. That reduced the
literal special-form surface, but it did not yet add any guard that prevents a
later slice from claiming "ordinary stdlib ownership" while still routing
through review-loop-specific compiler behavior.

The current checkout still has exactly that compatibility bridge:

1. `std/phase.orc` exports `review-revise-loop` as a macro that expands to
   `__stdlib-specialization__ phase-review-loop ...`.
2. `expressions.py` elaborates that request through
   `_elaborate_stdlib_specialization(...)` and
   `_elaborate_phase_review_loop_specialization(...)`.
3. `typecheck.py` still owns `_typecheck_stdlib_specialization_expr(...)` and
   `_validate_review_loop_result_contract(...)`.
4. `lowering/core.py` still owns review-loop-specific result-contract and
   branch-output helpers.
5. `compiler.py` still contains `_workflow_contains_review_revise_loop(...)`
   for feature detection.

Without a denylist slice, later imported-expansion or parametric work can drift
into a false-positive architecture: the public name is stdlib-owned on paper,
but the promoted compile path still depends on a review-loop-specific semantic
bridge.

This slice therefore owns the narrow guardrail between Stage 3 and Stage 5:

- add an explicit promoted-mode audit boundary;
- make that audit fail with stable frontend diagnostics when the legacy bridge
  is still used;
- keep legacy fixtures able to opt into the bridge explicitly while the generic
  imported-expansion route is still unimplemented;
- add static architecture tests so renamed special cases do not quietly reenter
  through source changes, imports, or reserved-name policy drift.

## Design Constraints

The implementation must stay coherent with:

- `docs/index.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - `10.3 Architectural Denylist Tests`
  - `10.4 Temporary Syntax Compatibility Shim`
  - `24. Incremental Implementation Plan`
  - `25. Diagnostics`
  - `26.3 Track A Architecture Fixtures`
  - `27. Acceptance Checks`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
- `docs/design/workflow_lisp_refactor_architecture.md`
- `docs/plans/2026-06-02-workflow-lisp-generic-orc-expansion-refactor.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/steering.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/2/prerequisite-selector/selection.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/2/design-gap-architect/architecture-targets.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/2/design-gap-architect/existing-architecture-index.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

The slice must also preserve these guardrails:

- keep `orchestrator/workflow_lisp/` as the frontend-owned package and keep
  shared runtime semantics under `orchestrator/workflow/`;
- reuse the staged frontend pipeline:
  read -> syntax -> macro expansion -> definitions/procedures/workflows ->
  typecheck -> lowering -> shared validation;
- reuse the existing provenance and diagnostics substrate:
  `SourcePosition`,
  `SourceSpan`,
  recursive syntax objects,
  macro expansion stacks,
  `LispFrontendDiagnostic`,
  and `LoweringOriginMap`;
- keep the denylist frontend-owned; do not turn it into a shared-validation or
  runtime policy;
- keep the work behavior-preserving for default legacy compilation:
  existing review-loop fixtures may continue to compile only when they opt into
  the compatibility bridge explicitly;
- keep structured state and typed artifacts authoritative; do not let the audit
  boundary weaken `provider-result`, `command-result`, or certified-adapter
  visibility.

`docs/design/workflow_command_adapter_contract.md` is authoritative here even
though this slice adds no new command boundary. The denylist must not become a
loophole where bridge code bypasses the same visible `command-result` or
certified-adapter semantics already required everywhere else in the frontend.

`docs/steering.md` is empty in this checkout. That is not permission to widen
scope. The selection bundle and target design remain the effective steering
surfaces.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The full index in
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/2/design-gap-architect/existing-architecture-index.md`
was reviewed for coherence. The directly reused slices for this gap are:

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-validation-diagnostics-pipeline/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/hygienic-defmacro-system/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/module-import-export-resolution/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/track-a-form-registry-elaboration-boundary/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-owner-seam-split-prerequisite/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-review-revise-preflight-hazard-fixes/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md`

### Decisions Reused

- Reuse the staged frontend pipeline and frontend/runtime package split.
- Reuse the form-registry classification and feature-tag model instead of
  adding another form inventory.
- Reuse the macro slice's rule that macro expansion is syntax-only; the public
  `review-revise-loop` head may stay ergonomic, but it must not imply compiler
  semantic ownership.
- Reuse the validation/diagnostics slice's ownership split:
  denylist failures are frontend diagnostics, not shared-validation errors.
- Reuse the owner-seam split's post-split module boundaries so the denylist can
  target explicit typecheck and lowering owners rather than monolithic facades.
- Reuse the lowering/source-map slices' rule that any generated or blocked path
  must still fail with normal provenance and source spans.

### New Decisions In This Slice

- Add one explicit compile-time policy for the review-loop compatibility bridge,
  with a legacy-allowed default and a promoted denylist mode used by focused
  architecture tests.
- Make promoted-mode failure explicit and stable:
  the bridge must fail closed with frontend diagnostics before it can reach an
  accepted semantic route.
- Keep the denylist checkout-aware:
  tests must cover the historical names listed by the target design and the
  current equivalent bridge artifacts that still exist in this checkout.
- Separate static architecture assertions from runtime-path assertions:
  source/import/name tests prevent reintroduction of old forms, while
  promoted-mode compile tests prove the current bridge cannot masquerade as the
  promoted route.

### Conflicts Or Revisions

The target design names historical artifacts such as `ReviewReviseLoopExpr` and
`_elaborate_review_revise_loop`. The current checkout has already partially
renamed that path into `StdlibSpecializationExpr`,
`_elaborate_phase_review_loop_specialization(...)`, and
`phase-review-loop`.

This slice does not revise the target design. It operationalizes the same
denylist intent against current equivalents so the tests remain meaningful in
the present checkout:

- historical names remain guarded and must stay absent;
- current renamed equivalents are treated as the live compatibility bridge that
  promoted mode must reject.

No prior slice is revised on shared concepts such as Core Workflow AST,
Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant
proof.

## Ownership Boundaries

This slice owns:

- one narrow compile-time bridge policy for `review-revise-loop` compatibility;
- bridge-deny checks in the frontend stages that can still observe the legacy
  route:
  expression elaboration,
  typechecking,
  and lowering;
- focused diagnostics for promoted-mode bridge rejection;
- the required Stage 4 architecture tests and the minimum legacy-opt-in
  fixtures that prove denylist behavior;
- checkout-aware denylist coverage for current equivalent artifacts and helper
  names.

This slice intentionally does not own:

- generic imported `.orc` expansion or imported helper specialization;
- authored replacement of `std/phase.orc` review-loop behavior;
- deletion of the compatibility bridge from `expressions.py`, `typecheck.py`,
  or `lowering/core.py`;
- parametric generics, loop exhaustion, or ProcRef specialization;
- shared validation/runtime changes or command-adapter redesign.

## Current Checkout Facts

The current checkout confirms the selected guardrail gap directly:

- `orchestrator/workflow_lisp/form_registry.py` already classifies
  `review-revise-loop` as a `STDLIB_EXTENSION` with feature tag
  `review_loop_public_surface`.
- The same registry classifies `__stdlib-specialization__` as a
  `TEMP_COMPILER_INTRINSIC` with feature tag `review_loop_compat_bridge`, and
  `_STDLIB_REQUEST_KIND_FEATURES` maps `phase-review-loop` to that same bridge
  tag.
- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` still defines:
  `(defmacro review-revise-loop ... (__stdlib-specialization__ phase-review-loop ...))`.
- `orchestrator/workflow_lisp/expressions.py` still owns
  `_elaborate_stdlib_specialization(...)` and
  `_elaborate_phase_review_loop_specialization(...)`.
- `orchestrator/workflow_lisp/typecheck.py` still owns
  `_validate_review_loop_result_contract(...)` and
  `_typecheck_stdlib_specialization_expr(...)`.
- `orchestrator/workflow_lisp/lowering/core.py` still owns
  `_review_loop_result_case_outputs(...)` and
  `_review_loop_result_output_contracts(...)`, with explicit
  `` `review-revise-loop` lowering requires a union return type `` errors.
- `orchestrator/workflow_lisp/compiler.py` still owns
  `_workflow_contains_review_revise_loop(...)`, although it now relies on
  feature tags instead of literal public-head checks.
- There are existing form-registry parity tests in
  `tests/test_workflow_lisp_macros.py`, but there are no Stage 4 denylist
  tests named by the target design yet.
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` contains no
  events, so there is no later recorded implementation state superseding this
  selected denylist obligation.

## Proposed Package Boundary

Keep the implementation narrow and local to the existing owners:

```text
orchestrator/workflow_lisp/
  compiler.py                  # optional Stage 3 entrypoint policy threading
  expressions.py               # reject bridge requests in promoted deny mode
  typecheck.py                 # fail closed if bridge reaches typed elaboration
  diagnostics.py               # register stable denylist diagnostic codes
  form_registry.py             # reused tags only; no new classification family
  stdlib_modules/std/phase.orc # unchanged compatibility macro surface

orchestrator/workflow_lisp/lowering/
  core.py                      # fail closed if bridge reaches lowering

tests/
  test_workflow_lisp_macros.py
  test_workflow_lisp_expressions.py
  test_workflow_lisp_phase_stdlib.py
  test_workflow_lisp_lowering.py
```

Do not add a new runtime module, CLI flag, or shared-validation subsystem for
this slice. If a user-facing switch becomes necessary later, it belongs to the
future promotion and migration tooling, not to this bounded Stage 4 guardrail.

## Denylist Architecture

### 1. Promoted-Mode Bridge Policy

Add one explicit, frontend-local policy surface with two modes:

- legacy-compatible:
  allow the existing `__stdlib-specialization__ phase-review-loop` bridge so
  current fixtures and parity evidence can keep running;
- promoted-denylist:
  reject any attempt to use the review-loop compatibility bridge as the
  semantic route.

Keep the default behavior legacy-compatible in this slice. The denylist mode is
for architecture tests and future promoted fixtures only. This keeps Stage 4
bounded and avoids pretending that Stage 5 imported `.orc` expansion has
already landed.

Preferred shape:

```python
review_loop_legacy_bridge_policy: Literal["allow", "deny"] = "allow"
```

Thread that policy only through the existing Stage 3 compile path and the
minimal internal helpers that need to enforce it.

### 2. Checkout-Aware Denylist Mapping

The target design's denylist names older artifacts. The tests in this slice
must map those names to the current checkout honestly.

Target design artifact -> current checkout guard target:

- `ReviewReviseLoopExpr`
  -> remains absent and must stay absent from any Core/frontend AST union.
- `_elaborate_review_revise_loop`
  -> current equivalent `_elaborate_phase_review_loop_specialization(...)`.
- `__review-revise-loop__`
  -> current equivalent `__stdlib-specialization__` with request kind
     `phase-review-loop`.
- `_lower_review_revise_loop`
  -> current equivalent review-loop-specific lowering helpers in
     `lowering/core.py`.
- typechecker branch keyed directly to `review-revise-loop`
  -> current equivalent `_typecheck_stdlib_specialization_expr(...)` plus
     `_validate_review_loop_result_contract(...)`.
- lowerer/compiler visitor logic keyed directly to `review-revise-loop`
  -> current equivalent bridge-tag detection and review-loop-specific lowering
     helper path.

This mapping is not a design change. It is the implementation-level audit table
needed to make Stage 4 meaningful in the present checkout.

### 3. Fail-Closed Enforcement Points

Use three enforcement points, ordered from earliest to latest:

1. Expression elaboration:
   if promoted denylist mode sees `__stdlib-specialization__` request kind
   `phase-review-loop`, raise `stdlib_special_form_disallowed`.
2. Typechecking:
   if a review-loop compatibility `StdlibSpecializationExpr` still reaches
   typed elaboration in promoted mode, raise the same frontend diagnostic
   rather than silently typing it.
3. Lowering:
   if a denied bridge still reaches review-loop-specific lowering helpers,
   raise `review_loop_special_lowerer_used`.

The first check is the expected path. The later checks are defense in depth so a
future refactor cannot reintroduce the bridge under a different compile entry or
manually constructed expression path.

### 4. Legacy Opt-In Behavior

Stage 4 must distinguish "syntax compatibility still exists" from "the promoted
semantic route is clean."

Required behavior:

- existing review-loop fixtures remain valid only when they compile with the
  explicit legacy-allowed policy;
- promoted-mode tests compile the same public surface and expect a stable
  denylist diagnostic until imported `.orc` expansion replaces the bridge;
- no fixture in this slice may claim that `review-revise-loop` already compiles
  through an imported `.orc` definition.

This is the smallest honest contract before Stage 5:
promoted mode rejects the bridge, legacy mode preserves it, and the difference
is deliberate and testable.

## Diagnostics And Tests

Add or reserve focused frontend diagnostics for this slice:

- `stdlib_special_form_disallowed`
- `review_loop_special_lowerer_used`

The required Stage 4 architecture tests should be implemented with the
following intent:

- `test_no_review_loop_expr_in_core_ast_union`
  proves the historical `ReviewReviseLoopExpr` route stays absent.
- `test_review_revise_loop_not_reserved_core_macro_name`
  proves the public head remains stdlib-owned and macro-bindable rather than a
  compiler-reserved core head.
- `test_review_revise_loop_not_elaborated_by_head_name`
  proves the public head is not reintroduced through direct elaborator
  dispatch.
- `test_typecheck_does_not_import_review_loop_expr`
  proves typechecking does not regain a historical review-loop AST dependency.
- `test_lowering_does_not_import_review_loop_expr`
  proves lowering does not regain that historical AST dependency.

Add two focused promoted/legacy behavior tests as the minimum execution proof
for the denylist policy:

- one test compiles an existing public `review-revise-loop` fixture in
  promoted-denylist mode and expects `stdlib_special_form_disallowed`;
- one test compiles the same fixture in explicit legacy mode and proves current
  behavior remains intact.

Keep these checks narrow. They are architecture guardrails, not parity or
runtime-evidence replacements.

## Acceptance Checks

This slice is complete when all of the following are true:

- the selected implementation architecture remains bounded to Track A denylist
  policy and architecture tests only;
- the Stage 3 compile path supports a narrow review-loop bridge policy with a
  legacy-allowed default and a promoted denylist mode for tests;
- promoted denylist mode fails closed on the current
  `__stdlib-specialization__ phase-review-loop` path with a stable frontend
  diagnostic;
- explicit legacy mode still allows the current review-loop compatibility
  bridge so existing fixtures can keep serving as bridge evidence;
- the required Stage 4 architecture tests named by the target design exist;
- the tests guard both historical names and the current equivalent bridge
  artifacts in this checkout;
- the public `review-revise-loop` head remains a stdlib extension and not a
  compiler-owned core special form or reserved core macro name;
- no imported `.orc` expansion, source-map parity, effect visibility parity, or
  review-loop bridge removal is claimed as complete by this slice.
