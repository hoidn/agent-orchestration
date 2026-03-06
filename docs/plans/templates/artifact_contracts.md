# Workflow Demo Artifact Contracts

This document defines the artifact vocabulary for the generic single-input workflow demo.

These are I/O contracts. They are intended to map directly to workflow `publishes` and `consumes` declarations.

This document is normative for artifact meaning.
Templates in this directory are authoring aids only.

## Backbone Artifacts

### `task`
- Kind: relpath
- Suggested canonical path: `state/task.md`
- Producer: setup or task-capture step
- Primary consumers: nearly all provider steps
- Meaning: the original user task description, persisted without paraphrase or narrowing

### `plan`
- Kind: relpath
- Suggested canonical path: `docs/plans/current-plan.md`
- Producer: plan-drafting or plan-revision step
- Primary consumers: plan review, execution, implementation review, fix
- Meaning: the current executable plan for the task

### `check_strategy`
- Kind: relpath
- Suggested canonical path: `state/check_strategy.md`
- Producer: plan-drafting or plan-revision step
- Primary consumers: plan review, execution, implementation review, fix
- Meaning: the current visible verification strategy for the task, including intended checks, expected gaps, and why the chosen checks are high-signal

## Plan-Loop Artifacts

### `plan_review_report`
- Kind: relpath
- Suggested canonical path: `artifacts/review/plan-review.md`
- Producer: plan-review step
- Primary consumers: plan-revision step
- Meaning: evidence-backed critique of plan quality and verification adequacy

### `plan_review_decision`
- Kind: scalar enum
- Allowed values: `APPROVE`, `REVISE`
- Producer: plan-review step
- Primary consumers: plan-loop gate
- Meaning:
  - `APPROVE`: plan is executable and verification strategy is credible enough to proceed
  - `REVISE`: plan or verification strategy has blocking issues and must be updated before execution

## Implementation-Loop Artifacts

### `execution_report`
- Kind: relpath
- Suggested canonical path: `artifacts/work/execution-report.md`
- Producer: execution or fix step
- Primary consumers: implementation review, later fix steps
- Meaning: concise handoff record of what was attempted and what changed

Required content:
- plan used
- files changed
- commands executed
- tests or checks added or modified
- claimed completion status
- blockers or unresolved risks

### `check_plan`
- Kind: relpath
- Suggested canonical path: `state/check_plan.json`
- Producer: execution or fix step
- Primary consumers: check runner, implementation review, later fix steps
- Meaning: the current runnable visible verification plan derived from the task, plan, repo state, and any tests/checks created during implementation

### `check_results`
- Kind: relpath
- Suggested canonical path: `artifacts/checks/check-results.json`
- Producer: check-running step
- Primary consumers: implementation review, fix
- Meaning: structured result of executing the current `check_plan`, including malformed-check and missing-executable failures when those occur

### `implementation_review_report`
- Kind: relpath
- Suggested canonical path: `artifacts/review/implementation-review.md`
- Producer: implementation-review step
- Primary consumers: fix step
- Meaning: evidence-backed review of implementation correctness relative to the task and plan

### `implementation_review_decision`
- Kind: scalar enum
- Allowed values: `APPROVE`, `REVISE`
- Producer: implementation-review step
- Primary consumers: implementation-loop gate
- Meaning:
  - `APPROVE`: no blocking correctness issues remain
  - `REVISE`: concrete blocking issues remain and must be fixed

## Contract Discipline

- `task`, `plan`, and `check_strategy` are backbone artifacts and should usually be consumed by later provider steps.
- `check_plan` is implementation-loop state and should be refreshed when execution adds or changes runnable verification.
- Stage-local artifacts should be consumed only where they add signal.
- Review reports are evidence artifacts, not conversational transcripts.
- Decision artifacts must be binary and machine-usable.
- Raw logs may exist separately, but downstream logic should depend on the contracts above rather than on free-form narrative.
