"""Integration tests for runtime step lifecycle state updates."""

import json
import threading
import time
from pathlib import Path

import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor


def _write_workflow(workspace: Path, workflow: dict) -> Path:
    workflow_file = workspace / "workflow.yaml"
    workflow_file.write_text(yaml.dump(workflow), encoding="utf-8")
    return workflow_file


def test_long_running_step_updates_current_step_heartbeat(tmp_path: Path):
    workflow = {
        "version": "1.1.1",
        "name": "runtime-step-lifecycle",
        "steps": [
            {
                "name": "LongCommand",
                "command": ["bash", "-lc", "python -c 'import time; time.sleep(0.6)'"],
            }
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(
        loaded,
        tmp_path,
        state_manager,
        step_heartbeat_interval_sec=0.1,
    )

    worker = threading.Thread(target=executor.execute)
    worker.start()

    state_file = tmp_path / ".orchestrate" / "runs" / "test-run" / "state.json"
    deadline = time.time() + 5
    running_snapshot = None
    while time.time() < deadline:
        if state_file.exists():
            snapshot = json.loads(state_file.read_text(encoding="utf-8"))
            current = snapshot.get("current_step")
            if isinstance(current, dict) and current.get("name") == "LongCommand":
                running_snapshot = snapshot
                break
        time.sleep(0.02)

    assert running_snapshot is not None
    first_heartbeat = running_snapshot["current_step"]["last_heartbeat_at"]

    time.sleep(0.25)
    second_snapshot = json.loads(state_file.read_text(encoding="utf-8"))
    assert second_snapshot.get("current_step", {}).get("name") == "LongCommand"
    assert second_snapshot["current_step"]["last_heartbeat_at"] != first_heartbeat

    worker.join(timeout=5)
    assert not worker.is_alive()

    final_snapshot = json.loads(state_file.read_text(encoding="utf-8"))
    assert final_snapshot.get("current_step") is None
    assert final_snapshot["steps"]["LongCommand"]["status"] == "completed"
