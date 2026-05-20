# Hygienic `defmacro` System Implementation Architecture

## Scope

This design gap covers only the user-defined hygienic macro system required by
the full Workflow Lisp frontend after the current Stage 1-4 slices:

- add same-file top-level `defmacro` definition support;
- resolve macro bindings before definition/workflow elaboration;
- expand macro calls hygienically and deterministically;
- preserve source spans and expansion provenance across expansion and later
  validation;
- hand expanded frontend syntax back to the existing Stage 1-4 definition,
  typing, lowering, and shared-validation pipeline without bypasses.

Out of scope for this tranche:

- `defproc`, `defun`, modules/imports/exports, or cross-file macro libraries;
- new runtime execution behavior, loader/CLI integration, or executable-IR
  changes;
- new shared Core Workflow AST, Semantic Workflow IR, TypeCatalog, SourceMap,
  pointer-authority, or variant-proof contracts;
- intentional capture forms such as `bind-as`;
- standard-library review-loop, drain, resource-transition, or phase macros as
  separate product features;
- command-adapter registry redesign or runtime-native effect promotion.

This slice is an implementation architecture for hygienic user macros only. It
does not replace the product design in
`docs/design/workflow_lisp_frontend_specification.md`.

## Design Constraints

The implementation must stay coherent with:

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
- `docs/design/workflow_command_adapter_contract.md`
- `docs/steering.md`
- `docs/design/workflow_language_design_principles.md`

The slice must also preserve the guardrails already established by the earlier
implementation architectures:

- keep `orchestrator/workflow_lisp/` isolated from `orchestrator/workflow/`;
- keep Stage 1 spans, syntax, and deterministic diagnostics as the frontend
  authority boundary;
- keep Stage 2 type/proof checking and Stage 3/4 lowering as the only route to
  workflow semantics;
- keep reports as views, structured bundles as authority, artifact values as
  authority, and pointer files as representations;
- keep `command-result` subject to the existing command-boundary
  classification rules even when it is emitted by a macro;
- do not let macros emit Core Workflow AST, Semantic Workflow IR, executable
  IR, hidden state rewrites, inline semantic shell/Python glue, or markdown
  parsing shortcuts.

