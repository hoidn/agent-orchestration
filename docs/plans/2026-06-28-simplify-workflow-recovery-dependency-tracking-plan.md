# Simplify Workflow Recovery Dependency Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees.

**Goal:** Reduce recovery dependency tracking from a selector-facing planning graph to a small runtime-owned recovery pointer.

**Architecture:** Keep rich recovery-edge parsing and validation inside scripts for backward compatibility with existing run state. Expose only the actionable recovery pointer to selector/provider steps: what is blocked, what it is waiting on, and whether retry is ready. Do not add new workflow statuses or target-specific rules.

**Tech Stack:** Agent-orchestration DSL v2.14 YAML, Python recovery scripts under `workflows/library/scripts/`, selector/classifier prompts, and pytest.

---

## Scope

This is a simplification pass for the recovery dependency surface, not a new recovery model.

In scope:

- Keep existing `recovery_dependency_edge` state readable.
- Depend on the anti-churn recorder validation from commit `0fb48e9` or equivalent behavior.
- Add a compact recovery-pointer projection for workflow/provider handoff.
- Stop exposing relation/reason/downstream edge metadata to selector prompts.
- Update workflow output-bundle contracts so compact pointer fields are materialized as artifacts.
- Preserve deterministic validation for cycles, stale completed prerequisites, and retry readiness.
- Add tests that prove selector-facing output is compact while legacy edge input still works.

Out of scope:

- Removing `recovery_dependency_edge` from historical run state.
- Rewriting the drain selector or target-design selection policy.
- Adding a general dependency graph planner.
- Adding new statuses such as `RECONCILE_STATE`.
- Changing `.orc` migration semantics.

## File Map

- Modify `workflows/library/scripts/workflow_recovery_dependencies.py`
  - Add a compact pointer projection helper over existing normalized edges/decisions.
- Modify `workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py`
  - Replace selector-facing edge fields with compact pointer fields.
- Modify `workflows/examples/lisp_frontend_design_delta_drain.yaml`
  - Update `DetectBlockedDesignGapRecovery` output-bundle fields to expose `waiting_on_work_id`, `waiting_on_work_source`, and `recovery_pointer_status`.
  - Update `ClassifyBlockedImplementationRecovery` output-bundle fields to prefer compact waiting-on fields instead of relation/reason graph fields.
- Modify `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml`
  - Apply the same classifier output-bundle compact pointer contract used by the parent workflow.
- Modify `workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md`
  - Remove wording that encourages the selector to reason from dependency edges.
  - Tell the selector to use the provided waiting-on/retry fact only.
- Modify `tests/test_workflow_recovery_dependency_graph.py`
  - Add focused unit tests for compact pointer projection.
- Modify `tests/test_lisp_frontend_autonomous_drain_runtime.py`
  - Update detector/pre-selection and workflow-contract assertions to the compact pointer surface.
  - Preserve legacy edge input tests.
- Validate `workflows/examples/lisp_frontend_design_delta_drain.yaml`
  - Dry-run after the required output-contract edits.

## Design Rule

The only selector-facing recovery fact should be:

```json
{
  "blocked_work_id": "A",
  "blocked_work_source": "DESIGN_GAP",
  "waiting_on_work_id": "B",
  "waiting_on_work_source": "DESIGN_GAP",
  "retry_target_id": "A",
  "retry_target_source": "DESIGN_GAP",
  "recovery_pointer_status": "WAITING"
}
```

Allowed `recovery_pointer_status` values:

- `WAITING`
- `READY_TO_RETRY`
- `INVALID`

Do not expose `relation`, `reason_code`, `downstream_work`, or edge-evidence metadata to selector/provider prompts. Those stay internal to validation and run-state compatibility.

Provider-produced prerequisite recovery should also use the compact pointer:

```json
{
  "blocked_recovery_route": "PREREQUISITE_GAP_REQUIRED",
  "reason": "prerequisite_gap_required",
  "waiting_on_work_id": "B",
  "waiting_on_work_source": "DESIGN_GAP"
}
```

