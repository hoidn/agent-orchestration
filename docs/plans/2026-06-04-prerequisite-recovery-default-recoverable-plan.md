# Prerequisite Recovery Default Recoverable Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Lisp frontend drain prerequisite recovery default to continued repo-local recovery, with terminal drain `BLOCKED` reserved for explicit user-input-required evidence.

**Architecture:** Keep durable blocked state small and fact-based: `recovery_route`, `recovery_status`, optional `waiting_on_prerequisite_gap_id`, evidence paths, and a user-input terminal reason. Do not add a standalone prerequisite scheduler or a large prerequisite-state taxonomy; derive recovery routing from blocked state plus completed/blocked child state. Prompt/provider output may classify semantic prerequisite needs, but deterministic scripts decide only validation, state reconciliation, and whether user input is explicitly required.

**Tech Stack:** Python workflow helper scripts, YAML workflow routing, pytest runtime tests, orchestrator dry-run validation.

---

## Problem

`PREREQUISITE_GAP_REQUIRED` is currently recoverable in intent but still has terminal-looking branches in implementation:

- `record_lisp_frontend_prerequisite_recovery_outcome.py` writes `PREREQUISITE_BLOCKED` and drain `BLOCKED` for selector decline, missing relation, self-selection without completed-prerequisite evidence, malformed/missing selected work status, and selected prerequisite terminal block.
- `lisp_frontend_design_delta_drain.yaml` exposes prerequisite recorder status as `RETRY_READY | WAITING_ON_RECOVERABLE_PREREQUISITE | BLOCKED`, making prerequisite awkwardness a terminal iteration result.
- `record_lisp_frontend_blocked_recovery_outcome.py` treats `REVISE` from blocked target-design recovery review as terminal `BLOCKED` with `*_revision_exhausted`, even though `REVISE` means the recovery design update needs another revision pass.
- tests still assert several `PREREQUISITE_BLOCKED` outcomes.

The desired policy is simpler:

```text
implementation block from design-gap work is recoverable by default.
terminal drain BLOCKED means USER_INPUT_REQUIRED only.
```

`USER_INPUT_REQUIRED` is valid only for:

```text
major unresolvable ambiguity in intention that cannot be resolved by target-design or gap-design revision
environment, access, credential, resource, or local setup failure that requires user intervention
true external authority outside repo-local workflow/design/code/prompt/contract repair
```

Prerequisite problems should normally route to one of:

```text
retry original gap
recover selected prerequisite gap
revise the target design
revise the selected/prerequisite gap design
reselect prerequisite work with better context
```

They should not terminally block merely because selector output was awkward or evidence is incomplete.

They also should not terminally block merely because the recovery design review requested `REVISE`. A recovery-review `REVISE` is a nonterminal workflow-control signal: keep the same original blocked gap as the current recovery obligation, revise the recovery design again, and only stop on explicit user-input-required evidence.

## File Map

- Modify: `workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py`
  - Owns prerequisite-selection outcome recording.
  - Change terminal prerequisite outcomes into recoverable blocked-state updates unless explicit user-input-required evidence is present.

- Modify: `workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py`
  - Owns pre-selection recovery routing.
  - Keep completed-prerequisite reconciliation, and add recovery routing for prerequisite records that need design revision rather than terminal block.

- Modify: `workflows/library/scripts/select_lisp_frontend_blocked_recovery_route.py`
  - Owns normalization of work-item classifier route.
  - Tighten `TERMINAL_BLOCKED/user_decision_required` to require explicit evidence that repo-local recovery cannot decide the issue.

- Modify: `workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py`
  - Owns durable blocked state after classifier/design revision.
  - Ensure `TERMINAL_BLOCKED` records are user-input-required only and preserve clear terminal evidence.
  - Ensure target-design recovery review `REVISE` is nonterminal for recoverable routes and keeps the same blocked gap current.

- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
  - Keep `TERMINAL_BLOCKED` in classifier output if needed for provider contract compatibility.
  - Change prerequisite recovery recorder output/status contract away from generic `BLOCKED` for recoverable prerequisite issues.
  - Route recoverable prerequisite recorder outcomes back through recovery-before-selection, not terminal drain.
  - Keep blocked target-design recovery review `REVISE` in the recovery-before-selection loop rather than resolving the iteration to terminal drain `BLOCKED`.

