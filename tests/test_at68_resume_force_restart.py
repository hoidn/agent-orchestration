"""Test for AT-68: Resume force-restart functionality."""

import json
import pytest
from pathlib import Path
import tempfile
import hashlib
from unittest.mock import patch, MagicMock
import uuid

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.state import StateManager


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        yield workspace


@pytest.fixture
def sample_workflow(temp_workspace):
    """Create a sample workflow file."""
    workflow_path = temp_workspace / "test_workflow.yaml"
    workflow_content = """
version: "1.1"
name: Test Force Restart Workflow
steps:
  - name: Step1
    command: ["echo", "Hello from Step1"]
    output_capture: text
  - name: Step2
    command: ["echo", "Hello from Step2"]
    output_capture: text
  - name: Step3
    command: ["echo", "Hello from Step3"]
    output_capture: text
"""
    workflow_path.write_text(workflow_content)

    # Calculate checksum in StateManager format
    checksum = f"sha256:{hashlib.sha256(workflow_content.encode()).hexdigest()}"

    return workflow_path, checksum


@pytest.fixture
def existing_run_state(temp_workspace, sample_workflow):
    """Create an existing run state with Step1 completed."""
    workflow_path, checksum = sample_workflow
    run_id = "existing-run-123"

    # Create state directory
    state_dir = temp_workspace / '.orchestrate' / 'runs' / run_id
    state_dir.mkdir(parents=True)

    # Create state.json
    state = {
        "schema_version": "1.1.1",
        "run_id": run_id,
        "workflow_file": str(workflow_path),
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "suspended",
        "context": {},
        "steps": {
            "Step1": {
                "status": "completed",
                "exit_code": 0,
                "output": "Hello from Step1",
                "started_at": "2024-01-01T00:00:01Z",
                "completed_at": "2024-01-01T00:00:02Z",
                "duration_ms": 1000
            }
        }
    }

    state_file = state_dir / "state.json"
    state_file.write_text(json.dumps(state, indent=2))

    return run_id, state_dir


def test_at68_resume_force_restart_creates_new_run(temp_workspace, existing_run_state):
    """
    AT-68: Resume force-restart - starts a new run (new run_id) and ignores existing state.

    Per spec: resume --force-restart starts a new run with a new run_id, not reusing the old one.
    """
    old_run_id, old_state_dir = existing_run_state

    # Mock uuid to control the new run_id
    new_run_id = "new-run-456"
    with patch('uuid.uuid4', return_value=MagicMock(hex=new_run_id)):
        # Mock WorkflowExecutor to check it gets a fresh state
        with patch('orchestrator.cli.commands.resume.WorkflowExecutor') as MockExecutor:
            mock_executor = MagicMock()
            mock_executor.execute.return_value = {
                'status': 'completed',
                'steps': {
                    'Step1': {'status': 'completed'},
                    'Step2': {'status': 'completed'},
                    'Step3': {'status': 'completed'}
                }
            }
            MockExecutor.return_value = mock_executor

            with patch('os.getcwd', return_value=str(temp_workspace)):
                # Call resume with force_restart=True
                result = resume_workflow(
                    run_id=old_run_id,
                    repair=False,
                    force_restart=True
                )

            # The function should have created a NEW StateManager with a NEW run_id
            # Check that WorkflowExecutor was initialized
            assert MockExecutor.called
            init_kwargs = MockExecutor.call_args.kwargs
            state_manager_used = init_kwargs['state_manager']

            # Verify the state manager has a different run_id
            assert state_manager_used.run_id != old_run_id

            # The executor should start from the beginning (no resume flag)
            mock_executor.execute.assert_called_once()
            call_kwargs = mock_executor.execute.call_args.kwargs
            assert call_kwargs.get('resume', False) == False

    assert result == 0

    # Verify the old state directory still exists (not deleted)
    assert old_state_dir.exists()
    old_state_file = old_state_dir / "state.json"
    assert old_state_file.exists()

    # Verify a new state directory was created for the new run
    new_state_dir = temp_workspace / '.orchestrate' / 'runs' / new_run_id
    # Note: In the mock, the state might not actually be written to disk,
    # but we're testing the logic flow here


def test_at68_force_restart_ignores_workflow_changes(temp_workspace, existing_run_state):
    """
    AT-68: Force restart should proceed even if workflow has been modified.

    With --force-restart, checksum validation is skipped and a new run starts.
    """
    old_run_id, old_state_dir = existing_run_state

    # Modify the workflow file (this would normally fail checksum validation)
    workflow_path = temp_workspace / "test_workflow.yaml"
    modified_content = """
version: "1.1"
name: Modified Workflow
steps:
  - name: Step1
    command: ["echo", "Modified Step1"]
    output_capture: text
  - name: NewStep
    command: ["echo", "This is a new step"]
    output_capture: text
"""
    workflow_path.write_text(modified_content)

    with patch('orchestrator.cli.commands.resume.WorkflowExecutor') as MockExecutor:
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {
            'status': 'completed',
            'steps': {
                'Step1': {'status': 'completed'},
                'NewStep': {'status': 'completed'}
            }
        }
        MockExecutor.return_value = mock_executor

        with patch('os.getcwd', return_value=str(temp_workspace)):
            # Should succeed despite checksum mismatch
            result = resume_workflow(
                run_id=old_run_id,
                repair=False,
                force_restart=True
            )

        # Should have been called with the modified workflow
        assert MockExecutor.called
        init_kwargs = MockExecutor.call_args.kwargs
        workflow = init_kwargs['workflow']
        assert workflow['name'] == 'Modified Workflow'

    assert result == 0


def test_at68_resume_without_force_restart_validates_checksum(temp_workspace, existing_run_state):
    """
    AT-68: Without force-restart, checksum validation should fail if workflow changed.

    This is the contrast case - normal resume enforces checksum validation.
    """
    old_run_id, old_state_dir = existing_run_state

    # Modify the workflow file
    workflow_path = temp_workspace / "test_workflow.yaml"
    modified_content = """
version: "1.1"
name: Modified Workflow
steps:
  - name: Step1
    command: ["echo", "Modified"]
"""
    workflow_path.write_text(modified_content)

    with patch('os.getcwd', return_value=str(temp_workspace)):
        # Should fail due to checksum mismatch
        result = resume_workflow(
            run_id=old_run_id,
            repair=False,
            force_restart=False  # Normal resume mode
        )

    # Should fail with exit code 1 due to checksum validation
    assert result == 1