"""Step executor for running commands and providers with output capture.

Implements step execution per specs/providers.md and specs/io.md.
"""

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from orchestrator.workflow.types import Step, OutputCapture as OutputCaptureEnum
from orchestrator.state.run_state import StepState
from .output_capture import OutputCapture, OutputCaptureMode, CaptureResult


@dataclass
class ExecutionResult:
    """Result of step execution."""
    exit_code: int
    stdout: bytes
    stderr: bytes
    duration_ms: int
    capture_result: Optional[CaptureResult] = None
    error_context: Optional[Dict[str, Any]] = None


class StepExecutor:
    """Executes workflow steps with output capture and state updates."""

    def __init__(
        self,
        workspace: Path,
        run_root: Path,
        providers: Optional[Dict[str, Dict[str, Any]]] = None
    ):
        """Initialize step executor.

        Args:
            workspace: Workspace root directory
            run_root: Run-specific directory for logs and state
            providers: Provider templates from workflow
        """
        self.workspace = workspace
        self.run_root = run_root
        self.log_dir = run_root / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.providers = providers or {}

    def execute(
        self,
        step: Step,
        context: Dict[str, str],
        loop_vars: Optional[Dict[str, str]] = None
    ) -> Tuple[StepState, ExecutionResult]:
        """Execute a step and return state and execution result.

        Args:
            step: Step to execute
            context: Current variable context
            loop_vars: Optional loop variables (item, loop.index, loop.total)

        Returns:
            Tuple of (StepState, ExecutionResult)
        """
        # Determine output capture mode - map from workflow enum to executor enum
        capture_mode = OutputCaptureMode.TEXT  # default
        if step.output_capture == OutputCaptureEnum.LINES:
            capture_mode = OutputCaptureMode.LINES
        elif step.output_capture == OutputCaptureEnum.JSON:
            capture_mode = OutputCaptureMode.JSON
        else:
            capture_mode = OutputCaptureMode.TEXT

        # Initialize state
        state = StepState(status="running")
        state.started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Build command based on step type
        if step.command:
            command = step.command
            stdin_input = None
        elif step.provider:
            command, stdin_input = self._build_provider_command(step, context, loop_vars)
        elif step.wait_for or step.for_each:
            # Other step types (wait_for, for_each) not implemented yet
            state.status = "failed"
            state.exit_code = 2
            state.error = {
                "message": f"Step type not yet implemented: {type(step).__name__}",
                "exit_code": 2
            }
            return state, ExecutionResult(
                exit_code=2,
                stdout=b"",
                stderr=b"",
                duration_ms=0
            )

        # Execute command
        start_time = time.time()
        try:
            # Build environment
            env = os.environ.copy()
            if step.env:
                env.update(step.env)

            # Handle secrets
            if step.secrets:
                missing_secrets = []
                for secret_name in step.secrets:
                    if secret_name in os.environ:
                        env[secret_name] = os.environ[secret_name]
                    else:
                        missing_secrets.append(secret_name)

                if missing_secrets:
                    # Missing secrets cause exit code 2
                    state.status = "failed"
                    state.exit_code = 2
                    state.error = {
                        "message": "Missing required secrets",
                        "exit_code": 2,
                        "context": {
                            "missing_secrets": missing_secrets
                        }
                    }
                    return state, ExecutionResult(
                        exit_code=2,
                        stdout=b"",
                        stderr=b"",
                        duration_ms=0
                    )

            # Run subprocess
            result = subprocess.run(
                command,
                input=stdin_input,
                capture_output=True,
                cwd=self.workspace,
                env=env,
                timeout=step.timeout_sec if hasattr(step, 'timeout_sec') and step.timeout_sec else None
            )

            exit_code = result.returncode
            stdout = result.stdout
            stderr = result.stderr

        except subprocess.TimeoutExpired as e:
            # Timeout exits with 124
            exit_code = 124
            stdout = e.stdout or b""
            stderr = e.stderr or b""
            state.error = {
                "message": f"Command timed out after {step.timeout_sec} seconds",
                "exit_code": 124
            }

        except Exception as e:
            # Other errors
            exit_code = 2
            stdout = b""
            stderr = str(e).encode('utf-8')
            state.error = {
                "message": str(e),
                "exit_code": 2
            }

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        # Capture output
        output_capture = OutputCapture(capture_mode, self.log_dir)

        # Determine output file if specified
        output_file = None
        if step.output_file:
            output_file = self.workspace / step.output_file

        capture_result = output_capture.capture(
            stdout,
            stderr,
            step.name,
            allow_parse_error=step.allow_parse_error if hasattr(step, 'allow_parse_error') else False,
            output_file=output_file
        )

        # Update state with capture results
        state.exit_code = exit_code
        state.completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        state.duration_ms = duration_ms

        # Set status based on exit code
        if exit_code == 0:
            state.status = "completed"
        else:
            state.status = "failed"

        # Handle JSON parse errors
        if capture_mode == OutputCaptureMode.JSON and capture_result.json_parse_error:
            if not step.allow_parse_error:
                # JSON parse error causes exit code 2
                state.exit_code = 2
                state.status = "failed"
                if not state.error:
                    state.error = {}
                state.error["message"] = f"JSON parse error: {capture_result.json_parse_error}"
                state.error["exit_code"] = 2

        # Store capture results in state
        if capture_mode == OutputCaptureMode.TEXT:
            state.output = capture_result.output
        elif capture_mode == OutputCaptureMode.LINES:
            state.lines = capture_result.lines
        elif capture_mode == OutputCaptureMode.JSON:
            if capture_result.json_data is not None:
                state.json = capture_result.json_data
            elif step.allow_parse_error:
                # Store as text when parse error is allowed
                state.output = capture_result.output
                if not state.debug:
                    state.debug = {}
                state.debug["json_parse_error"] = capture_result.json_parse_error

        # Set truncated flag if needed
        if capture_result.truncated:
            state.truncated = True

        # Record debug info
        if not state.debug:
            state.debug = {}
        state.debug["command"] = command
        state.debug["cwd"] = str(self.workspace)
        state.debug["env_count"] = len(env)

        execution_result = ExecutionResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            capture_result=capture_result
        )

        return state, execution_result

    def _build_provider_command(
        self,
        step: Step,
        context: Dict[str, str],
        loop_vars: Optional[Dict[str, str]] = None
    ) -> Tuple[List[str], Optional[bytes]]:
        """Build command for provider step.

        Args:
            step: Provider step
            context: Variable context
            loop_vars: Optional loop variables

        Returns:
            Tuple of (command, stdin_input)
        """
        # For now, return a simple echo command for testing
        # Full provider implementation will come later
        if step.input_file:
            input_path = self.workspace / step.input_file
            if input_path.exists():
                prompt = input_path.read_text()
            else:
                prompt = f"File not found: {step.input_file}"
        else:
            prompt = "No input file specified"

        # Simple test command that echoes the prompt
        command = ["echo", prompt]
        stdin_input = None

        return command, stdin_input