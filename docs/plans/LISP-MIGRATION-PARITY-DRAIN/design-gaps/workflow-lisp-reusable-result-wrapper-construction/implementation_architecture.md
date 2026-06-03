# Workflow Lisp Reusable-Result Wrapper Construction Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-reusable-result-wrapper-construction`
Target design: `docs/design/workflow_lisp_key_migration_parity_architecture.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected prerequisite gap:

- add one bounded authored Workflow Lisp surface for constructing union-returning
  reusable wrapper results in ordinary `.orc` code;
- make approved-only wrapper workflows able to return an authored union that can
  feed `resume-or-start :valid-when (APPROVED)` without relying on
  compiler-generated-only `UnionVariantExpr` nodes;
- keep wrapper construction generic so it works for family-local reusable
  wrappers, thin migration adapters, and future generic specialization outputs;
- reuse the existing union lowering, proof, reusable-state, and managed
  write-root substrates instead of inventing a new runtime effect or YAML
  primitive.

Out of scope for this slice:

- entrypoint context bootstrap, runtime-owned `RunCtx` / `PhaseCtx` creation,
  or hiding run-id/root inputs on promoted entry workflows;
- generic parametric type constraints, imported-procedure polymorphism, or
  replacing the current thin specialization bridge with the future
  compile-time-parametric design;
- redesign of `resume-or-start`, reusable-state summaries, review-loop
  composition, carried findings, command-result bundle ownership, or promotion
  reporting beyond reusing their existing decisions;
- new runtime-native effects, new command adapters, report parsing, pointer
  authority exceptions, or inline Python/shell semantic glue;
- family-specific hard-coded wrapper names, compiler branches keyed to one
  workflow family, or edits to backlog state and run state.

This is a bounded implementation architecture for one selected prerequisite
gap. It does not replace the parent migration architecture or reopen the
umbrella Workflow Lisp frontend contract.

## Problem Statement

The selected target design already isolated the missing prerequisite:

- wrapper-level approved-only reuse needs a union-shaped reusable result, not
  only a record projection;
- current migration work must not depend on compiler-generated-only union
  constructors such as `UnionVariantExpr`;
- the missing capability belongs in Workflow Lisp authoring and lowering, not
  in YAML, runtime state, or adapter glue.

The current checkout still falls short in three concrete ways:

1. Workflow Lisp already has `RecordExpr` as an authored surface, but
   `UnionVariantExpr` is still documented and used as a compiler-generated-only
   node in `orchestrator/workflow_lisp/expressions.py`.
2. Typecheck and lowering already understand `UnionVariantExpr`, but the normal
   elaboration path does not expose any authored union-construction form for
   wrapper workflows.
3. Existing resume fixtures such as
   `tests/fixtures/workflow_lisp/valid/phase_stdlib_resume_or_start.orc` and
   wrapper workflows such as
   `workflows/examples/design_plan_impl_review_stack_v2_call.orc` therefore
   normalize reusable phase results into authored records after `match` rather
   than being able to author a new reusable union surface.

The gap is therefore not “invent reusable state” and not “solve promoted
entrypoint context bootstrap.” The missing piece is one ordinary Workflow Lisp
expression surface that lets authored wrappers construct declared union variants
directly so approved-only reusable wrappers become legal without compiler-only
AST synthesis.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
  - `Required Changes By Gap`
  - `Newly Exposed Prerequisite Gaps`
  - `Dependencies And Sequencing`
  - `Evidence And Implementation Boundaries`
  - `Success Criteria`
  - `Stop / Revise Criteria`
- `docs/design/workflow_lisp_frontend_specification.md`
  - Sections 7.5, 8.4, 8.5, 10, 11, 14, 16-18, 28, 44-57, 63, 74, 95, 100-104
- `docs/design/workflow_lisp_compile_time_parametric_specialization.md`
- `docs/design/workflow_lisp_structural_parametric_constraints.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/lisp_workflow_drafting_guide.md`
- `specs/dsl.md`
- `specs/state.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`
- `docs/steering.md`

The slice must preserve these guardrails:

- keep authored reusable wrappers in ordinary `.orc` code rather than adding a
  family-specific compiler intrinsic;
- keep structured bundles, declared unions, and typed artifact values as
  authority;
- keep `match` and `requires_variant` as the only proof-bearing route for
  reading variant-specific fields;
- keep runtime execution unchanged by reusing the existing `UnionVariantExpr`
  typecheck/lowering substrate rather than adding a new runtime value model;
- keep provider, prompt, procedure, and workflow refs compile-time-only;
- keep `resume-or-start` reusable-state validation on the already-selected
  certified adapter/runtime contract rather than turning wrapper construction
  into a recovery shortcut;
- do not treat the empty `docs/steering.md` file as permission to widen scope.

`docs/design/workflow_command_adapter_contract.md` remains authoritative even
though this slice should not add new adapters. Wrapper construction must not be
“solved” by hiding union routing in a command adapter or report parser.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-command-result-compiler-owned-bundle-paths/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-defworkflow-input-default-parity/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-imported-review-loop-module-path-alignment/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-migration-promotion-parity-report-gate/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-resume-or-start-reusable-state-validation/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-findings-structured-dataflow/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-loop-generic-effectful-composition/implementation_architecture.md`
- coherence reference:
  `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md`

