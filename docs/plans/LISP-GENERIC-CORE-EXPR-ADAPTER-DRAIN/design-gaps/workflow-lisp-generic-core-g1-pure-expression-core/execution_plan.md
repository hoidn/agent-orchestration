# Workflow Lisp Generic Core G1 Pure Expression Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Project rule override: do not create a worktree.

**Goal:** Deliver Tranche G1 by adding the closed pure-expression operator surface, WCC/schema-2 pure-op lowering, the shared runtime evaluator, and visible `pure_projection` runtime steps with resume-safe private bundle transport, without retiring any adapters yet.

**Architecture:** Keep one semantics owner for pure computation: `orchestrator/workflow/pure_expr.py` defines the operator catalog, payload schema, and evaluator, and both compile-time folding and runtime projection execution call into it. Frontend work stays inside the existing expression/typecheck/WCC pipeline, then defunctionalization folds maximal pure regions into a new generated `pure_projection` step family that threads through Core AST, Semantic IR, Executable IR, runtime planning, state layout, and executor resume reuse without widening the authored YAML surface.

**Tech Stack:** Python dataclasses and JSON serialization, Workflow Lisp frontend and WCC schema 2, shared `orchestrator.workflow` validation/runtime surfaces, `.orc` fixtures under `tests/fixtures/workflow_lisp/`, pytest, and `python -m orchestrator compile|run`.

---

## Governing Context

Read before editing:

- `docs/index.md`
- `docs/work_definition_model.md`
- `docs/plans/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/work_instructions.md`
- `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/plans/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/design-gaps/workflow-lisp-generic-core-g1-pure-expression-core/implementation_architecture.md`
- `state/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/drain/iterations/0/design-gap-architect/work_item_context.md`
- `state/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/progress_ledger.json`

Current-state facts to preserve:

- `progress_ledger.json` is still empty. Treat this as the first implementation pass for the selected gap; do not infer prior partial work from the ledger.
- G0 is already drafted and provides the operator-justification evidence lane. G1 must cite that evidence but must not edit census semantics or flip any adapter to retired.
- `orchestrator/workflow_lisp/conditionals.py` currently accepts only literal/ref Bool conditions and emits `if_condition_not_projectable` for anything computed. G1 changes that rule only for pure `Bool` expressions.
- `orchestrator/workflow/state_layout.py` has generated roles for command/provider/variant bundles but no `pure_projection_bundle`.
- `orchestrator/workflow/loaded_bundle.py` currently treats only existing generated roles as managed runtime inputs; the new bundle role must be wired there too.
- `orchestrator/workflow_lisp/lowering/generated_paths.py` currently classifies managed generated result-bundle inputs through `allocation_reason(...)`, and only command/provider/variant bundles plus generated internal bindings flow through that seam today.
- This slice adds no authored DSL/YAML surface. `pure_projection` is compiler-generated only.

Non-negotiable constraints:

- WCC/schema 2 is the only lowering route touched here. Do not extend legacy schema-1 or per-form direct lowerers.
- Runtime evaluator semantics are authoritative. Compile-time folding must call the same evaluator implementation, not a shadow copy.
- The operator set is exactly the target design Section 10.2 table.
- Pure expressions remain effect-free, deterministic, and fail-closed on 64-bit overflow.
- Computed `if` conditions must not widen proof availability. `match` remains the only union-discrimination mechanism.
- Do not retire adapters, delete ontology tables, or change backlog/ledger workflow mechanics in this slice.

## File Map

Create:

- `orchestrator/workflow/pure_expr.py`: closed operator catalog, payload schema, evaluator, canonical result helpers, and typed evaluator errors.
- `orchestrator/workflow_lisp/typecheck_pure_ops.py`: catalog-driven pure-op typechecking helpers shared by dispatch.
- `tests/test_workflow_pure_expr.py`: focused runtime-evaluator and payload-schema tests.
- `tests/test_workflow_lisp_pure_projection_runtime.py`: compile/run/resume integration coverage for generated projection steps.
- `tests/fixtures/workflow_lisp/pure_expr/golden_vectors.json`: runtime/folding agreement vectors and expected failure codes.
- `tests/fixtures/workflow_lisp/valid/pure_expr_loop_counter.orc`: end-to-end loop counter fixture using `+`, comparison, and computed `if`.
- `tests/fixtures/workflow_lisp/valid/pure_expr_selector_action_projection.orc`: selector-action-style pure projection fixture using equality, boolean composition, option defaulting, and record/union construction without a command adapter.
- `tests/fixtures/workflow_lisp/invalid/pure_expr_union_equality.orc`
- `tests/fixtures/workflow_lisp/invalid/pure_expr_float_equality.orc`
- `tests/fixtures/workflow_lisp/invalid/pure_expr_path_string_concat.orc`
- `tests/fixtures/workflow_lisp/invalid/pure_expr_optional_access_unproved.orc`
- `tests/fixtures/workflow_lisp/invalid/pure_expr_operator_unsupported.orc`
- `tests/fixtures/workflow_lisp/invalid/pure_expr_computed_if_variant_ref_unproved.orc`
- `tests/fixtures/workflow_lisp/invalid/pure_expr_payload_too_large.orc` or an equivalent test-only fixture emitted from a helper if inline generation is cleaner.
- `workflows/examples/inputs/workflow_lisp_migrations/pure_expr_operator_justification.json`

Modify:

- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/form_registry.py`
- `orchestrator/workflow_lisp/typecheck_dispatch.py`
- `orchestrator/workflow_lisp/typecheck_effects.py`
- `orchestrator/workflow_lisp/conditionals.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/wcc/model.py`
- `orchestrator/workflow_lisp/wcc/elaborate.py`
- `orchestrator/workflow_lisp/wcc/anf.py`
- `orchestrator/workflow_lisp/wcc/analysis.py`
- `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- `orchestrator/workflow_lisp/lowering/core.py`: extend reviewed statement-family vocabulary so build/smoke assertions can see `pure_projection`.
- `orchestrator/workflow_lisp/lowering/generated_paths.py`: extend the shared lowering-side managed-write-root classification seam for `pure_projection` bundles.
- `orchestrator/workflow/state_layout.py`
- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/workflow/core_ast.py`
- `orchestrator/workflow/semantic_ir.py`
- `orchestrator/workflow/executable_ir.py`
- `orchestrator/workflow/runtime_plan.py`
- `orchestrator/workflow/runtime_step.py`
- `orchestrator/workflow/executor.py`
- `tests/test_workflow_lisp_expressions.py`
- `tests/test_workflow_lisp_diagnostics.py`
- `tests/test_workflow_lisp_wcc_m4.py`
- `tests/test_workflow_core_ast.py`
- `tests/test_workflow_semantic_ir.py`
- `tests/test_runtime_step_lifecycle.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_core_stmt_taxonomy.md`
- `docs/design/workflow_lisp_semantic_workflow_ir.md`
- `docs/design/workflow_lisp_executable_ir.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_effect_graph.md`
- `docs/capability_status_matrix.md`
- `docs/index.md`

Avoid touching:

- `specs/dsl.md`
- adapter manifests under `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json`
- G2+ transition/materialized-view/runtime-core surfaces
- backlog state, queue files, or ledger mutation logic

## Required Contracts To Encode

### 1. Pure Operator Surface

Implement exactly these operators:

- Equality: `=`, `!=` over `String`, `Int`, `Bool`, `Symbol`, and same-type enums.
- Ordering: `<`, `<=`, `>`, `>=` over `Int x Int` and `Float x Float`.
- Boolean: `and`, `or`, `not`.
- Arithmetic: `+`, `-`, `*`, `min`, `max` over `Int` with fail-closed 64-bit overflow.
- String: `string/concat`, `string/empty?`, `symbol/name`.
- Option: `some?`, `or-else`.
- Record: `record-update`.

Deliberate exclusions to preserve in tests and diagnostics:

- no division/modulo;
- no float equality;
- no path string concatenation;
- no deep record or union equality;
- no collection operators;
- no regex, clock, IO, randomness, workflow calls, or command/provider execution.

### 2. Payload And Runtime Contract

`pure_projection` payloads must carry:

- `pure_expr_schema_version: 1`
- declared result type
- closed expression tree
- resolved named inputs and typed ref bindings

Runtime rules:

- schema mismatch fails closed;
- payload node-count bound defaults to 256 nodes and raises `pure_expr_payload_too_large`;
- evaluation failures surface typed codes, including `pure_expr_overflow`;
- committed bundles are deterministic canonical JSON so resume reuse can compare digest plus schema version.

### 3. Diagnostics Vocabulary

Add and register:

- `pure_expr_operator_unsupported`
- `pure_expr_operand_type_mismatch`
- `pure_expr_union_equality_forbidden`
- `pure_expr_float_equality_forbidden`
- `pure_expr_path_string_concat_forbidden`
- `pure_expr_optional_access_unproved`
- `pure_expr_payload_too_large`
- `pure_expr_overflow`

Preserve `record_field_unknown` for unknown `record-update` fields instead of inventing a new duplicate code.

## Task 1: Lock The Runtime Evaluator Contract First

**Files:**

- Create: `tests/test_workflow_pure_expr.py`
- Create: `tests/fixtures/workflow_lisp/pure_expr/golden_vectors.json`
- Create: `orchestrator/workflow/pure_expr.py`

- [ ] Add failing tests in `tests/test_workflow_pure_expr.py` for:
  - every Section 10.2 operator group;
  - 64-bit overflow on `+`, `-`, and `*`;
  - `record-update` field replacement ordering;
  - `or-else` and `some?` over optional values;
  - schema-version rejection;
  - payload-size rejection;
  - canonical deterministic JSON serialization for equal results.

- [ ] Populate `golden_vectors.json` with one row per operator plus boundary/error rows. Include at least one nested multi-operator tree so later folding-agreement tests can reuse the same vectors unchanged.

- [ ] Implement `orchestrator/workflow/pure_expr.py` with:
  - `PURE_EXPR_SCHEMA_VERSION = 1`;
  - frozen operator catalog rows;
  - typed evaluator error class carrying code and optional source/payload metadata;
  - payload validation and deterministic evaluator entrypoints reused by runtime and compiler.

- [ ] Keep this module runtime-owned and dependency-light. It must not import `orchestrator.workflow_lisp`.

- [ ] Run:

```bash
python -m pytest --collect-only tests/test_workflow_pure_expr.py -q
python -m pytest tests/test_workflow_pure_expr.py -q
```

Expected: collection succeeds; the new evaluator suite passes before any frontend/WCC wiring lands.

## Task 2: Add The Frontend Surface And Typed Diagnostics

**Files:**

- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/form_registry.py`
- Create: `orchestrator/workflow_lisp/typecheck_pure_ops.py`
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py`
- Modify: `orchestrator/workflow_lisp/typecheck_effects.py`
- Modify: `orchestrator/workflow_lisp/conditionals.py`
- Modify: `orchestrator/workflow_lisp/diagnostics.py`
- Modify: `tests/test_workflow_lisp_expressions.py`
- Modify: `tests/test_workflow_lisp_diagnostics.py`
- Create: `tests/fixtures/workflow_lisp/invalid/pure_expr_union_equality.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/pure_expr_float_equality.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/pure_expr_path_string_concat.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/pure_expr_optional_access_unproved.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/pure_expr_operator_unsupported.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/pure_expr_computed_if_variant_ref_unproved.orc`

- [ ] Add failing expression tests that elaborate authored forms into `PureOpExpr` and `RecordUpdateExpr`, including nested operands and `record-update` field/value pairs.

- [ ] Register every pure-op head in `form_registry.py` as a compiler-known family so unknown pure operators fail with `pure_expr_operator_unsupported` instead of generic name lookup noise.

- [ ] Add failing diagnostic coverage for the closed-surface and proof-boundary safety rules:
  - `pure_expr_operator_unsupported.orc` must attempt a non-catalog pure-op head and assert the typed `pure_expr_operator_unsupported` diagnostic instead of generic name-resolution failure.
  - `pure_expr_computed_if_variant_ref_unproved.orc` must use a computed pure `Bool` `if` condition and then attempt variant-specific field access without `match`, asserting that the existing proof gate still fails with the variant-proof diagnostic rather than silently widening proof availability.

- [ ] Implement `typecheck_pure_ops.py` and route it from `typecheck_dispatch.py`.
  Required behaviors:
  - strict catalog-table typing;
  - no implicit coercion;
  - `Float` ordering allowed, `Float` equality forbidden;
  - optional values require `some?` or `or-else`;
  - `record-update` preserves base record type and reuses `record_field_unknown`.

- [ ] Mark pure ops as effect-free in `typecheck_effects.py`.

- [ ] Change `conditionals.py` so computed pure `Bool` expressions are classifiable while impure or non-`Bool` conditions still fail. Preserve the proof boundary: a computed comparison does not create variant proof context.

- [ ] Register the new diagnostic codes and pass-phase ownership in `diagnostics.py`.

- [ ] Update existing `if` diagnostic coverage so the old `if_condition_not_projectable` expectation only survives where the condition is still unsupported for non-pure reasons. Do not leave stale tests asserting that all computed conditions are illegal.

- [ ] Run:

```bash
python -m pytest tests/test_workflow_lisp_expressions.py -k "pure_op or record_update or computed_if" -q
python -m pytest tests/test_workflow_lisp_diagnostics.py -k "pure_expr or if_condition or variant_ref_unproved" -q
```

Expected: pure-op elaboration/typecheck tests pass; negative fixtures fail with the new typed diagnostics; unsupported pure operators stay pinned to `pure_expr_operator_unsupported`; computed pure `if` conditions stay proof-neutral and still reject variant-specific field access outside `match`.

## Task 3: Add WCC Pure Ops, ANF Atomization, And Folding Decisions

**Files:**

- Modify: `orchestrator/workflow_lisp/wcc/model.py`
- Modify: `orchestrator/workflow_lisp/wcc/elaborate.py`
- Modify: `orchestrator/workflow_lisp/wcc/anf.py`
- Modify: `orchestrator/workflow_lisp/wcc/analysis.py`
- Modify: `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- Modify: `tests/test_workflow_lisp_wcc_m4.py`