The recorder may still accept historical `recovery_dependency_edge`,
`dependency_relation`, and `dependency_reason_code` input, but new prompts and
output contracts should not ask providers or selectors to reason over those
fields.

## Preconditions

- [ ] **Step 1: Inspect dirty state**

Run:

```bash
git status --short
```

Expected:

- Identify unrelated generated workflow files.
- Do not stage unrelated active workflow outputs or generated gap drafts.

- [ ] **Step 2: Re-read relevant contracts**

Run:

```bash
sed -n '1,220p' docs/workflow_drafting_guide.md
sed -n '1,260p' workflows/library/scripts/workflow_recovery_dependencies.py
sed -n '120,285p' workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py
```

Expected:

- Confirm prompts propose local judgment.
- Confirm scripts own deterministic routing and durable state.
- Confirm existing rich edges remain script-owned compatibility input.
- Confirm commit `0fb48e9` or equivalent recorder validation is present; if not, implement that first.

## Task 1: Add Compact Recovery Pointer Projection

**Files:**

- Modify: `workflows/library/scripts/workflow_recovery_dependencies.py`
- Test: `tests/test_workflow_recovery_dependency_graph.py`

- [ ] **Step 1: Write failing pointer tests**

Add tests similar to:

```python
def test_recovery_pointer_for_waiting_prerequisite():
    edge = normalize_edge({
        "blocked_work": {"source": "DESIGN_GAP", "id": "parser"},
        "blocker_work": {"source": "DESIGN_GAP", "id": "context"},
        "relation": "requires_completion",
        "reason_code": "missing_context",
        "ready_when": {"kind": "completed", "source": "DESIGN_GAP", "id": "context"},
        "retry_target": {"source": "DESIGN_GAP", "id": "parser"},
    })
    decision = evaluate_edge(edge, {"completed_design_gaps": [], "blocked_design_gaps": {}})

    assert recovery_pointer_to_json(decision) == {
        "blocked_work_id": "parser",
        "blocked_work_source": "DESIGN_GAP",
        "waiting_on_work_id": "context",
        "waiting_on_work_source": "DESIGN_GAP",
        "retry_target_id": "parser",
        "retry_target_source": "DESIGN_GAP",
        "recovery_pointer_status": "WAITING",
    }
```

Add equivalent tests for `RETRY_TARGET -> READY_TO_RETRY` and `INVALID_EDGE -> INVALID`.

- [ ] **Step 2: Run failing tests**

Run:

```bash
python -m pytest tests/test_workflow_recovery_dependency_graph.py -k recovery_pointer -q
```

Expected:

- Tests collect and fail because `recovery_pointer_to_json` does not exist.

- [ ] **Step 3: Implement the projection helper**

In `workflow_recovery_dependencies.py`, add:

```python
def recovery_pointer_to_json(decision: RecoveryDependencyDecision) -> dict[str, str]:
    edge = decision.edge
    blocked = edge.blocked_work
    blocker = edge.blocker_work
    retry = edge.retry_target
    if decision.route == "RETRY_TARGET":
        status = "READY_TO_RETRY"
    elif decision.route == "INVALID_EDGE":
        status = "INVALID"
    else:
        status = "WAITING"
    return {
        "blocked_work_id": blocked.id if blocked is not None else "",
        "blocked_work_source": blocked.source if blocked is not None else "",
        "waiting_on_work_id": blocker.id if blocker is not None else "",
        "waiting_on_work_source": blocker.source if blocker is not None else "",
        "retry_target_id": retry.id if retry is not None else "",
        "retry_target_source": retry.source if retry is not None else "",
        "recovery_pointer_status": status,
    }
```

Do not remove `edge_to_json`, `normalize_edge`, or `evaluate_edge`.

- [ ] **Step 4: Run pointer tests**

Run:

```bash
python -m pytest tests/test_workflow_recovery_dependency_graph.py -k recovery_pointer -q
```

Expected:

- Pointer tests pass.

## Task 2: Stop Sending Edge Internals To Selector Handoff

**Files:**

- Modify: `workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py`
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Write/update failing detector tests**

Update the tests that currently assert selector-facing fields such as:

```python
assert payload["blocker_work_id"] == "generic-context-capability"
assert payload["dependency_relation"] == "requires_completion"
```

Expected new assertions:

```python
assert payload["pre_selection_route"] == "SELECT_PREREQUISITE_WORK"
assert payload["blocked_work_id"] == "parser-syntax"
assert payload["waiting_on_work_id"] == "generic-context-capability"
assert payload["waiting_on_work_source"] == "DESIGN_GAP"
assert payload["retry_target_id"] == "parser-syntax"
assert payload["recovery_pointer_status"] == "WAITING"
```

Keep tests that inspect durable run-state `recovery_dependency_edge`; that remains valid internal state.
Add a retry-ready detector assertion:

```python
assert payload["pre_selection_route"] == "RECOVER_BLOCKED_DESIGN_GAP"
assert payload["design_gap_id"] == "parser-syntax"
assert payload["recovery_status"] == "RETRY_READY"
assert payload["recovery_pointer_status"] == "READY_TO_RETRY"
```

- [ ] **Step 2: Run failing detector tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "prerequisite_recovery_records_compact_dependency_pointer or prerequisite_block_recovery_stays_nonterminal_until_target_revision" -q
```

Expected:

- Tests fail until detector output is compact.

- [ ] **Step 3: Replace `_edge_fields` with pointer projection**

In `detect_lisp_frontend_blocked_design_gap_recovery.py`:

- import `recovery_pointer_to_json`;
- change `_edge_fields(...)` into `_pointer_fields(decision)`;
- add output fields:
  - `waiting_on_work_id`;
  - `waiting_on_work_source`;
  - `recovery_pointer_status`;
- keep `dependency_relation` and `dependency_reason_code` present but empty only if existing output contracts/tests still require the keys;
- do not include `downstream_work` or edge evidence in the detector output.

The `SELECT_PREREQUISITE_WORK` branch should do:

```python
decision = evaluate_edge(edge, state)
payload.update(_pointer_fields(decision))
```

The `RETRY_TARGET` branch should not route through the selector. It should keep
the existing recovery path by returning `pre_selection_route:
RECOVER_BLOCKED_DESIGN_GAP` for the original blocked work, set
`recovery_status: RETRY_READY`, and include compact pointer fields only as
explanatory metadata.

Do not make the selector recompute edge state.

- [ ] **Step 4: Update detector output-bundle contract**

In `workflows/examples/lisp_frontend_design_delta_drain.yaml`, update
`DetectBlockedDesignGapRecovery.output_bundle.fields`:

- add fields:
  - `waiting_on_work_id` from `/waiting_on_work_id`;
  - `waiting_on_work_source` from `/waiting_on_work_source`;
  - `recovery_pointer_status` from `/recovery_pointer_status`, enum
    `["", "WAITING", "READY_TO_RETRY", "INVALID"]` if empty is needed for
    non-prerequisite routes;
- remove `dependency_relation` and `dependency_reason_code` from the
  output-bundle fields if no downstream typed ref still requires them;
- otherwise keep those old fields as `required: false` and require the detector
  to emit empty strings for them.

This YAML edit is required; otherwise the compact pointer will not be exposed as
typed artifacts for routing/tests.

- [ ] **Step 5: Run detector tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "blocked_recovery or prerequisite_recovery" -q
```

Expected:

- Existing recovery behavior passes with compact handoff fields.

## Task 3: Simplify Classifier Output Contract

**Files:**

- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Modify: `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml`
- Modify if needed: `workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Write/update classifier contract tests**

Add or update tests that inspect `ClassifyBlockedImplementationRecovery` output
contracts. Expected contract:

- includes optional `waiting_on_work_id`;
- includes optional `waiting_on_work_source`;
- does not ask the provider for `dependency_relation` or
  `dependency_reason_code`;
- still accepts historical rich `recovery_dependency_edge` fixtures through the
  recorder tests.

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "blocked_implementation_recovery_prompt_keeps_roles_clear or design_delta_work_item_records_blocked_implementation_for_drain_recovery" -q
```

Expected:

- New/updated assertions fail before YAML/script changes.

- [ ] **Step 2: Update classifier output-bundle fields**

In both workflow YAML files, update `ClassifyBlockedImplementationRecovery` so
new provider prompts see only compact prerequisite fields:

```yaml
- name: waiting_on_work_id
  json_pointer: /waiting_on_work_id
  type: string
  required: false
- name: waiting_on_work_source
  json_pointer: /waiting_on_work_source
  type: string
  required: false
```

Remove `dependency_relation` and `dependency_reason_code` from the provider
output contract unless a runtime validator still requires the keys. If the keys
must remain temporarily, mark them compatibility-only in tests and ensure prompt
instructions do not name them.

- [ ] **Step 3: Teach the recorder compact input**

In `record_lisp_frontend_blocked_recovery_outcome.py`, extend
`_raw_edge_from_bundle(...)` so a compact pointer is normalized into the same
internal edge:

```python
waiting_id = str(bundle.get("waiting_on_work_id") or "").strip()
waiting_source = str(bundle.get("waiting_on_work_source") or "DESIGN_GAP").strip()
if waiting_id:
    return {
        "blocked_work": {"source": args.source, "id": args.item_id},
        "blocker_work": {"source": waiting_source, "id": waiting_id},
        "relation": "requires_completion",
        "reason_code": str(bundle.get("reason") or "prerequisite_required"),
        "ready_when": {"kind": "completed", "source": waiting_source, "id": waiting_id},
        "retry_target": {"source": args.source, "id": args.item_id},
        "downstream_work": [],
        "evidence": {"created_by": "blocked_recovery_classifier"},
    }
```

Keep historical rich `recovery_dependency_edge` and generic edge fields accepted
for compatibility.

- [ ] **Step 4: Run classifier/recorder tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "blocked_recovery_recorder or prerequisite_recovery_records_compact_dependency_pointer or blocked_implementation_recovery_prompt_keeps_roles_clear" -q
```

Expected:

- Compact classifier output is accepted.
- Historical rich edge input still works.

## Task 4: Simplify Selector Prompt Wording

**Files:**

- Modify: `workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Edit dependency wording**

Replace wording like:

```text
If pre-selection metadata provides a dependency edge, select the blocker work
named by that edge...
```

with:

```text
If pre-selection metadata says a blocked item is waiting on another item, use
that as a routing fact only. Do not infer a broader dependency graph from it.
When metadata says retry is ready, select the original blocked item for retry.
```

Keep the prompt generic. Do not mention Design Delta, WCC, YAML, or any current target design.

- [ ] **Step 2: Run prompt-role tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "selector_prompt or design_delta_selector_prompt_defines_target_and_baseline or blocked_implementation_recovery_prompt_keeps_roles_clear" -q
```

Expected:

- Prompt tests pass without literal wording assertions.

## Task 5: Preserve Recorder Validation And Compatibility

**Files:**

- Modify if needed: `workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Confirm legacy rich edge input still works**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "blocked_recovery_recorder or prerequisite_recovery_rejects_self_completion_edge or prerequisite_recovery_records_compact_dependency_pointer" -q
```

Expected:

- Rich `recovery_dependency_edge` input still validates.
- Completed prerequisite still records retry-ready.
- Invalid self-prerequisite still fails closed.

- [ ] **Step 2: Patch only if compatibility regressed**

If tests fail because old edge input is no longer accepted, restore compatibility in the recorder by parsing rich edge JSON internally and projecting only at detector output time.

Do not weaken validation.

## Task 6: Workflow Validation

**Files:**

- Validate: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Validate: `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml`

- [ ] **Step 1: Parse YAML**

Run:

```bash
python - <<'PY'
import yaml
from pathlib import Path
for p in [
    'workflows/examples/lisp_frontend_design_delta_drain.yaml',
    'workflows/library/lisp_frontend_design_delta_work_item.v214.yaml',
]:
    yaml.safe_load(Path(p).read_text())
    print('ok', p)
