# Workflow Lisp Refactoring Backlog

Status: draft
Created: 2026-05-23
Scope: `orchestrator/workflow_lisp/`

## Purpose

This backlog captures refactoring work for the Workflow Lisp compiler frontend.
It is not a full-design implementation backlog. Missing language features and
missing shared contracts should remain tracked by design-gap work.

The goal here is narrower: reduce maintenance cost in the existing frontend
without changing the authored `.orc` language or weakening diagnostics,
source provenance, type safety, effect visibility, or lowering correctness.

## Current Assessment

The frontend has a sound multi-pass shape:

- reader and S-expression parsing
- syntax objects with spans and expansion provenance
- module loading and import resolution
- macro expansion
- definition and expression elaboration
- type and effect checking
- workflow lowering
- source-map and build-artifact emission

The main refactoring risk is not a missing architecture. The risk is accretive
complexity inside the implementation of that architecture:

- very large dispatch functions and helper clusters
- uneven use of context objects between passes
- repeated validation and diagnostic construction patterns
- long lowering helpers with mixed responsibilities
- difficult-to-see ownership boundaries between typed frontend state, lowered
  workflow dictionaries, source maps, and build artifacts

## Non-Goals

Do not use this backlog to:

- remove the pass-oriented compiler architecture
- replace structured diagnostics with plain exceptions
- weaken source spans, form paths, expansion stacks, or lowering origins
- convert immutable AST/state objects back to mutable ad hoc dictionaries
- implement missing full-design features such as new language forms
- redesign the runtime DSL or workflow executor
- perform broad style cleanup without a measurable maintenance benefit

## Backlog

| Priority | Item | Main files | Outcome |
| --- | --- | --- | --- |
| P0 | Split lowering responsibilities by operation family | `lowering.py` | Smaller, named lowering modules or sections with explicit ownership and no behavior change. |
| P0 | Add a typecheck context object | `typecheck.py` | Replace repeated environment/catalog/scope argument drilling with one explicit context value. |
| P0 | Characterize high-risk compiler behavior before refactors | `tests/test_workflow_lisp_*`, fixtures | Focused regression coverage for existing behavior that refactors must preserve. |
| P1 | Extract reusable diagnostic builders | `diagnostics.py`, pass modules | Reduce repeated diagnostic construction while preserving exact codes, spans, and expansion stacks. |
| P1 | Consolidate pass-local validation helpers | `definitions.py`, `workflows.py`, `procedures.py`, `typecheck.py` | Common validation idioms are easier to inspect and change. |
| P1 | Clarify source-map/build-artifact ownership | `source_map.py`, `build.py`, `lowering.py` | One documented path for where provenance is created, transformed, serialized, and validated. |
| P1 | Right-size central expression dispatch | `typecheck.py`, `lowering.py` | Dispatch remains explicit but becomes easier to extend and review. |
| P2 | Review naming length and helper layering | `workflow_lisp/*.py` | Long names remain only where they disambiguate real concepts. |
| P2 | Identify and retire migration scaffolding | `workflow_lisp/*.py`, tests | Remove compatibility helpers only after callers and fixtures prove they are obsolete. |
| P2 | Module-level dependency audit | `workflow_lisp/*.py` | Reduce circular reasoning and accidental coupling between compiler passes. |

## P0 Details

### 1. Split lowering responsibilities by operation family

Problem:

`lowering.py` is large enough that unrelated responsibilities are hard to
review together. It contains expression dispatch, provider/command lowering,
phase library lowering, drain library lowering, call/procedure lowering,
workflow-reference support, source-origin handling, output-contract flattening,
and validation remapping.

Refactoring target:

- Keep `lower_workflow_definitions` and `validate_lowered_workflows` as the
  public entrypoints.
- Move operation families behind small internal modules only when the boundary
  is obvious.
- Keep shared context and origin recording explicit.
- Avoid a plugin registry or visitor framework unless it demonstrably reduces
  complexity.

Candidate slices:

- provider, command, and structured-result lowering
- phase-standard-library lowering
- resource/drain-standard-library lowering
- call, procedure, and workflow-reference lowering
- output-contract flattening and local-value rendering
- source-origin and validation-remapping helpers

Acceptance criteria:

- No generated workflow behavior changes.
- Source-map and diagnostic tests still exercise the same public behavior.
- Each extracted module owns a coherent operation family rather than a random
  range of line numbers.

### 2. Add a typecheck context object

Problem:

`typecheck._typecheck` recurses through expressions while passing many separate
environment and catalog parameters. That makes signatures noisy and increases
the chance that future changes thread state inconsistently.

Refactoring target:

- Introduce an internal `TypecheckContext`.
- Keep changing proof scope or value environment explicit through context-copy
  helpers.