- [ ] Add failing WCC tests for:
  - `WccPureOp` construction and identity metadata;
  - nested pure expressions atomized under ANF;
  - effect analysis treating `WccPureOp` as effect-free;
  - constant-folded literal-only trees using the shared evaluator;
  - runtime-leaf pure regions lowering toward one visible projection producer rather than many micro-steps.

- [ ] Implement `WccPureOp` as an operation-layer node, not a control-flow node.

- [ ] In `defunctionalize.py`, separate two behaviors:
  - all-literal subtrees fold directly to literals via `evaluate_pure_expr`;
  - maximal runtime-visible pure regions fold into a single generated projection payload per binding group.

- [ ] Enforce the payload node-count bound during lowering and raise `pure_expr_payload_too_large` before runtime.

- [ ] Make source-map ownership mandatory for each emitted projection step. Treat missing authored-span lineage as a compile-time error.

- [ ] Run:

```bash
python -m pytest tests/test_workflow_lisp_wcc_m4.py -k "pure_op or pure_projection or computed_bool_if" -q
```

Expected: WCC/schema-2 tests pass without touching legacy routes.

## Task 4: Thread `pure_projection` Through Shared Workflow Surfaces

**Files:**

- Modify: `orchestrator/workflow/state_layout.py`
- Modify: `orchestrator/workflow/loaded_bundle.py`
- Modify: `orchestrator/workflow/core_ast.py`
- Modify: `orchestrator/workflow/semantic_ir.py`
- Modify: `orchestrator/workflow/executable_ir.py`
- Modify: `orchestrator/workflow/runtime_plan.py`
- Modify: `orchestrator/workflow/runtime_step.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow_lisp/lowering/core.py`
- Modify: `orchestrator/workflow_lisp/lowering/generated_paths.py`
- Modify: `tests/test_workflow_core_ast.py`
- Modify: `tests/test_workflow_semantic_ir.py`
- Modify: `tests/test_runtime_step_lifecycle.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] Add failing shared-surface tests for a new generated statement family:
  - Core AST serialization/deserialization retains payload, contract, allocation, and source-map metadata.
  - Semantic IR records a visible projection effect plus payload digest/schema version.
  - Executable IR and runtime plan expose a distinct executable node kind for projection execution.
  - `runtime_step.py` renders the new node kind in mapping views.
  - `loaded_bundle.py` recognizes the generated-input allocation role when enumerating managed write-root inputs.
  - `allocation_reason(...)` in `orchestrator/workflow_lisp/lowering/generated_paths.py` classifies `PURE_PROJECTION_BUNDLE` through the same managed-write-root bridge used by the existing generated result-bundle roles.

- [ ] Add `GeneratedPathSemanticRole.PURE_PROJECTION_BUNDLE` with privacy `PRIVATE_GENERATED`, the correct resume scope propagation, and matching lowering-side managed-write-root classification so generated projection bundles remain hidden runtime-owned transport instead of surfacing as ordinary authored inputs.

- [ ] Implement executor behavior:
  - resolve input refs;
  - call `evaluate_pure_expr`;
  - validate result against the declared contract;
  - atomically commit the private result bundle;
  - reuse committed bundles on resume only when schema version and payload digest match.

- [ ] Extend build-artifact and lowered-family helpers so repo-level artifact tests can see `pure_projection` explicitly instead of treating it as an unknown statement.

- [ ] Run:

```bash
python -m pytest tests/test_workflow_core_ast.py -k "pure_projection" -q
python -m pytest tests/test_workflow_semantic_ir.py -k "pure_projection" -q
python -m pytest tests/test_runtime_step_lifecycle.py -k "pure_projection" -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "pure_projection or pure_expr or generated_path" -q
```

Expected: shared workflow surfaces and runtime views recognize the new generated step family, and the lowering/runtime managed-write-root path classifies `PURE_PROJECTION_BUNDLE` exactly like the existing generated result-bundle roles.

## Task 5: Add End-To-End Compile, Dry-Run, And Resume Coverage

**Files:**

- Create: `tests/test_workflow_lisp_pure_projection_runtime.py`
- Create: `tests/fixtures/workflow_lisp/valid/pure_expr_loop_counter.orc`
- Create: `tests/fixtures/workflow_lisp/valid/pure_expr_selector_action_projection.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/pure_expr_payload_too_large.orc` or helper-generated equivalent
- Modify: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] Add a focused integration test module that compiles and executes the new fixtures through the real Stage 3 / executor path.

- [ ] `pure_expr_loop_counter.orc` must prove:
  - loop state can increment with `+`;
  - loop comparison uses the pure evaluator;
  - computed `if` lowers and executes through `pure_projection`;
  - no command adapter is needed.

- [ ] `pure_expr_selector_action_projection.orc` must prove:
  - equality, boolean composition, `or-else`, and `record-update` can express a selector-action-style pure projection;
  - the projection appears as a visible generated runtime step with source-map lineage;
  - this is fixture-only proof, not a family flip.

- [ ] Add runtime tests for:
  - successful bundle reuse on resume;
  - fail-closed behavior when the committed bundle schema version is changed;
  - compile-time payload-bound rejection for oversized pure regions.

- [ ] Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_pure_projection_runtime.py -q
python -m pytest tests/test_workflow_lisp_pure_projection_runtime.py -q
python -m orchestrator compile tests/fixtures/workflow_lisp/valid/pure_expr_selector_action_projection.orc --entry-workflow orchestrate --emit-semantic-ir .orchestrate/tmp/pure_expr_smoke/semantic_ir.json --emit-source-map .orchestrate/tmp/pure_expr_smoke/source_map.json
python -m orchestrator run tests/fixtures/workflow_lisp/valid/pure_expr_loop_counter.orc --entry-workflow run-counter --dry-run
```

