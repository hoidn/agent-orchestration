# Backlog Item: Typed Workflow AST / Executable IR Boundary

- Status: active
- Created on: 2026-03-09
- Plan: none yet

## Scope
Introduce a typed in-memory language pipeline between authored YAML and runtime execution without turning the orchestrator into a full compiler project. The target is a middle ground:
- keep YAML as the authored source language
- parse and validate it into a typed surface AST
- lower structured statements into a typed executable IR
- make the executor and its collaborators consume that lowered IR instead of raw `dict[str, Any]` workflow objects

This item is about internal language/runtime architecture, not user-facing syntax changes. It should preserve current external DSL behavior and `state.json` semantics unless a later, separately reviewed design intentionally changes them.

## Why This Is Backlog-Worthy
The current implementation has real language semantics: version gating, workflow signatures, structured control flow, lowering, scoped refs, stable internal identities, reusable calls, and resume-sensitive loop behavior. But most of the authored program still survives as mutable `dict`/`list` objects through load, validation, lowering, and execution.

That creates avoidable risk:
- parse/validate/lower/execute phases are weakly separated
- authored and lowered forms coexist in one ad hoc representation
- semantics depend heavily on key-presence checks instead of explicit node kinds
- lowering metadata is mixed into general step dictionaries
- executor/runtime services must defensively interpret partially normalized structures

The repo already recognizes the conceptual need for a statement layer in [2026-03-06-dsl-evolution-control-flow-and-reuse.md](../../plans/2026-03-06-dsl-evolution-control-flow-and-reuse.md), but that idea has not yet been turned into a concrete runtime architecture initiative.

## Desired Outcome
This follow-on should leave the workflow runtime with:
- a typed surface AST for authored workflows and structured statements
- a typed lowered IR for executable steps and control-flow helper nodes
- clear phase boundaries: parse -> validate/elaborate -> lower -> execute
- less stringly dispatch across loader, lowering, and executor code
- stable external DSL behavior, workflow examples, and persisted run semantics

The goal is not maximal compiler purity. The goal is to replace the current mutable, mixed-phase representation with a clearer internal contract that makes structured features, resume behavior, and future DSL evolution easier to reason about.

## Middle-Ground Constraints
This item should explicitly avoid a “full compiler rewrite”:
- do not replace YAML with a custom parser or new user-facing syntax
- do not introduce a serialized on-disk IR format
- do not redesign `state.json` as part of the first tranche
- do not bundle broad optimizer or normalization passes unrelated to correctness and maintainability

The intended middle ground is:
1. typed surface AST for authored workflow objects
2. typed executable IR for lowered runtime nodes
3. executor consumes only the lowered IR

## Likely Redesign Targets
The follow-on plan should evaluate these areas explicitly:

1. Surface AST boundary
- define explicit node types for workflow, step kinds, structured statements, and boundary contracts
- move loader validation away from direct mutation of generic dicts

2. Lowered executable IR
- define explicit lowered node types for branch markers, joins, loop frames, finalization steps, and call boundaries
- stop representing lowered helper nodes as ordinary step dictionaries with magic metadata keys

3. Loader/lowering phase separation
- separate authored-shape validation from elaboration and lowering
- make it clear which invariants belong to the surface AST and which belong to the executable IR

4. Executor contract cleanup
- make `WorkflowExecutor`, `LoopExecutor`, and `CallExecutor` consume a stable lowered representation
- reduce branching on key presence and mixed authored/lowered shape interpretation at runtime

5. Test architecture
- add tests that validate surface-AST errors, lowering invariants, and executable-IR behavior independently instead of only end-to-end dict-shaped behavior

## Non-Goals
This backlog item should not be used to justify:
- a large DSL redesign
- changing workflow authoring syntax without a separate proposal
- `state.json` redesign in the same tranche
- plugin frameworks or abstract compiler infrastructure
- performance work as the primary motivation
- deleting the recent executor seam refactors that are already paying off

## Entry Criteria For A Follow-On Plan
Before implementation starts, the follow-on plan should:
- identify the smallest useful AST/IR cut that reduces real complexity
- state exactly which current dict-shaped contracts will remain temporarily during migration
- explain how loader, lowering, and executor phases will coexist during the transition
- name which modules will own the surface AST and lowered IR
- include regression coverage for structured lowering, scoped refs, resume behavior, and call semantics
- define what stays out of scope for the first tranche

## Success Criteria
This backlog item is satisfied only if a follow-on design and implementation:
- replaces raw dict-based authored workflow handling with explicit typed surface nodes in the targeted area
- replaces raw dict-based lowered helper nodes with explicit executable IR nodes in the targeted area
- materially reduces mixed-phase logic in loader/lowering/executor paths
- preserves current external workflow behavior unless a separate design explicitly changes it
- makes future structured-control and reusable-execution features easier to extend without further ad hoc key-based branching
