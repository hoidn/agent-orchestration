# Idempotent Drain Blocked Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not create a worktree; this repo's `AGENTS.md` forbids worktrees.

**Goal:** Make the Workflow Lisp design-gap drain recover blocked implementation items through one idempotent drain-level state machine instead of separate startup and in-work-item recovery routes.

**Architecture:** A work item that blocks records durable recovery state and exits that item. The drain loop checks blocked recovery state before normal selection on every iteration, classifies the recovery route, revises the target design or gap design when appropriate, handles prerequisite/dependency blocks explicitly, and retries the same item only after recovery succeeds. Normal backlog/design-gap selection runs only when no blocked item requires recovery.

**Tech Stack:** Orchestrator YAML workflows, v2.14 structured control flow, Python command adapters under `workflows/library/scripts/`, pytest workflow/runtime tests, dry-run validation with `python -m orchestrator`.

---

## Problem Summary

The drain currently has two recovery paths:

- `workflows/examples/lisp_frontend_design_delta_drain.yaml` has a startup-only "prior blocked" path that can classify and revise an already blocked design gap before selection.
- `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml` has an in-work-item `IMPLEMENTATION_BLOCKED` path that classifies a block, but the `GAP_DESIGN_REVISION_REQUIRED` branch records `gap_design_revision` and returns `CONTINUE` instead of routing back through the same recovery and retry path.

That split is the root bug. After a recovered gap blocks again, the workflow records recovery bookkeeping and resumes normal selection instead of treating the blocked item as the current drain obligation.

The principled invariant is:

> A blocked implementation item must become durable drain state. The next drain action must resolve that blocked item or leave it visibly blocked before selecting unrelated work.

Status contract:

- Recoverable design-gap implementation blocks record durable blocked state and return `CONTINUE` to the drain. In this case, `CONTINUE` is only the nonterminal repeat signal: the next drain iteration must check blocked recovery state before normal selection.
- Successful drain-level recovery revisions write `RUN_RECOVERED_GAP`, not bare `CONTINUE`, so the same blocked gap is retried before normal selection. `CONTINUE` after a recoverable route is valid only for the initial work-item block record, before the next recovery-before-selection iteration.
- `BLOCKED` is reserved for terminal drain blocks: unsafe recovery, terminal classifier route, missing required recovery evidence, or exhausted/failed recovery.
- Do not introduce `RECOVERY_REQUIRED` in this tranche unless every workflow output enum, route, summary, and validation surface is updated in the same change.

## File Map

- Modify `workflows/examples/lisp_frontend_design_delta_drain.yaml`
  - Own the single drain-level recovery state machine.
  - Check blocked recovery state at the start of each repeat iteration.
  - Route recovered items back into the existing `work_item` imported workflow.

- Modify `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml`
  - Stop treating implementation-block recovery as in-item recovery.
  - Record blocked implementation evidence and return `CONTINUE` for recoverable design-gap routes or `BLOCKED` for terminal routes.

- Modify `workflows/library/scripts/update_lisp_frontend_run_state.py`
  - Extend blocked-state records with recovery metadata and artifact paths.
  - Keep blocked state until drain-level recovery either succeeds or terminally blocks.

- Modify `workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py`
  - Remove the behavior where `GAP_DESIGN_REVISION_REQUIRED` clears the blocked item and writes `CONTINUE`.
  - Either replace it with a pure recorder for durable blocked state or retire it in favor of direct `update_lisp_frontend_run_state.py blocked` calls.

- Create or rename `workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py`
  - Generalize `detect_lisp_frontend_prior_blocked_design_gap.py` so it detects blocked design gaps on every drain iteration, not only at startup.
  - Keep a compatibility wrapper only if existing tests or workflows still call the prior-specific script.

- Modify `workflows/library/scripts/prepare_lisp_frontend_recovered_design_gap_work_item.py`
  - Make it consume the generalized blocked-recovery bundle.
  - Preserve the same blocked gap id, revised design paths, architecture path, plan path, and recovery event id.

- Create `workflows/library/scripts/resolve_lisp_frontend_drain_iteration_status.py`
  - Merge normal-selection, recovery-record, recovered-work-item, and pre-selection blocked outcomes into the repeat loop's `drain_status`.

- Create `workflows/library/scripts/record_lisp_frontend_recovered_retry_unavailable.py`
  - If recovery requested `RUN_RECOVERED_GAP` but no recovered work-item drain status exists, keep the item blocked and record `retry_block_reason` in run state before scalar status resolution.