### Decisions Reused

- Reuse the existing authored `record` constructor pattern as the closest
  author-surface precedent for typed aggregate construction.
- Reuse the existing `UnionVariantExpr` typecheck and lowering support rather
  than creating a second union-runtime path.
- Reuse the `resume-or-start` reusable-state contract, including
  `:valid-when (APPROVED)`, `ReusablePhaseState.v1`, and certified
  validator/writer bindings from the reusable-state slice.
- Reuse the public/internal compiled-workflow input split from the
  command-result and input-default slices; union wrapper construction must not
  expose new managed inputs.
- Reuse the imported-stdlib/generic-specialization ownership model from the
  review-loop generic composition slice so thin macros and generated helpers can
  emit the same ordinary union-construction surface.
- Reuse existing variant-proof semantics and diagnostics instead of inventing a
  wrapper-only proof model.

### New Decisions In This Slice

- Add one bounded authored union-variant constructor surface to Workflow Lisp
  expressions for ordinary `.orc` code.
- Keep the constructor explicit about both the union type and variant name so
  wrapper normalization remains source-mapped and reviewable.
- Make authored wrapper unions legal in ordinary workflow bodies, `match`
  branches, private-workflow helpers, and generic specialization outputs.
- Restrict the first slice to concrete declared union types; it does not add
  inferred anonymous unions or runtime type values.
- Treat this surface as the minimum generic prerequisite required before the
  family parity rerun and before entrypoint context bootstrap.

### Conflicts Or Revisions

The current checkout treats `UnionVariantExpr` as compiler-generated-only and
uses it primarily in review-loop specialization and other generated paths. This
slice revises that assumption narrowly:

- the internal node remains the lowered representation;
- what changes is that ordinary authored `.orc` forms may now elaborate into
  that node;
- no family-specific compiler branch is added and no runtime semantics are
  changed.

The selected parent migration design names compile-time parametric
specialization as the long-term direction. This slice does not revise that. It
establishes the smaller ordinary authoring surface that generic specialization
can target immediately, without waiting for full structural parametric
constraints.

No shared concepts are redefined. Core Workflow AST, Semantic IR, TypeCatalog,
SourceMap, pointer authority, variant proof, and runtime execution ownership
remain with their existing owners.

## Ownership Boundaries

This slice owns:

- authored union-constructor elaboration in
  `orchestrator/workflow_lisp/expressions.py`;
- typed validation of authored union constructors in
  `orchestrator/workflow_lisp/typecheck.py`;
- lowering/source-map coverage for authored union constructors in
  `orchestrator/workflow_lisp/lowering.py`;
