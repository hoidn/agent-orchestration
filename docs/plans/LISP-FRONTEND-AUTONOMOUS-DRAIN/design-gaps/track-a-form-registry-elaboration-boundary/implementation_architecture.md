# Track A Form Registry And Elaboration Boundary Implementation Architecture

Status: draft
Design gap id: `track-a-form-registry-elaboration-boundary`
Target design: `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_mvp_specification.md`

## Scope

This slice covers exactly the first post-preflight Track A frontend boundary:

- add one frontend-owned registry that classifies every compiler-known form
  head used by macro reservation, top-level admission, or expression
  elaboration;
- route expression elaboration through that registry instead of the current
  literal `if head.resolved_name == ...` chain for compiler-known forms;
- derive macro-reserved names and top-level definition-head admission from the
  same registry, or fail closed when the registry and the derived sets diverge;
- classify the public `review-revise-loop` surface as a stdlib-owned extension
  rather than a compiler-owned special form;
- reclassify the current `__stdlib-specialization__ phase-review-loop` route as
  a temporary compiler intrinsic with explicit removal metadata;
- replace literal frontend detection helpers for review-loop presence with
  registry/tag-based classification so the compiler stops recognizing
  `review-revise-loop` by ad hoc name branches.

Out of scope for this slice:

- generic imported `.orc` inline expansion or specialization;
- Track A denylist tests that remove or quarantine later review-loop-specific
  typecheck/lowering branches;
- removal of `StdlibSpecializationExpr`,
  `_typecheck_stdlib_specialization_expr(...)`,
  `_validate_review_loop_result_contract(...)`,
  or review-loop-specific lowering helpers;
- generic ProcRef specialization, structural constraints, loop exhaustion
  projection, or stdlib `review-revise-loop` authored implementation;
- runtime, shared-validation, source-map, or command-adapter policy changes
  beyond reusing existing contracts.

This is a bounded implementation architecture for the selected Track A
registry/elaboration gap only. It does not replace the parent frontend design,
the refactor architecture, or the broader review/revise stdlib integration
design.

## Problem Statement

The current checkout still knows frontend forms through multiple hard-coded
lists and literal branches:

1. `orchestrator/workflow_lisp/macros.py` hard-codes both
   `_RESERVED_MACRO_NAMES` and `_ALLOWED_TOP_LEVEL_HEADS`.
2. `orchestrator/workflow_lisp/expressions.py::_elaborate_list(...)` contains
   one long ordered branch chain for core forms, effect bridges, stdlib-like
   forms, and temporary intrinsics.
3. `orchestrator/workflow_lisp/compiler.py` contains literal helper logic for
   `resume-or-start`, `review-revise-loop`, and the internal
   `__stdlib-specialization__` bridge.
4. The public stdlib macro
   `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` exports
   `review-revise-loop`, but the compiler still recognizes the review-loop path
   through internal spellings such as `phase-review-loop`.
5. `orchestrator/workflow_lisp/stdlib_contracts.py` already documents lowering
   expectations for high-level forms, but it does not own expression-head
   reservation or elaboration routing, so classification is still split across
   unrelated modules.

That creates the exact semantic-drift risk called out by the refactor design:
new compiler-known forms require manual updates in multiple places, and the
current review-loop bridge still looks like compiler knowledge keyed to a
domain-specific route rather than an explicit extension boundary.

The selected gap is therefore not generic imported expansion yet. It is the
smaller prerequisite that makes later imported expansion honest:

- one registry says which heads the compiler knows and why;
- one elaboration boundary consults that registry;
- one compatibility classification marks public stdlib extensions versus
  temporary intrinsic bridges;
- later slices can remove special-case review-loop semantics against that
  explicit inventory instead of chasing string branches.

## Design Constraints

The implementation must stay coherent with:

