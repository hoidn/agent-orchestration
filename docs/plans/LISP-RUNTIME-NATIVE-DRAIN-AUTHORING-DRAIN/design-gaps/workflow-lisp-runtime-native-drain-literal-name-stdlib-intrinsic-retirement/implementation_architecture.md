# Workflow Lisp Runtime-Native Drain Literal-Name Stdlib Intrinsic Retirement Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-runtime-native-drain-literal-name-stdlib-intrinsic-retirement`
Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected target-design gap:

- retire promoted-route compiler intrinsic and literal-name handling for
  `backlog-drain` and `finalize-selected-item`;
- make promoted `.orc` compilation reach those forms only through ordinary
  imported `std/drain` and `std/resource` stdlib expansion, procedure calls,
  typechecking, WCC lowering, shared validation, source maps, and effect
  visibility;
- quarantine any remaining bare-form compatibility fixtures behind explicit
  legacy/schema-1 routing; and
- tighten deletion evidence so the Design Delta parent family cannot claim the
  target while promoted-route registry or direct-lowering hooks still admit
  those literal heads.

Out of scope:

- redesigning `std/drain::backlog-drain` loop semantics;
- redesigning `std/resource::finalize-selected-item`;
- changing `resource-transition`, `materialize-view`, loop, match, ProcRef,
  macro hygiene, source-map, Core Workflow AST, Semantic IR, or executable IR
  contracts;
- changing Design Delta provider request records, boundary publication,
  bridge metadata, or gap re-entry convergence;
- adding command adapters, scripts, report parsing, pointer files, or
  compatibility-bundle rereads; and
- claiming YAML-primary promotion.

This is an implementation architecture for one retirement gap, not a
replacement product design or a broad runtime-native drain spec.

## Problem Statement

The current checkout already has ordinary imported stdlib proof lanes for
`finalize-selected-item` and `backlog-drain`. `std/resource.orc` exports
`finalize-selected-item` as a macro over `finalize-selected-item-proc`, and
`std/drain.orc` exports `backlog-drain` as a macro over typed loop,
workflow-call, match, transition, and materialized-view composition. Counted
fixtures also prove that the imported stdlib route can compile without
incrementing intrinsic-lowering counters.

The remaining gap is that promoted compiler surfaces still expose active
literal-head compatibility machinery:

- `orchestrator/workflow_lisp/form_registry.py` still registers
  `finalize-selected-item` and `backlog-drain` as
  `FormKind.TEMP_COMPILER_INTRINSIC` with `compatibility_route_only`;
- `orchestrator/workflow_lisp/expressions.py` still elaborates those literal
  heads into dedicated `FinalizeSelectedItemExpr` and `BacklogDrainExpr`
  values when macro expansion did not replace them;
- `orchestrator/workflow_lisp/lowering/control_dispatch.py` still dispatches
  those expression classes through direct lowerers and records intrinsic
  lowering hits; and
- `orchestrator/workflow_lisp/lowering/phase_stdlib.py` still forwards those
  direct lowerers while comments describe them as callable until a later G8
  cleanup.

That state conflicts with the target design's completion rule: promoted
Workflow Lisp routes must not branch on literal compiler names such as
`std/drain`, `backlog-drain`, `finalize-selected-item`, or `phase_drain`.
The implementation problem is therefore not to invent a new stdlib route. It
is to remove promoted-route admission and direct lowering for the two literal
stdlib heads now that the imported stdlib route is the authority.

## Design Constraints

This slice must preserve these contracts:

- `docs/design/workflow_lisp_runtime_native_drain_authoring.md` Sections 12.1,
  12.2, and 15 require `backlog-drain` and `finalize-selected-item` behavior
  to be owned by `std/*` or family `.orc` modules through ordinary imported
  composition, not compiler-name branches.
- `docs/design/workflow_lisp_frontend_specification.md` requires imported
  bindings to be the primary stdlib route, with promoted evidence compiling
  through imported stdlib definitions rather than silently elaborating through
  literal-name branches.
- `docs/design/workflow_command_adapter_contract.md` requires semantic
  workflow behavior to stay in typed procedures, typed calls, certified
  adapters, or runtime-native effects. This slice must not replace compiler
  intrinsics with scripts or opaque command glue.
