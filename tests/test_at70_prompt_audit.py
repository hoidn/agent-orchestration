"""
Test AT-70: Prompt audit & masking.

With --debug, composed prompt text written to logs/<Step>.prompt.txt with secrets masked.
"""

import os
from pathlib import Path

import pytest


def test_at70_prompt_audit_with_debug(tmp_path):
    """Test AT-70: Debug mode writes prompt audit with secrets masked."""
    # Create test structure
    workflow_file = tmp_path / "workflow.yaml"
    prompt_file = tmp_path / "prompt.txt"

    # Set a secret in environment
    os.environ["MY_SECRET_KEY"] = "super-secret-value-123"

    try:
        # Write workflow with provider step using secrets
        workflow_file.write_text("""
version: "1.1"
providers:
  test_provider:
    command: ["echo", "${PROMPT}"]
    input_mode: "argv"
    defaults:
      model: "test-model"
steps:
  - name: TestStep
    provider: test_provider
    input_file: prompt.txt
    secrets: ["MY_SECRET_KEY"]
    output_capture: text
""")

        # Write prompt that will contain the secret directly (to test masking)
        # AT-73: Variables in prompt files are NOT substituted, so if we want to test masking,
        # the secret value needs to be literally in the file
        prompt_file.write_text("Testing with context: super-secret-value-123")

        # Run orchestrator with debug mode
        from orchestrator.loader import WorkflowLoader
        from orchestrator.state import StateManager
        from orchestrator.workflow.executor import WorkflowExecutor

        loader = WorkflowLoader(tmp_path)
        workflow = loader.load(workflow_file)

        # Initialize state manager with debug=True
        state_manager = StateManager(
            workspace=tmp_path,
            debug=True  # This enables prompt audit
        )

        # Initialize with context containing the secret value
        state_manager.initialize(workflow_file.name, {
            "api_key": "super-secret-value-123"
        })

        # Create executor with debug mode
        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=tmp_path,
            state_manager=state_manager,
            debug=True
        )

        # Execute the workflow
        result = executor.execute()

        # Check that prompt audit file was created
        prompt_audit_file = state_manager.logs_dir / "TestStep.prompt.txt"
        assert prompt_audit_file.exists(), "Prompt audit file should be created"

        # Read the audit file
        audit_content = prompt_audit_file.read_text()

        # Verify secret is masked
        assert "super-secret-value-123" not in audit_content, "Secret should be masked"
        assert "***" in audit_content, "Masked placeholder should be present"
        assert "Testing with context:" in audit_content, "Non-secret content should be preserved"

    finally:
        # Clean up environment
        del os.environ["MY_SECRET_KEY"]


def test_at70_no_audit_without_debug(tmp_path):
    """Test that prompt audit is NOT written without debug mode."""
    # Create test structure
    workflow_file = tmp_path / "workflow.yaml"
    prompt_file = tmp_path / "prompt.txt"

    # Write workflow
    workflow_file.write_text("""
version: "1.1"
providers:
  test_provider:
    command: ["echo", "${PROMPT}"]
    input_mode: "argv"
    defaults:
      model: "test-model"
steps:
  - name: TestStep
    provider: test_provider
    input_file: prompt.txt
    output_capture: text
""")

    # Write prompt
    prompt_file.write_text("Test prompt content")

    # Run orchestrator WITHOUT debug mode
    from orchestrator.loader import WorkflowLoader
    from orchestrator.state import StateManager
    from orchestrator.workflow.executor import WorkflowExecutor

    loader = WorkflowLoader(tmp_path)
    workflow = loader.load(workflow_file)

    # Initialize state manager without debug
    state_manager = StateManager(
        workspace=tmp_path,
        debug=False  # Debug disabled
    )

    state_manager.initialize(workflow_file.name, {})

    # Create executor without debug
    executor = WorkflowExecutor(
        workflow=workflow,
        workspace=tmp_path,
        state_manager=state_manager,
        debug=False
    )

    # Execute the workflow
    result = executor.execute()

    # Check that prompt audit file was NOT created
    prompt_audit_file = state_manager.logs_dir / "TestStep.prompt.txt"
    assert not prompt_audit_file.exists(), "Prompt audit file should not be created without debug"