- Create `workflows/library/scripts/write_lisp_frontend_relpath_value.py`
  - Materialize deterministic relpath pointer values for placeholder branches that must expose typed relpath artifacts without using scalar-only `set_scalar`.

- Modify `workflows/library/scripts/select_lisp_frontend_blocked_recovery_route.py`
  - Add an explicit dependency/prerequisite route if classification identifies a missing generic capability or prerequisite design gap rather than a fix to the current gap design.

- Create `workflows/library/scripts/materialize_lisp_frontend_recovered_design_gap_draft.py`
  - Build the draft validation bundle consumed by `validate_lisp_frontend_design_gap_architecture.py`.
  - The bundle must include `draft_status`, `design_gap_id`, `architecture_path`, `work_item_context_path`, `check_commands_path`, `plan_target_path`, and `summary`.

- Use `workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py` after design-affecting recovery
  - Validate and rematerialize the recovered gap architecture bundle before retrying after either gap-design revision or target-design revision.
  - Do not reuse an old `architecture-validation.json` as authority after design-affecting recovery.
  - Reusing prior `work_item_context_path` and `check_commands_path` is allowed only as stable materialization inputs. In this tranche the fresh validator checks path safety, existence, and non-empty check commands; it does not semantically prove that those artifacts were regenerated from the revised architecture. If semantic revalidation is required, add an explicit validator change and tests before claiming that property.

- Modify `prompts/classify_lisp_frontend_blocked_implementation_recovery.md` or the currently referenced classifier prompt file
  - Distinguish current gap design revision from target design revision, terminal block, and prerequisite/dependency work.
  - Keep state transitions and validation deterministic in the workflow. Provider prompts may classify semantic blocker routes and, for prerequisite recovery, select or decline prerequisite work from structured context.

- Modify `tests/test_lisp_frontend_autonomous_drain_runtime.py`
  - Replace tests that encode "gap design recovery continues without target edit" as a final outcome.
  - Add regressions for in-run blocked recovery, re-blocked recovered gaps, and no normal selection while a blocked item is unresolved.

## State Contract

Blocked design-gap state should use one durable shape, regardless of whether the block was present before run start or produced during the current run:

```json
{
  "reason": "implementation_blocked",
  "timestamp_utc": "2026-06-02T00:00:00Z",
  "source": "DESIGN_GAP",
  "recovery_route": "GAP_DESIGN_REVISION_REQUIRED",
  "recovery_reason": "implementation_architecture_under_scoped",
  "progress_report_path": "artifacts/work/.../progress-report.md",
  "implementation_state_path": "artifacts/work/.../implementation_state.json",
  "architecture_path": "docs/plans/.../implementation_architecture.md",
  "plan_path": "docs/plans/.../implementation_plan.md",
  "recovery_event_id": "stable-id-for-this-block",
  "recovery_status": "CLASSIFIED",
  "prerequisite_selection_bundle_path": "",
  "waiting_on_prerequisite_gap_id": "",
  "prerequisite_recovery_status": "",
  "original_blocked_gap_id": "",
  "retry_count": 0
}
```

Minimum required fields for a recoverable blocked design gap are: item id, `reason`, `recovery_route`, `recovery_reason`, `progress_report_path`, `implementation_state_path`, `architecture_path`, `plan_path` or plan-target path, and stable `recovery_event_id`. Fields not consumed by detection, revision, validation, retry preparation, or evidence reporting may stay optional, but this minimum durable basis must be present before a recoverable block may return `CONTINUE`.

Prerequisite recovery may also carry `recovery_status`,
`prerequisite_selection_bundle_path`, `waiting_on_prerequisite_gap_id`,
`prerequisite_recovery_status`, and `original_blocked_gap_id`. These fields
track selector-driven prerequisite work after target-design revision has made
the prerequisite representable in the target design. They become required before
claiming that the workflow can automatically retry the original gap after
prerequisite completion.

`reason` is the stable block category and must be `implementation_blocked` for recoverable implementation blocks. Classifier causes such as `implementation_architecture_under_scoped`, `target_design_contract_gap`, or `prerequisite_gap_required` belong in `recovery_reason`. The detector must not infer missing `recovery_route`, `recovery_reason`, or `recovery_event_id`; missing required recovery fields produce an explicit `BLOCKED` pre-selection result.

