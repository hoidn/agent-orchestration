# NeurIPS Queue Ownership Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Keep each checkbox current as work progresses.

**Goal:** Prevent a NeurIPS backlog-drain run from crashing when an implementation provider prematurely moves the selected backlog item to `docs/backlog/done/`.

**Architecture:** The workflow is the sole owner of backlog queue transitions. Providers may edit code, docs, artifacts, and the selected backlog item's content, but they must not move the selected item between `docs/backlog/active/`, `docs/backlog/in_progress/`, `docs/backlog/done/`, or `docs/backlog/paused/`. The post-implementation reconcile step enforces this deterministically: if the selected item was prematurely moved to `done`, it restores the item to `in_progress` and lets the existing workflow completion step perform the authoritative `done` transition and run-state update.

**Tech Stack:** Python helper scripts, workflow YAML, workflow prompt assets, pytest, agent-orchestration DSL `2.7`/`2.12`, downstream PtychoPINN workflow copy.

---

## Root Cause

The failed PtychoPINN workflow had already passed implementation review. The implementation provider then moved:

`docs/backlog/in_progress/2026-05-04-cdi-lines128-srunet-branch-objective-ablation.md`

to:

`docs/backlog/done/2026-05-04-cdi-lines128-srunet-branch-objective-ablation.md`

before `RecordCompletedItem` ran.

`ReconcileSelectedItemQueueAfterImplementation` currently accepts only `active` or `in_progress`. When neither existed, it failed, even though the item was actually completed and present in `done`.

## Fix Contract

- Queue transitions are workflow-owned.
- Implementation providers must not move backlog files between queue directories.
- The pre-plan reconciliation path remains strict and must not accept `done`.
- Only the post-implementation reconciliation path may recover a premature `done` move.
- If `done` and `active` or `in_progress` both exist for the selected item, fail as an ambiguous duplicate-state error.
- If only `done/<selected-item>.md` exists after implementation, move it back to `in_progress/<selected-item>.md`, rewrite `plan_path`, and continue.
- The existing completion path remains the only place that records final completion.

## File Structure

Canonical repo:

```text
workflows/library/scripts/reconcile_neurips_selected_item.py
workflows/library/neurips_selected_backlog_item.yaml
workflows/library/prompts/neurips_backlog_implementation_phase/implement_implementation.md
tests/test_neurips_selected_item_reconcile.py
tests/test_major_project_workflows.py
```

Downstream PtychoPINN copy:

```text
/home/ollie/Documents/PtychoPINN/workflows/library/scripts/reconcile_neurips_selected_item.py
/home/ollie/Documents/PtychoPINN/workflows/library/neurips_selected_backlog_item.yaml
/home/ollie/Documents/PtychoPINN/workflows/library/prompts/neurips_backlog_implementation_phase/implement_implementation.md
/home/ollie/Documents/PtychoPINN/tests/studies/test_neurips_steered_backlog_helpers.py
```

---

## Task 1: Add Focused Reconcile Tests

- [ ] Create `tests/test_neurips_selected_item_reconcile.py`.
- [ ] Add a helper that builds a temporary repo-like tree with:
  - `docs/backlog/active/`
  - `docs/backlog/in_progress/`
  - `docs/backlog/done/`
  - `docs/plans/example-plan.md`
  - `state/out.txt`
- [ ] Add `test_reconcile_recovers_premature_done_move_when_enabled`:
  - Put the selected item only in `docs/backlog/done/<item>.md`.
  - Run `workflows/library/scripts/reconcile_neurips_selected_item.py` with `--recover-premature-done`.
  - Assert exit code `0`.
  - Assert `docs/backlog/done/<item>.md` no longer exists.
  - Assert `docs/backlog/in_progress/<item>.md` exists.
  - Assert the item's frontmatter `plan_path:` equals the supplied plan path.
  - Assert the output file contains the in-progress path.
- [ ] Add `test_reconcile_rejects_premature_done_move_by_default`:
  - Use the same premature-done state.
  - Omit `--recover-premature-done`.
  - Assert nonzero exit and an error explaining the item exists in neither `active` nor `in_progress`.