`docs/design/workflow_command_adapter_contract.md` is authoritative for this
slice because hygienic expansion must not become a loophole for scripts or
command steps that carry hidden workflow semantics. If a macro emits
`command-result`, the expanded form must still pass the same external-tool or
certified-adapter checks that Stage 3 already enforces.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`

### Decisions Reused

- Reuse the existing staged pipeline shape:
  read -> syntax -> definitions/workflows -> typecheck -> lowering ->
  shared validation.
- Reuse `LispFrontendDiagnostic` as the deterministic diagnostic surface rather
  than inventing a second error channel for macros.
- Reuse Stage 2 and Stage 3 as the semantic gatekeepers for effects, workflow
  calls, provider/command boundaries, contracts, and variant proof.
- Reuse the current package ownership split:
  syntax in `syntax.py`, expression typing in `typecheck.py`, workflow
  signatures in `workflows.py`, and authored-mapping lowering in `lowering.py`.
- Reuse the existing restriction that compiler-known provider/prompt externs
  and command-boundary metadata stay outside user-authored workflow values.

### New Decisions In This Slice

- Insert an explicit P2/P3 macro pipeline between syntax construction and the
  existing definition/workflow elaboration passes.
- Add a dedicated `macros.py` module that owns macro definition elaboration,
  macro catalogs, pattern/template interpretation, deterministic expansion, and
  cycle detection.
- Evolve syntax objects from a shallow top-level wrapper into recursive
  metadata-carrying syntax objects so hygiene and expansion provenance survive
  below the top level.
- Implement hygiene by deterministic introduced-identifier renaming plus
  expansion metadata, so the existing downstream passes can continue to resolve
  symbols by strings instead of requiring a whole new scope-aware typechecker.
- Require all user macros to expand into ordinary frontend syntax that then
  flows through the existing Stage 1-4 passes with no privileged escape hatch.

### Conflicts Or Revisions

The Stage 1 architecture intentionally deferred hygiene fields. This slice now
revises that boundary narrowly:

- `syntax.py` must stop treating syntax objects as only
  `SyntaxNode(datum, span, module_path, form_path)` wrappers over raw parse
  nodes;
- recursive syntax metadata is now required so introduced identifiers,
  preserved caller syntax, and expansion-stack frames can be tracked precisely.

This is not a revision of shared concepts such as spans, diagnostics, Core
Workflow AST, Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority,
or variant proof. It is a frontend-local evolution needed to make the already
specified macro behavior implementable.

## Ownership Boundaries

This slice owns:

- top-level `defmacro` elaboration and validation;
- same-file macro name registration and reserved-name checks;
- recursive hygienic macro expansion of ordinary frontend syntax;
- deterministic introduced-identifier generation;
- expansion-stack provenance that later diagnostics and lowering-origin remaps
  can consume;
- macro-specific diagnostic codes and rendering notes;
- tests and fixtures for macro elaboration, hygiene, cycle detection, invalid
  templates, and expansion-aware regression coverage.

This slice intentionally does not own:

- the reader grammar beyond reusing existing S-expression parsing;
- user-defined procedures, compile-time pure functions, or a general
  compile-time evaluator;
- cross-file module/import/export resolution;
- shared workflow semantics, runtime execution, path safety, pointer
  authority, state persistence, or resource-transition behavior;
- redesign of shared SourceMap or lowering of standard-library phase/resource
  abstractions;
- new adapter certification logic beyond reusing the Stage 3 command-boundary
  contract.

## Proposed Package Boundary

Extend the existing frontend package with one bounded macro layer:

```text
orchestrator/workflow_lisp/
  __init__.py
  compiler.py            # add macro expansion pass orchestration
  diagnostics.py         # add macro codes and expansion-stack rendering
  expressions.py         # elaborate from expanded syntax objects
  lowering.py            # preserve macro-origin notes in validation remapping
  macros.py              # new macro defs, catalog, expansion engine
  syntax.py              # recursive syntax objects + origin metadata
  workflows.py           # elaborate expanded defworkflow forms
```

Responsibilities:

- `syntax.py`
  - build recursive syntax objects from parse-tree nodes;
  - carry authored span, module path, form path, display spelling,
    resolved spelling, and expansion metadata;
  - provide helpers for cloning caller syntax vs introducing generated syntax.
- `macros.py`
  - elaborate raw `defmacro` forms into `MacroDef` records;
  - validate macro signatures and templates;
  - collect same-file macro bindings before expansion;
  - expand macro calls recursively with cycle detection and deterministic ids.
- `compiler.py`
  - run read -> syntax -> macro collection -> expansion -> existing Stage 1/3
    elaboration;
  - ensure `compile_stage1_module()` and `compile_stage3_module()` both consume
    expanded syntax rather than raw user syntax.
- `diagnostics.py`
  - add macro error codes and expansion-aware note rendering.
- `expressions.py` and `workflows.py`
  - elaborate expanded syntax using resolved spellings while preserving
    expansion provenance on emitted frontend AST nodes.
- `lowering.py`
  - carry expansion provenance into lowering-origin maps so shared-validation
    errors on generated workflow surfaces still blame the macro call site.

Planned test and fixture surface:

```text
tests/
  test_workflow_lisp_macros.py
  test_workflow_lisp_workflows.py
  test_workflow_lisp_expressions.py
  test_workflow_lisp_lowering.py
  test_workflow_lisp_phase_translation.py
  fixtures/workflow_lisp/valid/macro_workflow_alias.orc
  fixtures/workflow_lisp/valid/macro_hygiene_local_binding.orc
  fixtures/workflow_lisp/invalid/macro_expansion_cycle.orc
  fixtures/workflow_lisp/invalid/macro_reserved_name.orc
  fixtures/workflow_lisp/invalid/macro_bad_splice.orc
  fixtures/workflow_lisp/invalid/macro_emits_invalid_form.orc
