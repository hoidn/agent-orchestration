"""
Test suite for retry behavior implementation.
Tests AT-20, AT-21: Timeout and retry logic for providers and commands.
"""

import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest
import yaml

from orchestrator.exec.retry import RetryPolicy
from orchestrator.exec.step_executor import StepExecutor, ExecutionResult
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.state import StateManager
from orchestrator.exec.output_capture import CaptureResult, CaptureMode
from orchestrator.providers.executor import ProviderExecutionResult


class TestRetryPolicy:
    """Test the RetryPolicy class logic."""

    def test_provider_default_retry_policy(self):
        """AT-21: Provider steps retry on exit codes 1 and 124 by default."""
        policy = RetryPolicy.for_provider(max_retries=3)

        assert policy.max_retries == 3
        assert policy.delay_ms == 1000
        assert policy.retryable_codes == {1, 124}

        # Should retry on codes 1 and 124
        assert policy.should_retry(1, 0) is True
        assert policy.should_retry(124, 0) is True

        # Should not retry on other codes
        assert policy.should_retry(0, 0) is False
        assert policy.should_retry(2, 0) is False

        # Should not retry after max attempts
        assert policy.should_retry(1, 3) is False

    def test_command_no_retry_by_default(self):
        """AT-21: Raw commands are not retried unless retries field is set."""
        policy = RetryPolicy.for_command(None)

        assert policy.max_retries == 0
        assert policy.retryable_codes == set()

        # Should not retry on any code
        assert policy.should_retry(1, 0) is False
        assert policy.should_retry(124, 0) is False

    def test_command_with_retries_config(self):
        """AT-21: Commands with retries field set use retry policy."""
        retries_config = {'max': 2, 'delay_ms': 500}
        policy = RetryPolicy.for_command(retries_config)

        assert policy.max_retries == 2
        assert policy.delay_ms == 500
        assert policy.retryable_codes == {1, 124}

        # Should retry on codes 1 and 124
        assert policy.should_retry(1, 0) is True
        assert policy.should_retry(124, 0) is True
        assert policy.should_retry(1, 1) is True

        # Should not retry after max attempts
        assert policy.should_retry(1, 2) is False

    def test_retry_wait_delay(self):
        """Test that retry policy waits for the configured delay."""
        policy = RetryPolicy(max_retries=1, delay_ms=100)

        start = time.time()
        policy.wait()
        elapsed = time.time() - start

        # Allow some tolerance for timing
        assert 0.09 < elapsed < 0.15