- [ ] Add `test_reconcile_rejects_duplicate_done_and_in_progress_state`:
  - Put the same selected item in both `docs/backlog/in_progress/` and `docs/backlog/done/`.
  - Run with `--recover-premature-done`.
  - Assert nonzero exit and an ambiguous duplicate-state error.

Run:

```bash
pytest -q tests/test_neurips_selected_item_reconcile.py --collect-only
pytest -q tests/test_neurips_selected_item_reconcile.py
```

## Task 2: Implement Post-Implementation Recovery Mode

- [ ] Update `workflows/library/scripts/reconcile_neurips_selected_item.py`.
- [ ] Add `--recover-premature-done` as an opt-in boolean flag.
- [ ] Derive `done_path` from the selected item filename:

```python
done_path = Path("docs/backlog/done") / in_progress_path.name
```

- [ ] Validate `done_path` through the same safe repo-relative path logic.
- [ ] Preserve current behavior when the flag is absent.
- [ ] When the flag is present:
  - If `active`, `in_progress`, and `done` are all absent, fail.
  - If `done` exists together with `active` or `in_progress`, fail as duplicate queue state.
  - If only `done` exists, create `in_progress` parent directories and rename `done_path` to `in_progress_path`.
  - Then run the existing plan-path rewrite and output-path write logic.
- [ ] Keep the script's stdout simple: print the reconciled in-progress path, as it does now.

Implementation sketch:

```python
done_path = Path("docs/backlog/done") / in_progress_path.name
done_exists = done_path.is_file()

if done_exists and (active_exists or in_progress_exists):
    raise SystemExit(
        f"Selected item has ambiguous queue state across done and active/in_progress: {in_progress_path.name}"
    )

if not active_exists and not in_progress_exists:
    if args.recover_premature_done and done_exists:
        in_progress_path.parent.mkdir(parents=True, exist_ok=True)
        done_path.rename(in_progress_path)
        in_progress_exists = True
    else:
        raise SystemExit(...)
```

Run:

```bash
python -m compileall -q workflows/library/scripts
pytest -q tests/test_neurips_selected_item_reconcile.py
```

## Task 3: Wire Recovery Only After Implementation

- [ ] Update `workflows/library/neurips_selected_backlog_item.yaml`.
- [ ] Add `--recover-premature-done` only to `ReconcileSelectedItemQueueAfterImplementation`.
- [ ] Do not add the flag to `RewriteSelectedItemPlanPath`.
- [ ] Add or update a workflow-structure test in `tests/test_major_project_workflows.py`:
  - Assert `ReconcileSelectedItemQueueAfterImplementation` invokes `reconcile_neurips_selected_item.py` with `--recover-premature-done`.
  - Assert `RewriteSelectedItemPlanPath` invokes the same helper without `--recover-premature-done`.

Run:

```bash
pytest -q tests/test_major_project_workflows.py -k "neurips and reconcile"
```

## Task 4: Tighten Provider Boundary Prompt

- [ ] Update `workflows/library/prompts/neurips_backlog_implementation_phase/implement_implementation.md`.
- [ ] Add one concise rule near the implementation scope / completion instructions:

```text
Do not move backlog queue files between `docs/backlog/active/`, `docs/backlog/in_progress/`, `docs/backlog/done/`, or `docs/backlog/paused/`; the workflow owns queue transitions after review.
```

- [ ] Do not add prompt tests that assert this literal wording.
- [ ] Do not make review/fix prompts verbose unless inspection shows they currently instruct providers to move queue files.

Run:

```bash
rg -n "move backlog|docs/backlog/(active|in_progress|done|paused)|queue transitions" workflows/library/prompts/neurips_backlog_implementation_phase
```

## Task 5: Canonical Verification

- [ ] Run focused tests:

```bash
pytest -q tests/test_neurips_selected_item_reconcile.py
pytest -q tests/test_major_project_workflows.py -k "neurips and reconcile"
```

- [ ] Run a loader smoke check for the edited workflow:

```bash
python - <<'PY'
from pathlib import Path
from orchestrator.workflow_loader import WorkflowLoader

WorkflowLoader(Path(".")).load_bundle(Path("workflows/library/neurips_selected_backlog_item.yaml"))
print("loaded")
PY
```

