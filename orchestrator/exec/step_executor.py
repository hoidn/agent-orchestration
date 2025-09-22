"""
Step executor module for running commands and capturing output.
Implements basic command execution with output capture.
"""

import subprocess
import os
import shlex
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass

from .output_capture import OutputCapture, CaptureMode, CaptureResult
from ..fsq.wait import WaitFor, WaitForConfig, WaitForResult
from ..security.secrets import SecretsManager, SecretsContext


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

    def __init__(self, workspace: Path, logs_dir: Optional[Path] = None, secrets_manager: Optional[SecretsManager] = None):
        """
        Initialize step executor.

        Args:
            workspace: Base workspace directory
            logs_dir: Directory for logs (default: workspace/logs)
            secrets_manager: Manager for secrets handling and masking
        """
        self.workspace = workspace
        self.output_capture = OutputCapture(workspace, logs_dir)
        self.secrets_manager = secrets_manager or SecretsManager()

    def execute_command(
        self,
        step_name: str,
        command: Union[str, List[str]],
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        secrets: Optional[List[str]] = None,
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
            secrets: List of secret env var names to validate and mask
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

        # Resolve secrets and setup environment (AT-41,42,54,55)
        secrets_context = self.secrets_manager.resolve_secrets(
            declared_secrets=secrets,
            step_env=env
        )

        # Check for missing secrets (AT-41)
        if secrets_context.missing_secrets:
            error = {
                "type": "missing_secrets",
                "message": f"Missing required secrets: {', '.join(secrets_context.missing_secrets)}",
                "context": {"missing_secrets": secrets_context.missing_secrets}
            }
            capture_result = CaptureResult(
                mode=CaptureMode.TEXT,
                output="",
                lines=[],
                json_data=None,
                exit_code=2,
                error=error
            )
            return ExecutionResult(
                step_name=step_name,
                exit_code=2,
                capture_result=capture_result,
                duration_ms=0,
                error=error
            )

        # Use the composed environment from secrets resolution
        process_env = secrets_context.child_env

        # Record start time
        start_time = time.time()

        # Convert command to argv array if needed
        if isinstance(command, str):
            # Parse shell command into argv array using shlex for proper quoting/escaping
            command_argv = shlex.split(command)
        elif isinstance(command, list):
            # Already an argv array
            command_argv = command
        else:
            raise ValueError(f"Invalid command type: {type(command)}. Expected str or list.")

        try:
            # Execute command using argv mode (no shell=True for security)
            result = subprocess.run(
                command_argv,
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

        # Mask secrets in captured output (AT-42)
        if capture_result.output:
            capture_result.output = self.secrets_manager.mask_text(capture_result.output)
        if capture_result.lines:
            capture_result.lines = [self.secrets_manager.mask_text(line) for line in capture_result.lines]
        if capture_result.json_data:
            capture_result.json_data = self.secrets_manager.mask_dict(capture_result.json_data)

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

    def execute_wait_for(
        self,
        step_name: str,
        wait_config: Dict[str, Any],
    ) -> ExecutionResult:
        """
        Execute a wait_for step that polls for files.

        Args:
            step_name: Name of the step for logging
            wait_config: Wait configuration dict with glob, timeout_sec, poll_ms, min_count

        Returns:
            ExecutionResult with wait operation results
        """
        # Extract wait configuration with defaults
        glob_pattern = wait_config.get('glob', '')
        timeout_sec = wait_config.get('timeout_sec', 300)
        poll_ms = wait_config.get('poll_ms', 500)
        min_count = wait_config.get('min_count', 1)

        # Create wait configuration
        config = WaitForConfig(
            glob_pattern=glob_pattern,
            timeout_sec=timeout_sec,
            poll_ms=poll_ms,
            min_count=min_count,
            workspace=str(self.workspace)
        )

        # Execute wait operation
        waiter = WaitFor(config)
        wait_result = waiter.execute()

        # Create a capture result for consistency with other step types
        # Wait steps don't have stdout/stderr, but we can record the files found
        capture_result = CaptureResult(
            mode=CaptureMode.LINES,  # Use lines mode to store file list
            output=None,
            lines=wait_result.files if wait_result.files else [],
            json_data=None,
            truncated=False,
            exit_code=wait_result.exit_code,
            error=None,
            debug=None
        )

        # Handle errors from wait_for (AT-18 for timeout, AT-61 for path safety)
        error = wait_result.error  # May be set by path safety check
        if not error and wait_result.timed_out:
            error = {
                "type": "timeout",
                "message": f"Wait timed out after {timeout_sec} seconds",
                "context": {
                    "timeout_sec": timeout_sec,
                    "files_found": len(wait_result.files),
                    "min_count_required": min_count
                }
            }

        # Create result with wait-specific state (AT-19)
        result = ExecutionResult(
            step_name=step_name,
            exit_code=wait_result.exit_code,
            capture_result=capture_result,
            duration_ms=wait_result.wait_duration_ms,
            error=error
        )

        # Add wait-specific fields to the state dict
        def to_wait_state_dict() -> Dict[str, Any]:
            state: Dict[str, Any] = {
                "exit_code": wait_result.exit_code,
                "files": wait_result.files,
                "wait_duration_ms": wait_result.wait_duration_ms,
                "poll_count": wait_result.poll_count,
                "timed_out": wait_result.timed_out
            }
            if error:
                state["error"] = error
            return state

        # Override to_state_dict for wait results
        result.to_state_dict = to_wait_state_dict

        return result