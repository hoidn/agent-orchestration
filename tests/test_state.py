"""Tests for state persistence (AT-4) and related acceptance tests."""

import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone
import pytest

from orchestrator.state import StateManager, RunState, StepState, StateFileHandler


class TestStatePersistence:
    """Tests for AT-4: Status schema - Write/read status.json with v1 schema."""

    def setup_method(self):
        """Set up test workspace."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.workflow_file = self.test_dir / "workflow.yaml"
        self.workflow_file.write_text("version: '1.1.1'\nname: test\nsteps: []")

    def teardown_method(self):
        """Clean up test workspace."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_state_initialization_creates_run_id_format(self):
        """Test run_id format: YYYYMMDDTHHMMSSZ-<6char>."""
        manager = StateManager(self.test_dir)

        # Check format
        assert len(manager.run_id) == 23  # 16 for timestamp + 1 dash + 6 chars
        assert manager.run_id[8] == 'T'
        assert manager.run_id[15] == 'Z'
        assert manager.run_id[16] == '-'

        # Check timestamp is valid
        timestamp_part = manager.run_id[:16]
        datetime.strptime(timestamp_part, "%Y%m%dT%H%M%SZ")

    def test_state_file_written_with_schema_version(self):
        """Test state.json includes schema_version: 1.1.1."""
        manager = StateManager(self.test_dir)
        state = manager.initialize_run("workflow.yaml", self.workflow_file)

        # Check in-memory state
        assert state.schema_version == "1.1.1"

        # Check persisted file
        state_file = manager.state_file
        assert state_file.exists()

        with open(state_file, 'r') as f:
            data = json.load(f)

        assert data["schema_version"] == "1.1.1"
        assert data["run_id"] == manager.run_id
        assert data["workflow_file"] == "workflow.yaml"
        assert "workflow_checksum" in data
        assert data["workflow_checksum"].startswith("sha256:")

    def test_atomic_write_with_temp_file(self):
        """Test atomic writes using temp file + rename."""
        manager = StateManager(self.test_dir)
        state = manager.initialize_run("workflow.yaml", self.workflow_file)

        # Add a step
        step_state = StepState(
            status="completed",
            exit_code=0,
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=datetime.now(timezone.utc).isoformat(),
            duration_ms=1234,
            output="test output"
        )
        manager.update_step("TestStep", step_state)

        # Verify temp file doesn't exist after write
        temp_file = manager.state_file.with_suffix('.tmp')
        assert not temp_file.exists()

        # Verify state file has correct content
        with open(manager.state_file, 'r') as f:
            data = json.load(f)

        assert "TestStep" in data["steps"]
        assert data["steps"]["TestStep"]["status"] == "completed"
        assert data["steps"]["TestStep"]["exit_code"] == 0

    def test_load_existing_state(self):
        """Test loading and resuming from existing state file."""
        # Create initial run
        manager1 = StateManager(self.test_dir)
        state1 = manager1.initialize_run("workflow.yaml", self.workflow_file)
        run_id = manager1.run_id

        # Add some state
        manager1.update_step("Step1", StepState(status="completed", exit_code=0))
        manager1.update_status("running")

        # Load in new manager instance
        manager2 = StateManager(self.test_dir, run_id=run_id)
        state2 = manager2.load_state()

        assert state2.run_id == run_id
        assert state2.schema_version == "1.1.1"
        assert "Step1" in state2.steps
        assert state2.steps["Step1"].status == "completed"
        assert state2.status == "running"

    def test_workflow_checksum_validation(self):
        """Test workflow checksum is computed and validated."""
        manager = StateManager(self.test_dir)
        state = manager.initialize_run("workflow.yaml", self.workflow_file)

        # Checksum should be set
        assert state.workflow_checksum.startswith("sha256:")

        # Validation should pass for unchanged file
        assert manager.validate_checksum(self.workflow_file)

        # Modify workflow file
        self.workflow_file.write_text("version: '1.1.1'\nname: modified\nsteps: []")

        # Validation should fail
        assert not manager.validate_checksum(self.workflow_file)

    def test_backup_creation_with_backup_flag(self):
        """Test backup files are created when --backup-state is enabled."""
        manager = StateManager(self.test_dir, backup_enabled=True)
        manager.initialize_run("workflow.yaml", self.workflow_file)

        # Update steps multiple times
        for i in range(5):
            step_name = f"Step{i}"
            manager.update_step(step_name, StepState(status="completed", exit_code=0))

        # Check that backup files exist (max 3)
        backup_files = list(manager.run_root.glob("state.json.step_*.bak"))
        assert len(backup_files) <= 3  # Should keep only last 3

        # Verify backups are valid JSON
        for backup_file in backup_files:
            with open(backup_file, 'r') as f:
                data = json.load(f)
                assert data["schema_version"] == "1.1.1"

    def test_state_includes_all_required_fields(self):
        """Test state file includes all required fields per schema."""
        manager = StateManager(self.test_dir)
        state = manager.initialize_run("workflow.yaml", self.workflow_file, context={"key": "value"})

        # Add various step states
        manager.update_step("TextStep", StepState(
            status="completed",
            exit_code=0,
            output="text output",
            truncated=False
        ))

        manager.update_step("JsonStep", StepState(
            status="completed",
            exit_code=0,
            json={"result": "data"},
            truncated=False
        ))

        manager.update_step("LinesStep", StepState(
            status="completed",
            exit_code=0,
            lines=["line1", "line2"],
            truncated=False
        ))

        # Load and verify structure
        with open(manager.state_file, 'r') as f:
            data = json.load(f)

        # Required top-level fields
        assert "schema_version" in data
        assert "run_id" in data
        assert "workflow_file" in data
        assert "workflow_checksum" in data
        assert "started_at" in data
        assert "updated_at" in data
        assert "status" in data
        assert "context" in data
        assert "steps" in data

        # Context preserved
        assert data["context"] == {"key": "value"}

        # Step structures
        assert data["steps"]["TextStep"]["output"] == "text output"
        assert data["steps"]["JsonStep"]["json"] == {"result": "data"}
        assert data["steps"]["LinesStep"]["lines"] == ["line1", "line2"]

    def test_repair_from_backup(self):
        """Test state repair from backup files."""
        manager = StateManager(self.test_dir, backup_enabled=True)
        manager.initialize_run("workflow.yaml", self.workflow_file)

        # Create some valid state with backups
        manager.update_step("Step1", StepState(status="completed", exit_code=0))
        manager.update_step("Step2", StepState(status="completed", exit_code=0))

        # Corrupt the main state file
        manager.state_file.write_text("corrupted invalid json{")

        # Attempt repair
        success = manager.repair_from_backup()
        assert success

        # Should be able to load repaired state
        state = manager.load_state()
        assert state.schema_version == "1.1.1"
        # Should have at least one of the steps from backup
        assert len(state.steps) > 0

    def test_for_each_state_tracking(self):
        """Test for_each loop state is properly tracked."""
        from orchestrator.state.run_state import ForEachState

        manager = StateManager(self.test_dir)
        state = manager.initialize_run("workflow.yaml", self.workflow_file)

        # Add for_each state
        loop_state = ForEachState(
            items=["file1.txt", "file2.txt", "file3.txt"],
            completed_indices=[0, 1],
            current_index=2
        )
        state.for_each["ProcessLoop"] = loop_state
        manager.save_state()

        # Load and verify
        with open(manager.state_file, 'r') as f:
            data = json.load(f)

        assert "for_each" in data
        assert data["for_each"]["ProcessLoop"]["items"] == ["file1.txt", "file2.txt", "file3.txt"]
        assert data["for_each"]["ProcessLoop"]["completed_indices"] == [0, 1]
        assert data["for_each"]["ProcessLoop"]["current_index"] == 2

    def test_loop_state_indexing(self):
        """Test loop results stored as steps.<LoopName>[i].<StepName>."""
        manager = StateManager(self.test_dir)
        manager.initialize_run("workflow.yaml", self.workflow_file)

        # Add loop iteration results
        manager.update_step("ProcessItems[0].Transform", StepState(
            status="completed",
            exit_code=0,
            output="item0 result"
        ))
        manager.update_step("ProcessItems[1].Transform", StepState(
            status="completed",
            exit_code=0,
            output="item1 result"
        ))

        # Verify structure
        with open(manager.state_file, 'r') as f:
            data = json.load(f)

        assert "ProcessItems[0].Transform" in data["steps"]
        assert "ProcessItems[1].Transform" in data["steps"]
        assert data["steps"]["ProcessItems[0].Transform"]["output"] == "item0 result"

    def test_state_timestamps(self):
        """Test started_at and updated_at timestamps are maintained."""
        manager = StateManager(self.test_dir)
        state = manager.initialize_run("workflow.yaml", self.workflow_file)

        started_at = state.started_at
        first_updated = state.updated_at

        # Timestamps should be set
        assert started_at
        assert first_updated
        # They should be very close but may have microsecond differences

        # Update state
        import time
        time.sleep(0.01)  # Ensure time difference
        manager.update_step("Step1", StepState(status="running"))

        # Load and check
        state = manager.load_state()
        assert state.started_at == started_at  # Should not change
        assert state.updated_at != first_updated  # Should be updated
        assert state.updated_at > first_updated  # Should be later

    def test_run_status_transitions(self):
        """Test run status transitions: running -> completed/failed."""
        manager = StateManager(self.test_dir)
        state = manager.initialize_run("workflow.yaml", self.workflow_file)

        # Initial status
        assert state.status == "running"

        # Update to completed
        manager.update_status("completed")
        state = manager.load_state()
        assert state.status == "completed"

        # Update to failed
        manager.update_status("failed")
        state = manager.load_state()
        assert state.status == "failed"