PY
```

Expected:

- Both files parse.

- [ ] **Step 2: Dry-run the active drain**

Run:

```bash
python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml \
  --dry-run \
  --input steering_path=docs/steering.md \
  --input target_design_path=docs/design/workflow_lisp_runtime_native_drain_authoring.md \
  --input baseline_design_path=docs/design/workflow_lisp_frontend_specification.md \
  --input post_wcc_inventory_path=docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/post_wcc_current_state_inventory.json \
  --input command_adapter_contract_path=docs/design/workflow_command_adapter_contract.md \
  --input backlog_root=docs/backlog/active \
  --input progress_ledger_path=state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/progress_ledger.json \
  --input drain_state_root=state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain \
  --input run_state_target_path=state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain/run_state.json \
  --input drain_summary_target_path=artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain-summary.json \
  --input artifact_work_root=artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN \
  --input artifact_checks_root=artifacts/checks/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN \
  --input artifact_review_root=artifacts/review/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN \
  --input architecture_index_root=docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps \
  --input design_gap_draft_provider=codex \
  --input design_gap_draft_model=gpt-5.5 \
  --input design_gap_draft_effort=high \
  --input implementation_execute_provider=codex \
  --input implementation_review_provider=codex \
  --input done_review_provider=codex
```

Expected:

- Workflow validation successful.
- Existing unrelated lint warnings are acceptable only if unchanged.

## Task 7: Commit

- [ ] **Step 1: Review scoped diff**

Run:

```bash
git status --short
git diff --check
git diff -- workflows/library/scripts/workflow_recovery_dependencies.py \
  workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py \
  workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py \
  workflows/examples/lisp_frontend_design_delta_drain.yaml \
  workflows/library/lisp_frontend_design_delta_work_item.v214.yaml \
  workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md \
  tests/test_workflow_recovery_dependency_graph.py \
  tests/test_lisp_frontend_autonomous_drain_runtime.py
```

Expected:

- No unrelated generated workflow artifacts staged.
- No target-specific prompt examples.
- Rich edge state remains internal/compatibility only.

- [ ] **Step 2: Commit**

Run:

```bash
git add workflows/library/scripts/workflow_recovery_dependencies.py \
  workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py \
  workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py \
  workflows/examples/lisp_frontend_design_delta_drain.yaml \
  workflows/library/lisp_frontend_design_delta_work_item.v214.yaml \
  workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md \
  tests/test_workflow_recovery_dependency_graph.py \
  tests/test_lisp_frontend_autonomous_drain_runtime.py \
  docs/plans/2026-06-28-simplify-workflow-recovery-dependency-tracking-plan.md
git commit -m "Simplify workflow recovery dependency handoff"
```

Omit `record_lisp_frontend_blocked_recovery_outcome.py` from `git add` if it did not need compatibility changes.

## Success Criteria

- Selector-facing recovery metadata is a compact pointer, not a dependency graph.
- Provider prompts no longer invite agents to reason from relation/reason/downstream edge metadata.
- Old rich edge fields may remain readable by scripts and historical state, but are not named in prompt instructions or new provider-facing output contracts.
- Existing rich edge state still validates for compatibility.
- Completed prerequisites still retry the original blocked work.
- Invalid/cyclic prerequisites still fail closed.
- No new statuses or target-specific rules are introduced.
- Active drain dry-run still validates.