Legacy prior-blocked records that contain only `reason=implementation_blocked` are not recoverable until a deliberate normalization step populates the required recovery metadata from concrete evidence. This tranche does not add that normalizer; such records terminally block through the generic detector rather than using inferred defaults.

## Recovery Routes

Use one route vocabulary for startup blocks and in-run blocks:

- `GAP_DESIGN_REVISION_REQUIRED`
  - Revise the selected gap's implementation architecture/design.
  - Retry the same gap after revision succeeds.

- `TARGET_DESIGN_REVISION_REQUIRED`
  - Revise the target design document.
  - Retry the same gap after revision review approves.

- `PREREQUISITE_GAP_REQUIRED`
  - Do not pretend the current gap design was revised.
  - Keep the original gap visibly blocked with `recovery_route=PREREQUISITE_GAP_REQUIRED`.
  - If the prerequisite is not already represented in the target design, route through target-design revision/review first.
  - After target-design approval, set `recovery_status=PREREQUISITE_WORK_PENDING`.
  - On the next drain iteration, use `SELECT_PREREQUISITE_WORK` to call the existing selector with run-state context.
  - The selector should draft/select prerequisite work from the target design before unrelated work.
  - When the prerequisite work completes, record prerequisite satisfaction and set the original blocked gap to `RETRY_READY`.
  - `RETRY_READY` retries the original blocked gap once, without reclassifying first.
  - If the retry blocks again, classify from the new evidence normally.
  - Do not terminally block merely because prerequisite work is incomplete or unsupported by a narrow helper path. Keep recovery visible unless a recorded provider decline or concrete non-recoverable validation failure proves the workflow cannot safely proceed.

- `TERMINAL_BLOCKED`
  - Record a terminal block and stop the drain.

## Task 1: Lock The Current Failure With Tests

**Files:**
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add an in-run block regression**

Add a test that drives the drain through normal selection, work-item implementation block, `GAP_DESIGN_REVISION_REQUIRED` classification, gap design revision, and retry of the same design gap.

Expected assertions:

- `SelectNextWork` is not called for unrelated work between the block and the retry.
- The retry uses the same `design_gap_id`.
- The run state keeps the design gap blocked until the retry succeeds.
- After revision succeeds, the blocked entry is cleared only when the recovered retry completes successfully, or it remains blocked if the retry blocks again.

- [ ] **Step 2: Add a re-blocked recovered-gap regression**

Add a test for this observed sequence:

1. a prior blocked gap is recovered;
2. the recovered gap is retried;
3. implementation blocks again;
4. classifier returns `GAP_DESIGN_REVISION_REQUIRED` or `PREREQUISITE_GAP_REQUIRED`.

Expected assertions:

- the workflow does not return to normal selection immediately;
- the blocked gap remains the current recovery obligation;
- recovery route/evidence are written to run state.

- [ ] **Step 3: Replace the stale "continues without target edit" expectation**

Find `test_design_delta_gap_design_recovery_continues_without_target_edit`.

Change the expected behavior from "write `CONTINUE` after recording gap design revision" to "route the block into drain-level recovery and retry the same item, or leave it visibly blocked." If the old behavior still needs compatibility coverage, rename the test to make it explicit that it covers a deprecated script-level helper and not the workflow contract.

- [ ] **Step 4: Run the targeted tests and confirm failure**

Run:

```bash
python -m pytest \
  tests/test_lisp_frontend_autonomous_drain_runtime.py::test_design_delta_gap_design_recovery_continues_without_target_edit \
  tests/test_lisp_frontend_autonomous_drain_runtime.py::test_design_delta_prior_blocked_gap_design_recovery_before_selection \
  -q
```

Expected: FAIL because the workflow currently clears or continues instead of routing through one idempotent recovery path.

## Task 2: Make Blocked State Durable And Recovery-Aware

**Files:**
- Modify: `workflows/library/scripts/update_lisp_frontend_run_state.py`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add script-level tests for enriched blocked state**

Add tests for `update_lisp_frontend_run_state.py blocked` that cover optional recovery fields:

- `--recovery-route`
- `--recovery-reason`
- `--progress-report-path`
- `--implementation-state-path`
- `--architecture-path`
- `--plan-path`
- `--recovery-event-id`
- `--recovery-status`
- `--prerequisite-selection-bundle-path`
- `--waiting-on-prerequisite-gap-id`
- `--prerequisite-recovery-status`
- `--original-blocked-gap-id`

