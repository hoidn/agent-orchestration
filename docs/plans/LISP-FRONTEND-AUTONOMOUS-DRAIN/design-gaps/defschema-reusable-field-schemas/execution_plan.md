# Workflow Lisp `defschema` Reusable Field Schemas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the bounded Workflow Lisp `defschema` authoring surface so reusable field bundles can be included into schemas, records, and union variants while all downstream typing, lowering, and shared validation continue to consume only concrete expanded `RecordDef` and `UnionDef` structures.

**Architecture:** Keep `defschema` entirely frontend-local in `orchestrator/workflow_lisp/`. Parse authored schema definitions plus explicit `(:include SchemaName)` members, build a schema catalog during definition elaboration, expand includes left-to-right into ordinary `RecordField` lists before `FrontendTypeEnvironment` or workflow typing runs, and carry schema metadata only far enough for module linking and diagnostics. Reuse the current staged compiler, module graph, macro expansion, diagnostics, and source-span machinery rather than introducing runtime schema values, new lowering nodes, or command-backed materialization.

**Tech Stack:** Python dataclasses, `orchestrator/workflow_lisp`, existing shared `orchestrator.workflow` validation/runtime surfaces, pytest, `.orc` fixtures under `tests/fixtures/workflow_lisp/`, and the existing `python -m orchestrator compile ...` smoke path.

---

## Fixed Inputs

Treat these as implementation authority for this slice:

- `docs/index.md`
- `docs/steering.md`
  - currently empty in this checkout; do not treat that as permission to widen scope
- `docs/design/workflow_lisp_frontend_specification.md`
  - `8.1 defschema`
  - `8.4 defrecord`
  - `8.5 defunion`
  - `38. Intermediate Overview`
  - `60. Type Validation`
  - `67. Frontend Parse/Module Errors`
  - `69. Type Errors`
  - `74. Source Map Requirements`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `2. Relationship To The Full Specification`
  - `3. Non-Goals`
  - `4.2 Definitions`
  - `10. Validation`
  - `14. Implementation Stages`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defschema-reusable-field-schemas/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-full-restart-20260523T081550Z/iterations/7/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-full-restart-20260523T081550Z/iterations/7/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

Reference these exact implementation seams before editing:

- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/modules.py`
- `orchestrator/workflow_lisp/macros.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `tests/test_workflow_lisp_definitions.py`
- `tests/test_workflow_lisp_modules.py`
- `tests/test_workflow_lisp_macros.py`
- `tests/test_workflow_lisp_workflows.py`

## Current Repo Baseline

Assume this exact starting point:

- `progress_ledger.json` is still `{"ledger_version":1,"events":[]}`.
- `orchestrator/workflow_lisp/definitions.py` only admits `defenum`, `defpath`, `defrecord`, and `defunion` top-level forms and produces `WorkflowLispModule(..., definitions=...)` with no schema metadata.
- `orchestrator/workflow_lisp/compiler.py` Stage 1 and linked Stage 3 compilation construct definition modules with only the existing concrete type definitions and have no schema-expansion pass.
- `orchestrator/workflow_lisp/modules.py` exposes only type, macro, function, procedure, and workflow bindings; there is no schema namespace in export surfaces or import scopes.
- `orchestrator/workflow_lisp/macros.py` omits `defschema` from both `_RESERVED_MACRO_NAMES` and `_ALLOWED_TOP_LEVEL_HEADS`.
- `orchestrator/workflow_lisp/type_env.py` resolves only concrete types and would currently fall back to generic `type_unknown` for schema-name misuse.
- No `defschema` fixtures or test coverage currently exist under `tests/fixtures/workflow_lisp/`, `tests/test_workflow_lisp_definitions.py`, `tests/test_workflow_lisp_modules.py`, `tests/test_workflow_lisp_macros.py`, or `tests/test_workflow_lisp_workflows.py`.

Execution rule for this plan: if the checkout diverges from the approved implementation architecture, the approved architecture and the failing tests written from this plan win. If a focused failing test shows this slice cannot be implemented without widening into lowering/runtime/shared-validation ownership, stop, record the blocking mismatch, and revise the approved architecture instead of patching around it.

## Hard Scope Limits

Implement only the bounded `defschema-reusable-field-schemas` slice:

- top-level `defschema` elaboration
- authored member parsing for ordinary fields plus `(:include SchemaName)`
- schema catalog construction and recursive expansion
- deterministic duplicate-field, cycle, unknown-schema, and schema-as-type diagnostics
- schema-aware module export/import plumbing
- macro admission so macro-expanded `defschema` forms are allowed through the current top-level gate
- workflow transparency proof that expanded records/unions compile exactly like inline-field equivalents
- focused fixtures and tests for definitions, modules, macros, workflows, and one compile smoke

