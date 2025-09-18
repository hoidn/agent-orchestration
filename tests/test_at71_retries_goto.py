"""Test for AT-71: Retries + on.failure.goto integration."""

import pytest
from pathlib import Path
import tempfile

from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.state import StateManager


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        yield workspace


def test_at71_retries_exhausted_triggers_failure_goto(temp_workspace):
    """
    AT-71: After exhausting retries, on.failure.goto triggers and control follows the target step.

    This test verifies that when a step fails after exhausting all retry attempts,
    the on.failure.goto handler is triggered.
    """
    # Create a workflow with retries and failure goto
    workflow_content = """
version: "1.1"
name: Test Retries with Failure Goto
steps:
  - name: FailingStep
    command: ["sh", "-c", "exit 1"]  # Always fails
    retries: 2  # Will retry twice
    on:
      failure:
        goto: ErrorHandler

  - name: NormalStep
    command: ["echo", "This should be skipped"]
    output_capture: text

  - name: ErrorHandler
    command: ["echo", "Handling error after retries exhausted"]
    output_capture: text
"""
    workflow_path = temp_workspace / "retry_goto_workflow.yaml"
    workflow_path.write_text(workflow_content)

    # Load and execute workflow
    loader = WorkflowLoader(temp_workspace)
    workflow = loader.load(workflow_path)

    state_manager = StateManager(temp_workspace)
    state_manager.initialize(str(workflow_path))

    executor = WorkflowExecutor(
        workflow=workflow,
        workspace=temp_workspace,
        state_manager=state_manager
    )

    # Execute workflow
    final_state = executor.execute()

    # Verify the step was retried and then failed
    assert 'FailingStep' in final_state['steps']
    assert final_state['steps']['FailingStep']['exit_code'] == 1

    # AT-71: After retries exhausted, failure goto should have been triggered
    # ErrorHandler should have been executed
    assert 'ErrorHandler' in final_state['steps']
    assert final_state['steps']['ErrorHandler']['exit_code'] == 0
    assert 'Handling error after retries exhausted' in final_state['steps']['ErrorHandler'].get('output', '')

    # NormalStep should have been skipped (goto jumped over it)
    assert 'NormalStep' not in final_state['steps']


def test_at71_retries_success_no_failure_goto(temp_workspace):
    """
    AT-71: When retries succeed, on.failure.goto should NOT trigger.

    This test uses a script that fails once then succeeds, verifying
    that failure goto is not triggered when retry succeeds.
    """
    # Create a script that fails once then succeeds
    script_path = temp_workspace / "retry_script.sh"
    script_content = """#!/bin/bash
# Check if state file exists (this means it's a retry)
STATE_FILE="/tmp/retry_test_state_at71"
if [ -f "$STATE_FILE" ]; then
    echo "Retry succeeded"
    rm "$STATE_FILE"
    exit 0
else
    echo "First attempt failing"
    touch "$STATE_FILE"
    exit 1
fi
"""
    script_path.write_text(script_content)
    script_path.chmod(0o755)

    workflow_content = f"""
version: "1.1"
name: Test Retries Success No Goto
steps:
  - name: RetrySuccessStep
    command: ["{script_path}"]
    output_capture: text
    retries: 2
    on:
      failure:
        goto: ErrorHandler

  - name: NormalStep
    command: ["echo", "Normal execution continues"]
    output_capture: text

  - name: ErrorHandler
    command: ["echo", "This should NOT be executed"]
    output_capture: text
    when:
      equals:
        left: "1"
        right: "0"  # Never true - this step should only run via goto
"""
    workflow_path = temp_workspace / "retry_success_workflow.yaml"
    workflow_path.write_text(workflow_content)

    # Clean up any previous state file
    state_file = Path("/tmp/retry_test_state_at71")
    if state_file.exists():
        state_file.unlink()

    # Load and execute workflow
    loader = WorkflowLoader(temp_workspace)
    workflow = loader.load(workflow_path)

    state_manager = StateManager(temp_workspace)
    state_manager.initialize(str(workflow_path))

    executor = WorkflowExecutor(
        workflow=workflow,
        workspace=temp_workspace,
        state_manager=state_manager
    )

    # Execute workflow
    final_state = executor.execute()

    # Verify the step succeeded after retry
    assert 'RetrySuccessStep' in final_state['steps']
    assert final_state['steps']['RetrySuccessStep']['exit_code'] == 0
    assert 'Retry succeeded' in final_state['steps']['RetrySuccessStep'].get('output', '')

    # Normal execution should continue
    assert 'NormalStep' in final_state['steps']
    assert final_state['steps']['NormalStep']['exit_code'] == 0
    assert 'Normal execution continues' in final_state['steps']['NormalStep'].get('output', '')

    # ErrorHandler should NOT have been executed (failure goto not triggered)
    # It may be present but skipped due to the when condition
    if 'ErrorHandler' in final_state['steps']:
        assert final_state['steps']['ErrorHandler'].get('skipped') == True


