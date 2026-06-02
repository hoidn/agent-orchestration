# Workflow Lisp Refactor Architecture

Status: draft architecture guidance
Scope: `orchestrator/workflow_lisp` maintainability and tech-debt reduction
Parent contract: [Workflow Lisp Frontend Specification](workflow_lisp_frontend_specification.md)
Execution plan: [Workflow Lisp Low-Hanging Refactor Implementation Plan](../plans/2026-06-02-workflow-lisp-low-hanging-refactor-plan.md)

## Purpose

This document defines the target architecture for behavior-preserving Workflow
Lisp refactors. It is not a language redesign and it is not a runtime feature
specification. Its job is to keep local cleanup work aligned around stable
module boundaries, explicit compiler infrastructure, and unchanged `.orc`
semantics.

The implementation plan owns task order and commands. This design owns the
boundaries and invariants those tasks must preserve.

## Problem Statement

The current Workflow Lisp implementation has grown by delivering useful
surfaces quickly: structured results, stdlib forms, macro expansion, workflow
refs, ProcRefs, source maps, debug artifacts, and build integration. The result
works, but several modules now carry multiple architectural roles at once.

The main debt patterns are:

- large pass modules that mix orchestration, semantic policy, and mechanical
  transformation;
- repeated expression-tree walkers that must be updated manually for every new
  expression form;
- module-global compiler state in elaboration and typechecking paths;
- private helper imports across pass boundaries;
- duplicated registries for diagnostics, lints, effects, stdlib contracts, and
  generated build artifacts;
- package-root exports that make internal implementation classes look public;
- test fixtures and projection helpers that live beside production code.

The risk is not mainly aesthetics. The risk is semantic drift: a future form can
be parsed and typechecked while purity checks, extern discovery, ProcRef
specialization, source-map generation, or lowering analysis miss it.

## Non-Goals

This refactor must not:

- change authored `.orc` syntax;
- change generated workflow behavior;
- change runtime execution semantics;
- remove the legacy phase bridge;
- weaken diagnostics, source maps, effect visibility, contract validation, or
  generated workflow parity;
- turn debug YAML, rendered docs, pointer files, or reports into authority;
- replace the existing shared workflow validation or runtime.

## Design Principles

The refactor follows the same authority rules as the parent frontend design:

- surface syntax is not authority;
- Core Workflow AST, shared validation, Semantic IR, Executable IR, and runtime
  contracts remain the semantic path;
- macros and stdlib forms cannot hide effects;
- source maps are semantic infrastructure;
- behavior-preserving cleanup must be proven by characterization tests.

The refactor adds one local principle:

> A new compiler form should require one obvious update point for traversal,
> one obvious update point for type/effect semantics, and one obvious update
> point for lowering.

## Target Module Boundaries

### Package Facade

`orchestrator.workflow_lisp` should be a narrow import facade. It should expose
stable caller-facing entrypoints and result/diagnostic types. It should not make
frontend-local helpers, AST implementation details, or lowering internals look
like a public API.

Target public root surface:

- compile/build entrypoints needed by CLI and tests;
- `LispFrontendCompileError`;
- `LispFrontendDiagnostic`;
- diagnostic rendering helpers;
- externally consumed environment/result dataclasses, if any.

Everything else should be imported from its owning module.

### Expression Model And Traversal

Expression node definitions may remain simple dataclasses, but traversal must
be centralized.

Target ownership:

- expression node definitions: expression model module;
- syntax-to-expression elaboration: elaboration module/context;
- child traversal and tree walking: shared traversal utility;
- specialized semantic walkers: implemented on top of shared traversal unless
  they need explicit scoped behavior.

Required invariant:

- every `ExprNode` variant is either covered by child traversal or explicitly
  declared as a leaf/specialized form in a coverage test.

### Elaboration And Typecheck Context

Elaboration and typechecking should not rely on process-global mutable state.
Module globals make reentrancy, nested compile operations, and direct helper
tests fragile.

Target ownership:

- `ExpressionElaborationContext`: resolver state, loop/let-proc scope, and
  macro-expanded syntax provenance used during expression elaboration;
- `TypecheckContext`: catalogs, value environments, ProcRef environments,
  loop context, generated local procedures, workflow signature, and reusable
  state producer context.

Compatibility wrappers may remain during migration, but new code should receive
an explicit context object.

### Compiler Pipeline

`compiler.py` should coordinate passes, not own every pass boundary.

Target ownership:

- pipeline entrypoints and result assembly stay in compiler coordination;
- graph compilation accumulators move into a named compile-state object;
- command adapter defaults move to a stdlib/adapter registry;
- executable-validation remapping is exposed through public lowering/source-map
  APIs, not private helper imports;
- single-file and linked-module stage-3 paths share a common pipeline object.

### Lowering

Lowering is the most important split. It is allowed to remain the runtime-facing
frontend boundary, but operation families should not all live in one file and
one mutable context.

Target ownership:

- lowering facade: public entrypoints and compatibility exports;
- lowering context: split into frozen config, lexical scope, and mutable output
  sinks;
