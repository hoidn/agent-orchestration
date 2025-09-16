"""
Step executor module for running commands and capturing output.
Implements basic command execution with output capture.
"""

import subprocess
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union
from dataclasses import dataclass

from .output_capture import OutputCapture, CaptureMode, CaptureResult


@dataclass
class ExecutionResult:
    """Result of step execution."""
    step_name: str
    exit_code: int
    capture_result: CaptureResult
    duration_ms: int
    error: Optional[Dict[str, Any]] = None

    def to_state_dict(self) -> Dict[str, Any]:
        """Convert to state format for recording."""
        result = {
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            **self.capture_result.to_state_dict()
        }
        if self.error:
            result["error"] = self.error
        return result


class StepExecutor:
    """
    Executes workflow steps with output capture.
    Handles command execution, environment setup, and result processing.
    """

    def __init__(self, workspace: Path, logs_dir: Optional[Path] = None):
        """
        Initialize step executor.

        Args:
            workspace: Base workspace directory
            logs_dir: Directory for logs (default: workspace/logs)
        """
        self.workspace = workspace
        self.output_capture = OutputCapture(workspace, logs_dir)

    def execute_command(
        self,
        step_name: str,
        command: str,
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        timeout_sec: Optional[int] = None,
        output_capture: CaptureMode = CaptureMode.TEXT,
        output_file: Optional[Path] = None,
        allow_parse_error: bool = False,
    ) -> ExecutionResult:
        """
        Execute a command step with output capture.

        Args:
            step_name: Name of the step for logging
            command: Command to execute
            cwd: Working directory (default: workspace)
            env: Environment variables to add/override
            timeout_sec: Timeout in seconds
            output_capture: Capture mode (text/lines/json)
            output_file: Optional file to tee output to
            allow_parse_error: For JSON mode, whether to allow parse errors

        Returns:
            ExecutionResult with captured output and metadata
        """
        import time

        # Setup working directory
        working_dir = cwd or self.workspace

        # Setup environment
        process_env = os.environ.copy()
        if env:
            process_env.update(env)

        # Record start time
        start_time = time.time()

        try:
            # Execute command
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(working_dir),
                env=process_env,
                capture_output=True,
                timeout=timeout_sec,
            )

            exit_code = result.returncode
            stdout = result.stdout
            stderr = result.stderr
            error = None

        except subprocess.TimeoutExpired as e:
            # Timeout: exit code 124 per spec
            exit_code = 124
            stdout = e.stdout or b""
            stderr = e.stderr or b""
            error = {
                "type": "timeout",
                "message": f"Command timed out after {timeout_sec} seconds",
                "context": {"timeout_sec": timeout_sec}
            }

        except Exception as e:
            # Other execution errors
            exit_code = 1
            stdout = b""
            stderr = str(e).encode('utf-8')
            error = {
                "type": "execution_error",
                "message": str(e),
                "context": {}
            }

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        # Process output through capture pipeline
        capture_result = self.output_capture.capture(
            stdout=stdout,
            stderr=stderr,
            step_name=step_name,
            mode=output_capture,
            output_file=output_file,
            allow_parse_error=allow_parse_error,
            exit_code=exit_code,
        )

        # Override exit code if capture failed (e.g., JSON parse error)
        if capture_result.exit_code != 0:
            exit_code = capture_result.exit_code
            if capture_result.error:
                error = capture_result.error

        return ExecutionResult(
            step_name=step_name,
            exit_code=exit_code,
            capture_result=capture_result,
            duration_ms=duration_ms,
            error=error,
        )