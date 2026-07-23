import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _write_state(workspace: Path, run_id: str, payload: dict) -> Path:
    state_path = workspace / ".orchestrate/runs" / run_id / "state.json"
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


def _run_probe(workspace: Path, run_id: str, *extra: str) -> dict:
    output = "state/watchdog/watch.json"
    subprocess.run(
        [
            "python",
            str(ROOT / "workflows/library/scripts/probe_orchestrator_run.py"),
            "--run-id",
            run_id,
            "--output",
            output,
            "--evidence-root",
            "artifacts/work/watchdog",
            "--repair-result-target-path",
            "artifacts/work/watchdog/repair-result.json",
            *extra,
        ],
        cwd=workspace,
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


def _run_watchdog_script(
    workspace: Path,
    script_name: str,
    args: list[str],
    *,
    runtime_bundle_path: str,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"] = runtime_bundle_path
    return subprocess.run(
        [
            "python",
            str(ROOT / "workflows/library/scripts" / script_name),
            *args,
        ],
        cwd=workspace,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )


def test_watchdog_commands_write_runtime_and_compatibility_outputs(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_state(workspace, "target-run", {"status": "running"})

    _run_watchdog_script(
        workspace,
        "probe_orchestrator_run.py",
        [
            "--run-id",
            "target-run",
            "--output",
            "state/watchdog/watch.json",
            "--evidence-root",
            "artifacts/work/watchdog",
            "--repair-result-target-path",
            "artifacts/work/watchdog/repair-result.json",
        ],
        runtime_bundle_path="state/runtime/probe.json",
    )

    watch = json.loads((workspace / "state/watchdog/watch.json").read_text())
    probe_bundle = json.loads((workspace / "state/runtime/probe.json").read_text())
    assert watch["schema"] == "orchestrator_run_watch/v1"
    assert watch["watch_bundle_path"] == "state/watchdog/watch.json"
    assert probe_bundle == {
        "watch_bundle_path": "state/watchdog/watch.json",
        "watch_status": "RUNNING_OK",
        "repair_required": "NO",
        "recommended_recovery": "NONE",
        "evidence_bundle_path": "artifacts/work/watchdog/target-run-evidence.json",
        "repair_result_target_path": "artifacts/work/watchdog/repair-result.json",
    }

    _run_watchdog_script(
        workspace,
        "publish_run_watchdog_result.py",
        [
            "--watch-bundle-path",
            probe_bundle["watch_bundle_path"],
            "--target-run-id",
            "target-run",
            "--watch-status",
            "RUNNING_OK",
            "--repair-required",
            "NO",
            "--recommended-recovery",
            "NONE",
            "--evidence-bundle-path",
            probe_bundle["evidence_bundle_path"],
            "--repair-result-path",
            "",
            "--repair-status",
            "NO_ACTION",
            "--fix-complexity",
            "NOT_APPLICABLE",
            "--recovery-action",
            "NONE",
            "--repair-report-path",
            "",
            "--plan-path",
            "",
            "--new-run-id",
            "",
            "--output",
            "state/watchdog/watchdog-result.json",
        ],
        runtime_bundle_path="state/runtime/publish.json",
    )

    result = json.loads((workspace / "state/watchdog/watchdog-result.json").read_text())
    publish_bundle = json.loads((workspace / "state/runtime/publish.json").read_text())
    assert result["schema"] == "orchestrator_run_watchdog_result/v1"
    assert result["target_run_id"] == "target-run"
    assert result["repair_status"] == "NO_ACTION"
    assert result["repair_result_path"] == ""
    assert publish_bundle == {
        "watch_status": "RUNNING_OK",
        "repair_status": "NO_ACTION",
        "recovery_action": "NONE",
        "watchdog_result_path": "state/watchdog/watchdog-result.json",
    }

    _run_watchdog_script(
        workspace,
        "probe_orchestrator_run.py",
        [
            "--run-id",
            "target-run",
            "--output",
            "state/watchdog/same-path-watch.json",
            "--evidence-root",
            "artifacts/work/watchdog",
            "--repair-result-target-path",
            "artifacts/work/watchdog/repair-result.json",
        ],
        runtime_bundle_path="state/watchdog/same-path-watch.json",
    )
    same_path_probe = json.loads(
        (workspace / "state/watchdog/same-path-watch.json").read_text()
    )
    assert same_path_probe["schema"] == "orchestrator_run_watch/v1"
    for field, value in probe_bundle.items():
        expected = (
            "state/watchdog/same-path-watch.json"
            if field == "watch_bundle_path"
            else value
        )
        assert same_path_probe[field] == expected

    same_path_publish_args = [
        "--watch-bundle-path",
        "state/watchdog/same-path-watch.json",
        "--target-run-id",
        "target-run",
        "--watch-status",
        "RUNNING_OK",
        "--repair-required",
        "NO",
        "--recommended-recovery",
        "NONE",
        "--evidence-bundle-path",
        probe_bundle["evidence_bundle_path"],
        "--repair-result-path",
        "",
        "--repair-status",
        "NO_ACTION",
        "--fix-complexity",
        "NOT_APPLICABLE",
        "--recovery-action",
        "NONE",
        "--repair-report-path",
        "",
        "--plan-path",
        "",
        "--new-run-id",
        "",
        "--output",
        "state/watchdog/same-path-result.json",
    ]
    _run_watchdog_script(
        workspace,
        "publish_run_watchdog_result.py",
        same_path_publish_args,
        runtime_bundle_path="state/watchdog/same-path-result.json",
    )
    same_path_result = json.loads(
        (workspace / "state/watchdog/same-path-result.json").read_text()
    )
    assert same_path_result["schema"] == "orchestrator_run_watchdog_result/v1"
    assert {
        key: same_path_result[key]
        for key in (
            "watch_status",
            "repair_status",
            "recovery_action",
            "watchdog_result_path",
        )
    } == {
        "watch_status": "RUNNING_OK",
        "repair_status": "NO_ACTION",
        "recovery_action": "NONE",
        "watchdog_result_path": "state/watchdog/same-path-result.json",
    }


def test_watchdog_publisher_accepts_typed_repair_fields_without_parsing_control_state(
    tmp_path,
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    watch_path = workspace / "state/watchdog/watch.json"
    repair_path = workspace / "artifacts/work/watchdog/repair-result.json"
    report_path = workspace / "artifacts/work/watchdog/repair-report.md"
    evidence_path = workspace / "artifacts/work/watchdog/target-run-evidence.json"
    for path in (watch_path, repair_path, report_path, evidence_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    watch_path.write_text("not json\n", encoding="utf-8")
    repair_path.write_text("not json\n", encoding="utf-8")
    report_path.write_text("BLOCKED DECLINED\n", encoding="utf-8")
    evidence_path.write_text("{}\n", encoding="utf-8")

    _run_watchdog_script(
        workspace,
        "publish_run_watchdog_result.py",
        [
            "--watch-bundle-path",
            "state/watchdog/watch.json",
            "--target-run-id",
            "target-run",
            "--watch-status",
            "FAILED",
            "--repair-required",
            "YES",
            "--recommended-recovery",
            "RESUME",
            "--evidence-bundle-path",
            "artifacts/work/watchdog/target-run-evidence.json",
            "--repair-result-path",
            "artifacts/work/watchdog/repair-result.json",
            "--repair-status",
            "FIXED_AND_RESUMED",
            "--fix-complexity",
            "TRIVIAL",
            "--recovery-action",
            "RESUME",
            "--repair-report-path",
            "artifacts/work/watchdog/repair-report.md",
            "--plan-path",
            "",
            "--new-run-id",
            "",
            "--output",
            "state/watchdog/watchdog-result.json",
        ],
        runtime_bundle_path="state/runtime/publish.json",
    )

    result = json.loads((workspace / "state/watchdog/watchdog-result.json").read_text())
    assert result == {
        "schema": "orchestrator_run_watchdog_result/v1",
        "watchdog_result_path": "state/watchdog/watchdog-result.json",
        "target_run_id": "target-run",
        "watch_status": "FAILED",
        "repair_required": "YES",
        "recommended_recovery": "RESUME",
        "repair_status": "FIXED_AND_RESUMED",
        "fix_complexity": "TRIVIAL",
        "recovery_action": "RESUME",
        "evidence_bundle_path": "artifacts/work/watchdog/target-run-evidence.json",
        "repair_result_path": "artifacts/work/watchdog/repair-result.json",
        "repair_report_path": "artifacts/work/watchdog/repair-report.md",
        "plan_path": "",
        "new_run_id": "",
    }