- Modify: `workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md`
  - Clarify that `TERMINAL_BLOCKED/user_decision_required` is only for major unresolvable ambiguity in intention, environment/user-intervention issues, or true external authority outside repo-local design/gap/prompt/contract/code repair.

- Modify: `workflows/library/prompts/lisp_frontend_implementation_phase/implement_plan.md`
  - Keep implementation-block output guidance aligned: repo-local scope, dependency, contract, prompt, design, test, or prerequisite issues should be reported as recoverable blockers, not user-decision terminal blockers.

- Modify: `workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/implement_plan.md`
  - Same as above for design-delta implementation blocks.

- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`
  - Add failing tests for the revised policy.
  - Replace tests that expect terminal prerequisite block for recoverable cases.

## State Contract

Do not introduce a broad prerequisite state taxonomy.

Use this effective contract:

```json
{
  "reason": "implementation_blocked",
  "recovery_route": "PREREQUISITE_GAP_REQUIRED",
  "recovery_reason": "prerequisite_gap_required",
  "recovery_status": "PREREQUISITE_WORK_PENDING | RETRY_READY | USER_INPUT_REQUIRED",
  "waiting_on_prerequisite_gap_id": "optional design gap id",
  "waiting_on_prerequisite_source": "optional source",
  "user_input_reason": "optional reason when recovery_status is USER_INPUT_REQUIRED"
}
```

Compatibility note:

- Existing `PREREQUISITE_BLOCKED` records should be treated as recoverable unless their `prerequisite_recovery_reason` or classifier summary explicitly proves user input is required.
- Existing `TERMINAL_BLOCKED/user_decision_required` remains accepted only when supported by explicit evidence that repo-local recovery is unavailable.

## Routing Rules

For every blocked design gap before normal selection:

```text
if recovery_status == USER_INPUT_REQUIRED:
    pre_selection_route = BLOCKED

elif recovery_status == RETRY_READY:
    pre_selection_route = RECOVER_BLOCKED_DESIGN_GAP

elif waiting_on_prerequisite_gap_id is completed:
    treat as RETRY_READY

elif waiting_on_prerequisite_gap_id is blocked with recoverable metadata:
    make that prerequisite the current recovery obligation

elif recovery_route == PREREQUISITE_GAP_REQUIRED:
    select/revise prerequisite work in recovery context

else:
    use existing recovery route
```

Prerequisite recorder policy:

```text
selected prerequisite completed:
    record original RETRY_READY, drain CONTINUE

selected prerequisite recoverably blocked:
    record original PREREQUISITE_WORK_PENDING waiting_on selected prerequisite, drain CONTINUE

selected prerequisite terminal/user-input-required:
    record original PREREQUISITE_WORK_PENDING waiting_on selected prerequisite, drain CONTINUE
    let detector make the selected prerequisite the current user-input-required obligation

selector declined / malformed / missing relation / invalid status:
    record recoverable design-revision-needed outcome, drain CONTINUE
    do not terminal block unless explicit user-input-required evidence is present

self-selection:
    if recorded waiting prerequisite is completed:
        record original RETRY_READY, drain CONTINUE
    else:
        record recoverable design-revision-needed outcome, drain CONTINUE
```

Target-design recovery review policy:

```text
target-design recovery review APPROVE:
    record approved recovery revision
    transition to prerequisite selection or recovered-gap retry as appropriate
    drain CONTINUE or RUN_RECOVERED_GAP according to the approved route

target-design recovery review REVISE:
    keep the same original blocked gap in blocked_design_gaps
    keep recovery_route and recovery_status pointing at the same recovery obligation
    record the review report path and revise reason/history
    drain CONTINUE
    next drain iteration must recover the same blocked gap before normal selection

target-design recovery review BLOCKED or explicit user-input-required:
    terminal BLOCKED only when the review evidence says repo-local recovery cannot choose the next action
