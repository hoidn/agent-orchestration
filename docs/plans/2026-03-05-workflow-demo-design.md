# Workflow Demo Design: Single-Input Agent vs Workflow Comparison

**Status:** Proposed  
**Date:** 2026-03-05  
**Owners:** Orchestrator maintainers

## Goal

Design a fair demo that compares:
- a direct, single-shot agent run in a fresh project workspace
- a workflow-driven agent run in an equivalent fresh project workspace

The workflow should outperform the direct run because it enforces planning, verification, review, and bounded revision loops. The workflow must stay general-purpose. It must not hard-code the task domain into the YAML or prompts.

For harder tasks, the planning phase must include architectural design, not just implementation sequencing, because many likely failures come from poor decomposition rather than missed steps.

The first task family should be a coding task where agent use is self-explanatory, with an initial emphasis on Python-to-Rust translation for ML-adjacent code.

## Non-Goals

- Not a benchmark of raw model capability independent of process.
- Not a domain-specific workflow for Python-to-Rust or ML only.
- Not a demonstration that depends on user feedback mid-run.
- Not a demo where the workflow wins because it sees different repo instructions.

## Success Criteria

The demo is considered successful when all of the following hold:

1. Both arms receive the same `AGENTS.md`, the same initial scaffold, and the same task description.
2. The only substantial difference between the arms is execution process.
3. The workflow visibly exercises at least one revision loop in typical runs.
4. Final evaluation is externally verifiable through a hidden evaluator or equivalent canonical judge that is out of scope for both arms.
5. The workflow prompts remain generic and consume runtime artifacts rather than embedding task-specific instructions.

## Core Design Decision

Use a **single top-level task item** with **two explicit feedback loops**:

1. Plan loop:
   - Draft plan
   - Review plan
   - Revise plan if needed

2. Implementation loop:
   - Execute plan
   - Run checks
   - Review implementation
   - Fix issues if needed

This keeps the first demo focused on process hygiene rather than multi-item decomposition. Backlog directories may still exist in the scaffold because they are useful general process primitives, but the initial workflow does not depend on splitting one task into multiple queue items.

## Shared Scaffold

Both the direct arm and workflow arm should start from equivalent fresh workspaces with the same visible structure:

```text
AGENTS.md
docs/
  index.md
  dev_guidelines.md
  backlog/
    active/
  plans/
    templates/
      plan_template.md
      review_template.md
      check_plan_schema.md
      artifact_contracts.md
src_py/
rust/
artifacts/
  work/
  checks/
  review/
state/
```

Recommended scaffold properties:
- Python reference implementation already runnable.
- Rust project skeleton already present.
- Build tools and dependencies already installed.
- No setup puzzles unrelated to the workflow hypothesis.
- Hidden evaluator remains outside the agent-visible workspace.

## Information Equality

Both arms receive:
- the same original task description
- the same `AGENTS.md`
- the same scaffold repo contents
- the same visible source/reference files

The workflow arm does **not** receive extra domain knowledge. Its advantage comes from:
- explicit artifact contracts
- deterministic step boundaries
- mandatory plan and review gates
- bounded revision loops
- concrete check execution and evidence capture

## Experiment Setup Conventions

The demo needs explicit operational conventions so comparisons are repeatable and not distorted by setup differences.

### Workspace Provisioning

Recommended layout on disk:

```text
<experiment-root>/
  scaffold-template/
  direct-run/
  workflow-run/
  evaluator/
```

Recommended meanings:
- `scaffold-template/`: canonical source tree used to seed both arms
- `direct-run/`: fresh workspace for the direct single-shot run
- `workflow-run/`: fresh workspace for the workflow-driven run
- `evaluator/`: hidden evaluation harness not visible inside either run workspace

Recommendation:
- create both `direct-run/` and `workflow-run/` from the same template commit
- do not let either arm share a working directory with the other
- do not let the hidden evaluator write into either workspace during agent execution
- if the orchestrator requires workflow files to live under the workspace root, stage the workflow YAML and its prompt tree into `workflow-run/` during provisioning

For the first implementation, prefer **separate sibling directories created from the same source snapshot** over clever sharing. This is easier to reason about than trying to make one workspace serve both arms.

### Git Provisioning Model

