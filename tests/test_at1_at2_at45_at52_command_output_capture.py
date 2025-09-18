#!/usr/bin/env python3
"""
Test for AT-1, AT-2, AT-45, AT-52: Command output_capture mode conversion.

Tests that command steps properly convert output_capture string values
('text', 'lines', 'json') to CaptureMode enum values before passing to StepExecutor.
"""

import tempfile
import yaml
import pytest
from pathlib import Path

from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.state import StateManager


class TestCommandOutputCaptureConversion:
    """Test command output_capture string to enum conversion."""

    def test_at1_at2_at45_at52_command_text_mode(self):
        """Test command step with output_capture: 'text' converts properly."""
        workflow_content = {
            'version': '1.1',
            'name': 'test-text-mode',
            'steps': [
                {
                    'name': 'TextMode',
                    'command': 'echo "test text output"',
                    'output_capture': 'text'
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            # Write workflow file
            workflow_file = workspace / "workflow.yaml"
            with open(workflow_file, 'w') as f:
                yaml.dump(workflow_content, f)

            # Load and execute workflow
            loader = WorkflowLoader(workspace)
            workflow = loader.load(workflow_file)

            state_manager = StateManager(workspace=workspace, run_id='test-run')
            state_manager.initialize('workflow.yaml', {'test': 'data'})

            executor = WorkflowExecutor(workflow, workspace, state_manager)
            executor.execute()

            # Verify step completed successfully
            final_state = state_manager.load()
            assert 'TextMode' in final_state.steps
            step_result = final_state.steps['TextMode']
            assert step_result['status'] == 'completed'
            assert step_result['exit_code'] == 0
            assert 'test text output' in step_result['output']

    def test_at1_at2_at45_at52_command_lines_mode(self):
        """Test command step with output_capture: 'lines' converts properly."""
        workflow_content = {
            'version': '1.1',
            'name': 'test-lines-mode',
            'steps': [
                {
                    'name': 'LinesMode',
                    'command': ['sh', '-c', 'echo "line1"; echo "line2"; echo "line3"'],
                    'output_capture': 'lines'
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            # Write workflow file
            workflow_file = workspace / "workflow.yaml"
            with open(workflow_file, 'w') as f:
                yaml.dump(workflow_content, f)

            # Load and execute workflow
            loader = WorkflowLoader(workspace)
            workflow = loader.load(workflow_file)

            state_manager = StateManager(workspace=workspace, run_id='test-run')
            state_manager.initialize('workflow.yaml', {'test': 'data'})

            executor = WorkflowExecutor(workflow, workspace, state_manager)
            executor.execute()

            # Verify step completed successfully
            final_state = state_manager.load()
            assert 'LinesMode' in final_state.steps
            step_result = final_state.steps['LinesMode']
            assert step_result['status'] == 'completed'
            assert step_result['exit_code'] == 0
            # Lines mode should return a list in 'lines' key
            assert 'lines' in step_result
            assert isinstance(step_result['lines'], list)
            assert len(step_result['lines']) == 3
            assert step_result['lines'] == ['line1', 'line2', 'line3']

    def test_at1_at2_at45_at52_command_json_mode(self):
        """Test command step with output_capture: 'json' converts properly."""
        workflow_content = {
            'version': '1.1',
            'name': 'test-json-mode',
            'steps': [
                {
                    'name': 'JsonMode',
                    'command': ['sh', '-c', 'echo \'{"key": "value", "number": 42}\''],
                    'output_capture': 'json'
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            # Write workflow file
            workflow_file = workspace / "workflow.yaml"
            with open(workflow_file, 'w') as f:
                yaml.dump(workflow_content, f)

            # Load and execute workflow
            loader = WorkflowLoader(workspace)
            workflow = loader.load(workflow_file)

            state_manager = StateManager(workspace=workspace, run_id='test-run')
            state_manager.initialize('workflow.yaml', {'test': 'data'})

            executor = WorkflowExecutor(workflow, workspace, state_manager)
            executor.execute()

            # Verify step completed successfully
            final_state = state_manager.load()
            assert 'JsonMode' in final_state.steps
            step_result = final_state.steps['JsonMode']
            assert step_result['status'] == 'completed'
            assert step_result['exit_code'] == 0
            # JSON mode should return parsed object in 'json' key
            assert 'json' in step_result
            assert isinstance(step_result['json'], dict)
            assert step_result['json']['key'] == 'value'
            assert step_result['json']['number'] == 42

    def test_at1_at2_at45_at52_command_default_text_mode(self):
        """Test command step with no output_capture defaults to text mode."""
        workflow_content = {
            'version': '1.1',
            'name': 'test-default-mode',
            'steps': [
                {
                    'name': 'DefaultMode',
                    'command': 'echo "default mode test"'
                    # No output_capture specified, should default to 'text'
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            # Write workflow file
            workflow_file = workspace / "workflow.yaml"
            with open(workflow_file, 'w') as f:
                yaml.dump(workflow_content, f)

            # Load and execute workflow
            loader = WorkflowLoader(workspace)
            workflow = loader.load(workflow_file)

            state_manager = StateManager(workspace=workspace, run_id='test-run')
            state_manager.initialize('workflow.yaml', {'test': 'data'})

            executor = WorkflowExecutor(workflow, workspace, state_manager)
            executor.execute()

            # Verify step completed successfully with text mode behavior
            final_state = state_manager.load()
            assert 'DefaultMode' in final_state.steps
            step_result = final_state.steps['DefaultMode']
            assert step_result['status'] == 'completed'
            assert step_result['exit_code'] == 0
            assert 'default mode test' in step_result['output']
            # Should be string (text mode), not list (lines mode) or dict (json mode)
            assert isinstance(step_result['output'], str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])