```

## Task 1: Add Red Tests For Recoverable Prerequisite Awkwardness

**Files:**
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add selector-decline test**

Add a test near existing prerequisite recovery tests:

```python
def test_prerequisite_selector_decline_routes_to_recoverable_design_revision(tmp_path):
    ...
    selection_bundle.write_text(
        json.dumps({"selection_status": "DONE", "selection_rationale": "No safe prerequisite found yet."}) + "\n",
        encoding="utf-8",
    )
    selected_status.write_text("DONE\n", encoding="utf-8")
    ...
    assert blocked["recovery_status"] == "PREREQUISITE_WORK_PENDING"
    assert blocked["prerequisite_recovery_reason"] == "prerequisite_selector_declined"
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"
    assert summary["record_status"] == "RECOVERY_CONTINUES"
```

- [ ] **Step 2: Add missing-relation test**

```python
def test_prerequisite_missing_relation_remains_recoverable(tmp_path):
    ...
    selection_bundle.write_text(
        json.dumps({"selection_status": "DRAFT_DESIGN_GAP", "design_gap_id": "generic-context-capability"}) + "\n",
        encoding="utf-8",
    )
    ...
    assert blocked["recovery_status"] == "PREREQUISITE_WORK_PENDING"
    assert blocked["prerequisite_recovery_reason"] == "missing_prerequisite_relation"
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"
```

- [ ] **Step 3: Add selected-prerequisite-terminal test**

Existing behavior likely expects original terminal block. Replace or add:

```python
def test_prerequisite_selected_user_input_required_keeps_original_recoverable(tmp_path):
    ...
    # selected prerequisite has TERMINAL_BLOCKED/user_decision_required
    ...
    assert original["recovery_status"] == "PREREQUISITE_WORK_PENDING"
    assert original["waiting_on_prerequisite_gap_id"] == "owner-seam-prerequisite"
    assert original["prerequisite_recovery_reason"] == "selected_prerequisite_user_input_required"
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"
```

- [ ] **Step 4: Add classifier normalization test**

Add or adjust a test for `select_lisp_frontend_blocked_recovery_route.py`:

```python
def test_terminal_block_requires_explicit_user_input_evidence(tmp_path):
    bundle = {
        "blocked_recovery_route": "TERMINAL_BLOCKED",
        "reason": "user_decision_required",
        "summary": "Selector output was malformed and needs target design revision.",
    }
    ...
    assert route["blocked_recovery_route"] == "GAP_DESIGN_REVISION_REQUIRED"
```

- [ ] **Step 5: Run tests and verify they fail for current behavior**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "prerequisite_recovery or terminal_blocker or blocked_recovery" -q
```

Expected:

- New decline/missing relation/selected terminal tests fail because current recorder writes `BLOCKED`.
- Existing tests may fail where they still expect `PREREQUISITE_BLOCKED`.

## Task 2: Make Prerequisite Recorder Default To Continued Recovery

**Files:**
- Modify: `workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py`

- [ ] **Step 1: Add helper for recoverable prerequisite continuation**

Add:

```python
def _record_recovery_continues(
    state: dict[str, Any],
    *,
    original_gap_id: str,
    selection_path: Path,
    selected_source: str,
    selected_id: str,
    reason: str,
) -> None:
    _record_original(
        state,
        original_gap_id=original_gap_id,
        selection_path=selection_path,
        selected_source=selected_source,
        selected_id=selected_id,
        status="PREREQUISITE_WORK_PENDING",
        prerequisite_status="RECOVERY_CONTINUES",
        reason=reason,
        event="prerequisite_recovery_continues",
    )
```

- [ ] **Step 2: Change selector decline from terminal to recovery**

Change:

```python
if not selected_source or not selected_id:
    reason = "prerequisite_selector_declined"
    prerequisite_status = "DECLINED"
```

to return `_record_recovery_continues(..., selected_source="", selected_id="", reason="prerequisite_selector_declined")` and `_finish(..., record_status="RECOVERY_CONTINUES", drain_status="CONTINUE")`.

- [ ] **Step 3: Change missing relation from terminal to recovery**

Return `RECOVERY_CONTINUES` with reason `missing_prerequisite_relation`, not `BLOCKED_UNRECOVERABLE`.

- [ ] **Step 4: Change self-selection without completed prerequisite from terminal to recovery**