- author-surface classification updates in helper modules such as
  `orchestrator/workflow_lisp/functions.py`;
- focused fixtures and tests proving reusable wrapper construction and wrapper
  use with `resume-or-start`.

This slice intentionally does not own:

- runtime command execution, reusable-state adapter behavior, or command bundle
  injection;
- entrypoint context bootstrap and runtime-owned hidden `RunCtx` / `PhaseCtx`
  creation;
- full parametric constraint syntax or imported-procedure polymorphism;
- family-specific parity rewrites beyond any focused fixture or minimal example
  needed to prove the generic wrapper surface;
- spec edits that would redefine YAML/runtime semantics.

## Current Checkout Facts

The current checkout already contains the main substrate this slice should
reuse:

- `RecordExpr` is an ordinary authored surface and already establishes the
  constructor pattern for aggregate typed values.
- `UnionVariantExpr` already exists as a typed expression node and lowering path
  in `orchestrator/workflow_lisp/expressions.py`,
  `orchestrator/workflow_lisp/typecheck.py`, and
  `orchestrator/workflow_lisp/lowering.py`.
- `resume-or-start` already supports declared union return types and
  `:valid-when (APPROVED)` in ordinary authored workflows.
- library migration modules such as
  `workflows/library/tracked_design_phase.orc`,
  `workflows/library/tracked_plan_phase.orc`, and
  `workflows/library/design_plan_impl_implementation_phase.orc` already expose
  union-returning reusable phase workflows.

The same checkout also shows the exact missing wrapper capability:

- the `UnionVariantExpr` docstring still calls it “One compiler-generated
  union-variant constructor.”
- expression elaboration exposes `record` but does not expose a corresponding
  ordinary authored union-construction form.
- review-loop specialization still synthesizes `UnionVariantExpr` nodes
  internally in `typecheck.py`, proving the compiler can lower the node but not
  that users can author it.
- reusable wrapper examples such as
  `tests/fixtures/workflow_lisp/valid/phase_stdlib_resume_or_start.orc`
  normalize union results into records like `PlanGateSurfaceResult` rather than
  being able to return a wrapper union directly.
- the selected family entry workflow
  `workflows/examples/design_plan_impl_review_stack_v2_call.orc` still uses
  explicit `match` plus record aggregation after reusable phase calls; it also
  contains fake `RunCtx` literals, but that second issue is the separately
  selected `workflow-lisp-entrypoint-context-bootstrap` gap.

This makes the slice feasible without new runtime behavior. The missing work is
to expose the already-supported union-construction node as an ordinary authored
surface and prove that authored wrappers can use it with `resume-or-start`.

## Proposed Architecture

### 1. Add One Bounded Authored Union Constructor Surface

Add one explicit expression form for constructing a declared union variant in
ordinary `.orc` code.

Recommended surface:

```lisp
(variant PlanGateReusableResult APPROVED
  :report_path approved.execution_report_path)
```

The exact spelling may vary, but the semantic contract must be:

- the authored form names the declared union type;
- the authored form names exactly one variant of that type;
- fields are provided explicitly by keyword, just like `record`;
- the form elaborates to the existing `UnionVariantExpr` node rather than a new
  runtime representation.

This keeps wrapper union construction ordinary, reviewable, and source-mapped.
It also avoids hiding wrapper routing in macros, adapter scripts, or Python AST
construction.

### 2. Reuse Existing Lowering By Elaborating To `UnionVariantExpr`

The implementation should not add a second union-construction node.

Implementation direction:

- extend expression elaboration with one union-constructor head alongside the
  existing `record` surface;
- elaborate the authored form directly to `UnionVariantExpr`;
- update comments/docstrings and helper classification so the node is no longer
  treated as compiler-generated-only;
- keep review-loop specialization and other generic helper generation free to
  emit the same node, but no longer as the only authoring route.

This is the feasibility proof for the slice: lowering already handles
`UnionVariantExpr`, so the only missing generic capability is authored access to
that node.

