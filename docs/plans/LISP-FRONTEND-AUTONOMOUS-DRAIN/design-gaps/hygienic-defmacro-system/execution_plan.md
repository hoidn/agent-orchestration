# Hygienic `defmacro` System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add same-file hygienic user-defined `defmacro` support to the existing Workflow Lisp Stage 1-4 pipeline so macro-expanded `.orc` modules compile through the current typecheck, lowering, and shared-validation path without semantic bypasses.

**Architecture:** Keep all new ownership inside `orchestrator/workflow_lisp/`. Insert one frontend-only macro pass between `build_syntax_module()` and the current definition/workflow elaborators: recursive syntax objects carry spans plus expansion provenance, a same-file macro catalog is built before ordinary elaboration, macro calls expand hygienically by deterministic identifier renaming, and only ordinary expanded syntax reaches the existing Stage 1-4 semantics. Lowering and shared validation remain authoritative after expansion; generated nodes keep macro call provenance so downstream failures still point back to authored call sites.

**Tech Stack:** Python 3, dataclasses, the existing `orchestrator.workflow_lisp` Stage 1-4 compiler modules, pytest, `.orc` fixtures under `tests/fixtures/workflow_lisp/`, and the deterministic verification commands stored in `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/2/design-gap-architect/check_commands.json`.

---

## Fixed Inputs

Treat these as the implementation authority for this slice:

- `docs/index.md`
- `docs/steering.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `8.7 defmacro`
  - `32. Macro Phases`
  - `33. Syntax Objects`
  - `34. Hygiene`
  - `35. Macro Determinism`
  - `36. Macro Outputs`
  - `37. Macro Error Model`
  - `41. Syntax AST`
  - `42. Resolved Frontend AST`
  - `43. Expanded Frontend AST`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `2. Relationship To The Full Specification`
  - `3. Non-Goals`
  - `14. Implementation Stages`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/hygienic-defmacro-system/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/2/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/2/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

## Hard Scope Limits

Implement only the bounded hygienic user-macro slice from the work-item context:

- same-file top-level `defmacro` definition parsing and validation;
- same-file macro catalog collection before ordinary definition/workflow elaboration so forward references work;
- recursive hygienic expansion of user macro calls into ordinary frontend syntax;
- deterministic introduced-identifier generation and reuse without a new downstream scope engine;
- recursive syntax metadata carrying span, display spelling, resolved spelling, and expansion provenance;
- macro-aware diagnostics for arity problems, bad splices/templates, reserved heads, cycles, and malformed expansion output;
- post-expansion handoff into the existing definition, typing, lowering, and shared-validation pipeline;
- regression coverage proving current workflow, structured-result, lowering, and first-phase translation slices still pass after the macro pass is inserted.

Explicit non-goals:

- no `defproc`, `defun`, compile-time evaluator, or typed-macro system;
- no modules/imports/exports or cross-file macro libraries;
- no intentional capture forms such as `bind-as`;
- no loader/CLI integration, runtime execution changes, executable-IR work, or shared runtime redesign;
- no new Core Workflow AST, Semantic Workflow IR, TypeCatalog, SourceMap, pointer-authority, or variant-proof redesign;
- no standard-library macro product surface beyond the bounded fixture/test coverage needed here;
- no command-adapter policy weakening, report parsing, hidden filesystem effects, inline semantic shell, or inline semantic Python.

## Current Baseline

The implementation must extend the repo as it exists today, not as an earlier MVP sketch:

- `orchestrator/workflow_lisp/` already contains the Stage 1-4 baseline, including `with-phase`, `phase-target`, `provider-result`, `command-result`, and shared-validation handoff.
- `tests/test_workflow_lisp_reader.py` already covers quoted `phase-target` symbol rejection via `phase_target_quoted_symbol_invalid.orc`; do not recreate that slice.
- `progress_ledger.json` is empty, so there is no prior macro-slice execution history to preserve or reconcile.
- The macro pass must therefore be additive in front of the current Stage 4 surfaces and must leave existing first-phase translation behavior intact.

## File Ownership

Create:

- `orchestrator/workflow_lisp/macros.py`
- `tests/test_workflow_lisp_macros.py`
- `tests/fixtures/workflow_lisp/valid/macro_workflow_alias.orc`
- `tests/fixtures/workflow_lisp/valid/macro_hygiene_local_binding.orc`
- `tests/fixtures/workflow_lisp/invalid/macro_expansion_cycle.orc`
- `tests/fixtures/workflow_lisp/invalid/macro_reserved_name.orc`
- `tests/fixtures/workflow_lisp/invalid/macro_bad_splice.orc`
- `tests/fixtures/workflow_lisp/invalid/macro_emits_invalid_form.orc`

Modify:

- `orchestrator/workflow_lisp/__init__.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/workflows.py`
- `tests/test_workflow_lisp_diagnostics.py`
- `tests/test_workflow_lisp_expressions.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_phase_translation.py`
- `tests/test_workflow_lisp_structured_results.py`
- `tests/test_workflow_lisp_workflows.py`

Modify only if a failing targeted test proves the need for compatibility glue:

- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `tests/test_workflow_lisp_reader.py`
- `tests/test_workflow_lisp_definitions.py`

Reuse without broadening ownership:

- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/sexpr.py`
- `orchestrator/workflow_lisp/spans.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/phase.py`
- shared workflow validation/runtime modules under `orchestrator/workflow/`