Keep existing completed-prerequisite shortcut to `RETRY_READY`.

For the else case, return `RECOVERY_CONTINUES` with reason `self_prerequisite_selection`.

- [ ] **Step 5: Change selected terminal prerequisite handling**

For selected prerequisite entry with `recovery_route == "TERMINAL_BLOCKED"`:

- If `recovery_reason == "user_decision_required"` and entry has explicit user-input evidence, record original as waiting on selected prerequisite with reason `selected_prerequisite_user_input_required`, drain `CONTINUE`.
- Otherwise record original as waiting on selected prerequisite with reason `selected_prerequisite_needs_recovery`, drain `CONTINUE`.

Do not write original drain `BLOCKED`.

- [ ] **Step 6: Change invalid/missing selected status fallback**

For `selected_status != "CONTINUE"` and completion evidence missing, return `RECOVERY_CONTINUES` with reason:

```text
selected_prerequisite_status_<status>
selected_prerequisite_completion_evidence_missing
```

Do not terminal block.

- [ ] **Step 7: Run recorder tests**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "prerequisite_recovery" -q
```

Expected: prerequisite recorder tests pass after expected assertion updates.

- [ ] **Step 8: Commit**

```bash
git add workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "workflow: keep prerequisite recovery nonterminal"
```

## Task 3: Update Detector To Treat Old Prerequisite Blocks As Recoverable

**Files:**
- Modify: `workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add failing compatibility test**

```python
def test_detector_treats_legacy_prerequisite_blocked_as_recoverable(tmp_path):
    state = {
        "blocked_design_gaps": {
            "parser-syntax": {
                "reason": "implementation_blocked",
                "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                "recovery_reason": "prerequisite_gap_required",
                "recovery_status": "PREREQUISITE_BLOCKED",
                "prerequisite_recovery_status": "BLOCKED_UNRECOVERABLE",
                "prerequisite_recovery_reason": "missing_prerequisite_relation",
                ...
            }
        }
    }
    ...
    assert payload["pre_selection_route"] == "RECOVER_BLOCKED_DESIGN_GAP"
    assert payload["recovery_status"] == "PREREQUISITE_WORK_PENDING"
```

- [ ] **Step 2: Implement status normalization**

In detector, normalize before route decision:

```python
if recovery_route == "PREREQUISITE_GAP_REQUIRED" and recovery_status == "PREREQUISITE_BLOCKED":
    if _requires_user_input(entry):
        recovery_status = "USER_INPUT_REQUIRED"
    else:
        recovery_status = "PREREQUISITE_WORK_PENDING"
```

- [ ] **Step 3: Add user-input terminal test**

```python
def test_detector_blocks_only_explicit_user_input_required(tmp_path):
    ...
    entry["recovery_status"] = "USER_INPUT_REQUIRED"
    entry["recovery_reason"] = "user_decision_required"
    entry["user_input_reason"] = "External product decision required."
    ...
    assert payload["pre_selection_route"] == "BLOCKED"
    assert payload["recovery_reason"] == "user_decision_required"
```

- [ ] **Step 4: Run detector tests**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "detect or prerequisite_pending or prerequisite_recovery" -q
```

Expected: detector compatibility and stale-prerequisite tests pass.

- [ ] **Step 5: Commit**

```bash
git add workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "workflow: recover legacy prerequisite blocked state"
```

## Task 4: Tighten Terminal Route Normalization

**Files:**
- Modify: `workflows/library/scripts/select_lisp_frontend_blocked_recovery_route.py`
- Modify: `workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Define explicit user-input evidence helper**

In `select_lisp_frontend_blocked_recovery_route.py`, replace broad marker checks with a helper:

```python
def _has_explicit_user_input_evidence(bundle: dict[str, Any]) -> bool:
    summary = str(bundle.get("summary") or "").lower()
    if "user input required" not in summary and "human decision required" not in summary:
        return False
    return any(
        marker in summary
        for marker in (
            "no repo-local",
            "cannot be resolved by target design revision",
            "cannot be resolved by gap design revision",
            "cannot be represented as a design change",
            "ambiguity in intention",
            "ambiguous product intent",
            "environment issue",
            "credential",
            "access required",
            "permission",
            "local setup",
            "user intervention",
            "outside repository authority",
            "external human authority",
        )
    )
```

