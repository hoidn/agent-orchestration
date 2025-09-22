"""
Test suite for for-each loop execution.
Tests AT-3 and AT-13: Dynamic for-each with pointer resolution.
"""

import pytest
import json
from pathlib import Path
import tempfile
import shutil

from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.pointers import PointerResolver
from orchestrator.state import StateManager
from orchestrator.loader import WorkflowLoader


class TestPointerResolution:
    """Test pointer resolution for items_from."""

    def test_at3_items_from_lines(self):
        """AT-3: items_from with steps.X.lines pointer."""
        state = {
            'steps': {
                'ListFiles': {
                    'exit_code': 0,
                    'lines': ['file1.txt', 'file2.txt', 'file3.txt']
                }
            }
        }

        resolver = PointerResolver(state)
        result = resolver.resolve('steps.ListFiles.lines')

        assert result == ['file1.txt', 'file2.txt', 'file3.txt']

    def test_at13_items_from_json_nested(self):
        """AT-13: items_from with nested JSON path."""
        state = {
            'steps': {
                'ParseData': {
                    'exit_code': 0,
                    'json': {
                        'results': {
                            'files': ['a.json', 'b.json', 'c.json']
                        },
                        'count': 3
                    }
                }
            }
        }

        resolver = PointerResolver(state)

        # Test nested path resolution
        result = resolver.resolve('steps.ParseData.json.results.files')
        assert result == ['a.json', 'b.json', 'c.json']

        # Test single-level JSON access
        result = resolver.resolve('steps.ParseData.json.count')
        assert result == 3

    def test_invalid_pointer_syntax(self):
        """Test invalid pointer syntax is rejected."""
        resolver = PointerResolver({})

        with pytest.raises(ValueError, match="Invalid pointer syntax"):
            resolver.resolve('invalid.pointer')

        with pytest.raises(ValueError, match="Invalid pointer syntax"):
            resolver.resolve('steps')

    def test_missing_step_in_pointer(self):
        """Test pointer to non-existent step."""
        resolver = PointerResolver({'steps': {}})

        with pytest.raises(ValueError, match="Step 'Missing' not found"):
            resolver.resolve('steps.Missing.lines')

    def test_missing_output_type(self):
        """Test pointer to missing output type."""
        state = {
            'steps': {
                'Test': {
                    'exit_code': 0,
                    'text': 'some output'
                }
            }
        }

        resolver = PointerResolver(state)

        with pytest.raises(ValueError, match="does not have 'lines' output"):
            resolver.resolve('steps.Test.lines')

        with pytest.raises(ValueError, match="does not have 'json' output"):
            resolver.resolve('steps.Test.json')

    def test_invalid_json_path_navigation(self):
        """Test invalid JSON path navigation."""
        state = {
            'steps': {
                'Test': {
                    'exit_code': 0,
                    'json': {
                        'value': 'not_an_object'
                    }
                }
            }
        }

        resolver = PointerResolver(state)

        with pytest.raises(ValueError, match="is not an object"):
            resolver.resolve('steps.Test.json.value.nested')

        with pytest.raises(ValueError, match="missing key"):
            resolver.resolve('steps.Test.json.nonexistent')

    def test_safe_resolution(self):
        """Test safe resolution with error handling."""
        state = {
            'steps': {
                'Test': {
                    'lines': ['a', 'b']
                }
            }
        }

        resolver = PointerResolver(state)

        # Successful resolution
        success, value, error = resolver.resolve_safe('steps.Test.lines')
        assert success is True
        assert value == ['a', 'b']
        assert error is None

        # Failed resolution
        success, value, error = resolver.resolve_safe('steps.Missing.lines')
        assert success is False
        assert value is None
        assert "not found" in error


