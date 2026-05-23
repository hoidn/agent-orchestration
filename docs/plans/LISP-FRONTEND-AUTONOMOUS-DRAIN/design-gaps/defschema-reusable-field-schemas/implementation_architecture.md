# `defschema` Reusable Field Schemas Implementation Architecture

## Scope

This design gap covers only the bounded `defschema` slice selected for the
Workflow Lisp frontend full-design drain:

- add an implementation-ready top-level `defschema` definition form for
  reusable field bundles that are independent of concrete record or union
  types;
- define one explicit authored inclusion surface for reusing schemas inside
  `defschema`, `defrecord`, and union-variant payloads;
- expand schema reuse into ordinary concrete `RecordField` payloads before
  expression typing, workflow typing, lowering, or shared validation;
- preserve deterministic diagnostics, spans, and inclusion provenance when
  schema expansion introduces unknown schema names, cycles, or duplicate
  fields;
- thread schema names through the existing module import/export surface so
  schema reuse is available across linked `.orc` modules without creating a
  new runtime boundary.

Out of scope for this tranche:

- new runtime execution behavior, shared validation behavior, or build/runtime
  artifact changes;
- new command-step, adapter, or runtime-native effect semantics;
- redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog,
  SourceMap, pointer authority, or variant proof;
- record-construction syntax changes, workflow-boundary flattening changes, or
  new provider/command lowering rules;
- report parsing, pointer-as-state, or YAML-text generation.

This is an implementation architecture for exactly the selected
`defschema-reusable-field-schemas` gap. It does not replace the product design
in `docs/design/workflow_lisp_frontend_specification.md`.

## Design Constraints

The implementation must stay coherent with:

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
  - `4.2 Definitions`
  - `10. Validation`
  - `14. Implementation Stages`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/steering.md`

The slice must also preserve the guardrails established by the current
checkout and prior implementation architectures:

- keep `orchestrator/workflow_lisp/` as the frontend-owned package and keep
  shared runtime semantics under `orchestrator/workflow/`;
- reuse the existing staged pipeline:
  read -> syntax -> modules -> macro expansion -> definitions ->
  type environment -> typing -> lowering -> shared validation;
- keep structured type definitions authoritative and treat schema reuse as
  authored-surface compression, not as a second type system;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- keep command-boundary rules unchanged: `defschema` must not become a loophole
  for command-backed semantic materialization or hidden procedural state.

`docs/design/workflow_command_adapter_contract.md` remains authoritative here
even though this slice adds no new command form. Schema expansion must stay a
frontend-local elaboration step; it must not shell out to scripts, parse
reports, or synthesize semantic state through opaque command boundaries.

`docs/steering.md` is empty in this checkout. That does not widen scope. The
selector bundle, target contract, existing architecture index, and current repo
evidence remain the effective steering surfaces.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/core-workflow-ast-shared-contract/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defun-pure-helper-surface/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/executable-ir-runtime-plan/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-cli-artifact-emission/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-required-lints/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-validation-diagnostics-pipeline/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/hygienic-defmacro-system/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/lisp-frontend-cli-diagnostics-surface/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/loop-recur-bounded-loops/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/module-import-export-resolution/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resource-drain-library/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resume-or-start-reusable-state-validation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/semantic-workflow-ir-shared-contract/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-boundary-type-flattening/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md`

### Decisions Reused

- Reuse the existing frontend package ownership split and staged compile
  pipeline.
- Reuse `SourcePosition`, `SourceSpan`, recursive syntax metadata,
  `WorkflowLispModule`, `LispFrontendDiagnostic`, and the existing diagnostic
  classification pipeline instead of inventing parallel provenance or error
  systems.
- Reuse `RecordField`, `UnionVariant`, `FrontendTypeEnvironment`, and the
  existing concrete record/union authority downstream of definition
  elaboration.
- Reuse the module linker and export/import ownership boundaries rather than
  inventing a second cross-file registry for reusable schemas.
- Reuse the honesty rule from the build, source-map, and semantic-IR slices:
  do not fabricate new shared artifacts or runtime semantics for a
  frontend-local authoring feature.

