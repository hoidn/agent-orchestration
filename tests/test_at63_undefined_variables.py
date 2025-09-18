"""
Test for AT-63: Undefined variable in commands.
Verifies that referencing undefined ${run|context|steps|loop.*} yields exit 2
with error.context.undefined_vars and no process execution.
"""

import pytest
import tempfile
from pathlib import Path
import json

from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager


def test_at63_undefined_variable_in_command():
    """Test AT-63: Undefined variable detection prevents execution."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()

        # Create workflow with undefined variable reference
        workflow_path = workspace / "workflow.yaml"
        workflow_content = """
version: "1.1"
steps:
  - name: UseUndefined
    command: echo "Value is ${context.undefined_key}"
"""
        workflow_path.write_text(workflow_content)

        # Load and validate workflow
        loader = WorkflowLoader(workspace)
        workflow = loader.load(workflow_path)

        # Setup state manager
        state_dir = workspace / ".orchestrate/runs/test"
        state_dir.mkdir(parents=True)
        state_manager = StateManager(state_dir)

        # Create initial state with context
        state_manager.initialize(
            str(workflow_path),
            context={'defined_key': 'value1'}  # Note: undefined_key is NOT here
        )

        # Execute workflow
        executor = WorkflowExecutor(workflow, workspace, state_manager)
        result = executor.execute()
        print(f"Execute result type: {type(result)}")
        if isinstance(result, dict) and 'steps' in result:
            print(f"Result steps: {result['steps']}")

        # Verify execution failed with exit code 2
        state = state_manager.load()
        print(f"Steps in state: {list(state.steps.keys())}")
        print(f"Full state.steps: {state.steps}")
        assert 'UseUndefined' in state.steps, f"Step 'UseUndefined' not found in state. Available: {list(state.steps.keys())}"
        assert state.steps['UseUndefined']['exit_code'] == 2

        # Verify error context contains undefined_vars (AT-63 requirement)
        error = state.steps['UseUndefined'].get('error', {})
        assert error['type'] == 'undefined_variables'
        assert 'context.undefined_key' in error['message']

        # Most importantly: verify undefined_vars is in error context
        assert 'undefined_vars' in error['context']
        assert 'context.undefined_key' in error['context']['undefined_vars']

        # Verify substituted_command is present for debugging
        assert 'substituted_command' in error['context']
        assert 'echo "Value is ${context.undefined_key}"' in error['context']['substituted_command'][0]


def test_at63_undefined_variable_in_list_command():
    """Test AT-63: Undefined variables in list commands."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()

        # Create workflow with list command containing undefined variable
        workflow_path = workspace / "workflow.yaml"
        workflow_content = """
version: "1.1"
steps:
  - name: ListCommand
    command: ["echo", "Step ${steps.PreviousStep.exit_code} completed"]
"""
        workflow_path.write_text(workflow_content)

        loader = WorkflowLoader(workspace)
        workflow = loader.load(workflow_path)

        # Setup state manager
        state_dir = workspace / ".orchestrate/runs/test"
        state_dir.mkdir(parents=True)
        state_manager = StateManager(state_dir)

        # Create initial state (no PreviousStep exists)
        state_manager.initialize(
            str(workflow_path),
            context={}
        )

        # Execute workflow
        executor = WorkflowExecutor(workflow, workspace, state_manager)
        result = executor.execute()

        # Verify execution failed with exit code 2
        state = state_manager.load()
        assert state.steps['ListCommand']['exit_code'] == 2

        # Verify error context
        error = state.steps['ListCommand'].get('error', {})
        assert error['type'] == 'undefined_variables'
        assert 'undefined_vars' in error['context']
        assert 'steps.PreviousStep.exit_code' in error['context']['undefined_vars']


def test_at63_multiple_undefined_variables():
    """Test AT-63: Multiple undefined variables are all reported."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()

        # Create workflow with multiple undefined variables
        workflow_path = workspace / "workflow.yaml"
        workflow_content = """
version: "1.1"
steps:
  - name: MultipleUndefined
    command: "process ${run.missing} --input ${context.absent} --loop ${loop.index}"
