"""Tests for AT-69: Debug backups functionality.

AT-69: --debug produces state.json.step_<Step>.bak backups with rotation (keep last 3)
"""

import json
import pytest
from pathlib import Path
import tempfile
import time

from orchestrator.state import StateManager, RunState, StepResult
from orchestrator.workflow.executor import WorkflowExecutor


def test_at69_debug_enables_backups():
    """Test that debug flag enables state backups."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # Create state manager with debug=True (should enable backups)
        manager = StateManager(workspace, debug=True)

        # Initialize state
        workflow_file = workspace / "test.yaml"
        workflow_file.write_text("steps: []")
        manager.initialize("test.yaml")

        # Create backups for multiple steps
        manager.backup_state("Step1")
        manager.backup_state("Step2")
        manager.backup_state("Step3")

        # Check that backup files exist
        backup_dir = manager.run_root
        backups = list(backup_dir.glob("state.json.step_*.bak"))
        assert len(backups) == 3

        # Verify backup filenames
        backup_names = [b.name for b in backups]
        assert "state.json.step_Step1.bak" in backup_names
        assert "state.json.step_Step2.bak" in backup_names
        assert "state.json.step_Step3.bak" in backup_names


def test_at69_backup_rotation():
    """Test that only last 3 backups are kept (rotation)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # Create state manager with debug=True
        manager = StateManager(workspace, debug=True)

        # Initialize state
        workflow_file = workspace / "test.yaml"
        workflow_file.write_text("steps: []")
        manager.initialize("test.yaml")

        # Create more than 3 backups
        for i in range(5):
            manager.backup_state(f"Step{i}")
            # Small delay to ensure different timestamps
            time.sleep(0.01)

        # Check that only last 3 backups exist
        backup_dir = manager.run_root
        backups = sorted(backup_dir.glob("state.json.step_*.bak"))
        assert len(backups) == 3

        # Verify these are the last 3 steps
        backup_names = [b.name for b in backups]
        assert "state.json.step_Step2.bak" in backup_names
        assert "state.json.step_Step3.bak" in backup_names
        assert "state.json.step_Step4.bak" in backup_names

        # Old backups should be deleted
        assert "state.json.step_Step0.bak" not in backup_names
        assert "state.json.step_Step1.bak" not in backup_names


def test_at69_workflow_executor_creates_backups():
    """Test that WorkflowExecutor creates backups when debug=True."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # Create workflow file
        workflow = {
            'version': '1.1',
            'steps': [
                {'name': 'Step1', 'command': 'echo hello'},
                {'name': 'Step2', 'command': 'echo world'}
            ]
        }
        workflow_file = workspace / "workflow.yaml"
        import yaml
        with open(workflow_file, 'w') as f:
            yaml.dump(workflow, f)

        # Create state manager with debug=True
        state_manager = StateManager(workspace, debug=True)
        state_manager.initialize("workflow.yaml")

        # Create executor with debug=True
        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=workspace,
            state_manager=state_manager,
            debug=True  # Enable debug mode
        )

        # Execute workflow
        result = executor.execute()

        # Check that backups were created for each step
        backup_dir = state_manager.run_root
        backups = list(backup_dir.glob("state.json.step_*.bak"))
        backup_names = [b.name for b in backups]

        # Should have backups for both steps
        assert "state.json.step_Step1.bak" in backup_names
        assert "state.json.step_Step2.bak" in backup_names


def test_at69_for_each_loop_backups():
    """Test that backups are created for steps within for_each loops."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # Create workflow with for_each loop
        workflow = {
            'version': '1.1',
            'steps': [
                {
                    'name': 'ProcessItems',
                    'for_each': {
                        'items': ['item1', 'item2'],
                        'steps': [
                            {'name': 'Process', 'command': 'echo ${item}'}
                        ]
                    }
                }
            ]
        }
        workflow_file = workspace / "workflow.yaml"
        import yaml
        with open(workflow_file, 'w') as f:
            yaml.dump(workflow, f)

        # Create state manager with debug=True
        state_manager = StateManager(workspace, debug=True)
        state_manager.initialize("workflow.yaml")

        # Create executor with debug=True
        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=workspace,
            state_manager=state_manager,
            debug=True
        )

        # Execute workflow
        result = executor.execute()

        # Check that backups were created for loop steps
        backup_dir = state_manager.run_root
        backups = list(backup_dir.glob("state.json.step_*.bak"))
        backup_names = [b.name for b in backups]

        # Should have backup for main loop step
        assert "state.json.step_ProcessItems.bak" in backup_names
        # Should have backups for nested steps with iteration index
        assert "state.json.step_ProcessItems[0].Process.bak" in backup_names
        assert "state.json.step_ProcessItems[1].Process.bak" in backup_names


def test_at69_backup_content_validity():
    """Test that backup files contain valid state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # Create state manager with debug=True
        manager = StateManager(workspace, debug=True)

        # Initialize state
        workflow_file = workspace / "test.yaml"
        workflow_file.write_text("steps: []")
        manager.initialize("test.yaml")

        # Add a step result
        step_result = StepResult(
            status='completed',
            exit_code=0,
            output='test output'
        )
        manager.update_step('TestStep', step_result)

        # Create backup
        manager.backup_state("NextStep")

        # Read backup file
        backup_file = manager.run_root / "state.json.step_NextStep.bak"
        assert backup_file.exists()

        with open(backup_file, 'r') as f:
            backup_data = json.load(f)

        # Verify backup contains the step result
        assert 'steps' in backup_data
        assert 'TestStep' in backup_data['steps']
        assert backup_data['steps']['TestStep']['exit_code'] == 0
        assert backup_data['steps']['TestStep']['output'] == 'test output'


def test_at69_debug_false_no_backups():
    """Test that backups are NOT created when debug=False."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # Create state manager with debug=False
        manager = StateManager(workspace, debug=False, backup_enabled=False)

        # Initialize state
        workflow_file = workspace / "test.yaml"
        workflow_file.write_text("steps: []")
        manager.initialize("test.yaml")

        # Try to create backup (should be skipped)
        manager.backup_state("Step1")

        # Check that no backup files exist
        backup_dir = manager.run_root
        backups = list(backup_dir.glob("state.json.step_*.bak"))
        assert len(backups) == 0