Recommended model:
- maintain one canonical scaffold repository
- provision each arm as its own git working tree derived from the same starting commit

Acceptable implementations:
1. separate clones from a local seed repository
2. git worktrees from a common bare or non-bare source repository

Recommendation: use **git worktrees** if the provisioning script can do so cleanly, because they guarantee a shared starting commit while avoiding duplicate object storage. Use separate clones if worktree setup introduces operational friction.

The important invariant is:
- both arms start from the same commit
- neither arm sees the other arm's filesystem changes

### Git and Commit Policy

The experiment should define commit policy up front rather than leaving it implicit.

Recommended policy:
- both arms are allowed to create commits
- neither arm is required to commit for success
- hidden evaluation should run against the final filesystem state, not against commit existence

Rationale:
- requiring commits introduces noise unrelated to task correctness
- forbidding commits removes a realistic part of development behavior
- filesystem state is the canonical comparison target for the demo

Additional git rules:
- start each arm on a dedicated branch or detached workspace label
- do not push during the experiment
- do not fetch new external changes during the run
- record the starting commit SHA in each workspace before execution

### Run Lifecycle

Each experimental trial should follow the same lifecycle:

1. Provision `direct-run/` and `workflow-run/` from the same scaffold commit.
2. Materialize the same task description into both workspaces.
3. Verify both workspaces have the same visible files before execution.
4. Run the direct agent once in `direct-run/`.
5. Run the workflow once in `workflow-run/`.
6. Freeze both workspaces at end-of-run.
7. Execute the hidden evaluator separately against each frozen workspace.
8. Archive:
   - starting commit SHA
   - final git status
   - workflow run artifacts
   - evaluator verdicts

### Task Injection Conventions

The original task description should be inserted identically in both arms.

Recommendation:
- persist it as `state/task.md` in both workspaces before execution starts
- if backlog-oriented scaffold files are used, optionally also mirror it into `docs/backlog/active/task.md`

The direct arm may read any of those files voluntarily.
The workflow arm should treat the task artifact as the canonical `task` contract input.

### Reset and Cleanup Conventions

To keep repeated trials comparable:
- never reuse a modified workspace for a new trial
- reprovision both arms from the same scaffold snapshot for every run
- archive outputs outside the active run workspaces
- keep generated caches from prior trials out of the seed scaffold

This avoids contamination from prior runs and makes failures reproducible.

## Artifact Contracts

In this design, a contract is an I/O contract that maps cleanly to workflow `publishes` / `consumes` declarations.

### Backbone Artifacts

These are expected to be reused across multiple steps.

#### `task`
- Type: relpath
- Canonical path: `state/task.md`
- Purpose: user-provided task description
- Typical consumers: nearly all provider steps

#### `plan`
- Type: relpath
- Canonical path: `docs/plans/current-plan.md`
- Purpose: implementation plan derived from the task, including the proposed design and key invariants
- Typical consumers: plan review, plan revision, execution, implementation review, fix

#### `check_strategy`
- Type: relpath
- Canonical path: `state/check_strategy.md`
- Purpose: plan-time visible verification strategy
- Typical consumers: plan review, execution, implementation review, fix

### Stage Artifacts

These are local to a phase or loop.

#### `plan_review_report`
- Type: relpath
- Canonical path: `artifacts/review/plan-review.md`
- Purpose: evidence-backed critique of the current plan/check strategy

#### `plan_review_decision`
- Type: scalar enum
- Allowed: `APPROVE`, `REVISE`
- Purpose: binary gate for the plan loop

#### `check_plan`
- Type: relpath
- Canonical path: `state/check_plan.json`
- Purpose: runnable visible verification plan materialized during execution
- Typical consumers: run checks, implementation review, fix

#### `execution_report`
- Type: relpath
- Canonical path: `artifacts/work/execution-report.md`
- Purpose: concise execution handoff for later review/fix
- Required contents:
  - plan used
  - files changed
  - commands executed
  - tests/checks added or changed
  - claimed completion status
  - blockers or unresolved risks

#### `check_results`
- Type: relpath
- Canonical path: `artifacts/checks/check-results.json`
- Purpose: structured result of executing the check plan

