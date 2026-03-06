# Workflow Demo Scaffold and Runbook

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement follow-on setup work from this document.

**Goal:** Define the concrete seed workspace, provisioning rules, launch mechanics, and grading flow for the direct-vs-workflow demo.

**Architecture:** A single seed scaffold is materialized into two sibling workspaces, `direct-run/` and `workflow-run/`, from the same starting commit. The direct arm receives one prompt over the seeded repo; the workflow arm runs the generic task loop over the same repo shape and same task artifact.

**Tech Stack:** Git, Codex CLI, the orchestrator CLI, filesystem artifact contracts, hidden external evaluator.

---

## Scope

This document specifies the operational layer that sits on top of [2026-03-05-workflow-demo-design.md](/home/ollie/Documents/agent-orchestration/docs/plans/2026-03-05-workflow-demo-design.md). It makes the demo reproducible by defining:
- the concrete scaffold contents
- where the two workspace trees live
- how tasks are injected
- how both arms are launched
- how runs are frozen and graded

This document does not define the hidden evaluator internals or the specific Python-to-Rust task itself.

## Seed Scaffold

The canonical seed lives at [examples/demo_scaffold](/home/ollie/Documents/agent-orchestration/examples/demo_scaffold). It is the visible repo shape given to both arms.

Seed tree:

```text
examples/demo_scaffold/
  AGENTS.md
  README.md
  docs/
    index.md
    dev_guidelines.md
    backlog/
      active/
      done/
    plans/
      templates/
        plan_template.md
        review_template.md
        check_plan_schema.md
        artifact_contracts.md
  artifacts/
    work/
    checks/
    review/
  state/
  src_py/
  rust/
```

Scaffold design rules:
- keep the tree small and domain-neutral
- include process guidance, not task answers
- make expected working directories obvious
- include empty artifact/state directories so both arms converge on the same paths
- do not include the hidden evaluator or any hidden tests

## Required Seed Files

### `AGENTS.md`

Purpose:
- establish shared repo-level behavior for both arms
- point the agent to `docs/index.md` first
- require plans, explicit verification, and concise status logging
- prohibit guessing success without running visible checks

Constraint:
- the workflow arm must not receive extra instructions outside this shared file and the workflow prompts

### `docs/index.md`

Purpose:
- orient the agent to the repo layout
- identify the task artifact location
- identify where plans and reports belong
- list the visible success signals available inside the workspace

### `docs/dev_guidelines.md`

Purpose:
- define repo-local engineering expectations
- require minimal, targeted changes
- require runnable checks before claiming completion
- ban gratuitous refactors and style churn

### `docs/plans/templates/*`

Purpose:
- provide visible planning and review aids in both arms
- reinforce the same artifact vocabulary the workflow uses
- avoid giving the workflow exclusive structure advantages
- expose both plan-time verification strategy guidance and runtime check-plan guidance

## Workspace Provisioning

For each trial, create a fresh experiment root with sibling trees:

```text
<experiment-root>/
  seed/
  direct-run/
  workflow-run/
  evaluator/
  archive/
```

Recommended provisioning method:
1. create a clean git commit for the task-specific seed scaffold
2. materialize `direct-run/` and `workflow-run/` from that same commit
3. record the starting commit SHA in both workspaces

Recommended command:

```bash
python scripts/demo/provision_trial.py \
  --seed-repo /path/to/task-seed-repo \
  --experiment-root /path/to/experiment-root \
  --task-file /path/to/task.md \
  --workflow-path /path/to/agent-orchestration/workflows/examples/generic_task_plan_execute_review_loop.yaml \
  --workflow-prompts-dir /path/to/agent-orchestration/prompts/workflows
```

Git policy:
- each arm gets an isolated branch or detached worktree label
- commits are allowed but not required
- final grading is against filesystem state, not commit presence
- no network fetch/pull during a trial

## Task Injection

Inject the same task description into both workspaces before launch.

Canonical path:
- `state/task.md`

Optional mirrored path:
- `docs/backlog/active/task.md`

Task injection rules:
- the file content must be byte-identical in both arms
- any supporting visible files must also be byte-identical
- hidden evaluator assets stay outside the workspace
- if provisioning a workflow trial, stage the workflow YAML and `prompts/workflows/` into `workflow-run/` before launch so the orchestrator can resolve them within the workspace tree