Explicit non-goals:

- no runtime execution changes
- no shared validation or lowering redesign
- no new command-step, adapter, or runtime-native effect surface
- no new workflow-boundary transport for schema values
- no redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant proof
- no edits to `orchestrator/workflow_lisp/workflows.py`, `orchestrator/workflow_lisp/typecheck.py`, `orchestrator/workflow_lisp/procedures.py`, or `orchestrator/workflow_lisp/lowering.py` unless a focused failing test proves a frontend-owned transparency fix is impossible without them

## Locked Contracts

Do not re-decide these during implementation.

Author surface:

```lisp
(defschema ReportTargets
  (execution-report-target Path.execution-report-target)
  (:include CommonTargets)
  (review-report-target Path.review-report-target))
```

Inclusion rules:

- include spelling is exactly `(:include SchemaName)`
- include members are allowed in `defschema`, `defrecord`, and union variant payloads
- bare schema symbols are never implicit splices
- no other keyword-headed field-member forms are valid in this slice

Internal shape contract:

- add authored schema metadata in `definitions.py` with:
  - `SchemaDef(name, members, span)`
  - `SchemaInclude(schema_name, span)`
- keep `WorkflowLispModule.definitions` downstream-authoritative and concrete
- add `WorkflowLispModule.schemas` for authored schema metadata
- after expansion, downstream stages must still see only concrete `RecordField`, `RecordDef`, and `UnionVariant.fields`

Expansion contract:

1. collect local and imported schemas into one frontend-local catalog
2. expand schema members recursively, left-to-right
3. expand record fields and union-variant payloads by splicing included schema fields in authored order
4. validate duplicates and cycles during expansion with original authored spans
5. freeze the expanded concrete definitions before `FrontendTypeEnvironment.from_module(...)` or workflow typing runs

Module-linking contract:

- schema names participate in module export/import resolution
- schema bindings are frontend-only and remain separate from concrete type bindings
- imported schemas must resolve through the existing alias and `:only` machinery
- schema bindings must not enter runtime catalogs or boundary-type exports

Type-misuse contract:

- schema names are valid only in include positions
- using a schema name where a type name is required must raise `schema_used_as_type`, not generic `type_unknown`

Required diagnostics:

- `schema_definition_invalid`
- `schema_unknown`
- `schema_cycle`
- `schema_field_duplicate`
- `schema_used_as_type`

Existing diagnostics to reuse:

- `definition_duplicate`
- `record_field_duplicate`
- `union_variant_duplicate`
- `module_export_missing`
- `module_import_ambiguous`
- `definition_form_unknown`

## File Ownership