#### `implementation_review_report`
- Type: relpath
- Canonical path: `artifacts/review/implementation-review.md`
- Purpose: evidence-backed review of implementation correctness

#### `implementation_review_decision`
- Type: scalar enum
- Allowed: `APPROVE`, `REVISE`
- Purpose: binary gate for the implementation loop

## Check Strategy and Check Plan Contract

The workflow should use a fixed execution mechanism with runtime-derived commands, but should not force the plan loop to pretend that future tests already exist.

Plan-time `check_strategy`:
- describes intended visible verification
- distinguishes between checks that already exist and checks that should be created during execution
- does not need every future command to already be runnable

Implementation-time `check_plan`:
- contains only runnable commands
- is refreshed by execution/fix steps when verification changes

Recommended `check_plan` schema:

```json
{
  "checks": [
    {
      "name": "unit-tests",
      "argv": ["cargo", "test", "--quiet"],
      "timeout_sec": 900,
      "required": true
    }
  ]
}
```

Required fields:
- `name`
- `argv`
- `timeout_sec`
- `required`

Rationale:
- keeps the workflow general
- avoids hard-coding language or domain into the YAML
- gives deterministic, structured execution
- keeps plan review honest about current repo state
- produces concrete pass/fail evidence for later steps

Do not rely on arbitrary shell strings by default. If needed later, a constrained escape hatch can be added, but the initial design should prefer structured `argv`.

## Workflow Shape

### Phase 0: Task Publication

1. `PublishTask`
- Input: injected `state/task.md`
- Produces: `task`
- Responsibility: validate that the provisioned canonical task artifact exists and publish it for the rest of the workflow

### Phase 1: Plan Loop

2. `DraftPlan`
- Consumes: `task`
- Produces: `plan`, `check_strategy`
- Responsibility:
  - derive executable scope from the task
  - define implementation steps
  - define visible verification strategy

3. `ReviewPlan`
- Consumes: `task`, `plan`, `check_strategy`
- Produces: `plan_review_report`, `plan_review_decision`
- Reject when:
  - plan is underspecified
  - plan has obvious correctness gaps
  - verification strategy is weak, circular, or implausible
  - strategy does not credibly explain how runnable verification will exist by the implementation loop

4. `RevisePlan`
- Consumes: `task`, `plan`, `check_strategy`, `plan_review_report`
- Produces: updated `plan`, updated `check_strategy`
- Loop: returns to `ReviewPlan`

This loop is bounded by `max_plan_cycles`.

### Phase 2: Implementation Loop

5. `ExecutePlan`
- Consumes: `task`, `plan`, `check_strategy`
- Produces: `execution_report`, `check_plan`
- Responsibility: perform implementation work within the plan's scope and materialize the runnable verification plan

6. `RunChecks`
- Consumes: `check_plan`
- Produces: `check_results`
- Responsibility: execute the current verification plan exactly as written and persist logs/results
- Failure mode: stale or malformed check plans should normally become structured `check_results`, not abort the workflow

7. `ReviewImplementation`
- Consumes: `task`, `plan`, `check_strategy`, `check_plan`, `execution_report`, `check_results`
- Produces: `implementation_review_report`, `implementation_review_decision`
- Reject when:
  - checks failed
  - blocking correctness gaps remain despite passing visible checks
  - verification remains inadequate relative to the task
- Do not reject for style-only concerns

8. `FixIssues`
- Consumes: `task`, `plan`, `check_strategy`, `check_plan`, `execution_report`, `check_results`, `implementation_review_report`
- Produces: updated code/tests, a refreshed `execution_report`, and a refreshed `check_plan`
- Loop: returns to `RunChecks`, then `ReviewImplementation`

This loop is bounded by `max_impl_cycles`.

## Prompt Design Principles

The prompts should be generic. They should not say things like:
- translate Python to Rust
- port ML metrics
- use Cargo
- use PyO3

They should say things like:
- read the consumed artifacts before acting
- draft an implementation plan for the task
- derive a visible verification strategy from task requirements and repo state
- materialize a runnable check plan after execution has created the relevant checks
- review for blocking correctness and verification gaps
- keep work scoped to the task and plan
- produce outputs exactly at the contract paths

This keeps prompts reusable across task families.

## Reviewer Policy