Expected state: `blocked_design_gaps[item_id]` keeps these fields and appends one `history` event with the same recovery/prerequisite metadata.

- [ ] **Step 2: Implement the narrow CLI extension**

Add optional arguments to the `blocked` subcommand only. Keep old callers valid.

Implementation rule:

- do not add a second blocked-state collection;
- do not clear blocked state from `gap_design_revision`;
- keep `complete` responsible for clearing blocked state after successful retry completion.
- `design_revision`, `gap_design_revision`, and retry preparation must not clear blocked state.

- [ ] **Step 3: Run the script-level tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q -k "run_state and blocked"
```

Expected: PASS for the new enriched-state tests.

## Task 3: Replace Prior-Only Detection With Iteration-Level Recovery Detection

**Files:**
- Create: `workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py`
- Optionally keep/modify: `workflows/library/scripts/detect_lisp_frontend_prior_blocked_design_gap.py`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add tests for generic blocked recovery detection**

Test cases:

- no blocked design gaps -> `pre_selection_route: SELECT_NORMAL_WORK`;
- one blocked design gap with enough artifacts -> `pre_selection_route: RECOVER_BLOCKED_DESIGN_GAP`;
- one blocked design gap with `recovery_route=PREREQUISITE_GAP_REQUIRED` and `recovery_status=PREREQUISITE_WORK_PENDING` -> `pre_selection_route: SELECT_PREREQUISITE_WORK`;
- one blocked design gap with `recovery_route=PREREQUISITE_GAP_REQUIRED` and `recovery_status=RETRY_READY` -> `pre_selection_route: RECOVER_BLOCKED_DESIGN_GAP`, with the recovery recorder bypassing provider reclassification into `RUN_RECOVERED_GAP` for the same original gap;
- blocked design gap missing required architecture/plan/progress evidence -> `pre_selection_route: BLOCKED` with reason.
- blocked design gap missing `recovery_route`, `recovery_reason`, or `recovery_event_id` -> `pre_selection_route: BLOCKED` with reason.

- [ ] **Step 2: Implement the generic detector**

Use the prior detector as the starting point, but remove "prior" semantics from the contract. It should read the durable run state and produce a bundle like:

```json
{
  "pre_selection_route": "RECOVER_BLOCKED_DESIGN_GAP",
  "design_gap_id": "GAP-...",
  "recovery_route": "GAP_DESIGN_REVISION_REQUIRED",
  "recovery_reason": "implementation_architecture_under_scoped",
  "architecture_path": "docs/plans/.../implementation_architecture.md",
  "plan_path": "docs/plans/.../implementation_plan.md",
  "progress_report_path": "artifacts/work/.../progress-report.md",
  "recovery_event_id": "..."
}
```

- [ ] **Step 3: Keep backward compatibility deliberately**

If the existing startup path still calls `detect_lisp_frontend_prior_blocked_design_gap.py`, make it a thin wrapper around the generic detector. Do not leave two implementations.

- [ ] **Step 4: Run detector tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q -k "blocked_design_gap and detect"
```

Expected: PASS.

## Task 4: Refactor The Drain Loop To Check Recovery Before Selection

**Files:**
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add YAML structure tests**

Add tests that assert:

- `DrainLispFrontendWork` calls the generic blocked-recovery detector before `SelectNextWork`;
- the repeat body has one explicit route that can choose blocked recovery before normal selection;
- normal `SelectNextWork` is not the first operation inside the repeat body;
- prior-blocked startup handling is either removed or delegates to the same generic recovery path.

- [ ] **Step 2: Introduce a unified route before normal selection**

Avoid nested control-flow brittleness. Prefer a small recovery detector/route adapter that emits a unified pre-selection route:

- `RECOVER_BLOCKED_DESIGN_GAP`
- `SELECT_PREREQUISITE_WORK`
- `SELECT_NORMAL_WORK`
- `BLOCKED`

Then one `match` routes the repeat body. The adapter must not reimplement normal selector behavior. It may detect blocked recovery state and emit `SELECT_NORMAL_WORK` when no blocked item is present; the existing imported `selector` remains the only normal-selection authority and is called from `SELECT_NORMAL_WORK` and the recovery-specific `SELECT_PREREQUISITE_WORK` branch.

If the DSL cannot express that without excessive churn, keep `SelectNextWork` as a separate step but guard it behind a preceding `match` whose non-recovery branch is the only place normal selection happens.