class TestForEachExecution:
    """Test for-each loop execution in workflows."""

    def setup_method(self):
        """Setup test environment."""
        self.test_dir = Path(tempfile.mkdtemp(prefix='test_for_each_'))
        self.workspace = self.test_dir / 'workspace'
        self.workspace.mkdir()
        self.state_dir = self.test_dir / '.orchestrate'
        self.state_dir.mkdir()

    def teardown_method(self):
        """Cleanup test environment."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_at3_for_each_dynamic_items(self):
        """AT-3: Dynamic for-each with items_from executes correctly."""
        # Create a workflow with for_each using items_from
        workflow_yaml = """
version: "1.1"
steps:
  - name: ListFiles
    command: ["echo", "file1.txt\\nfile2.txt\\nfile3.txt"]
    output_capture: lines

  - name: ProcessFiles
    for_each:
      items_from: "steps.ListFiles.lines"
      as: filename
      steps:
        - name: ProcessFile
          command: ["echo", "Processing ${filename}"]
          output_capture: text
"""
        workflow_file = self.workspace / 'workflow.yaml'
        workflow_file.write_text(workflow_yaml)

        # Load workflow
        loader = WorkflowLoader(self.workspace)
        workflow = loader.load(str(workflow_file))
        assert workflow is not None

        # Create state manager
        state_manager = StateManager(
            workspace=self.workspace,
            run_id='test_run',
            backup_enabled=False
        )
        state_manager.initialize(str(workflow_file))

        # Execute workflow
        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=self.workspace,
            state_manager=state_manager
        )

        # Mock the command execution to avoid actual subprocess calls
        def mock_execute_command(self, **kwargs):
            step_name = kwargs['step_name']
            command = kwargs['command']

            # Handle both string and list commands
            if isinstance(command, list):
                command_str = ' '.join(command)
            else:
                command_str = command

            if step_name == 'ListFiles':
                # ListFiles step
                from orchestrator.exec.output_capture import CaptureResult, CaptureMode
                result = CaptureResult(
                    mode=CaptureMode.LINES,
                    output="file1.txt\nfile2.txt\nfile3.txt\n",
                    lines=["file1.txt", "file2.txt", "file3.txt"],
                    truncated=False
                )
                from orchestrator.exec.step_executor import ExecutionResult
                return ExecutionResult(
                    step_name=step_name,
                    exit_code=0,
                    capture_result=result,
                    duration_ms=10
                )
            else:
                # ProcessFile steps
                from orchestrator.exec.output_capture import CaptureResult, CaptureMode
                result = CaptureResult(
                    mode=CaptureMode.TEXT,
                    output=command_str,  # Echo back the command string
                    truncated=False
                )
                from orchestrator.exec.step_executor import ExecutionResult
                return ExecutionResult(
                    step_name=step_name,
                    exit_code=0,
                    capture_result=result,
                    duration_ms=5
                )

        # Patch the executor's command execution
        import types
        executor.step_executor.execute_command = types.MethodType(mock_execute_command, executor.step_executor)

        # Execute
        state = executor.execute()

        # Verify ListFiles executed
        assert 'ListFiles' in state['steps']
        assert state['steps']['ListFiles']['lines'] == ['file1.txt', 'file2.txt', 'file3.txt']

        # Verify ProcessFiles loop executed
        assert 'ProcessFiles' in state['steps']
        loop_results = state['steps']['ProcessFiles']

        # Should have 3 iterations
        assert len(loop_results) == 3

        # Check indexed results exist
        assert 'ProcessFiles[0].ProcessFile' in state['steps']
        assert 'ProcessFiles[1].ProcessFile' in state['steps']
        assert 'ProcessFiles[2].ProcessFile' in state['steps']

        # Verify each iteration processed the correct file
        for i, filename in enumerate(['file1.txt', 'file2.txt', 'file3.txt']):
            indexed_key = f'ProcessFiles[{i}].ProcessFile'
            assert indexed_key in state['steps']
            result = state['steps'][indexed_key]
            assert f'Processing {filename}' in result.get('output', '')

    def test_at13_for_each_json_pointer(self):
        """AT-13: for_each with nested JSON pointer."""
        # Create a workflow that uses nested JSON path
        workflow_yaml = """
