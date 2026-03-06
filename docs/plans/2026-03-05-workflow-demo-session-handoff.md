# Workflow Demo Session Handoff

**Status:** Active handoff / continuation document  
**Date:** 2026-03-05  
**Audience:** Any engineer continuing the workflow-demo effort with no prior chat context

## 1. What the user wanted

The user wants a demo for the orchestrator that compares two ways of solving the same coding task:

1. a direct, single-shot agent run in a fresh workspace
2. a workflow-driven agent run in an equivalent fresh workspace

The intended outcome is that the workflow-driven run succeeds more reliably than the direct run because the workflow enforces better process hygiene, not because it gets better instructions or extra information.

The user explicitly wanted the workflow to demonstrate the value of:
- planning before execution
- revision of plans and/or implementation
- concrete feedback loops
- verifiable outcomes

The user also explicitly constrained the setup:
- both arms are single-shot from the human's perspective
- neither arm gets user feedback during execution
- both arms should use the same `AGENTS.md`
- both arms should start from equivalent fresh directory trees
- the workflow should stay general-purpose rather than hard-coding the task domain into prompts or YAML
- the only task-specific input should be the original user task description, persisted into the workspace as a runtime artifact

The user prefers the first task family to be:
- coding-oriented rather than documentation-oriented
- Python-to-Rust if possible
- ML-adjacent if possible

The user also wants multiple candidate tasks eventually, because not every candidate will produce a convincing direct-vs-workflow gap.

## 2. Core hypothesis agreed in this session

The workflow should win because of enforced process structure, not because of privileged instructions.

That means the comparison must preserve information equality:
- same repo scaffold
- same `AGENTS.md`
- same initial task description
- same visible files
- same hidden evaluator model (external to both arms)

The only meaningful difference should be execution process.

The workflow therefore needs to enforce a sequence that a direct run might skip or underperform on:
- derive a plan
- derive a visible verification strategy
- review the plan and verification strategy
- revise them if needed
- execute the work
- run checks deterministically
- review the implementation using both artifacts and check results
- fix issues
- repeat in bounded loops

## 2.1 Key Repo References

Use this section as the file-level map for continuation.

### Core session outputs

- `docs/plans/2026-03-05-workflow-demo-session-handoff.md`
  - this handoff document
- `docs/plans/2026-03-05-workflow-demo-design.md`
  - primary design/spec for the demo experiment
- `docs/plans/templates/artifact_contracts.md`
  - workflow-facing artifact vocabulary
- `docs/plans/templates/check_plan_schema.md`
  - guidance for plan-time `check_strategy` and runtime `check_plan`
- `docs/plans/templates/plan_template.md`
  - optional authoring aid for the `plan` artifact
- `docs/plans/templates/review_template.md`
  - optional authoring aid for review artifacts
- `prompts/workflows/generic_task_loop/draft_plan.md`
- `prompts/workflows/generic_task_loop/review_plan.md`
- `prompts/workflows/generic_task_loop/revise_plan.md`
- `prompts/workflows/generic_task_loop/execute_plan.md`
- `prompts/workflows/generic_task_loop/review_implementation.md`
- `prompts/workflows/generic_task_loop/fix_issues.md`
- `workflows/examples/generic_task_plan_execute_review_loop.yaml`
  - the generic two-loop workflow example created from this design

### Core DSL and workflow authoring references

- `docs/index.md`
  - documentation hub for the repo
- `docs/orchestration_start_here.md`
  - conceptual model for orchestration, workflow, DSL, and runtime boundaries
- `docs/runtime_execution_lifecycle.md`
  - step sequencing and runtime state behavior
- `docs/workflow_drafting_guide.md`
  - informative authoring guidance for prompts, contracts, and gates
- `specs/index.md`
  - normative spec entrypoint
- `specs/dsl.md`
  - normative workflow schema and control flow
- `specs/providers.md`
  - provider prompt delivery and provider step semantics
- `specs/io.md`
  - output capture and deterministic output-contract behavior
- `specs/state.md`
  - state representation and artifact ledger semantics
- `specs/versioning.md`
  - feature/version gating, including v1.4 consume semantics
- `specs/queue.md`
  - queue and backlog-process semantics when those primitives are used
- `specs/observability.md`
  - run artifact and log expectations

### Example workflows and runbooks worth comparing against

- `workflows/examples/README_v0_artifact_contract.md`
  - existing runbook for artifact-contract workflows
- `workflows/examples/backlog_plan_execute_v1_2_dataflow.yaml`
  - compact v1.2 publish/consume example