- [ ] **Step 2: Normalize unsupported terminal routes**

If classifier says `TERMINAL_BLOCKED/user_decision_required` without the helper passing, normalize to:

```text
GAP_DESIGN_REVISION_REQUIRED / implementation_architecture_under_scoped
```

If classifier says `TERMINAL_BLOCKED` with any non-user-input reason, normalize or reject according to current tests; prefer normalize to `GAP_DESIGN_REVISION_REQUIRED` for design-gap work.

- [ ] **Step 3: Ensure recorder preserves user-input terminal evidence**

In `record_lisp_frontend_blocked_recovery_outcome.py`, when route is `TERMINAL_BLOCKED`, set:

```text
recovery_status = USER_INPUT_REQUIRED
recovery_reason = user_decision_required
user_input_reason = summary/reason
```

Do not use ambiguous `TERMINAL_BLOCKED` as the durable `recovery_status` if the detector will route on `USER_INPUT_REQUIRED`.

- [ ] **Step 4: Run terminal route tests**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "terminal_blocker or user_decision or blocked_recovery" -q
```

Expected:

- Explicit external/human authority stays terminal.
- Repo-local design/prerequisite ambiguity normalizes to recoverable route.

- [ ] **Step 5: Commit**

```bash
git add workflows/library/scripts/select_lisp_frontend_blocked_recovery_route.py workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "workflow: reserve terminal recovery for user input"
```

## Task 5: Keep Recovery Review REVISE Nonterminal

**Files:**
- Modify: `workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py`
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add failing target-design recovery review test**

Add a focused script-level test near existing blocked-recovery recorder tests:

```python
def test_prerequisite_target_design_review_revise_keeps_gap_recoverable(tmp_path):
    state_path = tmp_path / "run_state.json"
    state_path.write_text(
        json.dumps(
            {
                "blocked_design_gaps": {
                    "stdlib-review-loop": {
                        "reason": "implementation_blocked",
                        "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                        "recovery_reason": "prerequisite_gap_required",
                        "recovery_status": "TARGET_DESIGN_REVISION_REQUIRED",
                        "progress_report_path": "artifacts/work/progress.md",
                        "architecture_path": "docs/plans/gap/implementation_architecture.md",
                        "plan_path": "docs/plans/gap/execution_plan.md",
                        "implementation_state_path": "state/impl.json",
                        "recovery_event_id": "run:stdlib-review-loop:block",
                    }
                },
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    recovery_bundle = tmp_path / "recovery.json"
    recovery_bundle.write_text(
        json.dumps(
            {
                "blocked_recovery_route": "PREREQUISITE_GAP_REQUIRED",
                "reason": "prerequisite_gap_required",
                "summary": "Target design needs a clearer prerequisite entry.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    revision_report = tmp_path / "revision.json"
    revision_report.write_text(
        json.dumps(
            {
                "design_revision_decision": "REVISED",
                "summary": "Updated target design, but review may request another pass.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    review_decision = tmp_path / "review.txt"
    review_decision.write_text("REVISE\n", encoding="utf-8")
    drain_status = tmp_path / "drain-status.txt"
    summary_path = tmp_path / "summary.json"
    summary_pointer = tmp_path / "summary-pointer.txt"

    result = subprocess.run(
        [
            sys.executable,
            "workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py",
            "--recovery-bundle-path",
            str(recovery_bundle),
            "--revision-report",
            str(revision_report),
            "--target-design-review-decision",
            str(review_decision),
            "--terminal-action",
            "continue",
            "--state-path",
            str(state_path),
            "--item-id",
            "stdlib-review-loop",
            "--source",
            "DESIGN_GAP",
            "--progress-report-path",
            "artifacts/work/progress.md",
            "--implementation-state-path",
            "state/impl.json",
            "--architecture-path",
            "docs/plans/gap/implementation_architecture.md",
            "--plan-path",
            "docs/plans/gap/execution_plan.md",
            "--drain-status-path",
            str(drain_status),
            "--summary-path",
            str(summary_path),
            "--summary-pointer-path",
            str(summary_pointer),
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    blocked = state["blocked_design_gaps"]["stdlib-review-loop"]
    assert drain_status.read_text(encoding="utf-8").strip() == "CONTINUE"
    assert blocked["recovery_route"] == "PREREQUISITE_GAP_REQUIRED"
    assert blocked["recovery_status"] == "TARGET_DESIGN_REVISION_REQUIRED"
    assert blocked["recovery_reason"] == "prerequisite_target_design_revision_revise"
    assert any(event["event"] == "blocked_recovery_review_revise" for event in state["history"])
```

Expected current failure:

- Current recorder writes drain `BLOCKED`.
- Current blocked state uses `prerequisite_target_design_revision_exhausted`.

- [ ] **Step 2: Add normal-selection guard test**

Add or extend the detector test to prove the same original gap is selected before normal work after a recovery-review `REVISE`:

```python
def test_detector_reenters_same_gap_after_target_design_recovery_review_revise(tmp_path):
    state = {
        "blocked_design_gaps": {
            "stdlib-review-loop": {
                "reason": "implementation_blocked",
                "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                "recovery_reason": "prerequisite_target_design_revision_revise",
                "recovery_status": "TARGET_DESIGN_REVISION_REQUIRED",
                "progress_report_path": "artifacts/work/progress.md",
                "implementation_state_path": "state/impl.json",
                "architecture_path": "docs/plans/gap/implementation_architecture.md",
                "plan_path": "docs/plans/gap/execution_plan.md",
                "recovery_event_id": "run:stdlib-review-loop:block",
            }
        },
        "history": [{"event": "blocked_recovery_review_revise", "item_id": "stdlib-review-loop"}],
    }
    ...
    assert payload["pre_selection_route"] == "RECOVER_BLOCKED_DESIGN_GAP"
    assert payload["design_gap_id"] == "stdlib-review-loop"
    assert payload["recovery_status"] == "TARGET_DESIGN_REVISION_REQUIRED"
```

- [ ] **Step 3: Change recorder semantics for recovery-review REVISE**

In `record_lisp_frontend_blocked_recovery_outcome.py`, replace the `REVISE` branch for target-design recovery with nonterminal recording.

For route `TARGET_DESIGN_REVISION_REQUIRED`:

```python
if decision == "REVISE":
    result = _run_update(
        args,
        "blocked",
        "target_design_revision_revise",
        recovery_status="TARGET_DESIGN_REVISION_REQUIRED",
    )
    if result == 0 and args.terminal_action == "continue":
        Path(args.drain_status_path).write_text("CONTINUE\n", encoding="utf-8")
    return result
```

For route `PREREQUISITE_GAP_REQUIRED` after target-design revision review:

```python
if decision == "REVISE":
    result = _run_update(
        args,
        "blocked",
        "prerequisite_target_design_revision_revise",
        recovery_status="TARGET_DESIGN_REVISION_REQUIRED",
    )
    if result == 0:
        Path(args.drain_status_path).write_text("CONTINUE\n", encoding="utf-8")
    return result
```

Keep `BLOCKED` terminal only when the review output or classifier evidence is explicit user-input-required under the Task 4 helper. If the current review step cannot emit `BLOCKED`, leave that branch unchanged but do not use it for ordinary `REVISE`.

- [ ] **Step 4: Preserve durable review evidence**

If the current update-state helper cannot record the recovery review report path, add one of:

- fields passed through `record_lisp_frontend_blocked_recovery_outcome.py`, or
- a history event containing `target_design_review_decision`, `target_design_review_report_path`, and `revision_report_path`.

Minimum event:

```json
{
  "event": "blocked_recovery_review_revise",
  "item_id": "stdlib-review-loop",
  "source": "DESIGN_GAP",
  "recovery_route": "PREREQUISITE_GAP_REQUIRED",
  "reason": "prerequisite_target_design_revision_revise",
  "recovery_status": "TARGET_DESIGN_REVISION_REQUIRED",
  "revision_report_path": "...",
  "review_decision": "REVISE"
}
```

Do not clear blocked state until an approved recovery leads to a successful retry or a different explicit terminal obligation.

- [ ] **Step 5: Check YAML resolver remains nonterminal**

Confirm `RecordBlockedRecoveryOutcome.artifacts.recovery_drain_status == CONTINUE` flows through `ResolveIterationDrainStatus` to iteration `CONTINUE`.

If structure tests do not already cover it, add an assertion for:

```text
RECOVER_BLOCKED_DESIGN_GAP + recovery record CONTINUE -> iteration CONTINUE
```

No new branch is needed if the resolver already maps recovery record `CONTINUE` to iteration `CONTINUE`.

- [ ] **Step 6: Run focused tests and verify pass**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "target_design_recovery_review_revise or blocked_recovery or prerequisite_recovery" -q
```

Expected: new tests pass, existing blocked/prerequisite recovery tests pass.

- [ ] **Step 7: Commit**

```bash
git add workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py workflows/examples/lisp_frontend_design_delta_drain.yaml tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "workflow: keep recovery review revise nonterminal"
```

## Task 6: Align Workflow YAML Contracts

**Files:**
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Update prerequisite recorder output enum**

Change `prerequisite_recovery_record_status.allowed` from:

```yaml
["RETRY_READY", "WAITING_ON_RECOVERABLE_PREREQUISITE", "BLOCKED"]
```

to:

```yaml
["RETRY_READY", "WAITING_ON_RECOVERABLE_PREREQUISITE", "RECOVERY_CONTINUES"]
```

or keep `BLOCKED` only if it means `USER_INPUT_REQUIRED`; if kept, rename field expectations/tests to make that explicit.

- [ ] **Step 2: Update drain-status handling**

Ensure prerequisite recorder `drain_status` only writes:

```text
CONTINUE
```

for recoverable cases.

Terminal drain `BLOCKED` should come only from detector route `BLOCKED` with user-input evidence.

- [ ] **Step 3: Update structure tests**

Update `test_design_delta_drain_checks_blocked_recovery_before_selection` to assert:

```python
assert record_status_field["allowed"] == [
    "RETRY_READY",
    "WAITING_ON_RECOVERABLE_PREREQUISITE",
    "RECOVERY_CONTINUES",
]
```

- [ ] **Step 4: Run workflow-load tests**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "design_delta_drain_checks_blocked_recovery_before_selection or workflows_load or resolve_drain_iteration_status" -q
```

- [ ] **Step 5: Run dry-run**

Run:

```bash
python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml --dry-run \
  --input steering_path=docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md \
  --input target_design_path=docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md \
  --input baseline_design_path=docs/design/workflow_lisp_frontend_specification.md \
  --input run_state_target_path=state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/run_state.json \
  --input drain_state_root=state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain \
  --input backlog_root=docs/backlog/active \
  --input architecture_index_root=docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps \
  --input artifact_work_root=artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN \
  --input artifact_checks_root=artifacts/checks/LISP-FRONTEND-AUTONOMOUS-DRAIN \
  --input artifact_review_root=artifacts/review/LISP-FRONTEND-AUTONOMOUS-DRAIN \
  --input progress_ledger_path=state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json \
  --input drain_summary_target_path=artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-summary.json
```

Expected: workflow validation successful.

- [ ] **Step 6: Commit**

```bash
git add workflows/examples/lisp_frontend_design_delta_drain.yaml tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "workflow: make prerequisite recovery statuses nonterminal"
```

## Task 7: Align Prompts With User-Input-Only Terminal Policy

**Files:**
- Modify: `workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md`
- Modify: `workflows/library/prompts/lisp_frontend_implementation_phase/implement_plan.md`
- Modify: `workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/implement_plan.md`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Update classifier prompt policy**

Add a concise rule:

```text
Use TERMINAL_BLOCKED/user_decision_required only when the evidence shows one of these terminal categories: a major unresolvable ambiguity in intention that cannot be resolved by target-design or gap-design revision; an environment, access, credential, resource, or local setup failure that requires user intervention; or true external authority outside repo-local workflow/design/code/prompt/contract repair. Selector uncertainty, missing prerequisite representation, malformed artifact evidence, and implementation scope mismatch are recoverable and should route to target/gap/prerequisite recovery.
```

- [ ] **Step 2: Update implementation prompts**

Add the same policy in implementation blocker guidance:

```text
Do not label repo-local design, dependency, prerequisite, prompt, contract, test, or implementation-scope problems as user_decision_required. Report them as recoverable blockers with evidence.
```

- [ ] **Step 3: Add prompt contract tests without asserting literal prompt text**

Do not assert exact prompt wording. Assert durable concepts are present:

```python
def test_blocked_implementation_prompts_reserve_user_decision_for_external_authority():
    prompt = Path(...).read_text()
    assert "user_decision_required" in prompt
    assert "repo-local" in prompt
    assert "prerequisite" in prompt
    assert "target-design" in prompt or "target design" in prompt
    assert "environment" in prompt or "access" in prompt or "credential" in prompt
```

This is a concept-presence test, not a literal phrase snapshot.

- [ ] **Step 4: Run prompt tests**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "prompt or user_decision or blocker" -q
```

- [ ] **Step 5: Commit**

```bash
git add workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md workflows/library/prompts/lisp_frontend_implementation_phase/implement_plan.md workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/implement_plan.md tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "workflow: clarify recoverable blocker prompt policy"
```

## Task 8: Full Verification

**Files:**
- No new files.

- [ ] **Step 1: Run focused recovery tests**

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "blocked_recovery or prerequisite_recovery or prerequisite_pending or terminal_blocker or implementation_blocker or user_decision or target_design_recovery_review_revise" -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run module collection**

```bash
pytest --collect-only tests/test_lisp_frontend_autonomous_drain_runtime.py -q
```

Expected: collection succeeds.

- [ ] **Step 3: Compile changed scripts**

```bash
python -m py_compile \
  workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py \
  workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py \
  workflows/library/scripts/select_lisp_frontend_blocked_recovery_route.py \
  workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py
```

Expected: no output, exit code 0.

- [ ] **Step 4: Run drain workflow dry-run**

Use the dry-run command from Task 6.

Expected: `[DRY RUN] Workflow validation successful`.

- [ ] **Step 5: Check diff hygiene**

```bash
git diff --check
git status --short
```

Expected:

- no whitespace errors;
- only intended files are dirty or staged.

## Acceptance Criteria

- `PREREQUISITE_GAP_REQUIRED` no longer terminally blocks by default.
- Selector decline, missing relation, self-selection, selected recoverable prerequisite block, selected terminal prerequisite block, invalid selected work status, and missing completion evidence all keep the original blocked gap recoverable unless explicit user-input evidence exists.
- Target-design recovery review `REVISE` keeps the original blocked gap recoverable, records a recovery-review-revise event or equivalent durable evidence, and returns drain `CONTINUE`.
- Target-design recovery review `REVISE` cannot select unrelated normal work before the same blocked gap re-enters recovery.
- `*_revision_exhausted` is not used for a single ordinary recovery-review `REVISE`; it is removed or reserved for a separately specified explicit user-input-required stop.
- `TERMINAL_BLOCKED/user_decision_required` is preserved only with explicit evidence of major unresolvable ambiguity in intention, an environment/access/resource issue requiring user intervention, or true external authority outside repo-local recovery.
- Completed waiting prerequisites still become `RETRY_READY` before selector re-entry.
- Workflow YAML no longer treats generic prerequisite awkwardness as terminal drain `BLOCKED`.
- Existing normal retry, gap-design revision, target-design revision, and prerequisite selection paths still pass focused tests.
- Drain dry-run validates.

## Non-Goals

- Do not build a standalone prerequisite scheduler.
- Do not add a broad prerequisite-state taxonomy.
- Do not change selector semantics beyond prompt clarification.
- Do not remove `TERMINAL_BLOCKED` enum compatibility in one step if downstream contracts still consume it.
- Do not stage unrelated workflow-generated design/doc changes.

## Execution Notes

- This repo forbids creating worktrees; execute in the current checkout.
- The current worktree is dirty from workflow-generated changes. Use `git add -p` for `tests/test_lisp_frontend_autonomous_drain_runtime.py` and avoid staging unrelated hunks.
- If a live drain is running, do not kill or restart it unless explicitly requested. These changes affect future detection/recording behavior; live runs may need resume or state normalization separately.