The implementation reviewer should be allowed to reject based on:
- concrete failed checks
- code inspection and artifact inspection revealing blocking correctness issues
- inadequate verification relative to the task

The reviewer should not reject for:
- formatting
- naming preferences
- style-only refactors
- non-blocking cleanup suggestions

Every rejection should cite:
- concrete evidence
- specific required fixes
- a binary decision artifact

This is important because visible checks are intentionally incomplete. The workflow should be strong enough to catch likely hidden-evaluator failures without becoming a style-policing bottleneck.

## Execution Handoff Recommendation

Use a **structured execution report** rather than a full transcript handoff.

Rationale:
- a concise execution artifact is useful for review/fix steps
- full raw transcripts are too noisy and too sensitive to prompt wording
- review should focus on outcomes and evidence, not on narrative prose

Raw stdout/stderr logs can still be retained for observability, but they should be secondary artifacts rather than primary contracts.

## Why `RunChecks` Is Still Necessary

Even if the plan says tests should be written, a dedicated check step is still required because:
- writing tests is not the same as running them
- the workflow needs deterministic execution evidence
- later review/fix steps need structured results rather than self-reported success
- a weak or incomplete test suite should be visible as a review concern

So the intended split is:
- planning defines verification intent
- execution/fix may add or modify tests
- `RunChecks` executes the current check plan
- review inspects both the code and the concrete check results

## Candidate Task Portfolio

The first task family should emphasize Python-to-Rust coding tasks that are ML-adjacent and easy to evaluate externally.

### Candidate A: Numerical ML Utility Translation

Translate a nontrivial Python module to Rust, such as:
- evaluation metrics
- sampling utilities
- normalization/transforms
- batching logic
- dataset splitting utilities

Desired failure mode:
- direct run produces a plausible port that misses edge cases, numerical tolerance details, or error semantics
- workflow catches those issues during review/fix

### Candidate B: Inference Pre/Post-Processing Port

Port Python preprocessing or postprocessing logic for a small model pipeline into Rust.

Desired failure mode:
- direct run gets the rough shape right but misses shape handling, data layout, or invariants
- workflow improves through explicit check strategy and review

### Candidate C: Deterministic Data-Pipeline Utility Port

Port a Python utility involving sliding windows, patch extraction, reproducible shuffling, or split generation.

Desired failure mode:
- direct run under-specifies determinism or corner-case behavior
- workflow improves via derived checks and revision loops

Recommendation: start with Candidate A because it is easiest to scaffold cleanly and easiest to explain.

## Demo Fairness Requirements

To keep the comparison defensible:
- same repo scaffold in both arms
- same `AGENTS.md` in both arms
- same task text in both arms
- same hidden evaluator outside the repo
- no extra domain hints in workflow prompts
- no hidden workflow-only setup beyond orchestration machinery itself

The workflow should win because of process control, not because of privileged information.

## Risks

1. The task may be too easy.
- Mitigation: choose tasks where visible checks are necessarily incomplete and review has real work to do.

2. The task may be too hard for the workflow too.
- Mitigation: constrain scope and provide a prepared repo skeleton.

3. The workflow may overfit to narration.
- Mitigation: treat execution reports as concise evidence artifacts, not conversational transcripts.

4. The reviewer may nitpick style.
- Mitigation: encode a blocking-correctness-only rejection policy.

5. The direct arm may voluntarily mimic the workflow.
- This is acceptable. If the direct run independently self-organizes well enough to succeed, that is legitimate evidence about task difficulty. The task portfolio should therefore include multiple candidates.

## Recommended Next Steps

1. Create the shared scaffold repository layout and seed documents.
2. Draft the generic prompt set for:
   - `DraftPlan`
   - `ReviewPlan`
   - `RevisePlan`
   - `ExecutePlan`
   - `ReviewImplementation`
   - `FixIssues`
3. Draft the general workflow YAML with explicit artifact contracts and bounded loops.
4. Build 2-3 candidate Python-to-Rust ML-adjacent tasks against the scaffold.
5. Validate that at least one candidate usually triggers a meaningful revision cycle.

For entrypoint-matching tasks such as the current nanoBragg flagship, review and implementation gates should judge against the named reference entrypoint outputs and visible fixture boundaries rather than a broader inferred domain model.