- `docs/index.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - `8. Refactor Prerequisite Model`
  - `10. Track A: Generic .orc Expansion Substrate`
  - `10.1 Form Registry`
  - `10.2 Registry-Routed Elaboration`
  - `24. Incremental Implementation Plan`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
- `docs/design/workflow_lisp_refactor_architecture.md`
- `docs/plans/2026-06-02-workflow-lisp-low-hanging-refactor-plan.md`
- `docs/plans/2026-06-02-workflow-lisp-generic-orc-expansion-refactor.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/steering.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/selector/selection.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/design-gap-architect/architecture-targets.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/design-gap-architect/existing-architecture-index.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

The slice must also preserve these guardrails:

- keep `orchestrator/workflow_lisp/` as the frontend-owned package and keep
  shared runtime semantics under `orchestrator/workflow/`;
- reuse the current staged frontend pipeline:
  read -> syntax -> macro expansion -> definitions/functions/procedures/
  workflows -> typecheck -> lowering -> shared validation;
- reuse the existing provenance substrate:
  `SourcePosition`,
  `SourceSpan`,
  recursive syntax objects,
  macro expansion stacks,
  `LispFrontendDiagnostic`,
  and `LoweringOriginMap`;
- keep the work behavior-preserving for already-supported forms:
  no authored `.orc` syntax changes,
  no changed runtime behavior,
  no relaxed diagnostics,
  and no hidden new execution path;
- keep structured state and typed artifacts authoritative; do not let registry
  indirection create a loophole for inline semantic shell/Python glue, report
  parsing, or pointer-as-authority behavior.

`docs/design/workflow_command_adapter_contract.md` is authoritative here even
though this slice adds no new adapter. The registry will classify
`command-result`, `resume-or-start`, `resource-transition`, and related bridge
forms. That classification must preserve the existing command-boundary contract
rather than making compiler-known forms look like unconstrained syntax sugar.

`docs/steering.md` is empty in this checkout. That is not permission to widen
scope. The selection bundle and target design remain the effective steering
surfaces.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The full index in
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/design-gap-architect/existing-architecture-index.md`
was reviewed for coherence. The directly reused slices for this gap are:

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-validation-diagnostics-pipeline/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/hygienic-defmacro-system/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/module-import-export-resolution/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-review-revise-preflight-hazard-fixes/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md`

### Decisions Reused

- Reuse the staged frontend pipeline and the existing package ownership split.
- Reuse the existing span, diagnostic, macro-provenance, and lowering-origin
  substrate rather than inventing a parallel form-tracking channel.
- Reuse the preflight hazard-fix sequencing rule: Track A starts only after the
  concrete hazard slice, and this slice still stays behavior-preserving.
- Reuse the module/import slice's rule that imported stdlib ownership is a
  frontend concern, not a runtime loader concern.
- Reuse the phase-context and Stage 3 lowering slices' command-boundary
  classifications; the new registry catalogs those forms but does not replace
  their downstream typecheck/lowering contracts.
- Reuse the macro slice's rule that macro expansion is syntax-only and that
  imported/public macros may own ergonomic heads without making those heads
  compiler primitives.

### New Decisions In This Slice

- Add one dedicated frontend `form_registry.py` module as the authoritative
  inventory of compiler-known heads.
- Keep one explicit `FormKind` classification for compiler-known forms and add
  the minimum metadata needed to derive macro reservation, top-level admission,
  and expression elaboration routing from the same source.
- Treat `review-revise-loop` as a `STDLIB_EXTENSION` owned by `std/phase.orc`,
  not as a core reserved name or direct elaboration branch.
- Keep `__stdlib-specialization__` as a `TEMP_COMPILER_INTRINSIC` during the
  compatibility window, with explicit `remove_by` metadata pointing to the
  later imported `.orc` expansion route.
- Route `_elaborate_list(...)` through registry lookup first, then fall back to
  same-file function/procedure/local-proc resolution only when no compiler-known
  head matches.
- Replace compiler helper detection for review-loop presence with registry/tag
  checks rather than literal `review-revise-loop` or
  `__stdlib-specialization__` name branches.

