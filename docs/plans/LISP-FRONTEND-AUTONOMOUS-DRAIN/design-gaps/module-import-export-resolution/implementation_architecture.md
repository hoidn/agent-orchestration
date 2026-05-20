# Module Import Export Resolution Implementation Architecture

## Scope

This design gap covers only the bounded multi-file module/import/export layer
selected for the Workflow Lisp frontend:

- add an implementation-ready module declaration and top-level import/export
  directive surface for `.orc` files;
- resolve transitive `.orc` imports through deterministic module-name to
  filesystem mapping under compile-time source roots;
- validate export visibility, aliasing, `:only` imports, duplicate bindings,
  and cycle/ambiguity diagnostics;
- bind imported types, workflows, procedures, and macros into the existing
  staged frontend pipeline without bypassing typechecking or lowering;
- compile cross-module workflow calls through the existing imported-bundle and
  shared-validation seam rather than inventing a second runtime call surface;
- preserve source spans, form provenance, and module ownership in diagnostics
  and lowering-origin data.

Out of scope for this tranche:

- runtime execution changes, `WorkflowLoader` CLI entrypoints for `.orc`, or a
  second workflow executor;
- new standard-library forms, workflow-ref expansion beyond the already-owned
  Stage 6 surface, debug-YAML rendering, or broader Semantic IR redesign;
- redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog,
  SourceMap, pointer authority, variant proof, queue semantics, or runtime
  state persistence;
- report parsing, pointer-as-state, inline semantic shell/Python glue, or new
  command-adapter policy beyond reusing the existing contract;
- replacing the product design in
  `docs/design/workflow_lisp_frontend_specification.md`.

This is an implementation architecture for the selected module/import/export
gap only. It does not authorize widening the work into a general runtime
packaging redesign or a replacement syntax front end.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_frontend_specification.md`
  - `4. File Format And Module Form`
  - `6. Name Resolution`
  - `50. defworkflow Lowering`
  - `51. defproc Lowering`
  - `67. Frontend Parse/Module Errors`
  - `74. Source Map Requirements`
  - `94. Unit Tests`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `2. Relationship To The Full Specification`
  - deferred non-goals around modules/imports/exports
  - `14. Implementation Stages`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/steering.md`

The slice must also preserve the guardrails already established by the current
implementation and prior architecture documents:

- keep `orchestrator/workflow_lisp/` as the frontend-owned package and keep
  shared runtime semantics under `orchestrator/workflow/`;
- reuse the current staged pipeline:
  read -> syntax -> macro expansion -> definitions/procedures/workflows ->
  typecheck -> lowering -> shared validation;
- reuse `SourcePosition`, `SourceSpan`, recursive syntax provenance,
  `WorkflowLispModule`, `FrontendTypeEnvironment`, `EffectSummary`,
  `ExternEnvironment`, and `LoweringOriginMap` rather than inventing parallel
  tracking systems;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- preserve the current shared authored-mapping -> shared-validation bridge for
  lowered workflows instead of generating YAML text or a second validator;
- keep command-boundary classification unchanged for imported modules:
  imported `command-result` forms must still lower only through plain external
  tools or certified adapters.

`docs/design/workflow_command_adapter_contract.md` remains authoritative here
because module linking imports workflows and procedures that may already carry
`command-result` boundaries. This slice must transport those existing boundary
contracts across modules; it must not create a new loophole for hidden scripts,
inline semantic shell/Python glue, or module-loader-side state rewriting.

