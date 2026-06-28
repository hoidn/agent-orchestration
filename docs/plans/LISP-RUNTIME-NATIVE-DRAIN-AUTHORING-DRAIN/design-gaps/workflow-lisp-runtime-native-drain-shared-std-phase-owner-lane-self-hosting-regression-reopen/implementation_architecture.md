# Workflow Lisp Runtime-Native Drain Shared `std/phase` Owner-Lane Self-Hosting Regression Reopen Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-runtime-native-drain-shared-std-phase-owner-lane-self-hosting-regression-reopen`
Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`
Command-adapter authority: `docs/design/workflow_command_adapter_contract.md`

## Scope

This slice covers exactly the reopened shared prerequisite named by the
selected target-design gap:

- restore the builtin `std/phase` owner lane so `ReviewDecision`,
  `ReviewFindings`, `ReviewFindingsJsonPath`, and `ReviewLoopResult` resolve
  from `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` on the
  ordinary linked WCC/schema-2 route;
- prove that `review-revise-loop`, `phase-scope`, and their helper procedures
  compile and validate as imported stdlib definitions with the same type
  environment and source-map visibility as other builtin stdlib modules;
- add regression evidence that fails closed when `std/phase` local type
  resolution, export surfaces, or builtin self-reference drift; and
- unblock the Design Delta parent-family compile/smoke lane only by repairing
  the shared `std/phase` owner lane, not by adding family aliases or copying
  review-loop types into Design Delta modules.

Out of scope:

- changing Design Delta `.orc` workflows to restate `ReviewLoopResult` or
  route around `std/phase`;
- changing `std/drain`, `std/resource`, `backlog-drain`,
  `finalize-selected-item`, selector, gap-drafter, or work-item semantics;
- redesigning `review-revise-loop` loop behavior, review/fix ProcRef
  signatures, `ReviewFindings.v1`, or loop exhaustion;
- retiring the temporary `with-phase` compatibility intrinsic;
- replacing `validate_review_findings_v1` with a runtime-native validator;
- changing provider, command, Core Workflow AST, Semantic Workflow IR,
  executable IR, source-map, pointer-authority, or variant-proof contracts;
- adding scripts, inline command glue, report parsing, pointer-state reads, or
  compatibility-bundle rereads; and
- claiming YAML-primary promotion.

This is an implementation architecture for one regression-reopen slice. It
does not replace the runtime-native drain target design or the accepted
Workflow Lisp frontend baseline.

## Problem Statement

The target design says a family may depend on imported `std/phase` helpers only
after the shared stdlib owner lane proves that `std/phase` compiles and
validates as an ordinary imported module. The reopened failure is narrower:
fresh parent-drain verification reports `type_unknown` for `ReviewLoopResult`
in `std/phase.orc`.

The current checkout already contains the intended source of truth:

- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` declares and
  exports `ReviewDecision`, `ReviewFindingsJsonPath`, `ReviewFindings`,
  `ReviewLoopResult`, `PhaseScopeTargets`, `with-phase`, `phase-scope`,
  `review-revise-loop`, and `review-revise-loop-proc`;
- `review-revise-loop-proc` uses qualified references such as
  `std/phase/ReviewLoopResult`, `std/phase/ReviewFindings`, and
  `std/phase/ReviewDecision` inside its own defining module;
- `std/phase` imports `std/context :only (PhaseCtx)`, so builtin stdlib module
  graph ordering and export-surface construction matter before validating
  local definitions;
- `tests/test_workflow_lisp_phase_stdlib.py` already contains adjacent proof
  helpers for linked builtin `std/phase` type exports, review-loop compilation,
  and `ReviewFindings` alias handling; and
- the Design Delta family consumes `std/phase` through ordinary imports in
  `workflows/library/lisp_frontend_design_delta/plan_phase.orc` and
  `implementation_phase.orc`.

The implementation problem is therefore not to create new review-loop types.
It is to make builtin stdlib self-references and exports survive the same
linked module/type-environment path that downstream modules use. A fix that
patches Design Delta imports, forks `std/phase`, copies type declarations, or
adds compiler-name special cases would satisfy the immediate family compile
but violate the selected target gap.

## Design Constraints

This slice must preserve these contracts:

- `docs/design/workflow_lisp_runtime_native_drain_authoring.md` Section 9.3
  requires `std/phase` to resolve and export its own review/fix types and
  helpers without family-local aliases, copied type declarations, or
  compiler-name special cases.
- `docs/design/workflow_lisp_runtime_native_drain_authoring.md` Section 15
  requires Design Delta to depend on imported `std/phase` only after this
  shared builtin owner lane is proved on the ordinary imported-stdlib WCC
  route.
