## Completed In This Pass

- Fixed the reviewed cycle-guard correctness defect: `cycle_guard_exceeded` now stops routed step execution before any step-level `on.failure.goto` can continue the loop.
- Tightened the reusable-`call` write-root boundary:
  - loader validation now rejects invariant managed write-root bindings for looped `call` sites inside `repeat_until`
  - runtime now rejects repeated or aliased managed write roots when loop-local refs resolve to the same path across `for_each` / repeated call frames
- Updated the shipped repeat-until `call` fixtures/examples to bind per-iteration managed write roots plus an explicit `iteration` input, while keeping shared history logging outside the managed-output contract surface.
- Aligned the normative/docs/example surface with the corrected cycle-guard contract: guard trips are terminal for routed step execution.

## Completed Plan Tasks

- Task 5: cycle guards
  - corrective follow-up completed so raw-graph cycle guards cannot be bypassed by recovery routing
  - example/spec/test coverage now models guard trips as terminal
- Task 10 / Task 11 reusable-call boundary
  - completed the approved missing write-root collision enforcement for repeated looped `call` invocations
  - added loader/runtime coverage for looped `call` sites that reuse managed relpath bindings

## Remaining Required Plan Tasks

- None. The consumed plan was already otherwise complete; this pass addressed the remaining review findings and the still-missing Task 10/11 repeated-call write-root boundary.

## Verification

- `pytest --collect-only tests/test_control_flow_foundations.py tests/test_subworkflow_calls.py -k 'guard_stop_is_terminal or invariant_write_root_binding or reused_write_root_from_loop_local_ref' -q`
  - `2/19 tests collected (17 deselected) in 0.06s`
- `pytest tests/test_control_flow_foundations.py tests/test_subworkflow_calls.py -v`
  - `19 passed in 0.29s`
- `pytest tests/test_structured_control_flow.py -k 'repeat_until and call' -v`
  - `2 passed, 15 deselected in 0.15s`
- `pytest tests/test_resume_command.py -k 'test_repeat_until_resume_preserves_nested_call_frames_and_lowered_match_progress or control_flow_counters' -v`
  - `2 passed, 23 deselected in 0.16s`
- `pytest tests/test_workflow_examples_v0.py -k 'repeat_until_demo or cycle_guard_demo or call_subworkflow_demo' -v`
  - `3 passed, 17 deselected in 0.18s`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/repeat_until_demo.yaml --state-dir /tmp/dsl-evolution-repeat-until-smoke`
  - exit `0`; `/tmp/dsl-evolution-repeat-until-smoke/20260308T090201Z-9wvnqe/state.json` recorded `status: completed`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/call_subworkflow_demo.yaml --dry-run`
  - `[DRY RUN] Workflow validation successful`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/cycle_guard_demo.yaml --dry-run`
  - `[DRY RUN] Workflow validation successful`

## Residual Risks

- Loop-local managed write-root refs that are not statically provable as invariant (for example `self.*` / `parent.*` patterns) are now enforced at runtime rather than load time; they still fail closed when a repeated invocation resolves to the same path.
- Existing looped reusable-call workflows that intentionally reused one managed write root across iterations now fail validation or runtime contract checks and must be rewritten to bind unique per-invocation managed roots.
- The repo worktree still contains unrelated generated/runtime artifacts (`__pycache__`, `.orchestrate/`, `artifacts/`, `logs/`, `state/`, and similar paths). This pass left unrelated files untouched and stages only the scoped runtime, docs, workflow, test, and report updates.
