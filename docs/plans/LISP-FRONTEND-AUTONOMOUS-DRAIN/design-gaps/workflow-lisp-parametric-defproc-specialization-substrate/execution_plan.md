# Workflow Lisp Parametric Defproc Specialization Substrate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to execute this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement compile-time generic `defproc` specialization on the current owner-seam-split checkout: parse `:forall` and metadata-only `:where`, resolve compile-time `TypeParamRef`s, infer concrete call-site type bindings, materialize deterministic monomorphic specializations before lowering, and fail closed if parametric surfaces leak past compilation.

**Architecture:** Use the already-landed owner seams instead of reopening the old monoliths. `procedures.py` owns authored generic header metadata, `type_env.py` owns compile-time type-parameter resolution and substitution, `procedure_typecheck.py` and `procedure_specialization.py` own inference and specialization planning, `compiler.py` owns orchestration before lowering, and `lowering/procedures.py` owns the final runtime-erasure boundary. `:where` clauses must first pass header-surface validation for clause shape and declared type-parameter subjects, then remain metadata-only and fail closed with a dedicated semantic-use diagnostic until the structural-constraints slice lands; this plan does not implement structural constraint semantics or generic `defworkflow`.

**Tech Stack:** Python 3, pytest, Workflow Lisp frontend modules under `orchestrator/workflow_lisp/`, authoring docs under `docs/`, and stage-3 compile/validation helpers already used by the existing Workflow Lisp test suite.

---

## Fixed Inputs

Treat these as authority before editing:

- `docs/index.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
- `docs/design/workflow_lisp_compile_time_parametric_specialization.md`
- `docs/design/workflow_lisp_structural_parametric_constraints.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-parametric-defproc-specialization-substrate/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/3/recovered-gap/recovered-work-item-context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

Current-checkout routing note:

- The recovered iteration-3 bundle is the scope authority for this plan.
- The older blocked progress report and the previous gate-only execution plan are stale duplicates for current checkout state. The owner-seam prerequisite has already landed, so implementation should proceed on the current seams instead of routing back to the old handoff path.

## Current Checkout Baseline

Use these facts to avoid rediscovering scope:

- `orchestrator/workflow_lisp/procedure_typecheck.py`, `orchestrator/workflow_lisp/procedure_specialization.py`, and `orchestrator/workflow_lisp/lowering/procedures.py` already exist and are the correct owner seams for this slice.
- The old `parametric_procedures.py` placeholder named in the earlier architecture draft should not be introduced now. Extend `procedure_specialization.py` instead so specialization ownership stays in the landed seam.
- Public facades are still large, but the relevant ownership split is already in place:
  - `typecheck.py`: `5924` lines
  - `compiler.py`: `3087` lines
  - `lowering/__init__.py`: package facade
  - `procedure_typecheck.py`: `353` lines
  - `procedure_specialization.py`: `1059` lines
  - `lowering/procedures.py`: `663` lines
- There is still no implementation of `:forall`, parsed `:where`, `TypeParamRef`, generic specialization identity, or parametric-call inference in the frontend code or tests.
- The checkout is already dirty before this slice starts:
  - `git status --short -- tests/test_workflow_lisp_modules.py` currently reports ` M tests/test_workflow_lisp_modules.py`.
  - `git diff -- tests/test_workflow_lisp_modules.py` currently shows a pre-existing whitespace-only hunk near `_compiler_module()` and `test_compile_stage1_entrypoint_exposes_review_loop_macro_from_builtin_stdlib(...)`.
  - Treat that hunk as pre-existing unless the user says otherwise. Do not rely on intermediate commits that would require staging this file wholesale.
- Baseline verification already passes in this checkout:
  - `python -m compileall orchestrator/workflow_lisp`
  - `python -m pytest --collect-only tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_source_map.py tests/test_workflow_semantic_ir.py tests/test_workflow_lisp_examples.py -q`
  - expected current result: `215 tests collected`
  - `python -m pytest tests/test_workflow_lisp_procedures.py::test_compiler_owner_split_stops_importing_procedure_specialization_from_lowering tests/test_workflow_lisp_lowering.py::test_runtime_erasure_rejects_compile_time_only_proc_ref_values tests/test_workflow_lisp_examples.py::test_review_revise_parametric_design_docs_example_validates_with_prompt_bindings -q`
  - expected current result: `3 passed`
  - `git diff --check`