- `docs/capability_status_matrix.md` already treats G6 stdlib
  phase/resource/drain bridge surfaces as landed on imported owner lanes. This
  slice should consume that evidence and remove the remaining compatibility
  hooks, not reopen the G6 semantics.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-gap-drafter-callable-boundary-over-imported-backlog-drain/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-selector-stdlib-single-ctx-signature-alignment-regression-reopen/implementation_architecture.md`

### Decisions Reused

- Reuse the gap-drafter callable-boundary slice's owner split: imported
  `backlog-drain` owns the child loop boundary and typed workflow-ref calls;
  parent/family adoption must not smuggle payloads through compatibility
  wrappers.
- Reuse the selector signature-alignment slice's rule that fixed stdlib
  workflow-ref boundaries are preserved by typed calls, not widened arity,
  public path threading, or command glue.
- Reuse both slices' separation between shared stdlib proof lanes and
  downstream Design Delta family adoption. This slice retires only the
  remaining literal-head compiler compatibility surfaces.
- Reuse the command-adapter contract's decision that hidden semantic routing
  must move to typed stdlib composition or runtime-native effects, not scripts.

### New Decisions In This Slice

- Treat `finalize-selected-item` and `backlog-drain` as no longer valid
  promoted-route `TEMP_COMPILER_INTRINSIC` heads.
- Keep imported stdlib macro/procedure expansion as the only promoted route for
  those author-facing names.
- Preserve bare literal-head fixtures only if they are explicitly marked and
  routed as legacy/schema-1 characterization. They must not share the promoted
  form registry or WCC-default expression elaboration path.
- Strengthen Design Delta G8 deletion evidence so a compatibility-tagged
  promoted registry row is not enough to count as removed.

### Conflicts Or Revisions

- The capability matrix says the imported stdlib bridge route is landed; the
  selected gap says literal-name intrinsics still remain. Both can be true:
  landed stdlib proof exists, while stale compatibility hooks still need
  retirement.
- Existing tests that intentionally compile bare intrinsic fixtures under
  `lowering_route="legacy"` remain valid characterization only. If they
  currently rely on the same promoted registry and expression classes, the
  implementation must move them behind a legacy-only admission path or replace
  them with explicit failure tests for the promoted route.
- No shared concepts such as spans, diagnostics, Core Workflow AST, Semantic
  Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant proof are
  redefined here.

## Current Checkout Facts

- `orchestrator/workflow_lisp/form_registry.py` registers both
  `finalize-selected-item` and `backlog-drain` as
  `TEMP_COMPILER_INTRINSIC`, `macro_bindable=True`,
  `compatibility_route_only`, and with direct elaboration routes.
- `orchestrator/workflow_lisp/expressions.py` contains
  `_elaborate_finalize_selected_item(...)` and `_elaborate_backlog_drain(...)`
  that construct dedicated expression classes.
- `orchestrator/workflow_lisp/lowering/control_dispatch.py` imports those
  expression classes, dispatches them to direct lowerers, and increments
  intrinsic-form lowering counters.
- `orchestrator/workflow_lisp/lowering/phase_stdlib.py` still documents the
  direct lowerers as G6 callable compatibility lanes pending G8.
- `orchestrator/workflow_lisp/stdlib_modules/std/resource.orc` already owns
  `finalize-selected-item` through an imported macro that calls
  `finalize-selected-item-proc`.
- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc` already owns
  `backlog-drain` through an imported macro that expands to ordinary typed
  loop/call/match/projection/transition composition.
- `tests/test_workflow_lisp_stdlib_form_migration.py` already asserts imported
  stdlib fixtures compile without intrinsic-lowering counts, while legacy
  intrinsic fixtures still exercise compatibility accounting.
- `orchestrator/workflow_lisp/build.py` already emits G8 deletion evidence
  listing `with-phase`, `finalize-selected-item`, and `backlog-drain` as
  removed registry heads, but the current guard skips specs tagged
  `compatibility_route_only`. This leaves room for promoted registry entries
  to survive while deletion evidence still passes.

## Feasibility Proof

This slice is feasible without a new language feature because the replacement
route already exists:

1. Imported stdlib macro expansion already compiles the paired stdlib fixtures
   for `finalize-selected-item` and `backlog-drain`.
2. Dedicated runtime-proof and build-artifact tests already assert that
   imported `backlog-drain` can avoid intrinsic lowering on the promoted route.
3. `std/resource` and `std/drain` already contain the typed procedures,
   transitions, materialized views, loop state, and terminal projection needed
   by the promoted route.
4. The remaining direct lowerers are isolated enough to be guarded, moved to a
   legacy-only route, or deleted after bare intrinsic fixtures are converted to
   explicit legacy characterization.