class TestStateFileHandler:
    """Tests for StateFileHandler atomic operations."""

    def setup_method(self):
        """Set up test directory."""
        self.test_dir = Path(tempfile.mkdtemp())

    def teardown_method(self):
        """Clean up test directory."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_atomic_write_creates_parent_dirs(self):
        """Test atomic_write creates parent directories if needed."""
        nested_path = self.test_dir / "deep" / "nested" / "state.json"
        data = {"test": "data"}

        StateFileHandler.atomic_write(nested_path, data)

        assert nested_path.exists()
        with open(nested_path, 'r') as f:
            loaded = json.load(f)
        assert loaded == data

    def test_atomic_write_cleans_up_on_failure(self):
        """Test temp file is cleaned up if write fails."""
        file_path = self.test_dir / "state.json"
        temp_path = file_path.with_suffix('.tmp')

        # Create a read-only directory to force write failure
        self.test_dir.chmod(0o555)

        try:
            with pytest.raises(PermissionError):
                StateFileHandler.atomic_write(file_path, {"test": "data"})

            # Temp file should not exist
            assert not temp_path.exists()
        finally:
            # Restore permissions for cleanup
            self.test_dir.chmod(0o755)

    def test_checksum_computation(self):
        """Test SHA256 checksum computation."""
        test_file = self.test_dir / "test.txt"
        test_file.write_text("test content")

        checksum = StateFileHandler.compute_checksum(test_file)

        assert checksum.startswith("sha256:")
        # Verify it's a valid SHA256 hex string (64 chars after prefix)
        hex_part = checksum[7:]  # Skip "sha256:"
        assert len(hex_part) == 64
        assert all(c in '0123456789abcdef' for c in hex_part)

    def test_find_latest_backup(self):
        """Test finding most recent backup file."""
        import time

        # Create backup files with different timestamps
        for i in range(3):
            backup = self.test_dir / f"state.json.step_{i}.bak"
            backup.write_text(f"backup {i}")
            time.sleep(0.01)  # Ensure different mtimes

        latest = StateFileHandler.find_latest_backup(self.test_dir)

        assert latest is not None
        assert latest.name == "state.json.step_2.bak"


def test_acceptance_at4_state_persistence():
    """AT-4: Write/read status.json with v1 schema.

    This test validates the complete state persistence cycle:
    1. Create run with proper schema version
    2. Write state atomically
    3. Read state back correctly
    4. Handle updates and backups
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        workflow_file = workspace / "workflow.yaml"
        workflow_file.write_text("version: '1.1.1'\nname: test\nsteps:\n  - name: Test")

        # Initialize run
        manager = StateManager(workspace, backup_enabled=True)
        state = manager.initialize_run("workflow.yaml", workflow_file)

        # Verify initial state
        assert state.schema_version == "1.1.1"
        assert state.status == "running"

        # Add step results
        manager.update_step("Test", StepState(
            status="completed",
            exit_code=0,
            output="Success",
            duration_ms=100
        ))

        # Complete run
        manager.update_status("completed")

        # Read back and verify
        manager2 = StateManager(workspace, run_id=manager.run_id)
        loaded_state = manager2.load_state()

        assert loaded_state.schema_version == "1.1.1"
        assert loaded_state.status == "completed"
        assert loaded_state.steps["Test"].status == "completed"
        assert loaded_state.steps["Test"].output == "Success"

        print("✓ AT-4: State persistence with v1.1.1 schema working correctly")