def test_at71_provider_retries_with_failure_goto(temp_workspace):
    """
    AT-71: Provider steps with retries should also trigger on.failure.goto after exhaustion.

    Provider steps have default retry behavior (retry on exit codes 1 and 124).
    """
    # Create a failing provider template
    workflow_content = """
version: "1.1"
name: Test Provider Retries with Goto

providers:
  failing_provider:
    command: ["sh", "-c", "echo 'Provider failed' && exit 1"]
    input_mode: argv

steps:
  - name: FailingProviderStep
    provider: failing_provider
    on:
      failure:
        goto: ProviderErrorHandler

  - name: SkippedStep
    command: ["echo", "This should be skipped"]

  - name: ProviderErrorHandler
    command: ["echo", "Handling provider error after retries"]
    output_capture: text
"""
    workflow_path = temp_workspace / "provider_retry_goto.yaml"
    workflow_path.write_text(workflow_content)

    # Load and execute workflow
    loader = WorkflowLoader(temp_workspace)
    workflow = loader.load(workflow_path)

    state_manager = StateManager(temp_workspace)
    state_manager.initialize(str(workflow_path))

    # Provider steps have default retry policy
    executor = WorkflowExecutor(
        workflow=workflow,
        workspace=temp_workspace,
        state_manager=state_manager
    )

    # Execute workflow
    final_state = executor.execute()

    # Provider step should have failed after retries
    assert 'FailingProviderStep' in final_state['steps']
    assert final_state['steps']['FailingProviderStep']['exit_code'] == 1

    # AT-71: Error handler should have been executed
    assert 'ProviderErrorHandler' in final_state['steps']
    assert final_state['steps']['ProviderErrorHandler']['exit_code'] == 0
    assert 'Handling provider error after retries' in final_state['steps']['ProviderErrorHandler'].get('output', '')

    # SkippedStep should have been bypassed
    assert 'SkippedStep' not in final_state['steps']


def test_at71_no_retries_immediate_failure_goto(temp_workspace):
    """
    AT-71: Steps with no retries should immediately trigger on.failure.goto.

    This verifies the existing behavior still works when retries are not configured.
    """
    workflow_content = """
version: "1.1"
name: Test No Retries Immediate Goto
steps:
  - name: FailImmediately
    command: ["sh", "-c", "exit 42"]
    # No retries configured - should fail immediately
    on:
      failure:
        goto: ImmediateHandler

  - name: SkippedStep
    command: ["echo", "Skipped"]

  - name: ImmediateHandler
    command: ["echo", "Immediate failure handled"]
    output_capture: text
"""
    workflow_path = temp_workspace / "no_retry_goto.yaml"
    workflow_path.write_text(workflow_content)

    # Load and execute
    loader = WorkflowLoader(temp_workspace)
    workflow = loader.load(workflow_path)

    state_manager = StateManager(temp_workspace)
    state_manager.initialize(str(workflow_path))

    executor = WorkflowExecutor(
        workflow=workflow,
        workspace=temp_workspace,
        state_manager=state_manager
    )

    final_state = executor.execute()

    # Should fail immediately
    assert 'FailImmediately' in final_state['steps']
    assert final_state['steps']['FailImmediately']['exit_code'] == 42

    # Handler should execute
    assert 'ImmediateHandler' in final_state['steps']
    assert final_state['steps']['ImmediateHandler']['exit_code'] == 0
    assert 'Immediate failure handled' in final_state['steps']['ImmediateHandler'].get('output', '')