The unproven part is not semantic expressiveness; it is the cleanup mechanics:
legacy-only admission must not leak back into the promoted registry,
expression elaborator, lowering dispatch, or deletion evidence.

## Ownership Boundaries

This slice owns:

- `orchestrator/workflow_lisp/form_registry.py`
  - remove `finalize-selected-item` and `backlog-drain` from the promoted
    compiler-known intrinsic registry, or move their metadata to a legacy-only
    registry that `get_form_spec(...)` does not expose to promoted
    elaboration;
  - ensure a promoted bare occurrence fails as missing imported stdlib
    expansion or unknown form, rather than direct lowering.
- `orchestrator/workflow_lisp/expressions.py`
  - remove promoted elaboration for the two literal heads, or guard it behind
    an explicit legacy-only path;
  - keep imported macro expansion behavior unchanged.
- `orchestrator/workflow_lisp/lowering/control_dispatch.py`,
  `orchestrator/workflow_lisp/lowering/phase_stdlib.py`,
  `orchestrator/workflow_lisp/lowering/phase_resource.py`, and
  `orchestrator/workflow_lisp/lowering/phase_drain.py`
  - remove promoted dispatch for `FinalizeSelectedItemExpr` and
    `BacklogDrainExpr`, or require an explicit legacy/schema-1 route before
    those lowerers can run;
  - preserve generic lowerers used by stdlib-expanded ordinary forms.
- `tests/test_workflow_lisp_stdlib_form_migration.py`,
  `tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py`,
  `tests/test_workflow_lisp_build_artifacts.py`, and relevant fixture files
  under `tests/fixtures/workflow_lisp/valid/` and
  `tests/fixtures/workflow_lisp/invalid/`.
- `orchestrator/workflow_lisp/build.py` and
  `orchestrator/workflow_lisp/migration_parity.py` only for deletion-evidence
  guard tightening if the implementation changes how removed registry heads
  are represented.

This slice intentionally does not own:

- authored semantics in `std/resource.orc` or `std/drain.orc`, except for
  import/export metadata needed to keep the current macro route callable;
- Design Delta production workflow rewrites;
- command-boundary manifests or adapter certification;
- resource-transition backend semantics;
- public/private context classification beyond preserving existing evidence;
- source-map, Core Workflow AST, Semantic IR, or executable IR contracts; or
- YAML-primary promotion.

## Proposed Component Architecture

### 1. Split Promoted Registry From Legacy Characterization

The promoted `get_form_spec(...)` registry must no longer return
`TEMP_COMPILER_INTRINSIC` specs for `finalize-selected-item` or
`backlog-drain`.

Preferred implementation:

- delete both specs from `_FORM_SPECS`;
- rely on imported stdlib macro bindings for valid promoted authoring; and
- update reserved-macro and admitted-head behavior accordingly.

Acceptable compatibility implementation:

- move both specs to an explicit legacy/schema-1 registry accessed only by
  legacy fixture compilation; and
- make the promoted registry return `None` for both heads.

Do not convert these heads to promoted `STDLIB_EXTENSION` entries unless the
G8 deletion-evidence contract is deliberately revised to treat
`STDLIB_EXTENSION` as "imported-only but not removed." The selected target
uses "removed registry heads" evidence, so the cleaner route is absence from
the promoted registry.

### 2. Remove Promoted Literal-Head Elaboration

After registry cleanup, promoted expression elaboration must not construct
`FinalizeSelectedItemExpr` or `BacklogDrainExpr` from source literal heads.

Implementation direction:

- remove or legacy-guard `_elaborate_finalize_selected_item(...)` and
  `_elaborate_backlog_drain(...)`;
- remove their dispatch routes from `_dispatch_elaboration_route(...)` if those
  routes are no longer reachable in promoted mode;
- add promoted negative fixtures proving bare `(finalize-selected-item ...)`
  and `(backlog-drain ...)` fail unless the imported stdlib macro expansion has
  already rewritten them; and
- keep imported macro expansion from `std/resource` and `std/drain` as the
  valid route for authored uses.

### 3. Quarantine Or Delete Direct Lowerers

Direct lowering for `FinalizeSelectedItemExpr` and `BacklogDrainExpr` must be
unreachable on WCC-default/promoted routes.

Implementation direction:

- remove the direct `isinstance(...)` branches from
  `control_dispatch._control_lower_expression_impl(...)`, or make them fail
  unless the lowering context is explicitly legacy/schema-1;