## Launch Mechanics

### Direct Arm

The direct arm gets one prompt and no workflow-enforced stages.

Prompt file:
- `prompts/demo/run_direct_arm_task.md`

Recommended command shape:

```bash
codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check \
  "Complete the repository task described in state/task.md. Follow AGENTS.md and docs/index.md."
```

Operational rules:
- run once per trial
- allow the agent to use any visible repo files
- do not inject extra operator guidance after launch

### Workflow Arm

The workflow arm uses the generic task loop over the same seeded workspace.

Recommended command shape:

```bash
PYTHONPATH=/path/to/agent-orchestration \
python -m orchestrator run \
  workflows/examples/generic_task_plan_execute_review_loop.yaml
```

Operational rules:
- run exactly one workflow instance per trial
- preserve the workflow artifact tree after completion
- do not patch prompts between trials unless you are intentionally changing the experiment definition

### Trial Runner

The repo now includes a thin runner that provisions a trial, launches both arms, freezes workspace metadata, invokes the selected evaluator, and writes one comparison record.

Related prompt files:
- coordinator prompt: `prompts/demo/run_direct_vs_workflow_trial.md`
- direct-arm prompt: `prompts/demo/run_direct_arm_task.md`

Concrete command:

```bash
python scripts/demo/run_trial.py \
  --seed-repo /path/to/task-seed-repo \
  --experiment-root /path/to/experiment-root \
  --task-file /path/to/task.md
```

Current defaults:
- workflow: `workflows/examples/generic_task_plan_execute_review_loop.yaml`
- direct prompt: `Complete the repository task described in state/task.md. Follow AGENTS.md and docs/index.md.`
- the runner stages the selected workflow YAML and `prompts/workflows/` into `workflow-run/` before launch

## Freeze and Archive

At end-of-run:
1. stop further agent interaction in both workspaces
2. record `git status --short` and `git rev-parse HEAD || true`
3. archive the direct-arm workspace snapshot
4. archive the workflow-arm workspace snapshot plus workflow artifacts

Minimum archive contents:
- start commit SHA
- final workspace tree snapshot
- direct-run launcher command
- workflow-run launcher command
- workflow artifact outputs
- timestamps and duration

Current archive files produced by the runner:
- `archive/direct-command.json`
- `archive/workflow-command.json`
- `archive/direct-run-metadata.json`
- `archive/workflow-run-metadata.json`
- `archive/trial-result.json`

## Grading Flow

The hidden evaluator runs after both workspaces are frozen.

Evaluation rules:
- the evaluator must not mutate the frozen workspaces
- evaluator output must be stored outside the workspaces
- each arm gets the same evaluator version and invocation

Recommended evaluator outputs:
- verdict: `PASS` or `FAIL`
- machine-readable score summary
- separate soft-quality report that does not override the hard verdict
- failure categories such as:

Task-specific evaluator command for the first seed:

```bash
python scripts/demo/evaluate_linear_classifier.py /path/to/frozen-workspace
```

Current evaluator dispatch note:
- evaluator selection is still minimal, but now prefers the task fixture basename passed to the runner
- `port_linear_classifier_to_rust.md` dispatches to `scripts/demo/evaluate_linear_classifier.py`
- the old seed-directory-name check remains only as a backward-compatible fallback
- additional seeds will need either matching dispatch entries or a stronger explicit metadata contract

  - behavioral mismatch
  - missing required files
  - inadequate edge-case handling
  - build or test failure

## Trial Reporting

Each trial should produce one comparison record with:
- trial id
- seed commit SHA
- task id
- direct-arm verdict
- workflow-arm verdict
- direct-arm runtime
- workflow-arm runtime
- notable failure categories
- whether the workflow exercised plan revision
- whether the workflow exercised implementation revision

Current result location:
- `archive/trial-result.json`

## Immediate Follow-On Work

1. Build the first task-specific seed repo by copying and extending [examples/demo_scaffold](/home/ollie/Documents/agent-orchestration/examples/demo_scaffold).
2. Add a small provisioning script that stamps out `direct-run/` and `workflow-run/` from the same seed commit.
3. Add a task-specific hidden evaluator and archive its outputs outside the seeded workspaces.
