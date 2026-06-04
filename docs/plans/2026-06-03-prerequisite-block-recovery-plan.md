# Prerequisite Block Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make prerequisite work-item blocks re-enter the same recoverable blocked-design-gap state machine as ordinary blocks, instead of terminally blocking the drain by default.

**Architecture:** Preserve the original blocked gap as waiting on the selected prerequisite, and treat the selected prerequisite's own blocked state as the next recoverable obligation. The prerequisite recorder becomes a relationship/satisfaction recorder: it records completion as `RETRY_READY`, records recoverable prerequisite blocks as nonterminal `CONTINUE`, and reserves terminal `BLOCKED` only for cases where no recoverable target can be named or the selected prerequisite is explicitly terminal.

**Tech Stack:** Python helper scripts under `workflows/library/scripts/`, DSL v2.14 workflow YAML, pytest runtime/script tests in `tests/test_lisp_frontend_autonomous_drain_runtime.py`, and existing drain run-state JSON contracts.

---

## Problem

The current drain can recover an original blocked gap that requires prerequisite work:

1. Original gap blocks with `PREREQUISITE_GAP_REQUIRED`.
2. Recovery revises the target design if needed.
3. The original gap becomes `PREREQUISITE_WORK_PENDING`.
4. The next drain iteration runs `SELECT_PREREQUISITE_WORK`.
5. The selector picks or drafts prerequisite work.

The failure is step 6. If the selected prerequisite work item blocks, `workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py` currently marks the original gap as `PREREQUISITE_BLOCKED` and writes drain `BLOCKED`. That creates a second recovery route and prevents the newly blocked prerequisite from going through ordinary `GAP_DESIGN_REVISION_REQUIRED` / `TARGET_DESIGN_REVISION_REQUIRED` recovery.

This happened in run `20260603T220304Z-nl93d9`:

- original gap: `workflow-lisp-parametric-defproc-specialization-substrate`
- prerequisite gap: `workflow-lisp-owner-seam-split-prerequisite`
- prerequisite block route: `GAP_DESIGN_REVISION_REQUIRED`
- prerequisite block reason: `implementation_architecture_under_scoped`
- incorrect drain result: terminal `BLOCKED`

That prerequisite block was recoverable. The next drain iteration should have detected the prerequisite gap and revised its gap design.

## Desired State Machine

For an original gap `A` waiting on prerequisite `B`:

- `B` completes:
  - record prerequisite satisfaction;
  - set `A.recovery_status = RETRY_READY`;
  - write prerequisite recovery drain status `CONTINUE`;
  - next recovery iteration retries `A`.

- `B` blocks recoverably:
  - leave `A.recovery_status = PREREQUISITE_WORK_PENDING`;
  - keep `A.waiting_on_prerequisite_gap_id = B`;
  - keep `B` in `blocked_design_gaps` with its own `recovery_route`;
  - append a history event showing prerequisite recovery is pending on blocked prerequisite `B`;
  - write prerequisite recovery drain status `CONTINUE`;
  - next drain iteration detects `B` and routes it through normal blocked-design-gap recovery.

- `B` blocks terminally:
  - record that `A` is blocked because prerequisite `B` is terminal;
  - write prerequisite recovery drain status `BLOCKED`.

Terminal `BLOCKED` is rare. It is allowed only when the workflow cannot name a recoverable next obligation, or when the selected prerequisite itself is explicitly terminal.

## File Map

- Modify: `workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py`
  - Own prerequisite satisfaction and recoverable-prerequisite-block recording.
  - Stop treating all blocked prerequisites as terminal.
  - Add helper logic that inspects the selected prerequisite's own blocked-state entry.

- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`
  - Add focused script-level tests for recoverable prerequisite block, terminal prerequisite block, completion, and invalid/no-target cases.
  - Update existing prerequisite decline expectations if they currently require terminal `BLOCKED` where a recoverable obligation should be recorded.

- Modify only if tests prove it is necessary: `workflows/library/scripts/resolve_lisp_frontend_drain_iteration_status.py`
  - Expected current behavior is sufficient: `SELECT_PREREQUISITE_WORK` reads `prerequisite-recovery-drain-status.txt`. If the recorder writes `CONTINUE`, the repeat continues.

- Modify only if structure tests require it: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
  - Expected current wiring is sufficient: `RecordPrerequisiteRecoveryOutcome` already runs after prerequisite selected work and before `ResolveIterationDrainStatus`.

Do not modify selector prompts, target design docs, or gap-design artifacts in this fix. This is runtime recovery semantics, not a design-content revision.

## Contract Details

### Run-State Fields

The original blocked gap entry must keep:

- `recovery_route = PREREQUISITE_GAP_REQUIRED`
- `recovery_status = PREREQUISITE_WORK_PENDING` while prerequisite is still blocked/recovering
- `waiting_on_prerequisite_gap_id = <selected prerequisite id>`
- `waiting_on_prerequisite_source = DESIGN_GAP` or `BACKLOG_ITEM`
- `prerequisite_selection_bundle_path = <selection bundle>`
- `original_blocked_gap_id = <original gap id>`
- `prerequisite_recovery_status`
- `prerequisite_recovery_reason`
- `prerequisite_recovery_recorded_at_utc`

When prerequisite completes, set:

- `recovery_status = RETRY_READY`
- `prerequisite_recovery_status = COMPLETED`
- `prerequisite_recovery_reason = prerequisite_completed`

When prerequisite blocks recoverably, set on the original:

- `recovery_status = PREREQUISITE_WORK_PENDING`
- `prerequisite_recovery_status = BLOCKED_RECOVERABLE`
- `prerequisite_recovery_reason = selected_prerequisite_blocked_recoverable`

The selected prerequisite's own blocked entry must remain authoritative. Do not copy its recovery route into the original gap as if the original owns that block.

### Recoverable Versus Terminal

For selected prerequisite `B`, recoverable means:

- `B` exists in the relevant blocked-state map; and
- `B.reason == implementation_blocked`; and
- `B.recovery_route` exists; and
- `B.recovery_route != TERMINAL_BLOCKED`; and
- `B.recovery_reason` and `B.recovery_event_id` exist.

Terminal means:

- `B` exists in blocked state and `B.recovery_route == TERMINAL_BLOCKED`.

No-target / invalid means:

- selector did not name a selected prerequisite; or
- selector named the original gap as its own prerequisite; or
- selector selected work without a relation and no recoverable selected item can be identified; or
- selected work reported a status that cannot be reconciled with completed or blocked run state.

For no-target / invalid cases, prefer recording a concrete recoverable obligation if one can be named. Only write terminal `BLOCKED` when the recorder cannot identify either the selected prerequisite or another concrete recovery target.

## Task 1: Add Failing Tests For Recoverable Prerequisite Blocks

**Files:**

- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add a script-level test for recoverable selected prerequisite block**

Add a test near existing prerequisite recovery tests:

```python
def test_prerequisite_recovery_recoverable_prerequisite_block_continues(tmp_path):
    workspace = tmp_path
    state_path = workspace / "state/run_state.json"
    pre_selection_path = workspace / "state/blocked-recovery.json"
    selection_path = workspace / "state/prerequisite-selector/selection.json"
    selected_status_path = workspace / "state/prerequisite/drain_status.txt"
    summary_path = workspace / "artifacts/prerequisite-recovery-summary.json"
    drain_status_path = workspace / "state/prerequisite-recovery-drain-status.txt"

    state_path.parent.mkdir(parents=True)
    selection_path.parent.mkdir(parents=True)
    selected_status_path.parent.mkdir(parents=True)
    summary_path.parent.mkdir(parents=True)

    state_path.write_text(json.dumps({
        "schema": "lisp_frontend_run_state/v1",
        "blocked_design_gaps": {
            "original-gap": {
                "reason": "implementation_blocked",
                "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                "recovery_reason": "prerequisite_gap_required",
                "recovery_status": "PREREQUISITE_WORK_PENDING",
                "recovery_event_id": "run:original-gap:block",
            },
            "prerequisite-gap": {
                "reason": "implementation_blocked",
                "recovery_route": "GAP_DESIGN_REVISION_REQUIRED",
                "recovery_reason": "implementation_architecture_under_scoped",
                "recovery_event_id": "run:prerequisite-gap:block",
            },
        },
        "completed_design_gaps": [],
        "blocked_items": {},
        "completed_items": [],
        "history": [],
    }) + "\n")
    pre_selection_path.write_text(json.dumps({
        "pre_selection_route": "SELECT_PREREQUISITE_WORK",
        "design_gap_id": "original-gap",
        "recovery_route": "PREREQUISITE_GAP_REQUIRED",
        "recovery_reason": "prerequisite_gap_required",
        "recovery_status": "PREREQUISITE_WORK_PENDING",
        "recovery_event_id": "run:original-gap:block",
    }) + "\n")
    selection_path.write_text(json.dumps({
        "selection_status": "DRAFT_DESIGN_GAP",
        "design_gap_id": "prerequisite-gap",
        "prerequisite_relation": "Unblocks original-gap",
    }) + "\n")
    selected_status_path.write_text("CONTINUE\n")

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py",
        "--pre-selection-bundle-path", str(pre_selection_path),
        "--selection-bundle-path", str(selection_path),
        "--selected-work-status-path", str(selected_status_path),
        "--run-state-path", str(state_path),
        "--summary-path", str(summary_path),
        "--drain-status-path", str(drain_status_path),
    )

    state = json.loads(state_path.read_text())
    original = state["blocked_design_gaps"]["original-gap"]
    prerequisite = state["blocked_design_gaps"]["prerequisite-gap"]

    assert drain_status_path.read_text().strip() == "CONTINUE"
    assert original["recovery_status"] == "PREREQUISITE_WORK_PENDING"
    assert original["prerequisite_recovery_status"] == "BLOCKED_RECOVERABLE"
    assert original["waiting_on_prerequisite_gap_id"] == "prerequisite-gap"
    assert prerequisite["recovery_route"] == "GAP_DESIGN_REVISION_REQUIRED"
    assert state["history"][-1]["event"] == "prerequisite_recovery_pending_on_blocked_prerequisite"
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_prerequisite_recovery_recoverable_prerequisite_block_continues -q
```

Expected before implementation: FAIL because the recorder writes `BLOCKED` and sets original `recovery_status` to `PREREQUISITE_BLOCKED`.

## Task 2: Add Terminal And Completion Coverage

**Files:**

- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Keep or update the existing completion test**

Use existing `test_prerequisite_recovery_completion_marks_original_gap_retry_ready` as the completion guard. Confirm it asserts:

- drain status `CONTINUE`;
- original `recovery_status == RETRY_READY`;
- original `prerequisite_recovery_status == COMPLETED`;
- history event `prerequisite_recovery_satisfied`.

If any assertion is missing, add it.

- [ ] **Step 2: Add a terminal prerequisite block test**

Add a test where selected prerequisite is in `blocked_design_gaps` with:

```json
{
  "reason": "implementation_blocked",
  "recovery_route": "TERMINAL_BLOCKED",
  "recovery_reason": "unrecoverable_after_fix_attempt",
  "recovery_event_id": "run:prerequisite-gap:block"
}
```

Expected assertions:

- recorder writes drain status `BLOCKED`;
- original `recovery_status == PREREQUISITE_BLOCKED`;
- original `prerequisite_recovery_status == BLOCKED_TERMINAL`;
- original `prerequisite_recovery_reason == selected_prerequisite_terminal_blocked`;
- summary reason is `selected_prerequisite_terminal_blocked`.

- [ ] **Step 3: Reassess invalid selector tests**

Find existing `test_prerequisite_recovery_decline_keeps_original_gap_blocked`.

If it currently expects terminal `BLOCKED` for selector decline, keep that only if the selector output names no recoverable target. The test name should make that explicit, for example:

```python
def test_prerequisite_recovery_decline_without_recovery_target_blocks_explicitly(tmp_path):
    ...
