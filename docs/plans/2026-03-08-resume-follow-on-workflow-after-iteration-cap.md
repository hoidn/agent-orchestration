# Resume Follow-On Workflow After Iteration Cap Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Raise the follow-on workflow implementation loop cap from 20 to 30, repair the failed run state only as needed for that intentional config change, and resume the existing run.

**Architecture:** Keep the workflow change minimal: patch only `context.max_impl_iterations` in the example workflow. Treat the failed run as the source of truth for restart position; only repair checksum/state fields required to let the same run continue after the config change, and avoid resetting completed implementation/review history. Resume in tmux so the live run remains inspectable.

**Tech Stack:** Workflow YAML, `state.json` run persistence, orchestrator CLI resume flow, tmux, targeted pytest, dry-run validation.

---

### Task 1: Patch The Workflow Iteration Cap

**Files:**
- Modify: `workflows/examples/dsl_follow_on_plan_impl_review_loop.yaml`

**Step 1: Update the implementation cap**

Change:

```yaml
context:
  max_impl_iterations: "20"
```

to:

```yaml
context:
  max_impl_iterations: "30"
```

**Step 2: Sanity check the diff**

Run:

```bash
git diff -- workflows/examples/dsl_follow_on_plan_impl_review_loop.yaml
```

Expected: only the `max_impl_iterations` value changes.

### Task 2: Repair The Existing Run State For The Intentional Workflow Change

**Files:**
- Modify: `.orchestrate/runs/20260307T084343Z-mbzxdl/state.json`
- Create backup: `.orchestrate/runs/20260307T084343Z-mbzxdl/state.json.pre-*.bak`

**Step 1: Back up the run state**

Copy the current `state.json` to a timestamped backup beside the run.

**Step 2: Update only the persisted workflow checksum**

Set `workflow_checksum` in the run state to the checksum of the edited workflow file so `resume` accepts the intentional config change.

**Step 3: Leave the restart point intact unless inspection proves otherwise**

The failed run already ended at the iteration cap with:
- `ReviewImplementation: completed`
- `ImplementationReviewGate: failed`
- `ImplementationCycleGate: failed`
- `FixImplementation: completed`
- `MaxImplementationCyclesExceeded: failed`

Do not clear completed review/fix history if resume can naturally restart from `ImplementationReviewGate` and then re-enter `ImplementationCycleGate` under the new limit.

### Task 3: Verify The Edited Workflow And Resume The Existing Run

**Files:**
- No new files; verification + runtime action

**Step 1: Run narrow verification**

Run:

```bash
pytest tests/test_workflow_examples_v0.py -k dsl_follow_on_plan_impl_review_loop_runtime -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/dsl_follow_on_plan_impl_review_loop.yaml --dry-run --stream-output
```

Expected: the targeted example test passes and the dry run validates successfully.

**Step 2: Resume in tmux**

Launch:

```bash
tmux -S /tmp/claude-tmux-sockets/claude.sock new-session -d -s dsl-follow-on-resume-30 \
  'cd /home/ollie/Documents/agent-orchestration && PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator resume 20260307T084343Z-mbzxdl --stream-output'
```

**Step 3: Verify the resumed run is live**

Check:

```bash
tmux -S /tmp/claude-tmux-sockets/claude.sock capture-pane -p -J -t dsl-follow-on-resume-30:0.0 -S -120
python - <<'PY'
import json
from pathlib import Path
data = json.loads(Path('.orchestrate/runs/20260307T084343Z-mbzxdl/state.json').read_text())
print(data.get('status'))
print(data.get('current_step'))
print(data.get('step_visits', {}))
PY
```

Expected: the resume process is alive, `current_step` is populated or heartbeat advances, and the run is no longer stranded at `MaxImplementationCyclesExceeded`.