### 3. Typecheck The Constructor Against Ordinary Union Contracts

Typecheck should validate authored union constructors using ordinary declared
union metadata.

Required checks:

- the referenced type resolves and is a declared union;
- the named variant exists on that union;
- required variant fields are present exactly once;
- forbidden or unknown fields are rejected;
- each field expression is assignment-compatible with the declared field type;
- the whole expression has the selected union type, not a per-variant ad hoc
  type.

Diagnostics should prefer existing taxonomy where possible:

- unknown variant -> existing union/variant diagnostics;
- missing required field -> existing `variant_required_field_missing`;
- forbidden field -> existing `variant_forbidden_field_present`;
- non-union type in constructor position -> ordinary type mismatch / invalid
  constructor diagnostic.

This slice does not create new proof rules. Constructing a union value is not
proof of any later branch-specific field access outside `match`.

### 4. Make Wrapper-Level Approved-Only Reuse Ordinary

With an authored union constructor available, reusable wrappers can be written
as ordinary `.orc` workflows:

1. call or resume an inner reusable workflow;
2. `match` on its result;
3. construct a family-local or fixture-local wrapper union in each branch; and
4. expose that wrapper union as the reusable result consumed by an outer
   `resume-or-start :valid-when (APPROVED)`.

The minimum acceptance fixture should look like:

- inner workflow returns a reusable union such as `PlanGateResult`;
- wrapper workflow returns a different union such as
  `PlanGateReusableWrapperResult`;
- each branch constructs the wrapper union with the authored constructor;
- outer workflow uses `resume-or-start` over that wrapper union with
  `:valid-when (APPROVED)` and then projects it to a record or another public
  surface as needed.

This proves the exact selected prerequisite without dragging in entrypoint
context bootstrap. The fixture can keep explicit `phase_ctx` inputs and does
not need to solve runtime-owned hidden run bindings.

### 5. Keep Generic Specialization Compatible, But Out Of Scope

The parent design’s long-term direction is compile-time parametric
specialization plus structural constraints. This slice should not wait for that
full machinery.

Instead:

- thin macros and generated helpers may emit the new authored union-constructor
  surface or directly elaborate to the same `UnionVariantExpr`;
- future generic specialization can target this ordinary constructor rather than
  relying on review-loop-specific AST synthesis;
- structural parametric constraints remain follow-on work and are not required
  for this bounded prerequisite.

This keeps the slice minimal while still unblocking the family rerun.

## Proposed Code Footprint

- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/functions.py`
- `tests/fixtures/workflow_lisp/valid/phase_stdlib_resume_or_start.orc`
  or a new focused reusable-wrapper fixture
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_key_migrations.py`

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/phase_stdlib.py`
- `orchestrator/workflow_lisp/adapters/validate_reusable_phase_state.py`
- `orchestrator/workflow_lisp/adapters/write_reusable_phase_state_v1.py`
- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/workflow/executor.py`
- `workflows/examples/design_plan_impl_review_stack_v2_call.orc`
  except as a downstream consumer after this prerequisite lands

## Verification Strategy

Required checks for this slice:

1. parser/elaboration coverage for the authored union-constructor form;
2. typecheck negatives for:
   - non-union constructor targets;
   - unknown variants;
   - missing required fields;
   - forbidden fields;
   - field type mismatches;
3. lowering/source-map coverage proving authored constructors reuse the
   existing `UnionVariantExpr` path rather than a new runtime representation;
4. a focused reusable-wrapper fixture proving:
   - wrapper workflow returns an authored union;
   - outer `resume-or-start :valid-when (APPROVED)` accepts that wrapper
     result;
   - no compiler-family special casing is required;
5. regression coverage that existing review-loop specialization, reusable-state
   validation, and migrated reusable phase workflows still compile.

Acceptance is met when the repo can compile a reusable wrapper that returns an
authored union-shaped reusable result suitable for approved-only
`resume-or-start`, with no adapter workaround and no dependence on
compiler-generated-only union construction.
