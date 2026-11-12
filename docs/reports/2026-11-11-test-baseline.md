# Test Baseline And Suite Runtime, 2026-11-11

**Status: Captured evidence, not a contract.** This page records the test
baseline taken in [roadmap Phase 0](../plans/2026-11-11-roadmap-phase-0-records-and-baseline-plan.md)
and how the suite changed the same day. Later phases gate against the failing
ids listed here. The run logs were session scratch and are not kept; the
figures below are copied from them.

## Launch recipe

A detached worktree under `.worktrees/` pinned to one commit, then, from that
worktree, started directly from an existing shell (not a new tmux session):

```bash
PYTHONPATH=$PWD PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -rfE -n 16 \
  --dist=worksteal --basetemp=/tmp/<short> -p no:cacheprovider
```

## Runs

| Run | Commit | Collected | Passed | Skipped | Failed | Wall time | Load average |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline 1 | `f1f08237` | 18,491 | 18,358 | 123 | 8 | 54 min 29 s | 40–90 |
| Baseline 2 | `f1f08237` | 18,491 | 18,356 | 123 | 10 | 83 min 0 s | 40–90 |
| After removing 3,134 low-value tests | `a32cef14` | 15,357 | 15,243 | 107 | 5 | 51 min 8 s | 40–60 |
| After the import fix, the campaign-test opt-in and the test speed-ups | `32c3e5ab` | 15,357 | 14,337 | 1,016 | 4 | 8 min 6 s | about 20 |

The last run is 84% shorter than the 51-minute run. The earlier runs were
under heavier machine load, so part of that gap is load.

## Failing ids

**Common to both baseline runs (7).** Three were stale test inputs, fixed in
`7267e3c2`. Four are an artifact of the recipe: they need a sibling
`nanoBragg` checkout beside the repository, which a worktree under
`.worktrees/` does not have. They pass from the main checkout.

- `tests/test_demo_nanobragg_entrypoint_reference_harness.py::test_build_harness_produces_shared_library`
- `tests/test_demo_nanobragg_entrypoint_reference_harness.py::test_run_reference_case_returns_tensor_payload`
- `tests/test_demo_nanobragg_reference_harness.py::test_extract_accumulation_slice_reports_scoped_anchor_metadata`
- `tests/test_demo_nanobragg_reference_harness.py::test_reference_harness_supports_compile_check_mode`

**Seen in one run only (load-sensitive).** Each passes alone and passed in the
final run.

- `tests/test_provider_execution_control.py::test_persistent_group_signal_failure_uses_bounded_leader_fallback` (baseline 1 and the 51-minute run)
- `tests/test_provider_materialization_protocol.py::test_request_worker_start_failure_closes_connection_and_cleans_sets` (baseline 2)
- `tests/test_workflow_evaluated_run_ref_kills.py::test_kill_at_parent_settlement_gap_recovers[memo-before-finalize-evaluated]` (baseline 2; its marker wait has a 15-second deadline in `tests/workflow_evaluated_run_ref_helpers.py`)
- `tests/experiments/test_native_session_cli_probe.py::test_short_overlap_timeout_bounds_both_concurrent_model_calls[delayed-marker-hang]` (baseline 2; the module has since been removed)
- `tests/test_workflow_evaluated_resume_retry.py::test_pending_provider_required_dependency_c6_refuses_before_executor_then_retries[missing]` (failed once in a sampled run on `main` at load average about 20; passed three times alone)
- Nine kill-and-deadline tests in `tests/test_provider_interactive_terminal_recovery.py` failed once when run alone at load average about 60; they passed in every full run.

**Gate for later phases:** no test outside the four worktree-artifact ids
fails; a failure among the load-sensitive ids is rerun alone before it counts.

## What changed the runtime

Measured as the sum of per-test durations over 0.2 s across all workers:

| Change | Worker time |
| --- | --- |
| Before (51-minute run) | 41,097 s |
| Closed structural-search campaign tests made opt-in (`ORCHESTRATE_CAMPAIGN_TESTS=1`; 908 tests skipped by default) | −17,392 s |
| Lazy `jsonschema` import (a CLI start 3.45 s to 0.25 s) and test-side speed-ups in 14 modules | 23,705 s to about 6,800 s |

Removing the 3,134 low-value tests changed wall time little (54 to 51
minutes): they were mostly fast.

## Provider-call check

The final run had stub `claude` and `codex` executables first on `PATH` that
log and refuse every call (`experiments/thread_m/no_provider/`). The log
stayed empty: no test in the suite starts a real provider CLI.