## Files And Responsibilities

- Modify: `orchestrator/workflow_lisp/procedures.py`
  - Add generic `defproc` header metadata and clause-order validation.
- Modify: `orchestrator/workflow_lisp/type_env.py`
  - Add `TypeParamRef`, local type-parameter overlay lookup, recursive substitution, and leak detection helpers.
- Modify: `orchestrator/workflow_lisp/procedure_specialization.py`
  - Own parametric inference helpers, specialization keys, generated-name derivation, cache/reuse, and materialization helpers on the current seam.
- Modify: `orchestrator/workflow_lisp/procedure_typecheck.py`
  - Detect generic call targets, infer bindings from actual arguments, and emit specialization requests or diagnostics.
- Modify: `orchestrator/workflow_lisp/compiler.py`
  - Materialize generic specializations before lowering and compose them with existing ProcRef/workflow-ref specialization flow.
- Modify: `orchestrator/workflow_lisp/lowering/procedures.py`
  - Reject any leaked parametric type refs before runtime-visible lowering.
- Modify if needed: `orchestrator/workflow_lisp/__init__.py`
  - Re-export `TypeParamRef` if the package surface already exports other resolved type refs used by tests.
- Modify: `tests/test_workflow_lisp_procedures.py`
  - Parser, signature, inference, specialization, ambiguity, unresolved-binding, and compatibility regression coverage.
- Modify: `tests/test_workflow_lisp_modules.py`
  - Imported-module proof for generic procedure specialization.
- Modify: `tests/test_workflow_lisp_lowering.py`
  - Lowering and runtime-erasure coverage for generic specialization.
- Modify: `tests/test_workflow_lisp_source_map.py`
  - Provenance/source-map assertions for generated parametric specializations.
- Modify: `tests/test_workflow_semantic_ir.py`
  - Integration proof that compile-time type parameters are erased before semantic/executable artifacts.
- Modify: `tests/test_workflow_lisp_examples.py`
  - Compile-to-validated-bundle proof from a real workflow body that calls a generic procedure.
- Modify: `docs/lisp_workflow_drafting_guide.md`
  - Document the implemented generic `defproc` surface and the deliberate non-support of semantic `:where` constraints in this slice.

Prefer test-local temporary modules written with existing `_write_module(...)` helpers over adding many new fixture files. Add a durable fixture file only if an imported-module or example test becomes too noisy to maintain inline.

### Task 0: Reconfirm The Open Gate And Lock The Write Scope

**Files:**
- Verify only: `orchestrator/workflow_lisp/typecheck.py`
- Verify only: `orchestrator/workflow_lisp/compiler.py`
- Verify only: `orchestrator/workflow_lisp/lowering/__init__.py`
- Verify only: `orchestrator/workflow_lisp/procedure_typecheck.py`
- Verify only: `orchestrator/workflow_lisp/procedure_specialization.py`
- Verify only: `orchestrator/workflow_lisp/lowering/procedures.py`
- Verify only: `tests/test_workflow_lisp_modules.py`

- [ ] **Step 1: Reconfirm the owner seams that this plan is allowed to extend**

Run:

```bash
wc -l \
  orchestrator/workflow_lisp/typecheck.py \
  orchestrator/workflow_lisp/compiler.py \
  orchestrator/workflow_lisp/lowering/__init__.py \
  orchestrator/workflow_lisp/procedure_typecheck.py \
  orchestrator/workflow_lisp/procedure_specialization.py \
  orchestrator/workflow_lisp/lowering/procedures.py
```

Expected: the three split owner modules are present and remain the write targets
for this slice.

- [ ] **Step 2: Reconfirm the dirty-checkout boundary before touching Task 5 files**

Run:

```bash
git status --short -- tests/test_workflow_lisp_modules.py
git diff -- tests/test_workflow_lisp_modules.py
```

Expected: the file still contains only the pre-existing whitespace-only hunk
noted above. If that file has accumulated additional unrelated edits by the
time implementation starts, stop and ask for direction before touching Task 5.

- [ ] **Step 3: Reconfirm the plan's baseline test surface**

Run:

```bash
python -m compileall orchestrator/workflow_lisp
python -m pytest --collect-only \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_modules.py \
  tests/test_workflow_lisp_source_map.py \
  tests/test_workflow_semantic_ir.py \
  tests/test_workflow_lisp_examples.py \
  -q
python -m pytest \
  tests/test_workflow_lisp_procedures.py::test_compiler_owner_split_stops_importing_procedure_specialization_from_lowering \
  tests/test_workflow_lisp_lowering.py::test_runtime_erasure_rejects_compile_time_only_proc_ref_values \
  tests/test_workflow_lisp_examples.py::test_review_revise_parametric_design_docs_example_validates_with_prompt_bindings \
  -q
git diff --check
```

Expected: `215 tests collected`, `3 passed`, and clean diff check. If this
fails before implementation starts, stop and fix the unrelated baseline breakage
first instead of mixing it into the parametric feature work.

### Task 1: Add The Failing Parametric Header And Signature Tests

**Files:**
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `orchestrator/workflow_lisp/procedures.py`
- Modify if needed: `orchestrator/workflow_lisp/typecheck.py`

- [ ] **Step 1: Add parser and catalog tests for the new authored surface**

Add focused tests in `tests/test_workflow_lisp_procedures.py` for:

- `test_elaborate_defproc_parses_forall_and_where_metadata`
- `test_elaborate_defproc_rejects_duplicate_type_params`
- `test_elaborate_defproc_rejects_invalid_parametric_clause_order`
- `test_elaborate_defproc_rejects_where_subjects_not_declared_in_forall`
- `test_elaborate_defproc_rejects_malformed_where_clauses`
- `test_build_procedure_catalog_resolves_type_params_inside_nested_proc_ref_and_workflow_ref_types`

Each test should construct a tiny module string with `_write_module(...)` or the
existing inline helpers, then assert on `ProcedureDef` / `ProcedureSignature`
metadata instead of lowering output.

- [ ] **Step 2: Run the new tests and confirm they fail for the expected reason**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_procedures.py -q
python -m pytest \
  tests/test_workflow_lisp_procedures.py::test_elaborate_defproc_parses_forall_and_where_metadata \
  tests/test_workflow_lisp_procedures.py::test_elaborate_defproc_rejects_duplicate_type_params \
  tests/test_workflow_lisp_procedures.py::test_elaborate_defproc_rejects_invalid_parametric_clause_order \
  tests/test_workflow_lisp_procedures.py::test_elaborate_defproc_rejects_where_subjects_not_declared_in_forall \
  tests/test_workflow_lisp_procedures.py::test_elaborate_defproc_rejects_malformed_where_clauses \
  tests/test_workflow_lisp_procedures.py::test_build_procedure_catalog_resolves_type_params_inside_nested_proc_ref_and_workflow_ref_types \
  -q
```

Expected: collect succeeds and the new tests fail because the frontend does not
yet parse `:forall` / `:where` or carry generic signature metadata.

- [ ] **Step 3: Implement generic header metadata in `procedures.py`**

Implement the minimum parser/data-model changes:

- add `ProcedureTypeParam` and `ProcedureConstraintSyntax`;
- extend `ProcedureDef` with `type_params` and `where_clauses`;
- extend `ProcedureSignature` with `type_params` and `where_clauses`;
- teach `_elaborate_procedure_definition(...)` to accept exactly:
  `name`, optional `:forall`, params list, optional `:where`, `->`, return type;
- validate `:forall` clause shape, duplicate type-parameter names, and `:where`
  clause structure with dedicated `procedure_type_param_clause_invalid`,
  `procedure_type_param_duplicate`, `procedure_type_param_unknown`, and
  `procedure_where_clause_invalid` diagnostics;
- reject `:where` subjects that do not name a declared type parameter before
  metadata is stored;
- keep ordinary monomorphic `defproc` syntax unchanged;
- update helper constructors in `typecheck.py` that synthesize `ProcedureDef`
  or `ProcedureSignature` so generated procedures use empty tuples for the new
  fields.

- [ ] **Step 4: Re-run the focused parser and catalog tests**

Run the same `python -m pytest ... -q` command from Step 2.

Expected: the new tests pass, and no existing `defproc` tests regress.

- [ ] **Step 5: Check the scoped diff before moving on**

Run:

```bash
git diff -- \
  orchestrator/workflow_lisp/procedures.py \
  orchestrator/workflow_lisp/typecheck.py \
  tests/test_workflow_lisp_procedures.py
