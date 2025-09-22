"""
Output capture module for handling step outputs with truncation.
Implements text, lines, and JSON capture modes per specs/io.md.

AT-1: Lines capture - output_capture: lines → steps.X.lines[] populated
AT-2: JSON capture - output_capture: json → steps.X.json object available
AT-45: STDOUT capture threshold - text > 8 KiB truncates state and spills to logs
AT-52: Output tee semantics - output_file receives full stdout while limits apply
"""

import json
from pathlib import Path
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass


class CaptureMode(str, Enum):
    """Output capture modes per spec."""
    TEXT = "text"
    LINES = "lines"
    JSON = "json"


@dataclass
class CaptureResult:
    """Result of output capture processing."""
    mode: CaptureMode
    output: Optional[str] = None  # Raw text (for text mode or parse errors)
    lines: Optional[List[str]] = None  # For lines mode
    json_data: Optional[Dict[str, Any]] = None  # For json mode
    truncated: bool = False
    exit_code: int = 0
    error: Optional[Dict[str, Any]] = None
    debug: Optional[Dict[str, Any]] = None

    def to_state_dict(self) -> Dict[str, Any]:
        """Convert to state.json format."""
        result: Dict[str, Any] = {
            "exit_code": self.exit_code,
            "truncated": self.truncated,
        }

        # Per spec: For lines/json, omit raw output to avoid duplication
        if self.mode == CaptureMode.TEXT or (self.mode == CaptureMode.JSON and self.json_data is None):
            if self.output is not None:
                result["output"] = self.output

        if self.mode == CaptureMode.LINES and self.lines is not None:
            result["lines"] = self.lines

        if self.mode == CaptureMode.JSON and self.json_data is not None:
            result["json"] = self.json_data

        if self.error:
            result["error"] = self.error

        if self.debug:
            result["debug"] = self.debug

        return result