- `docs/design/workflow_lisp_frontend_specification.md` requires imported
  stdlib definitions to lower through ordinary import expansion, typechecking,
  WCC elaboration, effect visibility, source maps, shared validation, Semantic
  IR, and executable IR.
- `docs/design/workflow_lisp_frontend_specification.md` Section 27 owns the
  first-tranche `ReviewDecision`, `ReviewFindings`, and `ReviewLoopResult`
  schema. This slice may make those definitions resolve; it must not reshape
  their semantic contract.
- `docs/design/workflow_command_adapter_contract.md` governs the retained
  `validate_review_findings_v1` command boundary. This slice may keep that
  certified structured-result adapter, but must not add hidden scripts or make
  stdout/report text semantic authority.
- `docs/workflow_lisp_g6_verification_gate.json` already counts
  `tests/test_workflow_lisp_phase_stdlib.py` as the stdlib phase owner-lane
  suite. This slice should repair and strengthen that owner-lane evidence
  rather than moving proof into downstream family tests.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

From the generated architecture index for this request:

- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-family-specific-compiler-hook-retirement/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-gap-drafter-callable-boundary-over-imported-backlog-drain/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-literal-name-stdlib-intrinsic-retirement/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-selector-stdlib-call-contract-regression-reopen/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-selector-stdlib-single-ctx-signature-alignment-regression-reopen/implementation_architecture.md`

### Decisions Reused

- Reuse the family-specific compiler-hook retirement slice's boundary rule:
  do not repair a shared prerequisite with Design Delta workflow-name checks or
  family-local compiler branches.
- Reuse the gap-drafter callable-boundary slice's owner split: shared stdlib
  prerequisites are proved in shared owner lanes before downstream Design
  Delta adoption cites them.
- Reuse the literal-name stdlib intrinsic retirement slice's rule that promoted
  stdlib behavior must arrive through imported stdlib expansion and ordinary
  typed forms, not literal-name direct lowerers.
- Reuse both selector regression slices' narrowness discipline: repair the
  stale or broken owner boundary directly and split out any broader compiler
  or family adoption issue discovered during implementation.
- Reuse the command-adapter contract's rule that retained command behavior must
  be certified and fixture-backed; do not introduce command glue to manufacture
  type resolution.

### New Decisions In This Slice

- Treat `std/phase` builtin self-hosting as a first-class linked-module
  regression surface. The owner-lane fixture must inspect the actual
  `std/phase` module from `orchestrator/workflow_lisp/stdlib_modules`, not a
  copied teaching module.
- Make the linked type-environment rebuild path authoritative for this proof:
  `compile_stage1_entrypoint` and `compile_stage3_entrypoint` must be able to
  rebuild `std/phase` with local, qualified-local, and imported type refs
  available.
- Add a negative drift fixture that fails with `type_unknown` or
  `module_export_missing` when a local `std/phase` type used by
  `review-revise-loop-proc` is removed from the module/export surface.
- Keep `validate_review_findings_v1` as the certified validator adapter for
  `ReviewFindings.v1`; its command-boundary metadata remains in
  `orchestrator/workflow_lisp/stdlib_contracts.py`.
- Require the Design Delta parent compile check only as downstream regression
  evidence after the shared `std/phase` owner-lane fixture passes.

### Conflicts Or Revisions

- The current capability matrix and verification gate classify `std/phase` as
  landed. The reopened gap does not revise that status globally; it says a
  regression has reopened in a specific owner-lane path and must be re-proved.
- Existing tests may already prove imported `ReviewFindings` aliases and simple
  `phase_stdlib_review_loop.orc` compilation. This slice strengthens them to
  cover builtin module self-reference and downstream Design Delta compile
  traversal. It does not replace those tests.
- No shared concepts such as spans, diagnostics, Core Workflow AST, Semantic
  Workflow IR, TypeCatalog, SourceMap, pointer authority, variant proof,
  resource transitions, or command adapter certification are redefined here.

## Current Checkout Facts

- `std/phase.orc` declares all target review-loop types locally and exports
  them.
- `review-revise-loop-proc` is authored in `std/phase.orc`, not in a retired
  support module. It uses `loop/recur`, `match`, `variant`, `record`,
  `command-result`, and compile-time ProcRefs.
- The retained validator command boundary is declared as
  `validate_review_findings_v1` in `orchestrator/workflow_lisp/stdlib_contracts.py`
  with `behavior_class="structured_result"`, owner `std/phase`, positive and
  negative fixtures, path-safety policy, and a typed `ReviewFindings` output.
- `orchestrator/workflow_lisp/compiler.py` owns
  `_linked_module_type_environment(...)`, `_imported_type_refs(...)`, and
  `_validate_definition_module(...)`; these are the likely implementation
  boundary for local/qualified/imported type availability during linked
  builtin module validation.
- `orchestrator/workflow_lisp/modules.py` owns `build_import_scope(...)` and
  module export-surface derivation.
- `orchestrator/workflow_lisp/type_env.py` owns type resolution and emits
  `type_unknown`.
- `tests/test_workflow_lisp_phase_stdlib.py` is the counted owner-lane suite
  and already imports `compile_stage1_entrypoint`, `compile_stage3_entrypoint`,
  `_linked_module_type_environment`, `_imported_type_refs`,
  `build_import_scope`, and `FrontendTypeEnvironment`.
- `workflows/library/lisp_frontend_design_delta/plan_phase.orc` and
  `implementation_phase.orc` import `std/phase` review-loop types and
  `review-revise-loop`; the parent drain compile is the downstream consumer,
  not the place to patch the missing type.

## Feasibility Proof

This slice is feasible without new language features because:

1. The source `std/phase.orc` already contains the accepted review-loop schema
   and helper procedure.
2. Linked module graph compilation already loads builtin stdlib modules through
   source roots and export surfaces.
3. `FrontendTypeEnvironment.from_module(...)` already accepts explicit
   imported type refs, resources, and transitions.
4. Existing stage-1 and stage-3 tests already expose helper functions that can
   rebuild the linked type environment and assert type resolution for
   `std/phase`.
5. The retained command adapter is already certified; no new adapter or
   runtime effect is needed for type resolution.

The implementation risk is ordering: builtin export surfaces and type refs may
be derived before the expanded/validated `std/phase` definition module has the
local qualified names needed by its own `defproc` annotations. The plan must
localize that fix to linked module/type-environment construction rather than
loosening type validation globally.

## Owned Components

This slice owns:

- `orchestrator/workflow_lisp/compiler.py`
  - ensure linked stage-1 and stage-3 compilation rebuilds type environments
    for builtin stdlib modules with local, qualified-local, and imported
    `std/phase` type refs available;
  - keep `_validate_definition_module(...)` strict for unknown types;
  - avoid introducing Design Delta-specific type aliases or special cases.
- `orchestrator/workflow_lisp/modules.py`
  - adjust export-surface or import-scope derivation only if current ordering
    fails to expose local `std/phase` exports to later modules or to
    type-environment rebuilds.
- `orchestrator/workflow_lisp/type_env.py`
  - adjust only if canonical qualified type names such as
    `std/phase/ReviewLoopResult` fail to resolve despite the module defining
    the local type.
- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
  - fix authored self-references only if they are inconsistent with the
    baseline type-name grammar; do not copy or rename review-loop schemas.
- `tests/test_workflow_lisp_phase_stdlib.py`
  - add or strengthen owner-lane positive and negative regression tests.
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py` and
  `tests/test_workflow_lisp_build_artifacts.py`
  - keep one downstream Design Delta compile/build regression check after the
    shared owner-lane proof is green.