- remove promoted wrappers in `phase_stdlib.py` for those forms;
- keep `phase_resource.py` and `phase_drain.py` only as legacy compatibility
  modules if bare intrinsic fixtures are still retained; and
- keep the intrinsic-form lowering counter only for explicit legacy
  characterization, not as a normal promoted-route safety signal.

If deleting the direct lowerers is too large for one implementation slice, the
first implementation may add a fail-closed promoted-route guard and leave
legacy-only code in place. The acceptance condition remains that promoted
compiles cannot reach those lowerers.

### 4. Tighten Deletion Evidence

The G8 deletion-evidence lane should fail if a removed head is still present
in the promoted registry, even when tagged `compatibility_route_only`.

Implementation direction:

- update `_serialize_design_delta_g8_deletion_evidence(...)` so
  `DESIGN_DELTA_G8_REMOVED_REGISTRY_HEADS` means absent from the promoted
  registry;
- preserve the separate `imported_only_registry_heads` lane only for heads
  deliberately kept as imported-only registry entries, currently `with-phase`;
- keep parity validation requiring `removed_registry_heads` to include
  `finalize-selected-item` and `backlog-drain`; and
- add a negative test that monkeypatches either head back into the promoted
  registry and confirms deletion evidence fails.

### 5. Keep Stdlib Proof Lanes As The Positive Evidence

Positive evidence for this slice should cite the existing imported stdlib
fixtures and strengthen them where needed:

- imported `resource_stdlib_finalize_selected_item_stdlib.orc` compiles with no
  intrinsic lowering;
- imported `drain_stdlib_backlog_drain_stdlib.orc` compiles with no intrinsic
  lowering;
- dedicated runtime proof for imported `std/drain::backlog-drain` still builds
  a validated executable bundle; and
- Design Delta parent-family build/parity artifacts still record deleted
  registry heads and do not depend on the bare literal-head compatibility path.

## Verification Strategy

Minimum deterministic checks:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_stdlib_form_migration.py tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_migration_parity.py
python -m pytest tests/test_workflow_lisp_stdlib_form_migration.py -q
python -m pytest tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py::test_dedicated_runtime_proof_profile_builds_validated_entry_bundle_for_imported_stdlib_drain -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "g8_deletion_evidence or removed_registry_heads" -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "design_delta_parent_drain" -q
python -m pytest tests/test_workflow_lisp_migration_parity.py -k "g8_deletion_evidence or design_delta_parent_drain" -q
```

Expected evidence:

- imported stdlib fixtures still compile through the WCC/default route;
- promoted imported routes record no `finalize-selected-item` or
  `backlog-drain` intrinsic lowering hits;
- bare intrinsic fixtures either move to explicit legacy characterization or
  become promoted negative fixtures;
- G8 deletion evidence fails if either removed head remains in the promoted
  registry; and
- no new command-boundary row, script, report parser, pointer state, or
  compatibility-bundle reread is required.

## Acceptance Conditions

This slice is complete when:

- `finalize-selected-item` and `backlog-drain` are absent from the promoted
  compiler intrinsic registry;
- promoted expression elaboration cannot construct dedicated expression
  classes from those literal heads;
- promoted WCC/default lowering cannot dispatch to the direct
  `phase_resource` or `phase_drain` compatibility lowerers for those heads;
- imported stdlib macro/procedure routes for both forms continue to compile
  and validate;
- any remaining bare-form tests are labeled and routed as legacy
  characterization, not promoted evidence;
- Design Delta G8 deletion evidence treats the two registry heads as actually
  removed rather than merely compatibility-tagged; and
- downstream Design Delta parent-family compile/parity checks still consume
  typed stdlib/family composition rather than compiler-name branches.

## Implementation Handoff

The later implementation plan should:

1. add promoted negative tests for bare `finalize-selected-item` and
   `backlog-drain` literal heads;
2. tighten G8 deletion-evidence tests so compatibility-tagged registry specs
   fail for removed heads;
3. remove or legacy-quarantine the two promoted registry specs;
4. remove or legacy-guard expression elaboration and direct lowering dispatch
   for `FinalizeSelectedItemExpr` and `BacklogDrainExpr`;
5. rerun imported stdlib positive fixtures and dedicated runtime proof lanes;
6. rerun Design Delta build/parity selectors that consume G8 deletion
   evidence; and
7. stop before changing stdlib semantics, Design Delta source shape, command
   adapter manifests, or YAML-primary promotion gates.