`docs/steering.md` is empty in this checkout. That is not permission to widen
scope. The selector bundle, architecture target contract, and prior
implementation architectures remain the effective local steering surfaces.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/hygienic-defmacro-system/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resource-drain-library/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/implementation_architecture.md`

### Decisions Reused

- Reuse the existing staged frontend pipeline and its package ownership split.
- Reuse the Stage 1-7 provenance substrate:
  `SourcePosition`,
  `SourceSpan`,
  recursive syntax objects,
  `LispFrontendDiagnostic`,
  macro expansion stacks,
  and `LoweringOriginMap`.
- Reuse `WorkflowLispModule`, `FrontendTypeEnvironment`, workflow/procedure
  catalogs, `ExternEnvironment`, and `EffectSummary` as the frontend-local
  authority surfaces instead of inventing module-specific parallel type or
  effect systems.
- Reuse Stage 3 and later lowering through the existing authored mapping ->
  `elaborate_surface_workflow(...)` -> `lower_surface_workflow(...)` shared
  seam.
- Reuse the existing imported-bundle runtime call surface for cross-module
  workflow calls instead of creating a new runtime import mechanism.
- Reuse the existing command-boundary classification and certified-adapter
  contract for imported `command-result` semantics.

### New Decisions In This Slice

- Add explicit frontend-owned module metadata, import directives, export
  directives, and a transitive module graph linker around the current
  single-file compilation pipeline.
- Keep the current `workflow-lisp` file root and add module directives inside
  it, rather than replacing the reader with a whole-file `defmodule` wrapper.
- Canonicalize every authored module identity to one slash-delimited internal
  module key, while accepting a narrow compatibility spelling for the full
  design's dotted `defmodule` examples.
- Introduce a dedicated module graph/catalog layer that owns:
  module-name resolution,
  cycle checks,
  export-surface validation,
  import alias scopes,
  and linked compilation order.
- Allow cross-module binding for types, macros, procedures, and workflows,
  with imported names available only through explicit `:only` imports or
  alias-qualified references.
- Normalize every imported procedure/workflow reference to a canonical
  module-aware callable key before typechecking and lowering, then bridge those
  keys into the existing flat workflow/procedure catalogs and
  `imported_workflow_bundles` seam.
- Keep cross-module workflow lowering on the current imported-bundle contract:
  imported `.orc` workflows compile to bundles that the caller sees through the
  same validation/runtime seam already used for imported workflows today.
- Treat cross-module macro use as a compile-time concern only:
  imported macros participate in expansion provenance and must resolve before
  later definition/workflow elaboration runs.

### Conflicts Or Revisions

The full specification's illustrative module wrapper uses:

```lisp
(defmodule neurips.implementation ...)
```

The current implemented frontend and all prior implementation slices instead
standardize on:

```lisp
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  ...)
```

This slice revises the implementation path narrowly:

- the file root stays `workflow-lisp`;
- module identity becomes a required top-level directive inside that root;
- import and export directives also remain ordinary top-level forms inside the
  existing root.

Reason:

- it preserves the current reader contract, syntax-object metadata, macro
  expansion flow, fixtures, and `compile_stage1_module(...)` /
  `compile_stage3_module(...)` compatibility;
- replacing the file root would reopen parser scope, fixture churn, and
  top-level form ownership far beyond the selected gap.

The Stage 3-7 slices also relied on two temporary assumptions because no
authored module system existed yet:

- same-file workflows were the only native `.orc` call targets;
- imported workflows entered through out-of-band imported-bundle registration.

This slice narrows those assumptions rather than discarding them:

- same-file call behavior remains valid;
- cross-module `.orc` calls now compile through linked imported bundles built
  by the frontend;
- explicitly supplied imported YAML bundles remain supported as migration debt
  and are not replaced by this slice.

The full specification's authored namespace examples are slightly mixed today:

- `defmodule` examples use dotted names such as `neurips.implementation`;
- `import` examples use slash-delimited module paths such as
  `neurips/implementation`;
- name-resolution examples use qualified references such as
  `implementation/run`.

This slice resolves that mismatch with one compatibility rule instead of
silently changing the language:

- the canonical internal module key is slash-delimited, for example
  `neurips/implementation`;
- `defmodule` and `import` accept either `neurips/implementation` or the
  compatibility spelling `neurips.implementation`;
- both spellings normalize to the same canonical key before path resolution,
  graph linking, export validation, type lookup, or lowering;
- mixed delimiter spellings such as `neurips.implementation/run` are rejected.

The current Stage 3 workflow-bundle seam is also flatter than the new authored
module surface. This slice resolves that mismatch by introducing canonical
frontend callable keys for exported procedures and workflows, then using those
keys as the only strings that cross into flat catalogs or imported-bundle
registries.

No prior slice is reversed on shared concepts such as spans, diagnostics, Core
Workflow AST, Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority,
or variant proof.

## Ownership Boundaries

This slice owns:

- module declaration, import, and export directive elaboration/validation;
- module-name to path resolution under configured source roots;
- transitive module graph discovery, duplicate-name checks, and cycle
  diagnostics;
- per-module export-surface derivation for types, macros, procedures, and
  workflows;
- import alias scopes and `:only` import binding for later typechecking and
  elaboration phases;
- linked macro import resolution and linked compile ordering;
- cross-module workflow/procedure/type lookup in the frontend catalogs and type
  environment;
- frontend-owned compilation APIs for linked entrypoint compilation while
  keeping existing single-file APIs stable;
- source provenance that includes both module name and module path in linked
  diagnostics and lowering-origin remaps;
- focused fixtures and tests for module graph behavior, ambiguity, cycles,
  imported macro expansion, imported procedure/workflow calls, and cross-module
  lowering.

This slice intentionally does not own:

- new runtime workflow loading semantics, new shared call-step semantics, or a
  second imported-workflow runtime substrate;
- redesign of shared validation/runtime modules under `orchestrator/workflow/`;
- standard-library phase/resource/drain semantics already owned by Stages 5-7;
- runtime-native promotion of adapters or any change to command-adapter
  certification policy;
- shared TypeCatalog, Semantic Workflow IR, SourceMap contract, pointer
  authority, variant proof, queue semantics, or state persistence.

## Proposed Package Boundary

Extend the existing frontend package with one dedicated module-linking layer
and narrow updates to existing compilation layers:

```text
orchestrator/workflow_lisp/
  __init__.py
  compiler.py              # add linked-entrypoint orchestration APIs
  definitions.py           # add module/import/export directive data
  diagnostics.py           # add module graph and ambiguity diagnostics
  lowering.py              # lower cross-module workflow calls via linked bundles
  macros.py                # import exported macros into expansion catalogs
  modules.py               # new module graph, resolver, export surfaces, linking
  procedures.py            # import-aware procedure lookup and signatures
  syntax.py                # parse module/import/export directives under workflow-lisp
  type_env.py              # import-aware type environments
  workflows.py             # import-aware workflow lookup and imported bundle wiring
