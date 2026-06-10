# Workflow Lisp Imported-Child Returned-Variant Work-Item Prerequisite Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-imported-child-returned-variant-work-item-prerequisite`
Target design: `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected Tranche 2 prerequisite that now blocks
the Tranche 7 parent-callable work-item route:

- allow a parent workflow that matches an imported child union to return a
  local domain union without inheriting the child variant name as the target
  result identity;
- extend the existing returned-variant normalization route so a `match` arm may
  forward a same-target union boundary produced by a helper call, generated
  private workflow call, or imported child workflow call, instead of requiring
  one explicit target variant name at the outer arm boundary;
- keep explicit local `(variant WorkItemResult ...)` translation as the primary
  returned-variant route, and add only the bounded same-target union
  pass-through needed by the real `run-work-item` path;
- add focused lowering, feasibility, and parent-call smoke coverage for the
  real design-delta work-item path that previously blocked with
  `union_return_variant_ambiguous`.

Out of scope for this slice:

- the broader variant-scoped field/output identity gap (`F4`);
- redesign of nested structured control (`F2`);
- private executable context and hidden reusable-call binding (`F5`);
- selector typed projection (`F7`);
- certified adapter declaration ergonomics or resource-transition ownership
  (`F6` / `F10`);
- redesign of `work_item.orc` semantics beyond the minimum structure needed to
  consume the new lowering capability;
- shared Core Workflow AST, Semantic IR, Executable IR, TypeCatalog,
  SourceMap, pointer authority, variant proof, or shared validation ownership.

This is a bounded implementation architecture for one prerequisite gap. It does
not replace the umbrella frontend specification, the returned-variant slice, or
the parent-callable work-item architecture.

## Problem Statement

The target design now records one explicit prerequisite for Tranche 7:
the real parent-callable work-item route must compile when it matches imported
child unions and returns local `WorkItemResult` variants. The blocked route is
not the earlier explicit `(variant TargetUnion VARIANT ...)` case already
covered by the returned-variant slice. It is the mixed branch shape in the real
work-item module.

Current checkout evidence shows the missing seam precisely:

1. `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
   now names this exact prerequisite under Tranche 2 and Tranche 7. If the
   imported-child route still fails with `union_return_variant_ambiguous`,
   Tranche 7 remains blocked.
2. The blocked work-item record at
   `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/7/design-gap-work-item/blocked-implementation-recovery.json`
   points to `workflows/library/lisp_frontend_design_delta/work_item.orc:246`
   as the concrete failure site.
3. In `work_item.orc`, the `APPROVED` arm of `(match plan ...)` returns
   `WorkItemResult` through a mixture of:
   - explicit local `variant WorkItemResult ...` constructors; and
   - a helper call `(route-blocked-implementation ...) -> WorkItemResult`.
4. The existing returned-variant architecture already solved explicit target
   constructors, but `orchestrator/workflow_lisp/lowering/workflow_calls.py`
   and `orchestrator/workflow_lisp/lowering/procedures.py` still emit call
   terminals with flattened `return__*` refs and no lowering-time evidence that
   those refs already constitute a valid same-target union boundary.
5. `orchestrator/workflow_lisp/lowering/control_match.py` still resolves union
   match-arm output by:
   - explicit returned variant evidence; or
   - same-subject-union fallback when source and target unions are the same.
   Otherwise it raises `union_return_variant_ambiguous`.

That logic is too narrow for the real work-item shape:

```text
match imported child plan result:
  APPROVED ->
    if blocked
      call helper returning WorkItemResult
    else
      explicit WorkItemResult variants
  BLOCKED ->
    explicit WorkItemResult variant
  EXHAUSTED ->
    explicit WorkItemResult variant
```

The missing capability is therefore not "guess the target variant from the
source case name." It is one bounded branch-output handoff:

```text
typed branch terminal
-> explicit target variant OR same-target union boundary pass-through
-> match-arm output projection for WorkItemResult
-> existing shared validation/runtime bundle path
```

## Design Constraints

The implementation must stay coherent with:

- `docs/index.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  - `13. Tranche 2: Union Result Normalization And Variant-Scoped Output Identity`
  - `13.2 Union-to-union normalization rule`
  - `13.4 Tasks`
  - `13.5 Acceptance`
  - `18. Tranche 7: Work-Item And Parent Backlog-Drain Composition`
  - `22. Dependencies And Sequencing`
  - `27.3 Union and variant-output tests`
  - `27.8 Parent/backlog-drain tests`
  - `28.2 Union-to-union translation`
  - `29. Success Criteria`
- `docs/design/workflow_lisp_frontend_specification.md`
  - Sections `7.5`, `8.5`, `10-14`, `44-57`, `59-63`, `72`, `74`, and `95`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/reports/2026-06-09-design-delta-drain-orc-migration-frontend-runtime-findings.md`
- `docs/plans/LISP-FRONTEND-DESIGN-DELTA-DRAIN-ORC-MIGRATION/parent_drain_readiness_blockers.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/7/design-gap-work-item/blocked-implementation-recovery.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/9/prerequisite-selector/selection.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/9/design-gap-architect/architecture-targets.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/9/design-gap-architect/existing-architecture-index.md`

The slice must also preserve these guardrails:

- keep the fix frontend-owned under `orchestrator/workflow_lisp/`;
- keep shared validation and runtime semantics under `orchestrator/workflow/`;
- keep `docs/design/workflow_command_adapter_contract.md` authoritative for the
  script-backed work-item helpers already present in this route; this slice must
  not "fix" the gap by hiding meaning in new adapter glue;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- keep imported child workflows and helper procedures on ordinary typed call
  boundaries, not a compiler-special work-item branch;
- keep the baseline frontend design as a compatibility constraint rather than
  reopening workflow-call, union, or source-map ownership.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The full architecture index was reviewed. The directly reused slices are:

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-returned-variant-union-normalization/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-parent-callable-work-item-composition/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-nested-structured-control-composition/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-lowering-core-family-decomposition/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-typecheck-family-decomposition/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`

### Decisions Reused

- Reuse the returned-variant slice's decision that explicit target-union
  constructors remain the preferred authority for cross-union translation.
- Reuse the current call-boundary flattening contract: union-typed call results
  already lower to `return__variant` plus flattened `return__*` output refs.
- Reuse the existing lowering-family split:
  `workflow_calls.py` and `procedures.py` own call terminals,
  `control_match.py` owns branch normalization,
  and `context.py` owns `_TerminalResult`.
- Reuse the parent-callable work-item slice's ownership boundary:
  this prerequisite unblocks that slice but does not redefine the work-item
  family architecture.
- Reuse the source-map and diagnostic substrate already established by prior
  slices. No new provenance system is introduced here.

### New Decisions In This Slice

- Add one new lowering-time concept beside explicit returned-variant evidence:
  `same-target union boundary pass-through`.
- Allow a `match` arm to project an existing union-typed terminal directly when
  that terminal already exposes the full boundary contract for the declared
  target union.
- Treat helper calls, generated private workflow calls, and imported child
  workflow calls the same way if their terminal boundary already matches the
  target union.
- Keep `union_return_variant_ambiguous` only for branches whose terminal is
  still opaque from the outer match arm's perspective.

### Conflicts Or Revisions

The earlier returned-variant slice implicitly assumed that a union-returning
`match` case always needed one resolved target variant name before case outputs
could be normalized. This slice revises that assumption narrowly:

- explicit target variant resolution still applies when the branch result is an
  explicit constructor;
- same-target union branch terminals may now be forwarded without resolving one
  outer-arm variant name in advance;
- the matched source-case variant remains proof context for reading child
  fields, not the authority for the target union identity.

No shared concept is redefined. Core Workflow AST, Semantic IR, Executable IR,
TypeCatalog, SourceMap, pointer authority, and variant proof stay with their
existing owners.

## Ownership Boundaries

This slice owns:

- the lowering-time metadata needed to mark a terminal as a same-target union
  boundary pass-through;
- the call-lowering updates that emit that metadata for workflow and generated
  procedure calls returning union boundary outputs;
- the `control_match.py` branch-normalization path that consumes that metadata
  and projects case outputs directly;
- focused diagnostics for incompatible or still-opaque union branch terminals;
- the real imported-child work-item feasibility and smoke fixtures that prove
  Tranche 7 can resume once this prerequisite lands.

This slice intentionally does not own:

- explicit returned-variant constructor handling already covered by the prior
  returned-variant slice;
- variant-scoped field identity;
- the work-item module's broader resource-transition or recovery semantics;
- shared-validation uniqueness rules;
- runtime execution semantics for call boundaries or union bundles;
- command-adapter policy or new runtime-native effects.

## Current Checkout Facts And Feasibility Proof

### Current Checkout Facts

- `_TerminalResult` in
  `orchestrator/workflow_lisp/lowering/context.py` already carries
  `returned_union_type_name` and `returned_union_variant_name`, but no
  first-class marker that a terminal already represents a valid union boundary
  for pass-through.
- `orchestrator/workflow_lisp/lowering/workflow_calls.py` and
  `orchestrator/workflow_lisp/lowering/procedures.py` already emit flattened
  union output refs for call results:
  `return__variant` and the union boundary leaf outputs are present.
- `orchestrator/workflow_lisp/lowering/control_match.py` already contains the
  owned diagnostics `union_return_variant_ambiguous` and
  `union_return_variant_incompatible`.
- `workflows/library/lisp_frontend_design_delta/work_item.orc` contains the
  exact blocked shape in the `APPROVED` arm beginning at line 246:
  imported child plan match, helper call returning `WorkItemResult`, and local
  explicit `WorkItemResult` constructors in sibling subpaths.
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
  already contains the checked-in parent-callable candidate modules under
  `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/` and the
  verification-only parent wrapper
  `tests/fixtures/workflow_lisp/valid/design_delta_parent_calls_work_item.orc`.
  For this slice those checked-in `.orc` sources are the authoritative
  parent-callable proof surface until the shipping library module grows its own
  exported `run-work-item` surface.

### Feasibility Proof

This slice satisfies the design-spec feasibility trigger with a bounded,
checkout-backed route:

- no runtime change is required because the relevant call terminals already
  export the full flattened union boundary;
- the missing capability is only that `control_match.py` does not recognize
  those existing outputs as a valid case-output source when the target union is
  the same as the terminal union;
- workflow-call and generated-procedure-call lowering already share the same
  `_TerminalResult` seam, so one metadata addition covers both imported child
  workflows and helper-generated private workflows;
- the command-backed work-item helpers remain explicit typed boundaries, so the
  command-adapter contract is preserved rather than bypassed.

## Proposed Package Boundary

Frontend-owned implementation surface:

```text
orchestrator/workflow_lisp/
  lowering/
    context.py
    control_match.py
    procedures.py
    workflow_calls.py
  diagnostics.py           # only if diagnostic copy needs tightening