- `workflows/examples/backlog_plan_execute_v1_3_json_bundles.yaml`
  - example of JSON-bundle based assessment/gating
- `workflows/examples/test_fix_loop_v0.yaml`
  - minimal test/fix loop
- `workflows/examples/unit_of_work_plus_test_fix_v0.yaml`
  - example of unit-of-work plus verification loop
- `workflows/examples/ptychopinn_backlog_plan_slice_impl_review_loop.yaml`
  - informative downstream reference copied from the PtychoPINN workflow family

### Adjacent scaffold and experiment-operation assets now present in the repo

- `examples/demo_scaffold/AGENTS.md`
- `examples/demo_scaffold/README.md`
- `examples/demo_scaffold/docs/index.md`
- `examples/demo_scaffold/docs/dev_guidelines.md`
- `examples/demo_scaffold/src_py/README.md`
- `examples/demo_scaffold/rust/README.md`
- `docs/plans/2026-03-05-demo-scaffold-and-runbook.md`
- `docs/plans/2026-03-05-demo-provisioning-script.md`
- `scripts/demo/provision_trial.py`

These adjacent assets were not the main focus of the design thread captured here, but they are directly relevant to continuation and should be reconciled with the workflow/prompt/contract design before duplicating effort.

## 3. Major design decisions made

### 3.1 General shape of the workflow

We agreed on a **single top-level task item** for the first demo, not multi-item backlog decomposition.

Reason:
- it isolates the process advantage more cleanly
- it is easier to debug and explain
- it avoids mixing in decomposition-quality as a second confounding variable

Backlog directories may still exist in the scaffold because they are useful general process primitives, but the first workflow does not depend on splitting one task into multiple queue items.

### 3.2 Two explicit feedback loops

We agreed the workflow should contain two loops:

1. **Plan loop**
   - draft plan
   - review plan and check strategy
   - revise plan if needed

2. **Implementation loop**
   - execute plan
   - run checks
   - review implementation
   - fix issues if needed

The user specifically objected to a design that had no real feedback loops. The workflow must visibly exercise revision, otherwise it does not demonstrate the process advantage.

### 3.3 Revision should usually happen at least once

The user explicitly said the demo should aim for at least one revision cycle, because zero revisions would make the workflow advantage mostly invisible.

We therefore designed the workflow so:
- one-shot success is possible but should not be the common case
- visible checks are intentionally useful but incomplete
- review can reject based on blocking correctness issues even if visible checks pass

### 3.4 Hidden evaluation is external

The final evaluator is out of scope for both the direct run and the workflow run.

However, both arms still need to infer the likely success condition from:
- the original task description
- the repo scaffold
- their own analysis

This is why the workflow includes an explicit plan-time `check_strategy` artifact and an implementation-time `check_plan` artifact: they formalize visible verification without revealing hidden evaluator details.

### 3.5 `RunChecks` is required

The user asked whether `RunChecks` was necessary if the plan requires tests to be written.

Decision:
- yes, a dedicated `RunChecks` step is still necessary

Reason:
- writing tests is not the same as running them
- the workflow needs deterministic execution evidence
- review and fix steps need structured check results, not self-reported success
- a weak or incomplete test suite should remain visible as a review concern

### 3.6 Check execution mechanism should be general

The user objected to a fixed command that would effectively hard-code a domain like Python-to-Rust.

Decision:
- use a **fixed mechanism** with **runtime-derived commands**

Concretely:
- the workflow always has a `RunChecks` step
- the runnable checks are described in a machine-readable `check_plan` artifact
- `RunChecks` executes that plan generically
- the workflow YAML does not hard-code `cargo test`, `pytest`, or any other domain-specific command

### 3.7 Contracts are I/O contracts

The user clarified that “contract” should mean an artifact I/O interface that maps naturally to `consumes` / `publishes`, not a prose structure requirement.

Decision:
- separate artifact contracts from authoring templates

This yielded the split:
- artifact contracts define what gets produced and consumed
- templates are optional authoring aids for agents

### 3.8 Execution handoff should be structured, not a raw transcript

The user asked whether a session transcript handoff, like the PtychoPINN workflow, was needed.

Decision:
- keep a structured execution report as a first-class artifact
- do not make full transcripts a primary contract

Reason:
- review/fix loops need evidence about what happened
- raw transcripts are too noisy and prompt-sensitive
- outcome-oriented artifacts are more reusable and general-purpose

### 3.9 Shared backbone artifacts