## Required Frontend Contract

Lock these implementation choices before touching code.

Macro authoring surface for this slice:

```lisp
(defmacro macro-name (arg1 arg2 ... [&rest rest-name | &body body-name])
  template-form)
```

Rules:

- one top-level `defmacro` per form;
- one template form only;
- fixed positional parameters plus one optional terminal `&rest` or `&body` capture;
- `&rest` and `&body` are mutually exclusive and bind the remaining raw syntax forms as a list;
- templates are ordinary syntax forms plus explicit `(splice name)` for list splicing;
- no quote, quasiquote, eval, file I/O, env lookup, randomness, providers, or commands at macro expansion time.

Reserved heads that may not be rebound by `defmacro`:

- `workflow-lisp`
- `defenum`
- `defpath`
- `defrecord`
- `defunion`
- `defworkflow`
- `defmacro`
- `record`
- `let*`
- `match`
- `call`
- `provider-result`
- `command-result`
- `with-phase`
- `phase-target`

Recursive syntax surface to add in `orchestrator/workflow_lisp/syntax.py`:

```python
@dataclass(frozen=True)
class ExpansionFrame:
    macro_name: str
    expansion_id: str
    call_span: SourceSpan
    definition_span: SourceSpan
    template_path: tuple[str, ...]


ExpansionStack = tuple[ExpansionFrame, ...]


@dataclass(frozen=True)
class SyntaxIdentifier:
    display_name: str
    resolved_name: str
    span: SourceSpan
    module_path: str
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack
    introduced_by_expansion_id: str | None = None
```

Mirror that pattern for `SyntaxList`, `SyntaxKeyword`, `SyntaxString`, `SyntaxInt`, and `SyntaxBool`. Add helper constructors for:

- cloning caller-authored syntax while preserving `display_name`, `resolved_name`, and spans;
- introducing generated identifiers with deterministic resolved names;
- rendering or matching list heads by resolved name without scattering raw `SymbolAtom` checks across the compiler.

Hygiene contract for this slice:

- user-authored identifiers are never renamed;
- introduced binders and their references are renamed to `%macro__<macro_name>__<expansion_id>__<display_name>`;
- only binder positions in the currently supported frontend grammar need alpha-renaming:
  - `let*` binding names;
  - `match` arm binders;
  - macro-emitted `defworkflow` parameter names if a top-level macro expands to a workflow definition;
- literal form heads, type names, variant tags, record field keywords, provider/prompt extern names, `phase-target` target names, and command boundary names stay literal unless they were substituted from caller syntax.

Macro-specific diagnostics to support deterministically:

- `macro_reserved_name`
- `macro_arity_error`
- `macro_expansion_cycle`
- `macro_hygiene_violation`
- `macro_emits_invalid_ast`
- `macro_hidden_effect`

Keep these existing diagnostics authoritative where they already fit:

- `frontend_parse_error`
- `definition_form_unknown`
- `expression_form_unknown`
- `workflow_boundary_type_invalid`
- `shared_validation_error`

Expansion provenance rendering contract:

- downstream diagnostics keep the generated node's primary span;
- notes are appended in expansion order with both call site and macro definition site;
- shared-validation remaps on generated steps/inputs/outputs/paths must render at least one macro note when the origin came from expansion.

## Task 1: Lock Fixtures, Tests, And Failing Expectations

