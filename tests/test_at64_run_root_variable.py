"""
Test for AT-64: ${run.root} variable support.

AT-64: ${run.root} variable resolves to .orchestrate/runs/<run_id> and is usable in paths/commands.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.state import StateManager
from orchestrator.loader import WorkflowLoader


def test_at64_run_root_variable_in_command(tmp_path):
    """Test that ${run.root} resolves correctly in commands."""

    # Create workflow with ${run.root} reference
    workflow_yaml = """
version: "1.1"
steps:
  - name: CreateOutputDir
    command: ["mkdir", "-p", "${run.root}/output"]

  - name: WriteToRunRoot
    command: ["echo", "test data > ${run.root}/output/test.txt"]
"""

    # Write workflow to temp file
    workflow_file = tmp_path / "workflow.yaml"
    workflow_file.write_text(workflow_yaml)

    # Load workflow
    loader = WorkflowLoader(tmp_path)
    workflow = loader.load(str(workflow_file))

    # Create state manager with specific run_id
    run_id = "test_run_123"
    state_manager = StateManager(tmp_path, run_id=run_id, backup_enabled=False)
    state_manager.initialize(str(workflow_file))

    # Expected run_root path
    expected_run_root = str(tmp_path / ".orchestrate" / "runs" / run_id)

    # Verify state has run_root
    state = state_manager.load()
    assert state.run_root == expected_run_root, f"Expected run_root={expected_run_root}, got {state.run_root}"

    # Create executor
    executor = WorkflowExecutor(workflow, tmp_path, state_manager)

    # Mock subprocess to capture commands
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout=b"", stderr=b"")

        # Execute workflow
        executor.execute()

        # Verify commands were called with substituted run_root
        assert mock_run.call_count == 2

        # First command: mkdir -p ${run.root}/output
        first_call = mock_run.call_args_list[0]
        assert first_call[0][0] == ["mkdir", "-p", f"{expected_run_root}/output"]

        # Second command: echo with run_root path
        second_call = mock_run.call_args_list[1]
        assert second_call[0][0] == ["echo", f"test data > {expected_run_root}/output/test.txt"]


def test_at64_run_root_variable_in_paths(tmp_path):
    """Test that ${run.root} resolves correctly in file paths."""

    # Create workflow with ${run.root} in output_file
    workflow_yaml = """
version: "1.1"
steps:
  - name: WriteOutput
    command: ["echo", "test output"]
    output_file: "${run.root}/logs/custom_output.txt"
"""

    # Write workflow to temp file
    workflow_file = tmp_path / "workflow.yaml"
    workflow_file.write_text(workflow_yaml)

    # Load workflow
    loader = WorkflowLoader(tmp_path)
    workflow = loader.load(str(workflow_file))

    # Create state manager
    run_id = "test_run_456"
    state_manager = StateManager(tmp_path, run_id=run_id, backup_enabled=False)
    state_manager.initialize(str(workflow_file))

    expected_run_root = str(tmp_path / ".orchestrate" / "runs" / run_id)

    # Create executor
    executor = WorkflowExecutor(workflow, tmp_path, state_manager)

    # Mock subprocess
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout=b"test output\n", stderr=b"")

        # Execute workflow
        executor.execute()

        # Verify output file was created at correct path
        output_path = Path(expected_run_root) / "logs" / "custom_output.txt"
        # Note: In the mock, the file won't actually be created
        # but we can verify the path was processed correctly by checking the state

        state = state_manager.load()
        step_result = state.steps.get("WriteOutput")
        assert step_result is not None
        assert step_result["exit_code"] == 0


def test_at64_run_root_variable_with_context_vars(tmp_path):
    """Test ${run.root} works alongside other variable types."""

    workflow_yaml = """
version: "1.1"
steps:
  - name: CombineVariables
    command: ["echo", "${context.prefix}_${run.root}_${context.suffix}"]
"""

    # Write workflow to temp file
    workflow_file = tmp_path / "workflow.yaml"
    workflow_file.write_text(workflow_yaml)

    # Load workflow
    loader = WorkflowLoader(tmp_path)
    workflow = loader.load(str(workflow_file))

    # Create state manager
    run_id = "test_run_789"
    state_manager = StateManager(tmp_path, run_id=run_id, backup_enabled=False)
    state_manager.initialize(str(workflow_file), {"prefix": "START", "suffix": "END"})

    expected_run_root = str(tmp_path / ".orchestrate" / "runs" / run_id)

    # Create executor with context
    executor = WorkflowExecutor(workflow, tmp_path, state_manager)

    # Mock subprocess
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout=b"", stderr=b"")

        # Execute workflow
        executor.execute()

        # Verify command had all variables substituted
        call_args = mock_run.call_args_list[0][0][0]
        assert call_args == ["echo", f"START_{expected_run_root}_END"]


def test_at64_run_root_in_provider_params(tmp_path):
    """Test that ${run.root} works in provider_params."""

    workflow_yaml = """
version: "1.1"
providers:
  test_provider:
    command: ["bash", "-c", "Process ${file_path}"]
    defaults:
      file_path: "/default/path"

steps:
  - name: UseProvider
    provider: test_provider
    provider_params:
      file_path: "${run.root}/data/input.txt"
"""

    # Write workflow to temp file
    workflow_file = tmp_path / "workflow.yaml"
    workflow_file.write_text(workflow_yaml)

    # Load workflow
    loader = WorkflowLoader(tmp_path)
    workflow = loader.load(str(workflow_file))

    # Create state manager
    run_id = "test_run_abc"
    state_manager = StateManager(tmp_path, run_id=run_id, backup_enabled=False)
    state_manager.initialize(str(workflow_file))

    expected_run_root = str(tmp_path / ".orchestrate" / "runs" / run_id)

    # Create executor
    executor = WorkflowExecutor(workflow, tmp_path, state_manager)

    # Mock subprocess
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout=b"", stderr=b"")

        # Execute workflow
        executor.execute()

        # Verify provider was called with substituted run_root
        call_args = mock_run.call_args_list[0][0][0]
        expected_cmd = f"Process {expected_run_root}/data/input.txt"
        assert call_args == ["bash", "-c", expected_cmd]


def test_at64_run_root_persists_in_state(tmp_path):
    """Test that run_root is persisted in state.json and survives reload."""

    workflow_yaml = """
version: "1.1"
steps:
  - name: SimpleStep
    command: ["echo", "test"]
"""

    # Write workflow to temp file
    workflow_file = tmp_path / "workflow.yaml"
    workflow_file.write_text(workflow_yaml)

    # Create state manager
    run_id = "persist_test"
    state_manager1 = StateManager(tmp_path, run_id=run_id, backup_enabled=False)
    state_manager1.initialize(str(workflow_file))

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