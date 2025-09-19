#!/usr/bin/env python3
"""Standalone E2E test runner with verbose output for debugging."""

import json
import os
import sys
import tempfile
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from tests.e2e.reporter import E2ETestReporter


def run_codex_test():
    """Run a simple Codex E2E test with verbose output."""

    # Enable verbose reporting
    reporter = E2ETestReporter(enabled=True)

    # Create a temporary workspace
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # Create necessary directories
        (workspace / "workflows").mkdir()
        (workspace / "prompts").mkdir()
        (workspace / "artifacts" / "engineer").mkdir(parents=True)

        reporter.section("E2E Test: Codex Provider (stdin mode)")

        # Create prompt file
        prompt_content = "Print 'Hello from Codex' and exit"
        prompt_path = workspace / "prompts" / "test.md"
        prompt_path.write_text(prompt_content)
        reporter.prompt(prompt_path, prompt_content)

        # Create workflow
        workflow_content = """
version: "1.1"
name: e2e_codex_demo

providers:
  codex:
    command: ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check"]
    input_mode: stdin

steps:
  - name: TestCodex
    provider: codex
    input_file: prompts/test.md
    output_file: artifacts/engineer/output.txt
    output_capture: text
"""
        workflow_path = workspace / "workflows" / "test.yaml"
        workflow_path.write_text(workflow_content)

        reporter.subsection("Workflow Created")
        reporter.info(f"Path: {workflow_path}", 1)

        # Run the orchestrator
        orchestrate_path = project_root / "orchestrate"
        result = reporter.run_workflow_with_reporting(
            orchestrate_path=orchestrate_path,
            workflow_path=workflow_path,
            workspace=workspace
        )

        if result.returncode != 0:
            reporter.subsection("ERROR: Workflow failed")
            reporter.info(f"Exit code: {result.returncode}", 1)
            reporter.info("STDERR:", 1)
            for line in result.stderr.splitlines():
                reporter.info(line, 2)
            return False

        # Extract run ID
        import re
        run_id_match = re.search(r"Created new run: ([a-zA-Z0-9\-]+)", result.stderr)
        if not run_id_match:
            reporter.subsection("ERROR: Could not find run ID")
            return False

        run_id = run_id_match.group(1)
        reporter.info(f"Run ID: {run_id}", 1)

        # Inspect artifacts
        reporter.inspect_run_artifacts(workspace, run_id, "TestCodex")

        # Check state
        state_file = workspace / ".orchestrate" / "runs" / run_id / "state.json"
        if state_file.exists():
            state = json.loads(state_file.read_text())
            reporter.state_update("TestCodex", state)

            if state.get("status") == "completed":
                reporter.section("✅ TEST PASSED")
                return True

        reporter.section("❌ TEST FAILED")
        return False


def run_simple_command_test():
    """Run a simple command test that doesn't require external CLIs."""

    # Enable verbose reporting
    reporter = E2ETestReporter(enabled=True)

    # Create a temporary workspace
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # Create necessary directories
        (workspace / "workflows").mkdir()

        reporter.section("E2E Test: Simple Command (no external CLI)")

        # Create workflow
        workflow_content = """
version: "1.1"
name: simple_test

steps:
  - name: Echo
    command: echo "Hello from E2E test"
    output_capture: text

  - name: ListFiles
    command: ls -la
    output_capture: lines
"""
        workflow_path = workspace / "workflows" / "simple.yaml"
        workflow_path.write_text(workflow_content)

        reporter.subsection("Workflow Created")
        reporter.info(f"Path: {workflow_path}", 1)

        # Run the orchestrator
        orchestrate_path = project_root / "orchestrate"
        result = reporter.run_workflow_with_reporting(
            orchestrate_path=orchestrate_path,
            workflow_path=workflow_path,
            workspace=workspace
        )

        if result.returncode != 0:
            reporter.subsection("ERROR: Workflow failed")
            reporter.info(f"Exit code: {result.returncode}", 1)
            reporter.info("STDERR:", 1)
            for line in result.stderr.splitlines():
                reporter.info(line, 2)
            return False

        # Extract run ID
        import re
        run_id_match = re.search(r"Created new run: ([a-zA-Z0-9\-]+)", result.stderr)
        if not run_id_match:
            reporter.subsection("ERROR: Could not find run ID")
            return False

        run_id = run_id_match.group(1)
        reporter.info(f"Run ID: {run_id}", 1)

        # Check each step
        state_file = workspace / ".orchestrate" / "runs" / run_id / "state.json"
        if state_file.exists():
            state = json.loads(state_file.read_text())

            # Check Echo step
            reporter.inspect_run_artifacts(workspace, run_id, "Echo")
            reporter.state_update("Echo", state)

            # Check ListFiles step
            reporter.inspect_run_artifacts(workspace, run_id, "ListFiles")
            reporter.state_update("ListFiles", state)

            # Display any created artifacts
            reporter.artifacts(workspace)

            if state.get("status") == "completed":
                reporter.section("✅ TEST PASSED")
                return True

        reporter.section("❌ TEST FAILED")
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run E2E test with verbose output")
    parser.add_argument(
        "--test",
        choices=["codex", "simple"],
        default="simple",
        help="Which test to run (default: simple)"
    )

    args = parser.parse_args()

    # Set environment variables
    os.environ["ORCHESTRATE_E2E"] = "1"
    os.environ["ORCHESTRATE_E2E_VERBOSE"] = "1"

    if args.test == "codex":
        # Check if codex is available
        import shutil
        if not shutil.which("codex"):
            print("ERROR: codex CLI not found on PATH")
            print("Please install codex or run with --test=simple")
            sys.exit(1)

        success = run_codex_test()
    else:
        success = run_simple_command_test()

    sys.exit(0 if success else 1)