**Files:**

- Create: `tests/test_workflow_lisp_macros.py`
- Create: `tests/fixtures/workflow_lisp/valid/macro_workflow_alias.orc`
- Create: `tests/fixtures/workflow_lisp/valid/macro_hygiene_local_binding.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/macro_expansion_cycle.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/macro_reserved_name.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/macro_bad_splice.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/macro_emits_invalid_form.orc`
- Modify: `tests/test_workflow_lisp_diagnostics.py`
- Modify: `tests/test_workflow_lisp_expressions.py`
- Modify: `tests/test_workflow_lisp_structured_results.py`
- Modify: `tests/test_workflow_lisp_workflows.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_phase_translation.py`

- [ ] **Step 1: Create fixture modules that pin the exact macro behaviors**

Populate fixtures so each one proves one bounded contract:

- `macro_workflow_alias.orc`: same-file forward reference where a top-level macro call appears before its `defmacro`, expands into an ordinary `defworkflow`, and emits only Stage 4-valid frontend syntax.
- `macro_hygiene_local_binding.orc`: a macro introduces a local binding named like a caller-local value so the test can prove the generated binder and reference are hygienically renamed.
- `macro_expansion_cycle.orc`: two macros recurse into one another or one macro expands to itself so `macro_expansion_cycle` is deterministic.
- `macro_reserved_name.orc`: `defmacro` attempts to bind one of the reserved heads and must fail during catalog collection with `macro_reserved_name`.
- `macro_bad_splice.orc`: illegal `(splice ...)` usage outside a list or against a scalar binding must fail with `macro_emits_invalid_ast` or `macro_hygiene_violation`, whichever the implemented rule chooses; lock that choice in the test and keep it stable.
- `macro_emits_invalid_form.orc`: expansion emits an empty form or non-symbol head so ordinary elaboration never sees malformed syntax.

- [ ] **Step 2: Add failing tests before implementation**

In `tests/test_workflow_lisp_macros.py`, add focused tests for:

- macro catalog collection before workflow elaboration;
- same-file forward references;
- reserved-head rejection;
- deterministic expansion IDs;
- cycle detection;
- hygiene of introduced `let*` locals;
- top-level macro expansion into `defworkflow`;
- macro-emitted `provider-result` or `command-result` flowing into existing Stage 3/4 checks.

Update the existing test modules with one macro-aware regression each:

- `tests/test_workflow_lisp_diagnostics.py`: expansion notes render with stable locations and order.
- `tests/test_workflow_lisp_expressions.py`: elaboration prefers resolved names from expanded syntax instead of raw authored spellings.
- `tests/test_workflow_lisp_workflows.py`: workflow catalog/build/typecheck accepts expanded top-level workflows and still rejects invalid boundary types after expansion.
- `tests/test_workflow_lisp_structured_results.py`: macro-emitted `provider-result` or `command-result` still obeys the same extern and command-boundary rules.
- `tests/test_workflow_lisp_lowering.py`: generated steps from macro-expanded workflows preserve remappable origin data.
- `tests/test_workflow_lisp_phase_translation.py`: the existing phase translation fixture still passes unchanged after the macro pass is inserted ahead of it.

- [ ] **Step 3: Collect and run the failing test surface**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_macros.py -q
python -m pytest tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_diagnostics.py -q
```

Expected:

- collect-only succeeds and shows the new macro test module;
- execution fails because `defmacro` parsing, cataloging, expansion, or provenance support does not exist yet.

## Task 2: Implement Recursive Syntax Metadata And The Macro Expansion Engine

**Files:**

- Create: `orchestrator/workflow_lisp/macros.py`
- Modify: `orchestrator/workflow_lisp/__init__.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/syntax.py`
- Modify: `orchestrator/workflow_lisp/definitions.py` only if syntax helpers cannot preserve the Stage 1 API without a mechanical adapter

- [ ] **Step 1: Upgrade `syntax.py` from shallow wrappers to recursive syntax objects**

Implement recursive syntax builders that convert the existing `sexpr.py` parse tree into metadata-carrying syntax objects. Keep `WorkflowLispSyntaxModule` as the module boundary, but make its forms recursively typed so later passes can inspect:

- `display_name`;
- `resolved_name`;
- `span`;
- `form_path`;
- `module_path`;
- `expansion_stack`.

Do not spread raw `ListExpr` and `SymbolAtom` inspection deeper into the compiler after this step. Add centralized helpers in `syntax.py` for:

- reading the resolved head symbol of a form;
- extracting list items from syntax lists;
- cloning caller syntax for substitution;
- introducing generated identifiers for hygienic templates.

- [ ] **Step 2: Implement `macros.py` with one closed expansion DSL**

Add:

```python
@dataclass(frozen=True)
class MacroDef:
    name: str
    params: tuple[str, ...]
    rest_param: str | None
    body_param: str | None
    template: SyntaxList | SyntaxIdentifier | SyntaxString | SyntaxInt | SyntaxBool
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class MacroCatalog:
    definitions_by_name: Mapping[str, MacroDef]
