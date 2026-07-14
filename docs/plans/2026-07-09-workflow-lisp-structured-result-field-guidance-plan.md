# Workflow Lisp Structured-Result Field Guidance Implementation Plan

> **Status:** Superseded on 2026-07-10. Do not execute this provisional plan.
> Its scope was expanded and replaced by the accepted design
> `docs/design/workflow_lisp_native_transportable_returns.md` and the reviewed
> execution sequence:
> `docs/plans/2026-07-10-workflow-lisp-native-transportable-returns-plan.md`
> followed by
> `docs/plans/2026-07-10-workflow-lisp-typed-result-guidance-plan.md`.
> Both replacement plans are complete; DSL v2.15 is public. The
> procedure-first resolved-effect substrate is the current selector.

> **Historical record:** Everything below this notice preserves the superseded
> proposal for provenance only. Its dependencies, tasks, checkboxes, and
> execution instructions are obsolete; follow the two replacement plans above.

**Goal:** Let Workflow Lisp type declarations attach reusable semantic guidance
to structured-result fields so generated provider output-contract prompts
explain field meaning and examples without changing type or runtime semantics.

**Architecture:** The accepted frontend contract will own annotation syntax and
compile-time meaning. Typed definitions will retain validated guidance through
schema expansion, imports, generic specialization, record flattening, and union
lowering. Generated contracts will expose renderer-compatible `description`,
`format_hint`, and `example` metadata; prompt rendering may consume it, while
validation, optionality, routing, and runtime value semantics ignore it.

**Tech Stack:** Workflow Lisp syntax/elaboration/typechecking, generated
structured-result contracts, Core/Semantic/Executable IR projections,
source-map lineage, provider prompt-contract rendering, pytest.

---

## Roadmap position

- **Design:** Procedure-first roadmap Stage 4, as an explicit delta to
  `docs/design/workflow_lisp_frontend_specification.md`.
- **Implementation:** First bounded typed-return substrate item in Stage 5,
  before the procedure-first pilot and before other independently discovered
  substrate gaps.
- **Status:** Pending / not selectable.
- **Current-sequence effect:** None. Stages 1-3 retain the active order:
  runtime union-field lineage, boundary closure, then drain migration and
  retirement.

## Dependencies

1. Roadmap Gate S3 closes the parametric drain route and its cleanup lanes.
2. Stage 4 accepts a frontend-spec delta resolving every design question below.
3. This plan is revised with exact accepted syntax, file ownership, examples,
   tests, commands, and commit boundaries, then passes plan review.
4. Stage 5 begins; this item executes before the procedure-first pilot.

These dependencies form a one-way chain `S3 -> Stage 4 design -> guidance
substrate -> procedure-first pilot`; this plan introduces no dependency back to
Stages 1-3 or to the pilot.

## Current capability evidence

- `RecordField` currently retains only `name`, `type_name`, and `span` in
  `orchestrator/workflow_lisp/definitions.py`.
- `_elaborate_field_member` currently accepts only `(name Type)` or a schema
  include, so annotations cannot be authored.
- generated Workflow Lisp structured-result contracts carry type and runtime
  validation constraints but no semantic field guidance;
- `orchestrator/contracts/prompt_contract.py` already renders
  `description`, `format_hint`, and `example` when those keys reach a bundle
  field.

This proves a frontend propagation gap, not a prompt-renderer gap.

## Stage 4 design gate

The frontend-spec delta must decide the following before production code is
edited.

### Annotation syntax and ownership

- exact optional syntax for field `description`, `format_hint`, and `example`;
- source spelling versus generated-contract spelling, including whether
  `:format-hint` lowers to `format_hint`;
- whether annotations are allowed only on record/union payload fields or also
  on enum members and union variants;
- duplicate-key, unknown-key, empty-string, and annotation-order behavior;
- whether `example` is authored as a typed literal, a string to be parsed, or a
  deliberately narrower first-tranche form.

The accepted syntax must not introduce `:required`; optionality remains owned
only by `Optional[T]`.

### Composition and propagation

- how `defschema` declares and propagates guidance;
- conflict/override rules when schema includes and local fields meet;
- import/export preservation and module-qualified identity;
- generic specialization and whether guidance contributes to specialization
  identity or semantic fingerprints;
- nested-record flattening, including which declaration owns guidance for a
  flattened leaf;
- union shared-field and variant-specific lowering, including same-name fields
  with different guidance in different variants;
- source-map attribution for guidance errors and generated metadata.

### Compile-time validation

