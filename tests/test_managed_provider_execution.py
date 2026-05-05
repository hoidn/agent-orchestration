from pathlib import Path
from unittest.mock import patch
import json
import sys
import yaml

from orchestrator.managed_jobs.audit import append_event
from orchestrator.loader import WorkflowLoader
from orchestrator.providers.executor import ProviderExecutionResult, ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from tests.workflow_bundle_helpers import bundle_context_dict


def _write_workflow(tmp_path: Path, *, provider_code: str = "0") -> Path:
    review_path = (tmp_path / "review.txt").as_posix()
    fix_path = (tmp_path / "fix.txt").as_posix()
    payload = {
        "version": "2.13",
        "name": "managed-provider-execution",
        "providers": {
            "impl": {
                "command": [sys.executable, "-c", provider_code],
                "input_mode": "stdin",
            }
        },
        "steps": [
            {
                "name": "Execute",
                "id": "execute",
                "provider": "impl",
                "managed_jobs": {
                    "policy": "workflows/managed_jobs/policy.yaml",
                    "watch_roots": ["scripts/training"],
                    "backend": "auto",
                    "poll_budget_sec": 1,
                    "on": {
                        "complete": "Review",
                        "failed": "Fix",
                        "invalid": "Fix",
                        "outstanding": "fail_resumable",
                    },
                },
            },
            {
                "name": "Fix",
                "id": "fix",
                "command": [sys.executable, "-c", f"open({fix_path!r}, 'w').write('fix')"],
            },
            {
                "name": "Review",
                "id": "review",
                "command": [sys.executable, "-c", f"open({review_path!r}, 'w').write('review')"],
            },
        ],
    }
    path = tmp_path / "workflow.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _executor(
    tmp_path: Path,
    workflow_path: Path,
    *,
    max_retries: int = 0,
    initialize: bool = True,
) -> WorkflowExecutor:
    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    state_manager = StateManager(tmp_path, run_id="managed-run")
    if initialize:
        state_manager.initialize(str(workflow_path), bundle_context_dict(bundle))
    return WorkflowExecutor(bundle, tmp_path, state_manager, max_retries=max_retries, retry_delay_ms=0)


def test_managed_provider_wraps_invocation_recovers_and_routes_complete(tmp_path: Path) -> None:
    executor = _executor(tmp_path, _write_workflow(tmp_path))
    seen = []

    def _execute(_self, invocation, **_kwargs):
        seen.append(invocation)
        return ProviderExecutionResult(exit_code=0, stdout=b"ok", stderr=b"", duration_ms=1)

    with patch.object(ProviderExecutor, "execute", _execute):
        state = executor.execute()

    assert seen
    assert seen[0].terminate_process_tree is True
    assert "orchestrator.managed_jobs.provider_guard" in seen[0].command
    assert state["steps"]["Execute"]["managed_jobs"]["managed_job_outcome"] == "COMPLETE"
    assert (tmp_path / "review.txt").read_text(encoding="utf-8") == "review"
    assert not (tmp_path / "fix.txt").exists()


def test_managed_provider_disables_global_provider_retries(tmp_path: Path) -> None:
    executor = _executor(tmp_path, _write_workflow(tmp_path), max_retries=3)
    calls = {"count": 0}

    def _execute(_self, invocation, **_kwargs):
        calls["count"] += 1
        return ProviderExecutionResult(exit_code=1, stdout=b"failed", stderr=b"", duration_ms=1)

    with patch.object(ProviderExecutor, "execute", _execute):
        executor.execute()

    assert calls["count"] == 1


def test_managed_provider_resume_reenters_recovery_without_relaunch(tmp_path: Path) -> None:
    workflow_path = _write_workflow(tmp_path)
    executor = _executor(tmp_path, workflow_path)
    job_state_path = tmp_path / "job_state.json"

    def _execute_first(_self, invocation, **_kwargs):
        managed = invocation.metadata["managed_jobs"]
        job_state_path.write_text(
            json.dumps(
                {
                    "status": "RUNNING",
                    "job_identity_hash": "abc123",
                    "state_root": "state/job",
                    "snapshot": {"manifest": "state/job/snapshot/manifest.json"},
                    "verify_files": ["artifacts/metrics.json"],
                }
            ),
            encoding="utf-8",
        )
        append_event(
            Path(managed["audit_path"]),
            {
                "event": "job_submitted",
                "job_id": "job-1",
                "job_state_path": str(job_state_path),
            },
        )
        return ProviderExecutionResult(exit_code=0, stdout=b"submitted", stderr=b"", duration_ms=1)

    with patch.object(ProviderExecutor, "execute", _execute_first):
        first_state = executor.execute()

    assert first_state["status"] == "failed"
    assert first_state["current_step"]["managed_jobs"]["phase"] == "recovery"
    assert first_state["steps"]["Execute"]["managed_jobs"]["managed_job_outcome"] == "OUTSTANDING"

    job_state_path.write_text(
        json.dumps(
            {
                "status": "COMPLETED",
                "job_identity_hash": "abc123",
                "state_root": "state/job",
                "snapshot": {"manifest": "state/job/snapshot/manifest.json"},
                "verify_files": ["artifacts/metrics.json"],
            }
        ),
        encoding="utf-8",
    )
    resumed_executor = _executor(tmp_path, workflow_path, initialize=False)

    def _execute_resume(_self, invocation, **_kwargs):
        raise AssertionError("resume should recover managed jobs without relaunching provider")

    with patch.object(ProviderExecutor, "execute", _execute_resume):
        resumed_state = resumed_executor.execute(resume=True)

    assert resumed_state["steps"]["Execute"]["managed_jobs"]["managed_job_outcome"] == "COMPLETE"
    assert (tmp_path / "review.txt").read_text(encoding="utf-8") == "review"