version: "1.1"
steps:
  - name: GetData
    command: ["echo", '{"tasks": {"items": ["task1", "task2", "task3"]}}']
    output_capture: json

  - name: ProcessTasks
    for_each:
      items_from: "steps.GetData.json.tasks.items"
      as: task
      steps:
        - name: HandleTask
          command: ["echo", "Handling ${task}"]
"""
        workflow_file = self.workspace / 'workflow.yaml'
        workflow_file.write_text(workflow_yaml)

        # Load workflow
        loader = WorkflowLoader(self.workspace)
        workflow = loader.load(str(workflow_file))
        assert workflow is not None

        # Create state manager
        state_manager = StateManager(
            workspace=self.workspace,
            run_id='test_run',
            backup_enabled=False
        )
        state_manager.initialize(str(workflow_file))

        # Execute workflow
        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=self.workspace,
            state_manager=state_manager
        )

        # Mock execution
        def mock_execute_command(self, **kwargs):
            command = kwargs['command']

            # Convert command to string for checking
            command_str = ' '.join(command) if isinstance(command, list) else command

            if 'tasks' in command_str:
                # GetData step
                from orchestrator.exec.output_capture import CaptureResult, CaptureMode
                result = CaptureResult(
                    mode=CaptureMode.JSON,
                    output='{"tasks": {"items": ["task1", "task2", "task3"]}}',
                    json_data={"tasks": {"items": ["task1", "task2", "task3"]}},
                    truncated=False
                )
                from orchestrator.exec.step_executor import ExecutionResult
                return ExecutionResult(
                    step_name=kwargs['step_name'],
                    exit_code=0,
                    capture_result=result,
                    duration_ms=10
                )
            else:
                # HandleTask steps
                from orchestrator.exec.output_capture import CaptureResult, CaptureMode
                result = CaptureResult(
                    mode=CaptureMode.TEXT,
                    output=command_str,
                    truncated=False
                )
                from orchestrator.exec.step_executor import ExecutionResult
                return ExecutionResult(
                    step_name=kwargs['step_name'],
                    exit_code=0,
                    capture_result=result,
                    duration_ms=5
                )

        import types
        executor.step_executor.execute_command = types.MethodType(mock_execute_command, executor.step_executor)

        # Execute
        state = executor.execute()

        # Verify GetData executed
        assert 'GetData' in state['steps']
        assert state['steps']['GetData']['json']['tasks']['items'] == ['task1', 'task2', 'task3']

        # Verify ProcessTasks loop executed
        assert 'ProcessTasks' in state['steps']
        loop_results = state['steps']['ProcessTasks']
        assert len(loop_results) == 3

        # Check indexed results
        for i, task in enumerate(['task1', 'task2', 'task3']):
            indexed_key = f'ProcessTasks[{i}].HandleTask'
            assert indexed_key in state['steps']
            result = state['steps'][indexed_key]
            assert f'Handling {task}' in result.get('output', '')

    def test_for_each_invalid_pointer_fails(self):
        """Test for_each with invalid pointer fails with exit code 2."""
        workflow_yaml = """
version: "1.1"
steps:
  - name: ProcessItems
    for_each:
      items_from: "steps.NonExistent.lines"
      steps:
        - name: Process
          command: ["echo", "test"]
"""
        workflow_file = self.workspace / 'workflow.yaml'
        workflow_file.write_text(workflow_yaml)

        loader = WorkflowLoader(self.workspace)
        workflow = loader.load(str(workflow_file))

        state_manager = StateManager(
            workspace=self.workspace,
            run_id='test_run',
            backup_enabled=False
        )
        state_manager.initialize(str(workflow_file))

        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=self.workspace,
            state_manager=state_manager
        )

        # Execute
        state = executor.execute()

        # Should fail with exit code 2
        assert 'ProcessItems' in state['steps']
        assert state['steps']['ProcessItems']['exit_code'] == 2
        assert 'error' in state['steps']['ProcessItems']
        assert 'NonExistent' in state['steps']['ProcessItems']['error']['message']

    def test_for_each_non_array_pointer_fails(self):
        """Test for_each with pointer to non-array fails."""
        workflow_yaml = """