def test_at70_multiple_secrets_masked(tmp_path):
    """Test that multiple secrets are all masked in prompt audit."""
    # Create test structure
    workflow_file = tmp_path / "workflow.yaml"
    prompt_file = tmp_path / "prompt.txt"

    # Set multiple secrets
    os.environ["API_KEY"] = "api-secret-456"
    os.environ["DB_PASSWORD"] = "database-pwd-789"

    try:
        # Write workflow
        workflow_file.write_text("""
version: "1.1"
providers:
  test_provider:
    command: ["echo", "${PROMPT}"]
    input_mode: "argv"
    defaults:
      model: "test-model"
steps:
  - name: TestStep
    provider: test_provider
    input_file: prompt.txt
    secrets: ["API_KEY", "DB_PASSWORD"]
    output_capture: text
""")

        # Write prompt with multiple secrets directly (AT-73: no variable substitution)
        prompt_file.write_text("""
API Key: api-secret-456
Database: database-pwd-789
Regular text here
""")

        # Run orchestrator with debug mode
        from orchestrator.loader import WorkflowLoader
        from orchestrator.state import StateManager
        from orchestrator.workflow.executor import WorkflowExecutor

        loader = WorkflowLoader(tmp_path)
        workflow = loader.load(workflow_file)

        # Initialize state manager with debug
        state_manager = StateManager(
            workspace=tmp_path,
            debug=True
        )

        # Initialize with context containing secret values
        state_manager.initialize(workflow_file.name, {
            "key": "api-secret-456",
            "db": "database-pwd-789"
        })

        # Create executor with debug
        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=tmp_path,
            state_manager=state_manager,
            debug=True
        )

        # Execute the workflow
        result = executor.execute()

        # Check audit file
        prompt_audit_file = state_manager.logs_dir / "TestStep.prompt.txt"
        assert prompt_audit_file.exists()

        audit_content = prompt_audit_file.read_text()

        # Verify all secrets are masked
        assert "api-secret-456" not in audit_content
        assert "database-pwd-789" not in audit_content
        assert audit_content.count("***") >= 2, "Should have multiple masked values"
        assert "Regular text here" in audit_content, "Non-secret text preserved"

    finally:
        # Clean up
        del os.environ["API_KEY"]
        del os.environ["DB_PASSWORD"]


def test_at70_prompt_audit_with_dependency_injection(tmp_path):
    """Test prompt audit works with dependency injection."""
    # Create test structure
    workflow_file = tmp_path / "workflow.yaml"
    prompt_file = tmp_path / "prompt.txt"
    dep_file = tmp_path / "data.txt"

    # Write dependency file
    dep_file.write_text("dependency content")

    # Write workflow with dependency injection
    workflow_file.write_text("""
version: "1.1.1"
providers:
  test_provider:
    command: ["echo", "${PROMPT}"]
    input_mode: "argv"
    defaults:
      model: "test-model"
steps:
  - name: TestStep
    provider: test_provider
    input_file: prompt.txt
    depends_on:
      required: ["data.txt"]
      inject: true
    output_capture: text
""")

    # Write prompt
    prompt_file.write_text("Original prompt content")

    # Run orchestrator with debug mode
    from orchestrator.loader import WorkflowLoader
    from orchestrator.state import StateManager
    from orchestrator.workflow.executor import WorkflowExecutor

    loader = WorkflowLoader(tmp_path)
    workflow = loader.load(workflow_file)

    # Initialize state manager with debug
    state_manager = StateManager(
        workspace=tmp_path,
        debug=True
    )

    state_manager.initialize(workflow_file.name, {})

    # Create executor with debug
    executor = WorkflowExecutor(
        workflow=workflow,
        workspace=tmp_path,
        state_manager=state_manager,
        debug=True
    )

    # Execute the workflow
    result = executor.execute()

    # Check audit file
    prompt_audit_file = state_manager.logs_dir / "TestStep.prompt.txt"
    assert prompt_audit_file.exists()

    audit_content = prompt_audit_file.read_text()

    # Verify injected content is in audit
    assert "Original prompt content" in audit_content
    assert "data.txt" in audit_content, "Injected file should be listed"
    # Check for the injection instruction (could be required or optional)
    assert ("The following required files are available:" in audit_content or
            "The following files are available:" in audit_content or
            "Files:" in audit_content)