```

Do not add tests that make terminal block the default for malformed but recoverable situations.

- [ ] **Step 4: Run prerequisite recorder tests**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "prerequisite_recovery" -q
```

Expected before implementation: new recoverable-block test fails; existing completion test should still pass unless current code is already broken.

## Task 3: Implement Recorder Semantics

**Files:**

- Modify: `workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py`

- [ ] **Step 1: Add selected blocked-entry lookup**

Add helpers:

```python
def _blocked_entry(state: dict[str, Any], *, source: str, item_id: str) -> dict[str, Any]:
    if source == "DESIGN_GAP":
        return dict((state.get("blocked_design_gaps") or {}).get(item_id) or {})
    if source == "BACKLOG_ITEM":
        return dict((state.get("blocked_items") or {}).get(item_id) or {})
    return {}


def _recoverable_blocked_entry(entry: dict[str, Any]) -> bool:
    if not entry:
        return False
    if str(entry.get("reason") or "").strip() != "implementation_blocked":
        return False
    route = str(entry.get("recovery_route") or "").strip()
    if not route or route == "TERMINAL_BLOCKED":
        return False
    if not str(entry.get("recovery_reason") or "").strip():
        return False
    if not str(entry.get("recovery_event_id") or "").strip():
        return False
    return True
```