class TestWorkflowRetryExecution:
    """Test retry execution in the workflow executor."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir) / 'workspace'
        self.workspace.mkdir(parents=True)
        self.state_dir = Path(self.temp_dir) / 'state'
        self.state_dir.mkdir(parents=True)

    def test_at20_timeout_enforcement(self):
        """AT-20: Timeout enforcement with exit code 124."""
        workflow = {
            'version': '1.1',
            'steps': [
                {
                    'name': 'TimeoutStep',
                    'command': 'sleep 10',
                    'timeout_sec': 0.1  # Very short timeout
                }
            ]
        }

        # Create workflow file for state manager
        workflow_file = self.workspace / 'test_workflow.yaml'
        workflow_file.write_text(yaml.dump(workflow))

        state_manager = StateManager(self.workspace)
        state_manager.initialize(str(workflow_file), {})

        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=self.workspace,
            state_manager=state_manager
        )

        # Mock to simulate timeout (exit code 124)
        mock_result = ExecutionResult(
            step_name='TimeoutStep',
            exit_code=124,
            capture_result=CaptureResult(
                mode=CaptureMode.TEXT,
                output='',
                truncated=False,
                exit_code=124
            ),
            duration_ms=100,
            error={'type': 'timeout', 'message': 'Command timed out'}
        )

        with patch.object(executor.step_executor, 'execute_command', return_value=mock_result):
            result = executor.execute()

            # Verify timeout was recorded
            assert 'TimeoutStep' in result['steps']
            assert result['steps']['TimeoutStep']['exit_code'] == 124
            assert result['steps']['TimeoutStep']['error']['type'] == 'timeout'

    def test_at21_provider_retry_on_exit_1(self):
        """AT-21: Provider steps retry on exit code 1."""
        workflow = {
            'version': '1.1',
            'providers': {
                'test_provider': {
                    'command': ['echo', '${PROMPT}'],
                    'defaults': {}
                }
            },
            'steps': [
                {
                    'name': 'ProviderStep',
                    'provider': 'test_provider'
                }
            ]
        }

        # Create workflow file for state manager
        workflow_file = self.workspace / 'test_workflow.yaml'
        workflow_file.write_text(yaml.dump(workflow))

        state_manager = StateManager(self.workspace)
        state_manager.initialize(str(workflow_file), {})

        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=self.workspace,
            state_manager=state_manager,
            max_retries=2,
            retry_delay_ms=10  # Short delay for testing
        )

        # Mock provider to fail twice, then succeed
        call_count = 0
        def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            if call_count <= 2:
                # First two calls fail with retryable error
                return ProviderExecutionResult(
                    exit_code=1,
                    stdout=b'API error',
                    stderr=b'',
                    duration_ms=100,
                    error={'type': 'api_error', 'message': 'Retryable API error'}
                )
            else:
                # Third call succeeds
                return ProviderExecutionResult(
                    exit_code=0,
                    stdout=b'Success',
                    stderr=b'',
                    duration_ms=100,
                    error=None
                )

        with patch.object(executor.provider_executor, 'execute', side_effect=mock_execute):
            result = executor.execute()

            # Should have retried and eventually succeeded
            assert call_count == 3
            assert 'ProviderStep' in result['steps']
            assert result['steps']['ProviderStep']['exit_code'] == 0
            assert result['steps']['ProviderStep']['output'] == 'Success'

    def test_at21_provider_retry_on_timeout(self):
        """AT-21: Provider steps retry on exit code 124 (timeout)."""
        workflow = {
            'version': '1.1',
            'providers': {
                'test_provider': {
                    'command': ['echo', '${PROMPT}'],
                    'defaults': {}
                }
            },
            'steps': [
                {
                    'name': 'ProviderStep',
                    'provider': 'test_provider',
                    'timeout_sec': 1
                }
            ]
        }

        # Create workflow file for state manager
        workflow_file = self.workspace / 'test_workflow.yaml'
        workflow_file.write_text(yaml.dump(workflow))

        state_manager = StateManager(self.workspace)
        state_manager.initialize(str(workflow_file), {})

        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=self.workspace,
            state_manager=state_manager,
            max_retries=1,
            retry_delay_ms=10
        )

        # Mock provider to timeout once, then succeed
        call_count = 0
        def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # First call times out
                return ProviderExecutionResult(
                    exit_code=124,
                    stdout=b'',
                    stderr=b'',
                    duration_ms=1000,
                    error={'type': 'timeout', 'message': 'Provider timed out'}
                )
            else:
                # Second call succeeds
                return ProviderExecutionResult(
                    exit_code=0,
                    stdout=b'Success after retry',
                    stderr=b'',
                    duration_ms=100,
                    error=None
                )

        with patch.object(executor.provider_executor, 'execute', side_effect=mock_execute):
            result = executor.execute()

            # Should have retried after timeout and succeeded
            assert call_count == 2
            assert result['steps']['ProviderStep']['exit_code'] == 0

    def test_at21_command_no_retry_by_default(self):
        """AT-21: Raw commands are not retried by default."""
        workflow = {
            'version': '1.1',
            'steps': [
                {
                    'name': 'CommandStep',
                    'command': 'false'  # Command that always fails
                }
            ]
        }

        # Create workflow file for state manager
        workflow_file = self.workspace / 'test_workflow.yaml'
        workflow_file.write_text(yaml.dump(workflow))

        state_manager = StateManager(self.workspace)
        state_manager.initialize(str(workflow_file), {})

        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=self.workspace,
            state_manager=state_manager,
            max_retries=5  # Global retries should not apply to commands
        )

        # Mock command to fail
        mock_result = ExecutionResult(
            step_name='CommandStep',
            exit_code=1,
            capture_result=CaptureResult(
                mode=CaptureMode.TEXT,
                output='Command failed',
                truncated=False,
                exit_code=1
            ),
            duration_ms=100,
            error=None
        )

        call_count = 0
        def count_calls(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_result

        with patch.object(executor.step_executor, 'execute_command', side_effect=count_calls):
            result = executor.execute()

            # Should not retry - only called once
            assert call_count == 1
            assert result['steps']['CommandStep']['exit_code'] == 1

    def test_at21_command_retry_with_retries_field(self):
        """AT-21: Commands retry when retries field is set."""
        workflow = {
            'version': '1.1',
            'steps': [
                {
                    'name': 'CommandStep',
                    'command': 'flaky_command',
                    'retries': {
                        'max': 2,
                        'delay_ms': 10
                    }
                }
            ]
        }

        # Create workflow file for state manager
        workflow_file = self.workspace / 'test_workflow.yaml'
        workflow_file.write_text(yaml.dump(workflow))

        state_manager = StateManager(self.workspace)
        state_manager.initialize(str(workflow_file), {})

        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=self.workspace,
            state_manager=state_manager
        )

        # Mock command to fail once, then succeed
        call_count = 0
        def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # First call fails
                return ExecutionResult(
                    step_name='CommandStep',
                    exit_code=1,
                    capture_result=CaptureResult(
                        mode=CaptureMode.TEXT,
                        output='Command failed',
                        truncated=False,
                        exit_code=1
                    ),
                    duration_ms=100,
                    error=None
                )
            else:
                # Second call succeeds
                return ExecutionResult(
                    step_name='CommandStep',
                    exit_code=0,
                    capture_result=CaptureResult(
                        mode=CaptureMode.TEXT,
                        output='Command succeeded',
                        truncated=False,
                        exit_code=0
                    ),
                    duration_ms=100,
                    error=None
                )

        with patch.object(executor.step_executor, 'execute_command', side_effect=mock_execute):
            result = executor.execute()

            # Should have retried and succeeded
            assert call_count == 2
            assert result['steps']['CommandStep']['exit_code'] == 0

    def test_at21_provider_no_retry_on_exit_2(self):
        """AT-21: Providers do not retry on exit code 2 (non-retryable)."""
        workflow = {
            'version': '1.1',
            'providers': {
                'test_provider': {
                    'command': ['echo', '${PROMPT}'],
                    'defaults': {}
                }
            },
            'steps': [
                {
                    'name': 'ProviderStep',
                    'provider': 'test_provider'
                }
            ]
        }

        # Create workflow file for state manager
        workflow_file = self.workspace / 'test_workflow.yaml'
        workflow_file.write_text(yaml.dump(workflow))

        state_manager = StateManager(self.workspace)
        state_manager.initialize(str(workflow_file), {})

        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=self.workspace,
            state_manager=state_manager,
            max_retries=5
        )

        # Mock provider to fail with non-retryable error
        mock_result = ProviderExecutionResult(
            exit_code=2,
            stdout=b'Invalid input',
            stderr=b'',
            duration_ms=100,
            error={'type': 'validation_error', 'message': 'Invalid input'}
        )

        call_count = 0
        def count_calls(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_result

        with patch.object(executor.provider_executor, 'execute', side_effect=count_calls):
            result = executor.execute()

            # Should not retry on exit code 2
            assert call_count == 1
            assert result['steps']['ProviderStep']['exit_code'] == 2

    def test_step_override_global_retries(self):
        """Test that step-level retries override global settings."""
        workflow = {
            'version': '1.1',
            'providers': {
                'test_provider': {
                    'command': ['echo', 'test'],
                    'defaults': {}
                }
            },
            'steps': [
                {
                    'name': 'ProviderStep',
                    'provider': 'test_provider',
                    'retries': {
                        'max': 0  # Override to disable retries
                    }
                }
            ]
        }

        # Create workflow file for state manager
        workflow_file = self.workspace / 'test_workflow.yaml'
        workflow_file.write_text(yaml.dump(workflow))

        state_manager = StateManager(self.workspace)
        state_manager.initialize(str(workflow_file), {})

        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=self.workspace,
            state_manager=state_manager,
            max_retries=10  # Global setting
        )

        # Mock provider to fail
        mock_result = ProviderExecutionResult(
            exit_code=1,
            stdout=b'Failed',
            stderr=b'',
            duration_ms=100,
            error=None
        )

        call_count = 0
        def count_calls(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_result

        with patch.object(executor.provider_executor, 'execute', side_effect=count_calls):
            result = executor.execute()

            # Should not retry due to step-level override
            assert call_count == 1