Expected: the focused integration suite passes; the CLI compile/run smoke proves the generated step survives the public orchestration surface.

## Task 6: Lock The Operator-Justification Registry

**Files:**

- Create: `workflows/examples/inputs/workflow_lisp_migrations/pure_expr_operator_justification.json`
- Modify: `tests/test_workflow_pure_expr.py` or `tests/test_workflow_lisp_build_artifacts.py`

- [ ] Add a validating test that compares the runtime catalog to the justification registry and fails in both directions:
  - implemented operator missing a registry row;
  - registry row naming an unimplemented operator.

- [ ] Each row must cite either a G0 census row id or a named fixture path. Keep the registry census-driven; do not allow “future operator” placeholders.

- [ ] Reuse this registry in test assertions only. Do not turn it into runtime execution authority.

- [ ] Run:

```bash
python -m pytest tests/test_workflow_pure_expr.py -k "justification" -q
```

Expected: any future surface growth without design evidence becomes an immediate test failure.

## Task 7: Land The Normative And Discoverability Doc Deltas

**Files:**

- Modify: `docs/design/workflow_lisp_frontend_specification.md`
- Modify: `docs/design/workflow_lisp_core_stmt_taxonomy.md`
- Modify: `docs/design/workflow_lisp_semantic_workflow_ir.md`
- Modify: `docs/design/workflow_lisp_executable_ir.md`
- Modify: `docs/design/workflow_lisp_state_layout.md`
- Modify: `docs/design/workflow_lisp_effect_graph.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/index.md`

