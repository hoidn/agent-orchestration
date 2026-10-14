"""
Test for AT-64: ${run.root} variable support.

AT-64: ${run.root} variable resolves to .orchestrate/runs/<run_id> and is usable in paths/commands.
"""

import json

from tests.historical_state import write_historical_state
from orchestrator.state import StateManager


def test_at64_run_root_persists_in_state(tmp_path):
    """Test that run_root is persisted in state.json and survives reload."""

    workflow_yaml = r"""
{
  "version": "1.1",
  "steps": [
    {
      "name": "SimpleStep",
      "command": [
        "echo",
        "test"
      ]
    }
  ]
}
"""

    # Write workflow to temp file
    workflow_file = tmp_path / "workflow.yaml"
    workflow_file.write_text(workflow_yaml)

    # Create state manager
    run_id = "persist_test"
    state_manager1 = StateManager(tmp_path, run_id=run_id, backup_enabled=False)
    write_historical_state(state_manager1, str(workflow_file))

    expected_run_root = str(tmp_path / ".orchestrate" / "runs" / run_id)

    # Verify run_root in initial state
    state1 = state_manager1.load()
    assert state1.run_root == expected_run_root

    # Read state.json directly
    state_file = tmp_path / ".orchestrate" / "runs" / run_id / "state.json"
    with open(state_file, 'r') as f:
        state_data = json.load(f)

    assert "run_root" in state_data
    assert state_data["run_root"] == expected_run_root

    # Create new state manager and load existing state
    state_manager2 = StateManager(tmp_path, run_id=run_id, backup_enabled=False)
    state2 = state_manager2.load()

    # Verify run_root persisted correctly
    assert state2.run_root == expected_run_root
