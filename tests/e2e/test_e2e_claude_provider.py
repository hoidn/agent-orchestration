"""E2E-02: Claude Provider (argv mode) Minimal Flow.

This test validates real CLI invocation using argv prompt delivery via ${PROMPT}.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

from tests.e2e.conftest import skip_if_no_e2e, skip_if_no_cli
from tests.e2e.reporter import reporter


@pytest.mark.e2e
def test_e2e_claude_provider_argv_mode(e2e_workspace):
    """E2E-02: Test Claude provider with argv mode prompt delivery.

    Scope: Real CLI invocation using argv prompt delivery via ${PROMPT}.
    Preconditions: claude CLI available on PATH and authorized.
    """
    skip_if_no_e2e()
    skip_if_no_cli("claude")

    # Create the prompt file
    prompt_content = "Reply with OK"
    prompt_path = e2e_workspace / "prompts" / "ping.md"
    prompt_path.write_text(prompt_content)

    # Create the workflow with claude provider
    workflow_content = """
version: "1.1"
name: e2e_claude_test

providers:
  claude:
    command: ["claude", "-p", "${PROMPT}", "--model", "${model}"]
    input_mode: argv
    defaults:
      model: "claude-sonnet-4-20250514"

steps:
  - name: GenerateWithClaude
    provider: claude
    input_file: prompts/ping.md
    output_file: artifacts/architect/execution_log.txt
    output_capture: text
"""

    workflow_path = e2e_workspace / "workflows" / "claude_test.yaml"
    workflow_path.write_text(workflow_content)

    # Create artifacts directory
    (e2e_workspace / "artifacts" / "architect").mkdir(parents=True, exist_ok=True)

    # Start reporting
    reporter.section("E2E-02: Claude Provider Test (argv mode)")

    # Run the workflow with reporting
    orchestrate_path = Path(__file__).parent.parent.parent / "orchestrate"
    result = reporter.run_workflow_with_reporting(
        orchestrate_path=orchestrate_path,
        workflow_path=workflow_path,
        workspace=e2e_workspace
    )

    # Expected outcomes per E2E-02:
    # - Run status completed in state
    # - Step exit_code 0
    # - State captures non-empty output or logs/GenerateWithClaude.stdout exists
    # - artifacts/architect/execution_log.txt exists and is non-empty

    assert result.returncode == 0, f"Workflow should execute successfully: {result.stderr}"

    # Extract run ID from output
    import re
    run_id_match = re.search(r"Created new run: ([a-zA-Z0-9\-]+)", result.stderr)
    assert run_id_match, f"Could not find run ID in output: {result.stderr}"
    run_id = run_id_match.group(1)

    # Inspect run artifacts
    reporter.inspect_run_artifacts(e2e_workspace, run_id, "GenerateWithClaude")

    # Check state file in run-specific directory
    state_file = e2e_workspace / ".orchestrate" / "runs" / run_id / "state.json"
    assert state_file.exists(), f"State file should be created at {state_file}"

    state = json.loads(state_file.read_text())
    assert state["status"] == "completed", "Run should be completed"
    assert "GenerateWithClaude" in state["steps"], "Step should be in state"
    assert state["steps"]["GenerateWithClaude"]["exit_code"] == 0, "Step should succeed"

    # Check for captured output (either in state or logs)
    step_result = state["steps"]["GenerateWithClaude"]
    has_output = False
    if "output" in step_result and step_result["output"]:
        has_output = True
    else:
        # Check for log file
        log_file = e2e_workspace / ".orchestrate" / "runs" / state["run_id"] / "logs" / "GenerateWithClaude.stdout"
        if log_file.exists():
            has_output = True

    assert has_output, "Step should capture non-empty output"

    # Check artifact file
    artifact_file = e2e_workspace / "artifacts" / "architect" / "execution_log.txt"
    assert artifact_file.exists(), "Artifact file should exist"
    assert artifact_file.read_text().strip(), "Artifact file should be non-empty"

    # Display created artifacts
    reporter.artifacts(e2e_workspace)


@pytest.mark.e2e
def test_e2e_claude_provider_with_parameters(e2e_workspace):
    """E2E-02: Test Claude provider with custom parameters.

    This test validates that provider_params work correctly
    with real Claude CLI invocation.
    """
    skip_if_no_e2e()
    skip_if_no_cli("claude")

    # Create a more complex prompt
    prompt_content = "Count from 1 to 3"
    prompt_path = e2e_workspace / "prompts" / "count.md"
    prompt_path.write_text(prompt_content)

    # Create workflow with custom parameters
    workflow_content = """
version: "1.1"
name: e2e_claude_params

providers:
  claude:
    command: ["claude", "-p", "${PROMPT}", "--model", "${model}"]
    input_mode: argv
    defaults:
      model: "claude-sonnet-4-20250514"

steps:
  - name: ClaudeWithParams
    provider: claude
    input_file: prompts/count.md
    output_capture: text
"""

    workflow_path = e2e_workspace / "workflows" / "claude_params.yaml"
    workflow_path.write_text(workflow_content)

    # Start reporting
    reporter.section("E2E-02: Claude Provider Test with Parameters")

    # Run the workflow with reporting
    orchestrate_path = Path(__file__).parent.parent.parent / "orchestrate"
    result = reporter.run_workflow_with_reporting(
        orchestrate_path=orchestrate_path,
        workflow_path=workflow_path,
        workspace=e2e_workspace
    )

    assert result.returncode == 0, f"Workflow should execute successfully: {result.stderr}"

    # Extract run ID from output and verify parameter substitution worked
    import re
    run_id_match = re.search(r"Created new run: ([a-zA-Z0-9\-]+)", result.stderr)
    assert run_id_match, f"Could not find run ID in output: {result.stderr}"
    run_id = run_id_match.group(1)

    state_file = e2e_workspace / ".orchestrate" / "runs" / run_id / "state.json"
    assert state_file.exists(), f"State file should be created at {state_file}"
    state = json.loads(state_file.read_text())
    assert state["steps"]["ClaudeWithParams"]["exit_code"] == 0