- `description` and `format_hint` string validation;
- type compatibility rules for examples across primitive, enum, path,
  optional, list, map, record, and union types;
- whether path examples are checked structurally only or against filesystem
  existence constraints;
- stable diagnostic codes and subject/source attribution;
- fail-closed behavior for annotations that cannot survive a supported
  lowering path.

### Representation boundaries

- typed definition and type-environment representation;
- Core AST, Semantic IR, and Executable IR visibility versus omission;
- generated `output_bundle` and `variant_output` wire metadata;
- source-map relationship without making guidance semantic authority;
- provider prompt rendering for fixed, shared, and variant-specific fields;
- build/debug serialization and compatibility with older artifacts.

### Required invariant

Guidance may affect provider prompts and human-facing diagnostics only. It must
not alter optionality, accepted runtime values, contract validation,
variant-proof rules, routing, checkpoint identity, resume behavior, effect
semantics, or artifact authority.

## Provisional implementation waves

The following waves reserve ownership and acceptance scope. Their detailed
steps are intentionally provisional until the Stage 4 contract supplies exact
syntax and semantics.

### Task 1: Parse and retain accepted declaration metadata

**Expected owners:**
- `orchestrator/workflow_lisp/definitions.py`
- syntax/definition tests selected by the accepted design

- [ ] Add RED parser/elaboration tests for every accepted annotation site.
- [ ] Extend immutable typed definitions without changing unannotated forms.
- [ ] Reject unknown, duplicated, malformed, or unsupported annotations with
  stable diagnostics and authored spans.
- [ ] Prove old `(name Type)` declarations serialize and compare unchanged.

### Task 2: Typecheck examples and composition rules

**Expected owners:**
- Workflow Lisp definition/type environment and typechecking owner modules
- schema/import/generic tests selected by the accepted design

- [ ] Add RED tests for each accepted example type and each rejection class.
- [ ] Implement schema include, import, and specialization propagation exactly
  once in the type-definition pipeline.
- [ ] Prove guidance does not affect type identity, specialization identity,
  semantic fingerprints, or optionality.

### Task 3: Propagate guidance through structured-result lowering

**Expected owners:**
- `orchestrator/workflow_lisp/contracts.py`
- owning lowering modules identified by the Stage 4 call-site audit
- `tests/test_workflow_lisp_structured_results.py`

- [ ] Add RED contract tests for records, nested flattening, shared union
  fields, and variant-specific fields.
- [ ] Emit renderer-compatible `description`, `format_hint`, and `example`
  only where the accepted declaration owns them.
- [ ] Prove the metadata survives classic/WCC lowering, imports, generics, and
  procedure-return composition without name-specific branches.

### Task 4: Project guidance through IR and source maps

**Expected owners:**
- Core/Semantic/Executable IR projection modules selected by the design
- `orchestrator/workflow_lisp/source_map.py`
- IR/source-map tests selected by the design

- [ ] Add RED tests for the accepted IR visibility contract.
- [ ] Preserve authored source ownership for guidance and guidance errors.
- [ ] Prove guidance is representation metadata, not executable or resume
  authority.

### Task 5: Render provider prompts and prove runtime neutrality

**Expected owners:**
- generated provider contract/prompt integration paths
- `orchestrator/contracts/prompt_contract.py` only if the accepted design
  proves the existing renderer needs a generic fix
- prompt-contract, output-contract, and integration tests

- [ ] Compile a real annotated `.orc` provider result and assert generated
  prompt guidance for fixed, shared, and variant-specific fields.
- [ ] Compare annotated and unannotated runtime validation over identical
  values and prove equal validity, artifacts, routing, and exit behavior.
- [ ] Run one end-to-end orchestrator usage check through the production build
  and provider-prompt path.

### Task 6: Documentation and capability promotion

- [ ] Update the drafting guide with accepted syntax and non-authority rules.
- [ ] Promote the capability matrix row only from fresh implementation,
  integration, and runtime-neutrality evidence.
- [ ] Record exact verification, compatibility, and any deferred enum/variant
  guidance surface.

## Plan activation gate

Before changing the status from Pending:

- the Stage 4 frontend-spec delta is accepted;
- all design decisions above have one unambiguous answer;
- the provisional waves are replaced with exact paths, TDD examples, commands,
  expected RED failures, and commit boundaries;
- a plan-document reviewer approves the revised plan;
- Gate S3 is complete and no active migration owns overlapping frontend files.

Until then, this document is discoverable roadmap intent and dependency
authority, not permission to implement a guessed syntax.