This slice intentionally does not own:

- Design Delta workflow source rewrites;
- `std/drain.orc`, `std/resource.orc`, or their lowering semantics;
- `review-revise-loop` algorithm changes;
- Core Workflow AST, Semantic Workflow IR, executable IR, source-map schema,
  pointer-authority rules, or variant-proof rules;
- provider prompt rendering, typed provider request records, or boundary
  publication;
- command-boundary manifest widening beyond the existing certified
  `validate_review_findings_v1` metadata; or
- YAML-primary promotion or parity adjudication.

## Implementation Shape

The implementation should proceed in three bounded steps.

1. Reproduce and isolate the shared failure.

   Add a focused test that compiles a small entry module importing
   `std/phase` and then rebuilds the linked type environment for the actual
   builtin `std/phase` module. The assertion should resolve:

   - `ReviewDecision`
   - `ReviewFindings`
   - `ReviewFindingsJsonPath`
   - `ReviewLoopResult`
   - `PhaseScopeTargets`

   through both the `std/phase` environment and an importing module's
   `phase.<Type>` aliases.

2. Repair linked stdlib type resolution.

   The preferred fix is to make linked module type-environment construction
   consistently include:

   - local type refs;
   - module-qualified local refs such as `std/phase/ReviewLoopResult`;
   - exported imported refs from dependencies such as `std/context/PhaseCtx`;
   - canonical imported aliases used by `:only` and `:as phase`; and
   - the same exported type-ref table for builtin modules that downstream
     modules receive.

   The fix must keep `type_unknown` strict. It should not add a fallback that
   treats any unknown `std/phase/*` symbol as valid.

3. Prove owner-lane and downstream behavior.

   Strengthen the phase stdlib tests to compile `phase_stdlib_review_loop.orc`
   through stage 3 with shared validation, verify the specialized review loop
   no longer leaves `StdlibSpecializationExpr` nodes, and assert the retained
   `validate_review_findings_v1` adapter binding is present only because the
   stdlib procedure uses the certified validator.

   Then run the Design Delta parent drain compile/build checks as downstream
   evidence. If Design Delta still fails after `std/phase` self-hosting is
   fixed, split that failure into a separate family or shared prerequisite gap
   unless it is the same `std/phase` type-resolution path.