git diff --check -- \
  orchestrator/workflow_lisp/procedures.py \
  orchestrator/workflow_lisp/typecheck.py \
  tests/test_workflow_lisp_procedures.py
```

Expected: only the intended generic-header changes appear in these paths and
the scoped diff is whitespace-clean. Do not make an intermediate commit from a
dirty checkout; keep moving with unstaged or narrowly staged changes instead.

### Task 2: Add Compile-Time Type Parameters And Signature Substitution

**Files:**
- Modify: `orchestrator/workflow_lisp/type_env.py`
- Modify: `orchestrator/workflow_lisp/procedures.py`
- Modify if needed: `orchestrator/workflow_lisp/__init__.py`
- Modify: `tests/test_workflow_lisp_procedures.py`

- [ ] **Step 1: Add failing tests for resolved type-parameter behavior**

Add tests in `tests/test_workflow_lisp_procedures.py` for:

- `test_build_procedure_catalog_resolves_type_param_refs`
- `test_type_param_substitution_rewrites_nested_proc_ref_and_workflow_ref_types`
- `test_nonempty_where_metadata_is_preserved_when_header_validation_succeeds`

The first two should assert directly on resolved `TypeRef` trees. The third
should only prove that `where_clauses` metadata survives parsing/signature
building without yet asserting constraint semantics.

- [ ] **Step 2: Run the focused type-resolution tests and confirm failure**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_procedures.py -q
python -m pytest \
  tests/test_workflow_lisp_procedures.py::test_build_procedure_catalog_resolves_type_param_refs \
  tests/test_workflow_lisp_procedures.py::test_type_param_substitution_rewrites_nested_proc_ref_and_workflow_ref_types \
  tests/test_workflow_lisp_procedures.py::test_nonempty_where_metadata_is_preserved_when_header_validation_succeeds \
  -q
```

Expected: failure because there is no `TypeParamRef` or recursive substitution
support yet.

- [ ] **Step 3: Implement `TypeParamRef` and substitution helpers**

Extend `orchestrator/workflow_lisp/type_env.py` to:

- add `TypeParamRef`;
- allow a local type-parameter overlay during `resolve_type(...)`;
- resolve `NamedTypeExpr("T")` to `TypeParamRef` when `T` is declared by the
  current generic `defproc`;
- add one recursive substitution helper over every supported `TypeRef` branch;
- add one fail-closed helper that raises if `TypeParamRef` survives after
  specialization;
- keep runtime transport restrictions on ProcRef/workflow-ref/provider/prompt
  types exactly as they are now.

Then update `build_procedure_catalog(...)` so generic signatures resolve under a
local type-parameter scope and preserve `where_clauses` metadata.

- [ ] **Step 4: Re-run the focused type-resolution tests**

Run the same `python -m pytest ... -q` command from Step 2.

Expected: the new tests pass and existing non-generic signature behavior stays
unchanged.

- [ ] **Step 5: Check the scoped diff before moving on**

Run:

```bash
git diff -- \
  orchestrator/workflow_lisp/type_env.py \
  orchestrator/workflow_lisp/procedures.py \
  orchestrator/workflow_lisp/__init__.py \
  tests/test_workflow_lisp_procedures.py
git diff --check -- \
  orchestrator/workflow_lisp/type_env.py \
  orchestrator/workflow_lisp/procedures.py \
  orchestrator/workflow_lisp/__init__.py \
  tests/test_workflow_lisp_procedures.py
```

Expected: only compile-time type-parameter and substitution changes appear in
the scoped diff, with no whitespace issues.

### Task 3: Infer Concrete Type Bindings And Materialize Monomorphic Specializations

**Files:**
- Modify: `orchestrator/workflow_lisp/procedure_typecheck.py`
- Modify: `orchestrator/workflow_lisp/procedure_specialization.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/procedures.py`
- Modify: `tests/test_workflow_lisp_procedures.py`

- [ ] **Step 1: Add failing specialization tests**

Add tests in `tests/test_workflow_lisp_procedures.py` for:

- `test_compile_stage3_specializes_generic_defproc_before_lowering`
- `test_compile_stage3_reuses_equivalent_parametric_specializations`
- `test_compile_stage3_rejects_ambiguous_type_argument_bindings`
- `test_compile_stage3_rejects_unresolved_type_parameters`
- `test_compile_stage3_rejects_nonempty_where_before_structural_constraints_land`
- `test_compile_stage3_rejects_parametric_specialization_cycles`
- `test_compile_stage3_supports_type_params_nested_inside_proc_ref_signatures`

Each test should compile a tiny module and assert on typed procedures,
specialized names, diagnostic codes, or specialization metadata, not on raw
debug YAML.

- [ ] **Step 2: Run the failing specialization tests**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_procedures.py -q
python -m pytest \
  tests/test_workflow_lisp_procedures.py::test_compile_stage3_specializes_generic_defproc_before_lowering \
  tests/test_workflow_lisp_procedures.py::test_compile_stage3_reuses_equivalent_parametric_specializations \
  tests/test_workflow_lisp_procedures.py::test_compile_stage3_rejects_ambiguous_type_argument_bindings \
  tests/test_workflow_lisp_procedures.py::test_compile_stage3_rejects_unresolved_type_parameters \
  tests/test_workflow_lisp_procedures.py::test_compile_stage3_rejects_nonempty_where_before_structural_constraints_land \
  tests/test_workflow_lisp_procedures.py::test_compile_stage3_rejects_parametric_specialization_cycles \
  tests/test_workflow_lisp_procedures.py::test_compile_stage3_supports_type_params_nested_inside_proc_ref_signatures \
  -q
```

Expected: failure because the current compiler still typechecks and lowers only
monomorphic procedures.

- [ ] **Step 3: Implement inference and specialization on the landed owner seams**

Implement the specialization pipeline on current checkout structure:

- extend `ProcedureCallableSpecialization` with `type_bindings` and a stable
  combined specialization key;
- in `procedure_typecheck.py`, detect generic procedure signatures, infer
  concrete type bindings from actual argument types and compile-time callable
  signatures, and emit dedicated diagnostics for ambiguity or missing bindings;
- in `procedure_specialization.py`, add deterministic parametric
  specialization-key and generated-name logic, then materialize monomorphic
  `TypedProcedureDef` clones by substituting type bindings before body
  typechecking;
- keep reuse in the same cache/queue as existing ProcRef/workflow-ref/value
  specialization instead of adding a second specialization pipeline;
- extend the existing specialization-cycle guard so recursive generic
  specialization requests fail closed with `parametric_specialization_cycle`
  at the authored call site;
- reject any non-empty `:where` with a dedicated
  `unsupported_parametric_constraint_surface`-style diagnostic until the
  structural-constraints slice lands;
- in `compiler.py`, thread the new specialization requests through the existing
  stage-3 fixpoint so materialized parametric helpers are available before
  effect closure and lowering.

- [ ] **Step 4: Re-run the focused specialization tests**

Run the same `python -m pytest ... -q` command from Step 2.

Expected: the new tests pass, and existing ProcRef/workflow-ref specialization
tests still pass without behavioral weakening.

- [ ] **Step 5: Check the scoped diff before moving on**

Run:

```bash
git diff -- \
  orchestrator/workflow_lisp/procedure_typecheck.py \
  orchestrator/workflow_lisp/procedure_specialization.py \
  orchestrator/workflow_lisp/compiler.py \
  orchestrator/workflow_lisp/procedures.py \
  tests/test_workflow_lisp_procedures.py
git diff --check -- \
  orchestrator/workflow_lisp/procedure_typecheck.py \
  orchestrator/workflow_lisp/procedure_specialization.py \
  orchestrator/workflow_lisp/compiler.py \
  orchestrator/workflow_lisp/procedures.py \
  tests/test_workflow_lisp_procedures.py