- [ ] **Step 2: Add explicit pending-on-prerequisite recording**

Add or adapt `_record_original(...)` calls so recoverable prerequisite blocks record:

```python
status="PREREQUISITE_WORK_PENDING"
prerequisite_status="BLOCKED_RECOVERABLE"
reason="selected_prerequisite_blocked_recoverable"
```

The history event for this case should be:

```text
prerequisite_recovery_pending_on_blocked_prerequisite
```

Keep `prerequisite_recovery_blocked` for actual terminal prerequisite blocks or no-target failures.

- [ ] **Step 3: Change selected blocked branch**

Replace current behavior:

```python
elif _is_blocked(state, source=selected_source, item_id=selected_id):
    reason = "selected_prerequisite_blocked"
...
status="PREREQUISITE_BLOCKED"
drain_status="BLOCKED"
```

with:

```python
elif _is_blocked(state, source=selected_source, item_id=selected_id):
    entry = _blocked_entry(state, source=selected_source, item_id=selected_id)
    if _recoverable_blocked_entry(entry):
        _record_original(
            state,
            original_gap_id=original_gap_id,
            selection_path=selection_path,
            selected_source=selected_source,
            selected_id=selected_id,
            status="PREREQUISITE_WORK_PENDING",
            prerequisite_status="BLOCKED_RECOVERABLE",
            reason="selected_prerequisite_blocked_recoverable",
        )
        return _finish(
            state_path=state_path,
            state=state,
            summary_path=Path(args.summary_path),
            drain_status_path=Path(args.drain_status_path),
            summary={
                "record_status": "WAITING_ON_RECOVERABLE_PREREQUISITE",
                "original_blocked_gap_id": original_gap_id,
                "selected_prerequisite_id": selected_id,
                "selected_prerequisite_source": selected_source,
                "reason": "selected_prerequisite_blocked_recoverable",
                "selected_prerequisite_recovery_route": entry.get("recovery_route", ""),
                "selected_prerequisite_recovery_reason": entry.get("recovery_reason", ""),
            },
            drain_status="CONTINUE",
        )
    if str(entry.get("recovery_route") or "").strip() == "TERMINAL_BLOCKED":
        reason = "selected_prerequisite_terminal_blocked"
        prerequisite_status = "BLOCKED_TERMINAL"
    else:
        reason = "selected_prerequisite_blocked_without_recoverable_metadata"
        prerequisite_status = "BLOCKED_UNRECOVERABLE"
```

Then use `prerequisite_status` in the terminal `_record_original(...)` call.

- [ ] **Step 4: Keep completion branch unchanged**

Do not change the `_is_completed(...)` branch except to keep history/status naming consistent.

- [ ] **Step 5: Run focused recorder tests**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "prerequisite_recovery" -q
```

Expected after implementation: all prerequisite recovery tests pass.

## Task 4: Verify Drain-Level Routing Still Composes

**Files:**

- Modify only if necessary: `workflows/library/scripts/resolve_lisp_frontend_drain_iteration_status.py`
- Modify only if necessary: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Inspect resolver table tests**

Find the resolver parameterized cases around `SELECT_PREREQUISITE_WORK`.

Update or add the case:

```python
("SELECT_PREREQUISITE_WORK", ..., prerequisite_status="CONTINUE", expected="CONTINUE")
```

This is already likely present. Keep it as the route-level proof that recoverable prerequisite block lets the repeat continue.

- [ ] **Step 2: Add or update a structure test**

Ensure the workflow still runs `RecordPrerequisiteRecoveryOutcome` after prerequisite selected work and before `ResolveIterationDrainStatus`.

The structure test should not assert literal prompt text. It may assert step IDs and command script path.

- [ ] **Step 3: Run targeted workflow tests**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "prerequisite or ResolveIterationDrainStatus or design_delta_drain" -q
```