version: "1.1"
steps:
  - name: GetValue
    command: ["echo", '{"value": 42}']
    output_capture: json

  - name: ProcessValue
    for_each:
      items_from: "steps.GetValue.json.value"
      steps:
        - name: Process
          command: ["echo", "test"]
"""
        workflow_file = self.workspace / 'workflow.yaml'
        workflow_file.write_text(workflow_yaml)

        loader = WorkflowLoader(self.workspace)
        workflow = loader.load(str(workflow_file))

        state_manager = StateManager(
            workspace=self.workspace,
            run_id='test_run',
            backup_enabled=False
        )
        state_manager.initialize(str(workflow_file))

        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=self.workspace,
            state_manager=state_manager
        )

        # Mock GetValue execution
        def mock_execute_command(self, **kwargs):
            if 'GetValue' in kwargs['step_name']:
                from orchestrator.exec.output_capture import CaptureResult, CaptureMode
                result = CaptureResult(
                    mode=CaptureMode.JSON,
                    output='{"value": 42}',
                    json_data={"value": 42},
                    truncated=False
                )
                from orchestrator.exec.step_executor import ExecutionResult
                return ExecutionResult(
                    step_name=kwargs['step_name'],
                    exit_code=0,
                    capture_result=result,
                    duration_ms=10
                )

        import types
        executor.step_executor.execute_command = types.MethodType(mock_execute_command, executor.step_executor)

        # Execute
        state = executor.execute()

        # ProcessValue should fail
        assert 'ProcessValue' in state['steps']
        assert state['steps']['ProcessValue']['exit_code'] == 2
        assert 'error' in state['steps']['ProcessValue']
        assert 'must resolve to an array' in state['steps']['ProcessValue']['error']['message']

    def test_for_each_loop_variables(self):
        """Test loop variables are accessible within for_each."""
        workflow_yaml = """
version: "1.1"
steps:
  - name: ProcessItems
    for_each:
      items: ["alpha", "beta", "gamma"]
      as: value
      steps:
        - name: ShowIndex
          command: ["echo", "Item ${loop.index} of ${loop.total}: ${value}"]
          output_capture: text
"""
        workflow_file = self.workspace / 'workflow.yaml'
        workflow_file.write_text(workflow_yaml)

        loader = WorkflowLoader(self.workspace)
        workflow = loader.load(str(workflow_file))

        state_manager = StateManager(
            workspace=self.workspace,
            run_id='test_run',
            backup_enabled=False
        )
        state_manager.initialize(str(workflow_file))

        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=self.workspace,
            state_manager=state_manager
        )

        # Mock execution to capture variable substitution
        executed_commands = []

        def mock_execute_command(self, **kwargs):
            command = kwargs['command']
            executed_commands.append(command)

            from orchestrator.exec.output_capture import CaptureResult, CaptureMode
            result = CaptureResult(
                mode=CaptureMode.TEXT,
                output=command,
                truncated=False
            )
            from orchestrator.exec.step_executor import ExecutionResult
            return ExecutionResult(
                step_name=kwargs['step_name'],
                exit_code=0,
                capture_result=result,
                duration_ms=5
            )

        import types
        executor.step_executor.execute_command = types.MethodType(mock_execute_command, executor.step_executor)

        # Execute
        state = executor.execute()

        # Check that loop variables were substituted correctly
        assert len(executed_commands) == 3
        assert 'Item 0 of 3: alpha' in executed_commands[0]
        assert 'Item 1 of 3: beta' in executed_commands[1]
        assert 'Item 2 of 3: gamma' in executed_commands[2]