Create:

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defschema-reusable-field-schemas/execution_plan.md`
- `tests/fixtures/workflow_lisp/valid/defschema_type_definitions.orc`
- `tests/fixtures/workflow_lisp/valid/defschema_workflow_inputs.orc`
- `tests/fixtures/workflow_lisp/invalid/defschema_unknown_schema.orc`
- `tests/fixtures/workflow_lisp/invalid/defschema_cycle.orc`
- `tests/fixtures/workflow_lisp/invalid/defschema_duplicate_field.orc`
- `tests/fixtures/workflow_lisp/invalid/defschema_used_as_type.orc`
- `tests/fixtures/workflow_lisp/modules/valid/schema_import/neurips/entry.orc`
- `tests/fixtures/workflow_lisp/modules/valid/schema_import/neurips/schemas.orc`
- `tests/fixtures/workflow_lisp/modules/invalid/schema_only_ambiguous/neurips/entry.orc`
- `tests/fixtures/workflow_lisp/modules/invalid/schema_only_ambiguous/neurips/a.orc`
- `tests/fixtures/workflow_lisp/modules/invalid/schema_only_ambiguous/neurips/b.orc`

Modify:

- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/modules.py`
- `orchestrator/workflow_lisp/macros.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `tests/test_workflow_lisp_definitions.py`
- `tests/test_workflow_lisp_modules.py`
- `tests/test_workflow_lisp_macros.py`
- `tests/test_workflow_lisp_workflows.py`

Do not broaden ownership into:

- `orchestrator/workflow/`
- runtime/state/publish/resume modules
- YAML workflows or prompt files
- command adapters

## Task 1: Lock The Schema Contract With Fixtures And Failing Tests

**Files:**

- Create: `tests/fixtures/workflow_lisp/valid/defschema_type_definitions.orc`
- Create: `tests/fixtures/workflow_lisp/valid/defschema_workflow_inputs.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/defschema_unknown_schema.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/defschema_cycle.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/defschema_duplicate_field.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/defschema_used_as_type.orc`
- Create: `tests/fixtures/workflow_lisp/modules/valid/schema_import/neurips/entry.orc`
- Create: `tests/fixtures/workflow_lisp/modules/valid/schema_import/neurips/schemas.orc`
- Create: `tests/fixtures/workflow_lisp/modules/invalid/schema_only_ambiguous/neurips/entry.orc`
- Create: `tests/fixtures/workflow_lisp/modules/invalid/schema_only_ambiguous/neurips/a.orc`
- Create: `tests/fixtures/workflow_lisp/modules/invalid/schema_only_ambiguous/neurips/b.orc`
- Modify: `tests/test_workflow_lisp_definitions.py`
- Modify: `tests/test_workflow_lisp_modules.py`
- Modify: `tests/test_workflow_lisp_macros.py`
- Modify: `tests/test_workflow_lisp_workflows.py`

- [ ] **Step 1: Add same-file and cross-module fixtures that pin the authored surface**

Create fixtures for:

- one valid same-file schema graph with nested includes, record inclusion, and union-variant inclusion
- one valid workflow fixture that uses a record expanded from schemas and compiles through the normal Stage 3 path
- invalid unknown-schema, schema-cycle, duplicate-field, and schema-used-as-type cases
- one valid imported schema graph using `export` plus `import ... :only (...)`
- one invalid ambiguous bare imported schema case

- [ ] **Step 2: Add failing tests before implementation**

Add focused tests with exact names:

- `test_elaborate_definition_module_supports_defschema_and_expands_schema_includes`
- `test_compile_stage1_reports_unknown_schema_include`
- `test_compile_stage1_reports_schema_cycles`
- `test_compile_stage1_reports_duplicate_fields_from_schema_expansion`
- `test_compile_stage1_reports_schema_used_as_type`
- `test_compile_stage1_entrypoint_imports_exported_schemas_for_includes`
- `test_compile_stage1_entrypoint_rejects_ambiguous_unqualified_schema_imports`
- `test_compile_stage1_allows_macro_emitted_defschema_forms`
- `test_compile_stage3_module_keeps_schema_built_records_transparent_to_workflow_typing`

- [ ] **Step 3: Collect the narrowed suites after adding tests**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_definitions.py tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_workflows.py -q
```

Expected: the new tests and fixtures collect successfully.

- [ ] **Step 4: Run the new focused selectors and confirm they fail for the missing feature**

Run:

```bash
python -m pytest tests/test_workflow_lisp_definitions.py -k 'defschema or schema' -q
python -m pytest tests/test_workflow_lisp_modules.py -k 'schema' -q
python -m pytest tests/test_workflow_lisp_macros.py -k 'defschema' -q
python -m pytest tests/test_workflow_lisp_workflows.py -k 'schema' -q
```

Expected: failures point at unsupported `defschema`, missing schema bindings, and missing misuse diagnostics rather than unrelated runtime behavior.

## Task 2: Implement Authored Schema Definitions And Concrete Expansion

**Files:**

- Modify: `orchestrator/workflow_lisp/definitions.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/diagnostics.py`
- Modify: `tests/test_workflow_lisp_definitions.py`

- [ ] **Step 1: Extend `definitions.py` with authored schema data structures**

Add:

- `SchemaInclude`
- `SchemaDef`
- a shared authored-member vocabulary for schemas, records, and union variants
- `WorkflowLispModule.schemas`

Keep `WorkflowLispModule.definitions` limited to concrete expanded `EnumDef | PathDef | RecordDef | UnionDef`.

- [ ] **Step 2: Parse `defschema` and `(:include ...)` members**

Update top-level elaboration so:

- `defschema` is accepted in `_elaborate_top_level_form(...)`
- malformed schema members raise `schema_definition_invalid`
- `defrecord` and `defunion` collect authored members first instead of immediately freezing only raw `RecordField` values

- [ ] **Step 3: Add a frontend-local schema catalog and left-to-right expansion helpers**

Implement deterministic expansion that:

- resolves local and imported schema names
- preserves include spans for diagnostics
- rejects cycles with `schema_cycle`
- rejects duplicate fields inside expanded schemas with `schema_field_duplicate`
- rejects duplicate fields introduced into records or variants with existing `record_field_duplicate`

- [ ] **Step 4: Integrate schema expansion into the definition-validation path**

Update compiler sequencing so Stage 1 and linked Stage 3 both:

1. elaborate authored definitions
2. expand schemas to concrete record/union payloads
3. validate the expanded concrete definitions
4. pass only the expanded concrete definitions downstream

Avoid any lowering or runtime changes.

