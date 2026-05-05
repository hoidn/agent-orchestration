import json
from pathlib import Path

import pytest
import yaml

from orchestrator.managed_jobs.audit import read_events
from orchestrator.managed_jobs.runner import ManagedJobRunnerError, run_managed_job


def _write_policy(tmp_path: Path, entries: list[dict], *, default_backend: str = "local") -> Path:
    path = tmp_path / "policy.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "backend_defaults": {"backend": default_backend},
                "entries": entries,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def _managed_entry(path: str = "scripts/train.py", *, backend: str = "local") -> dict:
    return {
        "id": "train",
        "mode": "force_managed",
        "path": path,
        "backend": backend,
        "job": {
            "name_template": "train-{job_identity_hash}",
            "state_root_template": "managed_state/{entry_id}/{job_identity_hash}",
            "output_root_arg": "--output-dir",
            "verify_files": ["{output_root}/metrics.json"],
            "snapshot_roots": ["scripts"],
            "config_globs": ["configs/*.yaml"],
        },
    }


def test_managed_entry_writes_audit_events_and_job_state(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    script = workspace / "scripts" / "train.py"
    script.parent.mkdir(parents=True)
    script.write_text("print('managed')\n", encoding="utf-8")
    config = workspace / "configs" / "train.yaml"
    config.parent.mkdir()
    config.write_text("epochs: 1\n", encoding="utf-8")
    policy_path = _write_policy(workspace, [_managed_entry()])
    audit_path = tmp_path / "audit.jsonl"

    result = run_managed_job(
        ["python", "scripts/train.py"],
        workspace=workspace,
        policy_path=policy_path,
        audit_path=audit_path,
        state_root=tmp_path / "state",
        pending_policy_path=tmp_path / "pending.jsonl",
        backend="local",
    )

    assert result.status == "completed"
    events = read_events(audit_path)
    assert [event["event"] for event in events] == ["job_submitted", "job_completed"]
    job_state = json.loads(Path(result.job_state_path).read_text(encoding="utf-8"))
    assert job_state["job_identity_hash"] == result.job_identity_hash
    assert job_state["snapshot"]["manifest"]
    assert job_state["verify_files"] == ["{output_root}/metrics.json"]


def test_unmanaged_and_force_local_entries_run_locally(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    script = workspace / "scripts" / "prep.py"
    script.parent.mkdir(parents=True)
    output = workspace / "local.txt"
    script.write_text(f"from pathlib import Path; Path({str(output)!r}).write_text('ok')\n", encoding="utf-8")
    policy_path = _write_policy(
        workspace,
        [{"id": "prep", "mode": "force_local", "path": "scripts/prep.py"}],
    )

    result = run_managed_job(
        ["python", "scripts/prep.py"],
        workspace=workspace,
        policy_path=policy_path,
        audit_path=tmp_path / "audit.jsonl",
        state_root=tmp_path / "state",
        pending_policy_path=tmp_path / "pending.jsonl",
        backend="local",
    )

    assert result.status == "local"
    assert output.read_text(encoding="utf-8") == "ok"
    assert not (tmp_path / "audit.jsonl").exists()


def test_conflicting_policy_entries_fail_before_launch(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    script = workspace / "scripts" / "train.py"
    script.parent.mkdir(parents=True)
    script.write_text("raise SystemExit('should not run')\n", encoding="utf-8")
    policy_path = _write_policy(workspace, [_managed_entry(), _managed_entry()])

    with pytest.raises(ManagedJobRunnerError, match="conflicting"):
        run_managed_job(
            ["python", "scripts/train.py"],
            workspace=workspace,
            policy_path=policy_path,
            audit_path=tmp_path / "audit.jsonl",
            state_root=tmp_path / "state",
            pending_policy_path=tmp_path / "pending.jsonl",
            backend="local",
        )


def test_missing_managed_metadata_fails_before_launch(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    script = workspace / "scripts" / "train.py"
    script.parent.mkdir(parents=True)
    script.write_text("raise SystemExit('should not run')\n", encoding="utf-8")
    policy_path = _write_policy(
        workspace,
        [{"id": "train", "mode": "force_managed", "path": "scripts/train.py", "extractor": "missing"}],
    )

    with pytest.raises(ManagedJobRunnerError, match="metadata|extractor"):
        run_managed_job(
            ["python", "scripts/train.py"],
            workspace=workspace,
            policy_path=policy_path,
            audit_path=tmp_path / "audit.jsonl",
            state_root=tmp_path / "state",
            pending_policy_path=tmp_path / "pending.jsonl",
            backend="local",
        )


def test_job_identity_changes_with_arguments_and_config_inputs(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    script = workspace / "scripts" / "train.py"
    script.parent.mkdir(parents=True)
    script.write_text("print('managed')\n", encoding="utf-8")
    config = workspace / "configs" / "train.yaml"
    config.parent.mkdir()
    config.write_text("epochs: 1\n", encoding="utf-8")
    policy_path = _write_policy(workspace, [_managed_entry()])

    first = run_managed_job(
        ["python", "scripts/train.py", "--epochs", "1"],
        workspace=workspace,
        policy_path=policy_path,
        audit_path=tmp_path / "audit1.jsonl",
        state_root=tmp_path / "state1",
        pending_policy_path=tmp_path / "pending.jsonl",
        backend="local",
    )
    config.write_text("epochs: 2\n", encoding="utf-8")
    second = run_managed_job(
        ["python", "scripts/train.py", "--epochs", "2"],
        workspace=workspace,
        policy_path=policy_path,
        audit_path=tmp_path / "audit2.jsonl",
        state_root=tmp_path / "state2",
        pending_policy_path=tmp_path / "pending.jsonl",
        backend="local",
    )

    assert first.job_identity_hash != second.job_identity_hash


def test_slurm_backend_generates_snapshot_bound_script_without_cluster(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    script = workspace / "scripts" / "train.py"
    script.parent.mkdir(parents=True)
    script.write_text("print('managed')\n", encoding="utf-8")
    policy_path = _write_policy(workspace, [_managed_entry(backend="slurm")], default_backend="slurm")

    result = run_managed_job(
        ["python", "scripts/train.py"],
        workspace=workspace,
        policy_path=policy_path,
        audit_path=tmp_path / "audit.jsonl",
        state_root=tmp_path / "state",
        pending_policy_path=tmp_path / "pending.jsonl",
        backend="slurm",
    )

    job_state = json.loads(Path(result.job_state_path).read_text(encoding="utf-8"))
    script_text = Path(job_state["backend"]["script_path"]).read_text(encoding="utf-8")
    assert result.status == "submitted"
    assert "cd " in script_text
    assert job_state["snapshot"]["manifest"] in script_text
    assert result.job_identity_hash in script_text