Expected: tests pass.

## Task 5: Validate The Concrete Reproduction Shape

**Files:**

- No source edits expected.

- [ ] **Step 1: Reproduce the run-state shape from `20260603T220304Z-nl93d9` in a test fixture or temporary directory**

Use the exact semantic pattern:

- original gap blocked with `PREREQUISITE_GAP_REQUIRED`;
- selected prerequisite gap present in `blocked_design_gaps`;
- selected prerequisite gap route `GAP_DESIGN_REVISION_REQUIRED`;
- selected work status `CONTINUE`;
- prerequisite selection relation present.

This is the same shape as the live failure and should be covered by the Task 1 test.

- [ ] **Step 2: Run the exact new regression test**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_prerequisite_recovery_recoverable_prerequisite_block_continues -q
```

Expected: pass.

- [ ] **Step 3: Run script lint / diff hygiene**

Run:

```bash
python -m compileall workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py
git diff --check
```

Expected: both pass.

## Task 6: Commit The Fix

**Files:**

- `workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py`
- `tests/test_lisp_frontend_autonomous_drain_runtime.py`
- `workflows/library/scripts/resolve_lisp_frontend_drain_iteration_status.py` only if changed
- `workflows/examples/lisp_frontend_design_delta_drain.yaml` only if changed

- [ ] **Step 1: Review staged diff**

Run:

```bash
git diff -- workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py tests/test_lisp_frontend_autonomous_drain_runtime.py workflows/library/scripts/resolve_lisp_frontend_drain_iteration_status.py workflows/examples/lisp_frontend_design_delta_drain.yaml
```

Check that the diff is only prerequisite recovery semantics and tests.

- [ ] **Step 2: Stage only relevant files**

Run:

```bash
git add \
  workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py \
  tests/test_lisp_frontend_autonomous_drain_runtime.py
```

If resolver or YAML changed, stage those too.

- [ ] **Step 3: Commit**

Run:

```bash
git commit -m "Recover blocked prerequisite gaps through normal drain path"
```

## Task 7: Resume The Existing Blocked Drain

**Files:**

- No source edits expected.

- [ ] **Step 1: Resume rather than relaunch**

Because run `20260603T220304Z-nl93d9` already passed prior gates and failed downstream, use resume:

```bash
python -m orchestrator resume 20260603T220304Z-nl93d9 --stream-output
```

Launch it in tmux and disable summarization / live notes unless the user asks otherwise.

- [ ] **Step 2: Start or retarget watchdog**

Start a real watchdog loop targeting the resumed run id. If plain resume preserves the same run id, target `20260603T220304Z-nl93d9`. If resume force-restarts or emits a new run id, target the new run id.

- [ ] **Step 3: Verify behavior**

Expected next behavior:

1. The drain sees the prerequisite gap `workflow-lisp-owner-seam-split-prerequisite` as the current recoverable blocked design gap.
2. It routes through `GAP_DESIGN_REVISION_REQUIRED`.
3. It revises the prerequisite gap design/plan instead of selecting unrelated normal work.
4. Original gap `workflow-lisp-parametric-defproc-specialization-substrate` remains waiting on prerequisite until prerequisite completion.

## Acceptance Criteria

- Recoverable selected prerequisite blocks write drain `CONTINUE`, not terminal `BLOCKED`.
- Original blocked gap remains `PREREQUISITE_WORK_PENDING`.
- Original blocked gap records which prerequisite it is waiting on.
- Selected prerequisite's own blocked-state entry remains intact and authoritative.
- Next drain iteration can detect and recover the selected prerequisite through ordinary blocked-gap recovery.
- Completed prerequisite still transitions original gap to `RETRY_READY`.
- Explicit terminal prerequisite block still produces drain `BLOCKED`.
- No prompt text assertions are added.
- Focused tests pass.
- `python -m compileall` for the modified script passes.
- `git diff --check` passes.

## Non-Goals

- Do not add deterministic prerequisite scheduling.
- Do not change selector prompt semantics.
- Do not modify target design content.
- Do not fix unrelated `phase_stdlib` or reusable-phase-state failures in this change.
- Do not relaunch the whole drain unless resume is impossible.
