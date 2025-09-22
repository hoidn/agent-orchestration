"""
Tests for output capture module.
Covers AT-1, AT-2, AT-45, AT-52: Output capture modes and truncation.
"""

import json
import pytest
from pathlib import Path
import tempfile
import shutil

from orchestrator.exec import OutputCapture, CaptureMode, CaptureResult, StepExecutor


class TestOutputCapture:
    """Test output capture modes and limits."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace directory."""
        workspace = Path(tempfile.mkdtemp())
        yield workspace
        shutil.rmtree(workspace, ignore_errors=True)

    @pytest.fixture
    def capture(self, temp_workspace):
        """Create OutputCapture instance."""
        return OutputCapture(temp_workspace)

    def test_at1_lines_capture(self, capture):
        """AT-1: Lines capture - output_capture: lines → steps.X.lines[] populated."""
        # Test normal lines capture
        stdout = b"line1\nline2\nline3\n"
        result = capture.capture(
            stdout=stdout,
            stderr=b"",
            step_name="test_step",
            mode=CaptureMode.LINES,
        )

        assert result.mode == CaptureMode.LINES
        assert result.lines == ["line1", "line2", "line3"]
        assert result.truncated is False
        assert result.exit_code == 0

        # Verify state format (no raw output for lines mode)
        state = result.to_state_dict()
        assert "lines" in state
        assert "output" not in state  # Per spec: omit raw output for lines mode

    def test_at1_lines_capture_crlf_normalization(self, capture):
        """AT-1: Lines mode normalizes CRLF to LF."""
        stdout = b"line1\r\nline2\r\nline3"
        result = capture.capture(
            stdout=stdout,
            stderr=b"",
            step_name="test_step",
            mode=CaptureMode.LINES,
        )

        assert result.lines == ["line1", "line2", "line3"]

    def test_at1_lines_capture_truncation(self, capture):
        """AT-1: Lines mode truncates at 10,000 lines."""
        # Generate 10,001 lines
        lines = [f"line{i}" for i in range(10001)]
        stdout = "\n".join(lines).encode('utf-8')

        result = capture.capture(
            stdout=stdout,
            stderr=b"",
            step_name="test_step",
            mode=CaptureMode.LINES,
        )

        assert result.truncated is True
        assert len(result.lines) == 10000
        assert result.lines[0] == "line0"
        assert result.lines[-1] == "line9999"

        # Verify full output written to logs
        logs_file = capture.logs_dir / "test_step.stdout"
        assert logs_file.exists()
        assert logs_file.read_bytes() == stdout

    def test_at2_json_capture_success(self, capture):
        """AT-2: JSON capture - output_capture: json → steps.X.json object available."""
        data = {"key": "value", "number": 42, "array": [1, 2, 3]}
        stdout = json.dumps(data).encode('utf-8')

        result = capture.capture(
            stdout=stdout,
            stderr=b"",
            step_name="test_step",
            mode=CaptureMode.JSON,
        )

        assert result.mode == CaptureMode.JSON
        assert result.json_data == data
        assert result.truncated is False
        assert result.exit_code == 0

        # Verify state format (no raw output for successful JSON)
        state = result.to_state_dict()
        assert "json" in state
        assert "output" not in state

    def test_at14_json_oversize_fails(self, capture):
        """AT-14: JSON >1 MiB fails with exit 2."""
        # Create JSON larger than 1 MiB
        large_data = {"data": "x" * (1024 * 1024 + 1)}
        stdout = json.dumps(large_data).encode('utf-8')

        result = capture.capture(
            stdout=stdout,
            stderr=b"",
            step_name="test_step",
            mode=CaptureMode.JSON,
            allow_parse_error=False,
        )

        assert result.exit_code == 2
        assert result.error is not None
        assert result.error["type"] == "json_overflow"
        assert "1 MiB limit" in result.error["message"]

    def test_at15_json_parse_error_allowed(self, capture):
        """AT-15: JSON parse error with allow_parse_error: true succeeds."""
        stdout = b"not valid json"

        result = capture.capture(
            stdout=stdout,
            stderr=b"",
            step_name="test_step",
            mode=CaptureMode.JSON,
            allow_parse_error=True,
        )

        assert result.mode == CaptureMode.JSON
        assert result.exit_code == 0  # Success despite parse error
        assert result.output == "not valid json"  # Raw output stored
        assert result.json_data is None
        assert result.debug is not None
        assert "json_parse_error" in result.debug

    def test_at15_json_oversize_with_allow_parse_error(self, capture):
        """AT-15: JSON overflow with allow_parse_error stores truncated text."""
        # Create oversized non-JSON data
        large_text = "x" * (1024 * 1024 + 1)
        stdout = large_text.encode('utf-8')

        result = capture.capture(
            stdout=stdout,
            stderr=b"",
            step_name="test_step",
            mode=CaptureMode.JSON,
            allow_parse_error=True,
        )

        assert result.exit_code == 0
        assert result.truncated is True
        assert result.output is not None
        assert len(result.output.encode('utf-8')) <= 8 * 1024
        assert result.debug is not None
        assert "json_parse_error" in result.debug

    def test_at52_json_overflow_spills_to_logs(self, capture):
        """AT-52: JSON overflow with allow_parse_error spills full stdout to logs (regression test)."""
        # Create oversized data that triggers JSON buffer overflow
        large_text = "not json " * (128 * 1024)  # ~1.2 MiB of text
        stdout = large_text.encode('utf-8')

        result = capture.capture(
            stdout=stdout,
            stderr=b"",
            step_name="json_overflow_step",
            mode=CaptureMode.JSON,
            allow_parse_error=True,
        )

        # Verify result state
        assert result.exit_code == 0
        assert result.truncated is True
        assert result.output is not None
        assert len(result.output.encode('utf-8')) <= 8 * 1024
        assert result.debug is not None
        assert "JSON buffer overflow" in result.debug["json_parse_error"]

        # CRITICAL: Verify full output was spilled to logs (AT-52 consistency)
        logs_file = capture.logs_dir / "json_overflow_step.stdout"
        assert logs_file.exists(), "JSON overflow must spill full stdout to logs"
        assert logs_file.read_bytes() == stdout, "Spilled log must contain complete original output"

    def test_at45_text_capture_truncation(self, capture):
        """AT-45: Text mode truncates at 8 KiB and spills to logs."""
        # Create text larger than 8 KiB
        large_text = "x" * (8 * 1024 + 100)
        stdout = large_text.encode('utf-8')

        result = capture.capture(
            stdout=stdout,
            stderr=b"",
            step_name="test_step",
            mode=CaptureMode.TEXT,
        )

        assert result.mode == CaptureMode.TEXT
        assert result.truncated is True
        assert len(result.output.encode('utf-8')) <= 8 * 1024
        assert result.exit_code == 0

        # Verify full output written to logs
        logs_file = capture.logs_dir / "test_step.stdout"
        assert logs_file.exists()
        assert logs_file.read_bytes() == stdout

    def test_at52_output_tee_semantics(self, capture, temp_workspace):
        """AT-52: output_file receives full stdout while limits apply to state."""
        # Create large output that will be truncated
        large_text = "x" * (8 * 1024 + 100)
        stdout = large_text.encode('utf-8')
        output_file = temp_workspace / "output.txt"

        result = capture.capture(
            stdout=stdout,
            stderr=b"",
            step_name="test_step",
            mode=CaptureMode.TEXT,
            output_file=output_file,
        )

        # State should be truncated
        assert result.truncated is True
        assert len(result.output.encode('utf-8')) <= 8 * 1024

        # But output_file should have full content
        assert output_file.exists()
        assert output_file.read_bytes() == stdout

    def test_at67_tee_on_json_parse_failure(self, capture, temp_workspace):
        """AT-67: Tee on JSON parse failure - output_file still receives full stdout when JSON parsing fails."""
        # Test with invalid JSON that will fail to parse
        invalid_json = b"{ invalid json content }"
        output_file = temp_workspace / "output.txt"

        # Test without allow_parse_error (should fail with exit 2)
        result = capture.capture(
            stdout=invalid_json,
            stderr=b"",
            step_name="test_step",
            mode=CaptureMode.JSON,
            output_file=output_file,
            allow_parse_error=False,
        )

        # Should fail with exit code 2
        assert result.exit_code == 2
        assert result.error is not None
        assert result.error["type"] == "json_parse_error"

        # But output_file should still have received the full stdout
        assert output_file.exists()
        assert output_file.read_bytes() == invalid_json

        # Test with truncated JSON that will fail to parse
        large_invalid_json = b"{ " + b"x" * (8 * 1024) + b" not valid json"
        output_file2 = temp_workspace / "output2.txt"

        result2 = capture.capture(
            stdout=large_invalid_json,
            stderr=b"",
            step_name="test_step2",
            mode=CaptureMode.JSON,
            output_file=output_file2,
            allow_parse_error=False,
        )

        # Should fail with exit code 2
        assert result2.exit_code == 2
        assert result2.error is not None
        assert result2.error["type"] == "json_parse_error"

        # output_file should have full content even though parsing failed
        assert output_file2.exists()
        assert output_file2.read_bytes() == large_invalid_json

        # Test with JSON buffer overflow (>1 MiB)
        oversized_json = b"[" + b"1," * (512 * 1024) + b"2]"  # Over 1 MiB
        output_file3 = temp_workspace / "output3.txt"

        result3 = capture.capture(
            stdout=oversized_json,
            stderr=b"",
            step_name="test_step3",
            mode=CaptureMode.JSON,
            output_file=output_file3,
            allow_parse_error=False,
        )

        # Should fail with exit code 2 due to buffer overflow
        assert result3.exit_code == 2
        assert result3.error is not None
        assert result3.error["type"] == "json_overflow"

        # output_file should still have the full content
        assert output_file3.exists()
        assert output_file3.read_bytes() == oversized_json

    def test_stderr_capture(self, capture):
        """Stderr is always written to logs when non-empty."""
        stdout = b"stdout content"
        stderr = b"error message"

        result = capture.capture(
            stdout=stdout,
            stderr=stderr,
            step_name="test_step",
            mode=CaptureMode.TEXT,
        )

        # Check stderr was written to logs
        stderr_file = capture.logs_dir / "test_step.stderr"
        assert stderr_file.exists()
        assert stderr_file.read_bytes() == stderr


