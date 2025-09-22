"""Tests for the CLI resume command (AT-4)."""

import json
import pytest
from pathlib import Path
import tempfile
import shutil
from unittest.mock import patch, MagicMock
import hashlib

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.state import StateManager
from orchestrator.loader import WorkflowLoader


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
name: Test Resume Workflow
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
def partial_run_state(temp_workspace, sample_workflow):
    """Create a partial run state with Step1 completed."""
    workflow_path, checksum = sample_workflow
    run_id = "test-run-123"

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


def test_at4_resume_nonexistent_run(temp_workspace):
    """Test resuming a run that doesn't exist."""
    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id="nonexistent-run",
            repair=False,
            force_restart=False
        )

    assert result == 1  # Should fail


def test_at4_resume_completed_run(temp_workspace, sample_workflow):
    """Test resuming a run that has already completed."""
    workflow_path, checksum = sample_workflow
    run_id = "completed-run"

    # Create completed state
    state_dir = temp_workspace / '.orchestrate' / 'runs' / run_id
    state_dir.mkdir(parents=True)

    state = {
        "schema_version": "1.1.1",
        "run_id": run_id,
        "workflow_file": str(workflow_path),
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "completed",
        "context": {},
        "steps": {
            "Step1": {"status": "completed", "exit_code": 0},
            "Step2": {"status": "completed", "exit_code": 0},
            "Step3": {"status": "completed", "exit_code": 0}
        }
    }

    (state_dir / "state.json").write_text(json.dumps(state, indent=2))

    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False
        )

    assert result == 0  # Should succeed immediately


def test_at4_resume_with_checksum_mismatch(temp_workspace, partial_run_state):
    """Test resume when workflow has been modified."""
    run_id, state_dir = partial_run_state

    # Modify the workflow file
    workflow_path = Path(json.loads((state_dir / "state.json").read_text())["workflow_file"])
    workflow_path.write_text("""
version: "1.1"
name: Modified Workflow
steps:
  - name: Step1
    command: ["echo", "Modified"]
""")

    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False
        )

    assert result == 1  # Should fail due to checksum mismatch


def test_at4_resume_force_restart(temp_workspace, partial_run_state):
    """Test force restart ignores existing state."""
    run_id, state_dir = partial_run_state

    # Mock the WorkflowExecutor to verify it starts fresh
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
            result = resume_workflow(
                run_id=run_id,
                repair=False,
                force_restart=True
            )

        # AT-68: Verify executor was called with resume=False for force_restart
        mock_executor.execute.assert_called_once()
        call_kwargs = mock_executor.execute.call_args.kwargs
        assert call_kwargs.get('resume') == False

    assert result == 0


def test_at4_resume_corrupted_state_with_repair(temp_workspace, sample_workflow):
    """Test repairing from backup when state is corrupted."""
    workflow_path, checksum = sample_workflow
    run_id = "corrupted-run"

    # Create state directory with backup
    state_dir = temp_workspace / '.orchestrate' / 'runs' / run_id
    state_dir.mkdir(parents=True)

    # Create valid backup
    valid_state = {
        "schema_version": "1.1.1",
        "run_id": run_id,
        "workflow_file": str(workflow_path),
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "suspended",
        "context": {},
        "steps": {
            "Step1": {"status": "completed", "exit_code": 0}
        }
    }

    backup_file = state_dir / "state.json.step_Step1.bak"
    backup_file.write_text(json.dumps(valid_state, indent=2))

    # Create corrupted state file
    (state_dir / "state.json").write_text("{ corrupted json")

    # Mock WorkflowExecutor
    with patch('orchestrator.cli.commands.resume.WorkflowExecutor') as MockExecutor:
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {
            'status': 'completed',
            'steps': {}
        }
        MockExecutor.return_value = mock_executor

        with patch('os.getcwd', return_value=str(temp_workspace)):
            result = resume_workflow(
                run_id=run_id,
                repair=True,
                force_restart=False
            )

    assert result == 0  # Should succeed after repair

    # Verify state was repaired
    state_content = json.loads((state_dir / "state.json").read_text())
    assert state_content["steps"]["Step1"]["status"] == "completed"