### Conflicts Or Revisions

The current checkout already moved away from a dedicated `ReviewReviseLoopExpr`
AST node, but it still carries review-loop-specific knowledge through
`StdlibSpecializationExpr`, `phase-review-loop`, and multiple literal helper
branches. This slice does not remove that bridge. It revises its status:

- the public name `review-revise-loop` becomes an explicit stdlib extension
  classification;
- the internal bridge `__stdlib-specialization__` becomes explicitly temporary;
- later typecheck/lowering de-specialization remains a follow-on slice.

`macros.py` currently owns hand-maintained `_RESERVED_MACRO_NAMES` and
`_ALLOWED_TOP_LEVEL_HEADS`. This slice revises that ownership narrowly by
making those surfaces derived from, or validated against, the registry.

No prior slice is reversed on shared concepts such as spans, diagnostics, Core
Workflow AST, Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority,
or variant proof.

## Ownership Boundaries

This slice owns:

- one frontend-owned form-classification registry and its metadata schema;
- classification of compiler-known top-level heads, core expression forms,
  effect bridges, stdlib extensions, and temporary intrinsics;
- derivation or parity validation for macro-reserved names and top-level
  admitted definition heads;
- registry-routed expression elaboration dispatch in `expressions.py`;
- registry/tag-based compiler helper queries for review-loop route detection;
- focused tests proving registry coverage, reserved-name parity, compatibility
  classification, and unchanged imported stdlib review-loop compilation.

This slice intentionally does not own:

- imported `.orc` inline expansion or generic `expand_inline_procedure_call(...)`;
- removal of review-loop-specific typecheck or lowering behavior;
- review-loop result-contract redesign, findings-path redesign, or resume
  checkpoint identity;
- new command adapters, adapter registries, runtime-native effects, or
  command-boundary semantics;
- source-map/runtime-lineage schema changes or runtime observability changes.

## Current Checkout Facts

The current checkout confirms the selected gap directly:

- `orchestrator/workflow_lisp/macros.py` hard-codes
  `_RESERVED_MACRO_NAMES` and `_ALLOWED_TOP_LEVEL_HEADS`.
- `orchestrator/workflow_lisp/expressions.py::_elaborate_list(...)` contains a
  long literal branch chain for:
  `record`,
  `variant`,
  `let*`,
  `if`,
  `match`,
  `loop/recur`,
  `call`,
  `with-phase`,
  `phase-target`,
  `workflow-ref`,
  `proc-ref`,
  `bind-proc`,
  `let-proc`,
  `provider-result`,
  `command-result`,
  `run-provider-phase`,
  `produce-one-of`,
  `__stdlib-specialization__`,
  `resume-or-start`,
  `resource-transition`,
  `finalize-selected-item`,
  and `backlog-drain`.
- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` still exports the
  public macro `review-revise-loop`, and that macro expands to
  `(__stdlib-specialization__ phase-review-loop ...)`.
- `orchestrator/workflow_lisp/typecheck.py` still typechecks that bridge
  through `_typecheck_stdlib_specialization_expr(...)` and
  `_validate_review_loop_result_contract(...)`.
- `orchestrator/workflow_lisp/compiler.py` still contains
  `_workflow_contains_review_revise_loop(...)` with literal checks for both
  `review-revise-loop` and `__stdlib-specialization__`.
- `orchestrator/workflow_lisp/stdlib_contracts.py` already classifies
  `review-revise-loop` as a stdlib lowering contract, but there is no separate
  frontend-owned head registry that elaboration or macro reservation uses.
- no `orchestrator/workflow_lisp/form_registry.py` module exists yet.
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` contains no
  events, so no later recorded implementation state supersedes the selected
  Track A obligation.

One important compatibility fact also constrains the slice:

- the public `review-revise-loop` head is not currently in
  `_RESERVED_MACRO_NAMES`, which allows the imported stdlib macro to own that
  name today.

The new registry must preserve that public ownership while still reserving the
internal compatibility head `__stdlib-specialization__`.

