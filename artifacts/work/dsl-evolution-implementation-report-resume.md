## Completed In This Pass

- Fixed the high-severity Task 11 resume defect called out by review: nested `call` resumes now enforce imported-workflow checksum stability before reusing persisted child state.
- New call-frame state snapshots now record the real imported workflow checksum instead of the `call_frame` placeholder.
- Added a regression test that mutates only the imported child workflow between a failed run and `resume_workflow()`, then verifies resume exits non-zero and does not advance nested execution.
- Tightened call-frame persistence coverage so successful `call` execution asserts a real SHA256 checksum is stored in nested state.

## Completed Plan Tasks

- Task 11: imports + `call`
  - corrective follow-up completed for the approved resume/checksum boundary
  - resumed `call` steps now reject missing or changed imported-workflow checksums instead of continuing against stale nested state

## Remaining Required Plan Tasks

- None. The consumed plan was already complete; this pass addressed the remaining correctness regression from the implementation review.

## Verification

- `pytest --collect-only tests/test_resume_command.py -q`
  - `25 tests collected in 0.08s`
- `pytest tests/test_resume_command.py -k 'call_subworkflow_smoke_resume_preserves_completed_nested_steps or imported_workflow_checksum_mismatch' -v`
  - `2 passed in 0.15s`
- `pytest tests/test_subworkflow_calls.py -k persists_call_frame_state -v`
  - `1 passed in 0.08s`
- `pytest tests/test_resume_command.py tests/test_subworkflow_calls.py tests/test_state_manager.py -v`
  - `56 passed in 0.77s`

## Residual Risks

- In-progress call-frame states created before this fix may still carry the legacy `call_frame` placeholder checksum; those nested resumes now fail closed with `call_resume_checksum_mismatch` and should be restarted instead of resumed.
- The repo worktree still contains unrelated generated/runtime artifacts (`__pycache__`, `.orchestrate/`, `artifacts/`, `logs/`, `state/`, and similar paths). This pass left unrelated files untouched and stages only the scoped runtime, test, and report updates.