- [ ] Update the frontend specification to add the Section 10.2 operator table, computed pure `Bool` `if`, and the explicit “`match` still owns variant proof” rule.

- [ ] Update internal component docs only where this slice changes the current checkout contract:
  - `pure_projection` as a generated statement family;
  - projection effect visibility in Semantic IR/effect graph;
  - executable/runtime-plan ownership of the new node kind;
  - `pure_projection_bundle` in state-layout docs.

- [ ] Update `docs/capability_status_matrix.md` and `docs/index.md` so the new surface is discoverable and not mistaken for future-only work.

- [ ] Keep status-independent wording: document accepted contracts and evidence requirements, not transient blocker status.

- [ ] Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "pure_projection or source_map or generated_path" -q
```

Expected: doc-linked artifact assertions still match the emitted current-checkout surfaces.

## Final Verification

- [ ] Run the focused implementation suites in order, keeping selectors narrow first:

```bash
python -m pytest tests/test_workflow_pure_expr.py -q
python -m pytest tests/test_workflow_lisp_expressions.py -k "pure_op or record_update or computed_if" -q
python -m pytest tests/test_workflow_lisp_diagnostics.py -k "pure_expr or if_condition" -q
python -m pytest tests/test_workflow_lisp_wcc_m4.py -k "pure_op or pure_projection or computed_bool_if" -q
python -m pytest tests/test_workflow_core_ast.py -k "pure_projection" -q
python -m pytest tests/test_workflow_semantic_ir.py -k "pure_projection" -q
python -m pytest tests/test_runtime_step_lifecycle.py -k "pure_projection" -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "pure_projection or pure_expr or generated_path" -q
python -m pytest tests/test_workflow_lisp_pure_projection_runtime.py -q
```

- [ ] If any new test module names changed during implementation, rerun `pytest --collect-only` for those modules before claiming completion.

- [ ] Run the required public-surface smoke checks:

```bash
python -m orchestrator compile tests/fixtures/workflow_lisp/valid/pure_expr_selector_action_projection.orc --entry-workflow orchestrate --emit-semantic-ir .orchestrate/tmp/pure_expr_smoke/semantic_ir.json --emit-source-map .orchestrate/tmp/pure_expr_smoke/source_map.json
python -m orchestrator run tests/fixtures/workflow_lisp/valid/pure_expr_loop_counter.orc --entry-workflow run-counter --dry-run
```

- [ ] Record in the execution report:
  - the exact pytest selectors run;
  - whether resume reuse and schema-mismatch cases both passed;
  - whether the unsupported-operator and computed-`if` proof-boundary negative fixtures both passed with the intended diagnostics;
  - the compile/run smoke commands and emitted artifact paths;
  - the operator-justification registry path and validation result;
  - the docs updated for the normative delta.

## Acceptance Checklist

This work item is complete only when all of the following are true:

- all Section 10.2 operators are implemented and typechecked exactly as designed;
- compile-time folding and runtime evaluation share one implementation and agree on the golden vectors;
- `pure_projection` is visible across Core AST, Semantic IR, Executable IR, runtime plan, build artifacts, and runtime step views;
- `PURE_PROJECTION_BUNDLE` allocations are private, source-mapped, resume-safe, and classified through the existing lowering-side managed-write-root bridge;
- computed pure `Bool` `if` works without widening union proof;
- unsupported pure operators fail with `pure_expr_operator_unsupported`, and computed pure `if` still cannot unlock variant-specific fields outside `match`;
- loop-counter and selector-action-style fixtures compile and execute without command adapters;
- resume reuses committed projection bundles and fails closed on schema mismatch;
- the operator-justification registry covers exactly the implemented operator set;
- the frontend specification and relevant internal component docs are updated; and
- no adapter retirement, transition substrate, materialized view, or authored DSL surface change leaked into this G1 slice.