## Feasibility Proof

This slice depends on a replacement-of-special-cases claim, so the feasibility
boundary must be explicit.

Already proven in the current checkout:

- macro expansion runs before expression elaboration and can expand imported
  stdlib macros such as `std/phase.review-revise-loop`;
- `_elaborate_list(...)` is already the single central entry point for headed
  expression elaboration, so one registry lookup can replace the current branch
  chain without changing the surrounding pipeline;
- the compatibility bridge from `StdlibSpecializationExpr` through typecheck
  and lowering already works, so classifying that bridge as a temporary
  intrinsic does not require new runtime behavior;
- imported/public macros and same-file callable fallback already coexist, so a
  registry can fail closed for compiler-known heads while leaving ordinary
  callable resolution unchanged.

Not yet proven, and therefore intentionally out of scope here:

- generic imported `.orc` body expansion or specialization;
- denylist enforcement that removes review-loop-specific typecheck/lowering;
- direct elaboration of `STDLIB_EXTENSION` heads through an imported-definition
  route.

Therefore this slice can safely deliver the registry/elaboration boundary now,
while leaving imported expansion as an explicit later prerequisite instead of
pretending the generic route already exists.

## Proposed Package Boundary

Add one dedicated frontend-owned registry module and thread it through the
existing elaboration/macro/compiler seams:

```text
orchestrator/workflow_lisp/
  form_registry.py
  expressions.py
  macros.py
  compiler.py

tests/
  test_workflow_lisp_expressions.py
  test_workflow_lisp_macros.py
  test_workflow_lisp_phase_stdlib.py
  test_workflow_lisp_key_migrations.py
```

Responsibilities:

- `form_registry.py`
  - define `FormKind`, `FormSpec`, and the canonical head inventory;
  - expose helpers for:
    expression-head lookup,
    reserved-macro-name derivation,
    top-level definition-head derivation,
    and tag-based feature queries.
- `expressions.py`
  - keep elaborator implementations local;
  - replace literal head dispatch with registry lookup plus a small
    elaboration-route table;
  - keep same-file function/procedure fallback behavior unchanged.
- `macros.py`
  - derive or validate reserved macro names and allowed top-level heads from
    the registry;
  - preserve the existing user-facing diagnostics for duplicate or reserved
    macro names.
- `compiler.py`
  - replace literal review-loop route detection with registry/tag helpers;
  - keep the rest of the compile pipeline unchanged.
