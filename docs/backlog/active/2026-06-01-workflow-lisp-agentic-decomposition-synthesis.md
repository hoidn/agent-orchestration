# Backlog Item: Agentic Decomposition To Workflow Lisp

- Status: active
- Created on: 2026-06-01
- Plan: none yet

## Problem

Current Workflow Lisp authoring assumes the human or workflow author has already
chosen the decomposition shape: one provider step, a helper `defproc`, a
subworkflow, a review loop, a drain, or a reusable module. The implemented
compile-time higher-order surface (`ProcRef`, `bind-proc`, and `let-proc`) is
useful once that shape is known, but it does not let an agent decide the right
degree and form of workflow decomposition for a new task.

That leaves a gap between:

- unstructured provider execution, where an agent handles a whole task inside
  one opaque prompt; and
- fully hand-authored `.orc`, where the decomposition is explicit, typed,
  validated, reviewable, and reusable.

The desired capability is not runtime first-class functions and not inline
English `eval`. It is a staged authoring feature where a goal brief can be
turned into an explicit Workflow Lisp module whose decomposition choices are
visible, validated, reviewed, and then executed through the ordinary workflow
pipeline.

## Intended Capability

Given a task goal or English brief, an agent should be able to choose an
appropriate workflow structure:

- whether the task should stay one provider step or become multiple phases;
- whether it needs plan/review/fix loops;
- which typed inputs, outputs, reports, and artifacts should exist;
- which substeps should become reusable `defworkflow` or `defproc` modules;
- where validation, review, or human approval is warranted;
- how much structure is justified by task risk, repetition, and expected reuse.

The result should be materialized Workflow Lisp source, not hidden runtime
behavior:

```text
goal brief
  -> agent proposes decomposition
  -> agent emits `.orc` module
  -> compiler parses, typechecks, and lowers it
  -> shared validation and executable IR validation run
  -> optional review/approval gate accepts or rejects it
  -> generated workflow is called like any other workflow
```

## Candidate Authoring Surface

The eventual surface might look like a staged standard-library form, but the
exact syntax is intentionally not selected yet:

```lisp
(synthesize-workflow
  :goal "Run the implementation task, review it, apply bounded fixes if needed,
         and return APPROVED or BLOCKED with report artifacts."
  :inputs ImplementationTask
  :returns ReviewedImplementationResult
  :policy reviewed)
```

This should be understood as a request to synthesize a concrete `.orc` module,
not as a runtime expression that directly executes English.

Better names to evaluate:

- `synthesize-workflow`
- `decompose-to-workflow`
- `draft-workflow-module`

Avoid names such as `expand-to-workflow` if they imply ordinary macro expansion
from a known template. The important behavior is agent-selected decomposition,
not syntactic abbreviation.

## Required Boundaries

This feature must preserve the current Workflow Lisp authority model:

- generated `.orc` source is a durable artifact;
- generated source, prompt, model/provider metadata, inputs, review decision,
  compile artifacts, and validation results are recorded as provenance;
- execution uses the exact generated source that was validated, not a
  regenerated answer from the same English brief;
- generated workflows lower through Core Workflow AST, shared validation,
  Semantic IR, Executable IR, source maps, and the existing runtime;
- generated modules are called through ordinary workflow/module references
  after validation;
- provider, command, artifact, state, and review effects remain visible in
  generated artifacts and source maps;
- failures are explicit: generation failure, compile failure, validation
  failure, review rejection, or execution failure.

## Non-Goals

This item must not introduce:

- runtime first-class functions or runtime closures;
- inline English `eval`;
- provider output that executes in the same step that generated it;
- hidden workflow semantics inside provider prose;
- generated code that bypasses shared validation or executable IR validation;
- regeneration on resume instead of replaying the validated generated source;
- provider-selected callable values stored in workflow state, artifacts,
  provider results, command results, or ledgers;
- a general-purpose macro or plugin system.

## Design Questions

A follow-on design should answer:

- Is this a Workflow Lisp standard-library form, a workflow template, a CLI
  command, or a higher-level orchestration pattern?
- What policy levels are supported: compile-only, review-required,
  human-approval-required, or trusted-library-only?
- What typed contract does the synthesis provider return?
- How are generated module names, stable ids, source roots, prompt assets, and
  artifact paths chosen?
- How does the generated workflow import existing modules without creating
  ambiguous or unstable dependencies?
- What source-map/provenance links connect the English brief to generated `.orc`
  forms and then to Core/Semantic/Executable IR?
- What prevents prompt injection or task text from weakening validation,
  command-boundary, write-root, or artifact authority?
- How is resume handled when synthesis completed but execution did not?
- When does a synthesized workflow become reusable checked-in source versus a
  one-run generated artifact?

## Acceptance Criteria

This item is complete when there is an approved design and at least one
execution-ready implementation plan for staged agentic decomposition into
Workflow Lisp.

The design must include:

- a crisp distinction between agentic decomposition, macros, templates,
  compile-time `ProcRef` composition, and runtime closures;
- the exact artifact contract for generated `.orc` source and provenance;
- the validation and review gates before generated workflow execution;
- resume/replay rules that reuse validated generated source;
- source-map expectations from brief to generated source to runtime-facing IR;
- failure modes and recovery paths;
- a minimal pilot scenario, preferably a small reviewed implementation phase or
  single-backlog-item stack;
- negative cases proving English/provider output cannot bypass validation,
  command-adapter policy, path safety, or runtime closure deferral.

## Related Context

- `docs/lisp_workflow_drafting_guide.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_macro_surface_contract.md`
- `docs/design/workflow_lisp_runtime_closures_boundary.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/backlog/active/2026-04-29-workflow-authoring-frontend.md`
- `docs/backlog/active/2026-05-29-workflow-lisp-kiss-workflow-ergonomics.md`