```

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/spans.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/typecheck.py`
- shared workflow validation/runtime modules under `orchestrator/workflow/`

## Data Model

### Recursive Syntax Objects

Replace the shallow top-level wrapper model with recursive syntax objects:

- `SyntaxList`
- `SyntaxIdentifier`
- `SyntaxKeyword`
- `SyntaxString`
- `SyntaxInt`
- `SyntaxBool`

Every recursive syntax object carries:

- `span`
- `module_path`
- `form_path`
- `expansion_stack`

`SyntaxIdentifier` additionally carries:

- `display_name`
- `resolved_name`
- `introduced_by_expansion_id | None`

Why this split matters:

- `display_name` keeps user-facing spelling stable in diagnostics and rendered
  debug output;
- `resolved_name` is the string that later definition/expression/workflow
  passes use for lexical matching;
- introduced identifiers can therefore be hygienic without forcing Stage 2/3
  to adopt a brand-new scope-resolution model.

### Expansion Provenance

Introduce:

- `ExpansionFrame`
  - `macro_name`
  - `expansion_id`
  - `call_span`
  - `definition_span`
  - `template_path`
- `ExpansionStack = tuple[ExpansionFrame, ...]`

`expansion_id` must be deterministic. Use a monotonic per-module counter in
preorder expansion order, for example `m0001`, `m0002`, and so on.

### Macro Definitions

Add frontend-local macro definition records:

- `MacroDef(name, pattern, template, span, form_path)`
- `MacroCatalog(definitions_by_name, reserved_heads)`

This slice keeps the author surface bounded:

- macros are defined only at the top level with `defmacro`;
- macros expand one form into one form;
- pattern matching supports fixed positional arguments plus one terminal
  `&rest` or `&body` capture;
- templates support plain syntax emission, syntax-variable substitution, and
  explicit list splicing through a dedicated `(splice name)` template form.

The slice intentionally does not add compile-time `defun`, arbitrary
evaluation, or reader-level quote/unquote syntax.

## Hygiene Model

Use deterministic alpha-renaming for introduced identifiers.

Rules:

1. Syntax copied from the macro call site preserves its `display_name`,
   `resolved_name`, and original span.
2. Syntax introduced by the macro template keeps its authored
   `display_name`, but receives a generated `resolved_name` of the form:
   `%macro__<macro_name>__<expansion_id>__<display_name>`.
3. References and binders introduced by the same template expansion receive
   the same `resolved_name`.
4. No user-authored identifier is ever renamed by macro expansion.
5. Intentional capture is unsupported in this slice.

This approach satisfies the full design's hygiene requirement while staying
compatible with the current downstream implementation, which still resolves
names by string equality.

## Compilation And Expansion Pipeline

The revised frontend pipeline for Stage 1-4 entrypoints becomes:

```text
.orc source
  -> read S-expressions
  -> build recursive syntax module
  -> collect top-level macro definitions
  -> expand non-macro forms hygienically
  -> elaborate expanded definitions/workflows
  -> existing typecheck/lowering/shared-validation passes
```

### Phase Details

- P0/P1: unchanged reader and initial syntax construction.
- P2:
  - scan top-level syntax forms for `defmacro`;
  - reject duplicate macro names;
  - reject attempts to redefine reserved compiler-owned heads such as
    `workflow-lisp`, `defenum`, `defpath`, `defrecord`, `defunion`,
    `defworkflow`, `defmacro`, `record`, `let*`, `match`, `call`,
    `provider-result`, `command-result`, `with-phase`, and `phase-target`;
  - allow forward references among same-file macro call sites by building the
    catalog before expanding ordinary forms.
- P3:
  - recursively walk non-`defmacro` top-level forms;
  - when list head resolves to a macro name, match arguments against the
    pattern, instantiate the template, assign a fresh `expansion_id`, and
    continue expanding the result;
  - detect recursive expansion cycles with an active expansion stack keyed by
    `(macro_name, call_span)`.
- P4+:
  - feed the expanded syntax module into the existing definition, workflow,
    typecheck, lowering, and shared-validation passes.