```

Required functions:

- `collect_macro_catalog(module_syntax: WorkflowLispSyntaxModule) -> MacroCatalog`
- `expand_module_forms(module_syntax: WorkflowLispSyntaxModule, catalog: MacroCatalog) -> WorkflowLispSyntaxModule`
- private helpers for pattern matching, template instantiation, splice validation, cycle detection, and deterministic `expansion_id` allocation.

Collection rules:

- scan all top-level forms for `defmacro` before elaborating anything else;
- allow forward references among same-file call sites;
- reject duplicate macro names and reserved heads during collection;
- keep `defmacro` forms out of the downstream definition/workflow module once the catalog is built.

Expansion rules:

- recursively expand non-`defmacro` top-level forms and nested expressions;
- when a form head resolves to a macro name, bind arguments against fixed params plus optional `&rest`/`&body`;
- allow `(splice name)` only inside list templates and only when `name` is bound to a list capture;
- reuse the same generated resolved name for every binder/reference pair introduced by one expansion;
- detect cycles using the active expansion stack keyed by macro name plus call site span.

- [ ] **Step 3: Route both compiler entrypoints through macro collection and expansion**

Refactor `compile_stage1_module()` and `compile_stage3_module()` so they share one front-end pipeline:

```text
read -> build recursive syntax -> collect macros -> expand forms -> elaborate definitions/workflows -> existing validation
```

Concrete changes:

- add one small internal helper in `compiler.py` that returns the expanded `WorkflowLispSyntaxModule`;
- update `_definition_only_syntax_module()` to exclude both `defworkflow` and `defmacro` after collection;
- export the new macro surface from `__init__.py` only if tests require it; otherwise keep it internal.

- [ ] **Step 4: Run the macro tests until the catalog and expansion engine pass**

Run:

```bash
python -m pytest tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_diagnostics.py -q
```

Expected:

- reserved-name, cycle, and bad-splice fixtures now fail with stable macro diagnostics;
- forward-reference and deterministic-expansion tests pass;
- any remaining failures are provenance-threading failures for later tasks, not missing macro collection/expansion behavior.

## Task 3: Thread Expanded Syntax Through Elaboration, Typechecking, And Boundary Checks

**Files:**

- Modify: `orchestrator/workflow_lisp/diagnostics.py`
- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py` only if carrying provenance through `TypedExpr` is necessary
- Modify: `tests/test_workflow_lisp_expressions.py`
- Modify: `tests/test_workflow_lisp_structured_results.py`
- Modify: `tests/test_workflow_lisp_workflows.py`

- [ ] **Step 1: Make elaboration consume expanded syntax instead of raw symbols**

Update `expressions.py` and `workflows.py` to use the syntax helpers from `syntax.py` rather than direct `sexpr` type checks wherever expanded identifiers matter. The critical rule is:

- semantic matching uses `resolved_name`;
- user-facing messages and notes keep `display_name` plus expansion provenance.

Do not add a second name-resolution system. The current type/proof/lowering pipeline should continue to compare strings, just now using resolved names produced by macro hygiene.

- [ ] **Step 2: Preserve provenance on elaborated nodes**

Any AST node that may participate in later diagnostics from expanded syntax must retain the expansion metadata coming from the syntax object that produced it. Use the existing span/form-path carrying nodes as the seam; add expansion-stack fields only where they are needed to render notes later.

The minimum places that need provenance preserved are:

- macro-emitted workflow definitions;
- macro-emitted `let*`, `match`, `provider-result`, `command-result`, `with-phase`, and `phase-target` expressions;
- any generated workflow parameter binders that arise from top-level macro expansion.

- [ ] **Step 3: Keep Stage 2/3 authority unchanged for semantic checks**