```

Planned test and fixture surface:

```text
tests/
  test_workflow_lisp_modules.py
  test_workflow_lisp_macros.py
  test_workflow_lisp_procedures.py
  test_workflow_lisp_workflows.py
  test_workflow_lisp_lowering.py
  test_workflow_lisp_diagnostics.py
  fixtures/workflow_lisp/modules/valid/shared_types.orc
  fixtures/workflow_lisp/modules/valid/imported_macro.orc
  fixtures/workflow_lisp/modules/valid/imported_workflow_call.orc
  fixtures/workflow_lisp/modules/valid/imported_procedure_call.orc
  fixtures/workflow_lisp/modules/invalid/module_cycle_a.orc
  fixtures/workflow_lisp/modules/invalid/module_cycle_b.orc
  fixtures/workflow_lisp/modules/invalid/module_export_missing.orc
  fixtures/workflow_lisp/modules/invalid/module_import_ambiguous.orc
  fixtures/workflow_lisp/modules/invalid/module_path_mismatch.orc
```

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/spans.py`
- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/effects.py`
- `orchestrator/workflow_lisp/phase.py`
- `orchestrator/workflow_lisp/phase_stdlib.py`
- `orchestrator/workflow_lisp/resource.py`
- `orchestrator/workflow_lisp/resource_stdlib.py`
- `orchestrator/workflow_lisp/contracts.py`
- shared validation/runtime modules under `orchestrator/workflow/`

## Surface Syntax And Directive Model

### File Root

Keep the existing file root:

```lisp
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  ...)
```

Add three directive forms inside that root:

```lisp
(defmodule neurips/implementation)
(import neurips/types :as nt)
(export run ImplementationResult)
```

Directive rules:

- exactly one `defmodule` is required;
- `defmodule` must appear before any `import`, `export`, or executable
  top-level form;
- zero or more `import` forms may follow `defmodule`;
- zero or one `export` form may follow the imports;
- remaining forms are ordinary definitions, macros, procedures, or workflows;
- module directives are frontend-owned control forms and are not macro
  expandable in this tranche.

Keeping directives outside macro expansion avoids letting macro output redefine
module identity, source roots, or import topology.

### Module Names

The canonical internal module key is a slash-delimited path such as:

```text
neurips/implementation
std/paths
drain/gap_drafter
```

Authored compatibility contract:

- `defmodule` accepts either canonical slash form
  `neurips/implementation` or compatibility dotted form
  `neurips.implementation`;
- `import` targets accept the same two spellings and normalize them
  identically;
- both spellings normalize segment-by-segment to the canonical slash key before
  filesystem mapping or symbol binding;
- mixed-delimiter names, empty segments, doubled separators, or leading/trailing
  separators are rejected with a dedicated module-name diagnostic;
- all stored module graph keys, source-map module identities, export surfaces,
  imported workflow/procedure keys, and lowering-origin metadata use the
  normalized slash form only.

File-path mapping rule:

- each compile entrypoint accepts one or more source roots;
- canonical module key `a/b/c` resolves to `<source-root>/a/b/c.orc`;
- dotted authored spellings normalize to the same canonical path before
  matching;
- the declaring file's normalized `defmodule` key must match its resolved
  relative path;
- the first matching source root wins deterministically.

### Qualified Reference Spellings

This tranche supports three authored member-reference shapes, each normalized to
the same module/member binding record:

- local bare names such as `run` for current-module definitions;
- alias-qualified references such as `impl.run` for imported members reached
  through an explicit alias or default alias;
- compatibility direct-qualified symbols such as
  `neurips/implementation/run` when the referenced module is already imported.

Normalization rules:

- `impl.run` resolves through the importer's alias table to the exporting
  module's canonical slash key plus exported member name `run`;
- `neurips/implementation/run` resolves by splitting at the final `/`,
  interpreting the prefix as a canonical imported module key and the suffix as
  the exported member name;
- `:only` imports still allow bare imported names, but only after they
  normalize to the same canonical module/member binding;
- dotted full-module spellings such as `neurips.implementation.run` are
  rejected because `.` already carries field-access and alias-member meaning in
  the existing frontend;
- mixed spellings such as `neurips/implementation.run` are rejected.

The recommended authored style for new implementation fixtures is still
alias-qualified `impl.run`, because it fits the existing dotted field-access
surface and keeps direct module paths out of ordinary expressions. The direct
qualified symbol form remains supported only as a compatibility layer for the
full-spec examples.

## Import And Export Semantics

### Import Forms

Supported shapes:

```lisp
(import std/paths)
(import std/paths :as path)
(import neurips/types :only (ImplementationInputs ImplementationResult))
(import neurips/impl :as impl :only (run))
```

Import semantics:

- every import creates a module-alias binding;
- when `:as` is absent, the default alias is the final path segment:
  `neurips/types` -> `types`;
- `:only` narrows the imported member set to named exports;
- names listed in `:only` are also brought into the unqualified imported-name
  scope for that module;
- without `:only`, imported members are available only through the alias;
- re-exporting imported names is not supported in this tranche.

This keeps imports explicit and bounded while still allowing the full-design
authoring style where a few frequently used names can be imported unqualified.

### Export Form

Supported shape:

```lisp
(export
  ImplementationInputs
  ImplementationResult
  run)