class OutputCapture:
    """
    Handles output capture with mode-specific processing and truncation.
    Implements specs/io.md requirements.
    """

    # Capture limits per spec
    TEXT_LIMIT_BYTES = 8 * 1024  # 8 KiB for text mode
    LINES_LIMIT = 10_000  # 10,000 lines max
    JSON_BUFFER_LIMIT = 1024 * 1024  # 1 MiB for JSON parsing

    def __init__(self, workspace: Path, logs_dir: Optional[Path] = None):
        """
        Initialize output capture.

        Args:
            workspace: Base workspace directory
            logs_dir: Directory for overflow logs (default: workspace/logs)
        """
        self.workspace = workspace
        self.logs_dir = logs_dir or workspace / "logs"
        self.logs_dir.mkdir(exist_ok=True, parents=True)

    def capture(
        self,
        stdout: bytes,
        stderr: bytes,
        step_name: str,
        mode: CaptureMode = CaptureMode.TEXT,
        output_file: Optional[Path] = None,
        allow_parse_error: bool = False,
        exit_code: int = 0,
    ) -> CaptureResult:
        """
        Process captured output according to mode and limits.

        Args:
            stdout: Raw stdout bytes
            stderr: Raw stderr bytes
            step_name: Step name for logging
            mode: Capture mode (text/lines/json)
            output_file: Optional file to tee full output to
            allow_parse_error: For JSON mode, whether to allow parse errors
            exit_code: Process exit code

        Returns:
            CaptureResult with processed output
        """
        # Handle stderr (always written to logs if non-empty)
        if stderr:
            stderr_file = self.logs_dir / f"{step_name}.stderr"
            stderr_file.write_bytes(stderr)

        # Tee full stdout to output_file if specified (AT-52)
        if output_file:
            output_file.write_bytes(stdout)

        # Decode stdout for processing
        try:
            stdout_text = stdout.decode('utf-8', errors='replace')
        except Exception:
            stdout_text = stdout.decode('latin-1', errors='replace')

        # Process based on mode
        if mode == CaptureMode.TEXT:
            return self._capture_text(stdout_text, stdout, step_name, exit_code)
        elif mode == CaptureMode.LINES:
            return self._capture_lines(stdout_text, stdout, step_name, exit_code)
        elif mode == CaptureMode.JSON:
            return self._capture_json(stdout_text, stdout, step_name, allow_parse_error, exit_code)
        else:
            raise ValueError(f"Unknown capture mode: {mode}")

    def _capture_text(self, text: str, raw_stdout: bytes, step_name: str, exit_code: int) -> CaptureResult:
        """
        Capture text mode with 8 KiB limit (AT-45).
        """
        truncated = False
        output = text

        # Check size limit (8 KiB)
        if len(text.encode('utf-8')) > self.TEXT_LIMIT_BYTES:
            truncated = True
            # Truncate to fit in 8 KiB when encoded
            output = text[:self.TEXT_LIMIT_BYTES]
            # Ensure we don't split multi-byte characters
            while len(output.encode('utf-8')) > self.TEXT_LIMIT_BYTES:
                output = output[:-1]

            # Write full output to logs
            stdout_file = self.logs_dir / f"{step_name}.stdout"
            stdout_file.write_bytes(raw_stdout)

        return CaptureResult(
            mode=CaptureMode.TEXT,
            output=output,
            truncated=truncated,
            exit_code=exit_code,
        )

    def _capture_lines(self, text: str, raw_stdout: bytes, step_name: str, exit_code: int) -> CaptureResult:
        """
        Capture lines mode with 10,000 line limit (AT-1).
        Normalizes CRLF to LF per spec.
        """
        # Normalize line endings and split
        text = text.replace('\r\n', '\n')
        lines = text.split('\n')

        # Remove empty trailing line if present
        if lines and lines[-1] == '':
            lines = lines[:-1]

        truncated = False
        if len(lines) > self.LINES_LIMIT:
            truncated = True
            lines = lines[:self.LINES_LIMIT]

            # Write full output to logs
            stdout_file = self.logs_dir / f"{step_name}.stdout"
            stdout_file.write_bytes(raw_stdout)

        return CaptureResult(
            mode=CaptureMode.LINES,
            lines=lines,
            truncated=truncated,
            exit_code=exit_code,
        )

    def _capture_json(
        self,
        text: str,
        raw_stdout: bytes,
        step_name: str,
        allow_parse_error: bool,
        exit_code: int
    ) -> CaptureResult:
        """
        Capture JSON mode with 1 MiB buffer limit (AT-2, AT-14, AT-15).
        """
        # Check buffer limit first
        if len(raw_stdout) > self.JSON_BUFFER_LIMIT:
            if allow_parse_error:
                # AT-15: With allow_parse_error, treat as text with 8 KiB limit
                truncated_output = text[:self.TEXT_LIMIT_BYTES]
                while len(truncated_output.encode('utf-8')) > self.TEXT_LIMIT_BYTES:
                    truncated_output = truncated_output[:-1]

                # Write full output to logs (AT-52: spill consistency with text mode)
                stdout_file = self.logs_dir / f"{step_name}.stdout"
                stdout_file.write_bytes(raw_stdout)

                return CaptureResult(
                    mode=CaptureMode.JSON,
                    output=truncated_output,
                    truncated=True,
                    exit_code=0,  # Success with parse error allowed
                    debug={"json_parse_error": f"JSON buffer overflow: {len(raw_stdout)} bytes exceeds 1 MiB limit"}
                )
            else:
                # AT-14: JSON overflow fails with exit 2
                return CaptureResult(
                    mode=CaptureMode.JSON,
                    exit_code=2,
                    error={
                        "type": "json_overflow",
                        "message": f"JSON buffer overflow: {len(raw_stdout)} bytes exceeds 1 MiB limit",
                        "context": {
                            "buffer_size": len(raw_stdout),
                            "limit": self.JSON_BUFFER_LIMIT,
                        }
                    }
                )

        # Try to parse JSON
        try:
            json_data = json.loads(text)
            return CaptureResult(
                mode=CaptureMode.JSON,
                json_data=json_data,
                exit_code=exit_code,
            )
        except (json.JSONDecodeError, ValueError) as e:
            if allow_parse_error:
                # AT-15: With allow_parse_error, store raw output (8 KiB limit)
                truncated = False
                output = text
                if len(text.encode('utf-8')) > self.TEXT_LIMIT_BYTES:
                    truncated = True
                    output = text[:self.TEXT_LIMIT_BYTES]
                    while len(output.encode('utf-8')) > self.TEXT_LIMIT_BYTES:
                        output = output[:-1]

                    # Write full output to logs
                    stdout_file = self.logs_dir / f"{step_name}.stdout"
                    stdout_file.write_bytes(raw_stdout)

                return CaptureResult(
                    mode=CaptureMode.JSON,
                    output=output,
                    truncated=truncated,
                    exit_code=0,  # Success with parse error allowed
                    debug={"json_parse_error": str(e)}
                )
            else:
                # Parse failure without allow_parse_error: exit 2
                return CaptureResult(
                    mode=CaptureMode.JSON,
                    exit_code=2,
                    error={
                        "type": "json_parse_error",
                        "message": f"Failed to parse JSON: {e}",
                        "context": {}
                    }
                )