Verify by test that macro expansion does not bypass:

- workflow boundary type checks in `build_workflow_catalog()`;
- provider/prompt extern resolution;
- command boundary classification for `command-result`;
- phase-scope/type rules for `with-phase` and `phase-target`;
- variant proof rules for `match`.

Macro-emitted `command-result` must still fail if it uses an unregistered tool or inline semantic command shape; do not add any macro-only exception path.

- [ ] **Step 4: Expand diagnostics rendering to show macro provenance**

Extend `render_diagnostic()` so macro-generated failures append stable notes such as:

- `expanded from macro 'macro-name' call at path:line:column`
- `macro definition at path:line:column`

Keep note ordering deterministic from outermost call to innermost generated frame or vice versa, but choose one order and lock it in `tests/test_workflow_lisp_diagnostics.py`.

- [ ] **Step 5: Run the elaboration and structured-result regressions**

Run:

```bash
python -m pytest tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_structured_results.py -q
```

Expected:

- expanded top-level workflows elaborate and typecheck;
- hygiene tests prove introduced locals do not capture caller names;
- macro-emitted provider/command forms remain subject to the same structured-result and boundary rules as hand-authored code.

## Task 4: Propagate Macro Provenance Into Lowering And Shared-Validation Remaps

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_phase_translation.py`

- [ ] **Step 1: Replace span-only origin maps with origin records that can carry notes**

Today `LoweringOriginMap` stores only spans. Replace or extend those mappings so each generated step/input/output/path can carry:

- primary span;
- form path;
- expansion-stack notes, if any.

One acceptable shape is:

```python
@dataclass(frozen=True)
class LoweringOrigin:
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()
```

Then use `Mapping[str, LoweringOrigin]` in `LoweringOriginMap` rather than plain spans.

- [ ] **Step 2: Remap shared-validation failures back to macro call provenance**

Update `_raise_remapped_validation_error()` and `_remap_validation_message()` so a shared-validation failure on a generated step:

- still maps to the right authored location;
- still uses the existing shared-validation code path;
- now includes macro expansion notes when the generated origin came from a macro.

Do not invent a second validator or custom lowering-only failure channel.

- [ ] **Step 3: Add lowering and phase-translation regressions**

In `tests/test_workflow_lisp_lowering.py`, add assertions that macro-expanded workflows:

- lower to the same authored mapping shape as equivalent hand-authored workflows;
- preserve remappable origin data on generated step ids and generated inputs/outputs;
- still let externs and command boundaries flow through unchanged.

In `tests/test_workflow_lisp_phase_translation.py`, keep the existing hand-authored phase fixture passing unchanged and add one macro-aware regression only if needed to prove the inserted expansion pass does not alter current phase translation semantics.

- [ ] **Step 4: Run the lowering and phase-translation suite**

Run:

```bash
python -m pytest tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_phase_translation.py -q
```

Expected:

- shared-validation remap tests show macro notes on generated failures;
- first-phase translation regressions still pass with the macro pass enabled ahead of the existing Stage 4 pipeline.

## Task 5: Final Verification And Handoff Evidence

**Files:**

- No new source files in this task

- [ ] **Step 1: Run the required deterministic verification contract exactly**

Run these commands from the repo root in this order:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_macros.py -q
python -m pytest tests/test_workflow_lisp_macros.py -q
python -m pytest tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_expressions.py -q
python -m pytest tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_phase_translation.py -q
python -m pytest tests/test_workflow_lisp_reader.py tests/test_workflow_lisp_definitions.py tests/test_workflow_lisp_diagnostics.py tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_variant_proofs.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_phase_translation.py tests/test_workflow_lisp_macros.py -q
```

- [ ] **Step 2: If test files were added or renamed, confirm collection stays stable**

If the implementation changes test module names beyond what this plan specifies, run `pytest --collect-only` for each renamed module before claiming completion. Do not weaken or skip collection checks to hide import or discovery regressions.

- [ ] **Step 3: Record the implementation outcome with fresh evidence**

The implementation report for this work item must state:

- what changed in the frontend pipeline;
- which files were created or modified;
- which verification commands were run and their outcomes;
- whether any conditional compatibility edits to `definitions.py` or `typecheck.py` were required;
- whether any residual risk remains around expansion provenance or binder-position classification.

Do not claim the slice complete from inspection alone. Fresh command output is the success criterion.