- structured-result lowering: provider-result, command-result, produce-one-of;
- phase lowering: with-phase, phase-target, run-provider-phase,
  review-revise-loop, resume-or-start;
- resource/drain lowering: resource-transition, finalize-selected-item,
  backlog-drain;
- procedure lowering: inline/private/specialized procedure workflow generation;
- source-map bridge: generated step origins, hidden input origins, validation
  subject remapping.

The package split may happen before or after the first helper extractions, but
the long-term shape should preserve `orchestrator.workflow_lisp.lowering` as a
facade while moving implementation clusters behind it.

### Contracts And Type Projection

Contract projection should have one source of truth for flattening,
discriminants, bundle paths, path refinements, and lowerability rules.

Target ownership:

- boundary projection: workflow input/output flattening;
- structured result contracts: `output_bundle` and `variant_output` shapes;
- reusable-state contracts: phase-state fingerprints and reusable variants;
- stdlib contract identity: stable module/type identity helpers, not filesystem
  suffix checks.

Collision checks must happen at compile time where possible, not only after
runtime output-contract construction.

### Effects

Effects need a single registry that maps authored spelling, internal atom,
render label, Semantic IR kind, and authorable/internal policy.

Target ownership:

- effect vocabulary and parsing: effect registry;
- effect occurrence/provenance: separate from hashable effect atoms;
- local and transitive summaries: explicit names such as `local_effects`,
  `resolved_effects`, and `procedure_edges`;
- generated semantic effects: either wired into the same model or kept as a
  clearly separate generated-effect model.

### Diagnostics And Lints

Diagnostics and lints should fail closed. Unknown metadata should be explicit,
not silently classified as parse/read.

Target ownership:

- diagnostic code registry: code to validation pass, authority layer, and
  default metadata;
- lint rule registry: code, status, severity by profile, owner, replacement
  hint, and serialization metadata;
- validation pass catalog: one exported source used by diagnostics, validation,
  and compiler pipeline selection.

Severity strings and pass names should be validated at import time or represented
by typed constants.

### Macros

Macro expansion should remain syntax-only. Hygiene can be grammar-aware, but it
must fail through owned diagnostics rather than uncaught shape errors.

Target ownership:

- macro definition parsing and expansion;
- syntax template instantiation;
- introduced-name hygiene;
- expansion stack preservation.

Macro hygiene must not own downstream semantics. Malformed macro output should
keep macro provenance and then be rejected by normal elaboration/typecheck
validators.

### Build Artifacts And Debug Projections

Build artifact emission should be registry-driven. Debug YAML and source-map
documents are projections, not authority.

Target ownership:

- artifact registry: artifact name, filename, exportability, serializer, and
  manifest status;
- durable serializers: explicit and fail-fast for stable artifacts;
- debug serializers: allowed to be more permissive, but clearly marked as
  debug-only.

## Refactor Seams

The low-risk seams are:

1. concrete hazard fixes that do not change intended behavior;
2. expression traversal utility and coverage tests;
3. context objects with compatibility wrappers;
4. lowering facade plus extracted helper modules;
5. registry hardening for diagnostics/lints/effects/build artifacts;
6. package-root API narrowing;
7. fixture-only code movement into test support.

These seams are intentionally incremental. A broad rewrite of `lowering.py` or
`typecheck.py` before traversal and context cleanup would create unnecessary
regression risk.

## Compatibility Strategy

Each extraction should preserve imports first and move ownership second.

Allowed migration tools:

- re-export shims from old module paths;
- compatibility properties on renamed dataclass fields;
- focused characterization tests before extraction;
- staged commits by module family;
- explicit notes for pre-existing test failures.

Not allowed:

- changing `.orc` syntax to make refactoring easier;
- weakening tests that enforce semantic contracts;
- replacing source-mapped diagnostics with raw exceptions;
- accepting hidden effects or report/pointer authority drift.

## Verification Strategy

Every tranche should run:

```bash
python -m compileall orchestrator/workflow_lisp
git diff --check
```

Each module-family extraction should run the narrowest relevant pytest selectors.
Before claiming broad Workflow Lisp health, run:

```bash
pytest tests/test_workflow_lisp_* -q
```

If a selector has known unrelated failures, record the exact command and output
in the implementation notes. Do not let pre-existing failures become ambiguous
refactor regressions.

## Open Decisions

- Whether `orchestrator/workflow_lisp/lowering.py` should become a
  `lowering/` package before or after the first helper extractions.
- Exact stable root-package API.
- Whether effect atoms and generated semantic effects should unify immediately
  or remain separate with explicit boundaries.
- Whether source-map lineage should move closer to lowering, shared IR, or a
  dedicated lineage module.
- How much exact generated-YAML shape should remain in tests versus moving to
  semantic assertions.

## Implementation Handoff

Use the execution plan at
[Workflow Lisp Low-Hanging Refactor Implementation Plan](../plans/2026-06-02-workflow-lisp-low-hanging-refactor-plan.md).
The first implementation tranche should address the concrete hazards and
expression traversal before larger package or registry moves.
