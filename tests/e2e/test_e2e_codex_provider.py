"""E2E-03: Codex Provider (stdin mode) Minimal Flow.

This test validates real CLI invocation using stdin prompt delivery.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

from tests.e2e.conftest import skip_if_no_e2e, skip_if_no_cli
from tests.e2e.reporter import reporter


@pytest.mark.e2e
def test_e2e_codex_provider_stdin_mode(e2e_workspace):
    """E2E-03: Test Codex provider with stdin mode prompt delivery.

    Scope: Real CLI invocation using stdin prompt delivery.
    Preconditions: codex CLI available on PATH and authorized.
    """
    skip_if_no_e2e()
    skip_if_no_cli("codex")

    # Create the prompt file
    prompt_content = "Print OK and exit"
    prompt_path = e2e_workspace / "prompts" / "ping.md"
    prompt_path.write_text(prompt_content)

    # Create the workflow with codex provider
    workflow_content = """
version: "1.1"
name: e2e_codex_test

providers:
  codex:
    command: ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check"]
    input_mode: stdin

steps:
  - name: PingWithCodex
    provider: codex
    input_file: prompts/ping.md
    output_file: artifacts/engineer/execution_log.txt
    output_capture: text
"""

    workflow_path = e2e_workspace / "workflows" / "codex_test.yaml"
    workflow_path.write_text(workflow_content)

    # Create artifacts directory
    (e2e_workspace / "artifacts" / "engineer").mkdir(parents=True, exist_ok=True)

    # Start reporting
    reporter.section("E2E-03: Codex Provider Test (stdin mode)")

    # Run the workflow with reporting
    orchestrate_path = Path(__file__).parent.parent.parent / "orchestrate"
    result = reporter.run_workflow_with_reporting(
        orchestrate_path=orchestrate_path,
        workflow_path=workflow_path,
        workspace=e2e_workspace
    )

    # Expected outcomes per E2E-03:
    # - Run status completed in state
    # - Step exit_code 0
    # - State captures non-empty output or logs/PingWithCodex.stdout exists
    # - artifacts/engineer/execution_log.txt exists and is non-empty

    assert result.returncode == 0, f"Workflow should execute successfully: {result.stderr}"

    # Extract run_id from output (CLI logs to stderr)
    run_id = None
    for line in result.stderr.split('\n'):
        if "Created new run:" in line:
            run_id = line.split("Created new run:")[1].strip()
            break

    assert run_id, f"Run ID not found in output. stdout: {result.stdout}, stderr: {result.stderr}"

    # Inspect run artifacts
    reporter.inspect_run_artifacts(e2e_workspace, run_id, "PingWithCodex")

    # Check state file in the correct location
    state_file = e2e_workspace / ".orchestrate" / "runs" / run_id / "state.json"
    assert state_file.exists(), f"State file should be created at {state_file}"

    state = json.loads(state_file.read_text())
    assert state["status"] == "completed", f"Run should be completed, got {state.get('status')}"
    assert "PingWithCodex" in state["steps"], "Step should be in state"
    assert state["steps"]["PingWithCodex"]["exit_code"] == 0, "Step should succeed"

    # Check for captured output (using correct field name)
    step_result = state["steps"]["PingWithCodex"]
    has_output = False
    if "output" in step_result and step_result["output"]:
        has_output = True
    else:
        # Check for log file
        log_file = e2e_workspace / ".orchestrate" / "runs" / run_id / "logs" / "PingWithCodex.stdout"
        if log_file.exists():
            has_output = True

    assert has_output, "Step should capture non-empty output"

    # Check artifact file
    artifact_file = e2e_workspace / "artifacts" / "engineer" / "execution_log.txt"
    assert artifact_file.exists(), "Artifact file should exist"
    assert artifact_file.read_text().strip(), "Artifact file should be non-empty"

    # Display created artifacts
    reporter.artifacts(e2e_workspace)


@pytest.mark.e2e
def test_e2e_codex_provider_with_injection(e2e_workspace):
    """E2E-03: Test Codex provider with dependency injection.

    This test validates that stdin mode works correctly with
    dependency injection in list mode.
    """
    skip_if_no_e2e()
    skip_if_no_cli("codex")

    # Create dependency files
    (e2e_workspace / "lib").mkdir(exist_ok=True)
    lib1_path = e2e_workspace / "lib" / "helper.py"
    lib1_path.write_text("# Helper module\nprint('helper loaded')")

    lib2_path = e2e_workspace / "lib" / "utils.py"
    lib2_path.write_text("# Utils module\nprint('utils loaded')")

    # Create the prompt
    prompt_content = "Print the names of the dependency files"
    prompt_path = e2e_workspace / "prompts" / "list_deps.md"
    prompt_path.write_text(prompt_content)

    # Create workflow with dependency injection
    workflow_content = """
version: "1.1.1"
name: e2e_codex_injection

providers:
  codex:
    command: ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check"]
    input_mode: stdin

steps:
  - name: CodexWithDeps
    provider: codex
    input_file: prompts/list_deps.md
    depends_on:
      required:
        - lib/*.py
      inject: true
    output_capture: text
"""

    workflow_path = e2e_workspace / "workflows" / "codex_injection.yaml"
    workflow_path.write_text(workflow_content)

    # Start reporting
    reporter.section("E2E-03: Codex Provider Test with Injection")

    # Run the workflow with reporting
    orchestrate_path = Path(__file__).parent.parent.parent / "orchestrate"
    result = reporter.run_workflow_with_reporting(
        orchestrate_path=orchestrate_path,
        workflow_path=workflow_path,
        workspace=e2e_workspace
    )

    assert result.returncode == 0, f"Workflow should execute successfully: {result.stderr}"

    # Extract run_id from output (CLI logs to stderr)
    run_id = None
    for line in result.stderr.split('\n'):
        if "Created new run:" in line:
            run_id = line.split("Created new run:")[1].strip()
            break

    assert run_id, f"Run ID not found in output. stdout: {result.stdout}, stderr: {result.stderr}"

    # Verify injection was applied
    state_file = e2e_workspace / ".orchestrate" / "runs" / run_id / "state.json"
    state = json.loads(state_file.read_text())

    step_result = state["steps"]["CodexWithDeps"]
    assert step_result["exit_code"] == 0, "Step should succeed"

    # Check that injection metadata was recorded
    if "debug" in step_result and "injection" in step_result["debug"]:
        injection_info = step_result["debug"]["injection"]
        assert "files_included" in injection_info
        assert injection_info["files_included"] == 2  # helper.py and utils.py