```

Export semantics:

- exported names must resolve to locally defined types, macros, procedures, or
  workflows;
- unexported local names remain module-private;
- export lists must not reference imported names in this tranche;
- one spelling must resolve to exactly one exportable local symbol.

If an `export` name is missing or ambiguous, the compiler emits deterministic
module diagnostics instead of silently choosing a namespace.

## Data Model

### Syntax Layer

Extend `WorkflowLispSyntaxModule` with frontend-owned directive data:

- `module_name: str`
- `imports: tuple[ImportDirective, ...]`
- `exports: tuple[str, ...]`
- `forms: tuple[SyntaxNode, ...]`

New directive records:

- `ModuleDirective(name, span, form_path)`
- `ImportDirective(module_name, alias, only_names, span, form_path)`
- `ExportDirective(names, span, form_path)`

`syntax.py` remains responsible only for deterministic shape validation and
syntax-object wrapping. It does not resolve module graphs or symbol kinds.

### Definition And Catalog Layer

Extend `WorkflowLispModule` so later phases can reason about linked modules
without re-reading raw directives:

- `module_name`
- `imports`
- `exports`
- existing `definitions`

Add a new module-linking layer in `modules.py`:

- `ResolvedModuleSource(name, path, syntax_module, definition_module)`
- `ModuleExportSurface(types, macros, procedures, workflows)`
- `LinkedModuleGraph(entry_module, modules_by_name, topo_order)`
- `ModuleImportScope(alias_bindings, imported_name_bindings)`
- `ModuleMemberBinding(kind, module_name, member_name, canonical_key, source)`

Add one canonical flat-key encoding for exported procedures and workflows:

- canonical record shape:
  `(module_name=<canonical slash key>, member_name=<export name>)`
- canonical rendered string for flat catalog seams:
  `<canonical slash key>::<export name>`
- examples:
  `neurips/implementation::run`,
  `neurips/implementation::cleanup`,
  `neurips/types::ImplementationResult`

The export surface is frontend-local metadata. It does not redefine shared
TypeCatalog or runtime bundles; it only tells later frontend passes which local
symbols are visible to importers.

## Compilation Pipeline

Linked compilation becomes a thin graph wrapper around the existing staged
single-file compiler:

1. Read the entry file and collect its syntax directives.
2. Resolve transitive imports to source files under configured source roots.
3. Build a module graph and reject duplicate names or cycles.
4. Parse every discovered file into `WorkflowLispSyntaxModule`.
5. Collect local exportable declarations per module:
   types, macros, procedures, workflows.
6. Validate each module's `export` list against its local declarations.
7. Build per-module import scopes from dependency export surfaces.
8. Expand macros in topological order with imported macro bindings available.
9. Run the existing definition/procedure/workflow elaboration and typechecking
   per module, now with import-aware environments.
10. Lower workflows per module through the existing authored-mapping bridge.
11. Build linked imported bundles so cross-module calls reuse the current
   shared-validation/runtime seam.

Two API surfaces should coexist:

- keep `compile_stage1_module(path)` and `compile_stage3_module(path, ...)` as
  stable single-file wrappers for current tests and fixtures;
- add linked entrypoint APIs in `compiler.py`, such as
  `compile_stage1_entrypoint(...)` and `compile_stage3_entrypoint(...)`, that
  return linked graph metadata plus the compiled entry module.

The wrapper APIs may internally delegate to the linked-entrypoint path with a
single source root and no imports, but their return types should stay stable.

## Name Resolution Model

Resolution order remains compatible with the full specification and current
Stage 2 dotted-name behavior:

1. lexical bindings
2. local definitions in the current module
3. imported unqualified names introduced by `:only`
4. import aliases with member qualification
5. prelude symbols

Examples:

```text
ctx
selected.plan-path
nt.ImplementationResult
impl.run
path.execution-report
```

Resolver rules:

- if the first segment of a dotted symbol names a lexical value, treat it as
  field access, preserving current Stage 2 behavior;
- otherwise, if the first segment names an import alias, resolve it as
  `alias.member`;
- otherwise, if the symbol uses direct-qualified compatibility form
  `module/path/member`, normalize it to that imported module's canonical member
  binding;
- bare imported names exist only when introduced by `:only`;
- ambiguous bare imported names raise `module_import_ambiguous`;
- missing imported members raise `module_export_missing` against the exporting
  module surface, not a generic unknown-name error.

Namespace handling remains frontend-local and context-sensitive:

- type positions look up type exports;
- macro heads look up macro exports during expansion;
- bare call heads look up procedures in expression space;
- `call` callees look up exported workflows;
- successful imported procedure/workflow lookups always return the canonical
  flat callable key rather than the authored alias/member spelling.

This avoids inventing a new fully generic symbol table while still giving
cross-module binding a deterministic contract.

## Canonical Binding Keys And Flat Catalog Bridge

This slice keeps authored resolution module-aware while preserving the existing
flat workflow/procedure catalog seam.

Contract:

- module-aware authored references resolve first to a frontend-local
  `ModuleMemberBinding`;
- procedures and workflows then derive one canonical callable key string:
  `<module>::<member>`;
- local current-module references normalize to the current module's own
  canonical key, not to a globally bare name;
- `CallExpr.callee_name`, procedure-call callee names, workflow catalogs,
  procedure catalogs, lowered-callee tables, effect summaries, and
  `imported_workflow_bundles` all use that canonical key string once
  resolution has finished;
- authored spellings such as `run`, `impl.run`, and
  `neurips/implementation/run` are preserved only for diagnostics and
  source-remapping context.

Collision policy:

- local duplicate definitions in one module remain ordinary duplicate-definition
  errors;
- two modules may both export `run`, because their canonical keys differ, for
  example `neurips/implementation::run` and `std/tasks::run`;
- ambiguity arises only when an importer tries to expose both as the same bare
  authored name through `:only` or conflicting aliases, and that fails before
  lowering;
- an imported YAML bundle key that collides with an `.orc`-generated canonical
  callable key is rejected as a deterministic import collision instead of
  silently shadowing either source.

Bundle registration policy:

- each exported workflow from a compiled `.orc` module materializes its own
  `LoadedWorkflowBundle`;
- one module exporting multiple workflows therefore contributes multiple flat
  imported-bundle entries, one per canonical workflow key;
- imported procedure signatures use the same canonical key bridge, but remain
  frontend-local and never materialize runtime bundles;
- shared validation/runtime continue to receive a flat imported-bundle mapping,
  but the keys are now canonical callable keys rather than ambiguous authored
  aliases.

## Macro, Procedure, And Workflow Linking

### Imported Macros

Imported macros must resolve before ordinary elaboration. The linker therefore
provides an imported macro catalog to `macros.py` in dependency order.

Rules:

- imported macros must be exported by the dependency module;
- imported macros participate in the same hygiene and expansion provenance
  model as same-file macros;
- macro expansion cannot mutate module/import/export directives.

### Imported Procedures

Procedures remain compile-time/internal behavior rather than runtime workflow
boundaries.

Rules:

- imported procedures must be explicitly exported;
- bare procedure-call heads may resolve through `:only`;
- alias-qualified procedure calls use `alias.proc`;
- direct compatibility references such as `module/path/proc` normalize to the
  same imported procedure key only if that module was imported explicitly;
- every resolved imported procedure call stores the canonical key
  `<module>::<proc>` in the typed expression and effect summary;
- procedure effect summaries continue to compose through the existing
  `EffectSummary` model.

### Imported Workflows

Cross-module workflow calls remain on the existing workflow-boundary contract.

Rules:

- imported workflows must be explicitly exported;
- `call` resolves imported workflows through the linked workflow catalog;
- every resolved imported workflow call stores the canonical key
  `<module>::<workflow>`;
- the lowering path still emits imported bundles and ordinary call-step
  lowering understood by shared validation/runtime;
- one exporting module may contribute multiple imported workflow bundles, one
  for each exported workflow canonical key;
- migration-era imported YAML bundles remain valid explicit dependencies and
  share the same imported-workflow catalog surface.

This keeps the module slice compatible with the Stage 3-7 lowering work rather
than replacing it.

## Lowering And Shared Handoff

This slice does not introduce a new lowerer. It extends the existing lowering
bridge with linked module metadata:

- generated workflow identities and private procedure names include canonical
  module names to avoid collisions across files;
- lowering-origin data stores both module path and module name so imported-call
  validation failures remap cleanly;
- imported `.orc` workflows compile to validated bundles before the caller's
  lowering context wires them into `imported_bundles`, keyed by
  `<module>::<workflow>`;
- alias-qualified and direct-qualified authored references both lower through
  the same canonical callable key, so the Stage 3 flat `lowered_callees` and
  `call` surfaces never need to reason about module syntax directly;
- workflow-call boundary checks remain those already owned by `workflows.py`
  and shared validation.

No shared runtime or Core Workflow AST concept is redefined here.

## Diagnostics

Required module-focused diagnostics:

- `module_not_found`
- `module_cycle`
- `module_export_missing`
- `module_import_ambiguous`
- `module_path_mismatch`
- `module_declaration_missing`
- `module_name_invalid`
- `module_reference_invalid`
- `module_alias_duplicate`
- `module_export_duplicate`
- `module_import_collision`

Diagnostic requirements:

- point at the authored import/export/directive span, not only the dependent
  file path;
- include both importing module and imported module names where relevant;
- preserve expansion provenance when the failing use site came from an imported
  macro;
- keep existing typed frontend diagnostics as the only user-visible error
  channel.

## Test Strategy

Add one dedicated module-linking regression file and extend focused existing
frontend suites:

- `tests/test_workflow_lisp_modules.py`
  - module path resolution
  - default aliasing
  - `:only` binding
  - export validation
  - cycle rejection
  - ambiguous import rejection
- `tests/test_workflow_lisp_macros.py`
  - imported macro expansion
  - imported macro provenance and hygiene
- `tests/test_workflow_lisp_procedures.py`
  - imported procedure signatures
  - effect propagation across modules
- `tests/test_workflow_lisp_workflows.py`
  - imported workflow signature registration
  - cross-module `call` validation
  - multi-export module registration under distinct canonical workflow keys
- `tests/test_workflow_lisp_lowering.py`
  - linked imported-bundle lowering
  - alias-qualified and direct-qualified authored references lowering to the
    same canonical callable key
  - cross-module origin remapping
- `tests/test_workflow_lisp_diagnostics.py`
  - module-specific diagnostic rendering
  - module-name and imported-bundle collision diagnostics

Fixture strategy:

- keep multi-file fixtures under `tests/fixtures/workflow_lisp/modules/`;
- use tiny two- or three-file graphs so failures isolate one module rule at a
  time;
- include one graph where module `a` exports two workflows and module `b`
  exports another workflow with one conflicting bare export name, proving:
  - the importer sees distinct canonical keys for `a`'s two workflows;
  - alias-qualified calls remain unambiguous;
  - conflicting `:only` exposure fails deterministically with
    `module_import_ambiguous` or `module_import_collision`;
- include at least one fixture where an imported `.orc` workflow and an
  out-of-band imported YAML bundle coexist, proving the new module layer does
  not break the existing migration seam.

## Implementation Sequence

1. Add syntax and directive dataclasses for `defmodule`, `import`, and
   `export`.
2. Add `modules.py` with source-root resolution, graph discovery, and export
   surface validation.
3. Extend `WorkflowLispModule` and `FrontendTypeEnvironment` with import-aware
   metadata.
4. Extend macro collection/expansion to accept imported macro bindings.
5. Extend procedure/workflow catalogs with imported exported-symbol lookup.
6. Add linked-entrypoint compiler APIs while keeping existing single-file APIs
   stable.
7. Extend lowering to materialize linked imported `.orc` workflow bundles
   under canonical callable keys and preserve module-aware origin remapping.
8. Add focused module fixtures and regression tests, then rerun affected
   workflow/procedure/macro/lowering suites.

## Acceptance Conditions

This slice is complete when:

- an entry `.orc` file can import transitive `.orc` dependencies through
  deterministic source-root mapping;
- the implementation accepts the selected compatibility spellings for
  `defmodule`, `import`, and direct-qualified member references, then
  normalizes them deterministically to one canonical module key;
- imports and exports work for types, macros, procedures, and workflows with
  explicit aliasing and `:only` narrowing;
- module cycles and ambiguous imports fail with deterministic typed
  diagnostics;
- imported procedures and workflows typecheck through existing frontend-local
  catalogs without redefining shared TypeCatalog or runtime semantics;
- cross-module workflow calls lower through the existing imported-bundle and
  shared-validation seam using canonical flat callable keys, including modules
  that export multiple workflows;
- imported macros preserve hygiene and source provenance across module
  boundaries;
- the single-file compile APIs still behave as before on existing fixtures.

## Verification Plan

Deterministic implementation checks for this slice should be written to:

- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/7/design-gap-architect/check_commands.json`

Minimum expected coverage:

- collect-only for any new module-linking test file;
- the dedicated module-linking test file itself;
- focused macro, procedure, workflow, lowering, and diagnostic suites affected
  by cross-module binding;
- one scenario covering a module that exports multiple workflows plus another
  module that exports a conflicting workflow name, proving canonical key
  registration and deterministic ambiguity diagnostics;
- shared-validation coverage for at least one imported `.orc` workflow call.