```

Focused verification surface:

```text
tests/
  test_workflow_lisp_lowering.py
  test_workflow_lisp_design_delta_drain_migration_feasibility.py
  test_workflow_lisp_build_artifacts.py
```

This slice does not require shared-runtime edits under `orchestrator/workflow/`.

## Proposed Architecture

### 1. Add Same-Target Union Boundary Evidence

Extend `_TerminalResult` with one bounded branch-output capability:

- `exact returned variant` remains the existing explicit-constructor path;
- `same-target union boundary pass-through` is new and means:
  - the terminal is already typed as union `T`;
  - `output_refs` contain the flattened workflow-boundary leaves for `T`,
    including `return__variant`; and
  - the outer lowering step may reuse those refs directly instead of
    synthesizing a new fixed-variant bundle.

This should be modeled as explicit lowering metadata, not inferred again from
string heuristics at the last minute.

### 2. Populate Pass-Through Evidence At Call Boundaries

Update workflow-call and generated-procedure-call lowering so that when the
typed call result is a union boundary type, the emitted `_TerminalResult`
records:

- the target union type name; and
- that the terminal is eligible for same-target boundary pass-through.

This is intentionally narrower than callee-body variant inference. The call
site does not need to know which union variant the callee will return. It only
needs to know that the call terminal already satisfies the declared target
union boundary contract and may therefore be forwarded as that union.

### 3. Add A Pass-Through Branch Path In `control_match.py`

When lowering a `match` arm whose declared result type is union `TargetUnion`,
choose output handling in this order:

1. If the branch terminal carries explicit returned-variant evidence for
   `TargetUnion.VARIANT`, use the existing fixed-variant normalization path.
2. If the branch terminal carries same-target boundary pass-through evidence for
   `TargetUnion`, project the terminal's existing `return__*` refs directly to
   the match-case outputs and do not synthesize a new fixed-variant case bundle.
3. If the matched subject union and the target union are the same union, keep
   the existing same-subject fallback for compatibility where it already works.
4. Otherwise emit the existing owned ambiguity or incompatibility diagnostic.

The key revision is step 2. The outer match arm no longer needs to invent a
single target variant name when the branch already produced a target-union
terminal.

### 4. Imported-Child Work-Item Route

The real acceptance route should compile by applying the new pass-through path
to the approved-plan branch in `run-work-item`:

- the outer `match` still branches on imported child `DesignDeltaPlanPhaseResult`;
- explicit local `WorkItemResult` constructors stay on the direct
  `TERMINAL_BLOCKED` and `COMPLETED` paths;
- the helper call `(route-blocked-implementation ...) -> WorkItemResult` now
  contributes a same-target union boundary pass-through terminal instead of an
  opaque call result;
- the branch case outputs therefore remain valid even though the helper may
  return one of several `WorkItemResult` variants.

This unblocks the real work-item route without forcing outer domain unions to
mirror child control-state names and without splitting the route back into leaf
workflows.

### 5. Diagnostic Rules

Preserve the current frontend-owned error family, but tighten the trigger
boundaries:

- `union_return_variant_incompatible`
  - explicit returned-variant evidence names the wrong union or a non-member
    variant; or
  - same-target pass-through evidence exists, but its union type does not match
    the declared target union.
- `union_return_variant_ambiguous`
  - the branch terminal is a dynamic or opaque value with no explicit target
    variant and no same-target boundary pass-through;
  - cross-union helper or child call returns a different union and the branch
    does not remap it explicitly.

The diagnostic should name:

- the target union;
- the matched source variant;
- whether the branch terminal was explicit, pass-through, or opaque; and
- the call/helper source span when the opaque terminal came from a call.

### 6. Source Maps And Provenance

No new provenance system is needed. Reuse the existing lowering origin and
generated output span machinery so that:

- the outer match case retains the authored source span of the branch;
- pass-through outputs still point back to the helper or child call that
  produced the forwarded `return__*` refs;
- command-boundary lineage for the work-item helpers remains visible in build
  artifacts and diagnostics.

## Testing And Acceptance

### Focused Lowering Coverage

Add or update lowering tests for:

- explicit cross-union translation still using explicit returned variants;
- a `match` arm that forwards a same-target union call terminal while sibling
  subpaths return explicit local variants;
- incompatible pass-through where the call terminal union does not match the
  declared target union;
- still-opaque dynamic call terminal that correctly raises
  `union_return_variant_ambiguous`.

### Real Workflow-Family Coverage

Use the designated checked-in design-delta candidate sources as the canonical
proof for this slice:

- `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/work_item.orc`
- `tests/fixtures/workflow_lisp/valid/design_delta_parent_calls_work_item.orc`

This designation is intentional: the current shipping library module at
`workflows/library/lisp_frontend_design_delta/work_item.orc` remains the
closure-only guard surface for the separate parent-callable work-item
composition tranche. Until that later tranche lands, this imported-child
prerequisite must classify downstream blockers from the checked-in candidate
source above rather than pretending the closure-only library module is already
the parent-callable route.

The canonical tests remain:

- `test_design_delta_work_item_candidate_compiles_as_parent_callable_workflow`
- `test_design_delta_work_item_candidate_smokes_complete_and_blocked_recovery_routes`
- `test_design_delta_parent_call_work_item_smokes_complete_and_blocked_recovery_routes`
- `test_design_delta_migration_cross_union_result_translation_compiles`

These tests prove the prerequisite on the designated parent-callable candidate
route, not on ad hoc inline modules or a delegated child-only smoke helper.

### Acceptance Conditions

- the approved-plan branch in `run-work-item` no longer fails with
  `union_return_variant_ambiguous` merely because one subpath returns a helper
  call already typed as `WorkItemResult`;
- explicit local `variant WorkItemResult ...` paths remain unchanged;
- parent-call smoke still returns `COMPLETED`, `TERMINAL_BLOCKED`, and
  `BLOCKED_RECOVERY` through typed `WorkItemResult` outputs;
- no shared-runtime or shared-validation change is required;
- no new helper script or inline semantic glue is introduced.

## Implementation Notes

- Prefer a dedicated pass-through marker on `_TerminalResult` over inferring the
  mode indirectly from `return__variant` output-ref names. The mode is a
  semantic lowering decision, not a string-pattern heuristic.
- Keep this slice limited to union branch-output transport. Do not widen into
  work-item public-boundary changes, adapter redesign, or parent-drain
  semantics.
- If the real work-item route still needs one small authored refactor after the
  lowering change, it must stay bounded to exposing the new generic capability,
  not to papering over it with variant renaming or leaf splitting.
