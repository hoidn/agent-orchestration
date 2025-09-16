"""Tests for State Manager (AT-4)."""

import json
import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone

from orchestrator.state import StateManager, RunState, StepResult, ForEachState


class TestStateManager:
    """Test state manager functionality per AT-4."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace."""
        workspace = tempfile.mkdtemp()
        yield Path(workspace)
        shutil.rmtree(workspace)

    @pytest.fixture
    def workflow_file(self, temp_workspace):
        """Create a test workflow file."""
        workflow_path = temp_workspace / "test.yaml"
        workflow_path.write_text("""
version: "1.1"
steps:
  - name: Test
    command: echo test
""")
        return "test.yaml"

    def test_at4_state_file_write_read(self, temp_workspace, workflow_file):
        """AT-4: Write/read state.json with v1 schema."""
        # Initialize state manager
        manager = StateManager(temp_workspace)

        # Initialize state
        state = manager.initialize(workflow_file, context={"key": "value"})

        # Verify state structure
        assert state.schema_version == "1.1.1"
        assert state.run_id == manager.run_id
        assert state.workflow_file == workflow_file
        assert state.workflow_checksum.startswith("sha256:")
        assert state.status == "running"
        assert state.context == {"key": "value"}

        # Verify state file was written
        state_file = temp_workspace / ".orchestrate" / "runs" / manager.run_id / "state.json"
        assert state_file.exists()

        # Read state file directly
        with open(state_file, 'r') as f:
            data = json.load(f)

        # Verify JSON structure matches spec
        assert data["schema_version"] == "1.1.1"
        assert data["run_id"] == manager.run_id
        assert data["workflow_file"] == workflow_file
        assert data["workflow_checksum"].startswith("sha256:")
        assert data["started_at"]
        assert data["updated_at"]
        assert data["status"] == "running"
        assert data["context"] == {"key": "value"}
        assert data["steps"] == {}

        # Load state in new manager
        manager2 = StateManager(temp_workspace, run_id=manager.run_id)
        loaded_state = manager2.load()

        # Verify loaded state matches
        assert loaded_state.schema_version == state.schema_version
        assert loaded_state.run_id == state.run_id
        assert loaded_state.workflow_file == state.workflow_file
        assert loaded_state.workflow_checksum == state.workflow_checksum
        assert loaded_state.status == state.status
        assert loaded_state.context == state.context

    def test_at4_step_result_recording(self, temp_workspace, workflow_file):
        """AT-4: Record step results in state."""
        manager = StateManager(temp_workspace)
        manager.initialize(workflow_file)

        # Add step result
        result = StepResult(
            status="completed",
            exit_code=0,
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=datetime.now(timezone.utc).isoformat(),
            duration_ms=1234,
            output="test output",
            truncated=False
        )

        manager.update_step("TestStep", result)

        # Verify in memory
        assert "TestStep" in manager.state.steps

        # Load and verify persistence
        manager2 = StateManager(temp_workspace, run_id=manager.run_id)
        loaded_state = manager2.load()

        assert "TestStep" in loaded_state.steps
        step_data = loaded_state.steps["TestStep"]
        assert step_data["status"] == "completed"
        assert step_data["exit_code"] == 0
        assert step_data["duration_ms"] == 1234
        assert step_data["output"] == "test output"
        assert step_data["truncated"] is False

    def test_at4_loop_state_indexing(self, temp_workspace, workflow_file):
        """AT-4/AT-43: Loop state stored as steps.<LoopName>[i].<StepName>."""
        manager = StateManager(temp_workspace)
        manager.initialize(workflow_file)

        # Add for_each state
        loop_state = ForEachState(
            items=["item1", "item2", "item3"],
            completed_indices=[0],
            current_index=1
        )
        manager.update_for_each("ProcessItems", loop_state)

        # Add loop step results
        for i in range(2):
            result = StepResult(
                status="completed",
                exit_code=0,
                output=f"processed item{i+1}"
            )
            manager.update_loop_step("ProcessItems", i, "Process", result)

        # Verify state structure
        assert "ProcessItems" in manager.state.for_each
        assert manager.state.for_each["ProcessItems"].items == ["item1", "item2", "item3"]
        assert manager.state.for_each["ProcessItems"].completed_indices == [0]
        assert manager.state.for_each["ProcessItems"].current_index == 1

        # Verify loop step indexing
        assert "ProcessItems[0].Process" in manager.state.steps
        assert "ProcessItems[1].Process" in manager.state.steps

        # Load and verify persistence
        manager2 = StateManager(temp_workspace, run_id=manager.run_id)
        loaded_state = manager2.load()

        assert "ProcessItems" in loaded_state.for_each
        assert "ProcessItems[0].Process" in loaded_state.steps
        assert loaded_state.steps["ProcessItems[0].Process"]["output"] == "processed item1"
        assert loaded_state.steps["ProcessItems[1].Process"]["output"] == "processed item2"

    def test_at4_atomic_writes(self, temp_workspace, workflow_file):
        """AT-4: Verify atomic write behavior."""
        manager = StateManager(temp_workspace)
        manager.initialize(workflow_file)

        state_file = manager.state_file

        # Update state multiple times
        for i in range(5):
            result = StepResult(status="completed", exit_code=0, output=f"step{i}")
            manager.update_step(f"Step{i}", result)

            # Verify no .tmp file left behind
            assert not state_file.with_suffix('.tmp').exists()

            # Verify state file is valid JSON
            with open(state_file, 'r') as f:
                data = json.load(f)
                assert f"Step{i}" in data["steps"]

    def test_at4_backup_and_rotation(self, temp_workspace, workflow_file):
        """AT-4: Test backup creation and rotation."""
        manager = StateManager(temp_workspace, backup_enabled=True)
        manager.initialize(workflow_file)

        # Create backups for multiple steps
        step_names = ["Step1", "Step2", "Step3", "Step4", "Step5"]
        for step_name in step_names:
            manager.backup_state(step_name)
            result = StepResult(status="completed", exit_code=0)
            manager.update_step(step_name, result)

        # Check that only last 3 backups exist
        backup_files = list(manager.state_file.parent.glob("state.json.step_*.bak"))
        assert len(backup_files) == 3

        # Verify the remaining backups are the most recent ones
        backup_names = [f.stem for f in backup_files]
        assert "state.json.step_Step3" in str(backup_files)
        assert "state.json.step_Step4" in str(backup_files)
        assert "state.json.step_Step5" in str(backup_files)

    def test_at4_checksum_validation(self, temp_workspace, workflow_file):
        """AT-4: Test workflow checksum validation."""
        manager = StateManager(temp_workspace)
        manager.initialize(workflow_file)

        # Checksum should match
        assert manager.validate_checksum(workflow_file)

        # Modify workflow file
        workflow_path = temp_workspace / workflow_file
        workflow_path.write_text("""
version: "1.1"
steps:
  - name: Modified
    command: echo modified
""")

        # Checksum should not match
        assert not manager.validate_checksum(workflow_file)

    def test_at4_repair_from_backup(self, temp_workspace, workflow_file):
        """AT-4: Test state repair from backup."""
        manager = StateManager(temp_workspace, backup_enabled=True)
        manager.initialize(workflow_file)

        # Create a valid backup
        manager.backup_state("GoodStep")
        result = StepResult(status="completed", exit_code=0, output="good")
        manager.update_step("GoodStep", result)

        # Corrupt the main state file
        manager.state_file.write_text("invalid json {")

        # Attempt repair
        assert manager.attempt_repair()

        # Verify state was recovered
        loaded_state = manager.load()
        assert loaded_state.status == "running"
        assert loaded_state.workflow_file == workflow_file

    def test_at4_run_id_format(self, temp_workspace):
        """AT-4: Verify run_id format YYYYMMDDTHHMMSSZ-<6char>."""
        manager = StateManager(temp_workspace)

        # Check format
        run_id = manager.run_id
        assert len(run_id) == 23  # 16 for timestamp, 1 for dash, 6 for suffix
        assert run_id[15] == 'Z'
        assert run_id[16] == '-'
        assert run_id[:8].isdigit()  # YYYYMMDD
        assert run_id[9:15].isdigit()  # HHMMSS

    def test_at4_status_transitions(self, temp_workspace, workflow_file):
        """AT-4: Test status transitions."""
        manager = StateManager(temp_workspace)
        manager.initialize(workflow_file)

        # Initial status
        assert manager.state.status == "running"

        # Update to completed
        manager.update_status("completed")
        assert manager.state.status == "completed"

        # Load and verify
        manager2 = StateManager(temp_workspace, run_id=manager.run_id)
        loaded = manager2.load()
        assert loaded.status == "completed"

        # Update to failed
        manager.update_status("failed")
        assert manager.state.status == "failed"

    def test_at4_error_context_recording(self, temp_workspace, workflow_file):
        """AT-4: Test error context recording in step results."""
        manager = StateManager(temp_workspace)
        manager.initialize(workflow_file)

        # Add failed step with error context
        result = StepResult(
            status="failed",
            exit_code=2,
            error={
                "type": "ValidationError",
                "message": "Missing required dependency",
                "context": {
                    "missing_files": ["config.yaml"],
                    "step": "ValidateConfig"
                }
            }
        )

        manager.update_step("ValidateConfig", result)

        # Load and verify
        manager2 = StateManager(temp_workspace, run_id=manager.run_id)
        loaded = manager2.load()

        step = loaded.steps["ValidateConfig"]
        assert step["status"] == "failed"
        assert step["exit_code"] == 2
        assert step["error"]["type"] == "ValidationError"
        assert step["error"]["context"]["missing_files"] == ["config.yaml"]