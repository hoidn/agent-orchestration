# Backlog Item: Clarify Workflow Lisp `with-phase` Derived Boundary

Status: active

## Context

`with-phase` is currently implemented as a frontend expression that installs an
active compile-time phase scope for typechecking and lowering. It is not a
runtime operation, but the implementation treats it more specially than ordinary
derived syntax.

This is acceptable as a near-term compiler affordance, but it can become a
design smell if phase scoping grows into a second semantic substrate.

## Goal

Document and enforce the intended boundary:

`with-phase` is frontend sugar for scoped phase-context/path derivation. It must
erase before Core AST / executable IR and must not introduce runtime phase
objects, hidden effects, or a separate lowering model.

## Scope

- Audit current `with-phase` parsing, typechecking, and lowering behavior.
- Document whether `with-phase` is intended to remain a special frontend
  expression or be elaborated into explicit context construction later.
- Add tests or assertions proving no runtime `with-phase` node/value survives
  lowering.
- Ensure phase stdlib forms still require an active phase scope without making
  ambient compiler context broader than necessary.

## Non-Goals

- Do not remove working `with-phase` support.
- Do not redesign the whole phase/context stdlib.
- Do not change runtime state layout unless the audit finds a concrete bug.
- Do not rewrite existing generated gap architecture or execution plan docs.

## Acceptance Criteria

- The Workflow Lisp design docs clearly state that `with-phase` is
  compile-time-only / derived sugar.
- Tests prove lowered Core AST / executable output contains no runtime
  `with-phase` operation or value.
- Any remaining special lowering behavior is justified as source-map, scope, or
  path-derivation support rather than runtime semantics.
- The implementation has a clear follow-up path if `with-phase` should later be
  elaborated before Stage 3 lowering.
