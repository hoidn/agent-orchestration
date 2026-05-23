# Work Definition Model

Status: informative

This document explains how this repo separates semantic definitions from
procedural work instructions and workflow mechanics.

## Core Split

Specs and design contracts define what must be true.

Work instructions define what to do, in what order, and under what constraints
for a specific body of work.

Workflow YAML defines the executable process that selects, routes, runs,
records, and resumes work.

Run state, ledgers, reports, and artifacts record what happened.

## Terms

### Spec Or Design Contract

A spec or design contract defines correctness.

Examples:

- DSL semantics;
- state and artifact authority;
- provider and command contracts;
- Workflow Lisp frontend language rules;
- Core AST, IR, effect, proof, and source-map behavior.

Specs and design contracts should say what is valid, what is invalid, and which
values are authoritative. They should not become step-by-step instructions for a
temporary body of work.

### Work Instructions

Work instructions are procedural prescriptions for a specific body of work.

They may define:

- objective;
- work order;
- priorities;
- constraints;
- required source material;
- completion target.

They should not redefine semantic correctness. If work instructions conflict
with a spec or approved design contract, the spec or design contract wins.

They also should not define workflow mechanics such as selector routing, resume
behavior, ledger updates, or terminal-state bookkeeping. Those belong in the
workflow and its step contracts.

### Work Item

A work item is one bounded obligation that can be planned, implemented, checked,
and recorded.

A work item should have enough scope and acceptance criteria for a workflow or
agent to execute it without inventing the definition of success.

### Workflow Mechanics

Workflow mechanics are executable control behavior.

Examples:

- selecting the next item;
- deciding whether a missing work definition must be drafted;
- routing completed, blocked, or empty states;
- updating run state and progress ledgers;
- resuming prior state;
- publishing summaries and artifacts.

These mechanics belong in workflow YAML, reusable workflow libraries, scripts,
and prompt contracts for the relevant workflow step. They are not part of the
work instructions.

### Run Evidence

Run evidence records what happened.

Examples:

- run state;
- progress ledgers;
- iteration summaries;
- execution reports;
- review reports;
- generated artifacts.

Evidence can justify future work, but it is not itself a new work obligation
until converted into a work item or reflected in work instructions.

## Relationship

```text
specs/design contracts
  define what must be true

work instructions
  define what this body of work should do

work items
  define bounded executable obligations

workflow mechanics
  select, route, execute, record, and resume

run evidence
  records what happened
```

The important boundary is that specs hold semantic invariants, while work
instructions hold procedural prescriptions for the current body of work.

## Document Use Matrix

Use this table as a practical guide for which workflow role should rely on which
document kind.

| Document Kind | Drain Workflow | Selector | Design-Gap Architect | Planner | Implementer | Reviewer/Checker | Ledger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Spec / design contract | Pass through | Use to identify obligations and gaps | Use as constraints | Use as constraints | Use as constraints | Check result against | Reference only |
| Work instructions | Pass through | Use for priority, sequencing, and constraints | Use for scope and sequencing | Reference only | Reference only | Reference only | Reference only |
| Active backlog item | Route | Select when ready | Reference only | Plan if selected | Implement if plan approved | Judge result against | Record outcome |
| Design-gap architecture/work-item bundle | Route | Request when needed | Produce | Plan after produced | Implement if plan approved | Judge result against | Record outcome |
| Execution plan | Route | Reference only | Produce only when part of selected bundle | Produce | Follow | Compare result to plan | Record outcome |
| Check commands / check instructions | Route | Use for readiness when present | Include when drafting selected bundle | Include or preserve | Run or satisfy | Use to judge result | Record result |
| Run state / progress ledger | Own | Use heavily | Use as context | Use as context | Use as context | Append evidence when applicable | Own |
| Execution/review report | Record | Use as evidence only | Use as evidence only | Reference as context | Produce execution report | Produce or check review report | Reference only |

In the table, "own" means the role maintains or updates that artifact type.
"Reference only" means the role may cite the document as context or evidence but
should not treat it as a new obligation or a second source of acceptance
criteria.