### New Decisions In This Slice

- Introduce `defschema` as a frontend-local reusable field-bundle definition,
  not as a new boundary type.
- Add one explicit inclusion member form, `(:include SchemaName)`, for schema
  reuse inside `defschema`, `defrecord`, and union-variant payloads.
- Expand schema members into ordinary concrete `RecordField` lists during
  definition compilation so later typechecking, workflow typing, lowering, and
  shared validation continue to see only concrete records and unions.
- Preserve schema definitions as authored metadata on the compiled module so
  module export/import and diagnostics can refer to them, while keeping
  downstream type authority on expanded `RecordDef` and `UnionDef` payloads.
- Keep schema names in the top-level definition namespace, but treat them as
  invalid in type positions and diagnose that misuse explicitly.

### Conflicts Or Revisions

The full design specifies what `defschema` is for, but it does not define a
concrete authored inclusion syntax. This slice resolves that missing contract
with one bounded implementation choice:

- schema reuse is spelled `(:include SchemaName)`;
- bare schema symbols are not treated as implicit field splices;
- the same include spelling works in schemas, records, and union variants.

Reason:

- it is explicit in authored source;
- it fits the existing reader and syntax pipeline without broad parser work;
- it avoids ambiguity with ordinary field/type names and future namespace
  expansion;
- it keeps schema expansion entirely inside definition elaboration.

The current Stage 1 implementation only knows `defenum`, `defpath`,
`defrecord`, and `defunion`. This slice revises that frontend-local boundary
narrowly by adding one new authored definition kind and one pre-typecheck
expansion pass. It does not revise shared concepts such as Core Workflow AST,
Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant
proof.

## Ownership Boundaries

This slice owns:

- top-level `defschema` elaboration and validation;
- authored schema-member and schema-include parsing;
- a frontend-local schema catalog and expansion algorithm;
- duplicate-field, unknown-schema, misuse, and cycle diagnostics for schema
  reuse;
- schema-aware module import/export plumbing;
- macro/top-level admission updates so macros may emit `defschema` safely;
- focused fixtures and tests for definition parsing, expansion, module linking,
  macro admission, and workflow transparency.

This slice intentionally does not own:

- expression typing rules outside the limited “schema name used as a type”
  diagnostic;
- workflow/procedure lowering, shared validation, runtime execution, or build
  artifact formats;
- shared command-adapter policy, resource transitions, provider semantics, or
  state layout;
- new runtime transport for schema values, because schemas do not cross
  workflow boundaries as values or types.

## Current Checkout Facts

The current repo evidence shows `defschema` is still a design-only gap:

- `docs/design/workflow_lisp_frontend_specification.md` defines `defschema`,
  but `rg -n "defschema"` finds no implementation or test coverage under
  `orchestrator/workflow_lisp/` or `tests/`;
- `orchestrator/workflow_lisp/definitions.py` currently defines only
  `EnumDef`, `PathDef`, `RecordDef`, and `UnionDef`, and rejects other
  top-level definition heads;
- `orchestrator/workflow_lisp/compiler.py` still treats Stage 1 definitions as
  the four existing type forms and does not reserve a schema-expansion pass;
- `orchestrator/workflow_lisp/modules.py` currently scans only `defrecord`,
  `defenum`, `defunion`, and `defpath` as type-like exported definitions;
- `orchestrator/workflow_lisp/macros.py` reserves and allows a fixed set of
  top-level heads that omits `defschema`;
- `tests/test_workflow_lisp_definitions.py` exercises only the four current
  Stage 1 type-definition forms.

The gap is therefore not “finish a partial implementation.” The gap is to add
one explicit reusable-field-schema contract without widening into a second type
system or runtime feature.

## Proposed Package Boundary

Keep ownership in the existing frontend package:

```text
orchestrator/workflow_lisp/
  compiler.py          # add schema-expansion orchestration to Stage 1+
  definitions.py       # add schema defs, include members, expansion
  diagnostics.py       # classify schema diagnostics
  macros.py            # reserve/allow defschema at top level
  modules.py           # export/import schema bindings
  type_env.py          # reject schema names in type positions explicitly
```