Macro definitions themselves are not passed to Stage 1 definition validation or
Stage 3 workflow elaboration once the catalog is built.

## Validation And Error Model

Macro-specific diagnostics extend `LispFrontendDiagnostic.code` with:

- `macro_unknown`
- `macro_arity_error`
- `macro_keyword_unknown`
- `macro_keyword_missing`
- `macro_expansion_cycle`
- `macro_hygiene_violation`
- `macro_non_deterministic`
- `macro_emits_invalid_ast`
- `macro_emits_untyped_hole`
- `macro_weakens_contract`
- `macro_hidden_effect`

This slice should emit them under these conditions:

- `macro_arity_error`
  - pattern mismatch or invalid `&body`/`&rest` usage;
- `macro_expansion_cycle`
  - recursive or mutually recursive expansion on the active stack;
- `macro_hygiene_violation`
  - malformed template reuse that attempts to splice a scalar binding into a
    binder position or otherwise breaks introduced-name pairing;
- `macro_emits_invalid_ast`
  - template emits an empty form, non-symbol head, illegal splice position, or
    malformed top-level form;
- `macro_hidden_effect`
  - template tries to emit forbidden internal escape forms rather than normal
    frontend syntax;
- `macro_weakens_contract`
  - reserved for later typed-template checks, but the slice should keep the
    code available and route obvious contract-bypass escape attempts here.

Later Stage 1-4 diagnostics remain authoritative for ordinary definition,
typing, boundary, lowering, and shared-validation errors on expanded forms.

## Post-Expansion Validation Handoff

Macro expansion must not create a separate semantic pipeline.

Handoff rules:

- expanded syntax is the only input to `definitions.py`, `expressions.py`, and
  `workflows.py`;
- downstream AST nodes preserve `span`, `form_path`, and `expansion_stack`
  copied from the expanded syntax objects that produced them;
- diagnostics emitted after expansion keep the generated node's primary span,
  but render expansion-stack notes so the user sees the macro call site and the
  macro definition site;
- `lowering.py` extends its local origin-remap records to include expansion
  notes, so a shared-validation failure on a generated step or output can still
  be traced back to the authored macro call.

This slice intentionally does not redefine the shared `SourceMap` contract. It
provides the frontend-local provenance that later shared source-map work can
consume.

## Determinism And Safety

Determinism is enforced structurally in this tranche:

- user macros are interpreted from a closed pattern/template DSL;
- no compile-time Python callbacks, filesystem I/O, environment lookups,
  time, randomness, providers, or command execution are exposed;
- macro outputs are plain frontend syntax only;
- all emitted command/provider/state behavior remains visible to existing
  Stage 2/3/4 checks after expansion.

That means `macro_non_deterministic` should be unreachable in normal use for
this tranche; keeping the code reserved now avoids another diagnostic-shape
change later if macro capabilities expand.

## Test Strategy

Required test categories:

- macro definition elaboration and reserved-name rejection;
- forward reference and same-file catalog behavior;
- simple macro expansion into `defworkflow`/expression forms;
- hygiene regression where an introduced temporary cannot capture or be
  captured by a user binding with the same display name;
- expansion-cycle detection;
- invalid splice and malformed template diagnostics;
- Stage 3/4 regression coverage proving expanded `provider-result`,
  `command-result`, `with-phase`, and `phase-target` forms still lower through
  the existing semantic pipeline;
- shared-validation remap coverage proving expansion notes survive into the
  generated-workflow error path.

## Acceptance Boundary

This slice is complete when:

- user-authored same-file `defmacro` forms expand deterministically and
  hygienically into ordinary frontend syntax;
- no unresolved user macro calls survive the expansion pass;
- expanded workflows still typecheck, lower, and validate through the existing
  Stage 1-4 pipeline;
- introduced temporary names are hygienic without redefining the shared
  type/proof/runtime contracts;
- diagnostics for macro failures and later expanded-form failures preserve
  macro provenance; and
- macros do not create a loophole around the command adapter contract or any
  other existing semantic validation boundary.