If the implementation uses flat steps rather than one branch boundary, every recovery-only step predicate must first guard on `pre_selection_route == RECOVER_BLOCKED_DESIGN_GAP` before reading classifier, revision, validation, or retry artifacts. Add a structure test for this guard so skipped-step artifacts cannot be referenced during normal-selection or terminal-blocked iterations.

- [ ] **Step 3: Route `RECOVER_BLOCKED_DESIGN_GAP` through existing recovery steps**

The branch should:

1. validate that blocked state already contains the required recovery fields, then reclassify from the current durable evidence. The detector treats stored `recovery_route` as required prior state, but the drain-level classifier output for the current iteration is the route authority. Missing `recovery_route`, `recovery_reason`, or `recovery_event_id` must produce `BLOCKED`, not inference/defaulting;
2. run target design revision or gap design revision as required;
3. materialize a fresh draft architecture-validation input bundle with `materialize_lisp_frontend_recovered_design_gap_draft.py`, including `draft_status`, `design_gap_id`, `architecture_path`, `work_item_context_path`, `check_commands_path`, `plan_target_path`, and `summary`;
4. validate/rematerialize the recovered gap architecture bundle with `validate_lisp_frontend_design_gap_architecture.py`;
5. prepare the same design gap work item from the fresh validation bundle;
6. call the existing imported `work_item` workflow with that prepared selection;
7. return the called item's `drain_status`.

The retry path must not reuse an old `architecture-validation.json` after gap-design or target-design recovery. If the recovered design state does not provide enough material to produce fresh context/check/plan-target paths, the recovery branch should return `BLOCKED` rather than running stale inputs. The missing-materialization reason must remain visible through the blocked item in run state; the final drain summary surfaces that blocked-state record. If run state is updated at that point, it must remain under the blocked item rather than clearing the obligation.

- [ ] **Step 4: Remove prior-only special handling as a separate path**

The startup "prior blocked" path should become one of:

- an initialization step that records legacy state in the common blocked-state shape; or
- a call to the same detector/recovery route used inside the loop.

It must not remain a second recovery implementation with separate route vocabulary or clearing behavior.

Add a denylist test that fails if `lisp_frontend_design_delta_drain.yaml` still contains a prior-specific recovery implementation such as `RoutePriorBlockedDesignGapRecovery`, `ClassifyPriorBlockedImplementationRecovery`, `RevisePriorBlockedDesignGap`, `ReviewPriorBlockedDesignRevision`, `PrepareRecoveredPriorBlockedGapWorkItem`, or `RunRecoveredPriorBlockedGapWorkItem`. A compatibility detector script may remain only as a wrapper for external callers, not as a separate workflow path.

- [ ] **Step 5: Add resolver mapping tests**

Add script-level tests for `resolve_lisp_frontend_drain_iteration_status.py`:

| `pre_selection_route` | recovery status | recovered item status | prerequisite recorder status | expected drain status |
| --- | --- | --- | --- | --- |
| `SELECT_NORMAL_WORK` | ignored | ignored | ignored | normal selection status |
| `SELECT_PREREQUISITE_WORK` | ignored | ignored | `CONTINUE` | `CONTINUE` as a nonterminal drain signal after the recorder updates prerequisite state; selected-work `CONTINUE` alone is not satisfaction |
| `SELECT_PREREQUISITE_WORK` | ignored | ignored | `BLOCKED` | `BLOCKED` with the recorder's prerequisite recovery reason visible in run state/summary |
| `RECOVER_BLOCKED_DESIGN_GAP` | `RUN_RECOVERED_GAP` | `CONTINUE` / `BLOCKED` | ignored | recovered item status |
| `RECOVER_BLOCKED_DESIGN_GAP` | `CONTINUE` | ignored | ignored | `CONTINUE` |
| `RECOVER_BLOCKED_DESIGN_GAP` | `BLOCKED` | ignored | ignored | `BLOCKED` |
| `BLOCKED` | ignored | ignored | ignored | `BLOCKED` |

Also cover missing skipped-branch status files: normal selection must not require recovery status files, recovery `CONTINUE`/`BLOCKED` must not require a recovered-work-item status file, and pre-selection `BLOCKED` must not require normal or recovery status files.