The user asked whether some artifacts, like the plan, should be consumed by most workflow steps.

Decision:
- yes, some artifacts act as a shared backbone
- but consumption should still be declared explicitly per step

Backbone artifacts agreed in this session:
- `task`
- `plan`
- `check_strategy`

These are meant to be broadly reused by later provider steps.

## 4. High-level experiment design produced in this session

We produced a design doc for the overall experiment.

File created:
- `docs/plans/2026-03-05-workflow-demo-design.md`

Commit created:
- `5b83896` `docs: add workflow demo design`

What the design doc covers:
- objective of the demo
- equality constraints between direct and workflow arms
- decision to use one top-level task with two bounded loops
- shared scaffold repo shape
- artifact vocabulary
- check-plan schema
- generic workflow shape
- reviewer policy
- execution handoff recommendation
- reasons for keeping `RunChecks`
- candidate Python-to-Rust / ML-adjacent task families
- experiment setup conventions (workspace layout, git policy, run lifecycle, task injection, cleanup)

Important sections in the design doc:
- shared scaffold and equality model
- experiment setup conventions
- artifact contracts and backbone artifacts
- workflow shape
- candidate task portfolio

The design doc is conceptual and prescriptive. It is not the final runbook for actually launching and grading both arms.

## 5. Concrete files created from the design

### 5.1 Artifact-contract and template docs

We created the following scaffold-facing docs under `docs/plans/templates/`:

1. `artifact_contracts.md`
- defines the artifact vocabulary for the demo workflow
- artifact meanings are intended to map directly to workflow `publishes` / `consumes`
- backbone artifacts:
  - `task`
  - `plan`
  - `check_strategy`
- stage artifacts:
  - `plan_review_report`
  - `plan_review_decision`
  - `execution_report`
  - `check_results`
  - `implementation_review_report`
  - `implementation_review_decision`

2. `check_plan_schema.md`
- defines the split between plan-time `check_strategy` and runtime `check_plan`
- uses a constrained schema with:
  - `name`
  - `argv`
  - `timeout_sec`
  - `required`
- explicitly prefers structured `argv` over arbitrary shell strings

3. `plan_template.md`
- optional authoring aid for the `plan` artifact
- not normative
- includes suggested sections like task restatement, scope, risks, implementation steps, verification strategy, completion criteria

4. `review_template.md`
- optional authoring aid for review artifacts
- not normative
- emphasizes blocking findings, evidence, required fixes, and binary decision

Commit created:
- `193fce2` `docs: add generic workflow prompt and contract templates`

### 5.2 Generic workflow prompt set

We created a generic prompt set under:
- `prompts/workflows/generic_task_loop/`

Files created:
- `draft_plan.md`
- `review_plan.md`
- `revise_plan.md`
- `execute_plan.md`
- `review_implementation.md`
- `fix_issues.md`

Prompt design principles used:
- prompts are generic, not domain-specific
- prompts read `Consumed Artifacts` first
- prompts refer to the artifact contract docs and templates in `docs/plans/templates/`
- prompts rely on the workflow-injected output contract rather than hard-coded domain paths
- prompts prohibit unrelated refactors and fabricated results
- review prompts are strict about correctness but explicitly not style-policing

These prompts are intended to be reusable across task families so long as the scaffold and workflow honor the artifact contracts.

## 6. Workflow YAML created in this session

We created a concrete example workflow:
- `workflows/examples/generic_task_plan_execute_review_loop.yaml`

Commit created:
- `9b22a24` `docs: add generic task workflow example`

### 6.1 Workflow version and general shape

The workflow uses:
- `version: "1.4"`
- a codex provider template using stdin
- two bounded loops:
  - plan loop
  - implementation loop

Context values in the example:
- `task_source: "docs/backlog/active/task.md"`
- `max_plan_cycles: "2"`
- `max_impl_cycles: "4"`

### 6.2 Steps implemented

1. `InitializeWorkflowState`
- creates required directories
- writes all pointer-path files under `state/`
- initializes cycle counters

2. `CaptureTask`
- copies the task from `context.task_source` into `state/task.md`
- publishes `task`

3. `DraftPlan`
- consumes `task`
- uses the generic `draft_plan.md` prompt
- produces and publishes `plan` and `check_strategy`

4. `ReviewPlan`
- consumes `task`, `plan`, `check_strategy`
- uses the generic `review_plan.md` prompt
- produces and publishes `plan_review_report` and `plan_review_decision`

5. `PlanReviewGate`
- routes to execution on `APPROVE`
- routes to the plan-cycle gate on `REVISE`