class TestStepExecutor:
    """Test step executor with real command execution."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace directory."""
        workspace = Path(tempfile.mkdtemp())
        yield workspace
        shutil.rmtree(workspace, ignore_errors=True)

    @pytest.fixture
    def executor(self, temp_workspace):
        """Create StepExecutor instance."""
        return StepExecutor(temp_workspace)

    def test_command_execution_text_mode(self, executor):
        """Test basic command execution with text capture."""
        result = executor.execute_command(
            step_name="echo_test",
            command="echo 'Hello World'",
            output_capture=CaptureMode.TEXT,
        )

        assert result.exit_code == 0
        assert result.capture_result.output.strip() == "Hello World"
        assert result.capture_result.truncated is False
        assert result.duration_ms > 0

    def test_command_execution_lines_mode(self, executor):
        """Test command execution with lines capture."""
        result = executor.execute_command(
            step_name="lines_test",
            command="printf 'line1\\nline2\\nline3'",
            output_capture=CaptureMode.LINES,
        )

        assert result.exit_code == 0
        assert result.capture_result.lines == ["line1", "line2", "line3"]
        assert result.capture_result.truncated is False

    def test_command_execution_json_mode(self, executor):
        """Test command execution with JSON capture."""
        result = executor.execute_command(
            step_name="json_test",
            command='echo \'{"key": "value", "number": 42}\'',
            output_capture=CaptureMode.JSON,
        )

        assert result.exit_code == 0
        assert result.capture_result.json_data == {"key": "value", "number": 42}
        assert result.capture_result.truncated is False

    def test_command_timeout(self, executor):
        """Test command timeout handling."""
        result = executor.execute_command(
            step_name="timeout_test",
            command="sleep 10",
            timeout_sec=1,
            output_capture=CaptureMode.TEXT,
        )

        assert result.exit_code == 124  # Timeout exit code per spec
        assert result.error is not None
        assert result.error["type"] == "timeout"

    def test_command_with_env_vars(self, executor):
        """Test command execution with environment variables."""
        result = executor.execute_command(
            step_name="env_test",
            command="printenv TEST_VAR",  # Use printenv which doesn't need shell expansion
            env={"TEST_VAR": "test_value"},
            output_capture=CaptureMode.TEXT,
        )

        assert result.exit_code == 0
        assert result.capture_result.output.strip() == "test_value"

    def test_failed_command(self, executor):
        """Test handling of failed commands."""
        result = executor.execute_command(
            step_name="fail_test",
            command="false",  # Use 'false' command which returns exit code 1
            output_capture=CaptureMode.TEXT,
        )

        assert result.exit_code == 1
        assert result.error is None  # Normal non-zero exit, not an error

    def test_to_state_dict(self, executor):
        """Test conversion to state dictionary format."""
        result = executor.execute_command(
            step_name="state_test",
            command="echo 'test'",
            output_capture=CaptureMode.TEXT,
        )

        state = result.to_state_dict()
        assert "exit_code" in state
        assert "duration_ms" in state
        assert "output" in state
        assert "truncated" in state