## Data And Control Flow

1. `compile_stage1_entrypoint(...)` resolves the entry module graph, including
   builtin `std/context` and `std/phase`.
2. `std/context` exports `PhaseCtx`.
3. `std/phase` imports `PhaseCtx`, declares its own review-loop types, and
   exports those types plus macros/procedures.
4. The linked compiler derives an export surface for `std/phase` from the
   actual authored module.
5. `_linked_module_type_environment(...)` rebuilds the `std/phase`
   `FrontendTypeEnvironment` with local and imported type refs.
6. Importing modules resolve `phase.ReviewLoopResult` and unqualified
   `ReviewLoopResult` according to their `import std/phase` directives.
7. Stage-3 compilation expands `review-revise-loop` through imported stdlib
   macro/procedure composition and validates the resulting WCC/Core route.
8. Design Delta `plan_phase` and `implementation_phase` compile through the
   same path without type aliases or family-local review-loop schemas.

## Diagnostics And Failure Modes

Expected fail-closed behavior:

- missing or unexported `ReviewLoopResult` in `std/phase` emits
  `module_export_missing` or `type_unknown` at the stdlib source span;
- an importing module that requests a non-exported `std/phase` type emits the
  existing import/export diagnostic;
- stale local self-reference in `std/phase.orc` emits `type_unknown` with a
  source span in the builtin module;
- a Design Delta module that omits the needed `std/phase` import still fails as
  a normal import/type error; and
- use of rendered reports, pointer files, stdout, or command output as a
  substitute for typed review-loop state remains invalid.

Diagnostics should point to the authored type annotation or import form. The
implementation must not mask type failures by silently accepting unresolved
qualified names.

## Command Adapter Policy

No new command adapter is proposed.

The existing `validate_review_findings_v1` command boundary remains in scope
only as retained certified adapter metadata consumed by `std/phase`:

- behavior class: `structured_result`;
- owner module: `std/phase`;
- typed output: `ReviewFindings`;
- typed input signature: `ReviewFindingsJsonPath` plus the bounded carrier
  data already declared in the adapter binding;
- fixtures and negative fixtures: keep the existing validator fixture ids; and
- replacement path: no runtime-native promotion in this slice.

If implementation changes this adapter invocation while repairing
`std/phase`, it must continue to satisfy
`docs/design/workflow_command_adapter_contract.md`: stable command path, typed
inputs and outputs, declared effects, path-safety rules, source maps, fixture
tests, negative tests, and stable error taxonomy. Inline Python, shell glue,
report parsing, pointer-state reads, and stdout JSON are not acceptable fixes.

## Acceptance Conditions

The slice is complete when:

- the actual builtin `std/phase.orc` resolves and exports
  `ReviewDecision`, `ReviewFindings`, `ReviewFindingsJsonPath`, and
  `ReviewLoopResult` through linked stage-1 and stage-3 compile paths;
- `review-revise-loop` and `phase-scope` compile through imported stdlib
  expansion with source-map visibility and without a family-local alias module;
- a negative owner-lane fixture fails closed when `ReviewLoopResult` or another
  required review-loop type is removed or mis-exported;
- `validate_review_findings_v1` remains a certified structured-result adapter
  rather than hidden command glue;
- the Design Delta parent drain compile reaches past the reopened
  `std/phase` type-resolution failure; and
- no Design Delta module restates stdlib review-loop types to satisfy this
  prerequisite.

## Verification Strategy

Minimum deterministic checks for the implementation slice:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_wcc_m4.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py
python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "std_phase or review_loop or ReviewLoopResult or ReviewFindings" -q
python -m pytest tests/test_workflow_lisp_wcc_m4.py -k "stdlib_review_loop" -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "design_delta_parent_drain" -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "design_delta_parent_drain" -q
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
```

If any downstream Design Delta check fails with a diagnostic unrelated to
`std/phase` owner-lane type resolution, record the new diagnostic and split it
from this architecture rather than broadening the slice.

## Implementation Handoff

The implementation plan should:

1. add or strengthen an owner-lane regression test that reproduces the
   `ReviewLoopResult` resolution failure against the actual builtin
   `std/phase` module;
2. repair linked module/type-environment construction so local qualified
   `std/phase` self-references and exported type refs are available in the
   ordinary route;
3. add the negative drift fixture;
4. rerun the counted `std/phase` owner-lane suite and WCC review-loop checks;
5. rerun Design Delta parent compile/build checks as downstream confirmation;
   and
6. leave any remaining non-`std/phase` family failure as a separate selected
   gap.