If recovery writes `RUN_RECOVERED_GAP` but validation, materialization, or preparation prevents the recovered work item from producing `drain_status.txt`, `record_lisp_frontend_recovered_retry_unavailable.py` must keep the item blocked and record `retry_block_reason=recovered_retry_status_missing` before the resolver writes scalar `BLOCKED`. The resolver remains a scalar status resolver; it must not become the owner of blocked-state mutation. Tests should prove the final drain summary exposes the blocked item and reason.

- [ ] **Step 6: Run YAML structure tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q -k "drain and recovery"
```

Expected: PASS after the workflow is refactored.

## Task 5: Make Work-Item Blocking Return To The Drain Instead Of Recovering In-Item

**Files:**
- Modify: `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml`
- Modify: `workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add tests for work-item terminal behavior**

Add assertions that `IMPLEMENTATION_BLOCKED`:

- records durable blocked state with recovery evidence;
- writes `CONTINUE` for recoverable design-gap routes so the drain repeat performs another iteration;
- writes `BLOCKED` only for terminal recovery routes or unsafe/missing recovery evidence;
- does not clear blocked state or mark gap design revision complete inside `work_item`.

- [ ] **Step 2: Change the work-item workflow**

Move recovery responsibility out of `RouteWorkItemTerminal`.

Allowed behavior inside `work_item`:

- classify the blocked implementation enough to record evidence;
- write blocked state;
- return `CONTINUE` for recoverable design-gap routes so the drain loop re-enters recovery-before-selection on the next iteration;
- return `BLOCKED` for terminal drain blocks.

Disallowed behavior:

- clearing blocked state because a gap design revision was requested;
- writing `CONTINUE` after a block without durable blocked recovery state;
- selecting unrelated work.

- [ ] **Step 3: Simplify or retire the recorder script**

If `record_lisp_frontend_blocked_recovery_outcome.py` remains, make it a recorder with no route-specific clearing. It should call `update_lisp_frontend_run_state.py blocked` with recovery metadata. For recoverable routes it may write `CONTINUE`, but only as the nonterminal drain-repeat signal described in the status contract.

Recorder status split:

- Initial work-item implementation block: record durable blocked state and write `CONTINUE` for recoverable routes so the next drain iteration enters recovery-before-selection.
- In that initial block record, write `reason=implementation_blocked` and write the classifier cause to `recovery_reason`; add a recorder-to-detector handoff regression that records through this script and immediately detects through `detect_lisp_frontend_blocked_design_gap_recovery.py`.
- Drain-level `GAP_DESIGN_REVISION_REQUIRED` after `design_revision_decision=REVISED`: record the gap-design revision and write `RUN_RECOVERED_GAP`.
- Drain-level `TARGET_DESIGN_REVISION_REQUIRED` after review `APPROVE`: record the target-design revision and write `RUN_RECOVERED_GAP`.
- Any blocked, exhausted, terminal, unsafe, missing-evidence, or invalid prerequisite-selection route: keep/update blocked state and write `BLOCKED`. `PREREQUISITE_GAP_REQUIRED` itself is recoverable and should not write terminal `BLOCKED` merely because prerequisite work is not complete yet.

- [ ] **Step 4: Run work-item tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q -k "work_item and blocked"
```

Expected: PASS.

## Task 6: Add A Prerequisite/Dependency Recovery Route

**Files:**
- Modify: classifier prompt file referenced by `ClassifyBlockedImplementationRecovery`
- Modify: `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml`
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Modify: `workflows/library/scripts/select_lisp_frontend_blocked_recovery_route.py`
- Add/modify: `workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add route to output contracts**

Extend allowed route values from:

```text
GAP_DESIGN_REVISION_REQUIRED | TARGET_DESIGN_REVISION_REQUIRED | TERMINAL_BLOCKED
```

to:

```text
GAP_DESIGN_REVISION_REQUIRED | TARGET_DESIGN_REVISION_REQUIRED | PREREQUISITE_GAP_REQUIRED | TERMINAL_BLOCKED
```

- [ ] **Step 2: Update classifier prompt narrowly**

The prompt should classify from concrete evidence:

- current gap design is under-scoped -> `GAP_DESIGN_REVISION_REQUIRED`;
- target design/spec is wrong or missing -> `TARGET_DESIGN_REVISION_REQUIRED`;
- a different prerequisite capability/gap must land first -> `PREREQUISITE_GAP_REQUIRED`;
- unsafe or outside authority -> `TERMINAL_BLOCKED`.

