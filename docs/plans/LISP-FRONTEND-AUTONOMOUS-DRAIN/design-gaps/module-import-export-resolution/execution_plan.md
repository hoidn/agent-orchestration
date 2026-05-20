# Module Import Export Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the bounded Workflow Lisp multi-file module/import/export layer so `.orc` modules can declare identity, import exported types/macros/procedures/workflows, and lower cross-module workflow calls through the existing imported-bundle and shared-validation seam.

**Architecture:** Add one frontend-owned module-linking layer around the current single-file Stage 1-7 compiler. Keep the `workflow-lisp` root form, parse `defmodule` / `import` / `export` as top-level directives, resolve transitive source graphs under explicit source roots, normalize authored module/member spellings to canonical slash-delimited module keys plus flat callable keys `<module>::<member>`, and feed import-aware macro/type/procedure/workflow catalogs into the existing typing and lowering path. Runtime semantics, shared validation, imported bundle execution, pointer authority, and command-adapter rules remain owned by `orchestrator/workflow/`.

**Tech Stack:** Python 3, dataclasses, `pathlib.Path`, the existing `orchestrator.workflow_lisp` compiler/typecheck/lowering modules, `orchestrator.workflow.loaded_bundle.LoadedWorkflowBundle`, pytest, and `.orc` fixture graphs under `tests/fixtures/workflow_lisp/modules/`.

---

## Fixed Inputs

Treat these as the implementation authority for this slice:

- `docs/index.md`
- `docs/steering.md`
  - currently empty in this checkout; do not treat that as permission to widen scope
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `0. Prerequisites, Boundaries, And Missing Internal Specs`
  - `4. File Format And Module Form`
  - `6. Name Resolution`
  - `32-37` macro and provenance constraints
  - `50. defworkflow Lowering`
  - `51. defproc Lowering`
  - `67. Frontend Parse/Module Errors`
  - `74. Source Map Requirements`
  - `94. Unit Tests`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `2. Relationship To The Full Specification`
  - `3. Non-Goals`
  - `4.1 File Form`
  - `4.2 Definitions`
  - `6. Lowering Contract`
  - `14. Implementation Stages`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/module-import-export-resolution/implementation_architecture.md`
- `artifacts/review/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/module-import-export-resolution/architecture-review.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/7/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/7/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`
  - currently `{"ledger_version":1,"events":[]}`; there is no prior execution history to reconcile for this gap

## Hard Scope Limits

Implement only the bounded module/import/export slice selected in the work-item context:

- `workflow-lisp` root directives `defmodule`, `import`, and `export`
- deterministic module-name to file resolution under explicit source roots
- compatibility normalization for dotted versus slash-authored module names and direct-qualified member references
- export validation, alias binding, `:only` binding, duplicate binding detection, ambiguity detection, and cycle diagnostics
- imported macro, procedure, type, and workflow binding
- linked-entrypoint compile APIs that preserve current `compile_stage1_module(...)` and `compile_stage3_module(...)` wrappers
- linked lowering of imported `.orc` workflows through the existing `imported_workflow_bundles` seam
- canonical flat callable keys for imported procedures and workflows

Explicit non-goals:

- no runtime execution redesign, new `.orc` loader entrypoints, or second executor
- no new stdlib forms, no workflow-ref redesign beyond the current Stage 6 surface, and no debug-YAML work
- no redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, variant proof, queue semantics, or runtime state
- no new command adapters, no inline semantic shell/Python glue, no report parsing, and no runtime-native effect promotion
- no re-export of imported names in this tranche
- no SCC-aware recursive linker; cycles fail deterministically

## Current Baseline

The implementation must extend the repo as it exists now:

- `orchestrator/workflow_lisp/compiler.py` exposes only single-file `compile_stage1_module(path)` and `compile_stage3_module(path, ...)`.
- `orchestrator/workflow_lisp/syntax.py` validates only the `workflow-lisp` header plus ordinary top-level forms; it has no module/import/export directive model.
- `orchestrator/workflow_lisp/definitions.py` emits `WorkflowLispModule(language_version, target_dsl_version, definitions, span)` with no module metadata.
- `orchestrator/workflow_lisp/macros.py` collects and expands same-file macros only.
- `orchestrator/workflow_lisp/type_env.py` resolves prelude and same-file types only.
- `orchestrator/workflow_lisp/procedures.py` and `orchestrator/workflow_lisp/workflows.py` build same-file catalogs and accept externally supplied imported bundles, but they do not own a module graph or canonical module-aware callable keys.
- `orchestrator/workflow_lisp/lowering.py` already lowers workflow calls through flat `imported_workflow_bundles`, which is the seam this slice must reuse instead of replacing.
- `tests/test_workflow_lisp_modules.py` does not exist yet.

## File Ownership

Create:

- `orchestrator/workflow_lisp/modules.py`
- `tests/test_workflow_lisp_modules.py`
- fixture graphs under `tests/fixtures/workflow_lisp/modules/valid/`
- fixture graphs under `tests/fixtures/workflow_lisp/modules/invalid/`

Modify:

- `orchestrator/workflow_lisp/__init__.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/macros.py`
- `orchestrator/workflow_lisp/procedures.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/workflows.py`
- `tests/test_workflow_lisp_diagnostics.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_macros.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_workflows.py`

Modify only if a focused failing test proves the module layer cannot preserve existing contracts without it:

- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `tests/test_workflow_lisp_expressions.py`

Reuse without broadening ownership:

- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/spans.py`
- `orchestrator/workflow_lisp/phase.py`
- `orchestrator/workflow_lisp/phase_stdlib.py`
- `orchestrator/workflow_lisp/resource.py`
- `orchestrator/workflow_lisp/resource_stdlib.py`
- shared runtime/validation modules under `orchestrator/workflow/`