- [ ] **Step 5: Re-run the definition-focused suite until it passes**

Run:

```bash
python -m pytest tests/test_workflow_lisp_definitions.py -k 'defschema or schema' -q
```

Expected: PASS with coverage for valid same-file expansion and all schema-definition failure modes.

## Task 3: Thread Schema Bindings Through Modules, Macros, And Type Resolution

**Files:**

- Modify: `orchestrator/workflow_lisp/modules.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/macros.py`
- Modify: `orchestrator/workflow_lisp/type_env.py`
- Modify: `tests/test_workflow_lisp_modules.py`
- Modify: `tests/test_workflow_lisp_macros.py`

- [ ] **Step 1: Reserve and admit `defschema` at the macro/top-level gate**

Update `_RESERVED_MACRO_NAMES` and `_ALLOWED_TOP_LEVEL_HEADS` so macro authors cannot bind over `defschema`, and macro-expanded `defschema` forms are accepted by the same top-level validator as other definition heads.

- [ ] **Step 2: Add schema namespaces to export surfaces and import scopes**

Extend `ModuleExportSurface` and `ModuleImportScope` with explicit schema binding maps. Keep schema bindings parallel to type bindings rather than collapsing them into `types_by_name`, because schema names must be importable for includes but invalid as concrete type refs.

- [ ] **Step 3: Feed imported schemas into definition elaboration and expansion**

Update linked Stage 1 and linked Stage 3 compilation so imported schemas are available before elaborating dependent modules. The dependency order must remain:

1. compile imports first
2. expose their exported schemas
3. expand the importer's includes against those bindings
4. only then build the concrete `FrontendTypeEnvironment`

- [ ] **Step 4: Add explicit `schema_used_as_type` handling**

Teach `FrontendTypeEnvironment` to distinguish:

- imported/local concrete type names
- imported/local schema names

If a schema name appears in a type position, emit `schema_used_as_type` with the authored field span instead of falling through to `type_unknown`.

- [ ] **Step 5: Re-run module and macro selectors**

Run:

```bash
python -m pytest tests/test_workflow_lisp_modules.py -k 'schema' -q
python -m pytest tests/test_workflow_lisp_macros.py -k 'defschema' -q
```

Expected: PASS with schema export/import coverage, ambiguity detection, and macro-emitted `defschema` admission.

## Task 4: Prove Downstream Workflow Transparency And Finish Verification

**Files:**

- Modify: `tests/test_workflow_lisp_workflows.py`
- Modify: `tests/fixtures/workflow_lisp/valid/defschema_workflow_inputs.orc`
- Modify only if a focused failing test proves it is required: `orchestrator/workflow_lisp/compiler.py`

- [ ] **Step 1: Add the workflow transparency test**

Use `defschema_workflow_inputs.orc` to prove that a workflow using a record built from included schemas:

- typechecks through the current workflow catalog path
- exposes the expected concrete record fields to expressions
- compiles through Stage 3 without any schema-aware lowering code

- [ ] **Step 2: Run the workflow-focused selector**

Run:

```bash
python -m pytest tests/test_workflow_lisp_workflows.py -k 'schema' -q
```

Expected: PASS with no changes required to workflow typing or lowering ownership boundaries.

- [ ] **Step 3: Run the recorded narrow verification commands**

Run exactly:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_definitions.py tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_workflows.py -q
python -m pytest tests/test_workflow_lisp_definitions.py -k 'defschema or schema' -q
python -m pytest tests/test_workflow_lisp_modules.py -k 'schema' -q
python -m pytest tests/test_workflow_lisp_macros.py -k 'defschema' -q
python -m pytest tests/test_workflow_lisp_workflows.py -k 'schema' -q
python -m orchestrator compile tests/fixtures/workflow_lisp/valid/defschema_workflow_inputs.orc --entry-workflow summarize
```

Expected:

- collection succeeds
- all focused schema selectors pass
- the compile smoke succeeds and proves schema-expanded records remain transparent to downstream compilation

## Acceptance Conditions

This slice is complete only when all of the following are true:

1. `defschema` is accepted as a top-level authored form.
2. `(:include SchemaName)` works in schemas, records, and union variants.
3. Schema reuse expands deterministically to concrete field lists before `FrontendTypeEnvironment` and workflow typing run.
4. Unknown schema names, cycles, duplicate fields, and schema-as-type misuse fail with source-mapped frontend diagnostics.
5. Imported schema bindings resolve through the existing module system.
6. Existing workflow typing, lowering, and shared validation remain schema-agnostic because only concrete records and unions leave the definition phase.
7. The recorded focused pytest selectors and `python -m orchestrator compile ...` smoke command all pass without widening runtime ownership.