6. `PlanCycleGate`
- enforces `max_plan_cycles`

7. `RevisePlan`
- consumes `task`, `plan`, `check_strategy`, `plan_review_report`
- uses the generic `revise_plan.md` prompt
- republishes updated `plan` and `check_strategy`

8. `IncrementPlanCycle`
- increments the plan loop counter and returns to `ReviewPlan`

9. `ExecutePlan`
- consumes `task`, `plan`, and `check_strategy`
- uses the generic `execute_plan.md` prompt
- produces and publishes `execution_report` and `check_plan`

10. `RunChecks`
- consumes `check_plan` via `consume_bundle`
- reads the JSON check plan from the resolved artifact
- executes each check's `argv`
- writes per-check logs under `artifacts/checks/logs/`
- writes structured results to `artifacts/checks/check-results.json`, including malformed or stale check-plan failures when possible
- publishes `check_results`

11. `ReviewImplementation`
- consumes `task`, `plan`, `check_strategy`, `check_plan`, `execution_report`, `check_results`
- uses the generic `review_implementation.md` prompt
- produces and publishes `implementation_review_report` and `implementation_review_decision`

12. `ImplementationReviewGate`
- ends successfully on `APPROVE`
- routes to the implementation-cycle gate on `REVISE`

13. `ImplementationCycleGate`
- enforces `max_impl_cycles`

14. `FixIssues`
- consumes `task`, `plan`, `check_strategy`, `check_plan`, `execution_report`, `check_results`, `implementation_review_report`
- uses the generic `fix_issues.md` prompt
- republishes updated `execution_report` and `check_plan`

15. `IncrementImplementationCycle`
- increments the implementation loop counter and returns to `RunChecks`

16. Failure terminals
- `MaxPlanCyclesExceeded`
- `MaxImplementationCyclesExceeded`

### 6.3 Workflow artifacts declared

Top-level artifacts in the example workflow:
- `task` (relpath)
- `plan` (relpath)
- `check_strategy` (relpath)
- `check_plan` (relpath)
- `plan_review_report` (relpath)
- `plan_review_decision` (scalar enum)
- `execution_report` (relpath)
- `check_results` (relpath)
- `implementation_review_report` (relpath)
- `implementation_review_decision` (scalar enum)

### 6.4 Validation performed

We validated the YAML with a dry run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/generic_task_plan_execute_review_loop.yaml --dry-run
```

Result:
- validation succeeded

No runtime integration test was added yet.
No real end-to-end demo run has been executed with a scaffold and task.

## 7. Important operational decisions that were discussed but not fully implemented

### 7.1 Workspace layout for future experiment runs

The agreed design direction is:

```text
<experiment-root>/
  seed/
  direct-run/
  workflow-run/
  evaluator/
  archive/
