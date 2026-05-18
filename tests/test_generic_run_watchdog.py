import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from orchestrator.loader import WorkflowLoader
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_context, workflow_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs


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


def _copy_watchdog_runtime_files(workspace: Path) -> Path:
    files = [
        "workflows/examples/generic_run_watchdog.yaml",
        "workflows/library/scripts/probe_orchestrator_run.py",
        "workflows/library/scripts/publish_run_watchdog_result.py",
        "workflows/library/prompts/generic_run_watchdog/repair_run_failure.md",
    ]
    for relpath in files:
        src = ROOT / relpath
        dest = workspace / relpath
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return workspace / "workflows/examples/generic_run_watchdog.yaml"


def _bundle_context_dict(bundle) -> dict:
    return dict(workflow_context(bundle))


def _run_watchdog(workspace: Path, run_id: str, provider_writer=None) -> dict:
    workflow_path = _copy_watchdog_runtime_files(workspace)
    workflow = WorkflowLoader(workspace).load(workflow_path)
    bound_inputs = bind_workflow_inputs(
        workflow_input_contracts(workflow),
        {"target_run_id": run_id},
        workspace,
    )
    state_manager = StateManager(workspace=workspace, run_id="watchdog-test-run")
    state_manager.initialize(
        workflow_path.relative_to(workspace).as_posix(),
        _bundle_context_dict(workflow),
        bound_inputs=bound_inputs,
    )
    executor = WorkflowExecutor(workflow, workspace, state_manager)
    provider_calls = {"count": 0}

    def _prepare_invocation(_self, *args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", "")), None

    def _execute(_self, _invocation, **kwargs):
        provider_calls["count"] += 1
        assert provider_writer is not None
        provider_writer(workspace)
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        state = executor.execute()
    state["__provider_calls"] = provider_calls["count"]
    return state


def test_generic_watchdog_no_action_path_skips_provider(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_state(workspace, "target-run", {"status": "running"})

    state = _run_watchdog(workspace, "target-run")

    assert state["__provider_calls"] == 0
    result = json.loads((workspace / "state/GENERIC-RUN-WATCHDOG/watchdog-result.json").read_text())
    assert result["watch_status"] == "RUNNING_OK"
    assert result["repair_status"] == "NO_ACTION"


def test_generic_watchdog_repair_path_invokes_provider(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_state(workspace, "target-run", {"status": "failed"})

    def _write_repair_result(ws: Path) -> None:
        target = ws / "artifacts/work/generic-run-watchdog/repair-result.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "repair_status": "FIXED_AND_RESUMED",
                    "fix_complexity": "TRIVIAL",
                    "recovery_action": "RESUME",
                    "repair_report_path": "artifacts/work/generic-run-watchdog/repair-report.md",
                    "plan_path": "",
                    "new_run_id": "",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (ws / "artifacts/work/generic-run-watchdog/repair-report.md").write_text(
            "# Repair Report\n\nResumed.\n",
            encoding="utf-8",
        )

    state = _run_watchdog(workspace, "target-run", provider_writer=_write_repair_result)

    assert state["__provider_calls"] == 1
    result = json.loads((workspace / "state/GENERIC-RUN-WATCHDOG/watchdog-result.json").read_text())
    assert result["watch_status"] == "FAILED"
    assert result["repair_status"] == "FIXED_AND_RESUMED"
    assert result["recovery_action"] == "RESUME"