def test_at4_resume_partial_for_each_loop(temp_workspace):
    """Test resuming a partially completed for-each loop."""
    # Create workflow with for-each loop
    workflow_path = temp_workspace / "loop_workflow.yaml"
    workflow_content = """
version: "1.1"
name: Loop Workflow
steps:
  - name: GenerateList
    command: ["echo", "item1\\nitem2\\nitem3"]
    output_capture: lines
  - name: ProcessItems
    for_each:
      items_from: "steps.GenerateList.lines"
      steps:
        - name: ProcessItem
          command: ["echo", "Processing ${item}"]
          output_capture: text
"""
    workflow_path.write_text(workflow_content)
    checksum = f"sha256:{hashlib.sha256(workflow_content.encode()).hexdigest()}"

    run_id = "loop-run"
    state_dir = temp_workspace / '.orchestrate' / 'runs' / run_id
    state_dir.mkdir(parents=True)

    # Create state with partial loop completion
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
            "GenerateList": {
                "status": "completed",
                "exit_code": 0,
                "lines": ["item1", "item2", "item3"]
            },
            "ProcessItems[0].ProcessItem": {
                "status": "completed",
                "exit_code": 0,
                "output": "Processing item1"
            }
            # item2 and item3 not yet processed
        }
    }

    (state_dir / "state.json").write_text(json.dumps(state, indent=2))

    # Mock WorkflowExecutor
    with patch('orchestrator.cli.commands.resume.WorkflowExecutor') as MockExecutor:
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {
            'status': 'completed',
            'steps': {
                'GenerateList': {'status': 'completed'},
                'ProcessItems': [
                    {'status': 'completed'},
                    {'status': 'completed'},
                    {'status': 'completed'}
                ]
            }
        }
        MockExecutor.return_value = mock_executor

        with patch('os.getcwd', return_value=str(temp_workspace)):
            result = resume_workflow(
                run_id=run_id,
                repair=False,
                force_restart=False
            )

        # Verify executor was called with resume=True
        assert mock_executor.execute.call_args.kwargs.get('resume') == True

    assert result == 0


def test_at4_resume_with_retry_parameters(temp_workspace, partial_run_state):
    """Test resume with custom retry parameters."""
    run_id, state_dir = partial_run_state

    # Mock WorkflowExecutor
    with patch('orchestrator.cli.commands.resume.WorkflowExecutor') as MockExecutor:
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {
            'status': 'completed',
            'steps': {}
        }
        MockExecutor.return_value = mock_executor

        with patch('os.getcwd', return_value=str(temp_workspace)):
            result = resume_workflow(
                run_id=run_id,
                repair=False,
                force_restart=False,
                max_retries=5,
                retry_delay_ms=2000
            )

        # Verify executor was initialized with retry parameters
        MockExecutor.assert_called_once()
        call_kwargs = MockExecutor.call_args.kwargs
        assert call_kwargs.get('max_retries') == 5
        assert call_kwargs.get('retry_delay_ms') == 2000

    assert result == 0


def test_at4_resume_displays_progress_information(temp_workspace, partial_run_state, capsys):
    """Test that resume command displays progress information."""
    run_id, state_dir = partial_run_state

    # Add more steps to state
    state = json.loads((state_dir / "state.json").read_text())
    state["steps"]["Step2"] = {"status": "failed", "exit_code": 1}
    (state_dir / "state.json").write_text(json.dumps(state, indent=2))

    # Mock WorkflowExecutor
    with patch('orchestrator.cli.commands.resume.WorkflowExecutor') as MockExecutor:
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {
            'status': 'completed',
            'steps': {}
        }
        MockExecutor.return_value = mock_executor

        with patch('os.getcwd', return_value=str(temp_workspace)):
            resume_workflow(
                run_id=run_id,
                repair=False,
                force_restart=False
            )

    captured = capsys.readouterr()
    assert "Resuming run test-run-123" in captured.out
    assert "Completed steps: Step1" in captured.out
    assert "Pending steps: Step2" in captured.out