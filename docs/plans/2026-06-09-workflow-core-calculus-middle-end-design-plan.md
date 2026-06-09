# Workflow Core Calculus / Middle-End Design Plan

Status: plan
Created: 2026-06-09
Scope: draft a new future-target architecture doc,
`docs/design/workflow_lisp_core_calculus_middle_end.md`, proposing the
structural fix behind the composition gaps: a minimal workflow core calculus
plus a real compiler middle-end (ANF normalization, join-point control,
defunctionalization to the existing flat runtime), replacing per-form
lowerers with one general lowering route.

## Motivation

The post-foundation composition target
(`docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`)
is a locally scoped fix: it makes specific nested shapes lower and validate.
The design-delta findings showed the root cause is a missing compiler
middle-end — the typechecker accepts what lowering cannot express, and every
structured form has its own lowerer. The big fix is to re-found lowering on a
small core calculus so composition holds by construction and no future form
needs a one-off lowerer.

## Positioning

- New doc is a future-direction architecture, peer to
  `workflow_lisp_unified_frontend_design.md` in status; it does not replace
  the post-foundation target.
- It commits the strategic choice left open by post-foundation Tranche 1:
  the flattening route (compile to the existing validated model) implemented
  as ANF + join points + defunctionalization, with the nesting-preserving
  executable-IR authority inversion explicitly deferred.
- Post-foundation Tranche 1's "composition-normalized structured control
  graph" is implemented by this architecture when accepted; the two docs must
  not fork.

## Edits

1. Write `docs/design/workflow_lisp_core_calculus_middle_end.md` in house
   style (authority, dependency direction, invariants, incremental tranches
   with contract/tasks/acceptance, design details, contracts and interfaces,
   alternatives considered, evidence boundaries, verification, scenarios,
   success criteria).
2. Add entries to `docs/design/README.md` and `docs/index.md`.

## Verification

- `git diff --check` clean.
- Cross-references resolve to existing files.
