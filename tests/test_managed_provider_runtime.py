import sys
import json
from pathlib import Path

from orchestrator.managed_jobs.audit import append_event
from orchestrator.managed_jobs.recovery import recover_managed_jobs
from orchestrator.managed_jobs.runtime import ManagedProviderRuntime
from orchestrator.providers import InputMode
from orchestrator.providers.types import ProviderInvocation
from orchestrator.workflow.executable_ir import ManagedJobsConfig, ManagedJobsRoutes


def _managed_config() -> ManagedJobsConfig:
    return ManagedJobsConfig(
        policy="workflows/managed_jobs/policy.yaml",
        watch_roots=("scripts/training", "scripts/studies"),
        backend="auto",
        poll_budget_sec=60,
        on=ManagedJobsRoutes(
            complete="Review",
            failed="Fix",
            invalid="Fix",
            outstanding="fail_resumable",
        ),
    )


def test_wraps_provider_invocation_with_guard(tmp_path: Path) -> None:
    invocation = ProviderInvocation(
        command=["codex", "exec", "--model", "gpt-5.3"],
        input_mode=InputMode.STDIN,
        prompt="do work",
        output_file="artifacts/out.txt",
        env={"EXISTING": "1"},
        timeout_sec=120,
    )
    runtime = ManagedProviderRuntime(
        run_root=tmp_path / ".orchestrate" / "runs" / "run-1",
        workspace=tmp_path,
    )

    wrapped = runtime.wrap_invocation(
        invocation,
        step_name="Execute",
        visit_count=1,
        config=_managed_config(),
    )

    assert wrapped.prompt == invocation.prompt
    assert wrapped.output_file == invocation.output_file
    assert wrapped.timeout_sec == invocation.timeout_sec
    assert wrapped.input_mode == invocation.input_mode
    assert wrapped.terminate_process_tree is True
    assert wrapped.env["EXISTING"] == "1"
    assert wrapped.env["MANAGED_JOB_AUDIT_PATH"].endswith("managed_job_events.jsonl")
    assert wrapped.command[:3] == [sys.executable, "-m", "orchestrator.managed_jobs.provider_guard"]
    assert "--pending-policy" in wrapped.command
    assert wrapped.command[-4:] == ["codex", "exec", "--model", "gpt-5.3"]


def test_recovery_no_audited_jobs_is_complete(tmp_path: Path) -> None:
    summary = recover_managed_jobs(tmp_path / "managed_job_events.jsonl")

    assert summary["managed_job_outcome"] == "COMPLETE"
    assert summary["recovery_status"] == "COMPLETE"
    assert summary["jobs"] == []


def test_recovery_completed_verified_jobs_are_complete(tmp_path: Path) -> None:
    audit_path = tmp_path / "events.jsonl"
    state_path = tmp_path / "state" / "job_state.json"
    state_path.parent.mkdir()
    state_path.write_text(
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
    append_event(
        audit_path,
        {
            "event": "job_submitted",
            "job_id": "job-1",
            "job_state_path": str(state_path),
        },
    )

    summary = recover_managed_jobs(audit_path)

    assert summary["managed_job_outcome"] == "COMPLETE"
    assert summary["jobs"][0]["status"] == "VERIFIED"


def test_recovery_missing_identity_metadata_is_invalid(tmp_path: Path) -> None:
    audit_path = tmp_path / "events.jsonl"
    state_path = tmp_path / "job_state.json"
    state_path.write_text(json.dumps({"status": "COMPLETED"}), encoding="utf-8")
    append_event(
        audit_path,
        {
            "event": "job_submitted",
            "job_id": "job-1",
            "job_state_path": str(state_path),
        },
    )

    summary = recover_managed_jobs(audit_path)

    assert summary["managed_job_outcome"] == "INVALID"
    assert summary["jobs"][0]["status"] == "INVALID"


def test_recovery_pending_jobs_are_outstanding(tmp_path: Path) -> None:
    audit_path = tmp_path / "events.jsonl"
    state_path = tmp_path / "job_state.json"
    state_path.write_text(
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
        audit_path,
        {
            "event": "job_submitted",
            "job_id": "job-1",
            "job_state_path": str(state_path),
        },
    )

    summary = recover_managed_jobs(audit_path)

    assert summary["managed_job_outcome"] == "OUTSTANDING"
