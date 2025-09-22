"""E2E Test Reporter for enhanced observability of agent interactions.

This module provides real-time visibility into agent I/O during E2E tests
when ORCHESTRATE_E2E_VERBOSE=1 is set.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List


class E2ETestReporter:
    """Reporter for displaying agent I/O during E2E tests."""

    def __init__(self, enabled: Optional[bool] = None):
        """Initialize the reporter.

        Args:
            enabled: Whether to enable verbose output. If None, checks ORCHESTRATE_E2E_VERBOSE env var.
        """
        if enabled is None:
            enabled = os.getenv("ORCHESTRATE_E2E_VERBOSE") == "1"
        self.enabled = enabled
        self.indent = "  "

    def section(self, title: str) -> None:
        """Print a section header."""
        if not self.enabled:
            return
        print(f"\n{'=' * 60}")
        print(f"  {title}")
        print(f"{'=' * 60}")

    def subsection(self, title: str) -> None:
        """Print a subsection header."""
        if not self.enabled:
            return
        print(f"\n{'-' * 40}")
        print(f"  {title}")
        print(f"{'-' * 40}")

    def info(self, message: str, indent: int = 0) -> None:
        """Print an info message."""
        if not self.enabled:
            return
        prefix = self.indent * indent
        print(f"{prefix}{message}")

    def command(self, cmd: List[str], cwd: Optional[str] = None) -> None:
        """Display a command being executed."""
        if not self.enabled:
            return
        self.subsection("Command Execution")
        self.info("Command:", 1)
        self.info(" ".join(cmd), 2)
        if cwd:
            self.info(f"Working dir: {cwd}", 1)

    def prompt(self, prompt_file: Path, content: Optional[str] = None) -> None:
        """Display prompt content."""
        if not self.enabled:
            return
        self.subsection("Agent Input (Prompt)")
        self.info(f"File: {prompt_file}", 1)
        if content is None and prompt_file.exists():
            content = prompt_file.read_text()
        if content:
            self.info("Content:", 1)
            for line in content.splitlines():
                self.info(line, 2)

    def agent_output(self, output: str, truncate: int = 500) -> None:
        """Display agent output."""
        if not self.enabled:
            return
        self.subsection("Agent Response")
        lines = output.splitlines()
        if len(output) > truncate:
            # Show first and last parts
            head_lines = lines[:10]
            tail_lines = lines[-10:]
            for line in head_lines:
                self.info(line, 1)
            self.info(f"... ({len(lines) - 20} lines omitted) ...", 1)
            for line in tail_lines:
                self.info(line, 1)
        else:
            for line in lines:
                self.info(line, 1)

    def state_update(self, step_name: str, state: Dict[str, Any]) -> None:
        """Display state update for a step."""
        if not self.enabled:
            return
        self.subsection(f"State Update: {step_name}")
        if step_name in state.get("steps", {}):
            step_state = state["steps"][step_name]
            self.info(f"Exit code: {step_state.get('exit_code', 'N/A')}", 1)
            if "output" in step_state:
                output = step_state["output"]
                if isinstance(output, str):
                    self.info(f"Output length: {len(output)} chars", 1)
                elif isinstance(output, list):
                    self.info(f"Output lines: {len(output)}", 1)
                elif isinstance(output, dict):
                    self.info(f"Output keys: {', '.join(output.keys())}", 1)

    def artifacts(self, workspace: Path, pattern: str = "artifacts/**/*") -> None:
        """Display created artifacts."""
        if not self.enabled:
            return
        import glob
        artifacts = glob.glob(str(workspace / pattern), recursive=True)
        artifacts = [f for f in artifacts if Path(f).is_file()]
        if artifacts:
            self.subsection("Created Artifacts")
            for artifact in sorted(artifacts):
                rel_path = Path(artifact).relative_to(workspace)
                size = Path(artifact).stat().st_size
                self.info(f"{rel_path} ({size} bytes)", 1)

    def run_workflow_with_reporting(
        self,
        orchestrate_path: Path,
        workflow_path: Path,
        workspace: Path,
        env: Optional[Dict[str, str]] = None
    ) -> subprocess.CompletedProcess:
        """Run a workflow with enhanced reporting.

        Args:
            orchestrate_path: Path to orchestrate CLI script
            workflow_path: Path to workflow YAML file
            workspace: Working directory for execution
            env: Environment variables

        Returns:
            Completed process result
        """
        cmd = ["python", str(orchestrate_path), "run", str(workflow_path)]

        # Add --debug if verbose mode is enabled
        if self.enabled:
            cmd.append("--debug")

        # Prepare environment
        if env is None:
            env = os.environ.copy()
        env["ORCHESTRATE_E2E"] = "1"

        # Display command
        self.command(cmd, str(workspace))

        # Run the command
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(workspace),
            env=env
        )

        # Display output if verbose
        if self.enabled:
            if result.stdout:
                self.subsection("Orchestrator Output")
                for line in result.stdout.splitlines()[:20]:  # Limit to first 20 lines
                    self.info(line, 1)

            if result.stderr:
                self.subsection("Orchestrator Logs")
                # Parse for important info
                for line in result.stderr.splitlines():
                    if any(keyword in line for keyword in ["Created new run:", "ERROR", "WARNING", "Executing step"]):
                        self.info(line, 1)

        return result

    def inspect_run_artifacts(self, workspace: Path, run_id: str, step_name: str) -> None:
        """Inspect and display run artifacts for a step.

        Args:
            workspace: E2E test workspace
            run_id: Run ID from orchestrator
            step_name: Name of the step to inspect
        """
        if not self.enabled:
            return

        run_dir = workspace / ".orchestrate" / "runs" / run_id

        # Show prompt if it exists
        prompt_file = run_dir / "logs" / f"{step_name}.prompt.txt"
        if prompt_file.exists():
            self.prompt(prompt_file)

        # Show stdout if it exists
        stdout_file = run_dir / "logs" / f"{step_name}.stdout"
        if stdout_file.exists():
            content = stdout_file.read_text()
            self.agent_output(content)

        # Show state
        state_file = run_dir / "state.json"
        if state_file.exists():
            state = json.loads(state_file.read_text())
            self.state_update(step_name, state)


# Global reporter instance
reporter = E2ETestReporter()