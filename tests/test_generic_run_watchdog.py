import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _write_state(workspace: Path, run_id: str, payload: dict) -> Path:
    state_path = _target_workspace(workspace) / ".orchestrate/runs" / run_id / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    merged = {
        "schema_version": "2.1",
        "run_id": run_id,
        "workflow_file": "workflows/examples/demo.yaml",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "steps": {},
    }
    merged.update(payload)
    state_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return state_path


def _target_workspace(workspace: Path) -> Path:
    """The workspace of the observed run, beside the watchdog's own workspace."""

    return workspace.with_name(workspace.name + "-target")


def _run_probe(workspace: Path, run_id: str, *extra: str) -> dict:
    output = "state/watchdog/watch.json"
    subprocess.run(
        [
            "python",
            str(ROOT / "workflows/library/scripts/probe_orchestrator_run.py"),
            "--run-id",
            run_id,
            "--target-workspace",
            str(_target_workspace(workspace)),
            "--output",
            output,
            "--evidence-root",
            "artifacts/work/watchdog",
            "--repair-result-target-path",
            "artifacts/work/watchdog/repair-result.json",
            *extra,
        ],
        cwd=workspace,
        env={**os.environ, "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")},
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads((workspace / output).read_text(encoding="utf-8"))


def test_probe_classifies_running_completed_failed_and_stalled(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    _write_state(workspace, "run-running", {"status": "running"})
    running = _run_probe(workspace, "run-running")
    assert running["watch_status"] == "RUNNING_OK"
    assert running["repair_required"] == "NO"
    assert (workspace / running["evidence_bundle_path"]).is_file()

    _write_state(workspace, "run-completed", {"status": "completed"})
    completed = _run_probe(workspace, "run-completed")
    assert completed["watch_status"] == "COMPLETED"
    assert completed["recommended_recovery"] == "NONE"

    _write_state(
        workspace,
        "run-failed",
        {
            "status": "failed",
            "steps": {
                "Explode": {
                    "status": "failed",
                    "error": {"type": "boom", "message": "exploded"},
                }
            },
        },
    )
    failed = _run_probe(workspace, "run-failed")
    assert failed["watch_status"] == "FAILED"
    assert failed["repair_required"] == "YES"
    assert failed["recommended_recovery"] == "RESUME"
    evidence = json.loads((workspace / failed["evidence_bundle_path"]).read_text(encoding="utf-8"))
    assert evidence["failed_steps"][0]["name"] == "Explode"

    stale_time = datetime.now(timezone.utc) - timedelta(minutes=45)
    _write_state(workspace, "run-stale", {"status": "running", "updated_at": stale_time.isoformat()})
    stalled = _run_probe(workspace, "run-stale", "--max-stale-minutes", "30")
    assert stalled["watch_status"] == "STALLED"
    assert stalled["repair_required"] == "YES"
    assert stalled["recommended_recovery"] == "INVESTIGATE"
