"""Output capture handling with mode-specific limits and truncation.

Implements the spec from specs/io.md:
- text: 8 KiB limit in state
- lines: 10,000 lines limit in state
- json: 1 MiB parse buffer
"""

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

class OutputCaptureMode(Enum):
    """Output capture modes as defined in specs/io.md."""
    TEXT = "text"
    LINES = "lines"
    JSON = "json"


@dataclass
class CaptureResult:
    """Result of output capture with mode-specific data."""
    mode: OutputCaptureMode
    output: Optional[str] = None  # For text mode
    lines: Optional[List[str]] = None  # For lines mode
    json_data: Optional[Any] = None  # For json mode
    truncated: bool = False
    json_parse_error: Optional[str] = None
    stdout_file: Optional[Path] = None  # When spilled to logs
    stderr_file: Optional[Path] = None  # When stderr is non-empty


class OutputCapture:
    """Handles output capture with mode-specific limits per specs/io.md."""

    # Limits from specs/io.md
    TEXT_LIMIT_BYTES = 8 * 1024  # 8 KiB
    LINES_LIMIT_COUNT = 10_000  # 10,000 lines
    JSON_BUFFER_LIMIT = 1024 * 1024  # 1 MiB

    def __init__(self, mode: OutputCaptureMode, log_dir: Optional[Path] = None):
        """Initialize output capture handler.

        Args:
            mode: Capture mode (text/lines/json)
            log_dir: Directory for spill files when truncated
        """
        self.mode = mode
        self.log_dir = log_dir

    def capture(
        self,
        stdout: bytes,
        stderr: bytes,
        step_name: str,
        allow_parse_error: bool = False,
        output_file: Optional[Path] = None
    ) -> CaptureResult:
        """Capture output according to mode and limits.

        Args:
            stdout: Raw stdout bytes
            stderr: Raw stderr bytes
            step_name: Step name for log file naming
            allow_parse_error: For JSON mode, whether to allow parse errors
            output_file: Optional file to tee stdout to (gets full stream)

        Returns:
            CaptureResult with mode-specific data and truncation info
        """
        result = CaptureResult(mode=self.mode)

        # Handle output_file tee (always gets full stream)
        if output_file:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(stdout)

        # Handle stderr
        if stderr and self.log_dir:
            stderr_file = self.log_dir / f"{step_name}.stderr"
            stderr_file.parent.mkdir(parents=True, exist_ok=True)
            stderr_file.write_bytes(stderr)
            result.stderr_file = stderr_file

        # Mode-specific capture
        if self.mode == OutputCaptureMode.TEXT:
            result = self._capture_text(stdout, step_name, result)
        elif self.mode == OutputCaptureMode.LINES:
            result = self._capture_lines(stdout, step_name, result)
        elif self.mode == OutputCaptureMode.JSON:
            result = self._capture_json(stdout, step_name, allow_parse_error, result)

        return result

    def _capture_text(self, stdout: bytes, step_name: str, result: CaptureResult) -> CaptureResult:
        """Capture text mode with 8 KiB limit."""
        try:
            text = stdout.decode('utf-8', errors='replace')
        except Exception:
            text = str(stdout)

        if len(stdout) > self.TEXT_LIMIT_BYTES:
            # Truncate and spill
            result.output = text[:self.TEXT_LIMIT_BYTES]
            result.truncated = True

            if self.log_dir:
                stdout_file = self.log_dir / f"{step_name}.stdout"
                stdout_file.parent.mkdir(parents=True, exist_ok=True)
                stdout_file.write_bytes(stdout)
                result.stdout_file = stdout_file
        else:
            result.output = text

        return result

    def _capture_lines(self, stdout: bytes, step_name: str, result: CaptureResult) -> CaptureResult:
        """Capture lines mode with 10,000 lines limit."""
        try:
            text = stdout.decode('utf-8', errors='replace')
        except Exception:
            text = str(stdout)

        # Normalize CRLF to LF as per spec
        text = text.replace('\r\n', '\n')
        lines = text.split('\n')

        # Remove trailing empty line if text ends with newline
        if lines and lines[-1] == '':
            lines = lines[:-1]

        if len(lines) > self.LINES_LIMIT_COUNT:
            # Truncate and spill
            result.lines = lines[:self.LINES_LIMIT_COUNT]
            result.truncated = True

            if self.log_dir:
                stdout_file = self.log_dir / f"{step_name}.stdout"
                stdout_file.parent.mkdir(parents=True, exist_ok=True)
                stdout_file.write_bytes(stdout)
                result.stdout_file = stdout_file
        else:
            result.lines = lines

        return result

    def _capture_json(
        self,
        stdout: bytes,
        step_name: str,
        allow_parse_error: bool,
        result: CaptureResult
    ) -> CaptureResult:
        """Capture JSON mode with 1 MiB buffer limit."""
        # Check buffer size first
        if len(stdout) > self.JSON_BUFFER_LIMIT:
            if allow_parse_error:
                # Treat as text with truncation
                return self._capture_text(stdout, step_name, result)
            else:
                # This should cause exit code 2
                result.json_parse_error = f"JSON output exceeds 1 MiB limit ({len(stdout)} bytes)"
                return result

        # Try to parse JSON
        try:
            text = stdout.decode('utf-8', errors='strict')
            result.json_data = json.loads(text)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            if allow_parse_error:
                # Fall back to text mode
                result.json_parse_error = str(e)
                return self._capture_text(stdout, step_name, result)
            else:
                # This should cause exit code 2
                result.json_parse_error = str(e)
                return result

        return result