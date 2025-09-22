"""Test AT-60: Wait-for integration with state recording.

Engine executes wait_for steps and records files, wait_duration_ms, poll_count, timed_out;
downstream steps run on success.
"""

import pytest
import yaml
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.state import StateManager
from orchestrator.loader import WorkflowLoader


class TestAT60WaitForIntegration:
    """Test wait-for integration per AT-60."""

    def test_at60_wait_for_executes_and_records_state(self, tmp_path):
        """AT-60: Engine executes wait_for steps and records all required fields."""
        # Create workspace
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create a file that will be waited for
        target_file = workspace / "output.txt"

        # Create workflow
        workflow_content = {
            "version": "1.1",
            "name": "wait-for-test",
            "steps": [
                {
                    "name": "WaitForFile",
                    "wait_for": {
                        "glob": "output.txt",
                        "timeout_sec": 5,
                        "poll_ms": 100,
                        "min_count": 1
                    }
                },
                {
                    "name": "ProcessFile",
                    "command": ["echo", "Found files"]
                }
            ]
        }

        workflow_file = tmp_path / "workflow.yaml"
        with open(workflow_file, "w") as f:
            yaml.dump(workflow_content, f)

        # Load workflow
        loader = WorkflowLoader(workspace)
        workflow = loader.load(str(workflow_file))

        # Create state manager
        state_manager = StateManager(str(tmp_path / ".orchestrate"))
        state = state_manager.initialize(str(workflow_file))

        # Create executor
        executor = WorkflowExecutor(workflow, workspace, state_manager)

        # Create the target file after a short delay (simulating async creation)
        def create_file_async():
            time.sleep(0.2)  # Wait 200ms
            target_file.write_text("test content")

        import threading
        thread = threading.Thread(target=create_file_async)
        thread.start()

        # Execute workflow
        try:
            executor.execute()
            thread.join()

            # Load final state
            final_state = state_manager.load()

            # Verify wait_for step recorded all required fields (AT-60)
            wait_step = final_state.steps["WaitForFile"]
            assert wait_step["status"] == "completed"
            assert wait_step["exit_code"] == 0
            assert "files" in wait_step
            assert wait_step["files"] == ["output.txt"]
            assert "wait_duration_ms" in wait_step
            assert wait_step["wait_duration_ms"] >= 200  # At least 200ms wait
            assert "poll_count" in wait_step
            assert wait_step["poll_count"] >= 2  # At least 2 polls (200ms / 100ms)
            assert "timed_out" in wait_step
            assert wait_step["timed_out"] is False

            # Verify downstream step ran and could access wait_for results
            process_step = final_state.steps["ProcessFile"]
            if process_step["status"] != "completed":
                print(f"ProcessFile error: {process_step.get('error', 'No error info')}")
                print(f"ProcessFile full state: {process_step}")
            assert process_step["status"] == "completed"
            assert process_step["exit_code"] == 0

        finally:
            thread.join()

    def test_at60_wait_for_timeout_records_state(self, tmp_path):
        """AT-60: Wait-for timeout records timed_out=true and exit 124."""
        # Create workspace
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create workflow (file won't exist, will timeout)
        workflow_content = {
            "version": "1.1",
            "name": "wait-timeout-test",
            "steps": [
                {
                    "name": "WaitForMissing",
                    "wait_for": {
                        "glob": "missing.txt",
                        "timeout_sec": 1,
                        "poll_ms": 200
                    }
                },
                {
                    "name": "ShouldNotRun",
                    "command": ["echo", "This should not run"]
                }
            ]
        }

        workflow_file = tmp_path / "workflow.yaml"
        with open(workflow_file, "w") as f:
            yaml.dump(workflow_content, f)

        # Load workflow
        loader = WorkflowLoader(workspace)
        workflow = loader.load(str(workflow_file))

        # Create state manager
        state_manager = StateManager(str(tmp_path / ".orchestrate"))
        state = state_manager.initialize(str(workflow_file))

        # Create executor
        executor = WorkflowExecutor(workflow, workspace, state_manager)

        # Execute workflow (should fail with timeout but continue)
        try:
            executor.execute()
        except SystemExit:
            pass  # Expected if strict_flow stops on failure

        # Load final state
        final_state = state_manager.load()

        # Verify wait_for step recorded timeout (AT-60)
        wait_step = final_state.steps["WaitForMissing"]
        assert wait_step["status"] == "failed"
        assert wait_step["exit_code"] == 124
        assert wait_step["files"] == []
        assert wait_step["wait_duration_ms"] >= 1000  # At least 1 second
        assert wait_step["poll_count"] >= 5  # 1000ms / 200ms = 5 polls
        assert wait_step["timed_out"] is True

        # Verify downstream step did not run
        assert "ShouldNotRun" not in final_state.steps

    def test_at60_wait_for_multiple_files(self, tmp_path):
        """AT-60: Wait-for with multiple files records all found files."""
        # Create workspace
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create multiple files
        (workspace / "data1.txt").write_text("content1")
        (workspace / "data2.txt").write_text("content2")
        (workspace / "data3.txt").write_text("content3")

        # Create workflow
        workflow_content = {
            "version": "1.1",
            "name": "wait-multiple-test",
            "steps": [
                {
                    "name": "WaitForData",
                    "wait_for": {
                        "glob": "data*.txt",
                        "timeout_sec": 5,
                        "min_count": 2  # Wait for at least 2 files
                    }
                },
                {
                    "name": "CountFiles",
                    "command": ["echo", "Found ${steps.WaitForData.files}"]
                }
            ]
        }

        workflow_file = tmp_path / "workflow.yaml"
        with open(workflow_file, "w") as f:
            yaml.dump(workflow_content, f)

        # Load workflow
        loader = WorkflowLoader(workspace)
        workflow = loader.load(str(workflow_file))

        # Create state manager
        state_manager = StateManager(str(tmp_path / ".orchestrate"))
        state = state_manager.initialize(str(workflow_file))

        # Create executor
        executor = WorkflowExecutor(workflow, workspace, state_manager)

        # Execute workflow
        executor.execute()

        # Load final state
        final_state = state_manager.load()

        # Verify wait_for found all files (AT-60)
        wait_step = final_state.steps["WaitForData"]
        assert wait_step["status"] == "completed"
        assert wait_step["exit_code"] == 0
        assert sorted(wait_step["files"]) == ["data1.txt", "data2.txt", "data3.txt"]
        assert wait_step["timed_out"] is False

        # Verify downstream step ran
        count_step = final_state.steps["CountFiles"]
        assert count_step["status"] == "completed"

    def test_at60_wait_for_state_persistence(self, tmp_path):
        """AT-60: Wait-for results are persisted to state.json."""
        # Create workspace
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create target file
        (workspace / "ready.txt").write_text("ready")

        # Create workflow
        workflow_content = {
            "version": "1.1",
            "name": "persistence-test",
            "steps": [
                {
                    "name": "WaitStep",
                    "wait_for": {
                        "glob": "ready.txt",
                        "timeout_sec": 5
                    }
                }
            ]
        }

        workflow_file = tmp_path / "workflow.yaml"
        with open(workflow_file, "w") as f:
            yaml.dump(workflow_content, f)

        # Load workflow
        loader = WorkflowLoader(workspace)
        workflow = loader.load(str(workflow_file))

        # Create state manager
        state_dir = tmp_path / ".orchestrate"
        state_manager = StateManager(str(state_dir))
        state = state_manager.initialize(str(workflow_file))
        run_id = state.run_id

        # Create executor
        executor = WorkflowExecutor(workflow, workspace, state_manager)

        # Execute workflow
        executor.execute()

        # Read state.json directly from disk
        # The StateManager creates a nested .orchestrate within the base_dir
        state_file = state_dir / ".orchestrate" / "runs" / run_id / "state.json"
        if not state_file.exists():
            # Try without the extra .orchestrate
            state_file = state_dir / "runs" / run_id / "state.json"
        assert state_file.exists(), f"State file not found at {state_file}"

        import json
        with open(state_file) as f:
            persisted_state = json.load(f)

        # Verify wait_for fields are persisted (AT-60)
        wait_step = persisted_state["steps"]["WaitStep"]
        assert "files" in wait_step
        assert "wait_duration_ms" in wait_step
        assert "poll_count" in wait_step
        assert "timed_out" in wait_step
        assert wait_step["files"] == ["ready.txt"]
        assert wait_step["timed_out"] is False