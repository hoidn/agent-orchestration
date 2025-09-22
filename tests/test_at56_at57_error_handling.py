"""
Test suite for AT-56 and AT-57: Error handling and control flow.

AT-56: Strict flow stop - Non-zero exit halts run when no applicable goto and on_error=stop (default)
AT-57: on_error continue - With --on-error continue, run proceeds after non-zero exit
AT-58: Goto precedence - on.success/failure goto execute before strict_flow applies
AT-59: Goto always ordering - on.always evaluated after success/failure handlers
"""

import pytest
import tempfile
import json
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.state import StateManager


class TestErrorHandling:
    """Test suite for error handling and control flow."""

    def test_at56_strict_flow_stop(self, tmp_path):
        """
        AT-56: Non-zero exit halts run when no goto and on_error=stop.
        """
        # Create workflow with failing step
        workflow_yaml = """
version: "1.1"
name: test-strict-flow
strict_flow: true
steps:
  - name: step1
    command: ["echo", "Step 1"]

  - name: step2
    command: ["exit", "1"]  # This will fail

  - name: step3
    command: ["echo", "Step 3"]  # Should not execute
"""
        workflow_path = tmp_path / "workflow.yaml"
        workflow_path.write_text(workflow_yaml)

        # Load workflow
        loader = WorkflowLoader(tmp_path)
        workflow = loader.load(workflow_path)

        # Create state manager
        state_manager = StateManager(tmp_path)
        run_state = state_manager.initialize(str(workflow_path), {})

        # Create executor
        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=str(tmp_path),
            state_manager=state_manager,
            logs_dir=state_manager.logs_dir
        )

        # Mock command execution to control exit codes
        with patch.object(executor, '_execute_command_with_context') as mock_exec:
            def command_side_effect(step, context, state):
                name = step.get('name')
                if name == 'step1':
                    return {'exit_code': 0, 'output': 'Step 1'}
                elif name == 'step2':
                    return {'exit_code': 1, 'output': 'Failed'}
                elif name == 'step3':
                    return {'exit_code': 0, 'output': 'Step 3'}
                return {'exit_code': 0}

            mock_exec.side_effect = command_side_effect

            # Execute with on_error=stop (default)
            result = executor.execute(run_id=run_state.run_id, on_error='stop')

            # Verify execution stopped at step2
            assert mock_exec.call_count == 2  # Only step1 and step2 executed
            calls = [call[0][0]['name'] for call in mock_exec.call_args_list]
            assert calls == ['step1', 'step2']
            assert 'step3' not in calls  # Step 3 should not execute

    def test_at57_on_error_continue(self, tmp_path):
        """
        AT-57: With --on-error continue, run proceeds after non-zero exit.
        """
        # Create workflow with failing step
        workflow_yaml = """
version: "1.1"
name: test-continue-on-error
steps:
  - name: step1
    command: ["echo", "Step 1"]

  - name: step2
    command: ["exit", "1"]  # This will fail

  - name: step3
    command: ["echo", "Step 3"]  # Should execute with continue
"""
        workflow_path = tmp_path / "workflow.yaml"
        workflow_path.write_text(workflow_yaml)

        # Load workflow
        loader = WorkflowLoader(tmp_path)
        workflow = loader.load(workflow_path)

        # Create state manager
        state_manager = StateManager(tmp_path)
        run_state = state_manager.initialize(str(workflow_path), {})

        # Create executor
        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=str(tmp_path),
            state_manager=state_manager,
            logs_dir=state_manager.logs_dir
        )

        # Mock command execution
        with patch.object(executor, '_execute_command_with_context') as mock_exec:
            def command_side_effect(step, context, state):
                name = step.get('name')
                if name == 'step1':
                    return {'exit_code': 0, 'output': 'Step 1'}
                elif name == 'step2':
                    return {'exit_code': 1, 'output': 'Failed'}
                elif name == 'step3':
                    return {'exit_code': 0, 'output': 'Step 3'}
                return {'exit_code': 0}

            mock_exec.side_effect = command_side_effect

            # Execute with on_error=continue
            result = executor.execute(run_id=run_state.run_id, on_error='continue')

            # Verify all steps executed despite failure
            assert mock_exec.call_count == 3
            calls = [call[0][0]['name'] for call in mock_exec.call_args_list]
            assert calls == ['step1', 'step2', 'step3']

    def test_at58_goto_precedence_on_failure(self, tmp_path):
        """
        AT-58: on.failure.goto executes before strict_flow applies.
        """
        workflow_yaml = """
version: "1.1"
name: test-goto-precedence
strict_flow: true
steps:
  - name: step1
    command: ["exit", "1"]
    on:
      failure:
        goto: recovery

  - name: step2
    command: ["echo", "Should be skipped"]

  - name: recovery
    command: ["echo", "Recovery step"]

  - name: step3
    command: ["echo", "After recovery"]
"""
        workflow_path = tmp_path / "workflow.yaml"
        workflow_path.write_text(workflow_yaml)

        loader = WorkflowLoader(tmp_path)
        workflow = loader.load(workflow_path)

        state_dir = tmp_path / ".orchestrate"
        state_manager = StateManager(str(state_dir))
        run_state = state_manager.initialize(str(workflow_path), {})

        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=str(tmp_path),
            state_manager=state_manager,
            logs_dir=state_manager.logs_dir
        )

        with patch.object(executor, '_execute_command_with_context') as mock_exec:
            def command_side_effect(step, context, state):
                name = step.get('name')
                if name == 'step1':
                    return {'exit_code': 1, 'output': 'Failed'}
                return {'exit_code': 0, 'output': f'Executed {name}'}

            mock_exec.side_effect = command_side_effect

            # Execute with strict_flow and on_error=stop
            result = executor.execute(run_id=run_state.run_id, on_error='stop')

            # Verify goto was followed despite strict_flow
            calls = [call[0][0]['name'] for call in mock_exec.call_args_list]
            assert 'step1' in calls
            assert 'recovery' in calls  # Should jump to recovery
            assert 'step2' not in calls  # Should be skipped
            assert 'step3' in calls  # Should continue after recovery

    def test_at58_goto_precedence_on_success(self, tmp_path):
        """
        AT-58: on.success.goto executes and skips subsequent steps.
        """
        workflow_yaml = """
version: "1.1"
name: test-goto-success
steps:
  - name: step1
    command: ["echo", "Step 1"]
    on:
      success:
        goto: final

  - name: step2
    command: ["echo", "Should be skipped"]

  - name: step3
    command: ["echo", "Also skipped"]

  - name: final
    command: ["echo", "Final step"]
"""
        workflow_path = tmp_path / "workflow.yaml"
        workflow_path.write_text(workflow_yaml)

        loader = WorkflowLoader(tmp_path)
        workflow = loader.load(workflow_path)

        state_dir = tmp_path / ".orchestrate"
        state_manager = StateManager(str(state_dir))
        run_state = state_manager.initialize(str(workflow_path), {})

        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=str(tmp_path),
            state_manager=state_manager,
            logs_dir=state_manager.logs_dir
        )

        with patch.object(executor, '_execute_command_with_context') as mock_exec:
            mock_exec.return_value = {'exit_code': 0, 'output': 'Success'}

            result = executor.execute(run_id=run_state.run_id)

            calls = [call[0][0]['name'] for call in mock_exec.call_args_list]
            assert calls == ['step1', 'final']  # Jump from step1 to final

    def test_at59_goto_always_ordering(self, tmp_path):
        """
        AT-59: on.always evaluated after success/failure handlers.
        """
        workflow_yaml = """
version: "1.1"
name: test-goto-always
steps:
  - name: step1
    command: ["exit", "1"]
    on:
      failure:
        goto: recovery
      always:
        goto: cleanup  # Should override failure goto

  - name: recovery
    command: ["echo", "Recovery - should be skipped"]

  - name: cleanup
    command: ["echo", "Cleanup - always runs"]
"""
        workflow_path = tmp_path / "workflow.yaml"
        workflow_path.write_text(workflow_yaml)

        loader = WorkflowLoader(tmp_path)
        workflow = loader.load(workflow_path)

        state_dir = tmp_path / ".orchestrate"
        state_manager = StateManager(str(state_dir))
        run_state = state_manager.initialize(str(workflow_path), {})

        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=str(tmp_path),
            state_manager=state_manager,
            logs_dir=state_manager.logs_dir
        )

        with patch.object(executor, '_execute_command_with_context') as mock_exec:
            def command_side_effect(step, context, state):
                name = step.get('name')
                if name == 'step1':
                    return {'exit_code': 1, 'output': 'Failed'}
                return {'exit_code': 0, 'output': f'Executed {name}'}

            mock_exec.side_effect = command_side_effect

            result = executor.execute(run_id=run_state.run_id)

            calls = [call[0][0]['name'] for call in mock_exec.call_args_list]
            # on.always overrides on.failure
            assert calls == ['step1', 'cleanup']
            assert 'recovery' not in calls

    def test_goto_end_target(self, tmp_path):
        """
        Test that goto: _end terminates the workflow successfully.
        """
        workflow_yaml = """
version: "1.1"
name: test-goto-end
steps:
  - name: step1
    command: ["echo", "Step 1"]
    on:
      success:
        goto: _end

  - name: step2
    command: ["echo", "Should be skipped"]

  - name: step3
    command: ["echo", "Also skipped"]
"""
        workflow_path = tmp_path / "workflow.yaml"
        workflow_path.write_text(workflow_yaml)

        loader = WorkflowLoader(tmp_path)
        workflow = loader.load(workflow_path)

        state_dir = tmp_path / ".orchestrate"
        state_manager = StateManager(str(state_dir))
        run_state = state_manager.initialize(str(workflow_path), {})

        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=str(tmp_path),
            state_manager=state_manager,
            logs_dir=state_manager.logs_dir
        )

        with patch.object(executor, '_execute_command_with_context') as mock_exec:
            mock_exec.return_value = {'exit_code': 0, 'output': 'Success'}

            result = executor.execute(run_id=run_state.run_id)

            # Only step1 should execute before _end terminates
            assert mock_exec.call_count == 1
            assert mock_exec.call_args_list[0][0][0]['name'] == 'step1'

    def test_strict_flow_false_allows_continuation(self, tmp_path):
        """
        Test that strict_flow: false allows continuation after failures.
        """
        workflow_yaml = """
version: "1.1"
name: test-no-strict-flow
strict_flow: false
steps:
  - name: step1
    command: ["echo", "Step 1"]

  - name: step2
    command: ["exit", "1"]

  - name: step3
    command: ["echo", "Step 3"]
"""
        workflow_path = tmp_path / "workflow.yaml"
        workflow_path.write_text(workflow_yaml)

        loader = WorkflowLoader(tmp_path)
        workflow = loader.load(workflow_path)

        state_dir = tmp_path / ".orchestrate"
        state_manager = StateManager(str(state_dir))
        run_state = state_manager.initialize(str(workflow_path), {})

        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=str(tmp_path),
            state_manager=state_manager,
            logs_dir=state_manager.logs_dir
        )

        with patch.object(executor, '_execute_command_with_context') as mock_exec:
            def command_side_effect(step, context, state):
                name = step.get('name')
                if name == 'step2':
                    return {'exit_code': 1, 'output': 'Failed'}
                return {'exit_code': 0, 'output': 'Success'}

            mock_exec.side_effect = command_side_effect

            # Execute with strict_flow=false and on_error=stop
            result = executor.execute(run_id=run_state.run_id, on_error='stop')

            # All steps should execute because strict_flow is false
            assert mock_exec.call_count == 3
            calls = [call[0][0]['name'] for call in mock_exec.call_args_list]
            assert calls == ['step1', 'step2', 'step3']

    def test_skipped_steps_dont_trigger_control_flow(self, tmp_path):
        """
        Test that skipped steps (conditional false) don't trigger error handling.
        """
        workflow_yaml = """
version: "1.1"
name: test-skipped-control-flow
steps:
  - name: step1
    command: ["echo", "Step 1"]

  - name: step2
    command: ["exit", "1"]
    when:
      equals:
        left: "false"
        right: "true"  # Condition is false, step skipped

  - name: step3
    command: ["echo", "Step 3"]  # Should execute
"""
        workflow_path = tmp_path / "workflow.yaml"
        workflow_path.write_text(workflow_yaml)

        loader = WorkflowLoader(tmp_path)
        workflow = loader.load(workflow_path)

        state_dir = tmp_path / ".orchestrate"
        state_manager = StateManager(str(state_dir))
        run_state = state_manager.initialize(str(workflow_path), {})

        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=str(tmp_path),
            state_manager=state_manager,
            logs_dir=state_manager.logs_dir
        )

        with patch.object(executor, '_execute_command_with_context') as mock_exec:
            mock_exec.return_value = {'exit_code': 0, 'output': 'Success'}

            result = executor.execute(run_id=run_state.run_id, on_error='stop')

            # Only step1 and step3 execute (step2 is skipped)
            assert mock_exec.call_count == 2
            calls = [call[0][0]['name'] for call in mock_exec.call_args_list]
            assert calls == ['step1', 'step3']