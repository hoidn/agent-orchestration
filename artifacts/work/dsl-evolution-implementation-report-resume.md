## Completed In This Pass

- Fixed the high-severity custom state-root resume defect from review.
  - added `--state-dir` support to `orchestrate resume`
  - taught `resume_workflow()` to resolve existing runs under an overridden runs root instead of hard-coding `.orchestrate/runs`
  - carried the same override into the `--force-restart` branch so resumed runs restarted from custom roots stay in the same runs tree
- Closed the verification hole that let the regression survive the previous sweep.
  - added parser coverage for `resume --state-dir`
  - added a resume regression test that reopens a run stored under a custom runs root
  - refreshed two observability resume fixtures to use `StateManager.SCHEMA_VERSION` so the module exercises the intended resume behavior instead of failing on stale schema metadata

## Completed Plan Tasks

- No new execution-plan tranche was newly completed in this pass.
- All approved plan tasks from Task 1 through Task 16 remain implemented from the prior pass; this pass addressed post-implementation review feedback against the Task 16 resume/recovery boundary.

## Remaining Required Plan Tasks

- None.

## Verification

- `pytest --collect-only tests/test_cli_observability_config.py -q`
  - collected `8` tests
- `pytest --collect-only tests/test_resume_command.py -q`
  - collected `23` tests
- `pytest tests/test_cli_observability_config.py -k state_dir_on_run_and_resume -v`
  - `1 passed`
- `pytest tests/test_resume_command.py -k custom_state_dir_override -v`
  - `1 passed`
- `pytest tests/test_resume_command.py tests/test_cli_observability_config.py -v`
  - `31 passed`
- `pytest tests/test_cli_safety.py -k state_dir_override -v`
  - `1 passed`
- `pytest tests/test_state_manager.py -k custom_state_dir -v`
  - `1 passed`
- Custom-root CLI smoke via the public entrypoint:
  - `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run resume_demo.yaml --state-dir <custom-runs-root>` returned `1` after the intended gate failure and created run `20260308T040712Z-wpbxz5`
  - `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator resume 20260308T040712Z-wpbxz5 --state-dir <custom-runs-root>` returned `0`
  - final run `state.json` status was `completed`
  - workspace `state/history.log` was `["first", "blocked", "resumed"]`

## Residual Risks

- The normal custom-root resume path is now covered directly. The mirrored `--force-restart --state-dir` branch does not yet have its own dedicated CLI regression test, although the same override is now threaded through that code path.