Responsibilities:

- `definitions.py`
  - elaborate authored `defschema` forms;
  - parse `(:include SchemaName)` members;
  - build a schema catalog and expand concrete record/variant fields.
- `compiler.py`
  - sequence schema expansion between definition elaboration and downstream
    type-environment construction;
  - keep `compile_stage1_module(...)` and later compile stages deterministic.
- `modules.py`
  - track exported and imported schema bindings separately from type bindings;
  - resolve schema names for include members through the existing module scope.
- `macros.py`
  - treat `defschema` as a reserved top-level authored head;
  - allow macro-expanded `defschema` forms through the same top-level gate as
    the other definition forms.
- `type_env.py`
  - surface a dedicated diagnostic when a schema name is used where a type name
    is required.
- `diagnostics.py`
  - classify new schema diagnostics under the existing module/type passes
    instead of inventing a separate diagnostics channel.

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/workflows.py`
- `orchestrator/workflow_lisp/procedures.py`
- `orchestrator/workflow_lisp/lowering.py`
- shared validation/runtime modules under `orchestrator/workflow/`

## Data Model

### `SchemaDef` And Schema Members

Add one new top-level authored definition:

- `SchemaDef(name, members, span)`

Schema members use one shared authored-member vocabulary:

- `RecordField(name, type_name, span)`
- `SchemaInclude(schema_name, span)`

The same member vocabulary should be usable in:

- `defschema`
- `defrecord`
- `defunion` variant payloads

This keeps schema reuse one feature with one authored splice form instead of
separate record-only and variant-only rules.

### Draft Versus Expanded Definition Shapes

Do not force downstream stages to learn schema members. Keep the existing
concrete type definitions authoritative after one local expansion step.

Use two bounded layers inside `definitions.py`:

- authored layer:
  `SchemaDef`,
  authored record members,
  authored union-variant members;
- expanded layer:
  existing concrete `RecordDef.fields` and `UnionVariant.fields`.

`WorkflowLispModule` should grow a `schemas` collection for authored schema
metadata, while `definitions` continues to carry concrete expanded type
definitions used by `type_env.py`, workflow typing, and lowering.

### Schema Catalog And Expansion Trace

Add a frontend-local schema catalog:

- `SchemaCatalog(definitions_by_name, imported_bindings_by_name)`

Expansion should also preserve enough authored provenance for diagnostics:

- include span;
- included schema name;
- expansion stack for nested includes.

This does not require a new persisted build artifact. It is a frontend-local
trace used only to produce deterministic diagnostics and notes during
definition compilation.

## Elaboration And Expansion Pipeline

### Top-Level Admission

`defschema` becomes a first-class top-level definition head in the same places
that already recognize `defenum`, `defpath`, `defrecord`, and `defunion`:

- definition elaboration;
- macro reserved-head checking;
- Stage 1 definition-only filtering;
- module export/import scanning.

### Authored Shape

`defschema` syntax is:

```lisp
(defschema ReportTargets
  (execution-report-target Path.execution-report-target)
  (:include CommonTargets)
  (review-report-target Path.review-report-target))