Do not ask the prompt to manage loop state or choose the next workflow step.

- [ ] **Step 3: Implement target-design-revision plus recovery-context prerequisite selection**

For `PREREQUISITE_GAP_REQUIRED`:

- Keep the original gap visibly blocked with `recovery_route=PREREQUISITE_GAP_REQUIRED`.
- If the prerequisite is not already represented in the target design, route through target-design revision/review first.
- After target-design approval, set `recovery_status=PREREQUISITE_WORK_PENDING`.
- On the next drain iteration, use `SELECT_PREREQUISITE_WORK` to call the existing selector with run-state context.
- The selector should draft/select prerequisite work from the target design before unrelated work.
- Validate the selector output through schema, path safety, membership, no self-dependency, artifact existence, and existing work-item contracts.
- Record the selected prerequisite bundle/id/path before claiming the original gap can be retried.
- When the prerequisite work completes, record prerequisite satisfaction and set the original blocked gap to `RETRY_READY`.
- `RETRY_READY` retries the original blocked gap once, without reclassifying first.
- If the retry blocks again, classify from the new evidence normally.
- Do not terminally block merely because prerequisite work is incomplete or unsupported by a narrow helper path. Keep recovery visible unless a recorded provider decline or concrete non-recoverable validation failure proves the workflow cannot safely proceed.

Do not add deterministic prerequisite scheduling. Deterministic code validates
state, selector output, path safety, membership, no self-dependency, and
completion evidence. The target design plus selector prompt determine which
prerequisite work is next.

This task requires `record_lisp_frontend_prerequisite_recovery_outcome.py` as a
concrete satisfaction recorder/validator. It must consume the prerequisite
selection bundle, selected work-item status, selected work run-state/history,
original blocked gap id, and drain run state. It owns the transition:

- selected prerequisite completed with valid relation -> original blocked gap
  `recovery_status=RETRY_READY`;
- recorded provider decline or concrete non-recoverable validation failure ->
  original blocked gap remains visible and the drain returns `BLOCKED` with a
  recorded reason.

The concrete workflow step is `RecordPrerequisiteRecoveryOutcome`, placed after
`WriteNormalIterationStatus` and before `ResolveIterationDrainStatus`, guarded on
`pre_selection_route == SELECT_PREREQUISITE_WORK`. Its summary bundle exposes
`record_status`, `drain_status`, and `reason`; the resolver consumes the
prerequisite recorder's status file for `SELECT_PREREQUISITE_WORK` instead of
treating raw selected-work `CONTINUE` as prerequisite satisfaction.

Until that recorder/validator exists, `SELECT_PREREQUISITE_WORK` must never turn
selector `DONE` into drain `DONE`; it may pass through only `CONTINUE` from
actually selected work as a nonterminal drain signal and must fail closed to
`BLOCKED` for selector non-selection. The scalar `CONTINUE` status is not
evidence that the prerequisite was satisfied; the recorder/validator must inspect
the selected work state/history and relation fields before marking the original
gap `RETRY_READY`.

Selector output during prerequisite recovery must include
`prerequisite_relation` on `SELECT_BACKLOG_ITEM` or `DRAFT_DESIGN_GAP` outputs.
The prompt/provider owns that semantic relation. Deterministic code validates
that the relation is present, the selected id is not the original blocked gap,
and the selected work has completed before setting `RETRY_READY`.

Prerequisite recovery is target-design revision plus recovery-context selection,
not a separate scheduler and not `GAP_DESIGN_REVISION_REQUIRED`.

- [ ] **Step 4: Add fixture coverage**

Add provider fixtures where the recovery classifier returns `PREREQUISITE_GAP_REQUIRED`.

Expected:

- current gap remains visibly blocked;
- missing prerequisite work is represented through target-design revision before prerequisite selection;
- prerequisite selection runs before unrelated normal selection;
- provider decline or invalid/self-referential/out-of-scope prerequisite selection blocks with a precise recorded reason;
- original gap retries after prerequisite completion only after the selected prerequisite and satisfaction record are durable.
- resolver coverage proves `SELECT_PREREQUISITE_WORK` uses the prerequisite
  recorder status; selected-work `CONTINUE` remains nonterminal until the
  satisfaction recorder confirms completion.

## Task 7: End-To-End Workflow Verification

**Files:**
- All modified workflow/script/test files

- [ ] **Step 1: Run collect-only if tests were renamed or added**