"""
        workflow_path.write_text(workflow_content)

        loader = WorkflowLoader(workspace)
        workflow = loader.load(workflow_path)

        # Setup state manager
        state_dir = workspace / ".orchestrate/runs/test"
        state_dir.mkdir(parents=True)
        state_manager = StateManager(state_dir)

        # Create initial state
        state_manager.initialize(
            str(workflow_path),
            context={'present': 'value'}
        )

        # Execute workflow
        executor = WorkflowExecutor(workflow, workspace, state_manager)
        result = executor.execute()

        # Verify execution failed
        state = state_manager.load()
        assert state.steps['MultipleUndefined']['exit_code'] == 2

        # Verify all undefined variables are reported
        error = state.steps['MultipleUndefined'].get('error', {})
        assert 'undefined_vars' in error['context']
        undefined = error['context']['undefined_vars']

        # Should report all three undefined variables
        assert 'run.missing' in undefined
        assert 'context.absent' in undefined
        assert 'loop.index' in undefined  # Not in a loop, so this is undefined


def test_at63_defined_variables_execute_normally():
    """Test that commands with all variables defined execute normally."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()

        # Create workflow with all variables defined
        workflow_path = workspace / "workflow.yaml"
        workflow_content = """
version: "1.1"
steps:
  - name: FirstStep
    command: echo "Starting"
  - name: SecondStep
    command: echo "First step exit code was ${steps.FirstStep.exit_code}"
"""
        workflow_path.write_text(workflow_content)

        loader = WorkflowLoader(workspace)
        workflow = loader.load(workflow_path)

        # Setup state manager
        state_dir = workspace / ".orchestrate/runs/test"
        state_dir.mkdir(parents=True)
        state_manager = StateManager(state_dir)

        # Create initial state
        state_manager.initialize(
            str(workflow_path),
            context={}
        )

        # Execute workflow
        executor = WorkflowExecutor(workflow, workspace, state_manager)
        result = executor.execute()

        # Verify both steps executed successfully
        state = state_manager.load()
        assert state.steps['FirstStep']['exit_code'] == 0
        assert state.steps['SecondStep']['exit_code'] == 0

        # Second step should have the substituted value in output
        assert 'First step exit code was 0' in state.steps['SecondStep']['output']


def test_at63_no_execution_on_undefined():
    """Test AT-63: Verify no process execution occurs when undefined variables detected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()

        # Create a file that should NOT be created if the command runs
        marker_file = workspace / "should_not_exist.txt"

        # Create workflow that would create a file if executed
        workflow_path = workspace / "workflow.yaml"
        workflow_content = f"""
version: "1.1"
steps:
  - name: CreateFile
    command: touch {marker_file} && echo "Created ${{context.undefined}}"
"""
        workflow_path.write_text(workflow_content)

        loader = WorkflowLoader(workspace)
        workflow = loader.load(workflow_path)

        # Setup state manager
        state_dir = workspace / ".orchestrate/runs/test"
        state_dir.mkdir(parents=True)
        state_manager = StateManager(state_dir)

        # Create initial state
        state_manager.initialize(
            str(workflow_path),
            context={}
        )

        # Execute workflow
        executor = WorkflowExecutor(workflow, workspace, state_manager)
        result = executor.execute()

        # Verify the marker file was NOT created (command didn't run)
        assert not marker_file.exists(), "Command should not have executed with undefined variables"

        # Verify proper error reporting
        state = state_manager.load()
        assert state.steps['CreateFile']['exit_code'] == 2
        error = state.steps['CreateFile'].get('error', {})
        assert 'undefined_vars' in error['context']
        assert 'context.undefined' in error['context']['undefined_vars']


if __name__ == "__main__":
    # Run the tests
    test_at63_undefined_variable_in_command()
    test_at63_undefined_variable_in_list_command()
    test_at63_multiple_undefined_variables()
    test_at63_defined_variables_execute_normally()
    test_at63_no_execution_on_undefined()
    print("All AT-63 tests passed!")