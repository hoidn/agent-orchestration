"""Tests for State Manager (AT-4)."""

import pytest
import tempfile
import shutil
from pathlib import Path

from orchestrator.state import StateManager
from tests.historical_state import write_historical_state


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

    def test_custom_state_dir_overrides_default_runs_root(self, temp_workspace, workflow_file):
        """Custom state-dir roots should store runs outside WORKSPACE/.orchestrate."""
        custom_state_dir = temp_workspace / "external-runs"
        manager = StateManager(temp_workspace, state_dir=custom_state_dir, run_id="custom-run")

        state = write_historical_state(manager, workflow_file)

        expected_state_file = custom_state_dir / "custom-run" / "state.json"
        default_state_file = temp_workspace / ".orchestrate" / "runs" / "custom-run" / "state.json"

        assert state.run_root == str(custom_state_dir / "custom-run")
        assert expected_state_file.exists()
        assert not default_state_file.exists()

        manager2 = StateManager(temp_workspace, state_dir=custom_state_dir, run_id="custom-run")
        loaded_state = manager2.load()
        assert loaded_state.run_root == str(custom_state_dir / "custom-run")

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

