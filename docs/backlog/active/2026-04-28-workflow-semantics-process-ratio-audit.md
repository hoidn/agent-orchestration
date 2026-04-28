# Backlog Item: Audit Workflow Semantics And Process Ratio

- Status: active
- Created on: 2026-04-28
- Plan: none yet

## Problem

Some workflow-generated design, plan, and review artifacts can become hard to
judge because substantive domain semantics are mixed with large amounts of
process scaffolding, provenance, routing language, and defensive acceptance
rules. A certain amount of process text is necessary for repeatable workflows,
but too much can hide whether the artifact actually defines the behavior being
implemented.

The failure mode is not just verbosity. Reviewers and implementers may treat a
process-complete artifact as semantically complete, even when the domain model,
runtime contract, target behavior, or acceptance evidence is under-specified.

## Desired Outcome

Create a lightweight audit practice for workflow families that asks:

> Does this workflow produce artifacts with enough real task semantics to guide
> implementation and review, or is it mostly process/provenance scaffolding?

The audit should improve prompts, templates, skills, and examples so generated
artifacts are easier to read and harder to approve when they lack substantive
behavioral content.

## Scope

- Major-project roadmap, design, plan, implementation, and review prompts.
- Generic design and plan templates that shape workflow-generated artifacts.
- Workflow authoring guidance about the split between domain semantics,
  artifact contracts, deterministic routing, provenance, and review process.
- Representative existing workflow outputs used as audit samples.

## Required Guidance

- Distinguish at least these categories when auditing an artifact:
  - domain/runtime/API semantics
  - acceptance and evidence semantics
  - artifact-contract mechanics needed for automation
  - provenance, routing, status, and handoff process
  - repeated defensive boilerplate
- Treat artifact-contract mechanics as potentially semantic when they prevent
  known workflow failure modes, but require them to be tied to a real behavior
  or acceptance decision.
- Prefer shortening repeated context and handoff sections before weakening
  target behavior, invariants, or acceptance criteria.
- Reviewers should flag artifacts that are process-complete but do not define
  enough concrete behavior for implementation or review.
- Prompts and templates should ask for concise provenance and routing context,
  with most document weight reserved for the task-specific semantics and the
  evidence needed to verify them.

## Non-Goals

- Do not create a rigid numeric pass/fail threshold for semantics versus
  process text.
- Do not add prompt-text snapshot tests or tests that depend on exact wording.
- Do not remove necessary artifact contracts, lineage, or review evidence just
  to reduce line count.
- Do not make this specific to EasySpin, PyTorch, MATLAB parity, or any other
  downstream project.
- Do not require every workflow artifact to use the same section names.

## Success Criteria

- A small audit report samples several workflow-generated artifacts and labels
  which sections are semantic, automation-contract, or process-heavy.
- Follow-on prompt/template edits reduce repeated process bulk while preserving
  necessary contracts and review evidence.
- Review guidance explicitly treats "lots of workflow prose, little concrete
  behavior" as a review smell.
- Future workflow artifacts make the substantive target behavior and acceptance
  evidence easier to find than the routing or provenance scaffolding.