## Locked Contracts

Do not re-decide these during implementation.

Directive surface:

```lisp
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule neurips/implementation)
  (import neurips/types :as nt)
  (import neurips/shared :only (ImplementationInputs))
  (export run ImplementationResult)
  ...)
```

Rules:

- exactly one `defmodule` is required
- `defmodule` must appear before `import`, `export`, or ordinary definitions
- zero or more `import` directives may follow `defmodule`
- zero or one `export` directive may follow imports
- module directives are frontend-owned and are not macro-expandable

Module normalization contract:

- canonical stored module key: slash-delimited, for example `neurips/implementation`
- accepted authored spellings for `defmodule` and `import`: `neurips/implementation` and compatibility `neurips.implementation`
- mixed delimiter spellings, empty segments, doubled separators, or leading/trailing separators fail with `module_name_invalid`
- direct-qualified compatibility member references use `module/path/member`
- authored alias-qualified references use `alias.member`
- dotted full-module spellings like `neurips.implementation.run` remain invalid

Import/export contract:

- every import creates an alias binding
- missing `:as` defaults to the final module-path segment
- `:only` narrows imported members and also introduces those members into unqualified imported-name scope
- without `:only`, imported members are available only through alias qualification
- export lists may name only locally defined types, macros, procedures, and workflows
- re-exporting imported names is not supported in this slice

Canonical binding contract:

- exported procedure and workflow keys lower to `<module>::<member>`
- examples: `neurips/implementation::run`, `neurips/implementation::cleanup`
- local current-module procedures/workflows also normalize to canonical keys before they enter flat catalogs
- authored spellings remain only for diagnostics and source remapping

Linked compile API contract:

```python
def compile_stage1_entrypoint(
    path: Path,
    *,
    source_roots: tuple[Path, ...] | None = None,
) -> LinkedStage1CompileResult: ...


def compile_stage3_entrypoint(
    path: Path,
    *,
    source_roots: tuple[Path, ...] | None = None,
    provider_externs: Mapping[str, str] | None = None,
    prompt_externs: Mapping[str, str] | None = None,
    imported_workflow_bundles: Mapping[str, LoadedWorkflowBundle] | None = None,
    command_boundaries: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding] | None = None,
    validate_shared: bool = True,
    workspace_root: Path | None = None,
) -> LinkedStage3CompileResult: ...
```

Result-shape contract:

- linked results must expose the linked graph plus the compiled entry module/result
- existing `compile_stage1_module(...)` and `compile_stage3_module(...)` must keep their current return types and remain valid for single-file fixtures

Required diagnostics:

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

## Task 1: Lock Multi-File Fixture Graphs And Failing Tests

**Files:**

- Create: `tests/test_workflow_lisp_modules.py`
- Create: fixture graphs under `tests/fixtures/workflow_lisp/modules/valid/`
- Create: fixture graphs under `tests/fixtures/workflow_lisp/modules/invalid/`
- Modify: `tests/test_workflow_lisp_macros.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_workflows.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_diagnostics.py`

- [ ] **Step 1: Create the fixture graphs that pin each module contract**

Add small two- or three-file graphs that each prove one rule:

- valid path-matched module declaration
- default alias binding
- `:only` binding and bare imported-name access
- imported macro expansion
- imported procedure call
- imported workflow call
- one module exporting multiple workflows
- one graph where an imported `.orc` workflow and an explicit imported YAML bundle coexist
- invalid cycle
- invalid missing export
- invalid ambiguous imported bare name
- invalid declaring-file path mismatch

- [ ] **Step 2: Add failing tests before implementation**

In `tests/test_workflow_lisp_modules.py`, add focused tests for:

- source-root resolution and module-path matching
- default aliasing and `:only` behavior
- export-surface validation
- duplicate alias rejection distinct from imported-bundle key collisions
- cycle rejection
- ambiguity rejection
- canonical `<module>::<member>` key registration
- linked entrypoint API wrapper behavior

Augment existing suites with cross-module assertions:

- `tests/test_workflow_lisp_macros.py`: imported macro catalog, provenance, hygiene
- `tests/test_workflow_lisp_procedures.py`: imported procedure signature lookup and effect propagation
- `tests/test_workflow_lisp_workflows.py`: imported workflow signature registration and cross-module `call`
- `tests/test_workflow_lisp_lowering.py`: canonical key lowering and imported bundle registration
- `tests/test_workflow_lisp_diagnostics.py`: rendered module-specific diagnostics

- [ ] **Step 3: Run collect-only to verify selectors and names**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_diagnostics.py -q
```

Expected:

- collection succeeds
- the new module-linking test file appears
- implementation tests still fail because module support is not built yet

- [ ] **Step 4: Commit the test/fixture scaffold**

```bash
git add tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_diagnostics.py tests/fixtures/workflow_lisp/modules
git commit -m "test: pin workflow lisp module linking behavior"
```

## Task 2: Add Directive Parsing, Metadata, And Graph Resolution

**Files:**

- Create: `orchestrator/workflow_lisp/modules.py`
- Modify: `orchestrator/workflow_lisp/syntax.py`
- Modify: `orchestrator/workflow_lisp/definitions.py`
- Modify: `orchestrator/workflow_lisp/diagnostics.py`
- Modify: `orchestrator/workflow_lisp/__init__.py`

- [ ] **Step 1: Extend the syntax layer with directive records and ordering checks**

Add frontend-owned directive data in `syntax.py`:

- `ModuleDirective`
- `ImportDirective`
- `ExportDirective`
- `WorkflowLispSyntaxModule.module_name`
- `WorkflowLispSyntaxModule.imports`
- `WorkflowLispSyntaxModule.exports`

Validate:

- one required `defmodule`
- directive ordering
- accepted `import` options `:as` and `:only`
- deterministic module-name normalization and rejection of invalid spellings

- [ ] **Step 2: Extend `WorkflowLispModule` with imported/exported metadata**

In `definitions.py`, carry forward:

- `module_name`
- `imports`
- `exports`

Keep existing definition elaboration behavior unchanged for ordinary `defenum`, `defpath`, `defrecord`, and `defunion`.

- [ ] **Step 3: Implement the module graph/linker in `modules.py`**

Add dataclasses and helpers for:

- source-root resolution
- canonical module-name normalization
- `ResolvedModuleSource`
- `ModuleExportSurface`
- `ModuleMemberBinding`
- `ModuleImportScope`
- `LinkedModuleGraph`

Implement deterministic graph discovery, duplicate-name detection, cycle detection, and path mismatch validation.

- [ ] **Step 4: Run the dedicated module tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_modules.py -q
```

Expected:

- syntax and graph-resolution tests pass
- later cross-module macro/procedure/workflow tests still fail until import-aware catalogs exist

- [ ] **Step 5: Commit the directive and linker layer**

```bash
git add orchestrator/workflow_lisp/syntax.py orchestrator/workflow_lisp/definitions.py orchestrator/workflow_lisp/diagnostics.py orchestrator/workflow_lisp/modules.py orchestrator/workflow_lisp/__init__.py
git commit -m "feat: add workflow lisp module directives and graph linker"
```

## Task 3: Add Linked Entrypoint Compiler APIs While Preserving Single-File Wrappers

**Files:**

- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/modules.py`
- Modify: `orchestrator/workflow_lisp/__init__.py`

- [ ] **Step 1: Introduce linked result dataclasses and entrypoint APIs**

Add linked compile result dataclasses that expose:

- the `LinkedModuleGraph`
- the compiled entry module/result
- per-module compiled results
- flat validated workflow bundles keyed by canonical callable key

Add `compile_stage1_entrypoint(...)` and `compile_stage3_entrypoint(...)` using explicit `source_roots`.

- [ ] **Step 2: Delegate legacy wrappers through the linked path without changing their return types**

Keep:

- `compile_stage1_module(path) -> WorkflowLispModule`
- `compile_stage3_module(path, ...) -> Stage3CompileResult`

Implement wrapper delegation with a single source root and no authored imports so current fixtures keep passing untouched.

- [ ] **Step 3: Build the topological compile orchestration**

The linked compile path must:

1. read the entry syntax module
2. resolve transitive imports
3. build the graph
4. compute local exportable declarations per module
5. validate export surfaces before downstream elaboration
6. compile modules in dependency order

- [ ] **Step 4: Run focused wrapper and module tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_workflows.py -q
```

Expected:

- linked entrypoint API tests pass
- single-file workflow tests still pass
- imported macro/procedure/lowering tests may still fail until later tasks land

- [ ] **Step 5: Commit the compiler entrypoint work**

```bash
git add orchestrator/workflow_lisp/compiler.py orchestrator/workflow_lisp/modules.py orchestrator/workflow_lisp/__init__.py
git commit -m "feat: add linked workflow lisp compile entrypoints"
```

## Task 4: Make Type And Macro Resolution Import-Aware

**Files:**

- Modify: `orchestrator/workflow_lisp/type_env.py`
- Modify: `orchestrator/workflow_lisp/macros.py`
- Modify: `orchestrator/workflow_lisp/modules.py`
- Modify: `tests/test_workflow_lisp_macros.py`
- Modify: `tests/test_workflow_lisp_modules.py`

- [ ] **Step 1: Extend the type environment with import-scope lookups**

Teach `FrontendTypeEnvironment` or a linked wrapper around it to resolve:

- local type definitions first
- imported unqualified names introduced by `:only`
- alias-qualified imported type names
- direct-qualified compatibility names only when that module was explicitly imported
- prelude names last

Do not redefine shared TypeCatalog behavior; this is frontend-only name resolution.

- [ ] **Step 2: Merge imported macro exports into the expansion catalog**

Allow `macros.py` to receive imported exported macros from dependency modules in topological order. Keep the same hygiene and expansion provenance model, and reject macro output that tries to synthesize or mutate `defmodule`, `import`, or `export`.

- [ ] **Step 3: Preserve authored dotted field access semantics**

Do not break the existing distinction between:

- lexical dotted field access such as `selected.report.path`
- alias-qualified imported members such as `impl.run`

If the current resolver cannot preserve that boundary through module-layer lookup alone, stop and add only the minimum targeted normalization proven by failing tests.

- [ ] **Step 4: Run macro and module tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_modules.py -q
```

Expected:

- imported macro tests pass
- same-file macro tests still pass
- type import cases in the module suite pass

- [ ] **Step 5: Commit the import-aware type/macro resolution**

```bash
git add orchestrator/workflow_lisp/type_env.py orchestrator/workflow_lisp/macros.py orchestrator/workflow_lisp/modules.py tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_modules.py
git commit -m "feat: resolve imported workflow lisp types and macros"
```

## Task 5: Register Imported Procedures And Workflows Under Canonical Callable Keys

**Files:**

- Modify: `orchestrator/workflow_lisp/procedures.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `orchestrator/workflow_lisp/modules.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_workflows.py`
- Modify: `tests/test_workflow_lisp_modules.py`

- [ ] **Step 1: Build import-aware member bindings for procedures and workflows**

Use `ModuleImportScope` plus export surfaces to resolve imported members context-sensitively:

- type positions -> exported types
- procedure-call heads -> exported procedures
- `(call ...)` callees -> exported workflows

Successful procedure/workflow lookups must normalize to canonical callable keys `<module>::<member>`.

- [ ] **Step 2: Keep ambiguity and collision checks deterministic**

Reject:

- missing exported members with `module_export_missing`
- conflicting bare imported names with `module_import_ambiguous`
- duplicate import aliases with `module_alias_duplicate`
- canonical imported-bundle key collisions with `module_import_collision`

Do not silently shadow imported YAML bundles or `.orc`-generated workflow keys.

- [ ] **Step 3: Preserve current single-file behavior while extending linked catalogs**

Local same-file definitions must continue to work with current tests. Linked catalogs should add imported exported members without changing the current authored workflow surface.

- [ ] **Step 4: Run procedure and workflow suites**

Run:

```bash
python -m pytest tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_workflows.py -q
```

Expected:

- imported procedure and workflow registration tests pass
- same-file procedure/workflow regression tests continue to pass

- [ ] **Step 5: Commit the canonical catalog bridge**

```bash
git add orchestrator/workflow_lisp/procedures.py orchestrator/workflow_lisp/workflows.py orchestrator/workflow_lisp/modules.py orchestrator/workflow_lisp/compiler.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_modules.py
git commit -m "feat: register imported callables with canonical module keys"
```

## Task 6: Lower Linked Imported Workflows Through The Existing Bundle Seam

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `orchestrator/workflow_lisp/diagnostics.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_diagnostics.py`

- [ ] **Step 1: Materialize one imported bundle per exported workflow canonical key**

Compile imported `.orc` workflow exports to validated `LoadedWorkflowBundle` objects before lowering callers, and inject them into the caller's flat imported-bundle map using canonical keys.

- [ ] **Step 2: Keep lowering origin and generated names module-aware**

Extend lowering metadata so:

- generated workflow/private procedure identities include canonical module names when needed to avoid cross-file collisions
- source remapping preserves both module path and module name
- imported macro provenance still appears on downstream errors

- [ ] **Step 3: Keep the shared-validation seam authoritative**

Do not add a second lowerer or runtime path. Cross-module workflow calls must still lower to ordinary `call` steps and validate through the same shared workflow machinery already used for imported bundles today.

- [ ] **Step 4: Run lowering and diagnostics suites**

Run:

```bash
python -m pytest tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_diagnostics.py -q
```

Expected:

- alias-qualified and direct-qualified authored references lower to the same canonical callable key
- cross-module origin remapping is stable
- imported workflow shared-validation cases pass

- [ ] **Step 5: Commit the lowering bridge**

```bash
git add orchestrator/workflow_lisp/lowering.py orchestrator/workflow_lisp/compiler.py orchestrator/workflow_lisp/workflows.py orchestrator/workflow_lisp/diagnostics.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_diagnostics.py
git commit -m "feat: lower imported workflow lisp modules through bundle seam"
```

## Task 7: Run The Recorded Verification Set And Capture Final Evidence

**Files:**

- Modify: `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/7/design-gap-architect/check_commands.json`
  - only if the checked-in commands need to be updated to match the final selectors

- [ ] **Step 1: Verify collect-only coverage for the final selector set**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_diagnostics.py -q
```

Expected:

- all expected tests collect successfully

- [ ] **Step 2: Run the focused module suite**

Run:

```bash
python -m pytest tests/test_workflow_lisp_modules.py -q
```

Expected:

- PASS

- [ ] **Step 3: Run the cross-module workflow/lowering suite**

Run:

```bash
python -m pytest tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_lowering.py -q
```

Expected:

- PASS

- [ ] **Step 4: Run the macro/procedure/diagnostic regression suite**

Run:

```bash
python -m pytest tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_diagnostics.py -q
```

Expected:

- PASS

- [ ] **Step 5: Update `check_commands.json` only if needed, then commit**

```bash
git add state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/7/design-gap-architect/check_commands.json
git commit -m "chore: record module import export verification commands"
```

Skip this commit if the command file did not change.

## Acceptance Conditions

This slice is complete when:

- an entry `.orc` file can resolve transitive imports under explicit source roots
- `defmodule`, `import`, and `export` work inside the existing `workflow-lisp` root without replacing the reader root form
- dotted and slash authored module spellings normalize deterministically to one canonical slash key
- imports/exports work for types, macros, procedures, and workflows with explicit aliasing and `:only` narrowing
- module cycles, path mismatches, missing exports, ambiguous bare imports, and imported-bundle collisions fail with deterministic typed diagnostics
- imported procedures and workflows normalize to canonical callable keys `<module>::<member>`
- cross-module workflow calls lower through the current `imported_workflow_bundles` and shared-validation seam, including a module that exports multiple workflows
- imported macros preserve hygiene and provenance across module boundaries
- legacy single-file compile wrappers still behave as before on existing fixtures

## Verification Plan

The minimum command set for this slice is the one already recorded in:

- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/7/design-gap-architect/check_commands.json`

The final implementation must leave fresh evidence for:

- collect-only coverage of the new module-linking selectors
- the dedicated module-linking test file
- cross-module workflow and lowering tests
- macro, procedure, and diagnostic regressions affected by imported bindings
- at least one shared-validation scenario for an imported `.orc` workflow call
- at least one graph where one module exports multiple workflows and another module exports a conflicting workflow name, proving distinct canonical registration and deterministic ambiguity handling