- [ ] Run syntax and whitespace checks:

```bash
python -m compileall -q workflows/library/scripts
git diff --check
```

## Task 6: Propagate To PtychoPINN

- [ ] Inspect downstream files before editing because the PtychoPINN worktree may be dirty:

```bash
git -C /home/ollie/Documents/PtychoPINN status --short
git -C /home/ollie/Documents/PtychoPINN diff -- workflows/library/scripts/reconcile_neurips_selected_item.py workflows/library/neurips_selected_backlog_item.yaml workflows/library/prompts/neurips_backlog_implementation_phase/implement_implementation.md
```

- [ ] Apply equivalent script, workflow YAML, and prompt changes to:

```text
/home/ollie/Documents/PtychoPINN/workflows/library/scripts/reconcile_neurips_selected_item.py
/home/ollie/Documents/PtychoPINN/workflows/library/neurips_selected_backlog_item.yaml
/home/ollie/Documents/PtychoPINN/workflows/library/prompts/neurips_backlog_implementation_phase/implement_implementation.md
```

- [ ] Add or update downstream tests in:

```text
/home/ollie/Documents/PtychoPINN/tests/studies/test_neurips_steered_backlog_helpers.py
```

- [ ] Run downstream checks from the PtychoPINN repo root in `ptycho311`:

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate ptycho311
pytest -q tests/studies/test_neurips_steered_backlog_helpers.py
python -m compileall -q workflows/library/scripts
python - <<'PY'
from pathlib import Path
from orchestrator.workflow_loader import WorkflowLoader

WorkflowLoader(Path(".")).load_bundle(Path("workflows/library/neurips_selected_backlog_item.yaml"))
print("loaded")
PY
```

## Task 7: Resume The Failed PtychoPINN Run

- [ ] After downstream propagation and verification, resume the failed run instead of launching a fresh one:

```bash
tmux new-session -d -s ptychopinn-neurips-resume-queue-guard 'cd /home/ollie/Documents/PtychoPINN && source ~/miniconda3/etc/profile.d/conda.sh && conda activate ptycho311 && python -m orchestrator resume 20260505T003615Z-kz8gi5 --stream-output'
```

- [ ] Check status:

```bash
tmux capture-pane -pt ptychopinn-neurips-resume-queue-guard -S -200
python -m orchestrator status 20260505T003615Z-kz8gi5
```

- [ ] If resume cannot re-enter the failed nested reconcile step, run the new deterministic recovery helper manually in PtychoPINN with `--recover-premature-done`, then resume again. Record the manual recovery command and result in the final report.

## Task 8: Stage And Commit

- [ ] Stage only scoped agent-orchestration files:

```bash
git add \
  docs/plans/2026-05-05-neurips-queue-ownership-guard-plan.md \
  workflows/library/scripts/reconcile_neurips_selected_item.py \
  workflows/library/neurips_selected_backlog_item.yaml \
  workflows/library/prompts/neurips_backlog_implementation_phase/implement_implementation.md \
  tests/test_neurips_selected_item_reconcile.py \
  tests/test_major_project_workflows.py
git commit -m "fix: recover premature NeurIPS backlog queue moves"
```

- [ ] Stage only scoped PtychoPINN files:

```bash
git -C /home/ollie/Documents/PtychoPINN add \
  workflows/library/scripts/reconcile_neurips_selected_item.py \
  workflows/library/neurips_selected_backlog_item.yaml \
  workflows/library/prompts/neurips_backlog_implementation_phase/implement_implementation.md \
  tests/studies/test_neurips_steered_backlog_helpers.py
git -C /home/ollie/Documents/PtychoPINN commit -m "fix: recover premature NeurIPS backlog queue moves"
```

- [ ] If any listed file has unrelated pre-existing edits, use partial staging and explicitly report which hunks were staged.

## Expected Outcome

The previously failed run can continue from the current state: the selected item exists in `done`, the post-implementation reconcile step restores it to `in_progress`, and the existing workflow completion step performs the final `done` move and completion bookkeeping. Future provider-side queue moves no longer crash the drain, while genuine duplicate or missing queue states still fail deterministically.