```

Member rules:

- ordinary field members keep the existing `(field Type)` shape;
- include members are exactly `(:include SchemaName)`;
- no other keyword-headed schema member is valid in this slice.

### Expansion Order

Expansion is deterministic and left-to-right:

1. collect all local and imported schema definitions into `SchemaCatalog`;
2. expand each schema definition recursively into a concrete ordered field list;
3. expand each record and union variant by substituting included schema fields
   in authored order;
4. freeze concrete `RecordDef` and `UnionDef` values for downstream stages.

The expansion result is equivalent to textual field substitution, but the
implementation stays typed and span-aware.

### Import And Export Resolution

Schema names participate in module linking, but only in definition elaboration:

- exports may include schema names explicitly;
- imports may bring schema names into scope through alias or `:only` rules;
- schema bindings resolve through the existing module graph before later
  typechecking runs;
- schema bindings do not enter the value environment or workflow-boundary type
  catalog.

This keeps `defschema` aligned with the module slice without turning schemas
into runtime-visible values.

### Downstream Boundary

After expansion:

- `FrontendTypeEnvironment` continues to resolve only concrete types;
- workflow/procedure typing sees only ordinary concrete record and union field
  lists;
- contract lowering and workflow-boundary flattening remain unchanged;
- shared validation receives the same lowered surfaces it would have received
  if the repeated fields had been authored inline.

That is the key boundedness rule for this slice.

## Validation And Diagnostics

New or newly activated diagnostics in this slice:

- `schema_definition_invalid`
  - malformed `defschema` body or malformed `(:include ...)` member
- `schema_unknown`
  - include refers to no local or imported schema binding
- `schema_cycle`
  - recursive include chain
- `schema_field_duplicate`
  - duplicate field introduced while expanding one schema definition
- `schema_used_as_type`
  - schema name appears where a type name is required

Existing diagnostics reused:

- `definition_duplicate`
  - schema name collides with another top-level definition name
- `record_field_duplicate`
  - duplicate field introduced when a record or union variant expands included
    schema fields
- `module_export_missing`
  - exported schema name is absent
- `module_import_ambiguous`
  - imported schema binding is ambiguous

Classification rules:

- malformed schema syntax and namespace collisions stay in the existing module
  validation pass;
- `schema_used_as_type` stays in the existing type pass;
- no new shared-validation code is introduced because schema expansion is
  complete before lowering.

## Test Strategy

Add focused coverage in existing frontend suites:

- `tests/test_workflow_lisp_definitions.py`
  - valid schema definition elaboration
  - schema expansion inside records and union variants
  - duplicate-field and cycle failures
- `tests/test_workflow_lisp_modules.py`
  - export/import of schema bindings
  - ambiguous or missing imported schema bindings
- `tests/test_workflow_lisp_macros.py`
  - macro-emitted `defschema` admission and definition-only filtering
- `tests/test_workflow_lisp_workflows.py`
  - workflow typing remains transparent when record types were built from
    schemas rather than repeated inline fields

Add fixtures under `tests/fixtures/workflow_lisp/` for:

- one valid same-file schema reuse module;
- one valid cross-module schema import fixture;
- invalid unknown-schema, schema-cycle, and schema-used-as-type cases.

## Implementation Sequence

1. Extend top-level admission and authored definition parsing for `defschema`
   plus `(:include ...)` members.
2. Add `SchemaDef`, `SchemaInclude`, and schema-catalog expansion helpers in
   `definitions.py`.
3. Thread expanded concrete definitions plus authored schema metadata through
   `WorkflowLispModule` and the compiler entrypoints.
4. Extend module export/import resolution for schema bindings.
5. Add `schema_used_as_type` handling in `type_env.py`.
6. Add focused fixtures and tests for local, imported, and failure cases.

## Acceptance Conditions

This slice is complete when:

1. `defschema` is accepted as a top-level authored form.
2. `(:include SchemaName)` works in schemas, records, and union variants.
3. Schema reuse expands to deterministic concrete field lists before
   downstream typechecking.
4. Unknown schema names, cycles, duplicate fields, and schema-as-type misuse
   fail with source-mapped frontend diagnostics.
5. Imported schema bindings work through the existing module system.
6. Existing lowering and shared-validation behavior does not need schema-aware
   changes because only concrete records and unions leave the definition phase.

## Verification Plan

- `python -m pytest --collect-only tests/test_workflow_lisp_definitions.py tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_workflows.py -q`
- `python -m pytest tests/test_workflow_lisp_definitions.py -k 'defschema or schema' -q`
- `python -m pytest tests/test_workflow_lisp_modules.py -k 'schema' -q`
- `python -m pytest tests/test_workflow_lisp_macros.py -k 'defschema' -q`
- `python -m pytest tests/test_workflow_lisp_workflows.py -k 'schema' -q`
- `python -m orchestrator compile tests/fixtures/workflow_lisp/valid/defschema_workflow_inputs.orc --entry-workflow summarize`