```

Expected: the diff shows only specialization-pipeline changes, including the
new cycle failure coverage, and remains whitespace-clean.

### Task 4: Enforce Lowering Erasure And Artifact-Lineage Guarantees

**Files:**
- Modify: `orchestrator/workflow_lisp/lowering/procedures.py`
- Modify if needed: `orchestrator/workflow_lisp/source_map.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_source_map.py`
- Modify: `tests/test_workflow_semantic_ir.py`

- [ ] **Step 1: Add failing artifact and runtime-erasure tests**

Add tests for:

- `tests/test_workflow_lisp_lowering.py::test_parametric_specialization_rejects_leaked_type_params_before_runtime_lowering`
- `tests/test_workflow_lisp_source_map.py::test_source_map_records_parametric_specialization_authored_lineage`
- `tests/test_workflow_semantic_ir.py::test_compiled_bundle_erases_type_params_before_semantic_and_executable_surfaces`

Use a real stage-3 compile of a tiny generic procedure workflow so the tests
cover typed procedures, lowered workflows, source-map payload, and semantic IR
from one concrete artifact path.

- [ ] **Step 2: Run the failing erasure and lineage tests**

Run:

```bash
python -m pytest --collect-only \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_source_map.py \
  tests/test_workflow_semantic_ir.py \
  -q
python -m pytest \
  tests/test_workflow_lisp_lowering.py::test_parametric_specialization_rejects_leaked_type_params_before_runtime_lowering \
  tests/test_workflow_lisp_source_map.py::test_source_map_records_parametric_specialization_authored_lineage \
  tests/test_workflow_semantic_ir.py::test_compiled_bundle_erases_type_params_before_semantic_and_executable_surfaces \
  -q
```

Expected: failure because the runtime-erasure guard does not yet know about
`TypeParamRef`, and artifact-lineage assertions for parametric helpers do not
yet exist.

- [ ] **Step 3: Add fail-closed erasure checks and provenance notes**

Implement the smallest required runtime-boundary behavior:

- teach `lowering/procedures.py` to reject any procedure or local type binding
  that still contains `TypeParamRef` before runtime-visible lowering;
- keep generated helpers monomorphic before they reach lowered workflow bodies,
  source maps, or semantic/executable artifacts;
- reuse existing provenance/source-map structures and only touch
  `source_map.py` if the new tests prove the current note emission is
  insufficient to trace generic specializations back to the authored call site
  and generic definition.

- [ ] **Step 4: Re-run the focused erasure and lineage tests**

Run the same `python -m pytest ... -q` command from Step 2.

Expected: the new tests pass and the compiled bundle contains no runtime-visible
parametric type refs.

- [ ] **Step 5: Check the scoped diff before moving on**

Run:

```bash
git diff -- \
  orchestrator/workflow_lisp/lowering/procedures.py \
  orchestrator/workflow_lisp/source_map.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_source_map.py \
  tests/test_workflow_semantic_ir.py
git diff --check -- \
  orchestrator/workflow_lisp/lowering/procedures.py \
  orchestrator/workflow_lisp/source_map.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_source_map.py \
  tests/test_workflow_semantic_ir.py
```

Expected: only erasure and provenance changes appear in these paths, with no
scoped diff hygiene issues.

### Task 5: Add Imported-Module Proof, Real Workflow Proof, And Authoring Docs

**Files:**
- Modify: `tests/test_workflow_lisp_modules.py`
- Modify: `tests/test_workflow_lisp_examples.py`
- Modify: `docs/lisp_workflow_drafting_guide.md`

- [ ] **Step 1: Reconfirm the imported-module test file is still safe to touch**

Run:

```bash
git status --short -- tests/test_workflow_lisp_modules.py
git diff -- tests/test_workflow_lisp_modules.py
```

Expected: only the pre-existing whitespace-only hunk is present before this
task's edits begin. If unrelated edits have accumulated in that file, stop and
ask for direction instead of folding them into this slice.

- [ ] **Step 2: Add failing integration and authoring-surface tests**

Add:

- `tests/test_workflow_lisp_modules.py::test_compile_stage3_entrypoint_specializes_imported_parametric_proc_defs`
- `tests/test_workflow_lisp_examples.py::test_generic_defproc_workflow_body_compiles_to_validated_bundle`

The module test should compile an entry module that imports a generic helper
from another `.orc` module and prove the specialization happens through the
entrypoint path, not only same-file compilation. The example test should
compile a real workflow body that calls a generic procedure and reaches shared
validation.

- [ ] **Step 3: Run the failing integration tests**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_examples.py -q
python -m pytest \
  tests/test_workflow_lisp_modules.py::test_compile_stage3_entrypoint_specializes_imported_parametric_proc_defs \
  tests/test_workflow_lisp_examples.py::test_generic_defproc_workflow_body_compiles_to_validated_bundle \
  -q
```