- Do not hide semantic changes behind mutable context mutation.
- Preserve public `typecheck_expression` behavior.

Acceptance criteria:

- Recursive typecheck calls pass a context value instead of a long argument
  list.
- Proof-scope changes remain visible at match arms and control-flow boundaries.
- Diagnostic codes and source locations are preserved.

### 3. Characterize high-risk compiler behavior before refactors

Problem:

The frontend has enough behavior that large refactors can accidentally change
diagnostics, generated contracts, source-map provenance, or lowering shape.

Refactoring target:

- Identify representative fixtures for each pass boundary.
- Add or tighten characterization tests only where existing tests do not protect
  the behavior being refactored.
- Prefer semantic assertions over brittle full-output snapshots.

Areas to cover:

- macro expansion provenance
- variant proof and match narrowing
- provider-result and command-result structured outputs
- phase and resource standard-library forms
- workflow calls and workflow references
- source-map origin serialization
- validation-error remapping

Acceptance criteria:

- Refactors have focused tests that fail on meaningful behavior changes.
- Tests do not freeze incidental helper names or module layout.

## P1 Details

### 4. Extract reusable diagnostic builders

Problem:

Many passes construct `LispFrontendDiagnostic` directly. This keeps diagnostics
explicit, but it also encourages repeated boilerplate and small inconsistencies
in message shape.

Refactoring target:

- Add small builders only for repeated patterns.
- Keep diagnostic codes stable.
- Keep span, form path, and expansion stack visible at call sites when that
  improves reviewability.

Examples:

- unsupported form
- duplicate name
- unknown reference
- invalid boundary type
- contract mismatch
- unproved variant field access

### 5. Consolidate pass-local validation helpers

Problem:

Definition, workflow, procedure, type, and lowering passes each contain local
validation idioms. Some repetition is useful because passes have different
authority, but repeated mechanics should not obscure the actual rule.

Refactoring target:

- Keep pass-specific rules in their pass.
- Share low-level mechanics for common syntax checks only where that removes
  duplication without weakening local diagnostics.
- Avoid a generic validator framework.

### 6. Clarify source-map/build-artifact ownership

Problem:

Source origins, build artifacts, deferred shared-contract markers, and validation
remapping cross `lowering.py`, `source_map.py`, and `build.py`. The ownership
story is easy to blur.

Refactoring target:

- Document which module creates provenance, which module serializes it, and
  which module validates artifact coverage.
- Keep debug YAML non-authoritative.
- Keep deferred shared-contract markers explicit until shared Core AST and
  Semantic IR contracts are implemented.

### 7. Right-size central expression dispatch

Problem:

Central dispatch is simple to read in small compilers, but the current typecheck
and lowering dispatch surfaces are large enough that new expression forms risk
making the core functions harder to review.

Refactoring target:

- Preserve explicit dispatch.
- Move large branch bodies into named helpers.
- Group related branches by expression family.
- Avoid per-node methods unless the repo deliberately chooses a visitor-style
  architecture later.

## P2 Details

### 8. Review naming length and helper layering

Problem:

Some helper names are precise but difficult to scan. Long names should pay rent
by distinguishing concepts that are otherwise easy to confuse.

Refactoring target:

- Shorten only names that are locally obvious.
- Preserve long names where they encode an important contract boundary.
- Avoid churn-only renames.

### 9. Identify and retire migration scaffolding

Problem:

The frontend still contains deferred shared-contract markers and compatibility
surfaces. Some are necessary until Core Workflow AST and Semantic IR contracts
land; others may become obsolete as implementation stabilizes.

Refactoring target:

- Inventory helpers that exist only for migration staging.
- Delete only when no active caller, fixture, or design contract depends on
  them.
- Keep historical compatibility explicit when removal is not safe.

### 10. Module-level dependency audit

Problem:

The compiler passes are mostly separated, but dependency direction should remain
easy to explain as modules are split or consolidated.

Refactoring target:

- Produce a short import/dependency map.
- Identify pass-boundary leaks.
- Remove accidental imports that make lower-level modules know about higher
  phases.

## Suggested Order

1. Add or tighten characterization coverage for the specific area being changed.
2. Introduce `TypecheckContext`.
3. Split the largest lowering operation families.
4. Consolidate diagnostics and validation mechanics where repetition remains.
5. Clarify source-map/build-artifact ownership.
6. Audit migration scaffolding after shared Core AST and Semantic IR contracts
   are resolved.

## Completion Criteria

This backlog is complete when:

- `typecheck.py` and `lowering.py` are materially easier to review;
- recursive typechecking no longer relies on long repeated argument lists;
- lowering responsibilities have visible ownership boundaries;
- diagnostics and source provenance remain at least as good as before;
- no full-design feature is removed or silently downgraded;
- tests protect behavior rather than the old file layout.