Run:

```bash
python -m pytest --collect-only tests/test_lisp_frontend_autonomous_drain_runtime.py -q
```

Expected: the new tests collect with stable names.

- [ ] **Step 2: Run the full drain runtime test module**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q
```

Expected: PASS.

- [ ] **Step 3: Run workflow dry-run validation**

Use the same minimal inputs already used for this workflow family. Example:

```bash
python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml \
  --dry-run \
  --input steering_path=docs/steering.md \
  --input target_design_path=docs/design/workflow_lisp_key_migration_parity_architecture.md \
  --input baseline_design_path=docs/design/workflow_lisp_frontend_specification.md \
  --input drain_state_root=state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain \
  --input run_state_target_path=state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/run_state.json \
  --input backlog_root=docs/backlog/active
```

Expected: `[DRY RUN] Workflow validation successful`.

- [ ] **Step 4: Run a safe smoke if provider fixtures can cover the route**

Run the fixture-backed runtime test that exercises:

- normal selected gap blocks;
- recovery revises the right design surface;
- prerequisite selection uses `SELECT_PREREQUISITE_WORK`;
- selector `DONE`/`BLOCKED` during prerequisite recovery does not complete the drain;
- prerequisite completion records satisfaction before original-gap retry;
- same gap retries;
- no unrelated selection happens while unresolved.

Expected: PASS and run state history shows block -> recovery -> retry -> completion/block.

- [ ] **Step 5: Check diff hygiene**

Run:

```bash
git diff --check -- \
  workflows/examples/lisp_frontend_design_delta_drain.yaml \
  workflows/library/lisp_frontend_design_delta_work_item.v214.yaml \
  workflows/library/scripts/update_lisp_frontend_run_state.py \
  workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py \
  workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py \
  workflows/library/scripts/prepare_lisp_frontend_iteration_paths.py \
  workflows/library/scripts/detect_lisp_frontend_prior_blocked_design_gap.py \
  workflows/library/scripts/materialize_lisp_frontend_recovered_design_gap_draft.py \
  workflows/library/scripts/prepare_lisp_frontend_recovered_design_gap_work_item.py \
  workflows/library/scripts/record_lisp_frontend_recovered_retry_unavailable.py \
  workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py \
  workflows/library/scripts/resolve_lisp_frontend_drain_iteration_status.py \
  workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md \
  workflows/library/lisp_frontend_design_delta_selector.v214.yaml \
  workflows/library/scripts/select_lisp_frontend_blocked_recovery_route.py \
  workflows/library/scripts/write_lisp_frontend_drain_status.py \
  workflows/library/scripts/write_lisp_frontend_relpath_value.py \
  workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md \
  tests/test_lisp_frontend_autonomous_drain_runtime.py
```

Expected: no output.

## Acceptance Criteria

- A block produced during a work-item implementation is handled through the same recovery mechanism as a block discovered at startup.
- A recovered gap that blocks again remains the active recovery obligation; normal selection does not run until it is recovered or terminally blocked.
- `GAP_DESIGN_REVISION_REQUIRED` means revise the current gap design and retry the same gap; it does not mean "record and continue."
- `TARGET_DESIGN_REVISION_REQUIRED` means revise/review the target design and retry the same gap.
- `PREREQUISITE_GAP_REQUIRED` is distinct from gap design revision and does not get hidden behind normal selection.
- A missing prerequisite is represented via target-design revision before selector-driven prerequisite selection.
- The selector chooses prerequisite work from the revised target design before unrelated work.
- Blocked-state records preserve enough evidence for the recovery agent to know what to fix.
- The drain loop has one idempotent recovery-before-selection invariant.
- Existing startup prior-blocked records that already have required recovery metadata are handled through the generic path, not through a separate implementation. Legacy records without that metadata block visibly until normalized.
- Tests cover the observed failure mode and the second-block case.
- Workflow dry-run validation succeeds.

## Implementation Notes

- Keep prompt changes short. Prompts classify; workflows route and record.
- Do not add shell glue for routing if a small typed Python adapter plus YAML `match` can keep the contract explicit.
- Avoid tests that assert literal prompt wording. Assert route values, state records, artifact paths, and workflow decisions.
- Keep compatibility wrappers temporary and name them as wrappers if they remain.
- If an implementation step discovers that the DSL cannot express the desired control shape cleanly, stop and write a small design note instead of adding another hidden special case.