```

Intent:
- `seed/` is the provisioned source snapshot for the trial
- `direct-run/` and `workflow-run/` are seeded from the same commit
- `evaluator/` contains the hidden grading harness outside the agent-visible workspaces
- `archive/` stores frozen outputs and comparison artifacts after the run

Recommended provisioning model:
- use git worktrees if convenient and clean
- otherwise use separate sibling clones from the same source commit

### 7.2 Git usage policy for the experiment

The design direction is:
- both arms may create commits
- commits are not required for success
- final grading should be based on filesystem state, not commit existence
- both arms must start from the same commit
- neither arm should see the other's filesystem state

### 7.3 Task injection convention

The current design direction is:
- persist the original task into `state/task.md`
- optionally mirror it into `docs/backlog/active/task.md`
- the workflow treats the `task` artifact as canonical
- the direct arm is free to read the same files voluntarily

## 8. What still needs to be done next

Some items originally listed as pending have since been implemented in the repository. The remaining and updated next steps are below.

### 8.1 Shared scaffold seed and runbook

This is no longer pending.

Implemented artifacts now exist at:
- `examples/demo_scaffold/`
- `docs/plans/2026-03-05-demo-scaffold-and-runbook.md`

These files provide:
- the seed workspace tree
- shared `AGENTS.md`, `docs/index.md`, and `docs/dev_guidelines.md`
- planning/review/check-plan templates
- provisioning, launch, freeze, and grading conventions

### 8.2 Build candidate tasks

We agreed that the task portfolio should likely start with Python-to-Rust ML-adjacent coding tasks.

Candidate families discussed:
- numerical ML utility translation
- inference pre/post-processing port
- deterministic data-pipeline utility port

The first recommended candidate is numerical ML utility translation because it is easiest to scaffold and explain.

This is partially implemented now:
- `examples/demo_task_linear_classifier_port/`
- `orchestrator/demo/evaluators/linear_classifier.py`
- `scripts/demo/evaluate_linear_classifier.py`
- `tests/test_demo_linear_classifier_evaluator.py`
- `tests/test_demo_task_seed.py`

Current state:
- one concrete linear-classifier seed exists and is evaluator-backed
- a second sliding-window seed now exists but is not evaluator-backed yet

### 8.3 Provisioning utility

This is no longer pending.

Implemented artifacts now exist at:
- `orchestrator/demo/provisioning.py`
- `scripts/demo/provision_trial.py`
- `tests/test_demo_provisioning.py`

The provisioning utility now:
- stamps out `seed/`, `direct-run/`, and `workflow-run/` from one commit using git worktrees
- creates `archive/` and `evaluator/` directories
- injects identical task content into both run workspaces
- records start-commit metadata in `trial-metadata.json`

### 8.4 Add a first task fixture and hidden evaluator

This is no longer pending for the first task.

Implemented artifacts now exist at:
- `examples/demo_task_linear_classifier_port/`
- `orchestrator/demo/evaluators/linear_classifier.py`
- `scripts/demo/evaluate_linear_classifier.py`
- `tests/test_demo_linear_classifier_evaluator.py`

The most important remaining implementation work is now:
- add evaluator integration for the second seed
- harden the archived result schema if the current one proves too thin

### 8.5 Possibly add stronger end-to-end validation around the workflow demo path

Current validation status:
- prompt/contract docs: documentation-only
- workflow example: dry-run validation succeeded
- provisioning utility: targeted pytest coverage exists
- trial runner: targeted pytest coverage exists
- provisioned-workspace smoke path for the first seed: targeted pytest coverage exists
- a real direct-arm execution was attempted in a freshly provisioned workspace using the demo direct-arm prompt

Remaining gap:
- the trial runner has been exercised through mocked subprocess boundaries, not through a real local direct-arm plus workflow-arm trial
- the direct-arm prompt was exercised against the first seed, but the run could not complete because the local environment did not have `cargo` or `rustc`
- there is still no recorded end-to-end run where both arms complete and are evaluated under the local environment

Possible future hardening:
- add a smoke test that provisions a toy seed and validates expected workspace outputs
- add a minimal end-to-end demo run against a toy task

## 9. Things that came up during the session and matter for anyone continuing

### 9.1 Dirty worktree caveat

While working, we discovered this repository had many unrelated modified and untracked files.

We explicitly avoided bundling unrelated changes.
Commits made from this session were limited to targeted files only.

Anyone continuing should continue to be careful about staging only intended files.

### 9.2 Existing examples used as inspiration

We used the v1.4-style design direction from the downstream PtychoPINN workflow, especially:
- explicit artifact handoff
- review/fix loops
- step-local prompt files
- path-pointer pattern for relpath artifacts

However, we intentionally generalized away from the domain-specific details in the PtychoPINN workflow and prompts.

### 9.3 Why the workflow remains general-purpose

The prompts and workflow should not say things like:
- translate Python to Rust
- use Cargo
- use PyO3
- use ML-specific tools

Instead they say things like:
- read the task artifact
- derive a plan
- derive a visible verification strategy
- materialize a runnable check plan during execution
- review for blocking correctness and verification gaps
- write outputs to the contract paths

The task domain is meant to arrive via runtime artifacts, not baked-in prompt text.

## 10. Files and commits created by this session

### Design doc
- File: `docs/plans/2026-03-05-workflow-demo-design.md`
- Commit: `5b83896` `docs: add workflow demo design`

### Prompt and contract templates
- Files:
  - `docs/plans/templates/artifact_contracts.md`
  - `docs/plans/templates/check_plan_schema.md`
  - `docs/plans/templates/plan_template.md`
  - `docs/plans/templates/review_template.md`
  - `prompts/workflows/generic_task_loop/draft_plan.md`
  - `prompts/workflows/generic_task_loop/review_plan.md`
  - `prompts/workflows/generic_task_loop/revise_plan.md`
  - `prompts/workflows/generic_task_loop/execute_plan.md`
  - `prompts/workflows/generic_task_loop/review_implementation.md`
  - `prompts/workflows/generic_task_loop/fix_issues.md`
- Commit: `193fce2` `docs: add generic workflow prompt and contract templates`

### Generic workflow example
- File: `workflows/examples/generic_task_plan_execute_review_loop.yaml`
- Commit: `9b22a24` `docs: add generic task workflow example`

### Demo scaffold, provisioning, runner, and first evaluated seed
- Files:
  - `examples/demo_scaffold/`
  - `examples/demo_task_linear_classifier_port/`
  - `examples/demo_task_sliding_window_port/`
  - `orchestrator/demo/provisioning.py`
  - `orchestrator/demo/evaluators/linear_classifier.py`
  - `orchestrator/demo/trial_runner.py`
  - `scripts/demo/provision_trial.py`
  - `scripts/demo/evaluate_linear_classifier.py`
  - `scripts/demo/run_trial.py`
  - `tests/demo_helpers.py`
  - `tests/test_demo_provisioning.py`
  - `tests/test_demo_linear_classifier_evaluator.py`
  - `tests/test_demo_task_seed.py`
  - `tests/test_demo_task_sliding_window_seed.py`
  - `tests/test_demo_trial_smoke.py`
  - `tests/test_demo_trial_runner.py`
- Commits created after the original design session:
  - `ce3b788` `test: add demo trial smoke coverage`
  - `9c9ac59` `feat: add demo trial runner`
  - `b79f076` `feat: add sliding window demo task seed`
  - `4654aa3` `docs: finalize demo next-step runbook notes`

### Demo coordination prompts and runbook wiring
- Files:
  - `prompts/demo/run_direct_vs_workflow_trial.md`
  - `prompts/demo/run_direct_arm_task.md`
  - `docs/plans/2026-03-05-demo-scaffold-and-runbook.md`
- Status:
  - the runbook now points to both prompt files
  - the runner still uses its built-in default direct-arm prompt string unless explicitly updated to load prompt files
  - these prompt additions were created after the earlier committed runner work and may still need their own commit depending on repository state

### First real direct-arm prompt execution attempt
- Provisioned temporary trial paths:
  - seed repo: `/tmp/direct-arm-seed-iB80Wh`
  - experiment root: `/tmp/direct-arm-trial-yoUiqo`
  - direct workspace: `/tmp/direct-arm-trial-yoUiqo/direct-run`
- What the direct arm did:
  - read `AGENTS.md`, `docs/index.md`, and `state/task.md`
  - created `docs/plans/2026-03-05-linear-classifier-port.md`
  - modified `rust/tests/smoke_linear_classifier.rs`
- What blocked completion:
  - `cargo` was not installed or discoverable
  - `rustc` was not installed or discoverable
- Result:
  - this was a partial real execution of the direct arm, not a successful completed trial
  - it surfaced an environment prerequisite that the current docs and runner should make more explicit

## 11. Recommended continuation order

If picking up from this handoff, the recommended order is:

1. Finish the trial runner and archive/reporting docs integration.
2. Make the Rust toolchain requirement explicit in the runbook and runner-facing docs, or provision an environment that already has `cargo` and `rustc`.
3. Add evaluator integration for the second concrete Python-to-Rust ML-adjacent task seed.
4. Run the direct and workflow arms against the first seed using the new runner in an environment where both arms can actually execute Rust checks.
5. Observe whether the workflow naturally exercises at least one revision cycle.
6. If not, adjust the task family or visible-check design until the workflow advantage becomes visible but remains fair.

## 12. Bottom line

This session produced the conceptual design and the first concrete workflow/prompt/contract assets.

What now exists:
- a detailed design doc for the experiment
- artifact-contract and template docs
- a generic prompt set for the two-loop workflow
- a validating example workflow YAML
- a shared scaffold seed
- a first task-specific seed and evaluator
- a provisioning utility
- a trial runner API and CLI
- demo coordination prompts for the overall trial and the direct arm
- smoke and runner pytest coverage for the first evaluated path
- a second candidate seed for sliding-window translation
- one partial real direct-arm execution showing that the environment currently lacks the Rust toolchain needed to complete the task

What does not yet exist:
- evaluator integration for the second task seed
- a real end-to-end executed demo proving the direct-vs-workflow gap in an environment with a working Rust toolchain
- stronger evaluator-selection metadata than the current seed-name dispatch

A new engineer should be able to continue from here without needing the original chat, provided they start by reading:
1. this handoff document
2. `docs/plans/2026-03-05-workflow-demo-design.md`
3. `docs/plans/templates/artifact_contracts.md`
4. `workflows/examples/generic_task_plan_execute_review_loop.yaml`
5. the prompt files under `prompts/workflows/generic_task_loop/`