- focused tests
  - prove registry coverage and compatibility behavior without widening into
    imported `.orc` expansion or review-loop de-specialization.

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/stdlib_contracts.py`
- `orchestrator/workflow_lisp/modules.py`
- `orchestrator/workflow_lisp/procedures.py`
- `orchestrator/workflow_lisp/phase.py`
- shared validation/runtime modules under `orchestrator/workflow/`

## Data Model

### `FormKind`

Add one frontend-owned form classification enum:

- `TOP_LEVEL_DEFINITION`
- `CORE_SPECIAL`
- `CORE_EFFECT`
- `STDLIB_EXTENSION`
- `TEMP_COMPILER_INTRINSIC`

Reason for the `TOP_LEVEL_DEFINITION` addition:

- the target design sketch focuses on expression/head routing, but the current
  checkout also duplicates top-level-head knowledge in `macros.py`;
- leaving definition heads outside the registry would preserve a second manual
  classification surface and defeat the selected gap's goal of one explicit
  head inventory.

### `FormSpec`

Each registry entry should carry the minimum metadata needed by this slice:

- `name`
- `kind`
- `owner_module`
- `introduced_in`
- `remove_by`
- `macro_bindable`
- `admitted_top_level`
- `elaboration_route`
- `feature_tags`
- `rationale`

Required semantics:

- `macro_bindable=False` means the head belongs in the reserved-macro set;
- `admitted_top_level=True` means the head belongs in the top-level definition
  validator set;
- `elaboration_route` is a symbolic route key, not a direct function pointer,
  so the registry stays decoupled from `expressions.py` implementation details;
- `feature_tags` provide a stable way for compiler helpers to ask questions
  such as "is this part of the review-loop compatibility route?" without
  reintroducing literal string branches.

### Registry Inventory

The first registry inventory should classify at least these current checkout
heads:

- top-level definitions/directives:
  `workflow-lisp`,
  `defenum`,
  `defpath`,
  `defschema`,
  `defrecord`,
  `defunion`,
  `defworkflow`,
  `defun`,
  `defproc`,
  `defmodule`,
  `import`,
  `export`,
  `defmacro`
- core specials:
  `record`,
  `variant`,
  `let*`,
  `if`,
  `match`,
  `loop/recur`,
  `fn`,
  `continue`,
  `done`,
  `call`,
  `workflow-ref`,
  `proc-ref`,
  `bind-proc`,
  `let-proc`
- core effects:
  `provider-result`,
  `command-result`
- stdlib extensions:
  `review-revise-loop`
- temporary intrinsics:
  `with-phase`,
  `phase-target`,
  `run-provider-phase`,
  `produce-one-of`,
  `provider`,
  `__stdlib-specialization__`,
  `resume-or-start`,
  `resource-transition`,
  `finalize-selected-item`,
  `backlog-drain`

Compatibility-specific requirements:

- `review-revise-loop`
  - `kind=STDLIB_EXTENSION`
  - `macro_bindable=True`
  - `feature_tags` includes `review_loop_public_surface`
- `__stdlib-specialization__`
  - `kind=TEMP_COMPILER_INTRINSIC`
  - `macro_bindable=False`
  - `remove_by` points at imported `.orc` expansion and review-loop bridge
    retirement
  - `feature_tags` includes `review_loop_compat_bridge`

## Proposed Architecture

### 1. Make The Registry The Single Head Inventory

Create `orchestrator/workflow_lisp/form_registry.py` as the only frontend-owned
inventory of compiler-known heads.

That registry becomes the source of truth for:

- which heads are compiler-known;
- which heads are public stdlib extensions versus compiler intrinsics;
- which heads are reserved from user macro binding;
- which heads are admitted at top level;
- which heads participate in feature-family queries such as review-loop
  compatibility detection.

`stdlib_contracts.py` remains downstream lowering metadata. It is not upgraded
into the registry because it does not own macro reservation, top-level
admission, or expression dispatch.

### 2. Route Expression Elaboration Through Registry Lookup

Replace the literal chain in `_elaborate_list(...)` with this boundary:

1. resolve the syntax head;
2. ask the registry for a known form spec;
3. if no spec exists, fall back to same-file helper/procedure/local-proc rules;
4. if a spec exists:
   - `TOP_LEVEL_DEFINITION` is rejected in expression position;
   - `STDLIB_EXTENSION` uses the stdlib-extension branch;
   - all other kinds dispatch by `elaboration_route`.

In this slice, the `STDLIB_EXTENSION` branch is fail-closed, not imported
expansion. If a public stdlib extension head reaches expression elaboration
after macro expansion, emit an owned frontend diagnostic such as
`stdlib_extension_missing_import_route` rather than silently treating it as a
compiler primitive.

That keeps the design honest:

- `review-revise-loop` is now explicitly classified as a stdlib extension;
- the current working compatibility path still depends on the macro expanding
  into `__stdlib-specialization__`;
- imported `.orc` expansion remains a later slice rather than an implied
  capability.

### 3. Keep The Review-Loop Bridge Explicitly Temporary

The existing `__stdlib-specialization__ phase-review-loop` route remains
implemented for now, but it must be modeled as compatibility debt:

- keep its elaboration route in the registry under
  `TEMP_COMPILER_INTRINSIC`;
- keep its internal-only macro reservation;
- require explicit `remove_by` metadata tied to the later imported `.orc`
  expansion route;
- make all frontend consumers that still need to detect review-loop behavior
  query the registry/tag metadata instead of matching
  `review-revise-loop` or `phase-review-loop` directly.

This preserves current behavior without pretending the bridge is the target
architecture.

### 4. Derive Macro Reservation And Top-Level Admission From The Registry

`macros.py` should stop owning manual head sets as primary authority.

Required behavior:

- reserved macro names derive from every `FormSpec` where
  `macro_bindable=False`;
- top-level admitted heads derive from every `FormSpec` where
  `admitted_top_level=True`;
- import-time validation fails closed if a helper list remains and diverges
  from the registry.

Important compatibility outcome:

- `review-revise-loop` stays available to the imported stdlib macro because its
  `FormSpec` remains macro-bindable;
- `__stdlib-specialization__` stays reserved and internal-only;
- future compiler-known heads require one registry entry instead of multiple
  list edits.

### 5. Replace Literal Compiler Scanners With Registry/Tag Queries

`compiler.py` currently answers workflow questions by matching literal head
names. That must narrow to registry/tag queries for the selected review-loop
boundary.

For this slice:

- replace literal checks inside `_workflow_contains_review_revise_loop(...)`
  with registry-based detection of either:
  `review_loop_public_surface` or `review_loop_compat_bridge`;
- keep helper semantics unchanged otherwise;
- do not broaden this into a full generic traversal/registry rewrite for every
  compiler helper unless the current helper already touches the selected gap.

This step matters because otherwise the registry would exist, but the compiler
would still recognize review loops by raw strings in downstream helpers.

### 6. Keep Typecheck And Lowering Unchanged In This Slice

The selected gap ends at elaboration boundary hardening. It does not own later
removal of review-loop-specific downstream behavior.

Therefore:

- `StdlibSpecializationExpr` remains the compatibility expression node;
- `_typecheck_stdlib_specialization_expr(...)` remains the current typecheck
  bridge;
- `_validate_review_loop_result_contract(...)` remains the current result
  contract bridge;
- lowering remains unchanged except for any mechanical metadata rename needed
  to keep diagnostics/source maps consistent.

This keeps the slice bounded and prevents Track A registry work from
accidentally claiming imported stdlib execution parity it has not yet proven.

## Diagnostics And Tests

Add or reserve focused diagnostics for this slice:

- `form_registry_missing_classification`
- `reserved_name_registry_mismatch`
- `stdlib_extension_missing_import_route`

Focused tests should prove:

- every compiler-known head currently used by macros or expression elaboration
  has one registry entry;
- reserved macro names and top-level admitted heads derive from, or exactly
  match, the registry;
- `_elaborate_list(...)` dispatches known heads through registry lookup;
- the public head `review-revise-loop` is classified as a stdlib extension and
  is not a reserved compiler-owned macro name;
- the internal head `__stdlib-specialization__` remains reserved and classified
  as temporary compatibility;
- existing imported stdlib review-loop fixtures still compile through the
  current compatibility bridge after the registry is introduced.

Denylist tests for removing review-loop-specific typecheck/lowering behavior are
explicitly the next Track A slice, not part of this one.

## Acceptance Checks

This slice is complete when all of the following are true:

- `orchestrator/workflow_lisp/form_registry.py` exists and classifies every
  compiler-known head currently used by macro reservation or expression
  elaboration.
- `expressions.py` consults the registry before special-form dispatch.
- same-file function/procedure/local-proc fallback behavior still happens only
  after registry lookup misses.
- `review-revise-loop` is classified as a stdlib extension rather than a
  compiler-owned special form.
- `__stdlib-specialization__` is classified as a temporary intrinsic with
  explicit removal metadata.
- macro-reserved names and top-level admitted heads are derived from, or
  validated against, the registry.
- compiler review-loop detection no longer depends on literal
  `review-revise-loop` or `__stdlib-specialization__` string branches.
- no imported `.orc` expansion, denylist enforcement, or review-loop
  de-specialization is claimed as done by this slice.
