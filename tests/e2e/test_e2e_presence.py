"""E2E-01: Test Presence - Basic E2E test infrastructure.

This test validates that:
1. E2E tests are discoverable via pytest -m e2e
2. Tests skip gracefully when ORCHESTRATE_E2E is not set
3. Tests skip gracefully when required CLIs are unavailable
"""

import os
import subprocess
from pathlib import Path

import pytest

from tests.e2e.conftest import skip_if_no_e2e, skip_if_no_cli


@pytest.mark.e2e
def test_e2e_infrastructure_present():
    """E2E-01: Verify E2E test infrastructure exists and is discoverable.

    This test validates the basic E2E test presence requirement.
    It will skip gracefully when ORCHESTRATE_E2E is not set.
    """
    skip_if_no_e2e()

    # If we get here, E2E tests are enabled
    assert os.getenv("ORCHESTRATE_E2E"), "E2E tests are enabled"

    # Verify we can import the orchestrator modules
    from orchestrator.cli.main import main
    from orchestrator.loader import WorkflowLoader
    from orchestrator.state import StateManager

    # Basic smoke test that modules are importable
    assert main is not None
    assert WorkflowLoader is not None
    assert StateManager is not None


@pytest.mark.e2e
def test_e2e_cli_detection():
    """E2E-01: Test CLI detection and graceful skipping.

    This test validates that we can detect available CLIs
    and skip tests when they're not available.
    """
    skip_if_no_e2e()

    # Check for orchestrate CLI
    orchestrate_path = Path(__file__).parent.parent.parent / "orchestrate"
    assert orchestrate_path.exists(), f"orchestrate CLI script should exist at {orchestrate_path}"

    # Test that we can run orchestrate --help
    result = subprocess.run(
        ["python", str(orchestrate_path), "--help"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"orchestrate --help should succeed: {result.stderr}"
    assert "Multi-Agent Orchestration System" in result.stdout


@pytest.mark.e2e
def test_e2e_claude_cli_skip():
    """E2E-01: Test that claude CLI tests skip gracefully when unavailable."""
    skip_if_no_e2e()

    # This test demonstrates graceful skipping when claude is not available
    import shutil
    if not shutil.which("claude"):
        pytest.skip("claude CLI not available - test skipped gracefully")

    # If claude is available, just pass
    assert True, "claude CLI is available"


@pytest.mark.e2e
def test_e2e_codex_cli_skip():
    """E2E-01: Test that codex CLI tests skip gracefully when unavailable."""
    skip_if_no_e2e()

    # This test demonstrates graceful skipping when codex is not available
    import shutil
    if not shutil.which("codex"):
        pytest.skip("codex CLI not available - test skipped gracefully")

    # If codex is available, just pass
    assert True, "codex CLI is available"


@pytest.mark.e2e
def test_e2e_workspace_setup(e2e_workspace):
    """E2E-01: Test E2E workspace fixture setup.

    This validates that the E2E workspace fixture creates
    the expected directory structure for E2E tests.
    """
    skip_if_no_e2e()

    # Verify all expected directories exist
    expected_dirs = [
        "workflows",
        "prompts",
        "artifacts",
        "inbox",
        "processed",
        "failed",
        ".orchestrate"
    ]

    for dir_name in expected_dirs:
        dir_path = e2e_workspace / dir_name
        assert dir_path.exists(), f"Directory {dir_name} should exist"
        assert dir_path.is_dir(), f"{dir_name} should be a directory"

    # Verify we're in the workspace directory
    assert Path.cwd() == e2e_workspace, "Should be in workspace directory"


@pytest.mark.e2e
def test_e2e_minimal_workflow_execution(e2e_workspace):
    """E2E-01: Test minimal workflow execution without real CLIs.

    This test validates that the orchestrator can execute
    a simple workflow that doesn't require external CLIs.
    """
    skip_if_no_e2e()

    # Create a minimal workflow
    workflow_content = """
version: "1.1"
name: e2e_minimal

steps:
  - name: Echo
    command: echo "E2E test successful"
    output_capture: text
"""

    workflow_path = e2e_workspace / "workflows" / "minimal.yaml"
    workflow_path.write_text(workflow_content)

    # Run the workflow
    orchestrate_path = Path(__file__).parent.parent.parent / "orchestrate"
    result = subprocess.run(
        ["python", str(orchestrate_path), "run", str(workflow_path)],
        capture_output=True,
        text=True,
        cwd=str(e2e_workspace)
    )

    # Verify successful execution
    assert result.returncode == 0, f"Workflow should execute successfully: {result.stderr}"

    # Check that state file was created
    state_file = e2e_workspace / ".orchestrate" / "state.json"
    assert state_file.exists(), "State file should be created"

    # Verify state contains expected output
    import json
    state = json.loads(state_file.read_text())
    assert state["run"]["status"] == "completed"
    assert "Echo" in state["steps"]
    assert state["steps"]["Echo"]["exit_code"] == 0
    assert "E2E test successful" in state["steps"]["Echo"]["text"]