Expected: failure because there is no imported generic-procedure specialization
coverage yet.

- [ ] **Step 4: Land the integration proof and update author guidance**

Implement the smallest remaining integration/documentation changes:

- add the imported-module proof with existing `_write_module(...)` helpers or a
  small durable fixture if the inline setup becomes unreadable;
- add the real workflow-body compile proof in `tests/test_workflow_lisp_examples.py`;
- update `docs/lisp_workflow_drafting_guide.md` to say:
  - generic `defproc` headers with `:forall` are implemented;
  - non-empty `:where` is currently parsed but rejected pending structural
    constraints;
  - type parameters are compile-time-only and erased before runtime artifacts;
  - generic `defworkflow` remains out of scope.

- [ ] **Step 5: Re-run the integration tests**

Run the same `python -m pytest ... -q` command from Step 2.

Expected: both tests pass and demonstrate the required integration coverage for
frontend changes.

- [ ] **Step 6: Check the scoped diff before final verification**

Run:

```bash
git diff -- \
  tests/test_workflow_lisp_modules.py \
  tests/test_workflow_lisp_examples.py \
  docs/lisp_workflow_drafting_guide.md
git diff --check -- \
  tests/test_workflow_lisp_modules.py \
  tests/test_workflow_lisp_examples.py \
  docs/lisp_workflow_drafting_guide.md
```

Expected: the task's intended integration/doc changes are visible, the
pre-existing whitespace hunk in `tests/test_workflow_lisp_modules.py` is still
distinguishable from the new work, and the scoped diff is whitespace-clean.

### Task 6: Run Full Verification For This Slice

**Files:**
- Verify only: all files touched above

- [ ] **Step 1: Re-run compile and collection checks**

Run:

```bash
python -m compileall orchestrator/workflow_lisp
python -m pytest --collect-only \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_modules.py \
  tests/test_workflow_lisp_source_map.py \
  tests/test_workflow_semantic_ir.py \
  tests/test_workflow_lisp_examples.py \
  -q
```

Expected: compile succeeds and collect-only succeeds on all modified test
modules.

- [ ] **Step 2: Run the full relevant verification slice**

Run:

```bash
python -m pytest \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_modules.py \
  tests/test_workflow_lisp_source_map.py \
  tests/test_workflow_semantic_ir.py \
  tests/test_workflow_lisp_examples.py \
  -q
git diff --check
```

Expected: the full relevant frontend slice passes, and the diff is free of
whitespace or patch-format issues.

- [ ] **Step 3: Run one explicit end-to-end stage-3 usage proof**

Run:

```bash
python -m pytest \
  tests/test_workflow_lisp_examples.py::test_generic_defproc_workflow_body_compiles_to_validated_bundle \
  tests/test_workflow_lisp_modules.py::test_compile_stage3_entrypoint_specializes_imported_parametric_proc_defs \
  -q
```

Expected: both tests pass. This is the required integration proof for a
frontend change; no separate orchestrator workflow smoke run is needed because
these tests already compile through the shared validation/bundle pipeline.

## Acceptance Checklist

- Generic `defproc` headers accept `:forall` in the approved clause order.
- `:where` metadata is parsed and retained, but any non-empty semantic
  constraint surface still fails with a dedicated diagnostic in this slice.
- Malformed `:where` clauses and `:where` subjects that do not match declared
  type parameters fail during header validation with dedicated diagnostics.
- `TypeParamRef` can appear inside nested `ProcRef[...]` and `WorkflowRef[...]`
  signature positions before specialization.
- Call-site inference resolves concrete bindings from actual arguments alone and
  rejects ambiguous or unresolved bindings.
- Deterministic specialization reuse works for equivalent call sites.
- Recursive generic specialization requests fail closed with
  `parametric_specialization_cycle`.
- Parametric specializations materialize before lowering and compose with
  existing ProcRef/workflow-ref/value specialization flow.
- No `TypeParamRef` reaches lowered workflows, source maps, semantic IR,
  executable IR, or runtime-visible values.
- Imported-module and real workflow-body integration proofs pass.
- Existing non-generic procedure and specialization behavior remains intact.
