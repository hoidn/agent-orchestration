"""
Integration test for retry behavior.
Tests AT-20, AT-21: Timeout and retry logic for providers and commands.
"""

import os
import tempfile
import time
from pathlib import Path

import pytest
import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.state import StateManager


class TestRetryIntegration:
    """Integration tests for retry functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir) / 'workspace'
        self.workspace.mkdir(parents=True)

    def test_at21_command_with_explicit_retries(self):
        """AT-21: Commands retry when retries field is set."""
        workflow = {
            'version': '1.1',
            'steps': [
                {
                    'name': 'RetryCommand',
                    'command': 'echo "Success"',
                    'retries': {
                        'max': 2,
                        'delay_ms': 10
                    },
                    'output_capture': 'text'
                }
            ]
        }

        # Create workflow file
        workflow_file = self.workspace / 'retry_workflow.yaml'
        workflow_file.write_text(yaml.dump(workflow))

        # Initialize state manager
        state_manager = StateManager(self.workspace)
        state = state_manager.initialize(str(workflow_file), {})

        # Execute workflow
        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=self.workspace,
            state_manager=state_manager
        )

        result = executor.execute()

        # Verify command executed successfully
        assert 'RetryCommand' in result['steps']
        assert result['steps']['RetryCommand']['exit_code'] == 0
        assert 'Success' in result['steps']['RetryCommand']['output']

    def test_at21_command_no_retry_without_field(self):
        """AT-21: Commands don't retry without retries field."""
        # Create a script that fails the first time
        failing_script = self.workspace / 'fail_once.sh'
        failing_script.write_text("""#!/bin/bash
if [ ! -f /tmp/retry_test_flag ]; then
    touch /tmp/retry_test_flag
    exit 1
fi
exit 0
""")
        failing_script.chmod(0o755)

        # Clean up any previous flag
        flag_file = Path('/tmp/retry_test_flag')
        if flag_file.exists():
            flag_file.unlink()

        workflow = {
            'version': '1.1',
            'steps': [
                {
                    'name': 'NoRetryCommand',
                    'command': str(failing_script),
                    'output_capture': 'text'
                }
            ]
        }

        # Create workflow file
        workflow_file = self.workspace / 'no_retry_workflow.yaml'
        workflow_file.write_text(yaml.dump(workflow))

        # Initialize state manager
        state_manager = StateManager(self.workspace)
        state = state_manager.initialize(str(workflow_file), {})

        # Execute workflow (global retries should not apply)
        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=self.workspace,
            state_manager=state_manager,
            max_retries=5  # Global retries should not apply to commands
        )

        result = executor.execute()

        # Should fail without retry
        assert 'NoRetryCommand' in result['steps']
        assert result['steps']['NoRetryCommand']['exit_code'] == 1

        # Clean up flag file
        if flag_file.exists():
            flag_file.unlink()

    def test_at20_timeout_records_exit_124(self):
        """AT-20: Timeout enforcement records exit code 124."""
        workflow = {
            'version': '1.1',
            'steps': [
                {
                    'name': 'TimeoutCommand',
                    'command': 'sleep 10',
                    'timeout_sec': 0.5,  # Short timeout
                    'output_capture': 'text'
                }
            ]
        }

        # Create workflow file
        workflow_file = self.workspace / 'timeout_workflow.yaml'
        workflow_file.write_text(yaml.dump(workflow))

        # Initialize state manager
        state_manager = StateManager(self.workspace)
        state = state_manager.initialize(str(workflow_file), {})

        # Execute workflow
        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=self.workspace,
            state_manager=state_manager
        )

        start_time = time.time()
        result = executor.execute()
        elapsed = time.time() - start_time

        # Should timeout quickly
        assert elapsed < 2.0

        # Should record exit code 124
        assert 'TimeoutCommand' in result['steps']
        assert result['steps']['TimeoutCommand']['exit_code'] == 124

    def test_retry_policy_with_delay(self):
        """Test that retry delays are enforced."""
        # Create a script that fails twice
        counter_file = self.workspace / 'counter.txt'
        counter_file.write_text('0')

        fail_twice_script = self.workspace / 'fail_twice.sh'
        fail_twice_script.write_text(f"""#!/bin/bash
count=$(cat {counter_file})
count=$((count + 1))
echo $count > {counter_file}
if [ $count -le 2 ]; then
    exit 1
fi
exit 0
""")
        fail_twice_script.chmod(0o755)

        workflow = {
            'version': '1.1',
            'steps': [
                {
                    'name': 'RetryWithDelay',
                    'command': str(fail_twice_script),
                    'retries': {
                        'max': 3,
                        'delay_ms': 200  # 200ms delay
                    },
                    'output_capture': 'text'
                }
            ]
        }

        # Create workflow file
        workflow_file = self.workspace / 'delay_workflow.yaml'
        workflow_file.write_text(yaml.dump(workflow))

        # Initialize state manager
        state_manager = StateManager(self.workspace)
        state = state_manager.initialize(str(workflow_file), {})

        # Execute workflow
        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=self.workspace,
            state_manager=state_manager
        )

        start_time = time.time()
        result = executor.execute()
        elapsed = time.time() - start_time

        # Should have retried with delays (2 retries * 200ms = 400ms minimum)
        assert elapsed >= 0.4

        # Should eventually succeed
        assert 'RetryWithDelay' in result['steps']
        assert result['steps']['RetryWithDelay']['exit_code'] == 0

        # Check that it was called 3 times
        final_count = int(counter_file.read_text().strip())
        assert final_count == 3