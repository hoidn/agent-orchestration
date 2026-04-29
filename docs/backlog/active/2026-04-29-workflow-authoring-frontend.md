# Backlog Item: Better Workflow Authoring Frontend

- Status: active
- Created on: 2026-04-29
- Plan: none yet

## Scope
Design a better authoring frontend for complex orchestrator workflows while preserving the current YAML DSL as a compatibility and serialization target.

The current hand-authored YAML surface is increasingly brittle for large workflows because it must encode typed inputs/outputs, artifact lineage, prompt assets, reusable calls, structured control, loop outputs, stable ids, and escalation patterns directly in one low-level representation. That representation is readable for small examples, but poor at abstraction, refactoring, symbolic references, and repeated phase-stack patterns.

This item should evaluate a constrained, typed, domain-specific frontend that compiles to the existing workflow YAML or directly to the typed workflow AST/IR. The frontend should serve both human authors and agents generating or editing workflows.

## Candidate Direction
The leading candidate is a small declarative s-expression workflow language, not general Lisp.

Example intent shape:

```lisp
(workflow major-project-drain
  (version 2.12)

  (inputs
    (relpath project-roadmap :under "docs/plans/")
    (relpath tranche-manifest :under "state/"))

  (artifact drain-status
    (enum :allowed [CONTINUE DONE BLOCKED]))

  (repeat-until DrainManifest
    :max 50
    :outputs ((drain-status))

    (call PrepareDrainIterationPaths)
    (let ((result (call RunDrainIteration)))
      (match result.drain-status
        (CONTINUE (continue))
        (DONE     (finish :drain-status DONE))
        (BLOCKED  (finish :drain-status BLOCKED)))))))
```

The frontend should be declarative and macro-capable enough to express recurring workflow patterns such as:

```lisp
(phase-stack T26
  :scope roadmap
  :design tracked-design
  :plan roadmap-consistent-plan
  :implementation reviewed-implementation
  :on-escalate roadmap-revision)
```

The compiler would expand these forms into stable ids, call wiring, `inputs`/`outputs`, `expected_outputs`, `output_bundle`, `consumes`/`publishes`, structured `match`/`repeat_until`, pointer files, and prompt asset references.

## Why Not Typed Python As The Primary Frontend
Typed Python should remain a possible implementation API, but it is not the preferred human/agent-facing syntax:

- it is verbose for declarative workflow shape
- it blurs compile-time workflow description with arbitrary host-language execution
- it encourages helper code and side effects where the orchestrator needs a deterministic authored contract
- it makes safe agent editing harder because ordinary Python has far more semantics than workflow authoring needs

## Why Not Replace YAML Directly
This item should not remove YAML support. YAML should remain:

- the current stable external DSL
- a compatibility input
- a possible compiled artifact for review/debugging
- a migration bridge for existing workflows

The new frontend should be additive and should compile to the same canonical model used by YAML-loaded workflows.

## Relationship To Typed AST / IR Work
This item depends conceptually on the typed workflow AST/IR direction, but it is a separate user-facing syntax question.

The clean architecture is:

1. authoring frontend: constrained workflow language for humans and agents
2. canonical model: typed workflow AST/IR
3. serialization/compatibility: current YAML DSL
4. runtime: executor consumes lowered executable IR

The first design pass should decide whether this frontend should wait for the AST/IR boundary or can land as a compiler that emits current YAML plus strict dry-run validation.

## Desired Outcome
A follow-on design should define:

- the target user experience for humans and agents
- the concrete frontend syntax family
- the compilation target: YAML, typed AST, or lowered IR
- how reusable patterns/macros are represented and reviewed
- how symbolic references replace stringly `root.steps.*` paths
- how stable ids are generated and overridden
- how prompt assets, workflow-boundary inputs, runtime dependencies, and artifact lineage stay separate
- how generated YAML/IR remains inspectable and debuggable
- migration strategy for existing workflows

## Non-Goals
This backlog item should not be used to justify:

- deleting or deprecating existing YAML workflows in the first tranche
- adding a general-purpose Lisp or Python execution environment
- building a visual workflow editor before the typed frontend exists
- hiding generated workflow contracts from review
- changing runtime semantics as part of the syntax experiment
- broad executor rewrites unrelated to the frontend boundary

## Entry Criteria For A Follow-On Plan
Before implementation starts, the plan should:

- compare at least three frontend options: constrained s-expression DSL, typed Python builder, and CUE/Dhall/Jsonnet-like declarative config
- choose one initial frontend and justify why it serves both humans and agents
- specify whether macros/templates are hygienic, declarative expansions, or merely library functions over an AST
- define the smallest useful pilot workflow to rewrite
- define round-trip or generated-output review expectations
- include dry-run and golden-output tests showing the compiled workflow is equivalent to the intended YAML/IR

## Success Criteria
This item is satisfied only if a follow-on design and implementation:

- reduces boilerplate for at least one complex reusable workflow stack
- improves static validation of references, ids, artifacts, and phase-stack wiring
- preserves current YAML workflow behavior
- gives agents a safer editing surface than large YAML files
- gives humans a more concise representation of workflow intent
- keeps generated low-level contracts inspectable enough for debugging and review
